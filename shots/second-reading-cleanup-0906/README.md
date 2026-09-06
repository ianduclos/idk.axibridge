# Follow-up cleanup

`responses.png` shows ordinary Responsive output for seeds 12/23/42 at turns
4/8/12/20; `recipes.json` records each state and its decisions. Thick reinforcement
passes are absent. Thin echoes and occasional crossings remain possible.
`boundary-check.png` applies the same overshooting line to Clip, Turn inside and
Overshoot, demonstrating cutting, a rounded return and retained overshoot.
`bench.png` is the final UI on a temporary isolated server, showing .8 smoothing,
Randomize, explicit active boundary and the nominal dashed sheet.

Verification: 1,262 passed, 1 skipped; frontend build/typecheck and all 14 focused
Second Reading UI tests passed. Ready for Ian to check; no hardware used.
