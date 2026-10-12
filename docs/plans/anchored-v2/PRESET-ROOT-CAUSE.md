# Preset persistence root-cause evidence

## Ranked hypotheses

1. Browser-origin/context isolation: implementation persists only localStorage, so a fresh browser/device/origin cannot retrieve the same preset. Confirmed by live reproduction, not by inspecting the user's phone.
2. Storage denied or full: writeStorage silently swallows the failure while Save always announces success. Confirmed with a deliberately denied write in an isolated real browser.
3. Presets reinitializing during library refresh: not yet reproduced; source mounts don't establish this is happening.
4. crypto.randomUUID unavailable in older/insecure webviews: source dependency exists, but not demonstrated as this user's cause. Server-generated IDs avoid that unnecessary dependency.

## Tight loop and actual output

Command:
`node /home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/repro-presets.mjs`

Actual current-build observations:
```json
{"saved_in_context_a":true,"origin_a":"http://localhost:8123","saved_in_fresh_context_b":false,"blocked_storage_says_saved":true,"blocked_storage_persisted":false,"page_errors":[]}
```

Exit 1 on `Preset must persist beyond this isolated browser/origin, not only localStorage`. The second false-success is separately visible in the observed output. Both contexts were fresh agent-owned QA contexts; no user phone storage was read/cleared, no server preset records existed, and no generation was invoked.

`GET http://localhost:8123/api/presets` returned HTTP 404.

Source boundaries: `src/App.tsx:Presets` initializes from the browser key and declares Saved after changing React state; `src/lib.ts:writeStorage` returns no error and suppresses exceptions. The backend has no preset store/route. MDN describes origin-specific storage and possible SecurityError policy denial.[3]

## Required fix, not a speculative patch

Use server persistence as canonical data, retain/import existing browser copies idempotently, and acknowledge only confirmed writes. Preserve incomplete/legacy drafts rather than requiring a saved draft to be generatable or silently dropping it. Tests must cross independent browser contexts, denied storage and backend restart; same-context localStorage tests alone are a false green.
