"""Contract / expand: signed-offset contract + geometry checks."""

import math

from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect


def _square(side=20.0, x0=40.0, y0=40.0, filled=True):
    pts = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side), (x0, y0)]
    return Path(points=pts, filled=filled)


def _bounds(paths):
    xs = [x for p in paths for x, _ in p.points]
    ys = [y for p in paths for _, y in p.points]
    return min(xs), min(ys), max(xs), max(ys)


def test_expand_grows_filled_shape():
    eff = get_effect("contract_expand")
    out = eff.apply([_square()], eff.Params(offset=5.0), EffectContext())
    assert out and all(p.filled and p.points[0] == p.points[-1] for p in out)
    x0, y0, x1, y1 = _bounds(out)
    assert abs((x1 - x0) - 30.0) < 0.1 and abs((y1 - y0) - 30.0) < 0.1


def test_contract_shrinks_filled_shape():
    eff = get_effect("contract_expand")
    out = eff.apply([_square()], eff.Params(offset=-5.0), EffectContext())
    x0, y0, x1, y1 = _bounds(out)
    assert abs((x1 - x0) - 10.0) < 0.1 and abs((y1 - y0) - 10.0) < 0.1


def test_contract_past_vanishing_emits_nothing():
    eff = get_effect("contract_expand")
    assert eff.apply([_square(side=20.0)], eff.Params(offset=-11.0), EffectContext()) == []


def test_open_stroke_offsets_sideways():
    eff = get_effect("contract_expand")
    line = Path(points=[(50.0, 100.0), (150.0, 100.0)], filled=False)
    [left] = eff.apply([line], eff.Params(offset=4.0), EffectContext())
    [right] = eff.apply([line], eff.Params(offset=-4.0), EffectContext())
    assert not left.filled and not right.filled
    assert all(abs(y - 104.0) < 1e-6 for _, y in left.points)
    assert all(abs(y - 96.0) < 1e-6 for _, y in right.points)


def test_zero_offset_passes_through():
    eff = get_effect("contract_expand")
    line = Path(points=[(10.0, 10.0), (30.0, 20.0)], filled=False)
    out = eff.apply([line], eff.Params(offset=0.0), EffectContext())
    assert [p.points for p in out] == [line.points]


def test_closed_stroke_stays_closed_and_dot_passes():
    eff = get_effect("contract_expand")
    n = 24
    ring = Path(points=[(60 + 15 * math.cos(2 * math.pi * i / n),
                         60 + 15 * math.sin(2 * math.pi * i / n))
                        for i in range(n + 1)], filled=False)
    dot = Path(points=[(30.0, 30.0)], filled=False)
    ring_out, dot_out = eff.apply([ring, dot], eff.Params(offset=3.0), EffectContext())
    assert ring_out.points[0] == ring_out.points[-1]
    radii = [math.dist((60, 60), p) for p in ring_out.points]
    # a parallel ring 3 mm to the (winding-dependent) side, not an outline
    assert all(abs(abs(r - 15.0) - 3.0) < 0.5 for r in radii)
    assert dot_out.points == [(30.0, 30.0)]


def test_stacked_offsets_make_onion_rings():
    eff = get_effect("contract_expand")
    ctx = EffectContext()
    first = eff.apply([_square()], eff.Params(offset=-3.0), ctx)
    second = eff.apply(first, eff.Params(offset=-3.0), ctx)
    x0, y0, x1, y1 = _bounds(second)
    assert abs((x1 - x0) - 8.0) < 0.1  # 20 − 2·(3+3)


def test_pure_and_deterministic():
    eff = get_effect("contract_expand")
    src = _square()
    before = [tuple(p) for p in src.points]
    a = eff.apply([src], eff.Params(), EffectContext())
    b = eff.apply([src], eff.Params(), EffectContext())
    assert [tuple(p) for p in src.points] == before
    assert [p.points for p in a] == [p.points for p in b]
    assert eff.apply([], eff.Params(), EffectContext()) == []
