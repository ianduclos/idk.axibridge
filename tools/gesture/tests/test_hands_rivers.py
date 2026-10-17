"""Round 11 hands_rivers: river hands in the library, the river_loops and
river_braid voices (kit/voices_rivers.py)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit import voices_rivers as vr  # noqa: E402

HANDS = ("river_bend", "river_meander", "river_belt", "river_oxbow", "river_threads")
TILE = [130, 100]


def test_discovery_clean():
    kit.discover()
    assert "voices_rivers" not in " ".join(kit.DISCOVERY_ERRORS)
    ids = [m["id"] for m in kit.describe()["voice"]]
    assert "river_loops" in ids and "river_braid" in ids


@pytest.mark.parametrize("h", HANDS)
def test_hand_entries_load_and_draw(h):
    e = L.entry("hand", h)
    assert e["policy"] == "generative"
    pv = e["provenance"]
    assert pv["corpus"] == "earth" and pv["corpus_ids"] and pv["training_sheets"] and pv["extraction"]
    if h in ("river_bend", "river_meander", "river_belt"):
        assert pv["zoom_w"] in (60, 150, 400)
    g = L.load("hand", h)
    assert len(g.strokes) > 10
    sh = kit.run({"seed": 7000, "frame": TILE, "voice": {"id": "hand", "hand": h, "length": 2.0}})
    assert len(sh.marks) == 1 and len(sh.marks[0].points) > 50


def test_aux_entries():
    lo = L.load("river_loops", "river_cutoffs")
    assert lo["oxbow_phi"].shape[1] == vr.N_PROFILE and len(lo["oxbow_phi"]) > 100
    assert len(lo["neck_phi"]) > 100
    br = L.load("river_braid", "river_anavilhanas")
    assert br["profile"].shape[1] == 32 and len(br["aspect"]) >= 5 and np.all(br["aspect"] >= 1.5)


def test_loop_profile_roundtrip_closes():
    t = np.linspace(0, 2 * np.pi, 200, endpoint=False)
    ell = np.column_stack([3 * np.cos(t), np.sin(t)])
    phi, asp = vr.loop_profile(ell, True)
    assert 2.0 < asp < 3.0          # second-moment ratio of the outline (arc-length weighted), not the axis ratio
    p = vr.integrate(phi + 2 * np.pi * np.arange(len(phi)) / len(phi), 1.0, close=True)
    assert np.linalg.norm(p[-1] - p[0]) < 1e-9


def test_loops_alone_closed_and_deterministic():
    r = {"seed": 7000, "frame": TILE, "voice": {"id": "river_loops", "mode": "alone", "family": "oxbow", "n": 8}}
    a, b = kit.run(r), kit.run(r)
    assert len(a.marks) == 8
    for m in a.marks:
        L_ = m.length()
        assert np.linalg.norm(m.points[-1] - m.points[0]) < 1e-6 * max(L_, 1.0)
    for x, y in zip(a.marks, b.marks):
        assert np.array_equal(x.points, y.points)


def test_loops_knot_is_one_line_with_loops():
    sh = kit.run({"seed": 7001, "frame": TILE, "voice": {"id": "river_loops", "mode": "knot", "n": 4,
                                                          "loop_r": 1.0}})
    assert len(sh.marks) == 1
    m = sh.marks[0]
    assert m["loop"].max() == 1.0 and m["loop"].min() == 0.0
    assert 0.0 < float(m["r"].max()) <= 1.0


def test_braid_threads_touch_and_split():
    sh = kit.run({"seed": 7000, "frame": TILE, "voice": {"id": "river_braid", "threads": 3}})
    ms = sh.marks
    assert len(ms) == 3 and all(len(m) == len(ms[0]) for m in ms)
    d = np.linalg.norm(ms[0].points - ms[1].points, axis=1)
    assert d.min() < 1e-6 and d.max() > 1.0          # they touch at nodes and open into islands
    assert any(m["emphasis"].max() > 0.5 for m in ms)   # splits marked for bead renderers


def test_cross_process_determinism():
    code = ("import sys; sys.path.insert(0, %r); from gesture import kit; import hashlib, numpy as np; "
            "s = kit.run({'seed': 7002, 'frame': [130, 100], 'parts': ["
            "{'voice': {'id': 'river_braid', 'threads': 4}}, "
            "{'voice': {'id': 'river_loops', 'mode': 'beside', 'n': 3}}]}); "
            "print(hashlib.sha1(b''.join(np.ascontiguousarray(m.points).tobytes() for m in s.marks)).hexdigest())"
            % str(HERE))
    outs = set()
    for seed in ("0", "123"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outs.add(subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                                check=True).stdout.strip().splitlines()[-1])
    assert len(outs) == 1


def test_read_xlsx_cutoffs():
    sys.path.insert(0, str(HERE))
    from experiments import hands_rivers as hr
    p = hr.EARTH / "li-amazon-cutoffs/cutoff_data_Amazon_upload.xlsx"
    if not p.exists():
        pytest.skip("corpus not on this machine")
    cb = hr.cutoff_bends()
    assert len(cb) > 500 and {"Neck", "Chute"} <= {c["type"] for c in cb}


def test_measure_report_written_if_present():
    p = HERE.parents[1] / ".local/gesture/out/hands_rivers/measure.json"
    if not p.exists():
        pytest.skip("measure stage not run here")
    rep = json.loads(p.read_text())
    assert set(HANDS) <= set(rep["hands"]) and set(HANDS) <= set(rep["split_half"])
