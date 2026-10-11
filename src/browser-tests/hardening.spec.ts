import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockAPI, library, guide } from "./fixtures";
import type { Attribute } from "../types";

async function openAttribute(page: import("@playwright/test").Page, name: string) {
  const region = page.getByRole("region", { name, exact: true });
  const heading = region.getByRole("button", { name: `Edit ${name}`, exact: true });
  if (await heading.getAttribute("aria-expanded") === "false") await heading.click();
  return region;
}

test.describe("Frontend hardening — simulated API, no provider calls", () => {
  test("radio arrows select and focus immediately, wrap in both directions, and reach unset", async ({ page }) => {
    await mockAPI(page);
    await page.goto("/");
    const tone = await openAttribute(page, "Skin Tone");
    const porcelain = tone.getByRole("radio", { name: "Porcelain", exact: true });
    const fair = tone.getByRole("radio", { name: "Fair", exact: true });
    const unset = tone.getByRole("radio", { name: "Unset Skin Tone", exact: true });
    await porcelain.click();
    for (const key of ["ArrowRight", "ArrowDown"]) {
      await porcelain.click();
      await page.keyboard.press(key);
      await expect(fair).toBeFocused();
      await expect(fair).toBeChecked();
      await expect(porcelain).not.toBeChecked();
    }
    await page.keyboard.press("ArrowRight");
    await expect(unset).toBeFocused();
    await expect(unset).toBeChecked();
    await page.keyboard.press("ArrowRight");
    await expect(porcelain).toBeFocused();
    await expect(porcelain).toBeChecked();
    await page.keyboard.press("ArrowLeft");
    await expect(unset).toBeChecked();
    await page.keyboard.press("Home");
    await expect(porcelain).toBeChecked();
    await page.keyboard.press("End");
    await expect(unset).toBeChecked();
    await page.keyboard.press("ArrowUp");
    await expect(fair).toBeChecked();
    await expect(fair).toHaveAccessibleDescription(/Illustrative fair direction/);
  });

  test("empty Vary survives category changes and reload; single allowed value has honest hint and checkbox/unset state", async ({ page }) => {
    const api = await mockAPI(page);
    await page.goto("/");
    let tone = await openAttribute(page, "Skin Tone");
    await tone.getByRole("button", { name: "Vary", exact: true }).click();
    await expect(tone.getByRole("button", { name: "Unset Skin Tone" })).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("navigation", { name: "Library categories" }).getByRole("button", { name: "Pose", exact: false }).click();
    await page.getByRole("navigation", { name: "Library categories" }).getByRole("button", { name: "Skin & Phenotype", exact: false }).click();
    await expect(tone.getByRole("button", { name: "Vary", exact: true })).toHaveAttribute("aria-pressed", "true");
    await page.reload();
    tone = await openAttribute(page, "Skin Tone");
    await expect(tone.getByRole("button", { name: "Vary", exact: true })).toHaveAttribute("aria-pressed", "true");
    const porcelain = tone.getByRole("checkbox", { name: "Porcelain", exact: true });
    await porcelain.focus();
    await page.keyboard.press("Space");
    await expect(porcelain).toBeChecked();
    await expect(porcelain).toHaveAccessibleDescription(/One allowed value is deliberate/);
    await expect(tone.getByRole("button", { name: "Unset Skin Tone" })).toHaveAttribute("aria-pressed", "false");
    await page.getByRole("button", { name: "Preview prompt & plans" }).click();
    await expect(page.getByLabel("Prompt preview")).toContainText("1 combination");
    expect(api.previewPayloads.at(-1)?.whitelist.skin_tone).toEqual(["porcelain"]);
    expect(api.previewPayloads.at(-1)).not.toHaveProperty("attributeModes");
    await tone.getByRole("checkbox", { name: "Fair", exact: true }).click();
    await tone.getByRole("button", { name: "Lock", exact: true }).click();
    await expect(tone.getByRole("status")).toContainText("removed 1 allowed value");
    await expect(tone.getByRole("radio", { name: "Porcelain", exact: true })).toBeChecked();
    await tone.getByRole("button", { name: "Vary", exact: true }).click();
    await tone.getByRole("checkbox", { name: "Fair", exact: true }).click();
    await page.getByRole("combobox", { name: "Generation mode" }).click();
    await page.getByRole("option", { name: "Single · one composition" }).click();
    await expect(page.getByRole("complementary", { name: "Generation settings" }).getByRole("status")).toContainText("1 allowed value removed");
  });

  test("description-only and global searches expose values and preserve selections with category counts", async ({ page }) => {
    await mockAPI(page);
    const custom = structuredClone(library);
    custom.categories[0].attributes[0].description = "Unique pigment guidance";
    await page.route("**/api/library", (route) => route.fulfill({ json: custom }));
    await page.goto("/");
    await page.getByRole("radio", { name: "Porcelain", exact: true }).click();
    await page.getByLabel("Search library").fill("unique pigment");
    await expect(page.getByRole("radio", { name: "Fair", exact: true })).toBeVisible();
    await page.getByLabel("Search library").fill("fair");
    await expect(page.getByRole("radio", { name: "Porcelain", exact: true })).toBeChecked();
    await expect(page.getByLabel("1 matching values", { exact: true })).toBeVisible();
    await page.getByLabel("Search library").fill("RAW");
    await expect(page.getByRole("heading", { name: "Technical & Realism", exact: true })).toBeVisible();
    await expect(page.getByRole("radio", { name: "RAW Camera", exact: true })).toBeVisible();
    await page.getByRole("navigation", { name: "Library categories" }).getByRole("button", { name: "Skin & Phenotype", exact: false }).click();
    await expect(page.getByRole("radio", { name: "Porcelain", exact: true })).toBeChecked();
  });

  test("95 scenery and 70 pose values are bounded, searchable, and reachable; collapsed regions open and jump works", async ({ page }) => {
    await mockAPI(page);
    function large(id: string, name: string, count: number): Attribute {
      return { id, name, type: "exclusive", thumbnail_url: guide, values: Array.from({ length: count }, (_, i) => ({ id: `${id}_${i}`, name: `${name} ${i + 1}`, steers: `Direction ${i + 1}`, thumbnail_url: guide })) };
    }
    const custom = { categories: [{ id: "large", name: "Large library", attributes: [large("scenery", "Scenery", 95), large("pose", "Pose", 70), large("camera", "Camera", 2)] }] };
    await page.route("**/api/library", (route) => route.fulfill({ json: custom }));
    await page.goto("/");
    const scenery = page.getByRole("region", { name: "Scenery", exact: true });
    await expect(scenery.getByRole("radio")).toHaveCount(13);
    await scenery.getByRole("radio", { name: "Scenery 1", exact: true }).click();
    for (let i = 0; i < 7; i++) await scenery.getByRole("button", { name: /Show more Scenery values/ }).click();
    await expect(scenery.getByRole("radio", { name: "Scenery 95", exact: true })).toBeVisible();
    await scenery.getByRole("radio", { name: "Scenery 95", exact: true }).click();
    await page.getByLabel("Search library").fill("Scenery 44");
    await expect(scenery.getByRole("radio", { name: "Scenery 95", exact: true })).toBeChecked();
    await expect(scenery.getByRole("radio", { name: "Scenery 44", exact: true })).toBeVisible();
    await page.getByLabel("Search library").fill("");
    const camera = page.getByRole("region", { name: "Camera", exact: true });
    await expect(camera.getByRole("button", { name: "Edit Camera" })).toHaveAttribute("aria-expanded", "false");
    await camera.click();
    await expect(camera.getByRole("radio", { name: "Camera 1", exact: true })).toBeVisible();
    await page.getByLabel("Jump to attribute").selectOption("pose");
    await expect(page.getByRole("button", { name: "Edit Pose", exact: true })).toBeFocused();
    await page.getByLabel("Search library").fill("Pose 70");
    await expect(page.getByRole("radio", { name: "Pose 70", exact: true })).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test("approximate preview count, sampling seed, and billed call labels follow backend semantics", async ({ page }) => {
    await mockAPI(page);
    await page.route("**/api/preview", (route) => route.fulfill({ json: { plans: [{ selections: {}, prompt: "Simulated compatible plan" }], combination_count: 256, combination_count_exact: false, combination_count_metadata: { method: "bounded_search_lower_bound", unrestricted_product_count: 5000, visited_nodes: 1000, node_limit: 20000, result_limit: 256 } } }));
    await page.goto("/");
    await page.getByRole("button", { name: "Preview prompt & plans" }).click();
    await expect(page.getByLabel("Prompt preview")).toContainText("At least 256 combinations");
    await expect(page.getByLabel("Prompt preview")).toContainText("More may exist");
    await expect(page.getByLabel("Selection sampling seed", { exact: false })).toHaveAccessibleDescription(/does not make provider images deterministic/);
    await expect(page.locator(".generation-note")).toContainText("1 billed image call");
  });

  test("gallery filters reset pages, URL state reloads, selected filters survive search, and reuse is undoable", async ({ page }) => {
    const api = await mockAPI(page);
    await page.goto("/");
    await page.getByRole("radio", { name: "Fair", exact: true }).click();
    await page.getByRole("tab", { name: "Gallery", exact: true }).click();
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByRole("button", { name: "Open image 25", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Attribute filters", exact: false }).click();
    await page.getByRole("checkbox", { name: "Skin Tone: Fair", exact: true }).click();
    await page.getByLabel("Search filter values").fill("camera");
    await expect(page.getByRole("checkbox", { name: "Skin Tone: Fair", exact: true })).toBeChecked();
    await page.getByRole("checkbox", { name: "Camera: RAW Camera", exact: true }).click();
    await page.getByRole("button", { name: "Show matching images" }).click();
    await expect.poll(() => api.galleryQueries.at(-1)?.get("page")).toBe("1");
    await page.getByLabel("Search gallery").fill("quiet");
    await expect.poll(() => new URL(page.url()).searchParams.get("gallery_q")).toBe("quiet");
    await page.reload();
    await expect(page.getByLabel("Search gallery")).toHaveValue("quiet");
    await expect(page.getByRole("button", { name: "Remove filter Skin Tone: Fair" })).toBeVisible();
    await page.getByRole("button", { name: "Remove filter Camera: RAW Camera" }).click();
    await expect.poll(() => api.galleryQueries.at(-1)?.get("filters")).toBe(JSON.stringify({ skin_tone: ["fair"] }));
    await page.getByRole("button", { name: "Open image 1", exact: true }).click();
    await expect(page.getByRole("dialog").getByRole("img")).toHaveAttribute("alt", "Porcelain · 1:1");
    await page.getByRole("button", { name: "Reuse selections" }).click();
    await expect(page.getByRole("radio", { name: "Porcelain", exact: true })).toBeChecked();
    await page.getByRole("button", { name: "Undo reuse" }).click();
    await expect(page.getByRole("radio", { name: "Fair", exact: true })).toBeChecked();
  });

  for (const width of [1440, 390]) test(`axe has no violations in studio, gallery, and filters at ${width}px`, async ({ page }) => {
    await mockAPI(page);
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Skin & Phenotype", exact: true })).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.getByRole("tab", { name: "Gallery", exact: true }).click();
    await expect(page.getByRole("button", { name: "Open image 1", exact: true })).toBeVisible();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.getByRole("button", { name: "Attribute filters", exact: false }).click();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  });
});
