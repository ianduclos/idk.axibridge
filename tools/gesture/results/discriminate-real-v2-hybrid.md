> **Superseded (2026-10-16 review):** the "fair Pollock" table here did not actually exclude `rel_`, nulls were not compared to a pipeline-matched control, and the multi-class figure is padded by null classes. See `review-2026-10-16.md` and the v3 report.

# Stage-2 run v2 — hybrid extractor (2026-10-16)

Same setup as discriminate-real-v1.md, strokes from `extract_hybrid` (sub-pixel centrelines).
Geometry-only: Matisse vs Hokusai AUC 0.80–0.86 (v1 0.74–0.85), Matisse vs Ingres 0.86 (v1 0.80–0.87);
7-class balanced accuracy 0.76–0.79 (v1 0.73–0.77). Fair Pollock test 0.97–0.999. Better centrelines → better separation,
which is what the extraction bake-off predicted. Medium confound still applies (see v1 notes and the review).

---

# Discrimination — real-v2-hybrid

σ = 0.01·ref · k = 5-fold × 3 repeats · seed 0 · 74 features in groups k, ext, infl, turn, len, end, w, cl, rel · clothoid group: ok ×216 · panel 0.23 s/drawing

Classes: matisse (31), hokusai (27), ingres (34), null_random_walk (31), null_smooth_noise (31), null_shuffled_segments (31), null_kappa_permuted (31)

## 1. Multi-class balanced accuracy (chance 0.143)

| # | model | all features | geometry only (no w_, end_) |
|---|---|---|---|
| 1 | logreg | 0.787 ± 0.047 | 0.759 ± 0.043 |
| 2 | forest | 0.811 ± 0.087 | 0.788 ± 0.072 |

Confusion (logreg, rows = true, cols = predicted):

| true \ pred | matisse | hokusai | ingres | null_random_walk | null_smooth_noise | null_shuffled_segments | null_kappa_permuted |
|---|---|---|---|---|---|---|---|
| matisse | 17 | 3 | 7 | 1 | 1 | 1 | 1 |
| hokusai | 0 | 26 | 0 | 1 | 0 | 0 | 0 |
| ingres | 3 | 0 | 29 | 1 | 0 | 1 | 0 |
| null_random_walk | 1 | 0 | 0 | 26 | 1 | 3 | 0 |
| null_smooth_noise | 1 | 0 | 1 | 2 | 21 | 5 | 1 |
| null_shuffled_segments | 0 | 3 | 2 | 3 | 4 | 19 | 0 |
| null_kappa_permuted | 2 | 0 | 0 | 0 | 0 | 0 | 29 |

Confusion (forest, rows = true, cols = predicted):

| true \ pred | matisse | hokusai | ingres | null_random_walk | null_smooth_noise | null_shuffled_segments | null_kappa_permuted |
|---|---|---|---|---|---|---|---|
| matisse | 19 | 2 | 7 | 0 | 1 | 0 | 2 |
| hokusai | 2 | 24 | 1 | 0 | 0 | 0 | 0 |
| ingres | 0 | 2 | 32 | 0 | 0 | 0 | 0 |
| null_random_walk | 0 | 0 | 0 | 29 | 0 | 2 | 0 |
| null_smooth_noise | 2 | 0 | 1 | 2 | 22 | 4 | 0 |
| null_shuffled_segments | 1 | 0 | 1 | 3 | 4 | 21 | 1 |
| null_kappa_permuted | 1 | 0 | 0 | 0 | 0 | 0 | 30 |

## 2. Pairwise separations (AUC, mean over repeats)

| # | pair | logreg AUC | forest AUC | geometry-only logreg | geometry-only forest |
|---|---|---|---|---|---|
| 1 | matisse vs null_kappa_permuted **(Pollock)** | 0.971 | 0.989 | 0.971 | 0.989 |
| 2 | matisse vs null_random_walk **(Pollock)** | 0.996 | 0.999 | 0.997 | 0.997 |
| 3 | matisse vs null_shuffled_segments **(Pollock)** | 0.992 | 0.990 | 0.998 | 0.992 |
| 4 | matisse vs null_smooth_noise **(Pollock)** | 0.971 | 0.986 | 0.978 | 0.986 |
| 5 | hokusai vs ingres | 0.980 | 0.979 | — | — |
| 6 | hokusai vs null_kappa_permuted | 0.997 | 0.998 | — | — |
| 7 | hokusai vs null_random_walk | 0.999 | 0.998 | — | — |
| 8 | hokusai vs null_shuffled_segments | 0.980 | 1.000 | — | — |
| 9 | hokusai vs null_smooth_noise | 1.000 | 0.998 | — | — |
| 10 | ingres vs null_kappa_permuted | 0.998 | 1.000 | — | — |
| 11 | ingres vs null_random_walk | 0.995 | 0.998 | — | — |
| 12 | ingres vs null_shuffled_segments | 0.958 | 0.999 | — | — |
| 13 | ingres vs null_smooth_noise | 0.990 | 0.997 | — | — |
| 14 | matisse vs hokusai | 0.925 | 0.913 | 0.799 | 0.859 |
| 15 | matisse vs ingres | 0.858 | 0.933 | 0.857 | 0.862 |
| 16 | null_random_walk vs null_kappa_permuted | 0.983 | 1.000 | — | — |
| 17 | null_random_walk vs null_shuffled_segments | 0.917 | 0.961 | — | — |
| 18 | null_random_walk vs null_smooth_noise | 0.984 | 0.989 | — | — |
| 19 | null_shuffled_segments vs null_kappa_permuted | 0.999 | 0.994 | — | — |
| 20 | null_smooth_noise vs null_kappa_permuted | 0.997 | 1.000 | — | — |
| 21 | null_smooth_noise vs null_shuffled_segments | 0.909 | 0.938 | — | — |

Fair Pollock test (excludes w, end, rel_, len_closure — nulls are open and independently placed by construction):

| # | pair | logreg AUC | forest AUC |
|---|---|---|---|
| 1 | matisse vs null_kappa_permuted | 0.971 | 0.987 |
| 2 | matisse vs null_random_walk | 0.997 | 0.999 |
| 3 | matisse vs null_shuffled_segments | 0.995 | 0.993 |
| 4 | matisse vs null_smooth_noise | 0.976 | 0.988 |

Top separating features per pair with the source (Cohen's d, b − a; medians a → b):

- **matisse vs hokusai**: `w_med` d=+1.8 (0.00144 → 0.00275); `ext_rate` d=+1.4 (13 → 16.8); `cl_len_clothoid` d=-1.1 (0.105 → 0.087); `end_thick_q50` d=+1.1 (1.1 → 1.16); `cl_corner_rate` d=+1.1 (1.53 → 2.63)
- **matisse vs ingres**: `len_q90` d=-1.5 (0.163 → 0.0695); `len_q50` d=-1.4 (0.0386 → 0.0178); `len_top_share` d=-1.3 (0.0522 → 0.0237); `cl_segs_per_stroke` d=-1.3 (1.36 → 1.18); `rel_touch_rate` d=+1.2 (0.463 → 0.651)
- **matisse vs null_random_walk**: `infl_rate` d=+2.4 (11.3 → 18.1); `ext_rate` d=+2.3 (13 → 19); `rel_cross_per_len` d=+2.3 (0.534 → 3.61); `turn_net_ratio` d=-1.9 (0.62 → 0.481); `rel_cross_per_stroke` d=+1.7 (0.0283 → 0.192)
- **matisse vs null_smooth_noise**: `rel_cross_per_len` d=+2.0 (0.534 → 3.43); `rel_cross_per_stroke` d=+1.5 (0.0283 → 0.163); `rel_selfcross_frac` d=+1.4 (0 → 0.0261); `ext_w_q50` d=+1.3 (1.69 → 2.11); `rel_cross_angle` d=-1.1 (1.17 → 0.951)
- **matisse vs null_shuffled_segments**: `rel_cross_per_len` d=+2.2 (0.534 → 3.37); `rel_cross_per_stroke` d=+1.6 (0.0283 → 0.18); `ext_spacing_cv` d=-1.1 (0.618 → 0.47); `rel_cross_angle` d=-1.0 (1.17 → 0.961); `rel_selfcross_frac` d=+1.0 (0 → 0.0239)
- **matisse vs null_kappa_permuted**: `turn_net_ratio` d=+2.5 (0.62 → 0.795); `rel_cross_per_len` d=+2.2 (0.534 → 3.06); `infl_rate` d=-2.1 (11.3 → 6.13); `infl_stroke_frac` d=-1.9 (0.739 → 0.451); `rel_cross_per_stroke` d=+1.6 (0.0283 → 0.16)

## 3. Group ablation (multi-class balanced accuracy)

| # | group | n feat | drop: logreg Δ | drop: forest Δ | alone: logreg | alone: forest |
|---|---|---|---|---|---|---|
| 1 | k_ | 8 | +0.005 | -0.001 | 0.378 | 0.462 |
| 2 | ext_ | 6 | -0.052 | -0.017 | 0.545 | 0.552 |
| 3 | infl_ | 2 | -0.014 | +0.000 | 0.503 | 0.417 |
| 4 | turn_ | 10 | -0.013 | -0.003 | 0.449 | 0.489 |
| 5 | len_ | 7 | -0.003 | -0.004 | 0.260 | 0.233 |
| 6 | end_ | 5 | +0.008 | +0.005 | 0.176 | 0.160 |
| 7 | w_ | 4 | -0.042 | -0.032 | 0.233 | 0.254 |
| 8 | cl_ | 25 | +0.024 | -0.029 | 0.391 | 0.432 |
| 9 | rel_ | 7 | -0.070 | -0.055 | 0.475 | 0.445 |

## 4. Permutation importance (forest, held-out folds; correlated features share credit)

| # | feature | Δ balanced acc | std |
|---|---|---|---|
| 1 | `rel_cross_per_len` | 0.045 | 0.027 |
| 2 | `w_med` | 0.030 | 0.024 |
| 3 | `turn_net_ratio` | 0.024 | 0.029 |
| 4 | `ext_rate` | 0.024 | 0.019 |
| 5 | `rel_selfcross_frac` | 0.023 | 0.051 |
| 6 | `w_q90_q10` | 0.013 | 0.012 |
| 7 | `ext_spacing_cv` | 0.012 | 0.021 |
| 8 | `len_ink` | 0.010 | 0.018 |
| 9 | `rel_gap_log_q50` | 0.009 | 0.014 |
| 10 | `w_cv_between` | 0.009 | 0.012 |
| 11 | `infl_stroke_frac` | 0.008 | 0.021 |
| 12 | `cl_fit_err` | 0.007 | 0.018 |
| 13 | `cl_T_arc_clothoid` | 0.006 | 0.007 |
| 14 | `rel_touch_rate` | 0.006 | 0.017 |
| 15 | `cl_T_line_arc` | 0.004 | 0.009 |

## 5. Scatter

`/Users/ianduclos/_SecondBrain/02_Areas/_Coding/idk.axibridge/.local/gesture/out/discriminate/real-v2-hybrid/scatter.png`

Times: features 11.4 s (216 drawings, 6 jobs), analysis 92.6 s.
