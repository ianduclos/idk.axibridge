"""Renderer for thread D's test drawings (round 15, `meas`): one wire per
mark at one pen, in one named Flexoki ink (Ink.meta["colour"] = the name,
as ccolour's `render_pens` reads it). Constant width by design."""
from __future__ import annotations

from .core import Ink, P, renderer


@renderer("meas_ink", params=[
    P("pen", "float", 0.3, "pen width, mm", min=0.05, max=3.0),
    P("ink", "str", "black", "Flexoki ink name (black, blue, cyan, orange, red, …)"),
], doc="one wire per mark, one pen, one named ink", reach=lambda p: 0.5 * p["pen"])
def meas_ink(ctx, marks, *, pen, ink):
    return [Ink(m.points, closed=False, filled=False, pen=pen, meta={"colour": str(ink)})
            for m in marks if len(m) >= 2]
