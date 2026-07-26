# Plan (loose): hatch_fill connect_strokes v2 — boundary-hugging connector

Opened 2026-07-25 by Sonnet 5 + Ian, for a later session (Opus) to pick up.
Deliberately loose — not a frozen brief like the other `docs/plans/*.md`
briefs. The direction is agreed; the exact mechanics are judgment calls for
whoever implements it.

## The problem

`connect_strokes` (`axibridge/effects/hatch_fill.py`, shipped on
`feat/hatch-connect-strokes`, merged to main 2026-07-25) joins consecutive
serpentine hatch scanlines into one continuous stroke IF the dead-straight
connector between them stays entirely inside the shape
(`_join_where_possible`, lines ~86-105). On a simple convex-ish fill this
works well (a filled rectangle went from 26 paths to 2). On a concave shape
with a hole — see Ian's screenshot from this session, a hooked/petal shape
with an interior hole and sharp cusps at the tips — the straight-line test
fails constantly right where it matters most, leaving lots of short
unconnected fragments ("loose ends") near the tips and around the hole.

Root causes, diagnosed in conversation (not yet verified against the actual
screenshot shape in code — do that first):

1. **No minimum-length filter** — `_hatch` (lines ~56-78) keeps any clipped
   fragment with `length > 1e-9`; slivers near a sharp cusp survive as their
   own tiny stroke (their own pen lift) instead of being absorbed.
2. **Join is "next in scan order," not "nearest reachable"** — near a notch
   or hole, the closest geometrically-joinable segment often isn't the next
   one in the strict top-to-bottom serpentine list, so real joins get missed.
3. **Straight-line-only connector** — even when two segments are close and
   both inside the shape, the connector fails if the straight line between
   them clips outside a concave boundary. This is the one Ian wants tackled
   first.

## What to build first: boundary-hugging connector

When the straight connector fails, instead of giving up and forcing a lift,
try a connector that hugs the inside of the shape's boundary between the two
points — i.e. walk a short stretch of the polygon's boundary (exterior ring,
or the relevant interior/hole ring) instead of cutting straight across empty
space. If that stays inside (it should, by construction, modulo the inset),
join through it instead of lifting.

One plausible mechanic (not frozen — use judgment):
- `sub` (the `Polygon` passed into `_join_where_possible`) already has
  `.exterior` and `.interiors` rings available (shapely).
  For the two endpoints (`prev[-1]`, `nxt[0]`), find the nearest ring (via
  `sub.boundary` or checking each ring), project both points onto it
  (`ring.project(Point(...))`), and take the shorter of the two arcs between
  those projected positions as the candidate connector polyline.
- Simplify/resample that arc to a reasonable point count (it's a real stroke
  now, not just a lift — avoid emitting hundreds of boundary vertices for a
  short hop).
- Buffer/inset the connector polyline the same tiny epsilon the straight-line
  test already covers with (`_JOIN_EPS`), or reuse the shape's own inset if
  one was applied, so the connector doesn't ride exactly on the cut edge.
- Fall back to a real lift (today's behavior) only if even the boundary-hugging
  candidate doesn't stay inside, or if the arc length is unreasonably long
  relative to the straight-line distance (a boundary detour that goes most
  of the way around the shape is worse than a lift — needs a sanity cutoff,
  pick a reasonable one and note why).

## Constraints to respect (from the existing docstring + house invariants)

- A hole must still force a real lift when there's genuinely no way around
  it inside the shape — the fallback-to-separate-line path stays.
- A crosshatch's two angle passes never join to each other — unchanged,
  `_join_where_possible` is already called per `(sub, angle)` pass only.
- Effects must be pure (never mutate input `Path`s) — unchanged by
  construction if this stays inside `_join_where_possible`/`_hatch`.
- `connect_strokes` stays opt-in, off by default.

## Secondary, smaller wins (do these too if there's room, independently useful)

- **Minimum-length filter**: drop or absorb hatch fragments below some
  fraction of `spacing` instead of emitting them as their own lift — cheap,
  reduces visual clutter from tip slivers regardless of the connector work.
- **Greedy nearest-reachable join**: instead of only checking "next in list,"
  check a small window of upcoming candidates by endpoint distance for a
  containment-passing connector — recovers joins the strict order misses.
  Do this AFTER the boundary-hugging connector, since a smarter connector
  test reduces how often this reordering is even needed.

## Verification

- Reuse or approximate the screenshot shape (concave, with a hole, sharp
  cusps) as a new `tests/test_modules_new.py` case — assert fewer output
  `Path`s (fewer lifts) than today's straight-line-only join on that shape,
  while every existing `hatch_fill` test (crosshatch non-join, hole-forces-
  lift, opt-in default-off) still passes.
- Visual check: render the shape before/after and look for the loose-end
  fragments actually closing up, not just a lower path count (a lower count
  achieved by dropping detail would be the wrong fix).
- Full suite green (`.venv/bin/python -m pytest -q`) before calling it done.

---

# Results — built 2026-07-26 (Opus 5)

Branch `feat/hatch-connect-v2`. Suite 514 green (511 + 3 net new tests).
All three items above shipped; the first one grew a rule the plan did not
anticipate, described below.

## What was built

**Boundary-hugging connector** (`_Ring`, `_connector` in `hatch_fill.py`).
When a connector can't go straight, it walks the ring both endpoints sit on —
shorter of the two arcs first — and joins through it. Endpoints on *different*
rings (shape edge → hole edge) still can't be walked between: that's a lift.

**The rule that emerged: ink is permanent, a pen lift is invisible.** The plan
framed the cutoff as "a boundary detour that goes most of the way around is
worse than a lift", which is true but incomplete. The visual check turned up
the sharper problem — v1's *straight* connectors were unbounded, so the greedy
search happily drew 9–14 mm chords straight across a lobe. Those cost nothing
in lifts and look like a mistake. So a connector now has to draw where the
drawing already is:

- a straight hop under `_STRAIGHT_SPAN` (4 × spacing) is free — it reads as the
  fill turning at the edge;
- anything longer must ride the boundary instead, and is re-tried as a hug.
  An *empty* hug arc (no ring vertex between the two points) means the boundary
  there IS the straight line, so long edge-runs are still taken as-is;
- if the hug would add more than `_DETOUR_EXTRA` (2 × spacing) of extra travel,
  the pen lifts. This is what keeps a hole from being circled.

An earlier attempt gated long straights on an arc-length ÷ chord-length ratio;
it let a 14.4 mm chord across a lobe through (ratio 1.11 — a cusp makes the
boundary arc short even when the chord cuts open interior). Deleted in favour
of the above, which needs no extra test: preferring the hug *is* the rule.

**Greedy nearest-reachable join** (`_JOIN_WINDOW` = 8). Each stroke absorbs the
nearest reachable line within a short window ahead, either end first (so a line
may be walked in reverse). Bounded window on purpose: unbounded would scatter
the fill's stroke order and cost O(n²) containment tests.

**Minimum-length filter** — new `min_stroke` param (mm, default 0 = off, so
existing projects are bit-identical). Opt-in like `connect_strokes`, because
silently dropping geometry from every hatch in every saved project is not a
default anyone asked for.

## Measured

Trefoil with a hole, spacing 1.1 mm, angle 30°, inset 0.3:

| | strokes (= lifts) | ink |
|---|---|---|
| `connect_strokes` off | 37 | 290 mm |
| v1 (straight-only, strict order) | 3–4 | 393 mm |
| v2 (hug + greedy) | 3 | 334 mm |

v2 beats v1 on *both* counts — fewer lifts and 15% less ink — because a hug
along the edge is shorter than the chord-plus-lift dance v1 was doing, and the
nearest-first search stops it reaching across the shape in the first place.

Cost: ~2.7× the un-joined resolve (109 ms vs 41 ms on a 588-scanline shape;
219 ms vs 80 ms at 1178 scanlines). First cut was 13× — fixed by caching each
ring's vertices indexed by arc length (bisect instead of a full re-walk),
bbox-prefiltering the "which ring is this point on" test, prepared geometry for
containment, and rejecting an over-budget arc by its span *before* materialising
it. Still worth knowing it isn't free: it is opt-in and it runs in the resolve
path.

## Verification

- `tests/test_modules_new.py`: `..._hugs_a_concave_boundary` (a shape whose
  right edge bows inward, where *every* row-to-row chord exits the shape —
  v1 joined nothing there, v2 joins all of it, and the test asserts the join
  actually followed the boundary rather than going straight),
  `..._still_lifts_when_there_is_no_way_round` (a comb — teeth share one ring
  but neither a chord nor a ring walk reaches the next tooth),
  `..._min_stroke_drops_slivers`, plus the existing opt-in/crosshatch/
  determinism tests unchanged.
- `..._still_lifts_around_a_hole` was **renamed and its expectation changed**
  to `..._routes_around_a_hole_without_crossing_it`: with a hug available, a
  square with a hole no longer forces a lift — there is a way around inside the
  material and the join finds it. What it must never do (and the test still
  asserts) is cut across the hole. The old assertion encoded v1's mechanism,
  not the contract.
- Visual: rendered off / v1 / v2 side by side with pen-down and pen-up markers.
  v1's stray chords across the fill are gone; v2 reads as a clean boustrophedon
  whose turns follow the outline.

## Left open

- Fragments below `min_stroke` are *dropped*, not absorbed into a neighbour.
  Absorbing (extending the adjacent line to cover the sliver's span) would keep
  the coverage; it needs a rule for what to do at a cusp where "adjacent" is
  ambiguous.
- The arc-length **resample** case for tween morphs between differently-shaped
  A/B (noted in the geometry-morph work) is unrelated but still open.
- `_STRAIGHT_SPAN` / `_DETOUR_EXTRA` are constants, not params. If bench work
  says different shapes want different thresholds, they are the two dials to
  expose — but adding them to the form before that evidence exists would be
  two more knobs on an already 7-field module.
