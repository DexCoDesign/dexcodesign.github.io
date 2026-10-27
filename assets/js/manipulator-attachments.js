import * as THREE from 'three';

export function findNode(root, name) {
  return root.getObjectByName(name) || root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(name));
}

// All attachments reuse the catalog's original geometry/material buffers.
// Reflection creates the opposite hand; no per-combination GLB is generated.
export function createHandInstance(record, metadata, template, profile, side) {
  const copy = template.clone(true);
  const hand = findNode(copy, profile.root_node);
  if (!hand) throw new Error(`Missing wrist root for ${record.name}`);
  const originalNodes = new Map();
  hand.traverse(node => originalNodes.set(node.name, node));
  const prefix = `${side}_hand/`;
  const holder = new THREE.Group();
  holder.name = `${side}_hand_attachment`;
  holder.scale.x = side === 'left' ? -1 : 1;
  const align = new THREE.Group();
  align.quaternion.fromArray(profile.quaternion);
  align.position.fromArray(profile.translation || [0, 0, profile.offset_z]);
  const correction = new THREE.Group();
  correction.scale.x = profile.source_reflect_x ? -1 : 1;
  holder.add(align); align.add(correction); correction.add(hand);
  hand.position.set(0, 0, 0); hand.quaternion.identity(); hand.scale.set(1, 1, 1);
  hand.traverse(node => { node.name = prefix + node.name; });
  const nodes = new Map(), joints = [];
  for (const source of metadata.joints) {
    const node = originalNodes.get(source.node) || originalNodes.get(THREE.PropertyBinding.sanitizeNodeName(source.node));
    // Root/world motion belongs to the standalone display, not a wrist-mounted hand.
    if (!node || node === hand) continue;
    const joint = {...source, name: prefix + source.name, node: node.name};
    if (source.mimic) joint.mimic = {...source.mimic, source: prefix + source.mimic.source};
    if (record.id === 'kestrel17' && source.name === 'palm_ulnar_cup') {
      joint.visual_mimic = {source: prefix + 'palm_radial_cup', multiplier: .8};
    }
    joints.push(joint); nodes.set(joint.name, node);
  }
  const label = side === 'left' ? 'Left hand' : 'Right hand';
  const controls = metadata.controls.filter(c => nodes.has(prefix + c.name)).map(c => ({
    ...c, name: prefix + c.name, group: `${label} · ${c.group}`,
  }));
  const pose = values => Object.fromEntries(controls.map(c => [c.name,
    values?.[c.name.slice(prefix.length)] ?? 0]));
  const poses = {open: pose(metadata.poses.neutral), close: pose(metadata.poses.wrap || metadata.poses.flex || metadata.poses.neutral)};
  return {id: record.id, side, prefix, group: holder, sourceRoot: hand, profile, joints, nodes, controls, poses,
    loop: metadata.closed_loop_preview ? {prefix, preview: metadata.closed_loop_preview} : null};
}

export function composeAssembly(body, instances) {
  const preview = {...body, joints: [...body.joints], controls: [...body.controls],
    poses: structuredClone(body.poses), motion_pairs: [...(body.motion_pairs || [])],
    hand_poses: {open: {}, close: {}}, attachment_loops: []};
  const hands=[...instances];
  for (const hand of hands) {
    preview.joints.push(...hand.joints); preview.controls.push(...hand.controls);
    for (const [name,values] of Object.entries(preview.poses)) Object.assign(values, hand.poses[name==='fold'?'close':'open']);
    for (const key of ['open', 'close']) Object.assign(preview.hand_poses[key], hand.poses[key]);
    if (hand.loop) preview.attachment_loops.push(hand.loop);
  }
  if(hands.length===2&&hands[0].id===hands[1].id){
    const left=hands.find(h=>h.side==='left'),right=hands.find(h=>h.side==='right');
    for(const c of left.controls){
      const name=c.name.slice(left.prefix.length),opposite=right.prefix+name;
      if(right.nodes.has(opposite))preview.motion_pairs.push({left:c.name,right:opposite,sign:1,offset:0});
    }
  }
  preview.counts = {...body.counts, active: preview.controls.length};
  preview.body_controls = body.controls.length;
  preview.hand_controls = preview.controls.length - body.controls.length;
  return preview;
}
