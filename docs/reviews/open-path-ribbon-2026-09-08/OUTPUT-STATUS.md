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

## Mask overlaps across source paths

Ian requested that loop masking also work between paths. The UI control is now
**Mask overlaps** (engine option `maskLoops` retained for compatibility).
`generateMany` first applies each path's existing self-loop masking, then clips
its surviving strands against the union of all later input silhouettes. Reverse
order switches both the inter-path order and the within-path passage order.
The full retained-width silhouettes are blockers; individual strand gaps do not
leak lower paths. Per-fragment strand indices are retained. Closed bypassed paths
remain outside this open-ribbon masking policy.

The new Crossing paths fixture demonstrates the order change. `multi-mask-check`
passes inter-path cuts, intact top path, reversal, unchanged silhouette, provenance,
determinism and single-path compatibility. Length/output checks pass too. Browser
checks cover the new fixture, mask toggling and reversal; `cross-path-masking.png`
records the preview. These are study checks, not installed-app validation.

## Edge interpolation and pen-based density

`interpolation:'edges'` blends signed widths directly from one outer envelope to
the other, before the existing corner regularization. It uses `2*steps` strands
(an even count), avoiding a dedicated original or midpoint strand. The original
remains internal reference geometry only. The default `spine` mode is unchanged.
Length trimming removes pairs from the ends of the full edge-interpolation grid;
it never redistributes survivors. A trimmed asymmetric band can drift away from
the source, so its silhouette uses the interpolated band centre as its sweep
reference rather than incorrectly filling back to the original path.

`autoDensity` requires `penWidth` in path-coordinate units. The UI reads that
from the selected saved pen's `line_diameter_mm`, converted using the declared
160 mm default source horizontal span. `pen-widths.json` is a snapshot from the
local saved pen library taken this turn, not a live connection to the app. The
pen selector includes the saved 0.2 mm Uniball and three 0.4 mm presets. Changing
saved pens in the app does not refresh an already displayed study. Production
integration should obtain the assigned layer's pen directly.

Density targets a maximum sample cross-section gap of 90% of pen width. It budgets
both seed endpoints and the normal/miter frame magnitude conservatively, holding
one count throughout the seed blend. In multi-path collections it chooses the
largest required count before length trimming. A cap of 512 per-side steps has
an explicit `densityLimited` diagnostic and visible status; this is not silently
reported as solid. The preview uses the actual scaled pen width when auto mode
is active. Pen spread, curve/corner topology and paper still need physical
validation; no blanket ink-coverage guarantee is made.

`edge-density-check.cjs` passes even/no-centre interpolation, equal straight gaps,
exact outer edges and trimmed survivors, legacy defaults, seed endpoints,
auto-density gap bounds, thinner-pen monotonicity, stable blend counts and cap
reporting. Output checks include the displaced trimmed-band silhouette. Browser
checks cover the pen selector, auto/manual count switching and 360/736 layouts.
The lead inspected `edge-corner.png`, `edge-auto-density.png` and the dense loop
preview. Ready for Ian to check. No app source, hardware or saved pen settings
were changed.
