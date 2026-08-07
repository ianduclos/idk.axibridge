---
project: idk.axibridge
updated: 2026-08-07
entries: 4
---

### UI redesign — Slice 4 (the redesign itself) — opened 2026-08-07, owner: ian
- done: Slices 0-3 of `docs/plans/ui-redesign.md`, seven commits on main,
  suite 639 -> 689. Occlusion memoised (repeat resolve 430ms -> ~0, key
  completeness argued in `compose.OcclusionCache`'s header and pinned by
  `tests/test_occlusion_cache.py`); undo 8 -> 50 with a geometry budget, plus
  redo as a second stack; orientation made a mandatory `SourceModule`
  declaration with a test that fails on a module that omits it; a 10-test
  Playwright acceptance harness that runs against the BUILT frontend; the Vite
  + TypeScript port with the source unmoved and a one-rule server switch
  (`app.frontend_dir`). Ian eye-checked the running app: "seems to work".
- next: Slice 4, in a FRESH session — 4a (consolidate the dead `.engraved`
  rule so the typography change is a one-place edit), then 4b typography, then
  4c the menu/toolbar restructure. Sub-steps 4a-4g are independently
  shippable; commit and checkpoint after each, and put a before/after in front
  of Ian at 4c's FIRST step, not at the end.
- blockers: two decisions are Ian's, neither blocking 4a-4b. (1) Are
  `rectangle`/`grid`/`flowfield` right as `orientation="geometry"`? They now
  turn in portrait, so "Width 160" means 160mm across the screen in either
  view; `text`/`glyphgram` were the reported bug and are unambiguous, these
  three were the agent's judgement. One word per module to flip. (2) The plan
  asks whether jog earns its place at all once it is a menu item — do not
  delete it unilaterally; pen up/down and go-to-origin inside that group may
  be the parts that earn their keep.
- context: `docs/plans/ui-redesign.md` is written to be loaded cold and now
  carries inline notes where this session overtook it (redo shipped early at
  Ian's request; the Playwright chromium mismatch fixed properly). Slice 4's
  spec is in it verbatim. CLAUDE.md, ARCHITECTURE.md "Stack" and ROADMAP's
  "UI revamp — RESOLVED" describe the new build; `tests/test_acceptance_ui.py`
  is the contract the redesign must not break.

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
