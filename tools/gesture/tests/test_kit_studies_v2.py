"""Studies v2 research changes (2026-10-17): the kit sampler, straight chart
lines for a drawn measurement, the chorus voice count, and the exact clothoid
speed-ups (memos). Every change is additive and default-preserving."""
from __future__ import annotations

import copy
import json
import math

import numpy as np
import pytest
from experiments import combo_search as cs
from gesture import clothoid as C
from gesture import kit
from gesture.kit import library as L
from gesture.kit import sampler as S
from gesture.kit import voices_machine_diagram as vd


def _j(x):
    return json.dumps(x, sort_keys=True)


# ---------------------------------------------------------------------------
# sampler
# ---------------------------------------------------------------------------

def test_sampler_with_priors_is_combo_search_exactly():
    for seed in (0, 5, 11, 2026):
        a, b = np.random.default_rng(seed), np.random.default_rng(seed)
        for _ in range(8):
            assert _j(S.sample_recipe(a)) == _j(cs.sample_recipe(b))
    rec = cs.sample_recipe(np.random.default_rng(3))
    assert S.summarize(rec) == cs.summarize(rec)


def test_sample_is_deterministic_valid_and_seeded_by_the_seed():
    a, b = S.sample(123), S.sample(123)
    assert _j(a) == _j(b) and a["seed"] == 123
    kit.validate(a)
    assert _j(S.sample(124)) != _j(a)
    assert not (S._hands_of(a["parts"][0]) & set().union(*[S._hands_of(p) for p in a["parts"][1:]]))


class _Lib(L.Library):
    """The committed library plus one invented generative hand (ids only)."""

    def ids(self, kind):
        return sorted(super().ids(kind) + (["zz_new_hand"] if kind == "hand" else []))

    def entry(self, kind, id):
        if (kind, id) == ("hand", "zz_new_hand"):
            return {**super().entry("hand", "bubble"), "id": "zz_new_hand"}
        return super().entry(kind, id)


def test_library_pools_keep_the_priors_and_take_new_hands():
    lib = L.default()
    pools = S.library_pools(lib)
    assert pools.heavy[:len(S.HEAVY_HANDS)] == S.HEAVY_HANDS     # every prior is still in the library
    extra = set(pools.heavy) - set(S.HEAVY_HANDS)
    assert extra == set(pools.wire) - set(S.WIRE_HANDS)          # hands with no prior join both pools
    grown = S.library_pools(_Lib(lib.root))
    assert "zz_new_hand" in grown.heavy and "zz_new_hand" in grown.wire
    assert "zz_new_hand" not in pools.heavy


# ---------------------------------------------------------------------------
# straight chart lines (measure_pair drawn_by)
# ---------------------------------------------------------------------------

def _chart_polys():
    t = np.linspace(0, 2 * math.pi, 120)
    trace = np.column_stack([10 + 8 * t, 40 + 6 * np.sin(2 * t)])
    rules = [np.array([[0.0, 60.0], [60.0, 60.0]]), np.array([[0.0, 62.0], [45.0, 62.0]])]
    text = vd.text("K12", 2.0, 2.0, 2.0)
    return [trace, *rules, *text]


def test_chart_roles_from_geometry():
    polys = _chart_polys()
    roles = vd.chart_roles(polys, 2.0)
    assert roles[0] == "trace" and roles[1:3] == ["rule", "rule"]
    assert set(roles[3:]) == {"text"}


def test_straight_keeps_chosen_lines_and_leaves_the_rest_bit_identical():
    g = kit.library.default().load("hand", "matisse")
    polys = _chart_polys()
    base = vd.hand_drawn(polys, g, np.random.default_rng(4), amount=1.5, keep=0.006)
    same = vd.hand_drawn(polys, g, np.random.default_rng(4), amount=1.5, keep=0.006, straight=None)
    assert all(np.array_equal(a, b) for a, b in zip(base, same))
    flags = vd.straight_flags(polys, 2.0, "rules", 0.0, np.random.default_rng(0))
    assert flags[1] and flags[2] and not flags[0]
    mixed = vd.hand_drawn(polys, g, np.random.default_rng(4), amount=1.5, keep=0.006, straight=flags)
    for p, b, m, f in zip(polys, base, mixed, flags):
        assert np.array_equal(m, p if f else b)
    assert vd.straight_flags(polys, 2.0, "none", 0.0, np.random.default_rng(0)) is None
    some = vd.straight_flags(polys, 2.0, "none", 0.5, np.random.default_rng(0))
    assert some == vd.straight_flags(polys, 2.0, "none", 0.5, np.random.default_rng(0)) and any(some)


def test_measure_pair_straight_defaults_preserve_the_recipe():
    rec = {"seed": 7, "frame": [200, 140], "margin": 6.0,
           "voice": {"id": "hand", "hand": "lichtenberg", "length": 1.0},
           "modulators": [{"id": "measure_pair", "chart": "ledger", "drawn_by": "matisse"}],
           "renderer": {"id": "measure_wire"}}
    v = kit.validate(rec)["parts"][0]["modulators"][0]
    assert v["straight"] == "none" and v["straight_share"] == 0.0
    a = kit.run(rec)
    b = kit.run({**rec, "modulators": [{**rec["modulators"][0], "straight": "none", "straight_share": 0.0}]})
    assert [k.points.tolist() for k in a.inks] == [k.points.tolist() for k in b.inks]
    c = kit.run({**rec, "modulators": [{**rec["modulators"][0], "straight": "rules"}]})
    chart = [k for k in c.inks if k.meta.get("measure_role") == "chart"]
    flat = [k for k in chart if len(k.points) == 2]
    assert flat                                                   # table rules come back machine-straight
    assert len(c.inks) == len(a.inks)


# ---------------------------------------------------------------------------
# chorus voice count
# ---------------------------------------------------------------------------

def _voice(hand, renderer):
    return {"voice": {"id": "hand", "hand": hand, "length": 0.8},
            "modulators": [{"id": "prosody", "unit": "pulse", "span": 5.0}], "renderer": renderer}


def test_chorus_voices_sings_the_first_n_exactly():
    parts = [_voice("matisse", {"id": "nib", "style": "e"}), _voice("bubble", {"id": "wire", "pen": 0.3}),
             _voice("aaron", {"id": "wire", "pen": 0.3})]
    full = {"seed": 9, "frame": [200, 140], "margin": 8.0, "parts": parts,
            "arranger": {"id": "dev_chorus", "answer_to": "all", "inks": "black,red,blue"}}
    assert kit.validate(full)["arranger"]["voices"] is None
    two = copy.deepcopy(full)
    two["arranger"]["voices"] = 2
    a = kit.run(two)
    b = kit.run({**full, "parts": parts[:2]})
    assert {k.meta["part"] for k in a.inks} == {0, 1}
    assert [k.points.tolist() for k in a.inks] == [k.points.tolist() for k in b.inks]
    with pytest.raises(kit.RecipeError):
        kit.validate({**full, "arranger": {**full["arranger"], "voices": 0}})


# ---------------------------------------------------------------------------
# clothoid: exact speed-ups
# ---------------------------------------------------------------------------

def _wobbly(seed=0, n=400):
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 3 * math.pi, n)
    return np.column_stack([t * 30, 40 * np.sin(t) + rng.normal(0, 0.4, n)])


def test_fit_memo_returns_the_same_fit_as_a_fresh_fit_and_a_private_copy():
    pts = _wobbly(1)
    C._FIT_MEMO.clear()
    a = C.fit_stroke(pts, sigma=4.0)
    b = C.fit_stroke(pts, sigma=4.0)
    fresh = C._fit_stroke(pts, sigma=4.0)
    assert repr(a) == repr(b) == repr(fresh)
    assert a is not b and a.segments is not b.segments
    b.segments.clear()                                            # a caller's copy is its own
    assert repr(C.fit_stroke(pts, sigma=4.0)) == repr(fresh)
    assert repr(C.fit_stroke(pts, sigma=5.0)) != repr(fresh)      # arguments are part of the key


def test_model_sse_memo_is_the_solve():
    pts = _wobbly(2)
    seen = {}
    orig = C._Model.__init__

    def grab(self, *a, **k):
        orig(self, *a, **k)
        seen["m"] = self
    C._Model.__init__ = grab
    try:
        C._fit_stroke(pts, sigma=4.0)
    finally:
        C._Model.__init__ = orig
    m = seen["m"]
    assert m.sse_cache                                           # the greedy did re-visit configurations
    for key, e in list(m.sse_cache.items())[:40]:
        knots = [np.array(k, dtype=int) for k in key]
        assert m.solve(knots)[0] == e
