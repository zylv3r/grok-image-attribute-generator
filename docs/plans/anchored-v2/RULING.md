# Council ruling — anchored comparisons and category-by-category revision

## Status

Four seats (technical/security, design integrity, fashion/body taxonomy, visual/UX/photography), two rounds. All final seats returned **PASS for the amended contracts and proceeding scope**, with no new CRITICAL findings. This is not certification of unbuilt comparison code or approval of any paid image pilot. Full raw reviews and amendments travel with this ruling.

**Implemented now:** server-backed presets and whole-attribute Vary All/None/Inverse. Parent verified 25 browser tests/78 Python tests, plus REAL localhost-save → fresh authenticated phone-context readback/apply/delete with browser storage and crypto denied, and a REAL backend restart/idempotent save readback. QA records were deleted exactly; user data and photos preserved. Browser localStorage is origin-specific and may be denied, explaining why it cannot be canonical across devices/tunnels.[3]

**Not implemented or approved yet:** new category IDs/values, reference edit capability, masks, controlled sample publication or bulk regeneration. The 893 old photographs remain independent exploratory examples, not controlled comparisons.

## Governing preview rules

1. One operator-approved adult female subject and immutable base/crop per comparison group. Every value forks the same ORIGINAL reference, never a predecessor.
2. Hold all non-target variables: model identity, eye/skin color, outfit design/color, background, pose/head/gaze, light/camera/crop unless explicitly targeted or an approved unavoidable consequence.
3. Hair color and garment color: masked photographic recolor/texture swatches; compare lossless PNG masters and review masks. JPEG thumbnails are derivatives. Zero pixel drift outside a mask is a compositing check, not proof a mask is correctly drawn.
4. Hair styles, expressions, face shapes, poses/body and garment geometry: reference-conditioned edits, narrow reviewed change footprints, target-effect and identity/anatomy review; withhold drifted results. New xAI editing must use documented JSON/base64 inputs rather than an unsupported multipart SDK path, and actual installed model/OAuth compatibility remains unverified.[1][2]
5. Optics: one approved scene, honest simulated-method labels and declared physical consequences. Fixed-camera focal crops show field of view, not perspective; aperture/focus need depth assumptions, motion blur needs moving regions, white balance changes colors and rolloff cannot recover clipped highlights.[8][9]
6. Preserve raw presets/history before any ID changes. Freeze v1 catalog bytes, use per-category pointers, alias/retirement ledgers and explicit migration previews. Never silently clean away unsupported saved controls or orphan old gallery filters.
7. Every category has separate contract → capped pilot → user acceptance → expansion → reviewed publication. Approval names/hash, masks and artifacts are recorded. Hair approval cannot authorize another category or a full-library generation pass.

## First category: Hair — proposal for confirmation

**44 uniform pigment candidates:** 17 blondes, 14 red/copper/strawberry shades, 8 browns, 2 blacks and 3 grays.
Strawberry, champagne and copper-blonde terminology informs these proposed families.[10][11][12]
Blonde family examples and professional tone charts also inform the naming.[13][17]
These design candidates are not standardized RGB targets or guaranteed salon equivalents. Near-duplicates must merge if the pilot cannot distinguish them at thumbnail size.

**Blondes:** platinum, icy silver, pearl, very-light cream, pale butter, pale champagne, rosé champagne, light beige, ash, sandy beige, light golden, golden, medium honey, dark neutral, dark ash, caramel, golden bronde.

**Reds/copper/strawberry:** light peach strawberry, strawberry, dark strawberry, apricot copper blonde, honey copper blonde, bright ginger, natural copper, deep copper, muted light auburn copper, medium auburn, dark auburn, copper red, mahogany red, garnet red.

**Remaining families:** light/ash/mushroom/mocha/warm-golden/chestnut/chocolate/espresso brown; soft/jet black; white/silver/steel gray. Salt-and-pepper is a two-tone distribution recipe, not a uniform pigment.

**Reconcile ten controls:** pigment, cut, texture, arrangement, parting, finish, length, fringe, accessory, color treatment. Structured proposals include20 cuts,9 textures,19 arrangements,5 partings and6 finishes, while preserving length/fringe/accessory IDs. Old mixed styles become disclosed recipes rather than duplicate/conflicting knobs. All49 old Hair values have a proposed disposition in HAIR-MIGRATIONS.json; side_part needs left/right resolution, not a guessed mapping.

**Color sample locks:** same woman, same hairstyle/length/fringe, face/skin/iris, pose/gaze/head, outfit, background, light, camera and crop. Only hair pigment/luminance changes.

**Style sample locks:** same woman and one neutral medium-brown pigment; same wardrobe/scene/light/view. Only the approved hair-geometry/reveal/occlusion footprint changes. A wider reference may be required for lengths; it is approved as a distinct group, not secretly substituted mid-comparison.

**Pilot approval scope:** choose/reuse a female baseline, review mask overlay, six controlled color examples, and at most three paid reference-edit capability/style attempts including any needed baseline adjustment. No bulk Hair expansion until the pilot passes and you accept it. Reference edits cannot be called exactly locked merely because a prompt says so.

## Remaining categories — proposals, not changes

- **Face / expressions / makeup:** one canonical expression control; retire or disclose old Face & Expression concepts rather than pretend luminous/classic_beauty are emotions.43 expression candidates are defined for later review; visible mouth/brow/lid/cheek movements, fixed identity/angle/iris and gaze. FACS source supports movement terminology, not claims to read a real person's emotion.[21] Makeup stays separately owned.
- **Eyes:** expand iris colors and patterns; same iris geometry/face/light, iris-only color changes. Eyelashes use the same close eye crop, color/shape/skin/makeup, with only declared lash length/density/curl/pigment changes.
- **Skin:** remove active Style Inspiration, Complexion Detail and Facial Balance after archival/migration; reconcile tone/undertone/finish with cosmetics. Add appearance-only pigmentation distribution, freckles/moles and depigmented-patch controls, not clinical diagnosis or ancestry ranking.
- **Body:**14 proposed orthogonal controls with51 candidate values cover frame, stature, fullness, muscle definition, shoulder width/slope, waist, hip, bust volume, thigh volume, calf, leg/torso balance and glute/hip fullness. Figure/silhouette become recipes. Fitness labels describe visible muscle appearance, not health/ability/BMI. Same clothed adult female baseline; body-caused fabric-fit/shadow changes are explicit consequences.
- **Wardrobe:**24 proposed families/341 candidate options cover dress shapes/families, tops, necklines/collars, sleeves, rise/waistband, hems, trousers/skirts/jumpsuits/shorts, outerwear, construction/closures/materials/patterns/fit/shoes/layering.
  These design proposals use garment classification and neckline/collar terminology.[4][5][6]
  A fashion dictionary and dress-design examples also informed the families.[7][18][19]
  Clothing examples supplied further terminology.[20]
  The first candidate list still needs semantic deduplication (for example qipao/cheongsam); do not confuse differing IDs with distinct options. Garment colors use texture/color patches, not woman renders. Explicit layering allows valid dress-over-trousers combinations; default rules prevent accidental contradictory ensembles. Opaque secure adult strapless styles are not inherently prohibited.
- **Poses:** expand action/posture families and modifiers; use the same woman, outfit/colors, environment/light/lens; distinguish gestures/props from primary pose and validate anatomy/occlusion.
- **Age / gender:** age dial/input21–85 initially, no image renders; canonical discrete age IDs are recommended to avoid an immediate numeric gallery migration. Exact legacy24 mapping. Gender/presentation can vary in actual generation; all sample baselines remain women.
- **Photography:** same scene for focal length/aperture/shutter/grain/focus/WB/rolloff. Show permitted effects, not unrelated scene changes, and label simulations/couplings accurately.[8][9]
- **Editorial mood / narrative:** mood is a disclosed recipe of grade/contrast/light treatment, not another expression list. Narrative is an observable action recipe with explicitly permitted hands/arms/gaze/props/occlusions; writing versus conversation cannot be shown honestly with every pose and prop pixel locked. Confirm those allowances when that category arrives.
- **Lighting/composition, environment/weather/props:** each legacy control has an explicit owner and review gate. Background changes only when it is the target; location/weather/time and remaining style controls are not abandoned.

COVERAGE.json maps every one of the97 live attribute IDs to exactly one review group. Expanded JSON catalogs are proposals only; no provider calls or taxonomy publication were made for them.

## Decisions needed now — Hair only

1. Approve the split Hair taxonomy and44 pigment candidates, or amend/defer components.
2. Pick/approve the female baseline and its masks. Strict target-only master locks with enumerated geometry consequences are recommended; approximate edits are not presented as controlled.
3. Authorize only the bounded pilot (six deterministic color examples, up to three paid reference-edit attempts), or approve taxonomy discussion only. Expansion/publication needs a separate acceptance.

All later category decisions remain for their own confirmation, not one giant approval form.

## Sources

[1] https://docs.x.ai/developers/model-capabilities/images/editing
[2] https://docs.x.ai/developers/model-capabilities/images/multi-image-editing
[3] https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage
[4] https://textilelearner.net/different-types-of-necklines-in-fashion
[5] https://textilelearner.net/what-is-garment-classification-of-garments
[6] https://textilelearner.net/types-of-collars-for-dresses
[7] https://wunderlabel.com/lab/fashion-dictionary
[8] https://www.nikonusa.com/learn-and-explore/c/tips-and-techniques/setting-white-balance
[9] https://www.nikonusa.com/learn-and-explore/photography-glossary
[10] https://www.wella.com/professional/en-US/blog/hair-color/strawberry-blonde-hair-ideas
[11] https://www.wella.com/professional/en-US/blog/hair-care/champagne-blonde-hair-color
[12] https://www.wella.com/professional/en-US/blog/hair-color/copper-blonde-hair-color
[13] https://uk.wella.professionalstore.com/blog/hair-colour/blonde-hair-colours
[17] https://us.lorealprofessionnel.com/-/media/project/loreal/brand-sites/lp/americas/us/products/hair-color/majirel/majirel/majirel-color-chart-0686e00000xfmelaab.pdf
[18] https://textilelearner.net/different-types-of-dresses-for-women
[19] https://textilelearner.net/types-of-fashion-categories-to-dress-design
[20] https://textilelearner.net/different-types-of-clothes-with-pictures
[21] https://www.paulekman.com/facial-action-coding-system
