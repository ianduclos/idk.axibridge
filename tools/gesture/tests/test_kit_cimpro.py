"""Round 14 b2 `cimpro`: the composer as improviser (perceive → decide → act)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_cimpro as ci  # noqa: E402

FAST = 14010          # a sparse sheet (low appetite): runs in about a second


def _recipe(seed=FAST, **arr):
    return {"frame": [300.0, 200.0], "seed": seed, "margin": 0.0, "arranger": {"id": "cimpro", **arr},
            "parts": [{"voice": {"id": "hand", "hand": "river_bend", "length": 3.0}}],
            "renderer": {"id": "oehlen_found_ink", "pen": 0.4}}


def _log(sheet):
    return sheet.marks[0].meta["cimpro"]["log"]


def _digest(sheet) -> str:
    h = hashlib.sha256()
    for ink in sheet.inks:
        h.update(np.round(ink.points, 6).tobytes())
        h.update(str(ink.pen).encode())
    return h.hexdigest()


@pytest.fixture(scope="module")
def sheet():
    return kit.run(_recipe())


def test_registered_and_runs(sheet):
    assert "cimpro" in kit.core.registry("arranger")
    assert sheet.inks
    log = _log(sheet)
    assert log and all(e["verb"] in ci.VERBS for e in log)
    assert all("why" in e for e in log)
    # every move but the last names what it did; the run ends by deciding to stop (or at the cap)
    assert all(e.get("what") for e in log if e["verb"] != "stop")


def test_every_mark_is_inked_by_its_meta(sheet):
    for m in sheet.marks:
        assert m.meta["part"] == 0
        assert m.meta["ink"] in ci.FLEXOKI
        assert 0.05 <= m.meta["pen"] <= 3.0


def test_nothing_drawn_on_the_frame_edge(sheet):
    """Lines that leave are cut ragged inside the inner frame: no stray marks along the edge."""
    W, H = sheet.frame
    for ink in sheet.inks:
        p = ink.points
        assert p[:, 0].min() >= 7.0 - 1e-6 and p[:, 0].max() <= W - 7.0 + 1e-6
        assert p[:, 1].min() >= 7.0 - 1e-6 and p[:, 1].max() <= H - 7.0 + 1e-6


def test_upto_is_a_prefix_of_the_same_run(sheet):
    full = _log(sheet)
    n = min(3, len(full) - 1)
    part = _log(kit.run(_recipe(upto=n)))
    assert [(e["verb"], e.get("what")) for e in part] == [(e["verb"], e.get("what")) for e in full[:n]]


def test_deterministic_across_processes():
    code = ("import sys, json, hashlib, numpy as np; sys.path.insert(0, 'tools/gesture');"
            "from gesture import kit;"
            f"s = kit.run(json.loads({json.dumps(json.dumps(_recipe()))}));"
            "h = hashlib.sha256();"
            "[ (h.update(np.round(i.points, 6).tobytes()), h.update(str(i.pen).encode())) for i in s.inks ];"
            "print(h.hexdigest())")
    outs = set()
    for hs in ("0", "123"):
        env = {**os.environ, "PYTHONHASHSEED": hs}
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                           timeout=300)
        assert r.returncode == 0, r.stderr[-2000:]
        outs.add(r.stdout.strip().splitlines()[-1])
    assert len(outs) == 1
    assert outs == {_digest(kit.run(_recipe()))}


def test_population_is_not_one_template():
    """Different seeds: different openings, move sequences and move counts (cheap verbs only)."""
    seqs, counts = set(), set()
    for s in range(14301, 14307):
        log = _log(kit.run(_recipe(s, allow="found,seed,traverse,intrude,cover,cross,trail,reserve,answer,stop",
                                   moves_max=12)))
        seqs.add(tuple(e["verb"] for e in log[:4]))
        counts.add(len(log))
    assert len(seqs) >= 4
    assert len(counts) >= 2


def test_allow_restricts_the_moves():
    log = _log(kit.run(_recipe(14302, allow="seed,thicken,stop", moves_max=8)))
    assert {e["verb"] for e in log} <= {"seed", "thicken", "stop"}


# --- perception -------------------------------------------------------------

def _state_with_core(xy=(220.0, 60.0), r=12.0, n=40, seed=0):
    rng = np.random.default_rng(seed)
    S = ci.SheetState((300.0, 200.0), (7.0, 7.0, 293.0, 193.0))
    for _ in range(n):
        c = np.array(xy) + rng.normal(0, r / 2, 2)
        t = np.linspace(0, 2 * np.pi, 40)
        S.add(np.c_[c[0] + r / 3 * np.cos(t), c[1] + r / 3 * np.sin(t)], pen=0.3, ink="black", role="made",
              reg="hand", move=0)
    return S


def test_look_finds_the_core_and_the_blank():
    S = _state_with_core()
    per = ci.look(S, 4.0)
    cx, cy = per["core"]["xy"]
    assert abs(cx - 220) < 10 and abs(cy - 60) < 10
    bx, by = per["blank"]["xy"]
    assert np.hypot(bx - 220, by - 60) > 80          # the largest blank is away from the core
    assert per["core"]["share"] > 0.8
    assert per["settled"] > 0.5                       # one lone core: the eye rests on it


def test_a_competing_density_unsettles_the_sheet():
    S = _state_with_core()
    lone = ci.look(S, 4.0)["settled"]
    S2 = _state_with_core()
    for d in _state_with_core(xy=(60.0, 150.0), seed=1).lines:
        S2.lines.append(d)
    per = ci.look(S2, 4.0)
    assert per["core2"] is not None
    assert per["settled"] < lone


def test_look_is_cheap():
    import time
    S = _state_with_core(n=400)
    t = time.perf_counter()
    for _ in range(5):
        ci.look(S, 4.0)
    assert (time.perf_counter() - t) / 5 < 0.25


# --- decision ----------------------------------------------------------------

def _temper(seed=1):
    return ci.temperament(np.random.default_rng(seed), None, 3)


def test_decision_is_stochastic_and_state_dependent():
    S = _state_with_core()
    per = ci.look(S, 4.0)
    T = _temper()
    verbs = {ci.decide(S, per, T, 5, np.random.default_rng(i), min_moves=4, moves_max=60)[0] for i in range(60)}
    assert len(verbs) >= 4                            # the same state leads to different moves
    empty = ci.SheetState((300.0, 200.0), (7.0, 7.0, 293.0, 193.0))
    pe = ci.look(empty, 4.0)
    opening = {ci.decide(empty, pe, T, 0, np.random.default_rng(i), min_moves=4, moves_max=60)[0] for i in range(60)}
    assert opening <= {"found", "seed", "traverse", "sign", "reserve", "ladder"}
    assert "thicken" not in opening and "intrude" not in opening   # nothing to thicken or intrude on yet


def test_an_uncrossed_cover_invites_a_crossing():
    S = _state_with_core()
    S.covers.append({"poly": np.array([[0, 0], [1, 0], [1, 1], [0, 0]], float), "xy": [0, 0], "crossed": False})
    per = ci.look(S, 4.0)
    T = _temper()
    verbs = [ci.decide(S, per, T, 5, np.random.default_rng(i), min_moves=4, moves_max=60)[0] for i in range(80)]
    assert verbs.count("cross") >= 5


def test_habituation_lets_go_of_a_repeated_move():
    S = _state_with_core()
    per = ci.look(S, 4.0)
    T = _temper()
    T["verbs"]["thicken"] = 5.0
    base = [ci.decide(S, per, T, 5, np.random.default_rng(i), min_moves=4, moves_max=60)[0] for i in range(120)]
    S.log = [{"verb": "thicken"}] * 4
    bored = [ci.decide(S, per, T, 5, np.random.default_rng(i), min_moves=4, moves_max=60)[0] for i in range(120)]
    assert bored.count("thicken") < base.count("thicken")


# --- acts ----------------------------------------------------------------------

def _ctx():
    from gesture.kit import core, library
    return core.Ctx((300.0, 200.0), (0.0, 0.0, 300.0, 200.0), 1, 1, -1, "arranger", "cimpro",
                    core._Run(library.default()))


def test_intruder_is_heavy_and_cuts_the_core_edge():
    hits = 0
    for i in range(12):
        S = _state_with_core()
        per = ci.look(S, 4.0)
        T = _temper(i)
        rng = np.random.default_rng(100 + i)
        what = ci.act_intrude(_ctx(), S, per, T, rng, 3, step=0.35, heavy=(1.6, 2.8))
        if "knot" in what:
            continue
        heavy = [d for d in S.lines if d["role"] == "heavy"]
        assert heavy and all(d["pens"].min() >= 1.6 for d in heavy)
        P_ = np.vstack([d["pts"] for d in heavy])
        r = np.hypot(*(P_ - np.array(per["core"]["xy"])).T)
        rc = per["core"]["r"]
        # it sits at the edge: some of it inside the core's radius, some outside
        if r.min() < rc and r.max() > rc:
            hits += 1
    assert hits >= 5


def test_offset_passes_is_one_contiguous_line():
    path = np.array([[0.0, 0.0], [40.0, 0.0], [40.0, 20.0]])
    q = ci.offset_passes(path, 6.0, 2.0)
    assert q.ndim == 2 and len(q) > len(path)
    steps = np.linalg.norm(np.diff(q, axis=0), axis=1)
    assert steps.max() < 45.0                          # the passes are joined end to end, no lifts implied


def test_clip_ragged_pulls_cut_ends_back():
    rng = np.random.default_rng(0)
    line = np.c_[np.linspace(-50, 150, 400), np.full(400, 50.0)]
    pieces = ci.clip_ragged(line, (0.0, 0.0, 100.0, 100.0), rng)
    assert len(pieces) == 1
    p = pieces[0]
    assert p[:, 0].min() >= 3.0 - 0.6 and p[:, 0].max() <= 97.0 + 0.6


def test_place_along_keeps_the_grammar_whole():
    t = np.linspace(0, 6 * np.pi, 600)
    l = np.c_[t * 5, 8 * np.sin(t)]
    out = ci.place_along([l], (10.0, 10.0), (110.0, 10.0), max_half=2.0)[0]
    # a similarity (never squeezed): every distance scales by the same factor
    i, j = np.random.default_rng(0).integers(0, len(l), (2, 200))
    ok = i != j
    r = np.linalg.norm(out[i] - out[j], axis=1)[ok] / np.linalg.norm(l[i] - l[j], axis=1)[ok]
    assert np.ptp(r) < 1e-6 * r.mean() + 1e-9
    assert np.abs(out[:, 1] - 10.0).max() <= 2.0 + 1e-6      # the lateral cap shortens it instead
    assert abs(out[:, 0].min() - 10.0) < 0.5                # laid from A along AB
