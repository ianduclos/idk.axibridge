"""Extractor contender: the classic skeleton-graph pipeline, executed carefully.

    gray → (blur) → Sauvola mask → (open/close, hole fill) → thinning
         → sknw graph → spur pruning (relative to local width)
         → collapse short junction-junction edges (X = two Y nodes + stub)
         → per-junction optimal MATCHING of incident branches
           (cost = tangent deviation, tangents taken 1–3.5 w out; "end here"
           has a fixed cost) → chains, bridged through junctions with cubic
           Hermite curves (skeleton kinks near junctions do not survive)
         → free-tip gap bridging (global greedy matching, ink evidence required)
         → sub-pixel refinement: each 1 px sample moves to the ink-weighted
           centroid of its grayscale cross-section along the normal
         → light smoothing; closed loops marked closed.

Every stage is a keyword flag so it can be ablated on the bench. Points are
pixels, x = column, y = row; width is full width (2·distance transform).
Pure and deterministic.
"""
from __future__ import annotations

import itertools

import numpy as np
import sknw
from scipy.ndimage import (convolve, distance_transform_edt, gaussian_filter, gaussian_filter1d,
                           map_coordinates, percentile_filter, zoom)
from scipy.spatial import cKDTree
from skimage.filters import threshold_otsu, threshold_sauvola
from skimage.morphology import (binary_closing, binary_opening, closing, disk, medial_axis,
                                remove_small_holes, remove_small_objects, skeletonize, thin)

from .core import Drawing, Stroke

# --------------------------------------------------------------------------
# small geometry helpers
# --------------------------------------------------------------------------


def _cumlen(p: np.ndarray) -> np.ndarray:
    if len(p) < 2:
        return np.zeros(len(p))
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def _at(p: np.ndarray, s: np.ndarray, t: float) -> np.ndarray:
    return np.array([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.hypot(*v))
    return v / n if n > 1e-12 else np.array([1.0, 0.0])


def _angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.degrees(np.arccos(np.clip(np.dot(_unit(a), _unit(b)), -1.0, 1.0))))


def _hermite(p0, d0, p1, d1, scale: float = 1.0) -> np.ndarray:
    """Cubic Hermite from p0 (unit tangent d0) to p1 (unit tangent d1), ~1 px
    spacing, endpoints excluded."""
    L = float(np.hypot(*(p1 - p0)))
    n = max(int(np.ceil(L)), 1)
    if n < 2:
        return np.zeros((0, 2))
    t = np.linspace(0.0, 1.0, n + 1)[1:-1, None]
    m0, m1 = d0 * L * scale, d1 * L * scale
    h00 = 2 * t**3 - 3 * t**2 + 1
    h10 = t**3 - 2 * t**2 + t
    h01 = -2 * t**3 + 3 * t**2
    h11 = t**3 - t**2
    return h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1


def _resample(p: np.ndarray, flags: np.ndarray, step: float, closed: bool):
    if closed:
        p = np.vstack([p, p[:1]])
        flags = np.concatenate([flags, flags[:1]])
    s = _cumlen(p)
    total = s[-1]
    if total <= 0 or len(p) < 2:
        return p[:1].copy(), flags[:1].copy()
    n = max(int(round(total / step)), 2 if not closed else 3)
    t = np.linspace(0.0, total, n + 1)
    if closed:
        t = t[:-1]
    out = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
    idx = np.clip(np.searchsorted(s, t), 0, len(flags) - 1)
    idx0 = np.clip(idx - 1, 0, len(flags) - 1)
    f = flags[idx] | flags[idx0]
    return out, f


# --------------------------------------------------------------------------
# mask + skeleton
# --------------------------------------------------------------------------


def _thin(mask: np.ndarray, method: str) -> np.ndarray:
    if method == "zhang":
        return skeletonize(mask)
    if method == "lee":
        return skeletonize(mask, method="lee").astype(bool)
    if method == "medial":
        return medial_axis(mask)
    if method == "thin":
        return thin(mask)
    raise ValueError(f"unknown thinning method {method!r}")


def _junction_density(skel: np.ndarray) -> float:
    """Junction pixels per skeleton pixel (≈0.01–0.05 for pen/etching
    lines, 0.25–0.5 for a grainy crayon mask)."""
    n = int(skel.sum())
    if n == 0:
        return 0.0
    nb = convolve(skel.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - 1
    return float((skel & (nb >= 3)).sum()) / n


def _background(gray: np.ndarray) -> np.ndarray:
    """Paper level: 90th-percentile filter on an 8× downsample, upsampled."""
    H, W = gray.shape
    f = 8
    small = gray[: H - H % f or H, : W - W % f or W]
    if small.shape[0] >= f and small.shape[1] >= f:
        small = small.reshape(small.shape[0] // f, f, small.shape[1] // f, f).mean(axis=(1, 3))
    else:
        return np.full_like(gray, float(np.percentile(gray, 90)))
    bg = percentile_filter(small, 90, size=9, mode="nearest")
    bg = zoom(bg, (H / bg.shape[0], W / bg.shape[1]), order=1)
    out = np.empty_like(gray)
    out[: bg.shape[0], : bg.shape[1]] = bg[:H, :W]
    if bg.shape[0] < H:
        out[bg.shape[0]:] = out[bg.shape[0] - 1]
    if bg.shape[1] < W:
        out[:, bg.shape[1]:] = out[:, bg.shape[1] - 1: bg.shape[1]]
    return out


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------


class _Graph:
    """Nodes: id → centre (x, y). Edges: id → [u, v, pts] with pts (N, 2) xy,
    pts[0] = centre(u), pts[-1] = centre(v)."""

    def __init__(self):
        self.node: dict[int, np.ndarray] = {}
        self.edge: dict[int, list] = {}
        self._next_e = 0
        self._next_n = 0

    def add_node(self, c) -> int:
        i = self._next_n
        self._next_n += 1
        self.node[i] = np.asarray(c, float)
        return i

    def add_edge(self, u, v, pts) -> int:
        i = self._next_e
        self._next_e += 1
        self.edge[i] = [u, v, np.asarray(pts, float)]
        return i

    def incidence(self) -> dict[int, list[tuple[int, int]]]:
        inc: dict[int, list[tuple[int, int]]] = {n: [] for n in self.node}
        for e in sorted(self.edge):
            u, v, _ = self.edge[e]
            inc[u].append((e, 0))
            inc[v].append((e, 1))
        return inc

    def length(self, e) -> float:
        return float(_cumlen(self.edge[e][2])[-1])

    def oriented(self, e, end) -> np.ndarray:
        """Edge points starting at the node at `end` (0 = u, 1 = v)."""
        p = self.edge[e][2]
        return p if end == 0 else p[::-1]

    def merge_deg2(self) -> bool:
        changed = False
        while True:
            inc = self.incidence()
            done = True
            for n in sorted(inc):
                ends = inc[n]
                if len(ends) != 2 or ends[0][0] == ends[1][0]:
                    continue
                (ea, xa), (eb, xb) = ends
                pa = self.oriented(ea, xa)[::-1]   # ... → n
                pb = self.oriented(eb, xb)         # n → ...
                ua = self.edge[ea][1 - xa]
                vb = self.edge[eb][1 - xb]
                del self.edge[ea], self.edge[eb], self.node[n]
                self.add_edge(ua, vb, np.vstack([pa, pb[1:]]))
                changed = True
                done = False
                break
            if done:
                return changed


def _build_graph(skel: np.ndarray) -> _Graph:
    g = sknw.build_sknw(skel.astype(np.uint16), multi=True, iso=True, ring=True, full=False)
    G = _Graph()
    remap = {}
    for n in sorted(g.nodes()):
        rc = np.asarray(g.nodes[n]["pts"], float)
        remap[n] = G.add_node(rc.mean(axis=0)[::-1])
    for u, v, k in sorted(g.edges(keys=True)):
        rc = np.asarray(g[u][v][k]["pts"], float)
        xy = rc[:, ::-1]
        cu, cv = G.node[remap[u]], G.node[remap[v]]
        if u != v and len(xy) > 1:
            # sknw traces s→e but networkx may report (e, s): orient by distance
            if (np.hypot(*(xy[0] - cu)) + np.hypot(*(xy[-1] - cv))
                    > np.hypot(*(xy[0] - cv)) + np.hypot(*(xy[-1] - cu))):
                xy = xy[::-1]
        G.add_edge(remap[u], remap[v], np.vstack([cu, xy, cv]))
    return G


def _local_w(dt: np.ndarray, c: np.ndarray, w: float) -> float:
    H, W = dt.shape
    x = int(np.clip(round(c[0]), 0, W - 1))
    y = int(np.clip(round(c[1]), 0, H - 1))
    return max(2.0 * float(dt[y, x]) - 1.0, w)


def _prune(G: _Graph, dt, w, spur_factor, iso_min_len, max_iter=6):
    for _ in range(max_iter):
        inc = G.incidence()
        deg = {n: len(v) for n, v in inc.items()}
        kill = []
        for e in sorted(G.edge):
            u, v, _ = G.edge[e]
            L = G.length(e)
            if deg[u] == 1 and deg[v] == 1:
                if L < iso_min_len:
                    kill.append(e)
                continue
            for tip, base in ((u, v), (v, u)):
                if deg[tip] == 1 and deg[base] >= 3:
                    if L < spur_factor * _local_w(dt, G.node[base], w):
                        kill.append(e)
                    break
        if not kill:
            break
        for e in kill:
            if e in G.edge:
                del G.edge[e]
        inc = G.incidence()
        for n in [n for n, v in inc.items() if not v]:
            del G.node[n]
        G.merge_deg2()
    # isolated pixels/specks that never had an edge
    inc = G.incidence()
    for n in [n for n, v in inc.items() if not v]:
        del G.node[n]


def _is_corridor(G: _Graph, inc, e, w, span, fork_deg) -> bool:
    """Edge e joins two degree-3 junctions whose other two branches both
    continue the edge's direction (a fork at each end): two strokes merged
    over a stretch (shallow crossing or a kiss), not a real bar."""
    u, v, _ = G.edge[e]
    for n, end in ((u, 0), (v, 1)):
        if len(inc[n]) != 3:
            return False
        tc = _tangent(G.oriented(e, end), w, w + span)
        for f, fend in inc[n]:
            if f == e:
                continue
            if _angle_deg(_tangent(G.oriented(f, fend), w, w + span), -tc) > fork_deg:
                return False
    return True


def _collapse(G: _Graph, dt, w, factor, corridor_factor=0.0, fork_deg=45.0,
              span=2.5, max_iter=200):
    """Contract short edges whose both ends are junctions (deg ≥ 3), and
    longer merge corridors (see _is_corridor) up to corridor_factor·w."""
    if factor <= 0 and corridor_factor <= 0:
        return
    for _ in range(max_iter):
        inc = G.incidence()
        deg = {n: len(v) for n, v in inc.items()}
        best = None
        for e in sorted(G.edge):
            u, v, _ = G.edge[e]
            if u == v or deg[u] < 3 or deg[v] < 3:
                continue
            L = G.length(e)
            lim = factor * max(_local_w(dt, G.node[u], w), _local_w(dt, G.node[v], w))
            ok = L < lim
            if not ok and L < corridor_factor * w:
                ok = _is_corridor(G, inc, e, w, span * w, fork_deg)
            if ok and (best is None or L < best[0]):
                best = (L, e)
        if best is None:
            break
        e = best[1]
        u, v, p = G.edge.pop(e)
        s = _cumlen(p)
        G.node[u] = _at(p, s, 0.5 * s[-1])
        for f in list(G.edge):
            a, b, q = G.edge[f]
            if a == v:
                a = u
            if b == v:
                b = u
            G.edge[f] = [a, b, q]
        del G.node[v]
        # tiny self-loops (bubbles from holes) die
        for f in [f for f, (a, b, q) in G.edge.items() if a == b == u and G.length(f) < 3.5 * w]:
            del G.edge[f]
    G.merge_deg2()


# --------------------------------------------------------------------------
# junction matching
# --------------------------------------------------------------------------


def _tangent(p: np.ndarray, a: float, b: float) -> np.ndarray:
    """Unit direction AWAY from p[0], estimated between arc lengths a and b."""
    s = _cumlen(p)
    T = s[-1]
    if T <= 1e-9:
        return np.array([1.0, 0.0])
    if T < b:
        b = T
        a = min(a, 0.4 * T)
    return _unit(_at(p, s, b) - _at(p, s, a))


def _best_matching(n: int, cost: np.ndarray, end_cost: float):
    """Min-cost partial matching on n branches (pair cost matrix, each
    unmatched branch costs end_cost). Exhaustive for n ≤ 10, greedy above."""
    if n > 10:
        pairs = sorted((cost[i, j], i, j) for i in range(n) for j in range(i + 1, n))
        used, out = set(), []
        for c, i, j in pairs:
            if c < 2 * end_cost and i not in used and j not in used:
                used |= {i, j}
                out.append((i, j))
        return out
    best = [np.inf, []]

    def rec(free, acc, pairs):
        if acc >= best[0]:
            return
        if not free:
            best[0], best[1] = acc, list(pairs)
            return
        i, rest = free[0], free[1:]
        rec(rest, acc + end_cost, pairs)
        for k, j in enumerate(rest):
            pairs.append((i, j))
            rec(rest[:k] + rest[k + 1:], acc + cost[i, j], pairs)
            pairs.pop()

    rec(list(range(n)), 0.0, [])
    return best[1]


# --------------------------------------------------------------------------
# sub-pixel refinement
# --------------------------------------------------------------------------


def _refine(pts, synth, gray, bg, wloc, closed, sigma_shift, contrast):
    """Move each point to the ink centroid of its normal cross-section."""
    N = len(pts)
    if N < 4:
        return pts
    mode = "wrap" if closed else "nearest"
    sm = np.column_stack([gaussian_filter1d(pts[:, 0], 2.0, mode=mode),
                          gaussian_filter1d(pts[:, 1], 2.0, mode=mode)])
    if closed:
        d = np.roll(sm, -1, axis=0) - np.roll(sm, 1, axis=0)
    else:
        d = np.gradient(sm, axis=0)
    t = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    nrm = np.column_stack([-t[:, 1], t[:, 0]])
    R = float(np.max(0.75 * wloc)) + 1.5
    step = 0.25
    o = np.arange(-R, R + 1e-9, step)
    X = pts[:, 0:1] + o[None, :] * nrm[:, 0:1]
    Y = pts[:, 1:2] + o[None, :] * nrm[:, 1:2]
    g = map_coordinates(gray, [Y.ravel(), X.ravel()], order=1, mode="nearest").reshape(X.shape)
    b = map_coordinates(bg, [pts[:, 1], pts[:, 0]], order=1, mode="nearest")
    ink = np.clip(b[:, None] - g, 0, None)
    # peak near the current position
    near = np.abs(o) <= np.maximum(0.35 * wloc, 1.0)[:, None] + 1.0
    pk_idx = np.argmax(np.where(near, ink, -1.0), axis=1)
    peak = ink[np.arange(N), pk_idx]
    thr = 0.3 * peak
    below = ink < thr[:, None]
    M = len(o)
    j = np.arange(M)[None, :]
    left = np.max(np.where(below & (j < pk_idx[:, None]), j, -1), axis=1) + 1
    right = np.min(np.where(below & (j > pk_idx[:, None]), j, M), axis=1) - 1
    inrun = (j >= left[:, None]) & (j <= right[:, None])
    wts = np.where(inrun, ink - thr[:, None], 0.0)
    sw = wts.sum(axis=1)
    cen = (wts * o[None, :]).sum(axis=1) / np.maximum(sw, 1e-12)
    run_w = (right - left + 1) * step
    valid = (~synth) & (sw > 0) & (peak > 0.15 * contrast) \
        & (left > 0) & (right < M - 1) & (run_w < 1.8 * wloc + 2.0)
    shift = np.clip(cen, -(0.5 * wloc + 0.5), 0.5 * wloc + 0.5)
    sd = max(sigma_shift, 0.5)
    num = gaussian_filter1d(np.where(valid, shift, 0.0), sd, mode=mode)
    den = gaussian_filter1d(valid.astype(float), sd, mode=mode)
    sh = np.where(den > 0.2, num / np.maximum(den, 1e-9), 0.0)
    return pts + sh[:, None] * nrm


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def extract(gray: np.ndarray, *,
            thin_method: str = "zhang",
            pre_blur: float = 0.0,
            morph: str = "auto",
            close_max: int = 6,
            grain_sigmas: tuple = (1.0, 1.5, 2.0, 3.0, 4.0),
            grain_j: float = 0.07,
            sauvola_k: float = 0.2,
            faint_fallback: bool = True,
            window: int | None = None,
            fill_holes: bool = True,
            spur_factor: float = 1.5,
            collapse_factor: float = 2.0,
            corridor_factor: float = 25.0,
            fork_deg: float = 45.0,
            match: bool = True,
            end_cost_deg: float = 30.0,
            tangent_near: float = 1.5,
            tangent_span: float = 4.0,
            hermite: bool = True,
            bridge_gaps: bool = True,
            gap_factor: float = 6.0,
            gap_angle_deg: float = 35.0,
            refine: bool = True,
            refine_sigma: float = 0.15,
            post_smooth: float = 1.0,
            min_len_factor: float = 3.0,
            return_debug: bool = False) -> Drawing:
    """Scan (float [0,1], ink dark) → ordered centreline strokes in px.

    Flags (for ablation): thin_method zhang|lee|medial|thin; pre_blur σ px
    before binarising (0 = off); morph auto (grainy media detected by
    skeleton junction density > grain_j → ink-density mask) | none |
    close_auto (grainy → adaptive closing of the Sauvola mask instead) |
    open|close|both (disk 1); faint_fallback relaxes Sauvola k on near-blank
    masks; corridor_factor·w = longest merge corridor (two strokes sharing
    ink, fork at both ends) contracted into one junction; spur_factor ×local width (0 = no pruning); collapse_factor ×local width
    (0 = off); match False = every graph edge is its own stroke (junctions
    end everything); hermite False = joints keep raw skeleton geometry;
    bridge_gaps across mask breaks; refine = sub-pixel centroid step;
    post_smooth σ px of final light smoothing.
    """
    gray = np.asarray(gray, dtype=np.float64)
    H, W = gray.shape
    win = window or max(15, (min(H, W) // 60) | 1)

    # (b) mask ---------------------------------------------------------------
    g = gaussian_filter(gray, pre_blur) if pre_blur > 0 else gray
    thr = threshold_sauvola(g, window_size=win, k=sauvola_k)
    mask = g < thr
    if faint_fallback:
        # very faint pencil: k=0.2 finds (almost) nothing — relax k until the
        # page carries a plausible amount of ink
        for k2 in (0.1, 0.07, 0.05):
            if mask.mean() >= 0.002 or k2 >= sauvola_k:
                break
            mask = g < threshold_sauvola(g, window_size=win, k=k2)
    close_r = 0
    if morph in ("open", "both"):
        mask = binary_opening(mask, disk(1))
    if morph in ("close", "both"):
        mask = binary_closing(mask, disk(1))
    raw = remove_small_objects(mask, max_size=30)
    mask = raw
    skel = _thin(mask, thin_method)
    bg = _background(gray)
    grain_sigma = 0.0
    if morph == "auto" and _junction_density(skel) > grain_j:
        # grainy media (crayon, litho): Sauvola picks single grains and the
        # skeleton becomes a junction mesh. Use ink DENSITY instead: blur the
        # background-normalised darkness until the stroke reads as one body.
        dk = np.clip(bg - gray, 0, None)
        for grain_sigma in grain_sigmas:
            ds = gaussian_filter(dk, grain_sigma)
            mask = remove_small_objects(ds > 0.5 * threshold_otsu(ds), max_size=30)
            skel = _thin(mask, thin_method)
            if _junction_density(skel) <= grain_j:
                break
    elif morph == "close_auto":
        while close_r < close_max and _junction_density(skel) > grain_j:
            close_r += 1
            mask = remove_small_objects(closing(raw, disk(close_r)).astype(bool), max_size=30)
            skel = _thin(mask, thin_method)
    dt = distance_transform_edt(mask)
    # dt at the centre pixel of a w-wide line is ≈ w/2 + 0.5 (pixel centres)
    w = float(np.median(2 * dt[skel]) - 1.0) if skel.any() else 3.0
    w = max(w, 1.0)
    if fill_holes:
        filled = remove_small_holes(mask, max_size=max(4, int(round(1.5 * w * w))))
        if filled.sum() != mask.sum():
            mask = filled
            skel = _thin(mask, thin_method)
            dt = distance_transform_edt(mask)
    # specks: components smaller than a short dash
    mask2 = remove_small_objects(mask, max_size=max(30, int(round(2.0 * w * w))))
    if mask2.sum() != mask.sum():
        mask = mask2
        skel = skel & mask
    inkpix = bg[mask] - gray[mask]
    contrast = float(np.median(inkpix)) if inkpix.size else 0.5
    paperpix = (bg - gray)[~mask]
    noise = float(1.4826 * np.median(np.abs(paperpix - np.median(paperpix)))) if paperpix.size else 0.02

    # (c) graph ---------------------------------------------------------------
    G = _build_graph(skel)
    if spur_factor > 0:
        _prune(G, dt, w, spur_factor, iso_min_len=min_len_factor * w)
    else:
        G.merge_deg2()
    _collapse(G, dt, w, collapse_factor, corridor_factor, fork_deg, tangent_span)
    if spur_factor > 0:
        _prune(G, dt, w, spur_factor, iso_min_len=min_len_factor * w)

    inc = G.incidence()
    deg = {n: len(v) for n, v in inc.items()}
    wj = {n: _local_w(dt, G.node[n], w) for n in G.node}
    rtrim = {n: (tangent_near * wj[n] if deg[n] >= 3 else 0.0) for n in G.node}

    # tangents at each edge end (pointing away from the node)
    tan = {}
    for e, (u, v, p) in G.edge.items():
        for end, n in ((0, u), (1, v)):
            a = rtrim[n] if deg[n] >= 3 else 0.0
            tan[(e, end)] = _tangent(G.oriented(e, end), a, a + tangent_span * w)

    # (d) matching ------------------------------------------------------------
    link: dict[tuple, tuple] = {}
    match_log = []
    for n in sorted(inc):
        ends = inc[n]
        k = len(ends)
        if k == 2:
            pairs = [(0, 1)]
        elif k >= 3 and match:
            C = np.full((k, k), np.inf)
            for i in range(k):
                for j in range(i + 1, k):
                    if ends[i][0] == ends[j][0] and G.length(ends[i][0]) < 4 * w:
                        continue  # don't close a tiny loop on itself
                    C[i, j] = C[j, i] = _angle_deg(tan[ends[i]], -tan[ends[j]])
            pairs = _best_matching(k, C, end_cost_deg)
            if return_debug:
                match_log.append((G.node[n].copy(), ends, C, pairs))
        else:
            pairs = []
        for i, j in pairs:
            link[ends[i]] = ends[j]
            link[ends[j]] = ends[i]

    # chain edges -------------------------------------------------------------
    def node_at(e, end):
        return G.edge[e][0] if end == 0 else G.edge[e][1]

    seen = set()
    chains = []  # list of (items [(e, fwd)], closed)
    for e0 in sorted(G.edge):
        if e0 in seen:
            continue
        # walk backwards from e0's start to the chain head
        cur, end_in = e0, 0
        closed = False
        visited = {e0}
        while (cur, end_in) in link:
            nxt = link[(cur, end_in)]
            ne, nend = nxt
            if ne == e0:
                closed = True
                break
            if ne in visited:
                break
            visited.add(ne)
            cur, end_in = ne, 1 - nend
        if closed:
            head, head_fwd = e0, True
        else:
            head, head_fwd = cur, (end_in == 0)
        items = []
        e, fwd = head, head_fwd
        while True:
            items.append((e, fwd))
            seen.add(e)
            out_end = 1 if fwd else 0
            if (e, out_end) not in link:
                break
            ne, nend = link[(e, out_end)]
            if ne == head and (nend == (0 if head_fwd else 1)):
                closed = True
                break
            if ne in seen:
                break
            e, fwd = ne, (nend == 0)
        chains.append((items, closed))

    # geometry ----------------------------------------------------------------
    def trimmed(e, fwd):
        p = G.edge[e][2] if fwd else G.edge[e][2][::-1]
        n0 = node_at(e, 0 if fwd else 1)
        n1 = node_at(e, 1 if fwd else 0)
        s = _cumlen(p)
        T = s[-1]
        a = rtrim[n0] if (hermite and match) else 0.0
        b = T - (rtrim[n1] if (hermite and match) else 0.0)
        if b - a < 1.0:
            m = 0.5 * (a + b) if b > a else 0.5 * T
            return _at(p, s, np.clip(m, 0, T))[None, :]
        keep = (s > a) & (s < b)
        return np.vstack([_at(p, s, a), p[keep], _at(p, s, b)])

    def end_tan(e, fwd, at_start):
        # tangent pointing away from the node at that end of the oriented edge
        end = (0 if fwd else 1) if at_start else (1 if fwd else 0)
        return tan[(e, end)], node_at(e, end)

    polys = []  # (pts, synth_flags, closed, tip_kinds(start,end))
    for items, closed in chains:
        segs, flags = [], []
        kinds = ["", ""]
        for idx, (e, fwd) in enumerate(items):
            q = trimmed(e, fwd)
            if idx == 0 and not closed:
                t0, n0 = end_tan(e, fwd, True)
                kinds[0] = "tip" if deg[n0] == 1 else "junction"
                if deg[n0] >= 3 and hermite and match:
                    c = G.node[n0]
                    L = max(float(np.dot(c - q[0], -t0)), 0.0)
                    if L >= 1.0:
                        ext = q[0] + np.outer(np.linspace(L, 0, int(np.ceil(L)) + 1)[:-1], -t0)
                        segs.append(ext)
                        flags.append(np.ones(len(ext), bool))
            if idx > 0:
                pe, pf = items[idx - 1]
                ta, n = end_tan(pe, pf, False)
                tb, _ = end_tan(e, fwd, True)
                if hermite and match and deg[n] >= 3:
                    br = _hermite(segs[-1][-1], -ta, q[0], tb)
                    segs.append(br)
                    flags.append(np.ones(len(br), bool))
                elif len(segs) and np.allclose(segs[-1][-1], q[0]):
                    q = q[1:]
            segs.append(q)
            flags.append(np.zeros(len(q), bool))
        if closed:
            e, fwd = items[-1]
            ta, n = end_tan(e, fwd, False)
            e0, f0 = items[0]
            tb, _ = end_tan(e0, f0, True)
            first = segs[0][0]
            if hermite and match and deg[n] >= 3:
                br = _hermite(segs[-1][-1], -ta, first, tb)
                segs.append(br)
                flags.append(np.ones(len(br), bool))
        else:
            e, fwd = items[-1]
            t1, n1 = end_tan(e, fwd, False)
            kinds[1] = "tip" if deg[n1] == 1 else "junction"
            if deg[n1] >= 3 and hermite and match:
                last = segs[-1][-1]
                c = G.node[n1]
                L = max(float(np.dot(c - last, -t1)), 0.0)
                if L >= 1.0:
                    ext = last + np.outer(np.linspace(0, L, int(np.ceil(L)) + 1)[1:], -t1)
                    segs.append(ext)
                    flags.append(np.ones(len(ext), bool))
        P = np.vstack(segs)
        F = np.concatenate(flags)
        # drop consecutive duplicates
        keep = np.ones(len(P), bool)
        keep[1:] = np.linalg.norm(np.diff(P, axis=0), axis=1) > 1e-6
        P, F = P[keep], F[keep]
        if closed and len(P) > 2 and np.linalg.norm(P[-1] - P[0]) < 1e-6:
            P, F = P[:-1], F[:-1]
        if closed and len(P) < 3:
            closed = False
        polys.append([P, F, closed, kinds])

    # (g) gap bridging between free tips ---------------------------------------
    if bridge_gaps:
        polys = _bridge(polys, gray, bg, w, gap_factor, gap_angle_deg, contrast, noise)

    # grainy media: profile a blurred copy so grain gaps don't split the run
    gsig = grain_sigma if grain_sigma > 0 else 0.5 * close_r
    gprof = gaussian_filter(gray, gsig) if gsig > 0 else gray

    # refine + output -----------------------------------------------------------
    strokes = []
    for P, F, closed, kinds in polys:
        if len(P) < 2:
            continue
        L = float(_cumlen(np.vstack([P, P[:1]]) if closed else P)[-1])
        if L < min_len_factor * w:
            continue
        R, RF = _resample(P, F, 1.0, closed)
        wl = 2.0 * map_coordinates(dt, [R[:, 1], R[:, 0]], order=1, mode="nearest") - 1.0
        wl = np.clip(wl, 0.5 * w, 3.0 * w)
        if refine:
            R = _refine(R, RF, gprof, bg, wl, closed, refine_sigma * w, contrast)
        if post_smooth > 0 and len(R) > 3:
            mode = "wrap" if closed else "nearest"
            R2 = np.column_stack([gaussian_filter1d(R[:, 0], post_smooth, mode=mode),
                                  gaussian_filter1d(R[:, 1], post_smooth, mode=mode)])
            if not closed:  # keep the endpoints where they were
                R2[0], R2[-1] = R[0], R[-1]
            R = R2
        width = 2.0 * map_coordinates(dt, [R[:, 1], R[:, 0]], order=1, mode="nearest") - 1.0
        width = np.maximum(width, 0.5)
        strokes.append(Stroke(R, width=width, closed=bool(closed),
                              meta={"tips": list(kinds)}))
    meta = {"method": "extract_refine", "w_px": w, "close_r": close_r, "grain_sigma": grain_sigma}
    if return_debug:
        meta["debug"] = {"mask": mask, "skel": skel, "graph": G, "matches": match_log}
    return Drawing(strokes, source="", size=(W, H), meta=meta)


def _tip_dir(P: np.ndarray, at_start: bool, span: float) -> np.ndarray:
    """Outward unit direction at a polyline tip."""
    q = P if at_start else P[::-1]
    s = _cumlen(q)
    b = min(span, s[-1])
    if b <= 1e-9:
        return np.array([1.0, 0.0])
    return _unit(q[0] - _at(q, s, b))


def _bridge(polys, gray, bg, w, gap_factor, gap_angle, contrast, noise):
    """Greedy global matching of free stroke tips across mask breaks.

    A pair qualifies when the gap ≤ gap_factor·w, both tips point at each
    other within gap_angle, and the gray along the straight gap shows ink
    (median darkness ≥ max(3σ_paper, 0.15·contrast)). Cost = gap/w + angle
    terms; cheapest first, each tip used once. The two ends of one stroke
    may close it into a loop."""
    tips = []
    for i, (P, F, closed, kinds) in enumerate(polys):
        if closed or len(P) < 2:
            continue
        L = float(_cumlen(P)[-1])
        if L < 2 * w:
            continue
        for end in (0, 1):
            if kinds[end] != "tip":
                continue
            pos = P[0] if end == 0 else P[-1]
            tips.append((i, end, pos, _tip_dir(P, end == 0, 3.0 * w)))
    if len(tips) < 2:
        return polys
    pos = np.array([t[2] for t in tips])
    tree = cKDTree(pos)
    gmax = gap_factor * w
    thr_ink = max(3.0 * noise, 0.15 * contrast)
    cands = []
    for a, b in sorted(tree.query_pairs(gmax)):
        ia, ea, pa, da = tips[a]
        ib, eb, pb, db = tips[b]
        v = pb - pa
        d = float(np.hypot(*v))
        if d < 1e-6:
            continue
        aa = _angle_deg(da, v)
        ab = _angle_deg(db, -v)
        if aa > gap_angle or ab > gap_angle:
            continue
        if ia == ib and float(_cumlen(polys[ia][0])[-1]) < 6 * d:
            continue  # closing a loop needs a loop much longer than the gap
        n = max(int(np.ceil(d)), 2)
        t = np.linspace(0, 1, n + 1)[1:-1]
        seg = pa[None, :] + t[:, None] * v[None, :]
        if len(seg):
            gv = map_coordinates(gray, [seg[:, 1], seg[:, 0]], order=1, mode="nearest")
            bv = map_coordinates(bg, [seg[:, 1], seg[:, 0]], order=1, mode="nearest")
            if float(np.median(bv - gv)) < thr_ink:
                continue
        cost = d / w + (aa + ab) / gap_angle
        cands.append((cost, a, b))
    cands.sort()
    used = set()
    joins = []
    for c, a, b in cands:
        if a in used or b in used:
            continue
        used |= {a, b}
        joins.append((tips[a], tips[b]))
    if not joins:
        return polys
    # union strokes along joins
    parent = list(range(len(polys)))
    adj: dict[tuple[int, int], tuple[int, int]] = {}
    for (ia, ea, pa, da), (ib, eb, pb, db) in joins:
        adj[(ia, ea)] = (ib, eb)
        adj[(ib, eb)] = (ia, ea)
    out, done = [], set()
    for i in range(len(polys)):
        if i in done:
            continue
        if polys[i][2]:
            out.append(polys[i]); done.add(i); continue
        # find head: walk from end 0
        cur, cend = i, 0
        closed = False
        guard = set([i])
        while (cur, cend) in adj:
            j, je = adj[(cur, cend)]
            if j == i:
                closed = True
                break
            if j in guard:
                break
            guard.add(j)
            cur, cend = j, 1 - je
        head = i if closed else cur
        head_end = 0 if closed else cend
        segs, flags = [], []
        kinds = ["", ""]
        cur, start_end = head, head_end
        while True:
            P, F, _, k = polys[cur]
            if start_end == 1:
                P, F, k = P[::-1], F[::-1], k[::-1]
            if not segs:
                kinds[0] = k[0]
            else:
                prev = segs[-1][-1]
                d0 = _tip_dir(segs[-1], False, 3.0 * w)
                d1 = -_tip_dir(P, True, 3.0 * w)
                br = _hermite(prev, d0, P[0], d1)
                segs.append(br)
                flags.append(np.ones(len(br), bool))
            segs.append(P)
            flags.append(F)
            done.add(cur)
            kinds[1] = k[1]
            out_end = 1 - start_end
            if (cur, out_end) not in adj:
                break
            j, je = adj[(cur, out_end)]
            if j == head and closed:
                Pc = np.vstack(segs)
                d0 = _tip_dir(Pc, False, 3.0 * w)
                d1 = -_tip_dir(Pc, True, 3.0 * w)
                br = _hermite(Pc[-1], d0, Pc[0], d1)
                segs.append(br)
                flags.append(np.ones(len(br), bool))
                break
            if j in done:
                break
            cur, start_end = j, je
        P = np.vstack(segs)
        F = np.concatenate(flags)
        out.append([P, F, closed, kinds if not closed else ["", ""]])
    return out
