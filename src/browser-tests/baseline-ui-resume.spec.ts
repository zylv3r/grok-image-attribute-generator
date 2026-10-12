import { test, expect, type Page } from '@playwright/test';
import type { Library } from '../types';
import type { ComparisonReviewData } from '../comparisons';
import { mockAPI, guide, library as legacyLibrary } from './fixtures';

// Parent builds dist and runs Chromium. All API responses here are simulated.
const requirements = ['Full garment visible in the fixed crop.', 'Neutral front pose; hands clear of waist.'];
const hipRequirements = ['Hip contour visible in the fixed crop.'];
const catalog: Library = { catalog_version: 2, categories: [
  { id: 'body', name: 'Body', attributes: [
    { id: 'waist', name: 'Waist', type: 'exclusive', comparison_group: 'body:waist', preview_method: 'masked_recolor', preview_scope: 'localized', preview_contract: { baseline_requirements: ['Catalog fallback only.'] }, values: [{ id: 'narrow', name: 'Narrow', steers: 'narrow', colour: { hex: '#654321' } }] },
    { id: 'hip', name: 'Hip', type: 'exclusive', comparison_group: 'body:hip', preview_method: 'masked_recolor', preview_scope: 'localized', preview_contract: { baseline_requirements: hipRequirements }, values: [{ id: 'wide', name: 'Wide', steers: 'wide' }] },
  ] },
  { id: 'identity', name: 'Age and gender', attributes: [
    { id: 'age', name: 'Age', type: 'exclusive', control: 'range', range: { min: 21, max: 85, step: 1 }, default: 'age_24', preview_method: 'control_only', values: Array.from({ length: 65 }, (_, i) => ({ id: `age_${21+i}`, name: `${21+i} years`, steers: `adult age ${21+i}` })) },
  ] },
] };
function initial(id: string, declared: boolean): ComparisonReviewData {
  return { category_id: 'body', group: `body:${id}`, state: 'draft', contract_hash: 'c'.repeat(64), baseline: { asset_id: 'a'.repeat(32), url: `/api/comparisons/assets/${'a'.repeat(32)}.png`, sha256: 'd'.repeat(64), width: 400, height: 260, subject_id: 'woman-1' }, masks: { [id]: { polygon: [[.1,.1],[.8,.1],[.8,.8]] } }, artifacts: [], attributes: [{ id }], budget: { cap: 0, used: 0 }, locked_fields: ['identity'], allowed_changes: ['selected target'], ...(declared ? { baseline_requirements: id === 'waist' ? requirements : hipRequirements } : {}) };
}
async function setup(page: Page, options: { legacy?: boolean; missing?: boolean; delayedMask?: boolean } = {}) {
  await page.context().route('**/*', route => route.abort('blockedbyclient'));
  const api = await mockAPI(page);
  const activeCatalog = structuredClone(catalog);
  if (options.legacy) for (const attr of activeCatalog.categories[0].attributes) delete attr.preview_contract;
  const reviews = new Map(['waist', 'hip'].map(id => [id, initial(id, !options.legacy)]));
  if (options.missing) for (const r of reviews.values()) r.baseline = null;
  const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
  let releaseMask: (() => void) | undefined;
  await page.route('**/api/library', route => route.fulfill({ json: activeCatalog }));
  await page.route('**/api/catalog/versions', route => route.fulfill({ json: { active_version: 2, legacy_version: 1, library: activeCatalog, historical_library: legacyLibrary } }));
  await page.route('**/api/gallery?*', route => route.fulfill({ json: { items: ['owned', 'other'].map(id => ({ id, url: guide, thumbnail_url: guide, width: 400, height: 260, selections: {}, aspect_ratio: '3:2', prompt: 'Simulated owned photo', created_at: 'fixture' })), page: 1, pages: 1, page_size: 12, total: 2 } }));
  await page.route('**/api/comparisons/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname;
    if (path.includes('/assets/')) return route.fulfill({ body: decodeURIComponent(guide.split(',')[1]), contentType: 'image/svg+xml' });
    if (path.endsWith('/categories')) return route.fulfill({ json: { categories: [{ id: 'body', state: 'draft' }] } });
    if (request.method() === 'GET') return route.fulfill({ json: reviews.get(url.searchParams.get('attribute_id') || 'waist') });
    const body = request.postDataJSON() as Record<string, unknown>;
    posts.push({ path, body });
    const r = reviews.get(String(body.attribute_id));
    if (!r || body.group !== r.group) return route.fulfill({ status: 422, json: { error: 'Group mismatch' } });
    if (path.endsWith('/base')) {
      if (r.baseline_requirements?.length && JSON.stringify(body.baseline_confirmations) !== JSON.stringify(r.baseline_requirements)) return route.fulfill({ status: 422, json: { error: 'Exact human confirmations required' } });
      r.baseline = { ...initial(String(body.attribute_id), false).baseline!, image_id: String(body.image_id), crop: body.crop, sha256: 'e'.repeat(64) };
      r.masks = {}; r.contract_hash = 'f'.repeat(64);
    }
    if (path.endsWith('/mask')) {
      if (options.delayedMask) await new Promise<void>(resolve => { releaseMask = resolve; });
      r.masks[String(body.attribute_id)] = { polygon: body.polygon as [number, number][] };
    }
    if (path.endsWith('/approve')) { expect(body.expected_contract_hash).toBe(r.contract_hash); r.state = 'contract_approved'; }
    return route.fulfill({ json: r });
  });
  await page.goto('https://atelier.test/?workspace=comparisons');
  await expect(page.getByRole('heading', { name: 'Body', exact: true })).toBeVisible();
  await expect(page.getByLabel('Target attribute', { exact: true })).toHaveValue('waist');
  return { api, posts, reviews, releaseMask: () => { expect(releaseMask).toBeDefined(); releaseMask!(); } };
}

test('human baseline requirements gate exact group payload and immutable crop, then appear in approval', async ({ page }) => {
  const { posts } = await setup(page, { missing: true });
  await page.getByRole('button', { name: 'Choose gallery baseline', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Choose the original woman baseline' });
  const disclosure = dialog.getByRole('region', { name: 'Baseline requirements', exact: true });
  for (const text of requirements) await expect(disclosure.getByText(text, { exact: true })).toBeVisible();
  await expect(disclosure).toContainText('human operator review');
  await expect(dialog.getByText('Catalog fallback only.', { exact: true })).toHaveCount(0);
  await dialog.getByRole('radio').first().check();
  await dialog.getByRole('checkbox', { name: /declare the baseline/ }).check();
  const confirm = dialog.getByRole('checkbox', { name: /I confirm this image/ });
  const use = dialog.getByRole('button', { name: 'Use owned baseline', exact: true });
  await expect(use).toBeDisabled();
  await confirm.check();
  await expect(use).toBeEnabled();
  await dialog.getByRole('checkbox', { name: /Use a fixed crop/ }).check();
  await expect(confirm).not.toBeChecked();
  for (const [name, value] of [['left', '.1'], ['top', '.2'], ['right', '.9'], ['bottom', '.8']]) await dialog.getByRole('spinbutton', { name: `Baseline crop ${name}` }).fill(value);
  await confirm.check();
  await dialog.getByRole('spinbutton', { name: 'Baseline crop right' }).fill('.85');
  await expect(use).toBeDisabled();
  await confirm.check();
  await use.click();
  await expect(dialog).toBeHidden();
  expect(posts[0]).toEqual({ path: '/api/comparisons/body/base', body: { image_id: 'owned', subject_id: 'woman-1', attribute_id: 'waist', group: 'body:waist', crop: [.1,.2,.85,.8], baseline_confirmations: requirements } });
  await page.getByRole('button', { name: 'Review and approve contract', exact: true }).click();
  const approval = page.getByRole('dialog', { name: 'Approve this review group contract' });
  for (const text of requirements) await expect(approval.getByText(text, { exact: true })).toBeVisible();
  await approval.getByRole('checkbox', { name: /I reviewed/ }).check();
  await approval.getByRole('button', { name: 'Approve contract only' }).click();
  await expect(approval).toBeHidden();
  expect(posts[1].body).toMatchObject({ attribute_id: 'waist', group: 'body:waist', provider_attempt_cap: 0, expected_contract_hash: 'f'.repeat(64) });
  expect(posts.some(p => p.path.endsWith('/preview'))).toBe(false);
});

test('image changes, cancellation and selecting another group require a fresh declaration', async ({ page }) => {
  const { posts } = await setup(page);
  const open = () => page.getByRole('button', { name: 'Change gallery baseline', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Choose the original woman baseline' });
  await open();
  await dialog.getByRole('radio').first().check();
  await dialog.getByRole('checkbox', { name: /declare the baseline/ }).check();
  await dialog.getByRole('checkbox', { name: /I confirm this image/ }).check();
  await dialog.getByRole('radio').last().check();
  await expect(dialog.getByRole('checkbox', { name: /I confirm this image/ })).not.toBeChecked();
  await expect(dialog.getByRole('checkbox', { name: /declare the baseline/ })).not.toBeChecked();
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await open();
  await expect(dialog.getByRole('radio').first()).not.toBeChecked();
  await expect(dialog.getByRole('button', { name: 'Use owned baseline' })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByLabel('Target attribute', { exact: true }).selectOption('hip');
  await expect(page.getByRole('heading', { name: 'Hip: target mask', exact: true })).toBeVisible();
  await open();
  await expect(dialog.getByText(hipRequirements[0], { exact: true })).toBeVisible();
  await expect(dialog.getByText(requirements[0], { exact: true })).toHaveCount(0);
  await dialog.getByRole('radio').first().check();
  await dialog.getByRole('checkbox', { name: /declare the baseline/ }).check();
  await expect(dialog.getByRole('button', { name: 'Use owned baseline' })).toBeDisabled();
  await dialog.getByRole('checkbox', { name: /I confirm this image/ }).check();
  await dialog.getByRole('button', { name: 'Use owned baseline' }).click();
  await expect(dialog).toBeHidden();
  expect(posts[0].body).toMatchObject({ attribute_id: 'hip', group: 'body:hip', baseline_confirmations: hipRequirements });
});

test('legacy group with no requirements omits confirmations and keeps adult woman declaration', async ({ page }) => {
  const { posts } = await setup(page, { legacy: true, missing: true });
  await page.getByRole('button', { name: 'Choose gallery baseline', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Choose the original woman baseline' });
  await expect(dialog.getByRole('region', { name: 'Baseline requirements' })).toHaveCount(0);
  await dialog.getByRole('radio').first().check();
  await expect(dialog.getByRole('button', { name: 'Use owned baseline' })).toBeDisabled();
  await dialog.getByRole('checkbox', { name: /declare the baseline/ }).check();
  await dialog.getByRole('button', { name: 'Use owned baseline' }).click();
  await expect(dialog).toBeHidden();
  expect(posts[0].body).toEqual({ image_id: 'owned', subject_id: 'woman-1', attribute_id: 'waist', group: 'body:waist' });
});

test('busy disables target selection and reload; rapid group reads reconcile the last selection', async ({ page }) => {
  const { posts, releaseMask } = await setup(page, { delayedMask: true });
  await page.getByRole('spinbutton', { name: 'Point 1 X' }).fill('.2');
  await page.getByRole('button', { name: 'Save attribute mask', exact: true }).click();
  await expect.poll(() => posts.length).toBe(1);
  const target = page.getByLabel('Target attribute', { exact: true });
  await expect(target).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Reload category', exact: true })).toBeDisabled();
  releaseMask();
  await expect(target).toBeEnabled();
  await page.evaluate(() => {
    const selector = document.querySelector<HTMLSelectElement>('select[id^="comparison-attribute-"]')!;
    for (const value of ['hip', 'waist', 'hip']) { selector.value = value; selector.dispatchEvent(new Event('change', { bubbles: true })); }
  });
  await expect(target).toHaveValue('hip');
  await expect(page.getByRole('heading', { name: 'Original baseline · body:hip', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Hip: target mask', exact: true })).toBeVisible();
  expect(posts).toHaveLength(1);
});

test('unset age uses default 24 display; keyboard and click can explicitly select minimum 21', async ({ page }) => {
  const { api } = await setup(page);
  await page.goto('https://atelier.test/');
  await page.getByRole('navigation', { name: 'Library categories' }).getByRole('button', { name: /Age and gender/ }).click();
  const age = page.getByRole('region', { name: 'Age', exact: true });
  const dial = age.getByRole('slider', { name: 'Age dial' });
  const number = age.getByRole('spinbutton', { name: 'Age in years', exact: true });
  await expect(dial).toHaveValue('24'); await expect(number).toHaveValue('');
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.length).toBe(1);
  expect(api.previewPayloads[0].selections.age).toBeUndefined();
  await dial.focus(); await dial.press('Home');
  await expect(number).toHaveValue('21');
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.at(-1)?.selections.age).toEqual(['age_21']);
  await age.getByRole('button', { name: 'Unset Age', exact: true }).click();
  await expect(dial).toHaveValue('24');
  await dial.click({ position: { x: 1, y: 8 } });
  await expect(number).toHaveValue('21');
  expect(api.jobPayloads).toHaveLength(0);
});

test('age typing keeps invalid intermediate input quiet, preserves valid draft and clears notice on unset', async ({ page }) => {
  const { api } = await setup(page);
  await page.goto('https://atelier.test/');
  await page.getByRole('navigation', { name: 'Library categories' }).getByRole('button', { name: /Age and gender/ }).click();
  const age = page.getByRole('region', { name: 'Age', exact: true });
  const number = age.getByRole('spinbutton', { name: 'Age in years', exact: true });
  const notice = age.locator('#numeric-status-age');
  await number.pressSequentially('3');
  await expect(number).toHaveValue('3'); await expect(notice).toBeEmpty();
  await expect(number).toHaveAttribute('aria-invalid', 'false');
  await number.pressSequentially('5');
  await expect(number).toHaveValue('35'); await expect(notice).toBeEmpty();
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.at(-1)?.selections.age).toEqual(['age_35']);
  await number.fill('3'); await number.press('Tab');
  await expect(notice).toContainText('Choose a whole age');
  await expect(number).toHaveValue('35');
  await number.focus();
  await expect(notice).toBeEmpty(); await expect(number).toHaveValue('35');
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.length).toBe(2);
  expect(api.previewPayloads.at(-1)?.selections.age).toEqual(['age_35']);
  await age.getByRole('button', { name: 'Unset Age', exact: true }).click();
  await expect(notice).toBeEmpty(); await expect(number).toHaveValue('');
  await number.fill('3'); await number.press('Tab');
  await expect(notice).toContainText('Choose a whole age');
  await expect(number).toHaveValue('');
  // Refocusing a restored blank clears the notice even when fill('') changes nothing.
  await number.focus(); await expect(notice).toBeEmpty();
  await number.fill(''); await expect(notice).toBeEmpty();
  expect(api.jobPayloads).toHaveLength(0);
});
