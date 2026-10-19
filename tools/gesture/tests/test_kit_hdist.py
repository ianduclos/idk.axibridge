"""hdist (round 16, thread B): distinct hands under the zoom: each hand's own
scale ladder, the R calibration, the pen camera, the relay, the measures."""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit import voices_hdist as H  # noqa: E402
from gesture.kit import voices_lcorp as V  # noqa: E402

CELL = (480, 120)


def rec(hand, seed=1491, **over):
    return {"frame": list(CELL), "seed": seed, "margin": 6, "voice": {"id": "hdist_zoom", "hand": hand, **over},
            "renderer": {"id": "lcorp_ink", "pen": 0.45}}


def _turn_in_window(p, mm):
    """Largest |turning| inside any `mm` of arc (rad)."""
    r = V.resample(p, 0.1)
    d = np.diff(r, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    w = max(int(mm / 0.1), 1)
    return float(np.max(np.abs(th[w:] - th[:-w])))


@pytest.fixture(scope="module")
def chains():
    out = {}
    for h in ("mime_penguin", "river_bend", "polygon_walk"):
        out[h] = V.hand_chain(L.load("hand", h), np.random.default_rng(3), length_R=40)[0]
    return out


def test_ladder_reads_where_turning_lives():
    s = np.arange(0, 4000.0, 0.5)
    smooth = np.cumsum(np.full(len(s), 0.5 * (math.pi / 2) / 60))       # one bend size: a steady curve
    fine = smooth + 0.6 * np.sin(s / 1.5)                               # plus fine wiggle
    for th in (smooth, fine):
        lt = V.turn_length(th, 0.5)
        lad = H.ladder(th, 0.5, lt)
        assert lad["k_fine"] <= lad["k_coarse"]
    l_s = H.ladder(smooth, 0.5, V.turn_length(smooth, 0.5))
    l_f = H.ladder(fine, 0.5, V.turn_length(fine, 0.5))
    assert l_f["k_fine"] < l_s["k_fine"]                 # the wiggle puts the finest band lower
    assert H._cross(np.array([0.0, 1.0, 2.0]), np.array([1.0, 0.5, 0.0]), 0.75) == pytest.approx(0.5)


def test_R_calibration_keeps_curliness(chains):
    """calib R: one reference length = R_mm, so the far quarter-turn scales with the hand's own ℓ_turn:
    a curly hand turns many times in it, a sweeping one barely (v1 made them equal)."""
    g = np.zeros(400)
    kw = dict(fine_mm=0.8, top_mm=50, far_min_mm=2.2, far_max_mm=8, zoom_max=24, zoom=1.0, far_turn_mm=0.0,
              res_mm=0.45, reveal=1.0, valley=0.0, pace=0.5, drawn_mm=600.0, calib="R", R_mm=80.0)
    far = {}
    for h, q in chains.items():
        r = H.hand_zoom(q, g, **kw)
        far[h] = r["hdist"]["far_turn_mm"]
        assert far[h] == pytest.approx(80.0 * r["turn_len"] / V.UNIT, rel=1e-3)
    assert far["river_bend"] > 5 * far["mime_penguin"]


def test_zoom_stops_where_the_hand_runs_out_of_detail(chains):
    g = H.zoom_shape("push", 4000, np.random.default_rng(1), 2)
    r = H.hand_zoom(chains["mime_penguin"], g, fine_mm=0.8, top_mm=50, far_min_mm=2.2, far_max_mm=8, zoom_max=24,
                    zoom=0.0, far_turn_mm=0.0, res_mm=0.45, reveal=1.0, valley=1.0, pace=0.5, drawn_mm=800.0,
                    calib="R", R_mm=80.0, peak_fine_mm=4.0)
    hd = r["hdist"]
    finest = hd["far_turn_mm"] * 2.0 ** hd["k_fine"]
    assert 1.0 < hd["zoom"] < 24.0
    assert hd["zoom"] * finest == pytest.approx(4.0, rel=1e-3)
    assert float(np.max(r["zoom"])) == pytest.approx(hd["zoom"], rel=0.02)


def test_pen_camera_keeps_corners_that_lcorp_rounded():
    """A zigzag (corners every 20 units) zoomed ×8: the pen camera keeps a corner a corner; lcorp's
    camera (res 1.76 mm, reveal 0.4) turned it into an arc."""
    seg = np.array([[0, 0], [20, 12], [40, 0]], float)
    q = np.vstack([seg + [40 * i, 0] for i in range(60)])
    q = V.resample(q, 0.25)
    g = np.ones(400)
    _, th, h = V.profile(q, 0.5)
    lt = V.turn_length(th, h)
    c = 6.0 / lt
    ours = V.magnify_lod(V.resample(q, lt / 32), g, zoom=8.0, c=c, res_mm=0.45, reveal=1.0, max_mm=1500.0)
    v1 = V.magnify_lod(V.resample(q, lt / 32), g, zoom=8.0, c=c, res_mm=1.76, reveal=0.4, max_mm=1500.0)
    assert _turn_in_window(ours["points"], 3.0) > math.radians(55)
    assert _turn_in_window(v1["points"], 3.0) < _turn_in_window(ours["points"], 3.0) * 0.8


def test_voice_one_line_in_the_box_constant_width():
    sh = kit.run(rec("polygon_walk"))
    assert len(sh.marks) == 1 and len(sh.inks) == 1
    p = sh.marks[0].points
    x0, y0 = 6, 6
    assert p[:, 0].min() >= x0 - 1e-6 and p[:, 0].max() <= CELL[0] - 6 + 1e-6
    assert p[:, 1].min() >= y0 - 1e-6 and p[:, 1].max() <= CELL[1] - 6 + 1e-6
    assert np.all(np.linalg.norm(np.diff(p, axis=0), axis=1) < 2.0)       # contiguous
    assert sh.inks[0].pen == pytest.approx(0.45)
    hd = sh.marks[0].meta["hdist"]
    assert hd["calib"] == "R" and abs(hd["fit"] - 1.0) < 0.25           # the far scale is the sheet's scale


def test_hands_part_where_v1_kept_them_together():
    """The far quarter-turn on the sheet differs by hand (v1: the same 2.2 mm × fit for all)."""
    fars = [kit.run(rec(h)).marks[0].meta["hdist"]["far_on_sheet_mm"] for h in
            ("mime_penguin", "river_bend", "trail_borer", "shikasta")]
    assert max(fars) / min(fars) > 4


def test_relay_each_hand_whole_handovers_far():
    r = {"frame": [600, 150], "seed": 3001, "margin": 8,
         "voice": {"id": "hdist_zoom", "source": "relay", "hands": ["river_bend", "shikasta", "trail_borer"],
                   "drawn_mm": 1200},
         "renderer": {"id": "lcorp_ink", "by": "voice", "inks": "black,blue,red"}}
    m = kit.run(r).marks[0]
    v, z = m.channels["voice"], m.channels["zoom"]
    assert list(np.unique(v)) == [0.0, 1.0, 2.0]
    assert np.all(np.diff(v) >= 0)                                      # in order, each once
    for i in np.flatnonzero(np.diff(v) != 0):
        assert z[i] < 1.5 and z[i + 1] < 1.5                            # where both are far
    rel = m.meta["hdist"]["relay"]
    assert len({round(x["far_turn_mm"], 3) for x in rel}) == 3         # each at its own scale


def test_eye_features_read_the_obvious():
    import hdist_measure as HM
    t = np.linspace(0, 1, 2000)
    straight = np.column_stack([t * 300, np.zeros_like(t)])
    zig = np.vstack([[[10 * i, 0], [10 * i + 5, 8]] for i in range(30)]).astype(float)
    loops = np.column_stack([t * 300 + 3 * np.cos(t * 2 * np.pi * 30), 3 * np.sin(t * 2 * np.pi * 30)])  # < 25 mm each
    es, ez, el = (HM.eye_features(V.resample(x, 0.1)) for x in (straight, zig, loops))
    assert es["straight_share"] > 0.95 and es["loops_per_m"] == 0
    assert ez["corner_share"] > 0.5 > es["corner_share"]
    assert el["loops_per_m"] > 20


def test_score_with_hands_as_layers_runs_and_logs():
    from gesture.kit import _synth as synth
    import hdist_review as HR
    sc = HR.score6(16201)
    sc["layers"] = sc["layers"][:2]
    sh = synth.run(sc, cache=False)
    played = synth.played(sh)
    assert {m.meta["score_layer"] for m in sh.marks} == {"L0", "L1"}
    assert played is not None and "log" in played


def test_deterministic_across_processes():
    code = ("import sys,json,hashlib; sys.path.insert(0, %r); from gesture import kit; "
            "r=json.loads(sys.argv[1]); sh=kit.run(r); "
            "print(hashlib.sha1(b''.join(m.points.tobytes() for m in sh.marks)).hexdigest())") % str(ROOT)
    r = json.dumps(rec("hokusai", seed=77))
    outs = {subprocess.run([sys.executable, "-c", code, r], capture_output=True, text=True, check=True,
                           env={"PYTHONHASHSEED": str(s), "PATH": "/usr/bin:/bin"}).stdout for s in (1, 2)}
    assert len(outs) == 1
