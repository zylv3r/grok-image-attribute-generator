// Actual server/gateway preset persistence; isolated QA contexts, no generation.
import { chromium } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
const state=JSON.parse(await readFile(process.env.PHONE_STATE_FILE,'utf8'));
const name='QA_SHARED_PRESET_'+randomUUID();const base='http://localhost:8123';let id;
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const context=await browser.newContext();const page=await context.newPage();
const output=new URL('../acceptance-output/presets-live/',import.meta.url);await mkdir(output,{recursive:true});
try{
 await context.addInitScript(()=>{Storage.prototype.setItem=function(){throw new DOMException('QA storage denied','QuotaExceededError')};try{Object.defineProperty(crypto,'randomUUID',{value:undefined});}catch{}});
 await page.goto(base);await page.getByRole('heading',{name:'A vision, in the details.'}).waitFor();
 const lib=await(await page.request.get(base+'/api/library')).json();const hair=lib.categories.find(c=>c.id==='hair');const attr=hair.attributes.find(a=>a.id==='hair_color');const golden=attr.values.find(v=>v.id==='golden_blonde');
 await page.getByRole('navigation',{name:'Library categories'}).getByRole('button',{name:/Hair/}).click();await page.getByRole('region',{name:attr.name,exact:true}).getByRole('radio',{name:golden.name,exact:true}).click();
 await page.getByRole('button',{name:'Presets',exact:true}).click();await page.getByLabel('Name this direction').fill(name);await page.getByRole('button',{name:'Save preset',exact:true}).click();
 await page.getByRole('status').filter({hasText:'Preset saved on this studio.'}).waitFor();
 const stored=(await(await page.request.get(base+'/api/presets')).json()).presets.find(p=>p.name===name);assert.ok(stored);id=stored.id;assert.deepEqual(stored.draft.selections.hair_color,['golden_blonde']);
 await context.close();
 const phone=await browser.newContext({viewport:{width:390,height:844}});const mobile=await phone.newPage();
 await mobile.goto(state.origin+'/access/'+state.token,{timeout:60000});await mobile.getByRole('heading',{name:'A vision, in the details.'}).waitFor();await mobile.getByRole('button',{name:'Presets',exact:true}).click();await mobile.getByRole('button',{name:'Apply '+name,exact:true}).waitFor();
 await mobile.screenshot({path:new URL('saved-on-phone.png',output).pathname});
 const second=(await(await mobile.request.get(state.origin+'/api/presets')).json()).presets.find(p=>p.id===id);assert.deepEqual(second.draft,stored.draft);
 await mobile.getByRole('button',{name:'Apply '+name,exact:true}).click();
 const draft=await mobile.evaluate(()=>JSON.parse(localStorage.getItem('atelier.draft.v1')));assert.deepEqual(draft.selections.hair_color,['golden_blonde']);
 await mobile.getByRole('button',{name:'Presets',exact:true}).click();await mobile.getByRole('button',{name:'Delete '+name,exact:true}).click();await mobile.getByRole('status').filter({hasText:'Preset deleted from this studio.'}).waitFor();
 const final=await(await mobile.request.get(state.origin+'/api/presets')).json();assert.ok(!final.presets.some(p=>p.id===id));id=undefined;
 const report={source:'REAL localhost + authenticated HTTPS phone contexts; no interception or provider calls',saved_with_browser_storage_and_crypto_denied:true,fresh_phone_context_found_same_record:true,exact_draft_readback:true,apply_restored_hair_color:true,phone_delete_confirmed:true,qa_record_removed:true};
 await writeFile(new URL('report.json',output),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));await phone.close();
}finally{
 if(id){const cleanup=await browser.newContext();await cleanup.request.delete(base+'/api/presets/'+id,{headers:{Origin:base},data:{}});await cleanup.close();}
 await browser.close();
}
