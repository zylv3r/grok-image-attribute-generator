# Backend API

`server.py` serves the compiled UI at `dist/index.html`, build assets at `/assets/`, library-referenced thumbnail files at `/thumbnails/`, verified gallery images at `/generated/`, and registered comparison PNGs at `/api/comparisons/assets/<32hex>.png`. Build the frontend before an authorized backend start; missing builds return 404. Python 3.10+, Pillow, SQLite with FTS5, and the existing Hermes environment are required. Ordinary native generation and the separate native JSON reference-edit adapter keep provider credentials on the server. This describes implemented APIs, not final integrated verification or deployment.

Start when ready (this implementation does not restart the existing server):

```bash
/home/renriquez/.hermes/hermes-agent/venv/bin/python server.py
```

`HOST` defaults to `127.0.0.1` and must be loopback; `PORT` defaults to `8123`. Gallery/job persistence lives in `gallery.sqlite3` (including SQLite WAL files) and `generated/`; presets use `presets.sqlite3`. Comparison contracts, approvals, history and request reservations use a separate `comparisons.sqlite3`, with PNGs under `generated/comparisons/`. Run one backend per database and back up databases/assets together while stopped. Ordinary job startup marks unfinished plans failed, retains successful images and derives `partial` or `failed` status without paid retries. Comparison reservations remain recorded and consumed across restart, including unresolved `reserved` attempts; they are not resubmitted or refunded automatically. Unchanged catalog definitions preserve reviews/publication; changed definitions archive/invalidate affected gates and clear masks. This worker does not start/restart the live service or mutate its databases.

`GET /api/health` returns `status="ok"`, `job_counts` for queued/running/completed/partial/failed jobs, `pending_images`, `image_count`, `pending_limit=24`, and `provider_concurrency_limit=4`. Counts come from a consistent SQLite snapshot. The endpoint does not invoke the provider or inspect credentials/configuration and returns no prompts, error details, paths, credentials, or provider diagnostics. It indicates local database availability, not provider authentication or readiness.

## Library

`GET /api/library` returns the active catalog and runtime thumbnail projection, preserving `categories`, `base_locks` and `always_on`. With the complete activated bundle it loads `catalog/v2/library.json`; without a bundle a legacy/custom root loads `library.json`. A present malformed bundle fails validation instead of silently falling back. Categories contain `id`, `name`, and `attributes`. Attributes contain `id`, `name`, `type` (`exclusive`, `boolean`, or `multi`), `description`, `thumbnail_url`, and `values`. Values contain `id`, `name`, `steers`, `description`, and `thumbnail_url`. Missing descriptions/URLs normalize to strings; empty URLs mean no image. Boolean IDs are strings, typically `on`/`off`, not JSON booleans.

The checked-in bundle has 12 active categories, 129 attributes and 1,596 values; frozen v1 has 22 categories, 97 attributes and 893 values. Hair has 44 pigment targets, eyes 27, body 15 controls, wardrobe 37, pose 176 values, editorial mood 24 recipes and narrative 36 recipes. Counts describe controls, not photographs. Age is discrete `age_21`…`age_85` with range metadata; age/gender are `control_only`. Unset catalog defaults resolve to `age_24` and `woman`; explicit selections/whitelists take precedence. Person comparison baselines are operator-declared adult women, even when ordinary generation chooses a different presentation.

Attributes additionally declare `control`, `preview_method`, `preview_scope`, `comparison_group`, `preview_contract`, and, for local methods, `preview_parameter_schema`. Values may declare illustrative `colour.hex`, `preview_params`, `preview_baseline`, recipes and exclusions. Recipe components expand into authoritative resolved selections/prompts and compatibility checks; conflicting explicit components reject. The former style-inspiration (`ethnic_inspiration`), complexion-detail and facial-balance controls are retired/reconciled, not active generation fields. Body appearance recipes make no health/ability inference; wardrobe rules include explicit layering rather than forbidding every mixed garment.

`catalog/v2/active.json` activates controls only: its comparison pointers remain `awaiting_operator_review`. `/api/library` reports `catalog_version=2`, `thumbnail_mode="mixed"`, historical vocabulary, retirement disclosures and progress. Each value has `thumbnail_source` distinguishing `approved_comparison`, `legacy_independent`, `palette`, `control_only`, `pending` or `withheld_provenance`. Only explicitly published, individually accepted, intact canonical group artifacts project as controlled thumbnails. Compatible legacy photos/contact sheets remain labeled independent; altered/expanded values cannot inherit mismatched old photos. Missing controlled thumbnails remain pending operator approval, not full controlled photo coverage. Progress can be `paused` with `review_required=true`; ready counts may include legacy independent photos and do not prove controlled coverage. `GET /api/thumbnail-status` returns the same computed progress plus `mode`.

`GET /api/catalog/versions` returns `active_version`, `legacy_version`, `library_hash`, `source_control_mode`, `effective_counts` and per-category control counts/status. It does not return the full archived catalog or aliases; the library response supplies historical vocabulary/retired records, and the checked-in ledgers supply exhaustive migration disclosures.

`POST /api/catalog/resolve` requires exactly `{"draft": {...}}` and a matching Origin. It returns `raw_draft`, proposed `draft`, `changes` and `unresolved`; it calls no provider and saves nothing. The raw draft preserves unknown/retired IDs and other saved fields. Each change discloses source IDs, disposition and target controls; conflicts apply none of a coupled recipe's components. Coupled multi-attribute recipes cannot become independent whitelist pools. The UI requires an explicit Apply decision for unresolved data.

`catalog/v2/aliases.json` has exactly one disposition for each of the 893 frozen attribute/value pairs: 684 keep, 143 move, 49 disclosed recipe and 17 retire-unresolved. Entries retain original name/steer, reasons and target IDs. `coverage.json` assigns all 97 legacy attributes an owner; `retired.json` records every retired attribute and unresolved value. Loader checks enforce archive-byte equality, exhaustive coverage and valid active targets. Historical filters use the union of active and frozen IDs, without retagging old images. Generation validates active IDs; a historical filter's validity does not make a retired ID generatable.

## Comparison groups, bases and masks

`GET /api/comparisons/categories` returns `{"categories": [...]}` with category summaries and declared group summaries. `GET /api/comparisons/<category_id>?attribute_id=<id>&group=<group>` returns a targeted review; either selector can be supplied, and both must agree. Query fields must be unique, nonempty and at most 200 characters. Groups come from the attribute's `comparison_group` (for example `hair:hair_color` or shared `photography:same_scene`), not a browser-invented scope.

Reviews include `category_id`, `group`, `state`, `contract_hash`, `baseline`, `baseline_integrity`, `baseline_requirements` (a list of human-review strings), `masks`, `attributes`, `definition`, `locked_fields`, `allowed_changes`, `artifacts`, `approvals`, `history`, `attempts`, `published_artifact_ids`, `budget` and `cycle`. Group state/baseline/crop/masks are independent; photography attributes share one group and original scene. Unscoped GET includes `groups` and category summaries. The older unscoped category base establishes a compatibility view: implicit attribute targeting may use it until an explicit group base exists. Always send `group` for new clients; group-specific publication overrides compatibility artifacts for those attributes. Category aggregate budget caps can exceed three because they sum group caps; each approved cycle cap is still at most three.

Group `locked_fields` and `allowed_changes` derive from the actual member attributes' `preview_contract`, falling back to category fields only when a declaration is absent. A single-target group preserves its target's declarations. Shared groups require compatible contracts: native declarations cannot be widened by a union; known local methods permit declared field-of-view crop and global color/tone exceptions. Shared locks retain the intersection and changes the ordered union of compatible declarations. Baseline requirements are deduplicated in declaration order. Receipts retain the selected `target_contract`, and native prompts use that target's `allowed_changes` with the group locks. Unscoped compatibility reviews also collect declared baseline requirements rather than bypassing them.

All comparison POSTs require a matching Origin and JSON body, reject unknown fields and reject query strings. Successful mutations and previews return HTTP 200. Preflight guards generally return 400; attempted native failure can return 200 with a failed receipt and `id=null`, `url=null`. Check receipt status rather than HTTP success alone.

| POST route suffix | Required fields | Optional fields |
| --- | --- | --- |
| `/base` | `image_id` | `subject_id`, `crop`, `attribute_id`, `group`, `baseline_confirmations` (required when the review has baseline requirements) |
| `/mask` | `attribute_id`, `polygon` | `group` |
| `/approve` | `stage`, `expected_contract_hash` | `artifact_ids`, `provider_attempt_cap`, `approval_note`, `attribute_id`, `group` |
| `/reopen` | `expected_contract_hash`, `approval_note` | `attribute_id`, `group` |
| `/preview` | `attribute_id`, `value_id`, `method`, `request_key` | `params`, `group` |

For example, a targeted baseline request is:

```json
{
  "image_id":"<owned gallery 32hex ID>",
  "subject_id":"woman-1",
  "attribute_id":"eye_color",
  "group":"eyes:eye_color",
  "crop":[0.2,0.2,0.8,0.5],
  "baseline_confirmations":[
    "Operator reviewed the same approved close-eye view of the immutable original for every Eyes group, with the iris and lash boundary clearly visible.",
    "Identity, face viewing angle and non-target eye details remain unchanged; only the selected eye_color target may change.",
    "Iris recoloring is confined to the reviewed iris mask; iris geometry, radial pattern and eyelashes remain unchanged."
  ]
}
```

Read the current targeted review first and send its exact `baseline_requirements` strings as `baseline_confirmations` after visually reviewing the chosen image and crop. Missing, extra, changed or duplicate strings reject; input order can differ, and storage normalizes to requirement order. An empty requirement list permits omission or `[]`. The list allows at most 100 distinct nonblank strings of at most 1,000 characters each. The baseline records `baseline_confirmations` and `confirmation_basis="operator_attestation_not_machine_proof"`; this attests to operator review, not automatic image classification or proof of pigment, geometry, identity or framing. Requirements are bound into the definition/contract hash and checked again on approval and preview. The UI shows the server list, falling back to catalog declarations only for older responses, and resets confirmation when image, crop or group changes.

The current human-reviewed lists include:

- All nine Hair reference-edit groups start with `Operator reviewed the immutable original of the same approved adult woman with neutral medium-brown uniform hair pigment.` The second requirement is `Only the selected <attribute_id> target and its reviewed consequences may change; non-target hair geometry, pigment and distribution remain fixed.` with the actual attribute ID substituted. For `hair_color_treatment` it is instead `Only the selected hair_color_treatment distribution and its declared tones may change; non-target hair geometry and base pigment remain fixed.`
- Hair recolor uses `Operator reviewed a suitable immutable original of the same approved adult woman; the original hair pigment may be any suitable color.` and `Hair recoloring is confined to the reviewed hair-pigment mask; strand texture, geometry and distribution remain unchanged.` It does not require medium-brown pigment.
- Every Eyes group uses the close-eye original requirement in the example, then `Identity, face viewing angle and non-target eye details remain unchanged; only the selected <attribute_id> target may change.` with its actual ID. The third string for `eye_color` is shown above; `iris_pattern` uses `Iris-pattern edits preserve iris pigment, pupil geometry, eye geometry and eyelashes.`; `eyelashes` uses `Lash edits preserve iris pigment, iris and pupil geometry, and non-target eye geometry.`
- Face groups use `Operator reviewed the immutable original of the same approved adult woman; identity and face viewing angle remain unchanged throughout this group.` then `Constraints apply to the selected <attribute_id> target: only that target and its reviewed consequences may change; all non-target facial geometry, pigment, expression and gaze remain fixed.` with the actual ID.
- Every rendered `photography:same_scene` control uses exactly the shared list below; the control-only camera selector has no baseline requirements. The other current attributes have empty lists.

```json
[
  "Operator reviewed one approved immutable original scene shared by every rendered photography:same_scene control.",
  "Identity, scene contents, pose and camera position remain fixed; only the selected optical or photographic treatment and its declared consequences may change.",
  "Field-of-view crop, regional blur, synthetic grain and global color or tone changes are permitted only when declared by the selected target contract; no missing source detail, perspective change or camera equivalence is implied."
]
```

`image_id` must resolve server-side to a registered owned JPEG gallery photograph. Browsers cannot submit paths, URLs or image bytes. `subject_id` defaults to `woman-1` and is a safe ID of at most 100 characters. Adult-woman metadata is operator-declared, not detected. `crop` is normalized `[left, top, right, bottom]` or an object with exactly those keys; bounds lie in 0–1, have positive area and round to at least 2×2 source pixels. Eye-closeup declarations require choosing an appropriate original/crop; the API does not infer framing. Source bytes stay unchanged; normalization applies EXIF orientation/ICC-to-sRGB conversion, strips metadata and registers lossless RGBA PNG bytes. Hashes, dimensions, source hash and crop are recorded. Comparison outputs and copied/reencoded registered output pixels cannot be substituted as originals.

`polygon` is 3–256 normalized `[x,y]` points with nonzero area and pixel footprint; `[]` removes a saved mask. Localized masks reject coverage of 98% or more. Masks register PNG alpha footprints and overlays with hashes, coverage, provenance and `human_review_required=true`. Supersampled edges count as part of the footprint wherever alpha is nonzero. Explicitly global effects can register whole-frame masks; swatches can declare a whole-swatch footprint. These automatic declarations are never human approval. Show the registered overlay and review intended region/occlusion support before approving the contract.

Base/mask replacement is allowed only in `draft`; replacing a base clears masks, and changed inputs invalidate current gates/artifacts/publication. Previous records/assets and total attempts remain archived. There is no bypass flag for editing an approved review: use Reopen first. Exact `GET`/`HEAD /api/comparisons/assets/<32hex>.png` serves only registered, intact bounded PNGs under the comparison directory with the same private loopback guards. HTTP reads a bounded byte snapshot, validates its registered SHA-256, PNG decoding and dimensions, and serves that same snapshot without reopening the path. Comparison decode limits are 32 MiB, 16 million pixels and 8,192 pixels per side, separate from the JPEG gallery limits below.

## Approval, Reopen and bounded cycles

Implemented states are `draft`, `contract_approved`, `pilot_done`, `pilot_accepted` and `published`. There are no separate `expanded`, `reviewed` or `rejected` states/endpoints in this implementation. Rejection means withholding approval or leaving a candidate unaccepted; there is no reject endpoint.

| `/approve` stage | Preconditions and result |
| --- | --- |
| `contract` | Draft with valid base, masks and overlays; empty/omitted artifact IDs. Starts a cycle with cap 0–3 and state `contract_approved`; invokes no provider. |
| `pilot` | Current contract approval; state `contract_approved`, `pilot_done` or `pilot_accepted`; nonempty individual artifact IDs. Validates provenance and target change, accepts only selected artifacts, sets `pilot_accepted`; does not publish. |
| `publish` | `pilot_accepted`; selected IDs must have individual pilot acceptance, intact artifacts/receipts and canonical catalog parameters. Sets the selected publication list and state `published`. |
| `expansion` | Current contract with accepted pilot or published state; nonempty note, no artifact IDs, no unresolved reservation on this contract. Starts another cap 0–3 cycle with state `contract_approved`; no provider invocation. |

`expected_contract_hash` must equal the current internally verified SHA-256 contract. Approvals record actor/time/note, contract/base/mask/overlay/output hashes, cycle and total usage. `provider_attempt_cap` defaults to 0 and must be an integer (not a boolean) in 0–3; only contract/expansion starts an allowance. Other stages do not grant attempts. Approve notes are limited to 2,000 characters at HTTP ingress; expansion requires nonblank text. Artifact IDs are distinct registered 32hex IDs: ingress allows up to 2,000, but the engine enforces **100 per approval**. Contract/pilot/publish notes may be empty; visual review is still an explicit operator action, not an automated assertion of correctness.

The UI always sends `artifact_ids=[]` for contract/expansion, regardless of checked or stale candidate selections. Pilot/publish retain explicit nonempty current-review selection validation, and publish requires accepted candidates. Pilot/publish payloads send cap 0. Every approval stage verifies baseline, masks and overlays against registered bytes and dimensions plus the baseline attestation and current contract hash. Later stages also verify originating contract/current-cycle approval hashes and cycle provenance; candidate acceptance/publication verifies output and receipt provenance, with publish additionally checking pilot acceptance. Publication projection repeats these checks and withholds corrupt approvals/artifacts.

Example explicit Reopen:

```json
{"group":"hair:hair_color","expected_contract_hash":"<current 64hex SHA256>","approval_note":"Revise the hair footprint after inspecting edge halos."}
```

`POST /api/comparisons/hair/reopen` rejects stale hashes, blank notes and already-draft reviews. Reopen notes are currently bounded by the engine to 4,000 characters (the UI uses 2,000). It records an `operator_reopen` history event with note, expected hash and complete previous review, increments the revision, and invalidates current approvals/artifacts/publication back to draft with cap 0. It retains base/masks for editing, archived assets/receipts, all request tombstones and consumed usage. Fetch the targeted GET again for history; no separate history endpoint exists. Reapproving the revised contract is required before another native attempt. Reopen is an operator revision action, not a refund or retry.

`cycle={id,cap,used}` tracks the current cycle. `budget.used` is lifetime consumed provider attempts for that review record; it includes failed/ambiguous attempts and never decreases on Reopen or expansion. Group budget also carries cycle fields; unscoped category budget may summarize groups. A newly approved cycle resets only cycle usage. Cap ≤3 is per cycle, not a lifetime cap, aggregate category limit, automatic batch launch or permission to expand all categories.

`request_key` matches `[A-Za-z0-9_-]{1,128}`, unique per category across groups, revisions and cycles. A transaction commits the reservation and provider counters before invocation, preventing concurrent overrun. Identical completed requests return the same artifact; identical attempted failures return the same failed receipt. A changed payload/contract using an old key rejects. In-flight or crash-interrupted `reserved` attempts reject without retry after restart and remain consumed. Local attempts also have tombstones but do not spend provider budget. Expansion is blocked by reserved attempts on the current contract; historical reservations remain visible after explicit revision. New paid work always requires a fresh explicit request under the current approved allowance. No native failure automatically retries, publishes a pilot or approves a mask.

## Deterministic candidates and native reference edits

`/preview` requires an active attribute/value and the exact catalog-declared `method`. `params={}` uses attribute defaults plus selected-value parameters; explicit overrides apply last. Use the attribute's `preview_parameter_schema`; unsupported keys/nonfinite values reject. Optional `base_sha256` and `mask_sha256` assert the expected originals. The browser cannot override sources, masks, output size, resizing or prompt, including nested parameters.

Local methods may stage draft artifacts. `masked_recolor` preserves luminance texture using illustrative sRGB targets; it is not calibrated pigment/dye rendering. `fabric_swatch` samples texture or creates a synthetic neutral 256×256 no-person reference with illustrative weave; it is not a garment render or measured material. Method aliases retain the declared name in receipts while recording `effective_method`.

| Declared method | Disclosed operation/limits |
| --- | --- |
| `simulated_fov_crop` | Fixed-camera center crop/resample (`focal_fov`); no perspective or recovered optical detail. |
| `simulated_depth_blur`, `simulated_focus` | Mask-defined depth plane and explicit `depth_assumption`; constant-brightness blur, not physical bokeh/depth inference or recovered focus detail. |
| `simulated_motion_blur` | Drawn moving/swept footprint plus `moving_region`; directional blur approximates motion, not exposure. |
| `simulated_grain` | Seeded digital noise, not measured film/sensor behavior. |
| `simulated_white_balance` | RGB adjustment intentionally changes colors; not calibrated RAW temperature conversion. |
| `simulated_tone_curve` | Gentle highlight rolloff; no recovery of clipped detail. |
| `simulated_color_grade`, `simulated_contrast`, `simulated_palette`, `simulated_editorial_grade` | Disclosed tone/color or component recipes on the original scene; no generated outfit/prop/expression changes. |

`simulated_optics` is also supported when declared by a catalog attribute and dispatches a validated `effect`. For identical inputs/parameters/method version the local output is deterministic. Neutral catalog `preview_baseline=true` values return receipt status/effect role `baseline` with unchanged original pixels; they cannot pass effect acceptance/publication. Nonbaseline empty effects fail. Overrides differing from canonical parameters are marked `custom`/`custom_override` and may be inspected/accepted, but **cannot publish as the named canonical target** (including color aliases such as a red override under platinum).

`reference_edit` requires a reviewed adult-woman baseline, saved approved target mask, current hash-bound contract/cycle approval and remaining allowance before invocation. A synthetic `no_person` swatch reference is rejected before reservation/provider call. Browser-provided identity metadata is a declaration requiring operator review, not automatic person classification.

`edit_native_image` sends native JSON to `/images/edits` with a server-built `image.url` data URI from original registered PNG bytes, `image.type="image_url"`, server-built prompt, `response_format="b64_json"` and the server's edit model (default `grok-imagine-image-2.0`). The engine retains the validated baseline/mask/overlay byte snapshots from integrity preflight: decoding, compositing and provider input use those same bytes, without a later unvalidated source read. Supported generation ratios are sent explicitly; other reviewed crop ratios use reference dimensions without a resize instruction. Only bounded base64 output is accepted; no returned remote URL downloads or text-generation fallback. Credential/config resolution occurs server-side only when native work is authorized. Ordinary generation, compatibility generation and edits share the process-wide four-call semaphore. Comparison calls use their own capped ledger and are not asynchronous `/api/jobs` plans.

All variants use the original group's immutable bytes directly. The engine requires unchanged dimensions/alpha, discards provider pixels outside the approved mask and composites a lossless master. It verifies zero decoded RGBA changes where mask alpha is zero and nonzero target changes for effects. Receipts include original/mask/overlay/output hashes, method version, canonical/supplied/effective parameters, custom flag, group/cycle/total usage, locked asset IDs/crop/dimensions, target, approval, outside delta, inside-change statistics, provider outside drift, limitations and no-retry status. Provider failure details are sanitized; after an attempted native failure the receipt is `failed` with no artifact URL. Pixel equality proves compositing only, not semantic mask correctness, locked landmarks, identity, anatomy or realism inside the footprint. Operator inspection at 1×/2× remains required. Successful native transport alone does not prove pixel locks or authorize publication/full-catalog paid expansion.

## Presets and saved comparison context

`GET /api/presets` returns `{"presets":[...]}`. `POST /api/presets` requires exactly `name`, `draft`, `request_key`; returns the record with 201 for a new save or 200 for identical retry. Names are 1–80 characters without control characters; drafts are bounded to 65,536 encoded bytes. Structural validation permits unknown/historical controls for archival preservation. The transactional key ledger rejects different data with 409 and a retry of a deleted preset with 410. `DELETE /api/presets/<32hex>` returns the refreshed collection and preserves tombstones.

`POST /api/presets/import` accepts a bounded `presets` array (at most 256 records), optionally `raw_text`. It archives the raw envelope/warnings, imports records idempotently and retains conflicting legacy-ID records as distinct content rather than silently overwriting them. All mutations require a matching Origin. Browser import/save failures retain original local records and visible error state; migration Apply is separate from archival storage.

A saved draft may carry `comparison={category_id,group?,baseline_asset_id,contract_hash,locked_fields}`. UI Apply/reload checks the current review's baseline ID/hash integrity and contract/group; unavailable/stale anchors are disclosed. The server preset store archives metadata rather than enforcing generation validity. **Saved anchors are comparison-only reference context, not reference-conditioned generation**: UI `generationPayload` omits them, and `/api/preview`/`/api/jobs` reject extra fields. Conditioning occurs only through the explicit approved `/api/comparisons/<category>/preview` native-edit path. Saving or applying a preset does not approve a contract/mask, spend budget or publish a preview.

## Preview and jobs

`POST /api/preview` and `POST /api/jobs` accept the same JSON object:

```json
{
  "selections": {"micro_texture": ["on"]},
  "whitelist": {"hair_color": ["golden_blonde", "platinum"]},
  "mode": "variations",
  "n": 2,
  "aspect_ratio": "9:16",
  "extra_prompt": "golden hour portrait",
  "seed": 42
}
```

Defaults: `selections={}`, `whitelist={}`, `mode="single"`, `n=1`, `aspect_ratio="9:16"`, `extra_prompt=""`. Seed is optional/null or a signed 64-bit integer. Allowed ratios: `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`.

- `selections` locks the exact selected IDs. Exclusive and boolean locks permit one ID; multi locks preserve all selected IDs. Empty selection arrays omit that attribute. IDs must belong to that attribute; duplicates and wrong types are errors.
- `whitelist` is available in variations mode and contains nonempty arrays of allowed IDs. An attribute cannot appear in both maps, even with an empty selection array. Unspecified attributes are not randomized; declared catalog defaults can resolve unset attributes. Requested snapshots preserve pre-default selections; resolved snapshots include defaults and recipe expansion.
- `single` requires `n=1` and no whitelist.
- `repeat` permits `n=1..24` and no whitelist, producing identical plans for independent provider calls.
- `variations` permits `n=1..24`, samples distinct combinations without replacement, and rejects counts exceeding `combination_count`. Exclusive and boolean attributes pick one allowed value. Multi attributes pick one allowed value or a pair of allowed values: a whitelist of `m` multi values has `m + m*(m-1)/2` options. This bounds subset size; use selections to lock larger subsets.
- The unrestricted product is the product of whitelist option counts, or 1 with no whitelist. For products up to 4,096, the planner enumerates and filters incompatible combinations: `combination_count` is the exact remaining count and `combination_count_exact=true`. Locks participate in filtering. Repeat may exceed this count because it explicitly repeats plans.
- Larger products use seeded independent rejection sampling across **every** whitelisted attribute, not a truncated depth-first prefix. Each attempt draws all attributes independently; conflicting and duplicate combinations are rejected. The budget is 20,000 attribute-draw steps and at most 256 accepted candidates. If no catalog exclusion can apply, `combination_count` is the exact unrestricted product even when large. Otherwise it is the number of distinct compatible candidates actually found (a lower bound), `combination_count_exact=false`, and `combination_count_metadata.method="bounded_search_lower_bound"`. Metadata also provides `unrestricted_product_count`, `visited_nodes` (budgeted draw steps), `node_limit`, and `result_limit`. If fewer than `n` candidates are found within the budget, the request fails before any provider call and asks for a narrower whitelist. Rejection sampling avoids systematically freezing early attributes; individual small batches still need not include every allowed value. Fixed seeds reproduce plans for the same catalog and planner version.
- Sampling uses `random.Random(seed)` with attribute/value IDs sorted before option construction. Seed reproduces plan selection and order for the same library, payload, and planner version. An omitted/null seed is replaced with a random 64-bit nonnegative integer and returned as `selection_sampling_seed`. This controls selection sampling only; it is never sent as a provider deterministic image seed and does not promise reproducible pixels.

Cross-attribute validation is deliberately scoped. `hair_length:shaved` and `hair_length:buzz_cut` exclude `hair_style` values `braided_crown`, `low_bun`, `high_bun`, `low_ponytail`, `high_ponytail`, and `twin_braids`, plus `hair_fringe` values `blunt_bangs`, `curtain_bangs`, `side_swept_fringe`, `wispy_fringe`, `micro_bangs`, `curved_fringe`, and `face_framing_strands`. Rules activate only for IDs present in the loaded library. Direct conflicting locks return a specific 400 such as `conflicting selections: hair_length:buzz_cut + hair_style:high_bun`. Whitelist sampling filters those pairs, including conflicts with fixed locks.

Values may also declare `excludes: ["attribute_id:value_id"]`. References are checked when loading the catalog; one declaration excludes the pair in both directions, including pairs within a multi attribute. This backend does not edit the library. These explicit rules do not solve a universal ontology of scene/hair/weather contradictions or interpret arbitrary `extra_prompt` text.

Prompts are assembled on the server in library order from `base_locks`, selected values' `steers`, `always_on`, and `extra_prompt` (maximum 10,000 characters). New endpoints reject a client `prompt` field and other unknown fields. Preview never invokes the provider.

Preview responds 200:

```json
{"plans": [{"selections": {"micro_texture": ["on"], "hair_color": ["platinum"]}, "prompt": "server-built prompt", "plan_index": 0, "selection_sampling_seed": 42}], "combination_count": 2, "combination_count_exact": true, "combination_count_metadata": {"method": "exact", "unrestricted_product_count": 2, "visited_nodes": 3, "node_limit": 20000, "result_limit": 256}}
```

The example truncates plans and provenance fields for brevity; actual responses contain exactly `n` plans. Jobs respond 202 with `{"id":"32-character hex ID"}`. Poll `GET /api/jobs/<id>`:

```json
{
  "id": "32-character hex ID",
  "status": "partial",
  "total": 2,
  "completed": 1,
  "failed": 1,
  "results": [{"id":"image ID", "url":"/generated/image.jpg", "thumbnail_url":"/generated/image-thumb.jpg", "prompt":"server-built prompt", "selections":{}, "width":900, "height":1600, "created_at":"UTC ISO timestamp", "aspect_ratio":"9:16"}],
  "errors": [{"index":1,"error":"Image generation failed or returned an invalid image."}]
}
```

Statuses: `queued`, `running`, `completed` (all successful), `partial` (some successful), or `failed` (none successful). Results and errors are in original plan order; error `index` is zero-based. Jobs/plans and each image's tags are persisted transactionally. Polling reads a consistent SQLite snapshot.

Every preview plan and generated image record includes `library_hash` (SHA-256 of the loaded catalog bytes: the active v2 library when enabled), zero-based `plan_index`, and `selection_sampling_seed`. `selections` always contains the resolved IDs, never the job's whitelist. `requested_selection_snapshot` contains separate `selections` and `whitelist` maps; `resolved_selection_snapshot` contains each plan's final map. Snapshot maps preserve attribute names/types and value IDs/names/steers as they were at submission, so image details remain meaningful after library edits. Each map entry is `{"name":"Attribute name","type":"exclusive","values":[{"id":"value_id","name":"Value name","steers":"prompt text"}]}`.

Startup safely adds nullable provenance columns to existing `plans` and `images` tables. All inserts name their columns explicitly. Existing rows retain their IDs, selections, files and indexes, and unknown historical provenance stays null rather than using today's library. Their existing ordinal is exposed as `plan_index`. Compatibility-generated images have the current library hash, empty selection snapshots, a per-plan index, and a null sampling seed; optional legacy imports have unknown provenance. Detail lookup does not revalidate historical IDs against today's library. In v2, missing historical label snapshots can be disclosed as `label_snapshot_source="archived_catalog"`. Gallery filtering validates the active/frozen historical union; generation still validates active IDs only.

The ordinary-generation queue allows at most **24 unfinished images** across asynchronous and legacy requests; each job has at most 24 images. Excess submissions respond 429 before invoking the provider. A shared semaphore allows at most **four active native provider calls** across all jobs, the compatibility endpoint and comparison edits within the process. Comparison edits use their separately reserved review-cycle cap instead of the ordinary queue. Failed calls release concurrency capacity and do not discard successful results or refund comparison attempts.

## Image validation and gallery

An image only succeeds after strict base64 decoding, Pillow verification, full pixel decoding, EXIF orientation normalization, dimension checks, and aspect-ratio validation. Limits are 32 MiB decoded input and 40 million pixels. Ratio checks allow integer pixel rounding and up to 2% drift. Provider MIME claims do not determine success or filenames. Stored full images are verified JPEGs and thumbnails fit within 320×320 pixels. Invalid images have no gallery record or served URL.

Full images and thumbnails are encoded to temporary files inside `generated/`, flushed/fsynced, and individually published using `os.replace`. Both are ready before the image, tags, and completed plan commit in one SQLite transaction. Caught write/DB failures remove temporary files and newly published images/thumbs. The pair of renames and SQLite commit cannot be atomic together: a hard crash before the DB commit may leave unregistered files, which are never served. Recovery marks interrupted plans failed and never calls the provider again. Paths in SQLite remain relative to `generated/`; gallery thumbnails never touch library-owned `thumbnails/`. SQLite uses WAL, per-operation connections, busy timeouts, and indexes for tags, dates, ratios, jobs, assets, and plan status.

`GET /api/gallery?q=&page=1&page_size=24&filters=<URL-encoded JSON>&aspect_ratio=` responds:

```json
{"items":[],"total":0,"page":1,"page_size":24,"pages":0}
```

Items contain `id`, `url`, `thumbnail_url`, `prompt`, `selections`, `width`, `height`, `created_at`, and `aspect_ratio`. `GET /api/images/<id>` returns one such record or 404.

Filters are attribute IDs mapped to value ID arrays, e.g. `{"eye_color":["icy_blue","gray_blue"],"micro_texture":["on"]}`. Values use **OR within an attribute and AND across attributes**. In v2 IDs are checked against the active/frozen historical union, including boolean and multi fields. Canonical age filters include their equivalent old numeric tag; unambiguous one-to-one moved aliases can expand to old tags without rewriting rows. Coupled recipe aliases are not treated as equivalent independent gallery filters. An empty filter array has no effect. Prompt search uses the SQLite FTS5 index, treating whitespace-separated terms literally and requiring all terms; query syntax is not executed. Aspect ratio uses exact stored ratio matching. Results sort newest first, with stable ID tie breaking. Tag and ratio indexes, SQL counts, and LIMIT/OFFSET pagination avoid loading the gallery into Python. Page is 1..10,000, page size is 1..100 (default 24), and search text is at most 500 characters. Pages beyond the result set return an empty items array with accurate totals.

Legacy import is optional: set `IMPORT_LEGACY_IMAGES=1` on a future startup. It imports valid local PNG/JPEG/WebP files once, produces verified copies and thumbnails, skips symlinks/invalid files, and leaves unknown prompts/selections empty. It does not invent tags. Original files remain on disk; only database-registered copies are served.

## Compatibility and request security

`POST /api/generate` still accepts `{"prompt":"text","n":1,"aspect_ratio":"9:16"}` with `n=1..4` and responds 200 with `{"data":[{"url":"/generated/...jpg", ...}]}`. Image records now include gallery metadata with empty selections. Partial batches return their valid images plus an `errors` array; all-failed batches return 502. This endpoint shares queue/concurrency limits and pixel validation with jobs.

All requests require a loopback client and loopback `Host` with the backend's port. Preset/catalog/comparison mutations, and `/api/jobs`/`/api/generate` when v2 is active, require exactly one matching `Origin: http://<Host>` and reject cross-site fetches. Local CLI mutations must include that header. Legacy-only paid routes allow no-Origin local CLI calls but still reject mismatching/multiple Origin headers. `/api/preview` does not invoke a provider and uses the ordinary loopback guard. No permissive CORS headers are emitted. POSTs require `application/json`, a valid single `Content-Length`, and at most 200,000 body bytes. Transfer encoding, duplicate JSON keys, nonfinite JSON constants, malformed JSON, and non-object bodies are rejected. Provider exception details and credentials never enter API errors or request logs.

JSON errors have the shape `{"error":"message"}`. Common statuses: 400 invalid input or comparison contract/budget guard, 403 Host/Origin/client rejection, 404 missing record/asset, 408 body timeout, 409 preset key conflict, 410 deleted-preset retry, 411 missing length, 413 oversized body, 415 unsupported media type, 429 full ordinary queue, 502 sanitized ordinary provider failure. Attempted comparison-native failure instead returns its sanitized failed receipt with HTTP 200; it must not be interpreted as a successful candidate. GET and HEAD use the same explicit asset rules: compiled HTML, allowed compiled asset extensions, exact library-referenced thumbnails, verified preview atlases, registered gallery JPEGs and comparison PNGs. Source files, dotfiles, databases, directory listings, traversal, and escaping symlinks are inaccessible.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 /home/renriquez/.hermes/hermes-agent/venv/bin/python -m unittest discover -v
node --test src/browser-tests/*.test.mjs
./node_modules/.bin/tsc --noEmit
```

Tests use isolated temporary directories, real Pillow-encoded bytes, mocked providers, SQLite reopen/recovery and schema migration, provenance round trips, atomic replacement/DB failure cleanup, catalog rules/aliases, legacy filters, queue saturation and shared concurrency. Native generation/edit regressions stub requests, credential/config resolvers and user agent; they exercise actual adapter code and pixel validation without vendor traffic. HTTP fixtures feed raw requests through the real `BaseHTTPRequestHandler` parser with in-memory transport. Comparison tests exercise group crop/mask independence, Reopen, expansion, failure/ambiguous reservations, no-person denial, custom-target publication rejection, tampering and restart persistence. Node state tests cover selection/migration/anchor semantics. These commands do not establish that all assertions pass: report the actual exits/counts and source/test mismatches without removing assertions. They do not read real credentials, request paid generation or restart the live server. Actual headless UI, native capability proof, private full-photo inventory/performance checks and hosted delivery remain separate parent integration/acceptance work; offline passes alone are not final verification or deployment.

## Source/spec mismatches for integration

The amendment's longer approval-state sequence includes `expanded`, `reviewed` and `rejected`; the engine/API implement only the five states documented above. Expansion is an approval event/new bounded cycle returning to `contract_approved`, not a separate state. There is no reject endpoint; rejection means withholding approval or leaving candidates unaccepted. HTTP/engine approval ID/note limit differences remain as disclosed above. Offline tests and source inspection do not establish final integrated acceptance or live deployment.
