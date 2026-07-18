# Results: draw mode — main-canvas drawing as a first-class layer

Implements `docs/plans/draw-mode.md` in full. Branch `feat/draw-mode`,
3 commits (source module + tests, then the frontend). All contract
decisions in the plan were followed as specified — nothing was blocked or
renegotiated.

## What shipped

- **`axibridge/sources/drawing.py`** — new registered source, `id="drawing"`.
  `strokes: list[list[[x_mm, y_mm, t_s]]]` (hidden param, default `[]`),
  `resample_mm` (0.2–5.0mm, default 0.8), `smooth` (0–4 passes, default 1),
  `render: Literal["centerline"]` (placeholder for a future `velocity_tube`
  mode). Points are clamped into the bed rather than raising; total density
  is capped at 50k points (raises `ValueError`, matching
  `api._drawing_paths`'s pattern). Empty strokes raises
  `ValueError("draw a stroke first")`. Resampling ports
  `workbench.js`'s arc-length `resample()` into Python with a third `t`
  channel interpolated alongside x/y; smoothing ports
  `misremembered.py::_smooth`'s 3-point kernel, applied to x/y only so
  `t` survives untouched. Both preserve stroke endpoints exactly.
  No centering transform is added or needed — `DrawingParams` has no
  `image` field, so `session._centering_transform` already returns identity
  for it.
- **`tests/test_drawing_source.py`** (10 tests) — registration, empty-raise,
  determinism, 50k cap, off-bed clamping, resample vertex-count/endpoint
  behavior, two-strokes-two-paths, open/unfilled paths, bounded-param
  rejection, and a `session.add_generated_layer`/`regenerate_layer`
  round-trip.
- **`axibridge/static/js/draw.js`** (new) — `initDrawMode()`, imported and
  called once from `main.js`'s `initTabs()`. Capture-phase pointer
  listeners on `#canvas-wrap` (`stopPropagation` only while the mode is
  on) intercept strokes before `canvas.js`'s own bubble-phase
  selection/drag/marquee listeners on `#canvas` ever see them — zero
  changes to canvas.js. Pointer→mm reuses `CanvasEditor.toBed()` (the
  exact conversion drag/marquee already use, via
  `world.getScreenCTM().inverse()`), so portrait/landscape both place
  strokes correctly with no reimplementation of the view-rotation math.
  Live echo reuses workbench's existing `.wb-line`/`.wb-draw-live` CSS
  classes (no new styling needed for the stroke itself).
  - Pen-up commits: targets the selected layer if it's a `drawing`
    generator, else the remembered `activeDrawLayerId` if it still exists
    in the project (re-checked on every commit — never assumed), else
    creates a new layer via `/api/layers/generate`. Appends via
    `/api/layers/{id}/regenerate` **without** `coalesce`, so ⌘Z removes
    exactly one stroke.
  - Brush presets table (`BRUSHES`, exact shape from the plan: `id`,
    `label`, `source`, `effects`) — picking one replaces the active
    layer's effect stack (`actions.patchLayer`) and merges any `source`
    overrides via a regenerate; empty `params: {}` resolves to module
    defaults from `S.state.modules.effects[].defaults`. A brush picked
    before any stroke exists is remembered and applied when the first
    stroke creates the layer.
  - The toggle disables (and force-exits) while `#doc-preview-banner` is
    visible, via a `MutationObserver` on its `hidden` attribute — no
    changes needed to whatever sets that banner.
  - Guarded against `initTabs()` re-running on every SSE reconnect (a
    `wired` flag) so listeners are never double-bound.
- **`axibridge/static/index.html`** — `#draw-toggle` button +
  `#brush-select` (hidden until armed) appended to `#canvas-toolbar`.
- **`axibridge/static/js/main.js`** — one import, one `initDrawMode()`
  call next to the other tab inits.
- **`axibridge/static/style.css`** — `#draw-toggle.on` (matches
  `#ab-capture button.on`) and `#canvas-wrap.draw-mode` crosshair cursor.
- **`tests/test_workbench.py`** — one assertion updated. Registering a
  real `"drawing"` source changes `POST /api/workbench/preview
  {"module":"drawing"}` (no `paths`) from a 404 (unknown module, the old
  behavior) to a 400 (`"draw a stroke first"` — empty strokes on the now-real
  source). This is the intended, foreseeable effect of Part 1 and not a
  contract conflict; the comment and assertion were updated to match.

## Verification (Playwright, throwaway server on :29433)

All from a real browser driving the actual app, not just pytest:

1. Toggle enters draw mode (`#draw-toggle.on`, `#canvas-wrap.draw-mode`,
   `#brush-select` visible) — **PASS**
2. A synthesized pointerdown→move×6→up on the canvas (landscape view)
   creates exactly one project layer, `source.generator === "drawing"` —
   **PASS**
3. `strokes[0]` — every point has exactly 3 fields; `t_s` starts at 0,
   is non-decreasing, and stays in a plausible sub-second range for a
   ~150ms synthetic drag — **PASS**
4. Stroke start/end land within 3mm of the app's own `toBed()` conversion
   for those screen coordinates, in **landscape** view (explicitly
   selected — index.html defaults to Portrait, so this was verified to
   actually exercise landscape, not a no-op re-click) — **PASS** (both
   ends)
5. A second stroke appends to the same layer (still exactly 1 layer, now
   2 strokes) — **PASS**
6. ⌘Z (driven via `page.keyboard.press("Meta+z")` — the app's real
   shortcut, not a raw `fetch('/api/undo')`, so the client's cached
   project state stays in sync the way real usage does) removes exactly
   the last stroke (2 → 1) — **PASS**
7. Picking the "tube" brush adds `fat_tube` (`width: 5`, defaulted
   `smooth: 8`) to the layer's effect stack — **PASS**
8. Switching to **Portrait** and drawing a new stroke: appends (1 → 2
   strokes) and lands within 3mm of `toBed()`'s conversion for that view —
   **PASS**
9. Esc exits draw mode — **PASS**

17/17 assertions passed. Screenshots (visually inspected, both show
correctly placed, tube-shaped strokes matching their draw-time
orientation):
- landscape, after the tube brush: `landscape_after_tube.png`
- portrait, after both strokes: `portrait_after_stroke.png`
(paths under the session scratchpad, not the repo)

One test-harness pitfall worth flagging for future verification work: an
earlier draft of the Playwright script called `/api/undo` via a raw
`fetch()` instead of the app's ⌘Z handler, which left the client's
in-memory `S.state.project` stale (the handler also calls
`refreshProject()`/`refreshResolved()`, which the raw fetch skips) —
this produced a spurious "3 strokes instead of 2" result that looked like
an app bug but was purely the test bypassing the real interaction path.
Driving it through the keyboard shortcut fixed it. Also: re-running the
same Playwright script against an already-running throwaway server
compounds state from the previous run (same in-memory project) — always
restart the server between runs, or clear the project first.

## What I'd tune

- `resample_mm`/`smooth` defaults (0.8mm, 1 pass) were not tuned against
  real pen-and-tablet input, only synthetic straight-line strokes — worth
  an eyes-on pass with an actual mouse/trackpad once Ian tries it.
- The brush `source` merge always issues its own `regenerate` call
  separate from the effects `patchLayer` — for brushes with non-empty
  `source` this is two network round-trips instead of one. Fine at this
  scale (a handful of drawing-layer edits), but if brushes grow more
  elaborate `source` overrides, worth collapsing into one call.
- No visual affordance yet for "this brush is armed but no drawing layer
  exists" beyond the select's own value — a first-stroke hint might help
  discoverability.

## Open questions

None — every contract decision in the plan resolved cleanly against the
existing code (module registry, session regenerate/undo, `CanvasEditor`,
`describe_modules()`'s `defaults`). No blockers hit.
