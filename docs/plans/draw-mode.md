# Plan: draw mode — drawing as a first-class layer (agent run, Sonnet 5)

You are Claude (Sonnet 5) running as a coding agent on Ian's Mac, in a git
worktree of axibridge. This plan was written by a Fable session on
2026-07-17 after a design discussion with Ian; the architecture decisions
below are SETTLED — implement them, don't redesign them. If a decision
turns out to be impossible as specified, stop, write what you found to
`docs/plans/draw-mode-BLOCKED.md`, commit that, and end the run. Do not
improvise around the contract.

## Read first (in this order, all in-repo)

1. `CLAUDE.md` — operating rules. Single resolve path, module purity,
   bounded params, undo discipline. Non-negotiable.
2. `docs/MODULES.md` — the module authoring contract for the new source.
3. `axibridge/static/js/workbench.js` — the existing ✏ Draw capture
   (pointer → mm via the SVG viewBox, live stroke echo, stroke list).
   You are building the main-canvas sibling of this; steal its patterns.
4. `axibridge/api.py` `WorkbenchBody` + `_drawing_paths` — the house
   pattern for geometry-as-params: point budget cap, on-bed bounds.
5. `axibridge/static/js/compose.js` — the bench latch (top of file) and
   `renderGenForm`/`bindGenForm`; your draw mode must coexist with it.
6. `axibridge/static/js/canvas.js` — find the existing pointer→mm
   machine-frame conversion used for dragging/marquee and REUSE it.
   View rotation (portrait/landscape) is display-only; stored coordinates
   are always machine-frame mm. Do not reimplement the mapping.
7. `axibridge/static/js/forms.js` line ~78: fields with
   `json_schema_extra={"hidden": True}` are skipped by the auto-form —
   this is how the strokes blob stays out of the UI.

## Protocol

- `.venv/bin/python -m pytest -q` green before EVERY commit.
- Branch: `git checkout -b feat/draw-mode` from main. Conventional commits,
  one per coherent step (source module; frontend; presets; tests may ride
  along). NEVER commit to main. Do not push.
- Frontend has no build step: edit `axibridge/static/**`, reload.
- Verify in a real browser (protocol below), not just with pytest.
- When done: write `docs/plans/draw-mode-RESULTS.md` (what shipped, what
  you'd tune, anything surprising), update `ROADMAP.md` if it mentions
  drawing, commit.

## The contract (settled decisions)

**Stroke storage.** A drawing is a generator layer. Its source params carry
the strokes: `strokes: list[list[[x_mm, y_mm, t_s]]]` — machine-frame mm,
`t_s` = seconds since that stroke's pen-down (float ≥ 0, non-decreasing).
Timestamps are captured NOW even though nothing uses them yet: a later
"velocity tube" render mode derives speed from them, and they cannot be
recovered after the fact. Every stroke point is a strict 3-list.

**Why a layer, not a tool:** the moment a drawing is an ordinary layer it
inherits occlusion, pens, estimates, undo, regions, A/B capture, tweening
and the timeline for free, and decorations stay non-destructive effect
stacks. Nothing in this plan adds a second geometry path to the plotter.

## Part 1 — `sources/drawing.py`

- `@register_source`, id `"drawing"`, label `Drawing (pointer)`. Params:
  - `strokes`: the blob above, `json_schema_extra={"hidden": True}`,
    default `[]`. Pydantic-validate shape; clamp points into the bed
    (0 ≤ x ≤ 300, 0 ≤ y ≤ 218) rather than raising — a regenerate must
    never die on a stray captured point. Cap total points at 50_000
    (raise ValueError over that, matching `api._drawing_paths`).
  - `resample_mm`: float, ge=0.2, le=5.0, default 0.8 — resample each
    stroke at fixed arc-length so pointer-event density doesn't matter.
  - `smooth`: int, ge=0, le=4, default 1 — smoothing passes (use the
    3-point kernel style seen in `sources/misremembered.py::_smooth`).
  - `render`: `Literal["centerline"]`, default `"centerline"`. Yes, a
    one-value enum: a follow-up plan adds `"velocity_tube"`; the field
    must exist now so presets can reference it (see Part 3 shape).
- `generate()` emits one layer, open unfilled paths, points ≥ 0. Empty
  `strokes` → raise ValueError("draw a stroke first") like other sources
  raise helpful errors. Resampling/smoothing must preserve stroke ends.
- VERIFIED FACT: `session._centering_transform` only recenters generators
  with an `image` param — a drawing layer gets the identity transform, so
  strokes stay exactly where drawn. Do not add centering.
- Tests (`tests/test_drawing_source.py`): registered; empty-strokes raises;
  determinism (same params → same points); 50k cap raises; off-bed points
  clamped; resample_mm changes vertex count but not endpoints; regenerate
  round-trip through `session.add_generated_layer`/`regenerate_layer`.

## Part 2 — canvas draw mode (`static/js/draw.js`, new file)

- New module exporting `initDrawMode()`; import + call it from `main.js`
  next to the other init calls. Keep changes to existing JS files minimal:
  the toolbar button lives in `index.html`; pointer handling lives in
  draw.js using capture-phase listeners (`addEventListener(..., true)`)
  on `#canvas-wrap` with `stopPropagation()` while draw mode is active,
  so `canvas.js` selection/drag code is untouched.
- `index.html` `#canvas-toolbar` gains:
  `<button id="draw-toggle" title="Draw on the sheet — strokes become a Drawing layer">✎ Draw</button>`
  and `<select id="brush-select" hidden></select>` right after it.
- Mode behavior:
  - Toggle on: button gets the `.on` treatment (match `#ab-capture button.on`
    styling), cursor crosshair over the canvas, brush select becomes
    visible. Esc or re-click exits. While the doc-preview banner is active
    (`#doc-preview-banner` not hidden), the toggle is disabled — you can't
    draw on a transient preview.
  - Pointer down→move→up captures a stroke in machine mm with
    `performance.now()`-derived `t_s` per point (seconds since pen-down),
    clamped to the bed. Live echo: append a temporary polyline to the SVG
    styled like workbench's `.wb-draw-live`; remove it on commit.
  - Pen-up commits the stroke:
    - if the currently selected layer is a `drawing` layer, OR draw.js
      has an `activeDrawLayerId` still present in the project → append
      the stroke to its `source.params.strokes` and
      `POST /api/layers/{id}/regenerate {params}` — WITHOUT `coalesce`,
      so ⌘Z removes exactly one stroke (per-stroke undo is the point;
      the 8-deep history is a known, accepted limit).
    - else → `POST /api/layers/generate {module:"drawing", params:{strokes:[stroke]}}`,
      remember the id as `activeDrawLayerId`, `actions.setSelection([id])`.
  - After each commit: `actions.refreshProject()` + `refreshResolved()`.
  - Selecting a different drawing layer retargets drawing to it; deleting
    the active layer clears `activeDrawLayerId` (re-check on each commit,
    never assume).
- Coexistence with the bench latch (compose.js): do not touch the latch
  code. A drawing layer selected in the list latches the bench like any
  generator layer — that's fine and wanted (its resample/smooth sliders
  live-edit). Draw mode only appends strokes via its own regenerate calls.

## Part 3 — brush presets

- In draw.js, a const table — THIS SHAPE IS THE CONTRACT (a follow-up plan
  appends an entry with a `source` override, so both keys must exist):

  ```js
  const BRUSHES = [
    { id: "plain",   label: "plain",   source: {}, effects: [] },
    { id: "sketchy", label: "sketchy", source: {}, effects: [{ effect: "freehand", enabled: true, params: {} }] },
    { id: "tube",    label: "tube",    source: {}, effects: [{ effect: "fat_tube", enabled: true, params: { width: 5 } }] },
    { id: "wobble",  label: "wobble",  source: {}, effects: [{ effect: "coherent_jitter", enabled: true, params: { amplitude: 2 } }] },
  ];
  ```

- Picking a brush applies to the ACTIVE drawing layer: replace its effect
  stack (`actions.patchLayer(id, { effects })`) and, when `source` is
  non-empty, merge those keys into `source.params` + regenerate. If no
  drawing layer exists yet, remember the choice and apply it when the
  first stroke creates one. Empty `params: {}` means module defaults —
  resolve them from `S.state.modules.effects` at apply time.

## Verification protocol (browser, mandatory)

Start a throwaway server (isolated config, temp port — NEVER 2942):

```
AXIBRIDGE_CONFIG_DIR=$(mktemp -d) .venv/bin/python -m axibridge --port 29433
```

Drive it with Playwright (`.venv` has it; `wait_until="domcontentloaded"`,
never networkidle — SSE holds the connection open). Script and assert at
least: toggle enters draw mode; a synthesized pointerdown/move/up sequence
on the canvas creates a Drawing layer whose `strokes[0]` points carry
3 fields with plausible t; a second stroke appends (still ONE layer);
`POST /api/undo` removes exactly the last stroke; picking the "tube"
brush puts `fat_tube` on the layer; portrait AND landscape views both
place the stroke where the cursor was (compare against expected mm).
Screenshot the result and LOOK at it with the Read tool. Kill the server.

## Boundaries

- Do not touch: `model.py`, `compose.py`, `session.py`, `estimate.py`,
  backends, existing effects/sources, the undo/coalesce machinery.
- New files: `sources/drawing.py`, `static/js/draw.js`,
  `tests/test_drawing_source.py`. Edited files: `index.html` (toolbar),
  `main.js` (one import + one init call), `style.css` (draw-mode styles
  only). If you believe you need to edit anything else, that's a smell —
  re-read Part 2's capture-phase-listener approach first.
- Every numeric param bounded. Strokes deterministic (no RNG anywhere in
  this plan). Paths open + unfilled; nothing here touches occlusion.
