// Real production mixed-mode regression; no API mocks, generation or saved mutations.
import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({args:['--no-sandbox']});
try{const page=await browser.newPage();await page.goto(process.env.STUDIO_BASE_URL||'http://localhost:8123');
 const library=await(await page.request.get(new URL('/api/library',page.url()).href)).json();assert.equal(library.thumbnail_mode,'mixed');
 const pending=page.locator('#attribute-hair_color');await pending.getByRole('button',{name:'Edit Hair Pigment',exact:true}).click();
 const failures=[];
 if(await pending.locator('.thumb-fallback').count())failures.push('Pending V2 photographs are presented as generic letter placeholders');
 if(!await page.getByRole('region',{name:'Photographic preview progress'}).count())failures.push('Mixed-mode production catalog hides ready/pending/intentional coverage and paused state');
 assert.equal(await page.getByRole('region',{name:'Photographic preview progress'}).getByText('919 pending · 16 swatches · 70 control-only',{exact:true}).count(),1);
 assert.equal(await page.locator('#attribute-hair_length [data-value="shaved"] .example-label').innerText(),'Legacy independent example');
 assert.deepEqual(failures,[]);console.log('PASS: actual mixed-mode pending/progress presentation');
}finally{await browser.close();}
