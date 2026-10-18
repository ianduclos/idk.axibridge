"""Round 13, thread I-b `mutual`: regimes aware of one another, in interleaved turns."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit import voices_mutual as vm  # noqa: E402

ROOT = HERE.parents[1]
FDSN_OK = (vm.FDSN / "fdsn-tohoku2011-IU.ANMO").exists()
pytestmark = pytest.mark.skipif(not FDSN_OK, reason="needs the local FDSN corpus (graph regime)")

PIECE = {"seed": 1313, "frame": [300.0, 200.0], "margin": 10.0, "arranger": {"id": "single"},
         "renderer": {"id": "oehlen_found_ink"},
         "voice": {"id": "mutual", "river_scale": 1.6, "river_speed": 2.0, "river_rush": 2.4, "wrap_r": 16.0,
                   "invite": 2.0, "blank": [0.85, 0.58, 0.22], "appetite_gain": 0.004, "refuse_below": 0.45}}


@lru_cache(maxsize=4)
def _run(key: str):
    return kit.run(json.loads(key))


def run(r):
    return _run(json.dumps(r, sort_keys=True))


def meta(sh):
    return sh.marks[0].meta["mutual"]


def test_registered_and_channels():
    assert "mutual" in kit.registry("voice")
    sh = run({**PIECE, "voice": {**PIECE["voice"], "T": 40}})
    roles = {m.meta["of_role"] for m in sh.marks}
    assert {"graph", "river", "bold", "wire"} <= roles
    for m in sh.marks:
        assert "tick" in m.channels and "neg" in m.channels
        assert np.all(np.diff(m["tick"]) >= 0)          # drawn in turn order along every line


def test_valley_frame_is_exact_on_its_own_axis():
    fz = L.load("river_stems", "grwl_far_sb19")
    _, _, q = fz["stems"][("SB19", 0)]
    qm = np.asarray(q, float) * 1.6 / 1000.0
    vf = vm.valley_frame(qm, 9.0)
    assert np.all(np.diff(vf["s"]) >= 0)                # s never jumps back (no torn meander)
    # rebuild on the stem's own axis: the stem comes back
    qq = vm.resample(qm, 0.2)
    from scipy.ndimage import gaussian_filter1d
    a = vm.resample(gaussian_filter1d(qq, 9.0 / 0.2, axis=0, mode="nearest"), 0.25)
    sa = vm.arcl(a)
    t = vm.tangents(a, 2)
    tx, ty = np.interp(vf["s"], sa, t[:, 0]), np.interp(vf["s"], sa, t[:, 1])
    nrm = np.hypot(tx, ty)
    tx, ty = tx / nrm, ty / nrm
    ax = np.column_stack([np.interp(vf["s"], sa, a[:, 0]), np.interp(vf["s"], sa, a[:, 1])])
    back = ax + np.column_stack([tx, ty]) * vf["u"][:, None] + np.column_stack([-ty, tx]) * vf["n"][:, None]
    assert np.max(np.linalg.norm(back - qq, axis=1)) < 1e-6


def test_river_has_no_stray_chords():
    sh = run(PIECE)
    for m in sh.marks:
        if m.meta["of_role"] == "river":
            assert np.max(np.linalg.norm(np.diff(m.points, axis=0), axis=1)) < 1.0


def test_call_and_response_both_ways():
    """The judging test, as events: a bold stop the river answered (it wrapped the knot), and a river
    arrival that bold answered (it rode the river from its knot)."""
    ev = meta(run(PIECE))["events"]
    stops = [e for e in ev if e["src"] == "bold" and e["kind"] == "stop"]
    assert any(any(a["by"] == "river" and "wrapped" in a["how"] for a in e["answers"]) for e in stops)
    arrives = [e for e in ev if e["src"] == "river" and e["kind"] == "arrive"]
    assert any(any(a["by"] == "bold" and "rides the river" in a["how"] for a in e["answers"]) for e in arrives)
    # and a refusal: the tired bold turns its back on the second call
    assert any(any(a["by"] == "bold" and "refuses" in a["how"] for a in e["answers"]) for e in arrives)


def test_events_are_few():
    ev = meta(run(PIECE))["events"]
    assert len(ev) <= 20                                # discrete and few, never a field


def test_bold_rides_beside_the_river():
    sh = run(PIECE)
    river = np.vstack([m.points for m in sh.marks if m.meta["of_role"] == "river"])
    from scipy.spatial import cKDTree
    tr = cKDTree(river)
    for m in sh.marks:
        if m.meta["of_role"] == "bold" and np.any(m["neg"] > 0):
            d = tr.query(m.points[m["neg"] > 0])[0]
            assert np.median(d) < 1.5                   # 0.9 mm beside it, visible, not on it
            return
    pytest.fail("no ride")


def test_graph_lifts_while_ridden():
    sh = run(PIECE)
    m = meta(sh)
    rides = [e for e in m["events"] if e["src"] == "wire" and e["kind"] == "ride"]
    assert rides and all(any(a["by"] == "graph" and "lifts" in a["how"] for a in e["answers"]) for e in rides)
    pieces = [mk for mk in sh.marks if mk.meta["of_role"] == "graph"]
    assert len(pieces) == len(rides) + 1                # one gap per ride


def test_upto_is_a_prefix_of_the_same_run():
    full = run(PIECE)
    part = run({**PIECE, "voice": {**PIECE["voice"], "upto": 60}})
    b_full = np.vstack([m.points[m["tick"] < 60] for m in full.marks if m.meta["of_role"] == "bold"])
    b_part = np.vstack([m.points for m in part.marks if m.meta["of_role"] == "bold"])
    assert np.allclose(b_full, b_part)


def test_deterministic_across_processes():
    code = (
        "import sys, json, hashlib; sys.path.insert(0, 'tools/gesture');"
        "from gesture import kit; import numpy as np;"
        f"r = json.loads({json.dumps(json.dumps({**PIECE, 'voice': {**PIECE['voice'], 'T': 70}}))});"
        "sh = kit.run(r); h = hashlib.sha256();"
        "[h.update(np.round(i.points, 6).tobytes()) for i in sh.inks]; print(h.hexdigest())"
    )
    outs = set()
    for seed in ("1", "77"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                             timeout=600)
        assert out.returncode == 0, out.stderr[-2000:]
        outs.add(out.stdout.strip().splitlines()[-1])
    assert len(outs) == 1
