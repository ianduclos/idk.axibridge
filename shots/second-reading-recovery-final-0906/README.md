# Second Reading — final recovery experiment

First remains the default. The Shape and Relation experiments are optional.
This population is the pre-review study's same recipes after one focused change:
echo deformation follows travelled length instead of captured-point index.
The repeated right-bend hooks disappear; the original small central cusp survives.

A/B/C: First / Shape / Relation. Rows: seeds 1,4,12,23,42,91.
Columns: t5,t6,t8,t12. Same prefix/input through t5; reading changes at t6.
F: clip / containment / whole-fit, seeds 4/12/42 at t16. These are whole-run
boundary comparisons, not fixed-final-prefix causal ablations.

Start with `alternating-exchange.png`: actual lead-driven pointer captures,
with each successive stroke chosen after inspecting the preceding answer.
The last machine passage continues older ink and leaves the latest stroke alone.
`bench-*.json` stores the actual events; screenshots retain the observed UI.
The Kept screenshot/project preceded a discovered portrait-placement defect;
`bench-kept-project-after-placement.json` and `kept-on-bed.svg` show the corrected
same recipe within the bed. Screenshots also precede the final control visibility
cleanup. `bench-final-ui-resumed.png` and `kept-final-canvas.png` show the corrected final UI and placement. These are evidence of use and debugging, not Ian's acceptance or paper.

Reproduction:

```
.venv/bin/python tools/second_reading_recovery_study.py --output /tmp/second-reading-final
.venv/bin/python tools/second_reading_exchange_sheet.py --output /tmp/second-reading-exchange
```

Detailed artistic judgement, recovery provenance, reviewer calibration and
verification: `docs/reviews/second-reading-0906-lead.md` at repo root.

`controls.png` and `controls-recipes.json` compare Attention/Departure/Scale
independently at 0/.5/1 for seeds 12/23 after a fixed prefix/input. Reproduce with
`tools/second_reading_control_sheet.py --output /tmp/second-reading-controls`.
Scale changes interval width but currently leaves an echo's extent target-led;
see the lead report for this experimental limitation.
