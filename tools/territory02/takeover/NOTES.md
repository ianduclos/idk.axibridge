# Territory02 takeover probe

Ian rejected the later panel fills; the current [texture study](texture/index.html)
restores the earlier full textural baseline and tests its growth on these
unchanged curves. Integration remains open. [Texture notes](texture/NOTES.md).

The later [course-bound fill study](fill/index.html) responds to Ian's concern
that stronger curves were less coherent and fills remained untouched. Its two
constructions retain these curves; findings and limits are in [fill notes](fill/NOTES.md).

A screen experiment after the independent three-maker study. Ian asked for a
radical new curve regime: tighter stylized bends, more intricate passages, and
permission to modify Territory's courses. His sketch and paintings are visual
food, not coordinate templates. He rejected both literal fold recipes and a
subsequent version that still lacked bulbs and corners.

Open `index.html` to compare the unchanged Territory output, first intervention,
and a second pass that consumes the first pass's actual geometry. The original
three studies remain separate. No convergence or production integration has
been selected. The lead report is
`../../../docs/reviews/territory02-takeover-2026-10-05.md`; the bounded independent
Sol reading is `../../../docs/reviews/territory02-takeover-sol.md`.

## Current construction

- Territory supplies migration centreline courses. The pass finds encounters
  between those courses, moves and rotates their neighborhoods, and relaxes them
  with unequal resistance to bending. It does not look at reference-image pixels.
- The second pass can exchange real course continuations and cut courses. An
  exchange changes the network; the next encounter is found on the new geometry.
- Cubic fitting selects separated substantial bends and joins from that network.
  It inflates perpendicular control components along the incoming span, uses a
  very short incoming handle at selected turns, and allows entry and exit tangents
  to disagree. This creates swelling, tight returns and genuine corners. It is
  an explicit geometric bias, not an assurance of aesthetic variety.
- A few short restatement strands follow actual courses with unequal ends.
  Weight is physical line geometry: every visible path uses the same 0.1 mm
  stroke, no opacity, filled shapes or synthetic brush texture.

Stage 0 is the complete ordinary sparse Territory rendering, including its hand
and bundles. Stage 1 starts from Territory's latent centreline courses, so it
also removes that ordinary rendering treatment. It does **not** preserve or edit
every emitted hand stroke. Stage 2 consumes Stage 1's returned courses; short
restatements are redrawn rather than fed back as extra courses. Density is zero
throughout. This probe bypasses production's event, density and renderer
contracts; a port needs its own design and verification.

## Evidence and checks

Development seeds: 5, 13, 18, 24, 47, 82. The current source was frozen before
first rendering seeds **107, 173, 227, 281**. Earlier holdouts 31, 69, 103, 151
were inspected for the previous fit and are archived with trial4; they are not
fresh evidence for the current fit. `frozen-source/manifest.json` records the
current SHA-256 and populations. No tuning followed the current holdout view.

The renderer checks repeatability, unchanged Territory inputs, finite geometry,
the 300×218 mm bed, a 100 m ink budget and a 250k point budget. Synthetic checks
also exercise frozen inputs and repeated passes. Those are mechanical checks,
not beauty scores. A browser check loads all 60 whole/detail SVG views and checks
navigation, links and desktop/mobile layout. All close views share a recorded
100×70 mm window across stages, chosen around the second pass's first pressure
site; that automatic window can miss a more important passage elsewhere.

Whole-population PNGs, matched detail PNGs, JSON and source snapshots are saved.
SVGs and embedding HTML are reproducible generated files omitted from Git.
`evidence/blind/` preserves the previous fit's initial neutral review and removal
counterfactuals. `evidence/blind-bulbs/` contains the current neutral populations.
A review of the previous fit does not count as acceptance of this fit.

## Failed trials

`trial1` and `trial2` preserve preset fold/pinch recipes that followed Ian's
illustration too literally. Their development captures are exploratory records;
not every intermediate screenshot is a reproduction of the final archived
module. `trial3` retains the first contact/continuation fit, which simplified
many courses into angular stretches. `trial4` is the frozen contact/torque fit
reviewed under L/Q/T; Ian still found insufficient bulbs and corners.
`trial5` inflated controls throughout and produced repetitive teeth and spikes.
The current fit confines inflation to separated bends, keeping the weak cases
visible rather than replacing the population with selected highlights.

No physical plotting, native app restart, Pi action, or human/machine interactive
response test was performed. Thin screen paths may merge differently on paper.

## Reproduction

From this worktree, build `tools/territory02/experiments/baseline` with its local
`sh build.sh` if its generated engine is absent; it writes only its local engine.
Then run:

```sh
node tools/territory02/takeover/check.cjs
node tools/territory02/takeover/render.cjs
node tools/territory02/takeover/render.cjs --holdouts
node tools/territory02/takeover/review-evidence.cjs
```

Use a Python runtime with existing Playwright/Chromium to run
`tools/territory02/takeover/capture-evidence.py` and `check-viewer.py`.
The capture script produces the current population/detail PNGs and neutral
review images. The original repo's `.venv/bin/python` is such a runtime here.
The earlier blind review images are retained PNG evidence, not recreated by the
current renderer. The current module exactly matches `frozen-source/rewrite.cjs`.
