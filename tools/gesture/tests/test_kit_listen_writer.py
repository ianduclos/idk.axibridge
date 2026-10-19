"""S2a (synthesis bench, 2026-10-19): listen's eight kinds as relations, its void, and listen as a score writer."""
import copy
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit import arrangers_listen as al  # noqa: E402
from gesture.kit import core  # noqa: E402
from gesture.kit._relations import get_relation, relation_list  # noqa: E402
from gesture.kit._writers import compose, get_writer, recompose  # noqa: E402
from gesture.kit.relations_listen import KINDS, whole_lines  # noqa: E402
from gesture.kit.writers_listen import AWARE, BALANCE  # noqa: E402

FRAME = [250.0, 175.0]
SEED = 15104


def digest(sheet):
    return [(round(float(i.pen), 4), i.meta.get("colour"), np.round(i.points, 6).tobytes()) for i in sheet.inks]


def outcomes(sheet, rid):
    return [e["outcome"] for e in synth.played(sheet)["log"] if e["relation"] == rid]


def place(cx, cy):
    return {"id": "place", "centre": [cx, cy], "align": 0.0, "tilt": 10.0}


def scene():
    """Two speakers and one layer of every kind, written by hand."""
    hand = lambda h, n: {"id": "hand", "hand": h, "length": n, "joins": "smooth"}  # noqa: E731
    layers = [
        {"id": "S0", "role": "speaker", "pen": "black", "region": [0, 0, 200, 140],
         "part": {"voice": hand("dance_thrusting", 4.0), "modulators": [place(110, 90)],
                  "renderer": {"id": "wire", "pen": 0.6}}},
        {"id": "S1", "role": "speaker", "pen": "blue", "region": [0, 0, 180, 120],
         "part": {"voice": hand("hokusai", 3.5), "modulators": [place(150, 80)], "renderer": {"id": "wire", "pen": 0.4}}},
    ]
    rels = []
    for lid, kind, src, h in (("I", "imitate", "S0", "trail_miner"), ("X", "exaggerate", "S1", "mime_mantis"),
                              ("T", "translate", "I", "river_bend"), ("F", "refuse", "S0", "fly_fru")):
        layers.append({"id": lid, "role": "listener", "pen": "black", "region": [0, 0, 100, 70],
                       "part": {"voice": hand(h, 2.0), "renderer": {"id": "wire", "pen": 0.3}}})
        rels.append({"id": f"R{lid}", "kind": kind, "src": src, "dst": lid, "params": {"heard": "red"}})
    for lid, kind, src in (("E", "echo", "S1"), ("C", "calm", "S0"), ("N", "nest", "S0"), ("B", "bind", ["S0", "S1"])):
        layers.append({"id": lid, "role": kind, "pen": "green", "renderer": {"id": "wire", "pen": 0.3}})
        rels.append({"id": f"R{lid}", "kind": kind, "src": src, "dst": lid,
                     "params": {"second": "src"} if kind == "bind" else {}})
    return {"version": 2, "frame": FRAME, "seed": 17301, "layers": layers, "relations": rels}


@pytest.fixture(scope="module")
def written():
    """One written score per balance stop (same seed)."""
    return {b: compose("listen", frame=FRAME, seed=SEED, params={"balance": b}) for b in BALANCE}


# relations -------------------------------------------------------------------------------------------

def test_relations_and_writer_registered():
    have = {r["id"]: r["phase"] for r in relation_list()}
    for k in KINDS:
        assert have[k] == "grow", k
    assert have["mask"] == "contact"
    assert get_writer("listen").validate({})["balance"] == "one"
    assert "place" in core.registry("modulator")


def test_every_kind_plays_deterministically():
    s = scene()
    a = synth.run(s, cache=False)
    b = synth.run(copy.deepcopy(s), cache=False)
    assert digest(a) == digest(b)
    fired = 0
    for R in s["relations"]:
        out = outcomes(a, R["id"])
        assert out and set(out) <= {R["kind"], "unplaced"}, (R["id"], out)
        fired += R["kind"] in out
    assert fired >= 6
    # a spliced listener: one line (stable mid) whose heard stretch carries its own pen
    i = [m for m in a.marks if m.meta["layer"] == "I"]
    if "imitate" in outcomes(a, "RI"):
        assert {m.meta["mid"] for m in i} == {"I:0"}
        assert any(m.meta.get("own_pen") == {"colour": "red"} for m in i)
        assert {x.meta["colour"] for x in a.inks if x.meta["layer"] == "I"} == {"black", "red"}


def test_whole_lines_rejoin_cut_pieces():
    s = scene()
    s["relations"].append({"id": "Y", "kind": "crossing", "src": "*", "dst": "*",
                           "params": {"weights": {"gap_under": 1.0, "gap_over": 1.0}, "min_dash": 0.0}})
    sh = synth.run(s, cache=False, capture={"S0"})
    pieces = sh.meta["captured"]["S0"]
    lines = whole_lines(pieces)
    assert len(lines) == 1 and len(pieces) >= 1
    assert lines[0][0].length() >= 0.99 * sum(p.length() for p in pieces)


def test_unplaced_listener_draws_nothing():
    s = scene()
    s["relations"][0]["params"].update(box=[0.0, 0.0, 30.0, 30.0], margin=12.0)   # nowhere to lie
    sh = synth.run(s, cache=False)
    assert outcomes(sh, "RI") == ["unplaced"]
    assert not [m for m in sh.marks if m.meta["layer"] == "I"]


def test_mask_cuts_before_and_crosses_after():
    box = [80.0, 50.0, 160.0, 50.0, 160.0, 120.0, 80.0, 120.0, 80.0, 50.0]
    line = lambda y: [[10.0, y], [240.0, y]]  # noqa: E731
    s = {"version": 2, "frame": FRAME, "seed": 1,
         "layers": [{"id": "A", "lines": [line(80.0)]},
                    {"id": "V", "role": "mask", "lines": []},
                    {"id": "B", "lines": [line(100.0)]}],
         "relations": [{"id": "M", "kind": "mask", "src": "V", "dst": "*", "not_roles": ["mask"],
                        "params": {"polygon": box}}]}
    sh = synth.run(s, cache=False)
    a = [m for m in sh.marks if m.meta["layer"] == "A"]
    b = [m for m in sh.marks if m.meta["layer"] == "B"]
    assert len(a) == 2 and len(b) == 1
    assert {(e["dst"], e["outcome"]) for e in synth.played(sh)["log"]} == {("A", "mask"), ("B", "ignore")}
    s["relations"][0]["params"]["flip"] = "A,B"
    sh = synth.run(s, cache=False)
    assert len([m for m in sh.marks if m.meta["layer"] == "A"]) == 1
    assert len([m for m in sh.marks if m.meta["layer"] == "B"]) == 2


# the writer -------------------------------------------------------------------------------------------

def test_every_balance_stop_composes_validates_and_plays(written):
    for b, s in written.items():
        assert synth.validate(s)["layers"]
        sh = synth.run(s)
        assert sh.inks
        parts = [L for L in s["layers"] if "part" in L and L["role"] in ("speaker", "listener")]
        hd = [L["id"] for L in parts if L["part"]["voice"]["id"] == "hdist_zoom"]
        speakers = [L["id"] for L in parts if L["role"] == "speaker"]
        assert s["decisions"]["writers"][0]["decisions"]["distinct"] == hd
        if b == "none":
            assert hd == []
        elif b == "one":
            assert hd == speakers[:1]
        elif b == "speakers":
            assert hd == speakers
        else:
            assert hd == [L["id"] for L in parts]
    # the balance changes voices, never listen's own decisions
    d = [written[b]["decisions"]["writers"][0]["decisions"] for b in BALANCE]
    assert len({(x["colour_mode"], tuple(x["palette"]), x["flow_deg"], x["speakers"]) for x in d}) == 1


def test_writer_is_deterministic(written):
    again = compose("listen", frame=FRAME, seed=SEED, params={"balance": "one"})
    assert again == written["one"]


def test_written_score_opens_with_round15_listens_decisions(written):
    rec = al.recipe(SEED, frame=FRAME)
    r15 = core.run(rec).meta["notes"]["score"]["decisions"]
    d = written["none"]["decisions"]["writers"][0]["decisions"]
    assert (d["palette"], d["colour_mode"], d["bold_mm"], d["flow_deg"]) == \
           (r15["palette"], r15["colour_mode"], r15["bold_mm"], r15["flow_deg"])


def test_awareness_everywhere_but_the_void():
    s = compose("listen", frame=FRAME, seed=15102, params={"mask_p": 1.0})
    void = [L["id"] for L in s["layers"] if L["role"] == "mask"]
    assert len(void) == 1
    aw = [R for R in s["relations"] if R["kind"] in AWARE]
    assert sorted(R["kind"] for R in aw) == sorted(AWARE)
    assert all(R["src"] == "*" and R["dst"] == "*" and R["not_roles"] == ["mask"] for R in aw)
    log = synth.played(synth.run(s))["log"]
    assert not [e for e in log if e["kind"] in AWARE and void[0] in (e["src"], e["dst"])]
    assert any(e["kind"] in AWARE for e in log)
    assert {e["outcome"] for e in log if e["kind"] == "mask"} <= {"mask", "ignore"}
    off = compose("listen", frame=FRAME, seed=15102, params={"mask_p": 1.0, "awareness": False})
    assert not [R for R in off["relations"] if R["kind"] in AWARE]


def _heard_speaker(s):
    roles = {L["id"]: L["role"] for L in s["layers"]}
    rels = s["decisions"]["writers"][0]["decisions"]["relations"]
    r = next(r for r in rels if isinstance(r["src"], str) and roles[r["src"]] == "speaker")
    return r["src"], r["layer"]


def _swap(s, lid, hand):
    s = copy.deepcopy(s)
    s.pop("parts", None)
    for L in s["layers"]:
        if L["id"] == lid:
            L["part"]["voice"]["hand"] = hand
    return s


def test_follow_versus_pinned(written):
    s = written["none"]
    spk, lis = _heard_speaker(s)
    old = next(L for L in s["layers"] if L["id"] == spk)["part"]["voice"]["hand"]
    new = next(h for h in al.LISTEN_HANDS if h != old)

    def geo(score):
        return [m.points for m in synth.run(score, cache=False, capture={lis}).meta["captured"][lis]]

    def same(a, b):
        return len(a) == len(b) and all(x.shape == y.shape and np.allclose(x, y, atol=2e-3) for x, y in zip(a, b))
    before = geo(s)
    assert not same(geo(_swap(s, spk, new)), before)               # Follow: the listener re-places itself
    pinned = synth.pin(s, [lis])
    assert same(geo(_swap(pinned, spk, new)), before)             # pinned: it holds still


def test_recompose_keeps_locked_layers(written):
    s = written["one"]
    spk = next(L["id"] for L in s["layers"] if L["role"] == "speaker")
    pinned = synth.pin(s, [spk])
    again = recompose(pinned, locked=[spk], seed=15299)
    kept = next(L for L in again["layers"] if L["id"] == spk)
    assert kept == next(L for L in pinned["layers"] if L["id"] == spk)
    w = again["decisions"]["writers"][0]
    assert w["seed"] == 15299 and w["decisions"]["kept"] == [spk]
    a = synth.run(pinned, cache=False, capture={spk}).meta["captured"][spk]
    b = synth.run(again, cache=False, capture={spk}).meta["captured"][spk]
    assert len(a) == len(b) and all(np.allclose(x.points, y.points, atol=2e-3) for x, y in zip(a, b))
    others = [L for L in again["layers"] if L["id"] != spk]
    assert others and others != [L for L in s["layers"] if L["id"] != spk]


def test_a_whole_sheet_plays_quickly(written):
    synth.clear_cache()
    t = time.perf_counter()
    synth.run(written["one"], cache=False)
    assert time.perf_counter() - t < 3.0
