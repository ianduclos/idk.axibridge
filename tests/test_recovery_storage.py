"""Recovery archives keep a complete, detached project outside named folders."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from axibridge.compose import CanvasLayer, CaptureGroup, LayerSource, Project, StagedSheet
from axibridge.model import Layer, Path as DrawPath, PathDocument
from axibridge.recovery import RecoverySnapshot, RecoveryStore


def _snapshot(session_id: str = "a" * 32, revision: int = 1) -> RecoverySnapshot:
    generated = CanvasLayer(id="generated", name="ink", source=LayerSource(type="generator", generator="polygon"))
    uploaded = CanvasLayer(id="uploaded", name="trace", source=LayerSource(type="svg", file="sources/trace.svg"))
    project = Project(
        name="unfinished",
        layers=[generated, uploaded],
        staging=[CaptureGroup(id="capture", sheets=[StagedSheet(id="sheet")])],
    )
    geometry = {"generated": [DrawPath(points=[(1.0, 2.0), (3.0, 4.0)])],
                "uploaded": [DrawPath(points=[(5.0, 6.0), (7.0, 8.0)])]}
    svg = {'sources/trace.svg': '<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm" viewBox="0 0 10 10"><path d="M 5 6 L 7 8"/></svg>'}
    staged = PathDocument(layers=[Layer(id=1, paths=[DrawPath(points=[(9.0, 10.0), (11.0, 12.0)])])])
    earlier = (Project(name="before"), {"old": [DrawPath(points=[(1.0, 1.0)])]}, {}, {})
    return RecoverySnapshot(project=project, source_geometry=geometry, svg_files=svg,
                            assets={"depth.png": b"\x89PNG\r\nasset"},
                            staging_documents={"staging/sheet.svg": staged},
                            history=[earlier], revision=revision, session_id=session_id,
                            project_dir="/some/named/project")


def test_complete_roundtrip_uses_recovery_dir_and_detaches_inputs(tmp_path: Path):
    store = RecoveryStore(tmp_path / "config" / "recovery")
    snapshot = _snapshot()
    snapshot.project_dir = str(tmp_path / "named-project")
    original_project = snapshot.project.model_dump()
    original_history = snapshot.history[0][0].model_dump()

    entry = store.write(snapshot)
    assert entry["id"] == snapshot.session_id
    assert entry["revision"] == 1
    assert entry["name"] == "unfinished"
    assert entry["project_dir"] == str(tmp_path / "named-project")
    assert entry["created_at"].endswith("Z")
    assert snapshot.project.model_dump() == original_project
    assert snapshot.history[0][0].model_dump() == original_history
    assert snapshot.project.layers[0].source.file is None
    assert snapshot.project.staging[0].sheets[0].file is None
    assert not (tmp_path / "named-project").exists()

    archive = store.root / f"{snapshot.session_id}.zip"
    with zipfile.ZipFile(archive) as zf:
        assert json.loads(zf.read("recovery.json"))["revision"] == 1
        assert "project.json" in zf.namelist()
        assert "assets/depth.png" in zf.namelist()
    metadata, loaded = store.load(snapshot.session_id)
    project, geometry, svg_files, assets, documents, history = loaded
    assert metadata == entry
    assert project.layers[0].source.file == "sources/gen-generated.svg"
    assert geometry["generated"][0].points == [(1.0, 2.0), (3.0, 4.0)]
    assert geometry["uploaded"][0].points == [(5.0, 6.0), (7.0, 8.0)]
    assert svg_files == snapshot.svg_files
    assert assets == snapshot.assets
    assert project.staging[0].sheets[0].file == "staging/sheet.svg"
    staged_points = documents["staging/sheet.svg"].layers[0].paths[0].points
    assert staged_points[0] == pytest.approx((9.0, 10.0), abs=1e-3)
    assert staged_points[1] == pytest.approx((11.0, 12.0), abs=1e-3)
    assert len(history) == 1 and history[0][0].name == "before"
    assert history[0][1]["old"][0].points == [(1.0, 1.0)]


def test_corrupt_current_falls_back_to_prior_valid_archive(tmp_path: Path):
    store = RecoveryStore(tmp_path / "recovery")
    store.write(_snapshot(revision=1))
    store.write(_snapshot(revision=2))
    (store.root / f"{'a' * 32}.zip").write_bytes(b"broken archive")

    entry = store.list_entries()[0]
    assert entry["revision"] == 1
    assert entry["fallback"] is True
    metadata, loaded = store.load("a" * 32)
    assert metadata == entry
    assert loaded[0].name == "unfinished"


def test_failed_write_keeps_last_good_archive(tmp_path: Path, monkeypatch):
    from axibridge import recovery

    store = RecoveryStore(tmp_path / "recovery")
    store.write(_snapshot(revision=1))
    real_replace = recovery.os.replace

    def fail_current(src, dst):
        if Path(dst).name == f"{'a' * 32}.zip":
            raise OSError("disk write failed")
        return real_replace(src, dst)

    monkeypatch.setattr(recovery.os, "replace", fail_current)
    with pytest.raises(OSError, match="disk write failed"):
        store.write(_snapshot(revision=2))
    assert store.load("a" * 32)[0]["revision"] == 1
    assert not list(store.root.glob("*.tmp"))


def test_multiple_sessions_persist_until_the_requested_one_is_discarded(tmp_path: Path):
    store = RecoveryStore(tmp_path / "recovery")
    store.write(_snapshot("a" * 32))
    store.write(_snapshot("b" * 32))
    assert {entry["id"] for entry in store.list_entries()} == {"a" * 32, "b" * 32}
    store.discard("a" * 32)
    assert [entry["id"] for entry in store.list_entries()] == ["b" * 32]
    assert store.load("b" * 32)[0]["id"] == "b" * 32


def test_canonical_uuid_session_id_round_trips(tmp_path: Path):
    recovery_id = "12345678-1234-1234-1234-123456789abc"
    store = RecoveryStore(tmp_path / "recovery")
    store.write(_snapshot(recovery_id))
    assert store.load(recovery_id)[0]["id"] == recovery_id


@pytest.mark.parametrize("unsafe", ["../escape", "/absolute", "a/other", "", "a" * 128])
def test_unsafe_ids_are_rejected_before_accessing_paths(tmp_path: Path, unsafe: str):
    store = RecoveryStore(tmp_path / "recovery")
    with pytest.raises(ValueError):
        store.write(_snapshot(unsafe))
    with pytest.raises(ValueError):
        store.load(unsafe)
    with pytest.raises(ValueError):
        store.discard(unsafe)
    assert not store.root.exists()
