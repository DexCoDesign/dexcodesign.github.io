#!/usr/bin/env python3
"""Derive compact mounting frames from the existing displayed right-hand GLBs."""
import json
import re
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

OUT = Path(__file__).resolve().parents[1] / 'assets/models/studio'
ROOTS = dict(mano='right_palm', wuji_hand_2='r_wrist', sharpa_wave_01='right_hand_C_MC',
             tesollo_dg5f='rl_dg_palm', unitree_dex5_1='base_link00', shadow_hand_e='rh_forearm',
             midas_hand='palm_base', ruka_v2='base_new', inspire_rh56dfx='base',
             robotera_xhand1_pro='right_hand_link', talon9='palm')


def finger(name):
    n = name.lower()
    if re.search(r'thumb|thj|dg_1_|(?:yaw|roll|pitch)_1[1-4]r', n):
        return 'thumb'
    if re.search(r'index|ffj|dg_2_|(?:roll|pitch)_2[1-4]r', n):
        return 'index'
    if re.search(r'middle|(?:^|_)mid_|mfj|dg_3_|(?:roll|pitch)_3[1-4]r', n):
        return 'middle'


def within(scene, node, ancestor):
    while node is not None:
        if node == ancestor:
            return True
        node = scene.graph.transforms.parents.get(node)
    return False


def base_plane_center(scene, root, inverse, correction, alignment):
    """Find the broad planar mounting plate on a known base mesh."""
    groups = {}
    for node in scene.graph.nodes_geometry:
        if scene.graph.transforms.parents[node] != root:
            continue
        transform, name = scene.graph[node]
        geometry = scene.geometry[name]
        vertices = trimesh.transform_points(geometry.vertices, inverse @ transform) @ correction.T @ alignment.T
        mesh = trimesh.Trimesh(vertices, geometry.faces, process=False)
        low, high = mesh.bounds[:, 2]
        for normal, center, area, triangle in zip(mesh.face_normals, mesh.triangles_center, mesh.area_faces, mesh.triangles):
            if abs(normal[2]) < .98 or center[2] > low + .25 * (high - low):
                continue
            normal = normal if normal[2] > 0 else -normal
            key = (*normal.round(3), round(float(np.dot(normal, center)), 4))
            weight, points = groups.get(key, (0, []))
            groups[key] = (weight + area, points + list(triangle))
    assert groups, (root, 'Missing base mounting plane')
    _, points = max(groups.values(), key=lambda value: value[0])
    points = np.asarray(points)
    return (points.min(0) + points.max(0)) / 2


def main():
    records = json.loads((OUT / 'catalog.json').read_text())['records']
    profiles = {}
    for row in records:
        if row['category'] not in ('hand', 'robot', 'ai'):
            continue
        mid = row['id']
        meta = json.loads((OUT / f'{mid}.json').read_text())
        scene = trimesh.load(OUT / f'{mid}.glb', force='scene')
        root = 'link__' + ROOTS.get(mid, 'central_palm')
        assert root in scene.graph.nodes, (mid, root)
        for joint in meta['joints']:
            matrix = np.eye(4)
            matrix[:3, :3] = Rotation.from_quat(joint['quaternion']).as_matrix()
            matrix[:3, 3] = joint['position']
            motion = np.eye(4)
            q = meta['poses']['neutral'].get(joint['name'], 0)
            if joint['type'] == 'prismatic':
                motion[:3, 3] = np.asarray(joint['axis']) * q
            else:
                motion[:3, :3] = Rotation.from_rotvec(np.asarray(joint['axis']) * q).as_matrix()
            parent = scene.graph.transforms.parents[joint['node']]
            scene.graph.update(joint['node'], parent, matrix=matrix @ motion)
        inverse = np.linalg.inv(scene.graph.get(root)[0])
        reflect = bool(meta['category'] == 'ai' and meta.get('display_reflection') and mid != 'talon9')
        correction = np.diag([-1., 1., 1.]) if reflect else np.eye(3)
        landmarks = {key: [] for key in ('thumb', 'index', 'middle')}
        for joint in meta['joints']:
            key = finger(joint['name'])
            if key and within(scene, joint['node'], root):
                point = correction @ (inverse @ scene.graph.get(joint['node'])[0])[:3, 3]
                landmarks[key].append(point)
        points = landmarks['middle'] or landmarks['index']
        assert points and landmarks['thumb'], (mid, 'No mounting landmarks')
        tip = max(points, key=np.linalg.norm)
        distal = np.zeros(3); distal[np.argmax(abs(tip))] = np.sign(tip[np.argmax(abs(tip))])
        thumb = max(landmarks['thumb'], key=lambda p: np.linalg.norm(p - distal * np.dot(p, distal)))
        radial = thumb - distal * np.dot(thumb, distal)
        assert np.linalg.norm(radial) > .005, (mid, 'Degenerate thumb landmark')
        radial_axis = np.zeros(3); radial_axis[np.argmax(abs(radial))] = np.sign(radial[np.argmax(abs(radial))])
        target_distal, target_radial = np.array([0, 0, 1.]), np.array([-1., 0, 0])
        matrix = (np.outer(target_distal, distal) + np.outer(target_radial, radial_axis)
                  + np.outer(np.cross(target_distal, target_radial), np.cross(distal, radial_axis)))
        assert np.isclose(np.linalg.det(matrix), 1)
        bounds = []
        for node in scene.graph.nodes_geometry:
            if not within(scene, node, root):
                continue
            transform, name = scene.graph[node]
            vertices = trimesh.transform_points(scene.geometry[name].vertices, inverse @ transform)
            bounds.append(vertices @ correction.T @ matrix.T)
        vertices = np.concatenate(bounds)
        offset = max(0., -float(vertices[:, 2].min()))
        assert offset < .20, (mid, offset)
        translation = np.array([0., 0., offset])
        mount_center = None
        if mid in {'ruka_v2', 'shadow_hand_e'}:
            mount_center = base_plane_center(scene, root, inverse, correction, matrix)
            translation = -mount_center
        profiles[mid] = dict(root_node=root, quaternion=Rotation.from_matrix(matrix).as_quat().tolist(),
                             source_reflect_x=reflect, offset_z=round(float(translation[2]), 7),
                             translation=translation.round(7).tolist(),
                             mount_plane_center=mount_center.round(7).tolist() if mount_center is not None else None,
                             distal_axis=distal.tolist(), thumb_axis=radial_axis.tolist())
        print(mid, 'distal', distal.tolist(), 'thumb', radial_axis.tolist(), 'wrist translation', translation.round(4).tolist())
    (OUT / 'attachment_profiles.json').write_text(json.dumps(dict(
        schema=1, frame='+Z finger extension; right thumb -X; left is mirrored in canonical X',
        scope='Browser visualization only; mounting frames derived from existing neutral-pose landmarks',
        hands=profiles), separators=(',', ':')) + '\n')


if __name__ == '__main__':
    main()
