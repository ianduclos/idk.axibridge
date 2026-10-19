# FROZEN from research commit f59eac4: tools/gesture/gesture/kit/voices_machine_diagram.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Diagram voices: the system's own measurements drawn as plotter line (round 9).

Ian, round-8 review: "love these charts as pieces" — process as material
(review D). A diagram here is ink: rule lines, traces, ticks and labels in a
plotter stroke font, measured from Marks (their points and channels), so it
can be a piece in itself or sit beside the line it describes.

- voice `diagram`     grows a line (a hand, a drift, optionally handed to a
                      machine) and draws ONE chart of it, full box
- modulator `annotate` the chart of the marks it receives (after every
                      earlier modulator: a handover, a timing), placed
                      below / right of the drawing (which is refit into the
                      rest of the box), or as a `shadow`: a second line that
                      follows the drawing at a distance = the measurement

Charts (`CHARTS`):
- kappa   κ(s) as seismograph rows; seams (hand changes) ticked and named,
          machine stretches bracketed
- route   one lane per voice: its local share along s (the route weights
          as the line actually spoke them)
- tempo   the speed a hand would draw this at (2/3 power law, v ∝ κ^-1/3)
          and, after `timing`, the dance clock t(s) and regime r(s)
- phase   panel-space projection: the trajectory (κ, dκ/ds) as one line
- atlas   the line cut at inflections, specimens set chord-level in a grid,
          sorted by total turning, numbered
- ledger  a stat table drawn with rules: per decile |κ|·R, corners per R,
          machine share, the speaking voice

The limb (`drawn_by`): every chart polyline can be redrawn through a learned
hand (`grammar.restyle`: coarse path kept, fine turning from the hand) — a
measurement trace that becomes a drawing, e.g. Matisse drawing the κ(s) of
a shikasta line.

Labels use a 16-segment-like stroke font on a 3×5 grid (machine lettering;
uppercase, digits, a few signs). Never Arabic.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .core import Mark, P, modulator, voice
from .voices_base import grow
from .voices_machine import GRAMMARS, _OPTS, _opts, choose_stretches, hand_over

CHARTS = ("kappa", "route", "tempo", "phase", "atlas", "ledger")

# ---------------------------------------------------------------------------
# stroke font: glyphs on a 3×5 grid ("xy", x 0..2, y 0..4, y down)
# ---------------------------------------------------------------------------

_GLYPHS = {
    "A": "04-01-10-21-24|02-22", "B": "04-00-10-21-12-02|12-23-14-04", "C": "21-10-01-03-14-23",
    "D": "00-10-21-23-14-04-00", "E": "20-00-04-24|02-12", "F": "20-00-04|02-12",
    "G": "21-10-01-03-14-23-22-12", "H": "00-04|20-24|02-22", "I": "00-20|10-14|04-24", "J": "20-23-14-03",
    "K": "00-04|20-02-24", "L": "00-04-24", "M": "04-00-12-20-24", "N": "04-00-24-20",
    "O": "10-01-03-14-23-21-10", "P": "04-00-10-21-12-02", "Q": "10-01-03-14-23-21-10|13-24",
    "R": "04-00-10-21-12-02|12-24", "S": "21-10-01-12-23-14-03", "T": "00-20|10-14", "U": "00-03-14-23-20",
    "V": "00-14-20", "W": "00-04-12-24-20", "X": "00-24|20-04", "Y": "00-12-20|12-14", "Z": "00-20-04-24",
    "0": "10-01-03-14-23-21-10|03-21", "1": "01-10-14|04-24", "2": "01-10-21-22-04-24", "3": "00-20-12-23-14-03",
    "4": "10-03-23|20-24", "5": "20-00-02-12-23-14-04", "6": "21-10-01-03-14-23-12-02", "7": "00-20-14",
    "8": "10-01-12-23-14-03-12-21-10", "9": "22-02-01-10-21-23-14-04", "-": "02-22", "+": "02-22|11-13",
    "/": "04-20", "=": "01-21|03-23", ":": "11-11|13-13", ".": "14-14", "%": "00-11|04-20|13-24",
    "<": "20-02-24", ">": "00-22-04", "(": "10-01-03-14", ")": "10-21-23-14", "|": "10-14", "_": "04-24",
    "'": "10-11", "*": "01-23|21-03|10-14",
}


def text(s: str, x: float, y: float, h: float, *, anchor: str = "left") -> list[np.ndarray]:
    """Polylines of `s` with cap height h, baseline-top at y (y down)."""
    u = h / 4.0
    adv = 3.0 * u
    s = str(s).upper()
    w = max(len(s) * adv - u, 0.0)
    if anchor == "right":
        x -= w
    elif anchor == "centre":
        x -= w / 2
    out = []
    for i, c in enumerate(s):
        g = _GLYPHS.get(c)
        if not g:
            continue
        ox = x + i * adv
        for stroke in g.split("|"):
            pts = [(ox + int(p[0]) * u, y + int(p[1]) * u) for p in stroke.split("-")]
            if len(pts) == 2 and pts[0] == pts[1]:          # a dot: a tiny tick
                pts = [pts[0], (pts[0][0], pts[0][1] - 0.35 * u)]
            out.append(np.array(pts, float))
    return out


def text_width(s: str, h: float) -> float:
    return max(len(str(s)) * 0.75 * h - 0.25 * h, 0.0)


def short(name: str) -> str:
    name = str(name)
    if name.startswith("machine:"):
        return "M." + name.split(":", 1)[1][:4]
    return name[:4]


def num(v: float, nd: int = 2) -> str:
    if abs(v) >= 100:
        return f"{v:.0f}"
    return f"{v:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{v:.0f}"


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------

def measure(marks, *, step: float | None = None) -> dict:
    """Concatenated arc-length samples of every mark with κ, θ and channels."""
    live = [m for m in marks if len(m) >= 3 and m.length() > 0]
    if not live:
        return {"L": 0.0}
    Ltot = sum(m.length() for m in live)
    h = step or max(Ltot / 4000.0, 0.15)
    S, Pts, TH, K, V, MA, R, DT, MID = [], [], [], [], [], [], [], [], []
    off = 0.0
    voices = list(live[0].meta.get("voices", ["line"]))
    for mi, m in enumerate(live):
        q = m.resampled(h)
        p = q.points
        d = np.diff(p, axis=0)
        th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
        th = np.r_[th, th[-1:]]
        k = gaussian_filter1d(np.gradient(th) / h, 1.5, mode="nearest")
        s = q.arclength()
        S.append(s + off); Pts.append(p); TH.append(th); K.append(k)
        V.append(q.channels.get("voice", np.zeros(len(q))))
        MA.append(q.channels.get("machine", np.zeros(len(q))))
        R.append(q.channels["r"])
        DT.append(q.channels.get("dance_t", np.full(len(q), np.nan)))
        MID.append(np.full(len(q), mi))
        off += float(s[-1])
        for v in m.meta.get("voices", []):
            if v not in voices:
                voices.append(v)
    out = {"s": np.concatenate(S), "p": np.vstack(Pts), "theta": np.concatenate(TH), "kappa": np.concatenate(K),
           "voice": np.concatenate(V), "machine": np.concatenate(MA), "r": np.concatenate(R),
           "dance_t": np.concatenate(DT), "mark": np.concatenate(MID), "L": off, "h": h, "voices": voices,
           "machines": sorted({g for m in live for g in m.meta.get("machines", [])}, key=GRAMMARS.index),
           "R": float(np.hypot(*np.ptp(np.vstack(Pts), axis=0)))}
    return out


def runs(v: np.ndarray) -> list[tuple[int, int, float]]:
    """(i0, i1, value) runs of equal values."""
    if len(v) == 0:
        return []
    cut = np.flatnonzero(np.diff(v) != 0) + 1
    edges = np.r_[0, cut, len(v)]
    return [(int(a), int(b), float(v[a])) for a, b in zip(edges[:-1], edges[1:])]


def _nice(x: float) -> float:
    e = 10 ** math.floor(math.log10(max(x, 1e-12)))
    for m in (1, 2, 5, 10):
        if m * e >= x:
            return m * e
    return 10 * e


# ---------------------------------------------------------------------------
# charts — each returns polylines (mm) inside box (x0, y0, w, h)
# ---------------------------------------------------------------------------

def _rule(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y1]], float)


def chart_kappa(M, box, *, rows: int = 4, label_h: float = 2.2) -> list[np.ndarray]:
    x0, y0, w, h = box
    L, s, k = M["L"], M["s"], M["kappa"]
    out = []
    gut = text_width("0000", label_h) + 2.0
    xa, wa = x0 + gut, w - gut
    rh = h / rows
    kmax = max(float(np.percentile(np.abs(k), 98)), 1e-9)
    amp = 0.36 * rh
    per = L / rows
    tick = _nice(per / 8)
    vruns = runs(M["voice"])
    mruns = [r for r in runs(M["machine"]) if r[2] > 0]
    for r in range(rows):
        a, b = r * per, (r + 1) * per
        yb = y0 + (r + 0.5) * rh
        sel = (s >= a) & (s <= b)
        if sel.sum() >= 2:
            xs = xa + (s[sel] - a) / per * wa
            ys = yb - np.clip(k[sel] / kmax, -1.25, 1.25) * amp
            # split where the mark changes (no false join between marks)
            mk = M["mark"][sel]
            for i0, i1, _ in runs(mk):
                if i1 - i0 >= 2:
                    out.append(np.column_stack([xs[i0:i1], ys[i0:i1]]))
        out.append(_rule(xa, yb, xa + wa, yb))
        t = math.ceil(a / tick) * tick
        while t <= b + 1e-9:
            xt = xa + (t - a) / per * wa
            out.append(_rule(xt, yb, xt, yb + 0.12 * rh))
            t += tick
        out += text(num(a, 0), xa - 1.5, yb - label_h / 2, label_h, anchor="right")
        for i0, i1, v in vruns[1:]:
            sv = s[i0]
            if a <= sv <= b:
                xv = xa + (sv - a) / per * wa
                out.append(_rule(xv, yb - 0.46 * rh, xv, yb - 0.30 * rh))
        named = [(s[i0], s[i1 - 1], v) for i0, i1, v in vruns if s[i1 - 1] - s[i0] > 0.06 * per]
        for sa, sb, v in named:
            if a <= sa <= b:
                xv = xa + (sa - a) / per * wa
                nm = M["voices"][int(v)] if 0 <= int(v) < len(M["voices"]) else "?"
                out += text(short(nm), xv + 0.8, yb - 0.46 * rh, 0.75 * label_h)
        for i0, i1, v in mruns:
            sa, sb = max(s[i0], a), min(s[i1 - 1], b)
            if sb > sa:
                xa_, xb_ = xa + (sa - a) / per * wa, xa + (sb - a) / per * wa
                yy = yb + 0.40 * rh
                out.append(np.array([[xa_, yy - 0.06 * rh], [xa_, yy], [xb_, yy], [xb_, yy - 0.06 * rh]]))
    out += text("K(S)", x0, y0, label_h)
    return out


def chart_route(M, box, *, label_h: float = 2.2, **_) -> list[np.ndarray]:
    x0, y0, w, h = box
    voices = M["voices"]
    present = sorted({int(v) for v in np.unique(M["voice"])})
    n = max(len(present), 1)
    gut = max(text_width(short(voices[i]) if i < len(voices) else "?", label_h) for i in present) + 2.0 \
        if present else 10.0
    xa, wa = x0 + gut, w - gut
    lh = h / n
    s, L = M["s"], M["L"]
    win = max(int(round(0.04 * L / M["h"])), 3)
    out = []
    for j, vi in enumerate(present):
        yb = y0 + (j + 0.85) * lh
        share = gaussian_filter1d((M["voice"] == vi).astype(float), win, mode="nearest")
        xs = xa + s / L * wa
        ys = yb - share * 0.7 * lh
        out.append(np.column_stack([xs, ys]))
        out.append(_rule(xa, yb, xa + wa, yb))
        out.append(_rule(xa, yb - 0.7 * lh, xa + 0.015 * wa, yb - 0.7 * lh))
        nm = voices[vi] if vi < len(voices) else "?"
        out += text(short(nm), xa - 1.5, yb - 0.35 * lh - label_h / 2, label_h, anchor="right")
    return out


def chart_tempo(M, box, *, label_h: float = 2.2, **_) -> list[np.ndarray]:
    x0, y0, w, h = box
    s, L, k = M["s"], M["L"], M["kappa"]
    R = M["R"]
    ks = gaussian_filter1d(np.abs(k), max(0.006 * R / M["h"], 1.0), mode="nearest")
    lanes = [("V 2/3", (ks * R + 1.0) ** (-1.0 / 3.0))]
    if np.isfinite(M["dance_t"]).any():
        dt = np.nan_to_num(M["dance_t"], nan=0.0)
        lanes.append(("T", dt))
    if np.ptp(M["r"]) > 1e-9:
        lanes.append(("R", M["r"]))
    gut = max(text_width(nm, label_h) for nm, _ in lanes) + 2.0
    xa, wa = x0 + gut, w - gut
    lh = h / len(lanes)
    out = []
    for j, (nm, v) in enumerate(lanes):
        yb = y0 + (j + 0.9) * lh
        v = gaussian_filter1d(np.asarray(v, float), 2.0, mode="nearest")
        lo, hi = float(np.min(v)), float(np.max(v))
        ys = yb - (v - lo) / max(hi - lo, 1e-9) * 0.78 * lh
        out.append(np.column_stack([xa + s / L * wa, ys]))
        out.append(_rule(xa, yb, xa + wa, yb))
        out += text(nm, xa - 1.5, yb - 0.4 * lh - label_h / 2, label_h, anchor="right")
        out += text(num(hi), xa + wa, yb - 0.78 * lh - label_h - 0.5, 0.7 * label_h, anchor="right")
    return out


def chart_phase(M, box, *, label_h: float = 2.2, **_) -> list[np.ndarray]:
    x0, y0, w, h = box
    k = gaussian_filter1d(M["kappa"], 4.0, mode="nearest") * M["R"]
    dk = np.gradient(k) / (M["h"] / M["R"])
    dk = gaussian_filter1d(dk, 4.0, mode="nearest")
    sx = max(float(np.percentile(np.abs(k), 97)), 1e-9)
    sy = max(float(np.percentile(np.abs(dk), 97)), 1e-9)
    cx, cy = x0 + w / 2, y0 + h / 2
    half = 0.46 * min(w, h)
    X = cx + np.tanh(k / sx) * half * (w / min(w, h)) * 0.95
    Y = cy - np.tanh(dk / sy) * half
    out = []
    for i0, i1, _ in runs(M["mark"]):
        if i1 - i0 >= 2:
            out.append(np.column_stack([X[i0:i1], Y[i0:i1]]))
    out.append(_rule(x0, cy, x0 + w, cy))
    out.append(_rule(cx, y0, cx, y0 + h))
    out += text("K.R", x0 + w, cy + 1.0, label_h, anchor="right")
    out += text("DK/DS", cx + 1.0, y0, label_h)
    out += text(num(sx, 1), x0 + w, cy - label_h - 1.0, 0.7 * label_h, anchor="right")
    return out


def chart_atlas(M, box, *, label_h: float = 2.2, cells: int = 40, **_) -> list[np.ndarray]:
    x0, y0, w, h = box
    k = gaussian_filter1d(M["kappa"], 6.0, mode="nearest")
    sign = np.sign(k)
    cut = np.flatnonzero((np.diff(sign) != 0) | (np.diff(M["mark"]) != 0)) + 1
    edges = np.r_[0, cut, len(k)]
    toks = []
    minlen = 0.012 * M["L"]
    for a, b in zip(edges[:-1], edges[1:]):
        if b - a < 4 or M["s"][b - 1] - M["s"][a] < minlen:
            continue
        p = M["p"][a:b]
        turn = float(np.sum(M["kappa"][a:b]) * M["h"])
        toks.append((abs(turn), turn, p))
    if not toks:
        return []
    toks.sort(key=lambda t: t[0])
    if len(toks) > cells:
        idx = np.round(np.linspace(0, len(toks) - 1, cells)).astype(int)
        toks = [toks[i] for i in idx]
    n = len(toks)
    cols = max(int(round(math.sqrt(n * w / h))), 1)
    rows_ = -(-n // cols)
    cw, ch = w / cols, h / rows_
    norm = []
    for _, turn, p in toks:
        q = p - p[0]
        c = q[-1]
        a = math.atan2(c[1], c[0])
        R = np.array([[math.cos(-a), -math.sin(-a)], [math.sin(-a), math.cos(-a)]])
        q = q @ R.T
        norm.append((turn, q))
    ext = np.percentile([max(np.ptp(q[:, 0]), np.ptp(q[:, 1])) for _, q in norm], 90)
    out = []
    for i, (turn, q) in enumerate(norm):
        r, c = divmod(i, cols)
        cx0, cy0 = x0 + c * cw, y0 + r * ch
        sc = min(0.78 * cw, 0.62 * ch) / max(ext, 1e-9)
        sc = min(sc, 0.78 * cw / max(np.ptp(q[:, 0]), 1e-9), 0.62 * ch / max(np.ptp(q[:, 1]), 1e-9))
        mid = (q.min(axis=0) + q.max(axis=0)) / 2
        pts = (q - mid) * sc + np.array([cx0 + cw / 2, cy0 + 0.42 * ch])
        out.append(pts)
        out += text(f"{i + 1:02d} {math.degrees(turn):+.0f}", cx0 + cw / 2, cy0 + 0.80 * ch, 0.6 * label_h,
                    anchor="centre")
    return out


def chart_ledger(M, box, *, label_h: float = 2.2, **_) -> list[np.ndarray]:
    x0, y0, w, h = box
    s, L, R = M["s"], M["L"], M["R"]
    nrow = 10
    head = ["DEC", "K.R", "CORNERS/R", "MACHINE", "VOICE"]
    colx = [0.0, 0.10, 0.40, 0.68, 0.86]
    rh = h / (nrow + 1.6)
    th = min(label_h, 0.55 * rh)
    out = []
    for j, t in enumerate(head):
        out += text(t, x0 + colx[j] * w, y0, th)
    out.append(_rule(x0, y0 + 1.3 * rh, x0 + w, y0 + 1.3 * rh))
    out.append(_rule(x0, y0 + 1.3 * rh + 0.6, x0 + w, y0 + 1.3 * rh + 0.6))
    th_all = M["theta"]
    stats = []
    for d in range(nrow):
        sel = (s >= d * L / nrow) & (s < (d + 1) * L / nrow + 1e-9)
        if sel.sum() < 3:
            stats.append((0.0, 0.0, 0.0, 0))
            continue
        kr = float(np.median(np.abs(M["kappa"][sel]))) * R
        dth = np.abs(np.diff(th_all[sel]))
        win = max(int(round(0.01 * R / M["h"])), 1)
        turn = np.convolve(np.r_[dth, 0], np.ones(win), "same")
        corners = int(np.sum((turn[1:] > math.radians(40)) & (turn[:-1] <= math.radians(40))))
        cpr = corners / max((L / nrow) / R, 1e-9)
        msh = float(np.mean(M["machine"][sel] > 0))
        vals, cnt = np.unique(M["voice"][sel].astype(int), return_counts=True)
        stats.append((kr, cpr, msh, int(vals[np.argmax(cnt)])))
    kmax = max(max(st[0] for st in stats), 1e-9)
    cmax = max(max(st[1] for st in stats), 1e-9)
    for d, (kr, cpr, msh, vi) in enumerate(stats):
        yt = y0 + (1.6 + d) * rh
        yc = yt + 0.5 * th
        out += text(f"{d + 1:02d}", x0 + colx[0] * w, yt, th)
        out += text(num(kr, 1), x0 + colx[1] * w, yt, th)
        bx = x0 + (colx[1] + 0.12) * w
        out.append(_rule(bx, yc, bx + kr / kmax * 0.16 * w, yc))
        out += text(num(cpr, 0), x0 + colx[2] * w, yt, th)
        bx = x0 + (colx[2] + 0.08) * w
        out.append(_rule(bx, yc, bx + cpr / cmax * 0.18 * w, yc))
        bx = x0 + colx[3] * w
        out.append(_rule(bx, yc, bx + msh * 0.15 * w, yc))
        if msh > 0:
            out.append(_rule(bx, yc + 0.6, bx + msh * 0.15 * w, yc + 0.6))
        nm = M["voices"][vi] if 0 <= vi < len(M["voices"]) else "?"
        out += text(short(nm), x0 + colx[4] * w, yt, th)
        out.append(_rule(x0, yt + 0.95 * rh - 0.2 * rh, x0 + w, yt + 0.95 * rh - 0.2 * rh)
                   if d == nrow - 1 else np.zeros((0, 2)))
    return [p for p in out if len(p) >= 2]


CHART_FN = {"kappa": chart_kappa, "route": chart_route, "tempo": chart_tempo, "phase": chart_phase,
            "atlas": chart_atlas, "ledger": chart_ledger}


def draw_chart(kind: str, marks, box, *, rows: int = 4, label_h: float = 2.2) -> list[np.ndarray]:
    M = measure(marks)
    if M["L"] <= 0:
        return []
    kw = {"label_h": label_h}
    if kind == "kappa":
        kw["rows"] = rows
    return [np.asarray(p, float) for p in CHART_FN[kind](M, box, **kw) if len(p) >= 2]


def shadow(marks, *, measure_of: str, gap: float, gain: float) -> list[np.ndarray]:
    """A line following each mark at a normal distance gap + gain·m̂(s)."""
    M = measure(marks)
    if M["L"] <= 0:
        return []
    if measure_of == "tempo":
        v = (np.abs(M["kappa"]) * M["R"] + 0.5) ** (-1.0 / 3.0)
    elif measure_of == "route":
        v = M["voice"].astype(float)
    else:
        v = np.abs(M["kappa"])
    v = gaussian_filter1d(v, 3.0, mode="nearest")
    v = (v - v.min()) / max(np.ptp(v), 1e-9)
    out = []
    for i0, i1, _ in runs(M["mark"]):
        p = M["p"][i0:i1]
        if len(p) < 3:
            continue
        tg = np.gradient(p, axis=0)
        tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
        nrm = np.column_stack([-tg[:, 1], tg[:, 0]])
        out.append(p + nrm * (gap + gain * v[i0:i1])[:, None])
    return out


# ---------------------------------------------------------------------------
# the limb: a chart drawn by a hand
# ---------------------------------------------------------------------------

def hand_drawn(polys: list[np.ndarray], g, rng, *, amount: float, keep: float = 0.006, min_len: float = 1.5,
               straight=None) -> list[np.ndarray]:
    """Every polyline redrawn through hand g (`grammar.restyle`) in a common
    native frame (the chart's bbox diagonal ↦ 1000 px, so the hand's scale is
    shared by every line of the chart).

    straight: optional per-polyline flags (2026-10-17, Ian: "an option to
    keep some of the lines in the graph straight"). A flagged line keeps its
    machine shape; it is still restyled first and the result dropped, so the
    shared generator advances exactly as without the flag and every other
    line comes out identical. None (default) = every line hand-drawn."""
    from ._research import grammar as gm  # noqa: PLC0415
    from .voices_machine import resample  # noqa: PLC0415
    if not polys:
        return []
    allp = np.vstack(polys)
    lo = allp.min(axis=0)
    diag = float(np.hypot(*np.ptp(allp, axis=0))) or 1.0
    k = 1000.0 / diag
    R = 1000.0 / 0.9
    out = []
    for i, p in enumerate(polys):
        L = float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)))
        if L < min_len:
            out.append(p)
            continue
        q = resample((p - lo) * k, 1.0)
        if len(q) < 6:
            out.append(p)
            continue
        try:
            st = gm.restyle(q, g, rng, ref_length=R, amount=amount, coarse_frac=keep, step=1.0)
            out.append(p if straight is not None and straight[i] else st.points / k + lo)
        except Exception:  # noqa: BLE001 — a degenerate line keeps its machine shape
            out.append(p)
    return out


STRAIGHT = ("none", "rules", "text", "rules+text", "frame", "frame+text")
# "frame": only the outermost rules stay straight — the rules as long as the
# chart is wide (a ledger's top and bottom), while the rules inside it (bars,
# short ticks) are drawn by the hand (Ian, round 11: "keep the lines inside
# stylized. top and bottom straight (as option) is good").
FRAME_SHARE = 0.9          # a frame rule is at least this share of the longest rule


def chart_roles(polys: list[np.ndarray], label_h: float) -> list[str]:
    """What each chart polyline is, from its geometry alone: "rule" (one
    straight run longer than 1.25 cap heights: table rules, axes, bars,
    long ticks), "text" (a short stroke inside a 1.15 cap-height box with
    ≤ 10 points: the stroke font's glyph strokes, short ticks), "trace"
    (everything else: data curves, specimens, brackets)."""
    out = []
    for p in polys:
        p = np.asarray(p, float)
        d = np.diff(p, axis=0)
        L = float(np.sum(np.linalg.norm(d, axis=1)))
        chord = float(np.linalg.norm(p[-1] - p[0])) if len(p) >= 2 else 0.0
        ext = float(np.max(np.ptp(p, axis=0))) if len(p) else 0.0
        if len(p) >= 2 and L > 1.25 * label_h and chord >= L * (1 - 1e-9):
            out.append("rule")
        elif len(p) <= 10 and ext <= 1.15 * label_h:
            out.append("text")
        else:
            out.append("trace")
    return out


def straight_flags(polys: list[np.ndarray], label_h: float, keep_straight: str, share: float, rng) -> list[bool] | None:
    """Per-polyline flags for `hand_drawn(straight=...)`: the roles named by
    `keep_straight` ("rules", "text", "rules+text", "frame", "frame+text";
    "none"), plus a `share`
    of the remaining lines drawn from `rng` (its own stream, so the hand's
    generator is untouched). None when nothing stays straight (= the
    original output, bit for bit)."""
    if keep_straight == "none" and share <= 0:
        return None
    roles = chart_roles(polys, label_h)
    if keep_straight.startswith("frame"):
        lens = [float(np.sum(np.linalg.norm(np.diff(np.asarray(p, float), axis=0), axis=1))) if r == "rule" else 0.0
                for p, r in zip(polys, roles)]
        top = max(lens, default=0.0)
        roles = ["frame" if r == "rule" and top > 0 and ln >= FRAME_SHARE * top else r
                 for r, ln in zip(roles, lens)]
    keep = {"none": set(), "rules": {"rule"}, "text": {"text"}, "rules+text": {"rule", "text"},
            "frame": {"frame"}, "frame+text": {"frame", "text"}}[keep_straight]
    u = rng.random(len(polys))
    return [r in keep or (share > 0 and bool(ui < share)) for r, ui in zip(roles, u)]


def _chart_marks(polys, template_channels, kind, drawn_by) -> list[Mark]:
    """Chart polylines as Marks carrying every channel of the drawing (dry)."""
    out = []
    for p in polys:
        n = len(p)
        ch = {c: np.zeros(n) for c in template_channels}
        ch.update({"r": np.zeros(n), "voice": np.zeros(n), "machine": np.zeros(n)})
        for c in ("phi", "W", "M"):
            ch.pop(c, None)
        out.append(Mark(p, ch, {"diagram": kind, "voices": [f"diagram:{kind}"], "drawn_by": drawn_by}))
    return out


_CHART_PARAMS = [
    P("chart", "choice", "kappa", "what is measured and drawn", choices=CHARTS),
    P("rows", "int", 4, "kappa: seismograph rows", min=1, max=12),
    P("label_h", "float", 2.2, "label cap height, mm", min=0.8, max=8.0),
    P("drawn_by", "ref", None, "redraw the chart through this hand (null = the machine draws it)", kind="hand",
      optional=True),
    P("amount", "float", 1.5, "how much fine turning the hand owns (restyle amount)", min=0.0, max=3.0),
    P("keep", "float", 0.006, "drawn_by: the chart shape the hand must keep — the coarse scale as a share of "
      "each line's length (small = faithful, 0.04 = the hand reinterprets)", min=0.001, max=0.2),
]


@voice("diagram", params=[
    *_CHART_PARAMS,
    P("hands", "refs", ["matisse", "shikasta", "lichtenberg"], "the measured line's route", kind="hand",
      min_len=1, max_len=6),
    P("length", "float", 6.0, "measured line length in reference lengths", min=0.2, max=12.0),
    P("joins", "choice", "smooth", "drift joins", choices=("smooth", "chain")),
    P("of_part", "int", None, "measure the line grown at this part's seed (sheet seed + n), so the chart "
      "describes a neighbour part's voice line", min=0, max=999, optional=True),
    P("machine_a", "choice", "none", "hand stretches of the measured line to this machine first",
      choices=(*GRAMMARS, "none")),
    P("machine_b", "choice", "none", "…and alternate with this one", choices=(*GRAMMARS, "none")),
    P("share", "float", 0.35, "machine share", min=0.0, max=0.95),
    P("aspect", "float", None, "draw the chart in a w/h box of this aspect centred in the part's box (null = "
      "the whole box; set it when a grid cell's shape differs from the frame's)", min=0.1, max=20.0,
      optional=True),
], doc="the system's measurement of a line, drawn as a chart (a piece in itself)")
def diagram(ctx, *, chart: str, rows, label_h, drawn_by, amount, keep, hands, length, joins, of_part,
            machine_a, machine_b, share, aspect):
    gctx = ctx if of_part is None else replace(ctx, seed=int(ctx.sheet_seed) + int(of_part))
    pts, ch, meta = grow(gctx, list(hands), length=length, blend="mixture", joins=joins, plateau=0.12)
    m = Mark(pts, ch, meta)
    grammars = [g for g in (machine_a, machine_b) if g != "none"]
    if grammars and share > 0:
        diag = float(np.hypot(*np.ptp(pts, axis=0)))
        rng = ctx.rng("handover")
        iv = choose_stretches(m, rng, share=share, stretch=0.06 * m.length(), at="seams")
        m = hand_over(m, iv, grammars, rng, 0.02 * diag, _opts(5, 72.0, "L=LSR,R=RRS,S=SL", 2, 0.25))
    box = ctx.box
    if aspect is not None:
        x0, y0, w, h = box
        w2, h2 = (w, w / aspect) if w / h < aspect else (h * aspect, h)
        box = (x0 + (w - w2) / 2, y0 + (h - h2) / 2, w2, h2)
    polys = draw_chart(chart, [m], box, rows=rows, label_h=label_h)
    if drawn_by:
        polys = hand_drawn(polys, ctx.use("hand", drawn_by), ctx.rng("drawn_by", drawn_by), amount=amount, keep=keep)
    marks = _chart_marks(polys, [], chart, drawn_by)
    return [mk.evolve(meta={"measured": list(hands)}) for mk in marks]


def _annotate_reach(p):
    """A shadow line sits up to gap + gain from the centreline."""
    return p["gap"] + p["gain"] if p["layout"] == "shadow" else 0.0


@modulator("annotate", params=[
    *_CHART_PARAMS,
    P("layout", "choice", "below", "below / right: the drawing is refit into the rest of the box; shadow: a "
      "second line follows the drawing at a distance = the measurement", choices=("below", "right", "shadow")),
    P("split", "float", 0.36, "share of the box the chart takes (below / right)", min=0.1, max=0.8),
    P("gap", "float", 1.5, "shadow: base distance, mm", min=0.0, max=30.0),
    P("gain", "float", 5.0, "shadow: extra distance at the measurement's max, mm", min=0.0, max=60.0),
], doc="the measurement of the marks so far, drawn beside them (or shadowing them)", reach=_annotate_reach)
def annotate(ctx, marks, *, chart, rows, label_h, drawn_by, amount, keep, layout, split, gap, gain):
    from .core import refit  # noqa: PLC0415
    live = [m for m in marks if len(m) >= 2]
    if not live:
        return list(marks)
    template = sorted(set.intersection(*(set(m.channels) for m in marks)))
    x0, y0, w, h = ctx.box
    if layout == "shadow":
        polys = shadow(marks, measure_of=chart if chart in ("tempo", "route") else "kappa", gap=gap, gain=gain)
        drawing = list(marks)
    else:
        pad = 0.04 * (h if layout == "below" else w)
        if layout == "below":
            dbox = (x0, y0, w, h * (1 - split) - pad / 2)
            cbox = (x0, y0 + h * (1 - split) + pad / 2, w, h * split - pad / 2)
        else:
            dbox = (x0, y0, w * (1 - split) - pad / 2, h)
            cbox = (x0 + w * (1 - split) + pad / 2, y0, w * split - pad / 2, h)
        drawing = refit(list(marks), dbox)
        polys = draw_chart(chart, drawing, cbox, rows=rows, label_h=label_h)
    if drawn_by:
        polys = hand_drawn(polys, ctx.use("hand", drawn_by), ctx.rng("drawn_by", drawn_by), amount=amount, keep=keep)
    extra = _chart_marks(polys, template, chart if layout != "shadow" else f"shadow:{chart}", drawn_by)
    part = marks[0].meta.get("part")
    extra = [m.evolve(meta={"part": part, "voice_id": "annotate"}) for m in extra]
    return drawing + extra
