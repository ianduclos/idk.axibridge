"""Round 10 — a drawing and its measurement (kit/measure_pairs.py). Fast (< 30 s)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesture import kit  # noqa: E402
from gesture.kit import measure_pairs as mp  # noqa: E402
from gesture.kit import voices_machine_diagram as vd  # noqa: E402
from gesture.kit.core import Mark  # noqa: E402

DRIFT = {"id": "drift", "hands": ["matisse", "shikasta"], "length": 2.0}


def _run(mods, seed=11, voice=None, **kw):
    return kit.run({"seed": seed, "frame": [200, 140], "margin": 6.0, "voice": voice or dict(DRIFT),
                    "modulators": mods, "renderer": {"id": "measure_wire"}, **kw})


def _wiggle(n=500, amp=12.0):
    t = np.linspace(0, 6 * math.pi, n)
    return np.column_stack([20 + t * 8, 60 + amp * np.sin(t)])


def test_registered_and_discovered():
    assert not {k for k in kit.DISCOVERY_ERRORS if k.startswith("measure")}
    reg = kit.registry()
    assert {"measure_pair", "measure_shadow", "measure_atlas", "measure_answer"} <= set(reg["modulator"])
    assert "measure_wire" in reg["renderer"]


@pytest.mark.parametrize("layout,chart", [("diptych", "atlas"), ("margin", "kappa"), ("under", "route"),
                                          ("wrap", "kappa"), ("diptych", "phase"), ("diptych", "ledger")])
def test_pair_layouts_keep_drawing_and_add_tied_indices(layout, chart):
    s = _run([{"id": "measure_pair", "layout": layout, "chart": chart, "index": 6}])
    roles = [m.meta.get("measure_role", "drawing") for m in s.marks]
    assert roles.count("drawing") == 1                       # the drawing is still one whole line
    assert roles.count("chart") > 5 and roles.count("index") > 0
    W, H = s.frame
    for m in s.marks:
        assert np.all(m.points[:, 0] >= -1) and np.all(m.points[:, 0] <= W + 1)
        assert np.all(m.points[:, 1] >= -1) and np.all(m.points[:, 1] <= H + 1)
    # the drawing does not overlap the chart's box in side-by-side layouts
    if layout == "diptych":
        d = next(m for m in s.marks if "measure_role" not in m.meta)
        ch = np.vstack([m.points for m in s.marks if m.meta.get("measure_role") == "chart"])
        assert d.points[:, 0].max() < ch[:, 0].min() + 1e-6


def test_index_numbers_sit_on_the_line_they_name():
    m = Mark(_wiggle(), {})
    M = vd.measure([m])
    ss = mp.anchors(M, 5, "even")
    assert len(ss) == 5 and all(0 < s < M["L"] for s in ss)
    polys = mp.index_on_drawing(M, ss, [str(i + 1) for i in range(5)], label_h=1.6, tick=1.6)
    ticks = polys[0::1]
    # every tick starts within ~0.6 mm of the drawing
    starts = [p[0] for p in ticks if len(p) == 2]
    d = [float(np.min(np.linalg.norm(M["p"] - q, axis=1))) for q in starts[:5]]
    assert min(d) < 0.7


def test_peaks_anchor_on_the_strongest_turns():
    p = _wiggle()
    p[250:260] += np.array([0.0, 6.0]) * np.linspace(0, 1, 10)[:, None]    # a kink
    M = vd.measure([Mark(p, {})])
    ss = mp.anchors(M, 1, "peaks")
    i = int(np.searchsorted(M["s"], ss[0]))
    k = np.abs(M["kappa"])
    assert k[max(i - 3, 0):i + 4].max() >= 0.8 * k.max()


def test_atlas_specimens_carry_provenance_and_orders():
    M = vd.measure([Mark(_wiggle(), {})])
    sp = mp.specimens(M)
    assert len(sp) >= 5
    for t in sp:
        assert t["s0"] <= t["s_mid"] <= t["s1"]
        assert np.allclose(t["p"], M["p"][t["a"]:t["b"]])
    by_turn = mp.order_specimens(sp, "turning", 99)
    assert [abs(t["turn"]) for t in by_turn] == sorted(abs(t["turn"]) for t in by_turn)
    by_time = mp.order_specimens(sp, "time", 3)
    assert len(by_time) == 3 and by_time[0]["s0"] <= by_time[-1]["s0"]


def test_shadow_union_merges_overlaps_into_fewer_closed_rings():
    # a line that crosses itself: the unmerged shadow crosses the line; merged → closed rings, less ink
    t = np.linspace(0, 2 * math.pi, 600)
    p = np.column_stack([100 + 40 * np.sin(t), 70 + 25 * np.sin(2 * t)])      # a figure-eight
    M = vd.measure([Mark(p, {})])
    pairs = mp.shadow_lines(M, law="kappa", side="left", gap=1.5, gain=3.0)
    rings, opened, G = mp.merged_rings(pairs, close=0.0, shape="beads")
    assert G is not None and G.is_valid and G.area > 0
    assert rings and all(np.allclose(r[0], r[-1]) for r in rings)
    raw = M["L"] + sum(float(np.sum(np.linalg.norm(np.diff(q, axis=0), axis=1))) for _, q, _ in pairs)
    ink = sum(float(np.sum(np.linalg.norm(np.diff(r, axis=0), axis=1))) for r in rings)
    assert ink < raw                                          # overlaps were merged away


def test_shadow_turns_pinches_but_never_breaks_the_drawing():
    import shapely
    M = vd.measure([Mark(_wiggle(), {})])
    pairs = mp.shadow_lines(M, law="kappa", side="turns", gap=0.6, gain=5.0)
    rings, opened, G = mp.merged_rings(pairs, close=0.0)
    covered = shapely.LineString(M["p"]).difference(G.buffer(0.05))
    # whatever the contour does not cover is kept as open line
    kept = sum(shapely.LineString(o).length for o in opened)
    assert kept >= covered.length - 0.6 * (len(getattr(covered, "geoms", [covered])) + 1)


def test_shadow_modulator_modes_and_channels():
    s0 = _run([{"id": "measure_shadow", "merge": "none"}])
    s1 = _run([{"id": "measure_shadow", "merge": "union", "side": "turns", "close": 0.8}])
    assert sum(m.meta.get("measure_role") == "shadow" for m in s0.marks) == 1
    rings = [m for m in s1.marks if m.meta.get("merged") and not m.meta.get("open")]
    assert rings and all(np.allclose(m.points[0], m.points[-1]) for m in rings)
    assert all("voice" in m.channels for m in s1.marks)       # channels carried from the drawing


def test_atlas_piece_layouts_and_answer():
    for layout in ("grid", "frieze", "exploded"):
        s = _run([{"id": "measure_atlas", "layout": layout, "cells": 12}])
        assert sum(m.meta.get("measure_role") == "atlas" for m in s.marks) >= 12
    s = _run([{"id": "measure_atlas", "keep_drawing": True, "cells": 8}])
    assert any(m.meta.get("measure_role") == "index" for m in s.marks)
    for quiet in ("spine", "lift"):
        a = _run([{"id": "measure_answer", "quiet": quiet, "spine": 0.04, "offset": 3.0}])
        ans = [m for m in a.marks if m.meta.get("measure_role") == "answer"]
        assert ans and all(np.all(np.isfinite(m.points)) for m in ans)


def test_deterministic_and_wrap_frame_closed():
    r = [{"id": "measure_pair", "layout": "wrap", "index": 4}]
    a, b = _run(r), _run(r)
    assert len(a.marks) == len(b.marks)
    assert all(np.array_equal(x.points, y.points) for x, y in zip(a.marks, b.marks))
    fr = mp.rounded_frame((10, 10, 100, 60), 8.0)
    assert np.allclose(fr[0], fr[-1])
    assert fr[:, 0].min() >= 10 - 1e-6 and fr[:, 0].max() <= 110 + 1e-6


def test_renderer_pens_by_role():
    s = _run([{"id": "measure_pair", "layout": "margin", "chart": "kappa", "index": 3}])
    pens = {(i.meta["measure_role"], i.pen) for i in s.inks}
    assert ("drawing", 0.4) in pens and ("chart", 0.25) in pens
