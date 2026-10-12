"""Module discovery and the tuning loop. Previews never touch the project."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from PIL import Image as PILImage
from pydantic import Field

from .render import contact_sheet, fit_lines, png
from .targets import TargetName, Targets

KINDS = ("sources", "effects", "transforms")


def _modules(targets: Targets, target: TargetName) -> dict:
    return targets.client(target).get("/api/state")["modules"]


def _first_sentence(text: str | None) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text.split(". ")[0][:140]


def _error_tile(size: int) -> PILImage.Image:
    return PILImage.new("RGB", (size, size), "#FFE1D5")  # flexoki red-50


def register(tool, targets: Targets) -> None:
    @tool
    def modules(kind: Literal["sources", "effects", "transforms", "all"] = "all",
                query: str | None = None, target: TargetName = "live") -> str:
        """List generators ("sources"), effects and transforms as
        `id — label: summary`. `query` filters on id/label/description."""
        mods = _modules(targets, target)
        q = (query or "").lower()
        out = []
        for k in KINDS if kind == "all" else (kind,):
            rows = [m for m in mods.get(k, []) if not q or q in
                    f"{m['id']} {m.get('label', '')} {m.get('description', '')}".lower()]
            if rows:
                out.append(f"## {k}")
                out += [f"{m['id']} — {m.get('label', '')}: {_first_sentence(m.get('description'))}"
                        for m in rows]
        return "\n".join(out) or "no modules match"

    @tool
    def module_schema(module_id: str, target: TargetName = "live") -> str:
        """Full JSON Schema and defaults for one module's params."""
        mods = _modules(targets, target)
        for k in KINDS:
            for m in mods.get(k, []):
                if m["id"] == module_id:
                    return json.dumps({"id": m["id"], "kind": k, "label": m.get("label"),
                                       "description": m.get("description"),
                                       "schema": m.get("schema"),
                                       "defaults": m.get("defaults")}, indent=1)
        raise ToolError(f"no module {module_id!r} — call `modules` to list them")

    @tool
    def try_generator(module: str, param_sets: list[dict],
                      target: TargetName = "live",
                      tile: Annotated[int, Field(ge=100, le=800)] = 400) -> list:
        """Run a generator once per param set (each merged over its defaults by
        the server) and return ONE contact sheet, tiles numbered in order.
        Never touches the project. 1–16 sets."""
        if not 1 <= len(param_sets) <= 16:
            raise ToolError("give 1–16 param sets")
        c = targets.client(target)
        tiles, notes = [], []
        for i, params in enumerate(param_sets, 1):
            try:
                r = c.post("/api/generators/preview", {"module": module, "params": params})
            except ToolError as e:
                tiles.append((_error_tile(tile), f"{i}: error"))
                notes.append(f"{i}: error — {str(e)[:300]}")
                continue
            extra = " (decimated)" if r.get("decimated") else ""
            tiles.append((fit_lines(r["lines"], tile), f"{i}: {r['points']} pts{extra}"))
        if len(notes) == len(param_sets):
            raise ToolError(f"{module}: every param set failed\n" + "\n".join(notes))
        head = f"{module} — " + "; ".join(f"{i}={json.dumps(p)}" for i, p in enumerate(param_sets, 1))
        return ["\n".join([head, *notes]), png(contact_sheet(tiles))]

    @tool
    def try_effects(layer_id: str, chains: list[list[dict]],
                    target: TargetName = "live",
                    tile: Annotated[int, Field(ge=100, le=800)] = 400) -> list:
        """Preview whole effect stacks on an existing layer, one tile per chain.
        A chain is a list like [{"effect": "freehand", "params": {...}}]; an
        empty chain shows the bare layer. Never touches the project. 1–16."""
        if not 1 <= len(chains) <= 16:
            raise ToolError("give 1–16 chains")
        c = targets.client(target)
        tiles, notes = [], []
        for i, chain in enumerate(chains, 1):
            try:
                r = c.post(f"/api/layers/{layer_id}/effects/preview", {"effects": chain})
            except ToolError as e:
                tiles.append((_error_tile(tile), f"{i}: error"))
                notes.append(f"{i}: error — {str(e)[:300]}")
                continue
            label = " + ".join(s.get("effect", "?") for s in chain) or "bare"
            tiles.append((fit_lines(r["lines"], tile), f"{i}: {label}, {r['points']} pts"))
        if len(notes) == len(chains):
            raise ToolError(f"layer {layer_id}: every chain failed\n" + "\n".join(notes))
        return ["\n".join([f"layer {layer_id}", *notes]), png(contact_sheet(tiles))]
