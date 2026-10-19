import * as THREE from 'three';
import { OrbitControls } from '../vendor/three/OrbitControls.js';
import { GLTFLoader } from '../vendor/three/GLTFLoader.js';

const $ = id => document.getElementById('studio-' + id);
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const basicPoses = ['neutral','spread','wrap','pinch'];
const studioVersion = '7';
let model, root, joints = new Map(), sliders = new Map(), current = {}, target = {}, catalog = [], generation = 0;
let slow = false, selectedPose = 'neutral', clockStart = 0, dirty = true, visible = true;
const viewport = $('viewport');
const renderer = new THREE.WebGLRenderer({antialias:true,alpha:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
renderer.setClearColor(0,0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
// Keep authored material colors legible: a uniform neutral fill, no filmic
// shoulder that turns pale metals and skin into the same gray-white value.
renderer.toneMapping = THREE.NoToneMapping;
viewport.append(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35,1,.001,10);
camera.up.set(0,0,1);
const orbit = new OrbitControls(camera,renderer.domElement);
orbit.enableDamping = false;
orbit.enablePan = false;
orbit.rotateSpeed = .7;
orbit.zoomSpeed = .75;
orbit.minPolarAngle = .08; orbit.maxPolarAngle = Math.PI-.08;
orbit.addEventListener('change',()=>{dirty=true;});
// Neutral, symmetric fill: rotating a model never reveals an unlit side.
scene.add(new THREE.AmbientLight(0xffffff,.78));
for (const pos of [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]]) {
  const light=new THREE.DirectionalLight(0xffffff,.12);light.position.set(...pos);scene.add(light);
}
const palmView = {
  wuji_hand_2:[-.42,-1,.28], sharpa_wave_01:[1,.35,.28], tesollo_dg5f:[1,.35,.28],
  unitree_dex5_1:[-.42,-1,.28], shadow_hand_e:[-.42,-1,.28], midas_hand:[-.42,-1,.28],
  ruka_v2:[-.42,-1,.28], inspire_rh56dfx:[-.42,-1,.28], robotera_xhand1_pro:[-.42,-1,.28],
};
const loader = new GLTFLoader();
const axisQ = new THREE.Quaternion();
new ResizeObserver(()=>{const {width,height}=viewport.getBoundingClientRect();renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();dirty=true;}).observe(viewport);
new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;dirty=true;}).observe(viewport);

function dispose(object){object.traverse(o=>{o.geometry?.dispose();for(const m of (Array.isArray(o.material)?o.material:[o.material]))m?.dispose();});}
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
  if(next.category==='others')return;
  const neutral=Object.fromEntries(next.controls.map(c=>[c.name,clamp(next.poses.neutral?.[c.name]??0,c.lower,c.upper)]));
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
function pose(name){slow=false;selectedPose=name;target=values(model.poses[name]);buttons();$('status').textContent=name==='pinch'?(model.pinch_note||'Pinch preset · kinematic configuration, not a validated grasp.'):'Joint limits enforced · dependent joints follow their masters.';dirty=true;}
function buttons(){for(const b of $('actions').querySelectorAll('button'))b.classList.toggle('on',Boolean(b.dataset.pose===selectedPose&&!slow||b.dataset.slow&&slow));}
function apply(q){
  const resolved={...q}, resolving=new Set();
  function resolve(j){
    if(resolved[j.name]!==undefined)return resolved[j.name];
    if(resolving.has(j.name))throw new Error('Cyclic mimic joint');
    resolving.add(j.name);
    const src=j.mimic?model.joints.find(x=>x.name===j.mimic.source):null;
    const v=src?resolve(src)*j.mimic.multiplier+j.mimic.offset:0;
    resolving.delete(j.name);return resolved[j.name]=clamp(v,j.lower,j.upper);
  }
  for(const j of model.joints){const node=joints.get(j.name);if(!node)continue;const qj=resolve(j);node.position.fromArray(j.position);node.quaternion.fromArray(j.quaternion);if(j.type==='prismatic'){node.position.add(new THREE.Vector3().fromArray(j.axis).applyQuaternion(node.quaternion).multiplyScalar(qj));}else{axisQ.setFromAxisAngle(new THREE.Vector3().fromArray(j.axis),qj);node.quaternion.multiply(axisQ);}}
  for(const c of model.controls){const {input,output}=sliders.get(c.name);const value=c.unit==='m'?q[c.name]*1000:THREE.MathUtils.radToDeg(q[c.name]);input.value=value;output.value=value.toFixed(1)+(c.unit==='m'?' mm':'°');}
}
function buildControls(){
  $('controls').replaceChildren();sliders.clear();const groups=new Map();
  for(const [i,c] of model.controls.entries()){
    if(!groups.has(c.group)){const section=document.createElement('section');section.className='studio-group';const heading=document.createElement('h3');heading.textContent=c.group;section.append(heading);$('controls').append(section);groups.set(c.group,section);}
    const row=document.createElement('div');row.className='studio-joint';const label=document.createElement('label'),span=document.createElement('span'),output=document.createElement('output'),input=document.createElement('input');
    input.id='studio-joint-'+i;label.htmlFor=input.id;span.textContent=c.label;label.append(span,output);input.type='range';const scale=c.unit==='m'?1000:180/Math.PI;input.min=c.lower*scale;input.max=c.upper*scale;input.step=c.unit==='m'?.1:.5;input.setAttribute('aria-label',c.group+' '+c.label);
    input.addEventListener('input',()=>{slow=false;selectedPose='';target={...current,[c.name]:Number(input.value)/scale};current={...target};apply(current);buttons();dirty=true;});
    row.append(label,input);groups.get(c.group).append(row);sliders.set(c.name,{input,output});
  }
  $('actions').replaceChildren();
  for(const name of (model.category==='others'?['neutral','flex']:basicPoses)){const b=document.createElement('button');b.textContent=name[0].toUpperCase()+name.slice(1);b.dataset.pose=name;b.onclick=()=>pose(name);$('actions').append(b);}
  const b=document.createElement('button');b.textContent='Slow motion';b.className='slow';b.dataset.slow='true';b.onclick=()=>{if(!selectedPose||selectedPose==='neutral')selectedPose=model.category==='others'?'flex':'wrap';slow=!slow;if(!slow)target={...current};clockStart=performance.now();buttons();dirty=true;};$('actions').append(b);
}
async function choose(id){
  const token=++generation;slow=false;$('loading').hidden=false;$('loading').textContent='Loading model…';$('controls').replaceChildren();$('actions').replaceChildren();
  try{
    const record=catalog.find(r=>r.id===id);if(!record)throw new Error('Model is not in this collection');
    const response=await fetch(`${record.metadata}?v=${studioVersion}`);if(!response.ok)throw new Error('Model metadata unavailable');const next=await response.json();
    const gltf=await loader.loadAsync(`${next.glb}?v=${studioVersion}`,e=>{if(token===generation&&e.total)$('loading').textContent='Loading model · '+Math.round(e.loaded/e.total*100)+'%';});
    if(token!==generation){dispose(gltf.scene);return;}
    if(root){scene.remove(root);dispose(root);}root=gltf.scene;
    // Older AI GLBs were reflected although their source geometry is already
    // right-handed. Cancel only that recorded display reflection.
    if(next.category==='ai'&&next.display_reflection)root.scale.x=-1;
    root.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;}});addBasicPoses(next);model=next;scene.add(root);joints.clear();
    for(const j of model.joints){const n=root.getObjectByName(j.node);if(!n)throw new Error('Missing joint node: '+j.node);joints.set(j.name,n);}
    $('name').textContent=model.name;$('counts').textContent=`${model.counts.active} active · ${model.counts.coupled} coupled · ${model.counts.passive} passive`;
    buildControls();current=values(model.poses.neutral||{});target={...current};apply(current);root.updateMatrixWorld(true);
    const box=new THREE.Box3().setFromObject(root),center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());
    const radius=Math.max(size.x,size.y,size.z),distance=radius*2.15;camera.near=Math.max(radius/1000,.0001);camera.far=radius*100;camera.updateProjectionMatrix();
    orbit.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(...(palmView[model.id]||model.view_direction||[.42,1,.28])).normalize().multiplyScalar(distance));orbit.minDistance=radius*.9;orbit.maxDistance=radius*8;orbit.update();
    selectedPose='neutral';buttons();$('status').textContent=model.category==='ai'?(model.concept_note||'Hand-only concept · direct-drive actuators · closed motor enclosures.'):'Skynet asset snapshot · visual meshes with original joint kinematics.';
    $('loading').hidden=true;dirty=true;
  }catch(error){if(token===generation){$('loading').hidden=false;$('loading').textContent='Model could not load. '+error.message;console.error(error);}}
}
function category(){const records=catalog.filter(r=>r.category===$('category').value);$('model').replaceChildren();for(const r of records){const o=document.createElement('option');o.value=r.id;o.textContent=r.name;$('model').append(o);}if(records.length)choose(records[0].id);else{$('loading').hidden=false;$('loading').textContent='No models published in this collection yet.';}}
$('category').onchange=category;$('model').onchange=()=>choose($('model').value);
function tick(now){requestAnimationFrame(tick);if(!visible||document.hidden||!model)return;let moving=false;
  if(slow){const x=(1-Math.cos((now-clockStart)*.00085))/2,a=values(model.poses.neutral),b=values(model.poses[selectedPose]);for(const c of model.controls)current[c.name]=a[c.name]*(1-x)+b[c.name]*x;moving=true;}
  else{for(const c of model.controls){const delta=target[c.name]-current[c.name];if(Math.abs(delta)>1e-5){current[c.name]+=delta*.15;moving=true;}else current[c.name]=target[c.name];}}
  if(moving){apply(current);dirty=true;}if(dirty){renderer.render(scene,camera);dirty=false;}
}
requestAnimationFrame(tick);
fetch(`assets/models/studio/catalog.json?v=${studioVersion}`).then(r=>{if(!r.ok)throw new Error('Catalog unavailable');return r.json();}).then(data=>{catalog=data.records;category();}).catch(e=>{$('loading').textContent=e.message;});
