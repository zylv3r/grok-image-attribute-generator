// Real read-only saved-persona acceptance; no intercepted APIs or paid requests.
import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
const base = process.env.STUDIO_BASE_URL || 'http://localhost:8123';
const output = new URL('../acceptance-output/saved-base-live/', import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
const results = [];
try {
  for (const width of [1440, 390, 320]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const response = await context.request.get(`${base}/api/base-persona`);
    assert.equal(response.status(), 200, 'Saved persona endpoint must be active');
    const pack = await response.json();
    assert.equal(pack.id, 'persona-b');
    assert.equal(pack.controlled_masks_approved, false);
    assert.equal(pack.comparison_publication_approved, false);
    const policy = await (await context.request.get(`${base}/api/image-policy`)).json();
    assert.equal(policy.generation_model, 'grok-imagine-image-2.0');
    assert.equal(policy.reference_edit_model, 'grok-imagine-image-2.0');
    assert.equal(policy.legacy_fallback_allowed, false);
    for (const url of Object.keys(pack.assets)) {
      const asset = await context.request.get(base + url);
      assert.equal(asset.status(), 200, url);
      assert.ok((await asset.body()).length > 0, url);
    }
    await page.goto(base, { waitUntil: 'networkidle' });
    const region = page.getByRole('region', { name: 'Saved persona reference' });
    await region.waitFor();
    assert.ok(await region.isVisible());
    await region.getByRole('heading', { name: 'Persona B · reference v1' }).waitFor();
    const image = region.locator('img');
    await image.evaluate(async img => { await img.decode(); });
    const dimensions = await image.evaluate(img => ({ width: img.naturalWidth, height: img.naturalHeight }));
    assert.ok(dimensions.width > 0 && dimensions.height > 0);
    await image.scrollIntoViewIfNeeded();
    assert.ok(await image.isVisible());
    assert.equal(await region.getByRole('link', { name: 'Reference sheet PDF' }).getAttribute('href'), pack.pdf_url);
    await region.locator('summary').click();
    assert.ok(await region.getByText('Exact high-detail right-facing head profile remains held;', { exact: false }).isVisible());
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(overflow <= 1, `Page overflow at ${width}: ${overflow}`);
    assert.deepEqual(errors, []);
    const accessibility = await new AxeBuilder({ page }).include('.saved-base').analyze();
    assert.deepEqual(accessibility.violations, []);
    await region.screenshot({ path: new URL(`saved-base-${width}.png`, output).pathname });
    results.push({ width, assets: Object.keys(pack.assets).length, selected_views: Object.keys(pack.selected_views).length, dimensions, overflow, errors });
    await context.close();
  }
  await writeFile(new URL('results.json', output), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
} finally { await browser.close(); }
