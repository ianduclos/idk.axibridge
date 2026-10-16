# Grammar v5: joins and corners (2026-10-16)

v5 gives the grammar's relations layer topology's targets. It also tries three
corner remedies.

Files changed:

- `gesture/grammar.py`
- `tests/test_grammar.py` (+4 tests)
- `experiments/grammar_eval.py`, which gains:
  - a v5 `calibrate`;
  - `ablate` with topology features and a topology AUC;
  - `test1` with the identity floor and the topology AUC in the same run;
  - `memo` with the strokes as drawn;
  - `JOBS = 3`.
- `experiments/generate_demo.py`

Raw outputs are in `.local/gesture/out/grammar_v5/`:

- `ablate_v5.{md,json}`
- `test1.md`, `test1_key.md`, `test1_topo_key.md`
- `memo.md`, `calibration.json`
- the learned grammars `grammar_{artist}.json`
- `demo_v5/`
- per-drawing topology targets in `topo/`

Sheets: `grammar-v5-matisse.jpg`, `grammar-v5-hokusai.jpg`.

## Verdict

1. **Joins are fixed. Corners are not.**
   - Join deflection now matches the real hands: about 1.25–1.34 rad against
     real 1.18–1.32. v4 gave 0.35–0.55.
   - Joins are no longer over-produced. The L-end share is .08 / .09 / .08,
     where v4 gave .11 / .15 / .11 and the real hands .04 / 0 / .06.
   - Hokusai is no longer over-connected: isolated strokes are .35, against v4
     .21 and real .37.
   - Topology-only AUC, full run: Matisse .91 → **.83**, Hokusai .97 → **.89**,
     Ingres .88 → .91.
   - In the 14-drawing ablation the relations layer alone reached .67 / .75 / .77,
     but that did not hold at full size.
2. **Corner-aware steering helps a little on its own, and the new end
   behaviour cancels it.**
   - On its own (ablation), corner-aware steering takes Matisse from 2.55 to 2.28
     and Hokusai from 1.76 to 1.44. It does nothing for Ingres (2.12 → 2.23).
   - Combined with the end behaviour, the corner rate is back where it was:
     Matisse 2.64, Ingres 2.72, and Hokusai **2.03**, worse than v4's 1.40.
3. **Panel test 1 relative to its floor (measured in the same run):**

   | artist | floor | v5 | v4 |
   |---|---|---|---|
   | Matisse | .72 | .85 | .91 |
   | Hokusai | .46 | .85 | .77 |
   | Ingres | .66 | .93 | .89 |

   - The excess over the floor is Matisse +.13, Hokusai +.39, Ingres +.27.
     v4's was +.19, +.31 and +.23.
   - So v5 is better for Matisse and worse for Hokusai and Ingres. The main
     reason is **`len_q10`**: seeking ends cut lines short, and near-starts get
     boxed in.
4. **Memorisation did not regress.**

## 1. What changed in `grammar.py`

1. **Topology targets.**
   - `topology_summary(drawing)` measures each real long subset with
     `topology.relation_graph`.
   - `pool_topology` pools those per hand into `relations["topo"]`. That holds
     the end shares (T / L / near / free), and samples of join deflection, near
     gap and aim, T position and angle, and parallel offset and overlap. It also
     holds the kisses per ink and the parallel-ink share.
   - `learn(..., topo=)` stores it. `learn(drawings)` computes it itself.
2. **Start relations.** These are drawn from the end shares, scaled by the
   calibrated `end_gain`.
   - **L (join).** The line starts at a free end, turned by a learned deflection.
     `join="smooth"` keeps v4's tangent ± N(0, 0.25) for the ablation.
   - **T.** The branch starts away from the host's ends, so it is not read as a
     join.
   - **near.** The line starts at a learned gap beside a line and leaves at a
     learned aim.
   - **P (double contour).** The line starts beside a host at a learned offset,
     with a guide steering it to keep that offset over a learned overlap.
     `p_double` is calibrated.
   - **free.**
3. **End plans** (T / near / free).
   - **T and near.** From 0.85 × the planned length (up to 1.3 ×), a proposal
     that reaches ink is cut there. For T it is cut on the line; for near, at the
     learned gap.
   - **Free.** The line prefers a last step with no ink within 0.02 R. Free ends
     are then **protected**, so no later line comes within 0.02 R of them.
4. **Kisses.** Hands without kisses keep lines 1.1 × topology's touch distance
   apart, and their branches leave at ≥ 0.55 rad.
5. **Corners.** Three new remedies:
   - **`corner_budget`.** A proposal that adds a corner at panel scale (≥ 35°
     within ±2·7 w) beyond the hand's own rate × the line's length is skipped
     when a proposal within budget is feasible. The hand's rate is measured by
     the same proxy on its training strokes.
   - **`kmatch`.** k-NN splices prefer records whose next token starts at the
     current joint κ.
   - **`look_mult`.** A longer look-ahead.
   - Defaults: budget 1.0, kmatch **0**, look 1.
6. **Bug found on the way.** Asking the chain to go past its planned length
   (rem → 0) made it propose corners at 65 % of steps. Past the planned length
   the context is now `s + 0.3·length`.
7. `ends="v4"` reproduces v4. Grammars saved before v5 fall back to it.

## 2. Ablation

The ablation used 14 real drawings per artist, 3 repeats, and the full module
with calibration. Cells are generated median → real median. AUCs are logreg:
panel / topology.

| # | set | Matisse corners (1.40) | M tcorr (.71) | M AUC panel / topo | Hokusai corners (1.45) | H len_q10 (.111) | H AUC | Ingres corners (1.42) | I AUC | L defl (real ≈1.2) | kiss / ink M · H · I (0 · 0 · .11) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 | v4 | 2.55 | .57 | .96 / .90 | 1.76 | .086 | .91 / .82 | 2.12 | .93 / .85 | .43 · .33 · .42 | .15 · .05 · 0 |
| B2 | + kmatch | 2.80 | .59 | .89 / .88 | **0.98** | .076 | .76 / .80 | 2.46 | .88 / .72 | — | — |
| B3 | + budget 1.0 | **2.28** | .62 | .64 / .91 | **1.44** | .078 | .84 / .87 | 2.23 | .78 / .93 | — | 0 · .20 · .26 |
| B4 | + budget 0.5 | **2.13** | .63 | .93 / .92 | 1.49 | .078 | .74 / .85 | 2.21 | .72 / .88 | — | — |
| B5 | + look 2× | 2.87 | .53 | .82 / .89 | 1.73 | .071 | .73 / .92 | 2.42 | .84 / .77 | — | — |
| B6 | relations layer only | 2.46 | .51 | .94 / **.67** | 2.02 | **.045** | .77 / **.75** | 2.57 | .88 / .77 | **1.39 · 2.01 · 1.35** | .03 · .07 · .45 |
| B7 | relations layer, smooth joins | 2.72 | .52 | .94 / .81 | 1.98 | .047 | .79 / .78 | 3.19 | .95 / .83 | .37 · .25 · .33 | 0 · .18 · .45 |
| B8 | v5 (budget + kmatch + layer) | 2.54 | .56 | .98 / .69 | 1.50 | .053 | .86 / .74 | 2.78 | .88 / .85 | .88 · 1.51 · 1.02 | 0 · .20 · .21 |
| B9 | v5 + look 2× | 2.27 | .61 | .93 / .65 | 2.23 | .047 | .70 / .76 | 2.88 | .87 / .67 | 1.57 · 1.15 · 1.34 | .10 · 0 · .09 |

How to read it:

1. **The relations layer (B6) is the clear topology gain.**
   - Sharp joins against smooth ones (B6 vs B7) are worth .14 / .03 / .06
     topology AUC.
   - It costs `len_q10` (Hokusai .086 → .045). After this ablation, seeking was
     moved later (from 0.6 × to 0.85 × the planned length). Test 1 still shows
     the loss.
2. **Corner-aware steering** is the only remedy that lowers corners for two
   hands. Budget 0.5 is slightly better than 1.0 for Matisse.
3. **κ-matched splices** are inconsistent:
   - Hokusai's corners fall below the real rate, Matisse's and Ingres's rise.
   - On toy hands, kmatch boxed single lines in.
   - So it is off by default.
4. **Longer look-ahead** helps only together with the relations layer (Matisse).
5. **Kisses** are noisy at n = 14. Matisse reaches 0. Hokusai still kisses
   (.16–.20 in most runs). Ingres kisses, but at the wrong level: either too
   much (.45) or too little (.09 in test 1).

## 3. Key features: real / floor / v5 / v4 (test 1, all drawings)

| # | artist | corners / len | len_q10 | segs / stroke | touch | X / len | L share | L defl | near aim | free | isolated | kiss / ink | par ink |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| K1 | Matisse | 1.50 / 1.48 / **2.64** / 2.71 | .065 / .063 / .044 / .047 | 1.42 / 1.43 / 1.56 / 1.58 | .15 / .17 / .25 / .24 | .24 / .19 / .28 / .28 | .036 / .043 / .085 / .113 | 1.25 / 1.03 / **1.24** / .55 | 1.13 / 1.11 / .88 / 1.20 | .18 / .20 / .12 / .13 | .47 / .46 / .43 / .42 | 0 / 0 / **0** / .12 | .17 / .18 / .17 / .20 |
| K2 | Hokusai | 1.32 / 1.26 / **2.03** / 1.40 | .114 / .105 / **.058** / .075 | 1.41 / 1.36 / 1.50 / 1.36 | .21 / .16 / .27 / .37 | .27 / .39 / .32 / .40 | 0 / 0 / .085 / .152 | 1.18 / 1.59 / **1.32** / .35 | 1.38 / 1.37 / 1.03 / 1.48 | .19 / .32 / .17 / .16 | .37 / .47 / **.35** / .21 | 0 / 0 / .16 / .17 | .22 / .27 / **.11** / .10 |
| K3 | Ingres | 1.61 / 1.67 / 2.72 / 2.65 | .056 / .052 / .038 / .047 | 1.28 / 1.27 / 1.50 / 1.41 | .15 / .11 / .18 / .20 | .20 / .08 / .19 / .20 | .061 / .044 / .078 / .110 | 1.32 / 1.28 / **1.34** / .49 | 1.43 / 1.38 / 1.15 / 1.28 | .18 / .28 / .16 / .21 | .59 / .67 / .51 / .51 | .25 / .17 / .09 / .19 | .15 / .15 / .11 / .11 |

Turning correlation in test 1 is not in the key table. In the ablation (B1 →
B8): Matisse .57 → .56, Ingres .58 → .48. **tcorr did not improve.**

The T share is .149 / .205 / .105 against real .134 / .211 / .090: fine.

## 4. Test 1, relative to the floor

The run uses standard preprocessing, geometry only, 3 repeats, all drawings. The
v4 baseline is `grammar_v4_frozen` with its own crossing gains. The floor is real
strokes re-drawn from their own tokens.

| # | artist | **floor** | v5 learned | v5 − floor | v4 learned | v4 − floor | v5 no `rel_` | v5 tree | v4 tree |
|---|---|---|---|---|---|---|---|---|---|
| A1 | Matisse | .72 / .44 | **.85** / .94 | +.13 | .91 / .90 | +.19 | .86 | 1.0 | .99 |
| A2 | Hokusai | .46 / .41 | .85 / .86 | +.39 | .77 / .89 | +.31 | .83 | .96 | .97 |
| A3 | Ingres | .66 / .62 | .93 / .96 | +.27 | .89 / .92 | +.23 | .94 | 1.0 | 1.0 |

Top separating features for v5:

1. **Matisse:**
   - `cl_corner_rate` +1.5.
   - `len_q10` −1.3.
   - `cl_rate_line` +1.1.
2. **Hokusai:**
   - `len_q10` −1.3 (.114 → .058).
   - `rel_near_rate` +0.9.
   - Too many line pieces.
3. **Ingres:**
   - `cl_corner_rate` +1.5.
   - `cl_segs_per_stroke` +1.3.
   - Sharper extrema.

**Topology-only classifier** (`topology.FEATURES`, the topology study's
protocol), logreg / forest:

| # | artist | floor | v5 learned | v4 learned |
|---|---|---|---|---|
| T1 | Matisse | .67 / .20 | **.83 / .88** | .91 / .93 |
| T2 | Hokusai | .81 / .63 | **.89 / .94** | .97 / .96 |
| T3 | Ingres | .78 / .68 | .91 / .94 | .88 / .91 |

1. The top topology tells for v4 were `top_end_L` and `top_L_defl`. In v5 they
   are gone.
2. What separates v5 now:
   - T angle too wide (1.06–1.11 against .61–.91).
   - Near ends too aimed (.88–1.15 against 1.13–1.43).
   - Too few free ends (Matisse).
   - Too little parallel ink (Hokusai, d −1.2).
3. The topology floor (.67–.81) is itself well above 0.5. Even the identity
   re-draw changes the relations at the touch/near thresholds.

## 5. Memorisation (v4 protocol, n = 600)

Each cell is the share of strokes below the held-out 10th percentile. Healthy is
10 %.

| # | artist | strokes | chain (v4 protocol) | chain + kmatch | **as drawn by v5** | v4 chain |
|---|---|---|---|---|---|---|
| M1 | Matisse | ≥ 2 seg | 14 % | 15 % | **10 %** | 14 % |
| M2 | Matisse | ≥ 4 seg | 13 % | 14 % | **8 %** | 13 % |
| M3 | Hokusai | ≥ 2 seg | 20 % | 23 % | 20 % | 23 % |
| M4 | Hokusai | ≥ 4 seg | 17 % | 17 % | 15 % | 14 % |
| M5 | Ingres | ≥ 2 seg | 17 % | 20 % | **7 %** | 17 % |
| M6 | Ingres | ≥ 4 seg | 6 % | 3 % | 8 % | 8 % |

- **No regression.** The strokes actually drawn by v5 (steered, joined, cut at
  their ends) are at or below the held-out level, except Hokusai's short strokes
  (20 %), which were already there in v4.

## 6. The sheets, honestly

The sheets show `grammar-v5-matisse.jpg` and `grammar-v5-hokusai.jpg`. The
Ingres sheet was not kept: it is weak.

1. **Sharp joins are visible.** In the tree rows especially, lines meet at
   corners like the real ones. There are no more soft "continuation" bends where
   one line hands over to the next.
2. **Matisse.**
   - The tree row reads as connected cut-paper silhouettes and cell networks with
     angular junctions.
   - Learned #1 is a dud: an over-dense tangle of 142 short fragments at
     16 R of ink.
   - Learned #3 is a dud: almost empty, 1.1 R.
   - The single lines are still the best mode: long loops with bitten,
     jagged stretches.
3. **Hokusai** is *more angular than v4*: zig-zags of straight pieces with sharp
   turns. That is the corner regression (2.03), and it is visible. Double
   contours are rare.
4. **Ingres** (not kept): scattered short sticks and fragments. It reads least
   like a hand.
5. Overall, it still reads as fragments around a mass rather than a figure.
   There is no hatching anywhere.

Ready for Ian to look at. Nothing has been plotted.

## 7. Remaining gaps

1. **Line length.** Seeking ends and blocked near-starts shorten lines. Hokusai's
   `len_q10` is .058 against real .114. Next:
   - retry a near-start that is boxed in;
   - let an end plan fail over to "free" instead of cutting the line.
2. **Corners are unchanged overall.**
   - The budget works alone. The relations layer adds steering (steered share
     .30 → .40) and gives the gain back.
   - Next: budget 0.5 + look 2×, with the budget also applied during seeking.
3. **Double contours don't take.** Hokusai's parallel ink is .11 against real .22.
   The guide holds offset for only about 1–2 tokens; it needs more candidates or
   a dedicated offset-following mode.
4. **Near ends are too aimed** (end-seeking approaches ink head-on). Sample the
   approach angle from the learned aim.
5. **Kisses.** Hokusai still kisses, probably from near-starts running beside
   hosts. Ingres is unstable.
6. **Calibration is noisy.**
   - The per-drawing crossing count dominates the error. Knobs are now picked
     per term (`calibration.json`).
   - It ran before the last two changes (joins may now consume protected ends;
     seeking from 0.85). Re-run `calibrate` before trusting the shares to ±.02.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
sed 's/from \.\([a-z_]*\) import/from gesture.\1 import/' gesture/grammar_v4_frozen.py > /tmp/grammar_v4_base.py
$P -m experiments.grammar_eval calibrate                      # ~15 min (3 workers)
$P -m experiments.grammar_eval ablate --repeats 3 --max-real 14 --tag ablate_v5 \
   --only v4,kmatch,budget,budget05,look2,ends,ends_smooth,v5,v5_look2      # ~12 min
$P -m experiments.grammar_eval test1 --repeats 3 --baseline /tmp/grammar_v4_base.py   # ~15 min
$P -m experiments.grammar_eval memo --n 600
$P -m experiments.generate_demo                                # demo_v5/
```
