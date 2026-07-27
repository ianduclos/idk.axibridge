"""Brush source: the paint/erase fold, and the hole-by-nesting output contract.

The load-bearing test here is `test_repaint_over_an_erase_survives`, which
constructs the batched (union-all-then-difference-all) answer explicitly and
asserts the real implementation *differs* from it. That is the trap the brief
calls out, and it is invisible in every other test — batching passes all of
them.
"""

import math

import pytest
from shapely.geometry import LineString, Point, Polygon

from axibridge.registry import get_source
from axibridge.sources.brush import BrushParams, BrushStroke, _MAX_POINTS


def _src():
    return get_source("brush")


def _stroke(pts, mode="paint", radius=5.0):
    """Points as (x, y) for brevity — timestamps are captured but unused."""
    return {"points": [(x, y, i * 0.01) for i, (x, y) in enumerate(pts)],
            "mode": mode, "radius": radius}


def _run(strokes, **kw):
    return _src().generate(BrushParams(strokes=strokes, **kw))


def _paths(doc):
    return doc.layers[0].paths


def _region(doc):
    """Rebuild the emitted rings as a shapely area, holes read from nesting —
    the same even-odd rule compose.build_mask applies downstream."""
    polys = [Polygon(p.points) for p in _paths(doc) if len(p.points) >= 4]
    if not polys:
        return None
    region = polys[0]
    for poly in polys[1:]:
        region = region.symmetric_difference(poly)
    return region


def _area(doc):
    region = _region(doc)
    return 0.0 if region is None else region.area


# -- the basics ----------------------------------------------------------------

def test_one_stroke_is_one_filled_closed_region():
    doc = _run([_stroke([(50, 50), (100, 50)], radius=5.0)])
    paths = _paths(doc)
    assert len(paths) == 1
    assert paths[0].filled and paths[0].points[0] == paths[0].points[-1]
    expected = LineString([(50, 50), (100, 50)]).buffer(5.0).area
    assert abs(_area(doc) - expected) < expected * 0.02


def test_a_click_without_a_drag_is_a_dot():
    doc = _run([_stroke([(50, 50)], radius=4.0)])
    assert len(_paths(doc)) == 1
    assert abs(_area(doc) - Point(50, 50).buffer(4.0).area) < 2.0


def test_overlapping_paints_merge_into_one_region():
    doc = _run([_stroke([(50, 50), (80, 50)]), _stroke([(70, 50), (100, 50)])])
    assert len(_paths(doc)) == 1, "an overlap must merge, not leave two blobs"
    # strictly less than the two areas summed — the overlap is counted once
    lone = LineString([(50, 50), (80, 50)]).buffer(5.0).area
    assert _area(doc) < 2 * lone


def test_disjoint_paints_stay_separate():
    doc = _run([_stroke([(30, 30), (60, 30)]), _stroke([(150, 150), (180, 150)])])
    assert len(_paths(doc)) == 2


# -- erasing -------------------------------------------------------------------

def test_erase_bites_out_of_the_paint():
    painted = _run([_stroke([(40, 100), (160, 100)], radius=20.0)])
    bitten = _run([_stroke([(40, 100), (160, 100)], radius=20.0),
                   _stroke([(100, 100)], mode="erase", radius=10.0)])
    assert _area(bitten) < _area(painted)


def test_erase_strictly_inside_makes_a_hole_by_nesting():
    """Two closed filled rings — outer boundary and hole — with no hole flag:
    nesting alone marks it, and the area must reflect a real subtraction."""
    doc = _run([_stroke([(40, 100), (160, 100)], radius=25.0),
                _stroke([(100, 100)], mode="erase", radius=10.0)])
    paths = _paths(doc)
    assert len(paths) == 2 and all(p.filled for p in paths)
    inner, outer = sorted(paths, key=lambda p: Polygon(p.points).area)
    assert Polygon(outer.points).contains(Polygon(inner.points)), "hole must nest"
    solid = _run([_stroke([(40, 100), (160, 100)], radius=25.0)])
    assert _area(doc) < _area(solid) - 250.0  # ~pi*10^2 removed


def test_erase_before_any_paint_is_a_no_op():
    doc = _run([_stroke([(50, 50), (80, 50)], mode="erase")])
    assert _paths(doc) == []


def test_erasing_everything_is_empty_not_an_error():
    doc = _run([_stroke([(50, 50), (60, 50)], radius=3.0),
                _stroke([(40, 50), (70, 50)], mode="erase", radius=20.0)])
    assert _paths(doc) == []  # legitimate, if useless — must not raise


# -- the trap ------------------------------------------------------------------

def test_repaint_over_an_erase_survives():
    """Paint A, erase across it, then paint C back over the erased spot.

    The batched answer (union every paint, then subtract every erase) deletes
    C as well, because the subtraction cannot see that C came afterwards. Only
    a chronological fold gives the answer history implies. This test is the
    reason `_fold` exists; every other test in this file passes either way.
    """
    a = _stroke([(40, 100), (160, 100)], radius=20.0)
    erase = _stroke([(100, 60), (100, 140)], mode="erase", radius=15.0)
    c = _stroke([(100, 90), (100, 110)], radius=8.0)
    doc = _run([a, erase, c])

    # the deliberately-wrong implementation, spelled out
    from axibridge.sources.brush import _stamp
    from axibridge.sources.brush import BrushStroke as BS
    painted = _stamp(BS(**a), 8).union(_stamp(BS(**c), 8))
    batched = painted.difference(_stamp(BS(**erase), 8))

    assert _area(doc) > batched.area + 100.0, (
        "the repaint was swallowed — erases are being batched, not folded"
    )
    # and C's own centre really is inked in the folded result
    assert _region(doc).contains(Point(100, 100))


# -- contract ------------------------------------------------------------------

def test_no_strokes_raises():
    with pytest.raises(ValueError):
        _run([])


def test_deterministic():
    strokes = [_stroke([(40, 40), (90, 60), (120, 40)]),
               _stroke([(80, 50)], mode="erase", radius=6.0)]
    a, b = _run(strokes), _run(strokes)
    assert [p.points for p in _paths(a)] == [p.points for p in _paths(b)]


def test_points_are_bed_clamped():
    doc = _run([_stroke([(-500, -500), (5000, 5000)], radius=3.0)])
    for p in _paths(doc):
        for x, y in p.points:
            assert -3.1 <= x <= 303.1 and -3.1 <= y <= 221.1


def test_absurd_point_count_raises_cleanly():
    huge = [_stroke([(float(i % 300), 50.0)] * 1) for i in range(10)]
    huge[0]["points"] = [(float(i % 300), 50.0, 0.0) for i in range(_MAX_POINTS + 1)]
    with pytest.raises(ValueError, match="too dense"):
        _run(huge)


def test_radius_is_bounded_per_stroke():
    with pytest.raises(Exception):
        BrushStroke(points=[(1.0, 1.0, 0.0)], radius=500.0)
    with pytest.raises(Exception):
        BrushStroke(points=[(1.0, 1.0, 0.0)], radius=0.0)


def test_grow_fattens_the_finished_mass():
    plain = _run([_stroke([(50, 100), (150, 100)], radius=10.0)])
    fat = _run([_stroke([(50, 100), (150, 100)], radius=10.0)], grow=3.0)
    assert _area(fat) > _area(plain)
    thin = _run([_stroke([(50, 100), (150, 100)], radius=10.0)], grow=-3.0)
    assert _area(thin) < _area(plain)


def test_grow_does_not_reopen_seams_between_overlapping_strokes():
    """Growing the MERGED mass keeps it one region; growing each stroke before
    the union would too, but shrinking each would split it back into two."""
    doc = _run([_stroke([(50, 100), (90, 100)], radius=8.0),
                _stroke([(85, 100), (130, 100)], radius=8.0)], grow=-2.0)
    assert len(_paths(doc)) == 1


def test_output_survives_the_hatch_and_offset_fills():
    """A brush mass is a shape, not ink — it has to be fillable by both."""
    from axibridge.registry import EffectContext, get_effect
    doc = _run([_stroke([(60, 90), (140, 110)], radius=18.0),
                _stroke([(100, 100)], mode="erase", radius=7.0)])
    paths = _paths(doc)
    for effect_id in ("hatch_fill", "offset_fill"):
        eff = get_effect(effect_id)
        out = eff.apply(paths, eff.Params(), EffectContext())
        assert len(out) > len(paths), f"{effect_id} produced no fill"
        hole = Point(100, 100)
        for p in out:
            if p.filled:
                continue
            assert not hole.buffer(3.0).contains(Point(p.points[0])), (
                f"{effect_id} filled the erased hole"
            )
