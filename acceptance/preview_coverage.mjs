// Exhaustive read-only production catalog audit. No interception or paid writes.
import {chromium} from '@playwright/test';
import {mkdir,readFile,writeFile,appendFile,stat} from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve(new URL('..',import.meta.url).pathname);
const output=path.resolve(process.env.COVERAGE_OUTPUT||path.join(root,'acceptance-output/preview-coverage'));
await mkdir(output,{recursive:true});
let base=process.env.STUDIO_BASE_URL||'http://localhost:8123',entry=base;
if(process.env.PHONE_STATE_FILE){const s=JSON.parse(await readFile(process.env.PHONE_STATE_FILE,'utf8'));base=s.origin;entry=base+'/access/'+s.token;}
const browser=await chromium.launch({args:['--no-sandbox']});
const widths=(process.env.COVERAGE_WIDTHS||'1440,390').split(',').map(Number);
const results=[];
let plan;try{plan=JSON.parse(await readFile(path.join(root,'docs/preview-coverage/inventory-plan.json'),'utf8'));}catch{}
const candidates=new Map((plan?.pending_items||[]).map(i=>[i.attribute+':'+i.value,i.legacy_candidates]));
try{for(const width of widths){
 const context=await browser.newContext({viewport:{width,height:width===390?844:1000}});const page=await context.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(entry,{waitUntil:'networkidle'});
 const library=await(await context.request.get(base+'/api/library')).json();
 if(library.categories.length!==12||library.categories.flatMap(c=>c.attributes).length!==129||library.categories.flatMap(c=>c.attributes.flatMap(a=>a.values)).length!==1596)throw Error('Unexpected production catalog cardinality');
 await writeFile(path.join(output,'catalog.json'),JSON.stringify(library,null,2));
 const rows=[];const network=new Map();
 async function inspect(locator,item){
  let exists=false; if(item.url){try{exists=(await stat(path.join(root,item.url.startsWith('/preview-atlases/')?'generated'+item.url.split('?')[0]:item.url.split('?')[0]))).isFile();}catch{}}
  let http=null;if(item.url){if(!network.has(item.url)){const response=await context.request.get(base+item.url);network.set(item.url,{status:response.status(),contentType:response.headers()['content-type']});}http=network.get(item.url);}
  const initial=await locator.count()?await locator.evaluate(e=>({visible:!!e.getClientRects().length,text:e.innerText})):null;
  if(await locator.count())await locator.scrollIntoViewIfNeeded();
  const image=locator.locator('img').first();let rendered=null;
  if(await image.count())rendered=await image.evaluate(async i=>{let decodeError=null;try{await i.decode();}catch(e){decodeError=e.message;}const r=i.getBoundingClientRect(),s=getComputedStyle(i);let pixelRange=null;try{const c=document.createElement('canvas');c.width=c.height=32;const x=c.getContext('2d');x.drawImage(i,0,0,32,32);const d=x.getImageData(0,0,32,32).data;let lo=255,hi=0;for(let j=0;j<d.length;j+=4){lo=Math.min(lo,d[j],d[j+1],d[j+2]);hi=Math.max(hi,d[j],d[j+1],d[j+2]);}pixelRange=hi-lo;}catch{}return {src:i.getAttribute('src'),naturalWidth:i.naturalWidth,naturalHeight:i.naturalHeight,decodeError,pixelRange,width:r.width,height:r.height,objectFit:s.objectFit,visible:r.width>0&&r.height>0&&r.top<innerHeight&&r.bottom>0&&r.left<innerWidth&&r.right>0&&s.visibility==='visible'&&s.display!=='none'&&Number(s.opacity)>0};});
  const intentional=['control_only','swatch'].includes(item.status);
  const presentation=await locator.count()?await locator.evaluate(e=>({text:e.innerText,visible:!!e.getClientRects().length,placeholders:e.querySelectorAll('.thumb-fallback').length,swatch:e.querySelector('.fabric-swatch')?getComputedStyle(e.querySelector('.fabric-swatch')).backgroundColor:null})):null;
  const failure=!presentation?.visible||(!intentional&&presentation.placeholders>0)||item.url&&(!rendered||rendered.src!==item.url||!rendered.visible||!rendered.naturalWidth||rendered.decodeError||rendered.pixelRange===null||rendered.pixelRange<=16||rendered.objectFit!=='contain'||http?.status!==200||!exists);
  return {...item,file_exists:exists,http,initial,presentation,rendered,error:failure?'item_not_visibly_rendered':null,classification:intentional?'intentionally_photoless':failure?'broken':item.url?'ready':'never_created_or_unmapped'};
 }
 for(const category of library.categories){
  const nav=page.locator('.category-nav button');
  const button=page.getByRole('button',{name:new RegExp('^\\d+\\s*'+category.name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'$')});
  if(!await button.isVisible()){await page.getByRole('button',{name:'Browse categories',exact:true}).click();}
  await button.click();
  for(const attr of category.attributes){
   const section=page.locator('#attribute-'+attr.id);await section.waitFor();
   const toggle=section.locator('.attribute-toggle');const collapsed=await toggle.getAttribute('aria-expanded')==='false';
   const status=['control_only','fabric_swatch'].includes(attr.preview_method)?attr.preview_method==='fabric_swatch'?'swatch':'control_only':attr.thumbnail_status||'pending';
   rows.push({...await inspect(toggle,{kind:'attribute',category:category.id,attribute:attr.id,status,source:attr.thumbnail_source||null,intended_type:attr.control||attr.preview_method||'contact_sheet',url:attr.thumbnail_url||null}),initially_collapsed:collapsed});
   if(collapsed)await toggle.click();
   while(await section.locator('.show-more').count())await section.locator('.show-more').click();
   for(const value of attr.values){
    const locator=attr.control==='range'?section.locator('.numeric-attribute'):attr.control==='select'?section.locator('option').filter({hasText:value.name}).first():section.locator('.value-card').filter({has:page.locator('strong',{hasText:new RegExp('^'+value.name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'$')})});
    // Native option visibility is represented by its containing select, not getClientRects on option.
    const target=attr.control==='select'?section.locator('.select-attribute'):locator;
    const row=await inspect(target,{kind:'value',category:category.id,attribute:attr.id,value:value.id,status:value.thumbnail_status||'pending',source:value.thumbnail_source||null,intended_type:value.thumbnail_kind||attr.control||attr.preview_method,url:value.thumbnail_url||null});
    row.control_option_exists=attr.control==='select'?await locator.count()>0:attr.control==='range'?attr.values.some(v=>v.id===value.id):null;
    row.legacy_candidates=candidates.get(attr.id+':'+value.id)||[];
    if(row.classification==='never_created_or_unmapped')row.classification=row.legacy_candidates.length?'existing_legacy_unmapped_review_required':'preview_never_created';
    rows.push(row);
   }
   if(process.env.COVERAGE_ATTRIBUTE_SCREENSHOTS==='1')await section.screenshot({path:path.join(output,width+'-attribute-'+attr.id+'.png'),timeout:60000});
  }
  await page.locator('#attribute-'+category.attributes[0].id).scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(output,width+'-'+category.id+'.png')});
  await writeFile(path.join(output,width+'-'+category.id+'.json'),JSON.stringify(rows.filter(r=>r.category===category.id),null,2));
 }
 const counts={};for(const r of rows)counts[r.kind+':'+r.classification]=(counts[r.kind+':'+r.classification]||0)+1;
 const result={width,origin:base,rows,counts,errors};results.push(result);await writeFile(path.join(output,width+'.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({width,counts,errors}));await context.close();
}}finally{await browser.close();}
await writeFile(path.join(output,'summary.json'),JSON.stringify(results.map(({rows,...r})=>r),null,2));
if(results.some(r=>r.rows.some(x=>x.error)||r.errors.length))process.exitCode=1;
