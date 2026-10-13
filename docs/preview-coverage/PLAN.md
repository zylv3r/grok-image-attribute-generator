# Atelier V2 preview coverage: investigation, completion plan and approval request

## Verified scope, not a completion claim

Catalog at investigation base `3c7f58642509528a1165b37f66297bda30e1b0e4`: 12 categories, 129 attributes, 1,596 values. The live app serves `thumbnail_mode=mixed`.

- 591 registered **legacy independent** value photographs and 62 representative contact sheets visibly decode with nonblank canvas pixels at 1440 and 390 widths on localhost and an authenticated real HTTPS quick tunnel. No API interception.
- 919 values pending; 16 palette swatches and 70 control-only values intentionally have no photograph.
- 63 photographic attributes lack registered sheets; four additional attributes intentionally need no photographic sheet. Thus 62 ready + 63 missing + 4 intentional = 129.
- These are rendering results, not exhaustive human semantic acceptance. The hair length screenshot shows apparent short/bob examples under longer-length labels. A visible photograph does not establish the promised target effect, same identity, or controlled comparison.
- Pipeline stays paused. No provider generation, baseline/mask approval, comparison publication or retry was performed.

## Reproduced faults and disposition

1. App passed `photographic=false` for mixed V2. Attributes without a registered sheet used generic letter/icon fallback; mixed mode also hid the coverage/paused summary. `acceptance/mixed_preview_regression.mjs` failed on the live old build for both exact symptoms; the repaired actual build passes.
2. `acceptance/photographic_live.mjs` assumes the old 893-value photographic catalog and samples one value. It remains historical V1 evidence, not V2 acceptance. Use `acceptance/preview_coverage.mjs` instead.
3. No registered-photo HTTP, decoding, URL validation, lazy-load or crop failure was reproduced. Images use eager loading and contain framing; collapsed attributes and Show more pagination are user navigation, not network failures. The new census opens every actual attribute and exhausts pagination without selecting values or modifying stored composition.
4. There are 208 pending values with one-target keep/move aliases to completed photographic legacy tasks. Of these, 71 retain exactly the same steer. The server currently retains ready images only through its direct same-ID/semantic path, and does not resolve these alias/photo task candidates into active readiness. Changed metadata and migration contracts can legitimately prevent reuse. These are review candidates, not 208 certified missing mappings or controlled assets. The other 711 have no safe one-target keep/move photograph candidate in that ledger. No generic image is substituted.

## Exact pending inventory

`inventory-plan.json` enumerates all 919 pending category/attribute/value IDs, method, group, candidate source URLs and whether legacy steers match. It also lists all 63 missing sheets and group baseline requirements. Counts:

- Hair: 112 pending, 7 missing sheets.
- Face / expression / makeup: 43 pending, 1 missing sheet.
- Eyes: 36 pending, 3 missing sheets.
- Skin / pigmentation: 21 pending, 4 missing sheets.
- Body / avatar: 57 pending, 15 missing sheets.
- Wardrobe: 368 pending, 27 missing sheets; 16 swatches excluded from photographic work.
- Poses: 212 pending, 2 missing sheets.
- Identity: 68 control-only values; no photographic work.
- Photography: 6 pending, 1 missing sheet; 2 camera controls intentionally photoless.
- Editorial recipes: 60 pending, 2 missing sheets.
- Lighting / composition: no pending values or missing sheets.
- Environment / props: 4 pending, 1 missing sheet.

Declared target methods reconcile as 818 reference edits + 71 masked pigment recolors + 6 simulated color grades + 24 simulated editorial grades = 919. The latter 101 are local operations, not provider calls, but still require real operator review before controlled publication.

## Execution order

1. **Zero-provider reuse review.** Review 208 photographed candidates with active labels and full originals, prioritizing the 71 exact-steer candidates. Reject semantic mismatches even when strings match. Preserve raw alias IDs, gallery tags and original byte hashes. Register accepted examples in a separate versioned mapping with source `legacy_independent` and visible label **Legacy independent example**. No comparison receipts or controlled claims may be manufactured. Re-census after publication; recompute all remaining counts rather than subtracting an assumed acceptance rate. Some candidates overlap local-method targets; legacy reuse does not replace their future controlled methods.
2. **Local representative sheets.** Four sheets can already be derived from currently ready active subsets: `eyelashes` (6 ready values), `outerwear_length` (8), `color_grade` (8), `hand_prop` (8). Four unpublished QA derivatives were created under `acceptance-output/preview-coverage/qa-sheet-*.jpg`, with source hashes in `derived-qa-sheets.json`. They explicitly say independent/representative/unpublished. They do not fill live cards. Verify target semantics, add an independently registered V2 derivative mapping/allowlist and versioned URLs, then publish as representative subsets. Do not overwrite the historical atlases. The other 59 missing sheets wait for accepted constituent photographs. Every sheet is locally derived; **zero extra provider generations**.
3. **Human baseline/mask selection.** For pending controlled coverage the catalog declares 63 distinct groups: 59 reference-edit groups, 2 recolor groups and 2 global-grade groups. Select 63 group baseline records from existing owned originals if suitable; this means 63 group bindings, not necessarily 63 unique purchased photographs. Retain immutable original, lossless normalized baseline and approved crop hashes. Require 61 localized reviewed target masks and two explicitly scoped global-grade masks. Inspect overlays, hair/face boundaries, target visibility and each group's actual baseline requirements in the JSON inventory. A baseline that cannot expose its target blocks that group. Do not pay for replacement bases without a separate exact scope/cost approval.
4. **Bounded pilots, no blanket batch.** Start only after approval with three category/group pilots: `hair:hair_cut` targets `one_length`, `blunt_bob`; `wardrobe:top_style` targets `none`, `crewneck_tee`; `poses:pose` targets `standing_neutral`, `standing_left_support`. Six target outputs; three baseline/crop bindings and three reviewed masks; maximum two consumed native attempts per target, **12 total paid attempts**, concurrency one. The wardrobe `none` pilot must preserve approved adult clothed presentation using an explicitly reviewed alternative/underlayer; if its target contract cannot support that, hold rather than silently substitute. Every output forks directly from the approved original snapshot, never from another variant.
5. **Pilot acceptance, then expansion.** Inspect target effect, identity/anatomy realism, outside-mask drift and receipt integrity. Failed/ambiguous attempts stay consumed. No automatic retry; second attempt requires its own bounded cycle approval. Human pilot acceptance is distinct from contract approval, expansion and final publication. Expand only individually approved groups/categories. Also run two-target local pilots for each of the four pending local-method groups (eight uncharged local outputs), retaining original/mask/crop hashes and truthful simulation labels.
6. **Publication and final verification.** Verify the entire baseline → contract → approved masks → direct-original receipt → pilot → expansion → publication chain and immutable hashes. Publish only canonical targets with accepted artifacts; custom drafts cannot replace thumbnails. Rebuild representative local sheets; repeat exhaustive desktop/mobile localhost/tunnel census and preserve failures/idempotency history. Report independent legacy examples, controlled reference edits and deterministic simulations separately.

## Consolidated approval request — NOT granted by this document

**Stage A (recommended first):** authorize human review of 208 legacy reuse candidates and four unpublished representative sheets. No provider cost. Review does not auto-approve controlled baselines/masks.

**Stage B:** select/review the three pilot group baselines/crops, three masks, six canonical targets above, model/resolution, a per-cycle cap and billing route. Proposed first cycle: one attempt per target, six paid attempts; maximum subsequent cycle: six more only after explicit failure review. Combined ceiling: 12 attempts. Approve pilot acceptance/publication only after viewing real outputs.

**Stage C (later, not requested as an automatic batch):** the full remaining pending scope currently has 63 baseline/crop group bindings and 63 mask bindings (61 localized + 2 explicitly global). Baseline selection, mask review, contract approval, pilot acceptance, expansion and publication remain human hash-bound actions. Existing ready photographs would need additional controlled work if the goal expands from filling pending previews to replacing all independent examples; that work is outside this counted request.

Public xAI API pricing currently lists `grok-imagine-image-quality` 1K output at $0.05 and image input at $0.01.[1] Conditional estimate for one baseline input plus one 1K output is $0.06 per paid edit; this is **not confirmation of the application's OAuth/subscription billing, provider capabilities or a guaranteed invoice**. Confirm actual route, region, image input count, resolution and terms before granting a dollar cap.

- Initial six-attempt pilot cycle: estimated $0.36; combined 12-attempt ceiling: $0.72, assuming the stated API route and no other charges.
- 818 reference targets at one attempt each: estimated $49.08 before any accepted legacy reuse. This is planning only, not approved expenditure; replacement baselines, retries and semantic remediation of existing ready photos excluded.
- Local recolor/grade outputs and contact sheets: $0 provider charge, still gated by human review.
- No claim that 919 paid generations are necessary or authorized. Recompute after Stage A, then request category-specific paid cycles.

## Evidence / rerun

- `acceptance/preview_coverage.mjs`: real catalog, full attribute/value expansion, every rendered image decode/naturalWidth, CSS visibility, nonblank canvas pixels, file existence and HTTP media response. Category checkpoint JSON preserves progress. `COVERAGE_ATTRIBUTE_SCREENSHOTS=1` captures every expanded attribute at each width.
- `scripts/audit_preview_inventory.py`: exact plan, local hashes, 1,244 unique thumbnail/contact-sheet/original URL decodes.
- `scripts/derive_preview_qa_sheets.py`: unpaid unpublished derivatives; retained-gallery verification against prior handoff hashes.
- Run Python tests using the service environment: `/home/renriquez/.hermes/hermes-agent/venv/bin/python -m unittest discover -q`. The default interpreter lacks Pillow; that unavailable run is not a test pass.
- Evidence lives under ignored `acceptance-output/preview-coverage/`, with authenticated tunnel results in `tunnel/`. Private bootstrap tokens are never included in source, reports or screenshots.

## Sources

[1] https://docs.x.ai/developers/models/grok-imagine-image-quality
