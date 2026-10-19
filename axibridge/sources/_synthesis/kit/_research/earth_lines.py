# FROZEN from research commit 071aea1: tools/gesture/gesture/earth_lines.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Earth and physics lines as structures, and regime fields born from their data.

docs/research/gesture-corpus/earth-physics-lines.md (sources, recipe);
results/earth_lines-2026-10-16.md (what came out).

Sources → `Drawing` (README contract: px points, full width per point):

  grwl_window(tile, bbox_lonlat)   Amazon centrelines from the GRWL vector
                                   tiles, WIDTH PER VERTEX in metres scaled to
                                   px; segments become strokes, junctions are
                                   re-snapped so the network stays connected.
  scan_structure(path, invert=...) Lichtenberg figures, bubble-chamber
                                   frames, lightning, slime trails through
                                   the default extractor (`extract_hybrid`),
                                   bright-on-dark scans inverted.
  with_hosts(drawing)              host meta ("host" = stroke it branches
                                   from) from endpoint contacts, so the
                                   preset Strahler/trunk fields of
                                   `regime_field` work on these structures
                                   (the fair comparison).

Data-born regime fields (all `regime_field.Field`, r ∈ [0, 2]):

  data_field(drawing, values, ...)  generic: per-POINT data values are
                                    looked up at the nearest structure point
                                    (KD-tree), mapped through quantile
                                    levels to line / nib / mass and faded to
                                    `background` away from the structure.
  width_values(drawing)             channel width (rivers) / ink width
                                    (scans).
  curl_values(drawing)              |κ| per point at an explicit smoothing
                                    scale, so a slowing particle's
                                    tightening spiral pools to mass
                                    (bubble chamber "energy loss").
  order_values(drawing)             per-point Strahler order from hosts
                                    (a data reading of branching, for
                                    comparison with the preset).

Shapefile / DBF are parsed by hand (no pyshp/GDAL in the research venv):
`read_shp_polylines`, `read_dbf`.

Pure and deterministic: inputs never mutated.
"""
from __future__ import annotations

import math
import struct
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

from .core import Drawing, Stroke

REPO = Path(__file__).resolve().parents[3]
EARTH = REPO / ".local/gesture/corpus/earth"
R_EARTH = 6371008.8


# ---------------------------------------------------------------------------
# shapefile + dbf (by hand)
# ---------------------------------------------------------------------------

def read_shp_polylines(path) -> list[np.ndarray]:
    """Every record of a polyline (type 3) shapefile as one (N, 2) array of
    (x, y) = (lon, lat) for GCS files. One array per record, so the list
    index equals the `read_dbf` row. Multi-part records keep their first
    part (none seen in GRWL)."""
    buf = Path(path).read_bytes()
    shp_type = struct.unpack("<i", buf[32:36])[0]
    if shp_type not in (3, 13, 23):
        raise ValueError(f"not a polyline shapefile (type {shp_type})")
    out: list[np.ndarray] = []
    i = 100
    n = len(buf)
    while i + 8 <= n:
        clen = struct.unpack(">i", buf[i + 4:i + 8])[0] * 2
        rec = i + 8
        st = struct.unpack("<i", buf[rec:rec + 4])[0]
        if st == 0:
            out.append(np.zeros((0, 2)))
        else:
            nparts, npts = struct.unpack("<ii", buf[rec + 36:rec + 44])
            parts = np.frombuffer(buf, "<i4", nparts, rec + 44)
            pts = np.frombuffer(buf, "<f8", 2 * npts, rec + 44 + 4 * nparts).reshape(-1, 2)
            end = parts[1] if nparts > 1 else npts
            out.append(np.array(pts[parts[0]:end], dtype=np.float64))
        i = rec + clen
    return out


def read_dbf(path, fields=None) -> dict[str, np.ndarray]:
    """dBASE III table → {field: float array} for numeric (N/F) fields
    (others as bytes). `fields` restricts which are decoded."""
    buf = Path(path).read_bytes()
    nrec = struct.unpack("<I", buf[4:8])[0]
    hl, rl = struct.unpack("<HH", buf[8:12])
    specs, i, off = [], 32, 1
    while buf[i] != 0x0D:
        name = buf[i:i + 11].split(b"\0")[0].decode("ascii", "replace")
        typ = chr(buf[i + 11])
        ln = buf[i + 16]
        specs.append((name, typ, off, ln))
        off += ln
        i += 32
    raw = np.frombuffer(buf, np.uint8, nrec * rl, hl).reshape(nrec, rl)
    out = {}
    for name, typ, o, ln in specs:
        if fields is not None and name not in fields:
            continue
        col = raw[:, o:o + ln].copy().view(f"S{ln}").ravel()
        if typ in "NF":
            s = np.char.strip(col)
            v = np.full(nrec, np.nan)
            ok = s != b""
            v[ok] = s[ok].astype(np.float64)
            out[name] = v
        else:
            out[name] = col
    return out


# ---------------------------------------------------------------------------
# GRWL rivers
# ---------------------------------------------------------------------------

def _grwl_paths(tile: str):
    d = EARTH / f"grwl-vec-{tile}"
    return d / f"{tile}.shp", d / f"{tile}.dbf"


_GRWL_CACHE: dict = {}


def load_grwl(tile: str):
    """(polylines lon/lat, table) for a GRWL vector tile; cached per process."""
    if tile not in _GRWL_CACHE:
        shp, dbf = _grwl_paths(tile)
        _GRWL_CACHE[tile] = (read_shp_polylines(shp),
                             read_dbf(dbf, {"width_m", "nchannels", "segmentID", "segmentInd", "lakeFlag",
                                            "lon", "lat"}))
    return _GRWL_CACHE[tile]


def lonlat_to_m(lon, lat, lon0: float, lat0: float) -> np.ndarray:
    """Local equirectangular metres (x east, y SOUTH = image-down)."""
    x = np.radians(np.asarray(lon) - lon0) * R_EARTH * math.cos(math.radians(lat0))
    y = -np.radians(np.asarray(lat) - lat0) * R_EARTH
    return np.column_stack([x, y])


def grwl_window(tile: str, bbox, *, px: int = 1200, min_len_m: float = 1500.0, min_width_m: float = 30.0,
                drop_lakes: bool = True, step_m: float | None = None, smooth_m: float = 60.0) -> Drawing:
    """The GRWL centreline network inside bbox = (lon_min, lat_min, lon_max,
    lat_max) as a Drawing on a canvas whose long side is `px`.

    GRWL records are vertices (each a tiny polyline) with a width; vertices
    sharing a segmentID, ordered by segmentInd, make one stroke. Strokes are
    resampled at `step_m` (default: canvas px ≈ 1 step), widths smoothed
    along s over `smooth_m`. Stroke meta: segment, width_m (median),
    nchannels (median), and "kind": "river". Drawing meta: m_per_px."""
    polys, tab = load_grwl(tile)
    lon, lat = tab["lon"], tab["lat"]
    x0, y0, x1, y1 = bbox
    sel = (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1)
    if drop_lakes:
        sel &= ~(tab["lakeFlag"] > 0)
    idx = np.flatnonzero(sel)
    lon0, lat0 = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    corners = lonlat_to_m([x0, x1], [y1, y0], lon0, lat0)
    ext = corners[1] - corners[0]
    m_per_px = max(ext) / px
    size = (int(round(ext[0] / m_per_px)), int(round(ext[1] / m_per_px)))
    step = step_m or m_per_px
    seg = tab["segmentID"][idx]
    order = np.lexsort((tab["segmentInd"][idx], seg))
    idx, seg = idx[order], seg[order]
    cuts = np.flatnonzero(np.diff(seg)) + 1
    strokes = []
    for g in np.split(np.arange(len(idx)), cuts):
        ii = idx[g]
        P = lonlat_to_m(lon[ii], lat[ii], lon0, lat0) - corners[0]
        w = np.clip(np.nan_to_num(tab["width_m"][ii], nan=min_width_m), min_width_m, None)
        # GRWL vertices are ~30 m apart; break at gaps (window edges, lakes)
        gaps = np.flatnonzero(np.linalg.norm(np.diff(P, axis=0), axis=1) > 200.0) + 1
        for a, b in zip(np.r_[0, gaps], np.r_[gaps, len(P)]):
            p, ww = P[a:b], w[a:b]
            if len(p) < 3:
                continue
            s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
            if s[-1] < min_len_m:
                continue
            t = np.arange(0, s[-1] + 1e-9, step)
            q = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
            wq = np.interp(t, s, ww)
            # GRWL vertices sit on 30 m pixel centres: the stair is not the
            # river. Smooth the centreline at ~1.5 channel widths (the
            # recipe's σ ≈ 1–2 w), floored at one canvas px; ends pinned.
            sig = max(1.5 * float(np.median(ww)), m_per_px) / step
            if len(q) > 6 and sig > 0.3:
                qs = gaussian_filter1d(q, sig, axis=0, mode="nearest")
                q = qs
            if smooth_m > 0 and len(wq) > 3:
                wq = gaussian_filter1d(wq, max(smooth_m / step, 0.5), mode="nearest")
            strokes.append(Stroke(q / m_per_px, width=wq / m_per_px, meta={
                "kind": "river", "segment": int(seg[g[0]]), "width_m": float(np.median(ww)),
                "nchannels": float(np.nanmedian(tab["nchannels"][ii[a:b]])), "len_m": float(s[-1])}))
    return Drawing(strokes, source=f"grwl:{tile}:{bbox}", size=size,
                   meta={"m_per_px": m_per_px, "tile": tile, "bbox": list(bbox), "kind": "river"})


# ---------------------------------------------------------------------------
# scans (Lichtenberg, bubble chamber, lightning, slime)
# ---------------------------------------------------------------------------

def load_gray(path, *, invert: bool = False, max_side: int = 1600, crop=None, channel: str = "lum") -> np.ndarray:
    """Float gray [0, 1], ink DARK. crop = (x0, y0, x1, y1) in fractions of
    the image. channel "lum" | "max" (max of RGB: coloured glow on black)."""
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        if crop is not None:
            W, H = im.size
            im = im.crop((int(crop[0] * W), int(crop[1] * H), int(crop[2] * W), int(crop[3] * H)))
        im.thumbnail((max_side, max_side))
        a = np.asarray(im, dtype=np.float64) / 255.0
    g = a.max(axis=2) if channel == "max" else a @ np.array([0.299, 0.587, 0.114])
    return 1.0 - g if invert else g


def scan_structure(path, *, invert: bool = False, max_side: int = 1600, crop=None, channel: str = "lum",
                   min_len_frac: float = 0.01, **kw) -> Drawing:
    """A scan through the default extractor; strokes shorter than
    min_len_frac × canvas diagonal dropped (bubbles, dust, sparks)."""
    from . import extract_hybrid
    g = load_gray(path, invert=invert, max_side=max_side, crop=crop, channel=channel)
    d = extract_hybrid.extract(g, source=str(path), **kw)
    diag = math.hypot(*d.size)
    keep = [s for s in d.strokes if s.length() >= min_len_frac * diag and len(s) >= 3]
    return Drawing(keep, source=str(path), size=d.size, meta={**d.meta, "kind": "scan"})


# ---------------------------------------------------------------------------
# hosts from contacts (so preset Strahler / trunk fields apply)
# ---------------------------------------------------------------------------

def with_hosts(d: Drawing, *, tol: float | None = None, root: int | None = None) -> Drawing:
    """Give every stroke a "host": the stroke it branches from, by a BFS over
    endpoint contacts from `root` (default: the stroke with the largest
    length × median width). An endpoint within `tol` px of another stroke
    (anywhere along it) is a contact. Unreached strokes get host None (they
    are roots of their own components; the next root is the next largest).
    Returns a new Drawing; meta "host" and "order" (BFS depth)."""
    n = len(d.strokes)
    if n == 0:
        return d
    tol = tol if tol is not None else 0.006 * math.hypot(*d.size)
    pts = np.vstack([s.points for s in d.strokes])
    owner = np.concatenate([np.full(len(s), i) for i, s in enumerate(d.strokes)])
    tree = cKDTree(pts)
    adj: dict[int, set] = {i: set() for i in range(n)}
    for i, s in enumerate(d.strokes):
        for e in (s.points[0], s.points[-1]):
            for j in set(owner[tree.query_ball_point(e, tol)].tolist()) - {i}:
                adj[i].add(j)
                adj[j].add(i)
    mass = np.array([s.length() * (np.median(s.width) if s.width is not None else 1.0) for s in d.strokes])
    host: list[int | None] = [None] * n
    depth = [-1] * n
    remaining = list(np.argsort(-mass)) if root is None else [root] + [int(i) for i in np.argsort(-mass) if i != root]
    for r in remaining:
        r = int(r)
        if depth[r] >= 0:
            continue
        depth[r] = 0
        frontier = [r]
        while frontier:
            nxt = []
            # visit heavier neighbours first so the trunk carries the depth
            for u in frontier:
                for v in sorted(adj[u], key=lambda k: -mass[k]):
                    if depth[v] < 0:
                        depth[v] = depth[u] + 1
                        host[v] = u
                        nxt.append(v)
            frontier = nxt
    out = [Stroke(s.points, s.width, s.closed, {**s.meta, "host": host[i], "order": depth[i]})
           for i, s in enumerate(d.strokes)]
    return Drawing(out, source=d.source, size=d.size, meta=dict(d.meta))


# ---------------------------------------------------------------------------
# per-point data values
# ---------------------------------------------------------------------------

def width_values(d: Drawing) -> list[np.ndarray]:
    """Full width per point (px); strokes without widths get the drawing's
    median width."""
    ws = [s.width for s in d.strokes if s.width is not None]
    med = float(np.median(np.concatenate(ws))) if ws else 1.0
    return [np.asarray(s.width, float) if s.width is not None else np.full(len(s), med) for s in d.strokes]


def curl_values(d: Drawing, *, sigma_frac: float = 0.004) -> list[np.ndarray]:
    """|κ| per point (1/px) at smoothing σ = sigma_frac × canvas diagonal,
    from `curvature.kappa_s` (the one κ implementation), interpolated back
    onto the stroke's own points. Short strokes get 0."""
    from .curvature import kappa_s
    sig = sigma_frac * math.hypot(*d.size)
    out = []
    for s in d.strokes:
        p = s.points
        segl = np.linalg.norm(np.diff(p, axis=0), axis=1)
        L = float(segl.sum())
        if L < 6 * sig or len(p) < 4:
            out.append(np.zeros(len(p)))
            continue
        res = kappa_s(p, sigma=sig, step=sig / 4)
        ss, kk = _unpack_kappa(res)
        s0 = np.r_[0, np.cumsum(segl)]
        out.append(np.interp(s0, ss, np.abs(kk)))
    return out


def _unpack_kappa(res):
    """kappa_s returns either (s, κ, ...) or an object; normalise."""
    if isinstance(res, tuple):
        return np.asarray(res[0]), np.asarray(res[1])
    for a, b in (("s", "kappa"), ("s", "k")):
        if hasattr(res, a) and hasattr(res, b):
            return np.asarray(getattr(res, a)), np.asarray(getattr(res, b))
    raise TypeError(f"unexpected kappa_s result {type(res)}")


def order_values(d: Drawing) -> list[np.ndarray]:
    """Per-point Strahler order (from host meta via regime_field.strahler)."""
    from .regime_field import strahler
    o = strahler(d)
    return [np.full(len(s), float(o[i])) for i, s in enumerate(d.strokes)]


# ---------------------------------------------------------------------------
# data-born fields
# ---------------------------------------------------------------------------

def quantile_levels(v: np.ndarray, q=(0.55, 0.85)) -> tuple[float, float]:
    v = v[np.isfinite(v)]
    return tuple(float(np.quantile(v, x)) for x in q) if v.size else (0.0, 1.0)


def data_field(d: Drawing, values: list[np.ndarray], *, levels=None, q=(0.55, 0.85), soft: float = 0.35,
               log: bool = True, reach: float = 0.02, background: float = 0.0, smooth: float = 0.0,
               name: str = "data"):
    """A regime Field from per-point data. Each sheet position takes the value
    of the NEAREST structure point (so restyled lines that wander a little
    keep their data). The value maps to r through two soft levels:
    v ≤ lo → 0 (wire), lo..hi → 1 (nib), ≥ hi → 2 (mass); `levels`=(lo, hi)
    or quantiles `q` of all point values. `soft` = smoothstep half-width as a
    fraction of the level gap (in log space if `log`). Beyond `reach` sheet
    widths from any structure point, r fades to `background`.
    smooth > 0 smooths the values along each stroke first (points)."""
    from .regime_field import Field, smoothstep
    W, H = d.size
    pts = np.vstack([s.points for s in d.strokes])
    vals = []
    for v in values:
        v = np.asarray(v, float)
        if smooth > 0 and len(v) > 3:
            v = gaussian_filter1d(v, smooth, mode="nearest")
        vals.append(v)
    v = np.concatenate(vals)
    if log:
        v = np.log(np.maximum(v, 1e-12))
    lo, hi = (np.log(levels) if log else levels) if levels is not None else quantile_levels(v, q)
    gap = max(hi - lo, 1e-9)
    b = max(soft, 1e-3) * gap
    r_pt = smoothstep((v - lo) / (2 * b) + 0.5) + smoothstep((v - hi) / (2 * b) + 0.5)
    tree = cKDTree(pts / W)
    aspect = H / W

    def fn(u):
        q_ = np.column_stack([u[:, 0], u[:, 1] * aspect])
        dist, j = tree.query(q_)
        fade = np.exp(-(dist / max(reach, 1e-6)) ** 2)
        return background + (r_pt[j] - background) * fade

    meta = {"family": "data", "levels": [float(np.exp(lo)) if log else float(lo),
                                         float(np.exp(hi)) if log else float(hi)],
            "share": {"line": float(np.mean(r_pt < 0.5)), "nib": float(np.mean((r_pt >= 0.5) & (r_pt < 1.5))),
                      "shape": float(np.mean(r_pt >= 1.5))}}
    return Field(fn, f"data:{name}", aspect, meta), r_pt


def fit_to_sheet(d: Drawing, size=(840, 1200), margin: float = 0.06) -> Drawing:
    """Uniformly scale + centre a Drawing (points AND widths) onto a sheet."""
    W, H = size
    pts = np.vstack([s.points for s in d.strokes])
    lo, hi = pts.min(0), pts.max(0)
    ext = np.maximum(hi - lo, 1e-9)
    k = min(W * (1 - 2 * margin) / ext[0], H * (1 - 2 * margin) / ext[1])
    off = np.array([W, H]) / 2 - k * (lo + hi) / 2
    out = [Stroke(s.points * k + off, None if s.width is None else s.width * k, s.closed, dict(s.meta))
           for s in d.strokes]
    return Drawing(out, source=d.source, size=(int(W), int(H)), meta={**d.meta, "fit_scale": float(k)})


def prune(d: Drawing, *, max_strokes: int = 140, min_len_frac: float = 0.0) -> Drawing:
    """Keep the `max_strokes` heaviest strokes (length × median width), in
    original order; hosts are dropped (recompute with `with_hosts`)."""
    diag = math.hypot(*d.size)
    mass = np.array([s.length() * (np.median(s.width) if s.width is not None else 1.0) for s in d.strokes])
    ok = [i for i in np.argsort(-mass)[:max_strokes] if d.strokes[i].length() >= min_len_frac * diag]
    keep = [d.strokes[i] for i in sorted(ok)]
    keep = [Stroke(s.points, s.width, s.closed, {k: v for k, v in s.meta.items() if k not in ("host", "order")})
            for s in keep]
    return Drawing(keep, source=d.source, size=d.size, meta=dict(d.meta))
