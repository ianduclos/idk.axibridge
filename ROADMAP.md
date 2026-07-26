# Roadmap

Loose, ordered by conviction. Each item says *why*, so a future session (or
a smaller model) can judge whether the reasoning still holds before acting.
Rules of engagement for any of it: the resolve invariant and the module
contracts (ARCHITECTURE.md, docs/MODULES.md) are not negotiable; UI changes
must keep the zero-build ES-module setup — meaning no compiler/bundler in the
edit-reload loop, NOT "no tooling at all"; vendored single-file libraries and
`// @ts-check`+JSDoc are already in-bounds (see CLAUDE.md, ARCHITECTURE.md
"Stack"). A real bundler/compiler is a separate, larger, still-undecided call
— see "Far / undecided — UI revamp" below. Every numeric param stays bounded.
Loose generator brainstorms (uncanny/Cohen-line direction, plus how the
involved ones should meet the UI) live in `docs/IDEAS-generators.md`.

## URGENT fixes (Ian, 2026-07-13, from real use — do these first)

**Round worked 2026-07-13 on `fix/urgent-round1` (Sonnet agent waves,
Fable orchestrating). 11/11 shipped; suite 359 → 382; 12/12 live
Playwright/API checks. Bench eye-check still pending on: centering feel,
band select on a real photo, portrait width remap, viewAxis fader
direction (one fader's drag direction deliberately flipped — see the
feat(view) commit).**

1. ~~**Animation popup: show the last rendered frame**~~ — shipped: new
   frames render into a scratch buffer and swap in atomically; progress is
   an overlay badge; first-ever render still shows frame 0 immediately.
2. ~~**Tray "Preview sheet" → PNG popup**~~ — resolved by the merged
   `feat/animation-previews` canvas preview mode (banner + exit),
   Playwright-verified; Ian had proposed PNG because preview did nothing.
   No raster popup built — reopen only if the canvas mode still reads as
   nothing at the bench.
3. ~~**Center image-based generator output in the bed**~~ — shipped:
   centering Affine at `add_generated_layer`/`add_lineart_stack` for
   generators with an image param; procedural + clip-backed layers keep
   identity; stacks stay band-aligned.
4. ~~**Orientation coherence pass**~~ — shipped: params stay machine-frame
   forever; the display layer maps once via schema tags (viewRotate /
   viewAngle 360|180 / viewSize / viewOrient) in `static/js/viewmap.js` +
   forms.js; the portrait rotate=270 band-aids are gone (defaults remap
   generically); resolve is bit-identical across views (locked by
   `tests/test_view_coherence.py`). Includes the viewAxis sign fix — only
   the original-y fader negates in portrait now.
5. ~~**"Clear image assets" button**~~ — shipped: `DELETE /api/assets`
   (unreferenced-only by default, `?force=true` for all; referenced clips
   kept whole) + "Clear unused assets" button.
6. ~~**Depth Pro install**~~ — done: `apple/ml-depth-pro` in `.venv`,
   checkpoint at `checkpoints/depth_pro.pt` (1.8 GB, torch-load
   verified; dir gitignored). numpy moved to 1.26.4 — suite green.
7. ~~**image_threshold: min/max threshold range**~~ — shipped: true band
   select (inside = min ≤ v ≤ max, continuous at both extremes); legacy
   `threshold: t` loads as (0, t) byte-identical.
8. ~~**Effect-step boxes must not collapse on regenerate**~~ — shipped:
   `<details>` open-state persists across re-renders (openGroups Set +
   stateKey at all six renderForm call sites).
9. ~~**Workbench: separate image-based generators**~~ — shipped: picker
   optgroups (independent / image-based).
10. ~~**linedraw v1: higher resolution**~~ — shipped: `resolution` ×1..2,
    lineart-v2 pattern, px params scale with the canvas.
11. ~~**Menu-bar dropdowns**~~ — shipped: File (Save, Download SVG) +
    View (portrait/landscape proxies) in `static/js/menu.js`, no build
    step; existing control ids preserved.

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
  - *Offset rings*: ~~shapely `buffer` at k spacings~~ — **shipped
    2026-07-26** as `effects/offset_fill.py`, well past the "convenience"
    this item asked for: a second fill primitive beside `hatch_fill` that
    repeats the outline inward as concentric rings (contour-map look) rather
    than laying scanlines across it. `contract_expand` (2026-07-11) remains
    the per-path onion-ring tool; offset_fill is layer-wide because it has to
    run the even-odd hole assembly first. Topology needs no special-casing —
    components split, components vanish, holes grow and merge, and shapely
    returning a `MultiPolygon` or an empty geometry *is* the event; the
    levels form a monotone forest (erosion never invents a hole nor merges
    components). Every ring is eroded from the ORIGINAL at `k*spacing`, never
    iteratively, or corners re-round each pass. `medial_tail` draws a
    centreline down limbs too narrow for another whole ring, suppressed when
    it would double an existing one. **Still open**: a continuous *spiral*.
    One unbroken stroke only exists for a hole-free component that never
    splits before it dies (a topological disk that stays a disk); anywhere
    else the pen must lift, which is the `connect_strokes` problem again —
    build it on top of the rings, not instead of them.
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
   layers, library name kept). Later: scrap editing.
0a. ~~Draw mode (main canvas)~~ — **shipped July 2026**
   (`docs/plans/draw-mode.md` / `-RESULTS.md`): pointer strokes on the main
   canvas are a first-class `sources/drawing.py` generator layer, not a
   second geometry path — `strokes: [[x_mm, y_mm, t_s], …]` (hidden param,
   timestamps captured now for a future velocity-tube render mode),
   resampled at fixed arc-length + 3-point-smoothed. `static/js/draw.js`
   captures via capture-phase listeners on `#canvas-wrap` (canvas.js's own
   drag/marquee code never sees the events) and reuses `CanvasEditor.toBed`
   for the pointer→mm conversion, so portrait/landscape both place strokes
   correctly for free. Per-stroke undo (no coalesce); brush presets
   (plain/sketchy/tube/wobble) swap the layer's effect stack. Workbench's
   own ✏ Draw (raw/smooth/steps/zigzag/stitch shaping, scrap-only) is
   unchanged and still the separate playground path.
0b. **Pen tool (⚓ béziers)** — planned 2026-07-19, briefed 2026-07-19
   (`docs/plans/pen-brush-tools.md`, combined with 0c). Photoshop grammar:
   click = corner anchor, click-drag = smooth anchor with symmetric arms,
   rubber-band previews the next segment, Option-drag breaks arm symmetry,
   click-first-anchor closes (→ `filled=True` = instant occluder / region
   input; visible ink fill = `hatch_fill` on the stack), Enter commits
   open, Esc cancels, Backspace deletes last anchor. Storage: a `pen`
   source with anchors + handle vectors + `closed` per subpath;
   `generate()` flattens cubics at a bounded `flatten_tol` (~0.2 mm) — the
   grammar generator's exact precedent, `model.py` untouched. Post-commit:
   pen mode + selected pen layer shows an anchors/handles overlay; drags
   regenerate with `coalesce=true` (one undo entry per editing run).
   Toolbar becomes a mode segment: ↖ select · ✎ draw · ⚓ pen · ● brush;
   every tool = geometry-as-params source + canvas-mode JS module (the
   draw-mode pattern).
0c. **Brush tool (● circle brush)** — planned 2026-07-19, briefed 2026-07-19
   (`docs/plans/pen-brush-tools.md`, combined with 0b). A `brush`
   source: strokes + brush radius (`[`/`]` resize, circle cursor);
   commit = shapely buffer + union → closed `filled=True` boundary
   polygons (exterior AND interior/hole rings each emitted as their own
   closed `filled=True` path — nesting alone marks a hole, no flag needed).
   Eraser = boolean difference. Correction 2026-07-19: the hole question
   needs no compromise — `compose.build_mask`'s even-odd depth-parity pass
   (shipped 2026-07-10, `test_filled_occlusion_mask_respects_nested_holes`)
   already reassembles nested holes for OCCLUSION too, not just
   `hatch_fill`; a donut brush stroke masks correctly as a ring, hole
   included, with zero extra work. The stale "occlusion mask over-covers a
   donut's hole" limitation this item originally cited (from the
   Documentation-debts IPR-hole note, itself corrected below) no longer
   applies to anything — don't reintroduce the caveat.
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
4. ~~Glyph grammar source~~ — **shipped 2026-07-10** as
   `sources/glyphgram.py`: vpype Hershey fonts (futural → gothiceng, greek,
   japanese, astrology, music…) through fragment/drop/displace/recombine/
   mirror-echo rules, one `abstraction` master dial (0 = almost reads,
   1 = pure scaffold); empty text = asemic glyph soup.
5. **Perception pass — line weight = certainty** — briefed 2026-07-19
   (`docs/plans/perception-pass.md`; the ideas doc calls this
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

## Near term — AARON pass (July 2026, pass 3)

From `docs/IDEAS-aaron-pass.md` (grounded in Cohen's AAAI-1988 paper — the
mechanisms are quoted there). Pull order:

1. **Core-figure generator** — skeleton (plant morphology variables /
   armature with a balance constraint) → embodied closed outline walked
   around it with carefulness varying along the body (freehand controller
   as the hand) → several placed foreground-first under AARON's
   never-overlap rule via the existing masks. The missing thing-ness that
   two_hands lacks. Briefed 2026-07-19 (`docs/plans/aaron-core-figure.md`) —
   settles plant-morphology-not-figure-armature and the embodiment/
   never-overlap mechanics as concrete, self-contained (no session/compose
   change) design calls.
2. **Sheet-snapshot asset** — one endpoint/button rasterizing the current
   resolved output into an asset; every image-driven generator becomes
   context-aware (negative-space filler, two_hands v2 perceiving the sheet,
   respond/annotate generators). Zero architecture change.
3. **Felt-tip color kit** (with 4 — they share multi-layer-per-pen
   plumbing): overprint zones with pairwise intersections drawn in both
   pens; value-rule pen assignment with free hue (Cohen's color logic);
   duotone density mixing; repetition-as-pressure.
   *Implementation note (2026-07-19)*: overprint needs cross-layer geometry,
   which the effect protocol deliberately cannot see (effects are pure
   single-layer functions — keep it that way). Build it as a **session-level
   composer operation** — the `add_lineart_stack` pattern: compute the
   pairwise shapely intersections once at creation time and emit baked
   layers per pen. Do NOT bolt cross-layer reads onto effects, and don't
   reach for region layers either (regions shape what's below, they don't
   emit intersection geometry as new plottable layers).
4. ~~**linedraw v2**~~ — **shipped 2026-07-13**: staged pipeline (edge
   extraction / stroke tracing / flow-aligned streamline hatching),
   multi-layer output by tonal band, each band its own texture + pen.
   Family: `sources/lineart_edges.py` (XDoG/Sobel + trace + hand) +
   `sources/lineart_hatch.py` (flow-field streamlines + hand), engine in
   `sources/_lineart.py`; one-click `session.add_lineart_stack` (faithful
   4-layer / artistic 3-layer presets) + `POST /api/layers/lineart_stack`.
   Detail round (same day, from first real prints): edge maps are Zhang–Suen
   skeletonized before tracing (branches survive), `resolution` ×1..2
   working-canvas multiplier, `mass` (luminance-threshold solid ink) +
   `ink_fill` (flow-following fill of ink mass) let a maxed edges layer
   hold as a complete drawing; clip-backed generator layers now default
   `frame_follow=True` (a video layer plays under the timeline on creation).

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
  z-order (needs a positional merge) — since 2026-07-19 they only appear
  from the midpoint step on (one-sided layers step at t=0.5 in both
  directions; the B-only case used to crash below the midpoint). Batch
  steps are hard-linear — accept the tween `time_curve` enum. The larger
  2026-07-19 change: both interpolation instruments now share ONE per-layer
  blend core in `tween.py` (`blend_effect_stacks`/`blend_generator_params`/
  `lerp_paths`/`structures_match`), full-stack rule + tween-params-lerp
  landed, behavior pinned in `tests/test_interp_pinning.py` — extend the
  core, never re-fork it.
- **Plot-cursor persistence**: the stepper's page/pass lives in browser JS
  and dies on reload; persist alongside staging (non-undoable) so a
  multi-hour flipbook survives a restart.
- **Staging browser ergonomics**: batches make the tray list long — a grid
  browser with thumbnails (scrap-strip pattern from the workbench).
- ~~A/B capture series ergonomics~~ — **shipped 2026-07-10**: A · B · ⇄
  buttons in the canvas toolbar — capture the whole current output as A,
  change anything, capture B, generate an n-step interpolated staged series
  (wraps staging capture+interpolate; re-pressing a letter replaces that
  capture). The layer-by-layer tween dance is no longer the only path.
- ~~Pi round 2~~ — **shipped 2026-07-11** (`docs/plans/pi-round2-RESULTS.md`):
  bitmap redesign (default `style="lines"` quantizes paths to hard-cornered
  grids, identity preserved; the old merged treatment is `style="blocks"`),
  `contract_expand` signed-offset effect, region boundary continuity
  (`region_boundary: cut|continuous` — continuous stitches each path below
  back into one path through the seam), and workbench mouse drawing
  (✏ pointer strokes with raw/smooth/steps/zigzag/stitch modes, riding the
  scrap save/import machinery via `WorkbenchBody.paths`).

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
  Capturing a grid sheet and then "insert as layers" is the editable-layer
  escape hatch (the standalone `bake_contact_sheet` endpoint was removed
  2026-07-12 — capture + insert covers it and stays undoable in one step).
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

- ~~Tween interpolation modes: linear, cosine ease, cosine ping-pong~~ —
  **shipped July 2026** as `TweenParams.time_curve = "linear" | "cosine" |
  "cosine_pingpong"` in the Timeline panel. `cosine` is the ordinary smooth
  A→B ease (`0.5 - 0.5*cos(pi*t)`, added 2026-07-21 as its own mode, not
  overloading ping-pong); `cosine_pingpong` maps morph time A→B→A over 0..1.
  The raw master timeline still drives clip/frame-follow playback linearly.
- ~~Captured-geometry shape morph (pen/drawing tweens)~~ — **shipped
  2026-07-21**: a hidden geometry param (`pen.subpaths`, `drawing.strokes`)
  deep-lerps anchor-by-anchor when A and B share structure, so an animated
  pen shape eases between forms instead of jump-cutting at t=0.5. Mismatched
  point/anchor counts still step; arc-length resampling to morph
  differently-structured A/B is the remaining open piece (see MODULES.md
  "Geometry-as-params sources").
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
  The editable escape hatch is capture-a-sheet + "insert as layers", which
  bakes one layer per pen pass (the standalone `bake_contact_sheet`, which
  flattened one layer per frame, was removed 2026-07-12).
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

## Far / undecided — UI revamp (frontend tooling ceiling)

**Brainstorm pass: `docs/IDEAS-ui-revamp.md` (2026-07-26)** — what "serious
UI" concretely means here, ranked by operator value with a tooling tier
marked per item. Its two load-bearing findings: most of the wanted work is
Tier 0 (no invariant change), and *generating* types offline from the
server's own OpenAPI schema and checking them in is a tier this section's
three-way framing doesn't name — it captures most of the TypeScript case
without a build step. The criterion below is unchanged by it.

Opened 2026-07-25, from a discussion prompted by the pen-tool icon (an
emoji glyph, `⚓`, standing in for a real icon). The zero-build invariant
(ARCHITECTURE.md "Stack") was checked against what it actually costs, since
it hadn't been revisited since the fabric/konva rejection: are we still
paying only for what we meant to pay for, or has "no build step" quietly
turned into "no tooling of any kind" and started taxing things it was never
meant to block?

**What's already in-bounds without touching the invariant** (the zero-build
rule bars a compiler/bundler from the edit-reload loop; it was never "no
tooling at all" — see CLAUDE.md, ARCHITECTURE.md "Stack"):
- ~~Vendored inline SVG icons~~ — **shipped 2026-07-25**: the canvas
  toolbar's select/draw/pen buttons now use hand-authored inline SVG
  (`currentColor`-themed, so the `.on` accent-invert state is free) instead
  of Unicode/emoji glyphs (`↖ ✎ ⚓`). The pen icon deliberately echoes the
  pen tool's own on-canvas anchor language (`.pen-anchor` squares) rather
  than a generic library glyph. Legibility note for whoever touches this
  next: thin multi-stroke detail (a bezier curve + two small squares) reads
  as a blur at the ~16px toolbar size that actually ships — verified by
  rendering variants in isolation before committing; bold, high-contrast
  silhouettes (thick strokes, filled shapes) are what survives the scale-
  down, not literal small-scale fidelity to a bigger design.
- **Revised 2026-07-26**: the hand-authored tool icons were replaced with
  **Lucide** (ISC, `THIRD-PARTY-NOTICES.md`) after Ian called the hand-drawn
  pen and draw glyphs ugly — `mouse-pointer-2` / `pencil` / `pen-tool` /
  `check`, path data inlined verbatim, with stroke width and joins moved out
  of the markup into `.tool-icon` so the set has one place to stay
  consistent (2.2, not Lucide's stock 2: a 24px grid scaled to 16px thins
  strokes below toolbar legibility). The legibility lesson below still
  holds — it is *why* a designed set beats hand-drawing at this size.
- Still open, same tier (vendor-a-file, no npm/bundler): a matching pass
  over the toolbar's remaining emoji glyphs (`⛶` zoom-fit, `▶` animate,
  `⇄` series, plus any in the layer list / panels) — now with an obvious
  answer (the matching Lucide icon), and now visibly inconsistent next to
  the real icons. Still do it as one pass, not piecemeal.
- `// @ts-check` + JSDoc across `static/js/*.js` — real type-checking (catches
  the "passed a layer where an id was expected" class of bug) as an
  editor/CI lint pass, zero compiled output, zero runtime cost.
- A single vendored ESM component library (htm+preact is the known pattern
  for this — templated/reactive components via plain `<script
  type="module">` imports, no npm, no bundler) for the parts of the UI that
  are pure DOM-wrangling duplication: the growing set of panel/tab bodies
  (Compose/Draw/Pen/Bench/Timeline/Plot), the near-term list below.

**What a real bundler/compiler (Vite + TypeScript + a compiled framework)
would add on top, that the vendored tier can't:** compiled reactivity
(fine-grained DOM updates without hand-written diffing), full TS across
module boundaries (not just per-file JSDoc), CSS tooling (Tailwind/
PostCSS), code-splitting/minification. Note how much of the classic "why
npm" list does NOT apply here: geometry and authority are deliberately
server-side (single-resolve invariant) — the frontend is thin (forms, one
canvas, SSE) — so there's no large client-side data layer that needs a real
framework's diffing to stay fast.

**Costs of lifting it**, unchanged from the original call: the Node
toolchain question for the idkpi clone (checked 2026-07-25 — Pi-scheduled
agents currently work through `pytest`/PIL renders, never a browser, so
this is real but narrower than it sounds: it'd only bite the day a
Pi-scheduled agent needs to touch and verify frontend code); view-source
debuggability; and the standing philosophy that rejected fabric/konva
specifically for being "heavy and build-chain-y" for a single-operator
instrument — a real toolchain reopens dependency/lockfile/version-drift
overhead that the Python side has stayed almost entirely free of.

**Previously-costed-out things this bears on**, so they're not silently
re-litigated piecemeal later:
- The near-term UI comfort list (collapsible panels, drag-to-reorder
  layers, keyboard nudge) is exactly the kind of hand-rolled DOM code a
  component layer would shrink — try the vendored htm+preact tier there
  first if the hand-written version starts feeling like the bottleneck.
- The node question above already flags "zero-build vanilla JS node editors
  are non-trivial" as one of nodes' costs — if nodes are ever pursued, this
  question and that one interact directly (a node editor is the strongest
  concrete case for a real component framework, not just DOM cleanup).
- A dope-sheet/keyframe editor (mentioned under Animation's deferred list)
  is a similarly graph/state-heavy UI that would lean on the same tooling
  question.

**Criterion for reopening the "real bundler" question**: not "would it be
nicer" — it always would. Reopen only when a *specific* wanted feature
(the node editor, a dope-sheet, real drag-and-drop panel layout) genuinely
needs compiled reactivity or cross-file TS, and the vendored-ESM tier has
been tried and demonstrably isn't enough for it. Until then this stays
here, not acted on.

## Documentation / robustness debts

- ~~`main.js mapGhosts()` special-cases module ids for show-map ghosts~~ —
  done June 2026: any generator layer with `image` + `show_map` params
  ghosts in the layer frame; only the depth-displace *effect* (paper-space
  placement) remains special-cased, correctly.
- The IPR has no hole representation; holes are separate filled loops,
  nesting-derived (a closed `filled=True` loop inside another is a hole by
  depth parity, no explicit flag). **Corrected 2026-07-19** (was stale since
  2026-07-10): both `hatch_fill` AND occlusion (`compose.build_mask`)
  reassemble this even-odd — a donut occludes correctly as a ring, not a
  solid island (`test_filled_occlusion_mask_respects_nested_holes`). The
  remaining real gap is only the IPR itself carrying no hole *representation*
  (a hole is inferred from nesting + nearest-covering nesting only handles
  one level of "hole in a solid" cleanly) — if a design ever needs holes as
  a first-class field, or nesting deeper than solid→hole→solid, that is an
  IPR change; today's depth-parity pass is not that.
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
