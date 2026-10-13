"""The real entry point over stdio — what Claude Code actually launches."""

import os
import sys
import time

import anyio
import httpx

from _mcp_harness import REPO, axb, text  # noqa: F401
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters

ROSTER = {"state", "see", "see_ui", "modules", "module_schema", "try_generator", "try_effects",
          "add_layer", "edit_layer", "delete_layers", "reorder_layers", "undo", "redo",
          "project", "save_project", "estimate", "plot", "pen", "jog", "go_home", "stop",
          "pause", "logs", "diagnose", "sandbox", "call_api"}


def params(axb):
    return StdioServerParameters(command=sys.executable, args=["-m", "axibridge_mcp"],
                                 env={**os.environ, "AXIBRIDGE_MCP_LIVE_URL": axb}, cwd=str(REPO))


def test_stdio_server_lists_the_full_roster(axb):
    async def go():
        async with Client(params(axb)) as c:
            return {t.name for t in (await c.list_tools()).tools}
    assert anyio.run(go) == ROSTER


def test_stdio_exit_stops_the_sandbox(axb):
    # Claude Code closing the session must not leak a server
    async def go():
        async with Client(params(axb)) as c:
            out = await c.call_tool("sandbox", {"action": "start"})
            return text(out)
    out = anyio.run(go)
    url = out.split("running at ")[1].split()[0]
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            httpx.get(url + "/api/project", timeout=0.5)
            time.sleep(0.3)
        except httpx.HTTPError:
            return
    raise AssertionError(f"sandbox at {url} survived the MCP process")
