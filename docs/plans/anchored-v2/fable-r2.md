# Council R2 (final): Fable design-integrity seat

I worked read-only. The main repo is clean at `8d56e432` (checked with `git status --porcelain` and `git rev-parse HEAD`). Nothing was implemented, published, regenerated or billed. Plan mode only let me write one file, so the full report is at `/home/renriquez/.claude/plans/council-fable-round2-final-giggly-hare.md`. `fable-r2.md` in the council folder is still 0 bytes; please copy the report there.

## VERDICT: PASS (with conditions, 0 CRITICAL)

There are no new CRITICAL findings. The amended contracts cover all 10 of my r1 findings. Two still have gaps (R1 and R2 below), but they only block later steps: publishing Hair and the first P0 provider call. They don't block G1/G2 or showing the Hair contract to the operator.

This PASS clears the work to proceed; it doesn't approve any implementation. The G1/G2 code is uncommitted and I haven't reviewed it. Every category and preview item is still `unapproved_proposal`.

## Verified facts

- **Catalog count:** running `python3 -I` over `library.json` gives 22 categories, 97 attributes (93 exclusive, 4 boolean) and 893 values. My r1 count of 25 categories was wrong, and I withdraw it.
- **COVERAGE.json:**
  - Its 97 keys match the library's 97 attribute IDs exactly, with no duplicate raw keys (checked with `object_pairs_hook`).
  - Every `current_category` matches the library, and each ID has exactly one owner, across 12 owner groups.
  - All 97 are marked `unapproved_proposal` / `legacy_independent_v1`, so nothing is wrongly labeled "controlled".
- **HAIR-PROPOSAL.json:**
  - Its status is `proposal_only_not_approved`.
  - It has 44 unique colors (17+14+8+2+3), and its `counts` field matches.
  - 11 of the 12 current hair colors keep their IDs unchanged; `salt_and_pepper` becomes a treatment recipe.
- **Source 16:** `sources/16.md` is a 290-byte navigation stub.
- **Clothing baseline:** I agree with AMENDMENTS:7. `library.json` `base_locks` already requires "Fully opaque clothing, nonexplicit editorial presentation", so no further restriction is needed.
- **G1/G2 worktree:** its HEAD is still 8d56e43, with 12 uncommitted paths (`git --no-optional-locks status --short`). I didn't review it.

## r1 self-audit

| r1 finding | Covered by | Disposition |
|---|---|---|
| HIGH: page load strips presets | GLOBAL §4, §6 | **Closed for presets.** My r1 "byte-for-byte" test asked for too much; §6's rule (keep the raw text and import wrapper) is the right standard.<br>**Gap R1:** the working draft is still pruned and rewritten (`src/App.tsx:200`, `:253`), and no amendment mentions it. It can't cause damage until Hair IDs change. When they do, the user's unsaved `hair_style` selections are dropped silently.<br>**Fix:** add the working draft to Amend 12's archive-and-preview step before Hair publishes. |
| HIGH: one hash for the whole catalog, one global manifest | Amend 1, 2 | **Closed** as a contract. |
| HIGH: approval not enforced | Amend 4 | **Closed** as a contract.<br>**Gap R2:** an approval record holding a quoted operator message proves nothing, since an agent can write one. My r1 fix had the same hole.<br>**Fix:** before the first P0 provider call, only an operator click in the UI can record an approval. It goes through the same guard G1 uses for preset changes (exact Origin, loopback) and records the hash of the contract shown. |
| HIGH: "zero change outside the mask" can't fail | Amend 6, 7, 10 | **Closed.** The same flaw applies to Amend 8: with deterministic recolors, ΔE00≥5 only measures how far apart the implementer chose the target colors. Keep the operator's judgment as the deciding check. |
| MED: hard-coded exclusion rules | Amend 13 | **Closed.** `server.py:109-117` still uses `hair_style` IDs that the proposal moves to `hair_arrangement`, so the tests must cover that remap. |
| MED: attributes with no category | Amend 3 | **Closed;** verified above. |
| MED: numeric age | Amend 15 | **Closed** with option A. Current values are `24` plus `age_21`…`age_80` (9 values). |
| MED: old gallery tags and dropped preset controls | Amend 12, GLOBAL §6 | **Closed.** |
| MED: edit adapter called "optional" | Amend 9 | **Closed.** |
| LOW: source ledger | AMENDMENTS:9 | **Partly closed.** PLAN.md:73 still cites [16], and the ledger lists 24 sources but files exist only for 1-13 and 16-21.<br>**Condition:** the Hair contract should cite only sources 10-13 and 17.<br>These proposed names never appear in those five files: ginger, mahogany, mushroom, chestnut, espresso, soft/jet black, steel. Present them as our own labels, not sourced terms. |

## Unverified assumptions

1. **The phone gateway may fail G1's stricter Origin check.**
   - Today's guard for paid requests accepts a request with no Origin header (`server.py:678-681`). GLOBAL §2 requires an exact, non-empty Origin for preset changes.
   - If the gateway drops the Origin header instead of rewriting it, every Save from the phone gets a 403 error. The app would honestly show "Save failed", but the user's phone, where the problem was reported, would stay broken while localhost tests pass.
   - I didn't check the gateway config, since that was out of scope.
   - G1 acceptance needs one save, list and delete through the real gateway, or a replay of headers recorded from it.
2. Nobody has yet observed what causes the problem on the user's phone (PLAN.md:15).
3. Whether a deterministic recolor (Pillow) from one mid-light base looks realistic for platinum, white and jet black is untested until the pilot.
4. Whether the installed model and login support `/images/edits` is unverified (Amend 9).
5. I haven't reviewed any G1/G2 code.

## Can work proceed?

- **G1/G2: yes.** Continue in the separate worktree, and add assumption 1 to its acceptance tests. The parent verifies it before merging or restarting the live app.
- **Hair-first confirmation: yes.** It can go to the operator once the nine choices below are included. Nothing happens before approval is recorded (`contract_approved`): no pilot, mask, base image or ID change. Gap R2 must also be fixed before any provider call.

## Operator choices for Hair only

1. **Base image:** reuse a photo we already own (no cost), or generate a new one. A new base is a paid call that the proposal's limit of 3 edit calls (`paid_reference_edit_cap: 3`) doesn't count, so it needs its own limit.
2. **Starting hair colors:**
   - Pick the starting color for the color tests (a mid-light neutral is recommended).
   - Pick the brown for the hairstyle tests. The proposal says "medium-brown", which isn't one of the 44 colors, so choose one that is (`light_brown` or `mocha_brown`).
3. **Hair mask:** an agent draws it and the operator approves it, or a named segmentation model makes it. A model would be a new dependency; the repo has neither today.
4. **Exact colors:** approve one sRGB/Lab value per color name. The sources only support names, not values. Without this step, the operator approves names and the implementer picks the actual colors.
5. **Pilot size:**
   - Six samples can't show whether 44 colors are distinct. I recommend rendering all 44 deterministically (no paid calls) with a table of color differences between every pair. The operator then merges near-duplicates at real card size.
   - Use the six samples for the 1x/2x realism check. Include the hard cases: platinum, white, jet_black, bright_ginger, strawberry_blonde and the two closest colors.
6. **Splitting hair_style:**
   - Confirm the five new controls: cut, texture, arrangement, parting and finish. Each of the 13 current style IDs needs a mapping.
   - These four need a decision:
     - `side_part`: left, right or deep_side.
     - `messy_waves`: a texture plus finish recipe.
     - `sleek_center_part`: center plus sleek.
     - `straight`: straight_natural or pin_straight.
   - Decide whether `hair_style` itself is archived or kept as a read-only recipe.
7. **Cut vs length:**
   - `buzz_cut` exists in both the current `hair_length` and the proposed `hair_cut`, and pixie, bixie and undercut also imply a length.
   - Choose: short cuts set the length themselves, or an explicit table of banned cut and length pairs.
   - Also confirm the shaved/buzz rules against arrangement, fringe and parting.
8. **Color treatments:** the proposal's `kind: "recipe"` isn't a type the server accepts (`server.py:80` allows only exclusive, boolean and multi). Either leave treatments out of Hair v1, with `salt_and_pepper` still readable in history, or make treatment an exclusive control with explicit color and treatment rules.
9. **Old prompt text and preview accuracy:**
   - The prompt text for `golden_blonde` says "warm honey highlights", which conflicts with a single uniform color. Either freeze the old prompt text or rewrite it. A rewrite changes how old IDs generate, so take a snapshot first per Amend 12.
   - Previews will show 44 precise colors that the generator, working from text prompts, may not tell apart. Either label them "simulated target color; generated results approximate" (the default), or pay for a capped spot-check of the closest pairs before publishing.

**Recommendation:** split Hair into two releases. Hair-Color uses deterministic recolors and doesn't need the edit adapter. Hair-Geometry waits for the Amend 9 edit-support probe. That way Hair-Color can publish without waiting on edit support.
