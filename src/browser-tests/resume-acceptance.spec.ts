import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import type { Library } from '../types';
import type { ComparisonArtifact, ComparisonReviewData, Point } from '../comparisons';
import { mockAPI, guide, library as legacyLibrary } from './fixtures';

// Actual compiled UI, simulated installation only. No live socket or provider.
// Run with cwd containing a fresh dist/; Playwright's existing fixture serves it.
const baseId = 'a'.repeat(32), outputId = 'b'.repeat(32);
const contractHash = 'c'.repeat(64), baseHash = 'd'.repeat(64);
const assetURL = (id: string) => `/api/comparisons/assets/${id}.png`;
const catalog: Library = {
  catalog_version: 2,
  categories: [
    { id: 'hair', name: 'Hair', attributes: [
      { id: 'hair_color', name: 'Hair Colour', type: 'exclusive', preview_method: 'masked_recolor', preview_scope: 'localized', comparison_group: 'hair:hair_color', values: [
        { id: 'brown', name: 'Brown', steers: 'brown', colour: { hex: '#654321' } },
        { id: 'copper', name: 'Copper', steers: 'copper', colour: { hex: '#b4673d' } },
      ] },
      { id: 'hair_cut', name: 'Hair Cut', type: 'exclusive', preview_method: 'reference_edit', preview_scope: 'localized', comparison_group: 'hair:hair_cut', values: [{ id: 'bob', name: 'Bob', steers: 'bob' }] },
    ] },
    { id: 'photography', name: 'Photography', attributes: [
      { id: 'grain', name: 'Grain', type: 'exclusive', preview_method: 'simulated_grain', preview_scope: 'global', comparison_group: 'photography:same_scene', values: [{ id: 'fine', name: 'Fine', steers: 'fine grain' }, { id: 'coarse', name: 'Coarse', steers: 'coarse grain' }] },
    ] },
    { id: 'identity_controls', name: 'Age and gender', attributes: [
      { id: 'age', name: 'Age', type: 'exclusive', control: 'range', range: { min: 21, max: 85, step: 1 }, default: 'age_24', preview_method: 'control_only', preview_scope: 'generation_control_only', comparison_group: 'identity_controls:age', values: Array.from({ length: 65 }, (_, i) => ({ id: `age_${21 + i}`, name: `${21 + i} years`, steers: `adult age ${21 + i}` })) },
      { id: 'gender', name: 'Gender / presentation', type: 'exclusive', control: 'select', default: 'woman', preview_method: 'control_only', preview_scope: 'generation_control_only', comparison_group: 'identity_controls:gender', values: [{ id: 'woman', name: 'Woman', steers: 'adult woman' }, { id: 'man', name: 'Man', steers: 'adult man' }] },
    ] },
  ],
};
type RequestEvidence = { path: string; body: Record<string, unknown> };
function reviewFor(category: string, attribute: string, group: string): ComparisonReviewData {
  return {
    category_id: category, group, state: 'draft', contract_hash: contractHash,
    baseline: { asset_id: baseId, url: assetURL(baseId), sha256: baseHash, width: 400, height: 260, subject_id: 'woman-1' },
    masks: {}, artifacts: [], attributes: [{ id: attribute }],
    cycle: { id: 0, cap: 0, used: 0 }, budget: { cap: 0, used: 0, cycle_id: 0, cycle_used: 0 },
    locked_fields: ['identity', 'non_target_traits'], allowed_changes: ['selected target inside reviewed footprint'],
    history: [], approvals: [], attempts: [], published_artifact_ids: [],
  };
}
async function setup(page: Page, options: { state?: ComparisonReviewData['state']; mask?: boolean; custom?: boolean; missingBase?: boolean; failPreview?: boolean } = {}) {
  // Catch any unhandled request, including an accidental live/backend origin.
  await page.context().route('**/*', route => route.abort('blockedbyclient'));
  const api = await mockAPI(page);
  const posts: RequestEvidence[] = [], reads: string[] = [];
  const reviews = new Map<string, ComparisonReviewData>();
  for (const category of catalog.categories) for (const attr of category.attributes) {
    reviews.set(attr.id, reviewFor(category.id, attr.id, attr.comparison_group!));
  }
  const hair = reviews.get('hair_color')!;
  hair.state = options.state || 'draft';
  if (options.missingBase) hair.baseline = null;
  if (options.mask) hair.masks.hair_color = { polygon: [[.1, .1], [.8, .1], [.8, .8]], sha256: 'e'.repeat(64) };
  if (options.state === 'published' || options.state === 'pilot_accepted') {
    hair.cycle = { id: 1, cap: 1, used: 1 };
    hair.budget = { cap: 1, used: 1, cycle_id: 1, cycle_used: 1 };
    hair.artifacts = [{ id: outputId, url: assetURL(outputId), base_url: assetURL(baseId), attribute_id: 'hair_color', value_id: 'brown', method: 'masked_recolor', accepted: true, receipt: { status: 'staged', outside_mask_changed_pixels: 0, custom_override: !!options.custom, base_sha256: baseHash, output_sha256: 'f'.repeat(64) } }];
    if (options.state === 'published') hair.published_artifact_ids = [outputId];
  }
  await page.route('**/api/library', route => route.fulfill({ json: catalog }));
  await page.route('**/api/catalog/versions', route => route.fulfill({ json: { active_version: 2, legacy_version: 1, library: catalog, historical_library: legacyLibrary } }));
  await page.route('**/api/gallery?*', route => {
    const n = Number(new URL(route.request().url()).searchParams.get('page') || 1);
    return route.fulfill({ json: { items: [{ id: `owned-${n}`, url: guide, thumbnail_url: guide, width: 400, height: 260, selections: {}, aspect_ratio: '3:2', prompt: 'Simulated owned baseline', created_at: 'fixture' }], page: n, page_size: 12, total: 2, pages: 2 } });
  });
  await page.route('**/api/comparisons/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    if (request.method() === 'GET' && [assetURL(baseId), assetURL(outputId)].includes(path)) return route.fulfill({ body: decodeURIComponent(guide.split(',')[1]), contentType: 'image/svg+xml' });
    if (request.method() === 'GET' && path === '/api/comparisons/categories') return route.fulfill({ json: { categories: catalog.categories.map(c => ({ id: c.id, state: c.attributes.every(a => reviews.get(a.id)!.state === 'published') ? 'published' : 'draft', groups: Object.fromEntries(c.attributes.map(a => [a.comparison_group, { state: reviews.get(a.id)!.state }])) })) } });
    const match = /^\/api\/comparisons\/([^/]+)(?:\/(base|mask|reopen|approve|preview))?$/.exec(path);
    if (!match) return route.fulfill({ status: 404, json: { error: 'Unexpected fixture comparison route' } });
    const [, category, action] = match;
    if (request.method() === 'GET' && !action) {
      const attribute = url.searchParams.get('attribute_id'), group = url.searchParams.get('group');
      // Anchor validation reads by group alone; editor reads select an attribute.
      // When both selectors are supplied, neither may override a mismatch.
      const review = attribute !== null ? reviews.get(attribute) : [...reviews.values()].find(candidate => candidate.group === group);
      if (!review || review.category_id !== category || (group !== null && review.group !== group)) return route.fulfill({ status: 422, json: { error: 'Missing or mismatched selected attribute/group' } });
      reads.push(url.search);
      return route.fulfill({ json: review });
    }
    if (request.method() !== 'POST' || !action) return route.fulfill({ status: 405, json: { error: 'Unexpected fixture comparison method' } });
    const body = request.postDataJSON() as Record<string, unknown>;
    posts.push({ path, body });
    const review = reviews.get(String(body.attribute_id));
    if (!review || review.category_id !== category || body.group !== review.group) return route.fulfill({ status: 422, json: { error: 'Selected group does not match this fixture contract' } });
    if (action === 'base') {
      expect(review.state).toBe('draft');
      review.baseline = { ...reviewFor(category, String(body.attribute_id), review.group!).baseline!, image_id: String(body.image_id), sha256: '9'.repeat(64), crop: body.crop };
      review.masks = {}; review.artifacts = []; review.contract_hash = '8'.repeat(64);
    } else if (action === 'mask') {
      expect(review.state).toBe('draft');
      const polygon = body.polygon as Point[];
      if (polygon.length) review.masks[String(body.attribute_id)] = { polygon, sha256: 'e'.repeat(64) };
      else delete review.masks[String(body.attribute_id)];
      review.contract_hash = '7'.repeat(64);
    } else if (action === 'reopen') {
      expect(body.expected_contract_hash).toBe(review.contract_hash);
      expect(review.state).not.toBe('draft');
      expect(String(body.approval_note).trim()).not.toBe('');
      const previous = structuredClone(review);
      review.history = [...(review.history as unknown[]), { event: 'operator_reopen', data: { note: body.approval_note, expected_contract_hash: body.expected_contract_hash, previous } }, { event: 'reopened_contract_archived', data: previous }];
      review.state = 'draft'; review.artifacts = []; review.approvals = []; review.published_artifact_ids = []; review.contract_hash = '6'.repeat(64);
      review.budget = { ...review.budget, cap: 0 };
      review.cycle = { ...review.cycle!, cap: 0 };
    } else if (action === 'approve') {
      expect(body.expected_contract_hash).toBe(review.contract_hash);
      const ids = body.artifact_ids as string[];
      expect(Array.isArray(ids)).toBe(true);
      expect(ids.every(id => review.artifacts.some(a => a.id === id))).toBe(true);
      if (body.stage === 'contract' || body.stage === 'expansion') {
        expect(ids).toEqual([]);
        if (body.stage === 'contract') expect(review.state).toBe('draft');
        else {
          expect(['pilot_accepted', 'published']).toContain(review.state);
          expect(String(body.approval_note).trim()).not.toBe('');
        }
        expect(body.provider_attempt_cap).toBe(0);
        review.state = 'contract_approved';
        const id = (review.cycle?.id || 0) + 1, cap = Number(body.provider_attempt_cap);
        review.cycle = { id, cap, used: 0 };
        review.budget = { ...review.budget, cap, cycle_id: id, cycle_used: 0 };
      } else if (body.stage === 'pilot') {
        expect(['contract_approved', 'pilot_done', 'pilot_accepted']).toContain(review.state);
        expect(ids.length).toBeGreaterThan(0);
        review.state = 'pilot_accepted'; review.artifacts.forEach(a => { if (ids.includes(a.id)) a.accepted = true; });
      } else if (body.stage === 'publish') {
        expect(review.state).toBe('pilot_accepted'); expect(ids.length).toBeGreaterThan(0);
        expect(ids.every(id => review.artifacts.some(a => a.id === id && a.accepted))).toBe(true);
        review.state = 'published'; review.published_artifact_ids = [...ids];
      } else return route.fulfill({ status: 422, json: { error: 'Unexpected fixture approval stage' } });
    } else if (action === 'preview') {
      // Provider-capable methods are forbidden even in the simulated installation.
      expect(body.method).not.toBe('reference_edit');
      expect(review.state).not.toBe('published');
      if (options.failPreview) return route.fulfill({ status: 422, json: { error: 'Target effect is empty: unchanged masked pixels' } });
      const artifact: ComparisonArtifact = { id: outputId, url: assetURL(outputId), base_url: review.baseline!.url, attribute_id: String(body.attribute_id), value_id: String(body.value_id), method: String(body.method), accepted: false, receipt: { status: 'staged', base_sha256: review.baseline!.sha256, output_sha256: 'f'.repeat(64), outside_mask_changed_pixels: 0, custom_override: !!options.custom, method_version: 'simulated-browser-fixture' } };
      review.artifacts.push(artifact);
      if (review.state === 'contract_approved') review.state = 'pilot_done';
      return route.fulfill({ json: artifact });
    } else return route.fulfill({ status: 404, json: { error: 'Unexpected fixture mutation' } });
    return route.fulfill({ json: review });
  });
  await page.goto('/?workspace=comparisons');
  await expect(page.getByRole('heading', { name: 'Hair', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Original baseline · hair:hair_color', exact: true })).toBeVisible();
  return { api, posts, reads, reviews };
}
async function evidence(page: Page, name: string, posts: RequestEvidence[]) {
  const info = test.info();
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true });
  await info.attach('simulated-request-evidence', { body: JSON.stringify(posts, null, 2), contentType: 'application/json' });
}

test('resume: review fixture resolves exact group and rejects category or selector mismatches', async ({ page }) => {
  const { posts, reviews } = await setup(page);
  const read = (path: string) => page.evaluate(async path => {
    const response = await fetch(path);
    return { status: response.status, body: await response.json() };
  }, path);
  for (const query of ['attribute_id=hair_color', 'group=hair%3Ahair_color', 'attribute_id=hair_color&group=hair%3Ahair_color']) {
    expect(await read(`/api/comparisons/hair?${query}`)).toEqual({ status: 200, body: reviews.get('hair_color') });
  }
  expect(await read('/api/comparisons/hair?group=hair%3Ahair_cut')).toEqual({ status: 200, body: reviews.get('hair_cut') });
  for (const path of [
    '/api/comparisons/hair',
    '/api/comparisons/hair?group=',
    '/api/comparisons/hair?group=hair%3Ahair',
    '/api/comparisons/hair?group=photography%3Asame_scene',
    '/api/comparisons/photography?group=hair%3Ahair_color',
    '/api/comparisons/photography?attribute_id=hair_color',
    '/api/comparisons/hair?attribute_id=hair_color&group=hair%3Ahair_cut',
    '/api/comparisons/hair?attribute_id=hair_cut&group=hair%3Ahair_color',
    '/api/comparisons/hair?attribute_id=unknown&group=hair%3Ahair_color',
    '/api/comparisons/hair?attribute_id=&group=hair%3Ahair_color',
  ]) {
    const result = await read(path);
    expect(result.status, path).toBe(422);
    expect(result.body.error, path).toBe('Missing or mismatched selected attribute/group');
  }
  expect(posts).toHaveLength(0);
});

test('resume: keyboard mask addition, arrows, deletion, normalized save and removal', async ({ page }) => {
  const { posts } = await setup(page);
  for (const [i, x, y] of [[1, .1, .1], [2, .8, .1], [3, .8, .8]]) {
    await page.getByRole('button', { name: 'Add point', exact: true }).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('spinbutton', { name: `Point ${i} X` }).fill(String(x));
    await page.getByRole('spinbutton', { name: `Point ${i} Y` }).fill(String(y));
  }
  const point = page.getByRole('button', { name: /^Mask point 1,/ });
  await point.focus(); await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('spinbutton', { name: 'Point 1 X' })).toHaveValue('0.11');
  await expect(page.getByRole('spinbutton', { name: 'Point 1 Y' })).toHaveValue('0.11');
  await page.getByRole('button', { name: 'Add point', exact: true }).click();
  await page.getByRole('button', { name: /^Mask point 4,/ }).focus(); await page.keyboard.press('Delete');
  await expect(page.getByRole('spinbutton', { name: 'Point 4 X' })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('spinbutton', { name: 'Point 1 X' })).toHaveValue('0.11');
  await page.getByRole('button', { name: 'Save attribute mask', exact: true }).click();
  await expect.poll(() => posts.filter(p => p.path.endsWith('/mask')).length).toBe(1);
  expect(posts[0].body).toMatchObject({ attribute_id: 'hair_color', group: 'hair:hair_color', polygon: [[.11, .11], [.8, .1], [.8, .8]] });
  await page.getByRole('button', { name: 'Remove saved mask', exact: true }).click();
  await expect.poll(() => posts.filter(p => p.path.endsWith('/mask')).length).toBe(2);
  expect(posts[1].body.polygon).toEqual([]);
  expect(posts.filter(p => p.path.endsWith('/preview'))).toHaveLength(0);
  await evidence(page, 'keyboard-mask-mobile', posts);
});

test('resume: baseline picker declaration and invalid crop gate preserve group isolation', async ({ page }) => {
  const { posts, reviews, reads } = await setup(page, { missingBase: true });
  await page.getByRole('button', { name: 'Choose gallery baseline', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Choose the original woman baseline' });
  await dialog.getByRole('button', { name: 'Next gallery page' }).click();
  await expect(dialog.getByRole('radio')).toHaveValue('owned-2');
  await dialog.getByRole('radio').check();
  await expect(dialog.getByRole('button', { name: 'Use owned baseline' })).toBeDisabled();
  await dialog.getByRole('checkbox', { name: /declare the baseline/ }).check();
  await dialog.getByRole('checkbox', { name: /Use a fixed crop/ }).check();
  await dialog.getByRole('spinbutton', { name: 'Baseline crop right' }).fill('0');
  await expect(dialog.getByRole('button', { name: 'Use owned baseline' })).toBeDisabled();
  await expect(dialog.getByRole('alert')).toContainText('non-empty normalized crop');
  await dialog.getByRole('spinbutton', { name: 'Baseline crop right' }).fill('0.9');
  await dialog.getByRole('button', { name: 'Use owned baseline' }).click();
  await expect(dialog).toBeHidden();
  expect(posts[0]).toEqual({ path: '/api/comparisons/hair/base', body: { image_id: 'owned-2', subject_id: 'woman-1', crop: [0, 0, .9, 1], attribute_id: 'hair_color', group: 'hair:hair_color' } });
  await page.getByLabel('Target attribute', { exact: true }).selectOption('hair_cut');
  await expect(page.getByRole('heading', { name: 'Original baseline · hair:hair_cut', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Request one reference edit' })).toBeDisabled();
  expect(reviews.get('hair_cut')!.baseline!.sha256).toBe(baseHash);
  expect(reads).toContain('?attribute_id=hair_cut');
  expect(posts.filter(p => p.path.endsWith('/preview'))).toHaveLength(0);
  await evidence(page, 'isolated-baseline-groups', posts);
});

test('resume: explicit Reopen archives candidates and retains usage; bounded expansion starts no preview', async ({ page }) => {
  const { posts, reviews } = await setup(page, { state: 'published', mask: true });
  const originalArtifacts = structuredClone(reviews.get('hair_color')!.artifacts);
  const originalAttempts = structuredClone(reviews.get('hair_color')!.attempts);
  await expect(page.getByRole('button', { name: 'Change gallery baseline' })).toBeDisabled();
  await page.getByRole('button', { name: 'Approve another bounded expansion cycle', exact: true }).click();
  const expansion = page.getByRole('dialog', { name: 'Approve a bounded expansion cycle' });
  await expansion.getByRole('checkbox', { name: /I reviewed/ }).check();
  await expect(expansion.getByRole('button', { name: 'Approve expansion cycle only' })).toBeDisabled();
  await expansion.getByLabel('Approval note').fill('Review a second local cycle');
  await expansion.getByRole('spinbutton', { name: 'Provider attempt cap' }).fill('4');
  await expect(expansion.getByRole('button', { name: 'Approve expansion cycle only' })).toBeDisabled();
  await expansion.getByRole('spinbutton', { name: 'Provider attempt cap' }).fill('0');
  await expansion.getByRole('button', { name: 'Approve expansion cycle only' }).click();
  await expect(expansion).toBeHidden();
  expect(posts[0]).toEqual({ path: '/api/comparisons/hair/approve', body: { stage: 'expansion', attribute_id: 'hair_color', group: 'hair:hair_color', artifact_ids: [], provider_attempt_cap: 0, expected_contract_hash: contractHash, approval_note: 'Review a second local cycle' } });
  expect(reviews.get('hair_color')!.state).toBe('contract_approved');
  expect(reviews.get('hair_color')!.budget.used).toBe(1);
  expect(reviews.get('hair_color')!.cycle).toEqual({ id: 2, cap: 0, used: 0 });
  expect(reviews.get('hair_color')!.artifacts).toEqual(originalArtifacts);
  expect(posts.filter(p => p.path.endsWith('/preview'))).toHaveLength(0);
  await page.getByRole('button', { name: 'Reopen review group', exact: true }).click();
  const reopen = page.getByRole('dialog', { name: 'Reopen this review group' });
  await reopen.getByRole('checkbox', { name: /I reviewed/ }).check();
  await expect(reopen.getByRole('button', { name: 'Reopen group with note' })).toBeDisabled();
  await reopen.getByLabel('Approval note').fill('Revise the reviewed mask');
  await reopen.getByRole('button', { name: 'Reopen group with note' }).click();
  await expect(reopen).toBeHidden();
  await expect(page.getByRole('button', { name: 'Change gallery baseline' })).toBeEnabled();
  expect(posts[1]).toEqual({ path: '/api/comparisons/hair/reopen', body: { attribute_id: 'hair_color', group: 'hair:hair_color', expected_contract_hash: contractHash, approval_note: 'Revise the reviewed mask' } });
  const reopened = reviews.get('hair_color')!;
  expect(reopened.state).toBe('draft');
  expect(reopened.artifacts).toEqual([]);
  expect(reopened.published_artifact_ids).toEqual([]);
  expect(reopened.contract_hash).not.toBe(contractHash);
  expect(reopened.history).toEqual(expect.arrayContaining([expect.objectContaining({ event: 'operator_reopen', data: expect.objectContaining({ previous: expect.objectContaining({ artifacts: originalArtifacts }) }) })]));
  expect(reopened.budget).toEqual({ cap: 0, used: 1, cycle_id: 2, cycle_used: 0 });
  expect(reopened.cycle).toEqual({ id: 2, cap: 0, used: 0 });
  expect(reopened.attempts).toEqual(originalAttempts);
  await expect(page.getByRole('checkbox', { name: 'Select hair_color: brown' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Publish selected group candidates', exact: true })).toBeDisabled();
  await page.getByText('Category history and approvals', { exact: true }).click();
  await expect(page.locator('.comparison-evidence[open] pre')).toContainText('operator_reopen');
  expect(reviews.get('hair_cut')!.state).toBe('draft');
  expect(posts.filter(p => p.path.endsWith('/preview'))).toHaveLength(0);
  await evidence(page, 'explicit-cycle-reopen', posts);
});

test('resume: custom comparison disclosure, value parameter reset, before/after zoom and receipt', async ({ page }) => {
  const { posts } = await setup(page, { mask: true, custom: true });
  const colour = page.getByLabel('Target fabric / pigment RGB', { exact: true });
  await colour.fill('#112233');
  await page.getByRole('combobox', { name: /^Target value/ }).selectOption('copper');
  await expect(colour).toHaveValue('#b4673d');
  await colour.fill('#223344');
  await page.getByRole('button', { name: 'Render one local draft candidate', exact: true }).click();
  await expect(page.getByText('Candidate staged for review. It is not published.', { exact: true })).toBeVisible();
  expect(posts[0]).toEqual({ path: '/api/comparisons/hair/preview', body: { attribute_id: 'hair_color', group: 'hair:hair_color', value_id: 'copper', method: 'masked_recolor', params: { colour: { hex: '#223344' } }, request_key: expect.any(String) } });
  await expect(page.getByText(/Custom override · comparison only/)).toBeVisible();
  const panes = page.getByRole('region', { name: 'Baseline and candidate comparison', exact: true });
  await expect(panes.getByRole('img', { name: 'Before: original woman baseline', exact: true })).toHaveAttribute('src', assetURL(baseId));
  await expect(panes.getByRole('img', { name: 'After: selected controlled candidate', exact: true })).toHaveAttribute('src', assetURL(outputId));
  await panes.getByRole('button', { name: '2×', exact: true }).click();
  await expect(panes.getByRole('button', { name: '2×', exact: true })).toHaveAttribute('aria-pressed', 'true');
  const before = panes.getByRole('region', { name: 'Before image pan' });
  const after = panes.getByRole('region', { name: 'After image pan' });
  await before.evaluate(element => { element.scrollLeft = 60; element.scrollTop = 30; });
  await expect.poll(() => after.evaluate(e => e.scrollLeft)).toBe(60);
  await panes.getByLabel('Comparison view', { exact: true }).selectOption('slider');
  const slider = panes.getByRole('slider', { name: 'After before comparison reveal' });
  await slider.focus(); await slider.press('End'); await slider.press('ArrowLeft');
  await expect(slider).toHaveValue('99');
  await page.getByText('Receipt for copper', { exact: true }).click();
  await expect(page.locator('.comparison-evidence[open] pre')).toContainText('outside_mask_changed_pixels');
  await evidence(page, 'comparison-zoom-receipt', posts);
  await panes.getByLabel('Comparison view', { exact: true }).selectOption('before');
  await expect(panes.getByRole('img')).toHaveAttribute('src', assetURL(baseId));
  await panes.getByLabel('Comparison view', { exact: true }).selectOption('after');
  await expect(panes.getByRole('img')).toHaveAttribute('src', assetURL(outputId));
  await panes.getByRole('button', { name: '1×', exact: true }).click();
  await expect(panes.getByRole('button', { name: '1×', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('resume: optical parameter reset and same-scene/global assumptions are visible', async ({ page }) => {
  const { posts } = await setup(page);
  await page.getByRole('navigation', { name: 'Review categories' }).getByRole('button', { name: /Photography/ }).click();
  await expect(page.getByRole('heading', { name: 'Original baseline · photography:same_scene', exact: true })).toBeVisible();
  const amount = page.getByRole('spinbutton', { name: 'Grain amount' });
  await amount.fill('12');
  await page.getByRole('spinbutton', { name: 'Noise seed' }).fill('4');
  await page.getByRole('combobox', { name: /^Target value/ }).selectOption('coarse');
  await expect(amount).toHaveValue('');
  await expect(page.getByRole('spinbutton', { name: 'Noise seed' })).toHaveValue('');
  await amount.fill('7');
  await expect(page.getByText(/Optical effects are simulations/)).toBeVisible();
  await page.getByRole('button', { name: 'Render one local draft candidate', exact: true }).click();
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0]).toEqual({ path: '/api/comparisons/photography/preview', body: { attribute_id: 'grain', group: 'photography:same_scene', value_id: 'coarse', method: 'simulated_grain', params: { amount: 7 }, request_key: expect.any(String) } });
  await evidence(page, 'optics-params-reset', posts);
});

test('resume: preset saves comparison context and defaults; age/gender stay control only', async ({ page }) => {
  const { api, posts, reads } = await setup(page);
  await page.getByRole('button', { name: 'Use this anchor in preset', exact: true }).click();
  await page.getByRole('tab', { name: 'Studio', exact: true }).click();
  await page.getByRole('button', { name: 'Presets', exact: true }).click();
  await page.getByLabel('Name this direction').fill('Anchored resume defaults');
  await page.getByRole('button', { name: 'Save preset', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Preset saved');
  await page.getByRole('button', { name: 'Close presets' }).click();
  const saved = await page.evaluate(async () => (await (await fetch('/api/presets')).json()).presets[0]);
  expect(saved.draft.selections.gender).toEqual(['woman']);
  expect(saved.draft.comparison).toMatchObject({ category_id: 'hair', group: 'hair:hair_color', baseline_asset_id: baseId, contract_hash: contractHash, locked_fields: ['identity', 'non_target_traits'] });
  expect(reads).toContain('?group=hair%3Ahair_color');
  await page.getByRole('navigation', { name: 'Library categories' }).getByRole('button', { name: /Age and gender/ }).click();
  await expect(page.getByText(/Generation defaults for unset controls:.*Age: 24 years/)).toBeVisible();
  const age = page.getByRole('region', { name: 'Age', exact: true });
  const ageDial = age.getByRole('slider', { name: 'Age dial' });
  await ageDial.focus(); await ageDial.press('End');
  await expect(age.getByRole('spinbutton', { name: 'Age in years', exact: true })).toHaveValue('85');
  const gender = page.getByRole('region', { name: 'Gender / presentation', exact: true });
  await gender.getByRole('combobox', { name: 'Gender / presentation value' }).selectOption('man');
  await expect(age.locator('img')).toHaveCount(0); await expect(gender.locator('img')).toHaveCount(0);
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.at(-1)?.selections.age).toEqual(['age_85']);
  expect(api.previewPayloads.at(-1)?.selections.gender).toEqual(['man']);
  expect(api.jobPayloads).toHaveLength(0);
  await page.getByRole('tab', { name: 'Category review', exact: true }).click();
  await page.getByRole('navigation', { name: 'Review categories' }).getByRole('button', { name: /Age and gender/ }).click();
  await expect(page.getByText('This attribute is a control only; it has no model comparison render.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Render one local draft candidate' })).toBeDisabled();
  expect(posts).toHaveLength(0);
  await evidence(page, 'preset-anchor-control-only', posts);
});

test('resume: mobile axe reviews editor, baseline dialog, explicit approval and error state', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { posts } = await setup(page, { mask: true, failPreview: true });
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Change gallery baseline', exact: true }).click();
  const picker = page.getByRole('dialog', { name: 'Choose the original woman baseline' });
  await expect(picker.getByRole('radio')).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.keyboard.press('Escape'); await expect(picker).toBeHidden();
  const approve = page.getByRole('button', { name: 'Review and approve contract', exact: true });
  await approve.click();
  await expect(page.getByRole('dialog', { name: 'Approve this review group contract' })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.keyboard.press('Escape'); await expect(approve).toBeFocused();
  await page.getByRole('button', { name: 'Render one local draft candidate', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Target effect is empty');
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  expect(posts.filter(p => p.path.endsWith('/approve'))).toHaveLength(0);
  await evidence(page, 'mobile-review-error-axe', posts);
});
