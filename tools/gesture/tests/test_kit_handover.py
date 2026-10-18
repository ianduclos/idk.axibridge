"""morph_handover (round 13, thread `handover`): hand A becomes hand B one feature at a time."""
import os
import subprocess
import sys

import numpy as np
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "gesture"))

from gesture import kit  # noqa: E402
from gesture.kit import voices_handover as vh  # noqa: E402

SMALL = {"frame": [120, 60], "seed": 1311, "margin": 4,
         "voice": {"id": "morph_handover", "hands": ["meander69", "fly_open"], "order": "bend,turn,corner",
                   "rows": 2, "R_mm": 40, "band": 10, "K": 4, "windows": [0.2, 0.3, 0.45, 0.55, 0.7, 0.8]}}


def _run(**over):
    rec = {**SMALL, "voice": {**SMALL["voice"], **over}}
    return kit.run(rec)


def test_registered_and_imports_cleanly():
    assert not kit.DISCOVERY_ERRORS
    assert "morph_handover" in [d["id"] for d in kit.describe()["voice"]]


def test_compose_takes_each_feature_whole():
    a = {"corner": 1.5, "kind": "line", "l": 0.05, "k0": 0.0, "k1": 0.0, "sgn": -1.0}
    b = {"corner": None, "kind": "arc", "l": 0.02, "k0": 30.0, "k1": 30.0, "sgn": 1.0}
    for src in [dict(zip(vh.FEATURES, bits)) for bits in np.ndindex(2, 2, 2, 2)]:
        s = vh.compose(a, b, src)
        assert s["l"] == (b if src["length"] else a)["l"]                  # tempo from one hand
        assert s["kind"] == (b if src["bend"] else a)["kind"]              # bend shape from one hand
        turn_src = (b if src["bend"] else a)
        assert abs(0.5 * (s["k0"] + s["k1"]) * s["l"]) == pytest.approx(
            abs(0.5 * (turn_src["k0"] + turn_src["k1"]) * turn_src["l"]))   # turning angle kept, not averaged
        cs = (b if src["corner"] else a)["corner"]
        assert (s["corner"] is None) == (cs is None)
        if cs is not None:
            assert abs(s["corner"]) == pytest.approx(abs(cs))
            assert np.sign(s["corner"]) == (b if src["turn"] else a)["sgn"]  # handedness from the turn hand


def test_schedule_before_and_after_windows():
    assert vh.share_b(0.1, 0.2, 0.3, 1.5) == 0.0 and vh.share_b(0.31, 0.2, 0.3, 1.5) == 1.0
    rng = np.random.default_rng(0)
    assert all(vh.step_switch(0, 0.0, 3.0, rng) == 0 for _ in range(50))
    assert all(vh.step_switch(0, 1.0, 3.0, rng) == 1 for _ in range(50))


def test_line_starts_as_a_and_ends_as_b():
    m = _run().marks[0]
    u = m["handover_u"]
    for f in ("bend", "turn", "corner"):
        assert np.all(m[f"src_{f}"][u < 0.19] == 0)
        assert np.all(m[f"src_{f}"][u > 0.81] == 1)
    assert m["src_length"][u > 0.81].min() == 1                       # unlisted: goes with the last listed
    assert m["stage"].max() == 4 and m["stage"].min() == 0


def test_line_stays_in_frame_and_reaches_the_end():
    sh = _run()
    p = sh.marks[0].points
    W, H = sh.frame
    assert p[:, 0].min() > 0 and p[:, 1].min() > 0 and p[:, 0].max() < W and p[:, 1].max() < H
    assert sh.marks[0]["handover_u"][-1] > 0.85


@pytest.mark.parametrize("mode", ["tokens", "average"])
def test_controls_run(mode):
    m = _run(mode=mode).marks[0]
    assert len(m.points) > 100 and m.meta["handover"]["mode"] == mode


def test_bad_order_refused():
    with pytest.raises(Exception):
        _run(order="bend,bend")
    with pytest.raises(Exception):
        _run(order="bend,wobble")


def test_deterministic_across_processes():
    code = ("import sys,json; sys.path.insert(0,'tools/gesture'); from gesture import kit; "
            f"import hashlib; sh=kit.run(json.loads({__import__('json').dumps(__import__('json').dumps(SMALL))})); "
            "print(hashlib.sha1(sh.marks[0].points.tobytes()).hexdigest())")
    outs = set()
    for hs in ("0", "123"):
        env = {**os.environ, "PYTHONHASHSEED": hs}
        outs.add(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=ROOT,
                                check=True).stdout.strip())
    assert len(outs) == 1
