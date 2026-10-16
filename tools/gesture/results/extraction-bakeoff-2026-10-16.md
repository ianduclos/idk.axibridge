# Extraction bake-off — 2026-10-16

Stage 1 of `docs/IDEAS-gesture-bank.md`: which raster → strokes technique to
build on. Six entrants, built in parallel by separate agents against one
harness (`gesture/extract_eval.py`, `experiments/bench_extract.py`).

- **GT** = 18 synthetic renders with known strokes (`gesture/synth.py`):
  X / T / closed loop / random clothoid scenes / Matisse-like scenes, each at
  3 px clean and 6 px noisy.
- **Real** = the 19 tier-A Matisse scans from SMK, capped at 2500 px.
  Scored against reference ink v2 (contrast-stretched; fine ∪ coarse Sauvola
  mask). v1 found no ink on the faint pencil KKS18238 and handed `naive`
  its own mask as the reference; every entrant flagged it.

## Scores

| # | method | GT cover | GT prec | GT contin | GT frags | GT κ err | real cover | real prec | real mean_len | real short | real rough | s/scan |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | naive (skeleton edges) | 0.999 | 1.000 | 0.837 | 1.41 | 0.561 | 0.753 | 0.947 | 0.052 | 0.703 | 6070 | 0.8 |
| 2 | extract (hysteresis ink, skeleton graph, pairing, plate removal) | 0.992 | 0.997 | 0.974 | 1.06 | **0.718** | 0.935 | 0.965 | **0.202** | **0.124** | 6081 | 2.1 |
| 3 | voronoi (sub-pixel outline → medial axis) | 1.000 | 1.000 | 0.999 | 1.00 | 0.123 | 0.792 | 0.947 | 0.105 | 0.552 | 8018 | 1.3 |
| 4 | flow (orientation-field tracing) | 0.998 | 0.999 | 0.971 | 1.07 | 0.124 | 0.924 | 0.842 | 0.097 | 0.367 | **4899** | 3.2 |
| 5 | refine (skeleton + junction matching + sub-pixel centroid) | 1.000 | 1.000 | **0.999** | 1.00 | **0.104** | 0.848 | **0.991** | 0.179 | 0.204 | 7045 | 1.7 |
| 6 | ridge (Steger Hessian ridges, gap linking) | 0.999 | 1.000 | 0.971 | 1.08 | 0.160 | **0.967** | 0.886 | 0.161 | 0.325 | 6340 | 2.1 |

Lower is better for frags, κ err, short and rough. κ err = median
| |κ_found| − |κ_truth| |·ref_length at σ = 2w, stroke interiors.

## What the overlays show

Crops: `bakeoff-KKS10071.jpg` (crayon lithograph),
`bakeoff-KKS13429_V.jpg` (faint pen), `bakeoff-KKS1961-113.jpg` (etching
with tile grid and flower motifs). Panel order: naive, extract, voronoi /
flow, refine, ridge.

1. **Faint pen lines** (KKS13429_V): only the methods that don't start from
   Sauvola — extract (hysteresis), flow (background-subtracted relative
   threshold), ridge (no binarisation) — find them. naive, voronoi, refine
   see one line out of dozens.
2. **Crayon grain** (KKS10071): extract and refine give one long centreline
   per crayon stroke; ridge nearly so; naive and voronoi shatter into grain.
3. **Dense small motifs** (KKS1961-113 flowers): every method fragments.
   Not a priority — Matisse's hand is in the long contours.
4. **Signatures, edition numbers and plate marks** are extracted by all but
   extract (which erases plate lines and what lies outside them).

## Verdict

No single winner. **extract** has the best real-scan topology (coverage,
continuity, few fragments, faint-ink robustness) and the worst centreline
accuracy on ground truth; **refine / voronoi / flow** have 5–7× better κ
because they re-centre sub-pixel. Every κ-accurate method gets its accuracy
from one component: a normal-profile centroid (refine, flow's
core-of-profile) or a Steger Taylor step (ridge). That component is
extractor-independent.

Next: `extract` topology + a generic sub-pixel post-pass
(`gesture/subpixel.py`, `extract_hybrid.py`) — in progress at time of
writing. Grafts the agents recommended: refine's per-junction optimal
matching + corridor contraction for shallow crossings, flow's
cross-section-width crossing test, ridge's FWHM width estimate and gap
linker, voronoi's shallow-X Y-node merge.

## Known limits of the harness

- GT set is small (18 renders); one collapse parameter flipped one case.
  Treat differences < 0.02 in GT continuity as noise.
- Real-scan metrics are proxies. mean_len rewards joining; always check
  overlays before trusting it.
- KKS18238 (faint pencil, 967 px) is an outlier for every method.
