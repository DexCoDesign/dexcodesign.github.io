#!/usr/bin/env python3
"""Add four fixed-lift arm pairs while preserving each native kinematic chain."""
import argparse,copy,json,sys,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from export_hand_studio import OUT,export_one

MODELS={'franka_fr3':'Franka FR3','kinova_gen3':'Kinova Gen3','aloha2':'ALOHA 2 · dual ViperX','openarm2':'OpenArm 2.0'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project-root',type=Path,required=True);a=p.parse_args()
    root=a.project_root.resolve();sys.path.insert(0,str(root/'source/dexcodesign'))
    from dexcodesign.robot_layout.builder import meshless
    from dexcodesign.robot_layout.frames import worlds
    import mujoco,trimesh
    catalog=json.loads((OUT/'catalog.json').read_text());catalog['records']=[r for r in catalog['records'] if r['id'] not in MODELS];rows=[];audit=[]
    reflection=np.diag([1.,-1.,1.]);canonical_mirror=np.diag([-1.,1.,1.])
    for mid,label in MODELS.items():
        base=root/'assets/bimanual_manipulators'/mid;urdf=base/'body/robot.urdf';tree=ET.parse(urdf).getroot();manifest=json.loads((base/'body/manifest.json').read_text());home=json.loads((base/'home.json').read_text());groups=manifest['groups']
        row=export_one(urdf,mid,label,'manipulator',provenance={'host':'DexCoDesign fixed-lift bimanual library','commit':'22ed597813a25068f97bf474275e3b1f29a3ff76','path':str(urdf.relative_to(root))})
        mp=OUT/(mid+'.json');meta=json.loads(mp.read_text());frames=worlds(tree,home)
        # Canonical hands mirror in X; the native arm flange axes need not.
        adapters={'left':np.eye(3),'right':frames['right_eef_mount'][:3,:3].T@reflection@frames['left_eef_mount'][:3,:3]@canonical_mirror}
        scene=trimesh.load(OUT/(mid+'.glb'),force='scene');mounts={}
        for side in ('left','right'):
            node=side+'_hand_anchor';t=np.eye(4);t[:3,:3]=adapters[side]
            scene.graph.update(node,'link__'+side+'_eef_mount',matrix=t);mounts[side]=node
        (OUT/(mid+'.glb')).write_bytes(scene.export(file_type='glb',include_normals=True))
        model=mujoco.MjModel.from_xml_string(ET.tostring(meshless(tree),encoding='unicode'));data=mujoco.MjData(model)
        ids={s:np.array([model.joint(n).qposadr[0] for n in groups[s]]) for s in groups}
        limits={s:np.array([model.joint(n).range if model.joint(n).limited[0] else [-np.pi,np.pi] for n in groups[s]]) for s in groups}
        bodies={s:model.body(s+'_eef_mount').id for s in groups};home_q={s:np.array([home[n] for n in groups[s]]) for s in groups}
        seed_sign=np.array([-1,1,1,-1,1,-1] if mid=='aloha2' else [-1,-1,-1,1,-1,-1,-1] if mid=='openarm2' else [-1,1,-1,1,-1,1,-1])
        for n,q in home.items():data.joint(n).qpos[0]=q
        def mirrored_right(left,seed):
            data.qpos[ids['left']]=left;mujoco.mj_forward(model,data)
            target_position=reflection@data.xpos[bodies['left']]
            target_rotation=reflection@data.xmat[bodies['left']].reshape(3,3)@adapters['left']@canonical_mirror@adapters['right'].T
            def residual(q):
                data.qpos[ids['right']]=q;mujoco.mj_forward(model,data)
                return np.r_[10*(data.xpos[bodies['right']]-target_position),Rotation.from_matrix(target_rotation.T@data.xmat[bodies['right']].reshape(3,3)).as_rotvec(),1e-4*(q-seed)]
            low,high=limits['right'].T;fit=least_squares(residual,np.clip(seed,low+1e-7,high-1e-7),bounds=(low+1e-7,high-1e-7),max_nfev=160,ftol=1e-10,xtol=1e-10,gtol=1e-10)
            residual(fit.x);error=float(np.linalg.norm(data.xpos[bodies['right']]-target_position))
            return fit.x,error
        poses={'neutral':home.copy()}
        low,high=limits['left'].T
        spread=.65*home_q['left']+.35*np.clip(np.zeros(len(low)),low,high)
        fold=home_q['left'].copy();elbow=2 if mid=='aloha2' else 3;delta=.4*(1 if fold[elbow]>=0 else -1);fold[elbow]+=delta
        if len(fold)>5:fold[5]-=.4*delta
        for name,left in [('spread',spread),('fold',fold)]:
            left=np.clip(left,low+1e-6,high-1e-6);seed=home_q['right']+seed_sign*(left-home_q['left']);right,error=mirrored_right(left,seed)
            if error>.003:raise ValueError((mid,name,'mirror IK residual',error))
            poses[name]={**dict(zip(groups['left'],left.tolist())),**dict(zip(groups['right'],right.tolist()))}
        # Sample the two native chains independently. Joint angles are not equated.
        samples=[];maximum_error=0.;n=len(low);coefficient=np.cos(np.arange(n)*.43)
        aa=.09*coefficient;bb=.027*np.sin(np.arange(n)*.57+.3);radius=np.sqrt(aa*aa+bb*bb)
        center=np.clip(home_q['left']+bb,low+radius+.003,high-radius-.003)
        for phase in np.linspace(0,2*np.pi,65):
            left=center+aa*np.sin(phase)-bb*np.cos(phase);seed=home_q['right']+seed_sign*(left-home_q['left']);right,error=mirrored_right(left,seed);maximum_error=max(maximum_error,error)
            samples.append({**dict(zip(groups['left'],left.tolist())),**dict(zip(groups['right'],right.tolist()))})
        if maximum_error>.001:raise ValueError((mid,'motion mirror error',maximum_error))
        for control in meta['controls']:
            side='left' if control['name'].startswith('left_') else 'right'
            control['group']=side.title()+' arm';control['label']='Joint '+str(groups[side].index(control['name'])+1)
        meta.update(side='whole robot',base_model={'type':'fixed','joints':[],'wheel_drive_model':False},upright_node='link__lift_platform',hand_mounts=mounts,end_effectors_removed=True,root_link='world',poses=poses,pose_order=['neutral','spread','fold'],motion_pairs=[],motion_samples=samples,
                    view_direction=[3,-2,.8],preview_note='Fixed base · 45° mounting · Explore both arms and swap end effectors.',
                    mounting={'angle_degrees':45,'base_dof':0,'housing_rgba':[.32,.35,.38,1.],'cradle_wall_m':.018,'rim_screws_per_side':5,'arm_configuration':'independent native chains','hand_frame_calibration':{s:Rotation.from_matrix(r).as_quat().tolist() for s,r in adapters.items()}},
                    bytes=(OUT/(mid+'.glb')).stat().st_size)
        mp.write_text(json.dumps(meta,separators=(',',':'))+'\n');rows.append({**row,'side':'whole robot','bytes':meta['bytes']})
        audit.append({'id':mid,'max_motion_mirror_error_m':maximum_error,'native_home_preserved':poses['neutral']==home,'frames':len(frames)})
    index=next((i for i,r in enumerate(catalog['records']) if r['category']=='others'),len(catalog['records']));catalog['records'][index:index]=rows
    (OUT/'catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    licenses=OUT/'licenses';licenses.mkdir(exist_ok=True)
    source=root/'assets/bimanual_manipulators/sources'
    for relative in ['mujoco_menagerie/franka_fr3/LICENSE','mujoco_menagerie/kinova_gen3/LICENSE','mujoco_menagerie/aloha/LICENSE','openarm_description/LICENSE.txt']:
        p=source/relative;(licenses/('bimanual-'+p.parent.name+'-'+p.name)).write_bytes(p.read_bytes())
    print(json.dumps({'added':audit},indent=2))

if __name__=='__main__':main()
