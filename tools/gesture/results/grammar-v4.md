# Grammar v4: where along-line texture comes from (2026-10-16)

v4 traced where the excess corners come from and fixed what that showed. It kept the
gaps that v3 had closed.
Files changed: `gesture/grammar.py`, `experiments/grammar_eval.py` (new `ablate`
subcommand, damped `calibrate`, `--baseline` / `--current-name`), and
`experiments/generate_demo.py`.
Raw outputs are in `.local/gesture/out/grammar_v2/`:
`ablate.md`, `ablate2.md`, `ablate3.md`, `test1.md`, `test1_key.md`,
`memo.md`, `cross_gain.json` and `demo_v4/`.
Sheets: `grammar-v4-matisse.jpg`, `grammar-v4-hokusai.jpg`, `grammar-v4-juxtaposition.jpg`.

**Verdict:**

- The excess corners do not come from how corners are represented. Real strokes
  re-drawn from their own sharp-corner tokens reproduce the real corner rate.
- The excess comes from two sources:
  1. **k-NN splicing** in the order-2 chain;
  2. **steering**, which picks turnier proposals when a line is blocked.
- v4 does two things about it:
  1. It follows the source stroke of the previous token, for runs of at most
     2 tokens.
  2. It steers by choosing the feasible proposal whose turning is closest to the
     chain's own wish.
- Test 1 moved only slightly, from 0.92 / 0.82 / 0.93 (v3) to **0.90 / 0.80 / 0.90**
  (v4, learned relations, logreg).
- Longer runs push AUC to 0.83–0.85 but **quote** training strokes. That is the
  trade-off this round exposed.
- **Floor found:** real drawings re-drawn through their own clothoid tokens already
  separate from the originals at AUC 0.64–0.73 (Hokusai 0.44). So test 1 cannot be
  expected to reach 0.5. About 0.65–0.7 is the pipeline's own floor.

## 1. Ablations

Each row is evaluated against real long-stroke subsets, one generated drawing per real
drawing, all three artists. The columns are panel medians and AUC (standard
preprocessing, geometry only, 3 repeats).

| # | set | Matisse corner rate (real 1.5) | Matisse turn_tcorr_10 (real .71) | Matisse AUC logreg / forest | Hokusai corner rate (real 1.32) | Hokusai AUC | Ingres corner rate (real 1.61) | Ingres turn_tcorr_10 (real .73) | Ingres AUC |
|---|---|---|---|---|---|---|---|---|---|
| B1 | **identity**, sharp corners (real strokes → own σ = 2 w tokens → re-drawn) | **1.48** | .71 | .73 / .37 | 1.26 | .44 / .32 | 1.67 | .73 | .64 / .58 |
| B2 | identity, corners rounded over 4 w | 1.82 | .70 | .65 / .32 | 1.77 | .50 | 1.69 | .71 | .67 |
| B3 | identity, rounded over 8 w | 1.89 | .68 | .72 / .45 | 1.91 | .77 | 2.04 | .69 | .72 |
| B4 | v3 (k-NN chain, first-feasible steering) | 3.18 | .46 | .92 / .92 | 1.55 | .83 | 2.64 | .42 | .93 |
| B5 | v3, **no avoidance** (chain's first proposal always) | 2.38 | .61 | 1.0 (overlaps) | 1.64 | .95 | 2.19 | .63 | 1.0 |
| B6 | v3, rounded corners 4 w | 3.01 | .49 | .95 | 1.96 | .78 | 2.47 | .51 | .96 |
| B7 | steer "plain" (when blocked, prefer non-corner) | 2.75 | .54 | .95 | 1.51 | .84 | 2.78 | .51 | .88 |
| B8 | steer "typical" (when blocked, turning closest to the chain's wish) | 2.67 | .53 | .93 | 1.58 | .88 | 2.53 | .46 | .95 |
| B9 | follow 0.8, unlimited runs | 2.39 | .62 | .86 / .88 | 1.40 | .79 | 2.29 | .57 | .85 |
| B10 | follow 0.9 + typical, unlimited runs | 2.05 | .62 | .87 / .91 | 1.39 | .72 | 2.02 | .65 | .84 |
| B11 | follow 0.9 + typical, runs ≤ 3 tokens | 2.49 | .57 | .93 / .89 | 1.27 | .77 | 2.12 | .60 | .85 |
| **B12** | **follow 0.9 + typical, runs ≤ 2 tokens (v4 default)** | 2.69 | .59 | .89 / .89 | 1.40 | .76 | 2.66 | .57 | .91 |

What the ablations show:

1. **(b) The corner representation is not the cause.**
   - Sharp-corner identity (B1) matches the real corner rate in all three hands.
   - Rounding makes it worse (B2, B3).
   - Generated corner tokens make up 29 % of chosen tokens for Matisse, the same as
     in the training data.
   - So "generate corners the way they are measured" already holds: the extractor
     plus the 2 w fit report real corners as corner tokens, and the panel counts
     them the same way.
   - Rounding was therefore not adopted. `corner_round_w` stays available, default 0.
2. **(a) Steering accounts for roughly half the Matisse/Ingres excess.**
   - Turning avoidance off (B5) cuts the corner rate from 3.18 to 2.38 and raises
     turn_tcorr from .46 to .61.
   - The chosen proposal is not the chain's first in 33–41 % of steps.
   - The steered choice is not more often a corner token: chosen corner share equals
     the first-proposal share (.29 vs .29). Instead, steering picks segments that
     turn harder, and the panel reads those as corners at 7 w.
   - "typical" steering removes some of this (B8 vs B4).
3. **(c) Splicing accounts for the rest.**
   - Even without avoidance (B5), the corner rate is 2.38 against identity's 1.48.
   - In v3, only 5 % of joints continue the same training stroke (`followed_share`);
     95 % are k-NN splices.
   - Following the source stroke (B9, B10) brings the corner rate to 2.0–2.4 and
     tcorr to .62–.65, and gives the best AUCs (.72–.87).
   - But see §4: unlimited runs quote training strokes.

## 2. Key features: real / v3 / v4 (learned relations, same run)

| # | artist | len_q10 | len_q50 | rel_touch | X / len | self-X | segs / stroke | corners / len |
|---|---|---|---|---|---|---|---|---|
| K1 | matisse | .065 / .048 / .047 | .124 / .111 / .104 | .15 / .25 / .24 | .24 / .26 / .28 | 0 / 0 / 0 | 1.42 / 1.68 / 1.58 | 1.5 / 3.02 / **2.71** |
| K2 | hokusai | .114 / .078 / .075 | .184 / .155 / .154 | .21 / .38 / .37 | .27 / .33 / .40 | 0 / 0 / 0 | 1.41 / 1.43 / 1.36 | 1.32 / 1.55 / **1.40** |
| K3 | ingres | .056 / .050 / .047 | .085 / .087 / .086 | .15 / .18 / .20 | .20 / .20 / .20 | 0 / 0 / 0 | 1.28 / 1.45 / 1.41 | 1.61 / 2.70 / 2.65 |

Turning correlation (`turn_tcorr_10`, real / v3 / v4): Matisse .71 / .46 / .56, Ingres .73 / .42 / .57.

## 3. Test 1: v2 → v3 → v4

Fair comparison: real drawings restricted to the long-stroke subset, standard
preprocessing, geometry only, 5 repeats.
- v2 numbers are from `grammar-v3.md`.
- v3 and v4 come from one run, with the v3 module loaded from commit `c808397`.
  Both use the same calibrated crossing gains.

| # | artist | v2 learned | v3 learned | **v4 learned** | v4 learned, no `rel_` | v3 tree | **v4 tree** | v4 tree, no `rel_` |
|---|---|---|---|---|---|---|---|---|
| A1 | matisse | .969 / .974 | .923 / .925 | **.902 / .897** | .917 / .902 | .999 / 1.0 | .995 / 1.0 | .918 / .922 |
| A2 | hokusai | .957 / .921 | .818 / .879 | **.796 / .908** | .789 / .866 | .983 / .998 | .986 / .995 | .936 / .929 |
| A3 | ingres | .993 / .991 | .931 / .928 | **.896 / .933** | .892 / .925 | 1.0 / 1.0 | 1.0 / 1.0 | .982 / .978 |

Run-to-run noise is about ±0.02–0.05: v3's Matisse number was .917 in its own run and
.923 here. **The v3 → v4 gain is about 0.02–0.035 AUC, which is within the noise.**

Top separating features for v4 learned (Cohen's d, generated − real):

1. **Matisse:**
   - `cl_corner_rate` +1.4.
   - `cl_rate_line` +1.2. This is new: too many straight pieces.
   - `len_q10` −1.0.
   - `turn_tcorr_10` −0.9.
2. **Hokusai:**
   - `cl_rate_clothoid` −1.3 and `cl_frac_arc` +0.8: clothoids come out as arcs.
   - `rel_touch_rate` +1.2.
   - `turn_net_ratio` −1.1.
3. **Ingres:**
   - `ext_turn_q50` +1.6 and `ext_h_q50` +1.0: sharper extrema.
   - `cl_corner_rate` +1.1.

## 4. Memorisation: why runs are capped at 2 tokens

The chain itself is measured here, using `generate_tokens` with v4 following and no
steering. Each cell shows the generated median, then the share of generated strokes
below the held-out 10th percentile (the healthy value is 10 %).

| # | artist | strokes | v3 (no follow) | follow 0.8, unlimited runs | follow 0.9, runs ≤ 3 | **v4: follow 0.9, runs ≤ 2** | held-out real |
|---|---|---|---|---|---|---|---|
| M1 | matisse | ≥ 2 seg | .256 / 9 % | .203 / **22 %** | .237 / 18 % | **.267 / 14 %** | .271 |
| M2 | matisse | ≥ 4 seg | .306 / 12 % | .259 / 20 % | .318 / 12 % | **.336 / 13 %** | .322 |
| M3 | hokusai | ≥ 2 seg | .324 / 23 % | .272 / **37 %** | .302 / 31 % | **.333 / 23 %** | .324 |
| M4 | hokusai | ≥ 4 seg | .423 / 19 % | .367 / 33 % | .423 / 24 % | **.452 / 14 %** | .423 |
| M5 | ingres | ≥ 2 seg | .260 / 9 % | .165 / **23 %** | .177 / 26 % | **.209 / 17 %** | .258 |
| M6 | ingres | ≥ 4 seg | .364 / 2 % | .291 / 15 % | .362 / 11 % | **.392 / 8 %** | .347 |

Reading:

1. Unlimited following **quotes**. Generated strokes become closer to training strokes
   than held-out real ones are (22–37 % below the held-out 10th percentile). That rules
   out the best-AUC settings.
2. With runs capped at 2 tokens, strokes with ≥ 4 segments are back at the held-out
   level. Short strokes with 2–3 segments are still somewhat close: 14–23 % below the
   10th percentile, against v3's 9–23 %. A 2-token run covers half of such a stroke.
3. Hokusai's tail improved on long strokes (19 % → 14 %), but not on short ones (23 %).
4. Jittered training copies (the quote floor) sit at 0.08–0.21; generated strokes are
   far from that.

## 5. Secondary items

1. **Crossing calibration:** 24 drawings per round, damped (√) updates, and the
   gain whose measurement came closest is kept. Gains: Matisse 0.89, Hokusai 0.52,
   Ingres 0.84.
   - The per-round measurements still swing (Matisse 0.16–0.34 at gains of 0.84–1.0).
     The crossing count per drawing is intrinsically noisy.
   - Result: Ingres is exact (.20). Matisse is 1.2 × real and Hokusai 1.5 × real.
2. **Single-line robustness:**
   - After a failure, the next chunk target is halved.
   - A line that is boxed in at its very start restarts somewhere else.
   - On the toy test hands, a hand-switching line can still stall before its first
     switch, so the test now asserts less (see weaknesses below). On the real corpus
     the juxtaposition sheet shows the switch.
3. Not addressed: `len_q10` (still 0.66–0.85 × real) and Hokusai touching (1.8 × real).

## 6. The sheets, honestly

1. **Single line** is still the best mode, and it got slightly smoother.
   - Matisse lines are long, loose loops with fewer kinks than in v3.
   - Hokusai lines are mazy and curly, with hooks.
   - One Matisse line is short (2.4 R) and one Hokusai line is small. Both are duds.
2. **Contiguous, learned relations** (row 1).
   - Lines are less jagged than v3 on Matisse: long arcs with small bites at the joints.
   - It still reads as fragmentary: many separate pieces near each other, like the real
     long-stroke subsets themselves.
   - Small clusters of wiggle are visible where lines were steered, mostly in
     Hokusai, which still looks jagged.
   - Duds: one sheet is very sparse (ink budget 1.7 R), one is dense and tangled
     (10 R).
3. **Contiguous, tree** (row 2) is more connected and organic: branching cells with
   some flat straight runs. Still not Oehlen-dense.
4. **Juxtaposition.**
   - Two of the three code-switch lines alternate hands visibly. One line is shorter
     than the others.
   - Restyling still works; translation still breaks the tree apart.
5. No hatching anywhere.

Ready for Ian to look at; nothing has been plotted.

## 7. Remaining gaps and next steps

1. **Splice texture:** at a run boundary, choose the k-NN neighbour whose token
   *before* matches the current token (a κ-matched join) instead of only matching
   context. Or penalise the joint κ jump against the training distribution of joint
   κ jumps. That would get some of follow's benefit (AUC .72–.87) without quoting.
2. **Steering bias:** plan further ahead, by growing two tokens at a time or with a
   longer look-ahead ray, so the chain's first proposal is blocked less often (now 33–41 %).
3. **Too many line segments in Matisse** and **too few clothoids in Hokusai**: check
   `_continuity` relabelling and the line jitter, which force κ to 0 at joints.
4. **Test-1 floor:** report AUC relative to the identity floor (0.64–0.73) from now on.
5. **Memorisation:** short strokes (2–3 segments) still lean toward quoting with
   runs of 2. Consider following only within strokes of ≥ 4 segments.
6. **Not addressed:** `len_q10`, Hokusai touching, crossing-count noise.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
$P -m experiments.grammar_eval prepare
$P -m experiments.grammar_eval ablate --repeats 3                    # ~3 min, incl. identity floors
$P -m experiments.grammar_eval ablate --repeats 3 --only run1_typical,run2_typical --tag ablate3
$P -m experiments.grammar_eval calibrate                             # ~1.5 min
git show c808397:tools/gesture/gesture/grammar.py | sed 's/from \.\([a-z]*\) import/from gesture.\1 import/' > /tmp/grammar_v3.py
$P -m experiments.grammar_eval test1 --baseline /tmp/grammar_v3.py --baseline-name v3   # ~10 min
$P -m experiments.grammar_eval memo --n 600
$P -m experiments.generate_demo                                      # demo_v4/
```
