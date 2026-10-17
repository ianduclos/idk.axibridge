"""A drawing and its measurement (round 10, exploration `measure_pairs`).

Ian, round 9: the diagram voices are best as ACCESSORIES — "they feel like
they are measuring or have correlation with the drawings". This file pairs a
loose drawing with its OWN measurement as one piece, and makes the
correlation legible with small numbered indices that sit both on the
drawing and on the chart (never an infographic: no legend, no colour, one
pen, the drawing stays the bigger voice).

- modulator `measure_pair`   drawing + its chart composed: `margin` (below),
                             `diptych` (right), `under` (chart under the
                             drawing, same box, finer pen), `wrap` (the κ
                             seismograph runs round the drawing on a rounded
                             frame); numbered indices tie places in the
                             drawing to places on the chart
- modulator `measure_shadow` the shadow line with overlaps MERGED: the strip
                             between the drawing and its offset shadow is
                             unioned (shapely) and traced as outline rings —
                             drawing and shadow read as one contour; laws
                             kappa / speed / regime / voice / time, sides
                             left / right / turns (inner side of each turn,
                             pinching to nothing at inflections → beads)
- modulator `measure_atlas`  the drawing taken apart into its shape atlas, as
                             a stand-alone piece: order by turning / time /
                             hand / length / sign; layout grid / frieze /
                             exploded (each specimen left where it was in
                             the drawing, pushed out from the centre)
- modulator `measure_answer` (the risk) the measurement drawn back INTO the
                             drawing as a second voice: a hand grown along
                             the drawing's own smoothed spine, busy where the
                             drawing is calm (silence) or where it is busy
                             (echo) — call and response decided by κ
- renderer `measure_wire`    wire, with a finer pen for the measurement
                             (chart, indices, shadow outlines keep `pen`)

Every added mark carries meta["measure_role"] in {chart, index, answer,
shadow}; the drawing's own marks keep their channels untouched. Labels use
the diagram voice's 3×5 stroke font (never Arabic).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from . import voices_machine_diagram as vd
from .core import Ink, Mark, P, modulator, refit, renderer

CHARTS = ("kappa", "route", "phase", "atlas", "ledger")
LAYOUTS = ("margin", "diptych", "under", "wrap")
ORDERS = ("turning", "time", "hand", "length", "sign")


# ---------------------------------------------------------------------------
# small geometry helpers
# ---------------------------------------------------------------------------

def _rule(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y1]], float)


def _circle(c, r, n=14):
    t = np.linspace(0, 2 * math.pi, n + 1)
    return np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)])


def _normals(p: np.ndarray) -> np.ndarray:
    tg = np.gradient(p, axis=0)
    tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
    return np.column_stack([-tg[:, 1], tg[:, 0]])


def _label(s: str, c, h: float) -> list[np.ndarray]:
    """Text centred on point c."""
    return vd.text(s, float(c[0]), float(c[1]) - h / 2, h, anchor="centre")


def _template(marks) -> list[str]:
    live = [m for m in marks if len(m)]
    return sorted(set.intersection(*(set(m.channels) for m in live))) if live else []


def _new_marks(polys, template, role: str, extra_meta: dict | None = None, part=None,
               src: dict | None = None) -> list[Mark]:
    """Measurement polylines as Marks carrying every channel of the drawing.
    Channels default to 0 (dry wire; phi/W/M back to the defaults); with `src`
    = {"p": (N,2), name: (N,)} each point takes the nearest drawing sample's
    channel values instead."""
    out = []
    tree = None
    if src is not None and len(src["p"]):
        from scipy.spatial import cKDTree  # noqa: PLC0415
        tree = cKDTree(src["p"])
    for p in polys:
        p = np.asarray(p, float)
        if len(p) < 2:
            continue
        n = len(p)
        ch = {c: np.zeros(n) for c in template if c not in ("phi", "W", "M")}
        if tree is not None:
            _, j = tree.query(p)
            for c in template:
                if c in src:
                    ch[c] = np.asarray(src[c], float)[j]
        ch.setdefault("r", np.zeros(n))
        if tree is None:
            ch["r"] = np.zeros(n)
        md = {"measure_role": role, "voice_id": f"measure:{role}", **(extra_meta or {})}
        if part is not None:
            md["part"] = part
        out.append(Mark(p, ch, md))
    return out


# ---------------------------------------------------------------------------
# anchors: places along the drawing, numbered
# ---------------------------------------------------------------------------

def anchors(M: dict, n: int, by: str) -> list[float]:
    """Arc lengths s of n indices along the measured drawing.
    even: evenly spaced; seams: hand changes (topped up evenly); peaks: the
    n strongest |κ| peaks, separated by ≥ L/(3n)."""
    L, s = M["L"], M["s"]
    if n <= 0 or L <= 0:
        return []
    if by == "seams":
        cut = [s[a] for a, _, _ in vd.runs(M["voice"])[1:]]
        if len(cut) >= n:
            idx = np.round(np.linspace(0, len(cut) - 1, n)).astype(int)
            return sorted(float(cut[i]) for i in idx)
        rest = [L * (i + 0.5) / (n - len(cut)) for i in range(n - len(cut))] if n > len(cut) else []
        return sorted([float(c) for c in cut] + rest)
    if by == "peaks":
        k = gaussian_filter1d(np.abs(M["kappa"]), 2.0, mode="nearest")
        order = np.argsort(-k, kind="stable")
        sep = L / (3.0 * n)
        got: list[float] = []
        for i in order:
            si = float(s[i])
            if all(abs(si - g) >= sep for g in got):
                got.append(si)
                if len(got) == n:
                    break
        return sorted(got)
    return [L * (i + 0.5) / n for i in range(n)]


def _at(M: dict, s: float):
    """Point, unit normal and global sample index of the drawing at arc length s."""
    i = int(np.clip(np.searchsorted(M["s"], s), 0, len(M["s"]) - 1))
    lo, hi = max(i - 2, 0), min(i + 3, len(M["s"]))
    if M["mark"][lo] != M["mark"][hi - 1]:
        lo, hi = max(i - 1, 0), min(i + 2, len(M["s"]))
    d = M["p"][min(hi - 1, len(M["p"]) - 1)] - M["p"][lo]
    d = d / (np.linalg.norm(d) + 1e-12)
    return M["p"][i], np.array([-d[1], d[0]]), i


def index_on_drawing(M: dict, ss: list[float], labels: list[str], *, label_h: float, tick: float,
                     side: float = 1.0) -> list[np.ndarray]:
    """A short tick off the line at each s and its number beside it (on the
    normal side `side`, flipped to whichever side is emptier)."""
    out = []
    P_ = M["p"]
    for s_, lab in zip(ss, labels):
        p, nrm, _ = _at(M, s_)
        best = None
        for sg in (side, -side):
            c = p + sg * nrm * (tick + 0.9 * label_h)
            d = float(np.min(np.linalg.norm(P_ - c, axis=1)))
            if best is None or d > best[0] + 1e-9:
                best = (d, sg)
        sg = best[1]
        out.append(np.array([p + sg * nrm * 0.5, p + sg * nrm * (0.5 + tick)]))
        out += _label(lab, p + sg * nrm * (tick + 0.6 + 0.55 * label_h), label_h)
    return out


# ---------------------------------------------------------------------------
# charts that also say where an arc length lands on them
# ---------------------------------------------------------------------------

def kappa_with_index(M, box, ss, labels, *, rows, label_h):
    out = vd.chart_kappa(M, box, rows=rows, label_h=label_h)
    x0, y0, w, h = box
    gut = vd.text_width("0000", label_h) + 2.0
    xa, wa = x0 + gut, w - gut
    rh, per = h / rows, M["L"] / rows
    for s_, lab in zip(ss, labels):
        r = min(int(s_ // per), rows - 1)
        x = xa + (s_ - r * per) / per * wa
        yb = y0 + (r + 0.5) * rh
        out.append(_rule(x, yb + 0.15 * rh, x, yb + 0.27 * rh))
        out += vd.text(lab, x, yb + 0.29 * rh, 0.7 * label_h, anchor="centre")
    return out


def route_with_index(M, box, ss, labels, *, label_h, **_):
    out = vd.chart_route(M, box, label_h=label_h)
    x0, y0, w, h = box
    voices = M["voices"]
    present = sorted({int(v) for v in np.unique(M["voice"])})
    gut = max(vd.text_width(vd.short(voices[i]) if i < len(voices) else "?", label_h) for i in present) + 2.0
    xa, wa = x0 + gut, w - gut
    lh = h / max(len(present), 1)
    yb = y0 + (len(present) - 1 + 0.85) * lh
    for s_, lab in zip(ss, labels):
        x = xa + s_ / M["L"] * wa
        out.append(_rule(x, yb + 0.4, x, yb + 1.6))
        out += vd.text(lab, x, yb + 2.0, 0.7 * label_h, anchor="centre")
    return out


def phase_with_index(M, box, ss, labels, *, label_h, **_):
    out = vd.chart_phase(M, box, label_h=label_h)
    x0, y0, w, h = box
    k = gaussian_filter1d(M["kappa"], 4.0, mode="nearest") * M["R"]
    dk = gaussian_filter1d(np.gradient(k) / (M["h"] / M["R"]), 4.0, mode="nearest")
    sx = max(float(np.percentile(np.abs(k), 97)), 1e-9)
    sy = max(float(np.percentile(np.abs(dk), 97)), 1e-9)
    cx, cy = x0 + w / 2, y0 + h / 2
    half = 0.46 * min(w, h)
    for s_, lab in zip(ss, labels):
        i = int(np.clip(np.searchsorted(M["s"], s_), 0, len(k) - 1))
        X = cx + math.tanh(k[i] / sx) * half * (w / min(w, h)) * 0.95
        Y = cy - math.tanh(dk[i] / sy) * half
        out.append(_circle((X, Y), 0.5 * label_h))
        out += vd.text(lab, X + 0.7 * label_h, Y - 1.4 * label_h, 0.7 * label_h)
    return out


# ---------------------------------------------------------------------------
# atlas with provenance (each specimen knows where it came from)
# ---------------------------------------------------------------------------

def specimens(M: dict, *, min_frac: float = 0.012, sigma: float = 6.0) -> list[dict]:
    """The measured line cut at inflections (and mark ends): each specimen's
    points, signed turning, arc range, speaking voice."""
    k = gaussian_filter1d(M["kappa"], sigma, mode="nearest")
    cut = np.flatnonzero((np.diff(np.sign(k)) != 0) | (np.diff(M["mark"]) != 0)) + 1
    edges = np.r_[0, cut, len(k)]
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b - a < 4 or M["s"][b - 1] - M["s"][a] < min_frac * M["L"]:
            continue
        turn = float(np.sum(M["kappa"][a:b]) * M["h"])
        vals, cnt = np.unique(M["voice"][a:b].astype(int), return_counts=True)
        out.append({"a": int(a), "b": int(b), "p": M["p"][a:b], "turn": turn,
                    "s0": float(M["s"][a]), "s1": float(M["s"][b - 1]),
                    "s_mid": float(M["s"][(a + b) // 2]), "length": float(M["s"][b - 1] - M["s"][a]),
                    "voice": int(vals[np.argmax(cnt)])})
    return out


def order_specimens(sp: list[dict], order: str, cells: int) -> list[dict]:
    key = {"turning": lambda t: (abs(t["turn"]), t["s0"]), "time": lambda t: t["s0"],
           "hand": lambda t: (t["voice"], t["s0"]), "length": lambda t: (t["length"], t["s0"]),
           "sign": lambda t: (t["turn"], t["s0"])}[order]
    sp = sorted(sp, key=key)
    if len(sp) > cells:
        idx = np.round(np.linspace(0, len(sp) - 1, cells)).astype(int)
        sp = [sp[i] for i in idx]
    return sp


def _chord_frame(p: np.ndarray) -> np.ndarray:
    q = p - p[0]
    a = math.atan2(q[-1, 1], q[-1, 0])
    R = np.array([[math.cos(-a), -math.sin(-a)], [math.sin(-a), math.cos(-a)]])
    return q @ R.T


def atlas_layout(sp: list[dict], box, *, layout: str, label_h: float, numbers: bool, rows: int = 1,
                 explode: float = 0.45, centre=None, degrees: bool = True) -> list[np.ndarray]:
    """Specimens (already ordered) set in box. grid / frieze: chord-level, one
    common scale (so a big arc stays big), numbered in order; exploded: each
    specimen at its own place and angle, pushed out from `centre`."""
    x0, y0, w, h = box
    n = len(sp)
    if n == 0:
        return []
    out = []
    if layout == "exploded":
        c = np.asarray(centre if centre is not None else np.mean(np.vstack([t["p"] for t in sp]), axis=0))
        moved = []
        for t in sp:
            mid = t["p"].mean(axis=0)
            moved.append(t["p"] + explode * (mid - c))
        allp = np.vstack(moved)
        lo, hi = allp.min(axis=0), allp.max(axis=0)
        k = min(w / max(hi[0] - lo[0], 1e-9), (h - 1.6 * label_h) / max(hi[1] - lo[1], 1e-9))
        off = np.array([x0 + w / 2, y0 + (h - 1.6 * label_h) / 2]) - (lo + hi) / 2 * k
        for i, q in enumerate(moved):
            qq = q * k + off
            out.append(qq)
            if numbers:
                mid = qq[len(qq) // 2]
                nrm = _normals(qq)[len(qq) // 2]
                out += _label(f"{i + 1}", mid - nrm * 1.4 * label_h, 0.8 * label_h)
        return out
    norm = [_chord_frame(t["p"]) for t in sp]
    if layout == "frieze":
        rows_ = max(int(rows), 1)
        cols = -(-n // rows_)
    else:
        cols = max(int(round(math.sqrt(n * w / h))), 1)
        rows_ = -(-n // cols)
    cw, ch = w / cols, h / rows_
    ext_w = max(float(np.percentile([np.ptp(q[:, 0]) for q in norm], 92)), 1e-9)
    ext_h = max(float(np.percentile([np.ptp(q[:, 1]) for q in norm], 92)), 1e-9)
    sc = min(0.82 * cw / ext_w, 0.6 * ch / ext_h)
    for i, q in enumerate(norm):
        r, c = divmod(i, cols)
        cx0, cy0 = x0 + c * cw, y0 + r * ch
        s_ = min(sc, 0.92 * cw / max(np.ptp(q[:, 0]), 1e-9), 0.7 * ch / max(np.ptp(q[:, 1]), 1e-9))
        mid = (q.min(axis=0) + q.max(axis=0)) / 2
        pts = (q - mid) * s_ + np.array([cx0 + cw / 2, cy0 + 0.40 * ch])
        out.append(pts)
        if numbers:
            lab = f"{i + 1:02d}" + (f" {math.degrees(sp[i]['turn']):+.0f}" if degrees else "")
            out += vd.text(lab, cx0 + cw / 2, cy0 + 0.78 * ch, 0.85 * label_h, anchor="centre")
    return out


# ---------------------------------------------------------------------------
# wrap: the κ seismograph on a rounded frame round the drawing
# ---------------------------------------------------------------------------

def rounded_frame(box, r: float, step: float = 0.5) -> np.ndarray:
    """Closed rounded-rectangle polyline, clockwise on the sheet (y down),
    starting at the top-left end of the top edge."""
    x0, y0, w, h = box
    r = min(r, w / 2, h / 2)
    pts = []

    def arc(cx, cy, a0, a1):
        n = max(int(abs(a1 - a0) * r / step), 2)
        for t in np.linspace(a0, a1, n, endpoint=False):
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))

    def line(a, b):
        n = max(int(math.dist(a, b) / step), 1)
        for t in np.linspace(0, 1, n, endpoint=False):
            pts.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))

    line((x0 + r, y0), (x0 + w - r, y0))
    arc(x0 + w - r, y0 + r, -math.pi / 2, 0)
    line((x0 + w, y0 + r), (x0 + w, y0 + h - r))
    arc(x0 + w - r, y0 + h - r, 0, math.pi / 2)
    line((x0 + w - r, y0 + h), (x0 + r, y0 + h))
    arc(x0 + r, y0 + h - r, math.pi / 2, math.pi)
    line((x0, y0 + h - r), (x0, y0 + r))
    arc(x0 + r, y0 + r, math.pi, 1.5 * math.pi)
    pts.append(pts[0])
    return np.array(pts, float)


def wrap_chart(M, frame_box, ss, labels, *, amp: float, label_h: float, corner: float) -> list[np.ndarray]:
    fr = rounded_frame(frame_box, corner)
    u = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(fr, axis=0), axis=1))]
    Pm = u[-1]
    c = np.array([frame_box[0] + frame_box[2] / 2, frame_box[1] + frame_box[3] / 2])
    nrm = _normals(fr)
    flip = np.sign(np.sum(nrm * (fr - c), axis=1))
    nrm = nrm * np.where(flip == 0, 1, flip)[:, None]                  # outward everywhere

    def at(uu):
        x = np.interp(uu, u, fr[:, 0]); y = np.interp(uu, u, fr[:, 1])
        nx = np.interp(uu, u, nrm[:, 0]); ny = np.interp(uu, u, nrm[:, 1])
        nn = np.hypot(nx, ny) + 1e-12
        return np.column_stack([x, y]), np.column_stack([nx / nn, ny / nn])

    k = M["kappa"]
    kmax = max(float(np.percentile(np.abs(k), 98)), 1e-9)
    uu = M["s"] / M["L"] * Pm * 0.985                                   # a small gap marks the start
    base, nn = at(uu)
    tr = base + nn * (np.clip(k / kmax, -1.25, 1.25) * amp)[:, None]
    out = [fr]
    for i0, i1, _ in vd.runs(M["mark"]):
        if i1 - i0 >= 2:
            out.append(tr[i0:i1])
    for s_, lab in zip(ss, labels):
        b, n_ = at(np.array([s_ / M["L"] * Pm * 0.985]))
        b, n_ = b[0], n_[0]
        out.append(np.array([b - n_ * (amp * 0.15 + 0.8), b - n_ * (amp * 0.15 + 2.4)]))
        out += _label(lab, b - n_ * (amp * 0.15 + 3.4 + 0.5 * label_h), 0.75 * label_h)
    b0, n0 = at(np.array([0.0]))
    out.append(np.array([b0[0] - n0[0] * 1.2, b0[0] + n0[0] * 1.2]))
    return out


# ---------------------------------------------------------------------------
# modulator: measure_pair
# ---------------------------------------------------------------------------

_HAND_PARAMS = [
    P("drawn_by", "ref", None, "redraw the measurement through this hand (null = the machine draws it)",
      kind="hand", optional=True),
    P("amount", "float", 1.5, "how much fine turning the hand owns", min=0.0, max=3.0),
    P("keep", "float", 0.006, "drawn_by: coarse scale the hand must keep (small = faithful)", min=0.001, max=0.2),
]


def _pair_reach(p):
    return 2.0


@modulator("measure_pair", params=[
    P("chart", "choice", "kappa", "which measurement: kappa rows / route lanes / phase plot / atlas / ledger",
      choices=CHARTS),
    P("layout", "choice", "diptych", "margin: chart below | diptych: chart right | under: chart under the "
      "drawing in the same box (finer pen) | wrap: κ runs round the drawing on a rounded frame", choices=LAYOUTS),
    P("split", "float", 0.42, "share of the box the chart takes (margin/diptych); wrap: band width as a "
      "share of the short side × 0.33", min=0.1, max=0.8),
    P("index", "int", 9, "numbered indices tying places in the drawing to the chart (0 = none; atlas/ledger "
      "number their own specimens/deciles)", min=0, max=40),
    P("index_by", "choice", "peaks", "even | seams (hand changes) | peaks (strongest turns)",
      choices=("even", "seams", "peaks")),
    P("rows", "int", 5, "kappa rows", min=1, max=12),
    P("cells", "int", 24, "atlas: specimens shown", min=4, max=80),
    P("order", "choice", "time", "atlas: specimen order", choices=ORDERS),
    P("label_h", "float", 2.0, "label cap height, mm", min=0.8, max=8.0),
    P("index_h", "float", 1.6, "index number height on the drawing, mm", min=0.6, max=6.0),
    *_HAND_PARAMS,
], doc="a drawing paired with its own measurement, places tied by numbered indices", reach=_pair_reach)
def measure_pair(ctx, marks, *, chart, layout, split, index, index_by, rows, cells, order, label_h, index_h,
                 drawn_by, amount, keep):
    live = [m for m in marks if len(m) >= 2]
    if not live:
        return list(marks)
    template = _template(marks)
    part = marks[0].meta.get("part")
    x0, y0, w, h = ctx.box
    if layout == "wrap":
        band = split * 0.33 * min(w, h)
        dbox = (x0 + band, y0 + band, w - 2 * band, h - 2 * band)
        drawing = refit(list(marks), dbox)
    elif layout == "under":
        drawing = list(marks)
        cbox = ctx.box
    else:
        pad = 0.04 * (h if layout == "margin" else w)
        if layout == "margin":
            dbox = (x0, y0, w, h * (1 - split) - pad / 2)
            cbox = (x0, y0 + h * (1 - split) + pad / 2, w, h * split - pad / 2)
        else:
            dbox = (x0, y0, w * (1 - split) - pad / 2, h)
            cbox = (x0 + w * (1 - split) + pad / 2, y0, w * split - pad / 2, h)
        drawing = refit(list(marks), dbox)
    M = vd.measure(drawing)
    if M["L"] <= 0:
        return list(marks)
    idx_polys: list[np.ndarray] = []
    if chart == "atlas" and layout != "wrap":
        sp = order_specimens(specimens(M), order, cells)
        polys = atlas_layout(sp, cbox, layout="grid", label_h=label_h, numbers=True)
        ss = [t["s_mid"] for t in sp]
        labs = [f"{i + 1:02d}" for i in range(len(sp))]
    elif chart == "ledger" and layout != "wrap":
        polys = vd.chart_ledger(M, cbox, label_h=label_h)
        ss = [M["L"] * d / 10 for d in range(10)]
        labs = [f"{d + 1:02d}" for d in range(10)]
    else:
        ss = anchors(M, index, index_by)
        labs = [f"{i + 1}" for i in range(len(ss))]
        if layout == "wrap":
            lo, hi = M["p"].min(axis=0), M["p"].max(axis=0)          # the frame hugs the drawing
            fx0, fy0 = max(lo[0] - 0.58 * band, x0 + 0.42 * band), max(lo[1] - 0.58 * band, y0 + 0.42 * band)
            fx1 = min(hi[0] + 0.58 * band, x0 + w - 0.42 * band)
            fy1 = min(hi[1] + 0.58 * band, y0 + h - 0.42 * band)
            fb = (fx0, fy0, fx1 - fx0, fy1 - fy0)
            polys = wrap_chart(M, fb, ss, labs, amp=0.34 * band, label_h=label_h, corner=0.6 * band)
        elif chart == "kappa":
            polys = kappa_with_index(M, cbox, ss, labs, rows=rows, label_h=label_h)
        elif chart == "route":
            polys = route_with_index(M, cbox, ss, labs, label_h=label_h)
        else:
            polys = phase_with_index(M, cbox, ss, labs, label_h=label_h)
    if ss:
        idx_polys = index_on_drawing(M, ss, labs, label_h=index_h, tick=1.6)
    polys = [np.asarray(p, float) for p in polys if len(p) >= 2]
    if drawn_by:
        polys = vd.hand_drawn(polys, ctx.use("hand", drawn_by), ctx.rng("drawn_by", drawn_by), amount=amount,
                              keep=keep)
    out = list(drawing)
    out += _new_marks(polys, template, "chart", {"chart": chart, "layout": layout, "drawn_by": drawn_by}, part)
    out += _new_marks(idx_polys, template, "index", {"chart": chart}, part)
    return out


# ---------------------------------------------------------------------------
# modulator: measure_shadow (overlaps merged)
# ---------------------------------------------------------------------------

SHADOW_LAWS = ("kappa", "speed", "regime", "voice", "time")
SIDES = ("left", "right", "turns", "outer")


def _law(M: dict, law: str) -> np.ndarray:
    k = np.abs(M["kappa"])
    if law == "speed":
        v = M.get("speed")
        if v is None:
            v = (k * M["R"] + 0.5) ** (-1.0 / 3.0)                      # 2/3 power law: fast on straights
    elif law == "regime":
        v = M["r"].astype(float)
    elif law == "voice":
        v = M["voice"].astype(float)
    elif law == "time":
        dt = M["dance_t"]
        v = np.nan_to_num(dt, nan=0.0) if np.isfinite(dt).any() else M["s"] / M["L"]
    else:
        v = k
    v = gaussian_filter1d(np.asarray(v, float), 3.0, mode="nearest")
    lo, hi = float(np.percentile(v, 2)), float(np.percentile(v, 98))
    return np.clip((v - lo) / max(hi - lo, 1e-9), 0.0, 1.0)


def shadow_lines(M: dict, *, law: str, side: str, gap: float, gain: float) -> list[tuple[np.ndarray, np.ndarray, slice]]:
    """(drawing points, shadow points, sample slice) per mark."""
    v = _law(M, law)
    d = gap + gain * v
    ks = gaussian_filter1d(M["kappa"], 4.0, mode="nearest")
    k0 = max(float(np.percentile(np.abs(ks), 50)), 1e-9)
    if side == "left":
        sg = np.ones_like(d)
    elif side == "right":
        sg = -np.ones_like(d)
    elif side == "turns":
        sg = np.tanh(ks / k0)
    else:
        sg = -np.tanh(ks / k0)
    out = []
    for i0, i1, _ in vd.runs(M["mark"]):
        p = M["p"][i0:i1]
        if len(p) < 3:
            continue
        out.append((p, p + _normals(p) * (d[i0:i1] * sg[i0:i1])[:, None], slice(i0, i1)))
    return out


def _strip_triangles(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    a, b, c, d = p[:-1], p[1:], q[1:], q[:-1]
    return np.concatenate([np.stack([a, b, c, a], axis=1), np.stack([a, c, d, a], axis=1)])


def merged_rings(pairs, *, close: float, shape: str = "beads", simplify: float = 0.03, min_open: float = 0.6):
    """Merge each drawing line with its shadow into one contour.

    strip: the exact strip between line and shadow (triangles — always
    valid, degenerate where the shadow pinches to the line).
    beads: the strip from the line to the half-way line, plus a disc of
    diameter d at every half-way point — the far side rounds off (no
    swallowtails at tight inner turns; turns swell into beads).
    The union is closed morphologically by `close` mm and traced as outline
    rings; wherever the strip pinches to nothing the drawing's own line is
    kept as an open line, so the drawing never breaks.
    → (closed rings, open drawing remnants, union geometry)."""
    import shapely  # noqa: PLC0415
    tris, discs = [], []
    for p, q, _ in pairs:
        if shape == "strip":
            tris.append(_strip_triangles(p, q))
        else:
            c = (p + q) / 2
            r = np.linalg.norm(q - p, axis=1) / 2
            tris.append(_strip_triangles(p, c))
            keep = r > 0.05
            if keep.any():
                discs.append(shapely.buffer(shapely.points(c[keep]), r[keep], quad_segs=5))
    if not tris:
        return [], [], None
    T = np.concatenate(tris)
    area = 0.5 * np.abs((T[:, 1, 0] - T[:, 0, 0]) * (T[:, 2, 1] - T[:, 0, 1])
                        - (T[:, 2, 0] - T[:, 0, 0]) * (T[:, 1, 1] - T[:, 0, 1]))
    T = T[area > 1e-6]
    geoms = [shapely.polygons(T)] if len(T) else []
    geoms += discs
    if not geoms:
        return [], [np.asarray(p) for p, _, _ in pairs], None
    eps = 0.02
    G = shapely.union_all(shapely.buffer(np.concatenate(geoms), eps, quad_segs=2))
    if close > 0:
        G = G.buffer(close, quad_segs=4).buffer(-close, quad_segs=4)
    G = G.simplify(simplify)
    rings = []
    for g in sorted(getattr(G, "geoms", [G]), key=lambda g: -g.area):
        if g.is_empty or g.geom_type != "Polygon" or g.area < 0.05:
            continue
        rings.append(np.asarray(g.exterior.coords))
        rings += [np.asarray(r.coords) for r in g.interiors if len(r.coords) >= 4 and
                  shapely.Polygon(r).area >= 0.05]
    opened = []
    cover = G.buffer(0.03)
    for p, _, _ in pairs:
        rest = shapely.LineString(p).difference(cover)
        for ln in getattr(rest, "geoms", [rest]):
            if not ln.is_empty and ln.geom_type == "LineString" and ln.length >= min_open:
                opened.append(np.asarray(ln.coords))
    return rings, opened, G


def _shadow_reach(p):
    return p["gap"] + p["gain"]


@modulator("measure_shadow", params=[
    P("law", "choice", "kappa", "what sets the distance: kappa |κ| | speed (2/3 power law, or the dance's own) | "
      "regime r | voice | time (dance clock)", choices=SHADOW_LAWS),
    P("side", "choice", "left", "left / right of travel | turns: the inner side of every turn (pinches to the "
      "line at inflections → beads) | outer", choices=SIDES),
    P("gap", "float", 1.2, "base distance, mm", min=0.0, max=30.0),
    P("gain", "float", 4.0, "extra distance at the measurement's max, mm", min=0.0, max=60.0),
    P("merge", "choice", "union", "none: drawing + shadow as two lines (round 9) | union: the strip between "
      "them unioned and traced as outline rings — overlaps merge into one contour", choices=("none", "union")),
    P("shape", "choice", "beads", "union: beads (half-strip + discs: the far side rounds off, turns swell "
      "into beads) | strip (the exact strip; sharp swallowtails at tight turns)", choices=("beads", "strip")),
    P("close", "float", 0.0, "union: morphological closing radius, mm (fuses near-touches; 0 = exact)",
      min=0.0, max=10.0),
    P("keep_drawing", "bool", False, "union: also keep the drawing's own centreline inside the contour"),
], doc="the shadow line with overlaps merged: drawing ∪ shadow strip traced as one contour",
    reach=_shadow_reach)
def measure_shadow(ctx, marks, *, law, side, gap, gain, merge, shape, close, keep_drawing):
    live = [m for m in marks if len(m) >= 2]
    if not live:
        return list(marks)
    template = _template(marks)
    part = marks[0].meta.get("part")
    M = vd.measure(live)
    if M["L"] <= 0:
        return list(marks)
    if law == "speed" and all("dance_speed" in m.channels for m in live):
        sp = []
        for m in live:
            q = m.resampled(M["h"])
            sp.append(q.channels["dance_speed"])
        sp = np.concatenate(sp)
        if len(sp) == len(M["s"]):
            M["speed"] = sp
    pairs = shadow_lines(M, law=law, side=side, gap=gap, gain=gain)
    src = {"p": M["p"], "voice": M["voice"], "r": M["r"]}
    if merge == "none":
        return list(marks) + _new_marks([q for _, q, _ in pairs], template, "shadow",
                                        {"law": law, "side": side}, part)
    rings, opened, _ = merged_rings(pairs, close=close, shape=shape)
    out = list(marks) if keep_drawing else []
    out += _new_marks(rings, template, "shadow", {"law": law, "side": side, "merged": True}, part, src=src)
    if not keep_drawing:
        out += _new_marks(opened, template, "shadow", {"law": law, "side": side, "merged": True, "open": True},
                          part, src=src)
    return out or list(marks)


# ---------------------------------------------------------------------------
# modulator: measure_atlas (the atlas as a piece)
# ---------------------------------------------------------------------------

@modulator("measure_atlas", params=[
    P("order", "choice", "turning", "turning | time | hand | length | sign", choices=ORDERS),
    P("layout", "choice", "grid", "grid | frieze (rows of specimens, read like a line of writing) | exploded "
      "(each specimen where it was, pushed out from the centre)", choices=("grid", "frieze", "exploded")),
    P("cells", "int", 30, "specimens shown (evenly sampled over the order)", min=2, max=120),
    P("grain", "float", 0.012, "finest specimen, as a share of the line's length (smaller = more, shorter "
      "specimens; the inflection smoothing scales with it)", min=0.002, max=0.06),
    P("rows", "int", 3, "frieze rows", min=1, max=20),
    P("explode", "float", 0.45, "exploded: push-out factor", min=0.0, max=3.0),
    P("numbers", "bool", True, "number the specimens (order index + turning in degrees on grid/frieze)"),
    P("degrees", "bool", True, "grid/frieze: print each specimen's turning"),
    P("label_h", "float", 2.0, "label cap height, mm", min=0.8, max=8.0),
    P("keep_drawing", "bool", False, "keep the drawing (left/top half) beside its atlas"),
    *_HAND_PARAMS,
], doc="the drawing taken apart into its shape atlas, as a piece (orders, layouts, a hand to draw it)")
def measure_atlas(ctx, marks, *, order, layout, cells, grain, rows, explode, numbers, degrees, label_h, keep_drawing,
                  drawn_by, amount, keep):
    live = [m for m in marks if len(m) >= 2]
    if not live:
        return list(marks)
    template = _template(marks)
    part = marks[0].meta.get("part")
    x0, y0, w, h = ctx.box
    drawing = list(marks)
    abox = ctx.box
    if keep_drawing:
        pad = 0.04 * w
        drawing = refit(list(marks), (x0, y0, 0.42 * w - pad / 2, h))
        abox = (x0 + 0.42 * w + pad / 2, y0, 0.58 * w - pad / 2, h)
    M = vd.measure(drawing)
    sp = order_specimens(specimens(M, min_frac=grain, sigma=max(6.0 * grain / 0.012, 1.0)), order, cells)
    c = M["p"].mean(axis=0)
    polys = atlas_layout(sp, abox, layout=layout, label_h=label_h, numbers=numbers, rows=rows, explode=explode,
                         centre=c, degrees=degrees)
    if drawn_by:
        polys = vd.hand_drawn(polys, ctx.use("hand", drawn_by), ctx.rng("drawn_by", drawn_by), amount=amount,
                              keep=keep)
    out = list(drawing) if keep_drawing else []
    if keep_drawing and numbers and layout != "exploded":
        out += _new_marks(index_on_drawing(M, [t["s_mid"] for t in sp], [f"{i + 1:02d}" for i in range(len(sp))],
                                           label_h=0.75 * label_h, tick=1.4), template, "index", {}, part)
    out += _new_marks(polys, template, "chart" if keep_drawing else "atlas",
                      {"chart": f"atlas:{layout}", "order": order, "drawn_by": drawn_by}, part)
    return out


# ---------------------------------------------------------------------------
# modulator: measure_answer (the risk)
# ---------------------------------------------------------------------------

def _resample_n(p: np.ndarray, n: int) -> np.ndarray:
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    t = np.linspace(0, s[-1], n)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


@modulator("measure_answer", params=[
    P("hand", "ref", "lichtenberg", "the answering hand", kind="hand"),
    P("where", "choice", "silence", "silence: the answer is busy where the drawing is calm (and calm where it "
      "turns) | echo: busy where the drawing is busy", choices=("silence", "echo")),
    P("spine", "float", 0.03, "how far the answer may leave the drawing: smoothing of the drawing's course it "
      "follows, as a share of the sheet diagonal", min=0.002, max=0.2),
    P("offset", "float", 3.0, "lateral offset of the answer from the drawing, mm", min=-40.0, max=40.0),
    P("amount", "float", 2.2, "how much fine turning the answering hand owns at full voice", min=0.0, max=3.0),
    P("listen", "float", 0.08, "how far the answer listens along the line (smoothing of |κ|, share of length)",
      min=0.005, max=0.5),
    P("contrast", "float", 1.6, "how sharply the answer switches between voiced and quiet", min=0.3, max=6.0),
    P("quiet", "choice", "spine", "what the answer does when it is not speaking: spine (keeps going, plain, "
      "beside the drawing) | lift (pen up — the answer only interjects)", choices=("spine", "lift")),
], doc="the measurement drawn back into the drawing: a second hand that answers its turning",
    reach=lambda p: abs(p["offset"]))
def measure_answer(ctx, marks, *, hand, where, spine, offset, amount, listen, contrast, quiet):
    from .. import grammar as gm  # noqa: PLC0415
    from .voices_machine import resample  # noqa: PLC0415
    live = [m for m in marks if len(m) >= 2 and m.length() > 0]
    if not live:
        return list(marks)
    template = _template(marks)
    part = marks[0].meta.get("part")
    g = ctx.use("hand", hand)
    rng = ctx.rng("answer", hand)
    M = vd.measure(live)
    diag = M["R"]
    answers, voiced = [], []
    for i0, i1, _ in vd.runs(M["mark"]):
        p = M["p"][i0:i1]
        if len(p) < 12:
            continue
        sig = max(spine * diag / M["h"], 1.0)
        sp = np.column_stack([gaussian_filter1d(p[:, 0], sig, mode="nearest"),
                              gaussian_filter1d(p[:, 1], sig, mode="nearest")])
        sp = sp + _normals(sp) * offset
        k = gaussian_filter1d(np.abs(M["kappa"][i0:i1]), max(listen * M["L"] / M["h"], 1.0), mode="nearest")
        z = (k - np.median(k)) / max(float(np.std(k)), 1e-9)
        busy = 1.0 / (1.0 + np.exp(-contrast * z))
        voice_amt = (1.0 - busy) if where == "silence" else busy
        # the answering hand speaks the whole spine once, in a native frame
        lo = sp.min(axis=0)
        kk = 1000.0 / max(diag, 1e-9)
        q = resample((sp - lo) * kk, 1.0)
        if len(q) < 8:
            continue
        try:
            st = gm.restyle(q, g, rng, ref_length=1000.0 / 0.9, amount=amount, coarse_frac=0.004, step=1.0)
            H = st.points / kk + lo
        except Exception:  # noqa: BLE001 — degenerate spine: the answer stays quiet
            H = sp
        n = len(sp)
        Hn = _resample_n(H, n)
        a = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(voice_amt)), voice_amt)
        ans = sp + a[:, None] * (Hn - sp)
        if quiet == "lift":
            on = a >= 0.5
            for i0_, i1_, v in vd.runs(on.astype(float)):
                if v > 0 and i1_ - i0_ >= 8:
                    answers.append(ans[i0_:i1_])
        else:
            answers.append(ans)
        voiced.append(float(np.mean(a)))
    out = list(marks)
    out += _new_marks(answers, template, "answer", {"hand": hand, "where": where, "voices": [hand]}, part)
    return out


# ---------------------------------------------------------------------------
# renderer
# ---------------------------------------------------------------------------

@renderer("measure_wire", params=[
    P("pen", "float", 0.4, "pen for the drawing (and answer / shadow), mm", min=0.05, max=3.0),
    P("chart_pen", "float", 0.25, "pen for the measurement (chart, indices), mm", min=0.05, max=3.0),
], doc="wire, with a finer pen for the measurement", reach=lambda p: 0.5 * max(p["pen"], p["chart_pen"]))
def measure_wire(ctx, marks, *, pen, chart_pen):
    out = []
    for m in marks:
        if len(m) < 2:
            continue
        role = m.meta.get("measure_role", "drawing")
        pw = chart_pen if role in ("chart", "index") else pen
        closed = len(m) >= 4 and bool(np.allclose(m.points[0], m.points[-1], atol=1e-9))
        out.append(Ink(m.points, closed=closed, filled=False, pen=pw,
                       meta={"voice": m.meta.get("voice_id"), "measure_role": role}))
    return out
