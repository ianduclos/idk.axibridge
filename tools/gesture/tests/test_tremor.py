"""Tests for gesture.tremor — the fine-scale residual layer. Synthetic data
only (no corpus), fast."""
from __future__ import annotations

import numpy as np
import pytest

from gesture import synth
from gesture import tremor as tr
from gesture.core import Drawing, Stroke

W = 4.0   # line width, px


def _ar2_offsets(rng, n, a1=1.6, a2=-0.7, sd=1.0):
    e = rng.standard_normal(n + 200) * sd
    x = np.zeros(n + 200)
    for i in range(2, n + 200):
        x[i] = a1 * x[i - 1] + a2 * x[i - 2] + e[i]
    return x[200:]


def _ar_drawing(seed=0, n_strokes=12, length_w=300.0, amp_w=0.12, closed=False):
    """Straight strokes carrying a lateral AR(2) offset of rms amp_w line widths."""
    rng = np.random.default_rng(seed)
    st = []
    step = tr.STEP_W * W
    for k in range(n_strokes):
        n = int(length_w / tr.STEP_W)
        x = np.arange(n) * step
        off = _ar2_offsets(rng, n)
        off = off / off.std() * amp_w * W
        pts = np.column_stack([50 + x, 50 + 40 * k + off])
        st.append(Stroke(pts, width=np.full(n, W)))
    return Drawing(st, source="ar", size=(int(50 + length_w * W + 50), 50 + 40 * n_strokes + 50))


@pytest.fixture(scope="module")
def model():
    d = _ar_drawing()
    return tr.fit_model(tr.drawing_residuals(d), name="ar")


def _scene():
    d = synth.scene_t_junction(400)
    loop = synth.scene_closed_loop(400).strokes[0]          # placed clear of the T
    loop = Stroke(loop.points + [450.0, 0.0], closed=True)
    return Drawing([Stroke(s.points, width=np.full(len(s), W), closed=s.closed, meta=s.meta)
                    for s in d.strokes] + [loop],
                   source="t", size=(850, 400), meta={"line_width_px": W})


def test_straight_line_has_zero_residual_and_curve_bias_is_removed():
    x = np.linspace(0, 400, 801)
    r = tr.lateral_residual(np.column_stack([x, 0 * x]), W)
    assert np.abs(r["r"]).max() < 1e-9
    t = np.linspace(0, 2 * np.pi, 2000, endpoint=False)
    circ = np.column_stack([np.cos(t), np.sin(t)]) * 30 * W     # κ·w = 1/30
    r = tr.lateral_residual(circ, W, closed=True)
    assert np.abs(r["r"]).max() < 0.01                          # twicing: no κσ²/2 shrinkage


def test_model_recovers_synthetic_ar_statistics(model):
    d = _ar_drawing()
    ref = tr.residual_stats(tr.drawing_residuals(d))
    flat = Drawing([Stroke(np.column_stack([s.points[:, 0], np.full(len(s), s.points[:, 1].mean())]),
                           width=s.width) for s in d.strokes], size=d.size)
    gen = tr.apply_tremor(flat, model, np.random.default_rng(5))
    got = tr.residual_stats(tr.drawing_residuals(gen))
    assert got["rms"] == pytest.approx(ref["rms"], rel=0.2)
    assert got["corr_len_w"] == pytest.approx(ref["corr_len_w"], rel=0.2)
    # spectrum shape: band powers agree
    for k in ("rms_lambda_2_4w", "rms_lambda_4_8w"):
        assert got[k] == pytest.approx(ref[k], rel=0.3)
    # stationary synthesis matches the model's own rms
    y = tr.synth_residual(model, 200000, np.random.default_rng(1))
    assert y.std() == pytest.approx(model.rms, rel=0.05)


def test_floor_subtraction_reduces_rms(model):
    real = tr.drawing_residuals(_ar_drawing(seed=1, amp_w=0.12))
    floor = tr.drawing_residuals(_ar_drawing(seed=2, amp_w=0.06))
    m = tr.fit_model(real, floor)
    assert m.rms < tr.fit_model(real).rms
    assert m.rms == pytest.approx(np.sqrt(model.rms ** 2 * (1 - 0.25)), rel=0.25)


def test_determinism_and_purity(model):
    d = _scene()
    before = [s.points.copy() for s in d.strokes]
    a = tr.apply_tremor(d, model, np.random.default_rng(3))
    b = tr.apply_tremor(d, model, np.random.default_rng(3))
    for sa, sb in zip(a.strokes, b.strokes):
        np.testing.assert_array_equal(sa.points, sb.points)
    for s, p in zip(d.strokes, before):
        np.testing.assert_array_equal(s.points, p)
    c = tr.apply_tremor(d, model, np.random.default_rng(4))
    assert not np.allclose(a.strokes[0].points, c.strokes[0].points)


def test_amount_zero_is_identity(model):
    d = _scene()
    z = tr.apply_tremor(d, model, np.random.default_rng(0), amount=0.0)
    for s, t in zip(d.strokes, z.strokes):
        np.testing.assert_array_equal(s.points, t.points)
        assert s.closed == t.closed


def test_endpoints_pinned_and_contacts_kept(model):
    d = _scene()
    big = tr.TremorModel(**{**model.__dict__, "rms": model.rms * 3, "psd": list(np.asarray(model.psd) * 9)})
    for seed in range(5):
        out = tr.apply_tremor(d, big, np.random.default_rng(seed))
        host, stem = out.strokes[0], out.strokes[1]
        # free end of the host and both ends of the stem: pinned or re-snapped
        np.testing.assert_allclose(host.points[0], d.strokes[0].points[0], atol=1e-9)
        np.testing.assert_allclose(stem.points[0], d.strokes[1].points[0], atol=1e-9)
        # the stem ENDS on the host's interior: still touching it
        from shapely.geometry import LineString, Point
        d0 = LineString(d.strokes[0].points).distance(Point(d.strokes[1].points[-1]))
        d1 = LineString(host.points).distance(Point(stem.points[-1]))
        assert d1 <= d0 + 0.1 * W
        np.testing.assert_allclose(host.points[-1], d.strokes[0].points[-1], atol=1e-9)
        # the tremor is really there, in the interior
        dev = [LineString(d.strokes[0].points).distance(Point(p)) for p in host.points[::10]]
        assert max(dev) > 0.1 * W
        assert out.strokes[2].closed


def test_tremor_amplitude_scales_with_amount(model):
    d = _ar_drawing(seed=3, n_strokes=6)
    flat = Drawing([Stroke(np.column_stack([s.points[:, 0], np.full(len(s), s.points[:, 1].mean())]),
                           width=s.width) for s in d.strokes], size=d.size)
    r1 = tr.residual_stats(tr.drawing_residuals(tr.apply_tremor(flat, model, np.random.default_rng(0), 1.0)))["rms"]
    r5 = tr.residual_stats(tr.drawing_residuals(tr.apply_tremor(flat, model, np.random.default_rng(0), 0.5)))["rms"]
    assert r5 == pytest.approx(0.5 * r1, rel=0.05)


def test_detremor_removes_residual_and_keeps_ends(model):
    d = _ar_drawing(seed=4, n_strokes=4)
    clean = tr.detremor(d)
    a = tr.residual_stats(tr.drawing_residuals(d))["rms"]
    b = tr.residual_stats(tr.drawing_residuals(clean))["rms"]
    assert b < 0.35 * a
    for s, t in zip(d.strokes, clean.strokes):
        np.testing.assert_allclose(t.points[[0, -1]], s.points[[0, -1]], atol=1e-6)


def test_model_json_roundtrip(model, tmp_path):
    p = tmp_path / "m.json"
    model.save(p)
    m2 = tr.TremorModel.load(p)
    assert m2.rms == model.rms and m2.end_edges[-1] == np.inf
    y1 = tr.synth_residual(model, 500, np.random.default_rng(2))
    y2 = tr.synth_residual(m2, 500, np.random.default_rng(2))
    np.testing.assert_allclose(y1, y2)


# ---------------------------------------------------------------------------
# v2: bursty tremor (regime + kinks)
# ---------------------------------------------------------------------------

def _v2(model, regime=None, kinks=None):
    return tr.TremorModel(**{**model.__dict__, "version": 2,
                             "regime": regime or {"kind": "lognormal", "sigma": 0.6, "corr_w": 6.0},
                             "kinks": kinks or {"rate_per_100w": 3.0, "amp_w": 0.3, "amp_log_sd": 0.3, "tau_w": 0.75}})


def test_v1_still_available(model, tmp_path):
    d = _scene()
    m2 = _v2(model)
    a = tr.apply_tremor(d, m2, np.random.default_rng(3), mode="v1")
    b = tr.apply_tremor(d, model, np.random.default_rng(3))
    for sa, sb in zip(a.strokes, b.strokes):
        np.testing.assert_array_equal(sa.points, sb.points)
    c = tr.apply_tremor(d, m2, np.random.default_rng(3))
    assert not np.allclose(a.strokes[0].points, c.strokes[0].points)
    # a v1 JSON (no v2 fields) loads as v1; a v2 model round-trips
    p = tmp_path / "v1.json"
    js = model.to_json()
    for k in ("version", "regime", "kinks"):
        js.pop(k)
    p.write_text(__import__("json").dumps(js))
    assert tr.TremorModel.load(p).version == 1
    m2.save(tmp_path / "v2.json")
    assert tr.TremorModel.load(tmp_path / "v2.json").regime == m2.regime


def test_v2_determinism_purity_identity(model):
    d = _scene()
    m2 = _v2(model)
    before = [s.points.copy() for s in d.strokes]
    a = tr.apply_tremor(d, m2, np.random.default_rng(7))
    b = tr.apply_tremor(d, m2, np.random.default_rng(7))
    for sa, sb in zip(a.strokes, b.strokes):
        np.testing.assert_array_equal(sa.points, sb.points)
    for s, p in zip(d.strokes, before):
        np.testing.assert_array_equal(s.points, p)
    z = tr.apply_tremor(d, m2, np.random.default_rng(0), amount=0.0)
    for s, t in zip(d.strokes, z.strokes):
        np.testing.assert_array_equal(s.points, t.points)


def test_v2_ends_pinned_and_contacts_kept(model):
    from shapely.geometry import LineString, Point
    d = _scene()
    big = _v2(tr.TremorModel(**{**model.__dict__, "rms": model.rms * 3, "psd": list(np.asarray(model.psd) * 9)}))
    for seed in range(5):
        out = tr.apply_tremor(d, big, np.random.default_rng(seed))
        host, stem = out.strokes[0], out.strokes[1]
        np.testing.assert_allclose(host.points[0], d.strokes[0].points[0], atol=1e-9)
        np.testing.assert_allclose(host.points[-1], d.strokes[0].points[-1], atol=1e-9)
        np.testing.assert_allclose(stem.points[0], d.strokes[1].points[0], atol=1e-9)
        d0 = LineString(d.strokes[0].points).distance(Point(d.strokes[1].points[-1]))
        assert LineString(host.points).distance(Point(stem.points[-1])) <= d0 + 0.1 * W
        assert out.strokes[2].closed


def _regime_drawing(regime, seed=0, n_strokes=16, length_w=400.0, amp_w=0.1):
    rng = np.random.default_rng(seed)
    st = []
    n = int(length_w / tr.STEP_W)
    for k in range(n_strokes):
        off = _ar2_offsets(rng, n)
        off = off / off.std() * amp_w * W
        if regime:
            off = off * tr.synth_regime(regime, n, rng)
        pts = np.column_stack([50 + np.arange(n) * tr.STEP_W * W, 50 + 40 * k + off])
        st.append(Stroke(pts, width=np.full(n, W)))
    return Drawing(st, source="regime", size=(int(100 + length_w * W), 100 + 40 * n_strokes))


def test_regime_fit_recovers_switching_statistics():
    true = tr.markov2_normalised(3.0, 24.0, 8.0)
    res = tr.drawing_residuals(_regime_drawing(true))
    grid = {"ratio": [1.5, 3.0, 5.0], "dwell_lo_w": [8.0, 24.0, 64.0], "dwell_hi_w": [3.0, 8.0, 24.0]}
    f = tr.fit_regime(res, 0, kind="markov2", kappa_norm=False, grid=grid, fit_kinks=False)
    r = f["regime"]
    assert r["gain_hi"] / r["gain_lo"] == pytest.approx(3.0)
    assert r["dwell_lo_w"] == 24.0 and r["dwell_hi_w"] == 8.0
    # the measured switching statistics are reproduced
    for k in ("dwell_shaky_w", "dwell_calm_w", "shaky_frac"):
        assert f["fit"][k] == pytest.approx(f["target"][k], rel=0.25)
    # a stationary process is not called bursty
    res0 = tr.drawing_residuals(_regime_drawing(None, seed=1))
    f0 = tr.fit_regime(res0, 0, kind="lognormal", kappa_norm=False,
                       grid={"sigma": [0.0, 0.3, 0.6], "corr_w": [8.0]}, fit_kinks=False)
    assert f0["regime"]["sigma"] == 0.0
    b0 = tr.burst_stats(res0, np.random.default_rng(0), bimodal=False)
    b1 = tr.burst_stats(res, np.random.default_rng(0), bimodal=False)
    assert b1["env_lsd_within_excess"] > 2 * b0["env_lsd_within_excess"]


def test_regime_and_kink_synthesis_normalised():
    g = tr.synth_regime({"kind": "lognormal", "sigma": 0.5, "corr_w": 6.0}, 100000, np.random.default_rng(0))
    assert np.mean(g ** 2) == pytest.approx(1.0, rel=0.05)
    g = tr.synth_regime(tr.markov2_normalised(3.0, 20.0, 10.0), 100000, np.random.default_rng(0))
    assert np.mean(g ** 2) == pytest.approx(1.0, rel=0.08)
    k = tr.synth_kinks({"rate_per_100w": 2.0, "amp_w": 0.5, "tau_w": 0.75}, 40000, np.random.default_rng(0))
    n_events = len(tr._runs(np.abs(k) > 0.2))
    assert 100 < n_events < 300           # 40000 · 0.25 w = 10000 w → ≈ 200 kinks
