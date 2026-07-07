# Roadmap

Loose, ordered by conviction. Each item says *why*, so a future session (or
a smaller model) can judge whether the reasoning still holds before acting.
Rules of engagement for any of it: the resolve invariant and the module
contracts (ARCHITECTURE.md, docs/MODULES.md) are not negotiable; UI changes
must keep the zero-build ES-module setup; every numeric param stays bounded.

## Near term — make what exists comfortable

The UI is functionally complete but cluttered and navigation is weak.
Cheapest-first:

- **Canvas zoom & pan.** There is none today — the bed is always
  fit-to-viewport, which is most of "hard to move around". Wheel zoom about
  the cursor + space-drag (or middle-drag) pan, as an extra outer transform
  in `canvas.js` (display-only, exactly like the portrait rotation;
  `toBed()` already goes through `getScreenCTM().inverse()` so hit-testing
  survives untouched). Double-tap to re-fit.
- **Collapsible panels** (`<details>`/`<summary>` needs ~no JS) and
  collapsed-by-default effect steps showing a one-line param summary.
  The Compose tab with three layers + stacks is already a wall.
- **Drag-to-reorder layers** in the list (replaces ↑/↓ spam).
- **Keyboard**: arrows nudge selection 1 mm (shift = 10), ⌘D duplicate,
  numbers 1–4 switch tabs. The keydown plumbing exists (main.js).
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
    pinned at the top of the picker.
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
  between), contact-sheet bake (`/api/animation/contact_sheet` — shared
  scale across cells, `explode_tween`-style baked layers).
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

- **Tween interpolation modes: linear vs cosine ping-pong** — today the
  master timeline maps linearly into a tween's local A→B `t`. Ian wants to
  experiment with a "back and forth cosine" option where params/transform/
  effects ease from A to B and back to A over the same 0..1 frame range,
  while imported video/frame-sequence playback remains normal and linear.
  Implementation sketch: add a bounded enum on `TweenParams`, e.g.
  `time_curve = "linear" | "cosine_pingpong"`; keep the raw clamped
  `master_t` flowing into clip `frame_follow`; derive a separate shaped
  `morph_t = 0.5 - 0.5*cos(2*pi*local)` for param lerp, affine lerp,
  structural geometry lerp, and effect-param lerp. Be explicit in the UI
  that ping-pong ends at A, not B. If we later want ordinary smooth A→B,
  add a separate `cosine_ease` (`0.5 - 0.5*cos(pi*t)`) rather than overloading
  the ping-pong behavior.
- **Multidimensional video / sheet variants** — user idea July 2026: bake a
  16-frame animation into a contact/grid sheet, then vary another parameter
  on a second axis so there are parallel sheets/rows/pages that the "video"
  can traverse in different directions. Think of timeline `u` as frame/clip
  time and variant `v` as a second parameter dimension. Do not jump straight
  to a second global master timeline: start with a manual staging workflow
  that lets Ian set a secondary parameter, "add current grid sheet to batch",
  change the parameter, add another sheet, then export/plot the batch. That
  preserves the existing single resolve path and teaches the physical
  workflow before the data model grows. If/when automating it, model it as
  an ephemeral 2D sampling pass over the existing resolver: for each variant
  sample, apply temporary parameter/tween overrides, then call the same
  `session.resolved(master_t=u)` / `sheet_document` machinery. Watch-outs:
  undo history must not record per-sample mutation; pen grouping still needs
  to be by physical pass; preview/export/estimate must agree; naming should
  make "pages vs rows vs variants" clear.
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
- Per-frame fades via pen pressure / multipass density (motion trails);
  registration marks for multi-sheet alignment.
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
