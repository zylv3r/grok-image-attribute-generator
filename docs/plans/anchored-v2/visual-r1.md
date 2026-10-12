## VERDICT

CHANGES-REQUESTED. Round 1, visual/UX/photography seat.

Verified clean HEAD `8d56e432a0bbd87fbeca16497a74acf96f6df22f` using `git status --short` and `git rev-parse HEAD`. Reviewed the [proposal](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/PLAN.md), actual UI/catalog, and specified sources. Proposed comparison/preset modules do not exist yet. No writes, generations, storage inspection, or live restart performed. This is a source review, not rendered-browser acceptance.

The proposal correctly requires category approval and honest technique labels. Remaining issues need concrete contracts before approval; none warrants a CRITICAL verdict.

### [MEDIUM] Hair needs a concrete first-confirmation taxonomy

**Claim:** Hair will gain substantially expanded blonde/red families and reconciled controls.

**Reality:** The proposal leaves exact values pending. Actual Hair contains 12 colors, 13 styles, eight lengths, eight fringes and eight accessories. `hair_style` mixes texture, parting and arrangement; `hair_length` includes shaved/buzz treatments. See [library.json](/home/renriquez/projects/grok-image-attribute-generator/library.json:269), [style definitions](/home/renriquez/projects/grok-image-attribute-generator/library.json:362), and [Hair proposal](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/PLAN.md:71).

Sources support naming distinctions, not standardized RGB targets: [10: strawberry](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/sources/10.md:9), [11: champagne](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/sources/11.md:13), [12: copper](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/sources/12.md:13), [13: blonde families](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/sources/13.md:33), and [17: tone families](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/sources/17.md:147). Source [16](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/sources/16.md:1) contains only title/navigation and cannot substantiate copper-gold guidance.

**Consequence:** Approval could authorize synonym padding or preserve contradictory controls.

**Fix:** Present this bounded draft for **Hair only**, assigning stable IDs before confirmation:

| Family | Proposed visibly differentiated candidates |
|---|---|
| Blonde | Platinum/white; icy silver; pearl violet; very-light cream; pale butter; pale champagne; rosé champagne; light beige; medium ash; sandy beige; light golden; medium honey; dark neutral blonde; dark ash; caramel blonde; golden bronde |
| Red/copper | Light peach strawberry; classic strawberry; dark strawberry; apricot copper blonde; honey copper blonde; bright ginger; natural copper; deep copper; muted light auburn copper; medium auburn; dark auburn; red-copper; mahogany red; garnet red |

These are proposed visual targets, not claimed salon equivalents. Document depth/undertone for every candidate. Consolidate candidates that fail visual separation; do not publish barely distinguishable names.

Reconcile controls as:

- **Cut:** blunt one-length, graduated bob, long layers, shag, wolf cut, pixie, buzz. Length compatibility is explicit.
- **Texture:** straight, gentle waves, pronounced waves, loose ringlets, tight curls, tight coils.
- **Arrangement:** loose, low/high bun, low/high ponytail, single braid, twin braids, braided crown, half-up.
- **Parting:** center, left, right, no visible part. “Sleek” becomes a finish modifier.
- **Length:** actual loose-strand length, measured against approved anatomical landmarks; preserve existing IDs through migration.
- **Fringe:** preserve existing eight values. Map face-framing strands to a front-strand control; retain its legacy meaning.
- **Accessories:** preserve existing eight values and distinguish explicit “no accessory” from unset.
- **Treatments:** highlights, lowlights, root shadow, balayage, ombré and salt-and-pepper distribution are spatial treatments/recipes, not additional uniform pigments.

Map `straight`, `soft_waves`, `loose_curls`, `tight_coils` to texture; buns/ponytails/braids to arrangement; part values to parting. Preserve `messy_waves` and `sleek_center_part` as disclosed compound recipes. Legacy Golden Blonde’s honey-highlight steer also needs disclosed treatment migration.

**Closed choice H1:** approve this split taxonomy, or retain the current style IDs as explicitly compound recipes and defer splitting. Neither choice authorizes generation. Reject incompatible pools visibly—do not silently discard combinations.

### [HIGH] “Same base image” requires measurable acceptance and a paired reviewer

**Claim:** Every value forks one approved base and changes only its target.

**Reality:** [P0](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/PLAN.md:53) specifies provenance and drift checks, but no thresholds or review presentation. Current cards provide individual examples and “Open original”; [ImageDetail](/home/renriquez/projects/grok-image-attribute-generator/src/components/ImageDetail.tsx:74) displays one image. See [Library](/home/renriquez/projects/grok-image-attribute-generator/src/components/Library.tsx:53). The old worker’s [verification](/home/renriquez/projects/grok-image-attribute-generator/scripts/generate_photographic_previews.py:89) checks records/files/dimensions, not visual isolation.

**Consequence:** Correct bookkeeping can still admit altered faces, oversized masks, invisible color differences or misleading “unchanged” claims.

**Fix:** Approve two separate female baseline contracts:

- **Color:** one adult woman, straight collarbone-length hair, center part, open forehead, no accessory; fixed face, skin, eyes, expression, ivory opaque top, neutral background, light and crop.
- **Style:** the same approved woman in a sufficiently wide fixed frame, neutral medium-brown pigment. Each attribute group has its own frozen starting geometry; every result receives identical source bytes. Parting comparisons hold texture; texture comparisons hold cut/length.

Names above are proposals, not approved image IDs.

Reviewer: side-by-side baseline/result, before/after toggle, optional wipe, synchronized crop/pan and 100%/200% zoom. Mobile gets a full-width toggle with identical viewport coordinates. Display base ID/hash, target value, method and approval state. Provide a separate keyboard-accessible **Review** control so inspection does not select a value.

Label allowances plainly: **Hair pigment + edge blend**, **Hair geometry + revealed background**, **Declared shadow/occlusion change**, or **Whole-image simulated effect**.

Acceptance must require:

1. Identical recorded source hash, dimensions and crop for every result; no chained edits.
2. Zero changed decoded pixel channels outside the approved footprint for composited lossless masters. Include antialiased hair-edge pixels in that footprint.
3. Independently approved mask boundaries; hairstyle masks cover old/new silhouettes and necessary reveal regions, never the entire frame by default.
4. No displacement of visible locked facial landmarks; no unwanted halos, clipped strands, lost texture or facial edits at 100%.
5. Color candidates pass a proposed separation gate—e.g. median ΔE00 ≥5 on fixed representative hair patches—plus operator discrimination at intended card size. This is a design threshold, not a sourced industry standard.

**Closed choice H2:** exact composited locks with explicit geometry exceptions, or visibly labeled approximate reference edits. Approximate edits cannot satisfy the user’s exact same-base comparison requirement.

### [MEDIUM] Preset recovery needs distinct empty, unavailable and profile states

**Claim:** G1 fixes persistence and false save success.

**Reality:** Current [Presets](/home/renriquez/projects/grok-image-attribute-generator/src/App.tsx:57) loads browser storage, announces success before durable confirmation, and shows “No presets yet” for an empty result. [Storage helpers](/home/renriquez/projects/grok-image-attribute-generator/src/lib.ts:11) collapse read failures to null and suppress write failures. [G1](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/PLAN.md:32) addresses persistence but leaves collection/profile UX unspecified. The phone’s exact failure remains unverified.

**Consequence:** Storage denial or the wrong collection can look like missing data.

**Fix:** Separate **Loading**, **No saved presets**, **Cannot load—Retry**, **Saving**, **Saved**, and **Save failed—Retry**. Retain name/draft on failure. Explain blocked browser storage only when observed: server persistence may still work. Show legacy import status without clearing local copies.

**Closed choice P1:** one installation-wide collection labeled “Saved on this studio,” or explicit named profiles with separate collections and a visible profile switcher. Do not infer a profile from browser origin. If private preset storage is unavailable, show unavailable state; never claim an empty collection.

Before Apply, display unresolved/retired controls and their disposition rather than silently pruning them through [cleanDraft](/home/renriquez/projects/grok-image-attribute-generator/src/lib.ts:84).

### [LOW] Bulk variation scope is specified correctly but needs visible counts

**Claim:** All/None/Inverse covers the entire attribute.

**Reality:** [G2](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/PLAN.md:43) is explicit and sound. Current [Library](/home/renriquez/projects/grok-image-attribute-generator/src/components/Library.tsx:27) filters/paginates values and has only None/unset.

**Consequence:** Search can make an entire-attribute operation appear scoped to visible matches.

**Fix:** In Vary mode show **All N values**, **None**, **Inverse across N values**, plus “K allowed · M shown; actions affect all N.” Preserve catalog order and unrelated selections. None retains Vary preference and means unset; explicit boolean Off remains a separate value.

**Closed choice V1:** entire attribute now; filtered-results actions deferred. If later approved, offer a separately labeled “Matching results” scope. Never change scope implicitly when searching.

### [MEDIUM] Optics needs demonstrations of physical coupling, not setting-themed portraits

**Claim:** Photography previews isolate optics on one scene.

**Reality:** [P0](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/PLAN.md:61) recognizes simulation, but current [focal-length steers](/home/renriquez/projects/grok-image-attribute-generator/library.json:3079) associate focal length with perspective/compression without specifying camera position. Source [8](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/sources/8.md:143) supports WB color changes. Source [9’s truncation notice](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/sources/9.md:38) points to its verified [complete continuation](/home/renriquez/.local/share/hermes-owner/home/cache/web/www.nikonusa.com-f9b2aa5512.md:14), whose Depth of Field entry names focal length, aperture and distance as coupled variables.

**Consequence:** A same-image crop could falsely demonstrate perspective; automatic exposure could hide additional changed settings.

**Fix:** Use one approved scene containing the woman, near/far objects, gray/white patches, textured highlights and a declared moving region.

- **Focal length:** fixed sensor/camera position; longer settings narrow field of view. Crop simulation preserves perspective and loses resolution. Compensated framing requires moving the camera and changes perspective.
- **Aperture:** fixed lens, distance and focus plane; depth-aware blur simulation. Declare exposure compensation. Physical autoexposure changes shutter and/or ISO; a deterministic constant-brightness demo merely suppresses that consequence.
- **Shutter:** fixed motion direction/speed and camera stability; blur only the declared moving region and its swept footprint. Panning and camera shake need separate contracts. Still regions do not blur merely because shutter duration increases.
- **Focus:** use approved depth planes; an ordinary flattened image cannot recover detail absent from the source.
- **Grain:** seeded noise with separate scale/strength; label simulated grain/noise, not measured ISO capture.
- **WB:** same illumination, whole-image color adjustment; material colors necessarily change. Specify assumed illuminant and gains.
- **Rolloff:** fixed exposure and documented highlight curve; clipped information cannot be restored. Glow/bloom is a separate spatial effect.

**Closed choice O1:** publish fixed-camera field-of-view simulation first; defer compensated-framing perspective demonstrations until a separate camera-position allowance is approved. Require numeric transform receipts and reject uncalibrated photographic-setting claims.

### [MEDIUM] Mood and narrative require explicit exceptions to locks

**Claim:** These categories can expand while preserving an anchor.

**Reality:** Current [mood/narrative steers](/home/renriquez/projects/grok-image-attribute-generator/library.json:2876) mix wardrobe, gaze, posture, lighting, motion and presumed intention. [The proposal](/home/renriquez/.local/share/hermes-owner/home/cache/scratch/anchored-studio-council/PLAN.md:105) identifies the conflict but leaves its resolution open.

**Consequence:** Strictly locked previews cannot distinguish activities; unrestricted recipes undermine target isolation.

**Fix:** Mood becomes a disclosed aesthetic recipe referencing canonical grade/contrast/lighting controls, with identity/geometry locked. Each recipe lists changed components. Describe visible treatment rather than a real person’s emotional state.

Narrative uses observable actions: writing, examining an object, greeting, preparing a bag. Declare hands/arms/head/gaze, prop and occlusion allowances; keep identity, wardrobe design/color, camera and environment fixed. “Reflection” cannot be accepted solely from an assumed inner feeling.

**Closed choice M1:** allow listed aesthetic transformations, or retain mood as text-only direction. **Closed choice N1:** allow listed action/prop regions, or retain narrative as text-only direction. Approve these contracts when their category arrives; Hair approval must not authorize them.