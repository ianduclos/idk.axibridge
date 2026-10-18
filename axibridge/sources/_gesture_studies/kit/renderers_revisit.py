# FROZEN from research commit efce219: tools/gesture/gesture/kit/renderers_revisit.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Signs grown from the line, at events written by `revisit_notate`
(round 12, thread `revisit`). The round-7 operators (`gesture/signs.py`
`apply_events`: knots, commas, combs, bodies, hooks, vessels …) turn the
part of the line where the event happened into the sign; `render_events`
inks each mark (a line, its children and every line it shares a junction
with) as one unioned outline. Marks without events are drawn as wire.
"""
from __future__ import annotations

import math

import numpy as np

from ._research import signs as sg
from .core import Ink, P, renderer
from .modulators_revisit import END_OPS


def line_events(marks) -> list:
    """The `revisit_events` of every mark as round-7 LineEvents (mm)."""
    out = []
    for k, m in enumerate(marks):
        L = float(m.length())
        for e in m.meta.get("revisit_events", []):
            op = e["op"]
            if op in END_OPS:
                out.append(sg.LineEvent("end", op, k, L, e["size"], side=e.get("side", 1.0), end=1))
            elif e.get("other") is not None and op in ("body", "junction_mass"):
                out.append(sg.LineEvent("junction", op, k, e["s"], e["size"], side=e.get("side", 1.0),
                                        other=(int(e["other"][0]), float(e["other"][1]))))
            elif op == "comma":
                out.append(sg.LineEvent("corner", op, k, e["s"], e["size"], side=e.get("side", 1.0)))
            else:
                out.append(sg.LineEvent("interior", op, k, e["s"], e["size"], side=e.get("side", 1.0)))
    return out


def _reach(p: dict) -> float:
    return 3.0 + p["pen"]


@renderer("revisit_signs", params=[
    P("pen", "float", 0.35, "pen, mm (also the line width signs are measured in)", min=0.05, max=3.0),
    P("nib_deg", "float", 55.0, "nib angle of the swellings, degrees", min=-90.0, max=90.0),
    P("nib_mm", "float", 1.2, "nib width of the swellings, mm (null = drawn per line from the round-7 ratio)",
      min=0.1, max=12.0, optional=True),
    P("inks", "str", "black", "one Flexoki ink per mark (by the mark a sign group grows from), cycled"),
], doc="signs grown from the line at the written events (round-7 operators), one outline per mark", reach=_reach)
def revisit_signs(ctx, marks, *, pen, nib_deg, nib_mm, inks):
    marks = list(marks)
    lines = [np.asarray(m.points, float) for m in marks]
    if not lines:
        return []
    rng = ctx.rng("signs")
    evs = line_events(marks)
    for e in evs:                        # side: drawn per event, deterministically
        e.side = 1.0 if rng.random() < 0.5 else -1.0
    strokes = sg.apply_events(lines, evs, rng, w=pen, phi=math.radians(nib_deg), W=nib_mm)
    names = _inks(inks)
    groups: dict = {}
    for st in strokes:
        groups.setdefault(int(st.meta.get("mark", 0)), []).append(st)
    out = []
    for g in sorted(groups):
        name = names[g % len(names)]
        meta = {"colour": FLEXOKI[name], "ink": name, "mark": g}
        for p in sg.render_events(groups[g], pen=pen):
            p = np.asarray(p, float)
            if len(p) < 2:
                continue
            closed = bool(len(p) > 2 and np.allclose(p[0], p[-1]))
            out.append(Ink(p, closed=closed, filled=False, pen=pen, meta=meta))
    return out


FLEXOKI = {"black": "#100F0F", "red": "#AF3029", "orange": "#BC5215", "yellow": "#AD8301",
           "green": "#66800B", "cyan": "#24837B", "blue": "#205EA6", "purple": "#5E409D",
           "magenta": "#A02F6F"}           # Flexoki 600 accents (same values as dev_chorus.FLEXOKI)


def _inks(s: str) -> list[str]:
    names = [x.strip() for x in s.split(",") if x.strip()] or ["black"]
    bad = [x for x in names if x not in FLEXOKI]
    if bad:
        raise ValueError(f"revisit_nib: unknown ink(s) {bad}; choose from {sorted(FLEXOKI)}")
    return names


@renderer("revisit_nib", params=[
    P("style", "choice", "c+e", "nib style (as the `nib` renderer)", choices=("a", "b", "b+", "c", "e", "c+e", "b++c+e")),
    P("pen", "float", 0.35, "pen width mm", min=0.05, max=3.0),
    P("inks", "str", "black", "one Flexoki ink per mark, in mark order (cycled): one pen per host line"),
], doc="the nib renderer, one ink (pen colour) per mark: Ink.meta['colour']", reach=lambda p: 0.5 * p["pen"])
def revisit_nib(ctx, marks, *, style, pen, inks):
    from .renderers_base import nib
    names = _inks(inks)
    out = []
    for k, m in enumerate(marks):
        name = names[k % len(names)]
        for ink in nib(ctx, [m], style=style, pen=pen):
            out.append(Ink(ink.points, closed=ink.closed, filled=ink.filled, pen=ink.pen,
                           meta={**ink.meta, "colour": FLEXOKI[name], "ink": name, "mark": k}))
    return out
