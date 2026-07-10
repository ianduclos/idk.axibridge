"""Freehand effect: contract (purity, closure, determinism) + hand character."""

import math

from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect


def _square(side=60.0, x0=50.0, y0=50.0):
    pts = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side), (x0, y0)]
    return Path(points=pts, filled=True)


def _hline(length=120.0, y=100.0, x0=40.0):
    return Path(points=[(x0, y), (x0 + length, y)], filled=False)


def _dist_to_polyline(p, pts):
    best = math.inf
    for a, b in zip(pts, pts[1:]):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
        best = min(best, math.dist(p, (ax + dx * t, ay + dy * t)))
    return best


def test_registered():
    eff = get_effect("freehand")
    assert eff.label


def test_pure_and_deterministic():
    eff = get_effect("freehand")
    src = _square()
    before = [tuple(p) for p in src.points]
    ctx = EffectContext(seed=5)
    a = eff.apply([src], eff.Params(), ctx)
    b = eff.apply([src], eff.Params(), ctx)
    assert [tuple(p) for p in src.points] == before  # input untouched
    assert [p.points for p in a] == [p.points for p in b]


def test_seed_and_ctx_seed_vary_output():
    eff = get_effect("freehand")
    src = _hline()
    base = eff.apply([src], eff.Params(seed=1), EffectContext(seed=0))[0]
    reseeded = eff.apply([src], eff.Params(seed=2), EffectContext(seed=0))[0]
    relayered = eff.apply([src], eff.Params(seed=1), EffectContext(seed=9))[0]
    assert base.points != reseeded.points
    assert base.points != relayered.points


def test_closure_and_filled_preserved():
    eff = get_effect("freehand")
    [out] = eff.apply([_square()], eff.Params(), EffectContext())
    assert out.filled is True
    assert out.points[0] == out.points[-1]
    [line] = eff.apply([_hline()], eff.Params(), EffectContext())
    assert line.filled is False


def test_stays_near_intention():
    # gentle settings: the hand wanders but stays within a few mm of the line
    eff = get_effect("freehand")
    params = eff.Params(tremor=0.6, fatigue=0.2, correction=0.5)
    [out] = eff.apply([_square()], params, EffectContext(seed=3))
    worst = max(_dist_to_polyline(p, _square().points) for p in out.points)
    assert 0.05 < worst < 8.0  # visibly imperfect, still recognisably the square


def test_tremor_zero_is_calm_but_still_lags():
    eff = get_effect("freehand")
    [out] = eff.apply([_hline()], eff.Params(tremor=0.0, impulsiveness=0.0), EffectContext())
    worst = max(_dist_to_polyline(p, _hline().points) for p in out.points)
    assert worst < 0.5  # no noise -> essentially faithful on a straight line


def test_degenerate_paths_pass_through():
    eff = get_effect("freehand")
    dot = Path(points=[(10.0, 10.0)], filled=False)
    tiny = Path(points=[(10.0, 10.0), (10.05, 10.0)], filled=False)
    out = eff.apply([dot, tiny], eff.Params(), EffectContext())
    assert out[0].points == dot.points
    assert out[1].points == tiny.points
    assert out[0] is not dot  # still a new object (purity)
