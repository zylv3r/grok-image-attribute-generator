// REAL API / PAID GENERATION. Parent-only opt-in. No routes, interception, or mocks.
import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
if (process.env.RUN_PAID_GENERATION !== "1") {
  console.error(
    "Parent-only script: set RUN_PAID_GENERATION=1 and STUDIO_BASE_URL to the live server. This submits one paid image job.",
  );
  process.exit(2);
}
const baseURL = process.env.STUDIO_BASE_URL;
if (!baseURL || !/^https?:\/\//.test(baseURL))
  throw new Error("STUDIO_BASE_URL is required.");
const output = path.join(
  process.env.TMPDIR || os.tmpdir(),
  "atelier-actual-generation",
);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  headless: true,
  args: ["--no-sandbox"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const consoleErrors = [];
page.on("pageerror", (e) => consoleErrors.push(e.message));
try {
  await page.goto(baseURL);
  await page
    .getByRole("heading", { name: "A vision, in the details." })
    .waitFor();
  await page.getByRole("button", { name: "Reset composition" }).click();
  // Pick a real live-library value using its rendered accessible control.
  const firstChoice = page
    .locator(".attribute")
    .first()
    .getByRole("radio")
    .first();
  await firstChoice.click();
  await page
    .getByLabel("Your creative note", { exact: false })
    .fill("An elegant editorial composition with soft natural light.");
  const previewResponse = page.waitForResponse(
    (r) => r.url().endsWith("/api/preview") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Preview prompt & plans" }).click();
  const preview = await (await previewResponse).json();
  assert.equal(preview.plans.length, 1);
  assert.ok(preview.plans[0].prompt);
  const submitResponse = page.waitForResponse(
    (r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Generate 1 image", exact: true })
    .click();
  const submitted = await submitResponse;
  assert.equal(submitted.status(), 202);
  const { id } = await submitted.json();
  assert.ok(id);
  // Observe the same real responses used by the browser's job poller.
  const done = await page.waitForResponse(
    async (r) => {
      if (!r.url().endsWith(`/api/jobs/${encodeURIComponent(id)}`))
        return false;
      const j = await r.json();
      return ["completed", "partial", "failed"].includes(j.status);
    },
    { timeout: 600_000 },
  );
  const job = await done.json();
  await writeFile(path.join(output, "job.json"), JSON.stringify(job, null, 2));
  assert.equal(job.completed, 1, `Job failed: ${JSON.stringify(job.errors)}`);
  assert.equal(job.failed, 0);
  assert.ok(job.results[0].url);
  const result = job.results[0];
  const imageResponse = await page.request.get(
    new URL(result.url, baseURL).href,
  );
  assert.ok(imageResponse.ok());
  assert.match(imageResponse.headers()["content-type"], /^image\//);
  await page
    .getByRole("button", { name: `Open generated image ${result.id}` })
    .click();
  await page.getByRole("dialog").waitFor();
  await page.screenshot({
    path: path.join(output, "real-generation-detail.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Close image details" }).click();
  await page.getByRole("tab", { name: "Gallery", exact: true }).click();
  await page
    .getByRole("button", { name: `Open image ${result.id}`, exact: true })
    .waitFor();
  await page.screenshot({
    path: path.join(output, "real-gallery.png"),
    fullPage: true,
  });
  assert.deepEqual(consoleErrors, []);
  console.log(`REAL API generation verified. Evidence: ${output}`);
} finally {
  await browser.close();
}
