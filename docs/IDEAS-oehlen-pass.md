# Idea pass 2 — Oehlen / regime collision (July 2026)

Second concept pass, from a conversation over four Albert Oehlen works (the
1990s *Computer Paintings* and descendants). Companion to
`docs/IDEAS-generators.md` (pass 1: the Cohen/intentional-line direction —
its §1 shipped as `effects/freehand.py`). Pass 1 gave us the *hand*; this
pass is about the machine's own marks and letting incompatible voices
collide on one sheet.

## The analysis, condensed

Oehlen bought a PC around 1990, drew badly with a mouse in a cheap paint
program, and enlarged the results to 3-metre canvases. What the pictures
actually do:

1. **Tool honesty at hostile scale.** The machine's *native* marks — aliased
   staircase edges, dither scatter, pattern fills, the mouse's clumsy
   polling — used as drawn subject matter, blown up past politeness. Every
   pixel becomes a monumental decision.
2. **Regime collision.** Two or more irreconcilable rendering systems share
   one surface: smooth hairline freehand loops vs. hard bitmap blocks;
   spray-paint over enlarged prints; wiry ink lines wandering *indifferently*
   across collaged perspective grids. The energy is in the seams.
3. **Line weight as the whole composition.** Beams → tubes → hairlines,
   three orders of magnitude of stroke weight, no color, no focal point,
   all-over accumulation.
4. **Interruption and unmotivated placement.** Shapes truncated mid-gesture;
   texture patches parked where nothing asked for them; near-figuration
   (almost an eye, almost a letter) that refuses to resolve.
5. **The bad hand, recorded faithfully.** He drew badly *on purpose* and the
   machine transcribed the clumsiness with total fidelity. The inverse of
   our freehand effect (a skilled hand with human error).

**The trap:** literally drawing pixels/dither/checkerboards in 2026 is retro
nostalgia (vaporwave), not Oehlen. His move was *using the consumer
machine-tool of his moment, badly, and monumentalizing its native marks*.
Today's machine-native residue is different: segmentation masks, bounding
boxes, confidence scores, depth discontinuities, attention maps,
hallucinated completions, model disagreement. That is the vernacular to
blow up to sheet scale.

**Unifying AI-age principle worth pushing hardest — line weight = certainty:**
run several cheap perception passes over the same asset (threshold edges,
Depth Pro discontinuities, a segmentation boundary) and let *agreement* set
the mark: fat beam where all agree, hairline wander where one thinks so,
dither-density where ambiguous. Oehlen's weight hierarchy derived from
machine epistemics instead of taste.

## The commitments (ordered — see ROADMAP)

### 0. Generation workbench popup (build first) — **shipped July 2026**

Shipped as `static/js/workbench.js` + `scraps.py` + `/api/workbench/preview`
and `/api/scraps*`. Original sketch:

User direction: before the modules below, a popup screen for *messing with
generation* outside the project — pick a generator (+ effect stack), tweak
params with the same auto-forms, reroll seeds darkroom-style, then **save
the result as SVG for later** or **import it into the current project**.
Later growth: mouse drawing (the "bad hand" input device, see pass 1 UI
principle 4 and the mouse-preset idea below), editing of saved scraps.
Server side should stay *stateless* — a preview endpoint that runs
module+params without touching the session, project, or undo history;
plotting only ever happens after import, so the single-resolve invariant
keeps its meaning.

### 1. Bitmap + fat tube effects (quick, load-bearing) — **shipped July 2026**

Shipped as `effects/bitmap.py` + `effects/fat_tube.py`. Original sketch:

The regime vocabulary the region system will speak — build these first.

- **Bitmap**: quantize a layer's paths onto a coarse mm grid; emit filled
  staircase blocks (plus optional dither field at partial coverage).
  Occlusion handles the rest.
- **Fat tube**: offset a spine into a constant-width outlined pipe with
  round caps, `filled=True` — tubes then cross over/under each other
  through the existing occlusion masks for free (image 5's interlock).

### 2. Region layers — "affects below" (the real project) — **shipped July 2026**

Shipped as `CanvasLayer.region` + the region pass in
`compose.resolve_project` (see ARCHITECTURE.md "Resolve order"). Original
sketch:

Regional effects via the **adjustment-layer model, not nodes** (the ROADMAP
node question stays parked). Precedent already in the codebase: the
`occluder` flag — a layer whose silhouette acts on layers below via z-order.

A layer gains a mode: **affects below**. Its own geometry (any source:
rectangle, polygon, blob, image-threshold output) stops being drawn and
becomes a region mask; its effect stack applies to the geometry of layers
underneath, clipped to the region (shapely split at the boundary; inside
runs the stack, outside passes through). "A hard square that gets
pixellated", "an area that gets liquefied" — with zero new UI paradigms:
same layer list, effect stacks, transform gizmo, undo.

- Composes by z-order the way Oehlen composes by accumulation: multiple
  overlapping regions, reorderable, each biting sections out of everything
  below it.
- **Animates for free (sleeper payoff):** regions are layers → layers tween
  → tweens follow the master timeline. A pixellation square drifting across
  16 grid-sheet frames is a new animation vocabulary at zero extra cost.
- Hard boundaries are the aesthetic (regime collision with a visible seam),
  not a limitation. Feathering later, if ever.
- **The one careful design decision:** where regions sit in
  `occlusion(effects(transform(source)))`. Working instinct: regions apply
  to the post-effect, pre-occlusion geometry of lower layers, and region
  output re-enters occlusion normally (pixellated blocks can occlude).
  One seam in `compose.py`, not a rewrite; the single-resolve invariant
  survives.

### 3. Continue-strokes v1 — autocomplete as intrusion (no model needed) — **shipped July 2026**

Shipped as `effects/continue_strokes.py` (`id: continue_strokes`, Pi run):
order-N Markov chain over turning angles quantized on a grid adapted to the
layer's own spread, plus a step-length pool; `temperature` spans
most-typical → full empirical spread; closed paths pass through unchanged.
Original sketch:

An effect: for each path in the layer, learn local stroke statistics
(turning-angle + step-length distributions, n-gram/Markov over curvature)
from the strokes actually present, then extend each path past its endpoint
with a sampled continuation. Fluent but hollow, visible seam, deterministic
under seed. Pure Python, fits the effect contract as-is. A neural v2
(sketch-RNN-ish, behind `available()`) only if the statistical one feels
shallow — bet: it won't for a while.

### 4. Glyph grammar source — typography to total abstraction

Hershey stroke fonts (single-line, plotter-honest, shipped with vpype which
is already a dependency) fed through destruction rules — fragment,
recombine, mirror-stamp, over-rotate, scale beyond legibility — with an
`abstraction` dial from "almost reads" to "pure scaffold". Connects to the
pass-1 transgression-budget grammar; glyph fragments against organic
freehand loops is image 2's near-figuration device. Pairs with regions
(a region that pixellates a glyph field).

## Smaller notes captured along the way

- **Mouse preset for freehand**: the 2026 "bad hand" complement to fatigue —
  grid-quantized output, polling-rate resampling, sudden angular
  corrections. Cheap; params or preset on the existing effect.
- **Perception scaffolding as composition**: draw the bureaucratic marks of
  computer vision (segmentation polygon boundaries with over-simplified
  vertices, bounding boxes that don't quite fit, annotation tick marks) as
  first-class elements — our era's pattern fill; park them unmotivated,
  crop hard.
- **Indifferent lines over structured ground** (recipe, not module): dense
  structural ground (grids, perspective boxes, image texture), then two or
  three enormous wandering lines crossing the whole sheet ignoring
  everything beneath — no occlusion, fattest pen, drawn last.
