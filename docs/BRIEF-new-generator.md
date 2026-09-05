# Brief: build a new generator for axibridge

You are being asked to design and build **one new drawing generator** for a pen
plotter, inside an existing Python codebase, and to push the underlying idea
further than the people who wrote this brief managed to.

Read the whole thing before proposing anything. The last two sections — the
critique and the traps — are the ones that will decide whether what you build
is any good, and they are the ones a first read tends to skim.

---

## 1. The medium, which is not a screen

An **AxiDraw V3**: one pen, held by a machine, dragged across paper. This is the
entire output. It has consequences that invalidate most generative-art
instincts:

- **No opacity, no colour blending, no fills.** A region is dark because more
  line went there. Tone is density; there is no other channel.
- **A pen lift is visible and slow.** A drawing made of ten thousand
  disconnected two-point segments takes an hour of the machine going up-down
  and looks like static. Continuous strokes are both faster and better.
- **The paper is 300 × 218 mm**, coordinates are millimetres in the machine
  frame (x right, y down, origin at the carriage home corner).
- **Line weight is fixed per pen.** Variation comes from overdrawing, spacing,
  or swapping pens between passes — not from a width parameter.
- **Every mark is permanent.** There is no erase, no undo on paper, no layer
  opacity to hide a mistake behind.

Design for the machine's honesty. Anything that would look identical as a PNG is
not using the medium.

---

## 2. Ian's aesthetic vector, as operational criteria

Stated as things a reviewer could check, because "make it beautiful" is not a
brief. These come from two years of this project and several hundred plotted
sheets.

**Wanted:**

1. **Continuous, coherent lines that follow a structure.** A line that goes
   somewhere for a reason. Growth, navigation, a hand tracking a surface.
2. **Marks that read as decisions.** The eye should be able to ask "why did it
   do that there?" and feel that there is an answer, even without knowing it.
3. **Non-uniformity that comes from the process**, not from a noise parameter.
   Dense here and empty there because something happened, not because a random
   field said so.
4. **The uncanny.** Something not-quite-right, near-figurative, almost-familiar.
   Cohen's *AARON*, Albert Oehlen's regime collisions, Sol LeWitt's instruction
   drawings executed by a hand that gets tired.
5. **Legible history.** A drawing that shows it was made over time, in an order,
   with revisions — pentimento, construction lines, second thoughts.

**Rejected, explicitly and repeatedly:**

- **Scatter.** Point clouds, stipples, uniform hatching over an image, anything
  where the mark is a sample rather than a stroke.
- **Blobs.** Uniform texture that fills a region evenly. If it reads as a fill
  pattern, it is dead.
- **Idiomatic computational art.** The diagnosis this project works from: such
  work gives itself away through *uniform rules across the field, no privileged
  location, self-similarity across scale, one global state computed in one
  instant, no history, no cost, smooth parameter continuity.* Underneath all
  seven is one thing — **nothing is at stake.** Nothing can go wrong for the
  system, so nothing it does reads as a decision.
- **Prettiness that a parameter sweep would also produce.** If turning a knob
  moves smoothly through a family of equally-good pictures, none of them is a
  picture.

**The house style for the code:** dry, specific comments that say *why*, never
*what*. No emoji in the UI. Every numeric parameter bounded, because unbounded
values reach an open-loop machine that will drive a pen into the frame.

---

## 3. The machine you are building into

The codebase is `axibridge`: FastAPI + Pydantic v2 server, vanilla ES-module
frontend, a layer compositor. You add a **source module** — one file dropped
into `axibridge/sources/`, registered with a decorator, and it appears in the UI
with auto-generated controls.

**The non-negotiable contract:**

```python
@register_source
class MyThing(SourceModule):
    id = "mything"                # stable; stored in saved project files
    label = "My thing"
    description = "One line, shown in the UI."
    orientation = "geometry"      # or "none" / "param" — see registry.py
    Params = MyThingParams        # a pydantic BaseModel

    def generate(self, params: MyThingParams) -> PathDocument:
        ...
```

`generate()` **must be a pure function of its params.** Everything downstream —
a content-keyed memo, parameter interpolation for animation, undo, the time
estimator, the plotter itself — holds only because of this. A generator that
carries live mutable state between calls would need a second geometry path into
the plotter, which the project forbids.

Params are a Pydantic model whose JSON Schema renders the UI automatically.
Every numeric field needs `ge`/`le`. Titles and descriptions become labels and
tooltips, so write them for a person at the machine.

### Processes that unfold, and the bench

If your generator is a **process** — something that grows, searches, or holds
itself in equilibrium — subclass `ProcessModule` instead, and **time becomes an
ordinary bounded parameter**:

```python
class MyProcess(ProcessModule):
    time_axis = "steps"     # the name of a bounded int param
    accumulative = True     # each Step ADDS marks; state at N is the prefix 0..N

    def run(self, params) -> Iterator[Step]:
        while True:                      # the param bounds the run, not you
            yield Step(paths=[...],      # the marks added THIS step
                       telemetry={...})  # any floats worth plotting against time
```

`generate()` is then provided for you: it asks a cache for the state at step N.
The process is **replayed, never held**.

Declaring a `time_axis` buys the UI for free and you cannot opt out:

- a **▷ Bench** button that opens the generator's own controls beside a stage
  that plays and scrubs the axis, so you can tune the thing with its growth on
  screen and create the layer at the step you like;
- **▷ Watch** and **Rehearse** on a committed layer (Rehearse stamps several
  moments of one process onto the sheet — pentimento, nearly free, because the
  whole trajectory is cached);
- **telemetry plotted under the stage.** This matters more than it sounds. If
  your process has an internal state worth watching — an error, a population, a
  variable in trouble — emit it and you can see it hunt.

Give the time axis a tight `ge`/`le`: those bounds become the scrub range.

---

## 4. What already exists — do not rebuild these

- **`venation`** — space-colonisation growth. Branching lines toward scattered
  attractors. The first process module.
- **`homeostat`** — the one this brief is a reaction to; described below.
- ~30 other sources: flow fields, hatching from images, Hershey text, L-system
  grammars, drawing/pen capture tools, superformula curves, contour tracing from
  a fast-marching Eikonal solver, an eigenfunction (cymatic) fill.
- An effect stack per layer (pure functions, paper-space), occlusion masking,
  region layers that reshape what is below them, parameter tweening, a master
  timeline, multi-pen passes.

**The homeostat, in detail, because your job is to beat it.** Ashby's homeostat
as a generator: a pen wanders; an *essential variable* is measured against a
viable range; when it sits outside that range for N consecutive steps the pen's
**genome is rerolled blindly** — no gradient, no search, no memory of what
failed. The genome is its handwriting: turn bias, wander, persistence, dwell,
step scale. Four selectable variables: `crowding` (local ink density),
`coverage` (global), `tangle` (retracing), and `surprise` (the pen's own
prediction error about its own next turn, from two exponentially-weighted
timescales — so *becoming predictable is itself a crisis*). Optional second-order
loop: a reroll that **failed** widens the space the next hand is drawn from, a
long viable passage narrows it — the Law of Requisite Variety, giving the
drawing an arc. Optional 1–6 coupled units sharing one occupancy grid, with no
concept of each other, meeting only in the ink.

It works. It is also, honestly, **not enough**, and section 6 is why.

---

## 5. What we learned building it — the ideas ledger

Pass 4 of this project's idea-generation asked: what would make computational
art have something at stake? Two halves.

**Half A — give the process something to lose.** Shipped: time as a parameter
(the substrate above); the homeostat. Still open: *prediction error as an
effect*; *habituation* (Pask's Musicolour became **bored** when fed a repeating
figure and stopped responding — the machine's unresponsiveness was the
instruction); *the seam* (independent fronts with identical local rules and no
awareness of each other, drawing the failure to reconcile); *the descent* (start
from noise, iteratively pull toward a manifold, and draw the **intermediate
states** rather than the converged result); *algedonic marks* (Beer's VSM — when
something goes critical, a signal bypasses the hierarchy: a mark placed
**without regard to** the composition, indifference with a cause).

**Half B — let the field carry the structure.** If the rule is uniform but the
*field* it reads is not, you get non-uniform output without faking it. Shipped:
eigenfunction nodal lines. Open: *geodesics* (trace the orthogonal trajectories
of iso-time contours — lines that read as navigation, not as flow); *hachures*
(Lehmann's slope-proportional stroke system); *optimal transport* as a blending
primitive (a linear blend crossfades; OT makes mass **travel**, and with no
opacity available travel is the only interpolation a pen can draw).

In every technique here **the interesting places are where the field
misbehaves** — singularities, saddles, extremes — which is the opposite of the
usual instinct to smooth until it looks clean.

---

## 6. The critique — why the homeostat is not enough

This is the part to argue with. Six criticisms of our own work, in the order we
think they matter.

**1. Every variable it can measure is a first-order statistic of ink.**
Crowding, coverage and tangle are *how much stuff is where*. Even `surprise`,
which felt like a leap, is a statistic of the turn sequence. None of them is
about **relationships between marks** — parallelism, enclosure, alignment,
rhyme, echo, interval. But relationships are what make a drawing read as
*drawn* rather than as deposited. A system that cannot perceive that two strokes
are parallel cannot decide to make a third one parallel, or pointedly not.
**The single biggest opening: give the process a vocabulary of relations, and a
stake in them.**

**2. It has a life but no eye.** Ashby gives it something to lose; nothing gives
it a view of the page. There is no figure and ground, no focal point, no scale
hierarchy, no sense that a drawing has a *subject* and a *periphery*. The
compositions that work are lucky. A drawing that knows only "am I crowded here"
composes at the scale of the pen tip and never at the scale of the sheet.

**3. Nothing costs anything.** Cohen's line has *fatigue*, which is history and
cost in one gesture. Our pen can travel forever at no price. Give it a budget —
ink, distance, time, patience — and every mark becomes a decision made against
something. Cost also produces the arc that "no history" names as a giveaway:
early marks made cheaply, late marks made expensively, and the difference
visible.

**4. It has no memory of shapes, only of statistics.** It cannot recognise that
it has drawn this before, only that the area is dense. Real habituation — Pask's
boredom — needs a memory of *forms*, so that a repeated form stops earning a
response. This is also what would let a drawing *rhyme*: repeat a shape
deliberately, at another scale, in another place.

**5. The boundary is outside the loop.** The sheet edge is a hard rule the pen
obeys rather than a condition it experiences. It produces the most regular,
most predictable passages in the whole drawing — long scalloped runs along the
edge — which is embarrassing in a machine whose premise is hunting
unpredictability. Anything the system merely *obeys* will show up as the dullest
part of the picture. Look for the other rules you are tempted to hard-code and
put them inside the loop instead.

**6. Blind rerolling is honest but coarse.** Ashby's point was that the machine
does not reason, and we kept that. But the *consequence* is that a seam is a
discontinuity in statistics, and the eye barely registers it — the knots and
travels read, the transitions do not. The seam is supposed to be "a reason the
sheet can show", and it isn't showing. Either make the crisis leave a mark of a
different kind, or make what changes at a reroll something the eye tracks
(direction, scale, density regime) rather than a five-number genome.

**And one thing to be suspicious of in this brief:** the cybernetic framing is
seductive, and it is possible to build something conceptually immaculate that
draws badly. Every idea above should be judged by the sheet. If the beautiful
loop makes an ugly drawing, the loop is wrong.

---

## 7. What to build

**One new source module, with a bench** (i.e. a `ProcessModule` with a declared
time axis), that attacks at least one of the six criticisms — ideally the first
or the second, since those are where the ceiling is.

You are explicitly invited to **reject our framing**. If you think the
homeostatic loop is the wrong machine for Ian's vector, say so, argue it, and
build what you think is right. A convincing argument against the brief is worth
more than a competent execution of it.

**Deliverables:**

1. `axibridge/sources/<name>.py` — the module. One file, plus a private
   `_<name>.py` helper if the mechanism deserves testing on its own.
2. `tests/test_<name>.py` — hardware-free, in the normal suite. Test the
   *mechanism*, not golden files: properties, invariants, and at least one test
   that would fail against a plausible wrong implementation (see traps).
3. A short design note saying what it is, what it is trying to have at stake,
   and what you decided against.

**Done means:** `.venv/bin/python -m pytest -q` is green, the module appears in
the UI, its bench plays and scrubs, and a sheet from it can be argued for
against section 2.

---

## 8. Traps — every one of these bit us, measured

1. **A trajectory always runs to the time axis's declared UPPER bound**,
   regardless of the step count being viewed — that is what lets one cached run
   serve every scrub position. So any per-step cost that grows with step count
   lands, in full, on the very first call. A per-step measurement that walks the
   accumulated geometry is quadratic and will hang the UI. Keep per-step work
   O(1): maintain an incremental structure (we rasterise into a 1 mm occupancy
   grid) rather than re-reading the drawing.
2. **One segment per step means one PATH per step**, and the plotter reads that
   as a pen lift per step. If your marks are continuous, stitch contiguous
   segments into polylines in `document()` — the trajectory keeps per-step
   increments, so the prefix contract is untouched. Build the stitch by
   accumulating plain lists and constructing each `Path` once: the obvious
   per-segment rebuild is O(N²) and costs 40 ms against 0.19 ms, on every frame
   of a scrub.
3. **A normalised knob is not a reachable band.** We gave three measures one
   0…1 `target` control, which was honest and useless: a single pen inks under a
   tenth of a sheet, so a target sensible for local density put the global
   measure in permanent, unrecoverable crisis. If you expose one control over
   several quantities, state each one's reachable range in the field
   description, or normalise per quantity.
4. **A regulator can fail by thrashing, not only by converging.** Our first
   defaults sat outside their viable range 63% of the time — that is not
   hunting, and a thrashing system still draws, so nothing catches it. Measure
   the fraction of steps in range and make the tuning a test.
5. **A second-order loop that escalates on every failure is a ratchet.** Ours
   pinned its variety at maximum within twenty steps because it escalated after
   rerolls that had *worked*. Escalate only after a change that failed.
6. **Shared randomness fakes coupling.** With several agents drawing from one
   RNG, agent 0's behaviour changes merely because agent 1 exists, and you
   cannot tell coupling from stream interleaving. Give each its own stream and
   the coupling test becomes meaningful.
7. **A boundary rule is a drawing rule.** We reflected the heading and clamped
   the position, which is not reflection: at shallow incidence the pen slid
   along the wall for dozens of steps, drawing a frame around the picture.
8. **Tests that compare an algorithm to itself.** Our "from-scratch"
   rasterisation reference replayed the same segments through the same function.
   Write the reference by a *different* method, even a slow stupid one.
