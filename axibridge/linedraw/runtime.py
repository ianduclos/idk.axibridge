"""Optional, local-only model runtime. No neural packages imported by the server."""

from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections import OrderedDict
import numpy as np
from PIL import Image, ImageOps
from ..render_work import RenderCancelled
from ..stores import CONFIG_DIR
from .contracts import Candidate, Evidence, FaceRegion, LinedrawV3Params
from .trace import trace_map

_ROOT = Path(__file__).resolve().parents[2]
_LOCK = threading.Lock()
_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
_FINGERPRINTS = {}


def config_path():
    return Path(
        os.environ.get("AXIBRIDGE_LINEDRAW_CONFIG", CONFIG_DIR / "linedraw.json")
    ).expanduser()


def configuration():
    try:
        config = json.loads(config_path().read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(
            "Linedraw models are not configured. Run tools/setup_linedraw.py --help."
        ) from exc
    if not isinstance(config, dict):
        raise ValueError("Invalid Linedraw runtime configuration")
    for key in ("python", "line_code", "line_weights", "person_weights"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError(f"Linedraw configuration is missing {key}")
        if not Path(config.get(key, "")).is_file() and not (
            key == "line_code" and Path(config.get(key, "")).is_dir()
        ):
            raise ValueError(
                f"Linedraw configuration is missing {key}; run tools/setup_linedraw.py --check"
            )
    return config


def status():
    try:
        c = configuration()
        form = (
            all(Path(c.get(k, "")).is_file() for k in ("normal_weights",))
            and Path(c.get("normal_code", "")).is_dir()
        )
        faces = all(
            Path(c.get(k, "")).is_file() for k in ("face_python", "face_weights")
        )
        return {
            "available": True,
            "form": form,
            "faces": faces,
            "detail": "Local models configured; first analysis loads weights.",
        }
    except ValueError as exc:
        return {"available": False, "form": False, "faces": False, "detail": str(exc)}


def model_identity():
    c = configuration()
    digest = hashlib.sha256(b"linedraw-runtime-v2")
    digest.update(json.dumps(c, sort_keys=True).encode())
    for key in ("line_weights", "person_weights", "normal_weights", "face_weights"):
        path = Path(c.get(key, ""))
        if not path.is_file():
            continue
        stat = path.stat()
        token = (
            str(path),
            stat.st_mtime_ns,
            stat.st_ctime_ns,
            stat.st_ino,
            stat.st_size,
        )
        if token not in _FINGERPRINTS:
            with path.open("rb") as stream:
                h = hashlib.sha256()
                for part in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(part)
            _FINGERPRINTS.clear() if len(_FINGERPRINTS) > 32 else None
            _FINGERPRINTS[token] = h.digest()
        digest.update(_FINGERPRINTS[token])
    return digest.hexdigest()


def image_identity(data):
    return hashlib.sha256(data).hexdigest()


def evidence_key(data, p, identity):
    return hashlib.sha256(
        (
            image_identity(data)
            + identity
            + json.dumps([f.model_dump() for f in p.faces], sort_keys=True)
        ).encode()
    ).hexdigest()


def clear_cache():
    with _CACHE_LOCK:
        _CACHE.clear()


def _cache_put(key, evidence):
    from ..gencache import cache_budget_multiplier

    arrays = [
        evidence.rgb,
        evidence.foreground,
        evidence.normals,
        evidence.whole_lines,
        evidence.tiled_lines,
        evidence.alpha,
    ]
    size = sum(a.nbytes for a in arrays if a is not None) + sum(
        c.points.nbytes for cs in evidence.face_candidates.values() for c in cs
    )
    size += sum(c.points.nbytes for c in (evidence.whole_candidates or ()))
    size += sum(c.points.nbytes for c in (evidence.tiled_candidates or ()))
    budget = int(256 * 1024**2 * cache_budget_multiplier())
    if size > budget:
        return
    with _CACHE_LOCK:
        _CACHE[key] = (evidence, size)
        _CACHE.move_to_end(key)
        while sum(s for _, s in _CACHE.values()) > budget:
            _CACHE.popitem(last=False)


def validate_arrays(arrays, w, h):
    if min(w, h) < 1 or max(w, h) > 1536 or w * h > 2_400_000:
        raise ValueError("Invalid evidence dimensions")
    expected = {
        "rgb": (h, w, 3),
        "foreground": (h, w),
        "whole_lines": (h, w),
        "tiled_lines": (h, w),
        "alpha": (h, w),
    }
    if "normals" in arrays:
        expected["normals"] = (h, w, 3)
    for key, shape in expected.items():
        a = arrays.get(key)
        if a is None or a.shape != shape or not np.isfinite(a).all():
            raise ValueError(f"Invalid {key} evidence")
        if key != "normals" and (a.min() < 0 or a.max() > 1):
            raise ValueError(f"Out-of-range {key} evidence")


def native_candidates(line_map, bounds, width, height, name, checkpoint):
    """Trace before resizing; only vector coordinates enter the source frame."""
    checkpoint()
    line_map = np.asarray(line_map)
    bounds = np.asarray(bounds)
    if (
        line_map.ndim != 2
        or min(line_map.shape) < 1
        or max(line_map.shape) > 768
        or not np.isfinite(line_map).all()
        or line_map.min() < 0
        or line_map.max() > 1
        or bounds.shape != (4,)
        or not np.isfinite(bounds).all()
    ):
        raise ValueError("Invalid native contour evidence")
    x0, y0, x1, y1 = bounds.tolist()
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("Invalid contour crop bounds")
    candidates = trace_map(line_map, name, checkpoint)
    scale = [(x1 - x0) / line_map.shape[1], (y1 - y0) / line_map.shape[0]]
    return tuple(
        Candidate(c.points * scale + [x0, y0], c.confidence, c.identity)
        for c in candidates
    )


def _run(config, request, directory, cancel, progress):
    req = directory / "request.json"
    req.write_text(json.dumps(dict(request, config=config)))
    log = directory / "worker.log"
    last = None
    started = time.monotonic()
    with log.open("wb") as stream:
        proc = subprocess.Popen(
            [config["python"], "-m", "axibridge.linedraw.worker", str(req)],
            cwd=_ROOT,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
        )
        try:
            while proc.poll() is None:
                if cancel.is_set():
                    raise RenderCancelled()
                if time.monotonic() - started > 600:
                    raise ValueError("Linedraw analysis timed out after 10 minutes")
                if log.stat().st_size > 2 * 1024**2:
                    raise ValueError("Linedraw worker produced excessive diagnostics")
                try:
                    current = json.loads((directory / "progress.json").read_text())
                    if current != last:
                        progress(current["fraction"], current["message"])
                        last = current
                except (OSError, ValueError):
                    pass
                cancel.wait(0.1)
            if cancel.is_set():
                raise RenderCancelled()
            if proc.returncode:
                message = log.read_text(errors="replace")[-1500:]
                raise ValueError("Local model analysis failed: " + message)
        finally:
            # The group includes any separate MediaPipe child.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()


def detect_and_analyze(
    image_bytes, params, *, cancel=None, progress=lambda *a: None, detect=False
):
    cancel = cancel or threading.Event()
    if cancel.is_set():
        raise RenderCancelled()
    p = LinedrawV3Params(**params) if isinstance(params, dict) else params
    c = configuration()
    identity = model_identity()
    if p.image_identity and p.image_identity != image_identity(image_bytes):
        raise ValueError("Image changed; analyze it again before using face regions")
    key = evidence_key(image_bytes, p, identity)
    if not detect:
        with _CACHE_LOCK:
            if key in _CACHE:
                _CACHE.move_to_end(key)
                return _CACHE[key][0]
    while not _LOCK.acquire(timeout=0.1):
        if cancel.is_set():
            raise RenderCancelled()
    try:
        if cancel.is_set():
            raise RenderCancelled()
        with tempfile.TemporaryDirectory(prefix="axibridge-linedraw-") as tmp:
            directory = Path(tmp)
            image = ImageOps.exif_transpose(
                Image.open(io.BytesIO(image_bytes))
            ).convert("RGBA")
            image.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
            # Composite transparency onto white, retaining alpha for final clipping.
            background = Image.new("RGBA", image.size, "white")
            background.alpha_composite(image)
            background.convert("RGB").save(directory / "input.png")
            np.save(
                directory / "alpha.npy",
                np.asarray(image.getchannel("A"), dtype=np.float32) / 255,
            )
            _run(
                c,
                {"faces": [f.model_dump() for f in p.faces], "detect": detect},
                directory,
                cancel,
                progress,
            )
            output = directory / "output.npz"
            if not output.is_file() or output.stat().st_size > 128 * 1024**2:
                raise ValueError("Invalid model result size")
            # Uncompressed writer; zip members must also be bounded before allocation.
            import zipfile

            with zipfile.ZipFile(output) as z:
                if sum(i.file_size for i in z.infolist()) > 160 * 1024**2:
                    raise ValueError("Oversized model result")
            with np.load(output, allow_pickle=False) as data:
                arrays = {k: data[k] for k in data.files}
            w, h = image.size
            arrays["rgb"] = (
                np.asarray(background.convert("RGB"), dtype=np.float32) / 255
            )
            arrays["alpha"] = np.load(directory / "alpha.npy", allow_pickle=False)
            validate_arrays(arrays, w, h)
            metadata = json.loads((directory / "faces.json").read_text())
            faces = tuple(FaceRegion(**f) for f in metadata)
            if len(faces) > 32:
                raise ValueError("Too many face regions")

            def check():
                if cancel.is_set():
                    raise RenderCancelled()

            whole_candidates = native_candidates(
                arrays["whole_native"], [0, 0, w, h], w, h, "whole", check
            )
            tiled_candidates = tuple(
                c
                for i in range(4)
                for c in native_candidates(
                    arrays[f"tile_{i}"],
                    arrays[f"tile_box_{i}"],
                    w,
                    h,
                    f"tile-{i}",
                    check,
                )
            )
            face_candidates = {}
            for i, face in enumerate(faces):
                check()
                name = f"face_{i}"
                if name in arrays:
                    face_candidates[face.id] = native_candidates(
                        arrays[name], arrays[f"box_{i}"], w, h, f"face-{face.id}", check
                    )
            diagnostics = json.loads((directory / "diagnostics.json").read_text())
            device = str(diagnostics.get("device", "unknown"))[:64]
            accepted = p.model_copy(update={"faces": list(faces)})
            key = evidence_key(image_bytes, accepted, identity)
            evidence = Evidence(
                arrays["rgb"],
                arrays["foreground"],
                arrays.get("normals"),
                arrays["whole_lines"],
                arrays["tiled_lines"],
                faces,
                face_candidates,
                key,
                arrays["alpha"],
                whole_candidates,
                tiled_candidates,
                device,
            )
            if cancel.is_set():
                raise RenderCancelled()
            if identity != model_identity():
                raise ValueError("Model files changed during analysis; analyze again")
            _cache_put(key, evidence)
            return evidence
    finally:
        _LOCK.release()
