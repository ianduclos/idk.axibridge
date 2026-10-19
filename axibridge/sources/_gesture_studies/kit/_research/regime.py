# FROZEN from research commit ecd64f8: tools/gesture/gesture/regime.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Regime metamorphosis along one stroke: line → nib → shape (mass) and back.

Direction: docs/IDEAS-gesture-bank.md, "three regimes that become one another
in space". One stroke representation carries all three regimes; a scalar
regime value r(s) ∈ [0, 2] along the centreline decides, sample by sample,
what the mark is:

    r = 0   line   monoline, one pen wide (the centreline itself is drawn)
    r = 1   nib    broad-nib ribbon, ink width W·|sin(θ − φ)| + w_min
    r = 2   shape  a mass: the ribbon swells past the nib law to `mass`
                   (direction-free), closes on itself and is filled

=========================================================================
INTERFACE (for gesture/signs.py, gesture/regime_field.py and others)
=========================================================================

    from .regime import RegimeStroke, make, render, from_field

    RegimeStroke(points, r, phi, W, mass, w_min=0.0, closed=False,
                 fill=None, meta={})
        points  (N, 2) float  centreline, plotter units (mm), y down
        r       (N,)   float  regime value in [0, 2]
        phi     (N,)   float  nib EDGE page angle, rad (broadnib.py
                              convention: CCW from rightward horizontal as
                              the sheet is seen; thickest strokes run at
                              φ + 90°)
        W       (N,)   float  nib edge length (mm): full-nib width W(s)
        mass    (N,)   float  diameter the stroke swells to at r = 2 (mm)
        w_min   float         nib hairline (mm); below the pen it is the pen
        closed  bool          closed centreline (point 0 not repeated)
        fill    (N,) | None   fill weight in [0, 1]; None = derived from r
                              (smoothstep over r ∈ [1.1, 1.5]); the fill
                              pools from the centre outward as f → 1
        meta    dict

    make(points, r=0.0, phi=..., W=..., mass=None, ...) -> RegimeStroke
        Scalars broadcast; mass defaults to 2.5·W.

    render(stroke_or_strokes, pen=0.35, *, fill=True, wet=None, edge=None,
           seed=None, fill_style="concentric", nib_renderer=None) -> list[np.ndarray]
        Plotter polylines, each (M, 2) float, in drawing order. CLOSED
        contours repeat their first point at the end, so every array is
        drawable as-is. A list of strokes is rendered as ONE mark: their
        ribbons are unioned before outlining (a mass and the drips it
        sheds share one outline). Never hatching: line runs, ribbon
        outlines, concentric insets.
        Round 7 options (all default off): wet= a WET_PROFILES name
        ("reference" | "marden" | "hokusai" | "calligraphy") or True for
        data-fitted wet mass edges; edge= "scallop" | "notch" | dict for a
        rhythmic event on one side of a mass; per-stroke meta["wet"] /
        meta["edge"] override both; fill_style="spiral" chains the insets
        into few paths; nib_renderer= a hook for gesture/penrender.
        `rim_gap(strokes, paths, pen)` measures the white rim inside masses.

    from_field(points, field_fn, *, phi=..., W=..., mass=None, smooth=...,
               closed=False) -> RegimeStroke
        r(s) = field_fn(x, y) sampled along the points (vectorised call
        tried first, else per point), clipped to [0, 2] and smoothed along
        the stroke (σ = `smooth`, mm) so a field can never put a kink in
        the width.

    Also: `ink_width(stroke, pen)` (full ink width along the stroke),
    `pen_cost(paths)`, `regime_cost(stroke, paths)` (pen-down length split
    per regime), the transition operators `thicken`, `swell`, `close_fill`,
    `eye`, `terminal_drop`, `shed`, and `concat` / `reverse` / `resample`.

=========================================================================
MODEL
=========================================================================

At every sample the INK footprint of the tool is a stadium: a segment of
half-length a along the nib edge u(φ) = (cos φ, −sin φ), dilated by a disc
of radius ρ (segment ⊕ disc — exactly broadnib's Minkowski nib). Its width
across a path running at page angle θ is

    width = 2a·|sin(θ − φ)| + 2ρ.

r ∈ [0, 1] (thickening): t = smoothstep(r); a = t·W/2;
    ρ = max(pen, pen + t·(w_min − pen))/2  → at r = 0 the ink is the pen.
r ∈ [1, 2] (swelling): u = smoothstep(r − 1); a = W/2;
    ρ = ρ₁ + u·max(mass/2 − ρ₁, 0)       → the disc outgrows the nib, so the
    width stops depending on direction; the stroke balloons.

Width is non-decreasing in r for every direction, and smoothstep has zero
slope at r = 0, 1, 2, so width is C¹ in s wherever r(s) is — no kinks at
regime changes.

The tool is a pen of diameter `pen`, so the drawn contour is the boundary of
the PEN-CENTRE region: the ink region eroded by pen/2, i.e. the same sweep
with ρ' = ρ − pen/2. At r = 0 that stadium is a point and the sweep is the
centreline itself; as r rises it opens into a ribbon whose outline leaves
the line's end tangentially — the line and the outline are one continuous
mark. The sweep is the union of the convex hulls of consecutive stadia (the
exact Minkowski sweep for piecewise-linear motion with linearly varying
tool). Holes the pen would ink over anyway (inradius < pen/2) are dropped:
that is the moment a loop "closes". Fill = concentric insets of the
pen-centre region every `pen`, graded by the fill weight f: an inset at
depth d is drawn where d ≥ (1 − f)·(local half-extent), so the fill pools
from the centre outward as f rises (no seam where filling begins).

Pure and deterministic; nothing here mutates its inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
from scipy.ndimage import gaussian_filter1d

__all__ = [
    "RegimeStroke", "make", "render", "from_field", "ink_width", "footprint",
    "pen_cost", "regime_cost", "resample", "concat", "reverse", "arclength",
    "thicken", "swell", "close_fill", "eye", "terminal_drop", "shed",
    "PROFILE_DEFAULTS", "sample_profile", "LINE", "NIB", "SHAPE",
    "massness", "WET_PROFILES", "wet_params", "rim_gap",
]

LINE, NIB, SHAPE = 0.0, 1.0, 2.0
K_ARC = 12                     # boundary points per stadium end-disc in the hulls

# Operator defaults in units of the nib width W, fitted from data by
# experiments/regime_study.py `fit` (results/regime-2026-10-16.md §3):
# - ramp_w: FULL length of `thicken`'s ramp. Measured: thin → thick (25 % → 75 %
#   of the way from a stroke's q10 to q90 width) takes a median 1.46 thick
#   widths on the generative shikasta sheets (IQR 1.04–2.37; nasta'liq 1.22,
#   Baghdadi 1.36, Ian's reference image 1.49). The thicken ramp covers
#   25 → 75 % in 0.235 of its length, so ramp_w = 1.46 / 0.235 ≈ 6.2.
# - mass_w: swelling diameter at r = 2. Reference masses: median 8.6 thin
#   widths = 2.6 of its thick strokes (thick/thin ≈ 3.35).
# - bulb_w: terminal drop diameter. Terminal/interior width ratio q75–q90:
#   1.24–1.48 shikasta, 1.46–1.98 reference.
# - nuqta_w: calligraphic dot side ≈ the nib (not measured here; †).
PROFILE_DEFAULTS = {"ramp_w": 6.2, "ramp_w_q": (4.4, 6.2, 10.1), "bulb_w": 1.7, "bulb_w_q": (1.25, 1.7, 2.0),
                    "nuqta_w": 1.0, "mass_w": 2.6, "mass_w_q": (2.2, 2.6, 2.85)}


def sample_profile(rng: np.random.Generator, key: str = "ramp_w") -> float:
    """A draw from the fitted distribution of a profile parameter (log-normal
    through the measured quartiles / q25-q50-q75 triple of PROFILE_DEFAULTS[key + "_q"])."""
    lo, med, hi = PROFILE_DEFAULTS[key + "_q"]
    sd = (np.log(hi) - np.log(lo)) / (2 * 0.674)
    return float(np.exp(np.log(med) + sd * rng.standard_normal()))


# ---------------------------------------------------------------------------
# the stroke
# ---------------------------------------------------------------------------

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


def make(points, r=0.0, *, phi=np.deg2rad(60.0), W=1.5, mass=None, w_min: float = 0.0,
         closed: bool = False, fill=None, meta: dict | None = None) -> RegimeStroke:
    """RegimeStroke with scalar broadcasting; mass defaults to mass_w·W."""
    p = np.asarray(points, dtype=np.float64)
    n = len(p)
    Wv = np.broadcast_to(np.asarray(W, dtype=np.float64), (n,)).copy()
    mv = PROFILE_DEFAULTS["mass_w"] * Wv if mass is None else np.broadcast_to(
        np.asarray(mass, dtype=np.float64), (n,)).copy()
    return RegimeStroke(p, np.broadcast_to(np.asarray(r, float), (n,)).copy(),
                        np.broadcast_to(np.asarray(phi, float), (n,)).copy(), Wv, mv, float(w_min),
                        closed, fill, meta or {})


def arclength(points: np.ndarray, closed: bool = False) -> np.ndarray:
    """Cumulative arc length at each point (closed: one extra entry for the
    closing segment)."""
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


def reverse(st: RegimeStroke) -> RegimeStroke:
    f = {k: v[::-1].copy() for k, v in _fields(st).items()}
    return _rebuild(st, st.points[::-1].copy(), f)


def concat(a: RegimeStroke, b: RegimeStroke) -> RegimeStroke:
    """a then b (b's first point is dropped if it repeats a's last)."""
    sk = 1 if len(b) and len(a) and np.allclose(a.points[-1], b.points[0]) else 0
    fa, fb = _fields(a), _fields(b)
    if ("fill" in fa) != ("fill" in fb):
        fa.setdefault("fill", a.fill_weight())
        fb.setdefault("fill", b.fill_weight())
    f = {k: np.concatenate([fa[k], fb[k][sk:]]) for k in fa}
    return _rebuild(a, np.vstack([a.points, b.points[sk:]]), f, closed=False)


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


# ---------------------------------------------------------------------------
# the tool footprint and widths
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _hulls(c: np.ndarray, uvec: np.ndarray, a: np.ndarray, rr: np.ndarray, pairs: np.ndarray,
           pen: float = 0.35):
    """Convex hulls of consecutive pen-centre stadia (vectorised). The disc
    polygons get enough vertices that facets stay under ~0.3 pen of chord."""
    import shapely

    kk = int(np.clip(np.ceil(2 * np.pi * float(rr.max(initial=0.0)) / (0.3 * pen)), K_ARC, 160))
    ang = np.linspace(0, 2 * np.pi, kk, endpoint=False)
    circ = np.column_stack([np.cos(ang), np.sin(ang)])
    # per sample: 2 discs × K points  → (n, 2K, 2)
    e1 = c + a[:, None] * uvec
    e2 = c - a[:, None] * uvec
    ring = rr[:, None, None] * circ[None]
    P = np.concatenate([e1[:, None, :] + ring, e2[:, None, :] + ring], axis=1)
    i, j = pairs[:, 0], pairs[:, 1]
    pts = np.concatenate([P[i], P[j]], axis=1)              # (m, 4K, 2)
    m, k, _ = pts.shape
    mp = shapely.multipoints(pts.reshape(-1, 2), indices=np.repeat(np.arange(m), k))
    return shapely.convex_hull(mp)


def _prep(st: RegimeStroke, pen: float, step: float | None):
    if step is None:
        step = 0.5 * pen
        # cap the sample count: long strokes at 0.5 pen are plenty smooth
        L = st.length()
        if L / step > 4000:
            step = L / 4000
    q = resample(st, step) if len(st) >= 2 else st
    a, rho = footprint(q, pen)
    rr = np.maximum(rho - 0.5 * pen, 0.0)                  # pen-centre disc radius
    uvec = np.column_stack([np.cos(q.phi), -np.sin(q.phi)])
    n = len(q)
    if n < 2:
        pairs = np.zeros((0, 2), int)
    else:
        pairs = np.column_stack([np.arange(n - 1), np.arange(1, n)])
        if q.closed:
            pairs = np.vstack([pairs, [[n - 1, 0]]])
    return q, a, rr, uvec, pairs


def _stroke_samples(q: RegimeStroke, a: np.ndarray, rr: np.ndarray, sid: int) -> dict:
    """Per-sample data the fill grading and the edge process need."""
    p = q.points
    n = len(p)
    if n >= 2:
        g = np.gradient(np.vstack([p[-1:], p, p[:1]]) if q.closed else p, axis=0)
        if q.closed:
            g = g[1:-1]
    else:
        g = np.zeros((n, 2))
    tan = g / (np.linalg.norm(g, axis=1, keepdims=True) + 1e-12)
    s = arclength(p, q.closed)[:n]
    L = max(float(arclength(p, q.closed)[-1]), 1e-12)
    m = massness(q.r)
    # massy runs: position inside the run (0 → 1 along the stroke) and run length
    trun = np.zeros(n)
    lrun = np.zeros(n)
    on = m > 0.3
    if on.any():
        idx = np.flatnonzero(on)
        cuts = np.flatnonzero(np.diff(idx) > 1)
        for seg in np.split(idx, cuts + 1):
            s0, s1 = s[seg[0]], s[seg[-1]]
            trun[seg] = (s[seg] - s0) / max(s1 - s0, 1e-9)
            lrun[seg] = s1 - s0
    return {"P": p, "f": q.fill_weight(), "H": a + rr, "r": q.r, "m": m, "tan": tan, "sfrac": s / L,
            "trun": trun, "lrun": lrun, "sid": np.full(n, sid),
            "wet_ok": np.full(n, 0.0 if "shed" in q.meta else 1.0)}


def _geom_parts(strokes: list[RegimeStroke], pen: float, step: float | None, eps_frac: float = 0.05,
                edge_fn=None):
    """Pen-centre polygons, filled sub-region, exact line runs and per-sample
    data. `edge_fn(G, samples) -> G` (the wet / scallop edge process) runs
    on the unioned outline before line runs are clipped to it."""
    import shapely
    from shapely.geometry import LineString

    eps = eps_frac * pen
    polys, fills, runs, samples = [], [], [], []
    for sid, st in enumerate(strokes):
        a0, rho0 = footprint(st, pen)
        if np.all(a0 + np.maximum(rho0 - 0.5 * pen, 0.0) < eps):
            # a pure line: the centreline itself, exactly as given
            runs.append(np.vstack([st.points, st.points[:1]]) if st.closed else st.points.copy())
            continue
        q, a, rr, uvec, pairs = _prep(st, pen, step)
        ext = a + rr
        is_line = ext < eps
        samples.append(_stroke_samples(q, a, rr, sid))
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
        # line runs: maximal runs of line pairs, in stroke order
        idx = np.flatnonzero(line_pair)
        if len(idx):
            cuts = np.flatnonzero(np.diff(idx) > 1)
            for seg in np.split(idx, cuts + 1):
                ids = list(pairs[seg, 0]) + [pairs[seg[-1], 1]]
                runs.append(q.points[ids].copy())
            # closed stroke entirely line: merge the wrap
            if q.closed and line_pair.all():
                runs = runs[:-1] + [np.vstack([q.points, q.points[:1]])]
    G = None
    if polys:
        G = shapely.union_all(np.concatenate(polys))
        G = _polygonal(G)
    F = None
    if fills and G is not None:
        F = _polygonal(shapely.union_all(np.concatenate(fills)))
    if edge_fn is not None and G is not None and samples:
        G = _polygonal(edge_fn(G, samples)) or G
    # line runs that pass over a ribbon/mass are hidden there (no ink twice)
    if G is not None and not G.is_empty:
        out = []
        Gi = G.buffer(-1e-6)
        for rp in runs:
            ls = LineString(rp) if len(rp) >= 2 else None
            if ls is None or not ls.intersects(Gi):
                out.append(rp)
                continue
            d = ls.difference(Gi)
            for g in _lines(d):
                c = np.asarray(g.coords)
                if len(c) >= 2 and _plen(c) > 1e-6:
                    out.append(c)
        runs = out
    return G, F, runs, samples


def _cat_samples(samples: list[dict]) -> dict:
    return {k: np.concatenate([d[k] for d in samples]) for k in samples[0]}


def _attribute(tree, H: np.ndarray, pts: np.ndarray, k: int = 64) -> np.ndarray:
    """For each point, the centreline sample whose footprint GENERATES the
    outline there: argmax_j (H_j − |x − P_j|) over the k nearest samples.
    The nearest sample is wrong at a round mass's ends (the outline there is
    the disc of a sample well inside), which is what left the white rim."""
    k = int(min(k, tree.n))
    d, j = tree.query(pts, k=k)
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
    out = []
    for poly in _polys(G):
        if poly.area < min_area:
            continue
        out.append(_ring(poly.exterior.coords))
        for h in poly.interiors:
            from shapely.geometry import Polygon
            hp = Polygon(h)
            # a counter the pen would ink over anyway is not drawn: the loop has closed
            if hp.buffer(-0.5 * pen).is_empty:
                continue
            out.append(_ring(h.coords))
    return out


def _densify(c: np.ndarray, step: float) -> np.ndarray:
    d = np.linalg.norm(np.diff(c, axis=0), axis=1)
    k = np.maximum(np.ceil(d / step).astype(int), 1)
    parts = [c[i] + np.outer(np.arange(k[i]) / k[i], c[i + 1] - c[i]) for i in range(len(c) - 1)]
    return np.vstack(parts + [c[-1:]])


def _fill_paths(G, F, pen: float, samples, max_rings: int = 400) -> list[np.ndarray]:
    """Graded concentric fill. Insets of G every `pen` (the last one half a
    step, so no white spine is left); an inset vertex at depth d below the
    outline is kept where the GENERATING centreline sample's (`_attribute`)
    fill weight f satisfies d ≥ (1 − f)·h, h = that sample's pen-centre
    half-extent. So
    as f rises the ink pools from the CENTRE outward and reaches the
    outline at f = 1 — no straight seam where the fill begins."""
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
                # a run across the ring's seam is one piece
                if keep[0] and keep[-1] and len(pieces) > 1:
                    pieces = [np.vstack([pieces[-1], pieces[0][1:]])] + pieces[1:-1]
                out += [pc for pc in pieces if _plen(pc) > 2 * pen]
        nxt = g.buffer(-pen, join_style="round")
        step = pen
        if nxt.is_empty and not last:
            # the last region can be up to 2 pen wide: one more half-step
            # inset closes the white spine the plain rings would leave
            nxt = g.buffer(-0.5 * pen, join_style="round")
            step = 0.5 * pen
            last = True
        elif last:
            break
        g = nxt
        depth += step
        k += 1
    return out


# ---------------------------------------------------------------------------
# wet mass edges and edge events (results/regime-masses-2026-10-16.md)
# ---------------------------------------------------------------------------

def massness(r) -> np.ndarray:
    """How much a sample is a SHAPE (0 below r = 1.2, 1 from r = 1.8): the
    weight of the wet-edge process. Lines and nibs keep their exact outline,
    so a line still enters a wet mass tangentially."""
    return _smoothstep((np.asarray(r, dtype=np.float64) - 1.2) / 0.6)


# Mass-edge profiles fitted by experiments/regime_study.py `edges` (results/
# regime-masses-2026-10-16.md, raw: .local/gesture/out/regime_masses/).
# Units: the mass's equivalent diameter D (= √(4A/π)); spatial frequency in
# cycles per D along the outline.
#   bands    RMS outline deviation from the smoothed core outline per band
#            (0.5–1, 1–2, 2–4, 4–8, 8–16 cycles/D), median over masses. The
#            0.5–1 band is floor-corrected (a smooth 1.6:1 ellipse leaks
#            0.054 D there) and taken at 0.7 — the least certain number. It
#            is synthesised as ring harmonics 2–3 (lobes of the whole mass).
#            Above 1 cycle/D a smooth stadium already measures about as
#            rough as the data (0.019 / 0.012 / 0.008 D vs 0.022 / 0.007 /
#            0.003 D for compact data masses), so only about half the data's
#            value is added there: the wetness is low-order lumpiness, not
#            jitter.
#   skew     a in the negative-skew transform x → (1 − e^(−a·x))/a of the
#            unit noise: rounded outward lobes, sharper inward cusps (data
#            skew −0.2 calligraphy … −0.8 Marden on compact masses)
#   band_sd  log-sd of a per-mass multiplier on all bands (from the IQR of
#            the per-mass roughness: the variety between masses)
#   bays     mean count of EDGE bays per mass (hull pockets deeper than
#            0.06 D that the smoothed core outline does not have)
#   bay_q    bay depth quartiles (D); half of it is used (the measured
#            pockets include the core shape's own concavities)
#   aniso    edge RMS at the mass's ends ÷ at its sides
#   end      width ratio, heavy end third ÷ light end third (median); no
#            gravity preference was measurable (heavy end lower 40–57 %)
#   exits    (share of masses with thin exits, exits per mass, exit length
#            q50 in D) — dry-brush hairs and line exits are not separable at
#            scan resolution
# `reference` = Ian's 2024 image (27 masses), `marden` = Brice Marden
# stick-and-ink (221), `hokusai` = Hokusai brush drawings (810),
# `calligraphy` = the 13 generative-allowed sheets only (371 masses; gated
# by calligraphy.require_generative — the measure-only sheets are reported
# in the results doc and never used here).
WET_PROFILES: dict[str, dict] = {
    "reference": {"bands": (0.068, 0.011, 0.0030, 0.0011, 0.0008), "band_sd": 0.41, "skew": 0.6, "bays": 0.6,
                  "bay_q": (0.098, 0.18, 0.266), "aniso": 0.97, "end": 1.25, "exits": (0.93, 3, 0.18)},
    "marden": {"bands": (0.058, 0.011, 0.0035, 0.0013, 0.0008), "band_sd": 0.35, "skew": 1.1, "bays": 0.8,
               "bay_q": (0.096, 0.148, 0.253), "aniso": 0.66, "end": 1.24, "exits": (1.0, 5, 0.28)},
    "hokusai": {"bands": (0.055, 0.012, 0.0040, 0.0015, 0.0008), "band_sd": 0.38, "skew": 0.4, "bays": 0.8,
                "bay_q": (0.096, 0.154, 0.27), "aniso": 0.98, "end": 1.32, "exits": (0.96, 4, 0.15)},
    "calligraphy": {"bands": (0.012, 0.009, 0.0030, 0.0015, 0.0008), "band_sd": 0.47, "skew": 0.3, "bays": 0.3,
                    "bay_q": (0.105, 0.17, 0.28), "aniso": 1.04, "end": 1.19, "exits": (0.89, 2, 0.18)},
}
WET_BANDS = ((0.5, 1.0), (1.0, 2.0), (2.0, 4.0), (4.0, 8.0), (8.0, 16.0))


def _lognorm_q(rng, q) -> float:
    lo, med, hi = q
    sd = (np.log(hi) - np.log(max(lo, 1e-9))) / (2 * 0.674)
    return float(np.exp(np.log(med) + sd * rng.standard_normal()))


def wet_params(profile, rng: np.random.Generator) -> dict:
    """One mass's edge parameters drawn from a profile (name or dict): the
    band amplitudes get a shared log-normal multiplier plus a small per-band
    one, the bay count is Poisson, the bay depths log-normal — so no two
    masses come out alike."""
    pr = dict(WET_PROFILES[profile]) if isinstance(profile, str) else dict(profile)
    if "base" in pr:
        pr = {**WET_PROFILES[pr["base"]], **pr}
    mult = float(np.exp(pr.get("band_sd", 0.45) * rng.standard_normal())) * pr.get("gain", 1.0)
    bands = [b * mult * float(np.exp(0.25 * rng.standard_normal())) for b in pr["bands"]]
    nb = int(rng.poisson(pr.get("bays", 1.0) * pr.get("gain", 1.0) ** 0.5))
    # measured pockets include shape concavities: half their depth is taken as the edge's own
    bays = [min(0.5 * _lognorm_q(rng, pr["bay_q"]), 0.2) for _ in range(nb)]
    end = float(pr.get("end", 1.2)) ** float(np.exp(0.4 * rng.standard_normal()))
    beta = 1.5 * (end - 1.0) / (end + 1.0)
    return {"bands": bands, "bays": bays, "aniso": float(pr.get("aniso", 1.0)), "beta": beta,
            "skew": float(pr.get("skew", 0.0))}


def _ring_noise(tau: np.ndarray, T: float, bands, rng) -> np.ndarray:
    """Periodic coloured noise over τ ∈ [0, T) (units of D) with the given
    RMS per octave band (cycles per D)."""
    out = np.zeros_like(tau)
    if T <= 0:
        return out
    for bi, ((lo, hi), rms) in enumerate(zip(WET_BANDS, bands)):
        # the lowest band is lumpiness of the WHOLE mass: harmonics 2–3 of
        # the ring (a compact mass has T ≈ π, so that is ≈ 0.6–1 cycle/D);
        # counted per D along a long bar it would make a caterpillar
        ks = np.arange(2, 4) if bi == 0 else np.arange(max(int(np.ceil(lo * T)), 4), int(np.ceil(hi * T)))
        if not len(ks) or rms <= 0:
            continue
        amp = rms * np.sqrt(2.0 / len(ks))
        ph = rng.uniform(0, 2 * np.pi, len(ks))
        out += amp * np.cos(2 * np.pi * np.outer(tau, ks) / T + ph).sum(axis=1)
    return out


def _seed_of(strokes, seed) -> int:
    if seed is not None:
        return int(seed)
    for st in strokes:
        if "seed" in st.meta:
            return int(st.meta["seed"])
    h = 0
    for st in strokes:
        v = np.round(st.points[:: max(len(st) // 16, 1)] * 100).astype(np.int64)
        h = (h * 1000003 + int(np.abs(v).sum()) + 7 * len(st)) % (2 ** 31)
    return h


def _edge_process(strokes, pen: float, wet, edge, seed):
    """→ edge_fn(G, samples) for _geom_parts, or None when nothing applies.
    Per stroke, meta["wet"] / meta["edge"] override the render arguments."""
    wets = [st.meta.get("wet", wet) for st in strokes]
    edges = [st.meta.get("edge", edge) for st in strokes]
    if not any(w for w in wets) and not any(e for e in edges):
        return None
    rng0 = np.random.default_rng(_seed_of(strokes, seed))

    def fn(G, samples):
        from scipy.spatial import cKDTree
        from shapely.geometry import Polygon
        from shapely.geometry.polygon import orient
        from shapely import union_all
        S = _cat_samples(samples)
        tree = cKDTree(S["P"])
        out = []
        for poly0 in _polys(G):
            poly = orient(poly0, 1.0)
            rng = np.random.default_rng(rng0.integers(2 ** 31))
            rings = [np.asarray(poly.exterior.coords)] + [np.asarray(h.coords) for h in poly.interiors]
            new_rings = []
            params = {}
            touched = False
            for ri, rc in enumerate(rings):
                c = _densify(rc, 0.5 * pen)[:-1]
                if len(c) < 8:
                    new_rings.append(rc)
                    continue
                j = _attribute(tree, S["H"], c)
                m = S["m"][j] * S["wet_ok"][j]
                if m.max() < 0.02:
                    new_rings.append(rc)
                    continue
                touched = True
                # fade the edge process out before it reaches a line / nib / drip outline,
                # so a line still enters the mass cleanly (no detached necks)
                from scipy.ndimage import minimum_filter1d
                win = max(int(0.8 * float(np.median(2 * S["H"][j] + pen)) / (0.5 * pen)), 3)
                m = gaussian_filter1d(minimum_filter1d(m, win, mode="wrap"), win / 3, mode="wrap")
                sid = S["sid"][j]
                nxt, prv = np.roll(c, -1, axis=0), np.roll(c, 1, axis=0)
                t = nxt - prv
                t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
                nrm = np.column_stack([t[:, 1], -t[:, 0]])          # out of the ink (orient: ink on the left)
                Wl = 2 * S["H"][j] + pen                            # local ink width
                Deq = np.sqrt(4 / np.pi * Wl * np.clip(S["lrun"][j], Wl, 1.6 * Wl))
                ds = np.linalg.norm(nxt - c, axis=1)
                delta = np.zeros(len(c))
                tan_s = S["tan"][j]
                along = np.abs(np.sum(nrm * tan_s, axis=1))        # 1 at the ends, 0 on the sides
                for k in np.unique(sid):
                    sel = sid == k
                    w_k, e_k = wets[k], edges[k]
                    if w_k:
                        prof = "reference" if w_k is True else w_k
                        if k not in params:
                            params[k] = wet_params(prof, rng)
                        pk = params[k]
                        D_ring = float(np.median(Deq[sel & (m > 0.5)])) if np.any(sel & (m > 0.5)) else float(np.median(Deq[sel]))
                        tau = np.concatenate([[0.0], np.cumsum(ds / np.maximum(Deq, 1e-9))])[:-1]
                        T = float(tau[-1] + ds[-1] / max(Deq[-1], 1e-9))
                        n = _ring_noise(tau, T, pk["bands"], rng)
                        sk = pk["skew"]
                        sd_n = float(np.std(n))
                        if sk > 0 and sd_n > 0:
                            x = (1 - np.exp(-sk * n / sd_n)) / sk
                            n = (x - x.mean()) / max(np.std(x), 1e-12) * sd_n
                        an = pk["aniso"]
                        aw = (1 + (an - 1) * along) / (1 + (an - 1) * 0.5)
                        d_k = n * aw * Deq
                        # bays: narrow inward notches at random massy positions
                        cand = np.flatnonzero(sel & (m > 0.6))
                        s_c = np.concatenate([[0.0], np.cumsum(ds)])[:-1]
                        Pr = s_c[-1] + ds[-1]
                        for dep in pk["bays"]:
                            if not len(cand):
                                break
                            i0 = int(rng.choice(cand))
                            depth = dep * Deq[i0]
                            wid = depth * float(rng.uniform(0.35, 0.8))
                            dd = np.abs(s_c - s_c[i0])
                            dd = np.minimum(dd, Pr - dd)
                            d_k -= depth * np.exp(-0.5 * (dd / max(wid, 1e-9)) ** 2)
                        # pooled end heavier: the run's far end bulges, its start narrows
                        # (elongated runs only: a round blob has no 'end' to pool at)
                        el = _smoothstep((S["lrun"][j] / np.maximum(Wl, 1e-9) - 1.0) / 2.0)
                        d_k += pk["beta"] * Wl * (S["trun"][j] - 0.5) * (1 - along) * el
                        delta[sel] += (m * d_k)[sel]
                    if e_k:
                        delta[sel] += (m * _edge_event(e_k, S, j, nrm, Wl, along))[sel]
                # never eat through the mass nor sprout spikes: |move| bounded by the local width
                delta = np.clip(delta, -0.45 * S["H"][j], 0.3 * Wl)
                new_rings.append(np.vstack([c + delta[:, None] * nrm, c[:1] + delta[0] * nrm[0]]))
            if not touched:
                out.append(poly0)
                continue
            try:
                import shapely
                g = _polygonal(shapely.make_valid(Polygon(new_rings[0], new_rings[1:])))
                g = poly if g is None else g
            except Exception:  # noqa: BLE001 — degenerate ring: keep the clean outline
                g = poly
            out.append(g if not g.is_empty else poly)
        return union_all(out)

    return fn


def _edge_event(spec, S: dict, j: np.ndarray, nrm: np.ndarray, Wl: np.ndarray, along: np.ndarray) -> np.ndarray:
    """A rhythmic edge event over part of one side of a mass (after Oehlen's
    trunks, Baum 44 / 92). spec = {"mode": "scallop" | "notch", "count": 7,
    "amp": 0.18 (× local ink width), "extent": (0.25, 0.75) (stroke arc
    fraction), "side": +1 (left of the stroke's direction, as seen on the
    page with y down: +1 = the side n·(−t_y, t_x) > 0) | −1, "jitter": 0.15}.
    scallop = a run of rounded bumps out of the edge; notch = sharp V cuts in."""
    if isinstance(spec, str):
        spec = {"mode": spec}
    mode = spec.get("mode", "scallop")
    count = float(spec.get("count", 7))
    amp = float(spec.get("amp", 0.18))
    e0, e1 = spec.get("extent", (0.25, 0.75))
    side = float(spec.get("side", 1.0))
    jit = float(spec.get("jitter", 0.15))
    u = S["sfrac"][j]
    tan = S["tan"][j]
    left = np.column_stack([tan[:, 1], -tan[:, 0]])                # +90° from the tangent (y down: page-left)
    on_side = (np.sum(nrm * left, axis=1) * side > 0.3) & (along < 0.75)
    ph = count * (u - e0) / max(e1 - e0, 1e-9)
    # a little irregularity in rhythm (hand-made): phase wobble, per-bump amplitude
    rng = np.random.default_rng(int(spec.get("seed", 0)))
    nb = int(np.ceil(count)) + 2
    ph = ph + jit * np.interp(ph, np.arange(nb) - 1, rng.uniform(-1, 1, nb))
    ampk = 1 + jit * np.interp(ph, np.arange(nb) - 1, rng.uniform(-1, 1, nb))
    win = _smoothstep((u - e0) / max(0.04 * (e1 - e0), 1e-9)) * _smoothstep((e1 - u) / max(0.04 * (e1 - e0), 1e-9))
    x = np.mod(ph, 1.0)
    if mode == "scallop":
        shape = np.sqrt(np.clip(np.sin(np.pi * x), 0, 1))         # round bumps, cusps between
    elif mode == "notch":
        shape = -np.clip(1 - np.abs(2 * x - 1) / 0.35, 0, 1)        # V cuts, flat between
    else:
        raise ValueError(f"unknown edge mode {mode!r}")
    inside = (ph >= 0) & (ph <= count)
    return amp * Wl * ampk * shape * win * on_side * inside


def _chain_fill(paths: list[np.ndarray], pen: float, reach: float = 1.25, look: int = 60) -> list[np.ndarray]:
    """Spiral-like fill: join each fill contour to the next one whose nearest
    vertex is within `reach`·pen of the current end (closed rings are
    rotated to start there, open arcs are reversed if that is nearer). The
    connector crosses ink that the fill inks anyway. Turns ring-per-lift
    into a few long paths, and closes the open graded arcs at a mass's ends
    into a meander."""
    if not paths:
        return []
    rest = [np.asarray(p) for p in paths]
    out = []
    while rest:
        cur = rest.pop(0)
        while True:
            e = cur[-1]
            best, bi, how = reach * pen, -1, None
            for k, p in enumerate(rest[:look]):
                isring = len(p) > 2 and np.allclose(p[0], p[-1])
                if isring:
                    d = np.linalg.norm(p[:-1] - e, axis=1)
                    v = int(np.argmin(d))
                    if d[v] < best:
                        best, bi, how = d[v], k, ("ring", v)
                else:
                    for end, rev in ((0, False), (-1, True)):
                        d = float(np.linalg.norm(p[end] - e))
                        if d < best:
                            best, bi, how = d, k, ("open", rev)
            if bi < 0:
                break
            p = rest.pop(bi)
            if how[0] == "ring":
                rg_ = p[:-1]
                v = how[1]
                p = np.vstack([rg_[v:], rg_[:v], rg_[v:v + 1]])
            elif how[1]:
                p = p[::-1]
            cur = np.vstack([cur, p])
        out.append(cur)
    return out


def _merge_open(paths: list[np.ndarray], tol: float) -> list[np.ndarray]:
    """Join open polylines whose ends coincide (the pieces a clip cuts at a
    ring's seam)."""
    closed = [p for p in paths if len(p) > 2 and np.allclose(p[0], p[-1])]
    opn = [p for p in paths if not (len(p) > 2 and np.allclose(p[0], p[-1]))]
    changed = True
    while changed and len(opn) > 1:
        changed = False
        for i in range(len(opn)):
            for j in range(len(opn)):
                if i == j:
                    continue
                a, b = opn[i], opn[j]
                if np.linalg.norm(a[-1] - b[0]) <= tol:
                    opn[i] = np.vstack([a, b[1:]])
                    opn.pop(j)
                    changed = True
                    break
            if changed:
                break
    return closed + opn


def _splice(runs: list[np.ndarray], rings: list[np.ndarray], tol: float) -> list[np.ndarray]:
    """Fewer pen lifts: a line run whose end touches a ring continues round
    that ring (the line enters its ribbon and draws its outline), and
    open runs that meet end to end are joined."""
    rings = [r.copy() for r in rings]
    used = [False] * len(rings)
    out = []
    for rp in runs:
        path = rp
        for end in (-1, 0):
            pt = path[end]
            best, bi, bj = tol, -1, -1
            for k, rg in enumerate(rings):
                if used[k]:
                    continue
                d = np.linalg.norm(rg[:-1] - pt, axis=1)
                j = int(np.argmin(d))
                if d[j] <= best:
                    best, bi, bj = d[j], k, j
            if bi >= 0:
                rg = rings[bi][:-1]
                loop = np.vstack([rg[bj:], rg[:bj], rg[bj:bj + 1]])
                path = np.vstack([path, loop]) if end == -1 else np.vstack([loop, path])
                used[bi] = True
        out.append(path)
    out = _merge_open(out, tol)
    return out + [rg for rg, u in zip(rings, used) if not u]


def render(strokes, pen: float = 0.35, *, fill: bool = True, step: float | None = None,
           splice: bool = True, min_area: float | None = None, wet=None, edge=None,
           seed: int | None = None, fill_style: str = "concentric", nib_renderer=None) -> list[np.ndarray]:
    """Plotter polylines for one stroke or one MARK (a list of strokes whose
    ribbons are unioned). See the module docstring. Order: line runs (each
    continuing round the outline its end enters), remaining outlines,
    concentric fill contours. Closed contours repeat their first point.

    Optional (defaults keep the round-6 behaviour, apart from the rim fix):
      wet         None/False | True (= "reference") | profile name in
                  WET_PROFILES | dict: wet, irregular mass edges (coloured
                  noise along the outline, bays, a heavier pooled end),
                  weighted by `massness(r)` so lines and nibs are untouched.
      edge        None | "scallop" | "notch" | dict (see `_edge_event`): a
                  rhythmic edge event over part of one side of a mass.
      (a stroke's meta["wet"] / meta["edge"] override these per stroke)
      seed        edge-process seed (default: meta["seed"] or a hash of the
                  geometry — deterministic either way)
      fill_style  "concentric" (one path per inset) | "spiral" (insets
                  chained into few paths; also closes the open graded arcs)
      nib_renderer  callable(strokes=, pen=, paths=, parts=) → paths: a hook
                  for an alternative nib-ribbon renderer (gesture/penrender);
                  parts = {"G", "F", "runs", "rings", "fill"} (shapely
                  geometry and the default polylines)."""
    sts = [strokes] if isinstance(strokes, RegimeStroke) else list(strokes)
    sts = [s for s in sts if len(s)]
    if not sts:
        return []
    G, F, runs, samples = _geom_parts(sts, pen, step, edge_fn=_edge_process(sts, pen, wet, edge, seed))
    ma = (0.02 * pen * pen) if min_area is None else min_area
    rings = _outline_rings(G, pen, ma) if G is not None else []
    paths = _splice(runs, rings, tol=0.05 * pen + 1e-9) if splice else runs + rings
    fp = _fill_paths(G, F, pen, samples) if fill else []
    if fill_style == "spiral":
        fp = _chain_fill(fp, pen)
    elif fill_style != "concentric":
        raise ValueError(f"unknown fill_style {fill_style!r}")
    paths = paths + fp
    paths = [np.asarray(p, dtype=np.float64) for p in paths if len(p) >= 2]
    if nib_renderer is not None:
        paths = nib_renderer(strokes=sts, pen=pen, paths=paths,
                             parts={"G": G, "F": F, "runs": runs, "rings": rings, "fill": fp})
    return paths


def rim_gap(strokes, paths: list[np.ndarray], pen: float = 0.35, *, m_min: float = 0.9) -> float:
    """Widest white gap (mm, 2 × largest inscribed radius) left inside the
    drawn silhouette where the stroke is a full mass (massness ≥ m_min). The
    round-6 rim artefact is a gap > pen between a mass's outline and its
    pooled core; a solid mass has none."""
    import shapely
    from shapely.geometry import LineString, Point
    sts = [strokes] if isinstance(strokes, RegimeStroke) else list(strokes)
    lines = [LineString(p) for p in paths if len(p) >= 2]
    if not lines:
        return 0.0
    U = shapely.union_all(lines)                       # noded
    ink = U.buffer(0.5 * pen)
    sil = shapely.union_all([ink, shapely.polygonize(list(getattr(U, "geoms", [U])))])
    # a white gap counts when the sample that GENERATES the outline there is a full mass
    from scipy.spatial import cKDTree
    P, H, M = [], [], []
    for st in sts:
        a, rho = footprint(st, pen)
        P.append(st.points)
        H.append(a + np.maximum(rho - 0.5 * pen, 0.0))
        M.append(massness(st.r))
    P, H, M = np.vstack(P), np.concatenate(H), np.concatenate(M)
    tree = cKDTree(P)
    white = sil.difference(ink)
    best = 0.0
    for g in _polys(white):
        if g.area < 1e-6:
            continue
        c = shapely.maximum_inscribed_circle(g, tolerance=0.02 * pen)
        x = np.asarray(c.coords[0])[None]
        j = _attribute(tree, H, x)[0]
        if M[j] >= m_min and np.linalg.norm(P[j] - x[0]) <= H[j] + 1e-6:
            best = max(best, 2 * float(c.length))
    return best


def pen_cost(paths: list[np.ndarray]) -> dict:
    """Pen-down length, path count (= pen lifts + 1)."""
    return {"paths": len(paths), "length": float(sum(_plen(p) for p in paths)),
            "points": int(sum(len(p) for p in paths))}


def regime_cost(strokes, paths: list[np.ndarray]) -> dict:
    """Pen-down length of `paths` attributed to the regime of the nearest
    centreline sample: line r < 0.5, nib 0.5 ≤ r < 1.5, shape r ≥ 1.5. Also
    the centreline length per regime (the stroke's own measure), so the
    ratio is the pen cost per mm of stroke in each regime."""
    from scipy.spatial import cKDTree
    sts = [strokes] if isinstance(strokes, RegimeStroke) else list(strokes)
    P, R, segL = [], [], []
    for st in sts:
        q = resample(st, max(st.length() / 2000, 0.05)) if len(st) > 1 else st
        P.append(q.points)
        R.append(q.r)
        d = np.linalg.norm(np.diff(np.vstack([q.points, q.points[:1]]) if q.closed else q.points, axis=0), axis=1)
        segL.append(np.concatenate([d, [0.0]])[:len(q.points)] if not q.closed else d)
    P = np.vstack(P)
    R = np.concatenate(R)
    SL = np.concatenate(segL)
    tree = cKDTree(P)
    bucket = lambda r: np.where(r < 0.5, 0, np.where(r < 1.5, 1, 2))
    pen_len = np.zeros(3)
    for p in paths:
        if len(p) < 2:
            continue
        mid = 0.5 * (p[1:] + p[:-1])
        L = np.linalg.norm(np.diff(p, axis=0), axis=1)
        _, j = tree.query(mid)
        np.add.at(pen_len, bucket(R[j]), L)
    cl = np.zeros(3)
    np.add.at(cl, bucket(R), SL)
    names = ("line", "nib", "shape")
    return {n: {"pen_mm": float(pen_len[i]), "stroke_mm": float(cl[i]),
                "per_mm": float(pen_len[i] / cl[i]) if cl[i] > 0 else float("nan")}
            for i, n in enumerate(names)}


# ---------------------------------------------------------------------------
# field → stroke
# ---------------------------------------------------------------------------

def from_field(points, field_fn, *, phi=np.deg2rad(60.0), W=1.5, mass=None, w_min: float = 0.0,
               smooth: float | None = None, closed: bool = False, step: float | None = None,
               meta: dict | None = None) -> RegimeStroke:
    """r(s) = field_fn(x, y) along `points` (resampled at `step`, default
    W/4), clipped to [0, 2] and Gaussian-smoothed along s at σ = `smooth`
    (default W — a field cannot change regime faster than the nib can).
    phi / W / mass may be scalars or callables (x, y) → value."""
    p = np.asarray(points, dtype=np.float64)
    W0 = float(np.median(W(p[:, 0], p[:, 1]))) if callable(W) else float(np.median(W))
    step = step or max(W0 / 4.0, 0.05)
    base = make(p, 0.0, W=1.0, closed=closed)
    q = resample(base, step).points if len(p) > 1 else p

    def ev(fn):
        if not callable(fn):
            return fn
        try:
            v = np.asarray(fn(q[:, 0], q[:, 1]), dtype=np.float64)
            if v.shape == (len(q),):
                return v
        except Exception:  # noqa: BLE001 — scalar-only field functions
            pass
        return np.array([float(fn(x, y)) for x, y in q])

    r = np.clip(ev(field_fn), 0.0, 2.0)
    sm = W0 if smooth is None else smooth
    if sm > 0 and len(r) > 2:
        r = gaussian_filter1d(r, sm / step, mode="wrap" if closed else "nearest")
    return make(q, r, phi=ev(phi), W=ev(W), mass=None if mass is None else ev(mass), w_min=w_min,
                closed=closed, meta=meta)


# ---------------------------------------------------------------------------
# transition operators (each returns new stroke(s); the input is untouched)
# ---------------------------------------------------------------------------

def _s_frac(st: RegimeStroke) -> tuple[np.ndarray, float]:
    s = arclength(st.points, st.closed)[:len(st)]
    L = max(arclength(st.points, st.closed)[-1], 1e-12)
    return s, L


def _tangent_end(p: np.ndarray, back: float) -> tuple[np.ndarray, float]:
    """Unit tangent at the last point, averaged over the last `back` mm."""
    s = arclength(p)
    j = int(np.searchsorted(s, s[-1] - back))
    j = min(max(j, 0), len(p) - 2)
    d = p[-1] - p[j]
    n = np.linalg.norm(d)
    if n < 1e-12:
        d = p[-1] - p[-2]
        n = np.linalg.norm(d) + 1e-12
    return d / n, float(np.arctan2(d[1], d[0]))


def thicken(st: RegimeStroke, at: float = 0.3, *, ramp: float | None = None, to: float = NIB,
            until: float | None = None, ramp_out: float | None = None) -> RegimeStroke:
    """Line becomes nib: r rises from the stroke's own value to `to` after
    arc fraction `at`, over `ramp` mm (default PROFILE_DEFAULTS["ramp_w"]·W,
    the fitted thin→thick ramp). `until` (fraction) lets it fall back."""
    s, L = _s_frac(st)
    W0 = float(np.median(st.W))
    rp = ramp if ramp is not None else PROFILE_DEFAULTS["ramp_w"] * W0
    s0 = at * L
    g = _smoothstep((s - s0) / max(rp, 1e-9))
    if until is not None:
        ro = ramp_out if ramp_out is not None else rp
        g = g * (1.0 - _smoothstep((s - until * L) / max(ro, 1e-9)))
    r = st.r + (np.maximum(st.r, to) - st.r) * g
    return replace(st, r=r)


def swell(st: RegimeStroke, at: float = 0.5, *, length: float | None = None, peak: float = SHAPE,
          size: float | None = None, kind: str = "bead") -> RegimeStroke:
    """Nib/line becomes mass. kind="bead": a symmetric raised-cosine bump of
    r to `peak` centred at arc fraction `at`, `length` mm long (default
    3·mass) — a bead on a line. kind="vessel": r and the swelling diameter
    grow toward the END of the stroke from `at` on, the nib turning across
    the path so the stroke flares into a wide foot (goblet / trumpet).
    size: swelling diameter (mm) at the peak (default the stroke's mass)."""
    s, L = _s_frac(st)
    mass = st.mass.copy()
    if size is not None:
        mass = np.maximum(mass, 0.0) * 0 + size
    r = st.r.copy()
    if kind == "bead":
        ln = length if length is not None else 3.0 * float(np.median(mass))
        x = (s - at * L) / max(ln / 2.0, 1e-9)
        bump = np.where(np.abs(x) < 1, 0.5 * (1 + np.cos(np.pi * x)), 0.0)
        r = np.maximum(r, peak * bump)
        return replace(st, r=r, mass=np.where(bump > 0, mass, st.mass))
    if kind == "vessel":
        s0 = at * L
        g = np.clip((s - s0) / max(L - s0, 1e-9), 0, 1)
        g2 = g ** 2.2                                 # slow stem, fast flare
        r = np.maximum(r, 1.0 + (peak - 1.0) * g2 * 0.8)
        r = np.where(g > 0, np.maximum(r, np.minimum(1.0, 4 * g)), r)
        # the nib turns across the path and lengthens: a flat, wide foot
        p = st.points
        d = np.gradient(p, axis=0)
        theta = np.arctan2(-d[:, 1], d[:, 0])
        across = theta + np.pi / 2
        dphi = np.angle(np.exp(2j * (across - st.phi))) / 2
        phi = st.phi + dphi * g2
        Wv = st.W * (1.0 + 3.0 * g2)
        return replace(st, r=r, phi=phi, W=Wv, mass=mass * (1.0 + 0.5 * g2))
    raise ValueError(f"unknown swell kind {kind!r}")


def _loop(start: np.ndarray, heading: float, radius: float, turns: float, step: float,
          shrink: float = 0.0, sign: float = 1.0) -> np.ndarray:
    """Tangent-continuous circular (or inward-spiralling) loop from `start`
    at page heading (rad, image coords atan2(dy, dx))."""
    n = max(int(np.ceil(2 * np.pi * radius * turns / step)), 8)
    t = np.linspace(0, 2 * np.pi * turns, n + 1)
    rad = radius * (1.0 - shrink * t / max(t[-1], 1e-9))
    # centre to the left/right of the heading
    nrm = np.array([-np.sin(heading), np.cos(heading)]) * sign
    c = start + nrm * radius
    a0 = np.arctan2(start[1] - c[1], start[0] - c[0])
    ang = a0 + sign * t
    pts = c + np.column_stack([np.cos(ang), np.sin(ang)]) * rad[:, None]
    # keep the start exactly on the incoming line
    return pts - pts[0] + start


def _extend(st: RegimeStroke, ext: np.ndarray, r_ext: np.ndarray, **fields) -> RegimeStroke:
    n = len(ext)
    tail = RegimeStroke(ext, r_ext, fields.get("phi", np.full(n, st.phi[-1])),
                        fields.get("W", np.full(n, st.W[-1])), fields.get("mass", np.full(n, st.mass[-1])),
                        st.w_min, False, None if st.fill is None else fields.get("fill", np.full(n, st.fill[-1])),
                        st.meta)
    return concat(replace(st, closed=False), tail)


def close_fill(st: RegimeStroke, *, radius: float | None = None, amount: float = 1.0,
               side: float = 1.0, step: float | None = None) -> RegimeStroke:
    """Closing and filling: the stroke ends in a loop (tangent-continuous,
    one turn plus a short overlap) whose regime rises to r = 2·amount as it
    goes round: amount 0 = a plain line loop, 0.5 = a nib ring whose counter
    shrinks (a comma / hook), 1 = the counter closes into a filled dot.
    radius default 1.2·W."""
    W0 = float(np.median(st.W))
    rad = radius if radius is not None else 1.2 * W0
    step = step or max(W0 / 6, 0.05)
    u, h = _tangent_end(st.points, 2 * W0)
    loop = _loop(st.points[-1], h, rad, 1.1, step, shrink=0.15 * amount, sign=side)
    g = np.linspace(0, 1, len(loop))
    r0 = st.r[-1]
    peak = max(2.0 * amount, r0)
    r_ext = r0 + (peak - r0) * _smoothstep(g / 0.85)
    # the swelling diameter that closes the counter: ≥ the loop's diameter
    m_ext = np.full(len(loop), max(st.mass[-1], 2.2 * rad * amount))
    return _extend(st, loop, r_ext, mass=m_ext)


def eye(st: RegimeStroke, *, radius: float | None = None, pupil: float | None = None,
        side: float = 1.0, step: float | None = None) -> RegimeStroke:
    """An eye: the stroke stays a line round one loop, then spirals inward
    and swells into a pupil (r → 2) at the centre — loop and dot are one
    continuous stroke. pupil = dot diameter (default 0.8·radius)."""
    W0 = float(np.median(st.W))
    rad = radius if radius is not None else 2.0 * W0
    pd = pupil if pupil is not None else 0.8 * rad
    step = step or max(W0 / 6, 0.05)
    u, h = _tangent_end(st.points, 2 * W0)
    loop = _loop(st.points[-1], h, rad, 1.0, step, sign=side)
    nrm = np.array([-np.sin(h), np.cos(h)]) * side
    centre = st.points[-1] + nrm * rad
    # inward spiral from the loop's end to the centre
    a0 = np.arctan2(loop[-1, 1] - centre[1], loop[-1, 0] - centre[0])
    turns = 0.9
    n = max(int(np.ceil(np.pi * rad * turns / step)), 8)
    t = np.linspace(0, 1, n + 1)[1:]
    ang = a0 + side * 2 * np.pi * turns * t
    rr = rad * (1 - t) ** 1.3
    spiral = centre + np.column_stack([np.cos(ang), np.sin(ang)]) * rr[:, None]
    ext = np.vstack([loop, spiral])
    r_ext = np.concatenate([np.full(len(loop), st.r[-1]),
                            st.r[-1] + (2.0 - st.r[-1]) * _smoothstep((t - 0.55) / 0.4)])
    m_ext = np.full(len(ext), pd)
    return _extend(st, ext, r_ext, mass=m_ext)


def terminal_drop(st: RegimeStroke, *, kind: str = "lozenge", size: float | None = None,
                  step: float | None = None) -> RegimeStroke:
    """The stroke ends in a filled calligraphic dot.

    kind="lozenge" (nuqta): the nib turns into its own thick direction
    (φ + 90°) and makes a short press of length size (default
    PROFILE_DEFAULTS["nuqta_w"]·W): a rhombus whose sides are the nib —
    filled. kind="drop": r swells to 2 at the end, a teardrop of diameter
    size (default bulb_w·W)."""
    W0 = float(np.median(st.W))
    step = step or max(W0 / 8, 0.05)
    p = st.points
    u, h = _tangent_end(p, 2 * W0)
    if kind == "lozenge":
        ln = size if size is not None else PROFILE_DEFAULTS["nuqta_w"] * W0
        phi = float(st.phi[-1])
        thick = np.array([np.cos(phi + np.pi / 2), -np.sin(phi + np.pi / 2)])
        if np.dot(thick, u) < 0:
            thick = -thick
        # a short tangent-continuous hook (≈ 0.6 W) into the thick direction, then the press
        hook_len = 0.6 * W0
        n1 = max(int(hook_len / step), 4)
        tt = np.linspace(0, 1, n1 + 1)[1:]
        dirs = (1 - tt)[:, None] * u + tt[:, None] * thick
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
        hook = p[-1] + np.cumsum(dirs * (hook_len / n1), axis=0)
        n2 = max(int(ln / step), 4)
        press = hook[-1] + np.outer(np.linspace(0, 1, n2 + 1)[1:], thick * ln)
        ext = np.vstack([hook, press])
        r_ext = np.full(len(ext), max(st.r[-1], 1.0))
        r_ext[:n1] = st.r[-1] + (max(st.r[-1], 1.0) - st.r[-1]) * _smoothstep(tt)
        fill = np.concatenate([np.zeros(n1), np.ones(n2)])
        base = st if st.fill is not None else replace(st, fill=st.fill_weight())
        return _extend(base, ext, r_ext, fill=fill, phi=np.full(len(ext), phi))
    if kind == "drop":
        d = size if size is not None else PROFILE_DEFAULTS["bulb_w"] * W0
        ln = 1.2 * d
        n = max(int(ln / step), 6)
        tt = np.linspace(0, 1, n + 1)[1:]
        ext = p[-1] + np.outer(tt * ln, u)
        r_ext = st.r[-1] + (2.0 - st.r[-1]) * _smoothstep(tt / 0.7)
        # the drop sits at the end: shorten so its round end is the stroke end
        return _extend(st, ext[: int(0.75 * n) + 1], r_ext[: int(0.75 * n) + 1],
                       mass=np.full(int(0.75 * n) + 1, d))
    raise ValueError(f"unknown terminal kind {kind!r}")


def _bump(t, c, half):
    x = (t - c) / max(half, 1e-9)
    return np.where(np.abs(x) < 1, 0.5 * (1 + np.cos(np.pi * x)), 0.0)


def _lowfreq(rng, t, n_knots: int = 5) -> np.ndarray:
    """Smooth zero-mean noise in about [−1, 1] over t ∈ [0, 1]."""
    k = np.linspace(0, 1, n_knots)
    return np.interp(t, k, rng.uniform(-1, 1, n_knots))


def shed(st: RegimeStroke, rng: np.random.Generator, *, n: int = 4, kind: str = "drips",
         length: float | None = None, where: tuple[float, float] = (0.0, 1.0),
         wobble: float = 0.15, bead: bool = True) -> list[RegimeStroke]:
    """A mass emits thin lines. Returns [st, child, …] — render them as one
    mark (`render([...])`) and the children's roots merge into the mass's
    outline.

    kind="drips": runs down the page (+y) from the lower part of the swollen
    stretch (samples with r ≥ 1.5 inside `where`). Each drip is a SHAPE-regime
    thread (r = 2, width carried by `mass`, fill = 1, so it is solid at any
    width — no double ribbon): a wet neck that leaves the mass at
    0.15–0.4 of its diameter and thins to a pen line over 12–50 % of its
    length; length log-normal around `length` (default 6·W); a lean and a
    slow curvature walk (`wobble`); sometimes a hanging swelling halfway and,
    if `bead`, a drop at the tip in about half the drips.
    kind="hairs": dry-brush exits past the stroke's end — irregularly spaced
    roots, log-normal lengths, a fan, each a wet wedge that dries into a pen
    line; about a third skip (broken into dashes)."""
    s, L = _s_frac(st)
    W0 = float(np.median(st.W))
    out = [st]
    ln0 = length if length is not None else 6.0 * W0
    if kind == "drips":
        sel = np.flatnonzero((st.r >= 1.5) & (s >= where[0] * L) & (s <= where[1] * L))
        if not len(sel):
            sel = np.flatnonzero((s >= where[0] * L) & (s <= where[1] * L))
        picks = np.sort(rng.choice(sel, size=min(n, len(sel)), replace=False))
        a, rho = footprint(st, 0.0)
        for j in picks:
            reach = 0.6 * (rho[j] + a[j] * abs(np.cos(st.phi[j])))
            root = st.points[j] + np.array([0.0, reach])
            ln = ln0 * float(np.clip(np.exp(0.5 * rng.standard_normal()), 0.3, 2.5))
            stepd = max(min(W0 / 5, ln / 40), 0.03)
            m = max(int(ln / stepd), 12)
            t = np.linspace(0, 1, m)
            # heading: down, a lean, a slow curvature walk
            lean = rng.normal(0, 0.09)
            curv = np.cumsum(rng.normal(0, wobble * 0.6 / np.sqrt(m), m))
            th = np.pi / 2 + lean + curv - curv[0]
            dxy = np.column_stack([np.cos(th), np.sin(th)]) * (ln / (m - 1))
            pts = root + np.vstack([[0, 0], np.cumsum(dxy[:-1], axis=0)])
            md = float(st.mass[j])
            w0 = md * float(rng.uniform(0.15, 0.4))
            tn = float(rng.uniform(0.12, 0.5))
            w = w0 * (1 - _smoothstep(t / tn)) ** 1.5 * (1 + 0.25 * _lowfreq(rng, t))
            if rng.random() < 0.3:                                   # a hanging swelling on the way
                c = float(rng.uniform(0.4, 0.75))
                w = np.maximum(w, w0 * float(rng.uniform(0.45, 0.85)) * _bump(t, c, float(rng.uniform(0.03, 0.06))))
            if bead and rng.random() < 0.5:                          # sometimes a drop at the tip
                d = w0 * float(rng.uniform(0.5, 1.0))
                c = 1.0 - 0.5 * d / ln
                w = np.maximum(w, d * np.sqrt(np.clip(1 - ((t - c) / max(0.5 * d / ln, 1e-9)) ** 2, 0, 1)))
            out.append(RegimeStroke(pts, np.full(m, 2.0), np.full(m, st.phi[j]), np.full(m, 1e-3 * W0),
                                    np.maximum(w, 0.0), st.w_min, False, np.ones(m), {"shed": "drip"}))
        return out
    if kind == "hairs":
        u, h = _tangent_end(st.points, 2 * W0)
        nrm = np.array([-u[1], u[0]])
        a, rho = footprint(st, 0.0)
        half = max(rho[-1] + a[-1], 0.5 * W0)
        offs = np.sort(rng.uniform(-0.75, 0.75, n)) * half
        spread = float(rng.uniform(0.12, 0.35))
        for k, off in enumerate(offs):
            root = st.points[-1] - 0.8 * half * u + off * nrm
            ln = ln0 * float(np.clip(np.exp(0.45 * rng.standard_normal()), 0.25, 2.2))
            m = max(int(ln / (W0 / 5)), 12)
            t = np.linspace(0, 1, m)
            fan = off / max(half, 1e-9) * spread + rng.normal(0, 0.05)
            dirv = u + fan * nrm
            dirv /= np.linalg.norm(dirv)
            lat = np.cumsum(rng.normal(0, wobble * W0 / np.sqrt(m), m))
            pts = root + np.outer(t * ln, dirv) + np.outer(lat - lat[0], nrm)
            # a wet wedge (shape regime) that dries into a pen line
            td = float(rng.uniform(0.1, 0.3))
            wr = 2 * half / max(n, 1) * float(rng.uniform(0.6, 1.2))
            w = wr * (1 - _smoothstep(t / td))
            r = np.full(m, 2.0)
            child = RegimeStroke(pts, r, np.full(m, st.phi[-1]), np.full(m, 1e-3 * W0), w, st.w_min, False,
                                 np.ones(m), {"shed": "hair"})
            if rng.random() < 0.35:                                  # dry skip: broken into dashes
                cuts = np.sort(rng.uniform(td + 0.1, 0.95, int(rng.integers(1, 3))))
                keep = np.ones(m, bool)
                for c in cuts:
                    keep &= np.abs(t - c) > float(rng.uniform(0.02, 0.05))
                idx = np.flatnonzero(keep)
                for seg in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1):
                    if len(seg) >= 2:
                        out.append(RegimeStroke(pts[seg], r[seg], child.phi[seg], child.W[seg], w[seg], st.w_min,
                                                False, np.ones(len(seg)), {"shed": "hair"}))
            else:
                out.append(child)
        return out
    raise ValueError(f"unknown shed kind {kind!r}")
