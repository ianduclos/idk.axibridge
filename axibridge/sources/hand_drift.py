"""Hand Drift: one line whose hand drifts along a route of learned hands.

The gesture research's round-8 "limb" (tools/gesture/results/
hybrid_hands-2026-10-16.md), made a bench as it is (Ian, round-8 review,
plan docs/superpowers/plans/2026-10-17-hand-drift-bench.md). The engine is a
frozen copy in `_hand_drift/` — research keeps moving, a kept layer does not.

A line of `length` R (R = the research frame's reference length) is grown
chunk by chunk from 2–4 hands. Each hand speaks pure on a plateau and
cross-fades into the next along the line's arc length. Switches:

- blend — `mixture` (each token from one hand, chosen by weight) or `interp`
  (tokens moved toward the other hand's nearest token: tokens neither hand has);
- joins — `smooth` (every chunk starts fresh, κ continuous at the joint) or
  `chain` (each chunk continues the previous chunk's context: in short-stroke
  hands that throws straight runs and corners into the line — the "failure"
  Ian rated one of the best);
- lines 1–8 with route per line `same` / `rotate` / `shuffle` / `each` (each
  line ONE hand whole, no drift: distinct grammars side by side, never
  averaged);
- regimes — `off` (wire), `timing` (a dancer's tempo: stillness pools ink
  into masses, flow leaves a nib held at the wrist, speed a dry line) or
  `field` (a noise-front preset over the frame), inked in a nib style.

Geometry: each line is grown in the research frame (1000×1200 px), then all
lines are fitted at one common scale into a grid of cells inside the
`width`×`height` mm frame (`placement_frame`, fitted onto the bed at layer
creation). Wire lines are open paths; with regimes on, the outline rings of
ribbons and masses are closed `filled=True` paths (so they occlude), every
other pass (line runs, fills, lanes) open or closed `filled=False`.

Pure and deterministic: every random draw comes from numpy Generators seeded
from `seed` (line i uses seed + i, as the research sheets did); nothing
iterates a set or a dict whose order could depend on PYTHONHASHSEED.
"""
from __future__ import annotations

import contextvars
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source, report_progress
from ..render_work import checkpoint
from ._hand_drift import FROZEN_FROM
from ._hand_drift import hands as H
from ._hand_drift import hybrid as hy
from ._hand_drift import penrender as pr
from ._hand_drift import prosody as pz
from ._hand_drift import regime as rg

Hand = Literal["matisse", "hokusai", "ingres", "shikasta", "nastaliq", "marden", "lichtenberg", "bubble"]
OptionalHand = Literal["none", "matisse", "hokusai", "ingres", "shikasta", "nastaliq", "marden",
                       "lichtenberg", "bubble"]
Tempo = Literal["staccato", "levitation", "fluidity", "particles", "cmu_49_10", "cmu_55_mantis"]

RESEARCH_SIZE = (1000.0, 1200.0)       # the drift's research frame (px)
_INK = "#100f0f"


class HandDriftParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    hand_1: Hand = Field(default="matisse", title="Hand 1",
                         description="Where the line starts (route order)")
    hand_2: Hand = Field(default="shikasta", title="Hand 2")
    hand_3: OptionalHand = Field(default="lichtenberg", title="Hand 3")
    hand_4: OptionalHand = Field(default="none", title="Hand 4")
    plateau: float = Field(default=0.12, ge=0.0, le=0.6, title="Plateau",
                           description="Share of the line each hand speaks pure before it cross-fades")
    blend: Literal["mixture", "interp"] = Field(
        default="mixture", title="Blend",
        description="mixture: each token from one hand by weight; interp: tokens moved toward the "
                    "other hand's nearest token")
    joins: Literal["smooth", "chain"] = Field(
        default="smooth", title="Joins",
        description="smooth: chunks start fresh, curvature continuous; chain: chunks continue the "
                    "previous context (straight runs and corners break in)")
    length: float = Field(default=6.0, ge=1.0, le=12.0, title="Length (R)",
                          description="Line length in reference lengths of the research frame")
    lines: int = Field(default=1, ge=1, le=8, title="Lines")
    route_per_line: Literal["same", "rotate", "shuffle", "each"] = Field(
        default="same", title="Route per line",
        description="same / rotate / shuffle the route per line; each: every line keeps ONE hand "
                    "whole (no drift)")
    regimes: Literal["off", "timing", "field"] = Field(
        default="off", title="Regimes",
        description="off: wire; timing: a dancer's tempo makes nib and mass; field: a noise-front "
                    "preset over the frame")
    timing: Tempo = Field(default="staccato", title="Tempo",
                          description="Frozen dance tempo profile (timing regime)")
    wrist_nib: bool = Field(default=True, title="Wrist holds the nib",
                            description="Timing regime: the nib angle follows the dancer's wrist; "
                                        "off = the fixed nib angle")
    amount: float = Field(default=1.0, ge=0.0, le=2.0, title="Regime amount",
                          description="Scales the regime value (0 = wire, 2 = twice as heavy)")
    nib_width: float = Field(default=3.5, ge=0.5, le=12.0, title="Nib width (mm)")
    mass_width: float = Field(default=9.0, ge=1.0, le=30.0, title="Mass width (mm)")
    nib_angle: float = Field(default=35.0, ge=-90.0, le=90.0, title="Nib angle (°)")
    ink: Literal["a", "b+", "c", "e", "c+e"] = Field(
        default="e", title="Ink style",
        description="a: outline only; b+: concentric insets; c: lanes along the stroke; "
                    "e: nib-point traces; c+e: both pass families")
    pen: float = Field(default=0.4, ge=0.1, le=2.0, title="Pen width (mm)")
    width: float = Field(default=267.0, ge=40.0, le=300.0, title="Width (mm)")
    height: float = Field(default=180.0, ge=40.0, le=218.0, title="Height (mm)")
    seed: int = Field(default=7000, ge=0, le=2_147_483_647, title="Seed")

    def route(self) -> list[str]:
        return [h for h in (self.hand_1, self.hand_2, self.hand_3, self.hand_4) if h != "none"]


def line_routes(params: HandDriftParams) -> list[list[str]]:
    """The route each line follows (`each`: one hand per line, cycled)."""
    route = params.route()
    k = len(route)
    out = []
    for i in range(params.lines):
        if params.route_per_line == "each":
            out.append([route[i % k]])
        elif params.route_per_line == "rotate":
            j = i % k
            out.append(route[j:] + route[:j])
        elif params.route_per_line == "shuffle" and i > 0:
            perm = np.random.default_rng([params.seed, i, 1]).permutation(k)
            out.append([route[int(j)] for j in perm])
        else:
            out.append(list(route))
    return out


def _grid(n: int, frame: tuple[float, float], boxes: list[tuple[float, float]]) -> tuple[int, int, float]:
    """(cols, rows, common scale) placing n line boxes in equal cells: the
    layout with the largest common scale (ties: fewer rows)."""
    W, H = frame
    best = None
    for cols in range(1, n + 1):
        rows = -(-n // cols)
        cw, ch = W / cols, H / rows
        s = min(min(cw / max(bw, 1e-9), ch / max(bh, 1e-9)) for bw, bh in boxes)
        if best is None or s > best[2] + 1e-12:
            best = (cols, rows, s)
    return best


def _ink_reach(params: HandDriftParams) -> float:
    """How far ink can spread from a centreline (mm): the inset that keeps
    the rendered document inside the frame."""
    if params.regimes == "off" or params.amount <= 0:
        return 0.5 * params.pen
    mass = params.mass_width * (1.6 if params.regimes == "timing" else 1.0)
    jitter = 3.0 * params.pen if params.regimes == "timing" else 0.0
    return 0.5 * max(mass, params.nib_width) + 0.5 * params.pen + jitter


def drift_centrelines(params: HandDriftParams) -> list[np.ndarray]:
    """Every line grown in the research frame, then fitted (one common scale)
    into its grid cell of the mm frame. Points in mm, frame origin."""
    routes = line_routes(params)
    total = len(routes)
    raw = []
    for i, route in enumerate(routes):
        report_progress(0.6 * i / total, f"growing line {i + 1} of {total}")
        grams = [H.load_hand(h) for h in route]
        res = hy.drift_line(grams, np.random.default_rng(params.seed + i), total=params.length,
                            mode=params.blend, size=RESEARCH_SIZE, plateau=params.plateau,
                            context="chain" if params.joins == "chain" else "kappa", checkpoint=checkpoint)
        raw.append(res["points"])
    inset = _ink_reach(params)
    W = max(params.width - 2 * inset, 1.0)
    Hh = max(params.height - 2 * inset, 1.0)
    boxes = [tuple(np.ptp(p, axis=0)) for p in raw]
    cols, rows, s = _grid(len(raw), (W, Hh), boxes)
    cw, ch = W / cols, Hh / rows
    out = []
    for i, p in enumerate(raw):
        r, c = divmod(i, cols)
        lo, hi = p.min(axis=0), p.max(axis=0)
        centre = np.array([inset + (c + 0.5) * cw, inset + (r + 0.5) * ch])
        out.append((p - (lo + hi) / 2) * s + centre)
    return out


def _strokes(params: HandDriftParams, lines: list[np.ndarray]) -> list[rg.RegimeStroke]:
    W = params.nib_width
    phi = math.radians(params.nib_angle)
    if params.regimes == "timing":
        tm = H.load_timing(params.timing)
        sts = pz.danced(lines, tm, W=W, shape_w=params.mass_width, pen=params.pen, amount=params.amount)
        if not params.wrist_nib:
            sts = [rg.make(st.points, st.r, phi=phi, W=st.W, mass=st.mass) for st in sts]
        return sts
    aspect = params.height / params.width
    grid = pz.noise_fronts(params.seed, aspect=aspect)
    field = pz.field_sampler(grid, (params.width, params.height))
    out = []
    for p in lines:
        st = rg.from_field(p, field, phi=phi, W=W, mass=params.mass_width)
        out.append(rg.make(st.points, np.clip(params.amount * st.r, 0.0, 2.0), phi=phi, W=W,
                           mass=params.mass_width))
    return out


SIMPLIFY_MM = 0.01      # sub-visible (the plot pass's own simplify baseline)


def _simplified(paths: list[np.ndarray]) -> list[np.ndarray]:
    """Douglas-Peucker at SIMPLIFY_MM: the passes are resampled every
    ≤ 0.5 pen, far denser than a plotter or the canvas needs. End points
    (and so ring closure) are kept."""
    import shapely
    arrs = [np.asarray(p, dtype=np.float64) for p in paths if len(p) >= 2]
    if not arrs:
        return []
    geoms = shapely.linestrings(np.vstack(arrs), indices=np.repeat(np.arange(len(arrs)), [len(a) for a in arrs]))
    out = []
    for p, g in zip(arrs, shapely.simplify(geoms, SIMPLIFY_MM, preserve_topology=False)):
        c = shapely.get_coordinates(g)
        out.append(c if len(c) >= 2 else p)
    return out


def _closed(ring: np.ndarray) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in ring]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    pts[-1] = pts[0]          # exact closure (model.is_closed)
    return pts


def _fit_inside(paths: list[Path], width: float, height: float) -> list[Path]:
    """Safety net for the placement contract: if ink still overhangs the
    frame, shrink everything uniformly about the frame centre."""
    xs = [x for p in paths for x, _ in p.points]
    ys = [y for p in paths for _, y in p.points]
    if not xs:
        return paths
    lo_x, hi_x, lo_y, hi_y = min(xs), max(xs), min(ys), max(ys)
    if lo_x >= 0 and lo_y >= 0 and hi_x <= width and hi_y <= height:
        return paths
    cx, cy = width / 2, height / 2
    k = min(1.0,
            cx / max(cx - lo_x, hi_x - cx, 1e-9),
            cy / max(cy - lo_y, hi_y - cy, 1e-9)) * (1 - 1e-9)
    out = []
    for p in paths:
        pts = [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in p.points]
        if p.filled:
            pts[-1] = pts[0]
        out.append(Path(points=pts, filled=p.filled))
    return out


def render_paths(params: HandDriftParams) -> list[Path]:
    lines = drift_centrelines(params)
    if params.regimes == "off":
        return _fit_inside([Path(points=[(float(x), float(y)) for x, y in p]) for p in _simplified(lines)],
                           params.width, params.height)
    strokes = _strokes(params, lines)

    def ink_one(st: rg.RegimeStroke) -> list[Path]:
        checkpoint()
        rings, rest = pr.ink([st], params.ink, params.pen)
        rings = [r for r in rings if len(r) >= 4]
        out = []
        for full, r in zip(rings, _simplified(rings)):
            ring = r if len(r) >= 4 else full
            if len(ring) >= 4:
                out.append(Path(points=_closed(ring), filled=True))
        for q in _simplified(rest):
            if len(q) >= 2:
                out.append(Path(points=[(float(x), float(y)) for x, y in q], filled=False))
        return out

    # Each line is one mark, inked independently (shapely and the KD queries
    # release the GIL): a thread per line, results in line order, so the
    # output is the same as a serial loop. Each task runs in a copy of the
    # caller's context so preview cancellation still reaches `checkpoint`.
    paths: list[Path] = []
    with ThreadPoolExecutor(max_workers=min(4, max(len(strokes), 1))) as ex:
        futures = [ex.submit(contextvars.copy_context().run, ink_one, st) for st in strokes]
        for i, fut in enumerate(futures):
            paths += fut.result()
            report_progress(0.6 + 0.4 * (i + 1) / len(futures), f"inked line {i + 1} of {len(futures)}")
    return _fit_inside(paths, params.width, params.height)


@register_source
class HandDriftSource(SourceModule):
    id = "hand_drift"
    label = "Hand Drift"
    description = ("One line whose hand drifts along a route of learned hands (Matisse, Hokusai, "
                   "Ingres, shikasta and nasta'liq exercises, Marden, Lichtenberg, bubble chamber), "
                   "with switchable blend, joins, routes per line and regimes")
    orientation = "geometry"
    library_bench = True
    bench = {"adapter": "hand-drift", "version": 1, "modes": ["new", "resume"]}
    Params = HandDriftParams

    def placement_frame(self, params: dict) -> tuple[float, float] | None:
        return float(params.get("width", 267.0)), float(params.get("height", 180.0))

    def generate(self, params: HandDriftParams) -> PathDocument:
        paths = render_paths(params)
        route = " → ".join(params.route())
        return PathDocument(
            layers=[Layer(id=1, name="Hand drift", color=_INK, paths=paths)] if paths else [],
            width=params.width, height=params.height,
            source=f"hand_drift {route} ({params.blend}, {params.joins}, {params.regimes}; "
                   f"engine {FROZEN_FROM})",
        )
