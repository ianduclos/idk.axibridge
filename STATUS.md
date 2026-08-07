---
project: idk.axibridge
state: active
updated: 2026-08-07
machine: mac+pi
summary: Slices 0-3 of the UI redesign plan are done and on main — occlusion is memoised (430ms repeat resolves now ~0), undo is 50 deep with a geometry budget and now has redo, source-module orientation is a mandatory declaration with a test that fails when a new module omits it, a 10-test Playwright acceptance harness runs against the bundle, and the frontend is built by Vite with the source unmoved; 689 tests green, Ian has eye-checked the app.
next:
  - "Execute Slice 4 (the redesign itself) of docs/plans/ui-redesign.md in a FRESH session — 4a .engraved consolidation first, then typography, then the menu/toolbar restructure; show Ian a before/after at 4c's first step"
  - "Ian's call: are rectangle/grid/flowfield right as orientation='geometry'? They turn in portrait so 'Width 160' means 160mm across the screen — one word per module to flip"
  - "Ian's call, deferred from the plan: does jog earn its place at all once it is a menu item, or should it go?"
  - "Still open from July: bench eye-checks of offset_fill + brush, the 07-16→19 wave, and the URGENT round (see HANDOFF)"
handoff_for: ian
---

# idk.axibridge — status

**Session 2026-08-07 (Opus 5): the redesign plan's first three slices, plus redo.**

Worked `docs/plans/ui-redesign.md` from Slice 1 to Slice 3, checkpointing
after each. Seven commits, suite 639 → 689.

- **Occlusion is memoised** (`compose.OcclusionCache`). It used to run in full
  on every resolve; a repeat resolve on a 5-layer scene with a stroke occluder
  over a dense hatch fill went 430 ms → ~0. The cache is **content-keyed and
  never invalidated**: geometry is identified by object identity (legal only
  because modules are pure and lists are replaced wholesale), plus pen
  diameter, margin, groups, the receives flag, and layer order via the
  accumulated channel signature. `id()` reuse can't bite because every entry
  holds a strong reference to each list its key names. `tests/test_occlusion_cache.py`
  never inspects the cache — it asserts the cached resolve is byte-identical
  to an uncached one after every mutation that can move a mask. Known gap,
  documented: a visible region layer rewrites the shaped geometry below it
  each resolve, so those layers miss every time. Slow, never wrong.
- **Undo 8 → 50, with a geometry budget, and redo.** Measured first: an
  ordinary edit retains ~29 KB (the deep-copied Project), while an edit that
  REPLACES geometry pins its own copy at ~130 bytes/point — 50 bakes of a
  1200-path import is ~110 MB. Hence two caps, not one number. Redo makes
  history a pair of stacks; any real edit clears the redo branch, and a
  coalesced slider run is one entry in both directions.
- **Orientation is a declared layer property** (ROADMAP option B).
  `SourceModule.orientation` is mandatory — `"none" | "param" | "geometry"` —
  and for `"geometry"` sources in portrait the layer's affine carries the
  display map's inverse, so a layer lands where it would have in landscape,
  on screen. All 27 sources classified. The recurrence-stopper is
  `tests/test_orientation.py`: it fails on a source that declares nothing.
- **Acceptance harness** (`tests/test_acceptance_ui.py`): ten Playwright tests
  driving the real UI against a real server on a temp port, asserting what the
  user sees. They skip cleanly with no browser, which is how the Pi stays
  backend-only.
- **Vite + TypeScript**, with the source unmoved. `app.frontend_dir()` is the
  whole switch: built output when it exists, source when it doesn't — the
  fallback is what keeps a machine with no npm working. TypeScript is a lint
  pass (`allowJs`, `noEmit`), nothing renamed. ROADMAP's "Far / undecided — UI
  revamp" is marked RESOLVED with what was adopted and what it cost.
- **Edit menu** (Ian's ask, mid-session): Undo/Redo with ⌘Z / ⇧⌘Z; the
  portrait/landscape control **moved** into the View menu rather than being
  proxied there, so it cannot drift from `main.js`.


**Session 2026-07-27 (Opus 5): two new modules, and the workflow changed.**

Ian asked that work be **incorporated automatically** from here on — commit
straight to `main`, only branch when he says so. (Pushing still requires
asking; that rule is unchanged.) The trigger: nine feature branches had piled
up committed-but-unmerged, so finished work read to him as missing entirely.
`feat/ui-round-0726` was the last one and is now merged.

- **`effects/offset_fill.py`** — the second fill primitive beside `hatch_fill`:
  repeats the outline *inward* as concentric rings (contour-map look) instead
  of laying scanlines across it. The whole effect is erosion by a disk, and
  **topology needs no special-casing** — components split, components vanish,
  holes grow and merge, and shapely returning a `MultiPolygon` or an empty
  geometry *is* the event. The levels form a monotone forest because erosion
  can never invent a hole nor merge components. Load-bearing details, each
  pinned by a test: rings are eroded from the ORIGINAL at `k*spacing` (never
  iteratively, or corners re-round each pass); the even-odd hole assembly runs
  BEFORE eroding, which is why this is layer-wide and can't be a mode on
  `contract_expand`; inner rings are `filled=False` or occlusion reads the
  stack as stripes. `medial_tail` draws a centreline down limbs too narrow for
  another ring, suppressed when it would double an existing one.
- **`round_center`** (Ian's follow-up, same day) — relaxes each ring's corners
  in proportion to its depth, so the family morphs from the shape toward
  circles on the way in. A morphological opening, which is what buys the three
  properties that matter: it leaves straight runs untouched (ring spacing
  survives), it stays contained in the shape (rings can't escape or enter a
  hole), and it rounds only CONVEX corners — so concave structure survives and
  a star's centre becomes a flower, not a disc. That is the honest result, not
  a shortfall. The radius backs off by halves rather than ever costing a ring:
  verified that without the guard a 40mm square drops from 10 rings to 5.
- **`sources/brush.py` + `static/js/brush.js`** — ROADMAP 0c, the sibling of
  the shipped pen tool, now a 4th toolbar segment button. Circle brush, `[`/`]`
  resize, `E` toggles erase. The correctness story is the **sequential fold**:
  erases apply per stroke in chronological order, never
  union-all-then-subtract-all, or a repaint over an erased spot is swallowed.
  `test_repaint_over_an_erase_survives` builds the batched answer explicitly
  and asserts the real one differs — confirmed it is the only test of the 17
  that fails under a batched implementation. Output is every ring as a closed
  `filled=True` path, holes by nesting. Playwright-verified end-to-end against
  the real UI (4 strokes, no console errors, the erase bite and repaint bulge
  both visible in the resolved output).
- **`docs/plans/liquify-effect.md`** — a *loose* plan (hatch-connect-v2 style,
  not a frozen brief) for a soft-brush warp effect Ian raised hypothetically.
  Three findings worth keeping: it would be the first captured-input *Effect*
  (draw/pen/brush are all Sources); "depth as parameter" reads as a global
  `amount` 0..1 that must be exactly identity at 0, which makes timeline
  animation free; and **interpolating two liquifications is easier than the
  captured-geometry morph already shipped**, because a warp is a field rather
  than a structure. The trap there is that the tempting fix (A/B inside the
  effect) re-forks interpolation — extend the core instead. Filed as ROADMAP 0d.

Also merged this session: **`feat/ui-round-0726`** (Lucide tool icons, pen
Commit button, hatch-to-its-own-pen split), which had been sitting unmerged
since 07-26.

**Not done:** nothing has touched paper. Both new modules are screen-verified
only (rendered PNGs + Playwright), and ring-spacing-vs-pen-width is exactly
the kind of thing only real ink settles.

**Late in the session** (Ian's ask, all pushed):

- **`main` is on origin** — first push ever, and **idkpi pulled** to the same
  commit with 560 green there. Standing rule changed: push without asking on
  this project.
- **`fix(server)`: the app's slow quit was a one-line uvicorn default.**
  `timeout_graceful_shutdown` defaults to *wait forever* for open connections,
  and `/api/events` is an SSE stream that never finishes by design — so every
  quit hung until `launch/axibridge_app.py`'s 5s grace expired and SIGKILLed
  it. Measured with a stream held open: before, SIGTERM hung past 10s; after,
  clean exit in 2.17s. The plot-running close guard is untouched.
- **"Unknown source: brush" is a stale server, not a bug.**
  `load_builtin_modules()` runs once at startup, so a process started before a
  new module file exists never imports it — the browser picks up new JS
  instantly (no build step) and the mismatch looks like a broken tool. Restart
  the app after any new source/effect lands. Worth knowing generally.
- **"Graduate to a real app?"** — the shell question and the frontend-build
  question are separate and must stay that way (ROADMAP keeps the latter
  deliberately open). A Tauri/Electron shell would still point at
  `localhost:2942`, so the dev loop would be unchanged; a bundler is what
  would actually add tedium. Most of the "cheap" feeling was the shutdown bug
  above. Recommendation on record: use it a week, then fix the specific
  irritations rather than buying an architecture.

---

**Prior session 2026-07-25 (Sonnet 5): merged the four pending branches to main**
(nested-tween-morph, pen-tool, geometry-morph-tween, hatch-connect-strokes),
in dependency order with tests run after each step (suite 511 green).
`feat/geometry-morph-tween` needed a rebase onto the advanced `feat/pen-tool`
tip as flagged, which surfaced a real conflict/regression: nested-tween-morph
had rewired the live tween resolve path (`_source_paths_at`) to reduce
endpoints via `effective_generator` + `lerp_params` directly, bypassing
`blend_generator_params` — where the captured-geometry deep-lerp (pen/drawing
shape morph) lived. Fixed by applying the same deep-lerp inside
`_source_paths_at` on the post-reduction param dicts; one failing test
(`test_pen_tween_morphs_shape_continuously_not_stepped`) caught it before it
reached main.

---

**Session 2026-07-20 → 21 (Sonnet 5 / Opus 4.8): pen tool built, tween shapes now morph, hatch strokes join.**

The ⚓ pen tool (`sources/pen.py` + `static/js/pen.js`) with Photoshop grammar
and a 3-way toolbar mode segment driven by a shared `setToolMode` broker;
captured-geometry tween morph (`tween._blend_geometry` — pen/drawing shapes
morph A→B structurally instead of stepping at 0.5) plus a `cosine` ease;
`hatch_fill.connect_strokes` to cut pen lifts. Full record:
`docs/plans/pen-brush-tools-RESULTS.md`.

## Prior arc — 2026-07-19 (Fable + Sonnet 5): interpolation core unified, canon audit

One interpolation blend core in `tween.py` (`structures_match` / `lerp_paths` /
`blend_generator_params` / `blend_effect_stacks`), cheap-checkpoint invariant
restored, capture snapshots externalized to `staging/snapshot-<group>.json`,
registry-wide contract tests (`test_effect_contract.py`). **This is the
unification that ROADMAP 0d's liquify note warns against re-forking.**

## Prior arc — 2026-07-16 → 19 (generator v2, bench latch, draw/response tools)

`misremembered`/`glyphgram` v2 (scribble masses + tone, coherent-field +
continuity); generate-bench latch with coalesced undo; draw tool
(`sources/drawing.py` + `static/js/draw.js`) and response brushes
(`parasite_line`, `eyelets`, `velocity_tube`). Aesthetic rule (auto-memory):
structure-following marks, coherent fields, chaining — never uniform scatter.
Agent-ops: no worktrees (PEP 660 editable install imports main checkout);
agents work in the main checkout.

## Older history

URGENT round 11/11 (2026-07-13, orientation coherence via viewmap tags),
lineart v2, animation previews, Pi rounds, sheets v2, A/B capture — see
ROADMAP shipped sections and git history. Architecture invariants:
`ARCHITECTURE.md`, `docs/MODULES.md` (single resolve path; scrubbing never
mutates stored state). Two AxiDraw modes contend for the serial port —
Mac-driven pi_ssh (default) vs the disabled Pi-served service.
