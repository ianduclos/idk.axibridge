"""Round-12 keeps (2026-10-18): the found river frozen in the library, and the belt voice."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_oehlen_found as of  # noqa: E402
from gesture.kit import core  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit import voices_belt as vb  # noqa: E402

RESULTS = HERE / "results"
GRWL = HERE.parents[1] / ".local/gesture/corpus/earth/grwl-vec-SB19"


def _river(stems=of.FAR_STEMS, **voice):
    v = {"id": "oehlen_found_river", "tile": "SB19", "rank": 0, "start": 0.0, "span_w": 2400, "angle": 0.0,
         "stems": stems, **voice}
    return {"frame": [205.0, 297.0], "seed": 4441, "arranger": {"id": "single"}, "parts": [{"voice": v}],
            "renderer": {"id": "wire", "pen": 0.3}}


def test_river_stems_entry_is_small_generative_and_decodes():
    e = L.entry("river_stems", of.FAR_STEMS)
    assert e["policy"] == "generative" and e["size_bytes"] < 300_000
    assert "CC BY 4.0" in e["provenance"]["rights"]
    fz = L.load("river_stems", of.FAR_STEMS)
    seg, wm, q = fz["stems"][("SB19", 0)]
    assert q.dtype == np.float64 and q.shape == (9684, 2) and fz["n"]["SB19"] == 25


def test_piece_draws_without_the_corpus(monkeypatch):
    """The Oehlen found-ground piece never reaches the local GRWL corpus."""
    def boom(tile):
        raise AssertionError("the corpus was read")
    monkeypatch.setattr(of, "_stems", boom)
    r = json.loads((RESULTS / "oehlen_found-1-piece.recipe.json").read_text())
    s = kit.run(r)
    assert len(s.inks) == 241
    assert any(i.meta.get("colour") == "blue" for i in s.inks)


def test_rank_beyond_the_tile_clamps_like_the_corpus(monkeypatch):
    monkeypatch.setattr(of, "_stems", lambda tile: (_ for _ in ()).throw(AssertionError("corpus read")))
    a = kit.run(_river(rank=0)).inks[0].points
    with pytest.raises(AssertionError, match="corpus read"):     # rank 3 is not frozen: the corpus is asked
        kit.run(_river(rank=3))
    assert len(a) > 100


@pytest.mark.skipif(not GRWL.exists(), reason="local GRWL corpus not on this machine")
@pytest.mark.parametrize("voice", [{}, {"start": 0.5, "span_w": 1000}, {"angle": -25.0, "span_w": 1600}])
def test_river_from_library_equals_corpus(voice):
    a = kit.run(_river(None, **voice)).inks[0].points
    b = kit.run(_river(**voice)).inks[0].points
    assert np.array_equal(a, b)


def _keeps12():
    spec = importlib.util.spec_from_file_location("keeps12_river_belt",
                                                  HERE / "experiments/keeps12_river_belt.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _belt(**v):
    return {"frame": [280.0, 60.0], "seed": 12407, "arranger": {"id": "single"},
            "parts": [{"voice": {"id": "belt", **v}}], "renderer": {"id": "wire", "pen": 0.35}}


@pytest.mark.parametrize("gain,pull", [(1.0, 0.15), (1.8, 0.25), (2.6, 0.35)])
def test_belt_reproduces_the_keeps12_experiment(gain, pull):
    kb = _keeps12()
    line, _ = kb.hand_line(12407, 8.0)
    exp = kb.belt(kb.kappa_of(line), gain, pull)
    sh = kit.run(_belt(gain=gain, pull=pull))
    s, off = core.fit([exp], (0.175, 0.175, 280.0 - 0.35, 60.0 - 0.35))
    assert np.array_equal(sh.inks[0].points, exp * s + off)


def test_belt_gain_end_equal_is_constant_and_ramp_morphs():
    a = kit.run(_belt()).inks[0].points
    b = kit.run(_belt(gain_end=1.8)).inks[0].points
    c = kit.run(_belt(gain=1.0, gain_end=2.6)).inks[0].points
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c) and len(c) == len(a)
    assert np.array_equal(c, kit.run(_belt(gain=1.0, gain_end=2.6)).inks[0].points)


def test_belt_any_hand():
    s = kit.run(_belt(hand="meander69", length=4.0))
    assert len(s.inks) == 1 and len(s.inks[0].points) > 100
    assert s.inks[0].points[:, 0].min() >= 0 and s.inks[0].points[:, 0].max() <= 280.0


def test_belt_kappa_of_a_circle():
    t = np.linspace(0, 2 * np.pi, 2000)
    k = vb.kappa_of(np.c_[10 * np.cos(t), 10 * np.sin(t)], 0.25)
    assert abs(float(np.median(k)) - 0.1) < 1e-3
