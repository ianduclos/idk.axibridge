"""The synthesis bench's scores (S4): ask a writer, recompose around locks, validate, keep.

Scores are whole JSON documents (docs/SYNTHESIS.md); none of these touches
the machine. Keep is one of Ian's undo steps; the rest change nothing in the
project (a score only becomes layers on keep)."""

from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError

from .targets import TargetName, Targets


def _brief(score: dict) -> str:
    layers = ", ".join(f"{L['id']}:{L['role']}" + (" (locked)" if L.get("lock") else "") for L in score.get("layers", []))
    rels = ", ".join(f"{R['id']}:{R['kind']}" for R in score.get("relations", [])[:24])
    return (f"seed {score.get('seed')} · {len(score.get('layers', []))} layers [{layers}] · "
            f"{len(score.get('relations', []))} relations [{rels}]")


def register(tool, targets: Targets) -> None:
    @tool
    def synthesis(action: Literal["catalogue", "start", "compose", "recompose", "lock", "unlock", "validate",
                                  "keep"],
                  score: dict[str, Any] | None = None, writer: str | None = None, gallery: str | None = None,
                  seed: int | None = None, params: dict[str, Any] | None = None,
                  ids: list[str] | None = None, locked_relations: list[str] | None = None,
                  full: bool = False, target: TargetName = "sandbox") -> str:
        """Synthesis scores (layers + relations one executor plays). `catalogue` lists relations,
        writers, gallery; `start` opens a gallery card (`gallery` e.g. "writer:listen", "study:leaf_miner");
        `compose` asks `writer` (listen | arch | ccolour) at `seed`; `recompose` rewrites `score` at `seed`
        around locked layers `ids` (+ `locked_relations`); `lock` / `unlock` layers `ids`; `validate`
        normalises; `keep` adds the score to the project as a group (one undo step). Returns a brief, or
        the whole score JSON with `full`. Preview with try_generator(module="synthesis", params={"score": …})."""
        c = targets.client(target)
        if action == "catalogue":
            cat = c.get("/api/synthesis")
            return json.dumps({"relations": [(r["id"], r["phase"]) for r in cat["relations"]],
                               "writers": [w["id"] for w in cat["writers"]],
                               "gallery": [g["id"] for g in cat["gallery"]], "limits": cat["limits"]}, indent=1)
        if action == "start":
            if not gallery:
                raise ToolError("start needs `gallery` (see action='catalogue')")
            out = c.post("/api/synthesis/start", {"gallery": gallery, "seed": seed, "params": params or {}})
        elif action == "compose":
            if not writer or seed is None:
                raise ToolError("compose needs `writer` and `seed`")
            out = c.post("/api/synthesis/compose", {"writer": writer, "seed": seed, "params": params or {}})
        else:
            if score is None:
                raise ToolError(f"{action} needs `score`")
            if action == "recompose":
                if seed is None:
                    raise ToolError("recompose needs `seed`")
                out = c.post("/api/synthesis/recompose", {"score": score, "seed": seed, "locked": ids or [],
                                                          "locked_relations": locked_relations or []})
            elif action == "lock":
                out = c.post("/api/synthesis/lock", {"score": score, "ids": ids or []})
            elif action == "unlock":
                out = c.post("/api/synthesis/unlock", {"score": score, "ids": ids or []})
            elif action == "validate":
                out = c.post("/api/synthesis/validate", {"score": score})
            else:
                r = c.post("/api/synthesis/keep", {"params": {"score": score}})
                return f"kept group {r['group']['id']} “{r['group']['name']}”: {len(r['layers'])} layers"
        s = out["score"]
        return json.dumps(s) if full else _brief(s)
