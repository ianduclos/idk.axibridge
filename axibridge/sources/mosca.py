"""Replay a completed mosca-draw history as progressive plot geometry."""

from __future__ import annotations

import math

import numpy as np

from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..mosca import load_recording, recording_info
from ..registry import SourceModule, register_source
from ..render_work import checkpoint


class MoscaParams(BaseModel):
    recording: str = Field(
        default="", title="Recording",
        description="Prepared Mosca recording asset",
        json_schema_extra={"format": "asset", "hidden": True},
    )
    progress: float = Field(default=1.0, ge=0.0, le=1.0, title="Progress")
    tolerance: float = Field(
        default=0.05, ge=0.0, le=5.0, title="Curve tolerance (mm)",
        description="Simplify each uninterrupted ink passage independently",
    )


def _ink_runs(points: np.ndarray, pen_down: np.ndarray | None) -> list[np.ndarray]:
    if len(points) < 2:
        return []
    if pen_down is None:
        return [points]
    checkpoint()
    edges = np.r_[False, pen_down[1:], False]
    starts = np.flatnonzero(~edges[:-1] & edges[1:])
    stops = np.flatnonzero(edges[:-1] & ~edges[1:])
    return [points[lo:hi + 1] for lo, hi in zip(starts, stops)]


def _cut(path, pen_down, progress: float):
    """Cut at fractional sample time, including a partial final ink edge."""
    n = len(path)
    if progress <= 0 or n < 2:
        return np.empty((0, 2), dtype=np.float64), (
            np.empty(0, dtype=np.bool_) if pen_down is not None else None)
    edge_position = min(progress, 1.0) * (n - 1)
    complete = int(math.floor(edge_position + 1e-12))
    points = np.asarray(path[:complete + 1], dtype=np.float64)
    mask = (np.asarray(pen_down[:complete + 1], dtype=np.bool_)
            if pen_down is not None else None)
    fraction = edge_position - complete
    if fraction > 1e-12 and complete < n - 1:
        a, b = path[complete], path[complete + 1]
        endpoint = a + (b - a) * fraction
        points = np.vstack((points, endpoint))
        if mask is not None:
            mask = np.r_[mask, bool(pen_down[complete + 1])]
    return points, mask


def _simplify(points, tolerance: float
              ) -> np.ndarray:
    if tolerance <= 0 or len(points) <= 2:
        return points
    # Shapely is already a core compositor dependency.  Keeping this local
    # avoids paying its import cost while the module catalogue loads.
    from shapely.geometry import LineString
    checkpoint()
    simplified = np.asarray(
        LineString(points).simplify(tolerance, preserve_topology=False).coords,
        dtype=np.float64,
    )
    checkpoint()
    return simplified


def recording_paths(recording: dict, progress: float, tolerance: float
                    ) -> tuple[list[Path], float, float]:
    """Shared pure geometry core (also suitable for a future thumbnail)."""
    full = recording["path"]
    mn, mx = recording.get("_bounds") or (full.min(axis=0), full.max(axis=0))
    width, height = float(mx[0] - mn[0]) + 10.0, float(mx[1] - mn[1]) + 10.0
    cut, mask = _cut(full, recording["pen_down"], progress)
    paths = []
    for raw_run in _ink_runs(cut, mask):
        run = _simplify(raw_run, tolerance)
        points = [(float(x - mn[0] + 5.0), float(mx[1] - y + 5.0)) for x, y in run]
        paths.append(Path(points=points))
    return paths, width, height


@register_source
class MoscaSource(SourceModule):
    id = "mosca"
    label = "Mosca"
    description = "Replay and keep a completed mosca-draw trajectory."
    orientation = "geometry"
    Params = MoscaParams
    bench = {"adapter": "mosca", "version": 1, "modes": ["new", "resume"]}
    library_bench = True

    def placement_frame(self, params: dict) -> tuple[float, float] | None:
        name = str(params.get("recording", ""))
        if not name:
            return None
        info = recording_info(name)
        return info["width"], info["height"]

    def generate(self, params: MoscaParams) -> PathDocument:
        if not params.recording:
            return PathDocument(source="mosca")
        recording = load_recording(params.recording)
        paths, width, height = recording_paths(
            recording, params.progress, params.tolerance)
        return PathDocument(
            layers=[Layer(id=1, name="Mosca", paths=paths)],
            width=width, height=height, source="mosca",
        )
