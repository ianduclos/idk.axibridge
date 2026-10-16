"""Broad-nib model + calligraphy policy gate (fast: < 15 s)."""
import numpy as np
import pytest

from gesture import broadnib as bn
from gesture import calligraphy as C
from gesture.core import Drawing, Stroke


def _curve(seed=0, length=700):
    return bn.synth_centreline(np.random.default_rng(seed), length=length, kappa_sd=0.01, corr=80,
                               start=(0.0, 0.0))


def test_fit_recovers_model_exactly_from_samples():
    rng = np.random.default_rng(1)
    th = rng.uniform(-np.pi, np.pi, 2000)
    for phi_deg, W, w0 in ((0, 10, 1), (37, 14, 2), (128, 6, 0.5)):
        w = bn.nib_width(th, np.deg2rad(phi_deg), W, w0) + rng.normal(0, 0.1, th.size)
        f = bn.fit_nib(th, w)
        err = (f.phi_deg - phi_deg + 90) % 180 - 90
        assert abs(err) < 1.0
        assert abs(f.W - W) < 0.3 and abs(f.w_min - w0) < 0.2
        assert f.r2 > 0.98 and f.r2_null < 0.1


def test_direction_free_widths_score_like_null():
    rng = np.random.default_rng(2)
    th = rng.uniform(0, np.pi, 3000)
    f = bn.fit_nib(th, 5 + rng.normal(0, 1, th.size))
    assert f.r2 < 0.05


def test_sweep_width_matches_model_on_true_centreline():
    """Raster of a swept nib: 2·EDT at the true centreline ≈ model width."""
    from scipy import ndimage as ndi
    c = _curve(3) + 200
    phi, W, w0 = np.deg2rad(30), 16.0, 2.0
    g = bn.render_mask(bn.sweep_polygon(c, phi, W, w0), (int(c[:, 0].max() + 200), int(c[:, 1].max() + 200)))
    edt = ndi.distance_transform_edt(g < 0.5)
    q, _, _ = bn._resample(c, 2.0)
    th = bn.page_angle(q, sigma=8.0)
    ij = np.round(q[:, ::-1]).astype(int)
    meas = 2 * edt[ij[:, 0], ij[:, 1]]
    model = bn.nib_width(th, phi, W, w0)
    inner = slice(15, -15)
    assert np.median(np.abs(meas[inner] - model[inner])) < 1.5


def test_extract_and_fit_round_trip():
    """render → extract_hybrid → width samples → φ, W recovered."""
    from gesture import extract_hybrid
    rng = np.random.default_rng(4)
    phi, W, w0 = np.deg2rad(50), 14.0, 2.5
    geoms = []
    for k in range(3):
        c = bn.synth_centreline(rng, length=650, kappa_sd=0.01, corr=80)
        c = c - c.mean(0) + (180 + 220 * k, 400)
        geoms.append(bn.sweep_polygon(np.clip(c, 30, 770), phi, W, w0))
    g = bn.render_mask(geoms, (800, 800))
    d = extract_hybrid.extract(g, **C.EXTRACT_DEFAULTS)
    r = bn.fit_drawing(d)
    f = r["sheet"]
    err = (f.phi_deg - 50 + 90) % 180 - 90
    assert abs(err) < 5.0
    Wpx = f.W * r["w_med"]
    assert 0.75 * W < Wpx < 1.25 * W
    assert f.r2 > 0.8


def test_width_samples_skip_ends_and_junctions():
    p = np.column_stack([np.linspace(0, 200, 201), np.zeros(201)])
    st = Stroke(p, width=np.full(201, 10.0), meta={"junctions": [[100.0, 0.0]]})
    s = bn.width_samples(st)
    assert len(s["s"]) > 0
    assert s["s"].min() >= 15 - 1e-9 and s["s"].max() <= 185 + 1e-9
    assert not np.any(np.abs(s["s"] - 100) < 14)


def test_render_options_are_contiguous_closed_or_runs():
    c = _curve(5, 400) + 60
    geom = bn.sweep_polygon(c, np.deg2rad(40), 20.0, 2.0)
    A = bn.outline_paths(geom)
    B = bn.concentric_paths(geom, 3.0)
    M = bn.multipass_paths(c, bn.model_widths(c, np.deg2rad(40), 20.0, 2.0, sigma=10), 3.0)
    assert 1 <= len(A) <= 4                       # one ribbon → one outline (+ maybe a hole)
    assert len(B) > len(A)
    assert len(M) >= 1
    size = (int(c[:, 0].max() + 60), int(c[:, 1].max() + 60))
    tgt = bn.render_mask(geom, size)
    fb = bn.fidelity(bn.draw_paths(B, size, 3.0, closed=True), tgt)
    assert fb["coverage"] > 0.8


def test_policy_filter_blocks_restricted_content():
    man = {
        "ex": {"content_type": "exercise", "note": ""},
        "doc": {"content_type": "document (petition)", "note": ""},
        "mix": {"content_type": "exercise + poetry", "note": ""},
        "q": {"content_type": "qur'an", "note": ""},
        "dev": {"content_type": "devotional (verify)", "note": ""},
        "alb": {"content_type": "album page", "note": ""},
        "unv": {"content_type": "exercise (model book)", "note": "per-plate religious phrases unverified"},
        "book": {"content_type": "book", "note": ""},
    }
    ok = {k for k, r in man.items() if C.generative_allowed(r)}
    assert ok == {"ex", "doc", "mix"}
    d = Drawing([Stroke(np.zeros((3, 2)))])
    kept = C.filter_generative({k: d for k in man}, manifest=man)
    assert set(kept) == {"ex", "doc", "mix"}
    assert C.require_generative(["ex", "mix"], manifest=man) == ["ex", "mix"]
    for bad in ("q", "dev", "alb", "unv", "book", "missing"):
        with pytest.raises(C.PolicyError):
            C.require_generative(["ex", bad], manifest=man)


def test_policy_on_real_manifest():
    """The harvest manifests: the Baghdadi book (unverified plates), the
    banna'i panel (verify), album pages and every print item are restricted."""
    man = {**C.load_manifest("print"), **C.load_manifest("calligraphy")}
    for rid in ("nyu-baghdadi", "wc-37", "met-451802", "wc-39", "met-450714", "AF01", "AL08_p0011"):
        assert not C.generative_allowed(man[rid]), rid
    for rid in ("wc-12", "wc-13", "wc-15", "met-716305"):
        assert C.generative_allowed(man[rid]), rid
    with pytest.raises(C.PolicyError):
        C.require_generative(["wc-12", "nyu-baghdadi#p15"])


def test_neutral_strings():
    assert all(C.neutral_string_ok(s) for s in C.NEUTRAL_STRINGS)
    for bad in ("الله", "لله", "ﷲ", "كتاب", "ل ه لهه"):
        assert not C.neutral_string_ok(bad)


def test_outline_view_marks_counters():
    yy, xx = np.mgrid[:200, :200]
    r = np.hypot(xx - 100, yy - 100)
    m = (r < 60) & (r > 30)
    d = C.outlines(np.where(m, 0.0, 1.0), mask=m)
    assert sorted(s.meta["hole"] for s in d.strokes) == [False, True]
    outer = [s for s in d.strokes if not s.meta["hole"]][0]
    assert abs(outer.length() - 2 * np.pi * 60) < 10


def test_pen_strokes_drop_hairlines_and_frames():
    def st(y, w, x0=100.0):
        p = np.column_stack([np.linspace(x0, x0 + 300, 50), np.full(50, y)])
        return Stroke(p, width=np.full(50, w))
    d = Drawing([st(200, 10), st(300, 12), st(400, 1.0), st(5, 10)], size=(1000, 1000))
    kept = C.pen_strokes(d)
    ys = sorted(float(s.points[0, 1]) for s in kept.strokes)
    assert ys == [200.0, 300.0]
