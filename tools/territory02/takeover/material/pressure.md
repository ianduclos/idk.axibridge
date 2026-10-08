# Pressure experiment

`pressure.cjs` makes existing material push back on the takeover courses. It preserves the original texture population and its irregular strokes. There is no fill, hatch replacement, new ornamental curve, regrowth pass, inherited guidance field or procedural wave.

## Mechanism

1. Actual texture segment length accumulates in 2.5 mm occupancy cells. An 8 mm radial kernel measures nearby ink mass and its centroid.
2. Course samples compare material resistance 5 mm to either side of their local normal. Only unequal encounters qualify; a balanced mass does not receive an invented escape direction. The upper 30% of qualifying sampled densities, with a 12 mm weighted-ink floor, supplies candidates. Selected encounters remain separated in space and along a course.
3. Up to ten material encounters demand a 17–28 mm escape toward the lower-resistance side. The measured material centroid also supplies a small tangential drag. Material measured before/after the encounter sets unequal arclength reaches.
4. A local elastic displacement solve spreads those demands along each course. It diffuses displacement rather than original positions, preserving quiet bends. Dense shoulders have lower bending stiffness than clear bridges, concentrating turns instead of smoothing everything uniformly. Course endpoints remain anchored.
5. Base strokes and their nearby restatements follow the displaced course. Dense texture bodies resist this motion; thinner exits yield more, partially carrying adjacent course motion. Contributions from competing courses blend by physical proximity, permitting compression and stretched connectors without sudden ownership switches.

The complete result is clipped to the bed. The renderer keeps its shared 0.1 mm stroke width.

## Causal stages and events

- `occupied-material`: original courses and original texture.
- `curves-displaced`: displaced courses against the unchanged texture that exerted pressure.
- `filaments-yield`: complete final result, after the original texture partially yields.

Each `material-pressure` event records the affected course/source IDs, encounter position, measured mass centroid, weighted ink length, resistance on each side, demanded vector, unequal arclength reaches, resulting location and displacement. These records identify physical causes; they are not aesthetic scores.

## Limits

The coarse ink grid is a material approximation, not a collision simulator. Segment occupancy captures density but does not infer filled interiors. Some original crossings remain unresolved. Dense bodies can detach from their originating course while sparse exits carry only part of its displacement; that stubbornness is intentional but needs close visual review. Near bed edges, clipping can shorten pressured passages. Encounter selection is bounded and strongest-first; dense regions without a clear side difference remain quiet. No texture is regenerated from the moved geometry, so all history retained here belongs to the actual original material.

## Initial verification

Ran `node tools/territory02/takeover/material/render.cjs --mode=pressure --seeds=13,24,47`.

The renderer passed input purity, exact repeatability, finite bed coordinates and its physical limits for all three seeds. Results contain 19,980–46,408 points and 10.85–23.82 m of ink, with 5 / 5 / 3 pressure encounters respectively. These are mechanical checks only. The experiment is ready for the primary's raster inspection and possible revision; no aesthetic acceptance is claimed.
