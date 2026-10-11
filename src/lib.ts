import {
  Attribute,
  Choices,
  Draft,
  emptyDraft,
  Library,
  ratios,
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
  const { attributeModes: _preferences, ...payload } = draft;
  return payload;
}
export function imageDescription(image: { selections: Choices; aspect_ratio: string }, library: Library) {
  const names = Object.entries(image.selections || {}).flatMap(([id, ids]) => {
    const attr = attributes(library).find((a) => a.id === id);
    return (Array.isArray(ids) ? ids : [ids]).map((value) => attr?.values.find((v) => v.id === value)?.name || value);
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
  if (!raw || typeof raw !== "object") return { ...emptyDraft };
  const d = raw as Partial<Draft>;
  const selections = pruneChoices(d.selections, library);
  const whitelist = pruneChoices(d.whitelist, library, true);
  Object.keys(selections).forEach((id) => delete whitelist[id]);
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
  };
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
