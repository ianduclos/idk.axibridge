"""Round-15 keeps: each exposed control changes actual preview geometry.

The defaults also keep their committed-research parity, and multi-ink sheets
keep as a group with one nonempty layer per ink. No physical app or plotter.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from axibridge.sources._gesture_studies import engine, frozen_library as FL, studies as ST
from axibridge.sources.gesture_studies import GestureStudiesSource

STUDIES = ("arch", "listen", "river_zoom")
GEOS_SENSITIVE = {"arch"}
ALTERNATIVES = {
    "arch": {
        "arranger.density": 0.6,
        "arranger.pens": 5,
        "arranger.mode": "lines",
        "arranger.duet": 1.0,
    },
    "listen": {
        "arranger.mask_p": 0.0,
        "arranger.river_p": 0.0,
        "arranger.pens": 4,
    },
    "river_zoom": {
        "parts.0.voice.schedule": "breath",
        "parts.0.voice.recur": 5,
        "parts.0.voice.zoom": 12.0,
        "parts.0.voice.start": 0.3,
        "parts.0.voice.river": 0.5,
        "parts.0.voice.pace": 0.0,
    },
}


@pytest.fixture(scope="module")
def client():
    from axibridge.app import create_app

    # Enter the lifespan: the event bus is a process singleton, and a previous
    # file's app may have left it holding a closed loop ("Event loop is closed"
    # on the first progress event of a preview). Startup attaches a live one.
    with TestClient(create_app()) as c:
        yield c


def _params(sid, values=None):
    return {"study": ST.builtin(sid).model_dump(mode="json"), "values": values or {}}


def _preview(client, sid, values=None):
    response = client.post("/api/generators/preview", json={
        "module": "gesture_studies", "params": _params(sid, values),
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["lines"], sid
    return data


def _geometry(data):
    # Include EVERY preview coordinate; changes of colour/metadata alone do not count.
    return hashlib.sha256(json.dumps(data["lines"], separators=(",", ":")).encode()).hexdigest()


@pytest.fixture(scope="module")
def defaults():
    return {}


@pytest.mark.parametrize("sid", STUDIES)
def test_each_nonseed_control_has_an_activity_probe(sid):
    st = ST.builtin(sid)
    assert 3 <= len(st.controls) <= 8
    assert {c.key for c in st.controls if c.key != "seed"} == set(ALTERNATIVES[sid])
    for c in st.controls:
        if c.key != "seed":
            assert ST.get_at(st.recipe, c.targets[0]) != ALTERNATIVES[sid][c.key]


@pytest.mark.parametrize("sid,key,value", [
    (sid, key, value) for sid, changes in ALTERNATIVES.items() for key, value in changes.items()
])
def test_every_nonseed_control_changes_preview_geometry(client, defaults, sid, key, value):
    if sid not in defaults:
        defaults[sid] = _geometry(_preview(client, sid))
    assert _geometry(_preview(client, sid, {key: value})) != defaults[sid], (sid, key)


@pytest.mark.parametrize("sid", STUDIES)
def test_new_default_matches_research_fixture(sid):
    from tools.gesture_studies.freeze import _summary

    st = ST.builtin(sid)
    lib = FL.FrozenLibrary()
    actual = _summary(engine.run_kit(ST.resolve(st, {}, lib), lib))
    fixture = json.loads((Path(__file__).parent / "fixtures/gesture_studies" / f"{sid}.json").read_text())
    assert actual["n_points"] == fixture["n_points"]
    assert [i[:3] for i in actual["inks"]] == [i[:3] for i in fixture["inks"]]
    # arch's flicker is the limb signs, which are GEOS-sensitive: under another
    # GEOS (or numpy) one 5-point ink drifts ~1e-8 mm. Same drawing, so a
    # cross-GEOS run stays tight, just not to the last bits.
    import shapely

    rtol = 1e-9 if sid not in GEOS_SENSITIVE or fixture["geos"] == shapely.geos_version_string else 1e-6
    np.testing.assert_allclose(actual["inks"], fixture["inks"], rtol=rtol, atol=1e-7)
    np.testing.assert_allclose(actual["sample"], fixture["sample"], rtol=rtol, atol=1e-7)


@pytest.mark.parametrize("sid", ["arch", "listen"])
def test_composed_studies_keep_one_layer_per_used_ink(sid):
    from axibridge.session import session

    src = GestureStudiesSource()
    params = _params(sid)
    full = src.generate(src.Params(**params))
    group, layers = session.keep_gesture_study_voices(params)
    assert group.name == ST.builtin(sid).label
    assert len(layers) == len(full.layers) >= 2
    assert len({layer.pen_id for layer in layers}) == len(layers)
    assert [layer.source.params["voice"] for layer in layers] == [layer.id - 1 for layer in full.layers]
    assert all(layer.source.params["library"] for layer in layers)
    for kept, expected in zip(layers, full.layers):
        single = src.generate(src.Params(**kept.source.params))
        assert len(single.layers) == 1
        assert single.layers[0].paths == expected.paths
    session.undo()
    assert not session.project.layers


def test_arch_default_is_the_15002_sheet():
    # Ian on 15002: "absolutely excellent". The default is that recipe, with one change Ian made on
    # 2026-10-19 (version 2): the line no longer runs through the middle of the swell.
    st = ST.builtin("arch")
    research = json.loads((Path(__file__).resolve().parents[1]
                           / "tools/gesture/results/arch-2-15002.recipe.json").read_text())
    strip = lambda r: {k: v for k, v in r.items() if k not in ("label", "notes")}  # noqa: E731
    mine = strip(st.recipe)
    assert mine["renderer"].pop("swell_line") == "outside" and st.version == 2
    assert mine == strip(research)
    assert st.recipe["seed"] == 15002
    assert st.recipe["arranger"]["families"] == "danced,swell,flicker,passer"   # the passer needs free3966


def test_arch_passer_free_opening_reads_no_file():
    # The accrue 3966 free hand is embedded data in the frozen kit, never a read of tools/.
    from axibridge.sources._gesture_studies.kit import voices_passage as vp

    src = Path(vp.__file__).read_text()
    assert "read_text" not in src and "json.load" not in src and "open(" not in src
    pts, info = vp.free_opening(FL.FrozenLibrary().load("hand", "river_belt"), (0.0, 0.0, 285.0, 198.0))
    assert info["seed"] == 3966 and len(pts) == info["points"] > 1000


def test_river_default_is_the_free_push_strip_at_constant_width():
    st = ST.builtin("river_zoom")
    r = st.recipe
    assert r["frame"] == [300.0, 110.0]
    assert r["seed"] == 1491
    assert r["parts"][0]["voice"]["id"] == "river_zoom"
    assert r["parts"][0]["voice"]["course"] == "free"
    assert r["parts"][0]["voice"]["schedule"] == "push"
    lib = FL.FrozenLibrary()
    sheet = engine.run_kit(ST.resolve(st, {}, lib), lib)
    assert len(sheet.marks) == len(sheet.inks) == 1
    assert {ink.pen for ink in sheet.inks} == {0.3}
    assert not sheet.inks[0].closed
    assert not sheet.inks[0].filled


def test_general_zoom_is_callable_on_another_hand_and_as_a_modulator():
    import copy

    from axibridge.sources._gesture_studies import kit

    folder = ST.STUDIES_DIR / "river_zoom"
    recipe = json.loads((folder / "hand.recipe.json").read_text())
    lib = FL.FrozenLibrary()
    a = kit.run(recipe, library=lib)
    other = copy.deepcopy(recipe)
    other["parts"][0]["voice"]["hand"] = "lichtenberg"
    b = kit.run(other, library=lib)
    assert len(a.inks) == len(b.inks) == 1
    assert a.inks[0].points.tolist() != b.inks[0].points.tolist()
    assert a.inks[0].pen == b.inks[0].pen == 0.3
    plain = copy.deepcopy(recipe)
    plain["parts"][0] = {"voice": {"id": "hand", "hand": "dancer_cristel", "length": 6.0}}
    modulated = copy.deepcopy(plain)
    modulated["parts"][0]["modulators"] = [{"id": "lcorp_zoom_mod", "schedule": "push", "zoom": 24.0}]
    c, d = (kit.run(r, library=lib) for r in (plain, modulated))
    assert c.inks and d.inks
    assert c.inks[0].points.tolist() != d.inks[0].points.tolist()


def test_frozen_kit_import_does_not_require_pillow_or_matplotlib():
    import subprocess
    import sys

    probe = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split(".")[0] in {"PIL", "matplotlib"}:
        raise AssertionError("image library imported eagerly: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from axibridge.sources._gesture_studies import kit
assert not kit.DISCOVERY_ERRORS, kit.DISCOVERY_ERRORS
'''
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
