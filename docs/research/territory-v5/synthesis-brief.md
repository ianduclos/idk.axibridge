# Territory v5 build brief (synthesis, 2026-09-29)

Base: v2 lines as drawn in `Territory.arrive()` (K = borders+outer, O = +voids), `order='reversed'`. v5 is a **post-pass** on top of that ink, keyed to `contourGraph()` built from the drawn strokes, so cell identity survives. Nothing in `axibridge/` changes.

## 1. The instrument: three mechanisms, two rare events

**M1 Sediment → reduction (weight).** Each border's earlier positions (`T.snapshots`) become passes; a Picasso-style reduction keeps oldest+newest and throws away the middle. The sketch's sling band is 4–6 strokes that drift and pinch, not jitter around one truth. "More weight at parts, less at others" comes from history, not a dial, and the viewer can read *where the front used to be* ("what's really going on").

**M2 Register field + good continuation (mixing).** Walker state is a per-sample function of `(contest, age, junctionDist)`, so one pen-down stroke is organic in open ground, restated where contested, knotted at one or two doubt nodes, and hands itself to a neighbour's contour at a junction (the sketch's S serving two lobes; inward hooks at T-ends). This is the literal "registers mixing into each other" and the only place tangle may occur.

**M3 Silent winner + protagonist economy (negative space).** The camp holding the most ground gets the least ink; one graph component gets the full pass budget, the rest ≤1 ghost. Answers "weird compositions, negative space" and the review's finding that unequal treatment reads as deliberate (Z7, V11).

**Events (rare):** net on one lobe, aperture with lip, cancel stroke. Budgeted, never default.

Dropped: line-changes-jobs and pass-state machine (both subsumed by M2 over M1's offsets); gap coordination survives only inside the aperture event.

## 2. Data model, algorithms, order of operations

`runTerritory` line 534: `if (prm.render === 'v5') T.v5(rngFor(seed, 5151)); else …`. Force `keepHistory: true`; add `topo` to the snapshot record in `arrive()` (one field).

**2.1 Lineage occupancy (prerequisite).** `Sheet` gains `lineage = new Int32Array(maxIds)` and `related(a, b)`: same edge, or edges sharing a node. `hit()` returns `0` for owned cells whose lineage is related, `'ink'` otherwise; `mark()` unchanged. After graph construction rebuild: `this.sheet = new Sheet()`, re-`mark` every edge with `id = 1 + edgeId`, `lineage[id] = edgeId`, re-`forbid(L)`.

**2.2 Graph.** `G = contourGraph(base strokes)` where base = `this.lines` of kind border/outer. Per edge attach: `kind` (from `src` line), `pair` (sample `L` at ±1.5 mm along the mid-normal), `contest` (mean of `min(inf(k,c), max_j inf(j,c))`, as in `contours()`, sampled every 4 mm), `nrm[]` (2-point central normals).

**2.3 Sediment (M1).** For each edge and each snapshot with `topo===true` (cap 6, oldest→newest): spatial-hash the snapshot's same-kind contour points at 3.5 mm; for edge sample `p` with normal `n`, take the nearest snapshot point `q` within 20 mm with `|(q−p) − ((q−p)·n)n| < 3` mm; `d_t(s) = (q−p)·n`, else NaN. Smooth `d_t` over 5 mm; split into runs ≥ 12 mm. Per run: `|d|<1.5` **stable** (age++; restate in place, 0.3–0.6 mm toward the rival); `1.5–20` **ghost** (polyline `p + d_t n`, pinching where `d→0`); `>20` drop. On winner–rival borders keep ghosts only on the rival side.

**Reduction.** Candidate passes per edge = ghosts + stable restates + the final line. Keep the oldest ghost, the final line, and `round(spread/8)` middle passes (spread = max|d| in mm), choosing the ones farthest from their neighbours; cap 5 passes per edge, ≥40% of candidates on the heaviest edges must be discarded. Log `{edge, snapshot, d}` per kept pass in the recipe.

**2.4 Economy (M3).** Camp areas from `labels()`. Winner = largest camp: outer edges not restated, borders get pass 1 only (rival-side ghosts excepted). Protagonist = graph component maximising `Σ age·len`: full pass budget; other components ≤ 1 ghost; outer edges never gain passes. Cap: v5 ink ≤ `budgetMul` × base ink.

**2.5 Register field (M2).** Per sample of every planned pass: `contest` from 2.2, `age` from 2.3, `dJ` = distance to nearest degree≥3 node. Hysteresis on contest at 0.25/0.45 (a register run lasts ≥15 mm). Mapping: `loose = prm.loose·(0.45+1.1(1−contest))` (as `runs()` does), hand amplitude `A·(1−contest)`, the **final** pass on edges with contest>0.45 uses the firm hand with `wander 0.3` (the one committed line). Ghost passes use the loose hand.

**Good continuation.** At a node of degree ≥3, score exits by turning angle (tangents via `edgeFrom()` 2 mm out; camp ignored), 0.15 rad bonus for the least-used edge; take the lowest if < 110°, else stop. ≤2 transfers per stroke; the transferred stretch inherits the new edge's contest.

**Knots.** Doubt per node = spread of pass endpoints within 6 mm + crossings. Top 1–2 nodes per cell, ≥40 mm apart, get an orbit walk: `walkLine` with `related` true for the node's edges (other ink still a wall), targets on a shrinking orbit R 8→2 mm biased along incoming tangents, 60–200 mm of ink scaled by age, self-avoid 0.35 mm.

**Endings.** T-ends (`walkLine` ended on `'ink'`): hook 2–5 mm curling toward the owning camp's interior (sign from `∇(lg[k]−m)`), on ≤25% of ends, ≥25 mm apart. Fade-ends: taper only (drop the last 3 mm of amplitude), no hook.

**2.6 Draw.** Passes oldest→newest: `walkLine(sheet, chordDests(pass), id, prm, rng, D, {touch:true, r:0.45})` with lineage, then `handLine` (hand per 2.5). Emit `{kind:'sediment'|'commit'|'knot'|'hook'|'net'|'aperture'|'cancel', snapshot, edge}`.

**2.7 Events** (section 4), then stats.

Defaults: `budgetMul 2.5, snapMax 6, dStable 1.5, dMax 20, normalTol 3, maxPasses 5, protagonistShare 0.5, transfers 2, turnMax 110°, knots 2, knotGap 40, knotInk [60,200], hookFrac 0.25, hookLen [2,5], hookGap 25, contestHyst [0.25,0.45]`.

## 3. Register mixing, weight, tangle, emptiness

1. A stroke changes register only for a reason the drawing contains: contest changes along it (field), it transfers to another pair at a junction (continuation), it enters a doubt node (knot excursion, exiting on the same stroke), or it ends against ink (hook) vs. fades (taper). No global "sketchy" filter.
2. Weight with one pen = pass count × proximity. Target on an 8 mm raster: top-decile ink density ≥ 5× the median of non-empty cells; ≥ 50% of added ink within 20 mm of the protagonist.
3. Tangle lives only at knots (≤2/cell) and in bundles with ≥4 passes; everywhere else the line is single and organic. Textural passages ≤ 25% of border length.
4. Emptiness: ≥ 35% of 8 mm cells stay empty; the largest empty region is the winner's ground and must be asymmetric or touch the sheet edge; no ink is added inside it; outer edges keep v2 fading and never gain weight.

## 4. Event budget per drawing

Two slots, drawn in order with `rngFor(seed, 5152)`: cancel p=0.5 (1–2 strokes), aperture p=0.3, net p=0.3, rigid chord p=0.2 (one `disregard` border re-walked with `chordDests` low curvature, sway 0). Never net + aperture in one drawing this round. Events ≥ 25 mm from each other and ≥ 20 mm from knots.

- **Net:** one connected component of the last-arriving camp, never the winner, never a whole camp. Hidden height `inflate(mask, bb, 60, 0.8)`; family A = 6–10 `isoLevels` at 4–7 mm; family B = gradient streamlines seeded on the rim, `dsep 5`, stopping 2.5 mm from any line. Slip 2–6 mm, rotate 3°; 30–50% of the lobe unnetted away from the front; in an 8–15 mm spill band raise tremor with rival field, drop 30% of seeds, steer family B toward the nearest rival border.
- **Aperture:** a void (`S[0]`, O base) or else a fade gap 8–30 mm with the same camp both sides. SDF via `chamfer`; lip = 3 restated arcs at 2, 3.2, 4.6 mm on the half-rim facing the heaviest component (≤ 50% of rim); far rim open. Lines within 6 mm of the rim get the cusp turn-back; strokes within 15 mm are cut over overlapping, offset spans (Molnar).
- **Cancel:** one firm stroke 15–40 mm crossing the heaviest bundle at > 40°, stopping 3 mm past it.

## 5. Kill criteria (12-cell sheet) and test matrix

| # | Mechanism | Kill if |
|---|---|---|
| 1 | Sediment | ≥4 evenly spaced strokes along a whole band (tree rings) in >2 cells; every border bundled; heavy:light < 5:1 |
| 2 | Reduction | heaviest bundles lose < 40% of candidates; slings absent (no pinch) |
| 3 | Continuation | any stroke crossing > 60% of cell width (highway); junction knots all one size; > 60% of edges with 3+ passes |
| 4 | Knots | a knot away from a junction, no line leaving it, or > 2/cell; hairball read |
| 5 | Hooks | > 25% of ends, any > 6 mm, outward curl, or "curl motif" named in > 3 cells |
| 6 | Economy | vignette (radial density falloff) in > 4 cells; empty shape centred and symmetric |
| 7 | Net | globe/fishnet/map named, or edge-to-edge coverage, in more than 1 netted cell |
| 8 | Aperture | eye/donut/bullseye in > 1 cell; lip > 60% of rim; two apertures level |
| 9 | Cancel | parallel to what it cancels; > 2/cell |
| 10 | Whole | reviewer names "one handwriting" or cells look alike across seeds |

Test matrix (K seeds 1–12, neutral labels, `recipes.json` withheld until the review's section 2):
- **A** full v5 (M1+M2+M3, events per budget).
- **B** M1 only: isolates weight.
- **C** M1+M2, economy off: isolates composition.
- **D** O base, aperture forced (p=1, net 0).
- **E** K base, net forced (p=1, aperture 0).
- **Control** K plain.
Close views: cells 3, 7, 10, 12 (most-connected) and 5 (mass vs empty) on A, B, D, E. Ask the reviewer to date bundles (which stroke is oldest) and to name clichés unprompted.

## 6. Not this round

Suggestive contours, Fréchet matching, `D_t` field re-derivation (polyline snapshots suffice), damped-spring correction, TSP/tone or labyrinth fills, hatching or any interior fill, v4 `inflate` isolevels as visible outlines, general cross-fields, elastic-band relaxation, two-light seam, rhythm carrier, direction asymmetry, Mehretu scaffold, Cohen commitment states, net-inside-aperture, a second protagonist, gap coordination outside the aperture, per-region treatments, new interior marks, plotting, any `axibridge/` change.
