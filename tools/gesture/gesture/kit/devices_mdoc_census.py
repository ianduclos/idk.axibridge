"""Device `mdoc_census` (round 16, thread D `mdoc`): where every crossing
went, and which way.

It reads the played log of a v2 sheet (every event whose outcome is one of
the shared crossing names: gap_under, gap_over, cross, stop, sympathy). On a
sheet without a log (a v1 composer, or a score with no crossing relation)
it reads the crossings off the geometry instead — a layer's line that breaks
across another layer's line passed under it, one that runs through crossed,
one whose end sits on another's line stopped — and says so on the page.
Sympathy leaves no break, so geometry can't see it; the page says that too.

Two readings, chosen by placement (like `meas_arcs`):
- map (over/under): each crossing where it happened, light. A gap gets the
  hidden stretch of the under line restored as a few dashes (the map
  convention for a line passing beneath); a through-crossing gets a small
  ring; a stop a short bar along the line it stopped at; a sympathy a small
  tilde beside the line that leaned.
- table (beside/margin): one row per pair of layers (earlier > later), the
  pair's crossings in the order the drawing made them as pictograms — two
  short strokes in the two layers' inks, the later one broken, breaking the
  other, running through, stopping, or bending — then the counts. A streak
  of one outcome reads as a run of equal pictograms.
"""
from __future__ import annotations

import math
from collections import Counter, OrderedDict

import numpy as np

from . import devices_mdoc_read as D
from . import devices_meas_read as R
from ._devices import device
from .core import P


def _perp(u):
    return np.array([-u[1], u[0]])


def _tilde(c, u, size):
    t = np.linspace(-1, 1, 13)
    n = _perp(u)
    return np.array([c + u * size * x + n * 0.28 * size * math.sin(math.pi * x) for x in t])


# ---------------------------------------------------------------------------
# pictograms (table): the later line horizontal, the earlier one steep
# ---------------------------------------------------------------------------

def pictogram(outcome: str, x: float, y: float, c: float):
    """(dst polylines, src polylines) for one crossing in a c×c cell at x, y
    (top-left). dst = the later layer (horizontal), src = the earlier
    (steep)."""
    cy = y + c / 2
    xa, xb = x, x + c
    sa, sb = np.array([x + 0.32 * c, y + c]), np.array([x + 0.68 * c, y])
    mid = np.array([x + c / 2, cy])
    g = 0.2 * c
    H = [np.array([[xa, cy], [xb, cy]])]
    S = [np.array([sa, sb])]
    u = (sb - sa) / np.linalg.norm(sb - sa)
    if outcome == "gap_under":
        H = [np.array([[xa, cy], [mid[0] - g, cy]]), np.array([[mid[0] + g, cy], [xb, cy]])]
    elif outcome == "gap_over":
        S = [np.array([sa, mid - u * g * 1.1]), np.array([mid + u * g * 1.1, sb])]
    elif outcome == "stop":
        H = [np.array([[xa, cy], [mid[0] - 0.03 * c, cy]])]
    elif outcome == "sympathy":
        t = np.linspace(0, 1, 15)
        xs = xa + t * c
        bump = np.exp(-((xs - mid[0]) / (0.16 * c)) ** 2)
        H = [np.column_stack([xs, cy - 0.2 * c * bump * np.sign(xs - mid[0])])]
    elif outcome not in ("cross",):
        H = [np.array([[xa, cy], [xb, cy]])]
        S = [R.circle(mid, 0.12 * c, 8)]
    return H, S


@device("mdoc_census", family="process", params=[
    P("style", "choice", "auto", "auto (map over/under, table beside/margin) | map | table",
      choices=("auto", "map", "table")),
    P("read", "choice", "auto", "auto (the played log, else the geometry) | log | geometry",
      choices=("auto", "log", "geometry")),
    P("outcomes", "str", "", "only these outcomes, comma-separated (empty = all)"),
    P("ring", "float", 0.75, "map: ring radius at a through-crossing, mm", min=0.2, max=4.0),
    P("cell", "float", 3.2, "table: pictogram size, mm", min=1.5, max=10.0),
    P("max_rows", "int", 14, "table: most pairs listed (the rest folded)", min=1, max=60),
    P("tally", "bool", True, "print the counts (map: one small line in the emptiest corner)"),
    P("label_h", "float", 1.5, "lettering cap height, mm", min=0.6, max=6.0),
    P("pen", "float", 0.15, "pen, mm", min=0.05, max=1.0),
    P("ink", "str", "auto", "map ink: a Flexoki name, 'auto' (an accent the drawing does not use) or 'source' (each mark in its line's ink)"),
], doc="where every crossing went and which way (under, over, through, stop, sympathy): from the played log, "
       "else read off the geometry; a map on the drawing or a table of pictograms beside it")
def mdoc_census(dctx, sheet, *, style, read, outcomes, ring, cell, max_rows, tally, label_h, pen, ink):
    recs, source = D.crossing_records(sheet, read=read)
    if outcomes:
        keep = {o.strip() for o in outcomes.split(",") if o.strip()}
        recs = [r for r in recs if r["outcome"] in keep]
    if style == "auto":
        style = "map" if dctx.place in ("over", "under") else "table"
    L = D.layers(sheet)
    ink = D.free_ink(sheet, ink) if ink != "source" else ink
    if style == "map":
        return _map(dctx, sheet, recs, source, L, ring=ring, tally=tally, label_h=label_h, pen=pen, ink=ink)
    return _table(dctx, sheet, recs, source, L, cell=cell, max_rows=max_rows, tally=tally, label_h=label_h, pen=pen)


def _src_word(source: str, n: int) -> str:
    if source == "log":
        return f"{n} CROSSINGS FROM THE PLAYED LOG"
    return f"{n} CROSSINGS READ FROM THE GEOMETRY (NO LOG - SYMPATHY UNSEEN)"


def _counts(recs) -> str:
    c = Counter(r["outcome"] for r in recs)
    return "  ".join(f"{c[o]} {D.OUT_SHORT[o]}" for o in D.CROSS_OUTCOMES if c[o])


def _map(dctx, sheet, recs, source, L, *, ring, tally, label_h, pen, ink):
    polys_by: dict[str, list] = {}

    def add(colour, ps):
        polys_by.setdefault(colour, []).extend(ps)

    line_polys = {k: [np.asarray(m.points, float) for m in v["marks"]] for k, v in L.items()}
    for r in recs:
        at = np.asarray(r["at"], float)
        o = r["outcome"]
        if o in ("gap_under", "gap_over"):
            under = r.get("under") or (r["dst"] if o == "gap_under" else r["src"])
            col = L[under]["colour"] if ink == "source" and under in L else ink
            ends = D.under_ends(sheet, r, L)
            if ends is not None:
                add(col, D.dashes(ends[0], ends[1], dash=0.45, gap=0.4))
            else:
                add(col, [R.circle(at, ring * 0.7, 10)])
        elif o == "cross":
            add(L[r["dst"]]["colour"] if ink == "source" and r["dst"] in L else ink, [R.circle(at, ring, 14)])
        elif o == "stop":
            stopper = r.get("stopper") or r["dst"]
            wall = r["src"] if stopper == r["dst"] else r["dst"]
            u = D._seg_dir(line_polys.get(wall, []), at)
            col = L[stopper]["colour"] if ink == "source" and stopper in L else ink
            if u is None:
                add(col, [R.circle(at, ring * 0.7, 10)])
                continue
            n = _perp(u)
            # the side the stopping line arrived from
            sgn = 1.0
            best = None
            for m in L.get(stopper, {}).get("marks", []):
                p = np.asarray(m.points, float)
                for e, inner in ((p[0], p[min(4, len(p) - 1)]), (p[-1], p[max(len(p) - 5, 0)])):
                    d = float(np.linalg.norm(e - at))
                    if d < 3.0 and (best is None or d < best):
                        best, sgn = d, (1.0 if float((inner - e) @ n) >= 0 else -1.0)
            c = at + sgn * n * 0.9
            add(col, [np.array([c - u * 1.1, c + u * 1.1])])
        elif o == "sympathy":
            u = D._seg_dir(line_polys.get(r["dst"], []), at)
            col = L[r["dst"]]["colour"] if ink == "source" and r["dst"] in L else ink
            if u is None:
                u = np.array([1.0, 0.0])
            add(col, [_tilde(at + _perp(u) * 1.7, u, 1.3)])
    out = []
    for col, ps in polys_by.items():
        out += R.inks(ps, pen=pen, colour=col, role="census", meta={"source": source})
    words = []
    if not recs:
        words = D.free_corner(sheet, dctx.region, "NO CROSSINGS BETWEEN LAYERS", h=label_h * 0.8)
    elif tally or source != "log":
        msg = _src_word(source, len(recs)) + (":  " + _counts(recs) if tally else "")
        words = D.free_corner(sheet, dctx.region, msg, h=label_h * 0.8)
    out += R.inks(words, pen=pen, colour="black" if ink == "source" else ink, role="census-note")
    return out


def _table(dctx, sheet, recs, source, L, *, cell, max_rows, tally, label_h, pen):
    x0, y0, w, h = dctx.region
    pad = min(3.0 + 0.04 * min(w, h), 8.0)
    x0, y0, w, h = x0 + pad, y0 + pad, w - 2 * pad, h - 2 * pad
    out = []
    head = []
    head += R.text("CROSSINGS", x0, y0, label_h)
    head += D.note((x0, y0 + 1.5 * label_h, w, 2.4 * label_h), _src_word(source, len(recs)), h=0.75 * label_h,
                   corner="tl", pad=0.0)
    if not recs:
        head += R.text("NONE BETWEEN LAYERS", x0, y0 + 4 * label_h, 0.8 * label_h)
        return R.inks(head, pen=pen, colour="black", role="census")
    pairs: "OrderedDict[tuple, list]" = OrderedDict()
    for r in recs:
        pairs.setdefault((r["src"], r["dst"]), []).append(r)
    rows = list(pairs.items())
    folded = rows[max_rows:]
    rows = rows[:max_rows]
    name_w = max(R.text_w(f"{D.layer_tag(L, s)}>{D.layer_tag(L, d)}", 0.85 * label_h)
                 for (s, d), _ in rows) + 2.0
    count_w = R.text_w("99 99 99 99 99", 0.75 * label_h) + 1.5
    gx0 = x0 + name_w
    gw = max(w - name_w - count_w, cell * 3)
    per = max(int(gw // (cell * 1.25)), 1)
    y = y0 + 4.4 * label_h
    rules = [R.rule(x0, y - 0.9 * label_h, x0 + w, y - 0.9 * label_h)]
    for (s, d), rs in rows:
        nlines = math.ceil(len(rs) / per)
        rh = nlines * cell * 1.35
        if y + rh > y0 + h - 7 * label_h:
            folded = [((s, d), rs)] + folded
            continue
        sn, dn = D.layer_tag(L, s), D.layer_tag(L, d)
        head += R.text(f"{sn}>{dn}", x0, y + cell / 2 - 0.42 * label_h, 0.85 * label_h)
        cs = L[s]["colour"] if s in L else "black"
        cd = L[d]["colour"] if d in L else "black"
        Hs, Ss = [], []
        for i, r in enumerate(rs):
            cx = gx0 + (i % per) * cell * 1.25
            cy = y + (i // per) * cell * 1.35
            h1, s1 = pictogram(r["outcome"], cx, cy, cell)
            Hs += h1
            Ss += s1
        out += R.inks(Ss, pen=pen, colour=cs, role="census-src")
        out += R.inks(Hs, pen=pen, colour=cd, role="census-dst")
        c = Counter(r["outcome"] for r in rs)
        cnt = " ".join(f"{c[o]}" if c[o] else "-" for o in D.CROSS_OUTCOMES)
        head += R.text(cnt, x0 + w, y + cell / 2 - 0.38 * label_h, 0.75 * label_h, anchor="right")
        y += rh + 0.5 * cell
    if folded:
        n = sum(len(rs) for _, rs in folded)
        head += R.text(f"+{len(folded)} PAIRS / {n} CROSSINGS NOT LISTED", x0, y, 0.75 * label_h)
        y += 2 * label_h
    # the key: one pictogram per outcome, named, with the column order of the counts
    ky = y0 + h - 4.2 * label_h
    rules.append(R.rule(x0, ky - 1.2 * label_h, x0 + w, ky - 1.2 * label_h))
    kx = x0
    kc = cell * 0.9
    tot = Counter(r["outcome"] for r in recs)
    key_lines = []
    for o in D.CROSS_OUTCOMES:
        h1, s1 = pictogram(o, kx, ky, kc)
        key_lines += h1 + s1
        lab = f"{D.OUT_SHORT[o]} {tot[o]}"
        head += R.text(lab, kx + kc + 1.0, ky + kc / 2 - 0.35 * label_h, 0.7 * label_h)
        kx += kc + 2.5 + R.text_w(lab, 0.7 * label_h)
    head += R.text("COUNTS IN ORDER: UNDER OVER THROUGH STOP SYMPATHY - THE LATER LINE ACROSS", x0, ky + kc + 1.2,
                   0.6 * label_h)
    out += R.inks(rules + head + key_lines, pen=pen, colour="black", role="census")
    return out
