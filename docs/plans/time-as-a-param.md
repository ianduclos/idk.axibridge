# Time as a param, plus a live popup — design notes

Pass 4's **A1**, the substrate round (`docs/IDEAS-pass4.md` §A1, ROADMAP Round
3). Not started; this is the design agreed with Ian on 2026-08-21, written
before code because two of its decisions could reasonably have gone the other
way and the point of writing them down is that changing your mind later should
cost an afternoon rather than an archaeology session.

**A2 (the homeostat) appears here only as far as it constrains A1.** It is the
first real client, and one A1 requirement — the telemetry channel — is
invisible until you try to build it. A2 gets its own doc once A1 is real, for
the reason its own entry gives: its interesting decisions all change the moment
you can watch it hunt.

## The problem

Almost every generator in axibridge is *instantaneous*. You set params, you get
a drawing. But a growth, a search, a system holding itself in equilibrium — the
whole of pass 4's Half A — are processes that **unfold**, and the interesting
output is often the trajectory rather than the converged result. Today there is
nowhere to put that: no way to say "show me step 340", no way to watch it
happen, and no way to draw several moments of one process on one sheet.

Ian, 2026-08-18: *"many algos can occur in time; current ones are more
instant/parametric… a new sort of generator type that opens a popup where we
can visualize the live drawing and development, and even interact with it."*

This is not a revival of the workbench (removed July 2026). The workbench was a
stateless recipe playground *beside* the project. This is a per-layer inspector
for layers that genuinely have a time axis, and the layer stays an ordinary
layer throughout.

## Two things already exist, and they change the shape of the round

Found while designing, and worth stating first because the idea doc assumes
otherwise:

1. **The master-timeline binding is already built.** `Session._effective_gen_
   params` (`session.py:452`) already folds `master_t` into a generator's axis,
   gated on `layer.frame_follow` and on the module declaring the field. It is
   simply named `frame` and scoped by convention to image sequences. Binding a
   process's step count to the master timeline is a *generalisation of one
   method*, not new plumbing.
2. **`grammar.py:200` already has `iterations`** (1..8) — a step axis that
   nothing treats as time. It is the retrofit proof: if declaring a time axis
   is one word on an existing generator, the contract is the right size.

So A1 is smaller than budgeted. The real work is the trajectory cache and the
popup.

## The one rule everything else rests on

**`generate()` stays a pure function from params to geometry. Time is an
ordinary bounded param.**

Everything downstream — `gencache`'s content-keyed memo, `tween`'s param lerp,
undo, the estimate, the plotter, the single-resolve invariant — holds only
because a generator is a pure function of its params. A process that carried
live mutable state would need a second geometry path into the plotter, which
CLAUDE.md forbids for good reasons. So the process is *replayed*, never *held*,
and "step N" is a number in the params like any other.

Everything below is a consequence of that rule.

## The contract

### 1. A declared time axis

```python
class SourceModule:
    #: The param that is this generator's TIME axis, if it has one. The
    #: master timeline scrubs THIS field. None = instantaneous generator.
    time_axis: str | None = None
```

`_effective_gen_params` stops hardcoding `"frame"`. It reads the declared axis,
normalises the stored value against **that param's own Pydantic bounds**, adds
the shift in normalised units, clamps, and maps back:

```
norm  = (value - lo) / (hi - lo)
value = lo + clamp(norm + shift, 0, 1) * (hi - lo)
```

**The result is coerced to the field's own type**, and this matters: `grammar`'s
`iterations` is an `int`, and Pydantic v2 rejects `4.5` for an int field rather
than quietly truncating it. The fold rounds (half up) and re-clamps into
bounds for integer axes. Get this wrong and the failure is a 422 on a scrub,
which is at least loud.

**Modules that already have `frame` need no edit.** The lookup is
`time_axis or ("frame" if the model has a frame field else None)`, so every
image generator keeps working whether or not anyone remembers to declare it —
the declaration is how a NEW axis opts in, not a migration everything must
pass. Image sources' bounds are already 0..1, so `norm == value` and
**today's behaviour is byte-identical** — the existing
frame path becomes the special case, not a parallel one. A process declaring
`steps: int = Field(ge=0, le=2000)` gets `master_t = 0.5` → step 1000, which is
the reading a user expects: halfway through the timeline is halfway through the
process.

**The layer fields keep their names.** `frame_offset` and `frame_follow` are
persisted in every saved project; renaming them to `time_*` buys clarity worth
less than a migration. Documented naming debt, not an oversight.

### 2. `ProcessModule`

New `axibridge/process.py`. The author writes `run()`; the base provides
`generate()`.

```python
class ProcessModule(SourceModule):
    time_axis = "steps"
    accumulative = True

    def run(self, params) -> Iterator[Step]:
        """Yield one Step per tick of the process, in order."""
```

**`run()` may be unbounded.** The base stops consuming at the time axis's
upper bound, so a process author writes the natural `while True:` loop and the
*param* decides how long it runs — which is the same reason every numeric param
here is bounded, applied to time. A `run()` that ends early simply ends: steps
past the last yield repeat the final state rather than erroring, so a process
that converges before its budget still scrubs to the end.

where a `Step` carries:

* `paths: list[Path]` — **the marks ADDED at this step** when `accumulative`
  (the default), or the complete state at this step when not;
* `telemetry: dict[str, float] | None` — whatever the process wants plotted
  against time.

`generate()` is implemented once, in the base: resolve the trajectory (cached,
below), take the state at `params.<time_axis>`, wrap it in a `PathDocument`. A
`ProcessModule` is therefore an ordinary `SourceModule` to every other part of
the system — same registry, same decorator, same JSON-Schema-driven form, same
`cacheable` memo.

### 3. Telemetry, and why it is in A1 rather than A2

`telemetry` looks like a nicety and is not. A2's whole premise is a system with
an **essential variable** that leaves its viable range; "you cannot tune a
homeostat you cannot watch" means watching *that number*, not only the marks it
leaves. If the popup can only show geometry, A2 is untunable and A1 has failed
at the one job it exists for.

It is deliberately a flat `dict[str, float]` — no schema, no registration. The
popup plots whatever keys turn up. A process that reports nothing gets no plot
and costs nothing.

## The trajectory cache: run once, index every step

The decision (Ian, 2026-08-21) was **run the whole trajectory once and index
it**, over checkpoint-and-replay and over an incremental `step()` API. The
third was rejected outright: it breaks the purity rule above.

`axibridge/trajectory.py`, keyed on `(module id, params MINUS the time axis)`,
budgeted through `gencache.cache_budget_multiplier()` like every other cache.

**Because `run()` yields increments, the accumulative case is the good case:**

* memory is **one drawing's worth of geometry**, not N copies — the cache holds
  the increment lists and nothing else;
* state at step N is `flatten(increments[:N+1])` — a concatenation of
  pointers. Be exact about this: it is O(N) in *list appends*, not O(1), and
  not O(N) in process work. For a 2000-step process holding a few thousand
  paths that is microseconds, and it is the difference between "scrubbing is
  free" and "scrubbing re-runs the process", which is the claim that matters;
* the entire trajectory costs exactly one run, so scrubbing back and forth,
  playing, and the pentimento sweep below all share it.

This is the same move the eigenfunction fill made a week earlier (`effects/
_eigenmode.py`: solve the whole basis once, scrub the mode index for free), and
it should be recognisably the same shape.

**Non-accumulative processes** — curve-shortening flow, a diffusion descent,
anything that *revises* earlier marks rather than adding to them — declare
`accumulative = False` and get **snapshots under a memory budget**: every step
if it fits, otherwise every K-th, with scrub resolution degrading to that
stride. This is a real limitation and is stated rather than hidden. The
alternative (storing every snapshot) is unbounded in N and would evict
everything else in the process.

### What this costs

The ceiling becomes **one full run at the max step must be affordable**, which
a bounded time-axis param guarantees by construction — the same reason every
numeric param in this repo is bounded. A generator whose full run is genuinely
slow will feel slow *once*, then scrub freely. That is a better failure than
checkpointing's "every scrub step pays up to K steps of work, forever".

## The popup

Precedent and pattern: the **render popup** — static top-level markup in
`index.html`, opened from a button, living over any tab (`static/js/
timeline.js`, `index.html:318`).

* **Opened from** a "Watch" button in the layer detail panel, shown only when
  the layer's generator declares a `time_axis`.
* **Shows** the layer alone at step N (large), a scrub over the time axis,
  play/pause, step ±1, a readout, and a telemetry plot beneath.
* **Adds no API.** It drives the existing `POST /api/generators/preview`
  (`api.py:329`) with the time param set per step — that endpoint already runs
  a generator with no layer, no undo checkpoint and no session lock, which is
  exactly a scrub's requirements. With the trajectory cached, each step is a
  prefix slice rather than a re-run.
* **Never PATCHes the project.** Same discipline as the timeline bar
  (CLAUDE.md): the popup is a viewer of a param, and committing a step means
  typing it in the ordinary form.

## Pentimento falls out of machinery that exists

The roadmap's second argument for A1 — *"draw several moments of the same
process on one sheet" becomes a layer-level operation* — needs no new
machinery:

`Session.animate_layer` (`session.py:2593`) already splits a layer into A/B
keyframes under a follow-master tween. Set A's time axis to 0 and B's to max,
set `sweep = N`, and `Session.split_tween` (`session.py:1169`) already bakes
one layer per sweep step. Per-pass pen assignment already falls out of the
multi-pen path — **rehearsals in pencil, the committed stroke in ink**.

So this is a "Rehearse" button wiring three existing calls, and it
retroactively ships pass 1's §2, open since July.

## A2, only as far as it constrains A1

Ashby's homeostat: measure an essential variable; while it is in range, keep
drawing; when it leaves, **reroll the rule set blindly** until drawing can
continue. It rerolls, it does not reason — that is the point, and it is why the
seam lands where the system was in trouble. Oehlen's regime collision with a
reason the sheet can show.

As a `ProcessModule`, each `run()` step draws a little, measures, and sometimes
rerolls. What A2 pins down now, because it is what A1 must support:

| What A2 needs | Where A1 provides it |
|---|---|
| "the drawing so far", to measure | the accumulative trajectory — the increments to step N *are* the drawing so far |
| the essential variable, watchable | `Step.telemetry`, plotted in the popup |
| a step axis to hunt along | `time_axis` |
| reproducible reroll | the RNG seeds from params, like every other generator |

What A2 does **not** pin down now: what to measure (ink density, crossing
count, unmarked-area fraction, stroke-length variance — the biggest lever by
far), how wide the viable range should be (narrow = constant crisis and visible
thrash, wide = long stable passages punctuated by lurches), whether a reroll
swaps one param or a whole rule set, and whether it is global or per region.
Every one of those changes the moment you can watch it hunt, which is precisely
why A1 comes first. Memory stays **off by default**, exposed as a slider *so
you can watch the system converge and die* — converged being another word for
finished.

## Decisions, and how to reverse each one

**Interaction is deliberately not in v1** (Ian, 2026-08-21). The idea doc's
model — live pokes written into a hidden events list, so a session becomes a
recorded score — is what would keep the layer pure, reproducible and tweenable.
It is also the single most likely thing to force a redesign, because it makes
pokes *edits to a score* rather than direct manipulation, and poking twice at
the same moment means inserting into history. Shipping the watchable half first
buys the opinion needed to judge it.

*To reverse:* add the hidden events param, extend the trajectory cache key with
it, and invalidate only the suffix after the poke — the prefix stays valid,
which the increment model already guarantees. **No empty events param is being
added now as a placeholder**: a new Pydantic field with a default loads old
projects fine, so there is no migration to pre-empt and nothing is bought by
guessing its shape a round early.

**Increments rather than snapshots as the default.** Reversible per module via
`accumulative = False`; the cost of guessing wrong is memory, not correctness.

**One `Step` type carrying both geometry and telemetry**, rather than a second
channel. If telemetry ever needs to be richer than `dict[str, float]`, widening
that field touches the popup and nothing else.

**The popup reuses `/api/generators/preview` rather than getting its own
endpoint.** If scrubbing ever needs the *layer's* effects and transform applied
(the preview shows raw generator output), the honest fix is
`/api/layers/{id}/effects/preview`, which also exists — not a new route.

## Files

| | |
|---|---|
| The time-axis declaration | `axibridge/registry.py` (`SourceModule.time_axis`) |
| The master_t fold, generalised | `axibridge/session.py` (`_effective_gen_params`) |
| `ProcessModule`, `Step` | `axibridge/process.py` **(new)** |
| The trajectory cache | `axibridge/trajectory.py` **(new)** |
| Retrofit proof | `axibridge/sources/grammar.py` (declare `time_axis = "iterations"`) |
| The popup | `axibridge/static/index.html`, `static/js/process.js` **(new)** |
| Rehearse button | `axibridge/static/js/compose.js` + existing session calls |
| Docs | `docs/MODULES.md` gains a "Writing a Process source" section |

## Testing

Properties, not golden files — the standard `test_eigen_fill.py` set:

* **Prefix equality.** The state at step N equals a full run truncated to N.
  This is the trajectory cache's whole correctness claim.
* **The frame path is untouched.** Every image generator's output with a
  declared `time_axis = "frame"` is identical to its output before the change,
  and `master_t` folding on a 0..1 axis is byte-identical. The existing suite
  passing unchanged is most of this.
* **Bounds mapping, including the integer trap.** `master_t = 0.5` on a
  0..2000 axis lands on 1000; on `grammar`'s `int` 1..8 axis it lands on 4 (4.5
  rounded, re-clamped), and asserting that explicitly is what stops a scrub
  422ing on an integer axis.
* **Rehearsal nesting.** For an accumulative process, a sweep of N rehearsal
  layers has strictly nested geometry — each moment contains the one before.
* **Purity and determinism** come free: a `ProcessModule` is a `SourceModule`,
  so `tests/test_orientation.py` and the generate-memo tests already cover it
  the moment it registers.
* **The popup** gets one acceptance test in `tests/test_acceptance_ui.py`:
  the Watch button appears only for a layer with a time axis, scrubbing changes
  the ink, and the popup never mutates the project (assert the project hash is
  unchanged after a scrub).

## Known gaps

* **Non-accumulative processes scrub at snapshot stride**, not per step. Fine
  for watching, wrong for a rehearsal sweep that wants exact moments — if that
  bites, the fix is a per-layer stride override, not a change to the model.
* **A very slow process still costs one full run** before the first frame
  appears. `registry.report_progress` exists and the popup should feed the
  existing load bar, but there is no partial-trajectory display in v1.
* **Interaction (A1.5), A4 (the seam) and A7 (algedonic marks) are out**, the
  last two by the roadmap's own ordering. A7 pairs with A2 and bolts onto
  anything that already measures — it is the cheap follow-on once telemetry
  exists.
