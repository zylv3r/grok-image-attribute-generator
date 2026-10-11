# Final acceptance and council disposition

## Delivered application

- Durable source/runtime directory: `/home/renriquez/projects/grok-image-attribute-generator`.
- Loopback URL: `http://localhost:8123`.
- Persistent user service: `atelier-image-studio.service`, enabled; health endpoint and compiled HTML verified after relocation. This is a local single-user app, not a hardened Internet-facing multi-user service.
- Catalog: **22 categories, 97 attributes, 893 values**, including **70 poses and 95 scenery choices**.
- **990 SVG steering guides**: every attribute and value has a local illustration. All referenced assets returned 200 and decoded in the real headless browser. These are labeled illustrative diagrams, not generated before/after samples.
- React/Radix/Lucide interface; global search, accordions, 12-value expansion, category/attribute navigation, locks and allowed variations, presets, async progress, undoable reuse, responsive gallery/filter/detail views.
- Persistent SQLite/FTS gallery: every catalog attribute is filterable, OR within values and AND across attributes; 24 thumbnail cards/page, bounded server pagination.

## Parent-run final verification

All checks below were run from the durable delivered directory after the final amendments:

- Production TypeScript/Vite build: **PASS**.
- Python library/planner/provider-boundary/gallery/HTTP/amendment suite: **47 tests PASS**.
- Playwright simulated-API UI suite: **16 tests PASS**, including unchanged synchronous radio ArrowRight expectations, presets, long-library reachability, gallery filters/pagination, focus/reuse and full axe checks in studio/gallery/filter dialogs.
- Frontend selection/state suite: **9 tests PASS**.
- Read-only real live UI audit: **15 views at 1440/390/360px**, zero tested WCAG violations, no horizontal overflow and no page errors; **990/990 thumbnails fetched and decoded**. Unlike the earlier audit, this was rerun against the final build.
- Isolated synthetic **10,000-record** gallery benchmark: correct OR/AND/dedup/FTS totals, 24 returned cards maximum, distinct ordered pages and empty past-end page. Observed final query latencies 1.12–28.99 ms. This benchmark is metadata performance evidence, **not generated-image evidence**.
- Actual provider acceptance: a single image plus a two-image whitelist batch were generated through the rendered headless UI. After relocation/amendments, another real two-image batch succeeded through the final localhost:8123 app. All completed acceptance images were verified at **720×1280** for requested 9:16; real gallery AND/OR filters returned their actual records.
- Final paid job read back exactly: `39ac67d4eeab4c01838e4efbf5a85c3c`, two successful images, zero failures. Images `228138b96877470e93a3d03b93dd2621` and `b8238f4217ff4e27a4ad4985668eb23c`. Sampling seed, library hash and resolved label snapshots verified independently.
- Live read-only full-whitelist preview: **all 97 attributes varied across 24 distinct plans**, with identical plans on repeated seed 2 requests. No provider calls were made for this preview test.

Runtime evidence lives under ignored `acceptance-output/` and `generated/`; it is deliberately not published with source. Earlier single-image evidence also resides under the scratch `atelier-actual-generation/` directory. Generated jobs/images persist in the gallery database.

## Council review, not a rubber stamp

Eight raw reports (two technical seats and two design seats, two rounds each) are preserved in `docs/reviews/`. The raw visual round-two report has an inconsistent `## VERDICT BLOCK` heading followed by an explicit PASS/no-critical body; disposition follows its actual findings, and this formatting anomaly is not hidden.

Round two technical Fable found a real blocking large-whitelist bug: truncated depth-first search froze early attributes. The operator explicitly chose a targeted amendment, not a waiver or another review loop. Parent wrote regression tests first, observed them FAIL on the old code, then replaced wide-product sampling with independent seeded rejection sampling. The seven-attribute/four-value and full-catalog tests now prove diversity, compatibility and reproducibility. The live preview proves all 97 catalog attributes vary. Constrained huge products expose a bounded compatible-count lower bound; unconstrained products can report the exact arithmetic product.

Technical Astra found two remaining request/asset boundary gaps. Empty or duplicate Transfer-Encoding headers now reject before any provider call. SVG serving enforces byte/element limits and inert shapes, rejects scripts, event handlers, external references, CSS URLs and entities for both GET and HEAD, and supplies restrictive SVG CSP. Five amendment tests fail against the old implementation and pass against the patched implementation; the complete suite remains green.

Both design seats found no new critical interaction/visual issues. Their freshness condition is satisfied by rerunning the final live audit and complete browser suite. Additional parent fixes restored focus after gallery reuse, corrected search-count ARIA, made icons decorative to assistive technology, established a single top-level main landmark, prevented guide-text cropping and added a mobile composition shortcut.

## Explicit limitations

- Provider steering is probabilistic; anatomy, identity and literal prompt compliance are not guaranteed. Sampling seeds control plan selection, **not provider pixel determinism**.
- Compatibility rules cover explicit catalog exclusions and named hair-length/style/fringe pairs, not a universal ontology or arbitrary extra-prompt contradictions.
- Multi whitelist subsets are limited to singleton/pair options. The current curated catalog mainly uses exclusive choices plus four on/off controls; orthogonal attributes compose together.
- Huge constrained combination counts are bounded lower estimates; failed sampling is rejected before billing. A small random batch need not contain every permitted value.
- Offset pages may shift when new images are added. Historic detail snapshots remain accessible; filter pickers use current catalog IDs, so IDs should not be silently removed or repurposed.
- Interrupted jobs retain completed results but never automatically re-submit potentially billed work. A hard crash between file publication and SQLite commit can leave unregistered files, which are not served.
- Noncritical UX follow-ups remain: stale-preset pruning notices, undo for preset/reset, richer spoken card descriptions, mobile drawer focus trapping and softer empty-count editing. Retry-failed-only is deliberately manual to avoid hidden charges. These are not waived generation/security failures.
