"""Mosca 2's draft API and portable Keep path, without a neural runtime."""

import io
import os
import subprocess
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge import mosca2_api
from axibridge.session import session
from axibridge.sources.mosca2 import Mosca2Params


@pytest.fixture
def client():
    with TestClient(create_app()) as browser:
        yield browser


def _page():
    return {
        "engine": "mosca2-v1",
        "settings": {"seed": 71, "duration_s": 3.5, "heading_deg": -45},
        "parts": [
            {"id": "territory-1", "label": "Territory", "kind": "territory",
             "strokes": [[[10.125, 20.25], [11.5, 21.75]],
                         [[20.0, 30.0], [22.0, 31.0]]]},
            {"id": "hidden", "label": "Earlier", "kind": "flowing",
             "visible": False, "strokes": [[[100, 101], [102, 103]]]},
            {"id": "response-1", "label": "Response", "kind": "response",
             "strokes": [[[50.5, 60.25], [51.75, 61.5]]]},
        ],
        "history": [{"id": "run-1", "label": "First bout",
                     "before": [[[10.125, 20.25], [11.5, 21.75]]],
                     "added": [[[50.5, 60.25], [51.75, 61.5]]],
                     "settings": {"seed": 71}, "summary": "Contact response",
                     "provenance": "fixed fixture",
                     "events": [{"t_ms": 500, "kind": "contact",
                                 "detail": "near line"}]}],
    }


def test_draft_endpoints_validate_before_starting_a_job(client, monkeypatch):
    started = []
    monkeypatch.setattr(mosca2_api.manager, "start",
                        lambda request: started.append(request) or {"id": "fake", "status": "running"})
    bad = [
        {"strokes": [[[301, 10], [20, 20]]]},
        {"settings": {"duration_s": 0}},
        {"settings": {"unknown": 1}},
        {"strokes": [[[1, 2], [3, 4]]], "unknown": True},
    ]
    for payload in bad:
        response = client.post("/api/mosca2/jobs", json=payload)
        assert response.status_code == 422, response.text
    assert started == []

    response = client.post("/api/mosca2/jobs", json={"strokes": [[[1, 2], [3, 4]]]})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": "fake", "status": "running"}
    assert started[0].strokes == [[(1.0, 2.0), (3.0, 4.0)]]


def test_status_and_unknown_jobs_are_read_only(client, monkeypatch):
    monkeypatch.setattr(mosca2_api, "status",
                        lambda: {"available": False, "reason": "test runtime absent"})
    assert client.get("/api/mosca2/status").json() == {
        "available": False, "reason": "test runtime absent"}
    assert client.get("/api/mosca2/jobs/missing").status_code == 404
    assert client.delete("/api/mosca2/jobs/missing").status_code == 404
    assert session.project.layers == []


def test_invalid_keep_does_not_mutate_project(client):
    bad = _page()
    bad["parts"][0]["strokes"][0][1][0] = 301
    response = client.post("/api/layers/generate",
                           json={"module": "mosca2", "params": bad})
    assert response.status_code == 400, response.text
    assert session.project.layers == []
    assert session.source_geometry == {}


def test_bundled_materials_and_all_page_pieces_are_valid(client):
    response = client.get("/api/mosca2/materials")
    assert response.status_code == 200, response.text
    library = response.json()
    assert len(library["materials"]) == 7
    assert len(library["pieces"]) == 6
    for material in library["materials"]:
        params = Mosca2Params(parts=[{**material, "kind": "flowing"}])
        assert params.parts[0].strokes
    for piece in library["pieces"]:
        params = Mosca2Params(parts=piece["parts"])
        assert params.parts and all(part.strokes for part in params.parts)
        assert params == Mosca2Params.model_validate_json(params.model_dump_json())

    # A portrait view can receive already placed, rotated strokes. The source
    # should still accept the same fixed physical frame and preserve order.
    first = library["pieces"][0]
    rotated = []
    for part in first["parts"]:
        strokes = [[[150 - (y - 109) * .5, 109 + (x - 150) * .5]
                    for x, y in stroke] for stroke in part["strokes"]]
        rotated.append({**part, "strokes": strokes})
    portrait = Mosca2Params(parts=rotated)
    assert len(portrait.parts) == len(first["parts"])
    assert portrait.parts[0].strokes[0][0] == tuple(rotated[0]["strokes"][0][0])


@pytest.mark.parametrize('view', ['portrait', 'landscape'])
def test_keep_save_load_and_zip_need_no_runtime(client, monkeypatch, view):
    from axibridge.mosca2 import jobs

    def no_runtime():
        raise AssertionError("frozen replay must not inspect the neural runtime")

    monkeypatch.setattr(jobs, "runtime", no_runtime)
    params = _page()
    assert client.put("/api/project", json={"view": view}).status_code == 200
    kept = client.post("/api/layers/generate",
                       json={"module": "mosca2", "params": params})
    assert kept.status_code == 200, kept.text
    assert kept.json()["source"]["params"] == params
    assert kept.json()["transform"] == {"a": 1.0, "b": 0.0, "c": 0.0, "d": 1.0, "e": 0.0, "f": 0.0}
    assert len(session.project.layers) == 1
    assert [path.points for path in session.source_geometry[kept.json()["id"]]] == [
        [(10.125, 20.25), (11.5, 21.75)],
        [(20.0, 30.0), (22.0, 31.0)],
        [(50.5, 60.25), (51.75, 61.5)],
    ]
    assert client.post("/api/project/save", json={"name": "mosca2-portable"}).status_code == 200
    exported = client.get("/api/project/export.zip")
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert any(name.endswith("project.json") for name in archive.namelist())

    assert client.post("/api/project/new").status_code == 200
    loaded = client.post("/api/project/load", json={"name": "mosca2-portable"})
    assert loaded.status_code == 200, loaded.text
    assert session.project.layers[0].source.params == params
    assert len(session.source_geometry[session.project.layers[0].id]) == 3

    assert client.post("/api/project/new").status_code == 200
    imported = client.post("/api/project/import", files={
        "file": ("mosca2-archive.zip", exported.content, "application/zip")})
    assert imported.status_code == 200, imported.text
    assert session.project.layers[0].source.params == params
    assert len(session.source_geometry[session.project.layers[0].id]) == 3


def test_source_import_has_no_simulation_dependency():
    code = ("import sys; import axibridge.sources.mosca2; "
            "assert not any(name in sys.modules for name in "
            "('fly', 'body', 'senses', 'world', 'axibridge.mosca2.jobs'))")
    env = {**os.environ, "PYTHONPATH": os.path.dirname(os.path.dirname(__file__))}
    result = subprocess.run([sys.executable, "-c", code], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
