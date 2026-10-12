import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import Module, {createRequire} from 'node:module';
import ts from 'typescript';
const require = createRequire(import.meta.url), cache = new Map();
function source(file) {
  const absolute = path.resolve(file);
  if (cache.has(absolute)) return cache.get(absolute);
  const module = new Module(absolute); module.filename = absolute;
  module.require = id => id === './types' ? source('src/types.ts') : require(id);
  module._compile(ts.transpileModule(fs.readFileSync(absolute, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText, absolute);
  cache.set(absolute, module.exports); return module.exports;
}
const lib = source('src/lib.ts');
const values = Array.from({length:65}, (_,i)=>({id:`age_${i+21}`,name:String(i+21),steers:`age ${i+21}`}));
const library = {catalog_version:2,categories:[{id:'identity',name:'Identity',attributes:[{id:'age',name:'Age',type:'exclusive',control:'range',range:{min:21,max:85,step:1},values},{id:'gender',name:'Gender',type:'exclusive',control:'select',default:'woman',values:[{id:'woman',name:'Woman',steers:'woman'},{id:'man',name:'Man',steers:'man'}]}]}]};
const anchor={category_id:'identity',baseline_asset_id:'a'.repeat(32),contract_hash:'b'.repeat(64),locked_fields:['identity','wardrobe']};
test('new v2 composition defaults to woman, explicit unset persists',()=>{
  assert.deepEqual(lib.cleanDraft(null,library).selections,{gender:['woman']});
  assert.deepEqual(lib.cleanDraft({selections:{}},library).selections,{});
});
test('generation sends only supported generation fields, never preset or UI metadata',()=>{
  const draft={...lib.cleanDraft(null,library),comparison:anchor,attributeModes:{age:'whitelist'},future:{private:'ui'}};
  assert.deepEqual(Object.keys(lib.generationPayload(draft)).sort(),['aspect_ratio','extra_prompt','mode','n','selections','whitelist']);
});
test('valid anchor locks survive preset cleaning, malformed extensions do not',()=>{
  assert.deepEqual(lib.cleanDraft({comparison:anchor},library).comparison,anchor);
  for(const invalid of [{...anchor,category_id:'absent'},{...anchor,baseline_asset_id:'../../private.jpg'},{...anchor,contract_hash:'unapproved'},{...anchor,locked_fields:[42]}]) assert.equal(lib.cleanDraft({comparison:invalid},library).comparison,undefined);
});
test('historical filters preserve retired IDs and archived original labels without changing active controls',()=>{
  const legacy={categories:[{id:'old',name:'Historic',attributes:[{id:'age',name:'Legacy Age',type:'exclusive',values:[{id:'24',name:'24 original',steers:'age 24'}]},{id:'retired',name:'Historic silhouette',type:'exclusive',values:[{id:'old',name:'Original shape',steers:'legacy'}]}]}]};
  const before=JSON.stringify(library), historical=lib.historicalLibrary(library,legacy);
  assert.equal(JSON.stringify(library),before);
  assert.deepEqual(lib.galleryState('?gallery_filters='+encodeURIComponent(JSON.stringify({age:['24'],retired:['old']})),historical).filters,{age:['24'],retired:['old']});
  assert.equal(lib.attributes(historical).find(a=>a.id==='age').values.find(v=>v.id==='24').name,'24 original');
});
test('all 65 ages survive bulk inversion and restoration with discrete IDs',()=>{
  const age=library.categories[0].attributes[0];
  let draft=lib.bulkVary(lib.cleanDraft(null,library),age,'all');
  assert.equal(draft.whitelist.age.length,65);
  assert.deepEqual(lib.cleanDraft(draft,library).whitelist.age,values.map(v=>v.id));
  draft=lib.bulkVary(draft,age,'inverse');
  assert.equal(draft.whitelist.age,undefined); assert.deepEqual(draft.selections,{gender:['woman']});
});
