"""Round 12, thread oehlen_found: D1 found ground + D2 cover cuts (kit/arrangers_oehlen_found.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_oehlen_found as of  # noqa: E402
from gesture.kit import core  # noqa: E402

GRWL = HERE.parents[1] / ".local/gesture/corpus/earth/grwl-vec-SB19"


def _recipe(**arr):
    a = {"id": "oehlen_found", "found": 1, "late": 1,
         "found_boxes": [0.5, 0.4, 0.9, 0.6, -3.0], "late_box": [0.5, 0.55, 0.9, 0.7],
         "cover_boxes": [0.62, 0.45, 0.12, 0.5, 10.0, 4, 0, 0.3, 0.45, 0.35, 0.2, -5.0, 5, 1],
         "late_borrow": "all", "ride_gap": 0.9}
    a.update(arr)
    return {"frame": [205, 297], "seed": 4441, "margin": 10.0, "arranger": a,
            "parts": [{"voice": {"id": "hand", "hand": "hokusai", "length": 3.0},
                       "modulators": [{"id": "measure_next", "plate": "taxonomy", "hist": "none"}]},
                      {"voice": {"id": "hand", "hand": "dance_thrusting", "length": 2.0}}],
            "renderer": {"id": "oehlen_found_ink"}}


def test_registered_and_importable():
    core.discover()
    assert not kit.DISCOVERY_ERRORS
    assert "oehlen_found" in core.registry("arranger")
    assert "oehlen_found_river" in core.registry("voice")
    assert "oehlen_found_ink" in core.registry("renderer")


def test_run_deterministic_and_roles():
    a, b = kit.run(_recipe()), kit.run(_recipe())
    assert len(a.inks) == len(b.inks)
    for x, y in zip(a.inks, b.inks):
        assert np.array_equal(x.points, y.points) and x.meta == y.meta
    roles = {m.meta["of_role"] for m in a.marks}
    assert {"found", "late"} <= roles
    assert {i.meta["colour"] for i in a.inks} >= {"blue", "black", "green-400"}
    log = a.marks[0].meta["oehlen_found"]
    assert [c["mode"] for c in log["covers"]] == ["cut", "tint"]


def test_cut_cover_removes_found_and_late_line_crosses_uncut():
    from shapely.geometry import LineString, Polygon
    sh = kit.run(_recipe())
    log = sh.marks[0].meta["oehlen_found"]
    cut = Polygon(log["covers"][0]["polygon"]).buffer(-0.05)
    for m in sh.marks:
        if m.meta["of_role"] == "found" and len(m.points) >= 2:
            assert LineString(m.points).intersection(cut).length < 1e-6
    late = [m for m in sh.marks if m.meta["of_role"] == "late"]
    assert len(late) == 1                                  # the late line is drawn whole, never cut
    assert log["covers"][0]["late_crossing_mm"] > 0


def test_tint_reinks_inside():
    from shapely.geometry import Point, Polygon
    sh = kit.run(_recipe())
    tint = Polygon(sh.marks[0].meta["oehlen_found"]["covers"][1]["polygon"]).buffer(0.05)
    green = [m for m in sh.marks if m.meta["of_role"] == "found" and m.meta["ink"] == "green-400"]
    assert green
    for m in green:
        if m.meta.get("plate_role") == "label" or m.meta.get("measure_role") == "index":
            continue                                       # words are tinted by their centre
        assert all(tint.contains(Point(p)) for p in m.points[1:-1])


def test_split_drops_short_cut_stubs():
    sq = np.array([[10, 0], [20, 0], [20, 10], [10, 10], [10, 0]], float)
    line = np.array([[8.0, 5.0], [40.0, 5.0]])          # enters 2 mm before the cover: a 2 mm stub
    out = of._split([line], [sq], 4.0, ["cut"])
    assert len(out) == 1 and out[0][1][0][0] == pytest.approx(20.0)
    short = np.array([[11.0, 5.0], [13.0, 5.0]])         # uncut short lines are kept (only cuts make stubs)
    assert len(of._split([short + [30, 0]], [sq], 4.0, ["cut"])) == 1
    tinted = of._split([line], [sq], 1.0, ["tint"])
    assert sorted(t for _, _, t in tinted) == [False, False, True]


def test_negotiate_rides_a_parallel_contour_and_stays_contiguous():
    x = np.linspace(0, 200, 801)
    found = np.c_[x, 50 + 2.0 * np.sin(x / 3.0)]          # a wiggly found contour
    made = np.c_[x, 52.5 + 0 * x]                         # a straight made line beside it
    G = of.Ground([found], 0.4)
    pts, tags, log = of.negotiate(made, [G], np.random.default_rng(3), step=0.4, capture=6.0, align=0.5,
                                  ride=40.0, ride_sd=0.2, min_ride=10.0, listen=80.0, ignore=20.0,
                                  return_mm=20.0, ramp=2.0, grow=False, grow_reach=40.0, max_rides=3)
    assert log and (tags == 1).any()
    jumps = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    assert jumps.max() < 3.0                              # one contiguous line, bridges included
    rid = pts[tags == 1]
    assert np.std(rid[:, 1]) > 0.8                        # while riding it takes on the wiggle


def test_grow_starts_on_a_found_end():
    found = np.c_[np.linspace(0, 60, 151), np.full(151, 100.0)]
    made = np.c_[np.linspace(70, 150, 201), 100 + 10 * np.sin(np.linspace(0, 3, 201))]
    G = of.Ground([found], 0.4)
    pts, tags, log = of.negotiate(made, [G], np.random.default_rng(1), step=0.4, capture=1.0, align=0.9,
                                  ride=20.0, ride_sd=0.1, min_ride=5.0, listen=1.0, ignore=500.0,
                                  return_mm=20.0, ramp=1.0, grow=True, grow_reach=60.0, max_rides=2,
                                  bounds=(0, 0, 300, 300))
    assert log[0].get("grow")
    assert tags[0] == 1 and abs(pts[0][1] - 100.0) < 1e-6   # begins by tracing the found contour


def test_text_is_cut_whole():
    sh = kit.run(_recipe())
    from shapely.geometry import LineString, Polygon
    cut = Polygon(sh.marks[0].meta["oehlen_found"]["covers"][0]["polygon"])
    for m in sh.marks:
        if m.meta.get("plate_role") == "label" and len(m.points) >= 2:
            assert not LineString(m.points).intersects(cut)


@pytest.mark.skipif(not GRWL.exists(), reason="GRWL corpus not on this machine")
def test_found_river_is_a_far_view_band():
    sh = kit.run({"frame": [205, 297], "seed": 11, "voice": {"id": "oehlen_found_river", "span_w": 2400}})
    p = sh.marks[0].points
    lo, hi = p.min(axis=0), p.max(axis=0)
    assert (hi - lo)[0] > 3 * (hi - lo)[1]               # principal axis laid horizontal: a band
    s = of._arclen(p)[-1]
    assert s > 2.0 * (hi - lo)[0]                         # tight meanders: far longer than its span


# --- the clip cuts only where a line crosses the polygon's boundary (2026-10-18) -------------------------
# shapely's LineString ∩ / − Polygon nodes a line at its OWN crossings too: a knot wholly inside the sheet
# came back as ~100 pieces, and those under min_stub were dropped (lost ink, extra pen lifts).

def _knot(cx=150.0, cy=100.0):
    t = np.linspace(0, 12 * np.pi, 3000)
    return np.c_[cx - 70 + 20 * np.cos(t) + 4 * t, cy + 20 * np.sin(1.3 * t)]


def _box(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], float)


def _len(p):
    return float(of.arclen(np.asarray(p))[-1])


def test_clip_keeps_a_self_crossing_line_inside_whole():
    k = _knot()
    out = of.clip_rect([k], _box(0, 0, 300, 218), 4.0)
    assert len(out) == 1
    assert np.allclose(out[0], k)


def _runs(mask):
    """How many runs of True: the pieces a boundary-only cut must give (the knot's step is fine enough
    that no segment crosses an edge twice)."""
    m = np.r_[False, np.asarray(mask, bool), False].astype(int)
    return int((np.diff(m) == 1).sum())


def test_clip_cuts_only_at_the_rect_edge():
    from shapely.geometry import LineString, Polygon
    k = _knot()
    R = Polygon(_box(120, 0, 300, 218))
    out = of.clip_rect([k], _box(120, 0, 300, 218), 0.0)
    assert len(out) == _runs(k[:, 0] >= 120) == 2
    for q in out:
        assert R.buffer(1e-6).contains(LineString(q))
        for e in (q[0], q[-1]):                                       # every cut end lies on the edge
            assert abs(e[0] - 120) < 1e-9 or np.allclose(e, k[-1])
    assert sum(_len(q) for q in out) == pytest.approx(LineString(k).intersection(R).length, rel=1e-9)


def test_clip_cuts_a_long_segment_through_a_thin_rect():
    line = np.array([[0.0, 50.0], [300.0, 50.0]])                     # both ends outside, one segment
    out = of.clip_rect([line], _box(100, 0, 110, 218), 0.0)
    assert len(out) == 1 and np.allclose(out[0], [[100, 50], [110, 50]])


def test_split_cuts_only_at_the_cover_edge():
    k = _knot()
    cover = _box(0, 0, 95, 218)                                       # takes a bite out of the knot's first loop
    out = of.split_by_covers([k], [cover], 0.0, ["cut"])
    assert len(out) == _runs(k[:, 0] > 95) == 2 and not any(t for _, _, t in out)
    assert out[0][1][-1][0] == pytest.approx(95.0) and out[1][1][0][0] == pytest.approx(95.0)
    assert np.allclose(out[1][1][1:], k[k[:, 0] > 95][-(len(out[1][1]) - 1):])   # the rest is the knot, untouched
    stub = _len(out[0][1])
    assert len(of.split_by_covers([k], [cover], stub + 0.1, ["cut"])) == 1          # only the cut's stub is dropped


def test_split_tint_keeps_the_knot_under_it_as_one_tinted_piece():
    k = _knot()
    cover = _box(0, 0, 300, 218)
    out = of.split_by_covers([k], [cover], 4.0, ["tint"])
    assert len(out) == 1 and out[0][2] and np.allclose(out[0][1], k)


def test_split_conserves_length_and_classifies_by_region():
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    k = _knot()
    covers = [_box(90, 70, 140, 130), _box(160, 60, 200, 110), _box(180, 90, 230, 140)]
    modes = ["cut", "tint", "cut"]
    out = of.split_by_covers([k], covers, 0.0, modes)
    U = unary_union([Polygon(c) for c in covers])
    T = Polygon(covers[1])
    ls = LineString(k)
    assert sum(_len(q) for _, q, t in out if not t) == pytest.approx(ls.difference(U).length, rel=1e-9)
    assert sum(_len(q) for _, q, t in out if t) == pytest.approx(ls.intersection(T).length, rel=1e-9)
    # fewer pieces than shapely, which also cuts at every self-crossing
    assert len(out) < len(list(ls.difference(U).geoms)) + len(list(ls.intersection(T).geoms))


def test_clip_keeps_a_line_lying_on_the_edge_like_shapely():
    on = np.array([[120.0, 20.0], [120.0, 80.0]])                     # the polygon is closed: its edge is inside
    assert len(of.clip_rect([on], _box(120, 0, 300, 218), 0.0)) == 1
    assert of.split_by_covers([on], [_box(120, 0, 300, 218)], 0.0, ["cut"]) == []
