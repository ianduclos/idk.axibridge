# Blind visual judge — 2026-10-16

Plan item D2 ("AI as critic"), calibrated before use. `experiments/blind_pairs.py`
builds side-by-side crop pairs (A | B): one crop from a real drawing (the
long-stroke subset the grammar learns from), one from a machine drawing,
both re-rendered from stroke geometry with the same pen width and smoothing.
A Sonnet judge sees only the pair images (never code, key or labels) and
answers which side is the human's, with confidence and the deciding cue.
Answer keys live outside the repo; archived copies with the answers in
`.local/gesture/out/blind/round{1,2}/`.

Conditions, shuffled together:

- **test** — real vs grammar v3 (16 pairs per artist)
- **calib_pos** — real vs shuffled-segments null; a judge worth trusting
  should find these
- **calib_neg** — real vs identity null (same curvature, only re-integrated);
  should be at chance. Above chance means the judge is reading pipeline
  artefacts, and the test number is inflated

## Results

| # | round | calib_pos | calib_neg (want .5) | test: all | Matisse | Hokusai | Ingres |
|---|---|---|---|---|---|---|---|
| 1 | 1: smoothing at 5 px only | 16/16 | **11/15 = 0.73** (p = .06) | 42/47 = 0.89 | 14/16 | 16/16 | 12/15 |
| 2 | 2: + snapped joins, no crop reuse, plate lines dropped | 15/16 | 10/15 = 0.67 (p = .30) | **39/47 = 0.83** | 14/16 | 14/16 | 11/15 |

1. **Round 1 was contaminated.** The judge's top cues were rendering and
   sampling artefacts: hairline gaps where strokes meet (re-integrated lines
   drift off their junctions), the same real crop recurring across pairs,
   and straight plate-mark lines. The calibration caught it: calib_neg
   came out at 0.73.
2. **Round 2 removed those artefacts**, applied identically to every
   drawing. calib_neg fell to 0.67, which is not significant at n = 15 but
   is still above chance, so treat the test number as an upper bound. The
   judge now names content cues instead.
3. **Grammar v3 is still visibly machine at 0.83.** By the judge's own
   account the tells are:
   1. **coherent contours forming a figure** (hand, face, cuff) — the most
      decisive cue;
   2. **tremor and wavering** in real lines that survives 5 px smoothing;
   3. **junction behaviour**: T-junctions, near-meetings, small ticks at line
      ends;
   4. **machine tells**: isolated fragments unrelated to their neighbours,
      over-regular curves, loops and spirals, random straight crossings.

   Ingres is the closest to passing (11/15, n.s.). Sparse crops felt
   impossible to call.

## What it tells the research

- The statistics and the eye agree that **composition is the biggest gap**
  (cue 1 and the "isolated fragments" tell). This is the topology agent's
  remit.
- **Tremor at a few line widths** is part of the hand. The grammar works at
  σ = 2 w and cannot express it. The kinematic (lognormal) model or a
  residual "tremor" layer could.
- **The judge is useful as a second instrument**, but only with calib_neg
  alongside, and only after artefact hunts like round 1 → 2. Use ~30+ pairs
  per condition next time for tighter intervals.
