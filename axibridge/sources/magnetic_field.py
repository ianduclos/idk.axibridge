"""Illustrative magnetic orientation geometry.

This is a deterministic port of the approved September 2026 drawing study.
It traces a softened planar pole field; it is an artistic construction, not a
material or force solver.  Field routes are computed once, boundary filtering
happens on those complete routes, and the chosen mark treatment is applied
afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source, report_progress


_STEP = 0.42
_SOFTENING_SQ = 0.7**2
_POLE_BODY_RADIUS = 4.0
_HIDDEN_POLE_CORE_RADIUS = 0.7
_TRACE_STEPS = 2200
_OCCUPANCY_PITCH = 0.9
_MAX_OUTPUT_POINTS = 500_000
_POLE_SPACING_ZONE_RADIUS = 12.0
_HIDDEN = {"hidden": True}


class Magnet(BaseModel):
    """One bar magnet or independent circular pole."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    kind: Literal["bar", "north", "south"] = "bar"
    x: float = Field(default=70.0, ge=0.0, le=300.0)
    y: float = Field(default=85.0, ge=0.0, le=218.0)
    rotation: float = Field(default=0.0, ge=-180.0, le=180.0)
    length: float = Field(default=48.0, ge=8.0, le=80.0)
    thickness: float = Field(default=12.0, ge=4.0, le=24.0)
    strength: float = Field(default=1.0, ge=0.1, le=3.0)
    flipped: bool = False
    locked: bool = False


DEFAULT_MAGNETS = (
    Magnet(x=70.0, y=85.0),
    Magnet(x=170.0, y=85.0),
)


class MagnetSize(BaseModel):
    """Canonical body dimensions, preserved while corner poses fit the frame."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    length: float = Field(ge=8.0, le=80.0)
    thickness: float = Field(ge=4.0, le=24.0)


class MagneticFieldParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    width: float = Field(default=240.0, ge=40.0, le=300.0, title="Width (mm)")
    height: float = Field(default=170.0, ge=40.0, le=218.0, title="Height (mm)")
    density: int = Field(
        default=72, ge=24, le=100, title="Field density",
        description="Angular seed count around each magnetic pole",
    )
    style: Literal["continuous", "chains", "filings"] = Field(
        default="continuous", title="Mark treatment",
    )
    show_magnets: bool = Field(default=True, title="Show magnets")
    keep_silhouettes: bool = Field(
        default=True, title="Keep magnet silhouettes",
        description="Keep empty magnet-shaped gaps when the annotations are hidden",
    )
    remove_escaping: bool = Field(
        default=False, title="Remove escaping routes",
        description="Discard a complete route when either traced end meets the frame",
    )
    seed: int = Field(default=90826, ge=0, le=2_147_483_647, title="Seed")
    magnets: list[Magnet] = Field(
        default=list(DEFAULT_MAGNETS), max_length=16, title="Magnets",
        description="Bar magnets and independent north/south poles",
        json_schema_extra=_HIDDEN,
    )
    scatter_strength_min: float = Field(
        default=1.0, ge=0.1, le=3.0, json_schema_extra=_HIDDEN,
    )
    scatter_strength_max: float = Field(
        default=1.0, ge=0.1, le=3.0, json_schema_extra=_HIDDEN,
    )
    presets: list[list[Magnet] | None] = Field(
        default=[None, None, None, None], min_length=4, max_length=4,
        json_schema_extra=_HIDDEN,
    )
    preset_sizes: list[MagnetSize] | None = Field(
        default=None, max_length=16, json_schema_extra=_HIDDEN,
    )
    mix_x: float = Field(
        default=0.0, ge=0.0, le=1.0, json_schema_extra=_HIDDEN,
    )
    mix_y: float = Field(
        default=0.0, ge=0.0, le=1.0, json_schema_extra=_HIDDEN,
    )
    mix_active: bool = Field(default=False, json_schema_extra=_HIDDEN)
    pole_spacing: float = Field(
        default=0.0, ge=0.0, le=3.0, title="Pole spacing (mm)",
        description="Thin complete field routes that crowd together near a pole",
    )

    @model_validator(mode="after")
    def validate_recipe(self) -> "MagneticFieldParams":
        if self.scatter_strength_min > self.scatter_strength_max:
            raise ValueError("scatter strength minimum must not exceed maximum")
        if self.mix_active and any(preset is None for preset in self.presets):
            raise ValueError("active mixing requires all four presets")

        if self.preset_sizes is not None and len(self.preset_sizes) != len(self.magnets):
            raise ValueError("preset sizes must have the current magnet count")

        eps = 1e-9

        def check_fit(magnet: Magnet, label: str) -> None:
            if magnet.kind == "bar":
                angle = math.radians(magnet.rotation)
                c, s = abs(math.cos(angle)), abs(math.sin(angle))
                x_extent = c * magnet.length * 0.5 + s * magnet.thickness * 0.5
                y_extent = s * magnet.length * 0.5 + c * magnet.thickness * 0.5
            else:
                x_extent = y_extent = _POLE_BODY_RADIUS
            if (magnet.x - x_extent < -eps
                    or magnet.x + x_extent > self.width + eps
                    or magnet.y - y_extent < -eps
                    or magnet.y + y_extent > self.height + eps):
                raise ValueError(f"{label} body must stay inside the frame")

        for i, magnet in enumerate(self.magnets):
            check_fit(magnet, f"magnet {i}")
        for preset_index, preset in enumerate(self.presets):
            if preset is None:
                continue
            if len(preset) != len(self.magnets):
                raise ValueError(
                    f"preset {preset_index} must have the current magnet count"
                )
            for magnet_index, (current, captured) in enumerate(
                    zip(self.magnets, preset)):
                if (captured.kind, captured.flipped) != (current.kind, current.flipped):
                    raise ValueError(
                        f"preset {preset_index} magnet {magnet_index} kind and flipped "
                        "must match the current magnet"
                    )
                check_fit(captured, f"preset {preset_index} magnet {magnet_index}")
        return self


@dataclass(frozen=True)
class _BarGeometry:
    cx: float
    cy: float
    ux: float
    uy: float
    vx: float
    vy: float
    half_length: float
    half_thickness: float


@dataclass(frozen=True)
class _Scene:
    width: float
    height: float
    bars: tuple[_BarGeometry, ...]
    circles: tuple[tuple[float, float, float], ...]
    poles: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class _Trace:
    points: tuple[tuple[float, float], ...]
    termination: Literal["body", "boundary", "null", "turn", "loop", "step_limit"]


@dataclass(frozen=True)
class _Route:
    points: tuple[tuple[float, float], ...]
    touches_boundary: bool


def _scene(params: MagneticFieldParams) -> _Scene:
    bars: list[_BarGeometry] = []
    circles: list[tuple[float, float, float]] = []
    poles: list[tuple[float, float, float]] = []
    for magnet in params.magnets:
        charge = magnet.strength
        if magnet.kind == "bar":
            angle = math.radians(magnet.rotation)
            ux, uy = math.cos(angle), math.sin(angle)
            bar = _BarGeometry(
                magnet.x, magnet.y, ux, uy, -uy, ux,
                magnet.length * 0.5, magnet.thickness * 0.5,
            )
            bars.append(bar)
            negative_end_sign = -1.0 if magnet.flipped else 1.0
            poles.append((magnet.x - bar.half_length * ux,
                          magnet.y - bar.half_length * uy,
                          negative_end_sign * charge))
            poles.append((magnet.x + bar.half_length * ux,
                          magnet.y + bar.half_length * uy,
                          -negative_end_sign * charge))
        else:
            circles.append((magnet.x, magnet.y, _POLE_BODY_RADIUS))
            poles.append((magnet.x, magnet.y,
                          charge if magnet.kind == "north" else -charge))
    if not params.show_magnets and not params.keep_silhouettes:
        bars = []
        circles = [(x, y, _HIDDEN_POLE_CORE_RADIUS) for x, y, _ in poles]
    return _Scene(params.width, params.height, tuple(bars), tuple(circles), tuple(poles))


def _inside(x: float, y: float, scene: _Scene, padding: float = 0.0) -> bool:
    for bar in scene.bars:
        dx, dy = x - bar.cx, y - bar.cy
        if (abs(dx * bar.ux + dy * bar.uy) <= bar.half_length + padding
                and abs(dx * bar.vx + dy * bar.vy) <= bar.half_thickness + padding):
            return True
    return any((x - cx) ** 2 + (y - cy) ** 2 <= (radius + padding) ** 2
               for cx, cy, radius in scene.circles)


def _field(x: float, y: float, poles: tuple[tuple[float, float, float], ...]
           ) -> tuple[float, float] | None:
    bx = by = 0.0
    for px, py, charge in poles:
        dx, dy = x - px, y - py
        inv = charge / (dx * dx + dy * dy + _SOFTENING_SQ)
        bx += dx * inv
        by += dy * inv
    magnitude = math.hypot(bx, by)
    if magnitude <= 1e-9 or not math.isfinite(magnitude):
        return None
    return bx / magnitude, by / magnitude


def _trace(seed: tuple[float, float], direction: float, scene: _Scene) -> _Trace:
    x, y = seed
    points = [(x, y)]
    for _ in range(_TRACE_STEPS):
        vector = _field(x, y, scene.poles)
        if vector is None:
            return _Trace(tuple(points), "null")
        fx, fy = vector
        midx = x + direction * _STEP * 0.5 * fx
        midy = y + direction * _STEP * 0.5 * fy
        midpoint_vector = _field(midx, midy, scene.poles)
        if midpoint_vector is None:
            return _Trace(tuple(points), "null")
        mfx, mfy = midpoint_vector
        nextx = x + direction * _STEP * mfx
        nexty = y + direction * _STEP * mfy
        if not (math.isfinite(nextx) and math.isfinite(nexty)):
            return _Trace(tuple(points), "null")
        if _inside(nextx, nexty, scene, 0.18):
            return _Trace(tuple(points), "body")
        if not (0.0 <= nextx <= scene.width and 0.0 <= nexty <= scene.height):
            dx, dy = nextx - x, nexty - y
            fraction = 1.0
            if nextx < 0.0 and dx:
                fraction = min(fraction, -x / dx)
            elif nextx > scene.width and dx:
                fraction = min(fraction, (scene.width - x) / dx)
            if nexty < 0.0 and dy:
                fraction = min(fraction, -y / dy)
            elif nexty > scene.height and dy:
                fraction = min(fraction, (scene.height - y) / dy)
            endx = min(scene.width, max(0.0, x + fraction * dx))
            endy = min(scene.height, max(0.0, y + fraction * dy))
            if (endx, endy) != points[-1]:
                points.append((endx, endy))
            return _Trace(tuple(points), "boundary")
        if len(points) > 12:
            previous_x, previous_y = points[-2]
            if ((nextx - x) * (x - previous_x)
                    + (nexty - y) * (y - previous_y)) < 0.0:
                return _Trace(tuple(points), "turn")
        points.append((nextx, nexty))
        x, y = nextx, nexty
        if len(points) > 40:
            oldx, oldy = points[-30]
            if math.hypot(x - oldx, y - oldy) < _STEP * 2.0:
                return _Trace(tuple(points), "loop")
    return _Trace(tuple(points), "step_limit")


def _route_seeds(scene: _Scene, density: int, seed: int) -> list[tuple[float, float]]:
    rng = np.random.default_rng(seed)
    seeds: list[tuple[float, float]] = []
    for x, y, _ in scene.poles:
        for angle in np.linspace(0.0, 2.0 * math.pi, density, endpoint=False):
            varied = float(angle) + float(rng.normal(0.0, 0.006))
            sx, sy = x + 9.0 * math.cos(varied), y + 9.0 * math.sin(varied)
            if 0.0 <= sx <= scene.width and 0.0 <= sy <= scene.height:
                seeds.append((sx, sy))
    for x in np.arange(2.0, scene.width, 4.4):
        seeds.extend(((float(x), 0.02), (float(x), scene.height - 0.02)))
    for y in np.arange(2.0, scene.height, 4.4):
        seeds.extend(((0.02, float(y)), (scene.width - 0.02, float(y))))
    return seeds


def _trace_routes(scene: _Scene, density: int, seed: int) -> list[_Route]:
    seeds = _route_seeds(scene, density, seed)
    rows = int(scene.height / _OCCUPANCY_PITCH) + 2
    columns = int(scene.width / _OCCUPANCY_PITCH) + 2
    occupied = np.zeros((rows, columns), dtype=np.bool_)
    routes: list[_Route] = []
    output_points = 0
    for index, start in enumerate(seeds):
        if index % 32 == 0:
            report_progress(index / max(1, len(seeds)), "Tracing magnetic field")
        if _inside(*start, scene, 0.3):
            continue
        ix = min(columns - 1, max(0, int(start[0] / _OCCUPANCY_PITCH)))
        iy = min(rows - 1, max(0, int(start[1] / _OCCUPANCY_PITCH)))
        if occupied[iy, ix]:
            continue
        left = _trace(start, -1.0, scene)
        right = _trace(start, 1.0, scene)
        points = tuple(reversed(left.points[1:])) + right.points
        if len(points) < 18:
            continue
        cells = [(min(columns - 1, max(0, int(x / _OCCUPANCY_PITCH))),
                  min(rows - 1, max(0, int(y / _OCCUPANCY_PITCH))))
                 for x, y in points]
        if sum(bool(occupied[iy, ix]) for ix, iy in cells) / len(cells) > 0.42:
            continue
        if output_points + len(points) > _MAX_OUTPUT_POINTS:
            break
        for ix, iy in cells:
            occupied[iy, ix] = True
        routes.append(_Route(
            points=points,
            touches_boundary=(left.termination == "boundary"
                              or right.termination == "boundary"),
        ))
        output_points += len(points)
    report_progress(1.0, "Tracing magnetic field")
    return routes


def _thin_routes_near_poles(routes: list[_Route], scene: _Scene,
                            spacing: float) -> list[_Route]:
    """Greedily drop complete routes whose nearest pole approaches crowd.

    Each route contributes at most one sampled anchor per pole: its closest
    traced point within the fixed pole neighbourhood.  Accepted anchors occupy
    a small spatial hash, so later routes closer than ``spacing`` to one at the
    same pole are discarded whole.  Route order and points are left untouched.
    """
    if spacing <= 0.0 or not routes or not scene.poles:
        return routes

    zone_sq = _POLE_SPACING_ZONE_RADIUS**2
    spacing_sq = spacing**2
    cell_size = max(spacing, 1e-6)
    occupied: list[dict[tuple[int, int], list[tuple[float, float]]]] = [
        {} for _ in scene.poles
    ]
    kept: list[_Route] = []

    for route in routes:
        anchors: list[tuple[int, float, float]] = []
        for pole_index, (pole_x, pole_y, _) in enumerate(scene.poles):
            anchor_x, anchor_y = min(
                route.points,
                key=lambda point: ((point[0] - pole_x) ** 2
                                   + (point[1] - pole_y) ** 2),
            )
            distance_sq = (anchor_x - pole_x) ** 2 + (anchor_y - pole_y) ** 2
            if distance_sq <= zone_sq:
                anchors.append((pole_index, anchor_x, anchor_y))

        crowded = False
        for pole_index, anchor_x, anchor_y in anchors:
            cell_x = math.floor(anchor_x / cell_size)
            cell_y = math.floor(anchor_y / cell_size)
            pole_cells = occupied[pole_index]
            for offset_x in (-1, 0, 1):
                for offset_y in (-1, 0, 1):
                    for prior_x, prior_y in pole_cells.get(
                            (cell_x + offset_x, cell_y + offset_y), ()):
                        if ((anchor_x - prior_x) ** 2 + (anchor_y - prior_y) ** 2
                                < spacing_sq):
                            crowded = True
                            break
                    if crowded:
                        break
                if crowded:
                    break
            if crowded:
                break
        if crowded:
            continue

        kept.append(route)
        for pole_index, anchor_x, anchor_y in anchors:
            cell = (math.floor(anchor_x / cell_size),
                    math.floor(anchor_y / cell_size))
            occupied[pole_index].setdefault(cell, []).append((anchor_x, anchor_y))
    return kept


def _portion(path: np.ndarray, arc: np.ndarray, start: float, end: float) -> np.ndarray:
    keep = (arc > start) & (arc < end)
    ends = np.asarray([
        [np.interp(position, arc, path[:, axis]) for axis in (0, 1)]
        for position in (start, end)
    ])
    return np.vstack((ends[0], path[keep], ends[1]))


def _texture(routes: list[_Route], style: Literal["continuous", "chains", "filings"],
             scene: _Scene, seed: int) -> list[tuple[tuple[float, float], ...]]:
    if style == "continuous":
        return [route.points for route in routes]
    style_number = 1 if style == "chains" else 2
    rng = np.random.default_rng(seed + style_number)
    marks: list[tuple[tuple[float, float], ...]] = []
    for route_index, route in enumerate(routes):
        path = np.asarray(route.points, dtype=float)
        arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
        total = float(arc[-1])
        position = float(rng.uniform(0.0, 1.8))
        while position < total - 0.15:
            x = float(np.interp(position, arc, path[:, 0]))
            y = float(np.interp(position, arc, path[:, 1]))
            patch = (math.sin(x * 0.072 + y * 0.043)
                     + math.sin(y * 0.119 - x * 0.028) + 2.0) / 4.0
            if style == "chains":
                length = float(rng.uniform(0.28, 1.8)) * (0.55 + patch * 1.3)
                gap = float(rng.uniform(0.18, 0.95)) * (1.35 - patch * 0.7)
                if rng.random() < 0.045:
                    length *= 3.8
                mark = _portion(path, arc, position, min(total, position + length))
                delta = mark[-1] - mark[0]
                norm = float(np.linalg.norm(delta))
                if norm > 0.0:
                    normal = np.asarray((-delta[1], delta[0])) / norm
                    shift = (0.09 * math.sin(position * 0.65 + route_index * 1.7)
                             + float(rng.normal(0.0, 0.045)))
                    mark += normal * shift
            else:
                length = float(rng.uniform(0.32, 1.32)) * (0.8 + patch * 0.8)
                gap = float(rng.uniform(0.6, 1.9))
                mark = _portion(path, arc, position, min(total, position + length))
                delta = mark[-1] - mark[0]
                norm = float(np.linalg.norm(delta))
                if norm > 0.0:
                    normal = np.asarray((-delta[1], delta[0])) / norm
                    mark += normal * float(rng.normal(0.0, 0.58))
                    theta = float(rng.normal(0.0, 0.13))
                    cosine, sine = math.cos(theta), math.sin(theta)
                    rotation = np.asarray(((cosine, -sine), (sine, cosine)))
                    center = mark.mean(axis=0)
                    mark = (mark - center) @ rotation.T + center
            mark[:, 0] = np.clip(mark[:, 0], 0.0, scene.width)
            mark[:, 1] = np.clip(mark[:, 1], 0.0, scene.height)
            if (not any(_inside(float(px), float(py), scene, 0.12) for px, py in mark)
                    and float(np.linalg.norm(np.diff(mark, axis=0), axis=1).sum()) > 0.08):
                marks.append(tuple((float(px), float(py)) for px, py in mark))
            position += length + gap
    return marks


def _glyph(letter: Literal["N", "S"], x: float, y: float, *,
           ux: float = 1.0, uy: float = 0.0, vx: float = 0.0, vy: float = 1.0,
           half_width: float = 1.6, half_height: float = 2.5,
           ) -> list[tuple[tuple[float, float], ...]]:
    def world(local_x: float, local_y: float) -> tuple[float, float]:
        return (x + local_x * ux + local_y * vx,
                y + local_x * uy + local_y * vy)

    if letter == "N":
        local = [((-1.0, 1.0), (-1.0, -1.0)),
                 ((-1.0, -1.0), (1.0, 1.0)),
                 ((1.0, 1.0), (1.0, -1.0))]
    else:
        local = [((1.0, -1.0), (-0.44, -1.0), (-1.0, -0.56),
                  (-1.0, -0.16), (1.0, 0.16), (1.0, 0.56),
                  (0.44, 1.0), (-1.0, 1.0))]
    return [tuple(world(px * half_width, py * half_height) for px, py in stroke)
            for stroke in local]


def _annotations(params: MagneticFieldParams) -> list[Path]:
    paths: list[Path] = []

    def add(points: list[tuple[float, float]]) -> None:
        clipped: list[tuple[float, float]] = []
        for x, y in points:
            point = (min(params.width, max(0.0, x)),
                     min(params.height, max(0.0, y)))
            if not clipped or point != clipped[-1]:
                clipped.append(point)
        if len(clipped) >= 2 and any(a != b for a, b in zip(clipped, clipped[1:])):
            paths.append(Path(points=clipped, filled=False))

    for magnet in params.magnets:
        if magnet.kind == "bar":
            angle = math.radians(magnet.rotation)
            ux, uy = math.cos(angle), math.sin(angle)
            vx, vy = -uy, ux
            half_l, half_t = magnet.length * 0.5, magnet.thickness * 0.5
            corners = [
                (magnet.x + su * half_l * ux + sv * half_t * vx,
                 magnet.y + su * half_l * uy + sv * half_t * vy)
                for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))
            ]
            add(corners + [corners[0]])
            negative_letter: Literal["N", "S"] = "S" if magnet.flipped else "N"
            positive_letter: Literal["N", "S"] = "N" if magnet.flipped else "S"
            label_offset = min(17.0, half_l * 0.65)
            glyph_half_width = min(1.6, max(0.5, half_l - label_offset - 0.4))
            glyph_half_height = min(2.5, max(0.5, half_t - 0.4))
            for sign, letter in ((-1.0, negative_letter), (1.0, positive_letter)):
                label_x = magnet.x + sign * label_offset * ux
                label_y = magnet.y + sign * label_offset * uy
                for stroke in _glyph(
                    letter, label_x, label_y, ux=ux, uy=uy, vx=vx, vy=vy,
                    half_width=glyph_half_width, half_height=glyph_half_height,
                ):
                    add(list(stroke))
        else:
            outline = [
                (magnet.x + _POLE_BODY_RADIUS * math.cos(i * 2.0 * math.pi / 24.0),
                 magnet.y + _POLE_BODY_RADIUS * math.sin(i * 2.0 * math.pi / 24.0))
                for i in range(24)
            ]
            add(outline + [outline[0]])
            letter: Literal["N", "S"] = "N" if magnet.kind == "north" else "S"
            for stroke in _glyph(letter, magnet.x, magnet.y):
                add(list(stroke))
    return paths


@register_source
class MagneticFieldSource(SourceModule):
    id = "magnetic_field"
    label = "Magnetic field"
    description = ("Illustrative pole-field routes as continuous curves, irregular "
                   "chains or loose filings")
    orientation = "geometry"
    bench = {"adapter": "magnetic-field", "version": 1,
             "modes": ["new", "resume"]}
    Params = MagneticFieldParams

    def placement_frame(self, params: dict) -> tuple[float, float] | None:
        return float(params.get("width", 240.0)), float(params.get("height", 170.0))

    def generate(self, params: MagneticFieldParams) -> PathDocument:
        if not params.magnets:
            return PathDocument(layers=[], width=params.width, height=params.height,
                                source="magnetic_field (empty)")
        scene = _scene(params)
        routes = _trace_routes(scene, params.density, params.seed)
        if params.remove_escaping:
            routes = [route for route in routes if not route.touches_boundary]
        routes = _thin_routes_near_poles(routes, scene, params.pole_spacing)
        marks = _texture(routes, params.style, scene, params.seed)
        layers: list[Layer] = []
        if marks:
            layers.append(Layer(
                id=1, name="Magnetic field", color="#100f0f",
                paths=[Path(points=list(mark), filled=False) for mark in marks],
            ))
        if params.show_magnets:
            annotations = _annotations(params)
            if annotations:
                layers.append(Layer(id=2, name="Magnets", color="#100f0f",
                                    paths=annotations))
        return PathDocument(
            layers=layers, width=params.width, height=params.height,
            source=f"magnetic_field {params.style} ({len(params.magnets)} magnets)",
        )
