"""Server log ring (+ /api/logs) and the pywebview app shell's helpers.
The webview event loop itself is manually verified — these tests cover
everything up to the window."""

import logging
import subprocess
import sys
import time

import pytest

from axibridge import logbuf


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        yield c


# NOTE: pytest's logging plugin restores the ROOT level to WARNING around
# tests, undoing install()'s INFO bump (a production concern only uvicorn
# sees). The tests pin their own logger's level so they don't depend on it,
# and filter to that logger — other libraries (httpx) also log into the ring.
def _test_logger():
    lg = logging.getLogger("axibridge.test")
    lg.setLevel(logging.INFO)
    return lg


def _ours(entries):
    return [e for e in entries if e["logger"] == "axibridge.test"]


def test_logbuf_captures_and_filters():
    logbuf.install()
    _test_logger().info("ring me %s", "once")
    entries = logbuf.entries()
    assert any(e["msg"] == "ring me once" for e in entries)
    last = entries[-1]["id"]
    assert logbuf.entries(after=last) == []
    _test_logger().warning("newer")
    newer = _ours(logbuf.entries(after=last))
    assert [e["msg"] for e in newer] == ["newer"]
    assert newer[0]["level"] == "WARNING"


def test_logbuf_install_is_idempotent():
    logbuf.install()
    logbuf.install()
    _test_logger().info("exactly one entry")
    added = [e for e in logbuf.entries() if e["msg"] == "exactly one entry"]
    assert len(added) == 1  # two installs must not mean two handlers


def test_logs_endpoint(client):
    _test_logger().info("visible through the api")
    r = client.get("/api/logs")
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert any(e["msg"] == "visible through the api" for e in entries)
    last = entries[-1]["id"]
    later = client.get(f"/api/logs?after={last}").json()["entries"]
    assert _ours(later) == []  # cursor works (httpx logs its own requests)
    assert client.get("/api/logs?after=-1").status_code == 422


def test_app_shell_imports_without_side_effects():
    """Importing the shell must not probe, spawn, or open anything."""
    sys.path.insert(0, "launch")
    try:
        import axibridge_app
    finally:
        sys.path.pop(0)
    assert axibridge_app.PORT == 2942
    assert axibridge_app.PYTHON.name == "python"
    assert axibridge_app.REPO.joinpath("axibridge").is_dir()


def test_app_shell_spawn_probe_terminate_cycle():
    """The ownership lifecycle end-to-end, minus the window: nothing on the
    port -> spawn -> ready -> probe sees state -> terminate -> port free."""
    sys.path.insert(0, "launch")
    try:
        import axibridge_app as shell
    finally:
        sys.path.pop(0)
    if shell.probe() is not None:
        pytest.skip("a real axibridge server is already running on 2942")
    proc = shell.spawn_server()
    try:
        shell.wait_ready(proc)
        state = shell.probe()
        assert state and "machine" in state
        assert shell.plot_running() is False  # fresh server: idle
    finally:
        shell.terminate(proc)
    assert proc.poll() is not None
    deadline = time.monotonic() + 5
    while shell.probe(0.3) is not None and time.monotonic() < deadline:
        time.sleep(0.2)
    assert shell.probe(0.3) is None  # port released


def test_app_shell_wait_ready_reports_early_exit():
    sys.path.insert(0, "launch")
    try:
        import axibridge_app as shell
    finally:
        sys.path.pop(0)
    dead = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
    dead.wait()
    with pytest.raises(RuntimeError, match="exited during startup"):
        shell.wait_ready(dead, timeout=2)
