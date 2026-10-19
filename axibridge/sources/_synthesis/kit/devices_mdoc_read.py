# FROZEN from research commit a66c6a5: tools/gesture/gesture/kit/devices_mdoc_read.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 16 thread D (`mdoc`): the shared reader for the process documents.
It registers no device; the `devices_mdoc_*.py` files do.

What these documents read, and only this:
- the played score of a v2 sheet (`_synth.played`): layers, relations, the
  full event `log` (relation, kind, src, dst, step, outcome, at, s, …) and
  the `written` score, which `_synth.run` accepts, so a document may replay
  the score with a relation taken out (a counterfactual: what the line would
  have been without it). Replays go through the public executor only;
- on a v1 sheet, the score its composer recorded (`notes["score"]`) and the
  geometry itself (where a layer's line breaks across another layer's line).

Every reading says where it came from (`source`: "log" | "geometry" |
"score"), so a document can print it, small, on the page.
"""
from __future__ import annotations

import copy
import math
from collections import Counter, OrderedDict

import numpy as np

from . import devices_meas_read as R
from ._relations import _seg_hits, crossings

CROSS_OUTCOMES = ("gap_under", "gap_over", "cross", "stop", "sympathy")
OUT_SHORT = {"gap_under": "UNDER", "gap_over": "OVER", "cross": "THROUGH", "stop": "STOP", "sympathy": "SYMPATHY"}
NAMED_INKS = ("black", "red", "orange", "yellow", "green", "cyan", "blue", "purple", "magenta")


# ---------------------------------------------------------------------------
# the played score
# ---------------------------------------------------------------------------

def played(sheet) -> dict | None:
    """The v2 played score (with its event log), or None."""
    sc = (sheet.meta.get("notes") or {}).get("score")
    if isinstance(sc, dict) and sc.get("version") == 2 and isinstance(sc.get("log"), list):
        return sc
    return None


def any_score(sheet) -> dict | None:
    """The v2 played score, else a v1 recorded/derived score."""
    return played(sheet) or R.process_score(sheet)


def written(sheet) -> dict | None:
    pl = played(sheet)
    return copy.deepcopy(pl.get("written")) if pl and pl.get("written") else None


def replay(sheet, *, drop: set[str] | frozenset = frozenset(), keep_only_kinds=None):
    """The sheet's score played again with the relations in `drop` (relation ids) taken out — or,
    with `keep_only_kinds`, only relations of those kinds kept. No devices. None when the sheet has
    no written v2 score. (Now `_synth.replay`, S0′.)"""
    from . import _synth  # noqa: PLC0415
    return _synth.replay(sheet, drop=drop, keep_only_kinds=keep_only_kinds)


# ---------------------------------------------------------------------------
# layers: which marks belong to which layer, in drawing order
# ---------------------------------------------------------------------------

def mark_layer(m) -> str:
    md = m.meta
    for k in ("score_layer", "layer"):
        v = md.get(k)
        if v and v != "device":
            return str(v)
    if "obj" in md:
        o = md["obj"]
        return ":".join(str(x) for x in (o if isinstance(o, (list, tuple)) else [o]))
    return f"P{int(md.get('part', 0) or 0)}"


def mark_colour(m) -> str:
    for k in ("ink", "colour"):
        v = m.meta.get(k)
        if isinstance(v, str) and v and not v.startswith("#"):
            return v
    return "black"


def visible_marks(sheet) -> list:
    return [m for m in R.drawing_marks(sheet) if m.meta.get("of_role") != "unseen"]


def layers(sheet) -> "OrderedDict[str, dict]":
    """Layer id → {marks, colour, label, technique, role, index} in drawing
    order (the played score's order when there is one)."""
    sc = any_score(sheet)
    order: list[str] = []
    info: dict[str, dict] = {}
    if sc:
        for lay in sc.get("layers", []):
            order.append(str(lay["id"]))
            info[str(lay["id"])] = dict(lay)
    groups: dict[str, list] = {}
    for m in visible_marks(sheet):
        lid = mark_layer(m)
        groups.setdefault(lid, []).append(m)
    if order and not any(lid in groups for lid in order):
        order, info = [], {}            # a score whose layers name no mark (arch): the marks' own groups
    for lid in groups:
        if lid not in order:
            order.append(lid)
    out: "OrderedDict[str, dict]" = OrderedDict()
    for i, lid in enumerate(order):
        ms = groups.get(lid, [])
        lay = info.get(lid, {})
        cols = Counter()
        for m in ms:
            cols[mark_colour(m)] += m.length()
        colour = cols.most_common(1)[0][0] if cols else (lay.get("pen") if isinstance(lay.get("pen"), str) else
                                                         ((lay.get("pen") or {}).get("ink") if isinstance(lay.get("pen"), dict) else None)) or "black"
        out[lid] = {"id": lid, "marks": ms, "colour": colour, "index": i, "role": str(lay.get("role") or ""),
                    "technique": str(lay.get("technique") or ""), "label": layer_name(lid, lay, ms),
                    "visible": bool(ms) and lay.get("role") != "unseen", "score": lay}
    return out


def layer_name(lid: str, lay: dict, marks=()) -> str:
    """A short name: the layer's hand when it has one, else its technique/role."""
    p = lay.get("params") or {}
    for k in ("hand", "trail", "stems"):
        if p.get(k):
            return R.short(p[k], 7)
    v = p.get("voice") or {}
    if isinstance(v, dict) and v.get("hand"):
        return R.short(v["hand"], 7)
    for m in marks:
        vs = m.meta.get("voices")
        if vs:
            return R.short(vs[0], 7)
    if ":" in lid and not lay:                     # an arranger object (ccolour / arch): found:machine, made:1
        a, b = lid.split(":", 1)
        return (b if a == "found" else a + ("" if b == "0" else b)).replace("_", "")[:8].upper()
    t = lay.get("technique") or ""
    if t and t not in ("hand", "none"):
        return str(t).split(".")[-1][:7].upper()
    if lay.get("role"):
        return str(lay["role"])[:7].upper()
    return lid[:7].upper()


# ---------------------------------------------------------------------------
# crossings: from the log, or from the geometry
# ---------------------------------------------------------------------------

def _seg_dir(polys, at) -> np.ndarray | None:
    """Unit direction of the polyline segment nearest to `at`."""
    best, out = np.inf, None
    for q in polys:
        q = np.asarray(q, float)
        if len(q) < 2:
            continue
        a, b = q[:-1], q[1:]
        ab = b - a
        L2 = np.maximum((ab ** 2).sum(1), 1e-12)
        t = np.clip(((at - a) * ab).sum(1) / L2, 0, 1)
        d = np.linalg.norm(a + t[:, None] * ab - at, axis=1)
        j = int(d.argmin())
        if d[j] < best:
            best = d[j]
            out = ab[j] / math.sqrt(L2[j])
    return out


def _dist_to(polys, p) -> float:
    best = np.inf
    for q in polys:
        q = np.asarray(q, float)
        if len(q) < 2:
            continue
        a, b = q[:-1], q[1:]
        ab = b - a
        L2 = np.maximum((ab ** 2).sum(1), 1e-12)
        t = np.clip(((p - a) * ab).sum(1) / L2, 0, 1)
        best = min(best, float(np.linalg.norm(a + t[:, None] * ab - p, axis=1).min()))
    return best


def crossing_records(sheet, *, read: str = "auto", gap_max: float = 6.0, stop_tol: float = 0.9):
    """Every crossing between two layers and which way it went, in the
    order the drawing made them. Returns (records, source). A record:
    {outcome, at (np), src, dst, relation, kind, step}; src is the earlier
    layer of the pair, dst the later one (the executor's pairing).
    read: auto (the log when it holds crossing outcomes, else geometry) |
    log | geometry."""
    pl = played(sheet)
    recs = []
    if read in ("auto", "log") and pl:
        for e in pl["log"]:
            if e.get("outcome") in CROSS_OUTCOMES and e.get("at"):
                recs.append({"outcome": e["outcome"], "at": np.asarray(e["at"], float), "src": e["src"],
                             "dst": e["dst"], "relation": e.get("relation"), "kind": e.get("kind"),
                             "step": e.get("step"), "s": e.get("s"), "max_mm": e.get("max_mm")})
        if recs or read == "log":
            return recs, "log"
    return _geometry_census(sheet, gap_max=gap_max, stop_tol=stop_tol), "geometry"


def _geometry_census(sheet, *, gap_max: float, stop_tol: float) -> list[dict]:
    """Read the crossings off the geometry: a layer's line that breaks
    across another layer's line passed under it; one that runs through
    crossed; one whose end sits on another layer's line stopped there.
    Sympathy can't be read from geometry (it leaves no break)."""
    L = layers(sheet)
    ids = [k for k, v in L.items() if v["visible"]]
    pos = {k: i for i, k in enumerate(ids)}
    recs: list[dict] = []
    used_ends: set[tuple] = set()
    polys = {k: [np.asarray(m.points, float) for m in L[k]["marks"]] for k in ids}
    for X in ids:
        ms = L[X]["marks"]
        ends = []
        for i, m in enumerate(ms):
            p = np.asarray(m.points, float)
            if len(p) < 2:
                continue
            t0 = p[0] - p[min(3, len(p) - 1)]
            t1 = p[-1] - p[max(len(p) - 4, 0)]
            ends.append((i, 0, p[0], t0 / (np.linalg.norm(t0) + 1e-12)))
            ends.append((i, 1, p[-1], t1 / (np.linalg.norm(t1) + 1e-12)))
        cand = []
        for a in range(len(ends)):
            for b in range(a + 1, len(ends)):
                ia, fa, pa, ta = ends[a]
                ib, fb, pb, tb = ends[b]
                if ia == ib:
                    continue
                d = float(np.linalg.norm(pb - pa))
                if not 0.05 < d <= gap_max:
                    continue
                u = (pb - pa) / d
                if float(ta @ u) < 0.0 or float(tb @ -u) < 0.0:      # each end heads toward the other
                    continue
                cand.append((d, a, b))
        cand.sort()
        taken: set[int] = set()
        for d, a, b in cand:
            if a in taken or b in taken:
                continue
            pa, pb = ends[a][2], ends[b][2]
            chord = np.array([pa, pb])
            hit = None
            for Y in ids:
                if Y == X:
                    continue
                for q in polys[Y]:
                    hs = _seg_hits(chord, q)
                    if hs:
                        ip, tp, _, _ = hs[0]
                        hit = (Y, pa + tp * (pb - pa))
                        break
                if hit:
                    break
            if not hit:
                continue
            taken |= {a, b}
            used_ends |= {(X, ends[a][0], ends[a][1]), (X, ends[b][0], ends[b][1])}
            Y, at = hit
            src, dst = (Y, X) if pos[Y] < pos[X] else (X, Y)
            recs.append({"outcome": "gap_under" if X == dst else "gap_over", "at": at, "src": src, "dst": dst,
                         "relation": None, "kind": None, "step": pos[dst], "under": X,
                         "ends": [pa.tolist(), pb.tolist()]})
    for j, D in enumerate(ids):
        for S in ids[:j]:
            for c in crossings(L[S]["marks"], L[D]["marks"]):
                recs.append({"outcome": "cross", "at": np.asarray(c.at, float), "src": S, "dst": D,
                             "relation": None, "kind": None, "step": j})
    for X in ids:
        for i, m in enumerate(L[X]["marks"]):
            p = np.asarray(m.points, float)
            if len(p) < 4:
                continue
            for f, e in ((0, p[0]), (1, p[-1])):
                if (X, i, f) in used_ends:
                    continue
                for Y in ids:
                    if Y == X:
                        continue
                    if _dist_to(polys[Y], e) <= stop_tol:
                        src, dst = (Y, X) if pos[Y] < pos[X] else (X, Y)
                        recs.append({"outcome": "stop", "at": e.copy(), "src": src, "dst": dst, "relation": None,
                                     "kind": None, "step": pos[dst], "stopper": X})
                        break
    recs.sort(key=lambda r: (r["step"], ids.index(r["src"]) if r["src"] in ids else 0, float(r["at"][0]),
                             float(r["at"][1])))
    return recs


def under_ends(sheet, rec, L=None, *, reach: float = 4.5):
    """The two ends of the under line around a gap (for the ghost dashes):
    from the geometry census directly, else the nearest pair of ends of the
    under layer's marks on opposite sides of `at`."""
    if rec.get("ends"):
        return np.asarray(rec["ends"], float)
    L = L or layers(sheet)
    under = rec["dst"] if rec["outcome"] == "gap_under" else rec["src"]
    if under not in L:
        return None
    at = np.asarray(rec["at"], float)
    es = []
    for m in L[under]["marks"]:
        p = np.asarray(m.points, float)
        for e in (p[0], p[-1]):
            d = float(np.linalg.norm(e - at))
            if d <= reach:
                es.append((d, e))
    best = None
    for i in range(len(es)):
        for j in range(i + 1, len(es)):
            a, b = es[i][1], es[j][1]
            if float((a - at) @ (b - at)) < 0:
                sc = es[i][0] + es[j][0]
                if best is None or sc < best[0]:
                    best = (sc, a, b)
    return None if best is None else np.array([best[1], best[2]])


# ---------------------------------------------------------------------------
# small drawing helpers
# ---------------------------------------------------------------------------

def dashes(a, b, *, dash: float = 0.5, gap: float = 0.45) -> list[np.ndarray]:
    a, b = np.asarray(a, float), np.asarray(b, float)
    L = float(np.linalg.norm(b - a))
    if L < 1e-6:
        return []
    u = (b - a) / L
    out, s = [], 0.0
    while s < L - 1e-6:
        e = min(s + dash, L)
        out.append(np.array([a + s * u, a + e * u]))
        s = e + gap
    return out


def dashed_poly(p, *, dash: float = 0.6, gap: float = 0.5) -> list[np.ndarray]:
    """A polyline cut into dashes along its arc length."""
    p = np.asarray(p, float)
    if len(p) < 2:
        return []
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    out, a = [], 0.0
    while a < s[-1] - 1e-6:
        b = min(a + dash, s[-1])
        ss = np.r_[a, s[(s > a) & (s < b)], b]
        out.append(np.column_stack([np.interp(ss, s, p[:, 0]), np.interp(ss, s, p[:, 1])]))
        a = b + gap
    return out


def note(region, msg: str, *, h: float = 1.3, corner: str = "bl", pad: float = 2.0) -> list[np.ndarray]:
    """A small line of stroke text in a corner of the region (how a document
    says what it could not read)."""
    x0, y0, w, h0 = region
    msg = msg.upper()
    while R.text_w(msg, h) > w - 2 * pad and h > 0.7:
        h *= 0.9
    if corner == "tl":
        return R.text(msg, x0 + pad, y0 + pad, h)
    if corner == "br":
        return R.text(msg, x0 + w - pad, y0 + h0 - pad - h, h, anchor="right")
    return R.text(msg, x0 + pad, y0 + h0 - pad - h, h)


def free_corner(sheet, region, msg: str, *, h: float = 1.3, pad: float = 2.0):
    """The note in whichever corner of the region holds the least ink."""
    pts = [np.asarray(m.points, float) for m in R.drawing_marks(sheet)]
    allp = np.vstack(pts) if pts else np.zeros((0, 2))
    best = None
    for c in ("bl", "br", "tl"):
        polys = note(region, msg, h=h, corner=c, pad=pad)
        if not polys:
            return []
        q = np.vstack(polys)
        lo, hi = q.min(0) - 1.5, q.max(0) + 1.5
        n = int(((allp >= lo) & (allp <= hi)).all(1).sum()) if len(allp) else 0
        if best is None or n < best[0]:
            best = (n, polys)
    return best[1]


def free_ink(sheet, ink: str = "auto", prefer=("red", "magenta", "orange", "purple", "green", "cyan", "blue")) -> str:
    """'auto' → the first Flexoki accent the drawing does not use (its 400
    tints count as used), else the first preferred; any other value as given."""
    if ink != "auto":
        return ink
    used = set()
    for k in sheet.inks:
        if (k.meta or {}).get("layer") == "device":
            continue
        c = str((k.meta or {}).get("colour") or "black")
        used.add(c.split("-")[0])
    for m in sheet.marks:
        used.add(mark_colour(m).split("-")[0])
    for c in prefer:
        if c not in used:
            return c
    return prefer[0]


def layer_tag(L: dict, lid: str) -> str:
    """'3 MADELIN': the layer's place in the drawing order and its name."""
    if lid in L:
        return f"{L[lid]['index'] + 1} {L[lid]['label']}"
    return str(lid)
