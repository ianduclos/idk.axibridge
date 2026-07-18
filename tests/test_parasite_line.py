"""Parasite line effect: contract (purity, closure, determinism) + mechanics."""

import copy
import math

from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect


def _squiggle(n=60, x0=20.0, y0=100.0, length=80.0, amp=15.0):
    pts = []
    for i in range(n):
        t = i / (n - 1)
        x = x0 + length * t
        y = y0 + amp * math.sin(t * math.tau * 1.3)
        pts.append((x, y))
    return Path(points=pts, filled=False)


def _square(side=40.0, x0=50.0, y0=50.0):
    pts = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side), (x0, y0)]
    return Path(points=pts, filled=True)


def _hline(length=100.0, y=100.0, x0=20.0):
    return Path(points=[(x0, y), (x0 + length, y)], filled=False)


def test_registered():
    eff = get_effect("parasite_line")
    assert eff.label


def test_purity_input_untouched():
    eff = get_effect("parasite_line")
    src = _squiggle()
    before = copy.deepcopy(src.points)
    ctx = EffectContext(seed=1)
    eff.apply([src], eff.Params(), ctx)
    assert src.points == before


def test_originals_present_verbatim():
    eff = get_effect("parasite_line")
    src = _squiggle()
    out = eff.apply([src], eff.Params(), EffectContext(seed=2))
    assert any(p.points == src.points and p.filled == src.filled for p in out)


def test_deterministic_under_seed():
    eff = get_effect("parasite_line")
    src = _squiggle()
    ctx = EffectContext(seed=5)
    a = eff.apply([src], eff.Params(seed=3), ctx)
    b = eff.apply([src], eff.Params(seed=3), ctx)
    assert [p.points for p in a] == [p.points for p in b]


def test_two_layers_differ_via_ctx_seed():
    eff = get_effect("parasite_line")
    src = _squiggle()
    a = eff.apply([src], eff.Params(seed=3), EffectContext(seed=1))
    b = eff.apply([src], eff.Params(seed=3), EffectContext(seed=2))
    a_parasites = [p.points for p in a if p.points != src.points]
    b_parasites = [p.points for p in b if p.points != src.points]
    assert a_parasites != b_parasites


def test_dash_zero_emits_one_polyline_per_parasite():
    eff = get_effect("parasite_line")
    src = _squiggle()
    out = eff.apply([src], eff.Params(dash_mm=0.0), EffectContext(seed=0))
    parasites = [p for p in out if p.points != src.points]
    assert len(parasites) == 1
    assert len(parasites[0].points) > 2


def test_dash_nonzero_emits_multiple_segments():
    eff = get_effect("parasite_line")
    src = _squiggle()
    out = eff.apply([src], eff.Params(dash_mm=1.2, gap_mm=1.0), EffectContext(seed=0))
    parasites = [p for p in out if p.points != src.points]
    assert len(parasites) > 1
    for seg in parasites:
        assert len(seg.points) >= 2
        assert seg.filled is False


def test_short_paths_skipped():
    eff = get_effect("parasite_line")
    short = Path(points=[(10.0, 10.0), (12.0, 10.0)], filled=False)  # 2mm < default min_length
    out = eff.apply([short], eff.Params(), EffectContext(seed=0))
    assert len(out) == 1  # original only, no parasite
    assert out[0].points == short.points


def test_closed_path_kept_closed_parasite_open():
    eff = get_effect("parasite_line")
    src = _square()
    out = eff.apply([src], eff.Params(), EffectContext(seed=0))
    original = [p for p in out if p.points == src.points][0]
    assert original.filled is True
    assert original.points[0] == original.points[-1]
    parasites = [p for p in out if p.points != src.points]
    assert parasites  # square is long enough to get a parasite
    for p in parasites:
        assert p.filled is False


def test_bounds_respected():
    eff = get_effect("parasite_line")
    import pytest
    with pytest.raises(Exception):
        eff.Params(offset=100.0)  # above le=15
    with pytest.raises(Exception):
        eff.Params(loopiness=2.0)  # above le=1


def test_side_left_right_opposite_signs():
    eff = get_effect("parasite_line")
    src = _hline()
    left = eff.apply([src], eff.Params(side="left", wander=0.0, loopiness=0.0), EffectContext(seed=0))
    right = eff.apply([src], eff.Params(side="right", wander=0.0, loopiness=0.0), EffectContext(seed=0))
    left_p = [p for p in left if p.points != src.points][0]
    right_p = [p for p in right if p.points != src.points][0]
    # a horizontal line's normal is vertical; left/right should offset opposite ways
    assert (left_p.points[0][1] - src.points[0][1]) * (right_p.points[0][1] - src.points[0][1]) < 0


def test_on_closed_false_skips_closed_paths():
    """Response-brush targeting: with on_closed off, a closed outline stays
    bare while open strokes still get their companion."""
    eff = get_effect("parasite_line")
    closed, open_ = _square(), _squiggle()
    out = eff.apply([closed, open_], eff.Params(on_closed=False), EffectContext(seed=0))
    added = [p for p in out if p.points not in ([closed.points], [open_.points])
             and p.points != closed.points and p.points != open_.points]
    assert added, "the open stroke should still grow a parasite"
    # every added point should hug the open squiggle, not the square
    def near(pt, path, tol=25.0):
        return any(math.dist(pt, q) < tol for q in path.points[::4])
    assert all(near(p.points[0], open_) for p in added)
