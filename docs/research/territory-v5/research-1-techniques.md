# Territory v5 research 1: implementation techniques

Scope: eight shortlist items, judged against the v2 engine (`arrive`, `contours`, `runs`, `walkLine`, owner grid, `handLine`, contour graph). Budget: 24 thumbnails in <=5 s, i.e. ~200 ms per thumbnail, all in plain JS on a 300x218 grid. I did not run any of this code; costs are estimates from grid size (65k cells) and the walker's existing per-step cost. Searches turned up almost no code aimed at *this* problem (history-of-a-front as ink); most references are the nearest published mechanism. I say so where the fit is loose.

## 1. Sediment / palimpsest borders

Techniques:
- **Time-stamped level sets, not curve tracking.** Do not match curves between snapshots by Frechet. Store, per arrival, the scalar `D_t = F_a - max F_other` on the grid (or only its coarse 2 mm version, ~16k cells). Border position of snapshot t near a final-border point p is found by walking the gradient of `D_t` from p to its zero crossing: a 1D root find along the normal, 3-6 samples. Correspondence is then free (same normal, same p) and never fails on topology change. Frechet / partial matching ([Alt-Godau style, CGAL manual](https://doc.cgal.org/latest/Frechet_distance/index.html)) is O(nm) per pair, needs a threshold, and breaks exactly where the interesting merges and splits happen.
- **Displacement profile d_t(s)** along the final edge, then draw each ghost as `final(s) + d_t(s)*n(s)`, smoothed, clipped where |d|>20 mm (engine brainstorm 2's rule) or where the normal search finds no zero crossing. This gives the fan-and-pinch for free: d_t -> 0 pinches.
- **Stroke correspondence for the pen.** Each ghost is a polyline handed to `walkLine` as target with lineage = edge id (see item 8). Reference for the general idea of parametrising restated strokes on a base stroke: [Kalnins et al. 2002, WYSIWYG NPR](https://gfx.cs.princeton.edu/pubs/Kalnins_2002_WND/index.php) (strokes stored as offsets from a base path and re-emitted); loose fit, not the same problem.
- Dedupe with [Schneider curve fitting](https://github.com/soswow/fit-curve) only if ghost counts explode; usually unnecessary.

Recommended: snapshot `D` at 2 mm only on topology change (cap 6 per sheet), 1 to 3 ghosts per edge chosen by |d| spread, drawn oldest first.

Cost: snapshots ~16k floats x 6 = trivial. Ghost projection ~ edge length/1 mm x 5 samples x 6 snapshots ~ 30k evaluations of `D`. Under 20 ms/thumbnail. Ghost walking is the same cost as an extra border line each.

Pitfall: the normal search jumps between adjacent fronts (a ghost snapping to the wrong camp pair). Constrain by requiring the camp labels on both sides of the found zero crossing to equal the edge's pair; discard otherwise. Second pitfall: even spacing gives tree rings; select snapshots by topology change, not by index.

## 2. Contest register field

Techniques:
- **Register = per-sample walker parameter vector**, not a label: `r(s) = (contest, age, junctionDist)` from `runs()` mapped to (sway, restate count k, tangle probability, lift probability). Interpolate with a smoothstep hysteresis (two thresholds) so the stroke does not chatter between registers.
- **Tangle as bounded excursion, not a separate renderer.** Reference mechanism: [Pedersen and Singh, Organic Labyrinths and Mazes](https://www.dgp.toronto.edu/~karan/artexhibit/mazes.pdf) (Brownian motion + smoothing + short-range repulsion evolves a curve into dense but non-crossing convolutions; an existing port: [twentylemon/organic-labyrinth](https://github.com/twentylemon/organic-labyrinth)). For pen use: replace with a *self-avoiding random walk with curvature persistence* on the occupancy grid: step 0.6-1.0 mm, turn ~ N(0, 25 deg) with 0.7 persistence, reject moves that land within 0.35 mm of own ink, radius bound R(t) shrinking from 8 to 2 mm around an anchor. This is exactly brainstorm 1 idea 5's "shrinking orbit".
- **Tone by continuous line** ([TSP Art, Kaplan and Bosch](https://cs.uwaterloo.ca/~csk/publications/Papers/kaplan_bosch_2005.pdf)): needs a solver and a tone image; the result is uniform, anchorless line. Not recommended here: it makes tone the boss, and you want history to be.
- **Circular scribble** (Chiu et al. 2015, "Tone- and feature-aware circular scribble art", Computer Graphics Forum 34(7); no URL verified): a spiral/loop parametrisation whose radius follows tone. Useful as the loop primitive for the "knot" (loops with slowly drifting centre), cheaper than a random walk and more legible as hand.
- Stipple/stroke stipple background: Deussen et al. 2000 "Floating points" (no URL verified) (Voronoi relaxation); irrelevant unless you want dots.

Recommended: field-driven walker state + bounded self-avoiding orbit knot (with loop primitive as an option). The orbit walk is a `walkLine` with the lineage wall off and a target generator that returns the next orbit point.

Cost: the walk is the expensive part: 100-200 mm of ink ~ 250 steps x occupancy check (9 cells) ~ 5k ops; trivial. Danger is count, not cost.

Pitfall: knots as beads on a string (even spacing, same size). Draw knot size from `age` and place by importance sampling on `contest*age` with minimum spacing 40 mm, not by threshold.

## 3. Good continuation at junctions

Techniques:
- **Turning-angle traversal with pen-down Euler-style path cover.** Treat the contour graph as a multigraph, greedily extend a path at each node by the outgoing edge with smallest deflection `|angle(t_in, t_out)|`, breaking ties by least-used edge. This is the standard step in vectorization pipelines, e.g. [Bessmeltsev and Solomon, sketch vectorization](https://arxiv.org/pdf/1802.05902) (junction resolution by tangent continuity); also gives approximately the minimum number of pen lifts.
- **Elastica / smoothness cost** for choosing among more than 2 edges: minimise `int kappa^2 ds` over the 20 mm either side of the node; approximate with a cubic Hermite through node using the two candidate tangents and score max curvature. Reference for the perceptual basis: Gestalt good continuation / Kanizsa contour completion; computational form in Sharon, Brandt and Basri and Mumford's elastica (not searched; I cite from memory, unverified: check before relying on it).
- **Tangent estimation at a triple point is the fragile part**: use the field itself, tangents = perpendicular to `grad(F_a - max F_other)` sampled 2 mm off the node along each edge, not the polyline's last segment.

Recommended: implement as edge-sequence planner returning arc-length-parametrised polylines (composed of edge polylines joined by Hermite blends across 4 mm around the node). Cap 2 transfers per stroke.

Cost: negligible graph work (tens of nodes). The blend needs the walker to accept a target rather than descending the field; `walkLine` already does pursuit.

Pitfall: at a junction the field tangents of different camp pairs disagree by 120 deg; smooth blending across a Y creates a kink at the ~110 deg limit. Stop the stroke there and let item 4 hook it, as brainstorm 1 says.

## 4. The line that changes jobs; cusps and T-endings from a height field

Techniques:
- **Apparent-contour ending rule** ([Koenderink 1984](https://journals.sagepub.com/doi/10.1068/p130321), radial curvature vanishes at a fold cusp) . 2D fake: treat each camp's smoothed log-field `h_k = log S[k]` as a height. Contour = `h_k = c`. "Front" side of a run end is the side with larger `h`, and the run should *end by turning toward the lower side*, curvature increasing to a cusp; tangent aligned to the "view direction" you choose (global, e.g. 225 deg) at the ending. Implement as a last-8-mm bend: rotate the tangent by `phi(u) = phi_max * u^2`, u = 0..1 over the last 8 mm, sign from `grad h` relative to the tangent.
- **Suggestive contours** ([DeCarlo et al. 2003](https://gfx.cs.princeton.edu/pubs/DeCarlo_2003_SCF/index.php)): zero crossings of radial curvature `kappa_r = n^T H(w) n`-ish with `Dw kappa_r > 0`. Height-field version: for view direction `w` in the plane, radial curvature is second derivative of `h` along `w`. Find zero crossings of `d^2h/dw^2` (grid 2nd difference, marching squares) where the gradient magnitude along `w` has the sign that the suggestive rule requires, then cut short (they only run 5-25 mm). Yields short "almost-contours" that run out of a border and stop, which is the cusp-ish tail the sketch has. Strictly this is 3D theory faked on a 2D field; expect it to look plausible only with an H tuned smoother (sigma ~3 mm).
- **Illustrating smooth surfaces** ([Hertzmann and Zorin 2000](https://cims.nyu.edu/gcl/papers/hertzmann2000iss.pdf)): principal-direction hatch; useful for lip/fold direction choices.
- Lip/fold/thread (brainstorm 3 idea 1): offset copy = polyline offset by 2 mm using normal * `sign(F_a - F_b)`; fold = reverse traversal with offset 2-4 mm, 10-30 mm long starting at a curvature peak (peak picking on smoothed curvature).

Recommended: implement only (a) the cusp-bend ending, (b) lip via offset copy, (c) fold at <=3 curvature peaks per cell. Skip full suggestive contours unless (a) looks like hooks-everywhere.

Cost: curvature, offsets, peaks all O(polyline points) (~5k points per thumbnail). Suggestive contours add a marching squares on 16k cells ~ 5 ms. Cheap.

Pitfall: offset polylines self-intersect on the concave side; use a small-scale offset with a miter limit and trim loops (cut where `dist(offset, source) < 0.8*d`). Also ribbon/drapery clichés (brainstorm's own kill test).

## 5. Searching strokes responding to previous passes

Techniques:
- **Pass-state machine** (brainstorm 1 idea 4) built on *signed offset* `e(s)` between previous pass and target: correct by `target - 0.6 e`. Use the occupancy grid with per-cell store of "last pass id and signed offset" (rasterise the previous pass's normal displacement into a 2 mm grid, ~16k cells) so the next pass reads it in O(1).
- **Pentimento / stroke history**: [Kalnins et al. 2002](https://gfx.cs.princeton.edu/pubs/Kalnins_2002_WND/index.php) stroke-as-offset-from-base; for overshoot statistics, see the humanised drawing literature summarised in [Hertzmann's stroke-based rendering survey](https://www.dgp.toronto.edu/~hertzman/sbr02/hertzmann-cga03.pdf); no rigorous published "pentimento simulator" I found, so parameters are yours to tune. Reasonable defaults: overshoot 3-8 mm, correction gain 0.4-0.7, tremor 0.2 mm at 8 Hz-equivalent along arc length.
- **Correction as damped spring on the perpendicular offset**: `o'' = -k(o - o_target) - c o'` integrated along arc length; produces crossing ("searching") naturally when underdamped. That is 3 lines of code and gives better wobble than filtered noise.

Recommended: damped-spring line with the previous-pass offset raster as reference; pass count from contest (brainstorm's formula).

Cost: per pass ~ edge length steps; 5 passes x 200 mm ~ 1000 steps. Nothing.

Pitfall: uniform sketchy-filter look (brainstorm's own warning); make gain and pass count depend on the contest field and never on a global constant.

## 6. Net on a surface that misfits and frays

Techniques:
- **Evenly spaced streamlines** ([Jobard and Lefer 1997](https://link.springer.com/chapter/10.1007/978-3-7091-6876-9_5); code: [keithfma port](https://github.com/keithfma/evenly_spaced_streamlines); tutorial [allnans](https://www.allnans.com/jekyll/update/2018/04/04/beautiful-streamlines.html)). Seeds queue, separation `dsep`, terminate at `0.5 dsep`, grid-hash for lookups. Run on `grad log S[k]` for family B and on its 90-degree rotation for family A (isolines) rather than picking contour levels by hand: the two are then dual and adjacent lines form a curvilinear net.
- **Cross-field / principal directions** ([Hertzmann and Zorin 2000](https://cims.nyu.edu/gcl/papers/hertzmann2000iss.pdf), [Salisbury et al. 1994 pen-and-ink](https://dl.acm.org/doi/10.1145/192161.192185), direction-field-guided strokes; [Coherent Line Drawing, Kang et al.](https://cg.postech.ac.kr/papers/kang_npar07_hi.pdf) smooth tangent field). For a scalar height field the principal directions are the Hessian eigenvectors; a 4-symmetric cross field (rotate by 90 deg) is well defined, singular at umbilics (dome tops) where streamlines fan. Use the *gradient / isoline* pair, which has one singularity at each maximum, rather than a general cross field.
- **Misfit and fraying**: apply an affine slip (translate 2-6 mm, rotate 3 deg) to the lattice, and above threshold in the rival spill band blend the target direction from `grad S[k]` toward the direction to the nearest rival border with weight `w = S_rival/(S_own+S_rival)`; drop family-B seeds probabilistically as `w` increases.

Recommended: Jobard-Lefer on the two duals, restricted to one connected component, dsep 4-7 mm, 6-10 lines per family, followed by the blend rule.

Cost: streamline count ~ 20 lines x 100 mm ~ 2000 steps + hash checks; ~10 ms. Can afford it on every thumbnail but restrict to one per cell.

Pitfall: globe graticule (regular, closed); avoid by omitting lattice on the side away from the front and slipping it. Streamlines of a smooth bump will spiral into the maximum and pile up; stop at 0.5 dsep as in Jobard-Lefer.

## 7. Aperture / void pushing lines

Techniques:
- **Analytic repulsion warp.** Deform every polyline by `p' = p + a * g(F_void(p)) * grad_hat(F_void)`, g a smooth falloff (e.g., `exp(-(d/R)^2)`), then re-resample. This is a diffeo-like warp: no crossings if the derivative bound holds (`a * |g'| < 1`). The engine already has `S[0]` void field; no geometric pipeline required.
- **Elastic band / snake formulation**: model each line as a chain with spring lengths and repulsion from a mask SDF; relax 20-40 iterations (the Pedersen-Singh forces [PDF](https://www.dgp.toronto.edu/~karan/artexhibit/mazes.pdf) are the same family). Better when lines must slide along the rim (lip arcs) but more code and needs iteration tuning.
- **Mask distance field + level curves for the lip**: signed distance to the void mask via a two-pass chamfer transform (or Felzenszwalb EDT), lip arcs are level sets at distances 2, 3.2, 4.6 mm (unequal), kept only on the half-rim facing the heaviest camp (dot product of `n_rim` with the direction to that camp centroid > 0.3).
- **Negative space by inversion** (brainstorm 2 idea 5): score density falloff; there is no standard algorithm, so test by measurement: rasterise ink to 8 mm cells, compute radial profile vs sheet centre, kill when monotonic.

Recommended: analytic warp + SDF level-set lip. The turn-back at the rim (brainstorm 3 idea 7) is the same cusp-bend as item 4a.

Cost: EDT over 65k cells ~ 2 ms (typed arrays). Warp is per point. Negligible.

Pitfall: eye/donut/bullseye (kill tests as in the brainstorm); and the warp folds polylines when `a` is large relative to the falloff radius; check the Jacobian bound and clamp.

## 8. Lineage-based overlap permission

Techniques:
- **Per-cell owner id + lineage table.** Store `owner[cell] = strokeId` (Uint16Array) as now, plus `lineage[strokeId]` (edge id) and a union-find (or small adjacency bitset) over lineages for junction-sharing. `hit(cell)` returns free if `owner==0`, `pass` if `related(lineage[owner], myLineage)`, else `ink`. O(1); zero grid growth.
- **Permission with distance**: for related ink, allow overlap only when the separation is < d0 (e.g. 0.8 mm) or > d1 (2.5 mm); forbid the awkward 1-2 mm gap that reads as ruled hatching. Implemented as two thresholds on cell distance, on a 0.5 mm supersampled occupancy in a local window only where needed.
- **Layered ownership**: keep the first-comer wall for unrelated strokes; and within the lineage allow multiplicity counting (count[cell] <= N to cap ink density). Same idea as hatching-with-cap in the pen-and-ink systems ([Salisbury et al.](https://dl.acm.org/doi/10.1145/192161.192185)) which used priorities and stroke textures per region.

Recommended: implement first; it is the enabling change for items 1, 2, 5. About 30 lines in the `Sheet` class.

Cost: one extra array lookup per step, unmeasurable. Union-find with path compression for node-sharing.

Pitfall: lineage ids that are too coarse (whole camp) turn the never-overlap invariant off everywhere; key on the *edge* and let junction-sharing extend only to edges touching the same node within 10 mm of the node.

## Build-first ranking

1. **Item 8, lineage occupancy.** Prerequisite for 1, 2, 5; smallest change; test alone by drawing two lines of one lineage and one foreign.
2. **Item 1, sediment via time-stamped `D_t` snapshots** with normal-search correspondence. The most novel and true-to-history mechanism; cheap; pairs with 8 immediately.
3. **Item 5, damped-spring searching pass** on top of item 1 targets. Turns ghosts into a hand.
4. **Item 2, contest register field** and bounded orbit knot. Adds weight variation inside one stroke; dial down knots.
5. **Item 3, good continuation** with field tangents, cap 2 transfers. Higher risk (highways), but small code.
6. **Item 4a/b, cusp-bend endings and lip offset.** Cheap; restrict to 20% of ends.
7. **Item 7, analytic repulsion warp + SDF lip.** Later, as the aperture event.
8. **Item 6, streamline net.** Last: riskiest cliche (globe, fishnet); build only on a base that already has weight.

Unverified from memory: Sharon/Brandt/Basri and Mumford elastica citations in item 3; the Chiu et al. and Deussen et al. papers in item 2 are known only from a search listing, not opened.
