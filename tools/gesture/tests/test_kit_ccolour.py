"""Round 14 b4 `ccolour`: colour as structure (kit/arrangers_ccolour.py)."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_ccolour as cc  # noqa: E402
from gesture.kit.arrangers_oehlen_found import FLEXOKI  # noqa: E402

SEEDS = (4520, 4516)


@pytest.fixture(scope="module")
def sheets():
    return {s: kit.run(cc.recipe(s)) for s in SEEDS}


def digest(sheet):
    h = hashlib.sha256()
    for ink in sheet.inks:
        h.update(np.round(ink.points, 6).tobytes())
        h.update(str((ink.pen, ink.meta.get("colour"))).encode())
    return h.hexdigest()


def test_registered():
    assert "ccolour" in kit.core.registry("arranger")
    assert not kit.core.DISCOVERY_ERRORS


def test_compositions_differ_and_decide():
    """The composer decides frame, pens, mode, density and acts per seed: no template."""
    frames, modes, ns, lines, acts = set(), set(), set(), set(), set()
    for s in range(5000, 5040):
        r = cc.recipe(s)
        W, H = r["frame"]
        plan = cc.decide(np.random.default_rng(s), W, H)
        frames.add((W, H))
        modes.add(plan["pens"]["mode"])
        ns.add(plan["pens"]["n"])
        lines.add(plan["density"]["lines"])
        acts.add(tuple(k for k in ("container", "traverse", "counter", "intruder") if plan[k]))
    assert len(frames) >= 4 and len(modes) >= 4 and len(ns) >= 4
    assert max(lines) - min(lines) >= 7            # the density dial reaches its extremes
    assert len(acts) >= 6


def test_decide_is_deterministic():
    a = cc.decide(np.random.default_rng(7), 300.0, 200.0)
    b = cc.decide(np.random.default_rng(7), 300.0, 200.0)
    assert a == b


def test_run_deterministic(sheets):
    s = SEEDS[0]
    assert digest(kit.run(cc.recipe(s))) == digest(sheets[s])


def test_pens_are_real_and_few(sheets):
    for sheet in sheets.values():
        log = sheet.marks[0].meta["ccolour"]
        used = log["pens_used"]
        assert all(c in FLEXOKI for c in used)
        assert len(used) <= log["plan"]["pens"]["n"]
        assert set(used) <= set(log["plan"]["pens"]["palette"])


def test_inside_the_paper(sheets):
    for sheet in sheets.values():
        W, H = sheet.frame
        P = np.vstack([i.points for i in sheet.inks])
        assert P.min() >= 0.0 and P[:, 0].max() <= W and P[:, 1].max() <= H


def test_pen_changes_are_contiguous(sheets):
    """A change of pen along a line is one line drawn by two pens: the runs share their joint."""
    for sheet in sheets.values():
        prev = None
        joints = 0
        for m in sheet.marks:
            key = tuple(m.meta["obj"])
            if prev is not None and tuple(prev.meta["obj"]) == key and prev.meta["ink"] != m.meta["ink"]:
                if np.allclose(prev.points[-1], m.points[0]):
                    joints += 1
            prev = m
        log = sheet.marks[0].meta["ccolour"]
        if log["events"]:
            assert joints >= 1


def test_settle_makes_events_not_confetti():
    rng = np.random.default_rng(3)
    s = np.arange(600) * 0.3
    c = np.array(["own"] * 600, dtype=object)
    for a in rng.integers(0, 590, 25):               # 25 tiny borrowed blips
        c[a:a + int(rng.integers(1, 8))] = rng.choice(["a", "b"])
    out = cc._settle(c, s, "own", 15.0)
    cut = np.r_[0, np.flatnonzero(out[1:] != out[:-1]) + 1, len(out)]
    for a, b in zip(cut[:-1], cut[1:]):
        if out[a] != "own" and b < len(out):
            assert s[b - 1] - s[a] >= 15.0 - 0.31


def test_event_budget(sheets):
    for sheet in sheets.values():
        log = sheet.marks[0].meta["ccolour"]
        pp = log["plan"]["pens"]
        assert len(log["events"]) <= pp["budget"]
        per = {}
        for e in log["events"]:
            per[tuple(e["obj"])] = per.get(tuple(e["obj"]), 0) + 1
        assert all(v <= pp["per_line"] for v in per.values())


def test_legend_dud_and_acts():
    r = cc.recipe(SEEDS[0], colouring="legend", acts="core")
    sheet = kit.run(r)
    log = sheet.marks[0].meta["ccolour"]
    assert log["events"] == [{"kind": "legend"}]
    assert all(log["plan"][k] is None for k in ("traverse", "counter", "container", "intruder"))
    made = {m.meta["ink"] for m in sheet.marks if m.meta["register"] == "made"}
    assert made <= set(cc.LEGEND.values())
