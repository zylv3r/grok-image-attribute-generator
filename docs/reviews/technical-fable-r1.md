## VERDICT: CHANGES-REQUESTED

Nothing here is critical damage or a false green that blocks shipping, but 3 high and 4 medium gaps would remain even after the contract is fully executed. Scope: PLAN.md, the worker briefs (`image-app-work/{backend,library,frontend}.txt`) and git HEAD. I did not assess anything the workers are still writing. I ran no tests, because `server.py` is being edited right now.

### HIGH

**H1. Variation semantics are underspecified**
- **Claim:** "Variations whitelist samples one exclusive value/multi sensible subsets; reject impossible count or distinguish repeats; locks honored reproducible seed" (`backend.txt`).
- **Reality:**
  - "Sensible subsets" has no size bound.
  - `combination_count` has no formula for multi or boolean attributes.
  - There's no RNG spec or ordering, so the seed isn't reproducible across library edits.
  - The gallery `selections` field doesn't say whether it holds the resolved selections for each plan or the job's request.
  - HEAD has `pose` and `scenery` as `multi` (12 values each, from a `git show HEAD:library.json` probe), and the library brief turns them into exclusive "primary" attributes while the backend is being built against the same file.
- **Consequence:** UI and backend can each compute a different `combination_count`. A variations batch with n larger than the distinct combinations either silently repeats (the PLAN FAIL "whitelist ignored") or gets rejected unpredictably. The gallery could tag an image with whitelist values it never received, which breaks the definition of done ("resolved selections verified").
- **Fix:** Put this in BACKEND_API.md:
  - `combination_count` = product over whitelisted attributes of: |W| for exclusive, |W| for boolean (W ⊆ {on,off}), and the sum over k=1..K of C(|W|,k) for multi, with K = 3.
  - `mode=variations` with n > count returns 400.
  - Use `random.Random(seed)` over value IDs in sorted order.
  - Persist each image's resolved `selections` + `seed` + `plan_index`.
- **Verify:** A test with whitelist {exclusive: 3 values, boolean: on/off} and n=7 returns 400. With the same seed, two `/api/preview` calls return identical plans.

**H2. There are no cross-attribute conflict rules**
- **Claim:** "server-authoritative ID/type/conflict validation"; "exclusive and boolean contradictions prevented" (PLAN.md lines 10 and 15).
- **Reality:** The library schema in every brief is only `id,name,type,description,thumbnail` / `id,name,steers,...`. There is no `excludes` or `requires` field, so the server can only enforce one-value-per-attribute.
- **Consequence:** Once the library grows to ≥85 attributes covering hair, location and weather, the variation sampler will produce contradictory prompts across attributes (an indoor studio with rain, a buzz cut with a bun). "Conflict validation" passes its tests while those prompts still get through.
- **Fix:**
  - Add an optional `excludes: ["attr:value"]` on values.
  - The server rejects locked selections that conflict, and the sampler rejection-samples.
  - `combination_count` subtracts excluded pairs.
  - A library test asserts every `excludes` reference resolves.
- **Verify:** A test that locks two mutually excluded values gets 400. Running 1000 seeded variation plans produces zero excluded pairs.

**H3. Crash consistency between files and the DB is undefined; recovery can double-bill; the move can break paths**
- **Claim:** "persisted async partial results … recovery interrupted jobs" (`backend.txt`); "move app to durable ~/projects location … preserve outputs" (PLAN.md line 27).
- **Reality:**
  - The baseline writes the file with no DB row (`server.py:81`).
  - The contract doesn't specify write order, status for each plan, or what recovery does: re-run the provider call or mark it failed.
  - SQLite with `ThreadingHTTPServer` plus 4 provider threads needs a connection per thread and WAL/busy_timeout, and the contract mentions neither.
- **Consequence:**
  - A restart re-queues plans that already succeeded, which means a second paid call.
  - A crash between the file write and the insert leaves orphan files or rows that point at nothing.
  - Absolute paths stored in the DB break after the move to ~/projects.
- **Fix:**
  - Persist a `plans` table with status for each plan.
  - Write order: write to a temp file, run the Pillow check, `os.replace`, then insert the image row and its tags in one transaction, then mark the plan done.
  - Recovery re-queues only plans that are `running`/`queued` and have no image row.
  - Store paths relative to `generated/`.
  - Use WAL + `busy_timeout`.
- **Verify:** Kill the process during a mocked job, restart, and confirm the provider mock's call count equals the remaining plans only. `grep -c "$HOME" runtime/*.db` returns 0.

### MEDIUM

**M1. Gallery AND/OR can return duplicates; offset pagination can drift**
- **Claim:** "AND across attributes OR within values, bounded pagination" (PLAN.md line 15).
- **Reality:** Multi-valued tags mean an image can match 2 values of one attribute. A plain JOIN then returns it twice and inflates `total`. Ordering by `created_at` alone, with 4 concurrent writers, lets rows skip or repeat between pages. `page_size` has no maximum in the contract.
- **Fix:**
  - Use one `EXISTS (SELECT 1 FROM tags WHERE image_id=i.id AND attr=? AND value IN (...))` per attribute.
  - Order by `created_at DESC, id DESC`.
  - Index `tags(attr_id, value_id, image_id)`.
  - Clamp `page_size` to 1..100; reject `page` < 1.
  - A page past the end returns empty `items`.
- **Verify:** Seed an image tagged with 2 values of the same multi attribute, filter on both, and assert `total == 1`.

**M2. Tags have no library version, so they go stale**
- **Reality:** The library brief changes types (pose/scenery from multi to exclusive) and "removes" conflicting locks. Records in the backend brief have no `library_version`. The UI builds its filters from the *current* library.
- **Consequence:** After the next library edit, older images become unfilterable or are tagged with values that have since disappeared.
- **Fix:**
  - Store the sha256 of library.json on each image, and keep name snapshots alongside the tags.
  - The filter API rejects unknown attributes but keeps historical values reachable.
  - Document an ID-rename map.
- **Verify:** A test that removes a value from the library and then queries the gallery still returns the old record in detail view.

**M3. Image verification needs decoded bytes and a ratio tolerance; the baseline test treats fake bytes as success**
- **Reality:**
  - `server.py:54-55` labels every `b64_json` result `image/jpeg`, and the extension follows that label (`server.py:79`).
  - `test_server.py:19-26` asserts that `b'fake-image-bytes'` produces a successful `/generated/*.jpg`.
  - The xAI `1k` output won't match the requested ratio exactly (9:16 is 0.5625, and provider sizes round).
- **Consequence:** If the legacy test or the legacy `/api/generate` path is kept for "compatibility", it is a false green. Exact ratio equality would instead fail real successes or push someone to drop the check.
- **Fix:**
  - Detect the format with `Image.open(...).format` after `load()`, and keep `MAX_IMAGE_PIXELS`.
  - Allow ±2% ratio tolerance and store both `requested_ratio` and the measured `width/height`.
  - Route `/api/generate` through the same verify-and-persist pipeline.
  - Invert the test at `test_server.py:19` to expect failure.
- **Verify:** `grep -n "fake-image-bytes" test_server.py` must appear only in failure-path assertions.

**M4. Gallery thumbnail output path collides with library-owned files**
- **Reality:** `library.txt` gives the library worker `thumbnails/**`. `backend.txt` says "generate smaller gallery thumbs" with no path. `.gitignore` (working tree) ignores `generated/` and `runtime/` but not `thumbnails/`.
- **Consequence:** User images could land in the tracked `thumbnails/` and get published by the planned commit/push (PLAN.md line 27), or trip the library's "every SVG exists" test.
- **Fix:** Pin gallery thumbnails to `generated/thumbs/`, and have the library test assert that `thumbnails/` contains only `*.svg`.
- **Verify:** `git status --porcelain thumbnails | grep -v '\.svg$'` is empty after a mocked job.

### LOW

**L1. Value IDs are unique only within an attribute.** HEAD reuses `on`/`off` across `micro_texture`, `drape_effect` and `high_slit`. The library brief asks for "uniqueness" tests and also "preserve existing IDs". Fix: scope uniqueness to each attribute; tags and thumbnail filenames must key on `attr/value` (for example `thumbnails/<attr>/<value>.svg`).

**L2. Two gaps in lock contradictions and boolean filtering.**
- HEAD `base_locks` hardcodes "woman age 24" and negates "even lighting" and "perfect composition", but the contract has no mechanical check that the new steers don't contradict them. Fix: a test that asserts no value `steers` contains any term from the negative-lock list.
- Separately, an image with a boolean left unselected is not tagged `off`, so filtering on `off` won't return it. The UI should say so.

Note: the HEAD `camera` boolean has only `['on']`. That already fails the PLAN "boolean lacks on/off" criterion, so the library test must catch it.
