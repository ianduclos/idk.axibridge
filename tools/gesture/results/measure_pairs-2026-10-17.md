# Round 10 — measure_pairs: a drawing and its measurement — 2026-10-17

Ian, round 9: the diagram voices work as ACCESSORIES. "They feel like they are
measuring or have correlation with the drawings." He also wanted an option to
merge the shadow line's overlaps. This exploration pairs a loose drawing with
its own measurement as one piece. It adds the merged shadow, makes the atlas a
stand-alone print, and takes one risk: the measurement answers the drawing as a
second hand.

Code: `tools/gesture/gesture/kit/measure_pairs.py` (one new kit file, no core
edits). Driver: `experiments/measure_pairs.py`. Tests:
`tests/test_measure_pairs.py`, 16 tests in 8 s. Outputs are in
`.local/gesture/out/measure_pairs/`, with copies here as
`measure_pairs-*.jpg` + `.recipe.json`. Every image is under 400 KB. Each
contact sheet has a `.recipe.json` beside it that lists its cells' recipes.

## Modules

| # | kind | id | what |
|---|---|---|---|
| 1 | modulator | `measure_pair` | the drawing and its chart (kappa / route / phase / atlas / ledger) in one of four layouts: `margin`, `diptych`, `under` (same box, finer pen) or `wrap` (κ seismograph on a rounded frame that hugs the drawing). **Numbered indices** tie places in the drawing to places on the chart: by `even`, `seams` or `peaks`; atlas specimens and ledger deciles number their own sources |
| 2 | modulator | `measure_shadow` | the round-9 shadow with **overlaps merged** (`merge: union`). The strip between the line and its shadow is unioned (shapely) and traced as closed outline rings. Wherever the strip pinches to nothing, the drawing's own line is kept as an open line, so the drawing never breaks. Laws: kappa, speed (2/3 power law, or the dance's own `dance_speed`), regime, voice, time. Sides: left, right, `turns` (the inner side of every turn, pinching at inflections) and outer. Shapes: `beads` (half-strip + discs, so the far side rounds off) or `strip` (exact). Also `close` (morphological closing, in mm) |
| 3 | modulator | `measure_atlas` | the drawing taken apart into its shape atlas, as a piece. Order by turning / time / hand / length / sign. Layouts: grid, frieze, `exploded` (each specimen stays where it was, pushed out from the centre). Other params: `grain` (finest specimen), `drawn_by`, and `keep_drawing` (the drawing beside its atlas with origin numbers) |
| 4 | modulator | `measure_answer` | **the risk.** A second hand (restyle) is grown along the drawing's smoothed spine. It is busy where the drawing is calm (`silence`) or busy where the drawing turns (`echo`). `quiet: spine` keeps it as one continuous line; `quiet: lift` makes it only interject |
| 5 | renderer | `measure_wire` | wire at `pen` for the drawing, answer and shadow, and at `chart_pen` (0.25) for charts and indices |

## Images worth Ian's eyes

1. **`measure_pairs-shadow_turns.jpg`**: the merged shadow on the inner side of
   every turn. Drawing and shadow become one contour. It pinches to a single
   line at inflections and swells into round beads and knots at turns. This
   is not the capsule "sausage" he disliked: the beads are round, and the
   straights stay one line.
2. **`measure_pairs-pair_atlas.jpg`**: a drift beside its own shape atlas in
   time order. Each specimen's number is printed on the drawing where that
   specimen came from (01 to 24). The correlation reads at once, without a
   legend. The mantis version (`pair_dance.jpg`) does the same for the dance
   drawing itself.
3. **`measure_pairs-shadow.jpg`**: eight laws, sides and shapes on one drift,
   with round 9's unmerged shadow as cell 1 for comparison. Also look at
   `pair_wrap.jpg`, where κ(s) runs round the drawing on a frame, with the 9
   strongest turns numbered on both the drawing and the frame.

## Numbers (seed 7003 drift, L = 1555 mm, 28 specimens)

| # | shadow variant | rings | open | ink / unmerged ink |
|---|---|---|---|---|
| 1 | strip, κ left | 39 | 0 | 0.735 |
| 2 | beads, κ left | 40 | 0 | 0.726 |
| 3 | beads, κ turns | 26 | 8 | 0.711 |
| 4 | beads, speed right | 35 | 0 | 0.844 |
| 5 | beads, κ turns, close 1.5 | 21 | 7 | 0.576 |
| 6 | beads, voice left | 34 | 0 | 0.766 |
| 7 | beads, κ outer, far | 53 | 7 | 0.545 |

Merging removes 16–45 % of the pen travel. Each union takes 0.5–1.0 s.
`drawn_by` (restyling every chart polyline through a hand) is the slow part:
20–37 s per sheet, against under 1 s for anything machine-drawn.

## Surprises

- **Beads come free.** With `side: turns` the offset is
  `(gap + gain·|κ|)·tanh(κ/κ₀)`, which is continuous through zero, so the
  merged contour pinches exactly at inflections. The half-strip + disc
  construction then turns every tight turn into a round knot. This is the
  "round beads/knots" grammar from round 8, reached through measurement
  rather than through a regime.
- **Provenance numbers beat chart ticks.** For an atlas or a ledger, putting
  the specimen or decile number on the line reads better than any tick on a
  κ chart. Kappa-row indices work, but they are small, and the eye has to
  search the rows.
- **The `under` layout** (route lanes under the drawing in a finer pen) reads
  like a drawing on ruled paper whose rules are its own data. That was
  unexpected and quiet. Worth a look.

## The risk: `measure_answer`

It **half held.**

- **What held.** `silence` with a loose spine (matisse, 8 mm off,
  `answer_2.jpg`) and `lift` (lichtenberg, `answer_3.jpg`) read as a second
  loose hand that wanders beside the drawing. It goes quiet where the drawing
  turns and speaks on its straights, so the call and response comes from κ.
- **What did not.** With a tight spine (3 mm) the answer is too close to the
  drawing and reads as a wobbly double line. `echo` reads as a shadow. The
  dance version (shikasta answering levitation, dropped from the sheet) was
  nearly a plain double line, because the dance phrases are too short for the
  hand to add turning at that scale.
- **Verdict.** A real second voice needs a bigger departure (spine ≥ 0.05,
  offset ≥ 5 mm) or a different seed of the drift itself, not a restyle.

## Failures and limits

- The `phase` chart of a dance (`pair_dance_phase.jpg`) is a tangle: dance κ
  is noisy and the phase plot overdraws. Keep phase for drift lines.
- `frieze` is still a grid of equal cells. A true frieze would pack
  specimens left to right by their own width, like writing.
- `exploded` is dominated by the drift's one or two big arcs. The idea is
  sound, but it needs a length cap or per-specimen scaling.
- Index numbers are machine-lettered at 1.6–2.2 mm. They print legibly at
  6 px/mm but crowd where turns cluster. There is no collision avoidance
  between indices.
- The κ trace on the wrap frame gets stray diagonals at the rounded corners,
  because normals there swing fast.

## Proposed kit-core changes (not made)

1. **A per-mark role → pen in the core `wire` renderer.** For example
   `meta["pen_scale"]`, so that accessories (charts, indices) can be finer
   without a separate renderer. `measure_wire` exists only for this.
2. **A shared `measure()` cache per run.** `measure()` is called once per
   modulator; a run-scoped memo keyed on the marks' ids would save
   recomputation when several measurement modulators chain.
3. **Promote `text()` / `short()`** from `voices_machine_diagram.py` to a
   small `kit/_lettering.py`, so that accessories stop importing a voice
   file for its font.
4. **A contact-sheet recipe convention in `kit.contact`.** For example a
   `recipes=` argument that writes the list beside the image, so contacts
   honour "recipe beside every image" by default.

## Next

- Make the merged shadow a **save-able piece**: `shadow_turns` with
  `close` ≈ 1 on a dance or corpus hand.
- Build a true frieze (packing by width) and an exploded atlas with a length
  cap.
- Try the atlas drawn by a corpus hand (roadrunner, mantis), to see whether
  the Matisse-ledger magic carries over.
- Answer v2: grow the answering line as its own drift with the drawing's κ
  as its **route weights**, instead of restyling the spine.

## Test status

`tests/test_measure_pairs.py`: 16 passed in 8 s. The whole research suite,
run from the repo root: **553 passed** in 96 s, no failures. Run from
`tools/gesture/`, `test_script_syntax.py` fails to collect (`from tools.gesture
…` import), which is a pre-existing path assumption and not in this file set.
