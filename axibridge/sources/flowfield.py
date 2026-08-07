"""Flow field: evenly-spaced streamlines traced through a smooth noise field
(Jobard & Lefer 1997). The signature generative-plotter texture — hair, water,
wind — and a torture test for the planner's cornering on long smooth curves.

Spacing is enforced with an occupancy grid: a streamline dies when it comes
within ``separation/2`` of any previously traced line, so density stays even
at any wavelength. Tracing is bidirectional RK2 from seeds laid on a coarse
lattice; the field angle is fractal value noise (reused from the coherent
jitter effect — same lattice hash, so fields are seed-stable).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ..effects.coherent_jitter import _fbm
from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source

_MAX_POINTS = 400_000  # hard output cap: keep resolve interactive


class FlowFieldParams(BaseModel):
    width: float = Field(default=200, ge=10, le=400, title="Width (mm)")
    height: float = Field(default=150, ge=10, le=400, title="Height (mm)")
    separation: float = Field(default=2.5, ge=0.5, le=20.0, title="Line separation (mm)",
                              description="Streamlines keep at least half this distance apart")
    wavelength: float = Field(default=60.0, ge=5.0, le=400.0, title="Wavelength (mm)",
                              description="Size of the swirls — bigger = lazier flow")
    detail: int = Field(default=2, ge=1, le=4, title="Detail (octaves)")
    swirl: float = Field(default=1.0, ge=0.25, le=3.0, title="Swirl",
                         description="How many half-turns the field angle sweeps across the noise range")
    step: float = Field(default=0.8, ge=0.2, le=5.0, title="Trace step (mm)")
    max_length: float = Field(default=400.0, ge=10.0, le=2000.0, title="Max line length (mm)")
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")
    margin: float = Field(default=15, ge=0, le=100, title="Margin (mm)")


class _SpacingGrid:
    """Occupancy hash for the even-spacing test (cell size = test radius)."""

    def __init__(self, radius: float) -> None:
        self.r2 = radius * radius
        self.cell = radius
        self.cells: dict[tuple[int, int], list[tuple[float, float]]] = {}

    def _key(self, x: float, y: float) -> tuple[int, int]:
        return (int(x // self.cell), int(y // self.cell))

    def too_close(self, x: float, y: float) -> bool:
        kx, ky = self._key(x, y)
        for i in (kx - 1, kx, kx + 1):
            for j in (ky - 1, ky, ky + 1):
                for px, py in self.cells.get((i, j), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < self.r2:
                        return True
        return False

    def add(self, x: float, y: float) -> None:
        self.cells.setdefault(self._key(x, y), []).append((x, y))


@register_source
class FlowField(SourceModule):
    id = "flowfield"
    orientation = "geometry"  # a width x height field of streamlines: 'width' should mean the width you see
    label = "Flow field"
    description = "Evenly-spaced streamlines through fractal noise — hair, water, wind."
    Params = FlowFieldParams

    def generate(self, params: FlowFieldParams) -> PathDocument:
        p = params
        seed = (p.seed * 31 + 9176) & 0x7FFFFFFF
        inv_wl = 1.0 / p.wavelength

        def angle(x: float, y: float) -> float:
            return p.swirl * math.pi * _fbm(x * inv_wl, y * inv_wl, seed, p.detail)

        grid = _SpacingGrid(p.separation * 0.5)
        inside = lambda x, y: 0 <= x <= p.width and 0 <= y <= p.height  # noqa: E731
        max_steps = int(p.max_length / p.step)

        def trace(sx: float, sy: float, direction: float) -> list[tuple[float, float]]:
            pts: list[tuple[float, float]] = []
            x, y = sx, sy
            for _ in range(max_steps):
                a = angle(x, y)
                # RK2 midpoint: sample the field half a step ahead
                mx = x + direction * 0.5 * p.step * math.cos(a)
                my = y + direction * 0.5 * p.step * math.sin(a)
                a = angle(mx, my)
                x += direction * p.step * math.cos(a)
                y += direction * p.step * math.sin(a)
                if not inside(x, y) or grid.too_close(x, y):
                    break
                pts.append((x, y))
            return pts

        paths: list[Path] = []
        total = 0
        # seed lattice at `separation`, center outward for nicer long lines
        nx = max(int(p.width / p.separation), 1)
        ny = max(int(p.height / p.separation), 1)
        seeds = sorted(
            ((i + 0.5) * p.width / nx, (j + 0.5) * p.height / ny)
            for i in range(nx) for j in range(ny)
        )
        seeds.sort(key=lambda s: (s[0] - p.width / 2) ** 2 + (s[1] - p.height / 2) ** 2)
        for sx, sy in seeds:
            if total >= _MAX_POINTS:
                break
            if grid.too_close(sx, sy):
                continue
            back = trace(sx, sy, -1.0)
            fwd = trace(sx, sy, +1.0)
            pts = back[::-1] + [(sx, sy)] + fwd
            if len(pts) < 4 or (len(pts) - 1) * p.step < p.separation * 2:
                continue  # stubs shorter than ~2 separations just look like noise
            for x, y in pts:
                grid.add(x, y)
            total += len(pts)
            paths.append(Path(points=[(x + p.margin, y + p.margin) for x, y in pts]))

        return PathDocument(
            layers=[Layer(id=1, name="flow field", color="#1a3a5c", paths=paths)],
            width=p.width + 2 * p.margin,
            height=p.height + 2 * p.margin,
            source=f"flowfield seed={p.seed}",
        )
