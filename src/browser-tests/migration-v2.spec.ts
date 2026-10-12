import { test, expect, type Page } from "@playwright/test";
import { mockAPI, library, image } from "./fixtures";
import type { Preset } from "../types";

// These tests load the actual compiled application with an explicitly simulated API.
// They never call an image provider or write the installation archive.
async function migrationFixture(page: Page, options: { unresolved?: boolean; failure?: boolean } = {}) {
  const api = await mockAPI(page);
  const raw = { selections: { age: ["24"], ...(options.unresolved ? { retired_face: ["ideal"] } : {}) }, whitelist: {}, mode: "single", n: 1, aspect_ratio: "9:16", extra_prompt: "Original note", anchor: { category_id: "skin", asset_id: "a".repeat(32) } };
  const archived: Preset = { id: "historical", name: "Archived direction", draft: raw, schema_version: 1, catalog_hash: "v1", created_at: "then", updated_at: "then" };
  const resolved = { selections: { age: ["adult"] }, whitelist: {}, mode: "single", n: 1, aspect_ratio: "9:16", extra_prompt: "Original note" };
  const requests: unknown[] = [];
  let failure = options.failure;
  await page.route("**/api/presets", route => route.fulfill({ json: { presets: [archived] } }));
  await page.route("**/api/catalog/resolve", route => {
    requests.push(route.request().postDataJSON());
    return failure
      ? route.fulfill({ status: 503, json: { error: "Migration review offline" } })
      : route.fulfill({ json: { draft: resolved, changes: [{ attribute_id: "age", from: "24", to: "adult", disposition: "alias" }], unresolved: options.unresolved ? [{ attribute_id: "retired_face", value_id: "ideal", reason: "Retired control" }] : [] } });
  });
  await page.goto("/");
  return { api, raw, requests, recover: () => { failure = false; } };
}

test("preset migration reviews aliases and unresolved controls before any draft change", async ({ page }) => {
  const state = await migrationFixture(page, { unresolved: true });
  await page.getByRole("button", { name: "Presets", exact: true }).click();
  await page.getByRole("button", { name: "Apply Archived direction", exact: true }).click();
  const review = page.getByRole("dialog", { name: "Review catalog migration" });
  await expect(review).toBeVisible();
  await expect(review).toContainText("24");
  await expect(review).toContainText("adult");
  await expect(review).toContainText("retired_face");
  expect(state.requests).toEqual([{ draft: state.raw }]);
  expect(state.api.jobPayloads).toHaveLength(0);
  await page.getByRole("button", { name: "Cancel apply", exact: true }).click();
  await expect(page.getByRole("button", { name: "Apply Archived direction", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Apply Archived direction", exact: true }).click();
  await page.getByRole("button", { name: "Apply known controls", exact: true }).click();
  await expect(review).not.toBeVisible();
  expect(JSON.stringify(state.raw)).toContain("retired_face");
});

test("failed resolution blocks application and retry preserves the original archive", async ({ page }) => {
  const state = await migrationFixture(page, { failure: true });
  await page.getByRole("button", { name: "Presets", exact: true }).click();
  await page.getByRole("button", { name: "Apply Archived direction", exact: true }).click();
  const review = page.getByRole("dialog", { name: "Review catalog migration" });
  await expect(review).toContainText("Migration review offline");
  await expect(review.getByRole("button", { name: "Apply resolved controls", exact: true })).toBeDisabled();
  state.recover();
  await review.getByRole("button", { name: "Retry migration review", exact: true }).click();
  await expect(review).toContainText("adult");
  await review.getByRole("button", { name: "Apply resolved controls", exact: true }).click();
  expect(state.requests).toEqual([{ draft: state.raw }, { draft: state.raw }]);
  expect(state.api.jobPayloads).toHaveLength(0);
});

test("unchanged v2 controls still need confirmation and mobile Escape returns to the preset", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await migrationFixture(page);
  await page.route("**/api/catalog/resolve", route => route.fulfill({ json: { draft: { selections: { skin_tone: ["fair"] }, whitelist: {}, mode: "single", n: 1, aspect_ratio: "9:16", extra_prompt: "" }, changes: [], unresolved: [] } }));
  await page.getByRole("button", { name: "Presets", exact: true }).click();
  await page.getByRole("button", { name: "Apply Archived direction", exact: true }).click();
  const review = page.getByRole("dialog", { name: "Review catalog migration" });
  await expect(review).toContainText("No catalog changes are needed.");
  await expect(review.getByRole("button", { name: "Apply resolved controls", exact: true })).toBeEnabled();
  expect(await review.evaluate(element => element.getBoundingClientRect().width)).toBeLessThanOrEqual(390);
  await page.keyboard.press("Escape");
  await expect(review).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Apply Archived direction", exact: true })).toBeFocused();
  expect(state.api.jobPayloads).toHaveLength(0);
});

test("image reuse resolves original recorded selections and asks before applying", async ({ page }) => {
  const state = await migrationFixture(page);
  await page.getByRole("tab", { name: "Gallery", exact: true }).click();
  await page.getByRole("button", { name: "Open image 1", exact: true }).click();
  await page.getByRole("button", { name: /Reuse/ }).click();
  const review = page.getByRole("dialog", { name: "Review catalog migration" });
  await expect(review).toBeVisible();
  expect(state.requests).toHaveLength(1);
  expect((state.requests[0] as { draft: { selections: unknown } }).draft.selections).toEqual(image("1").selections);
  expect(state.api.jobPayloads).toHaveLength(0);
});

test("historical retired filters remain available and are clearly archived", async ({ page }) => {
  const api = await mockAPI(page);
  const historical = structuredClone(library);
  historical.categories[0].attributes.push({ id: "retired_face", name: "Archived Facial Balance", type: "exclusive", values: [{ id: "ideal", name: "Ideal (archived)", steers: "Historical record" }] });
  await page.route("**/api/library", route => route.fulfill({ json: { ...library, historical_library: historical } }));
  await page.route("**/api/catalog/versions", route => route.fulfill({ json: { active_version: 2, legacy_version: 1, library_hash: "fixture", source_control_mode: "legacy_exploratory", effective_counts: {}, categories: [] } }));
  await page.goto("/?gallery_filters=" + encodeURIComponent(JSON.stringify({ retired_face: ["ideal"] })));
  await page.getByRole("tab", { name: "Gallery", exact: true }).click();
  await page.getByRole("button", { name: /Attribute filters/ }).click();
  await expect(page.getByRole("dialog", { name: "Filter the archive" })).toContainText(/archived/i);
  await expect(page.getByRole("checkbox", { name: /Archived Facial Balance.*Ideal/ })).toBeChecked();
  await expect.poll(() => api.galleryQueries.length).toBeGreaterThan(0);
  expect(JSON.parse(api.galleryQueries.at(-1)!.get("filters")!)).toEqual({ retired_face: ["ideal"] });
});
