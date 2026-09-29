# Meander round 2: brainstorm, the tangle register (Opus)

Lens: the tangle register, the one Ian asked for that meander still lacks. Read before writing: plan round 2, `shots/meander-0929/README.md`, the Sonnet reviews, synthesis brief §1 and §9, and `t_meander.js` in full. Images checked: round-2 sheet A, close-a, Ian's sketch, v5 close-Ha.

## What the images say before any idea

- **The hairball, measured by eye (v5 close-Ha).** Clusters 5–15 mm across, made of many short strokes with tight radii (under 3 mm) that loop around one point and fan out in every direction. They sit at the junctions, so every cell gets one. The failure is not density. It is three things together: **isotropy** (no direction), **small radius** and **placement at every node**.
- **Ian's sketch tangles differently.** Its tangle is *anisotropic and long*. Look at the lower band under the central form, and at the upper-left fan. Four to six restatements travel the same route for 40–80 mm, drift apart into lens-shaped cells, cross at shallow angles (under 30°) and come back together. The upper-left fan comes from strokes that share one anchor and then diverge. Nothing in it loops tightly. The tangle is **a band that has lost its order**, not a knot.
- **Where meander is now (close-a).** Bands are ordered: strands keep their rank from the concave to the convex side, and crossings happen only by drift. The one tangle-like passage is M04's searching knot at the bottom right, which is exactly the sketch's grammar (horizontal restatements crossing at shallow angles). It works for that reason, and it is still bolted on.

So the design rule for everything below: **a tangle is a local loss of order inside a directional mark.** It keeps the channel's heading (strand tangents within about ±35° of the centreline) and gives up its ranking, spacing and continuity. Radius stays above 3 mm. It occurs only where the process says something happened.

**A shared kill metric (proposed, cheap).** For each tangle zone, record: the aspect ratio of the principal axes of its ink points (must be ≥ 3), the mean |angle| between stroke tangents and the local centreline (must be ≤ 35°), and the share of ink length on radii under 3 mm (must be ≤ 10 %). Across a sheet of 6 cells, the coefficient of variation of zone size and ink mass must be ≥ 0.4, because identical zones are the "stamp" failure. This sits next to the existing `hairball` window sum in `meanderRecipe`. A zone that fails 2 of the 4 checks counts as hairball-signature.

---

## 1. Decoherence (the band forgets its order)

**Mechanism.** In `bundleGeom`, each strand's offset is `drift + mine + b·S/2·(1 − 2((k+.5)/K)^1.5)`: the rank term dominates, so strands keep their order. Add a coherence field `coh(i) ∈ [0,1]` along the band:
`coh = 1 − smooth(q80, q98, A(C_i) · S_i/Smax · vl_i/vhi)`, the product of activity, swell and lagged migration speed, taken over its own per-band quantiles. Then blend the offsets:
`o_k = coh · ranked_k + (1 − coh) · wander_k`,
where `wander_k` is an independent low-frequency walk for each strand (noise1, wavelength 12–25 mm) confined to an envelope of `±0.7·S·(1 + 0.6(1 − coh))`. The envelope widens where order is lost, so the band's width goes "wrong" and bulges. Also, inside `1 − coh > 0.3`, the gap quantizer is skipped (the railway guard is moot when strands cross), dropped strands are revived (`ac = 1` up to Kmax), and put() runs with `cross:true`, since siblings are already `related`. Cost: one extra noise array per strand, O(n·Kmax), under 1 ms per band.

**Decision it makes.** Where a band's order breaks down. The answer is the swell peak on its most active bend: where the river worked hardest, the mark loses control.

**Cliché.** Rope or twisted cable, and DNA, if the wander wavelengths match and the crossings fall periodically. Also the "scribble-filter restatement", if it spreads along the whole band.

**Kill criterion (contact sheet).** You can count regularly spaced X crossings: the spacing of crossing points along s has a CV under 0.3, which reads as rope. Or decoherence covers more than 25 % of a band's length, which is the scribble filter. Or it fails the shared metric: it passes the hairball test by construction only if the envelope stays directional.

**Fade.** It is intrinsic: `coh` is continuous along s, so the band goes ordered → lens cells → ordered. At the ends of the zone, strands re-rank by crossing back, and that crossing-back *is* the fade. The sketch's lower band does exactly this.

**Rarity.** One window per band, taken at the top 2 % of the product and then widened by a 20–60 mm smooth ramp. Only bands with Kmax ≥ 4. At most 2 zones per sheet, and the second at half depth (its `coh` floor is 0.5).

## 2. Plait at a refused neck (the brief's deferred braid)

**Mechanism.** A `refuse` event gives `at`, `ch`, `other`, `t`. Where two limbs stall shoulder to shoulder and both carry strands (take the nearest index on each channel's `geo.C`, with the gap under neckW + S), define a window of ±L around each index, with `L = 10 + 25·A(at)` mm. Inside it, strand k of limb a gets a lateral excursion toward limb b:
`o_k += e(s) · g · sin(π·u_k(s))`,
where `g` is the centreline gap and `e(s)` is a raised-cosine envelope. Here `u_k` is a per-strand monotone phase with its own irregular rate (a cumulative sum of `0.5 + rng` steps), so each strand crosses the gap once or twice, at a different place from its neighbours. Limb b mirrors this with independent phases. The two sets pass through each other's bands: put() runs with `cross:true`, and the pair is already in `sim.pairs`, so `related` is true. Swapped strands may *stay* on the far limb (probability 0.3) and end there, so the plait leaks. Cost: trivial, since it only edits offsets in two windows.

**Decision it makes.** It adds a third outcome to the editor that the brief deferred. A neck that can be neither cut nor held **exchanges material**. Which necks plait is set by the event budget, not by geometry, so you can ask "why here".

**Cliché.** A Celtic plait or rope braid (regular over-under), a hair plait, or a DNA ladder.

**Kill criterion.** The crossings alternate regularly, and the plait reads as a *thing* sitting on the line (an ornament) rather than two currents mixing. Or the zone is rounder than 3:1, the hairball shape: that happens when the limbs meet at a steep angle, so plait only when the limb tangents are within 40° of antiparallel.

**Fade.** The raised-cosine envelope takes the excursions back to zero over 8–15 mm. The leaked strands carry the plait on as a one-strand misfit in the other band for up to 30 mm, a trace of it.

**Rarity.** Only `refuse` events (the cap is ≤ 2 per sheet today), and only when both limbs have K ≥ 3 at the neck. At most one full plait per sheet. A second qualifying neck gets a "half plait": only one limb leaks.

## 3. Hinge fan (time-lapse restatement anchored at an inflection)

**Mechanism.** History today is 1–4 concave-side traces, thresholded and clipped. The sketch's upper-left fan is a different object: several positions of one bend that **share an anchor and diverge**. Inflections barely migrate, and apexes migrate most, so snapshots of one bend taken between two inflections already form a fan pinned at the hinge. For a chosen bend, take 3–6 snapshots with irregular t spacing (skip snapshots at random, never evenly spaced). Keep only the half from the inflection to the apex, each truncated at its own length (40–100 % of the half-bend). Draw them with `cross:true` and without `erase`, so they cross the present band instead of being clipped by it. Run `ringTest` on the fan and require it to stay silent. Cost: `snaps` already holds the geometry, so it is under 1 ms.

**Decision it makes.** Which one bend shows its motion as a smear, and it is anchored at a hinge. That turns the history register from rings into gesture.

**Cliché.** A motion-blur or "speed lines" cartoon. Also tree rings, if the snapshot spacing becomes even.

**Kill criterion.** `ringTest` fires or the fan reads as nested concentric arcs (M13's failure). Or it reads as speed lines: all fan members end at the same place, like a comet.

**Fade.** It thins toward the apex, because members are truncated at different lengths. At the hinge the members converge into the present line and become one thicker stroke. The fan grows out of the line.

**Rarity.** Only bends whose snapshot inflection count flipped, or that were next to an event within ±16 steps (the existing `cands` rule). Only bends where the apex displacement between the first and last kept snapshot is > 8 mm. At most 1 per sheet, and this *replaces* the concave traces for that bend (it is not added on top).

## 4. Confluence spill (capture as mixing, not junction)

**Mechanism.** A `capture` event splits a minor at the trunk. Today the minor just ends against the trunk's occupancy (a T-cut). Instead, continue each strand of the minor's band (or restate a single-line minor 2–3 times) past the junction. Each continuation follows a pursuit curve: its heading turns toward the trunk tangent at its own rate (0.04–0.15 rad/mm) and toward a target offset drawn from the trunk's strand offsets at that s. It is drawn with `cross:true`, so it passes through trunk strands, and it ends when it is within 0.4 mm of a trunk strand for 5 mm (it has merged) or after 50 mm. Near the junction the trunk's own `coh` (idea 1) is pulled down by `0.4·exp(−d/15)`, so the trunk also loosens where it receives water.

**Decision it makes.** Capture becomes a place where two orders meet and dissolve into one. It is the only tangle driven by *two* channels' histories, so it varies more between cells.

**Cliché.** A river-confluence map glyph (a clean Y), or hair combing into a braid.

**Kill criterion.** It reads as a Y-junction map symbol (the spill is too short, under 15 mm), or as a fanning cluster at a point (the spill turns too fast and all continuations bunch in the first 5 mm, which is the hairball signature again).

**Fade.** The strands merge into trunk strands one by one over 15–50 mm. The last one to merge is the fade.

**Rarity.** Only captures (≤ 2 per sheet), and only when the trunk band at that point has K ≥ 3. If both captures qualify, only the later one spills fully.

## 5. Crossing drag (two bands pass through, with deflection)

**Mechanism.** Where two unrelated bands cross, put() currently cuts the later one at the earlier one's ink (`endT`). For crossings where both have K ≥ 3 and A > 0.6, run the later band's strands through instead (`cross:true` inside a 12 mm radius). Add a deflection to their offsets: `Δo_k = D·sign·exp(−(s − s_x)²/2σ²)`, with `σ = 4–8 mm`, `D ∝ S_other`, and the sign chosen per strand. Some strands are dragged along the other band's tangent for a few mm and then released. Two to four strands out of K still stop at the crossing (a random subset, not all), so the crossing is part cut, part flow. Cost: a crossing test on the band centrelines (segment-hash, which exists as `pointHash`) plus offset edits.

**Decision it makes.** At a crossing, which band yields and how much. The answer is a local "pressure" (the product of S at the crossing), not an ink order.

**Cliché.** Woven fabric, a warp-and-weft over-under. Or a highway interchange.

**Kill criterion.** The crossing reads as a right-angle weave (the crossing angle is over 60°). So only let it run at shallow crossings under 45°, and cut the rest as now. Or the drag is symmetric on both sides, which makes a lens bead that reads as a decorative knot.

**Fade.** The Gaussian deflection, plus the released strands rejoining their rank within 2σ.

**Rarity.** Usually 0–1 qualifying crossings per sheet (bands are only on the trunk and 2 minors), which is right. Hard cap 1.

## 6. Pile restatement (texture where history accumulates), a guarded idea

**Mechanism.** On the density grid `meanderRecipe` already builds (10 mm cells), find the single cell cluster where band plus traces plus search exceed the 97th percentile. Restate the *existing* strokes in it once or twice, each copy displaced by a smooth noise field at 0.5–1.5 mm and each clipped to a random sub-length (the searching register's grammar, applied to whatever is there rather than to one line). This is overdraw of the pile.

**Decision it makes.** Weight follows accumulated history, so the drawing gets darker where it has worked.

**Cliché, and why it is guarded.** This is closest to v5's hairball by construction: dark where it is already dark, at a point. Keep it only as a *modifier* of ideas 1–3: it may restate a decoherence zone, never raw ground. And if its first sheet shows a darkest blob in every cell, kill it.

**Kill criterion.** It fails the shared metric (a round zone), or 6 of 6 cells have their darkest 20 mm square at a tangle.

**Fade.** Displacement amplitude falls with the density gradient.

**Rarity.** One cluster per sheet, on a coin flip (probability 0.5).

---

## Ranking

1. **Decoherence (1).** It is the purest unity move: the tangle is the band itself at its most active point, with no new object, no new placement rule and cost under 1 ms. Its fade is intrinsic, so line → band → texture → band → line is one continuous function. It is also the closest match to the tangle in Ian's sketch (lens cells from restatements that disagree along one route). Build it first. Then see whether the "rails on gentle arcs" complaint shrinks for free, because the zone sits on high-curvature swell peaks.
2. **Plait at a refused neck (2).** This is the candidate Ian named, and it adds what (1) cannot: an *event* reason, legible as "two things touched here and traded material". It depends on (1) for its texture (a plait inside a decohered zone reads as mixing, not ornament). Build it second, on refuse events only.

The hinge fan (3) is the best history idea on the list and fixes the tree-ring risk as a side effect. It belongs with the history register if round 2 has room.

## Wild card: the unmade decision (double present at a neck)

When the editor chooses `cutoff`, draw **both futures**: the post-cut present (as now) *and* the pre-cut present of that bend, taken from the snapshot just before the cut. The pre-cut version is drawn as a thinned band (K − 2 strands, decohered with coh ≤ 0.5) that follows the loop, so it overlaps the oxbow trace and the present at the neck. It is neither history (the oxbow) nor the present: it is the path not taken, still being drawn. It crosses the live channel at the neck, where the two versions diverge, and that crossing *is* the tangle. The two outcomes of a decision are superimposed exactly where it was made. That is the most direct answer to "make you ask what's really going on", and it cannot be imitated from AARON, because it depends on this process's own editor. Risk: it reads as a doubled or ghosted drawing error. Kill it if a reader cannot tell which line is present within 2 s, *and* nothing else in the cell has a band. Rarity: at most one per sheet, only on the largest cutoff.
