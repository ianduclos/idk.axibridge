"""Linedraw (plotterfun, after lingdong's linedraw.py): sketch-style portrait
— Sobel edge contours plus multi-density hatching, roughened with perlin
noise. The algorithm autocontrasts first, then applies the shared image-
processing controls so brightness/contrast still visibly steer the drawing.

The heaviest generator in the set (full-image Sobel + contour linking); it
reports progress per stage, which is what the generate load bar is for.
"""

from __future__ import annotations

import math
import random

from pydantic import Field

from ..image_processing import (
    IMAGE_PROCESSING_GROUP,
    apply_image_processing_byte,
    image_processing_kwargs,
)
from ..model import PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageBaseParams, luma_grid, pixel_doc
from ._pixelgen import working_dims as _pixelgen_working_dims

Pt = tuple[float, float]

_IMAGE_PROCESSING = IMAGE_PROCESSING_GROUP


class LinedrawParams(ImageBaseParams):
    contours: bool = Field(default=True, title="Contours")
    contour_detail: int = Field(default=8, ge=1, le=16, title="Contour detail",
                                description="Stroke granularity in working px — smaller is finer")
    hatching: bool = Field(default=True, title="Hatching")
    hatch_scale: int = Field(default=8, ge=1, le=24, title="Hatch scale (px)")
    noise_scale: float = Field(default=1, ge=0, le=2, title="Noise scale",
                               description="Hand-drawn wobble on every stroke")
    seed: int = Field(default=0, ge=0, le=9999, title="Seed")
    resolution: float = Field(default=1.0, ge=1.0, le=2.0, title="Resolution ×",
                              description="Working-canvas multiplier — finer detail, slower")
    invert: bool = Field(default=False, title="Invert",
                         description="Draw the light areas instead",
                         json_schema_extra=_IMAGE_PROCESSING)
    brightness: float = Field(default=0.0, ge=-100.0, le=100.0, title="Brightness",
                              json_schema_extra=_IMAGE_PROCESSING)
    contrast: float = Field(default=0.0, ge=-100.0, le=100.0, title="Contrast",
                            json_schema_extra=_IMAGE_PROCESSING)
    gamma: float = Field(default=1.0, ge=0.1, le=5.0, title="Gamma",
                         json_schema_extra=_IMAGE_PROCESSING)
    black_point: float = Field(default=0.0, ge=0.0, le=1.0, title="Black point",
                               json_schema_extra=_IMAGE_PROCESSING)
    white_point: float = Field(default=1.0, ge=0.0, le=1.0, title="White point",
                               json_schema_extra=_IMAGE_PROCESSING)


class _Perlin:
    """p5-style gradient-free perlin (ported from plotterfun's helpers.js)."""

    _SIZE = 4095

    def __init__(self, rng: random.Random):
        self.t = [rng.random() for _ in range(self._SIZE + 1)]

    def __call__(self, x: float, y: float = 0.0, z: float = 1.0) -> float:
        x, y, z = abs(x), abs(y), abs(z)
        xi, yi, zi = int(x), int(y), int(z)
        xf, yf, zf = x - xi, y - yi, z - zi
        r, ampl = 0.0, 0.5
        cos_half = lambda i: 0.5 * (1.0 - math.cos(i * math.pi))
        t = self.t
        for _ in range(4):
            of = xi + (yi << 4) + (zi << 8)
            rxf, ryf = cos_half(xf), cos_half(yf)
            n1 = t[of & self._SIZE]
            n1 += rxf * (t[(of + 1) & self._SIZE] - n1)
            n2 = t[(of + 16) & self._SIZE]
            n2 += rxf * (t[(of + 17) & self._SIZE] - n2)
            n1 += ryf * (n2 - n1)
            of += 256
            n2 = t[of & self._SIZE]
            n2 += rxf * (t[(of + 1) & self._SIZE] - n2)
            n3 = t[(of + 16) & self._SIZE]
            n3 += rxf * (t[(of + 17) & self._SIZE] - n3)
            n2 += ryf * (n3 - n2)
            n1 += cos_half(zf) * (n2 - n1)
            r += n1 * ampl
            ampl *= 0.5
            xi, xf = xi << 1, xf * 2
            yi, yf = yi << 1, yf * 2
            zi, zf = zi << 1, zf * 2
            if xf >= 1.0:
                xi, xf = xi + 1, xf - 1
            if yf >= 1.0:
                yi, yf = yi + 1, yf - 1
            if zf >= 1.0:
                zi, zf = zi + 1, zf - 1
        return r


def _autocontrast(rows: list[list[float]], w: int, h: int, cutoff: float) -> list[list[float]]:
    """Column-major stretched-luma cache, like plotterfun's autocontrast."""
    hist = [0] * 256
    for row in rows:
        for v in row:
            hist[min(int(v + 0.5), 255)] += 1
    cut = cutoff * w * h
    low, acc = 0, 0
    for i in range(255):
        acc += hist[i]
        if acc > cut:
            low = i
            break
    high, acc = 255, 255  # the original seeds the accumulator at 255; kept
    for i in range(255, 1, -1):
        acc += hist[i]
        if acc >= cut:
            high = i
            break
    scale = 255 / (high - low) if high != low else 1.0
    return [[min(255.0, max(0.0, (rows[y][x] - low) * scale)) for y in range(h)]
            for x in range(w)]


def _sobel(cols: list[list[float]], w: int, h: int) -> list[list[int]]:
    """Binary edge map, column-major; out-of-bounds samples read as 0."""
    def g(x: int, y: int) -> float:
        return cols[x][y] if 0 <= x < w and 0 <= y < h else 0.0

    edges = [[0] * h for _ in range(w)]
    for x in range(w):
        if x % 64 == 0:
            report_progress(0.05 + 0.25 * x / w, "Edge finding")
        for y in range(h):
            px = (-g(x - 1, y - 1) + g(x + 1, y - 1) - 2 * g(x - 1, y)
                  + 2 * g(x + 1, y) - g(x - 1, y + 1) + g(x + 1, y + 1))
            py = (-g(x - 1, y - 1) - 2 * g(x, y - 1) - g(x + 1, y - 1)
                  + g(x - 1, y + 1) + 2 * g(x, y + 1) + g(x + 1, y + 1))
            if px * px + py * py > 128 * 128:
                edges[x][y] = 255
    return edges


def _get_dots(edges: list[list[int]], w: int, h: int, vertical: bool) -> list[list[int]]:
    """Midpoints of edge runs per scan position (rows for V, columns for H)."""
    dots: list[list[int]] = []
    outer, inner = (h - 1, w) if vertical else (w - 1, h)
    for s in range(outer):
        row: list[int] = []
        i = 1
        while i < inner:
            on = edges[i][s] if vertical else edges[s][i]
            if on == 255:
                i0 = i
                while i < inner and (edges[i][s] if vertical else edges[s][i]) == 255:
                    i += 1
                row.append(round((i + i0) / 2))
            else:
                i += 1
        dots.append(row)
    return dots


def _connect_dots(dots: list[list[int]], vertical: bool) -> list[list[Pt]]:
    """Chain dots across scan positions into contours (nearest within 3 px).
    The original scans every contour per dot; an end-point index replaces
    that O(dots x contours) search with a dict lookup."""
    contours: list[list[Pt]] = []
    open_ends: dict[tuple[int, int], int] = {}  # (scan_pos, crossing) -> contour idx
    last_s = len(dots) - 1
    for s, row in enumerate(dots):
        prev = dots[s - 1] if s > 0 else []
        for c in row:
            closest, cdist = -1, 10000
            for c0 in prev:
                d = abs(c - c0)
                if d < cdist:
                    closest, cdist = c0, d
            pt: Pt = (float(c), float(s)) if vertical else (float(s), float(c))
            idx = open_ends.get((s - 1, closest)) if cdist <= 3 else None
            if idx is None:
                contours.append([pt])
                idx = len(contours) - 1
            else:
                contours[idx].append(pt)
            open_ends[(s, c)] = idx
    # stubs that stalled >1 step with <4 points could never be extended again
    # (the original prunes them every row); dropping them at the end is the same
    def alive(c: list[Pt]) -> bool:
        end = c[-1][1] if vertical else c[-1][0]
        return len(c) >= 4 or end >= last_s - 1
    return [c for c in contours if alive(c)]


def _hatch(cols: list[list[float]], w: int, h: int, sc: int) -> list[list[Pt]]:
    def g(x: int, y: int) -> float:
        return cols[x][y] if 0 <= x < w and 0 <= y < h else 0.0

    lines: list[list[Pt]] = []

    def run(points, limit):
        pendown = False
        for x, y in points:
            if g(x, y) <= limit:
                if not pendown:
                    lines.append([(float(x), float(y))])
                else:
                    lines[-1].append((float(x), float(y)))
                pendown = True
            else:
                pendown = False

    for y in range(0, h, sc):                                   # horizontal, mid grey
        run(((x, y) for x in range(0, w, sc)), 144)
    for y in range(round(sc / 2), h, sc):                       # denser horizontal
        run(((x, y) for x in range(0, w, sc)), 64)
    for sy in range(0, h, sc):                                  # diagonal, darkest
        run(zip(range(0, w, sc), range(sy, 0, -sc)), 16)
    for sx in range(0, w, sc):
        run(zip(range(sx, w, sc), range(h, 0, -sc)), 16)
    return lines


@register_source
class Linedraw(SourceModule):
    id = "linedraw"
    label = "Linedraw (sketch)"
    description = "Sketch portrait: edge contours + multi-density hatching with perlin wobble."
    Params = LinedrawParams

    def generate(self, params: LinedrawParams) -> PathDocument:
        p = params
        if not p.contours and not p.hatching:
            raise ValueError("enable contours, hatching, or both")
        # px-space params keep their working-canvas meaning at any resolution:
        # everything calibrated in px is multiplied by the same factor the
        # canvas grew by (luma_grid caps the actual size, so derive k from it)
        rows, w, h = luma_grid(p, scale=p.resolution)
        base_w, _ = _pixelgen_working_dims(p)
        k = w / base_w
        report_progress(0.02, "Autocontrast")
        cols = _autocontrast(rows, w, h, 0.1)
        tone = image_processing_kwargs(p)
        cols = [[apply_image_processing_byte(v, **tone) for v in col] for col in cols]
        if p.invert:
            cols = [[255.0 - v for v in col] for col in cols]
        noise = _Perlin(random.Random(p.seed))

        def add_noise(lines: list[list[Pt]], sc: float) -> list[list[Pt]]:
            sc *= p.noise_scale
            return [[(x + sc * noise(i * 0.5, j * 0.1), y + sc * noise(i * 0.5, j * 0.1))
                     for j, (x, y) in enumerate(line)]
                    for i, line in enumerate(lines)]

        output: list[list[Pt]] = []
        if p.contours:
            edges = _sobel(cols, w, h)
            report_progress(0.35, "Tracing contours")
            contours = _connect_dots(_get_dots(edges, w, h, False), False)
            contours += _connect_dots(_get_dots(edges, w, h, True), True)
            report_progress(0.5, "Linking strokes")
            sc = max(1, round(p.contour_detail * k))
            for i in range(len(contours)):          # join ends closer than the stroke scale
                if not contours[i]:
                    continue
                for j in range(len(contours)):
                    if i == j or not contours[j]:
                        continue
                    ex, ey = contours[i][-1]
                    sx, sy = contours[j][0]
                    if math.hypot(ex - sx, ey - sy) < sc:
                        contours[i] = contours[i] + contours[j]
                        contours[j] = []
            simplified = [c[::sc] for c in contours if c]
            output += add_noise([c for c in simplified if c], 10 * k)
        if p.hatching:
            report_progress(0.7, "Hatching")
            hatch_sc = max(1, round(p.hatch_scale * k))
            output += add_noise(_hatch(cols, w, h, hatch_sc), hatch_sc)

        report_progress(0.95, "Building paths")
        return pixel_doc(p, w, h, output, "linedraw", f"linedraw {p.image}")
