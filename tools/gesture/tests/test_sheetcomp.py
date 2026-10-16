import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import sheetcomp as sc  # noqa: E402


def _disc_mask(n=256, centres=((0.5, 0.5),), r=0.05):
    yy, xx = np.mgrid[0:n, 0:n] / n
    m = np.zeros((n, n), bool)
    for cx, cy in centres:
        m |= (xx - cx) ** 2 + (yy - cy) ** 2 < r * r
    return m


def test_lacunarity_even_vs_clustered():
    rng = np.random.default_rng(0)
    even = rng.random((256, 256)) < 0.05
    clustered = _disc_mask(centres=((0.3, 0.3),), r=0.12)
    assert sc.lacunarity(even, 32) < 1.1
    assert sc.lacunarity(clustered, 32) > 3.0


def test_profile_keys_and_ranges():
    m = _disc_mask(centres=((0.25, 0.25), (0.75, 0.75)), r=0.06)
    p = sc.profile(m)
    assert set(sc.PROFILE_KEYS) <= set(p)
    assert 0 < p["cover"] < 0.1
    assert p["empty16"] > 0.7
    assert abs(p["com_dx"]) < 0.02 and abs(p["com_dy"]) < 0.02
    assert p["islands_3"] == pytest.approx(np.log(2))
    assert p["void_max"] > 0.2


def test_mass_share_is_relative_to_the_sheets_own_line():
    m = _disc_mask(centres=((0.5, 0.5),), r=0.08)
    m[:, 20:22] = True                       # long thin lines set the line width
    m[:, 230:232] = True
    m[40:42, :] = True
    p = sc.profile(m)
    assert 0.4 < p["mass_share"] < 0.95


def test_profile_off_centre_and_margin():
    m = _disc_mask(centres=((0.05, 0.5),), r=0.04)
    p = sc.profile(m)
    assert p["com_dx"] < -0.4
    assert p["margin_ratio"] > 2.0


def test_render_mask_scale_invariant_cover():
    poly = [np.array([[10, 10], [500, 700], [800, 100]], float)]
    a = sc.render_mask(poly, (840, 1200), 3.0, long_side=512)
    b = sc.render_mask([q * 2 for q in poly], (1680, 2400), 6.0, long_side=512)
    assert a.shape == b.shape
    assert abs(a.mean() - b.mean()) < 0.2 * a.mean()


def test_layout_field_clears_requested_share():
    rng = np.random.default_rng(1)
    d = np.abs(rng.standard_normal((16, 12)))
    E = sc.layout_field(d, empty_q=0.4, smooth=0.0)
    assert 0.25 < float(np.mean(E > 0.5)) < 0.55
    assert np.all(sc.layout_field(d, empty_q=0.0) == 0)


def test_clear_composition_cuts_lines_keeps_whole_marks():
    from gesture.regime_field import Composition
    W, H = 100, 100
    line = np.column_stack([np.linspace(0, 100, 200), np.full(200, 50.0)])
    ring_in = np.array([[20, 20], [24, 20], [24, 24], [20, 24], [20, 20]], float)     # in the void (left)
    ring_out = np.array([[80, 80], [84, 80], [84, 84], [80, 84], [80, 80]], float)   # outside
    c = Composition([line, ring_in, ring_out], (W, H), {"pen_px": 1.0}, groups=[0, 1, 2],
                    kinds=["line", "fill", "fill"])
    E = np.zeros((10, 10))
    E[:, :5] = 1.0                                       # left half is void
    out, void = sc.clear_composition(c, E, tau=0.5, min_len_frac=0.0)
    xs = np.concatenate([q[:, 0] for q, k in zip(out.polylines, out.kinds) if k == "line"])
    assert xs.min() > 40                                 # the line was cut near the middle
    fills = [q for q, k in zip(out.polylines, out.kinds) if k == "fill"]
    assert len(fills) == 1 and np.allclose(fills[0], ring_out)   # whole mark kept, the void one dropped
    assert c.polylines[0] is line                        # input untouched


def test_distance_zero_to_self():
    m = _disc_mask(centres=((0.4, 0.6),), r=0.1)
    p = sc.profile(m)
    q = sc.profile(_disc_mask(centres=((0.2, 0.2), (0.8, 0.3)), r=0.03))
    s = sc.Scale.fit([p, q], sc.COMPOSITION_KEYS)
    assert sc.distance(p, p, s) == 0.0
    assert sc.distance(p, q, s) > 0.5


def _cross_comp():
    from gesture.regime_field import Composition
    h = np.column_stack([np.linspace(10, 90, 161), np.full(161, 50.0)])
    v = np.column_stack([np.full(161, 50.0), np.linspace(10, 90, 161)])
    return Composition([h, v], (100, 100), {"pen_px": 1.0}, groups=[0, 1], kinds=["line", "line"])


def test_junction_gaps_open_the_crossing():
    c = _cross_comp()
    out = sc.junction_gaps(c, 2, np.random.default_rng(0), gap_frac=0.1)
    assert len(out.polylines) > 2                       # at least one line broke in two
    for q in out.polylines:                             # no piece runs through the crossing
        assert np.min(np.linalg.norm(q - [50, 50], axis=1)) > 2.0 or len(out.polylines) == 3
    assert len(c.polylines) == 2                        # input untouched


def test_zoom_pushes_ink_out_and_cuts():
    c = _cross_comp()
    out = sc.zoom_composition(c, 1.5)
    allp = np.vstack(out.polylines)
    assert allp.min() >= 0 and allp.max() <= 100
    assert allp[:, 0].max() > 95
