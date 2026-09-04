# The homeostat — design notes

Pass 4's **A2** (`docs/IDEAS-pass4.md` §A2, ROADMAP Round 3, item 6). Not
started; this is the design agreed with Ian on 2026-09-04, written before code
because three of its decisions could reasonably have gone the other way and the
point of writing them down is that changing your mind later should cost an
afternoon rather than an archaeology session.

A1 (`time-as-a-param.md`, shipped 2026-08-21, merged 2026-08-29) built this
module's substrate and deferred every decision below to the moment you could
watch a process hunt. That moment has arrived: the bench (2026-08-29) tunes a
process generator with its growth on screen. **Nothing in A1 needs changing to
build A2** — this is a new source file and a private helper, no session,
compose, cache or API change.

## The problem

Idiomatic computational art has nothing at stake. Nothing can go wrong for the
system, so nothing it does reads as a decision — the diagnosis that opened pass
4, and the reason its Half A exists.

Cybernetics is the study of systems that *can* be in trouble. Ashby's homeostat
held an essential variable inside a viable range and, pushed outside it,
**randomly rewired itself** until it found a configuration that worked.
Blindly — it rerolls, it does not reason. That blindness is the whole point:
the reconfiguration is not a search for a better drawing, and the seam it
leaves lands exactly where the system was in trouble.

Which makes this Oehlen's regime collision **motivated**. Pass 2 collided mark
regimes but never answered why a regime should change. Here the answer is on
the sheet.

## What it draws

**A single wandering pen with a rerollable hand.** One continuous line walks
the sheet; the rule vector — the *genome* — is its handwriting: turn bias,
wander amplitude, persistence, dwell, and a multiplier over the base step
length. A crisis rerolls the genome
mid-stroke.

Two alternatives were considered and rejected (2026-09-04):

- **A bank of named regimes** (wander / hatch / spiral / cluster / contour) —
  the most literal reading of regime collision, but each regime is a
  mini-generator to write and tune, and the sheet risks reading as collage
  rather than as one system in difficulty.
- **A coupled population of agents**, which is what Ashby's machine actually
  was (four units seeking joint equilibrium; a crisis rewires the coupling
  matrix). Truest to the source and the only version where the reroll is about
  *relationships*, but a rewire changes everything at once, which is the
  hardest thing there is to tune.

The genome is deliberately shaped so both remain reachable: it is a flat vector
of bounded floats, so a population version is N of them plus a coupling matrix,
and a regime bank is a genome with a discrete gene.

**Ruling: the line does not lift at a reroll.** The hand changes mid-stroke, so
the seam reads as a change of *character* in a continuous line rather than as
two marks butted together — and continuous coherent lines are what this project
wants and what plots cleanly. `lift_on_reroll` exists as a bool for the bench,
defaulting off.

## The loop

`class Homeostat(ProcessModule)`, `time_axis = "steps"`, `accumulative = True`.
One `Step` per pen advance:

1. **Advance.** `turn = persistence·prev_turn + wander`, sampled from the
   current genome; the pen moves `step_len` mm. Sheet edges reflect — the pen
   cannot leave the bed, and being against a wall raises crowding on its own,
   which is the system noticing a corner rather than a rule about corners.
2. **Measure.** The essential variable `v`, normalised to 0…1 (below).
3. **Judge.** Is `v` inside `target ± tolerance`?
4. **Reroll.** Out of range for `patience` consecutive steps → sample-and-hold
   a fresh genome from the seeded RNG. No gradient, no memory of what failed,
   no search.
5. **Report.** `Step.telemetry = {"variable": v, "strain": …, "rerolls": …}`,
   which the popup and the bench plot for free. `strain` is the signed
   normalised excursion `(v − target) / tolerance`, so 0 is content and ±1 is
   at the edge of viability — the number you actually watch while tuning.

`Step.paths` is the segment added this step, which is what makes state at step
N a prefix slice of the cached trajectory rather than a re-run.

**Memory** is a 0…1 slider defaulting to **0**. Above 0, a reroll is biased
toward genomes that previously held. Ashby deliberately had none, and adding it
makes the system converge — converged being another word for finished. It is
exposed *so you can watch it die*, not because converging is good.

## Measurement, and the mistake that would kill it

Three measures behind one `measure` enum: **crowding** (default), **coverage**,
**tangle**.

The trap is walking the accumulated paths every step to measure "the drawing so
far". That is quadratic in the step count, and `trajectory()` always runs a
process to its axis's declared *upper* bound — so the cost lands on the first
`generate()`, not when a user drags to the end. Venation was bitten by exactly
this shape of mistake; the account is in its module docstring and the guard is
`tests/test_venation.py::test_a_full_trajectory_is_fast`.

So: **one incremental occupancy grid** (numpy, ~1 mm cells) updated as each
segment is laid, and all three measures read off it in O(1) per step.

| Measure | Read | Reads as |
|---|---|---|
| `crowding` | mean occupancy in a window around the pen's head | local: "have I painted myself into a corner?" |
| `coverage` | running count of non-zero cells ÷ total cells | global: long stable passages punctuated by lurches |
| `tangle` | trailing-window rate of entering already-occupied cells | a cheap honest proxy for crossing density |

`tangle` is explicitly a proxy: exact segment-intersection counting is the
quadratic trap again, and the docstring says so rather than implying the number
is a crossing count.

All three normalise to 0…1, which is what lets `target`/`tolerance` mean the
same thing across measures — swap the measure and the range control still
reads. The doc calls the measure "the biggest lever by far", so it is a knob;
three, not eight.

A hard cap on total points, treated exactly like convergence (`run()` returns;
`Trajectory.state()` repeats the final geometry for any later step) — venation's
`_MAX_NODES` precedent, for the same reason.

## Params

All bounded — `tests/test_effect_contract.py::test_every_numeric_param_is_bounded`
sweeps the whole source registry and will cover this module the moment it
registers.

| Param | Range | Note |
|---|---|---|
| `steps` | 0…1200, default 300 | the time axis; bench scrub range |
| `width` / `height` | mm, bed-bounded | sheet the pen walks |
| `seed` | 0…99999 | every reroll derives from this; the run is reproducible |
| `measure` | enum | `crowding` \| `coverage` \| `tangle` |
| `target` | 0…1 | where the variable wants to sit |
| `tolerance` | 0…1 | viable half-width. Narrow = constant crisis and visible thrash; wide = long stable passages. The second-biggest lever |
| `patience` | 1…60 steps | consecutive out-of-range steps before a reroll — sample-and-hold interval |
| `variety` | 0…1 | how wide a reroll samples the genome. 0 rerolls to nearly the same hand |
| `memory` | 0…1, default 0 | bias toward genomes that held. Off by default |
| `step_len` | mm | base pen advance per step; the genome scales it |
| `lift_on_reroll` | bool, default false | the seam as one line, or as two |

The genome itself is sampled inside fixed sensible ranges rather than exposed
gene by gene; `variety` is the one knob over it. Exposing every gene bound
would be a worse bench than one honest slider.

## Files

| File | Why |
|---|---|
| `axibridge/sources/homeostat.py` | the module: params, `run()`, the pen |
| `axibridge/sources/_homeostasis.py` | the occupancy grid and the three measures |
| `tests/test_homeostat.py` | below |

The split follows `_eigenmode.py` / `_lineart.py` / `_fast_marching.py`: the
mechanism is testable on its own and liftable later without a refactor, which
matters because **A7 (algedonic marks) wants exactly this measurement
vocabulary** and is the next-smallest item in the pass.

## Testing

Hardware-free, in the normal suite.

1. **In range, nothing happens** — wide tolerance, `telemetry["rerolls"]`
   stays 0 for a whole trajectory.
2. **Out of range, it rerolls** — narrow tolerance produces rerolls, and the
   genome after one differs from the genome before.
3. **Patience is honoured** — a single out-of-range step does not reroll;
   `patience` consecutive ones do.
4. **Determinism** — same params twice, identical geometry; different `seed`,
   different geometry. This is the property the trajectory cache rests on.
5. **The grid invariant** — incremental occupancy after N steps equals a
   from-scratch rasterisation of the same paths. This is what licenses the O(1)
   claim; if it ever fails, every measure is quietly wrong.
6. **Normalisation** — all three measures stay within 0…1 across a run.
7. **Prefix property** — `state(n)` is a prefix of `state(n+1)`, the
   accumulative contract.
8. **Performance guard** — a full trajectory to the declared upper bound inside
   a generous wall-clock budget, venation's precedent, loose enough for the Pi.
9. **The pen stays on the bed** — every point inside width/height.

Nothing golden-file. The measures are analytic and the controller is a state
machine; both can be asserted on properties rather than on pixels.

## Docs trail

`docs/IDEAS-pass4.md` §A2 marked SHIPPED with the ledger; ROADMAP Round 3 item
6 struck; a `CHANGES.md` entry (a new source id is a boundary others read); and
a `-RESULTS.md` beside this file if the build teaches anything the design got
wrong, as A1's did. `docs/MODULES.md` needs **no** change — this is a source,
not a new module kind.

## Known gaps, deliberately

- **No interaction.** A1.5 (does poking a running process want direct
  manipulation or a recorded score?) is still unanswered and this module does
  not need it. If anything makes the case for the recorded score, it will be
  wanting to shove this pen while it hunts — but that is an observation to
  make at the bench, not a feature to design now.
- **No A7.** The algedonic mark — one monitored quantity, one threshold, one
  mark placed without regard to the composition — is a natural rider on this
  module's measures and is deliberately a separate item.
- **Memory is a slider, not a model.** No learning, no credit assignment. A
  homeostat that reasoned would not be a homeostat.
- **Nothing here has touched paper**, and neither has venation. The whole point
  of the round is the sheet; the suite can only prove the machine runs.
