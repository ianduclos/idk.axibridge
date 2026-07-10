# Roadmap

Loose, ordered by conviction. Each item says *why*, so a future session (or
a smaller model) can judge whether the reasoning still holds before acting.
Rules of engagement for any of it: the resolve invariant and the module
contracts (ARCHITECTURE.md, docs/MODULES.md) are not negotiable; UI changes
must keep the zero-build ES-module setup; every numeric param stays bounded.
Loose generator brainstorms (uncanny/Cohen-line direction, plus how the
involved ones should meet the UI) live in `docs/IDEAS-generators.md`.

## Near term — make what exists comfortable

The UI is functionally complete but cluttered and navigation is weak.
Cheapest-first:

- ~~Canvas zoom & pan~~ — **shipped July 2026** in `canvas.js` as a
  display-only viewBox transform. Mac trackpad two-finger scroll pans, pinch
  zooms around the cursor (`ctrl`-wheel / Safari `gesture*`), and the fit
  button or empty-canvas double-click refits. Geometry and plotting remain
  untouched because pointer math still flows through `getScreenCTM()`.
- **Collapsible panels** (`<details>`/`<summary>` needs ~no JS) and
  collapsed-by-default effect steps showing a one-line param summary.
  The Compose tab with three layers + stacks is already a wall.
- **Drag-to-reorder layers** in the list (replaces ↑/↓ spam).
- **Keyboard**: arrows nudge selection 1 mm (shift = 10), ⌘D duplicate,
  numbers 1–4 switch tabs. The keydown plumbing exists (main.js).
- **🎲 seed reroll in the main forms** (IDEAS pass-1 UI principle 3): one
  generic forms.js addition — a dice button beside any `seed` field — pays
  off across every stochastic module. The workbench has its own recipe-wide
  reroll; this brings the affordance to Compose layer/effect forms.
- **More simple effects** — each a drop-in pure file, ~an afternoon each:
  - *Perspective / 3D plane rotation*: treat the layer as a textured plane,
    tilt around x/y, perspective-project. Pure point map; bound the tilt so
    the horizon (division by ~0) is unreachable.
  - *Polar wrap*: x→angle, y→radius about a centre — straight hatching
    becomes rings/spirals; grids become spider webs.
  - *Mirror / kaleidoscope*: reflect/rotate-stamp about a paper-space axis.
  - *Offset rings*: shapely `buffer` at k spacings — bold "thick stroke"
    rendering for a single pen, and topo-map insets from filled shapes.
  - *Dash / stitch*: cut paths into dashes (gap, phase) for texture.
  - *Lens / attractor warp*: radial push/pull with falloff about a point —
    the hand-placed complement to the depth map.
  - *Crop*: ~~rectangular crop~~ — **shipped July 2026 as a plot-pass
    option** (PlotOptions.crop: guide/bed/custom + inward margin, vpype
    `crop` before merge/sort; exports and estimates included; canvas shows
    a dashed frame). A per-layer crop *effect* (this item's original form)
    is still open if paper-space per-layer clipping is ever wanted.
- **Image contours generator**: reuse `image_threshold`'s marching squares
  at N thresholds → nested contour rings (topographic shading). Most of the
  code already exists; it is the natural sibling of threshold + hatch.
- **Generator quality-of-life** (deferred by choice June 2026, when the ten
  plotterfun ports landed; the progress bar + grouped picker shipped then,
  and live param preview followed — `/api/generators/preview` + the dashed
  overlay; toggle persists in localStorage, requests are debounced and
  strictly serialized, responses decimated past 60k points):
  - *Presets & favourites*: named param sets per generator in a global JSON
    store (pattern: `stores.py` pen library), plus starred generators
    pinned at the top of the picker. This is also where the pass-1 **style
    genome / "hand" presets** land ("nervous", "tired" freehand hands;
    two_hands agent genomes — its params are already grouped for it):
    presets over parameters, per IDEAS pass-1 UI principle 2.
  - *CMYK / greyscale separation* (re-affirmed June 2026 — high conviction):
    image-driven generators (anything with a
    `format:"asset"` param — the picker already detects this) get a
    "separate channels" mode emitting one layer per C/M/Y/K channel, each
    assignable to a pen. Needs `asset_store` channel decode + a multi-layer
    return path from generate (the PathDocument already supports it).
- **Hershey/single-stroke text generator**: classic plotter need; fonts are
  public domain (Hershey set), output is plain polylines.
- **Plot resume**: the job already reports `paths_done`; persist the last
  finished index and offer "resume from path N" after a USB/power failure.
  Saves real plots, cheap to do at path granularity (native backend plots
  path-at-a-time already).
- **Interpolation-layer ergonomics** (user wishes, June 2026):
  - New tween layers should insert **between** the two source layers in
    z-order — specifically just below the upper one — not on top of the
    stack; a morph reads as belonging to its parents.
  - Dividing sweep copies into separate layers: `÷ Split into layers`
    exists (bakes each sweep step, tween stays hidden) — revisit the flow
    so it feels first-class (placement of the split layers, per-copy pens
    without hunting, maybe split-on-create option).
- **Survey off-kilter generation/effect ideas**: a research pass over the
  plotter-art space (and beyond plotterfun) for unusual-but-effective
  generators and effects worth porting or inventing — keep a shortlist
  with a sample image each before committing to any.

## Near term — Oehlen pass: regime collision (July 2026)

From the second idea pass (`docs/IDEAS-oehlen-pass.md` — read it first, the
*why* lives there). Ordered by dependency, not just conviction:

0. ~~Generation workbench popup~~ — **shipped July 2026**: ⚗ Bench button →
   popup with generator + effect stack (same auto-forms), 🎲 reroll of every
   seed in the recipe, live SVG preview via stateless
   `POST /api/workbench/preview` (no session/undo contact), global scrap
   library (`scraps.py`, `~/.axibridge/scraps/`, frozen SVG + recipe
   metadata), import live (generator layer + effects) or baked (scrap SVG →
   layers, library name kept). Later: mouse drawing, scrap editing.
1. ~~Bitmap + fat tube effects~~ — **shipped July 2026** as
   `effects/bitmap.py` (merged staircase blocks, grid anchored to layer
   translation, `solid` interior fill) and `effects/fat_tube.py`
   (round-capped filled pipes, per-path buffers so occlusion/draw order
   survive; loops self-merge with paper holes). Both stack with
   `hatch_fill`/`freehand`.
2. ~~Region layers ("affects below")~~ — **shipped July 2026** as
   `CanvasLayer.region`: placed silhouette masks, effect stack applies to
   layers below (inside clipped + effected, outside untouched), bottom→top
   stacking, post-effect/pre-occlusion so region output still occludes.
   Canvas shows the silhouette dashed; regions never plot. See
   ARCHITECTURE.md "Resolve order". Regions tween/animate for free.
3. ~~Continue-strokes v1~~ — **shipped July 2026** (Pi run) as
   `effects/continue_strokes.py`: order-N Markov over layer-adaptive
   quantized turning angles + step-length pool, temperature 0→1 from
   most-typical to full empirical spread; closed paths pass through.
   Neural v2 only if this feels shallow.
4. **Glyph grammar source** — Hershey strokes through destruction rules,
   `abstraction` dial from "almost reads" to pure scaffold.
5. **Perception pass — line weight = certainty** (the ideas doc calls this
   the strongest AI-age principle; promoted 2026-07-10): run several cheap
   perception passes over one asset (threshold edges, Depth Pro
   discontinuities, a segmentation boundary) and let *agreement* set the
   mark — fat beam where all agree, hairline wander where one thinks so,
   dither-density where ambiguous. Honors the far-section constraint: any
   model runs as an *asset producer*, the generator itself reads
   deterministic maps. Sibling: **perception scaffolding** (segmentation
   polygons, ill-fitting bounding boxes, annotation ticks as first-class
   marks — our era's pattern fill).
6. **Mouse preset for freehand** — the "bad hand": grid-quantized output,
   polling-rate resampling, sudden angular corrections. Cheap (params or a
   preset on the existing effect).

Also: **revise the pass-1 ideas** (`docs/IDEAS-generators.md` — rehearsal,
blind contour, phase transition) into roadmap items as conviction firms;
§1 shipped as `freehand`, and the July 2026 Pi run shipped §3
(`sources/misremembered.py`), §4 (`sources/grammar.py`) and §5
(`sources/two_hands.py`). **Tuning follow-ups from that run** are actionable
and live in `docs/plans/pi-generators-RESULTS.md`: a lattice grammar +
subtree-propagating violations, misremembered on a real photograph (widen
the searching-mark band if mid-confidence stays rare), two_hands genome
presets, a continue-strokes "seam pen" split. The *indifferent lines over
structured ground* recipe stays in the ideas doc — it's a composition
practice, not a module.

## Sheets workflow v2 (from the 2026-07-10 code review)

Findings and fixes for the grid-sheet/interp workflow; the analysis lives in
the 2026-07-10 session (summary here so it survives).

- ~~Fixed framing~~ — **shipped 2026-07-10**: `_grid_place(framing=)` —
  `"center"` re-centres each frame by its own bbox (parameter sweeps; pure
  translation animations cancel!), `"fixed"` uses one shared window so
  motion stays motion. UI defaults to fixed.
- ~~Crosshair marks~~ — **shipped 2026-07-10**: `marks=` on the sheet spec —
  ＋ registration crosses at every grid intersection, prepended to the FIRST
  pen pass (plot once per page), clamped to the bed.
- ~~Frame caches~~ — **shipped 2026-07-10**: `_frame_lru` (geometry, page-
  sized) + `_frame_bbox` (bounds for the shared-scale scan), keyed
  (t, pens-sig, assets-sig), cleared on any checkpoint/undo/history event
  and swapped in `_documents_with_temp_state`. Stepping pages/passes of an
  unchanged project now resolves each frame exactly once (was
  O(frames × pages × passes)).
- ~~One layout block in the UI~~ — **shipped 2026-07-10**: cols/rows +
  presets (1/2/4/16) + margin + framing + crosshairs feed the preview,
  stepper, "Capture to tray" AND the export link; the separate contact-sheet
  block is gone; a summary line says what the layout means physically.
  Capture-first is the stated primary path (tray sheets interp A ⇄ B).
  (Also fixed: module-level `captureStaged` called a closure-scoped helper —
  every staging-capture button was a ReferenceError.)

Still open, priority order (details in the session analysis):
- **`_documents_with_temp_state` → explicit args**: thread project/geo
  through `_documents_for_format` instead of swapping `self.*` under the
  lock; enables parallel interp batches.
- **Interp fidelity**: layers only in capture B append at the END of
  z-order in every in-between (needs a positional merge); batch steps are
  hard-linear — accept the tween `time_curve` enum.
- **Plot-cursor persistence**: the stepper's page/pass lives in browser JS
  and dies on reload; persist alongside staging (non-undoable) so a
  multi-hour flipbook survives a restart.
- **Staging browser ergonomics**: batches make the tray list long — a grid
  browser with thumbnails (scrap-strip pattern from the workbench).

## Animation — **SHIPPED July 2026** (v1: linear A→B over a master timeline)

Everything rides on the tween machinery; the master timeline `t` is an
ephemeral argument threaded through the single resolve path (never a second
geometry path, never a checkpoint). What landed:

- **Frame sequences**: folder/video import (`POST /api/assets/sequence`,
  imageio-ffmpeg) → assets named `clip#0000.jpg`; a normalized `frame` 0..1
  param on every image consumer (image_threshold, the pixel generators,
  depth_displace) — numeric, so the tween lerp scrubs video for free.
- **Master timeline**: `TweenParams.follow_master` + Compose scrubber
  (`/api/compose/resolved?t=`); one-click "⏱ Animate" (hidden A/B keyframes
  + follow-master tween, one undo step).
- **Outputs**: SVG zip (`/api/animation/export.zip`), plot-per-sheet stepper
  (`plot/start` takes `master_t`; explicit press per frame, paper swap
  between), and capture-to-staging as the primary contact/grid-sheet output.
  The old destructive contact-sheet bake still exists as an explicit
  editable-layer escape hatch.
- **Animation preview**: live SVG scrubber for quick timeline checking plus
  a raster popup (`/api/animation/preview.png`) for smoother playback of
  path-heavy frames. The PNG renderer still uses the single resolve path,
  then supersamples/downsamples and rotates to match the displayed page
  orientation.
- **Grid sheets** — **shipped July 2026**: plot many timeline frames per
  physical sheet (1/2/4/16 per page) without the destructive bake.
  `session.sheet_document` is transient plot-time assembly — no project
  mutation, one shared scale across ALL sheets (flipbook-consistent),
  grouped BY PEN so each sheet plots as one pass per pen (nib offset applied
  after placement). API: `SheetSpec` on `plot/start`, `?sheet=<json>` on
  `/plan`, `cols/rows/margin_mm` on `export.zip` (one `sheet_NN.svg` per
  page), and `GET /animation/sheet_info` (pass list per page). UI: a
  "per sheet" select drives a two-axis stepper (sheets × pen passes). This
  closes the old "2 A5 halves per page" ask (per-sheet = 2 → (2,1)) AND the
  per-pen deferral below.
- **Capture-based staging tray** — **shipped July 2026**: capture current
  plot/frame/grid output into saved project-owned staged sheets, each with
  frozen per-pass SVG geometry and a source snapshot. The Plot tab can rename,
  reorder, duplicate, delete, preview, export, plot, and explicitly insert a
  staged sheet as editable baked layers. Compatible capture pairs can generate
  interpolated staged batches from their source snapshots, so contact-sheet
  geometry flattening is no longer a dead end for batch variation.

**The frame-ladder recipe** (the canonical animation workflow, per Ian's
drawing — v1.4 semantics: positions never move with time, only clip content
advances; tween in-betweens are exclusive of A/B):

1. Import a clip (video or frame folder) → add a clip layer, tick **"clip
   follows timeline"** (layer panel, next to the frame offset).
2. Duplicate it, move the copy, set its **frame offset** (in frames, e.g.
   +3), tick its follow box too.
3. ⌘-select both → **⇄ interpolation**, set **copies** (in-betweens land
   strictly between A and B, sampling the in-between frames automatically).
4. Scrub the Timeline, or plot with the frame stepper (frames = clip length
   → one clip-frame per sheet). Each step: every position shows the next
   frame, conveyor-style; nothing moves on paper.

Deferred, roughly in order of pull:

- ~~Tween interpolation modes: linear vs cosine ping-pong~~ — **shipped July
  2026** as `TweenParams.time_curve = "linear" | "cosine_pingpong"` in the
  Timeline panel. Ping-pong maps morph time A→B→A over 0..1 while the raw
  master timeline still drives clip/frame-follow playback linearly. If we
  later want ordinary smooth A→B, add a separate `cosine_ease`
  (`0.5 - 0.5*cos(pi*t)`) rather than overloading the ping-pong behavior.
- **Multidimensional video / sheet variants, v2** — user idea July 2026:
  staging/batch interpolation now covers the first manual workflow: capture A,
  change parameters, capture B with the same format, then generate staged
  interpolated batches. The open question is a richer 2D authoring surface
  where timeline `u` is frame/clip time and variant `v` is a second parameter
  dimension with better browsing, naming, and traversal controls. Do not add
  a second global master timeline casually; keep any automation as temporary
  sampling over the existing resolver (`session.resolved(master_t=u)` /
  `sheet_document`) and preserve pen grouping, preview/export/estimate
  agreement, and undo sanity.
- **Easing curves beyond ping-pong / >2 keyframes** — a dope-sheet or
  keyframe list would deepen animation further. The data model question
  (keyframe lists vs. layer pairs vs. named channels) is the real cost, so
  keep it behind the smaller interpolation-mode experiment.
- ~~Per-tween t-mapping~~ — **shipped July 2026** as timeline windows
  (`window_from`/`window_to` on TweenParams: hold A, animate, hold B).
  Same round added cascade delete for animation groups, sequence-import
  start/every controls, auto-frame on animate, and the static-in-between
  button (a second non-following tween over the same A/B pair).
- ~~Per-pen contact-sheet layers~~ — **shipped July 2026** for the transient
  grid sheets (`sheet_document` groups by pen; each sheet = one pass per pen).
  The destructive `bake_contact_sheet` still flattens to one layer per frame
  by design (it's the editable variant); per-pen baking there is unclaimed.
- ~~GIF/PNG preview render~~ — **shipped July 2026** as the raster popup PNG
  frame cache. A server-side GIF/video export would be convenience only.
- Per-frame fades via pen pressure / multipass density (motion trails).
  ~~Registration marks for multi-sheet alignment~~ — shipped 2026-07-10 for
  grid sheets (crosshairs on the sheet spec); still open for plain
  multi-pass single-frame plots if ever wanted.
- Colour separation (above) intersects: per-frame AND per-pen matrices.

## Mid term — interpolation (the layer-variant idea) — **SHIPPED June 2026**

Implemented as designed below (`tween.py`; tween layers with t/sweep, live
refs, endpoint-exact lerp, delete-guard). Kept here for the reasoning.
Perspective shipped too. Remaining from "near term": zoom/pan (deferred by
choice), drag-reorder, keyboard nudge, polar wrap, image contours, Hershey
text, plot resume.

The wish: duplicate a layer, tweak generator params / effects / transform,
then **interpolate between the two**. This does *not* need a node graph:

- Everything that defines a layer's look is already a flat, typed,
  *numeric-heavy* dict: generator params, effect params (per step), the six
  affine numbers. Generic lerp over two such dicts (numbers lerp; bools/
  enums/strings step at t=0.5; mismatched effect stacks = hard error) gives
  an **interpolated layer**: a layer whose source is "tween(A, B, t)" and
  which regenerates through the existing single resolve path. One new
  `LayerSource.type`, one slider.
- **Sweep**: stamp K copies at t = 0…1 in one layer — the morphing-moiré
  plot that motivates this. (K bounded; estimates already per-layer.)
- Caveat to design around: param-lerp is only meaningful where geometry
  varies continuously with params (lissajous, grid, polygon: yes; `seed`
  fields: no — exclude integer seeds from lerp, hold A's value). A later,
  stronger fallback is *geometry* interpolation (resample both resolved
  sets to matched point counts, nearest-neighbour pairing, lerp points) —
  works across arbitrary sources, costs matching-quality artefacts.
- This is the best candidate for "before v3": it delivers the node-graph
  payoff (variation as a first-class object) with zero model rewrite.

## Far / undecided — AI-assisted inputs

Very down the line, deliberately after the manual pipeline is comfortable:
monocular **depth-map estimation** (MiDaS-class) so any photo yields a
depth asset for `depth_displace` without hand-painting; possibly
segmentation for auto-masking subjects. Constraint: keep it an *asset
producer* (a tool that writes into `assets/`), not a resolve-path stage —
the resolve pipeline stays deterministic and offline.

## Far / undecided — the node question

Intuition: modules are already pure functions; a node editor is "just" UI
over the same DAG. Honest counterpoints, recorded so the decision is made
deliberately:

- The current model *is* a graph — a linear one per layer, plus one global
  compositor node. Nodes pay off only when graphs stop being linear:
  sharing one source between two effect stacks, routing a layer's output
  into another's mask, parameter links. Today none of these exist.
- Costs: a canvas-plus-graph UI doubles surface area; project files become
  graphs (migration burden); "what does the canvas show" needs an answer
  for unterminated branches; zero-build vanilla JS node editors are
  non-trivial.
- **Criterion**: build nodes only when at least two concrete, wanted
  workflows are impossible in the layer model. Interpolation is not one
  (see above). Mask-routing ("use layer A's geometry as a clip for B's
  effect") would be the first real one — and even that may fit as an
  effect param referencing another layer.
- If/when: keep the IPR, registry, and resolve pipeline byte-identical;
  nodes become an alternative *editor* over `Project`, not a new engine.
  Anything that forces engine changes is the wrong node design.

## Documentation / robustness debts

- ~~`main.js mapGhosts()` special-cases module ids for show-map ghosts~~ —
  done June 2026: any generator layer with `image` + `show_map` params
  ghosts in the layer frame; only the depth-displace *effect* (paper-space
  placement) remains special-cased, correctly.
- The IPR has no hole representation; holes are separate filled loops.
  `hatch_fill` reassembles even-odd, occlusion does not. If holes start to
  matter for occlusion, that is an IPR change — design, don't patch.
- Pen-plotter-specific test gap: nothing exercises the native backend
  against recorded EBB traffic; a replay harness would catch the next
  protocol drift without hardware.
- **Unsaved-work guard** (added 2026-07-10, after an in-memory project was
  lost to an in-place server restart): the open project lives only in RAM
  until an explicit save, `POST /api/project/save` 422s on a bare body, and
  `/server/restart` drops everything with only a browser-side warning.
  Wanted: a periodic autosave to a recovery slot (NOT the project folder —
  don't clobber deliberate saves), and the restart endpoint refusing when
  unsaved changes exist unless `force=true`. Cheap insurance for a
  single-operator instrument.
