---
project: idk.axibridge
updated: 2026-07-27
entries: 4
---

### Push + idkpi pull: the module roster changed — opened 2026-07-25, updated 2026-07-27, owner: ian
- done: everything merged to `main` and green (suite 559). This session added
  a new EFFECT (`offset_fill`) and a new SOURCE (`brush`), and merged the
  pending `feat/ui-round-0726`. Earlier: the four 07-25 branches (pen tool,
  geometry morph, hatch connect, nested tween) and `feat/hatch-connect-v2`.
- next: (1) push `main` to origin — 48 commits ahead, never yet pushed,
  needs Ian's OK; (2) pull the idkpi clone, which is now a HARD requirement
  rather than hygiene: `tests/test_app.py::test_state_shape` pins the effect
  roster as a contract and `offset_fill` is in it, so the shared suite FAILS
  on the Pi until it pulls; (3) delete the merged local branches
  (`feat/ui-round-0726`, `feat/offset-fill`, plus the six older merged ones).
- blockers: none — routine, but (1) is Ian's call by standing rule.
- context: `git log --oneline origin/main..main`; the roster assertion is
  `tests/test_app.py` ~line 22; `.claude/skills/pi` is the Pi runbook.

### Bench eye-check: offset_fill + brush — opened 2026-07-27, owner: ian
- done: both modules built, merged and screen-verified only — `offset_fill`
  via rendered PNG sweeps across square/circle/donut/dumbbell/star/L/two-holes
  and a `round_center` 0→1 grid; `brush` via Playwright against the real UI
  (4 strokes, erase bite and repaint bulge both visible, no console errors).
  23 + 17 tests respectively.
- next: put ink on paper — (1) `offset_fill` spacing vs pen width, the one
  thing only real ink settles (does 2mm read as fill or as stripes at a 0.3mm
  pen?); (2) whether `medial_tail` slivers read as intentional or as noise;
  (3) `round_center` ~0.5 on a shape with real corners; (4) a brush mass with
  `offset_fill` stacked on it — the module docstring claims rings suit a
  painted mass better than hatching does, which is an aesthetic bet, not a
  tested fact.
- blockers: none.
- context: `axibridge/effects/offset_fill.py` and `axibridge/sources/brush.py`
  module docstrings carry the full reasoning; ROADMAP "Offset rings" and 0c.

### Bench eye-check of the 07-16→19 wave — opened 2026-07-19, owner: ian
- done: generator v2 (misremembered scribble masses + tone dial, glyphgram
  coherent-field + continuity), bench latch with coalesced undo, draw tool
  + response brushes all merged (main, suite 430); screen-level eye-checks
  passed via rendered PNGs and Playwright acceptance.
- next: plot on paper — (1) misremembered v2 on a real photo (tone ≈ 0.35,
  compare mass_style scribble vs blob), (2) glyphgram continuity 0.6 vs 1.0
  at pen width, (3) a response-brush stroke (watch dash density: ~174 lifts
  per stroke; a sparser dash variant is the queued tune), (4) velocity tube
  now ships WITHOUT centerline by default — confirm that reads right.
- blockers: none.
- context: docs/plans/draw-mode-RESULTS.md,
  docs/plans/response-brushes-RESULTS.md, ROADMAP 0a–0c.

### Bench eye-check of the URGENT round — opened 2026-07-13, owner: ian
- done: all 11 URGENT items merged to main (`16fc350`), suite 382,
  12/12 automated live checks passed.
- next: Ian verifies at the bench the four behavior changes machines can't
  judge: (1) image output now centers on the bed — does it feel right with
  stacks/regenerate? (2) image_threshold band select on a real photo,
  (3) portrait "Width (mm)" now means on-paper visual width, (4) the
  viewAxis fader fix — one fader's drag direction deliberately flipped in
  portrait (correct per the rotation math; revert candidate if it feels
  wrong: see the feat(view) commit).
- blockers: none.
- context: ROADMAP.md URGENT section (struck through, with notes);
  `tests/test_view_coherence.py` locks resolve view-independence.
