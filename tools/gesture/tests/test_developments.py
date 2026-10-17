"""Round 10 developments (kit files dev_*.py): beads, rare machine events, chorus."""
from __future__ import annotations

import numpy as np
import pytest

from gesture import kit
from gesture.kit.core import Mark
from gesture.kit.dev_chorus import parse_inks, render_colour
from gesture.kit.dev_rare import place_events

V = {"id": "drift_tokens", "joins": "chain", "length": 1.0}
PULSE = {"id": "prosody", "unit": "pulse", "span": 5.0}
SEG = {"id": "prosody", "unit": "segment", "span": 8.0}


def test_registered_and_discovered():
    kit.discover()
    assert not {k: v for k, v in kit.DISCOVERY_ERRORS.items() if "dev_" in k}
    reg = kit.registry()
    assert "dev_beads" in reg["renderer"] and "dev_rare_machine" in reg["modulator"]
    assert "dev_chorus" in reg["arranger"]


def _stressed_line(L=80.0, a=20.0, b=70.0):
    """A gently curving 80 mm line, loud from a to b mm (a 50 mm stress: a sausage in round 9)."""
    t = np.linspace(0, L, 401)
    pts = np.column_stack([20 + t, 60 + 6 * np.sin(t / 15.0)])
    e = ((t >= a) & (t <= b)).astype(float)
    return Mark(pts, {"emphasis": e, "r": 2 * e})


def _render(marks, **p):
    from gesture.kit.core import Ctx, _Run, get
    from gesture.kit import library
    m = get("renderer", "dev_beads")
    prm = m.validate({"id": "dev_beads", **p})
    ctx = Ctx((267.0, 180.0), (0, 0, 267, 180), 1, 1, 0, "renderer", "dev_beads", _Run(library.default()))
    return m.fn(ctx, marks, **{k: v for k, v in prm.items() if k != "id"})


@pytest.mark.parametrize("shape", ["gather", "pool", "cluster"])
def test_a_long_stress_stays_round(shape):
    inks = _render([_stressed_line()], shape=shape, size=7.0)
    beads = [k for k in inks if k.meta.get("role", "").startswith("bead")]
    assert beads, shape
    pts = np.vstack([k.points for k in beads])
    ext = np.ptp(pts, axis=0)
    # a 50 mm stress gives a mass at most ~1.6× its bead size, never a 50 mm capsule
    assert ext.max() < 7.0 * 1.3 * 1.7, (shape, ext)
    rings = [k for k in beads if k.closed and k.filled]
    assert rings and all(np.allclose(k.points[0], k.points[-1]) for k in rings)


def test_string_beads_along_the_stretch_and_ghost_has_no_line():
    inks = _render([_stressed_line()], shape="string", size=5.0, line="none")
    assert not [k for k in inks if k.meta.get("role") == "line"]
    rings = [k for k in inks if k.closed and k.filled]
    assert len(rings) >= 4
    cx = sorted(float(np.mean(k.points[:, 0])) for k in rings)
    assert cx[0] >= 20 + 20 - 4 and cx[-1] <= 20 + 70 + 4


def test_knot_is_one_contiguous_line_and_longer():
    m = _stressed_line()
    inks = _render([m], shape="knot", size=7.0, loops=4)
    assert len(inks) == 1
    L = float(np.sum(np.linalg.norm(np.diff(inks[0].points, axis=0), axis=1)))
    assert L > m.length() + 20.0
    assert np.allclose(inks[0].points[0], m.points[0]) and np.allclose(inks[0].points[-1], m.points[-1])


def test_beads_deterministic_and_preserve_marks():
    rec = {"seed": 7000, "voice": V, "modulators": [SEG], "renderer": {"id": "dev_beads", "shape": "cluster"}}
    a, b = kit.run(rec), kit.run(rec)
    assert len(a.inks) == len(b.inks)
    assert all(np.array_equal(x.points, y.points) for x, y in zip(a.inks, b.inks))
    assert np.array_equal(a.marks[0].points, b.marks[0].points)


def test_rare_machine_none_is_identity_and_events_are_rare():
    base = kit.run({"seed": 7000, "voice": V})
    none = kit.run({"seed": 7000, "voice": V, "modulators": [{"id": "dev_rare_machine", "events": 0}]})
    assert np.array_equal(base.marks[0].points, none.marks[0].points)
    assert not np.any(none.marks[0]["machine"])
    two = kit.run({"seed": 7000, "voice": V, "modulators": [{"id": "dev_rare_machine", "events": 2,
                                                               "min_gap": 40.0}]})
    m = two.marks[0]
    iv = m.meta["rare_machine"]["at"]
    assert 1 <= len(iv) <= 2 and "voice" in m.channels and "token" in m.channels
    if len(iv) == 2:
        assert iv[1][0] - iv[0][1] >= 40.0
    assert float(np.mean(m["machine"] > 0)) < 0.15


def test_place_events_respects_ends_and_count():
    t = np.linspace(0, 300, 1201)
    pts = np.column_stack([t, 10 * np.sin(t / 7.0)])
    m = Mark(pts)
    rng = np.random.default_rng(0)
    iv = place_events(m, events=3, place="salient", stretch=12.0, min_gap=50.0, rng=rng)
    L = m.length()
    assert len(iv) <= 3
    assert all(a > 5 and b < L - 5 for a, b in iv)


def test_chorus_all_listens_to_every_earlier_voice():
    lead = {"voice": V, "modulators": [PULSE], "renderer": {"id": "nib", "style": "e"}}
    f1 = {"voice": {**V, "hands": ["bubble", "hokusai"]}, "modulators": [SEG]}
    f2 = {"voice": {"id": "hand", "hand": "meander69", "length": 1.0}, "modulators": [SEG],
          "renderer": {"id": "dev_beads", "shape": "gather", "line": "none"}}
    sh = kit.run({"seed": 7100, "parts": [lead, f1, f2],
                  "arranger": {"id": "dev_chorus", "answer_to": "all", "radius": 10.0, "inks": "black,red,blue"}})
    from scipy.spatial import cKDTree
    by = {p: [m for m in sh.marks if m.meta["part"] == p] for p in range(3)}
    earlier = np.vstack([m.points[m["emphasis"] > 0.15] for p in (0, 1) for m in by[p]] or [np.zeros((0, 2))])
    loud2 = np.vstack([m.points[m["emphasis"] > 0.99] for m in by[2]] or [np.zeros((0, 2))])
    if len(earlier) and len(loud2):
        d, _ = cKDTree(earlier).query(loud2)
        assert float(np.min(d)) > 5.0
    im = render_colour(sh, px_per_mm=1.0)
    assert im.size == (267, 180)
    assert by[2][0].meta["chorus"]["listens_to"] == [0, 1]


def test_inks_are_checked():
    assert parse_inks("black, red") == ["black", "red"]
    with pytest.raises(ValueError):
        parse_inks("black,mauve")
