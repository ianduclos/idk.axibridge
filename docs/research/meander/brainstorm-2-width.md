# Meander brainstorm 2: width from lines

Lens: the illusion of line width, narrowness and volume, made with one 0.4 mm
pen at one stroke width, on a 300 × 218 mm sheet.

## Where I start (and where I disagree with v5)

v5 already restates lines: sediment ghosts, stable restates 0.3–0.6 mm toward
the rival, and a committed line. But it restates **around a single line**. Its
passes scatter on both sides of the edge with no rule about *spacing*. So a
bundle reads as "a line drawn several times", never as "one wide mark". Ian
asked for width and narrowness, and a shaky line can't give him that. The fix
is to treat a bundle as **one object with two banks and a width profile
w(s)**, where the strands are that object's edges and occasional interior
hairs.

Three perceptual facts drive every idea below. The numbers assume a plot seen
at about 40 cm and a contact-sheet thumbnail about 650 px wide.

1. **Strand gap sets the reading.** A gap of ≤ 0.5 mm merges into one
   *darker, thicker* line. A gap of 0.6–1.3 mm reads as a **double line**:
   railway track, ruled parallels, the look Ian rejected. A gap of 1.5–6 mm
   reads as a **band with a surface inside it**, which is where width and
   volume happen. Above about 8 mm it reads as two separate lines. The
   middle zone is poison, and v5's 0.3–0.6 mm "toward the rival" drifts into
   it.
2. **Volume comes from change in width, not from width itself.** A band of
   constant width is a pipe, the CAD tube Ian doesn't want. What implies a
   turning surface is width that goes to zero where the surface turns
   edge-on (a twist or pinch) and swells where it faces you. It also needs
   **asymmetry between the banks**: one edge firm, the other softened or
   multiplied, the way one side of a form is in light.
3. **The banks need correlated hands.** If each strand gets its own
   `handLine` sway (loose `A` ≈ 0.45 mm), two strands 1.5 mm apart wobble
   independently, and the width profile turns into noise. Every idea below
   uses one shared helper, `bandLine(spine, profile, hand)`. It gives all
   strands the same low-frequency displacement (`n1` at `l1`), gives each
   strand only a quarter of `n2` of its own, and clamps strand separation to
   ≥ 0.5 mm except at designed crossings. Cost: samples × strands, which is
   trivial against the 0.2 s budget. All strands of one band share a
   lineage in `Sheet`, as v5's `related()` already allows, so siblings are
   not walls.

---

## 1. Cut bank / point bar: weight lives on one side, and swaps

**Mechanism.** Take a spine: a v5 border edge, or a long open line *between*
things. Resample at 0.5 mm and compute signed curvature κ(s), smoothed over
8 mm. Then build the two banks.

- The **outer (convex) bank** is one firm stroke at `+w(s)/2`.
- The **inner (concave) bank** is a fan of 1 + n(s) strands, with
  n(s) = round(3·smooth(0.02, 0.08, |κ|)) and spacing that *grows outward
  geometrically* (1.6, 2.4, 3.8 mm…, ratio jittered 1.3–1.8). These are the
  scroll bars.
- Width w(s) = w0·(1 + 0.8·|κ|·R), with w0 of 2–4 mm, so bends run wider,
  as rivers do.
- At an inflection (κ changes sign) the fan dies to a single strand over
  about 6 mm and is reborn on the other bank.
- Fan strands are open. They start and end at different arclengths, and
  the outermost ends with a 2–4 mm inward hook.

**Decision.** Which side of a line is heavy. Once that is decided locally
and it flips at every inflection, an S-curve reads as a **ribbon turning
over**: light on one face, then on the other. That gives volume with no
shading.

**Cliché.** "Neat meandering river on a map" (Hodgin). Or every curve
shaded on its inside, like engraving or comic tube-shading. Or tree rings,
if the scroll bars come out evenly spaced.

**Kill.** (a) On any fan with ≥ 3 strands, the gaps have a coefficient of
variation < 0.3, or the fan runs for more than 60% of its spine: tree rings.
(b) In a blind look, ≥ 3 of 12 thumbnails read as "river". (c) Fans on every
bend of every spine: one handwriting everywhere. Cap fans to the 2–3 highest
|κ|·length bends per spine.

**Seeds.** The top junction arc in seed 3 already doubles asymmetrically,
heavier on the underside. This would make that the rule. The long diagonal
body in seed 21 has bundles on both sides of the same contour, and this
would force them onto alternate sides, so the body turns.

## 2. Coincide or separate: the spacing quantizer for restatement

**Mechanism.** This is a post-rule on any restatement, whether from v5
sediment, the idea 1 fans, or knots. For each new pass, measure its gap
g(s) to the nearest sibling strand. Remap each gap into one of two
permitted zones:

- **merge**: g → 0.15–0.45 mm. This adds darkness and thickness.
- **spread**: g → 1.6–5 mm. This adds width.

Nothing may sit in the 0.6–1.3 mm dead zone except while *passing through*
it at a crossing, with at least 25° of relative angle. The choice between
merge and spread comes from history. A stretch where the snapshots agreed
(v5's "stable", age high) merges. A stretch that migrated spreads, and the
spread is proportional to migration distance. A pass that changes zone
mid-stroke does it by **crossing** its sibling, never by sliding
alongside it.

**Decision.** Whether a restatement adds *dark* or adds *width*. This is the
tonal logic of the whole sheet: old, stable things are narrow and black;
contested, moving things are wide and pale. A brush does the opposite, and
that inversion is part of the "what's really going on".

**Cliché.** If it fails: railway tracks and ruled doubles. If it is
over-applied: every bundle alternates a thick black lane with an airy band
like a barcode.

**Kill.** Histogram the strand gaps within 8 mm, across the sheet. The
sheet fails if more than 15% of sampled gap length falls in 0.6–1.3 mm, or
if there are more than 4 merge↔spread switches per 100 mm of spine.

**Seeds.** Directly repairs the thing that makes 3 and 13 look "restated"
rather than "wide": their bundles sit at about 1 mm gaps. The tall vertical
pair at the left of 13 is already about 5 mm apart and reads as a tube, so
that is the spread zone working by accident.

## 3. Flux width: bands pinch between things and swell after

**Mechanism.** A band carries a conserved "flux" Q. Its local speed comes
from clearance: c(s) is `distField` of *other-lineage* ink at the spine
point, and w(s) = clamp(Q / v(s), 0.4, 7) with v ∝ 1/c^0.7. Squeezing
through a gap narrows the band, down to strands that touch or cross. On
leaving the gap the band **overshoots** its width (a jet): w is
low-passed with a 10–15 mm lag, so the swell sits *downstream* of the gap,
not at it. Where the swell exceeds 5 mm, one interior hair wanders off with
a loose hand and an open end and becomes a single thin line into open
ground. That is the line *between* things that Ian liked.

**Decision.** Width responds to neighbours. Every band on the sheet obeys
the same field, which is the cheapest route to "kinda more unified" without
unifying the handwriting.

**Cliché.** Metaball bridges, neon-tube liquid, "blobby" bodies. Width
responding symmetrically at the gap reads as a sausage chain.

**Kill.** (a) A band whose max/min width ratio is < 2 over its length:
pipe. (b) A pinch and its swell centred within 5 mm of each other: sausage.
(c) Any band > 7 mm wide whose interior is evenly filled with hairs:
engraving.

**Seeds.** Seed 13's horizontal rail at mid-height passes between two masses
and is uniformly doubled. Under flux it would pinch at the gap and bloom to
the right, where the ground opens.

## 4. The fold: which bank is in front

**Mechanism.** Give a band a twist angle φ(s). The visible width becomes
w·|cos φ|. At φ = 90° the banks meet, cross, and swap sides. Allow **0–2
folds per band**. Place them at spine inflections, which idea 1 hands over
for free, or where the band passes over other ink. At each fold, the bank
that goes "behind" is **broken**: it ends 1.5–3 mm before the crossing with
a T-end, and v5's T-end hook curls toward the band's interior. Then it
restarts on the far side 1 mm offset, the way `handLine.lift` re-enters. The
front bank is continuous and uses the firm hand. For about a third of the
band's length after a fold, the rear-to-front bank gets one extra merge
strand (idea 2) as a shadow.

**Decision.** Occlusion. The mark claims to be a surface with a front and a
back, the strongest volume cue a single line can carry. It also produces
the sketch's inward hooks *for a reason*.

**Cliché.** Banner ribbon, DNA helix, Möbius logo, CAD sweep.

**Kill.** (a) Folds at regular arclength intervals, or more than 2 per band.
(b) A band that reads as a flat ribbon, with constant width between folds.
Fold only bands already modulated by 1 or 3. (c) On more than a quarter
of the sheet, a folded band reads as a banner or a loop-the-loop.

**Seeds.** Seed 3's left hook-loop is already a bundle doubling back on
itself, and a fold would say which part is in front. It is the most
"what's going on" place in all three seeds.

## 5. One nib for the whole sheet (a width field)

**Mechanism.** Define one slow angle field θ(x, y) across the sheet: a
base angle plus curl noise at 120 mm scale, with 0–1 singularities, where
the field whirls. The width of any band is
w = w0 + w1·|sin(tangent − θ)|: marks moving across the nib swell, and marks
along it go thin. Every band uses it, and so do the fans in 1 and the
restates in 2 (the ratio of spread to merge follows the same term). Single
open lines ignore it.

**Decision.** A shared "light" for the sheet. Unrelated marks swell and
narrow in agreement, so the sheet coheres the way a drawing made with one
tool held one way coheres. That is, I think, what "more unified stuff"
meant.

**Cliché.** Italic calligraphy, copperplate, ornamental flourishes. With a
constant θ, every thick part points the same way and it reads as lettering.

**Kill.** (a) In a blind look, thumbnails read as script or monogram.
(b) Thick parts across the sheet share one orientation within ±15°. The
curl field must break this. (c) Swap θ to random per band. If the sheet
doesn't get *less* coherent, the field is doing nothing and should be
dropped.

**Seeds.** 21 is the most all-over of the three and the least unified. A
shared width field is what would make its scattered open lines and its
dense body feel like one sheet.

## 6. Loaded brush, dry tail

**Mechanism.** A band gets a pressure envelope p(s) with an attack of 3–8
mm, a peak at 15–45% of its length (seeded, never centred), and a long
release. Strand count k(s) runs from 1 to 4 and width from 0.4 to 5 mm,
both following p. The **head** is loaded: strands bunch in the merge zone,
and 1–2 short restarts overlap the first 5 mm (density piles where the
mark begins, often at a junction). The **tail** is dry: as p falls, strands
don't converge. They **splay** apart, drop out one by one at different
arclengths, and the last survivor carries on as a single thin line, which
may hook inward.

**Decision.** Where along its length a mark was pressed. It gives each
mark a direction and a time, and it gives the sheet "painterly" and
"dynamic" without a scribble filter.

**Cliché.** Sumi-e brush filter, commas and tadpoles, "Photoshop brush
stroke".

**Kill.** (a) The peak positions of all bands fall within ±10% of each
other. (b) More than a third of marks read as a comma or tadpole shape. (c)
Tails that splay symmetrically, like a broom or a horsetail.

**Seeds.** The heavy top bundle in seed 3 ends in thin single strands that
wander off right. That is a dry tail already, drawn by accident.

---

## Ranked recommendation

1. **Idea 2 (spacing quantizer) first.** It is a cheap post-rule on v5's
   existing restatement, and it removes the double-line dead zone that
   stops any bundle reading as width. Ship it even if nothing else lands.
   Everything else here depends on it.
2. **Idea 1 (cut bank / point bar), with idea 4's fold as a rare event at
   its inflections.** Together they carry the core claim: width with a lit
   side and a dark side that swaps. They are the sketch's sling band and
   hooks with a reason behind them, and they take the river's scroll bars
   as asymmetric history, not rings. Guard the geometric spacing hard (tree
   rings are the named risk).
3. **Idea 5 (sheet nib) as the unifier.** It is a one-line term in w(s). It
   only makes sense once 1–2 give bands something to modulate, and it
   answers "more unified" directly.

Ideas 3 and 6 are strong, but each adds a second width driver. If more than
two drivers act on one band, width turns to noise. Pick per band, and log
which driver won in the recipe so the review can tell them apart.

**First experiment:** v5 seeds 3, 13 and 21 with idea 2 alone, then with
1 + 2, then with 1 + 2 + 5. Review four things: the thumbnails, a 1:1 crop
(thumbnails merge gaps that paper won't), the gap histogram, and the fan
spacing CV.

## Wild card: width made of absence

Never draw the band. Draw only its **two banks, each in a different
register**. One bank belongs to the neighbouring mass: its tangle and
restates, dense and textural. The other is a single thin firm line 3–12 mm
away that follows the first bank's pinches and swells without agreeing
exactly, with a lag of about 8 mm. The "stroke" is a channel of bare paper
between two unlike edges. Its width is read entirely from the gap, and its
volume is read from which side is heavy. This is the river as it appears in
the photograph: a pale shape defined by darker banks. It is also the most
abstract answer here. The strongest mark on the sheet is ink you never put
down, and the two registers mix across it without touching. **Kill:** if
the channel reads as a road, or as a cartoon outline around nothing, which
happens when it closes on itself. Keep it open at both ends, and allow at
most one per sheet.
