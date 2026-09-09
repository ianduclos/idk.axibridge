# Gentle-curve sampling correction

Ian's screenshot showed small kinks repeated across neighboring strands on a
Ribbon bulge. The exact source drawing was not available in the open project;
`input.json` reproduces the same kind of artifact with a smooth two-anchor Pen
Bézier at its default 0.2 mm flattening tolerance.

Ribbon subdivided each flattened segment, then estimated an offset direction at
each new point. The tangent stayed constant along a segment and changed at its
original boundaries. A modulating width magnifies those abrupt direction changes.

The correction blends the original gentle-curve vertex directions over each
segment. Collinear subdivisions do not become extra tangent knots. It keeps the
source polyline, sampling stations, seeded width profiles and point budget. Sharp
corners and their adjacent spans retain the existing miter/sweep treatment; the
hidden fractured mode keeps its exact historical geometry. No new parameter.

`comparison.png` shows the same crop and line weight before and after. The
reproduction retains 21 strands and 430 points per strand; maximum geometric
Hausdorff displacement is 0.0882 mm. This corrects the offset-field artifact, not
the underlying Pen flattening: a coarse input polyline can still show its own
facets at high zoom.

Regression checks cover a known gentle circular arc, preservation of true corner
frames, collinear subdivision invariance, unchanged profiles/point budget and the
accepted acute-corner/edge/fractured fixtures. Native appearance and paper output
remain for Ian to check. Existing curved recipes intentionally regenerate with
the corrected directions; old exported geometry is not rewritten.

A 20-run alternating timing check of this small strand-only fixture measured
5.90 ms before and 6.12 ms after (medians). The added direction interpolation
does not increase the generated point count. This small fixture does not
benchmark the cost of complex masked ribbons.

Full hardware-free suite: **1,428 passed, one intentional lifecycle skip**,
with the existing Starlette warning. The backend was reloaded with the current
empty project preserved; the exact screenshot drawing still needs Ian's check.
