# Roadmap

Loose, ordered by conviction. Each item says *why*, so a future session (or
a smaller model) can judge whether the reasoning still holds before acting.
Rules of engagement for any of it: the resolve invariant and the module
contracts (ARCHITECTURE.md, docs/MODULES.md) are not negotiable; the frontend
source stays plain ES modules in `axibridge/static/` served buildless on a
machine with no npm, with Vite/TypeScript as an additive layer on top (see
CLAUDE.md's frontend-build note for what shipped 2026-08-07 and what it cost).
Every numeric param stays bounded. Loose generator brainstorms (uncanny/
Cohen-line direction, plus how the involved ones should meet the UI) live in
`docs/IDEAS-generators.md`.

Shipped work has been pruned from this file (2026-08-17) — see `git log` /
`STATUS.md` for what landed and when. This file tracks what's still open.

## Compose and open benches — implementation (2026-09-08)

Ian asked for a thorough review to lift the tool's look and feel, including
surface and architectural optimizations while preserving its experimental
philosophy. The [illustrated report](docs/reviews/ui-review-2026-09-07/index.html)
and [editable review](docs/reviews/ui-review-2026-09-07/REVIEW.md) are complete.

**7 September: Ian approved the first cosmetics pass.** Flexoki, mono hierarchy,
shared controls/icons, pending state styling and Second Reading sheet fit are
implemented; [captures and limits](docs/reviews/ui-review-2026-09-07/cosmetics/README.md)
are ready for him to check.

**8 September: Ian approved the mockups and bounded implementation.** Popup is
now the default, with expansion preserving state; Compose has explicit selected
source scope and a compact expandable layer list. Versioned bench identity,
shared presentation, specialised Second Reading comparison and grouped Homeostat
controls/observed telemetry are implemented. See
[implementation evidence](shots/ui-benches-0908/README.md). Native interaction
acceptance remains with Ian. Durable recovery, unified unsaved-work prompts and
richer application services remain deferred pending their own design.

**8 September: whole-app precision pass implemented.** Shared type/spacing,
quieter hierarchy, paired values and consistent states now carry across all tabs
and benches. [Matched evidence](docs/reviews/ui-precision-2026-09-08/report.html)
is ready for owner judgement; native/paper acceptance remains open. Existing
workflows and the mono/Flexoki identity are retained.

The remaining review is a proposal set. M1-M6 sequence
viewing/interaction confidence, preservation, everyday composition, sustained
development, output/performance and bounded spatial experiments. The report
reproduces sheet clipping, volatile working alternatives, modal focus/error
problems and guide-undo inconsistency; concurrent-response risks remain untested.
Retain bench-and-bed and the mono voice. Workspace promotion, comparison,
recovery ownership, node editing and framework changes need their stated
criteria and Ian's scope decision before implementation.

## Near term — Second Reading: recover responsiveness, make elements

**2026-09-05–06 shipped:** interactive process bench with recorded human turns,
continuation branches, Keep/Resume and reproducible studies; initial generator
and subsequent experiments. These are mechanically verified, not an aesthetic
completion. Ian's judgement: the first version was more responsive; later
revisions made little progress. Do not treat the latest mechanism as the winner.

**2026-09-06 implemented, ready for Ian to check:** first engine recovered from
prior tool history and matched against all 30 original cells. Separate geometry
and relation experiments, Attention/Departure/Scale, occasional wandering,
whole-element fitting and rounded inward boundary turns are available. A bounded
Sol review included neutral populations, altered variants and sequence calibration.
The lead removed sampling-dependent echo hooks; Ian then requested removal of
thick parallel reinforcement. Responsive is now the normal starting policy,
without those stacks. Visible/live pen smoothing and seed randomization are added.

**Still open:** Ian’s own alternating-use judgement, especially whether ignoring
new ink offers a consequential next move, and whether boundaries/smoothing feel
right in the hand. Scale affects extensions/connections but remains quiet on
copied motifs. Tapered multi-line finish stays deferred to a separate effect.
No paper test yet; no general aesthetic success claim. Current controls:
`docs/plans/second-reading-quick-guide.md`; retained evidence and limits:
`docs/reviews/second-reading-0906-lead.md` and `shots/second-reading-cleanup-0906/`.

## Near term — make what exists comfortable

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
  - *Dash / stitch*: cut paths into dashes (gap, phase) for texture.
  - *Lens / attractor warp*: radial push/pull with falloff about a point —
    the hand-placed complement to the depth map.
  - *Per-layer crop effect*: paper-space per-layer clipping. The plot-pass
    crop option (guide/bed/custom + inward margin) already covers the
    whole-plot case; this would be a layer-local effect instead.
- **Image contours generator**: reuse `image_threshold`'s marching squares
  at N thresholds → nested contour rings (topographic shading), following
  image luminance directly with no seed or propagation model — distinct
  from `fast_marching_topo`/`fast_marching_contours`, which solve a seeded
  Eikonal wavefront instead. Most of the code already exists; it is the
  natural sibling of threshold + hatch.
- **Generator quality-of-life**:
  - *Presets & favourites*: named param sets per generator in a global JSON
    store (pattern: `stores.py` pen library), plus starred generators
    pinned at the top of the picker. This is also where the pass-1 **style
    genome / "hand" presets** land ("nervous", "tired" freehand hands;
    two_hands agent genomes — its params are already grouped for it):
    presets over parameters, per IDEAS pass-1 UI principle 2.
  - *Colour separation follow-ons* — the CMYK/RGB/tonal separation itself
    shipped 2026-08-17 (`docs/plans/channel-separation.md` has the design and
    the decision table). Three extensions were roadmapped with it, and
    `channels.py`'s `CHANNEL_DECODERS` seam exists so each is a plate
    definition rather than surgery:
    - **Spot-colour plates**: pick a hex, the plate is per-pixel proximity to
      it. This is what actually separates for a drawer of three arbitrary
      felt tips rather than four theoretical inks. The real design work is
      the metric — RGB euclidean distance lies about perceived colour, Lab
      doesn't.
    - ~~**HSV / Lab opponent plates**~~ — **HSL shipped 2026-08-17** (hue /
      saturation / lightness, an HSL mode in the separation row). Saturation
      turned out to be the useful one (ink only where the image is colourful)
      and lightness is a genuinely different greyscale from luma. **Lab is
      still open** and is the better half: perceptual opponent axes, and its
      distance metric is what spot colour above actually wants.
    - **N-pen least-squares separation**: pick 3–5 real pens from the library
      and solve the subtractive mix per pixel for the closest match to the
      photo. The end of Cohen's colour logic — a palette chosen by what you
      own, not by what a printer assumes. Ambitious enough to be its own
      project; the one part of the current shape it would strain is that the
      plate list stops being a fixed `Literal`.
    - **Per-plate screen angles**: real CMYK printing rotates each screen
      (C 15°, M 75°, Y 0°, K 45°) to kill moiré, and separating with
      `halftone` at one angle almost certainly will moiré. Deliberately held
      back until Ian has seen the first prints and can say whether that
      moiré is a problem or a feature — and it only works for generators
      with an angle param, so it is conditional magic either way.
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

## Near term — Oehlen pass: regime collision

From the second idea pass (`docs/IDEAS-oehlen-pass.md` — read it first, the
*why* lives there).

- **Pen tool (⚓ béziers)** — briefed (`docs/plans/pen-brush-tools.md`,
  combined with the (shipped) brush tool brief). Photoshop grammar: click =
  corner anchor, click-drag = smooth anchor with symmetric arms, rubber-band
  previews the next segment, Option-drag breaks arm symmetry, click-first-
  anchor closes (→ `filled=True` = instant occluder / region input; visible
  ink fill = `hatch_fill` on the stack), Enter commits open, Esc cancels,
  Backspace deletes last anchor. Storage: a `pen` source with anchors +
  handle vectors + `closed` per subpath; `generate()` flattens cubics at a
  bounded `flatten_tol` (~0.2 mm) — the grammar generator's exact precedent,
  `model.py` untouched. Post-commit: pen mode + selected pen layer shows an
  anchors/handles overlay; drags regenerate with `coalesce=true` (one undo
  entry per editing run). Toolbar becomes a mode segment: ↖ select · ✎ draw ·
  ⚓ pen · ● brush; every tool = geometry-as-params source + canvas-mode JS
  module (the draw-mode pattern).
- **Liquify (soft-brush warp effect)** — raised as a hypothetical, thinking
  written down in `docs/plans/liquify-effect.md` (loose plan, NOT a
  commitment — read it before starting, the reasoning is the value).
  Push/twirl/pinch under a soft circular brush, in paper-space mm. Three
  things it settles: it would be the **first captured-input *Effect***
  (draw/pen/brush are all Sources — the only unfamiliar plumbing is PATCHing
  a step's params rather than POSTing `regenerate`); "depth as parameter"
  reads as a global `amount` 0..1 that must be *exactly* identity at 0,
  which makes timeline animation free; and **interpolating two
  liquifications is easier than the geometry morph already shipped**,
  because a warp is a field, not a structure, so it blends unconditionally.
  The trap there: `blend_effect_stacks` doesn't deep-lerp hidden geometry
  fields (only `blend_generator_params` does), and the tempting fix — A/B
  inside the effect — re-forks interpolation, which the 2026-07-19
  unification exists to prevent. Extend the core instead. Reuse
  `coherent_jitter._resample` (densify before warping, or straight segments
  stay straight) and `depth_displace`'s `anchor: layer|paper`.
- **Perception pass — line weight = certainty** — briefed
  (`docs/plans/perception-pass.md`; the ideas doc calls this the strongest
  AI-age principle): run several cheap perception passes over one asset
  (threshold edges, Depth Pro discontinuities, a segmentation boundary) and
  let *agreement* set the mark — fat beam where all agree, hairline wander
  where one thinks so, dither-density where ambiguous. Honors the far-
  section constraint: any model runs as an *asset producer*, the generator
  itself reads deterministic maps. Sibling: **perception scaffolding**
  (segmentation polygons, ill-fitting bounding boxes, annotation ticks as
  first-class marks — our era's pattern fill).
- **Mouse preset for freehand** — the "bad hand": grid-quantized output,
  polling-rate resampling, sudden angular corrections. Cheap (params or a
  preset on the existing effect).

Also: **revise the pass-1 ideas** (`docs/IDEAS-generators.md` — rehearsal,
blind contour, phase transition) into roadmap items as conviction firms.
**Tuning follow-ups** from the July Pi generator run are actionable and live
in `docs/plans/pi-generators-RESULTS.md`: a lattice grammar +
subtree-propagating violations, misremembered on a real photograph (widen
the searching-mark band if mid-confidence stays rare), two_hands genome
presets, a continue-strokes "seam pen" split. The *indifferent lines over
structured ground* recipe stays in the ideas doc — it's a composition
practice, not a module.

## Near term — AARON pass

From `docs/IDEAS-aaron-pass.md` (grounded in Cohen's AAAI-1988 paper — the
mechanisms are quoted there). Pull order:

1. **Core-figure generator** — skeleton (plant morphology variables /
   armature with a balance constraint) → embodied closed outline walked
   around it with carefulness varying along the body (freehand controller
   as the hand) → several placed foreground-first under AARON's
   never-overlap rule via the existing masks. The missing thing-ness that
   two_hands lacks. Briefed (`docs/plans/aaron-core-figure.md`) — settles
   plant-morphology-not-figure-armature and the embodiment/never-overlap
   mechanics as concrete, self-contained (no session/compose change) design
   calls.
2. **Sheet-snapshot asset** — one endpoint/button rasterizing the current
   resolved output into an asset; every image-driven generator becomes
   context-aware (negative-space filler, two_hands v2 perceiving the sheet,
   respond/annotate generators). Zero architecture change.
3. **Felt-tip color kit** (shares multi-layer-per-pen plumbing with the
   sheet-snapshot item): overprint zones with pairwise intersections drawn
   in both pens; value-rule pen assignment with free hue (Cohen's color
   logic); duotone density mixing; repetition-as-pressure.
   *Implementation note*: overprint needs cross-layer geometry, which the
   effect protocol deliberately cannot see (effects are pure single-layer
   functions — keep it that way). Build it as a **session-level composer
   operation** — the `add_lineart_stack` pattern: compute the pairwise
   shapely intersections once at creation time and emit baked layers per
   pen. Do NOT bolt cross-layer reads onto effects, and don't reach for
   region layers either (regions shape what's below, they don't emit
   intersection geometry as new plottable layers).

## Near term — pass 4: something at stake, and lines out of fields

From `docs/IDEAS-pass4.md` (read it first — the *why* lives there, and the
conceptual material is in the vault as atomic notes). Two halves: **A**, give
the process something to lose (cybernetic loops); **B**, let the field carry
the structure (field-derived geometry). Plus **C**, an adjacent blending axis.

**The dependency that sets the order:** B and C items are all independent of
each other and of A. Only A2/A4 genuinely needed A1 — and A1 has landed
(`docs/plans/time-as-a-param-RESULTS.md`, 2026-08-21: declared time axes,
`ProcessModule`/`Trajectory`, the `venation` generator, the process popup,
and `Rehearse` — the last of which also closes pass 1's §2, see
`docs/IDEAS-generators.md`). So Round 3 below is no longer gated; A2 and A4
can be picked up whenever, same as B and C.

### Round 1 — cheap, independent, new marks on paper immediately

1. **Geodesics on the Eikonal solver** (B1) — the shortest hop in the pass.
   `_fast_marching.py` already solves travel time under a spatially varying
   speed function; trace the **orthogonal trajectories** of the iso-time
   contours instead of the contours. Same solved field, a completely different
   picture: lines that read as navigation rather than as a flow field.
2. **Hachures** (B3) — Lehmann's slope-proportional stroke system. Direction
   and weight both derived from the surface, so depth maps and
   `_lineart.flow_field` supply everything it needs. A complete historical line
   grammar nobody's eye is tired of.

### Round 2 — the sensor, and the blending axis

3. **Prediction error as an effect, with habituation** (A3 + A5) — ~30-line
   predictive-coding loop on stroke statistics, modulating weight/presence by
   `|error|`. Build as an **effect** first, the `freehand` argument: it
   retrofits onto every existing source before a new generator is written. Two
   timescales beat one; the learning rate is "how easily bored".
   **Ship A5 with it, not after it.** A predictor that learns is a habituating
   memory; a drawer hunting for error is Pask's novelty drive. A3 alone has a
   known failure mode — ink is error, error decays as it learns, the drawing
   dies out — and A5 is precisely the fix. Shipping A3 by itself ships the bug.
4. **Optimal-transport blending** (C1) — correspondence-free morphing via
   `scipy.optimize.linear_sum_assignment`. **A linear blend crossfades; OT
   makes mass travel**, and with no opacity available travel is the only
   interpolation a pen can draw. Sinkhorn's ε is the expressive knob. Extend
   `tween.py`'s shared blend core — never re-fork it.
5. **Wasserstein barycenters** (C2) — N drawings, N weights, navigate the
   simplex. The direct answer to the latent-blending wish, and its ceiling
   rises with A1/A2 (plausible midpoints need a rich enough process to be a
   manifold).

### Round 3 — the engine

6. ~~**Homeostat generator** (A2)~~ — **SHIPPED 2026-09-04**, source id
   `homeostat`; ledger `docs/plans/homeostat-RESULTS.md`. Memory is a slider
   defaulting to 0, as specified. **Not yet on paper, and not yet seen in the
   bench** — that eye-check is the open half of the item, alongside venation's.
7. **The seam** (A4) — independent fronts with identical local rules and no
   awareness of each other; draw the failure to reconcile. The aesthetic
   inverse of `region_boundary: continuous`, which stitches. Ian's read: the
   existing attempts "don't really hit the spot but they're a good start" —
   return to it with A1 in hand rather than speccing it now.

### Opportunistic / parallel

- **Algedonic marks** (A7) — the smallest item in the pass. One monitored
  quantity, one threshold, one mark placed *without regard to* the composition
  because something went critical. Indifference with a cause, which reads
  differently from contrast for its own sake. Pairs with A2, which is the other
  response to a variable leaving range — Ashby rerolls the rules, Beer raises
  the alarm. Bolts onto anything that already measures something.
- **Curve-shortening flow** (B5) — small and self-contained. Doubles as a
  correspondence mechanism (A → circle → B, circle as normal form); run it
  forward on both and reverse one trajectory, since backward CSF is unstable.
- **Stripe patterns** (B4) — a **parallel branch** by Ian's reading, tied to
  his separate 3D-engine plan. `flow_field` already gives the direction field,
  so the cheap version can test the look; the paper's machinery is what makes
  the forced singularities land gracefully rather than arbitrarily.

### Spikes worth running before committing

- **Greedy residual stroke fitting** — "place the stroke that most reduces the
  error, repeat". ~100 lines, no dependencies, deterministic. If it delivers
  the structural point (marks that cost something), it may make the diffvg
  build fight unnecessary. Run this before touching diffvg/CLIPasso.
- **diffvg offline on CPU without CLIP** — is it buildable and usable as a bake
  step? Heavy dependency, historically fiddly build; torch is already present.
- **Stripe patterns in 2D** — is a plane-only implementation tractable without
  the full discrete-differential-geometry apparatus?

## Sheets workflow v2

Still open, priority order:

- **`_documents_with_temp_state` → explicit args**: thread project/geo
  through `_documents_for_format` instead of swapping `self.*` under the
  lock; enables parallel interp batches.
- **Interp fidelity**: layers only in capture B append at the END of
  z-order (needs a positional merge) — since 2026-07-19 they only appear
  from the midpoint step on (one-sided layers step at t=0.5 in both
  directions; the B-only case used to crash below the midpoint). Batch
  steps are hard-linear — accept the tween `time_curve` enum. Both
  interpolation instruments share ONE per-layer blend core in `tween.py`
  (`blend_effect_stacks`/`blend_generator_params`/`lerp_paths`/
  `structures_match`), full-stack rule + tween-params-lerp landed, behavior
  pinned in `tests/test_interp_pinning.py` — extend the core, never re-fork
  it.
- **Plot-cursor persistence**: the stepper's page/pass lives in browser JS
  and dies on reload; persist alongside staging (non-undoable) so a
  multi-hour flipbook survives a restart. Cheaper to survive since
  2026-08-11: `start here` inputs on the sheet and frame steppers make
  recovery one typed number instead of eighteen `Skip pass →` presses, and
  Reset now returns to that chosen start (a separate `⤒ 1` goes to the true
  beginning).
- **Staging browser ergonomics**: batches make the tray list long — a grid
  browser with thumbnails. Partly eased 2026-08-11: group headers carry the
  richer layout label and click to select, animation-born sheet groups are
  visually distinct (ochre edge), and passes plotted this session strike
  through (client-side only, no persistence). Thumbnails are still the ask.

## Animation — open items

Everything rides on the tween machinery; the master timeline `t` is an
ephemeral argument threaded through the single resolve path (never a second
geometry path, never a checkpoint). What's already shipped is in `git log` /
`STATUS.md` / `docs/plans/timeline-v2.md`'s closing ledger (§6). Still open:

- **Arc-length resampling for shape morph**: the captured-geometry tween
  (`pen.subpaths`, `drawing.strokes`) deep-lerps anchor-by-anchor when A and
  B share structure; mismatched point/anchor counts still step. Resampling
  to morph differently-structured A/B is the remaining open piece (see
  MODULES.md "Geometry-as-params sources").
- **Multidimensional video / sheet variants, v2**: staging/batch
  interpolation covers the manual workflow (capture A, change parameters,
  capture B with the same format, generate staged interpolated batches).
  Interpolating two *sheet* captures yields one group holding A's and B's
  own snapshot states as endpoints with the blends between them — Ian's 2D
  frame-matrix reading, where the same frames run along one axis and the
  parameters blend along the other. Same code path serves relayout, so
  re-gridding keeps the grouping. The open question is a richer 2D
  authoring surface where timeline `u` is frame/clip time and variant `v` is
  a second parameter dimension with better browsing, naming, and traversal
  controls. Do not add a second global master timeline casually; keep any
  automation as temporary sampling over the existing resolver
  (`session.resolved(master_t=u)` / `sheet_document`) and preserve pen
  grouping, preview/export/estimate agreement, and undo sanity.
- **Per-frame fades via pen pressure / multipass density** (motion trails).
- **Per-parameter copy/paste between chain checkpoints** — deferred
  2026-08-11 alongside timeline v2 (`docs/plans/timeline-v2.md` §2b, Q6):
  the checkpoint right-click menu ships whole-checkpoint Copy/Paste state
  only — params, effects and placement in one act, with a visible notice
  when a paste can't apply across generators. The finer version — copying a
  SINGLE parameter (or one param group) from checkpoint A onto checkpoint C
  — is wanted but deferred: it grows the menu a submenu per param group and
  needs a param-path addressing scheme. Revisit once chains are in daily
  use and the whole-checkpoint verb has proven which granularity is
  actually reached for.

**Parked by ruling, not forgotten** (full argument for each is in
`docs/plans/timeline-v2.md` §6d): a stored **auto-refreshing tray** and
**"project starts in a tray"**; whether **＋ keyframe** should **jump the
timeline to the new key** (it duplicates the previous checkpoint, so there
is nothing to see there yet — which argues both ways, and wants a bench
opinion); first-class layer **grouping** for a chain (a chain is still N
sibling layers plus one tween, and a real parent/child node in `compose.py`
+ the dock + the save format remains a round on its own; `keys` does not
foreclose it — a grouping UI would present the same list).

**Awaiting a bench/hardware look, not a decision**: the multi-pen swap
queue on a real machine (the guided pass queue is simulator/headless-tested
only, never run against real hardware), and whether a held queue *should*
survive a view change — that one is a deliberate reading of "what you see
is what plots", not an oversight.

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

**Do it after** the module gallery above if that gets built — a launcher and
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

## Documentation / robustness debts

- The IPR has no hole representation; holes are separate filled loops,
  nesting-derived (a closed `filled=True` loop inside another is a hole by
  depth parity, no explicit flag). Both `hatch_fill` AND occlusion
  (`compose.build_mask`) already reassemble this even-odd — a donut occludes
  correctly as a ring, not a solid island. The remaining real gap is only
  the IPR itself carrying no hole *representation* (a hole is inferred from
  nesting, and nesting only handles one level of "hole in a solid" cleanly)
  — if a design ever needs holes as a first-class field, or nesting deeper
  than solid→hole→solid, that is an IPR change; today's depth-parity pass
  is not that.
- Pen-plotter-specific test gap: nothing exercises the native backend
  against recorded EBB traffic; a replay harness would catch the next
  protocol drift without hardware.
- **Unsaved-work guard**: the open project lives only in RAM until an
  explicit save, `POST /api/project/save` 422s on a bare body, and
  `/server/restart` drops everything with only a browser-side warning.
  Wanted: a periodic autosave to a recovery slot (NOT the project folder —
  don't clobber deliberate saves), and the restart endpoint refusing when
  unsaved changes exist unless `force=true`. Cheap insurance for a
  single-operator instrument.
