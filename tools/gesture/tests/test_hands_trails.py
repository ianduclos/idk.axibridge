"""hands_trails (round 11): trail / fly / dancer hands in the library and the
voices_trails kit module (trail_sheet, trail_brood, trail_gallery,
trail_specimen). Fast: no extraction, no learning."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit import voices_trails as vt  # noqa: E402

NEW = ("trail_miner", "trail_beetle", "trail_slime", "trail_borer", "trail_oaknet", "trail_grazer", "trail_tracks",
       "fly_open", "fly_fru", "dancer_amber", "dancer_anna", "dancer_cristel", "dancer_madeline", "dancer_marija",
       "dancer_zachary")


def _has(h):
    return L.default().has("hand", h)


def test_registered():
    kit.core.discover()
    assert not {k: v for k, v in kit.DISCOVERY_ERRORS.items() if "voices_trails" in k}
    for kind, mid in (("voice", "trail_sheet"), ("voice", "trail_brood"), ("renderer", "trail_gallery"),
                      ("arranger", "trail_specimen")):
        assert kit.core.get(kind, mid).id == mid


@pytest.mark.parametrize("hid", NEW)
def test_new_hands_load_through_gate(hid):
    if not _has(hid):
        pytest.skip(f"{hid} not in library")
    e = L.entry("hand", hid)
    assert e["policy"] == "generative"
    assert e["provenance"]["training_sheets"]
    assert e["provenance"]["experiment"].startswith("tools/gesture/experiments/hands_trails.py")
    if hid.startswith("fly_"):
        assert e["provenance"]["simulated"] is True and "corpus" not in e["provenance"]
    else:
        assert e["provenance"]["corpus"] in ("earth", "dance")
    g = L.load("hand", hid)
    assert g.strokes and g.name == hid


def test_diwani_not_in_library():
    # learned and measured as evidence, dropped this round: it must not flow into the app on refreeze
    assert not _has("diwani_chancery")


def test_gallery_radius_swells_smoothly_into_chamber():
    s = np.linspace(0, 100, 501)
    h = vt.gallery_radius(s / 100, 0.4, 3.0, 1.6, 2.0, 1.5, s)
    assert h[0] == pytest.approx(0.2)
    assert h[-1] == pytest.approx(0.5 * 2.0 * 3.0)          # chamber radius at the end
    assert np.all(np.diff(h) >= -1e-12)                       # never narrows
    assert np.max(np.abs(np.diff(h, 2))) < 0.05               # no snap into the bead
    h0 = vt.gallery_radius(s / 100, 0.4, 3.0, 1.6, 0.0, 1.5, s)
    assert h0[-1] == pytest.approx(1.5)


def _recipe(seed=7000):
    hand = "trail_miner" if _has("trail_miner") else "lichtenberg"
    return {"frame": [120, 90], "seed": seed, "voice": {"id": "hand", "hand": hand, "length": 1.5},
            "renderer": {"id": "trail_gallery", "pen": 0.3, "w1": 3.0, "chamber": 2.0, "frass": "wander"}}


def test_gallery_deterministic_and_inks_roles():
    a, b = kit.run(_recipe()), kit.run(_recipe())
    assert len(a.inks) == len(b.inks)
    for x, y in zip(a.inks, b.inks):
        assert np.array_equal(x.points, y.points)
    roles = {i.meta.get("role") for i in a.inks}
    assert {"mine", "chamber", "frass"} <= roles
    W, H = a.frame
    P = np.vstack([i.points for i in a.inks])
    assert P.min() >= -1e-6 and P[:, 0].max() <= W + 1e-6 and P[:, 1].max() <= H + 1e-6


def test_specimen_scale_bar_is_paper_mm():
    r = {"frame": [160, 110], "seed": 7001, "arranger": {"id": "trail_specimen", "cols": 2, "bar": 10.0},
         "parts": [{"voice": {"id": "hand", "hand": "lichtenberg", "length": 1.0}} for _ in range(2)],
         "renderer": {"id": "wire", "pen": 0.35}}
    s = kit.run(r)
    bars = [m for m in s.marks if m.meta.get("role") == "scalebar"]
    assert len(bars) == 1
    p = bars[0].points
    assert p[2, 0] - p[1, 0] == pytest.approx(10.0)


def test_brood_ages_and_roles():
    r = {"frame": [120, 90], "seed": 7002,
         "voice": {"id": "trail_brood", "mother": "bubble", "larvae": "lichtenberg", "count": 6,
                   "mother_length": 0.6, "larva_length": 0.2},
         "renderer": {"id": "trail_gallery", "pen": 0.3}}
    s = kit.run(r)
    roles = [m.meta.get("role") for m in s.marks]
    assert roles.count("mother") == 1 and roles.count("larva") >= 4
    for m in s.marks:
        age = m.channel("age")
        assert age is not None and age.min() >= 0 and age.max() <= 1 + 1e-9
    s2 = kit.run(r)
    assert all(np.array_equal(a.points, b.points) for a, b in zip(s.marks, s2.marks))


def test_trail_sheet_many_lines():
    r = {"frame": [120, 90], "seed": 7003, "voice": {"id": "trail_sheet", "hand": "bubble", "lines": 4}}
    s = kit.run(r)
    assert 1 <= len(s.marks) <= 4
