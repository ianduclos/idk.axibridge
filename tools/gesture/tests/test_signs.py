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


# --- line events -----------------------------------------------------------

def _net_lines():
    """A small network: a wavy line, a line ending ON it (T junction), a
    crossing line, a line with a sharp corner and free ends."""
    t = np.linspace(0, 1, 300)
    a = np.column_stack([10 + 120 * t, 60 + 8 * np.sin(5 * t)])
    b = np.column_stack([70 + 0 * t, 10 + 50 * t])                 # ends on a (T)
    c = np.column_stack([30 + 60 * t, 20 + 90 * t])                # crosses a
    u = np.linspace(0, 1, 150)
    k = np.vstack([np.column_stack([100 + 30 * u, 90 + 0 * u]),
                   np.column_stack([130 - 25 * u[1:], 90 + 30 * u[1:]])])  # corner
    return [a, b, c, k]


def _connected_to_line(st, lines, tol):
    from shapely.geometry import LineString
    U = [LineString(p) for p in lines]
    return min(u.distance(LineString(st.points)) for u in U) <= tol


def test_events_edit_the_lines_not_stamps():
    L = _net_lines()
    rng = np.random.default_rng(4)
    evs = signs.plan_events(L, rng, signs.DEFAULT_EVENT_GRAMMAR, w=0.6, n=8)
    assert len(evs) >= 5
    assert all(e.site in signs.EVENT_SITES and e.op in signs.EVENT_OPS[e.site] or e.op == "pupil" for e in evs)
    sts = signs.apply_events(L, evs, np.random.default_rng(5), w=0.6)
    lines_out = [s for s in sts if "line" in s.meta and "parent" not in s.meta]
    assert len(lines_out) == len(L)
    # every input line is still there (its points are a prefix-preserving edit) and some carry events
    assert sum(1 for s in lines_out if s.meta["events"]) >= 3
    assert any(float(s.r.max()) > 1.5 for s in lines_out)          # a mass grown on a line
    # children are rooted INSIDE their line's ink (so they render as one mark);
    # only detached dots float, and they stay close to their line
    from gesture import regime as rg
    for s in sts[len(L):]:
        par = lines_out[s.meta["parent"]]
        if s.meta.get("detached"):
            # the gap is the calligraphic gap: ≤ 3 dot sizes (+ the dot itself)
            assert _connected_to_line(s, [par.points], 4.0 * float(s.mass.max()) / 0.75)
            continue
        a, rho = rg.footprint(par, 0.5)
        d = np.linalg.norm(par.points - s.points[0], axis=1)
        j = int(np.argmin(d))
        assert d[j] <= a[j] + rho[j] + 0.05


def test_events_detached_dots_are_rare():
    L = _net_lines()
    n_det = n_all = 0
    for seed in range(6):
        evs = signs.plan_events(L, np.random.default_rng(seed), w=0.6, n=8)
        n_all += len(evs)
        n_det += sum(1 for e in evs if e.op == "detached")
    assert n_all and n_det / n_all < 0.2


def test_events_deterministic_and_polylines():
    L = _net_lines()
    out = []
    for _ in range(2):
        sts = signs.place_events(L, np.random.default_rng(9), w=0.6, n=6)
        out.append(signs.render_events(sts, 0.5))
    assert len(out[0]) == len(out[1])
    for p, q in zip(*out):
        assert p.ndim == 2 and p.shape[1] == 2 and np.isfinite(p).all()
        assert np.array_equal(p, q)


def test_events_random_null_keeps_ops_and_inputs():
    L = _net_lines()
    before = [p.copy() for p in L]
    evs = signs.plan_events(L, np.random.default_rng(1), w=0.6, n=8)
    rnd = signs.plan_events(L, np.random.default_rng(2), w=0.6, mode="random", like=evs)
    assert rnd and all(e.group == -1 for e in rnd)
    assert len(rnd) <= len(evs)
    assert all(np.array_equal(x, y) for x, y in zip(L, before))


def test_event_grammar_policy_gate():
    forms = [{"site": "end", "op": "drop", "extent_w": 5.0, "group": None, "centre_w": [0, 0]}]
    with pytest.raises(cg.PolicyError):
        signs.learn_event_grammar(forms, skeleton_w=1000, dot_records=[_rec("ok-ex"), _rec("quran")], manifest=MAN)
    g = signs.learn_event_grammar(forms, skeleton_w=1000, dot_records=[_rec("ok-ex")], manifest=MAN)
    assert g.sources == ["ok-ex"] and g.gap_ratio and g.site_p == {"end": 1.0}


def test_reference_events_cover_manual_forms():
    from experiments import signs_study as st
    assert len(signs.REFERENCE_EVENTS) == len(st.MANUAL_REF)
    for site, op, _ in signs.REFERENCE_EVENTS:
        assert site is None or op in signs.EVENT_OPS[site]
