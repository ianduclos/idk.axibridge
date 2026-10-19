"""Round 16 thread A `aware`: crossing, sympathy, hesitate, accompany, make_room, and the listen bridge."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit._relations import crossings, relation_list  # noqa: E402
from gesture.kit.relations_aware import OUTCOMES  # noqa: E402

FRAME = [200.0, 140.0]
ALL = ("crossing", "sympathy", "hesitate", "accompany", "make_room")


def line(f, x0=10.0, x1=190.0, step=0.5):
    x = np.arange(x0, x1 + 1e-9, step)
    return np.column_stack([x, f(x)]).tolist()


def wave_line():
    """A long wave: crosses a horizontal at y=70 many times."""
    return line(lambda x: 70 + 20 * np.sin(x / 9.0))


def verticals(n=30):
    return [[[x, 15.0], [x, 125.0]] for x in np.linspace(30, 170, n)]


def score(layers, rels, seed=16101):
    return {"version": 2, "frame": FRAME, "seed": seed,
            "layers": [{"id": lid, "pen": pen, "lines": ls, "renderer": {"id": "wire", "pen": 0.4}}
                       for lid, pen, ls in layers],
            "relations": [{"id": f"R{i}", "src": "*", "dst": "*", **r} for i, r in enumerate(rels)]}


def two(rel, a=None, b=None, seed=16101):
    a = a if a is not None else [wave_line()]
    b = b if b is not None else verticals()
    return synth.run(score([("A", "black", a), ("B", "red", b)], [rel], seed), cache=False)


def max_turn(p) -> float:
    """The largest heading change between consecutive segments, degrees (a kink is tens)."""
    d = np.diff(np.asarray(p), axis=0)
    h = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    return float(np.degrees(np.abs(np.diff(h)).max())) if len(h) > 1 else 0.0


def marks(sh, lid):
    return [m for m in sh.marks if m.meta["layer"] == lid]


def total(ms):
    return sum(m.length() for m in ms)


def log(sh, kind=None):
    return [e for e in synth.played(sh)["log"] if kind is None or e["kind"] == kind]


def n_cross(a=None, b=None):
    return len(log(two({"kind": "cross"}, a, b)))


def test_registered_and_contact():
    rel = {r["id"]: r for r in relation_list()}
    for k in ALL:
        assert rel[k]["phase"] == "contact"


ONLY = {f"w_{k}": 0.0 for k in OUTCOMES}


def only(outcome, **kw):
    return {"kind": "crossing", "params": {**ONLY, f"w_{outcome}": 1.0, "tangle": 0.0, **kw}}


# -- crossing ---------------------------------------------------------------

def test_crossing_is_deterministic_and_seeded():
    r = {"kind": "crossing", "params": {"tangle": 0.0}}
    a, b = two(r), two(r)
    assert [e["outcome"] for e in log(a)] == [e["outcome"] for e in log(b)]
    for x, y in zip(a.inks, b.inks):
        np.testing.assert_array_equal(x.points, y.points)
    c = two(r, seed=16102)
    assert [e["outcome"] for e in log(a)] != [e["outcome"] for e in log(c)]


def test_every_crossing_gets_one_counted_outcome():
    n = n_cross()
    assert n >= 20
    sh = two({"kind": "crossing", "params": {"tangle": 0.0}})
    ev = log(sh, "crossing")
    assert len(ev) == n
    seen = {e["outcome"] for e in ev}
    assert seen <= set(OUTCOMES)
    assert len(seen) >= 3                       # varied, not a template
    played = synth.played(sh)["relations"]
    assert sum(sum(r["outcomes"].values()) for r in played) == n


@pytest.mark.parametrize("pen,gap", [(0.4, 1.75), (0.8, 1.0)])
def test_gap_under_breaks_only_the_dst_by_the_right_size(pen, gap):
    n = n_cross()
    base = two({"kind": "cross"})
    sh = two(only("gap_under", pen=pen, gap=gap, jitter=0.0))
    assert all(e["outcome"] == "gap_under" for e in log(sh))
    h = pen * (0.5 + gap)
    assert len(marks(sh, "A")) == len(marks(base, "A"))
    assert total(marks(sh, "A")) == pytest.approx(total(marks(base, "A")))
    lost = total(marks(base, "B")) - total(marks(sh, "B"))
    assert lost == pytest.approx(n * 2 * h, rel=0.03)
    for e in log(sh):
        assert e["gap_mm"] == pytest.approx(2 * h, abs=1e-3)


def test_gap_over_breaks_only_the_src():
    base = two({"kind": "cross"})
    sh = two(only("gap_over", jitter=0.0))
    assert total(marks(sh, "B")) == pytest.approx(total(marks(base, "B")))
    assert total(marks(sh, "A")) < total(marks(base, "A")) - 10


def test_cross_only_changes_nothing():
    base = two({"kind": "cross"})
    sh = two(only("cross"))
    for x, y in zip(base.inks, sh.inks):
        np.testing.assert_array_equal(x.points, y.points)


def test_stop_ends_the_short_tail_at_the_other_line():
    a = [line(lambda x: 70 + 0 * x)]                        # long horizontal
    b = [[[100.0, 20.0], [100.0, 76.0]]]                    # a vertical overshooting it by 6 mm
    sh = two(only("stop"), a, b)
    ev = log(sh)
    assert [e["outcome"] for e in ev] == ["stop"] and ev[0]["who"] == "dst"
    (m,) = marks(sh, "B")
    assert m.points[-1][1] == pytest.approx(70.0, abs=0.05)  # it ends on the other line
    assert total(marks(sh, "A")) == pytest.approx(180.0, abs=0.01)


def test_no_stop_without_a_short_free_tail():
    a = [line(lambda x: 70 + 0 * x)]
    b = [[[100.0, 10.0], [100.0, 130.0]]]                   # 60 mm both sides: too long to drop
    sh = two(only("stop", stop_max=25.0), a, b)
    assert [e["outcome"] for e in log(sh)] == ["cross"]     # stop is ineligible → falls back


def test_streak_makes_runs():
    def changes(st):
        out = [e["outcome"] for e in log(two({"kind": "crossing", "params": {"streak": st, "tangle": 0.0}}))]
        return sum(1 for x, y in zip(out, out[1:]) if x != y) / max(len(out) - 1, 1)
    assert changes(0.9) < changes(0.0) * 0.6


def test_crossing_sympathy_bends_smoothly_without_a_gap():
    a = [line(lambda x: 70 + 0 * x)]
    b = [line(lambda x: 20 + (x - 10) * 0.6, 60.0, 140.0)]
    sh = two(only("sympathy", lean=1.5, reach=6.0), a, b)
    ev = log(sh)
    assert [e["outcome"] for e in ev] == ["sympathy"]
    (m,) = marks(sh, "B")
    base = np.asarray(b[0])
    assert m.length() == pytest.approx(total([]) + np.sum(np.linalg.norm(np.diff(base, axis=0), axis=1)), rel=0.02)
    d = np.abs(m.points[:, 1] - (20 + (m.points[:, 0] - 10) * 0.6)) / np.sqrt(1.36)   # off its own course
    assert 0.5 < d.max() < 2.0                             # it bends, a little
    far = np.abs(m.points[:, 0] - ev[0]["at"][0]) > 8
    assert d[far].max() < 1e-6                             # only near the crossing
    assert max_turn(m.points) < 6.0                        # no kink


def test_tangle_takes_one_outcome():
    a = [line(lambda x: 70 + 3 * np.sin(x * 2.0))]          # a fast wiggle crossing a near-parallel line often
    b = [line(lambda x: 70 + 0.01 * (x - 100))]
    sh = two(only("gap_under", tangle=30.0, min_dash=0.0), a, b)
    ev = log(sh)
    assert sum(e["outcome"] == "gap_under" for e in ev) < len(ev) / 3
    assert all(e.get("tangle") for e in ev if e["outcome"] == "cross")


def test_no_stray_pieces():
    sh = two({"kind": "crossing", "params": {"tangle": 0.0, "min_piece": 2.5}})
    assert min(m.length() for m in sh.marks) >= 2.5 - 1e-6


# -- sympathy ---------------------------------------------------------------

def wiggly():
    return [line(lambda x: 70 + 0.6 * np.sin(x * 2 * np.pi / 2.5))]


def straight(y=72.0, x0=60.0, x1=140.0):
    return [line(lambda x: y + 0 * x, x0, x1)]


@pytest.mark.parametrize("bends,moved,still", [("dst", "B", "A"), ("later", "B", "A"), ("src", "A", "B")])
def test_sympathy_moves_only_the_side_it_should(bends, moved, still):
    base = two({"kind": "cross"}, wiggly(), straight())
    sh = two({"kind": "sympathy", "params": {"bends": bends}}, wiggly(), straight())
    for lid, should in ((moved, True), (still, False)):
        a = np.vstack([m.points for m in marks(base, lid)])
        b = np.vstack([m.points for m in marks(sh, lid)])
        if should:
            assert a.shape != b.shape or not np.allclose(a, b)
        else:
            np.testing.assert_array_equal(a, b)
    assert all(e["outcome"] == "sympathy" and e["bends"] == ("src" if bends == "src" else "dst")
               for e in log(sh))


def test_sympathy_takes_on_the_wiggle_subtly_and_smoothly():
    sh = two({"kind": "sympathy", "params": {"reach": 4.0, "gain": 0.8}}, wiggly(), straight())
    (m,) = marks(sh, "B")
    dy = m.points[:, 1] - 72.0
    assert 0.05 < np.abs(dy).max() < 0.6                  # subtle: under the src's own 0.6 mm
    src = 70 + 0.6 * np.sin(m.points[:, 0] * 2 * np.pi / 2.5)
    mid = (m.points[:, 0] > 70) & (m.points[:, 0] < 130)
    assert np.corrcoef(dy[mid], src[mid] - 70)[0, 1] > 0.6  # in phase with the src's wiggle
    assert np.abs(np.diff(dy)).max() < 0.25                # no kinks
    assert max_turn(m.points) < max_turn(np.asarray(wiggly()[0]))   # never sharper than what it hears
    far = two({"kind": "sympathy"}, wiggly(), straight(y=80.0))
    np.testing.assert_array_equal(marks(far, "B")[0].points, np.asarray(straight(y=80.0)[0]))   # beyond reach


# -- hesitate, accompany, make_room ------------------------------------------

def test_hesitate_rises_before_the_meeting_and_not_beside():
    a = [[[100.0, 10.0], [100.0, 130.0]]]
    b = [line(lambda x: 40 + 0 * x, 20.0, 99.5)]           # runs up to the other line and stops short
    sh = two({"kind": "hesitate", "params": {"amp": 0.3}}, a, b)
    (m,) = marks(sh, "B")
    dy = np.abs(m.points[:, 1] - 40)
    assert dy[m.points[:, 0] > 94].max() > 0.05            # unsure just before it arrives
    assert dy[m.points[:, 0] < 75].max() < 1e-6             # calm far away
    side = two({"kind": "hesitate", "params": {"amp": 0.3}}, [line(lambda x: 40 + 0 * x)],
               [line(lambda x: 42 + 0 * x, 30.0, 170.0)])  # runs beside at 2 mm: not closing in
    dy2 = np.abs(marks(side, "B")[0].points[:, 1] - 42)
    assert dy2[(marks(side, "B")[0].points[:, 0] > 40) & (marks(side, "B")[0].points[:, 0] < 160)].max() < 0.02


def test_accompany_holds_a_constant_distance_then_lets_go():
    a = [line(lambda x: 70 + 2.0 * np.sin(x / 6.0))]
    b = [line(lambda x: 74 + 0 * x, 30.0, 170.0)]
    sh = two({"kind": "accompany", "params": {"chance": 1.0, "hold": 60.0, "hold_var": 0.0}}, a, b)
    ev = log(sh)
    assert ev and ev[0]["outcome"] == "accompany"
    (m,) = marks(sh, "B")
    gap = m.points[:, 1] - (70 + 2.0 * np.sin(m.points[:, 0] / 6.0))
    s0, s1 = ev[0]["s"]
    x = m.points[:, 0]
    held = (x > 30 + s0 + 8) & (x < 30 + s0 + 50)
    before = 74 - (70 + 2.0 * np.sin(x / 6.0))
    assert np.std(gap[held]) < 0.5 * np.std(before[held])
    assert np.abs(m.points[-1, 1] - 74) < 1e-6 or x[-1] > 30 + s1   # it lets go: its own course again at the end


def test_make_room_bows_the_past_away_and_leaves_the_present():
    a = [line(lambda x: 70 + 0 * x)]                        # earlier
    b = [line(lambda x: 71.0 + 0 * x, 80.0, 120.0)]         # later, 1 mm away, never crossing
    base = two({"kind": "cross"}, a, b)
    sh = two({"kind": "make_room"}, a, b)
    np.testing.assert_array_equal(marks(sh, "B")[0].points, marks(base, "B")[0].points)
    (ma,) = marks(sh, "A")
    mid = (ma.points[:, 0] > 95) & (ma.points[:, 0] < 105)
    assert (71.0 - ma.points[mid, 1]).min() > 1.2           # more room than the 1 mm it had
    assert np.abs(ma.points[:, 1] - 70)[ma.points[:, 0] < 60].max() < 1e-6
    assert max_turn(ma.points) < 6.0                       # a bow, not a kink


def test_make_room_never_moves_a_crossing():
    a = [line(lambda x: 70 + 0 * x)]
    b = [line(lambda x: 69.0 - (x - 100) * 0.05, 40.0, 160.0)]   # a shallow crossing at x = 80
    sh = two({"kind": "make_room"}, a, b)
    xs0 = crossings([m for m in two({"kind": "cross"}, a, b).marks if m.meta["layer"] == "B"], marks(sh, "A"))
    assert xs0 and abs(xs0[0].at[0] - 80.0) < 0.5


def test_all_five_play_together_deterministically():
    rels = [{"kind": k} for k in ("make_room", "accompany", "sympathy", "hesitate", "crossing")]
    s = score([("A", "black", [wave_line()]), ("B", "red", verticals()),
               ("C", "blue", [line(lambda x: 60 + 15 * np.cos(x / 13.0))])], rels)
    a, b = synth.run(s, cache=False), synth.run(s, cache=False)
    assert [e["outcome"] for e in log(a)] == [e["outcome"] for e in log(b)]
    assert {e["kind"] for e in log(a)} >= {"crossing", "sympathy", "hesitate", "make_room"}


# -- the listen bridge -------------------------------------------------------

def test_bridge_writes_a_v2_score_with_one_pen_per_layer():
    from experiments.aware_bridge import score as bridge  # noqa: PLC0415
    s = bridge(15102)
    v = synth.validate(s)
    assert all("lines" in L and L["renderer"]["id"] == "wire" for L in v["layers"])
    assert len({L["id"] for L in v["layers"]}) == len(v["layers"])
    void = [L["id"] for L in v["layers"] if L["role"] == "mask"]
    assert void                                              # 15102 has the void …
    assert all(void[0] not in (r["src"], r["dst"]) for r in v["relations"])   # … and it is not aware
    s0 = bridge(15103, [])
    assert s0["relations"] == []
    s1 = bridge(15103)
    assert [(r["src"], r["dst"]) for r in s1["relations"]] == [("*", "*")] * 2   # no void: wildcards


def test_no_dashes_in_a_crowd():
    """A line crossing a crowd of close lines is never cut into dashes: every piece ≥ min_dash."""
    a = [[[x, 20.0], [x, 120.0]] for x in np.arange(60.0, 100.0, 3.0)]   # a crowd 3 mm apart
    b = [line(lambda x: 70 + 0 * x)]
    sh = two(only("gap_under", jitter=0.0, min_dash=5.0), a, b)
    assert min(m.length() for m in marks(sh, "B")) >= 5.0 - 1e-6
    assert any(e["outcome"] == "gap_under" for e in log(sh))
