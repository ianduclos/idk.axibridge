# Magnetic corners and Scatter extension

Implemented on main at Ian's request, 9 September 2026.

## Interaction

1. Scatter has minimum/maximum relative strength (0.1–3, both initially 1).
   Editing one bound beyond the other moves the other bound to it. Same seed
   and action settings repeat the unlocked distribution. Lock during Scatter
   preserves that indexed magnet exactly; count cannot remove a locked slot.
2. Store four arrangements as A (top left), B (top right), C (bottom left),
   D (bottom right). Recall returns to a corner; Replace updates its capture.
   X/Y sliders enable after all four are stored. Current magnet count, kinds,
   polarity, manual sizes and frame are held while any corner is stored.
   Scatter keeps the same indexed objects in this mode, moving/rotating and
   changing strength only for unlocked objects. Clear presets restores
   structural editing without deleting the current arrangement.
3. Positions and strengths blend with bilinear corner weights. Angles unwrap
   B/C near A, then D near their mean, before blending and wrapping back into
   the angle range. This avoids the ±180-degree jump during interpolation;
   conflicting corner rotations can still choose a longer turn on an edge.
   Magnet bodies fit inside the frame, with temporary scaling if needed.
   Separately captured canonical sizes prevent this from accumulating shrinkage
   or becoming size interpolation. Locks only constrain Scatter.
4. Sliders update magnet handles immediately and queue serial field previews;
   stale results cannot become the kept recipe. Each input gesture is one Undo
   entry; Escape cancels it. Manual pose edits retain the corners and mark the
   arrangement manual until the sliders or Recall are used again.
5. Keep saves the explicit resulting magnets, presets, canonical sizes, slider
   state, locks and strength range in the normal source recipe. Resume restores
   them. These editor fields do not change server-generated geometry by
   themselves. The field is regenerated from magnets, not morphed between SVGs;
   route counts can change during a blend.

## Pole spacing

Zero preserves the previous drawing. Positive spacing greedily rejects whole
routes based on their nearest sampled approach within 12 mm of each pole.
This runs after escaping-route removal and before chains/filings. Surviving
routes are unchanged; it introduces no new breaks or pen lifts. This is not
a guaranteed minimum distance between all curves.

[Matched comparison](spacing-sheet.png), [measurements](spacing-metrics.json)
and [renderer](render_spacing.py). A row shows visible magnets, B hidden
magnets without silhouettes. Columns 1/2/3 use 1/0/0.3 mm respectively.

Primary reading: high spacing can erase the sweeping structure, especially
with hidden bodies. Preserve zero as the default. Sol's independent informed
review preferred A3 (0.3) over dense A2: pole halos, central eye and a few long
sweeps give the spaces different shapes. It found B1 weak (isolated lobes and
an accidental-looking horizontal remnant), while protecting A1's lone low
U-shaped sweep. Agreement on the sparse limit does not establish paper quality.
Values 1–3 are available for deliberate near-erasure, not recommended defaults.

## Verification

Browser coverage includes seeded strength variation, locked slots, fixed preset
identities, four corner recall, mid-square values, angle wrapping, gesture Undo,
Escape during a held preview, Keep/Resume and narrow controls. Direct JavaScript
math tests exercise exact corners, square samples, fit bounds and canonical
size restoration. Source tests cover bounded metadata and presets, JSON
round-trip, geometry neutrality and whole-route thinning order/subsets.

Full suite: 1,387 passed, one intentional native lifecycle skip and one existing
Starlette warning. Typecheck and isolated source-only smoke passed. The final
count-display correction is covered by a separate rebuilt magnetic browser run.
Screens: [four corners](four-corners.png), [mixed](mixed.png),
[narrow controls](corners-narrow.png), [unbundled frontend](source-only.png). Images are screen evidence;
the main app was not restarted and no hardware or paper test was performed.
