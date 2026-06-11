"""Grid / flow field generators and the hatch fill effect."""

import math

from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect, get_source


def _gen(module_id, **params):
    src = get_source(module_id)
    return src.generate(src.Params(**params))


def test_grid_counts_and_trim():
    doc = _gen("grid", cells_x=4, cells_y=3, trim=0)
    assert len(doc.layers[0].paths) == (4 + 1) + (3 + 1)
    doc = _gen("grid", cells_x=4, cells_y=3, trim=1)  # the old "no border"
    assert len(doc.layers[0].paths) == (4 - 1) + (3 - 1)
    doc = _gen("grid", cells_x=8, cells_y=6, trim=2)
    assert len(doc.layers[0].paths) == (8 + 1 - 4) + (6 + 1 - 4)
    doc = _gen("grid", cells_x=2, cells_y=2, trim=10)  # over-trim: empty, not crash
    assert doc.layers[0].paths == []


def test_grid_overshoot_extends_past_area():
    margin = 15
    base = _gen("grid", width=100, height=80, margin=margin, overshoot_mm=0)
    shot = _gen("grid", width=100, height=80, margin=margin, overshoot_mm=10)
    bx = base.bounds()
    sx = shot.bounds()
    assert math.isclose(bx[2] - bx[0], 100)
    assert math.isclose(sx[2] - sx[0], 120)  # 10 mm out both sides
    # the line starts sit outside the grid area proper
    assert sx[0] < margin + 10  # document grew to hold the overshoot


def test_flowfield_spacing_respected():
    doc = _gen("flowfield", width=80, height=60, separation=4, seed=7)
    paths = doc.layers[0].paths
    assert paths, "field produced no streamlines"
    # no point of one line within separation/2 of another line's points
    r2 = (4 * 0.5) ** 2 * 0.95  # tolerance for the step quantisation
    pts_by_line = [p.points for p in paths]
    a = pts_by_line[0]
    for b in pts_by_line[1:3]:
        for x, y in a[:: max(len(a) // 20, 1)]:
            assert all((x - bx) ** 2 + (y - by) ** 2 > r2 * 0.5 for bx, by in b)


def test_flowfield_deterministic():
    d1 = _gen("flowfield", width=60, height=40, seed=3)
    d2 = _gen("flowfield", width=60, height=40, seed=3)
    assert [p.points for p in d1.layers[0].paths] == [p.points for p in d2.layers[0].paths]


def _square(filled=True):
    return Path(points=[(0, 0), (40, 0), (40, 40), (0, 40), (0, 0)], filled=filled)


def test_hatch_fill_fills_closed_filled_shapes():
    eff = get_effect("hatch_fill")
    src = _square()
    out = eff.apply([src], eff.Params(spacing=2.0, angle_deg=0, inset=1.0), EffectContext())
    outline = [p for p in out if p.filled]
    hatch = [p for p in out if not p.filled]
    assert len(outline) == 1 and outline[0].points == src.points  # kept, closure intact
    assert len(hatch) > 10
    for line in hatch:  # clipped inside the inset interior
        for x, y in line.points:
            assert 0.9 <= x <= 39.1 and 0.9 <= y <= 39.1
    assert src.points[0] == (0, 0)  # input not mutated


def test_hatch_fill_passes_open_and_unfilled_through():
    eff = get_effect("hatch_fill")
    open_line = Path(points=[(0, 0), (10, 10)])
    unfilled = _square(filled=False)
    out = eff.apply([open_line, unfilled], eff.Params(), EffectContext())
    assert out == [open_line, unfilled]


def test_hatch_fill_cross_doubles_coverage():
    eff = get_effect("hatch_fill")
    single = eff.apply([_square()], eff.Params(cross=False), EffectContext())
    double = eff.apply([_square()], eff.Params(cross=True), EffectContext())
    assert len(double) > len(single) * 1.7


def test_hatch_fill_treats_nested_loops_as_holes():
    eff = get_effect("hatch_fill")
    outer = _square()
    hole = Path(points=[(15, 15), (25, 15), (25, 25), (15, 25), (15, 15)], filled=True)
    out = eff.apply([outer, hole], eff.Params(spacing=2.0, angle_deg=0, inset=0), EffectContext())
    hatch = [p for p in out if not p.filled]
    assert hatch
    for line in hatch:
        for x, y in line.points:
            assert not (15.5 < x < 24.5 and 15.5 < y < 24.5), "hatch entered the hole"
