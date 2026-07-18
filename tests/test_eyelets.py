"""Eyelets effect: contract (purity, closure, determinism) + structure-following mechanics."""

import copy
import math

from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect


def _square(side=40.0, x0=50.0, y0=50.0):
    pts = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side), (x0, y0)]
    return Path(points=pts, filled=True)


def _hline(length=100.0, y=100.0, x0=20.0):
    return Path(points=[(x0, y), (x0 + length, y)], filled=False)


def _smooth_arc(radius=60.0, cx=100.0, cy=100.0, span_deg=90.0, n=80):
    pts = []
    for i in range(n):
        a = math.radians(span_deg * i / (n - 1))
        pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return Path(points=pts, filled=False)


def _circles_only(paths, original):
    return [p for p in paths if p.points != original.points]


def test_registered():
    eff = get_effect("eyelets")
    assert eff.label


def test_purity_input_untouched():
    eff = get_effect("eyelets")
    src = _square()
    before = copy.deepcopy(src.points)
    eff.apply([src], eff.Params(), EffectContext(seed=1))
    assert src.points == before


def test_originals_present_verbatim():
    eff = get_effect("eyelets")
    src = _square()
    out = eff.apply([src], eff.Params(), EffectContext(seed=2))
    assert any(p.points == src.points and p.filled == src.filled for p in out)


def test_circles_closed():
    eff = get_effect("eyelets")
    src = _square()
    out = eff.apply([src], eff.Params(), EffectContext(seed=0))
    circles = _circles_only(out, src)
    assert circles
    for c in circles:
        assert c.points[0] == c.points[-1]
        assert c.filled is False


def test_deterministic():
    eff = get_effect("eyelets")
    src = _square()
    ctx = EffectContext(seed=5)
    a = eff.apply([src], eff.Params(seed=3), ctx)
    b = eff.apply([src], eff.Params(seed=3), ctx)
    assert [p.points for p in a] == [p.points for p in b]


def test_square_gets_eyelet_near_each_corner():
    eff = get_effect("eyelets")
    src = _square(side=40.0, x0=50.0, y0=50.0)
    out = eff.apply([src], eff.Params(sensitivity=0.5, spacing=5.0, at_ends=False), EffectContext(seed=0))
    circles = _circles_only(out, src)
    corners = [(50.0, 50.0), (90.0, 50.0), (90.0, 90.0), (50.0, 90.0)]
    for corner in corners:
        closest = min(math.dist(corner, c.points[0]) for c in circles)
        # eyelet center is on/near the line, nudged by at most `nudge`+radius-ish
        assert closest < 5.0, f"no eyelet near corner {corner} (closest {closest})"


def test_straight_line_gets_only_end_eyelets():
    eff = get_effect("eyelets")
    src = _hline()
    out = eff.apply([src], eff.Params(at_ends=True), EffectContext(seed=0))
    circles = _circles_only(out, src)
    assert len(circles) == 2  # start + end only, no interior curvature


def test_straight_line_no_ends_gets_nothing():
    eff = get_effect("eyelets")
    src = _hline()
    out = eff.apply([src], eff.Params(at_ends=False), EffectContext(seed=0))
    circles = _circles_only(out, src)
    assert len(circles) == 0


def test_smooth_arc_does_not_chain_rings():
    # a gentle continuous arc should not spawn a chain of eyelets at default
    # sensitivity — only genuinely angular gestures should
    eff = get_effect("eyelets")
    src = _smooth_arc()
    out = eff.apply([src], eff.Params(at_ends=False), EffectContext(seed=0))
    circles = _circles_only(out, src)
    assert len(circles) == 0


def _zigzag(n=10):
    # a zigzag with several sharp corners close together (~10.4mm apart along
    # the path, moving steadily forward in x so arc length tracks Euclidean
    # distance closely enough to compare the two directly)
    pts = [(10.0, 10.0)]
    x = 10.0
    for i in range(n):
        x += 3.0
        y = 10.0 if i % 2 == 0 else 20.0
        pts.append((x, y))
    return Path(points=pts, filled=False)


def test_spacing_enforced():
    eff = get_effect("eyelets")
    src = _zigzag()
    tight = eff.apply([src], eff.Params(sensitivity=0.3, spacing=2.0, at_ends=False), EffectContext(seed=0))
    loose = eff.apply([src], eff.Params(sensitivity=0.3, spacing=60.0, at_ends=False), EffectContext(seed=0))
    n_tight = len(_circles_only(tight, src))
    n_loose = len(_circles_only(loose, src))
    assert n_tight >= 3          # the zigzag has several real corners
    assert n_loose < n_tight     # widening spacing strictly reduces the count


def test_bounds_respected():
    import pytest
    eff = get_effect("eyelets")
    with pytest.raises(Exception):
        eff.Params(radius=10.0)  # above le=6
    with pytest.raises(Exception):
        eff.Params(sensitivity=2.0)  # above le=1


def test_closed_path_kept_closed_no_end_eyelets():
    eff = get_effect("eyelets")
    src = _square()
    out = eff.apply([src], eff.Params(at_ends=True), EffectContext(seed=0))
    original = [p for p in out if p.points == src.points][0]
    assert original.filled is True
    assert original.points[0] == original.points[-1]
    # closed paths have no distinct "ends" — every eyelet should be corner-driven
    circles = _circles_only(out, src)
    assert len(circles) == 4  # one per corner, none doubled at the seam


def test_on_closed_false_skips_closed_paths():
    """Response-brush targeting: with on_closed off, the closed square grows
    no rings while the open line still gets its end eyelets."""
    eff = get_effect("eyelets")
    square, line = _square(), _hline()
    out = eff.apply([square, line], eff.Params(on_closed=False, at_ends=True),
                    EffectContext(seed=0))
    circles = [p for p in out
               if p.points != square.points and p.points != line.points]
    # exactly the line's two end eyelets — the square's four corners grew none
    assert len(circles) == 2
