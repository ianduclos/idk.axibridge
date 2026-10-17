"""Solid abstract script (round 11, exploration 3): kit modules + texture measure."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gesture import kit  # noqa: E402
from gesture.kit import script_solid as S  # noqa: E402
from gesture.kit import script_solid_measure as tm  # noqa: E402

ROOT = HERE.parents[2]

ROW = {"seed": 11000, "frame": [160.0, 52.0], "margin": 4.0,
       "voice": {"id": "script_solid", "hand": "shikasta", "x_height": 6.0, "rows": 2, "leading": 3.0,
                 "nib_w": 0.4, "dots": 0.3},
       "renderer": {"id": "script_solid_nib", "pen": 0.3}}


def test_registered_and_no_discovery_errors():
    kit.core.discover()
    reg = kit.core.registry()
    assert "script_solid" in reg["voice"]
    assert {"script_solid_nib", "script_solid_bar"} <= set(reg["renderer"])
    assert {"script_solid_page", "script_solid_stack"} <= set(reg["arranger"])
    assert not {k: v for k, v in kit.DISCOVERY_ERRORS.items() if "script_solid" in k}


def test_row_marks_channels_and_box():
    sh = kit.run(ROW)
    words = [m for m in sh.marks if m.meta["kind"] in ("word", "swash")]
    dots = [m for m in sh.marks if m.meta["kind"] == "dot"]
    assert len(words) >= 6 and dots
    for m in sh.marks:
        assert {"r", "phi", "W", "M"} <= set(m.channels)
        assert np.all(m["W"] > 0)
    P_ = np.vstack([m.points for m in sh.marks])
    assert P_[:, 0].min() >= 4.0 - 1.5 and P_[:, 0].max() <= 156.0 + 1.5
    assert {m.meta["row"] for m in words} == {0, 1}


def test_min_glyphs_and_row_join():
    r = json.loads(json.dumps(ROW))
    r["voice"]["join"] = "row"
    sh = kit.run(r)
    rows = [m for m in sh.marks if m.meta["kind"] == "row"]
    assert len(rows) == 2                       # each row is ONE continuous line
    w = np.asarray(rows[0]["W"])
    assert w.min() < 0.3 * w.max()              # hairline kashidas between words


def test_nib_fill_is_line_built_not_hatching():
    sh = kit.run(ROW)
    fills = [k for k in sh.inks if k.meta.get("fill")]
    hair = [k for k in sh.inks if k.meta.get("hairline")]
    assert fills and hair
    # a fill path is contour-parallel: consecutive points are close (no long straight hatch jumps)
    for k in fills:
        d = np.linalg.norm(np.diff(k.points, axis=0), axis=1)
        assert d.max() < 3.0


def test_line_built_keeps_counters_white():
    from shapely.geometry import Point
    ring = Point(0, 0).buffer(5.0).difference(Point(0, 0).buffer(2.0))
    paths = S.line_built(ring, pen=0.3, pitch=0.8)
    pts = np.vstack([p for p, _ in paths])
    r = np.linalg.norm(pts, axis=1)
    assert r.min() > 2.0 and r.max() < 5.0


def test_bar_renderer_carves():
    r = json.loads(json.dumps(ROW))
    r["renderer"] = {"id": "script_solid_bar", "merge": "word"}
    sh = kit.run(r)
    assert sh.inks and all(k.meta.get("kind") in ("bar", "dot") for k in sh.inks)


def test_page_arrangers_run():
    rec = {"seed": 11400, "frame": [200.0, 120.0], "margin": 8.0,
           "arranger": {"id": "script_solid_page", "layout": "wrap", "drawing_box": [0.3, 0.2, 0.4, 0.6]},
           "parts": [{"voice": {"id": "hand", "hand": "matisse", "length": 3.0}, "renderer": {"id": "wire"}},
                     {"voice": {"id": "script_solid", "hand": "matisse", "x_height": 5.0, "direction": "ltr"},
                      "renderer": {"id": "script_solid_nib"}}]}
    sh = kit.run(rec)
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    draw = unary_union([LineString(m.points) for m in sh.marks if m.meta["part"] == 0])
    words = [m for m in sh.marks if m.meta["part"] == 1 and m.meta.get("kind") == "word"]
    assert words
    hits = sum(LineString(m.points).intersects(draw) for m in words)
    assert hits <= 0.1 * len(words)            # the script writes around the drawing
    for lay in ("margin", "diagonal"):
        rec["arranger"] = {"id": "script_solid_page", "layout": lay}
        sh = kit.run(rec)
        P_ = np.vstack([m.points for m in sh.marks])
        assert P_.min() >= 0 and P_[:, 0].max() <= 200 and P_[:, 1].max() <= 120


def test_texture_measure_on_synthetic_rows():
    m = np.zeros((300, 800), bool)
    for row in (60, 160, 260):
        for x0 in range(20, 760, 60):          # words of vertical strokes with gaps
            for k in range(4):
                xs = x0 + 10 * k
                m[row - 20:row, xs:xs + 3] = True
            m[row - 2:row, x0:x0 + 33] = True
    recs = tm.measure(m)
    assert len(recs) == 3
    s = tm.summarize(recs)
    assert 0.5 < s["colfill"][0] <= 1.0
    assert s["word_W"][0] > s["gap_W"][0] > 0


def test_deterministic_across_processes():
    code = ("import sys,json,hashlib;sys.path.insert(0,'tools/gesture');from gesture import kit;"
            f"sh=kit.run(json.loads({json.dumps(json.dumps(ROW))}));"
            "print(hashlib.md5(b''.join(k.points.tobytes() for k in sh.inks)).hexdigest())")
    outs = set()
    for seed in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                           timeout=300)
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout.strip())
    assert len(outs) == 1


@pytest.mark.parametrize("hand", ["meander69", "mime_mantis"])
def test_other_hands(hand):
    r = json.loads(json.dumps(ROW))
    r["voice"].update({"hand": hand, "simple_only": True, "rows": 1})
    assert kit.run(r).inks
