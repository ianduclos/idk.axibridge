# Territory v2: web prototype and blind review (29 September 2026)

This is an AARON-adjacent bench experiment, not an imitation. You draw hidden **cores**, and the machine draws only what they cause.

- v1 artifact, *Cores and Skins*, with proposals A Pursuit, B Territory and C Find space: https://claude.ai/artifact/LPvKv1yKahSiEKVZv2Gf8M. Ian preferred B.
- v2 artifact, *Territory*, which develops B: https://claude.ai/artifact/Bawx12VN4uRgWR2wU2Lso3.

Both artifacts are private.

## Roles this round

- Fable advised on system design twice: the v1 critique and the v2 field model. Its advice changed the field (a sharp log-sum-exp per camp), the border tracing (from the territory map, with stochastic fading), the history rule (draw only runs more than ~4 mm clear of old ink; small moves held back until they add up or the territories merge or split), voids (their own camp that cannot be entered), and the interior vocabulary (no iso-hatch).
- Sonnet did the drawing review, on Ian's instruction. That replaces the drawing-review skill's Sol default for this round. The report is `docs/reviews/territory-v2-0929-sonnet.md`.

## The reviewed sheets

Labels are neutral. Cell *n* is the same random core set and seed in every sheet: `randomSheet(n)` in `prototype/territory-engine.js`. The recipes are in `recipes.json`.

| Sheet | Recipe |
|---|---|
| K | borders + outer edges |
| L | v1 Territory (control; voids ignored) |
| M | borders + outer + voids + interior |
| N | borders + voids + interior (no outer edges) |
| O | borders + outer + voids |

The close views show cells 3 and 7 of K, M, N and O.

## Changes after the review

The published v2 differs from the reviewed sheets. The sheets predate these changes, so they don't reproduce the published defaults exactly.

1. Interior marks are capped at two per drawing and are mostly lines crossing into a neighbour. The review said the spines read as scaffolding.
2. Void reach is ×2.2, up from ×1.6. The review said voids rarely bind.
3. Dash gaps vary from contour to contour.
4. Auto camps use 90 mm noise and a weaker weight bias, and the default reach is 15 mm, up from 12. Before this, 11 of 24 population sheets had no borders at all; now 4 do.

`artifact-final.png` is the published page after a scripted pointer stroke, with the population sheet open.

## Reproduce

The prototype is plain JS. `node prototype/sheet.js <config.json> out.html` renders a contact sheet (the configs have the shape of `recipes.json` plus cells), and `prototype/shoot.py` screenshots it with the repo venv's Playwright.

## Status

Screens only: nothing has been plotted. Ian has not judged v2 yet. Nothing is in `axibridge/` yet. The port would be a bench over the `second_reading` event model.
