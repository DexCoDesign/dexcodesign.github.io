// Check the rendered graph, not just the three labels in the control panel.
const fs=require('fs'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),out=process.env.QA_OUT||'/private/tmp/planar-base-qa';
const probe=`\nglobalThis.inspectBase=()=>{root.updateMatrixWorld(true);const points={};root.traverse(node=>{if((node.name.startsWith('link__')&&!['link__mobile_world','link__mobile_base_x_link','link__mobile_base_y_link'].includes(node.name))||node.name.endsWith('_hand_attachment'))points[node.name]=node.getWorldPosition(new THREE.Vector3()).toArray();});return {id:model.id,controls:model.controls,points,q:{...current},neutral:values(model.poses.neutral),slow,view:[...camera.position.toArray(),...camera.up.toArray(),...orbit.target.toArray(),camera.zoom,...viewShift.toArray()],joints:model.joints.map(j=>j.name),base:model.base_model};};`;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/hand-studio.js*',route=>route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'assets/js/hand-studio.js'),'utf8')+probe}));
  await page.goto(process.env.STUDIO_URL||'http://127.0.0.1:8768/#hand-studio');
  const ready=()=>page.waitForFunction(()=>document.querySelector('#studio-loading').hidden,null,{timeout:60000});
  await ready();fs.mkdirSync(out,{recursive:true});const records=[];
  for(const id of ['dexmate_vega','rby1','gento_luna','dyna_taku']){
   await page.locator('#studio-model').selectOption(id);await ready();
   const before=await page.evaluate(()=>inspectBase()),names=['mobile_base_x','mobile_base_y','mobile_base_yaw'];
   const base=before.controls.filter(c=>c.group==='Mobile base');
   if(JSON.stringify(base.map(c=>c.name))!==JSON.stringify(names))throw new Error('Wrong base controls '+id);
   if(before.joints.some(n=>/wheel|steer|^agv_.*rotate/i.test(n)))throw new Error('Wheel motor survived '+id);
   const x=.03,y=-.02,yaw=3*Math.PI/180;
   await page.evaluate(({names,values})=>{
    for(let i=0;i<names.length;i++){
     const row=inspectBase().controls.findIndex(c=>c.name===names[i]),input=document.querySelector('#studio-joint-'+row);
     input.value=values[i];input.dispatchEvent(new Event('input',{bubbles:true}));
    }
   },{names,values:[x*1000,y*1000,yaw*180/Math.PI]});
   const moved=await page.evaluate(()=>inspectBase());let maxError=0;
   for(const [name,p] of Object.entries(before.points)){
    const expected=[Math.cos(yaw)*p[0]-Math.sin(yaw)*p[1]+x,Math.sin(yaw)*p[0]+Math.cos(yaw)*p[1]+y,p[2]];
    maxError=Math.max(maxError,...expected.map((v,i)=>Math.abs(v-moved.points[name][i])));
   }
   if(maxError>1e-8)throw new Error('Base did not move robot and both hands rigidly '+id+' '+maxError);
   if(id==='gento_luna'){await page.locator('#hand-studio').scrollIntoViewIfNeeded();await page.locator('#hand-studio').screenshot({path:path.join(out,'luna-virtual-base.png')});}
   await page.getByRole('button',{name:'Fold',exact:true}).click();
   await page.getByRole('button',{name:'Close hands',exact:true}).click();
   await page.getByRole('button',{name:'Slow motion',exact:true}).click();
   await page.locator('#hand-studio').scrollIntoViewIfNeeded();
   const box=await page.locator('#studio-viewport').boundingBox();
   await page.mouse.move(box.x+box.width*.45,box.y+box.height*.45);await page.mouse.down();
   await page.mouse.move(box.x+box.width*.65,box.y+box.height*.6,{steps:8});await page.mouse.up();await page.mouse.wheel(0,-180);
   await page.waitForFunction(view=>inspectBase().view.some((value,i)=>Math.abs(value-view[i])>1e-5),before.view);
   await page.getByRole('button',{name:'Home',exact:true}).click();
   await page.waitForFunction(()=>{const state=inspectBase();return !state.slow&&Object.entries(state.neutral).every(([name,value])=>Math.abs(state.q[name]-value)<1e-5);});
   const restored=await page.evaluate(()=>inspectBase());
   const viewError=Math.max(...before.view.map((value,i)=>Math.abs(value-restored.view[i])));
   if(viewError>1e-8)throw new Error('Home did not restore the initial view '+id+' '+viewError);
   await page.waitForTimeout(150);
   if((await page.evaluate(()=>inspectBase())).slow)throw new Error('Home did not stop Slow motion '+id);
   if(id==='dexmate_vega')await page.locator('#studio-viewport').screenshot({path:path.join(out,'home-reset.png')});
   records.push({id,baseControls:base.map(c=>c.label),rigidFrames:Object.keys(before.points).length,maxError,homeResetsPoseAndView:true,viewError});
  }
  const report={records,errors};fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  if(errors.length)throw new Error('Browser errors');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
