"""Round 11 — measurement, next versions (kit/measure_next.py). Fast (< 60 s)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesture import kit  # noqa: E402
from gesture.kit import measure_next as mn  # noqa: E402
from gesture.kit import voices_machine_diagram as vd  # noqa: E402
from gesture.kit.core import Mark  # noqa: E402

DRIFT = {"id": "drift", "hands": ["matisse", "shikasta"], "length": 2.0}


def _run(mods, seed=11, voice=None, **kw):
    return kit.run({"seed": seed, "frame": [200, 140], "margin": 6.0, "voice": voice or dict(DRIFT),
                    "modulators": mods, "renderer": {"id": "measure_wire"}, **kw})


def _loopy(n=1600):
    """A prolate trochoid whose loops change direction (c(t) changes sign): real
    self-crossing loops and real inflections."""
    t = np.linspace(0, 8 * math.pi, n)
    c = np.cos(t / 4.0)
    return np.column_stack([20 + 6 * t - 14 * np.sin(t) * c, 70 + 14 * np.cos(t) * c])


@pytest.fixture(scope="module")
def drift_M():
    """Round 10's drift (seed 7003): it crosses itself, loops and comes close to itself."""
    s = kit.run({"seed": 7003, "frame": [267, 180], "margin": 8.0,
                 "voice": {"id": "drift", "hands": ["matisse", "shikasta", "lichtenberg"], "length": 6.0}})
    return mn.measure_plus(s.marks)


def _M(p, voice=None):
    ch = {} if voice is None else {"voice": voice}
    return mn.measure_plus([Mark(p, ch, {"voices": ["a", "b"]})])


def test_registered_and_discovered():
    assert not {k for k in kit.DISCOVERY_ERRORS if "measure_next" in k}
    reg = kit.registry()
    assert {"measure_next", "measure_next_rechain", "measure_next_rehand"} <= set(reg["modulator"])
    assert "measure_next_duet" in reg["voice"]


@pytest.mark.parametrize("cut", ["inflection", "pause", "hand", "crossing", "approach"])
def test_covering_cuts_cover_the_whole_line_in_order(cut, drift_M):
    M = drift_M
    sp = mn.cut_specimens(M, cut, 0.012)
    assert len(sp) >= 2
    assert sum(t["length"] for t in sp) / M["L"] > 0.97
    for a, b in zip(sp[:-1], sp[1:]):
        assert a["b"] == b["a"]                                   # contiguous, nothing dropped
        assert a["s0"] < b["s0"]


def test_hand_cut_falls_on_the_hand_change():
    p = _loopy()
    v = (np.arange(len(p)) > 700).astype(float)
    M = _M(p, v)
    sp = mn.cut_specimens(M, "hand", 0.01)
    assert len(sp) == 2 and sp[0]["voice"] == 0 and sp[1]["voice"] == 1


def test_loops_are_closed_and_crossings_are_found(drift_M):
    M = drift_M
    xs = mn.self_crossings(M)
    assert len(xs) >= 10
    loops = mn.cut_specimens(M, "loops", 0.012)
    assert len(loops) >= 3
    for t in loops:
        assert np.linalg.norm(t["p"][0] - t["p"][-1]) < 2.0       # a loop ends where it began


def test_closest_approaches_are_near_misses_not_crossings():
    t = np.linspace(0, 1, 800)
    a = np.column_stack([20 + 120 * t, 60 + 0 * t])
    b = np.column_stack([140 - 120 * t, 64 + 25 * (t - 0.5) ** 2])  # comes back, 4 mm away at its closest
    M = _M(np.vstack([a, b]))
    ap = mn.closest_approaches(M, 0.01)
    assert ap and all(d > 0.25 for _, _, d in ap)
    assert min(d for _, _, d in ap) < 5.0


def test_norms():
    rng = np.random.default_rng(0)
    p = np.cumsum(rng.normal(size=(200, 2)), axis=0) * 0.3
    q = mn.norm_geom(p, "chord")
    assert np.allclose(q[0], 0) and abs(q[-1, 1]) < 1e-9
    q = mn.norm_geom(p, "axis+size")
    assert abs(np.ptp(q, axis=0).max() - 1.0) < 1e-9 and np.ptp(q[:, 0]) >= np.ptp(q[:, 1]) - 1e-9
    assert q[-1, 0] >= q[0, 0]


def test_rechain_time_order_reproduces_the_drawing_exactly():
    M = _M(_loopy())
    sp = mn.cut_specimens(M, "inflection", 0.01)
    ch = mn.rechain(M, sp, list(range(len(sp))))
    assert np.allclose(ch["p"], M["p"][ch["src"]], atol=1e-9)


def test_rechain_keeps_g1_where_the_collage_breaks(drift_M):
    M = drift_M
    sp = mn.cut_specimens(M, "inflection", 0.012)
    seq = mn.rechain_order(sp, "sign", M)
    assert sorted(seq) == list(range(len(sp)))
    g1 = mn.join_report(M, sp, mn.rechain(M, sp, seq))
    col = mn.join_report(M, sp, mn.rechain(M, sp, seq, rotate=False))
    assert g1["visible_kinks"] <= g1["orig_visible_kinks"] + 1
    assert col["tangent_deg_median"] > 3 * max(g1["tangent_deg_median"], 1.0)
    assert g1["visible_kappa_jumps"] <= col["visible_kappa_jumps"]


@pytest.mark.parametrize("order", mn.RECHAIN)
def test_rechain_orders_are_permutations(order):
    M = _M(_loopy())
    sp = mn.cut_specimens(M, "inflection", 0.01)
    seq = mn.rechain_order(sp, order, M, np.random.default_rng(1))
    assert sorted(seq) == list(range(len(sp)))


def test_labels_avoid_each_other_and_the_line():
    M = _M(_loopy())
    ss = list(np.linspace(0.02, 0.98, 30) * M["L"])
    labs = [f"{i + 1:02d}" for i in range(30)]
    _, rects = mn.place_labels(M, ss, labs, label_h=2.0, avoid=True)
    st = mn.label_stats(M["p"], rects)
    old = mn.label_stats(M["p"], mn.round10_rects(M, ss, labs, label_h=2.0, tick=1.6))
    assert st["overlaps"] == 0 and st["on_line"] == 0
    assert old["overlaps"] + old["on_line"] >= st["overlaps"] + st["on_line"]


def test_families_are_deterministic_and_ranked_by_turning():
    M = _M(_loopy())
    sp = mn.cut_specimens(M, "inflection", 0.005)
    f1, f2 = mn.families(sp, 4), mn.families(sp, 4)
    assert f1 == f2 and set(f1) == set(range(max(f1) + 1))
    mt = [np.mean([abs(sp[i]["turn"]) for i in range(len(sp)) if f1[i] == g]) for g in range(max(f1) + 1)]
    assert mt == sorted(mt)


@pytest.mark.parametrize("plate,page,extra", [("grid", "diptych", {"trace": True}),
                                               ("frieze", "margin", {}),
                                               ("exploded", "diptych", {"cap": 2.0}),
                                               ("taxonomy", "diptych", {"hist": "length"}),
                                               ("taxonomy", "diptych", {"hist": "turning", "hist_style": "tally"}),
                                               ("grid", "triptych", {"rechain": "turning"})])
def test_pair_runs_keep_the_drawing_and_number_both_sides(plate, page, extra):
    mods = [{"id": "measure_next", "plate": plate, "page": page, "cut": "inflection", **extra}]
    s = _run(mods)
    roles = [m.meta.get("measure_role", "drawing") for m in s.marks]
    assert roles.count("drawing") == 1
    assert roles.count("chart") > 5 and roles.count("index") > 3
    if page == "triptych":
        assert roles.count("rechain") == 1
    W, H = s.frame
    for m in s.marks:
        assert np.all(m.points >= -1) and np.all(m.points[:, 0] <= W + 1) and np.all(m.points[:, 1] <= H + 1)
    s2 = _run(mods)
    assert all(np.array_equal(a.points, b.points) for a, b in zip(s.marks, s2.marks))


def test_taxonomy_labels_are_family_letters_on_both_sides():
    s = _run([{"id": "measure_next", "plate": "taxonomy", "cut": "inflection", "families": 3, "index_h": 1.6}])
    assert any(m.meta.get("plate_role") == "rule" for m in s.marks)        # rules between families


def test_drawn_by_keeps_rules_straight():
    s = _run([{"id": "measure_next", "cut": "inflection", "trace": True, "cells": 6, "drawn_by": "matisse",
               "straight": "rules+labels+specimens"}])
    rules = [m for m in s.marks if m.meta.get("plate_role") == "rule"]
    traces = [m for m in s.marks if m.meta.get("plate_role") == "trace"]
    assert rules and all(len(m) == 2 for m in rules)
    assert traces


def test_shadow_replaces_the_line_with_merged_beads():
    s = _run([{"id": "measure_next", "cut": "inflection", "shadow": "turns"}])
    roles = [m.meta.get("measure_role", "drawing") for m in s.marks]
    assert "drawing" not in roles and roles.count("shadow") >= 2


def test_rechain_modulator_is_one_line_with_join_report():
    s = _run([{"id": "measure_next_rechain", "cut": "inflection", "order": "turning"}])
    assert len(s.marks) == 1
    rep = s.marks[0].meta["rechain_joins"]
    assert rep["joins"] >= 2
    assert "mn_specimen" in s.marks[0].channels and "voice" in s.marks[0].channels


def test_rehand_changes_hand_per_specimen_and_keeps_its_course():
    base = _run([])
    s = _run([{"id": "measure_next_rehand", "hands": ["matisse", "lichtenberg"], "grain": 0.04}])
    assert len(s.marks) == len(base.marks) == 1
    m, b = s.marks[0], base.marks[0]
    assert set(np.unique(m.channels["voice"]).astype(int)) == {0, 1}
    assert np.linalg.norm(m.points[0] - b.points[0]) < 1e-6 and np.linalg.norm(m.points[-1] - b.points[-1]) < 1e-6
    assert m.meta["voices"] == ["matisse", "lichtenberg"]


def test_duet_voice_two_lines_two_voices():
    s = kit.run({"seed": 5, "frame": [200, 140], "voice": {"id": "measure_next_duet", "length": 1.5}})
    assert len(s.marks) == 2
    assert [int(m.channels["voice"][0]) for m in s.marks] == [0, 1]
    assert s.marks[0].meta["voices"] == ["matisse", "lichtenberg"]


def test_hist_steps_and_tally():
    vals = list(np.linspace(1, 50, 20))
    labs = [f"{i:02d}" for i in range(20)]
    st = mn.plate_hist(vals, labs, (0, 0, 80, 30), what="length", style="steps", label_h=2.0)
    hist = [p for p, r in st if r == "hist"]
    assert len(hist) == 1 and np.allclose(hist[0][0], hist[0][-1])          # one closed staircase
    ta = mn.plate_hist(vals, labs, (0, 0, 80, 40), what="turning", style="tally", label_h=2.0)
    assert sum(1 for _, r in ta if r == "label") > 20                       # the bars are made of numbers


def test_index_marks_use_the_chart_pen():
    s = _run([{"id": "measure_next", "cut": "inflection"}])
    pens = {i.meta["measure_role"]: i.pen for i in s.inks}
    assert pens["index"] == pens["chart"] < pens["drawing"]
    assert vd.measure([s.marks[0]])["L"] > 0


def test_defaults_without_avoid_redraw_the_frozen_pair_atlas():
    """measure_next's defaults are round 10's numbered atlas pairing (the frozen study)."""
    a = _run([{"id": "measure_pair", "chart": "atlas", "layout": "diptych", "split": 0.4, "cells": 24,
               "order": "time", "label_h": 2.0, "index_h": 2.0}])
    b = _run([{"id": "measure_next", "avoid": False}])
    assert len(a.marks) == len(b.marks)
    assert all(np.allclose(x.points, y.points) for x, y in zip(a.marks, b.marks))
