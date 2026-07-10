"""Continue-strokes effect: contract (purity, closure, determinism) + extension behavior."""

import math

from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect


def _square(side=60.0, x0=50.0, y0=50.0):
    pts = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side), (x0, y0)]
    return Path(points=pts, filled=True)


def _arc(cx=60.0, cy=60.0, r=30.0, n=40):
    pts = [(cx + r * math.cos(i * 0.06), cy + r * math.sin(i * 0.06)) for i in range(n)]
    return Path(points=pts, filled=False)


def _hline(length=120.0, y=100.0, x0=40.0):
    return Path(points=[(x0, y), (x0 + length, y)], filled=False)


def test_registered():
    eff = get_effect("continue_strokes")
    assert eff.label


def test_pure_and_deterministic():
    eff = get_effect("continue_strokes")
    src = _arc()
    before = [tuple(p) for p in src.points]
    ctx = EffectContext(seed=5)
    a = eff.apply([src], eff.Params(), ctx)
    b = eff.apply([src], eff.Params(), ctx)
    assert [tuple(p) for p in src.points] == before  # input untouched
    assert [p.points for p in a] == [p.points for p in b]


def test_seed_and_ctx_seed_vary_output():
    eff = get_effect("continue_strokes")
    src = _arc()
    params = eff.Params(temperature=0.8, seed=1)
    base = eff.apply([src], params, EffectContext(seed=0))[0]
    reseeded = eff.apply([src], eff.Params(temperature=0.8, seed=2), EffectContext(seed=0))[0]
    relayered = eff.apply([src], params, EffectContext(seed=9))[0]
    assert base.points != reseeded.points
    assert base.points != relayered.points


def test_closed_paths_pass_through_unchanged():
    eff = get_effect("continue_strokes")
    sq = _square()
    [out] = eff.apply([sq], eff.Params(), EffectContext())
    assert out.points == sq.points
    assert out.filled is True
    assert out is not sq  # still a new object (purity)


def test_extension_length_and_seam():
    eff = get_effect("continue_strokes")
    src = _arc()
    [out] = eff.apply([src], eff.Params(extension=30.0), EffectContext(seed=2))
    assert out.points[: len(src.points)] == src.points  # original stroke intact
    added = math.isclose(out.length(), src.length() + 30.0, rel_tol=0.02)
    assert added, (out.length(), src.length())
    # the continuation departs from the endpoint, not from anywhere else
    seam = math.dist(out.points[len(src.points)], src.points[-1])
    assert seam < 2.5


def test_both_ends():
    eff = get_effect("continue_strokes")
    src = _arc()
    [out] = eff.apply([src], eff.Params(extension=20.0, both_ends=True), EffectContext(seed=2))
    assert math.isclose(out.length(), src.length() + 40.0, rel_tol=0.02)
    assert src.points[0] in out.points and src.points[-1] in out.points


def test_straight_layer_continues_straight():
    # a layer of nothing but straight lines has near-zero turning statistics
    eff = get_effect("continue_strokes")
    [out] = eff.apply([_hline()], eff.Params(extension=40.0, temperature=0.0),
                      EffectContext(seed=1))
    ys = [y for _, y in out.points]
    assert max(ys) - min(ys) < 2.0  # stays essentially collinear


def test_degenerate_paths_pass_through():
    eff = get_effect("continue_strokes")
    dot = Path(points=[(10.0, 10.0)], filled=False)
    out = eff.apply([dot], eff.Params(), EffectContext())
    assert out[0].points == dot.points
    assert out[0] is not dot
