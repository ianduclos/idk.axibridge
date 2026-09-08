# Magnetic field bench implementation

Approved in conversation, 9 September 2026. Builds on the nine-cell visual
study and Ian's selection of continuous paths for lift economy.

## Accepted behaviour

1. A Magnetic field entry in Benches opens the existing popup shell. Arrange
   bars and independent north/south poles on a fixed drawing frame; drag to
   move, use a rotation handle or numeric controls, duplicate, flip and remove.
2. Continuous is the default; chains and filings retain the study treatments.
   Show magnets controls plotted bodies and pole labels. Hidden bodies retain
   their empty silhouettes by default; editing handles never plot. Ian's later
   filings reference adds an optional Keep empty silhouettes toggle: turning it
   off when magnets are hidden admits field lines into former body areas,
   stopping at small pole cores. This changes the drawn field geometry, not
   the positions or strengths of the underlying poles.
3. Remove escaping lines discards whole underlying routes that reach the
   drawing-frame boundary, before mark treatment. Popup size and zoom do not
   change the result. The frame is the generator's width/height, fitted to the
   bed through the existing placement_frame contract; later layer transforms
   and effects do not redefine the generator's boundary.
4. Scatter replaces the arrangement with a seeded distribution: count 1–16,
   bars/poles/both, random positions and bar rotations. Reshuffle advances the
   seed. Explicit resulting magnets remain editable and are saved in the recipe.
5. Working edits and undo stay local. Keep creates a new ordinary generator
   layer. Resume copies a kept recipe into a draft and Keep creates another
   layer; it never silently changes the original. Drafts survive popup closure
   during the current page session; project reset clears them.

## Architecture and limits

The registered pure Python source owns all generated geometry. The existing
preview endpoint and normal layer creation/resolve consume that source. The
JavaScript bench draws server lines and temporary handles, never substitutes a
second field solver. Only the latest recipe's completed preview can be kept.
Preview work is serial with a latest-request queue; moving a handle changes the
overlay immediately and requests a field on release. Pending geometry is dimmed.
The normal API may simplify preview points; indicate this in the bench readout.

Source params: width/height, density, style, show_magnets, keep_silhouettes,
remove_escaping, seed
and a bounded hidden list of explicit magnet objects. All object numerics are
finite and bounded. Default is the study's opposite-facing two-bar arrangement.
The simplified planar model is illustrative, not a force or material simulator.
No new dependencies, hardware action, automatic restart or API endpoint.

## Execution

1. Sol owns magnetic_field.py, an optional private geometry helper, and source
   tests: port the study, add whole-route escape metadata, annotation visibility,
   bounded termination and deterministic validation. Primary reviews integration.
2. Primary owns magnetic_bench.js, shared adapter/Compose wiring and existing
   bench-shell controls/styles. Follow its Flexoki variables and system faces.
   Use the catalogue defaults rather than duplicate the source's defaults.
3. Add real-browser tests before UI implementation, then verify editing,
   seed replay, hidden-body handles, escape removal, preview failure/races,
   draft closure, Keep/Resume, keyboard undo and narrow-window reachability.
4. Run source and bench regressions, typecheck, build, full hardware-free suite,
   isolated source-only browser smoke and screen inspection. Record actual
   generation timings and UI evidence; native/paper acceptance remains Ian's.
5. Update module docs, roadmap, status/handoff and commit verified changes.

## Default decisions

The UI starts with magnets visible and escaping routes retained. Scatter starts
with four bars; count/type are local action settings, while seed and explicit
positions are the saved recipe. Selection controls expose position, angle,
length, thickness and strength. Objects remain inside the frame when resized or
moved. Overlaps are allowed. A cleared arrangement produces an empty drawing.
Undo/redo is bounded to 80 local edits; a drag is one edit. Changes made while
Keep is in flight are disabled so its result has an unambiguous recipe.
