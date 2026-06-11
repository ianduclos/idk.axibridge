"""Transform modules backed by vpype — since v2, the plot-pass optimisation
vocabulary (linemerge / linesort / reloop / linesimplify over resolved
geometry). Creative reshaping moved to per-layer Effects; occlusion moved to
the compositor.

Pattern: each module builds a vpype CLI pipeline string from its params and
runs it through ``vpype_cli.execute`` — the documented programmatic entry
point. This keeps each wrapper ~15 lines and means any vpype/plugin command
can be exposed the same way.
"""

from __future__ import annotations

import vpype_cli
from pydantic import BaseModel, Field

from ..model import PathDocument
from ..registry import TransformModule, register_transform
from ..svg_io import doc_from_vpype, doc_to_vpype


class VpypeTransform(TransformModule):
    """Base for vpype-backed transforms: subclass and implement ``command``."""

    def command(self, params: BaseModel) -> str:
        raise NotImplementedError

    def apply(self, doc: PathDocument, params: BaseModel) -> PathDocument:
        vdoc = doc_to_vpype(doc)
        vdoc = vpype_cli.execute(self.command(params), document=vdoc)
        out = doc_from_vpype(vdoc, source=doc.source)
        # vpype ops preserve layer structure but may drop page size on empty docs
        out.width = out.width or doc.width
        out.height = out.height or doc.height
        return out


# --- optimize ---------------------------------------------------------------


class LineMergeParams(BaseModel):
    tolerance: float = Field(default=0.5, ge=0.0, le=10.0, title="Tolerance (mm)",
                             description="Join paths whose endpoints are closer than this")
    no_flip: bool = Field(default=False, title="Don't reverse paths to merge")


@register_transform
class LineMerge(VpypeTransform):
    id = "linemerge"
    label = "Merge lines"
    description = "Join paths with nearly-coincident endpoints — fewer pen lifts."
    category = "optimize"
    Params = LineMergeParams

    def command(self, p: LineMergeParams) -> str:
        return f"linemerge --tolerance {p.tolerance}mm" + (" --no-flip" if p.no_flip else "")


class LineSortParams(BaseModel):
    no_flip: bool = Field(default=False, title="Don't reverse paths while sorting")
    two_opt: bool = Field(default=False, title="2-opt refinement (slow, better)")


@register_transform
class LineSort(VpypeTransform):
    id = "linesort"
    label = "Sort lines"
    description = "Reorder paths to minimise pen-up travel."
    category = "optimize"
    Params = LineSortParams

    def command(self, p: LineSortParams) -> str:
        cmd = "linesort"
        if p.no_flip:
            cmd += " --no-flip"
        if p.two_opt:
            cmd += " --two-opt"
        return cmd


class ReloopParams(BaseModel):
    tolerance: float = Field(default=0.1, ge=0.0, le=5.0, title="Tolerance (mm)")


@register_transform
class Reloop(VpypeTransform):
    id = "reloop"
    label = "Reloop closed paths"
    description = "Randomise the seam point of closed loops — hides pen-down/up marks."
    category = "optimize"
    Params = ReloopParams

    def command(self, p: ReloopParams) -> str:
        return f"reloop --tolerance {p.tolerance}mm"


class SimplifyParams(BaseModel):
    tolerance: float = Field(default=0.05, ge=0.001, le=2.0, title="Tolerance (mm)",
                             description="Max deviation when removing redundant points")


@register_transform
class Simplify(VpypeTransform):
    id = "linesimplify"
    label = "Simplify lines"
    description = "Drop redundant points — smaller plans, smoother planning."
    category = "optimize"
    Params = SimplifyParams

    def command(self, p: SimplifyParams) -> str:
        return f"linesimplify --tolerance {p.tolerance}mm"
