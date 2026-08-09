"""The arc-native offsetter, and the gate it has to pass before anyone trusts it.

Two halves, doing different jobs:

* **unit tests** on the primitives, each pinning a bug that actually happened
  while building this. Arc geometry fails silently — a wrong centre still
  passes through both endpoints, a wrong bridge still joins the gap — so every
  one of these is a specific silent failure, not a smoke test.
* **a differential test** against `offset_fill`'s shapely erosion. That is the
  gate: the arc engine does not become the default on the strength of looking
  right, it becomes the default when it agrees with the engine that has been
  plotting real ink for a month. It is not the default today.
"""

import math

import pytest
from shapely.geometry import Polygon

from axibridge.effects import _arcpoly
from axibridge.effects._arcpoly import (
    Contour, Vertex, arc_of, fit_contour, flatten, offset_contour,
)
from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect


def _ngon(n, r=40.0, cx=50.0, cy=50.0):
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    return pts + [pts[0]]


def _star(cx=60.0, cy=60.0, ro=50.0, ri=20.0, n=5):
    pts = [(cx + (ro if i % 2 == 0 else ri) * math.cos(-math.pi / 2 + i * math.pi / n),
            cy + (ro if i % 2 == 0 else ri) * math.sin(-math.pi / 2 + i * math.pi / n))
           for i in range(2 * n)]
    return pts + [pts[0]]


_SQUARE = [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0), (0.0, 0.0)]
_DUMBBELL = [(0.0, 0.0), (30.0, 0.0), (30.0, 12.0), (40.0, 12.0), (40.0, 0.0),
             (70.0, 0.0), (70.0, 30.0), (40.0, 30.0), (40.0, 18.0), (30.0, 18.0),
             (30.0, 30.0), (0.0, 30.0), (0.0, 0.0)]
_C_SHAPE = [(5.0, 5.0), (120.0, 5.0), (120.0, 35.0), (35.0, 35.0), (35.0, 90.0),
            (120.0, 90.0), (120.0, 120.0), (5.0, 120.0), (5.0, 5.0)]


def _area(pts):
    return abs(sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
                   for i in range(len(pts) - 1)) / 2.0)


# -- primitives ----------------------------------------------------------------

@pytest.mark.parametrize("name,p0,p1,sweep", [
    ("quarter ccw", (1.0, 0.0), (0.0, 1.0), math.pi / 2),
    ("semi ccw", (1.0, 0.0), (-1.0, 0.0), math.pi),
    ("three quarter ccw", (1.0, 0.0), (0.0, -1.0), 3 * math.pi / 2),
    ("quarter cw", (0.0, 1.0), (1.0, 0.0), -math.pi / 2),
    ("three quarter cw", (0.0, -1.0), (1.0, 0.0), -3 * math.pi / 2),
])
def test_arc_of_finds_the_right_centre_including_reflex(name, p0, p1, sweep):
    """A REFLEX arc puts its centre on the other side of the chord from a minor
    one. Get that backwards and the arc still passes through both endpoints —
    it is just on a completely different circle, which nothing notices until
    something offsets it."""
    (cx, cy), r, _, _, _ = arc_of(Vertex(*p0, math.tan(sweep / 4)), Vertex(*p1))
    assert math.hypot(cx, cy) < 1e-9, f"{name}: centre {cx},{cy} should be the origin"
    assert abs(r - 1.0) < 1e-9


def test_a_square_does_not_fit_as_a_circle():
    """The trap that makes a vertex-only deviation test useless: a square's four
    corners are concyclic, so a fitter that only checks vertices declares them a
    perfect circle and silently rounds the square off."""
    fitted = fit_contour(_SQUARE, 0.05)
    assert len(fitted) == 4
    assert all(v.bulge == 0.0 for v in fitted.vertices)


def test_a_fine_polygon_collapses_to_arcs_and_a_coarse_one_does_not():
    """The payoff and its limit. A 360-gon IS a circle within any useful
    tolerance and should cost a handful of arcs; a 24-gon is a shape whose flat
    edges the caller can see, and turning it into a circle would move geometry
    by more than the tolerance allows."""
    assert len(fit_contour(_ngon(360), 0.05)) <= 6
    assert len(fit_contour(_ngon(24), 0.05)) == 24


@pytest.mark.parametrize("n", [48, 96, 360])
def test_a_fitted_circle_flattens_back_within_tolerance(n):
    for tol in (0.05, 0.01):
        back = flatten(fit_contour(_ngon(n), tol), tol)
        worst = max(abs(math.dist(p, (50.0, 50.0)) - 40.0) for p in back)
        assert worst <= tol * 2, f"{n}-gon at tol={tol} came back {worst:.4f}mm out"


def test_offsetting_a_circle_is_exact_at_every_depth():
    """The whole reason for the bulge representation. Shapely tessellates on the
    way in and again on the way out, so its rings are polygons that get rougher
    the bigger they are; an arc offset keeps the same centre and changes one
    number."""
    fitted = fit_contour(_ngon(96), 0.05)
    for d in (0.5, 5.0, 20.0, 39.0):
        loops = offset_contour(fitted, d, 0.02)
        assert len(loops) == 1, f"d={d} gave {len(loops)} loops, want 1"
        radii = [math.dist(p, (50.0, 50.0)) for p in flatten(loops[0], 0.02)]
        assert max(abs(r - (40.0 - d)) for r in radii) < 1e-3


def test_a_square_offsets_to_an_exact_square_and_then_dies():
    for d in (5.0, 15.0, 19.0):
        loops = offset_contour(fit_contour(_SQUARE, 0.05), d, 0.02)
        assert len(loops) == 1
        assert abs(_area(flatten(loops[0], 0.02)) - (40.0 - 2 * d) ** 2) < 1e-3
    assert offset_contour(fit_contour(_SQUARE, 0.05), 21.0, 0.02) == []


def test_a_split_reports_itself_as_two_loops():
    """Topology needs no detection here either: the pruning pass hands back one
    loop per surviving region, so a dumbbell pinching at its neck simply returns
    two. This is the arc engine's version of shapely returning a MultiPolygon."""
    fitted = fit_contour(_DUMBBELL, 0.05)
    assert len(offset_contour(fitted, 2.0, 0.02)) == 1     # still one lobe pair
    for d in (3.5, 5.0, 9.0):
        loops = offset_contour(fitted, d, 0.02)
        assert len(loops) == 2, f"d={d} should have pinched into two"
        a, b = (_area(flatten(loop, 0.05)) for loop in loops)
        assert abs(a - b) < 1e-6, "the two lobes are mirror images"
    assert offset_contour(fitted, 16.0, 0.02) == []


def test_reflex_corners_survive_the_pruning():
    """A star's inner points are where the raw offset folds back over itself, so
    they are where the prune-and-stitch pass earns its keep. Areas must shrink
    monotonically and never jump."""
    fitted = fit_contour(_star(), 0.05)
    areas = []
    for d in (2.0, 8.0, 15.0):
        loops = offset_contour(fitted, d, 0.02)
        assert len(loops) == 1, f"d={d} gave {len(loops)} loops"
        areas.append(_area(flatten(loops[0], 0.05)))
    assert all(a > b for a, b in zip(areas, areas[1:])), areas
    assert offset_contour(fitted, 25.0, 0.02) == []


def test_the_last_millimetre_before_collapse_is_the_engines_weak_spot():
    """Where the arc offsetter is honestly not trustworthy, pinned so it stays
    known rather than becoming a surprise.

    Right at the depth a star's centre pinches out, the raw offset crosses
    itself many times over and the noding invents faces inside the tangle. They
    pass the "at least |d| clear of the source" test truthfully — near the
    centre there IS clearance — so the primitive returns slivers whose total
    area GROWS with depth, which erosion cannot do.

    The symmetric "no further than |d| either" test does not save it: a mitre
    spike at a sharp reflex corner sits legitimately further away, because the
    perpendicular foot falls off the end of the segment it measured against.
    What saves it is the invariant, enforced one level up in `_forest`, where
    the previous level is in hand — which is why this is a `_arcpoly`
    limitation and not an `offset_fill_v2` bug.
    """
    fitted = fit_contour(_star(), 0.05)
    tangle = sum(_area(flatten(loop, 0.05)) for loop in offset_contour(fitted, 17.0, 0.02))
    assert tangle > _area(flatten(offset_contour(fitted, 16.0, 0.02)[0], 0.05)), (
        "if the primitive stopped growing here on its own, the clip in _forest "
        "is no longer load-bearing and this test should become an equality"
    )


def test_the_effect_never_lets_a_level_grow():
    """...and the clip that makes the above harmless. Erosion is monotone; the
    forest holds every level, so that is where it gets enforced."""
    from shapely.geometry import Polygon as _P

    from axibridge.effects.offset_fill_v2 import OffsetFillV2Params, _forest

    shapes = {"star": _star(), "spiky": _star(ro=50.0, ri=10.0, n=9),
              "circle": _ngon(96), "c_shape": _C_SHAPE, "dumbbell": _DUMBBELL}
    for name, pts in shapes.items():
        for spacing in (0.7, 2.0, 4.0):
            params = OffsetFillV2Params(engine="arc", spacing=spacing, max_rings=200)
            areas = [sum(n.poly.area for n in level)
                     for level in _forest(_P(pts[:-1]), params)]
            assert all(b <= a + 1e-6 for a, b in zip(areas, areas[1:])), (
                f"{name} at spacing {spacing} grew: {areas}"
            )


def test_offsetting_repeatedly_does_not_drift():
    """The claim that makes iterative offsetting safe in arc space, where it is
    not in shapely's: stepping in ten times by 1 mm lands where one step of
    10 mm lands, because an arc offset is not an approximation.

    It also pins the ORIENTATION contract, which is what actually broke here.
    `polygonize` hands back faces in whatever winding it likes, so the first
    result came back clockwise and the second offset — still asking to go left
    of travel — grew the circle instead of shrinking it. Silent, and only
    visible if you offset twice.
    """
    step = fit_contour(_ngon(96), 0.02)
    for k in range(10):
        loops = offset_contour(step, 1.0, 0.01)
        assert len(loops) == 1, f"lost the loop on step {k + 1}"
        step = loops[0]
    radii = [math.dist(p, (50.0, 50.0)) for p in flatten(step, 0.01)]
    assert max(abs(r - 30.0) for r in radii) < 0.01, "10 mm of travel, 10 µm of drift"


# -- the gate ------------------------------------------------------------------

DIFFERENTIAL_SHAPES = {
    "square": [Path(points=_SQUARE, filled=True)],
    "circle": [Path(points=_ngon(96), filled=True)],
    "coarse_circle": [Path(points=_ngon(24), filled=True)],
    "star": [Path(points=_star(), filled=True)],
    "dumbbell": [Path(points=_DUMBBELL, filled=True)],
    "c_shape": [Path(points=_C_SHAPE, filled=True)],
    "donut": [Path(points=_ngon(96, r=50.0), filled=True),
              Path(points=_ngon(96, r=25.0), filled=True)],
}


def _rings(engine, paths, **kw):
    eff = get_effect("offset_fill_v2")
    out = eff.apply(paths, eff.Params(engine=engine, spiral=False, **kw), EffectContext())
    return [p.points for p in out if not p.filled]


@pytest.mark.parametrize("name", sorted(DIFFERENTIAL_SHAPES))
def test_arc_engine_agrees_with_shapely(name):
    """The gate. Both engines answer the same question — what is the set of
    points at least k spacings inside this shape — so they must produce the same
    rings. They will not produce the same VERTICES (that is the point of the arc
    engine), so the comparison is by count and by area, not vertex for vertex.

    Flipping the default to the arc engine is a separate decision that wants
    this list much longer than it is, and a hardware check behind it.

    The one licensed disagreement is the LAST level. ``buffer`` will hand back a
    polygon of area 0.0 for a shape that has just vanished, and `offset_fill`
    duly draws it — a ring of no size, plotted as a dot. The arc engine returns
    nothing, which is the better answer, so the count is allowed to be one short
    provided the ring shapely drew and it did not was degenerate.
    """
    paths = DIFFERENTIAL_SHAPES[name]
    kw = dict(spacing=4.0, max_rings=200, medial_tail=False)
    ours = _rings("arc", paths, **kw)
    theirs = _rings("shapely", paths, **kw)
    if len(ours) == len(theirs) - 1:
        assert _area(theirs[-1]) < 1.0, (
            f"{name}: arc engine is a whole real ring short, not a degenerate one"
        )
        theirs = theirs[:-1]
    assert len(ours) == len(theirs), (
        f"{name}: arc engine drew {len(ours)} rings, shapely drew {len(theirs)}"
    )
    for i, (a, b) in enumerate(zip(ours, theirs)):
        area_a, area_b = _area(a), _area(b)
        assert abs(area_a - area_b) <= max(0.02 * area_b, 1.0), (
            f"{name} ring {i}: arc area {area_a:.2f} vs shapely {area_b:.2f}"
        )


def test_the_arc_engine_is_not_the_default():
    """Deliberate, and the reason is in `_arcpoly`'s docstring: a wrong prune is
    not a crash, it is permanent wrong ink. This test is the tripwire on someone
    flipping it without widening the differential corpus above."""
    assert get_effect("offset_fill_v2").Params().engine == "shapely"


@pytest.mark.parametrize("n", [360, 1440])
def test_the_arc_engine_decouples_output_density_from_input_density(n):
    """What the whole exercise actually buys, stated as a measurement.

    Not "rounder" — at a matched tolerance both engines hit the tolerance, and
    on an already-fine input shapely hits it by inheriting the input's vertices.
    That IS the cost: shapely's rings carry however many points the source
    polyline had, whatever precision was asked for. The arc engine recovers the
    curve and re-flattens it to the tolerance, so a 1440-gon traced import and a
    96-gon one produce the same ring, at the requested accuracy, for about a
    twentieth of the vertices. On a plotter that is planning time and file size,
    and it is why `simplify` exists to fight the same problem downstream.
    """
    centre = (60.0, 60.0)
    paths = [Path(points=_ngon(n, r=50.0, cx=centre[0], cy=centre[1]), filled=True)]
    kw = dict(spacing=6.0, max_rings=200, medial_tail=False, simplify=0.0,
              tolerance=0.05)
    counts, errors = {}, {}
    for engine in ("arc", "shapely"):
        rings = _rings(engine, paths, **kw)
        counts[engine] = sum(len(r) for r in rings)
        err = 0.0
        for ring in rings:
            radii = [math.dist(p, centre) for p in ring]
            target = sum(radii) / len(radii)
            mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(ring, ring[1:])]
            err = max(err, max(abs(math.dist(m, centre) - target) for m in mids))
        errors[engine] = err
    # two tolerance-bounded steps compose — the fit may sit `tol` off the input
    # and the flatten another `tol` off the fit — so the honest bound is 2×,
    # which is also what the module's docstring claims and no more
    assert errors["arc"] <= 2 * 0.05, f"arc missed its own tolerance: {errors}"
    assert counts["arc"] * 3 < counts["shapely"], (counts, errors)
