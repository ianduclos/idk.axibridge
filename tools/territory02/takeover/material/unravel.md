# Unravel — extraction from developed grown material

Experimental geometry only. `develop` accepts the shared fixed input and returns
complete drawing strokes, four or fewer extraction records, and three stages:
`developed` (all actual course-led texture before the operation), `body-after`
(the body after material was pulled), and `extracted` (pulled fibers and carried
scraps alone). The lead owns visual comparison and acceptance.

The mechanism finds existing `d-grow` runs between their actual direction
reversals, ranks developed passages by nearby grain and distance to the approved
curve encounter, and lifts one exact contiguous source run. The original source
vertex range is recorded. The complete extracted run is displaced under tension:
its first point stays fixed, its old fine vertices remain, and its free end moves
roughly 50–80 mm. The displacement combines its grown direction and the local
approved course tangent. Paper room constrains the pull. This is a transformation
of an existing fiber, not a new flowline added over texture.

A variable-width corridor follows that grown run. At its irregular boundary,
existing polylines are divided by segment bisection. Small cut grain fragments
at two portions of the corridor may travel along the pull by rigid translation;
their interior irregular geometry is unchanged. Remaining fragments move outward
to the torn rim. The cavity therefore has actual displaced source material and
an accountable origin. Original coarse curves stay present, and crossings with
the displaced strands remain unresolved. Unaffected grain is neither resampled
nor regenerated. The original lifted core is removed before it is emitted once
as the pulled curve. A run already severed by an earlier extraction is skipped.

Records include original source stroke and vertex range, original run geometry,
fixed root, displaced tip, source/pulled lengths, corridor width, quantities of
carried/rim material, and up to twelve example fragment source/destination
records. Input objects are never mutated and seed use is repeatable.

Limitations to inspect: rim translation can thicken a boundary into a conspicuous
edge; existing grown micro-turns survive in the stretched strand; source ranking
is a simple density/encounter heuristic; the corridor follows an actual fiber but
its varying width is prescribed. Fragment transport is geometric, not a tensile
material simulation. Very short fragments below 0.12 mm are omitted. The shared
final clipping may drop out-of-bed fragments. These details need close visual
inspection, not acceptance inferred from counts.

Verification: `node tools/territory02/takeover/material/render.cjs --mode=unravel
--seeds=13,24,47` checks purity, repeatability, bounds, point count and ink length.
No holdout seeds, other makers, browser, hardware or production geometry involved.
