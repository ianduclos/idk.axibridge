"""HTTP API. Commands are plain POSTs; live status flows out via SSE.

Handlers that touch the machine or run geometry are sync ``def`` — FastAPI
executes them in its thread pool, keeping the event loop free for SSE.
Errors become 409 (machine/state conflicts) or 400/404/422 (bad input).

The compose endpoints all read through ``session.resolved*`` — the single
resolve pipeline — so what this API serves the canvas is byte-for-byte what
the estimator times and the plotter draws.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path as FsPath
from typing import Any, Literal

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from . import calibration, compose, depth_pro, logbuf, project_io, svg_io
from .assets import SEQUENCE_FRAME_RE, asset_store, safe_asset_name
from .compose import PaperGuide, PlotOptions, Project
from .estimate import EstimatorConstants, MotionParams, plan_job
from .events import bus
from .machine import SoftLimits, manager
from .model import Layer as DocLayer, PathDocument
from .registry import EffectContext, describe_modules, get_effect, get_source, progress_scope
from .scraps import scrap_library
from .session import session
from .stores import Pen, pen_library, settings_store
from .tween import TweenParams

router = APIRouter(prefix="/api")


def _fail(exc: Exception, code: int = 409) -> HTTPException:
    return HTTPException(status_code=code, detail=str(exc))


def _project_payload() -> dict[str, Any]:
    return session.project.model_dump(exclude={"staging": {"__all__": {"snapshot"}}})


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
        "project": _project_payload(),
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
            "tween": TweenParams.model_json_schema(),
        },
    }


@router.post("/server/restart")
def restart_server() -> dict[str, str]:
    """Re-exec the server process in place: same interpreter, same CLI args,
    same environment — picks up code changes without touching the launcher.
    The open project lives in memory only, so unsaved changes are lost (the
    UI warns). Python fds are close-on-exec (PEP 446): the serial port and
    the listening socket release across the exec, and uvicorn's SO_REUSEADDR
    lets the new process rebind immediately."""
    if manager.job_state != "idle":
        raise HTTPException(status_code=409, detail="stop the current job before restarting")

    def _restart() -> None:
        time.sleep(0.5)  # let this response reach the browser first
        try:
            manager.shutdown()  # pen up, release the port politely
        except Exception:
            pass
        os.execv(sys.executable, [sys.executable, "-m", "axibridge", *sys.argv[1:]])

    threading.Thread(target=_restart, name="axibridge-restart", daemon=True).start()
    return {"restarting": "now"}


@router.get("/logs")
def get_logs(after: int = Query(default=0, ge=0)) -> dict[str, Any]:
    """Server log ring (last ~500 records) — the Settings tab's log panel;
    the app-shell window has no terminal. ``after`` is the last-seen entry id
    (cheap incremental polling)."""
    return {"entries": logbuf.entries(after)}


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
    settings_store.update({"soft_limits": limits.model_dump()})  # survives restarts
    return limits


# -- layers --------------------------------------------------------------------


class GenerateBody(BaseModel):
    module: str
    params: dict[str, Any] = Field(default_factory=dict)


def _gen_progress_sink() -> Any:
    """SSE sink for report_progress: the generate request itself blocks until
    done (the button awaits it), so progress is broadcast-only UI feed.
    Throttled here, not in the modules — they may call per inner-loop row."""
    last = {"t": 0.0, "frac": -1.0, "msg": ""}

    def sink(frac: float, msg: str = "") -> None:
        now = time.monotonic()
        if msg == last["msg"] and now - last["t"] < 0.1 and frac - last["frac"] < 0.02:
            return
        last.update(t=now, frac=frac, msg=msg)
        bus.emit({"type": "gen", "frac": round(min(max(frac, 0.0), 1.0), 3), "msg": msg})

    return sink


#: live-preview responses cap their point count; the wire and the canvas both
#: stay light, and the real layer (created on "Convert to layer") is exact.
_PREVIEW_MAX_PTS = 60_000


@router.post("/generators/preview")
def preview_generator(body: GenerateBody) -> dict[str, Any]:
    """Run a generator WITHOUT touching the project: no layer, no undo
    checkpoint, no lock — safe to call on every (debounced) slider move.
    Feeds the dashed preview overlay; progress streams like a real generate."""
    try:
        src = get_source(body.module)
    except KeyError as e:
        raise _fail(e, 404)
    try:
        with progress_scope(_gen_progress_sink()):
            doc = src.generate(src.Params(**body.params))
    except Exception as e:
        raise _fail(e, 400)
    paths = [p for layer in doc.layers for p in layer.paths]
    return {**_preview_payload(paths), "width": doc.width, "height": doc.height}


def _preview_payload(paths: list[Any]) -> dict[str, Any]:
    lines = [[(round(x, 2), round(y, 2)) for x, y in p.points] for p in paths]
    total = sum(len(line) for line in lines)
    stride = -(-total // _PREVIEW_MAX_PTS)  # ceil
    if stride > 1:
        lines = [
            line[::stride] + (line[-1:] if (len(line) - 1) % stride else [])
            for line in lines
        ]
    return {"lines": lines, "points": total, "decimated": stride > 1}


class EffectsPreviewBody(BaseModel):
    effects: list[dict[str, Any]]


@router.post("/layers/{layer_id}/effects/preview")
def preview_layer_effects(layer_id: str, body: EffectsPreviewBody) -> dict[str, Any]:
    """Shape one layer with a candidate effect stack, read-only — the live
    preview for effect-param drags. Output is paper-space (post transform +
    effects, pre occlusion), so the overlay needs no client transform."""
    try:
        with progress_scope(_gen_progress_sink()):
            paths = session.preview_layer_effects(layer_id, body.effects)
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)
    return _preview_payload(paths)


@router.post("/layers/generate")
def add_generated_layer(body: GenerateBody) -> dict[str, Any]:
    try:
        with progress_scope(_gen_progress_sink()):
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


class DepthProAssetBody(BaseModel):
    image: str = Field(..., min_length=1)
    frame: float = Field(default=0.0, ge=0.0, le=1.0)
    near_white: bool = True


@router.get("/assets/depth-pro/status")
def depth_pro_asset_status() -> dict[str, Any]:
    return depth_pro.status()


@router.post("/assets/depth-pro")
def create_depth_pro_asset(body: DepthProAssetBody) -> dict[str, Any]:
    source = asset_store.resolve_frame(body.image, body.frame)
    data = asset_store.get(source)
    if data is None:
        raise HTTPException(status_code=404, detail=f"no asset named {body.image!r}")
    name = depth_pro.depth_asset_name(body.image, body.frame)
    stored = name
    before = asset_store.all()
    try:
        png = depth_pro.depth_png_from_image(data, source, near_white=body.near_white)
        stored = asset_store.put(name, png)
        asset_store.grayscale(stored)  # validate bytes before handing it to generators
    except depth_pro.DepthProUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        asset_store.replace_all(before)
        raise _fail(e, 400)
    return {
        "name": stored,
        "source": body.image,
        "frame": body.frame,
        "assets": asset_store.info(),
    }


#: video containers the sequence importer decodes (single-file uploads);
#: multiple files are always treated as an ordered image sequence.
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
_MAX_SEQUENCE_FRAMES = 240


def _even_indices(total: int, n: int) -> list[int]:
    """``n`` indices spread evenly across ``range(total)``, both ends inclusive.
    Fewer than ``n`` available -> take them all; ``n<=1`` -> just the first."""
    if total <= 0:
        return []
    if n >= total:
        return list(range(total))
    if n <= 1:
        return [0]
    return [round(i * (total - 1) / (n - 1)) for i in range(n)]


def _select_indices(
    total: int, frames: int | None, start: int, every: int | None,
    max_frames: int | None = None,
) -> list[int]:
    """Which source indices survive the import controls (shared by the video
    and multi-image paths). Drop the first ``start`` items; ``every`` picks
    every Nth of the remainder (capped at ``frames`` when set), otherwise
    ``frames`` are spread evenly across the remainder. If ``frames`` is omitted,
    every source frame is kept up to the global sequence cap.

    ``total == 1`` (a single-image "sequence") passes through untouched; the
    "fewer than 2" guard only fires when the controls drop a genuinely
    multi-frame source below two frames."""
    if total > 1 and total - start < 2:
        raise HTTPException(status_code=400, detail="start leaves fewer than 2 frames")
    start = min(start, max(total - 1, 0))  # a lone remaining frame still resolves
    if every is not None:
        idxs = list(range(start, total, every))
        idxs = idxs[:frames] if frames is not None else idxs
    else:
        n = frames if frames is not None else total - start
        idxs = [start + i for i in _even_indices(total - start, n)]
    cap = _MAX_SEQUENCE_FRAMES if max_frames is None else max_frames
    if frames is None and cap is not None and len(idxs) > cap:
        idxs = [idxs[i] for i in _even_indices(len(idxs), cap)]
    return idxs


def _reencode_jpeg(img: Any) -> bytes:
    """Downscale a PIL image to <=1024 px on its long edge and re-encode as
    JPEG quality 85 (sequences hold many frames — keep each one light; depth /
    grayscale sampling doesn't miss the discarded alpha or chroma)."""
    from PIL import Image

    w, h = img.size
    long_edge = max(w, h)
    if long_edge > 1024:
        s = 1024 / long_edge
        img = img.resize((max(round(w * s), 1), max(round(h * s), 1)), Image.LANCZOS)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _extract_video_frames(
    data: bytes, suffix: str, frames: int | None, start: int, every: int | None,
    sink: Any = None,
) -> list[bytes]:
    """Decode the selected frames (see :func:`_select_indices`) to JPEG bytes,
    applying selection BEFORE re-encoding so dropped frames are never encoded.
    imageio + imageio-ffmpeg, imported lazily to keep server start fast; ffmpeg
    reads from a real path, so the upload is spooled to a temp file first.

    ``sink`` (the SSE progress sink) reports the decode as an asymptotic 0..0.5
    (total frame count is unknown mid-stream) and the re-encode as 0.5..1.0."""
    import imageio.v3 as iio  # lazy: pulls in the bundled static ffmpeg
    from PIL import Image

    def _report(frac: float, msg: str) -> None:
        if sink is not None:
            sink(frac, msg)

    with tempfile.NamedTemporaryFile(suffix=suffix or ".mp4", delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        # tiny clips: read every frame, then subsample. (Large videos would be
        # heavy here — acceptable for hand-authored sequence sources.)
        decoded: list[Any] = []
        for i, frame in enumerate(iio.imiter(path, plugin="FFMPEG")):
            decoded.append(frame)
            if i % 5 == 0:  # total unknown mid-stream: asymptotic fraction
                _report(min(0.5, i / (i + 40.0)), f"decoding video · {i} frames")
        if not decoded:
            raise ValueError("no frames decoded from video")
        idxs = _select_indices(len(decoded), frames, start, every)
        n = len(idxs)
        out: list[bytes] = []
        for i, idx in enumerate(idxs):
            out.append(_reencode_jpeg(Image.fromarray(decoded[idx])))
            _report(0.5 + 0.5 * (i + 1) / n, f"encoding frame {i + 1}/{n}")
        return out
    finally:
        os.unlink(path)


@router.post("/assets/sequence")
async def upload_sequence(
    files: list[UploadFile],
    frames: int | None = Form(default=None, ge=1, le=_MAX_SEQUENCE_FRAMES),
    start: int = Form(default=0, ge=0, le=100000),
    every: int | None = Form(default=None, ge=1, le=1000),
) -> dict[str, Any]:
    """Import a frame sequence: EITHER several image files (ordered by filename)
    OR one video file. ``frames`` is an optional max frame count (bound 1..240);
    when omitted, every source frame is imported up to the sequence cap.
    ``start`` drops the first N source frames; ``every`` takes every Nth of the
    remainder. Frames are stored as plain assets ``<stem>#0000.jpg`` …; image
    consumers pick one via a normalized ``frame`` param. Returns the ``<stem>#``
    prefix + frame count."""
    from PIL import Image, ImageOps  # lazy, like the single-asset upload probe

    if not files:
        raise HTTPException(status_code=400, detail="no files")
    sink = _gen_progress_sink()  # import progress rides the same SSE feed
    first = files[0]
    ext = FsPath(first.filename or "clip").suffix.lower()
    # name the sequence from the first upload's stem, stripping a trailing frame
    # number ("frame_0001" -> "frame") so the prefix reads cleanly; keep the
    # whole stem if stripping would empty it (e.g. a purely numeric name).
    raw_stem = FsPath(first.filename or "clip").stem
    base = raw_stem.rstrip("0123456789").rstrip("-_. ") or raw_stem
    stem = safe_asset_name(base) or "clip"

    if len(files) == 1 and ext in _VIDEO_EXTS:
        try:
            jpegs = _extract_video_frames(await first.read(), ext, frames, start, every, sink)
        except HTTPException:
            raise  # a selection error (e.g. start leaves fewer than 2 frames)
        except Exception as e:
            raise _fail(e, 400)
    else:
        blobs = [b for f in sorted(files, key=lambda f: f.filename or "")
                 if (b := await f.read())]
        if not blobs:
            raise HTTPException(status_code=400, detail="no image data")
        # bound the count exactly like the video path (1..240) before selecting
        n = min(_MAX_SEQUENCE_FRAMES, frames) if frames else frames
        blobs = [blobs[i] for i in _select_indices(len(blobs), n, start, every)]
        try:
            jpegs = []
            total = len(blobs)
            for i, b in enumerate(blobs):
                jpegs.append(
                    _reencode_jpeg(ImageOps.exif_transpose(Image.open(io.BytesIO(b)))))
                sink((i + 1) / total, f"frame {i + 1}/{total}")
        except Exception as e:
            raise _fail(e, 400)

    prefix = f"{stem}#"
    # collision: a re-import replaces the sequence wholesale — drop the old
    # frames of this prefix first so a shorter clip leaves no stale tail frames.
    kept = {k: v for k, v in asset_store.all().items()
            if not (k.startswith(prefix) and SEQUENCE_FRAME_RE.match(k))}
    asset_store.replace_all(kept)
    for i, jpg in enumerate(jpegs):
        asset_store.put(f"{prefix}{i:04d}.jpg", jpg)
    try:
        asset_store.grayscale(f"{prefix}0000.jpg")  # decode now: fail here, not at resolve
    except Exception as e:
        asset_store.replace_all(kept)
        raise _fail(e, 400)
    sink(1.0, "")  # done — clears the progress bar
    return {"name": prefix, "frames": len(jpegs), "assets": asset_store.info()}


@router.get("/assets")
def list_assets() -> dict[str, Any]:
    return {"assets": asset_store.info()}


@router.get("/assets/{name}")
def get_asset(
    name: str, frame: float | None = Query(default=None, ge=0.0, le=1.0)
) -> Response:
    """Raw image bytes — the canvas's show-map overlay reads this. For a
    sequence prefix, ``frame`` (0..1) picks the frame the overlay should show
    (the same mapping the generators use); without it a prefix serves its
    first frame."""
    if frame is not None:
        name = asset_store.resolve_frame(name, frame)
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
        with progress_scope(_gen_progress_sink()):
            return session.regenerate_layer(layer_id, body.params).model_dump()
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)


@router.delete("/layers/{layer_id}")
def delete_layer(layer_id: str) -> dict[str, Any]:
    """Cascade-delete a layer (default): a tween goes with its keyframes, and
    animate-created keyframes go with their tween. ``deleted`` lists every id
    that was actually removed (in z-order)."""
    try:
        deleted = session.delete_layer(layer_id)
    except KeyError as e:
        raise _fail(e, 404)
    return {"deleted": deleted}


class DeleteLayersBody(BaseModel):
    ids: list[str]
    cascade: bool = True


@router.post("/layers/delete")
def delete_layers(body: DeleteLayersBody) -> dict[str, Any]:
    """Bulk delete (one undo step) — what Backspace on a multi-selection sends.
    Cascades by default (see :func:`delete_layer`); ``cascade=false`` refuses if
    a surviving tween still references a doomed layer. ``deleted`` lists every
    removed id in z-order."""
    try:
        deleted = session.delete_layers(body.ids, cascade=body.cascade)
    except KeyError as e:
        raise _fail(e, 404)
    except RuntimeError as e:
        raise _fail(e, 409)
    return {"deleted": deleted}


class TweenBody(BaseModel):
    a: str
    b: str


@router.post("/layers/tween")
def create_tween(body: TweenBody) -> dict[str, Any]:
    """Interpolation layer between two compatible layers."""
    try:
        return session.create_tween_layer(body.a, body.b).model_dump()
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)


@router.put("/layers/{layer_id}/tween")
def put_tween_params(layer_id: str, values: dict[str, Any]) -> dict[str, Any]:
    try:
        return session.set_tween_params(layer_id, values).model_dump()
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 422)


@router.post("/layers/{layer_id}/explode")
def explode_tween(layer_id: str) -> dict[str, Any]:
    """Split a tween's sweep into individual baked layers."""
    try:
        return {"layers": [l.model_dump() for l in session.explode_tween(layer_id)]}
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)


@router.post("/layers/{layer_id}/duplicate")
def duplicate_layer(layer_id: str) -> dict[str, Any]:
    try:
        return session.duplicate_layer(layer_id).model_dump()
    except KeyError as e:
        raise _fail(e, 404)


@router.post("/layers/{layer_id}/animate")
def animate_layer(layer_id: str) -> dict[str, Any]:
    """One-click: turn a layer into a keyframed (A/B) tween animation."""
    try:
        return session.animate_layer(layer_id).model_dump()
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e)


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
    return _project_payload()


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
def get_resolved(
    t: float | None = Query(default=None, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """Per-layer RESOLVED geometry (post transform+effects+occlusion) plus
    per-layer stats and time estimates. This is what the canvas renders —
    identical to what plotting consumes.

    ``t`` (0..1) is the ephemeral master-timeline scrub: it drives every tween
    with ``follow_master`` set, live, without touching the stored project.
    Out-of-range values 422 (FastAPI bounds). Stats/estimates below reflect the
    scrubbed geometry because they read from the same ``resolved`` map."""
    try:
        resolved = session.resolved(master_t=t)
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
        # region layers resolve to nothing (never plotted) but the canvas
        # still needs their silhouette to select/drag — display-only paths
        display = paths
        if layer.region and layer.visible:
            display = compose.transform_paths(
                session.source_geometry.get(layer.id, []), layer.transform)
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
            "region": layer.region,
            "paths": [{"points": p.points, "filled": p.filled} for p in display],
            "stats": {
                "paths": len(paths),
                "points": sum(len(p.points) for p in paths),
                "pen_down_distance": pen_down,
                "est_s": est,
            },
        })
    return {"layers": layers_out, "bed": {"width": compose.BED_WIDTH, "height": compose.BED_HEIGHT}}


@router.get("/plan")
def get_plan(
    target: str = "all",
    sheet: str | None = Query(default=None),
    staged: str | None = Query(default=None),
) -> dict[str, Any]:
    """Planned job for a plot pass — explicit travel moves + timing, computed
    on the SAME plot document the backend will receive (pen compensation and
    plot-pass optimisation included). ``sheet`` (a JSON-encoded SheetSpec) plans
    the grid-sheet document for one page instead, so the canvas plan overlay
    previews the real page layout and the estimate reflects the shrunk cells."""
    try:
        if staged is not None:
            doc = session._optimize(_staged_document(StagedSpec.model_validate_json(staged)))
        elif sheet is not None:
            doc = session._optimize(_sheet_document(SheetSpec.model_validate_json(sheet)))
        else:
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
        doc = session.cropped(session.resolved_document(target))
    except KeyError as e:
        raise _fail(e, 404)
    name = project_io.safe_name(session.project.name)
    return Response(
        content=svg_io.doc_to_svg(doc),
        media_type="image/svg+xml",
        headers={"Content-Disposition": f'attachment; filename="{name}.svg"'},
    )


# -- animation: frame-sequence outputs ---------------------------------------------


@router.get("/animation/export.zip")
def export_animation_frames(
    frames: int = Query(ge=2, le=240),
    t_from: float = Query(default=0.0, ge=0.0, le=1.0),
    t_to: float = Query(default=1.0, ge=0.0, le=1.0),
    cols: int | None = Query(default=None, ge=1, le=12),
    rows: int | None = Query(default=None, ge=1, le=12),
    margin_mm: float = Query(default=5.0, ge=0.0, le=30.0),
    framing: Literal["center", "fixed"] = Query(default="center"),
    marks: bool = Query(default=False),
) -> Response:
    """SVG-sequence export: samples the master timeline ``frames`` times over
    [t_from, t_to] through the SAME resolve path the canvas and plotter use.

    Default (no cols/rows): one ``frame_NNNN.svg`` per sample. When BOTH
    ``cols`` and ``rows`` are given: grid-sheet mode instead — one
    ``sheet_NN.svg`` per physical sheet, every pen group a colored SVG layer
    (shared scale across sheets). 400 if the export resolves to no geometry."""
    buf = io.BytesIO()
    any_geometry = False
    grid = cols is not None and rows is not None
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if grid:
            n_pages = session.sheet_pages(frames, cols, rows)
            for page in range(n_pages):
                try:
                    doc = session.sheet_document(
                        cols, rows, frames, t_from, t_to, margin_mm, page,
                        pen_id=None, framing=framing, marks=marks)
                except (ValueError, IndexError, RuntimeError) as e:
                    raise HTTPException(status_code=400, detail=str(e))
                if any(layer.paths for layer in doc.layers):
                    any_geometry = True
                zf.writestr(f"sheet_{page:02d}.svg", svg_io.doc_to_svg(doc))
        else:
            for i in range(frames):
                t_i = t_from + (t_to - t_from) * i / (frames - 1) if frames > 1 else t_from
                doc = session.cropped(session.resolved_document(master_t=t_i))
                if any(layer.paths for layer in doc.layers):
                    any_geometry = True
                zf.writestr(f"frame_{i:04d}.svg", svg_io.doc_to_svg(doc))
    if not any_geometry:
        raise HTTPException(status_code=400, detail="project resolves to no geometry — nothing to export")
    name = project_io.safe_name(session.project.name)
    suffix = "sheets" if grid else "frames"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}_{suffix}.zip"'},
    )


@router.get("/animation/sheet_info")
def sheet_info(
    frames: int = Query(ge=2, le=240),
    cols: int = Query(ge=1, le=12),
    rows: int = Query(ge=1, le=12),
    t_from: float = Query(default=0.0, ge=0.0, le=1.0),
    t_to: float = Query(default=1.0, ge=0.0, le=1.0),
    margin_mm: float = Query(default=5.0, ge=0.0, le=30.0),
    page: int = Query(default=0, ge=0, le=239),
) -> dict[str, Any]:
    """Grid-sheet layout summary for the stepper: total ``sheets``, ``cells``
    on the requested page, and the ordered pen ``passes`` for that page (each
    ``{pen_id, name, color}`` — one plot pass; ``pen_id=""`` is the no-pen
    group). Lets the two-dimensional stepper label sheets/passes without
    recomputing the assembly client-side."""
    per_page = cols * rows
    n_pages = session.sheet_pages(frames, cols, rows)
    page = min(page, n_pages - 1)
    cells = min(per_page, frames - page * per_page)
    pens = session.pens()
    try:
        pids = session.sheet_passes(cols, rows, frames, t_from, t_to, margin_mm, page)
    except (ValueError, IndexError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    passes = [
        {
            "pen_id": pid,
            "name": (pens[pid].name if pid and pid in pens else "no pen"),
            "color": (pens[pid].color if pid and pid in pens else compose.INK),
        }
        for pid in pids
    ]
    return {"sheets": n_pages, "page": page, "cells": cells, "passes": passes}


@router.get("/animation/preview.png")
def animation_preview_png(
    t: float = Query(default=0.0, ge=0.0, le=1.0),
    width_px: int = Query(default=1200, ge=240, le=2400),
) -> Response:
    """Raster preview frame for popup playback. Geometry still comes from the
    single resolved path; this endpoint only draws that resolved geometry into
    a cached-friendly bitmap so playback can swap images instead of re-solving
    and re-DOMing vectors every frame."""
    from PIL import Image, ImageColor, ImageDraw

    aa = 2
    scale = width_px / compose.BED_WIDTH
    height_px = max(1, int(round(compose.BED_HEIGHT * scale)))
    draw_scale = scale * aa
    img = Image.new("RGB", (width_px * aa, height_px * aa), "#faf7ef")
    draw = ImageDraw.Draw(img, "RGBA")

    def rgba(color: str, opacity: float) -> tuple[int, int, int, int]:
        try:
            r, g, b = ImageColor.getrgb(color)
        except Exception:
            r, g, b = ImageColor.getrgb(compose.INK)
        return (r, g, b, int(max(0.0, min(1.0, opacity)) * 255))

    try:
        resolved = session.resolved(master_t=t)
    except Exception as e:
        raise _fail(e, 400)
    pens = session.pens()
    for layer in session.project.layers:
        if not layer.visible:
            continue
        paths = resolved.get(layer.id, [])
        if not paths:
            continue
        pen = pens.get(layer.pen_id or "")
        color = rgba(pen.color if pen else compose.INK, pen.opacity if pen else 1.0)
        width = max(1, int(round((pen.line_diameter_mm if pen else compose.DEFAULT_LINE_DIAMETER_MM) * draw_scale)))
        for path in paths:
            if len(path.points) < 2:
                continue
            pts = [(x * draw_scale, y * draw_scale) for x, y in path.points]
            draw.line(pts, fill=color, width=width, joint="curve")

    img = img.resize((width_px, height_px), Image.Resampling.LANCZOS)
    if session.project.view == "portrait":
        img = img.transpose(Image.Transpose.ROTATE_270)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Response(content=buf.getvalue(), media_type="image/png")


class ContactSheetBody(BaseModel):
    cols: int = Field(ge=1, le=12)
    rows: int = Field(ge=1, le=12)
    frames: int = Field(ge=2, le=144)  # further bounded to cols*rows in session
    margin_mm: float = Field(default=5.0, ge=0.0, le=30.0)
    t_from: float = Field(default=0.0, ge=0.0, le=1.0)
    t_to: float = Field(default=1.0, ge=0.0, le=1.0)


@router.post("/animation/contact_sheet")
def bake_contact_sheet(body: ContactSheetBody) -> dict[str, Any]:
    """Bake N frames of the master timeline into a cols×rows grid on one
    sheet — one baked layer per frame, uniformly scaled and centred in its
    cell. One undo step (see Session.bake_contact_sheet)."""
    try:
        layers = session.bake_contact_sheet(
            body.cols, body.rows, body.frames, body.margin_mm, body.t_from, body.t_to
        )
    except ValueError as e:
        raise _fail(e, 400)
    except Exception as e:
        raise _fail(e)
    return {"layers": [l.model_dump() for l in layers]}


# -- staging tray ---------------------------------------------------------------


@router.get("/staging")
def get_staging() -> dict[str, Any]:
    return {"groups": [g.model_dump(exclude={"snapshot"}) for g in session.project.staging]}


class StagingCaptureBody(BaseModel):
    kind: str = Field(pattern="^(plot|frame|sheet)$")
    name: str | None = None
    target: str = "all"
    master_t: float | None = Field(default=None, ge=0.0, le=1.0)
    cols: int = Field(default=1, ge=1, le=12)
    rows: int = Field(default=1, ge=1, le=12)
    frames: int = Field(default=2, ge=2, le=240)
    t_from: float = Field(default=0.0, ge=0.0, le=1.0)
    t_to: float = Field(default=1.0, ge=0.0, le=1.0)
    margin_mm: float = Field(default=5.0, ge=0.0, le=30.0)
    framing: Literal["center", "fixed"] = "center"
    marks: bool = False


@router.post("/staging/capture")
def capture_to_staging(body: StagingCaptureBody) -> dict[str, Any]:
    try:
        group = session.capture_to_staging(
            kind=body.kind,
            name=body.name,
            target=body.target,
            master_t=body.master_t,
            cols=body.cols,
            rows=body.rows,
            frames=body.frames,
            t_from=body.t_from,
            t_to=body.t_to,
            margin_mm=body.margin_mm,
            framing=body.framing,
            marks=body.marks,
        )
    except (KeyError, ValueError) as e:
        raise _fail(e, 400)
    except RuntimeError as e:
        raise _fail(e, 400)
    except Exception as e:
        raise _fail(e)
    return {"group": group.model_dump(exclude={"snapshot"})}


class RenameCaptureBody(BaseModel):
    name: str


@router.patch("/staging/groups/{group_id}")
def rename_capture_group(group_id: str, body: RenameCaptureBody) -> dict[str, Any]:
    try:
        group = session.rename_capture_group(group_id, body.name)
    except KeyError as e:
        raise _fail(e, 404)
    return {"group": group.model_dump(exclude={"snapshot"})}


class ReorderCapturesBody(BaseModel):
    ids: list[str]


@router.post("/staging/reorder")
def reorder_capture_groups(body: ReorderCapturesBody) -> dict[str, Any]:
    try:
        groups = session.reorder_capture_groups(body.ids)
    except ValueError as e:
        raise _fail(e, 422)
    return {"groups": [g.model_dump(exclude={"snapshot"}) for g in groups]}


@router.post("/staging/groups/{group_id}/duplicate")
def duplicate_capture_group(group_id: str) -> dict[str, Any]:
    try:
        group = session.duplicate_capture_group(group_id)
    except KeyError as e:
        raise _fail(e, 404)
    return {"group": group.model_dump(exclude={"snapshot"})}


@router.delete("/staging/groups/{group_id}")
def delete_capture_group(group_id: str) -> dict[str, Any]:
    try:
        removed = session.delete_capture_group(group_id)
    except KeyError as e:
        raise _fail(e, 404)
    return {"removed": removed}


@router.post("/staging/groups/{group_id}/sheets/{sheet_id}/insert")
def insert_staged_sheet(group_id: str, sheet_id: str) -> dict[str, Any]:
    try:
        layers = session.insert_staged_sheet(group_id, sheet_id)
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)
    return {"layers": [l.model_dump() for l in layers]}


class InterpolateCapturesBody(BaseModel):
    a: str
    b: str
    steps: int = Field(default=5, ge=2, le=60)
    name: str | None = None


@router.post("/staging/interpolate")
def interpolate_captures(body: InterpolateCapturesBody) -> dict[str, Any]:
    try:
        group = session.interpolate_captures(body.a, body.b, body.steps, body.name)
    except KeyError as e:
        raise _fail(e, 404)
    except ValueError as e:
        raise _fail(e, 400)
    except Exception as e:
        raise _fail(e)
    return {"group": group.model_dump(exclude={"snapshot"})}


@router.get("/staging/export.zip")
def export_staged_zip(group_id: str | None = None) -> Response:
    buf = io.BytesIO()
    groups = session.project.staging
    if group_id is not None:
        try:
            groups = [session._find_capture(group_id)]
        except KeyError as e:
            raise _fail(e, 404)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        any_geometry = False
        for group in groups:
            for i, sheet in enumerate(group.sheets):
                try:
                    doc = session._optimize(session.staged_document(group.id, sheet.id))
                except KeyError:
                    continue
                if any(layer.paths for layer in doc.layers):
                    any_geometry = True
                zf.writestr(
                    f"{project_io.safe_name(group.name)}_sheet_{i:02d}.svg",
                    svg_io.doc_to_svg(doc),
                )
    if not any_geometry:
        raise HTTPException(status_code=400, detail="no staged geometry to export")
    name = project_io.safe_name(session.project.name)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}_staging.zip"'},
    )


# -- generation workbench (stateless playground + global scrap library) --------------


class WorkbenchBody(BaseModel):
    """A workbench recipe: one generator plus a candidate effect stack."""
    module: str
    params: dict[str, Any] = Field(default_factory=dict)
    effects: list[dict[str, Any]] = Field(default_factory=list)
    name: str = ""


def _workbench_result(body: WorkbenchBody) -> tuple[Any, list[Any]]:
    """Run the recipe touching NOTHING: no session, no undo, no lock.
    Geometry stays at the canvas origin (identity placement), so effects run
    in paper space exactly as they would on a real layer. Nothing plots from
    here — geometry reaches the machine only after import, through the
    normal single resolve path."""
    src = get_source(body.module)
    doc = src.generate(src.Params(**body.params))
    paths = [p for layer in doc.layers for p in layer.paths]
    for step_dict in body.effects:
        step = compose.EffectStep(**step_dict)
        if not step.enabled:
            continue
        eff = get_effect(step.effect)
        paths = eff.apply(paths, eff.Params(**step.params), EffectContext())
    return doc, paths


@router.post("/workbench/preview")
def workbench_preview(body: WorkbenchBody) -> dict[str, Any]:
    try:
        with progress_scope(_gen_progress_sink()):
            doc, paths = _workbench_result(body)
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)
    return {**_preview_payload(paths), "width": doc.width, "height": doc.height}


@router.get("/scraps")
def list_scraps() -> dict[str, Any]:
    return {"scraps": [s.model_dump() for s in scrap_library.all()]}


@router.post("/scraps")
def save_scrap(body: WorkbenchBody) -> dict[str, Any]:
    """Regenerate server-side and freeze to SVG — a scrap stores what the
    recipe produces, not what the client happened to render."""
    try:
        doc, paths = _workbench_result(body)
    except KeyError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)
    if not any(p.points for p in paths):
        raise HTTPException(status_code=400, detail="nothing to save")
    frozen = PathDocument(
        layers=[DocLayer(id=1, name=body.name or body.module, paths=paths)],
        width=doc.width, height=doc.height, source=f"workbench:{body.module}",
    )
    scrap = scrap_library.save(
        name=body.name, module=body.module, params=body.params,
        effects=body.effects, svg=svg_io.doc_to_svg(frozen),
        points=sum(len(p.points) for p in paths),
    )
    return scrap.model_dump()


@router.get("/scraps/{scrap_id}.svg")
def scrap_svg(scrap_id: str) -> Response:
    svg = scrap_library.svg(scrap_id)
    if svg is None:
        raise HTTPException(status_code=404, detail="unknown scrap")
    return Response(content=svg, media_type="image/svg+xml")


@router.delete("/scraps/{scrap_id}")
def delete_scrap(scrap_id: str) -> dict[str, Any]:
    scrap_library.delete(scrap_id)
    return {"ok": True}


@router.post("/scraps/{scrap_id}/import")
def import_scrap(scrap_id: str) -> dict[str, Any]:
    """Insert a scrap's frozen SVG into the current project as baked layers —
    exactly what was saved, however module code evolved since."""
    scrap = scrap_library.get(scrap_id)
    svg = scrap_library.svg(scrap_id)
    if scrap is None or svg is None:
        raise HTTPException(status_code=404, detail="unknown scrap")
    try:
        created = session.add_svg_layers(
            svg, f"{project_io.safe_name(scrap.name)}.svg", 0.1, rename=scrap.name)
    except Exception as e:
        raise _fail(e, 400)
    return {"layers": [layer.model_dump() for layer in created]}


# -- plot control -------------------------------------------------------------------


class SheetSpec(BaseModel):
    """Grid-sheet assembly: ``frames`` timeline samples over [t_from, t_to]
    laid cols×rows per page, one shared scale across all sheets. ``page`` picks
    the physical sheet; ``pen_id`` picks a single pen pass (``""`` = the no-pen
    group, None = every group). Reused by plot/start, /plan and sheet_info."""
    cols: int = Field(ge=1, le=12)
    rows: int = Field(ge=1, le=12)
    frames: int = Field(ge=2, le=240)
    t_from: float = Field(default=0.0, ge=0.0, le=1.0)
    t_to: float = Field(default=1.0, ge=0.0, le=1.0)
    margin_mm: float = Field(default=5.0, ge=0.0, le=30.0)
    page: int = Field(default=0, ge=0, le=239)
    pen_id: str | None = None
    #: "center" = each frame centred by its own bbox (parameter sweeps);
    #: "fixed" = one shared window, so translation reads as motion (flipbooks)
    framing: Literal["center", "fixed"] = "center"
    #: registration crosshairs at the grid intersections, on the first pass
    marks: bool = False


def _sheet_document(spec: SheetSpec) -> Any:
    return session.sheet_document(
        spec.cols, spec.rows, spec.frames, spec.t_from, spec.t_to,
        spec.margin_mm, spec.page, spec.pen_id,
        framing=spec.framing, marks=spec.marks,
    )


class StagedSpec(BaseModel):
    group_id: str
    sheet_id: str | None = None
    pen_id: str | None = None


def _staged_document(spec: StagedSpec) -> Any:
    return session.staged_document(spec.group_id, spec.sheet_id, spec.pen_id)


class PlotStartBody(BaseModel):
    target: str = "all"  # "all" or a layer id — the manual multi-pen selector
    #: ephemeral master-timeline scrub (see Session.resolved) — the hook for
    #: the frame-by-frame animation stepper. None = no scrub (unchanged).
    master_t: float | None = Field(default=None, ge=0.0, le=1.0)
    #: grid-sheet plot pass — when set, plots one pen group of one sheet
    #: (transient assembly; ``target``/``master_t`` are ignored).
    sheet: SheetSpec | None = None
    staged: StagedSpec | None = None


@router.post("/plot/start")
def plot_start(body: PlotStartBody) -> dict[str, Any]:
    try:
        if body.staged is not None:
            doc = session._optimize(_staged_document(body.staged))
            pen = session.pens().get(body.staged.pen_id) if body.staged.pen_id else None
            params = session.effective_params(manager.active_id, pen=pen)
        elif body.sheet is not None:
            doc = session._optimize(_sheet_document(body.sheet))
            pen = session.pens().get(body.sheet.pen_id) if body.sheet.pen_id else None
            params = session.effective_params(manager.active_id, pen=pen)
        else:
            doc = session.plot_document(body.target, master_t=body.master_t)
            params = session.effective_params(manager.active_id, body.target)
        if not any(layer.paths for layer in doc.layers):
            raise RuntimeError("nothing to plot (no resolved geometry in target)")
        manager.start_plot(doc, params)
    except (KeyError, ValueError, IndexError) as e:
        raise _fail(e, 400)
    except RuntimeError as e:
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
def get_project() -> dict[str, Any]:
    return _project_payload()


class ProjectPatch(BaseModel):
    name: str | None = None
    guide: PaperGuide | None = None
    view: str | None = None
    plot_options: PlotOptions | None = None


@router.put("/project")
def patch_project(body: ProjectPatch) -> dict[str, Any]:
    p = session.project
    if body.name is not None:
        p.name = body.name
    if body.guide is not None:
        p.guide = body.guide
    if body.view in ("portrait", "landscape"):
        p.view = body.view
    if body.plot_options is not None:
        p.plot_options = body.plot_options
    return _project_payload()


@router.post("/project/new")
def new_project() -> dict[str, Any]:
    session.project = Project()
    session.project_dir = None
    session.source_geometry.clear()
    session.svg_files.clear()
    session.staging_documents.clear()
    session._shaped_cache.clear()
    session._tween_cache.clear()
    session._clip_cache.clear()
    session.clear_history()
    asset_store.replace_all({})
    return _project_payload()


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
            staging_documents=session.staging_documents,
            history=session.history_for_save(),
        )
    except OSError as e:
        raise _fail(e, 400)
    session.project_dir = str(target)
    return {"saved": str(target)}


class LoadBody(BaseModel):
    name: str


@router.post("/project/load")
def load_project(body: LoadBody) -> dict[str, Any]:
    target = settings_store.settings.projects_dir() / project_io.safe_name(body.name)
    try:
        project, geometry, svg_files, assets, staging_documents, history = project_io.load_project(target)
    except FileNotFoundError as e:
        raise _fail(e, 404)
    except Exception as e:
        raise _fail(e, 400)
    session.project = project
    session.source_geometry = geometry
    session.svg_files = svg_files
    session.staging_documents = staging_documents
    session.project_dir = str(target)
    session._shaped_cache.clear()
    session._tween_cache.clear()
    session._clip_cache.clear()
    session.restore_history(history)
    asset_store.replace_all(assets)
    return _project_payload()


@router.get("/project/export.zip")
def export_project() -> Response:
    name = project_io.safe_name(session.project.name)
    target = settings_store.settings.projects_dir() / name
    project_io.save_project(
        session.project, session.source_geometry, session.svg_files, target,
        assets=asset_store.all(),
        staging_documents=session.staging_documents,
        history=session.history_for_save(),
    )
    session.project_dir = str(target)
    data = project_io.export_zip(target)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )


@router.post("/project/import")
async def import_project(file: UploadFile) -> dict[str, Any]:
    data = await file.read()
    name = FsPath(file.filename or "imported").stem
    try:
        target = project_io.import_zip(data, settings_store.settings.projects_dir(), name)
        project, geometry, svg_files, assets, staging_documents, history = project_io.load_project(target)
    except (ValueError, FileExistsError) as e:
        raise _fail(e, 400)
    session.project = project
    session.source_geometry = geometry
    session.svg_files = svg_files
    session.staging_documents = staging_documents
    session.project_dir = str(target)
    session._shaped_cache.clear()
    session._tween_cache.clear()
    session._clip_cache.clear()
    session.restore_history(history)
    asset_store.replace_all(assets)
    return _project_payload()
