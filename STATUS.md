---
project: idk.axibridge
state: active
updated: 2026-07-25
machine: mac+pi
summary: All four pending branches merged to main (pen tool, captured-geometry tween morph + cosine ease, hatch connect_strokes, nested tween-of-tween bilinear morph) — suite 511 green. idkpi clone needs pull; CHANGES.md entry filed. Bench eye-checks still open.
next:
  - "Pull the idkpi clone (git pull on ~/idk.axibridge) — geometry-as-params tween SEMANTICS change (pen/drawing shapes now MORPH instead of stepping) + tween-of-tween lifted for same-generator layers"
  - "Push main to origin (16+ local commits ahead, not yet pushed — confirm with Ian first)"
  - "Bench: pen tool + animated pen morph on paper (new, from this merge)"
  - "Brush tool (ROADMAP 0c / pen-brush-tools.md Part 2) still deferred — the sibling to the shipped pen tool; Ian chose pen-only this pass"
  - "Older bench eye-checks still open (generator v2 wave + URGENT round) — see HANDOFF"
  - "Delete the four merged local feature branches once Ian confirms nothing else needs them (nested-tween-morph, pen-tool, geometry-morph-tween, hatch-connect-strokes)"
handoff_for: ian
---

# idk.axibridge — status

**Session 2026-07-25 (Sonnet 5): merged the four pending branches to main**
(nested-tween-morph, pen-tool, geometry-morph-tween, hatch-connect-strokes),
in dependency order with tests run after each step (suite 511 green).
`feat/geometry-morph-tween` needed a rebase onto the advanced `feat/pen-tool`
tip as flagged, which surfaced a real conflict/regression: nested-tween-morph
had rewired the live tween resolve path (`_source_paths_at`) to reduce
endpoints via `effective_generator` + `lerp_params` directly, bypassing
`blend_generator_params` — where the captured-geometry deep-lerp (pen/drawing
shape morph) lived. Fixed by applying the same deep-lerp inside
`_source_paths_at` on the post-reduction param dicts (a no-op for generators
without a hidden geometry field, so nested-tween-morph's own tests are
unaffected); one failing test (`test_pen_tween_morphs_shape_continuously_not_stepped`)
caught it before it reached main. CHANGES.md entry filed. Not yet done:
pulling the idkpi clone, pushing main, bench eye-checks.

---

**Prior session 2026-07-22 (Opus 4.8): nested tween-of-tween bilinear morph built
(`feat/nested-tween-morph`, suite 486) for Ian's stacked-threshold use case;
Pi plotting revived after a dead motor rail traced to the wrong barrel-jack
adapter (`QC` V+ 0023→0299).**

---

**Session 2026-07-20 → 21 (Sonnet 5 / Opus 4.8): pen tool built, tween shapes now morph, hatch strokes join. Three unmerged branches.**

Executed `docs/plans/pen-brush-tools.md` (pen only — brush Part 2 deferred by
Ian's call), then two adjacent features that came out of using it. Nothing
merged to main; nothing pushed. Suites green on each branch.

- **`feat/pen-tool`** (off main `5a31f58`; tip `4ecb49e`, suite ~492) — the
  ⚓ pen tool, Parts 0 + 1 of the brief. `sources/pen.py` (Bézier
  anchor/handle geometry-as-params source, adaptive de Casteljau flatten,
  12 tests) + a 3-way toolbar mode segment (**select · draw · pen**) driven
  by a shared `setToolMode` broker in `main.js` (draw.js refactored to
  activate/deactivate hooks; brush button omitted until built) +
  `static/js/pen.js` canvas mode. Then several rounds of hands-on fixes
  (each its own commit + RESULTS note): pending-path rendered as you place
  anchors; live curve preview while dragging a handle; Option-drag pulls a
  one-sided handle out of a corner; **auto-commit an unfinished line on
  tool-switch** (Escape stays the discard gesture); handles inert without
  Option (Option = move one, **Shift+Option = full symmetric mirror** —
  angle AND length, revised from an earlier angle-only choice); square
  (Photoshop-style) anchor markers; editable pending anchors *before*
  commit; **closing click-DRAG curves just the closing segment** (pulls only
  the first anchor's in_handle, one spline, no distortion); **selecting a ▸ A
  / ▸ B keyframe jumps the master timeline** to that end so you preview it.
  Full record + live-verification detail: `docs/plans/pen-brush-tools-RESULTS.md`.
- **`feat/geometry-morph-tween`** (stacked on feat/pen-tool @ `cbb2df3`; tip
  `b06bb26`, suite 499) — **resolves the geometry-as-params tween morph that
  MODULES.md had flagged as a deliberately-open question** (Ian directed
  building it). `tween.blend_generator_params` now structurally deep-lerps a
  hidden geometry field (`pen.subpaths`, `drawing.strokes`) when A and B
  share structure — anchors, Bézier handles, points ease A→B pointwise, then
  regenerate through the source's own flattening (true curved in-betweens,
  not linearly-lerped points). All-or-nothing per field: mismatched counts
  still step at 0.5 as before (the arc-length-resample case for
  differently-shaped A/B is the one piece left open). Shared blend core, so
  canvas tweens AND tray captures both morph. Also adds a **`cosine`** ease
  curve (`0.5-0.5cos(pi t)`) beside `linear` and `cosine_pingpong` (the exact
  addition ROADMAP predicted). Verified live: animated pen shape sweeps
  mean-y 40→65→90→115→140 (was stepping), cosine eases it 40→55→90→125→140.
  MODULES.md + ROADMAP.md updated on this branch.
- **`feat/hatch-connect-strokes`** (off main; tip `8606992`, suite 497) —
  `effects/hatch_fill.py` gains `connect_strokes` (opt-in, off by default):
  merges adjacent serpentine hatch lines into one continuous stroke wherever
  the connector stays inside the shape, cutting pen lifts; a hole still forces
  a real lift; crosshatch passes never join to each other. Verified: a filled
  rectangle dropped from 26 paths to 2 (**2 lifts**) with it on.

**Merge/rebase note carried into `next`:** feat/geometry-morph-tween branched
before feat/pen-tool's last two commits (`7af3fb4`, `4ecb49e`), so rebase it
onto the current pen tip before merging or those pen fixes will look reverted.

**Deferred this session by explicit choice:** brush tool (0c); "line modes"
for pen (steps/zigzag/stitch — steps already exists as `bitmap` style
`lines`; zigzag/stitch would be two new small effects — parked as its own
task); and my read that the **⚗ Bench**'s own mouse-drawing feature is now
largely superseded by the real Draw/Pen tools (a bench "drawing" scrap
freezes to dead SVG; a real layer stays live) — flagged for a later,
deliberate call, not touched.

## Prior arc — 2026-07-19 (Fable + Sonnet 5): interpolation core unified, canon audit

A deep architecture critique shipped two structural items, both on main
before this session:

- **One interpolation blend core** (`acbd717`, `d535d3e`): canvas tween and
  tray capture-blend had drifted (disabled-effect handling differed);
  `structures_match` / `lerp_paths` / `blend_generator_params` /
  `blend_effect_stacks` now live once in `tween.py`. Non-lerpables are
  EXCLUSIVELY bools, seeds, mismatched stacks (stack identity = full step
  list; `enabled` steps as a bool). Pinning (`tests/test_interp_pinning.py`)
  caught two real bugs: one-sided capture layers crashed below the midpoint;
  a tween-t change between captures froze every batch step at A. **This
  session's geometry-morph builds directly on this core** — the hidden-field
  deep-lerp slots into `blend_generator_params`.
- **Cheap-checkpoint invariant restored** (`2cf5eb6`, `5b1a828`): staging
  shared by reference into history; capture snapshots externalized to
  `staging/snapshot-<group>.json` (legacy inline still loads).
- Canon-doc audit + registry-wide contract tests (`test_effect_contract.py`);
  `Path.is_closed` unified three drifted inline definitions; the three build
  briefs in `docs/plans/` (pen-brush-tools, aaron-core-figure,
  perception-pass) written — pen-brush-tools is what this session executed.

## Prior arc — 2026-07-16 → 19 (generator v2, bench latch, draw/response tools)

`misremembered`/`glyphgram` v2 (scribble masses + tone, coherent-field +
continuity); generate-bench latch with coalesced undo; draw tool
(`sources/drawing.py` + `static/js/draw.js`) and response brushes
(`parasite_line`, `eyelets`, `velocity_tube`). Aesthetic rule (auto-memory):
structure-following marks, coherent fields, chaining — never uniform scatter.
Agent-ops: no worktrees (PEP 660 editable install imports main checkout);
agents work in the main checkout on feature branches.

## Older history

URGENT round 11/11 (2026-07-13, orientation coherence via viewmap tags),
lineart v2, animation previews, Pi rounds, sheets v2, A/B capture — see
ROADMAP shipped sections and git history. Architecture invariants:
`ARCHITECTURE.md`, `docs/MODULES.md` (single resolve path; scrubbing never
mutates stored state). Two AxiDraw modes contend for the serial port —
Mac-driven pi_ssh (default) vs the disabled Pi-served service.
