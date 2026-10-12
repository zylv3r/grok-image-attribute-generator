## VERDICT

CHANGES-REQUESTED

Round 1, technical/security/imaging QA. Verified clean HEAD `8d56e432a0bbd87fbeca16497a74acf96f6df22f`. The plan correctly identifies the current preset failure and independent-generation previews; its proposed safeguards are **not implemented**. No demonstrated CRITICAL damage or false-completion warrants BLOCK.

Read-only verification: the frontend state-test command passed; in-memory probes confirmed silent storage failure, retired-ID pruning, conditional Origin enforcement, and JPEG changes outside an edited region. No paid calls, writes, credentials/config reads, or live restart occurred. Write-producing browser/database suites were inspected, not executed.

### [HIGH] Legacy presets can lose controls before server import

**Claim:** G1 preserves raw drafts and retired controls.

**Reality:** [App.tsx](/home/renriquez/projects/grok-image-attribute-generator/src/App.tsx:57) immediately transforms stored presets through `cleanDraft`, then its effect writes that transformed list back. [lib.ts](/home/renriquez/projects/grok-image-attribute-generator/src/lib.ts:84) removes unknown controls. An in-memory Node probe using the actual transpiled helper reduced `{age:["24"], ethnic_inspiration:[...], retired_control:[...]}` to `{age:["24"]}` against a catalog with the retired attribute removed. The existing [browser regression](/home/renriquez/projects/grok-image-attribute-generator/src/browser-tests/studio.spec.ts:65) explicitly expects pruning.

**Consequence:** Adding server persistence while retaining this initialization path can import an already damaged copy. Merely leaving localStorage uncleared does not preserve its original contents.

**Fix:** Read legacy records into an immutable raw import envelope **before** normalization or any storage effect. Separate archival data from the applicable draft. Add RED cases for retired controls, unknown fields, empty Vary preferences, denied storage, and malformed records; mounting, failed import, and rejected migration must leave original bytes unchanged. Apply must disclose unresolved controls before dropping them.

### [MEDIUM] Ordinary Save retries lack a specified idempotency contract

**Claim:** Failed saves cannot create duplicates, and errors retain draft/name.

**Reality:** [PLAN.md](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/PLAN.md:36) specifies `{name,draft}` for creation and an import digest, but no retry identity for ordinary Save. A transaction can commit while its response is lost. Retrying that POST can create another UUID. Current [Save handling](/home/renriquez/projects/grok-image-attribute-generator/src/App.tsx:100) also clears the name and announces success unconditionally; the denied-storage probe showed `writeStorage` returning `undefined` without surfacing failure.

**Consequence:** “Network failure” does not prove “nothing saved”; retries can multiply records even with transactional SQLite.

**Fix:** Give each deliberate Save a stable request key retained through retries. Store that key, payload digest, and resulting preset ID atomically; reject reuse with different content. RED acceptance: commit then drop response, retry, restart, and read back exactly one record.

For import conflicts, close the policy explicitly: **A:** preserve differing records with the same legacy UUID as separate records and flag the conflict; **B:** hold conflicting records for resolution. Never overwrite by UUID alone. An identical raw record must converge across origins and concurrent imports.

### [MEDIUM] Preset mutations need an explicit security boundary

**Claim:** Every preset mutation enforces exact Origin/loopback and body guards.

**Reality:** [server.py](/home/renriquez/projects/grok-image-attribute-generator/server.py:663) checks Origin only when `paid=True`; POST dispatch enables it only for existing generation routes. An in-memory probe with loopback Host/client and foreign Origin was **accepted** with `paid=False`, rejected with `paid=True`. Existing [Origin tests](/home/renriquez/projects/grok-image-attribute-generator/test_server.py:407) cover paid routes, not future preset mutations. [Preview guard tests](/home/renriquez/projects/grok-image-attribute-generator/test_photographic_previews.py:224) cover hostile Host headers.

**Consequence:** Reusing the default guard for inexpensive writes silently omits Origin enforcement.

**Fix:** Separate mutation protection from billing, and invoke it for create/import/delete. Extend tests to hostile/null/duplicate Origin, duplicate Host, cross-site metadata, malformed IDs, oversized imports, duplicate JSON keys, and database/source GET/HEAD denial. Assert rejection before database mutation.

Close the originless-client policy: **A:** require Origin for preset mutations; **B:** permit originless loopback automation under a documented rule. Verify the approved phone gateway path without broadening trust to arbitrary forwarded headers.

### [HIGH] Lossless masters cannot use the existing image pipeline unchanged

**Claim:** PNG comparison masters support exact non-target pixel preservation.

**Reality:** [gallery.py](/home/renriquez/projects/grok-image-attribute-generator/gallery.py:47) converts every image to RGB and writes JPEG at quality 94/82. [Generated asset serving](/home/renriquez/projects/grok-image-attribute-generator/server.py:825) permits only registered UUID JPEG filenames. The proposal names `comparisons.py` but does not specify its storage/serving integration.

An in-memory Pillow probe changed only an 8×8 region: outside-region differences were **0** before encoding and **192 pixels** after separately encoding both images at quality 94.

**Consequence:** A valid composition can fail equality after JPEG encoding—or a master-level guarantee can be misleadingly presented as a guarantee about displayed JPEGs.

**Fix:** Add a separate comparison artifact store and exact registry-backed serving route. Retain immutable normalized PNG bases and PNG outputs, with dimensions, pixel hashes, color-space policy, and mask hashes. Verify decoded master pixels before making derivatives. Keep JPEG thumbnails explicitly identified as derivatives; preserve existing gallery assets and allowlists.

### [HIGH] “Drift checked” needs executable, artifact-bound acceptance

**Claim:** Same-base comparisons reject geometry/identity drift.

**Reality:** [P0](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/PLAN.md:53) lists provenance and metrics but leaves thresholds and composition checks unspecified; editing checks apply “where feasible.” The existing [inventory verifier](/home/renriquez/projects/grok-image-attribute-generator/scripts/verify_photographic_previews.py:27) verifies tags, decoding, dimensions, and file uniqueness—not identity or controlled variation—and accurately limits its claim at line 62.

**Consequence:** A wrong mask, expanded mask, unchanged output, or drift inside an overly broad region can pass “outside-mask equality.”

**Fix:** Approve and hash masks before editing. For geometry changes, approve the old/new support region and necessary occlusions beforehand. Composite onto the immutable base; assert exact equality wherever mask alpha is zero. Bind approval to base/mask/output hashes, transform parameters, method version, and review results.

RED fixtures must reject a changed locked landmark, wrong base, chained edit, post-hoc enlarged mask, unchanged target, resized output, and unapproved artifact substitution. Require target-effect checks plus human identity/anatomy review.

Close the consequence policy per category: **A:** strict target-only changes, withholding infeasible values; **B:** enumerated necessary consequences approved before the pilot. A generic exception cannot authorize arbitrary drift.

### [MEDIUM] Category and cost gates are procedural, not yet enforceable

**Claim:** Each confirmed category receives a bounded pilot before expansion or publication.

**Reality:** The existing [worker](/home/renriquez/projects/grok-image-attribute-generator/scripts/generate_photographic_previews.py:202) builds tasks for the whole catalog; its limit selects from a cross-category priority/order. [publish](/home/renriquez/projects/grok-image-attribute-generator/scripts/generate_photographic_previews.py:130) exposes completed tasks immediately. It does require explicit reconciliation when the catalog hash changes, which is a useful safeguard.

The current provider [adapter](/home/renriquez/projects/grok-image-attribute-generator/server.py:287) supports text generation only. Ledger source [1.md](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/sources/1.md:39) documents JSON edits using image-2.0; [2.md](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/sources/2.md:9) documents five references. Neither establishes current quality-model/OAuth compatibility.

**Consequence:** Reusing the old worker can cross category boundaries or publish before review. Documentation alone cannot green-light the installed edit path.

**Fix:** Freeze the legacy worker for v2. Require category/contract hash, approved values, explicit pilot request cap, retry ceiling, and publication approval. Keep paid results staged until acceptance. RED acceptance must show zero submissions for unapproved categories, stale contracts, exhausted budgets, or unknown edit capability. Mock the exact JSON reference request and prohibit text-generation fallback. Treat live capability as **unverified** until an authorized pilot supplies a receipt.

### [MEDIUM] Historical gallery preservation needs catalog-migration tests

**Claim:** Old gallery records remain readable and reusable after taxonomy reconciliation.

**Reality:** [test_gallery.py](/home/renriquez/projects/grok-image-attribute-generator/test_gallery.py:87) usefully verifies database-schema migration preserves old selections. However, [gallery filtering](/home/renriquez/projects/grok-image-attribute-generator/server.py:783) validates against the active catalog; the pure Catalog probe rejected a historical control as `unknown attribute`. [Reuse](/home/renriquez/projects/grok-image-attribute-generator/src/App.tsx:514) silently passes historical selections through `cleanDraft`. [Image details](/home/renriquez/projects/grok-image-attribute-generator/src/components/ImageDetail.tsx:128) use current labels or raw IDs.

The explicit source/test search found no `existingGallery` symbol.

**Consequence:** Rows can survive while historical filtering, readable names, and faithful reuse deteriorate.

**Fix:** Add an existing-gallery fixture covering catalog retirement, renaming, and recipe migration. Preserve row/tag/prompt/file hashes and historical snapshots. Resolve historical filters through archived IDs; show a migration preview before reuse. Verify publication and rollback preserve original records and selections.

### [MEDIUM] Optical simulations need value-level semantic mapping

**Claim:** Fixed-scene optical previews honestly illustrate the target setting.

**Reality:** [library.json](/home/renriquez/projects/grok-image-attribute-generator/library.json:3079) labels focal-length values with edge expansion and background compression. [P0](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/PLAN.md:61) proposes fixed-camera FoV crops and correctly disclaims actual lens/perspective measurement. Those crops do not demonstrate every existing steer.

**Consequence:** A generic “simulated” label still permits thumbnails to imply effects they do not show.

**Fix:** Map every optical value to its demonstrated effect and limitations. Close the focal-length choice: **A:** fixed-position FoV crops, explicitly labeled as such; **B:** hold calibrated perspective demonstrations for a separate approved scene method. Record crop/resampling, blur/depth, motion, exposure compensation, and randomness parameters. RED checks must reject perspective claims from crops, static motion demonstrations, unexplained exposure changes, and unfixed randomness presented as deterministic.