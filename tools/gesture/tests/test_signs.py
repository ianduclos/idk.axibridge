"""gesture/signs.py: policy gate, determinism, polyline outputs, scaling."""
import numpy as np
import pytest

from gesture import calligraphy as cg
from gesture import signs

MAN = {
    "ok-ex": {"content_type": "exercise", "note": ""},
    "ok-doc": {"content_type": "document (petition)", "note": ""},
    "quran": {"content_type": "qur'an", "note": ""},
    "devo": {"content_type": "devotional (verify)", "note": ""},
    "book": {"content_type": "exercise (model book)", "note": "unverified religious phrases"},
    "album": {"content_type": "album page", "note": ""},
}


def _rec(src, **kw):
    r = {"source": src, "size_w": 1.8, "aspect": 0.6, "axis_rel": 0.3, "host_gap_w": 1.2, "side_up": True,
         "along_u": 0.5, "cluster": 1, "cluster_lead": True}
    r.update(kw)
    return r


@pytest.mark.parametrize("bad", ["quran", "devo", "book", "album", "unknown-id"])
def test_policy_gate_blocks_restricted_sources(bad):
    recs = [_rec("ok-ex"), _rec(bad)]
    with pytest.raises(cg.PolicyError):
        signs.learn_grammar(recs, manifest=MAN)


def test_policy_gate_allows_secular_and_records_sources():
    g = signs.learn_grammar([_rec("ok-ex"), _rec("ok-doc", side_up=False)], manifest=MAN)
    assert g.sources == ["ok-doc", "ok-ex"]
    assert g.side_up == 0.5 and len(g.gap_w) == 2


def test_real_manifest_gate_on_study_sheets():
    from experiments import signs_study as st
    assert cg.require_generative(st.DOT_SHEETS) == st.DOT_SHEETS
    with pytest.raises(cg.PolicyError):
        cg.require_generative(["wc-37"])          # devotional (verify)
    with pytest.raises(cg.PolicyError):
        cg.require_generative(["nyu-baghdadi"])   # flagged model book


def _lines():
    t = np.linspace(0, 1, 200)
    a = np.column_stack([50 + 500 * t, 300 + 80 * np.sin(6 * t)])
    b = np.column_stack([300 + 60 * np.cos(2 * np.pi * t), 150 + 60 * np.sin(2 * np.pi * t)])
    c = np.column_stack([100 + 350 * t, 450 - 120 * t ** 2])
    return [a, b[:-1], c]


@pytest.mark.parametrize("kind", list(signs.vocabulary()))
def test_make_sign_polylines_and_scaling(kind):
    s1 = signs.make_sign(kind, np.random.default_rng(3), w=1.0)
    s2 = signs.make_sign(kind, np.random.default_rng(3), w=2.5)
    for s in (s1, s2):
        paths, closed = signs.sign_paths(s, pen=s.w)
        assert paths and len(paths) == len(closed)
        for p in paths:
            assert p.ndim == 2 and p.shape[1] == 2 and len(p) >= 2 and np.isfinite(p).all()
    assert s2.scale == pytest.approx(2.5 * s1.scale, rel=1e-6)


def test_place_signs_deterministic_and_clear():
    g = signs.DEFAULT_GRAMMAR
    L = _lines()
    a = signs.place_signs(L, np.random.default_rng(11), g, w=4.0, n=8)
    b = signs.place_signs(L, np.random.default_rng(11), g, w=4.0, n=8)
    assert [s.to_json() for s in a] == [s.to_json() for s in b]
    assert len(a) >= 4
    for s in a:
        assert s.relation in signs.RELATIONS
        paths, _ = signs.sign_paths(s)
        assert all(p.shape[1] == 2 for p in paths)
    r1 = signs.place_random(L, np.random.default_rng(5), a, w=4.0)
    r2 = signs.place_random(L, np.random.default_rng(5), a, w=4.0)
    assert [s.to_json() for s in r1] == [s.to_json() for s in r2]
    assert {s.kind for s in r1} <= {s.kind for s in a}


def test_inputs_not_mutated():
    L = _lines()
    before = [p.copy() for p in L]
    signs.place_signs(L, np.random.default_rng(2), w=4.0, n=5)
    assert all(np.array_equal(x, y) for x, y in zip(L, before))


def test_measure_dots_finds_dot_above_line():
    m = np.zeros((120, 300), bool)
    m[70:76, 20:280] = True                      # a body, w = 6
    yy, xx = np.mgrid[:120, :300]
    m |= (xx - 150) ** 2 + (yy - 55) ** 2 <= 25  # a dot above it
    d = signs.measure_dots(m, source="ok-ex", w=6.0)
    assert len(d) == 1
    assert d[0]["side_up"] and 0.5 < d[0]["host_gap_w"] < 2.5
