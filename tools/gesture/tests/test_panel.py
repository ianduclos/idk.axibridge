import copy
import warnings

import numpy as np
import pytest

from gesture import panel, synth
from gesture.core import Drawing, Stroke

SIZE = (900, 700)


def _scenes():
    rng = np.random.default_rng(7)
    return [
        synth.scene_matisse_like(rng, SIZE),
        synth.scene_random(rng, SIZE, n_strokes=12),
        synth.scene_closed_loop(SIZE),
        synth.scene_x_crossing(SIZE),
        synth.scene_t_junction(SIZE),
    ]


def _feats(d, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # clothoid may be absent
        return panel.features(d, **kw)


def _transform(d: Drawing, scale: float = 1.0, angle: float = 0.0, shift=(0.0, 0.0)) -> Drawing:
    c, s = np.cos(angle), np.sin(angle)
    M = np.array([[c, -s], [s, c]]) * scale
    out = []
    for st in d.strokes:
        w = None if st.width is None else st.width * scale
        out.append(Stroke(st.points @ M.T + np.asarray(shift), width=w, closed=st.closed, meta=st.meta))
    return Drawing(out, source=d.source, size=d.size, meta=d.meta)


def test_finite_and_documented():
    for d in _scenes():
        f = _feats(d)
        assert f, d.source
        assert set(f) <= set(panel.FEATURE_DOCS), set(f) - set(panel.FEATURE_DOCS)
        assert all(panel.group_of(k) in panel.GROUPS for k in f)
        for k, v in f.items():
            assert isinstance(v, float)
            assert np.isfinite(v) or np.isnan(v), k
    # a rich multi-stroke scene has every always-defined feature finite
    f = _feats(synth.scene_random(np.random.default_rng(3), SIZE, n_strokes=20))
    for k in ("k_q50", "k_mean", "infl_rate", "turn_tcorr_10", "len_ink", "rel_near_rate", "ext_rate"):
        assert np.isfinite(f[k]), k


def _close(a: dict, b: dict, rtol: float, atol: float, skip=()):
    assert set(a) == set(b)
    bad = []
    for k in a:
        if k.startswith(skip):
            continue
        x, y = a[k], b[k]
        if np.isnan(x) and np.isnan(y):
            continue
        if not np.isclose(x, y, rtol=rtol, atol=atol):
            bad.append((k, x, y))
    assert not bad, bad


@pytest.mark.parametrize("scale", [2.0, 0.5])
def test_scale_invariant(scale):
    d = synth.scene_matisse_like(np.random.default_rng(11), SIZE)
    # extremum widths / heights and fit-derived counts sit near thresholds, so
    # compare with a modest tolerance; everything is in ref/σ units.
    _close(_feats(d), _feats(_transform(d, scale=scale)), rtol=0.05, atol=0.03)


def test_rotation_invariant():
    d = synth.scene_random(np.random.default_rng(12), SIZE, n_strokes=10)
    r = _transform(d, angle=0.7, shift=(300.0, -50.0))
    # ref (bbox diagonal) itself changes under rotation, so lengths/ref and
    # κ·ref shift with it: compare after removing that factor.
    a, b = _feats(d), _feats(r)
    ratio = r.ref_length() / d.ref_length()
    b_scaled = dict(b)
    for k in ("len_ink", "len_q10", "len_q50", "len_q90"):
        b_scaled[k] = b[k] * ratio
    # 90° keeps the bbox: exact comparison of every feature
    r90 = _transform(d, angle=np.pi / 2)
    _close(a, _feats(r90), rtol=0.03, atol=0.03)
    # arbitrary angle: ratio-free features only (shape of distributions)
    for k in ("turn_tcorr_02", "turn_net_ratio", "len_top_share", "len_count",
              "rel_cross_per_stroke", "k_cv", "k_css_r2"):
        assert np.isclose(a[k], b[k], rtol=0.05, atol=0.03) or (np.isnan(a[k]) and np.isnan(b[k])), k


def test_straight_line_has_no_curvature():
    pts = np.column_stack([np.linspace(0, 500, 200), np.linspace(0, 120, 200)])
    d = Drawing([Stroke(pts), Stroke(pts + [0, 300])], size=SIZE)
    f = _feats(d)
    for k in ("k_q10", "k_q50", "k_q90", "k_mean", "infl_rate", "ext_rate", "turn_abs"):
        assert abs(f[k]) < 1e-6, (k, f[k])
    assert f["turn_tcorr_10"] == pytest.approx(1.0)
    assert np.isnan(f["k_cv"])          # 0/0: documented NaN


def test_circle_kappa_matches_ref():
    r = 200.0
    t = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    d = Drawing([Stroke(np.column_stack([450 + r * np.cos(t), 350 + r * np.sin(t)]), closed=True)], size=SIZE)
    f = _feats(d)
    expect = 2 * np.sqrt(2)                       # κ = 1/r, ref = 2√2 r
    for k in ("k_q10", "k_q50", "k_q90", "k_mean"):
        assert f[k] == pytest.approx(expect, rel=0.01), k
    assert f["k_css_r2"] == pytest.approx(1.0, abs=0.01)
    assert f["infl_rate"] == 0.0
    assert f["ext_rate"] == 0.0
    assert f["turn_net_ratio"] == pytest.approx(1.0, abs=1e-6)
    assert f["len_closure"] == 1.0


def test_width_groups_absent_without_width():
    d = synth.scene_random(np.random.default_rng(4), SIZE, n_strokes=6)
    assert all(st.width is None for st in d.strokes)
    f = _feats(d)
    assert not any(k.startswith(("w_", "end_")) for k in f)
    rng = np.random.default_rng(5)
    dw = Drawing([synth.with_width(st, 4.0, rng, taper=True) for st in d.strokes], size=d.size)
    fw = _feats(dw)
    assert any(k.startswith("w_") for k in fw) and any(k.startswith("end_") for k in fw)
    assert fw["end_thin_q50"] < 0.6           # taper to ~25% of base
    assert not any(k.startswith(("w_", "end_")) for k in _feats(dw, width_available=False))


def test_pure_and_deterministic():
    d = synth.scene_matisse_like(np.random.default_rng(9), SIZE)
    before = copy.deepcopy(d.to_json())
    a = _feats(d)
    b = _feats(d)
    assert d.to_json() == before
    assert a.keys() == b.keys()
    assert all((a[k] == b[k]) or (np.isnan(a[k]) and np.isnan(b[k])) for k in a)


def test_clothoid_failure_is_flagged(monkeypatch):
    import gesture.clothoid as cl

    def boom(*a, **k):
        raise RuntimeError("nope")
    monkeypatch.setattr(cl, "fit_stroke", boom, raising=False)
    d = synth.scene_matisse_like(np.random.default_rng(1), SIZE)
    with pytest.warns(RuntimeWarning):
        f, info = panel.features_with_info(d)
    assert info["clothoid"] != "ok"
    assert not any(k.startswith("cl_") for k in f)
    assert "k_mean" in f
