"""Gesture Studies: study format and bounds, every built-in renders, parity with
the research kit, new library hands flow into every study, kept layers never
change, the saved-studies store and its API."""
import copy
import hashlib
from collections import Counter
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import shapely
from fastapi.testclient import TestClient
from pydantic import ValidationError

from axibridge import gencache
from axibridge.model import is_closed
from axibridge.registry import describe_modules, get_source, load_builtin_modules
from axibridge.sources._gesture_studies import engine
from axibridge.sources._gesture_studies import frozen_library as FL
from axibridge.sources._gesture_studies import studies as ST

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "axibridge/sources/_gesture_studies"
FIXTURES = ROOT / "tests/fixtures/gesture_studies"
load_builtin_modules()
SRC = get_source("gesture_studies")
HD = get_source("hand_drift")
ORDER = ["hand_drift", "danced_chain", "two_voices", "drawing_and_measure", "shape_atlas", "conversation",
         "annotated_page", "three_voices",
         # Studies v2 (2026-10-17)
         "numbered_atlas", "dance_atlas", "margin_chart", "merged_shadow", "chorus", "sampler", "ledger_straight"]
KIT_STUDIES = ORDER[1:]                        # the sampler draws through the kit too
# Studies whose ink depends on GEOS's offset/buffer details: nib "c" lanes come out
# slightly differently under GEOS 3.13 (app venv) and 3.14 (research venv). The
# freeze script proves the frozen copy reproduces the research exactly under the
# research interpreter; here they must still agree structurally.
# The sampler's default combination changes when a refreeze adds hands; it may
# then be inked in nib "c" lanes, so it is held to the structural check too.
GEOS_SENSITIVE = {"two_voices", "sampler"}

_SHEETS: dict = {}


def sheet(sid):
    """The built-in study's kit sheet with its default values (rendered once)."""
    if sid not in _SHEETS:
        lib = FL.FrozenLibrary()
        st = ST.builtin(sid)
        _SHEETS[sid] = engine.run_kit(ST.run_recipe(st, ST.resolve(st, {}, lib), lib), lib)
    return _SHEETS[sid]


def study_paths(sid):
    st = ST.builtin(sid)
    lib = FL.FrozenLibrary()
    recipe = ST.resolve(st, {}, lib)
    if st.engine == "hand_drift":
        return engine.render(st.engine, recipe, lib), engine.frame_of(st.engine, recipe)
    W, H = engine.frame_of("kit", ST.run_recipe(st, recipe, lib))
    return engine._fit_inside(engine.inks_to_paths(sheet(sid).inks), W, H), (W, H)


def params(sid, values=None, **extra):
    return {"study": ST.builtin(sid).model_dump(mode="json"), "values": values or {}, **extra}


def gen(p):
    doc = SRC.generate(SRC.Params(**p))
    return [q for layer in doc.layers for q in layer.paths]


def fingerprint(paths):
    return [(p.filled, len(p.points), [round(v, 6) for v in p.points[0] + p.points[-1]]) for p in paths]


# ---------------------------------------------------------------------------
# format, bounds, registration
# ---------------------------------------------------------------------------

def test_builtin_studies_load_in_order_with_few_bounded_controls():
    studies = ST.builtin_studies()
    assert [s.id for s in studies] == ORDER
    for s in studies:
        ST.check_study(s)
        assert s.version >= 1 and s.notes and s.source
        assert any(c.key == "seed" and c.type == "int" for c in s.controls), s.id
        if s.engine == "kit":
            assert 3 <= len(s.controls) <= 8, s.id
        if s.engine == "sampler":                      # the seed IS the piece: it picks the combination
            assert [c.key for c in s.controls] == ["seed"]
        for c in s.controls:
            if c.type in ("int", "float"):
                assert c.min is not None and c.max is not None and c.min < c.max
    assert studies[0].engine == "hand_drift"          # the Hand Drift bench is the first study, as it is
    assert {c.key for c in studies[0].controls} >= set(HD.Params.model_fields) - {"route"}


def test_controls_must_fit_the_params_they_point_at():
    base = ST.builtin("danced_chain").model_dump()

    def bad(control, match):
        s = copy.deepcopy(base)
        s["controls"] = [control]
        with pytest.raises(ST.StudyError, match=match):
            ST.check_study(ST.Study(**s))

    bad({"path": "parts.0.voice.length", "label": "L", "type": "float", "min": 0.0, "max": 50.0}, "exceed")
    bad({"path": "parts.0.voice.nope", "label": "L", "type": "float", "min": 1, "max": 2}, "no param")
    bad({"path": "parts.3.voice.length", "label": "L", "type": "float", "min": 1, "max": 2}, "does not point")
    bad({"path": "parts.0.voice.hands", "label": "H", "type": "hand"}, "not one hand")
    bad({"path": "parts.0.modulators.0.tempo", "label": "T", "type": "hand"}, "not one hand")
    bad({"path": "parts.0.voice.joins", "label": "J", "type": "choice", "choices": ["smooth", "zigzag"]}, "choices")
    with pytest.raises(ValidationError):            # numeric controls must be bounded
        ST.Control(path="seed", label="Seed", type="int")
    with pytest.raises(ValidationError):
        ST.Control(path="seed", paths=["seed"], label="Seed", type="int", min=0, max=1)


def test_values_are_validated_against_controls_and_library():
    for values in ({"parts.0.voice.length": 99.0}, {"seed": -1}, {"seed": 1.5},
                   {"parts.0.voice.hands": ["matisse"]},                 # route takes 2–4
                   {"parts.0.voice.hands": ["matisse", "quran"]},        # not a library hand
                   {"parts.0.modulators.0.tempo": "matisse"},            # a hand is not a tempo
                   {"parts.0.voice.joins": "chain"},                     # fixed in this study: no control
                   {"parts.0.modulators.0.amount": float("nan")}):
        with pytest.raises((ValidationError, ValueError)):
            SRC.Params(**params("danced_chain", values))
    p = SRC.Params(**params("danced_chain", {"parts.0.voice.length": 3.0, "seed": 12}))
    assert p.recipe["parts"][0]["voice"]["length"] == 3.0 and p.recipe["seed"] == 12
    assert p.recipe["parts"][0]["voice"]["joins"] == "chain"


def test_source_registration_and_hand_drift_leaves_the_dropdown():
    assert SRC.bench == {"adapter": "gesture-studies", "version": 1, "modes": ["new", "resume"]}
    assert SRC.library_bench is True and SRC.orientation == "geometry"
    mods = {m["id"]: m for m in describe_modules()["sources"]}
    gs, hd = mods["gesture_studies"], mods["hand_drift"]
    assert gs["listed"] and "bench" in gs["library_categories"]
    assert gs["defaults"]["study"]["id"] == "hand_drift"
    assert not hd["listed"] and "bench" not in hd["library_categories"]
    assert hd["bench"]["adapter"] == "hand-drift"           # still resolves and resumes kept layers
    assert all(spec.get("hidden") for spec in gs["schema"]["properties"].values())
    assert gs["preset_exclusions"] == ["library", "pins", "sampled", "voice"]
    assert SRC.placement_frame(params("shape_atlas")) == (267.0, 120.0)
    assert SRC.placement_frame(params("hand_drift", {"width": 200.0, "height": 150.0})) == (200.0, 150.0)


def test_frozen_kit_is_untouched_and_names_its_research_commit():
    manifest = json.loads((APP / "kit/FROZEN.json").read_text())
    assert manifest["frozen_from"] and manifest["files"]
    for rel, rec in manifest["files"].items():
        data = (APP / rel).read_bytes()
        assert hashlib.sha256(data).hexdigest() == rec["sha256"], f"{rel} was edited by hand; refreeze instead"
        assert data.startswith(f"# FROZEN from research commit {manifest['frozen_from']}".encode()), rel
    index = json.loads((APP / "library/index.json").read_text())
    assert index["current"] in index["history"]
    assert (APP / "library/snapshots" / f"{index['current']}.json").exists()


def test_frozen_library_is_every_generative_entry_and_respects_policy():
    snap = FL.snapshot(FL.current_snapshot())
    assert len(snap["hand"]) >= 24 and len(snap["tempo"]) >= 6 and len(snap["dance_trail"]) >= 9
    lib = FL.FrozenLibrary()
    for kind in FL.index()["generative_kinds"]:
        for eid in lib.ids(kind):
            e = lib.entry(kind, eid)
            assert e["policy"] == "generative", f"{kind}/{eid}"
            lib.check(e, "generate")
    # Arabic hands come only from allow-listed calligraphy sheets (re-checked on every load)
    callig = lib.entry("corpus", "calligraphy")
    assert callig["policy"] == "measure-only"
    for name in ("shikasta", "nastaliq"):
        e = lib.entry("hand", name)
        assert e["provenance"]["corpus"] == "calligraphy"
        assert set(e["provenance"]["training_sheets"]) <= set(callig["generative_items"])
    size = sum(p.stat().st_size for p in (APP / "library").rglob("*") if p.is_file())
    assert size < 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sid", ORDER)
def test_every_builtin_study_renders_valid_paths_inside_its_frame(sid):
    paths, (W, H) = study_paths(sid)
    assert len(paths) > 0
    for p in paths:
        assert len(p.points) >= 2
        assert all(-1e-6 <= x <= W + 1e-6 and -1e-6 <= y <= H + 1e-6 for x, y in p.points)
        if p.filled:
            assert is_closed(p.points) and len(p.points) >= 4
    if sid in ("two_voices", "three_voices", "chorus"):
        assert any(p.filled for p in paths)            # mass / nib rims occlude


def test_source_generate_is_the_engine_output():
    p = params("drawing_and_measure")
    assert fingerprint(gen(p)) == fingerprint(study_paths("drawing_and_measure")[0])
    doc = SRC.generate(SRC.Params(**p))
    assert (doc.width, doc.height) == (267.0, 180.0) and "drawing_and_measure v1" in doc.source


def test_hand_drift_study_is_the_hand_drift_generator():
    cases = [{}, {"joins": "chain", "lines": 2, "length": 3.0},
             {"regimes": "timing", "length": 2.0, "ink": "c", "timing": "cmu_49_10"},
             {"regimes": "field", "length": 1.5, "hand_3": "none", "route_per_line": "each", "lines": 2}]
    for values in cases:
        mine = gen(params("hand_drift", values))
        theirs = [q for layer in HD.generate(HD.Params(**values)).layers for q in layer.paths]
        assert [(q.filled, q.points) for q in mine] == [(q.filled, q.points) for q in theirs], values


def test_hand_drift_study_reaches_library_hands_the_generator_never_had():
    a = gen(params("hand_drift", {"hand_2": "aaron", "length": 2.0}))
    b = gen(params("hand_drift", {"length": 2.0}))
    assert a and fingerprint(a) != fingerprint(b)


def _summary(sh):
    out = []
    for ink in sh.inks:
        p = np.asarray(ink.points, float)
        out.append([len(p), bool(ink.closed), bool(ink.filled), float(ink.pen), *p[0], *p[-1],
                    p[:, 0].sum(), p[:, 1].sum(), (p[:, 0] ** 2).sum(), (p[:, 1] ** 2).sum()])
    allp = np.vstack([np.asarray(i.points, float) for i in sh.inks])
    return out, allp


@pytest.mark.parametrize("sid", KIT_STUDIES)
def test_parity_with_the_research_kit(sid):
    """Same recipe ⇒ same paths as the research kit (fixture written by
    tools/gesture_studies/freeze.py from the HEAD research kit + library)."""
    fx = json.loads((FIXTURES / f"{sid}.json").read_text())
    assert fx["version"] == ST.builtin(sid).version
    if "sampled" in fx:                                    # the frozen sampler picked the research's recipe
        st = ST.builtin(sid)
        lib = FL.FrozenLibrary()
        assert ST.run_recipe(st, ST.resolve(st, {}, lib), lib) == ST._kit_recipe(fx["sampled"], lib)
    got, allp = _summary(sheet(sid))
    assert len(got) == len(fx["inks"])
    exact = sid not in GEOS_SENSITIVE or fx["geos"] == shapely.geos_version_string
    if exact:
        for a, b in zip(got, fx["inks"]):
            assert a[:3] == b[:3]
            assert np.allclose(a[3:], b[3:], rtol=1e-9, atol=1e-7)
        assert np.allclose(allp[::fx["stride"]], np.asarray(fx["sample"]), atol=1e-7)
    else:
        mine = Counter(tuple(a[1:3]) for a in got)
        theirs = Counter(tuple(b[1:3]) for b in fx["inks"])
        assert mine[(True, True)] == theirs[(True, True)]        # the same occluding rims
        assert all(abs(mine[k] - theirs[k]) <= 0.02 * len(got) for k in set(mine) | set(theirs))
        assert abs(len(allp) - fx["n_points"]) <= 0.01 * fx["n_points"]
        ref_mean = np.array([sum(b[8] for b in fx["inks"]), sum(b[9] for b in fx["inks"])]) / fx["n_points"]
        assert np.allclose(allp.mean(axis=0), ref_mean, atol=1.0)     # same drawing, same place (mm)
        same = sum(a[0] == b[0] and np.allclose(a[3:], b[3:], rtol=1e-9, atol=1e-7)
                   for a, b in zip(got, fx["inks"]))
        assert same >= 0.5 * len(got)


def test_same_params_same_geometry_in_process():
    for sid, values in (("conversation", {"arranger.turns": 6}), ("three_voices", {"seed": 3})):
        assert fingerprint(gen(params(sid, values))) == fingerprint(gen(params(sid, values)))


_PROBE = r"""
import json, sys
from axibridge.registry import load_builtin_modules, get_source
from axibridge.sources._gesture_studies import studies as ST
load_builtin_modules()
src = get_source("gesture_studies")
out = []
for sid, values in json.loads(sys.argv[1]):
    doc = src.generate(src.Params(study=ST.builtin(sid).model_dump(mode="json"), values=values))
    out.append([[p.filled, [list(map(float, q)) for q in p.points]] for l in doc.layers for p in l.paths])
print(json.dumps(out))
"""


def test_geometry_is_identical_across_hash_seeds():
    cases = [["conversation", {"arranger.turns": 6}], ["three_voices", {}], ["drawing_and_measure", {}]]
    results = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        run = subprocess.run([sys.executable, "-c", _PROBE, json.dumps(cases)], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=600)
        assert run.returncode == 0, run.stderr[-2000:]
        results.append(hashlib.sha256(run.stdout.strip().splitlines()[-1].encode()).hexdigest())
    assert results[0] == results[1]


def test_a_control_changes_the_output():
    a = gen(params("three_voices"))
    b = gen(params("three_voices", {"parts.1.voice.hand": "matisse"}))
    c = gen(params("three_voices", {"parts.0.voice.trail": "staccato"}))
    assert fingerprint(a) != fingerprint(b) and fingerprint(a) != fingerprint(c)


# ---------------------------------------------------------------------------
# the library grows: new hands appear everywhere; kept layers never change
# ---------------------------------------------------------------------------

def _temp_library(tmp_path, edits):
    """A copy of the frozen library with `edits` applied as a NEW freeze:
    edits = {(kind, id): (template_id, entry_overrides)}. Returns the root."""
    root = tmp_path / "library"
    shutil.copytree(APP / "library", root)
    index = json.loads((root / "index.json").read_text())
    snap = json.loads((root / "snapshots" / f"{index['current']}.json").read_text())
    for (kind, eid), (template, over) in edits.items():
        src = root / kind / template / snap["entries"][kind][template]
        entry = json.loads((src / "entry.json").read_text())
        entry.update({"id": eid, **over})
        h = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()[:12]
        dst = root / kind / eid / h
        shutil.copytree(src, dst)
        (dst / "entry.json").write_text(json.dumps(entry))
        snap["entries"][kind][eid] = h
    sid = hashlib.sha256(json.dumps(snap["entries"], sort_keys=True).encode()).hexdigest()[:12]
    snap["id"] = sid
    (root / "snapshots" / f"{sid}.json").write_text(json.dumps(snap))
    index["current"] = sid
    index["history"].append(sid)
    (root / "index.json").write_text(json.dumps(index))
    return root


@pytest.fixture()
def library_root():
    old = FL.ROOT
    yield lambda root: FL.set_root(root)
    FL.set_root(old)


def test_a_new_library_hand_is_offered_by_every_hand_control(tmp_path, library_root):
    root = _temp_library(tmp_path, {
        ("hand", "test_new_hand"): ("bubble", {"label": "Test hand", "provenance": {"corpus": "earth"}}),
        ("hand", "test_measure_only"): ("bubble", {"label": "Restricted", "policy": "measure-only"}),
        ("tempo", "test_new_tempo"): ("staccato", {"label": "Test tempo"}),
        ("dance_trail", "test_new_trail"): ("mantis", {"label": "Test trail"}),
    })
    library_root(root)
    assert "test_new_hand" in [o["id"] for o in FL.options("hand")]
    assert "test_measure_only" not in [o["id"] for o in FL.options("hand")]
    lib = FL.FrozenLibrary()
    seen = {"hand": 0, "tempo": 0, "trail": 0}
    for st in ST.builtin_studies():
        for c in st.controls:
            if c.type not in ("hand", "hands", "tempo", "trail"):
                continue
            new = {"tempo": "test_new_tempo", "trail": "test_new_trail"}.get(c.type, "test_new_hand")
            assert new in ST.options_for(st, c, lib), (st.id, c.key)
            assert "test_measure_only" not in ST.options_for(st, c, lib)
            v = ST.get_at(st.recipe, c.targets[0])
            if c.type == "hands":
                items = v.split() if c.join else list(v)
                value = " ".join([new, *items[1:]]) if c.join else [new, *items[1:]]
            else:
                value = new
            recipe = ST.resolve(st, {c.key: value}, lib)        # accepted, written into every target
            assert ST.get_at(recipe, c.targets[-1]) == value
            with pytest.raises(ST.StudyError):
                ST.resolve(st, {c.key: ["test_measure_only"] if c.type == "hands" and not c.join
                                else "test_measure_only"}, lib)
            seen["trail" if c.type == "trail" else "tempo" if c.type == "tempo" else "hand"] += 1
    assert all(seen.values()), seen
    # and it draws, in the kit and in the Hand Drift engine
    assert gen(params("three_voices", {"parts.1.voice.hand": "test_new_hand", "parts.0.voice.seconds": 4.0}))
    assert gen(params("hand_drift", {"hand_2": "test_new_hand", "regimes": "timing", "timing": "test_new_tempo",
                                     "length": 1.5}))


def test_kept_layer_survives_study_deletion_and_a_refreeze(tmp_path, library_root):
    from axibridge.gesture_studies_store import gesture_study_store
    from axibridge.session import session

    p = params("three_voices", {"parts.1.voice.hand": "matisse"})
    saved = gesture_study_store.save(label="Matisse among dancers", engine="kit",
                                     recipe=ST.resolve(ST.builtin("three_voices"), p["values"], FL.FrozenLibrary()),
                                     controls=[c.model_dump(exclude_none=True)
                                               for c in ST.builtin("three_voices").controls],
                                     parent={"id": "three_voices", "version": 1})
    layer = session.add_generated_layer("gesture_studies", {"study": saved.model_dump(mode="json"), "values": {}})
    kept = layer.source.params
    assert kept["library"] == FL.current_snapshot()
    pins = {(x["kind"], x["id"]): x for x in kept["pins"]}
    assert pins[("hand", "matisse")]["hash"] == FL.FrozenLibrary().hash_of("hand", "matisse")
    assert ("dance_trail", "mantis") in pins and pins[("hand", "matisse")]["version"] == 1
    before = fingerprint(session.source_geometry[layer.id])

    gesture_study_store.delete(saved.id)
    gencache.clear()                                           # really regenerate, no memo
    engine._SHEETS.clear()
    session.regenerate_layer(layer.id)
    assert fingerprint(session.source_geometry[layer.id]) == before

    # a refreeze replaces matisse with different data under the same id
    root = _temp_library(tmp_path, {("hand", "matisse"): ("hokusai", {"label": "Matisse v2", "version": 2})})
    library_root(root)
    assert FL.FrozenLibrary().hash_of("hand", "matisse") != pins[("hand", "matisse")]["hash"]
    fresh = gen({"study": saved.model_dump(mode="json"), "values": {}})
    assert fingerprint(fresh) != before                        # a new preview sees the new matisse …
    gencache.clear()
    engine._SHEETS.clear()
    session.regenerate_layer(layer.id)
    assert fingerprint(session.source_geometry[layer.id]) == before   # … the kept layer does not


def test_complete_params_pins_every_named_entry():
    out = SRC.complete_params(params("conversation"))
    assert out["library"] == FL.current_snapshot()
    named = {(x["kind"], x["id"]) for x in out["pins"]}
    pool = ST.builtin("conversation").recipe["arranger"]["pool"].split()
    assert {("hand", h) for h in pool} <= named and ("tempo", "staccato") not in named
    assert all(len(x["hash"]) == 12 and x["version"] >= 1 for x in out["pins"])
    with pytest.raises(ValidationError):
        SRC.Params(**{**out, "pins": [{"kind": "hand", "id": "matisse", "version": 1, "hash": "0" * 12}]})


# ---------------------------------------------------------------------------
# saved studies: store and API
# ---------------------------------------------------------------------------

def test_saved_study_store_round_trip():
    from axibridge.gesture_studies_store import gesture_study_store
    from axibridge.stores import CONFIG_DIR

    assert str(CONFIG_DIR).startswith(os.environ["AXIBRIDGE_CONFIG_DIR"])   # isolated, never ~/.axibridge
    st = ST.builtin("danced_chain")
    saved = gesture_study_store.save(label="Slow chain", engine="kit", recipe=st.recipe,
                                     controls=[c.model_dump(exclude_none=True) for c in st.controls],
                                     parent={"id": st.id, "version": st.version})
    assert saved.id.startswith("slow_chain_") and saved.parent.id == "danced_chain" and saved.version == 1
    listed = gesture_study_store.list()["items"]
    assert saved.id in [s.id for s in listed]
    assert gesture_study_store.get(saved.id).recipe == ST.check_study(saved).recipe
    with pytest.raises(ValueError):
        gesture_study_store.delete("danced_chain")
    with pytest.raises(ST.StudyError):
        gesture_study_store.save(label="Broken", engine="kit", recipe=st.recipe,
                                 controls=[{"path": "parts.0.voice.length", "label": "L", "type": "float",
                                            "min": 0, "max": 99}])
    gesture_study_store.delete(saved.id)
    assert saved.id not in [s.id for s in gesture_study_store.list()["items"]]
    with pytest.raises(KeyError):
        gesture_study_store.delete(saved.id)


def test_api_lists_saves_validates_and_deletes():
    from axibridge.app import create_app

    c = TestClient(create_app())
    r = c.get("/api/gesture-studies")
    assert r.status_code == 200
    body = r.json()
    builtin = [s for s in body["studies"] if s["builtin"]]
    assert [s["id"] for s in builtin] == ORDER
    assert {o["id"] for o in body["library"]["hand"]} >= {"matisse", "aaron", "polygon_walk", "shikasta"}
    assert body["library"]["dance_trail"] and body["snapshot"] == FL.current_snapshot()
    choice = next(c_ for c_ in builtin[3]["controls"] if c_["key"] == "parts.0.modulators.0.a")
    assert "ruler" in choice["choices"]                          # the param's choices spelled out

    study = {k: v for k, v in builtin[1].items() if k not in ("builtin", "defaults")}
    r = c.post("/api/gesture-studies", json={"label": "Heavier", "study": study,
                                             "values": {"parts.0.modulators.0.amount": 1.6}})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["parent"] == {"id": "danced_chain", "version": 1}
    assert saved["recipe"]["parts"][0]["modulators"][0]["amount"] == 1.6
    assert saved["id"] in [s["id"] for s in c.get("/api/gesture-studies").json()["studies"]]

    r = c.post("/api/gesture-studies/validate", json={"study": study, "values": {"seed": 5}})
    assert r.status_code == 200 and r.json()["recipe"]["seed"] == 5
    broken = copy.deepcopy(study)
    broken["recipe"]["parts"][0]["voice"]["length"] = 1e6
    assert c.post("/api/gesture-studies/validate", json={"study": broken}).status_code == 400
    broken = copy.deepcopy(study)
    broken["recipe"]["frame"] = [1500, 1500]                      # the kit allows 2 m; the app does not
    assert c.post("/api/gesture-studies/validate", json={"study": broken}).status_code == 400
    broken = copy.deepcopy(study)
    broken["recipe"]["parts"][0]["voice"]["hands"] = ["matisse", "no_such_hand"]
    assert c.post("/api/gesture-studies/validate", json={"study": broken}).status_code == 400
    assert c.post("/api/gesture-studies", json={"label": "", "study": study}).status_code == 422

    assert c.delete("/api/gesture-studies/danced_chain").status_code == 400
    assert c.delete(f"/api/gesture-studies/{saved['id']}").status_code == 200
    assert c.delete(f"/api/gesture-studies/{saved['id']}").status_code == 404
    assert c.delete("/api/gesture-studies/Not.A.Study").status_code == 404


# ---------------------------------------------------------------------------
# Studies v2: pinned edits, the sampler, the chorus kept as a group
# ---------------------------------------------------------------------------

def _old_snapshot_layer_params(tmp_path, library_root):
    """Params of a layer kept under the CURRENT snapshot, then a refreeze that
    adds a hand: the layer's snapshot is now the older one."""
    kept = SRC.complete_params(params("three_voices", {"parts.1.voice.hand": "matisse"}))
    root = _temp_library(tmp_path, {("hand", "test_new_hand"): ("bubble", {"label": "Test hand"})})
    library_root(root)
    assert FL.current_snapshot() != kept["library"]
    return kept


def test_edits_of_a_resumed_layer_stay_on_its_own_snapshot(tmp_path, library_root):
    kept = _old_snapshot_layer_params(tmp_path, library_root)
    old = kept["library"]
    # an edit (another seed, another hand of ITS snapshot) keeps the snapshot and the pins it had
    edited = {**copy.deepcopy(kept), "values": {**kept["values"], "seed": 99, "parts.2.voice.hand": "aaron"}}
    again = SRC.complete_params(edited)
    assert again["library"] == old
    pins = {(x["kind"], x["id"]): x["hash"] for x in again["pins"]}
    before = {(x["kind"], x["id"]): x["hash"] for x in kept["pins"]}
    assert pins[("hand", "matisse")] == before[("hand", "matisse")]
    assert ("hand", "aaron") in pins
    assert all(k in before or k == ("hand", "aaron") for k in pins)      # only what a control names
    # the pinned layer's hand controls list ITS snapshot: the newer hand is refused there …
    with pytest.raises(ValidationError):
        SRC.Params(**{**kept, "values": {**kept["values"], "parts.2.voice.hand": "test_new_hand"}})
    assert "test_new_hand" not in [o["id"] for o in FL.options("hand", old)]
    # … and offered once the layer is updated to the current library on purpose
    updated = {k: v for k, v in kept.items() if k not in ("library", "pins")}
    up = SRC.complete_params({**updated, "values": {**kept["values"], "parts.2.voice.hand": "test_new_hand"}})
    assert up["library"] == FL.current_snapshot()


def test_library_options_endpoint_lists_a_pinned_snapshot(tmp_path, library_root):
    from axibridge.app import create_app

    kept = _old_snapshot_layer_params(tmp_path, library_root)
    c = TestClient(create_app())
    r = c.get(f"/api/gesture-studies/library/{kept['library']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current"] == FL.current_snapshot() and body["snapshot"] == kept["library"]
    assert "test_new_hand" not in {o["id"] for o in body["library"]["hand"]}
    assert "test_new_hand" in {o["id"] for o in c.get("/api/gesture-studies").json()["library"]["hand"]}
    assert c.get("/api/gesture-studies/library/" + "0" * 12).status_code == 404
    # validate resolves against the pinned snapshot too
    st = ST.builtin("three_voices").model_dump(mode="json")
    bad = {"study": st, "values": {"parts.2.voice.hand": "test_new_hand"}, "library": kept["library"],
           "pins": kept["pins"]}
    assert c.post("/api/gesture-studies/validate", json=bad).status_code == 400
    assert c.post("/api/gesture-studies/validate", json={**bad, "library": None, "pins": []}).status_code == 200


def test_sampler_seed_picks_a_whole_combination_and_a_kept_layer_stores_it():
    a = SRC.Params(**params("sampler", {"seed": 5})).run_recipe
    b = SRC.Params(**params("sampler", {"seed": 6})).run_recipe
    assert a != b and a["seed"] == 5 and 2 <= len(a["parts"]) <= 3
    assert a == SRC.Params(**params("sampler", {"seed": 5})).run_recipe            # deterministic
    kept = SRC.complete_params(params("sampler", {"seed": 5}))
    assert kept["sampled"]["of"] == ST.sample_key({"frame": [267.0, 180.0], "seed": 5})
    assert kept["sampled"]["recipe"] == a
    # the stored combination is what the layer draws, whatever the sampler would pick now
    other = copy.deepcopy(kept)
    other["sampled"]["recipe"] = b
    assert SRC.Params(**other).run_recipe == b
    # a different seed is a different sample (the stored one no longer applies)
    moved = {**copy.deepcopy(kept), "values": {"seed": 6}}
    assert SRC.Params(**moved).run_recipe == b
    assert fingerprint(gen(kept)) == fingerprint(gen(params("sampler", {"seed": 5})))
    with pytest.raises(ValidationError):
        SRC.Params(**params("sampler", {"seed": 5, "frame": 3}))


def test_sampler_save_and_validate_api():
    from axibridge.app import create_app

    c = TestClient(create_app())
    st = ST.builtin("sampler").model_dump(mode="json")
    r = c.post("/api/gesture-studies/validate", json={"study": st, "values": {"seed": 9}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"] and " x " in body["summary"] and body["run_recipe"]["seed"] == 9
    assert body["voices"] == []
    r = c.post("/api/gesture-studies", json={"label": "Found combination", "study": st, "values": {"seed": 9}})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["engine"] == "kit" and saved["recipe"] == body["run_recipe"]   # it keeps what it found
    assert saved["parent"] == {"id": "sampler", "version": 1}
    assert c.delete(f"/api/gesture-studies/{saved['id']}").status_code == 200


def test_chorus_voices_resolve_one_at_a_time_and_add_up_to_the_chorus():
    full = gen(params("chorus"))
    voices = [gen(params("chorus", voice=i)) for i in range(4)]
    assert all(voices) and sum(len(v) for v in voices) == len(full)
    assert fingerprint([q for v in voices for q in v]) == fingerprint(full)
    doc = SRC.generate(SRC.Params(**params("chorus")))
    assert [layer.color for layer in doc.layers] == ["#100F0F", "#AF3029", "#205EA6", "#24837B"]
    three = gen(params("chorus", {"arranger.voices": 3}))
    assert fingerprint(three) == fingerprint([q for v in voices[:3] for q in v])   # the first 3, exactly
    with pytest.raises(ValidationError):
        SRC.Params(**params("chorus", {"arranger.voices": 3}, voice=3))           # not sung
    with pytest.raises(ValidationError):
        SRC.Params(**params("danced_chain", voice=0))                             # not a voices study


def test_keep_chorus_makes_one_group_with_a_layer_per_voice_on_its_own_pen():
    from axibridge.session import session
    from axibridge.stores import pen_library

    before = session.project.model_copy(deep=True)
    n_layers, n_groups = len(session.project.layers), len(session.project.groups)
    group, layers = session.keep_gesture_study_voices(params("chorus", {"arranger.voices": 3}))
    assert group.name == "Chorus, several pens" and len(layers) == 3
    assert all(layer.group_id == group.id for layer in layers)
    assert [layer.source.params["voice"] for layer in layers] == [0, 1, 2]
    pens = [pen_library.get(layer.pen_id) for layer in layers]
    assert len({p.id for p in pens}) == 3
    assert [p.color.lower() for p in pens] == ["#100f0f", "#af3029", "#205ea6"]
    lib = {layer.source.params["library"] for layer in layers}
    assert lib == {FL.current_snapshot()}                                   # pinned once, the same for all
    assert len({json.dumps(layer.source.params["pins"]) for layer in layers}) == 1
    assert len({json.dumps(layer.transform.model_dump(), sort_keys=True) for layer in layers}) == 1
    for i, layer in enumerate(layers):
        assert fingerprint(session.source_geometry[layer.id]) == fingerprint(
            gen(params("chorus", {"arranger.voices": 3}, voice=i)))
    assert len(session.project.layers) == n_layers + 3 and len(session.project.groups) == n_groups + 1
    # a second chorus reuses the pens (by colour), never adds more
    _, again = session.keep_gesture_study_voices(params("chorus", {"arranger.voices": 2}))
    assert [layer.pen_id for layer in again] == [layer.pen_id for layer in layers[:2]]
    session.undo()
    session.undo()                                                          # one undo per keep
    assert [l.id for l in session.project.layers] == [l.id for l in before.layers]
    assert [g.id for g in session.project.groups] == [g.id for g in before.groups]
    with pytest.raises(ValueError):
        session.keep_gesture_study_voices(params("danced_chain"))


def test_keep_endpoint():
    from axibridge.app import create_app

    with TestClient(create_app()) as c:           # a project mutation: run the app's lifespan (events)
        _keep_endpoint(c)


def _keep_endpoint(c):
    r = c.post("/api/gesture-studies/keep", json={"params": params("chorus", {"arranger.voices": 2})})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["layers"]) == 2 and body["group"]["name"] == "Chorus, several pens"
    proj = c.get("/api/project").json()
    assert {l["group_id"] for l in proj["layers"] if l["id"] in {x["id"] for x in body["layers"]}} == \
        {body["group"]["id"]}
    assert c.post("/api/gesture-studies/keep", json={"params": params("danced_chain")}).status_code == 400
    r = c.post("/api/gesture-studies/validate", json={"study": ST.builtin("chorus").model_dump(mode="json")})
    assert [v["ink"] for v in r.json()["voices"]] == ["black", "red", "blue", "cyan"]
    r = c.post("/api/generators/preview", json={"module": "gesture_studies", "params": params("chorus")})
    layers = r.json()["layers"]
    assert [x["color"] for x in layers] == ["#100F0F", "#AF3029", "#205EA6", "#24837B"]
    assert sum(x["paths"] for x in layers) == len(r.json()["lines"])
