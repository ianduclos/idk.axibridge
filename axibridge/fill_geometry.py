"""Pick bounded planar faces and capture them as editable pen rings.

Limits: 2,000 input segments, 20,000 noded segments, 2,000,000 gap
candidate comparisons, 20,000 ring vertices, and 2,000 output anchors.
GEOS calls are atomic; checkpoints surround them and bound Python loops.
Boundary clicks return None; the API should explain that a click must be
strictly inside a face. Gap repair adds connectors only at degree-one nodes;
it never moves existing geometry or closes already closed narrow holes.
"""
from __future__ import annotations

import math
from collections import Counter

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from .curvefit import detail_tolerance, fit_bezier
from .model import Path
from .render_work import checkpoint
from .sources.pen import PenSubpath, _flatten_subpath

MAX_SEGMENTS = 2000
MAX_NODED_SEGMENTS = 20000
MAX_GAP_COMPARISONS = 2000000
MAX_RING_VERTICES = 20000
MAX_ANCHORS = 2000


def _bounded(value, lower, upper, name):
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f'{name} must be finite and between {lower} and {upper}')


def _edges(geometry):
    parts = geometry.geoms if hasattr(geometry, 'geoms') else [geometry]
    edges = []
    for part in parts:
        checkpoint()
        coords = list(part.coords)
        for a,b in zip(coords,coords[1:]):
            edges.append(LineString([a,b]))
            if len(edges) > MAX_NODED_SEGMENTS:
                raise ValueError('Fill geometry noded segment limit exceeded; simplify the drawing')
    return edges


def find_face(paths: list[Path], point, gap_mm: float) -> Polygon | None:
    """Smallest polygonized face strictly containing point, or None."""
    checkpoint()
    _bounded(gap_mm,0,5,'Gap')
    for coordinate in point:
        _bounded(coordinate,-1000000,1000000,'Click coordinate')
    click = Point(point)
    segments = []
    input_segments = 0
    for path in paths:
        checkpoint()
        for a,b in zip(path.points,path.points[1:]):
            input_segments += 1
            if input_segments > MAX_SEGMENTS:
                raise ValueError('Fill geometry input segment limit exceeded; simplify the drawing')
            if input_segments % 128 == 0:
                checkpoint()
            for coordinate in (*a,*b):
                _bounded(coordinate,-1000000,1000000,'Path coordinate')
            if a != b:
                segments.append(LineString([a,b]))
    if not segments:
        return None
    checkpoint()
    noded = unary_union(segments)
    checkpoint()
    edges = _edges(noded)
    if gap_mm:
        degrees = Counter(p for edge in edges for p in (edge.coords[0],edge.coords[-1]))
        dangling = sorted(p for p,degree in degrees.items() if degree == 1)
        if len(dangling)*len(edges) > MAX_GAP_COMPARISONS:
            raise ValueError('Fill geometry gap search limit exceeded; simplify the drawing or set Gap to zero')
        connectors = []
        for source in dangling:
            checkpoint()
            start = Point(source)
            candidates = []
            for index,edge in enumerate(edges):
                if index % 128 == 0:
                    checkpoint()
                if source in (edge.coords[0],edge.coords[-1]):
                    continue
                target = edge.interpolate(edge.project(start))
                distance = start.distance(target)
                if 0 < distance <= gap_mm:
                    candidates.append((distance,target.x,target.y))
            if candidates:
                _,x,y = min(candidates)
                connectors.append(LineString([source,(x,y)]))
        if connectors:
            checkpoint()
            noded = unary_union([noded,*connectors])
            checkpoint()
            _edges(noded)  # bound polygonization input after repairs too
    checkpoint()
    faces = list(polygonize(noded))
    checkpoint()
    # A shared edge or dangling stroke is still a boundary, even if a
    # polygon would otherwise contain the click in its interior.
    if noded.distance(click) == 0:
        return None
    matches = []
    for face in faces:
        checkpoint()
        if face.contains(click):
            matches.append(face)
    return min(matches,key=lambda face:face.area) if matches else None


def fit_face(face: Polygon, detail: float) -> list[dict]:
    """Fit rings while preserving topology and corresponding holes.

    Each ring boundary must remain within detail_tolerance(detail) + 0.05 mm
    (the pen flatten tolerance). The caller must additionally verify the
    fitted polygon contains the actual click, which this helper does not know.
    """
    checkpoint()
    _bounded(detail,0,1,'Detail')
    if not isinstance(face,Polygon) or face.is_empty or not face.is_valid:
        raise ValueError('Cannot fit this face; raise Detail or choose another face')
    rings = [face.exterior,*face.interiors]
    if sum(len(ring.coords) for ring in rings) > MAX_RING_VERTICES:
        raise ValueError('Fill ring vertex limit exceeded; simplify the drawing')
    result = []
    flattened = []
    count = 0
    for ring in rings:
        checkpoint()
        for point in ring.coords:
            for coordinate in point:
                _bounded(coordinate,-1000000,1000000,'Ring coordinate')
        anchors = fit_bezier(list(ring.coords),closed=True,detail=detail)
        count += len(anchors)
        if count > MAX_ANCHORS:
            raise ValueError('Fill anchor limit exceeded; simplify the drawing or lower Detail')
        subpath = {'anchors':anchors,'closed':True,'kind':'bezier'}
        result.append(subpath)
        flattened.append(_flatten_subpath(PenSubpath(**subpath),.05))
    checkpoint()
    fitted = Polygon(flattened[0],flattened[1:])
    tolerance = detail_tolerance(detail) + .05
    valid = (fitted.is_valid and not fitted.is_empty
             and len(fitted.interiors) == len(face.interiors)
             and fitted.exterior.hausdorff_distance(face.exterior) <= tolerance
             and fitted.contains(face.representative_point()))
    if valid:
        for hole, fitted_hole in zip(face.interiors,fitted.interiors):
            checkpoint()
            original_hole, new_hole = Polygon(hole), Polygon(fitted_hole)
            if (hole.hausdorff_distance(fitted_hole) > tolerance
                    or not new_hole.contains(original_hole.representative_point())
                    or not original_hole.contains(new_hole.representative_point())):
                valid = False
                break
    if not valid:
        raise ValueError('Curve fit changed the selected face or its holes; raise Detail and try again')
    return result
