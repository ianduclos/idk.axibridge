import time
from pathlib import Path

import httpx

from _mcp_harness import axb, call, http, srv, targets, text  # noqa: F401

REPO = Path(__file__).resolve().parent.parent


def facts(**kw):
    from axibridge_mcp.diagnose import Facts
    base = dict(pid=123, command=f"{REPO}/.venv/bin/python -m axibridge", cwd=str(REPO),
                started=time.time(), parent="launch/axibridge_app.py",
                newest_backend=("axibridge/session.py", time.time() - 3600),
                newest_frontend=("axibridge/static/js/main.js", time.time() - 3600),
                dist_built=time.time() - 60, error=None)
    return Facts(**{**base, **kw})


def test_assess_is_quiet_for_a_fresh_owned_server():
    from axibridge_mcp.diagnose import assess
    assert assess(facts(), REPO) == []


def test_assess_flags_backend_edits_after_start():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(newest_backend=("axibridge/api.py", time.time() + 5)), REPO)
    assert any("axibridge/api.py" in p and "restart" in p for p in out)


def test_assess_flags_a_server_from_another_checkout():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(cwd="/Users/x/old/idk.axibridge",
                       command="/Users/x/old/idk.axibridge/.venv/bin/python -m axibridge"), REPO)
    assert any("not this repo" in p for p in out)


def test_assess_flags_a_stale_frontend_build():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(dist_built=time.time() - 7200), REPO)
    assert any("npm run build" in p for p in out)


def test_assess_notes_an_orphan():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(parent="launchd"), REPO)
    assert any("orphan" in p for p in out)


def test_assess_reports_nothing_listening():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(pid=None, error="nothing listening on port 1"), REPO)
    assert out == ["nothing listening on port 1"]


def test_diagnose_tool_on_the_test_server(srv, axb):
    out = text(call(srv, "diagnose"))
    assert "pid" in out and str(REPO) in out


def test_logs_filters_by_text(srv, axb):
    with http(axb) as h:
        h.post("/api/layers/generate", json={"module": "nope", "params": {}})
    r = call(srv, "logs", {"level": "DEBUG", "limit": 500})
    assert not r.is_error, text(r)
    out = text(call(srv, "logs", {"contains": "zzz-not-there"}))
    assert out == "no matching log entries"


def test_sandbox_status_start_seed_stop(srv, targets, axb):
    with http(axb) as h:
        h.post("/api/layers/generate", json={"module": "polygon", "params": {}})
        h.post("/api/project/save", json={"name": "seed-me"}).raise_for_status()
    assert "not running" in text(call(srv, "sandbox", {"action": "status"}))
    r = call(srv, "sandbox", {"action": "start", "seed_project": "seed-me"})
    assert not r.is_error, text(r)
    url = targets.sandbox.url
    assert len(httpx.get(url + "/api/project").json()["layers"]) == 1
    assert "running" in text(call(srv, "sandbox", {"action": "status"}))
    call(srv, "sandbox", {"action": "stop"})
    assert not targets.sandbox.running


def test_seeding_an_already_running_sandbox(srv, targets, axb):
    with http(axb) as h:
        h.post("/api/layers/generate", json={"module": "polygon", "params": {}})
        h.post("/api/project/save", json={"name": "seed-two"}).raise_for_status()
    assert not call(srv, "sandbox", {"action": "start"}).is_error
    r = call(srv, "sandbox", {"action": "start", "seed_project": "seed-two"})
    assert not r.is_error, text(r)
    assert len(httpx.get(targets.sandbox.url + "/api/project").json()["layers"]) == 1
    call(srv, "sandbox", {"action": "stop"})
    call(srv, "sandbox", {"action": "stop"})  # idempotent


def test_first_live_call_carries_the_stale_warning_once(axb):
    from axibridge_mcp.server import build_server
    from axibridge_mcp.targets import Targets
    t = Targets(live_url=axb, stale_check=lambda url: "WARNING: stale test server")
    try:
        srv = build_server(t)
        first = text(call(srv, "state"))
        second = text(call(srv, "state"))
    finally:
        t.close()
    assert first.startswith("WARNING: stale test server")
    assert "WARNING" not in second


def test_assess_accepts_command_in_repo_with_foreign_cwd():
    from axibridge_mcp.diagnose import assess
    assert assess(facts(cwd="/"), REPO) == []


def test_assess_flags_sibling_repo_prefix():
    from axibridge_mcp.diagnose import assess
    out = assess(facts(cwd="/", command=f"{REPO}-old/.venv/bin/python -m axibridge"), REPO)
    assert any("not this repo" in p for p in out)


def test_newest_skips_junk_files(tmp_path, monkeypatch):
    from axibridge_mcp import diagnose
    monkeypatch.setattr(diagnose, "REPO", tmp_path)
    (tmp_path / "a.js").write_text("x")
    import os
    os.utime(tmp_path / "a.js", (1000, 1000))
    for n in (".DS_Store", "b.js~", "c.swp", "d.tmp"):
        (tmp_path / n).write_text("x")
    best = diagnose._newest(tmp_path, "**/*", tmp_path)
    assert best[0] == "a.js"


def test_raising_stale_check_does_not_break_first_call(axb):
    from axibridge_mcp.server import build_server
    from axibridge_mcp.targets import Targets

    def boom(url):
        raise RuntimeError("boom")
    t = Targets(live_url=axb, stale_check=boom)
    try:
        r = call(build_server(t), "state")
    finally:
        t.close()
    assert not r.is_error, text(r)


def test_stale_warning_swallows_gather_errors(monkeypatch):
    from axibridge_mcp import diagnose
    monkeypatch.setattr(diagnose, "gather", lambda url: 1 / 0)
    assert diagnose.stale_warning("http://127.0.0.1:1") is None


def test_sandbox_rejects_bad_seed_names(srv, targets, tmp_path):
    for bad in ("../x", str(tmp_path), "a/b", ".."):
        r = call(srv, "sandbox", {"action": "start", "seed_project": bad})
        assert r.is_error, bad
        assert not targets.sandbox.running
    assert list(tmp_path.iterdir()) == []


def test_failed_seed_on_fresh_start_stops_sandbox(srv, targets):
    r = call(srv, "sandbox", {"action": "start", "seed_project": "no-such-project"})
    assert r.is_error
    assert not targets.sandbox.running
