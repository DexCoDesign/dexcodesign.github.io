// Exercise the published viewer graph, including opposite native arm configurations.
const fs=require('fs'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),out=process.env.QA_OUT||'/private/tmp/bimanual-site-qa';
const probe=`\nglobalThis.inspectBimanual=()=>{root.updateMatrixWorld(true);return {id:model.id,q:{...current},body:bodyModel.controls.map(c=>c.name),hands:[...mountedHands.values()].map(h=>({side:h.side,id:h.id,matrix:h.sourceRoot.matrixWorld.toArray()})),base:bodyModel.base_model,mounting:bodyModel.mounting};};`;
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],failed=[];page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400&&!r.url().endsWith('favicon.ico'))failed.push(r.url()+' '+r.status());});
  await page.route('**/hand-studio.js*',route=>route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'assets/js/hand-studio.js'),'utf8')+probe}));
  await page.goto(process.env.STUDIO_URL||'http://127.0.0.1:8779/#hand-studio');
  const ready=()=>page.waitForFunction(()=>document.querySelector('#studio-loading').hidden,null,{timeout:60000});await ready();await page.locator('#hand-studio').scrollIntoViewIfNeeded();
  if(await page.locator('#studio-category option[value="ai"]').textContent()!=='AI Hand')throw new Error('AI Hand category label missing');
  if(await page.locator('#studio-eef optgroup[label="AI Hand"]').count()!==1)throw new Error('AI Hand EEF label missing');
  const ids=['franka_fr3','kinova_gen3','aloha2','openarm2'];let selected='lyra10';const report=[];
  function symmetry(state){
   const l=state.hands.find(h=>h.side==='left'),r=state.hands.find(h=>h.side==='right');if(!l||!r)throw new Error('Missing hand');
   let maximum=0;for(let c=0;c<4;c++)for(let row=0;row<4;row++){const index=4*c+row;maximum=Math.max(maximum,Math.abs(l.matrix[index]-(row===1?-1:1)*r.matrix[index]));}
   if(maximum>.002)throw new Error('EEF mirror mismatch '+state.id+' '+maximum);return maximum;
  }
  for(const id of ids){
   await page.locator('#studio-model').selectOption(id);await ready();let state=await page.evaluate(()=>inspectBimanual());
   if(state.id!==id||state.hands.some(h=>h.id!==selected))throw new Error('EEF did not persist across model change');
   if(state.base.type!=='fixed'||state.base.joints.length||state.body.some(n=>/mobile_base|wheel|lift|mount_flip/.test(n)))throw new Error('Fixed lift exposes base DOF');
   const original=JSON.parse(fs.readFileSync(path.join(root,'assets/models/studio',id+'.json')));for(const [name,q] of Object.entries(original.poses.neutral))if(Math.abs(state.q[name]-q)>1e-8)throw new Error('Native Home changed');
   let mirror=symmetry(state);
   await page.locator('#studio-eef').selectOption('wuji_hand_2');await ready();selected='wuji_hand_2';symmetry(await page.evaluate(()=>inspectBimanual()));
   await page.getByRole('button',{name:'Slow motion',exact:true}).click();const samples=[];
   for(const delay of [950,900,900]){await page.waitForTimeout(delay);state=await page.evaluate(()=>inspectBimanual());mirror=Math.max(mirror,symmetry(state));samples.push(state);}
   for(const name of state.body){const q=samples.map(s=>s.q[name]);if(Math.max(...q)-Math.min(...q)<1e-5)throw new Error('Arm joint did not move '+id+' '+name);}
   await page.getByRole('button',{name:'Home',exact:true}).click();await page.waitForTimeout(800);symmetry(await page.evaluate(()=>inspectBimanual()));
   for(const label of ['Spread','Fold']){await page.getByRole('button',{name:label,exact:true}).click();await page.waitForTimeout(800);symmetry(await page.evaluate(()=>inspectBimanual()));}
   await page.getByRole('button',{name:'Home',exact:true}).click();await page.waitForTimeout(800);
   await page.locator('#hand-studio').screenshot({path:path.join(out,id+'-wuji.png')});
   await page.locator('#studio-eef').selectOption('lyra10');await ready();selected='lyra10';symmetry(await page.evaluate(()=>inspectBimanual()));
   await page.locator('#hand-studio').screenshot({path:path.join(out,id+'-lyra.png')});
   report.push({id,bodyJoints:state.body.length,maxEEFMatrixMirrorError:mirror,nativeHome:true,allBodyJointsMoved:true,realAndAIHands:true});
  }
  await page.locator('#studio-eef').selectOption('none');await ready();await page.locator('#studio-model').selectOption('franka_fr3');await ready();if((await page.evaluate(()=>inspectBimanual())).hands.length)throw new Error('Explicit None lost');
  await page.setViewportSize({width:390,height:844});await page.locator('#hand-studio').scrollIntoViewIfNeeded();if(await page.locator('.studio').evaluate(el=>el.getBoundingClientRect().width>innerWidth))throw new Error('Mobile overflow');await page.locator('#hand-studio').screenshot({path:path.join(out,'mobile.png'),style:'nav.site-nav {visibility:hidden}'});
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({report,labels:'AI Hand',errors,failed},null,2));console.log(JSON.stringify({report,errors,failed}));if(errors.length||failed.length)throw new Error('Browser or resource errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
