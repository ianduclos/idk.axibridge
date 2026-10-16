# Chain fix: one continuous line that keeps the structure and the hand (2026-10-16, night)

Follows `composite-2026-10-16.md`. There, `chain="before"` meant chaining the
skeleton into one line and then letting the hand redraw it. It was a dud: the
line ballooned at every out-and-back. This round finds where the balloons come
from, ablates five fixes, measures the single line with the panel, and writes the
first plot candidates as SVG.

Code:
- `experiments/composite.py`: `chain_paths` gains `walk="min_turn"`, `connect`,
  `max_paths`, and per-piece bookkeeping. Also new: `restyle_chain`,
  `offset_return`, `to_mm` / `to_svg` / `plot_stats` / `read_svg_paths`, and
  `composite(..., pin=, retrace=, walk=, connect=, max_paths=)`.
- `gesture/restyle.py`: `restyle_points(max_sigma=)`.
- `experiments/chain_study.py`: `ablation`, `sheets`, `plot`.
- Tests: 8 new in `tests/test_composite.py`, 1 in `tests/test_restyle.py`.

Raw outputs: `.local/gesture/out/composite_chain/` (`ablation.md/json`,
`rows.jsonl`, `diag.json`, `sheets/big-*.jpg`). Plot candidates:
`.local/gesture/out/plot_candidates/`.
Committed sheets: `composite-chain-trees.jpg`, `composite-chain-torso.jpg`,
`composite-chain-variants.jpg`.

**Verdict.**

- **The balloons are fixed.** The recipe is `chain="before", pin="turns",
  retrace="offset", walk="min_turn"` (with the default per-run σ cap). On 30 trees
  × 2 hands:
  - balloons per drawing drop from **7.2 to 1.3**. Chaining the restyled lines
    afterwards scores 1.6, and restyle alone 0.8;
  - mean distance to the skeleton drops from **0.0145 R to 0.0086 R**, better than
    restyle itself (0.0100);
  - the worst junction gap drops from 0.037 R to 0.015 R (median 0.0004 R).
  - It costs 0.4 s per drawing.
- **The hand survives, but only if the panel measures the line between hairpins.**
  - Measured as drawn, every single-line version, including plain `chain="after"`
    (the restyle's own geometry), falls to chance or below: a 20 000-point stroke
    with 50 % exact out-and-backs is outside the panel's domain.
  - Cut at hairpins, the fixed line separates Matisse from Hokusai at **0.73–0.83**
    (p ≤ .008). Chain-after scores 0.80 and restyle alone 0.87. The unpinned line
    scores 0.63 (n.s.).
- **The single line sits where `chain="after"` sits on the M–H panel axis.** The
  median logit is +1.8 / +1.2 (M hand / H hand) against +1.9 / +1.1. The ballooned
  line collapses to −0.0 / −0.3, so its two hands look alike, as round 3 saw by eye.
- **On paper the fixed line reads as a tree drawn in one line, with doubled twigs.**
  Plot candidates are below, unplotted.

## 1. Diagnosis: where the balloons come from, and why

Source: `diag.json`, 30 medium/simple/complex trees × 2 hands, amount 0.7,
σ_s = 0.070 R.

1. **Size.** The median balloon diameter is **0.073 R, which is σ_s**. The retraced
   pieces (twigs walked out and back) have a median length of **0.089 R = 1.3 σ_s**
   (q25–q75: 0.055–0.116 R).
   - Unpinned, the whole out-and-back lies inside one Gaussian window of the θ
     low-pass. The π reversal becomes a smooth π turn spread over ±2 σ_s: a loop
     about σ_s across.
   - `unwrap` picks the turning direction arbitrarily, so loops go either way.
   - The pins (every 2 σ_s = 0.14 R) are sparser than the twigs, so they cannot
     hold the tip.
2. **Where the loops close.** The crossing point of a balloon sits at the nearest
   node passage:

   | site | count |
   |---|---|
   | gentle junction passages | 147 |
   | sharp turns (≥ 60°) | 43 |
   | reversal tips | 45 |
   | run interior | 14 |

   - Most balloons close at the **base** of the twig, where the out and back
     passes cross, not at its tip.
   - A walk turns sharply in 1100 of 4310 node passages, and each of those is also
     rounded at σ_s.
3. **Why pinning only the tips is not enough** (the ablation below confirms each
   step):
   - Pinning the reversals still leaves runs that cross sharp junction turns, and
     those round off.
   - Pinning the turns too leaves short runs (a twig between two anchors, shorter
     than 2 σ_s). They get only their two end pins. The hand wanders, and
     `_align_intervals` stretches its steps up to 1.6⁴ = 6.6×, which makes a
     needle or loop.
     - **The same mechanism makes the wild hooks and needles at twig tips in plain
       restyle** (round 3's "duds"). That is why the σ cap also improves restyle's
       own fidelity.
   - Even with all of that, `retrace="redraw"` draws the back pass with a fresh,
     independent hand. The two passes cross and enclose small off-structure loops.
4. **The hand's chain refusing a hairpin** plays no part. `trace` never has to
   draw the hairpin: the reversal sits in the base path, and that base path is
   already ballooned before the hand traces it.

## 2. Fixes

All the fixes go through `restyle_chain`. It cuts the chained skeleton at
**anchors** and restyles each run between anchors on its own. Each run's ends are
then moved exactly onto its anchors (a cosine fade, the weld rule at both ends),
and the runs are welded end to end. The result is still one line, with a hard
corner at each anchor.

| # | fix | what it does |
|---|---|---|
| a | `pin="tips"` / `"turns"` / `"nodes"` | Anchors at reversals (a piece walked straight back, or a turn ≥ 150°), plus node turns ≥ `pin_angle` (60°). Also `max_sigma`: σ_s of each run ≤ run length / 3 (`RUN_SIGMAS`), so short runs get interior pins. |
| b | `retrace="exact"` / `"offset"` | The second pass reuses the first pass's drawn geometry, reversed. `offset` puts it `offset_w` = 1.5 line widths to the left of the return direction, tapering in and out over 4·offset (`offset_return`): a narrow hairpin at the tip and a clean rejoin at the junction. |
| c | `walk="min_turn"` | A Fleury walk: never take a bridge while another edge is left, and otherwise continue with the smallest turn at every node. |
| d | `max_paths` | At most k pen paths. More trails go to the largest component, and once every odd node has its own end there is no retrace. With `connect`, only as many connectors as the budget needs are added. |
| e | `model="lognormal"` | Unchanged adapter (`trace_ln`) for each run. |

Also new: `connect=True` joins loose components with straight connectors
(a minimum spanning tree over the closest node pairs), so the torso, 12 loose
contours, can be one line.

## 3. Ablation

Setup: 30 Oehlen trees (the round-3 pairwise structures), Matisse and Hokusai
hands, amount 0.7, seed 1. Values are medians over tree × hand.

- **Balloons**: the mean count of round loops (equivalent diameter 0.02–0.25 R,
  isoperimetric quotient ≥ .25), counting only loops whose boundary lies at least
  30 % farther than 0.02 R from the structure.
- **Loops**: all round loops, including the real cells a single line closes
  through crossing branches.
- **Retrace**: the doubled share of the structure's ink.
- **Torso**: Matisse KKS1971-302, with `connect=True`.

| # | condition | balloons (loops) | d_mean/R | d95/R | cover95/R | junction gap max/R | retrace | paths | s | torso balloons M/H |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | restyle only (round 3, not chained) | 0.8 (1.3) | .0100 | .034 | .020 | .0227 | 0 % | 40 | 0.3 | 1/1 |
| A2 | chain after restyle, exact retrace | 1.6 (4.2) | .0097 | .032 | .020 | .0227 | 49 % | 1 | 0.4 | 1/2 |
| A3 | chain after, ≤ 8 paths | 1.2 (3.3) | .0097 | .032 | .020 | .0227 | 19 % | 8 | 0.4 | 1/1 |
| A4 | **before, unpinned (round 3's dud)** | **7.2** (16.1) | .0145 | .044 | .029 | .0369 | 54 % | 1 | 1.3 | 3/4 |
| A5 | (a) pin reversals only | 6.0 (16.9) | .0128 | .041 | .021 | .0286 | 54 % | 1 | 0.5 | 3/2 |
| A6 | (a) + node turns ≥ 60° | 4.0 (15.0) | .0105 | .034 | .016 | .0142 | 54 % | 1 | 0.5 | 2/3 |
| A7 | (a) + σ cap | 2.9 (14.1) | .0085 | .030 | .014 | .0142 | 54 % | 1 | 0.6 | 1/2 |
| A8 | (a) + cap + exact returns | 1.4 (4.3) | .0084 | .030 | .017 | .0161 | 54 % | 1 | 0.4 | 0/0 |
| A9 | (a) + cap + offset returns (b) | 1.4 (4.6) | .0086 | .030 | .016 | .0154 | 54 % | 1 | 0.4 | 0/0 |
| A10 | (c) min-turn walk alone | 6.9 (15.8) | .0145 | .043 | .028 | .0362 | 54 % | 1 | 1.4 | 7/9 |
| A11 | **full: (c) + (b) + (a)** | **1.3** (4.6) | **.0086** | .029 | .017 | .0150 | 54 % | **1** | 0.4 | 0/1 |
| A12 | (d) full, ≤ 8 paths | 1.4 (3.8) | .0078 | .028 | .016 | .0090 | 22 % | 8 | 0.4 | 1/1 |
| A13 | (e) lognormal, unpinned | 8.6 (17.7) | .0159 | .047 | .028 | .0356 | 54 % | 1 | 3.1 | 5/4 |
| A14 | (e) lognormal, full fix | 0.3 (1.3) | .0041 | .013 | .009 | .0109 | 54 % | 1 | 1.6 | 1/0 |

Reading:

1. **Every step of (a) helps, and the return pass finishes the job.**
   - Balloons fall in steps: 7.2 (none) → 6.0 (tips) → 4.0 (turns) → 2.9 (cap)
     → 1.4 (exact or offset returns).
   - That is A2's level: the chained-after restyle has the same 1–2 hand loops.
   - Exact and offset returns tie on every measure.
2. **(c) The min-turn walk does nothing alone** (A10 ≈ A4). In the full recipe it
   changes neither balloons nor tree fidelity, but it helps on the torso: cover95
   .023 / .027 against .028 / .036 for A9.
   - It is kept because it makes the line continue the way a hand would: fewer
     forced corners at junctions.
   - This is not proven to matter on trees.
3. **(d) Eight paths instead of one** cut the retrace from 54 % to 22 %. They also
   tighten the junctions (max gap .009 against .015). Balloons stay the same.
4. **(e) The lognormal hand with the full fix is the most faithful single line**
   (d_mean .0041 R, 0.3 balloons). It also has no hand (§4), as in round 3.
   Unpinned, it balloons like the grammar: its pulses blend turns, but the base
   path it traces is already ballooned.
5. **Fidelity beats plain restyle** (.0086 against .0100) because of the per-run σ
   cap. Applying the cap to `restyle_drawing` for short strokes is an obvious
   follow-up. It was not done here, so as not to move round 3's numbers.

## 4. Pairwise hand test (Matisse vs Hokusai, same structure)

**Classifier.** Logistic regression on the texture features of **real** drawings.
- It uses the groups k, ext, infl and turn. The **cl group is dropped**: its
  clothoid fit took 160 s and more on one 21 000-point line.
- Calibration without cl: CV 0.81, real held-out pairwise 0.85. With cl, the
  figures are 0.76 / 0.85, so nothing is lost.
- Panel position is the median logit; > 0 is the Matisse side. Real Matisse sits at
  +1.54 and real Hokusai at −0.99.
- n = 30 trees per cell.

| # | condition | as drawn: acc (p) | logit M / H | **between hairpins**: acc (p) | logit M / H |
|---|---|---|---|---|---|
| H1 | restyle only | .80 (.001) | +2.6 / +1.3 | .87 (<.001) | +2.5 / +1.5 |
| H2 | chain after | .40 (.90) | −12.5 / −5.5 | .80 (.001) | +1.9 / +1.1 |
| H3 | chain after, ≤ 8 paths | .73 (.008) | −0.0 / −10.8 | .83 (<.001) | +2.0 / +1.1 |
| H4 | before, unpinned | .67 (.049) | −0.1 / −0.9 | .63 (.10) | −0.0 / −0.3 |
| H5 | pin tips | .63 (.10) | −1.6 / −1.7 | .70 (.021) | +0.3 / −0.2 |
| H6 | pin turns | .53 | −2.7 / −2.5 | .80 (.001) | +1.3 / +0.3 |
| H7 | + σ cap | .63 | −2.2 / −3.4 | .67 (.049) | +1.4 / +0.8 |
| H8 | + exact returns | .57 | −2.8 / −13.0 | .73 (.008) | +1.8 / +1.3 |
| H9 | + offset returns | .40 | −4.5 / −4.1 | **.83** (<.001) | +2.0 / +1.0 |
| H10 | min-turn walk alone | .70 (.021) | −0.2 / −0.5 | .57 | −0.2 / −0.7 |
| H11 | **full** | .47 | −4.3 / −3.6 | **.73** (.008) | +1.8 / +1.2 |
| H12 | full, ≤ 8 paths | .27 | −3.9 / −3.0 | .73 (.008) | +2.3 / +1.2 |
| H13 | lognormal, unpinned | .73 (.008) | −0.6 / −1.7 | .57 | −0.6 / −0.8 |
| H14 | lognormal, full fix | .03 | −3.9 / −2.6 | .57 | +2.5 / +2.5 |

1. **The panel cannot read a single line as drawn.**
   - H2 has exactly H1's geometry, only chained. It drops from .80 to .40, with
     logits around −12.
   - The exact out-and-backs and the 20 000-point stroke push k, ext and turn far
     outside anything real, and the classifier then extrapolates arbitrarily.
   - Any "as drawn" number for a single line is an artefact. **This also applies to
     round 3's `chain_paths` drawings**, but round 3's pairwise ran on unchained
     restyles, so its numbers stand.
2. **Cut at hairpins** (one rule for every condition: a turn > 120° over ±0.01 R),
   the lines come back into the panel's domain. Strokes after the cut: about 60 for
   the fixed line, 48 for restyle, 6 for the ballooned line.
   - Offset returns score .83 and the full recipe .73, against .80 for chain-after.
     These differences are 1–3 trees out of 30: noise.
   - **The fix keeps the hand.** The ballooned line (.63, logits near 0) and the
     min-turn walk alone (.57) lose it.
3. **Panel position.** Fixed single lines sit where chain-after sits (+1.8 / +1.2
   against +1.9 / +1.1).
   - Both hands land on the Matisse side of the real midpoint. Restyle orders the
     two hands; it does not place Hokusai's hand at Hokusai's position. This is
     known from round 3: the structure's smoothness is Matisse-like.
   - The ballooned line sits at the midpoint for both hands.
4. **The lognormal hand plus the fix is the cleanest line and no hand** (.57,
   +2.5 / +2.5).

## 5. Sheets, honestly

**`composite-chain-trees.jpg`**

- Layout: rows simple / medium / complex. Columns: skeleton, then for Matisse and
  for Hokusai, three versions each: before (raw) | fixed, 1 line | fixed,
  ≤ 8 paths.
- **Raw:** loops everywhere. The tree is gone, and the two hands are hard to tell
  apart.
- **Fixed, Matisse:** reads as the tree in every row. Every twig is a doubled
  stroke ending in a narrow hairpin. At 400 px the double reads as a thicker,
  slightly stuttering line; at 1200 px (`plot_candidates/*.jpg`) it is visibly two
  passes 1.5 w apart, like a contour gone over twice.
  - There are a few wild hooks and curls at twig tips: fewer than in round 3, but
    not none.
- **Fixed, Hokusai:** recognisably the tree, but much rougher.
  - Square notches, polygonal knots, a few round loops (2 counted on simple, 1 on
    complex), and some long straight chords where a trunk run came out as a
    straight-ish segment.
  - In the medium tree the lower half drifts. Big arcs and a triangular knot
    replace the lower branches (d_mean .0117 R against Matisse's .0066 R on that
    tree).
  - By eye the two hands differ clearly: Matisse is a nervous staircase with calm
    trunks, Hokusai is notched, knotted and loopier.
  - Awkward but alive. The complex Hokusai tree verges on a cell network again, as
    in round 3.
- **≤ 8 paths:** looks almost the same, with less doubling. The two hands become
  easier to tell apart because fewer doubles dominate.

**`composite-chain-torso.jpg`**

- **Matisse hand, 1 line:** keeps the figure: shoulder, breast, belly and the arm
  across. The hip region gets dense and heavy where the offset returns double
  short contours, and there is one hand balloon near the hand.
- **Hokusai hand, 1 line:** the figure is there, but the 11 connectors (0.44 R in
  total, 11 % of the ink) are redrawn by the hand.
  - One of them becomes a big S-shaped swing left of the chest, and one a lens at
    the right shoulder.
  - That is the connector being redrawn as a free line, not a balloon. It is
    honest about being one line, and it does not belong to Matisse's figure.
- **Hokusai hand, ≤ 8 paths:** grows a large arc over the head from a single
  hand-redrawn connector. It is the worst torso cell.
- **Raw:** loopy.
- **Next fix:** draw connectors straight, or as gentle arcs, outside the hand.

**`composite-chain-variants.jpg`** (medium tree, each fix in turn)

- **Tips, turns and turns+cap** (redraw returns): the doubled passes cross each
  other. The Hokusai row becomes a nervous mesh of crossing double strokes. As an
  image it has an Oehlen-like all-over energy, but it is not the tree.
- **Exact:** the cleanest thin tree. The retraces are invisible, and the image is
  essentially the restyle.
- **Full (offset):** the doubled-twig tree.
- **Lognormal full:** a clean doubled tree, nearly identical in both hands.

## 6. Plot candidates (not plotted)

Files are in `.local/gesture/out/plot_candidates/`: SVG plus a 1200 px JPEG
preview each, and `candidates.json`.
- Paper: A4 landscape, 297 × 210 mm, 10 mm margin, fitted and centred.
- One `<path>` per pen path, in pen order, stroke 0.4 mm, simplified at 0.02 mm.
- All three use the full recipe at amount 0.7, no tremor.
- **Time** is nominal: (pen-down + pen-up travel) / 25 mm/s + 0.5 s per pen
  cycle. Pen-up travel runs home → start → home.

| # | file | structure / hand | paths (lifts) | pen-down | pen-up | est. time | balloons | d_mean/R | junction gap max/R | retrace |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `tree-medium-matisse-1line.svg` | medium Oehlen tree (seed 101, round-3 sheet tree), Matisse | 1 (0) | 3.30 m | 0.51 m | 2.6 min | 0 | .0066 | .0010 | 64 % |
| 2 | `tree-medium-hokusai-1line.svg` | same tree, Hokusai | 1 (0) | 3.87 m | 0.52 m | 2.9 min | 0 | .0117 | .0012 | 64 % |
| 3 | `torso-hokusai-1line.svg` | Matisse KKS1971-302 torso, Hokusai, 11 connectors | 1 (0) | 1.74 m | 0.25 m | 1.3 min | 3 | .0168 | .0055 | 46 % |

**Notes for the machine:**

1. **Offset gap on paper.** On this paper R ≈ 270 mm, so the offset return sits
   0.62 mm (Matisse, 1.5 × w = 0.0015 R) or 1.16 mm (Hokusai, w = 0.0029 R) beside
   the outward pass.
   - With a 0.4 mm pen, that is a visible double line with a hairline gap
     (Matisse) or a clear gap (Hokusai).
   - With a broad pen the Matisse double fuses into one thicker stroke.
2. **Tree in the composite.** The 2.6–2.9 min estimate is far shorter than any
   machine limit.
3. **About two thirds of the pen-down length is a second pass.** That is the price
   of one line through a tree.
4. **≤ 8-path version.** Not written as a candidate, but it is one call:
   `dict(FULL, max_paths=8)`. It roughly halves the doubling, if the first plot
   looks over-inked.
5. **Torso.** Candidate 3 carries the awkward connector swing described in §5. If
   it looks wrong, the Matisse-hand torso (sheet, middle row) is cleaner.
6. **Order.** Ian's approval is needed for any motion. Suggested order: 1 and 2
   side by side (the pairwise test on paper), then 3.

## 7. Tests

`tests/test_composite.py` adds 8 tests (17 in the file, about 4.5 s):
1. Pinned reversals are exact anchors with a turn > 120°, both for tips and for
   turns. Every anchor lies on the skeleton, and the unpinned line misses the tip.
2. `offset_return` keeps its distance within ±0.5 px of the requested 3 px, and its
   ends coincide with the input's.
3. The return pass in `restyle_chain`: exact stays ≤ 0.05 w from the outward pass;
   offset stays at 0.75–2.25 w with offset_w = 1.5.
4. `restyle_chain` and `composite(chain="before", …)` are deterministic and pure.
5. The min-turn walk covers the same ink with the same retrace, and its turns are
   no larger than the default walk's. `connect` gives one path across a 30 px gap,
   and `max_paths=2` keeps two paths.
6. SVG round-trip: path count, bounds inside the margins, pen order, and pen-down
   length.

`tests/test_restyle.py` adds `max_sigma` (σ capped, more pins, finite output).

**Full gesture suite: 252 passed in 24 s.**

## Weaknesses and next steps

1. **Connectors** go through the hand (torso swing). Give them their own rule:
   straight, or a gentle arc, outside the hand.
2. **The σ cap on plain `restyle_drawing`** would likely remove its twig-tip
   needles too. One flag (`max_sigma = length / 3` per stroke); not applied, so as
   not to move round 3's numbers.
3. **The single line is out of the panel's domain as drawn.** "Between hairpins"
   is a reasonable reading, but it is a choice. The cl group is skipped for speed.
   A per-run clothoid fit would restore it.
4. **Pairwise n = 30, one seed.** Offset (.83) against full (.73) is noise-level.
5. **Retrace geometry is one choice.** The offset is always left of the return
   direction at 1.5 w. A side that avoids other ink, or an offset that varies with
   the hand's own line width, are cheap variants. Tremor is not applied: that
   module is being rewritten.
6. **The min-turn walk's value on trees is unmeasured.** It shows up only on the
   torso.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
$P -m experiments.chain_study ablation --n-tree 30   # ~5 min, 3 workers, resumable (rows.jsonl)
$P -m experiments.chain_study sheets                 # ~2 min
$P -m experiments.chain_study plot                   # SVG candidates → .local/gesture/out/plot_candidates/
$P -m pytest -q tests/test_composite.py tests/test_restyle.py
```
