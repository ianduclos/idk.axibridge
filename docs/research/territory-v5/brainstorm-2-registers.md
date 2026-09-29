# Territory v5 brainstorm 2: registers and composition

Lens: how organic line, tangle, net and aperture mix *into* each other; negative space as an agent; one-pen weight. Written 2026-09-29 against the v2 engine (`Territory.arrive/contours/runs`, label map `L`, camp fields `S[0..3]`, per-point contest value `s` on border runs, arrival order, `disregard`, void `forbid`).

## Where I disagree going in

1. **Per-region treatment is the wrong unit now.** Round 3 praised Z for "the choice of what to do to each body". That is side-by-side by construction: one register per shape. Ian now asks for registers "mixing into each other". A register has to be a *field sampled along the stroke*, not a label on a camp. One pen-down stroke should be able to be organic, then restated, then knotted, then net, with no seam.
2. **Round 3 said to drop territories. Keep the v2 borders as the skeleton.** Ian said b = "the strokes from the previous session". The bodies failed as "too concrete" because they were closed. Borders are open by nature and already make the eye do work (K3, K12).
3. **Voids are wasted as omissions.** The reviewer could not see them (O vs K). The engine makes one real decision about emptiness, then hides it. Voids should be the aperture mechanism.
4. **Density should come from the drawing's own history, not from added fill.** Hatch (round 2) and fills (round 3) read as texture laid on top: weather, engraving, coral. Ian's sketch gets its weight from bundles of near-parallel restated lines that drift apart and pinch together.

## Ideas

### 1. Palimpsest borders (ghosts of where the front used to be)
**Decision:** a border that moved during the arrivals leaves its earlier positions on the sheet. A border that never moved gets restated in place until it is heavy.
**Mechanism:** in `arrive()` snapshot `contours(S, L)` borders per arrival, tagged by camp pair. After the last arrival, match each final border point to the nearest same-pair point in each snapshot (≤25 mm). Displacement `d_j` per point per snapshot:
- `d < 1.5 mm`: add a restate pass along the final line with 0.3–0.6 mm jitter.
- `1.5–20 mm`: draw a ghost stroke through the snapshot positions. Use `walkLine` with `touch`, so ghosts converge onto the final line where `d → 0`. That gives fans that open and pinch, like the bottom bundle in the sketch.
- `>20 mm`: drop it. The front jumped, and the jump shows as a gap.

**Weight:** stable fronts are dark (N passes). Contested fronts are sprays of light lines. Outer edges keep their v2 fading and get no history, so they stay faint.
**Failure:** evenly spaced offsets read as a contour map or tree rings. **Kill:** more than a third of bundles have near-even spacing, or every border bundles. At most 2–3 fronts per cell should carry history.

### 2. Contest register field (register changes along one stroke)
**Decision:** how hard two camps are fighting at a point decides how the pen behaves there.
**Mechanism:** `runs()` already computes contest `smooth(eps, 0.4, s)` per point. Add `age` (how many arrivals that stretch survived unchanged) and `junction` (distance to a triple point in `L`). Then map to walker state, interpolated per point:
- Low contest: long smooth line, high sway, breaks allowed. This is the "organic" register.
- Mid contest: 2–3 drifting restatements.
- High contest × age: a local excursion. The walker crosses the border and loops back for `k ∝ age` turns, making a knot that is **tangle**. Then it releases and continues the same stroke.

**Weight:** it pools at old stalemates and triple junctions. Free edges stay thin.
**Failure:** knots spaced like beads on a necklace, or scribble everywhere. **Kill:** knots at even intervals, knots all the same size, or tangle on more than 25% of border length.

### 3. The net that frays (one lobe netted, contaminating its neighbour)
**Decision:** one lobe of one camp is "held". The machine draws that holding as a lattice, and the lattice loses its discipline as it crosses into rival ground.
**Mechanism:** pick one *connected component* of one camp. The choice rule, recorded: the component of the last-arriving camp, or the most fragmented one. Never the whole camp.
- Family A: isolines of `log S[k]` at 4–7 mm spacing.
- Family B: short streamlines along `∇S[k]`.

Together they form a curvilinear, non-orthogonal grid that follows the field. Dilate the lobe by 8–15 mm. In the spill band, raise tremor with rival field strength and randomly drop cells. Family-B lines stop following the gradient and pursue the nearest rival border, so the net turns into tangle at the front. Leave 30–50% of the lobe unnetted, on the side away from the front.
**Weight:** the net is mid-grey, the fray at the front is densest, and the unnetted part of the lobe is nearly empty.
**Failure:** globe graticule, fishnet stocking, map grid. **Kill:** the net reads as a sphere or map, or covers the lobe edge to edge.

### 4. Aperture as a pushing void (emptiness with a lip)
**Decision:** a void is not left out. It displaces. The hole is shown by what crowds against it, and only from one side.
**Mechanism:** use one void core per sheet (`S[0]`), never outlined. Push nearby border and outer points outward along `∇S[0]`, scaled by field strength, so fronts bend around it. On the half of the rim that faces the heaviest camp, add a **lip**: 3–6 restated arcs that follow the `S[0]` isoline and then peel away into ordinary borders. The far rim is left open, so the aperture leaks into the ground.
**Variant, strange and decided:** the net from idea 3 appears *only inside the aperture*, as if seen through it, and nowhere else on the sheet. You then ask what is behind the page.
**Weight:** the darkest mark on the sheet sits against the emptiest place.
**Failure:** an eye, a donut, a bullseye. **Kill:** a lip that goes around more than ~60% of the rim, or reads as an eye across more than 2 of 12 cells.

### 5. The winner is silent (composition by inversion)
**Decision:** the camp that holds the most ground gets the least ink. Its territory is the negative space, and it is shaped only by its rivals' pressure.
**Mechanism:** rank camps by area in `L`. For the largest:
- no interior, net or knots;
- its borders are drawn from the rival side only (restates offset into the rival's ground);
- its outer edges are suppressed.

Spend the whole ink budget on the smallest or latest camps. The result is a large, specific empty shape with heavy, busy edges on some of its sides.
**Weight:** extreme and unequal.
**Failure:** a vignette (dense rim around a blank centre) or a plain frame. **Kill:** density falls off radially in more than a third of cells. The empty shape must touch the paper edge or be asymmetric.

### 6. Disregard as a second hand (a rival truth in a rigid register)
**Decision:** borders drawn "as if a rival were absent" (the existing `disregard`) are a competing account of the map. They get the one rigid register: long near-straight chords with sharp corners, the "construction" authority that M5 and M3 had.
**Mechanism:** tag lines with `disregard`. Render them with `chordDests` at low curvature and sway ≈ 0. Cap them at 1–2 per cell. Where a rigid chord crosses an organic border it does not stop, and the organic line restates itself twice at the crossing.
**Weight:** small. Most of the effect is the authority contrast.
**Failure:** ruler lines that read as scaffolding (the round-1 M2 ladder). **Kill:** more than 2 rigid chords in a cell, or parallel chords.

## Ranking

1. **Palimpsest borders.** It takes weight straight from the composition's own history. Ian asked for the old strokes as the base, and this keeps them and makes them heavier. It is closest to what his sketch actually does: bundled, drifting, pinching restatement. It also answers "what's really going on": the viewer can see that the front used to be somewhere else. Snapshots are already computed per arrival, so it is cheap.
2. **Contest register field.** It is the only idea here where a register turns into another *inside one stroke*. That is the literal answer to "mixing into each other". It is also the infrastructure that ideas 3, 4 and 6 need, since they are all walker-state changes driven by a field. Build it once, then treat net-fray and the aperture lip as extra inputs to the same field.

For the first sheet I would pair 1 and 2 with the silent-winner rule (5) toggled per cell, and hold the net and aperture back for round 2. The net is the riskiest cliché here, so it should arrive on a base that already has weight.
