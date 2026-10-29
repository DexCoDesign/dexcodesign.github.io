// Resource-level regressions: no heavy first-load requests, lossless model
// delivery, bounded decoded scenes, cancellation and unchanged interaction.
const fs=require('fs'),path=require('path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),out=process.env.QA_OUT||'/private/tmp/studio-lazy-qa';
const base=process.env.STUDIO_URL||'http://127.0.0.1:8768/';
const probe=`\nglobalThis.studioResourceProbe=()=>({id:model?.id,cache:[...sceneCache].map(([id,entry])=>({id,ready:Boolean(entry.scene)})),frames:renderer.info.render.frame,pendingFrame:frameRequest,memory:renderer.info.memory});`;
const assert=(ok,message)=>{if(!ok)throw new Error(message);};
const heavy=url=>/\/vendor\/three\/|\.glb(?:\.gz)?(?:\?|$)|\.mp4(?:\?|$)/.test(url);
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  try{
    fs.mkdirSync(out,{recursive:true});
    const page=await browser.newPage({viewport:{width:1440,height:900}}),requests=[],responses=[],errors=[];
    page.on('request',request=>requests.push(request.url()));
    page.on('response',response=>responses.push({url:response.url(),bytes:Number(response.headers()['content-length']||0)}));
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/hand-studio.js*',route=>route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'assets/js/hand-studio.js'),'utf8')+probe}));
    const start=Date.now();
    await page.goto(base,{waitUntil:'load'});
    await page.waitForFunction(()=>document.querySelector('#studio-model').options.length>0);
    await page.waitForTimeout(250);
    const counts=await page.evaluate(()=>window.DEXCODESIGN_VIDEOS.reduce((counts,item)=>(counts[item.dataset]=(counts[item.dataset]||0)+1,counts),{}));
    const initial={loadMs:Date.now()-start,bytes:responses.reduce((sum,row)=>sum+row.bytes,0),requests:requests.length,heavy:requests.filter(heavy)};
    assert(!initial.heavy.length,'Heavy first-load requests '+initial.heavy);
    assert(!requests.some(url=>url.includes('/thumbnails/')),'Offscreen gallery loaded thumbnails');
    const initialCards=await page.locator('.demo-card').count();
    assert(initialCards===counts.taco,'Unexpected startup cards '+JSON.stringify({initialCards,errors}));

    await page.locator('#videos').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>[...document.querySelectorAll('.video-thumbnail')].some(image=>image.complete&&image.naturalWidth));
    assert(!requests.some(heavy),'Browsing thumbnails loaded the studio or a video');
    await page.getByRole('button',{name:/^HOCAP/}).click();
    await page.waitForFunction(count=>document.querySelectorAll('.demo-card:not([hidden])').length===count,counts.hocap);
    assert(await page.locator('.demo-card').count()===counts.taco+counts.hocap,'Dataset filter rendered unrelated cards');
    await page.locator('.demo-card:not([hidden]) .video-launch').first().click();
    await page.waitForFunction(()=>document.querySelector('.demo-card video')?.readyState>=1);
    const videoUrls=[...new Set(requests.filter(url=>/\.mp4(?:\?|$)/.test(url)))];
    assert(videoUrls.length===1,'More than the clicked video was requested');
    await page.locator('#videos').screenshot({path:path.join(out,'gallery.png')});
    await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
    await page.waitForFunction(()=>document.querySelector('.demo-card video').paused);
    assert(!requests.some(url=>url.includes('/vendor/three/')),'Jumping past the studio initialized WebGL');

    await page.locator('#hand-studio').scrollIntoViewIfNeeded();
    const ready=()=>page.waitForFunction(()=>document.querySelector('#studio-loading').hidden,null,{timeout:90000});
    await ready();
    const modelResponses=responses.filter(row=>/\.glb(?:\.gz)?(?:\?|$)/.test(row.url));
    assert(modelResponses.length===2&&modelResponses.every(row=>row.url.includes('/compressed/')),'Default assembly did not use two compressed models');
    assert((await page.evaluate(()=>studioResourceProbe())).id==='dexmate_vega','Initial assembly changed');
    await page.locator('#studio-viewport').screenshot({path:path.join(out,'studio.png')});
    await page.waitForTimeout(300);
    const frameBefore=await page.evaluate(()=>studioResourceProbe().frames);
    await page.waitForTimeout(250);
    assert(await page.evaluate(()=>studioResourceProbe().frames)===frameBefore,'Idle studio keeps rendering');
    await page.getByRole('button',{name:'Slow motion',exact:true}).click();
    await page.waitForFunction(before=>studioResourceProbe().frames>before,frameBefore);
    await page.getByRole('button',{name:'Slow motion',exact:true}).click();

    await page.locator('#studio-category').selectOption('ai');await ready();
    for(const id of ['orion16','helix15','talon9']){await page.locator('#studio-model').selectOption(id);await ready();}
    const cache=await page.evaluate(()=>studioResourceProbe());
    assert(cache.cache.length<=3,'Decoded model cache is unbounded');
    assert(cache.cache.some(row=>row.id==='talon9'&&row.ready),'Current model was evicted');

    let release,received,aborted=false;
    const gate=new Promise(resolve=>release=resolve),waiting=new Promise(resolve=>received=resolve);
    page.on('requestfailed',request=>{if(request.url().includes('/nacre18.glb.gz'))aborted=true;});
    await page.route('**/compressed/nacre18.glb.gz*',async route=>{received();await gate;await route.continue().catch(()=>{});});
    await page.locator('#studio-model').selectOption('nacre18');await waiting;
    await page.waitForFunction(()=>studioResourceProbe().cache.some(row=>row.id==='nacre18'&&!row.ready));
    await page.locator('#studio-model').selectOption('talon9');await ready();
    release();await page.waitForTimeout(250);
    assert(aborted,'Obsolete model download was not cancelled');
    assert(!await page.evaluate(()=>studioResourceProbe().cache.some(row=>row.id==='nacre18')),'Cancelled model survived in cache');

    const fallback=await browser.newPage({viewport:{width:390,height:844}}),fallbackRequests=[];
    fallback.on('request',request=>fallbackRequests.push(request.url()));
    fallback.on('pageerror',error=>errors.push(error.message));
    await fallback.addInitScript(()=>{globalThis.DecompressionStream=undefined;});
    const direct=new URL(base);direct.searchParams.set('model','lyra10');direct.hash='hand-studio';
    await fallback.goto(direct.href);
    await fallback.waitForFunction(()=>document.querySelector('#studio-loading').hidden,null,{timeout:90000});
    assert(fallbackRequests.some(url=>/\/lyra10\.glb\?/.test(url))&&!fallbackRequests.some(url=>url.includes('.glb.gz')),'Uncompressed compatibility fallback failed');
    assert(await fallback.locator('#studio-model').inputValue()==='lyra10','Mobile model deep link changed');
    await fallback.locator('#studio-viewport').screenshot({path:path.join(out,'mobile.png')});
    await fallback.close();
    assert(!errors.length,'Browser errors '+errors.join('; '));
    const report={initial,defaultAssemblyBytes:modelResponses.reduce((sum,row)=>sum+row.bytes,0),compressedModels:modelResponses.map(row=>row.url),singleClickedVideo:true,offscreenVideoPaused:true,idleRenderingStopped:true,maxDecodedModels:cache.cache.length,obsoleteDownloadCancelled:aborted,mobileAndRawFallback:true,errors};
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
