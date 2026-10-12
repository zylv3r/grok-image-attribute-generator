# Anchored Attribute Studio v2 — Implementation Plan

> **For Hermes:** Execute approved slices with strict TDD and verification; do not regenerate or replace unapproved categories.

**Goal:** Fix preset persistence and build category-approved, genuinely anchored visual comparisons, with a reconciled and substantially expanded adult fashion/avatar catalog.

**Architecture:** Server-backed presets are canonical across browsers/origins. Comparison previews use approved female reference bases, explicit target regions/effects, preserved non-target pixels where feasible, and source/method/approval provenance. Reference-conditioned generation is not sufficient by itself to guarantee locks: deterministic transforms or masked composition and drift checks are required. Catalog and preview changes ship one confirmed category at a time.

**Tech stack:** Existing Python HTTP/SQLite/Hermes OAuth backend, React/Radix/Lucide frontend, Pillow/lossless comparison masters; optional reference-edit adapter using documented xAI JSON API. No global Hermes provider change. No production/cluster writes.

## Survey and root causes

Repo: /home/renriquez/projects/grok-image-attribute-generator; clean main at 8d56e432a0bbd87fbeca16497a74acf96f6df22f before this task. Live app http://localhost:8123, protected phone gateway. Existing preview batch is complete (893 photographs/97 sheets), but photographs were independent generations and are NOT controlled comparisons. Keep originals and historic gallery records.

`src/App.tsx:Presets` initializes only from `atelier.presets.v1`; its effect calls `writeStorage`; Save always announces saved. `src/lib.ts:writeStorage` silently catches exceptions. No server preset store/API exists. localStorage is origin-specific and can be disallowed.[3] The user's exact phone symptom has not yet been observed on their device; distinguish structural evidence from a confirmed device cause.

Current category issues source-proven in library.json:
- `editorial.face_direction` (Face & Expression) overlaps `face.expression` but includes non-expression concepts; don't blindly map luminous/classic_beauty to emotions.
- `editorial.silhouette` overlaps `body.body_build`, body figure and proportions.
- `phenotype.ethnic_inspiration` (Style Inspiration), `complexion_detail`, `facial_balance` slated for removal from active UI; archive/migrate without losing historic tags or silently pruning presets.
- `outfit.fabric_color`, palette, skin tone/undertone, skin finish/makeup finish require distinct target semantics.
- Hair style currently bundles cuts, arrangement and texture; length/fringe already separate.

## Workstream definition of done

Every stated user requirement is represented in a reviewed category contract and migration ledger. Global preset/variation controls are deployed and work in fresh independent browser contexts and with blocked local storage. Each category has operator-approved IDs, values, female base(s), allowed-change masks/effects, locked parameters, comparison method, rollback and acceptance evidence BEFORE publishing its replacement samples. All existing private outputs/presets/history retained. No claims of zero drift or real lens capture from unverified provider output; no bulk paid regeneration before category approval.

## Immediate global slice G1 — Presets (Fable design / Codex implementation, 30–60min)

Work in a new clean git worktree from the surveyed commit, not a dirty integration checkout. Own new `presets.py`, `test_presets.py`, `src/components/Presets.tsx`, `src/browser-tests/presets-persistence.spec.ts`; targeted adapters in `server.py`, `src/App.tsx`, `src/types.ts`. Parent handles integration and live restart when no paid jobs pending.

Task sequence (each step small):
1. Write a failing browser regression: save in context A, close it, open fresh context B against same backend/shared fixture, expect the saved preset. Run and capture RED. Separately deny localStorage get/set and require no false save-success.
2. Add SQLite preset persistence (`presets.sqlite3`, private/ignored) with UUID IDs, bounded names/drafts, parameterized SQL, transactions and timestamps. Preserve raw draft + schema version/catalog hash; saving an unfinished draft must not require it to be currently generatable.
3. Test create/list/delete/import and restart persistence, malformed payloads, bounds and mutation Origin protection before writing routes.
4. Add `GET /api/presets`, `POST /api/presets` ({name,draft}), `DELETE /api/presets/<id>`, `POST /api/presets/import` ({presets:[{id,name,draft}]}). Every mutation enforces exact origin/loopback and JSON/body guards. Data/source files remain unserved.
5. Import existing browser presets idempotently. Use a canonical legacy-record digest for a server-side import ledger so blocked localStorage or repeated origins cannot multiply/overwrite records. Never clear local presets before confirmed server import. Import failures leave browser copies intact; do not silently discard retired controls.
6. UI reads server canonical state; show Saved only after confirmed write. Network/storage errors retain draft/name and show retry, not a success. Server generates IDs so missing browser crypto.randomUUID cannot prevent Save. Local storage becomes optional cache, not source of truth.
7. Verify save → reload → fresh browser context → backend restart → apply same values. Verify repeated imports and failed saves cannot delete/create duplicates. Do not inspect or clear the user's phone storage through a different agent browser.

PASS: exact selections, whitelist, mode/count/ratio/seed/note/UI preferences survive context/origin/restart and blocked browser storage; readback matches written target. FAIL: phantom saved status, context B missing record, silent schema pruning, import duplicates or exposure/cross-origin mutation. Rollback: previous source/build, leave preset DB and legacy browser copies intact.

## Immediate global slice G2 — Vary All / None / Inverse (Codex, 15–30min)

Own targeted `src/components/Library.tsx`, helper in `src/lib.ts`, tests in new `src/browser-tests/vary-bulk.spec.ts`. Test RED before implementation. Operate on the ENTIRE attribute's valid values, not just twelve visible cards/search matches. Buttons clearly say All N values / None / Inverse. Inverse is the complement in catalog order. These are alternatives for exclusive/boolean types, not concurrent contradictory values. Other attributes and locks remain unchanged; switching to Vary removes only that attribute's lock. None preserves the empty Vary preference and means unset, not boolean off. Explicit search-result bulk scope can be a later confirmed enhancement, not implicit behavior.

PASS: hidden/search-filtered values included, deterministic complement, all→inverse empty, none→inverse all, other selections unchanged, persistence captures pool. FAIL: only visible cards changed, unrelated locks erased, empty pool changes Off, or single-mode silently ignores pool. Rollback: previous UI/helper while retaining presets.

## Preview foundation P0 — Approved reference comparison contracts (Fable/Astra, 45–90min after approval)

Create `comparisons.py`, `test_comparisons.py`, `src/components/ComparisonReview.tsx`, versioned category contracts under `catalog/v2/`. Existing library and photo registry stay active until a category's review is approved.

Contract per preview group: category_id, attribute_id, catalog_version, female_subject_id, base_image_id + byte hash, lossless base crop dimensions/angle, optional scene/depth regions, allowed_change_fields/regions, locked_fields, method, approved value list, operator approval state, provenance and verification metrics.

Use ONE base per group and fork EVERY value directly from that base, NEVER daisy-chain edits. One female character may need distinct approved portrait/eye/full-body/technical-scene crops; all values within a group use exactly the same crop/base. Keep body/outfit/background/lighting/palette/pose/head position locked unless they are the target or an explicitly declared unavoidable consequence.

Methods:
- Masked photographic recolor for hair color; preserve hair geometry and texture, and non-hair pixels exactly. Source and comparison masters must be lossless PNG; JPEG encoding cannot prove pixel equality outside masks.
- Fabric color: controlled texture/cloth swatches, not a new woman render per color. Same fabric patch, light and folds, recolored pixels only.
- Hair styles, face expressions/shape, poses/body/clothing: reference-conditioned edit using owned image bytes, then masks/composition and geometric/color drift checks where feasible. No undocumented API mask assumptions. Reject/review drifts instead of silently calling them anchored.
- Grain, white balance, highlight rolloff and some focus/blur demos: deterministic transformations of one scene, labeled simulated effects. Focal-length fixed-camera FoV crop demo is not an actual lens/perspective measurement; aperture DoF demos hold exposure constant by declared compensation; shutter motion needs declared moving regions/direction. Physical coupling is shown, not hidden.[8][9]

xAI documents `/images/edits` JSON requests with local base64 data URIs; its multipart OpenAI SDK edit path is unsupported.[1] Multiple references support up to five inputs.[2] Current installed model/OAuth compatibility must be exercised; do not assume documentation for image-2.0 establishes support by grok-imagine-image-quality. No global config changes, credential exposure or public upload of private source images.

PASS: reference/provenance recorded, every value forks baseline, deterministic outside-mask delta zero on lossless masters, geometry/identity drift checked for edits, rejected samples withheld, technique honestly labeled. FAIL: new faces/background/clothes/poses in color samples, text-only generation fallback, unchecked drift, chained references, or unsupported provider assumptions. Rollback: restore previous versioned registry pointer; keep old/new artifacts for review. Model routing Codex implementation, Fable integrity/Astra false-green review.

## Category confirmation order and proposed reconciliation

Each category repeats: present taxonomy + anchor + mask/effect contract → user confirms/edits → bounded pilot → user accepts/rejects drift → expand approved values → independent physical/content review → publish category → ask next category. Estimate 30–90min source work/category, provider cost/time measured from its pilot, never invented. No work in dirty integration checkout.

### 1 Hair — FIRST confirmation

Preserve `hair_color`, `hair_length`, `hair_fringe`, `hair_accessory`; reconcile `hair_style` texture/cut/arrangement rather than padding similar labels. Expand natural blonde/red families substantially, with visibly distinct depth/undertone, using documented professional color terminology as naming references, not branded proprietary formulas.[10][11][12][13][16][17] Exact proposal after specialist review.

Color contract: same female face/skin/eye color, hairstyle/length/fringe, gaze/head position, outfit, background, light/camera/crop; only hair pigment changes. Style contract: same woman/angle/clothes/background/lighting and one consistent neutral hair color; only style geometry changes. Hair accessories and color treatments such as highlights/ombre become orthogonal controls/recipes only if their interactions are explicit. Don't offer buns with shaved hair or inconsistent color-treatment combinations.

### 2 Face / eyes / expressions

One canonical expression attribute only. Preserve/resolve old expression IDs with an explicit migration table; face_direction non-expression values can be retired or mapped only with disclosure. Expand named expressions into visible mouth/brow/eye movements, not purported emotion/intent inference from real faces; movement-based references can inform terminology.[21] Eye color expands while same eye shape/face/lighting stays fixed; eyelashes use a close eye crop with same iris, eye geometry and face. Face shapes share same female identity/view with only declared contour geometry changed; non-target landmarks remain fixed.

### 3 Skin / pigmentation

Remove active Style Inspiration, Complexion Detail, Facial Balance. Keep useful tone/undertone/texture controls reconciled with cosmetics finish. Add appearance-only pigmentation distributions such as freckles density/location, diffuse/sparse pigmentation, moles and vitiligo-like depigmented patches without clinical diagnosis claims. Old IDs remain readable in historic records; preset migration shows unresolved/removed controls before application.

### 4 Body / figure / fitness

Converge silhouette/body_build into canonical orthogonal adult avatar controls: frame/build, stature, shoulder width, waist definition, hip breadth, bust volume, thigh fullness, calf/leg proportions, torso/leg balance, muscle definition. Existing silhouette names become explicit recipes/presets rather than contradictory concurrent knobs. 'Fitness' should describe visible physique conditioning, not infer health or ability from body size. All previews use same adult woman, modest opaque fitted outfit, light, camera and pose; body/clothing-fit changes required by target morphology are declared consequences, garment design/color remain fixed. No nude/sexualized examples or medical measurement promises.

### 5 Wardrobe / textiles / garment color

Expand dress, top, bottom, outerwear, footwear and accessory families extensively; separate garment class, cut, neckline/collar, sleeve, hem/length, waist/rise, fit, closure, construction details, material, pattern, color and layering. Use reviewed taxonomy sources to distinguish garment silhouettes from their parts, not combine impossible full outfits.[4][5][6][7][18][19][20] Garment color uses texture swatches, no woman render. Actual garment-style comparisons use fixed woman/base and consistent material/color when those aren't the target. Material comparisons use same garment or fabric patch/crop and light.

### 6 Poses / orientation

Expand standing, seated, walking, leaning, kneeling/crouching, hand/arm/leg gestures and editorial transitions while distinguishing primary pose from orientation/head/gaze/gesture modifiers. Same female identity, wardrobe/colors, studio/background, lens and lighting across pose comparisons; anatomy and changed occlusions are verified. Do not keep pose aliases as inflated duplicates.

### 7 Identity controls — age and gender

Age is an accessible numeric dial/slider + input, adult bounds 21–85 initially (operator can amend), no paid thumbnail renders. Add explicit generation gender/presentation selection, while ALL sample baselines remain women. Numeric/range schema needs server validation and old age IDs mapped exactly; do not silently round or discard historical data.

### 8 Photography / optics

Same approved scene/model/shot for focal length, aperture, shutter motion, grain, focus target, white balance and highlight rolloff. Declare allowed target consequences (FoV, DoF, motion blur, color/tone changes), so 'all colors locked' does not falsely forbid white-balance effect. Simulated previews labeled as such; actual generation presets remain steering approximations.[8][9] No new scenes/subjects to sell an optical setting.

### 9 Editorial mood / narrative

Expand substantially after deciding distinct semantics. Mood should be an explicit style recipe/allowed aesthetic treatment on one anchor, not duplicate expressions/lighting/color-grade synonyms. Narrative requires action/gesture/prop changes: define a visible allowed-change set and locked identity/wardrobe/camera/environment; cannot honestly show 'writing' versus 'conversation' with every pose/prop locked. Ask the operator to confirm these necessary exceptions, don't silently violate locks.

### 10 Lighting / composition / scenery / props

Reconcile remaining overlapping physical controls and recipe layers. Lighting/composition use one scene with target effects only. Scenery intentionally changes environment but preserves subject/wardrobe/pose/light style/camera; backgrounds can't be simultaneously immutable and the target. Props permit only declared object/interaction changes. Preserve the old gallery and reference source set.

## Council instructions and bounded review

Two rounds maximum. Technical Astra red-teams false greens, masks, receipts, server preset security/import/recovery, physical optics coupling, provider assumptions and costs. Fable judges causal completeness, category sequencing and migration semantics. Wardrobe/body domain and visual/UX experts propose a reconciled taxonomy and comparison presentation, citing actual tree/source passages. CRITICAL means damage or false-completion, not aesthetic preference. Every finding needs a file/source citation or executable verification. R2 audits its own r1 disposition first; residual criticals go to ONE operator disposition (targeted amendment/hold/waiver), no endless review loop.

## No-touch and rollback

No deletion/rewriting of the 893 existing generated photos, masks/metadata absent until explicit category pilot, presets/imports preserved, no mass thumbnail batch, no other Hermes profiles/plugins/config, no tunnel weakening, no public image/credential upload, no remote force push. Category publication uses version pointers and a captured prior pointer, not destructive replacement. Global bug fixes can ship before category confirmations; catalog/paid preview changes cannot.
