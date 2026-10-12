import { test, expect } from "@playwright/test";
import { mockAPI, library } from "./fixtures";

test.describe("SIMULATED API — browser behavior (no paid generation)", () => {
  test("exclusive keyboard selection, explicit boolean off, multi, and disjoint variation payloads", async ({
    page,
  }) => {
    const api = await mockAPI(page);
    await page.goto("/");
    const tone = page.getByRole("region", { name: "Skin Tone", exact: true });
    await tone.getByRole("radio", { name: "Porcelain", exact: true }).click();
    await page.keyboard.press("ArrowRight");
    await expect(
      tone.getByRole("radio", { name: "Fair", exact: true }),
    ).toBeChecked();
    await expect(
      tone.getByRole("radio", { name: "Porcelain", exact: true }),
    ).not.toBeChecked();
    const texture = page.getByRole("region", {
      name: "Micro-Texture Lock",
      exact: true,
    });
    if (await texture.getByRole("button", { name: "Edit Micro-Texture Lock" }).getAttribute("aria-expanded") === "false") await texture.getByRole("button", { name: "Edit Micro-Texture Lock" }).click();
    await texture
      .getByRole("radio", { name: "Standard Skin", exact: true })
      .click();
    await page.getByRole("button", { name: "Preview prompt & plans" }).click();
    await expect(page.getByLabel("Prompt preview")).toContainText(
      "1 combination",
    );
    expect(api.previewPayloads.at(-1)?.selections.micro_texture).toEqual([
      "off",
    ]);
    await texture
      .getByRole("radio", { name: "Unset Micro-Texture Lock" })
      .click();
    await tone.getByRole("button", { name: "Vary", exact: true }).click();
    await tone
      .getByRole("checkbox", { name: "Porcelain", exact: true })
      .click();
    await page.getByRole("button", { name: "Preview prompt & plans" }).click();
    await expect(page.getByLabel("Prompt preview")).toBeVisible();
    const draft = api.previewPayloads.at(-1)!;
    expect(draft.selections.skin_tone).toBeUndefined();
    expect(draft.selections.micro_texture).toBeUndefined();
    expect(draft.whitelist.skin_tone).toEqual(["fair", "porcelain"]);
    await tone.getByRole("button", { name: "Lock", exact: true }).click();
    await page
      .getByRole("navigation", { name: "Library categories" })
      .getByRole("button", { name: "Pose" })
      .click();
    const pose = page.getByRole("region", { name: "Pose", exact: true });
    await pose.getByRole("checkbox", { name: "Standing", exact: true }).click();
    await pose.getByRole("checkbox", { name: "Sitting", exact: true }).focus();
    await page.keyboard.press("Space");
    await page.getByRole("button", { name: "Preview prompt & plans" }).click();
    await expect(page.getByLabel("Prompt preview")).toBeVisible();
    expect(api.previewPayloads.at(-1)?.selections.pose).toEqual([
      "standing",
      "sitting",
    ]);
    expect(api.previewPayloads.at(-1)?.whitelist.skin_tone).toBeUndefined();
  });

  test("safe storage, stale ID pruning, save/apply presets and reset", async ({
    page,
  }) => {
    await mockAPI(page);
    await page.addInitScript(() => {
      localStorage.setItem(
        "atelier.draft.v1",
        JSON.stringify({
          selections: {
            removed: ["old"],
            skin_tone: ["gone", "fair"],
            micro_texture: ["off"],
          },
          whitelist: { skin_tone: ["porcelain"], missing: ["old"] },
        }),
      );
      localStorage.setItem("atelier.presets.v1", "{broken");
    });
    await page.goto("/");
    await expect(
      page.getByRole("radio", { name: "Fair", exact: true }),
    ).toBeChecked();
    await page.getByRole("button", { name: "Presets", exact: true }).click();
    await page.getByLabel("Name this direction").fill("Saved direction");
    await page.getByRole("button", { name: "Save preset" }).click();
    await expect(page.getByRole("status")).toContainText("Preset saved");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Reset composition" }).click();
    await expect(
      page.getByRole("radio", { name: "Unset Skin Tone" }),
    ).toBeChecked();
    await page.getByRole("button", { name: "Presets", exact: true }).click();
    await page.getByRole("button", { name: "Apply Saved direction" }).click();
    await expect(
      page.getByRole("radio", { name: "Fair", exact: true }),
    ).toBeChecked();
    const saved = await page.evaluate(() =>
      JSON.parse(localStorage.getItem("atelier.draft.v1")!),
    );
    // Raw cached compositions must survive unsupported-ID discovery until the
    // operator explicitly applies a migration; presets apply to the editor only.
    expect(saved.selections.removed).toEqual(["old"]);
    expect(saved.whitelist.skin_tone).toEqual(["porcelain"]);
  });

  test("corrupt draft does not break startup", async ({ page }) => {
    await mockAPI(page);
    await page.addInitScript(() =>
      localStorage.setItem("atelier.draft.v1", "{bad JSON"),
    );
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "A vision, in the details." }),
    ).toBeVisible();
  });

  test("generation settings, bounded count, preview, duplicate suppression and partial failures", async ({
    page,
  }) => {
    const api = await mockAPI(page);
    await page.goto("/");
    await page.getByRole("combobox", { name: "Generation mode" }).click();
    await page.getByRole("option", { name: "Repeat · same direction" }).click();
    await page.getByLabel("Images", { exact: true }).fill("25");
    await expect(page.getByLabel("Images", { exact: true })).toHaveValue("24");
    await page.getByLabel("Images", { exact: true }).fill("2");
    await page
      .getByRole("combobox", { name: "Aspect ratio", exact: true })
      .click();
    await page.getByRole("option", { name: "3:2", exact: true }).click();
    await page.getByLabel("Selection sampling seed", { exact: false }).fill("abc");
    await expect(
      page.getByRole("button", { name: "Generate 2 images" }),
    ).toBeDisabled();
    await page.getByLabel("Selection sampling seed", { exact: false }).fill("123");
    await page
      .getByLabel("Your creative note", { exact: false })
      .fill("A simulated creative note");
    await page.getByRole("button", { name: "Preview prompt & plans" }).click();
    await expect(page.getByLabel("Prompt preview")).toContainText("2 plans");
    expect(api.previewPayloads.at(-1)).toMatchObject({
      mode: "repeat",
      n: 2,
      aspect_ratio: "3:2",
      seed: 123,
    });
    await page.getByRole("button", { name: "Generate 2 images" }).dblclick();
    await expect(page.getByLabel("Generation progress")).toContainText(
      "Partially completed",
    );
    await expect(page.getByLabel("Generation progress")).toContainText(
      "1 completed · 1 failed · 2 total",
    );
    await expect(page.getByLabel("Generation progress")).toContainText(
      "Simulated provider failure",
    );
    expect(api.jobPayloads).toHaveLength(1);
  });

  test("all library filters, AND/OR payload, debounce, true server pagination and detail keyboard/reuse", async ({
    page,
  }) => {
    const api = await mockAPI(page);
    await page.goto("/");
    await page.getByRole("tab", { name: "Gallery", exact: true }).click();
    await expect(
      page.getByRole("button", { name: /^Open image / }),
    ).toHaveCount(24);
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Open image 25", exact: true }),
    ).toBeVisible();
    expect(api.galleryQueries.at(-1)?.get("page")).toBe("2");
    expect(api.galleryQueries.at(-1)?.get("page_size")).toBe("24");
    await page.getByRole("button", { name: "Attribute filters" }).click();
    while (await page.locator("details.filter-attribute:not([open]) > summary").count()) await page.locator("details.filter-attribute:not([open]) > summary").first().click();
    for (const category of library.categories)
      for (const attr of category.attributes)
        for (const value of attr.values)
          await expect(
            page.getByRole("checkbox", {
              name: `${attr.name}: ${value.name}`,
              exact: true,
            }),
          ).toBeAttached();
    await page.getByRole("checkbox", { name: "Skin Tone: Porcelain" }).click();
    await page.getByRole("checkbox", { name: "Skin Tone: Fair" }).click();
    await page.getByRole("checkbox", { name: "Camera: RAW Camera" }).click();
    await page.getByRole("button", { name: "Show matching images" }).click();
    await expect(
      page.getByRole("button", { name: "Open image 1", exact: true }),
    ).toBeVisible();
    expect(JSON.parse(api.galleryQueries.at(-1)!.get("filters")!)).toEqual({
      skin_tone: ["porcelain", "fair"],
      camera: ["on"],
    });
    expect(api.galleryQueries.at(-1)?.get("page")).toBe("1");
    await page.getByLabel("Search gallery").fill("quiet");
    await expect.poll(() => api.galleryQueries.at(-1)?.get("q")).toBe("quiet");
    await page.getByRole("combobox", { name: "Gallery aspect ratio" }).click();
    await page.getByRole("option", { name: "1:1", exact: true }).click();
    await expect
      .poll(() => api.galleryQueries.at(-1)?.get("aspect_ratio"))
      .toBe("1:1");
    const card = page.getByRole("button", {
      name: "Open image 1",
      exact: true,
    });
    await card.click();
    await expect(page.getByRole("dialog")).toContainText("1024 × 1024");
    await expect(
      page.getByRole("link", { name: "Download original" }),
    ).toHaveAttribute("download", "atelier-1");
    await page.keyboard.press("Escape");
    await expect(card).toBeFocused();
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Reuse selections" }).click();
    await expect(
      page.getByRole("radio", { name: "Porcelain", exact: true }),
    ).toBeChecked();
    await expect(
      page.getByRole("tab", { name: "Studio", exact: true }),
    ).toHaveAttribute("data-state", "active");
  });

  test("library, preview and gallery errors can recover", async ({ page }) => {
    await mockAPI(page);
    let fail = true;
    await page.route("**/api/library", (route) =>
      route.fulfill(
        fail
          ? { status: 503, json: { error: "Simulated library outage" } }
          : { json: library },
      ),
    );
    await page.goto("/");
    await expect(page.getByRole("alert")).toContainText(
      "Simulated library outage",
    );
    fail = false;
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Skin & Phenotype", exact: true }),
    ).toBeVisible();
    await page.route("**/api/preview", (route) =>
      route.fulfill({
        status: 422,
        json: { error: "Simulated invalid variation" },
      }),
    );
    await page.getByRole("button", { name: "Preview prompt & plans" }).click();
    await expect(page.getByRole("alert")).toContainText(
      "Simulated invalid variation",
    );
    await page.route("**/api/gallery?**", (route) =>
      route.fulfill({
        status: 500,
        json: { error: "Simulated gallery outage" },
      }),
    );
    await page.getByRole("tab", { name: "Gallery", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText(
      "Simulated gallery outage",
    );
    await page.unroute("**/api/gallery?**");
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(
      page.getByRole("button", { name: /^Open image / }),
    ).toHaveCount(24);
  });

  test("poll errors retry status without duplicate generation; job survives tab changes", async ({
    page,
  }) => {
    const api = await mockAPI(page);
    let fail = true;
    await page.route("**/api/jobs/simulated-job", async (route) => {
      if (fail)
        return route.fulfill({
          status: 503,
          json: { error: "Simulated status outage" },
        });
      return route.fallback();
    });
    await page.goto("/");
    await page
      .getByRole("button", { name: "Generate 1 image", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "Simulated status outage",
    );
    await expect(
      page.getByRole("button", { name: "Generation in progress", exact: true }),
    ).toBeDisabled();
    await page.getByRole("tab", { name: "Gallery", exact: true }).click();
    await page.getByRole("tab", { name: "Studio", exact: true }).click();
    fail = false;
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(page.getByLabel("Generation progress")).toContainText(
      "Completed",
    );
    expect(api.jobPayloads).toHaveLength(1);
  });

  test("mobile category navigation is readable without horizontal overflow", async ({
    page,
  }) => {
    await mockAPI(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.getByRole("button", { name: "Browse categories" }).click();
    await page
      .getByRole("navigation", { name: "Library categories" })
      .getByRole("button", { name: "Technical & Realism" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Technical & Realism", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `${process.env.TMPDIR || "/tmp"}/atelier-simulated-mobile.png`,
      fullPage: true,
    });
  });
});
