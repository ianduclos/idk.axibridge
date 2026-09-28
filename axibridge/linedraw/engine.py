"""Pure model-evidence -> executable pen paths in millimetres."""

import numpy as np
from scipy.ndimage import gaussian_filter, distance_transform_edt
from shapely.geometry import Polygon, LineString, GeometryCollection, box
from shapely import make_valid
from shapely.ops import unary_union
from ..model import Path, Layer, PathDocument
from ..render_work import checkpoint as render_checkpoint
from .contracts import LinedrawV3Params, region_mask, Candidate
from .trace import trace_map, photographic_map
from .geometry import samples, arc, simplify
from .shadows import shadow_field, shapes, line_components
from .flow_hatch import flow_hatch
from .shading import scanline_mask


def clipped_candidates(candidates, mask, checkpoint=render_checkpoint):
    h, w = mask.shape
    out = []
    for c in candidates:
        checkpoint()
        dense = samples(c.points, 0.7)
        ix = np.clip(dense[:, 0].astype(int), 0, w - 1)
        iy = np.clip(dense[:, 1].astype(int), 0, h - 1)
        good = mask[iy, ix]
        starts = np.flatnonzero(np.diff(np.r_[False, good, False].astype(int)) == 1)
        ends = np.flatnonzero(np.diff(np.r_[False, good, False].astype(int)) == -1)
        for j, (a, b) in enumerate(zip(starts, ends)):
            if b - a >= 3 and arc(dense[a:b]) >= 2.5:
                out.append(
                    Candidate(
                        simplify(dense[a:b], 0.3), c.confidence, f"{c.identity}-{j}"
                    )
                )
    return out


def select(candidates, budget, w, h, checkpoint):
    # Independent spatial queues keep a single long passage from spending all ink.
    if not budget:
        return []
    queues = [[] for _ in range(9)]
    for c in candidates:
        checkpoint()
        center = c.points.mean(axis=0)
        cell = min(2, int(3 * center[1] / h)) * 3 + min(2, int(3 * center[0] / w))
        queues[cell].append(c)
    for queue in queues:
        queue.sort(
            key=lambda c: (
                -(arc(c.points) ** 0.67) * (0.22 + c.confidence) ** 0.5,
                c.identity,
            )
        )
    selected = []
    occupied = np.zeros((h, w), bool)
    while any(queues) and len(selected) < budget:
        checkpoint()
        for queue in queues:
            while queue:
                checkpoint()
                c = queue.pop(0)
                q = samples(c.points, 1)
                ix = np.clip(q[:, 0].astype(int), 0, w - 1)
                iy = np.clip(q[:, 1].astype(int), 0, h - 1)
                if occupied[iy, ix].mean() > 0.65:
                    continue
                selected.append(c.points)
                occupied[iy, ix] = True
                # one-pixel duplicate tolerance, without joining independent lines
                occupied[np.clip(iy + 1, 0, h - 1), ix] = True
                occupied[iy, np.clip(ix + 1, 0, w - 1)] = True
                break
            if len(selected) >= budget:
                break
    return selected


def fill_lines(shape, spacing, checkpoint):
    if shape.is_empty:
        return []
    x0, y0, x1, y1 = shape.bounds
    out = []
    for y in np.arange(y0 + spacing / 2, y1, spacing):
        checkpoint()
        out.extend(
            np.asarray(line.coords)
            for line in line_components(
                shape.intersection(LineString([(x0, y), (x1, y)]))
            )
            if line.length > 0.1
        )
        if len(out) > 20000:
            raise ValueError("Too many fill strokes; increase fill spacing")
    return out


def rotate_points(q, w, h, rotation):
    x, y = q[:, 0], q[:, 1]
    if rotation == 90:
        return np.column_stack((h - y, x))
    if rotation == 180:
        return np.column_stack((w - x, h - y))
    if rotation == 270:
        return np.column_stack((y, w - x))
    return q.copy()


def render_document(evidence, params, *, checkpoint=render_checkpoint):
    p = params if isinstance(params, LinedrawV3Params) else LinedrawV3Params(**params)
    h, w = evidence.rgb.shape[:2]
    checkpoint()
    if p.style in ("light_support", "regional_form"):
        if p.style == "light_support":
            from .reference_light import render_light_components
            output = render_light_components(evidence, p, checkpoint)
        else:
            from .regional_form import render_regional_components
            output = render_regional_components(evidence, p, checkpoint)
        return document_from_paths(output, p, w, h, checkpoint)
    fg = evidence.foreground > 0.35
    if evidence.alpha is not None:
        fg = fg & (evidence.alpha > 0.5)
    paper_w, paper_h = (h, w) if p.rotate in (90, 270) else (w, h)
    scale = p.width / paper_w
    active = [f for f in p.faces if f.enabled]
    face_mask = np.zeros((h, w), bool)
    face_paths = []
    for face in active:
        checkpoint()
        mask = region_mask(face, w, h) & fg
        face_mask |= mask
        candidates = evidence.face_candidates.get(face.id, ())
        face_paths.extend(
            select(
                clipped_candidates(candidates, mask, checkpoint),
                p.face_budget,
                w,
                h,
                checkpoint,
            )
        )
    pool = []
    for name, arr, native in [
        ("whole", evidence.whole_lines, evidence.whole_candidates),
        ("tiles", evidence.tiled_lines, evidence.tiled_candidates),
        ("photo", photographic_map(evidence.rgb), None),
    ]:
        checkpoint()
        pool.extend(native if native is not None else trace_map(arr, name, checkpoint))
    pool = clipped_candidates(pool, fg & ~face_mask, checkpoint)
    if len(pool) > 20000:
        raise ValueError("Too much detail; reduce image detail")
    contours = select(pool, p.contour_budget, w, h, checkpoint) + face_paths
    output = {"contours": list(contours), "form": [], "cores": []}
    if p.style != "contours" and fg.any() and p.shadow_strength > 0:
        checkpoint()
        if p.shadow_proxy == "material":
            if not active:
                raise ValueError(
                    "Material shadows need a face region; add a face or select local darkness"
                )
            field, _ = shadow_field(
                evidence.rgb, fg, [region_mask(f, w, h) for f in active]
            )
        else:
            lum = evidence.rgb @ np.array([0.2126, 0.7152, 0.0722])
            base = gaussian_filter(lum * fg, 32) / np.maximum(
                gaussian_filter(fg.astype(float), 32), 1e-5
            )
            field = np.clip(1 - lum / np.maximum(base, 0.05), 0, 1)
        threshold = 0.32 - 0.24 * p.shadow_strength
        groups, mask = shapes(field, fg, 2, 12, 128, threshold, checkpoint=checkpoint)
        mass = GeometryCollection()
        for _, rings in groups:
            checkpoint()
            component = GeometryCollection()
            for q in rings:
                checkpoint()
                component = component.symmetric_difference(make_valid(Polygon(q)))
            mass = mass.union(component)
        mass = mass.intersection(box(0, 0, w, h))
        protected = unary_union([LineString(q) for q in contours]).buffer(
            p.clearance / scale
        )
        mass = mass.difference(protected)
        if p.style == "shadow_shapes":
            if p.shading_mode == "original":
                output["cores"] += fill_lines(mass, p.fill_spacing / scale, checkpoint)
            else:
                deep = mask & (field >= threshold + .16)
                bands = [(mask & ~deep, p.fill_spacing / scale * 2)]
                if p.core_strength > 0:
                    bands.append((deep, p.fill_spacing / scale /
                                  max(.25, 2 * p.core_strength)))
                for band, spacing in bands:
                    for q in scanline_mask(band, spacing, checkpoint):
                        checkpoint()
                        output["cores"].extend(
                            np.asarray(line.coords) for line in
                            line_components(LineString(q).intersection(mass))
                            if line.length > .1)
        else:
            if evidence.normals is None:
                raise ValueError("Surface-normal model is required for form hatching")
            inset = distance_transform_edt(mask) > max(1, 1 / scale)
            # Never hatch over accepted face regions; facial marks use crop evidence.
            inset &= ~face_mask
            raw = flow_hatch(
                inset,
                evidence.normals,
                spacing=p.hatch_spacing / scale / p.form_density,
                checkpoint=checkpoint,
                coherent=p.form_flow == "coherent",
                density_field=np.clip(field * 2, 0, 1)
                if p.shading_mode == "tonal" else None,
            )
            hatch = []
            for i, q in enumerate(raw):
                checkpoint()
                for j, line in enumerate(
                    line_components(LineString(q).intersection(mass))
                ):
                    if line.length >= max(6, 2 / scale):
                        hatch.append(
                            Candidate(np.asarray(line.coords), 1, f"hatch-{i}-{j}")
                        )
            budget = 60 if p.style == "light_form" else 300
            if p.shading_mode == "tonal":
                budget = min(900, round(budget * p.form_density))
                # More strokes survive in the darker interior, while the
                # existing polygon and vector clearance remain authoritative.
                hatch = [Candidate(c.points, min(1., _line_tone(c.points, field) * 3),
                                   c.identity) for c in hatch
                         if _line_tone(c.points, field) >= .04]
            output["form"] += select(hatch, budget, w, h, checkpoint)
            if p.style == "face_form":
                # Reserve dense shadow cores for the deepest evidence only.
                core_groups, _ = shapes(
                    field,
                    fg & ~face_mask,
                    3,
                    25,
                    64,
                    threshold + (0.2 if p.shading_mode == "original" else
                                 0.28 - 0.2 * p.core_strength),
                    checkpoint=checkpoint,
                )
                core = GeometryCollection()
                for _, rings in core_groups:
                    checkpoint()
                    part = GeometryCollection()
                    for q in rings:
                        checkpoint()
                        part = part.symmetric_difference(make_valid(Polygon(q)))
                    core = core.union(part)
                core = core.intersection(box(0, 0, w, h)).difference(protected)
                if p.shading_mode == "original" or p.core_strength > 0:
                    spacing = p.fill_spacing / scale
                    if p.shading_mode == "tonal":
                        spacing /= max(.25, 2 * p.core_strength)
                    output["cores"] += fill_lines(core, spacing, checkpoint)
    return document_from_paths(output, p, w, h, checkpoint)


def _line_tone(points, field):
    q = np.asarray(points)
    h, w = field.shape
    ix = np.clip(np.rint(q[:, 0]).astype(int), 0, w - 1)
    iy = np.clip(np.rint(q[:, 1]).astype(int), 0, h - 1)
    return float(np.mean(field[iy, ix]))


def _smooth_path_mm(points, amount):
    """Relax shallow facets, keeping endpoints and tight turns that frame gaps."""
    if amount <= 0 or len(points) < 3:
        return points
    original = points.copy()
    result = points.copy()
    before, after = np.diff(original, axis=0)[:-1], np.diff(original, axis=0)[1:]
    cosine = np.sum(before * after, axis=1) / np.maximum(
        np.linalg.norm(before, axis=1) * np.linalg.norm(after, axis=1), 1e-12)
    # A right-angle or sharper turn can bound a deliberate white opening.
    easing = np.clip((cosine - .7) / .25, 0, 1)
    for _ in range(2):
        target = result.copy()
        target[1:-1] = result[1:-1] + easing[:, None] * (
            (result[:-2] + 2 * result[1:-1] + result[2:]) / 4 - result[1:-1])
        delta = target - original
        length = np.linalg.norm(delta, axis=1)
        result = original + delta * np.minimum(1, amount / np.maximum(length, 1e-12))[:, None]
    result[0], result[-1] = original[0], original[-1]
    return result


def document_from_paths(output, p, w, h, checkpoint):
    paper_w, paper_h = (h, w) if p.rotate in (90, 270) else (w, h)
    scale = p.width / paper_w
    checkpoint()
    if isinstance(output, dict):
        components = output
    else:
        components = {"contours": output, "form": [], "cores": []}
    enabled = set(p.ink_components)
    selected = {name: components.get(name, []) for name in ("contours", "form", "cores") if name in enabled}
    if sum(len(lines) for lines in selected.values()) > 20000 or sum(
        len(q) for lines in selected.values() for q in lines
    ) > 500000:
        raise ValueError(
            "Drawing is too detailed; reduce stroke budgets or increase spacing"
        )
    layers = []
    smoothing = getattr(p, "smoothing_mm", 0)
    for identity, name in enumerate(("contours", "form", "cores"), 1):
        if name not in selected:
            continue
        paths = []
        for q in selected[name]:
            checkpoint()
            q = np.asarray(q, float).copy()
            q[:, 0] = np.clip(q[:, 0], 0, w)
            q[:, 1] = np.clip(q[:, 1], 0, h)
            q = rotate_points(q, w, h, p.rotate) * scale
            if not np.isfinite(q).all():
                raise ValueError("Nonfinite drawing geometry")
            q = _smooth_path_mm(q, smoothing)
            paths.append(Path(points=q.tolist()))
        layers.append(Layer(id=identity, name=name, paths=paths))
    return PathDocument(
        layers=layers,
        width=p.width,
        height=paper_h * scale,
        source="linedraw_v3",
    )
