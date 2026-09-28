"""Conservative, deterministic guidance for existing continuous face strokes."""

from __future__ import annotations

import math
from copy import deepcopy

FEATURES = ("left_eye", "right_eye", "left_brow", "right_brow", "nose", "mouth", "face_contour")
ASSOCIATE_FRACTION = 0.055
MOVE_START_FRACTION = 0.018
MAX_MOVE_FRACTION = 0.015
ALIGN_FRACTION = 0.25
DUPLICATE_FRACTION = 0.012
POLYGON_SEGMENTS = 96 * 4  # Matches Point(0, 0).buffer(1, quad_segs=96).
BALANCED_WEIGHTS = {
    "left_eye": 2.0, "right_eye": 2.0, "mouth": 2.0,
    "left_brow": 1.0, "right_brow": 1.0, "nose": 1.0,
    "face_contour": 1.0, "unassigned": 0.6,
}


def _inside_shared_ellipse(p, ellipse):
    """Containment in the exact regular polygon used by evidence clipping."""
    cx, cy, rx, ry = map(float, ellipse)
    x, y = (p[0] - cx) / rx, (p[1] - cy) / ry
    angle = math.atan2(y, x) % (2 * math.pi)
    step = 2 * math.pi / POLYGON_SEGMENTS
    normal = (math.floor(angle / step) + 0.5) * step
    return x * math.cos(normal) + y * math.sin(normal) <= math.cos(step / 2) + 1e-12


def _arc(points):
    return sum(math.dist(a[:2], b[:2]) for a, b in zip(points, points[1:]))


def _point_segment(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    t = min(1.0, max(0.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den)) if den else 0.0
    q = (a[0] + t * dx, a[1] + t * dy)
    return math.dist(p[:2], q), q


def _nearest(p, contour):
    if not contour:
        return float("inf"), p[:2]
    if len(contour) == 1:
        return math.dist(p[:2], contour[0]), contour[0]
    return min((_point_segment(p, a, b) for a, b in zip(contour, contour[1:])), key=lambda pair: pair[0])


def _samples(points, count=13):
    if len(points) <= count:
        return points
    return [points[round(i * (len(points) - 1) / (count - 1))] for i in range(count)]


def _median(values):
    values = sorted(values)
    return values[len(values) // 2]


def _feature(points, contours, width):
    if not points:
        return None, float("inf")
    samples = _samples(points)
    distances = [(_median([_nearest(p, contours.get(name, []))[0] for p in samples]), name)
                 for name in FEATURES if contours.get(name)]
    if not distances:
        return None, float("inf")
    distance, name = min(distances)
    supported = sum(_nearest(p, contours[name])[0] <= ASSOCIATE_FRACTION * width for p in samples)
    if distance > ASSOCIATE_FRACTION * width or supported < math.ceil(len(samples) * 0.6):
        return None, distance
    return name, distance


def _duplicate(a, b, width):
    pa, pb = _samples(a["points"]), _samples(b["points"])
    if not pa or not pb:
        return False
    la, lb = max(float(a.get("length", 0)), 1e-9), max(float(b.get("length", 0)), 1e-9)
    if not 0.6 <= la / lb <= 1.6:
        return False
    def directed(one, other):
        return _median([min(math.dist(p[:2], q[:2]) for q in other) for p in one])
    return max(directed(pa, pb), directed(pb, pa)) <= DUPLICATE_FRACTION * width


def _rank(candidate):
    return (-float(candidate.get("score", 0)), -float(candidate.get("confidence", 0)),
            -float(candidate.get("length", 0)), str(candidate.get("id", "")))


def _finalize(chosen, candidates, face, contours, width):
    """Apply the same conservative refit and diagnostics to either selector."""
    output = []
    max_displacement = 0.0
    for c, feature, distance in chosen:
        copy = deepcopy(c)
        moved = []
        if feature:
            for p in c["points"]:
                d, q = _nearest(p, contours[feature])
                if d <= MOVE_START_FRACTION * width:
                    scale = min(ALIGN_FRACTION, MAX_MOVE_FRACTION * width / d) if d else 0.0
                    new = [p[0] + (q[0] - p[0]) * scale, p[1] + (q[1] - p[1]) * scale]
                    # Input fragments are clipped to the 96-segment polygon.
                    # Retain any point whose movement would escape it.
                    if not _inside_shared_ellipse(new, face["ellipse"]):
                        new = list(p)
                    moved.append(new)
                    max_displacement = max(max_displacement, math.dist(p[:2], new))
                else:
                    moved.append(list(p))
            copy["points"] = moved
            copy["feature"] = feature
            copy["displacement_max"] = max(math.dist(a[:2], b[:2]) for a, b in zip(c["points"], moved))
            if copy["displacement_max"] > 0:
                copy["source_length"] = c["length"]
                copy["source_score"] = c["score"]
                copy["length"] = _arc(moved)
                copy["score"] = copy["length"] ** .67 * (.22 + float(c["confidence"])) ** .5
        output.append(copy)
    return {"status": "ok", "candidates": output, "diagnostics": {
        "selected": len(output), "available": len(candidates), "supported_features": sorted({f for _, f, _ in chosen if f}),
        "max_displacement": max_displacement, "face_width": width,
        "associate_fraction": ASSOCIATE_FRACTION, "move_start_fraction": MOVE_START_FRACTION,
        "max_move_fraction": MAX_MOVE_FRACTION, "align_fraction": ALIGN_FRACTION,
        "duplicate_fraction": DUPLICATE_FRACTION}}


def select_guided(candidates: list[dict], face: dict, geometry: dict, budget: int) -> dict:
    """Select source-evidenced strokes; move only nearby points, by at most 1.5% face width."""
    budget = max(0, budget)
    width = 2 * float(face["ellipse"][2])
    ordered = sorted(candidates, key=_rank)
    if not geometry or geometry.get("status") != "ok" or not geometry.get("feature_contours"):
        return {"status": "unavailable", "candidates": deepcopy(ordered[:budget]),
                "diagnostics": {"reason": "landmarks_unavailable", "selected": min(len(ordered), budget)}}
    contours = geometry["feature_contours"]
    classified = []
    for c in ordered:
        name, distance = _feature(c.get("points", []), contours, width)
        classified.append((c, name, distance))
    chosen = []
    seen = set()
    # One evidenced stroke per supported feature before the remaining score-ranked candidates.
    for name in FEATURES:
        if len(chosen) >= budget:
            break
        for c, feature, distance in classified:
            if feature == name and c["id"] not in seen and not any(_duplicate(c, old[0], width) for old in chosen):
                chosen.append((c, feature, distance))
                seen.add(c["id"])
                break
        if len(chosen) >= budget:
            break
    for c, feature, distance in classified:
        if len(chosen) >= budget:
            break
        if c["id"] not in seen and not any(_duplicate(c, old[0], width) for old in chosen):
            chosen.append((c, feature, distance))
            seen.add(c["id"])
    return _finalize(chosen, candidates, face, contours, width)


def select_balanced(candidates: list[dict], face: dict, geometry: dict, budget: int) -> dict:
    """Spend the full budget by diminishing class merit, using only source strokes."""
    budget = max(0, budget)
    width = 2 * float(face["ellipse"][2])
    ordered = sorted(candidates, key=_rank)
    if not geometry or geometry.get("status") != "ok" or not geometry.get("feature_contours"):
        return {"status": "unavailable", "candidates": deepcopy(ordered[:budget]),
                "diagnostics": {"reason": "landmarks_unavailable", "selected": min(len(ordered), budget),
                                "class_counts": {}, "weights": BALANCED_WEIGHTS.copy()}}
    contours = geometry["feature_contours"]
    classes = {name: [] for name in BALANCED_WEIGHTS}
    for candidate in ordered:
        feature, distance = _feature(candidate.get("points", []), contours, width)
        classes[feature or "unassigned"].append((candidate, feature, distance))
    tops = {name: max(float(items[0][0].get("score", 0)), 0.0) if items else 0.0
            for name, items in classes.items()}
    counts = {name: 0 for name in BALANCED_WEIGHTS}
    positions = {name: 0 for name in BALANCED_WEIGHTS}
    chosen = []
    while len(chosen) < budget:
        available = []
        for name, items in classes.items():
            pos = positions[name]
            while pos < len(items) and any(_duplicate(items[pos][0], old[0], width) for old in chosen):
                pos += 1
            positions[name] = pos
            if pos >= len(items):
                continue
            candidate = items[pos][0]
            score = max(float(candidate.get("score", 0)), 0.0)
            ratio = score / tops[name] if tops[name] else 1.0
            merit = BALANCED_WEIGHTS[name] * math.sqrt(ratio) / (1 + counts[name])
            available.append((-merit, str(candidate.get("id", "")), name))
        if not available:
            break
        _, _, name = min(available)
        chosen.append(classes[name][positions[name]])
        positions[name] += 1
        counts[name] += 1
    result = _finalize(chosen, candidates, face, contours, width)
    result["diagnostics"].update({"class_counts": counts, "weights": BALANCED_WEIGHTS.copy(),
                                   "selection_rule": "weight*sqrt(next_score/top_score)/(1+selected_in_class)"})
    return result
