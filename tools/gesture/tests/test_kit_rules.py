"""Round 13, thread I-a `rules`: rules from the sheets, played as breakable rules (kit/arrangers_rules.py)."""
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
from gesture.kit import arrangers_rules as ar  # noqa: E402
from gesture.kit import core  # noqa: E402

FRAME = [300, 200]


def _recipe(seed=1317, hands=("dance_thrusting", "river_bend"), **arr):
    a = {"id": "rules", "found": 2,
         "found_boxes": [0.33, 0.33, 0.48, 0.42, -3.0, 0.42, 0.7, 0.6, 0.11, -7.0],
         "made_boxes": [0.4, 0.5, 0.55, 0.75, 0.55, 0.5, 0.5, 0.7], "cover_after": 1, "cover_wh": [24.0, 72.0]}
    a.update(arr)
    return {"frame": FRAME, "seed": seed, "margin": 4.0, "arranger": a,
            "parts": [{"voice": {"id": "diagram", "chart": "kappa", "hands": ["trail_miner"]}},
                      {"voice": {"id": "oehlen_found_river", "span_w": 2400}},
                      *[{"voice": {"id": "hand", "hand": h, "length": 3.0}} for h in hands]],
            "renderer": {"id": "oehlen_found_ink"}}


def _log(sh):
    return sh.marks[0].meta["rules"]["log"]


@pytest.fixture(scope="module")
def piece():
    return kit.run(_recipe())


def test_registered_and_importable():
    core.discover()
    assert not any("rules" in k for k in kit.DISCOVERY_ERRORS)
    assert "rules" in core.registry("arranger")
    kit.validate(_recipe())


def test_every_rule_logged_with_a_place_and_a_reason(piece):
    log = _log(piece)
    assert {e["rule"] for e in log} == set(ar.RULES)
    for e in log:
        assert e["event"] in ("fire", "break")
        assert len(e["xy"]) == 2 and e["why"]
        x, y = e["xy"]
        assert -1 <= x <= FRAME[0] + 1 and -1 <= y <= FRAME[1] + 1


def test_breaks_are_occasional(piece):
    """Rules mostly fire; a break is an event, not the norm."""
    log = _log(piece)
    br = [e for e in log if e["event"] == "break"]
    assert 1 <= len(br) <= len(log) // 3


def test_no_breaks_when_off():
    sh = kit.run(_recipe(breaks=False))
    assert all(e["event"] == "fire" for e in _log(sh))
    assert all(not c["cuts_made"] for c in sh.marks[0].meta["rules"]["covers"])


def test_r3_edge_entry_with_a_step():
    sh = kit.run(_recipe(rules="R3", grow_reach=0.0))
    made = [m for m in sh.marks if m.meta.get("of_role") == "made"]
    starts = {}
    for m in made:
        starts.setdefault(m.meta["line"], m)            # the first run of each line
    for m in starts.values():
        p0 = m.points[0]
        d_edge = min(p0[0], FRAME[0] - p0[0], p0[1], FRAME[1] - p0[1])
        assert d_edge <= 4.0 + 0.5                       # starts at the (inset) edge
        assert np.any(np.asarray(m["neg"]) == 3)         # with the stepped entry
    assert all(e["event"] == "fire" for e in _log(sh) if e["rule"] == "R3")


def test_r3_breaks_into_growth_when_a_found_end_is_near():
    sh = kit.run(_recipe(rules="R3,R4", grow_reach=200.0))
    r3 = [e for e in _log(sh) if e["rule"] == "R3"]
    assert r3 and all(e["event"] == "break" for e in r3)
    assert not any(np.any(np.asarray(m["neg"]) == 3) for m in sh.marks if m.meta.get("of_role") == "made")


def test_r1_weight_follows_ground_without_breaks():
    """With no breaks, a heavy stretch is near found ink or riding (the hysteresis may hold it a little longer)."""
    from scipy.spatial import cKDTree
    sh = kit.run(_recipe(rules="R1,R4", breaks=False, min_run=0.0))
    found = np.vstack([ar.resample(m.points, 0.2) for m in sh.marks
                       if m.meta.get("of_role") == "found" and not m.meta.get("text")])
    tree = cKDTree(found)
    pad = sh.recipe["arranger"]["region_pad"]
    bold = [m for m in sh.marks if m.meta.get("of_role") == "made" and m.meta.get("bold")]
    hair = [m for m in sh.marks if m.meta.get("of_role") == "made" and not m.meta.get("bold")]
    assert bold and hair
    for m in bold:
        d = tree.query(m.points)[0]
        riding = np.isin(np.asarray(m["neg"]).astype(int), (1, 4))
        assert np.mean((d <= pad + 1.0) | riding) > 0.95
    assert {m.meta["pen"] for m in bold} == {sh.recipe["arranger"]["bold_pen"]}


def test_r2_ends_in_the_found_shape(piece):
    r2 = [e for e in _log(piece) if e["rule"] == "R2"]
    assert r2
    lines = piece.marks[0].meta["rules"]["lines"]
    for L in lines:
        if L["motif"]:
            ends = [m for m in piece.marks if m.meta.get("of_role") == "made" and m.meta.get("line") == L["line"]]
            assert np.asarray(ends[-1]["neg"])[-1] == 5          # the line stops inside its motif


def test_become_keeps_own_line_when_env_is_zero():
    t = np.linspace(0, 1, 200)
    seg = np.c_[t * 60, 10 * np.sin(t * 3)]
    seg = ar.resample(seg, 0.4)
    src = np.c_[np.linspace(0, 40, 101), 2 * np.sin(np.linspace(0, 40, 101))]
    q = ar.become(seg, ar.resample(src, 0.4), 0, np.zeros(len(seg)), step=0.4, scale=1.0, sigma=0.0,
                  bounds=(-1e3, -1e3, 1e3, 1e3))
    assert np.max(np.linalg.norm(q - seg[: len(q)], axis=1)) < 1.0


def test_feature_start_finds_the_spike():
    row = np.c_[np.linspace(0, 100, 251), np.zeros(251)]
    row[150:153, 1] = -8.0                        # a spike 60 mm along
    i = ar.feature_start(row, 50, step=0.4, window_mm=10.0, search_mm=60.0)
    assert 120 <= i <= 152


def test_r5_cover_cuts_the_found():
    from shapely.geometry import LineString, Polygon
    sh = kit.run(_recipe(rules="R5", made_share=1.0))
    cov = sh.marks[0].meta["rules"]["covers"]
    assert len(cov) == 1 and not cov[0]["cuts_made"]
    P = Polygon(cov[0]["polygon"]).buffer(-0.5)
    for m in sh.marks:
        if m.meta.get("of_role") == "found":
            assert LineString(m.points).intersection(P).length < 0.5


def test_r5_breaks_on_its_own_knot():
    from shapely.geometry import LineString, Polygon
    sh = kit.run(_recipe(rules="R5", made_share=0.0))
    cov = sh.marks[0].meta["rules"]["covers"][0]
    assert cov["cuts_made"]
    P = Polygon(cov["polygon"]).buffer(-0.5)
    for m in sh.marks:
        if m.meta.get("of_role") == "made" and m.meta["line"] == 0:      # drawn before the cover
            assert LineString(m.points).intersection(P).length < 0.5


def _digest(sh):
    h = hashlib.sha256()
    for ink in sh.inks:
        h.update(np.round(ink.points, 4).tobytes())
    h.update(json.dumps(_log(sh), sort_keys=True).encode())
    return h.hexdigest()


def test_deterministic_across_processes(piece):
    code = ("import sys, json; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
            "from test_kit_rules import _recipe, _digest\nfrom gesture import kit\n"
            "print(_digest(kit.run(_recipe())))") % (str(HERE), str(Path(__file__).parent))
    outs = set()
    for seed in ("1", "77"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
        outs.add(r.stdout.strip().splitlines()[-1])
    assert outs == {_digest(piece)}
