"""Sub-pixel centreline refinement: error reduction, crossings, purity,
determinism. Small synthetic canvases; the file runs in a few seconds."""
import numpy as np
import pytest
from scipy.spatial import cKDTree

from gesture import synth
from gesture.core import Drawing, Stroke
from gesture.curvature import kappa_s, resample
from gesture.extract import extract
from gesture.extract_eval import score_gt
from gesture.subpixel import refine_centrelines

SIZE = (400, 400)
LW = 4.0


def _gray(d, lw=LW, noise=0.03):
    return synth.render(d, line_width=lw, paper_noise=noise, use_stroke_width=False,
                        seed=3).astype(np.float64) / 255.0


def _err(found: Drawing, truth: Drawing) -> float:
    """Mean distance from found points (1 px resample) to the true polyline."""
    T = np.vstack([resample(s.points, 0.1, s.closed) for s in truth.strokes])
    F = np.vstack([resample(s.points, 1.0, s.closed) for s in found.strokes])
    return float(cKDTree(T).query(F)[0].mean())


@pytest.fixture(scope="module")
def loop():
    truth = synth.scene_closed_loop(SIZE)
    return truth, _gray(truth)


def _perturbed(truth: Drawing, amp=1.0, period=25.0) -> Drawing:
    out = []
    for s in truth.strokes:
        p = resample(s.points, 1.0, s.closed)
        d = np.roll(p, -1, 0) - np.roll(p, 1, 0)
        t = d / np.linalg.norm(d, axis=1, keepdims=True)
        n = np.column_stack([-t[:, 1], t[:, 0]])
        sv = np.arange(len(p))
        off = amp * np.sign(np.sin(2 * np.pi * sv / period)) * (0.6 + 0.4 * np.cos(sv / 7.0))
        out.append(Stroke(p + off[:, None] * n, width=np.full(len(p), LW), closed=s.closed,
                          meta={"tag": "x"}))
    return Drawing(out, size=truth.size, meta={"m": 1})


@pytest.mark.parametrize("method", ["core", "steger"])
def test_reduces_centre_error(loop, method):
    truth, g = loop
    noisy = _perturbed(truth)
    e0 = _err(noisy, truth)
    r = refine_centrelines(g, noisy, method=method)
    e1 = _err(r, truth)
    assert e0 > 0.45
    assert e1 < 0.35 * e0, (e0, e1)
    # and κ: the wobble is gone at the scale the statistics read (σ = 2w)
    k0 = score_gt(truth, noisy, LW)["kappa_err"]
    k1 = score_gt(truth, r, LW)["kappa_err"]
    assert k1 < 0.3 * k0, (k0, k1)


def test_contract_kept(loop):
    truth, g = loop
    noisy = _perturbed(truth)
    r = refine_centrelines(g, noisy)
    assert len(r.strokes) == len(noisy.strokes)
    assert r.size == noisy.size and r.meta["m"] == 1 and "subpixel" in r.meta
    for a, b in zip(noisy.strokes, r.strokes):
        assert b.closed == a.closed
        assert b.width is not None and b.width.shape == (len(b),)
        assert b.meta["tag"] == "x"
        assert not np.allclose(b.points[0], b.points[-1])        # closed: no repeat
        assert np.all(np.isfinite(b.points))


def test_purity_and_determinism(loop):
    truth, g = loop
    noisy = _perturbed(truth)
    g0 = g.copy()
    p0 = [s.points.copy() for s in noisy.strokes]
    w0 = [s.width.copy() for s in noisy.strokes]
    m0 = [dict(s.meta) for s in noisy.strokes]
    a = refine_centrelines(g, noisy)
    b = refine_centrelines(g, noisy)
    assert np.array_equal(g, g0)
    for s, p, w, m in zip(noisy.strokes, p0, w0, m0):
        assert np.array_equal(s.points, p) and np.array_equal(s.width, w) and s.meta == m
    for x, y in zip(a.strokes, b.strokes):
        assert np.array_equal(x.points, y.points)


def test_open_stroke_without_width():
    """Widthless input (w measured from the image) on an open arc."""
    truth = synth.scene_t_junction(SIZE)
    g = _gray(truth)
    p = resample(truth.strokes[1].points, 1.0)
    rng = np.random.default_rng(0)
    noisy = Drawing([Stroke(p + rng.uniform(-1, 1, p.shape))], size=SIZE)
    r = refine_centrelines(g, noisy)
    assert r.strokes[0].width is None and not r.strokes[0].closed
    e0 = _err(noisy, Drawing([truth.strokes[1]]))
    e1 = _err(r, Drawing([truth.strokes[1]]))
    assert e1 < 0.6 * e0, (e0, e1)


def test_crossing_unharmed():
    """X scene: still 2 strokes, and no kink at the crossing — the max |κ|
    within 3w of the crossing is not much above the stroke's own level."""
    truth = synth.scene_x_crossing((500, 500))
    g = _gray(truth)
    base = extract(g)
    r = refine_centrelines(g, base)
    assert len(r.strokes) == 2
    # crossing point = closest approach of the two refined strokes
    A, B = (resample(s.points, 0.5, s.closed) for s in r.strokes)
    d, j = cKDTree(B).query(A)
    x = A[int(np.argmin(d))]
    for s in r.strokes:
        sv, k, sm = kappa_s(s.points, 2 * LW, step=1.0, closed=s.closed)
        keep = (sv > 3 * LW) & (sv < sv[-1] - 3 * LW)
        near = keep & (np.linalg.norm(sm - x, axis=1) < 3 * LW)
        far = keep & ~near
        assert near.any() and far.any()
        k_true = 0.6 / 500        # the gentler arc's κ is 0.4/500
        assert np.abs(k[near]).max() < np.abs(k[far]).max() + 2 * k_true, \
            (np.abs(k[near]).max(), np.abs(k[far]).max())
    assert _err(r, truth) <= _err(base, truth) + 0.05


def test_bad_method():
    with pytest.raises(ValueError):
        refine_centrelines(np.ones((10, 10)), Drawing([]), method="nope")
