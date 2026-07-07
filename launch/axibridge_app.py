"""axibridge app shell: a pywebview window instead of a browser tab.

Double-clicked via launch/AxiBridge.app (no Terminal). Lifecycle contract:

* If a server is already listening on the port (started from a terminal, or
  a second app window), ATTACH to it and leave it running on close — this
  shell never kills a server it didn't start.
* Otherwise SPAWN ``.venv/bin/python -m axibridge`` (bound to 127.0.0.1 —
  the windowed app is a desk tool; the wide-open LAN bind stays a choice of
  the terminal launcher) and terminate it when the window closes.
* Closing is refused while a plot is running on an owned server — stop the
  job first. The server log is readable in the UI (Settings → Server log).

Import-safe: no side effects at import time (unit tests import the helpers).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYTHON = REPO / ".venv" / "bin" / "python"
PORT = 2942
URL = f"http://127.0.0.1:{PORT}"


def probe(timeout: float = 1.0) -> dict | None:
    """The server's /api/state, or None if nothing is listening."""
    try:
        with urllib.request.urlopen(f"{URL}/api/state", timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def spawn_server() -> subprocess.Popen:
    """Start the pinned interpreter's server, silenced (the in-app log ring
    is the log surface). stdin closed so nothing ever blocks on a tty."""
    return subprocess.Popen(
        [str(PYTHON), "-m", "axibridge", "--host", "127.0.0.1", "--port", str(PORT)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(REPO),
    )


def wait_ready(proc: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited during startup (code {proc.returncode})")
        if probe(0.5) is not None:
            return
        time.sleep(0.2)
    raise RuntimeError(f"server did not come up on {URL} within {timeout:.0f}s")


def terminate(proc: subprocess.Popen, grace: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()  # uvicorn's shutdown runs manager.shutdown(): pen up, port released
    try:
        proc.wait(grace)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def plot_running() -> bool:
    state = probe()
    return bool(state) and state.get("machine", {}).get("job_state") not in (None, "idle")


def main() -> None:
    import webview  # deferred: import cost + lets tests import this module headless

    owned: subprocess.Popen | None = None
    if probe() is None:
        if not PYTHON.exists():
            raise SystemExit(f"pinned interpreter not found: {PYTHON}")
        owned = spawn_server()
        try:
            wait_ready(owned)
        except Exception:
            terminate(owned)
            raise

    window = webview.create_window("axibridge", URL, width=1440, height=900)

    def on_closing():
        # never strand a moving plotter: an owned server mid-plot refuses to die
        if owned is not None and plot_running():
            window.evaluate_js(
                "alert('a plot is running — stop it (Plot tab) before closing the app')")
            return False  # cancels the close
        return True

    window.events.closing += on_closing
    try:
        webview.start()
    finally:
        if owned is not None:
            terminate(owned)


if __name__ == "__main__":
    sys.exit(main())
