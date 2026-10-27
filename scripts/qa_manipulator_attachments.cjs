// Integration QA against the actual browser graph, with test-only inspection.
const fs=require('fs'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),out=process.env.QA_OUT||'/private/tmp/manipulator-attachments-qa';
fs.mkdirSync(out,{recursive:true});
const instrumentation=`
globalThis.measureWristPlates=()=>{root.updateMatrixWorld(true);const results=[];for(const hand of mountedHands.values()){const inverse=new THREE.Matrix4().copy(hand.group.parent.matrixWorld).invert(),points=[];for(const child of hand.sourceRoot.children){if(!child.isMesh)continue;const position=child.geometry.attributes.position,transform=new THREE.Matrix4().multiplyMatrices(inverse,child.matrixWorld);for(let i=0;i<position.count;i++){const p=new THREE.Vector3().fromBufferAttribute(position,i).applyMatrix4(transform);if(Math.abs(p.z)<.0002)points.push(p);}}const box=new THREE.Box3().setFromPoints(points),center=box.getCenter(new THREE.Vector3());results.push({id:hand.id,side:hand.side,root:hand.sourceRoot.name,points:points.length,center:center.toArray()});}return results;};
globalThis.inspectAssembly=()=>{
 root.updateMatrixWorld(true);
 return {id:model.id,upright:bodyModel?.upright_node?new THREE.Vector3(0,0,1).transformDirection(findNode(root,bodyModel.upright_node).matrixWorld).toArray():null,controls:model.controls.length,q:{...current},pairs:model.motion_pairs||[],actual:Object.fromEntries(model.joints.map(j=>{const node=joints.get(j.name),axis=new THREE.Vector3(...j.axis).normalize();if(j.type==='prismatic'){const base=new THREE.Quaternion().fromArray(j.quaternion);return [j.name,node.position.clone().sub(new THREE.Vector3(...j.position)).dot(axis.applyQuaternion(base))];}const relative=new THREE.Quaternion().fromArray(j.quaternion).invert().multiply(node.quaternion);return [j.name,2*Math.atan2(new THREE.Vector3(relative.x,relative.y,relative.z).dot(axis),relative.w)];})),movable:model.joints.filter(j=>j.upper-j.lower>1e-8&&j.mode!=='fixed').map(j=>j.name),hands:[...mountedHands.values()].map(hand=>{
   const origin=hand.group.parent.getWorldPosition(new THREE.Vector3());
   const normal=new THREE.Vector3(0,0,1).transformDirection(hand.group.parent.matrixWorld);
   const sourceAxis=new THREE.Vector3(...hand.profile.distal_axis);if(hand.profile.source_reflect_x)sourceAxis.x*=-1;
   const distal=sourceAxis.transformDirection(hand.sourceRoot.matrixWorld);
   return {id:hand.id,side:hand.side,origin:origin.toArray(),normal:normal.toArray(),distal:distal.toArray(),alignment:normal.dot(distal),
     baseNode:hand.sourceRoot.name,active:hand.controls.length,root:hand.sourceRoot.getWorldPosition(new THREE.Vector3()).toArray(),
     standaloneJoints:hand.joints.filter(j=>/(?:^|_)(?:pos|rot)_[xyz]$/.test(j.name)).length};
 })};
};`;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});
  const errors=[],failed=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.status()>=400&&!r.url().endsWith('/favicon.ico'))failed.push(r.url()+' '+r.status());});
  await page.route('**/hand-studio.js*',route=>route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'assets/js/hand-studio.js'),'utf8')+instrumentation}));
  await page.goto(process.env.STUDIO_URL||'http://127.0.0.1:8768/#hand-studio');
  await page.waitForFunction(()=>document.querySelector('#studio-loading').hidden);
  const catalog=JSON.parse(fs.readFileSync(path.join(root,'assets/models/studio/catalog.json'),'utf8'));
  const manipulators=catalog.records.filter(r=>r.category==='manipulator');
  if(manipulators.length!==4||catalog.records.some(r=>r.id==='galaxea_r1'))throw new Error('Manipulator collection must contain four models without Galaxea');
  const combinations=[['dexmate_vega','wuji_hand_2'],['rby1','mano'],['gento_luna','nacre18'],['dyna_taku','midas_hand']];
  const tested=[];let expectedEEF='lyra10';
  const startup=await page.evaluate(()=>inspectAssembly());
  if(startup.id!=='dexmate_vega'||startup.hands.length!==2||startup.hands.some(h=>h.id!=='lyra10'))throw new Error('Startup must be Dexmate + LYRA-10');
  await page.locator('#hand-studio').scrollIntoViewIfNeeded();await page.locator('#hand-studio').screenshot({path:path.join(out,'startup-dexmate-lyra.png')});
  async function checkGraph(){
   const state=await page.evaluate(()=>inspectAssembly());
   if(state.hands.some(h=>h.alignment<.999999||h.standaloneJoints||h.root.some(v=>!Number.isFinite(v))))throw new Error('Mount graph mismatch '+JSON.stringify(state));
   if(await page.locator('#studio-controls input').count()!==state.controls)throw new Error('Control count mismatch');
   return state;
  }
  for(const [mobile,hand] of combinations){
   await page.locator('#studio-model').selectOption(mobile);
   await page.waitForFunction(id=>typeof inspectAssembly==='function'&&inspectAssembly().id===id&&document.querySelector('#studio-loading').hidden,mobile);
   if(await page.locator('#studio-eef').inputValue()!==expectedEEF)throw new Error('Selected EEF was lost on model change');
   const carried=await checkGraph();if(carried.hands.length!==2||carried.hands.some(h=>h.id!==expectedEEF))throw new Error('Selected EEF did not reattach to the next body');
   await page.locator('#studio-eef').selectOption(hand);
   await page.waitForFunction(id=>inspectAssembly().hands.length===2&&inspectAssembly().hands.every(h=>h.id===id),hand);
   const initial=await checkGraph();
   if(initial.upright[2]<.999)throw new Error('Home upper body is tilted '+mobile);
   if(initial.hands.some(h=>h.normal[0]<.97))throw new Error('Home wrist does not point forward '+mobile);
   await page.locator('#hand-studio').scrollIntoViewIfNeeded();await page.waitForTimeout(200);
   await page.locator('#hand-studio').screenshot({path:path.join(out,mobile+'.png')});
   await page.getByRole('button',{name:'Close hands',exact:true}).click();await page.waitForTimeout(700);await checkGraph();
   const inputs=page.locator('#studio-controls input');
   const arm=page.locator('#studio-controls .studio-group').filter({has:page.getByRole('heading',{name:'Left arm',exact:true})}).locator('input').first();
   await arm.evaluate(el=>{el.value=Math.min(Number(el.max),Number(el.value)+5);el.dispatchEvent(new Event('input',{bubbles:true}));});
   const moved=await checkGraph();
   if(Math.max(...moved.hands.map(h=>Math.hypot(...h.origin.map((v,i)=>v-initial.hands.find(x=>x.side===h.side).origin[i]))))<1e-5)throw new Error('Arm did not move the mounted hand');
   await page.getByRole('button',{name:'Home',exact:true}).click();await page.waitForTimeout(700);await checkGraph();
   if(hand==='midas_hand'&&await page.locator('#studio-controls input:disabled').count()!==12)throw new Error('MIDAS nonlinear followers must be read-only on both hands');
   await page.getByRole('button',{name:'Slow motion',exact:true}).click();
   const samples=[];for(const delay of [950,1200,1200]){await page.waitForTimeout(delay);samples.push(await checkGraph());}
   for(const name of samples[0].movable){const values=samples.map(s=>s.actual[name]);if(Math.max(...values)-Math.min(...values)<1e-6)throw new Error('Joint stayed still during Slow motion '+mobile+' '+name);}
   for(const sample of samples)for(const pair of sample.pairs){if(Math.abs(sample.actual[pair.right]-pair.sign*sample.actual[pair.left]-pair.offset)>3e-5)throw new Error('Asymmetric joint motion '+JSON.stringify({pair,left:sample.actual[pair.left],right:sample.actual[pair.right],qleft:sample.q[pair.left],qright:sample.q[pair.right]}));}
   await page.getByRole('button',{name:'Slow motion',exact:true}).click();
   expectedEEF=hand;
   tested.push({mobile,hand,controls:initial.controls,preservesEEF:true,tabletopForward:true,rigidAfterArmMotion:true});
  }
  await page.locator('#studio-eef').selectOption('none');if((await checkGraph()).hands.length!==0)throw new Error('None must remove both hands');
  await page.locator('#studio-model').selectOption('rby1');await page.waitForFunction(()=>inspectAssembly().id==='rby1'&&document.querySelector('#studio-loading').hidden);
  if(await page.locator('#studio-eef').inputValue()!=='none'||(await checkGraph()).hands.length)throw new Error('Explicit None was lost on model change');
  await page.locator('#studio-model').selectOption('dyna_taku');await page.waitForFunction(()=>inspectAssembly().id==='dyna_taku'&&document.querySelector('#studio-loading').hidden);
  const hands=catalog.records.filter(r=>['hand','robot','ai'].includes(r.category));
  for(const record of hands){
   await page.locator('#studio-eef').selectOption(record.id);
   await page.waitForFunction(id=>inspectAssembly().hands.some(h=>h.side==='right'&&h.id===id),record.id);await checkGraph();
  }
  for(const id of ['ruka_v2','shadow_hand_e','unitree_dex5_1']){
   await page.locator('#studio-eef').selectOption(id);await page.waitForFunction(id=>inspectAssembly().hands.length===2&&inspectAssembly().hands.every(h=>h.id===id),id);
   const centered=await page.evaluate(()=>measureWristPlates());
   if(centered.some(r=>r.points<20||Math.hypot(r.center[0],r.center[1])>.0002))throw new Error('Wrist plate is not centered '+JSON.stringify(centered));
   if(id==='shadow_hand_e'&&centered.some(r=>!r.root.endsWith('link__rh_forearm')))throw new Error('Shadow base was cropped');
   fs.writeFileSync(path.join(out,id+'-centering.json'),JSON.stringify(centered,null,2));
   await page.getByRole('button',{name:'Slow motion',exact:true}).click();await page.waitForTimeout(950);const a=await checkGraph();await page.waitForTimeout(1600);const b=await checkGraph();for(const name of a.movable)if(Math.abs(a.actual[name]-b.actual[name])<1e-6)throw new Error('Restored hand joint stayed still '+id+' '+name);await page.getByRole('button',{name:'Slow motion',exact:true}).click();
  }
  await page.locator('#studio-eef').selectOption('midas_hand');
  await page.waitForFunction(()=>inspectAssembly().hands.some(h=>h.id==='midas_hand'));
  await page.evaluate(()=>{const el=document.querySelector('#studio-eef');for(const value of ['mano','nacre18','none']){el.value=value;el.dispatchEvent(new Event('change',{bubbles:true}));}});
  await page.waitForTimeout(500);if((await checkGraph()).hands.length!==0)throw new Error('Stale hand load survived a later None selection');
  await page.locator('#studio-eef').selectOption('midas_hand');await page.waitForFunction(()=>inspectAssembly().hands.length===2);
  await page.setViewportSize({width:390,height:844});await page.locator('#hand-studio').scrollIntoViewIfNeeded();await page.waitForTimeout(200);
  if(await page.locator('.studio').evaluate(el=>el.getBoundingClientRect().width>innerWidth))throw new Error('Mobile overflow');
  await page.locator('#hand-studio').screenshot({path:path.join(out,'taku-mobile.png'),style:'nav.site-nav { visibility:hidden; }'});
  const report={startup:'dexmate_vega+lyra10',preservesEEF:true,explicitNonePreserved:true,combinations:tested,allHandModels:hands.map(r=>r.id),rapidSelection:true,mobileLayout:true,errors,failed};
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  if(errors.length||failed.length)throw new Error('Browser or resource errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
