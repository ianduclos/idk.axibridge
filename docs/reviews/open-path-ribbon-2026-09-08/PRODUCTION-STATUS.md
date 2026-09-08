# Ribbon production effect — 2026-09-08

Registered effect: **Ribbon** (`ribbon`), available after the backend next starts.
The production path is Python/Shapely; the original JS study remains a reference.
`check-port-parity.py` compares all six accepted source fixtures: maximum
Hausdorff distance 5.17e-14 mm at the accepted defaults.

The effect retains independent side wavelengths, seeded height/spacing rhythms,
normalized Seed A/B blending, round-outside/preserved-inside corners, self- and
cross-path masking with reverse priority, filled mask outlines, merged outline
output, optional centre-free interpolation, and assigned-pen automatic density.
Closed paths and dots bypass unchanged. Public dimensions are millimetres.

New controls:
1. Crest softening: zero bypasses averaging, .055 preserves the accepted profile,
   and larger values broaden sharp peaks. Uneven softening varies the averaging
   radius continuously between independent targets on the rising and falling
   flank of every crest, using a separate seeded stream; knot timing/heights do
   not change, though the smoothed profile's maxima can move or diminish.
2. Remove outer pairs: applies a shared cutoff to the original strand grid.
   With 10 pairs and a half-length path, removing 3 leaves 7/5 pairs; removing 6
   leaves 4/4. Surviving paths retain their exact positions. At least one pair
   remains, including in centre-free interpolation.
3. Collapsible Shape, Rhythm, Strands and Output groups. Shape opens initially.
   A larger popup editor is deferred, along with D3 as a separate effect.

Automatic density uses the assigned pen (0.5 mm unassigned), with 10% nominal
stroke overlap and a blend-stable count. Normal, region and tween contexts carry
that width; pen changes participate in relevant cache keys. It remains a nominal
coverage calculation: physical ink and extreme curved joins need paper checks.
Requests beyond 512 pairs or one million estimated sampled points fail explicitly.

Solid output represents a filled occlusion boundary, not a painted polygon or
automatic hatch. Use the layer's occlusion controls to mask other layers. Filled
rings are unioned before emission, preserving holes and avoiding partial-overlap
parity ambiguity. Combining strands with Solid occluder adds boundary paths.
Masking removes hidden line geometry, so SVG/plot output follows the preview.
No global intersection-free guarantee is made for arbitrary dense input paths.

`production-review.html` / `.png` shows the actual Python effect on straight,
corner and loop inputs at maximum height/spacing variation. The original study
and current native app were not overwritten or restarted. Final visual/paper
acceptance remains with Ian; no hardware action or push was performed.


Final verification: 1,322 passed, one intentional native-app lifecycle skip and
one existing Starlette warning. This includes built-frontend UI acceptance and
normal/region/tween/preview/consolidate/merge pen-context regressions. Typecheck
passed. Profile parity and six full fixture parity checks passed; the shortest
independent wavelength retains all 20 expected crests in its regression fixture.


Restart follow-up: Ian authorized discarding the current session. POSTing the
existing restart endpoint succeeded, and the live Mac `/api/state` now includes
Ribbon. The Settings menu had a hidden two-click confirmation: selecting it
closed the menu before the second click. It now uses an explicit confirmation
dialog. Both cancel/confirm UI regressions passed against the built frontend;
typecheck passed. The original shipping pass's no-restart statement above
records that earlier checkpoint, not the current backend state.
