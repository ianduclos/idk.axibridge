"""Regression checks for recovery timing and failed project replacement."""

from __future__ import annotations

import io
import json
import threading
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axibridge import api as api_module, project_io
from axibridge.app import create_app
from axibridge.session import session


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _rename(client, name):
    response = client.put("/api/project", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


def test_save_keeps_later_edit_dirty_and_its_recovery(client, monkeypatch):
    changed = _rename(client, "snapshot on disk")
    assert client.post("/api/recovery/checkpoint").status_code == 200
    original = project_io.save_project

    def save_then_edit(*args, **kwargs):
        original(*args, **kwargs)
        session.project.name = "later edit"

    monkeypatch.setattr(project_io, "save_project", save_then_edit)
    response = client.post("/api/project/save", json={})
    assert response.status_code == 200, response.text
    saved_name = json.loads((Path(response.json()["saved"]) / "project.json").read_text())["name"]
    state = client.get("/api/project").json()
    assert saved_name == "snapshot on disk"
    assert state["name"] == "later edit" and state["dirty"] is True
    assert session.recovery_store.load(changed["session_id"])[1][0].name == "snapshot on disk"


def test_inflight_checkpoint_cannot_resurrect_archive_after_save(client, monkeypatch):
    _rename(client, "race save")
    store = session.recovery_store
    original_write = store.write
    entered = threading.Event()
    release = threading.Event()
    save_started = threading.Event()
    save_done = threading.Event()
    failures = []
    responses = []

    def delayed_write(snapshot):
        entered.set()
        assert release.wait(3), "test did not release checkpoint"
        return original_write(snapshot)

    def checkpoint():
        try:
            session.checkpoint_recovery()
        except Exception as exc:
            failures.append(exc)

    def save():
        save_started.set()
        try:
            responses.append(api_module.save_project(api_module.SaveBody()))
        except Exception as exc:
            failures.append(exc)
        finally:
            save_done.set()

    monkeypatch.setattr(store, "write", delayed_write)
    checkpoint_thread = threading.Thread(target=checkpoint, daemon=True)
    save_thread = threading.Thread(target=save, daemon=True)
    checkpoint_thread.start()
    try:
        assert entered.wait(3), "checkpoint did not enter write"
        save_thread.start()
        assert save_started.wait(3)
        assert not save_done.wait(0.05), "save passed an in-flight checkpoint"
    finally:
        release.set()
        checkpoint_thread.join(3)
        if save_thread.ident is not None:
            save_thread.join(3)
    assert not checkpoint_thread.is_alive() and not save_thread.is_alive()
    assert not failures and responses
    assert session.recovery_status()["dirty"] is False
    assert store.list_entries() == []


def test_edit_after_replacement_checkpoint_blocks_new_and_stays_in_memory(client, monkeypatch):
    changed = _rename(client, "checkpointed before replacement")
    original = api_module._recovery_checkpoint

    def checkpoint_then_edit():
        entry = original()
        session.project.name = "late edit before replacement"
        return entry

    monkeypatch.setattr(api_module, "_recovery_checkpoint", checkpoint_then_edit)
    response = client.post("/api/project/new", json={"recovery_action": "recover"})
    assert response.status_code == 409
    state = client.get("/api/project").json()
    assert state["name"] == "late edit before replacement"
    assert state["dirty"] is True and state["session_id"] == changed["session_id"]
    assert session.recovery_store.load(changed["session_id"])[1][0].name == "checkpointed before replacement"


def test_failed_discard_import_keeps_current_project_and_archive(client):
    changed = _rename(client, "dirty before bad import")
    assert client.post("/api/recovery/checkpoint").status_code == 200
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("unrelated.txt", "x")

    response = client.post("/api/project/import?recovery_action=discard", files={
        "file": ("broken.zip", payload.getvalue(), "application/zip")
    })
    assert response.status_code == 400
    state = client.get("/api/project").json()
    assert state["name"] == "dirty before bad import"
    assert state["dirty"] is True and state["session_id"] == changed["session_id"]
    assert session.recovery_store.load(changed["session_id"])[1][0].name == "dirty before bad import"


def test_recovery_offer_is_not_consumed_while_current_project_is_dirty(client, monkeypatch):
    monkeypatch.setattr(api_module, "_recovery_offered", False)
    older = _rename(client, "older unfinished")
    assert client.post("/api/project/new", json={"recovery_action": "recover"}).status_code == 200
    _rename(client, "currently dirty")
    first = client.get("/api/recovery").json()
    assert first["offered"] is False
    assert [entry["id"] for entry in first["entries"]] == [older["session_id"]]

    assert client.post("/api/project/new", json={"recovery_action": "discard"}).status_code == 200
    second = client.get("/api/recovery").json()
    assert second["offered"] is True
    assert [entry["id"] for entry in second["entries"]] == [older["session_id"]]
    assert client.get("/api/recovery").json()["offered"] is True
    assert client.post("/api/recovery/ack").status_code == 200
    assert client.get("/api/recovery").json()["offered"] is False
