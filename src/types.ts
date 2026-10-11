export type Choices = Record<string, string[]>;
export type Value = {
  id: string;
  name: string;
  steers: string;
  description?: string;
  thumbnail?: string;
  thumbnail_url?: string;
};
export type Attribute = {
  id: string;
  name: string;
  type: "exclusive" | "boolean" | "multi";
  description?: string;
  thumbnail?: string;
  thumbnail_url?: string;
  values: Value[];
};
export type Category = { id: string; name: string; attributes: Attribute[] };
export type Library = {
  categories: Category[];
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
