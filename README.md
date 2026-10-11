# Atelier — Attribute Image Studio

A local, server-backed visual composition studio for adult, nonexplicit fashion/editorial image generation. The browser never receives image-provider credentials.

## What it does

- Data-driven **categories → attributes → values** with local thumbnail steering guides and prompt descriptions.
- Explicit **exclusive**, **on/off**, and additive **multi-select** semantics. Unset is different from off.
- Lock selections for every image, repeat one direction, or whitelist allowed values to generate distinct variation plans. Only whitelisted attributes vary.
- Server-built prompts, optional reproducible **selection-sampling** seed, seven aspect-ratio choices, bounded asynchronous jobs and per-image error reporting.
- Persistent SQLite gallery with FTS prompt search, indexed attribute/value filters, thumbnail cards, bounded pagination, original downloads, metadata details and selection reuse.
- React, Radix UI accessibility primitives and Lucide icons; responsive category navigation, saved local presets, keyboard controls and explicit error/empty states.

**Photographic previews:** the hosted library now progressively displays actual provider-generated photographic examples for each value, and locally derived photographic contact sheets for attributes. Pending photographs are explicitly labeled; diagrams are not used as substitutes in photographic mode. The source SVG guides remain a legacy mode for deployments without a photographic manifest. Within an attribute, prompt framing stays consistent and the selected steer changes; independent generations may still change identity and other details, so these are aesthetic examples—not matched-person causal comparisons. Sampling seeds do not guarantee reproducible pixels.

The approved full catalog batch is resumable and updates the interface while it runs. See [photographic preview generation](docs/PHOTOGRAPHIC_PREVIEWS.md).

## Requirements and startup

Use the existing Hermes Python environment with Pillow and requests, plus Node/npm for the UI build:

```bash
npm ci
npm run build
"$HOME/.hermes/hermes-agent/venv/bin/python" server.py
```

Open **http://localhost:8123**. The server deliberately binds to loopback; it is not a multi-user/LAN deployment. Source files, Git internals and databases are not public routes.

Hermes must already be authenticated for xAI OAuth image generation. Credentials are resolved exclusively on the server. Consult the Hermes documentation for authentication/configuration; do not paste secrets into this app.

Environment:
- `PORT` (default `8123`), `HOST` (default `127.0.0.1`, loopback only).
- `HERMES_SOURCE` if the Hermes source checkout is in a nondefault location.
- `IMPORT_LEGACY_IMAGES=1` opts into importing existing verified image files without inventing prompts or attribute tags. Legacy untagged images appear in the gallery but do not match attribute filters.

Gallery files and SQLite state are local runtime data, excluded from Git. Keep the app in a durable directory, not a cleanup-prone temporary/scratch location. Back up the database and generated files together while stopped.

## Selection model

- **Lock:** select at most one value for an exclusive/boolean attribute; additive multi attributes can contain several.
- **Vary:** checked values form the allowed pool. Other attributes stay locked.
- **Single:** one locked composition.
- **Repeat:** multiple images from identical resolved selections (provider imagery may differ).
- **Variations:** distinct valid attribute combinations; impossible requested counts are rejected before any provider call.
- Cross-attribute compatibility checks cover explicit catalog exclusions and recognized hair-length/style/fringe contradictions; this is not a universal semantic consistency solver.
- Gallery filters are **OR within an attribute**, **AND across attributes**. A boolean left unset is not equivalent to explicitly off.

Interrupted jobs retain completed results and mark unfinished plans failed. They are not automatically re-submitted to the paid provider. A failed job can still have partial successful images; inspect the per-image report before retrying.

API details and variation-count semantics: [BACKEND_API.md](BACKEND_API.md).

## Verification

```bash
"$HOME/.hermes/hermes-agent/venv/bin/python" -m unittest discover -v
npm run build
npx playwright install chromium
npm run test:browser
"$HOME/.hermes/hermes-agent/venv/bin/python" acceptance/gallery_benchmark.py
```

The Python unit suite uses a mocked provider with actual decodable fixture images. The UI suite explicitly uses simulated APIs. The benchmark seeds isolated **synthetic metadata**, not generated images. None of those constitutes paid-generation proof.

Opt-in actual headless-browser generation with **no mocks/interception**:

```bash
# One paid image, selected through the UI:
RUN_PAID_GENERATION=1 STUDIO_BASE_URL=http://localhost:8123 npm run test:actual
# Two paid whitelist variations + locked values + pixel dimensions + real gallery filters:
RUN_PAID_GENERATION=1 STUDIO_BASE_URL=http://localhost:8123 node acceptance/real_variations.mjs
```

These scripts make real provider requests and may incur charges. Evidence is saved locally, not committed. Actual output dimensions are validated independently of claimed MIME type/provider success.

## Extending the library

Preserve stable category/attribute/value IDs. Add meaningful names, descriptions and `steers`, choose accurate selection semantics, and give every attribute/value a safe local thumbnail. Run the library checks and planner checks after any change. Generated result metadata stores resolved selections rather than the entire allowed whitelist. Historic IDs/names should not be silently repurposed.
