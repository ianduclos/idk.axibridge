"""oehlen_intuit: the finished sheet of an intuition-steered session (round 12).

Not a general technique: a replay. The session (log in
results/oehlen_intuit-2026-10-17.md, steps in experiments/oehlen_intuit_session.py)
made one drawing by feel; this voice rebuilds it from its frozen sources
(library typed_drawing/oehlen_intuit_sheet1) so it can be rerun, varied on the
few knobs the session actually turned, and kept as a study.

What it does, in session order (300 x 200 mm work frame, the machine's own
landscape; the sheet is seen turned, 200 x 300 portrait):
  - four polylines typed blind as numbers; the long one is smoothed (Chaikin x4)
    into a swoosh — the "wrong", too-competent thing the rest fights;
  - a stork's GPS window (300 fixes at the nest) scaled so 80 % of fixes lie
    within 22 mm, dropped in a dumb place on the typed horizon;
  - everything cut at the frame; cut ends pulled back 3–25 mm so lines stop
    in the air (no edge drawn by the cuts); the swoosh keeps its split at its
    own crossing (a clipping accident the session kept);
  - the first `fat_to` of each swoosh piece redrawn in a fat pen as a cheap-mouse
    pixel staircase (`cell` mm);
  - the knot split at its own crossings; pieces shorter than `tau` lifted: the
    hole is where the bird crossed itself most;
  - the last swoosh piece stops short; the feeler comes back in a second colour.

Marks carry meta["pen"] (mm), meta["colour"] (hex) and meta["role"]; the
renderer `oehlen_intuit_pens` inks them one wire per mark at that pen.
"""
from __future__ import annotations

import gzip
import json

import numpy as np

from . import library as L
from .core import Ink, Mark, P, renderer, voice

KIND = "typed_drawing"
WORK = (300.0, 200.0)
INSET = 4.0
BLACK = "#100F0F"
COLOURS = {"red": "#D14D41", "blue": "#4385BE", "black": BLACK}   # flexoki red-400 / blue-400 / black


@L.loader(KIND)
def _load(entry: dict, folder):
    return json.loads(gzip.decompress((folder / entry["files"]["lines"]).read_bytes()))


# ---------------------------------------------------------------- geometry helpers (private)

def _arr(p):
    return np.asarray(p, float).reshape(-1, 2)


def _resample(p, step):
    p = _arr(p)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    if s[-1] == 0:
        return p
    t = np.linspace(0, s[-1], max(2, int(s[-1] / step) + 1))
    return np.c_[np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])]


def _length(p):
    p = _arr(p)
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()) if len(p) > 1 else 0.0


def _chaikin(p, n):
    p = _arr(p)
    for _ in range(n):
        q = 0.75 * p[:-1] + 0.25 * p[1:]
        r = 0.25 * p[:-1] + 0.75 * p[1:]
        p = np.vstack([p[:1], np.c_[q, r].reshape(-1, 2), p[-1:]])
    return p


def _stretch(p, a, b):
    p = _resample(p, 0.5)
    n = len(p)
    return p[int(a * n):int(b * n)]


def _clip(line, frame, inset):
    from shapely.geometry import LineString, box as sbox  # noqa: PLC0415
    W, H = frame
    g = LineString(_arr(line)).intersection(sbox(inset, inset, W - inset, H - inset))
    parts = [g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))
    return [np.asarray(q.coords) for q in parts if q.geom_type == "LineString" and q.length > 0.5]


def _ragged(line, frame, inset, rng, pull=(3.0, 25.0)):
    W, H = frame
    out = []
    for ln in _clip(line, frame, inset):
        def edge(p):
            return min(p[0] - inset, W - inset - p[0], p[1] - inset, H - inset - p[1]) < 1e-6
        p = _resample(ln, 0.25)
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
        a, b = 0.0, s[-1]
        if edge(ln[0]):
            a = float(rng.uniform(*pull))
        if edge(ln[-1]):
            b = s[-1] - float(rng.uniform(*pull))
        if b - a < 2.0:
            continue
        out.append(ln if (a == 0 and b == s[-1]) else p[(s >= a) & (s <= b)])
    return out


def _pixelate(p, cell):
    p = _resample(p, cell / 4)
    g = np.round(p / cell).astype(int)
    out = [g[0]]
    for q in g[1:]:
        cur = out[-1].copy()
        while (cur != q).any():
            d = q - cur
            k = 0 if abs(d[0]) >= abs(d[1]) else 1
            cur = cur.copy()
            cur[k] += np.sign(d[k])
            out.append(cur)
    g = np.array(out)
    keep = [0] + [i for i in range(1, len(g) - 1) if not ((g[i] - g[i - 1]) == (g[i + 1] - g[i])).all()] + [len(g) - 1]
    return g[keep] * float(cell)


def _crossings(p):
    p = _arr(p)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s0 = np.concatenate([[0], np.cumsum(seg)])
    A, B = p[:-1], p[1:]
    out = []
    for i in range(len(A)):
        c, d = A[i + 2:], B[i + 2:]
        if len(c) == 0:
            continue
        r = B[i] - A[i]
        q = d - c
        den = r[0] * q[:, 1] - r[1] * q[:, 0]
        ok = np.abs(den) > 1e-12
        w = c - A[i]
        dd = np.where(ok, den, 1.0)
        t = np.where(ok, (w[:, 0] * q[:, 1] - w[:, 1] * q[:, 0]) / dd, -1)
        u = np.where(ok, (w[:, 0] * r[1] - w[:, 1] * r[0]) / dd, -1)
        for j in np.nonzero(ok & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1))[0]:
            out += [s0[i] + t[j] * seg[i], s0[i + 2 + j] + u[j] * seg[i + 2 + j]]
    return np.sort(np.array(out)), s0


def _hollow(p, tau, min_run=1.5):
    """Split at self-crossings, lift pieces shorter than tau, keep survivors joined."""
    cuts, s0 = _crossings(p)
    bounds = np.concatenate([[0.0], cuts, [s0[-1]]])
    keep = np.diff(bounds) >= tau
    q = _resample(p, 0.2)
    sq = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
    sq *= s0[-1] / max(sq[-1], 1e-9)
    m = keep[np.clip(np.searchsorted(bounds, sq, side="right") - 1, 0, len(keep) - 1)]
    runs, cur = [], []
    for pt, o in zip(q, m):
        if o:
            cur.append(pt)
        else:
            if len(cur) > 1 and _length(cur) >= min_run:
                runs.append(np.array(cur))
            cur = []
    if len(cur) > 1 and _length(cur) >= min_run:
        runs.append(np.array(cur))
    return runs


def _knot(data):
    Pm = _arr(data["knot_m"])
    c = np.median(Pm, axis=0)
    q = np.percentile(np.linalg.norm(Pm - c, axis=1), 80)
    kp = data["knot_place"]
    return (Pm - c) * (kp["inner80_radius_mm"] / q) + np.asarray(kp["centre_mm"], float)


def sheet_lines(data, *, tau, cell, fat_to, stop_short, feeler, stub, colour, rng_for):
    """The drawing in the work frame (300 x 200): list of (points, pen, colour, role)."""
    t = data["typed"]
    out = []
    # the swoosh: clipped (keeps its split at its own crossing), fat pixel stretch on each piece
    parts = _clip(_chaikin(t["swoosh"], 4), WORK, INSET)
    if stop_short < 1.0 and parts:
        parts[-1] = _stretch(parts[-1], 0.0, stop_short)
    for q in parts:
        out.append((q, 0.3, BLACK, "swoosh"))
        out.append((_pixelate(_stretch(q, 0.0, fat_to), cell), 1.6, BLACK, "fat"))
    for q in _ragged(t["horizon"], WORK, INSET, rng_for("horizon")):
        out.append((q, 0.4, BLACK, "horizon"))
    if stub:
        for q in _ragged(t["stub"], WORK, INSET, rng_for("stub")):
            out.append((q, 0.4, BLACK, "stub"))
    rk = rng_for("knot")
    for r in _hollow(_knot(data), tau):
        for q in _ragged(r, WORK, INSET, rk):
            out.append((q, 0.3, BLACK, "knot"))
    if feeler:
        for q in _ragged(t["feeler"], WORK, INSET, rng_for("feeler")):
            out.append((q, 0.5, COLOURS[colour], "feeler"))
    return out


@voice("oehlen_intuit_sheet",
       params=[P("drawing", "ref", "oehlen_intuit_sheet1", "frozen session sources", kind=KIND),
               P("tau", "float", 2.0, "knot: pieces between its own crossings shorter than this (mm) are lifted",
                 min=0.0, max=6.0),
               P("cell", "float", 3.0, "pixel cell of the fat stretch, mm", min=1.0, max=8.0),
               P("fat_to", "float", 0.33, "fat pixel stretch covers this share of each swoosh piece",
                 min=0.0, max=0.8),
               P("stop_short", "float", 0.62, "share of the last swoosh piece that is drawn", min=0.2, max=1.0),
               P("feeler", "bool", True, "the typed feeler, in a second colour"),
               P("stub", "bool", False, "the short typed stub (dropped in the session)"),
               P("colour", "choice", "red", "feeler pen colour", choices=("red", "blue", "black")),
               P("turn", "bool", True, "turn the work frame 90° cw (drawn landscape, seen portrait)")],
       doc="replay of the oehlen_intuit session's finished sheet: typed lines, a stork's nest, a pixel stretch")
def oehlen_intuit_sheet(ctx, *, drawing, tau, cell, fat_to, stop_short, feeler, stub, colour, turn):
    data = ctx.use(KIND, drawing)
    items = sheet_lines(data, tau=tau, cell=cell, fat_to=fat_to, stop_short=stop_short, feeler=feeler,
                        stub=stub, colour=colour, rng_for=lambda tag: ctx.rng("ragged", tag))
    W, H = WORK
    if turn:
        items = [(np.c_[H - q[:, 1], q[:, 0]], pen, c, role) for q, pen, c, role in items]
        W, H = H, W
    x0, y0, w, h = ctx.box
    s = min(w / W, h / H)
    off = np.array([x0 + (w - W * s) / 2, y0 + (h - H * s) / 2])
    return [Mark(q * s + off, {}, {"pen": float(pen), "colour": c, "role": role,
                                   "fit": {"scale": float(s), "offset": [float(off[0]), float(off[1])]}})
            for q, pen, c, role in items if len(q) >= 2]


@renderer("oehlen_intuit_pens", params=[], reach=lambda p: 0.8,
          doc="one wire per mark at its meta['pen'], colour in Ink.meta['colour']")
def oehlen_intuit_pens(ctx, marks):
    return [Ink(m.points, closed=False, filled=False, pen=float(m.meta.get("pen", 0.4)),
                meta={"colour": m.meta.get("colour", BLACK), "role": m.meta.get("role", "")}) for m in marks]
