# FROZEN from research commit c712045: tools/gesture/gesture/kit/renderers_arch.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Round 15 thread C `arch`: one renderer for a composed sheet whose marks need different inks.

`arch_ink` inks each mark the way its meta says (`draw`): `wire` (one polyline at meta['pen']),
`nib` (the kit's `nib` renderer on the mark's r / phi / W / M channels; style meta['nib_style'],
default e) or `swell` (the round-11 swell renderer with meta['swell'] over the defaults). Every
ink carries the mark's pen colour in Ink.meta['colour'] (a Flexoki name, as `oehlen_found_ink`),
so `arrangers_ccolour.render_pens` previews it in pens. Only renders: no geometry is decided here.
"""
from __future__ import annotations

from .core import Ink, P, get, renderer


@renderer("arch_ink", params=[
    P("pen", "float", 0.4, "pen for marks that carry none, mm", min=0.05, max=3.0),
    P("nib_style", "choice", "e", "nib style for marks drawn as nib (unless the mark names one)",
      choices=("a", "b", "b+", "c", "e", "c+e")),
    P("swell_line", "choice", "wire", "marks drawn as swell: the line runs through the swell (wire) | stops at "
      "its outline (outside: no line through the middle; Ian, 2026-10-19)", choices=("wire", "outside")),
], doc="per mark: wire | nib | swell (meta['draw']), each in its pen colour (meta['ink'])", reach=lambda p: 0.5)
def arch_ink(ctx, marks, *, pen, nib_style, swell_line):
    from .renderers_base import nib  # noqa: PLC0415
    from .swell_ink import swell  # noqa: PLC0415
    sw = get("renderer", "swell")
    out = []
    for m in marks:
        if len(m) < 2:
            continue
        colour = m.meta.get("ink", "black")
        p = float(m.meta.get("pen", pen))
        how = m.meta.get("draw", "wire")
        role = m.meta.get("of_role")
        if how == "nib":
            inks = nib(ctx, [m], style=m.meta.get("nib_style", nib_style), pen=p)
        elif how == "swell":
            prm = sw.validate({"id": "swell", **m.meta.get("swell", {}),
                               **({"line": "outside"} if swell_line == "outside" else {})})
            prm.pop("id")
            inks = swell(ctx, [m], **prm)
        else:
            inks = [Ink(m.points, closed=False, filled=False, pen=p)]
        out += [Ink(k.points, closed=k.closed, filled=k.filled, pen=k.pen,
                    meta={**k.meta, "colour": colour, "role": role}) for k in inks]
    return out
