# Meander 3 — brainstorm (Opus)

Unless noted, everything below is a post-pass over what is already drawn (`out` + `lin` + `erased`). Ranked best-first within each section.

**Riskiest single idea: A4 (long sweep).** It is the bridge Ian drew longest, and the one most likely to read as a second drawing, or as a river crossing, if its landing is wrong.

## Shared primitive: the drawn-stroke index

After all `emit()`s, flatten `out` into polylines tagged `{ch, kind, id}` at 0.5 mm with tangents, in one `pointHash(…, 3)`. A and B query it.

## A. Liminal bridges

Site finders. Each site yields `(P, tP)` on stroke *a* and `(Q, tQ)` on stroke *b*, with `lin(a) ≠ lin(b)` and not `related`:
- **X, crossing.** Two segments intersect at a crossing angle θ in 25–155°. The `put()` cuts (`endT/startT`) already record these.
- **N, near-contact.** Closest approach of 1.5–6 mm over a run of 5 mm or more, with no intersection.
- **E, end-points-at.** A piece end whose tangent ray hits another stroke within 8–40 mm, at a ray angle of 45° or less to that stroke's normal.
- **V, cusp.** Two piece ends of different lineage within 4 mm whose tangents make a V of 20–70°.

**Scoring.** Choose 1–4 per sheet, without resolving the picture:
`score = Ar(site) · rarity · (1 − coverage)`
- `rarity` down-weights a site within 30 mm of an already chosen bridge, a hook (`hooksAt`) or a search spot.
- `coverage` is ink density in a 10 mm disc. Skip dense knots; bridges go at the *edge* of a tangle, never inside it.
- Hard cap: total bridge length ≤ 6 % of total ink.
- Take the top site, then re-score. Stop at `N = min(4, 1 + Poisson(1.2))`.

**Curve construction.** A cubic Hermite from `(P, tP)` to `(Q, tQ)` with handles `h = k·|PQ|`, k ∈ [0.35, 0.55]. Then run 3 passes of curvature smoothing (Laplacian on the angle, not the position) to make it clothoid-ish: curvature ramps, with no arc-then-line kink. Reject if the resulting max |κ| is above 1/3 mm⁻¹ or the curve self-intersects. Draw it with `firm` at A × 0.5 and tremor 0: **calmer than its surroundings**, which is Ian's note on every blue curve.

| # | Mechanism | Site | Construction |
|---|---|---|---|
| **A1** | **Fillet / cup** | V, or X with θ < 70° | Offset both strokes by r (2–6 mm) into the acute sector. The fillet is the Hermite between the two offset points, where the circle of radius r touches both. Ends *overshoot* the tangent points by 2–5 mm along each stroke, so it grips rather than joins. "Cup": the same thing under a crossing, on the side away from the denser ink. |
| **A2** | **Peel-off echo** | N, or X at a shallow θ | Run parallel at offset d = 1.2–2.5 mm inside stroke *a* for 15–40 mm. Then depart with a Hermite and land tangent on *b*. The parallel run should *drift* (d ramps ±40 %); a fixed offset reads as ruling. |
| **A3** | **Continuation S** | E, a piece end of *a* and a mid-stroke of *b* | Hermite from the end of *a* (tangent continued), landing tangent on *b*. Stop 1–3 mm *short* of *b* 50 % of the time: an unclosed join. Inflection allowed, but only one. |
| **A4** | **Long sweep** | E, with a ray length of 40–120 mm across another band | One Hermite, max κ < 1/25. It must cross exactly one foreign band and land tangent. It is the riskiest idea: cap one per sheet and require `Ar < 0.5` along 70 % of its length, so it travels through quiet ground. |
| **A5** | **Short edge arc** | X near a tangle zone (`tangleZones`) | An 8–15 mm arc that crosses a band edge at 60–90°, curving toward the knot. |

**Parallel echoes that resolve at different points (A6, a modifier on A1–A4).** With probability 0.4, a bridge gets 1–3 echoes at offsets of 0.9–2.2 mm, with **non-uniform gaps** (reuse ringTest's cv: require cv > 0.35). Each echo lands on a *different target*, or at a different arclength on the same target: the inner echo lands early, the outer one runs on and lands further along, or on the next stroke its ray meets. Each echo is its own Hermite with a shifted landing, not an offset curve.

**The liminal plane (A7, layer order).** Bridges are emitted **last**, as `kind:'bridge'`, with `put(…, {erase:false, cross:true})`, so they pass *over* the ink cuts. That is the plane in between: nothing beneath clips them, and they clip nothing. Better:
- Before drawing, mark the bridge's own corridor into `erased` at r = 1.2 mm.
- Re-put only the `trace`/`oxbow` history items that cross it, so the history goes under the bridge while the present bands go over.

Three depths: bands, bridge, history.

**Rejection rules, applied per candidate:**
- **Closure.** If the bridge plus the two host strokes bound a region of area < 400 mm² with perimeter/area < 0.4 (a bean), reject it. Test with a quick polygon union on 10 mm of each host either side.
- **Bullseye.** More than 2 echoes that keep the same sign of curvature over more than 200° of turning: reject.
- **Ruling.** Echo gap cv < 0.35, or echo lengths within 15 % of each other: reject.
- **Crossings.** A bridge may cross at most one stroke of foreign lineage (A4 exactly one; all others zero).
- **Shape.** Total turning ≤ 180°: never a loop.

## B. Stylised accents ("eyebrows")

In the crop: 3–6 arcs on the **convex outside** of a sharp bend, uneven gaps of about 0.8–1.5 mm, unequal lengths growing outward, ends staggered more on one side. The offsets fan out; the arcs do not share a centre.

| # | Mechanism |
|---|---|
| **B1** | **Bend-bound eyebrow.** Site: on a band edge strand (k = 0), a curvature peak with \|κ\| > 1/8 mm⁻¹ over a turn of 60°–160°. Build n = 3–5 arcs. Arc j sits at offset `d_j = d_{j-1} + g_j`, with g_j drawn from {0.7, 1.0, 1.4} mm (shuffled, never monotone), and `d_0` = 0.8 mm. Arc j covers the bend angle window × (0.6 + 0.12 j), with its centre shifted *downstream* by 0.1–0.2 × length per step, so the stack leans instead of nesting concentrically. Taper: the outermost arc is broken once (a 1–2 mm lift). Hand: `firm`, tremor 0, A × 0.3, the most deliberate marks on the page. |
| **B2** | **Tie to chaos.** Placement is not global. For each tangle zone and each search spot, pick the nearest qualifying bend within 15–45 mm, at 1–2 accents per chaos zone and ≤ 3 per sheet. No chaos zone, no eyebrows. |
| **B3** | **Knot counterweight.** In the seed-22 junction, the small closed teardrop knot is itself a stylised element. Where a V site (A) is chosen, allow a 3–5 mm teardrop loop at the cusp (with one 0.5 mm gap, so it is not strictly closed), as an alternative to a fillet. At most 1 per sheet. |

Guards: B1 runs through `ringTest` (the cv rule) and a new **centre-spread test**. The fitted arc centres must span ≥ 1.5 mm. A shared centre means a bullseye or tree ring, so reject. Never place an eyebrow on the concave side.

## C. Chaos budget

| # | Mechanism |
|---|---|
| **C1** | **Two-zone hand field.** Choose 1–2 chaos centres at the top of `Ar` (or at the tangle zones if there are any), each with a radius of 25–45 mm. Define `χ(x,y)` = the max of the smoothsteps. Every `put()` interpolates its hand between `calm` (the firm hand at A × 0.4, over 0.5, lift 0.05, tremor 0.01) and the current `loose` by χ at the stroke midpoint. Outside the zones, strokes become smooth and deliberate. Search and tangle fire only where χ > 0.3. |
| **C2** | **Pre-smooth the present.** Outside χ, run `smoothPts(c.present, 3)` plus one curvature-flattening pass before `bundleGeom`. Most of the wobble comes from the migration wiggle, not the hand. |
| **C3** | **Budget as ink share.** Target a chaotic-ink share of 12–20 % of total length (strokes with χ > 0.5). Over: drop the lowest-`Ar` search spots and tangle zones. Under: promote one. One number, one page control. |
| **C4** | **Lift discipline.** Lifts (dashes) are allowed only inside χ, or on abandoned reaches. |

## D. Composition

| # | Mechanism |
|---|---|
| **D1** | **Second crossing trunk.** After the trunk is seeded, add trunk 2 as a `noiseWalk` started from a point at 35–60 % of the sheet width off trunk 1's midpoint, heading 50–110° off trunk 1's mean direction, length 180–300 mm. It must cross trunk 1 exactly once, with a retry budget of 8. `sim.pairs` does not relate them, so `put()` cuts both at the crossing, and that crossing becomes the prime A1/A2 site. |
| **D2** | **Replace `randomSheet` for meander.** A `meanderSheet(seed)` of 3–5 cores only: one long spine (hook or arc, 120–200 mm), one counter-spine (D1's direction), and 1–3 short hooks near the spine's bends. Drop `zig` and `line` from the pool. Place cores off-centre (as in seed 10) so negative space is authored. |
| **D3** | **Junction seeding.** Pick a junction J (jittered golden-section point) and make 2–3 `graft` sprouts start within 20 mm of it. That manufactures the seed-22 knot on purpose; B2 then fires there. |
| **D4** | **Mass asymmetry check.** Bin ink into 3×3 cells; reject a seed (re-roll the core RNG ≤ 4 times) if ink is even (entropy > 0.9·max) or if one cell holds > 45 %. (Seed 10: 2–3 heavy cells, 4 empty.) |

## Suggested build order

C1+C2, D1+D2, A1/A3 with A7 and the rejection rules, B1+B2, A6, then A4 behind a flag.
