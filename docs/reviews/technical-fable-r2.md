## VERDICT: BLOCK

All 42 tests pass, but one new critical bug gets past them: when a variations request is too large for exact enumeration, most of the attributes the user whitelisted never change. Every r1 HIGH and MEDIUM item is otherwise resolved, or rebutted with the limitation documented.

**How I checked.** I ran the unit suite in the Hermes venv (`python -m unittest test_server test_gallery test_library`: 42 tests, OK). I also called `Catalog.load('library.json').preview(...)` directly in Python. Neither step wrote anything, called the provider or restarted the server. The library has 97 attributes: 93 exclusive, 4 boolean, 0 multi.

### C1 (critical, new): wide whitelists vary only 3–4 attributes
- **Cause:** for whitelists whose combinations exceed 4,096 (`server.py:30`), the server walks attributes in alphabetical order (`server.py:169-177`). It shuffles only the values within each attribute (`server.py:188-190`) and stops after finding 256 valid combinations (`server.py:32`, `server.py:192-208`). Those 256 differ only in the last few attributes, and the 24 plans are sampled from them (`server.py:218`).
- **What the probe showed:**

  | Whitelist | Attributes that varied across 24 plans |
  |---|---|
  | 7 attributes × 4 values (16,384 combinations) | 4 of 7 |
  | 12 attributes × 4 values | 4 of 12 |
  | Full library | 3 of 97 |

  In the 7×4 case, `age=age_35`, `aperture=f_1_4` and `background_prop=no_background_prop` were the same in all 24 plans.
- **Why it's a false green:**
  - PLAN.md:15 lists "whitelist … ignored" as a FAIL condition.
  - The only test of this path (`test_server.py:117-126`) checks that there are 24 distinct plans, not that the whitelisted attributes vary.
  - `BACKEND_API.md:43` says sampling is "not … uniformly sampled", but it never says most whitelisted attributes stay fixed.
  - The real two-variation run used a small whitelist that took the exact path, so it never exercised this code.
  - The user pays for up to 24 near-identical images.
- **Fix:** replace the depth-first search with seeded rejection sampling. Draw each whitelisted attribute's value independently, reject combinations that conflict, and drop duplicates. Cap the attempts and keep the existing 400 when fewer than `n` plans are found.
- **Test to add:** whitelist 7 attributes × 4 values, seed 3, n=24. Assert every whitelisted attribute takes at least 2 values, no plan conflicts, and the same seed gives identical plans.

### r1 items
| r1 | Status | Evidence |
|---|---|---|
| H1 variation semantics | Partial (reopened as C1) | Asking for more variations than exist returns 400 on the small-whitelist path (probe). The same seed gives identical plans (probe). Resolved selections and snapshots are persisted (`server.py:222-228`). Multi subsets capped at pairs (documented as K=2), which doesn't matter while the library has 0 multi attributes. |
| H2 conflicts | Resolved within documented scope | `excludes` references are checked when the library loads (`server.py:62-71`), and the hair rules are wired in (`server.py:73-81`). No conflicting plans in the full-library probe. The limit is named at `BACKEND_API.md:48`. |
| H3 crash consistency | Resolved; your rebuttal of my requeue fix accepted | Image files are written atomically (`gallery.py:65-75`). The image row, tags, search index and plan status commit in one transaction (`gallery.py:236-249`). `recover()` marks interrupted plans failed and never retries the paid call (`gallery.py:169-177`). WAL and busy timeout are set (`gallery.py:96,143`). One acceptable remaining limitation: a crash between writing files and committing leaves orphan files, which are never served (`gallery.py:285-288`). |
| M1 gallery | Resolved | Filters can't return duplicates (`gallery.py:305-309`). Ordering is stable (`gallery.py:314`). Page and page size are clamped (`gallery.py:291-294`). The count and the page come from one transaction (`gallery.py:311-315`). |
| M2 library version | Resolved | Each image stores the hash of the raw library file (`server.py:88`) plus requested and resolved snapshots. Gallery filters use only the current library, which is documented (`BACKEND_API.md:76`). |
| M3 image verification | Resolved | Real decoding, byte and pixel caps, and a 2% aspect-ratio tolerance (`gallery.py:33-58`). The legacy path uses the same check (`server.py:309`). `fake-image-bytes` now appears only in tests that expect failure (`test_server.py:214-216`, `test_gallery.py:127`). |
| M4 thumbnail paths | Resolved | Gallery thumbnails go to `generated/` (`gallery.py:62`). `thumbnails/` holds 990 `.svg` files and nothing else. `.gitignore` covers the database and its WAL files. |
| L1 scoped IDs | Resolved | `server.py:49` |

The synthetic 10k gallery benchmark and the real UI generations are kept separate: the benchmark is labelled as not generation evidence (`acceptance/gallery_benchmark.py:2`, `README.md:61`). I didn't re-run the real generations because that would mean paid provider calls.

**To reach PASS:** fix C1, add the 7×4 test and re-run the suite. Nothing else is needed for this council.

The full report is in `/home/renriquez/.claude/plans/technical-council-fable-round2-luminous-snowflake.md`. Plan mode limited me to that file, so `image-app-work/technical-fable-r2.md` is still empty.
