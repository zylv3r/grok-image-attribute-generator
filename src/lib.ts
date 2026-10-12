import {
  Attribute,
  Choices,
  Draft,
  emptyDraft,
  Library,
  ratios,
  ThumbnailFields,
  ImageRecord,
} from "./types";
export const storageKey = "atelier.draft.v1";
export const presetKey = "atelier.presets.v1";
export function readStorage(key: string): unknown {
  try {
    return JSON.parse(localStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}
export function writeStorage(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Private/full storage must not break editing. */
  }
}
export function attributes(library: Library): Attribute[] {
  return library.categories.flatMap((c) => c.attributes);
}
export function matchingValues(attr: Attribute, query: string) {
  const normalized = query.trim().toLowerCase();
  return !normalized || `${attr.name} ${attr.description || ""}`.toLowerCase().includes(normalized)
    ? attr.values
    : attr.values.filter((v) => `${v.name} ${v.description || ""} ${v.steers}`.toLowerCase().includes(normalized));
}
export function generationPayload(draft: Draft) {
  const { selections, whitelist, mode, n, aspect_ratio, extra_prompt, seed } = draft;
  return { selections, whitelist, mode, n, aspect_ratio, extra_prompt,
    ...(seed !== undefined ? { seed } : {}) };
}
export function historicalLibrary(active: Library, legacy?: Library): Library {
  if (!legacy) return historyLibrary(active);
  const result = structuredClone(active);
  for (const category of legacy.categories) {
    let destination = result.categories.find(c => c.id === category.id);
    for (const attribute of category.attributes) {
      const existing = attributes(result).find(a => a.id === attribute.id);
      if (existing) {
        for (const value of attribute.values)
          if (!existing.values.some(v => v.id === value.id)) existing.values.push(structuredClone(value));
      } else {
        if (!destination) {
          destination = { ...structuredClone(category), attributes: [] };
          result.categories.push(destination);
        }
        destination.attributes.push(structuredClone(attribute));
      }
    }
  }
  return result;
}
export function historyLibrary(library: Library): Library {
  return library.historical_library || (library.historical_categories ? { categories: library.historical_categories } : library);
}
export function rangeValueId(attr: Attribute, value: number): string | undefined {
  const range = attr.range;
  if (!range || !Number.isFinite(value) || value < range.min || value > range.max || (value - range.min) % range.step !== 0) return;
  return attr.values.find(v => v.id === `${attr.id}_${value}`)?.id;
}
export function previewLabel(fields: ThumbnailFields): string {
  if (fields.thumbnail_source === "legacy_independent" || fields.preview_method === "legacy_independent_photo") return "Independent generated example";
  if (fields.preview_method?.includes("simulat") || fields.preview_method?.includes("optical") || fields.preview_method?.includes("crop")) return "Simulated comparison";
  if (fields.thumbnail_source === "approved_comparison" || fields.preview_method === "approved_comparison") return "Approved controlled comparison";
  return "Generated example";
}
export function imageDescription(image: Pick<ImageRecord, "selections" | "aspect_ratio" | "selection_labels" | "label_snapshot">, library: Library) {
  const snapshots = image.selection_labels || image.label_snapshot;
  const names = Object.entries(image.selections || {}).flatMap(([id, ids]) => {
    const attr = attributes(historyLibrary(library)).find((a) => a.id === id);
    return (Array.isArray(ids) ? ids : [ids]).map((value) => snapshots?.[id]?.values?.[value] || attr?.values.find((v) => v.id === value)?.name || value);
  });
  return `${names.length ? names.join(", ") : "Untagged composition"} · ${image.aspect_ratio}`;
}
export function combinationLabel(preview: { combination_count: number; combination_count_exact?: boolean }) {
  return `${preview.combination_count_exact === false ? "At least " : ""}${preview.combination_count.toLocaleString()} ${preview.combination_count === 1 ? "combination" : "combinations"}`;
}
export function pruneChoices(
  raw: unknown,
  library: Library,
  whitelist = false,
): Choices {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const clean: Choices = {};
  for (const attr of attributes(library)) {
    const value = (raw as Record<string, unknown>)[attr.id];
    const ids = Array.isArray(value)
      ? value
      : typeof value === "string"
        ? [value]
        : [];
    const valid = [
      ...new Set(
        ids.filter(
          (id): id is string =>
            typeof id === "string" && attr.values.some((v) => v.id === id),
        ),
      ),
    ];
    if (valid.length)
      clean[attr.id] =
        !whitelist && attr.type !== "multi" ? valid.slice(0, 1) : valid;
  }
  return clean;
}
export function galleryState(search: string, library: Library) {
  const params = new URLSearchParams(search);
  let filters: Choices = {};
  try { filters = pruneChoices(JSON.parse(params.get("gallery_filters") || "{}"), library, true); } catch { /* Ignore invalid URL filters. */ }
  const ratio = params.get("gallery_ratio") || "all";
  const page = Number(params.get("gallery_page") || 1);
  return { query: (params.get("gallery_q") || "").slice(0, 500), ratio: ratios.includes(ratio as (typeof ratios)[number]) ? ratio : "all", filters, page: Number.isSafeInteger(page) && page > 0 ? page : 1 };
}
export function cleanDraft(raw: unknown, library: Library): Draft {
  const d = (raw && typeof raw === "object" ? raw : emptyDraft) as Partial<Draft>;
  const selections = pruneChoices(d.selections, library);
  const whitelist = pruneChoices(d.whitelist, library, true);
  Object.keys(selections).forEach((id) => delete whitelist[id]);
  const gender = attributes(library).find(a => a.id === "gender");
  if ((!raw || typeof raw !== "object") && (library.catalog_version === 2 || library.version === 2 || gender?.control === "select") && !selections.gender && !whitelist.gender) {
    if (gender?.values.some(v => v.id === "woman")) selections.gender = ["woman"];
  }
  const mode = Object.keys(whitelist).length
    ? "variations"
    : d.mode === "repeat" || d.mode === "variations"
      ? d.mode
      : "single";
  const attributeModes: NonNullable<Draft["attributeModes"]> = {};
  for (const attr of attributes(library)) {
    const stored = d.attributeModes?.[attr.id];
    if (stored === "selections" || stored === "whitelist") attributeModes[attr.id] = stored;
    if (selections[attr.id]) attributeModes[attr.id] = "selections";
    if (whitelist[attr.id]) attributeModes[attr.id] = "whitelist";
  }
  return {
    selections,
    whitelist,
    attributeModes,
    mode,
    n:
      mode === "single"
        ? 1
        : Math.max(
            1,
            Math.min(24, Number.isFinite(d.n) ? Math.trunc(d.n!) : 4),
          ),
    aspect_ratio: ratios.includes(d.aspect_ratio as (typeof ratios)[number])
      ? d.aspect_ratio!
      : "9:16",
    extra_prompt: typeof d.extra_prompt === "string" ? d.extra_prompt : "",
    ...(Number.isSafeInteger(d.seed) && d.seed! >= 0 ? { seed: d.seed } : {}),
    ...(validComparison(d.comparison, library) ? { comparison: structuredClone(d.comparison) } : {}),
  };
}
export function validComparison(raw: unknown, library: Library): raw is NonNullable<Draft["comparison"]> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return false;
  const c = raw as Record<string, unknown>;
  return typeof c.category_id === "string" && library.categories.some(category => category.id === c.category_id)
    && typeof c.baseline_asset_id === "string" && /^[a-f0-9]{32}$/.test(c.baseline_asset_id)
    && typeof c.contract_hash === "string" && /^[a-f0-9]{64}$/.test(c.contract_hash)
    && (c.group === undefined || (typeof c.group === 'string' && c.group.length > 0 && c.group.length <= 200))
    && Array.isArray(c.locked_fields) && c.locked_fields.length <= 100
    && c.locked_fields.every(field => typeof field === "string" && field.length > 0 && field.length <= 500)
    && Object.keys(c).every(key => ["category_id", "baseline_asset_id", "contract_hash", "locked_fields", "group"].includes(key));
}
export function setAttribute(
  draft: Draft,
  attr: Attribute,
  target: "selections" | "whitelist",
  ids: string[],
): Draft {
  const selections = { ...draft.selections },
    whitelist = { ...draft.whitelist };
  const active = target === "selections" ? selections : whitelist;
  delete (target === "selections" ? whitelist : selections)[attr.id];
  if (ids.length)
    active[attr.id] =
      target === "selections" && attr.type !== "multi" ? ids.slice(0, 1) : ids;
  else delete active[attr.id];
  return {
    ...draft,
    selections,
    whitelist,
    attributeModes: { ...draft.attributeModes, [attr.id]: target },
    ...(target === "whitelist" && ids.length
      ? { mode: "variations" as const }
      : {}),
  };
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error(
      `The server returned an unreadable response (${response.status}).`,
    );
  }
  if (!response.ok) {
    const error =
      data && typeof data === "object"
        ? (data as Record<string, unknown>).error
        : undefined;
    throw new ApiError(
      typeof error === "string"
        ? error
        : `Request failed (${response.status}). Please try again.`,
      response.status,
    );
  }
  return data as T;
}
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (
    error &&
    typeof error === "object" &&
    "error" in error &&
    typeof error.error === "string"
  ) {
    const index =
      "index" in error && typeof error.index === "number"
        ? `Image ${error.index + 1}: `
        : "";
    return index + error.error;
  }
  return JSON.stringify(error) || "An unexpected error occurred.";
}

export function bulkVary(draft: Draft, attr: Attribute, action: "all" | "none" | "inverse"): Draft {
  const allowed = new Set(draft.whitelist[attr.id] || []);
  const ids = action === "none" ? [] : attr.values
    .filter(v => action === "all" || !allowed.has(v.id)).map(v => v.id);
  return setAttribute(draft, attr, "whitelist", ids);
}

// Capture the original text once, before ANY draft cleaning. Never rewrite legacy storage.
export function readLegacyPresets(): import("./types").LegacyPresets | null {
  try {
    const raw_text = localStorage.getItem(presetKey);
    if (raw_text === null) return null;
    let parsed: unknown;
    try { parsed = JSON.parse(raw_text); } catch { /* Archive malformed text for recovery. */ }
    return { raw_text, presets: Array.isArray(parsed) ? parsed : [] };
  } catch { return null; }
}

let fallbackSequence = 0;
export function presetRequest(name: string, draft: Draft) {
  const request_key = typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID()
    : `save-${Date.now().toString(36)}-${(++fallbackSequence).toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  return { name: name.trim(), draft: structuredClone(draft), request_key };
}

export function presetApplication(raw: Record<string, unknown>, library: Library, schemaVersion = 1) {
  const draft = cleanDraft(raw, library);
  const unresolved: string[] = [];
  if (schemaVersion !== 1) unresolved.push(`Unsupported schema version: ${schemaVersion}`);
  for (const [key, value] of Object.entries(raw)) {
    const known = (draft as unknown as Record<string, unknown>)[key];
    if (key === "selections" || key === "whitelist" || key === "attributeModes") {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        unresolved.push(`Unsupported ${key}`);
        continue;
      }
      for (const [id, stored] of Object.entries(value)) {
        const applied = (known as Record<string, unknown> | undefined)?.[id];
        // Compare arrays without treating harmless key ordering as an unresolved change.
        if (JSON.stringify(stored) !== JSON.stringify(applied)) {
          // An explicitly empty pool is supported via attributeModes and stays unset.
          if (key === "whitelist" && Array.isArray(stored) && stored.length === 0 && attributes(library).some(a => a.id === id)) continue;
          unresolved.push(`${key}.${id}: ${JSON.stringify(stored)}`);
        }
      }
    } else if (!(key in draft) || JSON.stringify(value) !== JSON.stringify(known)) {
      unresolved.push(`${key}: ${JSON.stringify(value)}`);
    }
  }
  return { draft, unresolved };
}

// Saved comparison metadata never conditions /api/jobs generation.
export async function validateComparisonAnchor(raw: unknown, library: Library, readReview: (path: string) => Promise<unknown> = api): Promise<boolean> {
  if (!validComparison(raw, library)) return false;
  const anchor = raw as NonNullable<Draft['comparison']> & {group?: string; baseline_integrity?: boolean};
  try {
    const current = await readReview(`/api/comparisons/${encodeURIComponent(anchor.category_id)}${anchor.group ? `?group=${encodeURIComponent(anchor.group)}` : ''}`) as {contract_hash?: string; baseline?: {asset_id?: string; sha256?: string}; group?: string; baseline_integrity?: boolean};
    return current.baseline_integrity !== false && current.contract_hash === anchor.contract_hash && current.baseline?.asset_id === anchor.baseline_asset_id
      && typeof current.baseline?.sha256 === 'string' && /^[a-f0-9]{64}$/.test(current.baseline.sha256)
      && (!anchor.group || current.group === anchor.group);
  } catch { return false; }
}

export function generationDefaults(draft: Pick<Draft, 'selections' | 'whitelist'>, library: Library): string[] {
  return attributes(library).flatMap(attr => {
    const value = (attr as Attribute & {default?: string; default_value?: string}).default || (attr as Attribute & {default_value?: string}).default_value;
    if (!value || draft.selections[attr.id]?.length || draft.whitelist[attr.id]?.length) return [];
    return [`${attr.name}: ${attr.values.find(v => v.id === value)?.name || value}`];
  });
}
