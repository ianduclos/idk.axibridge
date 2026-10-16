"""Nib ribbons at real pen widths (gesture/penrender.py)."""
import inspect

import numpy as np
import pytest

from gesture import penrender as pr
from gesture import regime as rg

PEN = 0.4


def _wave(L=30.0, amp=3.0, n=240, per=30.0):
    x = np.linspace(0, L, n)
    return np.column_stack([x, amp * np.sin(2 * np.pi * x / per)])


@pytest.fixture(scope="module")
def narrow():
    return rg.make(_wave(), 1.0, phi=np.deg2rad(45), W=1.5)


@pytest.fixture(scope="module")
def transition():
    base = rg.make(_wave(36, 2.5, 300, 40), 0.0, phi=np.deg2rad(50), W=2.2)
    return rg.swell(rg.thicken(base, 0.1, until=0.85), 0.5, length=14, size=5)


@pytest.fixture(scope="module")
def rendered(narrow):
    return {k: pr.strategy(k)(narrow, PEN) for k in pr.STRATEGIES}


def _polylines_ok(paths):
    assert isinstance(paths, list)
    assert len(paths.pens) == len(paths)
    for p in paths:
        assert isinstance(p, np.ndarray) and p.ndim == 2 and p.shape[1] == 2 and len(p) >= 2
        assert np.isfinite(p).all()


def test_every_strategy_returns_polylines(rendered):
    for k, paths in rendered.items():
        assert len(paths) >= 1, k
        _polylines_ok(paths)


def test_renderer_takes_what_regime_render_takes(transition, narrow):
    """Same call shape as regime.render: one stroke or a list (one mark)."""
    for k in ("b+", "c", "e"):
        rend = pr.strategy(k)
        _polylines_ok(rend(transition, PEN))
        _polylines_ok(rend([transition, narrow], pen=PEN))
        assert rend([], PEN) == []


def test_regime_hook_if_present(narrow):
    """When regime.render grows the `nib_renderer` hook, a penrender
    renderer plugs straight in."""
    if "nib_renderer" not in inspect.signature(rg.render).parameters:
        pytest.skip("regime.render has no nib_renderer hook yet")
    paths = rg.render(narrow, PEN, nib_renderer=pr.strategy("e"))
    assert all(np.asarray(p).ndim == 2 for p in paths)
    ev = pr.evaluate(narrow, paths, PEN, px_per_mm=16)
    assert ev["coverage"] >= 0.95, ev
    f = rg.render(narrow, PEN, nib_renderer=pr.strategy("f"))
    assert len(pr.layers(f)) == 2


@pytest.mark.parametrize("k", ["b+", "c", "e"])
def test_fill_coverage_in_narrow_ribbon(narrow, rendered, k):
    ev = pr.evaluate(narrow, rendered[k], PEN, px_per_mm=16)
    assert ev["coverage"] >= 0.95, ev
    if k != "b+":     # concentric insets leave slivers where a ribbon tapers
        assert ev["gap_mm"] <= 0.3, ev


def test_outline_is_the_pipe_control(narrow, rendered):
    ev = pr.evaluate(narrow, rendered["a"], PEN, px_per_mm=16)
    assert ev["coverage"] < 0.8 and ev["gap_mm"] > 0.4, ev


def test_lanes_cover_the_transition(transition):
    for k in ("c", "e"):
        ev = pr.evaluate(transition, pr.strategy(k)(transition, PEN), PEN, px_per_mm=16)
        assert ev["coverage"] >= 0.93, (k, ev)
        assert ev["spill"] < 0.03, (k, ev)


def _across_share(stroke, paths, pen):
    """Share of pen-down length running ACROSS the stroke (|cos| to the
    nearest centreline tangent < 0.5). Hatching would make this large."""
    from scipy.spatial import cKDTree
    q = rg.resample(stroke, 0.1)
    t = np.gradient(q.points, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True)
    tree = cKDTree(q.points)
    across = total = 0.0
    for p in paths:
        d = np.diff(p, axis=0)
        L = np.linalg.norm(d, axis=1)
        ok = L > 1e-9
        d, L = d[ok], L[ok]
        mid = 0.5 * (p[1:] + p[:-1])[ok]
        _, j = tree.query(mid)
        cos = np.abs(np.sum(d / L[:, None] * t[j], axis=1))
        across += float(L[cos < 0.5].sum())
        total += float(L.sum())
    return across / max(total, 1e-9)


@pytest.mark.parametrize("k", ["b+", "c", "e", "f"])
def test_no_hatching(narrow, rendered, k):
    assert _across_share(narrow, rendered[k], PEN) < 0.08


def test_two_pen_layers_stay_inside_the_ink(narrow, rendered):
    from shapely.geometry import LineString
    paths = rendered["f"]
    lay = pr.layers(paths)
    assert len(lay) == 2
    P = max(lay)
    ink = pr.ideal_ink(narrow, PEN)
    allowed = ink.buffer(-0.5 * P + 0.02)
    for m in lay[P]:
        assert allowed.covers(LineString(m)) or LineString(m).difference(allowed).length < 0.05


def test_chain_adds_no_visible_ink(narrow):
    base = rg.render(rg.replace(narrow, fill=np.ones(len(narrow))), PEN)
    chained = pr.chain(base, PEN)
    assert len(chained) <= len(base)
    box = (-3, -7, 33, 7)
    a = pr.ink_raster(base, box, px_per_mm=12, pens=[PEN] * len(base)) > 0.5
    b = pr.ink_raster(chained, box, px_per_mm=12, pens=[PEN] * len(chained)) > 0.5
    assert np.sum(b & ~a) / max(a.sum(), 1) < 0.01


def test_plot_time_counts_lifts_and_swaps():
    p = [np.array([[0.0, 0], [10, 0]]), np.array([[0.0, 1], [10, 1]])]
    one = pr.plot_time([np.vstack([p[0], p[1][::-1]])])
    two = pr.plot_time(p)
    assert two["total_s"] > one["total_s"]
    swap = pr.plot_time(pr.PenPaths(p, pens=[0.4, 1.0]))
    assert swap["swap_s"] == pr.MOTION["pen_swap_s"]
