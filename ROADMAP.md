# Roadmap

Loose, ordered by conviction. Each item says *why*, so a future session (or
a smaller model) can judge whether the reasoning still holds before acting.
Rules of engagement for any of it: the resolve invariant and the module
contracts (ARCHITECTURE.md, docs/MODULES.md) are not negotiable; the frontend
source stays plain ES modules in `axibridge/static/` served buildless on a
machine with no npm, with Vite/TypeScript as an additive layer on top (the
zero-build *invariant* was retired 2026-08-07 — see "Far / undecided — UI
revamp", RESOLVED, for what was adopted and what it cost; the source-fallback
rule in CLAUDE.md is what still carries the Pi). Every numeric param stays bounded.
Loose generator brainstorms (uncanny/Cohen-line direction, plus how the
involved ones should meet the UI) live in `docs/IDEAS-generators.md`.

## ~~URGENT (Ian, 2026-08-07) — orientation coherence is opt-in~~ — DONE, option B

**Shipped 2026-08-07** (Slice 1c of `docs/plans/ui-redesign.md`). The symptom
was `text` rendering its baseline *vertical* in portrait — same for
`glyphgram`, and latent in anything else with a dominant axis. The 2026-07-13
pass had built the right mechanism (params stay machine-frame; the display
layer remaps once via `viewRotate`/`viewAngle`/`viewOrient` tags in
`static/js/viewmap.js`) but participation was **opt-in**, and a module with
no rotation param had nothing to tag.

**Option B, as decided:** orientation is now a **mandatory declaration on the
source module** — `SourceModule.orientation` is one of `"none"` (no dominant
axis), `"param"` (a tagged rotation param already handles it), `"geometry"`
(the layer transform must). For `"geometry"` sources in portrait,
`Session._placement_transform` bakes the display map's inverse —
`(x, y) -> (y, H - x)`, a 270-degree turn plus the bed height — into the new
layer's affine, once, at creation, so the layer lands **where it would have
landed in landscape, on screen**. All 27 sources are classified: 14 `param`
(the image family), 5 `geometry` (`text`, `glyphgram`, `grid`, `rectangle`,
`flowfield`), 8 `none` (radial figures and the captured-input tools).

The part that ends the recurrence is `tests/test_orientation.py`: it **fails
on any source that declares nothing**, and separately checks that every
module claiming `"param"` actually carries a view tag — so the promise can't
be empty. Resolve stays view-independent (the correction is stored geometry,
not a resolve-time read), which `tests/test_view_coherence.py` still locks.

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
  off across every stochastic module. (Layer creation already rolls a fresh
  seed into the form; this would put the affordance on every form.)
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
    it would double an existing one. `round_center` (Ian's ask, same day)
    relaxes each ring's corners in proportion to its depth — a morphological
    opening, so flat runs stay put and ring spacing is untouched — making the
    family morph from the shape toward circles as it marches in; the radius
    backs off by halves rather than ever costing a ring. It rounds CONVEX
    corners only, so concave structure survives all the way down (a star's
    centre becomes a flower, not a disc — the honest result, not a shortfall).
    ~~**Still open**: a continuous *spiral*.~~ — **shipped 2026-08-09** as
    `effects/offset_fill_v2.py`, a SIBLING of `offset_fill` (v1 untouched and
    still stacked separately; `spiral=False` reproduces it path for path).
    Built on top of the rings exactly as this entry asked: a level *forest*
    links each component to what it erodes into, and a spiral runs down every
    maximal hole-free single-child chain, rings taking over wherever one
    splits or carries a hole. A dying limb's medial tail becomes the spiral's
    last turn instead of a pen lift. A 120mm square at 1mm spacing goes from
    61 strokes to 1. The subtlety worth carrying forward: laps hold their
    spacing by drifting in LOCKSTEP, and the innermost lap has nothing to
    drift toward, so a full-drift blend slides the lap above onto it —
    `blend` caps the drift and buys `(1 − blend) × spacing` of separation.
    Two other cavalier-contours ideas landed with it: **tolerance** (mm)
    replaced the scale-blind `smooth` segment count, and an **arc-native
    offset engine** (`effects/_arcpoly.py`, bulge polylines) sits behind
    `engine="arc"`, OFF by default. It decouples output vertex density from
    input density — a 1440-gon import fills at the same accuracy for a
    twentieth of the vertices — but a wrong prune is permanent wrong ink, so
    flipping the default wants a much wider differential corpus
    (`tests/test_arcpoly.py`) and a hardware check first. It is contained
    evidence for the IPR-arc question below, not an answer to it.
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
  **Related, but deliberately not the same item:** `fast_marching_topo`
  shipped 2026-08-10 as an image-driven source adapted from Roland Blok's
  FastMarchingTopoPlot. It solves a seeded Eikonal travel-time field where
  bright pixels propagate quickly and dark pixels slowly, then traces evenly
  spaced iso-times — so tone changes contour *spacing* around one expanding
  wavefront. The direct N-brightness-threshold version above remains open:
  it would follow image luminance itself and has no seed or propagation model.
  Fast marching uses the shared 800px canvas, 0.25×..2× resolution, mm blur,
  shared tone controls, frame assets and alpha clipping; default-size measured
  1.3s on Mac. Engine/source split: `sources/_fast_marching.py` and
  `sources/fast_marching_topo.py`; upstream is Unlicensed and credited there.
  **Its sibling `fast_marching_contours` shipped 2026-08-11** (`4c99f2b`) on
  the same engine and is a different picture again: it seeds a whole image
  EDGE at once, so the front starts as a straight line and *bends* as it
  crosses the image — successive contours are parallel-ish sweeps across the
  sheet rather than concentric rings, dense where the image is dark. The
  original part is the boundary-threading stage (`sources/_fm_threading.py`):
  where geometry permits, one continuous line threads level after level along
  the frame edge instead of lifting the pen every contour — 200 loose contours
  become a handful of serpentine pen-down trails. Multi-seed solving and
  per-level contour grouping are new in `_fast_marching.py` for it. The speed
  mapping matches padcrafting/ContourTool's documented approach (algorithm
  reference only, no code taken); ContourTool seeds a point and has no
  threading. 24 tests. Ian on the result: **"this is golden"** — taste-
  verified, not merely numerically.
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
- ~~Hershey/single-stroke text generator~~ — **shipped 2026-07-31**: `text`
  source with the 10 bundled CamBam stick fonts (fontTools outlines,
  reversed-stroke dedupe) plus vpype's whole Hershey set, multiline
  (textarea control, `\n` lines), tracking/line-spacing.
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

## Shipped 2026-07-31 (mixed batch)

- **Seeds**: layer-create rolls a random seed into the form (no more
  universal 0). Tween seeds no longer snap at 0.5: differing or zeroed
  endpoint seeds get a deterministic per-frame hash
  (`sha256(a:b:t) mod 10000`, scrub/plot-stable, endpoint fidelity kept);
  equal nonzero seeds stay constant. Still open: a dice button on every
  form (item above).
- **Grid sheets**: new 8-preset (4×2); 2×1 and 4×2 grids rotate the scene
  90° inside each cell (keyed on grid SHAPE, so hand-entered grids flip
  too) — portrait cells stop letterboxing landscape scenes.
- **Canvas tools**: "＋ empty layer" button (a `shape` layer for pen/brush,
  a drawing layer for draw) — an explicit fresh target instead of the
  tools' sticky last-layer append. Pen tool has add/subtract (E toggles,
  rust preview). New unified **`shape` source**: chronological
  add/subtract ops (brush strokes + pen silhouettes, implicitly closed)
  folded through shapely; plain pen/brush layers AUTO-CONVERT in place
  when a gesture needs region semantics (erase into a pen shape, pen-cut
  into a blob) — one undo step for convert+commit. Brush preview is fully
  opaque now.
- **Interrupted plot**: plot-tab panel bakes a contiguous pen-down slice
  of the whole resolved project (machine order after plot-pass opts,
  mid-stroke cuts, seed-rolled or manual start/stop) into one baked
  layer — recreates the plot that got stopped early.
- **fat_tube `solid`**: unions all tubes into one silhouette — crossing
  strokes leave no seam rings.
- **Invert effect**: page negative — the layer's ink (fills by even-odd
  parity, strokes as a configurable-width band) subtracted from the
  paper-guide rect; `margin` crops the boundary inward. `EffectContext`
  gained `page` (guide, else bed) — threaded through resolve + tween.
- **Occlusion groups**: checkbox group sets (A–D) on both sides —
  occluders pick which groups they mask (none = everything, the classic
  behaviour), receivers pick which they hear (none = global only).
  Additive semantics; single-letter projects migrate on load.
- **Native backend hardening** (from an evil-mad/axidraw review): PSU
  voltage warning on connect (barrel-jack missing — warn, never block);
  pause button ends a job gracefully and keeps the link, USB loss drops
  the zombie connection; `block()` + a Wait-idle button by the raw
  console; `resolution` (already defaulted to high — rough curves are
  geometry flattening, NOT microstepping), `penlift`, `servo_timeout_s`
  params; AxiDraw `model` picker syncs the soft envelope when it still
  matches a stock size; 0.1 mm envelope tolerance.

## Near term — Oehlen pass: regime collision (July 2026)

From the second idea pass (`docs/IDEAS-oehlen-pass.md` — read it first, the
*why* lives there). Ordered by dependency, not just conviction:

0. ~~Generation workbench popup~~ — shipped July 2026, **removed July 2026**:
   the stateless recipe playground + global scrap library (`scraps.py`,
   `/api/workbench/*`, `/api/scraps*`) never earned its keep once layer
   creation got seed-rolling and the canvas tools grew up. Scrap files on
   disk (`~/.axibridge/scraps/`) are left in place.
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
   (plain/sketchy/tube/wobble) swap the layer's effect stack.
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
0c. ~~**Brush tool (● circle brush)**~~ — **shipped 2026-07-27** as
   `sources/brush.py` + `static/js/brush.js` + a 4th toolbar segment button.
   Paint/erase circle brush; the swept area folds into closed `filled=True`
   rings (holes by nesting, no flag). The correctness rule is the
   **sequential fold** — erases apply per stroke in order, never
   union-all-then-subtract-all, or a repaint over an erased spot is swallowed
   (`test_repaint_over_an_erase_survives` is the only test of 17 that catches
   it). Per-point timestamps captured and unused, drawing.py's bet before
   velocity_tube: a **tapered brush** (radius from drawing speed) is the
   queued follow-up and lands as a pure addition. Original brief below, kept
   because its reasoning still holds:
0c-orig. **Brush tool (● circle brush)** — planned 2026-07-19, briefed 2026-07-19
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
0d. **Liquify (soft-brush warp effect)** — raised 2026-07-27 as a
   hypothetical, thinking written down in `docs/plans/liquify-effect.md`
   (loose plan, NOT a commitment — read it before starting, the reasoning is
   the value). Push/twirl/pinch under a soft circular brush, in paper-space
   mm. Three things it settles: it would be the **first captured-input
   *Effect*** (draw/pen/brush are all Sources — the only unfamiliar plumbing
   is PATCHing a step's params rather than POSTing `regenerate`); "depth as
   parameter" reads as a global `amount` 0..1 that must be *exactly* identity
   at 0, which makes timeline animation free; and **interpolating two
   liquifications is easier than the geometry morph already shipped**,
   because a warp is a field, not a structure, so it blends unconditionally.
   The trap there: `blend_effect_stacks` doesn't deep-lerp hidden geometry
   fields (only `blend_generator_params` does), and the tempting fix — A/B
   inside the effect — re-forks interpolation, which the 2026-07-19
   unification exists to prevent. Extend the core instead. Reuse
   `coherent_jitter._resample` (densify before warping, or straight segments
   stay straight) and `depth_displace`'s `anchor: layer|paper`.
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
  **Superseded 2026-08-11** (`7f2e2e8`, timeline-v2 §2c): `framing` became
  **`crop = timeline | full`**. `timeline` is the old `fixed` (one bbox
  unioned across all frames, so relative motion is preserved) and is the
  default; `full` keeps the untouched page rect and its negative space. The
  per-frame `center` mode is **deleted**, not renamed — Ian's ruling, because
  "cancels a pure translation" is a bug wearing a feature's clothes and it was
  the thing freezing motion out of every bake. Legacy formats still load
  (`_crop_from_format` reads either key; `center` maps to `timeline`), they
  just no longer drive new bakes. Grid orientation generalised with it, from a
  hardcoded shape lookup to whichever of upright/rotated achieves the larger
  scale.
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
  ~~presets (1/2/4/16)~~ + margin + ~~framing~~ crop + crosshairs feed the
  preview, stepper, ~~"Capture to tray"~~ **"Bake sheet"** AND the export
  link; the separate contact-sheet block is gone; a summary line says what
  the layout means physically (and, since 2026-08-11, what this sheet and the
  whole run cost in plot time).
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
  multi-hour flipbook survives a restart. *Still open, but much cheaper to
  survive since 2026-08-11*: `start here` inputs on the sheet and frame
  steppers make recovery one typed number instead of eighteen `Skip pass →`
  presses, and Reset now returns to that chosen start (a separate `⤒ 1` goes
  to the true beginning).
- **Staging browser ergonomics**: batches make the tray list long — a grid
  browser with thumbnails. *Partly eased 2026-08-11*: group headers carry the
  richer layout label and click to select, animation-born sheet groups are
  visually distinct (ochre edge), and passes plotted this session strike
  through (client-side only, no persistence). Thumbnails are still the ask.
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
  (✏ pointer strokes with raw/smooth/steps/zigzag/stitch modes — the
  workbench itself was removed July 2026, see item 0 above).

## Animation — **SHIPPED July 2026** (v1: linear A→B over a master timeline)

**v2 (chains, the bottom bar, the staging/plot rework) is its own section
below** — this one is kept as the v1 record, with its deferred list annotated
where v2 answered an item.

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
  physical sheet (~~1/2/4/16 per page~~ — rows × cols only since 2026-08-11;
  the presets left the UI because the two boxes already covered them) without
  the destructive bake.
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
  interpolated batches. **Partly advanced 2026-08-11**: interpolating two
  *sheet* captures now yields ONE group holding A's and B's own snapshot
  states as endpoints with the blends between them (`e1dee75`), which is
  Ian's 2D frame-matrix reading — the same frames run along one axis, the
  parameters blend along the other. Same code path serves relayout, so
  re-gridding keeps the grouping. The open question is a richer 2D authoring surface
  where timeline `u` is frame/clip time and variant `v` is a second parameter
  dimension with better browsing, naming, and traversal controls. Do not add
  a second global master timeline casually; keep any automation as temporary
  sampling over the existing resolver (`session.resolved(master_t=u)` /
  `sheet_document`) and preserve pen grouping, preview/export/estimate
  agreement, and undo sanity.
- ~~**Easing curves beyond ping-pong / >2 keyframes** — a dope-sheet or
  keyframe list would deepen animation further. The data model question
  (keyframe lists vs. layer pairs vs. named channels) is the real cost, so
  keep it behind the smaller interpolation-mode experiment.~~ — **answered
  2026-08-11** by keyframe chains (see "Animation v2" below): the data model
  is a **keyframe list**, `TweenParams.keys`, on the existing tween layer —
  not layer pairs, not named channels. Easing is per segment. What is *not*
  answered is the third option in that sentence, first-class **grouping** in
  the layer list (timeline-v2's Q1(c)): a chain is still N sibling layers plus
  one tween, and a real parent/child node in `compose.py` + the dock + the
  save format remains a round on its own. `keys` does not foreclose it — a
  grouping UI would present the same list.
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
  frame cache. ~~A server-side GIF/video export would be convenience only.~~ —
  that convenience shipped 2026-08-11 (`29a4dfd`): `animation/export.gif`
  (PIL, always available) and `export.mp4` (system ffmpeg, clean 501 and a
  disabled button with a reason when absent), off ONE shared frame renderer
  that also feeds `preview.png`. ffmpeg is now a declared, launch-installed
  dependency — see "Animation v2" for the PATH bug that made it look missing.
- Per-frame fades via pen pressure / multipass density (motion trails).
  ~~Registration marks for multi-sheet alignment~~ — shipped 2026-07-10 for
  grid sheets (crosshairs on the sheet spec); still open for plain
  multi-pass single-frame plots if ever wanted.
- Colour separation (above) intersects: per-frame AND per-pen matrices.

## Animation v2 — **SHIPPED 2026-08-11** (chains, the bar, the staging/plot rework)

One ~15-commit round, `4cebea7` → `e1dee75`, suite 843 → **947**. The design
doc `docs/plans/timeline-v2.md` is the contract (findings F1-F9, Ian's rulings
Q1-Q7 + §2b/§2c + the plot-flow ruling) and carries its own closing ledger in
§6 — read that for the reasoning behind any line here. **None of this has had
Ian's eyes or a real AxiDraw on it yet** (`CHECKME.md`, 2026-08-11).

- **Enabling round first — animation performance** (`9649d8d`, `fb959d5`,
  `966debf`, 2026-08-10→11), because half of what follows was unaffordable in
  July. A sentinel project scrubbing at >10 s/frame had four causes and got
  four fixes: a `stats=false` opt-out on `GET /api/compose/resolved` (the
  slider passes `plan:false, stats:false` while dragging and does a full
  refresh on release; the stray per-tick `/api/plan` is gone);
  `axibridge/gencache.py`, a content-keyed memo on `generate()` itself, keyed
  on generator id + canonicalised params + asset version; every per-layer
  cache (tween, clip-follow, shaped, occlusion) taken from ONE slot to a
  budget-bounded multi-entry map, each entry pinning the `id()`-keyed objects
  its key names; and an optional `skfmm` Eikonal solver behind the `[fast]`
  extra, with the pure-Python solver staying the tested reference and what the
  Pi runs. **Eviction is random, not LRU**, for the caches playback cycles
  through — at capacity LRU evicts precisely the frame about to be reused
  (`gencache.py`'s docstring has the argument). Cold frame >10 s → ~2.5 s, a
  revisited frame sub-millisecond. `tests/test_scrub_caches.py`,
  ARCHITECTURE.md "Many frames, not one".
- **Keyframe chains** (`46ecbfe`, `b071eb6`, `14006a1`). A>B>C>D is **one
  tween layer** carrying `TweenParams.keys` (≤ 24; empty ⇒ the classic A/B
  pair, and a chain shrinking back to two normalises to empty so an older
  build still reads the project). A global `u` reduces to `(segment, local t)`
  with isometric spacing — derived, never stored, so inserting or deleting a
  key re-spaces the whole chain with no windows to maintain. Easing is **per
  segment** (Ian's ruling, against the doc's recommendation: motion settles at
  every checkpoint, pose-to-pose), with globally-meaningful curves
  (`cosine_pingpong`) held global via a named frozenset. Occlusion, effects,
  pen and transform are the *layer's* — they were always the layer's — so
  nothing is per-segment except the pair being blended, and `sweep`
  generalises for free into a ladder across the whole motion. Endpoint snap at
  `k/(N-1)` is load-bearing beyond fidelity: `lerp_params` gates seed
  reproduction on an exact 0/1, so float error would have rolled per-frame
  seeds silently. UI is a numbered keyframe list with drag-reorder and
  right-click **Copy/Paste state** (whole checkpoint; per-parameter is
  deferred, below). Why not sugar over N windowed tweens: outside its window a
  tween *holds its endpoint and keeps drawing*, so N−1 segments would put N−1
  copies on the sheet, and making visibility a function of `master_t` breaks
  the scrubbing-never-mutates invariant. The probe that settled it is the
  doc's Appendix A.
- **The bottom timeline bar** (`086c365`, `5529abd`) — new
  `static/js/timeline.js`, mounted between the canvas and the status line,
  visible only when something actually follows the master timeline and zero
  height otherwise. Scrub (moved verbatim from `compose.js`, its no-PATCH
  discipline intact), jump-to-ends, frame steppers, one jump button per chain
  checkpoint, and a Render-popup button; play stayed in the Animation panel.
  The slider **snaps to the frame grid** (⇧ escapes to continuous, arrows step
  frames, phase-locked outside `[t from, t to]`), which is the payoff of the
  perf round: a continuous slider produced a fresh float per pixel of travel
  and so missed every cache, while playback of the same animation was nearly
  free — snapping makes scrubbing and playback share keys. Ticks mark grid
  frames and brighten once fetched this session; the code says out loud that a
  tick is a hint, not a guarantee, because the server evicts under a point
  budget.
- **Render popup** (`29a4dfd`, `b995752`): palindrome, 1-4× zoomable renders
  with true-to-zoom pan, GIF/MP4 export off one shared frame renderer, and
  every completed frame painting immediately instead of freezing on frame 0.
  It is top-level markup now, so it opens over any tab. **The ffmpeg finding
  is the durable one**: a Finder-launched app bundle never inherits the
  shell's brew PATH, so `_find_ffmpeg()` checks the well-known install
  locations directly and returns the resolved path used by both `/api/state`
  and the export — Ian *had* ffmpeg and the app said he did not. The launch
  script installs it only when genuinely absent; no embedded binary.
- **Staging: the live project does the work trays were being asked to do**
  (`30e7043`). Trays stay **frozen** by ruling. What changed instead: an
  always-visible view label naming what the canvas shows (live · sheet n/N vs
  a tray's own mark) written by the only two writers of that state, so it
  cannot lie; a **sticky live sheet view** — editing a param re-renders the
  sheet in place instead of dropping to a single frame (affordable only
  because of the caches); ↻ **re-bake from live** on any frozen tray, one
  checkpointed act re-running the group's own format under the same group id
  so undo restores the old bake byte-for-byte; and click-to-select tray
  headers. A stored auto-refreshing tray and "project starts in a tray" are
  **parked, not planned**.
- **Sheets: crop replaces framing** (`7f2e2e8`) — see the struck entry under
  "Sheets workflow v2" above for the full story. `crop = timeline | full`,
  the per-frame `center` mode deleted, motion survives baking, rows × cols
  only, "Capture to tray" renamed **"Bake sheet"** because it always was the
  bake.
- **▶ Plot obeys the view label** (`f030acd`) — **a semantic change**. Routing
  reads the same state the label prints, so what you see is what plots: the
  live view is unchanged (one `target=all` job, asserted), sheet and tray
  views fire their own passes, and zero passes refuses out loud rather than
  falling back to the live project. Multi-pen sheets run as a **guided pass
  queue**: one press starts pass 1, the status line reports "pass k/N —
  <pen>", and the machine holds between passes with "swap to <pen>, then ▶
  continue". Stop stays live during a hold so a half-run can be abandoned;
  the tray's per-pass buttons remain the out-of-order escape hatch; the
  all/layer/pen target picker greys out on sheet/tray views ("sheet passes
  carry their pens"). Seven acceptance tests assert the actual
  `/api/plot/start` bodies. **Not hardware-verified** — simulator and headless
  only, and the pen-swap hold is exactly what a real machine has to judge.
- **Tray A⇄B fence** (`e1dee75`): interpolation refuses keyframe chains **by
  name** and keeps working for video pairs (Ian's narrow reading — the strict
  one would have deleted working behaviour). Nothing was deleted to build the
  fence; what it buys is that `_captures_compatible`, `_interpolate_layer`,
  `relayout_capture` and the client mirror never have to learn chains.
- **The small round** that came with it: an honest tooltip on ▶ Animate plot
  (the app's only other ▶), a hint naming how many frames make a narrow tween
  visible, per-sheet and whole-run plot-time in the layout summary, closing
  the popup leaving the timeline on the frame that was on screen, a visible
  reason under the ⇄ row instead of a hidden `title`, `start here` inputs with
  an honest Reset, and struck-through marks on passes plotted this session.
  Plus the E-batch this round opened with (`4cebea7`, `8a4ffb8`): schematic
  hairline width as a screen property, a Settings **menu** owning Restart
  server, motion params under the paper guide, live generator param editing
  with a coalesced-undo drag, and keyframe sublayers sharing collapse/scroll
  state across an A/B flip.

**Parked by ruling, not forgotten** (the full argument for each is in the
plan's §6d): per-parameter copy/paste between checkpoints (its own section
below); a stored **auto-refreshing tray** and **"project starts in a tray"**;
whether `＋ keyframe` should **jump the timeline to the new key** (it
duplicates the previous checkpoint, so there is nothing to see there yet —
which argues both ways, and wants a bench opinion); and first-class layer
**grouping** for a chain (timeline-v2 Q1(c), see the struck ">2 keyframes"
item above). Awaiting a bench/hardware look rather than a decision: the
multi-pen swap queue on a real machine, and whether a held queue *should*
survive a view change — that one is a deliberate reading of "what you see is
what plots", not an oversight.

**Boundary changes** worth knowing outside this repo: new endpoints for chain
keyframe add/remove/reorder, staging rebake, and `animation export.gif` /
`export.mp4`; `crop` replaces `framing` in sheet and capture formats (legacy
keys still load); ▶ Plot's semantics; ffmpeg is now a launch-installed
dependency rather than an assumed one.

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

## Deferred — per-parameter copy/paste between chain checkpoints

Ruled 2026-08-11 alongside timeline v2 (docs/plans/timeline-v2.md §2b, Q6):
the checkpoint right-click menu shipped (`14006a1`) with whole-checkpoint
Copy/Paste state only — params, effects and placement in one act, with a
visible notice when a paste can't apply across generators. The finer version — copying a SINGLE parameter (or one param
group) from checkpoint A onto checkpoint C — is wanted but deferred: it
grows the menu a submenu per param group and needs a param-path addressing
scheme. Revisit once chains are in daily use and the whole-checkpoint verb
has proven which granularity is actually reached for.

## Far / undecided — AI-assisted inputs

Very down the line, deliberately after the manual pipeline is comfortable:
monocular **depth-map estimation** (MiDaS-class) so any photo yields a
depth asset for `depth_displace` without hand-painting; possibly
segmentation for auto-masking subjects. Constraint: keep it an *asset
producer* (a tool that writes into `assets/`), not a resolve-path stage —
the resolve pipeline stays deterministic and offline.

## Near term — module gallery: generators and effects, thumbnails and tags

Ian, 2026-08-07: *"a possible generator gallery and effect gallery with
thumbnails and tags for later cause the list is growing."* Brainstormed the
same day; the measurements below are the reason the design looks like it does.

**Browse structurally, filter by tags.** Three classes, and they DERIVE — a
new module lands in the right one without anyone remembering to file it:

| class | how it is known | today |
|---|---|---|
| image-based | any param with `format: "asset"` (already load-bearing) | 14 |
| captured | a small declared set — you are the input | 3 (pen, brush, drawing) |
| generative | everything else | 10 |

Tags are the user's, not the module's: free text, editable, stored
machine-level in `~/.axibridge/` beside the pen library so the vocabulary
survives projects — Ableton's model, and Ian asked for it by name. **Modules
ship with no tags.** The structural spine makes the gallery useful on day one,
so tagging stays something you do when a distinction starts mattering, not
data entry the tool demands upfront.

**Thumbnails are live, cached, and rendered against an image YOU choose.**
Ian's improvement on the original proposal, and the better idea: it turns the
gallery from "what does this do to a stock photo" into "what would this do to
*my* photo", which is the question you are actually asking while browsing.
Cache key = module + example params + the module file's mtime + which fixture
image, so editing a generator invalidates exactly its own tile and swapping
the image rebuilds in the background.

**Measured, because "live rendering is heavy" was the obvious objection:**

| | |
|---|---|
| all 27 sources, full rebuild, against a 512x512 fixture | **4.35 s** |
| worst single tile | `linedraw` 1.61 s, `lineart_hatch` 1.16 s |
| everything else | under 250 ms |
| 13 sources that render with no image at all | 0.17 s for the set |

At double the module count that is ~9 s, once, in the background, incremental
after. Pre-rendering and committing the images buys those seconds and pays for
them forever in silent drift — a thumbnail that stops matching a generator the
moment it is tuned, on a project where generators are tuned constantly. Live
and cached means a stale thumbnail is impossible rather than merely unlikely.

**Each module declares one example params dict**, same pattern as
`orientation`, with a test that fails when a new module omits it. Defaults are
not good enough: 14 of 27 sources render *nothing* at defaults, and
`misremembered` at defaults does not sell `misremembered`.

**The effect gallery is the same shelf with two differences.** Measured 14
effects at defaults on a generic reference (a filled circle plus one stroke):
11 read clearly; `hatch_fill` and `offset_fill` needed a shape the reference
was not, and `depth_displace` needs a depth map. So:

1. **Each effect also declares what to demonstrate it ON** — a filled shape,
   open strokes, or an image. One generic reference cannot serve all of them,
   and that was proven on the first attempt rather than argued.
2. **An effect tile is before → after, not after.** `contract_expand` scores a
   visible delta, but only *against the original*; "what does it do" is
   unanswerable from an after-image alone. A ghost of the input under the
   output carries what one frame cannot. This is a genuinely different tile
   from a source tile, where the output IS the answer.

**Starring, and what it does to the dropdown.** Ian, same session: *"starred
generators and effects are the ones shown on the dropdown."* This is better
than the review's plan, which was to DELETE the two selects with the ⌘K
launcher as the safety net that made deletion safe. Starring means the
dropdown does not need deleting — it gets a better job, and the three ways in
stop overlapping:

| surface | for | scope |
|---|---|---|
| dropdown | the five you reach for constantly | your starred set |
| gallery | discovery — "what have I got" | all 45, browsable |
| ⌘K | recall by name, when you know it | all 45, typed |

It also fixes the cold-start problem in the tag design above: **a star is a
one-bit tag.** The tagging system pays off on day one without anyone having
to invent a vocabulary first — and if starring turns out to be all Ian ever
uses, free-text tags were correctly deferred rather than wrongly built.

Two things that must be in it or it bites on a fresh install:

* **An empty star set means SHOW EVERYTHING**, never show nothing. A new
  install with an empty dropdown is broken, not minimal.
* The dropdown needs a **"Browse all…"** row that opens the gallery, or you
  are stranded the moment the module you want is not starred yet.

Stars live where tags live — machine-level in `~/.axibridge/`, beside the pen
library, surviving projects.

**Build order:** gallery before ⌘K. They are two doors onto the same list, and
the gallery's tags are what a launcher should search alongside names. Note
that starring changes the *reason* for ⌘K: it is no longer what makes deleting
the selects safe (nothing is deleted now), it is the keyboard path for someone
who already knows the module's name.

**Not designed yet, deliberately:** where the gallery opens (modal, tab, or
the Compose panel it replaces), and whether transforms — 4 of them, all in one
file — are worth a shelf at all.

## Near term — ⌘K launcher over the module registry

Ranked 11 of 12 in the 2026-08-07 multi-agent review, and the ONLY proposal
there that needed tooling the project did not have. It has it now: the Vite
port landed the same day, so the "vendored-esm" tag on that row is spent.

**What it is, and what it is not.** Not a generic command palette. A launcher
scoped to the registry — 27 sources, 14 effects, 4 transforms, plus backends
and the project's own layers by name. Press ⌘K, type `hatch`, get
"hatch_fill — effect", Enter, it is added to the selected layer.

**Why it earns its place:** the registry is 45 modules and growing, which is
what makes the two Compose `<select>` boxes hard to scan — a 27-item dropdown
is a list you read, not a thing you pick. The review's point is that the
launcher is what makes DELETING those selects safe: typing three letters
beats scrolling twenty-seven options, and the dropdown stops being the only
way in. It also answers the same problem a Generate ▸ submenu would have
answered badly — the review explicitly ruled that a 27-item submenu does not
earn its place while a fuzzy-matched launcher does.

**Needs:** a fuzzy-match input, not a framework. The matching is the whole
build; everything it launches already exists and is already addressable
(`/api/layers/generate`, the effect stack, `menu_spec`'s selector idea).

**Do it after** the module gallery below if that gets built — a launcher and
a gallery are the two ways into the same list, and the gallery's tags are the
thing a launcher should search alongside names.

## Far / undecided — interrupted plot should have been a generator

Ian, 2026-08-07: *"interrupted plot should have been a generator
(non-modifiable)."* He is right about the smell, and the reason it isn't one
is a real architecture question rather than an oversight — so it is filed
here rather than decided.

**The smell.** `session.interrupt_fragment` is an *aesthetic* tool: it rolls a
random start/stop over the plot's draw order, cuts strokes mid-line where the
pen would have lifted, and makes marks. Nothing in it touches the plotter. Yet
it lives in the Plot tab between Backend and Motion parameters, and it **bakes**
— `LayerSource(type="baked")`, geometry parked in `source_geometry`. Every
other generator in the app stays live: reroll a param, tween it, animate it,
scrub it on the master timeline. This one is frozen the moment it is made, and
undo is the only way back to before it.

**Why it isn't a source module.** A `SourceModule` produces geometry from its
params alone. `interrupt_fragment` needs `resolved_document("all")` — the whole
rest of the project, after plot-pass optimisation, because the whole point is
the order the machine would really have drawn in. That makes it the first
source that reads the document it is part of, which is a cycle against the
single-resolve invariant: the layer is inside what it consumes, so resolving it
changes its own input.

**Two ways out, both real work:**

- *Exclude-self.* It resolves against everything BELOW it, exactly as region
  layers already do — the resolve order (`occlusion(regions(effects(transform
  (source))))`) has the precedent and the machinery. Cost: the layer becomes
  order-dependent, and its output changes whenever anything beneath it changes.
  That is either exactly right (it stays a live view of "this plot, stopped
  early") or maddening (you nudge a layer and last week's fragment redraws).
- *Snapshot input.* It captures the resolved document once, and stays live only
  in its own params (seed, start, stop). Rerollable, tweenable and animatable
  with no cycle; the captured input goes stale when the layers under it change.
  This is what the A/B capture path already does, so the pattern exists.

**Revisit when** either (a) someone wants to animate or tween an interrupted
fragment — that is the use the bake blocks and the one that would force the
choice, or (b) the node question below is answered, since a node graph makes
"a layer whose input is other layers" ordinary rather than exceptional.

**Ian settled the ambiguity, 2026-08-07:** "(non-modifiable)" meant *once
baked* — the fragment is fixed after it is made — *"unless it is not expensive
to hold a copy of the plot to reiterate."*

**It is not expensive. Measured** (`tracemalloc`, snapshotting the flattened,
optimised path list, which is what a reroll needs):

| plot | paths | points | snapshot |
|---|---|---|---|
| 10 polygons | 10 | 80 | 0.01 MB |
| 20 lissajous | 20 | 14,420 | 0.89 MB |
| 100 lissajous | 100 | 72,100 | 4.6 MB |
| 400 lissajous (heavy) | 400 | 288,400 | 18.6 MB |

~64 B/point — lower than undo's ~130 B/point, which also carries a deep-copied
`Project`. For scale the whole undo geometry budget is ~65 MB. And the baked
layer ALREADY retains the fragment slice, so the marginal cost of holding the
whole plot instead is about `1/fraction-kept`, not the full figure.

So **snapshot-input is the affordable design**: the layer captures the
flattened plot once and stays live in its own params (seed, start, stop),
making it rerollable, tweenable and animatable with no cycle and no exclude-
self rule. Remaining cost to weigh when building: the snapshot goes stale when
layers under it change (needs a visible "recapture" affordance, like A/B), and
several such layers plus undo history multiply the figure — the existing undo
geometry budget already accounts for retained geometry, so check it holds.

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

## ~~Far / undecided — UI revamp (frontend tooling ceiling)~~ — RESOLVED 2026-08-07

**Ian's call, taken as part of `docs/plans/ui-redesign.md`: Vite +
TypeScript.** Everything below is kept as the reasoning that led here, not as
an open question — read it before proposing a *different* toolchain, not
before touching the frontend.

What was actually adopted, and how it answers each cost the section raises:

- **Source did not move.** `axibridge/static/` is still the source of truth,
  still plain ES modules, still view-source debuggable. Vite's `root` points
  at it; the bundle lands in `axibridge/static_dist/`.
- **The Pi keeps working with no Node at all.** `app.frontend_dir()` serves
  the build when it exists and the source when it doesn't — one rule, no env
  var, no third mode. That is the whole answer to "the Node toolchain question
  for the idkpi clone": a machine without npm serves exactly what it served
  before, because the source is real runnable code and not an intermediate.
- **TypeScript is loose and opt-in per file** (`allowJs`, `checkJs: false`,
  `noEmit`). `npm run typecheck` is the entire surface; nothing was renamed.
  The "generate types from OpenAPI" tier the brainstorm identified is still
  available and still a good idea — this doesn't foreclose it.
- **What it actually bought**, and it was NOT speed: npm access (so the
  deferred ⌘K launcher and a component tier stop being blocked on vendoring),
  and cross-file types. The measured build is ~260 ms, which was never the
  problem.
- **What it costs**, honestly: a lockfile and version drift on the JS side,
  and the stale-build trap (a `static_dist/` left over from an old build
  shadows your edits — the startup log names which frontend is live).

The criterion below was written for "reopen only when a specific feature needs
it". It was overtaken by a direct decision rather than met; recorded plainly
so nobody later reads a met criterion that wasn't.

### The reasoning that led here (kept)

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
