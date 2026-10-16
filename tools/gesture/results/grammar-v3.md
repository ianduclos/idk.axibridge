# Grammar v3: steered growth, learned relations, calibrated crossings (2026-10-16)

This round closes the stage-3 test-1 gaps that `grammar-v2.md` §4 found.
Files: `gesture/grammar.py`, `experiments/grammar_eval.py` (new `calibrate` and
`--baseline`), `experiments/generate_demo.py`.
Raw outputs: `.local/gesture/out/grammar_v2/{test1.md,test1_key.md,memo.md,cross_gain.json,demo_v3/}`.
Sheets: `grammar-v3-matisse.jpg`, `grammar-v3-hokusai.jpg`, `grammar-v3-juxtaposition.jpg`.
v2 numbers are re-measured in the same run: the committed v2 module was loaded
with `--baseline`, on the same seeds and canvases.

**Verdict:** for the learned-relations variant, test 1 improved by about 0.04–0.15 AUC. It is
now 0.92 for Matisse, 0.81 for Hokusai and 0.93 for Ingres (logreg). It is still
far from 0.5. Stroke lengths, touching and gaps are now close to the real
subsets. What separates real from generated is now **line texture**: corners
are twice as frequent, and tangent correlation along the line is lower.

## What changed

1. **Lines are grown, not cut** (`_Grower`). Each line gets a planned length,
   drawn from the long-stroke distribution. The line grows one token at a time:
   - The chain proposes K = 8 continuations from the same context.
   - Each continuation is integrated from the pen position.
   - The **first proposal in draw order** that stays on the sheet and clear of other
     ink and of the line itself is kept. Among those, a proposal that also has a clear
     look-ahead ray is preferred; the ray runs along the end tangent for about one
     median segment length.
   - This is rejection sampling. The chain's own proposal stands unless it is
     blocked, and any turn comes from a turning segment or corner that the chain
     itself proposed.
   - Nothing is inserted, so the v2 single-mode V-turns are gone.
   - A line stops early only when every proposal is blocked: 0–3 lines per drawing.
2. **Single mode** grows chunk by chunk with the same steering. When it is boxed in,
   it backtracks one chunk and regrows (up to 12 times).
3. **Relations follow the learned rates.** The default is now `relations="learned"`;
   `"tree"` stays available as an option.
   - A line attaches at its start with probability 2 × the learned share of
     attached ends. It then continues from a free end or branches at a learned
     position u and angle.
   - Every other line starts free, at a gap from existing ink. The gap is drawn
     from the learned gaps of the unattached real ends (new `relations.gap`).
4. **Crossings.**
   - The target is the per-drawing median `rel_cross_per_len` of the real subsets,
     not the ink-pooled rate.
   - The branch start zone now ignores only the host line. In v2 it hid crossings
     of other lines.
   - A per-hand gain is tuned by `grammar_eval calibrate`: 3 rounds of 12
     drawings. Result: Matisse 1.02, Hokusai 0.33 (clipped), Ingres 1.27.
5. **R convention.** R = 0.95 × the margin-box diagonal, about the ink's own
   bounding box. In v2, 0.85 × the canvas diagonal undershot it, so every length
   measured short by about 12 %.

## Key features: medians, real vs v2 vs v3

| # | artist | set | len_q10 | len_q50 | rel_touch | rel_near | rel_gap (log) | X / len | self-X | segs / stroke | corners / len |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F1 | matisse | **real** | .065 | .124 | .15 | .74 | −1.75 | .24 | 0 | 1.42 | 1.5 |
| F2 | matisse | v2 learned | .039 | .089 | .28 | .54 | −1.57 | .50 | 0 | 1.39 | 1.9 |
| F3 | matisse | v2 tree | .040 | .084 | .73 | .92 | −3.18 | .46 | 0 | 1.44 | 2.1 |
| F4 | matisse | **v3 learned** | .046 | .112 | .26 | .81 | −1.90 | .37 | 0 | 1.71 | **3.2** |
| F5 | matisse | v3 tree | .048 | .110 | .63 | .89 | −3.05 | .25 | 0 | 1.76 | 2.7 |
| F6 | hokusai | **real** | .114 | .184 | .21 | .67 | −1.68 | .27 | 0 | 1.41 | 1.3 |
| F7 | hokusai | v2 learned | .056 | .116 | .39 | .61 | −1.82 | .60 | 0 | 1.31 | 1.9 |
| F8 | hokusai | v2 tree | .061 | .126 | .67 | .88 | −3.07 | 1.04 | 0 | 1.25 | 1.1 |
| F9 | hokusai | **v3 learned** | .079 | .155 | .38 | .73 | −1.89 | .33 | 0 | 1.43 | 1.6 |
| F10 | hokusai | v3 tree | .078 | .161 | .59 | .82 | −3.02 | .40 | 0 | 1.41 | 1.5 |
| F11 | ingres | **real** | .056 | .085 | .15 | .60 | −1.66 | .20 | 0 | 1.28 | 1.6 |
| F12 | ingres | v2 learned | .036 | .065 | .20 | .40 | −1.40 | .26 | 0 | 1.31 | 1.9 |
| F13 | ingres | v2 tree | .041 | .078 | .71 | .89 | −3.13 | .41 | 0 | 1.28 | 1.8 |
| F14 | ingres | **v3 learned** | .050 | .091 | .18 | .74 | −1.75 | .24 | 0 | 1.42 | **2.6** |
| F15 | ingres | v3 tree | .055 | .095 | .63 | .85 | −3.07 | .28 | 0 | 1.46 | 2.4 |

Reading:

1. **Length is mostly fixed.** len_q50 is now 0.84–1.07 × real, against 0.63–0.76 × in
   v2. len_q10 is still short (0.70–0.90 × real), because the shortest accepted lines
   are the steered-but-blocked ones.
2. **Touching, near and gap now sit close to real for Matisse and Ingres.** Hokusai
   still touches at 1.8 × real, because its learned attach share is the highest
   (0.44).
3. **Crossings.**
   - Hokusai went from 2.3 × real to 1.2 × real, and Ingres is 1.2 × real.
   - **Matisse went up to 1.6 × real** after calibration. At gain 1 the
     uncalibrated run measured 0.24, which matched. The 12-drawing calibration is
     noisy, and its multiplicative update overshot.
   - The self-crossing median is 0 everywhere, matching real.
4. **New gap: corners.** Corners per length are 2.1 × real for Matisse and 1.6 × for
   Ingres. Segments per stroke rose too. Even first-feasible selection still favours
   corner+segment proposals near obstacles. The chain's corners are also
   instantaneous, so all of them pass the panel's 35° test at 7 w, while the real ones
   are rounded.

## Stage-3 test 1 (fair comparison)

Real drawings are restricted to the same long-stroke subset. Standard preprocessing,
geometry-only features, grouped 5-fold CV × 5 repeats. Each cell gives logreg / forest AUC.

| # | artist | v2 learned | **v3 learned** | v3 learned, no `rel_` | v2 tree | v3 tree | v3 tree, no `rel_` |
|---|---|---|---|---|---|---|---|
| A1 | matisse | .969 / .974 | **.917 / .920** | .907 / .920 | .995 / 1.0 | 1.0 / 1.0 | .980 / .954 |
| A2 | hokusai | .957 / .921 | **.807 / .859** | .781 / .829 | .998 / .993 | .981 / .997 | .906 / .943 |
| A3 | ingres | .993 / .991 | **.930 / .928** | .945 / .936 | 1.0 / 1.0 | 1.0 / 1.0 | .985 / .986 |

Top separating features for v3 learned (Cohen's d, generated − real). This is the to-do list:

1. **Matisse:**
   - `cl_corner_rate` +1.8.
   - `turn_tcorr_10` −1.5: the tangent decorrelates faster along the line, so lines
     wander more.
   - `cl_rate_line` +1.4.
   - `cl_segs_per_stroke` +1.2.
   - `len_q10` −1.0.
2. **Hokusai:**
   - `rel_touch_rate` +1.2.
   - `turn_net_ratio` −1.1: generated lines turn back on themselves more.
   - `len_q10` −1.0.
3. **Ingres:**
   - `ext_turn_q50` +1.6 and `ext_h_q50` +1.2: curvature extrema are sharper.
   - `turn_tcorr_05` −1.2.
   - `cl_corner_rate` +1.1.

All three come from the same source: texture along a single line, made at joints
and corners, not composition. The two likely causes:

- **Selection bias:** steering prefers turning proposals near obstacles.
- **Splices:** the order-2 k-NN joins tokens from different strokes, which adds κ
  spikes and corners that whole real strokes don't have.

## Memorisation: unchanged from v2, as expected

The chain did not change in v3; only the layout around it did. The memo run therefore
reproduces `grammar-v2.md` §5 exactly. Median nearest-neighbour distance on strokes
with ≥ 4 segments:

| artist | generated | held-out real | shuffled control | jittered copies (quote floor) |
|---|---|---|---|---|
| Matisse | .306 | .322 | .390 | .082 |
| Hokusai | .423 | .423 | .448 | .166 |
| Ingres | .364 | .347 | .428 | .122 |

So the chain speaks the hand without quoting it. Hokusai's lower tail is still too
close: 19 % of its generated strokes fall below the held-out 10th percentile, against
10 % expected.

## The sheets, honestly

1. **Contiguous mode (learned relations).** Lines are long and winding. They now
   start near other lines at real-looking gaps, so they read as fragments of a figure
   drawing: nested parallel curves, lines that nearly meet. They no longer read as
   tree networks. Nothing reads as hatching.
   - Matisse has calm long arcs with occasional kinks.
   - Hokusai has curls and small hooks.
   - Duds: some sheets with a low sampled ink budget are sparse. One Matisse sheet
     (10 R of ink) is dense and tangled.
   - Compared with v2's tree mode, this is less "Oehlen tree" and more
     "the real drawing's line field". `relations="tree"` is still there when Ian
     wants trees.
2. **Single mode** is the clearest gain. It draws one long continuous line with no
   inserted V-turns. It loops, nests and fills the sheet in the hand's own curves.
   The Hokusai lines are mazy and curly, the Matisse lines broad and slow. One
   Matisse line stalled early at 2.1 R.
3. **Juxtaposition.**
   - The alternating-hand lines visibly change character at each switch.
   - Two of the three panels stalled early: when the hand switches at a joint,
     boxed-in backtracking happens less, which may explain it.
   - Restyling a Matisse structure in Hokusai's hand works as before. Translation
     still drops the relations between lines.

Ready for Ian to look at. Nothing has been plotted.

## Remaining gaps and next steps

1. **Corner and texture excess** (§ key features, items 4 and test-1 lists):
   - Weight the steering choice by the chain's own corner rate. One way: reject a
     corner proposal unless the plain proposals are all blocked.
   - Render corners as short tight clothoids at the extraction's rounding scale, so
     that the panel sees the same corners on generated and real lines.
2. **Splice texture:** add a κ-continuity and κ-jump penalty on the k-NN join, set to
   the training distribution of joint κ jumps. Scale KNN with pool size; that also
   addresses the Hokusai quoting tail.
3. **Crossing calibration:** use more drawings (≥ 30), a damped update and a final
   check. The Matisse gain overshot.
4. **Hokusai touch:** the learned attach share (0.44) gives 1.8 × the real
   `rel_touch`. The attachment model should condition on whether an end attaches at
   start or end. Right now generated lines attach only at their start.
5. **len_q10:** retry blocked lines with a fresh start before accepting a short one.
6. **Code-switching single lines** stall more often than single-hand ones.

## Commands

```bash
cd tools/gesture
../../.local/gesture/.venv/bin/python -m experiments.grammar_eval prepare     # caches v3 fits (gaps)
../../.local/gesture/.venv/bin/python -m experiments.grammar_eval calibrate   # ~45 s → cross_gain.json
git show 20c3342:tools/gesture/gesture/grammar.py | sed 's/from \.\([a-z]*\) import/from gesture.\1 import/' > /tmp/grammar_v2.py
../../.local/gesture/.venv/bin/python -m experiments.grammar_eval test1 --baseline /tmp/grammar_v2.py   # ~2 min
../../.local/gesture/.venv/bin/python -m experiments.grammar_eval memo --n 600
../../.local/gesture/.venv/bin/python -m experiments.generate_demo            # ~1 min → demo_v3/
```
