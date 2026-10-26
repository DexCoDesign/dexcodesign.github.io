#!/usr/bin/env python3
"""Append full-body mobile-manipulator previews without re-exporting hands."""

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from export_hand_studio import OUT, export_one


MODELS = {
    'dexmate_vega': ('Dexmate Vega', 'dexmate_vega/body/robot.urdf',
        {'torso_j1': 1.3666, 'torso_j2': 2.7021, 'torso_j3': 1.2036,
         'L_arm_j1': 1.5707963267948966, 'R_arm_j1': -1.5707963267948966}),
    'rby1': ('Rainbow RB-Y1', 'rby1/body/robot.urdf', {}),
    'galaxea_r1': ('Galaxea R1', 'galaxea_r1/body/robot.urdf',
        {'left_arm_joint1': -1.5707963267948966, 'left_arm_joint3': -3.141592653589793,
         'right_arm_joint1': 1.5707963267948966, 'right_arm_joint3': -3.141592653589793}),
    'gento_luna': ('Gento Luna', 'gento_luna/body/robot.urdf',
        {'Arm_L1_Joint': -1.5707963267948966, 'Arm_L2_Joint': 1.5707963267948966,
         'Arm_L3_Joint': 1.5707963267948966, 'Arm_R1_Joint': -1.5707963267948966,
         'Arm_R2_Joint': -1.5707963267948966, 'Arm_R3_Joint': 1.5707963267948966}),
    'dyna_taku': ('DYNA Taku', 'dyna_taku/body/robot.urdf',
        {'folding_low_joint': -0.815, 'folding_high_joint': 1.915, 'waist_pitch_joint': -1.1}),
}


def group(name):
    low = name.lower()
    if 'wheel' in low or low.startswith('agv_'):
        return 'Mobile base'
    if any(word in low for word in ['head', 'neck']):
        return 'Head'
    if any(word in low for word in ['torso', 'waist', 'folding', 'gento luna_leg']):
        return 'Torso'
    if 'gripper' in low:
        return 'Grippers'
    if low.startswith(('l_arm', 'left_', 'arm_l')):
        return 'Left arm'
    if low.startswith(('r_arm', 'right_', 'arm_r')):
        return 'Right arm'
    return 'Joints'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-root', type=Path, required=True,
                        help='DexCoDesign assets/mobile_manipulators directory')
    args = parser.parse_args()
    catalog_path = OUT / 'catalog.json'
    original = json.loads(catalog_path.read_text())
    original['records'] = [row for row in original['records'] if row['category'] != 'manipulator']
    records = []
    for mid, (name, relative, home_values) in MODELS.items():
        urdf = args.asset_root / relative
        row = export_one(urdf, mid, name, 'manipulator', provenance={
            'host': 'DexCoDesign mobile-manipulator library',
            'path': 'assets/mobile_manipulators/' + relative,
            'description': 'Public-web reconstruction' if mid == 'dyna_taku' else 'Versioned vendor-derived end-effector-free description',
        })
        meta_path = OUT / f'{mid}.json'
        model = json.loads(meta_path.read_text())
        source = ET.parse(urdf).getroot()
        children = {j.find('child').get('link') for j in source.findall('joint')}
        root_link = next(link.get('name') for link in source.findall('link') if link.get('name') not in children)
        for control in model['controls']:
            control['group'] = group(control['name'])
            if mid == 'dexmate_vega' and control['group'] in ('Left arm', 'Right arm'):
                control['group'] = 'Right arm' if control['group'] == 'Left arm' else 'Left arm'
        home = {c['name']: max(c['lower'], min(c['upper'], home_values.get(c['name'], 0)))
                for c in model['controls']}
        reach, fold = dict(home), dict(home)
        for part in ['Left arm', 'Right arm', 'Torso']:
            selected = [c for c in model['controls'] if c['group'] == part]
            for control in selected[:2]:
                source = home[control['name']]
                direction = 1 if control['upper'] - source >= source - control['lower'] else -1
                step = min(0.35, 0.12 * (control['upper'] - control['lower']))
                destination = max(control['lower'], min(control['upper'], source + direction * step))
                (fold if part == 'Torso' else reach)[control['name']] = destination
        manifest = json.loads((urdf.parent / 'manifest.json').read_text())
        model.update(end_effectors_removed=True, color_basis=manifest['color_basis'], side='whole robot', root_link=root_link,
                     poses={'neutral': home, 'reach': reach, 'fold': fold},
                     pose_order=['neutral', 'reach', 'fold'],
                     view_direction=([-3, 1.4, 0.65] if mid == 'dexmate_vega' else [3, -1.4, 0.65]), limits_are_placeholders=mid == 'dyna_taku',
                     preview_note=('Whole-body joint preview. Taku ranges are display placeholders.' if mid == 'dyna_taku'
                                   else 'Whole-body joint preview. Use the sliders to explore the base, torso and arms.'))
        meta_path.write_text(json.dumps(model, separators=(',', ':')) + '\n')
        records.append({**row, 'side': 'whole robot'})
    index = next((i for i, row in enumerate(original['records']) if row['category'] == 'others'), len(original['records']))
    original['records'][index:index] = records
    catalog_path.write_text(json.dumps(original, indent=2) + '\n')
    print(json.dumps({'added_manipulators': list(MODELS), 'catalog_count': len(original['records'])}))


if __name__ == '__main__':
    main()
