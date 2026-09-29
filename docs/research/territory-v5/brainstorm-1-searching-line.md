# Territory v5 brainstorm 1: the searching line

Lens: pentimenti as a mechanism. Base = v2 `Territory` border/outer runs (sheet K/O).

**Where I disagree with the lead.** In the sketch the restatements are not scattered error around one "true" contour. Each pass commits to a different, slightly wrong idea of where the form is. The sling band shows this best: four strokes, evenly separated and not converging, which is a border drawn in four positions. With seed noise (a random offset per pass) the result is fur, or the ribbed doubles of round 2's S sheet. So each pass has to differ for a *reason the drawing contains*. v2 already holds one: the border *moves* as each core arrives, and today the engine discards that history. Ideas 1 and 2 are the core. 3 to 6 are how strokes behave inside that frame.

**Engine prerequisite (all ideas).** The `Sheet` owner grid forbids overlap, and restating needs overlap. Give each stroke a `lineage` (the contour-graph edge it serves). `hit()` treats ink of the same lineage (and of lineages sharing a junction node) as passable, and all other ink as the usual wall. That way never-overlap still separates unrelated forms and only stops applying within a restated contour. Build the **contour graph**: nodes = triple points plus run ends (where `runs` faded or hit ink); edges = runs, tagged with camp pair, `s` (contest), and arrival index.

---

## 1. Sediment: restatements are the border's own history
**Decision:** where a border *was* at each earlier arrival that changed topology, and whether that past position is still worth drawing.
**Mechanism:** In `arrive()`, snapshot `contours(S, L)` on every topology change (`topo`) and whenever `pending` would fire, not only the latest. For each final-graph edge, match earlier snapshots by nearest-point projection within ~8 mm. Each matched snapshot becomes a candidate pass. Draw passes oldest to newest, each through `walkLine` with `lineage` = the edge, so each walks in beside the previous one. Where snapshots nearly coincide (the border was stable), the passes pile into 3 to 5 near-coincident strokes, and a later pass may skip a stretch the earlier ones already carry. Where the border migrated, the passes fan out into a band that is wide at one end and pinched at the other. That is the sling.
**Weight:** stable borders get dark; borders that were fought over become bands; the latest-arrived borders stay single and thin. The history supplies the unequal authority, not a dial.
**Failure:** evenly spaced snapshots give tree rings or topo maps (round 3's G sheet). **Kill:** on the sheet, any band with ≥4 strokes at near-equal spacing along its whole length. Require snapshots gated by topology change and allow at most 2 contiguous parallel passes before a pinch.

## 2. Good continuation across the junction
**Decision:** at a junction, the pen takes the *smoothest* exit, not the one belonging to its own camp.
**Mechanism:** Walk each pass along the graph, not along one edge. At a node, score the outgoing edges by turning angle (plus a small bonus for the edge with the fewest passes so far) and take the lowest. The camp label is ignored, so one stroke leaves lobe A's contour and becomes lobe B's without lifting: the big S in the sketch that serves two forms. Successive passes through the same node can choose differently, since the fewest-passes bonus shifts. That gives the X-crossings and the braided knot at junctions. Stop at a node whose best exit turns more than ~110°, and hand that end to idea 3.
**Weight:** every route runs through junctions, so ink collects there on its own and the free curves stay thin, which is the density map the lead described.
**Failure:** every triple point becomes a star or hub knot, and the drawing reads as a road network. **Kill:** junction knots all the same size, or long S-strokes crossing the whole page like highways. Cap a single stroke at 2 junction transfers.

## 3. Hooks where the surface turns away
**Decision:** hook a line end *only* where the contour stops because something is in front of it.
**Mechanism:** Classify run ends. **T-ends** (the run stopped against older ink; `walkLine` broke on `hit==='ink'`) are occlusions, and they get a hook: 2 to 5 mm curling *toward the owning camp's interior* (sign from the gradient of `lg[k]-m`), tucked under the occluder. **Fade-ends** (the `runs` gap) get no hook, only a taper that lifts early. Restated passes differ at ends: pass 1 stops short, a later one overshoots the T and then hooks back, as `handLine.over` already does, but with the curl sign set by the camp instead of by 70% chance.
**Weight:** hooks are tiny local density that says "behind."
**Failure:** curlicues and paisley (the K1/K11 spirals are already on the edge). **Kill:** hooks at more than ~30% of ends, or any hook longer than 6 mm, or hooks curling outward.

## 4. The pass-state machine (correct / overshoot / abandon / commit)
**Decision:** each new pass reads the *previous pass* and chooses an attitude.
**Mechanism:** Measure the previous pass's signed offset `e(s)` from the target polyline (the target comes from idea 1's snapshot, or from the edge). Then the state machine, per stretch of about 15 mm:
- **correct**: |e| > 1.5 mm, so aim at `target − 0.6·e`. The new stroke crosses the old one, and that crossing is where a searching line reads as searching.
- **overshoot**: the previous pass stopped short of a node, so extend 3 to 8 mm past it.
- **abandon**: 2 or more passes already agree within 0.5 mm here, so lift and skip ahead.
- **commit**: the last pass on edges with low `s` (hotly contested) gets `wander`×0.3 and `loose` low. It is firm and is the only near-smooth line.
The pass count per edge is `1 + round(4·(1−contest)) ± 1`, so contested borders get searched and quiet ones get one line.
**Weight:** crossings and near-coincidences along contested edges; free edges stay single.
**Failure:** used alone (without idea 1) it becomes a uniform "sketchy filter" (every line jittered 3×), which is exactly one handwriting everywhere. **Kill:** if more than about 60% of edges get 3+ passes, or cells look alike across seeds.

## 5. Worrying: tangle where the drawing doubts itself
**Decision:** dwell where the passes disagreed most.
**Mechanism:** After the passes, compute per-node *doubt* = spread of pass endpoints plus the number of crossings within 6 mm. For the top 1 to 3 nodes in a cell, and only those, run a worrying walk: `walkLine` with the lineage wall off, targets drawn from a shrinking random orbit (radius 8 mm → 2 mm) around the node, biased along the incoming tangents, 60 to 200 mm of ink. The result is textural there, and organic line holds everywhere else.
**Weight:** the true darks.
**Failure:** hairballs and scribble clouds, which read as erasure or fur. **Kill:** a knot with no line leaving it, or a knot away from any junction, or more than 3 per cell.

## 6. Protagonist economy
**Decision:** the drawing picks *one* form to believe in and stays sceptical about the rest.
**Mechanism:** After the base graph is built, pick the camp region with the most junction-shared edges and the longest history (idea 1 snapshots) as protagonist. It gets the full pass budget; neighbours get ⅓ and distant regions get one pass or nothing (outer edges fade as in v2). The review's strongest finding for this lens: unequal treatment (Z7, V11) reads as deliberate. A second, contradicting protagonist at 20% probability gives two registers pulling against each other.
**Weight:** a single heavy mass with a thin periphery, or two masses in tension. That answers the "bit of either" (single mass or all-over) question per cell.
**Failure:** a centred dark logo on a grey scatter. **Kill:** protagonist centroid within 20% of the cell centre on more than half the sheet, or a protagonist that is a closed dark ring.

---

## Rank

1. **Sediment (1)** because it answers "what's really going on" with something true. The restatements record the ground being fought over, so they are coherent without being predictable: every seed's history differs, and no noise parameter produces the variation. It explains the sling rather than imitating it, and it keeps v2's strokes, replayed as time.
2. **Good continuation (2)** because it produces the sketch's strangest quality: lines that belong to two forms at once, forms that do not close on their own terms. Junction density also comes free. Together, 1+2 give weight at junctions and stable borders and lightness on the free curves, with no fill and no second geometry path. Ideas 3 and 4 are the stroke-level layer that makes 1+2 look hand-searched, so build them next. Keep 5 and 6 as later dials.

**First experiment:** 1+2+3 on K3, K7, K10, K12 (the most-connected graphs) against v2 plain, one pen at 0.3 mm, with each pass's snapshot index recorded in the recipe so the review can tell history from noise.
