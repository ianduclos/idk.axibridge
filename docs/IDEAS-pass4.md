# Idea pass 4 — something at stake, and lines out of fields (August 2026)

Loose brainstorm, 2026-08-18. Not commitments — ROADMAP.md carries conviction
ordering. Passes 1–3 are `IDEAS-generators.md` (Cohen / uncanny),
`IDEAS-oehlen-pass.md` (regime collision) and `IDEAS-aaron-pass.md` (AARON's
mechanisms).

The conceptual material from this pass was harvested into the vault as atomic
notes (`llm/proposed/`, 2026-08-18) — *Why Computational Art Looks
Computational*, *Cybernetic Mechanisms as Drawing Rules* and its three
children, *Optimal Transport as a Blending Primitive*, *Wasserstein
Barycenters*, *Prediction Error as the Visible Signal*, *Lines From Fields* and
its children, *Hachures*, *Eigenfunction Nodal Lines*. Those hold the *why*.
This doc holds what would be built here.

## The framing

Passes 1–3 all ask the same question in different accents: **what should the
marks look like?** Cohen's controller, Oehlen's colliding regimes, AARON's
cognitive mechanisms. That axis is well mined.

The diagnosis that opened this pass is different. Computational art gives
itself away through seven properties — uniform rules across the field, no
privileged location, self-similarity across scale, one global state computed in
one instant, no history, no cost, smooth parameter continuity. Underneath all
seven is one thing:

> **Idiomatic computational art has nothing at stake.** Nothing can go wrong
> for the system, so nothing it does reads as a decision.

Cohen got at this without naming it — his line has *fatigue*, which is history
and cost at once. Oehlen collided regimes but never motivated why a regime
should change.

Two answers, and this pass has a half for each.

**Half A — give the process something to lose.** Cybernetics is exactly the
study of systems with an essential variable and a viable range. Build the loop
and most of the seven properties break on their own.

**Half B — let the field carry the structure.** If the rule is uniform but the
*field* it reads is not, you get non-uniform output without faking it. And in
every technique here the interesting places are where the field misbehaves —
singularities, saddle points, extremes of a metric — which is the opposite of
the usual instinct to smooth until it looks clean.

The halves are complementary, not competing: A makes the process interesting,
B makes what it draws with interesting.

## Half A — something at stake

### A1. Time as a param, plus a live popup (the substrate) — SHIPPED 2026-08-21

`axibridge/process.py` + `axibridge/trajectory.py` + `axibridge/sources/
venation.py` + `static/js/process.js`. Full ledger and defect list:
`docs/plans/time-as-a-param-RESULTS.md`. One thing this sketch got wrong,
in the good direction: it assumed the master-timeline binding needed
building. It didn't — `Session._effective_gen_params` already folded
`master_t` into a generator's `frame` field, so A1 turned out to be a
*generalisation of one existing method*, not new plumbing, and the frame
path stayed byte-identical throughout. And the second argument for A1
below (pentimento) paid out further than expected: because the trajectory
cache keys on every param except the time axis, `Rehearse` gets N moments
of a process for the cost of ONE run, not N — a consequence of the cache
design colliding productively with a problem neither task set out to
solve together.

Ian, 2026-08-18: *"many algos can occur in time; current ones are more
instant/parametric… a new sort of generator type that opens a popup where we can
visualize the live drawing and development, and even interact with it."*

Almost everything else in Half A is a process that unfolds, and you cannot tune
a homeostat you cannot watch. This is the enabling round.

**The move that keeps the invariants:** treat time as a param. `generate()`
stays pure and returns the state at step *N*, where *N* is an ordinary bounded
field. Then:

- the popup scrubs and plays *N*, so growth is watchable;
- **interaction writes events into a hidden params list** — "at step 340 the
  user pushed here" — exactly the geometry-as-params pattern `drawing.py`,
  `pen.py` and `brush.py` already use. A live session becomes a **recorded
  score** stored in the layer, so it stays pure, reproducible, undoable and
  tweenable;
- `master_t` already exists, so binding step-count to the master timeline makes
  **the growth an animation for free**.

Honest cost: state at step *N* may mean running 0..*N*. `gencache` absorbs the
repeat and periodic checkpoints cap it, but a slow process will feel slow. The
popup precedent is the render popup (top-level markup, opens over any tab).

**This is not a revival of the workbench** (removed July 2026). The workbench
was a stateless recipe playground beside the project; this is a per-layer
inspector for layers that genuinely have a time axis.

### A2. Homeostat generator — regime collision with a reason

The most expansive single idea in the pass. Ashby's homeostat held equilibrium
and, pushed outside its viable range, **randomly rewired itself** until it found
a configuration that worked. Blindly — it rerolls, it does not reason.

As a signal flow: measure the drawing so far → is it in range? → if not,
sample-and-hold random → swap the **rule set** → keep drawing → re-measure.

The hack surface, roughly in order of how much it changes the result:

- **what you measure** (ink density, crossing count, unmarked-area fraction,
  stroke-length variance) — the biggest lever by far
- **range width** — narrow gives constant crisis and visible thrash; wide gives
  long stable passages punctuated by lurches
- **reroll scope** — one param, a whole rule set, or the generator itself
- **local vs global** — per region gives patches of regime rather than eras
- **memory** — Ashby deliberately had none. Adding it makes the system converge,
  and converged is another word for finished. Worth having as a slider *so you
  can watch it die*.

Why it matters here: this is Oehlen's regime collision **motivated**. The seam
lands where the system was in trouble, which is a reason the sheet can show.

### A3. Prediction error as an effect — the sensor

Two processes: one draws, the other predicts what it will draw next; only the
error is inked. Regularity cannot survive, because predictable means unmarked —
a grid draws once and vanishes as the predictor learns it. Symmetry erases
itself.

**Build it as an effect first**, for the same reason `freehand` is one: it
retrofits onto every existing source before a single new generator is written.

The minimal loop is genuinely ~30 lines — walk the path, keep a running
prediction of the next `(turn, length)` from exponentially-weighted history,
`error = actual − predicted`, update toward actual with gain α, modulate pen
width / presence / channel by `|error|`. `continue_strokes` is the ancestor
(order-N Markov on turning angles).

Two knobs matter more than the algorithm: **learning rate = how easily bored**,
and **two timescales beat one** (ink where a fast and a slow predictor
*disagree*, not where either is wrong against truth).

**The convergence worth building toward:** if ink is error and error falls as
the predictor learns, the drawing dies out. The fix is either a leaky predictor
or a drawer that hunts for what the predictor cannot guess — and **a drawer
adversarial to its own predictor is Pask's boredom.** A3 and the habituation
mechanic are one machine seen from two ends.

### A4. The seam — locally perfect, globally wrong

Grow from two or more independent seeds with identical local rules and **no
awareness of each other**. Where the fronts meet they cannot line up — spacing
out of phase, contours arriving at incompatible angles. Draw the failure to
reconcile rather than blending it away.

How it differs from what exists: `continue_strokes` extends one stroke's
statistics (1D, nothing ever meets); `two_hands` has two agents but they
*negotiate*; `region_boundary: continuous` **stitches** across a seam — this is
its exact aesthetic inverse.

The sibling idea is the global-count one: enforce local rules flawlessly and
keep **no global bookkeeping at all** — no closure check, no count, no symmetry
constraint. Every joint correct, six of them.

Ian, 2026-08-18: *"we already tried some of these, they don't really hit the
spot but they're a good start and we should iterate."* Treat as a direction to
return to with A1 in hand, not a spec.

### A5. Habituation — the machine that gets bored

Pask's **Musicolour** (1953) drove a light show from a musician's playing and
**became bored**: fed a repeating figure it stopped responding, forcing the
performer to find something new. The machine's unresponsiveness was the
instruction.

As a rule: keep a record of what has already been drawn, and make the system
progressively **less willing** to draw more of the same. Not novelty as noise —
a memory that actively suppresses self-similarity. The process is then driven
by what it has *not* done rather than by a target, so its output is uneven
because it is hunting.

Underneath is Pask's **requisite variety**: a controller needs at least as much
variety as what it regulates. Boredom is what a system does when the variety it
is being fed drops below what it needs.

**Build it with A3, not after it.** A predictor that learns *is* the habituating
memory; a drawer hunting for prediction error *is* the novelty drive. They are
one machine from two ends, and A3's known failure mode (ink is error, error
decays, the drawing dies out) is fixed by exactly this. Shipping A3 without it
means shipping the failure mode.

### A6. The descent, not the destination

Diffusion's actual mechanic is: start from noise, iteratively pull toward a
manifold. You cannot run a model in the resolve path, but the *structure* is
hand-writable with a crafted score function — and the interesting output is not
the converged result but **the intermediate states, drawn as ghost passes**.

This turns out to be the same thing as pass 1's §2 (rehearsal / pentimento,
**shipped August 2026** as `Session.rehearse_layer` — see
`docs/IDEAS-generators.md` §2 and `docs/plans/time-as-a-param-RESULTS.md`):
draw the figure, then draw it again, each pass a re-estimate of the last,
converging toward an ideal never stated. Construction lines under a figure
drawing. Visible machine self-revision, which reads as doubt. A6 itself (the
score-function generator whose intermediate states would be drawn this way)
remains unbuilt — what shipped is the layer-level sweep machinery A6 would
ride on, not A6.

**A1 delivered exactly this, and generally so.** Once time is a param, "draw
several moments of the same process on one sheet" is a *layer-level*
operation — the sweep machinery pointed at the time axis — rather than a
feature each generator has to implement. Every time-based generator gets
pentimento at once, with per-pass pen assignment falling out of the existing
multi-pen path (rehearsals in pencil, the committed stroke in ink) — modulo
the ruling that shipped `Rehearse` actually made: moments are independent
live layers with the source layer's effect stack copied on, not a tween you
can re-tune, since the trajectory cache already makes cheap re-runs the
mitigation.

That was a strong second argument for A1: it did not just enable Half A, it
retroactively shipped a pass-1 idea that had been open since July. A6's own
diffusion-mechanic generator is still open.

### A7. Algedonic marks (small)

In Beer's Viable System Model an **algedonic** signal bypasses the hierarchy —
when something is bad enough it goes straight to the top rather than being
filtered and summarised at each level.

A composition normally negotiates: everything placed relates to what is already
there. An algedonic channel is the exception — a mark placed *without regard to*
the composition because some measured quantity went critical. Not contrast for
its own sake; indifference with a cause, which reads differently and is harder
to fake.

The smallest item in the pass and the easiest to bolt onto anything with a
measure already: one monitored quantity, one threshold, one kind of mark that
does not ask permission. Pairs naturally with A2, which is the *other* response
to a variable leaving its range — Ashby changes the rules, Beer raises the
alarm.

## Half B — lines out of fields

### B1. Geodesics on the Eikonal solver

`_fast_marching.py` already solves for travel time under a spatially varying
speed function — which *is* a Riemannian metric. Today only its level sets are
traced (iso-time contours). The **orthogonal trajectories** of those contours
are the paths the wavefront travelled, and they read as *navigation* — as
something choosing a route — which is a markedly different impression from a
flow field.

Same solved field, two completely different pictures. The shortest hop in the
whole pass.

### B2. Eigenfunction fill — SHIPPED 2026-08-21

`effects/eigen_fill.py` + `effects/_eigenmode.py`. Both lifts below are
in it, and the honesty clause is stated in the module docstring: it is a
clamped membrane, not a free plate. One thing the sketch below did not
anticipate — a degenerate group needs a *canonical* basis or the default
picture is an accidental superposition and the mix knob changes meaning
whenever the shape is nudged; least-nodal-length settles it.

Chladni figures as a **fill primitive** rather than a generator, which is the
better idea: the nodal pattern is determined by the boundary of the shape being
filled, so the fill is *produced by the form* instead of laid over it. Every
shape gives a genuinely different pattern, and the mode index is a single
control that changes density **and character** together — unlike hatch spacing,
which only changes density.

Route: rasterise the shape → discrete Laplacian on the interior → `scipy.sparse.
linalg.eigsh` for the k-th eigenvector → marching squares on its zero level set.
Marching squares already exists in `image_threshold`; scipy is already a
dependency.

Two things that lift it past the obvious version:

- **Degenerate modes.** Symmetric domains have repeated eigenvalues, and any
  combination of the eigenfunctions at that frequency is also a mode — which is
  physically why a square plate gives stars and flowers rather than one figure.
  The control is not only *which mode* but *how the degenerate ones mix*.
- **High modes on irregular boundaries.** Nodal lines start to look like a
  random wave field (Berry's conjecture, the quantum-chaos regime): tangled,
  organic, unrepeating, and **entirely determined by the boundary**. Looks like
  noise, is pure structure.

Honesty: the easy version (Laplacian, clamped edge) is a *membrane*, not a
plate. Real Chladni is free-edge and biharmonic — different patterns, harder
problem. Both are worth having; know which is on screen.

Nodal lines are generically smooth, non-crossing, and either closed or ending on
the boundary — unusually well-behaved to plot, and likely fewer pen lifts than
hatching.

### B3. Hachures

Lehmann's system (~1799): short strokes running down the slope, **steeper ground
darker**, by making strokes thicker and closer. A complete, century-refined
grammar for rendering form with lines, abandoned when contours won on
*measurability* rather than on looks. Almost nobody's eye is tired of it.

Unlike hatching, which lays down a direction the artist chose, hachures derive
both direction and weight from the surface. Any field with a gradient supplies
what it needs — and there are already depth maps, `_lineart.flow_field`, and
Depth Pro in the venv.

### B4. Stripe patterns and phase fields

Evenly spaced lines following a direction field. The naive version (integrate
the field, take level sets of its cosine) works in smooth regions and **breaks
exactly at the singularities** — which are the interesting bits. Those defects
are topologically forced, not numerical failures, and they are where the visual
event is.

Knöppel, Crane, Pinkall & Schröder, *Stripe Patterns on Surfaces* (SIGGRAPH
2015) synthesises stripes at a specified orientation *and* spacing, inserting
the singularities needed to make both compatible, as the minimiser of a
convex-quadratic energy.

A **parallel branch** by Ian's own reading — it ties to his separate plan for a
basic 3D engine. The 2D case is simpler and `flow_field` already supplies the
direction field, so a cheap version is available to test the look first.

### B5. Curve-shortening flow

Any closed curve evolved by its own curvature becomes a circle. Run it partially,
anisotropically, or on a family, and you get deformations with a real physical
logic. Small, self-contained, elegant, and almost absent from generative work.

Its second use is as a **correspondence mechanism**: A → circle → B, with the
circle as a normal form, so two curves relate through it without any assignment
problem. Running it backwards is unstable (backward heat equation) — run it
forward on both and play one trajectory in reverse.

## Half C — the blending axis (adjacent, and the one Ian reacted hardest to)

Not a mark-making idea; an extension of what the tween machinery already does,
and by Ian's own reading the strongest part of the suite already. The limitation
is precise: **param blending can only explore the space its generator already
spans, and cannot leave it.**

### C1. Optimal-transport blending

Correspondence-free morphing. Treat each drawing as a set of strokes with
descriptors and solve for the cheapest matching — `scipy.optimize.
linear_sum_assignment` is already available. Unmatched strokes shrink to a point
or grow from one.

**The property that matters for a plotter: a linear blend crossfades, optimal
transport makes mass travel.** With no opacity available, a crossfade is
meaningless and travel is the only interpolation that can be drawn.

Sinkhorn is the soft version, and its regularisation ε is a genuine expressive
control — crisp one-to-one at low ε, diffuse and smearing at high. Sliced OT
(project to 1D, sort, average over directions) is the twenty-line approximation.

Token level keeps a stroke a stroke; density level blends smoothly but returns
*outlines of lines* rather than lines. A third path worth trying because it is
nearly free: rasterise → density barycenter → **skeletonise** (Zhang–Suen is
already in `_lineart.py`) → trace.

**Extend `tween.py`'s shared blend core — never re-fork it** (MODULES.md, and
the 2026-07-19 unification exists to prevent exactly that).

### C2. Wasserstein barycenters

The generalisation past two endpoints: N drawings, N weights, drag around inside
the simplex. Multiparameter interpolation of the kind Ian already works with in
Max, except the corners are whole drawings rather than parameter sets. Solomon
et al., *Convolutional Wasserstein Distances* (SIGGRAPH 2015), has reference
code.

This is the direct answer to the "two generations make some lines, explore the
latent space to reach the middle ground" wish — and the honest caveat is that
**plausible midpoints need a manifold**, which is what a rich process-like
generator supplies. So C2's ceiling rises with A1 and A2.

## Where to start (recommendation, 2026-08-18)

ROADMAP's rounds are ordered by dependency and cost. The recommendation argues
partly *against* that ordering, so it is recorded here rather than left implicit.

**Do B1 (geodesics) as a one-afternoon warm-up, then go straight at A1.**

B1 reuses the Eikonal solver that already exists — it traces the orthogonal
family of contours already being traced — so it is nearly free and it proves
whether the field-derived direction is worth the other two Round 1 items.

Then jump the queue to A1, for two reasons:

- **A1 is the only item in the pass that changes what is *possible* rather than
  what is *available*.** Round 1's items are excellent new textures, but they
  are textures: more things to draw with, the same kinds of drawings. Everything
  in Half A is downstream of A1.
- **Substrate rounds deferred behind cheap wins stay deferred**, because there
  is always another cheap win. B2 and B3 are independent by construction, so
  nothing is lost by taking them after — and they will be easier to tune with
  the popup in hand.

### Two design risks in A1, to settle before writing code

Neither is a coding problem; both could send the design back a step.

1. **O(N) replay.** State at step *N* may mean running steps 0..*N*. `gencache`
   absorbs repeats and periodic checkpointing caps the cost, but a genuinely
   slow process will still feel slow to scrub. Mitigable, not eliminable —
   decide what the acceptable ceiling is before building around it.
2. **Interaction-as-recorded-score may feel like fighting a tape.** Writing
   "at step 340 the user pushed here" into a hidden params list is what keeps
   the layer pure, reproducible and tweenable — the whole architectural win.
   But it makes live pokes *edits to a score* rather than direct manipulation,
   and scrubbing back to poke again means inserting into history. Whether that
   reads as expressive or as fussy is a bench question, and it is the single
   most likely thing to force a redesign. Worth a throwaway probe before
   committing to the model.

## Deliberately not in this pass

- **A 3D engine.** Ian has a separate plan; B4 touches it, nothing here depends
  on it.
- **The generator corpus map** (descriptors → dimensionality reduction → a 2D
  map you navigate, FluCoMa-style but over generator outputs). A real idea,
  parked — it belongs with the module gallery, not here.
- **diffvg / CLIPasso.** Genuinely wanted (Ian: *"I need this ASAP"*) but it is
  a heavy dependency with a historically fiddly build, and the 80% version —
  **greedy residual stroke fitting**, "place the stroke that most reduces the
  error, repeat" — is ~100 lines, needs nothing, is fully deterministic, and
  delivers the structural point (marks that cost something and must earn their
  place). Spike the greedy version first; it may make the build fight
  unnecessary. Both bookmarked in the vault.
