// Offline stage payloads and actual component handlers; no sockets or providers.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Module, { createRequire } from 'node:module';
import ts from 'typescript';

const require = createRequire(import.meta.url);
function load(file, overrides = {}, extra = '') {
  const mod = new Module(file);
  mod.require = id => id.endsWith('.css') ? {} : id in overrides ? overrides[id] : require(id);
  mod._compile(ts.transpileModule(fs.readFileSync(file, 'utf8') + extra, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText, file);
  return mod.exports;
}
const comparisons = load('src/comparisons.ts');
const { approvalPayload } = comparisons;
const hash = 'c'.repeat(64), candidate = 'b'.repeat(32), stale = 'f'.repeat(32);
const artifact = { id: candidate, url: '/candidate.png', base_url: '/baseline.png', attribute_id: 'hair_cut', value_id: 'bob', method: 'reference_edit', receipt: {}, accepted: false };
function review(state = 'draft') {
  return { category_id: 'hair', group: 'hair:hair_cut', state, contract_hash: hash, baseline: { asset_id: 'a'.repeat(32), url: '/baseline.png', sha256: 'd'.repeat(64), width: 400, height: 260, subject_id: 'woman-1' }, masks: {}, artifacts: [{ ...artifact }], attributes: [{ id: 'hair_cut' }], baseline_requirements: ['Operator reviewed the immutable original.'], budget: { cap: 0, used: 0 }, locked_fields: ['identity'], allowed_changes: ['hair cut'] };
}

for (const [stage, state] of [['contract', 'draft'], ['expansion', 'pilot_accepted'], ['expansion', 'published']]) {
  test(`${stage} from ${state} ignores both checked candidates and stale selection`, () => {
    const r = review(state);
    for (const selected of [[], [candidate], [stale], [candidate, stale]]) {
      const before = structuredClone(r), ids = [...selected];
      assert.deepEqual(approvalPayload(r, stage, ids, 3, '  Reviewed this exact cycle. \n'), {
        stage, group: 'hair:hair_cut', expected_contract_hash: hash, artifact_ids: [], provider_attempt_cap: 3, approval_note: 'Reviewed this exact cycle.',
      });
      assert.deepEqual(r, before);
      assert.deepEqual(ids, selected);
    }
  });
}

test('pilot and publish send only explicit reviewed selection with exact stage/group/hash/note and zero cap', () => {
  const other = { ...artifact, id: 'e'.repeat(32), accepted: true };
  for (const stage of ['pilot', 'publish']) {
    const r = { ...review('pilot_accepted'), artifacts: [{ ...artifact, accepted: true }, other] };
    const ids = [other.id, candidate];
    assert.deepEqual(approvalPayload(r, stage, ids, 3, ' \tReviewed targets.\n'), {
      stage, group: 'hair:hair_cut', expected_contract_hash: hash, artifact_ids: ids, provider_attempt_cap: 0, approval_note: 'Reviewed targets.',
    });
    assert.throws(() => approvalPayload(r, stage, [], 0, ''), /Select at least one reviewed candidate/);
    assert.throws(() => approvalPayload(r, stage, [candidate, stale], 0, ''), /All candidates must belong to this category/);
  }
  // Acceptance itself is allowed for an unaccepted candidate; publication is not.
  assert.deepEqual(approvalPayload(review('pilot_done'), 'pilot', [candidate], 0, '').artifact_ids, [candidate]);
  assert.throws(() => approvalPayload(review('pilot_accepted'), 'publish', [candidate], 0, ''), /Publication requires accepted category candidates/);
});

test('all stages retain their exact state gates', () => {
  const allowed = { contract: ['draft'], pilot: ['contract_approved', 'pilot_done', 'pilot_accepted'], publish: ['pilot_accepted'], expansion: ['pilot_accepted', 'published'] };
  for (const stage of Object.keys(allowed)) for (const state of ['draft', 'contract_approved', 'pilot_done', 'pilot_accepted', 'published']) {
    const r = review(state); r.artifacts[0].accepted = true;
    const action = () => approvalPayload(r, stage, [candidate], 0, 'Reviewed');
    if (allowed[stage].includes(state)) assert.doesNotThrow(action, `${stage}/${state}`);
    else assert.throws(action, /already been approved|before accepting|Publication requires|previous pilot/, `${stage}/${state}`);
  }
});

test('all stages retain cap validation and baseline/hash prerequisites', () => {
  for (const [stage, state] of [['contract', 'draft'], ['pilot', 'pilot_done'], ['publish', 'pilot_accepted'], ['expansion', 'published']]) {
    const r = review(state); r.artifacts[0].accepted = true;
    for (const cap of [-1, 4, .5, NaN, Infinity, '1', true]) assert.throws(() => approvalPayload(r, stage, [candidate], cap, 'Reviewed'), /integer from 0 to 3/);
    for (const cap of [0, 1, 2, 3]) assert.equal(approvalPayload(r, stage, [candidate], cap, 'Reviewed').provider_attempt_cap, ['contract', 'expansion'].includes(stage) ? cap : 0);
    for (const missing of [{ baseline: null }, { contract_hash: '' }]) assert.throws(() => approvalPayload({ ...r, ...missing }, stage, [stale], 0, 'Reviewed'), /Choose a baseline and review the current contract first/);
  }
});

test('expansion requires a trimmed nonempty note; empty notes on other stages remain valid', () => {
  for (const note of ['', ' \t\n']) assert.throws(() => approvalPayload(review('published'), 'expansion', [stale], 0, note), /expansion approval note is required/);
  for (const [stage, state] of [['contract', 'draft'], ['pilot', 'pilot_done'], ['publish', 'pilot_accepted']]) {
    const r = review(state); r.artifacts[0].accepted = true;
    assert.equal(approvalPayload(r, stage, [candidate], 0, ' \t\n').approval_note, '');
  }
});

test('compatibility reviews omit group; current review hash and group are forwarded exactly', () => {
  const r = review(); delete r.group;
  assert.deepEqual(approvalPayload(r, 'contract', [stale], 0, ''), { stage: 'contract', expected_contract_hash: hash, artifact_ids: [], provider_attempt_cap: 0, approval_note: '' });
  const changed = { ...r, group: 'hair:hair_length', contract_hash: '9'.repeat(64) };
  assert.deepEqual(approvalPayload(changed, 'contract', [stale], 1, 'reviewed'), { stage: 'contract', group: changed.group, expected_contract_hash: changed.contract_hash, artifact_ids: [], provider_attempt_cap: 1, approval_note: 'reviewed' });
});

// Minimal hook fixture executes the real CategoryReview event handlers, including
// its unchanged selection persistence across pilot acceptance and expansion.
function categoryHarness(api) {
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
  const jsx = (type, props) => ({ type, props: props || {} });
  const lib = load('src/lib.ts', { './types': load('src/types.ts') });
  const { CategoryReview } = load('src/components/Comparisons.tsx', {
    react: hooks, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'fragment' },
    '@radix-ui/react-dialog': Object.fromEntries(['Root', 'Portal', 'Overlay', 'Content', 'Title', 'Description', 'Close'].map(name => [name, `Dialog.${name}`])),
    '../comparisons': comparisons, '../lib': { ...lib, api }, './UI': { ErrorNotice: 'ErrorNotice' },
  }, '\nexport { CategoryReview };');
  const props = { categoryId: 'hair', name: 'Hair', attributes: [{ id: 'hair_cut', name: 'Hair Cut', type: 'exclusive', comparison_group: 'hair:hair_cut', preview_method: 'reference_edit', values: [{ id: 'bob', name: 'Bob' }] }], drafts: new Map(), onStateChange() {} };
  const render = () => {
    do { dirty = false; cursor = 0; tree = CategoryReview(props); } while (dirty);
    while (pending.length) pending.shift()();
    return dirty ? render() : tree;
  };
  return { render };
}
function nodes(tree) {
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  return tree && typeof tree === 'object' ? [tree, ...nodes(tree.props.children)] : [];
}
function content(tree) {
  if (Array.isArray(tree)) return tree.map(content).join('');
  return tree && typeof tree === 'object' ? content(tree.props.children) : tree === false || tree == null ? '' : String(tree);
}
function find(h, predicate) { const node = nodes(h.render()).find(predicate); assert.ok(node, 'Expected component control exists'); return node; }
const tick = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };

test('UI fixture accepts a checked pilot then approves expansion without forwarding its retained selection', async () => {
  let current = review('pilot_done');
  const posts = [];
  const h = categoryHarness(async (path, options) => {
    if (options?.method !== 'POST') return structuredClone(current);
    const body = JSON.parse(options.body); posts.push({ path, body });
    assert.equal(path, '/api/comparisons/hair/approve');
    if (body.stage === 'pilot') {
      assert.deepEqual(body, { stage: 'pilot', group: 'hair:hair_cut', attribute_id: 'hair_cut', expected_contract_hash: hash, artifact_ids: [candidate], provider_attempt_cap: 0, approval_note: 'Inspected at 2x.' });
      current = { ...current, state: 'pilot_accepted', artifacts: [{ ...artifact, accepted: true }] };
    } else {
      // Enforce the engine's empty-selection contract in this simulated API.
      assert.deepEqual(body, { stage: 'expansion', group: 'hair:hair_cut', attribute_id: 'hair_cut', expected_contract_hash: hash, artifact_ids: [], provider_attempt_cap: 2, approval_note: 'One further cycle.' });
      current = { ...current, state: 'contract_approved', budget: { cap: 2, used: 1 } };
    }
    return structuredClone(current);
  });
  h.render(); await tick();
  const checkbox = () => find(h, n => n.type === 'input' && n.props.type === 'checkbox');
  const button = text => find(h, n => n.type === 'button' && content(n).startsWith(text));
  const dialog = () => find(h, n => typeof n.type === 'function' && n.type.name === 'ApprovalDialog');
  checkbox().props.onChange({ target: { checked: true } });
  button('Accept selected candidates').props.onClick();
  assert.equal(dialog().props.stage, 'pilot');
  await dialog().props.onApprove(3, ' Inspected at 2x. ');
  assert.equal(checkbox().props.checked, true);
  assert.equal(button('Approve another bounded expansion cycle').props.disabled, false);
  button('Approve another bounded expansion cycle').props.onClick();
  assert.equal(dialog().props.stage, 'expansion');
  assert.deepEqual(dialog().props.artifactIds, [candidate]);
  await dialog().props.onApprove(2, ' One further cycle. ');
  assert.equal(posts.length, 2);
  assert.equal(checkbox().props.checked, true);
  assert.equal(dialog().props.stage, null);
  assert.match(content(h.render()), /New bounded expansion cycle approved/);
});
