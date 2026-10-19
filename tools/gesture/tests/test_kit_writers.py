"""S2 contract (2026-10-19): per-layer seeds, pinned (locked) layers, score writers (compose / recompose)."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit._relations import RelOut, relation  # noqa: E402
from gesture.kit._writers import compose, recompose, writer, writer_list  # noqa: E402
from gesture.kit.core import KitError, P, RecipeError  # noqa: E402

FRAME = [200.0, 140.0]
HANDS = ("marden", "lichtenberg", "matisse")


def inks_of(sheet, layer):
    return [i.points for i in sheet.inks if i.meta.get("layer") == layer]


def same(a, b, tol=0.0):
    return len(a) == len(b) and all(x.shape == y.shape and np.allclose(x, y, atol=tol, rtol=0) for x, y in zip(a, b))


@relation("_t2_beside", phase="grow", params=[P("dx", "float", 6.0, "", min=-50.0, max=50.0)],
          doc="test: the dst's own line moved to start beside the src's first point")
def _t2_beside(rctx, src, dst, *, dx):
    if not src or not dst:
        return RelOut()
    shift = src[0].points[0] + [dx, 0.0] - dst[0].points[0]
    return RelOut(dst=[m.evolve(points=m.points + shift) for m in dst], events=[{"outcome": "placed"}])


def three(hand_a="marden"):
    return {"version": 2, "frame": FRAME, "seed": 17001,
            "layers": [{"id": "A", "pen": "black", "part": {"voice": {"id": "hand", "hand": hand_a}}},
                       {"id": "B", "pen": "red", "part": {"voice": {"id": "hand", "hand": "lichtenberg"}}},
                       {"id": "C", "pen": "blue", "part": {"voice": {"id": "hand", "hand": "matisse"}}}],
            "relations": [{"id": "G", "kind": "_t2_beside", "src": "A", "dst": "B"},
                          {"id": "X", "kind": "crossing", "src": "*", "dst": "*"}]}


# per-layer seed -------------------------------------------------------------------------------------

def test_layer_seed_rerolls_one_layer_only():
    s = {**three(), "relations": three()["relations"][:1]}         # no crossings: C can't touch A
    base = synth.run(s, cache=False)
    s2 = {**three(), "relations": three()["relations"][:1]}
    s2["layers"][2]["seed"] = 17001 + 2                               # = the default: nothing changes
    assert same(inks_of(synth.run(s2, cache=False), "C"), inks_of(base, "C"))
    s2["layers"][2]["seed"] = 99
    other = synth.run(s2, cache=False)
    assert not same(inks_of(other, "C"), inks_of(base, "C"))
    assert same(inks_of(other, "A"), inks_of(base, "A"))
    with pytest.raises(RecipeError, match="seed"):
        synth.validate({**s, "layers": [{**s["layers"][0], "seed": -1}] + s["layers"][1:]})


# pin -------------------------------------------------------------------------------------------------

def test_pin_holds_a_layer_still_when_its_source_changes():
    s = three()
    pinned = synth.pin(s, ["B"])
    L = next(x for x in pinned["layers"] if x["id"] == "B")
    assert L["lock"] and L["pin"]["marks"] and L["seed"] == 17001 + 1
    a = synth.run(s, cache=False)
    b = synth.run(pinned, cache=False)
    assert same(inks_of(b, "B"), inks_of(a, "B"), tol=2e-3)          # pinning draws the same sheet
    edited = dict(pinned, layers=[{**pinned["layers"][0], "part": {"voice": {"id": "hand", "hand": "matisse"}}}]
                  + pinned["layers"][1:])
    free = dict(s, layers=[{**s["layers"][0], "part": {"voice": {"id": "hand", "hand": "matisse"}}}] + s["layers"][1:])
    # B as it stands after its own step (later layers may still cut it, as they would any layer)
    b_pinned = [m.points for m in synth.run(edited, cache=False, capture={"B"}).meta["captured"]["B"]]
    b_free = [m.points for m in synth.run(free, cache=False, capture={"B"}).meta["captured"]["B"]]
    b0 = [np.asarray(m["points"]) for m in L["pin"]["marks"]]
    assert same(b_pinned, b0, tol=1e-9)                              # pinned: A's new hand doesn't move it
    assert not same(b_free, b0, tol=1e-3)                             # unpinned, it follows its source


def test_pin_keeps_channels_and_marks_tagged():
    s = three()
    pinned = synth.pin(s, ["A"])
    sh = synth.run(pinned, cache=False)
    m = next(x for x in sh.marks if x.meta["layer"] == "A")
    assert m.meta["colour"] == "black" and m.meta["mid"].startswith("A:") and set(m.channels)


def test_pin_on_a_sealed_layer_freezes_its_seed_only():
    s = {**three(), "layers": three()["layers"][:1] + [
        {"id": "S", "role": "sealed", "pen": "blue", "region": [110, 20, 80, 60],
         "composer": {"arranger": {"id": "single"}, "parts": [{"voice": {"id": "hand", "hand": "matisse"}}]}}],
         "relations": []}
    p = synth.pin(s, ["S"])
    S = p["layers"][1]
    assert S["lock"] and S["seed"] == 17001 + 1 and "pin" not in S
    with pytest.raises(RecipeError, match="seed, not a pin"):
        synth.validate({**s, "layers": [s["layers"][0], {**s["layers"][1], "pin": {"marks": []}}]})


# writers ------------------------------------------------------------------------------------------

@writer("_t2_pair", params=[P("hand", "choice", "marden", "", choices=HANDS),
                            P("n", "int", 2, "how many layers", min=1, max=3)],
        doc="test: n hand layers in the region, each hearing the one before")
def _t2_pair(wctx, *, hand, n):
    rng = wctx.rng("hands")
    keep = {L["id"]: L for L in wctx.keep}
    x, y, w, h = wctx.region
    layers, rels = [], []
    for i in range(n):
        lid = wctx.id(f"L{i}")
        if lid in keep:
            layers.append(keep[lid])
        else:
            hd = hand if i == 0 else HANDS[int(rng.integers(len(HANDS)))]
            layers.append({"id": lid, "role": "speaker" if i == 0 else "listener", "pen": "black",
                           "region": [x, y, w, h], "part": {"voice": {"id": "hand", "hand": hd}},
                           "seed": int(rng.integers(1, 10**6))})
        if i:
            rels.append({"id": wctx.id(f"R{i}"), "kind": "_t2_beside", "src": layers[i - 1]["id"], "dst": lid})
    sh = wctx.play({"layers": layers, "relations": rels})                  # writers may read geometry
    return {"layers": layers, "relations": rels, "decisions": {"n": n, "marks": len(sh.marks)}}


def test_compose_writes_a_playable_score_and_records_the_writer():
    s = compose("_t2_pair", frame=FRAME, seed=17100, params={"n": 3})
    assert [L["id"] for L in s["layers"]] == ["L0", "L1", "L2"]
    w = s["decisions"]["writers"][0]
    assert w["writer"] == "_t2_pair" and w["prefix"] == "" and w["params"] == {"hand": "marden", "n": 3}
    assert w["decisions"]["n"] == 3 and w["layers"] == ["L0", "L1", "L2"]
    assert len(synth.run(s).inks) >= 3
    assert any(x["id"] == "_t2_pair" for x in writer_list())


def test_two_writers_share_a_sheet_without_rerolling_the_ground():
    left = compose("_t2_pair", frame=FRAME, seed=17100, region=[5, 5, 90, 130])
    both = compose("_t2_pair", frame=FRAME, seed=555, region=[105, 5, 90, 130], ground=left)
    assert both["seed"] == left["seed"]
    assert [L["id"] for L in both["layers"]] == ["L0", "L1", "w2_L0", "w2_L1"]
    a, b = synth.run(left, cache=False), synth.run(both, cache=False)
    assert same(inks_of(b, "L0"), inks_of(a, "L0"))


def test_recompose_keeps_locked_layers_and_rewrites_the_rest():
    s = compose("_t2_pair", frame=FRAME, seed=17100, params={"n": 3})
    s = synth.pin(s, ["L1"])
    again = recompose(s, locked=["L1"], seed=17999)
    L1 = next(L for L in again["layers"] if L["id"] == "L1")
    assert L1 == next(L for L in s["layers"] if L["id"] == "L1")
    assert next(L for L in again["layers"] if L["id"] == "L2") != next(L for L in s["layers"] if L["id"] == "L2")
    assert again["decisions"]["writers"][0]["seed"] == 17999
    with pytest.raises(RecipeError, match="not layers this writer wrote"):
        recompose(s, locked=["nope"], seed=1)


def test_compose_checks_prefixes_and_locks():
    @writer("_t2_bad", params=[], doc="test: forgets its prefix")
    def _t2_bad(wctx):
        return {"layers": [{"id": "Z", "part": {"voice": {"id": "hand", "hand": "marden"}}}], "relations": []}
    left = compose("_t2_pair", frame=FRAME, seed=1, region=[5, 5, 90, 130])
    with pytest.raises(KitError, match="prefix"):
        compose("_t2_bad", frame=FRAME, seed=2, ground=left)

    @writer("_t2_drop", params=[], doc="test: drops what Ian locked")
    def _t2_drop(wctx):
        return {"layers": [{"id": "L9", "part": {"voice": {"id": "hand", "hand": "marden"}}}], "relations": []}
    with pytest.raises(KitError, match="dropped locked"):
        compose("_t2_drop", frame=FRAME, seed=2, keep=[{"id": "L0", "part": {"voice": {"id": "hand", "hand": "marden"}}}])
