# Open-path ribbon study — 8 September 2026

Exploratory geometry and an interactive comparison based on Ian's A–E sketches.
This is not an installed AxiBridge effect. No application source, project state,
hardware or running server is involved. Coordinates are study units, not mm.

Latest follow-up: `CREST-STATUS.md` records the phrased crest experiment and its
independent spacing/height controls. `LOOP-STATUS.md` records the loop sample
correction; `STRESS.md` records the preceding 156-case sweep of the original mode.

## What is being compared

The source is measured by arc length. Two positive width profiles use alternating
crest/trough knots with horizontal-tangent cubic interpolation. Intermediate
strands are fixed fractions between the original and each outer edge. Every
strand shares the original endpoints. Closed inputs bypass the effect.

Mirrored sides share a profile. Related sides share a rhythm with small height
and spacing deviations. Independent sides use separate deterministic streams.
Variation changes irregularity; zero keeps a regular swelling rhythm. A fixed
strand count naturally makes pinches darker than wide passages. The prototype
uses a short fixed endpoint taper. Sharp corners now use a local swept-strip
boundary with a rounded outside turn; see CORNER-STATUS.md for the follow-up.

The original mode includes occasional suppressed crests. The new Phrased mode
groups 3–5 crests with a shared timing motif and one accent, blending toward
independent events at zero phrase strength. Spacing and height variation are
separate. Editable anchors and manual crest placement remain future possibilities.

## Lead reading

The corner gives this effect more to respond to than a straight line: the dark
hinge interrupts the upper and lower rhythms differently. Repeated symmetric
bulges readily become beads. Longer wavelengths are therefore the interactive
default, while the sheets retain the denser comparison to expose this weakness.

The independent side mode is worth keeping even if related sides remain the
starting direction. The unrestricted hairpin's folded eye is an interesting
option rather than a reason to promise that all crossings will be removed.

Sol's image-first reading is recorded in SECOND-EYE.md. Its first pass used
neutral IDs; review-map.json was disclosed afterward. The review supports the
corner and return, and finds the side modes less different than their names
suggest. The lead agrees; stronger controlled asymmetry is a useful next probe.
The report predates removal of narrowing. Current sheets are regenerated without
it; `narrowing-rejected/` preserves the last rejected experiment, not an exact
snapshot of the earlier image-first pass. In the current population P11 instead
compares the same unrestricted return at a smaller width.

## Rejected narrowing experiment

Optional curvature narrowing is not accepted. Initial per-strand clipping made
several strands coincide; clipping the outer envelope before interpolation
corrected that. Curvature estimates then alternated between original and inserted
vertices, producing sawteeth. A fixed arc-length neighbourhood reduces but does
not eliminate the ripples. The protected-hairpin continuity regression failed.
The lead offered rollback versus investigation under the repository's two-fix
rule, then selected the recommended removal under Ian's delegated discretion.
The delivered engine and controls contain no narrowing option. Crossings remain
possible and are stated in the visual. Do not treat the archived P11 as useful
narrowing. Evidence of the failed experiment remains available for future work.

## Files and reproduction

`geometry.js` is the temporary geometry engine; `study-template.html` supplies
the controls. `check-study.py` assembles the thread's inline fragment and uses
headless Chromium with the installed visualization style kit. It records layouts,
control behaviour and neutral comparison images. The kit/output paths are local
to this Mac and task. `geometry-check.cjs` verifies the numerical contract.

The corner/masking follow-up adds `corner-check.cjs`, `masking-check.cjs` and
`overlap-check.cjs`, plus matched images from `corner-evidence.py`.

Run from the repository root:

```sh
node docs/reviews/open-path-ribbon-2026-09-08/crest-check.cjs
node docs/reviews/open-path-ribbon-2026-09-08/geometry-check.cjs
node docs/reviews/open-path-ribbon-2026-09-08/corner-check.cjs
node docs/reviews/open-path-ribbon-2026-09-08/masking-check.cjs
node docs/reviews/open-path-ribbon-2026-09-08/overlap-check.cjs
.venv/bin/python docs/reviews/open-path-ribbon-2026-09-08/check-study.py
```

Final geometry checks pass: deterministic output, input purity, finite points,
shared endpoints, mirrored correspondence, regular zero-variation profiles,
sampling bounds, exact stress-case interpolation, and closed/degenerate inputs.
Browser checks pass for six fixtures at two widths, including optional
overlap masking and order inversion,
seed changes, strand count, source highlighting, finite SVG coordinates and
360/736-pixel layouts in light/dark appearance. The lead inspected current
drawings and enlarged corner/return views. These checks do not establish visual
quality. Ready for Ian to check; no paper output was tested. The full application
suite was not run because no application code changed.

Before production: settle local folds, strengthen side relationships, decide
trough depth and taper controls, define multiple-path seed stability, and adapt
to the existing pure Python effect/Path contract in millimetres. D1 and D3 are
deliberately outside this first study.
