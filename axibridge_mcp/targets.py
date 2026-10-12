"""Where tools point. `live` is Ian's running app — attach-only, never
started or killed here. `sandbox` is a server this process owns: temp port,
temp config, temp projects folder, killed on close()."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import json
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Literal

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from .client import ApiClient

REPO = Path(__file__).resolve().parent.parent
PYTHON = REPO / ".venv" / "bin" / "python"
DEFAULT_LIVE_URL = "http://127.0.0.1:2942"
TargetName = Literal["live", "sandbox"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Sandbox:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.dir: Path | None = None
        self.url: str | None = None
        self._log = None
        self._lock = threading.RLock()

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, timeout: float = 45.0) -> str:
        with self._lock:
            return self._start(timeout)

    def _start(self, timeout: float) -> str:
        if self.running:
            return self.url  # type: ignore[return-value]
        self.stop()  # clear a dead one
        self.dir = Path(tempfile.mkdtemp(prefix="axibridge-mcp-sandbox-"))
        port = _free_port()
        # projects_root goes into the config dir BEFORE the server exists, so
        # there is never a window where it points at Ian's real folder
        (self.dir / "config").mkdir()
        (self.dir / "config" / "settings.json").write_text(
            json.dumps({"projects_root": str(self.dir / "projects")}))
        env = {**os.environ, "AXIBRIDGE_CONFIG_DIR": str(self.dir / "config"),
               "AXIBRIDGE_NO_AUTOCONNECT": "1"}
        python = str(PYTHON if PYTHON.exists() else sys.executable)
        self._log = open(self.dir / "server.log", "wb")
        self.proc = subprocess.Popen(
            [python, "-m", "axibridge", "--host", "127.0.0.1", "--port", str(port)],
            cwd=REPO, env=env, stdin=subprocess.DEVNULL, stdout=self._log,
            stderr=subprocess.STDOUT)
        self.url = f"http://127.0.0.1:{port}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                tail = self.log_tail()
                self.stop()
                raise ToolError(f"sandbox server exited during startup:\n{tail}")
            try:
                httpx.get(self.url + "/api/project", timeout=1.0)
                break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            self.stop()
            raise ToolError(f"sandbox server did not answer within {timeout:.0f} s")
        return self.url

    def log_tail(self, n: int = 20) -> str:
        if not self.dir or not (self.dir / "server.log").exists():
            return "(no sandbox log)"
        lines = (self.dir / "server.log").read_text(errors="replace").splitlines()
        return "\n".join(lines[-n:]) or "(sandbox log empty)"

    def stop(self) -> None:
        with self._lock:
            self._stop()

    def _stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self._log is not None:
            self._log.close()
            self._log = None
        if self.dir is not None:
            shutil.rmtree(self.dir, ignore_errors=True)
            self.dir = None
        self.url = None


class Targets:
    def __init__(self, live_url: str | None = None,
                 stale_check: Callable[[str], str | None] | None = None) -> None:
        self.live_url = (live_url or os.environ.get("AXIBRIDGE_MCP_LIVE_URL")
                         or DEFAULT_LIVE_URL).rstrip("/")
        self.sandbox = Sandbox()
        self._stale_check = stale_check
        self._live = ApiClient(
            self.live_url, "live",
            lambda: f"the live app isn't running at {self.live_url} — open AxiBridge.app")
        self._sandbox_client: ApiClient | None = None
        self._live_checked = False
        self._lock = threading.RLock()
        self._warning: str | None = None

    def client(self, target: TargetName) -> ApiClient:
        with self._lock:
            return self._client(target)

    def _client(self, target: TargetName) -> ApiClient:
        if target == "live":
            if not self._live_checked:
                self._live_checked = True
                if self._stale_check is not None:
                    self._warning = self._stale_check(self.live_url)
            return self._live
        if target == "sandbox":
            url = self.sandbox.start()
            if self._sandbox_client is None or self._sandbox_client.base_url != url:
                if self._sandbox_client is not None:
                    self._sandbox_client.close()
                self._sandbox_client = ApiClient(
                    url, "sandbox",
                    lambda: "the sandbox server died:\n" + self.sandbox.log_tail())
            return self._sandbox_client
        raise ToolError(f"unknown target {target!r} — use 'live' or 'sandbox'")

    def live_only(self, target: TargetName) -> ApiClient:
        if target != "live":
            raise ToolError("motion tools only drive the live app — the sandbox has no machine")
        return self.client("live")

    def take_warning(self) -> str | None:
        with self._lock:
            warning, self._warning = self._warning, None
            return warning

    def close(self) -> None:
        with self._lock:
            self.sandbox.stop()
            self._live.close()
            if self._sandbox_client is not None:
                self._sandbox_client.close()
                self._sandbox_client = None
