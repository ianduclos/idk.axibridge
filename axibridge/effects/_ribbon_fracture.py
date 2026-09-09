"""Preserved experimental ribbon join that produces fractured edge routes.

This intentionally retains the 2026-09-09 reference-region trial, including
its route selection.  The resulting fractures are an artistic artifact rather
than a geometry repair; keep changes here isolated from the stable envelope.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from math import atan2, ceil, cos, hypot, sin, tan
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from ..render_work import checkpoint
from ._ribbon_geometry import EPS, Point2, _distance, _mix, _point, frames


def fractured_envelope(
    nodes: list[dict[str, Any]],
    spine: list[Point2],
    stations: list[float],
    corners: list[dict[str, float]],
    width: float,
) -> list[dict[str, Any]]:
    """Join a lane with the preserved reference-minus-positive-plus-negative trial."""
    checkpoint()
    if not corners:
        return nodes[:]
    frame = frames(spine)
    signed = [
        ((node["p"][0] - point[0]) * normal[0] + (node["p"][1] - point[1]) * normal[1])
        / (normal[0] * normal[0] + normal[1] * normal[1] or 1)
        for node, point, normal in zip(nodes, spine, frame)
    ]
    reference_mode = any(value > EPS for value in signed) and any(value < -EPS for value in signed)
    return _fractured_side(nodes, spine, stations, corners, width, reference_mode)


def _fractured_side(nodes, spine, stations, corners, width, reference_mode):
    supports = []
    for corner in corners:
        checkpoint()
        reach = width * min(4, abs(tan(corner["turn"] / 2))) * 2 + 12
        lo, hi = max(0, corner["s"] - reach), min(stations[-1], corner["s"] + reach)
        if supports and lo <= supports[-1][1]:
            supports[-1][1] = max(supports[-1][1], hi)
        else:
            supports.append([lo, hi])
    turns = {corner["s"]: corner["turn"] for corner in corners}
    frame = frames(spine)
    ranges = []
    for lo, hi in supports:
        checkpoint()
        start = max(0, bisect_left(stations, lo) - 1)
        end = min(len(stations) - 1, bisect_right(stations, hi))
        if ranges and start <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])

    patches = []
    for start, end in ranges:
        checkpoint()
        source, offset, ss, reference, distances = [], [], [], [], []
        for i in range(start, end + 1):
            checkpoint()
            if stations[i] in turns and 0 < i < len(spine) - 1:
                a, b = spine[i - 1], spine[i]
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = hypot(dx, dy)
                if not length:
                    continue
                nx, ny = -dy / length, dx / length
                p = _point(nodes[i])
                fx, fy = frame[i]
                lane_width = ((p[0] - b[0]) * fx + (p[1] - b[1]) * fy) / (fx * fx + fy * fy or 1)
                turn = turns[stations[i]]
                angle, count = atan2(ny, nx), max(4, ceil(abs(turn) / .055))
                for j in range(count + 1):
                    checkpoint()
                    theta = angle + turn * j / count
                    source.append(b)
                    offset.append((b[0] + lane_width * cos(theta), b[1] + lane_width * sin(theta)))
                    ss.append(stations[i])
                    reference.append((b[0] + width * cos(theta), b[1] + width * sin(theta)))
                    distances.append(lane_width)
            else:
                source.append(spine[i])
                offset.append(_point(nodes[i]))
                ss.append(stations[i])
                reference.append((spine[i][0] + frame[i][0] * width, spine[i][1] + frame[i][1] * width))
                fx, fy = frame[i]
                distances.append(
                    ((nodes[i]["p"][0] - spine[i][0]) * fx + (nodes[i]["p"][1] - spine[i][1]) * fy)
                    / (fx * fx + fy * fy or 1)
                )

        def add_quad(a, b, c, d, target):
            for triangle in ((a, b, c), (a, c, d)):
                polygon = Polygon(triangle)
                if polygon.area > 1e-10:
                    target.append(polygon)

        triangles = []
        for a, b, c, d in zip(source, source[1:], offset[1:], offset):
            checkpoint()
            add_quad(a, b, c, d, triangles)
        if not triangles:
            continue
        checkpoint()
        merged = unary_union(triangles)
        checkpoint()
        source_line = LineString(source)
        if reference_mode:
            positive, negative, reference_faces = [], [], []
            for i in range(len(source) - 1):
                checkpoint()
                a, b, u, v = source[i], source[i + 1], offset[i], offset[i + 1]
                wa, wb = distances[i], distances[i + 1]
                add_quad(a, b, reference[i + 1], reference[i], reference_faces)
                if wa * wb < 0:
                    t = wa / (wa - wb)
                    zero = (_mix(a[0], b[0], t), _mix(a[1], b[1], t))
                    add_quad(a, zero, zero, u, positive if wa > 0 else negative)
                    add_quad(zero, b, v, zero, positive if wb > 0 else negative)
                else:
                    add_quad(a, b, v, u, positive if wa + wb >= 0 else negative)
            checkpoint()
            reference_union = unary_union(reference_faces)
            checkpoint()
            positive_union = unary_union(positive)
            checkpoint()
            negative_union = unary_union(negative)
            checkpoint()
            merged = reference_union.difference(positive_union)
            checkpoint()
            merged = merged.union(negative_union)
            checkpoint()
            source_line = LineString(reference)

        candidates = [merged] if merged.geom_type == "Polygon" else [
            polygon for polygon in getattr(merged, "geoms", []) if polygon.geom_type == "Polygon"
        ]
        rings = [
            ring
            for polygon in candidates
            for ring in ([polygon.exterior, *polygon.interiors] if reference_mode else [polygon.exterior])
        ]
        chosen = None
        for boundary in rings:
            checkpoint()
            ring = list(boundary.coords)[:-1]
            ia = next((i for i, point in enumerate(ring) if _distance(point, offset[0]) < 1e-7), -1)
            ib = next((i for i, point in enumerate(ring) if _distance(point, offset[-1]) < 1e-7), -1)
            if ia < 0 or ib < 0:
                continue

            def route(step):
                path, i = [], ia
                while i != ib:
                    checkpoint()
                    path.append(ring[i])
                    i = (i + step) % len(ring)
                return path + [ring[ib]]

            one, two = route(1), route(-1)
            # Deliberately preserved: scoring against the reference edge picks
            # the remote boundary route and creates the characteristic fracture.
            score = lambda path: sum(source_line.distance(Point(point)) for point in path)
            chosen = one if score(one) > score(two) else two
            break
        if chosen is None:
            continue

        offset_line = LineString(offset)
        offset_lengths = [0.0]
        for a, b in zip(offset, offset[1:]):
            offset_lengths.append(offset_lengths[-1] + _distance(a, b))
        previous, path = stations[start], []
        for index, point in enumerate(chosen):
            checkpoint()
            if index == 0:
                path.append({"p": _point(nodes[start]), "s": stations[start]})
                continue
            if index == len(chosen) - 1:
                path.append({"p": _point(nodes[end]), "s": stations[end]})
                continue
            distance = offset_line.project(Point(point))
            j = min(len(offset) - 2, max(0, bisect_right(offset_lengths, distance) - 1))
            t = (distance - offset_lengths[j]) / (offset_lengths[j + 1] - offset_lengths[j] or 1)
            previous = max(previous, ss[j] + t * (ss[j + 1] - ss[j]))
            path.append({"p": (float(point[0]), float(point[1])), "s": previous})
        patches.append((start, end, path))

    result, cursor = [], 0
    for start, end, path in patches:
        result.extend(nodes[cursor:start])
        result.extend(path)
        cursor = end + 1
    return result + nodes[cursor:]
