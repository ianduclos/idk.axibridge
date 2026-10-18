"""Round 13, thread II-c `accrue`: morph by accumulation (voice accrue_walk, modulator accrue_ink)."""
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

PIECE = {"frame": [297.0, 105.0], "seed": 3944, "margin": 6.0,
         "parts": [{"voice": {"id": "accrue_walk"}, "modulators": [{"id": "accrue_ink"}]}],
         "renderer": {"id": "nib", "style": "e", "pen": 0.4}}


@pytest.fixture(scope="module")
def piece():
    return kit.run(PIECE)


def test_registered_and_imports_cleanly():
    kit.list()
    assert not {k: v for k, v in kit.DISCOVERY_ERRORS.items() if "accrue" in k}
    desc = kit.describe()
    text = json.dumps(desc)
    assert "accrue_walk" in text and "accrue_ink" in text


def test_deterministic_in_process(piece):
    again = kit.run(PIECE)
    assert np.array_equal(piece.marks[0].points, again.marks[0].points)
    assert len(piece.inks) == len(again.inks)


def test_deterministic_across_hash_seeds(piece):
    code = ("import sys,json; sys.path.insert(0, %r); from gesture import kit; "
            "s = kit.run(json.loads(%r)); import numpy as np; "
            "print(float(np.round(s.marks[0].points.sum(), 6)), len(s.inks))") % (str(HERE), json.dumps(PIECE))
    outs = set()
    for hs in ("1", "4242"):
        env = dict(os.environ, PYTHONHASHSEED=hs)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
        outs.add(r.stdout.strip().splitlines()[-1])
    assert len(outs) == 1
    want = f"{float(np.round(piece.marks[0].points.sum(), 6))} {len(piece.inks)}"
    assert outs == {want}


def test_ink_stays_on_the_paper(piece):
    W, H = piece.frame
    P = np.vstack([i.points for i in piece.inks])
    assert P[:, 0].min() >= 0 and P[:, 1].min() >= 0 and P[:, 0].max() <= W and P[:, 1].max() <= H


def test_loop_ratchet_is_a_staircase(piece):
    """In loops mode the curl only tightens at completed loops (a step per loop), until the first break."""
    ev = piece.marks[0].meta["accrue"]
    k0 = ev["knots"][0]["s"]
    steps = [e for e in ev["loops"] if e["s"] < k0]
    assert steps and steps[0]["kind"] == "first"
    mags = [abs(e["C"]) for e in steps if e["kind"] != "relapse"]
    assert all(b >= a - 1e-9 for a, b in zip(mags, mags[1:]))
    assert mags[-1] > 5 * mags[0]
    # same sense throughout one habit
    assert len({np.sign(e["C"]) for e in steps}) == 1


def test_knot_breaks_habit_and_hands_spin_to_the_nib(piece):
    m = piece.marks[0]
    c, ev = m.channels, m.meta["accrue"]
    s = c["acc_s"]
    k = ev["knots"][0]
    before = (s > k["s"] - 20) & (s < k["s"] - 2)
    after = (s > k["s"] + 30) & (s < k["s"] + 60)
    assert c["acc_curl"][before].max() > 0.9
    assert c["acc_curl"][after].max() < 0.2          # the habit broke
    assert np.abs(c["acc_spin"][after]).max() > 0.1  # the nib took the spin
    late = (s > k["s"] + 250) & (s < k["s"] + 300)
    assert np.abs(c["acc_spin"][late]).max() < 0.25 * np.abs(c["acc_spin"][after]).max()  # and it decays
    # the knot is mass, the free start is wire
    assert c["r"][(s > k["s"] - 14) & (s <= k["s"])].max() > 1.5
    assert c["r"][s < 80].max() < 0.05


def test_exhaust_and_recall_gap():
    rec = json.loads(json.dumps(PIECE))
    rec["parts"][0]["voice"].update({"exhaust": 1, "recall_gap": 120.0})
    for sd in (3944, 3965):
        rec["seed"] = sd
        ev = kit.run(rec).marks[0].meta["accrue"]
        assert len(ev["knots"]) <= 1
        for r in ev["recalls"]:
            assert r["s"] - r["from_s"] > 120.0 - 1.0


def test_regime_channels_bounded(piece):
    c = piece.marks[0].channels
    assert c["r"].min() >= 0 and c["r"].max() <= 2
    for k in ("phi", "W", "M"):
        assert np.all(np.isfinite(c[k]))


def test_leaky_mode_runs():
    rec = json.loads(json.dumps(PIECE))
    rec["parts"][0]["voice"].update({"habit": "leaky", "c_rate": 0.0, "length": 4.0})
    sh = kit.run(rec)
    assert len(sh.inks) > 0
    assert "acc_curl" in sh.marks[0].channels
