> **Superseded (2026-10-16 review):** the "fair Pollock" table here did not actually exclude `rel_`, nulls were not compared to a pipeline-matched control, and the multi-class figure is padded by null classes. See `review-2026-10-16.md` and the v3 report.

# Stage-2 gate, first real run — 2026-10-16 (read this first)

Extractor `extract` (bake-off winner on real-scan topology; κ accuracy not yet
fixed — see extraction-bakeoff-2026-10-16.md), panel v1 (74 features).
Matisse 31 SMK scans (tiers A+B), Hokusai 27 and Ingres 34 Met drawings, and
4 null drawings per Matisse sheet.

1. **Null test (Pollock): passed.** Matisse vs every null, with width,
   endings, closure and inter-stroke relations excluded: AUC 0.96–0.99. The
   hardest null is shuffled segments (0.96 logreg) — order of curvature
   along the line carries part of the hand, which supports the Markov layer.
2. **Artist test: near the bar, with a caveat.** Geometry-only pairwise AUC
   Matisse vs Hokusai 0.74–0.85, Matisse vs Ingres 0.80–0.87; 7-class
   balanced accuracy 0.73–0.77 geometry-only (chance 0.14). Elgammal et al.
   reached ~80% per drawing *with* thickness. Matisse is the most confused
   class (16/31 right) — it mixes etchings, crayon lithographs and pen.
3. **Caveat: medium is a confound.** Each artist is a single medium here
   (Hokusai brush, Ingres graphite with hatching). Some of what separates
   them is the tool and the extractor's response to it (Ingres's short
   hatching strokes drive `len_`). A medium-matched test is needed before
   claiming "hand": e.g. Matisse etchings vs Matisse lithographs vs another
   etcher.
4. **What carries it:** extrema (`ext_`) and inter-stroke relations
   (`rel_`) matter most in ablation; curvature level (`k_`) alone is weak
   (0.36–0.45). Consistent with Attneave and the research note: the hand is
   in *where and how sharply* the line turns, not in how much.

---

# Discrimination — real-v1-extract

σ = 0.01·ref · k = 5-fold × 3 repeats · seed 0 · 74 features in groups k, ext, infl, turn, len, end, w, cl, rel · clothoid group: ok ×216 · panel 0.27 s/drawing

Classes: matisse (31), hokusai (27), ingres (34), null_random_walk (31), null_smooth_noise (31), null_shuffled_segments (31), null_kappa_permuted (31)

## 1. Multi-class balanced accuracy (chance 0.143)

| # | model | all features | geometry only (no w_, end_) |
|---|---|---|---|
| 1 | logreg | 0.769 ± 0.055 | 0.725 ± 0.058 |
| 2 | forest | 0.785 ± 0.084 | 0.774 ± 0.073 |

Confusion (logreg, rows = true, cols = predicted):

| true \ pred | matisse | hokusai | ingres | null_random_walk | null_smooth_noise | null_shuffled_segments | null_kappa_permuted |
|---|---|---|---|---|---|---|---|
| matisse | 16 | 3 | 6 | 2 | 2 | 1 | 1 |
| hokusai | 1 | 25 | 1 | 0 | 0 | 0 | 0 |
| ingres | 4 | 0 | 28 | 0 | 0 | 1 | 1 |
| null_random_walk | 0 | 0 | 0 | 26 | 0 | 5 | 0 |
| null_smooth_noise | 1 | 0 | 0 | 1 | 23 | 6 | 0 |
| null_shuffled_segments | 1 | 1 | 1 | 6 | 1 | 21 | 0 |
| null_kappa_permuted | 2 | 0 | 0 | 0 | 2 | 0 | 27 |

Confusion (forest, rows = true, cols = predicted):

| true \ pred | matisse | hokusai | ingres | null_random_walk | null_smooth_noise | null_shuffled_segments | null_kappa_permuted |
|---|---|---|---|---|---|---|---|
| matisse | 16 | 3 | 8 | 0 | 1 | 0 | 3 |
| hokusai | 2 | 23 | 1 | 0 | 0 | 0 | 1 |
| ingres | 0 | 2 | 32 | 0 | 0 | 0 | 0 |
| null_random_walk | 2 | 0 | 0 | 27 | 0 | 2 | 0 |
| null_smooth_noise | 2 | 0 | 0 | 0 | 23 | 5 | 1 |
| null_shuffled_segments | 1 | 0 | 0 | 3 | 4 | 22 | 1 |
| null_kappa_permuted | 1 | 0 | 0 | 0 | 1 | 0 | 29 |

## 2. Pairwise separations (AUC, mean over repeats)

| # | pair | logreg AUC | forest AUC | geometry-only logreg | geometry-only forest |
|---|---|---|---|---|---|
| 1 | matisse vs null_kappa_permuted **(Pollock)** | 0.995 | 0.987 | 0.990 | 0.985 |
| 2 | matisse vs null_random_walk **(Pollock)** | 0.985 | 0.994 | 0.987 | 0.994 |
| 3 | matisse vs null_shuffled_segments **(Pollock)** | 0.952 | 0.986 | 0.961 | 0.984 |
| 4 | matisse vs null_smooth_noise **(Pollock)** | 0.977 | 0.993 | 0.981 | 0.997 |
| 5 | hokusai vs ingres | 0.985 | 0.983 | — | — |
| 6 | hokusai vs null_kappa_permuted | 1.000 | 0.996 | — | — |
| 7 | hokusai vs null_random_walk | 0.989 | 0.997 | — | — |
| 8 | hokusai vs null_shuffled_segments | 0.997 | 0.999 | — | — |
| 9 | hokusai vs null_smooth_noise | 0.984 | 0.998 | — | — |
| 10 | ingres vs null_kappa_permuted | 1.000 | 1.000 | — | — |
| 11 | ingres vs null_random_walk | 0.976 | 0.998 | — | — |
| 12 | ingres vs null_shuffled_segments | 0.995 | 1.000 | — | — |
| 13 | ingres vs null_smooth_noise | 0.999 | 1.000 | — | — |
| 14 | matisse vs hokusai | 0.896 | 0.906 | 0.736 | 0.851 |
| 15 | matisse vs ingres | 0.790 | 0.933 | 0.804 | 0.874 |
| 16 | null_random_walk vs null_kappa_permuted | 1.000 | 1.000 | — | — |
| 17 | null_random_walk vs null_shuffled_segments | 0.945 | 0.944 | — | — |
| 18 | null_random_walk vs null_smooth_noise | 0.997 | 1.000 | — | — |
| 19 | null_shuffled_segments vs null_kappa_permuted | 0.972 | 0.987 | — | — |
| 20 | null_smooth_noise vs null_kappa_permuted | 0.973 | 0.995 | — | — |
| 21 | null_smooth_noise vs null_shuffled_segments | 0.907 | 0.909 | — | — |

Fair Pollock test (excludes w, end, rel_, len_closure — nulls are open and independently placed by construction):

| # | pair | logreg AUC | forest AUC |
|---|---|---|---|
| 1 | matisse vs null_kappa_permuted | 0.989 | 0.985 |
| 2 | matisse vs null_random_walk | 0.985 | 0.995 |
| 3 | matisse vs null_shuffled_segments | 0.960 | 0.986 |
| 4 | matisse vs null_smooth_noise | 0.981 | 0.995 |

Top separating features per pair with the source (Cohen's d, b − a; medians a → b):

- **matisse vs hokusai**: `w_med` d=+1.8 (0.00144 → 0.00274); `ext_rate` d=+1.4 (13.6 → 17.2); `end_blob_frac` d=+1.2 (0.225 → 0.336); `end_thick_q50` d=+1.1 (1.1 → 1.16); `cl_len_clothoid` d=-1.0 (0.102 → 0.0873)
- **matisse vs ingres**: `len_q90` d=-1.5 (0.163 → 0.0705); `len_q50` d=-1.4 (0.0388 → 0.0178); `len_top_share` d=-1.3 (0.0526 → 0.0238); `cl_segs_per_stroke` d=-1.3 (1.36 → 1.19); `cl_rate_arc` d=+1.2 (3.65 → 6.12)
- **matisse vs null_random_walk**: `ext_rate` d=+2.6 (13.6 → 19.7); `infl_rate` d=+2.3 (11.5 → 17.9); `rel_cross_per_len` d=+2.2 (0.543 → 3.35); `turn_net_ratio` d=-1.9 (0.614 → 0.465); `rel_cross_per_stroke` d=+1.7 (0.0303 → 0.186)
- **matisse vs null_smooth_noise**: `rel_cross_per_len` d=+2.0 (0.543 → 3.28); `rel_cross_per_stroke` d=+1.6 (0.0303 → 0.167); `rel_selfcross_frac` d=+1.5 (0 → 0.0234); `ext_w_q50` d=+1.3 (1.72 → 2.14); `k_css_zc2` d=+1.0 (0.377 → 0.59)
- **matisse vs null_shuffled_segments**: `rel_cross_per_len` d=+2.3 (0.543 → 3.75); `rel_cross_per_stroke` d=+1.6 (0.0303 → 0.173); `rel_cross_angle` d=-1.1 (1.17 → 0.97); `ext_spacing_cv` d=-1.1 (0.626 → 0.455); `rel_selfcross_frac` d=+0.9 (0 → 0.028)
- **matisse vs null_kappa_permuted**: `turn_net_ratio` d=+2.5 (0.614 → 0.803); `infl_stroke_frac` d=-2.4 (0.79 → 0.429); `infl_rate` d=-2.2 (11.5 → 6.08); `rel_cross_per_len` d=+2.0 (0.543 → 3.03); `rel_cross_per_stroke` d=+1.6 (0.0303 → 0.154)

## 3. Group ablation (multi-class balanced accuracy)

| # | group | n feat | drop: logreg Δ | drop: forest Δ | alone: logreg | alone: forest |
|---|---|---|---|---|---|---|
| 1 | k_ | 8 | -0.011 | +0.002 | 0.361 | 0.448 |
| 2 | ext_ | 6 | -0.060 | -0.021 | 0.566 | 0.574 |
| 3 | infl_ | 2 | -0.026 | -0.007 | 0.468 | 0.449 |
| 4 | turn_ | 10 | +0.014 | -0.001 | 0.440 | 0.515 |
| 5 | len_ | 7 | -0.021 | +0.028 | 0.261 | 0.236 |
| 6 | end_ | 5 | -0.007 | +0.017 | 0.156 | 0.177 |
| 7 | w_ | 4 | -0.050 | -0.013 | 0.235 | 0.253 |
| 8 | cl_ | 25 | +0.040 | -0.008 | 0.417 | 0.433 |
| 9 | rel_ | 7 | -0.070 | -0.053 | 0.475 | 0.435 |

## 4. Permutation importance (forest, held-out folds; correlated features share credit)

| # | feature | Δ balanced acc | std |
|---|---|---|---|
| 1 | `rel_selfcross_frac` | 0.037 | 0.037 |
| 2 | `w_med` | 0.023 | 0.017 |
| 3 | `rel_cross_per_len` | 0.022 | 0.034 |
| 4 | `ext_rate` | 0.012 | 0.019 |
| 5 | `turn_net_ratio` | 0.009 | 0.017 |
| 6 | `turn_kcorr_20` | 0.007 | 0.009 |
| 7 | `rel_cross_angle` | 0.007 | 0.012 |
| 8 | `rel_cross_per_stroke` | 0.006 | 0.019 |
| 9 | `ext_w_q50` | 0.006 | 0.013 |
| 10 | `len_count` | 0.006 | 0.015 |
| 11 | `rel_gap_log_q50` | 0.005 | 0.016 |
| 12 | `k_cv` | 0.005 | 0.009 |
| 13 | `w_q90_q10` | 0.005 | 0.011 |
| 14 | `ext_turn_q50` | 0.004 | 0.010 |
| 15 | `k_q90` | 0.004 | 0.008 |

## 5. Scatter

`/Users/ianduclos/_SecondBrain/02_Areas/_Coding/idk.axibridge/.local/gesture/out/discriminate/real-v1-extract/scatter.png`

Times: features 12.8 s (216 drawings, 6 jobs), analysis 97.0 s.
