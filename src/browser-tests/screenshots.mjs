// Read-only real-server screenshots. No generation, interception, or mock data.
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
const baseURL = process.env.STUDIO_BASE_URL || "http://127.0.0.1:8123";
const output = path.join(
  process.env.TMPDIR || os.tmpdir(),
  "atelier-screenshots",
);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
  headless: true,
  args: ["--no-sandbox"],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  await page.goto(baseURL);
  await page
    .getByRole("heading", { name: "A vision, in the details." })
    .waitFor();
  await page.screenshot({
    path: path.join(output, "studio-desktop.png"),
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Gallery", exact: true }).click();
  await page
    .locator(".gallery-count")
    .filter({ hasNotText: "Loading" })
    .waitFor();
  await page.screenshot({
    path: path.join(output, "gallery-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: "Studio", exact: true }).click();
  await page.screenshot({
    path: path.join(output, "studio-mobile.png"),
    fullPage: true,
  });
  console.log(`Read-only screenshots: ${output}`);
} finally {
  await browser.close();
}
