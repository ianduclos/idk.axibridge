"""Round 14 b1 `cproc`: the composer as procedure (arrangers_cproc.py)."""
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
from gesture.kit import arrangers_cproc as cp  # noqa: E402

FAST = (58089, 60101)            # seeds whose plans are light (sparse / open): quick full runs


def test_registered_and_discovered():
    kit.discover()
    assert not kit.DISCOVERY_ERRORS
    assert "cproc" in kit.registry("arranger")
    assert "cproc_ink" in kit.registry("renderer")
    assert "cproc_score" in kit.registry("voice")


def test_frame_decided_on_purpose_and_fits_the_plotter():
    seen = set()
    for s in range(200):
        (w, h), name, why = cp.frame_for(s)
        assert why and name
        assert max(w, h) <= 300 and min(w, h) <= 218
        assert cp.frame_for(s) == cp.frame_for(s)
        seen.add(name)
    assert len(seen) >= 6                       # the frame varies: never the automatic A4


def _plans(n=60):
    out = []
    for s in range(1000, 1000 + n):
        (W, H), name, _ = cp.frame_for(s)
        out.append(cp.decide(np.random.default_rng([s, 1]), W, H, frame_name=name))
    return out


def test_density_dial_reaches_its_extremes():
    labels = [p["density_label"] for p in _plans(80)]
    assert labels.count("sparse") >= 5 and labels.count("all-over") >= 5      # U-shaped, extremes come up
    assert {"open", "dense"} <= set(labels)


def test_plans_are_not_one_template():
    plans = _plans(40)
    assert len({p["blank"]["kind"] for p in plans}) >= 4
    assert len({p["dominant"] for p in plans}) >= 4
    assert len({len(p["cores"]) for p in plans}) == 2
    orders = {tuple(a["act"] for a in p["acts"]) for p in plans}
    assert len(orders) >= 0.8 * len(plans)               # the act order is re-made per sheet
    xs = np.array([p["cores"][0]["xy"][0] / p["frame"][0] for p in plans])
    assert xs.std() > 0.15                               # the core moves


def test_order_has_a_late_reversal_then_a_crossing():
    for p in _plans(60):
        acts = [a["act"] for a in p["acts"]]
        assert acts.count("reversal") == 1
        k = acts.index("reversal")
        assert acts[k + 1] == "cross"
        drawn = [a for a in acts if a not in ("reversal", "cross")]
        assert k >= int(np.ceil(0.6 * len(drawn)))      # after at least 60 % of what is drawn
        json.dumps(p)                                    # the plan is a JSON record


def test_found_after_made_is_pasted_over_sometimes():
    flags = [a.get("pasted_over") for p in _plans(80) for a in p["acts"] if a["act"] == "found" and "pasted_over" in a]
    assert flags and any(flags)


def test_score_cut_and_tint():
    S = cp.Score(100, 100)
    S.add(np.c_[np.linspace(0, 100, 200), np.full(200, 50.0)], role="made", ink="black", pen=0.4, act=0, player="x")
    sq = np.array([[40, 40], [60, 40], [60, 60], [40, 60], [40, 40]], float)
    removed = S.cut([sq], ["cut"], "red")
    assert 18 < removed < 22
    assert len(S.items) == 2
    assert all(not ((it["mark"].points[:, 0] > 41) & (it["mark"].points[:, 0] < 59)).any() for it in S.items)
    S2 = cp.Score(100, 100)
    S2.add(np.c_[np.linspace(0, 100, 200), np.full(200, 50.0)], role="made", ink="black", pen=0.4, act=0, player="x")
    S2.cut([sq], ["tint"], "red")
    assert sorted(it["ink"] for it in S2.items) == ["black", "black", "red"]


def test_lay_along_follows_the_spine():
    spine = cp.bezier(np.array([0.0, 0.0]), np.array([50.0, 40.0]), np.array([100.0, -40.0]), np.array([150.0, 0.0]))
    L = float(cp.arclen(cp.resample(spine, 0.5))[-1])
    strip = np.c_[np.linspace(0, L, 300), np.full(300, 5.0)]
    out = cp.lay_along([strip], spine, 0.0, 5.0)
    assert len(out) == 1
    assert np.allclose(out[0][0], [0, 0], atol=0.6) and np.allclose(out[0][-1], [150, 0], atol=0.6)


def test_inside_runs_never_clamps_onto_the_edge():
    p = np.c_[np.linspace(-20, 120, 300), 50 + 30 * np.sin(np.linspace(0, 9, 300))]
    runs = cp.inside_runs(p, (0, 0, 100, 70))
    assert runs
    for r in runs:
        assert r[:, 0].min() >= 0 and r[:, 0].max() <= 100 and r[:, 1].max() <= 70


@pytest.mark.parametrize("seed", FAST)
def test_run_is_deterministic_and_inside_the_paper(seed):
    a = kit.run(cp.recipe(seed))
    b = kit.run(cp.recipe(seed))
    assert len(a.inks) == len(b.inks) > 0
    for x, y in zip(a.inks, b.inks):
        assert np.array_equal(x.points, y.points)
    W, H = a.frame
    for ink in a.inks:
        assert ink.points[:, 0].min() >= 0 and ink.points[:, 1].min() >= 0
        assert ink.points[:, 0].max() <= W and ink.points[:, 1].max() <= H
    plan = a.marks[0].meta["cproc"]
    assert plan["frame"] == [W, H]
    row = cp.table_row(a)
    assert row["seed"] == seed and row["order"]


def test_same_output_across_processes():
    code = ("import sys,hashlib; sys.path.insert(0, %r); from gesture import kit; "
            "from gesture.kit import arrangers_cproc as cp; s = kit.run(cp.recipe(58089)); "
            "h = hashlib.sha1(); [h.update(i.points.tobytes()) for i in s.inks]; print(h.hexdigest())") % str(HERE)
    outs = set()
    for hs in ("1", "777"):
        env = {**os.environ, "PYTHONHASHSEED": hs}
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=600)
        assert r.returncode == 0, r.stderr[-2000:]
        outs.add(r.stdout.strip().splitlines()[-1])
    assert len(outs) == 1


def test_density_override_changes_the_amount_of_drawing():
    def ink_mm(d):
        s = kit.run(cp.recipe(60101, density=d))
        return sum(float(cp.arclen(i.points)[-1]) for i in s.inks)
    assert ink_mm(0.97) > 2.5 * ink_mm(0.03)
