# FROZEN from research commit 6f96418: tools/gesture/gesture/penrender.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Nib ribbons that read as ink at real pen widths.

Round 6 found that at a 0.35 mm pen an outline-only nib ribbon (regime.py,
r ≤ 1.1) reads as a hollow double line, "a pipe". This module renders the
same RegimeStroke marks with several fill strategies and simulates what a
plot looks like on paper, so the choice is judged on the physical result
and not on hairline previews.

=========================================================================
INTERFACE
=========================================================================

    from . import penrender as pr

    pr.STRATEGIES                          # name -> factory(**params) -> renderer
    rend = pr.strategy("e")                # a renderer
    paths = rend(strokes, pen=0.4)         # same call shape as regime.render
    paths.pens                             # per-path pen width (mm), same order

A renderer is a callable `(strokes, pen=0.35, *, paths=None, parts=None,
**kw) -> PenPaths`. Standalone it takes what `regime.render` takes (one
RegimeStroke or a list rendered as ONE mark). It is also regime.render's
`nib_renderer` hook, which calls it as
`(strokes=, pen=, paths=<default polylines>, parts={"G","F","runs","rings","fill"})`:

    rg.render(stroke, 0.4, nib_renderer=pr.strategy("e"), wet=True)

Strategies a, c, e, f then build on regime's own paths and geometry (so
wet / edge processes survive). b, b+ and d change fill weights and
re-render, so through the hook they drop wet/edge options: call them
directly. `PenPaths` is a plain `list[np.ndarray]` with `.pens`; only "f"
(two pens) holds two widths; `layers(paths)` splits it per pen.

Strategies (letters as in results/penrender-2026-10-16.md):

    a   outline           regime.render unchanged (nib = two edges)
    b   inset_narrow      outline + concentric insets, forced full where the
                          ribbon is narrower than k·pen (default 6), fading
                          out above 1.5·k (wide ribbons keep a pooled core)
    b+  inset_full        concentric insets everywhere a nib exists
    c   lanes             outline + passes parallel to the centreline at
                          fixed normal offsets (0.85 pen apart), each pass
                          switched on where the local half-width can hold it;
                          chained boustrophedon through already-inked ground
    d   collapse          where the ink is narrower than t·pen (t = 1.2) the
                          ribbon becomes its centreline (a regime change to
                          line), the rest as b+
    e   nib_traces        outline + the paths of points ALONG THE NIB EDGE
                          (c + λ·a·u(φ)): each pass is the centreline
                          translated along the nib, the way a real broad nib
                          inks; passes thin out dyadically where the stroke
                          runs along the nib (hairlines), so they never pile
                          up there
    f   two_pen           thin pen: outline, lines and the parts narrower
                          than the marker; marker (default max(1.0, 2.5·pen)
                          mm): concentric insets of the ink eroded by its
                          half-width. Two layers, one pen swap.

Masses (r > 1) keep regime's concentric fill in every strategy, made solid
earlier (fill weight smoothstep((r − 1)/0.25)), so strategies differ only
in how a NIB ribbon is inked. Everything is a polyline that runs along the
stroke or round it. Nothing hatches across it.

Physical preview: `ink_raster(paths, box, px_per_mm=20, spread=...)` sweeps
a disc of the pen's real width (+ ink spread) along every path, and
`ideal_raster(strokes, pen, box)` is the solid ribbon the nib would leave
(regime's ink region), rendered with the same spread and blur. `evaluate`
compares the two and adds pen cost and an estimated plot time (the
trapezoid/junction model of axibridge/estimate.py, re-implemented here
because the gesture venv has no pydantic).
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
from scipy.ndimage import binary_erosion, distance_transform_edt, gaussian_filter, gaussian_filter1d

from . import regime as rg

__all__ = [
    "PenPaths", "STRATEGIES", "strategy", "layers", "ideal_ink", "ink_raster", "ideal_raster",
    "evaluate", "plot_time", "chain", "MOTION",
]

LANE_SPACING = 0.85        # passes this many pen widths apart (15 % overlap)
LANE_COVER = 0.95          # a new pass is switched on before a gap exceeds this × pen


class PenPaths(list):
    """list[np.ndarray] of polylines plus `.pens` (pen width per path, mm)."""

    def __init__(self, paths=(), pens=None, pen: float = 0.35):
        super().__init__(np.asarray(p, dtype=np.float64) for p in paths)
        self.pens = list(pens) if pens is not None else [float(pen)] * len(self)
        if len(self.pens) != len(self):
            raise ValueError("pens must match paths")


def layers(paths) -> dict[float, list[np.ndarray]]:
    """Split a PenPaths into {pen width: paths}, in drawing order per pen."""
    pens = getattr(paths, "pens", None) or [None] * len(paths)
    out: dict = {}
    for p, w in zip(paths, pens):
        out.setdefault(w, []).append(p)
    return out


# ---------------------------------------------------------------------------
# helpers on regime's geometry
# ---------------------------------------------------------------------------

def _as_list(strokes) -> list:
    sts = [strokes] if isinstance(strokes, rg.RegimeStroke) else list(strokes)
    return [s for s in sts if len(s)]


def _mass_fill(st: rg.RegimeStroke) -> rg.RegimeStroke:
    """Masses solid sooner: f = smoothstep((r − 1)/0.25) unless the stroke
    carries its own fill weights (then the larger of the two)."""
    f = rg._smoothstep((st.r - 1.0) / 0.25)
    if st.fill is not None:
        f = np.maximum(f, st.fill)
    return replace(st, fill=f)


def _with_fill(st: rg.RegimeStroke, f: np.ndarray) -> rg.RegimeStroke:
    return replace(st, fill=np.clip(np.maximum(f, _mass_fill(st).fill), 0.0, 1.0))


def ideal_ink(strokes, pen: float = 0.35, parts: dict | None = None):
    """The solid ink region the mark stands for (shapely geometry, mm):
    the pen-centre region dilated by pen/2, plus line runs swept by the pen.
    This is what a real nib/brush would leave, i.e. the target."""
    import shapely
    from shapely.geometry import LineString
    sts = _as_list(strokes)
    if parts is not None:
        G, runs = parts["G"], parts["runs"]
    else:
        G, _, runs, _ = rg._geom_parts(sts, pen, None)
    parts = []
    if G is not None and not G.is_empty:
        parts.append(G.buffer(0.5 * pen, quad_segs=16))
    for r in runs:
        if len(r) >= 2:
            parts.append(LineString(r).buffer(0.5 * pen, quad_segs=16))
        elif len(r) == 1:
            parts.append(shapely.Point(r[0]).buffer(0.5 * pen))
    return shapely.union_all(parts) if parts else None


def _centre_frame(st: rg.RegimeStroke, pen: float):
    """Resampled centreline with footprint, tangent/normal and the pen-centre
    half-width h across the path (ink half-width = h + pen/2)."""
    q, a, rr, uvec, _ = rg._prep(st, pen, None)
    p = q.points
    if len(p) < 3:
        return None
    if q.closed:
        ext = np.vstack([p[-3:], p, p[:3]])
        t = np.gradient(ext, axis=0)[3:-3]
    else:
        t = np.gradient(p, axis=0)
    sd = 1.0  # samples are 0.5 pen apart: σ = 1 sample ≈ half a pen
    t = np.column_stack([gaussian_filter1d(t[:, 0], sd, mode="wrap" if q.closed else "nearest"),
                         gaussian_filter1d(t[:, 1], sd, mode="wrap" if q.closed else "nearest")])
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    nrm = np.column_stack([-t[:, 1], t[:, 0]])
    # nib-across extent: |u × t| = |sin(θ − φ)|
    sin = np.abs(uvec[:, 0] * t[:, 1] - uvec[:, 1] * t[:, 0])
    h = a * sin + rr
    return {"q": q, "p": p, "a": a, "rr": rr, "u": uvec, "t": t, "n": nrm, "h": h,
            "f": _mass_fill(q).fill, "closed": q.closed}


def _runs(mask: np.ndarray, closed: bool) -> list[np.ndarray]:
    idx = np.flatnonzero(mask)
    if not len(idx):
        return []
    if closed and mask.all():
        return [np.r_[np.arange(len(mask)), 0]]
    cuts = np.flatnonzero(np.diff(idx) > 1)
    segs = np.split(idx, cuts + 1)
    if closed and len(segs) > 1 and mask[0] and mask[-1]:
        segs = [np.r_[segs[-1], segs[0]]] + segs[1:-1]
    return segs


def _plen(p) -> float:
    return rg._plen(p)


def _clip(paths, region, *, inside: bool = True, min_len: float = 0.0) -> list[np.ndarray]:
    """Keep the parts of open polylines inside (or outside) a region."""
    from shapely.geometry import LineString
    if region is None or region.is_empty:
        return [p for p in paths] if inside is False else []
    from shapely.prepared import prep
    pr_ = prep(region)
    out = []
    for p in paths:
        if len(p) < 2:
            continue
        ls = LineString(p)
        if inside and pr_.contains(ls):
            out.append(p)
            continue
        if not inside and not pr_.intersects(ls):
            out.append(p)
            continue
        g = ls.intersection(region) if inside else ls.difference(region)
        for x in rg._lines(g):
            c = np.asarray(x.coords)
            if len(c) >= 2 and _plen(c) >= min_len:
                out.append(c)
    return out


# ---------------------------------------------------------------------------
# chaining: fewer pen lifts, connectors only over ground already inked
# ---------------------------------------------------------------------------

def _coverage_mask(paths, pen: float, box, pxmm: float):
    x0, y0, x1, y1 = box
    W = int(np.ceil((x1 - x0) * pxmm)) + 1
    H = int(np.ceil((y1 - y0) * pxmm)) + 1
    from PIL import Image, ImageDraw
    img = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(img)
    rpx = 0.5 * pen * pxmm
    lw = max(int(round(pen * pxmm)), 1)
    for p in paths:
        q = (np.asarray(p) - [x0, y0]) * pxmm
        if len(q) >= 2:
            dr.line([tuple(v) for v in q], fill=255, width=lw, joint="curve")
        for v in (q[0], q[-1]):
            dr.ellipse([v[0] - rpx, v[1] - rpx, v[0] + rpx, v[1] + rpx], fill=255)
    m = np.asarray(img) > 127
    # a connector inks a disc of pen/2 around itself: it is invisible where
    # that whole disc is already ink → erode by pen/2 (less 1 px of slack)
    k = max(int(np.floor(0.5 * pen * pxmm)) - 1, 0)
    if k > 0:
        yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
        m = binary_erosion(m, structure=(xx * xx + yy * yy) <= k * k)
    return m


def chain(paths, pen: float, *, max_jump: float | None = None, pxmm: float = 20.0) -> list[np.ndarray]:
    """Greedy path chaining. From the end of the current path, jump to the
    nearest unvisited path end (a closed ring may be entered at any vertex)
    if the straight connector is ≤ max_jump and runs entirely over ground the
    paths already ink (so the connector adds no visible mark). Otherwise
    lift the pen. Order: start from the first path, nearest-neighbour."""
    paths = [np.asarray(p, dtype=np.float64) for p in paths if len(p) >= 2]
    if len(paths) < 2:
        return paths
    max_jump = 6.0 if max_jump is None else max_jump
    P = np.vstack(paths)
    m = 2 * pen + 2.0 / pxmm
    box = (P[:, 0].min() - m, P[:, 1].min() - m, P[:, 0].max() + m, P[:, 1].max() + m)
    mask = _coverage_mask(paths, pen, box, pxmm)
    Hm, Wm = mask.shape

    def ok(a, b) -> bool:
        d = float(np.linalg.norm(b - a))
        if d > max_jump:
            return False
        if d <= 0.5 * pen:
            return True
        n = int(np.ceil(d * pxmm * 1.5)) + 1
        t = np.linspace(0, 1, n)[:, None]
        s = (a + t * (b - a) - [box[0], box[1]]) * pxmm
        ix = np.clip(np.round(s[:, 0]).astype(int), 0, Wm - 1)
        iy = np.clip(np.round(s[:, 1]).astype(int), 0, Hm - 1)
        return bool(mask[iy, ix].all())

    closed = [len(p) > 2 and np.allclose(p[0], p[-1]) for p in paths]
    left = list(range(len(paths)))
    out = []
    cur = paths[left.pop(0)]
    while left:
        end = cur[-1]
        cands = []
        for k in left:
            p = paths[k]
            if closed[k]:
                d = np.linalg.norm(p[:-1] - end, axis=1)
                j = int(np.argmin(d))
                cands.append((float(d[j]), k, "ring", j))
            else:
                d0 = float(np.linalg.norm(p[0] - end))
                d1 = float(np.linalg.norm(p[-1] - end))
                cands.append((d0, k, "fwd", 0) if d0 <= d1 else (d1, k, "rev", 0))
        cands.sort(key=lambda c: c[0])
        joined = False
        for d, k, how, j in cands[:6]:
            p = paths[k]
            if how == "ring":
                rgp = p[:-1]
                nxt = np.vstack([rgp[j:], rgp[:j], rgp[j:j + 1]])
            elif how == "rev":
                nxt = p[::-1]
            else:
                nxt = p
            if ok(end, nxt[0]):
                cur = np.vstack([cur, nxt])
                left.remove(k)
                joined = True
                break
        if not joined:
            out.append(cur)
            k = cands[0][1]
            left.remove(k)
            cur = paths[k]
    out.append(cur)
    return out


# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------

def _base(sts, pen, *, fill=True, splice=True):
    """regime.render with masses made solid sooner."""
    return rg.render([_mass_fill(s) for s in sts], pen, fill=fill, splice=splice)


def _lanes_c(fr, pen: float) -> list[np.ndarray]:
    """(c) passes at fixed normal offsets j·s (s = 0.85 pen), on where the
    half-width can hold them: pass j (|j| ≥ 1) appears when the gap from
    pass j−1 to the edge exceeds 0.95 pen (it is then 0.1 pen inside the
    edge, so it peels off the outline tangentially); the centre pass when
    the gap between the two edges does."""
    sp = LANE_SPACING * pen
    cov = LANE_COVER * pen
    h, p, nrm = fr["h"], fr["p"], fr["n"]
    live = fr["f"] < 0.95
    J = int(np.ceil(h.max(initial=0.0) / sp)) + 1
    out = []
    for j in range(-J, J + 1):
        if j == 0:
            on = (2 * h > cov) & live
        else:
            on = (h > (abs(j) - 1) * sp + cov) & live
        for seg in _runs(on, fr["closed"]):
            if len(seg) < 2:
                continue
            c = p[seg] + (j * sp) * nrm[seg]
            if _plen(c) >= pen:
                out.append(c)
    return out


def _lanes_e(fr, pen: float) -> list[np.ndarray]:
    """(e) traces of points along the nib edge, c + λ·a·u. Interior λ only
    (the outline is the λ = ±1 trace). N − 1 = 2^m ≥ 2·a_max / s. Where the
    stroke runs along the nib the traces crowd together: pass j is on only
    where its dyadic level is needed to keep neighbouring passes ≤ 0.95 pen
    apart across the path."""
    a, u, p, t = fr["a"], fr["u"], fr["p"], fr["t"]
    sin = np.abs(u[:, 0] * t[:, 1] - u[:, 1] * t[:, 0])
    live = fr["f"] < 0.95
    amax = float(a.max(initial=0.0))
    cov = LANE_COVER * pen
    if 2 * amax <= cov:
        return []
    m = int(np.ceil(np.log2(max(2 * amax / (LANE_SPACING * pen), 1.0))))
    N1 = 2 ** max(m, 1)                      # intervals between λ = −1 … 1
    d1 = 2 * a * sin / N1                    # across-path gap between adjacent traces
    out = []
    for j in range(1, N1):
        # dyadic level of j: it is needed when the stride 2^lvl·d1 > cov
        lvl = (j & -j).bit_length() - 1      # trailing zeros
        stride = 2 ** (lvl + 1)              # gap that opens if j is missing
        on = (stride * d1 > cov) & live
        lam = -1.0 + 2.0 * j / N1
        for seg in _runs(on, fr["closed"]):
            if len(seg) < 2:
                continue
            c = p[seg] + (lam * a[seg])[:, None] * u[seg]
            if _plen(c) >= pen:
                out.append(c)
    return out


def touch_up(paths, ink, pen: float, *, min_area: float | None = None) -> list[np.ndarray]:
    """Close what a fill left white inside the ideal ink: holes = ink (less
    a 0.05-pen rim) minus the drawn coverage; each hole bigger than about a
    third of a pen across gets its own concentric rings (every 0.85 pen,
    first 0.3 pen in, or 0.1 pen for a hole too thin for that). This is where
    a mass's round cap meets a nib that the lanes cannot reach, and the
    spine a last inset leaves. Rings, so still no hatching."""
    import shapely
    from shapely.geometry import LineString
    if ink is None or ink.is_empty or not paths:
        return []
    cov = shapely.union_all([LineString(p).buffer(0.49 * pen, quad_segs=6) for p in paths if len(p) >= 2])
    hole = ink.buffer(-0.05 * pen).difference(cov)
    ma = (0.35 * pen) ** 2 if min_area is None else min_area
    out = []
    for h in rg._polys(hole):
        if h.area < ma:
            continue
        g = h.buffer(-0.3 * pen)
        if g.is_empty:
            g = h.buffer(-0.1 * pen)
        k = 0
        while not g.is_empty and k < 100:
            for poly in rg._polys(g):
                out.append(rg._ring(poly.exterior.coords))
                out += [rg._ring(i.coords) for i in poly.interiors]
            g = g.buffer(-LANE_SPACING * pen)
            k += 1
    return [o for o in out if len(o) >= 3]


def _lane_strategy(kind: str, patch: bool = True):
    def render(strokes, pen: float = 0.35, *, max_jump: float | None = None, paths=None, parts=None, **_):
        sts = _as_list(strokes)
        if not sts:
            return PenPaths([], pen=pen)
        # as regime.render's nib_renderer hook: build on its paths/geometry
        # (keeps wet / edge processes); standalone: masses solid sooner
        base = list(paths) if paths is not None else _base(sts, pen)
        G = parts["G"] if parts is not None else rg._geom_parts(sts, pen, None)[0]
        lanes = []
        for st in sts:
            fr = _centre_frame(st, pen)
            if fr is None:
                continue
            lanes += _lanes_c(fr, pen) if kind == "c" else _lanes_e(fr, pen)
        # passes stay inside the pen-centre region (a pass on a tight inner
        # turn can swing past the ribbon's edge)
        if G is not None and lanes:
            lanes = _clip(lanes, G.buffer(0.05 * pen), inside=True, min_len=pen)
        drawn = list(base) + lanes
        if patch:
            drawn += touch_up(drawn, ideal_ink(sts, pen, parts), pen)
        paths = chain(drawn, pen, max_jump=max_jump)
        return PenPaths(paths, pen=pen)
    render.__name__ = f"lanes_{kind}"
    return render


def outline(**_):
    """(a) regime.render unchanged."""
    def render(strokes, pen: float = 0.35, *, paths=None, **kw):
        return PenPaths(rg.render(strokes, pen) if paths is None else paths, pen=pen)
    return render


def inset(k: float | None = 6.0):
    """(b) / (b+): concentric insets forced full where the ink width is
    below k·pen (fading out by 1.5·k); k=None fills every nib."""
    def render(strokes, pen: float = 0.35, *, max_jump: float | None = None, **_):
        sts = []
        for st in _as_list(strokes):
            w = rg.ink_width(st, pen, sigma=2.0)
            nib = rg._smoothstep(st.r / 0.3)                     # any nib at all
            if k is None:
                f = nib
            else:
                f = nib * (1.0 - rg._smoothstep((w / pen - k) / (0.5 * k)))
            sts.append(_with_fill(st, f))
        paths = rg.render(sts, pen, fill=True)
        return PenPaths(chain(paths, pen, max_jump=max_jump), pen=pen)
    return render


def collapse(t: float = 1.2):
    """(d) ink narrower than t·pen → the ribbon becomes its centreline
    (r scaled down smoothly, σ = 1 mm along the stroke); the rest as b+."""
    fill_all = inset(None)

    def render(strokes, pen: float = 0.35, **kw):
        sts = []
        for st in _as_list(strokes):
            w = rg.ink_width(st, pen, sigma=2.0)
            g = rg._smoothstep((w / pen - t) / 0.5)
            r = np.where(st.r <= 1.0, st.r * g, st.r)
            if len(st) > 3:
                s = rg.arclength(st.points, st.closed)[:len(st)]
                ds = max(float(np.median(np.diff(s))) if len(s) > 1 else 1.0, 1e-6)
                r = gaussian_filter1d(r, 1.0 / ds, mode="wrap" if st.closed else "nearest")
                r = np.where(st.r > 1.0, st.r, np.minimum(r, st.r))
            sts.append(replace(st, r=r))
        return fill_all(sts, pen, **kw)
    return render


def lanes(patch: bool = True):
    """(c) passes along the stroke at fixed normal offsets (+ touch_up)."""
    return _lane_strategy("c", patch)


def nib_traces(patch: bool = True):
    """(e) passes = traces of points along the nib edge (+ touch_up)."""
    return _lane_strategy("e", patch)


def two_pen(thick: float | None = None, *, thin_strategy: str = "e", misreg=(0.0, 0.0)):
    """(f) thin pen + marker. Marker: concentric insets (every 0.85·P) of
    the ideal ink eroded by P/2 — it reaches the ink edge exactly where it
    fits. Thin pen: outline + line runs everywhere (crisp edges) + its own
    passes only outside the marker's reach (overlapping it by pen/2).
    `misreg` shifts the marker layer (mm) to simulate pen-swap registration
    error in previews; it is NOT applied to the geometry unless asked."""
    thin_r = STRATEGIES[thin_strategy]()

    def render(strokes, pen: float = 0.35, *, max_jump: float | None = None, apply_misreg=False,
               paths=None, parts=None, **_):
        sts = _as_list(strokes)
        P = float(thick) if thick is not None else max(1.0, 2.5 * pen)
        ink = ideal_ink(sts, pen, parts)
        if ink is None:
            return PenPaths([], pen=pen)
        Mc = ink.buffer(-0.5 * P, quad_segs=16)
        mpaths = []
        if not Mc.is_empty:
            g = Mc
            k = 0
            last = False
            while not g.is_empty and k < 200:
                for poly in rg._polys(g):
                    if poly.area < 1e-4:
                        continue
                    mpaths.append(rg._ring(poly.exterior.coords))
                    mpaths += [rg._ring(h.coords) for h in poly.interiors]
                nxt = g.buffer(-LANE_SPACING * P, quad_segs=16)
                if nxt.is_empty and not last:
                    # what is left is < 1.7 P wide: one more ring half a
                    # marker in closes the spine the last ring would leave
                    nxt = g.buffer(-0.45 * P, quad_segs=16)
                    last = True
                elif last:
                    break
                g = nxt
                k += 1
        reach = Mc.buffer(0.5 * P, quad_segs=16) if not Mc.is_empty else None
        thin_all = thin_r(sts, pen, max_jump=max_jump, paths=paths, parts=parts)
        # keep the thin pen's outline / line runs (exact silhouette), drop
        # its fill where the marker inks anyway
        G = parts["G"] if parts is not None else rg._geom_parts(sts, pen, None)[0]
        edge = None
        if G is not None:
            from shapely.geometry import LineString
            import shapely
            edge = shapely.union_all([LineString(rg._ring(pl.exterior.coords)) for pl in rg._polys(G)]
                                     + [LineString(rg._ring(h.coords)) for pl in rg._polys(G)
                                        for h in pl.interiors]).buffer(0.3 * pen)
        thin = []
        if reach is not None:
            core = reach.buffer(-0.5 * pen)
            if edge is not None:
                core = core.difference(edge)
            thin = _clip(thin_all, core, inside=False, min_len=0.5 * pen)
        else:
            thin = list(thin_all)
        # what neither pen reached (marker spine, clip seams): thin-pen rings
        cover = thin + [m for m in mpaths]
        if cover:
            import shapely
            from shapely.geometry import LineString
            cov_m = shapely.union_all([LineString(m).buffer(0.49 * P, quad_segs=6) for m in mpaths]) \
                if mpaths else None
            thin_poly = [t for t in thin]
            extra = touch_up(thin_poly, ink.difference(cov_m) if cov_m is not None else ink, pen)
            thin += extra
        thin = chain(thin, pen, max_jump=max_jump)
        mpaths = chain(mpaths, P, max_jump=max_jump)
        if apply_misreg and any(misreg):
            mpaths = [m + np.asarray(misreg) for m in mpaths]
        return PenPaths(thin + mpaths, pens=[pen] * len(thin) + [P] * len(mpaths))
    return render


STRATEGIES = {
    "a": outline,
    "b": inset,
    "b+": lambda **kw: inset(None),
    "c": lanes,
    "d": collapse,
    "e": nib_traces,
    "f": two_pen,
}
NAMES = {"a": "outline (current)", "b": "inset, narrow full", "b+": "inset, full",
         "c": "lanes along stroke", "d": "collapse <1.2p + inset", "e": "nib-point traces",
         "f": "two pens (thin + marker)"}


def strategy(name: str, **params):
    """A renderer `(strokes, pen=0.35, **kw) -> PenPaths` by letter."""
    return STRATEGIES[name](**params)


# ---------------------------------------------------------------------------
# nib styles: Ian's options (2026-10-16) — b, c and e, alone or combined
# ---------------------------------------------------------------------------

STYLE_PARTS = ("b", "b+", "c", "e")


def combined(names, patch: bool = True):
    """One renderer from several parts: at most one inset fill (b or b+)
    plus any of the pass families (c: along the stroke, e: nib-point
    traces). The outline and the mass fill are drawn once; the passes of
    every family are added on top, then one touch-up and one chaining —
    so 'c+e' does not double the outline."""
    names = [n for n in names]
    bad = [n for n in names if n not in STYLE_PARTS]
    if bad or not names:
        raise ValueError(f"nib style parts must be from {STYLE_PARTS}, got {names}")
    fills = [n for n in names if n in ("b", "b+")]
    if len(fills) > 1:
        raise ValueError("combine at most one of b / b+")
    kinds = [n for n in dict.fromkeys(names) if n in ("c", "e")]
    fill_r = inset(None if fills and fills[0] == "b+" else 6.0) if fills else None

    def render(strokes, pen: float = 0.35, *, max_jump: float | None = None, paths=None, parts=None, **_):
        sts = _as_list(strokes)
        if not sts:
            return PenPaths([], pen=pen)
        if fill_r is not None:
            base = list(fill_r(sts, pen, max_jump=max_jump))
        else:
            base = list(paths) if paths is not None else _base(sts, pen)
        if not kinds:
            return PenPaths(chain(base, pen, max_jump=max_jump), pen=pen)
        G = parts["G"] if parts is not None else rg._geom_parts(sts, pen, None)[0]
        lanes = []
        for st in sts:
            fr = _centre_frame(st, pen)
            if fr is None:
                continue
            for kind in kinds:
                lanes += _lanes_c(fr, pen) if kind == "c" else _lanes_e(fr, pen)
        if G is not None and lanes:
            lanes = _clip(lanes, G.buffer(0.05 * pen), inside=True, min_len=pen)
        drawn = base + lanes
        if patch:
            drawn += touch_up(drawn, ideal_ink(sts, pen, parts), pen)
        return PenPaths(chain(drawn, pen, max_jump=max_jump), pen=pen)
    render.__name__ = "nib_" + "+".join(names)
    return render


def _mark_key(strokes) -> int:
    """A stable integer per mark (rounded geometry), for per-mark mixing."""
    pts = np.vstack([np.asarray(s.points, float)[[0, -1]] for s in _as_list(strokes)])
    return int(abs(hash(tuple(np.round(pts, 2).ravel().tolist()))) % (2 ** 31))


def nib_style(spec, *, seed: int = 0):
    """The nib-ribbon renderer for a style spec, or None for the default
    outline (regime.render unchanged). Accepted specs:

      None / "a"            outline (current behaviour)
      "b", "b+", "c", "e"   one strategy (see the letters above)
      ["b+", "c"], ["c", "e"], ["b", "c", "e"]   a COMBINATION
                            (`combined`): one inset fill and/or several pass
                            families — the list form is unambiguous
      "c+e", "b++c+e"       the same as a string ('+' separates parts, so
                            "b+c" = narrow inset b + c; write "b++c" or use
                            the list form for full inset b+ with c)
      {"c": .5, "e": .5}    a per-mark MIX: each mark draws one style (any
                            of the above, combinations allowed) with these
                            weights, deterministically from (seed, mark)

    Usable standalone or as regime.render's `nib_renderer` hook."""
    if spec is None or spec == "a":
        return None
    if isinstance(spec, (list, tuple)):          # the unambiguous combination form
        return combined(list(spec))
    if isinstance(spec, dict):
        names = list(spec)
        w = np.array([float(spec[n]) for n in names], float)
        if (w < 0).any() or w.sum() <= 0:
            raise ValueError("mix weights must be ≥ 0 with a positive sum")
        w = w / w.sum()
        rends = {n: nib_style(n, seed=seed) for n in names}

        def render(strokes, pen: float = 0.35, **kw):
            rng = np.random.default_rng([seed, _mark_key(strokes)])
            pick = names[int(rng.choice(len(names), p=w))]
            r = rends[pick]
            if r is None:
                given = kw.get("paths")
                return PenPaths(list(given) if given is not None else rg.render(strokes, pen), pen=pen)
            return r(strokes, pen, **kw)
        render.__name__ = "nib_mix"
        return render
    s = str(spec)
    if s in STYLE_PARTS:
        return strategy(s)
    # "b++c" means b+ and c: split on '+' but keep the 'b+' token whole
    toks, i = [], 0
    while i < len(s):
        if s.startswith("b+", i) and (i + 2 == len(s) or s[i + 2] == "+"):
            toks.append("b+")
            i += 3
        else:
            j = s.find("+", i)
            j = len(s) if j < 0 else j
            toks.append(s[i:j])
            i = j + 1
    return combined([t for t in toks if t])


# ---------------------------------------------------------------------------
# physical preview
# ---------------------------------------------------------------------------

def _canvas(box, pxmm, ss):
    x0, y0, x1, y1 = box
    return int(np.ceil((x1 - x0) * pxmm)) * ss, int(np.ceil((y1 - y0) * pxmm)) * ss


def ink_raster(paths, box, *, px_per_mm: float = 20.0, spread: float = 0.04, blur: float = 0.02,
               pens=None, offsets=None, ss: int = 2) -> np.ndarray:
    """Simulated plot: each polyline swept by a disc of its pen's width plus
    `spread` (mm of ink bleed, total), anti-aliased, softened by a Gaussian of
    `blur` mm. Returns ink coverage (H, W) in [0, 1], 1 = ink. `offsets`:
    optional {pen width: (dx, dy)} registration error per pen."""
    from PIL import Image, ImageDraw
    pens = pens if pens is not None else getattr(paths, "pens", None) or [0.35] * len(paths)
    W, H = _canvas(box, px_per_mm, ss)
    img = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(img)
    k = px_per_mm * ss
    for p, w in zip(paths, pens):
        off = np.asarray((offsets or {}).get(w, (0.0, 0.0)))
        q = (np.asarray(p) + off - [box[0], box[1]]) * k
        d = (w + spread) * k
        r = d / 2
        if len(q) >= 2:
            dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
        # a disc at every vertex: PIL's wide-line joints leave pinholes
        # (≈ 1 % of a 1 mm marker's ink) that a real pen does not
        for v in (q if d > 4 else (q[0], q[-1])):
            dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
    a = np.asarray(img.resize((W // ss, H // ss), Image.Resampling.BOX), dtype=np.float64) / 255.0
    if blur > 0:
        a = gaussian_filter(a, blur * px_per_mm)
    return np.clip(a, 0.0, 1.0)


def geom_raster(geom, box, *, px_per_mm: float = 20.0, spread: float = 0.04, blur: float = 0.02,
                ss: int = 2) -> np.ndarray:
    """A solid shapely region rendered like ink_raster (dilated by spread/2)."""
    from PIL import Image, ImageDraw
    W, H = _canvas(box, px_per_mm, ss)
    img = Image.new("L", (W, H), 0)
    if geom is not None and not geom.is_empty:
        g = geom.buffer(0.5 * spread, quad_segs=8) if spread > 0 else geom
        dr = ImageDraw.Draw(img)
        k = px_per_mm * ss
        tr = lambda c: [tuple(v) for v in (np.asarray(c)[:, :2] - [box[0], box[1]]) * k]
        for poly in rg._polys(g):
            dr.polygon(tr(poly.exterior.coords), fill=255)
            for h in poly.interiors:
                dr.polygon(tr(h.coords), fill=0)
    a = np.asarray(img.resize((W // ss, H // ss), Image.Resampling.BOX), dtype=np.float64) / 255.0
    if blur > 0:
        a = gaussian_filter(a, blur * px_per_mm)
    return np.clip(a, 0.0, 1.0)


def ideal_raster(strokes, pen: float, box, **kw) -> np.ndarray:
    return geom_raster(ideal_ink(strokes, pen), box, **kw)


# ---------------------------------------------------------------------------
# plot time (axibridge/estimate.py's model, vectorised)
# ---------------------------------------------------------------------------

# Ian's native backend settings (~/.axibridge/settings.json, read 2026-10-16):
# speed_pendown 25 %, speed_penup 75 %, accel 100 %, pen 20/60 %, rates 50/75 %.
MOTION = {"v_down": 0.25 * 279.4, "v_up": 0.75 * 279.4, "a": 1.00 * 4000.0, "cornering": 10.0,
          "t_lift": 0.15 * 0.40 * (100 / 75), "t_lower": 0.15 * 0.40 * (100 / 50),
          "pen_swap_s": 60.0}


def _poly_time(p: np.ndarray, v_max: float, a: float, cornering: float) -> float:
    d = np.linalg.norm(np.diff(p, axis=0), axis=1)
    keep = d > 1e-9
    if not keep.any():
        return 0.0
    q = np.vstack([p[:1], p[1:][keep]])
    s = d[keep]
    n = len(s)
    vj = np.zeros(n + 1)
    if n > 1:
        u = np.diff(q, axis=0)
        un = u / np.linalg.norm(u, axis=1, keepdims=True)
        cos = np.clip(np.sum(un[:-1] * un[1:], axis=1), -1, 1)
        vj[1:n] = v_max * ((cos + 1) / 2) ** (1.0 / max(cornering / 25.0, 0.05))
    v = vj.copy()
    v[0] = 0.0
    v[n] = 0.0
    for i in range(1, n + 1):
        v[i] = min(v[i] if i < n else 0.0, np.sqrt(v[i - 1] ** 2 + 2 * a * s[i - 1]))
    for i in range(n - 1, -1, -1):
        v[i] = min(v[i], np.sqrt(v[i + 1] ** 2 + 2 * a * s[i]))
    v0, v1 = v[:-1], v[1:]
    vp = np.minimum(np.sqrt(np.maximum((2 * a * s + v0 ** 2 + v1 ** 2) / 2, 0)), v_max)
    ta, td = (vp - v0) / a, (vp - v1) / a
    da, dd = (v0 + vp) / 2 * ta, (v1 + vp) / 2 * td
    dc = np.maximum(s - da - dd, 0.0)
    return float(np.sum(ta + td + np.where(vp > 0, dc / np.maximum(vp, 1e-9), 0.0)))


def plot_time(paths, motion: dict | None = None) -> dict:
    """Estimated seconds: pen-down (trapezoid + junction slow-down), travel,
    lifts, and one pen swap per extra pen width."""
    m = {**MOTION, **(motion or {})}
    pens = getattr(paths, "pens", None) or [None] * len(paths)
    t_down = t_up = 0.0
    pos = np.zeros(2)
    for p in paths:
        p = np.asarray(p)
        t_up += _poly_time(np.vstack([pos, p[0]]), m["v_up"], m["a"], 100.0)
        t_down += _poly_time(p, m["v_down"], m["a"], m["cornering"])
        pos = p[-1]
    lifts = len(paths) * (m["t_lift"] + m["t_lower"])
    swaps = max(len(set(pens)) - 1, 0) * m["pen_swap_s"]
    return {"down_s": t_down, "travel_s": t_up, "lift_s": lifts, "swap_s": swaps,
            "total_s": t_down + t_up + lifts + swaps}


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------

def _edges(mask: np.ndarray) -> np.ndarray:
    return mask & ~binary_erosion(mask)


def evaluate(strokes, paths, pen: float, *, px_per_mm: float = 20.0, spread: float = 0.04,
             margin: float = 2.0, offsets=None) -> dict:
    """Physical render vs the ideal solid ribbon.

    coverage   share of the ideal ink that is inked (density match)
    spill      ink outside the ideal, as a share of the ideal's area
    density    mean ink over the ideal region / ideal's own mean (1 = match)
    gap_mm     widest white gap inside the ideal (2 × max distance from a
               white pixel to ink, among white pixels ≥ pen/2 inside the
               ideal's edge): > ~0.25 mm is a visible pipe at reading distance
    edge_mm    symmetric mean distance between drawn and ideal ink edges
               (includes the inner edges of a pipe, which a solid lacks)
    plus pen length, paths/lifts, estimated time."""
    sts = _as_list(strokes)
    ink = ideal_ink(sts, pen)
    pens = getattr(paths, "pens", None) or [pen] * len(paths)
    allp = [np.asarray(p) for p in paths]
    x0, y0, x1, y1 = ink.bounds
    big = max(pens) if pens else pen
    box = (x0 - margin - big, y0 - margin - big, x1 + margin + big, y1 + margin + big)
    T = geom_raster(ink, box, px_per_mm=px_per_mm, spread=spread)
    D = ink_raster(allp, box, px_per_mm=px_per_mm, spread=spread, pens=pens, offsets=offsets)
    t = T > 0.5
    d = D > 0.5
    area = float(t.sum()) + 1e-9
    cov = float((t & d).sum()) / area
    spill = float((d & ~t).sum()) / area
    dens = float(D[t].mean() / max(T[t].mean(), 1e-9))
    # gaps: white pixels inside the ideal, away from its edge
    inner = distance_transform_edt(t) > 0.5 * pen * px_per_mm
    white = ~d
    dist_to_ink = distance_transform_edt(white)
    g = dist_to_ink[inner & white]
    gap = 2.0 * float(g.max()) / px_per_mm if g.size else 0.0
    gap_share = float((inner & white).sum()) / (float(inner.sum()) + 1e-9)
    et, ed = _edges(t), _edges(d)
    if et.any() and ed.any():
        dt = distance_transform_edt(~et)
        dd = distance_transform_edt(~ed)
        edge = 0.5 * (float(dt[ed].mean()) + float(dd[et].mean())) / px_per_mm
    else:
        edge = float("nan")
    L = float(sum(_plen(p) for p in allp))
    tm = plot_time(paths)
    return {"coverage": cov, "spill": spill, "density": dens, "gap_mm": gap, "gap_share": gap_share,
            "edge_mm": edge, "length_mm": L, "paths": len(allp), "lifts": max(len(allp) - 1, 0),
            "time_s": tm["total_s"], "time_ex_swap_s": tm["total_s"] - tm["swap_s"],
            "pens": sorted(set(float(x) for x in pens))}
