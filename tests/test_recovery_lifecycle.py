"""Hardware-free API and native-shell recovery lifecycle checks."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axibridge import api as api_module
from axibridge.app import create_app
from axibridge.backends.simulator import SimulatorBackend
from axibridge.machine import SoftLimits, manager
from axibridge.session import session


@pytest.fixture()
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture()
def isolated_simulator(monkeypatch):
    """An earlier machine test can leave the singleton simulator re-originated."""
    monkeypatch.setitem(manager.backends, "simulator", SimulatorBackend())
    monkeypatch.setattr(manager, "limits", SoftLimits())


def rename(client, name):
    response = client.put("/api/project", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


def recoveries(client):
    response = client.get("/api/recovery")
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def test_clean_preview_scrub_and_state_reads_do_not_need_recovery(isolated_simulator, client):
    initial = client.get("/api/project").json()
    assert initial["dirty"] is False and initial["revision"] == 0
    assert client.post("/api/generators/preview", json={
        "module": "polygon", "params": {"sides": 5, "radius": 10}}).status_code == 200
    assert client.get("/api/compose/resolved", params={"master_t": .5}).status_code == 200
    assert client.get("/api/state").status_code == 200
    assert client.post("/api/backend/select", json={"backend": "simulator"}).status_code == 200
    assert client.post("/api/connect", json={}).status_code == 200
    assert client.post("/api/machine/jog", json={"dx": 1, "dy": 1}).status_code == 200
    assert client.post("/api/recovery/checkpoint").json()["checkpointed"] is False
    final = client.get("/api/project").json()
    assert (final["dirty"], final["revision"], final["session_id"]) == (
        False, 0, initial["session_id"])
    assert recoveries(client) == []


def test_dirty_project_checkpoint_is_loadable_and_reports_revision(client):
    changed = rename(client, "unsaved A")
    assert changed["dirty"] is True and changed["revision"] > 0
    response = client.post("/api/recovery/checkpoint")
    assert response.status_code == 200, response.text
    checkpoint = response.json()
    assert checkpoint["checkpointed"] is True
    assert checkpoint["id"] == changed["session_id"]
    assert checkpoint["revision"] == changed["revision"]
    assert client.get("/api/project").json()["recovery"]["id"] == changed["session_id"]
    assert [entry["id"] for entry in recoveries(client)] == [changed["session_id"]]
    metadata, loaded = session.recovery_store.load(changed["session_id"])
    assert metadata["revision"] == changed["revision"]
    assert loaded[0].name == "unsaved A"


def test_dirty_new_requires_action_and_recover_keeps_archive(client):
    changed = rename(client, "recover before New")
    denied = client.post("/api/project/new")
    assert denied.status_code == 409
    assert client.get("/api/project").json()["name"] == "recover before New"
    switched = client.post("/api/project/new", json={"recovery_action": "recover"})
    assert switched.status_code == 200, switched.text
    assert switched.json()["dirty"] is False
    assert switched.json()["session_id"] != changed["session_id"]
    assert [entry["id"] for entry in recoveries(client)] == [changed["session_id"]]


def test_two_unsaved_projects_survive_switch_and_restore_history(client):
    first = rename(client, "first")
    assert client.post("/api/layers/generate", json={"module": "polygon",
        "params": {"sides": 5, "radius": 10}}).status_code == 200
    assert client.post("/api/project/new", json={"recovery_action": "recover"}).status_code == 200
    second = rename(client, "second")
    assert client.post("/api/project/new", json={"recovery_action": "recover"}).status_code == 200
    assert {entry["id"] for entry in recoveries(client)} == {
        first["session_id"], second["session_id"]}
    restored = client.post(f"/api/recovery/{first['session_id']}/restore")
    assert restored.status_code == 200, restored.text
    assert restored.json()["name"] == "first"
    assert restored.json()["dirty"] is True
    assert len(restored.json()["layers"]) == 1
    assert client.post("/api/undo").status_code == 200
    assert client.get("/api/project").json()["layers"] == []
    assert {entry["id"] for entry in recoveries(client)} == {
        first["session_id"], second["session_id"]}


def test_explicit_save_and_save_on_replace_remove_only_current_recovery(client):
    first = rename(client, "first")
    client.post("/api/project/new", json={"recovery_action": "recover"})
    second = rename(client, "second")
    client.post("/api/recovery/checkpoint")
    saved = client.post("/api/project/save", json={"name": "second"})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/project").json()["dirty"] is False
    assert [entry["id"] for entry in recoveries(client)] == [first["session_id"]]
    assert second["session_id"] not in {entry["id"] for entry in recoveries(client)}
    third = rename(client, "third")
    assert client.post("/api/recovery/checkpoint").status_code == 200
    assert client.post("/api/project/new", json={"recovery_action": "save"}).status_code == 200
    assert [entry["id"] for entry in recoveries(client)] == [first["session_id"]]
    assert third["session_id"] not in {entry["id"] for entry in recoveries(client)}


def test_discard_action_removes_only_requested_archive(client):
    first = rename(client, "first")
    client.post("/api/project/new", json={"recovery_action": "recover"})
    second = rename(client, "second")
    client.post("/api/recovery/checkpoint")
    replaced = client.post("/api/project/new", json={"recovery_action": "discard"})
    assert replaced.status_code == 200, replaced.text
    assert [entry["id"] for entry in recoveries(client)] == [first["session_id"]]
    assert second["session_id"] not in {entry["id"] for entry in recoveries(client)}


def test_failed_checkpoint_blocks_replace_and_restart(client, monkeypatch):
    assert client.post("/api/project/save", json={"name": "saved base"}).status_code == 200
    changed = rename(client, "cannot checkpoint")
    def fail_write(_snapshot):
        raise OSError("disk full")
    monkeypatch.setattr(session.recovery_store, "write", fail_write)
    assert client.post("/api/recovery/checkpoint").status_code == 409
    assert client.post("/api/project/new", json={"recovery_action": "recover"}).status_code == 409
    assert client.post("/api/project/load", json={
        "name": "saved base", "recovery_action": "recover"}).status_code == 409
    assert client.post("/api/server/restart", json={"continue_with_recovery": True}).status_code == 409
    state = client.get("/api/project").json()
    assert state["session_id"] == changed["session_id"] and state["dirty"] is True
    assert "disk full" in state["recovery"]["error"]


def test_restart_requires_consent_then_checkpoints_before_scheduling(client, monkeypatch):
    changed = rename(client, "restart me")
    started = []
    monkeypatch.setattr(api_module.threading.Thread, "start", lambda self: started.append(self.name))
    monkeypatch.setattr(api_module.os, "execv", lambda *_: pytest.fail("restart executed"))
    assert client.post("/api/server/restart").status_code == 409
    assert not started
    response = client.post("/api/server/restart", json={"continue_with_recovery": True})
    assert response.status_code == 200, response.text
    assert started == ["axibridge-restart"]
    assert [entry["id"] for entry in recoveries(client)] == [changed["session_id"]]


def test_dirty_load_and_import_require_action(client):
    rename(client, "saved base")
    assert client.post("/api/project/save", json={"name": "saved base"}).status_code == 200
    archive = client.get("/api/project/export.zip").content
    rename(client, "later edits")
    assert client.post("/api/project/load", json={"name": "saved base"}).status_code == 409
    files = {"file": ("imported.zip", io.BytesIO(archive), "application/zip")}
    assert client.post("/api/project/import", files=files).status_code == 409
    loaded = client.post("/api/project/load", json={
        "name": "saved base", "recovery_action": "recover"})
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["name"] == "saved base"
    assert len(recoveries(client)) == 1
    rename(client, "dirty before import")
    files = {"file": ("imported.zip", io.BytesIO(archive), "application/zip")}
    imported = client.post("/api/project/import?recovery_action=recover", files=files)
    assert imported.status_code == 200, imported.text
    assert imported.json()["dirty"] is False
    assert len(recoveries(client)) == 2


def test_native_close_checkpoint_surfaces_http_failure(monkeypatch):
    path = Path(__file__).resolve().parent.parent / "launch" / "axibridge_app.py"
    spec = importlib.util.spec_from_file_location("axibridge_native_shell_recovery_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    def fail_request(_request, timeout):
        assert timeout == 30
        raise OSError("server unavailable")
    monkeypatch.setattr(module.urllib.request, "urlopen", fail_request)
    with pytest.raises(OSError, match="server unavailable"):
        module.checkpoint_before_close()
