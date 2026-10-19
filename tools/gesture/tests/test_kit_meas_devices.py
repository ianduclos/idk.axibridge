"""Thread D (`meas`, round 15): the process-correlated devices read what is
true of the sheet (its order, its sources, its clocks, its score) and lay
it inside the region `apply_devices` gives them."""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesture import kit  # noqa: E402
from gesture.kit import devices_meas_read as R  # noqa: E402
from gesture.kit import devices_meas_stations as ST  # noqa: E402
from gesture.kit import devices_meas_turning as TU  # noqa: E402
from gesture.kit import devices_meas_air as AIR  # noqa: E402
from gesture.kit._devices import apply_devices, device_list  # noqa: E402
from gesture.kit._score import Score, score_of  # noqa: E402
from gesture.kit.core import Ink, Mark, Sheet  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
IDS = ("meas_air", "meas_arcs", "meas_inventory", "meas_ledger", "meas_roll", "meas_stations", "meas_turning")

RECIPE = {
    "frame": [200.0, 140.0], "seed": 15400, "margin": 8.0,
    "arranger": {"id": "meas_boxes", "roles": "found,line,line",
                 "boxes": [0.0, 0.35, 1.0, 0.4, 0.0, 0.0, 0.55, 0.6, 0.55, 0.0, 0.45, 0.6]},
    "parts": [
        {"voice": {"id": "river_zoom", "schedule": "push", "course": "free", "river": 0.4},
         "renderer": {"id": "meas_ink", "pen": 0.3, "ink": "blue"}},
        {"voice": {"id": "drift", "hands": ["trail_miner", "dance_staccato"], "length": 1.5}},
        {"voice": {"id": "dance", "trail": "levitation", "effectors": "hands", "seconds": 4.0},
         "renderer": {"id": "meas_ink", "pen": 0.3, "ink": "orange"}},
    ],
}


@pytest.fixture(scope="module")
def sheet():
    return kit.run(RECIPE)


def _inside(inks, region, tol=0.5):
    x0, y0, w, h = region
    p = np.vstack([k.points for k in inks])
    return (p[:, 0] >= x0 - tol).all() and (p[:, 0] <= x0 + w + tol).all() and \
        (p[:, 1] >= y0 - tol).all() and (p[:, 1] <= y0 + h + tol).all()


def test_registered_as_process():
    got = {d["id"]: d for d in device_list()}
    for i in IDS:
        assert got[i]["family"] == "process", i
    assert not kit.DISCOVERY_ERRORS


def test_score_recorded_by_test_bed(sheet):
    sc = score_of(sheet)
    assert [lay["role"] for lay in sc["layers"]] == ["found", "line", "line"]
    assert {r["kind"] for r in sc["relations"]} <= {"cross", "near"}
    assert len(sc["relations"]) == 3                       # every later layer against every earlier one
    for r in sc["relations"]:
        assert r["at"] is not None


def test_units_read_provenance(sheet):
    us = R.units(sheet, "step")
    assert len(us) == 3
    assert us[0].hands == ["grwl_far_sb19"] and us[0].family == "river" and us[0].colour == "blue"
    assert set(us[1].hands) <= {"trail_miner", "dance_staccato"} and us[1].hands
    assert us[2].family == "dance" and us[2].colour == "orange"
    lines = R.units(sheet, "line")
    assert [u.index for u in lines] == list(range(len(lines)))
    assert sum(len(u.marks) for u in lines) == len(R.drawing_marks(sheet))


def test_voice_channel_weights_are_arc_length():
    p = np.column_stack([np.linspace(0, 30, 31), np.zeros(31)])
    v = np.r_[np.zeros(10), np.ones(21)]
    m = Mark(p, {"voice": v}, {"voices": ["a", "b"]})
    w = R._voice_weights(m)
    assert w["a"] == pytest.approx(10.0) and w["b"] == pytest.approx(20.0)


@pytest.mark.parametrize("place,side,size", [("beside", "right", 70.0), ("beside", "bottom", 40.0),
                                             ("margin", "bottom", 24.0)])
@pytest.mark.parametrize("did", IDS)
def test_devices_stay_in_their_panel(sheet, did, place, side, size):
    spec = {"id": did, "place": place, "side": side, "size": size}
    if did == "meas_stations":
        spec["on_line"] = False
    out = apply_devices(sheet, [spec])
    mine = [k for k in out.inks if k.meta.get("device") == did]
    assert mine, did
    mine = [k for k in mine if k.meta.get("role") not in ("index", "station")]   # these tie the panel to the drawing
    region = out.meta["devices"][-1]["region"]
    assert _inside(mine, region, tol=1.5), (did, place, side)
    for k in mine:
        assert np.isfinite(k.points).all() and 0.05 <= k.pen <= 1.5


@pytest.mark.parametrize("did", IDS)
def test_devices_are_deterministic(sheet, did):
    a = apply_devices(sheet, [{"id": did, "place": "beside", "side": "right", "size": 70}])
    b = apply_devices(sheet, [{"id": did, "place": "beside", "side": "right", "size": 70}])
    pa = [k.points for k in a.inks if k.meta.get("device") == did]
    pb = [k.points for k in b.inks if k.meta.get("device") == did]
    assert len(pa) == len(pb) and all(np.array_equal(x, y) for x, y in zip(pa, pb))


def test_device_output_is_the_same_in_another_process(sheet, tmp_path):
    code = (
        "import sys, json, hashlib; sys.path.insert(0, 'tools/gesture');"
        "from gesture import kit; from gesture.kit._devices import apply_devices;"
        f"sh = kit.run(json.loads({json.dumps(json.dumps(RECIPE))}));"
        "out = apply_devices(sh, [{'id': 'meas_ledger', 'place': 'beside'}, {'id': 'meas_roll', 'place': 'beside', 'side': 'bottom'}]);"
        "h = hashlib.sha1(); [h.update(k.points.tobytes()) for k in out.inks if k.meta.get('layer') == 'device'];"
        "print(h.hexdigest())")
    outs = {subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                           env={"PYTHONHASHSEED": s, "PATH": ""}).stdout.strip() for s in ("1", "2")}
    assert len(outs) == 1 and len(next(iter(outs))) == 40


def test_stations_sit_where_the_clock_says(sheet):
    river = [m for m in R.drawing_marks(sheet) if "u_km" in m.channels][0]
    p, c = np.asarray(river.points), np.asarray(river.channels["u_km"])
    cr = ST.crossings(p, c, 20.0)
    assert cr
    for fi, v in cr:
        i = int(fi)
        val = c[i] + (fi - i) * (c[min(i + 1, len(c) - 1)] - c[i])
        assert val == pytest.approx(v, abs=1e-6) and v % 20.0 == pytest.approx(0.0, abs=1e-6)
    # far stretches (low zoom) put more stations per mm of paper than close ones
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    pos = np.array([np.interp(fi, np.arange(len(s)), s) for fi, _ in cr])
    zoom = np.interp(pos, s, np.asarray(river.channels["zoom"]))
    gaps = np.diff(pos)
    zmid = (zoom[1:] + zoom[:-1]) / 2
    if len(gaps) > 6:
        assert np.corrcoef(gaps, zmid)[0, 1] > 0.5


def test_stations_never_invent_a_clock():
    p = np.column_stack([np.linspace(10, 90, 50), np.full(50, 40.0)])
    sh = Sheet((100.0, 80.0), [Mark(p, {}, {"part": 0})], [Ink(p)], {"recipe": {"seed": 1, "parts": []}})
    out = apply_devices(sh, [{"id": "meas_stations", "place": "over"}])
    assert not [k for k in out.inks if k.meta.get("device") == "meas_stations"]


def test_turning_counts_whole_turns():
    t = np.linspace(0, 2 * 2 * math.pi, 800)
    circ = np.column_stack([20 + 10 * np.cos(t), 20 + 10 * np.sin(t)])
    s, tt = TU.turning(circ, step=0.5, smooth_mm=0.5)
    assert abs(tt[-1]) == pytest.approx(2.0, abs=0.05)
    line = np.column_stack([np.linspace(0, 100, 200), np.zeros(200)])
    assert abs(TU.turning(line)[1][-1]) < 1e-6


def test_air_moves_join_each_end_to_the_next_start(sheet):
    moves, segs, first = AIR.air_moves(sheet, "line", 0.0)
    us = R.units(sheet, "line")
    assert len(moves) == len(us) - 1
    for (a, b, i), u0, u1 in zip(moves, us[:-1], us[1:]):
        assert np.allclose(a, u0.marks[-1].points[-1]) and np.allclose(b, u1.marks[0].points[0])


def _synthetic_score_sheet():
    """Two lines and a score the way a round-15 composer writes it."""
    a = np.column_stack([np.linspace(10, 110, 201), 40 + 8 * np.sin(np.linspace(0, 6, 201))])
    b = np.column_stack([np.full(120, 60.0), np.linspace(5, 75, 120)])
    sc = Score()
    l0 = sc.layer("found", "river_zoom", part=0, params={"stems": "grwl_far_sb19"}, label="river")
    l1 = sc.layer("line", "hand", part=1, params={"hand": "matisse"})
    sc.relate("echo", l1, l0, at=(60.0, 40.0), s=(30.0, 70.0), note="the line answers the river")
    sc.relate("mask", l0, l1, at=(60.0, 20.0))
    sc.relate("refuse", l1, l1)
    marks = [Mark(a, {}, {"part": 0}), Mark(b, {}, {"part": 1})]
    meta = {"recipe": {"seed": 3, "parts": [{"voice": {"id": "river_zoom"}}, {"voice": {"id": "hand", "hand": "matisse"}}]},
            "library": [], "notes": {"score": sc.to_json()}}
    return Sheet((130.0, 90.0), marks, [Ink(a), Ink(b)], meta)


def test_arcs_read_the_score():
    sh = _synthetic_score_sheet()
    out = apply_devices(sh, [{"id": "meas_arcs", "place": "beside", "side": "bottom", "size": 40}])
    rel = [k for k in out.inks if k.meta.get("device") == "meas_arcs" and k.meta.get("role") == "relation"]
    assert {k.meta["kind"] for k in rel} == {"echo", "mask", "refuse"}
    only = apply_devices(sh, [{"id": "meas_arcs", "place": "beside", "kinds": "echo"}])
    assert {k.meta["kind"] for k in only.inks if k.meta.get("role") == "relation"} == {"echo"}


def test_arcs_places_hug_the_named_stretch():
    sh = _synthetic_score_sheet()
    out = apply_devices(sh, [{"id": "meas_arcs", "place": "over", "hug": 1.5, "kinds": "echo"}])
    rel = [k for k in out.inks if k.meta.get("role") == "relation"]
    hug = max(rel, key=lambda k: len(k.points))                 # the stretch, not the ring or letters
    a = sh.marks[0].points
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(a, axis=0), axis=1))]
    L = float(np.sum(np.linalg.norm(np.diff(hug.points, axis=0), axis=1)))
    assert L == pytest.approx(40.0, rel=0.15)                    # s = [30, 70] on the river
    d = np.min(np.linalg.norm(a[None, :, :] - hug.points[:, None, :], axis=2), axis=1)
    assert np.allclose(d, 1.5, atol=0.2)
    assert s[-1] > 70


def test_no_score_no_arcs():
    p = np.column_stack([np.linspace(10, 90, 50), np.full(50, 40.0)])
    sh = Sheet((100.0, 80.0), [Mark(p, {}, {"part": 0})], [Ink(p)], {"recipe": {"seed": 1, "parts": []}})
    assert R.process_score(sh) is None
    out = apply_devices(sh, [{"id": "meas_arcs", "place": "beside"}])
    assert not [k for k in out.inks if k.meta.get("device") == "meas_arcs"]


@pytest.mark.parametrize("name,arranger,kinds", [("ccolour-3-4507", "ccolour", {"carry", "spill"}),
                                                 ("cimpro-4-sheet-14007", "cimpro", {"cover", "cross", "thicken"})])
def test_round14_scores_are_derived_from_their_logs(name, arranger, kinds):
    rec = json.loads((ROOT / "tools/gesture/results" / f"{name}.recipe.json").read_text())
    sh = kit.run(rec)
    sc = R.process_score(sh)
    assert sc["derived"] == arranger
    assert kinds <= {r["kind"] for r in sc["relations"]}
    ids = {lay["id"] for lay in sc["layers"]}
    assert all(r["src"] in ids and r["dst"] in ids for r in sc["relations"])
    us = R.units(sh, "step")
    assert all(u.hands or u.family in ("chart", "machine", "edge", "container", "intruder", "hand", "dashes")
               for u in us)
    lm = R.layer_marks(sh, sc)
    assert sum(len(v) for v in lm.values()) == len(R.drawing_marks(sh))
