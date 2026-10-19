"""Gesture Studies, Measure (study bench v3 move G, 2026-10-19): the round-15
measuring devices, frozen with the kit, laid on a study as an optional layer.

Ian: "a selection of these to be added as a separate layer"; the pen's flight
"has to be optional". Covered here: the frozen devices draw what the research
devices drew (fixtures written by tools/gesture_studies/freeze.py), the
`devices` param is validated against the registry, `beside` grows the frame,
the preview reports each device's run and what it read, and Keep with devices
makes a group (drawing + a Measure layer on its own pen) in one undo step,
while Keep without devices is unchanged."""
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
import shapely
from fastapi.testclient import TestClient
from pydantic import ValidationError

from axibridge.registry import get_source, load_builtin_modules
from axibridge.sources._gesture_studies import devices as DV
from axibridge.sources._gesture_studies import engine
from axibridge.sources._gesture_studies import frozen_library as FL
from axibridge.sources._gesture_studies import studies as ST

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/gesture_studies/devices"
load_builtin_modules()
SRC = get_source("gesture_studies")
PROCESS = {"meas_air", "meas_ledger", "meas_arcs", "meas_inventory", "meas_stations", "meas_turning", "meas_roll"}
GENERAL = {"scale_ruler", "density_isoline", "heading_rose", "arc_ticks", "survey_marks", "misfit_grid"}
ROSE = {"id": "heading_rose", "place": "beside", "side": "right", "size": 60}
RULER = {"id": "scale_ruler", "place": "margin", "side": "bottom", "size": 22}


def params(sid, values=None, **extra):
    return {"study": ST.builtin(sid).model_dump(mode="json"), "values": values or {}, **extra}


def doc_of(p):
    return SRC.generate(SRC.Params(**p))


def paths_of(doc):
    return [q for layer in doc.layers for q in layer.paths]


def fingerprint(paths):
    return [(p.filled, len(p.points), [round(v, 6) for v in p.points[0] + p.points[-1]]) for p in paths]


# ---------------------------------------------------------------------------
# the freeze: every device reaches the frozen registry and draws as the research did
# ---------------------------------------------------------------------------

def test_every_device_is_frozen_and_offered():
    cat = DV.catalogue()
    assert {d["id"] for d in cat} == PROCESS | GENERAL and len(cat) == 13
    assert {d["id"] for d in cat if d["family"] == "process"} == PROCESS
    from axibridge.sources._gesture_studies.kit import _devices
    assert set(_devices._DEVICES) >= PROCESS | GENERAL
    manifest = json.loads((ROOT / "axibridge/sources/_gesture_studies/kit/FROZEN.json").read_text())
    for name in ("_devices", "_score", "devices_meas_read", "devices_measg1", "devices_measg2"):
        assert name in manifest["kit_modules"]
    for d in cat:
        assert 2 <= len(d["shown"]) <= 3 and all(x["label"] for x in d["shown"])
        assert DV.check_specs([d["default"]], FL.FrozenLibrary()) == [d["default"]]      # defaults are valid
    by = {d["id"]: d["default"] for d in cat}
    # the write-ups' placements: the pen's flight over, ledger beside, arcs beside the bottom,
    # the ruler in the bottom margin, the grid under at a low strength, the rose beside
    assert by["meas_air"]["place"] == "over" and by["meas_ledger"]["place"] == "beside"
    assert (by["meas_arcs"]["place"], by["meas_arcs"]["side"]) == ("beside", "bottom")
    assert (by["scale_ruler"]["place"], by["scale_ruler"]["side"]) == ("margin", "bottom")
    assert by["misfit_grid"]["place"] == "under" and 0 < by["misfit_grid"]["strength"] < 4.0
    assert by["heading_rose"]["place"] == "beside"


def _device_inks(sheet):
    return [k for k in sheet.inks if (k.meta or {}).get("layer") == "device"]


@pytest.mark.parametrize("did", sorted(PROCESS | GENERAL))
def test_device_parity_with_the_research(did):
    """Same sheet + spec ⇒ the same device inks as the research device
    (fixture written, and checked frozen == research, by freeze.py)."""
    fx = json.loads((FIXTURES / f"{did}.json").read_text())
    lib = FL.FrozenLibrary()
    st = ST.builtin(fx["study"])
    sheet = engine.run_kit(ST.run_recipe(st, ST.resolve(st, {}, lib), lib), lib)
    out, notes = DV.apply(sheet, fx["spec"], lib)
    assert list(out.frame) == fx["frame"] and notes[0]["inks"] == len(fx["inks"]) and "error" not in notes[0]
    got = []
    for k in _device_inks(out):
        p = np.asarray(k.points, float)
        got.append([len(p), bool(k.closed), bool(k.filled), float(k.pen), *p[0], *p[-1],
                    p[:, 0].sum(), p[:, 1].sum(), (p[:, 0] ** 2).sum(), (p[:, 1] ** 2).sum()])
    allp = np.vstack([np.asarray(k.points, float) for k in _device_inks(out)])
    assert len(got) == len(fx["inks"]) and len(allp) == fx["n_points"]
    if fx["geos"] == shapely.geos_version_string or did not in {"misfit_grid"}:
        for a, b in zip(got, fx["inks"]):
            assert a[:3] == b[:3]
            assert np.allclose(a[3:], b[3:], rtol=1e-9, atol=1e-7)
        assert np.allclose(allp[::fx["stride"]], np.asarray(fx["sample"]), atol=1e-7)
    else:                                   # clipping against ink capsules is GEOS's: same grid, same place
        assert Counter(tuple(a[1:3]) for a in got) == Counter(tuple(b[1:3]) for b in fx["inks"])
        assert np.allclose(allp.mean(axis=0), np.array([sum(b[8] for b in fx["inks"]),
                                                        sum(b[9] for b in fx["inks"])]) / fx["n_points"], atol=0.5)


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    [{"id": "nope"}],                                                   # unknown device
    [{"id": "heading_rose"}, {"id": "heading_rose"}],                   # twice
    [{"id": "heading_rose", "place": "inside"}],                        # unknown placement
    [{"id": "heading_rose", "place": "beside", "side": "top"}],         # beside grows right or bottom only
    [{"id": "heading_rose", "place": "beside", "size": 2000}],          # an unbounded panel
    [{"id": "heading_rose", "place": "margin", "size": 1}],
    [{"id": "heading_rose", "bins": 2}],                                # below the device's own bound
    [{"id": "heading_rose", "bins": 12.5}],                             # an int param
    [{"id": "heading_rose", "colour": "red"}],                          # not a param of this device
    [{"id": "meas_air", "level": "page"}],                              # not a choice
    [{"id": "meas_air", "ink": "#ff0000"}],                             # inks are Flexoki names
    [{"id": "meas_inventory", "index": "yes"}],                         # a bool
    [{"id": "meas_ledger", "drawn_by": "nobody"}],                      # not a library hand
    [{"id": "meas_arcs", "kinds": "cross; rm -rf"}],                    # words only
    [{"id": "misfit_grid", "strength": float("nan")}],
    [{"id": "heading_rose"}] * 14,
    "heading_rose",
])
def test_devices_are_validated_against_the_registry(bad):
    with pytest.raises(ValidationError):
        SRC.Params(**params("river_zoom", devices=bad))


def test_show_needs_devices_and_measure_takes_no_voice():
    with pytest.raises(ValidationError):
        SRC.Params(**params("river_zoom", show="measure"))
    with pytest.raises(ValidationError):
        SRC.Params(**params("chorus", devices=[ROSE], show="measure", voice=0))
    p = SRC.Params(**params("river_zoom", devices=[{**ROSE, "size": 60}, {"id": "meas_air", "number_every": 2.0}]))
    assert p.devices[0]["size"] == 60.0 and p.devices[1]["number_every"] == 2       # normalised


def test_no_devices_is_exactly_the_study():
    plain = doc_of(params("river_zoom"))
    assert fingerprint(paths_of(plain)) == fingerprint(paths_of(doc_of(params("river_zoom", devices=[]))))
    assert SRC.preview_extra(plain) is None and [layer.name for layer in plain.layers] == ["Amazon, zooming"]


# ---------------------------------------------------------------------------
# frame, preview runs, what each device read
# ---------------------------------------------------------------------------

def test_beside_grows_the_frame_and_margin_does_not():
    W, H = SRC.placement_frame(params("river_zoom"))
    assert SRC.placement_frame(params("river_zoom", devices=[RULER])) == (W, H)
    assert SRC.placement_frame(params("river_zoom", devices=[ROSE])) == (W + 60, H)
    both = [ROSE, {"id": "meas_turning", "place": "beside", "side": "bottom", "size": 50}]
    assert SRC.placement_frame(params("river_zoom", devices=both)) == (W + 60, H + 50)
    doc = doc_of(params("river_zoom", devices=both))
    assert (doc.width, doc.height) == (W + 60, H + 50)
    for p in paths_of(doc):
        assert all(-1e-6 <= x <= W + 60 + 1e-6 and -1e-6 <= y <= H + 50 + 1e-6 for x, y in p.points)
    # the drawing itself does not move: the panel is added beside it
    assert fingerprint(doc.layers[0].paths) == fingerprint(paths_of(doc_of(params("river_zoom"))))


def test_device_inks_are_their_own_styled_run_and_layer():
    with TestClient(__import__("axibridge.app", fromlist=["create_app"]).create_app()) as c:
        body = {"module": "gesture_studies",
                "params": params("river_zoom", devices=[RULER, {"id": "meas_air", "place": "over"}])}
        r = c.post("/api/generators/preview", json=body)
        assert r.status_code == 200, r.text
        out = r.json()
    assert [x["name"] for x in out["layers"]] == ["Amazon, zooming", "Measure"] and out["measure_layer"] == 1
    assert sum(x["paths"] for x in out["styles"]) == len(out["lines"]) == sum(x["paths"] for x in out["layers"])
    drawing = out["layers"][0]["paths"]
    # the drawing's run(s) first, then the device inks in their own pen width
    runs, at = [], 0
    for s in out["styles"]:
        runs.append((at, s)); at += s["paths"]
    assert all(s["width"] <= 0.3 for a, s in runs if a >= drawing)
    notes = {n["id"]: n for n in out["devices"]}
    assert notes["scale_ruler"]["inks"] > 0
    assert notes["meas_air"]["inks"] == 0                 # one line: the pen never lifts — nothing to read


def test_a_process_device_says_when_the_study_has_nothing_for_it(monkeypatch):
    doc = doc_of(params("river_zoom", devices=[{"id": "meas_arcs", "place": "beside", "side": "bottom", "size": 50},
                                               {"id": "meas_stations", "place": "over"}]))
    notes = {n["id"]: n for n in SRC.preview_extra(doc)["devices"]}
    assert notes["meas_arcs"]["inks"] == 0               # no score, no arranger log
    assert notes["meas_stations"]["inks"] > 0             # river km along the line
    by = {d["id"]: d for d in DV.catalogue()}
    assert "score" in by["meas_arcs"]["empty"] and "clock" in by["meas_stations"]["empty"]
    # a device that refuses the drawing (a KitError) says why instead of failing the preview
    import dataclasses

    from axibridge.sources._gesture_studies.kit import _devices
    from axibridge.sources._gesture_studies.kit.core import KitError

    def refuse(dctx, sheet, **kw):
        raise KitError("scale_ruler: drawing extent does not fit region at true millimetre scale")
    monkeypatch.setitem(_devices._DEVICES, "scale_ruler", dataclasses.replace(_devices._DEVICES["scale_ruler"],
                                                                              fn=refuse))
    sheet = engine.run_kit(ST.resolve(ST.builtin("river_zoom"), {}, FL.FrozenLibrary()), FL.FrozenLibrary())
    out, notes = DV.apply(sheet, [RULER, ROSE], FL.FrozenLibrary())
    assert notes[0]["inks"] == 0 and "true millimetre scale" in notes[0]["error"]
    assert notes[1]["inks"] > 0 and len(_device_inks(out)) == notes[1]["inks"]


def test_hand_drift_study_takes_devices_without_changing_its_drawing():
    plain = paths_of(doc_of(params("hand_drift", {"length": 2.0})))
    doc = doc_of(params("hand_drift", {"length": 2.0}, devices=[ROSE, {"id": "meas_turning", "place": "over"}]))
    assert fingerprint(doc.layers[0].paths) == fingerprint(plain)
    assert doc.layers[1].name == "Measure" and doc.layers[1].paths


def test_ledger_hand_is_pinned_at_keep():
    p = params("river_zoom", devices=[{"id": "meas_ledger", "place": "beside", "drawn_by": "matisse", "max_rows": 3}])
    kept = SRC.complete_params(p)
    assert {"kind": "hand", "id": "matisse"} in [{"kind": x["kind"], "id": x["id"]} for x in kept["pins"]]


# ---------------------------------------------------------------------------
# Keep: a group with the drawing and one Measure layer, one undo step
# ---------------------------------------------------------------------------

def test_keep_with_devices_makes_a_group_with_a_measure_layer():
    from axibridge.session import session
    from axibridge.stores import pen_library

    before = session.project.model_copy(deep=True)
    p = params("river_zoom", devices=[RULER, ROSE])
    group, layers = session.keep_gesture_study_measured(p)
    assert group.name == "Amazon, zooming" and [l.name for l in layers] == ["Amazon, zooming", "Measure"]
    drawing, measure = layers
    assert all(l.group_id == group.id for l in layers)
    assert drawing.source.params["show"] == "drawing" and measure.source.params["show"] == "measure"
    assert measure.pen_id and measure.pen_id != drawing.pen_id
    assert pen_library.get(measure.pen_id).color.lower() == "#100f0f"
    assert drawing.transform == measure.transform                      # in register
    assert drawing.source.params["library"] == measure.source.params["library"] == FL.current_snapshot()
    full = doc_of(p)
    assert fingerprint(session.source_geometry[drawing.id]) == fingerprint(full.layers[0].paths)
    assert fingerprint(session.source_geometry[measure.id]) == fingerprint(full.layers[1].paths)
    session.undo()                                                     # one undo for the whole keep
    assert [l.id for l in session.project.layers] == [l.id for l in before.layers]
    assert [g.id for g in session.project.groups] == [g.id for g in before.groups]


def test_keep_under_puts_the_measure_layer_below():
    from axibridge.session import session

    grid = {"id": "misfit_grid", "place": "under", "strength": 2.0, "clear": 0.0, "pitch": 20.0}
    _, layers = session.keep_gesture_study_measured(params("river_zoom", devices=[grid]))
    assert [l.name for l in layers] == ["Measure", "Amazon, zooming"]
    ids = [l.id for l in session.project.layers]
    assert ids.index(layers[0].id) < ids.index(layers[1].id)          # first = bottom of the stack
    session.undo()


def test_keep_voices_with_devices_adds_one_measure_layer():
    from axibridge.session import session

    p = params("chorus", {"arranger.voices": 2}, devices=[{"id": "meas_air", "place": "over"}])
    group, layers = session.keep_gesture_study_measured(p)
    assert [l.name for l in layers] == ["Chorus, several pens · black", "Chorus, several pens · red", "Measure"]
    assert [l.source.params.get("voice") for l in layers] == [0, 1, None]
    assert len({l.pen_id for l in layers}) == 3                         # the Measure on its own pen
    assert len({json.dumps(l.transform.model_dump(), sort_keys=True) for l in layers}) == 1
    session.undo()


def test_keep_endpoint_with_and_without_devices():
    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        r = c.post("/api/gesture-studies/keep", json={"params": params("river_zoom", devices=[ROSE])})
        assert r.status_code == 200, r.text
        body = r.json()
        assert [l["name"] for l in body["layers"]] == ["Amazon, zooming", "Measure"]
        proj = c.get("/api/project").json()
        assert {l["group_id"] for l in proj["layers"] if l["id"] in {x["id"] for x in body["layers"]}} == \
            {body["group"]["id"]}
        # no devices: unchanged — a one-layer study is kept as a layer, not through this route
        assert c.post("/api/gesture-studies/keep", json={"params": params("river_zoom")}).status_code == 400
        # a device that reads nothing here cannot make an empty Measure layer
        r = c.post("/api/gesture-studies/keep", json={"params": params("river_zoom", devices=[
            {"id": "meas_arcs", "place": "over"}])})
        assert r.status_code == 400 and "nothing to read" in r.text
        bad = c.post("/api/gesture-studies/keep", json={"params": params("river_zoom", devices=[{"id": "nope"}])})
        assert bad.status_code == 400
        cat = c.get("/api/gesture-studies").json()["devices"]
        assert [d["id"] for d in cat][:2] == ["meas_air", "meas_ledger"] and len(cat) == 13
