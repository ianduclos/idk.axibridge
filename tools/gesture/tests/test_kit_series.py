"""Round 12 `series`: a travelling line across a row of sheets, the cut into
sheets, per-sheet recipes, and the relay's line identity across sheets."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_series as S  # noqa: E402

SW, H, N = 100.0, 140.0, 3


def small(seed=31, **kw):
    """A three-sheet row: one hand mines, then hands over to a wire."""
    return {"frame": [N * SW, H], "seed": seed, "margin": 0,
            "arranger": {"id": "series_row", "sheets": N, "at": [0.6], "inks": "black,black,blue",
                         "tuck": kw.get("tuck", 0.0)},
            "parts": [
                {"voice": {"id": "series_travel", "hands": ["trail_miner", "fly_fru"], "hand_at": [0.6],
                           "length": 5.0, "sheets": N, "K": 4, "step": 0.5, "exit": kw.get("exit", False),
                           "route": [0.0, 0.3, 0.5, 0.6, 1.6, 0.4, 1.0, 2.7, 0.5]}},
                {"voice": {"id": "series_stretch"},
                 "renderer": {"id": "trail_gallery", "w0": 0.3, "w1": 4.0, "chamber": 2.0}},
                {"voice": {"id": "series_stretch"}, "renderer": {"id": "wire", "pen": 0.3}}],
            "renderer": {"id": "wire", "pen": 0.35}}


@pytest.fixture(scope="module")
def row():
    return S.run_series(small())


def test_registered_and_valid():
    assert not kit.DISCOVERY_ERRORS
    reg = kit.describe()
    ids = {k: {m["id"] for m in v} for k, v in reg.items()}
    assert {"series_travel", "series_stretch"} <= ids["voice"]
    assert "series_row" in ids["arranger"]
    rec = kit.validate(small())
    assert rec["arranger"]["sheets"] == N


def test_line_travels_the_row(row):
    strip, sheets = row
    assert len(sheets) == N
    assert all(s.frame == (SW, H) for s in sheets)
    xs = np.concatenate([m.points[:, 0] for m in strip.marks])
    assert xs.min() < SW and xs.max() > (N - 1) * SW      # reaches the first and the last sheet
    assert all(any(len(i.points) >= 2 for i in s.inks) for s in sheets)
    u = np.concatenate([m["series_u"] for m in strip.marks])
    assert u.min() >= 0.0 and u.max() <= 1.0


def test_stretches_get_parts_and_age(row):
    strip, _ = row
    parts = sorted({m.meta["part"] for m in strip.marks})
    assert parts == [1, 2]                                 # part 0's line is wholly handed on
    for m in strip.marks:
        a = np.asarray(m["age"])
        assert a[0] == pytest.approx(0.0, abs=1e-6) and a[-1] == pytest.approx(1.0, abs=1e-6)
    # the joint: the mine ends where the wire starts
    mine = [m for m in strip.marks if m.meta["part"] == 1][-1]
    wire = [m for m in strip.marks if m.meta["part"] == 2][0]
    assert np.allclose(mine.points[-1], wire.points[0])


def test_tuck_trims_the_handed_stretch():
    strip, _ = S.run_series(small(tuck=6.0))
    mine = [m for m in strip.marks if m.meta["part"] == 1][-1]
    wire = [m for m in strip.marks if m.meta["part"] == 2][0]
    assert np.linalg.norm(wire.points[0] - mine.points[-1]) > 2.0


def test_cut_is_continuous_across_edges(row):
    """Every wire ink that ends on a shared edge has a partner on the next
    sheet starting at the same height."""
    strip, sheets = row
    for k in range(N - 1):
        right = [p for i in sheets[k].inks if i.meta.get("part") == 2 for p in (i.points[0], i.points[-1])
                 if abs(p[0] - SW) < 1e-6]
        left = [p for i in sheets[k + 1].inks if i.meta.get("part") == 2 for p in (i.points[0], i.points[-1])
                if abs(p[0]) < 1e-6]
        for p in right:
            assert any(abs(p[1] - q[1]) < 1e-6 for q in left)
        assert len(right) == len(left)
    for s in sheets:
        for i in s.inks:
            assert i.points[:, 0].min() >= -1e-6 and i.points[:, 0].max() <= SW + 1e-6


def test_sheet_recipe_rebuilds_its_sheet(row, tmp_path):
    _, sheets = row
    p = S.save_sheet_recipe(sheets[1], tmp_path / "s.recipe.json")
    again = S.run_sheet(json.loads(p.read_text()))
    a = np.vstack([i.points for i in sheets[1].inks])
    b = np.vstack([i.points for i in again.inks])
    assert np.array_equal(a, b)


def test_render_and_assemble(row):
    _, sheets = row
    ims = [S.render(s, px_per_mm=1.0) for s in sheets]
    assert ims[0].size == (100, 140)
    wall = S.assemble(ims, gap=5, pad=10)
    assert wall.width == 2 * 10 + 3 * 100 + 2 * 5


def test_deterministic_across_processes():
    code = ("import sys, json, hashlib; sys.path.insert(0, %r); sys.path.insert(0, %r);"
            "import test_kit_series as T; from gesture.kit import arrangers_series as S;"
            "st, sh = S.run_series(T.small());"
            "print(hashlib.sha1(b''.join(i.points.tobytes() for s in sh for i in s.inks)).hexdigest())"
            ) % (str(ROOT), str(ROOT / "tests"))
    outs = set()
    for hs in ("1", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": hs}
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
        outs.add(r.stdout.strip().splitlines()[-1])
    assert len(outs) == 1


def test_relay_lines_recur_on_the_next_sheet():
    import series as X  # noqa: PLC0415
    recs = X.relay_sheets(5310, hands=["hokusai", "marden", "meander69"], length=0.8, side=120.0)
    assert len(recs) == 2
    a, b = kit.run(recs[0]), kit.run(recs[1])
    ans = np.vstack([m.points for m in a.marks if m.meta["part"] == 1])
    call = np.vstack([m.points for m in b.marks if m.meta["part"] == 0])
    assert np.array_equal(ans, call)                      # the answer comes back as the call, same shape
