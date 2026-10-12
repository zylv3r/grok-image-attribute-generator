import { test, expect, type Page } from "@playwright/test";
import { mockAPI } from "./fixtures";
import type { Preset } from "../types";

// Shared simulated installation: contexts never share localStorage. Real handler/restart
// coverage is in test_presets.py; this fixture can also drop a committed response.
function installation() {
  const presets: Preset[] = [], requests = new Map<string, Preset>(), imports = new Map<string, Preset>();
  const state = { failSave: false, loseResponse: false, failImport: false, rawImports: [] as unknown[], savePayloads: [] as unknown[] };
  async function attach(page: Page) {
    const api = await mockAPI(page);
    await page.route("**/api/presets**", async route => {
      const req = route.request(), path = new URL(req.url()).pathname;
      if (req.method() === "GET") return route.fulfill({ json: { presets } });
      if (req.method() === "DELETE") {
        const index = presets.findIndex(p => p.id === path.split("/").at(-1));
        if (index >= 0) presets.splice(index, 1);
        return route.fulfill({ json: { presets } });
      }
      const body = req.postDataJSON();
      if (path.endsWith("/import")) {
        state.rawImports.push(body);
        if (state.failImport) return route.fulfill({ status: 503, json: { error: "Import offline" } });
        for (const record of body.presets) {
          const digest = JSON.stringify(record);
          if (!imports.has(digest)) {
            const p = { ...record, id: `import-${imports.size}`, schema_version: 1, catalog_hash: "fixture", created_at: "now", updated_at: "now" };
            imports.set(digest, p); presets.push(p);
          }
        }
        return route.fulfill({ json: { presets, warnings: [] } });
      }
      state.savePayloads.push(body);
      if (state.failSave) return route.fulfill({ status: 503, json: { error: "Save offline" } });
      let preset = requests.get(body.request_key);
      if (!preset) {
        preset = { id: `server-${requests.size}`, name: body.name, draft: body.draft, schema_version: 1, catalog_hash: "fixture", created_at: "now", updated_at: "now" };
        requests.set(body.request_key, preset!); presets.push(preset!);
      }
      if (state.loseResponse) { state.loseResponse = false; return route.abort(); }
      return route.fulfill({ status: 201, json: preset });
    });
    return api;
  }
  return { presets, requests, state, attach };
}
async function open(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Presets", exact: true }).click();
}

test("save survives fresh independent contexts/origins with storage and crypto denied", async ({ browser }) => {
  const store = installation();
  for (const origin of ["https://atelier.test", "https://renewed.test"]) {
    const context = await browser.newContext({ baseURL: "https://atelier.test" });
    const page = await context.newPage();
    await store.attach(page);
    await page.addInitScript(() => {
      Object.defineProperty(Storage.prototype, "getItem", { value: () => { throw Error("denied"); } });
      Object.defineProperty(Storage.prototype, "setItem", { value: () => { throw Error("denied"); } });
      Object.defineProperty(crypto, "randomUUID", { value: undefined });
    });
    await page.goto(origin);
    if (!store.presets.length) {
      await page.getByRole("radio", { name: "Fair", exact: true }).click();
      await page.getByRole("button", { name: "Presets", exact: true }).click();
      await page.getByLabel("Name this direction").fill("Shared studio");
      await page.getByRole("button", { name: "Save preset", exact: true }).click();
      await expect(page.getByRole("status")).toContainText("Preset saved");
    } else {
      await page.getByRole("button", { name: "Presets", exact: true }).click();
      await page.getByRole("button", { name: "Apply Shared studio", exact: true }).click();
      await expect(page.getByRole("radio", { name: "Fair", exact: true })).toBeChecked();
    }
    await context.close();
  }
  expect(store.presets).toHaveLength(1);
});

test("failed save retains name and stable retry key; lost commit response creates one record", async ({ page }) => {
  const store = installation(); const api = await store.attach(page); store.state.failSave = true;
  await open(page);
  await page.getByLabel("Name this direction").fill("Retry me");
  await page.getByRole("button", { name: "Save preset", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Save failed");
  await expect(page.getByLabel("Name this direction")).toHaveValue("Retry me");
  await page.getByRole("button", { name: "Close presets" }).click();
  await page.getByRole("radio", { name: "Fair", exact: true }).click();
  await page.getByRole("button", { name: "Presets", exact: true }).click();
  store.state.failSave = false; store.state.loseResponse = true;
  await page.getByRole("button", { name: "Retry save", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Save failed");
  await page.getByRole("button", { name: "Retry save", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Preset saved");
  expect(store.state.savePayloads).toHaveLength(3);
  expect(store.state.savePayloads[1]).toEqual(store.state.savePayloads[0]);
  expect(store.state.savePayloads[2]).toEqual(store.state.savePayloads[0]);
  expect(store.requests.size).toBe(1); expect(store.presets).toHaveLength(1);
  expect(api.jobPayloads).toHaveLength(0);
});

test("raw legacy survives failed import and needs explicit apply-known consent", async ({ page }) => {
  const store = installation(); await store.attach(page); store.state.failImport = true;
  const raw = JSON.stringify([{ id: "old", name: "Legacy", draft: { selections: { skin_tone: ["fair"], retired: ["lost"] }, future: { raw: true } }, extra: "keep" }]);
  await page.addInitScript(raw => localStorage.setItem("atelier.presets.v1", raw), raw);
  await open(page);
  await expect(page.getByText(/Import needs attention/)).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("atelier.presets.v1"))).toBe(raw);
  expect(store.state.rawImports[0]).toEqual({ raw_text: raw, presets: JSON.parse(raw) });
  store.state.failImport = false;
  await page.getByRole("button", { name: "Retry import" }).click();
  await page.getByRole("button", { name: "Apply Legacy", exact: true }).click();
  await expect(page.getByLabel("Unresolved preset controls")).toContainText("retired");
  await expect(page.getByLabel("Unresolved preset controls")).toContainText("future");
  await page.getByRole("button", { name: "Apply known controls", exact: true }).click();
  await expect(page.getByRole("radio", { name: "Fair", exact: true })).toBeChecked();
  expect(await page.evaluate(() => localStorage.getItem("atelier.presets.v1"))).toBe(raw);
});
