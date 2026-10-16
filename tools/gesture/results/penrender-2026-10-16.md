# Nib ribbons that read as ink at real pen widths — 2026-10-16

Round 6, item 3: at a 0.35 mm pen the nib regime (r ≤ 1.1) reads as a hollow
double line, "a pipe". This thread renders the same `RegimeStroke` marks with
seven fill strategies, simulates them on paper at real pen widths, and
measures them against the solid ribbon a real nib would leave. It feeds the
open **thickness gap** decision (`docs/IDEAS-gesture-bank.md`, "Open
decisions"). Nothing is settled here. §5 sets out the options.

Code:
- `gesture/penrender.py`: the strategies, the physical preview, the metrics
  and a plot-time estimate.
- `experiments/penrender_study.py`, stages `eval sheets crops blind`
  (≈ 40 s, 3 workers).
- `tests/test_penrender.py`: 15 tests in ≈ 2 s.

Raw outputs: `.local/gesture/out/penrender/eval.json` and
`eval_summary.json`. Sheets: `penrender-sheet-p02.jpg`, `-p04.jpg`,
`-p08.jpg` and `penrender-crops.jpg`.

## 1. Pens actually in use

Ian's pen library (`~/.axibridge/pens.json`, read-only) holds:

| # | pen | line width in the library |
|---|---|---|
| 1 | Uniball Black | **0.2 mm** |
| 2 | fineliner black | **0.4 mm** |
| 3 | red brush | 0.4 mm (the default value, so its real width is unknown) |
| 4 | Virtual | 0.4 mm |

There is **no marker**. The test widths are 0.2 and 0.4 mm (real) and 0.8 mm
(hypothetical). The two-pen marker is max(1.0, 2.5·pen) mm: 1 mm for the
real pens and 2 mm at 0.8. That marker is also hypothetical.

## 2. Physical preview

`ink_raster` sweeps a disc of the pen's real width, plus 0.04 mm of ink
spread, along every path at 20 px/mm. It is anti-aliased and softened by a
Gaussian of 0.02 mm. A vertex disc is added for wide pens, because PIL's
wide-line joints leave pinholes, about 1 % of a 1 mm marker's ink.

The target is `ideal_ink`, regime's own ink region (pen-centre region ⊕
pen/2, plus the line runs), rendered the same way. Sheets are rendered at
20 px/mm and **shown at 6 px/mm**, roughly how a sheet reads on a screen.
The crops are shown at 14 px/mm.

Metrics (`evaluate`):
- **coverage**: share of the ideal ink that gets inked.
- **gap**: the widest white gap inside the ideal, ignoring a pen/2 rim. A gap
  over about 0.25 mm is a visible pipe.
- **edge**: the symmetric mean distance between the drawn and ideal ink
  edges. It includes a pipe's inner edges.
- **spill**, pen length and paths.
- **time**: the trapezoid/junction model of `axibridge/estimate.py`,
  re-implemented because the gesture venv has no pydantic. It uses Ian's
  native settings (25 % pen-down, 75 % pen-up, accel 100 %), and counts a pen
  swap as 60 s, which is an assumption.

## 3. Strategies

All are polylines that run along the stroke or round it. Masses (r > 1) keep
regime's concentric fill in every strategy, so the strategies differ only on
the nib.

| # | strategy | what it draws |
|---|---|---|
| a | outline (current) | `regime.render` unchanged: a nib is its two edges. |
| b | inset, narrow full | Concentric insets, forced full where ink < 6·pen and fading by 9·pen. At 0.8 mm it equals b+ (every ribbon is < 4.8 mm). |
| b+ | inset, full | Concentric insets wherever a nib exists, i.e. regime's fill with f = 1. |
| c | lanes along the stroke | Edges, plus passes at fixed normal offsets 0.85·pen apart. Pass j switches on when the gap from pass j−1 to the edge exceeds 0.95·pen. It then sits 0.1·pen inside the edge, so it **peels off the outline tangentially**: no stepped strand starts. |
| d | collapse < 1.2·pen | Ink narrower than 1.2·pen becomes the centreline (r is scaled down smoothly); the rest is drawn as b+. |
| e | nib-point traces | Passes are the paths of points **along the nib edge**, c + λ·a·u(φ). Each pass is the centreline translated along the nib, the way a real broad nib inks, so tight turns cause no swallowtails. Where the stroke runs along the nib (a hairline), the traces crowd together and thin out dyadically. A pass only exists where it is needed to keep neighbours ≤ 0.95·pen apart, so hairlines are not overdrawn. |
| f | two pens | The thin pen draws the outline, the lines and whatever the marker cannot reach (as e). The marker draws concentric insets of the ink eroded by its half-width. The result is two layers and one pen swap. Previews misregister the marker by (0.12, −0.08) mm. |

Shared details:
- **c, e and f end with `touch_up`.** Any white left inside the ideal (a
  mass's round cap beyond the lanes' reach, an inset spine, clip seams) gets
  its own small rings.
- **Every strategy is chained** (`chain`). The pen jumps to the next path
  without lifting only if the straight connector runs over ground the paths
  already ink. This is checked on a coverage raster eroded by pen/2, so a
  connector never adds a visible mark. A test checks that it adds < 1 % ink.

## 4. Results (8 ribbons per pen)

The ribbons are: nib W 1.2 / 2.5 / 4 mm; a loop; the nib angle turning
0 → 150°; W ramping 0.6 → 4.5; line → nib → line; and line → nib → mass →
nib → line. Length and time are totals over all 8, with the ratio to (a) in
brackets. Time excludes the pen swap.

| # | pen | strat | coverage | gap max mm | edge mm | pen m | paths | time s |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.2 | a | 0.363 | 3.70 | 0.057 | 1.21 (1.0×) | 34 | 26 (1.0×) |
| 2 | 0.2 | b | 0.500 | 3.70 | 0.059 | 1.69 (1.4×) | 62 | 43 (1.6×) |
| 3 | 0.2 | b+ | 0.993 | 0.22 | 0.064 | 4.13 (3.4×) | 88 | 86 (3.3×) |
| 4 | 0.2 | c | 0.999 | 0.10 | 0.009 | 5.16 (4.3×) | 56 | 96 (3.6×) |
| 5 | 0.2 | d | 0.992 | 0.22 | 0.063 | 4.12 (3.4×) | 85 | 85 (3.2×) |
| 6 | 0.2 | **e** | 0.999 | 0.00 | 0.008 | 5.78 (4.8×) | 33 | 97 (3.7×) |
| 7 | 0.2 | **f** | 0.999 | 0.10 | 0.013 | 2.16 (1.8×) | 96 | 63 (2.4×) + swap |
| 8 | 0.4 | a | 0.507 | 3.50 | 0.100 | 1.01 (1.0×) | 22 | 21 (1.0×) |
| 9 | 0.4 | b | 0.836 | 3.50 | 0.125 | 1.81 (1.8×) | 71 | 47 (2.3×) |
| 10 | 0.4 | b+ | 0.978 | 0.41 | 0.098 | 2.31 (2.3×) | 61 | 52 (2.5×) |
| 11 | 0.4 | c | 0.998 | 0.10 | 0.010 | 2.92 (2.9×) | 41 | 56 (2.7×) |
| 12 | 0.4 | d | 0.976 | 0.36 | 0.099 | 2.30 (2.3×) | 60 | 51 (2.5×) |
| 13 | 0.4 | **e** | 0.998 | 0.10 | 0.009 | 3.13 (3.1×) | 42 | 60 (2.9×) |
| 14 | 0.4 | f | 0.998 | 0.20 | 0.026 | 2.03 (2.0×) | 87 | 58 (2.8×) + swap |
| 15 | 0.8 | a | 0.709 | 3.11 | 0.172 | 0.92 (1.0×) | 16 | 18 (1.0×) |
| 16 | 0.8 | b/b+ | 0.957 | 0.71 | 0.113 | 1.45 (1.6×) | 32 | 31 (1.7×) |
| 17 | 0.8 | c | 0.997 | 0.10 | 0.010 | 1.76 (1.9×) | 27 | 35 (1.9×) |
| 18 | 0.8 | d | 0.949 | 0.82 | 0.119 | 1.44 (1.6×) | 33 | 32 (1.8×) |
| 19 | 0.8 | **e** | 0.997 | 0.00 | 0.009 | 1.81 (2.0×) | 29 | 36 (2.0×) |
| 20 | 0.8 | f | 0.998 | 0.00 | 0.011 | 1.52 (1.7×) | 44 | 37 (2.1×) + swap |

**When does an outline become a pipe?** Two edges cover the ribbon only up
to an ink width of 2·pen. With a visible gap at about 0.25 mm, the outline
reads hollow above roughly **0.65 mm of ink at 0.2 mm, 1.05 mm at 0.4 mm and
1.85 mm at 0.8 mm**. Every nib in the regime sheets (W ≈ 1.5–4) is past
that at the real pens.

What the sheets show (looked at, not judged blind):

1. **a** is the pipe at every real pen. At 0.8 it is a heavy "drawn ribbon",
   still hollow above W ≈ 2.
2. **b** fills the narrow nibs but leaves wide ones as outlines with a pooled
   core: a pipe with a filling. At fine pens it is almost a.
3. **b+** (regime's concentric fill made full) reads as solid at 6 px/mm. In
   the crops it leaves **slivers where a ribbon tapers**: an inset ring ends
   and leaves a white wedge of up to 0.4 mm (0.4 pen) or 0.7 mm (0.8 pen).
   This is visible in the twist and ramp rows. It also has the most pen
   lifts.
4. **c** and **e** look like the ideal, both at 6 px/mm and in the crops.
   Their edges are exact (0.01 mm, the raster floor).
   - e draws a whole ribbon as one path where c needs several: 33 paths
     against 56 at 0.2. On the W 0.6 → 4.5 ramp, e is **1 path** at both
     real pens.
   - Through the hook, e and c keep regime's wet / edge processes (they
     build on regime's own paths).
5. **d** looks the same as b+. Under 2·pen the outline already reads as one
   line, so collapsing below 1.2·pen changes nothing you can see. Raising the
   threshold would be an aesthetic regime decision (where the nib "becomes
   the line"), not a rendering fix.
6. **f** is solid with crisp thin-pen edges.
   - It halves the pen length at 0.2 (1.8× outline, against 4.8× for e).
   - It costs many short thin-pen paths (96), so the time saving is only
     2.4× against 3.7×, plus a swap.
   - Misregistration of 0.1–0.15 mm shows as a slightly ragged inner
     texture in the crops, not at the silhouette.
   - At 0.4 it buys nothing over e (58 s against 60 s).

**Not simulated:**
- Ink pooling, darkening or paper pilling where 5–15 passes of a 0.2 mm
  fineliner overlap. e and c put up to about 20 passes across a W = 4 mm
  nib.
- Gel-pen skipping at speed.
- The Uniball's real line, which may run wider than its nominal 0.2 mm.

These are the first things a test plot should check.

## 5. Options for the thickness decision (Ian's call)

| # | option | look | cost vs outline | risk |
|---|---|---|---|---|
| 1 | **e at 0.4 mm** (the fineliner) | solid nib, exact silhouette, ~1 path per ribbon | ×3 pen, ×2.9 time | the overlapping passes on paper (pilling or sheen) are untested |
| 2 | **e at 0.2 mm** (Uniball) | the same, crisper hairlines | ×4.8 pen, ×3.7 time | the same, ×2; gel-pen wetness |
| 3 | **f: 0.2 + a 1 mm marker** | solid; hairlines from the fine pen | ×1.8 pen, ×2.4 time + 1 swap | needs a marker, which Ian doesn't own; registration; pays off only on fill-heavy sheets at fine pens |
| 4 | **keep a** (status quo) | "drawn ribbon" / pipe, as a style | ×1 | that is the round-6 complaint |
| 5 | a below r ≈ 1, e only where r ≥ 1 (or above a width threshold) | the pipe becomes a regime of its own between line and nib | in between | adds a fourth reading where Ian named three |

**Recommendation offered:** option 1. It looks the same as the ideal on every
test ribbon, it is one path per ribbon, and the fineliner is in the drawer. A
second pen (option 3) is worth buying only if a fine-pen sheet's time is
dominated by thick fill. On the ribbon set it saves about a third of the
time at 0.2 mm and nothing at 0.4 mm.

Drop b and d. b+ is dominated by e: e costs about the same time, closes
b+'s slivers and has half the lifts.

Before choosing, plot one strip: nib W2.5 under a, b+ and e at 0.4 mm, about
2 minutes. This settles the one thing the simulation cannot show, which is
how many overlapping fineliner passes behave on Ian's paper.

## 6. Blind judge set (built, not judged)

- **48 pairs** in `.local/gesture/out/blind_nib/pairs/`, with
  `../QUESTION.txt`. Each pair is the ideal solid ribbon against one
  strategy's physical render at 10 px/mm, on the same ribbon.
- Composition: 3 pens × 7 strategies × 2 ribbons (drawn from W2.5, W4, loop,
  twist and transition), plus **6 calibration pairs of ideal vs ideal**. The
  calibration pairs should split about 50/50 at low confidence.
- The question is which panel looks more like a single brush / nib stroke.
- Key: `/tmp/gesture_nib_key.json`, outside the repo. Each entry gives
  `ideal_side`, strategy, pen and ribbon.
- Reading: a strategy that the judge picks at about chance against the ideal
  is indistinguishable from it. The (a) pairs are the positive control.

## 7. Interface

```python
from gesture import penrender as pr, regime as rg
paths = pr.strategy("e")(stroke_or_strokes, pen=0.4)      # standalone, like rg.render
paths = rg.render(stroke, 0.4, nib_renderer=pr.strategy("e"), wet=True)   # as regime's hook
pr.layers(pr.strategy("f")(stroke, 0.2))                  # {0.2: [...], 1.0: [...]}
pr.evaluate(stroke, paths, 0.4)                           # coverage, gap, edge, length, time
```

Through the hook (`(strokes=, pen=, paths=, parts=)`), a, c, e and f build
on regime's paths and geometry. b, b+ and d re-render, so they lose
wet/edge options there; call them directly instead.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
$P -m experiments.penrender_study eval sheets crops blind   # ≈ 40 s, 3 workers
$P -m pytest -q tests/test_penrender.py                     # 15 tests, ≈ 2 s
```

## Blind judge on the nib pairs (run by the lead after this report)

Sonnet judge, images only, key outside the repo; 48 pairs. Question: which
panel looks more like a single solid stroke of a brush or nib? A good
strategy should be indistinguishable from the ideal solid ribbon (≈ chance,
low confidence).

| # | strategy | judge picks the ideal | mean confidence (1–5) |
|---|---|---|---|
| 1 | a outline (current) | 6/6 | 5.0 |
| 2 | b inset, partial | 6/6 | 4.7 |
| 3 | b+ full inset | 6/6 | 4.3 |
| 4 | d collapse thin | 6/6 | 4.5 |
| 5 | f two pens | 5/6 | 2.0 |
| 6 | **c passes along the stroke** | **3/6** | **1.3** |
| 7 | **e nib-point traces** | **4/6** | **1.0** |
| 8 | ideal vs ideal (control) | 2/6 | 1.0 |

c and e read as solid ink at every pen width, matching the coverage
numbers. Paper is still untested: a 2-minute test strip settles it.
