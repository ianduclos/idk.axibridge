"""Text — plotter fonts set as clean, plottable lines.

Two font families in one dropdown:

* **Stick 0–9** — the CamBam stick fonts bundled in ``axibridge/fonts/stick/``
  (single-line engraving faces, freeware — see THIRD-PARTY-NOTICES.md).
  Rendered from the TrueType outlines via fontTools: each glyph's contours
  are extracted, quadratics flattened, and — critically — the reversed
  out-and-back segments stick fonts are built from are DEDUPED, or every
  stroke would plot twice (drawn forward, then traced back over itself).
* **Hershey (vpype's built-ins)** — futural, scriptc, gothiceng, … rendered
  through ``vpype.text_line``, the same engine glyphgram uses, but kept
  faithful: no distortion, no chaining, just the glyphs.

Layout: lines split on ``\\n``, stacked at ``size × line_spacing`` downward,
advance from the font's own metrics plus ``tracking_mm`` per character. The
finished block is shifted so its top-left sits at the bed origin — placement
is the layer transform's job, like every procedural source.

Geometry-as-params with no captured state: pure function of the text. Empty
text is the deliberate empty-layer state (the "＋ empty layer" contract).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path as FsPath
from typing import Literal

import vpype
from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source
from ._fontglyph import glyph_contours

_FONT_DIR = FsPath(__file__).parent.parent / "fonts" / "stick"

#: stick font id → bundled file (mind the odd capitalization of stick 9)
_STICK_FILES = {
    **{f"stick{i}": f"1CamBam_Stick_{i}.ttf" for i in range(9)},
    "stick9": "1CAMBam_Stick_9.ttf",
}

_HERSHEY = sorted(vpype.FONT_NAMES)
_FONT_IDS = [*_STICK_FILES, *_HERSHEY]
_Font = Literal[*_FONT_IDS]  # noqa: F722 — dynamic enum from both families

_MAX_CHARS = 2000  # bounded params: unbounded text reaches an open-loop machine


class TextParams(BaseModel):
    text: str = Field(
        default="", max_length=_MAX_CHARS, title="Text",
        description="Newlines start a new line; empty = empty layer",
        json_schema_extra={"format": "textarea"},
    )
    font: _Font = Field(default="stick3", title="Font")
    size: float = Field(default=10.0, ge=1.0, le=100.0, title="Size (mm)",
                        description="Em height of the glyphs on the sheet")
    line_spacing: float = Field(default=1.2, ge=0.5, le=3.0, title="Line spacing ×")
    tracking_mm: float = Field(default=0.0, ge=-5.0, le=10.0,
                               title="Letter tracking (mm)",
                               description="Extra space after every character")
    dedupe: bool = Field(
        default=True, title="Dedupe strokes",
        description="Drop the reversed out-and-back segments stick fonts are "
                    "built from — off plots every stroke twice (slightly "
                    "bolder, double the time)",
        json_schema_extra={"group": "Fine tuning"},
    )
    flatten_tol: float = Field(
        default=0.1, ge=0.02, le=1.0, title="Curve tolerance (mm)",
        description="Lower is smoother; higher values use fewer points and may show facets in effects and plotting.",
        json_schema_extra={"group": "Fine tuning"},
    )


# -- stick fonts (fontTools) ----------------------------------------------------


@lru_cache(maxsize=len(_STICK_FILES))
def _stick_font(font_id: str):
    from fontTools.ttLib import TTFont  # local import: only stick fonts need it
    return TTFont(_FONT_DIR / _STICK_FILES[font_id])


def _dedupe_segments(contours: list[list[tuple[float, float]]]
                     ) -> list[list[tuple[float, float]]]:
    """Drop segments whose exact reverse already appeared (stick fonts trace
    each stroke out AND back). If dropping a segment breaks continuity the
    kept remainder starts a fresh polyline — never a phantom jump."""
    seen: set[tuple[float, float, float, float]] = set()
    out: list[list[tuple[float, float]]] = []
    for contour in contours:
        cur: list[tuple[float, float]] = []
        for a, b in zip(contour, contour[1:]):
            key = (round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3))
            rkey = (key[2], key[3], key[0], key[1])
            if key in seen or rkey in seen:
                continue  # already drawn this stroke (in either direction)
            seen.add(key)
            if cur and cur[-1] != a:  # gap from a dropped segment: new polyline
                if len(cur) >= 2:
                    out.append(cur)
                cur = []
            if not cur:
                cur = [a]
            cur.append(b)
        if len(cur) >= 2:
            out.append(cur)
    return out


def _stick_line(text: str, font_id: str, size: float, tracking: float,
                dedupe: bool, tol: float) -> list[list[tuple[float, float]]]:
    """One line of stick-font text as machine-frame polylines (y DOWN),
    starting at x=0 with the baseline at y=0."""
    font = _stick_font(font_id)
    scale = size / font["head"].unitsPerEm
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    hmtx = font["hmtx"]
    out: list[list[tuple[float, float]]] = []
    x = 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            x += 0.5 * size  # missing glyph: blank advance, no mark
            continue
        contours = glyph_contours(glyphs[name], tol, glyphs)
        if dedupe:
            contours = _dedupe_segments(contours)
        for contour in contours:
            out.append([(x + px * scale, -py * scale) for px, py in contour])
        x += hmtx[name][0] * scale + tracking
    return out


# -- layout ---------------------------------------------------------------------


def _block(params: TextParams) -> list[list[tuple[float, float]]]:
    lines = params.text.split("\n")
    step = params.size * params.line_spacing
    paths: list[list[tuple[float, float]]] = []
    for i, line in enumerate(lines):
        if not line:
            continue
        yoff = i * step
        if params.font in _STICK_FILES:
            segs = _stick_line(line, params.font, params.size,
                               params.tracking_mm, params.dedupe, params.flatten_tol)
        else:
            lc = vpype.text_line(line, params.font, size=params.size,
                                 spacing=params.tracking_mm)
            segs = [[(p.real, p.imag) for p in seg] for seg in lc]
        for seg in segs:
            if len(seg) >= 2:
                paths.append([(x, y + yoff) for x, y in seg])
    if not paths:
        return []
    # shift the block so its top-left sits at the bed origin
    minx = min(x for seg in paths for x, _ in seg)
    miny = min(y for seg in paths for _, y in seg)
    return [[(x - minx, y - miny) for x, y in seg] for seg in paths]


@register_source
class TextSource(SourceModule):
    id = "text"
    orientation = "geometry"  # a horizontal baseline, and no rotation param to remap — the reported bug
    label = "Text"
    description = ("Clean plottable text: CamBam stick fonts (single-line "
                   "engraving) plus vpype's Hershey fonts, multiline.")
    Params = TextParams

    def generate(self, params: TextParams) -> PathDocument:
        if not params.text.strip():
            # an empty layer is a deliberate state ("＋ empty layer" contract)
            return PathDocument(layers=[], source="text (empty)")
        paths = [Path(points=seg, filled=False) for seg in _block(params)]
        xs = [x for p in paths for x, _ in p.points]
        ys = [y for p in paths for _, y in p.points]
        return PathDocument(
            layers=[Layer(id=1, name="text", paths=paths)],
            width=max(xs) if xs else 0.0, height=max(ys) if ys else 0.0,
            source=f"text {len(params.text)} chars ({params.font})",
        )
