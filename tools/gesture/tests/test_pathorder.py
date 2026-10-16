"""Tests for gesture/pathorder.py: ordering keeps the ink, never adds pen-up
travel, joins only within tolerance, keeps a mass's inset order and the
phase / layer split, and is deterministic."""
from __future__ import annotations

import numpy as np

from gesture import pathorder as po


def _ring(c, r, n=40, start=0.0):
    t = start + np.linspace(0, 2 * np.pi, n, endpoint=False)
    q = np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)])
    return np.vstack([q, q[:1]])


def _scene(seed=0, n_open=40, n_masses=4, pen=1.0):
    """Random open wiggles + masses (outline ring, then concentric insets
    outside-in at pen spacing, some cut into open arcs)."""
    rng = np.random.default_rng(seed)
    paths, groups, phases = [], [], []
    for _ in range(n_open):
        p0 = rng.uniform(0, 200, 2)
        steps = rng.normal(0, 3, (int(rng.integers(3, 12)), 2))
        paths.append(np.vstack([p0, p0 + np.cumsum(steps, axis=0)]))
        groups.append(None)
        phases.append(0)
    for m in range(n_masses):
        c = rng.uniform(30, 170, 2)
        R = rng.uniform(8, 14)
        paths.append(_ring(c, R, start=rng.uniform(0, 6)))
        groups.append(None)
        phases.append(0)
        k = 1
        while R - k * pen > 0.5 * pen:
            q = _ring(c, R - k * pen, start=rng.uniform(0, 6))
            if k % 3 == 0:                       # a graded-fill arc
                q = q[3:30]
            paths.append(q)
            groups.append(1000 + m)
            phases.append(1)
            k += 1
    return paths, groups, phases


def test_geometry_preserved_and_travel_not_worse():
    for seed in range(3):
        paths, groups, phases = _scene(seed)
        for kw in ({}, {"groups": groups, "phases": phases}, {"groups": groups, "phases": phases, "nest_tol": 2.0}):
            pl = po.order_paths(paths, **kw)
            assert po.segments(pl.paths) == po.segments(paths)
            assert abs(sum(po.plen(p) for p in pl.paths) - sum(po.plen(p) for p in paths)) < 1e-6
            assert len(pl.paths) == len(paths)
            assert pl.after["pen_up_mm"] <= pl.before["pen_up_mm"] + 1e-9
            assert po.travel(pl.paths) <= po.travel(paths) + 1e-9
    # an input that is already well ordered can never get worse
    paths, groups, phases = _scene(5)
    good = po.order_paths(paths).paths
    again = po.order_paths(good)
    assert po.travel(again.paths) <= po.travel(good) + 1e-9


def test_join_respects_tolerance():
    paths, groups, phases = _scene(1)
    for tol, ctol in ((0.6, 0.0), (0.6, 2.5)):
        pl = po.order_paths(paths, groups, phases, join_tol=tol, chain_join_tol=ctol, nest_tol=2.0)
        assert len(pl.paths) < len(paths)                      # something was joined
        assert po.segments(paths) <= po.segments(pl.paths)     # nothing lost
        new = po.segments(pl.paths) - po.segments(paths)       # the inked connectors
        assert new
        for a, b in new:
            assert np.hypot(a[0] - b[0], a[1] - b[1]) <= max(tol, ctol) + 1e-6
        # joining only removes lifts: pen-up never grows
        up = po.order_paths(paths, groups, phases, nest_tol=2.0)
        assert pl.after["pen_up_mm"] <= up.after["pen_up_mm"] + 1e-9
    # a gap above every tolerance is never inked
    far = [np.array([[0.0, 0.0], [10.0, 0.0]]), np.array([[10.0 + 0.61, 0.0], [20.0, 0.0]])]
    assert len(po.order_paths(far, join_tol=0.6).paths) == 2
    assert len(po.order_paths(far, join_tol=0.62).paths) == 1


def test_mass_order_phases_and_layers():
    paths, groups, phases = _scene(2)
    pl = po.order_paths(paths, groups, phases)             # chains verbatim
    order = [i for src in pl.source for i, _ in src]
    for g in {g for g in groups if g is not None}:
        mine = [i for i in order if groups[i] == g]
        assert mine == sorted(mine)                        # inset order kept exactly
    ph = [phases[i] for i in order]
    assert ph == sorted(ph)                                # all lines before all mass fill
    # nest mode: every inset after the inset that encloses it
    pl2 = po.order_paths(paths, groups, phases, nest_tol=1.5)
    order2 = [i for src in pl2.source for i, _ in src]
    for g in {g for g in groups if g is not None}:
        ids = [i for i in range(len(paths)) if groups[i] == g]
        _, parent = po.nest_order([paths[i] for i in ids], 1.5)
        pos = {i: order2.index(i) for i in ids}
        for k, pa in enumerate(parent):
            if pa >= 0:
                assert pos[ids[pa]] < pos[ids[k]]
    # layers never mix and come in first-appearance order
    lay = [i % 2 for i in range(len(paths))]
    pl3 = po.order_paths(paths, groups, phases, layers=lay, join_tol=5.0)
    assert pl3.layers == sorted(pl3.layers)
    for src, L in zip(pl3.source, pl3.layers):
        assert all(lay[i] == L for i, _ in src)


def test_deterministic_and_estimate():
    paths, groups, phases = _scene(3)
    a = po.order_paths(paths, groups, phases, nest_tol=2.0, join_tol=0.5)
    b = po.order_paths(paths, groups, phases, nest_tol=2.0, join_tol=0.5)
    assert len(a.paths) == len(b.paths) and all(np.array_equal(p, q) for p, q in zip(a.paths, b.paths))
    # estimator port: a 100 mm straight line from home and back, native params
    e = po.estimate([np.array([[0.0, 0.0], [100.0, 0.0]])])
    v = 0.25 * 279.4
    acc = 4000.0
    t_line = 2 * v / acc + (100 - v * v / acc) / v       # trapezoid
    assert abs(e["pen_down_s"] - round(t_line, 1)) <= 0.1
    assert e["pen_up_mm"] == 100.0 and e["lifts"] == 1
