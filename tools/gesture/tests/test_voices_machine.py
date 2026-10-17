"""Round 9 — machine voices + diagram voices (kit/voices_machine*.py). Fast (< 30 s)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gesture import kit  # noqa: E402
from gesture.kit import voices_machine as vm  # noqa: E402
from gesture.kit import voices_machine_diagram as vd  # noqa: E402

DRIFT = {"id": "drift", "hands": ["matisse", "shikasta"], "length": 2.0}


def test_registered_and_discovered():
    assert not {k for k in kit.DISCOVERY_ERRORS if k.startswith("voices_machine")}
    reg = kit.registry()
    assert {"machine", "diagram"} <= set(reg["voice"])
    assert {"handover", "annotate"} <= set(reg["modulator"])


def _wiggle(n=600):
    t = np.linspace(0, 6 * math.pi, n)
    return np.column_stack([t * 10, 12 * np.sin(t) + 4 * np.sin(3.1 * t)])


@pytest.mark.parametrize("g", vm.GRAMMARS)
def test_grammar_lands_on_endpoints(g):
    p = _wiggle()
    q = vm.speak(g, p, np.random.default_rng(1), 6.0, {})
    assert np.allclose(q[0], p[0]) and np.allclose(q[-1], p[-1], atol=1e-6)
    assert np.all(np.isfinite(q)) and len(q) >= 2


def test_compass_and_stair_obey_their_rule():
    p = _wiggle()
    for g, k, nmax in (("compass", 5, 5), ("compass", 3, 3), ("stair", 0, 4)):
        q = vm.REWRITE[g](p, np.random.default_rng(2), 6.0, {"k": k})
        d = np.diff(q, axis=0)
        d = d[np.linalg.norm(d, axis=1) > 1e-6]
        h = np.round(np.degrees(np.arctan2(d[:, 1], d[:, 0])) % 360, 3)
        assert len(np.unique(np.round(h))) <= nmax, g


def test_machine_voice_and_determinism():
    rec = {"seed": 11, "voice": {"id": "machine", "grammar": "ruler", "length": 1.5}}
    a, b = kit.run(rec), kit.run(rec)
    assert np.array_equal(a.marks[0].points, b.marks[0].points)
    m = a.marks[0]
    assert m.meta["voices"] == ["machine:ruler"] and np.all(m["machine"] == 1 + vm.GRAMMARS.index("ruler"))


def test_handover_carries_channels_and_names_machines():
    sh = kit.run({"seed": 3, "voice": DRIFT, "modulators": [
        {"id": "timing", "tempo": "staccato"},
        {"id": "handover", "a": "stair", "b": "compass", "at": "even", "share": 0.4, "stretch": 15.0}]})
    m = sh.marks[0]
    assert {"dance_t", "tremor", "machine", "voice"} <= set(m.channels)
    assert m.meta["voices"][-2:] == ["machine:stair", "machine:compass"]
    assert len(m.meta["handover"]) >= 2
    took = m["machine"] > 0
    assert 0.1 < took.mean() < 0.9
    assert set(np.unique(m["voice"][took]).astype(int)) <= {len(m.meta["voices"]) - 2, len(m.meta["voices"]) - 1}


def test_annotate_layouts_place_chart_in_box():
    for layout in ("below", "right", "shadow"):
        sh = kit.run({"seed": 5, "voice": DRIFT, "modulators": [
            {"id": "handover", "a": "ruler", "b": "none", "share": 0.3},
            {"id": "annotate", "chart": "kappa", "layout": layout, "rows": 2}]})
        diag = [m for m in sh.marks if "diagram" in m.meta]
        assert diag, layout
        x0, y0, w, h = 0.0, 0.0, *sh.frame
        P_ = np.vstack([m.points for m in sh.marks])
        assert P_[:, 0].min() >= x0 - 1 and P_[:, 0].max() <= x0 + w + 1
        assert P_[:, 1].min() >= y0 - 1 and P_[:, 1].max() <= y0 + h + 1


@pytest.mark.parametrize("chart", vd.CHARTS)
def test_every_chart_draws(chart):
    sh = kit.run({"seed": 7, "voice": {"id": "diagram", "chart": chart, "hands": ["matisse", "shikasta"],
                                       "length": 1.5, "machine_a": "ruler", "share": 0.3, "rows": 2}})
    assert len(sh.inks) >= 3


def test_drawn_by_hand_changes_the_trace():
    base = {"id": "diagram", "chart": "phase", "hands": ["shikasta"], "length": 1.0}
    a = kit.run({"seed": 7, "voice": base})
    b = kit.run({"seed": 7, "voice": {**base, "drawn_by": "matisse"}})
    assert len(a.marks) == len(b.marks)
    assert any(len(x.points) != len(y.points) or not np.allclose(x.points, y.points)
               for x, y in zip(a.marks, b.marks))
    assert {"kind": "hand", "id": "matisse"} in [{"kind": e["kind"], "id": e["id"]} for e in b.meta["library"]]


def test_stroke_font_covers_labels():
    for s in ("K(S)", "DK/DS", "CORNERS/R", "M.RULE", "0123456789", "+12 -3.5"):
        polys = vd.text(s, 0, 0, 4)
        assert len(polys) >= len(s.replace(" ", "")), s
