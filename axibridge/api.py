"""HTTP API. Commands are plain POSTs; live status flows out via SSE.

Handlers that touch the machine or run geometry are sync ``def`` — FastAPI
executes them in its thread pool, keeping the event loop free for SSE.
Errors become 409 (machine/state conflicts) or 400/404/422 (bad input).

The compose endpoints all read through ``session.resolved*`` — the single
resolve pipeline — so what this API serves the canvas is byte-for-byte what
the estimator times and the plotter draws.
"""

from __future__ import annotations

from pathlib import Path as FsPath
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from . import calibration, compose, project_io, svg_io
from .assets import asset_store
from .compose import PaperGuide, PlotOptions, Project
from .estimate import EstimatorConstants, MotionParams, plan_job
from .events import bus
from .machine import SoftLimits, manager
from .registry import describe_modules
from .session import session
from .stores import Pen, pen_library, settings_store

router = APIRouter(prefix="/api")


def _fail(exc: Exception, code: int = 409) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


def _consts() -> EstimatorConstants:
    return EstimatorConstants(**settings_store.settings.model_dump())


def _estimator_params(backend_id: str) -> MotionParams:
    raw = session.params_for(backend_id).model_dump()
    return MotionParams(**{k: v for k, v in raw.items() if k in MotionParams.model_fields})


# -- state / events ----------------------------------------------------------


@router.get("/state")
def get_state() -> dict[str, Any]:
    """Full snapshot — the frontend hydrates from this on (re)connect."""
    return {
        "machine": manager.status(),
        "backends": manager.describe_backends(),
        "modules": describe_modules(),
        "project": session.project.model_dump(),
        "pens": [p.model_dump() for p in pen_library.all()],
        "settings": settings_store.settings.model_dump(),
        "project_dir": session.project_dir,
        "assets": asset_store.info(),
        "bed": {"width": compose.BED_WIDTH, "height": compose.BED_HEIGHT},
        # schemas the frontend renders forms from (same mechanism as modules)
        "schemas": {
            "plot_options": PlotOptions.model_json_schema(),
            "pen": Pen.model_json_schema(),
            "settings": settings_store.settings.model_json_schema(),
        },
    }


@router.get("/events")
async def events() -> StreamingResponse:
    return StreamingResponse(
        bus.subscribe(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- connection / machine (the execution column — unchanged from v1) -----------


@router.get("/ports")
def list_ports() -> list[dict[str, str]]:
    from serial.tools import list_ports as lp

    return [{"device": p.device, "description": p.description or ""} for p in lp.comports()]


class SelectBackendBody(BaseModel):
    backend: str


@router.post("/backend/select")
def select_backend(body: SelectBackendBody) -> dict[str, Any]:
    try:
        manager.select_backend(body.backend)
    except (KeyError, RuntimeError) as e:
        raise _fail(e)
    if body.backend == "native" and not manager.active.connected:
        manager.auto_connect()  # machine present? grab it right away
    return manager.status()


class ConnectBody(BaseModel):
    port: str | None = None


@router.post("/connect")
def connect(body: ConnectBody) -> dict[str, Any]:
    try:
        return manager.connect(body.port)
    except Exception as e:
        raise _fail(e)


@router.post("/disconnect")
def disconnect() -> dict[str, Any]:
    try:
        manager.disconnect()
    except RuntimeError as e:
        raise _fail(e)
    return manager.status()


class PenBody(BaseModel):
    down: bool


@router.post("/machine/pen")
def machine_pen(body: PenBody) -> dict[str, Any]:
    try:
        manager.pen(body.down, session.params_for(manager.active_id))
    except (RuntimeError, NotImplementedError) as e:
        raise _fail(e)
    return manager.status()


class JogBody(BaseModel):
    dx: float = 0
    dy: float = 0


@router.post("/machine/jog")
def jog(body: JogBody) -> dict[str, Any]:
    try:
        pos = manager.jog(body.dx, body.dy, session.params_for(manager.active_id))
    except (RuntimeError, NotImplementedError) as e:
        raise _fail(e)
    return {"position": list(pos)}


class GotoBody(BaseModel):
    x: float
    y: float


@router.post("/machine/goto")
def goto(body: GotoBody) -> dict[str, Any]:
    try:
        pos = manager.goto(body.x, body.y, session.params_for(manager.active_id))
    except (RuntimeError, NotImplementedError) as e:
        raise _fail(e)
    return {"position": list(pos)}


class OriginBody(BaseModel):
    x: float = 0.0
    y: float = 0.0


@router.post("/machine/origin")
def set_origin(body: OriginBody | None = None) -> dict[str, Any]:
    """Declare the current carriage position to be design point (x, y) —
    (0,0) re-zeroes; the paper-guide corner binds the frame to the sheet."""
    b = body or OriginBody()
    try:
        manager.set_origin(b.x, b.y)
    except (RuntimeError, NotImplementedError) as e:
        raise _fail(e)
    return manager.status()


class RawBody(BaseModel):
    command: str
    expect_reply: bool = True


@router.post("/machine/raw")
def raw(body: RawBody) -> dict[str, str]:
    """The trapdoor endpoint. Bypasses planner and soft limits by design."""
    try:
        reply = manager.raw(body.command, body.expect_reply)
    except (RuntimeError, NotImplementedError) as e:
        raise _fail(e)
    return {"reply": reply}


@router.get("/limits")
def get_limits() -> SoftLimits:
    return manager.limits


@router.put("/limits")
def put_limits(limits: SoftLimits) -> SoftLimits:
    manager.limits = limits
    return limits


# -- layers --------------------------------------------------------------------


class GenerateBody(BaseModel):
    module: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/layers/generate")
def add_generated_layer(body: GenerateBody) -> dict[str, Any]:
    try:
        layer = session.add_generated_layer(body.module, body.params)
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)
    return layer.model_dump()


@router.post("/layers/upload")
async def upload_svg_layers(file: UploadFile, quantization_mm: float = 0.1) -> dict[str, Any]:
    text = (await file.read()).decode("utf-8", errors="replace")
    try:
        created = session.add_svg_layers(text, file.filename or "upload.svg", quantization_mm)
    except Exception as e:
        raise _fail(e, 400)
    return {"layers": [layer.model_dump() for layer in created]}


@router.post("/assets")
async def upload_asset(file: UploadFile) -> dict[str, Any]:
    """Image asset (PNG/JPEG depth map). Stored with the project; effects
    reference it by name."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    name = asset_store.put(file.filename or "asset.png", data)
    try:
        asset_store.grayscale(name)  # decode now: fail at upload, not at resolve
    except Exception as e:
        asset_store.replace_all({k: v for k, v in asset_store.all().items() if k != name})
        raise _fail(e, 400)
    return {"name": name, "assets": asset_store.info()}


@router.get("/assets")
def list_assets() -> dict[str, Any]:
    return {"assets": asset_store.info()}


@router.get("/assets/{name}")
def get_asset(name: str) -> Response:
    """Raw image bytes — the canvas's show-map overlay reads this."""
    data = asset_store.get(name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"no asset named {name!r}")
    media = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    return Response(content=data, media_type=media)


@router.patch("/layers/{layer_id}")
def patch_layer(layer_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    try:
        return session.update_layer(layer_id, patch).model_dump()
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 422)


class RegenerateBody(BaseModel):
    params: dict[str, Any] | None = None


@router.post("/layers/{layer_id}/regenerate")
def regenerate_layer(layer_id: str, body: RegenerateBody) -> dict[str, Any]:
    try:
        return session.regenerate_layer(layer_id, body.params).model_dump()
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)


@router.delete("/layers/{layer_id}")
def delete_layer(layer_id: str) -> dict[str, str]:
    try:
        session.delete_layer(layer_id)
    except KeyError as e:
        raise _fail(e, 404)
    return {"deleted": layer_id}


class DeleteLayersBody(BaseModel):
    ids: list[str]


@router.post("/layers/delete")
def delete_layers(body: DeleteLayersBody) -> dict[str, Any]:
    """Bulk delete (one undo step) — what Backspace on a multi-selection sends."""
    try:
        session.delete_layers(body.ids)
    except KeyError as e:
        raise _fail(e, 404)
    return {"deleted": body.ids}


@router.post("/layers/{layer_id}/consolidate")
def consolidate_layer(layer_id: str) -> dict[str, Any]:
    """Bake the layer's transform + effect stack into its source geometry."""
    try:
        return session.consolidate_effects(layer_id).model_dump()
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)


@router.post("/undo")
def undo() -> dict[str, Any]:
    if not session.undo():
        raise HTTPException(status_code=409, detail="nothing to undo")
    return session.project.model_dump()


class OrderBody(BaseModel):
    ids: list[str]


@router.post("/layers/order")
def reorder_layers(body: OrderBody) -> dict[str, Any]:
    try:
        session.reorder_layers(body.ids)
    except ValueError as e:
        raise _fail(e, 422)
    return {"ids": [l.id for l in session.project.layers]}


# -- compose: the single source of truth ------------------------------------------


@router.get("/compose/resolved")
def get_resolved() -> dict[str, Any]:
    """Per-layer RESOLVED geometry (post transform+effects+occlusion) plus
    per-layer stats and time estimates. This is what the canvas renders —
    identical to what plotting consumes."""
    try:
        resolved = session.resolved()
    except Exception as e:
        raise _fail(e, 400)
    pens = session.pens()
    params = _estimator_params(manager.active_id)
    consts = _consts()
    layers_out = []
    for layer in session.project.layers:
        paths = resolved.get(layer.id, []) if layer.visible else []
        pen = pens.get(layer.pen_id or "")
        pen_down = sum(p.length() for p in paths)
        est = 0.0
        if paths:
            doc = compose.flatten_to_document(
                session.project, {layer.id: paths}, pens, target=layer.id
            )
            est = plan_job(doc, params, consts=consts).total_duration
        layers_out.append({
            "id": layer.id,
            "name": layer.name,
            "visible": layer.visible,
            "pen_id": layer.pen_id,
            "color": pen.color if pen else compose.INK,
            "line_diameter_mm": pen.line_diameter_mm if pen else compose.DEFAULT_LINE_DIAMETER_MM,
            "opacity": pen.opacity if pen else 1.0,
            "occluder": layer.occluder,
            "receives_occlusion": layer.receives_occlusion,
            "paths": [{"points": p.points, "filled": p.filled} for p in paths],
            "stats": {
                "paths": len(paths),
                "points": sum(len(p.points) for p in paths),
                "pen_down_distance": pen_down,
                "est_s": est,
            },
        })
    return {"layers": layers_out, "bed": {"width": compose.BED_WIDTH, "height": compose.BED_HEIGHT}}


@router.get("/plan")
def get_plan(target: str = "all") -> dict[str, Any]:
    """Planned job for a plot pass — explicit travel moves + timing, computed
    on the SAME plot document the backend will receive (pen compensation and
    plot-pass optimisation included)."""
    try:
        doc = session.plot_document(target)
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)
    job = plan_job(doc, _estimator_params(manager.active_id), consts=_consts())
    return {
        "target": target,
        "job": job.model_dump(),
        "warnings": manager.check_envelope(doc),
        "estimator_note": "estimate only — backends do their own planning",
    }


@router.get("/doc/{target}/svg")
def download_svg(target: str) -> Response:
    try:
        doc = session.resolved_document(target)
    except KeyError as e:
        raise _fail(e, 404)
    return Response(content=svg_io.doc_to_svg(doc), media_type="image/svg+xml")


# -- plot control -------------------------------------------------------------------


class PlotStartBody(BaseModel):
    target: str = "all"  # "all" or a layer id — the manual multi-pen selector


@router.post("/plot/start")
def plot_start(body: PlotStartBody) -> dict[str, Any]:
    try:
        doc = session.plot_document(body.target)
        if not any(layer.paths for layer in doc.layers):
            raise RuntimeError("nothing to plot (no resolved geometry in target)")
        params = session.effective_params(manager.active_id, body.target)
        manager.start_plot(doc, params)
    except (KeyError, RuntimeError) as e:
        raise _fail(e)
    return manager.status()


@router.post("/plot/pause")
def plot_pause() -> dict[str, Any]:
    try:
        manager.pause()
    except RuntimeError as e:
        raise _fail(e)
    return manager.status()


@router.post("/plot/resume")
def plot_resume() -> dict[str, Any]:
    try:
        manager.resume()
    except RuntimeError as e:
        raise _fail(e)
    return manager.status()


@router.post("/plot/stop")
def plot_stop() -> dict[str, Any]:
    manager.stop()
    return manager.status()


# -- backend params (stored in the project) -------------------------------------------


@router.get("/params/{backend_id}")
def get_params(backend_id: str) -> dict[str, Any]:
    if backend_id not in manager.backends:
        raise HTTPException(404, f"unknown backend {backend_id!r}")
    return session.params_for(backend_id).model_dump()


@router.put("/params/{backend_id}")
def put_params(backend_id: str, values: dict[str, Any]) -> dict[str, Any]:
    if backend_id not in manager.backends:
        raise HTTPException(404, f"unknown backend {backend_id!r}")
    try:
        return session.set_params(backend_id, values)
    except Exception as e:
        raise _fail(e, 422)


# -- pens ----------------------------------------------------------------------------


@router.get("/pens")
def get_pens() -> list[Pen]:
    return pen_library.all()


@router.post("/pens")
def upsert_pen(pen: Pen) -> Pen:
    saved = pen_library.upsert(pen)
    if saved.id in session.project.pens_used:
        session.project.pens_used[saved.id] = saved  # keep snapshot fresh
    return saved


@router.delete("/pens/{pen_id}")
def delete_pen(pen_id: str) -> dict[str, str]:
    pen_library.delete(pen_id)
    return {"deleted": pen_id}


# -- settings & calibration --------------------------------------------------------------


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    return settings_store.settings.model_dump()


@router.put("/settings")
def put_settings(values: dict[str, Any]) -> dict[str, Any]:
    try:
        return settings_store.update(values).model_dump()
    except Exception as e:
        raise _fail(e, 422)


@router.post("/calibration/holder/mark")
def plot_calibration_mark() -> dict[str, Any]:
    """Step 1/2 of the holder wizard: plot the registration crosshair with
    the currently loaded pen (run once per pen)."""
    try:
        manager.start_plot(calibration.registration_mark(), session.params_for(manager.active_id))
    except RuntimeError as e:
        raise _fail(e)
    return manager.status()


class HolderComputeBody(BaseModel):
    diameter_1: float = Field(gt=0, description="Barrel ⌀ of the first pen (mm)")
    diameter_2: float = Field(gt=0, description="Barrel ⌀ of the second pen (mm)")
    dx_mm: float = Field(description="Mark-2 minus mark-1 displacement, machine X (mm)")
    dy_mm: float = Field(description="Mark-2 minus mark-1 displacement, machine Y (mm)")


@router.post("/calibration/holder/compute")
def compute_holder(body: HolderComputeBody) -> dict[str, Any]:
    try:
        cal = calibration.compute_holder_vector(
            body.diameter_1, body.diameter_2, body.dx_mm, body.dy_mm
        )
    except ValueError as e:
        raise _fail(e, 422)
    settings_store.update({"holder_calibration": cal.model_dump()})
    return cal.model_dump()


class TestStrokeBody(BaseModel):
    x: float = 20
    y: float = 20
    length: float = Field(default=20, ge=2, le=100)


@router.post("/calibration/teststroke")
def plot_test_stroke(body: TestStrokeBody) -> dict[str, Any]:
    """Pen-height test: one short stroke at the current live heights."""
    try:
        manager.start_plot(
            calibration.test_stroke(body.x, body.y, body.length),
            session.params_for(manager.active_id),
        )
    except RuntimeError as e:
        raise _fail(e)
    return manager.status()


# -- project ------------------------------------------------------------------------------


@router.get("/project")
def get_project() -> Project:
    return session.project


class ProjectPatch(BaseModel):
    name: str | None = None
    guide: PaperGuide | None = None
    view: str | None = None
    plot_options: PlotOptions | None = None


@router.put("/project")
def patch_project(body: ProjectPatch) -> Project:
    p = session.project
    if body.name is not None:
        p.name = body.name
    if body.guide is not None:
        p.guide = body.guide
    if body.view in ("portrait", "landscape"):
        p.view = body.view
    if body.plot_options is not None:
        p.plot_options = body.plot_options
    return p


@router.post("/project/new")
def new_project() -> Project:
    session.project = Project()
    session.project_dir = None
    session.source_geometry.clear()
    session.svg_files.clear()
    session._shaped_cache.clear()
    session.clear_history()
    asset_store.replace_all({})
    return session.project


@router.get("/projects")
def list_projects() -> list[str]:
    root = settings_store.settings.projects_dir()
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if (d / "project.json").exists())


class SaveBody(BaseModel):
    name: str | None = None


@router.post("/project/save")
def save_project(body: SaveBody) -> dict[str, str]:
    if body.name:
        session.project.name = body.name
    name = project_io.safe_name(session.project.name)
    target = settings_store.settings.projects_dir() / name
    try:
        project_io.save_project(
            session.project, session.source_geometry, session.svg_files, target,
            assets=asset_store.all(),
        )
    except OSError as e:
        raise _fail(e, 400)
    session.project_dir = str(target)
    return {"saved": str(target)}


class LoadBody(BaseModel):
    name: str


@router.post("/project/load")
def load_project(body: LoadBody) -> Project:
    target = settings_store.settings.projects_dir() / project_io.safe_name(body.name)
    try:
        project, geometry, svg_files, assets = project_io.load_project(target)
    except FileNotFoundError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)
    session.project = project
    session.source_geometry = geometry
    session.svg_files = svg_files
    session.project_dir = str(target)
    session._shaped_cache.clear()
    session.clear_history()
    asset_store.replace_all(assets)
    return project


@router.get("/project/export.zip")
def export_project() -> Response:
    name = project_io.safe_name(session.project.name)
    target = settings_store.settings.projects_dir() / name
    project_io.save_project(
        session.project, session.source_geometry, session.svg_files, target,
        assets=asset_store.all(),
    )
    session.project_dir = str(target)
    data = project_io.export_zip(target)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )


@router.post("/project/import")
async def import_project(file: UploadFile) -> Project:
    data = await file.read()
    name = FsPath(file.filename or "imported").stem
    try:
        target = project_io.import_zip(data, settings_store.settings.projects_dir(), name)
        project, geometry, svg_files, assets = project_io.load_project(target)
    except (ValueError, FileExistsError) as e:
        raise _fail(e, 400)
    session.project = project
    session.source_geometry = geometry
    session.svg_files = svg_files
    session.project_dir = str(target)
    session._shaped_cache.clear()
    session.clear_history()
    asset_store.replace_all(assets)
    return project
