# Meander round 3: synthesis brief (Fable, 29 September 2026)

Inputs: Ian's notes and blue curves (`territory-meander-round-3.md`, binding), `v6-ref.png`, the Opus brainstorm, the engine, the page, and a 24-seed CPU profile run this session: 208 ms per sheet (24 ≈ 5.0 s); `stallW` 13 % (a linear scan over stalls per point per step), territory-v2 contour machinery ~38 % (the trunk's source).

Binding: "more deliberate for the most part", "1 or 2 more stylized elements", bridges "not an absolute rule … don't overdo". Target: the seed-22 crop, a junction with a small knot, stated arcs outside two sharp bends, everything else calm.

## 0. Decisions, and where I differ from the brainstorm

1. **Keep `randomSheet` and the territory source (D2 deferred).** Ian likes the shapes, and seeds 22 and 10 are the reference; a new core generator re-rolls the population and loses the target. Composition comes from a second trunk (D1) and junction sprouts (D3). D4 is a printed metric only.
2. **Bridges go before history, not after.** Sites come from the present (strands, search, accents); bridges are drawn `cross: true`, their corridor marked into `erased`, then M3 runs as now. Bands under, bridge over, history clipped under: three depths, no re-put.
3. **A4 (long sweep) is the last checkpoint, optional.** Ian drew it, so it is planned; it ships only if the budget holds and the shorter bridges do not already read as a second drawing.
4. **B3 (manufactured teardrop) is out.** The seed-22 knot came from the engine; stamping one is a motif. The 60–100 mm tangle is a mode of the existing zone (§2.4).

## 1. Build order and acceptance

Every checkpoint: `node smoke_meander.js 1 … 24` prints per-sheet ms, `deterministic=true` on all 24, and the metrics named. Re-render seeds 22 and 10 at defaults after each CP beside v6; the junction in 22 must survive.

| CP | Build | Accept (node) |
|---|---|---|
| **CP0** | Exact `stallW` early-out: skip a stall when `|dx| ≥ 10 ∨ |dy| ≥ 10` (`smooth(4,10,d) = 1` there). Memoise `T.labels()`. Smoke prints `ms`, `chaosShare`, `massEntropy` (3×3 ink-cell entropy / max). | 24 sheets ≤ 4.6 s; `lines` byte-identical to v6 on all 24. |
| **CP1** | χ field, calm hand, pre-smooth, search gating, share cap (§2.1). | `chaosShare` 0.08–0.30 on ≥ 20/24 at chaos 0.5; 0 at chaos 0 with no tangle, search or event; mean |κ| of k = 0 strands outside χ down ≥ 25 %. |
| **CP2** | Trunk 2, neck rule, junction sprouts, long tangle (§2.4). | `trunkCross === 1` whenever trunk 2 exists; trunk 2 on 20–35 % of sheets at complexity 0.5, none at ≤ 0.3; ≤ 1/24 flags `F`; ≤ 5.0 s. |
| **CP3** | Eyebrows (§2.2). | 0 at dial 0; 1–3 on ≥ 16/24 at 0.5; `centreSpread` ≥ 1.5 mm and `gapCv` ≥ 0.3 on every stack; ringTest never fires on one. |
| **CP4** | Index, sites X/E/V, A1 + A3, A7, rejections (§2.3). | 0 at dial 0; 1–3 on ≥ 18/24 at 0.5; `bridgeInk` under cap; bean flag `B` on 0 sheets; ≤ 5.3 s. |
| **CP5** | Echoes A6, A2, A5. | Echo `gapCv` ≥ 0.35, length spread ≥ 15 %; ≤ 4 echoes per sheet; ≤ 5.5 s. |
| **CP6** (optional) | A4 at bridges ≥ 0.7. | ≤ 1 per sheet; one foreign band crossed; `Ar < 0.5` along ≥ 70 %. |

## 2. Mechanisms

### 2.1 Chaos budget and the deliberate hand (C1–C4)

Centres: the tangle zones' midpoints (`tangleZones` exist before any `put()`), else the top `Ar` peak. Radius `r = 25 + 20u`, `u` from `rngFor(seed, 6168)`. `χ(x,y) = max_c smooth(r_c, 0.4·r_c, dist)`: 1 inside, 0 beyond r; at chaos 0, χ ≡ 0.

- **Hand blend.** `calm = { ...firm, A: firm.A·0.4, over: 0.5, lift: 0.05, tremor: 0.01 }`. `put()` blends every numeric field of the given hand toward `calm` by `1 − χ(mid)`. That is C4 too: lifts only inside χ; abandoned reaches keep `loose` unblended.
- **Pre-smooth (C2).** Before `bundleGeom`: `present[i] = lerp(smoothPts(present, 4)[i], present[i], χ_i)`. No rng.
- **Search gating.** Candidates need `χ > 0.3` as well as `Ar > 0.5`; the zone itself stays excluded.
- **Share cap (C3).** `chaosShare` = ink with χ(mid) > 0.5 over total. Search stops adding spots past `0.10 + 0.15·chaos`. Flag `C` outside 0.05–0.35.

### 2.2 Eyebrows (B1 + B2), `rngFor(seed, 6169)`

Budget `nA = round(3·accents)`. Sites: a k = 0 strand of a channel with `Kmax ≥ 3`, a curvature peak `|κ| > 1/8 mm⁻¹` turning 60–160°, within 15–45 mm of a χ centre. No χ centre, no eyebrows. Rank by `|κ_peak|·(1 − coverage)`; one per centre first, ≥ 30 mm apart.

Construction: `n = 3 + floor(3u)` arcs on the **convex** side. `d_0 = 0.8`; gaps from {0.6, 0.9, 1.5} mm without replacement, then with, reshuffled until non-monotone and `cv ≥ 0.3`. Arc j covers the bend window × (0.6 + 0.12 j), its centre shifted downstream by (0.1 + 0.1u) × its length per step, so the stack leans instead of nesting. The outermost arc is broken once (1–2 mm lift). Hand `firm`, A × 0.3, tremor 0, over 0, `put(…, {cross: true})`. Guards: fitted arc centres span ≥ 1.5 mm; skip a site whose corridor has ink coverage > 0.2. Emit `kind: 'accent'` after strands.

### 2.3 Bridges (A1–A3, A5–A7), `rngFor(seed, 6170)`; echoes `6171`

**Index.** After strands, search and accents: flatten `out` to 0.5 mm polylines with tangents, tagged `{lin, kind, id}`, in `pointHash(…, 3)`. Sites need `lin(a) ≠ lin(b)`, `!related`:
- **X**: a piece `startT`/`endT` cut; partner = `sheet.owner` at the cut cell; θ 25–155°.
- **E**: a piece end whose tangent ray (march `sheet.owner` at 1 mm) hits foreign ink within 8–40 mm at ≤ 45° to that stroke's normal.
- **V**: two piece ends of different lineage within 4 mm, tangents 20–70° apart.
- **N** (CP5): closest approach 1.5–6 mm over ≥ 5 mm, no intersection.

**Budget.** `nB = round(bridges·(2 + 3u))`: 0 at 0, 1–3 at 0.5, 2–5 at 1. Hard cap `bridgeInk ≤ (3 + 5·bridges) %` of `inkMm`. Score `Ar·rarity·(1 − coverage)`: rarity 0.3 within 30 mm of a chosen bridge, hook or search spot; coverage = ink cells in a 10 mm disc / area, skip > 0.25; skip `χ > 0.7` (edge of a tangle, never inside). Take the top, re-score, stop at `nB` or the cap. That is "don't overdo" in numbers.

**Construction.** Cubic Hermite `(P, tP) → (Q, tQ)`, handles `k·|PQ|`, `k = 0.35 + 0.2u`; three Laplacian passes on the tangent angle (clothoid-ish, no arc-then-line kink); 0.5 mm samples.
- **A1 fillet/cup** (V, or X with θ < 70°): offset both hosts by `r = 2 + 4u` into the acute sector, Hermite between the touch points, each end extended 2–5 mm along its host so it grips. Cup: the same under an X, on the side with less ink.
- **A3 continuation S** (E): tangent continued, landing tangent on b; stops 1–3 mm short half the time; one inflection at most.
- **A2 peel-off** (N or shallow X): parallel at `d = 1.2 + 1.3u` inside a for 15–40 mm, d ramping ± 40 %, then Hermite to b.
- **A5 edge arc** (X within 20 mm of a tangle zone): 8–15 mm across the band edge at 60–90°, toward the knot.
- **A4 sweep** (E, ray 40–120 mm): one Hermite, max κ < 1/25, one foreign band crossed, one per sheet.

Hand `firm`, A × 0.5, tremor 0, lift 0, over 0; `put(…, {cross: true})`; corridor into `erased` at r = 1.2; emit `kind: 'bridge'`; then M3.

**Echoes (A6).** p = 0.4: 1–3 echoes at offsets 0.9–2.2 mm, gap `cv ≥ 0.35`, each its own Hermite landing at a different arclength on b (± 5–15 mm) or on the next stroke its ray meets; lengths differ ≥ 15 %; ≤ 4 per sheet.

**Reject** on: max |κ| > 1/3 mm⁻¹; self-intersection; turning > 180°; any foreign crossing (A4: exactly one); **bean**: bridge plus 15 mm of each host enclose 30–400 mm² (under 30 is a fillet pocket, over 400 open ground); echo ruling (cv < 0.35 or lengths within 15 %).

### 2.4 Composition (D1, D3, long tangle)

- **Trunk 2** (`rngFor(seed, 6167)`): fires when `u < smooth(0.3, 0.9, complexity)` (0 at ≤ 0.3, ≈ 0.26 at 0.5, 1 at 0.9). Start 35–60 % of W off trunk 1's midpoint along its normal, heading 50–110° off trunk 1's mean direction, `noiseWalk` 180–300 mm, `trimToSheet` 12; retry ≤ 8 until it crosses trunk 1 exactly once, else none. Class `trunk`, `S0 = 5`, counted in `nCh`. **Neck rule:** a trunk–trunk neck in `editor` pushes a stall only (no refuse event, no `pairs` entry), so the crossing stays put and `put()` still cuts both there. Smoke prints `trunkCross`.
- **Junction sprouts (D3)** (`6172`): with trunk 2, two top-up sprouts start within 20 mm of the crossing: the seed-22 knot on purpose, and χ then centres there.
- **Long tangle:** at chaos > 0.5 the depth-1 dip may take half-width 30–50 mm, extended 1.5× toward the nearer terminal so it runs out and thins. The `K` flag stays the guard.

## 3. Determinism

Existing streams stay: 700, 6160–6166. New: **6167** trunk 2, **6168** χ radii, **6169** accents, **6170** bridges, **6171** echoes, **6172** junction sprouts. Each feature draws only from its own stream and passes it to `put()`. At dial 0 no new stream is consumed and the old ones are untouched; a chaos/accents/bridges 0 sheet differs from v6 only by the calm hand and pre-smooth, which is what chaos 0 means. Trunk 2 changes `migrate`'s events when it fires; that is the feature.

## 4. Kill criteria and the reviewer's questions

Reviewer: Sonnet, blind, given a 12-seed contact sheet at defaults plus seeds 22 and 10 with junction closes, the seed-22 crop as target, and the rule "don't resolve the whole picture". Ask, in order:

1. Two registers or one: point at the deliberate line and the chaotic passage; is the calm line still a hand, not CAD?
2. The stated arcs: like the crop's (uneven, leaning, unequal) or tree rings, fingerprint, bullseye?
3. Count the bridges. On a plane of their own, calmer than what they join? Any that close a bean, read as a river crossing, or tidy the picture up?
4. Where two rivers cross: one composition or two drawings?
5. Across 12 cells: the same knot-and-eyebrow at every junction?

Kill, per feature: eyebrows read as rings → widen the gap set or halve `nA`; bridges resolve the picture on ≥ 4/12 → halve `nB`, χ exclusion to 0.5; beans → tighten the area window; trunk 2 reads as two drawings → crossing must lie in the middle 60 % of the sheet; sameness → alternate which of A1/A3 leads per seed. Round kill: if the review prefers v6 on seeds 22 and 10, revert CP1's pre-smooth first, then the hand blend; bridges stay for a second look.

## 5. Performance

Baseline 208 ms per sheet; CP0 returns ~25 ms from `stallW`. Estimated costs: χ and pre-smooth 3 ms, eyebrows 3 ms, bridge index and sites ≤ 12 ms (N-site sampling at 2 mm, ≤ 200 candidates), trunk 2 +8 ms when it fires. Lands near 5.0 s; 5.5 s is a hard stop, and A4 goes first, then A2/A5.
