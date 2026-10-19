"""Synthesis (S4): the frozen kit, the generator, keep as a group, the HTTP boundary.

Contract: docs/SYNTHESIS.md. Parity fixtures are written by tools/synthesis/freeze.py
from the HEAD research kit + library (after checking the frozen copy reproduces them)."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
import shapely
from fastapi.testclient import TestClient

from axibridge.sources import synthesis as SY
from axibridge.sources._synthesis import engine as EN
from axibridge.sources._synthesis import frozen_library as FL

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "axibridge/sources/_synthesis"
FIXTURES = REPO / "tests/fixtures/synthesis"
CASES = sorted(p.stem for p in FIXTURES.glob("*.json"))


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture(scope="module")
def client():
    from axibridge.app import create_app
    return TestClient(create_app())


@pytest.fixture(scope="module")
def listen(client) -> dict:
    r = client.post("/api/synthesis/start", json={"gallery": "writer:listen", "seed": 15102})
    assert r.status_code == 200, r.text
    return r.json()["score"]


def params(score, **kw) -> SY.SynthesisParams:
    return SY.SynthesisParams(score=copy.deepcopy(score), **kw)


def paths_of(doc):
    return [(p.filled, tuple(p.points)) for layer in doc.layers for p in layer.paths]


# the frozen kit ------------------------------------------------------------------------------------

def test_frozen_files_are_not_hand_edited():
    manifest = json.loads((APP / "kit/FROZEN.json").read_text())
    assert manifest["files"]
    for rel, info in manifest["files"].items():
        assert hashlib.sha256((APP / rel).read_bytes()).hexdigest() == info["sha256"], rel


def test_the_synthesis_kit_is_its_own_copy():
    from axibridge.sources._gesture_studies import devices as GSD
    from axibridge.sources._gesture_studies.kit import core as gs_core
    from axibridge.sources._synthesis import devices as DV
    from axibridge.sources._synthesis.kit import core as syn_core
    assert gs_core is not syn_core and gs_core.Mark is not syn_core.Mark
    assert "mdoc_staff" in DV._gs.CATALOGUE and "mdoc_staff" not in GSD.CATALOGUE
    assert isinstance(FL.FrozenLibrary(), EN._kl.Library)
    # the shared library: the very same folder Gesture Studies reads
    from axibridge.sources._gesture_studies import frozen_library as GSL
    assert FL.ROOT == GSL.ROOT
    assert FL.current_snapshot() in GSL.index()["history"]


@pytest.mark.parametrize("name", CASES)
def test_parity_with_the_research_kit(name):
    fx = fixture(name)
    p = params(fx["score"], library=fx["library"])
    sheet, _ = EN.play(p.score, p._lib)
    got = []
    for ink in sheet.inks:
        a = np.asarray(ink.points, float)
        got.append([len(a), bool(ink.closed), bool(ink.filled), float(ink.pen), *a[0], *a[-1],
                    a[:, 0].sum(), a[:, 1].sum(), (a[:, 0] ** 2).sum(), (a[:, 1] ** 2).sum()])
    assert len(got) == len(fx["inks"])
    exact = fx["geos"] == shapely.geos_version_string
    same = sum(a[:3] == b[:3] and np.allclose(a[3:], b[3:], rtol=1e-9, atol=1e-7) for a, b in zip(got, fx["inks"]))
    if exact:
        assert same == len(got)
    else:                                     # another GEOS: the same drawing, the occluding rims exact
        assert Counter(tuple(a[1:3]) for a in got)[(True, True)] == Counter(
            tuple(b[1:3]) for b in fx["inks"])[(True, True)]
        assert same >= 0.9 * len(got)
    allp = np.vstack([np.asarray(i.points, float) for i in sheet.inks])
    assert abs(len(allp) - fx["n_points"]) <= 0.01 * fx["n_points"]


@pytest.mark.parametrize("name", [n for n in CASES if "compose" in fixture(n)["made"]])
def test_the_frozen_writers_write_the_fixture_scores(name):
    fx = fixture(name)
    w, seed, prm = fx["made"]["compose"]
    score = EN.compose(w, lib=FL.FrozenLibrary(fx["library"]), frame=[250.0, 175.0], seed=seed, params=prm)
    if fx["made"].get("devices"):
        score = {**score, "devices": fx["made"]["devices"]}
    want = fx["score"]
    assert [L["id"] for L in json.loads(json.dumps(score))["layers"]] == [L["id"] for L in want["layers"]]
    assert [R["id"] for R in score["relations"]] == [R["id"] for R in want["relations"]]
    assert [L["pen"] for L in score["layers"]] == [L["pen"] for L in want["layers"]]


# params ----------------------------------------------------------------------------------------------

def test_default_params_validate_and_draw():
    p = SY.SynthesisParams()
    doc = SY.SynthesisSource().generate(p)
    assert doc.layers and doc.layers[0].paths


def test_params_are_stored_normalised_and_idempotent(listen):
    p = params(listen)
    q = params(p.score)
    assert q.score == p.score


@pytest.mark.parametrize("mutate, match", [
    (lambda s: s.update(layers=[copy.deepcopy(s["layers"][0]) | {"id": f"X{i}"} for i in range(25)]), "24 layers"),
    (lambda s: s.update(relations=[{"id": f"R{i}", "kind": "crossing", "src": "*", "dst": "*"}
                                   for i in range(65)]), "64 relations"),
    (lambda s: s.update(frame=[700, 175]), "frame"),
    (lambda s: s["layers"].append({"id": "Big", "lines": [[[float(i % 200), float(i % 150)] for i in range(150_001)]]}),
     "literal points"),
    (lambda s: s["layers"].append({"id": "Bad", "part": {"voice": {"id": "no_such_voice"}}}), "no_such_voice"),
])
def test_bounds_and_executor_errors_are_refused(listen, mutate, match):
    s = copy.deepcopy(listen)
    mutate(s)
    with pytest.raises(ValueError, match=match):
        params(s)


def test_show_layer_and_measure_rules(listen):
    unseen = next((L["id"] for L in listen["layers"] if L["role"] == "unseen"), None)
    with pytest.raises(ValueError, match="needs `layer`"):
        params(listen, show="layer")
    with pytest.raises(ValueError, match="Measure"):
        params(listen, show="measure")
    with pytest.raises(ValueError, match="show=layer"):
        params(listen, layer="L0")
    if unseen:
        with pytest.raises(ValueError, match="unseen"):
            params(listen, show="layer", layer=unseen)


def test_members_resolve_the_same_sheet_as_the_whole(listen):
    src = SY.SynthesisSource()
    whole = src.generate(params(listen))
    shown = [L["id"] for L in listen["layers"] if L["role"] != "unseen"]
    members = []
    for lid in shown:
        doc = src.generate(params(listen, show="layer", layer=lid))
        members += paths_of(doc)
    assert sorted(members) == sorted(paths_of(whole))


def test_preview_extra_carries_the_played_summary(listen):
    src = SY.SynthesisSource()
    doc = src.generate(params(listen))
    extra = src.preview_extra(doc)["synthesis"]
    assert [x["id"] for x in extra["layers"]] == [L["id"] for L in listen["layers"]
                                                 if L["role"] != "unseen" and any(
                                                     g["id"] == L["id"] for g in extra["layers"])]
    assert set(extra["relations"]) == {R["id"] for R in listen["relations"]}
    assert any(r["fired"] for r in extra["relations"].values())
    assert all({"fired", "applied", "outcomes"} <= set(r) for r in extra["relations"].values())


def test_complete_params_pins_the_library_and_holds_the_drawing(listen):
    src = SY.SynthesisSource()
    done = src.complete_params({"score": listen})
    assert done["library"] == FL.current_snapshot()
    hands = {p["id"] for p in done["pins"] if p["kind"] == "hand"}
    used = {L["part"]["voice"].get("hand") for L in listen["layers"] if "part" in L} - {None}
    assert used and used <= hands
    assert paths_of(src.generate(SY.SynthesisParams(**done))) == paths_of(src.generate(params(listen)))


# keep as a group -------------------------------------------------------------------------------------

def _project(client):
    return client.get("/api/project").json()


def test_keep_makes_one_group_one_undo_step_and_replace_swaps_it(client, listen):
    before = len(_project(client)["layers"])
    r = client.post("/api/synthesis/keep", json={"params": {"score": listen}})
    assert r.status_code == 200, r.text
    group, layers = r.json()["group"], r.json()["layers"]
    drawn = [L for L in listen["layers"] if L["role"] != "unseen"]
    assert 1 <= len(layers) <= len(drawn)
    assert all(x["group_id"] == group["id"] and x["source"]["params"]["show"] == "layer" for x in layers)
    assert len({x["pen_id"] for x in layers}) == len(layers)          # a pen per member, by its ink
    assert all(x["source"]["params"]["library"] for x in layers)
    proj = _project(client)
    assert len(proj["layers"]) == before + len(layers)
    # replace: same group, same place in the stack, a recomposed score
    again = client.post("/api/synthesis/recompose", json={"score": listen, "seed": 15301}).json()["score"]
    r2 = client.post("/api/synthesis/keep", json={"params": {"score": again}, "replace": group["id"]})
    assert r2.status_code == 200, r2.text
    assert r2.json()["group"]["id"] == group["id"]
    proj = _project(client)
    mine = [x for x in proj["layers"] if x.get("group_id") == group["id"]]
    assert [x["id"] for x in mine] == [x["id"] for x in r2.json()["layers"]]
    assert len(proj["layers"]) == before + len(mine)
    # undo the replace, then the keep: back to where we started
    assert client.post("/api/undo").status_code == 200
    assert [x["id"] for x in _project(client)["layers"] if x.get("group_id") == group["id"]] == [x["id"] for x in layers]
    assert client.post("/api/undo").status_code == 200
    assert len(_project(client)["layers"]) == before


def test_keep_with_devices_adds_a_measure_layer(client, listen):
    s = {**listen, "devices": [{"id": "mdoc_staff", "place": "beside", "side": "bottom"}]}
    r = client.post("/api/synthesis/keep", json={"params": {"score": s}})
    assert r.status_code == 200, r.text
    layers = r.json()["layers"]
    assert layers[-1]["name"] == "Measure" and layers[-1]["source"]["params"]["show"] == "measure"
    client.post("/api/undo")


def test_replace_refuses_a_group_that_is_not_a_synthesis(client):
    r = client.post("/api/synthesis/keep", json={"params": {"score": SY.DEFAULT_SCORE}, "replace": "nosuchgroup"})
    assert r.status_code == 404


# the HTTP boundary ---------------------------------------------------------------------------------

def test_catalogue(client):
    cat = client.get("/api/synthesis").json()
    assert {w["id"] for w in cat["writers"]} == {"listen", "arch", "ccolour"}
    kinds = {r["id"]: r["phase"] for r in cat["relations"]}
    assert kinds["crossing"] == "contact" and kinds["imitate"] == "grow"
    assert {"writer:listen", "writer:arch", "study:leaf_miner"} <= {g["id"] for g in cat["gallery"]}
    assert not any(g["id"] in ("study:hand_drift", "study:sampler") for g in cat["gallery"])
    assert {d["id"] for d in cat["devices"]} >= {"meas_arcs", "mdoc_staff", "mdoc_unheard"}
    assert cat["limits"]["layers"] == SY.MAX_LAYERS and cat["snapshot"] == FL.current_snapshot()
    assert cat["inks"]["black"].startswith("#") and cat["library"]["hand"]


def test_a_study_opens_as_one_sealed_layer_drawing_the_study(client):
    from axibridge.sources import gesture_studies as GS
    from axibridge.sources._gesture_studies import studies as ST
    s = client.post("/api/synthesis/start", json={"gallery": "study:leaf_miner"}).json()["score"]
    assert [L["role"] for L in s["layers"]] == ["sealed"]
    mine = SY.SynthesisSource().generate(params(s))
    theirs = GS.GestureStudiesSource().generate(GS.GestureStudiesParams(study=ST.builtin("leaf_miner")))
    a = np.vstack([np.asarray(p.points) for L in mine.layers for p in L.paths])
    b = np.vstack([np.asarray(p.points) for L in theirs.layers for p in L.paths])
    assert abs(len(a) - len(b)) <= 0.01 * len(b) and np.allclose(a.mean(axis=0), b.mean(axis=0), atol=0.5)


def test_recompose_keeps_the_lock_and_builds_the_palette_around_it(client, listen):
    lock = next(L for L in listen["layers"] if L["role"] == "speaker")
    keep_rel = listen["relations"][-1]["id"]
    r = client.post("/api/synthesis/recompose", json={"score": listen, "seed": 15201, "locked": [lock["id"]],
                                                      "locked_relations": [keep_rel]})
    assert r.status_code == 200, r.text
    out = r.json()["score"]
    kept = next(L for L in out["layers"] if L["id"] == lock["id"])
    assert kept.get("lock") and kept.get("pin") and kept["pen"] == lock["pen"]
    assert lock["pen"] in out["decisions"]["writers"][-1]["decisions"]["palette"]
    assert keep_rel in {R["id"] for R in out["relations"]} or keep_rel in r.json()["dropped"]
    assert out["seed"] == 15201                   # the first writer on a sheet sets its seed; the lock keeps its own
    assert kept["seed"] == lock.get("seed", kept["seed"])


def test_lock_unlock_and_ripple_holds(client, listen):
    spk = next(L["id"] for L in listen["layers"] if L["role"] == "speaker")
    locked = client.post("/api/synthesis/lock", json={"score": listen, "ids": [spk]}).json()["score"]
    assert next(L for L in locked["layers"] if L["id"] == spk).get("pin")
    free = client.post("/api/synthesis/unlock", json={"score": locked, "ids": [spk]}).json()["score"]
    assert not next(L for L in free["layers"] if L["id"] == spk).get("pin")
    shown = {L["id"] for L in listen["layers"] if L["role"] != "unseen"}
    none = client.post("/api/synthesis/hold", json={"score": listen, "edited": spk, "ripple": "none"}).json()
    assert set(none["held"]) == shown - {spk}
    assert set(none["score"]["decisions"]["bench"]["held"]) == shown - {spk}
    direct = client.post("/api/synthesis/hold", json={"score": listen, "edited": spk, "ripple": "direct"}).json()
    assert set(direct["held"]) < set(none["held"])
    allr = client.post("/api/synthesis/hold", json={"score": listen, "edited": spk, "ripple": "all"}).json()
    assert allr["held"] == []
    released = client.post("/api/synthesis/unlock", json={"score": none["score"], "ids": none["held"]}).json()
    assert released["score"]["decisions"]["bench"]["held"] == []


def test_locking_changes_nothing_by_itself(client, listen):
    src = SY.SynthesisSource()
    base = paths_of(src.generate(params(listen)))
    shown = [L["id"] for L in listen["layers"] if L["role"] != "unseen"]
    every = client.post("/api/synthesis/lock", json={"score": listen, "ids": shown}).json()["score"]
    assert paths_of(src.generate(params(every))) == base


def test_ripple_none_moves_only_the_edited_layer(client, listen):
    spk = next(L for L in listen["layers"] if L["role"] == "speaker")
    held = client.post("/api/synthesis/hold", json={"score": listen, "edited": spk["id"], "ripple": "none"}).json()
    edited = copy.deepcopy(held["score"])
    L = next(x for x in edited["layers"] if x["id"] == spk["id"])
    L["part"]["voice"]["hand"] = "hokusai" if L["part"]["voice"].get("hand") != "hokusai" else "matisse"
    src = SY.SynthesisSource()
    for other in held["held"]:
        a = src.generate(params(held["score"], show="layer", layer=other))
        b = src.generate(params(edited, show="layer", layer=other))
        assert paths_of(a) == paths_of(b), other
    assert paths_of(src.generate(params(held["score"]))) == paths_of(src.generate(params(listen)))


def test_validate_reports_the_reason(client, listen):
    bad = copy.deepcopy(listen)
    bad["relations"].append({"id": "Rx", "kind": "imitate", "src": bad["layers"][-1]["id"],
                             "dst": bad["layers"][1]["id"]})
    r = client.post("/api/synthesis/validate", json={"score": bad})
    assert r.status_code == 400 and "EARLIER" in r.json()["detail"]


def test_saved_syntheses_round_trip(client, listen):
    r = client.post("/api/synthesis/saved", json={"label": "My listen", "score": listen})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert sid in {x["id"] for x in client.get("/api/synthesis/saved").json()["items"]}
    opened = client.post("/api/synthesis/start", json={"gallery": f"saved:{sid}"}).json()["score"]
    assert opened == params(listen).score
    assert client.delete(f"/api/synthesis/saved/{sid}").status_code == 200
    assert client.delete(f"/api/synthesis/saved/{sid}").status_code == 404
