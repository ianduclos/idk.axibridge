---
project: idk.axibridge
updated: 2026-08-07
entries: 4
---

### UI pass on design/bench-and-bed — opened 2026-08-07, owner: ian
- done: 6 commits on the branch, 638 tests green. New visual direction
  ("bench & bed", rationale in the `style.css` header comment); collapse state
  persisted per section; white button faces dropped for a measured steel blue
  (darker than the sheet, so no control outshines the paper); sliders became
  faders with shift fine-tune; quitting went 2.20s -> 0.17s; macOS title bar
  merged into the header with File/Canvas moved to the system menu bar, the
  in-app "axibridge" wordmark removed (the OS already says it twice), and the
  header made a drag region so the window still moves.
- next: restart AxiBridge.app and eye-check the shell — whether the traffic
  lights sit correctly in the header band (84px clearance and the 38px band
  are considered guesses, not measurements) and whether the Canvas menu reads
  right. Then decide what to take from the review and whether to merge the
  branch.
- blockers: none. The title-bar look is the only thing that could not be
  verified headless — it needs a real window.
- context: review artifact
  https://claude.ai/code/artifact/eb6f2105-7669-4bab-867b-2012122f84f6
  (three critics, rulings, 12 ranked proposals, corrections);
  direction artifact
  https://claude.ai/code/artifact/b595fdb0-9204-45c0-83ce-571dbcfb6427.
  Unfixed and highest-value: occlusion recomputes on every resolve
  (`compose.py` `clip_paths`; ~2.1s with an occluder over a hatch_fill layer,
  87% inside shapely's difference) — caching it needs a staleness design.
  Undo is 8 deep (`session.py:156`) and `undo()` pops, so redo is not
  bolt-on. ROADMAP's new URGENT section covers the portrait orientation bug.

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
