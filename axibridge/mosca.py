"""Read-only bridge from completed mosca-draw histories to project assets.

The simulation directory is never mutated.  ``prepare_recording`` reduces a
history to the small, safe subset needed by the source and keeps those bytes
in a bounded process-local cache until the caller persists them as an ordinary
project asset.
"""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import io
import json
import os
from pathlib import Path
import re
import threading
import zipfile

import numpy as np

from .assets import asset_store
from .gencache import cache_budget_multiplier


DEFAULT_MOSCA_DIR = Path("/Users/ianduclos/_SecondBrain/01_Projects/mosca-draw")
_PART_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_ASSET_RE = re.compile(r"[0-9a-f]{64}\.npz\Z")
_CACHE_LIMIT = max(1, int(64 * 1024 * 1024 * cache_budget_multiplier()))
_prepared: OrderedDict[str, bytes] = OrderedDict()
_prepared_size = 0
_prepared_lock = threading.Lock()
_decoded: OrderedDict[str, tuple[dict, int]] = OrderedDict()
_decoded_size = 0
_DECODED_LIMIT = max(1, int(128 * 1024 * 1024 * cache_budget_multiplier()))


def _out_dir() -> Path:
    root = Path(os.environ.get("AXIBRIDGE_MOSCA_DIR", DEFAULT_MOSCA_DIR)).expanduser()
    return root / "out" if (root / "out").is_dir() else root


def _parts(recording_id: str) -> tuple[str, str]:
    bits = recording_id.split("/")
    if len(bits) != 2 or not all(_PART_RE.fullmatch(bit) for bit in bits):
        raise ValueError("recording id must be 'experiment/name'")
    return bits[0], bits[1]


def _history_path(recording_id: str) -> Path:
    experiment, label = _parts(recording_id)
    out = _out_dir().resolve()
    if not out.is_dir():
        raise ValueError(
            f"Mosca output directory not found: {out}. "
            "Set AXIBRIDGE_MOSCA_DIR to the mosca-draw project or its out directory."
        )
    path = (out / experiment / f"{label}.npz").resolve()
    if out not in path.parents:
        raise ValueError("recording is outside the Mosca output directory")
    if not path.is_file():
        raise ValueError(f"unknown Mosca recording {recording_id!r}")
    return path


def list_recordings() -> list[dict[str, str]]:
    """List completed histories without opening their potentially large arrays."""
    out = _out_dir()
    if not out.is_dir():
        raise ValueError(
            f"Mosca output directory not found: {out}. "
            "Set AXIBRIDGE_MOSCA_DIR to the mosca-draw project or its out directory."
        )
    rows: list[dict[str, str]] = []
    for path in out.glob("*/*.npz"):
        experiment, label = path.parent.name, path.stem
        if _PART_RE.fullmatch(experiment) and _PART_RE.fullmatch(label):
            rows.append({"id": f"{experiment}/{label}",
                         "experiment": experiment, "label": label})
    return sorted(rows, key=lambda row: (row["experiment"], row["label"]))


def _scalar_float(value: np.ndarray, field: str) -> float:
    if value.shape != ():
        raise ValueError(f"{field} must be a scalar")
    number = float(value)
    if not np.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return number


def _scalar_text(value: np.ndarray, field: str) -> str:
    if value.shape != () or value.dtype.kind not in "US":
        raise ValueError(f"{field} must be a scalar string")
    text = str(value)
    try:
        json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must contain JSON") from exc
    return text


def _read(data_or_path: bytes | Path) -> dict:
    source = io.BytesIO(data_or_path) if isinstance(data_or_path, bytes) else data_or_path
    try:
        with np.load(source, allow_pickle=False) as archive:
            if "path" not in archive.files:
                raise ValueError("recording has no path")
            path = np.asarray(archive["path"])
            if path.ndim != 2 or path.shape[1:] != (2,) or path.dtype.kind not in "fiu":
                raise ValueError("path must be a numeric Nx2 array")
            path = np.asarray(path, dtype=np.float64)
            if len(path) == 0 or not np.isfinite(path).all():
                raise ValueError("path must contain finite samples")
            pen_down = None
            if "pen_down" in archive.files:
                raw_pen = np.asarray(archive["pen_down"])
                if raw_pen.shape != (len(path),) or raw_pen.dtype.kind not in "bui":
                    raise ValueError("pen_down must have one value per path point")
                if raw_pen.dtype.kind != "b" and not np.isin(raw_pen, (0, 1)).all():
                    raise ValueError("pen_down values must be boolean")
                pen_down = np.asarray(raw_pen, dtype=np.bool_)
            dt = _scalar_float(np.asarray(archive["dt"]), "dt") if "dt" in archive.files else None
            config = (_scalar_text(np.asarray(archive["config_json"]), "config_json")
                      if "config_json" in archive.files else None)
            experiment = (_scalar_text_value(np.asarray(archive["experiment"]), "experiment")
                          if "experiment" in archive.files else None)
            label = (_scalar_text_value(np.asarray(archive["label"]), "label")
                     if "label" in archive.files else None)
    except (OSError, zipfile.BadZipFile, EOFError) as exc:
        raise ValueError("invalid Mosca NPZ") from exc
    path.setflags(write=False)
    if pen_down is not None:
        pen_down.setflags(write=False)
    return {"path": path, "pen_down": pen_down, "dt": dt, "config_json": config,
            "experiment": experiment, "label": label,
            "_bounds": (path.min(axis=0), path.max(axis=0))}


def _scalar_text_value(value: np.ndarray, field: str) -> str:
    if value.shape != () or value.dtype.kind not in "US":
        raise ValueError(f"{field} must be a scalar string")
    text = str(value)
    if not _PART_RE.fullmatch(text):
        raise ValueError(f"invalid {field}")
    return text


def _npy_bytes(value: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.lib.format.write_array(stream, value, allow_pickle=False)
    return stream.getvalue()


def _compact_bytes(recording: dict) -> bytes:
    """A deterministic NPZ: fixed ZIP metadata makes the hash content-based."""
    arrays = [("path", np.asarray(recording["path"], dtype="<f8"))]
    if recording["pen_down"] is not None:
        arrays.append(("pen_down", np.asarray(recording["pen_down"], dtype=np.bool_)))
    if recording["dt"] is not None:
        arrays.append(("dt", np.asarray(recording["dt"], dtype="<f8")))
    if recording["config_json"] is not None:
        arrays.append(("config_json", np.asarray(recording["config_json"])))
    for field in ("experiment", "label"):
        if recording.get(field) is not None:
            arrays.append((field, np.asarray(recording[field])))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        for key, value in arrays:
            info = zipfile.ZipInfo(f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, _npy_bytes(value), compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=6)
    return stream.getvalue()


def _metadata(recording: dict) -> dict:
    path = recording["path"]
    mn, mx = recording.get("_bounds") or (path.min(axis=0), path.max(axis=0))
    result = {
        "samples": int(len(path)),
        "duration_ms": (float(recording["dt"]) * max(len(path) - 1, 0)
                        if recording["dt"] is not None else None),
        "width": float(mx[0] - mn[0]) + 10.0,
        "height": float(mx[1] - mn[1]) + 10.0,
    }
    if recording.get("experiment") is not None:
        result["experiment"] = recording["experiment"]
    if recording.get("label") is not None:
        result["label"] = recording["label"]
    return result


def _cache_put(name: str, data: bytes) -> None:
    global _prepared_size
    with _prepared_lock:
        old = _prepared.pop(name, None)
        if old is not None:
            _prepared_size -= len(old)
        _prepared[name] = data
        _prepared_size += len(data)
        while _prepared_size > _CACHE_LIMIT and len(_prepared) > 1:
            _, evicted = _prepared.popitem(last=False)
            _prepared_size -= len(evicted)


def prepare_recording(recording_id: str) -> dict:
    experiment, label = _parts(recording_id)
    recording = _read(_history_path(recording_id))
    recording["experiment"] = experiment
    recording["label"] = label
    data = _compact_bytes(recording)
    name = f"{hashlib.sha256(data).hexdigest()}.npz"
    _cache_put(name, data)
    _decoded_put(name, recording)
    return {"recording": name, **_metadata(recording)}


def recording_bytes(name: str) -> bytes:
    """Resolve a prepared recording or its persisted project-asset copy."""
    if not _ASSET_RE.fullmatch(name):
        raise ValueError("invalid Mosca recording asset name")
    with _prepared_lock:
        data = _prepared.get(name)
        if data is not None:
            _prepared.move_to_end(name)
            return data
    data = asset_store.get(name)
    if data is None:
        raise ValueError(f"no Mosca recording asset named {name!r}")
    return data


def recording_info(name: str) -> dict:
    return {"recording": name, **_metadata(load_recording(name))}


def load_recording(name: str) -> dict:
    """Internal source-facing decoded form with shared read-only arrays."""
    with _prepared_lock:
        cached = _decoded.get(name)
        if cached is not None:
            _decoded.move_to_end(name)
            return cached[0]
    decoded = _read(recording_bytes(name))
    _decoded_put(name, decoded)
    return decoded


def _decoded_put(name: str, recording: dict) -> None:
    global _decoded_size
    size = recording["path"].nbytes
    if recording["pen_down"] is not None:
        size += recording["pen_down"].nbytes
    with _prepared_lock:
        old = _decoded.pop(name, None)
        if old is not None:
            _decoded_size -= old[1]
        _decoded[name] = (recording, size)
        _decoded_size += size
        while _decoded_size > _DECODED_LIMIT and len(_decoded) > 1:
            _, (_, evicted_size) = _decoded.popitem(last=False)
            _decoded_size -= evicted_size


def thumbnail_recording(recording_id: str) -> str:
    """Render a bounded SVG preview without populating the prepared cache."""
    from .gallery import thumbnail
    from .model import Path as DrawingPath

    recording = _read(_history_path(recording_id))
    xy = recording["path"]
    pen = recording["pen_down"]
    mn, mx = xy.min(axis=0), xy.max(axis=0)

    # Locate continuous incoming-edge runs. Legacy recordings are one run.
    if pen is None:
        spans = [(0, len(xy) - 1)] if len(xy) >= 2 else []
    else:
        edges = np.r_[False, pen[1:], False]
        starts = np.flatnonzero(~edges[:-1] & edges[1:])
        stops = np.flatnonzero(edges[:-1] & ~edges[1:])
        spans = list(zip(starts.tolist(), stops.tolist()))
    total = sum(hi - lo + 1 for lo, hi in spans)
    stride = max(1, int(np.ceil(total / 60_000)))
    paths = []
    for lo, hi in spans:
        indexes = np.arange(lo, hi + 1, stride, dtype=np.int64)
        if len(indexes) == 0 or indexes[-1] != hi:
            indexes = np.r_[indexes, hi]
        sample = xy[indexes]
        points = [(float(x - mn[0] + 5.0), float(mx[1] - y + 5.0))
                  for x, y in sample]
        if len(points) >= 2:
            paths.append(DrawingPath(points=points))
    return thumbnail(paths)
