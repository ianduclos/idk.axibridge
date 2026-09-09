# Animation random identity — 9 September 2026

An untouched Animate A/B could change its random field at t=.5 because B had a
fresh layer ID and tweening switched context seeds at the midpoint. Ribbon
exposed this clearly by XORing its visible seeds with the layer context seed.
Separately, equal generator/effect seed=0 was deliberately rehashed per frame,
which contradicted the requested invariant that identical keyframes stay static.

## Shared fix

CanvasLayer has optional bounded 32-bit `effect_seed` metadata. None preserves
the existing ID-derived field. Animate B and appended keyframes inherit the
original effective seed; A's existing appearance stays exact. Both compositor
and tween contexts use the helper and their effect-observable cache keys include
it. Serialization and undo preserve it. Ordinary duplicates, split hatch layers
and exploded independent frames reset the override. Capture interpolation honors
an explicitly changed override at each endpoint.

Equal explicit seeds, including zero, now stay fixed. Differing seeds keep the
existing per-frame variation policy. Generator and effect endpoint parameters
are typed through their module model before blending, also in nested generator
and capture paths. This extends the preceding effect-only numeric fix.

Future effects must use ctx.seed, never layer IDs or mutable global RNG state;
future generators must be deterministic from their stored parameters. These
rules and tests live in docs/MODULES.md, ARCHITECTURE.md and
`tests/test_animation_random_identity.py`. Fresh probe modules verify shared
behavior without special-casing Ribbon; a real Ribbon regression checks the
midpoint too. Independently authored layers with different fields still retain
their endpoints; old animations are not silently rewritten at load time.


## Verification and live state

Full suite: 1,399 passed, one lifecycle skip, one existing Starlette warning.
After final independent-copy and capture-endpoint safeguards, 105 focused tests
passed. The real saved Ribbon pair at .4999/.5/.5001 matches direct evaluation
with A's original field exactly (20 strands), including a project save/load.

The app was empty during preflight, then Ian opened a Homeostat drawing during
the reload. The reload helper did not observe an empty post-restart state and
stopped before restoring its empty recovery. Subsequent state confirms the new
backend schema and the Homeostat drawing intact; do not restore the empty
recovery over it. The prior Ribbon A/B pair is repaired in a separate project:
`~/AxidrawProjects/ribbon-midpoint-repaired-20260909-015259`.

No hardware action or push. Native playback remains Ian's check. The shared
fix applies automatically to new Animate/append operations; older manually
authored independent keyframes retain their existing field choices.
