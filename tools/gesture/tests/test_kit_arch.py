"""Round 15 C `arch`: past keeps in new roles (kit/arrangers_arch.py, kit/renderers_arch.py)."""
from __future__ import annotations

import hashlib
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
from gesture.kit import arrangers_arch as ar  # noqa: E402
from gesture.kit._score import score_of  # noqa: E402
from gesture.kit.arrangers_oehlen_found import FLEXOKI, arclen  # noqa: E402

SEEDS = (15002, 15006)


@pytest.fixture(scope="module")
def sheets():
    return {s: kit.run(ar.recipe(s)) for s in SEEDS}


def digest(sheet):
    h = hashlib.sha256()
    for ink in sheet.inks:
        h.update(np.round(ink.points, 6).tobytes())
        h.update(str((ink.pen, ink.meta.get("colour"))).encode())
    return h.hexdigest()


def log(sheet):
    return sheet.marks[0].meta["arch"]


def test_registered():
    assert "arch" in kit.core.registry("arranger")
    assert "arch_ink" in kit.core.registry("renderer")
    assert not kit.core.DISCOVERY_ERRORS


def test_plan_roles_and_retired_chart():
    """Each family takes its new role; the kappa chart never enters as found matter; density stays middle."""
    seen = {f: 0 for f in ar.FAMILIES}
    for s in range(100):
        p = ar.plan_arch(np.random.default_rng(s), 300.0, 200.0)
        assert all(f["kind"] != "chart" for f in p["found"])
        assert p["density"]["dial"] <= 0.4 and p["density"]["lines"] <= 7
        assert 2 <= len(p["families"]) <= 4
        for f in p["families"]:
            seen[f] += 1
        if p["traverse"]:
            assert p["traverse"]["kind"] == "danced" and p["traverse"]["hands"]
        if p["intruder"]:
            assert p["intruder"]["kind"] == "swell"
        if p["passer"]:
            assert p["container"] is not None          # the passer's zone
        assert p["play"]["bold_pen"] <= 0.5            # weight belongs to the swell
    assert min(seen.values()) >= 30                    # every family shows up across a population


def test_deterministic_in_process(sheets):
    s = SEEDS[0]
    assert digest(kit.run(ar.recipe(s))) == digest(sheets[s])


def test_deterministic_across_processes(sheets):
    code = ("import sys, hashlib, numpy as np; sys.path.insert(0, %r)\n"
            "from gesture import kit\nfrom gesture.kit import arrangers_arch as ar\n"
            "s = kit.run(ar.recipe(%d)); h = hashlib.sha256()\n"
            "for i in s.inks:\n    h.update(np.round(i.points, 6).tobytes()); "
            "h.update(str((i.pen, i.meta.get('colour'))).encode())\nprint(h.hexdigest())") % (str(HERE), SEEDS[1])
    env = {**os.environ, "PYTHONHASHSEED": "123"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
    assert out.stdout.strip() == digest(sheets[SEEDS[1]])


def test_score_is_complete(sheets):
    """Every sheet records a score whose relations name real layers, and it is JSON-able."""
    for s, sh in sheets.items():
        sc = score_of(sh)
        assert sc and sc["version"] == 1
        json.dumps(sc)
        ids = {L["id"] for L in sc["layers"]}
        roles = {L["role"] for L in sc["layers"]}
        assert {"region", "line"} <= roles
        for r in sc["relations"]:
            assert r["src"] in ids and r["dst"] in ids and r["src"] != r["dst"]
        p = log(sh)["plan"]
        if p["traverse"]:
            assert "traverse" in roles and any(r["kind"] == "cross" for r in sc["relations"])
        if p["intruder"]:
            assert "intruder" in roles and any(r["kind"] == "intrude" for r in sc["relations"])
        if p["passer"] and log(sh)["passer_spans"]:
            assert any(r["kind"] == "translate" for r in sc["relations"])
        assert sc["decisions"]["families"] == p["families"]


def test_inside_paper_and_real_pens(sheets):
    for sh in sheets.values():
        W, H = sh.frame
        for ink in sh.inks:
            assert ink.points.min() >= 0.0
            assert (ink.points.max(axis=0) <= [W, H]).all()
            assert ink.meta.get("colour") in FLEXOKI


def test_heavy_ink_is_the_swell_or_a_nib(sheets):
    """T3: the only heavy line work is the swell (and nib/mass rendering); made lines stay ≤ 0.5 mm."""
    for sh in sheets.values():
        for m in sh.marks:
            if m.meta.get("draw", "wire") == "wire":
                assert float(m.meta.get("pen", 0.4)) <= 0.5


def test_swell_masses_are_round():
    """The swell renders round heads: its filled rings are near-circular, never capsules."""
    for s in range(15001, 15012):
        sh = kit.run(ar.recipe(s, families="swell,danced"))
        rings = [i for i in sh.inks if i.meta.get("role") == "intruder" and i.filled and len(i.points) > 20]
        if not rings:
            continue
        for ring in rings:
            q = ring.points - ring.points.mean(axis=0)
            ev = np.sqrt(np.maximum(np.linalg.eigvalsh(np.cov(q.T)), 1e-12))
            assert ev[1] / ev[0] < 4.0
        return
    pytest.skip("no swell heads in these seeds")


def test_flicker_figures_leave_and_return_to_the_host():
    found = 0
    for s in range(15001, 15010):
        sh = kit.run(ar.recipe(s, families="flicker,danced"))
        for e in log(sh)["flicker"]:
            figs = [m for m in sh.marks if m.meta.get("register") == "flicker" and m.meta["obj"][1] == e["fig"]]
            assert len(figs) == 1
            f = figs[0]
            assert np.allclose(f.points[0], e["at"], atol=0.06) and np.allclose(f.points[-1], f.points[0], atol=0.5)
            assert float(np.max(f["r"])) > 0.5 and float(f["r"][0]) < 0.5      # rises to nib, starts at wire
            found += 1
    assert found >= 3


def test_passer_changes_type_and_pen_only_in_its_zone():
    for s in range(15001, 15012):
        sh = kit.run(ar.recipe(s, families="passer,swell"))
        p = log(sh)["plan"]["passer"]
        if not p or not log(sh)["passer_spans"]:
            continue
        runs = [m for m in sh.marks if m.meta.get("register") == "passer"]
        for a, b in zip(runs[:-1], runs[1:]):
            assert np.allclose(a.points[-1], b.points[0])          # one line drawn by two pens
        inside = [m for m in runs if m.meta["ink"] == p["core_ink"]]
        assert inside
        for m in inside:
            mid = m.points[len(m.points) // 2]
            assert ar._core_depth(log(sh)["plan"], mid, "container") > -0.35   # in (or at) the container
        assert sum(arclen(m.points)[-1] for m in inside) < 0.6 * sum(arclen(m.points)[-1] for m in runs)
        return
    pytest.skip("no passer reached its zone in these seeds")


def test_steer_reaches_its_goal_and_keeps_turns():
    rng = np.random.default_rng(1)
    dth = rng.normal(0, 0.05, 4000)
    toks = ar.tokens(dth)
    assert toks[0][0] == 0 and toks[-1][1] == len(dth)
    pts, who = ar.steer({"x": (dth, toks)}, lambda pos, k: "x", (20, 100), (280, 100), frame=(300, 200),
                        via=(150, 60), pull=0.06)
    assert np.linalg.norm(pts[-1] - [280, 100]) < 4.0
    assert ((pts > 0) & (pts < [300, 200])).all()
    assert np.min(np.linalg.norm(pts - [150, 60], axis=1)) < 0.08 * 300


def test_unknown_family_refused():
    with pytest.raises(ValueError):
        kit.run(ar.recipe(15001, families="danced,nostalgia"))
