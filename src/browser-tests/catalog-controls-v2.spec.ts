import { test, expect } from '@playwright/test';
import { mockAPI, library } from './fixtures';

// Simulated API responses serve the actual compiled UI. No provider requests.
const expanded = structuredClone(library);
expanded.categories[0].attributes = [
  { id: 'age', name: 'Age', type: 'exclusive', control: 'range', range: { min: 21, max: 85, step: 1 }, preview_scope: 'control_only', values: Array.from({ length: 65 }, (_, i) => ({ id: `age_${i + 21}`, name: `${i + 21} years`, steers: `adult age ${i + 21}` })) },
  { id: 'gender', name: 'Gender / presentation', type: 'exclusive', control: 'select', preview_scope: 'control_only', values: [{ id: 'woman', name: 'Woman', steers: 'adult woman' }, { id: 'man', name: 'Man', steers: 'adult man' }] },
  { id: 'fabric_color', name: 'Fabric color', type: 'exclusive', control: 'swatch', preview_method: 'fabric_swatch', values: [{ id: 'wine', name: 'Wine', steers: 'wine fabric', rgb: [117, 34, 59] }, { id: 'ivory', name: 'Ivory', steers: 'ivory fabric', rgb: [237, 229, 208] }] },
] as typeof expanded.categories[0]['attributes'];

async function setup(page: Parameters<typeof mockAPI>[0]) {
  const api = await mockAPI(page);
  await page.route('**/api/library', route => route.fulfill({ json: expanded }));
  await page.goto('/');
  return api;
}

test('age dial and numeric input use canonical IDs; unset and all 65 variations survive previews', async ({ page }) => {
  const api = await setup(page);
  const age = page.getByRole('region', { name: 'Age', exact: true });
  await expect(age.getByRole('slider', { name: 'Age dial' })).toBeVisible();
  await age.getByRole('spinbutton', { name: 'Age in years', exact: true }).fill('85');
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.at(-1)?.selections.age).toEqual(['age_85']);
  await age.getByRole('button', { name: 'Unset Age', exact: true }).click();
  await expect(age.getByRole('spinbutton', { name: 'Age in years', exact: true })).toHaveValue('');
  await age.getByRole('button', { name: 'Vary', exact: true }).click();
  await age.getByRole('spinbutton', { name: 'Minimum allowed Age' }).fill('30');
  await age.getByRole('spinbutton', { name: 'Maximum allowed Age' }).fill('34');
  await age.getByRole('button', { name: 'Use age range' }).click();
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.at(-1)?.whitelist.age).toEqual(['age_30', 'age_31', 'age_32', 'age_33', 'age_34']);
  await age.getByRole('button', { name: 'All 65 values', exact: true }).click();
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.at(-1)?.whitelist.age?.length).toBe(65);
  await age.getByRole('button', { name: 'Inverse across 65', exact: true }).click();
  await expect(age.getByRole('button', { name: 'Vary', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(age.locator('img')).toHaveCount(0);
  expect(api.jobPayloads).toHaveLength(0);
});

test('gender is a select and fabric colors are textured RGB swatches without model photographs', async ({ page }) => {
  const api = await setup(page);
  const gender = page.getByRole('region', { name: 'Gender / presentation', exact: true });
  await expect(gender.getByRole('combobox', { name: 'Gender / presentation value', exact: true })).toHaveValue('woman');
  await gender.getByRole('combobox', { name: 'Gender / presentation value', exact: true }).selectOption('man');
  const fabric = page.getByRole('region', { name: 'Fabric color', exact: true });
  await fabric.getByRole('button', { name: 'Edit Fabric color' }).click();
  await fabric.getByRole('radio', { name: 'Wine', exact: true }).click();
  await expect(fabric.getByText('RGB 117, 34, 59', { exact: true })).toBeVisible();
  await expect(fabric.locator('.fabric-swatch')).toHaveCount(2);
  await expect(gender.locator('img')).toHaveCount(0);
  await expect(fabric.locator('img')).toHaveCount(0);
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.at(-1)?.selections.gender).toEqual(['man']);
  await expect.poll(() => api.previewPayloads.at(-1)?.selections.fabric_color).toEqual(['wine']);
  expect(api.jobPayloads).toHaveLength(0);
});

test('explicit recipe application reviews overrides and preserves unrelated locks', async ({ page }) => {
  const api = await mockAPI(page);
  const recipeLibrary = structuredClone(expanded);
  recipeLibrary.categories[0].attributes.push(
    { id: 'hair_cut', name: 'Hair cut', type: 'exclusive', control: 'cards', values: [{ id: 'bob', name: 'Bob', steers: 'bob cut' }, { id: 'long', name: 'Long', steers: 'long cut' }] },
    { id: 'hair_recipe', name: 'Hair recipe', type: 'exclusive', control: 'cards', values: [{ id: 'tidy_bob', name: 'Tidy Bob', steers: 'tidy bob recipe', recipe: { selections: { hair_cut: ['bob'] }, allowed_component_changes: ['hair_cut'] } }] },
  );
  await page.route('**/api/library', route => route.fulfill({ json: recipeLibrary }));
  await page.goto('/');
  const hair = page.getByRole('region', { name: 'Hair cut', exact: true });
  await hair.getByRole('button', { name: 'Edit Hair cut' }).click();
  await hair.getByRole('radio', { name: 'Long', exact: true }).click();
  const recipe = page.getByRole('region', { name: 'Hair recipe', exact: true });
  await recipe.getByRole('button', { name: 'Edit Hair recipe' }).click();
  await recipe.getByRole('button', { name: 'Apply Tidy Bob recipe components' }).click();
  const dialog = page.getByRole('dialog', { name: 'Apply Tidy Bob recipe' });
  await expect(dialog.getByText(/Replaces Lock: Long/)).toBeVisible();
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(hair.getByRole('radio', { name: 'Long', exact: true })).toBeChecked();
  await recipe.getByRole('button', { name: 'Apply Tidy Bob recipe components' }).click();
  await dialog.getByRole('button', { name: 'Apply recipe and component locks' }).click();
  await expect(hair.getByRole('radio', { name: 'Bob', exact: true })).toBeChecked();
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.at(-1)?.selections.hair_recipe).toEqual(['tidy_bob']);
  await expect.poll(() => api.previewPayloads.at(-1)?.selections.hair_cut).toEqual(['bob']);
  await expect.poll(() => api.previewPayloads.at(-1)?.selections.gender).toEqual(['woman']);
  expect(api.jobPayloads).toHaveLength(0);
});

test('age editing remains keyboard accessible at phone width and rejects invalid range application', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = await setup(page);
  const age = page.getByRole('region', { name: 'Age', exact: true });
  const number = age.getByRole('spinbutton', { name: 'Age in years', exact: true });
  await number.pressSequentially('35');
  await page.getByRole('button', { name: 'Preview prompt & plans' }).click();
  await expect.poll(() => api.previewPayloads.at(-1)?.selections.age).toEqual(['age_35']);
  await age.getByRole('button', { name: 'Vary', exact: true }).click();
  await age.getByRole('spinbutton', { name: 'Minimum allowed Age' }).fill('70');
  await age.getByRole('spinbutton', { name: 'Maximum allowed Age' }).fill('30');
  await age.getByRole('button', { name: 'Use age range' }).click();
  await expect(age.locator('#numeric-status-age')).toContainText('Enter an ordered range');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(api.jobPayloads).toHaveLength(0);
});
