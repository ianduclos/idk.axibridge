# Grammar v6: planned lengths and a corner budget (2026-10-16)

v6 plans each line first and gives the chain a per-stroke corner budget.

Files changed:

- `gesture/grammar.py`
- `tests/test_grammar.py`: 3 tests adapted, plus a budget check in the single-line test
- `experiments/grammar_eval.py`, which gains:
  - a `chainfree` diagnosis;
  - calibration noise batches;
  - v6 ablations;
  - a v5 baseline with its own calibration (`--baseline-calib`);
  - v6 sets in `memo`.
- `experiments/generate_demo.py`, which now writes `demo_v6/`.

Raw outputs are in `.local/gesture/out/grammar_v6/`:

- learned grammars: `grammar_{artist}.json`
- `calibration.json`
- `ablate_v6.md`
- `chainfree*.md`
- `test1*.md`
- `memo.md`
- `demo_v6/`
- the first pass at turning gain 1.0 is in `gt1/`

Sheets: `grammar-v6-matisse.jpg`, `grammar-v6-hokusai.jpg`.

## Verdict

1. **Most of the corner excess comes from the chain itself, not from the layout.**
   - The free chain was tested with no steering, no relations and no sheet: each
     real stroke was replaced by a chain stroke of the same length.
   - At panel scale it already has 1.2–1.4× the real corner rate.
   - It has 1.4–1.8× the real corner *tokens* per unit length.
   - Taking only the single nearest record (`knn=1`, which is close to replay)
     removes the excess. So the cause is the k-NN splice: a uniform draw among the
     12 nearest contexts.
   - It is not κ-continuity, not the order-2 context, and not the corner
     representation.
2. **The fix sits where the problem is, in the chain's draw.**
   - Each line draws a budget of corners and turning from one real stroke.
   - The chain's k-NN proposals are re-weighted against that budget.
   - In the free chain, corner tokens per length now match real for all three
     hands.
3. **Lengths:** the plan is drawn per *drawing*, and the end-seeking cut bug is fixed.
   - `len_q10` goes from 0.6 × real to 0.86–0.96 × real.
   - Hokusai's `len_q10` is .110 against real .114 (v5 .058).
4. **Panel test 1 beats v5 for all three hands, measured in the same run:**

   | artist | v6 − floor | v5 − floor |
   |---|---|---|
   | Matisse | +.08 | +.13 |
   | Hokusai | +.24 | +.39 |
   | Ingres | +.16 | +.27 |

5. **Topology AUC moved in different directions and is noisy:**
   - Hokusai reached its floor.
   - Matisse and Ingres came out worse in the final run.
6. **Memorisation regressed for Hokusai's and Ingres's short strokes** (see §6).

## 1. Diagnosis: is the corner excess already in the free chain?

Method: `grammar_eval chainfree`, all 184 drawings. Each real long stroke is
replaced by a chain stroke of exactly its length, rigidly aligned onto it. Corners
are counted exactly as the panel's `cl_corner_rate` counts them (σ = max(.01 R, 7 w)).
There is no steering, no sheet and no relations.

The table gives the median corner rate per drawing, then corner tokens and segments
per R. Real values are shown in bold.

| # | set | Matisse corners / tok / segs | Hokusai | Ingres |
|---|---|---|---|---|
| C1 | real | **1.49** / **5.3** / **23.7** | **1.26** / **6.9** / **15.4** | **1.56** / **8.6** / **25.6** |
| C2 | identity: own tokens re-drawn (the floor) | 1.43 / 5.3 / 23.7 | 1.24 / 6.9 / 15.4 | 1.54 / 8.6 / 25.6 |
| C3 | own tokens, shuffled | 1.9–2.3 / 5.3 | 1.66 | 1.7–2.0 |
| C4 | v3 chain (no follow) | 1.75 / 9.5 / 31.9 | 1.83 / 8.3 | 2.12 / 12.4 |
| C5 | **v5 chain** (follow 0.9, runs ≤ 2) | **1.95–2.15** / 8.7 / 31.2 | **1.69–1.85** / 9.2 | **1.86–2.50** / 12.0 |
| C6 | v5 chain, no κ-continuity | 2.13 / 8.8 | 1.62 / 8.3 | 2.12 / 11.2 |
| C7 | v5 chain, order 1 (25 drawings) | 1.86 | 1.62 | 1.95 |
| C8 | v5 chain, k = 4 | 2.09 | 1.65 | 1.92 |
| C9 | **v5 chain, k = 1** (nearest record only) | **1.53** / 7.4 | **1.36** / 9.2 | **1.53** / 11.8 |
| C10 | **v6 chain** (budget from that drawing, turning gain 0.3) | **1.65** / **5.4** / 30.4 | **1.51** / **6.4** / 18.3 | **1.58** / **7.9** / 30.5 |
| C11 | v6 chain, turning gain 1.0 | 1.52 / 5.4 | 1.77 / 8.4 | 1.79 / 8.3 |
| C12 | v6 chain, budget gain 2 | 1.16 / 5.1 | 1.49 / 7.0 | 1.39 / 6.7 |

Ranges show two full runs of the same variant. They differ only in how the shared
generator is consumed, so the noise in a per-artist median is about ±0.2–0.3.

**Diagnosis.**

1. The free chain alone is 1.2–1.4× real at panel scale and 1.4–1.8× at token
   level.
   - v5's drawings were 1.5–1.8× real. So most of the excess is in the chain, and
     layout and steering add the remaining ~0.3×.
2. The cause is the k-NN draw.
   - At k = 1 the excess disappears (C9). Smaller k helps a little.
   - Removing κ-continuity or the order-2 context does not help (C6, C7).
   - Following the source stroke helps only as far as it approaches replay.
3. The mechanism: neighbouring contexts come from other strokes, and their next
   tokens are shorter than the current stroke's own would be.
   - The mean segment is .031 against real .042 (Matisse).
   - So tokens, corners and turning per length all go up together.
4. The budget repairs corner tokens per length exactly (C10). It brings the panel
   rate to 1.0–1.2×.
5. **Not fixed: segments are still too short** (30 against 24 segments per R).
   - That is why Hokusai keeps a residual at panel scale even with exact corner
     tokens: short turny segments read as corners at 7 w.

## 2. What changed in `grammar.py`

1. **`plan_line`: a line is planned first.** The plan holds the line's length, its
   corner tokens per length and its segment turning per length.
   - All three are taken *jointly from one training stroke* of the sheet's
     **source drawing**. That is one training drawing per sheet, the same one that
     sets the ink budget.
   - Only those three scalars are taken.
   - Why per drawing: real `len_q10` is a per-drawing statistic. v3–v5 sampled
     lengths from the pool of all strokes, so dense drawings with short strokes
     dominated. The pooled q10 (.046 / .072 / .044) sits well under the per-drawing
     median q10 (.065 / .114 / .056). That accounted for most of the "lines are too
     short" gap since v3.
2. **`_Budget` re-weights the chain's k-NN proposals.**
   - **Corners:** the plan's rate × the line's length, stochastically rounded to a
     whole number n and released evenly along the line (ceil(n·x/L) by arc length
     x).
   - **Turning:** the plan's rate × x, plus a slack of up to one median segment
     turning.
   - Over budget, the weight is exp(−2·excess corners) · exp(−0.3·excess radians).
     Within budget, the chain is untouched.
   - Follows go through the same weight, as an acceptance probability.
   - If every neighbour is over budget, the pool widens once to 4k.
   - Applied in `generate_tokens(budget=)` and in `_Grower`. In single mode, a
     chunk retries without the budget after 2 failed tries: the budget is a prior,
     not a wall.
3. **Seeking a T or near end.**
   - Ink is sought only within (1 ± `SEEK_WIN` = 0.15) × the plan.
   - v5 gated on the *candidate's* end passing 0.85 L, but cut at the first point
     that reached ink. That could be anywhere in a long candidate, so lines ended at
     0.3–0.7 × plan. In v5, T/near ends were at a median 0.7 × plan and a q10 of
     0.3 × plan.
   - A line that finds no ink is now cut back to its plan, so failed seeks no longer
     run to 1.3 ×.
4. **Acceptance.**
   - A line realised below `LEN_KEEP` = 0.75 × its plan is regrown, up to
     `LEN_TRIES` = 10 times. Every try re-seeds its start relation, so a boxed-in
     near-start becomes a new start rather than a stub.
   - If all tries fail, the line is not placed.
   - Result: realised / planned length is q10 ≥ 0.77, against v5's 0.21–0.38.
5. **Single-line bug fixed:** backing up a chunk now also restores its hand.
6. **Flags:**
   - `lengths="v5"` and `chain_budget=0` give v5 behaviour.
   - `ends="v4"` still works.
   - Grammar version is 6. Older grammars fall back to the pooled plan.

## 3. Ablation

16 real drawings per artist, 3 repeats, the v6 calibration for every row. This run
used turning gain 1.0; the final default is 0.3, which is not ablated. Each cell is
corners / tcorr / `len_q10` / AUC panel–topology.

Real values: Matisse 1.40 / .71 / .069, Hokusai 1.29 / .43 / .111, Ingres 1.42 / .78 / .053.

| # | set | Matisse | Hokusai | Ingres |
|---|---|---|---|---|
| B1 | v5 (in the v6 module) | 2.46 / .54 / .043 / .87–.73 | 1.91 / .52 / .057 / .95–.84 | 2.75 / .50 / .036 / .90–.86 |
| B2 | lengths fix alone | 2.08 / .67 / .055 / .92–.80 | 1.81 / .46 / **.107** / **.73**–.78 | 2.24 / .53 / .056 / .84–.75 |
| B3 | budget alone | 2.23 / .67 / .039 / .64–.72 | 1.66 / .53 / .053 / .79–.84 | 2.26 / .52 / .043 / .95–.89 |
| B4 | **v6 (both)** | **1.80** / .64 / .053 / .84–.64 | **1.67** / .55 / .102 / .82–.77 | **1.85** / .57 / .057 / .89–.89 |
| B5 | v6, budget gain 2 | 1.12 / .78 / .057 / .72–.71 | 1.30 / .67 / .115 / .84–.89 | 2.06 / .76 / .053 / .88–.90 |
| B6 | v6, v5's panel-scale steering budget off | 1.94 / .65 / .053 / .75–.77 | 1.79 / .52 / .106 / .79–.78 | 2.05 / .60 / .052 / .81–.95 |

How to read it:

1. The two fixes add up.
   - The lengths fix alone also removes corners (2.46 → 2.08). Fewer blocked lines
     means less steering.
   - The budget alone does the rest.
2. Gain 2 overshoots for Matisse (1.12) and over-straightens: tcorr .78.
3. v5's panel-scale steering budget still contributes a little (B6 vs B4), so it
   stays on.
4. AUCs at n = 16 are ±0.1, so read only the direction.

## 4. Key features: real / v6 / v5 (test 1, all drawings, the same run)

| # | artist | corners / len | len_q10 | len_q50 | segs / stroke | X / len | L share | L defl | near aim | kiss / ink | par ink | isolated |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| K1 | Matisse | 1.50 / **1.69** / 2.64 | .065 / **.056** / .044 | .124 / .105 / .102 | 1.42 / 1.42 / 1.56 | .24 / .21 / .28 | .036 / .077 / .085 | 1.25 / 1.02 / 1.24 | 1.13 / 1.03 / .88 | 0 / 0 / 0 | .17 / .17 / .17 | .47 / .43 / .43 |
| K2 | Hokusai | 1.32 / **1.36** / 2.03 | .114 / **.110** / .058 | .184 / .185 / .133 | 1.41 / 1.43 / 1.50 | .27 / .26 / .32 | 0 / .069 / .085 | 1.18 / 1.46 / 1.32 | 1.38 / 1.10 / 1.03 | 0 / **0** / .16 | .22 / .16 / .11 | .37 / .27 / .35 |
| K3 | Ingres | 1.61 / **1.85** / 2.72 | .056 / **.048** / .038 | .085 / .083 / .084 | 1.28 / 1.35 / 1.50 | .20 / .24 / .19 | .061 / .066 / .078 | 1.32 / 1.30 / 1.34 | 1.43 / 1.28 / 1.15 | .25 / .28 / .09 | .15 / .14 / .11 | .59 / .52 / .51 |

1. Corners are now 1.13 / 1.03 / 1.15 × real. In v5 they were 1.76 / 1.54 / 1.69 ×.
2. Turn correlation `turn_tcorr_10` in the ablation: Matisse .54 → .64 (real .71),
   Ingres .50 → .57 (real .78), Hokusai .52 → .55 (real .43).
3. T share: .156 / .229 / .093, against real .134 / .211 / .090.

## 5. Test 1 against the floor (same run)

The setup:

- standard preprocessing, geometry only, 3 repeats;
- v5 is the HEAD module with v5's own calibration;
- the floor is real strokes re-drawn from their own tokens.

Each cell is logreg / forest.

| # | artist | floor | **v6 learned** | v6 − floor | v5 learned | v5 − floor | v6 no `rel_` | v6 tree |
|---|---|---|---|---|---|---|---|---|
| A1 | Matisse | .72 / .43 | **.80** / .85 | **+.08** | .85 / .94 | +.13 | .81 | .99 |
| A2 | Hokusai | .46 / .41 | **.70** / .75 | **+.24** | .85 / .84 | +.39 | .69 | .96 |
| A3 | Ingres | .66 / .62 | **.82** / .86 | **+.16** | .93 / .96 | +.27 | .76 | 1.0 |

1. The first v6 pass, with turning gain 1.0, gave .85 / .69 / .92. Moving to 0.3
   mostly helped Ingres. The turning budget at 1.0 made Hokusai and Ingres too
   smooth.
2. Top v6 tells:
   - **Matisse:** crossing angle too shallow; long lines too few (`len_q90` .30 →
     .24); near-rate +.7.
   - **Hokusai:** **too little turning** (`turn_abs` −0.8, `turn_net_ratio` −0.9)
     and short-range κ correlation lost.
   - **Ingres:** near-rate +1.1, fewer curvature extrema (−0.9), sharper extrema
     (+0.8).
   - Corners and `len_q10` are no longer among the top tells for any hand.
3. The tree mode is still near 1.0. Its touching is about 4× real by design.

**Topology-only classifier** (logreg / forest):

| # | artist | floor | v6 (final) | v6 (gain-1.0 pass) | v5 |
|---|---|---|---|---|---|
| T1 | Matisse | .67 / .20 | .87 / .87 | .72 / .83 | .83 / .88 |
| T2 | Hokusai | .81 / .63 | **.80 / .88** | .83 / .89 | .89 / .94 |
| T3 | Ingres | .78 / .68 | .94 / .93 | .88 / .93 | .91 / .94 |

1. Matisse moved by .15 between two nearly identical runs. The topology AUC is
   noise-dominated at n ≈ 30.
2. Hokusai is at its floor in both v6 runs, and its kisses are gone.
3. Topology tells that remain:
   - L share 2× real (Matisse, Hokusai);
   - T angle too wide;
   - near aim too head-on;
   - Hokusai parallel ink .16 against .22;
   - Hokusai isolated strokes .27 against .37.

## 6. Memorisation (v4 protocol, n = 600)

Each cell is the share of strokes below the held-out 10th percentile, ≥ 2 / ≥ 4
segments. Healthy is 10 %.

| # | artist | chain v5 | chain v6 (budget) | **drawn v6** | drawn v5 mode (same run) | v5 report, drawn |
|---|---|---|---|---|---|---|
| M1 | Matisse | 14 / 13 | 15 / 14 | **12 / 12** | 12 / 8 | 10 / 8 |
| M2 | Hokusai | 26 / 20 | 25 / 25 | **24 / 20** | 13 / 4 | 20 / 15 |
| M3 | Ingres | 18 / 7 | 21 / 9 | **16 / 9** | 7 / 3 | 7 / 8 |

1. The budgeted chain is at the unbudgeted chain's level, within ±4 points.
2. Drawn v6 strokes are at the chain's own level. In v5, drawn strokes sat
   *below* the chain, because v5 cut lines at arbitrary points: truncated strokes
   are far from every training stroke.
3. Against v5's drawn strokes this is a **regression** for Hokusai (13 → 24 %) and
   Ingres short strokes (7 → 16 %).
4. A second cause is likely, though it is not isolated:
   - v6 lines now have *exactly* a training stroke's length;
   - `log(length)` is part of the turning signature.
   - Next step: jitter the planned length (log-normal, ≈ 0.1–0.15) and re-measure.
5. The jittered-copy floor is 38–74 %. v6 is nowhere near quoting.

## 7. Calibration (v6, 24 drawings per round, 4 rounds + 2 noise batches)

| # | artist | cross gain | end gains T / L / near / free | p_double | crossings: real → batches | par ink: real → batches |
|---|---|---|---|---|---|---|
| Q1 | Matisse | 0.95 | 1.39 / 0.89 / 0.96 / 0.92 | .031 | .237 → .233, .246 | .168 → .173, .185 |
| Q2 | Hokusai | 0.77 | 1.62 / 0.80 / 1.01 / 0.63 | .184 | .265 → **.352, .229** | .223 → .149, .155 |
| Q3 | Ingres | 0.79 | 1.43 / 0.87 / 1.02 / 0.84 | .038 | .200 → .209, .211 | .152 → .152, .146 |

Noise:

1. End shares are stable between batches to ±.01–.015.
2. Crossings are stable for Matisse and Ingres (±.01). Hokusai swings ±25 %: its
   crossings per drawing are intrinsically heavy-tailed.
3. Within the rounds, the same gain gave .236 and .313 (Matisse). The full curves
   are in `calibration.json`.
4. Hokusai's parallel ink does not reach the real level even at p_double .18. The
   guide holds its offset for too short a run; this was already the case in v5.
5. Calibration ran at turning gain 1.0, before the switch to 0.3. Test 1 crossings
   at 0.3 are .21 / .26 / .24 against real .24 / .27 / .20, so close enough.

## 8. The sheets, looked at

The sheets are `grammar-v6-matisse.jpg` and `grammar-v6-hokusai.jpg`. The Ingres
sheet was rendered (`demo_v6/`) but not reviewed.

1. **Matisse.**
   - Lines are visibly longer and calmer than in v5: long open arcs and silhouettes
     with fewer jagged bites. Single lines are long smooth loops, and one reads as
     a torso or vase silhouette.
   - The tree row reads as cut-paper shapes and cells.
   - Learned #1 and #4 are dense tangles (≈ 10 R of ink). They are still mostly
     short pieces near each other, not figures.
   - Learned #4 has a few **long dead-straight lines** forming a triangle. That is
     a corner-free budget on a long plan, and it looks foreign.
   - Learned #2 and tree #2 are sparse or small.
2. **Hokusai.**
   - Curlier and more hooked than v5. Single lines are mazy, with loops and hooks.
     Tree #4 is a large flowing contour.
   - Some stretches still read as zig-zags of straight pieces (learned #2 and #4,
     tree #1): less than in v5, but present.
   - Learned #1 is sparse (2 R).
3. **Both hands.**
   - Still fragments around a mass more than a figure, as in v5.
   - Contiguous lines, no hatching anywhere.

Ready for Ian to look at. Nothing has been plotted.

## 9. Remaining gaps

1. **Segments are too short in the chain** (about 30 against 24 per R). This is the
   residual k-NN bias.
   - The budget only fixes corners and turning, not segment length.
   - Next: weight neighbours by next-segment length, or weight neighbour records
     by the context's remaining-length agreement. `W_REM` = 4 helped Matisse in a
     25-drawing probe.
2. **Long lines are under-represented** for Matisse (`len_q50` .105 against .124,
   `len_q90` .24 against .30). This is probably survival bias: in dense sheets,
   long plans fail the 0.75 acceptance more often and are replaced by fresh plans.
   - Next: keep a failed plan's length in the queue, or relax acceptance for long
     plans.
3. **Memorisation regressed against v5's drawn strokes** for Hokusai and Ingres.
   Jitter the planned length (§6).
4. **Topology:**
   - L share is 2× real;
   - T angle too wide;
   - near aims too head-on;
   - Hokusai double contours (.16 against .22);
   - Hokusai isolated strokes (.27 against .37).
5. **Hokusai turning is now slightly too low** (`turn_abs` −0.8). The turning
   budget slack could be per-drawing, or the gain set per hand.
6. **Occasional dead-straight long lines** (Matisse) where a zero-corner budget meets
   a long plan.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
git show 29bc4a7:tools/gesture/gesture/grammar.py | sed 's/from \.\([a-z_]*\) import/from gesture.\1 import/' > /tmp/grammar_v5_base.py   # v5
$P -m experiments.grammar_eval chainfree                 # ~4 min: the free-chain diagnosis
$P -m experiments.grammar_eval calibrate                 # ~7 min (24 drawings × 4 rounds + 2 noise batches)
$P -m experiments.grammar_eval ablate --repeats 3 --max-real 16 --tag ablate_v6 \
   --only v5,v6_lengths,v6_budget,v6,v6_b2,v6_nosteer_budget              # ~4 min
$P -m experiments.grammar_eval test1 --repeats 3 --baseline /tmp/grammar_v5_base.py \
   --baseline-name v5 --baseline-calib ../../.local/gesture/out/grammar_v5   # ~8 min
$P -m experiments.grammar_eval memo --n 600
$P -m experiments.generate_demo                          # demo_v6/
```
