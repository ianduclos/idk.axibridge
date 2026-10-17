"""Frozen: regimes along one stroke — line → nib → mass (research
`gesture/regime.py` at c897f28, trimmed).

A scalar regime value r(s) ∈ [0, 2] along the centreline decides, sample by
sample, what the mark is:

    r = 0   line   monoline, one pen wide (the centreline itself is drawn)
    r = 1   nib    broad-nib ribbon, ink width W·|sin(θ − φ)| + w_min
    r = 2   mass   the ribbon swells past the nib law to `mass`
                   (direction-free) and is filled

The ink footprint at every sample is a stadium (a segment of half-length a
along the nib edge u(φ) = (cos φ, −sin φ), dilated by a disc of radius ρ).
The drawn contour is the boundary of the PEN-CENTRE region (the swept ink
eroded by pen/2), so at r = 0 it is the centreline itself and as r rises it
opens into a ribbon whose outline leaves the line tangentially. Fill =
concentric insets every pen, graded by the fill weight so ink pools from the
centre outward. Never hatching.

Dropped: wet / edge processes, spiral fill, transition operators, cost
measures. app: `render` returns the outline rings separately from the other
paths (`splice=False` keeps them whole) so the source can mark them filled.

Pure and deterministic; nothing here mutates its inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter1d

K_ARC = 12                     # boundary points per stadium end-disc in the hulls


@dataclass(frozen=True)
class RegimeStroke:
    points: np.ndarray
    r: np.ndarray
    phi: np.ndarray
    W: np.ndarray
    mass: np.ndarray
    w_min: float = 0.0
    closed: bool = False
    fill: np.ndarray | None = None
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        p = np.array(self.points, dtype=np.float64)
        if p.ndim != 2 or p.shape[1] != 2:
            raise ValueError(f"points must be (N, 2), got {p.shape}")
        n = len(p)
        object.__setattr__(self, "points", p)
        for k in ("r", "phi", "W", "mass"):
            v = np.array(getattr(self, k), dtype=np.float64)
            v = np.full(n, float(v)) if v.ndim == 0 else v
            if v.shape != (n,):
                raise ValueError(f"{k} must be (N,) matching points")
            object.__setattr__(self, k, v)
        object.__setattr__(self, "r", np.clip(self.r, 0.0, 2.0))
        if self.fill is not None:
            f = np.array(self.fill, dtype=np.float64)
            f = np.full(n, float(f)) if f.ndim == 0 else f
            if f.shape != (n,):
                raise ValueError("fill must be (N,) matching points")
            object.__setattr__(self, "fill", np.clip(f, 0.0, 1.0))
        object.__setattr__(self, "meta", dict(self.meta))

    def __len__(self) -> int:
        return len(self.points)

    def fill_weight(self) -> np.ndarray:
        return self.fill if self.fill is not None else _smoothstep((self.r - 1.1) / 0.4)

    def length(self) -> float:
        return float(arclength(self.points, self.closed)[-1])


MASS_W = 2.6     # PROFILE_DEFAULTS["mass_w"]: default mass diameter in nib widths


def make(points, r=0.0, *, phi=np.deg2rad(60.0), W=1.5, mass=None, w_min: float = 0.0,
         closed: bool = False, fill=None, meta: dict | None = None) -> RegimeStroke:
    """RegimeStroke with scalar broadcasting; mass defaults to mass_w·W."""
    p = np.asarray(points, dtype=np.float64)
    n = len(p)
    Wv = np.broadcast_to(np.asarray(W, dtype=np.float64), (n,)).copy()
    mv = MASS_W * Wv if mass is None else np.broadcast_to(np.asarray(mass, dtype=np.float64), (n,)).copy()
    return RegimeStroke(p, np.broadcast_to(np.asarray(r, float), (n,)).copy(),
                        np.broadcast_to(np.asarray(phi, float), (n,)).copy(), Wv, mv, float(w_min),
                        closed, fill, meta or {})


def arclength(points: np.ndarray, closed: bool = False) -> np.ndarray:
    p = np.asarray(points, dtype=np.float64)
    if closed and len(p) > 1:
        p = np.vstack([p, p[:1]])
    if len(p) < 2:
        return np.zeros(len(p))
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def _fields(st: RegimeStroke) -> dict:
    f = {"r": st.r, "phi_c": np.cos(2 * st.phi), "phi_s": np.sin(2 * st.phi), "W": st.W, "mass": st.mass}
    if st.fill is not None:
        f["fill"] = st.fill
    return f


def _rebuild(st: RegimeStroke, pts: np.ndarray, f: dict, **kw) -> RegimeStroke:
    phi = 0.5 * np.arctan2(f["phi_s"], f["phi_c"])
    return RegimeStroke(pts, f["r"], phi, f["W"], f["mass"], kw.get("w_min", st.w_min),
                        kw.get("closed", st.closed), f.get("fill"), kw.get("meta", st.meta))


def resample(st: RegimeStroke, step: float) -> RegimeStroke:
    """Uniform arc-length resampling of the centreline and every field
    (φ interpolated on the doubled angle — the nib edge has period π)."""
    s = arclength(st.points, st.closed)
    L = s[-1]
    if L <= 0 or len(st) < 2:
        return st
    pts = np.vstack([st.points, st.points[:1]]) if st.closed else st.points
    n = max(int(np.ceil(L / step)), 1)
    t = np.linspace(0.0, L, n + 1)
    if st.closed:
        t = t[:-1]
    q = np.column_stack([np.interp(t, s, pts[:, 0]), np.interp(t, s, pts[:, 1])])
    f = {}
    for k, v in _fields(st).items():
        vv = np.concatenate([v, v[:1]]) if st.closed else v
        f[k] = np.interp(t, s, vv)
    return _rebuild(st, q, f)


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def footprint(st: RegimeStroke, pen: float) -> tuple[np.ndarray, np.ndarray]:
    """INK stadium (half-length a along the nib edge, disc radius ρ) per sample."""
    r = st.r
    t = _smoothstep(r)
    u = _smoothstep(r - 1.0)
    a = 0.5 * t * st.W
    rho0 = 0.5 * pen
    rho1 = 0.5 * max(pen, st.w_min)
    rho_line_nib = 0.5 * np.maximum(pen, pen + t * (max(st.w_min, pen) - pen))
    rho = rho_line_nib + u * np.maximum(0.5 * st.mass - rho1, 0.0)
    rho = np.maximum(rho, rho0)
    return a, rho


def ink_width(st: RegimeStroke, pen: float = 0.35, *, sigma: float | None = None) -> np.ndarray:
    """Full ink width across the path at every sample (mm)."""
    a, rho = footprint(st, pen)
    p = st.points
    if len(p) < 2:
        return 2 * rho
    g = np.gradient(np.vstack([p[-1:], p, p[:1]]) if st.closed else p, axis=0)
    if st.closed:
        g = g[1:-1]
    if sigma:
        g = np.column_stack([gaussian_filter1d(g[:, 0], sigma), gaussian_filter1d(g[:, 1], sigma)])
    theta = np.arctan2(-g[:, 1], g[:, 0])
    return 2 * a * np.abs(np.sin(theta - st.phi)) + 2 * rho


def _hulls(c: np.ndarray, uvec: np.ndarray, a: np.ndarray, rr: np.ndarray, pairs: np.ndarray,
           pen: float = 0.35):
    """Convex hulls of consecutive pen-centre stadia (vectorised)."""
    import shapely

    kk = int(np.clip(np.ceil(2 * np.pi * float(rr.max(initial=0.0)) / (0.3 * pen)), K_ARC, 160))
    ang = np.linspace(0, 2 * np.pi, kk, endpoint=False)
    circ = np.column_stack([np.cos(ang), np.sin(ang)])
    e1 = c + a[:, None] * uvec
    e2 = c - a[:, None] * uvec
    ring = rr[:, None, None] * circ[None]
    P = np.concatenate([e1[:, None, :] + ring, e2[:, None, :] + ring], axis=1)
    i, j = pairs[:, 0], pairs[:, 1]
    pts = np.concatenate([P[i], P[j]], axis=1)
    m, k, _ = pts.shape
    mp = shapely.multipoints(pts.reshape(-1, 2), indices=np.repeat(np.arange(m), k))
    return shapely.convex_hull(mp)


def _prep(st: RegimeStroke, pen: float, step: float | None):
    if step is None:
        step = 0.5 * pen
        L = st.length()
        if L / step > 4000:
            step = L / 4000
    q = resample(st, step) if len(st) >= 2 else st
    a, rho = footprint(q, pen)
    rr = np.maximum(rho - 0.5 * pen, 0.0)
    uvec = np.column_stack([np.cos(q.phi), -np.sin(q.phi)])
    n = len(q)
    if n < 2:
        pairs = np.zeros((0, 2), int)
    else:
        pairs = np.column_stack([np.arange(n - 1), np.arange(1, n)])
        if q.closed:
            pairs = np.vstack([pairs, [[n - 1, 0]]])
    return q, a, rr, uvec, pairs


def _geom_parts(strokes: list[RegimeStroke], pen: float, step: float | None, eps_frac: float = 0.05):
    """Pen-centre polygons G, filled sub-region F, exact line runs and the
    per-sample data the fill grading needs (P, f, H)."""
    import shapely
    from shapely.geometry import LineString

    eps = eps_frac * pen
    polys, fills, runs, samples = [], [], [], []
    for st in strokes:
        a0, rho0 = footprint(st, pen)
        if np.all(a0 + np.maximum(rho0 - 0.5 * pen, 0.0) < eps):
            runs.append(np.vstack([st.points, st.points[:1]]) if st.closed else st.points.copy())
            continue
        q, a, rr, uvec, pairs = _prep(st, pen, step)
        ext = a + rr
        is_line = ext < eps
        samples.append({"P": q.points, "f": q.fill_weight(), "H": a + rr})
        if len(pairs) == 0:
            if len(q):
                runs.append(q.points.copy())
            continue
        line_pair = is_line[pairs[:, 0]] & is_line[pairs[:, 1]]
        hp = pairs[~line_pair]
        if len(hp):
            hulls = _hulls(q.points, uvec, a, rr, hp, pen)
            polys.append(hulls)
            fw = q.fill_weight()
            fsel = (fw[hp[:, 0]] > 0.02) | (fw[hp[:, 1]] > 0.02)
            if fsel.any():
                fills.append(hulls[fsel])
        idx = np.flatnonzero(line_pair)
        if len(idx):
            cuts = np.flatnonzero(np.diff(idx) > 1)
            for seg in np.split(idx, cuts + 1):
                ids = list(pairs[seg, 0]) + [pairs[seg[-1], 1]]
                runs.append(q.points[ids].copy())
            if q.closed and line_pair.all():
                runs = runs[:-1] + [np.vstack([q.points, q.points[:1]])]
    G = None
    if polys:
        G = _polygonal(shapely.union_all(np.concatenate(polys)))
    F = None
    if fills and G is not None:
        F = _polygonal(shapely.union_all(np.concatenate(fills)))
    # line runs that pass over a ribbon/mass are hidden there (no ink twice)
    if G is not None and not G.is_empty:
        out = []
        Gi = G.buffer(-1e-6)
        for rp in runs:
            ls = LineString(rp) if len(rp) >= 2 else None
            if ls is None or not ls.intersects(Gi):
                out.append(rp)
                continue
            for g in _lines(ls.difference(Gi)):
                c = np.asarray(g.coords)
                if len(c) >= 2 and _plen(c) > 1e-6:
                    out.append(c)
        runs = out
    return G, F, runs, samples


def _cat_samples(samples: list[dict]) -> dict:
    return {k: np.concatenate([d[k] for d in samples]) for k in samples[0]}


def _attribute(tree, H: np.ndarray, pts: np.ndarray, k: int = 64) -> np.ndarray:
    """For each point, the centreline sample whose footprint GENERATES the
    outline there: argmax_j (H_j − |x − P_j|) over the k nearest samples."""
    k = int(min(k, tree.n))
    d, j = tree.query(pts, k=k, workers=-1)          # app: threads; same result
    if k == 1:
        return np.atleast_1d(j)
    best = np.argmax(H[j] - d, axis=1)
    return j[np.arange(len(pts)), best]


def _polygonal(g):
    from shapely.geometry import MultiPolygon, Polygon
    if g is None or g.is_empty:
        return None
    if isinstance(g, (Polygon, MultiPolygon)):
        return g if g.is_valid else g.buffer(0)
    ps = [x for x in getattr(g, "geoms", []) if isinstance(x, (Polygon, MultiPolygon))]
    if not ps:
        return None
    from shapely import union_all
    return union_all(ps)


def _polys(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    out = []
    for x in getattr(g, "geoms", []):
        out += _polys(x)
    return out


def _lines(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type in ("LineString", "LinearRing"):
        return [g]
    out = []
    for x in getattr(g, "geoms", []):
        out += _lines(x)
    return out


def _plen(p) -> float:
    p = np.asarray(p)
    return float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1))) if len(p) > 1 else 0.0


def _ring(coords) -> np.ndarray:
    c = np.asarray(coords, dtype=np.float64)
    if len(c) and not np.allclose(c[0], c[-1]):
        c = np.vstack([c, c[:1]])
    return c


def _outline_rings(G, pen: float, min_area: float) -> list[np.ndarray]:
    from shapely.geometry import Polygon
    out = []
    for poly in _polys(G):
        if poly.area < min_area:
            continue
        out.append(_ring(poly.exterior.coords))
        for h in poly.interiors:
            # a counter the pen would ink over anyway is not drawn: the loop has closed
            if Polygon(h).buffer(-0.5 * pen).is_empty:
                continue
            out.append(_ring(h.coords))
    return out


def _densify(c: np.ndarray, step: float) -> np.ndarray:
    """Every segment split into ceil(len / step) equal parts (app: vectorised;
    same points as the research's per-segment loop)."""
    d = np.linalg.norm(np.diff(c, axis=0), axis=1)
    k = np.maximum(np.ceil(d / step).astype(int), 1)
    seg = np.repeat(np.arange(len(c) - 1), k)
    first = np.repeat(np.cumsum(k) - k, k)
    f = (np.arange(len(seg)) - first) / k[seg]
    pts = c[seg] + f[:, None] * (c[seg + 1] - c[seg])
    return np.vstack([pts, c[-1:]])


def _fill_paths(G, F, pen: float, samples, max_rings: int = 400) -> list[np.ndarray]:
    """Graded concentric fill: insets of G every pen; an inset vertex at
    depth d is kept where its generating sample's fill weight f satisfies
    d ≥ (1 − f)·h, so ink pools from the centre outward."""
    from scipy.spatial import cKDTree
    from shapely.geometry import LineString
    if G is None or F is None or not samples:
        return []
    S = _cat_samples(samples)
    P, Fw, H = S["P"], S["f"], S["H"]
    tree = cKDTree(P)
    Fb = F.buffer(pen)
    out = []
    g = G.buffer(-pen, join_style="round")
    depth = pen
    k = 0
    last = False
    while g is not None and not g.is_empty and k < max_rings:
        for poly in _polys(g):
            for ring in [poly.exterior, *poly.interiors]:
                if not LineString(ring.coords).intersects(Fb):
                    continue
                c = _densify(np.asarray(ring.coords), 0.5 * pen)
                j = _attribute(tree, H, c)
                keep = depth >= (1.0 - Fw[j]) * H[j] - 1e-9
                if keep.all():
                    out.append(_ring(c))
                    continue
                idx = np.flatnonzero(keep)
                if not len(idx):
                    continue
                cuts = np.flatnonzero(np.diff(idx) > 1)
                pieces = [c[seg] for seg in np.split(idx, cuts + 1)]
                if keep[0] and keep[-1] and len(pieces) > 1:
                    pieces = [np.vstack([pieces[-1], pieces[0][1:]])] + pieces[1:-1]
                out += [pc for pc in pieces if _plen(pc) > 2 * pen]
        nxt = g.buffer(-pen, join_style="round")
        step = pen
        if nxt.is_empty and not last:
            nxt = g.buffer(-0.5 * pen, join_style="round")
            step = 0.5 * pen
            last = True
        elif last:
            break
        g = nxt
        depth += step
        k += 1
    return out


def render_parts(strokes, pen: float = 0.35, *, fill: bool = True, step: float | None = None,
                 min_area: float | None = None) -> dict:
    """The research `render` pieces for one stroke or one MARK (a list of
    strokes whose ribbons are unioned): G / F (shapely), `runs` (line runs),
    `rings` (outline rings, closed, first point repeated) and `fill`
    (concentric fill contours). app: no splicing, so rings stay whole."""
    sts = [strokes] if isinstance(strokes, RegimeStroke) else list(strokes)
    sts = [s for s in sts if len(s)]
    if not sts:
        return {"G": None, "F": None, "runs": [], "rings": [], "fill": []}
    G, F, runs, samples = _geom_parts(sts, pen, step)
    ma = (0.02 * pen * pen) if min_area is None else min_area
    rings = _outline_rings(G, pen, ma) if G is not None else []
    fp = _fill_paths(G, F, pen, samples) if fill else []
    clean = lambda ps: [np.asarray(p, dtype=np.float64) for p in ps if len(p) >= 2]  # noqa: E731
    return {"G": G, "F": F, "runs": clean(runs), "rings": clean(rings), "fill": clean(fp)}


def from_field(points, field_fn, *, phi=np.deg2rad(60.0), W=1.5, mass=None, w_min: float = 0.0,
               smooth: float | None = None, closed: bool = False, step: float | None = None,
               meta: dict | None = None) -> RegimeStroke:
    """r(s) = field_fn(x, y) along `points` (resampled at `step`, default
    W/4), clipped to [0, 2] and Gaussian-smoothed along s at σ = `smooth`
    (default W — a field cannot change regime faster than the nib can)."""
    p = np.asarray(points, dtype=np.float64)
    W0 = float(np.median(W))
    step = step or max(W0 / 4.0, 0.05)
    base = make(p, 0.0, W=1.0, closed=closed)
    q = resample(base, step).points if len(p) > 1 else p
    r = np.clip(np.asarray(field_fn(q[:, 0], q[:, 1]), dtype=np.float64), 0.0, 2.0)
    sm = W0 if smooth is None else smooth
    if sm > 0 and len(r) > 2:
        r = gaussian_filter1d(r, sm / step, mode="wrap" if closed else "nearest")
    return make(q, r, phi=phi, W=W, mass=mass, w_min=w_min, closed=closed, meta=meta)
