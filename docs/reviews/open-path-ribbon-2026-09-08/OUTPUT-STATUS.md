# Silhouettes, outlines and length-based width — 8 September 2026

Requested by Ian after accepting the crest and normalized seed-blend studies.
This is still a standalone study. No registered effect, application UI, running
server or hardware changed.

## Outputs

`outputMode` selects `strands` (default), `outline`, or `solid`. The selected
output is `drawingPaths`; `strands` remains available as construction geometry.
Outline mode contains boundary rings only, including hole boundaries; no centre
or intermediate strands. `mergeOverlaps` unites overlapping areas and removes
internal edges, including overlaps between separate input ribbons. Raw outline
mode keeps the connected outer edges and may self-cross. Solid mode always uses
the union and is displayed as a black region; this does not add a plotter fill.

`solidOccluder` emits closed `{points, filled:true}` entries in `occluders` and a
multipolygon in `silhouette`. It is independent of strand/outline display; solid
mode implies it. The lower-layer checkbox demonstrates actual segment clipping,
not an opaque preview patch. Holes remain transparent, and lines exactly on the
boundary are blocked. The filled metadata is the existing app's occlusion
contract, not an instruction for a pen to paint a filled area.

Silhouette union uses triangles swept between each retained outer edge and the
source spine, with original station correspondence through regularized corners.
This avoids winding cancellation at self-crossings. Multi-ribbon masks are united
before emission so nested filled rings preserve the app's even-odd hole semantics.
Large tight bends can leave small genuine holes or thin features; this mode does
not fill holes deliberately. Shapes retain floating-point polygon union limits.

## Trim width by path length

`generateMany(inputs, options)` measures source arc lengths. With `widthByLength`,
it retains `ceil(steps * length / longest)` strand pairs (at least one); the
longest keeps every pair. Retained strands use their ORIGINAL fractions of the
full width, so no surviving line moves. The effective boundary and solid mask
follow the outermost retained pair. Width changes are discrete pair removals.
Single-input collections retain full width. Closed source paths bypass the effect
and do not set the longest-open-path reference. The four example paths share
seed settings; per-input seed diversification remains a future policy.

## Verification and reproduction

1. `node .../silhouette-check.cjs`: union, holes, purity, closure, collinear
   boundary clipping and visible hole interiors.
2. `node .../output-check.cjs`: 12 fixture/mode cases, filled metadata, raw/merged
   outlines, two-ribbon overlap union and mixed closed/open bypass.
3. `node .../length-width-check.cjs`: exact retained-strand equality, proportional
   counts, unchanged corner survivors and single-path full width.
4. `.venv/bin/python .../occlusion-contract-check.py`: six generated silhouettes
   match the REAL `compose.build_mask` region, including holes, and the app's
   `clip_paths` removes covered portions of lower paths. Runs with temporary
   config and no hardware. Study coordinates are not production millimetres.
5. `check-study.py`: all prior browser controls plus output switching, source-line
   removal, merging, actual lower-layer length reduction, solid preview, and
   21/17/11/5 strands on the four length fixtures. 360/736 layouts remain checked.

Here `...` means `docs/reviews/open-path-ribbon-2026-09-08`. Existing crest and
seed-blend numerical checks passed too. The lead inspected `outline-occlusion.png`,
`solid-occlusion.png` and `length-width.png`. Ready for Ian to check; no physical
output or full application suite was run. Installing the effect requires the
separate Python/Path integration already noted in the study README.
