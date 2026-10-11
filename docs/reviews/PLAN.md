# Attribute Studio build contract

Existing source: /home/renriquez/.local/share/hermes-owner/home/cache/scratch/grok-image-attribute-generator. Live loopback app localhost:8123 remains unchanged until integration. No cluster writes, model/provider config changes or credential access. Workers are Codex authenticated CLI, disjoint paths in initially clean checkout; not fleet panes. No merge/commit during integration.

## Definition of done
A user can choose category -> attribute -> values using thumbnail guides, produce one actual provider image and a whitelist-controlled variation batch through headless browser, then search/filter the persistent gallery by any library attribute with bounded pagination. Valid image files, actual dimensions, resolved selections and provider status are verified. Technical and UX/design council findings are resolved or explicitly disclosed. App hosted persistently on loopback and delivered with evidence. Illustrative diagrams are labeled, not claimed to be generated sample images. No credential is served and provider faults cannot become fabricated successes.

## Slice 1 Library and previews
Owner: Codex/library; estimate 15-25 minutes. Files library.json thumbnails scripts/build_thumbnails.py test_library.py.
PASS: >=18 categories >=85 substantive attributes >=750 values, >=80 scenery values and >=60 poses; every attribute/value has meaningful steer/description and safe valid local illustration; exclusive and boolean contradictions prevented. FAIL: missing/broken thumbnail, text-only placeholder diagrams, invalid IDs, boolean lacks on/off, fixed global locks contradict supported selections.
Rollback: original library from git HEAD, retaining generated outputs.

## Slice 2 Generation and gallery
Owner Codex/backend; estimate 20-35 minutes. Files server.py gallery.py tests BACKEND_API.md.
PASS: server-authoritative ID/type/conflict validation; locked attributes preserved; sampled whitelisted values only; bounded global 4-provider concurrency; persisted async partial results; indexed attribute gallery with AND across attributes OR within values, bounded pagination; verified decoded image dimensions; no secrets/source/db served or cross-origin paid requests. FAIL: false successes, silent ratio fallback, arbitrary files exposed, gallery loads all images, whitelist treated as multi conflicting values or ignored.
Rollback: old server/library from HEAD and stop new service, keep output/db.

## Slice 3 UI
Owner Codex/frontend; estimate 20-35 minutes. Files src package/config/index/tests only.
PASS: React/Radix accessible desktop/mobile app, category nav, semantic exclusivity/boolean/multi controls, all thumbnail guides available, locks/whitelist distinction, generation progress/errors, presets, every library attr gallery filter, detail/reuse/download and real pagination. Build + simulated UI tests + actual generation through headless browser all pass. FAIL: nonfunctional CDN stubs, inaccessible controls, overflow, invalid persistence, fake actual generation evidence.
Rollback: previous index.html, remove dist routing, retain runtime outputs.

## Integration and councils
Two technical seats: adversarial security/reliability and architectural/data correctness. Two design seats: interaction/accessibility and visual/information architecture. Each must inspect real files and cite command/path, record severity, consequence, fix, verification. Two rounds maximum then operator disposition for residual criticals. First assess contract/baseline while implementation runs, then assess integrated implementation/screenshots. Technical review cannot claim future code is already present. Actual image generation bounded to 3-5 images for acceptance, no costly automatic hundreds-of-preview generation.

## Persistence and delivery
After tests, move app to durable ~/projects location to avoid scratch TTL, preserve outputs; loopback systemd user service or durable process; probe exact origin HTML/assets/API and actual gallery records. No push required by current request; prior user requested source publishing so commit/push may be done after real verification if auth remains correct. Do not force-push or alter unrelated changes.
