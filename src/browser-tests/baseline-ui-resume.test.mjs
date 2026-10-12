// Socket-free component transitions. Chromium coverage lives in the sibling spec.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Module, { createRequire } from 'node:module';
import ts from 'typescript';
const require = createRequire(import.meta.url);
const jsx = (type, props) => ({ type, props: props || {} });
function load(file, overrides = {}, extra = '') {
  const mod = new Module(file);
  mod.require = id => id.endsWith('.css') ? {} : id in overrides ? overrides[id] : require(id);
  mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8') + extra, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText, file);
  return mod.exports;
}
const comparisons = load('src/comparisons.ts');
const lib = load('src/lib.ts', { './types': load('src/types.ts') });
// Hooks are driven through real component event handlers; no duplicate UI logic.
function harness(file, exported, props, api = async () => ({})) {
  let cursor = 0, dirty = false, tree;
  const slots = [], pending = [];
  const hooks = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
      return [slots[index], value => { const next = typeof value === 'function' ? value(slots[index]) : value; if (!Object.is(next, slots[index])) { slots[index] = next; dirty = true; } }];
    },
    useRef(initial) { const index = cursor++; return slots[index] ||= { current: initial }; },
    useEffect(effect, deps) {
      const index = cursor++, previous = slots[index];
      if (!previous || deps.some((value, i) => !Object.is(value, previous.deps[i]))) {
        slots[index] = { deps, cleanup: previous?.cleanup };
        pending.push(() => { slots[index].cleanup?.(); slots[index].cleanup = effect(); });
      }
    },
  };
  const extraExports = file.includes('Comparisons.tsx') ? '\nexport { CategoryReview, GalleryBaseline, ApprovalDialog };' : '';
  const components = load(file, { react: hooks, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'fragment' }, '@radix-ui/react-dialog': Object.fromEntries(['Root', 'Portal', 'Overlay', 'Content', 'Title', 'Description', 'Close'].map(name => [name, `Dialog.${name}`])), '../comparisons': comparisons, '../lib': { ...lib, api }, './UI': { ErrorNotice: 'ErrorNotice' } }, extraExports);
  const render = () => { do { dirty = false; cursor = 0; tree = components[exported](props); } while (dirty); while (pending.length) pending.shift()(); if (dirty) return render(); return tree; };
  return { render, update(next) { props = { ...props, ...next }; return render(); }, get tree() { return tree; } };
}
function nodes(tree) {
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  if (!tree || typeof tree !== 'object') return [];
  return [tree, ...nodes(tree.props.children)];
}
function content(tree) { if (Array.isArray(tree)) return tree.map(content).join(''); return tree && typeof tree === 'object' ? content(tree.props.children) : tree === false || tree == null ? '' : String(tree); }
function find(h, predicate) { const node = nodes(h.render()).find(predicate); assert.ok(node, 'Expected component control exists'); return node; }
const tick = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const requirements = ['Full garment visible in the fixed crop.', 'Neutral front pose; hands clear of waist.'];
const review = (id = 'waist', declared = requirements) => ({ category_id: 'body', group: `body:${id}`, state: 'draft', contract_hash: 'c'.repeat(64), baseline: { asset_id: 'a'.repeat(32), url: '/baseline.png', sha256: 'd'.repeat(64), width: 400, height: 260, subject_id: 'woman-1' }, masks: {}, artifacts: [], attributes: [{ id }], budget: { cap: 0, used: 0 }, locked_fields: [], allowed_changes: [], ...(declared === undefined ? {} : { baseline_requirements: declared }) });
const attr = { id: 'waist', name: 'Waist', type: 'exclusive', comparison_group: 'body:waist', preview_contract: { baseline_requirements: ['Catalog fallback only.'] }, preview_method: 'masked_recolor', preview_scope: 'localized', values: [{ id: 'narrow', name: 'Narrow', steers: 'narrow' }] };

test('selected review requirements are authoritative, exact and backward compatible', () => {
  assert.deepEqual(comparisons.baselineRequirements(review(), attr), requirements);
  assert.deepEqual(comparisons.baselineRequirements(review('waist', []), attr), []);
  const old = review(); delete old.baseline_requirements;
  assert.deepEqual(comparisons.baselineRequirements(old, attr), ['Catalog fallback only.']);
  assert.deepEqual(comparisons.baselinePayload('owned', [.1,.2,.9,.8], requirements, true), { image_id: 'owned', subject_id: 'woman-1', crop: [.1,.2,.9,.8], baseline_confirmations: requirements });
  assert.throws(() => comparisons.baselinePayload('owned', undefined, requirements, false), /confirm/i);
  assert.deepEqual(comparisons.baselinePayload('owned', undefined, [], false), { image_id: 'owned', subject_id: 'woman-1' });
  assert.throws(() => comparisons.parseReview({ ...review(), baseline_requirements: [42] }, 'body', 'waist', 'body:waist'), /requirements/i);
});

test('picker requires separate human constraints confirmation and resets on image, crop and group changes', async () => {
  const chosen = [];
  const h = harness('src/components/Comparisons.tsx', 'GalleryBaseline', { open: true, busy: false, error: '', group: 'body:waist', requirements, onOpenChange() {}, async onChoose(body) { chosen.push(body); } }, async () => ({ items: [{ id: 'owned', width: 400, height: 260 }, { id: 'other', width: 400, height: 260 }], pages: 1 }));
  h.render(); await tick();
  const radio = id => find(h, n => n.type === 'input' && n.props.type === 'radio' && n.props.value === id);
  const box = text => find(h, n => n.type === 'label' && content(n).includes(text)).props.children.find(n => n?.type === 'input');
  const use = () => find(h, n => n.type === 'button' && content(n) === 'Use owned baseline');
  radio('owned').props.onChange(); box('declare the baseline').props.onChange({ target: { checked: true } });
  assert.equal(use().props.disabled, true);
  assert.ok(content(h.tree).includes(requirements[0]));
  box('I confirm this image').props.onChange({ target: { checked: true } });
  assert.equal(use().props.disabled, false);
  box('Use a fixed crop').props.onChange({ target: { checked: true } });
  assert.equal(use().props.disabled, true);
  box('I confirm this image').props.onChange({ target: { checked: true } });
  use().props.onClick(); await tick();
  assert.deepEqual(chosen[0].baseline_confirmations, requirements);
  radio('other').props.onChange(); assert.equal(use().props.disabled, true);
  h.update({ group: 'body:hip', requirements: ['Hip contour visible.'] });
  assert.equal(use().props.disabled, true);
  assert.equal(content(h.tree).includes(requirements[0]), false);
});

test('approval displays actual group baseline requirements as human reviewed constraints', () => {
  const h = harness('src/components/Comparisons.tsx', 'ApprovalDialog', { stage: 'contract', review: review(), requirements, artifactIds: [], busy: false, error: '', onClose() {}, onApprove() {} });
  assert.ok(content(h.render()).includes(requirements[1]));
  assert.match(content(h.tree), /human|operator/i);
});

test('returning to the same group rejects its older mutation response', async () => {
  const oldMutation = deferred();
  const h = harness('src/components/Comparisons.tsx', 'CategoryReview', { categoryId: 'body', name: 'Body', attributes: [attr, { ...attr, id: 'hip', comparison_group: 'body:hip' }], drafts: new Map(), onStateChange() {} }, (path, options) => options?.method === 'POST' ? oldMutation.promise : Promise.resolve(review(new URL(path, 'https://local.invalid').searchParams.get('attribute_id'))));
  h.render(); await tick();
  const editor = () => find(h, n => typeof n.type === 'function' && n.type.name === 'AttributeEditor');
  const select = find(h, n => n.type === 'select').props.onChange;
  const mutation = editor().props.onSaveMask([[0,0],[1,0],[1,1]]);
  select({ target: { value: 'hip' } }); h.render(); await tick();
  select({ target: { value: 'waist' } }); h.render(); await tick();
  oldMutation.resolve({ ...review('waist'), contract_hash: '9'.repeat(64) }); await mutation;
  assert.equal(editor().props.review.contract_hash, 'c'.repeat(64));
  assert.equal(content(h.tree).includes('Attribute mask saved.'), false);
});

for (const failure of [false, true]) test(`prior group preview ${failure ? 'failure recovery' : 'result'} cannot replace a new group`, async () => {
  const pending = deferred(); let reads = 0;
  const h = harness('src/components/Comparisons.tsx', 'CategoryReview', { categoryId: 'body', name: 'Body', attributes: [attr, { ...attr, id: 'hip', comparison_group: 'body:hip' }], drafts: new Map(), onStateChange() {} }, (path, options) => {
    if (options?.method === 'POST') return failure ? Promise.reject(Error('Preview failed')) : pending.promise;
    const id = new URL(path, 'https://local.invalid').searchParams.get('attribute_id');
    if (failure && ++reads === 2) return pending.promise;
    return Promise.resolve(review(id));
  });
  h.render(); await tick();
  const editor = () => find(h, n => typeof n.type === 'function' && n.type.name === 'AttributeEditor');
  const select = find(h, n => n.type === 'select').props.onChange;
  const preview = editor().props.onPreview({ method: 'masked_recolor', value: 'narrow', params: {}, polygon: [] });
  await tick();
  select({ target: { value: 'hip' } }); h.render(); await tick();
  pending.resolve(failure ? review('waist') : { id: 'old-artifact', receipt: { status: 'staged' } });
  await preview;
  assert.equal(editor().props.review.group, 'body:hip');
  assert.equal(content(h.tree).includes('Candidate staged'), false);
  assert.equal(content(h.tree).includes('Preview failed'), false);
});

for (const failure of [false, true]) test(`prior group ${failure ? 'failure' : 'mutation'} cannot overwrite a rapid selection or clear its busy state`, async () => {
  const oldMutation = deferred(), currentMutation = deferred();
  let calls = 0;
  const h = harness('src/components/Comparisons.tsx', 'CategoryReview', { categoryId: 'body', name: 'Body', attributes: [attr, { ...attr, id: 'hip', name: 'Hip', comparison_group: 'body:hip' }], drafts: new Map(), onStateChange() {} }, (path, options) => options?.method === 'POST' ? (++calls === 1 ? oldMutation.promise : currentMutation.promise) : Promise.resolve(review(new URL(path, 'https://local.invalid').searchParams.get('attribute_id'))));
  h.render(); await tick();
  const selector = () => find(h, n => n.type === 'select');
  const editor = () => find(h, n => typeof n.type === 'function' && n.type.name === 'AttributeEditor');
  // Retain the old selection handler to model an already queued selection event.
  const queuedSelect = selector().props.onChange;
  const first = editor().props.onSaveMask([[0,0],[1,0],[1,1]]);
  assert.equal(selector().props.disabled, true);
  queuedSelect({ target: { value: 'hip' } }); h.render(); await tick();
  assert.equal(editor().props.attr.id, 'hip');
  assert.equal(editor().props.review.group, 'body:hip');
  const second = editor().props.onSaveMask([[0,0],[1,0],[1,1]]);
  if (failure) oldMutation.reject(Error('Old waist failure')); else oldMutation.resolve(review('waist'));
  await first; h.render();
  assert.equal(editor().props.review.group, 'body:hip');
  assert.equal(selector().props.disabled, true);
  assert.equal(content(h.tree).includes('Old waist failure'), false);
  assert.equal(content(h.tree).includes('Attribute mask saved.'), false);
  currentMutation.resolve(review('hip')); await second;
  assert.equal(selector().props.disabled, false);
});

const age = { id: 'age', name: 'Age', type: 'exclusive', range: { min: 21, max: 85, step: 1 }, default: 'age_24', values: Array.from({ length: 65 }, (_, i) => ({ id: `age_${21+i}`, name: `${21+i} years` })) };
function ageHarness() {
  let draft = { selections: {}, whitelist: {} };
  const h = harness('src/components/AttributeControls.tsx', 'RangeControl', { attr: age, draft, target: 'selections', ids: [], change(next) { draft = next; h.update({ draft, ids: draft.selections.age || [] }); } });
  return { h, get draft() { return draft; }, number: () => find(h, n => n.type === 'input' && n.props.type === 'number'), slider: () => find(h, n => n.type === 'input' && n.props.type === 'range'), status: () => content(find(h, n => n.props.id === 'numeric-status-age')) };
}
test('unset dial displays declared default without selecting it; Home and minimum click select canonical 21', () => {
  const a = ageHarness(); assert.equal(a.slider().props.value, 24); assert.deepEqual(a.draft.selections, {});
  a.slider().props.onKeyDown({ key: 'Home', preventDefault() {} }); assert.deepEqual(a.draft.selections.age, ['age_21']);
  find(a.h, n => n.type === 'button' && n.props['aria-label'] === 'Unset Age').props.onClick();
  a.slider().props.onPointerUp({ currentTarget: { value: '21' } }); assert.deepEqual(a.draft.selections.age, ['age_21']);
});
test('typing 3 then 35 does not flash invalid notices; valid commits retain draft and unset clears notice', () => {
  const a = ageHarness();
  a.number().props.onChange({ target: { value: '3' } }); assert.equal(a.status(), ''); assert.equal(a.number().props['aria-invalid'], false);
  a.number().props.onChange({ target: { value: '35' } }); assert.deepEqual(a.draft.selections.age, ['age_35']); assert.equal(a.number().props.value, '35');
  a.number().props.onChange({ target: { value: '035' } }); assert.equal(a.number().props.value, '035');
  a.number().props.onChange({ target: { value: '3' } }); a.number().props.onBlur(); assert.match(a.status(), /whole age/);
  find(a.h, n => n.type === 'button' && n.props['aria-label'] === 'Unset Age').props.onClick(); assert.equal(a.status(), ''); assert.equal(a.number().props.value, '');
  a.number().props.onChange({ target: { value: '3' } }); a.number().props.onBlur();
  a.number().props.onChange({ target: { value: '' } }); assert.equal(a.status(), ''); assert.deepEqual(a.draft.selections, {});
});
