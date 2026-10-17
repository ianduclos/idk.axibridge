"""Tests for gesture.kit — the gesture kit skeleton (registry, recipes,
seeds, policy gate, channels, library) and its parity with the Hand Drift
bench's drift (research hybrid.drift_line)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import numpy as np
import pytest

from gesture import grammar as gm
from gesture import hybrid as hy
from gesture import kit
from gesture.core import Drawing, Stroke
from gesture.curvature import integrate_kappa
from gesture.gesture_timing import Timing
from gesture.kit import core
from gesture.kit import library as L

GES = Path(__file__).resolve().parents[1]          # tools/gesture
REPO = GES.parents[1]
KIT_DIR = GES / "gesture/kit"
BENCH = ["matisse", "shikasta", "lichtenberg"]
SMALL = {"seed": 11, "frame": [200, 140],
         "voice": {"id": "drift", "hands": ["lichtenberg", "bubble"], "length": 1.5},
         "modulators": [{"id": "timing", "tempo": "staccato"}, {"id": "field", "amount": 0.5}]}


def digest(sheet) -> str:
    h = hashlib.sha256()
    for m in sheet.marks:
        h.update(np.ascontiguousarray(m.points).tobytes())
        for k, v in m.channels.items():
            h.update(k.encode())
            h.update(np.ascontiguousarray(v).tobytes())
    for ink in sheet.inks:
        h.update(np.ascontiguousarray(ink.points).tobytes())
        h.update(bytes([ink.closed, ink.filled]))
    h.update(json.dumps(sheet.meta["recipe"], sort_keys=True).encode())
    h.update(json.dumps(sheet.meta["library"], sort_keys=True).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def test_seed_modules_registered_and_listed():
    reg = kit.registry()
    assert {"hand", "drift"} <= set(reg["voice"])
    assert {"wire", "timing", "field", "constant"} <= set(reg["modulator"])
    assert {"wire", "nib"} <= set(reg["renderer"])
    assert {"single", "grid"} <= set(reg["arranger"])
    assert kit.DISCOVERY_ERRORS == {}
    text = kit.list(quiet=True)
    for kind in reg.values():
        for mid, m in kind.items():
            assert mid in text
            for p in m.params:
                assert p.name in text
    spec = kit.describe()
    json.dumps(spec)                                  # JSON-native, for a future bench
    assert all("params" in m for ms in spec.values() for m in ms)


def test_auto_discovery_new_file_registers():
    """A new technique is a new file: dropped into the package, it registers
    on the next import with no edit anywhere else."""
    name = f"zz_tmp_{uuid.uuid4().hex[:8]}"
    path = KIT_DIR / f"{name}.py"
    path.write_text(textwrap.dedent(f"""
        import numpy as np
        from .core import P, Mark, voice

        @voice("{name}", params=[P("n", "int", 5, "points", min=2, max=50)], doc="temp test voice")
        def tmp(ctx, *, n):
            return [Mark(np.column_stack([np.linspace(0, 10, n), np.zeros(n)]))]
    """))
    try:
        code = ("import sys; sys.path.insert(0, %r); from gesture import kit; "
                "print(%r in kit.registry('voice')); "
                "s = kit.run({'voice': {'id': %r, 'n': 7}}); print(len(s.marks[0]))") % (str(GES), name, name)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr
        assert out.stdout.split() == ["True", "7"]
    finally:
        path.unlink(missing_ok=True)
        for pyc in (KIT_DIR / "__pycache__").glob(f"{name}.*"):
            pyc.unlink()


def test_duplicate_id_from_another_module_is_refused():
    with pytest.raises(kit.RegistrationError):
        @kit.voice("drift")
        def other_drift(ctx):  # pragma: no cover
            return []


def test_params_must_be_bounded():
    with pytest.raises(kit.RegistrationError):
        kit.P("x", "float", 1.0, "unbounded")


# ---------------------------------------------------------------------------
# recipes
# ---------------------------------------------------------------------------

def test_validate_fills_defaults_and_shorthand():
    r = kit.validate({"voice": {"id": "drift"}})
    assert r["parts"][0]["voice"]["hands"] == BENCH
    assert r["parts"][0]["voice"]["joins"] == "smooth"
    assert r["renderer"] == {"id": "wire", "pen": 0.4}
    assert r["arranger"]["id"] == "single"
    assert r["frame"] == [267.0, 180.0] and r["seed"] == 0
    assert kit.validate(r) == r                       # normalized recipes are fixed points


@pytest.mark.parametrize("bad", [
    {"voice": {"id": "drift"}, "colour": "red"},                                  # unknown top key
    {"voice": {"id": "nope"}},                                                    # unknown module
    {"voice": {"id": "drift", "length": 99}},                                     # out of bounds
    {"voice": {"id": "drift", "hands": ["matisse", "picasso"]}},                  # not in the library
    {"voice": {"id": "drift", "joins": "glue"}},                                  # not a choice
    {"voice": {"id": "drift", "speed": 2}},                                       # unknown param
    {"voice": {"id": "hand"}, "seed": -1},
    {"parts": []},
])
def test_validate_rejects(bad):
    with pytest.raises(kit.RecipeError):
        kit.validate(bad)


def test_recipe_is_deterministic_in_process():
    a, b = kit.run(SMALL), kit.run(SMALL)
    assert digest(a) == digest(b)
    c = kit.run({**SMALL, "seed": 12})
    assert digest(a) != digest(c)


def test_recipe_is_deterministic_across_processes_and_hash_seeds():
    code = ("import sys, json; sys.path.insert(0, %r); sys.path.insert(0, %r); "
            "from test_kit import digest, SMALL; from gesture import kit; print(digest(kit.run(SMALL)))"
            % (str(GES), str(GES / "tests")))
    outs = []
    for hs in ("0", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": hs}
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=300)
        assert p.returncode == 0, p.stderr
        outs.append(p.stdout.strip().splitlines()[-1])
    assert outs[0] == outs[1] == digest(kit.run(SMALL))


def test_part_seeds_derive_from_recipe_seed_and_index_only():
    r = {"seed": 5, "arranger": {"id": "grid"},
         "parts": [{"voice": {"id": "hand", "hand": "bubble", "length": 1.0}},
                   {"voice": {"id": "hand", "hand": "lichtenberg", "length": 1.0}}]}
    s = kit.run(r)
    assert [p["seed"] for p in s.meta["parts"]] == [5, 6]
    # a part's line does not depend on its neighbours
    alone = kit.run({"seed": 6, "voice": {"id": "hand", "hand": "lichtenberg", "length": 1.0}})
    a = s.marks[1]
    b = alone.marks[0]
    na = (a.points - a.meta["fit"]["offset"]) / a.meta["fit"]["scale"]
    nb = (b.points - b.meta["fit"]["offset"]) / b.meta["fit"]["scale"]
    assert np.allclose(na, nb, atol=1e-8)


# ---------------------------------------------------------------------------
# bench parity
# ---------------------------------------------------------------------------

def _research_drift(hands, seed, **kw):
    st, _ = hy.drift_line(hands, np.random.default_rng(seed), total=kw.get("total", 6.0),
                          mode=kw.get("mode", "mixture"), size=(1000, 1200), plateau=0.12,
                          context=kw.get("context", "kappa"))
    return st.points


def test_bench_default_recipe_reproduces_drift_line():
    sheet = kit.run({"frame": [267, 180], "seed": 7000,
                     "voice": {"id": "drift", "hands": BENCH, "joins": "smooth"}, "renderer": {"id": "wire"}})
    m = sheet.marks[0]
    px = _research_drift([L.load("hand", h) for h in BENCH], 7000)
    s, off = m.meta["fit"]["scale"], np.asarray(m.meta["fit"]["offset"])
    assert np.allclose(m.points, px * s + off, atol=1e-9)
    # the bench's fit: inset = pen / 2, uniform scale, centred in the frame
    inset = 0.2
    W, H = 267 - 2 * inset, 180 - 2 * inset
    bw, bh = np.ptp(px, axis=0)
    assert s == pytest.approx(min(W / bw, H / bh), rel=1e-12)
    lo, hi = m.points.min(axis=0), m.points.max(axis=0)
    assert np.allclose((lo + hi) / 2, [133.5, 90.0], atol=1e-9)
    assert lo.min() >= inset - 1e-9 and hi[0] <= 267 - inset + 1e-9 and hi[1] <= 180 - inset + 1e-9
    # one ink, the line itself
    assert len(sheet.inks) == 1 and np.array_equal(sheet.inks[0].points, m.points)


@pytest.mark.skipif(not (REPO / ".local/gesture/out/grammar_v7/grammar_matisse.json").exists(),
                    reason="research grammars are local to the Mac")
def test_bench_default_matches_research_json_grammars():
    paths = {"matisse": REPO / ".local/gesture/out/grammar_v7/grammar_matisse.json",
             "shikasta": REPO / ".local/gesture/out/hybrid_hands/grammars/shikasta.json",
             "lichtenberg": REPO / ".local/gesture/out/hybrid_hands/grammars/lichtenberg.json"}
    a = _research_drift([gm.Grammar.load(paths[h]) for h in BENCH], 7000)
    b = _research_drift([L.load("hand", h) for h in BENCH], 7000)
    assert np.array_equal(a, b)


def test_grid_each_matches_bench_line_seeds():
    hands = ["matisse", "shikasta", "lichtenberg", "bubble"]
    sheet = kit.run({"seed": 7000, "arranger": {"id": "grid"},
                     "parts": [{"voice": {"id": "hand", "hand": h, "length": 1.0}} for h in hands]})
    scales = set()
    for i, (h, m) in enumerate(zip(hands, sheet.marks)):
        px = _research_drift([L.load("hand", h)], 7000 + i, total=1.0)
        s, off = m.meta["fit"]["scale"], np.asarray(m.meta["fit"]["offset"])
        assert np.allclose(m.points, px * s + off, atol=1e-8)
        scales.add(round(s, 12))
    assert len(scales) == 1                           # one common scale, as the bench


# ---------------------------------------------------------------------------
# channels
# ---------------------------------------------------------------------------

@kit.voice("test_channel_voice", params=[kit.P("n", "int", 400, "points", min=2, max=5000)],
           doc="test-only: a wave carrying an unknown channel")
def _test_channel_voice(ctx, *, n):
    x = np.linspace(0, 100, n)
    pts = np.column_stack([x, 10 * np.sin(x / 7)])
    return kit.fitted([pts], ctx.box, [{"ink_age": x / 100.0}], [{"note": "test"}])


@kit.modulator("test_drop_channel", doc="test-only: breaks the pass-through contract")
def _test_drop(ctx, marks):
    return [kit.Mark(m.points, {"r": m["r"]}, m.meta) for m in marks]


def test_unknown_channels_pass_through_every_seed_modulator():
    sheet = kit.run({"seed": 3, "voice": {"id": "test_channel_voice"},
                     "modulators": [{"id": "constant", "W": 2.0}, {"id": "timing", "tempo": "fluidity"},
                                    {"id": "field"}, {"id": "wire"}]})
    m = sheet.marks[0]
    assert set(kit.REQUIRED_CHANNELS) <= set(m.channels)
    assert "ink_age" in m.channels and "tremor" in m.channels
    age = m["ink_age"]
    assert age[0] == pytest.approx(0.0, abs=1e-3) and age[-1] == pytest.approx(1.0, abs=1e-3)
    assert np.all(np.diff(age) >= -1e-9)              # interpolated along the line, order kept
    assert np.all(m["r"] == 0.0)                      # wire last
    assert m.meta["note"] == "test"


def test_dropping_a_channel_is_an_error():
    with pytest.raises(kit.ChannelError):
        kit.run({"voice": {"id": "test_channel_voice"}, "modulators": [{"id": "test_drop_channel"}]})


def test_marks_are_immutable_and_stages_pure():
    m = kit.Mark(np.zeros((3, 2)), {"x": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError):
        m.points[0, 0] = 1.0
    with pytest.raises(ValueError):
        m["x"][0] = 9.0
    m2 = m.evolve(channels={"x": np.ones(3)})
    assert list(m["x"]) == [1.0, 2.0, 3.0] and list(m2["x"]) == [1.0, 1.0, 1.0]
    assert m.channels["r"].tolist() == [0.0, 0.0, 0.0] and m["W"][0] == kit.DEFAULT_CHANNELS["W"]
    with pytest.raises(kit.ChannelError):
        kit.Mark(np.zeros((3, 2)), {"x": [1.0, 2.0]})


@pytest.mark.parametrize("style", ["a", "b+", "e"])
def test_nib_renderer_inks_regimes(style):
    sheet = kit.run({"seed": 4, "voice": {"id": "test_channel_voice", "n": 300},
                     "modulators": [{"id": "constant", "r": 2.0, "W": 3.0, "M": 8.0}],
                     "renderer": {"id": "nib", "style": style}})
    assert len(sheet.inks) > 3 and any(i.closed for i in sheet.inks)
    assert all(i.closed for i in sheet.inks if i.filled)
    if style == "a":       # research styles b+/c/e chain the outline into their passes: no lone ring
        assert any(i.filled for i in sheet.inks)


# ---------------------------------------------------------------------------
# policy gate
# ---------------------------------------------------------------------------

def test_policy_gate_measure_only_corpus():
    with pytest.raises(kit.PolicyError):
        L.load("corpus", "calligraphy")
    with pytest.raises(kit.PolicyError):
        L.load("corpus", "print")
    assert L.load("corpus", "calligraphy", purpose="measure")["id"] == "calligraphy"
    assert L.load("corpus", "calligraphy", items=["wc-12", "wc-13"])["policy"] == "measure-only"
    with pytest.raises(kit.PolicyError):
        L.load("corpus", "calligraphy", items=["wc-12", "wc-30"])      # wc-30: lead ruled measure-only
    from gesture.calligraphy import PolicyError as ResearchPolicyError
    assert issubclass(kit.PolicyError, ResearchPolicyError)


def test_arabic_hands_carry_allow_list_provenance():
    allow = set(L.entry("corpus", "calligraphy")["generative_items"])
    assert "wc-30" not in allow
    sh = L.entry("hand", "shikasta")
    assert sh["provenance"]["training_sheets"] == ["wc-12", "wc-13", "wc-15"]
    na = L.entry("hand", "nastaliq")
    for e in (sh, na):
        assert e["provenance"]["corpus"] == "calligraphy" and "allow_list" in e["provenance"]
        assert set(e["provenance"]["training_sheets"]) <= allow
    for e in L.entries("hand"):
        assert e["provenance"]["training_sheets"], e["id"]


@pytest.fixture()
def tmp_library(tmp_path, monkeypatch):
    root = tmp_path / "library"
    shutil.copytree(L.ROOT, root)
    monkeypatch.setenv("GESTURE_KIT_LIBRARY", str(root))
    return L.Library(root)


def test_policy_gate_blocks_generation_through_run(tmp_library):
    e = tmp_library.entry("hand", "bubble")
    e["policy"] = "measure-only"
    tmp_library.save(e, None, overwrite=True)
    with pytest.raises(kit.PolicyError):
        kit.run({"voice": {"id": "hand", "hand": "bubble", "length": 0.5}})
    # a hand claiming a sheet outside the corpus allow-list is refused too
    e = tmp_library.entry("hand", "shikasta")
    e["provenance"]["training_sheets"] = ["wc-12", "wc-30"]
    tmp_library.save(e, None, overwrite=True)
    with pytest.raises(kit.PolicyError):
        kit.run({"voice": {"id": "drift", "hands": ["matisse", "shikasta"], "length": 0.5}})


def test_sheet_meta_records_library_ids():
    s = kit.run(SMALL)
    ids = [(u["kind"], u["id"]) for u in s.meta["library"]]
    assert ids == [("hand", "bubble"), ("hand", "lichtenberg"), ("tempo", "staccato")]


# ---------------------------------------------------------------------------
# library round trip
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_grammar():
    rng = np.random.default_rng(0)
    ds = []
    for _ in range(2):
        strokes = []
        for i in range(8):
            k = rng.uniform(-1 / 80, 1 / 80)
            p = integrate_kappa(np.array([0, rng.uniform(150, 400)]), np.array([k, -k]), 1.0,
                                start=(300 + 20 * i, 300 + 15 * i), heading=rng.uniform(0, 6.28))
            strokes.append(Stroke(p, width=np.full(len(p), 2.0)))
        ds.append(Drawing(strokes, source="t", size=(1000, 1000)))
    return gm.learn(ds, name="synthetic", len_quantile=0.0)


def test_hand_round_trip_is_exact(tmp_path, synthetic_grammar):
    g = synthetic_grammar.to_json()
    arrays, sheet = L.encode_hand(g)
    lib = L.Library(tmp_path)
    lib.save({"id": "synthetic", "kind": "hand", "label": "Synthetic", "policy": "generative",
              "provenance": {"training_sheets": ["t"]}},
             {"tables.npz": L.npz_bytes(arrays), "sheet.json.gz": L.json_gz_bytes(sheet)})
    back = lib.load("hand", "synthetic")
    assert L.deep_equal(back.to_json(), g)
    a = _research_drift([synthetic_grammar], 9, total=2.0)
    b = _research_drift([back], 9, total=2.0)
    assert np.array_equal(a, b)
    assert L.npz_bytes(arrays) == L.npz_bytes(arrays) and L.json_gz_bytes(sheet) == L.json_gz_bytes(sheet)
    with pytest.raises(L.LibraryError):
        lib.save({"id": "synthetic", "kind": "hand", "label": "x", "policy": "generative"}, {})


def test_tempo_round_trip_is_exact(tmp_path):
    rng = np.random.default_rng(1)
    n = 500
    tm = Timing(np.arange(n) / 50.0, rng.random(n) * 30, rng.random(n) * np.pi, rng.normal(0, 0.1, n),
                rng.normal(0, 100, n), rng.random(n) < 0.1, label="synthetic", meta={"fps": 50.0})
    arrays, sheet = L.encode_tempo(tm)
    lib = L.Library(tmp_path)
    lib.save({"id": "syn", "kind": "tempo", "label": "syn", "policy": "generative"},
             {"profile.npz": L.npz_bytes(arrays), "sheet.json.gz": L.json_gz_bytes(sheet)})
    back = lib.load("tempo", "syn")
    for k in L.TEMPO_ARRAYS:
        assert np.array_equal(getattr(back, k), getattr(tm, k))
    assert back.label == "synthetic" and back.fps == pytest.approx(50.0)


@pytest.mark.skipif(not (REPO / ".local/gesture/out/hybrid_hands/grammars/meta.json").exists(),
                    reason="research grammars are local to the Mac")
@pytest.mark.parametrize("hand", ["matisse", "hokusai", "ingres", "shikasta", "nastaliq", "marden",
                                  "lichtenberg", "bubble"])
def test_committed_hands_equal_research_json(hand):
    e = L.entry("hand", hand)
    d = json.loads((REPO / e["provenance"]["research_file"]).read_text())
    assert L.deep_equal(L.load("hand", hand).to_json(), d)


def test_committed_library_shape_and_budget():
    lib = L.default()
    assert set(lib.ids("hand")) == {"matisse", "hokusai", "ingres", "shikasta", "nastaliq", "marden",
                                    "lichtenberg", "bubble"}
    assert set(lib.ids("tempo")) == {"staccato", "levitation", "fluidity", "particles", "cmu_49_10",
                                     "cmu_55_mantis"}
    assert {"calligraphy", "print", "matisse", "dance", "earth"} <= set(lib.ids("corpus"))
    for e in lib.entries():
        assert e["policy"] in L.POLICIES
        for rel in e["files"].values():
            assert (lib.folder(e["kind"], e["id"]) / rel).exists()
    assert lib.size() < 10 * 2**20
    corpus = REPO / ".local/gesture/corpus"
    if corpus.exists():
        assert set(lib.ids("corpus")) == {p.name for p in corpus.iterdir() if p.is_dir()}


def test_preview_writes_image_and_recipe(tmp_path):
    s = kit.run({"seed": 2, "voice": {"id": "hand", "hand": "bubble", "length": 0.6}})
    p = kit.preview(s, tmp_path / "x.png", px_per_mm=2.0)
    assert p.exists() and p.with_suffix(".recipe.json").exists()
    again = kit.run(json.loads(p.with_suffix(".recipe.json").read_text()))
    assert digest(again) == digest(s)
    from PIL import Image
    im = np.asarray(Image.open(p).convert("RGB"))
    assert tuple(im[2, 2]) == core.PAPER
