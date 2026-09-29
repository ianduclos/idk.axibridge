# Meander round 2: synthesis brief (Fable, 29 September 2026)

Read: the round-2 plan, `shots/meander-0929/README.md`, both Sonnet reviews, the three meander2 reports, `t_meander.js` (658 lines, current), round-2 `close-a`/`sheet-A`, Ian's 03:12 sketch, v5 `close-Ha`. Numbers below marked *measured* come from a profiled run in node this session (`seedChannels` / `migrate` / rest timed separately, 6 seeds × 2 sources), not from the reports.

Ian's direction, binding: "nuanced tangle that becomes textural at places, organic line based at others. painterly. dynamic. make you ask whats really going on"; "weird compositions, negative space, different registers mixing into each other"; "stranger yet coherent forms. more weight at parts and less at others"; "kinda more unified stuff"; one pen. Rejected: v5's hairball knot, scribble-filter, one handwriting, ruled parallels / tree rings, closed beans, map / topographic.

## 0. Where I differ from the lead

1. **Work map before tangle, not after.** The tangle zone is placed at the band's most active swell, and today "active" is a random blob field aligned with nothing (brainstorm-composition fact 3; the thin cells prove it). Build the work map first: it is ~30 lines, isolated, testable on the current sheets against flag `N`, and it decides where the tangle lands. Building the tangle on the random field means re-tuning its placement a day later; the review sheet still leads with tangle.
2. **Plait is not a mechanism this round; it is a second dip source.** Both tangle reports make the plait a phase model with its own cliché (Celtic braid). The same effect for a tenth of the code: a `refuse` event lowers coherence on *both* limbs around `at`, they are already `related` in `sim.pairs`, so decohered strands of one limb wander into the other's band. Exchange without an over-under rule. If a reviewer still asks for the braid after seeing it, round 3.
3. **Rails on gentle arcs have a measurable cause, not a taste one.** `bundleGeom` normalises migration speed per channel (`vlo`/`vhi` = own p15/p95), so a channel that barely moved still earns a full swell somewhere on it; M10's straight double is a manufactured swell. Gate `S` by absolute bend curvature and add an absolute speed floor. Curvature-gated dropout (the reviewer's suggestion) is the second half of the same fix.
4. **All three composition ideas fit, but the window goes last and is the one to shrink if time runs out.** Work map and graft are cheap and independent; the window is the only piece that touches eight lines of the sim. It must not block the tangle review.

Everything else I adopt: offset-space wander on `bundleGeom` rather than a separate walker (a strand's offset from the parent *is* its integrated relative heading, so a leash on the offset is the leash on the heading, and `put()` clips it for free); 1–2 zones per sheet, some none; ≤ 0.3 s per sheet.

## 1. Mechanisms

Execution order per sheet: `seedChannels` (graft) → `migrate` on field F → `workMap` → `findWindow` + `toSheet` → M2 (`bundleGeom` with coherence) → search → M3 unchanged.

### 1.1 Work map (`workMap`, `renderField`)

```
workMap(snaps, F)                                  // 5 mm grid over F, ~2 ms
  Wk = Float32 grid; for s in snaps: for i: Wk[cell(s.pts[i])] += s.speed[i]
  box-blur 3 passes (σ ≈ 10 mm); normalise by p98 over non-empty cells; clamp 0..1
  return bilinear lookup + grid (the window score reuses the grid)

renderField(A, Wk, mu, gamma=2)  →  Ar(x,y) = (1-mu)·A(x,y) + mu·Wk(x,y)^gamma
```

`A` stays the *simulation* field (it seeds variety in `migrate`, line 197). `Ar` replaces `A` at every render-time read: `bundleGeom` line 311 (`Ai`), minor ranking line 440, `cross` permission line 460, search candidates line 480, history keep line 512, and tangle placement below. `mu` is param `work`; γ = 2 fixed (γ 3 hands everything to one U-turn, kill row 8).

### 1.2 Tangle: coherence dial on the band (`coherence`, inside `bundleGeom`)

Rule from both reports: a tangle is the band's own strands losing rank, spacing and continuity along a stretch while keeping the channel's heading. No new object.

```
coherence(g, Ar, ev, rng)        // g = the bundleGeom arrays; returns coh[n] in 0..1, zones[]
  if rng() < 0.3 or g.Kmax < 4: return ones, []        // some sheets carry none
  P[i] = Ar(C_i) · S[i]/Smax · vl[i]/vhi                 // where the band worked hardest
  P[i] = 0 where dInf[i] < 8 or min(i, n-1-i)·0.5 < 20   // never across a pinch or an end
  dips = [ {i: argmax P, depth: 1} ]                      // the swell peak
  for e in ev of kind 'refuse' touching this channel:      // plait as a dip, half depth
    j = nearest index of C to e.at; if K[j] >= 3 and P[j] > 0: dips.push({i: j, depth: 0.5})
  keep ≤ 2 dips per channel, ≤ 2 per sheet (trunk first, then the highest P)
  for d in dips:
    L = (10 + 20·rng() + 15·Ar(C_d)) / 0.5                  // half-width in samples: 20–45 mm
    L = max(L, 3·1.6·S[d.i]/0.5 / 2)                         // zone ≥ 3× longer than wide
    coh[i] = 1 - depth · raisedCos((i - d.i)/L)  for |i-d.i| < L
    zones.push({i0, i1, ch, depth})
```

Inside `bundleGeom` after `off`/`act` are built (line 333), and before pieces (line 340):

```
for k in 0..Kmax-1:
  wander_k = noise1(rng), lam_k = 12 + 13·rng() mm, phase_k = rng()·100
  for i where coh[i] < 1:
    w = 1 - coh[i]
    env = 0.7·S[i]·(1 + 0.6·w)                               // leash: band bulges where order goes
    o = coh[i]·off[k][i] + w·env·wander_k(phase_k + i·0.5/lam_k)
    off[k][i] = o;  if w > 0.3: act[k][i] = 1                // dropped strands revive
  re-run boxFilter(off[k], 8) over the zone only (20 would smear the wander)
```

Heading check by construction: amplitude ≤ 0.7·S·1.6 ≈ 2 mm at S 2, λ ≥ 12 mm gives strand tangents within `atan(2π·2/12)` ≈ 45° worst case, ~30° typical; the metric (§1.6) enforces ≤ 35° mean. Curls under 3 mm cannot occur (λ ≥ 12).

Pieces inside a zone: length `(10 + 15·rng())` mm, gap `2 + 4·rng()` mm, and a strand may not start or end within 4 mm (in s) of a sibling's start/end (the anti-stamp rule from research §11). `put()` for pieces whose midpoint lies in a zone runs with `cross: true`.

Fade is intrinsic: `coh` is a raised cosine, so strands cross back into rank at the zone ends; S is already falling toward the next pinch, so K steps down 6→4→3→1 over ≥ 15 mm (kill row 3 checks it).

Stops: (a) `coh` returning to 1; (b) ink budget: if the strand length added inside a zone exceeds 300 mm, halve `L` and recompute; (c) spacing: after the wander, for each i sort active strands by offset; an adjacent pair with |gap| < 0.35 mm for > 8 mm without a sign change loses the outer strand (`act = 0`, it rides the neighbour: an existing merge behaviour).

### 1.3 Curvature gate for rails (`bundleGeom`, lines 312 and 348/355)

```
cg[i] = smooth(0.012, 0.035, |kap[i]|)                     // radius 80 mm → 0, radius < 30 mm → 1
vhi   = max(vs[p95], V_ABS)                                 // V_ABS: calibrate at CP1 as the p95 of vl
                                                            // on seed 21's trunk; write it in the header
s     = ... · lerp(0.35, 1, cg[i])                          // a gentle arc gets at most a third of its swell
piece length ·= lerp(0.55, 1, cg), gap ·= lerp(2, 1, cg)    // dropout is heavier where the arc is gentle
```

`kap` here is the 16-sample box-filtered curvature already computed at line 291.

### 1.4 Searching register: 2–3 unequal patches (lines 477–497)

`want = 2 + (rE() < 0.5)`; `half = clamp(8·exp(0.6·gauss(rE)), 6, 40)` mm (lognormal, so the three differ); `passes = 2 + floor(5·rE()·half/40)` (the largest patch gets the most passes); spacing ≥ 35 mm; candidates use `Ar > 0.5` and admit `S < 3` for one of the three so a patch may sit on the edge of a band. Skip a candidate inside a tangle zone (the two registers must stay distinct, review r2 §4c).

### 1.5 Sprout graft (`seedChannels`, lines 150–165)

```
inherited = chains.slice(1).filter(P => near(P, trunk.pts, 25) > 0.15)     // touch the trunk
take round(g·(nCh-1)) of them (longest first, the existing overlap test); the top-up loop fills the rest
sprout index: sample i ∝ |curvatureOf(tr)[i]| + 0.01 instead of uniform     // sprawl grows at the bends
```

`g = 1` is today's territory topology; `g = 0` is the "nothing" topology on an inherited trunk. `source: 'nothing'` stays as is (noise trunk). Zero cost (*measured*: `seedChannels` is 1–27 ms).

### 1.6 Found window (`fieldOf`, `findWindow`, `toSheet`)

```
fieldOf(prm) → F = prm.window ? {x0:-0.3W, y0:-0.3H, x1:1.3W, y1:1.3H} : {x0:0, y0:0, x1:W, y1:H}
```

Pass `F` explicitly into `activityField` (lines 37–40), `trimToSheet` (95), `noiseWalk` (105–106), `seedChannels` (131, 147) and `migrate` (209, 212): every `W`/`H` there becomes `F.x1 - x` etc. Territory chains keep their sheet coordinates (they sit in the middle of F); nothing-source starts anywhere inside F's inner 70 %. Lines 422, 630, 644 stay in sheet space. Cost: *measured* `migrate` scales with channel points × steps, not area; `maxLen` bounds the points, so expect ≤ +15 % (channels reach `maxLen` sooner without edge damping).

```
findWindow(Wk, chans, sim, F, rng)              // ~150 windows, summed-area table, ≤ 5 ms
  empty = cells with Wk < 0.02 and no present centreline within 6 mm
  for s in [1.0, 0.8, 0.65]: for origin on a 10 mm lattice inside F, window = s·(W,H):
    a: work centroid offset 0.15–0.35 of the diagonal from centre        (score 1 inside, falls off)
    b: largest empty component 25–55 % of the window, touching ≤ 2 edges  (flood on ≤ 60×44 cells)
    c: top-decile Wk cells cut 1–2 window edges; centreline frame crossings 1–5 (0 = today's inset,
       ≥ 6 = excerpt); both hard
    d: best 40 mm sub-window ≥ 3.5× median Wk                             (hard)
    s < 1 only if ≥ 2 drawn channels' presents lie inside                 (anti-logo)
  choose argmax of a·b with c, d as gates; tie-break by rng(); if no window passes, s = 1 centred
toSheet(sim, chans, win): p' = (p - origin)/s for every present, snapshot, event.at, cutoff loop;
  speed' = speed/s; then M2/M3 run unchanged in sheet mm (band spacing is computed after scaling)
```

## 2. Parameters (4 new; two defaults change)

| Name | Default | Range | Moves |
|---|---|---|---|
| `tangle` | 0.6 | 0–1 | depth multiplier on `coh` dips; 0 = none |
| `work` | 0.7 | 0–1 | `mu`: how much render weight follows the work map |
| `graft` | 0.3 | 0–1 | share of inherited minors under `source: 'territory'` |
| `window` | 1 | 0 / 1 | simulate on 1.6× and crop by score |

Changed defaults: `search` stays 1 but now yields 2–3 patches; `channels` 8 unchanged. New rng keys: 6165 (tangle), 6166 (window). Recipe gains `tangles: [{ch, i0, i1, aspect, angle, curl, ink}]`, `window: {s, origin, score}`, `workPeak`, and flag letters below.

## 3. Kill table

| # | Criterion | Measured (node) or seen | Change |
|---|---|---|---|
| 1 | Hairball zone: aspect ratio of the zone's ink-point principal axes < 3, or mean strand-tangent deviation from `th` > 35°, or > 10 % of zone length on radius < 3 mm; 2 of 3 fails → flag `K` | `tangleMetric(zone)` on the pieces with `i` in `[i0,i1]`, in the recipe | raise λ floor to 16; lower `env` to 0.5·S; if still, depth cap 0.7 |
| 2 | Stamp: zone ink or length CV across a 6-cell sheet < 0.4 | `sheet.js` caption from `res.meander.tangles` | widen the `L` range and the depth range; ensure the 30 % no-tangle branch fires |
| 3 | Rope / scribble-filter: crossing points along s spaced with CV < 0.3, or zones cover > 25 % of a band | count sign changes of sibling gaps in the zone | per-strand `lam_k` too close: widen to 10–30 mm; `L` cap |
| 4 | Hard fade: K drops by ≥ 3 within 10 mm at a zone end | K series at `i0`, `i1` | zone ends before the swell ends: shrink `L` or move the dip |
| 5 | Existing X (20 mm square > 400 mm ink) | already in recipe | zone budget 300 → 200 mm |
| 6 | Rails: strands with K ≥ 3 where `cg < 0.3` over > 20 % of banded length | new `railFrac` in recipe | gate too soft: 0.012/0.035 → 0.02/0.05 |
| 7 | No protagonist: top-decile density < 4× median (`N`) on seeds 7 and 3 | existing `contrast` | `work` 0.7 → 0.85 before touching γ |
| 8 | Formula: ≥ 4 of 6 protagonists are a U-turn at the largest bend | seen (sheet) | choose between the first and second work peak by rng |
| 9 | Excerpt / inset map: reviewer names "map / detail / excerpt" on ≥ 3 of 18, or < half of window cells show a line leaving the frame | seen + `frameCrossings` in recipe | tighten term c to 1–3 crossings; drop s 0.65 |
| 10 | Score composes the process: > 60 % of windows put the mass in the same quadrant | recipe `origin` over the matrix | term a is too narrow: 0.15–0.35 → 0.1–0.4 |
| 11 | Graft invisible: reviewer groups `graft 0.3` cells with their `graft 1` siblings at < 3 of 6 | review pairing | inheritance is not worth its code: keep `graft` at 0 and note it |
| 12 | Twig / tree: ≥ 2 cells named "branch / coral / antler" | seen | sprout angle range 0.6–1.4 → 0.9–1.6 rad and curvature weighting off |
| 13 | Searching register still one patch, or it reads as noise | seen at close | `want` floor 3; check candidates are not all filtered by the zone-exclusion |
| 14 | Budget: warm sheet > 300 ms | `smoke_meander.js` (discard the first, JIT) | window lattice 10 → 15 mm; snapshot cadence 8 → 10 |
| 15 | Determinism broken | `smoke_meander.js` two-run compare | a sort without total order or an unkeyed rng |

## 4. Blind test matrix (18 cells)

Neutral IDs `R01–R18`; split into three sheets of 6 (A: R01–06, B: R07–12, C: R13–18) with the order shuffled per sheet in the withheld file; closes `close.js R##:auto` on every cell. Base `prm` = the round-2 base plus the new defaults; `window` and `tangle` on.

```json
{"title": "meander round 2", "cols": 2, "w": 0.4,
 "prm": {"loose": 0.5, "yieldP": 0.5, "wander": 1, "reach": 15, "spread": 0.7, "eps": 0.03,
         "borders": true, "outer": true, "voids": false, "interior": false, "disregard": 0.15, "hyst": 25,
         "render": "meander", "source": "territory", "channels": 8, "drift": 0.6, "band": 1, "history": 0.6,
         "activity": 0.9, "events": 2, "white": 0, "hetero": 0.6, "search": 1,
         "tangle": 0.6, "work": 0.7, "graft": 0.3, "window": 1},
 "cells": [
  {"id": "R01", "random": 3,  "order": "reversed", "prm": {}},
  {"id": "R02", "random": 13, "order": "reversed", "prm": {}},
  {"id": "R03", "random": 21, "order": "reversed", "prm": {}},
  {"id": "R04", "random": 7,  "order": "reversed", "prm": {}},
  {"id": "R05", "random": 34, "order": "reversed", "prm": {}},
  {"id": "R06", "random": 58, "order": "reversed", "prm": {}},
  {"id": "R07", "random": 3,  "order": "reversed", "prm": {"tangle": 0}},
  {"id": "R08", "random": 21, "order": "reversed", "prm": {"tangle": 0}},
  {"id": "R09", "random": 7,  "order": "reversed", "prm": {"tangle": 0}},
  {"id": "R10", "random": 3,  "order": "reversed", "prm": {"work": 0}},
  {"id": "R11", "random": 7,  "order": "reversed", "prm": {"work": 0}},
  {"id": "R12", "random": 13, "order": "reversed", "prm": {"work": 0}},
  {"id": "R13", "random": 13, "order": "reversed", "prm": {"window": 0}},
  {"id": "R14", "random": 21, "order": "reversed", "prm": {"window": 0}},
  {"id": "R15", "random": 58, "order": "reversed", "prm": {"window": 0}},
  {"id": "R16", "random": 3,  "order": "reversed", "prm": {"graft": 1}},
  {"id": "R17", "random": 13, "order": "reversed", "prm": {"graft": 1}},
  {"id": "R18", "random": 21, "order": "reversed", "prm": {"graft": 1}}
 ]}
```

Withheld mapping: R01–06 new defaults on the six seeds; R07–09 isolate tangle (against R01/R03/R04); R10–12 isolate the work map (seeds 3 and 7 are the round-2 thin cells); R13–15 isolate the window (against R02/R03/R06); R16–18 are today's territory topology (against R01–03, and the reviewer's round-2 M12/M16/M06 memory) for kill rows 11–12. Review asks per cell: registers, where the tangle is and whether it is *the line* losing order or an object on it, associations, where the eye rests, does anything leave the frame, is the void shaped; then the row-9, row-11 pairings after recipes. Sheets at 6 cells plus 100 × 70 mm closes, as the round-1 lesson says.

## 5. Build order

1. **CP1 work map + curvature gate + searching patches** (½ session). `workMap`, `renderField`, the five `A → Ar` swaps, `cg`, `V_ABS` calibrated and written in the header, `want`/`half` changes. Check: seeds 3 and 7 lose flag `N`; `railFrac` on seed 58 (M09/M10) falls below 0.2; smoke deterministic, warm ≤ 250 ms. Commit.
2. **CP2 tangle** (1 session). `coherence`, wander blend, zone pieces, spacing stop, `tangleMetric`, flag `K`, recipe `tangles`. Dev sheet of the six seeds plus closes; rows 1–5 clear on at least 5 of 6; at least one of the six has no zone, and seed 21's zone sits on the U-turn that was M04's protagonist. Commit.
3. **CP3 graft** (¼ session). Zero-cost; check `graft 1` reproduces today's channel list on seeds 3/13/21 exactly (regression), `graft 0` has no isolated minors.
4. **CP4 window** (1 session). `F` plumbing, `findWindow`, `toSheet`, recipe `window`. Check on 24 crops: rows 9–10, every default cell has ≥ 1 frame crossing, warm ≤ 300 ms. If it slips, ship R01–12 + R16–18 with `window: 0` and keep R13–15 for a second sheet.
5. **Matrix, blind review, one iteration, evidence** in `shots/meander2-<date>/` with README and withheld recipes; then Ian, on screen, "ready for you to check". Commit at each CP on `feat/territory-bench`.

## 6. Not this round

Plait as an over-under phase model; hinge fan; confluence spill; crossing drag; pile restatement; the "double present" wild card; contour-steered walk (flow-field risk); gather/scatter `m`; lag-by-activity; the off-frame protagonist; bend-level heterochrony; white channel revival; a second tangle generator of any kind (convergent search, tremor, ligatures) — the coherence dial must be seen on its own first; any `axibridge/` change; plotting; colour; paper.

## 7. Risks to watch

- **Two fields, one letter.** After CP1 a stray `A(` at render time is a silent regression; `migrate` line 197 is the only intentional one.
- **Window + history.** `e.loop` (oxbows) and `snaps` need the same `toSheet` transform as the presents, or they land off-sheet; a channel with no bend ≥ 60 mm gets no dip, which is correct, not a bug.
