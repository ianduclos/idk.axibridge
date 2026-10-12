"""Looking: compact state now; canvas and UI images in later tasks."""

from __future__ import annotations

import json

from .targets import TargetName, Targets


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
