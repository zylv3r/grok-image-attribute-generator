import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Module, {createRequire} from 'node:module';
import ts from 'typescript';
const require = createRequire(import.meta.url);
function load(file) {
  const module = new Module(file);
  module.require = id => id === './types' ? load('src/types.ts') : require(id);
  module._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2022}}).outputText, file);
  return module.exports;
}
const lib = load('src/lib.ts');
const age = {id:'age', name:'Age',type:'exclusive',control:'range',range:{min:21,max:85,step:1}, values:Array.from({length:65},(_,i)=>({id:`age_${i+21}`,name:String(i+21),steers:''}))};
const active = {catalog_version:2,categories:[{id:'identity',name:'Identity',attributes:[age,{id:'gender',type:'exclusive',default:'woman',values:[{id:'woman',name:'Woman',steers:''}]}]}]};
test('numeric age maps only to bounded canonical discrete values',()=>{
  assert.equal(lib.rangeValueId(age,24),'age_24');
  for(const invalid of [20,86,24.5,NaN]) assert.equal(lib.rangeValueId(age,invalid),undefined);
});
test('v2 gender default is explicit while legacy drafts retain unset behavior',()=>{
  assert.deepEqual(lib.cleanDraft(null,active).selections,{gender:['woman']});
  assert.deepEqual(lib.cleanDraft(null,{categories:[]}).selections,{});
});
test('archive vocabulary and snapshots retain retired labels',()=>{
  const historic={categories:[{id:'old',name:'Old',attributes:[{id:'retired',name:'Historic attribute',values:[{id:'old',name:'Historic label'}]}]}]};
  assert.equal(lib.historyLibrary({...active,historical_library:historic}),historic);
  assert.equal(lib.imageDescription({selections:{retired:['old']},aspect_ratio:'1:1',selection_labels:{retired:{name:'Saved attribute',values:{old:'Saved value'}}}},active),'Saved value · 1:1');
});
test('comparison method labels distinguish simulated and independent examples',()=>{
  assert.match(lib.previewLabel({preview_method:'optical_simulation'}),/Simulated/i);
  assert.match(lib.previewLabel({thumbnail_source:'legacy_independent'}),/Independent/i);
});
