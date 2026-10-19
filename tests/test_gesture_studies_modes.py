"""Study modes: river_zoom's line source, river | relay of hands (2026-10-19).

Ian on the round-16 distinct-hands relay (hdist-4-relay, panel 0): "yess thats
whats up … commit it to the previous line study we saved". The river mode must
stay the study exactly as it was kept: its recipe, its controls and every
drawing they make are checked against the study as it stood before modes
(`fixtures/gesture_studies/before_modes/river_zoom.study.json`), which is also
what every layer kept before this change carries. The relay mode is the
research recipe in the river study's frame, frozen and parity-checked by
tools/gesture_studies/freeze.py (`river_zoom@relay.json`).
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from axibridge.registry import get_source, load_builtin_modules
from axibridge.sources._gesture_studies import engine
from axibridge.sources._gesture_studies import frozen_library as FL
from axibridge.sources._gesture_studies import studies as ST

load_builtin_modules()
SRC = get_source("gesture_studies")
FIXTURES = Path(__file__).parent / "fixtures/gesture_studies"
BEFORE = json.loads((FIXTURES / "before_modes/river_zoom.study.json").read_text())
RELAY = {"line_source": "relay"}
ROUTE = ["river_bend", "shikasta", "trail_borer", "fly_fru"]
# the river controls' alternative values (as test_gesture_studies_new_alive), and the seed
RIVER_VALUES = [{}, {"parts.0.voice.schedule": "breath"}, {"parts.0.voice.recur": 5},
                {"parts.0.voice.zoom": 12.0}, {"parts.0.voice.start": 0.3}, {"parts.0.voice.river": 0.5},
                {"parts.0.voice.pace": 0.0}, {"seed": 7}]
# every relay control but the seed, with a value that must change the drawing
RELAY_ALTERNATIVES = {"parts.0.voice.hands": ["river_bend", "shikasta", "matisse"],
                      "parts.0.voice.R_mm": 40.0,
                      "parts.0.voice.peak_fine_mm": 10.0}


def study():
    return ST.builtin("river_zoom")


def doc_of(st, values):
    return SRC.generate(SRC.Params(study=st if isinstance(st, dict) else st.model_dump(mode="json"), values=values))


def exact(doc):
    """Every coordinate, filled flag and the frame: equal means bit-identical."""
    return (doc.width, doc.height, [[(p.filled, list(map(tuple, p.points))) for p in layer.paths]
                                    for layer in doc.layers])


def digest(doc):
    return hashlib.sha256(json.dumps(exact(doc)).encode()).hexdigest()


# ---------------------------------------------------------------------------
# the river mode is the study as it was
# ---------------------------------------------------------------------------

def test_river_mode_is_the_study_as_it_was_kept():
    st = json.loads((ST.STUDIES_DIR / "river_zoom/study.json").read_text())
    for k, v in BEFORE.items():
        if k != "notes":                                   # the notes now also describe the relay
            assert st[k] == v, k
    assert set(st) - set(BEFORE) == {"modes"}
    assert [m["id"] for m in st["modes"]["choices"]] == ["river", "relay"]
    assert study().model_dump(exclude={"notes", "modes"}) == ST.Study(**BEFORE).model_dump(exclude={"notes"})


@pytest.mark.parametrize("values", RIVER_VALUES, ids=lambda v: ",".join(v) or "defaults")
def test_river_drawing_is_bit_identical(values):
    lib = FL.FrozenLibrary()
    before = ST.Study(**BEFORE)
    assert ST.resolve(study(), values, lib) == ST.resolve(before, values, lib)
    assert ST.resolve(study(), {**values, "line_source": "river"}, lib) == ST.resolve(before, values, lib)
    old = exact(doc_of(BEFORE, values))
    assert exact(doc_of(study(), values)) == old
    assert exact(doc_of(study(), {**values, "line_source": "river"})) == old


def test_a_layer_kept_before_modes_resolves_exactly_as_before():
    kept = SRC.complete_params({"study": BEFORE, "values": {"parts.0.voice.zoom": 12.0}})
    p = SRC.Params(**kept)
    assert p.study.modes is None
    assert "modes" not in p.model_dump(mode="json")["study"]     # a study without modes dumps as it did
    assert json.loads(p.model_dump_json())["study"] == ST.Study(**BEFORE).model_dump(mode="json")
    assert exact(SRC.generate(p)) == exact(doc_of(study(), {"parts.0.voice.zoom": 12.0}))


def test_studies_without_modes_dump_without_the_key():
    for st in ST.builtin_studies():
        if st.id != "river_zoom":
            assert "modes" not in st.model_dump(mode="json") and "modes" not in json.loads(st.model_dump_json())


def test_river_defaults_and_controls_are_unchanged():
    assert ST.defaults(study()) == ST.defaults(ST.Study(**BEFORE))
    checked = ST.check_study(study())
    assert [c.key for c in checked.controls] == [c["path"] for c in BEFORE["controls"]]
    assert all(ST.acts(checked, {}, c) for c in checked.controls)
    assert not any(ST.acts(checked, RELAY, c) for c in checked.controls if c.key != "seed")


# ---------------------------------------------------------------------------
# the relay mode
# ---------------------------------------------------------------------------

def test_relay_default_is_the_research_relay_in_the_river_frame():
    lib = FL.FrozenLibrary()
    recipe = ST.resolve(study(), RELAY, lib)
    research = json.loads((Path(__file__).resolve().parents[1]
                           / "tools/gesture/results/hdist-4-relay.recipe.json").read_text())["panels"][0]
    assert recipe["frame"] == [300.0, 110.0] and recipe["seed"] == 3001
    assert recipe["parts"][0]["voice"] == ST._kit_recipe({**research, "frame": [300.0, 110.0]}, lib)["parts"][0]["voice"]
    assert research["seed"] == 3001 and research["margin"] == recipe["margin"]
    assert recipe["parts"][0]["voice"]["hands"] == ROUTE and recipe["parts"][0]["voice"]["source"] == "relay"
    assert recipe["renderer"] == research["renderer"]           # lcorp_ink, by voice: an ink per hand
    one, values = ST.active(study(), RELAY)
    assert values == {} and one.modes is None
    assert [c.key for c in one.controls] == [*RELAY_ALTERNATIVES, "seed"]
    assert 3 <= len(one.controls) <= 4


def test_relay_matches_the_research_kit():
    """The fixture is written by freeze.py from the HEAD research kit + library."""
    from tools.gesture_studies.freeze import _summary

    lib = FL.FrozenLibrary()
    actual = _summary(engine.run_kit(ST.resolve(study(), RELAY, lib), lib))
    fixture = json.loads((FIXTURES / "river_zoom@relay.json").read_text())
    assert fixture["version"] == study().version
    assert actual["n_points"] == fixture["n_points"]
    assert [i[:3] for i in actual["inks"]] == [i[:3] for i in fixture["inks"]]
    np.testing.assert_allclose(actual["inks"], fixture["inks"], rtol=1e-9, atol=1e-7)
    np.testing.assert_allclose(actual["sample"], fixture["sample"], rtol=1e-9, atol=1e-7)


def test_relay_renders_deterministically_one_layer_coloured_by_hand():
    from axibridge.sources import gesture_studies as GS

    GS.clear_slow_cache()
    a = doc_of(study(), RELAY)
    GS.clear_slow_cache()
    b = doc_of(study(), RELAY)
    assert a is not b and exact(a) == exact(b)
    assert len(a.layers) == 1 and a.layers[0].paths and (a.width, a.height) == (300.0, 110.0)
    assert digest(a) != digest(doc_of(study(), {}))
    colours = [r["color"] for r in SRC.preview_styles(a)]
    assert len(set(colours)) == 4                              # black, blue, red, green: one per hand
    assert {r["width"] for r in SRC.preview_styles(a)} == {0.3}


@pytest.mark.parametrize("key", list(RELAY_ALTERNATIVES) + ["seed"])
def test_every_relay_control_is_alive(key):
    checked = ST.check_study(study())
    one, _ = ST.active(checked, RELAY)
    c = next(x for x in one.controls if x.key == key)
    assert ST.acts(checked, RELAY, c)
    value = 3002 if key == "seed" else RELAY_ALTERNATIVES[key]
    assert ST.get_at(one.recipe, c.targets[0]) != value
    assert digest(doc_of(study(), {**RELAY, key: value})) != digest(doc_of(study(), RELAY)), key


def test_a_kept_relay_layer_pins_its_hands_and_resolves():
    from axibridge.session import session

    values = {**RELAY, "parts.0.voice.hands": ["shikasta", "river_bend"]}
    kept = SRC.complete_params({"study": study().model_dump(mode="json"), "values": values})
    assert kept["library"] == FL.current_snapshot()
    assert {(x["kind"], x["id"]) for x in kept["pins"]} == {("hand", "shikasta"), ("hand", "river_bend")}
    preview = doc_of(study(), values)
    assert exact(SRC.generate(SRC.Params(**kept))) == exact(preview)
    # through the project, as the bench's Keep adds it, and back out of a saved project's JSON
    before = len(session.project.layers)
    layer = session.add_generated_layer("gesture_studies", kept)
    try:
        assert layer.source.params["values"] == values and layer.source.params["pins"] == kept["pins"]
        paths = [p for x in preview.layers for p in x.paths]
        assert session.source_geometry[layer.id] == paths
        again = SRC.Params(**json.loads(json.dumps(layer.source.params)))
        assert exact(SRC.generate(again)) == exact(preview)
    finally:
        session.undo()
    assert len(session.project.layers) == before


# ---------------------------------------------------------------------------
# the format
# ---------------------------------------------------------------------------

def test_mode_values_are_validated():
    lib = FL.FrozenLibrary()
    with pytest.raises(ST.StudyError, match="not one of"):
        ST.resolve(study(), {"line_source": "lake"}, lib)
    with pytest.raises(ST.StudyError, match="unknown control value"):        # the other mode's controls
        ST.resolve(study(), {**RELAY, "parts.0.voice.zoom": 12.0}, lib)
    with pytest.raises(ST.StudyError, match="unknown control value"):
        ST.resolve(study(), {"parts.0.voice.hands": ROUTE}, lib)
    with pytest.raises(ValidationError):
        SRC.Params(study=study().model_dump(mode="json"), values={**RELAY, "parts.0.voice.hands": ["nobody"]})


def test_modes_are_validated():
    raw = study().model_dump(mode="json")
    bad = copy.deepcopy(raw)
    bad["modes"]["key"] = "seed"
    with pytest.raises(ValidationError, match="also a control"):
        ST.Study(**bad)
    bad = copy.deepcopy(raw)
    bad["modes"]["choices"][0]["recipe"] = bad["recipe"]
    with pytest.raises(ValidationError, match="carries neither"):
        ST.Study(**bad)
    bad = copy.deepcopy(raw)
    del bad["modes"]["choices"][1]["controls"]
    with pytest.raises(ValidationError, match="its own recipe and controls"):
        ST.Study(**bad)
    bad = copy.deepcopy(raw)
    bad["modes"]["choices"][1]["controls"][1]["max"] = 9999.0          # beyond the voice param's bounds
    with pytest.raises(ST.StudyError):
        ST.check_study(ST.Study(**bad))
    bad = copy.deepcopy(raw)
    bad["modes"]["choices"][1]["recipe"]["parts"][0]["voice"]["hands"] = ["nobody"]
    with pytest.raises(ST.StudyError):
        ST.check_study(ST.Study(**bad))


def test_api_lists_modes_and_a_fork_saves_the_chosen_mode():
    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        listed = next(s for s in c.get("/api/gesture-studies").json()["studies"] if s["id"] == "river_zoom")
        assert listed["modes"]["key"] == "line_source"
        relay = listed["modes"]["choices"][1]
        assert relay["label"] == "relay of hands" and relay["controls"][0]["type"] == "hands"
        st = {k: v for k, v in listed.items() if k not in ("builtin", "defaults")}
        r = c.post("/api/gesture-studies/validate", json={"study": st, "values": {**RELAY, "seed": 5}})
        assert r.status_code == 200, r.text
        assert r.json()["recipe"]["seed"] == 5 and r.json()["recipe"]["parts"][0]["voice"]["id"] == "hdist_zoom"
        assert "modes" not in r.json()
        r = c.post("/api/gesture-studies", json={"label": "Relay fork", "study": st, "values": RELAY})
        assert r.status_code == 200, r.text
        saved = r.json()
        assert saved["parent"] == {"id": "river_zoom", "version": 1} and "modes" not in saved
        assert saved["recipe"]["parts"][0]["voice"]["hands"] == ROUTE
        assert [x["key"] for x in saved["controls"]] == [*RELAY_ALTERNATIVES, "seed"]
        assert c.post("/api/gesture-studies/validate",
                      json={"study": st, "values": {"line_source": "lake"}}).status_code == 400
        assert c.delete(f"/api/gesture-studies/{saved['id']}").status_code == 200
