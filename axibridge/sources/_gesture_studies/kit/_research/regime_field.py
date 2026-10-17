# FROZEN from research commit 529a195: tools/gesture/gesture/regime_field.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Regime fields r(x, y) ∈ [0, 2] over a sheet, hand fields, and the
composition pipeline that turns structure + fields into plotter polylines.

docs/IDEAS-gesture-bank.md, "Direction: three regimes that become one another
in space": the regime (0 = line, 1 = nib, 2 = shape) is a property of WHERE a
line is, not of what kind of mark it is. results/regime-field-2026-10-16.md.

Coordinates. A field is evaluated on *unit sheet coordinates* u = (x / W,
y / H) ∈ [0, 1]², y down (image convention). Points outside the sheet are
clamped. Every field is deterministic in its seed and never mutates inputs.

Field families
  authored   `axis`, `bands`, `margins`, `radial`
  structure  `structure_field(drawing, mode=...)`: "strahler" / "order" (tree
             depth: trunk → shape, branches → nib, twigs → line), "density"
             (ink density), "trunk" (distance to the main axis line)
  procedural `noise_fronts`: smooth noise through soft thresholds whose bleed
             itself varies over the sheet (fronts both gradual and abrupt)
  mixed      `mix`, `maximum`, `minimum`, `offset`, `scale`, `warp` (domain
             warp: wobbly fronts), `levels` (re-quantise a field)

Hand fields (`HandField`): soft weights over named hands per position
(`hand_zones` = soft Voronoi on noise, `hand_bands`, `hand_by_field`). A line
crossing a zone border is split into runs per hand (with hysteresis and
stochastic code-switching inside the bleed) and each run is restyled in its
hand; overlapping runs are cross-faded, so the line stays one line.

compose(seed, size, structure=..., field=..., hands=..., signs=...) →
`Composition` (polylines in px; `drawing()` for composite.to_svg).

Regime rendering uses `gesture.regime` (RegimeStroke, from_field, render)
and `gesture.signs.place_signs` when those modules exist; otherwise the
minimal stand-in here (`StandInStroke`, `standin_render`, `standin_signs`)
with the same interface. `engine="standin"` forces the stand-in.
"""
from __future__ import annotations

import importlib
import inspect
import math
import warnings
from dataclasses import dataclass, field as dc_field
from typing import Callable, Sequence

import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d, map_coordinates

from .core import Drawing, Stroke

R_MAX = 2.0
GRID = 160                    # field raster resolution (long side)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _soft_levels(d: np.ndarray, edges: Sequence[float], values: Sequence[float], bleed) -> np.ndarray:
    """Piecewise-constant values[i] between edges, each step a smoothstep of
    width `bleed` (scalar or array like d) centred on the edge. bleed → 0 is a
    hard front."""
    values = list(values)
    assert len(values) == len(edges) + 1
    out = np.full(np.shape(d), float(values[0]))
    b = np.maximum(np.asarray(bleed, float), 1e-6)
    for e, v0, v1 in zip(edges, values[:-1], values[1:]):
        out = out + (v1 - v0) * smoothstep((d - e) / b + 0.5)
    return out


def _unit(u) -> np.ndarray:
    u = np.asarray(u, dtype=np.float64)
    if u.ndim == 1:
        u = u[None, :]
    return np.clip(u, 0.0, 1.0)


def _noise_grid(seed, shape, sigma: float) -> np.ndarray:
    """Smooth Gaussian noise on a grid, zero mean, unit sd. sigma in cells."""
    rng = np.random.default_rng(seed)
    pad = int(3 * sigma) + 2
    n = rng.standard_normal((shape[0] + 2 * pad, shape[1] + 2 * pad))
    n = gaussian_filter(n, sigma, mode="wrap")[pad:pad + shape[0], pad:pad + shape[1]]
    n = n - n.mean()
    return n / max(float(n.std()), 1e-12)


def _noise_1d(seed, n: int, sigma: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = gaussian_filter1d(rng.standard_normal(n + 6 * int(sigma) + 4), sigma, mode="nearest")
    x = x[3 * int(sigma) + 2:3 * int(sigma) + 2 + n]
    return (x - x.mean()) / max(float(x.std()), 1e-12)


# ---------------------------------------------------------------------------
# the Field type
# ---------------------------------------------------------------------------

class Field:
    """r(u) ∈ [0, 2] on unit sheet coordinates (N, 2) → (N,). `aspect` =
    H / W of the sheet the field was authored for (distances are measured
    in units of the sheet width, so circles stay round)."""

    name = "field"

    def __init__(self, fn: Callable[[np.ndarray], np.ndarray], name: str = "field", aspect: float = 1.0,
                 meta: dict | None = None):
        self._fn = fn
        self.name = name
        self.aspect = float(aspect)
        self.meta = dict(meta or {})

    def __call__(self, u) -> np.ndarray:
        r = np.asarray(self._fn(_unit(u)), dtype=np.float64)
        return np.clip(np.nan_to_num(r, nan=0.0), 0.0, R_MAX)

    def at_px(self, points, size) -> np.ndarray:
        """Evaluate at pixel points (x, y) on a sheet of `size` = (W, H)."""
        W, H = size
        p = np.asarray(points, dtype=np.float64)
        return self(p / np.array([W, H], float))

    def raster(self, shape=(GRID, GRID)) -> np.ndarray:
        """The field on a (rows, cols) grid over the unit sheet (for figures)."""
        ys, xs = np.mgrid[0:shape[0], 0:shape[1]]
        u = np.column_stack([(xs.ravel() + 0.5) / shape[1], (ys.ravel() + 0.5) / shape[0]])
        return self(u).reshape(shape)

    def __repr__(self):
        return f"Field({self.name})"


class GridField(Field):
    """A field stored as a raster over the unit sheet, bilinear lookup."""

    def __init__(self, grid: np.ndarray, name: str = "grid", aspect: float = 1.0, meta: dict | None = None):
        g = np.clip(np.asarray(grid, float), 0.0, R_MAX)
        self.grid = g

        def fn(u):
            rows, cols = g.shape
            return map_coordinates(g, [u[:, 1] * rows - 0.5, u[:, 0] * cols - 0.5], order=1, mode="nearest")

        super().__init__(fn, name, aspect, meta)


def _grid_shape(aspect: float, n: int = GRID) -> tuple[int, int]:
    """(rows, cols) with the long side n for a sheet of H/W = aspect."""
    if aspect >= 1:
        return n, max(int(round(n / aspect)), 8)
    return max(int(round(n * aspect)), 8), n


def constant(r: float) -> Field:
    return Field(lambda u: np.full(len(u), float(r)), f"const{r:g}")


# ---------------------------------------------------------------------------
# authored families
# ---------------------------------------------------------------------------

def axis(x: float = 0.62, *, core: float = 0.035, band: float = 0.09, bleed: float = 0.04, tilt: float = 0.0,
         wobble: float = 0.025, seed: int = 0, aspect: float = 1.0, values=(0.0, 1.0, 2.0),
         taper: float = 0.0) -> Field:
    """A vertical (tilted, wobbling) axis: shape on the axis (within `core`),
    nib in a band around it (within `band`), line beyond. Distances in sheet
    widths. taper > 0 thins the axis toward the top (y = 0) like a trunk."""
    wob = _noise_1d(seed, 256, 18.0) * wobble
    far, mid, near = values

    def fn(u):
        yy = u[:, 1]
        xa = x + tilt * (yy - 0.5) + np.interp(yy, np.linspace(0, 1, 256), wob)
        d = np.abs(u[:, 0] - xa)
        k = 1.0 - taper * (1.0 - yy)
        return _soft_levels(-d, [-band * k, -core * k], [far, mid, near], bleed)

    return Field(fn, f"axis(x={x:g})", aspect, {"family": "authored", "x": x})


def bands(edges=(0.3, 0.55, 0.8), values=(0.0, 1.2, 0.2, 1.8), *, along: str = "y", bleed: float = 0.03,
          wobble: float = 0.03, seed: int = 0, aspect: float = 1.0) -> Field:
    """Bands across the sheet (along "y": horizontal bands stacked down the
    sheet), each front wobbling by smooth noise."""
    wob = [_noise_1d((seed, i), 256, 20.0) * wobble for i in range(len(edges))]
    t = np.linspace(0, 1, 256)

    def fn(u):
        c, o = (u[:, 1], u[:, 0]) if along == "y" else (u[:, 0], u[:, 1])
        out = np.full(len(u), float(values[0]))
        for i, (e, v0, v1) in enumerate(zip(edges, values[:-1], values[1:])):
            ee = e + np.interp(o, t, wob[i])
            out = out + (v1 - v0) * smoothstep((c - ee) / max(bleed, 1e-6) + 0.5)
        return out

    return Field(fn, f"bands({along})", aspect, {"family": "authored"})


def margins(inset: float = 0.13, *, sides: str = "lrtb", margin_value: float = 1.0, inner_value: float = 0.0,
            bleed: float = 0.04, wobble: float = 0.02, seed: int = 0, aspect: float = 1.0) -> Field:
    """Margin zones (script-like nib along the chosen sides), inner value inside."""
    wob = _noise_1d(seed, 256, 16.0) * wobble
    t = np.linspace(0, 1, 256)

    def fn(u):
        ds = []
        if "l" in sides:
            ds.append(u[:, 0] - np.interp(u[:, 1], t, wob))
        if "r" in sides:
            ds.append(1 - u[:, 0] + np.interp(u[:, 1], t, wob))
        if "t" in sides:
            ds.append((u[:, 1] - np.interp(u[:, 0], t, wob)) * aspect)
        if "b" in sides:
            ds.append((1 - u[:, 1] + np.interp(u[:, 0], t, wob)) * aspect)
        d = np.min(np.vstack(ds), axis=0)
        return _soft_levels(d, [inset], [margin_value, inner_value], bleed)

    return Field(fn, f"margins({sides})", aspect, {"family": "authored"})


def radial(centre=(0.5, 0.45), radii=(0.12, 0.3), values=(2.0, 1.0, 0.0), *, bleed: float = 0.05,
           aspect: float = 1.0, lobes: int = 0, lobe_amp: float = 0.0, seed: int = 0) -> Field:
    """Concentric zones around a centre (distance in sheet widths, so round
    on the page); optional angular lobes."""
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * np.pi)

    def fn(u):
        dx = u[:, 0] - centre[0]
        dy = (u[:, 1] - centre[1]) * aspect
        d = np.hypot(dx, dy)
        if lobes:
            d = d * (1 + lobe_amp * np.sin(lobes * np.arctan2(dy, dx) + ph))
        return _soft_levels(d, list(radii), list(values), bleed)

    return Field(fn, "radial", aspect, {"family": "authored"})


# ---------------------------------------------------------------------------
# procedural family
# ---------------------------------------------------------------------------

def noise_fronts(seed: int = 0, *, scale: float = 0.12, thresholds=(-0.35, 0.55), values=(0.0, 1.0, 2.0),
                 bleed_lo: float = 0.03, bleed_hi: float = 0.6, aspect: float = 1.0) -> Field:
    """Smooth noise n (sd 1, correlation length `scale` sheet widths) through
    soft thresholds. The bleed (in noise sd) itself varies over the sheet
    between bleed_lo (abrupt fronts) and bleed_hi (gradual) by a second
    noise, so one sheet has both kinds of transition."""
    shape = _grid_shape(aspect)
    cell = 1.0 / max(shape[1], 1)
    n = _noise_grid((seed, 0), shape, scale / cell / 2.0)
    b = smoothstep(0.5 + 0.5 * _noise_grid((seed, 1), shape, 1.5 * scale / cell / 2.0))
    bleed = bleed_lo + (bleed_hi - bleed_lo) * b
    g = _soft_levels(n, list(thresholds), list(values), bleed)
    return GridField(g, f"noise(s={scale:g})", aspect, {"family": "procedural", "seed": seed})


# ---------------------------------------------------------------------------
# structure-derived family
# ---------------------------------------------------------------------------

def strahler(drawing: Drawing) -> np.ndarray:
    """Strahler order per stroke of a host tree (stroke meta "host" = index
    of the stroke it branches from; None = root). Leaves are 1; a parent
    takes the max child order, +1 when two children share it. Strokes with
    no host information get 1."""
    n = len(drawing.strokes)
    kids: dict[int, list[int]] = {i: [] for i in range(n)}
    for i, st in enumerate(drawing.strokes):
        h = st.meta.get("host")
        if h is not None and 0 <= int(h) < n and int(h) != i:
            kids[int(h)].append(i)
    order = np.zeros(n, int)

    def visit(i, depth=0):
        if order[i] or depth > n:
            return order[i] or 1
        ch = [visit(c, depth + 1) for c in kids[i]]
        if not ch:
            order[i] = 1
        else:
            m = max(ch)
            order[i] = m + 1 if ch.count(m) >= 2 else m
        return order[i]

    for i in range(n):
        visit(i)
    return order


def _splat(drawing: Drawing, values: np.ndarray, shape, sigma_cells: float, weight_floor: float = 1e-3):
    """Rasterise per-stroke values: a kernel-weighted mean over nearby ink
    (value grid) and the ink density (weight grid), both on the unit sheet."""
    W, H = drawing.size
    num = np.zeros(shape)
    den = np.zeros(shape)
    for st, v in zip(drawing.strokes, values):
        p = st.points
        if len(p) < 2:
            continue
        seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
        L = float(seg.sum())
        k = max(int(L / max(min(W, H) / shape[1] / 2, 1e-9)), 2)
        s = np.concatenate([[0], np.cumsum(seg)])
        t = np.linspace(0, L, k)
        q = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
        c = np.clip((q[:, 0] / W * shape[1]).astype(int), 0, shape[1] - 1)
        r = np.clip((q[:, 1] / H * shape[0]).astype(int), 0, shape[0] - 1)
        np.add.at(num, (r, c), float(v))
        np.add.at(den, (r, c), 1.0)
    num = gaussian_filter(num, sigma_cells, mode="constant")
    den = gaussian_filter(den, sigma_cells, mode="constant")
    return num / np.maximum(den, weight_floor), den


def structure_field(drawing: Drawing, mode: str = "strahler", *, sigma: float = 0.02, gamma: float = 1.0,
                    values=(0.0, 2.0), background: float | None = None, reach: float = 0.06) -> Field:
    """A field derived from a structure drawing (pixel coords, drawing.size).

    mode "strahler": per-stroke Strahler order (trunk → shape, branches →
         nib, twigs → line), splatted over the sheet with a Gaussian of
         `sigma` sheet widths; "order": tree depth (meta "order", 0 =
         trunk) inverted the same way; "density": ink density (dense → high);
         "trunk": distance to the longest high-order stroke (near → high,
         fading over `reach` sheet widths).
    values: (low, high) regime the normalised quantity maps to; `gamma`
    shapes the mapping. Far from all ink the field fades to `background`
    (default: low)."""
    W, H = drawing.size
    aspect = H / W
    shape = _grid_shape(aspect)
    cells = sigma * shape[1]
    lo, hi = values
    bg = lo if background is None else background
    n = len(drawing.strokes)
    meta = {"family": "structure", "mode": mode}
    if mode in ("strahler", "order"):
        if mode == "strahler":
            o = strahler(drawing).astype(float)
            q = (o - 1) / max(o.max() - 1, 1)
        else:
            o = np.array([float(st.meta.get("order", 0)) for st in drawing.strokes])
            q = 1 - o / max(o.max(), 1)
        q = np.clip(q, 0, 1) ** gamma
        val, den = _splat(drawing, q, shape, cells)
        cover = smoothstep(den / max(np.quantile(den[den > 0], 0.25) if np.any(den > 0) else 1, 1e-9))
        g = bg + (lo + (hi - lo) * val - bg) * cover
        meta["orders"] = np.bincount(o.astype(int)).tolist() if n else []
    elif mode == "density":
        _, den = _splat(drawing, np.ones(n), shape, cells)
        d = den / max(float(np.quantile(den, 0.98)), 1e-9)
        g = lo + (hi - lo) * np.clip(d, 0, 1) ** gamma
    elif mode == "trunk":
        o = strahler(drawing)
        lens = np.array([float(np.sum(np.linalg.norm(np.diff(st.points, axis=0), axis=1))) for st in drawing.strokes])
        main = int(np.argmax(o * 1e6 + lens)) if n else 0
        p = drawing.strokes[main].points if n else np.array([[W / 2, 0], [W / 2, H]])
        ys, xs = np.mgrid[0:shape[0], 0:shape[1]]
        grid_pts = np.column_stack([(xs.ravel() + 0.5) / shape[1] * W, (ys.ravel() + 0.5) / shape[0] * H])
        from scipy.spatial import cKDTree
        d, _ = cKDTree(p).query(grid_pts)
        d = (d / W).reshape(shape)
        g = lo + (hi - lo) * np.exp(-(d / max(reach, 1e-6)) ** 2) ** gamma
        meta["main_stroke"] = main
    else:
        raise ValueError(f"unknown structure_field mode {mode!r}")
    return GridField(g, f"structure:{mode}", aspect, meta)


# ---------------------------------------------------------------------------
# mixed / combinators
# ---------------------------------------------------------------------------

def mix(a: Field, b: Field, w) -> Field:
    """(1 − w)·a + w·b; w a number or a Field read as w = field / 2."""
    if isinstance(w, Field):
        fn = lambda u: (1 - w(u) / R_MAX) * a(u) + w(u) / R_MAX * b(u)  # noqa: E731
    else:
        fn = lambda u: (1 - float(w)) * a(u) + float(w) * b(u)  # noqa: E731
    return Field(fn, f"mix({a.name},{b.name})", a.aspect, {"family": "mixed"})


def maximum(*fs: Field) -> Field:
    return Field(lambda u: np.max(np.vstack([f(u) for f in fs]), axis=0),
                 "max(" + ",".join(f.name for f in fs) + ")", fs[0].aspect, {"family": "mixed"})


def minimum(*fs: Field) -> Field:
    return Field(lambda u: np.min(np.vstack([f(u) for f in fs]), axis=0),
                 "min(" + ",".join(f.name for f in fs) + ")", fs[0].aspect, {"family": "mixed"})


def offset(f: Field, by: float) -> Field:
    return Field(lambda u: f(u) + by, f"{f.name}{by:+g}", f.aspect, f.meta)


def scale(f: Field, k: float) -> Field:
    return Field(lambda u: f(u) * k, f"{f.name}*{k:g}", f.aspect, f.meta)


def warp(f: Field, seed: int = 0, *, amp: float = 0.04, scale_: float = 0.15) -> Field:
    """Domain warp: f evaluated at u + amp·(noise_x, noise_y). Straight
    authored fronts become wobbly coastlines."""
    shape = _grid_shape(f.aspect, 96)
    cell = 1.0 / shape[1]
    nx = _noise_grid((seed, 10), shape, scale_ / cell / 2)
    ny = _noise_grid((seed, 11), shape, scale_ / cell / 2)

    def fn(u):
        rows, cols = shape
        c = [u[:, 1] * rows - 0.5, u[:, 0] * cols - 0.5]
        du = np.column_stack([map_coordinates(nx, c, order=1, mode="nearest"),
                              map_coordinates(ny, c, order=1, mode="nearest") / max(f.aspect, 1e-9)])
        return f(np.clip(u + amp * du, 0, 1))

    return Field(fn, f"warp({f.name})", f.aspect, {**f.meta, "warp": amp})


def levels(f: Field, edges=(0.5, 1.4), values=(0.0, 1.0, 2.0), bleed: float = 0.1) -> Field:
    """Re-quantise a field into regimes with fronts of `bleed` (r units)."""
    return Field(lambda u: _soft_levels(f(u), list(edges), list(values), bleed), f"levels({f.name})", f.aspect,
                 f.meta)


# ---------------------------------------------------------------------------
# hand fields
# ---------------------------------------------------------------------------

class HandField:
    """Soft weights over named hands per position: weights(u) → (N, K)."""

    def __init__(self, hands: Sequence[str], fn: Callable[[np.ndarray], np.ndarray], name: str = "hands"):
        self.hands = list(hands)
        self._fn = fn
        self.name = name

    def weights(self, u) -> np.ndarray:
        w = np.maximum(np.asarray(self._fn(_unit(u)), float), 0)
        return w / np.maximum(w.sum(axis=1, keepdims=True), 1e-12)

    def dominant(self, u) -> list[str]:
        return [self.hands[i] for i in np.argmax(self.weights(u), axis=1)]


def single_hand(hand: str) -> HandField:
    return HandField([hand], lambda u: np.ones((len(u), 1)), f"hand:{hand}")


def hand_zones(hands: Sequence[str], seed: int = 0, *, scale: float = 0.22, temp: float = 0.25,
               aspect: float = 1.0, bias: Sequence[float] | None = None) -> HandField:
    """Soft Voronoi of K smooth noise fields: weights = softmax(noise / temp).
    Small temp → hard borders; large → broad bleed where hands mix."""
    shape = _grid_shape(aspect, 96)
    cell = 1.0 / shape[1]
    grids = [_noise_grid((seed, 20 + i), shape, scale / cell / 2) + (0 if bias is None else bias[i])
             for i in range(len(hands))]

    def fn(u):
        rows, cols = shape
        c = [u[:, 1] * rows - 0.5, u[:, 0] * cols - 0.5]
        z = np.column_stack([map_coordinates(g, c, order=1, mode="nearest") for g in grids]) / max(temp, 1e-6)
        z = z - z.max(axis=1, keepdims=True)
        return np.exp(z)

    return HandField(hands, fn, f"zones({','.join(hands)})")


def hand_by_field(f: Field, hands_by_level: dict[str, float], *, width: float = 0.35) -> HandField:
    """Hands keyed to a field's value (e.g. lines in a Matisse hand, nib
    zones in the shikasta hand): weight = exp(−((r − level)/width)²)."""
    hands = list(hands_by_level)
    lv = np.array([hands_by_level[h] for h in hands])

    def fn(u):
        r = f(u)[:, None]
        return np.exp(-((r - lv[None, :]) / width) ** 2) + 1e-6

    return HandField(hands, fn, f"by({f.name})")


def hand_bands(hands: Sequence[str], edges: Sequence[float], *, along: str = "x", bleed: float = 0.05) -> HandField:
    def fn(u):
        c = u[:, 0] if along == "x" else u[:, 1]
        cols = []
        for i in range(len(hands)):
            lo = -np.inf if i == 0 else edges[i - 1]
            hi = np.inf if i == len(hands) - 1 else edges[i]
            a = np.ones(len(u)) if not np.isfinite(lo) else smoothstep((c - lo) / bleed + 0.5)
            b = np.ones(len(u)) if not np.isfinite(hi) else 1 - smoothstep((c - hi) / bleed + 0.5)
            cols.append(a * b + 1e-6)
        return np.column_stack(cols)

    return HandField(hands, fn, "hand_bands")


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def arclen(p: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def resample(p: np.ndarray, step: float) -> np.ndarray:
    p = np.asarray(p, float)
    s = arclen(p)
    if s[-1] <= step or len(p) < 2:
        return p.copy()
    t = np.linspace(0, s[-1], max(int(math.ceil(s[-1] / step)) + 1, 2))
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def _tangent_angle(p: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    """Page angle (CCW from rightward, y up on the page) of the travel direction."""
    d = np.gradient(gaussian_filter1d(p, sigma, axis=0, mode="nearest"), axis=0)
    return np.arctan2(-d[:, 1], d[:, 0])


# ---------------------------------------------------------------------------
# regime stroke: stand-in for gesture.regime (same interface)
# ---------------------------------------------------------------------------

@dataclass
class StandInStroke:
    """Centreline (px) + regime r(s) ∈ [0, 2] (0 line, 1 nib, 2 shape)."""
    points: np.ndarray
    r: np.ndarray
    phi: float = math.radians(60.0)      # nib edge page angle (shikasta wc-15 fit)
    W: float = 12.0                      # nib edge length at r = 1 (px)
    shape_w: float = 34.0                # shape width at r = 2 (px)
    pen: float = 1.7                     # pen width (px)
    meta: dict = dc_field(default_factory=dict)


def standin_from_field(points, field_fn, *, step: float | None = None, smooth: float | None = None, size=None, **kw):
    """RegimeStroke from a centreline and r = field_fn(points px)."""
    s = StandInStroke(np.asarray(points, float), np.zeros(0), **kw)
    p = resample(s.points, step or s.pen)
    r = np.clip(np.asarray(field_fn(p), float), 0, R_MAX)
    sm = smooth if smooth is not None else max(s.W / max(step or s.pen, 1e-9), 1.0)
    if len(r) > 3:
        r = gaussian_filter1d(r, sm, mode="nearest")
    s.points, s.r = p, r
    return s


def _width_profile(s: StandInStroke):
    """Per-sample half-offset vectors (N, 2) in image coords, whether the
    sample is a shape sample, and the scalar width."""
    p, r = s.points, s.r
    a = np.clip(r, 0, 1)
    b = smoothstep(np.clip(r - 1, 0, 1))
    th = _tangent_angle(p, max(s.W / max(s.pen, 1e-9) / 2, 1.0))
    nib_dir = np.array([math.cos(s.phi), -math.sin(s.phi)])           # image coords of the nib edge
    nrm = np.column_stack([-np.sin(th), -np.cos(th)])                    # image-coord normal of page tangent
    # nib edge grows with a; the shape part swells isotropically with b
    half_nib = 0.5 * s.W * a
    n_pts = len(p)
    sw = 0.5 * s.shape_w * b
    if n_pts > 3:
        sw = gaussian_filter1d(sw, max(s.shape_w / max(s.pen, 1e-9) * 0.35, 1.0), mode="nearest")
    vec = (1 - b)[:, None] * half_nib[:, None] * nib_dir[None, :] + sw[:, None] * nrm
    width = 2 * np.linalg.norm(vec, axis=1) * np.where(b > 0, 1.0, np.abs(np.sin(th - s.phi))) + s.pen
    return vec, b, width, sw


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def _ring_split(ring: np.ndarray, a: np.ndarray, b: np.ndarray):
    """Split a closed ring (no repeated point) at the vertices nearest a and
    b → (arc a→b, arc b→a), each an open polyline."""
    ia = int(np.argmin(np.sum((ring - a) ** 2, axis=1)))
    ib = int(np.argmin(np.sum((ring - b) ** 2, axis=1)))
    n = len(ring)
    if ia == ib:
        r = np.roll(ring, -ia, axis=0)
        return np.vstack([r, r[:1]]), None
    idx1 = [(ia + k) % n for k in range(((ib - ia) % n) + 1)]
    idx2 = [(ib + k) % n for k in range(((ia - ib) % n) + 1)]
    return ring[idx1], ring[idx2]


def standin_render(s: StandInStroke, *, fill_shapes: bool = True, min_run: int = 3) -> list[np.ndarray]:
    """Plotter polylines of one regime stroke. Line samples → the centreline;
    nib/shape runs → the swept ribbon's outline, entered and left at its
    tips so the main path stays one contiguous line (the ribbon's other side
    is a second path); shape cores → concentric contours at pen spacing
    (never hatching). Closed rings repeat their first point."""
    from shapely.geometry import Polygon, Point
    from shapely.ops import unary_union

    p = s.points
    if len(p) < 2:
        return []
    vec, b, width, sw = _width_profile(s)
    thick = width > 1.6 * s.pen
    # drop tiny islands of thickness (noise in r)
    for i0, i1 in _runs(thick):
        if i1 - i0 + 1 < min_run:
            thick[i0:i1 + 1] = False
    out: list[np.ndarray] = []
    main: list[np.ndarray] = []
    cur = [p[0]]
    i = 0
    n = len(p)
    runs = _runs(thick)
    for i0, i1 in runs:
        cur.extend(p[i:i0 + 1][1:] if i < i0 else [])
        if i < i0:
            pass
        j0, j1 = max(i0 - 1, 0), min(i1 + 1, n - 1)
        quads = []
        A = p + vec
        B = p - vec
        for k in range(j0, j1):
            q = Polygon([A[k], A[k + 1], B[k + 1], B[k]])
            if not q.is_valid:
                q = q.buffer(0)
            if q.area > 1e-9:
                quads.append(q)
        for k in range(j0, j1 + 1):
            if b[k] > 0.05 and sw[k] > s.pen:
                quads.append(Point(p[k]).buffer(float(sw[k]), quad_segs=6))
        geom = unary_union(quads).buffer(s.pen / 2, quad_segs=4) if quads else None
        if geom is None or geom.is_empty:
            cur.extend(p[i0:i1 + 1])
            i = i1
            continue
        polys = [geom] if geom.geom_type == "Polygon" else sorted(geom.geoms, key=lambda g: -g.area)
        big = polys[0]
        ring = np.asarray(big.exterior.coords)[:-1]
        arc1, arc2 = _ring_split(ring, p[j0], p[j1])
        cur.extend(arc1)
        main.append(np.asarray(cur))
        if arc2 is not None and len(arc2) >= 2:
            out.append(arc2)
        cur = [arc1[-1]]
        for hole in big.interiors:
            h = np.asarray(hole.coords)
            if len(h) >= 4:
                out.append(h)
        for extra in polys[1:]:
            if extra.area > s.pen ** 2:
                out.append(np.asarray(extra.exterior.coords))
        if fill_shapes and np.any(b[j0:j1 + 1] > 0.5):
            core_pts = [Point(p[k]).buffer(float(max(sw[k], s.pen)), quad_segs=6)
                        for k in range(j0, j1 + 1) if b[k] > 0.5]
            core = unary_union(core_pts).intersection(big) if core_pts else None
            if core is not None and not core.is_empty:
                inner = core.buffer(-s.pen, quad_segs=4)
                k = 0
                while not inner.is_empty and k < 80:
                    for pg in ([inner] if inner.geom_type == "Polygon" else list(getattr(inner, "geoms", []))):
                        if pg.geom_type != "Polygon" or pg.area < s.pen ** 2 * 0.5:
                            continue
                        out.append(np.asarray(pg.exterior.coords))
                    inner = inner.buffer(-s.pen, quad_segs=4)
                    k += 1
        i = j1
    cur.extend(p[i + 1:] if i + 1 < n else [])
    if len(cur) >= 2:
        main.append(np.asarray(cur))
    # join main pieces that touch (they share tips) into one path
    joined: list[np.ndarray] = []
    for m in main:
        if joined and np.linalg.norm(joined[-1][-1] - m[0]) < 3 * s.pen:
            joined[-1] = np.vstack([joined[-1], m[1:]])
        else:
            joined.append(m)
    res = [q for q in joined + out if len(q) >= 2]
    return [np.asarray(q, float) for q in res]


# ---------------------------------------------------------------------------
# signs: stand-in for gesture.signs.place_signs
# ---------------------------------------------------------------------------

def _disc_rings(c, rad: float, pen: float) -> list[np.ndarray]:
    out, r = [], rad
    t = np.linspace(0, 2 * np.pi, 25)
    while r > pen * 0.4:
        k = max(int(2 * np.pi * r / max(pen, 1e-9)), 8)
        tt = np.linspace(0, 2 * np.pi, min(k, 48) + 1)
        out.append(np.column_stack([c[0] + r * np.cos(tt), c[1] + r * np.sin(tt)]))
        r -= pen
    if not out:
        out.append(np.column_stack([c[0] + pen * 0.3 * np.cos(t), c[1] + pen * 0.3 * np.sin(t)]))
    return out


def standin_signs(lines: list[np.ndarray], rng: np.random.Generator, grammar=None, *, n: int = 8,
                  size_px: float = 14.0, pen: float = 1.7) -> list[np.ndarray]:
    """A few sign-like marks placed in relation to line ends: an eye (loop
    holding a dot), a bead on the line, a hook ending in a dot, a lozenge."""
    ends = []
    for q in lines:
        if len(q) < 6:
            continue
        L = arclen(q)[-1]
        if L < 4 * size_px:
            continue
        for e, nb in ((q[-1], q[-4]), (q[0], q[3])):
            d = e - nb
            ends.append((e, math.atan2(d[1], d[0])))
    if not ends:
        return []
    out: list[np.ndarray] = []
    pick = rng.choice(len(ends), size=min(n, len(ends)), replace=False)
    kinds = ("eye", "bead", "hook", "lozenge")
    for k, i in enumerate(pick):
        e, a = ends[int(i)]
        u = np.array([math.cos(a), math.sin(a)])
        v = np.array([-u[1], u[0]])
        s = size_px * rng.uniform(0.7, 1.3)
        kind = kinds[int(rng.integers(len(kinds)))]
        c = e + u * s * 0.9
        if kind == "eye":
            t = np.linspace(0, 2 * np.pi, 41)
            ring = c + np.outer(np.cos(t) * s * 0.9, u) + np.outer(np.sin(t) * s * 0.5, v)
            out.append(ring)
            out += _disc_rings(c, s * 0.18, pen)
        elif kind == "bead":
            out += _disc_rings(e - u * s * 1.5, s * 0.3, pen)
        elif kind == "hook":
            t = np.linspace(0, np.pi * 1.2, 20)
            hook = e + np.outer(np.sin(t) * s * 0.7, u) + np.outer((1 - np.cos(t)) * s * 0.45, v)
            out.append(hook)
            out += _disc_rings(hook[-1], s * 0.16, pen)
        else:
            dia = [c - u * s * 0.6, c + v * s * 0.3, c + u * s * 0.6, c - v * s * 0.3, c - u * s * 0.6]
            out.append(np.asarray(dia))
            out += _disc_rings(c, s * 0.2, pen)
    return [np.asarray(o, float) for o in out]


# ---------------------------------------------------------------------------
# engines: the real modules when present, the stand-in otherwise
# ---------------------------------------------------------------------------

def _try_import(name: str):
    try:
        return importlib.import_module(f"{__package__}.{name}")
    except Exception:  # noqa: BLE001
        return None


def _call_with(fn, *args, **kw):
    """Call fn with only the keyword arguments its signature accepts."""
    try:
        sig = inspect.signature(fn)
        if not any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            kw = {k: v for k, v in kw.items() if k in sig.parameters}
    except (TypeError, ValueError):
        pass
    return fn(*args, **kw)


def _as_polylines(obj) -> list[np.ndarray]:
    """Normalise whatever a renderer returns into (N, 2) float polylines."""
    out = []
    if obj is None:
        return out
    if isinstance(obj, np.ndarray) and obj.ndim == 2:
        obj = [obj]
    if isinstance(obj, Drawing):
        obj = obj.strokes
    if isinstance(obj, dict):
        obj = obj.get("polylines") or obj.get("paths") or []
    for o in obj:
        if isinstance(o, Stroke):
            q = np.vstack([o.points, o.points[:1]]) if o.closed else o.points
        elif hasattr(o, "points"):
            q = np.asarray(o.points)
            if getattr(o, "closed", False):
                q = np.vstack([q, q[:1]])
        else:
            q = np.asarray(o)
        if q.ndim == 2 and q.shape[1] == 2 and len(q) >= 2 and np.all(np.isfinite(q)):
            out.append(q.astype(np.float64))
    return out


@dataclass
class Engine:
    """Adapters: stroke(points, ffn, **widths) → regime stroke;
    render(stroke) → polylines; signs(lines, rng, n, w, pen) → polylines."""
    name: str
    signs_name: str
    stroke: Callable
    render: Callable
    signs: Callable


def _close_flagged(paths, closed) -> list[np.ndarray]:
    out = []
    for q, c in zip(paths, closed):
        q = np.asarray(q, float)
        if c and len(q) > 2 and np.linalg.norm(q[0] - q[-1]) > 1e-9:
            q = np.vstack([q, q[:1]])
        out.append(q)
    return out


def engine(which: str = "auto", nib_renderer=None) -> Engine:
    """'auto': gesture.regime / gesture.signs if importable (each
    independently), else the stand-in; 'standin': always the stand-in.
    nib_renderer: optional regime.render hook (gesture.penrender.nib_style)
    for nib ribbons; used only on full (fill=True) renders."""
    reg = _try_import("regime") if which == "auto" else None
    sg = _try_import("signs") if which == "auto" else None
    ok_reg = reg is not None and hasattr(reg, "from_field") and hasattr(reg, "render")
    ok_sg = sg is not None and hasattr(sg, "place_signs") and hasattr(sg, "sign_paths")
    if ok_reg:
        def stroke(q, ffn, *, phi, W, shape_w, pen):
            f2 = lambda x, y: ffn(np.column_stack([np.ravel(x), np.ravel(y)]))  # noqa: E731
            return reg.from_field(q, f2, phi=phi, W=W, mass=shape_w, w_min=0.0)

        def render(st, *, pen, fill=True, styled=True):
            if fill and styled and nib_renderer is not None:
                return list(reg.render(st, pen=pen, fill=True, nib_renderer=nib_renderer))
            return reg.render(st, pen=pen, fill=fill)
    else:
        def stroke(q, ffn, *, phi, W, shape_w, pen):
            return standin_from_field(q, ffn, phi=phi, W=W, shape_w=shape_w, pen=pen)

        def render(st, *, pen, fill=True, styled=True):
            return standin_render(st)
    if ok_sg:
        def signs(lines, rng, *, n, w, pen, grouped=False):
            placed = sg.place_signs(lines, rng, None, w=w, n=n)
            out = []
            for ps in placed:
                paths, closed = sg.sign_paths(ps, pen=pen)
                out.append(_close_flagged(paths, closed))
            return out if grouped else [q for g in out for q in g]
    else:
        def signs(lines, rng, *, n, w, pen, grouped=False):
            out = standin_signs(lines, rng, n=n, size_px=3 * w, pen=pen)
            return [out] if grouped else out
    return Engine("regime" if ok_reg else "standin", "signs" if ok_sg else "standin", stroke, render, signs)


# ---------------------------------------------------------------------------
# hatching detector (the "never hatching" rule as a check)
# ---------------------------------------------------------------------------

def _split_reversals(q: np.ndarray, angle_deg: float = 120.0) -> list[np.ndarray]:
    if len(q) < 3:
        return [q]
    d = np.diff(q, axis=0)
    a = np.arctan2(d[:, 1], d[:, 0])
    t = np.abs((np.diff(a) + np.pi) % (2 * np.pi) - np.pi)
    cut = np.where(t > math.radians(angle_deg))[0] + 1        # vertex index of each reversal
    if not len(cut):
        return [q]
    edges = [0, *cut.tolist(), len(q) - 1]
    return [q[a:b + 1] for a, b in zip(edges[:-1], edges[1:]) if b > a]


def hatching_families(polylines: list[np.ndarray], *, max_len: float, straight: float = 0.92,
                      angle_deg: float = 15.0, min_family: int = 4, radius: float = 1.5,
                      solid_gap: float = 0.0) -> dict:
    """Families of short parallel straight marks = hatching. Open polylines
    are cut at reversals (zig-zag hatching drawn as one path); closed rings
    (first == last) are taken whole. A mark is short (≤ max_len) and straight
    (chord/length ≥ straight); a family is ≥ min_family marks within
    `radius` × length of each other, parallel within angle_deg, of similar
    length (ratio ≤ 2) and side by side (perpendicular offset ≥ 0.15 length).
    solid_gap > 0 (≈ 1.25 pen widths): a family whose marks sit at most this
    far from their nearest parallel neighbour (median) inks solid — pen-spaced
    contour fill, not hatching — and is counted in "solid" instead.
    Returns {"marks", "flagged", "families", "solid"}."""
    marks = []
    for q in polylines:
        q = np.asarray(q, float)
        if len(q) < 2:
            continue
        closed = len(q) > 3 and np.linalg.norm(q[0] - q[-1]) < 1e-6
        for piece in ([q] if closed else _split_reversals(q)):
            L = float(arclen(piece)[-1])
            if L <= 1e-9 or L > max_len:
                continue
            ch = float(np.linalg.norm(piece[-1] - piece[0]))
            if ch / L < straight:
                continue
            d = (piece[-1] - piece[0]) / max(ch, 1e-12)
            marks.append((piece.mean(axis=0), d, L))
    n = len(marks)
    if n == 0:
        return {"marks": 0, "flagged": 0, "families": 0, "solid": 0}
    M = np.array([m[0] for m in marks])
    D = np.array([m[1] for m in marks])
    L = np.array([m[2] for m in marks])
    adj = [[] for _ in range(n)]
    nn_gap = np.full(n, np.inf)
    cosmin = math.cos(math.radians(angle_deg))
    for i in range(n):
        dv = M - M[i]
        dist = np.linalg.norm(dv, axis=1)
        par = np.abs(D @ D[i]) >= cosmin
        perp = np.abs(dv @ np.array([-D[i][1], D[i][0]]))
        near = (dist <= radius * L[i]) & par & (np.maximum(L, L[i]) / np.minimum(L, L[i]) <= 2.0)
        near[i] = False
        ok = near & (perp >= 0.15 * L[i])
        adj[i] = list(np.where(ok)[0])
        side = near & (perp > 1e-6)
        if np.any(side):
            nn_gap[i] = float(perp[side].min())
    flagged = np.array([len(a) >= min_family - 1 for a in adj])
    seen, fam, solid = set(), 0, 0
    for i in np.where(flagged)[0]:
        if i in seen:
            continue
        members, stack = [], [i]
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            members.append(k)
            stack.extend(j for j in adj[k] if flagged[j])
        if solid_gap > 0 and float(np.median(nn_gap[members])) <= solid_gap:
            solid += 1
        else:
            fam += 1
    return {"marks": n, "flagged": int(flagged.sum()), "families": fam, "solid": solid}


# ---------------------------------------------------------------------------
# the composition
# ---------------------------------------------------------------------------

@dataclass
class Composition:
    polylines: list[np.ndarray]
    size: tuple[int, int]
    meta: dict
    centrelines: list[np.ndarray] = dc_field(default_factory=list)
    regimes: list[np.ndarray] = dc_field(default_factory=list)
    groups: list[int] = dc_field(default_factory=list)     # mark id per polyline (path ordering)
    kinds: list[str] = dc_field(default_factory=list)      # "line" | "fill" | "sign" | "echo" | "drip"

    def drawing(self) -> Drawing:
        """As a Drawing (closed rings as closed strokes) for composite.to_svg."""
        st = []
        for q in self.polylines:
            closed = len(q) > 3 and np.linalg.norm(q[0] - q[-1]) < 1e-6
            st.append(Stroke(q[:-1].copy() if closed else q.copy(), closed=closed))
        return Drawing(st, source=f"regime:{self.meta.get('label', '')}", size=self.size, meta=dict(self.meta))


def pen_px_for(size, paper_mm=(210.0, 297.0), margin_mm: float = 10.0, pen_mm: float = 0.4) -> float:
    """Pen width in px when a sheet of `size` px is fitted onto the paper."""
    W, H = size
    k = min((paper_mm[0] - 2 * margin_mm) / W, (paper_mm[1] - 2 * margin_mm) / H)   # mm per px
    return pen_mm / k


# --- structures ------------------------------------------------------------

def make_structure(kind, rng: np.random.Generator, size, hand: str = "hokusai", params: dict | None = None):
    """(Drawing in px, already_in_hand). kind: "tree" (one-trunk Oehlen tree,
    the axis), "forest" (3 trunks), "grammar" (grammar-v6 contiguous lines in
    `hand`, already handed), "single" (one chained single line through a
    tree in `hand`, already handed), "line" (one long wandering structure
    line), or a Drawing."""
    from . import topology
    W, H = size
    prm = dict(params or {})
    if isinstance(kind, Drawing):
        return kind, False
    if kind in ("tree", "forest"):
        prm.setdefault("trunks", 1 if kind == "tree" else 3)
        prm.setdefault("fill", 0.92)
        prm.setdefault("clearance_r", 0.008)
        return topology.generate_structure(None, rng, (W, H), kind="oehlen_tree", **prm), False
    if kind == "grammar":
        g = load_hand(hand)
        from . import grammar_v6_frozen as gm6
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = gm6.generate_drawing(g, rng, (W, H), mode=prm.pop("mode", "contiguous"), **prm)
        return Drawing([Stroke(s.points, closed=s.closed, meta={**s.meta, "hand": hand}) for s in d.strokes],
                       source=d.source, size=(W, H), meta=d.meta), True
    if kind == "single":
        from experiments import composite as cp
        tp = {"trunks": 1, **prm}
        d = cp.composite("oehlen_tree", load_hand(hand) if hand == "shikasta" else hand, rng, size=(W, H),
                         amount=0.7, chain="before", pin="turns", retrace="offset", walk="min_turn",
                         structure_params=tp)
        return Drawing([Stroke(s.points, closed=s.closed, meta={**s.meta, "hand": hand}) for s in d.strokes],
                       source=d.source, size=(W, H), meta=d.meta), True
    if kind == "line":
        n = 900
        t = np.linspace(0, 1, n)
        k = _noise_1d(int(rng.integers(1 << 30)), n, 40) * 9 + _noise_1d(int(rng.integers(1 << 30)), n, 8) * 3
        th = -np.pi / 2 + np.cumsum(k) / n * 2
        step = 3.2 * H / n
        p = np.cumsum(np.column_stack([np.cos(th), np.sin(th)]) * step, axis=0)
        p = p - p.min(0)
        p = p / max(np.ptp(p, axis=0).max(), 1e-9) * 0.9 * min(W, H) + 0.05 * np.array([W, H])
        _ = t
        return Drawing([Stroke(p, meta={"order": 0})], source="line", size=(W, H)), False
    raise ValueError(f"unknown structure {kind!r}")


def _grammar_mixed(rng, size, hf: "HandField", params: dict | None = None) -> Drawing:
    """Grammar-v6 contiguous lines from several hands: one drawing per hand,
    each keeping the lines whose centroid lies where that hand dominates.
    Whole lines are kept, so lines cross zone borders."""
    W, H = size
    keep = []
    for k, h in enumerate(hf.hands):
        d, _ = make_structure("grammar", np.random.default_rng(int(rng.integers(1 << 31))), size, hand=h,
                              params=params)
        for s_ in d.strokes:
            c = s_.points.mean(axis=0) / np.array([W, H])
            if int(np.argmax(hf.weights(c[None])[0])) == k:
                keep.append(s_)
    return Drawing(keep, source="grammar-mixed", size=(W, H))


def script_fill(fobj: Field, hand: str, rng: np.random.Generator, size, *, tiles: int = 6,
                tile_frac: float = 0.42, lo: float = 0.55, hi: float = 1.5, keep: float = 0.6,
                min_len: float = 0.08, per_tile: int = 5) -> list[np.ndarray]:
    """Script-like zones: small grammar-v6 drawings in `hand` (tiles of
    tile_frac × the sheet) placed where the field is nib (r ∈ [lo, hi]);
    a line is kept when ≥ `keep` of its points lie in r ∈ [lo − 0.3, hi + 0.5]
    and it is ≥ min_len × H long (short pieces become nib confetti that reads
    as hatching); at most `per_tile` lines per tile, longest first.
    Line lengths are tile-relative, so the zone reads as small writing
    against the sheet-scale structure."""
    W, H = size
    cand = rng.uniform([0, 0], [W, H], size=(600, 2))
    r = fobj.at_px(cand, size)
    cand = cand[(r >= lo) & (r <= hi)]
    if len(cand) == 0:
        return []
    centres = [cand[int(rng.integers(len(cand)))]]
    while len(centres) < tiles:
        d = np.min(np.linalg.norm(cand[:, None, :] - np.array(centres)[None], axis=2), axis=1)
        if d.max() < 0.05 * H:
            break
        centres.append(cand[int(np.argmax(d * rng.uniform(0.7, 1.0, len(d))))])
    tw, th = int(W * tile_frac), int(H * tile_frac * 0.75)
    out = []
    for c in centres:
        d, _ = make_structure("grammar", np.random.default_rng(int(rng.integers(1 << 31))), (tw, th), hand=hand)
        got = []
        for st in d.strokes:
            p = st.points - np.array([tw, th]) / 2 + c
            L = float(arclen(p)[-1])
            if L < min_len * H:
                continue
            rr = fobj.at_px(p, size)
            inside = (p[:, 0] > 0) & (p[:, 0] < W) & (p[:, 1] > 0) & (p[:, 1] < H)
            if np.mean((rr >= lo - 0.3) & (rr <= hi + 0.5) & inside) >= keep:
                got.append((L, np.clip(p, 0, [W, H])))
        out += [p for _, p in sorted(got, key=lambda t: -t[0])[:per_tile]]
    return out


_HANDS: dict = {}
SHIKASTA = "shikasta"


def register_hand(name: str, grammar) -> None:
    """Make a grammar object available under `name` (tests, ad-hoc hands)."""
    _HANDS[name] = grammar


def load_hand(hand: str):
    """A learned grammar: matisse / hokusai / ingres (frozen v6) or
    "shikasta" (grammar v6 learned on the policy-gated shikasta exercise /
    document sheets — `regime_compose hand`; falls back to hokusai with a
    warning if the file is missing)."""
    if hand in _HANDS:
        return _HANDS[hand]
    from pathlib import Path
    from . import grammar_v6_frozen as gm6
    root = Path(__file__).resolve().parents[3] / ".local/gesture/out"
    if hand == SHIKASTA:
        p = root / "regime_field" / "grammar_shikasta.json"
        if not p.exists():
            warnings.warn("shikasta grammar missing; using hokusai (run regime_compose hand)")
            return load_hand("hokusai")
        g = gm6.Grammar.load(p)
    else:
        g = gm6.Grammar.load(root / "grammar_v6_frozen" / f"grammar_{hand}.json")
    _HANDS[hand] = g
    return g


# --- hands along a line (code-switching) -------------------------------------

def hand_runs(points: np.ndarray, hf: HandField, size, rng: np.random.Generator, *, piece: float,
              keep: float = 0.35, switch_p: float = 0.35) -> list[tuple[int, int, str]]:
    """Runs of one hand along a line: walk in pieces of ~`piece` px; stay
    with the current hand while its weight ≥ keep (hysteresis); inside the
    bleed (no hand dominant) switch to another hand with probability
    switch_p per piece — code-switching. Returns (i0, i1, hand) index runs."""
    W, H = size
    s = arclen(points)
    n = len(points)
    if len(hf.hands) == 1 or n < 3:
        return [(0, n - 1, hf.hands[0])]
    k = max(int(s[-1] / max(piece, 1e-9)), 1)
    bounds = np.searchsorted(s, np.linspace(0, s[-1], k + 1))
    bounds[0], bounds[-1] = 0, n - 1
    mids = np.array([points[(bounds[i] + bounds[i + 1]) // 2] for i in range(k)]) / np.array([W, H])
    wts = hf.weights(mids)
    cur = int(np.argmax(wts[0]))
    labels = []
    for i in range(k):
        w = wts[i]
        top = int(np.argmax(w))
        if w[cur] < keep:
            cur = top
        elif top != cur and w[top] < 0.75 and rng.random() < switch_p:
            cur = top
        labels.append(cur)
    runs = []
    for i in range(k):
        if runs and runs[-1][2] == labels[i]:
            runs[-1][1] = int(bounds[i + 1])
        else:
            runs.append([int(bounds[i]), int(bounds[i + 1]), labels[i]])
    return [(a, b, hf.hands[h]) for a, b, h in runs]


def restyle_line(points: np.ndarray, runs, rng: np.random.Generator, *, amount: float, R: float,
                 overlap: float, budget: float | None = None) -> np.ndarray:
    """Restyle a line run by run, each run in its hand, extended by `overlap`
    px into its neighbours and cross-faded there (smoothstep blend of
    positions), so a line that changes hand stays one continuous line."""
    from . import restyle as rs
    if len(runs) == 1:
        out, _ = rs.restyle_points(points, load_hand(runs[0][2]), rng, amount=amount, ref_length=R,
                                   method="gauss", source="trace", budget=budget)
        return out
    s = arclen(points)
    out_pts = None
    for idx, (i0, i1, hand) in enumerate(runs):
        a = max(s[i0] - overlap, 0.0)
        b = min(s[i1] + overlap, s[-1])
        j0 = int(np.searchsorted(s, a))
        j1 = min(int(np.searchsorted(s, b)), len(points) - 1)
        seg = points[j0:j1 + 1]
        if len(seg) < 4:
            seg_out = seg.copy()
        else:
            seg_out, _ = rs.restyle_points(seg, load_hand(hand), rng, amount=amount, ref_length=R,
                                           method="gauss", source="trace", budget=budget)
            seg_out = resample(seg_out, 1.0)
        # map restyled samples back onto the source arc range [s[j0], s[j1]] by arc fraction
        ss = arclen(seg_out)
        f = ss / max(ss[-1], 1e-9)
        tgt = s[j0] + f * (s[j1] - s[j0])
        xi = np.interp(s, tgt, seg_out[:, 0], left=np.nan, right=np.nan)
        yi = np.interp(s, tgt, seg_out[:, 1], left=np.nan, right=np.nan)
        cur = np.column_stack([xi, yi])
        if out_pts is None:
            out_pts = cur
            continue
        # blend over the overlap [s[i0] - overlap, s[i0] + overlap]
        w = smoothstep((s - (s[i0] - overlap)) / max(2 * overlap, 1e-9))
        both = np.isfinite(out_pts[:, 0]) & np.isfinite(cur[:, 0])
        only_new = ~np.isfinite(out_pts[:, 0]) & np.isfinite(cur[:, 0])
        out_pts[both] = (1 - w[both, None]) * out_pts[both] + w[both, None] * cur[both]
        out_pts[only_new] = cur[only_new]
    ok = np.isfinite(out_pts[:, 0])
    return out_pts[ok]


# --- echoes and drips ----------------------------------------------------------

def _closed_rings(polys):
    return [q for q in polys if len(q) > 6 and np.linalg.norm(q[0] - q[-1]) < 1e-6]


def echoes(shape_rings: list[np.ndarray], lines: list[np.ndarray], field: Field, size, rng, *, n: int = 2,
           sign_px: float = 16.0, pen: float = 1.7) -> list[np.ndarray]:
    """A shape in one zone answered by a sign in another: the outline of one
    of the largest shapes, shrunk to sign size (with its concentric core),
    placed near a line end in the line regime (lowest r)."""
    from shapely.geometry import Polygon
    if not shape_rings or not lines:
        return []
    W, H = size
    areas = [abs(Polygon(q).area) if len(q) >= 4 else 0 for q in shape_rings]
    order = np.argsort(areas)[::-1][:max(3 * n, 3)]
    ends = []
    for q in lines:
        if len(q) >= 6 and arclen(q)[-1] > 6 * sign_px:
            ends += [q[-1], q[0]]
    if not ends:
        return []
    E = np.array(ends)
    rE = field.at_px(E, (W, H))
    cand = np.argsort(rE)[:max(4 * n, 4)]
    out = []
    for k in range(n):
        if k >= len(order):
            break
        src = shape_rings[int(order[rng.integers(len(order))])]
        poly = Polygon(src).buffer(0)
        if poly.is_empty:
            continue
        c = np.array(poly.centroid.coords[0])
        ext = max(np.ptp(src, axis=0).max(), 1e-9)
        f = sign_px / ext * rng.uniform(0.8, 1.3)
        pos = E[int(cand[rng.integers(len(cand))])] + rng.normal(0, sign_px * 0.6, 2)
        rot = rng.uniform(-0.6, 0.6)
        Rm = np.array([[math.cos(rot), -math.sin(rot)], [math.sin(rot), math.cos(rot)]])
        small = Polygon((src - c) @ Rm.T * f + pos).buffer(0)
        geoms = [small]
        while geoms and not geoms[-1].is_empty and len(geoms) < 30:
            geoms.append(geoms[-1].buffer(-pen, quad_segs=4))
        for g in geoms:
            for pg in ([g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))):
                if pg.geom_type == "Polygon" and not pg.is_empty and pg.area > pen ** 2 * 0.5:
                    out.append(np.asarray(pg.exterior.coords))
    return out


def drips(shape_rings: list[np.ndarray], rng, *, H: float, n: int = 6, length=(0.02, 0.07),
          pen: float = 1.7) -> list[np.ndarray]:
    """Shapes shed lines: from the lowest points of some masses, short
    wavering lines fall downward, some ending in a bead (the reference's
    drips; a metamorphosis shape → line)."""
    from shapely.geometry import Polygon
    big = [q for q in shape_rings if len(q) >= 8 and abs(Polygon(q).area) > (6 * pen) ** 2]
    if not big:
        return []
    out = []
    used: dict[int, int] = {}
    for _ in range(n):
        k = int(rng.integers(len(big)))
        if used.get(k, 0) >= 2:            # ≤ 2 drips per mass: a comb of parallel drips reads as hatching
            continue
        used[k] = used.get(k, 0) + 1
        q = big[k]
        i = int(np.argmax(q[:, 1] + rng.normal(0, np.ptp(q[:, 1]) * 0.15 + 1e-9, len(q))))
        p0 = q[i]
        L = rng.uniform(*length) * H
        m = max(int(L / 2), 4)
        y = np.linspace(0, L, m)
        x = gaussian_filter1d(np.cumsum(rng.normal(0, 1.0, m)), 3) * pen * 0.6 * rng.choice([-1, 1])
        line = np.column_stack([p0[0] + x, p0[1] + y])
        out.append(line)
        if rng.random() < 0.5:
            out += _disc_rings(line[-1] + np.array([0, pen * 1.2]), pen * rng.uniform(1.2, 2.2), pen)
    return out


# --- the pipeline ----------------------------------------------------------------

def compose(seed: int, size=(840, 1200), *, structure="tree", field: Field | Callable | str = "axis",
            hands: HandField | str = "hokusai", signs: int | bool = 6, tremor: float = 0.0,
            amount: float = 0.6, structure_params: dict | None = None, echo: int = 0, drip: int = 0,
            nib_w: float | None = None, shape_w: float | None = None, phi_deg: float = 60.0,
            pen_px: float | None = None, overlap: float | None = None, piece: float | None = None,
            engine_name: str = "auto", label: str = "", sign_w: float | None = None,
            field_kw: dict | None = None, script: int = 0, script_hand: str | None = None,
            clip: bool = True, nib_style=None) -> Composition:
    """structure → hands (per-line runs, cross-faded) → optional tremor →
    regime r(s) sampled from `field` → RegimeStroke rendering → signs,
    echoes, drips → plotter polylines (px, y down, on a `size` sheet).

    field: a Field, or a callable (structure Drawing) → Field (for fields
    derived from the structure), or a preset name (`PRESETS`).
    hands: a HandField or one hand name. Lines that come already handed
    (structure "grammar"/"single") are not restyled.
    clip=False keeps marks that run past the sheet edge whole (the caller
    fits the ink, e.g. regime_compose.sheet_to_mm(fit_ink=True)).
    nib_style: how nib ribbons are inked (gesture.penrender.nib_style):
    None/"a" outline (default), "b"/"b+"/"c"/"e", a combination such as
    ["b+", "c"] or "c+e", or a per-mark mix {"c": .5, "e": .5}.
    Deterministic in seed. Widths default to fractions of the sheet height:
    nib 1.0 %, shape 3.0 %; pen = 0.4 mm on A4 portrait."""
    W, H = int(size[0]), int(size[1])
    aspect = H / W
    rng = np.random.default_rng(seed)
    s_rng, h_rng, t_rng, g_rng, e_rng = (np.random.default_rng(int(x)) for x in rng.integers(0, 2 ** 31, 5))
    pen = pen_px if pen_px is not None else pen_px_for((W, H))
    nib_w = nib_w if nib_w is not None else 0.013 * H
    shape_w = shape_w if shape_w is not None else 0.030 * H
    # the structure needs a hand only when it comes already handed; the
    # field may need the structure; a hand field may need the field
    pre_hands = hands if isinstance(hands, (HandField, str)) else None
    main_hand = (pre_hands.hands[0] if isinstance(pre_hands, HandField) else pre_hands) or "hokusai"
    if structure == "grammar" and isinstance(pre_hands, HandField) and len(pre_hands.hands) > 1:
        st, handed = _grammar_mixed(s_rng, (W, H), pre_hands, structure_params), True
    else:
        st, handed = make_structure(structure, s_rng, (W, H), hand=main_hand, params=structure_params)
    if isinstance(field, str):
        fobj = {**PRESETS, **EXTRA_PRESETS}[field](st, seed, aspect, **(field_kw or {}))
    elif isinstance(field, Field):
        fobj = field
    else:
        fobj = field(st)
    if isinstance(hands, HandField):
        hf = hands
    elif isinstance(hands, str):
        hf = single_hand(hands)
    else:
        hf = hands(fobj, aspect, seed)
    if structure == "grammar" and not isinstance(pre_hands, HandField) and len(hf.hands) > 1:
        st, handed = _grammar_mixed(s_rng, (W, H), hf, structure_params), True
    # hands
    R = st.ref_length()
    lines, line_hands = [], []
    if handed or amount <= 0:
        for s in st.strokes:
            p = np.vstack([s.points, s.points[:1]]) if s.closed else s.points
            lines.append(p)
            line_hands.append(s.meta.get("hand", main_hand))
    else:
        from . import restyle as rs
        outs = []
        for i, s in enumerate(st.strokes):
            p = resample(s.points, 2.0)
            runs = hand_runs(p, hf, (W, H), h_rng, piece=piece or 0.06 * H)
            lr = np.random.default_rng([seed, i])
            q = restyle_line(p, runs, lr, amount=amount, R=R, overlap=overlap or 0.02 * H)
            outs.append(Stroke(q, closed=False, meta=dict(s.meta)))
            hs = [h for _, _, h in runs]
            line_hands.append(max(dict.fromkeys(hs), key=hs.count))  # ties: first run wins (set order is hash-seeded)
        welded, _ = rs.weld_junctions(st, outs, R) if len(outs) > 1 else (outs, {})
        lines = [w.points for w in welded]
    if script:
        sh = script_hand or (SHIKASTA if SHIKASTA in hf.hands else main_hand)
        extra = script_fill(fobj, sh, np.random.default_rng([seed, 99]), (W, H), tiles=int(script))
        lines = list(lines) + extra
        line_hands = list(line_hands) + [sh] * len(extra)
    # tremor (on centrelines, before width, so ribbons tremble with their line)
    if tremor and tremor > 0:
        lines = _tremor_lines(lines, line_hands, (W, H), t_rng, tremor, R)
    # regimes
    nib_r = None
    if nib_style not in (None, "a"):
        from . import penrender as _pr
        nib_r = _pr.nib_style(nib_style, seed=seed)
    eng = engine(engine_name, nib_renderer=nib_r)
    ffn = lambda q: fobj.at_px(q, (W, H))  # noqa: E731
    polys: list[np.ndarray] = []
    centre, regs = [], []
    shape_rings: list[np.ndarray] = []
    tags: list[tuple[int, str]] = []          # (group, kind) per polyline, for path ordering
    next_gid = 0
    for q in lines:
        if len(q) < 2:
            continue
        rsk = eng.stroke(q, ffn, phi=math.radians(phi_deg), W=nib_w, shape_w=shape_w, pen=pen)
        rp = _as_polylines(eng.render(rsk, pen=pen))
        if nib_r is not None:
            # a styled render is chained (passes and outline interleave), so it
            # is not prefix-ordered: tag the whole mark as fill if it pools
            fw = getattr(rsk, "fill_weight", None)
            pooled = fw is not None and float(np.max(fw())) > 0.0
            n_out = 0 if pooled else len(rp)
        else:
            n_out = _n_outline(eng, rsk, pen, len(rp))
        tags += [(next_gid, "line")] * n_out
        comp = fill_components(rp[n_out:], pen)
        tags += [(next_gid + 1 + int(c), "fill") for c in comp]
        next_gid += 2 + (int(max(comp)) if len(comp) else 0)
        polys += rp
        centre.append(np.asarray(getattr(rsk, "points", q)))
        rr = np.asarray(getattr(rsk, "r", np.zeros(0)))
        regs.append(rr)
        if rr.size and rr.max() > 1.5:
            # echoes/drips grow from the plain render, so the nib style changes
            # only the ink, never the composition
            src = rp if nib_r is None else _as_polylines(eng.render(rsk, pen=pen, styled=False))
            shape_rings += _closed_rings(src)
    # signs, echoes, drips
    n_signs = int(signs) if not isinstance(signs, bool) else (6 if signs else 0)
    sign_polys: list[np.ndarray] = []
    sign_groups: list[list[np.ndarray]] = []
    if n_signs > 0:
        sw = sign_w if sign_w is not None else 0.6 * nib_w
        try:
            sign_groups = [_as_polylines(g) for g in eng.signs(centre, g_rng, n=n_signs, w=sw, pen=pen,
                                                                grouped=True)]
        except Exception as e:  # noqa: BLE001
            warnings.warn(f"place_signs failed ({e!r}); stand-in signs used")
            sign_groups = [_as_polylines(standin_signs(centre, g_rng, n=n_signs, size_px=3 * sw, pen=pen))]
    sign_polys = [q for g in sign_groups for q in g]
    echo_polys = echoes(shape_rings, centre, fobj, (W, H), e_rng, n=echo, sign_px=0.016 * H, pen=pen) if echo else []
    drip_polys = drips(shape_rings, e_rng, H=H, n=drip, pen=pen) if drip else []
    gid = next_gid
    for g in sign_groups:
        t, gid = nest_tags(g, gid, pen, "sign")
        tags += t
    for extra, kind in ((echo_polys, "echo"), (drip_polys, "drip")):
        t, gid = nest_tags(extra, gid, pen, kind)
        tags += t
    tagged = [(piece, t) for q, t in zip(polys + sign_polys + echo_polys + drip_polys, tags) if len(q) >= 2
              for piece in (clip_to_sheet(q, W, H) if clip else [np.asarray(q, float)])]
    allp = [q for q, _ in tagged]
    rcat = np.concatenate([r for r in regs if r.size]) if any(r.size for r in regs) else np.zeros(0)
    meta = {"label": label, "seed": seed, "structure": structure if isinstance(structure, str) else "given",
            "field": fobj.name, "hands": hf.hands, "hand_field": hf.name, "engine": eng.name, "signs_engine":
            eng.signs_name, "pen_px": pen, "nib_w": nib_w, "shape_w": shape_w, "tremor": tremor,
            "n_lines": len(lines), "n_polylines": len(allp), "n_signs": len(sign_polys), "n_echo": len(echo_polys),
            "n_drip": len(drip_polys), "script": int(script),
            "regime_share": {"line": float(np.mean(rcat < 0.5)) if rcat.size else 0.0,
                             "nib": float(np.mean((rcat >= 0.5) & (rcat < 1.5))) if rcat.size else 0.0,
                             "shape": float(np.mean(rcat >= 1.5)) if rcat.size else 0.0},
            "line_hands": line_hands}
    return Composition(allp, (W, H), meta, centre, regs, groups=[t[0] for _, t in tagged],
                       kinds=[t[1] for _, t in tagged])


def clip_to_sheet(q: np.ndarray, W: float, H: float) -> list[np.ndarray]:
    """The parts of a polyline inside the sheet [0, W] × [0, H]. Cut, not
    clamped: clamping (np.clip) flattened everything beyond the edge onto
    the border as a straight bar along it (a ribbon end became a ruled
    line on the r6 Strahler sheet)."""
    q = np.asarray(q, float)
    if q.min(axis=0)[0] >= 0 and q.min(axis=0)[1] >= 0 and q.max(axis=0)[0] <= W and q.max(axis=0)[1] <= H:
        return [q]
    from shapely.geometry import LineString, box
    g = LineString(q).intersection(box(0, 0, W, H))
    parts = [g] if g.geom_type == "LineString" else [x for x in getattr(g, "geoms", []) if x.geom_type == "LineString"]
    out = [np.asarray(x.coords, float) for x in parts if not x.is_empty and len(x.coords) >= 2]
    return [o for o in out if float(np.sum(np.linalg.norm(np.diff(o, axis=0), axis=1))) > 1e-6]


def _n_outline(eng: "Engine", rsk, pen: float, n_all: int) -> int:
    """How many of a render's polylines precede the mass fill: regime.render
    returns runs + outlines, then the concentric fill (its documented order),
    so the count is the length of the same render without fill. Strokes that
    never fill skip the second render."""
    fw = getattr(rsk, "fill_weight", None)
    try:
        if fw is None or float(np.max(fw())) <= 0.0:
            return n_all
        return min(len(_as_polylines(eng.render(rsk, pen=pen, fill=False))), n_all)
    except TypeError:                     # stand-in engine: no fill switch
        return n_all


def fill_components(fill: list[np.ndarray], pen: float) -> list[int]:
    """Connected-mass index of each concentric fill path of one stroke: one
    stroke can swell into several separate masses, and its fill visits them
    depth by depth. Paths whose 0.75-pen buffers touch belong to one mass
    (adjacent insets are one pen apart)."""
    if not fill:
        return []
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    bufs = [LineString(q).buffer(0.75 * pen, quad_segs=2) for q in fill]
    parent = list(range(len(fill)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    tree = STRtree(bufs)
    for i, b in enumerate(bufs):
        for j in tree.query(b, predicate="intersects"):
            a, c = find(i), find(int(j))
            if a != c:
                parent[max(a, c)] = min(a, c)
    roots = {}
    return [roots.setdefault(find(i), len(roots)) for i in range(len(fill))]


def nest_tags(polys: list[np.ndarray], gid: int, pen: float, kind: str) -> tuple[list[tuple[int, str]], int]:
    """(group, kind) tags for a list of small marks by containment: a path
    lying inside a closed ring of the list joins that ring's (outermost)
    group as "fill"; everything else starts its own group. Returns the tags
    and the next free group id."""
    from shapely.geometry import Polygon
    from shapely.prepared import prep
    rings = []
    for k, q in enumerate(polys):
        if len(q) >= 4 and np.linalg.norm(q[0] - q[-1]) < 1e-6:
            pg = Polygon(q).buffer(0.5 * pen)
            if not pg.is_empty and pg.area > 0:
                rings.append((pg.area, k, prep(pg)))
    rings.sort(key=lambda t: -t[0])
    owner = [-1] * len(polys)
    from shapely.geometry import MultiPoint
    for area, k, pg in rings:                 # biggest first: outermost container wins
        for j, q in enumerate(polys):
            if j == k or owner[j] >= 0 or owner[k] == j:
                continue
            if pg.contains(MultiPoint(np.asarray(q[:: max(1, len(q) // 24)]))):
                owner[j] = k if owner[k] < 0 else owner[k]
    tags, ids = [], {}
    for j in range(len(polys)):
        root = j if owner[j] < 0 else owner[j]
        if root not in ids:
            ids[root] = gid
            gid += 1
        tags.append((ids[root], kind if owner[j] < 0 else "fill"))
    return tags, gid


def _tremor_lines(lines, hands, size, rng, amount, R):
    """Tremor per hand group on the centrelines (composite's per-hand
    default model; shikasta borrows hokusai's)."""
    try:
        from experiments import composite as cp
        from . import tremor as tr
    except Exception:  # noqa: BLE001
        return lines
    out = list(lines)
    for h in sorted(set(hands)):
        idx = [i for i, x in enumerate(hands) if x == h]
        art = h if h in ("matisse", "hokusai", "ingres") else "hokusai"
        try:
            model, mode, _ = cp.tremor_model(art)
        except Exception:  # noqa: BLE001
            continue
        d = Drawing([Stroke(lines[i]) for i in idx], size=size)
        w = cp.hand_w(art) * R
        t = tr.apply_tremor(d, model, np.random.default_rng(int(rng.integers(1 << 31))), amount, w=w, mode=mode)
        for k, i in enumerate(idx):
            out[i] = t.strokes[k].points
    return out


# --- named field presets (structure, seed, aspect) → Field --------------------------

def _p_axis(st, seed, aspect, **kw):
    return warp(axis(0.6, core=0.03, band=0.085, bleed=0.035, seed=seed, aspect=aspect, taper=0.4), seed, amp=0.02)


def _p_bands(st, seed, aspect, **kw):
    return bands((0.28, 0.5, 0.74), (0.0, 1.1, 0.3, 1.7), bleed=0.05, seed=seed, aspect=aspect)


def _p_margins(st, seed, aspect, **kw):
    return warp(maximum(margins(0.16, sides="lr", margin_value=1.1, seed=seed, aspect=aspect),
                        radial((0.5, 0.42), (0.06, 0.16), (2.0, 0.9, 0.0), aspect=aspect, lobes=3, lobe_amp=0.3,
                               seed=seed)), seed, amp=0.03)


def _p_noise(st, seed, aspect, **kw):
    return noise_fronts(seed, **{"scale": 0.13, **kw}, aspect=aspect)


def _p_strahler(st, seed, aspect, **kw):
    return structure_field(st, "strahler", sigma=0.025, gamma=1.3)


def _p_density(st, seed, aspect, **kw):
    return levels(structure_field(st, "density", sigma=0.03), (0.6, 1.5), (0.0, 1.0, 2.0), 0.25)


def _p_trunk(st, seed, aspect, **kw):
    return maximum(structure_field(st, "trunk", reach=0.05, values=(0.0, 2.0)),
                   scale(noise_fronts(seed, scale=0.1, thresholds=(0.6, 1.6), values=(0.0, 1.0, 1.8),
                                      aspect=aspect), 0.9))


def _p_sense(st, seed, aspect, **kw):
    """The mixed field closest to the reference's distribution: an axis on the
    structure's trunk that alternates between nib ribbon and mass along its
    length, script (nib) zones in the right margin and the top of a centre
    column, a line tangle elsewhere, a few noise islands of nib (rarely
    shape); all fronts warped."""
    trunk = structure_field(st, "trunk", reach=0.03, values=(0.0, 2.0), gamma=1.0)
    along = noise_fronts(seed + 5, scale=0.09, thresholds=(0.1, 0.9), values=(1.0, 1.5, 2.0), bleed_lo=0.05,
                         bleed_hi=0.5, aspect=aspect)
    axis_ = minimum(trunk, along)
    script = margins(0.14, sides="r", margin_value=1.0, inner_value=0.0, seed=seed, aspect=aspect)
    column = Field(lambda u: 1.0 * smoothstep((0.45 - u[:, 1]) / 0.1) * smoothstep(1 - np.abs(u[:, 0] - 0.42) / 0.09),
                   "column", aspect)
    islands = noise_fronts(seed + 7, scale=0.08, thresholds=(1.3, 2.2), values=(0.0, 1.0, 2.0), aspect=aspect)
    parts = [script, column, islands] if kw.get("no_axis") else [axis_, script, column, islands]
    return warp(maximum(*parts), seed, amp=0.02)


def _p_sense_noaxis(st, seed, aspect, **kw):
    return _p_sense(st, seed, aspect, no_axis=True)


PRESETS: dict[str, Callable] = {
    "axis": _p_axis, "bands": _p_bands, "margins": _p_margins, "noise": _p_noise,
    "strahler": _p_strahler, "density": _p_density, "trunk": _p_trunk, "sense": _p_sense,
}
EXTRA_PRESETS = {"sense_noaxis": _p_sense_noaxis}
FAMILY = {"axis": "authored", "bands": "authored", "margins": "authored", "noise": "procedural",
          "strahler": "structure", "density": "structure", "trunk": "mixed", "sense": "mixed",
          "sense_noaxis": "mixed"}
