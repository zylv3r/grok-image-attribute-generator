// Frontend state contract checks against the real library; no provider or HTTP calls.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import Module, { createRequire } from "node:module";
import ts from "typescript";
const require = createRequire(import.meta.url);
const cache = new Map();
function sourceModule(file) {
  const absolute = path.resolve(file);
  if (cache.has(absolute)) return cache.get(absolute);
  const code = ts.transpileModule(fs.readFileSync(absolute, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const module = new Module(absolute);
  module.filename = absolute;
  module.require = (id) =>
    id === "./types" ? sourceModule("src/types.ts") : require(id);
  module._compile(code, absolute);
  cache.set(absolute, module.exports);
  return module.exports;
}
const { cleanDraft, pruneChoices, setAttribute, readStorage, writeStorage } =
  sourceModule("src/lib.ts");
const library = JSON.parse(fs.readFileSync("library.json", "utf8"));
test("every real library value survives restoration; stale attributes and values are pruned", () => {
  for (const category of library.categories)
    for (const attr of category.attributes) {
      for (const value of attr.values)
        assert.deepEqual(
          pruneChoices(
            {
              [attr.id]: ["missing-value", value.id],
              "missing-attribute": ["bad"],
            },
            library,
          ),
          { [attr.id]: [value.id] },
        );
    }
});
test("locks and whitelists stay disjoint when moved; exclusive locks preserve one and multi locks preserve all", () => {
  for (const category of library.categories)
    for (const attr of category.attributes) {
      const ids = attr.values.map((value) => value.id);
      let draft = cleanDraft(
        { selections: { [attr.id]: ids }, whitelist: { [attr.id]: ids } },
        library,
      );
      assert.deepEqual(
        draft.selections[attr.id],
        attr.type === "multi" ? ids : ids.slice(0, 1),
      );
      assert.equal(draft.whitelist[attr.id], undefined);
      draft = setAttribute(draft, attr, "whitelist", ids);
      assert.equal(draft.selections[attr.id], undefined);
      assert.deepEqual(draft.whitelist[attr.id], ids);
      assert.equal(draft.mode, "variations");
      draft = setAttribute(draft, attr, "selections", ids);
      assert.equal(draft.whitelist[attr.id], undefined);
      assert.deepEqual(
        draft.selections[attr.id],
        attr.type === "multi" ? ids : ids.slice(0, 1),
      );
      draft = setAttribute(draft, attr, "selections", []);
      assert.equal(draft.selections[attr.id], undefined);
    }
});
test("explicit boolean off is retained, while unset omits the attribute", () => {
  for (const category of library.categories)
    for (const attr of category.attributes.filter(
      (a) => a.type === "boolean",
    )) {
      const off = attr.values.find((v) => v.id === "off");
      if (!off) continue;
      let draft = cleanDraft({ selections: { [attr.id]: ["off"] } }, library);
      assert.deepEqual(draft.selections[attr.id], ["off"]);
      draft = setAttribute(draft, attr, "selections", []);
      assert.equal(draft.selections[attr.id], undefined);
    }
});
test("restored generation settings are bounded and safe; malformed/unavailable storage does not throw", () => {
  assert.equal(cleanDraft({ mode: "single", n: 24 }, library).n, 1);
  assert.equal(cleanDraft({ mode: "repeat", n: 99 }, library).n, 24);
  assert.equal(cleanDraft({ mode: "variations", n: -9 }, library).n, 1);
  assert.equal(
    cleanDraft({ seed: "not-an-integer", aspect_ratio: "invalid" }, library)
      .seed,
    undefined,
  );
  assert.equal(cleanDraft(null, library).aspect_ratio, "9:16");
  globalThis.localStorage = {
    getItem: () => "{invalid-json",
    setItem: () => {
      throw Error("Storage denied");
    },
  };
  assert.equal(readStorage("draft"), null);
  assert.doesNotThrow(() => writeStorage("draft", {}));
  globalThis.localStorage = {
    getItem: () => {
      throw Error("Storage denied");
    },
  };
  assert.equal(readStorage("draft"), null);
  delete globalThis.localStorage;
});
const { generationPayload, matchingValues, combinationLabel, galleryState, imageDescription } = sourceModule("src/lib.ts");
test("empty Vary preference survives restoration but never becomes an API field", () => {
  const attr = library.categories[0].attributes[0];
  let draft = setAttribute(cleanDraft(null, library), attr, "whitelist", []);
  draft = cleanDraft(JSON.parse(JSON.stringify(draft)), library);
  assert.equal(draft.attributeModes[attr.id], "whitelist");
  assert.equal(draft.whitelist[attr.id], undefined);
  assert.equal(generationPayload(draft).attributeModes, undefined);
  draft = setAttribute(draft, attr, "whitelist", [attr.values[0].id]);
  assert.equal(generationPayload(draft).mode, "variations");
  assert.deepEqual(generationPayload(draft).whitelist[attr.id], [attr.values[0].id]);
});
test("description-only attribute searches expose all options; individual value steering is searchable", () => {
  const attr = { ...library.categories[0].attributes[0], description: "unique-description-token" };
  assert.deepEqual(matchingValues(attr, " UNIQUE-DESCRIPTION-TOKEN "), attr.values);
  assert.equal(matchingValues(attr, "nonexistent-query").length, 0);
  assert.ok(matchingValues(attr, attr.values[0].steers).some((v) => v.id === attr.values[0].id));
});
test("count labels distinguish bounded lower estimates from exact counts", () => {
  assert.equal(combinationLabel({ combination_count: 1, combination_count_exact: true }), "1 combination");
  assert.equal(combinationLabel({ combination_count: 256, combination_count_exact: false }), "At least 256 combinations");
});
test("gallery URL restoration keeps OR filters, validates IDs and bounds malformed page and ratio", () => {
  const attr = library.categories[0].attributes[0];
  const filters = { [attr.id]: attr.values.slice(0, 2).map((v) => v.id) };
  const params = new URLSearchParams({ gallery_q: "quiet", gallery_ratio: "1:1", gallery_page: "3", gallery_filters: JSON.stringify(filters) });
  assert.deepEqual(galleryState(params.toString(), library), { query: "quiet", ratio: "1:1", page: 3, filters });
  assert.deepEqual(galleryState("gallery_filters=bad-json&gallery_page=-1&gallery_ratio=bad", library), { query: "", ratio: "all", page: 1, filters: {} });
});
test("image descriptions name selections and ratio instead of exposing a full prompt", () => {
  const attr = library.categories[0].attributes[0];
  const image = { selections: { [attr.id]: [attr.values[0].id] }, aspect_ratio: "9:16", prompt: "Long provider prompt" };
  assert.equal(imageDescription(image, library), `${attr.values[0].name} · 9:16`);
  assert.equal(imageDescription({ selections: {}, aspect_ratio: "1:1" }, library), "Untagged composition · 1:1");
});
