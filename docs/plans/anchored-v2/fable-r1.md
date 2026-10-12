# Council R1: Design-integrity / causal architecture seat

I reviewed PLAN.md against the repo at commit 8d56e43 (clean), read-only. None of the plan is built yet: there is no `presets.py`, `comparisons.py` or `catalog/v2/`, and the backend only calls `/images/generations` (server.py:301). I also wrote this report to the plan file, `/home/renriquez/.claude/plans/read-only-council-round1-repo-vivid-shell.md`.

## VERDICT: CHANGES-REQUESTED

The plan names the right causes:
- Presets are stored only in the browser.
- `writeStorage` swallows write errors, and Save says "saved" anyway.
- The 893 preview photos were generated independently, so they aren't controlled comparisons.

Three things are still missing:
- A way to publish one category at a time.
- A hard ordering gate that protects the raw preset data.
- An owner for about 15 attributes.

Nothing here is CRITICAL, because no code has changed. Each item turns into data loss or a false pass as soon as the first category (Hair) lands.

---

### [HIGH] The current loader already strips presets on load, so the planned import only sees the stripped copy
**Claim:** Step G1.5 imports browser presets "without silently discarding retired controls."

**Reality:**
- `src/App.tsx:57-75` loads `atelier.presets.v1` and runs each draft through `cleanDraft(p.draft, library)`.
- An effect then writes that stripped copy back to storage on mount: `useEffect(() => writeStorage(presetKey, presets))`.
- `pruneChoices` (`src/lib.ts:46-73`) drops any attribute or value ID that isn't in the current library.
- The saved draft gets the same treatment (`App.tsx:200,253`).

**Consequence:** The first page load after any catalog ID change destroys raw preset data before any importer runs. That breaks the plan's own rule that presets and imports are preserved.

**Fix:**
- The importer reads the raw string from `localStorage.getItem(presetKey)` before `cleanDraft` runs and posts it unchanged. The server stores `raw_json` plus `catalog_hash`.
- Remove the write-on-mount effect.
- **Gate:** no `library.json` ID change merges until G1 is live and this test passes: seed a preset that uses a retired ID, load the app against a catalog without that ID, and check the server row still holds it byte-for-byte.

### [HIGH] No per-category catalog state: one category edit breaks verification for all 97 attributes
**Reality:**
- `Catalog.load` hashes the whole `library.json` (server.py:121-125).
- `scripts/verify_photographic_previews.py:22` and `generate_photographic_previews.py:205` both check that whole-file hash.
- There is one global preview manifest (server.py:497), joined to the library by attribute and value ID.
- The progress text is one global count, "N/893" (photographic.spec.ts:81).
- App.tsx:45 tells users every attribute uses a "fixed photographic prompt baseline".

**Consequence:** The first Hair edit causes four problems at once:
- The recorded verified completion fails for every attribute.
- Renamed values silently lose their preview photo (server.py:543-547).
- The 893 total changes.
- The page shows one method label even though methods will differ.

The likely "fix" for the failing check is regenerating everything, which is the paid bulk change the plan forbids.

**Fix (in P0, before Category 1):**
1. Freeze a byte copy of the current catalog as `catalog/v1/library.json`, and point both photographic scripts at it.
2. Give each attribute a preview source in priority order (approved comparison, then v1 photographic, then illustrative), recorded in `catalog/v2/active.json` with the previous entry kept for rollback.
3. Count progress per source instead of one global 893.
4. Show the method label per attribute.

### [HIGH] Category approval is described in prose but never recorded or enforced
**Reality:** The approval cycle on line 69 has no persisted record. The contract field "operator approval state" (line 53) has no defined states and nothing enforces it.

**Consequence:** An agent can declare its own approval, and a paid pilot can run before any contract exists.

**Fix:**
- Store `catalog/v2/<category>/approval.json` with states `draft → contract_approved → pilot_done → pilot_accepted → expanded → reviewed → published | rejected`.
- Each transition records `{by:"operator", quote, at, artifact_sha256}`.
- `comparisons.py` refuses to call the provider below `contract_approved` (with a matching contract hash), refuses to expand values below `pilot_accepted`, and refuses to switch the published pointer below `reviewed`.
- Write a failing test for each refusal first.

### [HIGH] "Zero change outside the mask" is true by construction, so it can't pass or fail anything
**Reality:**
- Compositing `base*(1-m) + edit*m` leaves every pixel outside the mask identical by definition.
- The plan never says where the hair, face or garment masks come from.
- The only image library is Pillow, and the repo has no segmentation code.

**Consequence:** This is a false pass. A mask that misses stray hairs or spills onto skin still passes. So does a painted-looking dark-to-platinum recolor.

**Fix:**
- Keep the zero-delta check, but only as a guard against compositing bugs.
- Add to PASS: where each mask came from (hand-drawn or a named model) plus its hash, a mask-coverage overlay in ComparisonReview, and an operator realism check at the pilot.
- Pick a mid-light neutral hair base so no sample requires lightening.

### [MEDIUM] The hard-coded hair exclusions switch themselves off when IDs change
**Reality:** server.py:107-117 hard-codes pairs such as shaved/buzz-cut versus buns, braids and fringes. It keeps a pair only `if left in known and right in known`. Only one pair is tested (test_server.py:360).

**Consequence:** The Category 1 hair-style rename silently drops the "no buns with shaved hair" rule the plan requires (line 75).

**Fix:** Move these rules into the catalog's existing `excludes` field (validated at server.py:94-103), make a missing ID a load error, and test every expected pair.

### [MEDIUM] About 15 live attributes have no approval category
**Reality:** I dumped `library.json` (25 categories, 893 values). None of the plan's 10 categories covers these:
- Makeup: `lip_color`, `eye_makeup`, `blush_placement`
- Weather: `weather`, `time_of_day`, `wind`, `season`
- Location: `ground_surface`, `wall_surface`, `vegetation`
- Style: `photo_genre`, `contrast`; `color_grade` and `palette` are mentioned only as "synonyms"
- Others: `eyewear`, `micro_texture`, `camera`

**Consequence:** Even if every slice ships, these attributes keep uncontrolled preview photos and no contract. That breaks the definition of done on line 26.

**Fix:** Add `catalog/v2/coverage.json` that maps every attribute ID to exactly one category or to `retain-v1-unchanged`, plus a test that this set equals the library's attribute set.

### [MEDIUM] Numeric age has no schema path
**Reality:**
- The server only accepts attribute types exclusive, boolean and multi (server.py:80).
- Selections must be known string IDs (server.py:149-154).
- Gallery tag values are stored as TEXT (gallery.py:115-118), so range filters would compare text, not numbers.
- Age IDs are already inconsistent: `"24"` sits next to `age_21` through `age_80`.

**Closed choice (I recommend A):**
- **A.** A slider over 65 discrete IDs, `age_21` to `age_85`. Map `"24"` to `age_24`. Old IDs stay valid and gallery filters keep working. "Vary age" becomes a range that expands to IDs. No schema change, and it's easy to undo.
- **B.** A real `numeric` attribute type with `{min,max}` in the draft. This touches about 5 files and needs a gallery tag-table migration.

### [MEDIUM] Retiring attributes makes old gallery tags unfilterable, and there's no way to show dropped preset controls
**Reality:**
- Gallery filters go through `validate_map` (server.py:783), which rejects retired attribute IDs with "unknown attribute".
- The client also strips them from the gallery state (lib.ts:77).
- Category 3 promises that presets "show unresolved/removed controls", but G1 has no API for it.

**Fix:**
- In G1, applying a preset returns `{draft, dropped:[...]}`, and the UI shows the dropped list before applying.
- Add a `retired` block to the catalog. Gallery filtering and display accept retired IDs; generation rejects them.

### [MEDIUM] The edit adapter is called "optional" but 6 of the 10 categories need it
**Reality:**
- Line 9 calls the reference-edit adapter optional.
- Lines 60 and 75-110 make it the only method for hair style, expressions, face, pose, body and narrative.
- The backend only calls `/images/generations` (server.py:301).
- xAI's docs show JSON requests with base64 images for `grok-imagine-image-2.0` (sources/1.md:11,27). Whether the installed model and OAuth support edits is unverified.

**Fix:**
- Add a single-call adapter probe to P0 that records model, HTTP status and whether the base image was respected.
- If the probe fails, those categories offer only honestly labeled independent renders, or wait for an operator decision.
- Hair color (masked recolor) and fabric swatches don't depend on it and stay unblocked.

### [LOW] Source ledger doesn't match the source files
**Reality:**
- `sources-ledger.json` lists IDs 1-24, but files exist only for 1-13 and 16-21.
- `sources/16.md` is a 290-byte navigation stub, yet the plan cites [16] for hair color names.
- Citations [1], [2], [3] and [21] check out (1.md:11, 2.md:9, 3.md:16, 21.md:21).

**Fix:** Drop [16] from line 73 or fetch it again, and trim the ledger to the files that exist.

---

## Seat answers

- **What ships now:** G1, G2, the exclusion-rules move, the frozen v1 catalog plus per-attribute preview pointer, and `coverage.json`. None changes catalog IDs or costs anything to generate. Every ID rename or retirement, new value and preview publication waits for its category's approval.
- **Deterministic transforms vs reference edits:**
  - Deterministic and honest, labeled "simulated": masked hair recolor, fabric swatches, white balance, grain, highlight rolloff, focal-length crop and depth-of-field blur.
  - Reference edits: style, expression, face shape, pose, body and narrative. Label these "anchored-edit (drift reviewed)" only after a drift check and operator acceptance, never "locked".
- **Combinations:** every value forks from one base image hash, with no chaining. State plainly that combinations are not previewed, so nobody implies the locks hold across combined attributes.
- **Duplicate controls (closed choices):**
  - `face_direction`: **A (recommended)** retire it with no mapping and show a dropped notice on presets that use it; **B** map `confident` to `expression:serious` plus `gaze_direction:camera`, with disclosure.
  - `silhouette` vs `body_build`: **A (recommended)** turn silhouette values into read-only catalog recipes, stored separately from user presets; **B** retire them.
  - `pale_pink_freckled` (from `complexion_detail`): show a dropped notice; don't automatically map it to `freckles:on`.

**Verification commands:** `sed` over `src/App.tsx:40-135`, `src/lib.ts:1-120`, `server.py:60-175,495-560` and `gallery.py:105-130`; `grep library_hash scripts/verify_photographic_previews.py`; a taxonomy dump with `python3 -I` over `library.json`; `grep` over `sources/{1,2,3,21}.md`; `ls sources/`.
