"""A real server crash preserves a timed recovery for the next process."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
PYTHON = REPO / ".venv/bin/python"


def _free_port() -> int:
    while True:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port != 2942:
            return port


def _json_request(base: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        base + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def _wait_ready(process: subprocess.Popen, base: str, log_path: Path) -> None:
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"server exited early ({process.returncode}): {log_path.read_text()[-4000:]}")
        try:
            _json_request(base, "/api/project")
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.1)
    raise AssertionError(f"server did not start: {log_path.read_text()[-4000:]}")


def test_sigkill_after_timer_snapshot_restores_kept_project_and_history(tmp_path: Path):
    config = tmp_path / "config"
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "AXIBRIDGE_CONFIG_DIR": str(config), "AXIBRIDGE_NO_AUTOCONNECT": "1"}
    log_path = tmp_path / "server.log"
    processes: list[subprocess.Popen] = []

    with log_path.open("wb") as log:
        def start_server() -> subprocess.Popen:
            process = subprocess.Popen(
                [str(PYTHON), "-m", "axibridge", "--host", "127.0.0.1", "--port", str(port)],
                cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            processes.append(process)
            _wait_ready(process, base, log_path)
            return process

        try:
            first = start_server()
            renamed = _json_request(base, "/api/project", "PUT", {"name": "Crash survivor"})
            session_id = renamed["session_id"]
            layer = _json_request(base, "/api/layers/generate", "POST", {
                "module": "polygon", "params": {"sides": 5, "radius": 10},
            })
            assert layer["id"]
            assert _json_request(base, "/api/project")["recovery"] == {}

            # No checkpoint endpoint is called: this waits for the live 30 s
            # lifespan timer to publish a complete ZIP on its own.
            deadline = time.monotonic() + 42
            archive = config / "recovery" / f"{session_id}.zip"
            while time.monotonic() < deadline:
                state = _json_request(base, "/api/project")
                if state["recovery"].get("revision") == state["revision"] and archive.is_file():
                    break
                time.sleep(0.25)
            else:
                raise AssertionError(f"30 s autosnapshot was not written: {log_path.read_text()[-4000:]}")

            first.kill()  # SIGKILL: lifespan shutdown cannot save for us.
            first.wait(timeout=5)
            assert first.returncode == -signal.SIGKILL

            start_server()
            offered = _json_request(base, "/api/recovery")
            assert offered["offered"] is True
            assert len(offered["entries"]) == 1
            entry = offered["entries"][0]
            assert entry["id"] == session_id and entry["name"] == "Crash survivor"
            created = datetime.fromisoformat(entry["created_at"].replace("Z", "+00:00"))
            assert created.tzinfo is not None and created <= datetime.now(timezone.utc)

            restored = _json_request(base, f"/api/recovery/{session_id}/restore", "POST", {})
            assert restored["name"] == "Crash survivor" and restored["dirty"] is True
            assert [item["id"] for item in restored["layers"]] == [layer["id"]]
            undone = _json_request(base, "/api/undo", "POST", {})
            assert undone["name"] == "Crash survivor" and undone["layers"] == []
            redone = _json_request(base, "/api/redo", "POST", {})
            assert [item["id"] for item in redone["layers"]] == [layer["id"]]
        finally:
            for process in processes:
                if process.poll() is not None:
                    continue
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
