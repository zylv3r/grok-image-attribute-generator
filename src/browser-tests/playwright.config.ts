import { defineConfig } from "@playwright/test";
import path from "node:path";
import os from "node:os";
export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 7000 },
  outputDir: path.join(
    process.env.TMPDIR || os.tmpdir(),
    "atelier-playwright-results",
  ),
  reporter: [["list"]],
  use: {
    baseURL: "https://atelier.test",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
      args: ["--no-sandbox"],
    },
  },
});
