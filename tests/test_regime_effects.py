"""Bitmap + fat tube: the Oehlen regime effects (contract + geometry checks)."""

import math

from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect


def _square(side=20.0, x0=40.0, y0=40.0, filled=True):
    pts = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side), (x0, y0)]
    return Path(points=pts, filled=filled)


# ---- bitmap (lines — the default) ---------------------------------------------------


def test_bitmap_lines_grid_and_axis_alignment():
    eff = get_effect("bitmap")
    diag = Path(points=[(10.3, 10.7), (52.1, 47.9)], filled=False)
    [out] = eff.apply([diag], eff.Params(cell=4.0), EffectContext(translation=(1.5, 0.0)))
    assert not out.filled
    for x, y in out.points:
        # every vertex lies on the grid anchored at the layer translation
        assert abs((x - 1.5) / 4.0 - round((x - 1.5) / 4.0)) < 1e-6
        assert abs(y / 4.0 - round(y / 4.0)) < 1e-6
    for (x0, y0), (x1, y1) in zip(out.points, out.points[1:]):
        # every segment is axis-aligned: exactly one coordinate moves
        assert (x0 == x1) != (y0 == y1)
    # a diagonal actually staircases — both axes are visited
    assert len({x for x, _ in out.points}) > 2 and len({y for _, y in out.points}) > 2


def test_bitmap_lines_identity_and_closure():
    eff = get_effect("bitmap")
    n = 24
    circle = Path(points=[(60 + 20 * math.cos(2 * math.pi * i / n),
                           60 + 20 * math.sin(2 * math.pi * i / n))
                          for i in range(n + 1)], filled=True)
    stroke = Path(points=[(10.0, 10.0), (30.0, 12.0)], filled=False)
    out = eff.apply([circle, stroke], eff.Params(cell=3.0), EffectContext())
    assert len(out) == 2  # one path in, one path out
    assert out[0].filled and out[0].points[0] == out[0].points[-1]
    assert not out[1].filled
    # repeated points collapsed
    for p in out:
        assert all(a != b for a, b in zip(p.points, p.points[1:]))


# ---- bitmap (blocks — the original raster treatment) --------------------------------


def test_bitmap_blocks_snaps_to_translated_grid():
    eff = get_effect("bitmap")
    diag = Path(points=[(10.3, 10.7), (52.1, 47.9)], filled=False)
    out = eff.apply([diag], eff.Params(style="blocks", cell=4.0),
                    EffectContext(translation=(1.5, 0.0)))
    assert out
    for p in out:
        assert p.filled and p.points[0] == p.points[-1]
        for x, y in p.points:
            # every vertex lies on the grid anchored at the layer translation
            assert abs((x - 1.5) / 4.0 - round((x - 1.5) / 4.0)) < 1e-6
            assert abs(y / 4.0 - round(y / 4.0)) < 1e-6


def test_bitmap_blocks_solid_fills_interior():
    eff = get_effect("bitmap")
    ctx = EffectContext()
    sq = _square(side=20.0)

    def area(paths):  # shoelace over exteriors minus holes ≈ lit area
        total = 0.0
        for p in paths:
            s = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(p.points, p.points[1:]))
            total += s / 2.0
        return abs(total)

    solid = eff.apply([sq], eff.Params(style="blocks", cell=2.0, solid=True), ctx)
    hollow = eff.apply([sq], eff.Params(style="blocks", cell=2.0, solid=False), ctx)
    assert area(solid) > area(hollow) * 1.5  # interior actually lit
    # a hollow bitmapped ring has a hole: exterior + interior rings
    assert len(hollow) >= 2


def test_bitmap_pure_deterministic_and_empty():
    eff = get_effect("bitmap")
    src = _square()
    before = [tuple(p) for p in src.points]
    for params in (eff.Params(), eff.Params(style="blocks")):
        a = eff.apply([src], params, EffectContext())
        b = eff.apply([src], params, EffectContext())
        assert [tuple(p) for p in src.points] == before
        assert [p.points for p in a] == [p.points for p in b]
        assert eff.apply([], params, EffectContext()) == []


# ---- fat tube -----------------------------------------------------------------------


def test_tube_width_and_closure():
    eff = get_effect("fat_tube")
    line = Path(points=[(50.0, 100.0), (150.0, 100.0)], filled=False)
    [out] = eff.apply([line], eff.Params(width=8.0), EffectContext())
    assert out.filled and out.points[0] == out.points[-1]
    ys = [y for _, y in out.points]
    xs = [x for x, _ in out.points]
    assert abs((max(ys) - min(ys)) - 8.0) < 0.2       # tube diameter
    assert abs((max(xs) - min(xs)) - 108.0) < 0.2     # round caps add w/2 each end


def test_tube_dot_becomes_disc():
    eff = get_effect("fat_tube")
    [disc] = eff.apply([Path(points=[(30.0, 30.0)], filled=False)],
                       eff.Params(width=6.0), EffectContext())
    assert disc.filled
    radii = [math.dist((30, 30), p) for p in disc.points]
    assert all(abs(r - 3.0) < 0.05 for r in radii)


def test_tube_self_crossing_merges_with_hole():
    eff = get_effect("fat_tube")
    # a loop: circle-ish path whose tube encloses paper -> exterior + hole
    n = 48
    loop = Path(points=[(60 + 15 * math.cos(2 * math.pi * i / n),
                         60 + 15 * math.sin(2 * math.pi * i / n)) for i in range(n + 1)],
                filled=False)
    out = eff.apply([loop], eff.Params(width=5.0), EffectContext())
    assert len(out) == 2  # ring outline + enclosed-paper hole
    assert all(p.filled and p.points[0] == p.points[-1] for p in out)


def test_tube_pure():
    eff = get_effect("fat_tube")
    src = _square(filled=False)
    before = [tuple(p) for p in src.points]
    eff.apply([src], eff.Params(), EffectContext())
    assert [tuple(p) for p in src.points] == before
