"""gesture/shape_lexicon.py: EFD invariance, extraction on a synthetic
sheet, the sampler's policy gate and novelty, contiguous growth."""
import math

import numpy as np
import pytest

from gesture import calligraphy as cg
from gesture import shape_lexicon as sl
from gesture import signs


def _bean(n=300):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = 1 + 0.3 * np.cos(2 * t) + 0.15 * np.sin(3 * t)
    return np.column_stack([r * np.cos(t), 0.6 * r * np.sin(t)])


def _xf(c, ang, sc, sh, roll):
    R = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
    return np.roll(c @ R.T * sc + sh, roll, 0)


def _shape(c, **kw):
    base = dict(source="marden", sheet="s", kind="body", klass="terminal", D_w=5.0, generative=True)
    base.update(kw)
    return sl.shape_from_contour(c, **base)


def test_efd_invariant_to_similarity_and_start_point():
    c = _bean()
    a = _shape(_xf(c, 0.3, 5, [10, 4], 0))
    b = _shape(_xf(c, 2.5, 17, [-3, 40], 77))
    assert np.allclose(a.coeffs, b.coeffs, atol=1e-6)
    assert a.coeffs[0, 0] == pytest.approx(1.0)
    # clockwise input gives the same shape
    d = _shape(_xf(c, 1.0, 3, [0, 0], 0)[::-1])
    assert np.allclose(a.coeffs, d.coeffs, atol=1e-6)


def test_unit_frame_maps_outline_and_exits_onto_reconstruction():
    c = _xf(_bean(), 0.7, 9, [5, 5], 13)
    s = _shape(c, exits_px=c[[0, 150]])
    rec = sl.reconstruct(s.coeffs)
    from scipy.spatial import cKDTree
    assert cKDTree(rec).query(s.outline)[0].mean() < 0.02
    assert cKDTree(s.outline).query(s.exits)[0].max() < 0.05


def test_extract_finds_body_exits_counter_and_mark():
    H, W = 300, 400
    g = np.ones((H, W))
    yy, xx = np.mgrid[:H, :W]
    g[(xx - 100) ** 2 / 30 ** 2 + (yy - 150) ** 2 / 18 ** 2 <= 1] = 0.0      # a mass
    g[148:152, 130:220] = 0.0                                                 # its exit line
    ring = np.hypot(xx - 300, yy - 150)
    g[(ring > 25) & (ring < 29)] = 0.0                                        # a counter
    g[60:64, 250:290] = 0.0                                                   # a thin mark
    shapes, info = sl.extract_shapes(g, source="test", sheet="t", generative=True)
    kinds = {s.kind for s in shapes}
    assert {"body", "counter", "mark"} <= kinds
    body = [s for s in shapes if s.kind == "body"][0]
    assert body.meta["n_exits"] == 1 and body.klass == "terminal"


def _toy_lexicon():
    rng = np.random.default_rng(0)
    shapes = []
    for k in range(60):
        t = np.linspace(0, 2 * np.pi, 200, endpoint=False)
        r = 1 + rng.uniform(0, 0.3) * np.cos(2 * t + rng.uniform(0, 6)) + rng.uniform(0, 0.15) * np.sin(3 * t)
        c = np.column_stack([r * np.cos(t), rng.uniform(0.4, 0.9) * r * np.sin(t)]) * 20
        src = ["marden", "calligraphy", "print"][k % 3]
        kind, klass = (("counter", "loop") if k % 4 == 0 else ("body", "terminal"))
        sheet = "met-716305" if src == "calligraphy" else "x"
        s = _shape(c, source=src, sheet=sheet, kind=kind, klass=klass, generative=src != "print",
                   exits_px=c[[0]] if kind == "body" else None)
        shapes.append(s)
    return sl.Lexicon(shapes, k_clusters=4)


def test_sampler_returns_new_simple_outlines_from_generative_pool_only():
    from shapely.geometry import Polygon
    lex = _toy_lexicon()
    rng = np.random.default_rng(3)
    for _ in range(10):
        U, ex, info = lex.sample(rng, klass="terminal")
        assert Polygon(U).is_valid
        assert info["source"] != "print"
        # not a copy of any training outline
        d = min(np.abs(sl.reconstruct(s.coeffs) - U).max() for s in lex.shapes)
        assert d > 1e-3


def test_policy_gate_rejects_measure_only_calligraphy():
    lex = _toy_lexicon()
    lex.shapes[1] = sl.Shape(**{**lex.shapes[1].__dict__, "sheet": "wc-37", "generative": True})
    with pytest.raises(cg.PolicyError):
        lex.generative_pool(sources={"calligraphy"})


def test_grow_keeps_lines_contiguous():
    lex = _toy_lexicon()
    t = np.linspace(0, 1, 400)
    line = np.column_stack([5 + 60 * t, 20 + 3 * np.sin(2 * np.pi * t)])
    E = signs.LineEvent
    evs = [E("end", "drop", 0, 0.0, 3.0, 1.0, end=1), E("interior", "bead", 0, 20.0, 2.5, -1.0),
           E("interior", "ring", 0, 40.0, 3.0, 1.0)]
    paths, log = sl.grow_events([line], evs, lex, np.random.default_rng(1), w=0.6, pen=0.5)
    assert len(paths) == 1                      # one polyline: the line with its shapes
    p = paths[0]
    assert np.allclose(p[0], line[0])
    assert len(log) == 3 and any(g.filled for g in log)
    # every step of the spliced line is short except fill-ring hops (≤ shape size)
    steps = np.linalg.norm(np.diff(p, axis=0), axis=1)
    assert steps.max() < 3.5


def test_transition_stats_mi_zero_for_independent_and_positive_for_structured():
    a = np.array([0, 1, 0, 1, 2, 2] * 20)
    b = np.array([0, 1, 0, 1, 2, 2] * 20)
    st = sl.transition_stats(a, b, 3)
    assert st["mi"] > 0.5
    rng = np.random.default_rng(0)
    st0 = sl.transition_stats(rng.integers(0, 3, 4000), rng.integers(0, 3, 4000), 3)
    assert st0["mi"] < 0.01
