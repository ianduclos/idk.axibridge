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
"📷 Image-driven" optgroup in the Add-layer picker automatically.

Image-driven modules read pixels through `assets.asset_store`:
`grayscale(name, blur_px)` (cached per blur radius — derive `blur_px` from a
`smoothing` mm param × image px / placed mm width) and `alpha(name)`
(unblurred crop mask, `None` when absent). Shared brightness/contrast/gamma/
levels behavior lives in `image_processing.py`; apply it to grayscale samples,
not alpha masks. If the named asset is missing, **pass through / return empty,
don't raise** in effects (a stored project must still resolve); generators
may raise a helpful `ValueError`.

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
- Slow generators should call `registry.report_progress(frac, msg)` from
  their loops — it feeds the Generate button's load bar over SSE and is a
  no-op outside a request. Call it freely; the API layer throttles.
- **Pixel-space image generators** (the plotterfun family): subclass
  `sources/_pixelgen.PixelGenParams` (image/rotate/width/show_map + the
  collapsed Image processing group), sample darkness 0–255 through
  `ImageSampler`, and return via `pixel_doc(...)` — it scales the fixed
  800-px working canvas to the `width` mm placement. Copy `sources/subline.py`.
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
  `sources/drawing.py` + `static/js/draw.js`. **Tween: captured geometry now
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

- **You receive geometry already placed on the paper** (the layer transform
  runs first). So a millimetre in your params is a millimetre on the sheet,
  no matter how the layer is scaled — that's the system's promise to the
  user; don't undo it by scaling your own output.
- **Be pure.** Return new `Path` objects; never mutate inputs. The
  compositor caches and re-runs stacks freely; the before/after of a toggle
  depends on the input surviving.
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
  `hatch_fill` XORs (`symmetric_difference` — the overlap lens comes out
  unhatched) while `compose.build_mask` unions by representative-point
  depth (the overlap usually occludes as solid). Partial overlap of filled
  paths within a layer is effectively undefined behavior; emit properly
  nested or disjoint filled loops (pre-union overlapping shapes yourself,
  the way the brush tool spec does).
- **Use `ctx` for stability.** `ctx.seed` is stable per layer — mix it into
  your RNG so overlapping layers differ and re-resolves are reproducible.
  `ctx.translation` is the layer's placement: sample noise fields at
  `point − ctx.translation` so dragging a layer keeps its character
  (see `coherent_jitter.py`).
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
