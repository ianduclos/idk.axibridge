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
- **Image contours generator**: reuse `image_threshold`'s marching squares
  at N thresholds → nested contour rings (topographic shading). Most of the
  code already exists; it is the natural sibling of threshold + hatch.
- **Hershey/single-stroke text generator**: classic plotter need; fonts are
  public domain (Hershey set), output is plain polylines.
- **Plot resume**: the job already reports `paths_done`; persist the last
  finished index and offer "resume from path N" after a USB/power failure.
  Saves real plots, cheap to do at path granularity (native backend plots
  path-at-a-time already).

## Mid term — interpolation (the layer-variant idea)

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

- `main.js mapGhosts()` special-cases module ids for show-map ghosts —
  generalise (e.g. modules declare a `placement` schema tag) when a third
  image-driven module appears.
- The IPR has no hole representation; holes are separate filled loops.
  `hatch_fill` reassembles even-odd, occlusion does not. If holes start to
  matter for occlusion, that is an IPR change — design, don't patch.
- Pen-plotter-specific test gap: nothing exercises the native backend
  against recorded EBB traffic; a replay harness would catch the next
  protocol drift without hardware.
