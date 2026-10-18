"""Round 13 `stages`: a morph across a series caused by events. The line changes
only where it meets something: tested by moving the things it meets."""
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

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_stages as ST  # noqa: E402

SW, H, N = 148.0, 210.0, 5
ROUTE = [0.25, 0.25, 0.55, 0.4, 0.75, 0.62, 1.3, 0.68, 1.6, 0.45, 1.92, 0.35, 2.25, 0.5, 2.6, 0.42, 2.9, 0.5,
         3.25, 0.45, 3.58, 0.3, 3.75, 0.52, 3.5, 0.7, 3.3, 0.52, 3.62, 0.42, 4.15, 0.45, 4.5, 0.22, 4.6, 0.08]


def rec(seed=5316, river_box=(0.55, 0.56, 1.0, 0.2), red_box=(2.08, 0.08, 0.84, 0.84), cause="events"):
    """The review piece's recipe (experiments/stages.py r_main)."""
    line = {"id": "stages_line", "hand": "ingres", "length": 6000.0, "route": ROUTE,
            "read_box": [0.0, 0.0, 280.0, 400.0], "pull": 0.07, "reach": 20.0, "ride_mm": 55.0, "tau": 150.0,
            "p_max": 0.92, "dW": 0.55, "W_max": 2.6, "ink": 1700.0, "pool_gap": 10.0}
    return {"frame": [N * SW, H], "seed": seed, "margin": 0.0,
            "arranger": {"id": "stages_row", "sheets": N, "boxes": [*river_box, *red_box],
                         "effects": "grammar,nib", "inks": "black,blue,red", "cause": cause},
            "parts": [{"voice": line, "renderer": {"id": "stages_ink", "pen": 0.35}},
                      {"voice": {"id": "oehlen_found_river", "tile": "SB19", "rank": 0, "start": 0.18,
                                 "span_w": 1400, "angle": -8.0}, "renderer": {"id": "stages_layer", "pen": 0.3}},
                      {"voice": {"id": "hand", "hand": "hokusai", "length": 0.6},
                       "renderer": {"id": "stages_layer", "pen": 0.35}}],
            "renderer": {"id": "wire", "pen": 0.35}}


def the_line(sheet):
    return [m for m in sheet.marks if m.meta.get("part") == 0][0]


@pytest.fixture(scope="module")
def main():
    return ST.run_stages(rec())


def test_registered_and_no_discovery_errors():
    kit.list()
    from gesture.kit import core
    reg = core.registry()
    assert "stages_row" in reg["arranger"] and "stages_line" in reg["voice"]
    assert "stages_ink" in reg["renderer"] and "stages_layer" in reg["renderer"]
    assert not [k for k in kit.DISCOVERY_ERRORS if "stages" in k]


def test_events_in_order(main):
    strip, sheets = main
    ln = the_line(strip)
    kinds = [e[1].split(":")[0] for e in ln.meta["events"] if not e[1].startswith("waypoint")]
    assert kinds[0] == "ride" and "leave" in kinds
    first_cross = kinds.index("cross")
    first_pool = kinds.index("pool")
    assert first_cross < first_pool < kinds.index("dry")
    assert len(sheets) == N
    # nothing is wet before the first crossing; the caught grammar only after the ride
    s = ln.arclength()
    ev = {k: e[0] for e, k in ((e, e[1].split(":")[0]) for e in reversed(ln.meta["events"]))}
    W = np.asarray(ln["W"])
    assert W[s < ev["cross"] - 1.0].max() <= 0.35 + 1e-9
    src = np.asarray(ln["src"])
    assert not np.any(src[s < ev["leave"]] == 1)
    assert np.any(src[s > ev["leave"]] == 1)


def test_red_moved_same_path_no_nib(main):
    """Counterfactual: the line never meets the red voice → identical path, no nib, no beads."""
    a = the_line(main[0])
    b = the_line(ST.run_stages(rec(red_box=(2.15, 0.6, 0.7, 0.36)))[0])
    assert np.array_equal(a.points, b.points)
    assert np.asarray(b["W"]).max() <= 0.35 + 1e-9 and np.asarray(a["W"]).max() > 1.0
    assert not b.meta["pools"] and a.meta["pools"]


def test_river_moved_no_river_bends():
    b = the_line(ST.run_stages(rec(river_box=(0.55, 0.84, 1.0, 0.13)))[0])
    assert not np.any(np.asarray(b["src"]) == 1)
    assert not any(e[1].startswith("ride") for e in b.meta["events"])


def test_control_changes_at_edges_only():
    b = the_line(ST.run_stages(rec(cause="edges"))[0])
    kinds = [e[1].split(":")[0] for e in b.meta["events"]]
    assert "edge" in kinds and "ride" not in kinds and "cross" not in kinds


def test_sheet_recipe_rebuilds_sheet(main):
    strip, sheets = main
    k = 3
    again = ST.run_stage_sheet(sheets[k].meta["recipe"])
    assert len(again.inks) == len(sheets[k].inks)
    for p, q in zip(again.inks, sheets[k].inks):
        assert np.array_equal(np.asarray(p.points), np.asarray(q.points))


def test_beads_are_round(main):
    beads = [i for i in main[0].inks if i.meta.get("role") == "bead" and i.closed]
    assert beads
    for b in beads:
        p = np.asarray(b.points)
        c = p.mean(axis=0)
        r = np.linalg.norm(p - c, axis=1)
        assert r.max() / max(r.min(), 1e-9) < 1.6


def test_line_voice_alone():
    sh = kit.run({"frame": [148, 210], "seed": 5, "margin": 0,
                  "voice": {"id": "stages_line", "length": 300.0, "route": [0.2, 0.3, 0.8, 0.6]}})
    assert len(sh.marks) == 1 and sh.marks[0].length() > 50


def test_deterministic_across_processes(tmp_path):
    code = (f"import sys,json,hashlib; sys.path.insert(0,{str(ROOT)!r}); "
            "from gesture.kit import arrangers_stages as ST; import numpy as np; "
            f"r=json.loads({json.dumps(json.dumps(rec()))}); s,_=ST.run_stages(r); "
            "h=hashlib.sha1(); [h.update(np.ascontiguousarray(i.points).tobytes()) for i in s.inks]; "
            "print(h.hexdigest())")
    outs = []
    for seed in ("1", "77"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outs.append(subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                                   check=True).stdout.strip())
    assert outs[0] == outs[1] and outs[0]
