# Edge interpolation joins — 9 September 2026

`input.json` records Ian's actual pen path with edge interpolation and its
layer-derived seed. `stable.png` / `.svg` / `.json` are the integrated candidate.
`render.py stable` regenerates them through the real compositor.

## Regular edge mode

Independent envelopes can exchange relative width inside a joined corner
support. Intermediate lanes then change sides, and the old same-side strip
union follows the source boundary, producing slits and shared routes.

The repair preserves total width at every source station while stabilizing the
left/right allocation through each corner support. Allocation is the ratio of
arc-length-integrated left width to integrated total width. Short smoothstep
transitions reconnect the independent profiles outside the support. This makes
lanes fixed fractions of a single same-side profile inside each join. Spine
interpolation and paths without sharp corners retain their previous geometry.

Tradeoff: neighboring acute corners can merge into a long support, so local
asymmetry can change across a substantial part of a tangled path. This is
intentional regularization, not preservation of the original outer boundaries.
It is not a general proof against intersections on arbitrary looping paths.

The actual fixture retains 20 strands, with no self intersections, crossing
pairs or shared interior routes. Total-width preservation, fixed join ratios,
input purity and unchanged regions are covered by regression tests. Six original
spine study fixtures still match within 5.17e-14 mm Hausdorff distance.

## Preserved experiment

Ian corrected the desired experimental reference to `download (1).png`, which
matches `ordered.png`: the polygon-cutout reference-region trial. Set Ribbon's
hidden parameter `fractured_edges: true` with `interpolation: "edges"` to use it.
The ordinary form hides this flag. Default is false; spine mode ignores it.
`tests/test_ribbon_fracture.py` verifies the production flag reproduces every
coordinate in `ordered.json`. Deliberate polygon fractures/crossings are part
of this experiment and should not be used as regular corner repair.

## Review and exploratory archive

`stable-review.html` compares A: old edge mode; B: integrated regular candidate;
C: preserved experiment. The Sol second-eye review selected B for regular mode,
noting the loss of some angular severity; see `STABLE-SECOND-EYE.md`. The review
initially used `balanced` (sample-weighted prototype); the final `stable` uses
arc-length weighting and was visually inspected by the primary.

`after` is the failed zero-crossing split trial; `arc`, `paired`, and `paired-arc`
are correspondence experiments; `balanced` is the successful prototype.
`trial-*.py` and `proposed_regression.py` are historical diagnostic sources,
not production code or accepted standalone tests. `comparison.*` compares only
the first failed trial, not the final candidate. Tests and screen review remain
provisional until Ian checks the live effect and paper output.

## Verification and live reload

Full suite: **1,363 passed, one intentional lifecycle skip**, one existing
Starlette deprecation warning. Backend reloaded with the current drawing saved
to a distinct `ribbon-edge-recovery-20260909-003112` recovery folder, then
restored. Layer IDs, anchors, effect parameters and transforms match; live
resolved coordinates match `stable.json` exactly. No hardware action or push.
