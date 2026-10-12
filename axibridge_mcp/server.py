"""axibridge MCP server: see, compose, tune, diagnose — and, with Ian's
per-call approval, plot. Entry point: `python -m axibridge_mcp` (stdio)."""

from __future__ import annotations

import atexit
import functools
import signal
import sys

from mcp.server.mcpserver import MCPServer

from . import tools_compose, tools_look, tools_machine, tools_modules
from .targets import Targets

INSTRUCTIONS = """\
axibridge is Ian's pen-plotter compositor (AxiDraw V3). Coordinates are
millimetres in the machine frame (x right <= 300, y down <= 218).
Targets: 'live' is Ian's open app — he sees every edit, and his cmd-Z undoes
yours. 'sandbox' is a private server for experiments and dev checks.
Start with `state`, look with `see`, tune with `try_generator`/`try_effects`.
Motion tools (plot, pen, jog, go_home) are live-only and Ian approves each
call: show him `see` + `estimate` first. `stop` is always safe.
"""

MODULES = (tools_look, tools_modules, tools_compose, tools_machine)


def make_tool_decorator(srv: MCPServer, targets: Targets):
    """Register fn as an unstructured tool whose result gets the one-time
    stale-server warning prefixed (see Targets.client). Tools must be sync
    functions: an async tool would return an un-awaited coroutine through the
    wrapper."""
    def tool(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            out = fn(*args, **kwargs)
            warning = targets.take_warning()
            if not warning:
                return out
            return [warning, *out] if isinstance(out, list) else [warning, out]

        srv.tool(structured_output=False)(wrapper)
        return fn
    return tool


def build_server(targets: Targets | None = None) -> MCPServer:
    targets = targets or Targets()
    srv = MCPServer("axibridge", instructions=INSTRUCTIONS)
    tool = make_tool_decorator(srv, targets)
    for module in MODULES:
        module.register(tool, targets)
    return srv


def main() -> None:
    targets = Targets()
    atexit.register(targets.close)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(0))  # sys.exit runs atexit → sandbox stops
    build_server(targets).run("stdio")
