"""Round 13, thread I-c contagion: a line that catches a regime's grammar (kit/arrangers_contagion.py)."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_contagion as cg  # noqa: E402
from gesture.kit import core  # noqa: E402

RIVER, RULE, TICK = cg.RIVER, cg.RULE, cg.TICK


def _recipe(**arr):
    """The piece's recipe (experiments/contagion.py piece_recipe), written out so the test stands alone."""
    a = {"id": "contagion", "found_boxes": [0.5, 0.27, 0.9, 0.44, -2.5, 0.5, 0.55, 0.95, 0.13, -8.0],
         "late_box": [0.5, 0.55, 0.9, 0.82]}
    a.update(arr)
    return {"frame": [205, 297], "seed": 5302, "margin": 10.0, "arranger": a,
            "parts": [{"voice": {"id": "hand", "hand": "hokusai", "length": 4.0},
                       "modulators": [{"id": "measure_next", "cut": "inflection", "plate": "taxonomy",
                                       "page": "diptych", "families": 5, "straight": "rules+labels",
                                       "hist": "none", "split": 0.6}]},
                      {"voice": {"id": "oehlen_found_river", "tile": "SB19", "rank": 0, "start": 0.0,
                                 "span_w": 2400, "angle": 0.0}},
                      {"voice": {"id": "hand", "hand": "dance_thrusting", "length": 4.0}}],
            "renderer": {"id": "oehlen_found_ink"}}


@pytest.fixture(scope="module")
def piece():
    return kit.run(_recipe())


def _late(sheet):
    return next(m for m in sheet.marks if m.meta.get("of_role") == "late")


def _digest(sheet) -> str:
    h = hashlib.sha256()
    for ink in sheet.inks:
        h.update(np.round(ink.points, 6).tobytes())
    return h.hexdigest()


def test_registered_and_importable():
    core.discover()
    assert not kit.DISCOVERY_ERRORS
    assert "contagion" in core.registry("arranger")


def test_piece_catches_both_regimes_and_carries_them(piece):
    log = piece.marks[0].meta["contagion"]
    assert log["grammars"]["plate"]["angle_deg"] == pytest.approx(-2.5, abs=0.1)
    regs = [f["regime"] for f in log["lines"][0]["infections"]]
    assert {"river", "plate"} <= set(regs)
    codes = np.asarray(_late(piece)["catch"]).astype(int)
    assert set(np.unique(codes)) <= {0, 1, 2, 3, 4, 5}
    assert {RIVER, RULE, TICK} <= set(np.unique(codes))
    assert len([m for m in piece.marks if m.meta.get("of_role") == "late"]) == 1   # one contiguous line


def test_second_regime_caught_while_carrying_the_first(piece):
    inf = piece.marks[0].meta["contagion"]["lines"][0]["infections"]
    overlap = [min(a["end_mm"], b["end_mm"]) - max(a["on_mm"], b["on_mm"])
               for k, a in enumerate(inf) for b in inf[k + 1:] if a["regime"] != b["regime"]]
    assert max(overlap) > 20.0


def test_deterministic_across_processes(piece):
    code = ("import sys; sys.path.insert(0, %r); sys.path.insert(0, %r)\n"
            "import test_kit_contagion as t; from gesture import kit\n"
            "print(t._digest(kit.run(t._recipe())))") % (str(HERE), str(HERE / "tests"))
    outs = set()
    for seed in ("1", "77"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=HERE.parents[1])
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout.strip().splitlines()[-1])
    assert outs == {_digest(piece)}


def test_ride_control_carries_nothing(piece):
    sh = kit.run(_recipe(catch="ride"))
    codes = set(np.unique(np.asarray(_late(sh)["catch"]).astype(int)))
    assert codes & {1, 2}                       # it still rides at contact
    assert not codes & {RIVER, RULE, TICK}      # but nothing is carried
    assert sh.marks[0].meta["contagion"]["lines"][0]["contacts_only"]


def test_river_grammar_recovers_a_sine_generated_curve():
    # a known sine-generated curve: swing 70°, half-bend 5 mm
    s = np.arange(0, 600, 0.05)
    th = np.radians(70.0) * np.sin(np.pi * s / 5.0)
    p = np.cumsum(np.c_[np.cos(th), np.sin(th)] * 0.05, axis=0)
    g = cg.river_grammar([p], calibrate=False)
    assert g["omega_deg_p50"] == pytest.approx(70.0, abs=6.0)
    assert g["halfbend_mm_p50"] == pytest.approx(5.0, abs=0.6)


def test_carried_river_is_fresh_and_keeps_the_grammar(piece):
    g = piece.marks[0].meta["contagion"]["grammars"]["river"]
    xy = cg.gen_meander(np.random.default_rng(1), g, 300.0)
    g2 = cg.river_grammar([xy], calibrate=False)
    assert g2["omega_deg_p50"] == pytest.approx(g["omega_deg_p50"], rel=0.25)
    assert g2["halfbend_mm_p50"] == pytest.approx(g["halfbend_mm_p50"], rel=0.25)
    # carried, not pasted: the piece's carried river lies mostly far from the found river
    from scipy.spatial import cKDTree
    found = np.vstack([m.points for m in piece.marks if str(m.meta.get("found", "")).startswith("grwl")])
    late = _late(piece)
    c = np.asarray(late["catch"]).astype(int)
    d = cKDTree(found).query(late.points[c == RIVER])[0]
    assert np.mean(d > 15.0) > 0.7


def _demo_walk(seed=3, full=30.0, decay=90.0):
    """A straight own path that meets a short found river piece at its start."""
    t = np.linspace(0, 1, 400)
    piece = np.c_[2 + 20 * t, 10 + 0.8 * np.sin(2 * np.pi * t * 4)]
    own = np.c_[np.linspace(0.0, 200.0, 800), np.full(800, 10.0)]
    g = {"river": {"model": "sine-generated", "axis_mm": 10.0, "mu": [np.log(np.radians(80.0)), np.log(4.6)],
                   "cov": [[0.2, 0.05], [0.05, 0.1]], "profile": list((1 - np.cos(np.pi * np.linspace(0, 1, 17))) / 2)}}
    G = cg.Ground([piece], 0.3, tag=1)
    return cg.contagion_walk(own, {"river": G}, g, np.random.default_rng(seed), step=0.3, capture=4.0, align=0.5,
                             listen=400.0, ignore=0.0, ride=8.0, ride_sd=0.1, min_ride=4.0, ride_gap=0.9,
                             return_mm=15.0, ramp=1.0, max_offset=18.0, catches=1,
                             full={"river": full, "plate": 1.0}, decay={"river": decay, "plate": 1.0},
                             tick_linger=1.0, own_mm=6.0, rule_tol=3.5, snap=20.0, tick_pitch=6.3,
                             immune_mm=60.0, omega_max=120.0, regimes=("river",))


def test_way_out_sheds_whole_bends_not_amplitude():
    pts, codes, log = _demo_walk()
    f = log["infections"][0]
    onset_x, full_x, end_x = f["onset"][0], f["full_end"][0], f["end"][0]
    riv = codes == RIVER
    x = pts[:, 0]
    early = riv[(x > onset_x) & (x < full_x)].mean()
    late = riv[(x > full_x + 0.5 * (end_x - full_x)) & (x < end_x)].mean()
    assert early > 0.8 and late < early                       # rarer as it wears off
    amp_early = np.abs(pts[riv & (x < full_x), 1] - 10.0).max()
    amp_late = np.abs(pts[riv & (x > full_x + 10), 1] - 10.0)
    if len(amp_late):
        assert amp_late.max() > 0.5 * amp_early               # what is left is still whole, not shrunk
    assert not riv[x > end_x + 5].any()                       # and then it is gone


def test_unknown_ink_refused():
    with pytest.raises(ValueError):
        kit.run(_recipe(late_ink="nope"))
