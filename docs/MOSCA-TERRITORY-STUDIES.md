# Mosca × Territory: making more

Checkpoint: 5 October 2026. Ian called the six-piece round “good progress.”
This accepts the direction on screen; nothing has been physically plotted.

## Three routes available now

1. **More treatments of existing Mosca drawings:** open the
   [Flowing bench preview](http://127.0.0.1:50465/mosca-line-option/web/bench.html).
   Choose a recording, set **Line style → Flowing · earlier study**, adjust
   **Bundle spread**, **Source detail** and **Pen width**, then **Download SVG**.
   Original remains the default; Fine bundle is a separate option. Flowing
   applies the earlier bundle/field treatment to existing paths. It cannot
   recover the earlier experiment's exact motion or 500 ms timing from those
   simplified recordings. No new brain simulation is needed for these controls.
2. **Compose with the actual earlier flowing drawings:** open
   [Flowing studies](http://127.0.0.1:50465/pieces-study/artifact/index.html),
   scroll to **The original flowing drawings**, and download an original SVG.
   In AxiBridge use **Compose → Import & assets → Upload**. Import another
   drawing or make a Territory layer using **Generate → Territory → Bench →
   Keep as layer**. Move, rotate and scale the layers on the canvas. **Save to
   gallery** in the selected layer's Effects area preserves reusable material.
   This is the available hands-on composition workflow; the studies gallery
   itself is a viewer/exporter, with layer visibility controls, not a generator.
3. **New brain runs:** from a terminal run `rack mosca-studio`, then use the
   Studio's **Make** controls to design/run a walk or generate a set. The
   project's launcher is `bin/studio.sh` in
   `/Users/ianduclos/_SecondBrain/01_Projects/mosca-draw`; its URL is
   `http://127.0.0.1:8770/web/studio.html` after launching. New walks are not
   automatically passed through this experimental flowing/composition pipeline.
   The native AxiBridge Mosca bench still browses recordings; its controls do
   not include the old K-series bench's new Flowing treatment.

For a fresh old-style bench server, run `bin/bench-serve.sh 8765` from the
mosca-draw repository and open `http://127.0.0.1:8765/web/bench.html`.
The standalone preview above contains the completed K-series recordings.

## Preserved experiment and restart

The lab is outside both applications:

```sh
LAB=/Users/ianduclos/.codex/visualizations/2026/10/05/01a10a65-93a8-7c60-919b-d277d02a951f/mosca-territory-lab
```

Its HTTP server is on 127.0.0.1:50465. If that server has stopped, restart it
without touching either application:

```sh
python3 -m http.server 50465 --bind 127.0.0.1 --directory "$LAB"
```

Open `/pieces-study/artifact/index.html` beneath that address. The same server
also exposes `/action-study/artifact/index.html` (earlier flowing drawings),
`/encounter-study/artifact/index.html` (causal interruption/replay comparison),
and `/recipe-instrument/artifact/index.html` (earlier parameter-driven study).

The latest set is in `pieces-study/artifact/`: six SVGs, six 300 dpi PNGs,
seven original flowing SVGs, `portfolio.pdf`, `pieces.zip`, and provenance.
The PDF has six unlabelled vector pages: five 300 × 218 mm landscape sheets
and one 218 × 300 mm portrait sheet. These are slightly larger than A4.
The portrait export must be placed/oriented to fit the physical plotter bed
before plotting; the export itself is a portrait art sheet.

## Script route for another series

The current arrangements are authored. They use recorded outputs of the
fixed-weight fly model, not recordings from living flies, and the new composite
pages have not been fed back into the model.

- `pieces-study/materials.py` / `materials.json` preserve seven earlier drawings
  from action-study seeds 31, 37, 41 and held-out seed 5. Bands retain recorded
  points; spines are simplified within 0.003 mm before placement. Separate pen
  runs and their gaps are preserved.
- `pieces-study/compose_flowing.py` defines Cross-current, Held open and
  Intervals. `flow(material_id, center, span, angle, paper, passage=...)`
  places an entire drawing or a named complete passage. `span` is the desired
  longest extent in mm, reduced if needed to keep the margin. `move_passage`
  changes one complete passage's placement without changing its shape.
- `pieces-study/encounter_candidates.py` has a `RECIPES` table for Return,
  Crossing and Wake. It combines recorded interrupted encounter responses
  with intact flowing drawings; it does not run a new brain simulation.
- `build.py` verifies source hashes and paper bounds, then writes the SVGs,
  gallery data and neutral contact sheet. `export_pdf.py` writes the portfolio.
  `render_verify.py` renders PNGs, checks source transforms/export equality,
  exercises the gallery and bundles downloads. `REVIEW.txt`, `evidence/` and
  `iterations/first/` retain the review and earlier arrangements.

To make a separate six-piece series, copy `pieces-study` to a **sibling** lab
directory, edit those two recipe files, and change both hard-coded gallery URLs
in the copied `render_verify.py` to the new directory. The builder currently
expects the same six candidate IDs. Keep the accepted series intact. Run the
two recipe scripts, `build.py`, `export_pdf.py`, then `render_verify.py` in that
order, and visually review all six outputs, including weaker ones.

Use the existing AxiBridge `.venv/bin/python` for the geometry/browser scripts;
the PDF script uses the bundled runtime at
`/Users/ianduclos/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`.
No installation is needed. Do not run `uv run` from AxiBridge to prepare an
unrelated experiment: it resolves this project's environment. Any further
isolated neural runtime must use an explicit scratch cwd and `--no-project`.

## What this round established and left open

Flowing material can carry most of a composition rather than decorate it.
The six pieces retain distinct amounts of open space and entanglement. Astra
reviewed neutral contacts and close views before mechanism labels. Its strongest
initial readings were Wake and Crossing; Cross-current improved substantially
with a diagonal placement. Intervals improved narrowly and still reads somewhat
like specimens arranged on a page. Originals and a rejected placement variant
remain available; this was not a beauty-score search.

The encounter comparison showed changed motor/drawing responses to an authored
page-relative cue, with exact sensory-replay controls. It did not establish
compositional intelligence or learning. A live instrument in which the brain
encounters the current composite page remains unbuilt. So does a direct UI for
these six-piece recipes. Ian's priorities are the earlier flowing line before
fine bundle, actual compositions, and perceptible consequences of feedback.

Verification: 1,503 placed flowing strokes match their source transforms;
source hashes and paper bounds pass; exported SVG paths equal display data;
six-page vector PDF rendered and inspected; gallery controls checked at 360,
736 and 1440 px with no browser errors. These are screen/export checks, not
paper verification.

## Environment follow-up

An earlier encounter-study command accidentally refreshed AxiBridge's `.venv`
through project-aware `uv run`. NumPy 2.5.3 caused nine existing 2D-cross-product
test failures. NumPy was returned to 2.2.6 and the non-UI suite passed; other
refreshed package versions remain. The original full package list was not
captured, so exact restoration cannot be claimed. `depth-pro` imports, but its
metadata declares NumPy <2; compatibility beyond that import remains unverified.
The incident record and displaced lockfile are in
`$LAB/encounter-study/results/`; final wrap-up test results are in STATUS.md.
No application source fix was made for this environment incident.
