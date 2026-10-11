import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockAPI, library } from "./fixtures";
import type { Library, ThumbnailProgress, ThumbnailStatus } from "../types";

const imageId = "a".repeat(32);
const secondId = "b".repeat(32);
const progress: ThumbnailProgress = {
  version: 1, total: 893, status: "running", value_completed: 1, failed: 0,
  attribute_completed: 1,
};

function photographicLibrary(state: ThumbnailProgress): Library {
  const result = structuredClone(library);
  result.thumbnail_mode = "photographic";
  result.thumbnail_progress = { ...state };
  // Keep the old SVG URLs on pending entries to catch accidental illustrative fallbacks.
  for (const attr of result.categories.flatMap((category) => category.attributes)) {
    attr.thumbnail_status = "pending";
    attr.thumbnail_kind = "pending";
    for (const value of attr.values) { value.thumbnail_status = "pending"; value.thumbnail_kind = "pending"; }
  }
  const tone = result.categories[0].attributes[0];
  tone.thumbnail_url = "/preview-atlases/skin_tone.jpg";
  tone.thumbnail_status = "ready";
  tone.thumbnail_kind = "contact_sheet";
  Object.assign(tone.values[0], {
    thumbnail_status: "ready", thumbnail_kind: "photographic", thumbnail_url: `/generated/${imageId}-thumb.jpg`,
    example_url: `/generated/${imageId}.jpg`, image_id: imageId,
  });
  if (state.value_completed >= 2) {
    Object.assign(result.categories[1].attributes[0].values[0], {
      thumbnail_status: "ready", thumbnail_kind: "photographic", thumbnail_url: `/generated/${secondId}-thumb.jpg`,
      example_url: `/generated/${secondId}.jpg`, image_id: secondId,
    });
  }
  return result;
}

async function photographicAPI(page: Page, initial = progress) {
  const api = await mockAPI(page);
  // A tiny JPEG fixture tests decoding and media type without any provider calls.
  const jpeg = Buffer.from(await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 8;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#a29d88";
    ctx.fillRect(0, 0, 8, 8);
    return canvas.toDataURL("image/jpeg").split(",")[1];
  }), "base64");
  const state = {
    progress: { ...initial }, statusCalls: 0, libraryCalls: 0,
    failStatus: false, failLibrary: false, staleInitial: false,
    holdStatus: undefined as Promise<void> | undefined,
  };
  // Context routing also covers the popup's initial navigation.
  await page.context().route("**/generated/*.jpg", (route) => route.fulfill({ contentType: "image/jpeg", body: jpeg }));
  await page.route("**/generated/*.jpg", (route) => route.fulfill({ contentType: "image/jpeg", body: jpeg }));
  await page.route("**/preview-atlases/*.jpg", (route) => route.fulfill({ contentType: "image/jpeg", body: jpeg }));
  await page.route("**/api/library", (route) => {
    state.libraryCalls++;
    if (state.failLibrary) return route.fulfill({ status: 503, json: { error: "Simulated library refresh failure" } });
    return route.fulfill({ json: state.staleInitial && state.libraryCalls === 1 ? library : photographicLibrary(state.progress) });
  });
  await page.route("**/api/thumbnail-status", async (route) => {
    state.statusCalls++;
    if (state.holdStatus) await state.holdStatus;
    if (state.failStatus) return route.fulfill({ status: 503, json: { error: "Simulated preview status failure" } });
    const response: ThumbnailStatus = { mode: "photographic", ...state.progress };
    return route.fulfill({ json: response });
  });
  return { state, api };
}

test.describe("Photographic library — simulated API, no provider calls", () => {
  test("ready JPEGs show full frames and original links; pending entries never use diagrams or letters", async ({ page }) => {
    await photographicAPI(page);
    await page.goto("/");
    const main = page.locator("#studio-content");
    await expect(main.getByText("Generated photographic examples", { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Photographic preview progress" })).toContainText("Real photo values 1/893 · Contact sheets 1/5");
    const tone = page.getByRole("region", { name: "Skin Tone", exact: true });
    const ready = tone.getByRole("radio", { name: "Porcelain", exact: true });
    const photo = ready.getByRole("img", { name: "Generated example: Porcelain" });
    await expect(photo).toHaveAttribute("src", `/generated/${imageId}-thumb.jpg`);
    await expect(photo).toHaveCSS("object-fit", "contain");
    await expect.poll(() => photo.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
    expect(await photo.evaluate((img) => Math.abs(img.clientWidth - img.clientHeight))).toBeLessThanOrEqual(1);
    await expect(ready.getByText("Generated example", { exact: true })).toBeVisible();
    const pending = tone.getByRole("radio", { name: "Fair", exact: true });
    await expect(pending).toContainText("Photograph pending");
    await expect(pending.locator("img, svg, .thumb-fallback")).toHaveCount(0);
    await expect(main.locator('img[src*="svg"], .thumb-fallback')).toHaveCount(0);
    await expect(tone.getByRole("img", { name: "Skin Tone: representative examples" })).toHaveAttribute("src", "/preview-atlases/skin_tone.jpg");
    await expect(tone.getByText("Representative examples", { exact: true })).toBeVisible();
    const original = tone.getByRole("link", { name: "Open original generated example: Porcelain" });
    await expect(original).toHaveAttribute("href", `/generated/${imageId}.jpg`);
    await expect(ready.getByRole("link")).toHaveCount(0);
    const opened = page.waitForEvent("popup");
    await original.click();
    const popup = await opened;
    await expect(popup).toHaveURL(`https://atelier.test/generated/${imageId}.jpg`);
    await popup.close();
    await expect(ready).not.toBeChecked();
    await ready.click();
    await page.keyboard.press("ArrowRight");
    await expect(pending).toBeFocused();
    await expect(pending).toBeChecked();
    await expect(main).toContainText("fixed photographic prompt baseline");
    await expect(main).toContainText("Provider variability");
    const axe = await new AxeBuilder({ page }).analyze();
    expect(axe.violations).toEqual([]);
  });

  test("ten-second version updates preserve selections, category, search, generation settings, and presets", async ({ page }) => {
    await page.clock.install();
    const { state, api } = await photographicAPI(page);
    await page.goto("/");
    await expect(page.getByRole("region", { name: "Photographic preview progress" })).toContainText("1/893");
    await expect.poll(() => state.statusCalls).toBe(1);
    await page.getByRole("navigation", { name: "Library categories" }).getByRole("button", { name: "Pose" }).click();
    const pose = page.getByRole("region", { name: "Pose", exact: true });
    await pose.getByRole("checkbox", { name: "Standing", exact: true }).click();
    await page.getByRole("textbox", { name: "Search library" }).fill("Standing");
    await page.getByRole("combobox", { name: "Generation mode" }).click();
    await page.getByRole("option", { name: "Repeat · same direction" }).click();
    await page.getByRole("spinbutton", { name: "Images", exact: true }).fill("3");
    await page.locator("#extra-prompt").fill("Keep my composition");
    await page.getByRole("button", { name: "Presets", exact: true }).click();
    await page.getByRole("textbox", { name: "Name this direction" }).fill("Saved standing");
    await page.getByRole("button", { name: "Save preset", exact: true }).click();
    await page.getByRole("button", { name: "Close presets" }).click();
    state.progress = { ...state.progress, version: 2, value_completed: 2, attribute_completed: 2 };
    await page.clock.runFor(10_001);
    await expect(page.getByRole("region", { name: "Photographic preview progress" })).toContainText("Real photo values 2/893 · Contact sheets 2/5");
    expect(state.libraryCalls).toBe(2);
    await expect(page.getByRole("textbox", { name: "Search library" })).toHaveValue("Standing");
    await expect(page.getByRole("heading", { level: 2, name: "Pose", exact: true })).toBeVisible();
    await expect(pose.getByRole("checkbox", { name: "Standing", exact: true })).toBeChecked();
    await expect(pose.getByRole("img", { name: "Generated example: Standing" })).toHaveAttribute("src", `/generated/${secondId}-thumb.jpg`);
    await expect(page.getByRole("combobox", { name: "Generation mode" })).toContainText("Repeat");
    await expect(page.getByRole("spinbutton", { name: "Images", exact: true })).toHaveValue("3");
    await expect(page.locator("#extra-prompt")).toHaveValue("Keep my composition");
    await page.getByRole("button", { name: "Presets", exact: true }).click();
    await expect(page.getByRole("dialog")).toContainText("Saved standing");
    await page.getByRole("button", { name: "Close presets" }).click();
    await page.getByRole("button", { name: "Preview prompt & plans" }).click();
    await expect.poll(() => api.previewPayloads.length).toBeGreaterThan(0);
    expect(api.previewPayloads.at(-1)).toMatchObject({ selections: { pose: ["standing"] }, mode: "repeat", n: 3, extra_prompt: "Keep my composition" });
    await page.clock.runFor(10_001);
    await expect.poll(() => state.statusCalls).toBe(3);
    expect(state.libraryCalls).toBe(2);
  });

  test("initial status detects photographic activation even when the first library response is illustrative", async ({ page }) => {
    const { state } = await photographicAPI(page);
    state.staleInitial = true;
    let release!: () => void;
    state.holdStatus = new Promise<void>((resolve) => { release = resolve; });
    await page.goto("/");
    await expect(page.getByText("Illustrative guides · not generated results")).toBeVisible();
    const selected = page.getByRole("radio", { name: "Porcelain", exact: true });
    await selected.click();
    await page.getByRole("textbox", { name: "Search library" }).fill("Porcelain");
    release();
    await expect(page.getByText("Generated photographic examples", { exact: true })).toBeVisible();
    expect(state.libraryCalls).toBe(2);
    await expect(selected).toBeChecked();
    await expect(page.getByRole("textbox", { name: "Search library" })).toHaveValue("Porcelain");
    await expect(selected.getByRole("img")).toHaveAttribute("src", `/generated/${imageId}-thumb.jpg`);
  });

  test("status and library failures stay inline; reload retries without resetting the working draft", async ({ page }) => {
    await page.clock.install();
    const { state } = await photographicAPI(page);
    state.failStatus = true;
    await page.goto("/");
    const selected = page.getByRole("radio", { name: "Porcelain", exact: true });
    await selected.click();
    await expect(page.getByText("Preview updates are temporarily unavailable. You can keep composing.")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    state.failStatus = false;
    await page.getByRole("button", { name: "Reload previews" }).click();
    await expect(page.getByRole("button", { name: "Reload previews" })).toHaveCount(0);
    await expect(selected).toBeChecked();
    state.progress = { ...state.progress, version: 2, value_completed: 2 };
    state.failLibrary = true;
    await page.clock.runFor(10_001);
    await expect(page.getByRole("button", { name: "Reload previews" })).toBeVisible();
    await expect(selected).toBeChecked();
    state.failLibrary = false;
    await page.getByRole("button", { name: "Reload previews" }).click();
    await expect(page.getByRole("region", { name: "Photographic preview progress" })).toContainText("2/893");
    await expect(page.getByRole("button", { name: "Reload previews" })).toHaveCount(0);
    await expect(selected).toBeChecked();
  });

  test("completed generation uses slow polling and missing status endpoints leave illustrative startup working", async ({ page }) => {
    await page.clock.install();
    const { state } = await photographicAPI(page, { ...progress, status: "completed", value_completed: 893, attribute_completed: 5 });
    const initialStatus = page.waitForResponse("**/api/thumbnail-status");
    await page.goto("/");
    await (await initialStatus).finished();
    // Yield one browser task so the completed fetch installs its next poll before advancing time.
    await page.evaluate(() => new Promise<void>((resolve) => setTimeout(resolve, 0)));
    await expect(page.getByRole("region", { name: "Photographic preview progress" })).toContainText("Completed");
    await expect.poll(() => state.statusCalls).toBe(1);
    await page.clock.runFor(30_001);
    expect(state.statusCalls).toBe(1);
    await page.clock.runFor(30_001);
    await expect.poll(() => state.statusCalls).toBe(2);
    await page.unroute("**/api/library");
    await page.unroute("**/api/thumbnail-status");
    await page.reload();
    await expect(page.getByText("Illustrative guides · not generated results")).toBeVisible();
    await expect(page.getByRole("button", { name: "Reload previews" })).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);
    await page.getByRole("radio", { name: "Fair", exact: true }).click();
    await expect(page.getByRole("radio", { name: "Fair", exact: true })).toBeChecked();
  });
});
