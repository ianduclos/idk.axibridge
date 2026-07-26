"""Offset fill: concentric-ring geometry, and the topology events it must survive.

The interesting half of this file is the topology group. Erosion is defined
for any shape, but it does not always hand back one closed curve — components
split and vanish, holes grow and merge — and the effect's claim is that those
need no special-casing. These pin that claim, plus the two axibridge-specific
traps the module docstring calls out (even-odd holes; rings not marked filled).
"""

import math

from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect


def _eff():
    return get_effect("offset_fill")


def _run(paths, **kw):
    eff = _eff()
    return eff.apply(paths, eff.Params(**kw), EffectContext())


def _square(side=40.0, x0=60.0, y0=60.0, filled=True):
    pts = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side), (x0, y0)]
    return Path(points=pts, filled=filled)


def _circle(cx=100.0, cy=100.0, r=20.0, n=96, filled=True):
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    return Path(points=pts + [pts[0]], filled=filled)


def _dumbbell(neck=6.0):
    """Two 30x30 lobes joined by a `neck`-tall bridge — pinches off at neck/2."""
    half = neck / 2
    return Path(points=[
        (0.0, 0.0), (30.0, 0.0), (30.0, 15.0 - half), (40.0, 15.0 - half),
        (40.0, 0.0), (70.0, 0.0), (70.0, 30.0), (40.0, 30.0),
        (40.0, 15.0 + half), (30.0, 15.0 + half), (30.0, 30.0), (0.0, 30.0), (0.0, 0.0),
    ], filled=True)


def _bounds(pts):
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _rings(out):
    """The generated rings — everything the effect added past the outlines."""
    return [p for p in out if not p.filled]


# -- the easy cases: the shape repeats inward ---------------------------------

def test_square_fills_with_concentric_squares():
    out = _run([_square(side=40.0)], spacing=2.0, medial_tail=False)
    rings = _rings(out)
    assert rings, "a 40mm square at 2mm spacing must produce rings"
    # every ring is still a 4-corner square (5 points with the closing repeat):
    # the shape repeats, it does not degrade into a rounded blob
    assert all(len(p.points) == 5 for p in rings)
    widths = sorted((_bounds(p.points)[2] - _bounds(p.points)[0]) for p in rings)
    # 40mm side, 2mm spacing -> rings at 36, 32, ... 4mm, stepping by 4 (2 each side)
    assert widths[-1] == 36.0 or abs(widths[-1] - 36.0) < 0.01
    steps = [b - a for a, b in zip(widths, widths[1:])]
    assert all(abs(s - 4.0) < 0.01 for s in steps), f"uneven ring spacing: {steps}"


def test_rings_are_concentric_with_the_original():
    out = _run([_square(side=40.0, x0=60.0, y0=60.0)], spacing=2.0, medial_tail=False)
    for p in _rings(out):
        x0, y0, x1, y1 = _bounds(p.points)
        assert abs((x0 + x1) / 2 - 80.0) < 0.01 and abs((y0 + y1) / 2 - 80.0) < 0.01


def test_corners_stay_sharp_at_depth():
    """Regression on the "erode from the original, never iteratively" rule.

    Iterative buffering re-rounds each corner it has already rounded, so the
    innermost rings would gain vertices and lose their corners. Computed from
    the original every time, ring 9 is as square as ring 1.
    """
    out = _run([_square(side=40.0)], spacing=2.0, join_style="round", medial_tail=False)
    assert all(len(p.points) == 5 for p in _rings(out))


def test_convex_shape_is_identical_under_every_join_style():
    """The module's corner claim: only REFLEX vertices take a join decision, so
    an all-convex shape cannot tell mitre from round from bevel."""
    variants = [
        [tuple(p.points) for p in _rings(_run([_square()], join_style=j))]
        for j in ("mitre", "round", "bevel")
    ]
    assert variants[0] == variants[1] == variants[2]


def test_circle_fills_with_circles():
    out = _run([_circle(r=20.0)], spacing=2.0, medial_tail=False)
    rings = _rings(out)
    assert rings
    for p in rings:
        x0, y0, x1, y1 = _bounds(p.points)
        radii = [math.dist((x, y), (100.0, 100.0)) for x, y in p.points]
        assert max(radii) - min(radii) < 0.2, "a circle's rings must stay round"


# -- topology: split, vanish, holes --------------------------------------------

def test_component_split_is_handled_without_special_casing():
    """A dumbbell pinches at the neck: past that depth one ring becomes two."""
    out = _run([_dumbbell(neck=6.0)], spacing=2.0, medial_tail=False)
    rings = _rings(out)
    # a ring deeper than the 3mm half-neck must live entirely in one lobe
    deep = [p for p in rings if (_bounds(p.points)[2] - _bounds(p.points)[0]) < 30.0]
    assert len(deep) >= 2, "the two lobes must fill as separate rings after the pinch"
    lefts = [p for p in deep if _bounds(p.points)[2] < 35.0]
    rights = [p for p in deep if _bounds(p.points)[0] > 35.0]
    assert lefts and rights, "the split must produce rings on BOTH sides of the neck"


def test_rings_stop_when_the_shape_vanishes():
    """Nothing is emitted past the inradius, however high max_rings is."""
    out = _run([_square(side=20.0)], spacing=2.0, max_rings=200, medial_tail=False)
    rings = _rings(out)
    assert 1 <= len(rings) <= 5, f"a 20mm square holds ~4 rings, got {len(rings)}"
    for p in rings:
        x0, y0, x1, y1 = _bounds(p.points)
        assert x0 >= 60.0 - 1e-6 and x1 <= 80.0 + 1e-6, "a ring escaped the shape"


def test_hole_is_not_filled_with_rings():
    """The even-odd trap: a donut is two nested filled loops in the IPR, and
    per-path offsetting would happily fill the hole. Nothing may enter it."""
    out = _run([_circle(r=20.0), _circle(r=8.0)], spacing=2.0, medial_tail=False)
    for p in _rings(out):
        for x, y in p.points:
            assert math.dist((x, y), (100.0, 100.0)) > 8.0 - 1e-6, "a ring entered the hole"


def test_hole_grows_as_the_outline_shrinks():
    """Both boundaries of an annulus erode toward the wall's middle."""
    out = _run([_circle(r=20.0), _circle(r=8.0)], spacing=2.0, medial_tail=False)
    radii = sorted({round(max(math.dist((x, y), (100.0, 100.0)) for x, y in p.points), 1)
                    for p in _rings(out)})
    assert any(r < 20.0 for r in radii), "the outer boundary must come inward"
    inner = [min(math.dist((x, y), (100.0, 100.0)) for x, y in p.points)
             for p in _rings(out)]
    assert any(r > 8.5 for r in inner), "the hole must grow outward"


def test_max_rings_caps_the_output():
    few = _rings(_run([_square(side=40.0)], spacing=1.0, max_rings=3, medial_tail=False))
    assert len(few) == 3


# -- round_center --------------------------------------------------------------

def test_round_center_softens_the_inner_rings():
    """A square's rings gain corner arcs as they go in — and the OUTER ring is
    less affected than the inner one, which is what makes the family morph."""
    rings = _rings(_run([_square(side=40.0)], spacing=2.0, round_center=1.0,
                        medial_tail=False))
    assert len(rings) >= 4
    by_size = sorted(rings, key=lambda p: -(_bounds(p.points)[2] - _bounds(p.points)[0]))
    assert len(by_size[0].points) > 5, "even the outer ring picks up corner arcs"
    assert len(by_size[1].points) > len(by_size[0].points), (
        "rounding must grow with depth, or the family does not morph"
    )


def test_round_center_zero_is_the_sharp_original():
    sharp = _rings(_run([_square()], spacing=2.0, round_center=0.0,
                        medial_tail=False))
    assert all(len(p.points) == 5 for p in sharp)


def test_rounding_never_costs_a_ring():
    """The back-off in `_level`: a rounding radius big enough to erode a ring
    away is halved until the ring exists. Ring COUNT is invariant."""
    for shape in ([_square(side=40.0)], [_circle(r=20.0)],
                  [Path(points=[(30.0, 4.0), (56.0, 52.0), (4.0, 52.0), (30.0, 4.0)],
                        filled=True)]):
        counts = {rc: len(_rings(_run(shape, spacing=2.0, round_center=rc)))
                  for rc in (0.0, 0.5, 1.0)}
        assert len(set(counts.values())) == 1, f"rounding changed ring count: {counts}"


def test_rounding_does_not_move_straight_runs():
    """An opening leaves flat edges exactly where they were, so ring spacing
    along an edge — the thing that makes the fill read as even — is untouched."""
    sharp = _rings(_run([_square(side=40.0)], spacing=2.0, round_center=0.0,
                        medial_tail=False))
    round_ = _rings(_run([_square(side=40.0)], spacing=2.0, round_center=1.0,
                         medial_tail=False))
    widths = lambda rs: sorted(_bounds(p.points)[2] - _bounds(p.points)[0] for p in rs)
    for a, b in zip(widths(sharp), widths(round_)):
        assert abs(a - b) < 0.01, "a ring's edge-to-edge span moved under rounding"


def test_rounded_rings_stay_inside_the_shape_and_out_of_holes():
    out = _run([_circle(r=20.0), _circle(r=8.0)], spacing=2.0, round_center=1.0)
    for p in _rings(out):
        for x, y in p.points:
            d = math.dist((x, y), (100.0, 100.0))
            assert 8.0 - 1e-6 < d < 20.0 + 1e-6, "a rounded ring escaped its band"


# -- thin areas ----------------------------------------------------------------

def test_medial_tail_closes_a_shape_too_thin_for_a_ring():
    sliver = Path(points=[(10.0, 10.0), (90.0, 10.0), (90.0, 13.0), (10.0, 13.0),
                          (10.0, 10.0)], filled=True)
    off = _rings(_run([sliver], spacing=2.0, medial_tail=False))
    on = _rings(_run([sliver], spacing=2.0, medial_tail=True))
    assert not off, "3mm at 2mm spacing has no room for a whole ring"
    assert on, "with the tail on it must get a centreline instead of reading hollow"
    _, y0, _, y1 = _bounds(on[0].points)
    assert 11.0 < (y0 + y1) / 2 < 12.0, "the tail should run down the middle"


def test_medial_tail_is_dropped_when_it_would_double_an_existing_ring():
    """A limb dying just AFTER a ring puts its centreline on top of that ring —
    three lines inside one spacing, which plots as a band of doubled ink."""
    # 22mm wall (r 31->9) at 2mm spacing dies ~0.5mm past the depth-10 ring
    donut = [_circle(r=31.0), _circle(r=9.0)]
    rings = _rings(_run(donut, spacing=2.0, medial_tail=True))
    radii = sorted(sum(math.dist((x, y), (100.0, 100.0)) for x, y in p.points)
                   / len(p.points) for p in rings)
    gaps = [b - a for a, b in zip(radii, radii[1:])]
    assert all(g > 0.9 for g in gaps), f"rings crowded into one band: {gaps}"


def test_medial_tail_of_an_annulus_is_its_centre_circle():
    out = _run([_circle(r=20.0), _circle(r=8.0)], spacing=2.0, medial_tail=True)
    radii = [math.dist((x, y), (100.0, 100.0)) for x, y in _rings(out)[-1].points]
    assert abs(sum(radii) / len(radii) - 14.0) < 0.3, "wall midline is r=14"


# -- contract ------------------------------------------------------------------

def test_inner_rings_are_not_marked_filled():
    """Marking rings filled would let occlusion's depth parity read the stack as
    alternating solid/hole and the layer would occlude as stripes."""
    out = _run([_square()], spacing=2.0)
    assert sum(1 for p in out if p.filled) == 1, "only the original outline is filled"
    assert all(p.points[0] == p.points[-1] for p in _rings(out)), "rings stay closed"


def test_outline_can_be_dropped():
    out = _run([_square()], spacing=2.0, outline=False)
    assert out and not any(p.filled for p in out)


def test_open_and_unfilled_paths_pass_through_untouched():
    stroke = Path(points=[(10.0, 10.0), (20.0, 20.0), (30.0, 15.0)], filled=False)
    dot = Path(points=[(50.0, 50.0)], filled=False)
    unfilled_loop = _square(filled=False)
    out = _run([stroke, dot, unfilled_loop], spacing=2.0)
    assert [p.points for p in out] == [stroke.points, dot.points, unfilled_loop.points]


def test_self_intersecting_input_does_not_crash():
    bowtie = Path(points=[(0.0, 0.0), (40.0, 40.0), (40.0, 0.0), (0.0, 40.0), (0.0, 0.0)],
                  filled=True)
    out = _run([bowtie], spacing=2.0)
    assert out and all(len(p.points) >= 2 for p in out)


def test_no_filled_shapes_is_a_pass_through():
    stroke = Path(points=[(1.0, 1.0), (2.0, 2.0)], filled=False)
    assert _run([stroke]) == [stroke]
