"""voices_corpus (round 9): new hands in the library, the `dance` voice and
the `own_tempo` modulator. Fast: no learning, no extraction."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit import voices_corpus as vc  # noqa: E402

NEW_HANDS = ("dance_staccato", "dance_levitation", "mime_mantis", "aaron", "polygon_walk", "meander69",
             "molnar_letters", "mime_monkey_hands")


def test_registered():
    kit.core.discover()
    assert not {k: v for k, v in kit.DISCOVERY_ERRORS.items() if "voices_corpus" in k}
    assert kit.core.get("voice", "dance").id == "dance"
    assert kit.core.get("modulator", "own_tempo").id == "own_tempo"


@pytest.mark.parametrize("hid", NEW_HANDS)
def test_new_hand_entries_load_through_gate(hid):
    if not L.default().has("hand", hid):
        pytest.skip(f"{hid} not in library")
    e = L.entry("hand", hid)
    assert e["policy"] == "generative"
    assert e["provenance"]["corpus"] in ("dance", "artists")
    assert e["provenance"]["training_sheets"]
    g = L.load("hand", hid)
    assert g.strokes and g.name == hid


def test_phrase_cuts_deterministic_and_gapped():
    rng = np.random.default_rng(0)
    e = np.abs(np.sin(np.linspace(0, 20, 600))) + 0.01 * rng.random(600)
    c1, c2 = vc.phrase_cuts(e, 30.0), vc.phrase_cuts(e.copy(), 30.0)
    assert np.array_equal(c1, c2) and len(c1) > 2
    assert np.all(np.diff(c1) >= int(1.2 * 30))


def _dance_recipe(**v):
    return {"seed": 11, "frame": [120, 90],
            "voice": {"id": "dance", "trail": "mantis", "seconds": 8.0, **v},
            "modulators": [{"id": "own_tempo"}], "renderer": {"id": "wire", "pen": 0.3}}


def test_dance_voice_channels_and_own_tempo():
    if not L.default().has("dance_trail", "mantis"):
        pytest.skip("trail not in library")
    sheet = kit.run(_dance_recipe())
    assert sheet.marks
    for m in sheet.marks:
        assert {"dance_t", "dance_speed", "dance_acc", "r"} <= set(m.channels)
        t = m["dance_t"]
        assert np.all(np.diff(t) >= -1e-6) and t.min() >= 0 and t.max() <= 8.0 + 1e-6
        assert m["r"].min() >= 0 and m["r"].max() <= 2
    r = np.concatenate([m["r"] for m in sheet.marks])
    assert (r < 0.5).mean() > 0.5            # mostly wire, sparse beads
    assert any(m.meta.get("joint") == "head" for m in sheet.marks)
    again = kit.run(_dance_recipe())
    assert all(np.array_equal(a.points, b.points) for a, b in zip(sheet.marks, again.marks))


def test_own_tempo_passes_marks_without_dance_channels():
    sheet = kit.run({"seed": 3, "frame": [100, 80], "voice": {"id": "hand", "hand": "matisse", "length": 1.0},
                     "modulators": [{"id": "own_tempo"}]})
    assert sheet.marks and all("dance_speed" not in m.channels for m in sheet.marks)


def test_effector_sets_and_fit_in_box():
    if not L.default().has("dance_trail", "levitation"):
        pytest.skip("trail not in library")
    sheet = kit.run({"seed": 1, "frame": [100, 100], "margin": 5,
                     "voice": {"id": "dance", "trail": "levitation", "effectors": "hands", "seconds": 6.0,
                               "cut": "none"}})
    joints = {m.meta["joint"] for m in sheet.marks}
    assert joints <= {"lhand", "rhand"}
    P = np.vstack([m.points for m in sheet.marks])
    assert P.min() >= 5 - 1e-6 and P.max() <= 95 + 1e-6


def test_own_tempo_pauses_sparser_than_dwell():
    if not L.default().has("dance_trail", "penguin"):
        pytest.skip("trail not in library")
    share = {}
    for b in ("pauses", "dwell"):
        rec = {"seed": 5, "frame": [120, 90], "voice": {"id": "dance", "trail": "penguin", "seconds": 10.0},
               "modulators": [{"id": "own_tempo", "beads": b}]}
        r = np.concatenate([m["r"] for m in kit.run(rec).marks])
        share[b] = float((r > 1.5).mean())
    assert share["pauses"] < share["dwell"]
    assert share["pauses"] < 0.25
