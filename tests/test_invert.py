"""Invert effect: the layer's ink as a hole in the page-boundary rectangle."""

import pytest
from shapely.geometry import Point, Polygon, box

from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect

BED = (0.0, 0.0, 300.0, 218.0)


def _ctx(page=BED):
    return EffectContext(page=page)


def _square(x0=50.0, y0=50.0, side=50.0, filled=True):
    return Path(points=[(x0, y0), (x0 + side, y0), (x0 + side, y0 + side),
                        (x0, y0 + side), (x0, y0)], filled=filled)


def _rings(out):
    return [Polygon(p.points) for p in out]


def _ink_area(out):
    """Ring areas with even-odd nesting: a ring adds or subtracts by how many
    other rings contain it (page +, hole −, island-in-hole +)."""
    rings = _rings(out)
    total = 0.0
    for i, r in enumerate(rings):
        depth = sum(1 for j, o in enumerate(rings) if i != j and o.contains(r))
        total += -r.area if depth % 2 else r.area
    return total


def test_registered():
    assert get_effect("invert").label == "Invert (page negative)"


def test_filled_square_becomes_a_hole():
    eff = get_effect("invert")
    out = eff.apply([_square()], eff.Params(), _ctx())
    assert len(out) == 2  # page exterior + the square hole
    assert all(p.filled and p.points[0] == p.points[-1] for p in out)
    assert _ink_area(out) == pytest.approx(300 * 218 - 2500, rel=1e-3)
    hole = min(_rings(out), key=lambda r: r.area)
    assert hole.contains(Point(75, 75))  # the shape's centre is open paper


def test_empty_input_is_the_full_page():
    eff = get_effect("invert")
    out = eff.apply([], eff.Params(), _ctx())
    assert _ink_area(out) == pytest.approx(300 * 218, rel=1e-3)


def test_margin_crops_the_boundary():
    eff = get_effect("invert")
    out = eff.apply([], eff.Params(margin=10.0), _ctx())
    assert _ink_area(out) == pytest.approx(280 * 198, rel=1e-3)
    xs = [x for p in out for x, _ in p.points]
    ys = [y for p in out for _, y in p.points]
    assert min(xs) >= 9.9 and min(ys) >= 9.9
    assert max(xs) <= 290.1 and max(ys) <= 208.1


def test_open_stroke_subtracts_a_band():
    eff = get_effect("invert")
    line = Path(points=[(0.0, 100.0), (300.0, 100.0)], filled=False)
    out = eff.apply([line], eff.Params(stroke_width=2.0), _ctx())
    # the 2mm band across the full bed splits the page into two regions
    assert _ink_area(out) == pytest.approx(300 * 218 - 300 * 2.0, rel=2e-2)
    rings = _rings(out)
    exterior_parts = [r for r in rings
                      if not any(o is not r and o.contains(r) for o in rings)]
    assert len(exterior_parts) == 2


def test_donut_hole_stays_paper():
    eff = get_effect("invert")
    outer = _square(40.0, 40.0, 80.0)
    inner = _square(60.0, 60.0, 40.0)  # nested ring = the donut's hole
    out = eff.apply([outer, inner], eff.Params(), _ctx())
    # negative = page − (donut mass) = page − outer + inner island of ink
    assert _ink_area(out) == pytest.approx(300 * 218 - 6400 + 1600, rel=1e-2)


def test_guide_rect_respected_and_bed_fallback():
    eff = get_effect("invert")
    out = eff.apply([], eff.Params(), _ctx(page=(10.0, 20.0, 100.0, 80.0)))
    assert _ink_area(out) == pytest.approx(100 * 80, rel=1e-3)
    from axibridge.registry import EffectContext as EC
    out2 = eff.apply([], eff.Params(), EC())  # no page: full bed fallback
    assert _ink_area(out2) == pytest.approx(300 * 218, rel=1e-3)


def test_margin_collapse_emits_nothing():
    eff = get_effect("invert")
    assert eff.apply([_square()], eff.Params(margin=50.0),
                     _ctx(page=(0.0, 0.0, 60.0, 60.0))) == []


def test_pure_and_deterministic():
    eff = get_effect("invert")
    src = [_square(), Path(points=[(0.0, 0.0), (300.0, 218.0)], filled=False)]
    before = [tuple(p) for p in src[0].points] + [tuple(p) for p in src[1].points]
    a = eff.apply(src, eff.Params(margin=5.0), _ctx())
    b = eff.apply(src, eff.Params(margin=5.0), _ctx())
    assert [p.points for p in a] == [p.points for p in b]
    after = [tuple(p) for p in src[0].points] + [tuple(p) for p in src[1].points]
    assert before == after


def test_end_to_end_through_resolve():
    """ctx.page flows from the project guide through the single resolve path."""
    from axibridge.session import session
    from axibridge.compose import PaperGuide

    layer = session.add_generated_layer("drawing", {"strokes": [
        [[50.0, 50.0, 0.0], [100.0, 50.0, 1.0]]], "resample_mm": 5.0})
    session.update_layer(layer.id, {"effects": [
        {"effect": "invert", "enabled": True, "params": {"stroke_width": 2.0}}]})
    session.project.guide = PaperGuide(x=0.0, y=0.0, width=200.0, height=150.0)
    resolved = session.resolved()
    out = resolved[layer.id]
    assert out and all(p.filled for p in out)
    xs = [x for p in out for x, _ in p.points]
    ys = [y for p in out for _, y in p.points]
    assert max(xs) <= 200.0 + 1e-6 and max(ys) <= 150.0 + 1e-6
