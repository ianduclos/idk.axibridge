"""Session recovery state follows kept project content, not transient renders."""

from __future__ import annotations

import pytest

from axibridge.assets import asset_store
from axibridge.compose import CanvasLayer, CaptureGroup, LayerSource, StagedSheet
from axibridge.model import Layer, Path, PathDocument
from axibridge.recovery import RecoveryStore
from axibridge.session import Session


@pytest.fixture
def recovery_session():
    before = asset_store.all()
    asset_store.replace_all({})
    try:
        yield Session()
    finally:
        asset_store.replace_all(before)


def test_persistent_project_changes_dirty_and_undo_to_saved_baseline_cleans(recovery_session):
    session = recovery_session
    start = session.recovery_status()
    assert start == {"dirty": False, "revision": 0, "session_id": start["session_id"], "recovery": {}}

    session.project.name = "edited"
    changed = session.recovery_status()
    assert changed["dirty"] is True and changed["revision"] == 1
    assert session.recovery_status()["revision"] == 1

    session.project.name = "untitled"  # undo back to saved content
    restored = session.recovery_status()
    assert restored["dirty"] is False
    assert restored["revision"] == 2
    session.project.backend_params["simulator"] = {"speed": 10}
    assert session.recovery_status()["dirty"] is True
    session.mark_saved()
    assert session.recovery_status()["dirty"] is False


def test_derived_provenance_tween_geometry_and_preview_caches_stay_clean(recovery_session):
    session = recovery_session
    generated = CanvasLayer(id="gen", source=LayerSource(type="generator", generator="polygon"))
    tween = CanvasLayer(id="tw", source=LayerSource(type="tween", params={"a": "gen", "b": "gen"}))
    session.project.layers = [generated, tween]
    session.source_geometry = {"gen": [Path(points=[(1, 2)])], "tw": []}
    session.project.staging = [CaptureGroup(sheets=[StagedSheet(id="sheet")])]
    session.mark_saved()

    generated.source.file = "sources/gen-gen.svg"
    generated.source.svg_layer = None
    session.project.staging[0].sheets[0].file = "staging/sheet.svg"
    session.source_geometry["tw"] = [Path(points=[(9, 9)])]
    session._frame_lru["preview"] = {}
    assert session.recovery_status()["dirty"] is False

    session.source_geometry["gen"] = [Path(points=[(3, 4)])]
    assert session.recovery_status()["dirty"] is True


def test_assets_and_staging_are_tracked_and_project_switch_resets_identity(recovery_session):
    session = recovery_session
    prior_id = session.recovery_status()["session_id"]
    asset_store.put("depth.png", b"pixels")
    assert session.recovery_status()["dirty"] is True
    session.mark_saved()

    session.project.staging = [CaptureGroup(sheets=[StagedSheet(id="sheet", file="staging/sheet.svg")])]
    session.staging_documents["staging/sheet.svg"] = PathDocument(layers=[Layer(id=1, paths=[Path(points=[(1, 2)])])])
    assert session.recovery_status()["dirty"] is True
    session.begin_project()
    switched = session.recovery_status()
    assert switched["session_id"] != prior_id
    assert switched["revision"] == 0 and switched["dirty"] is False
    assert switched["recovery"] == {}


def test_capture_is_detached_from_mutable_project_maps_and_history(recovery_session):
    session = recovery_session
    session.project.name = "captured"
    session.project.layers = [CanvasLayer(id="gen", source=LayerSource(type="generator", generator="polygon"))]
    paths = [Path(points=[(1, 2), (3, 4)])]
    session.source_geometry["gen"] = paths
    session.svg_files["sources/original.svg"] = "<svg/>"
    session.staging_documents["staging/sheet.svg"] = PathDocument()
    session._history.append((session.project.model_copy(deep=True), dict(session.source_geometry), {}, {}))

    snapshot = session.capture_recovery()
    session.project.name = "later"
    session.source_geometry.clear()
    session.svg_files.clear()
    session.staging_documents.clear()
    session._history[0][0].name = "changed history"
    assert snapshot.project.name == "captured"
    assert snapshot.source_geometry == {"gen": paths}
    assert snapshot.source_geometry["gen"] is paths
    assert snapshot.svg_files == {"sources/original.svg": "<svg/>"}
    assert "staging/sheet.svg" in snapshot.staging_documents
    assert snapshot.history[0][0].name == "captured"


def test_checkpoint_records_only_current_revision_and_exposes_write_errors(recovery_session):
    session = recovery_session
    session.project.name = "first"

    class Store:
        def write(self, snapshot):
            session.project.name = "second"  # edit while disk I/O is underway
            return {"id": snapshot.session_id, "revision": snapshot.revision}

    session._recovery_store = Store()
    result = session.checkpoint_recovery()
    assert result["revision"] == 1
    status = session.recovery_status()
    assert status["revision"] == 2
    assert status["recovery"] == {}

    class FailingStore:
        def write(self, snapshot):
            raise OSError("disk full")

    session._recovery_store = FailingStore()
    with pytest.raises(OSError, match="disk full"):
        session.checkpoint_recovery()
    assert session.recovery_status()["recovery"]["error"] == "disk full"


def test_checkpoint_writes_loadable_snapshot_and_reports_its_metadata(recovery_session, tmp_path):
    session = recovery_session
    session._recovery_store = RecoveryStore(tmp_path / "recovery")
    session.project.name = "recover me"
    metadata = session.checkpoint_recovery()

    status = session.recovery_status()
    assert status["dirty"] is True
    assert status["recovery"] == metadata
    assert session.recovery_store.load(status["session_id"])[1][0].name == "recover me"
