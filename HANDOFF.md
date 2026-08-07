---
project: idk.axibridge
updated: 2026-08-07
entries: 4
---

### UI redesign — Slice 4c (menus and toolbar) — opened 2026-08-07, owner: ian
- done: 4a (engraved consolidation, measured no-op). 4b typography BUILT AND
  REVERTED — Ian: "got used to the mono"; do not rebuild it, the plan's 4b
  section says why and keeps the findings. Emoji removed from the layer list.
  The two menu bars became ONE definition: `axibridge/menu_spec.py` parses
  `#menubar` out of `index.html` and the macOS menu is derived from it, merged
  into pywebview's own Edit/View, with working checkmarks. 4c's first step
  landed — View took the canvas overlays and Schematic·Ink, toolbar 3 rows → 2.
  Suite 689 → 712. Ian confirmed all of it in the running app.
- next: 4c continues — (1) the A/B/steps/⇄ cluster moves to Plot › Staging,
  (2) Animate plot + speed becomes a playback strip at the canvas foot shown
  only when a timeline or staged series exists, (3) then `flex-wrap: nowrap`
  + a "»" overflow so the canvas top edge stops moving on resize. All three
  are page-only and fully testable headless. After that, the Machine menu.
- blockers: **the Machine step is blocked on one decision.** Of the five
  panels leaving the Plot tab, only ACTIONS can be menu items — Ian's own menu
  rule sends anything with a readout or live value to a panel, and motion
  parameters, raw EBB, soft-limit values and calibration steps all have one.
  They need a destination: Settings tab, a new Machine tab, or both. Asked
  2026-08-07, not answered — do not pick one unilaterally, it changes the
  whole shape of the step.
  SETTLED 2026-08-07: (a) jog stays for now — move it as a menu item and
  **re-ask after Ian has used it that way**, which is the whole point of
  deferring rather than carrying it forever; (b) the header's dead middle is
  parked until 4d needs somewhere to put machine state, and the project-name
  fix already landed; (c) the rectangle/grid/flowfield orientation
  classification is accepted, nothing to flip.
- context: `docs/plans/ui-redesign.md` (4b annotated BUILT-THEN-REVERTED, 4a
  marked done, the Settled table's Typeface row struck through).
  `axibridge/menu_spec.py`'s module docstring carries the whole why.
  **Editing `#menubar` in `index.html` now changes the macOS menu too** — that
  is the contract, and `tests/test_menu_spec.py` + `tests/test_app_shell.py`
  enforce it. When a shell-only thing misbehaves, read
  `~/Library/Logs/axibridge-shell.log` FIRST; it exists because four bugs in a
  row failed silently. Any new main-thread work must go through
  `axibridge_app.on_main()` — a block that returns a value kills the app.
  New, 2026-08-07: Ian observed that **interrupted plot should have been a
  generator** — it is an aesthetic tool in a machine tab, and it bakes where
  everything else stays live. Filed with the real obstacle (a source that
  reads its own document is a cycle) in ROADMAP "Far / undecided — interrupted
  plot should have been a generator". Not a 4c task; do not fold it in.

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
