# FROZEN from research commit a66c6a5: tools/gesture/gesture/kit/devices_mdoc_ledger.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Device `mdoc_ledger` (round 16, thread D `mdoc`): the relation ledger,
the round-15 ledger's sibling. Where `meas_ledger` keeps the books of what
each step drew, this one keeps the books of who heard whom: the played log
of a v2 score, one row per relation and pair of layers, in the order the
executor played them.

Columns: the row number; the relation's id and kind; who heard whom (the
layer that acted > the layer it acted on, each with its place in the drawing
order); how (the outcomes, most first); how often; the step it played at;
and where — a thumbnail of the sheet's frame with a point at every event.
A relation that was written but whose `p` didn't fire gets a SILENT row; one
that played but met nothing (no crossing, no gesture to hear) a NOTHING row:
silence is part of the score.

On a v1 sheet (no log) it reads the relations the composer recorded, one
row each, and says so in the header. The rules can be drawn by a hand with
the frame and the lettering kept straight (Ian, round 11).
"""
from __future__ import annotations

import re
from collections import Counter, OrderedDict

import numpy as np

from . import devices_mdoc_read as D
from . import devices_meas_read as R
from . import voices_machine_diagram as vd
from ._devices import device
from .core import P

HEAD = ("NO", "REL", "KIND", "WHO HEARD WHOM", "HOW", "N", "STEP", "WHERE")
COLX = (0.0, 0.045, 0.11, 0.24, 0.50, 0.70, 0.76, 0.82)


def rows_of(sheet) -> tuple[list[dict], str]:
    """The ledger's rows and where they came from ("log" | "score" | "")."""
    pl = D.played(sheet)
    if pl:
        agg: "OrderedDict[tuple, dict]" = OrderedDict()
        for e in pl["log"]:
            key = (e["relation"], e["src"], e["dst"])
            r = agg.setdefault(key, {"relation": e["relation"], "kind": e["kind"], "src": e["src"], "dst": e["dst"],
                                     "step": e.get("step"), "outcomes": Counter(), "at": []})
            r["outcomes"][e["outcome"]] += 1
            if e.get("at"):
                r["at"].append(e["at"])
        rows = list(agg.values())
        heard = {r["relation"] for r in rows}
        for R_ in (pl.get("written") or {}).get("relations", []):
            if R_["id"] not in heard:
                rows.append({"relation": R_["id"], "kind": R_["kind"], "src": R_["src"], "dst": R_["dst"],
                             "step": None, "outcomes": Counter({"nothing": 1}), "at": []})
        return rows, "log"
    sc = R.process_score(sheet)
    if sc and sc.get("relations"):
        rows = []
        for r in sc["relations"]:
            m = re.match(r"\s*(\d+)\s+(event|crossing)", str(r.get("note", "")))
            n = int(m.group(1)) if m else 1
            rows.append({"relation": "-", "kind": r["kind"], "src": r["src"], "dst": r["dst"], "step": None,
                         "outcomes": Counter({r["kind"]: n}), "at": [r["at"]] if r.get("at") else [],
                         "how": str(r.get("note") or "")})
        return rows, "score"
    return [], ""


def _words(text: str, nchar: int) -> str:
    """The text cut at a word boundary to at most nchar characters."""
    out = ""
    for wd in str(text).split():
        if len((out + " " + wd).strip()) > nchar:
            break
        out = (out + " " + wd).strip()
    return out or str(text)[:nchar]


def _how(outcomes: Counter, nchar: int) -> str:
    if set(outcomes) == {"silent"}:
        return "SILENT"
    if set(outcomes) == {"nothing"}:
        return "NOTHING MET"
    parts = [f"{v} {D.OUT_SHORT.get(k, k).upper()}" for k, v in sorted(outcomes.items(), key=lambda t: (-t[1], t[0]))]
    s = ""
    for i, p in enumerate(parts):
        nxt = (s + " " + p).strip()
        room = nchar - (2 if i < len(parts) - 1 else 0)          # leave room for the " +"
        if len(nxt) > room:
            return (s + " +").strip() if s else p[:nchar]
        s = nxt
    return s


@device("mdoc_ledger", family="process", params=[
    P("max_rows", "int", 24, "most rows (later ones folded into a last 'more' row)", min=3, max=80),
    P("drawn_by", "str", "matisse", "hand that draws the inner rules ('' = machine-straight)"),
    P("straight", "choice", "frame+text", "with drawn_by: which lines stay straight", choices=vd.STRAIGHT),
    P("amount", "float", 0.6, "with drawn_by: how much fine turning the hand owns", min=0.0, max=3.0),
    P("label_h", "float", 1.6, "lettering cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.18, "pen, mm", min=0.05, max=1.5),
    P("ink", "str", "black", "ink for the table"),
    P("dots", "str", "source", "ink for the WHERE points: a Flexoki name or 'source' (the heard layer's ink)"),
], doc="the played log as a document: who heard whom, how, how often, when and where — silence included")
def mdoc_ledger(dctx, sheet, *, max_rows, drawn_by, straight, amount, label_h, pen, ink, dots):
    rows, source = rows_of(sheet)
    x0, y0, w, h = dctx.region
    pad = min(3.0 + 0.04 * min(w, h), 8.0)
    x0, y0, w, h = x0 + pad, y0 + pad, w - 2 * pad, h - 2 * pad
    if not rows:
        return R.inks(R.text("RELATIONS", x0, y0, label_h) +
                      R.text("NO SCORE ON THIS SHEET - NOTHING TO LEDGER", x0, y0 + 2 * label_h, 0.7 * label_h),
                      pen=pen, colour=ink, role="ledger")
    L = D.layers(sheet)
    more = rows[max_rows - 1:] if len(rows) > max_rows else None
    if more:
        rows = rows[:max_rows - 1]
    nrow = len(rows) + (1 if more else 0)
    rh = min(h / (nrow + 3.2), 4.2 * label_h)
    th = min(label_h, 0.42 * rh)
    letters, rules, dot_polys, maps = [], [], [], []
    title = {"log": "RELATIONS AS PLAYED", "score": "RELATIONS AS THE COMPOSER RECORDED THEM (NO LOG)"}[source]
    letters += R.text(title, x0, y0, th)
    yh0 = y0 + 1.7 * th
    for j, t in enumerate(HEAD):
        letters += R.text(t, x0 + COLX[j] * w, yh0, 0.8 * th)
    yh = yh0 + 1.6 * th
    rules.append(R.rule(x0, yh, x0 + w, yh))
    frame = (sheet.meta.get("recipe") or {}).get("frame") or list(sheet.frame)
    FW, FH = float(frame[0]), float(frame[1])
    how_chars = int(((COLX[5] - COLX[4]) * w - 2.5) / (0.75 * th))
    who_chars = int(((COLX[4] - COLX[3]) * w - 1.0) / (0.75 * th))
    for i, r in enumerate(rows + ([None] if more else [])):
        yt = yh + 0.5 * th + i * rh
        if r is None:
            n = sum(sum(x["outcomes"].values()) for x in more)
            letters += R.text(f"{i + 1:02d}", x0, yt, th)
            letters += R.text(f"+{len(more)} MORE ROWS / {n} EVENTS", x0 + COLX[1] * w, yt, th)
            continue
        n = sum(v for k, v in r["outcomes"].items() if k not in ("silent", "nothing"))
        who = f"{D.layer_tag(L, r['src'])}>{D.layer_tag(L, r['dst'])}" if r["src"] != "*" else \
            f"ALL>{D.layer_tag(L, r['dst'])}"
        cells = (f"{i + 1:02d}", str(r["relation"])[:4], str(r["kind"])[:9], who[:who_chars],
                 (_words(r["how"], how_chars) if r.get("how") else _how(r["outcomes"], how_chars)), str(n) if n else "-",
                 "-" if r["step"] is None else str(int(r["step"]) + 1))
        for j, c in enumerate(cells):
            letters += R.text(c.upper(), x0 + COLX[j] * w, yt, th)
        # where: the frame in miniature, a point per event
        mh = min(rh * 0.82, 0.18 * w * FH / FW)
        mw = mh * FW / FH
        mx, my = x0 + COLX[7] * w, yt - 0.15 * rh + 0.1 * th
        maps.append(np.array([[mx, my], [mx + mw, my], [mx + mw, my + mh], [mx, my + mh], [mx, my]]))
        col = (L[r["dst"]]["colour"] if r["dst"] in L else "black") if dots == "source" else dots
        for a in r["at"]:
            px, py = mx + a[0] / FW * mw, my + a[1] / FH * mh
            dot_polys.append((R.circle((px, py), max(0.2, 0.015 * mw), 6), col))
        if i < nrow - 1:
            yr = yt + rh - 0.45 * th
            rules.append(R.rule(x0 + COLX[1] * w, yr, x0 + (COLX[7] - 0.015) * w, yr))
    yb = yh + 0.5 * th + nrow * rh - 0.2 * th
    rules.append(R.rule(x0, yb, x0 + w, yb))
    polys = rules + letters
    if drawn_by:
        from . import library  # noqa: PLC0415
        g = library.load("hand", drawn_by)
        flags = vd.straight_flags(polys, th, straight, 0.0, dctx.rng("straight"))
        polys = vd.hand_drawn(polys, g, dctx.rng("drawn_by", drawn_by), amount=amount, keep=0.006, straight=flags)
    out = R.inks(polys + maps, pen=pen, colour=ink, role="ledger")
    for p, c in dot_polys:
        out += R.inks([p], pen=pen, colour=c, role="where")
    return out
