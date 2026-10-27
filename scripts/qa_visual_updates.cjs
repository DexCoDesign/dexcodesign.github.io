const fs=require('fs'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),out=process.env.QA_OUT||'/private/tmp/studio-visual-updates';
const probe=`\nglobalThis.inspectVisuals=()=>{const skin=[];for(const hand of mountedHands.values())hand.group.traverse(node=>{if(node.isMesh)for(const material of [].concat(node.material))skin.push(material.color.getHexString(THREE.SRGBColorSpace));});let cameraVertices=0;findNode(root,'link__dexmate_camera_head')?.traverse(node=>{if(node.isMesh)cameraVertices+=node.geometry.attributes.position.count;});return {id:model.id,skin,cameraVertices,shoulders:['arm_L','arm_R'].map(name=>{const node=findNode(root,'link__'+name);let vertices=0;for(const visual of node?.children||[])if(visual.name.startsWith('visual__'))visual.traverse(child=>{if(child.isMesh)vertices+=child.geometry.attributes.position.count;});return {name,vertices};}),yaw:model.controls.find(c=>c.name==='mobile_base_yaw')};};`;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/hand-studio.js*',route=>route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'assets/js/hand-studio.js'),'utf8')+probe}));
  await page.goto(process.env.STUDIO_URL||'http://127.0.0.1:8768/#hand-studio');
  const ready=()=>page.waitForFunction(()=>document.querySelector('#studio-loading').hidden,null,{timeout:60000});await ready();fs.mkdirSync(out,{recursive:true});
  for(const id of ['dexmate_vega','rby1','gento_luna','dyna_taku']){
   await page.locator('#studio-model').selectOption(id);await ready();
   const state=await page.evaluate(()=>inspectVisuals());if(Math.abs(state.yaw.upper-20*Math.PI/180)>1e-10||Math.abs(state.yaw.lower+20*Math.PI/180)>1e-10)throw new Error('Wrong yaw range '+id);
  }
  await page.locator('#studio-model').selectOption('rby1');await ready();await page.locator('#studio-eef').selectOption('mano');await ready();
  const mano=await page.evaluate(()=>inspectVisuals());if(mano.cameraVertices<100)throw new Error('RBY1 cosmetic camera missing');if(!mano.skin.length||mano.skin.some(color=>color!=='d6a88e'))throw new Error('Wrong MANO skin color');
  await page.locator('#hand-studio').scrollIntoViewIfNeeded();await page.locator('#hand-studio').screenshot({path:path.join(out,'mano-skin.png')});
  await page.locator('#studio-model').selectOption('gento_luna');await ready();
  const luna=await page.evaluate(()=>inspectVisuals());if(luna.shoulders.some(part=>part.vertices<1000))throw new Error('Luna shoulder housing missing '+JSON.stringify(luna.shoulders));
  await page.locator('#studio-eef').selectOption('none');await ready();await page.locator('#hand-studio').screenshot({path:path.join(out,'luna-v3-shoulders.png')});
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({manoSkin:'d6a88e',rbyCameraVertices:mano.cameraVertices,lunaShoulders:luna.shoulders,allYawLimitsDeg:20,errors},null,2));
  console.log(JSON.stringify({manoSkin:'d6a88e',rbyCameraVertices:mano.cameraVertices,lunaShoulders:luna.shoulders,allYawLimitsDeg:20,errors}));if(errors.length)throw new Error('Browser errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
