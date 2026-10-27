import * as THREE from 'three';
import { OrbitControls } from '../vendor/three/OrbitControls.js';
import { GLTFLoader } from '../vendor/three/GLTFLoader.js';
import {createHandInstance, composeAssembly, findNode} from './manipulator-attachments.js?v=62';
import {createMotionPlan, sampleMotion} from './joint-motion.js?v=62';

const $ = id => document.getElementById('studio-' + id);
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const basicPoses = ['neutral','spread','wrap','pinch'];
const studioVersion = '66';
const posterVersion = '66';
const visualPassiveResponse = {
  // The KESTREL ulnar arch is a free passive joint (0–26 degrees), so the
  // original renderer held it at zero. Show a bounded response to radial
  // cupping in this kinematic preview without changing the source asset.
  kestrel17: {palm_ulnar_cup:{source:'palm_radial_cup',multiplier:.8}},
};
let model, root, joints = new Map(), sliders = new Map(), current = {}, target = {}, catalog = [], generation = 0;
const metadataCache = new Map(), sceneCache = new Map();
let bodyModel = null, bodyJointNodes = new Map(), attachmentProfiles = null;
const mountedHands = new Map();
let handGeneration=0, selectedEEF='lyra10';
let bodyLoading=true, handLoading=false;
let slow = false, selectedPose = 'neutral', clockStart = 0, dirty = true, visible = true;
let slowStart = {}, slowPlan = [], previousFrameTime=0;
const viewShift = new THREE.Vector2();
const viewport = $('viewport');
const renderer = new THREE.WebGLRenderer({antialias:true,alpha:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.setClearColor(0,0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
// Keep highlights from clipping while preserving the authored material hue.
renderer.toneMapping = THREE.NeutralToneMapping;
renderer.toneMappingExposure = 1.25;
viewport.append(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35,1,.001,10);
camera.up.set(0,0,1);
class StudioOrbitControls extends OrbitControls {
  update(deltaTime=null){
    this._quat.setFromUnitVectors(this.object.up,new THREE.Vector3(0,1,0));
    this._quatInverse.copy(this._quat).invert();
    return super.update(deltaTime);
  }
  _rotateUp(angle){
    // Keep OrbitControls' original drag mapping, carrying the camera's up
    // direction through each pitch so rotating over either pole stays smooth.
    const eye=this.object.position.clone().sub(this.target);
    const right=new THREE.Vector3().crossVectors(this.object.up,eye).normalize();
    const rotation=new THREE.Quaternion().setFromAxisAngle(right,-angle);
    this.object.position.copy(this.target).add(eye.applyQuaternion(rotation));
    this.object.up.applyQuaternion(rotation).normalize();
  }
}
const orbit = new StudioOrbitControls(camera,renderer.domElement);
orbit.enableDamping = false;
orbit.enablePan = false;
orbit.rotateSpeed = .6;
orbit.zoomSpeed = .75;
orbit.addEventListener('change',()=>{dirty=true;});
// Neutral, symmetric fill: rotating a model never reveals an unlit side.
scene.add(new THREE.AmbientLight(0xffffff,.65));
for (const pos of [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]]) {
  const light=new THREE.DirectionalLight(0xffffff,.18);light.position.set(...pos);scene.add(light);
}
const palmView = {
  wuji_hand_2:[-.42,-1,.28], sharpa_wave_01:[1,.35,.28], tesollo_dg5f:[1,.35,.28],
  unitree_dex5_1:[-.42,-1,.28], shadow_hand_e:[-.42,-1,.28], midas_hand:[-.42,-1,.28],
  ruka_v2:[-.42,-1,.28], inspire_rh56dfx:[-.42,-1,.28], robotera_xhand1_pro:[-.42,-1,.28],
  supr_female_foot:[-.42,-1,.28],
};
const palmLink = {
  talon9:'palm', mano:'right_palm', wuji_hand_2:'r_wrist',
  sharpa_wave_01:'right_hand_C_MC', tesollo_dg5f:'rl_dg_palm',
  unitree_dex5_1:'base_link00', shadow_hand_e:'rh_palm', midas_hand:'palm_base',
  ruka_v2:'base_new', inspire_rh56dfx:'base', robotera_xhand1_pro:'right_hand_link',
  supr_female_foot:'foot_base',
};
function rotationCenter(next){
  if(next.category==='manipulator')return new THREE.Box3().setFromObject(root).getCenter(new THREE.Vector3());
  const base=root.getObjectByName('link__'+(palmLink[next.id]||'central_palm'));
  if(!base)throw new Error('Model palm base is missing');
  // Use only the base's own visual meshes: the articulated thumb and fingers
  // must not shift the rotation center away from the palm.
  const bounds=new THREE.Box3();
  for(const child of base.children)if(child.name.startsWith('visual__'))bounds.expandByObject(child);
  return bounds.isEmpty()?base.getWorldPosition(new THREE.Vector3()):bounds.getCenter(new THREE.Vector3());
}
function frameView(bounds,center,direction,radius){
  camera.clearViewOffset();
  let distance=radius*2.15;
  const projected=new THREE.Box2();
  for(let attempt=0;attempt<4;attempt++){
    camera.position.copy(center).addScaledVector(direction,distance);orbit.update();camera.updateMatrixWorld(true);projected.makeEmpty();
    for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){
      const point=new THREE.Vector3(x,y,z).project(camera);projected.expandByPoint(new THREE.Vector2(point.x,point.y));
    }
    const span=projected.getSize(new THREE.Vector2()),scale=Math.max(span.x,span.y)/1.8;
    if(scale<=1||attempt===3)break;
    distance*=scale*1.05;
  }
  // Lens shift centers the initial model while the physical palm base remains
  // the fixed rotation pivot, independent of finger reach and thumb position.
  projected.getCenter(viewShift);viewShift.multiply(new THREE.Vector2(.5,-.5));
  resizeView();
}
function resizeView(){
  const {width,height}=viewport.getBoundingClientRect();
  camera.aspect=width/height;camera.setViewOffset(width,height,viewShift.x*width,viewShift.y*height,width,height);camera.updateProjectionMatrix();
}
// Display-only: raise the toes (+X -> +Z) and face the sole (-Z -> -Y),
// matching the palm-facing initial view without changing the source asset.
const footDisplayRotation = new THREE.Quaternion().setFromAxisAngle(
  new THREE.Vector3(1,1,1).normalize(), -2*Math.PI/3);
const loader = new GLTFLoader();
// All models share the same lamps. Material-specific reflection distinguishes
// metallic housings from plastic; there are no model-specific lighting hacks.
function displayMaterial(material){
  if(!material?.isMeshStandardMaterial)return material;
  const metal=material.metalness>=.45;
  const matte=!metal&&material.roughness>=.7;
  const printed=!metal&&material.roughness>=.65&&!matte;
  return new THREE.MeshPhongMaterial({
    name:material.name,
    color:material.color,
    map:material.map,
    transparent:material.transparent,
    opacity:material.opacity,
    side:material.side,
    vertexColors:material.vertexColors,
    specular:new THREE.Color(metal?0x9ca8b2:matte?0x1e1e1e:printed?0x303030:0x383838),
    shininess:metal?84:matte?14:printed?20:28,
  });
}
const axisQ = new THREE.Quaternion();
new ResizeObserver(()=>{const {width,height}=viewport.getBoundingClientRect();renderer.setSize(width,height);resizeView();dirty=true;}).observe(viewport);
new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;dirty=true;}).observe(viewport);

function loading(percent,text='Loading model'){
  const value=clamp(Math.floor(percent),0,100);
  $('progress').value=value;$('loading-text').textContent=`${text} · ${value}%`;
}
function syncLoadingState(){
  const busy=bodyLoading||handLoading;
  viewport.dataset.loading=String(busy);viewport.tabIndex=busy?-1:0;
  viewport.closest('.studio').setAttribute('aria-busy',String(busy));
  $('loading').hidden=!busy;orbit.enabled=!busy;$('eef').disabled=busy;
  $('controls').inert=busy;$('actions').inert=busy;
  for(const [name,{input}] of sliders)input.disabled=busy||loopDependent(name);
  for(const button of $('actions').querySelectorAll('button'))button.disabled=busy;
  if(!busy)$('poster').hidden=true;
}
async function paintLoadingState(){
  // Cached scenes can still spend a frame cloning/uploading meshes. Paint the
  // loading UI before doing that work, including when no network request occurs.
  if(document.hidden)return;
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
}
async function getMetadata(record){
  if(!metadataCache.has(record.id))metadataCache.set(record.id,fetch(`${record.metadata}?v=${studioVersion}`).then(r=>{if(!r.ok)throw new Error('Model metadata unavailable');return r.json();}).catch(e=>{metadataCache.delete(record.id);throw e;}));
  return metadataCache.get(record.id);
}
async function getScene(next,token,onProgress=percent=>loading(percent)){
  if(!sceneCache.has(next.id))sceneCache.set(next.id,loader.loadAsync(`${next.glb}?v=${studioVersion}`,e=>{
    if(token===generation&&e.total)onProgress(Math.min(99,100*e.loaded/e.total));
  }).then(gltf=>{
    const converted=new Map();
    gltf.scene.traverse(node=>{
      if(!node.isMesh)return;
      const convert=material=>{
        if(!converted.has(material)){
          const shown=displayMaterial(material);
          if(next.id==='mano')shown.color.set('#d6a88e');
          converted.set(material,shown);
        }
        return converted.get(material);
      };
      node.material=Array.isArray(node.material)?node.material.map(convert):convert(node.material);
    });
    return gltf.scene;
  }).catch(e=>{sceneCache.delete(next.id);throw e;}));
  return sceneCache.get(next.id);
}
function values(pose){return Object.fromEntries(model.controls.map(c=>[c.name,clamp(pose[c.name]??0,c.lower,c.upper)]));}
function fingerOf(control){
  const n=control.name.toLowerCase(), g=control.group.toLowerCase(), s=n+' '+g;
  if(/thumb|thj|dg_1_|(?:yaw|roll|pitch)_1[1-4]r/.test(s))return 'thumb';
  if(/index|ffj|dg_2_|(?:roll|pitch)_2[1-4]r/.test(s))return 'index';
  if(/middle|(?:^|_)mid_|\bmid|mfj|dg_3_|(?:roll|pitch)_3[1-4]r/.test(s))return 'middle';
  if(/ring|rfj|dg_4_|(?:roll|pitch)_4[1-4]r/.test(s))return 'ring';
  if(/little|pinky|lfj|dg_5_|(?:roll|pitch)_5[1-4]r/.test(s))return 'little';
  return null;
}
function isSpread(control){
  const n=control.name.toLowerCase();
  return /abd|splay|spread|abad|_aa|yaw|1y$|thumb1z$|mcp0|(?:^|_)roll_[2-5]1r|dg_[2-5]_1$|(?:ff|mf|rf|lf)j4$/.test(n);
}
function movement(control,fraction,sign=1){
  const extreme=sign<0&&control.lower<0?control.lower:control.upper>0?control.upper:control.lower;
  return clamp(extreme*fraction,control.lower,control.upper);
}
function addBasicPoses(next){
  if(next.category==='others'||next.category==='manipulator')return;
  const neutral=Object.fromEntries(next.controls.map(c=>[c.name,clamp(next.poses.neutral?.[c.name]??0,c.lower,c.upper)]));
  if(next.category==='robot'){
    // Robot axes and flexion signs vary. Only use presets derived from this
    // model's kinematic chain; the old name/limit heuristic closed Spread.
    for(const name of basicPoses)if(!next.poses[name])throw new Error(`Missing verified ${name} preset for ${next.name}`);
    return;
  }
  const spread={...neutral},wrap={...neutral},pinch={...neutral};
  for(const c of next.controls){
    const finger=fingerOf(c),n=c.name.toLowerCase();
    if(!finger||/wrist|base_|linkage/.test(n))continue;
    if(isSpread(c)){
      const sign={thumb:1,index:1,middle:1,ring:-1,little:-1}[finger];
      spread[c.name]=movement(c,finger==='middle'?.12:.55,sign);
      if(finger==='thumb')pinch[c.name]=movement(c,.4);
    }else{
      wrap[c.name]=movement(c,finger==='thumb'?.5:.66);
      pinch[c.name]=movement(c,finger==='thumb'?.53:finger==='index'?.58:.06);
    }
  }
  for(const [name,pose] of Object.entries({neutral,spread,wrap,pinch}))next.poses[name]??=pose;
}
function pose(name){slow=false;selectedPose=name;target=values(model.poses[name]);buttons();$('status').textContent=model.category==='manipulator'?model.preview_note:name==='pinch'?(model.pinch_note||'Pinch preset · kinematic configuration, not a validated grasp.'):'Joint limits enforced · dependent joints follow their masters.';dirty=true;}
function buttons(){for(const b of $('actions').querySelectorAll('button'))b.classList.toggle('on',Boolean(b.dataset.pose===selectedPose&&!slow||b.dataset.slow&&slow));}
function loopDependent(name){
  const loops=[...(model?.closed_loop_preview?[{prefix:'',preview:model.closed_loop_preview}]:[]),...(model?.attachment_loops||[])];
  return loops.some(({prefix})=>name.startsWith(prefix)&&/(?:index|middle|ring)_dip(?:_linkage)?_joint$/.test(name.slice(prefix.length)));
}
function closeMidasLoops(q){
  const loops=[...(model.closed_loop_preview?[{prefix:'',preview:model.closed_loop_preview}]:[]),...(model.attachment_loops||[])];
  for(const {prefix,preview} of loops)for(const [finger,samples] of Object.entries(preview.fingers)){
    const pip=clamp(q[`${prefix}${finger}_pip_joint`]??0,samples.at(-1)[0],samples[0][0]);
    let i=1;while(i<samples.length-1&&samples[i][0]>pip)i++;
    const a=samples[i-1],b=samples[i],t=(pip-a[0])/(b[0]-a[0]);
    q[`${prefix}${finger}_dip_joint`]=a[1]+t*(b[1]-a[1]);
    q[`${prefix}${finger}_dip_linkage_joint`]=a[2]+t*(b[2]-a[2]);
  }
}
function apply(q){
  const resolved={...q}, resolving=new Set();closeMidasLoops(resolved);
  function resolve(j){
    if(resolved[j.name]!==undefined)return resolved[j.name];
    if(resolving.has(j.name))throw new Error('Cyclic mimic joint');
    resolving.add(j.name);
    const src=j.mimic?model.joints.find(x=>x.name===j.mimic.source):null;
    const preview=j.visual_mimic||visualPassiveResponse[model.id]?.[j.name];
    // Passive joints are not actuators. This is an explicitly visual response
    // to a neighboring active joint, not a source-URDF mimic or force model.
    const v=src?resolve(src)*j.mimic.multiplier+j.mimic.offset:
      preview?(q[preview.source]??0)*preview.multiplier+(preview.offset??0):0;
    resolving.delete(j.name);return resolved[j.name]=clamp(v,j.lower,j.upper);
  }
  for(const j of model.joints){const node=joints.get(j.name);if(!node)continue;const qj=resolve(j);node.position.fromArray(j.position);node.quaternion.fromArray(j.quaternion);if(j.type==='prismatic'){node.position.add(new THREE.Vector3().fromArray(j.axis).applyQuaternion(node.quaternion).multiplyScalar(qj));}else{axisQ.setFromAxisAngle(new THREE.Vector3().fromArray(j.axis),qj);node.quaternion.multiply(axisQ);}}
  for(const c of model.controls){const {input,output}=sliders.get(c.name);const value=c.unit==='m'?resolved[c.name]*1000:THREE.MathUtils.radToDeg(resolved[c.name]);input.value=value;output.value=value.toFixed(1)+(c.unit==='m'?' mm':'°');}
}
function buildControls(){
  $('controls').replaceChildren();sliders.clear();const groups=new Map();
  for(const [i,c] of model.controls.entries()){
    if(!groups.has(c.group)){const section=document.createElement('section');section.className='studio-group';const heading=document.createElement('h3');heading.textContent=c.group;section.append(heading);$('controls').append(section);groups.set(c.group,section);}
    const row=document.createElement('div');row.className='studio-joint';const label=document.createElement('label'),span=document.createElement('span'),output=document.createElement('output'),input=document.createElement('input');
    input.id='studio-joint-'+i;label.htmlFor=input.id;span.textContent=c.label;label.append(span,output);input.type='range';const scale=c.unit==='m'?1000:180/Math.PI;input.min=c.lower*scale;input.max=c.upper*scale;input.step=c.unit==='m'?.1:.5;input.setAttribute('aria-label',c.group+' '+c.label);
    if(loopDependent(c.name)){input.disabled=true;input.title='Follows the PIP joint through the original MIDAS fingertip linkage';}
    input.addEventListener('input',()=>{slow=false;selectedPose='';target={...current,[c.name]:Number(input.value)/scale};current={...target};apply(current);buttons();dirty=true;});
    row.append(label,input);groups.get(c.group).append(row);sliders.set(c.name,{input,output});
  }
  $('actions').replaceChildren();
  for(const name of (model.pose_order||(model.category==='others'?['neutral','flex']:basicPoses))){const b=document.createElement('button');b.textContent=model.category==='manipulator'&&name==='neutral'?'Home':name[0].toUpperCase()+name.slice(1);b.dataset.pose=name;b.onclick=()=>pose(name);$('actions').append(b);}
  if(model.category==='manipulator'&&model.hand_controls){
    for(const [name,text] of [['open','Open hands'],['close','Close hands']]){
      const button=document.createElement('button');button.textContent=text;button.dataset.handPose=name;
      button.onclick=()=>{slow=false;selectedPose='';target={...current,...model.hand_poses[name]};buttons();dirty=true;};$('actions').append(button);
    }
  }
  const b=document.createElement('button');b.textContent='Slow motion';b.className='slow';b.dataset.slow='true';b.onclick=()=>{
    if(!slow){
      slowStart={...current};slowPlan=createMotionPlan(model,slowStart,loopDependent);
      $('status').textContent=model.category==='manipulator'?'All movable joints · paired arms and hands move symmetrically.':'Every independent joint moves; coupled and passive joints follow their source relationships.';
    }else target={...current};
    slow=!slow;clockStart=performance.now();buttons();dirty=true;
  };$('actions').append(b);
  syncLoadingState();
}
function showReviewLegend(){
  const legend=$('review-legend');legend.replaceChildren();
  if(!model.review_palette){legend.hidden=true;return;}
  legend.hidden=false;
  const heading=document.createElement('div');heading.className='studio-review-heading';heading.textContent='Temporary color key · existing black parts stay black';legend.append(heading);
  for(const part of model.review_palette.parts){
    const item=document.createElement('div');item.className='studio-review-item';item.title=part.link;
    const swatch=document.createElement('span');swatch.className='studio-review-swatch';swatch.style.backgroundColor=part.color;
    const label=document.createElement('span');label.textContent=part.label;item.append(swatch,label);legend.append(item);
  }
}
function countText(next){
  if(next.category==='manipulator')return next.hand_controls?`${next.body_controls} body joints · ${next.hand_controls} hand joints`:`${next.counts.active} joint controls · whole robot`;
  return next.closed_loop_preview?
    `${next.counts.active} URDF joints · 6 source-loop joints follow PIP in this preview`:
    `${next.counts.active} active · ${next.counts.coupled} coupled · ${next.counts.passive} passive`;
}
async function choose(id){
  const token=++generation;handGeneration++;bodyLoading=true;handLoading=false;mountedHands.clear();bodyModel=null;bodyJointNodes.clear();$('mounts').hidden=true;slow=false;syncLoadingState();loading(0);$('controls').replaceChildren();$('actions').replaceChildren();$('review-legend').hidden=true;
  try{
    const record=catalog.find(r=>r.id===id);if(!record)throw new Error('Model is not in this collection');
    $('name').textContent=record.name;$('counts').textContent=`${record.counts.active} active · ${record.counts.coupled} coupled · ${record.counts.passive} passive`;
    $('poster').src=`assets/images/studio/posters/${id}.jpg?v=${posterVersion}`;$('poster').hidden=false;
    $('poster').onerror=()=>{if(token===generation)$('poster').hidden=true;};
    const next=await getMetadata(record);
    if(token!==generation)return;
    const template=await getScene(next,token);
    if(token!==generation)return;
    if(root)scene.remove(root);root=template.clone(true);
    if(next.id==='supr_female_foot')root.quaternion.premultiply(footDisplayRotation);
    // Legacy AI exports were reflected although those sources were already
    // right-sided; TALON-9 is the opposite and needs its export reflection.
    if(next.category==='ai'&&next.display_reflection&&next.id!=='talon9')root.scale.x=-1;
    root.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;}});addBasicPoses(next);model=next;scene.add(root);joints.clear();
    for(const j of model.joints){const n=root.getObjectByName(j.node)||root.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(j.node));if(!n)throw new Error('Missing joint node: '+j.node);joints.set(j.name,n);}
    if(model.category==='manipulator'){bodyModel=model;bodyJointNodes=new Map(joints);configureEEFSelector();}
    $('name').textContent=record.name;$('counts').textContent=countText(model);
    buildControls();showReviewLegend();current=values(model.poses.neutral||{});target={...current};apply(current);root.updateMatrixWorld(true);
    const box=new THREE.Box3().setFromObject(root),center=rotationCenter(model),size=box.getSize(new THREE.Vector3());
    const radius=Math.max(size.x,size.y,size.z),direction=new THREE.Vector3(...(palmView[model.id]||model.view_direction||[.42,1,.28])).normalize();camera.up.set(0,0,1);
    camera.near=Math.max(radius/1000,.0001);camera.far=radius*100;camera.updateProjectionMatrix();
    orbit.target.copy(center);orbit.minDistance=radius*.9;orbit.maxDistance=radius*8;frameView(box,center,direction,radius);
    selectedPose='neutral';buttons();$('status').textContent=model.category==='manipulator'?model.preview_note:model.closed_loop_preview?'MIDAS preview: fingertip linkages follow original four-bar closure; training URDF is unchanged.':model.category==='ai'?(model.concept_note||'Hand-only concept · direct-drive actuators · closed motor enclosures.'):'Skynet asset snapshot · visual meshes with original joint kinematics.';
    if(model.category==='manipulator'&&selectedEEF!=='none'){await chooseEEF();if(token!==generation)return;}
    loading(100);renderer.render(scene,camera);dirty=false;bodyLoading=false;syncLoadingState();
  }catch(error){if(token===generation){$('loading').hidden=false;$('loading-text').textContent='Model could not load · '+error.message;console.error(error);}}
}
function configureEEFSelector(){
  $('mounts').hidden=false;
  const select=$('eef');select.replaceChildren(new Option('None (bare wrists)','none'));
  for(const [category,label] of [['hand','Human'],['robot','Robot hands'],['ai','AI gen']]){
    const group=document.createElement('optgroup');group.label=label;
    for(const record of catalog.filter(row=>row.category===category))group.append(new Option(record.name,record.id));
    select.append(group);
  }
  select.value=[...select.options].some(option=>option.value===selectedEEF)?selectedEEF:'none';selectedEEF=select.value;syncLoadingState();
}
function rebuildAttachedPreview(initial={}){
  const previous={...current,...initial};model=composeAssembly(bodyModel,mountedHands.values());joints=new Map(bodyJointNodes);
  for(const hand of mountedHands.values())for(const [name,node] of hand.nodes)joints.set(name,node);
  slow=false;buildControls();current=values(previous);target={...current};apply(current);buttons();
  $('counts').textContent=countText(model);$('status').textContent=mountedHands.size?'Optional hands attached · move the arm or finger joints to explore.':bodyModel.preview_note;dirty=true;
}
async function chooseEEF(){
  selectedEEF=$('eef').value;
  if(!bodyModel)return;
  const id=selectedEEF,bodyToken=generation,token=++handGeneration;
  handLoading=true;slow=false;target={...current};buttons();syncLoadingState();
  $('poster').hidden=false;loading(0,'Loading end effector');$('status').textContent='Loading end effector…';
  try{
    await paintLoadingState();
    if(generation!==bodyToken||token!==handGeneration)return;
    if(id==='none'){
      for(const hand of mountedHands.values())hand.group.removeFromParent();mountedHands.clear();rebuildAttachedPreview();
    }else{
      if(!attachmentProfiles)attachmentProfiles=fetch(`assets/models/studio/attachment_profiles.json?v=${studioVersion}`).then(r=>{if(!r.ok)throw new Error('Hand mounting profiles unavailable');return r.json();}).catch(error=>{attachmentProfiles=null;throw error;});
      const record=catalog.find(row=>row.id===id),profiles=await attachmentProfiles;
      if(generation!==bodyToken||token!==handGeneration)return;
      const metadata=structuredClone(await getMetadata(record));addBasicPoses(metadata);
      if(generation!==bodyToken||token!==handGeneration)return;
      const template=await getScene(metadata,bodyToken,percent=>{if(token===handGeneration)loading(percent,'Loading end effector');});
      if(generation!==bodyToken||token!==handGeneration)return;
      const additions=['left','right'].map(side=>{
        const anchor=findNode(root,bodyModel.hand_mounts[side]);if(!anchor)throw new Error(`Missing ${side} wrist mount`);
        return {anchor,instance:createHandInstance(record,metadata,template,profiles.hands[id],side)};
      });
      for(const old of mountedHands.values())old.group.removeFromParent();mountedHands.clear();
      const initial={};for(const {anchor,instance} of additions){anchor.add(instance.group);mountedHands.set(instance.side,instance);Object.assign(initial,instance.poses[selectedPose==='fold'?'close':'open']);}
      rebuildAttachedPreview(initial);
    }
    loading(100,'Loading end effector');renderer.render(scene,camera);dirty=false;
  }catch(error){
    if(generation!==bodyToken||token!==handGeneration)return;
    selectedEEF=[...mountedHands.values()][0]?.id||'none';$('eef').value=selectedEEF;$('status').textContent=`End effector could not attach · ${error.message}`;console.error(error);
  }finally{
    if(generation===bodyToken&&token===handGeneration){handLoading=false;syncLoadingState();}
  }
}
$('eef').onchange=chooseEEF;

function category(preferredId){const records=catalog.filter(r=>r.category===$('category').value);$('model').replaceChildren();for(const r of records){const o=document.createElement('option');o.value=r.id;o.textContent=r.name;$('model').append(o);}if(records.length){const record=records.find(r=>r.id===preferredId)||records[0];$('model').value=record.id;choose(record.id);}else{$('loading').hidden=false;$('loading-text').textContent='No models published in this collection yet.';}}
$('category').onchange=()=>category();$('model').onchange=()=>choose($('model').value);
function tick(now){requestAnimationFrame(tick);const dt=previousFrameTime?Math.min((now-previousFrameTime)/1000,.25):1/60;previousFrameTime=now;if(!visible||document.hidden||!model||bodyLoading||handLoading)return;const poseBlend=1-Math.exp(-12*dt);let moving=false;
  if(slow){current=sampleMotion(slowPlan,slowStart,now-clockStart);moving=true;}
  else{for(const c of model.controls){const delta=target[c.name]-current[c.name];if(Math.abs(delta)>1e-5){current[c.name]+=delta*poseBlend;moving=true;}else current[c.name]=target[c.name];}}
  if(moving){apply(current);dirty=true;}if(dirty){renderer.render(scene,camera);dirty=false;}
}
requestAnimationFrame(tick);
fetch(`assets/models/studio/catalog.json?v=${studioVersion}`).then(r=>{if(!r.ok)throw new Error('Catalog unavailable');return r.json();}).then(data=>{catalog=data.records;const params=new URLSearchParams(location.search),requested=catalog.find(r=>r.id===params.get('model')),collection=requested?.category||params.get('collection')||'manipulator';if([...$('category').options].some(o=>o.value===collection))$('category').value=collection;category(requested?.id||($('category').value==='manipulator'?'dexmate_vega':undefined));}).catch(e=>{$('loading-text').textContent=e.message;});
