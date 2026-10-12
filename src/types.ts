export type Choices = Record<string, string[]>;
export type ThumbnailMode = "illustrative" | "photographic" | "mixed";
export type ThumbnailFields = {
  thumbnail?: string;
  thumbnail_url?: string;
  thumbnail_mode?: ThumbnailMode;
  thumbnail_kind?: "illustrative" | "photographic" | "contact_sheet" | "pending" | "comparison" | "control_only" | "swatch";
  thumbnail_status?: "ready" | "pending" | "failed" | "control_only" | "swatch";
  status?: "ready" | "pending" | "failed";
  example_url?: string;
  image_id?: string;
  illustration_url?: string;
  thumbnail_source?: string;
  preview_method?: string;
  preview_scope?: string;
};
export type ThumbnailProgress = {
  version: number;
  total: number;
  status: "running" | "completed" | "paused" | "failed";
  value_completed: number;
  attribute_completed: number;
  failed: number;
};
export type ThumbnailStatus = ThumbnailProgress & { mode: ThumbnailMode };
export type Value = ThumbnailFields & {
  id: string;
  name: string;
  steers: string;
  description?: string;
  color?: string | number[];
  rgb?: string | number[];
  recipe?: { selections: Choices; allowed_component_changes: string[] } | Record<string, string[]> | string;
  hex?: string;
  [key: string]: unknown;
};
export type Attribute = ThumbnailFields & {
  id: string;
  name: string;
  type: "exclusive" | "boolean" | "multi";
  description?: string;
  values: Value[];
  control?: "swatch" | "range" | "select" | "cards";
  range?: { min: number; max: number; step: number };
  default?: string | string[];
  comparison_group?: string;
  [key: string]: unknown;
};
export type Category = { id: string; name: string; attributes: Attribute[]; retired?: boolean; [key: string]: unknown };
export type Library = {
  categories: Category[];
  catalog_version?: number;
  version?: number;
  historical_library?: Library;
  historical_categories?: Category[];
  thumbnail_mode?: ThumbnailMode;
  thumbnail_progress?: ThumbnailProgress;
  base_locks?: string;
  always_on?: string;
};
export const ratios = [
  "1:1",
  "16:9",
  "9:16",
  "4:3",
  "3:4",
  "3:2",
  "2:3",
] as const;
export type Mode = "single" | "repeat" | "variations";
export type Draft = {
  selections: Choices;
  whitelist: Choices;
  mode: Mode;
  n: number;
  aspect_ratio: string;
  extra_prompt: string;
  seed?: number;
  attributeModes?: Record<string, "selections" | "whitelist">;
  comparison?: { category_id: string; baseline_asset_id: string; contract_hash: string; locked_fields: string[] };
};
export type Plan = { selections: Choices; prompt: string; selection_sampling_seed?: number };
export type Preview = {
  plans: Plan[];
  combination_count: number;
  combination_count_exact?: boolean;
  combination_count_metadata?: { method: string; unrestricted_product_count: number; visited_nodes: number; node_limit: number; result_limit: number };
};
export type ImageRecord = {
  id: string;
  url: string;
  thumbnail_url?: string;
  prompt: string;
  selections: Choices;
  width: number;
  height: number;
  created_at: string;
  aspect_ratio: string;
  seed?: number;
  selection_sampling_seed?: number;
  selection_labels?: Record<string, { name: string; values: Record<string, string> }>;
  label_snapshot?: Record<string, { name: string; values: Record<string, string> }>;
};
export type Job = {
  id: string;
  status: "queued" | "running" | "completed" | "partial" | "failed";
  total: number;
  completed: number;
  failed: number;
  results: ImageRecord[];
  errors: unknown[];
};
export type GalleryResponse = {
  items: ImageRecord[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};
export const emptyDraft: Draft = {
  selections: {},
  whitelist: {},
  mode: "single",
  n: 1,
  aspect_ratio: "9:16",
  extra_prompt: "",
};

// Archival drafts may contain retired IDs and future fields; clean only on explicit Apply.
export type Preset = {
  id: string;
  name: string;
  draft: Record<string, unknown>;
  schema_version: number;
  catalog_hash: string;
  created_at: string;
  updated_at: string;
};
export type PresetResponse = { presets: Preset[]; warnings?: string[] };
export type LegacyPresets = { raw_text: string; presets: unknown[] };
export type DraftResolution = { draft: Record<string, unknown>; changes: unknown[]; unresolved: unknown[] };
export type ComparisonArtifact = { id: string; url: string; base_url: string; attribute_id: string; value_id: string; method: string; receipt: Record<string, unknown>; accepted: boolean };
export type ComparisonReviewRecord = {
  category_id: string; state: "draft" | "contract_approved" | "pilot_done" | "pilot_accepted" | "published";
  contract_hash: string;
  baseline?: { asset_id: string; url: string; sha256: string; width: number; height: number; subject_id: string } | null;
  masks: Record<string, { polygon?: [number, number][]; sha256?: string; url?: string }>;
  artifacts: ComparisonArtifact[]; budget: {cap: number; used: number};
  locked_fields: unknown; allowed_changes: unknown;
};
