# The homeostat — what shipped, and what the design got wrong

Ledger for pass 4's **A2**, built 2026-09-04 in one session. Design
`homeostat.md`, plan `homeostat-IMPLEMENTATION.md`. Six commits,
`a5973da..eb0ec3e`; suite **1121 → 1156**.

## What shipped

| File | What |
|---|---|
| `axibridge/sources/_homeostasis.py` | `OccupancyGrid` + `Measures` — the measurement vocabulary, deliberately free of pens and params so A7 can import it alone |
| `axibridge/sources/homeostat.py` | `Genome`, `sample_genome`, `advance`, `HomeostatParams`, `Homeostat(ProcessModule)` — source id `homeostat` |
| `tests/test_homeostasis.py` | 13 tests: the grid, the three measures |
| `tests/test_homeostat.py` | 21 tests: the pen, the controller, the defaults |

A single wandering pen; a genome of five bounded genes; a blind sample-and-hold
reroll when the essential variable sits outside `target ± tolerance` for
`patience` consecutive steps; three measures read in O(1) off one incremental
occupancy grid; `variable`/`strain`/`rerolls` telemetry for the bench.

No session, compose, cache or API change, exactly as designed.

## What the design got wrong

**1. It was silent on stroke continuity, and the naive reading falsifies its own
central ruling.** `Step.paths` is the marks *added* this step, so one segment
per step is one two-point *path* per step — 300 pen lifts, and "the line does
not lift at a reroll" false precisely on paper, the only place it matters.
Caught while planning, not while building. `document()` now stitches.

**2. It specified a point cap that cannot fire.** Venation needs `_MAX_NODES`
because one step can add unboundedly many nodes. Here one step adds one
segment, so the axis bound *is* the point bound. Dead code, struck.

**3. The three measures share a 0…1 knob but not a reachable band.** The design
treated normalisation as sufficient for the measure to be a swappable knob. It
isn't: a single pen inks under a tenth of a sheet in a full run, so `coverage`
tops out near 0.10 while `crowding` lives near 0.14 and `tangle` near 0.27. The
original default target of 0.25 was *unreachable* under `coverage` — switching
measure at the bench dropped you into permanent, unrecoverable crisis (0% of
steps in range, 150 rerolls). The normalisation is honest and stays; what was
missing was saying where each band is, which the form now does.

**4. A homeostat can fail by thrashing, not only by converging.** The design
worried at length about `memory` making the system converge and die, and said
nothing about the opposite failure. The first defaults were it: 37% of steps in
range and 71 rerolls per 1200 — a system permanently in crisis is not hunting
either. Retuned to 0.12 ± 0.08 (74–76% in range, ~21 rerolls, stable across
seeds), and the tuning is a **test**, because a thrashing homeostat still draws
and nothing else would notice.

**5. The boundary was drawing.** `advance()` was specified to reflect at the
edges — and the implementation reflected the *heading* while clamping the
*position*, which is not the same thing. At shallow incidence the pen bounced
*along* the wall for many steps, growing a rectangular frame around the picture:
long straight runs that read as a decision the system never made. Mirroring the
overshoot too cut wall-pinned points from 4.7/2.7/8.2% to 2.6/1.8/0.5% across
three seeds. **The general lesson: a boundary rule is a drawing rule.**

## What the review caught that the build did not

A fresh-context review of the five feature commits, before the docs trail. All
six findings were real; all are fixed in `eb0ec3e`.

- **`_stitch` was O(N²)** — a rebuilt *and Pydantic-revalidated* point list per
  segment: 40 ms at the axis bound versus 0.19 ms for byte-identical output, on
  every frame of a scrub. The plan asserted O(N) and nobody measured it. The
  quadratic trap this module was designed around got reintroduced one layer
  down, in the function added to fix a different problem.
- **`patience` had no discriminating test.** Both controller tests used a range
  one pen can never reach (in-range fraction: 0.0000), so `out_of_range` never
  reset and *consecutive* was indistinguishable from *cumulative* — a mutant
  counting total out-of-range steps passed the whole suite. The design doc had
  specified this exact test ("a single out-of-range step does not reroll") and
  it was dropped between the design and the plan.
- **The test named for THE invariant compared the algorithm to itself** — the
  "from-scratch" grid was built by replaying the same segments through the same
  `mark()`. Now three tests, one of them against an independent dense
  rasterisation (0.937 agreement, strict subset; a 4× undersampling mutant
  scores 0.453 against a 0.85 floor).
- `_cells_on` claimed "no gaps" and is an 8-connected chain, ~94% of a
  supercover; `advance` claimed reflection and clamped (finding 5 above);
  `measure` was the only enum param in the source registry not a `Literal`, so
  a bad value surfaced as a 400 from inside `generate()` instead of a 422.

The pattern worth carrying: **every one of these was a claim in a docstring or
a plan that no test held to account.** The mechanism was right each time.

## Open

- **Nothing has touched paper.** Not this, not venation, not the cymatic fill.
- **Nobody has seen it in the actual bench** — the popup, the telemetry plot,
  the scrub. `shots/homeostat-first-look.png` is a matplotlib render, which is
  not the UI and is not a plotter.
- `held` accumulates duplicate genomes, so `memory`'s uniform pick is weighted
  by how many holding episodes a hand had. Defensible — a hand that held often
  is a better bet — but undocumented and unexamined. Only reachable at
  `memory > 0`, which is off by default.
- **A7 (algedonic marks)** is now cheap: `_homeostasis.py` is the vocabulary it
  needs, and the threshold-crossing it wants is `strain` leaving ±1.

## The ensemble (2026-09-04, second round)

`pens` 1–6 coupled units on one shared grid, plus a `unit` param so the layer
can be duplicated at the same seed and plotted in several pens. This is also
**A4 (the seam)** arriving through the front door: independent fronts, identical
local rules, no awareness of each other.

Two decisions, both Ian's, both taken before building: units are **identical
machines differing only in seed and start** (Ashby's four units were identical
in construction — the difference should come from position and history, not
from being told to differ), and a unit reacts to **all ink equally**, its own
included, so it has no concept of another pen at all.

**Every unit gets its own RNG stream**, and that is not a detail. Drawing them
all from one generator interleaves the streams, so unit 0's hand would change
merely because two other pens exist — and then "the units are coupled" could
not be told apart from "the random numbers moved". With one stream each, the
only channel between units is the shared grid, and the coupling test can prove
it: unit 0 alone and unit 0 in company share a start and diverge anyway.

**What the ensemble taught, and it is Ashby's own result:** joint equilibrium is
harder to reach the more units are coupled. Every unit inks the one grid they
all measure, so crowding rises ~N times faster while each unit's viable band
stays put. At the single-pen defaults, in-range falls 70% → 49% → 28% and total
rerolls climb 26 → 178 → 566 from one pen to three to six. The sheet fills and
the composition that made the single-pen drawings good — knots against long
empty travels — is lost above about three pens.

This is **not** auto-corrected, deliberately. Scaling the band by pen count
would hide the finding, and a system that quietly adjusts its own viable range
so it is never in trouble is precisely the thing this whole pass exists to
avoid. The rule of thumb is in the test: widen `tolerance` as pens are added —
0.30 ± 0.20 restores six pens to ~65% in range.

Sweet spot at current defaults: **two or three pens.**
