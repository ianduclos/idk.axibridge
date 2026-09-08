---
project: idk.axibridge
updated: 2026-09-09
entries: 16
---

### Magnetic field bench acceptance — updated 2026-09-09, owner: ian

- done: The approved study is now a registered generator and interactive bench.
  Continuous default, editable bars/poles, seeded scatter, magnet visibility,
  optional empty silhouettes, whole-route boundary removal, local undo and
  Keep/Resume. The later filings reference guided the no-silhouette option.
- verified: 1,360 tests passed, one intentional native-app lifecycle skip;
  typecheck, built UI and isolated source-only smoke passed. Screens are
  provisional until Ian checks the native app and paper output.
- next: Try the open native bench and check paper output. The app and backend
  were restarted at Ian's request on 9 September; Ribbon was recovered from a
  separate `before-magnetic-bench-20260909-002530` project. The bench is open
  with continuous curves and both magnet bodies and silhouettes hidden.
  No hardware action was taken.
- limits: Simplified planar model; small pole cores remain untraced. Irregular
  styles require many lifts; actual paper/time benefit remains untested.
- context: docs/reviews/magnetic-bench-2026-09-09/README.md and
  docs/plans/magnetic-field-bench.md. Original study remains preserved.

### Ribbon production acceptance — updated 2026-09-09, owner: ian

- done: Registered Ribbon effect ports the accepted study to Python. Includes
  seed blend normalization, independent wavelengths, corner/loop handling,
  inter-path masks, silhouette/outline output, centre-free interpolation, actual
  pen density, optional crest smoothing and a shared outer-pair cutoff.
- hard corners: Ian’s actual acute pen path is repaired without changing its
  parameters or strand count. Full suite: 1,326 passed, one lifecycle skip.
  Evidence: docs/reviews/ribbon-hard-corners-2026-09-08/README.md.
- edge joins: Regular edge mode stabilizes local side balance through acute
  joins, preserving total width. The live-path fixture has 20 separate strands
  without self intersections, crossing pairs or shared interior routes. Hidden
  `fractured_edges: true` with `interpolation: "edges"` preserves the exact
  polygon-cutout experiment Ian selected; default remains false. Evidence and
  tradeoffs: docs/reviews/ribbon-edge-joins-2026-09-09/README.md.
  Full suite: 1,363 passed, one lifecycle skip. Live backend reloaded and current
  drawing restored; resolved coordinates match the candidate exactly.
- next: Check Ribbon from the layer effects picker; the Mac backend now includes
  it after Ian authorized a restart. Review optional per-flank softening on real
  paths/paper. The original inline study is unchanged and remains reference.
- deferred: D3 crossing-envelope effect next; expanded popup editor later, both
  recorded in ROADMAP.md. Restart completed with authorization; no push or hardware run.
- context: docs/plans/ribbon-shipping.md,
  docs/reviews/open-path-ribbon-2026-09-08/PRODUCTION-STATUS.md and
  production-review.html. Tests and visual verification are provisional until
  Ian checks the result; existing unrelated acceptance entries remain below.

### Mac visual and icon acceptance — updated 2026-09-08, owner: ian

- done: Whole-app precision and all five cosmetic sheen touches are installed;
  Ian approved the preview direction. The selected geometric scaffold appears
  in both the web favicon/touch icon and the separate Mac application icon.
  The app was opened on request; the live server serves the selected favicon.
  Working benches remain Venation, Homeostat and Second Reading only.
- next: Check native Mac appearance/input feel and the displayed app icon.
  The Pi never runs the UI and is excluded from visual acceptance.
- blockers: none for implementation; native appearance is not yet confirmed.
- context: docs/plans/ui-precision-IMPLEMENTATION.md,
  docs/reviews/ui-precision-2026-09-08/report.html and
  docs/reviews/ui-sheen-2026-09-08/index.html. Both reports retain their original
  fixtures. Final suite: 1,289 passed, one lifecycle skip because the app is open;
  typecheck and isolated source smoke passed. No push or hardware action.
  Durable recovery and future bench
  services remain separately deferred.

### Interactive drawing machine: Second Reading — updated 2026-09-06, owner: ian

- done: First recovered from prior tool output; all 30 original geometry/decision
  fixtures match with historical replay enabled. Responsive is now the default;
  thick reinforcement stacks are removed from ordinary readings. Shape and
  Relation experiments preserve baseline choices while varying geometry and
  optional wider relationships. Attention/Departure/Scale are experimental.
- boundaries: Clip, Turn inside, Overshoot + fit element. Boundary is a new-drawing
  choice; capture frame stays fixed, raw events replay exactly, one whole-element
  affine produces the kept document, and source frame placement fits the bed in
  portrait and landscape. Layers can still be manually moved/scaled afterwards.
- review: bounded Sol neutral populations + calibration variants + sequences;
  lead kept the small original cusp and removed repeated sampling-dependent
  hooks. Terra prepared an iteration sheet from actual recorded bench exchanges.
- latest user fixes: visible smoothing with live preview, Randomize seed, persistent
  pending new-drawing fields, explicit active boundary and nominal sheet outline.
  Turn inside now reflects inward with a rounded turn. Agent protocol in AGENTS.md.
- judgement: First remains available for response-policy comparison. Relations has some useful openings, not
  demonstrated overall superiority. Containment can press runs against edges;
  whole-fit keeps proportions but a broad excursion may diminish an older knot.
- next: alternate at the bench and compare the offers, including ignored inputs.
  No paper test yet. Start with `docs/reviews/second-reading-0906-lead.md` and the
  final iteration/alternating sheets. No hardware or running user app touched.
- verification: 1,262 passed, 1 skipped; build/typecheck and independent final Resume/placement browser check passed.
- context: `docs/plans/second-reading-next-session.md` retains the agreed brief;
  `docs/plans/second-reading.md` records current contracts. Old unversioned recipes
  are historical evidence; explicit `reading` now selects the retained engine.

### Bench + paper: the homeostat (A2) — opened 2026-09-04, owner: ian

- done: pass 4's **A2** shipped and pushed — `sources/homeostat.py` +
  `sources/_homeostasis.py`. A pen whose handwriting is rerolled blindly when
  an essential variable leaves its viable range; four variables (crowding,
  coverage, tangle, and **surprise** — the pen's own prediction error about its
  own next turn, so becoming predictable is itself a crisis); **ultrastability**
  (`escalation`: a reroll that FAILED widens the space the next hand is drawn
  from, a viable passage narrows it — the drawing gets an arc); and 1-6
  **coupled units** sharing one occupancy grid with no concept of each other,
  which also closes **A4 (the seam)**. Suite 1121 -> 1182. Ian ran the bench on
  2026-09-04 and kept four highlights (`shots/homeostat-bench-0904/`).
- next:
  - **Plot one.** Still nothing from pass 4 has touched paper — not the
    homeostat, not venation, not the cymatic fill. The homeostat's output is a
    single continuous stroke, which should plot unusually cleanly.
  - Try `measure = surprise` (band ~0.30 +- 0.20) against the default
    `crowding` on the same seed — that is the change that alters what the
    drawing is ABOUT, and it wants an eye, not a test.
  - Turn on `escalation` 0.4 with `variety` STARTING low (~0.35) and watch the
    variety trace in the bench. From 0.8 there is nowhere to escalate to.
  - Two or three `pens` is the sweet spot; four and six fill the sheet (that is
    Ashby's own result, see the ledger). Duplicate the layer at one seed, set
    `unit` 0/1/2 and give each a pen to plot the ensemble in colour.
- blockers: none — shipped, green and pushed; this is eyes, hands and paper.
- context: `docs/plans/homeostat.md` (design), `-IMPLEMENTATION.md` (plan),
  `-RESULTS.md` (what the design got wrong, what a review caught, and the
  ensemble finding), `shots/homeostat-bench-0904/README.md` (what Ian's own
  runs showed that the renders did not), `shots/homeostat-coupled-pens.png`,
  `shots/homeostat-surprise-arc.png`. The six criticisms of this module —
  where the ceiling actually is — are section 6 of `docs/BRIEF-new-generator.md`.

### Watch/scrub/rehearse/plot: time as a param (A1) — opened 2026-08-21, updated 2026-09-04, owner: ian

**2026-09-04:** the substrate is no longer unseen — Ian drove the bench for the
homeostat and it held up (play, scrub, tune, create at the step on screen). The
A1.5 question is still formally open, but nothing about the session argued for
direct manipulation over a recorded score. **Venation itself is still unwatched
and unplotted**, which is what the rest of this entry is about.

- done: generators can declare a time axis; `ProcessModule` yields step-by-step
  process output; a trajectory cache runs a process once so scrubbing is a
  free prefix slice; `venation` (space-colonisation growth) is the first real
  process generator; a popup plays and scrubs any layer with a time axis;
  Rehearse stamps several moments of one process onto the sheet in one undo
  step, at nearly no extra cost because the trajectory cache shares across
  moments. Suite 1080 → 1115, verified only through pytest/simulator —
  nothing here has touched paper, and nobody has watched it on a real screen
  yet either. `docs/plans/time-as-a-param-RESULTS.md` has the full ledger.
- next:
  - **The question this whole round exists to make answerable: now that
    there is something to watch, does poking a running process want to be
    direct manipulation, or a recorded score?** The design deliberately
    deferred interaction (A1.5) because it is the single most likely thing
    here to force a redesign, and it cannot be settled from a desk — it
    wants a hand actually on the scrub slider while venation is growing.
  - Watch a venation layer play in the popup. It requests one step every
    40ms, but each request is a full HTTP round trip — check by eye whether
    it holds anywhere near that rate, or reads as choppy.
  - Scrub it by hand — does landing on an arbitrary step ever look "wrong"
    (a half-grown branch, a stalled tip) in a way that argues for smarter
    snapping.
  - Rehearse one — does a pencil-then-ink pass on a growth process actually
    read as rehearsal, or does the nesting need something like fading pen
    weight per moment to sell it.
  - **Plot one.** Nodal-free continuous growth lines should plot unusually
    cleanly — no crossing hatch, no fill boundary, just branching strokes —
    and that claim has never met a pen.
- blockers: none — it's shipped and green, this is eyes/hands/paper only, and
  the A1.5 question above is the input the next round (A2, the homeostat)
  needs before it can be designed.
- context: `docs/plans/time-as-a-param.md` (design, with the interaction
  decision and its reversal path spelled out), `docs/plans/time-as-a-param-
  RESULTS.md` (what shipped and what the design got wrong), `axibridge/
  sources/venation.py`, `axibridge/process.py`, `axibridge/trajectory.py`,
  `axibridge/static/js/process.js`. ROADMAP's A2 (homeostat) is the item most
  directly waiting on this answer.

### Eye-check: eigenfunction (cymatic) fill — opened 2026-08-21, updated 2026-08-21, owner: ian

- done: new effect **Eigenfunction fill (cymatics)** — every closed+filled
  path in a layer becomes a vibrating membrane and gets filled with its own
  nodal lines, so the pattern is produced by the boundary rather than laid
  over it. Mode changes density *and* character on one scrub; Mix sweeps the
  family of figures a symmetric shape shows at one frequency (a square: the
  straight line at 0, the two diagonals at ±1); an image can weigh the
  membrane so lines bunch where it is dark. **Second round the same day,
  after Ian saw the first output and called it boring — correctly**: it drew
  only the nodal set, which Courant's theorem caps at ~n curves, so it was a
  partition of the shape rather than a fill (2 strokes on his shape). It now
  traces a whole family of level sets (`levels`, `level_bias`), can contour
  stillness instead of displacement (`field=sand`), and can ring across a
  band of modes (`spread`). Suite 1049 → 1075, all analytic
  (rectangle spectrum in closed form, Courant's nodal-domain bound) rather
  than golden files. Verified end to end through the real API — PATCH, resolve,
  stats, undo — and rendered to PNG contact sheets, but never on paper and
  never in the actual browser UI.
- next:
  - Look at the defaults first — Mode 6, 9 levels, bias 0.6. Then **drag
    Level bias from 0 to 1** on a mid mode: 0 shades every lobe alike, 1
    piles the contours onto the nodal figure. That is the tonal control and
    the one most likely to be tuned wrong.
  - **`field = sand`** is the other look worth an early opinion — it is the
    physically honest one (ink where the surface is still) and much denser.
  - Add a filled `polygon` layer, stack the effect, and **drag Mode**. The
    first drag step pays for the eigensolve (~80 ms on a 120 mm pentagon),
    every step after is ~10 ms from the cached basis. If that ever feels slow,
    the honest fix is a coarser Detail, not a smaller cache.
  - Set the polygon to 4 sides and **sweep Mix from −1 to +1** — that is the
    detail the whole item was for, and it is the one thing a test can only
    check is *different*, not whether it is *right*.
  - Push Mode past ~60 on an irregular shape (a `shape` layer, or text_fill
    glyphs) for the tangled Berry regime, then plot one. Nodal lines are
    smooth and non-crossing, so it should be an unusually clean plot — that
    claim has never met a pen.
  - Try it on `text_fill` glyphs: each letter is its own membrane with its
    counters as real holes, which is the case with no precedent to compare to.
- blockers: none — it is shipped and green, this is eyes-and-ink only.
- context: `axibridge/effects/eigen_fill.py` (docstring states the physics
  honestly: clamped membrane, NOT a free Chladni plate),
  `axibridge/effects/_eigenmode.py` (solver, cache, degenerate-basis
  reasoning), `tests/test_eigen_fill.py`, `docs/IDEAS-pass4.md` §B2.

### Eye-check + paper: colour separation — opened 2026-08-17, owner: ian
- done: image generators can sample a colour plate instead of only luminance
  (CMYK / RGB / luma, with a black-generation knob), plus tonal-band
  separation, plus a ⌗ Separate row that turns one image into N ordinary
  generator layers with a pen each, in one undo step. A plate may carry its
  own generator, so cyan can be halftone dots and magenta squiggles. Suite
  990 → 1048 including three acceptance tests that drive the real UI end to
  end. An HSL mode (hue/saturation/lightness) landed the same day for fun.
  Separately: seed rolling now covers effects and every server-side creation
  path, which it never did before. Note the behaviour change that comes with
  it — two layers of the same generator, or the same effect stacked twice, no
  longer come out identical unless you pin the seed.
- next:
  - Work through **CHECKME.md's 2026-08-17 section** — the screen half first
    (black generation, effects on one plate, per-plate generators, tone
    bands), then paper.
  - **The paper half is the actual deliverable and no test reaches it**: does
    cyan-over-magenta give you a real third colour, does separating with
    `halftone` moiré badly (four dot grids at one angle — if it does, the
    roadmapped per-plate screen angles become worth building), and does the
    `slop` misregistration read as charm or as a mistake.
  - Two decisions are yours once you have seen ink: whether the subtract GCR
    form lays the right amount of ink (the divide form is the textbook
    alternative and roughly doubles it), and whether `tone_rescale` should
    default on. Both are one-line changes documented with their alternatives.
- blockers: none.
- context: `docs/plans/channel-separation.md` is the design doc — it carries a
  decision table of every judgment call, its alternative, and the exact change
  that reverses it. `axibridge/channels.py`'s docstring has the polarity
  contract everything rests on. ROADMAP's colour-separation follow-ons (spot
  colour, HSV/Lab, the N-pen solve, screen angles) say what was deliberately
  left for later.

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
