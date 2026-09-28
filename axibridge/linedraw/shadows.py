"""Shadow-shape research primitives; supplied arrays only, no reference assets.

The material proxy is a photographic heuristic, not intrinsic decomposition.
All coordinates, blur scales and areas are working-image pixels.
"""

import numpy as np
import contourpy
from scipy.ndimage import gaussian_filter, binary_closing, binary_opening, label
from shapely.geometry import GeometryCollection
from shapely.ops import unary_union
from .geometry import simplify


def shadow_field(rgb, foreground, face_masks):
    """Estimate local material darkness using caller-supplied face regions.

    RGB must be finite HxWx3 in [0,1]; masks must match HxW. At least one
    supplied face must contain samples accepted by the color heuristic.
    Face regions are annotations/detections supplied by the caller, not
    automatic body-part recognition performed here.
    """
    rgb = np.asarray(rgb, dtype=float)
    fg = np.asarray(foreground, dtype=bool)
    if rgb.shape != (*fg.shape, 3) or fg.ndim != 2:
        raise ValueError("RGB must be HxWx3 and foreground HxW")
    if not np.isfinite(rgb).all() or np.any((rgb < 0) | (rgb > 1)):
        raise ValueError("RGB must be finite and normalized to [0,1]")
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    chroma = np.stack(
        [
            np.log((rgb[..., 0] + 0.02) / (rgb[..., 1] + 0.02)),
            np.log((rgb[..., 2] + 0.02) / (rgb[..., 1] + 0.02)),
        ],
        axis=-1,
    )
    prototypes = []
    for face in face_masks:
        face = np.asarray(face, dtype=bool)
        if face.shape != fg.shape:
            raise ValueError("face masks must match foreground")
        sample = face & fg & (rgb[..., 0] - rgb[..., 2] > 0.065)
        if not sample.any():
            continue
        sample &= lum > np.percentile(lum[sample], 40)
        if sample.any():
            prototypes.append(np.median(chroma[sample], axis=0))
    if not prototypes:
        raise ValueError("no supported face color samples; proxy unavailable")
    distance = np.min(
        np.stack([np.linalg.norm(chroma - v, axis=-1) for v in prototypes]), axis=0
    )
    skin = binary_closing((distance < 0.20) & (lum > 0.15) & fg, iterations=3) & fg
    light = (~skin) & (lum > 0.42) & fg
    field = np.zeros(fg.shape, dtype=float)
    for material in (skin, light):
        base = gaussian_filter(lum * material, 32) / np.maximum(
            gaussian_filter(material.astype(float), 32), 1e-5
        )
        field[material] = np.clip(
            1 - lum[material] / np.maximum(base[material], 0.05), 0, 1
        )
    return field, {"skin": skin, "light": light}


def shapes(field, fg, sigma, minarea, cap, threshold, checkpoint=None):
    check = checkpoint or (lambda: None)
    # Normalize blur at the silhouette; never let background create a shadow rim.
    check()
    smooth = gaussian_filter(field * fg, sigma) / np.maximum(
        gaussian_filter(fg.astype(float), sigma), 1e-5
    )
    check()
    m = (smooth > threshold) & fg
    check()
    m = binary_closing(m, iterations=max(1, round(sigma / 2))) & fg
    check()
    m = binary_opening(m, iterations=1)
    check()
    labs, n = label(m)
    check()
    counts = np.bincount(labs.ravel(), minlength=n + 1)
    check()
    candidates = []
    for k in range(1, n + 1):
        check()
        size = int(counts[k])
        if size < minarea:
            continue
        candidates.append((size, k))
    selected = np.zeros_like(m)
    groups = []
    for size, k in sorted(candidates, reverse=True)[:cap]:
        check()
        component = labs == k
        selected |= component
        # Pad to close actual clipped filled regions at the image boundary.
        curves = contourpy.contour_generator(
            z=np.pad(component.astype(float), 1)
        ).lines(0.5)
        check()
        qs = []
        for c in curves:
            check()
            q = simplify(c - 1, max(0.35, sigma * 0.16))
            check()
            if len(q) > 3:
                qs.append(q)
        if qs:
            groups.append((size, qs))
        check()
    return groups, selected


def line_components(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [geometry]
    return [
        line
        for part in getattr(geometry, "geoms", [])
        for line in line_components(part)
    ]


def clear_hatching(
    hatches, protected_lines, stroke_width, clearance_strokes=1.5, minimum_strokes=2.25
):
    """Subtract true geometric clearances, potentially increasing fragments."""
    if not np.isfinite(stroke_width) or stroke_width <= 0:
        raise ValueError("stroke width must be positive and finite")
    if not all(np.isfinite(v) and v >= 0 for v in (clearance_strokes, minimum_strokes)):
        raise ValueError("clearance and minimum length must be nonnegative and finite")
    protected = unary_union(protected_lines).buffer(
        stroke_width * clearance_strokes, quad_segs=4
    )
    return [
        part
        for line in hatches
        for part in line_components(line.difference(protected))
        if part.length >= stroke_width * minimum_strokes
    ]


def cut_shadow(mass, feature_lines, edit_region, cut_width):
    """Return edited mass and removed geometry; cut_width is FULL width.

    Features outside edit_region do not cut. Callers separately retain black
    feature strokes on white paper. This function never creates white paint.
    """
    if not np.isfinite(cut_width) or cut_width <= 0:
        raise ValueError("cut width must be positive and finite")
    if not feature_lines:
        return mass, GeometryCollection()
    cutters = unary_union(feature_lines).buffer(cut_width / 2).intersection(edit_region)
    return mass.difference(cutters), mass.intersection(cutters)
