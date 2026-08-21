"""Eigenfunction fill: fill a shape with the nodal lines of its own vibration.

Sprinkle sand on a vibrating drumhead and it gathers along the lines that are
not moving. Those lines are decided entirely by the shape of the boundary, so
this is a fill that is **produced by the form** rather than laid over it —
every silhouette gives a different figure, and the same shape gives a whole
family as the mode index rises. Compare a hatch, where spacing changes density
and nothing else: here one control changes density *and* character together.

What this is NOT: a Chladni plate. A bowed metal plate is a free-edge
fourth-order (biharmonic) problem; this is a clamped membrane, a drumhead. The
figures are genuinely different and the distinction is usually glossed over —
``_eigenmode.py`` has the full statement. "Cymatics" is fair for both; Chladni
is not, so the label does not claim it.

**Why a family of levels and not just the nodal lines.** The nodal set alone
is a *thin* set — Courant's theorem caps the n-th mode at n nodal domains, so
it can only ever be a dozen or so strokes with a great deal of white between
them: a partition of the shape rather than a fill of it. Every other level set
of that same mode is equally a product of the boundary, and they nest into
long continuous closed curves, so tracing a family is what makes this a fill.
``levels = 1`` is still the bare nodal figure.

Four controls carry the idea:

* **Mode** — which vibration. Low modes are a few big lobes; push it up on an
  irregular boundary and the nodal lines drift into the quantum-chaos regime,
  tangled and unrepeating and entirely determined by the outline. Looks like
  noise, is pure structure.
* **Mix** — a symmetric shape has *repeated* frequencies, and any combination
  of the modes sharing one is also a valid mode. That is physically why a
  square gives stars, crosses and flowers rather than a single figure, and why
  this knob is signed: +1 and -1 are ``u1 + u2`` and ``u1 - u2``, two
  different pictures of the same note.
* **Levels / bias** — how many contours, and whether they spread evenly
  through each lobe (bias 0, every lobe shaded alike) or pile onto the nodal
  figure (bias 1, which keeps it legible as a dark ridge while the lobes open
  out). ``Field`` switches what is contoured: *displacement* nests the lobes;
  *sand* contours |u| instead, so the ink gathers where the surface is STILL
  and the nodal lines thicken into dark bands — which is literally what the
  sand on a real plate does.
* **Spread** — ring the shape at several frequencies at once instead of
  holding it at one, the way a struck plate does. Breaks the schematic
  symmetry of a single mode, and costs nothing: the modes are already solved.
* **Density** — an image weighs the membrane. Heavy is slow is short
  wavelength, so lines bunch and low modes gather where the picture is dark.

Each closed+filled path in the layer becomes its own membrane, with nested
loops read as holes by the same even-odd rule ``hatch_fill`` uses — and a hole
is a real boundary here, pinned like any other, so the pattern reorganises
around it. Open or unfilled paths pass through untouched.

Cost lives in the eigensolve, which is cached whole (see ``_eigenmode``):
the first move of the Mode slider pays for it and the rest are free. Detail
sets the lattice pitch, and therefore both the accuracy and the highest mode
the discretisation can honestly resolve.

No roughening or smoothing of its own — stack ``freehand`` or ``smoothen``
after it.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, Field
from shapely.geometry import LineString, Polygon

from ..channels import ChannelName, sample_rows
from ..marching import trace_contours
from ..model import Path, is_closed
from ..registry import EffectContext, EffectModule, register_effect
from . import _eigenmode

_DENSITY = {"group": "Density (image)"}

#: × the amount param: the heaviest-to-lightest mass ratio at density 1.0.
#: Wavelength goes as 1/sqrt(rho), so 8 is already a 2.8x change in line
#: spacing across the picture — well past the point where it reads.
DENSITY_CONTRAST = 8.0


class EigenFillParams(BaseModel):
    mode: int = Field(default=6, ge=1, le=200, title="Mode",
                      description="Which vibration of the shape. Higher is finer AND "
                                  "more tangled — on an irregular outline the high "
                                  "modes stop looking periodic altogether. Detail "
                                  "limits how high the lattice can honestly go")
    mix: float = Field(default=0.0, ge=-1.0, le=1.0, title="Mix",
                       description="Blend into the neighbouring mode. On a symmetric "
                                   "shape that neighbour shares this frequency, so "
                                   "+1 and -1 are two different figures of the same "
                                   "note (a square's star vs its cross); elsewhere "
                                   "it is a chord rather than a true mode")
    spread: int = Field(default=0, ge=0, le=24, title="Spread",
                        description="Sum this many further modes above Mode, with "
                                    "decaying weight — a struck plate ringing across "
                                    "a band rather than held at one frequency. 0 is a "
                                    "single pure mode")
    field: Literal["displacement", "sand"] = Field(
        default="displacement", title="Field",
        description="What the contours follow. Displacement nests the lobes of the "
                    "vibration; sand contours the STILLNESS instead, so ink gathers "
                    "along the nodal lines as bands — what the sand on a real plate "
                    "actually does")
    levels: int = Field(default=9, ge=1, le=41, title="Levels",
                        description="How many contours to trace. 1 is the bare nodal "
                                    "figure — a partition rather than a fill. This is "
                                    "the density control; Mode is the character one. "
                                    "Displacement always includes the nodal line, so "
                                    "an even count is rounded up")
    level_bias: float = Field(default=0.6, ge=0.0, le=1.0, title="Level bias",
                              description="0 spreads the contours evenly through each "
                                          "lobe; 1 piles them onto the nodal lines, "
                                          "which keeps the figure legible as a dark "
                                          "ridge while the lobes open out")
    detail: float = Field(default=1.5, ge=0.5, le=8.0, title="Detail (mm)",
                          description="Solve lattice pitch — finer follows the "
                                      "boundary more exactly, reaches higher modes, "
                                      "and costs more to solve")
    inset: float = Field(default=0.5, ge=0.0, le=10.0, title="Inset (mm)",
                         description="Pull the lines in from the outline")
    outline: bool = Field(default=True, title="Keep outline",
                          description="Off also stops the shape occluding as a solid")
    min_length: float = Field(default=0.5, ge=0.0, le=20.0, title="Min length (mm)",
                              description="Drop fragments shorter than this — each is "
                                          "otherwise its own pen lift")
    density: float = Field(default=0.0, ge=0.0, le=1.0, title="Image density",
                           description="How strongly the image weighs the membrane. "
                                       "Dark is heavy is slow, so nodal lines bunch "
                                       "there. 0 is a uniform membrane and ignores "
                                       "the image entirely",
                           json_schema_extra=_DENSITY)
    image: str = Field(default="", title="Image (asset)",
                       description="Uploaded image asset, fitted to the layer's shapes",
                       json_schema_extra={"format": "asset", **_DENSITY})
    channel: ChannelName = Field(default="luma", title="Channel",
                                 description="Which plane weighs the membrane",
                                 json_schema_extra=_DENSITY)
    black_generation: float = Field(default=1.0, ge=0.0, le=1.0, title="Black generation",
                                    description="CMYK only: how much shared grey goes to K",
                                    json_schema_extra=_DENSITY)
    rotate: Literal[0, 90, 180, 270] = Field(default=0, title="Rotate image (°)",
                                             json_schema_extra={"viewRotate": True, **_DENSITY})
    frame: float = Field(default=0.0, ge=0.0, le=1.0, title="Frame",
                         description="Position in an image sequence; ignored for stills",
                         json_schema_extra=_DENSITY)


def _sampler(params: EigenFillParams, bounds: tuple[float, float, float, float]):
    """Node coordinates -> mass per node, or None for a uniform membrane.

    The image is fitted to `bounds` — the layer's filled geometry — rather than
    carrying its own x/y/width, so several shapes in one layer sample one
    coherent field instead of each getting a private copy of the picture.

    A missing asset returns None rather than raising: a stored project must
    still resolve when its assets have gone walkabout (docs/MODULES.md).
    """
    if params.density <= 0.0 or not params.image:
        return None
    got = sample_rows(params)
    if got is None:
        return None
    rows, iw, ih = got
    grid = np.asarray(rows, dtype=np.float64)
    minx, miny, maxx, maxy = bounds
    span_x, span_y = max(maxx - minx, 1e-6), max(maxy - miny, 1e-6)
    contrast = 1.0 + (DENSITY_CONTRAST - 1.0) * params.density

    def mass(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        # nearest-neighbour is enough: the lattice is far coarser than the
        # image, and the solve smooths anything finer than a cell anyway
        cx = np.clip(((xs - minx) / span_x * iw).astype(int), 0, iw - 1)
        cy = np.clip(((ys - miny) / span_y * ih).astype(int), 0, ih - 1)
        v = grid[cy, cx]                      # 0 = darkest, the shared polarity
        return contrast ** (1.0 - 2.0 * v)    # dark -> heavy, light -> light

    return mass


@register_effect
class EigenFill(EffectModule):
    id = "eigen_fill"
    label = "Eigenfunction fill (cymatics)"
    description = "Fill filled shapes with the nodal lines of their own vibration."
    Params = EigenFillParams

    def available(self) -> tuple[bool, str]:
        return _eigenmode.available()

    def apply(self, paths: list[Path], params: EigenFillParams,
              ctx: EffectContext) -> list[Path]:
        out: list[Path] = []
        shapes: list[Polygon] = []
        for path in paths:
            pts = path.points
            if not (path.filled and is_closed(pts)):
                out.append(path)
                continue
            if params.outline:
                out.append(path)
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                shapes.append(poly)
        if not shapes:
            return out

        # even-odd assembly, the same rule hatch_fill uses: a closed loop
        # nested inside another is a HOLE, and XOR degenerates to union for
        # disjoint shapes so plain multi-shape layers behave as expected
        region = shapes[0]
        for poly in shapes[1:]:
            region = region.symmetric_difference(poly)
        mass = _sampler(params, region.bounds)

        for sub in (region.geoms if hasattr(region, "geoms") else [region]):
            if not isinstance(sub, Polygon) or sub.is_empty:
                continue
            # The membrane is the shape itself; the inset trims the DRAWING
            # only. Solving the inset shape instead would make the inset a
            # physical parameter and re-solve on every nudge of it.
            basis = _eigenmode.basis(sub, params.detail,
                                     params.mode + params.spread, mass)
            if basis is None:
                continue
            clip = sub.buffer(-params.inset) if params.inset > 0 else sub
            if clip.is_empty:
                continue
            sand = params.field == "sand"
            field, (ox, oy) = _eigenmode.contour_field(
                basis, params.mode, params.mix, params.spread, sand)
            for level in _eigenmode.contour_levels(params.levels, params.level_bias, sand):
                for loop in trace_contours(field, level, basis.pitch):
                    cut = LineString([(x + ox, y + oy) for x, y in loop]).intersection(clip)
                    for part in getattr(cut, "geoms", [cut]):
                        if not isinstance(part, LineString) or part.is_empty:
                            continue
                        if part.length < params.min_length:
                            continue
                        out.append(Path(points=[(x, y) for x, y in part.coords],
                                        filled=False))
        return out
