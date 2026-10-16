# Stage-2 run v4 — standard preprocessing (2026-10-16)

`experiments/discriminate.py` now defaults to `--preprocess standard`
(`gesture/medium.py`): panel σ ≥ 7 line widths, then the within-hand medium
directions listed in `docs/research/gesture-corpus/medium-pairs.csv`
(currently Matisse etching vs lithograph) are projected out of the geometry
features (INLP ×4, medium labels only). Width/ending columns are left raw so
"geometry only" stays width-free. `--preprocess raw` gives the old panel.
Hybrid extractor, grouped CV, identity-null control as in v3. Full report:
`.local/gesture/out/discriminate/real-v4-standard/report.md`.

| # | measure | v3 (raw, σ = 0.01·ref) | **v4 (standard)** | want |
|---|---|---|---|---|
| 1 | Matisse etching vs litho, held-out, linear probe | 0.77–0.81 | **0.41 ± 0.19** | ≈ .5 |
| 2 | same, forest probe | 0.76–0.77 | **0.60 ± 0.16** | ≈ .5 |
| 3 | artists only, geometry only, bacc logreg / forest (chance .333) | 0.731 / 0.762 | **0.806 / 0.786** | high |
| 4 | Matisse vs Hokusai AUC, geometry only | 0.822 / 0.851 | **0.894 / 0.921** | high |
| 5 | Matisse vs Ingres AUC, geometry only | 0.857 / 0.870 | **0.872 / 0.877** | high |
| 6 | Hokusai vs Ingres AUC | 0.984 | 0.988 / 0.971 | — (brush vs graphite, not covered) |
| 7 | null vs identity: kappa_permuted / random_walk / shuffled / smooth (logreg) | 0.92 / 0.99 / 0.92 / 0.93 | 0.92 / 0.97 / **0.82** / 0.92 | high |

Reading:

1. **The medium control is gone for a linear reader and mostly gone for a
   non-linear one**, and the artist test got *better*, not worse — the
   artist signal was never mainly printmaking medium.
2. **The null test still passes but softens at the coarser scale**: shuffled
   segments vs identity drops to 0.82 (forest 0.92). Measuring at ≥ 7 line
   widths smooths away some of the fine order that the shuffle destroys.
   Order information lives partly below 7w — worth remembering for the
   grammar, which needs it.
3. **Not covered:** brush (Hokusai) and graphite (Ingres) — no within-hand
   pair yet. Row 6 is still medium as much as hand.
4. Matisse vs the identity null is still 0.89–0.97: the re-integration
   pipeline itself is detectable, which is why nulls are compared to
   identity, not to the real drawings.

Command:

```bash
cd tools/gesture && E=../../.local/gesture/out/extract_hybrid
../../.local/gesture/.venv/bin/python -m experiments.discriminate --name real-v4-standard \
  --group matisse=$E/matisse --group hokusai=$E/hokusai --group ingres=$E/ingres --null-source matisse
```
