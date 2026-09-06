"""Bounded local encounters; no global composition or collision-avoidance field."""
from __future__ import annotations
from dataclasses import dataclass
from shapely.geometry import LineString, Point as GeometryPoint
from shapely.ops import substring
from ..model import Path, Point
from ._second_reading import Passage


@dataclass(frozen=True)
class Encounter:
    other_id: int
    point: Point
    fraction: float


def encounters(points: list[Point], memory: list[Passage], excluded: tuple[int, ...] = ()) -> list[Encounter]:
    """Inspect at most twelve passages; keep at most eight contacts.

    Cached bounding boxes reject distant passages. Exact spine geometry then
    locates contacts, including in a dense human stroke. Shared endpoints and
    coincident runs are not interpreted as crossings.
    """
    line = LineString(points)
    if line.length < 1:
        return []
    out = []
    for passage in reversed(memory[-12:]):
        if passage.id in excluded:
            continue
        a,b,c,d = line.bounds
        x,y,z,w = passage.bbox
        if c < x or z < a or d < y or w < b:
            continue
        other = LineString(max(passage.paths, key=lambda p: p.length()).points)
        contact = line.intersection(other)
        candidates = [contact] if contact.geom_type == 'Point' else (
            list(contact.geoms) if contact.geom_type == 'MultiPoint' else [])
        for point in candidates:
            at = line.project(point)
            there = other.project(point)
            if not (.6 < at < line.length-.6 and .6 < there < other.length-.6):
                continue
            if any(point.distance(GeometryPoint(e.point)) < 1.2 for e in out):
                continue
            out.append(Encounter(passage.id, (point.x, point.y), at/line.length))
            if len(out) == 8:
                return out
    return out


def yield_at(path: Path, contact: Encounter, gap: float = 3.2) -> list[Path]:
    """Lift the new line around one encounter. The old line is never rewritten."""
    line = LineString(path.points)
    at = line.length*contact.fraction
    out = []
    for start, stop in ((0, max(0, at-gap/2)), (min(line.length, at+gap/2), line.length)):
        if stop-start > .1:
            part = substring(line, start, stop)
            out.append(Path(points=list(part.coords)))
    return out
