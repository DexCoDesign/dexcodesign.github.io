#!/usr/bin/env python3
"""Append full-body mobile-manipulator previews without re-exporting hands."""

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from export_hand_studio import OUT, export_one


MODELS = {
    'dexmate_vega': ('Dexmate Vega', 'dexmate_vega/eef_free/robot.urdf',
        {'torso_j1': 1.3666, 'torso_j2': 2.7021, 'torso_j3': 1.2036,
         'L_arm_j1': 1.5707963267948966, 'R_arm_j1': -1.5707963267948966}),
    'rby1': ('Rainbow RB-Y1', 'rby1/eef_free/robot.urdf', {}),
    'galaxea_r1': ('Galaxea R1', 'galaxea_r1/eef_free/robot.urdf',
        {'left_arm_joint1': -1.5707963267948966, 'left_arm_joint3': -3.141592653589793,
         'right_arm_joint1': 1.5707963267948966, 'right_arm_joint3': -3.141592653589793}),
    'dyna_taku': ('DYNA Taku', 'dyna_taku/full/robot.urdf',
        {'right_shoulder_pitch_joint': -0.55, 'right_shoulder_roll_joint': -0.15,
         'right_elbow_joint': -1.35, 'left_shoulder_pitch_joint': -0.25,
         'left_elbow_joint': -0.9, 'folding_low_joint': 0.24}),
}


def group(name):
    low = name.lower()
    if 'wheel' in low or low.startswith('agv_'):
        return 'Mobile base'
    if any(word in low for word in ['head', 'neck']):
        return 'Head'
    if any(word in low for word in ['torso', 'waist', 'folding']):
        return 'Torso'
    if 'gripper' in low:
        return 'Grippers'
    if low.startswith(('l_arm', 'left_')):
        return 'Left arm'
    if low.startswith(('r_arm', 'right_')):
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
        model.update(side='whole robot', root_link=root_link,
                     poses={'neutral': home, 'reach': reach, 'fold': fold},
                     pose_order=['neutral', 'reach', 'fold'],
                     view_direction=[1.4, -2.2, 0.8], limits_are_placeholders=mid == 'dyna_taku',
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
