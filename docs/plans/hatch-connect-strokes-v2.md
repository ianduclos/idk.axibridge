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
