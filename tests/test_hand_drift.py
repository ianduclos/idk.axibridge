"""Hand Drift source: frozen engine, frozen hands, switches and invariants."""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from axibridge.model import is_closed
from axibridge.registry import get_source
from axibridge.sources import hand_drift as hd
from axibridge.sources._hand_drift import FROZEN_FROM, hands as H, hybrid as fh

ROOT = Path(__file__).resolve().parents[1]
SRC = get_source("hand_drift")

# The only calligraphy sheets a generative hand may come from: exercises
# (siyah mashq, pen trials) and one petition — generative-allowed content
# types in docs/research/gesture-corpus. Qur'anic / devotional / album verse
# pages are measure-only and must never appear here.
ARABIC_ALLOWED = {
    "shikasta": {"wc-12", "wc-13", "wc-15"},
    "nastaliq": {"cma-1983.1115.a", "met-716304", "met-716305", "met-716307", "wal-W668-66b", "wal-W668-74b"},
}
MEASURE_ONLY = {"met-450714", "met-716315", "wc-10", "wc-17", "met-450713", "wc-19", "wc-22", "wc-24"}


def doc_paths(params):
    doc = SRC.generate(SRC.Params(**params))
    return [p for layer in doc.layers for p in layer.paths]


_BASE: dict = {}


def base_paths(params):
    """Baselines shared by the switch tests (generated once per session)."""
    key = json.dumps(params, sort_keys=True)
    if key not in _BASE:
        _BASE[key] = doc_paths(params)
    return _BASE[key]


def fingerprint(paths):
    return [(p.filled, len(p.points), [round(v, 6) for v in p.points[0] + p.points[-1]]) for p in paths]


# ---------------------------------------------------------------------------
# frozen engine and hands
# ---------------------------------------------------------------------------

def test_frozen_hands_load_with_provenance_and_stay_small():
    cat = H.catalogue()
    assert cat["frozen_from"] == FROZEN_FROM
    assert list(cat["hands"]) == list(H.HAND_IDS)
    for name in H.HAND_IDS:
        g = H.load_hand(name)
        meta = cat["hands"][name]
        assert meta["sheets"] and meta["rights"] and meta["description"]
        assert len(g.trans["nx"]) == meta["records"] > 0
        assert g.stroke_lengths and all(x > 0 for x in g.stroke_lengths)
    for name in H.TIMING_IDS:
        tm = H.load_timing(name)
        assert len(tm["speed"]) == len(tm["phi"]) == len(tm["t"]) > 100 and tm["fps"] > 0
    size = sum(p.stat().st_size for p in H.DATA.iterdir())
    assert size < 2.2 * 1024 * 1024


def test_arabic_hands_come_only_from_generative_allowed_sheets():
    cat = H.catalogue()["hands"]
    assert set(H.ARABIC_HANDS) == set(ARABIC_ALLOWED)
    for name in H.ARABIC_HANDS:
        sheets = {s.split("#")[0] for s in cat[name]["sheets"]}
        assert sheets and sheets <= ARABIC_ALLOWED[name], f"{name}: {sheets - ARABIC_ALLOWED[name]}"
        assert "generative-allowed" in cat[name]["policy"]
    for name, meta in cat.items():
        assert not ({s.split("#")[0] for s in meta["sheets"]} & MEASURE_ONLY), name


def test_engine_reproduces_the_research_drift():
    """Golden values from research commit c897f28 (`hybrid.drift_line`, route
    matisse -> shikasta -> lichtenberg, 6 R, seed 7000), which the frozen
    engine matched bit for bit at freeze time. A change here changes every
    kept Hand Drift layer: make it a deliberate engine version, not a sync."""
    hands = [H.load_hand(h) for h in ("matisse", "shikasta", "lichtenberg")]
    golden = {"kappa": (8330, 225, [468.74941721852537, 70.4523159028758]),
              "chain": (8340, 314, [429.96402394101545, 284.212660665979])}
    for ctx, (n, toks, last) in golden.items():
        r = fh.drift_line(hands, np.random.default_rng(7000), total=6.0, size=(1000, 1200), context=ctx)
        assert len(r["points"]) == n and len(r["tokens"]) == toks
        assert np.allclose(r["points"][-1], last, atol=1e-6)


# ---------------------------------------------------------------------------
# params
# ---------------------------------------------------------------------------

def test_every_numeric_param_is_bounded_and_validated():
    props = SRC.Params.model_json_schema()["properties"]
    for name, spec in props.items():
        if spec.get("type") in ("number", "integer"):
            assert "minimum" in spec and "maximum" in spec, name
    for bad in ({"lines": 9}, {"lines": 0}, {"length": 50}, {"pen": 0}, {"width": 301}, {"height": 219},
                {"amount": 3}, {"seed": -1}, {"hand_1": "none"}, {"hand_2": "quran"}, {"unknown": 1},
                {"nib_width": float("nan")}):
        with pytest.raises(ValidationError):
            SRC.Params(**bad)


def test_bench_descriptor_placement_and_orientation():
    assert SRC.bench == {"adapter": "hand-drift", "version": 1, "modes": ["new", "resume"]}
    # superseded by the Gesture Studies bench (its first study): registered, unlisted
    assert SRC.library_bench is False and SRC.listed is False and SRC.orientation == "geometry"
    assert SRC.placement_frame({"width": 200, "height": 150}) == (200.0, 150.0)
    assert SRC.placement_frame(SRC.Params().model_dump()) == (267.0, 180.0)


def test_route_per_line():
    p = SRC.Params(lines=5, hand_3="ingres", hand_4="none")
    route = ["matisse", "shikasta", "ingres"]
    assert hd.line_routes(p) == [route] * 5
    assert hd.line_routes(p.model_copy(update={"route_per_line": "rotate"}))[1] == ["shikasta", "ingres", "matisse"]
    assert hd.line_routes(p.model_copy(update={"route_per_line": "each"})) == [[h] for h in route + route[:2]]
    shuffled = hd.line_routes(p.model_copy(update={"route_per_line": "shuffle"}))
    assert shuffled[0] == route and all(sorted(r) == sorted(route) for r in shuffled)


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

WIRE = {"length": 3.0}
INKED = {"length": 2.0, "regimes": "timing"}


def test_same_params_same_geometry_in_process():
    for params in (WIRE, {**WIRE, "lines": 3, "route_per_line": "shuffle", "joins": "chain"}, INKED):
        a = SRC.generate(SRC.Params(**params))
        b = SRC.generate(SRC.Params(**params))
        assert a.model_dump() == b.model_dump()


_PROBE = r"""
import hashlib, json, sys
from axibridge.registry import get_source, load_builtin_modules
load_builtin_modules()
src = get_source("hand_drift")
out = []
for params in json.loads(sys.argv[1]):
    doc = src.generate(src.Params(**params))
    out.append(hashlib.sha256(json.dumps(doc.model_dump(), sort_keys=True).encode()).hexdigest())
print(json.dumps(out))
"""


def test_geometry_is_identical_across_hash_seeds():
    """Round 7 found set-order (PYTHONHASHSEED) bugs in the research; the
    frozen engine iterates no sets or hash-ordered dicts."""
    cases = [WIRE, {**WIRE, "lines": 3, "route_per_line": "shuffle", "blend": "interp"},
             {"length": 1.5, "regimes": "field", "ink": "c+e", "lines": 2, "route_per_line": "each"}]
    results = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        run = subprocess.run([sys.executable, "-c", _PROBE, json.dumps(cases)], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=600)
        assert run.returncode == 0, run.stderr[-2000:]
        results.append(json.loads(run.stdout.strip().splitlines()[-1]))
    assert results[0] == results[1]


@pytest.mark.parametrize("name,alt", [
    ("blend", "interp"), ("joins", "chain"), ("route_per_line", "each"), ("route_per_line", "rotate"),
    ("plateau", 0.5), ("hand_2", "bubble"), ("seed", 7001),
])
def test_each_line_switch_yields_geometry_and_changes_it(name, alt):
    base = {**WIRE, "lines": 2}
    a, b = base_paths(base), doc_paths({**base, name: alt})
    assert a and b and fingerprint(a) != fingerprint(b)


@pytest.mark.parametrize("name,alt", [
    ("ink", "a"), ("ink", "b+"), ("ink", "c"), ("ink", "c+e"), ("timing", "cmu_49_10"),
    ("wrist_nib", False), ("nib_width", 6.0), ("amount", 1.6),
])
def test_each_ink_switch_yields_geometry_and_changes_it(name, alt):
    a, b = base_paths(INKED), doc_paths({**INKED, name: alt})
    assert a and b and fingerprint(a) != fingerprint(b)


def test_regimes_off_timing_field_differ_and_keep_the_ipr_invariants():
    shown = {}
    for regimes in ("off", "timing", "field"):
        params = SRC.Params(length=2.0, regimes=regimes, lines=2)
        paths = doc_paths(params.model_dump())
        shown[regimes] = fingerprint(paths)
        assert paths
        for p in paths:
            if p.filled:
                assert is_closed(p.points)
            for x, y in p.points:
                assert 0 <= x <= params.width and 0 <= y <= params.height
        if regimes == "off":
            assert len(paths) == 2 and not any(p.filled or is_closed(p.points) for p in paths)
        else:
            assert any(p.filled for p in paths) and any(not p.filled for p in paths)
    assert len({json.dumps(v) for v in shown.values()}) == 3


def test_each_keeps_one_hand_whole_per_line():
    """`each`: line i is the single-hand drift of route[i % k] (no blending)."""
    p = SRC.Params(length=2.0, lines=3, route_per_line="each", hand_3="none")
    lines = hd.drift_centrelines(p)
    for i, hand in enumerate(["matisse", "shikasta", "matisse"]):
        r = fh.drift_line([H.load_hand(hand)], np.random.default_rng(p.seed + i), total=2.0,
                          size=hd.RESEARCH_SIZE, plateau=p.plateau)
        assert len(r["points"]) == len(lines[i])
        assert {h for _, h in r["hand_log"]} == {0}
