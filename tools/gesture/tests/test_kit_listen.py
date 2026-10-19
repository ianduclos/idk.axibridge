"""Round 15 thread A `listen`: layers that listen to each other; the score is complete and truthful."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gesture import kit  # noqa: E402
from gesture.kit import arrangers_listen as al  # noqa: E402
from gesture.kit._score import score_of  # noqa: E402

SEEDS = (15101, 15102, 15105, 15111)
OWN = set(al.VOCAB) | {"mask", "ignore", "weave", "yield"}


@pytest.fixture(scope="module")
def sheets():
    return {s: kit.run(al.recipe(s)) for s in SEEDS}


@pytest.fixture(scope="module")
def masked():
    return kit.run(al.recipe(15103, mask_p=1.0))


def _all(sheets, masked):
    return list(sheets.values()) + [masked]


def test_registered_and_recipe_validates():
    assert "listen" in kit.registry("arranger")
    rec = kit.validate(al.recipe(15101))
    assert rec["arranger"]["id"] == "listen" and 0.2 <= rec["arranger"]["density"] <= 0.8


def test_score_is_complete(sheets, masked):
    """Every relation's src and dst is a recorded layer, every drawn mark belongs to a recorded layer,
    every recorded layer except a void with no drawn edge has ink, kinds are the documented ones."""
    for sh in _all(sheets, masked):
        sc = score_of(sh)
        assert sc and sc["version"] == 1
        ids = [l["id"] for l in sc["layers"]]
        assert len(ids) == len(set(ids))
        for r in sc["relations"]:
            assert r["src"] in ids and r["dst"] in ids, r
            assert r["kind"] in OWN, r["kind"]
            assert r["at"] is None or len(r["at"]) == 2
        drawn = {m.meta["layer"] for m in sh.marks}
        assert drawn <= set(ids)
        for l in sc["layers"]:
            if l["role"] == "mask" and l["params"]["edge_runs"] == 0:
                continue
            assert l["id"] in drawn, l
        assert sc["decisions"]["order"] == ids


def test_every_listener_and_later_layer_is_explained(sheets, masked):
    """A layer made by a relation has that relation recorded with it as dst (or as the bind's ligature)."""
    for sh in _all(sheets, masked):
        sc = score_of(sh)
        for l in sc["layers"]:
            kind = l["technique"].split(".")[-1]
            if l["role"] in ("listener", "echo", "calm", "nest"):
                assert any(r["dst"] == l["id"] and r["kind"] == kind for r in sc["relations"]), l
            if l["role"] == "bind":
                assert any(r["kind"] == "bind" and l["id"] in r["note"] for r in sc["relations"])


def test_relations_fire_and_vary(sheets):
    kinds = set()
    for sh in sheets.values():
        rel = [r["kind"] for r in score_of(sh)["relations"] if r["kind"] in al.VOCAB]
        assert len(rel) >= 3                                  # every sheet listens
        for k, cap in al.CAP.items():
            assert rel.count(k) <= cap or k == "refuse"       # refuse records each detour of one refuser
        kinds |= set(rel)
    assert len(kinds) >= 5


def test_deterministic_in_process(sheets):
    again = kit.run(al.recipe(15102))
    a, b = sheets[15102], again
    assert len(a.marks) == len(b.marks)
    assert all(np.array_equal(x.points, y.points) for x, y in zip(a.marks, b.marks))
    assert score_of(a) == score_of(b)


def test_deterministic_across_processes():
    code = ("import sys,hashlib;sys.path.insert(0,%r);import warnings;warnings.filterwarnings('ignore');"
            "from gesture import kit;from gesture.kit import arrangers_listen as al;"
            "s=kit.run(al.recipe(15105));h=hashlib.sha1();"
            "[h.update(m.points.tobytes()) for m in s.marks];print(h.hexdigest())") % str(ROOT)
    outs = set()
    for hs in ("1", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": hs}
        outs.add(subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                                check=True).stdout.strip())
    assert len(outs) == 1


def test_middle_density_never_extreme(sheets):
    for sh in sheets.values():
        W, H = sh.frame
        d = sum(m.length() for m in sh.marks) / (W * H / 100.0)
        assert 3.0 <= d <= 20.0, d
        assert score_of(sh)["decisions"]["density"]["achieved"] <= 20.0


def test_inside_paper_and_no_stubs(sheets, masked):
    for sh in _all(sheets, masked):
        W, H = sh.frame
        for m in sh.marks:
            assert m.points.min() >= 1.0 - 1e-9
            assert (m.points[:, 0] <= W - 1.0 + 1e-9).all() and (m.points[:, 1] <= H - 1.0 + 1e-9).all()
            assert m.length() >= 1.5


def test_overlaps_are_aware(sheets):
    """No two different layers simply cross: every crossing left a gap in one of them."""
    from shapely.geometry import LineString
    for sh in sheets.values():
        by = {}
        for m in sh.marks:
            if m.meta["of_role"] != "mask":
                by.setdefault(m.meta["layer"], []).append(LineString(m.points))
        ids = sorted(by)
        bare = 0
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                for la in by[a]:
                    for lb in by[b]:
                        x = la.intersection(lb)
                        bare += 0 if x.is_empty else 1
        assert bare <= 2, bare                                # end points may graze; crossings never


def test_mask_cuts_who_it_says(masked):
    from shapely import contains_xy
    from shapely.geometry import Polygon
    sc = score_of(masked)
    M = next(l for l in sc["layers"] if l["role"] == "mask")
    P = Polygon(M["params"]["polygon"])
    cut = {r["dst"] for r in sc["relations"] if r["kind"] == "mask"}
    crossed = {r["dst"] for r in sc["relations"] if r["kind"] == "ignore"}
    assert cut and crossed                                     # some layers respect it, some cross it
    for m in masked.marks:
        inside = contains_xy(P, m.points[:, 0], m.points[:, 1]).sum()
        if m.meta["layer"] in cut:
            assert inside <= 2
    assert any(contains_xy(P, m.points[:, 0], m.points[:, 1]).sum() > 4 for m in masked.marks
               if m.meta["layer"] in crossed)


def test_score_s_ranges_find_their_stretch(sheets):
    """`s` on a spliced relation names a stretch of the dst layer's drawn ink (via mark meta s0)."""
    from gesture.kit.arrangers_oehlen_found import arclen
    n = 0
    for sh in sheets.values():
        sc = score_of(sh)
        for r in sc["relations"]:
            if r["kind"] not in ("imitate", "exaggerate", "translate") or not r["s"]:
                continue
            hit = 0
            for m in sh.marks:
                if m.meta["layer"] == r["dst"] and m.meta.get("s0") is not None:
                    s = m.meta["s0"] + arclen(m.points)
                    hit += int(((s >= r["s"][0]) & (s <= r["s"][1])).sum())
            assert hit > 0, r
            n += 1
    assert n >= 4


# --- the mechanisms ---------------------------------------------------------

def _wave(n=240, amp=6.0):
    x = np.linspace(0, 80, n)
    return np.c_[x, amp * np.sin(x / 8.0)]


def test_amplify_pushes_the_same_shape():
    g = al.resample(_wave(), al.STEP)
    q = al.amplify(g, 2.0, 1.3)
    assert np.ptp(q[:, 1]) > 2.0 * np.ptp(g[:, 1])
    # same shape: the sign pattern of the sideways excursion is kept
    gy = np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(g)), g[:, 1] - g[:, 1].mean())
    qy = np.interp(np.linspace(0, 1, 50), np.linspace(0, 1, len(q)), q[:, 1] - q[:, 1].mean())
    assert np.corrcoef(gy, qy)[0, 1] > 0.95


def test_calm_lands_on_the_gesture_ends():
    g = al.resample(_wave(), al.STEP)
    q = al.similar_to(al.push(g, 0.2, 1.0, trend_mm=0.0), g[0], g[-1])
    assert np.allclose(q[0], g[0]) and np.allclose(q[-1], g[-1])
    assert al.turning(q) < 0.5 * al.turning(g)


def test_translate_styles_keep_the_course():
    g = al.resample(_wave(), al.STEP)
    for q in (al.ruled(g, 1.5), al.meander(g, 1.0, 6.0, 6.0)):
        assert np.linalg.norm(q[-1] - g[-1]) < 6.0
    assert len(al.ruled(g, 1.5)) > 10


def test_refuse_walks_the_halo():
    from shapely.geometry import LineString
    src = np.c_[np.linspace(40, 60, 41), np.full(41, 50.0)]       # a short stroke: a way round exists
    line = np.c_[np.full(201, 50.0) + np.linspace(-20, 20, 201), np.linspace(10, 90, 201)]
    out, where = al.detour(al.resample(line, al.STEP), [src], 4.0)
    assert where and out is not None
    assert LineString(out).distance(LineString(src)) >= 4.0 - 0.3


def test_echo_never_larger_than_what_it_echoes(sheets):
    for sh in sheets.values():
        for l in score_of(sh)["layers"]:
            if l["role"] == "echo":
                assert l["params"]["scale"] <= 1.0
