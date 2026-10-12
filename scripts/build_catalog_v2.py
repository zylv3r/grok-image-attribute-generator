"""Deterministic offline v2 catalog build. Never rewrites v1 or invokes a provider."""
from pathlib import Path
import copy
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {
    'hair': 'Hair', 'face_expression_makeup': 'Face, Expression & Makeup', 'eyes': 'Eyes',
    'skin_pigmentation': 'Skin & Pigmentation', 'body_avatar': 'Body & Avatar',
    'wardrobe': 'Wardrobe', 'poses': 'Poses', 'identity_controls': 'Identity Controls',
    'photography': 'Photography', 'editorial_recipes': 'Editorial Recipes',
    'lighting_composition': 'Lighting & Composition', 'environment_props': 'Environment & Props',
}


def rows(text):
    return [line.split('|', 1) for line in text.strip().splitlines() if line.strip()]


def value(vid, meaning, **extra):
    return dict(id=vid, name=vid.replace('_', ' ').title(), description=meaning[0].upper()+meaning[1:]+'.', steers=meaning, **extra)


def attr(aid, title, description, values, **extra):
    return dict(id=aid, name=title, description=description, type='exclusive', values=values, **extra)


HAIR = '''one_length|a uniform perimeter with no graduated internal layers
blunt_bob|a jaw-length bob with a sharp horizontal perimeter
graduated_bob|a bob with softly rising back layers and longer front edges
stacked_bob|a bob with closely stacked nape layers building back volume
long_bob|a shoulder-skimming bob with an even perimeter
long_layers|long graduated internal layers without changing the selected perimeter
short_layers|short internal layers producing a stepped crown outline
shag|distributed feathered layers with a broken perimeter
wolf_cut|short crown layers transitioning into a noticeably longer nape
butterfly_cut|face-framing shorter layers separated from long lower layers
pixie|a closely cropped nape and sides with a short shaped crown
bixie|a short bob perimeter combined with pixie-like crown layers
hush_cut|soft tapered layers around the ears with a wispy perimeter
hime_cut|distinct blunt cheek-length side panels beside a long back section
v_cut|a back perimeter forming a clear centered V
u_cut|a back perimeter forming a gently rounded U
tapered_cut|progressively shorter hair toward the nape and temples
undercut|closely clipped lower sides beneath a longer upper section
mullet|short front and side sections with a visibly longer back
buzz_cut|uniform close clipping over the scalp
pin_straight|straight parallel strands with no visible bends
straight_natural|mostly aligned strands with small natural bends
gentle_waves|broad low-amplitude S bends through the strands
pronounced_waves|deep repeating S bends without closed ringlets
beach_waves|irregular loose bends with separated strand groups
loose_ringlets|large open spiral curls separated into soft clusters
defined_curls|distinct medium spiral loops with visible curl boundaries
tight_curls|small compact ringlets with a repeating rounded contour
tight_coils|very small helical coils with a densely textured surface
worn_down|hair released freely below the crown without gathering
half_up|upper hair gathered behind the crown while lower lengths remain loose
half_up_bun|upper hair wrapped into a small crown bun with lower lengths loose
low_bun|hair gathered into a compact coil at the nape
high_bun|hair gathered into a compact coil above the crown
messy_bun|hair gathered into a loose coil with visibly escaping ends
low_ponytail|hair gathered into one tail secured at the nape
high_ponytail|hair gathered into one tail secured high on the crown
side_ponytail|hair gathered into one tail secured beside the neck
bubble_ponytail|one tail divided by spaced bands into rounded sections
single_braid|hair interwoven into one three-strand braid
twin_braids|hair separated into two independently interwoven braids
fishtail_braid|one braid formed from narrow alternating outer sections
dutch_braids|two raised braids interwoven outward along the scalp
braided_crown|a scalp-following braid crossing the upper crown
halo_braid|a continuous braid encircling the head above the hairline
french_twist|hair folded into a vertical roll at the back
chignon|hair folded into a low broad knot behind the neck
pinned_updo|lengths lifted and secured into several visible folded sections
center|a scalp part centered between the temples
left|a scalp part on the subject left side
right|a scalp part on the subject right side
deep_side|a far lateral part with a broad swept section across the crown
no_visible_part|hair directed back without an exposed scalp part
natural|a matte natural strand finish with small flyaways
sleek|aligned compact strands with suppressed flyaways
glossy|increased specular strand sheen without changing the cut
tousled|irregular strand direction and small lifted flyaways
airy_volume|lifted roots and loosely separated strands
defined_separation|distinct strand clusters with clear edges
uniform|one uniform pigment from roots to ends
highlights|broad lighter strands distributed through the selected base pigment
babylights|very fine lighter strands sparsely distributed through the selected pigment
lowlights|darker strands distributed within the selected lighter base pigment
balayage|hand-painted lighter outer sections with a soft transition from roots
ombre|a horizontal transition from darker roots to lighter ends
root_shadow|a darker root zone fading into the selected length pigment
face_frame_brightening|lighter strands limited to the front face-framing sections
salt_and_pepper_distribution|intermixed dark and gray strands with individually visible boundaries'''
HAIR_MEANINGS = dict(rows(HAIR))

EXPRESSION_MOVEMENTS = '''neutral_relaxed|relaxed lips meeting without pressure, level brows and open resting lids
poised_neutral|level mouth corners, gently held closed lips and slightly lifted upper lids
gentle_closed_lip_smile|slightly lifted mouth corners with lips closed and relaxed cheeks
warm_closed_lip_smile|lifted closed-lip corners with rounded raised cheeks and subtle lid narrowing
broad_smile|widely lifted mouth corners with stretched lips and prominently raised cheeks
open_lip_smile|lifted mouth corners with a small gap between the lips
teeth_visible_smile|lifted mouth corners and parted lips revealing the upper teeth
dimpled_smile|closed lifted mouth corners with small cheek indentations
smiling_eyes|raised cheeks narrowing lower lids while the mouth remains nearly level
asymmetric_smile|one mouth corner lifted more strongly than the other
left_smirk|only the subject left mouth corner lifted with other muscles relaxed
right_smirk|only the subject right mouth corner lifted with other muscles relaxed
playful_grin|stretched corners and a narrow tooth-revealing lip opening
soft_laugh|rounded raised cheeks and moderately open mouth with visible upper teeth
open_laugh|widely open mouth with lifted cheeks and narrowed lids
eyes_closed_laugh|closed lids, lifted cheeks and open laughing mouth
serene_closed_eyes|both lids closed with smooth brows and a relaxed closed mouth
softened_lids|upper lids lowered slightly with relaxed brows and mouth
focused_squint|both lids narrowed with a lightly tense lower lid edge
smiling_squint|narrowed lids with lifted cheeks and closed smiling lips
wide_eyes|upper lids lifted exposing more iris with brows held level
both_brows_raised|both brows lifted while lips remain relaxed and closed
left_brow_raised|subject left brow lifted while the right brow stays level
right_brow_raised|subject right brow lifted while the left brow stays level
brows_knit|inner brow ends drawn together over a relaxed mouth
brow_concentration|inner brows lowered slightly with a small vertical crease
lips_lightly_pressed|lips meeting with gentle pressure and smooth cheeks
lips_firmly_pressed|lips compressed into a narrow line with flattened mouth corners
pursed_lips|lips drawn inward and forward into a small rounded aperture
slight_pout|lower lip projected subtly with relaxed level brows
parted_lips|relaxed lips separated by a narrow vertical opening
lower_lip_tucked|lower lip rolled slightly inward below the upper lip
mouth_corners_down|both mouth corners lowered slightly without changing the gaze
surprised_open_mouth|rounded open mouth, raised brows and lifted upper lids
soft_awe|small open mouth with gently lifted brows and relaxed cheeks
concerned_brow_mouth|inner brows lifted and drawn together with slightly downturned mouth corners
determined_press|firmly pressed lips with lowered inner brows
skeptical_brow|one raised brow combined with slightly compressed lips
weary_lids|lowered upper lids with a relaxed straight mouth
melancholic_soft|slightly lifted inner brows and gently lowered closed mouth corners
hesitant_smile|a small closed smile with unequal corners and slightly raised inner brows
left_wink|subject left lid closed while the right eye remains open
right_wink|subject right lid closed while the left eye remains open'''

# These are garment geometry/material definitions, not branding or authenticity claims.
WARDROBE_MEANINGS = '''sheath|straight fitted dress perimeter following the torso with movement ease
shift|straight dress falling loosely from the shoulders without a shaped waist
a_line|dress widening gradually from the waist toward the hem
fit_and_flare|fitted bodice meeting a distinctly flared skirt
wrap|overlapping dress front secured at the waist
empire|dress skirt beginning immediately below the bust
column|long dress with a narrow continuous vertical outline
mermaid|close dress fit through the knees with a pronounced lower flare
trumpet|dress widening gradually from the mid-thigh
princess_seam|dress shaped through long vertical curved panel seams
tent|dress widening freely from the shoulders without waist shaping
trapeze|dress with a narrow shoulder span and strongly flared body
cocoon|rounded dress volume narrowing at the hem
tunic|long straight garment ending below the hips
smock|loose dress gathered from a high yoke
bias_cut|fabric cut diagonally across its grain for a fluid body-following drape
ballgown|fitted bodice meeting a full floor-length skirt
asymmetric_drape|dress folds gathered to one side with unequal side contours
tiered|garment volume built from stacked gathered horizontal panels
shirt_dress|button-front dress with a shirt-style bodice
slip_dress|opaque narrow-strap dress with a simple bias drape
tea_dress|fitted-waist dress with a softly flared mid-calf skirt
sundress|light opaque sleeveless dress with a relaxed summer-weight skirt
sweater_dress|dress made from substantial opaque knitted fabric
pinafore_dress|sleeveless bib-front dress layered over a separate top
blazer_dress|dress with a tailored lapel and jacket-like front
coat_dress|closed tailored dress with coat-like panel construction
kaftan_dress|loose full-length dress with broad continuous sleeve panels
cheongsam_inspired|high stand-collar fitted dress with a diagonal front closure
sari_inspired_drape|opaque garment with a separate diagonal shoulder drape
crewneck_tee|simple opaque knit T-shirt body with a round close neck
vneck_tee|opaque knit T-shirt body with a V neck
 tank|opaque sleeveless knit top with substantial shoulder straps
camisole_opaque|opaque lightweight top with narrow secure straps
shell_top|simple sleeveless woven top with a smooth fitted body
button_front_shirt|woven shirt with a full vertical button placket
oxford_shirt|woven shirt with an oxford basket texture and structured body
popover_shirt|woven shirt with a partial front placket pulled over the head
blouse|soft woven top with gathered ease through the body
peasant_blouse|loose woven blouse gathered at its neckline and cuffs
wrap_top|top with overlapping front panels tied at the waist
peplum_top|fitted top with a short flared lower panel at the waist
knit_pullover|opaque knitted upper garment pulled over the head
cardigan|knitted upper layer opening down the front
sweatshirt|opaque fleece-backed knit top with ribbed edges
hoodie|opaque sweatshirt body with an attached hood
polo|knit top with a short button placket and folded collar
henley|knit top with a short button placket and collarless round neck
bodysuit_opaque|opaque fitted top anchored beneath the waistband
halter_top|opaque top supported around the neck with secure upper coverage
tube_top_secure|opaque strapless top with secure structured upper support
bustier_style_opaque_top|opaque structured top with supportive vertical bodice seams
vest_top|sleeveless tailored upper garment opening at the front
crew|close round neckline at the base of the neck
round|curved neckline set below the base of the neck
scoop|wide curved neckline dipping below the collarbones
v|two sloping neckline edges meeting at a secure V
square|horizontal lower neckline joined to straight vertical sides
sweetheart|two curved neckline lobes meeting at a shallow center dip
boat|broad shallow neckline spanning the collarbones
cowl|neckline formed by loose folded fabric
halter|neckline rising around the neck from angled armhole edges
off_shoulder|secure neckline sitting horizontally below both shoulders
one_shoulder|secure neckline crossing diagonally to one supported shoulder
asymmetric|neckline with unequal left and right edges
keyhole_secure|small enclosed opening below a securely covered neck
mockneck|short close upright neckline below the jaw
turtleneck|tall folded close knit neckline around the neck
jewel|round woven neckline immediately around the neck base
strapless_secure|secure structured upper edge without shoulder straps
none|absence of this garment feature without changing other selected details
shirt_point|folded collar ending in two pointed front tips
spread|folded collar with widely separated front points
button_down|folded collar with both points fastened to the shirt
mandarin|short upright collar with separated front edges
stand|upright collar encircling the neck without folded points
peter_pan|flat collar with rounded front lobes
shawl|continuous rounded collar folded into the front opening
notched|lapel and collar meeting at distinct angular notches
sailor|broad flat collar with a square back panel
funnel|wide upright collar tapering toward the neck
pussy_bow|soft collar extensions tied into a front bow
straight|parallel garment edges with an even width
fitted|garment contour following the body with comfortable movement ease
raglan|sleeve panel extending diagonally from underarm to neckline
dolman|broad sleeve continuing from a low underarm
kimono|straight sleeve cut continuously with the upper body panel
batwing|very deep sleeve underarm narrowing toward the wrist
puff|sleeve volume gathered into a rounded upper-arm section
bishop|full sleeve narrowing into a gathered wrist cuff
balloon|rounded sleeve volume gathered at both ends
bell|sleeve widening toward the open cuff
flutter|short loose sleeve draping in soft rippling folds
cap|very short sleeve covering only the shoulder edge
petal|short sleeve formed by overlapping curved panels
leg_of_mutton|large upper sleeve tapering sharply below the elbow
lantern|sleeve with a rounded central section between narrower seams
split|garment edge opening into two separate supported panels
cape|outer layer suspended from the shoulders with open arm access
short|sleeve ending on the upper arm
elbow|sleeve ending at the elbow crease
three_quarter|sleeve ending halfway along the forearm
bracelet|sleeve ending above the wrist bone
long|sleeve ending at the wrist
extended|sleeve cuff extending partly over the hand
low|waistband sitting securely on the upper hips
mid|waistband between the hip crest and natural waist
high|waistband aligned above the natural waist
ultra_high|waistband rising well above the natural waist
plain|smooth unadorned waistband without gathers
belted|waistband secured by a distinct external belt
elastic|waistband gently gathered over covered elastic
drawstring|waistband gathered by a visible tied cord
paperbag|gathered waistband with a ruffled upper extension
yoke|shaped waistband panel extending below the waist
wide|broad waistband spanning several centimeters vertically
contoured|curved waistband shaped to follow the waist
above_knee|hem ending clearly above the knee
knee|hem ending at the center of the knee
below_knee|hem ending just below the knee
mid_calf|hem ending halfway between knee and ankle
ankle|hem ending at the ankle bone
floor|hem ending near the floor without dragging
rounded|hem edge sweeping upward in a smooth curve at the sides
high_low|hem distinctly shorter in front than at the back
handkerchief|hem falling into several pointed corners
scalloped|hem finished with repeating rounded lobes
ruffled|hem finished with a separate gathered fabric strip
slim|trouser legs closely shaped with small movement ease
skinny|trouser legs closely following both thigh and calf
cigarette|narrow straight trouser legs ending near the ankle
tapered|trouser legs progressively narrowing toward the ankle
wide_leg|trouser legs broad from hip to hem
palazzo|very broad fluid trouser legs with deep vertical drape
flare|trouser legs widening substantially below the knee
bootcut|trouser legs widening slightly below the knee
culotte|broad cropped trouser legs ending below the knee
barrel|trouser legs bowed outward at the thigh and narrowing at the ankle
peg|trouser legs full at the hip and sharply tapered below
harem|trousers with a lowered crotch and gathered ankle hems
jogger|relaxed trouser legs gathered into ankle cuffs
cargo|relaxed trousers with substantial side thigh pockets
carpenter|straight work-style trousers with tool-loop construction
sailor|broad trousers with a front buttoned panel
pencil|skirt tapering subtly toward the knee with walking ease
circle|skirt cut from a full circular panel with radial folds
half_circle|skirt cut from a half-circle panel with moderate flare
bias|skirt cut diagonally to the grain for a soft contour-following drape
tulip|skirt with overlapping curved front panels tapering toward the hem
godet|triangular fabric inserts increasing lower garment flare
gored|skirt built from shaped vertical panels increasing hem fullness
sarong_inspired|opaque skirt secured by an overlapping tied side panel
draped|garment fabric gathered into flowing diagonal folds
kilt_inspired|skirt with a flat overlapping front and pleated sides
utility|jumpsuit with a practical front closure and substantial pockets
boiler_suit|one-piece long-sleeve garment with workwear panel construction
romper|one-piece upper garment joined to shorts
bermuda|shorts ending just above the knees
culotte_short|very wide shorts with a skirt-like drape
athletic|loose opaque shorts with a secure elastic waistband
cycling_opaque|opaque fitted shorts extending to mid-thigh
skort|shorts covered by an overlapping skirt panel
blazer|tailored jacket with lapels and structured shoulders
double_breasted_blazer|tailored jacket with two overlapping button columns
tuxedo_jacket|tailored jacket with satin-faced lapels
trench|belted coat with overlapping front and storm flaps
mac_coat|clean single-breasted raincoat with a straight body
pea_coat|short double-breasted coat with broad lapels
overcoat|substantial long tailored coat worn above other layers
wrap_coat|coat with overlapping panels tied by a waist belt
cocoon_coat|coat with rounded body volume narrowing at the hem
duffle_coat|hooded substantial coat with toggle fastenings
parka|hooded weather coat with a longer protective body
puffer|insulated jacket with visibly rounded stitched chambers
quilted_jacket|jacket with a thin padded surface divided by stitched lines
bomber|short jacket with gathered ribbed cuffs and hem
harrington|short zip jacket with a standing collar and plain body
biker_jacket|close leather-style jacket with an asymmetric front closure
denim_jacket|short structured jacket with yoke seams and chest pockets
field_jacket|hip-length jacket with four substantial front pockets
utility_jacket|straight jacket with practical patch pockets
cropped_jacket|jacket ending above the natural waist
bolero|short open jacket covering shoulders and upper arms
poncho|loose outer panel with a central head opening
gilet|sleeveless outer layer covering the torso
duster|light long outer layer falling near the ankles
chore_jacket|straight work-style jacket with a simple buttoned front
princess_seams|curving vertical seams shaping the garment through the torso
darts|small tapered sewn folds shaping local garment volume
knife_pleats|parallel fabric folds all pressed in one direction
box_pleats|paired opposing fabric folds creating broad flat pleats
inverted_pleats|opposing folds meeting inward at a central line
gathers|fabric distributed into many small unpressed folds
smocking|stitched gathered fabric forming a flexible patterned panel
ruching|fabric gathered along a seam into dense soft folds
shirring|parallel elastic gathering lines compressing a fabric panel
tucks|narrow sewn folds forming straight raised lines
godets|triangular inserted panels expanding the garment hem
ruffles|gathered strips attached along a garment seam
flounces|circular-cut fabric strips falling in soft curved waves
piping|narrow raised corded trim outlining garment seams
topstitch|visible stitching parallel to the garment seam
patch_pockets|separate pocket panels stitched onto the outer garment surface
welt_pockets|slit pockets finished with narrow folded fabric edges
cargo_pockets|large external pockets with expanding sides and flaps
epaulettes|narrow buttoned fabric tabs across the shoulders
pull_on|garment opening without a separate mechanical fastening
buttons|front opening secured by individual buttons through holes
zipper|opening secured by a continuous interlocking zip
snaps|opening secured by paired press-stud fastenings
hooks|opening secured by small hook-and-eye pairs
tie|opening secured by knotted fabric ties
lace_up|opening secured by cord threaded through paired eyelets
belted_wrap|overlapping garment panels secured by a tied belt
toggle|opening secured by loop-and-toggle fastenings
asymmetric_zip|zip opening positioned diagonally across the front
cotton_poplin|smooth tightly woven cotton with a fine crosswise rib
cotton_twill|cotton with a visible diagonal woven rib
denim|substantial cotton with a contrasting warp and pale diagonal weft
linen|matte woven linen with irregular slubs and visible creasing
wool_flannel|soft wool fabric with a lightly brushed matte surface
wool_gabardine|dense wool twill with a smooth fine diagonal rib
tweed|coarse woven wool with mixed flecked yarns
velvet|dense short pile with direction-dependent deep highlights
velour|soft knit pile with a flexible rounded drape
corduroy|parallel raised pile ridges separated by narrow channels
opaque_satin|fully opaque fabric with a smooth directional satin sheen
opaque_silk_twill|fully opaque silk-like twill with fine diagonal sheen
crepe|fine pebbled fabric with a matte fluid drape
jacquard|woven motif formed through varying yarn interlacings
brocade|raised woven motifs on a substantial textile base
jersey|smooth knit fabric with slight stretch and soft drape
rib_knit|knit fabric with repeating raised vertical ribs
cable_knit|knit fabric with raised interlaced cable motifs
interlock|dense smooth double knit with an opaque stable body
fleece|soft insulating knit with a brushed surface
boucle|textile with small looped yarns and a nubbly surface
leather|smooth opaque hide-like surface with subtle natural grain
suede|matte fine-napped hide-like surface
technical_nylon|smooth lightweight opaque technical weave
lined_mesh|open mesh surface backed by a fully opaque lining
lined_lace|open lace motif backed by a fully opaque lining
solid|uniform garment color without a repeating printed motif
pinstripe|narrow evenly spaced parallel garment stripes
wide_stripe|broad alternating parallel garment stripes
gingham|small regular two-color checked weave
tartan|crossing multi-width stripes forming repeated checked blocks
windowpane|thin widely spaced lines forming large square checks
houndstooth|small interlocking broken-check motifs
herringbone|alternating diagonal lines forming repeated V shapes
polka_dot|regular medium circular dots on a plain textile base
micro_dot|dense small circular dots on a plain textile base
floral|repeating stylized botanical flowers on the textile
paisley|curved teardrop motifs with internal decorative detail
geometric|repeating angular textile shapes with clear edges
abstract|irregular nonrepresentational textile marks
animal_inspired|stylized spotted or striped motifs inspired by animal coats
color_block|large adjacent garment panels with distinct colors
ombre|gradual garment pigment transition across the selected textile
jacquard_motif|repeating woven motif with subtle texture contrast
tailored|garment shaped by structured seams with controlled ease
regular|garment with moderate consistent movement ease
relaxed|garment falling with generous soft movement ease
oversized|garment intentionally wider and longer than ordinary ease
boxy|garment body with a broad straight rectangular outline
ballet_flat|flat closed shoe with a low rounded opening
mary_jane_flat|flat closed shoe with a strap crossing the instep
loafer|slip-on flat shoe with a structured low vamp
moccasin|soft shoe with a visibly stitched wraparound upper
oxford|lace-up shoe with closed lacing quarters
derby|lace-up shoe with open lacing quarters
brogue|structured shoe with decorative punched edging
mule|shoe with an open back and closed front upper
clog|shoe with a substantial rigid sole and broad closed upper
slingback|shoe with a strap securing the heel from behind
court_pump|closed dress shoe with a low vamp and shaped heel
mary_jane_pump|closed dress shoe with an instep strap and raised heel
ankle_strap_sandal|open shoe secured by a distinct ankle strap
tstrap_sandal|open shoe with a central strap joining the ankle strap
fisherman_sandal|open shoe with interwoven substantial straps
espadrille|shoe with a woven rope-like sole edge
wedge|continuous heel wedge supporting the entire rear foot
platform|shoe with a thick elevated forefoot sole
low_top_sneaker|casual lace-up shoe ending below the ankle
high_top_sneaker|casual lace-up shoe extending above the ankle
running_shoe|athletic shoe with a segmented cushioned sole
ankle_boot|closed boot ending just above the ankle
chelsea_boot|ankle boot with elastic side panels
chukka_boot|ankle boot with a low two-eyelet lacing front
lace_up_boot|boot with a continuous lace-up front
cowboy_boot|boot with an angled heel and shaped western-style shaft
knee_high_boot|boot shaft ending near the knee
riding_boot|knee-length boot with a low flat heel and plain shaft
over_knee_boot|boot shaft extending above the knee
flat|heel with almost no rise above the forefoot
kitten|short narrow heel with a gentle curved profile
block|heel with a broad square support surface
cone|heel narrowing gradually from a broad top
stiletto|tall narrow heel with a small ground-contact tip'''
WARDROBE_MEANINGS = {k.strip(): v for k,v in rows(WARDROBE_MEANINGS)}

# Primary support, balance and movement configurations; modifiers live separately.
POSES = '''standing_neutral|stand with weight evenly shared between two parallel feet
standing_left_support|stand with weight over the left leg and the right foot resting lightly
standing_right_support|stand with weight over the right leg and the left foot resting lightly
standing_left_heel_lift|stand with the left heel lifted while the right foot supports the body
standing_right_heel_lift|stand with the right heel lifted while the left foot supports the body
standing_left_toe_out|stand with the left foot turned outward and the right foot straight
standing_right_toe_out|stand with the right foot turned outward and the left foot straight
standing_offset_feet|stand with one foot half a foot-length behind the other
standing_parallel_wide|stand with parallel feet slightly wider than the shoulders
standing_cross_step|stand at the end of a crossing step with one foot diagonally ahead
standing_left_knee_soft|stand with the left knee softly bent and the right leg straight
standing_right_knee_soft|stand with the right knee softly bent and the left leg straight
standing_toes_in|stand with toes slightly inward and heels separated naturally
standing_both_heels_up|balance briefly on both forefeet with heels raised slightly
standing_left_lateral_step|transfer weight sideways onto the left foot with the right foot trailing
standing_right_lateral_step|transfer weight sideways onto the right foot with the left foot trailing
standing_forward_transfer|transfer body weight onto a forward foot with the rear heel rising
standing_backward_transfer|transfer weight onto a rear foot while the front toes remain grounded
standing_counterlean|hold a small sideways torso counterlean above a stable wide stance
standing_forward_hinge|hinge the torso slightly forward from the hips with knees unlocked
standing_sidebend_left|bend the torso gently left above a stable parallel stance
standing_sidebend_right|bend the torso gently right above a stable parallel stance
standing_twist_left|rotate the torso left while hips and feet stay forward
standing_twist_right|rotate the torso right while hips and feet stay forward
walking_heel_contact|walk at the instant the leading heel touches the ground
walking_midstance|walk with the supporting foot flat and the opposite leg passing forward
walking_toe_release|walk with the trailing toes leaving the ground
walking_slow_long|take a slow long stride with an upright torso and low arm swing
walking_brisk_short|take a brisk short stride with bent elbows and a small forward lean
walking_diagonal_left|walk diagonally toward camera left with alternating balanced steps
walking_diagonal_right|walk diagonally toward camera right with alternating balanced steps
walking_backward|take a careful backward step with the rear toes touching first
walking_sideways_left|step laterally left without crossing the feet
walking_sideways_right|step laterally right without crossing the feet
walking_crossover_left|step the right foot across the left in a controlled leftward movement
walking_crossover_right|step the left foot across the right in a controlled rightward movement
walking_arc_left|follow a shallow leftward arc with the torso turning through the step
walking_arc_right|follow a shallow rightward arc with the torso turning through the step
walking_stop|finish a walk with both feet settling and the torso decelerating upright
walking_start|begin a forward step with one heel lifting behind
walking_half_turn|turn halfway around during a slow grounded step
walking_pivot_front|pivot to face forward on a planted foot with the other foot repositioning
walking_pivot_back|pivot away on a planted foot with the free foot moving behind
walking_careful_narrow|walk with small steps along a narrow imagined path
walking_toe_lead|take a slow step with the leading toes contacting before the heel
walking_rise_step|rise slightly onto the forefoot during a light walking step
seated_parallel_feet|sit upright with knees parallel and both feet flat
seated_left_leg_cross|sit with the left thigh crossed over the right and relaxed ankles
seated_right_leg_cross|sit with the right thigh crossed over the left and relaxed ankles
seated_left_ankle_over|sit with the left ankle crossed over the right lower leg
seated_right_ankle_over|sit with the right ankle crossed over the left lower leg
seated_feet_apart|sit with feet comfortably apart and knees aligned above the feet
seated_feet_tucked|sit with both feet drawn slightly beneath the seat
seated_one_foot_extended|sit with one foot extended forward and the other beneath the knee
seated_edge_upright|sit on the front edge of a stable seat with an upright spine
seated_edge_forward|sit on the seat edge with a gentle hip hinge forward
seated_supported_recline|sit against a supporting backrest with feet planted
seated_side_left|sit sideways with both knees directed left of the seat
seated_side_right|sit sideways with both knees directed right of the seat
seated_twist_left|sit with hips forward and torso rotated gently left
seated_twist_right|sit with hips forward and torso rotated gently right
seated_left_knee_raised|sit on a low support with the left knee raised and right foot lower
seated_right_knee_raised|sit on a low support with the right knee raised and left foot lower
seated_lowering|lower into a seat with hips moving back and knees flexing
seated_rising|rise from a seat with feet planted and torso leaning forward
seated_scoot_left|shift seated weight left while keeping both feet grounded
seated_scoot_right|shift seated weight right while keeping both feet grounded
seated_backless_balance|balance upright on a backless seat with equal weight at the hips
floor_crosslegged|sit on the floor with shins crossed and torso upright
floor_left_sidefold|sit on the floor with both lower legs folded to the left
floor_right_sidefold|sit on the floor with both lower legs folded to the right
floor_legs_forward|sit on the floor with both legs extended forward and knees relaxed
floor_one_knee_up|sit on the floor with one knee raised and the other leg folded
floor_both_knees_up|sit on the floor with both knees raised and feet planted
floor_left_support|sit with knees bent and weight supported partly by the left palm behind
floor_right_support|sit with knees bent and weight supported partly by the right palm behind
floor_backward_support|sit with both palms behind the hips and bent knees grounded
floor_side_recline_left|rest on the left forearm with hips on the floor and knees bent
floor_side_recline_right|rest on the right forearm with hips on the floor and knees bent
kneeling_both_upright|kneel on both knees with hips lifted above the heels
kneeling_both_low|kneel with hips resting gently above the heels
kneeling_left_high|kneel on the left knee with the right foot forward and right knee raised
kneeling_right_high|kneel on the right knee with the left foot forward and left knee raised
kneeling_left_lateral|kneel on the left knee with the right foot planted to the side
kneeling_right_lateral|kneel on the right knee with the left foot planted to the side
kneeling_half_rise|rise from one knee with the front foot supporting the lifting torso
kneeling_lowering|lower carefully toward one knee while the front foot remains flat
kneeling_torso_turn_left|kneel on both knees while turning the torso gently left
kneeling_torso_turn_right|kneel on both knees while turning the torso gently right
crouch_parallel|crouch with both feet flat and knees tracking over the toes
crouch_left_support|crouch with weight mainly over the left foot and right heel raised
crouch_right_support|crouch with weight mainly over the right foot and left heel raised
crouch_wide|crouch with feet wide and knees opening naturally
crouch_shallow|bend both knees into a shallow crouch with an upright torso
crouch_deep|lower into a deeper crouch with the hips near the heels
crouch_side_left|lower weight over the left leg while the right leg extends sideways
crouch_side_right|lower weight over the right leg while the left leg extends sideways
crouch_rising|straighten from a crouch with heels grounded and torso lifting
lunge_left_forward|place the left foot forward with the left knee bent and rear leg extended
lunge_right_forward|place the right foot forward with the right knee bent and rear leg extended
lunge_left_side|bend the left knee into a lateral lunge with the right leg extended
lunge_right_side|bend the right knee into a lateral lunge with the left leg extended
balance_left_knee_lift|balance on the left leg with the right knee lifted slightly
balance_right_knee_lift|balance on the right leg with the left knee lifted slightly
balance_left_back_leg|balance on the left foot with the right toes lifted just behind
balance_right_back_leg|balance on the right foot with the left toes lifted just behind
balance_left_forward_leg|balance on the left foot with the right leg extended slightly forward
balance_right_forward_leg|balance on the right foot with the left leg extended slightly forward
balance_left_side_leg|balance on the left foot with the right leg lifted slightly sideways
balance_right_side_leg|balance on the right foot with the left leg lifted slightly sideways
pivot_left_toe|pivot left on the ball of one foot while the other heel shifts
pivot_right_toe|pivot right on the ball of one foot while the other heel shifts
turn_left_settle|settle after a left turn with both feet grounded and torso following
turn_right_settle|settle after a right turn with both feet grounded and torso following
stretch_left_calf|place the left foot back with the left heel grounded and front knee bent
stretch_right_calf|place the right foot back with the right heel grounded and front knee bent
stretch_forward_fold|hinge forward with knees soft and the spine naturally lengthened
stretch_side_left|reach the right arm overhead during a gentle left side bend
stretch_side_right|reach the left arm overhead during a gentle right side bend
stretch_chest_open|stand with shoulders opening and arms extending slightly behind
stretch_upper_back|stand with forearms forward and upper back gently rounded
stretch_left_quad|balance on the right leg while holding the left foot behind without strain
stretch_right_quad|balance on the left leg while holding the right foot behind without strain'''

GESTURES = '''relaxed|let both arms hang naturally with fingers loosely curved
hands_waist|rest both palms lightly against the waist without changing leg stance
left_hand_hip|rest the left hand on the hip and relax the right arm
right_hand_hip|rest the right hand on the hip and relax the left arm
clasp_front|link both hands loosely in front of the waist
clasp_back|link both hands loosely behind the lower back
folded_arms|fold arms loosely with relaxed shoulders
hand_forearm|rest one hand gently across the opposite forearm
hand_elbow|support one elbow with the opposite hand
left_wave|raise the left hand with an open palm in a small wave
right_wave|raise the right hand with an open palm in a small wave
open_palm_left|extend the left forearm with an open upward palm
open_palm_right|extend the right forearm with an open upward palm
both_palms_open|hold both hands forward with relaxed upward palms
finger_near_lips|hold one relaxed fingertip near the closed lips
hand_in_hair|raise one hand into the hair without changing its cut
hands_thighs|rest both hands flat on the upper thighs
left_arm_up|extend the left arm upward without arching the spine
right_arm_up|extend the right arm upward without arching the spine
arms_overhead|extend both arms overhead with a natural shoulder range
hand_clavicle|rest fingertips gently above the garment collarbone edge
hands_lap|rest both hands together in the lap
left_hand_cheek|rest the left fingertips lightly beside the cheek
right_hand_cheek|rest the right fingertips lightly beside the cheek'''

# Iris tint varies inside the same iris geometry; pattern is independently selected.
EYE_COLORS = '''icy_blue|very pale cool blue iris pigment
sky_blue|light clear blue iris pigment
cornflower_blue|medium slightly violet blue iris pigment
deep_blue|dark saturated blue iris pigment
steel_blue|muted medium blue iris pigment with gray undertones
gray_blue|gray dominant iris pigment with blue undertones
aqua|light blue-green iris pigment
blue_green|balanced medium blue and green iris pigment
pale_green|very light soft green iris pigment
sage_green|muted gray-green iris pigment
olive_green|green iris pigment with subdued yellow-brown undertones
emerald_green|medium saturated green iris pigment
forest_green|deep muted green iris pigment
gray_green|gray dominant iris pigment with green undertones
silver_gray|light neutral gray iris pigment
slate_gray|medium cool gray iris pigment
charcoal_gray|deep neutral gray iris pigment
honey_hazel|golden-brown iris pigment with muted green undertones
green_hazel|green dominant iris pigment with warm brown undertones
brown_hazel|brown dominant iris pigment with olive undertones
light_amber|light warm amber iris pigment
copper_amber|medium orange-brown amber iris pigment
golden_brown|light brown iris pigment with golden undertones
chestnut_brown|medium warm red-brown iris pigment
walnut_brown|medium neutral brown iris pigment
deep_brown|deep dark brown iris pigment'''

BODY_FEATURES = {
'frame': ('Skeletal Frame', {'small':'a relatively narrow adult skeletal frame','medium':'a moderate adult skeletal frame','broad':'a relatively broad adult skeletal frame'}),
'stature': ('Height', {'petite':'shorter adult stature with preserved limb proportions','average':'middle adult stature with preserved limb proportions','tall':'taller adult stature with preserved limb proportions'}),
'fullness': ('Body Fullness', {'slender':'slender soft-tissue contours through the adult torso and limbs','lean':'low soft-tissue fullness without implying muscular definition','balanced':'moderate soft-tissue fullness through torso and limbs','soft_full':'full soft contours through the torso and limbs','curved_full':'full soft contours with pronounced natural curvature'}),
'muscle_definition': ('Visible Muscle Definition', {'smooth':'smooth visible contours without pronounced muscle separation','lightly_toned':'subtle visible muscle contours in exposed arms and legs','athletically_defined':'clear visible muscle contours without changing soft-tissue fullness','strongly_defined':'pronounced visible muscle separation in arms and legs','muscular':'substantial visible muscle volume with distinct contour separation'}),
'shoulder_width': ('Shoulder Width', {'narrow':'narrow shoulder span relative to the torso','balanced':'moderate shoulder span relative to the torso','broad':'broad shoulder span relative to the torso'}),
'shoulder_slope': ('Shoulder Slope', {'gentle':'gently downward sloping shoulder line','average':'moderately sloping shoulder line','square':'near-level shoulder line without changing shoulder span'}),
'waist_definition': ('Waist Definition', {'soft':'subtle inward waist contour','moderate':'moderate inward waist contour','defined':'clear inward waist contour','strong':'pronounced but anatomically plausible inward waist contour'}),
'hip_breadth': ('Hip Breadth', {'narrow':'narrow pelvic outline relative to the torso','balanced':'moderate pelvic outline relative to the torso','wide':'broad pelvic outline relative to the torso'}),
'bust_volume': ('Clothed Bust Volume', {'very_small':'very small natural bust volume beneath opaque fitted clothing','small':'small natural bust volume beneath opaque fitted clothing','medium':'moderate natural bust volume beneath opaque fitted clothing','moderately_full':'moderately full natural bust volume beneath opaque fitted clothing','full':'full natural bust volume beneath opaque fitted clothing'}),
'thigh_volume': ('Thigh Volume', {'slender':'slender upper leg contours with unchanged leg length','lean':'lean upper leg contours with slight visible definition','balanced':'moderate upper leg fullness with unchanged leg length','full':'full upper leg soft contours with unchanged leg length','muscular':'substantial upper leg muscle contours with unchanged leg length'}),
'calf_volume': ('Calf Volume', {'slim':'slim lower leg contours with unchanged leg length','balanced':'moderate lower leg contours with unchanged leg length','full':'full lower leg contours with unchanged leg length'}),
'leg_torso_balance': ('Leg to Torso Balance', {'shorter_legs':'shorter legs relative to the torso at the selected height','balanced':'balanced leg and torso proportions at the selected height','longer_legs':'longer legs relative to the torso at the selected height'}),
'torso_length': ('Torso Length', {'short':'shorter ribcage-to-pelvis distance with unchanged total height','balanced':'moderate ribcage-to-pelvis distance with unchanged total height','long':'longer ribcage-to-pelvis distance with unchanged total height'}),
'glute_hip_fullness': ('Clothed Glute and Hip Fullness', {'subtle':'subtle rear hip projection beneath opaque fitted clothing','balanced':'moderate rear hip projection beneath opaque fitted clothing','full':'full natural rear hip projection beneath opaque fitted clothing'}),
}

MOODS = '''quiet_luxury|neutral warm grade and gently reduced contrast|neutral|gentle
sensual_luxe|warm neutral grade and rounded highlight transitions|warm_neutral|gentle
cinematic_romance|warm highlights against subtly cool shadows|warm_highlights|soft
modern_glamour|neutral color with crisp midtone separation|neutral|crisp
cool_minimal|subtle cool grade with smooth low contrast|cool|soft
warm_documentary|warm neutral grade with natural midtone separation|warm_neutral|natural
noir|monochrome grade with deep separated shadows|monochrome|high
soft_monochrome|monochrome grade with open shadows and gentle contrast|monochrome|gentle
high_key_print|neutral grade with lifted shadow tones|neutral|low
low_key_print|neutral grade with deeper shadow tones|neutral|high
muted_pastel|reduced chroma with gentle tonal separation|muted|soft
vivid_graphic|increased chroma and strong midtone contrast|vivid|high
cool_silver|cool near-neutral grade and clean highlight edges|cool|crisp
amber_evening|amber grade with smooth warm highlights|amber|gentle
teal_shadows|subtle teal shadow tint with neutral highlights|teal_shadow|natural
rose_print|subtle rose grade with open midtones|rose|soft
sepia_archive|warm monochrome grade with moderate contrast|sepia|natural
matte_editorial|muted grade with lifted black point|muted|low
rich_editorial|neutral grade with deep blacks and separated midtones|neutral|high
bleach_bypass|reduced chroma with strong shadow contrast|muted|high
blue_hour_grade|cool blue grade with restrained contrast|blue|soft
sunlit_grade|warm highlight grade with moderate contrast|warm_highlights|natural
neutral_catalog|neutral color grade with balanced contrast|neutral|natural
bold_color_print|vivid color grade with crisp tonal edges|vivid|crisp'''

NARRATIVES = '''arrival|pause after a forward step with one hand slightly raised|walking_stop|right_wave
departure|turn away while beginning a slow step|walking_start|relaxed
pause|settle into a balanced standing posture with loosely linked hands|standing_neutral|clasp_front
conversation|extend one open palm during a balanced standing pause|standing_neutral|open_palm_right
reflection|sit quietly with hands gathered in the lap|seated_parallel_feet|hands_lap
exploration|begin a diagonal step while extending an open hand|walking_diagonal_left|open_palm_left
preparation|stand upright with fingers resting beside the collarbone|standing_neutral|hand_clavicle
observation|stand on one support leg with hands loosely linked behind|standing_left_support|clasp_back
introducing|stand with both palms open at waist height|standing_neutral|both_palms_open
greeting|settle from a step and raise the left palm|walking_stop|left_wave
farewell|pivot away with the right palm raised|walking_pivot_back|right_wave
waiting|stand with offset feet and hands loosely clasped|standing_offset_feet|clasp_front
listening|sit forward with relaxed hands on thighs|seated_edge_forward|hands_thighs
explaining|sit upright with the left palm open|seated_parallel_feet|open_palm_left
considering|sit with fingertips resting beside one cheek|seated_parallel_feet|left_hand_cheek
resting|sit supported with hands gathered in the lap|seated_supported_recline|hands_lap
stretch_break|stand while extending both arms overhead|standing_neutral|arms_overhead
changing_direction|turn left through a balanced grounded pivot|pivot_left_toe|relaxed
approaching|begin a slow long forward stride|walking_slow_long|relaxed
stepping_aside|step laterally right with the left palm open|walking_sideways_right|open_palm_left
making_space|step backward with both hands open|walking_backward|both_palms_open
settling_in|lower into a seat with hands resting on thighs|seated_lowering|hands_thighs
standing_to_leave|rise from a seat with arms relaxed|seated_rising|relaxed
looking_across|sit with the torso rotated left and hands in lap|seated_twist_left|hands_lap
turning_to_listen|stand with torso rotated right and arms folded loosely|standing_twist_right|folded_arms
small_celebration|settle into a wide stable stance with the right arm raised|standing_parallel_wide|right_arm_up
quiet_resolve|stand with even support and hands linked behind|standing_neutral|clasp_back
welcoming|stand with both palms extended openly|standing_parallel_wide|both_palms_open
hesitating|hold a paused weight transfer with hands gathered in front|standing_forward_transfer|clasp_front
reorienting|settle after a right turn with one open palm|turn_right_settle|open_palm_right
kneeling_pause|rest on both knees with hands on thighs|kneeling_both_low|hands_thighs
floor_rest|sit cross-legged with hands loosely gathered|floor_crosslegged|clasp_front
writing|sit forward holding a pen against paper on a stable lap board|seated_edge_forward|relaxed
reading|sit upright holding an open book above the lap|seated_parallel_feet|hands_lap
cup_pause|stand with both hands around a cup below the face|standing_neutral|clasp_front
umbrella_wait|stand evenly while holding an umbrella shaft beside one shoulder|standing_neutral|relaxed'''
POSES += '''
floor_side_legs_left|sit with both legs extended diagonally left and torso held upright
floor_side_legs_right|sit with both legs extended diagonally right and torso held upright
floor_left_leg_folded|sit with the left leg folded inward and the right leg extended
floor_right_leg_folded|sit with the right leg folded inward and the left leg extended
floor_butterfly|sit with soles together and knees relaxed outward
floor_tall_kneel_transition|lift the hips from a heel sit into an upright two-knee kneel
floor_seated_to_kneel|move from a side-folded sit toward a supported kneeling posture
floor_kneel_to_sit|lower the hips from a kneel toward a side-folded seated posture
floor_left_knee_hug|sit with left knee raised and gently held while right leg extends
floor_right_knee_hug|sit with right knee raised and gently held while left leg extends
floor_both_knees_hug|sit with both knees drawn toward the torso and hands linked around shins
floor_long_sit_forward|sit with legs extended and torso hinging gently forward
floor_long_sit_twist_left|sit with legs extended while turning the torso slightly left
floor_long_sit_twist_right|sit with legs extended while turning the torso slightly right
kneel_left_forward_hinge|half-kneel on the left knee with torso leaning over the right thigh
kneel_right_forward_hinge|half-kneel on the right knee with torso leaning over the left thigh
kneel_left_rear_shift|half-kneel with left knee grounded and weight shifted back from right foot
kneel_right_rear_shift|half-kneel with right knee grounded and weight shifted back from left foot
kneel_wide_base|kneel upright with knees spaced comfortably apart
kneel_narrow_base|kneel upright with knees close and parallel
standing_left_backstep|settle onto the left foot after a short backward step
standing_right_backstep|settle onto the right foot after a short backward step
standing_left_diagonal_reach|stand on a stable base while hinging diagonally toward the left knee
standing_right_diagonal_reach|stand on a stable base while hinging diagonally toward the right knee
standing_feet_v|stand with heels near together and toes opened moderately outward
standing_left_front_toe|stand on the right foot while placing only the left toes forward
standing_right_front_toe|stand on the left foot while placing only the right toes forward
seated_left_heel_raise|sit with both knees forward and only the left heel lifted
seated_right_heel_raise|sit with both knees forward and only the right heel lifted
seated_both_heels_raise|sit upright with both forefeet grounded and both heels lifted
seated_diagonal_feet|sit with both feet placed diagonally to one side of the knees
seated_left_leg_extended|sit with the left knee straight and heel resting forward
seated_right_leg_extended|sit with the right knee straight and heel resting forward
seated_ankles_uncrossing|sit while separating previously crossed ankles into parallel support
seated_hips_rotating|rotate the seated hips slightly while keeping feet supported
walking_left_step_over|step the left foot across a low imagined obstacle with knee flexed
walking_right_step_over|step the right foot across a low imagined obstacle with knee flexed
walking_left_outside_step|place the left foot outward during a gentle change of direction
walking_right_outside_step|place the right foot outward during a gentle change of direction
walking_feet_collect|bring the trailing foot beside the supporting foot after a slow step'''

COLOR_PIGMENTS = '''platinum|very pale neutral blonde
icy_silver_blonde|very pale silver-cool blonde
pearl_blonde|very pale violet-neutral blonde
very_light_cream_blonde|very pale creamy neutral blonde
pale_butter_blonde|very pale soft yellow blonde
pale_champagne_blonde|very pale muted beige-gold blonde
rose_champagne_blonde|very pale rose-beige blonde
light_beige_blonde|light neutral beige blonde
ash_blonde|light muted gray-cool blonde
sandy_beige_blonde|medium light sandy beige blonde
light_golden_blonde|light warm yellow-gold blonde
golden_blonde|medium warm golden blonde
medium_honey_blonde|medium warm honey blonde
dark_neutral_blonde|dark neutral blonde
dark_ash_blonde|dark gray-cool blonde
caramel_blonde|dark warm caramel blonde
golden_bronde|deep blonde with golden brown undertones
light_peach_strawberry_blonde|light pale peach blonde with faint copper undertones
strawberry_blonde|light pink-copper blonde
dark_strawberry_blonde|medium pink-copper blonde
apricot_copper_blonde|light apricot orange-copper blonde
honey_copper_blonde|medium honey-gold blonde with copper undertones
bright_ginger|light vivid orange red
natural_copper|medium natural orange copper
deep_copper|dark saturated orange copper
light_auburn_copper|light muted auburn with copper undertones
medium_auburn|medium brown-red auburn
dark_auburn|deep brown-red auburn
copper_red|medium warm red with copper undertones
mahogany_red|dark brown-red with violet undertones
garnet_red|deep cool red with burgundy undertones
light_brown|light neutral brown
ash_brown|medium gray-cool brown
mushroom_brown|medium taupe brown
mocha_brown|medium neutral cocoa brown
warm_golden_brown|medium warm brown with golden undertones
chestnut|medium warm brown with red undertones
chocolate|deep neutral chocolate brown
espresso|very deep cool brown
soft_black|near-black with soft neutral brown undertones
jet_black|deep neutral black
white|very pale neutral white with no dark pigment
silver|light cool silver gray
steel_gray|medium dark cool steel gray'''

EXTRA_FEATURES = {
 'iris_pattern': ('eyes', 'Iris Pattern', 'Radial iris markings remain orthogonal to iris tint and pupil geometry.', '''fine_radial|fine evenly spaced radial iris fibers with fixed pupil geometry
coarse_radial|broad radial iris fibers with fixed pupil geometry
subtle_ring|a subtle concentric iris ring within fixed iris geometry
central_fleck|small tonal flecks near the pupil without changing the iris tint
outer_fleck|small tonal flecks near the outer iris without changing the iris tint
limbal_soft|a soft low-contrast limbal boundary with unchanged iris geometry
limbal_defined|a distinctly darker narrow limbal boundary with unchanged iris geometry'''),
 'pigmentation_distribution': ('skin_pigmentation', 'Pigment Distribution', 'Appearance-only distribution of visible pigment; this control makes no ancestry or clinical diagnosis claim.', '''even|visually even pigment distribution with natural skin texture
sparse_spots|sparse small darker pigment spots with unaffected surrounding texture
diffuse_patches|soft-edged darker pigment patches distributed across exposed skin
clustered_patches|localized clusters of darker pigment patches across exposed skin
contrasting_patches|clearly bounded darker pigment patches with unchanged skin texture'''),
 'freckle_location': ('skin_pigmentation', 'Freckle Location', 'Location of visible freckles is separate from their density and base skin pigment.', '''nose_cheeks|freckles distributed across the nose bridge and upper cheeks
face_scattered|freckles scattered over the visible face
shoulders|freckles limited to visible shoulder and upper arm skin
arms|freckles distributed over visible forearm skin
exposed_skin|freckles scattered across visible face and limb skin'''),
 'mole_distribution': ('skin_pigmentation', 'Visible Beauty Marks', 'Appearance-only beauty-mark distribution with no diagnostic meaning or medical inference.', '''none|no added visible beauty marks on the selected exposed skin
single_cheek|one small natural-looking beauty mark on a cheek
sparse_face|a few small natural-looking beauty marks on the face
sparse_body|a few small natural-looking beauty marks on exposed limbs
scattered|scattered small natural-looking beauty marks on exposed face and limb skin'''),
 'depigmented_patches': ('skin_pigmentation', 'Light Pigment Patches', 'Appearance-only lighter pigment patch patterns without asserting a cause or clinical diagnosis.', '''none|no added depigmented patch distribution on exposed skin
small_localized|a few small lighter pigment patches on exposed skin
hands_localized|lighter pigment patches confined to visible hand skin
face_localized|lighter pigment patches confined to visible face skin
broad_asymmetric|broad asymmetric lighter pigment patches across exposed skin
bilateral|lighter pigment patches on both sides of visible exposed skin'''),
 'garment_set': ('wardrobe', 'Garment Set', 'Select which primary garment pieces are present; cut details do not implicitly introduce extra garments.', '''dress|one opaque dress as the primary outfit with no separate top or bottom
separates_trousers|one opaque upper garment with separate trousers
separates_skirt|one opaque upper garment with a separate skirt
separates_shorts|one opaque upper garment with separate shorts
jumpsuit|one opaque full-length one-piece jumpsuit
romper|one opaque short-leg one-piece romper'''),
}

FAMILY_IDS = {
'dress_silhouette':'dress_silhouette', 'dress_family_recipes':'dress_family', 'upper_garment':'top_style',
'neckline':'neckline','collar':'collar','sleeve_shape':'sleeve_shape','sleeve_length':'sleeve_length',
'waist_rise':'waist_rise','waistband':'waistband','hem_length':'hem_length','hem_shape':'hem_shape',
'trouser_cut':'trouser_cut','skirt_cut':'skirt_cut','jumpsuit_family':'jumpsuit_family','shorts_cut':'shorts_cut',
'outerwear_family':'outerwear_style','construction_details':'construction_detail','closure':'garment_closure',
'material':'fabric_material','pattern':'garment_pattern','fit':'garment_fit','shoe_family':'shoe_style',
'heel_shape':'heel_shape','layering_recipe':'layering',
}
FAMILY_PURPOSE = {
'dress_silhouette':'Shape of the dress perimeter independently of its neckline, sleeves and textile.',
'dress_family':'Disclosed compound dress construction defaults; explicit orthogonal selections are never overwritten.',
'top_style':'Upper garment construction; compound styles disclose neckline, collar and material defaults.',
'neckline':'Opening geometry around the neck and shoulders, independent of collar and sleeve shaping.',
'collar':'Attached collar construction independently of neckline geometry where structurally compatible.',
'sleeve_shape':'Sleeve panel and volume geometry independently of selected sleeve length.',
'sleeve_length':'Distance covered along the arm, independently of sleeve panel shape.',
'waist_rise':'Waistband vertical position independently of waistband construction.',
'waistband':'Waistband construction independently of its height on the torso.',
'hem_length':'Distance from the waist to the garment lower edge independently of the hem shape.',
'hem_shape':'Lower garment edge geometry independently of its selected length.',
'trouser_cut':'Trouser leg outline; closures, material, pockets and waist details remain separately selected.',
'skirt_cut':'Skirt panel outline and construction; closures and textile remain separately selected.',
'jumpsuit_family':'Disclosed one-piece garment construction defaults that preserve explicit component locks.',
'shorts_cut':'Short-leg garment shape; material, construction and waist details are separately selected.',
'outerwear_style':'Outer garment construction independently of its textile, length and selected layering.',
'construction_detail':'Visible sewn detail selected independently of garment class and textile.',
'garment_closure':'Mechanical fastening construction independently of garment silhouette and material.',
'fabric_material':'Textile weave, fiber appearance and surface independently of garment pigment or silhouette.',
'garment_pattern':'Textile motif independently of garment class and selected base color.',
'garment_fit':'Ease through the selected garment independently of body morphology and garment class.',
'shoe_style':'Footwear upper and shaft construction, with compatible heel and material selected separately.',
'heel_shape':'Footwear support geometry independently of upper material and shoe family.',
'layering':'Explicit garment combinations permit intentional layered ensembles without accidental piece collisions.',
}


def recipe(value_record, selections, allowed=None, consequences=None):
    value_record['recipe'] = {'selections':selections, 'allowed_component_changes':list(allowed or selections),
                             'locked_fields_policy':'explicit component selections and locks take precedence; report conflicts',
                             'consequences':list(consequences or [])}
    return value_record


def baseline_requirements(category_id, attribute):
    """Human review declarations, never automated image detection or crop rules.

    Target-specific wording preserves the geometry/distribution edit allowances.
    Shared optics requirements permit only effects declared by each target contract.
    """
    aid = attribute['id']
    if category_id == 'hair':
        if attribute['preview_method'] == 'reference_edit':
            target = (
                'Only the selected hair_color_treatment distribution and its declared tones may change; non-target hair geometry and base pigment remain fixed.'
                if aid == 'hair_color_treatment' else
                f'Only the selected {aid} target and its reviewed consequences may change; non-target hair geometry, pigment and distribution remain fixed.'
            )
            return [
                'Operator reviewed the immutable original of the same approved adult woman with neutral medium-brown uniform hair pigment.',
                target,
            ]
        if aid == 'hair_color':
            return [
                'Operator reviewed a suitable immutable original of the same approved adult woman; the original hair pigment may be any suitable color.',
                'Hair recoloring is confined to the reviewed hair-pigment mask; strand texture, geometry and distribution remain unchanged.',
            ]
    if category_id == 'eyes':
        targets = {
            'eye_color': 'Iris recoloring is confined to the reviewed iris mask; iris geometry, radial pattern and eyelashes remain unchanged.',
            'iris_pattern': 'Iris-pattern edits preserve iris pigment, pupil geometry, eye geometry and eyelashes.',
            'eyelashes': 'Lash edits preserve iris pigment, iris and pupil geometry, and non-target eye geometry.',
        }
        return [
            'Operator reviewed the same approved close-eye view of the immutable original for every Eyes group, with the iris and lash boundary clearly visible.',
            f'Identity, face viewing angle and non-target eye details remain unchanged; only the selected {aid} target may change.',
            targets[aid],
        ]
    if category_id == 'face_expression_makeup':
        return [
            'Operator reviewed the immutable original of the same approved adult woman; identity and face viewing angle remain unchanged throughout this group.',
            f'Constraints apply to the selected {aid} target: only that target and its reviewed consequences may change; all non-target facial geometry, pigment, expression and gaze remain fixed.',
        ]
    if (attribute['comparison_group'] == 'photography:same_scene'
            and attribute['preview_method'] != 'control_only'):
        return [
            'Operator reviewed one approved immutable original scene shared by every rendered photography:same_scene control.',
            'Identity, scene contents, pose and camera position remain fixed; only the selected optical or photographic treatment and its declared consequences may change.',
            'Field-of-view crop, regional blur, synthetic grain and global color or tone changes are permitted only when declared by the selected target contract; no missing source detail, perspective change or camera equivalence is implied.',
        ]
    return []


def configure_local_previews(active):
    """Executable artistic recipes, never measured pigment/lens/camera equivalents."""
    sys.path.insert(0, str(ROOT))
    from comparisons import LOCAL_METHODS, METHOD_ALIASES, PARAM_DEFAULTS, local_parameter_schema

    hair = dict(rows('''platinum|e8e1ce
icy_silver_blonde|d8dfe2
pearl_blonde|e4dbd2
very_light_cream_blonde|e5d4ad
pale_butter_blonde|e2ce90
pale_champagne_blonde|d8c7a6
rose_champagne_blonde|d8b5ab
light_beige_blonde|c9b68e
ash_blonde|b5ac97
sandy_beige_blonde|bdaa81
light_golden_blonde|d0af69
golden_blonde|bd974d
medium_honey_blonde|b78e51
dark_neutral_blonde|988260
dark_ash_blonde|8b8374
caramel_blonde|ad7b47
golden_bronde|92713e
light_peach_strawberry_blonde|dda989
strawberry_blonde|c68d68
dark_strawberry_blonde|a76a48
apricot_copper_blonde|d09258
honey_copper_blonde|b98448
bright_ginger|c16c36
natural_copper|ac6038
deep_copper|87472c
light_auburn_copper|a65e45
medium_auburn|814834
dark_auburn|5c3229
copper_red|a64b2d
mahogany_red|67322e
garnet_red|592b32
light_brown|96704e
ash_brown|766c61
mushroom_brown|87796b
mocha_brown|685044
warm_golden_brown|8a6335
chestnut|75482f
chocolate|53392c
espresso|32251f
soft_black|262323
jet_black|121419
white|f1efea
silver|bfc2c5
steel_gray|7a8188'''))
    iris = dict(rows('''icy_blue|a9c8d2
sky_blue|7cacc2
cornflower_blue|658bb3
deep_blue|3d6085
steel_blue|6a8a98
gray_blue|889ca3
aqua|6ba9a6
blue_green|568e85
pale_green|b0b99a
sage_green|8f9d7b
olive_green|7e8050
emerald_green|47755e
forest_green|435f48
gray_green|8b9986
silver_gray|b1b6b3
slate_gray|7d8589
charcoal_gray|525b60
honey_hazel|a18b54
green_hazel|88895b
brown_hazel|8b704b
light_amber|b09253
copper_amber|a77942
golden_brown|91713e
chestnut_brown|795338
walnut_brown|614c38
deep_brown|403229
warm_gray|9d978a'''))
    for aid, targets in [('hair_color', hair), ('eye_color', iris)]:
        attribute = active[aid]
        assert set(targets) == {v['id'] for v in attribute['values']}, aid
        attribute['palette_policy'] = ('Illustrative natural artistic sRGB recipes; no calibrated salon, dye, '
                                       'biological pigment or brand colour precision claim.')
        for v in attribute['values']:
            v['colour'] = {'hex': '#' + targets[v['id']], 'color_space': 'sRGB', 'basis': 'illustrative_artistic_recipe'}
    fabric = active['fabric_color']
    fabric['preview_scope'] = 'swatch'
    fabric['palette_policy'] = 'Illustrative design sRGB recipes on identical woven texture; no branded dye or measured textile equivalence.'
    for v in fabric['values']:
        v['colour'] = {'hex': '#' + ''.join(f'{c:02x}' for c in v['swatch']['rgb']),
                       'color_space': 'sRGB', 'basis': 'illustrative_artistic_recipe'}
        v['preview_params'] = {'weave_scale': 4}

    def assign(aid, settings, baselines=()):
        a = active[aid]
        assert set(settings) == {v['id'] for v in a['values']}, aid
        for v in a['values']:
            v['preview_params'] = settings[v['id']]
            if v['id'] in baselines:
                v['preview_baseline'] = True
                v['preview_note'] = 'Baseline: original pixels unchanged; this choice does not sharpen or recover source detail.'

    # A declared 24 mm equivalent is only the relative crop origin. No wider
    # view, perspective, inferred sensor size or physical lens reconstruction.
    assign('focal_length', {v['id']: {'factor': int(v['id'][:-2]) / 24}
                            for v in active['focal_length']['values']}, ['24mm'])
    active['focal_length']['preview_note'] = 'Relative FOV crop from a declared 24 mm baseline; fixed viewpoint, no perspective or optical compression claim.'
    aperture_radii = {'f_1_4': 12, 'f_2': 9, 'f_2_8': 6, 'f_4': 4, 'f_5_6': 2.5,
                      'f_8': 1.5, 'f_11': .7, 'f_16': 0}
    assign('aperture', {k: {'radius': r, 'depth_assumption':
        'Declared approximation: the reviewed mask is a single out-of-focus depth plane; preserve unmasked subject, constant brightness. No scene depth is inferred.'}
        for k, r in aperture_radii.items()}, ['f_16'])
    motion = {'frozen': (0, 0), 'crisp_still': (0, 0), 'slight_fabric_blur': (3, 20),
              'walking_blur': (8, 0), 'panned': (14, 0), 'long_background': (24, 0),
              'handheld_trace': (4, 35), 'wind_trace': (10, -25)}
    motion_regions = {'frozen': 'drawn reviewed footprint; no added motion',
        'crisp_still': 'drawn reviewed footprint; retain source sharpness, no added motion',
        'slight_fabric_blur': 'moving fabric including its swept footprint',
        'walking_blur': 'moving body or garment including its swept footprint',
        'panned': 'background swept footprint only; unmasked subject stays fixed',
        'long_background': 'background moving-region swept footprint only',
        'handheld_trace': 'drawn moving-region trace footprint only; no whole-camera reconstruction',
        'wind_trace': 'wind-driven fabric or strands including their swept footprint'}
    assign('shutter_motion', {k: {'distance': d, 'direction': angle,
        'moving_region': 'Declared approximation: operator-reviewed mask covers ' + motion_regions[k]}
        for k, (d, angle) in motion.items()}, ['frozen', 'crisp_still'])
    grain = {'clean_digital': (0, 0, 0), 'fine_grain': (4, 0, 0), 'medium_grain': (9, 0, 0),
             'coarse_grain': (17, 0, 0), 'shadow_grain': (14, .9, 0),
             'soft_film_grain': (11, 0, .7), 'high_iso': (24, .4, 0), 'low_iso': (2, 0, 0)}
    assign('grain', {k: {'amount': amount, 'seed': 0, 'shadow_bias': bias, 'soften': soften}
                     for k, (amount, bias, soften) in grain.items()}, ['clean_digital'])
    focus = {'near_eye': (5, 'the near eye'), 'both_eyes': (4.5, 'both eyes'),
             'face_plane': (4, 'the face plane'), 'garment_detail': (3, 'selected garment detail'),
             'hands': (3.5, 'the hands'), 'full_subject': (2, 'the full subject'),
             'accessory': (6, 'selected accessory'), 'environmental': (1, 'the environmental context')}
    assign('focus_target', {k: {'radius': r, 'depth_assumption':
        'Declared approximation: reviewed mask covers the out-of-focus plane outside ' + target +
        '; the unmasked focus target retains original detail. No scene depth or focus recovery is inferred.'}
        for k, (r, target) in focus.items()})
    wb = {'daylight': (0, 0), 'cloudy': (.24, 0), 'shade': (.4, .02),
          'tungsten': (-.5, .03), 'cool_neutral': (-.12, 0), 'warm_neutral': (.12, 0),
          'mixed_balanced': (.04, -.08), 'custom_gray': (0, 0)}
    assign('white_balance', {k: {'temperature': t, 'tint': tint} for k, (t, tint) in wb.items()},
           ['daylight', 'custom_gray'])
    active['white_balance']['preview_note'] = 'Illustrative channel gains, not Kelvin or RAW calibration. Custom gray is the unchanged baseline until operator adjustment.'
    rolloff = {'gentle': (.35, .7), 'neutral_rolloff': (0, .7), 'film_shoulder': (.65, .6),
               'crisp_white': (.15, .88), 'protect_whites': (.8, .75),
               'glowing_edge': (.4, .82), 'matte_brights': (.9, .55), 'high_latitude': (.5, .5)}
    assign('highlight_rolloff', {k: {'strength': s, 'threshold': t} for k, (s, t) in rolloff.items()},
           ['neutral_rolloff'])
    next(v for v in active['highlight_rolloff']['values'] if v['id'] == 'glowing_edge')['preview_note'] = (
        'Highlight-only shoulder approximation; no added edge glow or bloom is allowed.')
    grades = {
        'neutral_grade': {}, 'warm_grade': {'temperature': .2}, 'cool_grade': {'temperature': -.2},
        'muted_grade': {'saturation': .65}, 'rich_grade': {'saturation': 1.3},
        'pastel_grade': {'saturation': .72, 'lift': 12},
        'earth_grade': {'saturation': .8, 'temperature': .16, 'shadow_tint': [8, 2, -8]},
        'monochrome': {'saturation': 0},
        'warm_highlights_grade': {'highlight_tint': [16, 6, -10], 'shadow_tint': [-5, 0, 7]},
        'amber_grade': {'temperature': .32, 'tint': -.08},
        'teal_shadow_grade': {'shadow_tint': [-12, 8, 10]},
        'rose_grade': {'tint': .18, 'highlight_tint': [8, -2, 3]},
        'sepia_grade': {'saturation': 0, 'temperature': .4, 'tint': -.12},
        'blue_grade': {'temperature': -.32, 'shadow_tint': [-4, 0, 9]},
    }
    assign('color_grade', {k: {**copy.deepcopy(PARAM_DEFAULTS['color_grade']), **p}
                          for k, p in grades.items()}, ['neutral_grade'])
    contrasts = {'low_contrast': {'slope': .65}, 'soft_contrast': {'slope': .85},
        'balanced_contrast': {}, 'crisp_contrast': {'slope': 1.18},
        'deep_shadows': {'slope': 1.12, 'shadows': -20},
        'lifted_shadows': {'shadows': 24}, 'soft_highlights': {'highlights': -22},
        'strong_midtones': {'midtones': .85}}
    assign('contrast', {k: {**PARAM_DEFAULTS['contrast'], **p} for k, p in contrasts.items()}, ['balanced_contrast'])
    palettes = {'analogous': (['#bd7448', '#c7a14e', '#9f5039'], .45, .95),
        'complementary': (['#b67545', '#457fb6'], .5, 1),
        'triadic': (['#b84c4c', '#4cb84c', '#4c4cb8'], .5, 1.05),
        'monochromatic': (['#8d779c'], .75, .65),
        'neutral_accent': (['#be6a46'], .2, .35),
        'warm_dominant': (['#bf7048', '#c7a24c'], .55, 1),
        'cool_dominant': (['#487eab', '#549c91'], .55, .95),
        'balanced_warm_cool': (['#b98554', '#5495a0'], .35, .85)}
    assign('palette', {k: {'anchors': anchors, 'strength': s, 'saturation': sat}
                       for k, (anchors, s, sat) in palettes.items()})
    # Preserve every selected canonical recipe component. Mix discloses the
    # strength of its combined treatment, including moods with shared components.
    mixes = {'quiet_luxury': .72, 'sensual_luxe': .8, 'cinematic_romance': .9,
        'modern_glamour': .9, 'cool_minimal': .7, 'warm_documentary': .8,
        'noir': 1, 'soft_monochrome': .9, 'high_key_print': .9, 'low_key_print': 1,
        'muted_pastel': .85, 'vivid_graphic': 1, 'cool_silver': .85,
        'amber_evening': .9, 'teal_shadows': .85, 'rose_print': .8, 'sepia_archive': 1,
        'matte_editorial': .9, 'rich_editorial': .82, 'bleach_bypass': 1,
        'blue_hour_grade': .85, 'sunlit_grade': .9, 'neutral_catalog': 1, 'bold_color_print': .9}
    by_value = {aid: {v['id']: v for v in active[aid]['values']} for aid in ('color_grade', 'contrast')}
    settings = {}
    for v in active['editorial_mood']['values']:
        selections = v['recipe']['selections']
        settings[v['id']] = {'grade': copy.deepcopy(by_value['color_grade'][selections['color_grade'][0]]['preview_params']),
                             'contrast': copy.deepcopy(by_value['contrast'][selections['contrast'][0]]['preview_params']),
                             'mix': mixes[v['id']]}
        v['preview_note'] = 'Apply disclosed canonical grade then contrast to the original, at ' + str(mixes[v['id']]) + ' recipe strength.'
    assign('editorial_mood', settings, ['neutral_catalog'])
    globals_ = {'focal_length', 'grain', 'white_balance', 'highlight_rolloff', 'color_grade',
                'contrast', 'palette', 'editorial_mood'}
    colour_tone = {'white_balance', 'highlight_rolloff', 'color_grade', 'contrast', 'palette', 'editorial_mood'}
    for aid in {'hair_color', 'eye_color', 'fabric_color', 'aperture', 'focus_target', 'shutter_motion'} | globals_:
        a = active[aid]
        a['provider_allowed'] = False
        a['preview_parameter_schema'] = local_parameter_schema(a['preview_method'])
        a['preview_method_label'] = LOCAL_METHODS[METHOD_ALIASES.get(a['preview_method'], a['preview_method'])][0]
        if aid in globals_:
            a['preview_scope'] = 'global'
            a['global_effect'] = True
            a['preview_contract']['mask'] = 'explicit global effect; whole-frame footprint permitted'
        if aid in colour_tone:
            a['preview_contract']['allowed_changes'] = ['global colour and tone']
            a['preview_contract']['locked_fields'] = [f for f in a['preview_contract']['locked_fields']
                                                       if f not in {'non_target_pigment', 'wardrobe_color'}]
        if aid in {'aperture', 'focus_target', 'shutter_motion'}:
            a['preview_scope'] = 'reviewed_localized_mask'
            a['preview_contract']['mask'] = 'operator-reviewed localized depth-plane or moving/swept footprint; declaration required'


def build(root=ROOT):
    root = Path(root)
    original = (root/'library.json').read_bytes()
    legacy = json.loads(original)
    plans = root/'docs/plans/anchored-v2'
    proposal = json.loads((plans/'HAIR-PROPOSAL.json').read_text())
    wardrobe = json.loads((plans/'WARDROBE-PROPOSAL.json').read_text())
    coverage_source = json.loads((plans/'COVERAGE.json').read_text())['coverage']
    old = {a['id']:a for c in legacy['categories'] for a in c['attributes']}
    cats = {cid:dict(id=cid,name=name,attributes=[]) for cid,name in CATEGORIES.items()}
    data = copy.deepcopy(legacy)
    data.update(schema_version=2, catalog_version=2, categories=list(cats.values()), comparison_subject_policy='All comparison baselines are approved clothed adult women; identity controls affect actual generation only.',
                thumbnail_note='Historical v1 illustrations and independent photographs remain archived. New comparisons await operator review.',
                compatibility_rules=[])
    active = {}
    def add(cid, a):
        a = copy.deepcopy(a)
        a.pop('thumbnail', None)
        for v in a['values']:
            v.pop('thumbnail', None)
            if len(v['steers'].split())<4:
                v['steers'] += ' on the selected target'
        a.update(control=a.get('control','cards'), preview_method=a.get('preview_method','reference_edit'),
                 preview_scope=a.get('preview_scope','reviewed_localized_mask'),comparison_group=a.get('comparison_group',cid+':'+a['id']),
                 preview_status='awaiting_operator_review', provider_allowed=a.get('provider_allowed',True))
        a['preview_contract'] = {'subject':'same approved adult woman', 'base':'immutable original lossless normalized PNG',
                                 'mask':'independently reviewed target footprint required before reference edit',
                                 'locked_fields':['identity','non_target_geometry','non_target_pigment','wardrobe_design','wardrobe_color','scene','pose','gaze','lighting','camera','crop'],
                                 'allowed_changes':[a['id']], 'publication':'operator accepted artifacts only'}
        cats[cid]['attributes'].append(a)
        active[a['id']]=a
        return a
    replaced = {'hair_style','hair_color','expression','eye_color','age','body_build','shoulder_shape','silhouette','face_direction',
                'ethnic_inspiration','complexion_detail','facial_balance','editorial_mood','narrative','pose',
                'dress_style','top_style','neckline','sleeve_shape','sleeve_length','waist_position','trouser_cut','skirt_cut',
                'outerwear_style','fabric_material','garment_pattern','shoe_style','hem_length','seam_detail'}
    for aid,a in old.items():
        if aid not in replaced:
            add(coverage_source[aid]['owner_category'], a)

    pigments = dict(rows(COLOR_PIGMENTS))
    colors=[]
    for family, ids in proposal['base_color_values'].items():
        for vid in ids:
            colors.append(value(vid,pigments[vid]+' uniform hair pigment, preserving strand texture and hair geometry',family=family))
    add('hair',attr('hair_color','Hair Pigment','Uniform pigment depth and undertone without changing cut, texture, distribution or length.',colors,
                    preview_method='masked_recolor',preview_scope='hair_pigment_mask'))
    for aid,spec in proposal['controls'].items():
        if aid=='hair_color' or aid in active: continue
        a=add('hair',attr(aid,aid.replace('_',' ').title(), 'Select '+aid.replace('_',' ')+' independently of the other nine hair controls; compatibility checks preserve feasible geometry and pigment distributions.',
                          [value(v,HAIR_MEANINGS[v]) for v in spec['values']]))
        if aid=='hair_color_treatment':
            a['distribution_metadata'] = {'uniform':'single pigment','salt_and_pepper_distribution':'two-tone appearance distribution; tones and fraction need mask review'}
    add('face_expression_makeup',attr('expression','Expression','Visible mouth, brow, lid and cheek movements; identity, head angle and gaze remain independently locked.',
                                     [value(v,t) for v,t in rows(EXPRESSION_MOVEMENTS)], preview_scope='expression_movement_mask'))
    add('eyes',attr('eye_color','Iris Color','Natural iris tonal tint independently of radial pattern, iris diameter, pupil size and eye geometry.',
                    [value(v,t+' with unchanged iris geometry and radial pattern') for v,t in rows(EYE_COLORS)],preview_method='masked_recolor',preview_scope='iris_only_mask'))
    # Do not let historical eyelash wording imply a selected iris pigment.
    lashes=active['eyelashes']
    lashes['preview_scope']='close_eye_lash_mask_fixed_iris_geometry_color'
    for v in lashes['values']:
        if v['id']=='dark_long':v['steers']='dark long separated natural eyelashes with unchanged iris pigment and eye geometry'
        if v['id']=='soft_dark':v['steers']='soft dark separated natural eyelashes with unchanged iris pigment and eye geometry'
        v['description']='Lash-only appearance: '+v['steers']+'.'
    for aid,(cid,title,desc,text) in EXTRA_FEATURES.items():
        add(cid,attr(aid,title,desc,[value(v,t) for v,t in rows(text)]))
    for aid,(title,meanings) in BODY_FEATURES.items():
        a=add('body_avatar',attr(aid,title,'Adult avatar appearance only. '+title+' is independently controlled without inferring health, ability, BMI or a medical measurement.',
                               [value(v,t) for v,t in meanings.items()],preview_scope='clothed_body_geometry_mask'))
        a['preview_contract']['consequences']=['body-caused opaque fabric fit','local shadows','target-caused occlusion and reveal']
    add('identity_controls',attr('age','Age','Adult generation age from 21 through 85; one canonical discrete ID for each range step, without rendered age previews.',
                                [value('age_'+str(n),f'an adult subject aged {n} with natural age-appropriate facial detail') for n in range(21,86)],
                                control='range',range={'min':21,'max':85,'step':1},default='age_24',preview_method='control_only',preview_scope='generation_control_only',provider_allowed=False))
    add('identity_controls',attr('gender','Gender / Presentation','Actual generation wording for adult gender presentation; comparison baselines remain approved adult women.',
                                [value('woman','an adult woman with feminine gender presentation'),value('man','an adult man with masculine gender presentation'),value('nonbinary','an adult nonbinary person with androgynous gender presentation')],
                                control='select',default='woman',preview_method='control_only',preview_scope='generation_control_only',provider_allowed=False))

    # One primary pose; arm gestures, orientation, head angle and prop actions are separate.
    add('poses',attr('pose','Primary Pose','Whole-body support, balance and movement configuration; arm gestures, head tilt, body orientation and prop actions have separate controls.',
                     [value(v,t) for v,t in rows(POSES)],preview_scope='full_body_pose_reviewed_footprint'))
    add('poses',attr('arm_gesture','Arm / Hand Gesture','Arm and hand configuration independently of primary body support, body orientation and head angle.',
                     [value(v,t) for v,t in rows(GESTURES)],preview_scope='arms_hands_occlusion_mask'))
    family_ids={}
    layering = {
        'single_garment': 'one primary garment ensemble without additional intentional piece layering',
        'open_outerwear': 'an unfastened outer layer revealing the selected primary garment ensemble',
        'buttoned_outerwear': 'a fastened outer layer covering part of the selected primary garment ensemble',
        'shirt_under_knit': 'a woven shirt beneath a separate knitted upper layer',
        'shirt_under_dress': 'a woven shirt beneath a sleeveless opaque dress',
        'top_over_dress': 'a separate upper garment intentionally layered over an opaque dress',
        'dress_over_trousers': 'an opaque dress intentionally layered above separate trousers',
        'vest_over_shirt': 'a separate sleeveless vest intentionally layered over a shirt',
        'coat_over_blazer': 'a separate outer coat intentionally layered over a tailored blazer',
    }
    scoped = {
      ('collar','sailor'):'broad flat collar with a square back panel',
      ('trouser_cut','balloon'):'trouser legs with rounded thigh volume gathered into narrow ankle hems',
      ('trouser_cut','tailored_pleated_recipe'):'tailored trouser construction with front knife pleats',
      ('shorts_cut','tailored'):'shorts with structured straight legs and tailored seam shaping',
      ('shorts_cut','paperbag'):'short-leg construction with a gathered extended waistband',
      ('shorts_cut','denim'):'short-leg construction using substantial opaque denim fabric',
      ('shorts_cut','cargo'):'short-leg construction with substantial side pockets',
      ('shorts_cut','sailor'):'short-leg construction with a buttoned front waistband panel',
      ('jumpsuit_family','tailored'):'one-piece trouser garment with structured seam shaping',
      ('jumpsuit_family','wide_leg'):'one-piece trouser garment with broad flowing legs',
      ('jumpsuit_family','tapered'):'one-piece trouser garment with legs narrowing at the ankle',
      ('jumpsuit_family','wrap'):'one-piece trouser garment with an overlapping upper front',
      ('jumpsuit_family','halter'):'one-piece trouser garment with a secure neck-supported upper body',
      ('heel_shape','wedge'):'continuous wedge heel supporting the entire rear foot',
      ('heel_shape','platform'):'thick elevated forefoot sole supporting a raised shoe body',
      ('construction_detail','yoke'):'shaped fabric panel connecting the garment shoulders or upper hips',
      ('waistband','yoke'):'shaped waistband panel extending below the waist',
      ('hem_shape','asymmetric'):'hem lower on one side than the other',
      ('skirt_cut','wrap'):'skirt with overlapping front panels secured at the side waist',
      ('skirt_cut','straight'):'skirt falling in a straight outline with even movement ease',
      ('skirt_cut','a_line'):'skirt widening gradually from waistband to hem',
      ('skirt_cut','mermaid'):'skirt fitted through the knees with a pronounced lower flare',
      ('skirt_cut','trumpet'):'skirt widening gradually from mid-thigh toward the hem',
      ('skirt_cut','balloon'):'skirt with rounded gathered volume narrowing at its lower edge',
      ('skirt_cut','tiered'):'skirt formed from stacked gathered horizontal panels',
    }
    for family,ids in wardrobe['families'].items():
        aid=FAMILY_IDS[family]
        # Equivalent names and cross-axis feature entries receive proposal dispositions below.
        ids=[v for v in ids if v not in {'qipao_inspired'} and not (aid=='sleeve_shape' and v=='cap')]
        vals=[]
        for vid in ids:
            meaning=scoped.get((aid,vid),layering.get(vid,WARDROBE_MEANINGS.get(vid)))
            if meaning is None:raise ValueError('missing garment meaning: '+aid+':'+vid)
            vals.append(value(vid,meaning))
        if aid in {'dress_silhouette','dress_family','top_style','trouser_cut','skirt_cut','jumpsuit_family','shorts_cut','outerwear_style','sleeve_shape','heel_shape','construction_detail'} and 'none' not in ids:
            vals.insert(0,value('none','no selected '+aid.replace('_',' ')+' component; preserve the other garment controls'))
        a=add('wardrobe',attr(aid,aid.replace('_',' ').title(),FAMILY_PURPOSE[aid],vals))
        family_ids[aid]=[v['id'] for v in vals]
        if aid=='construction_detail': a['type']='multi'
    # Remove redundant family geometry from active recipe axes; recipes disclose its actual target.
    # Garment families that mix anatomy-independent components are executable defaults.
    dress_recipes = {
      'shirt_dress':{'garment_closure':['buttons'],'collar':['shirt_point'],'dress_silhouette':['shift']},
      'slip_dress':{'dress_silhouette':['bias_cut'],'sleeve_length':['none'],'collar':['none']},
      'tea_dress':{'dress_silhouette':['fit_and_flare'],'hem_length':['mid_calf']},
      'sundress':{'dress_silhouette':['a_line'],'sleeve_length':['none']},
      'sweater_dress':{'fabric_material':['rib_knit']},
      'pinafore_dress':{'dress_silhouette':['a_line'],'sleeve_length':['none'],'layering':['shirt_under_dress'],'top_style':['button_front_shirt']},
      'blazer_dress':{'collar':['notched'],'garment_closure':['buttons']},
      'coat_dress':{'dress_silhouette':['column'],'garment_closure':['buttons']},
      'kaftan_dress':{'dress_silhouette':['tent'],'sleeve_shape':['kimono']},
      'cheongsam_inspired':{'dress_silhouette':['sheath'],'collar':['mandarin'],'garment_closure':['snaps']},
      'sari_inspired_drape':{'dress_silhouette':['asymmetric_drape']},
    }
    for v in active['dress_family']['values']:
        if v['id'] in dress_recipes:recipe(v,dress_recipes[v['id']],consequences=['declared garment construction defaults only; no pigment changes'])
    top_recipes={
      'crewneck_tee':{'neckline':['crew'],'fabric_material':['jersey']},
      'vneck_tee':{'neckline':['v'],'fabric_material':['jersey']},
      'oxford_shirt':{'collar':['button_down'],'garment_closure':['buttons']},
      'button_front_shirt':{'garment_closure':['buttons']},
      'tank':{'sleeve_length':['none'],'fabric_material':['jersey']},
      'camisole_opaque':{'sleeve_length':['none']},'shell_top':{'sleeve_length':['none']},
      'wrap_top':{'garment_closure':['belted_wrap']}, 'knit_pullover':{'fabric_material':['rib_knit']},
      'cardigan':{'fabric_material':['rib_knit'],'garment_closure':['buttons']},
      'sweatshirt':{'fabric_material':['fleece']}, 'hoodie':{'fabric_material':['fleece']},
      'polo':{'collar':['shirt_point'],'garment_closure':['buttons']},
      'henley':{'neckline':['round'],'collar':['none'],'garment_closure':['buttons']},
      'halter_top':{'neckline':['halter'],'sleeve_length':['none']},
      'tube_top_secure':{'neckline':['strapless_secure'],'sleeve_length':['none'],'collar':['none']},
      'bustier_style_opaque_top':{'construction_detail':['princess_seams'],'sleeve_length':['none']},
      'vest_top':{'sleeve_length':['none']},
    }
    for v in active['top_style']['values']:
        if v['id'] in top_recipes:recipe(v,top_recipes[v['id']])
    component_recipes={
      ('trouser_cut','tailored_pleated_recipe'):{'garment_fit':['tailored'],'construction_detail':['knife_pleats']},
      ('trouser_cut','cargo'):{'construction_detail':['cargo_pockets']},
      ('trouser_cut','carpenter'):{'construction_detail':['patch_pockets']},
      ('shorts_cut','denim'):{'fabric_material':['denim']},
      ('shorts_cut','paperbag'):{'waistband':['paperbag']},
      ('shorts_cut','cargo'):{'construction_detail':['cargo_pockets']},
      ('shorts_cut','athletic'):{'waistband':['elastic']},
      ('outerwear_style','tuxedo_jacket'):{'collar':['shawl']},
      ('outerwear_style','trench'):{'garment_closure':['buttons'],'waistband':['belted']},
      ('outerwear_style','wrap_coat'):{'garment_closure':['belted_wrap']},
      ('outerwear_style','duffle_coat'):{'garment_closure':['toggle']},
      ('outerwear_style','biker_jacket'):{'garment_closure':['asymmetric_zip']},
      ('shoe_style','mary_jane_flat'):{'heel_shape':['flat']},
      ('shoe_style','ballet_flat'):{'heel_shape':['flat']},
      ('shoe_style','wedge'):{'heel_shape':['wedge']},
      ('shoe_style','platform'):{'heel_shape':['platform']},
    }
    for aid in ('jumpsuit_family',):
        for vid, components in {
          'tailored':{'garment_fit':['tailored']},'wide_leg':{'trouser_cut':['wide_leg']},
          'tapered':{'trouser_cut':['tapered']},'wrap':{'garment_closure':['belted_wrap']},
          'halter':{'neckline':['halter'],'sleeve_length':['none']},'romper':{'garment_set':['romper']},
        }.items(): component_recipes[(aid,vid)]=components
    for (aid,vid),components in component_recipes.items():
        recipe(next(v for v in active[aid]['values'] if v['id']==vid),components)
    # Shape options that are literally neckline/hem/material/details are disclosed recipes, not a second independently applied steer.
    for a in active.values():
        for v in a['values']:
            if 'recipe' in v:
                defaults='; '.join(k.replace('_',' ')+': '+', '.join(x.replace('_',' ') for x in ids)
                                   for k,ids in v['recipe']['selections'].items())
                v['steers'] += '; disclosed component defaults are '+defaults+'; preserve explicit orthogonal locks'
    # Archived color patches are retained only as archival imagery; new swatches have executable RGB metadata.
    rgb={'pale_pink':[235,193,201],'emerald':[31,118,84],'deep_red':[135,31,47],'ivory':[235,230,211],
         'champagne':[211,194,154],'black':[24,24,25],'sage':[143,159,128],'navy':[34,49,79],
         'cobalt':[38,74,171],'ochre':[173,132,41],'terracotta':[179,94,70],'lavender':[179,163,204],
         'plum':[98,52,91],'teal':[41,117,120],'charcoal':[67,70,74],'white':[243,243,239]}
    a=active['fabric_color'];a.update(control='swatch',preview_method='fabric_swatch',preview_scope='fabric_texture_patch',provider_allowed=False)
    a['palette_policy']='Design RGB targets, not branded dye equivalents; every swatch uses the same fabric texture, folds and light.'
    for v in a['values']:
        v['swatch']={'rgb':rgb[v['id']],'texture':'same neutral woven fabric','color_space':'sRGB','comparison':'identical texture and illumination; pigment only'}
    active['outerwear_length']['values'].insert(0,value('none','no outerwear length because no outer layer is present'))

    # Appearance recipes are exclusive suggestions; a conflicting explicit component fails review.
    body_recipes={
      'elegant_hourglass':{'waist_definition':['defined'],'hip_breadth':['balanced'],'bust_volume':['moderately_full']},
      'couture_hourglass':{'waist_definition':['strong'],'hip_breadth':['balanced'],'bust_volume':['full']},
      'slender_hourglass':{'fullness':['slender'],'waist_definition':['defined'],'hip_breadth':['balanced'],'bust_volume':['moderately_full']},
      'slender_toned_legs':{'frame':['small'],'stature':['petite'],'leg_torso_balance':['longer_legs'],'muscle_definition':['lightly_toned']},
      'graceful_curves':{'fullness':['soft_full'],'waist_definition':['moderate']},
      'statuesque':{'stature':['tall']},
    }
    add('body_avatar',attr('body_recipe','Figure Recipe','One disclosed figure suggestion at a time; canonical body components remain orthogonal and explicitly selected values are never overwritten.',
                          [recipe(copy.deepcopy(v),body_recipes[v['id']]) for v in old['silhouette']['values']]))
    grade_ids={'neutral':'neutral_grade','warm_neutral':'warm_grade','cool':'cool_grade','monochrome':'monochrome','muted':'muted_grade','vivid':'rich_grade'}
    extra_grade={'warm_highlights':'warm highlight tint with neutral midtones and subtly cool shadows',
                 'amber':'amber tonal tint preserving photographic skin detail','teal_shadow':'subtle teal shadow tint with neutral highlights',
                 'rose':'subtle rose photographic tint with neutral shadow detail','sepia':'warm monochrome photographic tint preserving tonal order',
                 'blue':'subtle blue photographic tint preserving midtone detail'}
    for k,t in extra_grade.items():
        grade_ids[k]=k+'_grade'; active['color_grade']['values'].append(value(k+'_grade',t))
    contrast_ids={'gentle':'soft_highlights','soft':'soft_contrast','natural':'balanced_contrast','crisp':'crisp_contrast','high':'deep_shadows','low':'lifted_shadows'}
    moods=[]
    for line in MOODS.strip().splitlines():
        vid,t,g,c=line.split('|')
        moods.append(recipe(value(vid,'apply '+t+' as an editorial tonal treatment'),{'color_grade':[grade_ids[g]],'contrast':[contrast_ids[c]]},
                            consequences=['global tonal tint and contrast; garment design, garment pigment control, face movements and props remain fixed']))
    add('editorial_recipes',attr('editorial_mood','Editorial Mood','One disclosed grade and contrast recipe; moods do not change expression, clothing design, clothing color, pose or props.',moods,
                               preview_method='simulated_editorial_grade',preview_scope='explicit_global_tonal_effect',provider_allowed=False))
    narratives=[]
    for line in NARRATIVES.strip().splitlines():
        vid,t,p,g=line.split('|'); components={'pose':[p],'arm_gesture':[g]}
        consequences=['declared body and hand movement','local pose shadows','target-caused occlusion and reveal']
        if vid in {'writing','reading','cup_pause','umbrella_wait'}:
            prop={'writing':'writing_kit','reading':'open_book','cup_pause':'ceramic_mug','umbrella_wait':'open_umbrella'}[vid]
            components['hand_prop']=[prop];consequences.append('explicitly selected hand prop')
        narratives.append(recipe(value(vid,t),components,consequences=consequences))
    active['hand_prop']['values'] += [
        value('writing_kit','a pen and paper supported by a stable lap board'),
        value('open_book','an unbranded book held open above the lap'),
        value('open_umbrella','an open umbrella held securely beside one shoulder'),
    ]
    add('editorial_recipes',attr('narrative','Narrative Action','One observable action recipe with declared body, hand and prop allowances; clothing, identity, scene and color remain locked.',narratives,
                               preview_scope='declared_action_hands_props_occlusion_mask'))
    # Remaining optical/style controls retain their generation steers but honestly describe comparison simulations.
    optical = {
      'focal_length':('simulated_fov_crop','fixed-camera crop changes field of view only; no perspective or compression claim; cannot invent source pixels'),
      'aperture':('simulated_depth_blur','depth-region blur under declared depth assumptions and constant brightness; no actual aperture measurement'),
      'shutter_motion':('simulated_motion_blur','reviewed moving regions and swept footprint required; no blur on fixed non-target pixels'),
      'grain':('simulated_grain','added synthetic texture on one original scene; no sensor or camera equivalence'),
      'focus_target':('simulated_focus','reviewed depth regions softened around selected focus; cannot recover missing source detail'),
      'white_balance':('simulated_white_balance','global chromatic adaptation intentionally changes colors in the same scene'),
      'highlight_rolloff':('simulated_tone_curve','global highlight tone mapping cannot recover clipped source detail; edge glow requires separate bloom allowance'),
      'color_grade':('simulated_color_grade','global color tint intentionally changes all scene colors; no wardrobe redesign'),
      'contrast':('simulated_contrast','global tonal remapping without changes to scene geometry'),
      'palette':('simulated_palette','global color relationship simulation on the same scene; no hidden garment or prop replacements'),
      'photo_genre':('reference_edit','same scene and identity; photographic treatment changes only after a reviewed category contract'),
      'camera':('control_only','generation response preference only; no brand equivalence or actual camera-capture comparison'),
    }
    for aid,(method,constraint) in optical.items():
        a=active[aid];a.update(preview_method=method,preview_scope='same_scene_optical_simulation' if method.startswith('simulated') else 'generation_control_only' if method=='control_only' else 'reviewed_photographic_treatment',provider_allowed=method=='reference_edit',simulation_constraints=constraint)
        a['comparison_group']='photography:same_scene'
        a['preview_contract']['consequences']=[constraint]
        a['global_effect']=aid in {'focal_length','grain','white_balance','highlight_rolloff','color_grade','contrast','palette'}
    active['editorial_mood']['global_effect']=True
    active['camera']['values'][0].update(description='Natural photographic response preference without a claim of a branded camera equivalent.',steers='natural photographic color response; leave focal length, aperture and grain to their separate controls')
    for a in active.values():
        if a['preview_method']=='control_only':
            a['preview_status']='control_only';a['control']='range' if a['id']=='age' else 'select'
        if a['id'] in {'hair_color','eye_color'}:a['provider_allowed']=False
        if a['id'] in {'pose','arm_gesture','body_recipe'} or a['id'] in BODY_FEATURES:
            a['preview_contract']['locked_fields']=[k for k in a['preview_contract']['locked_fields'] if k!='pose']
        if a['id'] in {'color_grade','white_balance','palette','editorial_mood'}:
            a['preview_contract']['locked_fields']=[k for k in a['preview_contract']['locked_fields'] if k!='non_target_pigment']

    # Seam finishing is orthogonal to decorative construction; duplicate old
    # piping/topstitch/princess controls move into the construction axis.
    add('wardrobe',attr('seam_finish','Seam Finish','How seam allowances and garment edges are finished, independently of decorative construction and garment silhouette.',
                       [copy.deepcopy(v) for v in old['seam_detail']['values'] if v['id'] in {'clean_seams','flat_fell','bound_edges','raised_welts'}]))
    active['construction_detail']['values'].append(value('panel_seams','visible panel joining lines without a predetermined garment silhouette'))
    active['garment_pattern']['values'].append(value('botanical_print','restrained leafy botanical textile motifs without changing garment construction'))

    # Group locks name non-target details, never the component being changed.
    # Optical global effects are explicit; depth/focus/motion still need narrow
    # reviewed regions. Fabric pigment uses one texture patch, without a model.
    for cid,c in cats.items():
        for a in c['attributes']:
            contract=a['preview_contract']
            contract['category_id']=cid
            contract['attribute_id']=a['id']
            contract['locked_fields']=[('wardrobe_non_target_details' if f=='wardrobe_design' and cid=='wardrobe' else
                                       'scene_non_target_details' if f=='scene' and cid=='environment_props' else
                                       'lighting_non_target_parameters' if f=='lighting' and cid=='lighting_composition' and a['id'].startswith(('light','fill','practical')) else f)
                                      for f in contract['locked_fields']]
            if a['id']=='narrative':
                contract['locked_fields']=[f for f in contract['locked_fields'] if f!='pose']
                contract['allowed_changes']=['declared pose','declared arm/hand gesture','declared hand prop','target-caused shadows and occlusion']
            if a['id']=='focal_length':
                contract['locked_fields']=[f for f in contract['locked_fields'] if f!='crop']
                contract['allowed_changes']=['fixed-position field-of-view crop and resampling; no perspective change']
            if a['preview_method']=='fabric_swatch':
                contract.update(subject='identical neutral woven fabric texture patch; no human model render',
                                locked_fields=['fabric weave','texture','fold geometry','illumination','crop'],allowed_changes=['fabric pigment RGB'])
            if a['preview_method']=='control_only':
                contract.update(subject='no comparison image',base='no image rendered',mask='not applicable',publication='generation control only')
            if cid=='wardrobe':
                contract['consequences']=['target garment component geometry','local fabric fit and shadows','target-caused occlusion and reveal']
            if cid=='environment_props':
                contract['consequences']=['target scene or prop geometry','target-caused scene shadows','target-caused occlusion and reveal']
            a['generation_policy']='Use observable steering and declared component recipes; reject specific compatibility conflicts before generation.'

    def rule(rid,when,message,excludes=None,requires=None,unless=None):
        r=dict(id=rid,when=when,message=message)
        if excludes:r['excludes']=excludes
        if requires:r['requires']=requires
        if unless:r['unless']=unless
        data['compatibility_rules'].append(r)
    def present(aid):return [v['id'] for v in active[aid]['values'] if v['id'] not in {'none','no_outerwear'}]
    rule('no_outerwear_length',{'outerwear_style':['none']},'An outerwear length requires an outer garment.',excludes={'outerwear_length':present('outerwear_length')})
    rule('no_sleeve_shape',{'sleeve_length':['none']},'Sleeveless garments cannot have a sleeve shape.',excludes={'sleeve_shape':present('sleeve_shape')})
    rule('no_shoulder_collar',{'neckline':['strapless_secure','off_shoulder','one_shoulder']},'This open-shoulder neckline cannot support an attached neck collar.',excludes={'collar':present('collar')})
    rule('closed_neck_collar',{'neckline':['turtleneck','cowl']},'A folded knit neck or cowl cannot simultaneously have a separate attached collar.',excludes={'collar':present('collar')})
    rule('slit_requires_skirt',{'high_slit':['on']},'A skirt slit requires a dress or skirt garment set.',requires={'garment_set':['dress','separates_skirt']})
    rule('flat_shoe_heel',{'shoe_style':['ballet_flat','mary_jane_flat','loafer','moccasin','oxford','derby','low_top_sneaker','high_top_sneaker','running_shoe','riding_boot']},'This flat footwear family cannot carry the selected raised heel.',excludes={'heel_shape':['kitten','cone','stiletto','wedge','platform']})
    rule('pump_requires_heel',{'shoe_style':['court_pump','mary_jane_pump']},'A pump requires a raised heel geometry.',requires={'heel_shape':['kitten','block','cone','stiletto']})
    rule('shaved_arrangement',{'hair_length':['shaved','buzz_cut']},'Shaved or buzz-length hair cannot support gathered arrangements.',excludes={'hair_arrangement':[v for v in present('hair_arrangement') if v!='worn_down']})
    rule('short_cut_arrangement',{'hair_cut':['buzz_cut','pixie']},'A buzz or pixie cut cannot support a bun, braid or ponytail.',excludes={'hair_arrangement':[v for v in present('hair_arrangement') if v!='worn_down']})
    rule('shaved_treatment',{'hair_length':['shaved']},'A shaved scalp cannot carry distributed length color treatments.',excludes={'hair_color_treatment':[v for v in present('hair_color_treatment') if v not in {'uniform','salt_and_pepper_distribution'}]})
    rule('shaved_accessory',{'hair_length':['shaved','buzz_cut']},'Shaved or buzz-length hair cannot hold strand-fastened accessories.',excludes={'hair_accessory':['silk_ribbon','metal_barrette','small_clips','scrunchie']})
    rule('shaved_fringe',{'hair_length':['shaved','buzz_cut']},'Shaved or buzz-length hair cannot have a hanging fringe.',excludes={'hair_fringe':[v for v in present('hair_fringe') if v!='open_forehead']})
    rule('bun_minimum_length',{'hair_arrangement':['low_bun','high_bun','messy_bun','chignon','french_twist','low_ponytail','high_ponytail','single_braid','twin_braids','fishtail_braid','dutch_braids','braided_crown','halo_braid']},'This gathered arrangement needs shoulder-length or longer hair.',requires={'hair_length':['shoulder_length','collarbone_length','mid_back','waist_length']})
    rule('short_cut_length',{'hair_cut':['blunt_bob','graduated_bob','stacked_bob','pixie','bixie','buzz_cut']},'The selected short cut conflicts with long hanging lengths.',excludes={'hair_length':['mid_back','waist_length']})
    rule('buzz_length_match',{'hair_cut':['buzz_cut']},'A buzz cut requires buzz-length hair.',requires={'hair_length':['buzz_cut']})
    rule('long_cut_length',{'hair_cut':['long_bob','long_layers','butterfly_cut','hime_cut','v_cut','u_cut']},'This cut requires visible lengths beyond a shaved or cropped scalp.',excludes={'hair_length':['shaved','buzz_cut','ear_length']})
    # Explicit overrides permit deliberate layering; rules are conjunctions of selected axes.
    rule('dress_trousers_collision',{'dress_silhouette':present('dress_silhouette')},'A dress and separate trousers require explicit dress-over-trousers layering.',excludes={'trouser_cut':present('trouser_cut')},unless={'layering':['dress_over_trousers']})
    rule('dress_top_collision',{'dress_silhouette':present('dress_silhouette')},'A dress and separate upper garment require explicit top-over-dress or shirt-under-dress layering.',excludes={'top_style':present('top_style')},unless={'layering':['top_over_dress','shirt_under_dress']})
    rule('two_bottoms_collision',{'trouser_cut':present('trouser_cut')},'Separate trousers and a separate skirt cannot occupy one default garment set.',excludes={'skirt_cut':present('skirt_cut')})
    rule('shorts_trousers_collision',{'shorts_cut':present('shorts_cut')},'Separate shorts and trousers cannot occupy one default garment set.',excludes={'trouser_cut':present('trouser_cut')})
    rule('shorts_skirt_collision',{'shorts_cut':present('shorts_cut')},'Separate shorts and skirts need a single skort construction instead of two competing bottom garments.',excludes={'skirt_cut':present('skirt_cut')})
    rule('dress_set_bottom',{'garment_set':['dress']},'The dress garment set excludes separate bottoms except intentional dress-over-trousers layering.',excludes={'trouser_cut':present('trouser_cut')},unless={'layering':['dress_over_trousers']})
    rule('dress_set_skirt',{'garment_set':['dress']},'A dress already includes its skirt; a separate skirt cut belongs to a separates garment set.',excludes={'skirt_cut':present('skirt_cut')})
    rule('dress_set_shorts',{'garment_set':['dress']},'A dress garment set cannot simultaneously include separate shorts.',excludes={'shorts_cut':present('shorts_cut')})
    rule('dress_set_top',{'garment_set':['dress']},'The dress garment set excludes an additional upper garment unless layering is explicit.',excludes={'top_style':present('top_style')},unless={'layering':['top_over_dress','shirt_under_dress']})
    rule('trouser_set_skirt',{'garment_set':['separates_trousers']},'A trouser garment set cannot include a separate skirt.',excludes={'skirt_cut':present('skirt_cut')})
    rule('trouser_set_shorts',{'garment_set':['separates_trousers']},'A trouser garment set cannot include separate shorts.',excludes={'shorts_cut':present('shorts_cut')})
    rule('skirt_set_trouser',{'garment_set':['separates_skirt']},'A skirt garment set cannot include separate trousers.',excludes={'trouser_cut':present('trouser_cut')})
    rule('skirt_set_shorts',{'garment_set':['separates_skirt']},'A skirt garment set cannot include separate shorts.',excludes={'shorts_cut':present('shorts_cut')})
    rule('shorts_set_bottoms',{'garment_set':['separates_shorts']},'A shorts garment set cannot include a separate skirt or separate trousers.',excludes={'skirt_cut':present('skirt_cut'),'trouser_cut':present('trouser_cut')})
    rule('separates_dress',{'garment_set':['separates_trousers','separates_skirt','separates_shorts']},'Separate top-and-bottom ensembles cannot include a dress unless dress-over-trousers layering is explicit.',excludes={'dress_silhouette':present('dress_silhouette'),'dress_family':present('dress_family')},unless={'layering':['dress_over_trousers']})
    rule('separates_onepiece',{'garment_set':['separates_trousers','separates_skirt','separates_shorts']},'A separates ensemble cannot include a one-piece jumpsuit family.',excludes={'jumpsuit_family':present('jumpsuit_family')})
    rule('onepiece_skirt',{'garment_set':['jumpsuit','romper']},'A one-piece garment set cannot include a separate dress or skirt.',excludes={'dress_silhouette':present('dress_silhouette'),'dress_family':present('dress_family'),'skirt_cut':present('skirt_cut')})
    rule('dress_family_trousers_collision',{'dress_family':present('dress_family')},'A dress family with separate trousers requires explicit dress-over-trousers layering.',excludes={'trouser_cut':present('trouser_cut')},unless={'layering':['dress_over_trousers']})
    rule('sleeve_cap_length',{'sleeve_shape':['bishop','leg_of_mutton','lantern']},'This shaped sleeve needs elbow-length or longer fabric to form its defined volume.',excludes={'sleeve_length':['cap','short']})
    rule('shirt_under_dress_top',{'layering':['shirt_under_dress']},'Shirt-under-dress layering requires a separate shirt component.',requires={'top_style':['button_front_shirt','oxford_shirt','popover_shirt','blouse']})
    rule('jumpsuit_top_collision',{'garment_set':['jumpsuit','romper']},'A one-piece garment set cannot include a separate upper garment without an explicitly reviewed layering recipe.',excludes={'top_style':present('top_style')})
    rule('torso_leg_coupling_short',{'torso_length':['short']},'At fixed height a short torso conflicts with a shorter-leg proportion.',excludes={'leg_torso_balance':['shorter_legs']})
    rule('torso_leg_coupling_long',{'torso_length':['long']},'At fixed height a long torso conflicts with a longer-leg proportion.',excludes={'leg_torso_balance':['longer_legs']})
    aliases={}
    retired={'attributes':{},'values':{}}
    mappings={}
    def mapv(aid,vid,*targets):mappings[aid+':'+vid]=list(targets)
    def move_map(aid,target_aid,translation):
        for old_id,new_id in translation.items():mapv(aid,old_id,target_aid+':'+new_id)
    for row in json.loads((plans/'HAIR-MIGRATIONS.json').read_text())['rows']:
        mappings[row['legacy']]=row['targets']
    move_map('age','age',{'24':'age_24'})
    move_map('hem_length','hem_length',{'at_knee':'knee'})
    mapv('hem_length','asymmetric','hem_shape:asymmetric')
    mapv('hem_length','high_low','hem_shape:high_low')
    for vid in ['clean_seams','flat_fell','bound_edges','raised_welts']:
        mapv('seam_detail',vid,'seam_finish:'+vid)
    for old_id,new_id in {'topstitch':'topstitch','piped_seams':'piping','panel_seams':'panel_seams','princess_seams':'princess_seams'}.items():
        mapv('seam_detail',old_id,'construction_detail:'+new_id)
    move_map('expression','expression',{'neutral':'neutral_relaxed','gentle_smile':'gentle_closed_lip_smile','open_smile':'teeth_visible_smile','thoughtful':'brow_concentration','amused':'warm_closed_lip_smile','serious':'poised_neutral','surprised':'soft_awe','serene':'softened_lids'})
    # Retain useful historic eye IDs as distinct natural options when neither tint nor pattern is equivalent.
    active['eye_color']['values'].append(value('warm_gray','warm neutral gray iris pigment with unchanged iris geometry and radial pattern'))
    move_map('eye_color','eye_color',{'dark_brown':'deep_brown','amber':'light_amber','hazel':'brown_hazel'})
    move_map('silhouette','body_recipe',{v['id']:v['id'] for v in old['silhouette']['values']})
    for vid,targets in {
       'lean':['fullness:lean'],'athletic':['muscle_definition:athletically_defined'],
       'soft_average':['fullness:balanced','muscle_definition:smooth'],
       'broad_frame':['frame:broad'],'petite_frame':['frame:small','stature:petite'],
       'full_figure':['fullness:soft_full'],'tall_frame':['stature:tall'],
       'compact_athletic':['frame:small','muscle_definition:athletically_defined'],
    }.items():mapv('body_build',vid,*targets)
    for vid,targets in {
       'narrow_shoulders':['shoulder_width:narrow'],'balanced_shoulders':['shoulder_width:balanced'],
       'broad_shoulders':['shoulder_width:broad'],'soft_slope':['shoulder_slope:gentle'],
       'square_shoulders':['shoulder_slope:square'],
    }.items():mapv('shoulder_shape',vid,*targets)
    # Shoulder roundness/relaxation were bundled posture, not a width/slope equivalence.
    for vid in ['rounded_shoulders','defined_shoulders','relaxed_shoulders']:mappings['shoulder_shape:'+vid]=[]
    wardrobe_translation={
      'top_style':{'crew_tee':'crewneck_tee','button_shirt':'button_front_shirt'},
      'neckline':{'crew_neck':'crew','boat_neck':'boat','square_neck':'square','modest_v_neck':'v','high_neck':'mockneck','cowl_neck':'cowl'},
      'sleeve_length':{'sleeveless':'none','cap_sleeve':'cap','short_sleeve':'short','elbow_sleeve':'elbow','three_quarter_sleeve':'three_quarter','wrist_sleeve':'long','extended_cuff':'extended'},
      'sleeve_shape':{'straight_sleeve':'straight','fitted_sleeve':'fitted','bell_sleeve':'bell','bishop_sleeve':'bishop','puff_sleeve':'puff','dolman_sleeve':'dolman','raglan_sleeve':'raglan'},
      'trouser_cut':{'straight_leg':'straight','culottes':'culotte','pleated_trousers':'tailored_pleated_recipe','relaxed_cargo':'cargo','slim_tailored':'slim'},
      'skirt_cut':{'a_line_skirt':'a_line','wrap_skirt':'wrap','straight_skirt':'straight','bias_cut':'bias'},
      'outerwear_style':{'no_outerwear':'none','trench_coat':'trench','wool_coat':'overcoat'},
      'shoe_style':{'loafers':'loafer','ballet_flats':'ballet_flat','ankle_boots':'ankle_boot','knee_boots':'knee_high_boot','low_pumps':'court_pump','sneakers':'low_top_sneaker','oxfords':'oxford','sandals':'ankle_strap_sandal'},
      'fabric_material':{'satin':'opaque_satin'},
    }
    for aid,translation in wardrobe_translation.items():move_map(aid,aid,translation)
    # Preserve meaningful remaining old garments as recipes or distinct missing features.
    for aid,vid,t in [
      ('sleeve_length','rolled_sleeve','full-length sleeves rolled into a neat cuff above the wrist'),
      ('sleeve_shape','structured_sleeve','sleeves with crisp tailored panel seams and a defined outline'),
      ('fabric_material','wool','opaque wool cloth with a soft natural fiber surface'),
      ('outerwear_style','cardigan','knitted outer layer opening down the front'),
    ]:active[aid]['values'].append(value(vid,t))
    mapv('top_style','turtleneck','top_style:knit_pullover','neckline:turtleneck')
    mapv('top_style','boat_neck_top','top_style:shell_top','neckline:boat')
    mapv('neckline','collared','collar:shirt_point')
    mapv('neckline','stand_collar','collar:stand')
    mapv('skirt_cut','pleated','skirt_cut:straight','construction_detail:knife_pleats')
    waist_maps={
       'natural_waist':['waist_rise:mid'],'high_waist':['waist_rise:high'],'mid_rise':['waist_rise:mid'],
       'hip_rise':['waist_rise:low'],'paperbag_waist':['waistband:paperbag','waist_rise:high'],
       'contoured_waist':['waistband:contoured'],'wide_waistband':['waistband:wide'],'elastic_waist':['waistband:elastic'],
    }
    # Natural-waist and mid-rise remain separate placement choices.
    active['waist_rise']['values'].append(value('natural','waistband aligned exactly with the natural waist'))
    waist_maps['natural_waist']=['waist_rise:natural']
    for vid,targets in waist_maps.items():mapv('waist_position',vid,*targets)
    dresses={
      'slip':['dress_family:slip_dress'],'bodycon':['dress_silhouette:sheath','garment_fit:fitted'],
      'off_shoulder':['dress_silhouette:sheath','neckline:off_shoulder'],
      'a_line':['dress_silhouette:a_line'],'shirt_dress':['dress_family:shirt_dress'],
      'wrap_dress':['dress_silhouette:wrap'],'column_dress':['dress_silhouette:column'],
      'fit_and_flare':['dress_silhouette:fit_and_flare'],'shift_dress':['dress_silhouette:shift'],
      'pleated_dress':['dress_silhouette:a_line','construction_detail:knife_pleats'],
      'high_neck_dress':['dress_silhouette:sheath','neckline:mockneck'],
    }
    for vid,targets in dresses.items():mapv('dress_style',vid,*targets)
    # Primary old poses resolve to actual support configurations. Gestures/orientation are disclosed component recipes.
    pose_targets={
      'hands_on_hips':['arm_gesture:hands_waist'],'weight_shift':['pose:standing_left_support'],
      'over_shoulder':['body_orientation:back_three_quarter_left','head_tilt:turn_left'],
      'finger_near_lips':['arm_gesture:finger_near_lips'],'seated':['pose:seated_left_leg_cross'],
      'three_quarter':['body_orientation:quarter_left'],'looking_back':['body_orientation:back','head_tilt:turn_left'],
      'hand_in_hair':['arm_gesture:hand_in_hair'],'arms_relaxed':['arm_gesture:relaxed'],
      'walking_forward':['pose:walking_midstance'],'walking_left':['pose:walking_diagonal_left'],
      'walking_right':['pose:walking_diagonal_right'],'long_stride':['pose:walking_slow_long'],
      'short_step':['pose:walking_careful_narrow'],'paused_step':['pose:walking_toe_release'],
      'wide_stance':['pose:standing_parallel_wide'],'one_knee_bent':['pose:standing_left_knee_soft'],
      'one_foot_forward':['pose:standing_offset_feet'],'hands_clasped_front':['arm_gesture:clasp_front'],
      'hands_behind_back':['arm_gesture:clasp_back'],'one_hand_on_hip':['arm_gesture:left_hand_hip'],
      'arms_folded':['arm_gesture:folded_arms'],'hand_on_forearm':['arm_gesture:hand_forearm'],
      'hand_on_elbow':['arm_gesture:hand_elbow'],'waving':['arm_gesture:right_wave'],
      'open_hand_gesture':['arm_gesture:open_palm_right'],'reaching_up':['arm_gesture:right_arm_up'],
      'stretching_shoulders':['arm_gesture:arms_overhead'],'turning_in_place':['pose:walking_half_turn'],
      'pivot_left':['pose:pivot_left_toe'],'pivot_right':['pose:pivot_right_toe'],
      'seated_upright':['pose:seated_parallel_feet','arm_gesture:hands_thighs'],
      'seated_sideways':['pose:seated_side_left'],'seated_ankles_crossed':['pose:seated_left_ankle_over'],
      'seated_lean_forward':['pose:seated_edge_forward'],'seated_lean_back':['pose:seated_supported_recline'],
      'seated_hands_clasped':['pose:seated_parallel_feet','arm_gesture:hands_lap'],
      'seated_looking_up':['pose:seated_parallel_feet','head_tilt:chin_up'],
      'bench_side_sit':['pose:seated_side_right'],
      'reading_book':['narrative:reading'],'seated_reading':['narrative:reading'],
      'holding_cup':['narrative:cup_pause'],
    }
    # Preserve genuinely distinct support/action features missing from the primary expansion.
    extra_poses={
      'crossed_ankles':'stand with ankles gently crossed and weight shared between both feet',
      'feet_together':'stand with feet touching parallel and weight evenly shared',
      'slight_arch':'stand with a slight natural back extension and both feet grounded',
      'stool_perch':'sit upright on a high stable stool with one foot on its footrest',
      'step_sit':'sit on a wide stable step with both feet supported by the next step',
      'ledge_sit':'sit on a low stable ledge with both feet touching the ground',
      'wall_lean_shoulder':'stand with one shoulder supported by a stable wall',
      'wall_lean_back':'stand with the back supported lightly by a stable wall',
      'rail_lean':'stand with forearms supported lightly on a stable rail',
      'table_lean':'stand with one palm supported on a stable waist-height table',
      'doorway_rest':'stand with one hand supported by a stable vertical doorway frame',
      'ascending_step':'transfer weight upward onto a stair with the leading knee flexed',
      'descending_step':'transfer weight down a stair with a naturally counterbalanced torso',
    }
    # Supports are declared geometry consequences, never automatically injected props.
    for vid,t in extra_poses.items():
        v=value(vid,t)
        v['required_support']='operator-reviewed existing support geometry' if vid not in {'crossed_ankles','feet_together','slight_arch'} else 'ground'
        active['pose']['values'].append(v)
    extra_gestures={
      'touching_collar':'touch an existing garment collar lightly with one hand',
      'touching_cuff':'adjust an existing sleeve cuff with the opposite hand',
      'holding_lapel':'hold one existing jacket lapel lightly between fingers',
      'holding_hem':'hold one existing opaque garment hem lightly without raising it',
      'checking_watch':'lift one forearm and turn the wrist to view an existing watch',
      'pointing_side':'extend one arm sideways with a relaxed pointing hand',
      'reaching_shelf':'extend one arm toward shoulder height with an open reaching hand',
      'seated_one_arm_on_back':'rest one arm along an existing stable seat back',
      'looking_into_window':'gather hands loosely while turning the head toward an existing window',
      'tying_scarf':'bring both hands to an existing scarf knot near the neck',
      'buttoning_jacket':'bring both hands to an existing jacket button near the waist',
      'adjusting_strap':'touch an existing secure shoulder strap without changing garment coverage',
    }
    for vid,t in extra_gestures.items():
        active['arm_gesture']['values'].append(value(vid,t,requires_existing_feature=True))
        pose_targets[vid]=['arm_gesture:'+vid]
    pose_targets['carrying_bag']=['hand_prop:bag']
    active['hand_prop']['values'].append(value('bag','an unbranded bag held beside the thigh'))
    pose_targets['holding_umbrella']=['hand_prop:open_umbrella']
    pose_targets['leaning']=[] # support kind cannot be inferred without user input
    for vid,targets in pose_targets.items():mapv('pose',vid,*targets)
    reasons={
      'ethnic_inspiration':'Retired ancestry-style stereotype control has no appearance-only equivalent; preserve raw tags and choose explicit appearance controls.',
      'complexion_detail':'Retired bundled complexion recipe needs explicit tone, undertone and freckle decisions; no inferred replacement.',
      'facial_balance':'Retired subjective balance label has no measurable independent appearance equivalent.',
      'face_direction':'Retired non-expression editorial label cannot be guessed into a mouth, brow or lid movement.',
      'shoulder_shape':'Bundled shoulder contour or posture needs explicit width/slope/posture choices.',
      'pose':'The legacy pose needs an explicit support or orientation decision before generation.',
    }
    for aid,a in old.items():
        for v in a['values']:
            key=aid+':'+v['id']
            targets=mappings.get(key)
            if targets is None:
                targets=[key] if aid in active and v['id'] in {x['id'] for x in active[aid]['values']} else []
            disposition='retire_unresolved' if not targets else 'keep' if targets==[key] else 'move' if len(targets)==1 else 'disclosed_recipe'
            if len(targets)==1:
                ta,tv=targets[0].split(':')
                target=next(x for x in active[ta]['values'] if x['id']==tv)
                if 'recipe' in target:disposition='disclosed_recipe'
            reason=reasons.get(aid,'The archived raw wording and tags remain available; review the disclosed canonical component targets before applying a migration.') if not targets else 'Raw historic label and steer retained; '+('canonical ID remains available in its assigned v2 category.' if disposition=='keep' else 'migration preview discloses the target control'+('s and recipe consequences.' if disposition=='disclosed_recipe' else '.'))
            if key=='hair_style:side_part':reason='Legacy side_part does not specify left or right; operator must choose a canonical part explicitly.'
            alias={'disposition':disposition,'targets':[dict(attribute_id=t.split(':')[0],value_id=t.split(':')[1]) for t in targets],
                   'legacy_name':v['name'],'legacy_steer':v['steers'],'legacy_description':v['description'],
                   'legacy_category':coverage_source[aid]['current_category'],'reason':reason,'historical_filter_retained':True}
            aliases[key]=alias
            if not targets:retired['values'][key]=copy.deepcopy(alias)
        if aid not in active:
            retired['attributes'][aid]={'legacy_name':a['name'],'legacy_description':a['description'],
                'owner_category':coverage_source[aid]['owner_category'],'disposition':'retire_unresolved' if all(not aliases[aid+':'+v['id']]['targets'] for v in a['values']) else 'reconciled',
                'reason':'Archived raw control remains available for historical filters; review each value disposition before generation.'}
    configure_local_previews(active)
    for cid, category in cats.items():
        for attribute in category['attributes']:
            attribute['preview_contract']['baseline_requirements'] = baseline_requirements(cid, attribute)
    coverage={'legacy_attribute_count':len(old),'legacy_value_count':len(aliases),'attributes':{}}
    for aid,record in coverage_source.items():
        dispositions=sorted({aliases[aid+':'+v['id']]['disposition'] for v in old[aid]['values']})
        coverage['attributes'][aid]={**record,'disposition':dispositions[0] if len(dispositions)==1 else 'mixed',
            'value_dispositions':{v['id']:aliases[aid+':'+v['id']]['disposition'] for v in old[aid]['values']},
            'status':'controls_active_v2','preview_status':'comparison_previews_awaiting_operator_review'}
    coverage['active_counts']={cid:{'attributes':len(c['attributes']),'values':sum(len(a['values']) for a in c['attributes'])} for cid,c in cats.items()}
    coverage['proposal_reconciliation']={'wardrobe_source_candidates':wardrobe['proposed_values_total'],
        'removed_semantic_equivalents':{'qipao_inspired':'dress_family:cheongsam_inspired','sleeve_shape:cap':'sleeve_length:cap'},
        'wardrobe_source':'docs/plans/anchored-v2/WARDROBE-PROPOSAL.json',
        'wardrobe_candidates':{family+':'+vid:{'disposition':'move' if vid=='qipao_inspired' or family=='sleeve_shape' and vid=='cap' else 'keep',
            'target':('dress_family:cheongsam_inspired' if vid=='qipao_inspired' else 'sleeve_length:cap' if family=='sleeve_shape' and vid=='cap' else FAMILY_IDS[family]+':'+vid)}
          for family,ids in wardrobe['families'].items() for vid in ids}}
    coverage['v1_sha256']=hashlib.sha256(original).hexdigest()
    pointers={'version':2,'categories':{cid:{'controls':{'version':2,'source':'catalog/v2/library.json','status':'active'},
        'comparison_previews':{'status':'awaiting_operator_review','source':None},
        'previous':{'version':1,'source':'catalog/v1/library.json'}} for cid in cats}}
    # Validate everything before creating output; a malformed source never partially replaces an active bundle.
    sys.path.insert(0,str(root))
    from catalog_v2 import validate_library, validate_compatibility
    validate_library(data)
    for aid,a in active.items():
        for v in a['values']:
            if 'recipe' in v:
                conflict=validate_compatibility({aid:[v['id']]},data)
                if conflict:raise ValueError(f'invalid recipe {aid}:{v["id"]}: {conflict}')
    v1=root/'catalog/v1/library.json'
    v1.parent.mkdir(parents=True,exist_ok=True)
    if v1.exists() and v1.read_bytes()!=original:raise ValueError('Frozen v1 snapshot differs; refuse overwrite')
    if not v1.exists():v1.write_bytes(original)
    folder=root/'catalog/v2';folder.mkdir(parents=True,exist_ok=True)
    for name,document in [('library',data),('aliases',aliases),('retired',retired),('coverage',coverage),('active',pointers)]:
        (folder/(name+'.json')).write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Strict bundle validation includes every legacy pair and every migration reference.
    from catalog_v2 import load_bundle
    load_bundle(root)
    return coverage


if __name__=='__main__':
    coverage=build(Path(sys.argv[1]) if len(sys.argv)>1 else ROOT)
    print(json.dumps({'v1_sha256':coverage['v1_sha256'],'legacy_attributes':coverage['legacy_attribute_count'],
                      'legacy_values':coverage['legacy_value_count'],'active_counts':coverage['active_counts']},indent=2))
