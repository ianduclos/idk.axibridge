"""Looking: compact state now; canvas and UI images in later tasks."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .render import png, render_layers
from .targets import TargetName, Targets
from .ui import UiStep, screenshot


def _source_label(source: dict) -> str:
    kind = source.get("type", "?")
    name = source.get("generator") or source.get("file") or ""
    return f"{kind}:{name}" if name else kind


def register(tool, targets: Targets) -> None:
    @tool
    def state(target: TargetName = "live") -> str:
        """Compact snapshot of a target: project (name, dir, edit_rev, dirty,
        view), layers bottom→top (id, name, source, pen, visible, effects,
        paths, points) and machine (backend, connected, job state, position).
        Call this first — /api/state itself is ~300 KB."""
        c = targets.client(target)
        project = c.get("/api/project")
        resolved = c.get("/api/compose/resolved")
        st = c.get("/api/state")
        stats = {l["id"]: l.get("stats") or {} for l in resolved["layers"]}
        layers = [{
            "id": l["id"],
            "name": l["name"],
            "source": _source_label(l["source"]),
            "pen": l.get("pen_id"),
            "visible": l.get("visible", True),
            "effects": [e.get("effect") for e in l.get("effects", [])],
            "paths": stats.get(l["id"], {}).get("paths"),
            "points": stats.get(l["id"], {}).get("points"),
        } for l in project["layers"]]
        m = st["machine"]
        return json.dumps({
            "target": target,
            "project": {"name": project.get("name"), "dir": st.get("project_dir"),
                        "edit_rev": project.get("edit_rev"), "dirty": project.get("dirty"),
                        "view": project.get("view")},
            "layers": layers,
            "machine": {"backend": m.get("backend"), "connected": m.get("connected"),
                        "job_state": m.get("job_state"), "position": m.get("position")},
        }, indent=1)

    @tool
    def see(target: TargetName = "live",
            layer_ids: list[str] | None = None,
            t: Annotated[float | None, Field(ge=0.0, le=1.0)] = None,
            travel: bool = False,
            size: Annotated[int, Field(ge=200, le=2400)] = 1200,
            orient: Literal["view", "machine"] = "view") -> list:
        """PNG of the resolved canvas — exactly what plotting consumes.
        `layer_ids` limits it to some layers; `t` scrubs the master timeline
        (tweens that follow it); `travel` overlays pen-up moves in red (from
        the stored-t plan); `orient="view"` matches Ian's screen (portrait is
        rotated, origin top-right), "machine" is the raw machine frame."""
        c = targets.client(target)
        resolved = c.get("/api/compose/resolved", t=t, stats="false")
        project = c.get("/api/project")
        if layer_ids is not None:
            known = {l["id"] for l in resolved["layers"]}
            unknown = [i for i in layer_ids if i not in known]
            if unknown:
                raise ToolError(f"no layer {', '.join(map(repr, unknown))} — "
                                "`state` lists the layer ids")
        layers = [l for l in resolved["layers"] if layer_ids is None or l["id"] in layer_ids]
        moves = None
        if travel:
            moves = [m["points"] for m in c.get("/api/plan")["job"]["moves"] if not m["pen_down"]]
        view = project.get("view", "landscape") if orient == "view" else "landscape"
        bed = (resolved["bed"]["width"], resolved["bed"]["height"])
        data = render_layers(layers, bed=bed, guide=project.get("guide"), travel=moves,
                             view=view, size=size)
        paths = sum(len(l["paths"]) for l in layers if l.get("visible", True))
        n = len(layers)
        caption = f"{n} layer{'s' if n != 1 else ''}, {paths} paths, {view}"
        return [caption, png(data)]

    @tool
    def see_ui(target: TargetName = "live",
               tab: Literal["compose", "assets", "plot", "pens", "settings"] | None = None,
               steps: list[UiStep] | None = None,
               width: Annotated[int, Field(ge=800, le=2560)] = 1440,
               height: Annotated[int, Field(ge=600, le=1600)] = 900) -> list:
        """Screenshot the app's UI in a headless browser, optionally after
        switching tab and running steps (click/fill/press/wait). This is a
        separate browser, not Ian's window — but clicks are real edits on the
        target, so dogfood on the sandbox."""
        c = targets.client(target)
        data = screenshot(c.base_url, tab, steps or [], width, height)
        return [f"{target} UI{f' — {tab} tab' if tab else ''}", png(data)]
