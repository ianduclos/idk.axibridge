"""Composing through the normal API — every edit is one of Ian's undo steps."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .targets import TargetName, Targets

RecoveryAction = Literal["save", "recover", "discard"]


def _layer_line(layer: dict) -> str:
    src = layer.get("source", {})
    return f"{layer['id']} “{layer.get('name')}” ({src.get('type')}:{src.get('generator') or ''})"


def register(tool, targets: Targets) -> None:
    @tool
    def add_layer(module: str, params: dict[str, Any] | None = None,
                  name: str | None = None, pen_id: str | None = None,
                  target: TargetName = "live") -> str:
        """Add a generator layer (params merged over the module's defaults).
        Setting name/pen is a second edit, so ⌘Z takes two steps then."""
        c = targets.client(target)
        layer = c.post("/api/layers/generate", {"module": module, "params": params or {}})
        patch = {k: v for k, v in {"name": name, "pen_id": pen_id}.items() if v is not None}
        if patch:
            layer = c.patch(f"/api/layers/{layer['id']}", patch)
        return f"added {_layer_line(layer)}"

    @tool
    def edit_layer(layer_id: str, patch: dict[str, Any] | None = None,
                   params: dict[str, Any] | None = None,
                   target: TargetName = "live") -> str:
        """Change a layer. `patch` sets layer fields (name, visible, pen_id,
        transform {a,b,c,d,e,f}, effects [{effect, params}], occluder, …);
        `params` re-runs a generator layer with new params."""
        if not patch and not params:
            raise ToolError("nothing to change — pass `patch`, `params` or both")
        c = targets.client(target)
        layer = None
        if params:
            layer = c.post(f"/api/layers/{layer_id}/regenerate", {"params": params, "coalesce": False})
        if patch:
            layer = c.patch(f"/api/layers/{layer_id}", patch)
        return f"edited {_layer_line(layer)}"

    @tool
    def delete_layers(ids: list[str], cascade: bool = True,
                      target: TargetName = "live") -> str:
        """Delete layers in one undo step. cascade=True also removes tweens
        that reference them."""
        r = targets.client(target).post("/api/layers/delete", {"ids": ids, "cascade": cascade})
        return f"deleted {', '.join(r.get('deleted', ids))}"

    @tool
    def reorder_layers(ids: list[str], target: TargetName = "live") -> str:
        """Set the full layer order, bottom→top (the resolve order). Must list
        every current layer id exactly once."""
        r = targets.client(target).post("/api/layers/order", {"ids": ids})
        return "order (bottom→top): " + ", ".join(r["ids"])

    def _history(direction: str, steps: int, target: TargetName) -> str:
        c = targets.client(target)
        # whole literal paths, not a computed one: the freshness test finds
        # endpoints by scanning for their string literals
        path = "/api/undo" if direction == "undo" else "/api/redo"
        done = 0
        for _ in range(steps):
            try:
                c.post(path)
            except ToolError as e:
                if f"nothing to {direction}" in str(e):
                    return f"{'undid' if direction == 'undo' else 'redid'} {done}; nothing more to {direction}"
                raise
            done += 1
        return f"{'undid' if direction == 'undo' else 'redid'} {done}"

    @tool
    def undo(steps: Annotated[int, Field(ge=1, le=50)] = 1, target: TargetName = "live") -> str:
        """Step back through the shared undo history (Ian's ⌘Z history too)."""
        return _history("undo", steps, target)

    @tool
    def redo(steps: Annotated[int, Field(ge=1, le=50)] = 1, target: TargetName = "live") -> str:
        """Step forward again after undo."""
        return _history("redo", steps, target)

    @tool
    def project(action: Literal["status", "list", "new", "open"],
                name: str | None = None,
                recovery_action: RecoveryAction | None = None,
                target: TargetName = "live") -> str:
        """Project status, list saved projects, start a new one, or open one.
        If the open project has unsaved work, new/open fail with "unsaved work"
        — then pass recovery_action: "save" (save first), "recover" (keep a
        recovery copy) or "discard". On live, never "discard" unless Ian said so."""
        c = targets.client(target)
        if action == "status":
            p = c.get("/api/project")
            st = c.get("/api/state")
            return json.dumps({"name": p.get("name"), "dir": st.get("project_dir"),
                               "dirty": p.get("dirty"), "edit_rev": p.get("edit_rev"),
                               "recovery": c.get("/api/recovery")}, indent=1)
        if action == "list":
            return "\n".join(c.get("/api/projects")) or "no saved projects"
        if action == "new":
            c.post("/api/project/new", {"recovery_action": recovery_action})
            return "new empty project"
        if not name:
            raise ToolError("open needs `name` — `project(action='list')` shows them")
        p = c.post("/api/project/load", {"name": name, "recovery_action": recovery_action})
        return f"opened {name} ({len(p.get('layers', []))} layers)"

    @tool
    def save_project(name: str | None = None, target: TargetName = "live") -> str:
        """Save the open project to its folder (overwrites it on disk).
        `name` saves under a new name."""
        targets.client(target).post("/api/project/save", {"name": name})
        return f"saved {name or 'project'}"
