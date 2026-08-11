"""Shared glyph-outline machinery for text sources: font loading, variable-
font axis instancing, and contour flattening — used by both the stick-font
stroke text (``text.py``) and the filled-outline text (``text_fill.py``)
generators, so the two never carry two different implementations of the
same fontTools plumbing.

Contour extraction handles TrueType ``glyf`` quadratics (with the implied
on-curve midpoint between consecutive off-curve points) and CFF/OTF cubics
(``curveTo``), both flattened through ``pen.py``'s adaptive de Casteljau
subdivider.

**Holes are deliberately not resolved here.** A glyph's contours are handed
back as independent closed rings; this repo's standing convention
(``compose.build_mask``, and the ``invert``/``hatch_fill``/``offset_fill``
effects) already reassembles nesting-derived holes uniformly, wherever a
filled region is actually needed, via even-odd containment depth over
whatever `Path(filled=True)` rings a layer holds — the IPR carries no
explicit hole field on purpose (see CLAUDE.md). This module's only job
w.r.t. correctness is producing the *right set* of rings, which matters for
glyphs authored with deliberately overlapping contours (common in variable
and display fonts, meant to be merged): those get run through skia-pathops'
nonzero-winding ``simplify()`` — the same routine fontTools' own
``removeOverlaps`` uses — when it's importable. Without it (an optional
dependency, excluded from the Pi's default install like scikit-fmm) the
raw extracted contours are used as-is, which is correct for the
overwhelming majority of well-formed, non-self-overlapping fonts.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path as FsPath

from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.ttLib import TTFont

from .pen import _flatten_cubic

try:
    import pathops
except ImportError:  # pragma: no cover - exercised on machines without it
    pathops = None

# Runtime switch: True when skia-pathops is importable. Tests that pin exact
# geometry monkeypatch this to False to force the always-available raw-
# contour path regardless of what's installed in the test environment —
# same shape as _fast_marching.py's USE_SKFMM.
USE_PATHOPS = pathops is not None

XY = tuple[float, float]
Contour = list[XY]


def solver_name() -> str:
    """Which overlap-resolution backend is currently active: "pathops"
    (compiled, optional) or "raw" (contours used as extracted, always
    available). Lets callers/logs surface which one ran."""
    return "pathops" if USE_PATHOPS else "raw"


# -- loading ----------------------------------------------------------------


def load_font_file(path: str | FsPath, font_number: int = 0) -> TTFont:
    """A TTFont from a file on disk. ``font_number`` selects a face inside a
    TrueType Collection (.ttc); ignored for single-font files."""
    return TTFont(str(path), fontNumber=font_number)


def load_font_bytes(data: bytes, font_number: int = 0) -> TTFont:
    """A TTFont from raw font bytes (an uploaded file, for instance)."""
    return TTFont(BytesIO(data), fontNumber=font_number)


# -- variable-font axis instancing -------------------------------------------

_instance_cache: dict[tuple, TTFont] = {}


def instantiate(font: TTFont, font_key: str, axes: dict[str, float]) -> TTFont:
    """A static instance of a variable font at the given axis coordinates.
    Axis tags the font doesn't declare are silently ignored — the same
    param set stays safe to apply to any font, variable or not, with
    different axes or none. ``font_key`` identifies the *source* font for
    the cache (a path or asset name), since instancing rebuilds glyf/CFF2
    and must not re-run per glyph or per keystroke."""
    fvar = font.get("fvar")
    if fvar is None or not axes:
        return font
    tags = {a.axisTag for a in fvar.axes}
    use = {t: v for t, v in axes.items() if t in tags}
    if not use:
        return font
    key = (font_key, tuple(sorted(use.items())))
    inst = _instance_cache.get(key)
    if inst is None:
        from fontTools.varLib.instancer import instantiateVariableFont
        inst = instantiateVariableFont(font, use, inplace=False)
        _instance_cache[key] = inst
    return inst


# -- contour extraction -------------------------------------------------------


def _flatten_quad(p0: XY, q: XY, p2: XY, tol: float) -> list[XY]:
    """Degree-elevate the quadratic to a cubic, then reuse pen.py's adaptive
    de Casteljau flattener. Returns points AFTER p0, ending at p2."""
    c1 = (p0[0] + (q[0] - p0[0]) * 2 / 3, p0[1] + (q[1] - p0[1]) * 2 / 3)
    c2 = (p2[0] + (q[0] - p2[0]) * 2 / 3, p2[1] + (q[1] - p2[1]) * 2 / 3)
    return _flatten_cubic(p0, c1, c2, p2, tol)


def _pen_contours(ops, tol: float) -> list[Contour]:
    """Replay a fontTools RecordingPen's recorded ops into flattened, closed
    polylines. Handles moveTo/lineTo/closePath directly, qCurveTo with
    TrueType's implied on-curve midpoints (glyf), and curveTo cubics
    (CFF/OTF, and skia-pathops' own draw() output)."""
    contours: list[Contour] = []
    cur: Contour = []
    start = (0.0, 0.0)
    pos = (0.0, 0.0)
    for op, args in ops:
        pts = [(float(x), float(y)) for x, y in args if x is not None]
        if op == "moveTo":
            if cur:
                contours.append(cur)
            cur = [pts[0]]
            start = pos = pts[0]
        elif op == "lineTo":
            cur.extend(pts)
            pos = pts[-1]
        elif op == "curveTo":
            # groups of (c1, c2, end) — fontTools' super-bezier convention
            for i in range(0, len(pts), 3):
                c1, c2, end = pts[i], pts[i + 1], pts[i + 2]
                cur.extend(_flatten_cubic(pos, c1, c2, end, tol))
                pos = end
        elif op == "qCurveTo":
            # RecordingPen gives None as the final point when the contour
            # closes through a curve — the endpoint is the contour start
            raw = list(args)
            if raw and raw[-1] is None:
                raw[-1] = start
            qpts = [(float(x), float(y)) for x, y in raw]
            # qpts[:-1] are off-curve controls, qpts[-1] the on-curve end.
            # TrueType implies an on-curve midpoint between consecutive
            # off-curve controls.
            controls = qpts[:-1]
            if not controls:
                pos = qpts[-1]
                continue
            ends = [((q[0] + controls[i + 1][0]) / 2,
                     (q[1] + controls[i + 1][1]) / 2)
                    for i, q in enumerate(controls[:-1])]
            ends.append(qpts[-1])
            for q, end in zip(controls, ends):
                cur.extend(_flatten_quad(pos, q, end, tol))
                pos = end
        elif op in ("closePath", "endPath"):
            if op == "closePath" and cur and cur[-1] != start:
                cur.append(start)
            if cur:
                contours.append(cur)
            cur = []
            pos = start
    if cur:
        contours.append(cur)
    return contours


def glyph_contours(glyph, tol: float, glyph_set=None) -> list[Contour]:
    """A glyph's raw contours as flattened polylines in font units (y up),
    before any overlap resolution. Pass `glyph_set` (the font's
    `getGlyphSet()`) to decompose composite glyphs (accented letters,
    shared-component constructions) into real contours — simple engraving
    fonts typically have none, but any full-charset font (Recursive
    included) does, and drawing a composite through a plain RecordingPen
    just records an unusable `addComponent` op instead of geometry."""
    pen = DecomposingRecordingPen(glyph_set) if glyph_set is not None else RecordingPen()
    glyph.draw(pen)
    return _pen_contours(pen.value, tol)


# -- overlap resolution -------------------------------------------------------


def resolve_rings(contours: list[Contour]) -> list[Contour]:
    """Clean, closed rings ready to become filled Paths. Runs skia-pathops'
    nonzero-winding simplification when available (merges self-overlapping
    contours into their correct minimal set); otherwise the extracted
    contours are used as-is (see module docstring for why that's still
    correct for non-self-overlapping fonts). Deliberately does not classify
    which ring is a hole — that's a downstream, uniform, even-odd-by-depth
    job (``compose.build_mask`` and friends)."""
    closed: list[Contour] = []
    for c in contours:
        if len(c) < 2:
            continue
        ring = c if c[0] == c[-1] else [*c, c[0]]
        if len(ring) >= 4:
            closed.append(ring)
    if not closed or not USE_PATHOPS:
        return closed
    path = pathops.Path()
    pen = path.getPen()
    for ring in closed:
        pen.moveTo(ring[0])
        for pt in ring[1:-1]:
            pen.lineTo(pt)
        pen.closePath()
    path.simplify()
    rec = RecordingPen()
    path.draw(rec)
    # the path fed in is all straight lines, so no curve ops come back out —
    # tol is unused, but _pen_contours needs one
    return _pen_contours(rec.value, 0.0)


def glyph_rings(glyph, tol: float, glyph_set=None) -> list[Contour]:
    """One glyph's contours as closed, overlap-resolved rings — the full
    pipeline a filled-outline text generator needs per character."""
    return resolve_rings(glyph_contours(glyph, tol, glyph_set))
