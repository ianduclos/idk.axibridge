"""Round-16 contract: the v2 score, the relation registry, the executor, the played log."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesture import kit  # noqa: E402
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit._relations import RelOut, crossings, cut, relation, relation_list  # noqa: E402
from gesture.kit.core import Mark, P, RecipeError  # noqa: E402

FRAME = [200.0, 140.0]


def score(**kw):
    s = {"version": 2, "frame": FRAME, "seed": 16001,
         "layers": [{"id": "A", "pen": "black", "part": {"voice": {"id": "hand", "hand": "marden"}}},
                    {"id": "B", "pen": "red", "part": {"voice": {"id": "hand", "hand": "lichtenberg"}}}],
         "relations": [{"id": "R0", "kind": "yield", "src": "*", "dst": "*"}]}
    s.update(kw)
    return s


def digest(sheet) -> str:
    h = hashlib.sha1()
    for i in sheet.inks:
        h.update(np.round(i.points, 6).tobytes())
        h.update(str(i.meta.get("colour")).encode())
    return h.hexdigest()


@relation("_t16_count", phase="grow", params=[P("n", "int", 1, "", min=0, max=9)], doc="test: logs its src size")
def _t16_count(rctx, src, dst, *, n):
    return RelOut(events=[{"outcome": "heard", "n_src": len(src), "draw": float(rctx.rng("x").random())}])


@relation("_t16_dup", phase="grow", params=[], doc="test: illegal — rewrites the past")
def _t16_dup(rctx, src, dst):
    return RelOut(src=list(src))


def test_registry_lists_reference_relations():
    ids = {r["id"] for r in relation_list()}
    assert {"cross", "yield"} <= ids
    assert next(r for r in relation_list() if r["id"] == "yield")["phase"] == "contact"


def test_run_is_a_sheet_with_layers_tagged():
    sh = synth.run(score(), cache=False)
    assert {m.meta["layer"] for m in sh.marks} == {"A", "B"}
    assert {i.meta["colour"] for i in sh.inks} == {"black", "red"}
    assert all(i.meta["score_layer"] == i.meta["layer"] for i in sh.inks)


def test_layer_seeds_match_v1_parts():
    """A score whose layers are a recipe's parts draws the same lines (no relations)."""
    s = score(relations=[])
    v1 = kit.run({"frame": FRAME, "seed": 16001, "margin": 5.0,
                  "parts": [{"voice": l["part"]["voice"]} for l in s["layers"]]})
    v2 = synth.run(s, cache=False)
    assert len(v1.marks) == len(v2.marks)
    for a, b in zip(v1.marks, v2.marks):
        np.testing.assert_allclose(a.points, b.points)


def test_yield_cuts_the_later_layer_and_logs_every_crossing():
    base = synth.run(score(relations=[{"id": "C", "kind": "cross", "src": "*", "dst": "*"}]), cache=False)
    n_cross = sum(1 for e in synth.played(base)["log"] if e["outcome"] == "cross")
    assert n_cross > 0
    sh = synth.run(score(), cache=False)
    log = synth.played(sh)["log"]
    assert sum(1 for e in log if e["outcome"] == "gap_under") == n_cross
    assert all(e["src"] == "A" and e["dst"] == "B" for e in log)
    a0 = [m for m in base.marks if m.meta["layer"] == "A"]
    a1 = [m for m in sh.marks if m.meta["layer"] == "A"]
    assert len(a0) == len(a1)                          # the earlier layer is untouched
    assert len([m for m in sh.marks if m.meta["layer"] == "B"]) > len([m for m in base.marks if m.meta["layer"] == "B"])


def test_played_score_reads_as_v1_for_devices():
    sh = synth.run(score(), cache=False)
    sc = synth.played(sh)
    assert [l["id"] for l in sc["layers"]] == ["A", "B"]
    r = sc["relations"][0]
    assert r["kind"] == "yield" and r["src"] == "A" and r["dst"] == "B" and r["at"] is not None
    assert sc["written"]["relations"][0]["id"] == "R0"
    from gesture.kit.devices_meas_read import layer_marks
    lm = layer_marks(sh, sc)
    assert lm["A"] and lm["B"]


def test_devices_apply():
    sh = synth.run(score(devices=[{"id": "meas_arcs", "place": "beside"}]), cache=False)
    assert any(i.meta.get("layer") == "device" for i in sh.inks)
    assert sh.frame[0] > FRAME[0]


def test_grow_src_star_hears_earlier_visible_layers_only():
    s = score(base={"lines": [[[10, 10], [190, 130]]]},
              relations=[{"id": "G", "kind": "_t16_count", "src": "*", "dst": "B"}])
    sh = synth.run(s, cache=False)
    ev = [e for e in synth.played(sh)["log"] if e["relation"] == "G"]
    n_a = len([m for m in sh.marks if m.meta["layer"] == "A"])
    assert ev[0]["n_src"] == n_a                       # the unseen base is not in "*"
    assert not any(i.meta["layer"] == "base" for i in sh.inks)
    assert any(m.meta["layer"] == "base" and m.meta["of_role"] == "unseen" for m in sh.marks)


def test_unseen_base_never_inked_and_skipped_by_wildcard():
    s = score(base={"lines": [[[0, 70], [200, 70]], [[100, 0], [100, 140]]]})
    sh = synth.run(s, cache=False)
    log = synth.played(sh)["log"]
    assert all("base" not in (e["src"], e["dst"]) for e in log if e["relation"] == "R0")
    assert not any(i.meta["layer"] == "base" for i in sh.inks)


def test_lines_layer_with_its_own_renderer():
    s = score(layers=[{"id": "W", "pen": "blue", "lines": [[[10, 10], [190, 130]]],
                       "renderer": {"id": "wire", "pen": 1.1}}], relations=[])
    sh = synth.run(s, cache=False)
    assert [round(i.pen, 3) for i in sh.inks] == [1.1]
    with pytest.raises(RecipeError, match="lines layers"):
        synth.validate(score(layers=[dict(score()["layers"][0], renderer={"id": "wire"})]))


def test_named_unseen_layer_is_heard():
    lines = [[[5, y], [195, y]] for y in np.linspace(10, 130, 9)]
    s = score(base={"lines": lines}, relations=[{"id": "Y", "kind": "yield", "src": "base", "dst": "A"}])
    log = synth.played(synth.run(s, cache=False))["log"]
    assert any(e["src"] == "base" and e["dst"] == "A" for e in log)


def test_grow_relation_may_not_rewrite_the_past():
    with pytest.raises(Exception, match="past"):
        synth.run(score(relations=[{"id": "X", "kind": "_t16_dup", "src": "A", "dst": "B"}]), cache=False)


def test_validation_errors():
    with pytest.raises(RecipeError, match="EARLIER"):
        synth.validate(score(relations=[{"id": "X", "kind": "_t16_count", "src": "B", "dst": "A"}]))
    with pytest.raises(RecipeError, match="not a layer"):
        synth.validate(score(relations=[{"kind": "yield", "src": "Z", "dst": "A"}]))
    with pytest.raises(RecipeError, match="unknown relation"):
        synth.validate(score(relations=[{"kind": "nope"}]))
    with pytest.raises(RecipeError):
        synth.validate(score(relations=[{"kind": "yield", "params": {"gap": 99}}]))
    with pytest.raises(RecipeError, match="duplicate"):
        synth.validate(score(layers=[score()["layers"][0], score()["layers"][0]]))


def test_probability_and_silent_events():
    s = score(relations=[{"id": "R0", "kind": "yield", "src": "*", "dst": "*", "p": 0.0}])
    log = synth.played(synth.run(s, cache=False))["log"]
    assert [e["outcome"] for e in log] == ["silent"]


def test_editing_one_relation_rerolls_only_it():
    def draws(sc):
        return {e["relation"]: e["draw"] for e in synth.played(synth.run(sc, cache=False))["log"] if "draw" in e}
    rels = [{"id": "G1", "kind": "_t16_count", "src": "A", "dst": "B", "params": {"n": 1}},
            {"id": "G2", "kind": "_t16_count", "src": "A", "dst": "B", "params": {"n": 1}}]
    a = draws(score(relations=rels))
    rels2 = [dict(rels[0], id="G1b"), rels[1]]
    b = draws(score(relations=rels2))
    assert a["G2"] == b["G2"] and a["G1"] != b["G1b"]


def test_cache_reuses_the_prefix_and_matches_a_cold_run():
    synth.clear_cache()
    s = score(layers=score()["layers"] + [{"id": "C", "pen": "blue", "part": {"voice": {"id": "hand", "hand": "matisse"}}}])
    cold = synth.run(s, cache=False)
    warm1 = synth.run(s)
    assert warm1.meta["cache_hits"] == 0
    s2 = json.loads(json.dumps(s))
    s2["layers"][2]["pen"] = "green"                   # only the last layer changes
    warm2 = synth.run(s2)
    assert warm2.meta["cache_hits"] == 2
    assert digest(cold) == digest(warm1)
    assert digest(synth.run(s2, cache=False)) == digest(warm2)


def test_sealed_composer_layer_is_placed_in_its_region():
    s = score(layers=[score()["layers"][0],
                      {"id": "S", "role": "sealed", "pen": "blue", "region": [110, 20, 80, 60],
                       "composer": {"arranger": {"id": "single"},
                                    "parts": [{"voice": {"id": "hand", "hand": "matisse"}}]}}])
    sh = synth.run(s, cache=False)
    pts = np.vstack([m.points for m in sh.marks if m.meta["layer"] == "S"])
    assert pts[:, 0].min() >= 110 - 1e-6 and pts[:, 0].max() <= 190 + 1e-6
    assert pts[:, 1].min() >= 20 - 1e-6 and pts[:, 1].max() <= 80 + 1e-6
    assert any(i.meta["layer"] == "S" for i in sh.inks)


def test_cut_and_crossings_helpers():
    m = Mark(np.array([[0.0, 0.0], [10.0, 0.0]]))
    pieces = cut(m, [(3.0, 4.0)])
    assert len(pieces) == 2 and abs(pieces[0].length() - 3.0) < 1e-9 and abs(pieces[1].length() - 6.0) < 1e-9
    v = Mark(np.array([[5.0, -5.0], [5.0, 5.0]]))
    xs = crossings([v], [m])
    assert len(xs) == 1 and abs(xs[0].s_dst - 5.0) < 1e-9 and abs(xs[0].s_src - 5.0) < 1e-9


def test_preview_writes_image_and_scores(tmp_path):
    sh = synth.run(score(), cache=False)
    p = synth.preview(sh, tmp_path / "x.jpg", px_per_mm=2)
    assert p.exists() and (tmp_path / "x.recipe.json").exists() and (tmp_path / "x.played.json").exists()
    again = synth.run(json.loads((tmp_path / "x.recipe.json").read_text()), cache=False)
    assert digest(again) == digest(sh)


def test_deterministic_across_processes():
    code = (f"import sys; sys.path.insert(0, {str(ROOT)!r});"
            "import hashlib, json, numpy as np;"
            "from gesture.kit import _synth as s;"
            f"sh = s.run(json.loads({json.dumps(score())!r}), cache=False);"
            "h = hashlib.sha1(b''.join(np.round(i.points, 6).tobytes() for i in sh.inks)).hexdigest();"
            "print(h)")
    outs = set()
    for hs in ("0", "1", "12345"):
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env={**os.environ, "PYTHONHASHSEED": hs}, timeout=300)
        assert p.returncode == 0, p.stderr
        outs.add(p.stdout.strip())
    assert len(outs) == 1
