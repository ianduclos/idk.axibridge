"""Eyelets — small circles sprouted where the line has structure: curvature
extrema and stroke ends. Structure-following, never random scatter (the
demo's little rivets/grommets at corners and junctions).

Input paths ALWAYS pass through unchanged; eyelet circles are ADDED
(docs/plans/response-brushes.md Part 3 — see that file for the demo look).

Mechanics, one line each:

* resample at ~0.5mm so curvature can be read at a consistent scale,
  independent of the input's own vertex density;
* curvature is the signed discrete turn angle at each point (angle between
  the incoming and outgoing chord) — `sensitivity` maps to a degree
  threshold (low sensitivity catches gentle bends, 1.0 catches only the
  sharpest kinks), so a smooth arc (no real corners) stays bare while an
  angular gesture gets marked;
* consecutive above-threshold samples are one corner (resampling can spread
  a single kink over a couple of points) — only the sharpest sample in each
  run becomes a candidate, then candidates are accepted greedily in arc-
  length order with `spacing` between them, so eyelets read as sparse
  rivets, never a chain of rings;
* each eyelet radius is jittered +-30% from the seed, and nudged `nudge` mm
  outward from the corner (away from the turn) along the local normal, so
  rings sit like beads just off the line rather than dead-centered;
* `at_ends` adds one eyelet at each open path's start and end (skipped for
  closed paths, which have no distinct ends).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from ..model import Path
from ..registry import EffectContext, EffectModule, register_effect

_STEP = 0.5  # mm, internal resample step for curvature sampling
_CIRCLE_SEGS = 20


class EyeletsParams(BaseModel):
    radius: float = Field(default=1.4, ge=0.4, le=6.0, title="Radius (mm)",
                          description="Nominal eyelet radius (jittered +-30% per eyelet)")
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0, title="Sensitivity",
                               description="Curvature threshold — 1.0 marks only the sharpest corners")
    spacing: float = Field(default=12.0, ge=2.0, le=60.0, title="Spacing (mm)",
                           description="Minimum arc-length gap between eyelets")
    at_ends: bool = Field(default=True, title="Mark ends",
                          description="Add an eyelet at each open path's start and end")
    nudge: float = Field(default=0.6, ge=0.0, le=4.0, title="Nudge (mm)",
                         description="Push eyelets outward from the corner, off the line",
                         json_schema_extra={"group": "Fine tuning"})
    seed: int = Field(default=0, ge=0, le=99999, title="Seed",
                      json_schema_extra={"group": "Fine tuning"})


def _hash01(i: int, seed: int) -> float:
    h = (i * 374761393 + seed * 668265263) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / 0xFFFFFF


def _resample(points: list[tuple[float, float]], step: float) -> list[tuple[float, float]]:
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    carry = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        seg = math.dist((x0, y0), (x1, y1))
        if seg < 1e-12:
            continue
        d = step - carry
        while d <= seg:
            t = d / seg
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
            d += step
        carry = seg - (d - step)
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def _angle_between(v1: tuple[float, float], v2: tuple[float, float]) -> float:
    """Signed turn angle from v1 to v2, radians in [-pi, pi]. Sign follows
    the standard CCW-positive convention (cross > 0 = left turn)."""
    d1, d2 = math.hypot(*v1), math.hypot(*v2)
    if d1 < 1e-9 or d2 < 1e-9:
        return 0.0
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    return math.atan2(cross, dot)


def _dedupe_closed(pts: list[tuple[float, float]], closed: bool) -> list[tuple[float, float]]:
    """Drop the duplicated closing point for closed paths so every downstream
    index space is the cyclic point set itself, with no seam special-case
    to forget (the caller maps a picked `core` index back via `core[idx]`,
    identical to `pts[idx]` since the duplicate is only ever the tail)."""
    if closed and len(pts) > 1 and pts[0] == pts[-1]:
        return pts[:-1]
    return list(pts)


def _turn_angles(core: list[tuple[float, float]], closed: bool) -> list[float]:
    """Signed turn angle per core point. Closed paths wrap the neighbor
    lookup cyclically so the corner AT the seam is evaluated correctly."""
    m = len(core)
    if m < 3:
        return [0.0] * m
    angles = []
    for i in range(m):
        if closed:
            a, b, c = core[(i - 1) % m], core[i], core[(i + 1) % m]
        else:
            a = core[i - 1] if i > 0 else core[i]
            b = core[i]
            c = core[i + 1] if i < m - 1 else core[i]
        v_in = (b[0] - a[0], b[1] - a[1])
        v_out = (c[0] - b[0], c[1] - b[1])
        angles.append(_angle_between(v_in, v_out))
    return angles


def _normals(core: list[tuple[float, float]], closed: bool) -> list[tuple[float, float]]:
    m = len(core)
    out = []
    for i in range(m):
        if closed:
            a, b = core[(i - 1) % m], core[(i + 1) % m]
        else:
            a = core[i - 1] if i > 0 else core[i]
            b = core[i + 1] if i < m - 1 else core[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        tx, ty = (dx / d, dy / d) if d > 1e-12 else (1.0, 0.0)
        out.append((-ty, tx))
    return out


def _select_sites(core: list[tuple[float, float]], angles: list[float], threshold: float,
                   spacing: float, at_ends: bool, closed: bool) -> list[int]:
    m = len(core)
    cum = [0.0]
    for a, b in zip(core, core[1:]):
        cum.append(cum[-1] + math.dist(a, b))

    # group consecutive above-threshold samples (one kink can spread over a
    # couple of resampled points); keep only the sharpest sample per group
    groups: list[tuple[int, int]] = []
    in_group = False
    group_start = 0
    for i in range(m):
        above = abs(angles[i]) >= threshold
        if above and not in_group:
            in_group, group_start = True, i
        elif not above and in_group:
            groups.append((group_start, i - 1))
            in_group = False
    if in_group:
        groups.append((group_start, m - 1))

    # a closed path's index-0 seam can split one physical corner into a
    # group touching the start and a group touching the end — merge them
    # cyclically so the seam never scores two eyelets for one corner
    if closed and len(groups) >= 2 and groups[0][0] == 0 and groups[-1][1] == m - 1:
        head = groups.pop(0)
        tail = groups.pop()
        wrapped_indices = list(range(tail[0], m)) + list(range(0, head[1] + 1))
        best = max(wrapped_indices, key=lambda k: abs(angles[k]))
        candidates = [best] + [max(range(gs, ge + 1), key=lambda k: abs(angles[k])) for gs, ge in groups]
    else:
        candidates = [max(range(gs, ge + 1), key=lambda k: abs(angles[k])) for gs, ge in groups]
    candidates.sort(key=lambda k: cum[k])

    accepted: list[int] = []
    last_s = -math.inf
    for idx in candidates:
        if cum[idx] - last_s >= spacing:
            accepted.append(idx)
            last_s = cum[idx]

    if at_ends and not closed and m > 0:
        if not accepted or cum[accepted[0]] > 1e-6:
            accepted.insert(0, 0)
        if accepted[-1] != m - 1:
            accepted.append(m - 1)
    return accepted


def _circle(center: tuple[float, float], radius: float) -> list[tuple[float, float]]:
    pts = []
    for k in range(_CIRCLE_SEGS):
        a = math.tau * k / _CIRCLE_SEGS
        pts.append((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))
    pts.append(pts[0])  # exact closure by reuse, not by trusting cos/sin(tau) round-trip
    return pts


@register_effect
class Eyelets(EffectModule):
    id = "eyelets"
    label = "Eyelets"
    description = ("Sprouts small circles at curvature extrema and stroke ends — rivets "
                   "marking the joints. Originals pass through unchanged.")
    Params = EyeletsParams

    def apply(self, paths: list[Path], params: EyeletsParams, ctx: EffectContext) -> list[Path]:
        base_seed = (params.seed * 31 + ctx.seed) & 0x7FFFFFFF
        out: list[Path] = list(paths)  # originals verbatim, untouched
        for idx, path in enumerate(paths):
            seed = (base_seed + idx * 7919) & 0x7FFFFFFF
            out.extend(self._eyelets(path, params, seed))
        return out

    def _eyelets(self, path: Path, params: EyeletsParams, seed: int) -> list[Path]:
        closed = len(path.points) > 2 and path.points[0] == path.points[-1]
        pts = _resample(path.points, _STEP)
        if len(pts) < 2:
            return []
        core = _dedupe_closed(pts, closed)
        if len(core) < 2:
            return []
        angles = _turn_angles(core, closed)
        normals = _normals(core, closed)
        threshold = math.radians(3.0 + 87.0 * params.sensitivity)
        sites = _select_sites(core, angles, threshold, params.spacing, params.at_ends, closed)

        circles: list[Path] = []
        for idx in sites:
            radius = params.radius * (0.7 + 0.6 * _hash01(idx, seed + 3001))
            nx, ny = normals[idx]
            # nudge outward from the turn: a positive (CCW/left) turn's
            # "outside" is the -normal side; endpoints (angle==0) fall back
            # to a seeded side so they don't all nudge the same way
            if abs(angles[idx]) > 1e-6:
                sign = -1.0 if angles[idx] > 0 else 1.0
            else:
                sign = 1.0 if _hash01(idx, seed + 6007) < 0.5 else -1.0
            cx = core[idx][0] + sign * nx * params.nudge
            cy = core[idx][1] + sign * ny * params.nudge
            circles.append(Path(points=_circle((cx, cy), radius), filled=False))
        return circles
