"""Shared harness for the MCP tests: a real axibridge on a temp port (never
2942, never Ian's config or projects folder) and an in-process MCP client.

Skips the importing module when the `mcp` extra isn't installed (the Pi)."""

from __future__ import annotations

import base64
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="mcp extra not installed (backend-only machine)")

import anyio  # noqa: E402
import httpx  # noqa: E402
from mcp.client.client import Client  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server() -> tuple[subprocess.Popen, str]:
    root = Path(tempfile.mkdtemp(prefix="axibridge-mcp-test-"))
    port = free_port()
    env = {**os.environ, "AXIBRIDGE_CONFIG_DIR": str(root / "config"),
           "AXIBRIDGE_NO_AUTOCONNECT": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "axibridge.app:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("test server exited during startup")
        try:
            httpx.get(base + "/api/project", timeout=1.0)
            break
        except httpx.HTTPError:
            time.sleep(0.15)
    else:
        proc.kill()
        raise RuntimeError("test server never answered")
    # the default projects_root is Ian's real ~/AxidrawProjects even with a
    # temp config dir — point it somewhere disposable before anything saves
    httpx.put(base + "/api/settings", json={"projects_root": str(root / "projects")},
              timeout=10).raise_for_status()
    return proc, base


def stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def http(base: str) -> httpx.Client:
    return httpx.Client(base_url=base, timeout=60)


@pytest.fixture(scope="module")
def axb():
    proc, base = start_server()
    yield base
    stop_server(proc)


@pytest.fixture()
def targets(axb):
    from axibridge_mcp.targets import Targets

    with http(axb) as h:
        h.post("/api/project/new", json={"recovery_action": "discard"}).raise_for_status()
    t = Targets(live_url=axb)
    yield t
    t.close()


@pytest.fixture()
def srv(targets):
    from axibridge_mcp.server import build_server

    return build_server(targets)


def call(srv, name: str, args: dict | None = None):
    async def go():
        async with Client(srv) as c:
            return await c.call_tool(name, args or {})
    return anyio.run(go)


def text(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


def images(result) -> list[bytes]:
    return [base64.b64decode(c.data) for c in result.content if c.type == "image"]
