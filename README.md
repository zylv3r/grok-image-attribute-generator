# Atelier — Anchored Comparison v2 Image Studio

A local, server-backed visual composition and comparison studio for adult, nonexplicit fashion/editorial images. Provider credentials remain on the server. The commands below launch the local application and an authenticated temporary tunnel; publication of controlled comparison photos still requires explicit operator review.

## What it does

- Data-driven **categories → attributes → values** with local thumbnail steering guides and prompt descriptions.
- Explicit **exclusive**, **on/off**, and additive **multi-select** semantics. Unset is different from off.
- Lock selections for every image, repeat one direction, or whitelist allowed values to generate distinct variation plans. Only whitelisted attributes vary.
- Server-built prompts, optional reproducible **selection-sampling** seed, seven aspect-ratio choices, bounded asynchronous jobs and per-image error reporting.
- Persistent SQLite gallery with FTS prompt search, indexed attribute/value filters, thumbnail cards, bounded pagination, original downloads, metadata details and selection reuse.
- React, Radix UI accessibility primitives and Lucide icons; responsive category navigation, installation-wide server-persisted presets, keyboard controls and explicit error/empty states.

## Active controls and historical data

The checked-in v2 bundle contains **12 categories, 129 attributes and 1,596 values**. `catalog/v2/active.json` activates controls while comparison thumbnails remain **pending operator approval**, not full controlled photo coverage. `library.json` and `catalog/v1/library.json` preserve byte-identical v1 catalog bytes: 22 categories, 97 attributes and 893 values. Existing gallery photographs, tags and archived labels are retained.

- Hair has 44 uniform pigment targets and separate cut, length, texture, arrangement, parting, finish, fringe, accessory and color-treatment controls. Pigment comparisons use local recolor; split/two-tone and geometry changes have separate reference-edit review groups.
- Eyes have 27 pigment targets and eye-closeup mask declarations. One expression control, face shape and makeup have separate review groups. Operators choose the actual original image/crop; framing declarations do not create a reviewed photograph.
- Skin uses appearance/pigmentation controls. Former style-inspiration vocabulary (`ethnic_inspiration`), `complexion_detail` and `facial_balance` are absent from active controls. Body has 15 controls including bust/thigh volume and disclosed figure/fitness appearance recipes, without health or ability inference.
- Wardrobe has 37 controls and explicit garment-set/layering compatibility rules. Fabric colors use illustrative textured swatches, not new woman renders. Poses include 176 pose values plus orientation, arm gesture and head tilt.
- Age uses accessible range/number inputs over `age_21`…`age_85`; gender/presentation is a generation selector. Defaults are age 24 and woman. Both are control-only and launch no comparison render. Person baselines declare adult women; this is operator metadata, not pixel-based detection.
- Photography shares `photography:same_scene`. Editorial mood has 24 disclosed local grade recipes; narrative has 36 reference-edit action recipes with declared consequences and independent review gates.

[Aliases](catalog/v2/aliases.json) account for every legacy attribute/value pair: 684 keep, 143 move, 49 disclosed recipe and 17 retire-unresolved dispositions. [Coverage](catalog/v2/coverage.json) assigns all 97 old attributes an owner; [retirement records](catalog/v2/retired.json) preserve original wording. Historical gallery filters accept frozen IDs. Reuse and preset Apply show migration previews and preserve raw unknown, retired or conflicting data for an explicit decision. Coupled recipes cannot silently become independent variation pools. Generation rejects unsupported legacy IDs until explicitly resolved.

## Anchored comparison review

Category Review targets each attribute's declared `comparison_group`. Each group owns its base/crop, masks, contract, approvals and artifacts; different groups may use different originals/crops. Photography shares one scene. Unscoped category APIs remain for older single-category callers; new clients should explicitly target a group.

1. Choose an owned gallery photograph and optional normalized crop. Review the selected group's `review.baseline_requirements` and explicitly confirm every requirement; `/base` sends the exact list as `baseline_confirmations`. Hair geometry/reference groups require neutral medium-brown uniform pigment, while hair recolor permits any suitable original pigment. Eyes require the same approved close-eye view with visible iris/lash boundaries; rendered photography controls require one shared immutable scene. Confirmation records human operator attestation, not image classification. The server registers a lossless immutable PNG master without rewriting the source. Every candidate forks that original directly; edited predecessors cannot become new references.
2. Draw/edit normalized polygons, including keyboard/coordinate editing, and inspect the registered overlay. Localized controls need drawn footprints; explicitly global effects and swatches may create declared whole-frame footprints. Creation is not operator approval.
3. Local methods may stage drafts without provider calls. **Approve contract** binds exact contract/base/mask/overlay hashes and an integer provider-attempt cap of **0–3**. Cap 0 allows local review only. Approval starts no render/batch.
4. Inspect individual candidates with before/after, side-by-side, zoom and receipts. **Accept selected candidates** (`pilot`) is separate from **Publish selected group candidates**. Publication requires those accepted artifacts, valid provenance and canonical target settings; it does not approve other groups.
5. **Approve another bounded expansion cycle** requires an accepted pilot or published state, current contract hash, nonempty note and cap 0–3. It starts no provider request. Current-cycle usage resets; total consumed attempts never resets.
6. **Reopen review group** requires `expected_contract_hash` and a nonempty `approval_note`. It archives the previous review in history, advances its revision and returns to draft for base/mask edits. Current approvals/publication clear; previous assets, receipts, request-key tombstones and consumed attempts remain. Direct approved base/mask replacement is rejected.

Contract and expansion approvals always send `artifact_ids=[]`, regardless of checked or stale candidate selections. Pilot and publish require a nonempty explicit selection from the current review; publish additionally requires every selected candidate to be accepted. All four stages check baseline/mask/overlay integrity and the current contract hash, with prior cycle approval provenance checked for later stages.

Group locks, allowed changes and baseline requirements derive from their attributes' actual `preview_contract` declarations. Shared photography groups retain validated method-specific consequences, and native prompts use the selected target's declared allowances. See [the exact baseline confirmation and group contract rules](BACKEND_API.md#comparison-groups-bases-and-masks).

The review engine decodes and supplies the same validated asset snapshot bytes to local processing and native edits. Comparison HTTP GET/HEAD validates and serves the same bounded snapshot, so validation does not authorize a later unvalidated file read.

Reference edits reserve budget transactionally before invocation. Failed/ambiguous attempts remain consumed after interruption. The same request key returns recorded success/failure or refuses a reserved/in-flight attempt without blind retry. Keys remain unique per category across groups, revisions and cycles. Expansion rejects unresolved reservations on the current contract. A cycle cap is not a lifetime maximum or authorization for a paid full-catalog batch. No masks or candidates are automatically approved/published.

The implemented states are `draft`, `contract_approved`, `pilot_done`, `pilot_accepted` and `published`. Historical proposals also use `expanded`, `reviewed` and `rejected`; those are not implemented states. Expansion returns to `contract_approved`. There is no reject endpoint: rejection means withholding approval or leaving a candidate unaccepted.

Native edits use validated original PNG snapshot bytes in a server-built JSON data URI and share the four-call provider semaphore with ordinary generation. Unsupported edits fail closed without text-generation fallback. Synthetic fabric references declare `no_person` and cannot enter native person editing. Browsers cannot supply source URLs, paths, bytes or edit prompts.

Registered base/mask/overlay/output PNGs and receipts pin inputs, dimensions, method/parameters, contract/output hashes, target changes and exact outside-footprint equality. The composited master has zero changed pixels where mask alpha is zero. This does not prove segmentation, identity, anatomy or realism inside the footprint; operator review at 1×/2× remains required. Custom overrides remain inspectable drafts and cannot publish as canonical catalog targets. Declared neutral baseline candidates preserve original pixels and cannot pass the target-effect publication gate.

## Honest local effects and thumbnails

Local effects are deterministic for fixed original/mask/parameters and method version, with seeded grain. Pigment targets are illustrative sRGB recipes, not calibrated dyes. Fabric swatches use sampled or synthetic woven texture, not measured fabrics or garment geometry renders.

Receipts disclose optics assumptions: FoV is fixed-camera crop/resample without perspective change; aperture/focus blur uses a declared mask-defined depth plane at constant brightness; motion blur requires a moving/swept region. Grain is digital noise, white balance is RGB adjustment, and highlight rolloff cannot recover clipped detail. Grades, contrast, palette and editorial recipes change disclosed colors/tones without generating outfits or subjects. These are simulations, not physical lens/film measurements.

The library labels approved comparisons, compatible legacy independent photos, swatches, control-only values and pending/review-required thumbnails. Independent generations can change identity and other details and are never relabeled controlled. Publication projects only selected valid group attribute/value targets; tampered provenance is withheld. Legacy photographic manifests/contact sheets remain historical sources, not permission to regenerate v2. See [legacy photographic previews](docs/PHOTOGRAPHIC_PREVIEWS.md).

## Saved persona reference and image policy

The Studio displays **Persona B latest**, one overwriteable working set. `base-personas/current.json` points at `persona-b/latest/persona.json`. View files in that folder are served live. `sheet.jpg` is rendered from those views on each request, so the same URL shows the current character after a refresh. Numbered packs such as v1 stay on disk and are not the served set. A numbered pack, if selected again, remains hash-pinned.

- `GET /api/base-persona` returns the selected reference metadata and asset URLs.
- `GET /base-personas/persona-b/latest/sheet.jpg` is the stable sheet to keep open.
- `GET /base-personas/<id>/latest/<asset>` serves allowlisted files from the working set. `GET /base-personas/<id>/v<revision>/<asset>` still serves a hash-pinned pack when that pack is the selection.
- `GET /api/image-policy` reports the enforced `grok-imagine-image-2.0` generation and reference-edit model, with no legacy fallback. Historical assets retain their actual source-model metadata.
- Saving a persona does not automatically supply it to ordinary text-to-image generation. Reference edits explicitly supply original bytes; group masks, pilots and publication still need their own approvals.
- The latest sheet states its own limits: the set is not locked, angles are quality-model edits, and the body face is not a pixel lock to the portrait.

Read-only desktop/mobile acceptance: `node acceptance/saved_base_live.mjs`. It checks the real running app at 1440, 390 and 320 pixels, all asset responses, decoded/visible reference-sheet pixels, policy metadata, visible caveats and page overflow. It makes no provider calls or approval writes.

## Requirements and startup

Use the existing Hermes Python environment with Pillow and requests, plus Node/npm for the UI build. From a WSL/Linux terminal:

```bash
cd ~/projects/grok-image-attribute-generator
./scripts/run-server.sh
```

Open **http://localhost:8123**. On the existing installation the launcher starts the matching `atelier-image-studio.service` idempotently and checks health; it does not kill another listener or restart running jobs. On a checkout without a matching installed service it runs in the foreground and builds a missing/stale UI. `./scripts/run-server.sh --check` checks prerequisites without starting or installing anything. `--foreground` explicitly selects foreground mode. Run only one backend per checkout/database; stop an existing backend before replacing it. `PYTHON_BIN` can select another Python executable with Pillow and requests, and `PORT` selects a loopback port.

### Private temporary tunnel

With the server running, use a second terminal:

```bash
cd ~/projects/grok-image-attribute-generator
./scripts/run-tunnel.sh
```

The tunnel launcher requires `cloudflared` on PATH or in `~/bin`, checks the local server, and creates its **own** ephemeral loopback authentication gateway and Cloudflare quick tunnel. It does not replace other phone proxies/tunnels. In an interactive terminal it prints a private access link; opening it installs a Secure, HttpOnly access cookie. The bare public URL rejects anonymous gallery/API access. Keep the private link to yourself: anyone with it can access your gallery and the app's paid-generation controls.

The original app remains loopback-only. The gateway validates authentication, the exact external Host/Origin, body limits and expiration before rewriting the trusted local hop. This preserves POST/DELETE protection for generation, comparison reviews and presets. No generation or category approval is started by either launcher.

```bash
# One-hour tunnel (seconds; maximum/default lease is 86400):
./scripts/run-tunnel.sh --ttl 3600
# Use a different local app port:
./scripts/run-tunnel.sh --app-port 8130
# For captured automation output, never print the private access URL:
./scripts/run-tunnel.sh --no-print-private
```

The tunnel stays attached to that terminal. Ctrl+C, SIGTERM, expiration or an early cloudflared exit shuts down only the launcher's own tunnel/gateway. WSL and the host must remain running. Quick-tunnel addresses change on each launch. State and the private link are stored in a unique owner-only directory under ignored `runtime/tunnels/`, never committed. Non-interactive output omits the private link; do not publish/redirect interactive output containing it. Run either script with `--help` for options.

Source files, Git internals and databases are not public app routes.

Hermes must already be authenticated for xAI OAuth image generation. Credentials are resolved exclusively on the server. Consult the Hermes documentation for authentication/configuration; do not paste secrets into this app.

Environment:

- `PORT` (default `8123`), `HOST` (default `127.0.0.1`, loopback only).
- `HERMES_SOURCE` if the Hermes source checkout is in a nondefault location.
- `IMPORT_LEGACY_IMAGES=1` opts into importing existing verified image files without inventing prompts or attribute tags. Legacy untagged images appear in the gallery but do not match attribute filters.

Gallery/jobs persist in `gallery.sqlite3` and `generated/`; presets in `presets.sqlite3`; comparison contracts, approvals, history and attempt ledger in `comparisons.sqlite3`, with registered PNGs under `generated/comparisons/`. Restart preserves unchanged reviews/publications; changed catalog definitions invalidate affected gates and masks. Interrupted comparison reservations stay consumed without automatic retry. Run one backend per database in a durable directory and back up databases/assets together while stopped.

Presets use an installation-wide collection with idempotent save/import ledgers and deletion tombstones. Raw legacy records and unresolved data are archived before migration; failed import retains browser originals. A draft may save `comparison` metadata (`category_id`, optional `group`, `baseline_asset_id`, `contract_hash`, `locked_fields`). Apply checks the current baseline and contract. **Saved anchors are comparison/reference context only, not reference-conditioned generation**: `/api/preview` and `/api/jobs` receive ordinary selection fields, not anchors. Native conditioning exists only in the separately gated comparison-edit workflow.

## Selection model

- **Lock:** select at most one value for an exclusive/boolean attribute; additive multi attributes can contain several.
- **Vary:** checked values form the allowed pool. Other attributes stay locked.
- **Single:** one locked composition.
- **Repeat:** multiple images from identical resolved selections (provider imagery may differ).
- **Variations:** distinct valid attribute combinations; impossible requested counts are rejected before any provider call.
- Cross-attribute compatibility checks evaluate catalog exclusions, required components and recipes, including hair and wardrobe layering rules; this is not a universal semantic consistency solver.
- Gallery filters are **OR within an attribute**, **AND across attributes**. A boolean left unset is not equivalent to explicitly off.

Interrupted jobs retain completed results and mark unfinished plans failed. They are not automatically re-submitted to the paid provider. A failed job can still have partial successful images; inspect the per-image report before retrying.

API details and variation-count semantics: [BACKEND_API.md](BACKEND_API.md).

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 /home/renriquez/.hermes/hermes-agent/venv/bin/python -m unittest discover -v
node --test src/browser-tests/*.test.mjs
./node_modules/.bin/tsc --noEmit
```

The offline Python suite uses mocked providers/credential/config resolvers, actual decodable fixture images and isolated temporary databases/assets. Node tests exercise selection, migration and comparison state, including retained pilot selection during expansion through real component handlers in a socket-free fixture. The commands above are checks to run, not a claim that final acceptance has passed. These checks do not establish vendor capability, operator approval, full controlled photo coverage or deployment. `npm run test:browser` exercises headless UI with simulated APIs after a frontend build. Integration, remaining source/test mismatches, hosted UI/native verification and delivery remain the parent's responsibility.

Separately authorized actual headless-browser generation with **no mocks/interception**:

```bash
# One paid image, selected through the UI:
RUN_PAID_GENERATION=1 STUDIO_BASE_URL=http://localhost:8123 npm run test:actual
# Two paid whitelist variations + locked values + pixel dimensions + real gallery filters:
RUN_PAID_GENERATION=1 STUDIO_BASE_URL=http://localhost:8123 node acceptance/real_variations.mjs
```

These scripts make paid provider requests; do not run them as offline checks. Their existence is not authorization to run them or a new v2 full-catalog batch. Evidence is saved locally, not committed. Actual output dimensions are validated independently of claimed MIME type/provider success.

## Extending the library

Preserve stable category/attribute/value IDs. Add meaningful names, descriptions and `steers`, choose accurate selection semantics, and give every attribute/value a safe local thumbnail. Run the library checks and planner checks after any change. Generated result metadata stores resolved selections rather than the entire allowed whitelist. Historic IDs/names should not be silently repurposed.
