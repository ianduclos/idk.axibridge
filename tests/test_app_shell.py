"""Server log ring (+ /api/logs) and the pywebview app shell's helpers.
The webview event loop itself is manually verified — these tests cover
everything up to the window."""

import logging
import subprocess
import sys
import time
from pathlib import Path

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


# -- macOS chrome integration -------------------------------------------------
#
# Both tweaks poke at AppKit and pywebview internals, so they are written to
# degrade rather than raise: a failure must leave the stock title bar and the
# in-page menu, never stop the window opening. These tests pin that contract
# (they run headless on any platform — no window is created).

def _shell():
    sys.path.insert(0, "launch")
    try:
        import axibridge_app
        return axibridge_app
    finally:
        sys.path.pop(0)


class _FakeWindow:
    """A window with no native handle — the degraded path."""

    native = None

    def __init__(self):
        self.js = []

    def evaluate_js(self, src):
        self.js.append(src)


def test_integrate_titlebar_degrades_without_a_native_window():
    assert _shell().integrate_titlebar(_FakeWindow()) is False


def test_integrate_titlebar_survives_a_hostile_window():
    """Anything unexpected from pywebview must be swallowed, not raised."""
    class Boom:
        @property
        def native(self):
            raise RuntimeError("no window yet")

    assert _shell().integrate_titlebar(Boom()) is False


def test_menu_items_only_proxy_existing_controls():
    """Same rule as the in-page bar (menu.js): every item clicks a control that
    already exists, so the native menu cannot drift from the app's own logic.
    No item may call an API directly."""
    shell = _shell()
    win = _FakeWindow()
    menus = shell.build_menu(win)
    if not menus:
        pytest.skip("pywebview menu API unavailable")

    # neither "Edit" nor "View": pywebview installs its own of both, and its
    # Edit > Undo means "undo my typing", not "undo the project"
    assert [m.title for m in menus] == ["File", "History", "Canvas"]

    index = (Path("axibridge/static/index.html")).read_text()
    clicked = 0
    for menu in menus:
        for item in menu.items:
            fn = getattr(item, "function", None)
            if fn is None:      # separator
                continue
            win.js.clear()
            fn()
            (src,) = win.js
            assert ".click()" in src, f"{item.title!r} must proxy a real control"
            assert "/api/" not in src, f"{item.title!r} must not call the API directly"
            selector = src.split("'")[1]
            token = selector.split("[")[0].split()[0].lstrip("#")  # "#a b[c]" -> "a"
            assert token in index, f"{item.title!r} targets {selector}, absent from index.html"
            clicked += 1
    assert clicked >= 6


def test_refresh_frontend_build_never_creates_one(tmp_path, monkeypatch):
    """It keeps an existing build fresh; with no build it must leave the
    source alone, or a machine with no npm would be worse off than before
    there was a build step at all."""
    shell = _shell()
    monkeypatch.setattr(shell, "REPO", tmp_path)
    (tmp_path / "axibridge").mkdir()
    called = []
    monkeypatch.setattr(shell.subprocess, "run",
                        lambda *a, **k: called.append(a) or _Ran(0))

    assert "no build" in shell.refresh_frontend_build()
    assert not called, "must not build when there is no build"

    dist = tmp_path / "axibridge" / "static_dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>")
    (tmp_path / "node_modules").mkdir()
    monkeypatch.setattr(shell.shutil, "which", lambda _: "/usr/bin/npm")
    assert shell.refresh_frontend_build() == "built (refreshed)"
    assert called, "an existing build must be refreshed"


def test_refresh_frontend_build_survives_a_broken_toolchain(tmp_path, monkeypatch):
    """A failed build must never stop the window opening."""
    shell = _shell()
    monkeypatch.setattr(shell, "REPO", tmp_path)
    dist = tmp_path / "axibridge" / "static_dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>")
    (tmp_path / "node_modules").mkdir()
    monkeypatch.setattr(shell.shutil, "which", lambda _: "/usr/bin/npm")
    monkeypatch.setattr(shell.subprocess, "run",
                        lambda *a, **k: _Ran(1, err="vite exploded"))
    assert "REFRESH FAILED" in shell.refresh_frontend_build()


class _Ran:
    def __init__(self, code, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_mark_native_shell_publishes_shell_and_titlebar_state():
    """The title-bar tweak is a best-effort AppKit poke, and three separate
    rounds of it failed by doing nothing at all rather than raising. Its
    outcome is published to the DOM so a no-op is inspectable."""
    shell = _shell()
    win = _FakeWindow()
    shell.integrate_titlebar(win)          # no native window -> degraded path
    shell.mark_native_shell(win)
    (src,) = win.js
    assert "dataset.shell = 'native'" in src
    assert "dataset.titlebar = 'no-native-window'" in src
