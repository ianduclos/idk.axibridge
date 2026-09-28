"""Synthetic boundary tests for the Linedraw v3 recipe and draft lifecycle."""

import io
import os
import threading

import numpy as np
import pytest
from PIL import Image

from axibridge.assets import asset_store
from axibridge.linedraw.contracts import (
    Candidate,
    Evidence,
    FaceRegion,
    LinedrawV3Params,
)


def _blank_evidence(size=100, *, faces=(), candidates=None):
    return Evidence(
        rgb=np.ones((size, size, 3), dtype=np.float32),
        foreground=np.ones((size, size), dtype=np.float32),
        normals=None,
        whole_lines=np.ones((size, size), dtype=np.float32),
        tiled_lines=np.ones((size, size), dtype=np.float32),
        faces=tuple(faces),
        face_candidates=candidates or {},
    )


def _paths(document):
    return [path.points for _, path in document.iter_paths()]


def test_face_allowance_is_per_region_even_with_zero_broad_allowance(monkeypatch):
    from axibridge.linedraw import engine

    monkeypatch.setattr(engine, "trace_map", lambda *args: [])
    left = FaceRegion(id="left", cx=0.25, cy=0.5, rx=0.2, ry=0.25)
    right = FaceRegion(id="right", cx=0.75, cy=0.5, rx=0.2, ry=0.25)
    candidates = {
        face.id: tuple(
            Candidate(
                np.array([[center - 8, y], [center + 8, y]], dtype=float),
                1,
                f"{face.id}-{y}",
            )
            for y in (42, 50, 58)
        )
        for face, center in ((left, 25), (right, 75))
    }
    evidence = _blank_evidence(faces=(left, right), candidates=candidates)
    params = LinedrawV3Params(
        style="contours",
        width=100,
        contour_budget=0,
        face_budget=2,
        faces=[left, right],
    )
    assert len(_paths(engine.render_document(evidence, params))) == 4
    assert (
        len(
            _paths(
                engine.render_document(
                    evidence, params.model_copy(update={"face_budget": 1})
                )
            )
        )
        == 2
    )
    disabled = right.model_copy(update={"enabled": False})
    assert (
        len(
            _paths(
                engine.render_document(
                    evidence, params.model_copy(update={"faces": [left, disabled]})
                )
            )
        )
        == 2
    )


def test_evidence_key_reuses_style_edits_and_invalidates_image_model_or_faces():
    from axibridge.linedraw.runtime import evidence_key

    image = b"synthetic-image-A"
    face = FaceRegion(id="accepted", cx=0.4, cy=0.5, rx=0.1, ry=0.2)
    params = LinedrawV3Params(faces=[face])
    original = evidence_key(image, params, "model-A")
    changed_style = params.model_copy(
        update={
            "style": "shadow_shapes",
            "contour_budget": 5,
            "face_budget": 1,
            "fill_spacing": 2.0,
        }
    )
    assert evidence_key(image, changed_style, "model-A") == original
    assert evidence_key(image + b"B", params, "model-A") != original
    assert evidence_key(image, params, "model-B") != original
    moved = face.model_copy(update={"cx": 0.6})
    assert (
        evidence_key(image, params.model_copy(update={"faces": [moved]}), "model-A")
        != original
    )


def test_replacing_weights_with_same_size_and_mtime_changes_model_identity(
    tmp_path, monkeypatch
):
    from axibridge.linedraw import runtime

    weights = tmp_path / "line.weights"
    weights.write_bytes(b"AAAA")
    config = {
        "python": "/fake/python",
        "line_code": "/fake/code",
        "line_weights": str(weights),
        "person_weights": str(weights),
    }
    monkeypatch.setattr(runtime, "configuration", lambda: config)
    monkeypatch.setattr(runtime, "_FINGERPRINTS", {})
    before = runtime.model_identity()
    old_stat = weights.stat()
    replacement = tmp_path / "replacement.weights"
    replacement.write_bytes(b"BBBB")
    os.utime(replacement, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    replacement.replace(weights)
    assert weights.stat().st_size == old_stat.st_size
    assert weights.stat().st_mtime_ns == old_stat.st_mtime_ns
    assert runtime.model_identity() != before


@pytest.mark.parametrize(
    "field", ["rgb", "foreground", "whole_lines", "tiled_lines", "alpha", "normals"]
)
def test_nonfinite_model_evidence_is_rejected_in_each_channel(field):
    from axibridge.linedraw.runtime import validate_arrays

    arrays = {
        "rgb": np.zeros((4, 4, 3)),
        "foreground": np.zeros((4, 4)),
        "whole_lines": np.zeros((4, 4)),
        "tiled_lines": np.zeros((4, 4)),
        "alpha": np.ones((4, 4)),
        "normals": np.zeros((4, 4, 3)),
    }
    arrays[field][0, 0] = np.inf
    with pytest.raises(ValueError, match=field):
        validate_arrays(arrays, 4, 4)


def test_cancel_queued_and_running_drafts_discards_late_results(monkeypatch):
    from axibridge.linedraw import runtime
    from axibridge.linedraw.jobs import JobManager

    image = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(image, format="PNG")
    asset_store.put("edge-cancel.png", image.getvalue())
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def analyze(*args, **kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(5), "test worker was not released"
        return _blank_evidence(16)

    monkeypatch.setattr(runtime, "detect_and_analyze", analyze)
    monkeypatch.setattr(runtime, "model_identity", lambda: "synthetic-model")
    manager = JobManager()
    try:
        params = LinedrawV3Params(image="edge-cancel.png", style="contours")
        running = manager.start("draft-old", params, "analyze")["id"]
        assert entered.wait(2)
        queued = manager.start("draft-new", params, "analyze")["id"]
        assert manager.cancel(queued)["state"] == "cancelled"
        assert manager.cancel(running)["state"] == "cancelled"
        release.set()
        manager.executor.submit(lambda: None).result(timeout=3)
        for identity in (running, queued):
            result = manager.get(identity)
            assert result["state"] == "cancelled"
            assert result["result"] is None
    finally:
        release.set()
        manager.shutdown()
    assert calls == [1]


def test_saved_recipe_and_frozen_paths_reopen_without_models(tmp_path):
    from axibridge.compose import CanvasLayer, LayerSource, Project
    from axibridge.model import Path
    from axibridge.project_io import load_project, save_project

    face = FaceRegion(
        id="edited-face", cx=0.37, cy=0.48, rx=0.13, ry=0.19, origin="manual"
    )
    params = LinedrawV3Params(
        image="portrait.png",
        style="face_form",
        faces=[face],
        image_identity="a" * 64,
        model_identity="b" * 64,
    )
    layer = CanvasLayer(
        id="frozen",
        source=LayerSource(
            type="generator", generator="linedraw_v3", params=params.model_dump()
        ),
    )
    project = Project(layers=[layer])
    frozen = [Path(points=[(1.0, 2.0), (3.0, 4.0)])]
    save_project(
        project,
        {layer.id: frozen},
        {},
        tmp_path,
        assets={"portrait.png": b"image bytes"},
    )
    reopened, geometry, _, assets, _, _ = load_project(tmp_path)
    assert reopened.layers[0].source.params == params.model_dump()
    assert geometry[layer.id] == frozen
    assert assets["portrait.png"] == b"image bytes"


def test_shadow_shapes_cancellation_stops_before_next_raster_stage(monkeypatch):
    from axibridge.linedraw import shadows
    from axibridge.render_work import RenderCancelled

    cancelled = threading.Event()
    real_closing = shadows.binary_closing

    def closing(*args, **kwargs):
        result = real_closing(*args, **kwargs)
        cancelled.set()
        return result

    def unexpected_opening(*args, **kwargs):
        pytest.fail("opening ran after cancellation")

    def check():
        if cancelled.is_set():
            raise RenderCancelled()

    monkeypatch.setattr(shadows, "binary_closing", closing)
    monkeypatch.setattr(shadows, "binary_opening", unexpected_opening)
    field = np.zeros((32, 32))
    field[4:28, 4:28] = 1
    with pytest.raises(RenderCancelled):
        shadows.shapes(field, np.ones_like(field, dtype=bool), 1, 4, 8, .5,
                       checkpoint=check)


def test_shadow_shapes_cancellation_interrupts_curve_loop(monkeypatch):
    from axibridge.linedraw import shadows
    from axibridge.render_work import RenderCancelled

    yy, xx = np.mgrid[:64, :64]
    ring = (((xx - 32) ** 2 + (yy - 32) ** 2 < 24 ** 2) &
            ((xx - 32) ** 2 + (yy - 32) ** 2 > 10 ** 2))
    cancelled = threading.Event()
    simplified = []
    real_simplify = shadows.simplify

    def simplify_one_curve(*args, **kwargs):
        result = real_simplify(*args, **kwargs)
        simplified.append(result)
        cancelled.set()
        return result

    def check():
        if cancelled.is_set():
            raise RenderCancelled()

    monkeypatch.setattr(shadows, "simplify", simplify_one_curve)
    with pytest.raises(RenderCancelled):
        shadows.shapes(ring.astype(float), np.ones_like(ring), 1, 10, 8, .5,
                       checkpoint=check)
    assert len(simplified) == 1
