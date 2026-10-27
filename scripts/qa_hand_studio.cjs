// Local development QA; never shipped as a browser dependency.
const fs=require('fs'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});
 const errors=[],failed=[];page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400)failed.push(r.url()+' '+r.status());});
 await page.goto(process.env.STUDIO_URL||'http://127.0.0.1:8767/#hand-studio');
 await page.locator('#hand-studio').scrollIntoViewIfNeeded();
 const catalog=await page.evaluate(async()=>await(await fetch('assets/models/studio/catalog.json')).json());
 const out=process.env.QA_OUT||'/private/tmp/hand-studio-qa';fs.mkdirSync(out,{recursive:true});
 const records=[];
 const selected=process.env.QA_MODELS?.split(',');
 for(const record of catalog.records.filter(r=>!selected||selected.includes(r.id))){
  if(await page.locator('#studio-category').inputValue()!==record.category)await page.locator('#studio-category').selectOption(record.category);
  await page.locator('#studio-model').selectOption(record.id);
  await page.waitForFunction(name=>document.querySelector('#studio-name').textContent===name&&document.querySelector('#studio-loading').hidden,record.name,{timeout:60000});
  await page.waitForTimeout(250);
  const controls=page.locator('#studio-controls input');if(await controls.count()!==record.counts.active)throw new Error('Control count mismatch '+record.id);
  await page.locator('#studio-viewport').screenshot({path:path.join(out,record.id+'.png')});
  const expected=record.category==='manipulator'?['Home','Spread','Fold']:record.category==='others'?['Neutral','Flex']:['Neutral','Spread','Wrap','Pinch'];
  const names=await page.locator('#studio-actions button[data-pose]').allTextContents();
  if(JSON.stringify(names)!==JSON.stringify(expected))throw new Error('Pose buttons mismatch '+record.id+': '+names);
  for(const name of expected){
   await page.getByRole('button',{name,exact:true}).click();
   if(!await page.getByRole('button',{name,exact:true}).evaluate(el=>el.classList.contains('on')))throw new Error('Pose did not activate '+record.id+' '+name);
   if((process.env.QA_CAPTURE_POSES||'').split(',').includes(name.toLowerCase())){
    await page.waitForTimeout(650);
    await page.locator('#studio-viewport').screenshot({path:path.join(out,record.id+'-'+name.toLowerCase()+'.png')});
   }
  }
  await page.waitForTimeout(650);
  await page.locator('#studio-viewport').screenshot({path:path.join(out,record.id+'-pose.png')});
  await page.getByRole('button',{name:record.category==='manipulator'?'Home':'Neutral',exact:true}).click();
  const first=controls.first();await first.focus();await first.press('ArrowRight');
  await page.getByRole('button',{name:'Slow motion',exact:true}).click();await page.waitForTimeout(150);
  await page.getByRole('button',{name:'Slow motion',exact:true}).click();
  records.push({id:record.id,controls:await controls.count(),loaded:true});
 }
 await page.locator('#studio-category').selectOption('ai');await page.locator('#studio-model').selectOption('lyra10');
 await page.waitForFunction(()=>document.querySelector('#studio-name').textContent==='LYRA-10'&&document.querySelector('#studio-loading').hidden);
 await page.waitForTimeout(200);await page.locator('#hand-studio').screenshot({path:path.join(out,'desktop.png')});
 const box=await page.locator('#studio-viewport').boundingBox();await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.7,box.y+box.height*.6,{steps:10});await page.mouse.up();await page.waitForTimeout(200);
 await page.locator('#studio-viewport').screenshot({path:path.join(out,'drag.png')});
 await page.setViewportSize({width:390,height:844});await page.locator('#studio-model').selectOption('aster20');await page.locator('#studio-model').selectOption('lyra10');
 await page.waitForFunction(()=>document.querySelector('#studio-name').textContent==='LYRA-10'&&document.querySelector('#studio-loading').hidden);
 await page.locator('#hand-studio').scrollIntoViewIfNeeded();await page.waitForTimeout(150);await page.locator('#hand-studio').screenshot({path:path.join(out,'mobile.png'),style:'nav.site-nav { visibility:hidden; }'});
 let manipulator=null;
 if(catalog.records.some(r=>r.category==='manipulator')){
  const destination=new URL(process.env.STUDIO_URL||'http://127.0.0.1:8767/#hand-studio');destination.searchParams.set('collection','manipulator');destination.searchParams.set('model','dyna_taku');
  await page.goto(destination.href);
  await page.waitForFunction(()=>document.querySelector('#studio-name').textContent==='DYNA Taku'&&document.querySelector('#studio-loading').hidden);
  const categories=await page.locator('#studio-category option').evaluateAll(items=>items.map(o=>o.value));
  if(categories.indexOf('manipulator')!==categories.indexOf('ai')+1||categories.indexOf('others')!==categories.indexOf('manipulator')+1)throw new Error('Manipulator collection order changed');
  if(await page.locator('#studio-category').inputValue()!=='manipulator'||await page.locator('#studio-model').inputValue()!=='dyna_taku')throw new Error('Manipulator deep link did not select the model');
  await page.setViewportSize({width:1440,height:1100});await page.locator('#hand-studio').scrollIntoViewIfNeeded();await page.waitForTimeout(200);
  await page.locator('#hand-studio').screenshot({path:path.join(out,'manipulator-desktop.png')});
  await page.setViewportSize({width:390,height:844});await page.locator('#hand-studio').scrollIntoViewIfNeeded();await page.waitForTimeout(200);
  const width=await page.locator('.studio').evaluate(el=>({width:el.getBoundingClientRect().width,viewport:innerWidth}));
  if(width.width>width.viewport)throw new Error('Manipulator mobile layout overflows viewport');
  await page.locator('#hand-studio').screenshot({path:path.join(out,'manipulator-mobile.png'),style:'nav.site-nav { visibility:hidden; }'});
  manipulator={deepLink:true,categoryOrder:true,mobileLayout:true,controls:await page.locator('#studio-controls input').count()};
 }
 const report={records,manipulator,errors,failed};fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 await browser.close();if(errors.length||failed.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1);});
