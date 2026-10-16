# Grammar v7: where segments get short, what memorisation really is (2026-10-16)

v7 is a diagnosis round more than a feature round. Three v6 gaps were traced to
their sources; two fixes are on by default, one is an opt-in, and one suspected
cause turned out to be small.

Files changed:

- `gesture/grammar.py`: `plan_line(mode="v7")`, `Grammar.drawing_scales`, the
  segment-scale context in `Grammar.draw` (`dscale`, `w_ds`), the end fit in
  `generate_tokens` and `_Grower`, `generate_drawing(plans=, seg_scale=,
  order=, end_fit=, seek=)`, plan sources in stroke meta.
- `tests/test_grammar.py`: two v7 tests; the single-line stall check now
  takes the median over 30 seeds (the 8-seed median moved .43–.52 with the rng
  stream alone).
- `experiments/grammar_eval.py`: output to `grammar_v7/`, v6 reachable as the
  `V6` flag set, v7 ablations, `memo` with drawn variants and the
  "nearest = plan source" share, `chainfree` with segment-length quantiles,
  `test1 --variants` (in-module flag variants) and a token-level key table.
- `experiments/generate_demo.py`: writes `demo_v7/`.

**v6 stays reachable:** `plans="v6", seg_scale=0, order="draw", end_fit=0`
(the `V6` dict in `grammar_eval.py`). No new grammar fields: v6 grammar files
work unchanged.

Raw outputs: `.local/gesture/out/grammar_v7/` (`memo.md`, `chainfree_v7.md`,
`ablate_v7*.md`, `calibration.json`, `s0_test1*.md`, `s1_test1*.md`,
`memo_final.md`, `demo_v7/`).

## Verdict

1. **Segments too short: found, half fixed.** Three sources. (a) The pooled
   k-NN gives every sheet the *pooled* segment density, which dense drawings
   dominate (real per drawing: 14–46 segments/R for Matisse). (b) Every line
   ended in a stub (last segments 0.6 × real). (c) In drawn sheets, steering
   adds more: 36–39 segments/R drawn vs 31 in the free chain (real 24). The
   segment-scale context fixes (a) in the free chain (Matisse 31 → 25–27) but
   raised panel corners in drawn sheets, so it is opt-in. The end fit fixes
   (b) and is on. (c) is the open one.
2. **Memorisation: plan copying is real but small; the budget and the protocol
   are the large terms.** In v6, 4–5 % of drawn strokes had their plan's source
   stroke as nearest neighbour; the smoothed plan takes that to 0–1 %. Final
   drawn shares: Matisse 12 / 11 (v6 15 / 18), Ingres 17 / 12 (20 / 11),
   Hokusai 26 / 25 (25 / 22, unchanged). For Hokusai, a chain trained on
   *shuffled* tokens already scores 22 / 20 %, so the 10 % line cannot be
   reached there. v5's lower drawn numbers came from its arbitrary end cuts.
3. **Long lines: survival bias confirmed, partly fixed.** With v6, placed lines
   had a median of .114 against a plan median of .120 (q90 .28 vs .32).
   Long-first lifts the placed median to .125. But panel `len_q50` for Matisse
   did not move (.102 / .106 vs real .124), and the longest plans still fail.
4. **v7 as a whole is not better than v6 on test 1.** The two seeds averaged,
   logreg, the excess over the floor is:

   | artist | v7 | v6 |
   |---|---|---|
   | Matisse | +.12 | +.07 |
   | Hokusai | +.25 | +.15 |
   | Ingres | +.18 | +.23 |

   Hokusai panel corners rise from 1.46–1.53 to 1.77–1.95 (real 1.32): the
   corner match is *lost* for Hokusai and slightly worse for Matisse. Matisse
   turn correlation improves (.707 vs v6 .617, real .712).

   `plans="v6"` restores v6's plan. The ablation points at the smoothed plan
   and long-first as the Hokusai corner source; see §3.

## 1. Segments too short: the cause is per-drawing, then the line ends

Token level (σ = 2 w fit tokens vs chain tokens), each real long stroke
replaced by a chain stroke of its own length, plan from its own drawing
(`chainfree`, all 184 drawings; per-drawing medians):

| # | set | Matisse segs/R · seg q10/q50/q90 | Hokusai | Ingres |
|---|---|---|---|---|
| C1 | real | **23.7** · .009/.036/.081 | **15.4** · .017/.055/.121 | **25.6** · .009/.032/.073 |
| C2 | v6 chain | 31.1 · .005/.022/.071 | 19.5 · .011/.040/.107 | 30.5 · .006/.025/.068 |
| C3 | v6 + drawing segment scale | 26.2 · .007/.029/.079 | 18.3 · .012/.045/.121 | 29.4 · .006/.026/.070 |
| C4 | v6 + end fit | 30.6 · .005/.022/.075 | 18.5 · .012/.042/.110 | 29.2 · .007/.026/.070 |
| C5 | v7 chain (both + smoothed plan) | 26.6 · .008/.029/.078 | 17.3 · .012/.048/.114 | 28.3 · .007/.029/.070 |

Diagnosis, in order of size:

1. **Regression to the pool.** Real segment density varies 3× between drawings
   (Matisse 14–46 segments/R, q10–q90) and dense drawings have short segments
   (corr(segments/R, strokes per drawing) = .79–.90). The k-NN pool is
   dominated by dense drawings, so every sheet got the *pooled* density: the
   chain gave 24–41 around the pooled ~32 (Matisse), median 31.9 against the
   per-drawing median 23.7. This is the same per-drawing-vs-pooled error v6
   fixed for stroke lengths, one level down. The k-NN draw itself is unbiased:
   inner segments are at real (Matisse inner-segment median .0182 vs .0183).
2. **End stubs.** Each line's last token was cut at the target and kept if
   ≥ 30 % of it: last segments were 0.6 × real (Matisse .018 vs .029) and
   strokes carried +0.3–0.4 segments. Renewal-process stopping, not the hand.
3. Not the cause: κ-continuity relabelling (no-continuity chain: same density),
   the order-2 context, `W_REM` = 4 (no change), the corner budget (v5 chain
   has the same density).

Fixes:

- **Segment-scale context** (`seg_scale`, `W_DSCALE` = 4): every pool record
  carries its drawing's segment scale (log ink / segments); the query uses
  the source drawing's. Correlation of per-drawing density with real goes
  .81 → .95–.98 (Matisse), and the median 31.9 → 24.5. **But** in drawn
  sheets it *raised* panel corners in both ablations (Matisse 1.74 → 1.94–1.99,
  Ingres 1.75 → 2.08–2.25; §3). Not understood; so it is an **opt-in**, off by
  default.
- **End fit** (`END_FIT` = 0.5, default on): a last token that would be cut
  below half its length is not drawn. In the chain the previous segment absorbs
  the remainder (length stays exact); in a drawing the line ends there, under
  half a token short.

What remains: the drawn sheets have still shorter segments than the free chain
(§4: steering prefers feasible proposals, and short proposals are more often
feasible). That selection is the next suspect.

## 2. Memorisation: the cause, isolated

v4 protocol (every 5th drawing held out, grammar learned on the rest; share of
strokes whose nearest training turning signature is below the held-out real
10th percentile; healthy 10 %), 24 drawn sheets per variant (v6 used 9). Cells:
≥ 2 / ≥ 4 segments, in %. "src" = share of drawn strokes whose nearest training
stroke is the one their length / budget was copied from.

| # | set | Matisse | Hokusai | Ingres |
|---|---|---|---|---|
| Y1 | held-out real | 10 / 10 | 10 / 10 | 10 / 10 |
| Y2 | **shuffled-token control chain** | 13 / 11 | **22 / 20** | 15 / 7 |
| Y3 | chain, unbudgeted | 14 / 13 | 22 / 16 | 18 / 5 |
| Y4 | chain, v6 budget | 17 / 16 | 26 / 26 | 25 / 10 |
| Y5 | chain, v7 (smoothed plan) | 11 / 15 | 24 / 23 | 22 / 4 |
| Y6 | drawn, v5 mode | 10 / 8 | 16 / 11 | 9 / 5 |
| Y7 | drawn, v6 with v5's end-seeking cuts | 9 / 11 | 16 / 17 | 9 / 10 |
| Y8 | **drawn, v6** | 12 / 15 (src 4) | **28 / 27** (src 5) | 20 / 10 (src 5) |
| Y9 | drawn, v6 without the chain budget | 15 / 12 (src 3) | 22 / 15 (src 4) | 14 / 7 (src 4) |
| Y10 | drawn, v6 + smoothed plan | 14 / 14 (src 1) | 24 / 23 (src 1) | 19 / 14 (src 1) |
| Y11 | drawn, v7 study default (+ segment scale) | 11 / 11 (src 1–2) | 25 / 23 (src 1–2) | 15 / 10 (src 1) |
| Y12 | drawn, v7 without segment scale | 12 / 14 (src 1) | 23 / 21 (src 1) | 16 / 13 (src 0) |
| Y13 | jittered training copies (quoting) | 45 / 50 | 62 / 67 | 40 / 40 |

(Y11/Y12 ran before the end fit worked in drawings; the final default is in §5.)

1. **Plan copying is real but small.** In v6, 4–5 % of drawn strokes have
   their plan's source stroke as nearest neighbour (10–12 % of the low ones).
   The smoothed plan drops that to ~1 %, and the share by 0–4 points.
2. **The budget is the bigger term.** Removing it lowers Hokusai ≥ 4 from 27 to
   15 % (Ingres 10 → 7, chain level 26 → 16). The budget pulls each line's
   turning towards a real stroke's, which makes lines typical.
3. **v5's low drawn numbers were an artefact.** Its end-seeking cut lines at
   arbitrary points; giving v6 that seek alone (Y7) brings it back to v5's level.
   Truncated strokes are far from every training stroke. That is not a fix.
4. **The 10 % line is not reachable for Hokusai by construction.** A chain
   trained on *shuffled* tokens (Y2) is already at 22 / 20 %: held-out Hokusai
   drawings are far from the training drawings, while anything sampled from the
   training pool is close to it. Measured against the shuffled control, v7 is
   +0–3 points (v6: +5–7 for Hokusai and Ingres).
5. Nothing is near quoting (40–67 %).

## 3. Ablation (drawn sheets)

Two runs. The first used 16 drawings and 3 repeats; the second used 24 drawings,
2 repeats, and the end fit fixed (in the first run it was a no-op in drawings: a
branch-order bug, now fixed). Both used the v7 calibration, which ran with the
segment scale on. Each cell is panel corners / `turn_tcorr_10` / `len_q10` /
`len_q50` / panel AUC (logreg).

Real values: Matisse 1.31–1.40 / .715 / .063–.069 / .119–.124; Hokusai
1.29–1.36 / .43–.45 / .111 / .184–.187; Ingres 1.42–1.45 / .77–.78 / .053–.057 /
.084–.085.

| # | set | Matisse | Hokusai | Ingres |
|---|---|---|---|---|
| B1 | v6 (run 1) | 1.74 / .60 / .048 / .097 / .53 | 1.45 / .53 / .117 / .190 / .78 | 1.62 / .71 / .052 / .088 / .76 |
| B2 | v6 + smoothed plan | 1.35 / .62 / .047 / .093 / .75 | 1.64 / .60 / .102 / .190 / .68 | 1.58 / .73 / .048 / .089 / .91 |
| B3 | v6 + segment scale | 1.99 / .61 / .053 / .093 / .80 | 1.33 / .55 / .111 / .214 / .82 | 2.25 / .69 / .052 / .092 / .85 |
| B4 | v6 + long first | 1.67 / .68 / .050 / .099 / .72 | 1.58 / .46 / .107 / .197 / .65 | 1.74 / .68 / .051 / .084 / .85 |
| B5 | all + segment scale (study default) | 1.94 / .66 / .051 / .098 / .88 | 1.71 / .55 / .122 / .207 / .81 | 1.79 / .69 / .048 / .084 / .90 |
| B6 | v6 (run 2) | 1.74 / .61 / .057 / .106 / .69 | 1.49 / .53 / .108 / .190 / .70 | 1.75 / .71 / .051 / .088 / .87 |
| B7 | v6 + end fit | 1.75 / .64 / .062 / .109 / .76 | 1.46 / .53 / .098 / .190 / .71 | 1.65 / .72 / .047 / .083 / .91 |
| B8 | all + segment scale | 1.94 / .65 / .054 / .108 / .80 | 1.71 / .58 / .105 / .192 / .82 | 2.08 / .76 / .048 / .081 / .93 |
| B9 | all, segment scale 1 | 1.71 / .70 / .054 / .106 / .84 | 1.77 / .58 / .101 / .191 / .73 | 1.78 / .69 / .051 / .086 / .89 |
| B10 | all, no segment scale (≈ final default) | 1.68 / .71 / .054 / .106 / .72 | 1.93 / .59 / .108 / .191 / .67 | 1.68 / .66 / .047 / .080 / .86 |

1. AUCs at n = 16–24 move by ±.15 between runs of the same variant. B1 vs B6
   is the same v6: .53 against .69 for Matisse. Read only the corners and
   lengths.
2. The **segment scale raises corners** for Matisse and Ingres in both runs
   (B3, B5, B8: up to +.5). That is why it is opt-in.
3. **Hokusai's corners rise with the smoothed plan and with long-first** (B2,
   B4, B10). Each effect is within noise on its own, but they agree with test 1.
   A likely mechanism: with ~20 strokes per drawing the Silverman bandwidth hits
   its 0.30 cap. The budget stroke is then often a much straighter or turnier
   stroke than the length suggests, and over-budget lines turn through steering
   instead.
4. The end fit is neutral to good everywhere (B7).

## 4. Key features and test 1

Test 1 used standard preprocessing, geometry only and 3 repeats, with two seeds
(0 / 1). v6 ran as in-module flags (`--variants '{"v6": "V6"}'`); both v6 and v7
used the v7 calibration. Cells are logreg AUC as seed 0 / seed 1.

| # | artist | floor | **v7** | v7 − floor | v6 | v6 − floor | v7 tree |
|---|---|---|---|---|---|---|---|
| A1 | Matisse | .72 / .68 | **.83 / .81** | +.12 | .78 / .76 | +.07 | 1.0 |
| A2 | Hokusai | .46 / .49 | **.66 / .79** | +.25 | .66 / .59 | +.15 | .96 / .97 |
| A3 | Ingres | .66 / .67 | **.87 / .83** | +.18 | .90 / .90 | +.23 | 1.0 |

The topology-only classifier (logreg, seed 0 / seed 1):

| # | artist | floor | v7 | v6 |
|---|---|---|---|---|
| T1 | Matisse | .67 / .66 | .83 / .88 | .86 / .72 |
| T2 | Hokusai | .81 / .81 | **.76 / .84** (at the floor) | .87 / .85 |
| T3 | Ingres | .78 / .78 | .87 / .92 | .95 / .89 |

Topology still swings by about ±.08 between seeds. Hokusai v7 sits at its
floor in both seeds.

Key features, real / v7 / v6, seed 0 (seed 1 in brackets where it differs):

| # | artist | corners | `turn_abs` | `turn_tcorr_10` | len_q10 | len_q50 | len_q90 | X / len | L share | T angle | near aim | par ink | isolated |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| K1 | Matisse | 1.50 / 1.68 (1.70) / 1.77 (1.69) | 15.6 / 14.6 / 15.2 | .71 / **.71** / .62 | .065 / .051 / .057 | .124 / .102 / .104 | .30 / .25 / .23 | .24 / .26 / .35 | .036 / .088 / .083 | .91 / 1.09 / 1.13 | 1.13 / 1.08 / .98 | .17 / .22 / .17 | .47 / .43 / .42 |
| K2 | Hokusai | 1.32 / **1.95 (1.77)** / 1.46 (1.53) | 17.6 / 15.1 / 14.6 | .46 / .59 / .52 | .114 / .112 (.081) / .118 (.099) | .184 / .187 / .193 | .35 / .35 / .36 | .27 / .33 / .30 | 0 / .091 / .103 | .89 / 1.10 / 1.11 | 1.38 / 1.04 / 1.06 | .22 / .14 / .16 | .37 / .32 / .33 |
| K3 | Ingres | 1.61 / 1.68 (2.22) / 1.75 (2.06) | 21.6 / 18.0 / 17.0 | .73 / .70 / .71 | .056 / .046 / .046 | .085 / .078 / .080 | .19 / .18 / .16 | .20 / .29 / .26 | .061 / .071 / .071 | .61 / .76 / .84 | 1.43 / 1.26 / 1.26 | .15 / .16 / .12 | .59 / .51 / .53 |

Token level, drawn sheets (real = σ = 2 w fit tokens; generated = the chain
tokens drawn), seed 0. Columns: segments/R per-drawing median; corner tokens
per R; segment length q10 / q50 / q90; last-segment q50; segments per stroke.

| # | artist | real | v7 | v6 |
|---|---|---|---|---|
| S1 | Matisse | 23.7 · 5.3 · .006/.024/.073 · .029 · 4.2 | 38.6 · 9.5 · .004/.017/.058 · .018 · 4.9 | 38.8 · 8.5 · .004/.016/.058 · .016 · 4.8 |
| S2 | Hokusai | 15.4 · 6.9 · .014/.045/.116 · .044 · 3.2 | 21.4 · 7.7 · .008/.032/.101 · .030 · 4.5 | 21.7 · 7.6 · .008/.033/.099 · .029 · 4.4 |
| S3 | Ingres | 25.6 · 8.6 · .008/.029/.073 · .030 · 2.8 | 33.9 · 9.4 · .005/.022/.064 · .017 · 3.3 | 34.3 · 10.6 · .004/.021/.061 · .016 · 3.4 |

1. **Drawn sheets are much further from real than the free chain:** 38.6 against
   31 segments/R (Matisse), and corner *tokens* 9.5/R against the plan's 5.3.
   The budget is a prior, and steering overrides it. With K = 8 proposals,
   blocked lines take the feasible one, and short or cornered proposals are more
   often feasible. That is the main remaining source of short segments.
2. The end fit lifts drawn last segments only slightly (.016 → .018): most
   drawn lines end by T/near seeking or by being blocked, not at their plan.

## 5. Memorisation, final default

Final default (smoothed plans, long-first, end fit, no segment scale), 24
sheets per variant, the same held-out split. Cells are ≥ 2 / ≥ 4 segments in %,
with NN = plan source in brackets.

| # | set | Matisse | Hokusai | Ingres |
|---|---|---|---|---|
| Z1 | shuffled-token control | 13 / 11 | 22 / 20 | 15 / 7 |
| Z2 | **drawn v7** | **12 / 11** (0 %) | 26 / 25 (0–1 %) | **17 / 12** (0–1 %) |
| Z3 | drawn v6 (same run) | 15 / 18 (4 %) | 25 / 22 (4 %) | 20 / 11 (5 %) |

1. Plan quoting is gone in v7.
2. Matisse and Ingres sit at the shuffled control's level.
3. Hokusai is at control + 4–5 points, as v6 was. The remaining term there is
   the chain budget (§2).

## 6. Long lines (Matisse)

Twelve to sixteen v6 sheets were examined directly, with each line's planned
target against its realised length:

1. Realised / target = 1.00. Lines that are placed reach their plan.
2. R measured / R generated = 1.01. The measurement scale is not the cause.
3. Placed targets have a median of .114–.119 against the source drawing's plan
   median of .120–.141. The q90 is .28 against .32. This is **survival bias**:
   long plans fail the 0.75 acceptance more often and are replaced.
4. `order="long"` (the plans for the sheet's whole ink, grown roughly longest
   first) lifts the placed median to .125, above the plan median. The q90 is
   still short (.27 vs .32): the longest plans fail even on an emptier sheet.
5. Panel `len_q50` does not follow: .102 / .106 against real .124, within the
   noise of v6.

Next options:

- relax acceptance for the top length class (accept ≥ 0.5 × plan);
- or let a failed long plan re-seed elsewhere instead of being dropped.

## 7. Calibration

Settings: 24 drawings, 4 rounds plus 1 noise batch. It ran with the segment
scale on, and the end fit was a no-op at the time.

| # | artist | cross gain | end gains T / L / near / free | p_double |
|---|---|---|---|---|
| Q1 | Matisse | 0.90 | 1.27 / 0.93 / 0.96 / 0.98 | .035 |
| Q2 | Hokusai | 0.87 | 1.35 / 1.09 / 1.00 / 0.74 | .126 |
| Q3 | Ingres | 0.72 | 1.39 / 0.77 / 1.01 / 0.93 | .022 |

**The crossing response is noise-dominated.**

- Matisse at almost the same gain gave .179 to .348 crossings per length.
- Hokusai *rose* as the gain fell: 1.00 → .35, .65 → .43.
- A fitted response curve is not possible with this noise; 24 drawings per
  round is too few.
- Next options:
  - pool more rounds at a fixed gain grid (≥ 60 drawings per point);
  - or calibrate on a crossing count less tied to a few heavy sheets, such as
    the median of per-sheet crossings over ink.

## 8. The sheets, looked at

The sheets are `grammar-v7-matisse.jpg`, `grammar-v7-hokusai.jpg` and
`grammar-v7-ingres.jpg`, in the final default, seed 20261016.

1. **Matisse.**
   - Learned #1 is a dense, page-filling tangle of short pieces (≈ 12 R of ink),
     as in v6. Learned #2 is scattered fragments.
   - Learned #3 is the best tile: long flowing silhouettes and an enclosing
     contour. It still has two long dead-straight diagonals crossing it. The
     straight-line tell from v6 has not gone; learned #4 has one too.
   - Tree #2 and #3 are large cut-paper masses with long contour lines, the most
     figure-like. Tree #1 and #4 are sparse.
   - Single lines are smooth large loops. One has a straight diagonal; one ends
     in a small nervous knot.
2. **Hokusai.**
   - Curly and hooked lines, but **more angular than real**: tree #3 and #4 read
     as jagged blobs of short straight pieces with sharp turns. That is the
     corner rise from §4 made visible.
   - Learned #1 is sparse (3 R).
   - Single lines are mazy with loops. Single #3 has a dense knot at the bottom.
3. **Ingres.**
   - The learned sheets are sparse short fragments scattered over the page. They
     do not read as Ingres's long enclosing contours (compare the real tiles).
   - Tree #2 is a large drapery-like mass with long lines and reads well. Tree
     #3 and #4 look like crumpled paper.
   - Two of the four single lines stalled early (1.0 and 2.3 R of ink).
4. **All three hands.**
   - Contiguous lines, no hatching anywhere.
   - Composition is still fragments around a mass, as in v6.
   - The tree mode is again the most "drawing-like" and the furthest from real
     statistically (touching ~4×).

Ready for Ian to look at. Nothing has been plotted. Visually, v7 is not a clear
step from v6.

## 9. Remaining gaps

1. **Steering makes segments short and cornered in drawn sheets** (§4: 38.6
   against 31 in the free chain against 24 real; corner tokens 9.5 against 5.3
   planned). Next:
   - choose among feasible proposals by budget weight, not by the first
     feasible one;
   - count steered corners against the budget too;
   - raise K so a within-budget feasible proposal exists more often.
2. **Hokusai corner match lost in v7** (1.8–1.95 against 1.32; v6 1.46–1.53).
   Suspects are the smoothed plan's capped bandwidth on few-stroke drawings,
   and long-first. Try a smaller `PLAN_BW` cap or a per-hand plan mode. Until
   then `plans="v6"` is the safer setting for Hokusai.
3. **The segment-scale context** is correct in the free chain but raises panel
   corners in drawn sheets, for reasons not yet understood. It is opt-in
   (`seg_scale=gm.W_DSCALE`).
4. **Memorisation for Hokusai** is set by the protocol (shuffled control 22 %)
   and the chain budget (+4–10 points). A softer budget trades against corners.
5. **Long lines:** the median is fixed at plan level, but panel `len_q50` and
   q90 have not moved (§6).
6. **Topology (not attempted this round):**
   - L share is 2× real (.088 vs .036 Matisse; .09 vs 0 Hokusai);
   - T angle too wide (1.09 vs .91);
   - near aim too head-on (Hokusai 1.04 vs 1.38);
   - Hokusai parallel ink .14 vs .22 and isolated strokes .32 vs .37;
   - Hokusai `turn_abs` low (15.1 vs 17.6).
7. **Crossing calibration noise** (§7).

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
$P -m experiments.grammar_eval chainfree --only v6_chain_drawing,v6+dscale,v6+endfit,v7_chain --tag chainfree_v7  # ~4 min
$P -m experiments.grammar_eval memo --n 600                     # ~5 min, all MEMO_DRAWN variants
$P -m experiments.grammar_eval calibrate --calib-noise 1        # ~6 min
$P -m experiments.grammar_eval ablate --repeats 2 --max-real 24 --tag ablate_v7b \
   --only v6,v6+endfit,v7,v7+dscale --extra '{"v7_ds1": {"seg_scale": 1.0}}'   # ~5 min
$P -m experiments.grammar_eval test1 --repeats 3 --seed 0 --variants '{"v6": "V6"}'   # ~6 min; again with --seed 1
$P -m experiments.grammar_eval memo --n 600 --only drawn_v7,drawn_v6 --tag memo_final
$P -m experiments.generate_demo                                 # demo_v7/
```
