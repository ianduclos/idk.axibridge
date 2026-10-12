"""Live sync: every project change bumps Session.edit_rev and is announced
once on the event bus as {type: "project", rev, origin} — after the request
finished, so a subscriber that refetches sees the post-mutation state."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.events import bus

REPO = Path(__file__).resolve().parent.parent
POLY = {"module": "polygon", "params": {"sides": 5, "radius": 20}}


@pytest.fixture()
def api(monkeypatch):
    seen: list[dict] = []
    with TestClient(create_app()) as c:
        monkeypatch.setattr(bus, "emit", lambda ev: seen.append(ev))
        yield c, seen


def project_events(seen):
    return [e for e in seen if e.get("type") == "project"]


def emits(seen, fn) -> list[dict]:
    """Run fn and return the project events it caused."""
    before = len(project_events(seen))
    fn()
    return project_events(seen)[before:]


def test_edit_rev_is_in_the_project_payload_and_moves_on_edit(api):
    c, _ = api
    r0 = c.get("/api/project").json()["edit_rev"]
    c.post("/api/layers/generate", json=POLY)
    assert c.get("/api/project").json()["edit_rev"] > r0


def test_one_event_per_changing_request_carrying_origin_and_rev(api):
    c, seen = api
    ev = emits(seen, lambda: c.post("/api/layers/generate", json=POLY,
                                    headers={"X-Axb-Client": "tab-1"}))
    assert len(ev) == 1
    assert ev[0]["origin"] == "tab-1"
    assert ev[0]["rev"] == c.get("/api/project").json()["edit_rev"]


def test_origin_is_null_without_the_header(api):
    c, seen = api
    ev = emits(seen, lambda: c.post("/api/layers/generate", json=POLY))
    assert len(ev) == 1 and ev[0]["origin"] is None


def test_reads_and_refused_requests_announce_nothing(api):
    c, seen = api
    assert emits(seen, lambda: c.get("/api/project")) == []
    assert emits(seen, lambda: c.get("/api/compose/resolved")) == []
    # nothing to undo → 409, no state change
    assert emits(seen, lambda: c.post("/api/undo")) == []
    # unknown layer → 404 before any checkpoint
    assert emits(seen, lambda: c.patch("/api/layers/nope", json={"name": "x"})) == []


def test_every_kind_of_change_is_announced(api):
    c, seen = api
    lid = c.post("/api/layers/generate", json=POLY).json()["id"]
    assert len(emits(seen, lambda: c.patch(f"/api/layers/{lid}", json={"name": "renamed"}))) == 1
    assert len(emits(seen, lambda: c.post(f"/api/layers/{lid}/regenerate",
                                          json={"params": {"sides": 6}, "coalesce": True}))) == 1
    # a coalesced run still changes state, so it is still announced
    assert len(emits(seen, lambda: c.post(f"/api/layers/{lid}/regenerate",
                                          json={"params": {"sides": 7}, "coalesce": True}))) == 1
    assert len(emits(seen, lambda: c.post("/api/undo"))) == 1
    assert len(emits(seen, lambda: c.post("/api/redo"))) == 1
    assert len(emits(seen, lambda: c.post("/api/project/save", json={"name": "sync-test"}))) == 1
    assert len(emits(seen, lambda: c.post("/api/project/new",
                                          json={"recovery_action": "discard"}))) == 1
    assert len(emits(seen, lambda: c.post("/api/project/load",
                                          json={"name": "sync-test",
                                                "recovery_action": "discard"}))) == 1


def test_edit_rev_never_goes_backwards_across_projects(api):
    c, _ = api
    c.post("/api/layers/generate", json=POLY)
    before = c.get("/api/project").json()["edit_rev"]
    c.post("/api/project/new", json={"recovery_action": "discard"})
    assert c.get("/api/project").json()["edit_rev"] > before


def test_client_id_does_not_need_a_secure_context():
    # Review Focus 1: the app is opened over plain http from the LAN, where
    # crypto.randomUUID is undefined. The tab id must not depend on it.
    src = (REPO / "axibridge" / "static" / "js" / "api.js").read_text()
    assert "X-Axb-Client" in src
    assert "randomUUID" not in src


def test_a_handler_that_raises_after_checkpointing_still_announces(api, monkeypatch):
    # PUT /api/project has no try/except, so an exception escapes the handler
    # after Session._checkpoint() already moved edit_rev — the middleware must
    # still announce it, or open windows silently miss a real change.
    from axibridge.session import session
    c, seen = api

    def checkpoint_then_fail(patch):
        with session._lock:
            session._checkpoint()
        raise RuntimeError("boom after checkpoint")
    monkeypatch.setattr(session, "update_project", checkpoint_then_fail)
    before, n0 = session.edit_rev, len(project_events(seen))
    with pytest.raises(RuntimeError, match="boom after checkpoint"):
        c.put("/api/project", json={"name": "x"}, headers={"X-Axb-Client": "tab-9"})
    ev = project_events(seen)[n0:]
    assert session.edit_rev != before
    assert len(ev) == 1
    assert ev[0]["rev"] == session.edit_rev and ev[0]["origin"] == "tab-9"
