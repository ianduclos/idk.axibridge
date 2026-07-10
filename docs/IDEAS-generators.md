# Generator ideas — uncanny / liminal / machine-drawn

Loose brainstorm, July 2026. Not commitments — read ROADMAP.md for conviction
ordering. Kept because the *framing* matters as much as the entries.
Pass 2 (Oehlen / regime collision) lives in `docs/IDEAS-oehlen-pass.md`.

## The framing

The computer-art clichés (perlin jitter, circle packing, flow fields) apply
randomness to **geometry**. Cohen's insight in AARON was to apply imperfection
to **decision-making**: the line has a destination, momentum, and a correction
behavior, and the wobble is evidence of a control loop struggling — not noise
added afterward. Uncanniness lives in *intention imperfectly executed* and in
*near-order*, not in randomness.

Rule of thumb for every idea here: **perturb the controller, not the output.**

References worth pulling before implementing: Harold Cohen's essays ("What is
an image?"; the AARON papers document his closure and core-figure algorithms
well enough to reimplement), Stiny's shape grammars for §4.

## Cross-cutting moves (multiply everything below)

- **Style genome.** Drive every micro-decision (curvature preference,
  pen-lift frequency, overshoot tendency, correction gain) from one small
  bounded vector, so different seeds feel like different *people*, not
  different noise. The tween machinery then does something conceptually
  interesting for free: interpolating two genomes = morphing between two
  hands. Candidate for a global store like the pen library (see UI section).
- **Build §1 first.** The intentional-line controller is the shared
  substrate — §2, §3, §5, §6 all want their strokes executed through it, and
  as an *effect* it retrofits uncanniness onto the entire existing source
  library before any new source is written.

## 1. The intentional line (Cohen kernel) — as an effect — **shipped July 2026**

Shipped as `effects/freehand.py` (`id: freehand`): eye-leads-hand pursuit with
a clamped semi-implicit spring-damper, steering-space tremor, per-stroke
fatigue, and drawn-then-snapped closure. Params match the sketch below
(`confidence`/`correction`/`impulsiveness`/`tremor`/`fatigue`, with
step + seed under a collapsed "Fine tuning" group per UI principle 1).
Original sketch kept for the rationale:

Pen as an under-damped steering agent: knows where it wants to go, corrects
with finite gain, overshoots, accumulates fatigue (error grows with path
length since last pen lift), occasionally recommits to a new local target.

- **Params:** `impulsiveness`, `correction_gain`, `fatigue_rate`,
  `confidence` (lookahead distance). All bounded, all tweenable.
- **Why an effect, not a source:** it takes the resolved paths of any layer
  as *intentions* and redraws them freehand. A grid drawn by something trying
  its best to draw a grid beats a jittered grid, because errors are
  correlated the way human errors are: corners overshoot, long lines drift
  then correct, closure points miss and get patched.
- **Invariants:** pure (reads input paths, emits new ones). Preserve
  `filled` + closure by making the controller *seek* the start point at the
  end — visible correction and all. Effects run in paper space, so the hand's
  mm-scale tremor stays physical at any layer scale.
- **UI load:** low — 4-6 sliders, standard auto-form.

## 2. Rehearsal / pentimento

Draw the figure, then draw it *again* — each pass a re-estimate of the
previous attempt, converging toward an ideal never stated. Ghost passes plus
a committed final stroke, like construction lines under a figure drawing.

- **Params:** rehearsal count, `self_trust` (copy previous pass vs. original
  intention), per-pass pen assignment.
- **Fit:** maps directly onto per-pen passes — rehearsals in 6B pencil,
  final stroke in ink. Visible machine self-revision reads as doubt, which is
  deeply un-plotter-like.
- **UI load:** medium — per-pass configuration wants a small list UI, not a
  flat param panel (see UI section).

## 3. Misremembered image — **shipped July 2026**

Shipped as `sources/misremembered.py` (`id: misremembered`, Pi run): blob
phase on the dark masses first (amoebas probed from a pooled-darkness
field), then greedy streamline strokes along the gradient field, recall
threshold relaxing as strong structure runs out; confidence → firm drifting
polyline vs. short broken searching fragments. `budget` is the dial and is
tweenable. Original sketch:

Not thresholding/hatching (already have those) but lossy *recall*: sample the
image sparsely, fit a small budget of primitives (long arcs, straight
strokes, a few closed blobs), draw the reconstruction. Per-primitive
confidence controls line character — confident regions get one firm stroke
through the §1 controller; uncertain regions get short, tentative, searching
marks. Recognizable but wrong the way memory is wrong: big masses right,
details confabulated.

- **Key param:** the primitive budget. 40 strokes vs. 400 is the dial
  between "dream of a face" and "portrait". Tweenable → an animation can
  literally *remember harder* over master_t.
- **Fit:** existing asset store (`format: "asset"` param), existing image
  pipeline in `image_processing.py`.
- **UI load:** low-medium — one asset dropdown, budget slider, a few
  confidence-shaping params.

## 4. Grammar with a transgression budget — **shipped July 2026**

Shipped as `sources/grammar.py` (`id: grammar`, Pi run): three built-in
grammars (branching / band frieze / radial rosette) authored in cubic
bézier space, flattened only at output; violations are rule-aware affines
on placed motifs (rotate off-true, scale off-module, vocabulary swap),
spent at salient sites with a size discount so each one stays perceptible.
No rule editor, per UI principle 5. Original sketch:

A shape grammar (Stiny-style rewrite rules) that obeys itself almost
everywhere — but carries a budget of deliberate violations, spent at
*salient* locations: on symmetry axes, at the center of mass, at the rule
application that would have completed a pattern. Near-order is the uncanny
valley of pattern: a grid perfect except one cell rotated 3° isn't glitch
aesthetics, it's a wrongness you feel before you can point at it. Violations
are rule-aware (the generator knows what it breaks), not noise-driven.

- **Params:** transgression budget, salience bias, violation magnitude,
  grammar preset.
- **UI load:** depends entirely on how rules are authored. Start with a
  handful of built-in grammars behind an enum; a rule *editor* is a separate
  project and probably a trap (see UI section).

## 5. Two hands negotiating — **shipped July 2026**

Shipped as `sources/two_hands.py` (`id: two_hands`, Pi run): perceive →
respond (echo / complete / contradict per `agreeableness`, focus per
`attention`) → mark in a bounded per-agent genome (grouped `Agent A`/`B`
params — UI principle 1, not the preset store yet). The `draw` enum is a
pure filter over one deterministic conversation, so two layers + two pens
give the physical negotiation. Original sketch:

Two line-agents with different style genomes take turns marking the page,
each responding to the other's last stroke — completing, echoing,
contradicting, avoiding. Drawing as conversation (close to how Cohen
described AARON's feedback loop).

- **Params:** per-agent genome, `agreeableness` (imitate vs. oppose),
  `attention` (respond to recent strokes vs. whole page), turn length,
  rounds.
- **Fit:** per-pen passes give each agent its own physical pen, so the
  negotiation is legible on paper. Strongest "machine creativity" candidate:
  composition genuinely emerges from the interaction.
- **UI load:** high — two genomes plus interaction params is a wall of
  sliders in a flat panel. Wants genome presets + grouped/collapsed advanced
  params, and ideally a step/replay affordance (see UI section).

## 6. Blind contour machine

The generator perceives a source image (or another layer's geometry) through
a small foveal window moving along edges, and draws continuously without
lifting — but the pen *lags* the eye and never gets visual feedback, exactly
like blind contour drawing exercises. Eye path faithful; hand path drifts,
and drift compounds.

- **Params:** fovea size, hand lag, drift rate, optional "glances" (brief
  re-registrations to truth).
- **Why:** blind contours of faces are the single most reliably uncanny
  drawing genre humans produce — topology right, metric wrong. Nobody's
  plotter does this.
- **UI load:** low — asset dropdown + 4 sliders.

## 7. Phase-transition field

One lattice, one physical process, crossing its critical point *across the
page*: an Ising/annealing system with spatially varying temperature — one
edge crystalline order, the other melt, and the artwork is the transition
band where structure is deciding whether to exist. Liminal in the literal
sense: the threshold region is the subject.

- **Params:** critical band position + width, coupling anisotropy, seed.
- **Fit:** natural animation piece — master_t = annealing time; a 16-frame
  grid sheet shows the same lattice freezing.
- **UI load:** low — but simulation cost may want a resolution/quality param
  and a visible "computing…" state (resolve is currently synchronous).

## UI: how the involved ones should land without cramming the panel

The Compose tab is already a wall (ROADMAP near-term section says the same).
Principles for these modules, cheapest first — all keep the zero-build setup:

1. **Use the `group` hook that already exists.** `forms.js` renders fields
   tagged `json_schema_extra={"group": "..."}` into a collapsed `<details>`.
   Every module above should ship with 2-4 *headline* params visible and the
   rest under groups like "hand", "memory", "advanced". This is a convention
   to adopt, not code to write — document it in docs/MODULES.md when the
   first of these ships.
2. **Presets over parameters.** For genome-sized param spaces (§1, §5), the
   user-facing unit should be a named preset ("nervous", "confident",
   "tired"), with the raw vector under a collapsed group. Presets could be a
   small global JSON store like the pen library (`stores.py` pattern) so
   hands are reusable across projects — "draw this with the same hand as
   last week".
3. **Seed + reroll as a first-class affordance.** These generators are
   variation machines; the workflow is *reroll until it surprises you*. A
   tiny 🎲 button next to seed fields (forms.js, one generic addition keyed
   on a `format: "seed"` extra) pays for itself across every stochastic
   module, existing ones included.
4. **Popup workbench, not new tabs.** For the genuinely process-like modules
   (§2's passes, §5's turn-taking), follow the animation-preview-popup
   precedent rather than adding tabs: a modal per module that shows the
   process (step through negotiation rounds, toggle rehearsal ghosts) while
   the layer panel stays a compact summary. Tabs are global navigation;
   these are per-layer inspections. User direction (July 2026): this popup
   should grow toward a *generator workbench* — generate, reroll, and **save
   the results as project assets**, eventually with light editing of those
   generated assets. That makes expensive/stochastic generators feel like a
   darkroom (contact sheet → pick → keep) instead of a slider panel, and it
   composes with the existing staging tray rather than replacing it.
5. **Don't build editors.** No grammar editor (§4), no genome curve editor.
   Built-in enums/presets first; an editor is only worth it once a preset
   list demonstrably can't hold the interesting space.

None of this blocks the algorithms: §1, §3, §6, §7 fit today's auto-form
fine. Only §5 (and §2's per-pass list) genuinely *needs* UI thought before
it ships.
