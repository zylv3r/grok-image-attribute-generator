# Immediate G1/G2 controls

Presets now use one installation-wide `presets.sqlite3` collection, labeled **Saved on this studio**. The database is ignored by git and is outside the server's asset allowlist. Keep it across source rollbacks and restarts.

- `GET /api/presets` returns `{presets:[{id,name,draft,schema_version,catalog_hash,created_at,updated_at}]}`.
- `POST /api/presets` accepts `{name,draft,request_key}`; returns the preset with 201 for creation or 200 for a replay. Same key/different data returns 409; replay after deletion returns 410.
- `DELETE /api/presets/<id>` accepts an empty JSON object and returns `{presets:[...]}`. Delete is repeatable; save/import ledgers remain as tombstones.
- `POST /api/presets/import` accepts `{presets:[raw legacy records],raw_text?:string}` and returns `{presets:[...],warnings:[...]}`.

All mutations require exactly one non-null Origin equal to `http://` plus the validated loopback Host, a loopback client, and the existing bounded JSON/body protections. Duplicate Origin/Host/Content-Type/Content-Length headers and JSON keys are rejected. Forwarded headers grant no trust. An authenticated phone gateway must rewrite Host and Origin to the loopback backend; parent verifies the existing gateway during integration.

Save validation accepts unfinished pools and bounded unknown/retired fields; it never calls generation validation. Drafts are limited to 64 KiB, import envelopes to 180,000 bytes, nesting to 16 levels, with forbidden prototype keys rejected. Server UUIDs identify records. Browser retry keys survive failed writes, have a fallback when `crypto.randomUUID` is unavailable, and are committed with the payload digest and preset ID in one transaction.

App captures raw legacy storage before draft cleaning. Presets never rewrites or clears `atelier.presets.v1`; failed imports retain that original and the last confirmed server list. Import stores the raw text and complete structural envelope in the SQLite `archives` table, including malformed text/records with recovery warnings. Canonical per-record digests converge repeated and concurrent imports regardless of object key order. A legacy ID with changed data creates a separate preserved record. Canonical serialization preserves structural fields; the separate raw text preserves original formatting.

Apply cleans only a derived draft. Unresolved fields/IDs or unsupported schema versions are listed and require **Apply known controls**. Supported complete records apply directly. Neither path rewrites the archive. Background preview/library refresh does not reload presets or change the draft.

Vary **All N values / None / Inverse across N** acts on the whole attribute catalog, including hidden and searched-out values. The UI reports **K allowed · M shown; actions affect all N**. Inverse follows catalog order; None retains Vary, never substitutes boolean Off, and other locks stay unchanged.

## Validation and parent handoff

RED ran before implementation: all five new HTTP preset tests failed with absent routes (404); nine original state tests passed and three new G1/G2 tests failed on missing helpers. An additional empty-string legacy case failed before its preservation fix. Actual GREEN output is retained in `GLOBAL_CONTROLS_TEST_OUTPUT.txt`.

```sh
/home/renriquez/.hermes/hermes-agent/venv/bin/python -m unittest test_presets test_server test_gallery -v
node src/browser-tests/selection-state.test.mjs
npm run build
npm run test:browser -- presets-persistence.spec.ts vary-bulk.spec.ts studio.spec.ts photographic.spec.ts
```

Python: 39 passed, using real HTTP-handler/parser transport through `test_server.MemorySocket`, temporary SQLite databases, restart/retry/concurrency checks and mock providers. Node: 12 passed. Build and separate typecheck of the new browser suites passed; Playwright discovery finds 25 tests total. The sandbox's `node --test` subprocess wrapper failed, so the Node test file ran directly, preserving its TAP assertions.

Browser execution and live gateway/restart verification remain with parent as requested; no browser pass is claimed here. New browser suites use the compiled UI, two independent contexts on distinct fixture origins, a shared installation fixture, denied storage/crypto, failed writes and lost commit responses, raw import preservation, explicit Apply, and whole-catalog bulk controls. Existing behavior assertions are unchanged; their fixture gained only preset API mocks. No paid calls, live-source edits, catalog/generated-data edits, restart, push or commit occurred.
