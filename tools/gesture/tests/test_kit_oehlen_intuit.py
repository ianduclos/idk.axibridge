"""oehlen_intuit: the replay voice of the session's finished sheet."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))

from gesture import kit  # noqa: E402

RECIPE = {"frame": [200, 300], "seed": 4127, "margin": 0,
          "voice": {"id": "oehlen_intuit_sheet"}, "renderer": {"id": "oehlen_intuit_pens"}}


def test_registered_and_entry_loads():
    assert not kit.DISCOVERY_ERRORS
    ids = [e["id"] for e in kit.library.entries("typed_drawing")]
    assert "oehlen_intuit_sheet1" in ids
    d = kit.library.load("typed_drawing", "oehlen_intuit_sheet1")
    assert set(d["typed"]) == {"swoosh", "stub", "horizon", "feeler"}
    assert len(d["knot_m"]) == 300


def test_final_sheet_shape_pens_and_frame():
    s = kit.run(RECIPE)
    roles = {}
    for ink in s.inks:
        roles[ink.meta["role"]] = roles.get(ink.meta["role"], 0) + 1
        assert len(ink.points) >= 2 and not ink.filled
        p = ink.points
        assert p[:, 0].min() >= 0 and p[:, 1].min() >= 0 and p[:, 0].max() <= 200 and p[:, 1].max() <= 300
    assert roles["fat"] == roles["swoosh"] >= 2          # the self-crossing split is kept
    assert roles["feeler"] == 1 and "stub" not in roles
    assert 60 <= roles["knot"] <= 400                     # hollowed knot: joined runs, not 1000 flakes
    assert {i.pen for i in s.inks} == {0.3, 0.4, 0.5, 1.6}
    assert any(i.meta["colour"] == "#D14D41" for i in s.inks)


def test_machine_orientation_fits_axidraw():
    s = kit.run({**RECIPE, "frame": [300, 200], "voice": {"id": "oehlen_intuit_sheet", "turn": False}})
    P = np.vstack([i.points for i in s.inks])
    assert P[:, 0].max() <= 300 and P[:, 1].max() <= 218 and P.min() >= 0


def test_fat_stretch_is_a_staircase():
    s = kit.run(RECIPE)
    for ink in s.inks:
        if ink.meta["role"] == "fat":
            d = np.diff(ink.points, axis=0)
            assert np.all((np.abs(d[:, 0]) < 1e-9) | (np.abs(d[:, 1]) < 1e-9))   # axis-aligned steps only


def test_tau_controls_the_hole():
    a = kit.run({**RECIPE, "voice": {"id": "oehlen_intuit_sheet", "tau": 0.0}})
    b = kit.run({**RECIPE, "voice": {"id": "oehlen_intuit_sheet", "tau": 3.0}})
    knot_len = lambda s: sum(float(np.linalg.norm(np.diff(i.points, axis=0), axis=1).sum())  # noqa: E731
                             for i in s.inks if i.meta["role"] == "knot")
    assert knot_len(b) < 0.9 * knot_len(a)   # tau 3 lifts ~19 % of the knot (measured)


def test_deterministic_across_processes():
    code = ("import sys,json; sys.path.insert(0,'tools/gesture'); from gesture import kit; "
            f"s=kit.run({json.dumps(RECIPE)}); "
            "print(json.dumps([round(float(v),6) for i in s.inks for v in i.points.ravel()[:4]]))")
    outs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outs.append(subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                                   capture_output=True, text=True, check=True).stdout)
    assert outs[0] == outs[1]
