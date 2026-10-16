"""Vector outline → Voronoi medial axis → strokes (bake-off technique).

Pipeline
1. Field. F = gaussian(gray, σ) − Sauvola threshold: its zero level set is a
   sub-pixel ink edge. Specks (< min_area px) are forced to paper and small
   holes (< hole_area px) to ink, so neither produces contours.
2. Outline. Per 8-connected ink component, `find_contours(F, 0)` on a padded
   crop (other components forced to paper) gives smooth closed boundaries,
   holes included; each is resampled at `spacing` px.
3. Medial axis. Voronoi diagram of the boundary samples; keep finite ridges
   whose two vertices are inside the ink (bilinear F < 0) and whose generator
   points subtend ≥ `theta_deg` at the ridge (the θ-medial-axis filter —
   removes ridges between neighbouring boundary samples and most noise
   spurs). Vertex radius = distance to the nearest boundary sample.
4. Graph. Ridges → branches between nodes (degree ≠ 2). Terminal branches are
   pruned greedily while their protrusion beyond the junction's disc,
   L + r_tip − r_junction, is < `prune_k`·r_junction (erosion-thickness style).
5. Junctions. Junction nodes joined by a branch shorter than
   `cluster_c`·(r_u + r_v) merge into one cluster (an X of thick lines has two
   Y nodes). At each cluster, branch ends are paired greedily by tangent
   continuity (tangent measured `cut`..`cut+span` radii out, i.e. outside the
   distorted junction core); a pair is accepted when it deviates from straight
   by < `pair_max_deg`. Paired ends are cut back and joined with a cubic
   Hermite bridge; unpaired ends (T stems) run on to the junction node.
6. Strokes. Ends are chained through pairings; all-paired cycles become closed
   strokes. Each stroke is resampled and lightly Gaussian-smoothed; width = 2r.
"""
from __future__ import annotations

import heapq

import numpy as np
from scipy.ndimage import binary_closing, gaussian_filter, gaussian_filter1d, label, map_coordinates, find_objects
from scipy.spatial import Voronoi, cKDTree
from skimage.filters import threshold_sauvola
from skimage.measure import find_contours
from skimage.morphology import disk, remove_small_holes, remove_small_objects

from .core import Drawing, Stroke
from .curvature import arclength, resample

_EPS = 0.02  # field value forced on specks (paper) / filled holes (ink)


# --------------------------------------------------------------------------
# 1–3: field, outlines, medial axis
# --------------------------------------------------------------------------

def _field(gray, window, k, sigma, min_area, hole_area, close_r=0):
    H, W = gray.shape
    win = window or max(15, (min(H, W) // 60) | 1)
    T = threshold_sauvola(gray, window_size=win, k=k)
    F = gaussian_filter(gray, sigma) - T if sigma > 0 else gray - T
    ink = F < 0
    if close_r > 0:
        ink = ink | binary_closing(ink, structure=disk(close_r).astype(bool))
    clean = remove_small_objects(ink, max_size=min_area, connectivity=2)
    holes = remove_small_holes(clean, max_size=hole_area) & ~clean
    F = F.copy()
    F[ink & ~clean] = _EPS
    F[holes] = np.minimum(F[holes], -_EPS)
    F[clean] = np.minimum(F[clean], -_EPS * 0.25) if close_r > 0 else F[clean]
    return F


def _component_axis(sub, own, spacing, theta_deg, r_min, contour_sigma):
    """Medial-axis ridges of one ink component. `sub` is the padded field
    crop with every non-own ink pixel already forced to paper. Returns
    (vertices (M,2) as (row, col) in crop coords, radius (M,), edges (E,2))."""
    cs = find_contours(sub, 0.0, fully_connected="low")
    samples, cid, sidx, clen = [], [], [], []
    for c in cs:
        if len(c) < 4:
            continue
        closed = np.allclose(c[0], c[-1])
        p = c[:-1] if closed else c
        if arclength(np.vstack([p, p[:1]]))[-1] < 3 * spacing:
            continue
        r = resample(p, spacing, closed=True)
        if contour_sigma > 0 and len(r) > 6:
            sd = contour_sigma / spacing
            r = np.column_stack([gaussian_filter1d(r[:, 0], sd, mode="wrap"),
                                 gaussian_filter1d(r[:, 1], sd, mode="wrap")])
        samples.append(r)
        cid.append(np.full(len(r), len(clen)))
        sidx.append(np.arange(len(r)))
        clen.append(len(r))
    if not samples:
        return None
    B = np.vstack(samples)
    cid, sidx, clen = np.concatenate(cid), np.concatenate(sidx), np.asarray(clen)
    # exact duplicates break qhull's input
    _, first = np.unique(np.round(B, 6), axis=0, return_index=True)
    first = np.sort(first)
    B, cid, sidx = B[first], cid[first], sidx[first]
    if len(B) < 5:
        return None
    try:
        vor = Voronoi(B)
    except Exception:
        try:
            vor = Voronoi(B, qhull_options="QJ")
        except Exception:
            return None
    V = vor.vertices
    rv = np.asarray(vor.ridge_vertices)
    rp = vor.ridge_points
    fin = (rv >= 0).all(axis=1)
    rv, rp = rv[fin], rp[fin]
    if not len(rv):
        return None
    inb = ((V[:, 0] >= 0) & (V[:, 0] <= sub.shape[0] - 1)
           & (V[:, 1] >= 0) & (V[:, 1] <= sub.shape[1] - 1))
    inside = np.zeros(len(V), bool)
    idx = np.nonzero(inb)[0]
    inside[idx] = map_coordinates(sub, V[idx].T, order=1, mode="nearest") < 0
    rad = np.zeros(len(V))
    used = np.unique(rv)
    used = used[inside[used]]
    if not len(used):
        return None
    rad[used] = cKDTree(B).query(V[used])[0]
    inside &= rad >= r_min
    keep = inside[rv[:, 0]] & inside[rv[:, 1]]
    gd = np.linalg.norm(B[rp[:, 0]] - B[rp[:, 1]], axis=1)
    rr = 0.5 * (rad[rv[:, 0]] + rad[rv[:, 1]])
    keep &= gd >= 2 * rr * np.sin(np.deg2rad(theta_deg) / 2)
    # generators that are near neighbours along one contour: not medial
    same = cid[rp[:, 0]] == cid[rp[:, 1]]
    di = np.abs(sidx[rp[:, 0]] - sidx[rp[:, 1]])
    di = np.minimum(di, clen[cid[rp[:, 0]]] - di)
    keep &= ~(same & (di * spacing < np.maximum(2.0 * rr, 2.5 * spacing)))
    rv = rv[keep]
    if not len(rv):
        return None
    vids, inv = np.unique(rv, return_inverse=True)
    return V[vids], rad[vids], inv.reshape(-1, 2)


def _medial_graph(F, spacing, theta_deg, r_min, contour_sigma, pad=3):
    lab, n = label(F < 0, structure=np.ones((3, 3)))
    objs = find_objects(lab)
    Fp = np.pad(F, pad, mode="constant", constant_values=1.0)
    labp = np.pad(lab, pad)
    P, R, E, off = [], [], [], 0
    for i, sl in enumerate(objs, start=1):
        if sl is None:
            continue
        r0, r1 = sl[0].start, sl[0].stop + 2 * pad
        c0, c1 = sl[1].start, sl[1].stop + 2 * pad
        sub = Fp[r0:r1, c0:c1].copy()
        lb = labp[r0:r1, c0:c1]
        other = (lb != 0) & (lb != i)
        sub[other] = np.maximum(sub[other], _EPS)
        res = _component_axis(sub, i, spacing, theta_deg, r_min, contour_sigma)
        if res is None:
            continue
        V, rad, e = res
        xy = np.column_stack([V[:, 1] + c0 - pad, V[:, 0] + r0 - pad])
        P.append(xy); R.append(rad); E.append(e + off)
        off += len(xy)
    if not P:
        return np.zeros((0, 2)), np.zeros(0), np.zeros((0, 2), int)
    return np.vstack(P), np.concatenate(R), np.vstack(E)


# --------------------------------------------------------------------------
# 4: branch graph + pruning
# --------------------------------------------------------------------------

class _BranchGraph:
    """Branches are vertex-id arrays; nodes are their end vertex ids."""

    def __init__(self, P, R, E):
        self.P, self.R = P, R
        self.br: dict[int, np.ndarray] = {}
        self.nadj: dict[int, list] = {}
        self.cycles: list[np.ndarray] = []
        self._next = 0
        self._build(E)

    def blen(self, v):
        return float(np.sum(np.linalg.norm(np.diff(self.P[v], axis=0), axis=1)))

    def _add(self, verts):
        b = self._next
        self._next += 1
        self.br[b] = verts
        self.nadj.setdefault(int(verts[0]), []).append((b, 0))
        self.nadj.setdefault(int(verts[-1]), []).append((b, 1))
        return b

    def _remove(self, b):
        v = self.br.pop(b)
        for node, end in ((int(v[0]), 0), (int(v[-1]), 1)):
            lst = self.nadj[node]
            lst.remove((b, end))
            if not lst:
                del self.nadj[node]

    def _build(self, E):
        M = len(self.P)
        if not len(E):
            return
        a = np.concatenate([E[:, 0], E[:, 1]])
        b = np.concatenate([E[:, 1], E[:, 0]])
        order = np.argsort(a, kind="stable")
        a, b = a[order], b[order]
        indptr = np.searchsorted(a, np.arange(M + 1))
        nbr = [b[indptr[i]:indptr[i + 1]].tolist() for i in range(M)]
        deg = np.diff(indptr)
        visited = np.zeros(M, bool)
        seen_direct = set()
        for node in np.nonzero(deg != 2)[0].tolist():
            if deg[node] == 0:
                continue
            for nb in nbr[node]:
                if deg[nb] != 2:
                    key = (min(node, nb), max(node, nb))
                    if key in seen_direct:
                        continue
                    seen_direct.add(key)
                    self._add(np.array([node, nb]))
                    continue
                if visited[nb]:
                    continue
                path = [node]
                prev, cur = node, nb
                while deg[cur] == 2 and not visited[cur]:
                    visited[cur] = True
                    path.append(cur)
                    n0, n1 = nbr[cur]
                    prev, cur = cur, (n1 if n0 == prev else n0)
                if deg[cur] == 2:  # ran into a visited deg-2 vertex: degenerate, stop
                    continue
                path.append(cur)
                self._add(np.array(path))
        for start in np.nonzero((deg == 2) & ~visited)[0].tolist():
            if visited[start]:
                continue
            path = [start]
            visited[start] = True
            prev, cur = start, nbr[start][0]
            while cur != start and not visited[cur]:
                visited[cur] = True
                path.append(cur)
                n0, n1 = nbr[cur]
                prev, cur = cur, (n1 if n0 == prev else n0)
            if len(path) >= 3:
                self.cycles.append(np.array(path))

    def degree(self, node):
        return len(self.nadj.get(node, ()))

    def _merge_at(self, node):
        """Node has degree 2: splice its two branches into one."""
        (b1, e1), (b2, e2) = self.nadj[node]
        if b1 == b2:  # a loop hanging on nothing: becomes a pure cycle
            v = self.br[b1]
            self._remove(b1)
            self.cycles.append(v[:-1])
            return None
        v1 = self.br[b1] if e1 == 1 else self.br[b1][::-1]   # ... → node
        v2 = self.br[b2] if e2 == 0 else self.br[b2][::-1]   # node → ...
        self._remove(b1)
        self._remove(b2)
        return self._add(np.concatenate([v1, v2[1:]]))

    def prune(self, prune_k, min_spur_px):
        heap = []

        def push(b):
            v = self.br.get(b)
            if v is None:
                return
            d0, d1 = self.degree(int(v[0])), self.degree(int(v[-1]))
            if (d0 == 1) == (d1 == 1):
                return
            tip, j = (v[0], v[-1]) if d0 == 1 else (v[-1], v[0])
            L = self.blen(v)
            prot = L + self.R[tip] - self.R[j]
            if prot < prune_k * self.R[j] or L < min_spur_px:
                heapq.heappush(heap, (prot / max(self.R[j], 1e-6), b, len(v)))

        for b in list(self.br):
            push(b)
        while heap:
            _, b, n = heapq.heappop(heap)
            v = self.br.get(b)
            if v is None or len(v) != n:
                continue
            d0, d1 = self.degree(int(v[0])), self.degree(int(v[-1]))
            if (d0 == 1) == (d1 == 1):
                continue
            j = int(v[-1]) if d0 == 1 else int(v[0])
            self._remove(b)
            dj = self.degree(j)
            if dj == 2:
                nb = self._merge_at(j)
                if nb is not None:
                    push(nb)
            elif dj >= 1:
                for bb, _ in list(self.nadj[j]):
                    push(bb)

    def drop_isolated(self, min_len):
        for b, v in list(self.br.items()):
            if self.degree(int(v[0])) == 1 and self.degree(int(v[-1])) == 1:
                if self.blen(v) + self.R[v[0]] + self.R[v[-1]] < min_len:
                    self._remove(b)


# --------------------------------------------------------------------------
# 5–6: junction pairing + chaining
# --------------------------------------------------------------------------

def _poly_at(P, s, t):
    return np.column_stack([np.interp(t, s, P[:, 0]), np.interp(t, s, P[:, 1])])


def _hermite(p0, m0, p1, m1, step=0.5):
    d = float(np.linalg.norm(p1 - p0))
    n = max(int(np.ceil(d / step)), 2)
    t = np.linspace(0, 1, n + 1)[1:-1, None]
    h00 = 2 * t**3 - 3 * t**2 + 1
    h10 = t**3 - 2 * t**2 + t
    h01 = -2 * t**3 + 3 * t**2
    h11 = t**3 - t**2
    return h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1


def _strokes(G: _BranchGraph, cluster_c, cut_k, span_k, pair_max_deg, min_px, bridge_k):
    P, R = G.P, G.R
    nodes = [n for n in G.nadj if G.degree(n) >= 3]
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # oriented geometry of every branch (from end 0) and arc lengths
    geo = {}
    for b, v in G.br.items():
        pts = P[v]
        geo[b] = (pts, arclength(pts), R[v])

    def out_dir(b, e, Rj):
        """Tangent pointing away from the junction at end e of branch b,
        measured outside the junction core. Returns (cut point, dir, cut)."""
        pts, s, _ = geo[b]
        L = s[-1]
        a = min(max(cut_k * Rj, 0.5 * min_px), 0.4 * L)
        c = min(a + max(span_k * Rj, min_px), L)
        sa, sb = (a, max(c, a + 1e-6)) if e == 0 else (L - a, min(L - c, L - a - 1e-6))
        q = _poly_at(pts, s, np.array([sa, sb]))
        t = q[1] - q[0]
        nt = np.linalg.norm(t)
        return q[0], (t / nt if nt > 1e-9 else np.zeros(2)), a

    cmin = np.cos(np.deg2rad(pair_max_deg))

    def crossing_bridge(b, u, w):
        """u—w both degree 3, joined by b: is this the merged core of a
        shallow X (outer ends pair across the bridge, not around it)?"""
        if G.degree(u) != 3 or G.degree(w) != 3:
            return False
        Rj = max(R[u], R[w])
        ou = [(bb, e) for bb, e in G.nadj[u] if bb != b]
        ow = [(bb, e) for bb, e in G.nadj[w] if bb != b]
        if len(ou) != 2 or len(ow) != 2:
            return False
        du = [out_dir(bb, e, Rj)[1] for bb, e in ou]
        dw = [out_dir(bb, e, Rj)[1] for bb, e in ow]
        if -float(np.dot(du[0], du[1])) >= cmin or -float(np.dot(dw[0], dw[1])) >= cmin:
            return False
        for (i, j), (k, l) in (((0, 0), (1, 1)), ((0, 1), (1, 0))):
            if -float(np.dot(du[i], dw[j])) >= cmin and -float(np.dot(du[k], dw[l])) >= cmin:
                return True
        return False

    internal = set()
    for b, v in G.br.items():
        u, w = int(v[0]), int(v[-1])
        if u == w or u not in parent or w not in parent:
            continue
        L = geo[b][1][-1]
        if L < max(cluster_c * (R[u] + R[w]), min_px) or (
                L < bridge_k * (R[u] + R[w]) and crossing_bridge(b, u, w)):
            internal.add(b)
            parent[find(u)] = find(w)
    clusters: dict[int, list] = {}
    for n in nodes:
        clusters.setdefault(find(n), []).append(n)
    for b in internal:
        geo.pop(b)

    cut = {}       # (b, end) -> arc length removed at that end
    partner = {}   # (b, end) -> (b2, end2)
    tang = {}
    for root, members in clusters.items():
        Rj = float(max(R[m] for m in members))
        centre = np.average(P[members], axis=0, weights=R[members])
        ends = [(b, e) for m in members for (b, e) in G.nadj[m] if b not in internal]
        dirs = []
        for b, e in ends:
            tang[(b, e)] = out_dir(b, e, Rj)
            dirs.append(tang[(b, e)][1])
        cand = []
        for i in range(len(ends)):
            for j in range(i + 1, len(ends)):
                sc = -float(np.dot(dirs[i], dirs[j]))
                if sc >= np.cos(np.deg2rad(pair_max_deg)):
                    cand.append((sc, i, j))
        cand.sort(reverse=True)
        taken = set()
        for sc, i, j in cand:
            if i in taken or j in taken:
                continue
            taken |= {i, j}
            partner[ends[i]] = ends[j]
            partner[ends[j]] = ends[i]
            cut[ends[i]] = tang[ends[i]][2]
            cut[ends[j]] = tang[ends[j]][2]
        _ = centre

    def piece(b, start_end):
        """Branch b oriented from start_end, trimmed by any cuts. Returns pts, w."""
        pts, s, r = geo[b]
        L = s[-1]
        lo, hi = cut.get((b, 0), 0.0), L - cut.get((b, 1), 0.0)
        if hi <= lo:
            mid = 0.5 * (lo + hi)
            lo, hi = mid, mid
        keep = (s > lo) & (s < hi)
        t = np.concatenate([[lo], s[keep], [hi]])
        q = _poly_at(pts, s, t)
        w = 2 * np.interp(t, s, r)
        if start_end == 1:
            q, w = q[::-1], w[::-1]
        return q, w

    def bridge(end_a, end_b, pa, wa, pb, wb):
        _, ta, _ = tang[end_a]
        _, tb, _ = tang[end_b]
        d = float(np.linalg.norm(pb - pa))
        q = _hermite(pa, -ta * d, pb, tb * d)
        w = np.interp(np.linspace(0, 1, len(q) + 2)[1:-1], [0, 1], [wa, wb])
        return q, w

    used = set()
    out = []

    def free(b, e):
        v = G.br[b]
        return G.degree(int(v[0] if e == 0 else v[-1])) == 1

    def walk(b, e, closed_start=None):
        pts, ws = [], []
        f0 = free(b, e)
        while True:
            used.add(b)
            q, w = piece(b, e)
            if pts:
                bq, bw = bridge(prev_end, (b, e), pts[-1][-1], ws[-1][-1], q[0], w[0])
                pts.append(bq); ws.append(bw)
            pts.append(q); ws.append(w)
            other = (b, 1 - e)
            nxt = partner.get(other)
            if nxt is None:
                return np.vstack(pts), np.concatenate(ws), False, (f0, free(*other))
            if nxt[0] in used:
                if closed_start is not None and nxt == closed_start:
                    q0 = pts[0]
                    bq, bw = bridge(other, nxt, pts[-1][-1], ws[-1][-1], q0[0], ws[0][0])
                    pts.append(bq); ws.append(bw)
                    return np.vstack(pts), np.concatenate(ws), True, (False, False)
                return np.vstack(pts), np.concatenate(ws), False, (False, False)
            prev_end = other
            b, e = nxt

    for b in list(geo):
        if b in used:
            continue
        for e in (0, 1):
            if (b, e) not in partner:
                break
        else:
            continue
        # walk from the unpaired end e
        out.append(walk(b, e))
    for b in list(geo):
        if b in used:
            continue
        out.append(walk(b, 0, closed_start=(b, 0)))
    for v in G.cycles:
        out.append((P[v], 2 * R[v], True, (False, False)))
    return out


def _end_tangent(pts, s, at_start, span):
    """Unit tangent pointing OUT of the stroke at one end, over `span` px."""
    L = s[-1]
    if at_start:
        q = _poly_at(pts, s, np.array([min(span, L), 0.0]))
    else:
        q = _poly_at(pts, s, np.array([max(L - span, 0.0), L]))
    t = q[1] - q[0]
    n = np.linalg.norm(t)
    return t / n if n > 1e-9 else np.zeros(2)


def _bridge_gaps(polys, gap_k, gap_px, max_deg, span_k, min_span_px):
    """Join free stroke ends across small ink breaks: ends closer than
    max(gap_px, gap_k·w), both tangents pointing at each other within
    `max_deg`. Greedy by gap/width + angle. Ends that stop on a junction are
    never bridged (they are already in contact with ink)."""
    ends, info = [], []
    for i, (pts, w, closed, flags) in enumerate(polys):
        if closed or len(pts) < 2:
            continue
        s = arclength(pts)
        if s[-1] < 2.0:
            continue
        for e, at_start in ((0, True), (1, False)):
            if not flags[e]:
                continue
            wi = float(w[0] if at_start else w[-1])
            span = min(max(span_k * wi, min_span_px), s[-1])
            ends.append((i, e))
            info.append((pts[0] if at_start else pts[-1], _end_tangent(pts, s, at_start, span), wi, s[-1]))
    if len(ends) < 2:
        return polys
    E = np.array([x[0] for x in info])
    wmax = max(x[2] for x in info)
    pairs = cKDTree(E).query_pairs(max(gap_px, gap_k * wmax), output_type="ndarray")
    cmax = np.cos(np.deg2rad(max_deg))
    cand = []
    for a, b in pairs.tolist():
        (ia, ea), (ib, eb) = ends[a], ends[b]
        pa, ta, wa, la = info[a]
        pb, tb, wb, lb = info[b]
        v = pb - pa
        d = float(np.linalg.norm(v))
        if d > max(gap_px, gap_k * 0.5 * (wa + wb)):
            continue
        if ia == ib and la < 6 * max(d, 1.0):
            continue
        if -float(np.dot(ta, tb)) < cmax:
            continue
        if d > 1e-6:
            v = v / d
            if float(np.dot(ta, v)) < cmax or float(np.dot(tb, -v)) < cmax:
                continue
        cost = d / max(0.5 * (wa + wb), 1.0) + (1 + float(np.dot(ta, tb)))
        cand.append((cost, a, b))
    cand.sort()
    partner = {}
    for _, a, b in cand:
        if ends[a] in partner or ends[b] in partner:
            continue
        partner[ends[a]] = ends[b]
        partner[ends[b]] = ends[a]
    if not partner:
        return polys
    tang = {ends[k]: info[k] for k in range(len(ends))}
    out, used = [], set()

    def oriented(i, e):
        pts, w = polys[i][0], polys[i][1]
        return (pts, w) if e == 0 else (pts[::-1], w[::-1])

    def join(i, e):
        """Walk from stroke i entering at end e."""
        start = (i, e)
        P_, W_ = [], []
        f0 = polys[i][3][e]
        while True:
            used.add(i)
            q, w = oriented(i, e)
            if P_:
                pa, ta = P_[-1][-1], tang[prev][1]
                pb, tb = q[0], tang[(i, e)][1]
                d = float(np.linalg.norm(pb - pa))
                if d > 1e-6:
                    bq = _hermite(pa, ta * d, pb, -tb * d)
                    P_.append(bq)
                    W_.append(np.interp(np.linspace(0, 1, len(bq) + 2)[1:-1], [0, 1], [W_[-1][-1], w[0]]))
            P_.append(q); W_.append(w)
            other = (i, 1 - e)
            nxt = partner.get(other)
            if nxt is None:
                return (np.vstack(P_), np.concatenate(W_), False, (f0, polys[i][3][1 - e]))
            if nxt == start:
                pa, ta = P_[-1][-1], tang[other][1]
                pb, tb = P_[0][0], tang[start][1]
                d = float(np.linalg.norm(pb - pa))
                if d > 1e-6:
                    bq = _hermite(pa, ta * d, pb, -tb * d)
                    P_.append(bq)
                    W_.append(np.interp(np.linspace(0, 1, len(bq) + 2)[1:-1], [0, 1], [W_[-1][-1], W_[0][0]]))
                return (np.vstack(P_), np.concatenate(W_), True, (False, False))
            if nxt[0] in used:
                return (np.vstack(P_), np.concatenate(W_), False, (f0, False))
            prev = other
            i, e = nxt

    for i in range(len(polys)):
        if i in used:
            continue
        closed = polys[i][2]
        if closed:
            out.append(polys[i]); used.add(i); continue
        if (i, 0) not in partner:
            out.append(join(i, 0))
        elif (i, 1) not in partner:
            out.append(join(i, 1))
    for i in range(len(polys)):
        if i not in used:
            out.append(join(i, 0))
    return out


def _finish(pts, w, closed, smooth_sigma, step):
    if len(pts) < 2:
        return None
    keep = np.concatenate([[True], np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-9])
    pts, w = pts[keep], w[keep]
    if closed and len(pts) > 2 and np.linalg.norm(pts[0] - pts[-1]) < 1e-9:
        pts, w = pts[:-1], w[:-1]
    if len(pts) < 2:
        return None
    loop = np.vstack([pts, pts[:1]]) if closed else pts
    wl = np.concatenate([w, w[:1]]) if closed else w
    s = arclength(loop)
    if s[-1] < 1e-6:
        return None
    r = resample(pts, step, closed=closed)
    sr = arclength(np.vstack([r, r[:1]]) if closed else r)
    if not closed:
        sr = sr * (s[-1] / max(sr[-1], 1e-9))
    wr = np.interp(sr[:len(r)], s, wl)
    if smooth_sigma > 0 and len(r) > 3:
        mode = "wrap" if closed else "nearest"
        sd = smooth_sigma / step
        r = np.column_stack([gaussian_filter1d(r[:, 0], sd, mode=mode),
                             gaussian_filter1d(r[:, 1], sd, mode=mode)])
        if not closed:  # keep end points where they were measured
            r[0], r[-1] = pts[0], pts[-1]
        wr = gaussian_filter1d(wr, sd, mode=mode)
    if closed and len(r) < 3:
        return None
    return r, wr


def extract(gray: np.ndarray, *, window: int | None = None, k: float = 0.2,
            field_sigma: float = 0.0, contour_sigma: float = 0.6, min_area: int = 30, hole_area: int = 12, close_r: int = 0,
            spacing: float = 0.6, theta_deg: float = 70.0, r_min: float = 0.35,
            prune_k: float = 1.0, min_spur_px: float = 1.5,
            cluster_c: float = 1.5, cut_k: float = 1.5, span_k: float = 2.5,
            pair_max_deg: float = 45.0, junction_px: float = 4.0, bridge_k: float = 8.0, smooth_sigma: float = 1.0,
            gap_k: float = 2.0, gap_px: float = 4.0, gap_max_deg: float = 30.0,
            gap_span_k: float = 3.0, gap_span_px: float = 6.0,
            step: float = 0.75, min_len: float = 3.0) -> Drawing:
    """Voronoi-medial-axis extractor. gray float (H, W) in [0, 1], ink dark."""
    g = np.asarray(gray, dtype=np.float64)
    H, W = g.shape
    F = _field(g, window, k, field_sigma, min_area, hole_area, close_r)
    P, R, E = _medial_graph(F, spacing, theta_deg, r_min, contour_sigma)
    G = _BranchGraph(P, R, E)
    G.prune(prune_k, min_spur_px)
    G.drop_isolated(min_len)
    strokes = []
    polys = _strokes(G, cluster_c, cut_k, span_k, pair_max_deg, junction_px, bridge_k)
    if gap_k > 0 or gap_px > 0:
        polys = _bridge_gaps(polys, gap_k, gap_px, gap_max_deg, gap_span_k, gap_span_px)
    for pts, w, closed, _ in polys:
        res = _finish(pts, w, closed, smooth_sigma, step)
        if res is None:
            continue
        r, wr = res
        st = Stroke(r, width=wr, closed=closed)
        if st.length() < min_len:
            continue
        strokes.append(st)
    return Drawing(strokes, source="", size=(W, H), meta={"method": "voronoi"})
