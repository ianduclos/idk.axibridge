# Magnetic field bench — 9 September 2026

The working bench follows Ian's approved study and preference for continuous
curves to reduce pen lifts. [Implementation contract](../../plans/magnetic-field-bench.md).

## Use

1. After restarting the app, choose **Magnetic field** in the **Benches** group
   and open **Bench**. Drag magnets to move; drag the round handle to rotate a
   bar. Position, angle, size and strength also have numeric controls. Add bars,
   N or S poles; duplicate, flip, remove or clear. Click paper to clear handles.
2. **Continuous curves** is the default. Chains and filings remain available,
   with the ink-path count making their greater lift demand visible.
3. **Show magnets** controls plotted bodies and pole labels. When hidden,
   **Keep empty silhouettes** retains the original gaps. Turn that off for the
   filings-reference treatment: curves enter former body areas and converge at
   small pole cores. Selection handles are editing aids only and never plot.
4. **Remove escaping lines** drops whole routes that reach the drawing-frame
   boundary before applying the mark treatment. It does not depend on zoom or
   popup dimensions. Changing the layer's later placement/effects does not
   redefine this generator boundary.
5. **Scatter** uses the chosen seed, count and type; **Reshuffle** advances the
   seed. Both replace the arrangement, and Undo restores it. Resulting magnets
   stay individually editable. **Keep as layer** creates a new ordinary layer;
   **Resume in bench** starts a working copy without changing the kept original.

## Screen evidence

| ID | Screen | Purpose |
| --- | --- | --- |
| 1 | [Default](default.png) | Continuous curves and editable bars |
| 2 | [Hidden, empty silhouettes](empty-silhouettes.png) | Original negative-space option |
| 3 | [Hidden, filled footprints](filled-footprints.png) | New reference-inspired option |
| 4 | [Escaping routes removed](contained-no-silhouettes.png) | Whole-route filtering |
| 5 | [Hidden magnet editing](hidden-editing.png) | Rotated bar remains editable |
| 6 | [Narrow window](narrow.png) | Controls reachable in an extreme 16-object, 40-mm frame |
| 7 | [Source-only](source-only.png) | Unbundled UI and Keep |

The later user reference was found as
`/Users/ianduclos/Downloads/magnetic-fields-iron-filings-flickr-oskay.jpg`
(the supplied `.webp` path did not exist). It guided the pole gatherings, not
a literal copy of the photograph. The tiny untraced pole cores prevent numerical
oscillation; there are no rectangular gaps when empty silhouettes are disabled.

The lead inspected the screenshots and retained the default sweeping structure.
Sol's bounded second-eye review also found the no-silhouette change consequential:
the curved passages take priority over rectangular cutouts. It noted that removing
escaping routes can leave broad, quiet margins, and that the deliberately cramped
16-object fixture is not evidence of a successful composition. These are optional
settings with different results, not a promise that every scatter is compelling.

## Verification

Final full hardware-free suite: **1,360 passed, one intentional native-app
lifecycle skip**, with the existing Starlette deprecation warning. No production
application restart or hardware check was part of that run.

1. Backend tests cover deterministic geometry, bounded finite inputs/output,
   empty and cancelling arrangements, hidden annotations and both footprint
   treatments, whole-route escape filtering, rotated small labels, orientation,
   Session regeneration/resolve and project save/load.
2. Real-browser tests exercise Keep/Resume preservation, seeded replay, local
   undo and Escape during drag, hidden-object editing, delayed preview races,
   failed-preview retry, small frames, narrow controls, empty drawings,
   cross-bench lifecycle and persistence of the footprint setting. The magnetic
   and shared bench regression run passed **29 tests**.
3. Typecheck passed. The isolated source-only smoke opened the new bench,
   disabled silhouettes, kept a layer and checked the saved recipe without page
   errors. The normal UI harness rebuilds and exercises the bundled frontend.
4. Agent-measured generation on this Mac: default continuous **0.116 s**,
   hidden/open **0.150 s**, 16-bar grid **0.822 s**. These are measured fixtures,
   not latency guarantees for every arrangement. The default output has roughly
   43,000 vertices; the existing API marks decimated previews as simplified.

## Limits

The model is a softened planar pole construction, not a calibrated magnetic
material solver. Working drafts and undo survive popup closure in this page;
reload recovery comes from a kept recipe. There are no new dependencies or
hardware paths. The live native app was not restarted, no hardware was used,
and paper appearance and actual lift/time savings remain for Ian to check.
