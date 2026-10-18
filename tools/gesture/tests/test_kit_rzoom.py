"""river_zoom (round 14, thread c1): the far Amazon stem zooming in and out along itself."""
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, "tools/gesture")
from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit.renderers_rzoom import bands  # noqa: E402
from gesture.kit.voices_rzoom import SHAPES, heading_profile, magnify, pace_warp, window_frames, zoom_shape  # noqa: E402

PIECE = {"frame": [190, 270], "seed": 1461, "margin": 8,
         "voice": {"id": "river_zoom", "schedule": "push", "zoom": 32, "recur": 4, "pace": 0.6, "angle": 90,
                   "far_mm_per_km": 0.8},
         "renderer": {"id": "rzoom_ink", "pens": [0.25, 0.35, 0.5, 0.7], "inks": "blue,blue,black,black"}}


@pytest.fixture(scope="module")
def q():
    return L.load("river_stems", "grwl_far_sb19")["stems"][("SB19", 0)][2]


def _turning(p):
    d = np.diff(p, axis=0)
    return np.unwrap(np.arctan2(d[:, 1], d[:, 0])), np.linalg.norm(d, axis=1)


def test_registered():
    kit.discover()
    assert not kit.DISCOVERY_ERRORS
    assert "river_zoom" in kit.registry("voice") and "rzoom_ink" in kit.registry("renderer")


@pytest.mark.parametrize("shape", SHAPES)
def test_shapes_bounded_and_reach_both_ends(shape):
    g = zoom_shape(shape, 2000, np.random.default_rng(3), 3)
    assert g.shape == (2000,) and np.all(np.isfinite(g))
    assert g.min() >= 0.0 and g.max() <= 1.0
    assert g.max() > 0.95 and g.min() < 0.05          # far and close both visited


def test_constant_zoom_is_a_pure_magnification(q):
    """z = 1 everywhere: the integrated line is the stem itself (same turning
    function per arc length); z = k everywhere: the same curve k times larger."""
    um, th, Ltot = heading_profile(q)
    g0 = np.zeros(100)
    r1 = magnify(q, g0, zoom=1.0, start=0.1, river=0.05, far_mm_per_km=1.0, channel_w=254.0, course="free")
    r4 = magnify(q, np.ones(100), zoom=4.0, start=0.1, river=0.05, far_mm_per_km=1.0, channel_w=254.0,
                 course="free")
    assert r1["length_mm"] == pytest.approx(0.05 * Ltot / 1000.0, rel=1e-3)     # 1 mm per km
    assert r4["length_mm"] == pytest.approx(4 * r1["length_mm"], rel=1e-3)
    t1, d1 = _turning(r1["points"])
    t4, d4 = _turning(r4["points"])
    s1, s4 = np.cumsum(d1) / d1.sum(), np.cumsum(d4) / d4.sum()
    grid = np.linspace(0.02, 0.98, 400)
    a, b = np.interp(grid, s1, t1), np.interp(grid, s4, t4)
    assert np.max(np.abs((a - a[0]) - (b - b[0]))) < 0.02                       # same bends, radians
    # and the same bends as the stem itself
    i0 = np.searchsorted(um, 0.1 * Ltot)
    i1 = np.searchsorted(um, 0.15 * Ltot)
    ts = np.interp(grid, (um[i0:i1] - um[i0]) / (um[i1 - 1] - um[i0]), th[i0:i1])
    assert np.max(np.abs((ts - ts[0]) - (a - a[0]))) < 0.1                       # window ends differ by < 1 sample


def test_curvature_scales_by_one_over_zoom(q):
    g = np.r_[np.zeros(50), np.ones(50)]
    r = magnify(q, g, zoom=10.0, start=0.2, river=0.1, far_mm_per_km=0.8, channel_w=254.0, course="free")
    z, u = r["zoom"], r["u"]
    ds = np.linalg.norm(np.diff(r["points"], axis=0), axis=1)
    du = np.diff(u)
    k = ds / np.maximum(du, 1e-12) / 0.0008                                    # paper mm per river m / c
    flat = (np.diff(z) == 0) & (du > 0)                                         # away from the jump
    assert np.allclose(k[flat], z[1:][flat], rtol=0.02)                          # ds = c·z·du


def test_river_consumed_and_monotonic(q):
    r = magnify(q, zoom_shape("pulses", 3000, np.random.default_rng(1), 4), zoom=24.0, start=0.05, river=1.0,
                pace=0.6, far_mm_per_km=0.8, channel_w=254.0, course="free")
    assert np.all(np.diff(r["u"]) >= 0)
    _, _, Ltot = heading_profile(q)
    assert r["river_km"] * 1000 <= Ltot * 0.95 + 1


def test_pace_lengthens_zoomed_stretches():
    g = np.r_[np.zeros(500), np.ones(500)]
    a, b = pace_warp(g, 20.0, 0.0, 1000), pace_warp(g, 20.0, 1.0, 1000)
    assert np.mean(a > 0.5) == pytest.approx(0.5, abs=0.01)
    assert np.mean(b > 0.5) == pytest.approx(20 / 21, abs=0.01)


def test_step_heading_is_the_naive_magnification(q):
    """`step` keeps each stem segment's heading: corners at the stem samples;
    `linear` turns continuously (no turn between paper samples larger than
    the step's ds-share of a sample turn)."""
    kw = dict(zoom=40.0, start=0.3, river=0.02, far_mm_per_km=0.8, channel_w=254.0, course="free")
    lin = magnify(q, np.ones(10), **kw)
    stp = magnify(q, np.ones(10), interp="step", **kw)
    tl, _ = _turning(lin["points"])
    ts, _ = _turning(stp["points"])
    assert np.abs(np.diff(ts)).max() > 5 * np.abs(np.diff(tl)).max()


def test_steer_stays_in_box_and_keeps_meanders(q):
    box = (8.0, 8.0, 174.0, 254.0)
    r = magnify(q, zoom_shape("push", 3000, np.random.default_rng(2), 4), zoom=32.0, start=0.05, river=1.0,
                pace=0.6, far_mm_per_km=0.8, channel_w=254.0, course="steer", box=box, angle=90.0,
                rng=np.random.default_rng(5))
    p = r["points"]
    assert np.isfinite(p).all() and len(p) > 1000
    run = kit.run(PIECE)
    m = run.marks[0]
    x0, y0, w, h = box
    assert m.points[:, 0].min() >= x0 - 1e-6 and m.points[:, 0].max() <= x0 + w + 1e-6
    assert m.points[:, 1].min() >= y0 - 1e-6 and m.points[:, 1].max() <= y0 + h + 1e-6
    assert m.meta["fit"]["scale"] <= 1.0                                        # shrink-only, never clipped


def test_piece_one_contiguous_line_and_channels():
    s = kit.run(PIECE)
    assert len(s.marks) == 1
    m = s.marks[0]
    assert {"zoom", "u_km"} <= set(m.channels)
    assert m["zoom"].min() == pytest.approx(1.0, abs=1e-6) and m["zoom"].max() == pytest.approx(32.0, rel=1e-3)
    assert np.all(np.diff(m["u_km"]) >= 0)
    gaps = np.linalg.norm(np.diff(m.points, axis=0), axis=1)
    assert gaps.max() < 0.5                                                     # no jumps
    # inks: runs of one line, each run starting where the previous ended
    inks = s.inks
    assert len(inks) >= 2
    for a, b in zip(inks[:-1], inks[1:]):
        assert np.allclose(a.points[-1], b.points[0])
    assert {i.meta["colour"] for i in inks} == {"blue", "black"}


def test_bands_merge_short_runs():
    z = np.r_[np.ones(100), np.full(3, 30.0), np.ones(100)]
    s = np.arange(len(z)) * 0.5
    b = bands(z, 3, s, min_run=4.0, top=30.0)
    assert set(b) == {0}


def test_window_frames(q):
    box = (10.0, 10.0, 280.0, 180.0)
    fr = window_frames(q, frames=5, zoom=16.0, start=0.2, span_w=1600, channel_w=254.0, box=box, pan=0.2)
    assert len(fr) == 5
    for f in fr:
        p = f["points"]
        assert p[:, 0].min() >= 10 - 1e-6 and p[:, 0].max() <= 290 + 1e-6
        assert p[:, 1].min() >= 10 - 1e-6 and p[:, 1].max() <= 190 + 1e-6
    assert fr[-1]["span_m"] < fr[0]["span_m"] / 8


def test_deterministic_across_processes():
    code = ("import sys, json, hashlib; sys.path.insert(0, 'tools/gesture'); from gesture import kit; "
            f"s = kit.run({PIECE!r}); "
            "print(hashlib.sha1(s.marks[0].points.tobytes()).hexdigest())")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                           env={"PYTHONHASHSEED": str(k), "PATH": "/usr/bin:/bin"}).stdout for k in (1, 2)}
    assert len(outs) == 1
