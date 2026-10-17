"""Round 11 swell thread (kit/swell_ink.py): smooth swells, deliberate dots, authored placement."""
from __future__ import annotations

import numpy as np
import pytest

from gesture import kit
from gesture.kit.core import Ctx, Mark, _Run, get
from gesture.kit.swell_ink import SWELL_PARAMS, dot_plan, side, smootherstep, swell_geometry


def _line(L=90.0, a=30.0, b=60.0):
    t = np.linspace(0, L, 451)
    pts = np.column_stack([20 + t, 60 + 5 * np.sin(t / 14.0)])
    e = ((t >= a) & (t <= b)).astype(float)
    return Mark(pts, {"emphasis": e, "r": 2 * e})


def _render(rid, marks, **p):
    from gesture.kit import library
    m = get("renderer", rid)
    prm = m.validate({"id": rid, **p})
    ctx = Ctx((267.0, 180.0), (0, 0, 267, 180), 1, 1, 0, "renderer", rid, _Run(library.default()))
    return m.fn(ctx, marks, **{k: v for k, v in prm.items() if k != "id"})


def _prm(**kw):
    return {**{p.name: p.default for p in SWELL_PARAMS}, **kw}


def test_registered():
    kit.discover()
    assert not {k: v for k, v in kit.DISCOVERY_ERRORS.items() if "swell" in k}
    reg = kit.registry()
    assert {"swell", "swell_dots"} <= set(reg["renderer"]) and "swell_place" in reg["arranger"]


def test_side_meets_head_with_slope_k_and_smootherstep_is_c1():
    R, r0, k = 3.5, 0.2, 0.75
    x = np.array([0.0, 1e-4])
    r = side(x, R, r0, k, tail=0.0, tail_w=1.6)
    assert r[0] == pytest.approx(R)
    assert (r[0] - r[1]) / 1e-4 == pytest.approx(k, rel=1e-2)
    u = np.array([0.0, 1e-5, 1 - 1e-5, 1.0])
    d = np.diff(smootherstep(u))
    assert d[0] < 1e-9 and d[-1] < 1e-9


@pytest.mark.parametrize("profile", ["lens", "drop", "press", "turn", "momentum", "sag", "necklace"])
def test_a_30mm_stress_stays_compact(profile):
    m = _line()
    if profile == "turn":                                   # a turn needs a turn: a sharp corner at 45 mm
        t = np.linspace(0, 90, 451)
        ang = np.where(t < 45, 0.0, np.radians(120))
        steps = np.column_stack([np.cos(ang), np.sin(ang)])[1:] * 0.2
        pts = np.vstack([[20.0, 60.0], np.array([20.0, 60.0]) + np.cumsum(steps, axis=0)])
        m = Mark(pts, {"emphasis": m["emphasis"], "r": m["r"]})
    g, info = swell_geometry(m, _prm(profile=profile, size=7.0))
    assert g is not None and len(info["stresses"]) == 1
    D = info["stresses"][0]["D"]
    # the mass part (wider than 3.2 mm) never becomes a 30 mm capsule
    core = g.buffer(-1.6).buffer(1.6)
    ext = max(np.ptp(np.asarray(q.exterior.coords), axis=0).max()
              for q in (core.geoms if hasattr(core, "geoms") else [core]))
    assert ext < D * (3.2 if profile == "necklace" else 2.0), (profile, ext, D)


def test_turn_on_a_gentle_bend_stays_a_line():
    g, _ = swell_geometry(_line(), _prm(profile="turn", size=7.0))
    assert g is None or g.buffer(-1.6).is_empty              # no mass where the line hardly turns


def test_long_bell_is_the_sausage():
    g, info = swell_geometry(_line(), _prm(profile="bell", length=3.0))
    D = info["stresses"][0]["D"]
    core = g.buffer(-1.6).buffer(1.6)
    assert np.ptp(np.asarray(core.exterior.coords), axis=0).max() > 2.5 * D


def test_swell_inks_are_line_built_and_ghost_has_no_line():
    inks = _render("swell", [_line()], profile="drop", line="none")
    assert not [k for k in inks if k.meta.get("role") == "line"]
    rings = [k for k in inks if k.closed and k.filled]
    fills = [k for k in inks if not k.closed]
    assert rings and fills and all(np.allclose(k.points[0], k.points[-1]) for k in rings)


def test_beat_dots_are_evenly_spaced_and_follow_the_size_pattern():
    plan, _, _ = dot_plan(_line(), {"rule": "beat", "period": 10.0, "sizes": "Lss", "gap": 0.0, "scale": 5.0,
                                    "phrase": 70.0, "decel_n": 6, "decel_q": 0.7, "thr": 0.15, "size": 6.0})
    xs = np.array([p[0] for p in plan])
    assert np.allclose(np.diff(xs), 10.0, atol=1e-6)
    assert "".join(p[1] for p in plan[:6]) == "LssLss"


def test_fullstop_breaks_the_line_and_wound_stays_contiguous():
    m = _line(200.0, 0, 0)
    inks = _render("swell_dots", [m], rule="fullstop", phrase=40.0, space=8.0)
    lines = [k for k in inks if k.meta.get("role") == "line"]
    stops = [k for k in inks if k.meta.get("role", "").startswith("dot") and k.closed]
    assert len(lines) >= 2 and len(stops) == len(lines)
    inks = _render("swell_dots", [m], rule="beat", period=25.0, shape_L="wound", shape_s="wound")
    assert len(inks) == 1                                      # the dots ARE the line
    p = inks[0].points
    assert np.max(np.linalg.norm(np.diff(p, axis=0), axis=1)) < 0.8   # no jumps (no stray chords)


@pytest.mark.parametrize("shape,rings", [("ring", 2), ("split", 2), ("disc", 1), ("comma", 1)])
def test_dot_shapes(shape, rings):
    inks = _render("swell_dots", [_line(60.0, 0, 0)], rule="beat", period=100.0, sizes="L", shape_L=shape,
                   line="none", size=8.0)
    closed = [k for k in inks if k.closed]
    assert len(closed) == rings, (shape, len(closed))


def test_place_and_determinism():
    rec = {"seed": 7700, "arranger": {"id": "swell_place", "boxes": [0.0, 0.0, 0.3, 1.0]},
           "parts": [{"voice": {"id": "hand", "hand": "matisse", "length": 0.8},
                      "modulators": [{"id": "prosody", "density": 0.5}],
                      "renderer": {"id": "swell", "profile": "drop", "size": 12.0}}]}
    a, b = kit.run(rec), kit.run(rec)
    xs = np.vstack([k.points for k in a.inks])[:, 0]
    assert xs.max() < 0.36 * 267
    assert len(a.inks) == len(b.inks) and all(np.array_equal(p.points, q.points) for p, q in zip(a.inks, b.inks))
