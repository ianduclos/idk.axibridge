"""Hand effect: a frozen library hand redraws any layer."""

import math

from axibridge import registry
from axibridge.model import Path, is_closed
from axibridge.registry import EffectContext, get_effect


def _square(x0=50.0, y0=50.0, side=60.0):
    pts = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side), (x0, y0)]
    return Path(points=pts, filled=True)


def _run(paths, ctx_seed=1, **kw):
    eff = get_effect("hand")
    return eff.apply(paths, eff.Params(**kw), EffectContext(layer_id="t", translation=(0, 0), seed=ctx_seed))


def test_registered_as_line_effect():
    registry.load_builtin_modules()
    assert "hand" in registry.effects()
    assert registry._EFFECT_LIBRARY_CATEGORIES["hand"] == "line"


def test_filled_square_stays_closed_and_filled():
    out = _run([_square()])
    assert len(out) == 1
    assert out[0].filled is True
    assert is_closed(out[0].points)
    assert len(out[0].points) > 5


def test_each_subpath_gets_its_own_seed():
    a, b = _square(10, 10), _square(110, 110)
    out = _run([a, b])
    da = [(x - 10, y - 10) for x, y in out[0].points]
    db = [(x - 110, y - 110) for x, y in out[1].points]
    assert da != db


def test_seed_and_ctx_seed_change_output():
    base = _run([_square()], seed=0, ctx_seed=1)[0].points
    assert _run([_square()], seed=5, ctx_seed=1)[0].points != base
    assert _run([_square()], seed=0, ctx_seed=2)[0].points != base
    assert _run([_square()], seed=0, ctx_seed=1)[0].points == base


def test_unknown_hand_returns_input_unchanged():
    src = [_square(), Path(points=[(0.0, 0.0), (50.0, 0.0)], filled=False)]
    out = _run(src, hand="no_such_hand_xyz")
    assert [p.points for p in out] == [p.points for p in src]
    assert [p.filled for p in out] == [p.filled for p in src]
    assert out[0] is not src[0]


def test_pin_for_other_hand_is_ignored_and_pin_accepted():
    out = _run([_square()], pin="someone_else@0123456789ab")
    assert is_closed(out[0].points)
    assert _run([_square()], pin="matisse@000000000000")[0].points == _square().points


def test_bend_lower_bound():
    eff = get_effect("hand")
    props = eff.Params.model_json_schema()["properties"]
    assert props["bend_mm"]["minimum"] == 3 and props["bend_mm"]["maximum"] == 200
