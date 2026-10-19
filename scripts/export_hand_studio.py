#!/usr/bin/env python3
"""Build static, visual-only articulated GLBs from authoritative right URDFs.

No simulation service, checkpoints, training code, or collision geometry is
published. Re-run with a fresh Skynet snapshot to maintain real embodiments.
"""
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/models/studio'
REFLECT = np.diag([-1., 1., 1., 1.])


def recovered_materials(snapshot):
    """Recover exact Shadow MJCF colors by body/include (no geometry edits)."""
    base=snapshot/'shadow_hand_e/source/mujoco_models'
    result={}
    if not base.exists(): return result
    mats={m.get('name'):np.fromstring(m.get('rgba','1 1 1 1'),sep=' ').tolist()
          for m in ET.parse(base/'shared_assets.xml').getroot().iter('material')}
    for body in ET.parse(base/'sr_hand_e_model.canonical.xml').getroot().iter('body'):
        colors=[]
        for include in body.findall('include'):
            for geom in ET.parse(base/include.get('file')).getroot().iter('geom'):
                if geom.get('class')=='visual' and geom.get('material') in mats:colors.append(mats[geom.get('material')])
        if colors and all(c==colors[0] for c in colors):result[body.get('name')]=colors[0]
    return result


def appearance(mid, link, color, source, recovered):
    # These rules affect the static display only, never the authoritative URDF.
    if mid=='shadow_hand_e' and source=='unspecified-fallback' and link in recovered:
        return np.array(recovered[link]),'restored-source-mjcf'
    if mid=='inspire_rh56dfx' and source=='unspecified-fallback':
        return np.array([.1,.1,.1,1]),'restored-source-mjcf-visual-default'
    if mid=='mano' and source=='unspecified-fallback':return np.array([.5,.5,.5,1]),'source-mujoco-default'
    if mid=='tesollo_dg5f' and source=='unspecified-fallback':
        rgba=([.12,.13,.14,1] if 'mount' in link or 'tip' in link else
              [.86,.87,.88,1] if 'palm' in link or 'base' in link else [.61,.64,.66,1])
        return np.array(rgba),'photo-approximation-TESOLLO-DG5F'
    if mid=='sharpa_wave_01' and color[1]>.95 and color[0]<.3:
        return np.array([.12,.13,.14,1]),'photo-approximation-tactile-elastomer'
    if mid=='unitree_dex5_1' and color[3]<1:
        color=color.copy();color[3]=1
        return color,'source-rgb-opaque-display-casing'
    return color,source


def origin(el):
    matrix = np.eye(4)
    if el is not None:
        matrix[:3, :3] = Rotation.from_euler('xyz', np.fromstring(el.get('rpy', '0 0 0'), sep=' ')).as_matrix()
        matrix[:3, 3] = np.fromstring(el.get('xyz', '0 0 0'), sep=' ')
    return matrix


def label(name):
    return name.replace('_', ' ').replace('right ', '').replace('r ', '').title()


def export_one(path, mid, name, category, spec=None, provenance=None, mirror=False, recovered=None):
    robot = ET.parse(path).getroot()
    scene = trimesh.Scene(base_frame='studio_world')
    global_mats = {m.get('name'): m for m in robot.findall('material')}
    joints, joint_by_child, controls = [], {}, []
    active = {c['name']: c for c in spec['controls']} if spec else {}
    passive = {p['name'] for p in spec['passive']} if spec else set()
    mesh_hashes, color_audit = {}, []
    children = {j.find('child').get('link') for j in robot.findall('joint')}
    for link in robot.findall('link'):
        if link.get('name') not in children:
            scene.graph.update('link__' + link.get('name'), 'studio_world', matrix=np.eye(4))
    for joint in robot.findall('joint'):
        child, parent = joint.find('child').get('link'), joint.find('parent').get('link')
        matrix = origin(joint.find('origin'))
        if mirror:
            matrix = REFLECT @ matrix @ REFLECT
        node = 'link__' + child
        scene.graph.update(node, 'link__' + parent, matrix=matrix)
        kind = joint.get('type')
        if kind == 'fixed':
            continue
        jname = joint.get('name')
        axis = joint.find('axis')
        axis = np.fromstring(axis.get('xyz', '1 0 0') if axis is not None else '1 0 0', sep=' ')
        if mirror:
            axis = REFLECT[:3, :3] @ axis * (1 if kind == 'prismatic' else -1)
        lim = joint.find('limit')
        lower, upper = (float(lim.get('lower', '-3.14159')), float(lim.get('upper', '3.14159'))) if lim is not None else (-np.pi, np.pi)
        mimic = joint.find('mimic')
        mode = 'passive' if jname in passive else 'coupled' if mimic is not None else 'active'
        # Root translations/rotations are not finger controls in a fixed display.
        root_dof = bool(re.search(r'(?:^|_)(?:pos|rot)_[xyz]$', jname))
        if root_dof:
            mode = 'fixed'
        row = dict(name=jname, node=node, type=kind, axis=axis.tolist(),
                   position=matrix[:3, 3].tolist(), quaternion=Rotation.from_matrix(matrix[:3, :3]).as_quat().tolist(),
                   lower=lower, upper=upper, mode=mode)
        if mimic is not None:
            row['mimic'] = dict(source=mimic.get('joint'), multiplier=float(mimic.get('multiplier', 1)), offset=float(mimic.get('offset', 0)))
        if spec:
            match = next((p for p in spec.get('actuator_couplings', []) if p['name'] == jname), None)
            if match:
                row['mimic'] = dict(source=match['source'], multiplier=match['multiplier'], offset=match.get('offset', 0))
        joints.append(row)
        joint_by_child[child] = row
        if mode == 'active':
            item = active.get(jname, {})
            group = item.get('group') or next((n.title() for n in ['thumb', 'index', 'middle', 'ring', 'little', 'pinky', 'toe'] if n in jname.lower()), 'Joints')
            controls.append(dict(name=jname, label=item.get('label', label(jname)), group=group, lower=lower, upper=upper, unit='m' if kind == 'prismatic' else 'rad'))
    for link in robot.findall('link'):
        groups = defaultdict(list)
        for vi, visual in enumerate(link.findall('visual')):
            geom = visual.find('geometry')
            if geom is None:
                continue
            material = visual.find('material')
            if material is not None and material.find('color') is None:
                material = global_mats.get(material.get('name'), material)
            col = material.find('color') if material is not None else None
            color = np.fromstring(col.get('rgba'), sep=' ') if col is not None else np.array([.68, .71, .74, 1.])
            color_source='urdf' if col is not None else 'unspecified-fallback'
            original_color=color.tolist() if col is not None else None
            node = geom.find('mesh')
            if node is not None:
                filename = node.get('filename')
                if filename.startswith('package://'):
                    raise ValueError('Resolve package paths in the authoritative export first: ' + filename)
                meshpath = (path.parent / filename).resolve()
                mesh_hashes[filename] = hashlib.sha256(meshpath.read_bytes()).hexdigest()
                mesh = trimesh.load(meshpath, force='mesh', process=False)
                mesh.apply_scale(np.fromstring(node.get('scale', '1 1 1'), sep=' '))
                if col is None and mesh.visual.kind=='texture':
                    mat=mesh.visual.material
                    color=np.asarray(getattr(mat,'diffuse',[173,181,189,255]),dtype=float)/255
                    color_source='mesh-material-diffuse'
            elif geom.find('box') is not None:
                mesh = trimesh.creation.box(np.fromstring(geom.find('box').get('size'), sep=' '))
            elif geom.find('cylinder') is not None:
                node = geom.find('cylinder');mesh = trimesh.creation.cylinder(float(node.get('radius')), float(node.get('length')), sections=32)
            elif geom.find('sphere') is not None:
                mesh = trimesh.creation.icosphere(subdivisions=2, radius=float(geom.find('sphere').get('radius')))
            else:
                continue
            color,color_source=appearance(mid,link.get('name'),color,color_source,recovered or {})
            color_audit.append(dict(link=link.get('name'), visual=vi, rgba=color.tolist(), source_rgba=original_color, origin=color_source))
            mesh.apply_transform(origin(visual.find('origin')))
            if mirror:
                mesh.apply_transform(REFLECT)
            groups[tuple(color)].append(mesh)
        for gi, (rgba, pieces) in enumerate(groups.items()):
            mesh = trimesh.util.concatenate(pieces)
            # Display-only simplification; source geometry never changes.
            if len(mesh.faces) > 15000:
                mesh = mesh.simplify_quadric_decimation(face_count=15000)
            # Native MuJoCo used smooth mesh normals. Merge coincident STL
            # vertices before exporting normals instead of shading each face.
            mesh.merge_vertices(merge_norm=True,merge_tex=True)
            _ = mesh.vertex_normals
            mesh.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
                baseColorFactor=np.clip(np.array(rgba)*255, 0, 255).astype(np.uint8),
                metallicFactor=.12, roughnessFactor=.56))
            scene.add_geometry(mesh, node_name=f'visual__{link.get("name")}__{gi}', parent_node_name='link__' + link.get('name'))
    if spec:
        poses = {k: {n: float(np.radians(v)) for n, v in values.items()} for k, values in spec['poses'].items()}
    else:
        poses = {'neutral': {c['name']: float(np.clip(0, c['lower'], c['upper'])) for c in controls}}
        # A modest articulation preview, not an inferred grasp or retarget pose.
        poses['flex']={c['name']:float(np.clip(0,c['lower'],c['upper'])) if re.search('spread|splay|yaw|rot|wrist|WRJ|J4|J5',c['name'],re.I)
                       else float(c['lower']*.2+c['upper']*.25) for c in controls}
        poses['flex']={c['name']:float(np.clip(poses['flex'][c['name']],c['lower'],c['upper'])) for c in controls}
    OUT.mkdir(parents=True, exist_ok=True)
    glb = scene.export(file_type='glb',include_normals=True)
    (OUT / f'{mid}.glb').write_bytes(glb)
    model = dict(id=mid, name=name, category=category, side='right', glb=f'assets/models/studio/{mid}.glb',
                 bytes=len(glb), joints=joints, controls=controls, poses=poses,
                 counts=dict(active=len(controls), coupled=sum(j['mode']=='coupled' for j in joints), passive=sum(j['mode']=='passive' for j in joints)),
                 source=provenance, source_urdf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 source_mesh_sha256=mesh_hashes, display_reflection='X reflection of AI source; axial vectors reflected with determinant sign' if mirror else None,
                 bounds=scene.bounds.tolist(), materials=color_audit,
                 view_direction=[1,.35,.28] if mid=='tesollo_dg5f' else [.42,1,.28],
                 pinch_note=spec.get('pinch_note') if spec else None,
                 semantics='Visual meshes and exact joint forward kinematics. No physics, contact, grasp or payload validation in the browser.')
    (OUT / f'{mid}.json').write_text(json.dumps(model, separators=(',', ':')) + '\n')
    print(mid, len(glb), len(controls), 'controls', flush=True)
    return {k: model[k] for k in ['id', 'name', 'category', 'side', 'counts', 'bytes']} | {'metadata': f'assets/models/studio/{mid}.json'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ai-root', type=Path, required=True)
    ap.add_argument('--skynet-root', type=Path)
    ap.add_argument('--snapshot-commit', default='unknown')
    ap.add_argument('--skip-ai',action='store_true')
    args = ap.parse_args()
    records = []
    if args.skip_ai:
        records=[r for r in json.loads((OUT/'catalog.json').read_text())['records'] if r['category']=='ai']
    for row in ([] if args.skip_ai else json.loads((args.ai_root / 'catalog.json').read_text())):
        base = args.ai_root / 'models' / row['id']
        spec = json.loads((base / 'specification.json').read_text())
        records.append(export_one(base / 'hand.urdf', row['id'], row['name'], 'ai', spec, 'Locally generated mechanical concept', mirror=True))
    if args.skynet_root:
        registry = json.loads((args.skynet_root / 'direct_motor/registry.json').read_text())
        recovered=recovered_materials(args.skynet_root)
        for mid, record in registry['hands'].items():
            entry = record.get('entries', {}).get('right')
            if not entry:
                continue
            path = args.skynet_root / entry['path']
            category = 'others' if 'foot' in mid else 'hand' if mid == 'mano' else 'robot'
            records.append(export_one(path, mid, record['display_name'], category, recovered=recovered,
                provenance={'host':'Skynet','commit':args.snapshot_commit,'path':'assets/robot_hands/' + entry['path'],'upstream':record.get('source')}))
        license_dir=OUT/'licenses';license_dir.mkdir(exist_ok=True)
        for path in args.skynet_root.glob('*/LICENSE*'):
            shutil.copy2(path,license_dir/(path.parent.name+'-'+path.name))
    (OUT / 'catalog.json').write_text(json.dumps(dict(version=1, records=records), indent=2) + '\n')


if __name__ == '__main__':
    main()
