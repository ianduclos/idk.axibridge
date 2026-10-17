"""combo_search: the recipe sampler, breeding, and the selector's proxies."""
from __future__ import annotations

import copy
import json

import numpy as np
from experiments import combo_search as cs
from gesture import kit
from gesture.kit.core import Ink, Sheet


def _wire_hands(rec):
    return set().union(*[cs._hands_of(p) for p in rec["parts"][1:]])


def test_sampler_valid_deterministic_and_distinct():
    a = [cs.sample_recipe(np.random.default_rng(5)) for _ in range(2)]
    assert json.dumps(a[0], sort_keys=True) == json.dumps(a[1], sort_keys=True)
    rng = np.random.default_rng(11)
    for _ in range(60):
        rec = cs.sample_recipe(rng)
        kit.validate(rec)                                   # every candidate is a valid recipe
        assert 2 <= len(rec["parts"]) <= 3
        assert not (cs._hands_of(rec["parts"][0]) & _wire_hands(rec))   # grammars never shared
        assert rec["parts"][1]["renderer"]["id"] == "wire"  # the second voice stays dry


def test_breeding_valid_and_pure():
    rng = np.random.default_rng(3)
    pa, pb = cs.sample_recipe(rng), cs.sample_recipe(rng)
    keep_a, keep_b = copy.deepcopy(pa), copy.deepcopy(pb)
    for _ in range(25):
        child, ops = cs.mutate(pa, rng)
        assert ops and kit.validate(child)
        assert not (cs._hands_of(child["parts"][0]) & _wire_hands(child))
        x = cs.crossover(pa, pb, rng)
        assert x["parts"][0]["voice"] == pa["parts"][0]["voice"]   # heavy voice of A
        assert x["parts"][1]["voice"]["id"] == pb["parts"][1]["voice"]["id"]   # wire of B
        kit.validate(x)
    assert pa == keep_a and pb == keep_b                    # parents untouched


def _sheet(inks, frame=(100.0, 80.0)):
    return Sheet(frame, [], inks, {"parts": [{"index": 0}], "recipe": {}})


def _ring(cx, cy, a, b, n=64, wiggle=0.0):
    t = np.linspace(0, 2 * np.pi, n)
    p = np.c_[cx + a * np.cos(t), cy + b * np.sin(t) + wiggle * np.sin(5 * t)]
    p[-1] = p[0]
    return p


def test_capsule_proxy_solid_vs_open_vs_bead():
    sausage = _ring(50, 40, 20, 4)
    bead = _ring(20, 20, 4, 4)
    sheet = _sheet([Ink(sausage, closed=True), Ink(bead, closed=True)])
    H, W = 205, 256                                         # mask at ~2.56 px/mm
    k = W / 100.0
    yy, xx = np.mgrid[0:H, 0:W]
    solid = ((xx / k - 50) / 20) ** 2 + ((yy / k - 40) / 4) ** 2 <= 1
    c_solid = cs.capsules(sheet, solid)
    assert c_solid["n_capsules"] == 1 and c_solid["n_beads"] == 1
    assert c_solid["capsule_area"] > 0.02
    outline_only = solid & ~(((xx / k - 50) / 19) ** 2 + ((yy / k - 40) / 3) ** 2 <= 1)
    c_open = cs.capsules(sheet, outline_only)
    assert c_open["n_capsules"] == 0 and c_open["n_open_capsules"] == 1


def test_hatching_proxy():
    m = np.zeros((240, 240), bool)
    for y in range(10, 230, 8):                             # parallel strokes ~2 mm apart
        m[y:y + 2, 10:230] = True
    assert cs.hatching(m) > 0.8
    curve = np.zeros((240, 240), bool)
    t = np.linspace(0, 1, 2000)
    xs = (20 + 200 * t).astype(int)
    ys = (120 + 80 * np.sin(6 * t)).astype(int)
    curve[ys, xs] = True
    assert cs.hatching(curve) == 0.0


def test_separability_proxy():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, (80, 6))
    b = rng.normal(0, 1, (80, 6)) + 3.0
    lo, _ = cs.separability([a, b])
    assert lo > 0.9
    same, _ = cs.separability([a, rng.normal(0, 1, (80, 6))])
    assert 0.3 < same < 0.7


def test_score_terms_bounded_and_sausage_hurts():
    f = {"sep_min": 0.85, "contrast": 1.0, "crossing": 0.3, "wholeness": 1.0, "presence": 0.5,
         "capsule_area": 0.0, "hatch": 0.0, "specks": 0.0, "cover": 0.05}
    t = cs.terms(f)
    assert all(0.0 <= v <= 1.0 for v in t.values())
    worse = dict(f, capsule_area=0.02)
    assert cs.score(worse) < cs.score(f)
    assert cs.auc([1, 2, 3], [0, 0.5]) == 1.0


def test_features_end_to_end_small():
    rec = {"frame": [120, 80], "seed": 21000,
           "parts": [{"voice": {"id": "hand", "hand": "hokusai", "length": 0.6},
                      "modulators": [{"id": "constant", "r": 1.0, "W": 2.5}],
                      "renderer": {"id": "nib", "style": "c"}},
                     {"voice": {"id": "hand", "hand": "bubble", "length": 0.6},
                      "modulators": [{"id": "wire"}], "renderer": {"id": "wire", "pen": 0.3}}]}
    f = cs.features(kit.run(rec))
    assert f["n_parts"] == 2 and 0 < f["cover"] < 0.5
    assert 0.0 <= f["sep_min"] <= 1.0 and f["weights"][0] > f["weights"][1]   # the nib voice is heavier
