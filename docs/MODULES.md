# Module authoring guide

axibridge has four extension points. Three are drop-in-a-file geometry
modules; the fourth (execution backends) is registered in code:

| Kind | Signature | Directory | Worked example |
|---|---|---|---|
| **Source** | `params → PathDocument` | `axibridge/sources/` | `polygon.py` (minimal), `flowfield.py`, `image_threshold.py` (asset-driven) |
| **Effect** | `(list[Path], params, ctx) → list[Path]` | `axibridge/effects/` | `multipass.py` (minimal), `coherent_jitter.py`, `depth_displace.py` (asset-driven, crop/split) |
| **Transform** | `(PathDocument, params) → PathDocument` | `axibridge/transforms/` | `vpype_ops.py` |
| **Backend** | lifecycle + `plot(doc, params, control, emit)` | `axibridge/backends/` | `simulator.py` |

All four follow the same recipe:

1. a Pydantic `Params` model — *this generates your UI controls*;
2. a class implementing the kind's protocol (`axibridge/registry.py` for the
   geometry kinds, `backends/base.py` for backends);
3. registration — `@register_source` / `@register_effect` /
   `@register_transform` decorator (auto-imported from the directory), or one
   line in `MachineManager.__init__` for a backend.

Restart the server and the module is in the UI. No frontend work, ever.

## The params model: your UI for free

```python
from pydantic import BaseModel, Field

class MyParams(BaseModel):
    spacing: float = Field(default=2.0, ge=0.1, le=20, title="Spacing (mm)",
                           description="Shown as a tooltip in the UI")
    closed: bool = Field(default=False, title="Close paths")
```

Rendering rules (`static/js/forms.js`):

| Schema shape | Control |
|---|---|
| `number`/`integer` with `ge`+`le` | slider + spinbox (slider commits on release) |
| `number`/`integer` unbounded | spinbox |
| `bool` | checkbox |
| `str` | text input |
| `str` + `json_schema_extra={"format": "textarea"}` | multiline textarea |
| `enum`/`Literal` | dropdown |
| `str` + `json_schema_extra={"format": "asset"}` | dropdown over uploaded image assets, with inline upload |

`title` is the label; `description` the tooltip. **Always bound numerics** —
unbounded values reach an open-loop machine with no limit switches.
Validation is server-side and automatic: bad values 422 before your code runs.

Three more `json_schema_extra` tags with frontend meaning:

- `{"viewAxis": True}` on a paper-space x/y pair: in portrait view the label
  letter swaps and the displayed value negates, so the fader moves things
  the way the rotated bed *looks*. Only use on fields with symmetric bounds.
- `{"group": "Image processing"}` (any name) collapses those fields into a closed
  `<details>` at the bottom of the form — use for shared boilerplate params
  so a long form stays scannable.
- `show_map: bool` params ghost the module's image asset on the canvas.
  For **generators** this is automatic: any generator layer whose params
  carry `image` + `show_map` (+ `width`/`rotate`) ghosts in the layer's
  local frame. Effects that place their map in paper space (depth_displace)
  are still special-cased in `main.js mapGhosts()`. Preview only; never
  plotted.

Generators with a `format:"asset"` param are listed under the
"Image-driven" optgroup in the Add-layer picker automatically.

Image-driven modules read pixels through `assets.asset_store`:
`grayscale(name, blur_px, rotate, size)` (cached per blur radius and optional
working size — derive `blur_px` from a `smoothing` mm param × image px / placed
mm width) and `alpha(name, rotate, size)` (matching resampled, unblurred crop
mask; `None` when absent). Shared brightness/contrast/gamma/levels behavior
lives in `image_processing.py`; apply it to grayscale samples, not alpha masks.

**Colour separation comes free with `ImageBaseParams`.** Subclass it and your
module gains `channel` (luma / c m y k / r g b) and `black_generation`, so one
image can drive one layer per ink plate, a pen each. Sample through
`channels.sample_rows(params, blur_px, size)` rather than calling `grayscale`
directly — it resolves frame sequences and reads the selected plate. **Every
plate comes back in `grayscale`'s polarity: 0 = draw hardest**, whichever plane
it is, which is precisely why nothing downstream of the decode needs to know a
channel exists. Keep it that way. Dimension probes may stay on `grayscale`
(no channel changes an image's size). The `tone_from`/`tone_to`/`tone_rescale`
window is separate and lives on `PixelGenParams`, since it acts inside
`_tone_lut`. Reasoning, alternatives and the extension seam:
`docs/plans/channel-separation.md`.
If the named asset is missing, **pass through / return empty, don't raise** in
effects (a stored project must still resolve); generators may raise a helpful
`ValueError`.

## Writing a Source (generator)

A generated document enters the compositor as a **layer**: its layers'
paths are merged into one layer's source geometry, placed at the canvas
origin, and the user transforms it from there. Copy `sources/polygon.py`.

Contract:

- Output coordinates in **mm, all ≥ 0** (the machine frame has no negatives).
- Mark closed shapes that should occlude as solid with
  `Path(points=..., filled=True)` — first point must equal last. Stroke-only
  paths leave `filled=False` (they mask as a thin band at pen width).
- Deterministic for fixed params (seed any randomness): "regenerate" and
  project-loading both re-run you. (Projects also snapshot generated
  geometry to SVG, so old artworks survive changes to your code.)
- **Declare `orientation` — it is mandatory** (`tests/test_orientation.py`
  fails on a module that doesn't). The canvas draws portrait through
  `translate(H 0) rotate(90)`, so anything with a dominant axis arrives a
  quarter-turn round unless something corrects it, and "somebody will notice"
  is exactly how this bug came back three times. Pick one:
  `"none"` (no dominant axis — a polygon, a lissajous, marks the user drew
  themselves), `"param"` (you expose a rotation param tagged `viewRotate` /
  `viewAngle` / `viewOrient`, so `static/js/viewmap.js` remaps its default —
  the image family; the test also checks the tag really exists), or
  `"geometry"` (oriented output with no such param — a text baseline, a
  width x height field: `Session._placement_transform` bakes portrait's
  quarter-turn into the layer's affine at creation).
- Slow generators should call `registry.report_progress(frac, msg)` from
  their loops — it feeds the Generate button's load bar over SSE and is a
  no-op outside a request. Call it freely; the API layer throttles.
- **Pixel-space image generators** (the plotterfun family): subclass
  `sources/_pixelgen.PixelGenParams` (image/rotate/width/show_map + the
  collapsed Image processing group), sample darkness 0–255 through
  `ImageSampler`, and return via `pixel_doc(...)` — it scales the fixed
  800-px working canvas to the `width` mm placement. `luma_grid(..., scale=)`
  accepts a bounded 0.25×..2× quality multiplier for generators whose cost
  needs an explicit speed/detail tradeoff. Copy `sources/subline.py`.
- **Geometry-as-params sources** (the canvas-tool family — draw mode, and
  the pen/brush tools it precedes): the param model carries CAPTURED
  geometry directly — a hidden `strokes`/`anchors` list, already in
  machine-frame mm, bed-clamped and point/anchor-count capped — instead of
  generating shape from a few numeric dials. `generate()` still has to be
  pure and deterministic (same params → same output), it just has nothing
  to seed: the geometry itself IS the input. The layer transform is
  typically left at identity since the capture already placed the geometry
  on the bed; downstream (occlusion, pens, estimates, undo, regions, A/B
  capture) treats it exactly like any other layer for free — see
  `sources/drawing.py`'s module docstring for why this beats a bespoke
  client-side tool. A companion `static/js/<tool>.js` captures pointer
  events into the params and POSTs `regenerate` (usually with
  `coalesce=true` mid-drag — see CLAUDE.md's Undo discipline). Copy
  `sources/drawing.py` + `static/js/draw.js`.
  **A new TOOL does not imply a new SOURCE.** The shape tool
  (`static/js/shapes.js`, 2026-08-21) adds rectangle/ellipse/line to the canvas
  without a line of Python: a rectangle is four corner anchors and an ellipse
  is four with kappa handles, so both are ordinary pen subpaths committed
  through `pen.js`'s `commitPenSubpath` — which is also what earns them boolean
  add/subtract against brush and pen layers for free. A line has no interior to
  union, so it commits through `draw.js`'s `commitDrawStroke` as a two-point
  stroke instead. Before writing a source for a new tool, check whether an
  existing param model already says what the gesture produces.
  **Tween: captured geometry now
  MORPHS when A and B share structure** (2026-07-21). A hidden geometry param
  (`pen.subpaths`, `drawing.strokes` — anything marked
  `json_schema_extra={"hidden": True}`) is deep-lerped by
  `tween.blend_generator_params` → `_blend_geometry`: anchors, Bézier handles
  and points ease A→B pointwise, then regenerate through the source's own
  flattening (true curved in-betweens, not linearly-lerped points). This is
  what "animate a pen shape and drag B's anchors" needs, and it flows through
  the shared blend core so canvas tweens AND tray captures both get it. The
  morph is all-or-nothing per field: **identical structure required** (same
  subpath/anchor/point counts — what "animate"/"duplicate" produce). When the
  counts DON'T match — e.g. B has an extra anchor, or two freehand drawings
  with different point counts — that field still *steps* at t=0.5 as before.
  The remaining open piece is only the mismatched-count case: resampling both
  geometries to a common point count via arc-length so even differently-shaped
  A/B could morph. That's still a genuine design decision (resample vs. keep
  stepping mismatches) and is deliberately left for later — the structural
  case covers the common workflow.
- **Process sources** (`axibridge/process.py`): a generator that UNFOLDS.
  Subclass `ProcessModule`, declare a bounded step param as `time_axis`, and
  write `run()` yielding one `Step` per tick — the marks ADDED at that step,
  plus optional `telemetry` for the popup to plot. `generate()` is provided
  and stays pure: it asks the trajectory cache for the state at step N. `run()`
  may be `while True`; the param bounds it. A process that revises earlier
  marks rather than adding sets `accumulative = False` and yields whole states,
  which costs much more to cache. Copy `sources/venation.py`.
  A time axis gives older modules the generic process bench by compatibility:
  the Generate panel shows a **▷ Bench** button (params beside a stage that
  plays and scrubs the axis, then creates the layer at the step on screen), and
  a committed layer gets **▷ Watch** and **Rehearse**. The bench form drops the
  axis field — the scrub bar is that
  param's control — so give the axis a real title and a tight `ge`/`le`: those
  bounds become the scrub's range, and an unbounded axis has nothing to scrub.
  New modules may instead declare an explicit, versioned bench independently
  of time:

  ```python
  bench = {"adapter": "process", "version": 1,
           "modes": ["new", "watch"]}
  ```

  `adapter` is a nonempty UI adapter name, `version` is a positive integer, and
  `modes` is a list containing only `new`, `watch`, and/or `resume`. Unknown
  adapter names remain in the catalogue so the UI can report that it cannot
  open them. For compatibility, an undeclared source with both `intervene` and
  `branch` capabilities resolves to `second-reading` v1 (`new`, `resume`); any
  other source with an effective time axis resolves to `process` v1 (`new`,
  `watch`); a source with neither has no bench.
  **Interactive score bench (2026-09-05):** `second_reading` additionally
  declares `bench = {"adapter": "second-reading", "version": 1, "modes":
  ["new", "resume"]}` and retains `bench_capabilities = ("intervene",
  "branch")` for compatibility. This selects an event-aware editor with human
  turns, preserved alternatives and Keep as layer. It requires the recorded-event contract in
  `plans/second-reading.md`; adding the capability to an arbitrary process
  does not make that process understand interventions. `Step.metadata`
  retains discrete decisions alongside numeric telemetry. The preview API
  returns these under optional `process`; the interactive bench exposes
  details on demand. Generic Watch still graphs point count.

## Writing an Effect — the v2 per-layer stack

Effects are the non-destructive, reorderable, toggleable stack on each layer
(Blender-modifier style). Copy `effects/multipass.py` for the minimal shape,
`effects/coherent_jitter.py` for the full treatment.

```python
from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect

@register_effect
class MyEffect(EffectModule):
    id = "myeffect"            # unique, stable — stored in project files
    label = "My effect"
    Params = MyParams

    def apply(self, paths: list[Path], params: MyParams, ctx: EffectContext) -> list[Path]:
        ...
```

The contract, and why each clause exists:

- **Assigned pen context (2026-09-08).** `ctx.line_diameter_mm` supplies the
  assigned output pen's mark width (0.5 mm when unassigned), without effects
  reading global stores. Normal layers use their pen, region effects use the
  region pen, and materialized tween effects use the tween output pen. Pen
  edits participate in effect-bearing shape and tween cache keys. Ribbon uses
  this for automatic strand density; its profiles and geometry helpers live in
  `_ribbon_profile.py` and `_ribbon_geometry.py` for reuse by the planned D3 effect.
- **You receive geometry already placed on the paper** (the layer transform
  runs first). So a millimetre in your params is a millimetre on the sheet,
  no matter how the layer is scaled — that's the system's promise to the
  user; don't undo it by scaling your own output.
- **Be pure.** Return new `Path` objects; never mutate inputs. The
  compositor caches and re-runs stacks freely; the before/after of a toggle
  depends on the input surviving. Since 2026-08-11 purity + determinism are
  also what make `gencache.generate_cached` legal — source outputs are
  memoized content-keyed and returned by reference. A deliberately
  nondeterministic source must set `cacheable = False` on its class
  (`registry.SourceModule`) or the memo will freeze its first roll.
- **Preserve `filled` and closure.** Carry `filled=path.filled` through, and
  if a path arrived closed (first == last), return it closed — occlusion
  masks are built from your output. Use `Path.is_closed` / `model.is_closed`
  for the check, never a hand-rolled `pts[0] == pts[-1]` (the definitions
  had drifted three ways before 2026-07-19). Closure is EXACT float
  equality: if your effect moves points, snap the closing point back onto
  the first (see freehand's closed-path snap) — epsilon-close is open, and
  an open path silently stops masking as a solid.
  `tests/test_effect_contract.py` enforces the one-way implication
  (`filled` ⇒ closed), purity, and determinism over every registered
  effect automatically — your module is covered the moment it registers.

  *Semantics corner, documented rather than fixed*: nested filled loops are
  holes by even-odd parity, and both consumers agree for **proper nesting**
  — but for *partially overlapping* filled paths in one layer they diverge:
  the fill effects XOR (`symmetric_difference` — the overlap lens comes out
  unfilled; `hatch_fill` and `offset_fill` share this rule deliberately)
  while `compose.build_mask` unions by representative-point
  depth (the overlap usually occludes as solid). Partial overlap of filled
  paths within a layer is effectively undefined behavior; emit properly
  nested or disjoint filled loops (pre-union overlapping shapes yourself,
  the way the brush tool spec does).
- **Use `ctx` for stability.** `ctx.seed` is stable per independent layer —
  mix it into your RNG so overlapping layers differ and re-resolves reproduce.
  Animate and appended keyframes inherit the original field identity via the
  optional persisted `CanvasLayer.effect_seed`; ordinary duplicates get a fresh
  field. Never derive RNG state from `ctx.layer_id`, object IDs, clock time or
  global mutable RNGs: those defeat animation identity and caching.
  `ctx.translation` is the layer's placement: sample noise fields at
  `point − ctx.translation` so dragging a layer keeps its character
  (see `coherent_jitter.py`).
- **`ctx.page` is the page rect** (x, y, w, h) — the paper guide, or the
  full bed when no guide is set. Use it for page-relative geometry
  (`invert.py` is the worked example); it's `None` only in hand-built
  contexts, so fall back to the bed constants.
- Declare missing optional deps via `available()` rather than import-time
  crashes; the UI greys you out with your reason.

## Writing a Transform

Document-level ops over **resolved** geometry. Since v2 these power the
plot-pass optimisation step (`PlotOptions` → `session._optimize`); they are
not user-stackable. The pattern worth copying is `transforms/vpype_ops.py`:
subclass `VpypeTransform`, emit a vpype CLI fragment, and conversion is
handled. To expose a new one in the Plot tab, add a field to `PlotOptions`
(`compose.py`) and a branch in `session._optimize`.

## Writing an execution backend

Unchanged from v1 — `backends/base.py` is the protocol, `simulator.py` the
reference implementation, and `axidraw_native.py` / `saxi.py` the serial and
subprocess variants. The compositor changes nothing here: backends consume a
flattened `PathDocument` exactly as before.

```python
class MyBackend(ExecutionBackend):
    id = "mybackend"
    label = "My backend"
    Params = MyBackendParams      # ONLY params you actually honour

    def capabilities(self) -> BackendCapabilities: ...
    def connect(self, port): ...
    def disconnect(self): ...
    def deactivate(self):
        # MUST release the serial port / kill subprocesses — this is what
        # makes backend switching safe; the manager calls it on every switch.
        self.disconnect()

    def plot(self, doc, params, control, emit):
        emit({"kind": "started", "paths_total": n})
        for layer, path in doc.iter_paths():
            if control.stopped: break
            control.wait_if_paused()
            ...
            emit({"kind": "progress", "paths_done": i, "paths_total": n,
                  "progress": i / n, "position": [x, y]})
        # pen UP on every exit path, including exceptions
        emit({"kind": "stopped" if control.stopped else "finished"})
```

Register in `MachineManager.__init__` (`axibridge/machine.py`). Rules:

- `plot()` is blocking, runs in a manager-owned thread; honour `control`
  (pause/stop) at your natural granularity.
- `emit()` dicts become SSE events; kinds the frontend knows: `started`,
  `progress`, `position`, `message`, `finished`, `stopped`, `error`.
- Honest capabilities only — a pause button that doesn't pause leaves a pen
  on the paper. The UI renders exactly what you advertise.
- Report import failures with `sys.executable` in the message (see
  `axidraw_native.available()`) — environment mismatch must be diagnosable
  at a glance.
- A streaming/look-ahead backend fits this same `plot()` seam: feed the EBB
  incrementally, check `control` between chunks.

## Checklist before you ship a module

- [ ] Params bounded, titled, described.
- [ ] `id` unique and stable (it's persisted in project manifests).
- [ ] Pure: same input + params + ctx → same output, input untouched.
- [ ] Coordinates mm; sources non-negative; `filled`/closure preserved.
- [ ] Optional deps via `available()`.
- [ ] A test in `tests/` — the simulator keeps backend tests hardware-free.

### Optional bounded element placement

A source may implement `placement_frame(params) -> (width, height)` when its
output document is guaranteed to lie inside that physical frame. Session creation
then uniformly fits the entire frame to the bed, including portrait orientation;
the stored layer affine is what the single resolve consumes. View toggles compose
the relative old/new frame placements so roundtrips preserve scale. Default is
`None`, preserving existing generator placement. Second Reading is the first
user: whole-element fitting happens in its document, and this hook prevents the
canvas's later quarter-turn from making the kept element exceed the bed. It does
not constrain manual layer transforms or effects.


Bench adapters currently registered at version 1 are `process`, `homeostat`, `territory`,
`second-reading`, `magnetic-field`, `linedraw`, `mosca`, `mosca2`, `hand-drift` and `gesture-studies`. Homeostat owns a grouped form schema in `homeostat_bench.js`;
its generation recipe is unchanged. Schema groups may set `groupOpen: true` for
an initially expanded group; a remembered user preference takes precedence.

`magnetic-field` is a non-temporal arrangement editor (`new`, `resume`). Its
bounded hidden `magnets` list stores explicit bar/pole positions, rotations,
sizes and strengths. Scattering is a seeded editor action whose results become
that list. Server generation owns the field; no client field solver or new API
is involved. `keep_silhouettes=False` only opens body footprints when
`show_magnets=False`; visible bodies always exclude field ink. Resume copies a
kept recipe, and Keep creates another layer through the normal creation path.
The bench uses `placement_frame` to fit its fixed drawing frame to the bed.

The magnetic bench also stores four optional `presets` (A/B/C/D), `mix_x`,
`mix_y`, `mix_active`, canonical `preset_sizes`, scatter strength bounds and
per-magnet `locked` flags. These are editor metadata: the explicit `magnets`
list remains the sole geometry input. The bench blends position/strength
bilinearly, unwraps angles for a continuous square, then fits each pose into the
frame. Canonical sizes prevent temporary fitting from becoming size blending.
Presets keep indexed magnet kinds/polarity and frame fixed; clear them before
structural edits. Locks affect Scatter only. `pole_spacing` optionally thins
whole routes after boundary filtering and before mark styling; zero preserves
the existing geometry. It compares closest sampled approaches within 12 mm of
each pole, not global curve clearance.


### Hand Drift bench (2026-10-17)

`hand_drift` (`sources/hand_drift.py`, adapter `hand-drift` v1 in
`static/js/hand_drift_bench.js`, modes `new`/`resume`) is the gesture
research's round-8 "limb" made a bench as it is: one line whose hand drifts
along a route of 2–4 learned hands. Plan and Ian's decisions:
`docs/superpowers/plans/2026-10-17-hand-drift-bench.md`.

- **Frozen engine.** `sources/_hand_drift/` is a vendored, trimmed copy of the
  research code (`tools/gesture/gesture/`) frozen at commit `c897f28`
  (`FROZEN_FROM`): grammar chain, `drift_line`, regimes, nib styles, timing
  and field. It does not follow the research; a change there is a deliberate
  engine version (`tests/test_hand_drift.py` holds golden research values).
  numpy / scipy / shapely only. The app never reads `.local/` or `tools/`.
- **Frozen hands.** `_hand_drift/hands/*.npz` (eight hands, ~600 KB with six
  dance tempo profiles) are written by `tools/hand_drift/freeze.py` from the
  research grammars, lossless (integers at the research's rounding; the
  drift is bit-identical to the research on the same seeds). Provenance per
  hand is in `hands.json`. Arabic hands come only from generative-allowed
  sheets; a test holds the allow-list. Qur'anic/devotional material is
  measure-only and never reaches a hand.
- **Switches** (all visible as segmented controls in the bench): blend
  `mixture`|`interp`; joins `smooth`|`chain` (chained context — the
  "failure" Ian kept); lines 1–8 with route per line
  `same`|`rotate`|`shuffle`|`each` (`each`: one hand whole per line, no
  drift); regimes `off`|`timing`|`field` with amount, nib/mass width, nib
  angle and the wrist toggle; ink `a`|`b+`|`c`|`e`|`c+e`; pen width.
- **Output.** Lines are grown in the research frame (1000×1200 px), fitted at
  one common scale into grid cells of the `width`×`height` frame
  (`placement_frame`; default 267×180 sits inside the A4 guide once
  centred on the bed). Wire lines are open paths. With regimes on, ribbon and
  mass outline rings are closed `filled=True` (exterior and holes, even-odd);
  line runs, fills and lanes are `filled=False`. Paths are simplified at
  0.01 mm. Line i uses `seed + i`.
- **Cost.** Wire: ~0.2 s per line. Regimes: ~1.5–3 s for one line, ~9–13 s
  for eight (inking runs one thread per line; output is order-identical).
- **Unlisted (2026-10-17).** Gesture Studies replaced it in the dropdown: Hand
  Drift is that bench's first study, through this same engine (identical
  output). `hand_drift` keeps `listed = False`, `library_bench = False` and
  its `hand-drift` bench, so kept layers resolve and resume. `render_paths`
  takes optional `load_hand` / `load_timing` so the study can reach library
  hands this engine never froze.

### Gesture Studies bench (2026-10-17)

`gesture_studies` (`sources/gesture_studies.py`, adapter `gesture-studies` v1
in `static/js/gesture_studies_bench.js`, modes `new`/`resume`,
`library_bench`). Spec and Ian's decisions:
`docs/superpowers/specs/2026-10-17-gesture-studies.md`. One generator, a
study dropdown inside; each study shows only its own controls.

- **A study** (`sources/_gesture_studies/studies.py`) is a frozen recipe + a
  few controls + version + parent. A control points into the recipe (`path`,
  or `paths` to set several places at once) with a label and a type: `int` /
  `float` (`min`/`max` required, inside the module param's own bounds), `bool`,
  `choice` (a subset of the param's), or a library pick — `hand`, `hands`
  (`min_len`/`max_len`; `join: " "` for a space-separated pool), `tempo`,
  `trail`. Seed is always a control. Everything else is fixed. A control's
  default is the value at its path. `check_study` validates the recipe with
  its engine and every control against the param it points at; `resolve`
  writes values in and validates again.
- **Engines.** `kit`: the frozen gesture kit (`_gesture_studies/kit/`, research
  commit in `kit/FROZEN.json` and every file header; `kit/_research/` holds the
  research modules it imports; calligraphy is a `PolicyError` stub). `hand_drift`
  (the first study): delegates to `sources/hand_drift.render_paths`, identical
  to the standalone generator; hands/tempos outside that engine's frozen set
  are decoded from the Gesture Studies library into its compact grammar form.
  The kit needs numpy / scipy / shapely, plus Pillow (a declared app
  dependency) for penrender's pen-lift coverage raster — kept for parity.
  `engine.install_hooks` wraps every kit stage and the long research loops with
  `checkpoint()` so superseded previews cancel; output is unchanged.
- **Library** (`_gesture_studies/library/`, `frozen_library.py`): EVERY
  generative hand / tempo / dance trail of the research library (policy gate
  applied at freeze time; measure-only entries never become options) plus the
  corpus index entries the gate reads. Content-addressed and append-only:
  `<kind>/<id>/<hash12>/`, `snapshots/<id>.json`, `index.json` (`current`,
  `history`, `withdrawn`). Hand / tempo / dance controls list whatever the
  current snapshot holds, so a refreeze after new hands are learned adds them
  to every study with no study edits.
- **Kept layers** carry `study` (full snapshot), `values`, and — filled by
  `complete_params` when a layer is created or regenerated, never on preview —
  `library` (snapshot id) and `pins` (kind/id/version/hash of every entry the
  controls name). A layer therefore never changes when a study is edited or
  deleted, or the library refrozen (old hash folders and snapshots stay).
  Resume restores the layer's recipe and pins; the first edit drops the pins
  (Keep pins the current library again). Presets exclude `library`/`pins`.
- **Saved studies** (`gesture_studies_store.py`, machine-level beside the pens
  and gallery, `AXIBRIDGE_CONFIG_DIR` in tests): "Save as new study" stores
  the current study with the current values as its recipe, a fresh id,
  version 1 and `parent` = the study + version it grew from. Built-ins ship in
  `_gesture_studies/studies/<id>/study.json` (order in `index.json`) and cannot
  be deleted. API (`gesture_studies_api.py`): `GET /api/gesture-studies`
  (studies, library options, snapshot), `POST /api/gesture-studies` (save a
  fork), `POST /api/gesture-studies/validate` (Edit recipe drawer),
  `DELETE /api/gesture-studies/{id}`.
- **Output.** The recipe's frame in mm (`placement_frame`), simplified at
  0.01 mm, closed rings closed exactly, nib/mass outline rings `filled=True`,
  everything else open or unfilled; `_fit_inside` safety net. Deterministic
  across processes and `PYTHONHASHSEED`.
- **Refreeze**: `.local/gesture/.venv/bin/python tools/gesture_studies/freeze.py`
  (reads `git archive HEAD`, never the working tree; re-checks that the frozen
  copy reproduces the research kit exactly; writes the parity fixtures in
  `tests/fixtures/gesture_studies/`). Adding a kit module a new study needs:
  append it to `KIT_MODULES` / `RESEARCH_MODULES` there.
- **Measure** (bench v3 move G, 2026-10-19; `_gesture_studies/devices.py`):
  the 13 round-15 measuring devices (`kit/_devices.py` contract, `kit/devices_*`)
  frozen with the kit; parity fixtures in `tests/fixtures/gesture_studies/devices/`.
  A layer's `devices` param (`[{"id", "place": over|under|margin|beside, "side",
  "size", …params}]`, empty = off) is checked against the frozen registry
  (`check_specs`: numbers bounded, choices closed, inks Flexoki names, the
  ledger's `drawn_by` a library hand, pinned at Keep). The engine lays them on
  the finished sheet (`render_measured`; `beside` grows the frame, drawing and
  devices fitted as one) and the preview reports each device's run, its inks
  count (0 = nothing to read: the bench says so) and `measure_layer`. Keep with
  devices on (`POST /api/gesture-studies/keep`) makes a group: the drawing (or
  one layer per voice) with `show: "drawing"` plus ONE "Measure" layer
  (`show: "measure"`) on its own pen, one undo step; the Measure layer sits
  below when every device is `under`. Slow: the hand-drawn ledger (~30 s on a
  busy study) and the misfit grid (1–15 s); the rest under 0.25 s.
- **Cost** (app venv, default values): Hand Drift 0.4 s, Drawing and its
  measure 0.3 s, Three voices 0.8 s, Conversation 1.6 s, Danced chain 4 s,
  Annotated page 4 s, Two voices 10 s, Shape atlas ~60 s (drawn by a hand;
  ~0.6 s machine-drawn).

 adapters call
`openGallerySave({kind: 'generator', module, params}, suggestedName)` with the
exact completed preview recipe. The promise spans the save/cancel dialog;
guard against pending renders, stale keys, gestures and other writes. Save
does not Keep, close the bench, or modify its draft. The backend regenerates
full paths through the existing memo; never send display `lines` as geometry.
See [Asset gallery](ASSET-GALLERY.md).

### Animation stability contract (2026-09-09)

An untouched Animate A/B/C chain must render the same drawing throughout.
Generators are pure functions of validated parameters: equal seeds, **including
zero**, remain fixed across animation. To choose a fresh starting seed, use the
creation/edit action and store the chosen value; do not reroll during generate.
Different explicit endpoint seeds still request per-frame random variation;
for a smooth random-pattern transition, expose a continuous blend between two
fixed seeds, as Ribbon does. Discrete enums/bools still step by design.

Both effect and generator interpolation use their parameter models to restore
numeric types before lerping (JSON `0`/`1` does not make a float slider integer).
The same rule covers nested generator tweens and capture blending. Effects use
`ctx.seed`; the compositor and tween caches include the effective field identity.
Old layers without `effect_seed` keep their original ID-derived field. Older
animation files are not silently migrated; matching keyframes can explicitly
share the original's effective seed when repairing an existing animation.

`tests/test_animation_random_identity.py` registers fresh probe effect/generator
modules to check this shared contract, plus real Ribbon, append, cache, undo
and serialization checks. Follow it when adding module-specific animation tests.

### Cancellable preview work (2026-09-09)

Long effects should call `axibridge.render_work.checkpoint()` at bounded work
intervals and before/after expensive geometry operations. Generators already
using `registry.report_progress()` get the same checkpoint automatically.
These hooks are no-ops outside an explicit read-only preview scope; do not
wrap project mutations or plotting in a cancellable scope. Cancellation raises
`RenderCancelled` (a `BaseException`) so ordinary geometry fallback handlers
cannot turn an obsolete render into a successful partial drawing. Use `finally`
for temporary resources; never swallow this signal or cache partial output.

The interactive resolved/effect-preview/plan/sheet/raster HTTP endpoints return 409 with
`detail.code == "render_cancelled"` when superseded by an edit/deletion. Treat
that as cancellation, not a toast-worthy failure. Layer edits, regeneration,
ordering, tween edits and undo/redo signal cancellation before taking the session
lock. Committing source regeneration remains atomic and is not itself aborted.
A single native GEOS call cannot be interrupted; the next checkpoint handles
it. Full percentage progress is deliberately not inferred from strand count:
clipping and unions have irregular costs.

### Curve accuracy defaults and wording (2026-09-09)

Ian wants curves to start smooth without having to diagnose hidden quality
settings. Pen, including Pen silhouettes inside Shape, defaults to its finest supported
tolerance, 0.05 mm. Explicit
stored tolerances are respected. Future curve-producing modules should favor
fine geometry by default and make any quality/cost trade-off explicit.

For a geometric approximation error, use **Curve tolerance (mm)** and explain
**lower is smoother; higher uses fewer points and may show facets**. State
whether the tolerance is measured before or after placement/scaling. This is
actual path geometry consumed by effects and plotting, distinct from a raster
preview's resolution. Keep those controls clearly distinguished. Do not hide
quality loss behind automatic simplification or a silently exhausted point
budget; report a limit or expose a deliberate coarser setting.

Pen, Shape, Grammar, Text/Text Fill and SVG import use the shared wording. Their numeric
ranges are module-specific; a label change does not rewrite existing recipes.

Affine placement does not reflatten source curves: scaling a layer up also
scales its existing approximation error. Prefer finer source geometry before
large enlargement; display resolution cannot recover missing curve detail.


### Animation ownership and tool completion (2026-09-09)

`CanvasLayer.animation_owner_id` belongs to the session family operations, not
module recipes. Owned keys cannot be reused as independent tween sources or
merged away. Use keyframe add/remove/reorder and family duplication; never
construct a copied owner ID without updating the master's key list. See
ARCHITECTURE.md for load adoption, deletion and compositor rules.

Pen/Shape commit helpers return the committed layer ID (null on a failed
write). Successful writes remain committed if subsequent preview refresh fails.
The tool broker returns to Select unless Repeat is enabled or the user already
chose another tool. Keep failed drafts until retry/cancellation and block new
gestures during a pending write.

### Module browsers and presets

The registry publishes representative example parameters and an explicit
preset-exclusion contract. Captured drawing data, interventions and external
image references must not become portable starting-settings presets. Add a
round-trip/reset test when introducing such fields or a new bench adapter.
All editable adapters use the shared `createPresetControls` component, supply
a current draft snapshot, guard pending renders/gestures, and reset local
interaction state when applying resolved settings. Watch views remain read-only.
See [Module library](MODULE-LIBRARY.md) for storage, lifecycle and API behavior.

Library category filters are exposed as `library_categories` in catalogue
metadata. Sources derive Image/Procedural from asset inputs and independently
add Bench for the product working benches (`library_bench` opts extensions in).
A temporal Watch view alone does not make a generator a working bench. Effects describe intended input with
`library_category = "line" | "shape" | "agnostic"`; built-ins are explicitly
classified in the registry. This is a browsing aid, not geometry validation.

### Recorded trajectory benches

Mosca uses a dedicated `mosca` v1 adapter (`new`, `resume`) to browse external
recordings and retain prefixes as layers. A hidden `format: "asset"` parameter
references the compact recording, so existing cleanup and preset exclusions
apply. Preparation stays outside project assets; successful layer creation
persists the recording, and normal save/load/ZIP carries it. Sources use a fixed
`placement_frame` derived from the full recording, never from the prefix.
See [Mosca recording bench](MOSCA-BENCH.md) for the pen-mask and import contracts.

### Mosca 2 composition bench

Mosca 2 uses the `mosca2` v1 adapter (`new`, `resume`). Its pure frozen source
stores bounded parts, settings and before/added exchanges; it resolves without
Mosca data. `mosca2_api.py` owns draft jobs, while `mosca2/worker.py` runs the
full model and flowing renderer in an isolated process. Keep uses the ordinary
source endpoint; no alternate plotting path exists. The browser composer
reuses Territory's worker generator and bundled earlier flowing material.
See [Mosca 2](MOSCA2.md) for sensing, portability and runtime contracts.

### Client-engine benches (Territory)

Territory (`sources/territory.py`, `static/js/territory_bench.js`, adapter
`territory` v1, `new`/`resume`) is the one bench whose geometry is computed in
the browser. The engine is the approved meander prototype, generated as an ES
module into `static/js/territory/engine.js` by `tools/territory-prototype/build.sh`.
Never edit the generated file; `tests/test_territory_engine_js.py` fails when it
is stale and pins the Version 10 output. It runs in a module worker
(`territory/worker.js`), which works in both the built and the source-only
(Pi) frontends.
- **Keep** sends the stage's exact strokes, simplified at 0.05 mm and rounded
  to 0.01 mm, together with the `recipe` (seed and dials).
- **The source replays the strokes verbatim** and never recomputes, so the
  single resolve path and the Pi need no JavaScript.
- **Resume** re-runs the deterministic engine from the stored recipe, with
  every dial live.


## Group placement and form comforts

Sources remain local geometry. The compositor applies layer/group placement
before effect stacks, so effect distances remain millimetres. Effects must never
inspect or mutate group metadata. Reference-frame interpolation and visibility
are resolver responsibilities; the plotting route stays the same. See
[LAYER-GROUPS](LAYER-GROUPS.md).

Numeric seed fields expose a reroll through their existing onChange path, using
schema minimum/maximum bounds. Preset Select/Apply remains immediately available;
Save/Update lives under Manage presets. Asset-field dropdowns refresh after
Assets-tab import, clearing unused media or Depth Pro completion. Canvas drops
continue binding the current generator without moving its Compose form.
