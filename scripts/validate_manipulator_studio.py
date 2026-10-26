#!/usr/bin/env python3
"""Check whole-body browser FK against an independent URDF parser."""

import argparse
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
import trimesh
import yourdfpy

from export_manipulator_studio import MODELS, OUT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-root', type=Path, required=True)
    args = parser.parse_args()
    rng = np.random.default_rng(20261026)
    results = []
    for mid, (_, relative, _) in MODELS.items():
        # Some vendor collision proxies use MuJoCo's capsule extension. They
        # do not affect FK and are outside this independent parser's schema.
        xml = ET.parse(args.asset_root / relative)
        for link in xml.getroot().findall('link'):
            for collision in link.findall('collision'):
                link.remove(collision)
        with tempfile.TemporaryDirectory() as temporary:
            source_path = Path(temporary) / 'kinematics.urdf'
            xml.write(source_path, encoding='utf-8', xml_declaration=True)
            source = yourdfpy.URDF.load(source_path, load_meshes=False,
                                        load_collision_meshes=False, build_scene_graph=True)
        metadata = json.loads((OUT / f'{mid}.json').read_text())
        scene = trimesh.load(OUT / f'{mid}.glb', force='scene')
        assert metadata['category'] == 'manipulator'
        assert metadata['side'] == 'whole robot'
        poses = list(metadata['poses'].values())
        for _ in range(2):
            poses.append({c['name']: float(rng.uniform(c['lower'], c['upper'])) for c in metadata['controls']})
        max_error = 0.0
        for pose in poses:
            values = {c['name']: np.float64(pose[c['name']]) for c in metadata['controls']}
            source.update_cfg(values)
            for joint in metadata['joints']:
                matrix = np.eye(4)
                matrix[:3, :3] = Rotation.from_quat(joint['quaternion']).as_matrix()
                matrix[:3, 3] = joint['position']
                motion = np.eye(4)
                value = values[joint['name']]
                if joint['type'] == 'prismatic':
                    motion[:3, 3] = np.asarray(joint['axis']) * value
                else:
                    motion[:3, :3] = Rotation.from_rotvec(np.asarray(joint['axis']) * value).as_matrix()
                parent = scene.graph.transforms.parents[joint['node']]
                scene.graph.update(joint['node'], parent, matrix=matrix @ motion)
            for name in source.link_map:
                actual = scene.graph.get('link__' + name)[0]
                expected = source.get_transform(name)
                max_error = max(max_error, float(np.abs(actual - expected).max()))
        assert max_error < 2e-6, (mid, max_error)
        results.append({'id': mid, 'frames': len(source.link_map), 'poses': len(poses),
                        'controls': len(metadata['controls']), 'max_fk_error': max_error})
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
