// Read-only REAL photographic UI acceptance. No routes, mocks or provider calls.
import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
let base=process.env.STUDIO_BASE_URL||'http://localhost:8123';
let entry=base;
if(process.env.PHONE_STATE_FILE){const state=JSON.parse(await readFile(process.env.PHONE_STATE_FILE,'utf8'));base=state.origin;entry=base+'/access/'+state.token;}
const output=new URL('../acceptance-output/photographic-live/',import.meta.url);await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const context=await browser.newContext({viewport:{width:390,height:844}});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(entry,{waitUntil:'domcontentloaded',timeout:60000});
 const progress=page.getByRole('region',{name:'Photographic preview progress'});await progress.waitFor({timeout:60000});
 await page.getByText('Generated photographic examples',{exact:true}).waitFor();
 const images=page.locator('#studio-content img[src*="/generated/"]');assert.ok(await images.count()>0);
 assert.equal(await page.locator('#studio-content img[src*="/thumbnails/"]').count(),0);
 const first=images.first();await first.scrollIntoViewIfNeeded();await first.evaluate(async image=>{await image.decode();if(!image.naturalWidth)throw Error('Photograph did not decode');});
 const pixelProof=await first.evaluate(image=>{const canvas=document.createElement('canvas');canvas.width=canvas.height=32;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0,32,32);const data=ctx.getImageData(0,0,32,32).data;let lo=255,hi=0;for(let i=0;i<data.length;i+=4){lo=Math.min(lo,data[i],data[i+1],data[i+2]);hi=Math.max(hi,data[i],data[i+1],data[i+2]);}const style=getComputedStyle(image);return {pixelRange:hi-lo,opacity:style.opacity,visibility:style.visibility,width:image.getBoundingClientRect().width,height:image.getBoundingClientRect().height};});
 assert.ok(pixelProof.pixelRange>16);assert.equal(pixelProof.opacity,'1');assert.equal(pixelProof.visibility,'visible');assert.ok(pixelProof.width>0&&pixelProof.height>0);
 assert.ok(await page.locator('#studio-content img[src*="/preview-atlases/"]').count()>0,'Versioned contact sheets must actually render');
 const library=await(await page.request.get(base+'/api/library')).json();const status=await(await page.request.get(base+'/api/thumbnail-status')).json();
 assert.equal(status.mode,'photographic');assert.equal(status.total,893);assert.ok(status.value_completed>=6);
 assert.equal(library.thumbnail_mode,'photographic');
 const ready=library.categories.flatMap(c=>c.attributes.flatMap(a=>a.values.filter(v=>v.thumbnail_kind==='photographic')));
 assert.ok(ready.length>=6);
 const response=await page.request.get(base+ready[0].example_url);assert.equal(response.status(),200);assert.match(response.headers()['content-type'],/^image\/jpeg/);
 const checks=[];
 for(const width of [390,1440]){
  await page.setViewportSize({width,height:width===390?844:1000});await page.evaluate(()=>scrollTo(0,0));
  const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  checks.push({width,overflow,violations:axe.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}))});
  await page.screenshot({path:new URL(width+'.png',output).pathname});
 }
 await writeFile(new URL('report.json',output),JSON.stringify({evidence:'REAL authenticated/loopback photographic UI; no interception or provider calls',status,ready_values:ready.length,checks,errors},null,2));
 console.log(JSON.stringify({status,visible_photo_count:await images.count(),diagrams_visible:0,checks,errors,evidence:output.pathname},null,2));
 assert.deepEqual(errors,[]);assert.ok(checks.every(c=>!c.overflow&&!c.violations.length));
}finally{await browser.close();}
