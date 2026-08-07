---
project: idk.axibridge
updated: 2026-08-07
entries: 4
---

### Layers panel + eye-check of the finished Slice 4 — opened 2026-08-07, owner: ian
- done: **Slice 4 of `docs/plans/ui-redesign.md` is complete, a through g.**
  Toolbar is one fixed row of tools; View and Machine menus hold what left it;
  machine state + Pause/Resume/Stop live in the always-visible status line;
  Plot tab 10 panels -> 5 (the machine ones went to Settings); plot targets
  accept `pen:<id>`; layer list drags to reorder, renames in place, and the
  occlusion channels are two segmented groups. The app shell's macOS menu is
  DERIVED from `#menubar`'s markup (`axibridge/menu_spec.py`), merged into
  pywebview's own Edit/View, showing checkmarks and greying what it cannot do.
  Suite 727, 26 acceptance tests.
- next: **Ian eye-checks. `CHECKME.md` at the repo root is the list**, grouped
  by how likely each thing is to be wrong (shell-only paths first — those are
  verified only against fakes and need a full relaunch). Delete it when done.
  `docs/plans/layers-panel.md` is BUILT: the layer list is now a persistent
  collapsible/resizable dock at the foot of the sidebar, on all four tabs, one
  list in the DOM, `＋ empty layer` left in Compose. Its third slice was
  dropped on the measurement rather than built — reorder+resolve is 0.2-2.1 ms
  across everything up to 100 layers / 72k points, so a progress indicator
  would have been decoration. The caveat is written into the plan: I could not
  reconstruct the 430 ms occluder-over-hatch case at a representative size, so
  that is "could not construct a slow reorder", not "none exists".
- blockers: none. Two decisions are flagged inside the plan for when there is
  something to look at (does the box scroll or grow; should the plot target
  follow the selection — probably not, plotting the wrong layer costs paper).
- context: `docs/plans/layers-panel.md` (the plan, with Ian's words verbatim).
  **Ian has NOT eye-checked the 4c-4g round** — the Machine menu's greying is
  verified only against real AppKit objects and a faked bridge, and the status
  strip only against the simulator. When anything shell-only misbehaves read
  `~/Library/Logs/axibridge-shell.log` FIRST, and route any new main-thread
  work through `axibridge_app.on_main()` — a block that returns a value kills
  the app. Editing `#menubar` in `index.html` now changes the macOS menu too.
  Re-ask the jog question: Ian's ruling was to keep it, use it as a menu item,
  then decide.

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
