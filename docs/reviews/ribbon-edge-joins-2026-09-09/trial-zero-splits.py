"""Geometry primitives shared by the open-path ribbon effect.

This is a deliberately close port of the small, dependency-free helpers used
by the ribbon study.  The public functions use ordinary ``(x, y)`` tuples and
Shapely only at the boundary where polygon Boolean operations are needed.
"""

from __future__ import annotations

from collections import defaultdict
from bisect import bisect_left, bisect_right
from math import atan2, ceil, cos, floor, hypot, sin, tan
from typing import Any, Iterable

from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union
from shapely import make_valid

EPS = 1e-9
Point2 = tuple[float, float]


def _point(value: Any) -> Point2:
    value = value["p"] if isinstance(value, dict) else value
    return (float(value[0]), float(value[1]))


def _node(value: Any) -> tuple[Point2, float]:
    if isinstance(value, dict):
        return _point(value), float(value["s"])
    return _point(value), float(value.s)


def _mix(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _distance(a: Point2, b: Point2) -> float:
    return hypot(b[0] - a[0], b[1] - a[1])


def sample_polyline(points: list[Point2], spacing: float) -> tuple[list[Point2], list[float], float]:
    """Subdivide every source segment exactly as the browser implementation."""
    if not points:
        return [], [], 0.0
    if spacing <= 0:
        raise ValueError("spacing must be positive")
    source = [_point(p) for p in points]
    spine, stations, total = [source[0]], [0.0], 0.0
    for a, b in zip(source, source[1:]):
        length = _distance(a, b)
        count = max(1, ceil(length / spacing))
        for j in range(1, count + 1):
            t = j / count
            spine.append((_mix(a[0], b[0], t), _mix(a[1], b[1], t)))
            total += length / count
            stations.append(total)
    return spine, stations, total


def frames(spine: list[Point2]) -> list[Point2]:
    """Return capped-miter normals (the values include the miter scale)."""
    out: list[Point2] = []
    for i, here in enumerate(spine):
        prev, nxt = spine[max(0, i - 1)], spine[min(len(spine) - 1, i + 1)]
        ax, ay, bx, by = here[0] - prev[0], here[1] - prev[1], nxt[0] - here[0], nxt[1] - here[1]
        if i == 0:
            ax, ay = bx, by
        if i == len(spine) - 1:
            bx, by = ax, ay
        al, bl = hypot(ax, ay) or 1.0, hypot(bx, by) or 1.0
        ax, ay, bx, by = ax / al, ay / al, bx / bl, by / bl
        n1, n2 = (-ay, ax), (-by, bx)
        nx, ny = n1[0] + n2[0], n1[1] + n2[1]
        norm = hypot(nx, ny)
        if norm < 1e-6:
            nx, ny = n2
        else:
            nx, ny = nx / norm, ny / norm
        miter = min(2.4, 1.0 / max(0.35, nx * n2[0] + ny * n2[1]))
        out.append((nx * miter, ny * miter))
    return out


def sharp_corners(spine: list[Point2], stations: list[float]) -> list[dict[str, float]]:
    out = []
    for i in range(1, len(spine) - 1):
        a = (spine[i][0] - spine[i - 1][0], spine[i][1] - spine[i - 1][1])
        b = (spine[i + 1][0] - spine[i][0], spine[i + 1][1] - spine[i][1])
        turn = atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1])
        if abs(turn) > 0.4:
            out.append({"s": stations[i], "turn": turn})
    return out


def _projection(p: Point2, a: Point2, b: Point2) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy or 1)))
    return t, hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def envelope(nodes: list[dict[str, Any]], spine: list[Point2], stations: list[float], corners: list[dict[str, float]], width: float) -> list[dict[str, Any]]:
    """Join an offset lane, including edge-interpolated lanes crossing the spine.

    A swept strip must stay on one side of its source. Otherwise its boundary
    can switch onto the source itself. Insert exact zero-width crossings and
    join each same-side run independently, then reconnect at the shared zero.
    """
    if not corners:
        return nodes[:]
    normals = frames(spine)
    signed = [((n['p'][0]-p[0])*f[0]+(n['p'][1]-p[1])*f[1])/(f[0]*f[0]+f[1]*f[1] or 1)
              for n,p,f in zip(nodes,spine,normals)]
    if not (any(w > EPS for w in signed) and any(w < -EPS for w in signed)):
        return _side_envelope(nodes,spine,stations,corners,width)
    out = []
    run_nodes, run_spine, run_stations = [nodes[0]], [spine[0]], [stations[0]]

    def finish():
        if len(run_nodes)<2:
            return
        local = [c for c in corners if run_stations[0]<c['s']<run_stations[-1]]
        joined = _side_envelope(run_nodes,run_spine,run_stations,local,width)
        out.extend(joined if not out else joined[1:])

    for i in range(1,len(nodes)):
        a,b = signed[i-1],signed[i]
        if a*b < 0 and abs(a)>EPS and abs(b)>EPS:
            t = a/(a-b)
            p = (_mix(spine[i-1][0],spine[i][0],t),_mix(spine[i-1][1],spine[i][1],t))
            s = _mix(stations[i-1],stations[i],t)
            zero = {'p':p,'s':s}
            run_nodes.append(zero); run_spine.append(p); run_stations.append(s)
            finish()
            run_nodes,run_spine,run_stations = [zero],[p],[s]
        run_nodes.append(nodes[i]); run_spine.append(spine[i]); run_stations.append(stations[i])
        if abs(b)<=EPS and i<len(nodes)-1:
            finish()
            run_nodes,run_spine,run_stations = [nodes[i]],[spine[i]],[stations[i]]
    finish()
    return out


def _side_envelope(nodes: list[dict[str, Any]], spine: list[Point2], stations: list[float], corners: list[dict[str, float]], width: float) -> list[dict[str, Any]]:
    """Replace sharp offset corners with the selected local swept-strip edge."""
    if not corners:
        return nodes[:]
    # Overlapping supports must be swept together. Splitting at the midpoint
    # both revisited a sample and left inner offsets of a neighbouring turn
    # inside the union, where no boundary route could connect the patch ends.
    supports = []
    for corner in corners:
        reach = width * min(4, abs(tan(corner["turn"] / 2))) * 2 + 12
        lo, hi = max(0,corner["s"]-reach), min(stations[-1],corner["s"]+reach)
        if supports and lo <= supports[-1][1]:
            supports[-1][1] = max(supports[-1][1],hi)
        else:
            supports.append([lo,hi])
    turns = {corner["s"]:corner["turn"] for corner in corners}
    frame = frames(spine)
    ranges = []
    for lo,hi in supports:
        start = max(0,bisect_left(stations,lo)-1)
        end = min(len(stations)-1,bisect_right(stations,hi))
        # Quantization to source samples can also make disjoint supports touch.
        if ranges and start <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1],end)
        else:
            ranges.append([start,end])
    patches = []
    for start,end in ranges:
        source: list[Point2] = []
        offset: list[Point2] = []
        ss: list[float] = []
        for i in range(start, end + 1):
            if stations[i] in turns and 0 < i < len(spine) - 1:
                a, b = spine[i - 1], spine[i]
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = hypot(dx, dy)
                if not length:
                    continue
                nx, ny = -dy / length, dx / length
                p = _point(nodes[i])
                # Recover the requested signed distance, including when the
                # raw frame's miter has been capped on a near reversal.
                fx,fy = frame[i]
                w = ((p[0]-b[0])*fx+(p[1]-b[1])*fy)/(fx*fx+fy*fy or 1)
                turn = turns[stations[i]]
                angle, count = atan2(ny, nx), max(4, ceil(abs(turn) / .055))
                for j in range(count + 1):
                    source.append(b)
                    offset.append((b[0] + w * cos(angle + turn * j / count), b[1] + w * sin(angle + turn * j / count)))
                    ss.append(stations[i])
            else:
                source.append(spine[i]); offset.append(_point(nodes[i])); ss.append(stations[i])
        triangles = []
        for a, b, c, d in zip(source, source[1:], offset[1:], offset):
            for tri in ((a, b, c), (a, c, d)):
                poly = Polygon(tri)
                if abs(poly.area) > 1e-10:
                    triangles.append(poly)
        if not triangles:
            continue
        merged = unary_union(triangles)
        source_line = LineString(source)
        candidates = list(merged.geoms) if isinstance(merged, MultiPolygon) else [merged]
        chosen = None
        for poly in candidates:
            ring = list(poly.exterior.coords)[:-1]
            ia = next((i for i, p in enumerate(ring) if _distance(p, offset[0]) < 1e-7), -1)
            ib = next((i for i, p in enumerate(ring) if _distance(p, offset[-1]) < 1e-7), -1)
            if ia < 0 or ib < 0:
                continue
            def route(step: int) -> list[Point2]:
                path, i = [], ia
                while i != ib:
                    path.append(ring[i]); i = (i + step) % len(ring)
                return path + [ring[ib]]
            one, two = route(1), route(-1)
            score = lambda path: sum(source_line.distance(Point(p)) for p in path)
            chosen = one if score(one) > score(two) else two
            break
        if chosen is None:
            continue
        offset_line = LineString(offset)
        offset_lengths = [0.0]
        for a, b in zip(offset,offset[1:]):
            offset_lengths.append(offset_lengths[-1]+_distance(a,b))
        previous, path = stations[start], []
        for index, p in enumerate(chosen):
            if index == 0:
                path.append({"p": _point(nodes[start]), "s": stations[start]}); continue
            if index == len(chosen) - 1:
                path.append({"p": _point(nodes[end]), "s": stations[end]}); continue
            distance = offset_line.project(Point(p))
            j = min(len(offset)-2,max(0,bisect_right(offset_lengths,distance)-1))
            t = (distance-offset_lengths[j]) / (offset_lengths[j+1]-offset_lengths[j] or 1)
            best_s = ss[j]+t*(ss[j+1]-ss[j])
            previous = max(previous, best_s)
            path.append({"p": (float(p[0]), float(p[1])), "s": previous})
        patches.append((start, end, path))
    result: list[dict[str, Any]] = []
    cursor = 0
    for start, end, path in patches:
        result.extend(nodes[cursor:start]); result.extend(path); cursor = end + 1
    return result + nodes[cursor:]


def _spine_at(spine: list[Any], s: float, hint: float) -> Point2:
    values = [_node(x) for x in spine]
    exact = [i for i, (_, station) in enumerate(values) if abs(station - s) <= EPS]
    if exact:
        return values[min(exact, key=lambda i: abs(i - hint))][0]
    for (a, sa), (b, sb) in zip(values, values[1:]):
        if sa - EPS <= s <= sb + EPS and sb > sa + EPS:
            t = max(0.0, min(1.0, (s - sa) / (sb - sa)))
            return (_mix(a[0], b[0], t), _mix(a[1], b[1], t))
    return values[0 if s <= values[0][1] else -1][0]


def silhouette(left_nodes: list[Any], right_nodes: list[Any], spine_nodes: list[Any]):
    """Union sweep triangles, preserving holes created by closed ribbon loops."""
    if not left_nodes or not right_nodes or not spine_nodes:
        return GeometryCollection()
    pieces = []
    for nodes in (left_nodes, right_nodes):
        denom = max(1, len(nodes) - 1)
        for i, (first, second) in enumerate(zip(nodes, nodes[1:])):
            a, sa = _node(first); b, sb = _node(second)
            ca = _spine_at(spine_nodes, sa, i / denom * max(0, len(spine_nodes) - 1))
            cb = _spine_at(spine_nodes, sb, (i + 1) / denom * max(0, len(spine_nodes) - 1))
            for tri in ((ca, cb, b), (ca, b, a)):
                poly = Polygon(tri)
                if abs(poly.area) > EPS:
                    pieces.append(poly)
    return unary_union(pieces) if pieces else GeometryCollection()


def _segment_visible(a: Point2, b: Point2, mask) -> list[tuple[float, float]]:
    line = LineString((a, b))
    if line.length <= EPS:
        return [] if mask.covers(Point(a)) else [(0.0, 1.0)]
    cuts = [0.0, 1.0]
    inter = line.intersection(mask.boundary)
    geoms: Iterable[Any] = getattr(inter, "geoms", [inter])
    for geom in geoms:
        if geom.is_empty:
            continue
        if geom.geom_type == "Point":
            cuts.append(line.project(geom, normalized=True))
        elif geom.geom_type == "LineString" and len(geom.coords) >= 2:
            cuts.extend((line.project(Point(geom.coords[0]), normalized=True), line.project(Point(geom.coords[-1]), normalized=True)))
    cuts = sorted(cuts)
    unique = [x for i, x in enumerate(cuts) if not i or x - cuts[i - 1] > EPS]
    return [(lo, hi) for lo, hi in zip(unique, unique[1:]) if hi - lo > EPS and not mask.covers(line.interpolate((lo + hi) / 2, normalized=True))]


def clip_paths(paths: list[list[Point2]], mask) -> list[list[Point2]]:
    """Remove filled mask and its boundary; preserve input route and direction."""
    out: list[list[Point2]] = []
    for path in paths:
        if len(path) < 2:
            continue
        current: list[Point2] | None = None
        for a, b in zip(map(_point, path), map(_point, path[1:])):
            intervals = _segment_visible(a, b, mask)
            for lo, hi in intervals:
                p, q = (_mix(a[0], b[0], lo), _mix(a[1], b[1], lo)), (_mix(a[0], b[0], hi), _mix(a[1], b[1], hi))
                if current is not None and _distance(current[-1], p) <= EPS:
                    current.append(q)
                else:
                    current = [p, q]; out.append(current)
            if not intervals:
                current = None
    return out


def self_mask(paths_nodes: list[list[dict[str, Any]]], left_nodes: list[dict[str, Any]], right_nodes: list[dict[str, Any]], stations: list[float], corners: list[dict[str, float]], width: float, reverse: bool = False) -> list[list[Point2]]:
    """Mask crossings by later (or earlier) swept faces, retaining accepted runs."""
    def resample(nodes):
        i = 0; result = []
        for s in stations:
            while i + 1 < len(nodes) - 1 and nodes[i + 1]["s"] < s: i += 1
            a, sa = _node(nodes[i]); b, sb = _node(nodes[min(i + 1, len(nodes) - 1)])
            t = max(0.0, min(1.0, (s - sa) / (sb - sa or 1)))
            result.append((_mix(a[0], b[0], t), _mix(a[1], b[1], t)))
        return result
    left, right, faces, grid = resample(left_nodes), resample(right_nodes), [], defaultdict(list)
    cell = max(16.0, width * 2)
    def keys(x0, y0, x1, y1):
        return [(x, y) for x in range(floor(x0 / cell), floor(x1 / cell) + 1) for y in range(floor(y0 / cell), floor(y1 / cell) + 1)]
    for i in range(len(stations) - 1):
        ring = [left[i], left[i + 1], right[i + 1], right[i]]
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        polygon = Polygon(ring)
        # A tight return can fold a quadrilateral over itself.  polygon-clipping
        # treats that input by its even-odd filled pieces; make_valid gives GEOS
        # the corresponding valid area before we union candidate blockers.
        if not polygon.is_valid:
            polygon = make_valid(polygon)
        face = (polygon, stations[i], stations[i + 1], min(xs), max(xs), min(ys), max(ys))
        faces.append(face)
        for key in keys(face[3], face[5], face[4], face[6]): grid[key].append(i)
    joins = [(c["s"], width * min(4, abs(tan(c["turn"] / 2))) * 2 + 8) for c in corners]
    result: list[list[Point2]] = []
    for nodes in paths_nodes:
        run: list[Point2] = []
        def finish():
            nonlocal run
            if len(run) > 1: result.append(run)
            run = []
        for first, second in zip(nodes, nodes[1:]):
            a, sa = _node(first); b, sb = _node(second)
            x0, x1, y0, y1 = min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])
            blocker_indices = set(j for key in keys(x0, y0, x1, y1) for j in grid[key])
            blockers = []
            for j in blocker_indices:
                poly, fs, fe, fx0, fx1, fy0, fy1 = faces[j]
                if (fe >= sa - 4) if reverse else (fs <= sb + 4): continue
                if fx1 < x0 or fx0 > x1 or fy1 < y0 or fy0 > y1: continue
                if any(abs((sa + sb) / 2 - cs) < reach and abs((fs + fe) / 2 - cs) < reach for cs, reach in joins): continue
                blockers.append(poly)
            intervals = _segment_visible(a, b, unary_union(blockers)) if blockers else [(0.0, 1.0)]
            if not intervals:
                finish(); continue
            for lo, hi in intervals:
                p, q = (_mix(a[0], b[0], lo), _mix(a[1], b[1], lo)), (_mix(a[0], b[0], hi), _mix(a[1], b[1], hi))
                if lo > EPS or (run and _distance(run[-1], p) > 1e-7): finish()
                if not run: run.append(p)
                if _distance(run[-1], q) > EPS: run.append(q)
                if hi < 1 - EPS: finish()
        finish()
    return result
