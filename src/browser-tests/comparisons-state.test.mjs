// Pure frontend comparison contracts. No HTTP or provider calls.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import Module from 'node:module';
import ts from 'typescript';
const file = new URL('../comparisons.ts', import.meta.url);
const module = new Module(file.pathname);
module._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, file.pathname);
const { normalizedPoint, validPolygon, previewBlocker, approvalPayload, methodLabel, comparisonParameters, draftKey, retainedEditorDraft, catalogColour, parseReview, isFabricReference } = module.exports;
const review = { category_id: 'hair', state: 'draft', contract_hash: 'contract-a', baseline: { asset_id: 'base', subject_id: 'woman-1' }, masks: {}, artifacts: [], budget: { cap: 0, used: 0 } };
test('mask drawing stores image coordinates, independent of rendered dimensions and constrained to the image', () => {
  assert.deepEqual(normalizedPoint(150, 250, { left: 50, top: 50, width: 200, height: 400 }), [.5, .5]);
  assert.deepEqual(normalizedPoint(250, 450, { left: 50, top: 50, width: 400, height: 800 }), [.5, .5]);
  assert.deepEqual(normalizedPoint(-10, 1000, { left: 0, top: 0, width: 100, height: 100 }), [0, 1]);
  assert.equal(normalizedPoint(1, 1, { left: 0, top: 0, width: 0, height: 10 }), null);
});
test('mask validation rejects missing, nonfinite, duplicate and degenerate polygons', () => {
  assert.equal(validPolygon([[0,0],[1,0],[1,1]]), true);
  for (const points of [[], [[0,0],[1,1]], [[0,0],[.5,.5],[1,1]], [[0,0],[1,0],[NaN,1]], [[0,0],[1,0],[1,0]], [[0,0],[2,0],[1,1]]]) assert.equal(validPolygon(points), false);
});
test('draft deterministic previews work, paid previews require explicit approved masks and remaining category budget', () => {
  assert.equal(previewBlocker(review, 'hair_color', 'masked_recolor'), null);
  assert.equal(previewBlocker({ ...review, baseline: null }, 'color', 'fabric_swatch'), null);
  assert.match(previewBlocker(review, 'hair_style', 'reference_edit'), /approved contract/);
  const approved = { ...review, state: 'contract_approved', budget: { cap: 1, used: 0 } };
  assert.match(previewBlocker(approved, 'hair_style', 'reference_edit'), /saved mask/);
  const masked = { ...approved, masks: { hair_style: { polygon: [[0,0],[1,0],[1,1]] } } };
  assert.equal(previewBlocker(masked, 'hair_style', 'reference_edit'), null);
  assert.match(previewBlocker({ ...masked, budget: { cap: 1, used: 1 } }, 'hair_style', 'reference_edit'), /exhausted/);
  assert.match(previewBlocker({ ...masked, state: 'published' }, 'hair_style', 'reference_edit'), /published/);
  assert.match(previewBlocker(review, 'gender', 'control_only'), /control/);
});
test('operator acceptance binds exact category contract and explicit artifact IDs; paid cap never exceeds three', () => {
  const withArtifacts = { ...review, state: 'pilot_done', artifacts: [{ id: 'a', accepted: false }, { id: 'b', accepted: false }] };
  assert.deepEqual(approvalPayload(review, 'contract', [], 2, 'Reviewed mask'), { stage: 'contract', expected_contract_hash: 'contract-a', artifact_ids: [], provider_attempt_cap: 2, approval_note: 'Reviewed mask' });
  assert.deepEqual(approvalPayload(withArtifacts, 'pilot', ['a'], 0, '' ).artifact_ids, ['a']);
  assert.throws(() => approvalPayload(review, 'contract', [], 4, ''), /0.*3/);
  assert.throws(() => approvalPayload(withArtifacts, 'pilot', [], 0, ''), /candidate/);
  assert.throws(() => approvalPayload(withArtifacts, 'pilot', ['other-category'], 0, ''), /category/);
  assert.throws(() => approvalPayload(review, 'publish', [], 0, ''), /accepted/);
});
test('simulated optics are explicitly labelled, supported parameter values are typed, local drafts retain attribute identity', () => {
  assert.match(methodLabel('simulated_fov'), /simulated/i);
  assert.match(methodLabel('reference_edit'), /reference/i);
  assert.deepEqual(comparisonParameters('masked_recolor', { rgb: '#aabbcc' }), { colour: { hex: '#aabbcc' } });
  assert.deepEqual(comparisonParameters('grain', { amount: '0.2', seed: '11' }), { amount: .2, seed: 11 });
  assert.throws(() => comparisonParameters('grain', { amount: 'bad' }), /number/);
  assert.notEqual(draftKey('hair', 'color'), draftKey('eyes', 'color'));
});

test('cached mask drafts are source-bound; catalog RGB and synthetic references retain honest provenance', () => {
  const cached = { base_sha256: 'original', polygon: [[0,0],[1,0],[1,1]], params: {}, method: 'masked_recolor', value: 'red' };
  assert.equal(retainedEditorDraft(cached, 'original'), cached);
  assert.equal(retainedEditorDraft(cached, 'replaced'), undefined);
  assert.equal(catalogColour({ colour: { hex: '#AaBbCc' } }), '#aabbcc');
  assert.equal(catalogColour({ rgb: [1,2,255] }), '#0102ff');
  assert.equal(catalogColour({ color: 'red' }), null);
  const synthetic = { subject_id: 'fabric-swatch', subject_metadata: { presentation: 'no_person' } };
  assert.equal(isFabricReference(synthetic), true);
  assert.match(previewBlocker({ ...review, baseline: synthetic, state: 'contract_approved', budget: { cap: 1, used: 0 } }, 'hair_cut', 'reference_edit'), /adult woman/);
  assert.throws(() => parseReview(null, 'hair'), /invalid category/);
  assert.throws(() => parseReview({ state: 'contrived-approved' }, 'hair'), /invalid category/);
});
