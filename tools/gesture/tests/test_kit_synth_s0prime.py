"""S0′ (synthesis bench build, 2026-10-19): the ten score-contract gaps round 16 found, plus a list src.

Every addition is opt-in; scores that use none of it play bit-identically (checked against round
16's written scores by `experiments/s0prime_golden.py`, and here on a small scene)."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit._devices import apply_devices  # noqa: E402
from gesture.kit._relations import RelOut, cut, relation  # noqa: E402
from gesture.kit.core import Mark, P, RecipeError  # noqa: E402

FRAME = [200.0, 140.0]


def grid(n=4, renderer_pens=(0.4, 0.4, 0.4), extra=()):
    """Three lines layers: A horizontals, B verticals, C diagonals: many crossings, all predictable."""
    ys = np.linspace(25, 115, n)
    xs = np.linspace(30, 170, n)
    A = [[[10.0, float(y)], [190.0, float(y)]] for y in ys]
    B = [[[float(x), 10.0], [float(x), 130.0]] for x in xs]
    C = [[[10.0 + 30 * i, 130.0], [70.0 + 30 * i, 10.0]] for i in range(n)]
    layers = [{"id": k, "pen": c, "lines": v, "renderer": {"id": "wire", "pen": p}}
              for k, c, v, p in zip("ABC", ("black", "red", "blue"), (A, B, C), renderer_pens)]
    return {"version": 2, "frame": FRAME, "seed": 16900, "layers": layers + list(extra), "relations": []}


def ink_digest(sheet):
    return [(round(float(i.pen), 4), i.meta.get("colour"), np.round(i.points, 6).tobytes()) for i in sheet.inks]


@relation("_s0p_trace", phase="grow", params=[P("dy", "float", 4.0, "", min=-20.0, max=20.0),
                                              P("colour", "str", "")],
          doc="test: copies its src lines shifted down; with a colour, in its own pen")
def _s0p_trace(rctx, src, dst, *, dy, colour):
    meta = {"own_pen": {"colour": colour, "renderer": {"id": "wire", "pen": 0.9}}} if colour else {}
    out = [m.evolve(points=m.points + [0.0, dy], meta=meta) for m in src]
    return RelOut(dst=list(dst) + out, events=[{"outcome": "traced", "n": len(out),
                                                "layers": sorted({m.meta.get("score_layer") for m in src})}])


# 1 · wildcard with exceptions -------------------------------------------------------------------

def test_except_and_role_filters_narrow_a_wildcard():
    s = grid()
    s["layers"][2]["role"] = "mask"
    base = dict(s, relations=[{"id": "R", "kind": "cross", "src": "*", "dst": "*"}])
    pairs = {(e["src"], e["dst"]) for e in synth.played(synth.run(base, cache=False))["log"]}
    assert pairs == {("A", "B"), ("A", "C"), ("B", "C")}
    for extra in ({"except": ["C"]}, {"not_roles": ["mask"]}, {"roles": ["line"]}):
        sh = synth.run(dict(s, relations=[{"id": "R", "kind": "cross", "src": "*", "dst": "*", **extra}]), cache=False)
        assert {(e["src"], e["dst"]) for e in synth.played(sh)["log"]} == {("A", "B")}, extra
    with pytest.raises(RecipeError, match="filter"):
        synth.validate(dict(s, relations=[{"id": "R", "kind": "cross", "src": "A", "dst": "B", "except": ["C"]}]))
    with pytest.raises(RecipeError, match="except"):
        synth.validate(dict(s, relations=[{"id": "R", "kind": "cross", "src": "*", "dst": "*", "except": ["Z"]}]))


# 2 · pen width on marks, and crossing sized by it -------------------------------------------------

def test_marks_carry_their_renderers_pen_width():
    sh = synth.run(grid(renderer_pens=(0.3, 1.2, 0.5)), cache=False)
    by = {m.meta["layer"]: m.meta["pen_mm"] for m in sh.marks}
    assert by == {"A": 0.3, "B": 1.2, "C": 0.5}


def test_crossing_gap_follows_the_over_lines_pen():
    def gaps(pen_from):
        s = grid(n=1, renderer_pens=(0.3, 2.0, 0.3))
        s["layers"] = s["layers"][:2]
        s["relations"] = [{"id": "R", "kind": "crossing", "src": "A", "dst": "B",
                           "params": {"weights": {"gap_under": 1.0}, "jitter": 0.0, "pen_from": pen_from,
                                      "min_dash": 0.0}}]
        return [e["gap_mm"] for e in synth.played(synth.run(s, cache=False))["log"] if "gap_mm" in e]
    assert gaps("param") == [pytest.approx(2 * 0.4 * 2.25, abs=1e-3)]
    assert gaps("marks") == [pytest.approx(2 * 0.3 * 2.25, abs=1e-3)]     # B passes under A: A's pen sets it


# 3 · a dict param -------------------------------------------------------------------------------------

def test_weights_param_type_and_crossing_weights():
    s = grid()
    defaults = {"gap_under": 0.26, "gap_over": 0.22, "cross": 0.30, "stop": 0.10, "sympathy": 0.12}
    a = dict(s, relations=[{"id": "R", "kind": "crossing"}])
    b = dict(s, relations=[{"id": "R", "kind": "crossing", "params": {"weights": defaults}}])
    assert ink_digest(synth.run(a, cache=False)) == ink_digest(synth.run(b, cache=False))
    with pytest.raises(RecipeError, match="unknown key"):
        synth.validate(dict(s, relations=[{"id": "R", "kind": "crossing", "params": {"weights": {"melt": 1.0}}}]))
    with pytest.raises(RecipeError, match="outside"):
        synth.validate(dict(s, relations=[{"id": "R", "kind": "crossing", "params": {"weights": {"cross": 2.0}}}]))
    v = synth.validate(dict(s, relations=[{"id": "R", "kind": "crossing", "params": {"weights": {"cross": 1}}}]))
    assert v["relations"][0]["params"]["weights"] == {"cross": 1.0, "gap_over": 0.0, "gap_under": 0.0,
                                                      "stop": 0.0, "sympathy": 0.0}


# 4 + 5 · a layer made only by relations; marks with their own pen ------------------------------------

def test_relation_only_layer_and_own_pen():
    s = grid(extra=[{"id": "T", "pen": "black", "renderer": {"id": "wire", "pen": 0.2}}])
    s["relations"] = [{"id": "G", "kind": "_s0p_trace", "src": "A", "dst": "T", "params": {"colour": "magenta"}}]
    sh = synth.run(s, cache=False)
    t = [i for i in sh.inks if i.meta["layer"] == "T"]
    assert len(t) == 4 and {i.meta["colour"] for i in t} == {"magenta"} and {round(i.pen, 3) for i in t} == {0.9}
    assert synth.played(sh)["layers"][3]["technique"] == "relations"
    s["relations"][0]["params"] = {}                                   # no own pen: the layer's renderer + pen
    t = [i for i in synth.run(s, cache=False).inks if i.meta["layer"] == "T"]
    assert {i.meta["colour"] for i in t} == {"black"} and {round(i.pen, 3) for i in t} == {0.2}
    with pytest.raises(RecipeError, match="grow relation must draw it"):
        synth.validate(dict(s, relations=[]))


def test_own_pen_marks_render_after_the_layers_own():
    s = grid(extra=[{"id": "T", "pen": "black", "lines": [[[5.0, 5.0], [50.0, 5.0]]]}])
    s["relations"] = [{"id": "G", "kind": "_s0p_trace", "src": "B", "dst": "T", "params": {"colour": "green"}}]
    t = [i.meta["colour"] for i in synth.run(s, cache=False).inks if i.meta["layer"] == "T"]
    assert t == ["black"] + ["green"] * 4


# a list src (bind hears two layers) ----------------------------------------------------------------

def test_grow_relation_hears_a_list_of_layers():
    s = grid(extra=[{"id": "T", "pen": "black"}])
    s["relations"] = [{"id": "G", "kind": "_s0p_trace", "src": ["A", "C"], "dst": "T"}]
    sh = synth.run(s, cache=False)
    ev = next(e for e in synth.played(sh)["log"] if e["relation"] == "G")
    assert ev["n"] == 8 and ev["layers"] == ["A", "C"] and ev["srcs"] == ["A", "C"] and ev["src"] == "A"
    with pytest.raises(RecipeError, match="list src"):
        synth.validate(dict(s, relations=[{"id": "X", "kind": "cross", "src": ["A", "B"], "dst": "C"}]))
    with pytest.raises(RecipeError, match="EARLIER"):
        synth.validate(dict(s, relations=[{"id": "X", "kind": "_s0p_trace", "src": ["A", "T"], "dst": "C"}]))


# 6 · a sheet-wide budget ------------------------------------------------------------------------------

def test_budget_caps_changes_across_every_pair():
    s = grid(n=5)
    rel = {"id": "R", "kind": "crossing", "src": "*", "dst": "*",
           "params": {"weights": {"gap_under": 1.0}, "min_dash": 0.0, "streak": 0.0}}
    free = synth.played(synth.run(dict(s, relations=[rel]), cache=False))["log"]
    assert sum(e["outcome"] == "gap_under" for e in free) > 20
    log = synth.played(synth.run(dict(s, relations=[{**rel, "budget": 7}]), cache=False))["log"]
    assert sum(e["outcome"] not in synth.NEUTRAL for e in log) == 7
    assert any(e["outcome"] == "spent" for e in log) or sum(e["outcome"] == "cross" for e in log) > 0


# 7 · stable mark ids --------------------------------------------------------------------------------

def test_cut_keeps_the_mark_id_and_its_place_on_the_uncut_line():
    m = Mark(np.array([[0.0, 0.0], [100.0, 0.0]]), {}, {"mid": "A:0", "mid_s0": 10.0})
    pieces = cut(m, [(20.0, 30.0), (60.0, 65.0)])
    assert [p.meta["mid"] for p in pieces] == ["A:0"] * 3
    assert [round(p.meta["mid_s0"], 6) for p in pieces] == [10.0, 40.0, 75.0]


def test_events_name_marks_by_stable_id_after_later_cuts():
    s = grid()
    s["relations"] = [{"id": "Y", "kind": "yield", "src": "*", "dst": "*"}]
    log = synth.played(synth.run(s, cache=False))["log"]
    late = [e for e in log if e["dst"] == "C"]
    assert late and all(e["mid"].startswith("C:") and len(e["s_uncut"]) == 2 for e in late)
    # B's marks were cut by its crossings with A before C crossed them: C's events on the src still name
    # B's uncut line, so equal mids on B share one coordinate along it
    on_b = [e for e in log if e["dst"] == "B"]
    assert all(e["s_uncut"][0] <= 120.0 + 1e-6 for e in on_b)


# 8 · counterfactual replay -----------------------------------------------------------------------

def test_replay_drops_relations_by_id_or_kind():
    s = grid()
    s["relations"] = [{"id": "Y", "kind": "yield", "src": "*", "dst": "*"},
                      {"id": "X", "kind": "cross", "src": "*", "dst": "*"}]
    sh = synth.run(s, cache=False)
    bare = synth.run(dict(s, relations=[s["relations"][1]]), cache=False)
    assert ink_digest(synth.replay(sh, drop={"Y"})) == ink_digest(bare)
    assert ink_digest(synth.replay(s, drop_kinds={"yield"})) == ink_digest(bare)
    assert ink_digest(synth.replay(s, keep_only_kinds={"cross"})) == ink_digest(bare)
    assert synth.replay(synth.run(s, cache=False), keep_only=[]).meta["notes"]["score"]["log"] == []


# 9 · stacked beside panels ----------------------------------------------------------------------

def test_stacked_beside_devices_share_one_panel():
    sh = synth.run(dict(grid(), relations=[{"id": "Y", "kind": "yield", "src": "*", "dst": "*"}]), cache=False)
    two = apply_devices(sh, [{"id": "mdoc_census", "place": "beside", "stack": True, "size": 50},
                             {"id": "mdoc_ledger", "place": "beside", "stack": True, "size": 60}])
    assert two.frame == (260.0, 140.0)
    r = [d["region"] for d in two.meta["devices"]]
    assert r[0] == [200.0, 0.0, 60.0, 70.0] and r[1] == [200.0, 70.0, 60.0, 70.0]
    apart = apply_devices(sh, [{"id": "mdoc_census", "place": "beside", "size": 50},
                               {"id": "mdoc_ledger", "place": "beside", "size": 60}])
    assert apart.frame == (310.0, 140.0)                                # unchanged default: one panel each


# 10 · the library measure ---------------------------------------------------------------------------

def test_measure_against_library():
    from gesture.kit import _measure
    if not (_measure.LIB_GEN.exists() and _measure.REAL.exists()):
        pytest.skip("library panel files not built on this machine")
    sh = synth.run({"version": 2, "frame": [250, 175], "seed": 7, "layers": [
        {"id": "A", "part": {"voice": {"id": "hand", "hand": "marden", "length": 6.0}}}]}, cache=False)
    pts = max((m.points for m in sh.marks), key=len)
    r = _measure.against_library(pts, own="marden")
    assert len(r["nearest"]) > 10 and isinstance(r["own_rank"], int)


# default-preserving, on a small scene -------------------------------------------------------------

def test_unused_additions_change_nothing():
    s = grid()
    s["relations"] = [{"id": "R", "kind": "crossing", "src": "*", "dst": "*"},
                      {"id": "S", "kind": "sympathy", "src": "*", "dst": "*"}]
    a = synth.run(s, cache=False)
    b = synth.run(dict(s, relations=[{**r, "except": []} for r in s["relations"]]), cache=False)
    assert ink_digest(a) == ink_digest(b)
