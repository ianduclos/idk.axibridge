# Composite on grammar v6 + tremor v2 (2026-10-16, late night)

Follows `composite-chain-2026-10-16.md` (chain fix, frozen v4, no tremor). This
round re-points the composite to the frozen v6 grammar, puts v6's corner/turning
budget *inside* restyle's `trace`, applies tremor v2 after the chain, and
regenerates the plot candidates.

Code:
- `gesture/restyle.py`: the grammar module is taken from the grammar object
  (`_gmod`). With a v6 grammar, `trace` and `chain` draw under v6's per-line budget
  (`TRACE_BUDGET = 1.0`, `budget=` on `restyle_points` / `restyle_drawing`;
  `budget=0` consumes no randomness, so it equals v4's rule).
- `experiments/composite.py`:
  - `grammar(art, version)` and `GRAMMAR_VERSION = "v6"` (the default);
    `composite(grammar_version="v4")` is the comparison flag. Line widths
    (`hand_w`, `w_common`) stay on the v4 snapshot, so offsets are comparable.
  - The tremor stage (`TREMOR_DEFAULT`): v1 for Matisse, v2 for Hokusai and Ingres;
    `tremor_which` overrides it.
  - `tremor_chain(returns="follow"|"independent", pin_w=)` for single lines;
    `restyle_chain` now records `runs` (return spans); `return_spacing`.
- `experiments/composite_v6_study.py`: `ablation`, `report`, `sheets`, `plot`.
- Tests: 5 new in `tests/test_composite.py` (22 in the file; with `test_restyle.py`
  42 tests in 4.5 s).

Raw outputs: `.local/gesture/out/composite_v6/` (`rows.jsonl`, `report.md/json`,
`sheets/big-*.jpg`). Plot candidates: `.local/gesture/out/plot_candidates_v2/`.
Sheets: `composite-v6-{trees,paths,torso,complex}.jpg`.

## Verdict

1. **v6's corner budget does carry into restyle**, once it is applied inside `trace`.
   - Round 3 found that v4's fixes did not carry, because `trace` bypasses steering.
     The budget lives in the chain's draw (`Grammar.draw(weights=)`), which `trace`
     calls, so it reaches the line.
   - With the budget off, v6 restyle is **bit-identical** to v4: the learned
     transitions are the same. Every difference below is the budget.
2. **Texture moves toward real, and fidelity improves.**
   - Corners fall 25–40 %, turn correlation rises to about real, and the distance to
     the structure falls by about 30 %.
   - The price: Matisse and Ingres are now **under-turned** (turn_abs 9.7 / 12.3
     against real 15.6 / 21.6). The budget's turning term over-smooths inside `trace`.
3. **The hand separates a little less** on the panel. Single-line M–H drops from
   .83 to .73, H–I from .90 to .77; with n = 30, ±.09 is noise, but the direction is
   the same in every cell. The budget pulls all three hands toward a common
   smoothness: the Hokusai-hand logit moves to the Matisse side.
4. **By eye, v6 is clearly better** (sheets): the trees read as trees in all three
   hands. v4 Hokusai's wild drift, chords and big loops are mostly gone.
5. **Tremor after the chain is safe and invisible to the panel.**
   - Junctions are unchanged and the path ends stay pinned.
   - With "follow" returns the double line keeps its 1.5 w spacing at the median.
     Independent returns push more samples under 1 w.
   - Pairwise with versus without tremor: noise-level differences. Tremor neither
     helps nor hurts hand identification at the panel's σ ≥ 7 w.
6. **First plot:** `tree-medium-hokusai-1line` and `tree-medium-matisse-1line` (v6 +
   tremor) side by side. Six SVGs are ready (§5). Nothing was plotted.

## 1. v4 vs v6 restyle

Setup: 30 Oehlen trees (the round-3 pairwise structures) and the Matisse torso; hands
Matisse / Hokusai / Ingres; amount 0.7; seed 1. Medians are over trees.
- Panel features at w_common (σ ≥ 7 w), cl group included.
- Single lines are measured between hairpins (the round-4 rule).
- "Corners" is `cl_corner_rate`.

| # | condition | hand | corners | turn_tcorr_10 | k_q50 | turn_abs | d_mean/R | junction gap max/R | balloons |
|---|---|---|---|---|---|---|---|---|---|
| V1 | restyle v4 | M | 2.79 | .64 | 7.2 | 17.8 | .0076 | .0217 | 0.5 |
| V2 | restyle v6 | M | **1.64** | .81 | 5.0 | 9.7 | **.0055** | .0176 | 0.1 |
| V3 | restyle v4 | H | 4.42 | .38 | 10.9 | 26.7 | .0128 | .0254 | 1.1 |
| V4 | restyle v6 | H | **3.51** | .61 | 8.0 | 18.4 | **.0077** | .0233 | 0.5 |
| V5 | restyle v4 | I | 3.70 | .54 | 7.8 | 23.5 | .0091 | .0242 | 0.6 |
| V6 | restyle v6 | I | **2.36** | .74 | 5.5 | 12.3 | **.0062** | .0191 | 0.2 |
| V7 | single line v4 | M / H / I | 4.67 / 5.24 / 4.93 | .38 / .32 / .41 | 9.1 / 12.1 / 9.2 | 18.3 / 21.0 / 20.0 | .0065 / .0099 / .0070 | .012 / .018 / .012 | 0.7 / 1.9 / 0.5 |
| V8 | single line v6 | M / H / I | **3.82 / 4.80 / 4.18** | .50 / .42 / .49 | 7.0 / 9.8 / 7.2 | 13.7 / 17.9 / 14.6 | **.0048 / .0075 / .0051** | .011 / .008 / .011 | 0.7 / 1.1 / 0.3 |
| V9 | real | M / H / I | 1.50 / 1.32 / 1.61 | .71 / .46 / .73 | 5.5 / 8.1 / 6.3 | 15.6 / 17.6 / 21.6 | — | — | — |

The skeleton alone scores 0 corners, tcorr .94 and k_q50 3.1.

**Budget gain** (restyle; single line in brackets):

| # | gain | M corners | H corners | I corners | M–H pairwise | H–I pairwise |
|---|---|---|---|---|---|---|
| G1 | 0 (= v4) | 2.79 | 4.42 | 3.70 | .97 (.83) | .97 (.90) |
| G2 | 0.5 | 1.96 | 3.50 | 2.41 | .90 (.67) | .97 (.80) |
| G3 | **1 (default)** | 1.64 | 3.51 | 2.36 | .90 (.73) | .87 (.77) |
| G4 | 2 | 1.54 | 3.07 | 2.19 | .90 (.73) | .80 (.63) |

**Reading:**

1. **Matisse restyle reaches real corners** (1.64 against 1.50). Ingres is at 1.5×
   real, Hokusai at 2.7×.
2. **Single lines stay at 2.5–3.6× real corners even in v6.** Two causes:
   - The anchors are hard corners by construction: every node turn ≥ 60° is pinned.
   - The hairpin cut leaves short pieces whose ends count as corners.

   This is a property of the single-line recipe and of how the line is measured, not
   of the hand.
3. **Gain 0.5 keeps the hand better on restyle** (H–I .97, the same as v4) for about
   the same corner rate as gain 1, except for Matisse (1.96).
   - It is a candidate default if hand identity matters more than Matisse's corner
     rate.
   - Not adopted: the single-line numbers do not favour it (M–H .67).
4. **The turning undershoot** (Matisse and Ingres turn_abs about 60 % of real) is the
   clearest new tell.
   - Next step: a per-hand turning gain in the budget, or letting `trace` use only
     the corner term (`BUDGET_GT` → 0).
   - That was not tried, because grammar.py belongs to another agent and the frozen
     v6 is read-only. A trace-local copy of `_Budget` with its own `gt` would be the
     way.

## 2. Tremor in the pipeline

**Setup.**
- Stage order: structure → restyle → chain → tremor, at amount 1.
- Per-hand default model (`TREMOR_DEFAULT`):

  | hand | model | mode |
  |---|---|---|
  | Matisse | v1 (`tremor/models/matisse.json`) | stationary |
  | Hokusai | v2 (`tremor_v2/models/hokusai.json`) | bursty |
  | Ingres | v2 (`tremor_v2/models/ingres.json`) | bursty |

  `matisse_etching` v2 is available as `tremor_which="v2_etching"`. On the medium
  tree it gives rms 0.083 w against v1's 0.064 w.
- Line width is the hand's own w.

**Single lines** go through `tremor_chain`. Each pen path gets one tremor field from
`gesture.tremor` (ends pinned, κ/end envelope, v2 regime and kinks). Return passes
are handled one of two ways:
- **"follow"** (default): each return sample takes the displacement *vector* of
  the nearest outward-pass sample. One tremor field covers the double line.
- **"independent"**: each pass trembles on its own.

**Restyle-only drawings** use `apply_tremor`, which re-snaps contacts.

**Spacing measure.** For the central part of every offset return, the distance to
its counterpart is measured: the nearest outward sample running the opposite way
(tangent dot < −0.7, within 4 w). Crossings with other lines are ignored. Values are
medians over 30 trees.

| # | condition | hand | tremor rms (w) | spacing median (w) | q01 | share < 1 w | share < 0.5 w | junction gap max/R |
|---|---|---|---|---|---|---|---|---|
| S1 | no tremor | M / H / I | — | 1.50 / 1.50 / 1.50 | .24 / .16 / .21 | 6.3 / 8.6 / 7.0 % | 2.5 / 3.6 / 3.1 % | .0113 / .0082 / .0112 |
| S2 | **follow** | M / H / I | .041 / .125 / .149 | 1.50 / 1.49 / 1.50 | .16 / .11 / .16 | 8.6 / **13.4** / 8.5 % | 3.4 / 6.2 / 3.8 % | .0113 / .0085 / .0112 |
| S3 | independent | M / H / I | .041 / .127 / .155 | 1.50 / 1.47 / 1.49 | .16 / .12 / .16 | 8.6 / **15.8** / 9.7 % | 3.5 / 6.8 / 3.8 % | .0113 / .0085 / .0112 |

**Reading:**

1. **The sub-1 w share is there before any tremor** (6–9 %).
   - The offset return collapses on the inside of the hand's own sharp corners,
     because the offset is larger than the local radius.
   - The worst tree touches (min ≈ 0) in every condition.
   - That is geometry from the chain fix, not tremor.
2. **Follow keeps the median spacing exactly.** It roughly halves to two thirds the
   extra close samples that independent passes add (Hokusai +4.8 against +7.2
   points).
   - It is not perfect: the nearest-sample correspondence is wrong near corners.
   - An arc-length correspondence through `runs` would be exact. It was not done.
3. **Junctions are untouched.** The tremor is about 0.0003 R, against junction gaps of
   about 0.01 R.
   - `pin_w` (zero tremor within pin_w line widths of every anchor) is implemented
     and tested, but off by default: nothing needed it.
   - The path ends are exactly pinned (test).
4. **Tremor does not change the panel's texture numbers** (V8 against f6t: corners
   ±0.15, everything else ±0.01), as the tremor-v2 round predicted at σ ≥ 7 w.

**On paper** (A4, the plot candidates):
- Hokusai: tremor rms 0.16 mm, offset 1.15 mm, q01 spacing 0.10 mm.
- Matisse: rms 0.026 mm, offset 0.61 mm.

With a 0.4 mm pen, the two passes touch once their centres come closer than the pen
width:
- Hokusai: below 0.51 w, at about 6 % of its return length (share < 0.5 w), mostly
  at corners.
- Matisse: below about 1 w, since the pen ≈ its w, at about 9 %. The Matisse double
  line is a hairline pair that fuses wherever it turns.

## 3. Pairwise hand test

**Setup.**
- The classifier is trained on REAL drawings of A vs B; the texture groups are k,
  ext, infl, turn and cl.
- n = 30 trees per cell; the learned topologies are n = 12, 4 per artist model.
- Single lines are measured between hairpins.
- A trial is correct when the A-hand drawing scores more A than the B-hand drawing
  of the same structure.

| # | condition | M–H | M–I | H–I |
|---|---|---|---|---|
| W1 | restyle v4 | **.97** | .60 | **.97** |
| W2 | restyle v6 | **.90** | .50 | **.87** |
| W3 | restyle v6 + tremor | .83 | .33 | .80 |
| W4 | single line v4 | **.83** | .43 | **.90** |
| W5 | single line v4 + tremor | .90 | .50 | .87 |
| W6 | single line v6 | .73 (p .008) | .53 | .77 (p .003) |
| W7 | **single line v6 + tremor (final pipeline)** | **.77 (p .003)** | .43 | **.70 (p .021)** |
| W8 | single line v6 + tremor, independent returns | .73 | .53 | .77 |
| W9 | final pipeline, learned topologies (n = 12) | .50 | .50 | .42 |

**Calibration.** Real cross-validation / real held-out pairwise:
- M–H: .76 / .85
- M–I: .69 / .75
- H–I: .95 / .99

**Without the cl group** (round 4's setup), every number is 0.05–0.25 lower, and the
v6 single line drops to .57–.70.

**Reading:**

1. **M–H and H–I survive the full pipeline.** M–I fails, as in every round: it is the
   weakest real pair.
2. **v6 costs about .1 of hand separation** relative to v4, in every cell.
   - The v4 hand is partly *carried by its excess corners and turning*: Hokusai's
     knots, the jaggedness.
   - The budget removes some of that, so the hands converge.
3. **Tremor helps or hurts by at most 1–3 structures out of 30**, in both
   directions: noise. The panel at σ ≥ 7 w cannot see a 0.04–0.15 w tremor. Whether
   the *eye* uses it is a judge question; it was not run here.
4. **Learned topologies are at chance** in the final pipeline. Composition remains
   the gap, and trees remain the right vehicle.

## 4. The sheets, looked at

1. **`composite-v6-trees.jpg`**
   - Layout: medium and complex trees. Columns: skeleton | Matisse v4, v6, v6 + tremor
     | Hokusai v4, v6, v6 + tremor | Ingres v6, v6 + tremor.
   - **Matisse v6** is the best tree drawing so far. The structure reads exactly:
     calm trunks and doubled twigs, with only a few short notches. v4 had curls and
     hooks at twig tips; v6 has almost none.
   - **Hokusai v6** is far cleaner than v4.
     - v4's medium tree drifted into loops, chords and a big swirl. v6 keeps the
       tree: wavering doubled branches, sharp square notches, one round knot.
     - The complex Hokusai tree still has one big lobe at the top, and its frame
       shrinks because of it.
   - **Ingres v6:** long straight runs with polygonal zig-zags, and a dense knot of
     crossing returns in the medium tree's upper middle.
   - **Tremor** is invisible at sheet scale (360 px).
     - At 1200 px (`big-medium-hokusai-v6_tremor.jpg`) Hokusai's doubled branches
       waver together, with bursts of irregular edge. That reads as a brush pressed
       harder, not as noise.
     - Matisse's v1 tremor is too small to see.
   - **The three hands are distinct by eye:**
     - Matisse: calm and nervous-notched;
     - Hokusai: wavering, knotted, square notches;
     - Ingres: straight and polygonal.
2. **`composite-v6-paths.jpg`**
   - **≤ 8 paths, v6 + tremor:** clean, with less doubling. v4 Hokusai at ≤ 8 paths
     shows round balloon loops and straight chords across the tree; v6 has none.
   - **Learned topologies as one line** (connect):
     - Hokusai's is a convincing cellular mass of wavering doubled contours, the
       most "painting"-like.
     - Matisse's and Ingres's are fragments with long connector chords. Thick
       doubled connector stretches read as heavy strokes, a little foreign.
3. **`composite-v6-torso.jpg`**
   - **v6 Matisse:** the figure holds: shoulder, breast, belly, arm, and the hip and
     thigh as doubled contours. It is the cleanest torso yet.
   - **v6 Hokusai:** the round-4 S-swing connector is gone. Instead the back contour
     bulges into a large hump at the right shoulder; awkward but readable.
   - **v6 Ingres:** one connector across the chest became a long doubled lens, like
     a horizontal bar. That is the connector-in-the-hand problem again; it is not
     solved.
   - **Hokusai ≤ 8 paths:** loses the hips: they become fragments.
   - **v4:** Hokusai has three balloons and loops at the hip; Matisse and Ingres are
     acceptable.
4. **`composite-v6-complex.jpg`**, "more complex than the trees":
   - **Dense crossing network** (depth 5, 3 trunks, fill .95, p_cross .35, chained at
     crossings): an all-over field of cells, twigs and doubled spurs.
     - Hokusai's reads most like an Oehlen computer drawing: knotted cells, a
       wavering line everywhere, no centre.
     - Matisse's is calmer, with one fat loop.
   - **Torso + tree** (a regime collision, one line): the figure is almost lost
     under the branches.
     - In the Matisse hand the belly and arm curves survive as the calmest lines in
       a thicket. Hokusai's becomes a dense tangle.
     - Interesting as a collision, but the torso needs to dominate (fewer, shorter
       branches) to read.

Nothing has been verified by Ian's eye.

## 5. Plot candidates v2 (not plotted)

**Location:** `.local/gesture/out/plot_candidates_v2/`, one SVG and one 1200 px JPEG
preview per candidate, plus `candidates.json`.

**Format:**
- A4 landscape, 297 × 210 mm, 10 mm margin.
- One `<path>` per pen path; stroke 0.4 mm.
- Recipe: v6 grammar, chain fix (`pin="turns", retrace="offset", walk="min_turn"`),
  amount 0.7, per-hand tremor at amount 1, follow returns.
- Time = (pen-down + pen-up travel) / 25 mm/s + 0.5 s per pen cycle.

| # | file | structure / hand | paths (lifts) | pen-down | pen-up | est. time | w / offset (mm) | tremor rms | spacing q01 | d_mean/R | junction gap max/R | retrace |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | `tree-medium-matisse-1line.svg` | medium tree (seed 101), Matisse, tremor v1 | 1 (0) | 3.05 m | 0.52 m | 2.4 min | 0.41 / 0.61 | 0.026 mm | 0.05 mm | .0042 | .0011 | 64 % |
| C2 | `tree-medium-hokusai-1line.svg` | same tree, Hokusai, tremor v2 | 1 (0) | 3.51 m | 0.51 m | 2.7 min | 0.76 / 1.15 | 0.156 mm | 0.10 mm | .0074 | .0025 | 64 % |
| C3 | `torso-matisse-1line.svg` | Matisse KKS1971-302 torso, Matisse, 11 connectors | 1 (0) | 1.44 m | 0.24 m | 1.1 min | 0.33 / 0.50 | 0.032 mm | 0.08 mm | .0096 | .0058 | 46 % |
| C4 | `torso-hokusai-1line.svg` | torso, Hokusai | 1 (0) | 1.66 m | 0.24 m | 1.3 min | 0.63 / 0.95 | 0.087 mm | 0.25 mm | .0107 | .0066 | 46 % |
| C5 | `dense-hokusai-1line.svg` | dense crossing network, Hokusai | 1 (0) | 4.14 m | 0.45 m | 3.1 min | 0.78 / 1.17 | 0.167 mm | 0.07 mm | .0062 | .0030 | 42 % |
| C6 | `torso-tree-matisse-1line.svg` | torso + tree collision, Matisse | 1 (0) | 4.20 m | 0.44 m | 3.1 min | 0.41 / 0.61 | 0.035 mm | 0.06 mm | .0051 | .0131 | 56 % |

**Against round 4** (C1, C2): the same tree and seed. d_mean is lower (.0042 against
.0066 for Matisse, .0074 against .0117 for Hokusai), there are no balloons, and
pen-down is 7–10 % shorter.

**Tremor on paper:**
- The Hokusai tremor rms (0.16 mm) and its burst excursions sit above the AxiDraw's
  ≈ 0.1 mm mechanical jitter, so they should show.
- Matisse's (0.03 mm) will not show. If visible tremor is wanted there, use
  `tremor_which="v2_etching"` or amount 2.

## 6. How to load these SVGs into axibridge (read-only inspection)

The existing path is **Assets tab → "Import SVG" → choose file → "Upload SVG"**.

1. That button (`axibridge/static/js/assets_tab.js`) sends
   `POST /api/layers/upload?quantization_mm=<curve tolerance, default 0.1>`.
2. The endpoint `upload_svg_layers` (`axibridge/api.py`) calls
   `session.add_svg_layers`.
3. That calls `svg_io.doc_from_svg`.

**What the import does:**

1. **Layers.** Each top-level `<g>` becomes one compositor layer. Our files have one
   unnamed `<g>`, so the result is one layer named "layer 1". Its source is
   `type="svg"`, kept in the project as `sources/<filename>`.
2. **Units.** `doc_from_svg` reads `width="297mm"` and `viewBox="0 0 297 210"` through
   svgelements at 96 ppi, then divides by `_SE_PX_PER_MM`, so coordinates arrive in
   mm unchanged.
   - Origin is top-left = carriage home, y down.
   - 297 × 210 fits the machine frame (x ≤ 300, y ≤ 218).
3. **Flattening.** The paths are pure `M`/`L` polylines, so the 0.1 mm curve
   tolerance does not touch them (it flattens only curves).
4. **Plotting.** It goes through the normal resolve → `_optimize`:
   - a 0.01 mm simplify baseline;
   - with the project's default plot options, `linemerge` (0.05 mm) and `linesort`.

   For the 1-path candidates neither changes anything. For a ≤ 8-path variant,
   `linesort` may reorder or reverse the paths, unless "Sort paths" is switched off.
5. **The MCP** has no upload tool. `call_api` sends JSON, not multipart, so the UI
   button (or a multipart POST to that endpoint) is the route.

Not done: no import was performed, the app was not touched, and nothing was plotted.

## 7. Recommendation for the first plot

1. **C2 and C1 side by side:** the medium tree in the Hokusai and Matisse hands.
   - It is the pairwise test on paper.
   - C2 also carries the only tremor large enough to see.
   - Expect visible double lines with a hairline gap in Matisse (0.61 mm offset) and
     a clear gap in Hokusai (1.15 mm), fusing at corners.
2. **Then C3** (the torso in its own hand, the cleanest figure) **or C5** (the dense
   network, the most Oehlen-like).
3. **Hold C4 and C6** until C1/C2 have been looked at on paper.

## Weaknesses and next steps

1. **v6 over-smooths turning** (Matisse and Ingres turn_abs ≈ 60 % of real) and costs
   about .1 pairwise. Try a trace-local budget with corner term only, or per-hand
   gains; gain 0.5 is the nearest existing compromise.
2. **Follow returns use a nearest-sample correspondence.** Mapping through the run
   spans by arc length would keep the spacing exact. The offset itself collapses on
   inner corners: clip the offset to the local radius.
3. **Connectors** are still redrawn by the hand (the Ingres chest bar, the Hokusai
   hump).
4. **Pairwise** is one seed, n = 30; learned topologies n = 12. The judge was not run
   on the v6 sheets.
5. **The torso + tree collision** needs the structure weighted toward the figure.

## Commands

```bash
cd tools/gesture
P=../../.local/gesture/.venv/bin/python
$P -m experiments.composite_v6_study ablation      # ~6 min, 3 workers, resumable (rows.jsonl); --conds to add cells
$P -m experiments.composite_v6_study report
$P -m experiments.composite_v6_study sheets        # ~2 min
$P -m experiments.composite_v6_study plot          # → .local/gesture/out/plot_candidates_v2/
$P -m pytest -q tests/test_composite.py tests/test_restyle.py
```

**Full gesture suite: 257 passed in 29 s.**
