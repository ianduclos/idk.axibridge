"""Text (filled) — real font outlines as closed, fillable shapes.

Where text.py plots letterforms as single engraved lines, this renders
actual glyph outlines: every contour becomes a closed `Path(filled=True)`
ring, right down to the counters in "o"/"e"/"B" — which read as holes
automatically, the same way any other filled-path source's holes do (see
`_fontglyph.py`'s docstring; no explicit hole handling lives here, or
anywhere a generator hands filled rings to the compositor).

One font ships in-repo: Recursive (OFL, `google/fonts`), a variable font
whose weight/slant/mono/casual axes are exposed as sliders. Each slider is
a no-op if the loaded font doesn't declare that axis tag (`_fontglyph.
instantiate` drops unknown tags silently) — the same four fields stay safe
on any font, including the ones this reaches for next: `font` also accepts
a system-discovered face id (`system_fonts.catalogue()`), so real
Helvetica/Arial/Times New Roman render here where actually installed —
they're proprietary (Monotype/Linotype) and this repo can't bundle them,
so finding real copies on the machine is the only path to them, rather
than shipping open metric-compatible substitutes under those names.
Unresolvable ids (a system font since uninstalled) fall back to the
bundled font rather than raising — a saved project should still open.

Layout mirrors text.py: lines split on `\\n`, stacked at `size ×
line_spacing`, glyphs advance by the font's own (instance-correct) hmtx
plus `tracking_mm`, the finished block shifted so its top-left sits at the
bed origin — placement is the layer transform's job, like every procedural
source.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path as FsPath

from pydantic import BaseModel, Field

from .. import system_fonts
from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source
from . import _fontglyph as fg

_VARIABLE_DIR = FsPath(__file__).parent.parent / "fonts" / "variable"

_DEFAULT_FONT = "recursive"

# Contributed to the shared system_fonts catalogue (not a private mapping
# here) so /api/fonts stays one generic lookup regardless of how many
# source modules end up bundling a font — see system_fonts.register_bundled.
system_fonts.register_bundled(
    _DEFAULT_FONT, "Recursive (variable)", _VARIABLE_DIR / "Recursive-Variable.ttf")

_MAX_CHARS = 2000  # bounded params: unbounded text reaches an open-loop machine


class TextFillParams(BaseModel):
    text: str = Field(
        default="", max_length=_MAX_CHARS, title="Text",
        description="Newlines start a new line; empty = empty layer",
        json_schema_extra={"format": "textarea"},
    )
    font: str = Field(default=_DEFAULT_FONT, title="Font",
                      json_schema_extra={"format": "font"})
    size: float = Field(default=10.0, ge=1.0, le=100.0, title="Size (mm)",
                        description="Em height of the glyphs on the sheet")
    line_spacing: float = Field(default=1.2, ge=0.5, le=3.0, title="Line spacing ×")
    tracking_mm: float = Field(default=0.0, ge=-5.0, le=10.0,
                               title="Letter tracking (mm)",
                               description="Extra space after every character")
    weight: float = Field(
        default=400.0, ge=300.0, le=1000.0, title="Weight",
        description="Variable 'wght' axis — no-op on a font without one",
        json_schema_extra={"group": "Variable axes"},
    )
    slant: float = Field(
        default=0.0, ge=-15.0, le=0.0, title="Slant",
        description="Variable 'slnt' axis — no-op on a font without one",
        json_schema_extra={"group": "Variable axes"},
    )
    mono: float = Field(
        default=0.0, ge=0.0, le=1.0, title="Mono",
        description="Variable 'MONO' axis — no-op on a font without one",
        json_schema_extra={"group": "Variable axes"},
    )
    casual: float = Field(
        default=0.0, ge=0.0, le=1.0, title="Casual",
        description="Variable 'CASL' axis — no-op on a font without one",
        json_schema_extra={"group": "Variable axes"},
    )
    flatten_tol: float = Field(
        default=0.1, ge=0.02, le=1.0, title="Curve flatten tolerance (mm)",
        json_schema_extra={"group": "Fine tuning"},
    )


# -- font loading + instancing -----------------------------------------------


@lru_cache(maxsize=64)
def _load_font(path: str, font_number: int):
    return fg.load_font_file(path, font_number)


def _resolve_font(font_id: str):
    """A TTFont for `font_id`, looked up in the shared catalogue (bundled or
    system-discovered — see system_fonts.py). Falls back to the default
    bundled font rather than raising: a project saved with a since-
    uninstalled system font should still open, just with different glyphs,
    not a broken layer."""
    face = system_fonts.find(font_id) or system_fonts.find(_DEFAULT_FONT)
    return _load_font(face.path, face.font_number)


def _axes(p: TextFillParams) -> dict[str, float]:
    return {"wght": p.weight, "slnt": p.slant, "MONO": p.mono, "CASL": p.casual}


# -- glyph layout --------------------------------------------------------------


def _line(text: str, font_id: str, size: float, tracking: float, tol_mm: float,
         axes: dict[str, float]) -> list[list[tuple[float, float]]]:
    """One line of filled-outline text as machine-frame closed rings
    (y DOWN), starting at x=0 with the baseline at y=0."""
    font = fg.instantiate(_resolve_font(font_id), font_id, axes)
    scale = size / font["head"].unitsPerEm
    tol_fu = tol_mm / scale if scale else tol_mm  # flatten in font units, label in mm
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
        for ring in fg.glyph_rings(glyphs[name], tol_fu, glyphs):
            out.append([(x + px * scale, -py * scale) for px, py in ring])
        x += hmtx[name][0] * scale + tracking
    return out


def _block(params: TextFillParams) -> list[list[tuple[float, float]]]:
    lines = params.text.split("\n")
    step = params.size * params.line_spacing
    axes = _axes(params)
    rings: list[list[tuple[float, float]]] = []
    for i, line in enumerate(lines):
        if not line:
            continue
        yoff = i * step
        for ring in _line(line, params.font, params.size, params.tracking_mm,
                          params.flatten_tol, axes):
            rings.append([(x, y + yoff) for x, y in ring])
    if not rings:
        return []
    # shift the block so its top-left sits at the bed origin
    minx = min(x for ring in rings for x, _ in ring)
    miny = min(y for ring in rings for _, y in ring)
    return [[(x - minx, y - miny) for x, y in ring] for ring in rings]


@register_source
class TextFillSource(SourceModule):
    id = "text_fill"
    orientation = "geometry"  # a horizontal baseline, and no rotation param to remap
    label = "Text (filled)"
    description = ("Real font outlines as closed, fillable shapes — counters "
                   "in letters like \"o\"/\"e\"/\"B\" read as holes.")
    Params = TextFillParams

    def generate(self, params: TextFillParams) -> PathDocument:
        if not params.text.strip():
            # an empty layer is a deliberate state ("＋ empty layer" contract)
            return PathDocument(layers=[], source="text_fill (empty)")
        paths = [Path(points=ring, filled=True) for ring in _block(params)]
        xs = [x for p in paths for x, _ in p.points]
        ys = [y for p in paths for _, y in p.points]
        return PathDocument(
            layers=[Layer(id=1, name="text (filled)", paths=paths)],
            width=max(xs) if xs else 0.0, height=max(ys) if ys else 0.0,
            source=f"text_fill {len(params.text)} chars ({params.font})",
        )
