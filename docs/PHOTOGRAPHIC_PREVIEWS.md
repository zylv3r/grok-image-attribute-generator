# Generated photographic library previews

The operator approved generating all **893** value photographs in resumable batches. **97 attribute contact sheets** are derived locally from those photographs, not charged as extra provider generations. Runtime photos and manifests are private local data and excluded from Git.

## What is real, what is not

Every ready photographic value thumbnail comes from an actual completed native xAI image-generation job submitted through the application's existing `/api/jobs` endpoint. It retains the selected attribute/value tags and full prompt in the gallery. The worker independently verifies original and thumbnail JPEG bytes, measured square dimensions, local file boundaries and resolved selections before publishing a ready record.

Examples use photographic framing suited to their attribute: hair portraits, face/skin close-ups, fabric details, full-body poses, environmental scenery, and lighting/composition studies. Within each attribute the baseline prompt is fixed and the chosen library steer changes. These are independently generated aesthetic examples; identity and incidental details can vary. They are **not** claimed to be matched-person A/B experiments, real-world documentary photographs, or guarantees of perfect literal provider compliance.

The first six actual photographs were independently inspected: golden blonde/platinum, cotton poplin/satin, and hard/soft light. The distinguishing aesthetics were visible. The full batch then started; do not interpret this initial validation or source commit as proof that all 893 images are already complete. Live status is authoritative.

## Run and resume

Requires the app running on localhost:8123 with working Hermes xAI OAuth and sufficient provider quota. This makes real paid/quota-consuming requests:

```bash
"$HOME/.hermes/hermes-agent/venv/bin/python" scripts/generate_photographic_previews.py --workers 3
```

The default root is the script's repository, not a hardcoded temporary checkout. An optional `--base http://127.0.0.1:8123` selects the local origin. `--limit 6` executes a bounded tranche; `--limit 0` validates/re-publishes existing results without generating another photo.

- One controller at a time is enforced with `flock`.
- Initial priorities establish representative hair, textile and lighting examples; remaining work progresses across attributes before exhausting long pose/scenery lists.
- Three worker threads submit single-image jobs. All calls use the app's global four-provider-slot semaphore and 24-unfinished-image queue; this is not an independent unbounded vendor client.
- Queue admission 429 responses can wait/retry because they were rejected before generation. Successful records are verified and skipped on resume.
- Known job IDs are reconciled and polled without re-submitting their paid request, even after a polling transport failure.
- An interrupted submission without a known ID is marked ambiguous, not blindly repeated. Provider failures remain recorded and require deliberate investigation/retry; the controller pauses after persistent failures rather than hammering the remaining catalog.
- Library byte hash and exact task inventory must match on resume. The library is not modified while generating.

## State and serving

`generated/photographic-previews.json` is an atomic checkpoint containing all 893 task states, known job IDs, verified result IDs, URL mappings, progress and manifest version. Original photographs and smaller thumbnails are existing gallery files. Derived sheets live at `generated/preview-atlases/<attribute>.jpg` and use adaptive one/two/four-photo layouts.

`GET /api/library` reads the live registry on a copy of the catalog. Known IDs, registered gallery images, exact URL shapes, matching image tags, original/thumbnail JPEG data and contact-sheet JPEG boundaries are validated. In photographic mode, missing/invalid values receive an explicit pending state and no diagram URL in their default thumbnail.

`GET /api/thumbnail-status` returns:

```json
{"mode":"photographic","total":893,"value_completed":6,"attribute_completed":3,"failed":0,"status":"running","version":11}
```

The numbers above are an illustrative schema example, not a current completion claim. Success and total counts are derived from validated local data rather than trusting declared manifest totals. Contact sheets can be ready from representative values before an attribute's entire value set is complete. Global completion requires all catalog values and all attribute sheets.

Contact sheets are served through an explicit known-attribute JPEG allowlist for GET/HEAD; path traversal, symlinks, unregistered paths and malformed/non-JPEG content are rejected. Versioned atlas URLs ensure progressive sheet changes actually refresh in an already-open browser.

The frontend polls status every ten seconds while running and replaces only the library on a version change. Draft selections, allowed pools, category, query, settings and presets are preserved. Terminal/paused states use slower polling; a nonfatal inline reload control is available. Source SVGs remain an explicitly illustrative legacy mode when no photographic registry is present.

## Acceptance

- Existing library/planner/gallery/HTTP tests remain intact.
- Photographic backend tests cover readiness and truthful progress, live rereads, correct tags, corrupt/missing files, bounded JPEG verification, malformed registries, traversal/symlinks, complete-catalog requirements and contact-sheet cache invalidation.
- Worker fixture tests explicitly make no provider calls and cover inventory, actual fixture image decoding, URL/tag/dimension checks, checkpoint skips, known-job reconciliation and ambiguous submission handling.
- Simulated browser tests cover ready JPEG framing, actual image decoding, pending entries with no diagram/letter fallback, non-nested original-image links, progress refresh without selection loss, activation detection, recovery and slow terminal polling.
- Production proof uses actual generated records plus the live authenticated phone/browser path; it is distinct from these mocked-provider fixtures.

Inspect live status and the manifest before declaring the complete batch delivered. A completion notification or a generated source file is not itself proof of 893 verified photographs.
