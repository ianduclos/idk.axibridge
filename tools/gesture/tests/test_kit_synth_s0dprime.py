"""S0″ (synthesis bench build, 2026-10-19): side-specific wildcard filters, shared budgets, and
writers building their palette around locked pens (Ian's answer to the S2 recompose question).

Opt-in like S0′: round 16 replays bit-identically (`experiments/s0prime_golden.py`) and a plain
compose of the S2 writers is unchanged (`experiments/s0dprime_golden.py`)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit._writers import compose, hue, palette_around, recompose  # noqa: E402
from gesture.kit.core import RecipeError  # noqa: E402
from test_kit_synth_s0prime import grid  # noqa: E402

CROSS = {"weights": {"gap_under": 1.0}, "min_dash": 0.0, "streak": 0.0}


def pairs(score):
    return {(e["src"], e["dst"]) for e in synth.played(synth.run(score, cache=False))["log"]}


# side-specific filters ------------------------------------------------------------------------------

def test_dst_except_says_ground_times_mine_but_not_ground_times_ground():
    s = grid()                                   # A, B: "the ground"; C: mine
    rel = {"id": "R", "kind": "cross", "src": "*", "dst": "*"}
    assert pairs(dict(s, relations=[rel])) == {("A", "B"), ("A", "C"), ("B", "C")}
    assert pairs(dict(s, relations=[{**rel, "dst_except": ["A", "B"]}])) == {("A", "C"), ("B", "C")}
    # the symmetric key can't say it: excepting the ground on both sides leaves nothing to pair C with
    assert pairs(dict(s, relations=[{**rel, "except": ["A", "B"]}])) == set()


def test_src_filters_narrow_only_the_heard_side():
    s = grid()
    s["layers"][0]["role"] = "found"
    rel = {"id": "R", "kind": "cross", "src": "*", "dst": "*"}
    assert pairs(dict(s, relations=[{**rel, "src_roles": ["found"]}])) == {("A", "B"), ("A", "C")}
    assert pairs(dict(s, relations=[{**rel, "src_not_roles": ["found"]}])) == {("B", "C")}
    assert pairs(dict(s, relations=[{**rel, "dst_roles": ["found"]}])) == set()     # A is never placed after anyone


def test_side_filters_on_a_named_dst_and_a_grow_relation():
    s = grid()
    named = {"id": "R", "kind": "cross", "src": "*", "dst": "B"}
    assert pairs(dict(s, relations=[named])) == {("A", "B"), ("C", "B")}            # later layers fire too (by design)
    assert pairs(dict(s, relations=[{**named, "src_except": ["C"]}])) == {("A", "B")}
    trace = {"id": "T", "kind": "_s0p_trace", "src": "*", "dst": "C", "params": {"dy": 2.0}}
    sh = synth.run(dict(s, relations=[{**trace, "src_except": ["A"]}]), cache=False)
    ev = [e for e in synth.played(sh)["log"] if e["outcome"] == "traced"]
    assert ev and ev[0]["layers"] == ["B"]


def test_side_filters_validate():
    s = grid()
    with pytest.raises(RecipeError, match="dst_except"):
        synth.validate(dict(s, relations=[{"id": "R", "kind": "cross", "src": "*", "dst": "B", "dst_except": ["A"]}]))
    with pytest.raises(RecipeError, match="src_roles is a list"):
        synth.validate(dict(s, relations=[{"id": "R", "kind": "cross", "src": "*", "dst": "*", "src_roles": "found"}]))
    with pytest.raises(RecipeError, match="src_except is a list of layer ids"):
        synth.validate(dict(s, relations=[{"id": "R", "kind": "cross", "src": "*", "dst": "*", "src_except": ["Z"]}]))


# budget_group ---------------------------------------------------------------------------------------

def test_budget_group_is_shared_by_its_relations():
    s = grid(n=5)
    r1 = {"id": "R1", "kind": "crossing", "src": "*", "dst": "B", "params": CROSS, "budget_group": "pens"}
    r2 = {"id": "R2", "kind": "crossing", "src": "*", "dst": "C", "params": CROSS, "budget_group": "pens"}
    free = dict(s, relations=[{k: v for k, v in r.items() if k != "budget_group"} for r in (r1, r2)])
    n_free = sum(e["outcome"] not in synth.NEUTRAL for e in synth.played(synth.run(free, cache=False))["log"])
    assert n_free > 12
    log = synth.played(synth.run(dict(s, relations=[r1, r2], budget_groups={"pens": 9}), cache=False))["log"]
    assert sum(e["outcome"] not in synth.NEUTRAL for e in log) == 9
    # the tighter of its own budget and the group's
    log = synth.played(synth.run(dict(s, relations=[{**r1, "budget": 2}, r2], budget_groups={"pens": 9}),
                                 cache=False))["log"]
    assert sum(e["outcome"] not in synth.NEUTRAL and e["relation"] == "R1" for e in log) <= 2
    assert sum(e["outcome"] not in synth.NEUTRAL for e in log) <= 9


def test_budget_group_validates():
    s = grid()
    r = {"id": "R", "kind": "crossing", "src": "*", "dst": "*", "params": CROSS, "budget_group": "pens"}
    with pytest.raises(RecipeError, match="budget_groups"):
        synth.validate(dict(s, relations=[r]))
    with pytest.raises(RecipeError, match="budget_groups"):
        synth.validate(dict(s, relations=[r], budget_groups={"pens": -1}))
    assert synth.validate(dict(s, relations=[r], budget_groups={"pens": 3}))["budget_groups"] == {"pens": 3}
    assert "budget_groups" not in synth.validate(s)


# palettes around locked pens --------------------------------------------------------------------------

def test_palette_around_substitutes_by_hue_then_by_slot():
    assert palette_around(["black", "red", "blue"], []) == (["black", "red", "blue"], {})
    assert palette_around(["black", "red"], ["red"]) == (["black", "red"], {})
    assert palette_around(["black", "red-400"], ["red"]) == (["black", "red"], {"red-400": "red"})
    assert palette_around(["black", "blue"], ["purple"]) == (["purple", "blue"], {"black": "purple"})
    pal, m = palette_around(["black"], ["purple", "green"])
    assert pal == ["purple", "green"] and m == {"black": "purple"}
    assert hue("blue-400") == "blue"


@pytest.mark.parametrize("w,seed", [("listen", 15106), ("ccolour", 4545)])
def test_recompose_builds_its_palette_around_the_locked_pen(w, seed):
    s = compose(w, frame=[250, 175], seed=seed)
    roles = ("speaker",) if w == "listen" else ("made",)
    lock = next(L for L in s["layers"] if L["role"] in roles)
    pinned = synth.pin(s, [lock["id"]])
    for new_seed in (15201, 15202, 15203):
        again = recompose(pinned, locked=[lock["id"]], seed=new_seed)
        pal = again["decisions"]["writers"][-1]["decisions"].get("palette") or \
            again["decisions"]["writers"][-1]["decisions"]["pens"]["palette"]
        assert lock["pen"] in pal, (new_seed, lock["pen"], pal)
        inks = {L["pen"] for L in again["layers"] if L["role"] not in ("unseen",)}
        assert lock["pen"] in inks


# the relation's own die ------------------------------------------------------------------------------

def test_relation_seed_rerolls_that_relation():
    s = grid(n=5)
    p = {"weights": {"gap_under": 0.5, "cross": 0.5}, "min_dash": 0.0, "streak": 0.0}
    r1 = {"id": "R1", "kind": "crossing", "src": "*", "dst": "B", "params": p}
    r2 = {"id": "R2", "kind": "crossing", "src": "*", "dst": "C", "params": p}

    def outcomes(rels):
        log = synth.played(synth.run(dict(s, relations=rels), cache=False))["log"]
        return {rid: [e["outcome"] for e in log if e["relation"] == rid] for rid in ("R1", "R2")}
    a = outcomes([r1, r2])
    b = outcomes([{**r1, "seed": 777}, r2])
    assert b["R1"] != a["R1"]                  # (R2 hears the lines R1 changed, so it may move too)
    assert outcomes([{**r1, "seed": s["seed"]}, r2]) == a       # its own seed = the sheet's: unchanged
    with pytest.raises(RecipeError, match="seed"):
        synth.validate(dict(s, relations=[{**r1, "seed": -1}]))


# locks change nothing by themselves (S4) -----------------------------------------------------------------

def _inks(sheet):
    return [(i.meta.get("score_layer"), i.points.tobytes()) for i in sheet.inks]


@pytest.mark.parametrize("w,seed", [("listen", 15102), ("ccolour", 4545)])
def test_locking_any_layer_leaves_the_sheet_unchanged(w, seed):
    """A pin holds a layer as grown (part + grow relations) at full precision, and its contact
    relations still play at its step: what it cut in earlier layers stays cut."""
    s = compose(w, frame=[250, 175], seed=seed)
    base = _inks(synth.run(s, cache=False))
    for L in s["layers"]:
        if L["role"] == "unseen":
            continue
        assert _inks(synth.run(synth.pin(s, [L["id"]]), cache=False)) == base, L["id"]
        assert _inks(synth.run(synth.pin(s, [L["id"]]))) == base, L["id"]      # through the cache too
