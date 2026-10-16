# The composite pipeline and the pairwise hand test (2026-10-16, evening)

Structure → hand → single line → tremor, and the test restyle needed all along:
same structure, two hands, which one is A?
Code: `experiments/composite.py` (pipeline + `pairwise`, `judge`, `sheets`, `bench`),
`gesture/restyle.py` (re-pointed to the FROZEN v4 grammar; junction welding;
per-stroke scale; lognormal trace), `experiments/restyle_study.py` (`delta`),
`tests/test_composite.py` (10 tests, ~3 s).
Raw outputs: `.local/gesture/out/composite/` (`pairwise*.md/json`, `bench.json`,
`sheets/` incl. 1200 px single renders `big-*.jpg`), `.local/gesture/out/restyle/delta_v4*.md`.
Committed sheets: `composite-trees.jpg`, `composite-trees-chained.jpg`,
`composite-translation.jpg`, `composite-models.jpg`.

**Verdict.**

- **On matched structure the hands are separable by the panel.** The
  old absolute 3-way test scored restyle at chance. Pairwise, with a classifier
  trained only on real drawings of A vs B, it picks the right hand:
  - Matisse vs Hokusai: **0.75** (40 structures, p = .001), trees 0.85–0.90.
  - Hokusai vs Ingres: **0.90**.
  - Matisse vs Ingres: at chance. That pair is also the weakest pair on real
    drawings (held-out pairwise 0.75).
- **The kinematic (lognormal) hand is a faithful tracer, not a hand.** It keeps the
  structure almost exactly, and pairwise it sits at chance.
- **Welding works.** Every tree junction stays closed after restyle. Max gap
  ≤ 0.0006 R, against 0.04 R before.
- **Single line through the structure** is solved as a graph problem
  (exact open Chinese postman). Trees need 47–65 % retrace to be one line.
  `max_retrace` trades the retrace for a few pen lifts.
- **Bring to paper first:** a medium/complex Oehlen tree in the Hokusai or
  Matisse hand, amount 0.7, chained *after* restyle with `max_retrace≈0.15`.
  Details in §6.

## 1. Restyle on v4: what carried over

- `restyle.py` now imports `grammar_v4_frozen` and the v4 grammars in
  `.local/gesture/out/grammar_v4_frozen/`.
- The v4 learned transitions are the v3 ones. v4's changes are in generation:
  1. source-stroke runs (`P_FOLLOW` 0.9, runs ≤ 2 tokens);
  2. "typical" steering in `_Grower`.
- `trace` has its own selection rule (closest to the path), so the only v4
  feature that reaches restyle is the runs. The ablation shows it is a trade-off
  (`delta_v4.md` with runs, `delta_v4_nofollow.md` without):

| # | trace @ amount | grammar | d_mean/R | corner rate | k_q50 | turn_tcorr_10 | s / drawing |
|---|---|---|---|---|---|---|---|
| D1 | 0.4 | v3 | .0026 | 3.25 | 7.3 | .62 | 2.5 |
| D2 | 0.4 | v4, runs on | .0038 | 3.98 | 10.5 | .52 | 0.6 |
| D3 | 0.4 | v4, runs off | .0026 | 3.23 | 7.3 | .62 | 0.7 |
| D4 | 0.6 | v3 | .0056 | 3.14 | 7.5 | .56 | 1.7 |
| D5 | 0.6 | v4, runs on | .0092 | 3.97 | 10.7 | .46 | 0.5 |
| D6 | 0.6 | v4, runs off | .0060 | 3.23 | 7.6 | .56 | 0.7 |
| D7 | 0.8 | v3 | .0111 | 4.00 | 8.2 | .56 | 1.0 |
| D8 | 0.8 | v4, runs on | .0150 | 4.00 | 9.8 | .42 | 0.4 |
| D9 | 0.8 | v4, runs off | .0111 | 4.07 | 8.0 | .56 | 0.5 |

Real values: corner rate 1.50 / 1.32 / 1.61 and turn_tcorr_10 .71 / .46 / .73
(M / H / I).
The table shows medians over 5 sources (tree, dense, primitives, Matisse KKS1971-302,
Hokusai 57262) and 3 hands, gauss decomposition.

1. **v4's corner improvements do not carry over.**
   - With runs off, v4 restyle is v3, to the second decimal.
   - With runs on, corners go *up* (3.2 → 4.0) and κ goes up. Inside trace the k
     proposals become near-copies of the followed token, so the closest one is
     a worse fit and the pin correction bends harder.
   - Runs are 2–3× faster, because the follow draw skips the k-NN query.
2. **But runs carry more of the hand.** The pairwise test (§3) gives:

   | # | pair | runs on, 0.5 / 0.8 | runs off, 0.5 / 0.8 |
   |---|---|---|---|
   | R1 | Matisse vs Hokusai | 0.75 / 0.75 | 0.45 / 0.80 |
   | R2 | Hokusai vs Ingres | 0.90 / 0.90 | 0.40 / 0.80 |

   - Default: **`TRACE_FOLLOW = True`**, because hand identity is the point of
     translation.
   - The corner excess (≈ 2.5× real) is the known grammar gap either way.
3. **Junction pin** (restyle next step 6) is done:
   - `restyle_drawing(weld=True)` is the default.
   - An open source end within 0.006 R of another stroke is a junction.
   - After restyle it moves onto the restyled host at the same structural
     position: the host sample index ↔ source arc fraction, then the nearest
     host point within ±σ_s.
   - The move has a cosine fade over 2 σ_s, at most half the stroke.
   - Hosts are welded before their dependents, and cycles are welded last.
   - Junction gap: 0.0004–0.0013 R, against 0.04 R unwelded on a 42-stroke tree
     at 0.8.
4. **Per-stroke σ_s** (restyle next step 4) is `scale="stroke"`.
   - σ_s = sigma_of(amount) · min(R, 2 ℓ), where ℓ = length per quarter-turn of
     the stroke smoothed at 0.01 R.
   - Implemented and runs. It was **not evaluated on a grid**: there was no time.
     The default stays `"drawing"`.
5. **Lognormal adapter.** `source="trace_ln"` takes a `lognormal.Hand`. It grows
   pulse by pulse from the hand's chain, keeping the proposal whose
   re-integrated window stays closest to the path. Then the same pin fit runs.
   It costs 1–5 s per drawing, 5–10× trace.

## 2. The composite pipeline

`composite(structure, hand, rng, *, size, amount, chain=False, tremor=None, model="grammar")`:

1. **Structure** (0.05–0.3 s): `topology.generate_structure`. Options:
   - `"oehlen_tree"` with complexity params (`TREE_LEVELS`: simple = depth 3 /
     1 trunk / fill 0.6; medium = 4 / 2 / 0.8; complex = 5 / 3 / 0.92);
   - `"learned"` with the hand's own TopologyModel;
   - any `Drawing`, for example `real_structure(art, stem)`, the long strokes of a
     real drawing.
2. **Hand** (0.2–1.7 s): `restyle_drawing`, gauss/trace, frozen v4, welded.
   `model="lognormal"` uses `trace_ln` instead (1–6.5 s).
3. **Chain** (0.01–1.2 s), in `chain_paths`:
   - Junction ends split their host. X crossings become nodes only with
     `at_crossings`.
   - Per component, odd nodes are paired by an exact open-Chinese-postman matching:
     two free virtual ends let the matching choose where the line starts and ends.
     A test checks that a T retraces exactly its shortest arm.
   - Matched shortest paths are duplicated, then an Euler path is walked.
   - `max_retrace` adds pen paths (2 more virtual ends each) until the retrace
     falls under budget.
   - `chain=True`/`"after"` chains the restyled geometry. The retraces are
     exact, so the image is unchanged and only the pen path changes.
   - `chain="before"` chains the skeleton and lets the hand redraw the one long
     line.
4. **Tremor** (optional, about 0.03 s): another agent's `gesture.tremor.apply_tremor`,
   with the model from `out/tremor/models/{hand}.json` and w = the hand's own w/R × R.
   It is wired and smoke-run. It is not on the sheets, because that module is
   still in flux.

**Cost per drawing.** Grammar hand: 0.3–2 s in total (median about 0.6 s).
Lognormal hand: 1–7 s. All of it is pure numpy/scipy/networkx.

**Retrace.** A single line (`bench.json`) costs this much:

| # | structure | single-line retrace (share of ink) |
|---|---|---|
| T1 | simple tree | 62–65 % |
| T2 | medium tree | 47–57 % |
| T3 | complex tree | 48–51 % (complex trees are sometimes 2 components → 2 paths) |
| T4 | learned topology | 15–25 %, but 7–21 paths: free-floating lines |

The trade on a medium tree:

| # | max_retrace | paths | retrace |
|---|---|---|---|
| M1 | none | 1 | 46 % |
| M2 | 0.3 | 4 | 27 % |
| M3 | 0.15 | 8 | 15 % |
| M4 | 0 | 26 | 0 % |

## 3. Pairwise hand test (panel)

**Setup.**

- 40 structures: 20 Oehlen trees over the complexity grid and 20 learned
  topologies, rotating M/H/I models.
- Each structure is restyled into every hand at amounts 0.5 and 0.8 (seed 1),
  then measured at one common line width (the σ/w confound is removed).
- For each pair (A, B), logistic regression is trained on texture features
  (k, ext, infl, turn, cl; 51 features) of the **real** long-stroke drawings of A
  and B only. Standard preprocessing applies (σ ≥ 7 w, medium projection).
- A trial is correct when P_A(restyle→A) > P_A(restyle→B) on the same structure.
  Chance is 0.5; p is one-sided binomial. Full table: `out/composite/pairwise.md`.

| # | pair | model | amount | all (n = 40) | trees (20) | learned (20) |
|---|---|---|---|---|---|---|
| P1 | Matisse vs Hokusai | grammar | 0.5 | **0.75** (p .001) | 0.85 | 0.65 |
| P2 | Matisse vs Hokusai | grammar | 0.8 | **0.75** (p .001) | 0.90 | 0.60 |
| P3 | Matisse vs Ingres | grammar | 0.5 | 0.50 | 0.45 | 0.55 |
| P4 | Matisse vs Ingres | grammar | 0.8 | 0.55 | 0.50 | 0.60 |
| P5 | Hokusai vs Ingres | grammar | 0.5 | **0.90** (p < .001) | 1.00 | 0.80 |
| P6 | Hokusai vs Ingres | grammar | 0.8 | **0.90** (p < .001) | 0.90 | 0.90 |
| P7 | Matisse vs Hokusai | lognormal | 0.5 / 0.8 | 0.40 / 0.57 | | |
| P8 | Matisse vs Ingres | lognormal | 0.5 / 0.8 | 0.57 / 0.42 | | |
| P9 | Hokusai vs Ingres | lognormal | 0.5 / 0.8 | 0.45 / 0.70 | | |

Calibration and ceilings (the same classifiers):

| # | pair | real CV acc | real held-out pairwise (real A vs real B) | grammar v4's own drawings, pairwise |
|---|---|---|---|---|
| C1 | Matisse vs Hokusai | .76 | .85 | .75 |
| C2 | Matisse vs Ingres | .69 | .75 | .88 |
| C3 | Hokusai vs Ingres | .95 | .99 | .94 |

The same hand twice is 0.5 by construction for the panel.

Reading:

1. **Restyle carries a measurable hand on matched structure.** For M–H and H–I,
   restyle reaches the grammar's own pairwise level (.75 / .90 against .75 / .94):
   translation loses little of what the grammar has.
   - The absolute test in `restyle-2026-10-16.md` asked for more than this
     instrument can give.
   - The median P_A margins are small: +0.07 to +0.4. The classifier is ordering
     the pair, not confident about either drawing.
2. **Matisse vs Ingres fails.** It is the weakest pair on reals too (.75). The
   grammar's own M–I drawings separate (.88), so the separation is lost in
   translation. Both are "contour" hands, and restyle squeezes them toward the
   structure's smoothness.
3. **Trees separate the hands better than learned topologies** (M–H .85–.90 vs
   .60–.65). Long connected lines give the hand more line to show itself.
4. **Lognormal is at chance.** The kinematic trace is so faithful (`composite-models.jpg`)
   that the hand barely shows. That fits the lognormal round, where its strength
   was representation, not difference.

## 4. Judge pairs (built, not judged)

- **Paths.** Images: `.local/gesture/out/blind_hand/pairs/pair_001.png` …
  `pair_050.png`. Key (outside the repo): `/tmp/gesture_hand_key.json`.
- **Layout.** Top: A | B, two 480 px crops of the *same window* of one structure
  redrawn in two hands. Bottom: reference crops of a real Matisse and a real
  Hokusai.
  - Rendering, line width and 5 px smoothing match `blind_pairs.py`.
  - The shared frame makes A and B land on the same pixels.
- **Question for the judge:** "Both drawings share a structure; which one is in
  Matisse's hand?"
- **Conditions:**
  1. **test** (30): Matisse vs Hokusai restyle at 0.8, trace, welded.
     Structures alternate Oehlen tree and learned topology.
  2. **calib_pos** (10): a real Matisse crop vs a real Hokusai crop, with references
     taken from other sheets. A judge worth trusting should find these easy.
  3. **calib_neg** (10): one structure in the Matisse hand twice, with different
     seeds. The key answer is "none"; a forced choice should be at chance.
- Not judged by me, per the brief.

## 5. The sheets, honestly

1. **`composite-trees.jpg`**: rows simple / medium / complex tree, columns
   skeleton | Matisse | Hokusai | Ingres, amount 0.7.
   - **Structure-in-a-hand:** the simple and medium rows read as the same tree,
     redrawn. All junctions are welded: no branch floats off its limb.
   - **The hands are distinguishable by eye at medium:**
     - Matisse: stepped micro-kinks, a "nervous staircase" along long lines.
     - Hokusai: square notches, loops and blobby closed knots at junctions.
     - Ingres: the longest calm runs, with sudden thin spikes and small eyelets.
   - **Noise:** in the complex row the hand eats the structure. Hokusai throws a
     big balloon loop off the top, and all three become "cell networks with
     wobble" more than trees.
   - Wild hooks at some twig tips are duds; awkward but alive.
2. **`composite-trees-chained.jpg`**: `chain="before"`, one continuous line
   through the skeleton redrawn by the hand, plus a Matisse column at
   `max_retrace` 0.15.
   - **Mostly a dud as tree translation.** Every retrace hairpin (the line going
     out a twig and back) is smoothed by the σ_s low-pass into a round balloon
     loop. The tree dissolves into a loopy meander, and the three hands look
     alike, because the loops dominate.
   - As an image it is an Oehlen-ish all-over single line (the medium row
     especially). Worth seeing, but it is not "the tree in a hand".
   - At 15 % retrace (11–17 paths) the trunk lines come back.
   - The fix is cheap and untried: pin hairpin tips as corners (clothoid
     decomposition, or a pin at each retrace turn).
   - `chain="after"` gives exactly the `composite-trees.jpg` image as 1–2 pen
     paths (verified by the sheet, not committed).
3. **`composite-translation.jpg`**: real long strokes → each hand, plus one
   chained-skeleton column.
   - **Matisse KKS1971-302** (the torso) is the best translation yet. The figure
     holds in all three hands:
     - Hokusai adds loops and polygonal knots at the hip;
     - Ingres keeps long contours with angular notches;
     - Matisse→Matisse goes jaggy, which shows the grammar's corner excess, not
       Matisse.
   - **Matisse KKS13418_2** (striped interior) and **Hokusai 57263** (wave/cloud)
     drown. The source strokes are short, and the restyle wobble is as large as
     the forms. The chained-skeleton versions balloon, as in item 2.
4. **`composite-learned.jpg`** (not committed): learned topology per hand.
   - Scattered fragments, 15–51 paths. There is no figure, the known composition
     gap. Hokusai's is the only one with some connected masses.
   - Ingres s2 has a long needle-like spike: a restyle dud on a short, sharply
     turning stroke.
   - Chaining at crossings saves only 25–50 % of the paths, because these
     structures are mostly free lines.
5. **`composite-models.jpg`**: the same medium tree, grammar vs lognormal, chained
   and not.
   - Lognormal is almost the skeleton with a slight tremble: clean, plottable, and
     the hands are indistinguishable.
   - Grammar shows hands.
   - Chained = unchained in appearance (`after`), as designed.

**Distinguishable by eye:** Hokusai is the easiest to tell, by loops and square
notches. Matisse and Ingres are separable on trees: staircase vs long-calm-plus-spike.
They are not separable on short real fragments.

## 6. Recommendation: what to put on paper first

1. **An Oehlen tree, medium complexity** (depth 4, 2 trunks, fill 0.8), in the
   **Hokusai** and **Matisse** hands at **amount 0.7**, plotted as
   `chain="after", max_retrace=0.15`: about 8–12 pen lifts instead of 35, and
   15 % doubled twigs.
   - Two sheets, same structure, side by side. That is the pairwise test on paper,
     and the pair the panel separates at 0.75–0.90.
   - `.local/gesture/out/composite/sheets/big-trees-medium-{matisse,hokusai}.jpg`
     are the 1200 px previews of that structure.
2. Second: **the Matisse torso in the Hokusai hand**, a real structure
   translated. It is the clearest "translation" image so far.
3. **Not yet:**
   - single-line `chain="before"` (balloons);
   - learned topologies (no figure);
   - lognormal (no hand).

## Weaknesses and next steps

1. The judge pairs are built but not run, so there is no human-like reading yet.
   Run them with calib_pos and calib_neg alongside.
2. The pairwise test is one seed per structure × amount, n = 40 per cell. The margins
   are small, so more seeds would tighten the M–H .75.
3. Hairpin-aware `chain="before"`: pin the retrace turns, or decompose with
   `clothoid` so the turn stays a corner.
4. Retrace geometry: an exact retrace is invisible on paper but doubles ink. A
   slightly offset retrace would read as Matisse's doubled contour. That is a cheap
   experiment.
5. `scale="stroke"` needs a grid run. Tremor needs a look once its module settles.
6. The corner excess (about 2.5× real) is still the dominant texture error, and
   runs make it worse. It belongs to the grammar thread, not to translation.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
$P -m experiments.composite pairwise --n-tree 20 --n-learned 20 --models grammar,lognormal  # ~7 min, 3 workers, resumable
$P -m experiments.composite sheets      # ~2 min
$P -m experiments.composite judge       # ~2 min; key → /tmp/gesture_hand_key.json
$P -m experiments.composite bench
$P -m experiments.restyle_study delta   # v4 vs v3 restyle cells
$P -m pytest -q tests/test_composite.py tests/test_restyle.py
```
