# Stage-2 gate, corrected run v3 — 2026-10-16

After the review (`review-2026-10-16.md`): hybrid extractor, fixed fair set
(width, endings, inter-stroke relations and closure excluded), grouped CV
(a sheet and its nulls never straddle folds), pipeline-matched null control,
artists-only accuracy reported on its own. Full reports:
`.local/gesture/out/discriminate/real-v3-hybrid*/report.md` (not committed;
regenerate with `experiments/discriminate.py`, commands below).

## 1. Null test — the gate number

Each null vs the **identity control** (the source's own κ(s), measured and
re-integrated exactly like the nulls; nothing shuffled), fair feature set:

| # | null | logreg AUC | forest AUC |
|---|---|---|---|
| 1 | kappa_permuted (same κ values, order destroyed) | 0.924 | 0.942 |
| 2 | random_walk | 0.989 | 0.999 |
| 3 | shuffled_segments (real pieces, wrong order) | 0.920 | 0.993 |
| 4 | smooth_noise | 0.931 | 0.950 |

**Passes.** What the shuffles destroy is detectable even when the pipeline
is held constant. Shuffled segments and permuted κ are the hardest: order
along the line matters, but less than raw curvature content.

## 2. Artist test (geometry only = no width, no endings)

| # | run | σ | artists-only bacc logreg / forest (chance 0.333) | M vs H AUC | M vs I AUC | H vs I AUC |
|---|---|---|---|---|---|---|
| 1 | v3 | 0.01·ref | 0.731 / 0.762 | 0.822 / 0.851 | 0.857 / 0.870 | — |
| 2 | v3, σ ≥ 3w | max(0.01·ref, 3w) | 0.716 / 0.746 | 0.778 / 0.829 | 0.857 / 0.870 | — |
| 3 | v3, σ ≥ 7w | max(0.01·ref, 7w) | **0.815 / 0.782** | **0.903 / 0.909** | 0.862 / 0.875 | 0.988 / 0.968 |

The review's worry was that σ/w (pixels per line, a per-collection
constant) drives the separation. Floor σ at 7 line widths, which puts every
collection at the same scale relative to its own line, and separation goes
**up**, not down. So σ/w is not the explanation.

**Still open: medium.** Each artist is one medium here (Matisse etching /
lithograph / pen, Hokusai brush, Ingres graphite). Hokusai vs Ingres at
0.97–0.99 is almost certainly brush vs pencil as much as hand. The next
honest test is medium-matched — e.g. Matisse etchings vs another
draughtsman's etchings, or Matisse lithographs vs Matisse etchings (should
*not* separate if the panel measures the hand).

## Commands

```bash
cd tools/gesture && E=../../.local/gesture/out/extract_hybrid
../../.local/gesture/.venv/bin/python -m experiments.discriminate --name real-v3-hybrid \
  --group matisse=$E/matisse --group hokusai=$E/hokusai --group ingres=$E/ingres --null-source matisse
../../.local/gesture/.venv/bin/python -m experiments.discriminate --name real-v3-hybrid-sw7-artists \
  --sigma-min-w 7 --group matisse=$E/matisse --group hokusai=$E/hokusai --group ingres=$E/ingres
```
