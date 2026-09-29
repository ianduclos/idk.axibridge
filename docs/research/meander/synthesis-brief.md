# Meander round: synthesis brief (Fable, 29 September 2026)

Input: `PACK.md` and its images, the plan, the three brainstorms, the two research reports, and the prototype code (`t_head.js`, `t_hand.js`, `t_body.js`, `t_graph.js`, `t_v5.js`, `sheet.js`), read in full. Every utility signature quoted below was checked against the source, not the reports. Research-1's Howard–Knutson coefficients are unverified except what meanderpy carries (ω = −1, γ = 2.5, CFL 0.5, cutoff distance 2 W); treat them as starting values to calibrate at checkpoint 1, not as facts.

## 0. Where I differ from the lead's reading

Four changes, each with a reason. Everything else in the lead's direction I adopt.

1. **Bundle and cut-bank asymmetry are one mechanism, not two.** Brainstorm 2's fact 3 and research 1 §5 both say: more than two width drivers on one band → noise. So the strands are *the* banks. One spread profile `S(s)`, one side bias `b(s)`, one shared wobble. No separate offset-bank pair, ever (an offset pair is the strongest river cue on the whole list).
2. **Fan and history go on the concave side; the convex side stays single.** Brainstorm 1 idea 5 says traces on the outer (migrating) side; brainstorm 1 idea 7, brainstorm 2 idea 1 and the river itself say inner. Inner is right: history is where the channel *was*, which is inside the present bend. Adopt inner, and let the pinch at each inflection be the swap. Consistent rule, one flag fewer.
3. **The activity field cannot set wavelength.** Brainstorm 3's `λ = lerp(60, 3, A)` is not how curvature-driven migration behaves: research 1 §1 (and the meanderpy source) show wavelength follows the seed spectrum and the lag length `1/α`, not a local dial. So the ≥4× scale spread comes from **two channel classes with different seeds and lag lengths** (trunk vs. minors, brainstorm 3 idea 5), and `A(x,y)` drives what it genuinely can: migration rate, spread, history keep-probability and crossing permission.
4. **Starting centrelines: chain the existing contour graph, don't ridge-trace ink density.** Brainstorm 1 idea 6's ridge tracer is new infrastructure with its own failure modes. `Territory.contours(S, L)` + `contourGraph` + v5's good-continuation walk (t_v5.js lines 185–203) already yield long polylines that carry the gesture of seeds 3/13/21. Zero new code for the inheritance; the "from nothing" option is a noise walk.

On the white channel: three reports proposed it independently, which is a signal. My ruling is **one event, at most one per sheet, default probability 0.35, tested in its own matrix column**. Not a register and not a hard rule: brainstorm 3's own kill criterion for the hard-rule version ("sparse with no protagonist") is the likeliest outcome on a sheet with 3 channels, and Ian's sketch *draws* its channels. The weakened form I do adopt as an invariant: the present channel is never drawn as a complete two-bank outline; it is only ever strands.

## 1. The three mechanisms

All three read and write one data model (§2). Order of execution per sheet: M1 runs to completion (pure geometry, no ink), then M2 and M3 draw into one `Sheet`, newest first.

### M1 — Migrate and remember (the process; no ink)

Curvature-driven migration of 2–5 open centrelines, with a spatially varying rate from `A(x,y)`, neck detection, and an *editor* that decides what a neck becomes. Snapshots and events are stored; nothing is drawn.

```
seedCentrelines(T, prm, rng) → Channel[]
  if prm.source == 'territory':
    polys = T.contours(T.S, T.labels()).filter(inside 6 mm margin).map(c => c.pts)
    G = contourGraph(polys, 3.5)
    trunk = longest chain by good continuation (reuse the v5 commit walk: edgeFrom/otherEnd,
            turnMax 110°, up to 4 transfers), resample(·, 2), smoothPts(·, 2), ≥ 120 mm
    minors = next 1–4 chains of 40–120 mm not overlapping the trunk (pointHash test at 6 mm)
  else 'nothing':
    trunk = noise walk: heading h += noise1(rng)(s/45)·0.35 rad per 2 mm, 160–280 mm long,
            start inside a 70 % ellipse; minors spawned off it at 2–4 random arc positions
  each Channel: cls, x/y Float64Array at ds, q = cls=='trunk' ? 1 : 0.3–0.6,
                lag = 1/α in mm (trunk 25–40, minor 8–15), kl base rate (trunk 1, minor 1.6)

migrate(channels, A, prm, rng)
  steps = round(180 + 420·prm.drift)                       // 180–600
  for t in 0..steps:
    for ch alive:
      κ = curvature(ch) smoothed [1 2 1]/4 ×2                 // research 1 §1
      R0 = kl(s)·κ ; kl(s) = ch.kl · lerp(0.25, 1.4, A at node)  // the activity field, here
      R1 = ω·R0 + γ·runningExp(R0, exp(-ds/ch.lag))            // O(N) recurrence, ω=-1, γ=2.5
      if ch.reversed covers node i and t ≥ ch.reversalT: use the downstream recurrence instead
      disp = clamp(R1·dt, ±0.5·ds) along the normal; pin 6 nodes at each end (research 1: pad)
      apply; every 3 steps: resample(·, ds); smoothPts(·, 1) every 6 steps
    if t % 8 == 0: snapshots.push({ch, t, pts: Float32Array copy})
    if t % 5 == 0: necks = neckDetect(channels)               // grid hash cell 3 mm,
                                                                 // arc gap > 4·S0, distance < neckW
      for n in necks: editor(n)                                // §1 below
    if channels ≥ 2 and t % 5 == 0: captureDetect()            // cross-channel neck
  return {channels, snapshots, events}
```

`ds` = 2 mm for trunks, 1.2 mm for minors. `dt` such that the trunk apex moves ~0.3 mm/step at kl = 1; calibrate at checkpoint 1 so 400 steps grow 3–5 mature bends on a trunk seeded from a v5 contour.

**The editor** (brainstorm 1 idea 2, minus braid). A neck is a candidate, never automatic. Per sheet it holds a budget (§4). Outcome by where the consequence lands:

- **cut** if the stranded loop would sit over empty ground (mean `distField` inside the loop > 12 mm, computed on a `Sheet` pre-marked with all present centrelines at r = 2): splice, store the loop as `Event{kind:'cutoff', loop, neck}`, smooth ±5 nodes at the join, log `t`.
- **refuse** if the two limbs belong to different channels or the loop is over the heaviest region: add a local repulsion for 20–40 mm so the limbs slide past each other; log `Event{kind:'refuse', span}`. This is the sling band.
- **ignore** when the budget is spent: the neck just keeps narrowing until the CFL clamp stalls it. Fine; a stalled neck is a strong pinch.

**Capture** (brainstorm 1 idea 3): when a minor's node comes within `neckW` of the trunk, the minor's upstream reach joins the trunk (the trunk's `q` steps up by the minor's `q` from that node on), and the downstream reach is marked `abandoned` (stops migrating, `q → 0.15`). Log `Event{kind:'capture', at, t}`.

**Reversal** (brainstorm 1 idea 4 / brainstorm 3 idea 7, one per sheet at most): at `t* = 0.55–0.75·steps`, for one contiguous span of one channel (25–40 % of its length), flip the recurrence direction. Log `Event{kind:'reversal', ch, span, t}`.

**Heterochrony** (brainstorm 1 idea 1) is a *drawing-time* decision made at the end of M1: each channel is assigned its own present time `tDraw ∈ [0.45·steps, steps]`, spread so that at least two channels differ by ≥ 40 % of the run. Its present centreline is `snapshot(ch, tDraw)`, and its history is snapshots before that. That is channel-level heterochrony; bend-level (per-bend `t*` with cross-fades) is checkpoint 4's decision, see §8.

Utilities used: `resample`, `smoothPts`, `noise1`, `rngFor`, `contourGraph`, `edgeFrom`, `otherEnd`, `Territory.contours`, `Territory.labels`, `distField`, `Sheet` (as a bitmap only).

### M2 — Bundle (width from lines; the present tense)

Each channel's present centreline is drawn as K strands around it. Strands are the banks. This is the direct answer to "illusion of line width and narrowness … volume".

```
bundle(ch, A, sheet, hands, rng) → Stroke[]
  C = catmullRom(resample(ch.present, 2), 0.5)      // 0.5 mm samples
  κ = signed curvature, smoothed over 8 mm
  v = |R1| at each node from the last migration step, smoothed 8 mm, then LAGGED 8–15 mm
      downstream (low-pass with a one-sided kernel) so the swell sits after the apex
  S(s) = S0 · (0.25 + 0.75·A(p)) · (0.4 + 1.2·smooth(0, vmax, v)) · prm.spread      // mm
         clamp trunk 0.3–7, minor 0.3–4;  S0 trunk 3, minor 1.5
  b(s) = -sign(κ) settled over a 10 mm window (brainstorm-1 §440-450 style majority), then
         eased to 0 within 6 mm of each sign change                       // the swap
  K(s) = clamp(1 + floor(S(s) / 1.4), 1, 6)
  shared = noise1(rng);  drift(s) = 0.45·hand.A·shared(s / 30)         // ONE slow wobble
  for k in 0..Kmax-1:
    r_k = deterministic quantile in (-1, 1) with jitter: r_k = (2(k+0.5)/Kmax - 1)·(0.85 + 0.3·rng())
    // side bias: fan on the concave side, one firm strand on the convex side
    u_k(s) = b(s) > 0 ? lerp(r_k, |r_k|, b) : lerp(r_k, -|r_k|, -b)
    o_k(s) = drift(s) + u_k(s)·S(s)/2 + 0.25·hand.A·own_k(s / 10)
  quantize(o, s)   // §3: per 10 mm window, sort strands by offset, push each gap out of 0.6–1.3
  for k: strand k exists only where K(s) > k;  split into runs ≥ 12 mm;
         stagger each run's start/end by 3–12 mm; the outermost run on the concave side
         ends with an inward hook (v5 hook code, sign toward the centreline)
  strand k=0 (the convex-side one) uses hand `firm`; others use {...loose, A: loose.A·0.3}
  each run → walkLine(sheet, dests, id_k, {loose:0.3, wander:0.35, yieldP:0.6}, rng, D,
                       {touch:true, r:0.4, cross: meanA(run) > 0.6})
           → handLine(stroke, hand, rng)   // shared wobble is already in the geometry
```

Strands of one channel share a lineage, so `Sheet.related` returns true for them and they may sit 0.2 mm apart or cross. Other channels' ink is a wall except where `A > 0.6` (`cross:true`), which is where tangle is permitted.

Why `handLine` alone will not do: it draws fresh `n1/n2` per call from `rng`, so two strands 1.5 mm apart wobble independently and the width profile becomes noise (brainstorm 2, fact 3). The shared `drift(s)` is added to the geometry before the hand; the hand then adds only a quarter of its usual amplitude per strand. That needs no change to `t_hand.js`.

Utilities: `catmullRom`, `resample`, `noise1`, `makeHands`, `handLine`, `walkLine`, `Sheet.related`.

### M3 — Erode and keep (history, emptiness, events; the past tense)

History is drawn only when tied to an event, only as spans, only on the concave side, and only where a later sweep did not erase it. Drawn newest-first into the same `Sheet`.

```
history(ch, snapshots, events, sheet, erased, hands, rng) → Stroke[]
  candidates = snapshots of ch with t < ch.tDraw whose t is within ±16 steps of an event on ch
               (cutoff, capture, refuse, reversal) or of a curvature-sign flip of a bend (bend
               changing hands: detect by inflection count changing between snapshots)
  keep-probability per candidate = prm.history · lerp(0.3, 1, A at its apex)
  add: displacement rule (research 1 §3.2): keep only sub-arcs displaced > thr ∈ [0.6, 4] mm
       from the previously kept trace, thr redrawn per candidate (gaps then vary ≥ 5×)
  order kept traces newest → oldest
  erased = new Sheet()                                  // a bitmap, not ink
  mark the present bundle's strip into `erased` at r = S(s)/2 + 1
  for trace in kept (newest first):
    spans = arcs of trace on the concave side of the PRESENT bend (dot(normal, toward present) > 0)
            with length 15–60 mm, anchored: one end within 3 mm of present ink or a previous trace
    for span: clip where erased.owner[cellOf(p)] != 0; drop pieces < 8 mm
      draw via walkLine(sheet, dests, id_trace, {loose:0.5, wander:0.5, yieldP:0.5}, rng, D,
                        {touch:true, r:0.4, noSwerve:true})   → handLine(·, loose, rng)
      T-ends (stopped by ink or by `erased`) get an inward hook, capped one per 25 mm
    mark this trace's strip into `erased` at r = 1.2                   // erases what is older
  treeRingGuard(kept spans)                             // §6 row 1; if it fires, drop the offending
                                                        // middle trace and re-run from that trace
```

**Oxbows** (cut events): the stored loop is drawn once, occasionally twice (second pass offset 1.5–3 mm, 40–70 % of the arc), as an **open** arc: remove 4–12 mm at the old neck, hook both ends inward 2–5 mm, and drop strands along the arc so the far side is a single line. Never closed, never filled. If two oxbows on a sheet open within 60° of the same direction, the later one is not drawn.

**Refuse events** are already visible in the geometry (two channels shoulder to shoulder); M3 adds nothing except that the two channels are `related` along the refuse span so the strands may touch there.

**Abandoned reaches** (capture losers): drawn as one strand only, hand `loose`, with the far end fading by dropping to `walkLine` `yieldP: 0.9` so it breaks and stops in open ground. These are the long open lines between things.

**White channel** (event, ≤ 1 per sheet, probability `prm.white`): the trunk's present bundle is *not* drawn. Instead its strip is marked into the ink `sheet` under a reserved id (1, unrelated to every lineage) at r = max(2, S(s)/2), before anything else is drawn. Everything else stops at its edge (the walker sees a wall), and the T-end hooks it collects outline a ribbon nobody drew. Its history and oxbows are drawn as usual, so the densest ink sits against the one undrawn thing. Kill on sight if the ribbon is not findable in the thumbnail in ~2 s, or if it closes on itself.

Utilities: `Sheet` (twice: ink, and `erased` as a bitmap), `distField`, `walkLine`, `handLine`, `cellOf`, `smooth`.

## 2. Data model

```js
Channel  { id, cls:'trunk'|'minor', x:Float64Array, y:Float64Array, n, ds,
           q, kl, lag, alive, abandonedFrom, capturedBy, reversal:{i0,i1,t}|null,
           tDraw, present:[[x,y]] }          // present = snapshot at tDraw, as [x,y] pairs
Snapshot { ch, t, pts:Float32Array }         // every 8 steps; ~75 per channel at 600 steps
Event    { kind:'cutoff'|'refuse'|'capture'|'reversal'|'flip'|'white',
           ch, t, at:[x,y], loop?:[[x,y]], neck?:[i,j], span?:[i0,i1] }
Trace    { ch, t, spans:[[[x,y]]], drawn:boolean }
Strand   { ch, k, runs:[[[x,y]]], hand:'firm'|'loose' }
Lineage  lin: Map<sheetId, channelId>; related(a,b) = lin(a)==lin(b)
           || refusePair(lin(a),lin(b)) || capturePair(lin(a),lin(b))
Output   lines: [{ core:-1, kind:'strand'|'trace'|'oxbow'|'abandoned'|'hook',
                  strokes:[[[x,y]]], ch, t, k }]     // the shape sheet.js and svgOf already read
Recipe   { seed, prm, channels, events:[{kind,t,at}], tDraw[], inkMm, gapHist, spacingCV, density }
```

`Sheet` is used three ways, all with the existing class: the ink sheet (with `related` set, as v5 does at t_v5.js:49–56), the `erased` bitmap (owner ≠ 0 means "a later sweep passed here"), and, when the white event fires, the reserved id 1 for the undrawn ribbon. `Sheet.mark` writes only empty cells, so marking the ribbon first makes it authoritative.

Hook-up: in `runTerritory` (t_body.js:535) add `else if (prm.render === 'meander') T.meander(cores, rngFor(seed, 6161));` and inside `T.meander` replace `this.lines` wholesale (the v2 base is input, not output). `sheet.js` needs no change: `random` gives the seed and the cores, `prm.render:'meander'` routes it. The `Recipe` object goes in `res.meander` for the review's withheld-recipes file.

Determinism: every random stream via `rngFor(seed, key)`, keys 6161 (migration), 6162 (bundle), 6163 (history), 6164 (events). No `Math.random`, no `Date`, no sort without a total order (break ties on `id`).

## 3. Weight and width model (mm)

Pen 0.4 mm plotted; sheet SVG at `w: 0.4`. Everything below assumes viewing a plot at ~40 cm.

| Quantity | Value | Why |
|---|---|---|
| Strand gap zones | merge 0.15–0.45 · **dead 0.6–1.3** · spread 1.5–6 · separate > 8 | brainstorm 2 fact 1; the dead zone is the railway/ruled-double look |
| Quantizer | per 10 mm window, gap < 0.95 → pull to ≤ 0.45; else push to ≥ 1.5; correction low-passed over 10 mm so it never jitters; a strand changes zone only by crossing its sibling | brainstorm 2 idea 2 |
| Spread S(s) | trunk S0 3, range 0.3–7; minor S0 1.5, range 0.3–4; scaled by `prm.spread` | volume needs change, not width |
| Width ratio | max S / min S ≥ 2.5 per channel, else raise the `v` term until it is | anti-pipe |
| Swell lag | 8–15 mm downstream of the apex | anti-sausage (pinch and swell never coincide) |
| Pinch | S → 0.3 within ±6 mm of each inflection; the fan swaps sides there | the ribbon turns |
| Strand count K | 1 + floor(S/1.4), 1–6; convex side always exactly one firm strand | one lit edge, one heavy edge |
| Strand ends | staggered 3–12 mm; ≤ 60 % of a channel's length carries K ≥ 3 | anti "one handwriting" |
| Shared wobble | 0.45·A_loose at λ 30 mm on the geometry; per-strand hand at 0.3·A | banks correlate |
| History spans | 15–60 mm, one-sided, 0–5 per bend, spacing from displacement thresholds 0.6–4 mm redrawn per trace | uneven by construction |
| Oxbow | one pass (30 % chance of a second at 1.5–3 mm), neck gap 4–12 mm, hooks 2–5 mm | open, never a bean |
| Hooks | 2–5 mm, inward, at T-ends only, ≤ 1 per 25 mm | the sketch |
| Ink total | 1 600–4 200 mm per sheet (v5 defaults landed ~2 500) | density, not lines |
| Weight contrast | top-decile 10 mm-cell ink density ≥ 4× the median non-empty cell | "more weight at parts" |
| Emptiness | ≥ 35 % of cells farther than 8 mm from any ink, and the largest empty region touches ≤ 2 sheet edges | shaped ground |
| Anti-map invariants | no bank pair touches two sheet edges; gap CV ≥ 0.4 over any 30 mm of a channel with K ≥ 2; trunk λ / minor λ ≥ 4; every channel end is inside the sheet and hooked or faded | brainstorm 3 §"minimum cue", fixed, not exposed |

## 4. Event budget (per sheet, scaled by `prm.events` ∈ 0–3, default 2)

| Event | Default count | Hard cap | Placement rule |
|---|---|---|---|
| Cutoff → oxbow | 1–2 | 3 | only where the loop lands over empty ground; opening directions ≥ 60° apart or the later one is undrawn |
| Refuse (sling) | 0–2 | 2 | between the two heaviest masses, or between different channels |
| Capture | 0–2 | 2 | needs ≥ 2 channels; the trunk always wins |
| Reversal | 0–1 | 1 | one span of one channel, 25–40 % of its length |
| White channel | 0–1 (p = `prm.white`, default 0.35) | 1 | trunk only, and only if the trunk has ≥ 2 traces so the ribbon has edges |
| Heterochrony | always at channel level | – | ≥ 2 channels differ in `tDraw` by ≥ 40 % of the run |
| Braid / knot / net / aperture / cancel | 0 | 0 | not this round (§9) |

About a fifth of sheets should end up with only heterochrony and one cutoff. An event-less sheet is allowed; an event-saturated one is a failure.

## 5. Parameters exposed to the page (9 new; hand params `sway/overshoot/lifts/tremor` are inherited)

| Name | Default | Range | What it moves |
|---|---|---|---|
| `source` | `'territory'` | `'territory' | 'nothing'` | centrelines from the seed's contour graph, or a noise walk |
| `channels` | 3 | 2–5 | 1 trunk + (channels−1) minors |
| `drift` | 0.6 | 0.2–1 | migration steps 180–600: how far the sheet leaves its inheritance |
| `spread` | 1 | 0.5–2 | multiplier on S(s); 0.5 is nearly single lines |
| `history` | 0.6 | 0–1 | keep-probability of event-dated traces; 0 = present tense only |
| `activity` | 0.7 | 0–1 | contrast of `A(x,y)` (0 = flat: no registers) |
| `events` | 2 | 0–3 | scales every row of §4 |
| `white` | 0.35 | 0–1 | probability of the white-channel event (1 forces it) |
| `hetero` | 0.6 | 0–1 | spread of `tDraw` across channels (0 = one clock) |

`A(x,y)`: a 60×44 grid of two or three broad noise blobs plus one sharp ridge, contrast set by `activity`, seeded from `rngFor(seed, 6160)`. Sampled bilinearly.

## 6. Kill table

| # | Criterion | How measured or seen | What to change |
|---|---|---|---|
| 1 | Tree rings: ≥ 4 nested traces with spacing CV < 0.25 | automatic: sample normals of each present bank every 5 mm, count trace crossings within 20 mm, CV of gaps; logged in the recipe and printed on the contact sheet | drop the middle trace of the run (`treeRingGuard`), widen displacement thresholds; if it persists, cap traces per bend at 3 |
| 2 | Railway / ruled doubles: > 15 % of strand-gap length in 0.6–1.3 mm | automatic gap histogram over all sibling strands within 8 mm | quantizer window or thresholds wrong; check the low-pass isn't averaging across a crossing |
| 3 | Pipe: a channel with max S / min S < 2.5 | automatic per channel | raise the `v` term weight; check the lag hasn't flattened v |
| 4 | Sausage: pinch and swell centred within 5 mm | automatic: argmin/argmax of S per bend | swell lag too short |
| 5 | River / map: ≥ 3 of 12 thumbnails named "river" or "map" unprompted | blind review | first check invariants 1–4 in §3 actually fired; then lower `spread`, raise `hetero`, and make sure the trunk has a hooked end inside the sheet |
| 6 | Closed bean: any oxbow with neck gap < 4 mm drawn, or any loop reading as closed | automatic gap check + review | widen the neck cut; drop the second oxbow pass |
| 7 | Through-flow: a bank pair (K ≥ 2) within 6 mm of two sheet edges | automatic | shorten the trunk or curl its ends (pinned nodes get inward curvature) |
| 8 | One handwriting: strand-count histograms of all channels within 10 % of each other, or K ≥ 3 over > 60 % of any channel | automatic | S0 per class too close; activity contrast too low |
| 9 | Hairball: any 20 mm disc holds > 400 mm of ink | automatic density grid | crossing permission threshold (`A > 0.6`) too permissive; cap `cross` strands to 2 per channel |
| 10 | No protagonist: top-decile density < 4× median non-empty | automatic | history too even; raise `A` contrast or concentrate keep-probability on the trunk |
| 11 | Inheritance invisible: blind reviewer pairs meander outputs with v5 seeds 3/13/21 at chance | review, 3 + 3 decoys | lower `drift` to 0.4; if outputs are "v5 plus loops", raise it |
| 12 | Heterochrony invisible: reviewer cannot find a "young" and a "stranded" bend in most cells | review | move to bend-level heterochrony (checkpoint 4 decision) |
| 13 | Reversal reads as fur/jitter | review of the reversal cell vs. its twin | cap the span at 25 %; if still nothing, drop reversal |
| 14 | White channel not findable in ~2 s, or reads as a road, or closes | review | it stays an event at p ≤ 0.35 or is dropped; never widen it to fix legibility |
| 15 | Wallpaper: three chosen thumbnails not distinguishable at sheet size | review | `A` field too weak, or event budget too even across seeds |

Rows 1–4 and 6–10 run in node on every render and are printed in the recipe; the contact sheet caption carries a one-letter flag per row so the lead sees failures before the reviewer does.

## 7. Blind test matrix

24 cells, 3 columns. IDs are neutral; the mapping below is the withheld recipe. Compatible with `sheet.js` as it stands (`random` supplies both seed and cores; `source:'nothing'` ignores the cores).

```json
{
 "title": "meander round 1",
 "cols": 3,
 "w": 0.4,
 "prm": {
  "loose": 0.5, "yieldP": 0.5, "wander": 1, "reach": 15, "spread_v2": 0.7, "eps": 0.03,
  "borders": true, "outer": true, "voids": false, "interior": false, "disregard": 0.15, "hyst": 25,
  "render": "meander",
  "source": "territory", "channels": 3, "drift": 0.6, "spread": 1, "history": 0.6,
  "activity": 0.7, "events": 2, "white": 0.35, "hetero": 0.6
 },
 "cells": [
  {"id": "K01", "random": 3,  "order": "reversed"},
  {"id": "K02", "random": 13, "order": "reversed"},
  {"id": "K03", "random": 21, "order": "reversed"},
  {"id": "K04", "random": 7,  "order": "reversed"},
  {"id": "K05", "random": 34, "order": "reversed"},
  {"id": "K06", "random": 58, "order": "reversed"},
  {"id": "K07", "random": 3,  "order": "reversed", "prm": {"spread": 0.5, "channels": 3}},
  {"id": "K08", "random": 13, "order": "reversed", "prm": {"spread": 0.5}},
  {"id": "K09", "random": 21, "order": "reversed", "prm": {"spread": 0.5}},
  {"id": "K10", "random": 3,  "order": "reversed", "prm": {"history": 0}},
  {"id": "K11", "random": 13, "order": "reversed", "prm": {"history": 0}},
  {"id": "K12", "random": 21, "order": "reversed", "prm": {"history": 0}},
  {"id": "K13", "random": 7,  "order": "reversed", "prm": {"events": 0, "white": 0, "hetero": 0}},
  {"id": "K14", "random": 34, "order": "reversed", "prm": {"events": 0, "white": 0, "hetero": 0}},
  {"id": "K15", "random": 58, "order": "reversed", "prm": {"events": 0, "white": 0, "hetero": 0}},
  {"id": "K16", "random": 3,  "order": "reversed", "prm": {"white": 1}},
  {"id": "K17", "random": 13, "order": "reversed", "prm": {"white": 1}},
  {"id": "K18", "random": 21, "order": "reversed", "prm": {"white": 1}},
  {"id": "K19", "random": 3,  "order": "reversed", "prm": {"source": "nothing"}},
  {"id": "K20", "random": 13, "order": "reversed", "prm": {"source": "nothing"}},
  {"id": "K21", "random": 21, "order": "reversed", "prm": {"source": "nothing"}},
  {"id": "K22", "random": 7,  "order": "reversed", "prm": {"activity": 0}},
  {"id": "K23", "random": 34, "order": "reversed", "prm": {"activity": 0}},
  {"id": "K24", "random": 58, "order": "reversed", "prm": {"activity": 0}}
 ]
}
```

Note: the v2 base param is named `spread` in the v5 configs (`"spread": 0.7`); the meander `spread` collides with it. Either rename the meander one (`band`) or, as above, keep `spread` for meander and pass the v2 one under a new key the Territory constructor accepts. Decide at scaffold time; don't let the two silently share a key.

Withheld mapping: K01–06 full defaults (the six seeds); K07–09 bundle nearly off (isolates M2); K10–12 history off (isolates M3); K13–15 no events, one clock (isolates the editor and heterochrony); K16–18 white channel forced; K19–21 from nothing (isolates inheritance, row 11 pairs these against K01–03); K22–24 flat activity (isolates unity). Review asks, per cell: registers count, named associations, where the eye rests, is width read as volume, and the row-5 and row-11 questions. Provide 1:1 crops of K01–03 and K16–18: thumbnails merge gaps that paper will not (brainstorm 2's first-experiment note).

This same file is the speed test: 24 cells ≤ 5 s in node, measured with `process.hrtime` around `runTerritory` only.

## 8. Build order with checkpoints

0. **Scaffold** (½ session). `t_meander.js`, the dispatch line in `runTerritory`, README build line (`… t_graph.js t_v5.js t_meander.js`), `A(x,y)` field, `Recipe` plumbing into `res.meander`, a node smoke script asserting determinism (two runs, same seed, identical stroke JSON) and timing. **CP0:** matrix renders 24 empty cells in < 1 s.
1. **M1 without ink.** Seeding from the contour graph and from nothing, migration, snapshots, neck detection with cut only, capture. Debug render: present centreline single, all snapshots faint grey (debug flag, never in the review). **CP1:** on seeds 3/13/21 at drift 0.6 the trunk grows 3–5 bends, no kinks, 1–3 cutoffs fire, migration ≤ 80 ms, and the trunk is recognisably the seed's main contour. Calibrate `dt`, `lag`, `neckW` here and write the numbers into the file header.
2. **M2 bundle.** Spread, side bias, shared wobble, quantizer, stagger, hooks. **CP2:** rows 2–4 and 8 pass on all six seeds; a 1:1 crop of seed 13's trunk reads as one wide mark that turns, not as a line drawn several times. If it reads as a road, the convex strand is too parallel: give it 0.3·A more of its own noise before touching S.
3. **M3 history.** Event-dated candidates, displacement thresholds, newest-first erosion with the `erased` bitmap, oxbows as open hooked arcs, abandoned reaches, `treeRingGuard`. **CP3:** rows 1, 6, 7, 10 pass; seed 3's right half is empty *with an edge* (truncated ends agree on a line nobody drew).
4. **Events and time.** Refuse, reversal, channel-level heterochrony, white channel, the budget. **CP4:** render K13–15 against K04–06; if the reviewer (or you) cannot find a young and a stranded bend in most default cells, implement bend-level heterochrony (inflection-to-inflection segments tracked by nearest-inflection matching, per-bend `t*`, 10–15 mm cross-fade at stitches) before the review; otherwise leave it in §9.
5. **Matrix and review round 1.** Sheets, 1:1 crops, recipes withheld, Sonnet appends "Meander round 1" to `docs/reviews/meander-sonnet.md`. Fix only what the kill table names.
6. **One iteration, review round 2, evidence.** `shots/meander-<date>/` with README, recipes, sheets. Then Ian, "ready for you to check", on screen only.

Commit at CP1, CP3 and after each review round.

## 9. Not this round

- **Braid / knot tangle** at necks (brainstorm 1 idea 2's third outcome): v5's knot was the hairball failure; tangle this round comes only from `cross:true` strands in high-`A` zones.
- **Bend-level heterochrony** unless CP4 forces it.
- **Magnifier lobe**, **crop from a larger field** (brainstorm 3 wild card and idea 6): both are composition wrappers to try once the core reads.
- **v5 events** (net, aperture, cancel, chord), **knots**, **searching passes**: nothing from `t_v5.js` runs in `meander` mode; the v2 base lines are input only and are not drawn.
- **Ridge tracing of ink density** for seeding; **Kinoshita curve** seeds (textbook loops).
- **Flux width from `distField` clearance**, **pressure envelope** (brainstorm 2 ideas 3, 6), **sheet-wide nib field** (idea 5): each is a second width driver. Revisit only if M2 passes rows 2–4 and still reads flat.
- **Interference patch / net on one lobe** (research 2 B4): one-use idea for a later round, with its stated cultural caution.
- **Bank lag as a separate width process** (brainstorm 1 idea 7): subsumed by M2's fan on the concave side.
- Plotting, any `axibridge/` change, colour, multi-pen, the bench port.

## 10. Risks I would watch during the build

- **Cost creep is in the walker, not the sim.** Research 1 estimates 0.1–0.15 s for the migration alone at 1000 steps; at 180–600 steps and N ≈ 150–400 per channel it is ~30–60 ms. The v5 experience says `walkLine` + `handLine` over 20–40 runs is ~50 ms. Keep the sum honest with the CP0 timer; the first lever is snapshot cadence, the second is `steps`, never the strand count.
- **`smoothPts` shrinks.** Every pass pulls curves inward; used every step it will damp the migration into a sine. Once per 6 steps, one pass, and smooth curvature rather than positions if bends still fail to grow.
- **`resample` is arc-length linear and re-emits the last point only if > 0.3·step away**, so the node count wobbles by one; index-based bookkeeping (pinned ends, reversal spans) must be re-derived from arc length after each resample, not carried as indices.
- **`Sheet.hit` returns `'self'` when the same id revisits after 8 mm of arc** (`SELFWIN`). A strand that legitimately crosses its own channel's earlier stretch is fine (siblings are `related`), but a *single* strand doubling back on itself will stop. Give each run its own id under the channel's lineage, as v5's `newId(eid)` does.
- **The two `spread` keys** (§7 note).
