# Kinematic hand: sigma-lognormal pulses vs clothoid grammar v3 (2026-10-16)

Files: `gesture/lognormal.py`, `experiments/lognormal_study.py`, `tests/test_lognormal.py`.
Raw outputs: `.local/gesture/out/lognormal/{synth,signature,test1,memo}.md`, `fits/`, `hand_*.json`,
`sheets/`. Sheets: `lognormal-matisse.jpg`, `lognormal-hokusai.jpg`.

**Verdict.** The kinematic representation itself is adequate: refitted real
strokes are indistinguishable from the originals on the panel. But
**generation from it does not beat clothoid v3 on stage-3 test 1**. Logreg / forest
AUC is 0.96 / 0.96 for Matisse (v3 0.91 / 0.91), 0.75 / 0.90 for Hokusai
(v3 0.82 / 0.84) and 0.95 / 0.93 for Ingres (v3 0.91 / 0.93).

It does fix part of the along-line texture:
- Curvature extrema now match real in height and turn, where v3's were about 2× too sharp.
- Matisse's tangent correlation moves most of the way back to real.

The corner rate is still about 1.8× real (v3: about 2×). The jaggedness is reduced, not
solved.

## Method

- **Model.** The model follows Plamondon's sigma-lognormal formulation. Each pulse has
  six parameters: (t0, μ, σ, D, θs, θe).
  - Its speed is D times the lognormal pdf.
  - Its direction rotates linearly with its own progress, so a lone pulse draws a
    circular arc.
  - Velocity is the sum over pulses. Synthesis integrates it by cumulative trapezoid
    on a time grid fine enough for every pulse.
- **Timing from a static trace.** Scans have no timing, so the stroke is smoothed at
  σ = 2 line widths (the grammar's scale). Speed is then set by the 2/3 power law,
  v ∝ (|κ|R + 2)^(−1/3), with a start/end ramp, and time is integrated from it.
  Speed minima then fall on curvature maxima. These are the landmarks of Berio,
  Leymarie & Plamondon, *Kinematics Reconstruction of Static Calligraphic Traces from
  Curvilinear Shape Features* (Lognormality Principle book chapter).
- **Fit.**
  1. One pulse per speed-peak segment between landmarks.
  2. Levenberg–Marquardt on velocity plus integrated position, with an analytic
     Jacobian. σ is sigmoid-bounded to [0.08, 0.7]. A ΣD ≈ path-length penalty stops
     pulses from cancelling each other.
  3. Up to 4 rounds, each adding up to 3 pulses at residual peaks, while the velocity
     SNR is below 20 dB.
  4. At most 12 randomly chosen long strokes per drawing were fitted, using
     `grammar_v3_frozen.long_drawing` (CPU budget on a shared machine). That gives
     370 Matisse, 308 Hokusai and 402 Ingres strokes.
- **Hand.**
  - Each pulse is reduced to a rotation- and time-scale-free row
    `[log D/R, Δθ, σ, onset delay ÷ previous duration, log(T / stroke median T), jump θs − prev θe]`.
  - The sequence model is an order-2 k-NN chain: the context is the previous row, the
    previous Δθ and jump, and u = s/L; K = 10, with 5 % jitter.
  - An earlier version chained log T as a ratio. It random-walked in time scale, and
    proposal windows exploded, so the stationary form replaced it.
- **Generation.** Lines grow pulse by pulse. `_Line` re-integrates only after the new
  pulse's onset. At each step there are 8 proposals, and the first feasible one in draw
  order is kept: on the sheet, clear of ink, crossings under the learned budget,
  preferring those with a clear look-ahead ray. This is the same rejection-steering
  rule as v3, so the comparison isolates the representation.
  - Layout uses v3's learned relations: attach share, angle, free-start gaps and
    crossing rate.
  - `mode="single"` is one line with backtracking of 1–4 pulses and a widened search
    when stuck.

## Fit quality

**Synthetic, known pulses** (12 strokes per row):

| # | true n | mode | fitted n | exact | ±1 | SNR dB | D rel err | Δθ err | shape err ÷ L |
|---|---|---|---|---|---|---|---|---|---|
| S1 | 1 | timed | 1 | 1.00 | 1.00 | 74 | 0.00 | 0.00 | — |
| S2 | 1 | static | 3 | 0 | 0 | 25 | 0.84 | 0.41 | 0.0008 |
| S3 | 2 | timed | 2 | 0.75 | 0.92 | 47 | 0.00 | 0.00 | — |
| S4 | 2 | static | 7 | 0 | 0 | 22 | 0.78 | 0.54 | 0.0006 |
| S5 | 4 | timed | 6 | 0.25 | 0.50 | 22 | 0.40 | 0.61 | — |
| S6 | 4 | static | 10 | 0 | 0 | 22 | 0.62 | 0.67 | 0.0003 |
| S7 | 8 | timed | 3 | 0.08 | 0.17 | 7 | 1.65 | 0.78 | — |
| S8 | 8 | static | 18 | 0 | 0 | 21 | 0.67 | 0.81 | 0.0006 |

1. **Static fits reproduce geometry but do not recover the true pulses.** Shape error
   is under 0.1 % of length. But the pulse count comes out 2–3× too high, because
   power-law timing is not lognormal timing, and the extra pulses absorb the mismatch.
2. **Even with the true timing, recovery fails beyond about 4 heavily overlapping
   pulses**: the landmark initialisation misses them, and 8 pulses ended at 7 dB.
3. **Consequence:** the pulse parameters from scans are a *consistent description* —
   one pipeline, compared across artists — not the artist's real motor kinematics.

**Real long strokes:** the median velocity SNR is 22.4–22.9 dB, and 100 % of strokes
are ≥ 20 dB by construction. Mean shape error is 0.05 line widths (q90 0.15 w), about
0.08 % of stroke length.

## Per-artist kinematic signatures

| # | descriptor | Matisse | Hokusai | Ingres |
|---|---|---|---|---|
| K1 | pulses per 100 line widths | 8.7 | 10.0 | 11.7 |
| K2 | pulses per stroke (median) | 8 | 7 | 7 |
| K3 | D/R per pulse (median) | 0.013 | 0.023 | 0.011 |
| K4 | abs(Δθ) per pulse, median / q90 (rad) | 0.21 / 1.26 | 0.36 / 1.76 | 0.26 / 1.42 |
| K5 | σ (median) | 0.30 | 0.26 | 0.29 |
| K6 | onset delay ÷ previous duration (median; lower = more overlap) | 0.25 | 0.29 | 0.27 |
| K7 | abs(jump) between pulses (median, rad) | 0.29 | 0.61 | 0.43 |

The per-drawing IQRs show that K4 and K7 separate Matisse from Hokusai almost
without overlap. For abs(jump), Matisse is 0.22–0.41 and Hokusai 0.44–0.87; for
abs(Δθ), Matisse is 0.16–0.29 and Hokusai 0.27–0.48. Pulses per 100 w separates
Ingres (10.7–13.2) from Matisse (7.9–10.2).

Reading:
- **Matisse:** few, smooth, gently curving pulses with small re-aims.
- **Hokusai:** each pulse curves more and re-aims more abruptly.
- **Ingres:** more, shorter pulses per unit of line width.

All pulses overlap heavily (87 % start before the previous pulse ends), so overlap does
not discriminate. Caveat: the absolute numbers depend on the 20 dB target and the
power-law assumption (§ fit quality).

## Stage-3 test 1 vs grammar v3

Setup:
- Same protocol as `grammar-v3.md`: real long-stroke subsets against the same number
  of generated drawings on the same canvases.
- Standard preprocessing, geometry only, grouped 5-fold × 5.
- v3 was generated from the frozen module and the saved v3 grammars, copied to
  `.local/gesture/out/lognormal/v3_grammars/` before anyone could overwrite them.
- **recon** compares real drawings restricted to the fitted strokes against the same
  strokes resynthesised from their pulses.

| # | artist | generator | geometry: logreg / forest | no rel_ | texture only |
|---|---|---|---|---|---|
| A1 | matisse | lognormal | .956 / .961 | .928 / .963 | .904 / .940 |
| A2 | matisse | v3 | .909 / .912 | .893 / .921 | .889 / .902 |
| A3 | matisse | recon | .26 / .07 | .27 / .06 | .44 / .14 |
| A4 | hokusai | lognormal | .754 / .901 | .771 / .892 | .730 / .829 |
| A5 | hokusai | v3 | .823 / .843 | .803 / .833 | .666 / .733 |
| A6 | hokusai | recon | .32 / .09 | .35 / .12 | .46 / .33 |
| A7 | ingres | lognormal | .948 / .932 | .894 / .901 | .886 / .848 |
| A8 | ingres | v3 | .909 / .930 | .923 / .930 | .866 / .916 |
| A9 | ingres | recon | .40 / .10 | .40 / .11 | .51 / .20 |

The recon AUCs are below 0.5. That is an artefact: each recon drawing and its
real twin are near-duplicates that the CV puts in different folds, so the classifier
anti-learns. It should be read as "indistinguishable". It should have been grouped by
pair; fix that before reusing the result. **The representation therefore loses
nothing the panel can see. The tell comes from the chain and the layout, not from the
fit.**

**Along-line texture (medians):**

| # | artist | set | corner rate | tcorr_05 | tcorr_10 | ext_turn_q50 | ext_h_q50 | infl_rate |
|---|---|---|---|---|---|---|---|---|
| T1 | matisse | real | 1.50 | .83 | .71 | .41 | 15.7 | 9.9 |
| T2 | matisse | lognormal | 2.75 | .81 | .65 | .37 | 15.8 | 12.3 |
| T3 | matisse | v3 | 3.18 | .70 | .46 | .68 | 30.7 | 11.3 |
| T4 | hokusai | real | 1.32 | .72 | .46 | .78 | 25.7 | 5.5 |
| T5 | hokusai | lognormal | 1.71 | .72 | .47 | .78 | 20.8 | 6.1 |
| T6 | hokusai | v3 | 1.55 | .70 | .47 | 1.03 | 26.5 | 6.0 |
| T7 | ingres | real | 1.61 | .82 | .73 | .34 | 18.0 | 12.9 |
| T8 | ingres | lognormal | 2.79 | .70 | .50 | .41 | 20.6 | 15.0 |
| T9 | ingres | v3 | 2.64 | .67 | .42 | .63 | 31.6 | 11.0 |

Reading:

1. **Fixed:**
   - The sharpness of curvature extrema (ext_turn, ext_h) is now at real for all
     three, against about 2× in v3. Overlapping pulses round every turn.
   - Matisse's tangent correlation at lag 0.10 is 0.65 against a real 0.71 (v3 0.46).
2. **Not fixed:**
   - Corner rate stays 1.8× real for Matisse and Ingres.
   - Ingres still wanders: tcorr_10 is 0.50 against a real 0.73.
   - Inflections are 20–25 % too frequent.
   - Lognormal adds a new tell: small self-crossings (`rel_selfcross_frac` +1.6 d for
     Ingres, +0.9 for Hokusai). Tiny hooks at line starts and at low-overlap/large-jump
     junctions close on themselves inside the self-avoidance lag.
3. **Top d for lognormal.** `cl_corner_rate`, `cl_fit_err` (the clothoid fitter fits
   lognormal lines worse than real ones) and `infl_stroke_frac` for Matisse.
   `turn_net_ratio` −1.4 for Hokusai: generated lines turn back on themselves less.
4. **Open: chain or steering?** The extra corners come from the chain's pulse-to-pulse
   junctions or from steering selection; this run did not separate the two. The free-stroke
   ablation I tried used the wrong scale and was discarded. It is the obvious next
   measurement.

## Memorisation

Distance is the turning signature, computed on the polylines. Held-out drawings are
every 5th one, the hand is trained on the rest, and real strokes are compared as their
lognormal reconstructions.

| # | artist | generated median (share < held-out q10) | held-out real | shuffled-pulse control | jittered copies (quote floor) |
|---|---|---|---|---|---|
| M1 | matisse | .171 (.04) | .162 (.11) | .221 (.05) | .034 (.79) |
| M2 | hokusai | .314 (.09) | .260 (.10) | .369 (.05) | .042 (.84) |
| M3 | ingres | .179 (.07) | .177 (.11) | .260 (.06) | .034 (.81) |

1. Generated strokes sit at held-out distance and far above the quote floor: no
   quoting. That includes Hokusai, whose v3 tail was too close (19 %); here it is 9 %.
2. The shuffled-pulse control is farther from the training strokes than generated
   strokes, so pulse order carries the hand.

## The sheets, honestly

Per artist: 6 contiguous drawings, 3 single lines, 2 v3, 1 real long-stroke subset.

1. **Contiguous, Matisse.**
   - Long, calm lines; nothing reads as hatching.
   - Line quality is visibly smoother than v3, which has many small curls and hooks.
   - But the sheets read as **crumpled paper or a cracked surface**: many medium-length
     straight-ish runs meeting at shallow kinks, dense and evenly spread. They are less
     figure-like than v3's nested curves, and nowhere near the real sheet (a
     reclining figure).
   - One sheet (15 R of ink) is overfull.
2. **Contiguous, Hokusai.**
   - Rounder, blobbier lines with loops; the closest to its hand.
   - Low-ink samples are sparse (2–4 lines).
3. **Contiguous, Ingres.**
   - Too many short choppy strokes in clusters.
   - The real long-stroke subset is itself near-vertical hatch-like contour, which the
     model does not attempt.
4. **Single line — the best output.**
   - One continuous line of 3–9 R in big winding loops.
   - Matisse: broad rectangles-ish enclosures with doubled parallel passes where the
     line runs back alongside itself at the clearance distance — an Oehlen-like
     "contour doubling" that is quite good.
   - Hokusai: lobed and blobby.
   - Ingres: a long wander with a tight knot at one end.
   - Awkward spots: small notches and zig-zags where a short, low-overlap pulse
     re-aims, and a few self-crossings once backtracking runs out.
5. Nothing has been plotted. Ready for Ian to look at.

## Should lognormal features join the panel?

**Not yet — as a candidate group (`kin_`), after two fixes.** K4 and K7 are
interpretable, and per drawing they separate Matisse from Hokusai about as well as the
best `turn_` features. But two problems come first:

1. They are a description conditioned on an assumed timing model and an SNR target,
   not a measurement.
2. Fitting costs about 1 s per stroke.

**Fixes before trying:**
- Make the count SNR-independent (e.g. pulses at a fixed geometric error ÷ w).
- Run the medium-invariance check (etching vs litho), as every new group must.

**Test:** whether adding the group to the panel raises artist AUC above 0.81 / 0.79.

## Weaknesses

1. **Pulse identifiability.** Static fits inflate the pulse count 2–3×. Timed fits
   fail beyond about 4 overlapping pulses (single landmark start, one prominence; more
   starts cost CPU).
2. **Stroke subset.** Only 12 random long strokes per drawing were fitted, so the
   hands see about 1/3 of v3's training strokes.
3. **Degenerate pulses.** One stroke had a degenerate T → 0 pulse. Such strokes are
   filtered in `learn`, `signature` and the recon, not fixed in the fitter.
4. **Starts and hooks.** Generated lines often start with a tiny hook: the first pulse
   is sampled from training first pulses, which absorb the ramp artefact of the timing
   model.
5. **Shared layout.** Layout and steering are v3's. Steering selection bias may
   explain the remaining corner excess for both models.
6. **Test conditions.** Tests take about 16 s under a load average above 100; that
   should be under 15 s on an idle machine, but it was not measured idle.

## Next

1. Separate chain from steering. Run panel texture on free chain strokes (no sheet) at
   the same R and width as the real ones; the attempt this run used the wrong scale.
2. Condition the first pulse on not starting with a hook, and penalise low-overlap
   large-jump junctions. Or resample `dt` jointly with `jump` from the real joint
   distribution instead of row-wise k-NN plus jitter.
3. Code-switching is natural here: swap the hand's chain at a pulse boundary, and
   overlap blends the join for free.

## Commands

```bash
cd tools/gesture
../../.local/gesture/.venv/bin/python -m experiments.lognormal_study synth --n 12
../../.local/gesture/.venv/bin/python -m experiments.lognormal_study fit      # ~3 min, cached
../../.local/gesture/.venv/bin/python -m experiments.lognormal_study test1    # ~8 min
../../.local/gesture/.venv/bin/python -m experiments.lognormal_study memo --n 300
../../.local/gesture/.venv/bin/python -m experiments.lognormal_study sheets
```

Set `OMP_NUM_THREADS=1`; `LN_JOBS` sets the number of worker processes.
