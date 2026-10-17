# New voices learned from corpora — round 9, thread voices_corpus (2026-10-17)

Code:

- `gesture/kit/voices_corpus.py`: kit module. Library kind `dance_trail`, voice `dance`, modulator `own_tempo`.
- `experiments/voices_corpus.py`: stages `extract learn measure limb sheets`.
- `tests/test_voices_corpus.py`: 14 tests, about 2 s.

Raw outputs are in `.local/gesture/out/voices_corpus/`: extraction overlays, research grammars,
`measure.{md,json}`, `limb.{md,json}`, and every tile with its `.recipe.json` in `sheets/`.
Nothing was plotted or downloaded.

## Look at these first

1. `voices_corpus-dance-itself.jpg`: the dance drawing itself. Trails come straight from
   the frozen mocap, weighted by **their own clock**, so the result is mostly wire with one
   bead per pause. Rows 1–3 use the default (`beads=pauses`). Row 4 is the old
   "every still sample is mass" (`dwell`), where standing feet become solid bars. Row 5 uses
   an absolute speed normaliser.
2. `voices_corpus-limb.jpg`: the two hands farthest from everything in the library.
   **polygon_walk** (Noll + Nake) and **mime_monkey_hands** are shown alone and in drifts.
3. `voices_corpus-hands-computer.jpg`: AARON, Cohen's 1969 meanders and Molnar, each with
   smooth joins and with chain joins.

Also:

- `voices_corpus-hands-dance.jpg`: 11 dance and mime hands alone.
- `voices_corpus-drifts.jpg`: new hands drifting with seed hands.
- `voices_corpus-grid.jpg`: new hands set among seed hands at one scale, plus one polyphonic surface.

## What was built

| # | module | what |
|---|---|---|
| 1 | library kind `dance_trail` (loader) | frozen end-effector trails (5 effectors, front view, body-height units, 30 fps) + per-frame speed, acceleration, whole-body energy |
| 2 | voice `dance` | the trails as danced, cut into phrases at whole-body stillness; channels `dance_t` (s), `dance_speed` (bh/s), `dance_acc`; params trail, effectors (all/hands/feet/hands+head/single), t0, seconds, cut |
| 3 | modulator `own_tempo` | r from the line's **own** dance channels: one bead per pause (pauses ≥ 0.25 s, merged within 0.6 s), slow acceleration → a little nib, speed → wire; `norm` self/absolute; marks without dance channels pass unchanged |

New hands are plain library `hand` entries. The seed `hand` and `drift` voices use them
as they are.

## Library entries added (442 KB of hands + 780 KB of trails; the whole library is now 2.31 MB)

- **Hands, dance (E2 Stocos, CC BY 4.0)**: `dance_staccato` 44 KB, `dance_levitation` 13,
  `dance_thrusting` 55, `dance_particles` 38, `dance_fluidity` 23. Each is learned from 6 windows of
  15 s, all five effectors.
- **Hands, CMU-55 mimes**: `mime_mantis` 18, `mime_penguin` 13, `mime_dragon` 14,
  `mime_roadrunner` 40, `mime_prairiedog` 12, `mime_monkey` 20, and the limb's `mime_monkey_hands` 14
  (hand trails only).
- **Hands, early computer art** (V&A images; statistics only, private research):
  - `polygon_walk` 12 KB: Noll *Gaussian-Quadratic* + Nake *Random Polygons*.
  - `aaron` 72: Cohen/AARON 1985 + two 1987 drawings, with the signature cropped out.
  - `meander69` 47: Cohen's 1969 plotter meanders, tiled 2×2.
  - `molnar_letters` 7: *Letters from my Mother*, tiled 2×2.
- **Dance trails**: `levitation staccato thrusting particles outofbalance mantis penguin
  dragon hummingbird`, 54–105 KB each.

Every entry records its provenance: files, windows or extracts, rights, corpus,
`training_sheets` and commit. All are `generative`. No calligraphy is involved.

**Duds (evidence):**

- **Desmond Paul Henry** (`henry_machine`) was learned and measured but **kept out of the
  library**. Otsu picks up fragments of the dense curve families. The hand lands next to
  Marden (0.51) and is loose (tightness 1.15).
- **AARON 1989** extracted to 30 specks.
- **Trace fossils** (Helminthoida, Nereites) are relief photographs, not ink. They gave 1
  and 0 strokes.
- **Hummingbird hands** are still a scribble, as in round 8.

## Numbers: distinctness and coherence (panel space, standard preprocessing)

Method:

- Each hand drew 6 `generate_drawing` sheets (seeds 9000–9005).
- Panel features go through `hybrid.projector`, the MediumProjector fitted on the round-8 real
  panel.

The columns:

- **dist**: centroid distance to the nearest *library* hand, in units of the mean RMS radius of the two
  hands (≈ 1 means the clouds touch).
- **tightness**: the hand's own RMS radius ÷ the median over all hands. Below 1 means its sheets obey
  one rule set.
- **self-recog**: leave-one-out nearest centroid, i.e. how often one of its sheets is assigned
  back to it.
- **score**: dist ÷ tightness.

| # | hand | nearest library hand (dist) | tightness | self-recog | score |
|---|---|---|---|---|---|
| 1 | **polygon_walk** | henry_machine 1.35 (seed: marden 2.27) | **0.33** | **1.00** | **4.11** |
| 2 | **aaron** | molnar_letters 1.05 (seed: ingres 1.11) | 0.51 | 0.67 | 2.04 |
| 3 | lichtenberg (seed, for scale) | nastaliq 0.69 | 0.39 | 0.67 | 1.79 |
| 4 | **mime_monkey_hands** | mime_monkey **2.61** | 1.70 | **1.00** | 1.54 |
| 5 | matisse (seed) | ingres 0.45 | 0.48 | 0.33 | 0.93 |
| 6 | meander69 | dance_fluidity 0.83 (seed: marden 1.91) | 1.06 | 0.33 | 0.78 |
| 7 | molnar_letters | ingres 0.69 | 0.91 | 0.33 | 0.76 |
| 8 | dance hands (5) | another dance hand, 0.69–0.82 (seed: shikasta/marden 1.1–5.4) | 1.3–3.0 | 0.17–0.50 | 0.28–0.54 |
| 9 | mime hands (6) | another mime/dance hand, 0.50–1.06 (seed: shikasta 1.9–7.0) | 1.2–2.1 | 0–0.67 | 0.25–0.81 |

Full tables: `measure.md` (the first pass, all hands) and `limb.md` (with the variants).

**Reading:**

1. **The dance and mime hands are far from every seed hand.** Distances to the nearest seed
   hand run from 1.1 (Levitation, near Marden) to 7.0 (monkey, near shikasta). As a family
   they sit apart from the drawn hands, like round 8's dance structures.
2. **Within the dance family they are not separable, and they are loose.** Each one's
   nearest hand is another dance hand at 0.5–0.8, and self-recognition is mostly 0.17–0.5.
   Mocap hands are one strange grammar with many dialects.
3. **The computer-art hands are both distinct and coherent.** polygon_walk is the tightest
   hand in the library, AARON is next, and both recognise themselves.
4. **Fidelity is uninformative.** A classifier separates generated sheets from the hand's own
   training drawings for nearly every hand, the seed hands included (AUC 0.9–1.0). AARON
   (0.68) is the exception. I report it in the JSON but don't rank on it.

## Surprises

- **The dance trails make a better voice than they make a hand.** The learned dance hands
  are stranger than the seed hands (wandering loops with sharp hooks; roadrunner and prairie
  dog flick into tiny zigzags). But in hand form they lose what made the dance drawing:
  the body's phrase structure and its feet as floor lines. The `dance` voice keeps both,
  and `own_tempo` lets the body's pauses, not a borrowed tempo, decide where ink pools.
- **Pauses, not dwell.** Kinematic regimes put mass on every still sample, so a standing
  foot becomes a bar of mass (see the `dwell` row). One bead per pause, with pauses shorter
  than 0.25 s ignored and pauses within 0.6 s merged, gives the "mostly wire, sparse
  beads" Ian liked. The penguin's floor line becomes three beads on a wire.
- **The absolute normaliser barely changes Levitation vs Staccato** at v_ref 1.5 body heights/s. Their
  difference is already in the geometry (Staccato knots, Levitation long arcs).
- **molnar_letters splits by join mode.** Chain joins give a Noll-like zigzag script;
  smooth joins give loops and circles. It is one hand with two grammars, depending on context.

## The limb: the most distinct grammar the library can hold

I swept 10 variants (pairing, tiling, `min_len_w`, body part). All were measured against
the library; see `limb.md`.

1. **Noll + Nake as a pair, untiled (`polygon_walk`) is the winner, and it holds.** Score
   4.11, against 1.19 for Noll alone and 1.00 for Nake alone (each tiled 2×2), and 1.65 for
   the pair tiled.
   - Caveat: tiling and splitting are confounded. Tiling alone costs most of it: the pair
     tiled drops to 1.65.
   - So the distinctness lives partly in the *sheet-level* plan of a whole plotter
     composition, not only in the tokens.
2. **Restricting a dance to one body part does not tighten it.** Staccato hands 2.87, roadrunner feet
   3.27, Levitation head 0.94.
3. **Monkey hands only** jumped 2.61 away from monkey-all-effectors, which is the largest
   distance in the library. Its sheets always recognise themselves (1.00), though they
   vary a lot. Visually, *Monkey hands only* draws long swooping arcs, flat lenses and large
   loops, with no hooks. I saved it as `mime_monkey_hands`.
4. Raising `min_len_w` (polygon w40, meander w40, AARON w30) always made the hand looser
   and less distinct.

## Proposed kit-core change

`tests/test_kit.py::test_committed_library_shape_and_budget` asserts that the library's
hand ids **equal** the 8 seed hands. Any thread that adds a hand, which is the README's own
workflow, fails it. This is the only failure in the full suite. Proposal: change `==` to
`<=` for `hand` (and `tempo`), keeping the budget assert. I did not edit it.

Also optional: `kit.preview` could print part labels in `grid` cells. To get labelled
tiles I rendered one sheet per hand and assembled them with `kit.contact`.

## Next limb

1. **A dance voice over a learned hand.** Restyle the `dance` trail through `polygon_walk` or
   AARON at a low amount (0.3), keeping the dance's phrase cuts, floor lines and own clock.
   That gives the body's structure with a machine hand's surface, and `own_tempo` still reads
   `dance_t`.
2. **`own_tempo` on learned hands.** Give the grammar's tokens a synthetic clock, so non-dance
   hands can use pause beads too.
3. **More whole plotter compositions per artist** (Noll's other 1960s plots, more Nake) to
   check whether polygon_walk's coherence comes from the pair or from "whole composition".
