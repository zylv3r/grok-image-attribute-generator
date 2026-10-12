## VERDICT
**CHANGES-REQUESTED.** I found no CRITICAL problems (no damage or false-green completion), but two HIGH gaps make the plan's promises about keeping old IDs readable and preventing invalid combinations impossible to enforce as written. The plan is still only a proposal: the repo is clean at 8d56e43, and `catalog/v2/`, `comparisons.py` and `presets.py` don't exist yet.

The baseline is confirmed by script: `library.json` has 21 categories, **97 attributes and 893 values**. The gallery has 1001 images and 3346 image tags (read through a read-only SQLite connection).

## Findings

### [HIGH] Retiring or renaming an ID silently deletes it from saved selections
- **Plan says (§3):** old IDs stay readable, and preset migration shows controls that can't be resolved.
- **Code does:** `src/lib.ts:48-75 pruneChoices` quietly drops any attribute or value that isn't in the current library. Drafts (`cleanDraft`, `:84-89`) and gallery URL filters (`:79`) both pass through it. On the server, `server.py:145` rejects the request with `unknown attribute`; I confirmed this by calling `validate_map({'retired_attr':[...]})` directly.
- **Old images still tagged with values the plan changes:** face_direction 44, silhouette 46, facial_balance 42, complexion_detail 3, ethnic_inspiration 3, hair_style 113, age 109.
- **Result:** a retired ID disappears from presets and from "reuse selections" without any message, and old images can no longer be filtered by it.
- **Fix:** add a `catalog/v2/aliases.json` that maps each old `attr:value` either to its new value(s) or to `{retired, disclosure}`. Resolve it before `pruneChoices` and `validate_map`, and return a list of unresolved IDs to the UI. Keep the old values as read-only gallery filters. Add a test that every retired ID comes back with its disclosure.

### [HIGH] Only hair has combination rules, so impossible outfits pass validation
- **Evidence:** `grep -c '"excludes"' library.json` returns 0. The only rules are hardcoded in `server.py:109-117`: 26 pairs (2 short hair lengths × 13 styled hair and fringe values).
- **Combinations that currently pass with no conflict** (checked with Pillow stubbed out, no writes):
  - a slip dress together with trousers, a skirt and a top
  - "no outerwear" with an ankle-length coat
  - a high slit with culottes
  - silhouette `slender_hourglass` with body build `full_figure`
  - a shaved head with a scrunchie and tight coils
- **Result:** these outfits get generated, and the combination count is wrong for them (`server.py:259`).
- **Fix:** add attribute-level rules to the v2 schema (`excludes_attribute`, plus `requires: garment_set in {...}`) and generate the pair list from them so the existing `conflict()` check keeps working. Add one test per rule.

### [MEDIUM] Two current values contradict the non-sexual baseline
- `editorial_mood.sensual_luxe` steers toward "sensual, sexy yet tasteful".
- `silhouette.couture_hourglass` steers toward a "visually cinched couture waist, a naturally fuller bust".
- Both conflict with the library's own "nonexplicit" base lock and with §4 of the plan.
- **Fix:** retire both with a disclosure. Replace them with `satin_evening_luxe` (styling and material only) and the `hourglass` body recipe.

### [MEDIUM] The sources ledger doesn't match the fetched files
- The ledger lists sources 1–24, but files exist for only 19. **14, 15, 22, 23 and 24 are missing.**
- `16.md` is a 290-byte navigation stub, yet the plan's §1 cites [16] for hair color.
- `7.md` is cut off: it only has dictionary sections A, B, C, W, X, Y and Z (`grep -c '^## [D-V]$'` returns 0).
- `21.md` has no list of Action Units. It only says FACS is "anatomically based" and covers "visually discernible facial movement".
- **Fix:** refetch [14–16] and [22–24], or drop the citations. Don't cite Action Unit numbers until 22 or 23 is actually fetched. My proposals cite only 4–7, 10–13, 17, 18 and 21.

### [MEDIUM] Several attributes combine two or three different settings in one list
This is why a comparison can't change one thing while holding everything else fixed.

| Attribute | What it combines | Example |
|---|---|---|
| `skin_tone.pale_pinkish` | skin depth and undertone | can be paired with undertone `warm_gold`, which contradicts it |
| `hair_style` | texture, parting and updo | `messy_waves`, `sleek_center_part`, `low_bun` |
| `waist_position` | rise and waistband construction | `high_waist` vs `paperbag_waist` |
| `hem_length` | length and hem shape | `ankle` vs `high_low` |
| `neckline` | necklines and collars | `collared`, `stand_collar`; source 6 treats collars separately |
| `dress_style` | dress shapes and necklines | `off_shoulder`, `high_neck_dress` |
| `top_style` | top types and necklines | `turtleneck`, `boat_neck_top` |
| `shoulder_shape` | width, slope, muscle and posture | `defined_shoulders`, `relaxed_shoulders` |
| `pose` | poses and hand props | `reading_book`, `holding_cup`, `holding_umbrella` duplicate `hand_prop` values |

`eyewear` also sits under Props when it's an accessory.

### [LOW] The age ID `24` doesn't follow the `age_N` pattern
27 old tags use `24` and 75 use `age_21`. When age becomes a numeric dial, map each ID to its exact number with no rounding.

## Proposed category map (proposal only)
- **Identity:** age as a number from 21 to 85, plus presentation.
- **Hair:** color, color treatment, length, texture, part, arrangement, finish, fringe, accessory.
- **Face structure:** face shape, cheekbones, brows, eye shape, nose, lips.
- **Eyes:** eye color, eyelashes.
- **Expression and gaze.**
- **Skin:** tone, undertone, finish, micro-texture, freckle density, freckle distribution, pigment features.
- **Makeup:** unchanged.
- **Body:** 10 controls plus named body recipes.
- **Wardrobe:** outfit type, garment pieces, details, materials, outerwear and layering.
- **Footwear.**
- **Accessories,** with eyewear moved here.
- **Editorial recipes:** mood and narrative.

This seat covers 59 of the 97 attributes. The other 38 (pose, optics, lighting, scenery and props) belong to other reviewers.

## Migration table for the 59 attributes in scope

**Kept unchanged (25):** micro_texture, skin_undertone, hair_length, hair_fringe, hair_accessory, face_shape, brow_shape, eye_shape, nose_shape, lip_shape, gaze_direction, the 4 makeup attributes, sleeve_length, skirt_cut, outerwear_length, shoe_material, fabric_color, drape_effect, seam_detail, jewelry_style, metal_finish, bag_style, belt_style, scarf_style.

**Changed:**

| Current | Action | What happens to old values |
|---|---|---|
| `hair_style` (13) | Split | Texture: `messy_waves` becomes `soft_waves` plus a tousled finish; `soft_waves`, `straight`, `loose_curls` and `tight_coils` keep their IDs. Part: `sleek_center_part` becomes center part plus a sleek finish; `side_part` keeps its ID. Arrangement: the 6 updos keep their IDs. |
| `hair_color` (12) | Keep all 12, expand to 35 | none lost |
| `freckles` | Replace | `off` becomes density none; `on` becomes light density on face, shoulders and upper chest; `prominent` becomes moderate density on nose and cheeks |
| `skin_tone.pale_pinkish` | Merge | becomes `porcelain` with a `cool_rose` undertone, shown to the user |
| `skin_finish.hydrated` | Merge | becomes `dewy` (the steer text is effectively the same) |
| `expression` (8) | Keep IDs | steers rewritten as visible face movement |
| `face_direction` | Retire | `confident` maps to gaze at camera plus a serious expression, shown to the user; `soft_sultry` maps to `softened_lids`; `luminous` and `classic_beauty` are flagged as unresolved |
| `ethnic_inspiration`, `complexion_detail`, `facial_balance` | Retire (8 values) | readable on old images only; old complexion values can be offered as undertone suggestions but are never applied automatically |
| `cheekbones`, `eye_color`, `eyelashes` | Move to Face and Eyes | eye color expands from 9 to 15 |
| `silhouette` | Retire | each value becomes a body recipe; `couture_hourglass` becomes `hourglass` with a disclosure |
| `body_build` | Split | `lean` → fullness lean; `athletic` → muscle athletic; `soft_average` → fullness soft; `broad_frame` → frame broad; `petite_frame` → frame petite; `full_figure` → fullness full; `tall_frame` → stature tall; `compact_athletic` → frame slight plus muscle athletic |
| `shoulder_shape` | Split | width and slope are kept; `defined_shoulders` becomes toned muscle definition; `rounded_shoulders` and `relaxed_shoulders` are retired because they describe posture |
| `dress_style` | Rename to `dress_silhouette` | `off_shoulder` moves to neckline; `high_neck_dress` becomes `column_dress` with a high neck; `pleated_dress` becomes `a_line` with knife pleats |
| `top_style` | Keep 6 | `turtleneck` becomes a knit pullover with a turtleneck neckline; `boat_neck_top` becomes a shell top with a boat neck |
| `neckline` | Split | `collared` becomes a shirt collar; `stand_collar` becomes a mandarin collar |
| `waist_position` | Split | into rise (4 values) and waistband construction |
| `hem_length` | Split | `asymmetric` and `high_low` move to a new hem shape attribute |
| `trouser_cut` | Keep 7 | `pleated_trousers` becomes `straight_leg` with knife pleats |
| `high_slit` | Keep | only allowed with a dress or skirt |
| `editorial_mood` | Keep 3 | `sensual_luxe` is retired and replaced by `satin_evening_luxe` |
| `narrative` | Becomes a recipe | see rulings |
| `age` | Becomes numeric | exact mapping |
| `eyewear` | Move to Accessories | none lost |

## Proposed value catalogs
A script counted these: **43 attributes and 371 values** across the touched families. This is a proposal, not implemented.

- **Hair:**
  - color treatment (7): none, highlights, babylights, balayage, ombre, face-frame brightening, root shadow [10][13]
  - texture (8), part (4), arrangement (11), finish (5)
- **Expression (19):** neutral, gentle smile, broad smile, open smile, laughing, amused, smirk, serene, serious, thoughtful, concentrated brow, lips pressed, pursed lips, parted lips, surprised, curious brow raise, one brow raised, softened lids, eyes crinkled with smile.
- **Eye color (15).**
- **Skin:**
  - freckle density (5) and freckle distribution (4)
  - pigment features (6, multi-select): beauty mark, scattered moles, sun spots, diffuse uneven pigment, and vitiligo-like light patches. These are labeled by appearance only, with no diagnosis named.
- **Body (10 controls, 40 values):** frame, stature, fullness and muscle definition (5 each); shoulder width and slope (3 each); waist definition and hip breadth (4 each); bust proportion and leg-to-torso balance (3 each).
  - Recipes set these controls rather than adding more: hourglass, slender hourglass, pear, inverted triangle, rectangle, statuesque, petite long-legged.
  - "Fitness" means visible muscle definition only, with no health, BMI or ability wording.
- **Wardrobe:**
  - outfit type (5: dress, jumpsuit, top and trousers, top and skirt, top and shorts) and dress shape (15)
  - tops (14), trousers (13), skirts (10)
  - necklines (14) [4], collars (8) [6], sleeve shape (11)
  - rise (4), waistband (6), hem length (6), hem shape (6)
  - fit (5) [7], closure (7), surface details (10)
  - material (16, grouped as woven, knit and nonwoven) [5], pattern (13)
  - outerwear (17) [18], shoes (15), heel height (4), layering (5)
- **Deliberately left out:** plunging and illusion necklines [4], babydoll and chemise [7][18], sheer fabrics unless lined, and source 18's lingerie list.

**Combination rules to encode** (the fix for the second HIGH finding):
- Outfit type:
  - A dress or jumpsuit excludes tops, trousers and skirts.
  - The "top and …" outfits exclude dress shapes.
  - Trousers and skirts exclude each other.
- Outerwear: "no outerwear" excludes outerwear length.
- Necklines and sleeves:
  - Strapless, halter and off-shoulder necklines allow only "no collar".
  - Sleeveless excludes sleeve shape.
- Hems and shoes:
  - Hem length and hem shape require a dress or skirt.
  - Sneakers exclude high heels.
- Hair:
  - Shaved and buzz-cut lengths exclude texture, part and finish, every arrangement except worn down, and every accessory except a wide headband.
  - Ear-length hair allows only worn down or half up.

## Category rulings
- **Hair (first category to review):**
  - Review color first, then the `hair_style` split, then the combination rules.
  - Name colors by depth level and tone, following the level-plus-tone codes on the professional color chart in source 17 (lines 147–148 and 253–254). Each value stores its level and tone so near-duplicates have to differ by at least one step.
  - The 35 values:
    - 12 blondes [11][13]: platinum, ice, ash, beige, champagne, cream, butter, golden, honey, caramel, dark, bronde
    - 5 strawberry and copper blondes [10][12]: light, regular and dark strawberry blonde; copper blonde; apricot blonde
    - 6 reds [12]: light auburn copper, golden copper, copper red, deep copper, auburn, dark auburn
    - 7 browns [17]: light, ash, mocha, warm golden, chestnut, chocolate, espresso
    - 2 blacks: soft black, jet black
    - 3 grays: silver, salt-and-pepper, white
  - Dropped as near-duplicates: dirty blonde, vanilla, powdered, silver blonde.
  - Balayage, ombre and highlights are techniques, so they go under color treatment.
- **Expression:**
  - One canonical expression attribute.
  - Steers describe only visible movement of the mouth, brows, lids and cheeks [21], never an inferred emotion.
  - The lids may change, but gaze stays locked, and "eyes closed" excludes "softened lids".
- **Eyes:**
  - Eye color comparisons use a close crop where only the iris changes.
  - The `brown_lashes` value mixes color into a shape list. Keep it for now but flag it.
- **Skin:** compare skin finish only with bare-face makeup. When makeup is applied, makeup finish governs the face.
- **Body:**
  - Comparisons use the same adult woman in an opaque fitted knit, facing front, in a neutral pose.
  - The garment's fit may follow the body change. Its design and color stay fixed.
- **Mood vs narrative:**
  - Mood is a recipe that sets color grade, contrast, light quality and styling polish. It may not change expression, pose or body.
  - Narrative may change only pose, gaze and hand prop. Expression stays neutral, and wardrobe, scene and camera are locked.

## Operator choices (each closed)
1. **Narrative:** (A) a recipe that writes pose, gaze and prop *(recommended)*, or (B) a standalone steer with pose and gaze unlocked as a declared exception.
2. **Bust proportion:** (A) include it with 3 neutral levels *(recommended)*, or (B) leave it out and let the recipes cover it.
3. **Strapless neckline:** (A) exclude it *(recommended)*, or (B) include it, opaque and secure.
4. **`luminous` and `classic_beauty`:** (A) retire them as unresolved *(recommended)*, or (B) map them to gentle smile and neutral with a disclosure.
5. **Hair colors:** (A) approve all 35 *(recommended)*, or (B) pilot the 23 blonde and red values first.

The full report is saved at `/home/renriquez/.claude/plans/read-only-council-round1-repo-vast-karp.md`. I made no other writes, no generations and no config reads.
