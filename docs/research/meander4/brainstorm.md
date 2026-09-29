# Meander 4: Density brainstorm (Opus, 29 Sep 2026)

## Facts that shape it

- V7 inks **1.2–1.8 m** per sheet in ~240 ms (`smoke_meander --r3`, seeds 22, 5 and 7). Density 1 means 40–100 m, **30–60× that**. At 40 m the average is 0.6 mm/mm² (≈ 1.6 mm spacing). With 30 % kept void, the dark parts sit at 0.5–0.9 mm.
- `put()` cuts a stroke wherever it meets unrelated ink. Cover strokes sent through it would come out as hatch dashes. **Density needs its own occlusion model** (0b).
- Flags E, X and N fire on every dense sheet. Gate them to D = 0, or rescale them (E counts reserved voids only).
- The two references split one way. The pink ref has **lit ribbons**; the monoprint has **reserved (cut-out) ribbons over dark ground**. The same geometry can give either.

## 0. Frame

- **0a.** At D = 0 the density code consumes no RNG; new streams start at `rngFor(seed, 6170+k)`. Test: byte-identical on seeds 1–24.
- **0b. Cover mask `M`.** A 0.5 mm grid (600×436 Uint8) holding a z-level per cell. Layers are drawn top-first; each marks `M` with a halo, and lower layers clip against it. Order, top to bottom: slash, V7 skeleton, surprise, ribbons, fans, ground. The skeleton halo is 0.6 + 1.2·D mm, which keeps the loved drawing legible.
- **0c. Rank-thinning.** Generate each layer's full candidate set once and give each stroke a rank `u = rng()·(1 − 0.5·importance)`. Keep it if `u < f(D·sub)`. The dial then only adds strokes and never reshuffles; the thinning also leaves the field irregular, which fights engraving. Cache the set per seed so drags are cheap.
- **0d. Mapping.** `eff = D·sub`. Cover ink goes as eff², so the low half of the dial stays near V7.

## A. Continue

- **A1. History ribbons (top pick).**
  - Source: 1–3 trunk (or first-minor) snapshots whose Hausdorff distance from the present is > 25 mm, i.e. where the river used to be. Extend them with A2 until they cross the sheet.
  - Geometry: rails at ±w/2, with w = 5–14 mm under noise of period 60–120 mm.
  - **Twist:** at centreline inflections only, the rails cross over 10–20 mm. This is the ribbon turning over.
  - Body, chosen per ribbon and never all alike: *lit* (3–7 long streaks bunched against one rail) or *reserved* (marks `M`).
  - It is coherent because it is the river's own past, offset.
- **A2. Curvature extrapolation.**
  - Past an end, integrate κ(s) = κ̄₃₀ₘₘ·e^(−s/L), with L = 60–120 mm, plus 0.3× steering toward θ (B0).
  - Cap the total turn at 200°; past that it closes into a bean.
  - Also lets 1–2 skeleton band ends run on 40–150 mm as 1–3 strands, then leave the sheet.
- **A3. Weave.** At rail × skeleton and rail × rail crossings, alternate over and under along each ribbon. "Under" is a 0.8–1.5 mm gap cut through `M`. That gives wrapping with no 3D model.
- **A4. Offset echoes.** The present trunk offset 15–40 mm, drawn over 40–70 % of its length. Rank it last: it tends toward tree rings. Only use it where it crosses another channel.

## B. Cover

- **B0. Flow field θ on a 2 mm grid.**
  - Average the doubled angle over nearby tangents from the present centrelines and the **older snapshots**, weighted by a Gaussian (σ = 12 mm near, 35 mm far).
  - Add ±20° of low-frequency noise.
  - **Never use the distance-field gradient**: its isolines are topographic contours.
- **B1. Tone field T.**
  - T = (0.35 + Ar) × χ boost (+0.4) × lobe bias (×1.5 on the concave side of a bend, ×0.6 on the convex side, from `kap`'s sign at the nearest centreline point).
  - Voids (B4) are set to T = 0.
  - Stretch T until the 90th/50th percentile of ink per 10 mm cell is ≥ 4.
- **B2. Scrub strokes (the core idea).** The rubbed ground is boustrophedon.
  - One pen-down path makes 3–9 passes along θ. Passes are 12–45 mm (lognormal, median 22) and advance 0.4–1.4 mm laterally, jittered per pass.
  - **Turns:** hairpins of radius 0.3–0.8 mm. Pass ends are staggered ±4 mm, giving a dry-brush edge.
  - **Seeding:** Poisson-disc, with density ∝ T. The spacing test is loose (0.3 × local spacing on a 0.5 mm grid), so **overlap and merging are allowed**; overlap is the tone.
  - **Cost:** 60–300 mm per lift.
- **B3. Dry-brush breaks.**
  - Mask each pass with noise stretched 8:1 along θ, at a threshold that falls with T. Breaks in neighbouring passes then align into skip-shapes rather than scattered dashes.
  - Drop pieces under 6 mm; merge gaps under 1 mm.
- **B4. Voids as shapes.**
  - Pick distance-field maxima of skeleton + ribbons whose lineage Voronoi pocket borders ≥ 2 channels. The void is the pocket shrunk 2–5 mm, so its edges are band edges and it reads as a cut-out.
  - At D = 1: 2–4 voids covering 12–30 % of the area.
  - Kill any void with hull ratio > 0.9 and area < 400 mm² (a bean).
- **B5. Fans in lobes (shells).**
  - Where: the 1–3 strongest bends with radius 8–35 mm. Pivot 0.3–0.6 r inside the concave side.
  - Rays: 12–40 at a 2–5° pitch (±40 %), each with sagitta 4–10 %. They end on the band's inner edge (clipped by `M`); reach varies 60–100 %.
  - Drawn as one zig-zag (pivot to rim to pivot), one lift per fan.
  - Caps: at most 3 per sheet, one per channel, never the same ray count twice.
- **B6. Cross-layer.** Inside χ, and in 15–30 % of the T > 0.6 area (cells picked by the stretched noise), add a second scrub layer at θ + 25–40°. Gives the dark rubbed patches.
- **Anti-engraving, measured as recipe metrics:**
  - spacing never constant over more than ~10 mm;
  - stroke-length CV ≥ 0.5;
  - no ground streak parallel to a skeleton line within 3 mm (it butts into the halo at > 25° or passes under);
  - ≥ 2 directions per 40 mm window where T > 0.5.

## C. Slash

- **C1. Restated chords.**
  - Candidates are 80–260 mm long, scored on crossing ≥ 2 bands or ribbons, passing through a void, and cutting θ at 50–90°. Keep 1–5.
  - Each is 2–4 lines 0.2–0.8 mm apart, at ±0.4–1.2°, ends staggered 3–15 mm. Tremor ≈ 0.
  - In dark ground, a 0.5 mm halo in `M` puts the slash *over* the ground.
- **C2. Shard wedges.**
  - Where: gaps with distance 6–20 mm that border ≥ 2 channels.
  - A triangle 20–70 mm long, apex along the nearest slash or rail, filled with 5–14 lines converging on the apex (one zig-zag lift).
  - 2–6 at slash = 1.
- **C3. The X.** Two 40–75 mm chords crossing at 35–60° over a void or χ, each restated 3–5×. At most one per sheet, with p = 0.35·eff. Top z.

## D. Surprise (one region per sheet)

Candidates are scored, then chosen by a weighted roll; a second one is allowed only when eff > 0.8, at p = 0.3. **Each must touch existing ink**; that is the "arising within".

- **D1. Thorn star.** Weighted toward the knot, χ or a ribbon × trunk crossing.
  - 5–11 spikes, each a pair of slightly concave lines meeting at a tip, 12–45 mm long.
  - Angles jittered ±15°, with 1–2 spikes missing so it has no radial symmetry.
  - The body reserves `M`.
- **D2. Loop cells.** Weighted toward the emptiest low-Ar pocket with T > 0.3.
  - Inside 30–60 mm, the ground is replaced by crossing chains of overlapping open "e" loops (3–12 mm) running along θ.
  - Guard against bullseye and coral: no concentric loops within 2 mm, and every loop keeps a 15–40° gap.
- **D3. Black void.** Weighted toward the largest void (≥ 800 mm²), which is inverted: filled with cross-scrubs at 0.35 mm spacing, its edges inherited from the bands. The monoprint's black shape.
- **D4. Reversal patch.** Ground at θ + 90° inside a pocket. Fallback only.

## E. Ink, time, performance

**E1. Allocation.** L runs 5–100 m (default 40). Each layer fills in priority order up to its cap:

| # | Layer | Cap |
|---|---|---|
| 1 | Skeleton | ~1.5 m, always |
| 2 | Slash | ≤ 3 % |
| 3 | Surprise | ≤ 12 % |
| 4 | Ribbons | ≤ 15 % |
| 5 | Fans and wedges | ≤ 15 % |
| 6 | Ground | the remainder |

Ground spacing is solved analytically (ink ≈ Σ area·T/s), then rank-thinned to the exact cap, lowest T first. Light areas thin before dark ones, so the weight structure survives.

**E2. Time estimate** on the page: pen-down / 25 mm/s + lifts × 0.35 s + travel / 80 mm/s (check the real AxiDraw settings first). Worked examples:

| # | 60 m drawn as | Lifts | Time |
|---|---|---|---|
| 1 | 25 mm streaks | ~2400 | ~64 min |
| 2 | ~180 mm scrubs | ~330 | ~46 min |

That gap is why B2 comes first.

**E3. Ordering.**
1. Greedy nearest endpoint with reversal, using a 5 mm hash.
2. 2-opt over 200-stroke windows.
3. **Merge** where an end is < 1.2 mm from the next start and turns < 120°; the joint becomes a hairpin.

Order within each layer, so a stopped plot still reads.

**E4. Performance (≤ 1.5 s at D = 1).**

| # | Step | Cost |
|---|---|---|
| 1 | θ and T grids | ~40 ms |
| 2 | 120 k scrub samples | ~250 ms |
| 3 | Other layers | < 50 ms |
| 4 | Ordering | ~100 ms |

- No `handLine` on ground strokes; use a 1-octave tremor.
- Cache per (seed, non-density dials).
- Contact-sheet thumbnails render at D = 0.5.

## Riskiest

1. **R1 (highest): B reads engraved, topographic or ruled.** Evenly spaced streamlines along band tangents *are* the rejected look. Mitigation: B2, B3 and B6 plus the metrics. Prototype B2 alone on one seed before building anything else.
2. **R2: density drowns the skeleton.** Mitigation: the halo and reserved ribbons. Always review D = 1 beside its D = 0 twin.
3. **R3: stamps return** (the round-1 lesson). Mitigation: hard caps and randomised counts and geometry. Reviewers score motif repetition across the 12 cells.
4. **R4: the twist reads as rope or DNA.** Mitigation: inflections only, never periodic.
5. **R5: time budget.** Mitigation: Poisson pre-seed, no rejection loops.

## Build order

| CP | Build | Gate |
|---|---|---|
| 0 | Dials (D, 4 subs, ink limit), rank scaffold, `M`, ink/time metrics, flag gating, ordering | Byte-identical at D = 0 |
| 1 | **B0–B3 ground only**, seeds 22, 7 and 13 at D 0.3/0.6/1 | Lead checks R1; stop and rethink if engraved |
| 2 | B4 voids, halo, B6 | Contrast ≥ 4; voids 12–30 % |
| 3 | A1–A3 ribbons, then A4 | Ribbons cross the sheet on ≥ 8/12 |
| 4 | B5, C1–C3 | Caps held |
| 5 | D1–D4 | One per sheet, touching ink |
| 6 | E1 solve, E3 merge, perf | ≤ 1.5 s at L = 100; ink within ±5 % of cap |
| 7 | Blind review 1 (D ∈ {0.3, 0.7, 1} × 6 seeds), fixes, review 2, publish V8 | — |
