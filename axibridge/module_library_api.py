"""HTTP boundary for the project-independent module library."""
from html import escape
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .module_library import Kind, module_library_store
from .registry import get_effect, get_source

router = APIRouter(prefix="/module-library")


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


class CreatePreset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    module: str
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class UpdatePreset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    params: dict[str, Any] | None = None


class ResolvePreset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    module: str
    preset_id: str | None = None
    current_params: dict[str, Any] = Field(default_factory=dict)


class UpdatePreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starred: bool = False
    tags: list[str] = Field(default_factory=list)
    rating: int | None = Field(default=None, ge=1, le=5)


@router.get("")
def list_library():
    return _call(module_library_store.list)


@router.post("/presets")
def create_preset(body: CreatePreset):
    return _call(module_library_store.create, **body.model_dump())


@router.get("/presets/{preset_id}")
def preset_detail(preset_id: str):
    library = _call(module_library_store.list)
    try:
        return next(item for item in library["presets"] if item["id"] == preset_id)
    except StopIteration as exc:
        raise HTTPException(404, "Preset not found") from exc


@router.patch("/presets/{preset_id}")
def update_preset(preset_id: str, body: UpdatePreset):
    return _call(module_library_store.update, preset_id, **body.model_dump())


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: str):
    _call(module_library_store.delete, preset_id)
    return {"ok": True}


@router.post("/resolve")
def resolve_preset(body: ResolvePreset):
    params = _call(module_library_store.resolve, body.kind, body.module,
                   body.preset_id, body.current_params)
    return {"params": params}


@router.put("/preferences/{kind}/{module}")
def update_preference(kind: Kind, module: str, body: UpdatePreference):
    return _call(module_library_store.preference, kind, module,
                 **body.model_dump(exclude_unset=True))


@router.get("/modules/{kind}/{module}/thumbnail")
def module_thumbnail(kind: Kind, module: str):
    try:
        registered = get_source(module) if kind == "source" else get_effect(module)
    except KeyError as exc:
        raise HTTPException(404, str(exc).strip("'")) from exc
    headers = {"Cache-Control": "private, no-cache"}
    try:
        svg = module_library_store.thumbnail(kind, module)
    except (ValueError, OSError):
        # Rendering failure and queue saturation are expected while browsing:
        # identify the registered tool by name without inventing geometry.
        label = escape(registered.label)
        svg = ("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 240 80\">"
               "<rect width=\"240\" height=\"80\" fill=\"#f2f0e5\"/>"
               f"<text x=\"120\" y=\"42\" text-anchor=\"middle\" fill=\"#575653\" "
               f"font-family=\"system-ui,sans-serif\" font-size=\"13\">{label}</text></svg>")
        headers["X-Preview-Unavailable"] = "true"
    return Response(svg, media_type="image/svg+xml", headers=headers)
