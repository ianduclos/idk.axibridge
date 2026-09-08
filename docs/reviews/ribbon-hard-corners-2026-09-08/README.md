# Hard-corner ribbon repair — 8 September 2026

`input.json` is the actual pen layer and Ribbon settings captured read-only from
Ian's live session after his 23:44 screenshot. `before` uses the shipped helper;
`after` uses the corrected helper. The comparison holds source, seed, blend,
widths, strand count and masking order fixed. It is shown in portrait orientation.

Cause: join supports were clipped separately at adjacent corner midpoints and
rounded to overlapping source samples. Splicing them reversed station order,
violating the masking sampler's assumptions. On the actual layer-derived seed,
three outer joins also failed boundary-route selection and retained raw offset
folds, producing 17–29 mm diagonals. The initial diagnostic agent used a different
seed and did not reproduce those fallbacks; primary runtime tracing did. Miter
capping also reduced the recovered round-join radius on near-reversals.

Repair: merge overlapping join supports before sweeping, including overlaps
introduced by source-sample rounding, and include every corner in that cluster.
Recover each strand's true signed width from the offset frame, even at a capped
miter. The resulting nested strip boundaries retain rounded outer turns and
sharp inner creases. Geometry projections use GEOS rather than nested Python
segment scans; this optimization left the rendered routes unchanged.

Evidence: the captured fixture keeps 21 strands. Self-intersecting strands drop
from 20 to zero, and crossing strand pairs from 53 to zero. Station order and
absence of long fallback diagonals have regression tests. All six earlier full
study fixtures still match their accepted coordinates to 5.17e-14 mm. This is
not a guarantee for every possible self-crossing input path.

`SECOND-EYE.md` records a neutral A/B visual review. The lead accepts the rounder
small elbow: the adjacent snag in the previous version was part of the folded
join. The stronger lower crease and width modulation are retained. Screen
inspection is provisional; Ian's app and paper acceptance remain outstanding.


Verification: 1,326 passed, one intentional native-app lifecycle skip, one
existing Starlette deprecation warning. The frontend was built by the suite's
UI acceptance harness. `cluster.*` retains the first successful geometry before
projection optimization; its routes and the final `after.*` routes coincide.

Live installation: the current untitled project was saved to a distinct recovery
folder, the backend restarted, and the project restored. Pen geometry was
regenerated from its unchanged anchors to avoid SVG snapshot rounding. The live
resolve confirms 21 strands, zero self-intersecting strands and zero crossing
pairs. Recovery: `/Users/ianduclos/AxidrawProjects/ribbon-corner-recovery-20260908-235643`.
The project name, layer IDs, source parameters, effects and transforms were
verified after restoration. Native visual/paper acceptance remains with Ian.
