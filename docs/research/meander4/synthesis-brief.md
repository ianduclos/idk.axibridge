# Meander round 4: Density — synthesis brief (Fable, 29 September 2026)

Inputs: Ian's plan (binding), both references, the Opus brainstorm, `post-r2-check.png`, `seed22-rescue.png`, engine and page. Measured (`smoke_meander --r3`, seeds 22/7/13/5): V7 inks **1.18–1.72 m** at **200–320 ms**, flag `N` everywhere. Density 1 at 40 m is ~30× that.

Binding: one Density dial, four sub-dials, "smart and contextually aware, but not conservative", ink ≤ 100 m and controllable, overlap fine. The seed-22 junction shapes (drip, crescents, restated neck) stay visible at every D.

## 0. Decisions, and where I differ from the brainstorm

1. **The mask is a second `Sheet`.** `M = new Sheet()`, 1 mm cells, marked top-first with `id = z` (chords 6, base 5, surprise 4, ribbons 3, fans 2; ground is 1 and never marks). `mark` keeps the first owner, so a stroke at z is cut where `M.owner > z`. Halo = mark radius. `distField(M)` gives the voids.
2. **The base is a white reserve.** Ground stops at its halo, so the drawing reads lit, like the monoprint's cut-outs; the halo jitters (§3), never a uniform glow.
3. **Junction pools.** `J` = cells within 14 mm of a point where two channels' present lines lie within 12 mm (`junc`, `id = -1`). Ground tone there is 0; ribbons, fans, wedges never enter; one slash may cross, only at `eff_slash ≥ 0.7`. The knot sits in open paper: the focal hole.
4. **Continuations use `put()` at base z** (the channel carrying on, its lineage, `cross: true`). Everything else clips against `M` only.
5. **Sub-dials are weights.** `eff_k = clamp(D·2·sub_k, 0, 1)` for continue/slash/surprise; `cov = D·2·sub_cover` (0–2). At page defaults `eff = D`. `cov > 1` adds no ink: it stretches tone (spacing floor 0.5 mm, cross layer everywhere).
6. **Out:** A4 offset echoes (tree rings), D2 loop chains (coral), D4; reserved rings replace D2 (§2.7). **D 0 runs no new code**: one `if (D > 0)` block, base stroke order untouched.

## 1. Checkpoints

`smoke_meander --r3 --d <D> --ink <L>` prints the `density` block (§6); `--hash` hashes `lines`.

| CP | Build | Accept |
|---|---|---|
| **CP0** | Dials, guard, `M` with base marked (§3), θ/T/J grids, void finder, budget, ordering, metrics, flag gating. | D 0 hash identical to V7 on seeds 1–24; ≤ 260 ms. |
| **CP1** | Ground only (§2.2), seeds 22/7/13/5 at D 0.3/0.6/1, L 40. | `spacingCV ≥ 0.45`, `lenCV ≥ 0.5`, `parBand ≤ 0.15`, `dirFrac ≥ 0.5`, ink ±5 %, `baseVis ≥ 0.9`, `juncClear ≥ 0.95`; ≤ 0.9 s at L 100. **Lead views D 1 beside D 0; engraved → stop and rethink.** |
| **CP2** | Voids, fans. | `voidShare` 0.12–0.30 at D 1 on ≥ 9/12; no bean; ≤ 3 fans, distinct ray counts, none within 20 mm of J. |
| **CP3** | Ribbons, continuations, twist, over/under. | A ribbon touches two edges on ≥ 8/12 at D 1; ≤ 2 twists each; layer ≤ 15 %. |
| **CP4** | Chords, wedges, X. | Caps held; ≤ 1 chord through J; X count over 24 seeds ≈ 0.35·eff·24 ± 3. |
| **CP5** | Surprise. | ≤ 1 per sheet (2 only at eff > 0.8, p 0.3); touches ink; no kind on > 60 % of seeds. |
| **CP6** | Exact budget, merge, thumbs. | Ink ±3 % at L 40 and 100; lifts ≤ 350 at 40 m, ≤ 750 at 100 m; ≤ 1.5 s at D 1, L 100; deterministic ×24; thumbs ≤ 0.4 s. |
| **CP7** | Blind review 1 (D 0.3/0.7/1 × seeds 22, 7, 13, 5, 31, 10), fixes, review 2, V8. | §6. |

## 2. Mechanisms

Every layer is generated at full strength, each stroke ranked `u·(1 − 0.5·importance)`, kept in rank order up to its cap (§4). The dial only adds.

### 2.1 Fields, `rngFor(seed, 6180)`

- **θ, 4 mm grid, bilinear.** Doubled-angle average of tangents from present centrelines (`g.th`) and all `snaps`, Gaussian σ 12 / 35 mm, plus ±20° noise from two `noise1`, λ 60–90 mm. **Never the distance-field gradient.** Within 12 mm of base ink tilt by `(1 − smooth(4, 12, Dbase))·40°`, sign per channel: streaks meet the halo obliquely instead of echoing the band.
- **T.** `(0.35 + Ar)·(1 + 0.4χ)·lobe`; lobe 1.5 concave / 0.6 convex of the nearest bend (`g.b` sign at the nearest `g.C`, pointHash 8 mm), 1 beyond 25 mm; 0 in voids and J. Then `T ← T^γ`, γ by bisection until the 90th/50th percentile over ground cells is ≥ 4 (6 at `cov > 1`).

### 2.2 Ground (cover), `6181` scrubs, `6182` dry-brush

- **Scrub** = one pen-down polyline of 3–9 passes marched at 0.5 mm along θ (re-read each step, so passes bend with the form); pass length lognormal median 22 mm σ 0.55, clamped 8–55; hairpin radius 0.3–0.8 mm; lateral advance `lognormal(0.9, 0.5)` clamped 0.35–2.2 mm, one side per scrub; ±0.5 mm lateral noise λ 12 mm within a pass. The head stops on `M.owner > 1`, a 3 mm margin, or `T < 0.1`. No `handLine`; tremor 0.04 mm.
- **Seeding.** Per 10 mm cell, expected count `d(T)·100/130` (130 mm = mean scrub ink), Poisson from the stream in scan order, jittered; `d = d_max·T^1.3`, `d_max` solved so Σ = ground cap. Overlap is the tone.
- **Dry-brush.** Noise stretched 8:1 along the scrub's mean heading, threshold `0.55 − 0.45T`; drop pieces < 6 mm, merge gaps < 1 mm, so neighbouring passes break in aligned skip-shapes.
- **Cross layer.** Inside χ, and in 15–30 % of `T > 0.6` cells picked by the same noise (all at `cov > 1`): a second scrub set at θ + 25–40°.

### 2.3 Voids (cover), `6183`

Local maxima of `distField(M)` ≥ 14 mm after base and ribbons are marked. Pocket = component of `{dist ≥ 2 + 3u}` holding the maximum, clipped to a disc `min(1.6·Dmax, 45)`. Reject if the disc arc is > 45 % of the perimeter, the pocket borders < 2 lineages, or hull ratio > 0.9 with area < 400 mm². Keep `round(eff_cover·4)` by area, 12–30 % of the sheet at D 1; they set `T = 0`.

### 2.4 Fans (cover), `6186`

`n = min(3, round(cov·(1 + 2u)))`, the strongest bends of radius 8–35 mm, one per channel, pivot 0.3–0.6 r inside the concave side, none within 20 mm of J. 12–40 rays at 2–5° pitch ±40 %, sagitta 4–10 %, reach 60–100 %, ending where `M` cuts them; one zig-zag, one lift; ray counts never repeat on a sheet. Marks z 2, halo 0.6.

### 2.5 Continue, `6184` ribbons, `6185` continuations

- **Ribbons**, `n = round(eff·(1 + 2u))`: trunk snapshots with Hausdorff > 25 mm from the present, extended past both ends by `κ(s) = κ̄₃₀·e^(−s/L)`, L 60–120 mm, 0.3× steering to θ, turn ≤ 200°, until off-sheet. Fallback: a `noiseWalk` sweep off-sheet → largest void → off-sheet, |κ| < 1/40. Rails ±w/2, `w = 5 + 9u`, noise period 60–120 mm. Body, never all alike on a sheet: **lit** (3–7 dry-brushed streaks bunched on one rail) or **reserved** (body marks z 3: white ribbon on dark ground). **Twist** at inflections only, ≤ 2: rails cross over 10–20 mm. **Over/under** alternates along each ribbon, conflicts to the longer; under = rail gap `w_over/2 + 1 mm`.
- **Continuations**, `n = round(eff·(1 + 1.5u))`: a k = 0 band end outside J runs on 40–150 mm as 1–3 strands by the same extrapolation, off-sheet or into a void. `put(…, ch, edgeHand, r, {cross: true})`, marked into `sheet` and `M` at z 5.

### 2.6 Slash, `6187` chords, `6188` wedges/X

- **Chords**, `n = round(eff·(1 + 4u))`, 80–260 mm, scored on crossing ≥ 2 bands or ribbons, passing a void, cutting θ at 50–90°; ≤ 20 mm in J, one at most. 2–4 lines 0.2–0.8 mm apart at ±0.4–1.2°, ends staggered 3–15 mm, tremor 0: the one ruled thing, the foil. Marks z 6, halo 0.5.
- **Wedges**, `n = round(eff·(2 + 4u))`: gaps of `dist` 6–20 mm bordering ≥ 2 lineages; triangle 20–70 mm, apex on the nearest chord or rail, 5–14 lines converging as one zig-zag (spacing 0 → w, never constant).
- **X**: two 40–75 mm chords at 35–60° over a void or χ, restated 3–5×, `p = 0.35·eff`, ≤ 1.

### 2.7 Surprise, `6189`

Weighted roll among available candidates, `p_none = 1 − eff`; it must touch existing ink.
- **Thorn star** (1): on χ or a ribbon × trunk crossing; 5–11 spikes of paired slightly concave lines 12–45 mm, angles ±15°, 1–2 missing; body reserves z 4.
- **Reserved rings** (1; needs a `T > 0.7` pocket ≥ 40 mm): 3–7 overlapping open rings 6–18 mm cut out of the ground (ring body 1.2 mm in `M`). Zero ink.
- **Black void** (1.2; needs a void ≥ 800 mm²): inverted, cross-scrubs at 0.35 mm in two directions, edges from the bands.

## 3. Layering and the halo

Mark order: chords (0.5 mm); base + continuations, halo `(0.8 + 1.0D)·(0.6 + 0.8·n(s))`, `n` noise λ 20 mm along arc length, `3 + 2D` in J; surprise; ribbons (reserved body, or rails + 0.8); fans (0.6). Then ground. A stroke is cut where `M.owner > z`, never otherwise dashed. `baseVis` = base samples with no density ink within 0.8 mm; `juncClear` = J cells free of it.

## 4. Ink, ordering, time

`I* = base + (L − base)·D^1.5` (D 0.5, L 40 → ~15 m). Caps on `I* − base`: slash 3 %, surprise 12 %, continue 15 %, fans + wedges 12 %, ground the remainder × `smooth(0, 1, cov)`. Ground thins lowest-T scrubs first; the budget is re-solved once to land within ±3 %.

Ordering, density strokes only, per layer (a stopped plot still reads): greedy nearest endpoint with reversal on a 5 mm hash, 2-opt over 200-stroke windows, merge where an end is < 1.2 mm from the next start and the turn < 120° (the joint is a hairpin). No rng.

Page time, labelled ≈: pen-down 70 mm/s (`estimate.py`: 25 % of 279) × 0.6 on scrubs, lifts 0.35 s, travel 210 mm/s; 40 m ≈ 25 min, 100 m ≈ 60 min. Use the axibridge estimator before plotting. Thumbnails render the same ranked sets to `min(L, 15 m)`, captioned `15/40 m`.

## 5. Determinism

Existing: 700, 6160–6173. New: **6180** fields, **6181** scrubs, **6182** dry-brush, **6183** voids, **6184** ribbons, **6185** continuations, **6186** fans, **6187** chords, **6188** wedges/X, **6189** surprise. One stream per layer; Poisson seeding in cell order; rng-free ordering. None created at D 0.

## 6. Flags, reviewer, kill

At D > 0 flags `E X N` are suppressed; the `density` block prints `inkM, lifts, timeEst, contrastD (≥ 3), baseVis, juncClear, voidShare, spacingCV, lenCV, dirFrac, parBand` and counts. `spacingCV`: 400 ground samples, gaps to the next three ground cells across θ. `parBand`: ground samples within 3 mm beyond the halo running within 20° of the nearest base tangent. `dirFrac`: `T > 0.5` 40 mm windows with ≥ 2 directions > 25° apart.

Reviewer: Sonnet, blind; 18 cells (D 0.3/0.7/1 × 6 seeds) each beside its D 0 twin, both references, the seed-22 close at D 0 and 1. In order:
1. Rubbed streak and fan, or hatching, contour, weather chart?
2. Is the calm drawing still there; are the junction shapes the first thing seen at D 1?
3. Ribbons: wrap and cross, or rope, DNA, tree rings?
4. Voids: shapes, or holes and beans?
5. Across 18 cells, what repeats?
6. Which D would you plot, per seed?

Kill: **engraved/ruled** (Q1 fails ≥ 6/18) → halve passes, double advance σ, tilt 55°; still → single streaks instead of scrubs, the core risk realised. **Hairball** (`hair` > 600 per cell outside the black void) → cross layer only inside χ. **Buries the base** (Q2 fails ≥ 4/18 or `baseVis < 0.9`) → halo 1.5×, J 18 mm; still → ground cap 60 %. **Rope** → twists off. **Stamps** → widen ranges, never add a guard. Round kill: the review prefers D 0 on every seed → V8 ships with the dial opt-in and the work stops.
