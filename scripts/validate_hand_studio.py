"""Check every exported joint transform against its source URDF FK."""
import argparse,json
from pathlib import Path
import numpy as np
import trimesh,yourdfpy
from scipy.spatial.transform import Rotation
from export_hand_studio import OUT,REFLECT

ap=argparse.ArgumentParser();ap.add_argument('--ai-root',type=Path,required=True);ap.add_argument('--skynet-root',type=Path,required=True)
ap.add_argument('--hand', help='Validate one model without loading unrelated sources')
args=ap.parse_args()
rng=np.random.default_rng(42);results=[]
for record in json.loads((OUT/'catalog.json').read_text())['records']:
    if record['category']=='manipulator':continue
    if args.hand and record['id']!=args.hand:continue
    m=json.loads((OUT/f'{record["id"]}.json').read_text());ai=record['category']=='ai'
    path=(OUT/'sources/talon9/hand.urdf' if record['id']=='talon9' else
          args.ai_root/'models'/record['id']/'hand.urdf' if ai else
          args.skynet_root/'direct_motor'/record['id']/'right/hand.urdf')
    source=yourdfpy.URDF.load(path,load_meshes=False,load_collision_meshes=False,build_scene_graph=True)
    glb=trimesh.load(OUT/f'{record["id"]}.glb',force='scene');maxerr=0.
    for _ in range(5):
        q={c['name']:float(rng.uniform(c['lower'],c['upper'])) for c in m['controls']}
        source.update_cfg(q)
        pending={j['name']:j for j in m['joints'] if j['name'] not in q}
        while pending:
            before=len(pending)
            for name,j in list(pending.items()):
                if j.get('mimic'):
                    mm=j['mimic']
                    if mm['source'] not in q:continue
                    q[name]=q[mm['source']]*mm['multiplier']+mm['offset']
                else:q[name]=0.
                pending.pop(name)
            assert len(pending)<before,'Cyclic mimic'
        for j in m['joints']:
            T=np.eye(4);T[:3,:3]=Rotation.from_quat(j['quaternion']).as_matrix();T[:3,3]=j['position']
            R=np.eye(4)
            value=np.clip(q[j['name']],j['lower'],j['upper'])
            if j['type']=='prismatic':R[:3,3]=np.asarray(j['axis'])*value
            else:R[:3,:3]=Rotation.from_rotvec(np.asarray(j['axis'])*value).as_matrix()
            parent=glb.graph.transforms.parents[j['node']];glb.graph.update(j['node'],parent,matrix=T@R)
        # Sample within mimic limits; compare independent nodes and their parents.
        for j in m['joints']:
            if j.get('mimic'):continue
            actual=glb.graph.get(j['node'])[0];expected=source.get_transform(j['node'][6:])
            if m.get('display_reflection'):expected=REFLECT@expected@REFLECT
            maxerr=max(maxerr,float(np.max(np.abs(actual-expected))))
    assert maxerr<2e-6,(record['id'],maxerr)
    assert record['side']=='right'
    results.append(dict(id=record['id'],max_transform_error=maxerr,active=len(m['controls'])))
print(json.dumps(results,indent=2))
