"""Completed Linedraw drafts separate from their retained pen geometry."""

import pytest
from fastapi import HTTPException
import numpy as np

from axibridge.compose import Affine, CanvasLayer, EffectStep, LayerSource, Project
from axibridge.linedraw.contracts import LinedrawV3Params
from axibridge.linedraw.contracts import Evidence
from axibridge.linedraw.jobs import Job, JobManager
from axibridge.linedraw import jobs, runtime
from axibridge.model import Layer, Path, PathDocument
from axibridge.project_io import load_project, save_project
from axibridge.session import session
from axibridge import linedraw_api


def _document():
    return PathDocument(
        width=100, height=80,
        layers=[
            Layer(id=1, name="contours", paths=[Path(points=[(1, 2), (3, 4)])]),
            Layer(id=2, name="form", paths=[]),
            Layer(id=3, name="cores", paths=[Path(points=[(5, 6), (7, 8)])]),
        ],
    )


def _completed(monkeypatch):
    manager = JobManager()
    params = LinedrawV3Params(image="synthetic.png", width=100)
    job = Job("synthetic-job", "revision-1", params, "render", b"", session.project)
    job.state = "complete"
    job.document = _document()
    manager.jobs[job.id] = job
    monkeypatch.setattr(linedraw_api, "manager", manager)
    return job


def test_completed_job_exposes_flat_and_component_previews(monkeypatch):
    evidence = Evidence(
        rgb=np.ones((4, 4, 3), dtype=np.float32),
        foreground=np.ones((4, 4), dtype=np.float32),
        normals=None,
        whole_lines=np.ones((4, 4), dtype=np.float32),
        tiled_lines=np.ones((4, 4), dtype=np.float32),
    )
    monkeypatch.setattr(runtime, "detect_and_analyze", lambda *args, **kwargs: evidence)
    monkeypatch.setattr(runtime, "image_identity", lambda image: "synthetic-image")
    monkeypatch.setattr(runtime, "model_identity", lambda: "synthetic-model")
    monkeypatch.setattr(jobs, "render_document", lambda *args, **kwargs: _document())
    manager = JobManager()
    job = Job("preview-job", "revision-1", LinedrawV3Params(image="synthetic.png"),
              "render", b"synthetic-image", session.project)
    manager.jobs[job.id] = job
    manager._run(job)
    assert job.state == "complete"
    assert job.image == b""
    assert job.result["preview"]["lines"] == [[(1, 2), (3, 4)], [(5, 6), (7, 8)]]
    assert [(item["id"], item["count"]) for item in job.result["preview"]["components"]] == [
        ("contours", 1), ("form", 0), ("cores", 1),
    ]
    assert manager.completed_snapshot(job.id, job.revision, session.project)[0] is job.document


def test_detach_creates_frozen_aligned_layers_in_one_undo_step(monkeypatch):
    job = _completed(monkeypatch)
    response = linedraw_api.detach(job.id, linedraw_api.DetachJob(
        revision=job.revision, source_layer_id=None,
    ))
    created = response["layers"]
    assert [layer["name"] for layer in created] == ["Linedraw · Contours", "Linedraw · Cores"]
    assert len({tuple(layer["transform"].values()) for layer in created}) == 1
    assert all(layer["source"] == LayerSource(type="baked").model_dump() for layer in created)
    assert session.source_geometry[created[0]["id"]][0].points == [(1, 2), (3, 4)]
    assert session.source_geometry[created[1]["id"]][0].points == [(5, 6), (7, 8)]
    job.document.layers[0].paths[0].points[0] = (99, 99)
    assert session.source_geometry[created[0]["id"]][0].points[0] == (1, 2)
    assert session.undo()
    assert session.project.layers == []


def test_detached_layers_save_and_reopen_without_recipe_or_models(monkeypatch, tmp_path):
    job = _completed(monkeypatch)
    linedraw_api.detach(job.id, linedraw_api.DetachJob(
        revision=job.revision, source_layer_id=None,
    ))
    save_project(session.project, session.source_geometry, {}, tmp_path)
    reopened, geometry, _, _, _, _ = load_project(tmp_path)
    assert len(reopened.layers) == 2
    assert all(layer.source.type == "baked" and layer.source.generator is None
               for layer in reopened.layers)
    assert [geometry[layer.id][0].points for layer in reopened.layers] == [
        [(1, 2), (3, 4)], [(5, 6), (7, 8)],
    ]


def test_reopened_source_keeps_its_recipe_and_effects(monkeypatch):
    job = _completed(monkeypatch)
    source = CanvasLayer(
        name="original", source=LayerSource(type="generator", generator="linedraw_v3",
                                            params=job.params.model_dump()),
        transform=Affine(a=0.8, d=0.8, e=17, f=23),
        effects=[EffectStep(effect="some-effect")],
    )
    session.project.layers.append(source)
    before = source.model_dump()
    created = linedraw_api.detach(job.id, linedraw_api.DetachJob(
        revision=job.revision, source_layer_id=source.id,
    ))["layers"]
    assert source.model_dump() == before
    assert all(layer["transform"] == source.transform.model_dump() for layer in created)
    assert all(layer["effects"] == [] for layer in created)
    assert all(layer["source"]["generator"] is None for layer in created)


@pytest.mark.parametrize("case", ["revision", "cancelled", "new-project", "bad-source"])
def test_detach_rejects_stale_or_invalid_drafts_without_mutation(monkeypatch, case):
    job = _completed(monkeypatch)
    source_id = None
    revision = job.revision
    if case == "revision":
        revision = "older-revision"
    elif case == "cancelled":
        job.state = "cancelled"
    elif case == "new-project":
        session.project = Project()
    elif case == "bad-source":
        source_id = "missing-layer"
    before = session.project.model_dump()
    with pytest.raises(HTTPException) as exc:
        linedraw_api.detach(job.id, linedraw_api.DetachJob(
            revision=revision, source_layer_id=source_id,
        ))
    assert exc.value.status_code == 409
    assert session.project.model_dump() == before
    assert not session._history
