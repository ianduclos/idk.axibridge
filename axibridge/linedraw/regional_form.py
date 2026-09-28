"""Reference Face + form base with independently allocated regional ink.

All input geometry and returned polylines use EXIF-corrected source pixels.
This renderer does not load models, assets, or study artifacts.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter
from shapely import affinity
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from .flow_hatch import flow_hatch
from .geometry import samples, simplify
from .regional_allocation import prepare_case, select_details
from .shading import scanline_mask
from .shadows import line_components, shadow_field, shapes


def _value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _ellipse(face, w, h):
    return affinity.translate(
        affinity.scale(Point(0, 0).buffer(1, quad_segs=96),
                       _value(face, "rx") * w, _value(face, "ry") * h),
        _value(face, "cx") * w, _value(face, "cy") * h,
    )


def _points(candidate):
    points = np.asarray(_value(candidate, "points"), dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 2 or not np.isfinite(points).all():
        return None
    return points


def _candidate_dict(candidate, index):
    points = _points(candidate)
    if points is None:
        return None
    confidence = float(_value(candidate, "confidence", 0.5))
    return {"id": str(_value(candidate, "id", _value(candidate, "identity", str(index)))),
            "points": points.tolist(), "confidence": confidence,
            "score": float(_value(candidate, "score", LineString(points).length ** .67 * (.22 + confidence) ** .5))}


def _resize(array, size, resample):
    image = Image.fromarray(np.asarray(array, dtype=np.float32), mode="F")
    return np.asarray(image.resize(size, resample), dtype=float)


def _baseline(evidence, faces, checkpoint, params=None):
    """The study's middle material proxy at 768 long-side pixels."""
    h, w = evidence.rgb.shape[:2]
    work_w = max(1, round(w * 768 / max(w, h)))
    work_h = max(1, round(h * 768 / max(w, h)))
    size = (work_w, work_h)
    scale = np.array([w / work_w, h / work_h])
    source_rgb = np.uint8(np.rint(np.clip(evidence.rgb, 0, 1) * 255))
    rgb = np.asarray(Image.fromarray(source_rgb, mode="RGB").resize(
        size, Image.Resampling.LANCZOS), dtype=float) / 255
    fg = _resize(evidence.foreground, size, Image.Resampling.BILINEAR) > .35
    if evidence.alpha is not None:
        fg &= _resize(evidence.alpha, size, Image.Resampling.BILINEAR) > .5
    face_masks = []
    yy, xx = np.mgrid[:work_h, :work_w]
    for face in faces:
        face_masks.append((((xx / work_w - _value(face, "cx")) / _value(face, "rx")) ** 2
                           + ((yy / work_h - _value(face, "cy")) / _value(face, "ry")) ** 2) < 1)
    face_area = np.logical_or.reduce(face_masks)

    def mostly_outside_face(points):
        sample = samples(points, .9)
        indices = np.clip(sample.astype(int), [0, 0], [work_w - 1, work_h - 1])
        return float(np.mean(face_area[indices[:, 1], indices[:, 0]])) < .05
    checkpoint()
    field, _ = shadow_field(rgb, fg, face_masks)
    _, mask = shapes(field, fg, 4., 55, 16, .08, checkpoint=checkpoint)
    face_geometry = unary_union([_ellipse(face, w, h) for face in faces])
    if evidence.normals is None:
        raise ValueError("Surface-normal evidence is required for regional form")
    normals = np.stack([_resize(evidence.normals[..., i], size, Image.Resampling.BILINEAR)
                        for i in range(min(3, evidence.normals.shape[-1]))], axis=-1)
    base = []
    density = float(_value(params, "form_density", 1))
    flow = _value(params, "form_flow", "original")
    hatch_kwargs = {"coherent": True} if flow == "coherent" else {}
    if _value(params, "shading_mode", "original") == "tonal":
        hatch_kwargs["density_field"] = np.clip(field * 2, 0, 1)
    for raw in flow_hatch(mask, normals, 5. / density, checkpoint=checkpoint, **hatch_kwargs):
        checkpoint()
        if len(raw) < 2:
            continue
        simplified = simplify(raw, .25)
        if not mostly_outside_face(simplified):
            continue
        # The legacy middle export serialized working coordinates to tenths
        # before the later source-pixel clipping pass.
        line = LineString(np.round(simplified, 1) * scale)
        for part in line_components(line.difference(face_geometry)):
            if part.length > 1e-6:
                base.append((part, "hatch"))
    distance = distance_transform_edt(~mask)
    cues = 0
    for item in (_value(evidence, "reference_base") or ()):
        checkpoint()
        points = _points(item)
        if points is None:
            continue
        line = LineString(points)
        if line.length < 6 * max(scale):
            continue
        ix = np.clip((points / scale).astype(int), [0, 0], [work_w - 1, work_h - 1])
        if np.mean((distance[ix[:, 1], ix[:, 0]] > 2.5) & fg[ix[:, 1], ix[:, 0]]) <= .75:
            continue
        cues += 1
        if mostly_outside_face(points / scale):
            for part in line_components(line.difference(face_geometry)):
                if part.length > 1e-6:
                    base.append((part, "contour"))
        if cues >= 28:
            break
    cores = []
    strength = float(_value(params, "core_strength", .5))
    if _value(params, "shading_mode", "original") == "tonal" and strength > 0:
        deep = mask & (field >= .3) & ~face_area
        spacing = max(1., 6. / max(.25, 2 * strength))
        for q in scanline_mask(deep, spacing, checkpoint, min_length=4, limit=1200):
            checkpoint()
            line = LineString(q * scale)
            cores.extend(np.asarray(part.coords, float) for part in
                         line_components(line.difference(face_geometry))
                         if part.length >= 3 * max(scale))
    return base, face_geometry, cores


def _annotation_case(params, w, h):
    faces = [f for f in _value(params, "faces", ()) if _value(f, "enabled", True)]
    people = list(_value(params, "people", ()))
    if not people:
        if len(faces) > 1:
            raise ValueError("Multiple faces require explicit person ownership")
        people = [{"id": "person-1", "face_id": _value(faces[0], "id") if faces else None,
                   "polygon": [(0, 0), (1, 0), (1, 1), (0, 1)]}]
    regions = list(_value(params, "detail_regions", ()))
    def absolute(polygon):
        return [[float(x) * w, float(y) * h] for x, y in polygon]
    by_person = {str(_value(p, "id")): {"id": str(_value(p, "id")),
        "owner_polygon": absolute(_value(p, "polygon")), "regions": []} for p in people}
    face_by_id = {f.id if not isinstance(f, dict) else f["id"]: f for f in faces}
    for p in people:
        fid = _value(p, "face_id")
        if fid and fid in face_by_id:
            f = face_by_id[fid]
            by_person[str(_value(p, "id"))]["face"] = {"id": fid,
                "ellipse": [_value(f, "cx") * w, _value(f, "cy") * h,
                            _value(f, "rx") * w, _value(f, "ry") * h]}
    for region in regions:
        if not _value(region, "enabled", True):
            continue
        pid = str(_value(region, "person_id"))
        if pid not in by_person:
            raise ValueError(f"Detail region has unknown person: {pid}")
        by_person[pid]["regions"].append({"id": str(_value(region, "id")),
            "category": _value(region, "category"),
            "polygon": absolute(_value(region, "polygon")),
            "exclude_polygons": [absolute(p) for p in _value(region, "exclude_polygons", ())]})
    return faces, {"id": "current", "width": w, "height": h,
                   "people": list(by_person.values())}


def _bend_hair_guide(points, image_tangent_field, amount):
    """Steer one supplied hair stroke toward local image isophotes, within 0.6 px."""
    if amount <= 0:
        return np.asarray(points, float)
    q = samples(np.asarray(points, float), 4.)
    if len(q) < 3:
        return q
    dx, dy = image_tangent_field
    h, w = dx.shape
    ix = np.clip(np.rint(q[:, 0]).astype(int), 0, w - 1)
    iy = np.clip(np.rint(q[:, 1]).astype(int), 0, h - 1)
    image_tangent = np.column_stack((dx[iy, ix], dy[iy, ix]))
    image_tangent /= np.maximum(np.linalg.norm(image_tangent, axis=1)[:, None], 1e-9)
    guide_tangent = np.empty_like(q)
    guide_tangent[1:-1] = q[2:] - q[:-2]
    guide_tangent[0], guide_tangent[-1] = q[1] - q[0], q[-1] - q[-2]
    guide_tangent /= np.maximum(np.linalg.norm(guide_tangent, axis=1)[:, None], 1e-9)
    sign = np.where(np.sum(image_tangent * guide_tangent, axis=1) < 0, -1, 1)
    blended = (1 - amount) * guide_tangent + amount * image_tangent * sign[:, None]
    normal = np.column_stack((-guide_tangent[:, 1], guide_tangent[:, 0]))
    offset = np.clip(np.sum(blended * normal, axis=1), -.6, .6) * amount
    offset[0] = offset[-1] = 0
    return q + offset[:, None] * normal


def render_regional_components(evidence, params, checkpoint=lambda: None) -> dict[str, list[np.ndarray]]:
    """Render the frozen recipe with its source-pixel ink roles retained."""
    h, w = evidence.rgb.shape[:2]
    faces, case = _annotation_case(params, w, h)
    if not faces:
        raise ValueError("Regional form requires an enabled face for the material proxy")
    baseline = _baseline(evidence, faces, checkpoint, params)
    base, face_geometry = baseline[:2]
    cores = baseline[2] if len(baseline) > 2 else []
    face_paths = []
    for face in faces:
        checkpoint()
        fid = _value(face, "id")
        source = _value(evidence, "reference_faces", {}).get(fid, ())
        ranked = sorted((_candidate_dict(c, i) for i, c in enumerate(source)),
                        key=lambda c: (-c["score"], c["id"]) if c else (float("inf"), ""))
        for candidate in [c for c in ranked if c][:int(_value(params, "face_budget", 48))]:
            line = LineString(candidate["points"])
            for part in line_components(line.intersection(_ellipse(face, w, h))):
                if part.length > .02:
                    face_paths.append(np.asarray(part.coords, dtype=float))
    probability = evidence.foreground
    if evidence.alpha is not None:
        probability = np.minimum(probability, evidence.alpha)
    prepared = prepare_case(case, probability, checkpoint)
    region_source = _value(evidence, "reference_regions", {})
    candidates = {"case_id": "current", "regions": {
        rid: [q for i, item in enumerate(items) if (q := _candidate_dict(item, i))]
        for rid, items in region_source.items()}}
    selected = select_details(candidates, case, prepared, "regional",
                              int(_value(params, "detail_budget", 192)), checkpoint)["selected"]
    categories = set(_value(params, "detail_categories", ("hands_feet", "clothing", "hair")))
    visible = [q for q in selected if q["category"] in categories]
    detail_lines = [(LineString(q["points"]), q["category"]) for q in visible]
    tolerance = h / 768
    output = {"contours": [], "form": [], "cores": []}
    for line, role in base:
        checkpoint()
        if role != "hatch" and any(
            line.envelope.buffer(tolerance).intersects(detail.envelope)
            and line.length > 0
            and line.intersection(detail.buffer(tolerance)).length / line.length >= .85
            and detail.length >= line.length * .8
            for detail, _ in detail_lines
        ):
            continue
        output["form" if role == "hatch" else "contours"].append(
            np.asarray(line.coords, dtype=float))
    output["contours"].extend(face_paths)
    hair_flow = float(_value(params, "hair_flow", 0))
    image_direction = None
    if hair_flow > 0 and any(category == "hair" for _, category in detail_lines):
        lum = np.asarray(evidence.rgb, float) @ np.array([.2126, .7152, .0722])
        gy, gx = np.gradient(gaussian_filter(lum, 2.))
        image_direction = (-gy, gx)
    for line, category in detail_lines:
        checkpoint()
        points = np.asarray(line.coords, dtype=float)
        if category == "hair" and hair_flow > 0:
            points = _bend_hair_guide(points, image_direction, hair_flow)
        output["contours"].append(points)
    if cores:
        # Raster gaps stay open, and vector clearance protects all accepted
        # contours and supplied detail guides after regional allocation.
        paper_w = h if _value(params, "rotate", 0) in (90, 270) else w
        protected = unary_union([LineString(q) for q in output["contours"]]).buffer(
            float(_value(params, "clearance", .6)) * paper_w /
            float(_value(params, "width", 150)))
        for q in cores:
            checkpoint()
            output["cores"].extend(np.asarray(part.coords, float) for part in
                                   line_components(LineString(q).difference(protected))
                                   if part.length > 1)
    return output


def render_regional(evidence, params, checkpoint=lambda: None) -> list[np.ndarray]:
    """Public source-pixel list API for the frozen regional recipe."""
    groups = render_regional_components(evidence, params, checkpoint)
    return groups["form"] + groups["contours"] + groups["cores"]
