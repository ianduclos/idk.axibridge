"""Round 12, thread `revisit`: figures written at a limb's stops, and the
round-7 sign operators keyed to dance events (kit/voices_revisit.py,
kit/modulators_revisit.py, kit/renderers_revisit.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import kit  # noqa: E402
from gesture.kit import modulators_revisit as MR  # noqa: E402
from gesture.kit import voices_revisit as VR  # noqa: E402


def _recipe(**kw):
    v = {"id": "revisit_glyph", "trail": "particles", "host": "rfoot", "with_": "head", "seconds": 20,
         "still": 0.2, "min_hold_s": 0.25, "max_glyphs": 3, **kw}
    return {"seed": 1201, "frame": [150, 210], "margin": 10, "voice": v,
            "renderer": {"id": "revisit_nib", "inks": "black,red"}}


def test_registered():
    ids = {k: {m["id"] for m in v} for k, v in kit.describe().items()}
    assert not any("revisit" in k for k in kit.DISCOVERY_ERRORS)
    assert "revisit_glyph" in ids["voice"] and "revisit_notate" in ids["modulator"]
    assert {"revisit_signs", "revisit_nib"} <= ids["renderer"]


def test_excursion_closes_on_the_stop():
    rng = np.random.default_rng(3)
    p = np.cumsum(rng.normal(size=(40, 2)), axis=0)
    ex = VR.excursion(p)
    assert np.allclose(ex[0], 0) and np.allclose(ex[-1], 0, atol=1e-9)


def test_holds_on_a_synthetic_speed():
    t = np.arange(100) / 25.0
    v = np.ones(100)
    v[20:35] = 0.01          # 0.56 s hold
    v[60:62] = 0.01          # a flicker: too short
    hs = VR.holds(v, t, still=0.1, min_s=0.25, merge_s=0.1)
    assert len(hs) == 1 and hs[0][0] == 20 and hs[0][1] == 34 and 20 <= hs[0][2] <= 34


def test_figures_are_spliced_and_weighted():
    sheet = kit.run(_recipe())
    assert len(sheet.marks) == 2
    for m in sheet.marks:
        g, r = np.asarray(m["glyph"]), np.asarray(m["r"])
        assert np.all(r[g == 0] == 0)                       # the host stays wire
        if m.meta["figures"]:
            assert r[g > 0].max() > 0.9                     # figures rise into nib
        assert [f["glyph"] for f in m.meta["figures"]] == list(range(1, len(m.meta["figures"]) + 1))


def test_stops_only_draws_the_plain_line_at_the_same_stops():
    a = kit.run(_recipe())
    b = kit.run(_recipe(draw="stops"))
    for ma, mb in zip(a.marks, b.marks):
        assert np.all(np.asarray(mb["glyph"]) == 0)
        assert [f["t_stop"] for f in ma.meta["figures"]] == [f["t_stop"] for f in mb.meta["figures"]]


def test_deterministic():
    a, b = kit.run(_recipe()), kit.run(_recipe())
    assert len(a.inks) == len(b.inks)
    assert all(np.array_equal(x.points, y.points) for x, y in zip(a.inks, b.inks))
    assert {i.meta["colour"] for i in a.inks} == {"#100F0F", "#AF3029"}


def test_operator_notation_at_the_same_stops():
    r = _recipe(draw="stops")
    r["modulators"] = [{"id": "revisit_notate", "source": "stops", "code": "hold=body,end=none", "gap_mm": 0.0}]
    r["renderer"] = {"id": "revisit_signs", "inks": "black,red"}
    s = kit.run(r)
    for m in s.marks:
        evs = m.meta["revisit_events"]
        assert len(evs) == len(m.meta["figures"]) and all(e["op"] == "body" for e in evs)
    assert s.inks


def test_notation_detects_on_the_dance_voice():
    r = {"seed": 5, "frame": [200, 150], "voice": {"id": "dance", "trail": "mantis", "effectors": "hands+head"},
         "modulators": [{"id": "revisit_notate"}], "renderer": {"id": "revisit_signs"}}
    s = kit.run(r)
    kinds = {e["kind"] for m in s.marks for e in m.meta["revisit_events"]}
    assert "end" in kinds and len(kinds) >= 2


def test_parse_code():
    assert MR.parse_code("hold=knot, end=none") == {"hold": "knot"}
    with pytest.raises(ValueError):
        MR.parse_code("hold=vessel")             # an end op cannot sit inside a line
    with pytest.raises(ValueError):
        MR.parse_code("sneeze=knot")
