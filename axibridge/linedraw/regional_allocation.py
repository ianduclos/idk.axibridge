"""Pure source-pixel ownership, clipping, and per-person detail allocation.

The caller supplies a probability array and annotation dictionaries. No model,
image, or output file is loaded or written by this module.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree


CATEGORY_PRIORITY = ("hands_feet", "clothing", "hair", "body")
CATEGORY_WEIGHTS = {"hands_feet": 3, "clothing": 2, "body": 2, "hair": 1}
MIN_LENGTH_MM = 0.35


def _polygon_mask(polygon, width, height):
    image = Image.new("1", (width, height), 0)
    ImageDraw.Draw(image).polygon([tuple(xy) for xy in polygon], fill=1)
    return np.asarray(image, dtype=bool)


def _ellipse_mask(ellipse, width, height):
    cx, cy, rx, ry = map(float, ellipse)
    mask = np.zeros((height, width), dtype=bool)
    if rx <= 0 or ry <= 0:
        return mask
    x0, x1 = max(0, int(cx-rx)-1), min(width, int(cx+rx)+2)
    y0, y1 = max(0, int(cy-ry)-1), min(height, int(cy+ry)+2)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask[y0:y1, x0:x1] = ((xx-cx)/rx)**2 + ((yy-cy)/ry)**2 <= 1
    return mask


def _probability(probability, width, height):
    array = np.squeeze(np.asarray(probability))
    if array.ndim != 2:
        raise ValueError(f"person map must be 2D: {array.shape}")
    if array.shape != (height, width):
        image = Image.fromarray(array.astype(np.float32), mode="F")
        array = np.asarray(image.resize((width, height), Image.Resampling.BILINEAR))
    return array


def prepare_case(case: dict, probability: np.ndarray, checkpoint=lambda: None) -> dict:
    """Build exclusive source-pixel owners and regions in memory."""
    width, height = int(case["width"]), int(case["height"])
    foreground = _probability(probability, width, height) > .15
    radius = 3 * max(width, height) / 768
    reach = math.ceil(radius)
    yy, xx = np.ogrid[-reach:reach+1, -reach:reach+1]
    foreground = ndimage.binary_dilation(foreground, structure=(xx*xx+yy*yy <= radius*radius))

    owners = {}
    claimed = np.zeros((height, width), dtype=bool)
    # The manifest lists back to front; front people claim ambiguous pixels.
    for person in reversed(case["people"]):
        checkpoint()
        owner = foreground & _polygon_mask(person["owner_polygon"], width, height) & ~claimed
        owners[person["id"]] = owner
        claimed |= owner

    faces = {}
    protected = np.zeros((height, width), dtype=bool)
    for person in case["people"]:
        checkpoint()
        face = person.get("face")
        if face:
            # Pixel-center inclusion alone misses diagonals through edge cells.
            # One source-pixel guard clears the continuous vector ellipse.
            mask = ndimage.binary_dilation(_ellipse_mask(face["ellipse"], width, height),
                                           structure=np.ones((3, 3), dtype=bool))
            faces[face["id"]] = mask
            protected |= mask

    regions = {}
    region_meta = {}
    for person in case["people"]:
        checkpoint()
        owner = owners[person["id"]]
        occupied = protected.copy()
        raw = []
        for region in person["regions"]:
            if region["category"] not in CATEGORY_PRIORITY:
                raise ValueError(f"unknown category {region['category']}")
            polygon = _polygon_mask(region["polygon"], width, height)
            for exclusion in region.get("exclude_polygons", []):
                polygon = polygon & ~_polygon_mask(exclusion, width, height)
            raw.append((region, polygon, int(np.count_nonzero(owner & polygon & ~protected))))
        raw.sort(key=lambda item: (CATEGORY_PRIORITY.index(item[0]["category"]), item[2], item[0]["id"]))
        for region, polygon, raw_area in raw:
            mask = owner & polygon & ~occupied
            occupied |= mask
            region_id = region["id"]
            regions[region_id] = mask
            region_meta[region_id] = {
                "id": region_id, "person_id": person["id"], "category": region["category"],
                "polygon": region["polygon"], "exclude_polygons": region.get("exclude_polygons", []),
                "raw_area_px": raw_area,
                "final_area_px": int(np.count_nonzero(mask)), "empty": not bool(mask.any()),
            }

    guide = {
        "case_id": case["id"], "size": [width, height], "foreground_threshold": .15,
        "dilation_radius_source_px": radius, "ownership_order_front_first": [p["id"] for p in reversed(case["people"])],
        "people": [{"id": p["id"], "owner_polygon": p["owner_polygon"],
                    "owner_area_px": int(owners[p["id"]].sum()), "face": p.get("face")}
                   for p in case["people"]],
        "regions": [region_meta[r["id"]] for p in case["people"] for r in p["regions"]],
    }
    return {"width": width, "height": height, "owners": owners, "regions": regions,
            "region_meta": region_meta, "faces": faces, "protected": protected, "guide": guide}


def _inside(mask, point):
    x, y = point
    ix, iy = math.floor(x), math.floor(y)
    return 0 <= iy < mask.shape[0] and 0 <= ix < mask.shape[1] and bool(mask[iy, ix])


def _line_length(points):
    p = np.asarray(points, dtype=float)
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()) if len(p) > 1 else 0.


def _clip_path(points, mask):
    """Split at exact raster-cell crossings, including one-pixel holes."""
    points = np.asarray(points, dtype=float)
    if len(points) < 2:
        return []
    result, current = [], []
    for a, b in zip(points[:-1], points[1:]):
        delta = b-a
        if np.linalg.norm(delta) <= 1e-9:
            continue
        fractions = [0., 1.]
        for coordinate in (0, 1):
            if abs(delta[coordinate]) <= 1e-12:
                continue
            low, high = sorted((a[coordinate], b[coordinate]))
            for boundary in range(math.floor(low)+1, math.ceil(high)):
                t = (boundary-a[coordinate])/delta[coordinate]
                if 1e-12 < t < 1-1e-12:
                    fractions.append(t)
        fractions = sorted(set(fractions))
        for t0, t1 in zip(fractions[:-1], fractions[1:]):
            if t1-t0 < 1e-12:
                continue
            if _inside(mask, a+delta*((t0+t1)/2)):
                start, end = (a+delta*t0).tolist(), (a+delta*t1).tolist()
                if not current:
                    current = [start]
                elif np.linalg.norm(np.asarray(current[-1])-start) > 1e-6:
                    current.append(start)
                current.append(end)
            elif len(current) > 1:
                result.append(current)
                current = []
    if len(current) > 1:
        result.append(current)
    simplified = []
    for path in result:
        clean = [path[0]]
        for point in path[1:]:
            if np.linalg.norm(np.asarray(point)-clean[-1]) < 1e-6:
                continue
            while len(clean) > 1:
                a, b, c = map(np.asarray, (clean[-2], clean[-1], point))
                if abs(np.cross(b-a, c-b)) > 1e-7 or np.dot(b-a, c-b) < 0:
                    break
                clean.pop()
            clean.append(point)
        if len(clean) > 1 and _line_length(clean) > 1e-6:
            simplified.append(clean)
    return simplified


def _samples(points, spacing=1.0):
    p = np.asarray(points, dtype=float)
    lengths = np.linalg.norm(np.diff(p, axis=0), axis=1)
    cumulative = np.concatenate(([0.], np.cumsum(lengths)))
    if cumulative[-1] <= 0:
        return p[:1]
    distances = np.linspace(0, cumulative[-1], max(2, math.ceil(cumulative[-1]/spacing-1e-6)+1))
    index = np.minimum(np.searchsorted(cumulative, distances, side="right")-1, len(p)-2)
    fraction = (distances-cumulative[index]) / np.maximum(lengths[index], 1e-12)
    return p[index]+(p[index+1]-p[index])*fraction[:, None]


def _duplicate(a, b, threshold):
    length_a, length_b = a["length"], b["length"]
    ratio = length_a / max(length_b, 1e-12)
    if not .6 <= ratio <= 1.6:
        return False
    pa, pb = _samples(a["points"]), _samples(b["points"])
    return (cKDTree(pb).query(pa)[0].mean() <= threshold and
            cKDTree(pa).query(pb)[0].mean() <= threshold)


def _deduplicate(paths, threshold):
    kept = []
    boxes = []
    for path in sorted(paths, key=lambda p: (-p["score"], p["id"])):
        p = np.asarray(path["points"])
        box = (p[:,0].min(), p[:,1].min(), p[:,0].max(), p[:,1].max())
        if not any(box[0] <= oldbox[2]+threshold and oldbox[0] <= box[2]+threshold and
                   box[1] <= oldbox[3]+threshold and oldbox[1] <= box[3]+threshold and
                   _duplicate(path, old, threshold) for old, oldbox in zip(kept, boxes)):
            kept.append(path)
            boxes.append(box)
    return kept


def _join(paths, gap_limit, mask=None):
    """Join only mutual best, unbranched endpoint matches with aligned tangents."""
    paths = list(paths)
    if len(paths) < 2:
        return paths
    endpoints = []
    inward = []
    for path in paths:
        p = np.asarray(path["points"], dtype=float)
        endpoints.extend((p[0], p[-1]))
        inward.extend((p[1]-p[0], p[-2]-p[-1]))
    endpoints = np.asarray(endpoints)
    tree = cKDTree(endpoints)
    matches = {}
    for index, endpoint in enumerate(endpoints):
        best = None
        for other_index in tree.query_ball_point(endpoint, gap_limit):
            if other_index // 2 == index // 2:
                continue
            # Two fragments of one raw stroke were split by clipping for a reason.
            if paths[index//2]["id"].split("@")[0] == paths[other_index//2]["id"].split("@")[0]:
                continue
            vector_a, vector_b = inward[index], inward[other_index]
            norm = np.linalg.norm(vector_a)*np.linalg.norm(vector_b)
            if norm < 1e-9 or np.dot(-vector_a, vector_b)/norm < math.cos(math.radians(50)):
                continue
            distance = float(np.linalg.norm(endpoint-endpoints[other_index]))
            if mask is not None and distance > 1e-9:
                steps = max(2, math.ceil(distance/.2))
                if not all(_inside(mask, endpoint+(endpoints[other_index]-endpoint)*t)
                           for t in np.linspace(0, 1, steps+1)[1:-1]):
                    continue
            option = (distance, other_index)
            if best is None or option < best:
                best = option
        if best is not None:
            matches[index] = best[1]
    pairs = []
    used = set()
    for index, other_index in sorted(matches.items()):
        i, j = index//2, other_index//2
        if index < other_index and matches.get(other_index) == index and i not in used and j not in used:
            pairs.append((i, 0 if index%2 == 0 else -1, j, 0 if other_index%2 == 0 else -1))
            used.update((i,j))
    output = [p for i,p in enumerate(paths) if i not in used]
    for i, ai, j, bi in pairs:
        a, b = paths[i], paths[j]
        first = a["points"] if ai == -1 else list(reversed(a["points"]))
        second = b["points"] if bi == 0 else list(reversed(b["points"]))
        points = first + second
        confidence = max(a["confidence"], b["confidence"])
        merged = {**a, "id": f"{a['id']}+{b['id']}", "points": points,
                  "length": _line_length(points), "confidence": confidence}
        merged["score"] = merged["length"]**.67 * (.22+confidence)**.5
        output.append(merged)
    return output


def select_details(candidates: dict, case: dict, prepared: dict, method: str, budget: int,
                   checkpoint=lambda: None) -> dict:
    if method not in ("whole", "regional"):
        raise ValueError("method must be whole or regional")
    if budget < 0:
        raise ValueError("budget must be nonnegative")
    if candidates.get("case_id") != case["id"]:
        raise ValueError("candidate case_id does not match case")
    factor = max(prepared["width"], prepared["height"]) / 768
    min_length = MIN_LENGTH_MM * prepared["height"] / 200
    pools = {}
    diagnostics = {"method": method, "budget_per_person": budget, "regions": {}}
    for person in case["people"]:
        checkpoint()
        for region in person["regions"]:
            rid = region["id"]
            mask = prepared["regions"][rid]
            source = candidates.get("whole_candidates", []) if method == "whole" else candidates.get("regions", {}).get(rid, [])
            clipped = []
            if mask.any():
                for candidate in source:
                    checkpoint()
                    for fragment_index, points in enumerate(_clip_path(candidate["points"], mask)):
                        length = _line_length(points)
                        if length < min_length:
                            continue
                        confidence = float(candidate["confidence"])
                        clipped.append({"id": f"{candidate['id']}@{rid}:{fragment_index}",
                                        "points": points, "length": length, "confidence": confidence,
                                        "score": length**.67*(.22+confidence)**.5,
                                        "person_id": person["id"], "region_id": rid,
                                        "category": region["category"]})
            before_dedup = len(clipped)
            clipped = _deduplicate(clipped, factor)
            after_dedup = len(clipped)
            clipped = _join(clipped, 1.5*factor, mask)
            clipped = [p for p in clipped if p["length"] >= min_length]
            clipped.sort(key=lambda p: (-p["score"], p["id"]))
            pools[rid] = clipped
            diagnostics["regions"][rid] = {"area_px": prepared["region_meta"][rid]["final_area_px"],
                                            "clipped": before_dedup, "after_dedup": after_dedup,
                                            "available": len(clipped), "selected": 0}

    selected = []
    counts = {}
    for person in case["people"]:
        checkpoint()
        pid = person["id"]
        region_ids = [r["id"] for r in person["regions"] if pools[r["id"]]]
        category_counts = {category: sum(prepared["region_meta"][rid]["category"] == category for rid in region_ids)
                           for category in CATEGORY_PRIORITY}
        picked = {rid: 0 for rid in region_ids}
        for _ in range(budget):
            checkpoint()
            active = [rid for rid in region_ids if picked[rid] < len(pools[rid])]
            if not active:
                break
            def finish_time(rid):
                category = prepared["region_meta"][rid]["category"]
                weight = CATEGORY_WEIGHTS[category] / category_counts[category]
                return ((picked[rid]+1)/weight, CATEGORY_PRIORITY.index(category), rid)
            rid = min(active, key=finish_time)
            selected.append(pools[rid][picked[rid]])
            picked[rid] += 1
            diagnostics["regions"][rid]["selected"] += 1
        counts[pid] = sum(picked.values())
    diagnostics["total_selected"] = len(selected)
    return {"selected": selected, "counts": counts, "diagnostics": diagnostics}
