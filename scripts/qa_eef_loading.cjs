// Exercise actual loading barriers with delayed requests, cached scenes and errors.
const fs=require('fs'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),out=process.env.QA_OUT||'/private/tmp/eef-loading-qa';
const probe=`\nglobalThis.loadingProbe=()=>({id:model.id,hands:[...mountedHands.values()].map(h=>h.id),q:{...current},orbit:orbit.enabled,bodyLoading,handLoading});`;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/hand-studio.js*',route=>route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'assets/js/hand-studio.js'),'utf8')+probe}));
  function hold(id){
   let release,received;
   const waiting=new Promise(resolve=>received=resolve),gate=new Promise(resolve=>release=resolve);
   page.route(`**/studio/${id}.json*`,async route=>{received();await gate;await route.continue();});
   return {waiting,release:()=>release()};
  }
  const ready=()=>page.waitForFunction(()=>document.querySelector('#studio-loading').hidden,null,{timeout:60000});
  const state=()=>page.evaluate(()=>loadingProbe());
  const assert=(ok,message)=>{if(!ok)throw new Error(message);};
  async function locked(){
   const ui=await page.evaluate(()=>({
    busy:document.querySelector('.studio').getAttribute('aria-busy'),
    loading:!document.querySelector('#studio-loading').hidden,
    text:document.querySelector('#studio-loading-text').textContent,
    canvas:getComputedStyle(document.querySelector('#studio-viewport canvas')).visibility,
    eef:document.querySelector('#studio-eef').disabled,
    inputs:[...document.querySelectorAll('#studio-controls input')].every(el=>el.disabled),
    buttons:[...document.querySelectorAll('#studio-actions button')].every(el=>el.disabled),
    inert:document.querySelector('#studio-controls').inert&&document.querySelector('#studio-actions').inert,
    navigation:!document.querySelector('#studio-model').disabled&&!document.querySelector('#studio-category').disabled
   }));
   assert(ui.busy==='true'&&ui.loading&&ui.canvas==='hidden'&&ui.eef&&ui.inputs&&ui.buttons&&ui.inert&&ui.navigation,'Incomplete loading barrier '+JSON.stringify(ui));
   assert(!(await state()).orbit,'Orbit still enabled during loading');return ui;
  }
  fs.mkdirSync(out,{recursive:true});
  await page.goto(process.env.STUDIO_URL||'http://127.0.0.1:8768/#hand-studio');await ready();
  await page.locator('#hand-studio').scrollIntoViewIfNeeded();
  const delayed=hold('aster20');
  await page.getByRole('button',{name:'Slow motion',exact:true}).click();
  await page.locator('#studio-eef').selectOption('aster20');await delayed.waiting;
  const networkLoading=await locked(),before=await state();
  assert(networkLoading.text.includes('Loading end effector'),'Wrong loading label');
  await page.getByRole('button',{name:'Close hands',exact:true}).click({force:true});
  await page.waitForTimeout(250);
  assert(JSON.stringify(before.q)===JSON.stringify((await state()).q),'Old joints moved while loading');
  await page.locator('#hand-studio').screenshot({path:path.join(out,'loading.png')});
  delayed.release();await ready();
  assert((await state()).hands.every(id=>id==='aster20'),'Replacement did not attach');
  const cached=await page.evaluate(async()=>{
   const select=document.querySelector('#studio-eef');select.value='lyra10';select.dispatchEvent(new Event('change',{bubbles:true}));
   return new Promise(resolve=>requestAnimationFrame(()=>resolve({busy:!document.querySelector('#studio-loading').hidden,disabled:select.disabled,hands:loadingProbe().hands})));
  });
  assert(cached.busy&&cached.disabled&&cached.hands.every(id=>id==='aster20'),'Cached hand skipped loading paint');
  await ready();assert((await state()).hands.every(id=>id==='lyra10'),'Cached replacement failed');
  await page.route('**/studio/robotera_xhand1_pro.json*',route=>route.fulfill({status:503,body:'Test unavailable hand'}));
  await page.locator('#studio-eef').selectOption('robotera_xhand1_pro');await ready();
  assert(await page.locator('#studio-eef').inputValue()==='lyra10','Failed replacement lost previous EEF');
  assert((await state()).hands.every(id=>id==='lyra10')&&(await state()).orbit,'Failed replacement did not restore old preview');
  assert((await page.locator('#studio-status').textContent()).includes('could not attach'),'Missing failure message');
  assert(await page.locator('#studio-controls input:disabled').count()===0,'Controls stayed disabled after failure');
  const obsolete=hold('nacre18'),nextBody=hold('orion16');
  await page.locator('#studio-eef').selectOption('nacre18');await obsolete.waiting;
  await page.locator('#studio-category').selectOption('ai');await page.locator('#studio-model').selectOption('orion16');await nextBody.waiting;
  obsolete.release();await page.waitForTimeout(150);await locked();
  nextBody.release();await ready();
  assert((await state()).id==='orion16'&&(await state()).hands.length===0,'Stale hand survived model switch');
  assert(!await page.locator('#studio-actions button:disabled').count(),'New body stayed locked');
  const report={delayedRequestLocked:true,oldMotionFrozen:true,cachedLoadingPaint:true,errorRestoresOldHand:true,staleRequestCannotUnlockNewModel:true,errors};
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  assert(!errors.length,'Browser errors');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
