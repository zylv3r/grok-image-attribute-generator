// REAL isolated staging UI/API acceptance; no API interception and no new vendor calls.
import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const base=process.env.STUDIO_BASE_URL||'http://127.0.0.1:8126';
const out=new URL('../acceptance-output/anchored-v2-live/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(base);await page.getByRole('heading',{name:'A vision, in the details.'}).waitFor();
 const library=await(await page.request.get(base+'/api/library')).json();const attrs=library.categories.flatMap(c=>c.attributes);const attr=id=>attrs.find(a=>a.id===id);
 assert.equal(library.catalog_version,2);assert.equal(library.categories.length,12);assert.ok(attr('hair_color').values.length>=44);assert.ok(attr('pose').values.length>=150);
 for(const retired of ['ethnic_inspiration','complexion_detail','facial_balance','face_direction'])assert.ok(!attr(retired));
 const nav=page.getByRole('navigation',{name:'Library categories'});
 const identity=library.categories.find(c=>c.attributes.some(a=>a.id==='age'));await nav.getByRole('button',{name:new RegExp(identity.name)}).click();
 const age=page.getByRole('region',{name:attr('age').name,exact:true});await age.getByRole('slider').fill('35');await age.getByRole('spinbutton',{name:'Age in years',exact:true}).fill('36');
 assert.equal(await age.locator('img').count(),0);await page.getByRole('button',{name:'Preview prompt & plans'}).click();await page.getByLabel('Prompt preview').waitFor();
 const wardrobe=library.categories.find(c=>c.attributes.some(a=>a.id==='fabric_color'));await nav.getByRole('button',{name:new RegExp(wardrobe.name)}).click();
 const fabric=page.getByRole('region',{name:attr('fabric_color').name,exact:true});const header=fabric.getByRole('button',{name:'Edit '+attr('fabric_color').name});if(await header.getAttribute('aria-expanded')==='false')await header.click();
 assert.equal(await fabric.locator('img').count(),0);assert.ok(await fabric.locator('.fabric-swatch').count()>0);
 await page.getByRole('tab',{name:'Category review',exact:true}).click();await page.getByRole('heading',{name:'Category review',exact:true}).waitFor();
 const hair=library.categories.find(c=>c.id==='hair');await page.getByRole('navigation',{name:'Review categories'}).getByRole('button',{name:new RegExp(hair.name)}).click();await page.getByLabel('Target attribute').selectOption('hair_color');await page.getByRole('heading',{name:'Original baseline · hair:hair_color',exact:true}).waitFor();
 await page.getByRole('button',{name:/^(Choose gallery baseline|Change gallery baseline)$/}).click();const dialog=page.getByRole('dialog',{name:'Choose the original woman baseline'});await dialog.getByRole('radio').first().check();await dialog.getByRole('checkbox',{name:/declare the baseline/}).check();const confirmations=dialog.getByRole('checkbox',{name:/confirm this image and its fixed crop/});if(await confirmations.count())await confirmations.check();await dialog.getByRole('button',{name:'Use owned baseline'}).click();await dialog.waitFor({state:'hidden'});
 await page.getByLabel('Target attribute').selectOption('hair_color');const removeMask=page.getByRole('button',{name:'Remove saved mask',exact:true});if(await removeMask.isEnabled()){await removeMask.click();await page.getByText('Attribute mask removed.',{exact:true}).waitFor();}await page.getByRole('button',{name:'Clear draft mask',exact:true}).click();
 const polygon=[['0.22','0.18'],['0.35','0.18'],['0.34','0.26'],['0.2','0.28']];
 for(let i=0;i<polygon.length;i++){await page.getByRole('button',{name:'Add point',exact:true}).click();await page.getByRole('spinbutton',{name:'Point '+(i+1)+' X'}).fill(polygon[i][0]);await page.getByRole('spinbutton',{name:'Point '+(i+1)+' Y'}).fill(polygon[i][1]);}
 await page.getByRole('button',{name:'Save attribute mask',exact:true}).click();await page.getByText('Saved mask hash and coordinates',{exact:true}).waitFor();
 await page.getByRole('textbox',{name:'Target fabric / pigment RGB'}).fill('#9d5535');
 const waited=page.waitForResponse(r=>r.url().endsWith('/api/comparisons/hair/preview')&&r.request().method()==='POST');await page.getByRole('button',{name:'Render one local draft candidate',exact:true}).click();const response=await waited;const artifact=await response.json();assert.equal(response.status(),200,JSON.stringify(artifact));assert.ok(artifact.url);assert.equal(artifact.receipt.outside_delta,0);assert.ok(artifact.receipt.target_changed_pixels>0);assert.equal(artifact.accepted,false);assert.equal(artifact.receipt.group,'hair:hair_color');assert.equal(artifact.receipt.custom_override,true);
 await page.getByLabel('Comparison view',{exact:true}).selectOption('slider');await page.getByRole('slider',{name:'After before comparison reveal'}).fill('65');await page.getByRole('button',{name:'2×',exact:true}).click();
 const png=await page.request.get(base+artifact.url);assert.equal(png.status(),200);assert.match(png.headers()['content-type'],/image\/png/);
 const checks=[];for(const width of [1440,390]){await page.setViewportSize({width,height:1000});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);const axe=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();checks.push({width,overflow,violations:axe.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))});await page.screenshot({path:new URL(width+'.png',out).pathname});}
 const review=await(await page.request.get(base+'/api/comparisons/hair?attribute_id=hair_color&group=hair%3Ahair_color')).json();assert.equal(review.state,'draft');assert.equal(review.budget.used,0);
 const report={evidence:'REAL compiled v2 staging UI with owned actual photo, no routes or provider calls, small QA mask not category approval',categories:library.categories.length,attributes:attrs.length,values:attrs.reduce((n,a)=>n+a.values.length,0),hair_colors:attr('hair_color').values.length,pose_options:attr('pose').values.length,artifact,review_state:review.state,provider_calls:0,checks,errors};await writeFile(new URL('report.json',out),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,artifact:{id:artifact.id,outside_delta:artifact.receipt.outside_delta,target_changed_pixels:artifact.receipt.target_changed_pixels}},null,2));
 assert.deepEqual(errors,[]);assert.ok(checks.every(c=>!c.overflow&&!c.violations.length));
}finally{await browser.close();}
