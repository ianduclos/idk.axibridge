# Results: time as a param, plus a live popup

Implements `docs/plans/time-as-a-param.md` (design) via
`docs/plans/time-as-a-param-IMPLEMENTATION.md` (plan), Round 3 of
`docs/IDEAS-pass4.md`'s A1. Branch `feat/time-as-a-param`, 10 commits
(`2c3aefe..72167f5`), base `21f4ddc`. Suite 1080 → 1115. Full SDD ledger —
every ruling, every defect, every measurement — is
`.superpowers/sdd/time-as-a-param-IMPLEMENTATION/progress.md`; this doc is
the settled record, not a replay of the process.

## What shipped

- **A declared time axis.** `SourceModule.time_axis: str | None` — the field
  the master timeline scrubs. `Session._effective_gen_params`'s `master_t`
  fold, previously hardcoded to `frame`, now reads whichever param a
  generator declares, normalises against **that param's own Pydantic
  bounds**, and re-clamps into an `int` when the field is one. Modules with
  an existing `frame` field need no edit — the lookup falls back to `frame`
  when nothing is declared, so `Session.time_axis("image_threshold")` still
  returns `"frame"` with zero changes to that module. The fold arithmetic
  lives once, in `registry.fold_time_axis`, called from both
  `_effective_gen_params` and `tween.py` (both used to hardcode it
  separately — tween's copy additionally clamped to a hardcoded 0..1, wrong
  for a 0..600 step axis; see "What the plan got wrong" below).
- **`axibridge/process.py`** (new) — `ProcessModule`, a `SourceModule` whose
  author writes `run()`, yielding one `Step` (added paths + optional
  telemetry) per tick, and whose `generate()` is provided by the base: ask
  the trajectory for the state at step N, wrap it in a document. `run()` may
  be `while True`; the declared axis's upper bound is what stops it.
- **`axibridge/trajectory.py`** (new) — run a process once, to its axis's
  declared upper bound, and cache the whole thing keyed on every param
  **except** the time axis. Scrubbing is then a prefix slice
  (`state(n) = concat(steps[:n+1])` for the accumulative case) rather than a
  re-run. Budgeted through `gencache.cache_budget_multiplier()` like every
  other cache in the repo (0.25× on the Pi), LRU-evicted with the
  just-inserted key protected from evicting itself (see "A cache that
  evicted itself" below).
- **`venation`** (`axibridge/sources/venation.py`, new) — space colonisation
  / leaf-venation growth, the first real `ProcessModule`: branching lines
  that grow toward scattered attractors, one step at a time, consuming an
  attractor when a node gets within `kill` radius. Accumulative by
  construction (each step only adds segments), continuous coherent lines
  rather than scatter — the aesthetic direction this whole project favours.
  Declares `time_axis = "steps"`, reports `attractors` and `tips` telemetry.
- **The process popup** (`axibridge/static/js/process.js`, new) — a "Watch"
  button appears on any layer whose generator declares a time axis (direct
  or `frame`-fallback); it opens a popup showing the layer alone at step N,
  a scrub slider, play/pause, step ±1, a telemetry plot. It adds **no new
  API** — it drives the existing `POST /api/generators/preview` with the
  time param set per step, the same endpoint the render popup already uses
  for a no-layer, no-checkpoint, no-lock preview. Never PATCHes the project;
  a scrub is a viewer of a param, same discipline as the timeline bar.
- **Rehearse** (`Session.rehearse_layer`, `axibridge/session.py`) — stamps
  `moments` evenly-spaced moments of a process onto the sheet as ordinary,
  live, re-editable generator layers, in one undo step. See "The nicest
  surprise" below — this is where the round paid out more than it cost.

## What the design doc got wrong

**The master-timeline binding was already mostly built.** The design doc
called this out as a risk-reducer going in (`_effective_gen_params` already
folded `master_t` into `frame`), and it held: A1 turned out to be a
*generalisation* of one existing method rather than new plumbing. The
frame-fallback path is byte-identical to pre-change behaviour — every
image-generator test in the suite passed unchanged through the whole round,
which is the evidence that mattered more than any single assertion.

**Seven real defects were found in the plan's own code and tests** — not in
what the implementers designed, but in what the plan told them to write,
because each dispatch was told to check whether a predicted test failure
would actually happen for the reason the step claimed:

1. Task 1's own test file imported the `session` singleton but every test
   called `Session.time_axis` — a `NameError` before the `AttributeError`
   the brief predicted.
2. Task 1's fold clamped **after** the int cast, so at an axis's own bounds
   `min(8.0, max(1.0, 8))` returned float `8.0` against a test pinning `int`.
   Reordered: clamp in float space, cast last.
3. Task 2's telemetry test expected 5 entries from a 5-step scrub; the
   trajectory correctly runs to the axis's **declared bound** (10 → 11
   entries) regardless of the param's current value — which is exactly what
   lets one cached trajectory serve every scrub position. The test's
   expectation was wrong, not the code.
4. Task 4's acceptance test queried `#process-canvas path`; the plan's own
   `draw()` created `polyline` elements. Caught before dispatch (Ruling 11
   in the ledger) rather than left as a mystery hang.
5. Task 5's popup CSS classes (`.popup`/`.popup-head`/`.popup-controls`)
   never existed anywhere in the stylesheet — the popup would have rendered
   unstyled in document flow. Fixed by reusing the render popup's existing
   modal furniture.
6. Task 5's `#process-telemetry` markup was wired to nothing — dead SVG the
   plan specified but never connected to a data source. Wired to plot
   points-so-far from data the preview response already returns, at no
   extra request cost.
7. Task 4's `test_a_seed_pins_the_whole_run` and
   `test_coordinates_are_plain_python_floats` were both vacuous: the first
   compared a cached object with itself (no `clear_cache()` between calls,
   so it could never have failed), the second asserted a Pydantic coercion
   that happens on validation regardless of the code under test.

**The lesson worth keeping**: the plan's test code had never been run, and
prose that says "run it and watch it fail" is not the same as having
watched it fail. Every implementer in this round was explicitly told to run
that step and treat a pass as a defect report, not a formality — that is
what surfaced all seven.

**Two performance defects were mine** (the plan author's), not the
implementers'. The venation brief specified the nearest-node search as a
pure-Python double loop over attractors × nodes. At the module's own
declared bounds (`steps` ≤ 600, `attractors` ≤ 3000) that is on the order of
**918 million distance computations for one trajectory** — about **3
minutes** — and because a trajectory always runs to its declared bound
(that is the mechanism that makes scrubbing free), that cost lands on the
very first `generate()`, which would have made the Task 5 popup unusable.
Caught before dispatch and fixed with a numpy vectorisation (measured
0.108s at default params against the ~3-minute estimate — vindicated).

That fixed the constant factor but not the growth. The review that followed
found the vectorised version still pathological: at `kill` near its
declared minimum (0.5), attractors are consumed too slowly for growth to
converge, so node count runs away — **~92k nodes, ~7GB RSS, did not finish
in 60 seconds** at default `attractors`, and **64 seconds / 6.2GB** at
`attractors=3000`. All of that is reachable inside declared param bounds,
one slider drag from default, on the first `generate()`. Fixed two ways at
once: the `(M, N, 2)` intermediate tensor was replaced with the
`|a|²+|b|²−2·a·bᵀ` squared-distance expansion (no per-pair vector
materialised), and a hard `_MAX_NODES = 8000` cap was added in the repo's
existing idiom (`_MAX_EMISSIONS` in `grammar.py`, `_MAX_POINTS` in
`drawing.py`, `_MAX_ANCHORS` in `pen.py`) — hitting the cap simply returns
from `run()`, which the trajectory already treats as convergence.

**Final numbers**: the pathological case (`kill=0.5`, `attractors=3000`)
went **64s / 6.2GB → 6.18s / 465MB**. The other reviewer-found pathological
case (`kill=0.5`, default `attractors`) went from **not finishing in 60s at
~7GB → 0.21s / ~150MB**. The default-params case is **0.108s** for a full
600-step trajectory.

**A cache that evicted itself.** The trajectory cache's eviction loop had
no protection for the entry it had just inserted, so a single trajectory
larger than the cache budget would empty the cache on every insert — a
silent zero-hit-rate cache that recomputed the same oversized trajectory
forever. `gencache` has protected exactly this case for years
(`_evict_locked(protect_key)`); the reviewer caught it by comparing the new
cache against that sibling rather than reasoning about the new code in
isolation. Fixed by mirroring the same contract: the just-inserted key
cannot be popped even as the sole over-budget entry.

**One deviation from the design doc, recorded prominently because it is the
best thing this round produced.** The design doc, and the plan built from
it, specified Rehearse as three existing calls in sequence:
`animate_layer` → set the A/B keyframes to the axis's ends → `set_tween_
params(sweep=N)` → `explode_tween`. Checking `_checkpoint()` before
dispatch showed this cannot give one undo step: it folds consecutive
checkpoints only when the **previous** checkpoint carried the same
coalesce key, and each of those four public `Session` methods checkpoints
independently with no key of its own — so the tween route yields four undo
entries, not the one the design requires.

The repo already has a precedent for a compound, single-undo operation:
`add_separation_stack` computes everything first, then does one lock + one
`_checkpoint()` + a direct `project.layers` mutation, calling no other
public method along the way. `rehearse_layer` is built the same way — N
ordinary generator layers, one per moment, each the same generator with a
different value on the time axis, generated before the lock is taken and
appended in a single atomic mutation.

**This is simpler than the tween route, genuinely delivers one undo step,
keeps every moment live and independently re-editable rather than baked**
— and it is nearly free, which the design doc did not anticipate: the
trajectory cache key excludes the time axis (Task 3), so all N moments of
a process-backed layer share **one** trajectory run. Rehearsing a venation
layer at 4, 8, or 40 moments costs the same one `generate()`-worth of
process work; only the slicing differs. That payoff is a consequence of
Task 3's cache design colliding productively with Task 6's problem, and it
was not something either task set out to produce.

The cost of the deviation: the tween route's property that "the live tween
stays, hidden, so the rehearsal can be re-tuned and re-exploded" is not
there — a rehearsal is N independent layers, not one tween you can nudge.
That is mitigated by rehearsal now being cheap enough to simply delete and
re-run with a different `moments` value.

## What is still open

Deferred minors, carried from the ledger, roughly in order of how much they
matter:

- **Popup playback is one HTTP round trip per step** (~600 requests for a
  full 600-step run). Fine locally — the trajectory costs milliseconds and
  each step is a cached-prefix slice — but it will not hold frame rate over
  the Pi's SSH link. The honest fix is a multi-step reply, which means a new
  endpoint; this round deliberately did not add one (see the design doc's
  "adds no API" rule). Flagged for whoever picks this up next.
- An int-typed time axis whose bounds span less than one integer (e.g.
  `ge=1.1, le=1.4`) inverts the floor/ceil re-clamp in `registry.
  fold_time_axis` and can return a value outside the declared bounds. No
  such axis exists in the repo today; this needs a genuinely nonsensical
  field declaration to trigger.
- `trajectory.py`'s cache recomputes its whole running-points total on
  every miss, rather than keeping an incremental total the way `gencache`
  does. Negligible at the 32-entry cache cap; incremental bookkeeping would
  be its own bug surface for no measured benefit yet.
- `trajectory.py`'s cache key uses `json.dumps(default=str)`, which is
  stable for every param type actually in use but would silently change key
  if a `Params` field ever held an object with an identity-based `repr`
  (e.g. an unhashed custom class). No such field exists today.
- `venation`'s nearest-node search uses `np.unique`, whose sorted output
  changes within-step voter order relative to the reference algorithm. This
  is deterministic (a fixed seed still reproduces exactly) and draw order
  within a step was never a spec requirement — noted for anyone diffing
  against a textbook implementation, not a defect.
- `test_it_grows_monotonically` in `tests/test_venation.py` is guaranteed
  by `Trajectory.state()`'s slicing rather than by anything `venation.run()`
  itself asserts — a structurally weaker guarantee than it reads as, though
  correct.

Both one-line code tidies flagged at the end of the ledger were folded into
this task: `session.py`'s `rehearse_layer` docstring narrowed its "nearly
free" claim to `ProcessModule` sources specifically (an image generator
reached through the plain `frame` fallback pays N memoised `generate()`
calls, not one shared trajectory), and `process.py`'s unused `Any` import
was removed.

## Known limitation, not a defect

**Non-accumulative processes** (`accumulative = False` — a curve-shortening
flow, a diffusion descent, anything that *revises* earlier marks instead of
adding to them) get snapshot-under-budget caching rather than per-step
slicing: every step if it fits the budget, otherwise every K-th, with scrub
resolution degrading to that stride. This is a stated limitation of the
design, not something this round tried to avoid — no non-accumulative
process exists yet to exercise it. `venation` is accumulative by
construction, which is exactly why it was chosen as the first real client.

## What A1.5 needs, and cannot get from a desk

Interaction — poking a running process, in the popup, while it plays — was
deliberately left out of this round (the design doc's decision, restated in
the ledger). The design doc's proposed mechanism, if it is built, is to
write pokes into a hidden events param so a session becomes a recorded
score: reproducible, undoable, tweenable, at the cost of pokes reading as
edits to a score rather than as direct manipulation. That trade-off is the
single most likely thing in this whole area to force a redesign, and it
cannot be judged from a desk — see the `HANDOFF.md` entry this task adds.
