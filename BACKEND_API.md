# Backend API

`server.py` serves the compiled UI at `dist/index.html`, build assets at `/assets/`, library-referenced thumbnail files at `/thumbnails/`, and verified gallery images at `/generated/`. Build the frontend before starting the backend. Missing builds return 404. Python 3.10+, Pillow, SQLite with FTS5, and the existing Hermes environment are required. The native `generate_native_image(prompt, aspect_ratio)` OAuth integration remains intact; browser requests never supply provider credentials.

Start when ready (this implementation does not restart the existing server):

```bash
"$HOME/.hermes/hermes-agent/venv/bin/python" server.py
```

`HOST` defaults to `127.0.0.1` and must be loopback; `PORT` defaults to `8123`. Persistence lives in `gallery.sqlite3` (including SQLite WAL files) and `generated/`. Run one backend process per database. Startup marks unfinished plans from an interrupted process as failed, retains successful images, and derives `partial` or `failed` status. It never automatically retries an interrupted paid request. A provider may already have billed an interrupted request even without a committed image; requeueing that plan risks double billing. Submit a new job to retry deliberately.

`GET /api/health` returns `status="ok"`, `job_counts` for queued/running/completed/partial/failed jobs, `pending_images`, `image_count`, `pending_limit=24`, and `provider_concurrency_limit=4`. Counts come from a consistent SQLite snapshot. The endpoint does not invoke the provider or inspect credentials/configuration and returns no prompts, error details, paths, credentials, or provider diagnostics. It indicates local database availability, not provider authentication or readiness.

## Library

`GET /api/library` returns `library.json`, preserving `categories`, `base_locks`, and `always_on`. Categories contain `id`, `name`, and `attributes`. Attributes contain `id`, `name`, `type` (`exclusive`, `boolean`, or `multi`), `description`, `thumbnail_url`, and `values`. Values contain `id`, `name`, `steers`, `description`, and `thumbnail_url`. Missing descriptions and thumbnail URLs are normalized to strings (a missing value description falls back to `steers`). Empty thumbnail URLs mean no supplied image. Boolean values use the library's string IDs, typically `on`/`off`; JSON booleans are not value IDs. Every library attribute supports planning and gallery filtering.

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
- `whitelist` is available in variations mode and contains nonempty arrays of allowed IDs. An attribute cannot appear in both maps, even with an empty selection array. Unspecified attributes are omitted, rather than randomized.
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

Every preview plan and generated image record includes `library_hash` (SHA-256 of the loaded library.json bytes), zero-based `plan_index`, and `selection_sampling_seed`. `selections` always contains the resolved IDs, never the job's whitelist. `requested_selection_snapshot` contains separate `selections` and `whitelist` maps; `resolved_selection_snapshot` contains each plan's final map. Snapshot maps preserve attribute names/types and value IDs/names/steers as they were at submission, so image details remain meaningful after library edits. Each map entry is `{"name":"Attribute name","type":"exclusive","values":[{"id":"value_id","name":"Value name","steers":"prompt text"}]}`.

Startup safely adds nullable provenance columns to existing `plans` and `images` tables. All inserts name their columns explicitly. Existing rows retain their IDs, selections, files and indexes, and unknown historical provenance stays null rather than using today's library. Their existing ordinal is exposed as `plan_index`. Compatibility-generated images have the current library hash, empty selection snapshots, a per-plan index, and a null sampling seed; optional legacy imports have unknown provenance. Detail lookup does not revalidate historical IDs against today's library. Gallery filters continue to validate current library IDs.

The queue allows at most **24 unfinished images** across asynchronous and legacy requests; each job has at most 24 images. Excess submissions respond 429 before invoking the provider. A shared semaphore allows at most **four active native provider calls** across all jobs and the compatibility endpoint within the process. Failed calls release capacity and do not discard successful results.

## Image validation and gallery

An image only succeeds after strict base64 decoding, Pillow verification, full pixel decoding, EXIF orientation normalization, dimension checks, and aspect-ratio validation. Limits are 32 MiB decoded input and 40 million pixels. Ratio checks allow integer pixel rounding and up to 2% drift. Provider MIME claims do not determine success or filenames. Stored full images are verified JPEGs and thumbnails fit within 320×320 pixels. Invalid images have no gallery record or served URL.

Full images and thumbnails are encoded to temporary files inside `generated/`, flushed/fsynced, and individually published using `os.replace`. Both are ready before the image, tags, and completed plan commit in one SQLite transaction. Caught write/DB failures remove temporary files and newly published images/thumbs. The pair of renames and SQLite commit cannot be atomic together: a hard crash before the DB commit may leave unregistered files, which are never served. Recovery marks interrupted plans failed and never calls the provider again. Paths in SQLite remain relative to `generated/`; gallery thumbnails never touch library-owned `thumbnails/`. SQLite uses WAL, per-operation connections, busy timeouts, and indexes for tags, dates, ratios, jobs, assets, and plan status.

`GET /api/gallery?q=&page=1&page_size=24&filters=<URL-encoded JSON>&aspect_ratio=` responds:

```json
{"items":[],"total":0,"page":1,"page_size":24,"pages":0}
```

Items contain `id`, `url`, `thumbnail_url`, `prompt`, `selections`, `width`, `height`, `created_at`, and `aspect_ratio`. `GET /api/images/<id>` returns one such record or 404.

Filters are attribute IDs mapped to value ID arrays, e.g. `{"eye_color":["icy_blue","gray_blue"],"micro_texture":["on"]}`. Values use **OR within an attribute and AND across attributes**. All attributes and value IDs are checked against the library, including boolean and multi fields. An empty filter array has no effect. Prompt search uses the SQLite FTS5 index, treating whitespace-separated terms literally and requiring all terms; query syntax is not executed. Aspect ratio uses exact stored ratio matching. Results sort newest first, with stable ID tie breaking. Tag and ratio indexes, SQL counts, and LIMIT/OFFSET pagination avoid loading the gallery into Python. Page is 1..10,000, page size is 1..100 (default 24), and search text is at most 500 characters. Pages beyond the result set return an empty items array with accurate totals.

Legacy import is optional: set `IMPORT_LEGACY_IMAGES=1` on a future startup. It imports valid local PNG/JPEG/WebP files once, produces verified copies and thumbnails, skips symlinks/invalid files, and leaves unknown prompts/selections empty. It does not invent tags. Original files remain on disk; only database-registered copies are served.

## Compatibility and request security

`POST /api/generate` still accepts `{"prompt":"text","n":1,"aspect_ratio":"9:16"}` with `n=1..4` and responds 200 with `{"data":[{"url":"/generated/...jpg", ...}]}`. Image records now include gallery metadata with empty selections. Partial batches return their valid images plus an `errors` array; all-failed batches return 502. This endpoint shares queue/concurrency limits and pixel validation with jobs.

All requests require a loopback client and loopback `Host` with the backend's port. Paid POST routes (`/api/jobs`, `/api/generate`) reject mismatching/multiple Origin headers and cross-site fetches. Same-origin browser requests and local CLI requests without Origin are accepted. No permissive CORS headers are emitted. POSTs require `application/json`, a valid single `Content-Length`, and at most 200,000 body bytes. Transfer encoding, duplicate JSON keys, nonfinite JSON constants, malformed JSON, and non-object bodies are rejected. Provider exception details and credentials never enter API errors or request logs.

JSON errors have the shape `{"error":"message"}`. Common statuses: 400 invalid input, 403 Host/Origin/client rejection, 404 missing record/asset, 408 body timeout, 411 missing length, 413 oversized body, 415 unsupported media type, 429 full queue, 502 sanitized provider failure. GET and HEAD use the same explicit asset rules: compiled HTML, allowed compiled asset extensions, exact library-referenced thumbnail paths with image extensions, and database-registered generated images. Source files, dotfiles, databases, directory listings, traversal, and escaping symlinks are inaccessible.

## Verification

```bash
"$HOME/.hermes/hermes-agent/venv/bin/python" -m unittest test_server test_gallery test_library -v
```

Tests use temporary directories under `TMPDIR`, real Pillow-encoded image bytes, mocked providers, SQLite reopen/recovery and old-schema migration, provenance round trips, atomic replacement/DB failure cleanup, 100 seeded conflict-safe planning runs, every actual library attribute/value, gallery queries, legacy partial failures, queue saturation, and concurrency across multiple managers and compatibility calls. The native URL regression executes `generate_native_image` with mocked requests, Hermes credentials resolver, config loader, and user agent; its output must pass the same pixel verifier, and corrupt URL bytes fail. HTTP tests feed raw requests through the real `BaseHTTPRequestHandler` parser using an in-memory transport because the execution sandbox prohibits opening sockets. They cover preview → job → image/gallery flows, health counts, specific hair-conflict errors, JSON errors, Host/Origin checks, body caps, GET/HEAD assets, and sanitized errors. No test reads OAuth credentials, makes a paid request, or contacts/restarts the live server. A real socket/browser smoke test remains for an environment permitting sockets.
