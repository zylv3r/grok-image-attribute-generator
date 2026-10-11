// REAL paid provider flow: rendered UI, no mocked API, route interception or fabricated records.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
const baseURL=process.env.STUDIO_BASE_URL||'http://localhost:8124';
if(process.env.RUN_PAID_GENERATION!=='1') throw Error('Set RUN_PAID_GENERATION=1; this submits exactly two paid images.');
const output=new URL('../acceptance-output/',import.meta.url); await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage(); const errors=[]; page.on('pageerror',e=>errors.push(e.message));
try {
 const library=await (await context.request.get(baseURL+'/api/library')).json();
 const attrs=library.categories.flatMap(c=>c.attributes);
 const attr=id=>attrs.find(a=>a.id===id); const value=(id,vid)=>attr(id).values.find(v=>v.id===vid).name;
 await page.goto(baseURL); await page.getByRole('heading',{name:'A vision, in the details.'}).waitFor();
 await page.getByRole('button',{name:'Reset composition'}).click();
 const nav=page.getByRole('navigation',{name:'Library categories'});
 async function categoryFor(aid){const c=library.categories.find(c=>c.attributes.some(a=>a.id===aid)); await nav.getByRole('button',{name:new RegExp(c.name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'))}).click();}
 await categoryFor('skin_tone');
 await page.getByRole('region',{name:attr('skin_tone').name,exact:true}).getByRole('radio',{name:value('skin_tone','porcelain'),exact:true}).click();
 for(const [aid,ids] of [['hair_color',['golden_blonde','platinum']],['scenery',['garden_path','library']]]){
  await categoryFor(aid); const region=page.getByRole('region',{name:attr(aid).name,exact:true});
  await region.getByRole('button',{name:'Vary',exact:true}).click();
  for(const id of ids) await region.getByRole('checkbox',{name:value(aid,id),exact:true}).click();
 }
 await page.getByLabel('Images',{exact:true}).fill('2');
 await page.getByLabel('Seed',{exact:false}).fill('42');
 await page.getByLabel('Your creative note',{exact:false}).fill('An adult woman in an opaque ivory tailored suit. Editorial natural daylight, full-length believable anatomy.');
 const previewWait=page.waitForResponse(r=>r.url().endsWith('/api/preview')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Preview prompt & plans'}).click();
 const preview=await(await previewWait).json(); assert.equal(preview.plans.length,2); assert.equal(preview.combination_count,4);
 for(const p of preview.plans){assert.deepEqual(p.selections.skin_tone,['porcelain']); assert.ok(['golden_blonde','platinum'].includes(p.selections.hair_color[0]));assert.ok(['garden_path','library'].includes(p.selections.scenery[0]));}
 await writeFile(new URL('real-variations-preview.json',output),JSON.stringify(preview,null,2));
 const submitWait=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Generate 2 images',exact:true}).click();
 const submitted=await submitWait; assert.equal(submitted.status(),202); const {id}=await submitted.json();
 const done=await page.waitForResponse(async r=>{if(!r.url().endsWith('/api/jobs/'+id))return false; return ['completed','partial','failed'].includes((await r.json()).status);},{timeout:600000});
 const job=await done.json(); await writeFile(new URL('real-variations-job.json',output),JSON.stringify(job,null,2));
 assert.equal(job.completed,2,JSON.stringify(job.errors));assert.equal(job.failed,0);assert.equal(job.results.length,2);
 for(const item of job.results){
  assert.deepEqual(item.selections.skin_tone,['porcelain']);assert.ok(['golden_blonde','platinum'].includes(item.selections.hair_color[0]));assert.ok(['garden_path','library'].includes(item.selections.scenery[0]));
  const dimensions=await page.evaluate(async url=>{const image=new Image();image.src=url;await image.decode();return [image.naturalWidth,image.naturalHeight];},item.url);
  assert.deepEqual(dimensions,[item.width,item.height]);assert.ok(Math.abs(dimensions[0]/dimensions[1]-9/16)<.012);
  const response=await context.request.get(baseURL+item.url);assert.equal(response.status(),200);await writeFile(new URL(item.id+'.jpg',output),await response.body());
 }
 assert.notDeepEqual(job.results[0].selections,job.results[1].selections);
 await page.getByRole('tab',{name:'Gallery',exact:true}).click();
 for(const item of job.results)await page.getByRole('button',{name:'Open image '+item.id,exact:true}).waitFor();
 await page.screenshot({path:new URL('real-variations-gallery.png',output).pathname});
 // UI-driven gallery AND/OR filtering must return the generated selections, not just echoed request tags.
 await page.getByRole('button',{name:'Attribute filters'}).click();
 async function openFilter(aid){const detail=page.locator('details.filter-attribute').filter({has:page.locator('summary').filter({hasText:attr(aid).name})}).first(); if(await detail.count() && await detail.getAttribute('open')===null) await detail.locator('summary').click();}
 await openFilter('hair_color');
 for(const vid of ['golden_blonde','platinum']) await page.getByRole('checkbox',{name:attr('hair_color').name+': '+value('hair_color',vid),exact:true}).click();
 await openFilter('skin_tone');
 await page.getByRole('checkbox',{name:attr('skin_tone').name+': '+value('skin_tone','porcelain'),exact:true}).click();
 const galleryWait=page.waitForResponse(r=>r.url().includes('/api/gallery?')&&r.request().method()==='GET');
 await page.getByRole('button',{name:'Show matching images'}).click(); const filtered=await(await galleryWait).json();
 for(const item of job.results) assert.ok(filtered.items.some(x=>x.id===item.id));
 await page.screenshot({path:new URL('real-filtered-gallery.png',output).pathname});
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({evidence:'REAL headless UI provider generation + whitelist + locked values + dimensions + gallery filters',job_id:id,generated:job.results.map(x=>({id:x.id,width:x.width,height:x.height,selections:x.selections})),output:output.pathname},null,2));
} finally {await browser.close();}
