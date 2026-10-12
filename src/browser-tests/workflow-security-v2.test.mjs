import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Module from 'node:module';
import ts from 'typescript';
function load(name) { const file=new URL(`../${name}.ts`,import.meta.url);const mod=new Module(file.pathname);mod.require=(id)=>id==='./types'?load('types'):Module.createRequire(file)(id);mod._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file.pathname);return mod.exports; }
const c=load('comparisons'),lib=load('lib');
const r={category_id:'hair',group:'hair:color',state:'pilot_accepted',contract_hash:'a'.repeat(64),baseline:{asset_id:'b'.repeat(32),sha256:'c'.repeat(64),url:'/base',width:20,height:20},masks:{},artifacts:[],budget:{cap:1,used:9,cycle_used:0,cycle_id:3}};
test('reopen binds selected group and hash and requires a revision note',()=>{
 assert.throws(()=>c.reopenPayload(r,''),/note/);
 assert.deepEqual(c.reopenPayload(r,'Fix mask'),{group:'hair:color',expected_contract_hash:r.contract_hash,approval_note:'Fix mask'});
});
test('expansion approval requires accepted pilot and has its own bounded usage',()=>{
 const body=c.approvalPayload(r,'expansion',[],2,'Two more');assert.equal(body.provider_attempt_cap,2);assert.equal(body.group,'hair:color');
 assert.throws(()=>c.approvalPayload({...r,state:'pilot_done'},'expansion',[],1,'More'),/accept/i);
 assert.equal(c.previewBlocker({...r,masks:{color:{polygon:[[0,0],[1,0],[1,1]]}}},'color','reference_edit'),null);
});
test('selected group review cannot adopt another group identity',()=>{
 assert.throws(()=>c.parseReview(r,'hair','color','hair:cut'),/group/);
 assert.equal(c.parseReview(r,'hair',undefined,'hair:color').group,'hair:color');
});
test('preset comparison metadata must match current immutable base and contract',async()=>{
 const library={categories:[{id:'hair',attributes:[]}]};const anchor={category_id:'hair',baseline_asset_id:r.baseline.asset_id,contract_hash:r.contract_hash,locked_fields:['identity'],group:r.group};
 assert.equal(await lib.validateComparisonAnchor(anchor,library,async()=>r),true);
 assert.equal(await lib.validateComparisonAnchor(anchor,library,async()=>({...r,contract_hash:'d'.repeat(64)})),false);
 assert.equal(await lib.validateComparisonAnchor(anchor,library,async()=>({...r,baseline:{...r.baseline,asset_id:'e'.repeat(32)}})),false);
 assert.equal(await lib.validateComparisonAnchor(anchor,library,async()=>({...r,baseline_integrity:false})),false);
 assert.equal(await lib.validateComparisonAnchor(anchor,library,async()=>{throw Error('offline')}),false);
 assert.equal('comparison' in lib.generationPayload({...anchor,selections:{},whitelist:{},mode:'single',n:1,aspect_ratio:'9:16',extra_prompt:'',comparison:anchor}),false);
});
test('generation defaults are disclosed outside collapsed controls',()=>{
 const library={categories:[{attributes:[{id:'gender',name:'Gender',default:'woman',values:[{id:'woman',name:'Woman'}]},{id:'age',name:'Age',default:'age_24',values:[{id:'age_24',name:'24'}]}]}]};
 assert.deepEqual(lib.generationDefaults({selections:{age:['age_30']},whitelist:{}},library),['Gender: Woman']);
 assert.deepEqual(lib.generationDefaults({selections:{},whitelist:{gender:['man']}},library),['Age: 24']);
});
