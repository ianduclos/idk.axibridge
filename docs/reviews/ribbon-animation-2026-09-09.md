# Ribbon Seed blend animation — 9 September 2026

Ian's actual layer animation had Ribbon `seed_blend: 1` on A and `0` on B.
The generic scalar interpolation inferred integer rounding from those JSON
values, even though Ribbon declares this slider as float. At t=.25/.5/.75 it
therefore returned 1/0/0 instead of .75/.5/.25. The A/B setup was correct; this
was an effect-parameter typing bug, unrelated to device capability or bench
eligibility. Generator Watch is a separate time-axis interface.

`blend_effect_stacks` now validates each endpoint with the effect's parameter
model before interpolation, restoring declared numeric types. Integer controls
still round, equal seeds stay fixed, and input stacks are not mutated. This
fix covers matched effect stacks in both canvas tweening and tray blending;
it does not change standalone generator-parameter interpolation.

The new regression failed at all three intermediate positions before the fix.
Afterward 116 Ribbon, tween, tray and sheet tests passed (one existing Starlette
warning). The backend was reloaded using a distinct recovery project
`ribbon-tween-recovery-20260909-012338`; A/B layers, source anchors, transforms
and effects were verified preserved. Live t=.25/.5/.75 returns three distinct
20-strand frames. Native playback and paper output remain user checks; the
computation cost can still limit frame rate. No hardware operation or push.
