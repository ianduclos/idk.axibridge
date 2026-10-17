"""Round 9 prosody / accumulation modules (kit files prosody_*.py)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from gesture import kit
from gesture.kit.core import KitError, Mark
from gesture.kit.prosody_modulators import line_events, select_stresses
from gesture.kit.prosody_renderers import stretches

V = {"id": "drift_tokens", "joins": "chain", "length": 1.0}
PROS = {"id": "prosody", "unit": "segment", "span": 8.0}


def test_registered_and_discovered():
    kit.discover()
    assert not {k: v for k, v in kit.DISCOVERY_ERRORS.items() if k.startswith("prosody")}
    reg = kit.registry()
    assert "drift_tokens" in reg["voice"] and "prosody" in reg["modulator"]
    assert {"restate", "coil"} <= set(reg["renderer"]) and "call_response" in reg["arranger"]


def test_drift_tokens_is_the_drift_line_plus_tokens():
    a = kit.run({"seed": 7000, "voice": {"id": "drift", "joins": "chain", "length": 1.0}})
    b = kit.run({"seed": 7000, "voice": V})
    ma, mb = a.marks[0], b.marks[0]
    assert np.array_equal(ma.points, mb.points) and np.array_equal(ma["voice"], mb["voice"])
    assert {"token", "tok_turn"} <= set(mb.channels)
    assert np.all(np.diff(mb["token"]) >= 0) and mb["token"][-1] > 5


def test_corner_is_heard_where_it_is():
    t = np.linspace(0, 50, 126)
    pts = np.vstack([np.column_stack([t, 0 * t]), np.column_stack([50 + 0 * t[1:], t[1:]])])
    evs = line_events(Mark(pts), listen=("corner",))
    assert len(evs) == 1 and abs(evs[0][0] - 50.0) < 1.5 and evs[0][2] == ("corner",)


def test_select_respects_gap_and_cap():
    evs = [(float(s), 1.0 - 0.001 * s, ("corner",)) for s in range(0, 300, 5)]
    st = select_stresses(evs, 300.0, rhythm="event", density=1.0, gap=30.0, primary=0.34, quiet=0.5)
    assert len(st) == 3
    assert all(b[0] - a[0] >= 30 for a, b in zip(st[:-1], st[1:]))
    assert sorted(lv for _, lv in st) == [0.5, 0.5, 1.0]


@pytest.mark.parametrize("rhythm", ["event", "regular", "syncopated", "phrase"])
def test_prosody_is_sparse_and_carries_channels(rhythm):
    rec = {"seed": 7000, "voice": V,
           "modulators": [{"id": "timing", "tempo": "staccato"}, {**PROS, "rhythm": rhythm}]}
    s1, s2 = kit.run(rec), kit.run(rec)
    m = s1.marks[0]
    assert {"emphasis", "tremor", "dance_t", "token", "voice"} <= set(m.channels)
    assert 0.0 < np.mean(m["emphasis"] > 0.15) < 0.4          # most of the line stays wire
    assert m["r"].min() >= 0 and m["r"].max() <= 2
    assert np.array_equal(m["r"], s2.marks[0]["r"])
    assert m.meta["prosody"]["stresses"]


def test_restate_counts_copies_and_bounds():
    rec = {"seed": 7000, "voice": V, "modulators": [{**PROS, "primary": 1.0}],
           "renderer": {"id": "restate", "copies": 5, "bound": "contour"}}
    sh = kit.run(rec)
    m = sh.marks[0]
    runs = stretches(m["emphasis"], 0.15)
    rest = [k for k in sh.inks if k.meta.get("role") == "restate"]
    bounds = [k for k in sh.inks if k.meta.get("role") == "bound"]
    exp = sum(int(round(4 * p)) for _, _, p in runs)
    assert len(rest) == exp and len(bounds) == sum(1 for *_, p in runs if round(4 * p) > 0)
    assert all(b.closed and np.allclose(b.points[0], b.points[-1]) for b in bounds)
    again = kit.run(rec)
    assert all(np.array_equal(a.points, b.points) for a, b in zip(sh.inks, again.inks))


def test_coil_spiral_is_one_line_per_stretch():
    base = {"seed": 7000, "voice": V, "modulators": [PROS]}
    sp = kit.run({**base, "renderer": {"id": "coil", "shape": "spiral"}})
    rg = kit.run({**base, "renderer": {"id": "coil", "shape": "rings"}})
    n = len(stretches(sp.marks[0]["emphasis"], 0.15))
    assert len([k for k in sp.inks if k.meta.get("role") == "coil"]) == n
    rings = [k for k in rg.inks if k.meta.get("role") == "coil"]
    assert len(rings) >= n and all(np.allclose(k.points[0], k.points[-1]) for k in rings)


def _overlap(sheet):
    a, b = sheet.marks[0], sheet.marks[1]
    uu = np.linspace(0, 1, 1001)
    ea = np.interp(uu, a.arclength() / a.length(), a["emphasis"])
    eb = np.interp(uu, b.arclength() / b.length(), b["emphasis"])
    return float(np.mean((ea > 0.15) & (eb > 0.15)))


def test_call_response_answers_into_silence():
    parts = [{"voice": V, "modulators": [PROS]},
             {"voice": {**V, "hands": ["bubble", "hokusai"]}, "modulators": [{**PROS, "density": 2.0}]}]
    free = kit.run({"seed": 7100, "parts": parts, "arranger": {"id": "single"}})
    ans = kit.run({"seed": 7100, "parts": parts, "arranger": {"id": "call_response", "listen_by": "time",
                                                               "window": 0.02}})
    assert _overlap(ans) <= _overlap(free)
    assert _overlap(ans) < 0.01
    assert ans.marks[1].meta["prosody"]["answer"]["by"] == "time"
    with pytest.raises(KitError):
        kit.run({"seed": 7100, "parts": [{"voice": V}, {"voice": V}], "arranger": {"id": "call_response"}})
    assert math.isfinite(_overlap(free))
