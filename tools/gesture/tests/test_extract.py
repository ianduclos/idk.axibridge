"""Tests for gesture.extract (raster → strokes).

Own fixtures first (exact antialiased thick polylines drawn here, so the
suite never depends on synth.py); synth-based round trips at the end are
skipped when gesture.synth is missing or lacks the expected API.
"""
from __future__ import annotations

import importlib
import json

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

from gesture.core import Drawing, Stroke
from gesture.curvature import integrate_kappa, kappa_s
from gesture.extract import debug_overlay, extract, extract_file, load_image


# --------------------------------------------------------------------------
# fixtures: exact antialiased rendering of thick polylines (paper 1, ink 0)
# --------------------------------------------------------------------------

def dense(poly, step: float = 0.2, closed: bool = False) -> np.ndarray:
    p = np.asarray(poly, dtype=np.float64)
    if closed:
        p = np.vstack([p, p[:1]])
    out = []
    for a, b in zip(p[:-1], p[1:]):
        n = max(int(np.ceil(np.linalg.norm(b - a) / step)), 1)
        t = np.linspace(0.0, 1.0, n, endpoint=False)[:, None]
        out.append(a + (b - a) * t)
    out.append(p[-1:])
    return np.vstack(out)


def render(polys, size=(240, 240), width: float = 5.0, closed=None) -> np.ndarray:
    """Float image in [0, 1]: 1 − coverage of round-capped lines of full
    width `width` px around each (x, y) polyline. size = (H, W)."""
    H, W = size
    closed = closed or [False] * len(polys)
    pts = np.vstack([dense(p, closed=c) for p, c in zip(polys, closed)])
    yy, xx = np.mgrid[0:H, 0:W]
    d, _ = cKDTree(pts).query(np.column_stack([xx.ravel(), yy.ravel()]),
                              distance_upper_bound=width + 2)
    d = d.reshape(H, W)
    return 1.0 - np.clip(width / 2 + 0.5 - d, 0.0, 1.0)


def circle_pts(cx, cy, r, n=720):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([cx + r * np.cos(t), cy + r * np.sin(t)])


def smooth_curve():
    """A gentle S-ish curve, κ ≪ 1/width."""
    t = np.linspace(0, 1, 400)
    return np.column_stack([30 + 180 * t, 120 + 50 * np.sin(2.2 * np.pi * t) * (0.6 + 0.4 * t)])


def dist_to(points: np.ndarray, truth: np.ndarray) -> np.ndarray:
    return cKDTree(dense(truth)).query(points)[0]


W5 = 5.0


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def test_single_curve_centreline_and_width():
    truth = smooth_curve()
    d = extract(render([truth], width=W5))
    assert len(d.strokes) == 1
    s = d.strokes[0]
    assert not s.closed
    e = dist_to(s.points, truth)
    assert e.mean() < 0.5 and e.max() < 1.5            # extracted → truth
    back = cKDTree(s.points).query(dense(truth))[0]
    assert back.max() < W5                              # ends shortened by ≤ ~w/2
    assert abs(np.median(s.width) - W5) / W5 < 0.25
    assert d.meta["counts"]["strokes"] == 1


@pytest.mark.parametrize("angle", [90, 60, 40])
def test_x_crossing_gives_two_strokes_through_the_crossing(angle):
    a = np.array([(20.0, 120.0), (220.0, 120.0)])
    t = np.radians(angle)
    b = np.array([(120 - 100 * np.cos(t), 120 - 100 * np.sin(t)),
                  (120 + 100 * np.cos(t), 120 + 100 * np.sin(t))])
    d = extract(render([a, b], width=W5))
    assert len(d.strokes) == 2
    for s in d.strokes:
        assert np.min(np.linalg.norm(s.points - [120, 120], axis=1)) < 1.5
        assert s.length() > 180                         # spans the whole line
        assert len(s.meta["junctions"]) == 1
    # each extracted stroke follows ONE of the two truth lines
    errs = sorted(min(dist_to(s.points, a).max(), dist_to(s.points, b).max()) for s in d.strokes)
    assert errs[-1] < 2.0


def test_t_junction_bar_unbroken_stem_ends_at_bar():
    bar = np.array([(20.0, 100.0), (220.0, 100.0)])
    stem = np.array([(120.0, 100.0), (120.0, 220.0)])
    d = extract(render([bar, stem], width=W5))
    assert len(d.strokes) == 2
    lens = sorted(s.length() for s in d.strokes)
    long_s = max(d.strokes, key=lambda s: s.length())
    short_s = min(d.strokes, key=lambda s: s.length())
    assert lens[1] > 190                                # bar unbroken
    assert dist_to(long_s.points, bar).max() < 1.5
    ends = short_s.points[[0, -1]]
    top = ends[np.argmin(ends[:, 1])]
    assert abs(top[1] - 100.0) < W5                     # stem stops at the bar…
    assert abs(top[0] - 120.0) < 1.5
    assert ends[:, 1].max() > 210                       # …and runs to its tip


def test_closed_circle_one_closed_stroke_length():
    r = 70.0
    d = extract(render([circle_pts(120, 120, r)], width=W5, closed=[True]))
    assert len(d.strokes) == 1
    s = d.strokes[0]
    assert s.closed
    assert not np.allclose(s.points[0], s.points[-1])   # no repeated first point
    assert abs(s.length() - 2 * np.pi * r) / (2 * np.pi * r) < 0.03
    assert dist_to(s.points, np.vstack([circle_pts(120, 120, r), circle_pts(120, 120, r)[:1]])).max() < 1.0


def test_sharp_v_is_one_stroke_with_a_corner():
    """A V corner of one stroke and two strokes touching tip-to-tip are the
    same ink; the extractor returns ONE stroke (documented convention)."""
    v = np.array([(30.0, 30.0), (120.0, 210.0), (210.0, 30.0)])
    one = extract(render([v], width=W5))
    two = extract(render([v[:2], v[1:]], width=W5))
    arms = 2 * np.hypot(90, 180)
    for d in (one, two):
        assert len(d.strokes) == 1
        assert abs(d.strokes[0].length() - arms) / arms < 0.06
    assert one.meta["conventions"]["v_corner"].startswith("a sharp V is one stroke")


def scene():
    a = np.array([(20.0, 60.0), (220.0, 60.0)])
    b = np.array([(60.0, 20.0), (60.0, 140.0)])
    c = smooth_curve() + [0, 40]
    return [a, b, c, circle_pts(150, 210, 25)], [False, False, False, True]


def test_noise_robust_stroke_count():
    polys, closed = scene()
    clean = render(polys, width=W5, closed=closed)
    rng = np.random.default_rng(7)
    noisy = gaussian_filter(clean, 1.0) + rng.normal(0, 0.04, clean.shape)
    speck = rng.random(clean.shape) < 0.002
    noisy[speck] = rng.uniform(0.0, 0.5, speck.sum())
    noisy = np.clip(noisy, 0, 1)
    n_clean = len(extract(clean).strokes)
    n_noisy = len(extract(noisy).strokes)
    assert n_clean == 4                                  # a, b (crossing a), c, circle
    assert n_noisy == n_clean


def test_inputs_not_mutated_and_deterministic():
    polys, closed = scene()
    img = render(polys, width=W5, closed=closed)
    ref = img.copy()
    d1 = extract(img)
    d2 = extract(img)
    assert np.array_equal(img, ref)
    j1, j2 = json.loads(json.dumps(d1.to_json())), json.loads(json.dumps(d2.to_json()))
    for j in (j1, j2):
        j["meta"].pop("timings")                         # wall-clock, not geometry
    assert j1 == j2


def test_uint8_and_invert_and_overlay():
    img = render([smooth_curve()], width=W5)
    u8 = (img * 255).round().astype(np.uint8)
    a = extract(u8)
    b = extract(255 - u8, invert=True)
    assert len(a.strokes) == len(b.strokes) == 1
    assert np.allclose(a.strokes[0].points, b.strokes[0].points, atol=0.3)
    ov = debug_overlay(img, a)
    assert ov.dtype == np.uint8 and ov.shape == img.shape + (3,)


def test_extract_file_downscale_reports_original_pixels(tmp_path):
    """A 2× raster read with max_side = half its size must return geometry in
    the ORIGINAL file's pixels."""
    truth = smooth_curve() * 2.0
    img = render([truth], size=(480, 480), width=2 * W5)
    path = tmp_path / "fx.png"
    Image.fromarray((img * 255).round().astype(np.uint8)).save(path)
    g, scale = load_image(path, max_side=240)
    assert g.shape == (240, 240) and abs(scale - 0.5) < 1e-9
    d = extract_file(path, max_side=240)
    assert d.size == (480, 480)
    assert len(d.strokes) == 1
    e = dist_to(d.strokes[0].points, truth)
    assert e.mean() < 1.0
    assert abs(np.median(d.strokes[0].width) - 2 * W5) / (2 * W5) < 0.25
    assert d.meta["scale"] == pytest.approx(0.5)


def test_drawing_json_roundtrip(tmp_path):
    polys, closed = scene()
    d = extract(render(polys, width=W5, closed=closed))
    p = tmp_path / "d.json"
    d.save(p)
    e = Drawing.load(p)
    assert len(e.strokes) == len(d.strokes)
    assert [s.closed for s in e.strokes] == [s.closed for s in d.strokes]


def test_collinear_gap_is_joined_but_corner_gap_is_not():
    a = np.array([(20.0, 120.0), (115.0, 120.0)])
    b = np.array([(125.0, 120.0), (220.0, 120.0)])           # 10 px gap = 2 w
    d = extract(render([a, b], width=W5))
    assert len(d.strokes) == 1 and d.strokes[0].meta["gap_joins"] == 1
    assert dist_to(d.strokes[0].points, np.array([(20.0, 120.0), (220.0, 120.0)])).max() < 1.5
    c = np.array([(125.0, 125.0), (125.0, 220.0)])           # same gap, but a corner
    d2 = extract(render([a, c], width=W5))
    assert len(d2.strokes) == 2
    assert extract(render([a, b], width=W5), gap_join_factor=0).meta["counts"]["strokes"] == 2


def test_plate_mark_and_outside_marks_removed():
    """A ruler-straight rectangle near the sheet edge is a plate mark: it is
    erased, the drawing inside survives intact, marks outside it go."""
    H = W = 320
    m = 24.0
    frame = np.array([(m, m), (W - 1 - m, m), (W - 1 - m, H - 1 - m), (m, H - 1 - m)])
    curve = smooth_curve() + [40, 40]
    tick = np.array([(250.0, 310.0), (290.0, 310.0)])        # "signature" below the plate
    img = render([frame, curve, tick], size=(H, W), width=3.0, closed=[True, False, False])
    d = extract(img)
    assert d.meta["counts"]["plate_lines"] >= 4
    assert len(d.strokes) == 1
    assert dist_to(d.strokes[0].points, curve).max() < 1.5
    keep = extract(img, drop_frames=False)
    assert len(keep.strokes) >= 3


# --------------------------------------------------------------------------
# κ recovery
# --------------------------------------------------------------------------

def kappa_error(truth: np.ndarray, got: Stroke, sigma: float) -> tuple[float, float]:
    """RMS |κ_extracted − κ_truth| over the interior (≥ 3σ from either end
    of the extracted stroke), both measured with curvature.kappa_s at the
    same σ; returned with the truth's max |κ| for scale."""
    pts = got.points
    if np.linalg.norm(pts[0] - truth[0]) > np.linalg.norm(pts[-1] - truth[0]):
        pts = pts[::-1]                                  # align direction
    s_t, k_t, sm_t = kappa_s(truth, sigma)
    s_g, k_g, sm_g = kappa_s(pts, sigma)
    idx = cKDTree(sm_t).query(sm_g)[1]
    interior = (s_g > 3 * sigma) & (s_g < s_g[-1] - 3 * sigma)
    err = k_g[interior] - k_t[idx[interior]]
    return float(np.sqrt(np.mean(err**2))), float(np.max(np.abs(k_t)))


def test_kappa_recovery_on_known_stroke():
    """Piecewise-linear κ(s) (line → clothoid → arc → clothoid, inflection),
    width 4 px, extracted and measured at σ = 2 × width."""
    w = 4.0
    breaks = np.array([0, 60, 160, 260, 380.0])
    kappas = np.array([0.0, 0.0, 1 / 45, 1 / 45, -1 / 60])
    truth = integrate_kappa(breaks, kappas, 0.25, start=(40.0, 200.0), heading=-0.3)
    d = extract(render([truth], size=(300, 320), width=w))
    assert len(d.strokes) == 1
    rms, kmax = kappa_error(truth, d.strokes[0], sigma=2 * w)
    print(f"\nκ recovery: RMS error {rms:.5f} 1/px = {rms / kmax:.1%} of max|κ| ({kmax:.4f})")
    assert rms / kmax < 0.10


# --------------------------------------------------------------------------
# synth-based round trips (skipped while synth.py is absent / incomplete)
# --------------------------------------------------------------------------

def _synth():
    try:
        mod = importlib.import_module("gesture.synth")
    except Exception as e:  # pragma: no cover - depends on the sibling agent
        pytest.skip(f"gesture.synth not importable: {e}")
    need = ["render", "scene_x_crossing", "scene_t_junction", "scene_closed_loop",
            "random_clothoid_stroke"]
    missing = [n for n in need if not hasattr(mod, n)]
    if missing:
        pytest.skip(f"gesture.synth lacks {missing}")
    return mod


def test_synth_x_crossing():
    sy = _synth()
    truth = sy.scene_x_crossing(320)
    d = extract(sy.render(truth, line_width=4.0, seed=1))
    assert len(d.strokes) == 2
    for s in d.strokes:
        e = min(dist_to(s.points, t.points).mean() for t in truth.strokes)
        assert e < 1.0


def test_synth_t_junction():
    sy = _synth()
    truth = sy.scene_t_junction(320)
    d = extract(sy.render(truth, line_width=4.0, seed=2))
    assert len(d.strokes) == 2
    bar, stem = truth.strokes
    got_bar = max(d.strokes, key=lambda s: s.length())
    assert got_bar.length() > 0.9 * bar.length()
    got_stem = min(d.strokes, key=lambda s: s.length())
    j = np.asarray(stem.meta["junction"])
    assert np.min(np.linalg.norm(got_stem.points[[0, -1]] - j, axis=1)) < 4.0


def test_synth_closed_loop_length():
    sy = _synth()
    truth = sy.scene_closed_loop(320)
    d = extract(sy.render(truth, line_width=4.0, seed=3))
    assert len(d.strokes) == 1 and d.strokes[0].closed
    L, Lt = d.strokes[0].length(), truth.strokes[0].length()
    assert abs(L - Lt) / Lt < 0.03


def test_synth_clothoid_kappa_recovery():
    sy = _synth()
    rng = np.random.default_rng(11)
    errs = []
    for k in range(3):
        st = sy.random_clothoid_stroke(rng, 300.0, 4, 1 / 50, heading=float(rng.uniform(0, 2 * np.pi)))
        p = st.points - st.points.min(axis=0) + 30
        size = tuple(int(v) for v in np.ceil(p.max(axis=0) + 30))
        dr = Drawing([Stroke(p)], size=size)
        d = extract(sy.render(dr, line_width=4.0, seed=k))
        assert len(d.strokes) == 1
        rms, kmax = kappa_error(p, d.strokes[0], sigma=8.0)
        errs.append(rms / max(kmax, 1e-9))
    print(f"\nsynth clothoid κ RMS / max|κ|: {np.round(errs, 3).tolist()}")
    assert max(errs) < 0.15
