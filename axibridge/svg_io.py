"""SVG ⇄ PathDocument ⇄ vpype.Document conversions.

Two readers live here:

* :func:`doc_from_svg` — the v2 fill-aware reader, built directly on
  svgelements. It records each path's ``filled`` flag (the input to
  fill-aware occlusion masks), follows the vpype layer convention (top-level
  groups = layers), and flattens curves by recursive subdivision against the
  quantization tolerance.
* vpype converters (:func:`doc_to_vpype` / :func:`doc_from_vpype`) — kept for
  SVG export and for the plot-pass optimisation ops, which run through vpype.

vpype and CSS SVG work in pixels (96 dpi); the IPR is millimetres. All unit
conversion is confined to this file — nothing else in axibridge should ever
see a pixel.
"""

from __future__ import annotations

import io
import math

import numpy as np
import svgelements as se
import vpype

from .model import LAYER_PALETTE, Layer, Path, PathDocument

#: CSS pixels per millimetre (96 dpi) — vpype's convention.
PX_PER_MM = 96.0 / 25.4

#: svgelements hardcodes a *slightly different* mm constant (3.7795296, not
#: 96/25.4 = 3.77952756). The svgelements-based reader must divide by THEIR
#: constant or every mm→SVG→mm round-trip picks up a 5.4e-7 multiplicative
#: drift — harmless visually, but it shifts occlusion clip points and breaks
#: exact save/load reproducibility.
_SE_PX_PER_MM = float(se.Length("1mm").value(ppi=96.0))

_INKSCAPE_LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"


def _color_of(lc: vpype.LineCollection, fallback: str) -> str:
    try:
        c = lc.property(vpype.METADATA_FIELD_COLOR)
        return str(c) if c is not None else fallback
    except Exception:
        return fallback


def _name_of(lc: vpype.LineCollection, fallback: str) -> str:
    try:
        n = lc.property(vpype.METADATA_FIELD_NAME)
        return str(n) if n else fallback
    except Exception:
        return fallback


def doc_from_vpype(vdoc: vpype.Document, source: str = "") -> PathDocument:
    """Convert a vpype Document (px) to a PathDocument (mm)."""
    layers: list[Layer] = []
    for i, (lid, lc) in enumerate(sorted(vdoc.layers.items())):
        paths = [
            Path(points=[(z.real / PX_PER_MM, z.imag / PX_PER_MM) for z in line])
            for line in lc
            if len(line) > 0
        ]
        layers.append(
            Layer(
                id=int(lid),
                name=_name_of(lc, f"layer {lid}"),
                color=_color_of(lc, LAYER_PALETTE[i % len(LAYER_PALETTE)]),
                paths=paths,
            )
        )
    width = height = None
    if vdoc.page_size is not None:
        width = vdoc.page_size[0] / PX_PER_MM
        height = vdoc.page_size[1] / PX_PER_MM
    return PathDocument(layers=layers, width=width, height=height, source=source)


def doc_to_vpype(doc: PathDocument) -> vpype.Document:
    """Convert a PathDocument (mm) to a vpype Document (px), preserving layer
    ids, names and colours so vpype operations stay layer-aware."""
    vdoc = vpype.Document()
    for layer in doc.layers:
        lc = vpype.LineCollection(
            [
                np.array([complex(x * PX_PER_MM, y * PX_PER_MM) for x, y in p.points])
                for p in layer.paths
            ]
        )
        try:
            lc.set_property(vpype.METADATA_FIELD_NAME, layer.name)
            lc.set_property(vpype.METADATA_FIELD_COLOR, layer.color)
        except Exception:
            pass
        vdoc.add(lc, layer_id=layer.id)
    if doc.width is not None and doc.height is not None:
        vdoc.page_size = (doc.width * PX_PER_MM, doc.height * PX_PER_MM)
    return vdoc


# ---------------------------------------------------------------------------
# Fill-aware SVG reader (svgelements)
# ---------------------------------------------------------------------------


def _flatten_cubic(p0, p1, p2, p3, tol: float, out: list) -> None:
    """Recursive de Casteljau flattening: subdivide until the control points
    sit within ``tol`` of the chord, then emit the endpoint."""
    d1 = _point_chord_dist(p1, p0, p3)
    d2 = _point_chord_dist(p2, p0, p3)
    if max(d1, d2) <= tol:
        out.append(p3)
        return
    # de Casteljau split at t=0.5
    m01 = _mid(p0, p1); m12 = _mid(p1, p2); m23 = _mid(p2, p3)
    m012 = _mid(m01, m12); m123 = _mid(m12, m23)
    m = _mid(m012, m123)
    _flatten_cubic(p0, m01, m012, m, tol, out)
    _flatten_cubic(m, m123, m23, p3, tol, out)


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _point_chord_dist(p, a, b) -> float:
    """Distance from p to segment a-b."""
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    n = dx * dx + dy * dy
    if n < 1e-18:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / n))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def _pt(sp) -> tuple[float, float]:
    return (float(sp.x), float(sp.y))


def _shape_to_paths(shape: se.Shape, tol_px: float) -> list[Path]:
    """Flatten one svgelements Shape into IPR paths (still in px)."""
    filled = (
        shape.fill is not None
        and shape.fill.value is not None
        and (shape.fill.alpha or 0) > 0
    )
    paths: list[Path] = []
    for sub in se.Path(shape).as_subpaths():
        pts: list[tuple[float, float]] = []
        closed = False
        for seg in sub.segments():
            if isinstance(seg, se.Move):
                if seg.end is not None:
                    pts = [_pt(seg.end)]
            elif isinstance(seg, se.Close):
                closed = True
                if pts and pts[0] != pts[-1]:
                    pts.append(pts[0])
            elif isinstance(seg, se.Line):
                pts.append(_pt(seg.end))
            elif isinstance(seg, se.CubicBezier):
                _flatten_cubic(_pt(seg.start), _pt(seg.control1),
                               _pt(seg.control2), _pt(seg.end), tol_px, pts)
            elif isinstance(seg, se.QuadraticBezier):
                # promote to cubic (exact) then flatten
                p0, pc, p3 = _pt(seg.start), _pt(seg.control), _pt(seg.end)
                c1 = (p0[0] + 2 / 3 * (pc[0] - p0[0]), p0[1] + 2 / 3 * (pc[1] - p0[1]))
                c2 = (p3[0] + 2 / 3 * (pc[0] - p3[0]), p3[1] + 2 / 3 * (pc[1] - p3[1]))
                _flatten_cubic(p0, c1, c2, p3, tol_px, pts)
            elif isinstance(seg, se.Arc):
                for cub in seg.as_cubic_curves():
                    _flatten_cubic(_pt(cub.start), _pt(cub.control1),
                                   _pt(cub.control2), _pt(cub.end), tol_px, pts)
        if len(pts) >= 2:
            paths.append(Path(points=pts, filled=filled and closed))
    return paths


def doc_from_svg(
    svg_text: str, quantization_mm: float = 0.1, source: str = "uploaded SVG"
) -> PathDocument:
    """Parse SVG markup into the IPR, fill-aware.

    ``quantization_mm`` is the curve-flattening tolerance: the maximum
    distance between the true curve and its polyline approximation. This is
    *the* lossy step of the whole pipeline, which is why it is a parameter
    and not a constant.

    Layer convention (vpype-compatible): each top-level ``<g>`` is a layer
    (named by ``inkscape:label`` or ``id``); shapes outside any group land in
    a catch-all layer. ``filled`` is set from the element's actual SVG fill —
    the input for fill-aware occlusion.
    """
    svg = se.SVG.parse(io.StringIO(svg_text), reify=True, ppi=96.0)
    tol_px = quantization_mm * _SE_PX_PER_MM

    def collect(el) -> list[Path]:
        out: list[Path] = []
        if isinstance(el, se.Group):
            for child in el:
                out.extend(collect(child))
        elif isinstance(el, se.Shape):
            out.extend(_shape_to_paths(el, tol_px))
        return out

    layers: list[Layer] = []
    loose: list[Path] = []
    stroke_of: dict[int, str] = {}

    def first_stroke(el) -> str | None:
        if isinstance(el, se.Shape) and el.stroke is not None and el.stroke.value is not None:
            return str(el.stroke.hex if hasattr(el.stroke, "hex") else el.stroke)
        if isinstance(el, se.Group):
            for child in el:
                s = first_stroke(child)
                if s:
                    return s
        return None

    next_id = 1
    for child in svg:
        if isinstance(child, se.Group):
            paths = collect(child)
            if not paths:
                continue
            name = child.values.get(_INKSCAPE_LABEL) or child.values.get("id") or f"layer {next_id}"
            layers.append(Layer(id=next_id, name=str(name), color="", paths=paths))
            stroke_of[next_id] = first_stroke(child) or ""
            next_id += 1
        elif isinstance(child, se.Shape):
            loose.extend(_shape_to_paths(child, tol_px))
            if next_id not in stroke_of:
                stroke_of[0] = first_stroke(child) or stroke_of.get(0, "")
    if loose:
        layers.append(Layer(id=next_id, name="ungrouped", color="", paths=loose))
        stroke_of[next_id] = stroke_of.get(0, "")

    # px -> mm (svgelements' constant — see _SE_PX_PER_MM), fallback palette
    for i, layer in enumerate(layers):
        layer.color = stroke_of.get(layer.id) or LAYER_PALETTE[i % len(LAYER_PALETTE)]
        for p in layer.paths:
            p.points = [(x / _SE_PX_PER_MM, y / _SE_PX_PER_MM) for x, y in p.points]

    width = float(svg.width) / _SE_PX_PER_MM if svg.width else None
    height = float(svg.height) / _SE_PX_PER_MM if svg.height else None
    return PathDocument(layers=layers, width=width, height=height, source=source)


def doc_to_svg(doc: PathDocument) -> str:
    """Serialise the IPR back to layered SVG (used by the saxi backend and the
    download endpoint)."""
    vdoc = doc_to_vpype(doc)
    page = vdoc.page_size
    if page is None:
        b = vdoc.bounds()
        page = (b[2], b[3]) if b else (210 * PX_PER_MM, 297 * PX_PER_MM)
    out = io.StringIO()
    vpype.write_svg(out, vdoc, page_size=page, color_mode="layer")
    return out.getvalue()
