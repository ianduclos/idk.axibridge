"""Round 16 C `dig`: revivals as v2 relations (pool, restate, tremble, stiffen, knot) + the dig_wet renderer."""
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
from gesture.kit._relations import crossings, relation_list  # noqa: E402

FRAME = [250.0, 175.0]
IDS = ("dig_pool", "dig_restate", "dig_tremble", "dig_stiffen", "dig_knot")


def score(rels, seed=16301, renderer=None, hands=("dance_thrusting", "trail_miner", "river_bend")):
    boxes = ([10, 15, 200, 140], [60, 40, 170, 120], [20, 60, 130, 100])
    lens = (4.0, 3.0, 2.5)
    layers = []
    for i, (h, b, n) in enumerate(zip(hands, boxes, lens)):
        p = {"voice": {"id": "hand", "hand": h, "length": n}}
        if renderer:
            p["renderer"] = renderer
        layers.append({"id": f"L{i}", "pen": ("black", "red", "blue")[i], "region": b, "part": p})
    return {"version": 2, "frame": FRAME, "seed": seed, "layers": layers, "relations": rels}


def digest(sheet) -> str:
    h = hashlib.sha1()
    for i in sheet.inks:
        h.update(np.round(i.points, 6).tobytes())
        h.update(str(i.meta.get("colour")).encode())
    return h.hexdigest()


def layer_marks(sheet, lid):
    return [m for m in sheet.marks if m.meta.get("layer") == lid]


def events(sheet, kind):
    return [e for e in synth.played(sheet)["log"] if e["kind"] == kind and e["outcome"] != "silent"]


def test_registered_and_discovered():
    assert kit.DISCOVERY_ERRORS == {}
    ids = {r["id"]: r for r in relation_list()}
    for i in IDS:
        assert i in ids
    assert ids["dig_restate"]["phase"] == "grow"
    assert all(ids[i]["phase"] == "contact" for i in IDS if i != "dig_restate")
    assert any(m["id"] == "dig_wet" for m in kit.describe()["renderer"])


@pytest.mark.parametrize("kind", IDS)
def test_each_relation_fires_and_is_deterministic(kind):
    src, dst = ("L0", "L1") if kind == "dig_restate" else ("*", "*")
    s = score([{"id": "R", "kind": kind, "src": src, "dst": dst}])
    a, b = synth.run(s, cache=False), synth.run(s, cache=False)
    assert digest(a) == digest(b)
    assert events(a, kind), f"{kind} logged nothing"
    assert all(np.all(np.isfinite(i.points)) for i in a.inks)


def test_pool_single_weight_round_and_at_a_crossing():
    s = score([{"id": "P", "kind": "dig_pool", "src": "*", "dst": "*",
                "params": {"size": 10.0, "roundness": 1.0, "sheet_max": 1, "w_coil": 0.0}}],
              renderer={"id": "dig_wet", "wet": "reference", "fill": "spiral"})
    sh = synth.run(s, cache=False)
    ev = events(sh, "dig_pool")
    assert len(ev) == 1                                 # one weight on the whole sheet, all pairs together
    massy = [m for m in sh.marks if float(np.max(m["r"])) >= 1.99]
    assert len(massy) == 1
    m = massy[0]
    on = m["r"] > 1.2
    s_ = m.arclength()
    assert s_[on].max() - s_[on].min() < 0.8 * 10.0     # a bead, not a capsule
    assert np.min(np.linalg.norm(m.points[on] - np.array(ev[0]["at"]), axis=1)) < 1.0


def test_pool_coil_is_one_contiguous_line_through_the_crossing():
    s = score([{"id": "P", "kind": "dig_pool", "src": "*", "dst": "*",
                "params": {"size": 9.0, "sheet_max": 1, "w_wet": 0.0, "w_coil": 1.0}}])
    sh = synth.run(s, cache=False)
    ev = events(sh, "dig_pool")
    assert ev and ev[0]["how"] == "coil"
    coiled = [m for m in sh.marks if float(np.max(m.channel("pool", 0.0))) > 0.99]
    assert len(coiled) == 1
    m = coiled[0]
    steps = np.linalg.norm(np.diff(m.points, axis=0), axis=1)
    assert steps.max() < 2.0                             # contiguous: no jump
    d = np.linalg.norm(m.points - np.array(ev[0]["at"]), axis=1)
    assert d.min() < 0.5                                 # it winds out from the crossing itself
    assert float(np.max(m["r"])) == 0.0                  # built from line, not ink fill


def test_restate_keeps_own_line_and_adds_restatements_near_the_src():
    s = score([{"id": "R", "kind": "dig_restate", "src": "L0", "dst": "L1",
                "params": {"n": 2, "w_shuttle": 0.0, "w_copies": 1.0, "w_echo": 0.0}}])
    plain = synth.run(score([]), cache=False)
    sh = synth.run(s, cache=False)
    own = layer_marks(plain, "L1")
    got = layer_marks(sh, "L1")
    assert len(got) > len(own)
    np.testing.assert_allclose(got[0].points, own[0].points)
    src_pts = np.vstack([m.points for m in layer_marks(sh, "L0")])
    for m in got:
        if float(np.max(m.channel("restate", 0.0))) > 0:
            d = np.min(np.linalg.norm(m.points[::5, None, :] - src_pts[None, ::3, :], axis=2), axis=1)
            assert np.median(d) < 4.0                    # copies lie nearly on the src's stretch
    assert {e["outcome"] for e in events(sh, "dig_restate")} == {"copies"}


def test_tremble_moves_only_near_the_other_line():
    s = score([{"id": "T", "kind": "dig_tremble", "src": "L0", "dst": "L1",
                "params": {"base": 0.0, "w_still": 0.0, "reach": 4.0}}])
    plain = synth.run(score([]), cache=False)
    sh = synth.run(s, cache=False)
    m = layer_marks(sh, "L1")[0]
    tr = np.abs(m.channel("tremor", 0.0))
    assert tr.max() > 0.05
    src = np.vstack([q.resampled(0.5).points for q in layer_marks(plain, "L0")])
    d = np.min(np.linalg.norm(m.points[::4, None, :] - src[None, :, :], axis=2), axis=1)
    far = d > 4.0 + 6.0                                  # reach plus the easing
    assert np.all(tr[::4][far] < 1e-6)


def test_stiffen_hands_a_stretch_at_the_crossing_to_a_machine():
    s = score([{"id": "S", "kind": "dig_stiffen", "src": "L0", "dst": "L1", "params": {"count": 1}}])
    sh = synth.run(s, cache=False)
    ev = events(sh, "dig_stiffen")
    assert len(ev) == 1
    m = layer_marks(sh, "L1")[0]
    mach = m.channel("machine", 0.0) > 0
    assert mach.any() and not mach.all()
    d = np.linalg.norm(m.points[mach] - np.array(ev[0]["at"]), axis=1)
    assert d.min() < 25.0


def test_knot_loop_holds_the_other_line():
    from shapely.geometry import Point, Polygon
    s = score([{"id": "K", "kind": "dig_knot", "src": "L0", "dst": "L1", "params": {"count": 1, "side_src": 0.0}}])
    plain = synth.run(score([]), cache=False)
    sh = synth.run(s, cache=False)
    ev = events(sh, "dig_knot")
    assert ev and ev[0]["outcome"] == "knot_under"
    m = layer_marks(sh, "L1")[0]
    k = m.channel("knot", 0.0) > 0.5
    ring = m.points[k]
    assert Polygon(ring).buffer(0).contains(Point(ev[0]["at"]))      # the crossing sits inside the loop
    # the src still runs through the crossing point, untouched
    xs = crossings(layer_marks(plain, "L1"), layer_marks(plain, "L0"))
    assert xs


def test_cross_process_determinism():
    code = (
        "import sys, json, hashlib, numpy as np; sys.path.insert(0, %r);"
        "from gesture.kit import _synth as s;"
        "sc = json.loads(%r); sh = s.run(sc, cache=False); h = hashlib.sha1()\n"
        "for i in sh.inks: h.update(np.round(i.points, 6).tobytes())\n"
        "print(h.hexdigest())"
    )
    sc = score([{"id": "P", "kind": "dig_pool", "src": "*", "dst": "*", "params": {"w_coil": 1.0, "w_wet": 0.0}},
                {"id": "T", "kind": "dig_tremble", "src": "*", "dst": "*"},
                {"id": "R", "kind": "dig_restate", "src": "L0", "dst": "L2"}])
    outs = set()
    for seed in ("1", "77"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run([sys.executable, "-c", code % (str(ROOT), json.dumps(sc))], env=env,
                           capture_output=True, text=True, check=True)
        outs.add(r.stdout.strip().splitlines()[-1])
    assert len(outs) == 1
