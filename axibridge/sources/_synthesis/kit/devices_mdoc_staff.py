# FROZEN from research commit c712045: tools/gesture/gesture/kit/devices_mdoc_staff.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Device `mdoc_staff` (round 16, thread D `mdoc`, its own): the score as
a score. A process only this bench has: the drawing is played, in order,
and some of what was written stays silent.

Time runs left to right, one column per step of the executor (a layer
placed and every relation that acted then). Each layer is a staff that
enters at its step and runs on to the end, named at the left in its own
ink: a solid line for a drawn layer, a double line for a sealed composer,
dashes for an unseen layer (heard, never inked). Every relation that acted
is a stem at its step from the layer it heard to the layer it acted on: a
ring where it landed (contact) or an arrowhead (grow), the number of events
beside it. A written relation whose chance didn't come up is a rest on the
staff it would have acted on; one that played and met nothing, a small
empty square. So the page shows the order, who listened to whom, how much,
and what was silent.

On a v1 sheet it reads the recorded score: layers in order, each relation
at the step of the layer it acted on; no rests (a v1 composer logs no
silence), and the header says so.
"""
from __future__ import annotations

import re
from collections import OrderedDict

import numpy as np

from . import devices_mdoc_read as D
from . import devices_meas_read as R
from ._devices import device
from ._relations import get_relation
from .core import P


def events_by_step(sheet):
    """(layers [(id, role, colour, tag, entry step)], groups, source) where a
    group = {step, relation, kind, phase, src, dst, n, state: played|silent|nothing}."""
    pl = D.played(sheet)
    L = D.layers(sheet)
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    if pl:
        lays = []
        for k, lay in enumerate(pl["layers"]):
            lid = lay["id"]
            colour = L[lid]["colour"] if lid in L else (lay.get("pen") or "black")
            lays.append({"id": lid, "role": lay.get("role", ""), "colour": colour, "tag": D.layer_tag(L, lid)
                         if lid in L else f"{k + 1} {lid}", "step": k, "sealed": bool(lay.get("inner")) or
                         lay.get("technique") not in ("hand", "lines") and lay.get("role") == "sealed"})
        pos = {x["id"]: x["step"] for x in lays}
        for e in pl["log"]:
            key = (e.get("step"), e["relation"], e["src"], e["dst"])
            try:
                phase = get_relation(e["kind"]).phase
            except Exception:  # noqa: BLE001
                phase = "contact"
            g = groups.setdefault(key, {"step": e.get("step", pos.get(e["dst"], 0)), "relation": e["relation"],
                                        "kind": e["kind"], "phase": phase, "src": e["src"], "dst": e["dst"], "n": 0,
                                        "state": "played"})
            if e["outcome"] == "silent":
                g["state"] = "silent"
            else:
                g["n"] += 1
        heard = {g["relation"] for g in groups.values()}
        for r in (pl.get("written") or {}).get("relations", []):
            if r["id"] in heard:
                continue
            dst = r["dst"] if r["dst"] != "*" else (lays[-1]["id"] if lays else None)
            if dst is None:
                continue
            try:
                phase = get_relation(r["kind"]).phase
            except Exception:  # noqa: BLE001
                phase = "contact"
            step = max(pos.get(r["dst"], 0), pos.get(r["src"], 0)) if r["src"] != "*" and r["dst"] != "*" else \
                pos.get(dst, 0)
            groups[(step, r["id"], r["src"], dst)] = {"step": step, "relation": r["id"], "kind": r["kind"],
                                                      "phase": phase, "src": r["src"], "dst": dst, "n": 0,
                                                      "state": "nothing"}
        return lays, sorted(groups.values(), key=lambda g: (g["step"], g["relation"])), "log"
    sc = R.process_score(sheet)
    if not sc or not sc.get("layers"):
        return [], [], ""
    lays = []
    for k, lay in enumerate(sc["layers"]):
        lid = lay["id"]
        colour = L[lid]["colour"] if lid in L else "black"
        lays.append({"id": lid, "role": lay.get("role", ""), "colour": colour,
                     "tag": D.layer_tag(L, lid) if lid in L else f"{k + 1} {lid}", "step": k, "sealed": False})
    pos = {x["id"]: x["step"] for x in lays}
    for r in sc.get("relations", []):
        if r.get("src") not in pos or r.get("dst") not in pos:
            continue
        step = max(pos[r["src"]], pos[r["dst"]])
        key = (step, r["kind"], r["src"], r["dst"])
        g = groups.setdefault(key, {"step": step, "relation": "-", "kind": r["kind"], "phase": "contact",
                                    "src": r["src"], "dst": r["dst"], "n": 0, "state": "played"})
        m = re.match(r"\s*(\d+)\s+(event|crossing)", str(r.get("note", "")))
        g["n"] += int(m.group(1)) if m else 1
    return lays, sorted(groups.values(), key=lambda g: g["step"]), "score"


@device("mdoc_staff", family="process", params=[
    P("label_h", "float", 1.4, "lettering cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.16, "pen, mm", min=0.05, max=1.0),
    P("ink", "str", "black", "ink for staves' frame, stems and lettering (staves and heads take their layer's ink)"),
    P("kinds", "bool", True, "name each stem's relation kind (small, under the step)"),
], doc="the score as a score: one staff per layer entering at its step, a stem per relation that acted (who "
       "heard whom, how many events), rests for what stayed silent")
def mdoc_staff(dctx, sheet, *, label_h, pen, ink, kinds):
    x0, y0, w, h = dctx.region
    pad = min(3.0 + 0.04 * min(w, h), 8.0)
    x0, y0, w, h = x0 + pad, y0 + pad, w - 2 * pad, h - 2 * pad
    lays, groups, source = events_by_step(sheet)
    th = label_h
    title = {"log": "THE SCORE AS PLAYED", "score": "THE SCORE AS RECORDED (NO LOG - NO SILENCES KNOWN)",
             "": "NO SCORE ON THIS SHEET"}[source]
    black = R.text(title, x0, y0, th)
    if not lays:
        return R.inks(black, pen=pen, colour=ink, role="staff")
    nL = len(lays)
    names_w = max(R.text_w(x["tag"], 0.8 * th) for x in lays) + 2.5
    top = y0 + 4.4 * th
    bot = y0 + h - (2.8 * th if kinds else 0.8 * th)
    rowh = (bot - top) / nL
    ys = {x["id"]: top + (i + 0.5) * rowh for i, x in enumerate(lays)}
    nsteps = nL
    per = [0] * nsteps
    for g in groups:
        per[min(max(int(g["step"]), 0), nsteps - 1)] += 1
    unit = [1.0 + c for c in per]
    span = w - names_w
    tot = sum(unit)
    xs, acc = [], x0 + names_w
    for u in unit:
        xs.append((acc, acc + span * u / tot))
        acc += span * u / tot
    xr = x0 + w
    coloured: list[tuple] = []
    for i, x in enumerate(lays):
        y = ys[x["id"]]
        a = xs[x["step"]][0] + 0.4 * (xs[x["step"]][1] - xs[x["step"]][0]) / unit[x["step"]]
        coloured.append((R.text(x["tag"], x0, y - 0.4 * th, 0.8 * th), x["colour"]))
        if x["role"] == "unseen":
            coloured.append((D.dashes((a, y), (xr, y), dash=0.8, gap=0.8), x["colour"]))
        elif x["sealed"]:
            coloured.append(([np.array([[a, y - 0.35], [xr, y - 0.35]]), np.array([[a, y + 0.35], [xr, y + 0.35]])],
                             x["colour"]))
        else:
            coloured.append(([np.array([[a, y], [xr, y]])], x["colour"]))
        black.append(np.array([[a, y - 0.9], [a, y + 0.9]]))           # the entry
    for k in range(nsteps):
        black += R.text(str(k + 1), xs[k][0] + 0.4 * (xs[k][1] - xs[k][0]) / unit[k], top - 1.8 * th, 0.7 * th,
                        anchor="centre")
    slot = {k: 0 for k in range(nsteps)}
    col_of = {x["id"]: x["colour"] for x in lays}
    for g in groups:
        k = min(max(int(g["step"]), 0), nsteps - 1)
        slot[k] += 1
        cx = xs[k][0] + (slot[k] + 0.4) * (xs[k][1] - xs[k][0]) / unit[k]
        yd = ys.get(g["dst"])
        if yd is None:
            continue
        if g["src"] == "*":
            ys_src = min((ys[x["id"]] for x in lays if x["step"] < k and x["role"] != "unseen"), default=yd)
        else:
            ys_src = ys.get(g["src"], yd)
        cd = col_of.get(g["dst"], "black")
        if g["state"] == "silent":
            z = np.array([[cx - 0.6, yd - 1.4], [cx + 0.5, yd - 0.6], [cx - 0.5, yd + 0.2], [cx + 0.6, yd + 1.0]])
            black.append(z)
        elif g["state"] == "nothing":
            black.append(np.array([[cx - 0.5, yd - 0.5], [cx + 0.5, yd - 0.5], [cx + 0.5, yd + 0.5],
                                   [cx - 0.5, yd + 0.5], [cx - 0.5, yd - 0.5]]))
        else:
            sgn = 1.0 if ys_src < yd else -1.0
            r = 0.55
            if abs(ys_src - yd) > 1e-6:
                black.append(np.array([[cx, ys_src], [cx, yd - sgn * r]]))
                black.append(np.array([[cx - 0.35, ys_src], [cx + 0.35, ys_src]]))     # where it heard
            if g["phase"] == "grow":
                coloured.append(([np.array([[cx - 0.6, yd - sgn * 1.1], [cx, yd], [cx + 0.6, yd - sgn * 1.1]])], cd))
            else:
                coloured.append(([R.circle((cx, yd), r, 10)], cd))
            if g["n"] > 1:
                black += R.text(str(g["n"]), cx + 0.9, yd + (0.3 if sgn > 0 else -1.0) * th, 0.6 * th)
        if kinds:
            black += R.text(str(g["kind"]).replace("mdoc_", "")[:8].upper(), cx, bot + 0.5 * th + (slot[k] % 2) * 1.1 * th, 0.6 * th,
                            anchor="centre")
    black.append(R.rule(x0 + names_w, top - 0.6 * th, xr, top - 0.6 * th))
    out = R.inks(black, pen=pen, colour=ink, role="staff")
    for ps, c in coloured:
        out += R.inks(ps, pen=pen, colour=c, role="staff-layer")
    return out
