"""Offset fill v2: the spiral, and the tolerance that replaced the segment count.

`test_offset_fill.py` already pins the erosion behaviour this module inherits
wholesale — topology events, even-odd holes, medial tails, rings not marked
filled — and none of that is retested here. What IS here is the two things v2
claims on top, plus the control arm that proves it did not disturb v1:

* **one stroke instead of sixty.** Pen lifts were the whole reason v2 exists,
  so the tests count strokes, not vertices.
* **it may not put ink where ink does not belong.** A spiral is generated
  geometry that has to stay inside a shape and never double back over its own
  line — ink is permanent, and a self-crossing spiral is not a rounding error.
  The laps-stay-apart test pins the exact guarantee the `blend` parameter makes.
* **`spiral=False` still reproduces `offset_fill`.** That control arm is what
  makes the rest of this file trustworthy.
"""

import math

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from axibridge.effects.offset_fill_v2 import _quad_segs
from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect


def _run(paths, **kw):
    eff = get_effect("offset_fill_v2")
    return eff.apply(paths, eff.Params(**kw), EffectContext())


def _v1(paths, **kw):
    eff = get_effect("offset_fill")
    return eff.apply(paths, eff.Params(**kw), EffectContext())


def _strokes(out):
    """The generated marks — everything that is not a pass-through outline."""
    return [p for p in out if not p.filled]


def _square(side=120.0, x0=5.0, y0=5.0):
    return Path(points=[(x0, y0), (x0 + side, y0), (x0 + side, y0 + side),
                        (x0, y0 + side), (x0, y0)], filled=True)


def _circle(cx=65.0, cy=65.0, r=58.0, n=120):
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    return Path(points=pts + [pts[0]], filled=True)


def _star(cx=65.0, cy=65.0, ro=58.0, ri=24.0, n=5):
    pts = [(cx + (ro if i % 2 == 0 else ri) * math.cos(-math.pi / 2 + i * math.pi / n),
            cy + (ro if i % 2 == 0 else ri) * math.sin(-math.pi / 2 + i * math.pi / n))
           for i in range(2 * n)]
    return Path(points=pts + [pts[0]], filled=True)


def _dumbbell(neck=6.0):
    """Two lobes joined by a `neck`-tall bridge — pinches off at neck/2."""
    half = neck / 2
    return Path(points=[
        (0.0, 0.0), (30.0, 0.0), (30.0, 15.0 - half), (40.0, 15.0 - half),
        (40.0, 0.0), (70.0, 0.0), (70.0, 30.0), (40.0, 30.0),
        (40.0, 15.0 + half), (30.0, 15.0 + half), (30.0, 30.0), (0.0, 30.0), (0.0, 0.0),
    ], filled=True)


def _c_shape():
    """Long and thin: its contours barely shorten as they erode, which is the
    hard case for anything that joins rings together."""
    return Path(points=[(5.0, 5.0), (120.0, 5.0), (120.0, 35.0), (35.0, 35.0),
                        (35.0, 90.0), (120.0, 90.0), (120.0, 120.0), (5.0, 120.0),
                        (5.0, 5.0)], filled=True)


def _region(paths):
    """The even-odd region the effect fills, rebuilt the way the effect does."""
    region = None
    for p in paths:
        poly = Polygon(p.points)
        if not poly.is_valid:
            poly = poly.buffer(0)
        region = poly if region is None else region.symmetric_difference(poly)
    return unary_union([g for g in getattr(region, "geoms", [region])])


# -- the point of the exercise: pen lifts --------------------------------------

def test_a_convex_fill_is_one_unbroken_stroke():
    """v1 plots a 120mm square at 1mm spacing as 61 separate strokes, i.e. 61
    pen lifts. Every one of them is travel between rings a millimetre apart."""
    before = _strokes(_v1([_square()], spacing=1.0, max_rings=200))
    after = _strokes(_run([_square()], spacing=1.0, max_rings=200))
    assert len(before) > 50, "v1 baseline should be many rings"
    assert len(after) == 1, f"expected one spiral, got {len(after)} strokes"


def test_the_spiral_is_open_and_the_outline_still_carries_the_fill():
    """The outline stays a separate FILLED path: occlusion masks are built from
    filled outlines, so folding it into the spiral would lose the layer's
    solidity. Everything the effect generates is unfilled, exactly as in v1."""
    out = _run([_circle()], spacing=3.0)
    assert sum(1 for p in out if p.filled) == 1
    spiral = _strokes(out)[0]
    assert spiral.points[0] != spiral.points[-1], "a spiral is an open stroke"


def test_a_hole_forces_the_ring_fallback():
    """A spiral only exists for a hole-free component. A donut has one from the
    start, so v2 must fall back to rings rather than invent a crossing."""
    donut = [_circle(r=50.0), _circle(r=25.0)]
    assert len(_strokes(_run(donut, spacing=2.0))) == len(_strokes(_v1(donut, spacing=2.0)))


def test_a_split_spirals_down_to_the_pinch_then_falls_back():
    """A dumbbell is one component until its neck pinches, then two. The chain
    condition ends at the split; below it each lobe starts its own spiral, and
    the result is far fewer strokes than rings but more than one."""
    out = _strokes(_run([_dumbbell()], spacing=1.0, max_rings=200))
    rings = _strokes(_v1([_dumbbell()], spacing=1.0, max_rings=200))
    assert 1 < len(out) < len(rings) / 3


def test_a_thin_limb_finishes_the_spiral_instead_of_lifting_for_it():
    """`medial_tail` draws a centreline down a limb too narrow for another ring.
    In v1 that is one more separate stroke; here it is one more turn, because a
    dying limb's centreline is simply the next level down."""
    star = [_star(ri=14.0)]
    with_tail = _strokes(_run(star, spacing=3.0, medial_tail=True))
    without = _strokes(_run(star, spacing=3.0, medial_tail=False))
    assert len(with_tail) == len(without), "the tail must not cost a pen lift"


# -- it may not put ink where ink does not belong ------------------------------

SHAPES = {
    "square": [_square()],
    "circle": [_circle()],
    "star": [_star()],
    "spiky": [_star(ri=10.0, n=12)],
    "c_shape": [_c_shape()],
    "dumbbell": [_dumbbell()],
    "donut": [_circle(r=50.0), _circle(r=25.0)],
}


def test_no_stroke_ever_leaves_the_shape():
    """The blend is a straight chord between two nested rings; across a deep
    concavity that chord can cut the corner and leave the region. `_safe_lerp`
    is the guard, and this is what it guards."""
    for name, paths in SHAPES.items():
        region = _region(paths).buffer(1e-6)
        for blend in (0.0, 0.5, 1.0):
            for p in _strokes(_run(paths, spacing=1.5, max_rings=200, blend=blend)):
                escaped = LineString(p.points).difference(region).length
                assert escaped < 1e-6, f"{name} blend={blend} left the shape by {escaped}mm"


def _self_crossings(pts, tol=1e-6):
    """Self-touches that are NOT a vertex the stroke deliberately revisits.

    A spiral legitimately revisits one point per closed lap — the innermost lap
    closes on itself, and at `blend` 0 every lap does. Those are touches, not
    crossings, and `is_simple` cannot tell the difference; this can.
    """
    line = LineString(pts)
    if line.is_simple:
        return []
    revisited = [p for p in set(pts) if pts.count(p) > 1]
    noded = unary_union(line)
    ends = set()
    for part in getattr(noded, "geoms", [noded]):
        ends.add(part.coords[0])
        ends.add(part.coords[-1])
    return [e for e in ends
            if not any(math.dist(e, r) < tol for r in revisited)
            and math.dist(e, pts[0]) >= tol and math.dist(e, pts[-1]) >= tol]


def test_no_stroke_ever_crosses_itself():
    """Ink is permanent: a spiral that doubles back over its own line has drawn
    something the user cannot undo."""
    for name, paths in SHAPES.items():
        for blend in (0.0, 0.35, 0.5, 1.0):
            for sp in (1.0, 2.5):
                for p in _strokes(_run(paths, spacing=sp, max_rings=200, blend=blend)):
                    bad = _self_crossings(p.points)
                    assert not bad, f"{name} blend={blend} spacing={sp} crosses at {bad[:2]}"


def _doubled_ink(strokes, spacing, samples=500):
    """Percent of the inked length running within half a spacing of a stretch
    that is not its own neighbourhood — i.e. what would plot as a dark smudge.

    Not "closest approach", which any spiral fails: at the seam a lap comes back
    to where it started before hopping inward, so consecutive turns always MEET
    somewhere. A crossing costs one pen width; a converging stretch costs a
    smudge. This measures the second.
    """
    xy, arc, sid = [], [], []
    for i, pts in enumerate(strokes):
        if len(pts) < 2:
            continue
        line = LineString(pts)
        n = max(50, min(samples, int(line.length / (spacing / 4))))
        d = np.linspace(0.0, line.length, n)
        xy.append(np.array([line.interpolate(t).coords[0] for t in d]))
        arc.append(d)
        sid.append(np.full(n, i))
    if not xy:
        return 0.0
    xy, arc, sid = np.vstack(xy), np.concatenate(arc), np.concatenate(sid)
    gap = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
    elsewhere = (sid[:, None] != sid[None, :]) | (np.abs(arc[:, None] - arc[None, :])
                                                  > spacing * 3)
    return float(((gap < spacing * 0.5) & elsewhere).any(axis=1).mean() * 100.0)


def test_the_spiral_does_not_plot_as_doubled_ink():
    """The `blend` parameter's contract, on the shapes that expose it.

    Laps hold their spacing because they drift in lockstep — but the innermost
    lap has nothing to drift toward, so the lap above slides onto it. Capping
    the drift at `blend` bounds the parallel-stretch separation at
    (1 − blend) × spacing, and at the default that keeps the spiral no darker
    than the rings it replaces.

    A C is the hard case and a square is not: a C's contours barely shorten as
    they erode, so its innermost lap is nearly as long as its outermost and the
    colliding pair is a large slice of the whole fill.
    """
    spacing = 4.0
    for name in ("c_shape", "square", "star", "circle"):
        rings = _doubled_ink([p.points for p in _strokes(
            _v1(SHAPES[name], spacing=spacing, max_rings=200, medial_tail=False))], spacing)
        for blend in (0.0, 0.25, 0.5):
            spun = _doubled_ink([p.points for p in _strokes(
                _run(SHAPES[name], spacing=spacing, max_rings=200,
                     blend=blend, medial_tail=False))], spacing)
            assert spun <= rings + 4.0, (
                f"{name} blend={blend}: {spun:.1f}% of the spiral plots as doubled "
                f"ink, against {rings:.1f}% for the rings it replaces"
            )


def test_pushing_blend_past_the_default_is_what_costs_you():
    """The documented price of a perfectly smooth spiral, pinned so it cannot
    drift: at blend 1.0 the innermost turns touch, and on a long thin shape
    that is a large fraction of the fill. This is why the default is 0.5 and
    the parameter's description says what it says."""
    c = _doubled_ink([p.points for p in _strokes(
        _run(SHAPES["c_shape"], spacing=4.0, max_rings=200, blend=1.0,
             medial_tail=False))], 4.0)
    assert c > 15.0, "if this dropped, the blend cap changed — update the docs"


# -- the control arm -----------------------------------------------------------

def test_spiral_off_reproduces_offset_fill_exactly():
    """With the spiral off and mitre joins, v2 must be `offset_fill` path for
    path — same rings, same order, same vertices. Every other test in this file
    leans on that: it is what says the spiral was added to the module rather
    than in place of something."""
    for name, paths in SHAPES.items():
        for kw in ({}, {"spacing": 1.0, "max_rings": 200}, {"medial_tail": False},
                   {"outline": False}, {"spacing": 0.6, "max_rings": 200}):
            a = _v1(paths, **kw)
            b = _run(paths, spiral=False, **kw)
            assert [(p.filled, p.points) for p in a] == [(p.filled, p.points) for p in b], \
                f"{name} {kw} diverged from offset_fill"


def test_round_joins_differ_from_v1_only_in_flattening_density():
    """The one place `spiral=False` is NOT byte-identical, and deliberately so:
    round joins are flattened to a tolerance now instead of a fixed segment
    count. Same rings in the same order — a different number of points on them."""
    a = _v1([_square()], round_center=0.7)
    b = _run([_square()], round_center=0.7, spiral=False)
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert LineString(x.points).hausdorff_distance(LineString(y.points)) < 0.2


def test_open_and_unfilled_paths_pass_through_untouched():
    stroke = Path(points=[(10.0, 10.0), (20.0, 20.0), (30.0, 15.0)], filled=False)
    dot = Path(points=[(50.0, 50.0)], filled=False)
    loop = Path(points=[(1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 1.0)], filled=False)
    out = _run([stroke, dot, loop], spacing=2.0)
    assert [p.points for p in out] == [stroke.points, dot.points, loop.points]


# -- tolerance instead of a segment count --------------------------------------

def test_quad_segs_holds_the_tolerance_at_every_radius():
    """v1's fixed 8 segments per quarter meant 0.005mm of error at a 1mm radius
    and 0.53mm at 110mm — finer than anyone asked for on small corners, coarser
    than a pen width on big ones. The whole point is that this does not happen."""
    for tol in (0.05, 0.02):
        for r in (0.5, 1.0, 5.0, 24.0, 60.0, 110.0):
            q = _quad_segs(r, tol)
            sagitta = r * (1.0 - math.cos(math.pi / 2 / q / 2))
            assert sagitta <= tol + 1e-9 or q == 64, (
                f"r={r} tol={tol}: {q} segments leave {sagitta:.4f}mm of error"
            )


def test_quad_segs_tracks_scale_in_both_directions():
    """Cheaper than v1 where v1 was wasteful, finer where v1 was coarse."""
    assert _quad_segs(1.0, 0.05) < 8 < _quad_segs(60.0, 0.05)


def test_a_finer_tolerance_buys_a_rounder_corner():
    """`simplify` is held at 0 here on purpose. It thins the finished rings, so
    left at its default it hands back the same vertex count whatever tolerance
    asked for — which is exactly the trap its own description warns about.

    A square, not a circle: `join_style` is mitre by default and eroding a
    CONVEX polygon with mitre joins draws no arcs at all, so a 120-gon circle
    comes back a 120-gon at every tolerance. `round_center` on a square is the
    case that actually generates arcs — sharp convex corners opened into
    quarter-round ones.
    """
    kw = dict(spacing=6.0, round_center=1.0, spiral=False, simplify=0.0)
    coarse = _run([_square()], tolerance=0.5, **kw)
    fine = _run([_square()], tolerance=0.01, **kw)
    assert sum(len(p.points) for p in fine) > 2 * sum(len(p.points) for p in coarse)
