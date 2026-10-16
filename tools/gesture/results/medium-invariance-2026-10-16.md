# Medium invariance — 2026-10-16

Question (Ian, after v3): find what the Matisse etching-vs-lithograph
control separates on, remove it, and rerun the artist test.

Setup: Matisse 31 (etching 15, lithograph 10, other 6), Hokusai 27, Ingres
34; hybrid extractor; geometry-only panel (no width, no endings); grouped CV.
**Control** = Matisse etching vs Matisse lithograph — same hand, so it
should sit at AUC ≈ 0.5. **Target** = Matisse vs Hokusai vs Ingres.
Code: `experiments/medium_invariance.py`; full tables in
`.local/gesture/out/medium_invariance/report{,_inlp}.md`.

## 1. What the control separates on

Univariate etching-vs-litho AUC, top features (lithographs higher unless
AUC < 0.5): `k_q10` 0.90 (lithos have almost no near-straight passages),
`len_ink` 0.16 and `len_count` 0.19 (fewer, sparser strokes), `k_css_zc2`
0.81 (more curvature sign changes at fine scale), `cl_segs_per_stroke` 0.78,
`k_q50` 0.78, `ext_turn_q50` 0.77, `rel_gap_log_q50` 0.77. In words: crayon
grain makes the extracted centreline wander at a few line widths, and
lithographs are sparser sheets. 20 of 65 geometry features have
|AUC − 0.5| > 0.2.

## 2. Three remedies, held-out medium control vs artist test

| # | remedy | medium AUC held-out (want .5) | artists bacc logreg / forest (chance .333) | M–H AUC | M–I AUC |
|---|---|---|---|---|---|
| 1 | none (σ = 0.01·ref) | 0.77 | 0.73 / 0.74 | 0.86 / 0.85 | 0.86 / 0.86 |
| 2 | **scale**: σ ≥ 7 w | 0.76 | 0.82 / 0.81 | 0.91 / 0.90 | 0.87 / 0.88 |
| 3 | scale σ ≥ 12 w | 0.65–0.70 | 0.71 / 0.78 | 0.80 / 0.90 | 0.81 / 0.89 |
| 4 | **drop** features, σ ≥ 7 w, \|AUC−.5\| > 0.15 | 0.63 | 0.75 / 0.71 | — | — |
| 5 | drop, σ ≥ 12 w, > 0.10 | 0.57 | 0.56 / 0.65 | — | — |
| 6 | **project** (INLP ×4), σ ≥ 7 w | **0.44 ± 0.18** (linear probe) · 0.61 ± 0.17 (forest probe) | **0.83 / 0.79** | **0.90 / 0.93** | **0.89 / 0.88** |
| 7 | project (INLP ×8), σ ≥ 7 w | 0.50 ± 0.18 (linear) · 0.57 ± 0.18 (forest) | 0.78 / 0.79 | 0.83 / 0.90 | 0.90 / 0.87 |

- **Dropping features doesn't work.** In-sample it looks perfect (the
  control falls to 0.36–0.56), but held out it barely moves (0.77 →
  0.6), and the artist signal goes with it. Medium is spread thinly across
  many correlated features; removing the loudest ones leaves the rest.
- **Coarser scale alone doesn't remove medium** but does help the artist
  test up to σ ≈ 7 w; beyond ~12 w both signals fade.
- **Nullspace projection works.** Fit the etching-vs-litho directions on
  the Matisse sheets (medium labels only, never artist labels), project them
  out of every drawing's features. At σ ≥ 7 w, 4 iterations, a fresh linear
  probe can no longer recover medium on held-out sheets, and artist
  separation is unchanged or better (0.83 / 0.79, chance 0.33). A non-linear
  probe still finds a little (0.57–0.61), so some non-linear medium signal
  remains.

## 3. What this does and does not show

- **Shows:** the artist separation is not *printmaking medium* in disguise
  — removing everything that tells Matisse's etchings from his lithographs
  leaves Matisse vs Hokusai at 0.90–0.93 and Matisse vs Ingres at 0.88–0.89.
- **Does not show:** invariance to brush (Hokusai) or graphite (Ingres).
  The only medium direction we can estimate *within one hand* is
  etching vs lithograph, so Hokusai vs Ingres (0.96–0.99) is still brush vs
  pencil as much as anything. Removing those needs a within-hand comparison
  across them (an artist with both pen and brush, or pen and pencil, in the
  corpus) — Matisse's 6 "other" sheets (pen drawings, linocut, woodcut) are
  too few and too mixed to fit a direction.
- Small samples (15 vs 10 for the control): held-out standard deviations are
  ±0.12–0.19. Treat as indicative.

## 4. Recommendation

Adopt **σ = max(0.01·ref, 7 w) + INLP ×4 fitted on known within-hand medium
pairs** as the panel's standard preprocessing for artist comparisons, and
grow the within-hand medium set before trusting cross-medium claims. Stage-2
artist gate: **met for printmaking medium**, open for brush/graphite.
