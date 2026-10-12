// Runs the actual dist UI. Every API in this suite is explicitly simulated; no provider.
import { test, expect, Page } from '@playwright/test';
import { mockAPI, library as legacyLibrary, guide } from './fixtures';
import type { Library } from '../types';
import type { ComparisonArtifact, ComparisonReviewData, Point } from '../comparisons';
const baseId = 'a'.repeat(32), outputId = 'b'.repeat(32), contractHash = 'c'.repeat(64);
const url = (id: string) => `/api/comparisons/assets/${id}.png`;
const reviewLibrary: Library = { catalog_version: 2, categories: [
  {id: 'hair', name: 'Hair', attributes: [
    {id: 'hair_color', name: 'Hair Colour', type: 'exclusive', preview_method: 'masked_recolor', preview_scope: 'localized', comparison_group: 'hair:hair_color', values: [{id: 'brown', name: 'Brown', steers: 'brown', colour: {hex: '#654321'}}]},
    {id: 'hair_cut', name: 'Hair Cut', type: 'exclusive', preview_method: 'reference_edit', preview_scope: 'localized', comparison_group: 'hair:hair_cut', values: [{id: 'bob', name: 'Bob', steers: 'bob'}]},
  ]},
  {id: 'photography', name: 'Photography', attributes: [{id: 'grain', name: 'Grain', type: 'exclusive', preview_method: 'simulated_grain', preview_scope: 'global', comparison_group: 'photography:same_scene', values: [{id: 'fine', name: 'Fine', steers: 'fine grain'}]}]},
]};
function initial(category: string, attribute: string, group: string): ComparisonReviewData {
  return { category_id: category, group, attributes: [{id: attribute}], state: 'draft', contract_hash: contractHash, baseline: { asset_id: baseId, url: url(baseId), sha256: 'd'.repeat(64), width: 400, height: 260, subject_id: 'woman-1' }, masks: {}, artifacts: [], published_artifact_ids: [], cycle: {id: 0, cap: 0, used: 0}, budget: {cap: 0, used: 0, cycle_id: 0, cycle_used: 0}, locked_fields: ['identity','non_target_traits'], allowed_changes: ['selected target inside approved footprint'] };
}
async function comparisonFixture(page: Page, options: { initialMask?: boolean; missingBase?: boolean; failPreview?: boolean } = {}) {
  await page.context().route('**/*', route => route.abort('blockedbyclient'));
  await mockAPI(page);
  const reviews = new Map<string, ComparisonReviewData>();
  for (const category of reviewLibrary.categories) for (const attr of category.attributes)
    reviews.set(attr.id, initial(category.id, attr.id, attr.comparison_group!));
  const hair = reviews.get('hair_color')!;
  if (options.initialMask) hair.masks.hair_color = {polygon: [[.1,.1],[.5,.1],[.5,.5]], sha256: 'e'.repeat(64)};
  if (options.missingBase) hair.baseline = null;
  const posts: {path: string; body: Record<string, unknown>}[] = [];
  const reads: string[] = [];
  const galleryPages: number[] = [];
  await page.route('**/api/library', route => route.fulfill({json: reviewLibrary}));
  await page.route('**/api/catalog/versions', route => route.fulfill({json: {active_version: 2, legacy_version: 1, library: reviewLibrary, historical_library: legacyLibrary}}));
  await page.route('**/api/gallery?*', route => {
    const pageNumber = Number(new URL(route.request().url()).searchParams.get('page')); galleryPages.push(pageNumber);
    return route.fulfill({json: {items: [{id: `owned-${pageNumber}`, url: guide, thumbnail_url: guide, width: 400, height: 260, selections: {}, aspect_ratio: '3:2', prompt: 'Simulated owned image', created_at: 'fixture'}], page: pageNumber, page_size: 12, total: 2, pages: 2}});
  });
  await page.route('**/api/comparisons/**', async route => {
    const request = route.request(), requestURL = new URL(request.url()), path = requestURL.pathname;
    if (request.method() === 'GET' && [url(baseId), url(outputId)].includes(path)) return route.fulfill({body: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="260"><rect width="400" height="260" fill="#aab98a" /></svg>'), contentType: 'image/svg+xml'});
    if (request.method() === 'GET' && path === '/api/comparisons/categories') return route.fulfill({json: {categories: reviewLibrary.categories.map(c => ({id: c.id, state: c.attributes.every(a => reviews.get(a.id)!.state === 'published') ? 'published' : 'draft', groups: Object.fromEntries(c.attributes.map(a => [a.comparison_group, {state: reviews.get(a.id)!.state}]))}))}});
    const match = /^\/api\/comparisons\/([^/]+)(?:\/(base|mask|approve|preview))?$/.exec(path);
    if (!match) return route.fulfill({status: 404, json: {error: 'Unexpected simulated comparison route'}});
    const [, category, action] = match;
    if (request.method() === 'GET' && !action) {
      const review = reviews.get(requestURL.searchParams.get('attribute_id') || '');
      if (!review || review.category_id !== category) return route.fulfill({status: 422, json: {error: 'Missing or mismatched selected attribute'}});
      reads.push(path + requestURL.search);
      return route.fulfill({json: review});
    }
    if (request.method() !== 'POST' || !action) return route.fulfill({status: 405, json: {error: 'Unexpected simulated comparison method'}});
    const body = request.postDataJSON() as Record<string, unknown>; posts.push({path, body});
    const review = reviews.get(String(body.attribute_id));
    if (!review || review.category_id !== category || body.group !== review.group) return route.fulfill({status: 422, json: {error: 'Selected group does not match this fixture contract'}});
    if (action === 'base') {
      expect(review.state).toBe('draft');
      review.baseline = { ...initial(category, String(body.attribute_id), review.group!).baseline!, image_id: String(body.image_id), crop: body.crop, sha256: '9'.repeat(64) };
      review.masks = {}; review.artifacts = []; review.contract_hash = '8'.repeat(64);
    } else if (action === 'mask') {
      expect(review.state).toBe('draft');
      const polygon = body.polygon as Point[];
      if (polygon.length) review.masks[String(body.attribute_id)] = {polygon, sha256: 'e'.repeat(64)}; else delete review.masks[String(body.attribute_id)];
      review.contract_hash = '7'.repeat(64);
    } else if (action === 'approve') {
      expect(body.expected_contract_hash).toBe(review.contract_hash);
      const ids = body.artifact_ids as string[];
      expect(Array.isArray(ids)).toBe(true);
      expect(ids.every(id => review.artifacts.some(a => a.id === id))).toBe(true);
      if (body.stage === 'contract') {
        expect(review.state).toBe('draft'); expect(ids).toEqual([]);
        expect(body.provider_attempt_cap).toBe(0);
        review.state = 'contract_approved'; review.cycle = {id: 1, cap: 0, used: 0}; review.budget = {...review.budget, cycle_id: 1};
      } else if (body.stage === 'pilot') {
        expect(['contract_approved', 'pilot_done', 'pilot_accepted']).toContain(review.state);
        expect(ids.length).toBeGreaterThan(0);
        review.state = 'pilot_accepted'; review.artifacts.forEach(a => { if (ids.includes(a.id)) a.accepted = true; });
      } else if (body.stage === 'publish') {
        expect(review.state).toBe('pilot_accepted'); expect(ids.length).toBeGreaterThan(0);
        expect(ids.every(id => review.artifacts.some(a => a.id === id && a.accepted))).toBe(true);
        review.state = 'published'; review.published_artifact_ids = [...ids];
      } else return route.fulfill({status: 422, json: {error: 'Unexpected fixture approval stage'}});
    } else if (action === 'preview') {
      expect(review.state).not.toBe('published');
      expect(body.method).not.toBe('reference_edit');
      if (options.failPreview) return route.fulfill({status: 422, json: {error: 'Target effect is empty: unchanged masked pixels'}});
      const artifact: ComparisonArtifact = {id: outputId, url: url(outputId), base_url: review.baseline!.url, attribute_id: String(body.attribute_id), value_id: String(body.value_id), method: String(body.method), receipt: {status: 'staged', base_sha256: review.baseline!.sha256, output_sha256: 'f'.repeat(64), outside_mask_changed_pixels: 0, method_version: 'simulated-fixture'}, accepted: false};
      review.artifacts.push(artifact); if (review.state === 'contract_approved') review.state = 'pilot_done';
      return route.fulfill({json: artifact});
    }
    return route.fulfill({json: review});
  });
  await page.goto('/?workspace=comparisons');
  await expect(page.getByRole('heading', {name: 'Category review', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Hair', exact: true})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Original baseline · hair:hair_color', exact: true})).toBeVisible();
  return {posts, reviews, galleryPages, reads};
}

test('normalized mask drawing, manual point edits and category drafts survive responsive resizing', async ({page}) => {
  const {posts} = await comparisonFixture(page);
  const svg = page.getByRole('application', {name: 'Hair Colour normalized polygon mask'});
  for (const [index,x,y] of [[1,.1,.1],[2,.5,.1],[3,.5,.5]]) {
    await svg.scrollIntoViewIfNeeded();
    const box = await svg.boundingBox(); expect(box).not.toBeNull();
    await page.mouse.click(box!.x + x * box!.width, box!.y + y * box!.height);
    await expect(page.getByRole('spinbutton', {name: `Point ${index} X`})).toBeVisible();
  }
  expect(await page.getByRole('spinbutton', {name: 'Point 1 X'}).inputValue().then(Number)).toBeCloseTo(.1, 2);
  for (const [index, x, y] of [[1,'.1','.1'],[2,'.5','.1'],[3,'.5','.5']]) { await page.getByRole('spinbutton', {name: `Point ${index} X`}).fill(String(x)); await page.getByRole('spinbutton', {name: `Point ${index} Y`}).fill(String(y)); }
  await page.getByRole('spinbutton', {name: 'Point 1 X'}).fill('0.125');
  await page.setViewportSize({width: 390, height: 844});
  await expect(page.getByRole('spinbutton', {name: 'Point 1 X'})).toHaveValue('0.125');
  await page.getByRole('navigation', {name: 'Review categories'}).getByRole('button', {name: /Photography/}).click();
  await page.getByRole('navigation', {name: 'Review categories'}).getByRole('button', {name: /Hair/}).click();
  await expect(page.getByRole('spinbutton', {name: 'Point 1 X'})).toHaveValue('0.125');
  await page.getByRole('button', {name: 'Save attribute mask', exact: true}).click();
  await expect.poll(() => posts.filter(p => p.path.endsWith('/mask')).length).toBe(1);
  expect(posts.find(p => p.path.endsWith('/mask'))).toEqual({path: '/api/comparisons/hair/mask', body: {attribute_id: 'hair_color', group: 'hair:hair_color', polygon: [[.125,.1],[.5,.1],[.5,.5]]}});
  await page.getByRole('button', {name: 'Remove saved mask', exact: true}).click();
  await expect.poll(() => posts.filter(p => p.path.endsWith('/mask')).length).toBe(2);
  expect(posts.filter(p => p.path.endsWith('/mask')).at(-1)!.body.polygon).toEqual([]);
  expect(posts.filter(p => p.path.endsWith('/preview'))).toHaveLength(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('approval is explicit and group bounded; local preview, receipt, slider, acceptance and publication use exact routes', async ({page}) => {
  const {posts, reviews, reads} = await comparisonFixture(page, {initialMask: true});
  await page.getByRole('button', {name: 'Review and approve contract', exact: true}).click();
  const dialog = page.getByRole('dialog', {name: 'Approve this review group contract', exact: true});
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/Billing notice/)).toBeVisible();
  await dialog.getByRole('spinbutton', {name: 'Provider attempt cap'}).fill('4');
  await expect(dialog.getByRole('button', {name: 'Approve contract only'})).toBeDisabled();
  await dialog.getByRole('spinbutton', {name: 'Provider attempt cap'}).fill('0');
  await dialog.getByRole('checkbox', {name: /I reviewed/}).check();
  await dialog.getByRole('button', {name: 'Approve contract only'}).click();
  await expect(dialog).toBeHidden();
  expect(posts.filter(p => p.path.endsWith('/preview'))).toHaveLength(0);
  expect(posts[0]).toEqual({path: '/api/comparisons/hair/approve', body: {stage: 'contract', attribute_id: 'hair_color', group: 'hair:hair_color', artifact_ids: [], approval_note: '', provider_attempt_cap: 0, expected_contract_hash: contractHash}});
  expect(reviews.get('hair_color')!.state).toBe('contract_approved');
  expect(reviews.get('hair_cut')!.state).toBe('draft');
  await expect(page.getByRole('button', {name: 'Publish selected group candidates', exact: true})).toBeDisabled();
  await page.getByRole('button', {name: 'Render one local draft candidate', exact: true}).click();
  await expect(page.getByText('Candidate staged for review. It is not published.', {exact: true})).toBeVisible();
  expect(posts.find(p => p.path.endsWith('/preview'))).toEqual({path: '/api/comparisons/hair/preview', body: {attribute_id: 'hair_color', group: 'hair:hair_color', value_id: 'brown', method: 'masked_recolor', params: {colour: {hex: '#654321'}}, request_key: expect.any(String)}});
  expect(posts.find(p => p.path.endsWith('/preview'))!.body.request_key).toEqual(expect.any(String));
  expect(reviews.get('hair_color')!.state).toBe('pilot_done');
  await page.getByLabel('Comparison view', {exact: true}).selectOption('slider');
  const slider = page.getByRole('slider', {name: 'After before comparison reveal'});
  await slider.focus(); await slider.press('End'); await slider.press('ArrowLeft'); await expect(slider).toHaveValue('99');
  await page.getByRole('button', {name: '2×', exact: true}).click();
  await expect(page.getByRole('button', {name: '2×', exact: true})).toHaveAttribute('aria-pressed', 'true');
  await page.getByText('Receipt for brown', {exact: true}).click();
  await expect(page.getByText(/outside_mask_changed_pixels/)).toBeVisible();
  await page.getByRole('checkbox', {name: 'Select hair_color: brown'}).check();
  await page.getByRole('button', {name: 'Accept selected candidates (1)', exact: true}).click();
  const accept = page.getByRole('dialog', {name: 'Accept reviewed group candidates', exact: true});
  await accept.getByRole('checkbox', {name: /I reviewed/}).check();
  await accept.getByRole('button', {name: 'Accept selected candidates', exact: true}).click();
  await expect(accept).toBeHidden();
  expect(reviews.get('hair_color')!.state).toBe('pilot_accepted');
  expect(reviews.get('hair_color')!.artifacts[0].accepted).toBe(true);
  expect(reviews.get('hair_color')!.published_artifact_ids).toEqual([]);
  await page.getByRole('button', {name: 'Publish selected group candidates', exact: true}).click();
  const publish = page.getByRole('dialog', {name: 'Publish selected group candidates', exact: true});
  await publish.getByRole('checkbox', {name: /I reviewed/}).check();
  await publish.getByRole('button', {name: 'Publish selected candidates', exact: true}).click();
  await expect(publish).toBeHidden();
  expect(posts.filter(p => p.path.endsWith('/approve')).slice(1)).toEqual(['pilot','publish'].map(stage => ({path: '/api/comparisons/hair/approve', body: {stage, attribute_id: 'hair_color', group: 'hair:hair_color', expected_contract_hash: contractHash, artifact_ids: [outputId], provider_attempt_cap: 0, approval_note: ''}})));
  expect(reviews.get('hair_color')!.state).toBe('published');
  expect(reviews.get('hair_color')!.published_artifact_ids).toEqual([outputId]);
  expect(reviews.get('hair_cut')!.state).toBe('draft');
  await expect(page.getByRole('navigation', {name: 'Review categories'}).getByRole('button', {name: /Hair/})).toContainText('1/2 groups published');
  expect(posts.every(p => p.path.startsWith('/api/comparisons/hair/'))).toBe(true);
  await page.getByLabel('Target attribute', {exact: true}).selectOption('hair_cut');
  await expect(page.getByRole('heading', {name: 'Original baseline · hair:hair_cut', exact: true})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Request one reference edit'})).toBeDisabled();
  await expect(page.getByRole('button', {name: 'Review and approve contract', exact: true})).toBeEnabled();
  await expect(page.getByRole('checkbox', {name: 'Select hair_color: brown'})).toHaveCount(0);
  expect(reads).toContain('/api/comparisons/hair?attribute_id=hair_cut');
  expect(reviews.get('hair_cut')!.artifacts).toEqual([]);
  expect(posts.filter(p => p.path.endsWith('/preview'))).toHaveLength(1);
});

test('private owned gallery pagination, adult woman declaration and normalized baseline crop are explicit', async ({page}) => {
  const {posts, galleryPages} = await comparisonFixture(page, {missingBase: true});
  await page.getByRole('button', {name: 'Choose gallery baseline'}).click();
  const dialog = page.getByRole('dialog', {name: 'Choose the original woman baseline'});
  await dialog.getByRole('button', {name: 'Next gallery page'}).click();
  await dialog.getByRole('radio').check();
  await expect(dialog.getByRole('button', {name: 'Use owned baseline'})).toBeDisabled();
  await dialog.getByRole('checkbox', {name: /declare the baseline/}).check();
  await dialog.getByRole('checkbox', {name: /Use a fixed crop/}).check();
  for (const [name,value] of [['left','0.1'],['top','0.2'],['right','0.9'],['bottom','0.8']]) await dialog.getByRole('spinbutton', {name: `Baseline crop ${name}`}).fill(value);
  await dialog.getByRole('button', {name: 'Use owned baseline'}).click();
  await expect(dialog).toBeHidden();
  expect(galleryPages).toEqual([1,2]);
  expect(posts[0]).toEqual({path:'/api/comparisons/hair/base', body: {image_id:'owned-2', subject_id:'woman-1', crop:[.1,.2,.9,.8], attribute_id: 'hair_color', group: 'hair:hair_color'}});
  expect(posts.filter(p => p.path.endsWith('/preview'))).toHaveLength(0);
});

test('draft local errors remain visible, reference edits are gated, and approval cancellation restores focus', async ({page}) => {
  const {posts} = await comparisonFixture(page, {initialMask: true, failPreview: true});
  const approve = page.getByRole('button', {name: 'Review and approve contract', exact:true});
  await approve.click();
  await page.getByRole('dialog').getByRole('button', {name:'Cancel', exact:true}).click();
  await expect(approve).toBeFocused();
  await page.getByRole('button', {name:'Render one local draft candidate', exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Target effect is empty');
  await page.getByLabel('Target attribute').selectOption('hair_cut');
  await expect(page.getByRole('button', {name:'Request one reference edit'})).toBeDisabled();
  await expect(page.getByText('Reference edit requires an approved contract.', {exact:true})).toBeVisible();
  expect(posts.filter(p => p.path.endsWith('/preview'))).toHaveLength(1);
  expect(posts.filter(p => p.path.endsWith('/approve'))).toHaveLength(0);
});

test('changing the target value resets prior overrides to its own catalog pigment', async ({page}) => {
  const attr = reviewLibrary.categories[0].attributes[0];
  const original = attr.values;
  attr.values = [...original, {id:'copper', name:'Copper', steers:'copper pigment', colour:{hex:'#b4673d'}}];
  try {
    const {posts} = await comparisonFixture(page, {initialMask:true});
    const rgb = page.getByRole('textbox', {name:'Target fabric / pigment RGB'});
    await rgb.fill('#112233');
    await page.getByRole('combobox', {name: /^Target value/}).selectOption('copper');
    await expect(rgb).toHaveValue('#b4673d');
    await page.getByRole('button', {name:'Render one local draft candidate',exact:true}).click();
    await expect.poll(() => posts.filter(p=>p.path.endsWith('/preview')).length).toBe(1);
    expect(posts.find(p=>p.path.endsWith('/preview'))!.body.params).toEqual({colour:{hex:'#b4673d'}});
  } finally { attr.values = original; }
});
