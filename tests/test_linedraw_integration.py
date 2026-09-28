import io
import numpy as np
import pytest
from PIL import Image
from axibridge.assets import asset_store
from axibridge.linedraw.contracts import Evidence, LinedrawV3Params
from axibridge.linedraw import runtime
from axibridge.session import session
from axibridge import project_io, gencache


@pytest.fixture
def recipe(monkeypatch):
    image = Image.new("RGB", (48, 64), "white")
    b = io.BytesIO()
    image.save(b, format="PNG")
    asset_store.put("synthetic.png", b.getvalue())
    lines = np.ones((64, 48), np.float32)
    lines[8:55, 20] = 0
    rgb = np.full((64, 48, 3), 0.8)
    rgb[20:45, 10:35] = 0.2
    normals = np.zeros_like(rgb)
    normals[..., 2] = 1
    evidence = Evidence(rgb, np.ones((64, 48)), normals, lines, lines)
    monkeypatch.setattr(runtime, "model_identity", lambda: "synthetic-model")
    monkeypatch.setattr(runtime, "detect_and_analyze", lambda *a, **k: evidence)
    gencache.clear()
    return LinedrawV3Params(
        image="synthetic.png",
        image_identity=runtime.image_identity(b.getvalue()),
        model_identity="synthetic-model",
    ).model_dump()


@pytest.mark.parametrize(
    "style", ["contours", "light_form", "shadow_shapes", "face_form"]
)
def test_project_roundtrip_keeps_geometry_without_models(
    recipe, style, tmp_path, monkeypatch
):
    recipe["style"] = style
    layer = session.add_generated_layer("linedraw_v3", recipe)
    original = session.resolved()[layer.id]
    assert original
    project_io.save_project(
        session.project,
        session.source_geometry,
        session.svg_files,
        tmp_path,
        assets={"synthetic.png": asset_store.get("synthetic.png")},
    )
    project, geometry, _, assets, _, _ = project_io.load_project(tmp_path)
    session.project = project
    session.source_geometry = geometry
    session._shaped_cache.clear()
    asset_store.replace_all(assets)
    monkeypatch.setattr(
        runtime,
        "detect_and_analyze",
        lambda *a, **k: pytest.fail("Saved paths must not need inference"),
    )
    actual = session.resolved()[layer.id]
    assert len(actual) == len(original)
    for a, b in zip(actual, original):
        assert np.asarray(a.points) == pytest.approx(np.asarray(b.points), abs=1e-5)
    assert session.project.layer(layer.id).source.params == recipe


def test_failed_regeneration_preserves_recipe_and_undo(recipe, monkeypatch):
    layer = session.add_generated_layer("linedraw_v3", recipe)
    before = session.project.model_dump()
    history = len(session._history)
    geometry = session.source_geometry[layer.id]

    def unavailable(*a, **k):
        raise ValueError("Models unavailable")

    monkeypatch.setattr(runtime, "detect_and_analyze", unavailable)
    with pytest.raises(ValueError, match="Models unavailable"):
        session.regenerate_layer(layer.id, {**recipe, "contour_budget": 3})
    assert session.project.model_dump() == before
    assert len(session._history) == history
    assert session.source_geometry[layer.id] is geometry


def test_job_keep_apply_and_undo_use_normal_api(recipe):
    import time
    from fastapi.testclient import TestClient
    from axibridge.app import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/linedraw/jobs",
            json={"revision": "draft-1", "params": recipe, "operation": "render"},
        )
        assert response.status_code == 200
        job = response.json()
        for _ in range(100):
            job = client.get("/api/linedraw/jobs/" + job["id"]).json()
            if job["state"] in ("complete", "failed"):
                break
            time.sleep(0.01)
        assert job["state"] == "complete", job
        assert not session.project.layers
        accepted = job["result"]["params"]
        kept = client.post(
            "/api/layers/generate", json={"module": "linedraw_v3", "params": accepted}
        )
        assert kept.status_code == 200, kept.text
        layer = kept.json()
        original = session.source_geometry[layer["id"]]
        changed = {**accepted, "style": "contours", "contour_budget": 1}
        applied = client.post(
            "/api/layers/" + layer["id"] + "/regenerate", json={"params": changed}
        )
        assert applied.status_code == 200, applied.text
        assert session.project.layers[0].source.params == changed
        assert session.undo()
        assert session.project.layers[0].source.params == accepted
        assert session.source_geometry[layer["id"]] is original
