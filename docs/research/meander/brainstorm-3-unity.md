# Meander brainstorm 3: unity and abstraction

Lens: how one process covers the sheet ("kinda more unified stuff") without
becoming a map. I looked at the river, Ian's sketch, both references and
v5 seeds 3, 13 and 21 before writing this.

## What the seeds tell me about unity

The three seeds are not unified for the same reason: **their weight and their
single lines come from different processes.** The heavy parts are restated
contour bundles around bodies: seed 3's central mass, seed 13's joined pair
and left bundle, seed 21's diagonal tube. The thin parts are leftovers. They
are scattered fragments that belong to nothing. In seed 3 they are the
confetti on the right, and in seed 21 the long drifting lines at the left.
The eye reads two systems, "the drawing" and "the debris", so the sheet feels
like a figure placed on a scattered ground.

Seed 21's diagonal is the most useful mark in the set. Two banks pinch and
swell along it and are restated unevenly, so it already reads as width made
of lines. Seed 13's left bundle runs off the bottom edge, which is the only
place in the three where the drawing refuses the frame.

In the river, the thin, the dense and the empty parts are **one process at
different moments and rates**. That, not the river look, is what to take.
Every idea below is a way of making the thin lines, the tangle and the empty
ground come from the same rule.

## The minimum cue that stops it reading as a map

A drawing reads as a map when three things coincide:

- a channel of constant width,
- that runs through the frame edge to edge,
- at one legible scale.

Break any two and the river is gone, while its logic stays. I'd make these
hard rules for the whole round, not tunable options:

1. **No through-flow.** No bank pair runs continuously from one sheet edge to
   another. Channels begin and end inside the sheet, and their ends turn
   inward, as in Ian's hooks. A river with no source and no mouth is no
   longer geography.
2. **No constant width.** Along any stretch of 30 mm or more, the gap
   between the two banks varies by at least 40%, measured as the coefficient
   of variation (CV) of the gap.
3. **At least two scales.** Every sheet contains features whose wavelengths
   differ by a factor of 4 or more. A single wavelength is what makes the
   Hodgin look read as "satellite view".

Omission is the cheapest abstraction on this list, and idea 3 is built on it.

---

## 1. Activity field: one dial, three registers

**Mechanism.** Store a scalar field `A(x,y)` in [0,1] on a coarse grid
(60×44), made of 2–3 broad noise blobs plus one sharp ridge. Run a single
curvature-driven migration (Howard–Knutson style: the migration rate is an
exponentially weighted upstream integral of curvature, O(N) per step with a
recursive filter). Every local constant of the step is read from `A` at
that point:

- wavelength and resample step: `λ = lerp(60, 3, A)` mm, step `λ/12`
- migration rate: fast where `A` is high
- snapshot cadence: frequent where `A` is high
- crossing permission: occupancy is respected where `A < 0.6` and ignored
  above it

The output is no longer "a river with some texture". It is:

- **organic single line** where `A` is low (long λ, slow, few snapshots,
  no crossings)
- **textural** where `A` is mid (short λ, many snapshots packed tight but
  not crossing)
- **tangle** where `A` is high (λ close to pen spacing, crossings allowed,
  so the cutoffs pile up as overlapping stranded loops)

The same stroke passes through all three. N is about 1500 points and about
400 steps, so roughly 0.6M point updates, which is well under 50 ms.

**Decision it makes.** Where the drawing is fine-grained or coarse, busy or
calm. That is "weight at parts and less at others", with the parts chosen
by one field rather than by treatment type.

**Cliché.** In the high-`A` zone, a small λ with occupancy respected is
exactly **brain coral or fingerprint**. That is why crossings must switch
on there. Where they are allowed, the zone risks looking like a scribble
fill with a hard edge.

**Kill.** On a 24-thumbnail sheet, kill it if **any** high-`A` zone reads as
a patch with a visible outline, a "filled region". Also kill it if two or
more thumbnails show evenly spaced parallel meanders anywhere (coral).

**Seeds.** This makes seed 13's junction knots and its thin singles one
thing. The knot is the same line where `A` peaks.

## 2. Erosion truncation: emptiness made of what was destroyed

**Mechanism.** Run the migration long enough that the channel sweeps much
of its neighbourhood, keeping snapshots. Record the swept footprint `R`,
the union of the channel strips over time, as a bitmap. Then draw
**newest first**, which is v5's reversed arrival in a new role, into
`Sheet` occupancy with lineage:

- The final channel is drawn first.
- Each older snapshot is clipped wherever a *later* channel strip passed
  over it. This is what a real river does to its scroll bars: later
  migration erases earlier bars.
- Where a trace is clipped, its end gets an inward hook (from `handLine`'s
  curl, sign forced toward the old centre).

The survivors are scroll-bar fragments whose ends stop dead against an
**invisible line**, which is the edge of a later sweep that is itself not
drawn. The empty ground is therefore **shaped**: its boundary is implied by
many truncated line-ends that agree on an edge nobody drew. In geology
this is an unconformity.

Cost: rasterising the strips at 1 mm is cheap, and clipping uses the existing
`segHit`.

**Decision it makes.** Which history survives, and therefore where the
emptiness is and what shape it has. The floodplain stops being leftover
paper and becomes a defined absence.

**Cliché.** If erosion is weak, the surviving sets are complete concentric
arcs (**tree rings**, the named risk). If the implied edges are too
straight, they look like torn paper or a collage mask.

**Kill.** Kill it if more than a third of the surviving scroll sets are
complete, un-truncated arcs of 90° or more. Also kill it if, on the contact
sheet, the empty regions have no perceivable edge and read as random
blank patches rather than a shape cut out of the texture.

**Seeds.** Seed 3 has open ground but no edge to it. This gives the right
half of seed 3 a reason to be empty.

## 3. Headless channel: omit the present tense

**Mechanism.** Keep the migration history but **never draw the current
channel as two complete banks**. The present is drawn as at most one bank,
for at most 40% of its length, and preferably on the side of the lower
activity field `A`. Everything else on the sheet is history: scroll
fragments, stranded oxbow halves, and abandoned banks.

Add the no-through-flow rule. The initial centreline is a closed-ish open
curve seeded inside a 70%-of-sheet ellipse, and both ends are pinned by an
inward-curl boundary condition: at each step the last 8 points get curvature
added toward the interior.

**Decision it makes.** What is absent. The viewer sees a force's aftermath
without the force. That is the most direct engine for "make you ask whats
really going on", and it costs nothing, because it is a filter on what is
drawn.

**Cliché.** A drawing of stretch marks, or a Spirograph missing lines. If
the history is too regular, the missing channel becomes obvious in a
literal way: "a river was here", which is still a map.

**Kill.** In a blind review, kill it if at least half the reviewers name
"river" or "map" unprompted from thumbnails. Separately, kill it if the
sheet reads as sparse with no protagonist, meaning nothing holds the eye
for more than 2 seconds.

**Seeds.** All three seeds have a strong closed form in the middle. This
removes the object and keeps the searching around it. It is the most
direct answer to "holding onto the territory thing too closely".

## 4. One bundle, whole sheet: every line is a strand

**Mechanism.** The sheet has **one** migrating centreline `C(s)`. It is
drawn as K = 5–9 strands, and each strand is `C(s) + o_i(s)·n(s)`, where
`o_i` is a slow 1-D noise per strand multiplied by a spread field
`S(s)` in mm.

The spread field is keyed to curvature and to the activity field `A`:

- **At the bends**, S goes to 0.3–1.5 mm. The strands converge into one
  heavy, slightly frayed line. This is the **narrow part**: it reads as
  a thin edge turned toward you.
- **On the straights**, S grows to 6–25 mm. The strands separate into a
  band with visible width: the **swell**, and the volume.
- **At the extremes**, 1–3 strands exceed a threshold, detach, and
  continue on their own path. A detached strand follows `C`'s
  *tangent integral* with its own drift, runs out across empty ground,
  and either rejoins elsewhere (a capture) or ends in a hook. These
  are Ian's long open lines *between* things, and they are the same
  line as the bundle.

Each strand passes through the hand separately, so the strands disagree.
They are written as separate strokes, so the pen lifts produce slight
misregistration.

Cost: K × N points, trivial.

**Decision it makes.** Width versus narrowness, and so the illusion of
volume Ian asked for. It also decides which lines leave the mass. Unity is
structural: there is literally one line family.

**Cliché.** Rope, hair, cable, a Hodgin-style ribbon, or string art. If the
strand offsets are too uniform, the result is **ruled parallels**, which
Ian rejected.

**Kill.** Measure the CV of inter-strand gaps along each 20 mm window.
Kill it if the median CV is below 0.25, because that is ruled-parallel.
On the contact sheet, kill it if any thumbnail reads as a braid or a rope.

**Seeds.** This is seed 21's diagonal, generalised to cover the sheet. Its
pinch-and-swell tube is the one mark in v5 that already shows width made
of lines.

## 5. Two scales, one rule, shared banks

**Mechanism.** Run **the same migration rule twice** on one sheet, at
wavelengths about 6× apart:

- one large channel, λ ≈ 70 mm, mostly single or double lines
- one small channel, λ ≈ 10 mm, restless, with many snapshots

They share a single occupancy `Sheet`. When the small channel's migration
brings it within 1.5 mm of an ink cell of the large one, it is
**captured**: for the next 10–40 mm it follows the large one's bank using
its tangent, which gives the restated drifting double contour. Then it
peels off with an inward hook.

The large channel ignores the small one; the dominance is asymmetric.
Cost: two simulations, still under 0.1 s.

**Decision it makes.** Where the registers collide, and which one yields.
This is Ian's "different registers mixing into each other" and the sketch's
"lines shared between lobes", produced by an event rather than by a style
switch. The scale mismatch alone defeats the map reading. The eye cannot
choose which one is "the river", so neither is.

**Cliché.** A big doodle with a small doodle decorating it. At worst, the
small channel frames the big one like an ornamental border.

**Kill.** Kill it if, in the median thumbnail, the small channel runs along
the large one for more than 35% of its length (ornament). Kill it if the
two never meet in at least half the thumbnails, because then there are two
unrelated drawings.

**Seeds.** Seed 13 already has two registers: the heavy vertical bundle
and the joined lobes. It lacks the capture where they trade lines.

## 6. Crop from a larger field: composition as a found window

**Mechanism.** Simulate on a virtual field 2–3× the sheet, 600–900 mm
wide. Compute the ink density on a 5 mm grid with a summed-area table, and
evaluate about 200 candidate windows of sheet aspect at 2–3 zoom levels.
Score each window on four things:

- the ink centre of mass is at least 20% of the width from the centre
- the largest empty connected region covers 30–55% of the area and
  touches at most 2 frame edges
- at least one heavy run crosses a frame edge
- the density histogram is bimodal

The best-scoring window wins. Zooming gives the **scale jump** for free: a
crop at 0.35× of the field makes one bend fill the sheet, with its scroll
set becoming a texture at body size. Cost: the sim is at most 2× more
expensive, and the scoring is under 5 ms.

**Decision it makes.** Composition and scale, chosen after the process
rather than imposed before it. A cropped process feels unmoored: it
continues past the edge, which is the "weird compositions" Ian asked for,
and it is not an object placed in a margin.

**Cliché.** A slice of wallpaper, where every crop is an excerpt of one
even texture. Or a "detail shot" of a map, which a crop can make *more*
map-like.

**Kill.** Kill it if 24 crops sort into indistinguishable excerpts, meaning
a reviewer cannot tell three chosen crops apart at thumbnail size. Also
kill it if more than 60% of winning windows put their mass in the same
quadrant, which means the score, not the process, is composing.

**Seeds.** Seed 13's bottom-edge bundle is the one existing case of the
drawing leaving the frame, and it is why that seed has more pull than it
should.

## 7. Rate reversal: the process changes its mind mid-sheet

**Mechanism.** Choose one moment in the run, a step `t*` at about
55–75% of the run, and one region. At `t*` in that region, the sign of the
migration coefficient flips: bends that were growing start to shrink and
straighten. Locally, the channel retraces backwards across its own scroll
bars, and the new history overprints the old at a slight angle rather
than parallel. This interleaves two restatement directions at about
10–25°, which gives a net-like tangle on one lobe. It is Ian's "net on
one lobe", made by the process instead of stamped on.

The event is budgeted to one per sheet. It costs a sign flip and an
extra 60 steps.

**Decision it makes.** Where the drawing doubts itself. It gives the sheet
a single event that the viewer can sense but cannot parse.

**Cliché.** Crosshatching. If the angle is too large or too even, it
becomes engraved hatching, which Ian rejected.

**Kill.** Kill it if the crossing angles in the event zone cluster within
±5° of a single value (hatch). Kill it if the zone reads as a separate
patch rather than as the same line turning on itself.

**Seeds.** This is seed 3's top junction, where restatements pile up and
cross, extended into an event with a cause.

---

## Ranked recommendation

1. **One bundle, whole sheet (4), inside an activity field (1).** Together
   they are one mechanism: the activity field sets λ, crossings and
   snapshot cadence, and the bundle's spread field is keyed to it. This is
   the only pairing that answers both halves of Ian's v5 note at once:
   volume from width made of lines, and unity because every line on the
   sheet is a strand of one family, including the thin loose ones. Build
   it first.
2. **Erosion truncation (2), drawn newest-first.** This is v5's reversed
   arrival in the role where it pays: it produces shaped emptiness and
   abrupt, hooked line-ends, and it is the strongest defence against tree
   rings. It layers directly on top of 1+4 as the history filter.
3. **Headless channel (3), as a hard rule, not an option,** plus the three
   anti-map rules above (no through-flow, no constant width, two scales).
   It is almost free, and it is the minimum abstraction that has to be
   designed in from step 1.

Ideas 5, 6 and 7 are good second-round events. 6 (the crop) is cheap enough
to try as a composition wrapper around anything.

## Wild card: the magnifier lobe

One region of the sheet, about 25–40% of it, bounded by the edge of an
eroded sweep and **not** by a drawn outline, shows the *same simulation at
4–6× magnification*. Inside it, the geometry is the neighbourhood of one
point outside, rescaled.

The lines are continuous across the boundary as topology but jump in scale.
A thin single line outside becomes, inside, a wide restated bundle of the
same strands; the tangle outside becomes open organic lines inside. The
registers swap at the boundary, but they are provably the same drawing.

It will read as a lens, as depth, or as volume ("a body with a surface"),
without any figuration. Kill it on sight if it looks like an inset map or a
magnifying-glass diagram. That is the risk, and also why it is worth one
try.
