"""oehlen_intuit: small drawing toolbox for the intuition-steered session.

Lines are lists of (N, 2) arrays in sheet mm, y down. `show` renders ink on
Flexoki paper at each line's pen width and writes a params JSON beside the
image so every working image can be rebuilt. No randomness here; every
random draw in the session uses np.random.default_rng(<recorded seed>).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(".local/gesture/out/oehlen_intuit")
PAPER = (0xFF, 0xFC, 0xF0)
INK = (0x10, 0x0F, 0x0F)


def arr(pts):
    return np.asarray(pts, float).reshape(-1, 2)


def show(lines, frame, name, *, pens=None, px_per_mm=6.0, params=None, colors=None):
    """lines: list of arrays; pens: list of pen widths (mm) or one float."""
    W, H = frame
    ss = 2
    s = px_per_mm * ss
    im = Image.new("RGB", (int(W * s), int(H * s)), PAPER)
    d = ImageDraw.Draw(im)
    if pens is None or isinstance(pens, (int, float)):
        pens = [pens or 0.4] * len(lines)
    for i, (ln, pen) in enumerate(zip(lines, pens)):
        ln = arr(ln)
        if len(ln) < 2:
            continue
        col = INK if colors is None else colors[i]
        w = max(1, int(round(pen * s)))
        d.line([tuple(p) for p in (ln * s)], fill=col, width=w, joint="curve")
        r = w / 2
        for p in (ln[0] * s, ln[-1] * s):
            d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=col)
    im = im.resize((int(W * px_per_mm), int(H * px_per_mm)), Image.LANCZOS)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.jpg"
    im.save(path, quality=90)
    meta = {"frame": list(frame), "n_lines": len(lines), "pens": list(map(float, pens)),
            "params": params or {},
            "lines_mm": [np.round(arr(l), 3).tolist() for l in lines]}
    (OUT / f"{name}.params.json").write_text(json.dumps(meta))
    return path


def fit(pts, box):
    """Uniformly scale points (any units) into box (x0, y0, w, h), centred."""
    p = arr(pts)
    lo, hi = p.min(0), p.max(0)
    span = np.maximum(hi - lo, 1e-9)
    k = min(box[2] / span[0], box[3] / span[1])
    c = (lo + hi) / 2
    return (p - c) * k + np.array([box[0] + box[2] / 2, box[1] + box[3] / 2])


def resample(p, step):
    p = arr(p)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] == 0:
        return p
    n = max(2, int(s[-1] / step) + 1)
    t = np.linspace(0, s[-1], n)
    return np.c_[np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])]


def length(p):
    p = arr(p)
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


def chaikin(p, n=3):
    p = arr(p)
    for _ in range(n):
        q = 0.75 * p[:-1] + 0.25 * p[1:]
        r = 0.25 * p[:-1] + 0.75 * p[1:]
        p = np.vstack([p[:1], np.c_[q, r].reshape(-1, 2), p[-1:]])
    return p


_STORK = None


def stork(individual="Oduella"):
    """One stork's fixes as local metres (equirectangular), in time order."""
    global _STORK
    import csv
    if _STORK is None:
        _STORK = {}
        with open(".local/gesture/corpus/animal/movebank-lifetrack-stork-sicily/stork-gps.csv") as f:
            for d in csv.DictReader(f):
                if d["location-long"] and d["location-lat"]:
                    _STORK.setdefault(d["individual-local-identifier"].split()[0], []).append(
                        (d["timestamp"], float(d["location-long"]), float(d["location-lat"])))
        for k in _STORK:
            _STORK[k].sort()
    xs = _STORK[individual]
    lon = np.array([x[1] for x in xs]); lat = np.array([x[2] for x in xs])
    k = np.cos(np.radians(lat.mean()))
    return np.c_[(lon - lon[0]) * 111320 * k, -(lat - lat[0]) * 110540]


def clip(lines, frame, inset=0.0):
    """Cut polylines at the frame rectangle (inset mm); returns the inside runs."""
    from shapely.geometry import LineString, box as sbox
    W, H = frame
    B = sbox(inset, inset, W - inset, H - inset)
    out, keep = [], []
    for k, ln in enumerate(lines):
        ln = arr(ln)
        if len(ln) < 2:
            continue
        g = LineString(ln).intersection(B)
        parts = [g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))
        for q in parts:
            if q.geom_type == "LineString" and q.length > 0.5:
                out.append(np.asarray(q.coords))
                keep.append(k)
    return out, keep


def shp_polylines(path):
    """Minimal ESRI .shp reader for PolyLine records (type 3); returns list of (N, 2) arrays."""
    import struct
    b = Path(path).read_bytes()
    out, i = [], 100
    while i + 8 <= len(b):
        _, clen = struct.unpack(">ii", b[i:i + 8])
        rec = b[i + 8:i + 8 + clen * 2]
        i += 8 + clen * 2
        st = struct.unpack("<i", rec[:4])[0]
        if st not in (3, 13, 23):
            continue
        nparts, npts = struct.unpack("<ii", rec[36:44])
        parts = struct.unpack(f"<{nparts}i", rec[44:44 + 4 * nparts])
        o = 44 + 4 * nparts
        pts = np.frombuffer(rec[o:o + 16 * npts], dtype="<f8").reshape(-1, 2)
        bounds = list(parts) + [npts]
        for a, c in zip(bounds[:-1], bounds[1:]):
            out.append(pts[a:c].copy())
    return out


def river_cl(name="Rio_Curuca/Rio_Curuca/centerline_csv/Rio_Curuca_2020_centerline.csv"):
    """A Greenberg-Ganti single-river centreline (30 m pixel steps), metres, y down."""
    import csv
    import io
    import zipfile
    z = zipfile.ZipFile(".local/gesture/corpus/earth/greenberg-ganti-single-rivers/Single_Rivers.zip")
    rows = list(csv.DictReader(io.StringIO(z.read("Single_Rivers/" + name).decode())))
    p = np.array([(float(r["easting"]), -float(r["northing"])) for r in rows])
    return p


def pixelate(p, cell, origin=(0.0, 0.0)):
    """Cheap-mouse version of a line: snap to a grid of `cell` mm and walk it in
    4-connected unit steps (a staircase); consecutive duplicates dropped."""
    p = resample(p, cell / 4)
    o = np.asarray(origin, float)
    g = np.round((p - o) / cell).astype(int)
    out = [g[0]]
    for q in g[1:]:
        cur = out[-1].copy()
        while (cur != q).any():
            d = q - cur
            k = 0 if abs(d[0]) >= abs(d[1]) else 1
            cur = cur.copy(); cur[k] += np.sign(d[k])
            out.append(cur)
    g = np.array(out)
    keep = [0] + [i for i in range(1, len(g) - 1)
                  if not ((g[i] - g[i - 1]) == (g[i + 1] - g[i])).all()] + [len(g) - 1]
    return g[keep] * cell + o


def trim_inside(lines, frame, inset=6.0):
    """Instead of cutting at the frame (which lines every cut up on one edge),
    break each line at its vertices that leave the frame: runs end at their
    last inside vertex, so they stop in the air at uneven distances."""
    W, H = frame
    out, keep = [], []
    for k, ln in enumerate(lines):
        ln = arr(ln)
        ok = (ln[:, 0] >= inset) & (ln[:, 0] <= W - inset) & (ln[:, 1] >= inset) & (ln[:, 1] <= H - inset)
        run = []
        for p, o in zip(ln, ok):
            if o:
                run.append(p)
            else:
                if len(run) >= 2:
                    out.append(np.array(run)); keep.append(k)
                run = []
        if len(run) >= 2:
            out.append(np.array(run)); keep.append(k)
    return out, keep


def ragged_clip(lines, frame, inset, rng, pull=(3.0, 25.0)):
    """Cut at the frame, then pull every cut end back along its line by a random
    amount, so lines that leave the sheet stop in the air at uneven places and
    no edge is drawn by the cuts. Ends that were inside are untouched."""
    W, H = frame
    cl, keep = clip(lines, frame, inset)
    out, k2 = [], []
    for ln, k in zip(cl, keep):
        def on_edge(p):
            return min(p[0] - inset, W - inset - p[0], p[1] - inset, H - inset - p[1]) < 1e-6
        p = resample(ln, 0.25)
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
        a, b = 0.0, s[-1]
        if on_edge(ln[0]):
            a = float(rng.uniform(*pull))
        if on_edge(ln[-1]):
            b = s[-1] - float(rng.uniform(*pull))
        if b - a < 2.0:
            continue
        m = (s >= a) & (s <= b)
        q = ln if (a == 0 and b == s[-1]) else p[m]
        out.append(q); k2.append(k)
    return out, k2


def self_cross_params(p):
    """Arc-length positions along polyline p of every point where it crosses itself."""
    p = arr(p)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s0 = np.concatenate([[0], np.cumsum(seg)])
    A, B = p[:-1], p[1:]
    out = []
    n = len(A)
    for i in range(n):
        a, b = A[i], B[i]
        c, d = A[i + 2:], B[i + 2:]
        if len(c) == 0:
            continue
        r = b - a
        q = d - c
        den = r[0] * q[:, 1] - r[1] * q[:, 0]
        ok = np.abs(den) > 1e-12
        w = c - a
        t = np.where(ok, (w[:, 0] * q[:, 1] - w[:, 1] * q[:, 0]) / np.where(ok, den, 1), -1)
        u = np.where(ok, (w[:, 0] * r[1] - w[:, 1] * r[0]) / np.where(ok, den, 1), -1)
        hit = ok & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
        for j in np.nonzero(hit)[0]:
            out.append(s0[i] + t[j] * seg[i])
            out.append(s0[i + 2 + j] + u[j] * seg[i + 2 + j])
    return np.sort(np.array(out)), s0


def drop_short_between_crossings(p, tau):
    """Split p at its self-crossings; pieces shorter than tau are lifted (not drawn);
    consecutive surviving pieces stay one contiguous line."""
    p = arr(p)
    cuts, s0 = self_cross_params(p)
    bounds = np.concatenate([[0.0], cuts, [s0[-1]]])
    keep = np.diff(bounds) >= tau
    q = resample(p, 0.2)
    sq = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
    sq *= s0[-1] / max(sq[-1], 1e-9)
    piece = np.clip(np.searchsorted(bounds, sq, side="right") - 1, 0, len(keep) - 1)
    m = keep[piece]
    runs, cur = [], []
    for pt, o in zip(q, m):
        if o:
            cur.append(pt)
        else:
            if len(cur) > 1:
                runs.append(np.array(cur))
            cur = []
    if len(cur) > 1:
        runs.append(np.array(cur))
    return runs
