"""Keeps the MCP honest while the app changes under it. In-process, no
server: an app change that strands a tool fails HERE, naming the tool file
and the endpoint, in the same suite run as the change itself."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="mcp extra not installed (backend-only machine)")

import anyio  # noqa: E402
from mcp.client.client import Client  # noqa: E402

from axibridge.app import create_app  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MCP_DIR = REPO / "axibridge_mcp"
# '/api/...' in a plain or f-string literal; stops at a quote, query or space,
# but swallows whole {placeholders} so f"/api/layers/{layer['id']}" stays whole
LITERAL = re.compile(r"""["'](/api/(?:[^"'?\s{]|\{[^}]*\})*)""")
PARAM = re.compile(r"\{[^}]+\}")
# control endpoints that are safe by design (stopping is the safe direction)
SAFE_CONTROL = {"/api/plot/stop", "/api/plot/pause"}
# path segments that smell like machine motion. A non-GET route containing one
# must be refused by call_api or listed in REVIEWED_NOT_MOTION with a reason.
MOTION_WORDS = {"machine", "plot", "jog", "goto", "home", "pen", "motor", "motors",
                "raw", "calibration", "teststroke", "servo"}
REVIEWED_NOT_MOTION: dict[str, str] = {
    # "/api/example/plot-preview": "renders an image, never touches the machine",
    # Gesture Studies (2026-10-17): saved-study store + recipe validation; no geometry, no machine
    "/api/gesture-studies": "saves a study recipe to the machine-level store, never touches the machine",
    "/api/gesture-studies/validate": "validates a study recipe, never touches the machine",
    "/api/gesture-studies/{}": "deletes a saved study recipe, never touches the machine",
    # Studies v2 (2026-10-17): a chorus kept as a group of layers (creates project layers, no machine)
    "/api/gesture-studies/keep": "adds a group of layers to the project, never touches the machine",
}


def app_routes() -> set[tuple[str, str]]:
    spec = create_app().openapi()
    return {(method.upper(), PARAM.sub("{}", path))
            for path, ops in spec["paths"].items() for method in ops}


def used_paths() -> dict[str, set[str]]:
    used: dict[str, set[str]] = {}
    for f in sorted(MCP_DIR.glob("*.py")):
        for m in LITERAL.finditer(f.read_text()):
            path = PARAM.sub("{}", m.group(1)).rstrip("/")
            if path == "/api":  # tools_api's prefix check, not an endpoint
                continue
            used.setdefault(path, set()).add(f.name)
    return used


def test_the_mcp_finds_its_endpoints():
    # guards the guard: if the literal scan breaks, the drift test passes vacuously
    used = used_paths()
    assert "/api/project" in used and "/api/layers/{}/regenerate" in used


def test_every_endpoint_the_mcp_calls_still_exists():
    routes = {path for _, path in app_routes()}
    missing = {p: sorted(files) for p, files in used_paths().items() if p not in routes}
    assert not missing, (
        "the MCP calls endpoints the app no longer has — fix the tool in the same change:\n"
        + "\n".join(f"  {p}  (used in {', '.join(files)})" for p, files in sorted(missing.items())))


def test_every_motion_shaped_endpoint_is_refused_by_call_api():
    from mcp.server.mcpserver.exceptions import ToolError
    from axibridge_mcp.tools_api import check_allowed

    unguarded = []
    for method, path in sorted(app_routes()):
        segments = set(path.strip("/").split("/"))
        if method == "GET" or not segments & MOTION_WORDS:
            continue
        if path in SAFE_CONTROL or path in REVIEWED_NOT_MOTION:
            continue
        if path == "/api/pens" or path.startswith("/api/pens/"):
            continue  # the pen LIBRARY (names, colours), not the pen servo
        try:
            check_allowed(method, path.replace("{}", "x"), "sandbox")
        except ToolError:
            continue
        unguarded.append(f"{method} {path}")
    assert not unguarded, (
        "new motion-shaped endpoints reachable through call_api — block them in "
        "tools_api._MOTION, or add them to REVIEWED_NOT_MOTION with a reason:\n  "
        + "\n  ".join(unguarded))


def tool_names() -> set[str]:
    from axibridge_mcp.server import build_server
    from axibridge_mcp.targets import Targets

    t = Targets(live_url="http://127.0.0.1:9")  # never contacted: listing is local

    async def go():
        async with Client(build_server(t)) as c:
            return {tool.name for tool in (await c.list_tools()).tools}
    try:
        return anyio.run(go)
    finally:
        t.close()


def test_the_docs_name_every_tool():
    doc = (REPO / "docs" / "MCP.md").read_text()
    missing = sorted(n for n in tool_names() if f"`{n}`" not in doc)
    assert not missing, f"docs/MCP.md doesn't mention: {missing}"


def test_every_tool_has_a_docstring_the_agent_can_read():
    async def go():
        from axibridge_mcp.server import build_server
        from axibridge_mcp.targets import Targets
        t = Targets(live_url="http://127.0.0.1:9")
        try:
            async with Client(build_server(t)) as c:
                return [(x.name, x.description or "") for x in (await c.list_tools()).tools]
        finally:
            t.close()
    thin = [name for name, desc in anyio.run(go) if len(desc.strip()) < 20]
    assert not thin, f"tools without a real description: {thin}"


def test_the_mcp_notices_its_own_source_changed(tmp_path, monkeypatch):
    import axibridge_mcp
    from axibridge_mcp import diagnose

    assert diagnose.mcp_self_warning() is None or axibridge_mcp.STARTED < time.time()
    monkeypatch.setattr(axibridge_mcp, "STARTED", 0.0)  # older than any source file
    hit = diagnose.mcp_self_warning()
    assert hit is not None and "/mcp" in hit[0]
