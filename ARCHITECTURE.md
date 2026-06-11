# Architecture

Why axibridge is shaped the way it is. Module authoring lives in
[docs/MODULES.md](docs/MODULES.md); agent-facing operational notes in
[CLAUDE.md](CLAUDE.md).

## The machine dictates the design

The AxiDraw V3 is **open-loop**: steppers without encoders, no limit
switches, no homing. Usable travel **300 × 218 mm** — physically landscape;
A4's long edge only fits along machine X, so an A4 sheet always lies rotated
on the bed. Consequences that run through everything:

1. **Position is dead reckoning.** Wherever the carriage sits at connect is
   (0,0); commanded position *is* physical position until a raw command or a
   skipped step desynchronises it. Hence: origin is a software offset
   ("set origin" can bind the frame to the paper-guide corner), and the raw
   console warns that it stales the reckoning.
2. **Nothing stops you driving into the frame.** Soft limits are enforced
   centrally in `MachineManager` — uniformly for every backend, and
   *toggleable*, because pushing the envelope is experimentation, not error.
   The raw trapdoor bypasses them by design.
3. **All intelligence is host-side.** The EiBotBoard executes timed moves;
   the planner lives in the host stack — which is why execution is layered
   with a raw-EBB trapdoor *underneath* the planner.
4. **No homing ⇒ multi-pen registration is human-in-the-loop.** The machine
   cannot find a datum itself; the A4 guide + set-origin give the human a
   repeatable one, and the pen-offset compensation (below) removes the
   *systematic* part of pen-swap misregistration.

## v2 in one sentence

v1's linear source → pipeline → plot became a **layer compositor**: layers
are first-class objects (provenance, affine transform, effect stack, pen
reference, occlusion properties) composited on a canvas that *is* the
machine bed; the compositor flattens to the v1 `PathDocument`, and the
entire execution column consumes that exactly as before.

```
 sources (generators / uploaded SVG layers)
    │ per layer
    ▼
 CanvasLayer ── transform (affine) ── effect stack (paper space) ──┐
                                                                   ▼
                    occlusion across layers (design frame, shapely) │ compose.py
                                                                   ▼
                resolved geometry  ←— THE single source of truth
                 │            │                │
                 ▼            ▼                ▼
              canvas      per-layer        plot pass (target = all | layer)
              preview     estimates          │ pen-offset compensation
                                             │ plot-pass optimisation (vpype)
                                             ▼
                                        PathDocument  →  unchanged v1 execution:
                                        machine.py → backends (native/sim/saxi)
                                        SSE events ← progress
```

### The resolve invariant

Preview, per-layer time estimates, and plotting all read from **one**
server-side resolve (`session.resolved*()` → `compose.resolve_project`).
"Plot this layer" means plot its *resolved* geometry — clipped by whatever
occludes it — never its raw source. If preview and plot ever disagree the
tool is worthless; this is the invariant everything else defends. (The
canvas applies a client-side *delta* matrix during a drag for instant
feedback, then commits and re-fetches the authoritative resolve.)

### Resolve order (deliberate, user-confirmed)

`resolved = occlusion(effects(transform(source)))` — transform **first**, so
effects operate in paper space: 0.5 mm of jitter is 0.5 mm on the sheet no
matter how the layer is scaled. Noise effects sample their field at
`point − layer translation` (layer-anchored), so dragging a layer doesn't
reshuffle its wobble. The canvas handles edit the same six matrix numbers the
server bakes (`<g transform="matrix(…)">` ⇄ `Affine`) — no impedance
mismatch by construction.

### Occlusion (shapely, not occult)

Per layer, two independent flags: **occluder** (masks layers below) and
**receives occlusion** (may be exempted from masks above) — a mid-stack
layer can be both. Masks are built from the occluder's *shaped* geometry:
filled closed paths become polygons (`Path.filled` is set from the actual
SVG fill at ingestion, or by generators); stroke-only paths become a swept
band at the pen's line width. Each occluder's signed **margin** buffers its
mask: positive opens a negative-space gap, negative deliberately bleeds
lower layers into it. Masks come from *pre-clip* geometry — like physical
opaque sheets, a partially-hidden occluder still masks fully.

**Pen-invariance:** occlusion is computed once, in the design frame. The
per-pen nib offset is applied later, as a plot-time toolpath compensation
that brings every pen's ink *to* the design position — so the one mask is
correct for every pen, and offsets are never folded into mask geometry.

Why shapely and not vpype-occult: occult has no signed margins, no
per-layer occluder/receives flags, and no stroke-band masks; shapely (already
a vpype dependency) provides polygon/buffer/difference directly.

### Pens & diameter-driven registration

The pen library is **global** (`~/.axibridge/pens.json` — the physical
drawer); projects snapshot the pens they use so a moved folder still knows
what drew it. The V-cradle holder self-centres every barrel on the vee's
bisector, so a pen's nib offset is one fixed direction scaled by barrel
diameter: `offset = holder_vector × ⌀`. The holder vector is measured once
(two pens, two plotted marks, calipered displacement ÷ ⌀ difference) and
stored machine-level; cataloguing a new pen is then just calipering its
barrel. Compensation translates each pass by `−offset`; the constant part of
seating error is common to all pens and absorbed by the origin. A zero
vector disables compensation — deliberately available when raw seating
misregistration is wanted as an artifact. Pen presets may carry pen-down/up
height overrides, applied when that pen's layer is plotted singly (the
manual multi-pen unit of work).

### Plotting — manual multi-pen

A selector (all / one layer) and a Plot button; swap pen, pick next layer,
plot again. No queue, no automation — no homing means the human owns paper
registration, and the tool's job is to make each pass land registered
(resolved geometry + pen compensation) rather than to pretend it can
choreograph pen swaps. Plot-pass **optimisation** (linemerge/linesort/
reloop/simplify, vpype-backed) runs on the resolved geometry of each pass —
it replaced v1's user-arranged pipeline because creative reshaping moved
into per-layer effect stacks, leaving optimisation as a property of the
*pass*, not the artwork.

### Undo, duplication, consolidation

The session keeps an 8-deep undo deque. Snapshots are cheap by construction:
the `Project` model is deep-copied, but geometry lists are shared by
*reference* — safe because the module contract forbids in-place mutation
(lists are only ever replaced wholesale). Every mutating `Session` method
checkpoints once under the lock; bulk operations (multi-delete) are one
checkpoint so one ⌘Z restores the lot. **Consolidate** bakes a layer's
transform + effect stack into its source geometry (resolved output is
bit-identical; the layer's `source.type` becomes `"baked"` but keeps
generator provenance, so *regenerate* explicitly reverts the bake).
**Duplicate** copies a layer sharing the same source-geometry list.

### Image assets (depth maps, threshold sources)

`assets.py` holds a module-level store (name → bytes, with cached
grayscale-at-blur-radius and alpha decodes) — a singleton, like the pen
stores, so effects (which only see paths+params) and the session (which owns
save/load) reach it without import cycles. Modules reference assets by name
through a string param tagged `json_schema_extra={"format": "asset"}`; the
form renderer turns that into a dropdown over uploaded assets with an inline
upload button. `show_map` params ghost the image on the canvas — preview
only, computed client-side in `main.js mapGhosts()`, which currently
special-cases the module ids that have placements (a known wart: a new
image-driven module wanting a ghost must add a case there). Brightness
sampling is bilinear over a Gaussian-blurred copy (the `smoothing` param, in
paper mm) — pixel steps and 8-bit banding never reach the geometry.

## Persistence

A **project is a folder**: `project.json` (the full `Project` model,
pretty-printed, diff-able) plus `sources/*.svg` — uploaded files verbatim,
generated *and baked* layers snapshotted as SVG (exact geometry survives
generator-code drift; generator id+params stay in the manifest for
re-editing) — plus `assets/*` (image assets, verbatim). Zip
export/import wraps the folder. Machine-level state stays out of projects:
pen library and settings (holder vector, estimator constants, projects root,
host/port) live in `~/.axibridge/`. A subtle but load-bearing detail: the
SVG reader divides by *svgelements'* mm constant (3.7795296 ≠ 96/25.4) so
mm→SVG→mm round-trips are exact and a reloaded project resolves
bit-comparably; snapshots also write real `fill` attributes (a tiny custom
writer) because vpype's writer would drop them and fills are mask input.

## What v1 established (still true)

- **`PathDocument`** — polylines, mm, machine frame, draw order = list
  order, pen-up travel implicit; the geometry⇄execution contract. v2 added
  one field: `Path.filled` (compose-side metadata; execution ignores it).
- **Capability advertising** — backends declare feature flags + their own
  Params model; the UI renders exactly what the active backend honours. No
  dead knobs: native has the raw trapdoor but no cornering field, saxi has
  cornering but no trapdoor, the simulator has everything plus time-scale.
- **Port arbitration** — `MachineManager.select_backend` always runs
  `old.deactivate()` (close serial / kill the saxi subprocess) before
  `new.activate()`.
- **saxi via CLI** — the stock saxi server's `POST /plot` takes a
  pre-computed plan (planning happens in its browser UI), so the supported
  SVG-in path is `saxi plot file.svg` as a subprocess.
- **SSE, not WebSockets** — progress is one-way; commands are POSTs;
  EventSource reconnects itself across Tailscale roaming.
- **Threads in the hardware layer** — pyaxidraw is blocking; one plot
  thread + `JobControl` events; the manager's lock serialises interactive
  ops against jobs.
- **`estimate.py` is an estimator, never a planner** — trapezoid + junction
  model for timing only; backends do their own planning. v2 moved its
  calibration constants into Settings so the ±15% can be tuned out.
- **Streaming seam** — a future look-ahead backend implements the same
  `plot(doc, params, control, emit)` signature, feeding the EBB
  incrementally; nothing above it changes.

## Stack

FastAPI + Pydantic v2 (one type system = contract + validation + UI schema;
sync handlers in the thread pool so serial I/O never blocks the loop);
zero-build vanilla-ES-module frontend (no toolchain on the Pi, view-source
debuggable; the only "framework" is ~80 lines of schema→form rendering and a
~400-line SVG canvas editor — fabric/konva were rejected as canvas-based,
heavy, and build-chain-y); shapely for occlusion; svgelements for fill-aware
SVG reading; vpype for optimisation ops and SVG export.

**Environment pinning:** the launchers hard-code the venv interpreter
because the classic failure is pyaxidraw installed into a different Python
than the server runs from. Backend `available()` diagnostics therefore name
`sys.executable` in the error — an environment mismatch reads as "pyaxidraw
not importable in /path/.venv/bin/python", not as a mystery.

**Binding:** default `0.0.0.0:2942` ("AXI2"), configurable in Settings.
**There is no authentication** — a deliberate v2 choice for the
single-operator LAN/Tailscale workflow, documented so it's a decision, not a
surprise.

## Known sharp edges (documented, not hidden)

- Soft limits measure from the **user origin**; re-binding origin to the
  guide corner shifts the guarded window accordingly.
- After raw motion commands, host position is stale — re-set origin.
- Native plotting hands each polyline to pyaxidraw's `draw_path` (the real
  planner, with lookahead and cornering across vertices). Never replace it
  with per-segment `lineto`: interactive mode plans each command as an
  isolated stop-start move — unusably slow on flattened curves, and the
  serial flood can wedge the EBB. Consequence: pause/stop land at *path*
  boundaries.
- The playback/travel overlay draws the *commanded* (pen-compensated) path;
  with a calibrated holder it sits `vector × ⌀` away from the ink position.
  Zero calibration ⇒ identical.
- saxi flags (`--no-sort-paths`, etc.) assume a current saxi;
  `SaxiBackend._build_cmd` is the single place to touch if they drift.
- pyaxidraw's numeric options must be **ints** (`_apply` casts); a float
  leaks into EBB command strings, the firmware errors, and the stray reply
  permanently desynchronises plotink's one-command-one-response reads —
  presenting as "USB connection lost" on a healthy link. Belt-and-braces:
  `_flush_stale()` drains the receive buffer before each command sequence.
- The path model has no holes: a traced hole (image_threshold) is its own
  closed filled loop. `hatch_fill` reassembles nesting even-odd, but
  occlusion masks union filled paths — holes read as solid to layers below.
- `POST /api/server/restart` re-execs the process in place (same argv/env);
  the in-memory project does not survive it.
