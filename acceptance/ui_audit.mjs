// Read-only live UI QA: no generation, no simulated APIs.
import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const base=process.env.STUDIO_BASE_URL||'http://localhost:8124';
const output=new URL('../acceptance-output/ui-audit/',import.meta.url);await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const context=await browser.newContext();const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
const reports=[];
try{
 await page.goto(base);await page.getByRole('heading',{name:'A vision, in the details.'}).waitFor();
 const library=await(await page.request.get(base+'/api/library')).json();
 const all=library.categories.flatMap(c=>c.attributes.flatMap(a=>[a.thumbnail,...a.values.map(v=>v.thumbnail)]));
 const unique=[...new Set(all)];assert.equal(all.length,unique.length);
 const thumbResults=[];
 if(process.env.SKIP_ASSET_CENSUS!=='1'){
  for(let i=0;i<unique.length;i+=12){
   const batch=await Promise.all(unique.slice(i,i+12).map(async url=>{const r=await page.request.get(base+url);return {url,status:r.status(),type:r.headers()['content-type']};}));thumbResults.push(...batch);
  }
  assert.equal(thumbResults.length,all.length);assert.ok(thumbResults.every(r=>r.status===200&&r.type.includes('image/svg+xml')));
  const decoded=await page.evaluate(async urls=>{let ok=0;const failed=[];for(let i=0;i<urls.length;i+=12){await Promise.all(urls.slice(i,i+12).map(async url=>{const im=new Image();im.src=url;try{await im.decode();if(im.naturalWidth>0&&im.naturalHeight>0)ok++;else failed.push(url);}catch{failed.push(url);}}));}return {ok,failed};},unique);
  assert.equal(decoded.ok,all.length);assert.deepEqual(decoded.failed,[]);
 }
 for(const width of [1440,390,360]){
  await page.setViewportSize({width,height:width===1440?1000:844});
  await page.getByRole('tab',{name:'Studio',exact:true}).click();
  for(const id of ['skin','hair','pose','scenery']){
   if(width<700)await page.getByRole('button',{name:'Browse categories'}).click();
   const cat=library.categories.find(c=>c.id===id);await page.getByRole('navigation',{name:'Library categories'}).getByRole('button',{name:new RegExp(cat.name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'))}).click();
   const overflow=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth}));
   const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
   reports.push({width,view:id,overflow,violations:result.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))});
   await page.screenshot({path:new URL(width+'-'+id+'.png',output).pathname});
  }
  await page.getByRole('tab',{name:'Gallery',exact:true}).click();await page.getByLabel('Search gallery').waitFor();
  const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();reports.push({width,view:'gallery',overflow:await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth})),violations:result.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))});
  await page.screenshot({path:new URL(width+'-gallery.png',output).pathname});
 }
 await writeFile(new URL('report.json',output),JSON.stringify({evidence_type:'read-only REAL live UI audit; no provider calls',thumbnail_count:unique.length,thumbnail_results:thumbResults,reports,errors},null,2));
 console.log(JSON.stringify({thumbnail_count:unique.length,checked_thumbnails:thumbResults.length,views:reports.map(r=>({width:r.width,view:r.view,overflow:r.overflow.scroll>r.overflow.width,violations:r.violations.map(v=>v.id)})),errors,output:output.pathname},null,2));
 assert.deepEqual(errors,[]);assert.ok(reports.every(r=>r.overflow.scroll<=r.overflow.width));assert.ok(reports.every(r=>!r.violations.length),'Accessibility violations see report.json');
}finally{await browser.close();}
