"""lcorp (round 15, thread B): the zoom on any line, the lens, applied style,
aware overlaps, relays."""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit import modulators_lcorp as M  # noqa: E402
from gesture.kit import voices_lcorp as V  # noqa: E402
from gesture.kit.core import Mark  # noqa: E402
from gesture.kit.voices_rzoom import zoom_shape  # noqa: E402


def _turning(p):
    d = np.diff(p, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    return th, np.r_[0, np.cumsum(np.linalg.norm(d, axis=1))]


@pytest.fixture(scope="module")
def chain():
    return V.hand_chain(L.load("hand", "hokusai"), np.random.default_rng(5), length_R=20)[0]


def test_constant_zoom_is_pure_magnification():
    s = np.linspace(0, 400, 8000)
    src = V.integrate(np.sin(s / 7) + 0.6 * np.sin(s / 23 + 1), s[1] - s[0])
    g = np.zeros(400)
    r = V.zoom_line(src, g, zoom=8.0, far_turn_mm=2.0, lod=0.0, valley=0.0)
    th_o, _ = _turning(r["points"])
    rr, th_s, h = V.profile(src, r["turn_len"] / 24)
    # the drawn heading at each point is the source's heading where it stands on the source
    um = 0.5 * (r["u"][1:] + r["u"][:-1])
    b = np.interp(um, (np.arange(len(th_s)) + 0.5) * h, th_s)
    d = (th_o - b) - np.mean(th_o - b)                    # up to the free course's rotation
    assert np.max(np.abs(d)) < 0.15


def test_paper_speed_follows_zoom(chain):
    g = zoom_shape("push", 4000, np.random.default_rng(1), 2)
    r = V.zoom_line(chain, g, zoom=12.0, far_turn_mm=2.0, lod=0.8, reveal=0.4, valley=4.0)
    p, z, u = r["points"], r["zoom"], r["u"]
    ds = np.linalg.norm(np.diff(p, axis=0), axis=1)
    du = np.diff(u)
    zm = 0.5 * (z[1:] + z[:-1])
    m = du > 0
    ratio = ds[m] / (r["c_mm_per_unit"] * zm[m] * du[m])
    assert abs(np.median(ratio) - 1.0) < 0.05          # ds = c·z·du (straightening keeps arc length)
    assert z.max() > 11.0 and z.min() < 1.05


def test_level_of_detail_hides_and_reveals(chain):
    g = np.zeros(400)
    raw = V.zoom_line(chain, g, zoom=1.0, far_turn_mm=2.0, lod=0.0)
    lod = V.zoom_line(chain, g, zoom=1.0, far_turn_mm=2.0, lod=0.8)
    tr = np.abs(np.diff(_turning(raw["points"])[0])).sum() / raw["length_mm"]
    tl = np.abs(np.diff(_turning(lod["points"])[0])).sum() / lod["length_mm"]
    assert tl < tr                                      # the far view is band-limited


@pytest.mark.parametrize("src", [
    {"source": "hand", "hand": "matisse"},
    {"source": "relay", "hands": ["matisse", "lichtenberg"], "schedule": "pinch"},
    {"source": "dance", "trail": "mantis"},
    {"source": "river"},
])
def test_voice_is_one_contiguous_line_in_the_box(src):
    sh = kit.run({"frame": [300, 100], "seed": 11, "margin": 6, "voice": {"id": "lcorp_zoom", **src},
                  "renderer": {"id": "lcorp_ink", "by": "voice"}})
    assert len(sh.marks) == 1
    p = sh.marks[0].points
    assert np.max(np.linalg.norm(np.diff(p, axis=0), axis=1)) < 3.0
    assert p[:, 0].min() >= 5.9 and p[:, 0].max() <= 294.1 and p[:, 1].min() >= 5.9 and p[:, 1].max() <= 94.1
    assert len({round(i.pen, 6) for i in sh.inks}) == 1          # constant width
    for a, b in zip(sh.inks[:-1], sh.inks[1:]):                     # colour runs share their end points
        assert np.allclose(a.points[-1], b.points[0])


def test_relay_hands_over_in_the_far_twists():
    sh = kit.run({"frame": [600, 150], "seed": 3001, "margin": 8,
                  "voice": {"id": "lcorp_zoom", "source": "relay", "hands": ["matisse", "lichtenberg", "trail_slime"],
                            "schedule": "pinch", "zoom": 24},
                  "renderer": {"id": "lcorp_ink", "by": "voice"}})
    m = sh.marks[0]
    v, z = m["voice"], m["zoom"]
    cuts = np.flatnonzero(np.diff(v) != 0)
    assert len(cuts) == 2 and sorted(set(v.astype(int))) == [0, 1, 2]
    assert all(z[i] < math.sqrt(24) for i in cuts)
    sc = sh.meta["notes"]["score"]
    assert [r["kind"] for r in sc["relations"]] == ["handover", "handover"]


def test_measures_separate_flat_from_open():
    def meas(hand):
        sh = kit.run({"frame": [480, 120], "seed": 1491, "margin": 6,
                      "voice": {"id": "lcorp_zoom", "source": "hand", "hand": hand}})
        return sh.marks[0].meta["measure"]
    flat, opened = meas("river_bend"), meas("dancer_cristel")
    assert opened["contrast"] > flat["contrast"] and flat["inner"] > 0.5 > opened["inner"]


def test_restyle_keeps_each_band_whole():
    rng = np.random.default_rng(0)
    th_c = np.cumsum(rng.normal(0, 0.05, 4000))
    th_s = np.cumsum(rng.normal(0, 0.3, 4000))
    out = V.restyle_theta(th_c, th_s, h=0.2, split=10.0, amount=0.0)
    from scipy.ndimage import gaussian_filter1d
    assert np.allclose(out, gaussian_filter1d(th_c, 50.0, mode="nearest"))


def test_apply_style_pins_the_course_ends():
    x = np.linspace(0, 200, 800)
    course = np.column_stack([x, 20 * np.sin(x / 30)])
    q = V.hand_chain(L.load("hand", "lichtenberg"), np.random.default_rng(2), length_R=60)[0]
    p = M.apply_style(course, q, split_mm=12, style_turn_mm=2.0)
    assert np.allclose(p[0], course[0], atol=0.3) and np.allclose(p[-1], course[-1], atol=0.3)
    assert np.std(p[:, 1] - np.interp(p[:, 0], course[:, 0], course[:, 1])) > 0.2   # the bends arrived


def _line(a, b, z, n=400):
    t = np.linspace(0, 1, n)[:, None]
    p = np.asarray(a) * (1 - t) + np.asarray(b) * t
    return Mark(p, {"zoom": np.full(n, float(z))}, {})


def test_depth_cuts_only_the_farther_pass():
    near = _line((0, 50), (100, 50), 20.0)
    far = _line((50, 0), (50, 100), 1.0)
    out, log = M.aware_marks([near, far], mode="depth", gap=1.0)
    assert len(out) == 3                              # near whole, far in two
    assert np.allclose(out[0].points[0], near.points[0]) and out[0].length() == pytest.approx(100, abs=0.5)
    gaps = [m for m in out[1:]]
    assert all(np.min(np.abs(m.points[:, 1] - 50)) >= 0.9 for m in gaps)
    assert log and log[0]["kind"] == "mask"
    same, _ = M.aware_marks([_line((0, 50), (100, 50), 1.0), far], mode="depth")
    assert len(same) == 2                             # equal zoom: they simply cross


def test_sympathy_moves_only_the_near_pass_near_the_far_one():
    x = np.linspace(0, 100, 800)
    far = Mark(np.column_stack([x, 50 + 0.8 * np.sin(x * 2.0)]), {"zoom": np.ones(800)}, {})
    near = _line((0, 52), (100, 52), 10.0, n=800)
    away = _line((0, 90), (100, 90), 10.0, n=800)
    out, _ = M.aware_marks([near, far, away], mode="sympathy", reach=5.0)
    assert np.allclose(out[1].points, far.resampled(0.25).points)
    assert np.std(out[0].points[:, 1]) > 0.1
    assert np.allclose(out[2].points[:, 1], 90)


LENS = {"frame": [267, 180], "seed": 2201, "margin": 10,
        "arranger": {"id": "lcorp_lens", "field": "lens", "far_turn_mm": 0.8, "zoom": 24, "lod": 0.6,
                     "aware": "depth"},
        "parts": [{"voice": {"id": "lcorp_zoom", "source": "hand", "hand": h}} for h in ("hokusai", "matisse",
                                                                                         "trail_slime")],
        "renderer": {"id": "lcorp_ink"}}


def test_lens_records_a_truthful_score_and_never_clips():
    sh = kit.run(LENS)
    sc = sh.meta["notes"]["score"]
    roles = [lay["role"] for lay in sc["layers"]]
    assert roles.count("field") == 1 and roles.count("line") == 3
    ids = {lay["id"] for lay in sc["layers"]}
    assert all(r["src"] in ids and r["dst"] in ids for r in sc["relations"])
    assert any(r["kind"] == "exaggerate" for r in sc["relations"])
    allp = np.vstack([m.points for m in sh.marks])
    assert allp[:, 0].min() > 10 and allp[:, 0].max() < 257 and allp[:, 1].min() > 10 and allp[:, 1].max() < 170
    assert max(m["zoom"].max() for m in sh.marks) > 10


def test_zoom_modulator_wraps_any_voice():
    sh = kit.run({"frame": [200, 100], "seed": 7, "voice": {"id": "hand", "hand": "lichtenberg"},
                  "modulators": [{"id": "lcorp_zoom_mod", "zoom": 8}]})
    m = sh.marks[0]
    assert "zoom" in m.channels and m["zoom"].max() > 7 and "voice" in m.channels


def test_deterministic_across_processes():
    code = ("import sys,json,hashlib; sys.path.insert(0, %r); from gesture import kit; "
            "r=json.loads(sys.argv[1]); sh=kit.run(r); "
            "print(hashlib.sha1(b''.join(m.points.tobytes() for m in sh.marks)).hexdigest())") % str(ROOT)
    rec = json.dumps(LENS | {"parts": LENS["parts"][:2]})
    outs = {subprocess.run([sys.executable, "-c", code, rec], capture_output=True, text=True, check=True,
                           env={"PYTHONHASHSEED": str(s), "PATH": "/usr/bin:/bin"}).stdout for s in (1, 2)}
    assert len(outs) == 1


def test_tie_z_cuts_opened_equal_zoom_crossings_later_in_front():
    a = _line((0, 50), (100, 50), 10.0)
    b = _line((50, 0), (50, 100), 10.0)
    out, _ = M.aware_marks([a, b], mode="depth", tie_z=3.0)
    assert len(out) == 3 and out[-1].length() == pytest.approx(100, abs=0.5)   # b (later) whole, a cut
    low, _ = M.aware_marks([_line((0, 50), (100, 50), 2.0), _line((50, 0), (50, 100), 2.0)], mode="depth",
                           tie_z=3.0)
    assert len(low) == 2
