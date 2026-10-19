"""S2b (synthesis bench, 2026-10-19): ccolour and arch as score writers, their relations, Follow / pin."""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit._relations import RCtx, get_relation, relation_list  # noqa: E402
from gesture.kit._writers import compose, recompose, writer_list  # noqa: E402
from gesture.kit.core import Mark  # noqa: E402

FRAME = [200.0, 140.0]
MINE = ("paste", "answer", "catch", "cover", "cover_cut", "carry", "ride", "reverse", "contain", "spill", "touch",
        "steer", "flicker")
LIMIT_S = 40.0          # loose: a sheet plays in ~1–6 s on the Mac


def digest(sheet):
    return [(round(float(i.pen), 4), i.meta.get("colour"), np.round(i.points, 5).tobytes()) for i in sheet.inks]


def timed(score):
    t = time.perf_counter()
    sh = synth.run(score, cache=False)
    dt = time.perf_counter() - t
    assert dt < LIMIT_S, f"a sheet took {dt:.1f} s"
    return sh


def kinds(sheet):
    return {e["kind"] for e in synth.played(sheet)["log"] if e["outcome"] not in ("silent", "spent")}


@pytest.fixture(scope="module")
def cc_score():
    return compose("ccolour", frame=FRAME, seed=4545, params={"density": 0.45})


# registry and determinism ---------------------------------------------------------------------------

def test_relations_and_writers_registered():
    ids = {r["id"] for r in relation_list()}
    assert set(MINE) <= ids
    assert {"ccolour", "arch"} <= {w["id"] for w in writer_list()}
    assert get_relation("carry").phase == get_relation("ride").phase == get_relation("reverse").phase == "contact"


def test_compose_and_play_are_deterministic(cc_score):
    again = compose("ccolour", frame=FRAME, seed=4545, params={"density": 0.45})
    assert json.dumps(cc_score, sort_keys=True) == json.dumps(again, sort_keys=True)
    a, b = timed(cc_score), timed(again)
    assert digest(a) == digest(b)
    assert [(e["relation"], e["outcome"]) for e in synth.played(a)["log"]] == \
           [(e["relation"], e["outcome"]) for e in synth.played(b)["log"]]


# both writers, several settings ----------------------------------------------------------------------

@pytest.mark.parametrize("params", [{}, {"density": 0.05, "pens": 1}, {"mode": "mono", "pens": 3, "acts": "core"},
                                    {"colouring": "legend", "awareness": False}])
def test_ccolour_writer_composes_validates_plays(params):
    s = compose("ccolour", frame=FRAME, seed=4546, params=params)
    assert synth.validate(s)["layers"]
    sh = timed(s)
    assert sh.inks and "catch" in kinds(sh)
    roles = {L["role"] for L in s["layers"]}
    assert {"found", "made"} <= roles
    w = s["decisions"]["writers"][0]
    assert w["writer"] == "ccolour" and "pens" in w["decisions"] and "plan" in w["decisions"]
    if params.get("awareness") is False:
        assert not any(R["kind"] == "crossing" for R in s["relations"])
    else:
        assert {"crossing", "sympathy", "hesitate", "accompany", "make_room"} <= {R["kind"] for R in s["relations"]}
    if params.get("colouring") == "legend":
        assert not any(R["kind"] in ("carry", "ride", "reverse", "spill", "touch") for R in s["relations"])


@pytest.mark.parametrize("params", [{}, {"families": "swell", "duet": 1.0}, {"families": "danced,passer"}])
def test_arch_writer_composes_validates_plays(params):
    s = compose("arch", frame=FRAME, seed=15046, params=params)
    sh = timed(s)
    assert sh.inks
    roles = {L["role"] for L in s["layers"]}
    fam = params.get("families", "danced,swell,flicker,passer")
    plan = s["decisions"]["writers"][0]["decisions"]["plan"]
    if "danced" in fam and plan.get("traverse"):
        assert "traverse" in roles and any(R["kind"] == "steer" for R in s["relations"])
    if fam == "swell":
        assert "intruder" in roles
        assert any(R["kind"] == "answer" and R["params"]["by"] == "stress" for R in s["relations"])
        assert "answer" in kinds(sh)
    if "passer" in fam and plan.get("passer"):
        assert "passer" in roles and "container" in roles


# carry / ride / reverse are three relations -------------------------------------------------------

def _rctx(kind, src_id, dst_id, ground, seed=1):
    return RCtx((200.0, 140.0), seed, f"R_{kind}", kind, src_id, dst_id, 3, None, ground, None)


def _scene():
    """A river (found, blue) and a made line (black) that carries the river (code 6) for a stretch, then
    rides the river (code 1) 0.9 mm beside it."""
    x = np.linspace(10, 190, 721)
    F = Mark(np.c_[x, np.full_like(x, 70.0)], {}, {"score_layer": "F", "layer": "F", "of_role": "found",
                                                   "colour": "blue", "found_kind": "river", "mid": "F:0"})
    neg = np.zeros_like(x)
    neg[(x > 30) & (x < 80)] = 6
    neg[(x > 110) & (x < 170)] = 1
    y = np.where(neg == 1, 70.9, 40.0)
    M = Mark(np.c_[x, y], {"neg": neg}, {"score_layer": "M", "layer": "M", "of_role": "made", "colour": "black",
                                         "mid": "M:0"})
    return F, M


def test_carry_ride_reverse_are_distinct():
    F, M = _scene()
    ground = {"F": [F], "M": [M]}
    lend = {"p": 1.0, "p_lie": 0.0, "p_end": 0.0, "min_run": 5.0}
    outs = {}
    for k in ("carry", "ride", "reverse"):
        rel = get_relation(k)
        prm = rel.validate(lend)
        outs[k] = rel.fn(_rctx(k, "F", "M", ground), [F], [M], **prm)
    c, r, v = outs["carry"], outs["ride"], outs["reverse"]
    assert [e["outcome"] for e in c.events] == ["carry"] and c.events[0]["what"] == "river"
    assert [e["outcome"] for e in r.events] == ["ride"]
    assert [e["outcome"] for e in v.events] == ["reverse"]
    # carry and ride lend the river's pen to the LINE; reverse lends the line's pen to the RIVER
    assert c.src is None and r.src is None and v.dst is None
    lent_c = [m for m in c.dst if m.meta.get("lent") == "carry"]
    lent_r = [m for m in r.dst if m.meta.get("lent") == "ride"]
    lent_v = [m for m in v.src if m.meta.get("lent") == "reverse"]
    assert lent_c and lent_r and lent_v
    assert all(m.meta["own_pen"]["colour"] == "blue" for m in lent_c + lent_r)
    assert all(m.meta["own_pen"]["colour"] == "black" for m in lent_v)
    xs_c = np.concatenate([m.points[:, 0] for m in lent_c])
    xs_r = np.concatenate([m.points[:, 0] for m in lent_r])
    assert xs_c.min() >= 29 and xs_c.max() <= 81 and xs_r.min() >= 109 and xs_r.max() <= 171
    # contiguous: the pieces join end to end
    for out in (c.dst, r.dst, v.src):
        for a, b in zip(out[:-1], out[1:]):
            assert np.allclose(a.points[-1], b.points[0])


def test_pen_relations_written_separately_and_logged_by_kind():
    seen = set()
    for seed in (4541, 4542, 4543, 4544):
        s = compose("ccolour", frame=FRAME, seed=seed, params={"pens": 4, "mode": "registers"})
        rels = {R["kind"] for R in s["relations"]}
        on = s["decisions"]["writers"][0]["decisions"]["events_on"]
        if "ride" in on:
            assert "ride" in rels
        if "reverse" in on:
            assert "reverse" in rels
        for R in s["relations"]:
            if R["kind"] in ("carry", "ride", "reverse", "spill", "touch"):
                assert R["budget"] >= 1
        sh = timed(s)
        for e in synth.played(sh)["log"]:
            if e["kind"] in ("carry", "ride", "reverse") and e["outcome"] not in ("silent", "spent"):
                assert e["outcome"] == e["kind"]
                seen.add(e["kind"])
    assert seen, "no pen event fired on four sheets"


# Follow vs pinned, recompose, two writers ------------------------------------------------------------

def _swap(score, lid, hand):
    s = json.loads(json.dumps(score))
    s.pop("parts", None)
    for L in s["layers"]:
        if L["id"] == lid:
            L["part"]["voice"]["hand"] = hand
    return s


def test_edits_follow_and_pins_hold(cc_score):
    hears = {R["dst"]: (R["src"] if isinstance(R["src"], list) else [R["src"]])
             for R in cc_score["relations"] if R["kind"] == "catch"}
    edit = next(L["id"] for L in cc_score["layers"] if L["role"] == "made" and any(L["id"] in v for v in hears.values()))
    follower = next(k for k, v in hears.items() if edit in v)
    cap = {follower}
    before = synth.run(cc_score, cache=False, capture=cap).meta["captured"][follower]
    after = synth.run(_swap(cc_score, edit, "hokusai"), cache=False, capture=cap).meta["captured"][follower]
    assert not (len(before) == len(after) and all(np.allclose(a.points, b.points) for a, b in zip(before, after)))
    pinned = synth.pin(cc_score, [follower])
    held = synth.run(_swap(pinned, edit, "hokusai"), cache=False, capture=cap).meta["captured"][follower]
    pin_pts = [np.asarray(m["points"]) for m in next(L for L in pinned["layers"] if L["id"] == follower)["pin"]["marks"]]
    assert len(held) == len(pin_pts) and all(np.allclose(a.points, b, atol=1e-9) for a, b in zip(held, pin_pts))


def test_recompose_keeps_locked_layers(cc_score):
    made = [L["id"] for L in cc_score["layers"] if L["role"] == "made"]
    lock = made[:1]
    pinned = synth.pin(cc_score, lock)
    again = recompose(pinned, locked=lock, seed=4999)
    L0 = next(L for L in again["layers"] if L["id"] == lock[0])
    assert L0 == next(L for L in pinned["layers"] if L["id"] == lock[0])
    assert again["decisions"]["writers"][0]["seed"] == 4999
    assert again["layers"] != pinned["layers"]
    timed(again)


def test_two_writers_share_a_sheet():
    W, H = 260.0, 160.0
    left = compose("ccolour", frame=[W, H], seed=4547, region=[5, 5, 120, 150], params={"density": 0.3})
    both = compose("arch", frame=[W, H], seed=15047, region=[135, 5, 120, 150], ground=left)
    assert both["seed"] == left["seed"]
    ids = [L["id"] for L in both["layers"]]
    assert ids[:len(left["layers"])] == [L["id"] for L in left["layers"]]
    assert all(i.startswith("w2_") for i in ids[len(left["layers"]):])
    sh = timed(both)
    for L in both["layers"]:
        if L["id"].startswith("w2_") and L.get("region"):
            assert L["region"][0] >= 130 - 1e-6
    first = [L["id"] for L in left["layers"] if L["role"] == "found"][0]
    assert any(i.meta.get("layer") == first for i in sh.inks)      # the left writer's found matter is still drawn
    # the second writer's awareness is over "*": it would hear the first's layers where they met
    cross = next(R for R in both["relations"] if R["id"] == "w2_R_aw_crossing")
    assert cross["src"] == "*" and not set(cross.get("except", ())) & {L["id"] for L in left["layers"]}
    assert [w["writer"] for w in both["decisions"]["writers"]] == ["ccolour", "arch"]
