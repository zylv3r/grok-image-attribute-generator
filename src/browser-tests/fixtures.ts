import { readFile } from "node:fs/promises";
import path from "node:path";
import { Page } from "@playwright/test";
import { Draft, GalleryResponse, ImageRecord, Library, Preset } from "../types";
export const guide =
  "data:image/svg+xml," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260"><defs><linearGradient id="a"><stop stop-color="#ded9c7"/><stop offset="1" stop-color="#758469"/></linearGradient></defs><rect width="400" height="260" fill="url(#a)"/><ellipse cx="200" cy="165" rx="65" ry="135" fill="#fff" opacity=".22"/><path d="M0 220Q160 80 400 200V260H0" fill="#3b5039" opacity=".3"/></svg>',
  );
const value = (id: string, name: string) => ({
  id,
  name,
  steers: `Direction for ${name}`,
  description: `Illustrative ${name.toLowerCase()} direction.`,
  thumbnail_url: guide,
});
export const library: Library = {
  categories: [
    {
      id: "skin",
      name: "Skin & Phenotype",
      attributes: [
        {
          id: "skin_tone",
          name: "Skin Tone",
          type: "exclusive",
          thumbnail_url: guide,
          values: [value("porcelain", "Porcelain"), value("fair", "Fair")],
        },
        {
          id: "micro_texture",
          name: "Micro-Texture Lock",
          type: "boolean",
          thumbnail_url: guide,
          values: [
            value("on", "Full Micro-Texture"),
            value("off", "Standard Skin"),
          ],
        },
      ],
    },
    {
      id: "pose",
      name: "Pose",
      attributes: [
        {
          id: "pose",
          name: "Pose",
          type: "multi",
          thumbnail_url: guide,
          values: [value("standing", "Standing"), value("sitting", "Sitting")],
        },
      ],
    },
    {
      id: "technical",
      name: "Technical & Realism",
      attributes: [
        {
          id: "camera",
          name: "Camera",
          type: "boolean",
          thumbnail_url: guide,
          values: [value("on", "RAW Camera")],
        },
        {
          id: "age",
          name: "Age",
          type: "exclusive",
          thumbnail_url: guide,
          values: [value("adult", "Adult")],
        },
      ],
    },
  ],
};
export function image(id: string): ImageRecord {
  return {
    id,
    url: guide,
    thumbnail_url: guide,
    prompt: `Simulated composition ${id}`,
    selections: { skin_tone: ["porcelain"] },
    width: 1024,
    height: 1024,
    aspect_ratio: "1:1",
    created_at: "2026-10-10T12:00:00Z",
  };
}
export async function mockAPI(page: Page) {
  const previewPayloads: Draft[] = [],
    jobPayloads: Draft[] = [],
    galleryQueries: URLSearchParams[] = [];
  let polls = 0;
  const presets: Preset[] = [];
  const presetRequests = new Map<string, Preset>();
  // Serve the real compiled frontend in the browser without opening a socket.
  await page.route(/^https:\/\/(?:atelier|renewed)\.test\//, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/")) return route.fallback();
    const file = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
    if (file !== "index.html" && !/^assets\/[a-zA-Z0-9_.-]+$/.test(file))
      return route.abort();
    const contentType = file.endsWith(".js")
      ? "application/javascript"
      : file.endsWith(".css")
        ? "text/css"
        : file.endsWith(".woff2")
          ? "font/woff2"
          : "text/html";
    return route.fulfill({
      body: await readFile(path.resolve("dist", file)),
      contentType,
    });
  });
  await page.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    if (url.pathname === "/api/presets/import")
      return route.fulfill({ json: { presets, warnings: request.postDataJSON().raw_text === "{broken" ? ["Malformed legacy text archived for recovery."] : [] } });
    if (url.pathname === "/api/presets") {
      if (request.method() === "GET") return route.fulfill({ json: { presets } });
      const body = request.postDataJSON();
      let preset = presetRequests.get(body.request_key);
      if (!preset) {
        preset = { id: `preset-${presetRequests.size}`, name: body.name, draft: body.draft, schema_version: 1, catalog_hash: "fixture", created_at: "now", updated_at: "now" };
        presetRequests.set(body.request_key, preset); presets.push(preset);
      }
      return route.fulfill({ status: 201, json: preset });
    }
    if (url.pathname.startsWith("/api/presets/") && request.method() === "DELETE") {
      const index = presets.findIndex(p => p.id === url.pathname.split("/").at(-1));
      if (index >= 0) presets.splice(index, 1);
      return route.fulfill({ json: { presets } });
    }
    if (url.pathname === "/api/library")
      return route.fulfill({ json: library });
    if (url.pathname === "/api/preview") {
      const draft = request.postDataJSON() as Draft;
      previewPayloads.push(draft);
      const combinationCount = Object.entries(draft.whitelist).reduce(
        (count, [id, ids]) => {
          const attr = library.categories
            .flatMap((c) => c.attributes)
            .find((a) => a.id === id);
          return (
            count *
            (attr?.type === "multi"
              ? ids.length + (ids.length * (ids.length - 1)) / 2
              : ids.length)
          );
        },
        1,
      );
      return route.fulfill({
        json: {
          plans: Array.from({ length: draft.n }, (_, i) => ({
            selections: draft.selections,
            prompt: `Simulated server plan ${i + 1}. ${draft.extra_prompt}`,
          })),
          combination_count: combinationCount,
        },
      });
    }
    if (url.pathname === "/api/jobs") {
      jobPayloads.push(request.postDataJSON());
      polls = 0;
      return route.fulfill({ status: 202, json: { id: "simulated-job" } });
    }
    if (url.pathname === "/api/jobs/simulated-job") {
      polls++;
      const total = jobPayloads.at(-1)?.n || 1;
      const failed = polls === 1 || total === 1 ? 0 : 1;
      const completed = polls === 1 ? 0 : total - failed;
      return route.fulfill({
        json: {
          id: "simulated-job",
          status: polls === 1 ? "running" : failed ? "partial" : "completed",
          total,
          completed,
          failed,
          results: Array.from({ length: completed }, (_, i) =>
            image(i === 0 ? "result" : `result-${i}`),
          ),
          errors: failed ? ["Simulated provider failure"] : [],
        },
      });
    }
    if (url.pathname === "/api/gallery") {
      galleryQueries.push(url.searchParams);
      const n = Number(url.searchParams.get("page") || 1);
      const response: GalleryResponse = {
        items:
          n === 1
            ? Array.from({ length: 24 }, (_, i) => image(String(i + 1)))
            : [image("25")],
        total: 25,
        page: n,
        page_size: 24,
        pages: 2,
      };
      return route.fulfill({ json: response });
    }
    if (url.pathname.startsWith("/api/images/"))
      return route.fulfill({ json: image(url.pathname.split("/").pop()!) });
    return route.fulfill({
      status: 404,
      json: { error: "Unexpected simulated API request" },
    });
  });
  return { previewPayloads, jobPayloads, galleryQueries };
}
