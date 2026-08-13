---
project: idk.axibridge
updated: 2026-08-13
entries: 9
---

### Eye-check: text_fill + two orientation fixes — opened 2026-08-13, owner: ian
- done: new "Text (filled)" source (real font outlines, closed/holed shapes,
  system-font discovery, drag-in upload) plus two bug fixes found and closed
  in the same session — a layer left un-rotated after toggling the view
  (affects every `orientation="geometry"` source, not just text_fill), and
  grid-sheet frame order ignoring portrait. Everything verified via
  Playwright against the real UI and the full suite (990 passed), but per
  standing rule that's provisional until you've clicked through it yourself.
- next:
  - Try the actual fonts you care about — a real system font (Helvetica/
    Arial/Times New Roman if installed), the bundled Recursive variable
    font's four sliders, and drag a `.ttf` file onto the canvas.
  - Toggle portrait/landscape on a text/text_fill layer created in the
    *other* view and confirm it reads right, then check a grid-sheet bake
    (any cols×rows) in portrait for natural reading order.
  - Nothing here has touched paper — this is screen/geometry-level only.
- blockers: none.
- context: `axibridge/sources/text_fill.py` + `_fontglyph.py` module
  docstrings carry the font reasoning; `session.py`'s `set_view` and
  `_grid_place` docstrings carry the orientation-fix derivation; STATUS.md's
  top entry has the commit-by-commit summary.

### Docs-upkeep pass — opened 2026-08-11, owner: claude-hub — **DONE 2026-08-11**
- done: the pass ran (Opus, docs only — no code, no tests, suite untouched at
  947). `docs/plans/timeline-v2.md` is CLOSED: every build-order slice is
  annotated SHIPPED with its commit and a new **§6 closing ledger** records
  the slices, all ten proposals, the two supersessions (S4's Q7(b) play
  button; framing → crop) and what stayed deliberately open. ROADMAP gained an
  **"Animation v2 — SHIPPED 2026-08-11"** section (chains, the bar, the
  staging/plot rework, plus the 08-10→11 perf round and
  `fast_marching_contours`, neither of which had been recorded), and the
  entries this round resolved are struck/annotated in place: ">2 keyframes /
  keyframe lists vs layer pairs" (answered — a keys list; grouping still
  open), `framing` under Sheets workflow v2, the 1/2/4/16 presets, the
  GIF/video "convenience only" line, multidimensional sheet variants,
  plot-cursor persistence and staging browser ergonomics. ARCHITECTURE.md:
  the tween description generalises past two endpoints, chains get their own
  paragraph, "Plotting — manual multi-pen" records the view-bound ▶ Plot and
  the guided pass queue, and the tray paragraph records A→blends→B groups,
  the chain fence and ↻ re-bake. CLAUDE.md: `timeline.js` in the table,
  chains named on the `tween.py` row, one new ▶-Plot-semantics invariant.
- next: nothing — this entry is closed; the orchestrator reviews and commits.
  `docs/MODULES.md` was checked and deliberately left alone: chains live
  inside `tween.py` and the crop rename is a sheet format, so neither changes
  the module-authoring story.
- blockers: none.
- context: `docs/plans/timeline-v2.md` is the round's contract (Ian's Q1-Q7
  rulings + §2b/§2c + the plot-flow ruling); STATUS.md's top entry lists what
  actually shipped, which is the thing to check docs against.

### Bench + hardware check: E-batch, timeline v2, staging/plot rework — opened 2026-08-11, owner: ian
- done: ~15 commits, suite 843 → 947, all simulator/headless-verified only —
  nothing in this round has had Ian's eyes or real hardware on it yet.
- next:
  - **Bench eye-check** everything in CHECKME.md's new 2026-08-11 section
    (chains, the bottom timeline bar, trays, sheet crop modes, the render
    popup, the E1-E6 fixes) — delete that section once cleared.
  - **Hardware pass on the multi-pen swap queue**: run one real multi-pen
    sheet, confirm "swap to pen, then ▶ continue" holds pen state correctly
    mid-job and that Stop actually clears the queue rather than leaving it
    primed. Nothing about this has touched a real AxiDraw yet.
  - **One bench look at whether held-queue-survives-view-change is right** —
    the plot-flow ruling made it deliberate, not an oversight, but it's
    exactly the kind of call that wants a real "did that surprise me" check.
- blockers: none.
- context: `docs/plans/timeline-v2.md`'s plot-flow ruling section for why the
  queue behaves this way; `axibridge/static/js/plot.js` for the queue itself;
  CHECKME.md for the full eye-check list.

### Eye-check: Fast marching topo — opened 2026-08-10, owner: ian
- done: `fast_marching_topo` ships as a native image-driven generator: seeded
  Eikonal/Fast Marching travel time, compiled marching-squares iso-lines,
  shared image tone/frame/rotation controls, mm smoothing, 0.25×..2×
  resolution and transparent-PNG clipping. Default 800px generation measured
  1.3s on Mac; eleven focused tests plus the full suite are green (800).
- next: try one real tonal portrait and one transparent PNG in the app. Check
  whether 200 contours / speed offset 0.1 are useful defaults, whether moving
  the seed reads as an intentional compositional control, and whether alpha
  clipping leaves objectionable short pen strokes at the silhouette. Put one
  result on paper only if the screen result earns it; plot-pass simplify is
  available if the default ~128k-point output is too literal.
- blockers: none.
- context: `axibridge/sources/fast_marching_topo.py` is params/plumbing;
  `_fast_marching.py` is the solver/tracer; `tests/test_fast_marching_topo.py`
  pins the contract. ROADMAP keeps the older direct N-brightness-threshold
  contours idea open because it is a different field, not an unfinished part
  of this generator.

### Eye-check: taller bed, finer sliders, Smoothen — opened 2026-08-08, owner: ian
- done: three unrelated asks, all committed to main (`d74f357`), suite 743.
  (1) ~20px of dead height above the canvas reclaimed by tightening the header
  band and the paddings around the tool row — `#canvas-wrap` top 93 -> 75,
  measured in both shell modes; no markup changed. (2) Shift fine-tune resolves
  below the coarse step at last: `forms.js` now derives a `fine` quantum
  (`step / 10`, 1 for integers) and quantizes to *that*, so a span > 20 field
  commits tenths instead of whole millimetres and shift+arrow finally differs
  from a plain arrow. Placement's four hand-written boxes got the same by hand.
  (3) `effects/smoothen.py`, Catmull-Rom — interpolating, so it passes through
  the points it was given; `relax` is the averaging behaviour, opt-in.
- next: Ian looks at the **2026-08-08 section of `CHECKME.md`**. The three
  questions only he can answer: is the tighter header still comfortable to
  grab and drag the window by; are the 10x slower number-box arrows an
  irritation (that is the one trade the finer quantum cost); and does Smoothen
  at `resolution` 0.5mm cost too much plot time on a real sheet. Smoothen also
  wants one filled shape under an occluder, on paper.
- blockers: none.
- context: `axibridge/effects/smoothen.py`'s module docstring carries the full
  reasoning for interpolating over averaging. The fine-quantum change is the
  comment block at `forms.js`'s `const fine = ...`. Two fine-tune gaps were
  left on purpose and are NOT oversights: canvas guide drags still snap to
  whole mm (`canvas.js`) and transform/pen-anchor handles have no fine
  modifier at all — direct manipulation is a different problem from slider
  resolution. The bigger space win (hoisting the tool row into the header
  band, ~50px) was offered and declined this round; it is still there.

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
  The jog question is ANSWERED (2026-08-08): out of the UI, endpoint kept.

### Bench eye-check: offset_fill (+ v2) + brush — opened 2026-07-27, updated 2026-08-09, owner: ian
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
  Added 2026-08-09: **`offset_fill_v2`** ships beside v1 (v1 untouched) and
  plots the same fill as ONE continuous spiral — 61 strokes becomes 1 on a
  120mm square at 1mm spacing. It needs the same ink test and two of its own:
  (5) does an unbroken spiral read better on paper than concentric rings, or
  does the seam show; (6) is `blend` 0.5 the right default — it trades seam
  visibility against how close consecutive turns run, and the bound is
  `(1 - blend) x spacing`. Ian called it "good enough for my use" on screen;
  none of it has been plotted.
- blockers: none.
- context: `axibridge/effects/offset_fill.py`, `offset_fill_v2.py` and
  `axibridge/sources/brush.py` module docstrings carry the full reasoning —
  v2's `_spiral` has the lockstep/drift argument, `_arcpoly.py` has the
  arc-engine one and why it is not the default. ROADMAP "Offset rings" and 0c.

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
