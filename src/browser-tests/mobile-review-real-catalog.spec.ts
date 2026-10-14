import { readFile } from 'node:fs/promises';
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import type { Library, Category } from '../types';
import { methodLabel, type ComparisonAttribute, type ComparisonReviewData } from '../comparisons';
import { mockAPI, library as legacyLibrary } from './fixtures';

// Parent builds dist and runs Chromium. Catalog vocabulary is never shortened or
// synthesized; only the empty API review state is simulated. No auth state needed.
const catalog: Library = JSON.parse(await readFile(new URL('../../catalog/v2/library.json', import.meta.url), 'utf8'));
const targets = catalog.categories.flatMap(category => category.attributes.map(attribute => ({
  category, attribute: attribute as ComparisonAttribute,
})));
const counts = {
  categories: catalog.categories.length,
  attributes: targets.length,
  values: targets.reduce((total, { attribute }) => total + attribute.values.length, 0),
  groups: new Set(targets.map(({ attribute }) => attribute.comparison_group)).size,
};
const widths = [320, 390, 430];
const defaultTarget = targets[0];
const longestReferenceGroup = targets.filter(({ attribute }) => attribute.preview_method === 'reference_edit')
  .reduce((longest, target) => target.attribute.comparison_group!.length > longest.attribute.comparison_group!.length ? target : longest);
const longestValue = (attribute: ComparisonAttribute) => attribute.values.reduce((longest, value) => value.name.length > longest.name.length ? value : longest);

test.use({ serviceWorkers: 'block' });

async function setup(page: Page) {
  const writes: string[] = [], unexpected: string[] = [], reads: string[] = [];
  await page.context().route('**/*', route => {
    unexpected.push(route.request().url());
    return route.abort('blockedbyclient');
  });
  const api = await mockAPI(page);
  // This later route also prevents mockAPI's simulated write handlers from ever
  // accepting a render, approval, preset write, or job request in this suite.
  await page.route('**/api/**', route => {
    const request = route.request(), url = new URL(request.url());
    if (request.method() !== 'GET') {
      writes.push(`${request.method()} ${url.pathname}`);
      return route.abort('blockedbyclient');
    }
    if (url.origin !== 'https://atelier.test') {
      unexpected.push(request.url());
      return route.abort('blockedbyclient');
    }
    if (url.pathname === '/api/library') return route.fulfill({ json: catalog });
    if (url.pathname === '/api/catalog/versions') return route.fulfill({ json: {
      active_version: 2, legacy_version: 1, library: catalog, historical_library: legacyLibrary,
    } });
    if (url.pathname === '/api/base-persona') return route.fulfill({ json: { available: false } });
    if (url.pathname === '/api/presets') return route.fulfill({ json: { presets: [] } });
    if (url.pathname === '/api/gallery') return route.fulfill({ json: { items: [], page: 1, page_size: 24, total: 0, pages: 0 } });
    if (url.pathname === '/api/thumbnail-status') return route.fulfill({ status: 404, json: { error: 'No photographic preview worker in this fixture' } });
    if (url.pathname === '/api/comparisons/categories') return route.fulfill({ json: {
      categories: catalog.categories.map(category => ({
        id: category.id, state: 'draft',
        groups: Object.fromEntries(category.attributes.map(attribute => [attribute.comparison_group!, { state: 'draft' }])),
      })),
    } });
    const category = catalog.categories.find(candidate => url.pathname === `/api/comparisons/${encodeURIComponent(candidate.id)}`);
    const attribute = category?.attributes.find(candidate => candidate.id === url.searchParams.get('attribute_id')) as ComparisonAttribute | undefined;
    if (category && attribute && url.searchParams.size === 1) {
      reads.push(url.pathname + url.search);
      const groupAttributes = category.attributes.filter(candidate => candidate.comparison_group === attribute.comparison_group);
      const review: ComparisonReviewData = {
        category_id: category.id, group: attribute.comparison_group,
        attributes: groupAttributes, state: 'draft', contract_hash: 'c'.repeat(64),
        baseline: null, masks: {}, artifacts: [], attempts: [], history: [], approvals: [],
        cycle: { id: 0, cap: 0, used: 0 }, budget: { cap: 0, used: 0, cycle_id: 0, cycle_used: 0 },
        locked_fields: attribute.preview_contract?.locked_fields ?? [],
        allowed_changes: attribute.preview_contract?.allowed_changes ?? [],
        baseline_requirements: attribute.preview_contract?.baseline_requirements as string[] | undefined,
      };
      return route.fulfill({ json: review });
    }
    unexpected.push(request.url());
    return route.abort('blockedbyclient');
  });
  await page.goto('/?workspace=comparisons');
  await waitForTarget(page, defaultTarget.category, defaultTarget.attribute);
  return { writes, unexpected, reads, api };
}

async function waitForTarget(page: Page, category: Category, attribute: ComparisonAttribute) {
  await expect(page.getByRole('heading', { name: category.name, exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: `Original baseline · ${attribute.comparison_group}`, exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: `${attribute.name}: target mask`, exact: true })).toBeVisible();
  await expect(page.locator('.comparison-category')).toHaveAttribute('aria-busy', 'false');
  await expect(page.getByRole('combobox', { name: 'Target attribute', exact: true })).toHaveValue(attribute.id);
  await expect(page.getByRole('combobox', { name: 'Comparison method', exact: true })).toHaveValue(attribute.preview_method!);
}

async function selectCategory(page: Page, category: Category) {
  await page.getByRole('navigation', { name: 'Review categories', exact: true })
    .getByRole('button').filter({ has: page.getByText(category.name, { exact: true }) }).click();
  await waitForTarget(page, category, category.attributes[0] as ComparisonAttribute);
}

async function assertBounds(page: Page, state: string) {
  const geometry = await page.evaluate(() => {
    const root = document.querySelector<HTMLElement>('.comparison-review')!;
    const selector = '.comparison-layout, .comparison-categories, .comparison-category, .comparison-schema, .comparison-table-wrap, .comparison-contract, .comparison-attribute-picker, .comparison-editor, .comparison-candidates, fieldset, legend, label, select, input:not([type=checkbox]):not([type=radio]), button';
    const failures: Array<Record<string, unknown>> = [];
    let fieldsets = 0, selects = 0;
    for (const element of [root, ...root.querySelectorAll<HTMLElement>(selector)]) {
      // Closed details have no visible layout. Open table contents may extend
      // inside their intentional scroller; only its outer wrapper must fit.
      const scroller = element.closest('.comparison-table-wrap');
      if (scroller && scroller !== element) continue;
      let closedDetails = false;
      for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
        if (ancestor instanceof HTMLDetailsElement && !ancestor.open && !ancestor.querySelector(':scope > summary')?.contains(element)) {
          closedDetails = true;
          break;
        }
      }
      if (closedDetails) continue;
      const rect = element.getBoundingClientRect(), style = getComputedStyle(element);
      if (!element.getClientRects().length || !rect.width || !rect.height || style.visibility === 'hidden' || style.display === 'none') continue;
      if (element.tagName === 'FIELDSET') fieldsets++;
      if (element.tagName === 'SELECT') selects++;
      const parent = element.parentElement!;
      const parentRect = parent.getBoundingClientRect(), parentStyle = getComputedStyle(parent);
      // Legends occupy the fieldset border. Other controls must fit the parent's
      // content area, so a select spilling into fieldset padding also fails.
      const left = parentRect.left + parseFloat(parentStyle.borderLeftWidth) + (element.tagName === 'LEGEND' ? 0 : parseFloat(parentStyle.paddingLeft));
      const right = parentRect.right - parseFloat(parentStyle.borderRightWidth) - (element.tagName === 'LEGEND' ? 0 : parseFloat(parentStyle.paddingRight));
      if (rect.left < -0.5 || rect.right > innerWidth + 0.5 || rect.left < left - 0.5 || rect.right > right + 0.5) {
        failures.push({ tag: element.tagName, class: element.className, text: element.textContent?.trim().slice(0, 100), left: rect.left, right: rect.right, parentLeft: left, parentRight: right });
      }
    }
    return { viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth, fieldsets, selects, failures };
  });
  expect(geometry.document, `${state}: document width`).toBeLessThanOrEqual(geometry.viewport);
  expect(geometry.body, `${state}: body width`).toBeLessThanOrEqual(geometry.viewport);
  expect(geometry.fieldsets, `${state}: visible preview fieldset checked`).toBeGreaterThan(0);
  expect(geometry.selects, `${state}: target attribute, value and method checked`).toBe(3);
  expect(geometry.failures, `${state}: visible controls and cards fit their parents`).toEqual([]);
}

async function assertSchema(page: Page, category: Category, attribute: ComparisonAttribute, width: number) {
  const schema = page.locator('.comparison-schema');
  const summary = schema.locator(':scope > summary');
  const wrapper = schema.locator('.comparison-table-wrap');
  expect(await schema.evaluate(element => (element as HTMLDetailsElement).open)).toBe(false);
  await expect(summary).toBeVisible();
  await assertBounds(page, `${width} ${category.id}/${attribute.id} schema closed`);
  await summary.click();
  await expect(wrapper).toBeVisible();
  await expect(wrapper.locator('tbody tr')).toHaveCount(category.attributes.length);
  expect(await wrapper.locator('th[scope=row] small').allTextContents()).toEqual(category.attributes.map(candidate => candidate.id));
  const scroll = await wrapper.evaluate(element => {
    const style = getComputedStyle(element);
    element.scrollLeft = element.scrollWidth - element.clientWidth;
    return { overflow: style.overflowX, excess: element.scrollWidth - element.clientWidth, offset: element.scrollLeft };
  });
  expect(scroll.overflow).toBe('auto');
  if (scroll.excess > 0) expect(scroll.offset, 'wide schema is reachable through its own scroller').toBeGreaterThan(0);
  await assertBounds(page, `${width} ${category.id}/${attribute.id} schema open and scrolled`);
  await wrapper.evaluate(element => { element.scrollLeft = 0; });
  await summary.click();
  expect(await schema.evaluate(element => (element as HTMLDetailsElement).open)).toBe(false);
}

function assertNoWrites(fixture: Awaited<ReturnType<typeof setup>>) {
  expect(fixture.writes).toEqual([]);
  expect(fixture.unexpected).toEqual([]);
  expect(fixture.api.jobPayloads).toEqual([]);
  expect(fixture.api.previewPayloads).toEqual([]);
}

for (const width of widths) {
  test(`actual v2 catalog: all ${counts.attributes} attributes fit closed/open review at ${width}px`, async ({ page }, testInfo) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width, height: 844 });
    const fixture = await setup(page);
    const visited: string[] = [], groups = new Set<string>();
    let checkedValues = 0;
    await expect(page.getByRole('navigation', { name: 'Review categories', exact: true }).getByRole('button')).toHaveCount(counts.categories);
    // The first assertion is the deployed default: hair_length/reference_edit
    // with its original first value, not the previous short hair_color fixture.
    await assertBounds(page, `${width} actual empty default`);
    for (const category of catalog.categories) {
      if (category.id !== defaultTarget.category.id) await selectCategory(page, category);
      for (const sourceAttribute of category.attributes) {
        const attribute = sourceAttribute as ComparisonAttribute;
        await test.step(`${category.id}/${attribute.id} · ${attribute.comparison_group}`, async () => {
          await page.getByRole('combobox', { name: 'Target attribute', exact: true }).selectOption(attribute.id);
          await waitForTarget(page, category, attribute);
          const value = page.getByRole('combobox', { name: 'Target value', exact: true });
          expect(await value.evaluate(element => Array.from((element as HTMLSelectElement).options, option => ({ id: option.value, name: option.text })))).toEqual(attribute.values.map(option => ({ id: option.id, name: option.name })));
          const longest = longestValue(attribute);
          await value.selectOption(longest.id);
          await expect(value).toHaveValue(longest.id);
          await expect(page.getByRole('combobox', { name: 'Comparison method', exact: true }).locator('option')).toHaveText(methodLabel(attribute.preview_method!));
          await expect(page.getByText('No baseline chosen.', { exact: false })).toBeVisible();
          const preview = page.locator('.comparison-preview-controls').getByRole('button');
          // Fabric swatches can stage a local texture with no person; every other
          // method remains blocked by the empty baseline or control-only policy.
          if (attribute.preview_method === 'fabric_swatch') await expect(preview).toBeEnabled();
          else await expect(preview).toBeDisabled();
          await assertSchema(page, category, attribute, width);
          visited.push(`${category.id}/${attribute.id}`);
          groups.add(attribute.comparison_group!);
          checkedValues += attribute.values.length;
        });
      }
    }
    const expectedTargets = targets.map(({ category, attribute }) => `${category.id}/${attribute.id}`);
    expect(visited).toEqual(expectedTargets);
    expect(groups.size).toBe(counts.groups);
    expect(checkedValues).toBe(counts.values);
    const expectedReads = targets.map(({ category, attribute }) => `/api/comparisons/${encodeURIComponent(category.id)}?${new URLSearchParams({ attribute_id: attribute.id })}`);
    expect([...new Set(fixture.reads)].sort()).toEqual(expectedReads.sort());
    assertNoWrites(fixture);
    await testInfo.attach('real-catalog-coverage', { body: JSON.stringify({ width, ...counts, checkedValues, reviewed: visited, schemaStates: ['closed', 'open/scrolled'], writes: fixture.writes }), contentType: 'application/json' });
  });

  test(`full axe: actual empty default and longest reference group at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    const fixture = await setup(page);
    await assertBounds(page, `${width} default axe state`);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    const { category, attribute } = longestReferenceGroup;
    await selectCategory(page, category);
    await page.getByRole('combobox', { name: 'Target attribute', exact: true }).selectOption(attribute.id);
    await waitForTarget(page, category, attribute);
    await page.getByRole('combobox', { name: 'Target value', exact: true }).selectOption(longestValue(attribute).id);
    await assertBounds(page, `${width} longest reference group axe state`);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await expect(page.getByRole('button', { name: 'Request one reference edit', exact: true })).toBeDisabled();
    assertNoWrites(fixture);
  });
}
