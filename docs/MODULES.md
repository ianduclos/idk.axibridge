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

Two more `json_schema_extra` tags with frontend meaning:

- `{"viewAxis": True}` on a paper-space x/y pair: in portrait view the label
  letter swaps and the displayed value negates, so the fader moves things
  the way the rotated bed *looks*. Only use on fields with symmetric bounds.
- `show_map: bool` params ghost the module's image asset on the canvas.
  This is wired client-side in `main.js mapGhosts()`, which special-cases
  module ids (it needs to know where the image sits) — a new image-driven
  module wanting a ghost must add a case there. Preview only; never plotted.

Image-driven modules read pixels through `assets.asset_store`:
`grayscale(name, blur_px)` (cached per blur radius — derive `blur_px` from a
`smoothing` mm param × image px / placed mm width) and `alpha(name)`
(unblurred crop mask, `None` when absent). If the named asset is missing,
**pass through / return empty, don't raise** in effects (a stored project
must still resolve); generators may raise a helpful `ValueError`.

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
  masks are built from your output.
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
