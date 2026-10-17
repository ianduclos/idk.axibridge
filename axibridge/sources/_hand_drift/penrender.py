"""Frozen: nib ribbons that read as ink at real pen widths (research
`gesture/penrender.py` at c897f28, the nib styles Ian chose: a, b+, c, e, c+e).

    a    outline         regime's outline and graded mass fill, nothing else
                         (a nib reads as two edges — "a pipe")
    b+   inset, full     concentric insets everywhere a nib exists
    c    lanes           outline + passes parallel to the centreline at fixed
                         normal offsets (0.85 pen apart), each switched on
                         where the local half-width can hold it
    e    nib traces      outline + the paths of points ALONG THE NIB EDGE;
                         passes thin out dyadically where the stroke runs
                         along the nib, so they never pile up there
    c+e  both pass families on one outline

Masses (r > 1) keep regime's concentric fill in every style, made solid
sooner. Everything runs along the stroke or round it; nothing hatches.

app: every style returns `(rings, paths)` — the outline rings (closed, kept
whole so the source marks them `filled`) and every other pass. The greedy
pen-lift chaining runs over `paths` only, with the rings' ink counted as
covered ground; its coverage test is a shapely erosion instead of the
research's PIL raster (same rule: a connector may only run where its whole
pen disc is already ink).
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
from scipy.ndimage import gaussian_filter1d

from . import regime as rg

LANE_SPACING = 0.85        # passes this many pen widths apart (15 % overlap)
LANE_COVER = 0.95          # a new pass is switched on before a gap exceeds this × pen
STYLES = ("a", "b+", "c", "e", "c+e")


def _mass_fill(st: rg.RegimeStroke) -> rg.RegimeStroke:
    """Masses solid sooner: f = smoothstep((r − 1)/0.25) unless the stroke
    carries its own fill weights (then the larger of the two)."""
    f = rg._smoothstep((st.r - 1.0) / 0.25)
    if st.fill is not None:
        f = np.maximum(f, st.fill)
    return replace(st, fill=f)


def _with_fill(st: rg.RegimeStroke, f: np.ndarray) -> rg.RegimeStroke:
    return replace(st, fill=np.clip(np.maximum(f, _mass_fill(st).fill), 0.0, 1.0))


def ideal_ink(G, runs, pen: float):
    """The solid ink region the mark stands for: the pen-centre region
    dilated by pen/2, plus line runs swept by the pen."""
    import shapely
    from shapely.geometry import LineString
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
    q, a, rr, uvec, _ = rg._prep(st, pen, None)
    p = q.points
    if len(p) < 3:
        return None
    if q.closed:
        ext = np.vstack([p[-3:], p, p[:3]])
        t = np.gradient(ext, axis=0)[3:-3]
    else:
        t = np.gradient(p, axis=0)
    sd = 1.0
    t = np.column_stack([gaussian_filter1d(t[:, 0], sd, mode="wrap" if q.closed else "nearest"),
                         gaussian_filter1d(t[:, 1], sd, mode="wrap" if q.closed else "nearest")])
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    nrm = np.column_stack([-t[:, 1], t[:, 0]])
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


def _clip(paths, region, *, min_len: float = 0.0) -> list[np.ndarray]:
    """Keep the parts of open polylines inside a region."""
    from shapely.geometry import LineString
    from shapely.prepared import prep
    if region is None or region.is_empty:
        return []
    pr_ = prep(region)
    out = []
    for p in paths:
        if len(p) < 2:
            continue
        ls = LineString(p)
        if pr_.contains(ls):
            out.append(p)
            continue
        for x in rg._lines(ls.intersection(region)):
            c = np.asarray(x.coords)
            if len(c) >= 2 and rg._plen(c) >= min_len:
                out.append(c)
    return out


CHAIN_PXMM = 10.0          # app: coverage raster resolution (research: 20 px/mm through PIL)


def _coverage_mask(paths, pen: float, box, pxmm: float) -> np.ndarray:
    """Where a connector adds no visible mark: the paths swept by the pen
    (discs of pen/2), eroded by pen/2 less one pixel. app: numpy + scipy
    (points every half pixel, binary dilation / erosion) instead of PIL."""
    from scipy.ndimage import binary_dilation, binary_erosion
    x0, y0, x1, y1 = box
    W = int(np.ceil((x1 - x0) * pxmm)) + 1
    H = int(np.ceil((y1 - y0) * pxmm)) + 1
    m = np.zeros((H, W), bool)
    for p in paths:
        q = (np.asarray(p, dtype=np.float64) - [x0, y0]) * pxmm
        if len(q) >= 2:
            q = rg._densify(q, 0.5)
        ix = np.clip(np.round(q[:, 0]).astype(int), 0, W - 1)
        iy = np.clip(np.round(q[:, 1]).astype(int), 0, H - 1)
        m[iy, ix] = True

    def disc(r: float) -> np.ndarray:
        k = int(np.ceil(r))
        yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
        return (xx * xx + yy * yy) <= r * r

    r = 0.5 * pen * pxmm
    if r >= 0.5:
        m = binary_dilation(m, structure=disc(r))
    k = max(int(np.floor(r)) - 1, 0)
    if k > 0:
        m = binary_erosion(m, structure=disc(k))
    return m


def chain(paths, pen: float, *, cover=(), max_jump: float | None = None,
          pxmm: float = CHAIN_PXMM) -> list[np.ndarray]:
    """Greedy path chaining. From the end of the current path, jump to the
    nearest unvisited path end (a closed ring may be entered at any vertex)
    if the straight connector is ≤ max_jump and runs entirely over ground
    already inked (by `paths` or `cover`), so it adds no visible mark.
    Otherwise lift the pen. Order: from the first path, nearest-neighbour."""
    from scipy.spatial import cKDTree
    paths = [np.asarray(p, dtype=np.float64) for p in paths if len(p) >= 2]
    if len(paths) < 2:
        return paths
    max_jump = 6.0 if max_jump is None else max_jump
    inked = paths + [np.asarray(c, dtype=np.float64) for c in cover if len(c) >= 2]
    P = np.vstack(inked)
    mg = 2 * pen + 2.0 / pxmm
    box = (P[:, 0].min() - mg, P[:, 1].min() - mg, P[:, 0].max() + mg, P[:, 1].max() + mg)
    mask = _coverage_mask(inked, pen, box, pxmm)
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
    trees = {k: cKDTree(paths[k][:-1]) for k in range(len(paths)) if closed[k]}
    starts = np.array([p[0] for p in paths])
    ends = np.array([p[-1] for p in paths])
    left = list(range(len(paths)))
    out = []
    cur = paths[left.pop(0)]
    while left:
        end = cur[-1]
        L = np.array(left)
        d0 = np.linalg.norm(starts[L] - end, axis=1)
        d1 = np.linalg.norm(ends[L] - end, axis=1)
        cands = []
        for k, a0, a1 in zip(left, d0, d1):
            if closed[k]:
                dj, j = trees[k].query(end)
                cands.append((float(dj), k, "ring", int(j)))
            else:
                cands.append((float(a0), k, "fwd", 0) if a0 <= a1 else (float(a1), k, "rev", 0))
        cands.sort(key=lambda c: (c[0], c[1]))
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


def _lanes_c(fr, pen: float) -> list[np.ndarray]:
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
            if rg._plen(c) >= pen:
                out.append(c)
    return out


def _lanes_e(fr, pen: float) -> list[np.ndarray]:
    a, u, p, t = fr["a"], fr["u"], fr["p"], fr["t"]
    sin = np.abs(u[:, 0] * t[:, 1] - u[:, 1] * t[:, 0])
    live = fr["f"] < 0.95
    amax = float(a.max(initial=0.0))
    cov = LANE_COVER * pen
    if 2 * amax <= cov:
        return []
    m = int(np.ceil(np.log2(max(2 * amax / (LANE_SPACING * pen), 1.0))))
    N1 = 2 ** max(m, 1)
    d1 = 2 * a * sin / N1
    out = []
    for j in range(1, N1):
        lvl = (j & -j).bit_length() - 1
        stride = 2 ** (lvl + 1)
        on = (stride * d1 > cov) & live
        lam = -1.0 + 2.0 * j / N1
        for seg in _runs(on, fr["closed"]):
            if len(seg) < 2:
                continue
            c = p[seg] + (lam * a[seg])[:, None] * u[seg]
            if rg._plen(c) >= pen:
                out.append(c)
    return out


def touch_up(paths, ink, pen: float, *, min_area: float | None = None) -> list[np.ndarray]:
    """Close what a fill left white inside the ideal ink with concentric
    rings (every 0.85 pen). Rings, so still no hatching."""
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


def ink(strokes, style: str, pen: float = 0.35, *, max_jump: float | None = None
        ) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """One mark (strokes whose ribbons union) inked in `style` →
    (outline rings, other paths)."""
    if style not in STYLES:
        raise ValueError(f"nib style must be one of {STYLES}")
    sts = [strokes] if isinstance(strokes, rg.RegimeStroke) else [s for s in strokes if len(s)]
    if not sts:
        return [], []
    if style == "a":                        # regime.render unchanged
        parts = rg.render_parts(sts, pen)
        return parts["rings"], parts["runs"] + parts["fill"]
    if style == "b+":                       # concentric insets wherever a nib exists
        filled = [_with_fill(st, rg._smoothstep(st.r / 0.3)) for st in sts]
        parts = rg.render_parts(filled, pen)
        return parts["rings"], chain(parts["runs"] + parts["fill"], pen, cover=parts["rings"],
                                     max_jump=max_jump)
    kinds = ("c", "e") if style == "c+e" else (style,)
    parts = rg.render_parts([_mass_fill(s) for s in sts], pen)
    G = parts["G"]
    lanes = []
    for st in sts:
        fr = _centre_frame(st, pen)
        if fr is None:
            continue
        for kind in kinds:
            lanes += _lanes_c(fr, pen) if kind == "c" else _lanes_e(fr, pen)
    if G is not None and lanes:
        lanes = _clip(lanes, G.buffer(0.05 * pen), min_len=pen)
    drawn = parts["runs"] + parts["fill"] + lanes
    drawn += touch_up(parts["rings"] + drawn, ideal_ink(G, parts["runs"], pen), pen)
    return parts["rings"], chain(drawn, pen, cover=parts["rings"], max_jump=max_jump)
