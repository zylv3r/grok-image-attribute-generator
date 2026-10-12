import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import Module, { createRequire } from 'node:module';
const root = process.cwd(), require = createRequire(path.join(root, 'package.json'));
const ts = require('typescript'), cache = new Map();
function sourceModule(file) {
  const absolute = path.resolve(root, file);
  if (cache.has(absolute)) return cache.get(absolute);
  const code = ts.transpileModule(fs.readFileSync(absolute,'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const module = new Module(absolute); module.filename = absolute;
  module.require = id => {
    if (id.endsWith('.css')) return {};
    if (!id.startsWith('.')) return require(id);
    const base = path.resolve(path.dirname(absolute), id);
    const next = [base, `${base}.ts`, `${base}.tsx`].find(item => fs.existsSync(item) && fs.statSync(item).isFile());
    if (!next) throw Error(`Missing ${id}`);
    return sourceModule(next);
  };
  module._compile(code,absolute); cache.set(absolute,module.exports); return module.exports;
}
const { resolveMigration } = sourceModule('src/components/MigrationReview.tsx');
const library = { categories: [{ id:'age', name:'Age', attributes: [{ id:'age', name:'Age', type:'exclusive', values:[{id:'age_24', name:'24', steers:'24'}]}] }] };
const raw = { selections: { age:['24'], retired:['lost'] }, whitelist:{}, mode:'single', n:1, aspect_ratio:'9:16', extra_prompt:'Keep me', future:{saved:true} };
const source = { name:'Original', draft:raw, schemaVersion:1 };
const resolved = { selections:{age:['age_24']}, whitelist:{}, mode:'single', n:1, aspect_ratio:'9:16', extra_prompt:'Keep me' };
test('uses exact resolve endpoint with original raw draft, retains unresolved, archive unchanged', async () => {
  const before = JSON.stringify(raw), calls=[];
  globalThis.fetch = async (url,init) => { calls.push({url,init}); return new Response(JSON.stringify({draft:resolved,changes:[{from:'24',to:'age_24'}],unresolved:[{attribute_id:'retired',reason:'retired'}]}),{status:200}); };
  const result = await resolveMigration(source,library);
  assert.equal(calls[0].url,'/api/catalog/resolve'); assert.equal(calls[0].init.method,'POST');
  assert.deepEqual(JSON.parse(calls[0].init.body),{draft:raw});
  assert.deepEqual(result.draft.selections,{age:['age_24']}); assert.equal(result.legacy,false);
  assert.equal(result.changes.length,1); assert.equal(result.unresolved.length,1);
  assert.equal(JSON.stringify(raw),before);
});
test('404 legacy fallback preserves explicit unresolved review without changing archive', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({error:'No catalog resolver'}),{status:404});
  const result = await resolveMigration(source,library);
  assert.equal(result.legacy,true); assert.ok(result.unresolved.some(field => field.includes('retired')));
  assert.ok(result.unresolved.some(field => field.includes('future')));
  assert.deepEqual(raw.selections.age,['24']);
});
test('service failures block application; invalid response is not treated as resolution', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({error:'Review offline'}),{status:503});
  await assert.rejects(resolveMigration(source,library),/Review offline/);
  globalThis.fetch = async () => new Response(JSON.stringify({draft:resolved,changes:'bad',unresolved:[]}),{status:200});
  await assert.rejects(resolveMigration(source,library),/unreadable catalog resolution/);
});
test('unsupported resolver response fields surface rather than vanish silently',async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({draft:{...resolved, unknown_future:{kept:true}},changes:[],unresolved:[]}),{status:200});
  const result = await resolveMigration(source,library);
  assert.ok(result.unresolved.some(field => field.includes('unknown_future')));
});
const { archivedGalleryState } = sourceModule('src/components/Gallery.tsx');
test('historical gallery IDs survive initial active-library load and late historical vocabulary', () => {
  const search = new URLSearchParams({gallery_filters:JSON.stringify({retired:['lost'],age:['24']})}).toString();
  assert.deepEqual(archivedGalleryState(search,library).filters,{retired:['lost'],age:['24']});
  assert.deepEqual(archivedGalleryState(search,{categories:[]}).filters,{retired:['lost'],age:['24']});
  assert.deepEqual(archivedGalleryState('gallery_filters=bad-json',library).filters,{});
});
test('supported legacy record has no unresolved fields and uses installed vocabulary',async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({error:'Missing'}),{status:404});
  const result = await resolveMigration({name:'Valid legacy',draft:resolved,schemaVersion:1},library);
  assert.equal(result.legacy,true); assert.deepEqual(result.unresolved,[]);
  assert.deepEqual(result.draft.selections,{age:['age_24']});
});
test('valid comparison anchor and lock metadata survives resolution while invalid metadata is disclosed', async () => {
  const comparison = {category_id:'age',baseline_asset_id:'a'.repeat(32),contract_hash:'b'.repeat(64),locked_fields:['subject','lighting']};
  globalThis.fetch = async () => new Response(JSON.stringify({draft:{...resolved,comparison},changes:[],unresolved:[]}),{status:200});
  let result = await resolveMigration(source,library);
  assert.deepEqual(result.draft.comparison,comparison); assert.deepEqual(result.unresolved,[]);
  globalThis.fetch = async () => new Response(JSON.stringify({draft:{...resolved,comparison:{...comparison,baseline_asset_id:'not-owned'}},changes:[],unresolved:[]}),{status:200});
  result = await resolveMigration(source,library);
  assert.equal(result.draft.comparison,undefined); assert.ok(result.unresolved.some(field => field.includes('comparison')));
});
