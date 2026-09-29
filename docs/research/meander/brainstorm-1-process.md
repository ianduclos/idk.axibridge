# Meander brainstorm 1: meander as drawing process

Lens: migration, cutoffs and reversals as *drawing decisions*. Several channels that cross, capture and abandon one another. Where the starting centrelines come from.

## Where I disagree going in

**Ian's sketch is already a meander, caught just before a cutoff.** Read it again with the river beside it. The two bulbs are two bends. The sling band between them is the **neck**: the narrow strip of floodplain that is about to be breached, drawn four or five times because it is where the tension is. The long S-stroke through the middle is a channel shared between lobes. The inward hooks are stranded loop ends. None of this needs to be "river-looking". It needs the *moment* of the river, not its map. So the first decision the process makes is **when to stop**, and that decision should be made per bend, not for the whole sheet.

**The simulator is a proposal engine, not the author.** A curvature-driven migration step (Howard–Knutson style, cheap in JS) is fine to generate candidate positions. Every visible outcome — which past positions get drawn, which necks get cut, which channel wins a crossing — is a decision with a compositional reason. If we let hydrology choose, we get Hodgin: a horizontal belt, evenly skewed bends, oxbows dotted along both sides, all the same scale.

**Anti-map constraints from step 1, not patched later.** Channels never run edge to edge. They start and end inside the sheet (a stroke that begins in a knot and dies in open ground). The valley axis is curved and sheet-specific, never horizontal. Channels on one sheet differ in scale by 3–5× (a slow wide one and tight nervous ones). These are cheap and they kill the map look before it appears.

## Shared machinery (assumed by all ideas)

- **Centreline** `C = {pts[], q (discharge 0.2–1), age, id}`, resampled every 1.5 mm.
- **Migration step**: curvature `κ_i`; rate `R_i = Ω·κ_i + Γ·Σ_{j≥1} κ_{i∓j}·e^{−αj}` (the lag sum is upstream for a normal channel, see idea 4); `p_i += dt·R_i·n_i`; resample; one `smoothPts` pass. 400–700 nodes × 150–250 steps ≈ 10⁵ ops, well inside the 0.2 s thumbnail budget.
- **History**: store a snapshot of each centreline every step (cheap: typed arrays), plus events (`cutoff`, `capture`, `reversal`) with step index and location.
- **Neck detection**: spatial hash at 3 mm; pairs `(i, j)` with arc gap > 4× local width and distance < `neckW`. That makes the gap a *candidate* cutoff, not an automatic one.
- **Drawing**: everything goes through `walkLine` + `handLine` with lineage (v5's related-edge occupancy carries over unchanged: banks of the same channel may touch; other ink is a wall except where an idea says otherwise).

---

## 1. Heterochrony: every bend frozen at its own moment

**Mechanism.** Run the migration to a long horizon (250 steps). Segment the final and historical centrelines into **bends** (inflection to inflection, tracked through time by nearest-inflection matching). For each bend compute a *tension curve* over time: `T(t) = bend amplitude / neck width`. Each bend is then drawn at a **different time** `t*_b`, chosen per bend: most bends at their tension peak (neck narrowest, just before a cutoff would fire), one or two long after cutoff (the stranded loop, open), a few early (low, lazy undulation). Adjacent bends are stitched at inflections with a short blend (10–15 mm cross-fade between the two times' centrelines). The neck of each peak bend is restated 3–6 times using that bend's positions at `t*−k … t*` — five slightly different necks that don't agree. Cost: the sim once, then bend tracking O(bends × steps); trivial.

**Decision it makes.** *What time it is, locally.* A physics sim has one clock. This draws a sheet where one lobe is about to pinch, the next already stranded, a third still young. That is "make you ask what's really going on": the parts are coherent individually and inconsistent as a set. Weight piles at necks because the drawing chose tension, which is exactly the sketch's sling band and "density piled at the junctions".

**Cliché.** A row of balloon-animal loops, or pretzel knots, all at the same peak tension, evenly spaced: the tension-maximum is the most river-postcard moment. Also the closed-pebble risk: a peak bend with a 2 mm neck reads as a closed bean body.

**Kill criterion.** On a 12-cell sheet: if more than a third of cells show ≥3 loops of similar size (within ±30% area) with similar neck widths, or if any peak loop reads as closed (neck gap < 1.5 mm drawn), kill or cap peak bends to 1–2 per sheet. Also kill if the eye can't find at least one "young" and one "stranded" bend in most cells — then the heterochrony isn't visible and it's just a snapshot.

**Seeds.** Seed 3's left hooked arm is a bend at its peak with the neck restated; seed 13's lower double lobe is two bends sharing a neck. Starting centrelines from these give the process a head start: their bends already sit at different "times".

---

## 2. The cutoff editor: which necks break, and how

**Mechanism.** When neck detection fires, the drawing chooses among three outcomes, each drawn differently:
- **Cut** (stranding): splice the centreline, the loop becomes an *oxbow* drawn once or twice as an **open arc**: always a 4–12 mm gap at the old neck, ends hooked inward 2–5 mm (reuse v5's hook code, sign toward the loop interior). Oxbows fade: their bank strands drop one by one along the arc so the far side of the loop is a single line.
- **Braid** (overlap): let the two limbs cross; draw the crossing as a knot with lineage relaxed for 8 mm (both limbs may touch), then continue. This is the only place tangle is allowed.
- **Refuse** (dodge): add a local repulsion so the limbs slide past each other; the drawing gets a tight parallel squeeze (two channels running shoulder to shoulder for 20–40 mm, then parting). That squeeze is a sling band.

Choice rule: a per-sheet budget (e.g. 1–3 cuts, ≤1 braid, 1–2 refuses) allocated by composition: cuts go where the stranded arc would land in **emptier** ground (open shapes in negative space), braids go to the heaviest region, refuses go between the two biggest masses.

**Decision it makes.** Hydrology always cuts. The drawing decides the event type by where its consequence lands on the sheet. Cutoffs become the source of open shapes (Ian's "open shapes based on the compositions we had before") rather than decoration.

**Cliché.** Oxbow lakes dotted beside a channel, crescent after crescent. The v5 review already caught "repeated crescents" — this is the same failure with a better excuse.

**Kill criterion.** More than 2 visible crescents per cell in more than a quarter of cells, or crescents all opening the same way → the rule is producing a pattern, not events. Also kill "braid" on sight if it produces a hairball (v5's knot failure): a braid must stay under ~60 mm of extra ink.

**Seeds.** Seed 21's small loop cluster at the bottom and the offset loop in seed 3 (right, middle) are almost-oxbows: isolated, restated, small. They are what a stranded loop should feel like — off to the side, a little odd.

---

## 3. Capture and abandonment: several channels, one winner

**Mechanism.** 3–6 channels, each with discharge `q`. Width-from-lines is set by `q` (strand count `1 + round(4q)`, spacing 0.6–2.5 mm; the details belong to brainstorm 2). Channels migrate together; the neck test runs *between* channels as well. When a bend of channel A touches channel B:
- **Capture:** the bigger (by a *composition score*, see below) takes the smaller's upstream reach. The smaller's downstream reach is **abandoned**: it stops migrating, loses strands to 1, and is drawn with a thin, loose hand and a fade. The capturer's `q` jumps, so from the capture point on its strands multiply. A trunk swells visibly *at the event*: width steps up where history happened.
- **Crossing without capture:** allowed when angles exceed 50°. The higher-`q` channel is drawn continuous; the other is **interrupted** (a lift of 3–6 mm around the crossing). With one pen, over/under is the cheapest volume cue we have.

Composition score: favour captures that pull weight toward a chosen mass centre (per sheet: one centre = "one mass", zero = "all-over", which answers Ian's "bit of either"). Cost: pairwise channel hash per step, negligible.

**Decision it makes.** Who wins is decided by where the drawing wants weight, not by gradient or slope. Abandoned reaches are the "long open lines *between* things" that survived from v5, but now they have a reason: they're what's left of a loser.

**Cliché.** A dendritic river network or a neuron (Y-junctions everywhere, branches at similar angles, tapering tree). Second cliché: braided-river texture (many interweaving equal channels).

**Kill criterion.** Count junction types: if > 60% of channel meetings are Y-shaped with a smaller branch entering at 30–60°, it's reading as a tree → cut channel count or force more crossings. If no cell has a clear trunk vs. thin lines weight difference (top-decile density < 4× median non-empty), the capture isn't producing weight.

**Seeds.** Seed 13 is this idea already: the left vertical bundle is a trunk, the horizontal band crossing it is a captured channel, and the thin verticals to its right are abandoned reaches. Start from it and the process has somewhere to go.

---

## 4. Reversal: the lag flips

**Mechanism.** The upstream-lag term in the migration rate gives real meanders their downstream skew. The drawing flips its sign (`Σ κ_{i+j}` instead of `κ_{i−j}`) for chosen spans and times: a **reversal event**, 1–2 per channel. Bends then migrate against their own history, so new positions cut across older ones instead of stacking outside them. Draw: the pre-reversal positions (selected, see idea 5) plus the present. Because they migrated in different directions, the traces **cross and don't agree**, which is the sketch's restated contours that drift and disagree. Cost: a sign flag per node span; free.

**Decision it makes.** Direction of time/flow per region. Physics never does this. It is also the meander version of v5's "reversed arrival order" — the one lever Ian noticed changed the base masses.

**Cliché.** Mush: if reversals are frequent the bends just wobble in place and the result is a jittery single line with fur (the S-sheet ribbed doubles from v5 round 2).

**Kill criterion.** If a reversed span and a non-reversed span on the same sheet can't be told apart on the contact sheet (no crossing traces, no change of skew), reversal is doing nothing → drop it. If more than a third of a channel's length is reversed and the line reads as fur/jitter → cap to one reversal per channel.

**Seeds.** Seed 3's central mass has contours that go around then back through (the diagonal strokes crossing its rim). That crossing restatement is what a reversal produces.

---

## 5. Scroll traces chosen by event, never by timestep

**Mechanism.** Past centreline positions are *candidates*, never drawn by schedule. A past position is drawn only if it's attached to an **event**: the step before a cutoff, the step of a capture, the step of a reversal, or a local curvature sign flip (a bend changing hands). Each drawn trace is a **span** (15–60 mm, open), not a whole channel, and anchored at one end on present ink (so it grows off a bank, like the sketch's restated contours hanging off a junction). Spacing is whatever the events produced — which is uneven because events cluster. Hard cap: no more than 3 nested traces in a run with spacing CV < 0.3; if the chooser would produce a 4th, it skips to a far-apart one (v5's "reduction" rule, applied to migration history instead of arrival history).

**Decision it makes.** Which moments of the past count. Scroll bars in a real point bar are near-periodic (annual floods); these are dated by *drama*. Weight lands where things happened.

**Cliché.** Tree rings / topographic contours: the named risk. Also a "motion blur" look if spans are too long and too many.

**Kill criterion.** Any cell with a nested family of ≥4 arcs at roughly even spacing (spacing CV < 0.25) is a failure, full stop. Measure it automatically: along the normal of each present bank, count crossings of history traces within 20 mm and compute spacing CV.

**Seeds.** This is v5's sediment made continuous. Seeds 3 and 21 show the good version (two or three disagreeing rims on one side only, the other side single). Keep that one-sidedness: traces only on the migrating (outer) side, never both.

---

## 6. Where centrelines come from: inherit the gesture, not the territory

**Mechanism.** Three sources, one param:
- **From v5 ink (default).** Rasterise a v5 render's ink density on 2 mm, blur σ 4 mm, trace **density ridges** with `walkLine` following the ridge (steepest-ascent then along the principal eigenvector of the Hessian). The top ridge becomes the trunk (seed 13's left bundle, seed 21's diagonal corridor, seed 3's hook arm → rim). Secondary ridges or v5's long thin open lines become minor channels. Territory camps, borders and outer edges are thrown away: only the *gesture* survives.
- **From cores.** Centrelines as smooth paths *between* cores (Catmull-Rom through core pairs, never around them) — keeps "long lines between things".
- **From nothing.** One low-frequency noise walk, 150–300 mm, curled valley axis, plus 2–4 short channels spawned off it at random points.

Then migration runs 40–250 steps depending on how far the sheet should drift from its inheritance (param `drift`).

**Decision it makes.** What the river *is* before it moves. Choosing ridges of an existing drawing means the meander process reworks a composition rather than inventing a landscape — a painter's reworking, not a map.

**Cliché.** From nothing: a sine-ish horizontal wave, i.e. the generic river. From v5: at low drift, a v5 drawing with extra lines (no change); at high drift, the inheritance evaporates.

**Kill criterion.** Render seeds 3/13/21 through the process at the default drift next to three random-start seeds; if a blind reviewer can't pair each output with its v5 source better than chance, the inheritance is noise → lower drift or drop the source. Conversely, if outputs are v5 plus a few loops, raise drift.

**Seeds.** What should survive from each: **3** — the one heavy mass with an open, sparse right half, and the hook arm; **13** — the trunk + crossing band (a capture already happened), the double lobe; **21** — the diagonal corridor mass with restated rims against long, lazy single lines far away. Across all three: the lopsided weight and the large, uncomposed-looking empty ground. Those survive via ridge tracing + budget; the camps don't.

---

## 7. The bank that lags (width as process)

**Mechanism.** Each channel has two banks that migrate separately. The **outer** bank of a bend moves with the centreline (erosion). The **inner** bank lags by `k` steps (deposition, `k` 5–30, set per bend). Width therefore swells at bends that migrate fast and pinches at inflections and stable reaches. Draw the outer bank firm and single; draw the inner bank as the searching restatement (positions `t−k … t`, 2–4 of them, each a partial span). So each ribbon is a thick, restated inside edge against a clean outside edge — asymmetric width, which reads as turning volume.

**Decision it makes.** Which side of a band carries the doubt, and how far it lags. Physics sets that by sediment supply; the drawing sets it by sheet weight (lag longer on the protagonist channel).

**Cliché.** Evenly doubled road-map lines, or a calligraphy-ribbon screensaver. (This overlaps brainstorm 2's lens; I include it only because width arising from the migration history is a process claim.)

**Kill criterion.** If ribbon width varies less than 2:1 along most channels, or both banks look equally restated, it's reading as a double line → drop the lag and hand width to brainstorm 2's mechanism.

**Seeds.** Seed 13's vertical bundle already pinches and swells — two banks, one restated.

---

## Ranked recommendation

1. **Heterochrony (1) with the cutoff editor (2) as its event vocabulary.** It is the only idea here that maps straight onto Ian's sketch (two bends, a neck, a sling band, hooked stranded ends) and it produces "what's really going on" by construction: parts of the sheet are at different times. Build first.
2. **Capture and abandonment (3), seeded from v5 ridges (6).** This carries unity and weight: one trunk that grows by eating the others, the losers left as long thin open lines between things. Seed 13 is already an instance, so it's the lowest-risk bridge from what Ian liked.
3. **Event-dated scroll traces (5)** as the only history rule, with the automatic spacing-CV check wired into the contact sheet from day one: it is the tree-ring guard.

Reversal (4) is a cheap flag; give it one test cell, keep it if it makes contours disagree. Bank lag (7) should defer to whatever brainstorm 2 proposes for width.

## Wild card: the white river

Draw no active channel at all. The present-day channel is **negative space**: an unmarked ribbon 4–15 mm wide whose presence you only infer from the edges of everything else — oxbows, event traces, abandoned reaches, and restated outer banks that stop exactly at its edge. Width and pinch are real (the ribbon swells and narrows) but made of absence; the densest ink on the sheet sits *against* the one thing that isn't drawn. It is the most direct answer to "negative space" and "make you ask what's really going on", and it is the least likely to read as a river render, because the river is the one thing missing. Risk: it may just look like a sparse drawing with an accidental gap. Kill it if a viewer can't find the ribbon in the thumbnail within a couple of seconds.
