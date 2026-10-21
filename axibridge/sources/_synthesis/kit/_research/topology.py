# FROZEN from research commit 6f96418: tools/gesture/gesture/topology.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""The composition / topology layer: how lines relate to each other.

Two halves (results/topology-2026-10-16.md):

**Measure** (`relation_graph`, `topology_features`). A drawing (normally the
long, non-hatching subset `grammar_v3_frozen.long_drawing`) becomes a
stroke-relation graph: strokes are nodes, relations are edges. The relation
taxonomy, every threshold dimensionless (R = `Drawing.ref_length()`; a floor
in line widths so a thick line never "touches" by its own width):

- **ends** — each open-stroke end is exactly one of
  ``T``     ends on another line's interior (host position u = s/L, branch
            angle between the end tangent and the host, folded to [0, π/2]);
  ``L``     ends on another line's end (join; deflection 0 = smooth
            continuation, π = a cusp);
  ``near``  stops short of another line, gap ≤ NEAR_R (gap, aim angle);
  ``free``  nothing within NEAR_R;
  ``self``  ends on its own body (a loop closing onto itself).
- **X** — proper crossing of two strokes away from both ends (angle).
- **P** — near-parallel run: ≥ PAR_MIN_R of one line within (touch, PAR_MAX_R]
  of another's interior with tangents within PAR_ANGLE (offset, overlap
  length, offset ÷ overlap, offset CV). Nested parallel curves.
- **K** — kiss: the two interiors come within touch, tangentially, and part
  without crossing (contact ≤ KISS_MAX_R). Longer tangential contact = ``merge``.
- **forms** — a stroke whose end gap ≤ CLOSE_FRAC × its length is a closed
  form; containment of forms gives nesting depth. **cells** — faces of the
  planar arrangement of all lines (ends extended by the touch distance).
- **graph** — contact degree (T, L, X), all-relation degree, components.
- **ink field** — ink on a GRID² lattice over the ink's bounding box:
  coverage, entropy, central mass, radial spread; plus canvas-frame margins
  (descriptive only: scan crops are arbitrary).

**Generate** (`learn_model`, `generate_structure`). Hand-less skeleton lines
(a smooth Ornstein–Uhlenbeck curvature walk at the coarse "path" scale,
steered off the sheet edge, around other ink and toward empty space)
composed by explicit relations:

- ``kind="learned"``: a `TopologyModel` (learned per artist, or hand-set):
  each new line starts as T (branch from a host interior at a learned u and
  angle), L (continue a free end), P (offset copy of a host stretch at a
  learned offset, then free growth), near (at a learned gap) or free (in an
  emptier part of a smooth random "figure envelope"); when a growing line
  meets ink it ends on it (T), crosses it (within the learned X rate) or
  steers away (and stops short when boxed in: a near-meeting); past its
  planned length a line may home in on the nearest ink and stop at a
  learned gap (near/(near+free) of the learned ends); a share of long lines
  curl shut as closed forms.
- ``kind="oehlen_tree"``: one or a few trunks that wind and fork
  recursively (sympodial forks at a decaying length ratio, alternating
  sides), twigs shorter and windier with order, tips steered into empty
  space, re-sprouting from existing branches toward the emptiest region
  until the sheet is filled to a target coverage. A large clearance and a
  minimum branch length keep it from becoming texture.

Output: a `Drawing` of smooth structural polylines with per-stroke meta
(relation, host, order) — meant to be redrawn in a hand
(`grammar_v3_frozen.restyle`, or restyle.py when it exists).

Pure and deterministic: inputs never mutated; randomness via
np.random.Generator.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from scipy.spatial import cKDTree

from .core import Drawing, Stroke
from .curvature import arclength, resample

# --- measurement thresholds (R units unless *_W) -------------------------------
STEP_R = 1 / 1500        # sampling step
TOUCH_R = 0.005          # end within this of a line touches it ...
TOUCH_W = 1.5            # ... and never less than this many line widths
NEAR_R = 0.02            # gap up to this = a near-meeting
END_EPS_R = 0.01         # a crossing this close to either line's end is not an X
HOST_END_R = 0.012       # T within this arc distance of the host's end is a join (L)
TAN_R = 0.008            # half-window for tangents
PAR_ANGLE = np.deg2rad(20.0)
PAR_MAX_R = 0.06
PAR_MIN_R = 0.03
KISS_MAX_R = 0.1         # tangential contact longer than this is a merge (retrace)
CLOSE_FRAC = 0.1
NEAR_CLOSE_FRAC = 0.25
GRID = 10

END_KINDS = ("T", "L", "near", "free", "self")


def line_width(drawing: Drawing) -> float:
    """Median stroke width (px): per-stroke median widths, else
    meta["line_width_px"], else 0.0025 R."""
    ws = [float(np.median(s.width)) for s in drawing.strokes if s.width is not None and len(s.width)]
    if ws:
        return float(np.median(ws))
    w = drawing.meta.get("line_width_px")
    return float(w) if w else 0.0025 * drawing.ref_length()


def _tangents(q: np.ndarray, k: int) -> np.ndarray:
    n = len(q)
    i = np.arange(n)
    v = q[np.minimum(i + k, n - 1)] - q[np.maximum(i - k, 0)]
    nv = np.linalg.norm(v, axis=1, keepdims=True)
    return np.divide(v, nv, out=np.tile([1.0, 0.0], (n, 1)), where=nv > 0)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[(start, stop)) index runs where mask is True."""
    if not mask.any():
        return []
    m = np.concatenate([[False], mask, [False]]).astype(np.int8)
    d = np.diff(m)
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def _fold(c: float) -> float:
    """Acute angle from |cos|."""
    return float(np.arccos(min(abs(c), 1.0)))


@dataclass
class Topology:
    """The relation graph of one drawing. Lengths in R units."""
    R: float
    w: float
    n: int
    lengths: list
    closed: list                     # per stroke: closed-like form
    ends: list = field(default_factory=list)       # dicts: stroke, end, kind, host, u, angle, gap, aim, defl
    crosses: list = field(default_factory=list)    # dicts: a, b, angle
    selfcross: list = field(default_factory=list)  # per stroke bool
    parallels: list = field(default_factory=list)  # dicts: a, b, s0, s1, length, offset, cv
    kisses: list = field(default_factory=list)     # dicts: a, b, length, kind (kiss|merge)
    forms: list = field(default_factory=list)      # dicts: stroke, area, depth
    cells: dict = field(default_factory=dict)
    field: dict = field(default_factory=dict)
    par_ink: float = 0.0

    def graph(self, kinds=("T", "L", "X")):
        """networkx Graph over strokes with an edge per pair having any of
        `kinds` (T, L, X, P, K, near)."""
        import networkx as nx
        G = nx.Graph()
        G.add_nodes_from((i, {"length": self.lengths[i]}) for i in range(self.n))
        def add(a, b, k):
            if a == b or k not in kinds:
                return
            if G.has_edge(a, b):
                G[a][b]["kinds"].add(k)
            else:
                G.add_edge(a, b, kinds={k})
        for e in self.ends:
            if e["kind"] in ("T", "L", "near") and e["host"] is not None:
                add(e["stroke"], e["host"], e["kind"])
        for x in self.crosses:
            add(x["a"], x["b"], "X")
        for p in self.parallels:
            add(p["a"], p["b"], "P")
        for k in self.kisses:
            add(k["a"], k["b"], "K")
        return G


def _sample(drawing: Drawing, R: float, step: float):
    P, keep = [], []
    for i, st in enumerate(drawing.strokes):
        if len(st) < 2 or st.length() < 3 * step:
            continue
        q = resample(st.points, step, closed=st.closed)
        if st.closed:
            q = np.vstack([q, q[:1]])
        P.append(q)
        keep.append(i)
    return P, keep


def relation_graph(drawing: Drawing) -> Topology:
    """Measure every relation of the taxonomy (module docstring)."""
    import shapely
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import polygonize, unary_union

    R = drawing.ref_length()
    w = line_width(drawing)
    step = max(STEP_R * R, 0.25)
    P, keep = _sample(drawing, R, step)
    strokes = [drawing.strokes[i] for i in keep]
    n = len(P)
    S = [arclength(q) for q in P]
    L = np.array([s[-1] for s in S])
    kt = max(1, int(round(TAN_R * R / step)))
    T = [_tangents(q, kt) for q in P]
    touch = max(TOUCH_R * R, TOUCH_W * w)
    near = max(NEAR_R * R, 2 * touch)
    endgap = np.array([0.0 if st.closed else float(np.linalg.norm(q[0] - q[-1])) for st, q in zip(strokes, P)])
    closed = [bool(st.closed or endgap[i] <= max(CLOSE_FRAC * L[i], touch)) for i, st in enumerate(strokes)]
    topo = Topology(R=R, w=w, n=n, lengths=(L / R).tolist(), closed=closed)
    if n == 0:
        return topo
    allp = np.vstack(P)
    own = np.concatenate([np.full(len(q), i) for i, q in enumerate(P)])
    idx = np.concatenate([np.arange(len(q)) for q in P])
    tree = cKDTree(allp)
    trees = [cKDTree(q) for q in P]
    ke = max(1, int(round(0.02 * R / step)))

    # -- ends -----------------------------------------------------------------
    for i, q in enumerate(P):
        if strokes[i].closed or closed[i] and endgap[i] <= touch:
            continue
        for end, j0 in ((0, 0), (1, len(q) - 1)):
            e = q[j0]
            jo = min(ke, len(q) - 1)
            tout = q[0] - q[jo] if end == 0 else q[-1] - q[-1 - jo]
            nt = np.linalg.norm(tout)
            tout = tout / nt if nt > 0 else np.array([1.0, 0.0])
            rec = {"stroke": i, "end": end, "kind": "free", "host": None, "u": None, "angle": None,
                   "gap": None, "aim": None, "defl": None}
            cand = tree.query_ball_point(e, near)
            best = {}
            for c in cand:
                h = int(own[c])
                if h == i:
                    if abs(S[i][idx[c]] - S[i][j0]) <= max(near, 0.05 * L[i]):
                        continue
                d = float(np.linalg.norm(allp[c] - e))
                if h not in best or d < best[h][0]:
                    best[h] = (d, int(idx[c]))
            if best:
                h = min(best, key=lambda k: best[k][0])
                d, k = best[h]
                if h == i:
                    rec.update(kind="self" if d <= touch else "near", host=i, gap=d / R)
                else:
                    hs = S[h]
                    dend = min(hs[k], hs[-1] - hs[k])
                    host_end = (not closed[h]) and dend <= max(HOST_END_R * R, 2 * touch)
                    if d <= touch:
                        if host_end:
                            ht = T[h][k] * (1 if hs[k] < hs[-1] - hs[k] else -1)  # inward along host
                            rec.update(kind="L", host=h, gap=d / R,
                                       defl=float(np.arccos(np.clip(np.dot(tout, ht), -1, 1))))
                        else:
                            rec.update(kind="T", host=h, gap=d / R, u=float(hs[k] / hs[-1]),
                                       angle=_fold(float(np.dot(tout, T[h][k]))))
                    else:
                        v = allp[np.flatnonzero((own == h) & (idx == k))[0]] - e
                        nv = np.linalg.norm(v)
                        rec.update(kind="near", host=h, gap=d / R,
                                   aim=float(np.arccos(np.clip(np.dot(tout, v / nv), -1, 1))) if nv > 0 else 0.0,
                                   u=None if host_end else float(hs[k] / hs[-1]))
            topo.ends.append(rec)

    # -- crossings ------------------------------------------------------------
    lines = [LineString(q) for q in P]
    eps = END_EPS_R * R
    strt = shapely.STRtree(lines)
    for a in range(n):
        for b in strt.query(lines[a], predicate="intersects"):
            b = int(b)
            if b <= a:
                continue
            inter = lines[a].intersection(lines[b])
            pts = [g for g in getattr(inter, "geoms", [inter]) if g.geom_type == "Point"]
            for pt in pts:
                if any(not closed[m] and (Point(P[m][0]).distance(pt) < eps or Point(P[m][-1]).distance(pt) < eps)
                       for m in (a, b)):
                    continue
                ta = T[a][trees[a].query([pt.x, pt.y])[1]]
                tb = T[b][trees[b].query([pt.x, pt.y])[1]]
                topo.crosses.append({"a": a, "b": b, "angle": _fold(float(np.dot(ta, tb)))})
    topo.selfcross = [bool(not closed[i] and not lines[i].is_simple) for i in range(n)]

    # -- parallel runs and kisses ---------------------------------------------
    cosp = math.cos(PAR_ANGLE)
    lo = np.array([q.min(axis=0) for q in P])
    hi = np.array([q.max(axis=0) for q in P])
    par_mask = [np.zeros(len(q), bool) for q in P]
    seen_pairs = set()
    ein = max(1, int(round(END_EPS_R * R / step)))
    for a in range(n):
        for b in range(n):
            if a == b:
                continue
            if np.any(lo[a] > hi[b] + PAR_MAX_R * R) or np.any(lo[b] > hi[a] + PAR_MAX_R * R):
                continue
            d, k = trees[b].query(P[a], distance_upper_bound=PAR_MAX_R * R)
            ok = np.isfinite(d)
            if not ok.any():
                continue
            k = np.where(ok, k, 0)
            c = np.abs(np.einsum("ij,ij->i", T[a], T[b][k]))
            nb = len(P[b])
            interior_b = closed[b] | ((k > ein) & (k < nb - 1 - ein))
            para = ok & interior_b & (c >= cosp)
            na_ = len(P[a])
            ia = np.arange(na_)
            interior_a = closed[a] | ((ia > ein) & (ia < na_ - 1 - ein))
            key = (min(a, b), max(a, b))
            order = np.arange(na_)
            if closed[a] and para.any() and not para.all():
                order = np.roll(order, -int(np.argmin(para)))   # runs never straddle a loop's seam
            ds_a = L[a] / max(na_ - 1, 1)
            for r0, r1 in _runs(para[order]):
                ix = order[r0:r1]
                dd = d[ix]
                contact = dd <= touch
                if contact.any():
                    # tangential contact: a kiss (short), a merge (long), or a shallow X (skip)
                    if a > b or not interior_a[ix][contact].all():
                        continue                              # counted once; ends are end relations
                    kk = k[ix]
                    side = np.sign(T[b][kk, 0] * (P[a][ix, 1] - P[b][kk, 1])
                                   - T[b][kk, 1] * (P[a][ix, 0] - P[b][kk, 0]))
                    side = side[side != 0]
                    if len(side) and side.min() < 0 < side.max():
                        continue                              # a shallow crossing, not a kiss
                    cl = max(int(contact.sum()) - 1, 1) * ds_a
                    topo.kisses.append({"a": a, "b": b, "length": float(cl / R),
                                        "kind": "kiss" if cl <= KISS_MAX_R * R else "merge"})
                    continue
                ln = (r1 - r0 - 1) * ds_a
                if ln < PAR_MIN_R * R:
                    continue
                par_mask[a][ix] = True
                topo.parallels.append({"a": a, "b": b, "s0": float(S[a][ix[0]] / R), "s1": float(S[a][ix[-1]] / R),
                                       "length": float(ln / R), "offset": float(np.median(dd) / R),
                                       "cv": float(np.std(dd) / max(np.mean(dd), 1e-9)),
                                       "first": key not in seen_pairs})
                seen_pairs.add(key)
    ink = float(L.sum())
    topo.par_ink = float(sum(m.sum() * L[i] / max(len(m) - 1, 1) for i, m in enumerate(par_mask)) / ink) \
        if ink > 0 else 0.0

    # -- closed forms and nesting ---------------------------------------------
    polys = []
    for i, q in enumerate(P):
        if not closed[i] or len(q) < 4:
            continue
        pg = Polygon(q).buffer(0)
        if pg.is_empty:
            continue
        if pg.geom_type == "MultiPolygon":
            pg = max(pg.geoms, key=lambda g: g.area)
        if pg.area >= (0.02 * R) ** 2:
            polys.append((i, pg))
    polys.sort(key=lambda t: -t[1].area)
    depth = {}
    for a_, (i, pg) in enumerate(polys):
        rp = pg.representative_point()
        dmax = 0
        for j, pj in polys[:a_]:
            if pj.contains(rp):
                dmax = max(dmax, depth[j])
        depth[i] = dmax + 1
        topo.forms.append({"stroke": i, "area": float(pg.area / R ** 2), "depth": dmax + 1})

    # -- planar cells ---------------------------------------------------------
    ext = []
    for i, q in enumerate(P):
        if closed[i]:
            ext.append(q)
            continue
        jo = min(ke, len(q) - 1)
        t0 = q[0] - q[jo]
        t1 = q[-1] - q[-1 - jo]
        t0 = t0 / max(np.linalg.norm(t0), 1e-9)
        t1 = t1 / max(np.linalg.norm(t1), 1e-9)
        ext.append(np.vstack([q[0] + 1.2 * touch * t0, q, q[-1] + 1.2 * touch * t1]))
    try:
        u = unary_union([LineString(q).simplify(0.5 * step) for q in ext])
        faces = [f for f in polygonize(u) if f.area >= (0.02 * R) ** 2]
    except Exception:  # noqa: BLE001 — degenerate geometry: no cells
        faces = []
    hull = shapely.MultiPoint(allp).convex_hull
    topo.cells = {"n": len(faces), "area": float(sum(f.area for f in faces) / max(hull.area, 1e-9)),
                  "areas": sorted(float(f.area / R ** 2) for f in faces)}

    # -- ink field ------------------------------------------------------------
    topo.field = _ink_field(allp, drawing.size)
    return topo


def _ink_field(allp: np.ndarray, size) -> dict:
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    u = np.clip((allp - lo) / span, 0, 1 - 1e-9)
    H, _, _ = np.histogram2d(u[:, 0], u[:, 1], bins=GRID, range=[[0, 1], [0, 1]])
    p = H.ravel() / max(H.sum(), 1)
    nz = p[p > 0]
    c = u.mean(axis=0)
    centre = np.mean(np.all(np.abs(u - 0.5) <= 0.25, axis=1))
    rad = float(np.mean(np.linalg.norm(u - c, axis=1)) / (0.5 * np.sqrt(2)))
    W, Hh = (size if size and size[0] else (hi[0] + lo[0], hi[1] + lo[1]))
    diag = float(np.hypot(W, Hh))
    margin = float(min(lo[0], lo[1], W - hi[0], Hh - hi[1]) / diag) if diag > 0 else float("nan")
    off = float(np.linalg.norm(allp.mean(axis=0) - np.array([W, Hh]) / 2) / diag) if diag > 0 else float("nan")
    return {"cover": float(np.mean(H > 0)), "entropy": float(-np.sum(nz * np.log(nz)) / np.log(GRID * GRID)),
            "centre": float(centre), "radial": rad, "aspect": float(min(span) / max(span)),
            "canvas_margin": margin, "canvas_offcentre": off,
            "density": (H / max(H.sum(), 1)).tolist()}


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------

FEATURES = {
    # economy
    "top_n_strokes": "number of strokes (long subset)",
    "top_ink": "total ink ÷ R",
    "top_len_q50": "median stroke length ÷ R",
    "top_len_max_frac": "longest stroke ÷ total ink",
    # ends
    "top_end_T": "share of open ends that end on another line's interior (T)",
    "top_end_L": "share of open ends meeting another line's end (join)",
    "top_end_near": "share of open ends stopping short of another line (gap ≤ 0.02 R)",
    "top_end_free": "share of open ends with nothing within 0.02 R",
    "top_T_u_mid": "share of T attachments in the middle 60 % of the host",
    "top_T_angle": "median T branch angle (rad, 0..π/2)",
    "top_L_defl": "median join deflection (rad; 0 = smooth continuation, π = cusp)",
    "top_near_gap_log": "median log10(gap ÷ R) of near ends",
    "top_near_aim": "median angle between a near end's direction and its nearest line (rad)",
    # crossings
    "top_x_per_ink": "X crossings per unit ink (R)",
    "top_x_angle": "median crossing angle (rad)",
    "top_selfcross": "share of open strokes crossing themselves",
    # parallels / kisses
    "top_par_pairs": "stroke pairs with a near-parallel run, per stroke",
    "top_par_ink": "share of ink in near-parallel runs",
    "top_par_offset_log": "median log10(parallel offset ÷ R)",
    "top_par_ratio_log": "median log10(offset ÷ overlap length)",
    "top_par_cv": "median offset CV along a parallel run (low = truly nested)",
    "top_kiss_per_ink": "tangential kisses per unit ink",
    "top_merge_per_ink": "long tangential contacts (merges/retraces) per unit ink",
    # forms
    "top_closed": "share of strokes that are closed forms",
    "top_near_closed": "share of strokes with end gap ≤ 0.25 × length",
    "top_nest_max": "deepest nesting of closed forms (0 = none)",
    "top_nested": "share of closed forms inside another",
    "top_cells_per_ink": "planar cells (faces of the line arrangement) per unit ink",
    "top_cell_area": "cells' total area ÷ ink hull area",
    # graph
    "top_deg_contact": "mean contact degree (T, L, X neighbours)",
    "top_deg_all": "mean degree over all relations (T, L, X, P, K, near)",
    "top_isolated": "share of strokes without contact",
    "top_hub": "share of strokes hosting ≥ 2 T attachments",
    "top_comp_per_stroke": "contact components ÷ strokes",
    "top_comp_largest": "ink share of the largest contact component",
    # ink field
    "top_cover": "share of the 10×10 ink-bbox lattice holding ink",
    "top_entropy": "entropy of ink over that lattice (÷ log 100)",
    "top_centre": "share of ink in the central quarter of the ink bbox",
    "top_radial": "mean ink distance from the ink centroid (÷ half bbox diagonal)",
    "top_aspect": "ink bbox short ÷ long side",
    # descriptive only (scan crops are arbitrary)
    "canvas_margin": "min ink-to-canvas-edge distance ÷ canvas diagonal (descriptive)",
    "canvas_offcentre": "ink centroid offset from canvas centre ÷ diagonal (descriptive)",
}
DESCRIPTIVE = ("canvas_margin", "canvas_offcentre")


def _med(v, default=float("nan")):
    v = [x for x in v if x is not None and np.isfinite(x)]
    return float(np.median(v)) if v else default


def features_from(t: Topology) -> dict:
    nan = float("nan")
    f = {k: nan for k in FEATURES}
    n = t.n
    if n == 0:
        return f
    L = np.array(t.lengths)
    ink = float(L.sum())
    f["top_n_strokes"] = float(n)
    f["top_ink"] = ink
    f["top_len_q50"] = float(np.median(L))
    f["top_len_max_frac"] = float(L.max() / ink) if ink > 0 else nan
    ends = t.ends
    if ends:
        kinds = [e["kind"] for e in ends]
        for k in ("T", "L", "near", "free"):
            f[f"top_end_{k}"] = kinds.count(k) / len(kinds)
    Ts = [e for e in ends if e["kind"] == "T"]
    if Ts:
        f["top_T_u_mid"] = float(np.mean([0.2 <= e["u"] <= 0.8 for e in Ts]))
        f["top_T_angle"] = _med([e["angle"] for e in Ts])
    f["top_L_defl"] = _med([e["defl"] for e in ends if e["kind"] == "L"])
    nr = [e for e in ends if e["kind"] == "near"]
    f["top_near_gap_log"] = _med([np.log10(max(e["gap"], 1e-6)) for e in nr])
    f["top_near_aim"] = _med([e["aim"] for e in nr])
    f["top_x_per_ink"] = len(t.crosses) / ink if ink > 0 else nan
    f["top_x_angle"] = _med([x["angle"] for x in t.crosses])
    opens = [s for s, c in zip(t.selfcross, t.closed) if not c]
    f["top_selfcross"] = float(np.mean(t.selfcross)) if t.selfcross else nan
    pairs = {(min(p["a"], p["b"]), max(p["a"], p["b"])) for p in t.parallels}
    f["top_par_pairs"] = len(pairs) / n
    f["top_par_ink"] = t.par_ink
    f["top_par_offset_log"] = _med([np.log10(max(p["offset"], 1e-6)) for p in t.parallels])
    f["top_par_ratio_log"] = _med([np.log10(max(p["offset"], 1e-6) / max(p["length"], 1e-6)) for p in t.parallels])
    f["top_par_cv"] = _med([p["cv"] for p in t.parallels])
    f["top_kiss_per_ink"] = sum(k["kind"] == "kiss" for k in t.kisses) / ink if ink > 0 else nan
    f["top_merge_per_ink"] = sum(k["kind"] == "merge" for k in t.kisses) / ink if ink > 0 else nan
    f["top_closed"] = float(np.mean(t.closed))
    f["top_near_closed"] = nan  # filled by topology_features (needs end gaps)
    f["top_nest_max"] = float(max([x["depth"] for x in t.forms], default=0))
    f["top_nested"] = float(np.mean([x["depth"] >= 2 for x in t.forms])) if t.forms else nan
    f["top_cells_per_ink"] = t.cells.get("n", 0) / ink if ink > 0 else nan
    f["top_cell_area"] = t.cells.get("area", nan)
    Gc = t.graph(("T", "L", "X"))
    Ga = t.graph(("T", "L", "X", "P", "K", "near"))
    dc = np.array([d for _, d in Gc.degree()])
    f["top_deg_contact"] = float(dc.mean())
    f["top_deg_all"] = float(np.mean([d for _, d in Ga.degree()]))
    f["top_isolated"] = float(np.mean(dc == 0))
    hosts = {}
    for e in Ts:
        hosts[e["host"]] = hosts.get(e["host"], 0) + 1
    f["top_hub"] = sum(v >= 2 for v in hosts.values()) / n
    import networkx as nx
    comps = list(nx.connected_components(Gc))
    f["top_comp_per_stroke"] = len(comps) / n
    f["top_comp_largest"] = max(sum(L[i] for i in c) for c in comps) / ink if ink > 0 else nan
    for k in ("cover", "entropy", "centre", "radial", "aspect"):
        f[f"top_{k}"] = t.field.get(k, nan)
    f["canvas_margin"] = t.field.get("canvas_margin", nan)
    f["canvas_offcentre"] = t.field.get("canvas_offcentre", nan)
    return f


def topology_features(drawing: Drawing) -> dict:
    """Per-drawing topology feature vector (FEATURES; dimensionless)."""
    t = relation_graph(drawing)
    f = features_from(t)
    R = t.R
    nc = []
    for st in drawing.strokes:
        if len(st) < 2:
            continue
        L = st.length()
        if L <= 0:
            continue
        nc.append(st.closed or np.linalg.norm(st.points[0] - st.points[-1]) <= NEAR_CLOSE_FRAC * L)
    f["top_near_closed"] = float(np.mean(nc)) if nc else float("nan")
    _ = R
    return f


# ---------------------------------------------------------------------------
# the learned topology model
# ---------------------------------------------------------------------------

@dataclass
class TopologyModel:
    """Pooled relation statistics of one hand (all lengths in R units).
    Every field can be hand-set; `learn_model` fills them from drawings."""
    name: str = "hand-set"
    lengths: list = field(default_factory=lambda: [0.08, 0.12, 0.18, 0.25, 0.35])
    inks: list = field(default_factory=lambda: [4.0, 5.0, 6.0])
    end_p: dict = field(default_factory=lambda: {"T": 0.2, "L": 0.05, "near": 0.5, "free": 0.25})
    t_u: list = field(default_factory=lambda: [0.2, 0.5, 0.8])
    t_angle: list = field(default_factory=lambda: [0.6, 0.9, 1.2])
    l_defl: list = field(default_factory=lambda: [0.3, 0.8])
    near_gap: list = field(default_factory=lambda: [0.008, 0.012, 0.02])
    x_per_ink: list = field(default_factory=lambda: [0.2])
    par_per_stroke: list = field(default_factory=lambda: [0.3])
    par_offset: list = field(default_factory=lambda: [0.015, 0.025, 0.04])
    par_length: list = field(default_factory=lambda: [0.05, 0.08, 0.12])
    closed_frac: list = field(default_factory=lambda: [0.0])
    cover: list = field(default_factory=lambda: [0.55])
    wind_sd: float = 4.0       # sd of κ·R at the path scale
    wind_corr: float = 0.06    # correlation length of κ (R units)
    w_over_R: float = 0.002

    def to_json(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_json(d: dict) -> "TopologyModel":
        return TopologyModel(**{k: v for k, v in d.items() if k in TopologyModel.__dataclass_fields__})

    def save(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_json()))

    @staticmethod
    def load(path) -> "TopologyModel":
        return TopologyModel.from_json(json.loads(Path(path).read_text()))


PATH_SIGMA_R = 0.015     # the "path" scale: κ below this is the hand's, above it the structure's


def path_wind(drawing: Drawing, sigma_r: float = PATH_SIGMA_R) -> tuple[list, list]:
    """Per long stroke: sd of κ·R and its correlation length (R units) after
    smoothing at σ = sigma_r·R — the structural winding, hand removed."""
    from .curvature import kappa_s
    R = drawing.ref_length()
    sds, cors = [], []
    for st in drawing.strokes:
        L = st.length()
        if L < 8 * sigma_r * R or len(st) < 4:
            continue
        s, k, _ = kappa_s(st.points, sigma_r * R, closed=st.closed)
        m = max(1, int(len(k) * 0.05))                      # drop end effects
        kk = k[m:-m] * R if len(k) > 4 * m else k * R
        if len(kk) < 8:
            continue
        sds.append(float(np.std(kk)))
        x = kk - kk.mean()
        ac = np.correlate(x, x, "full")[len(x) - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        lag = int(np.argmax(ac < np.exp(-1))) if np.any(ac < np.exp(-1)) else len(ac) - 1
        ds = (s[1] - s[0]) if len(s) > 1 else 1.0
        cors.append(float(lag * ds / R))
    return sds, cors


def learn_model(drawings: list[Drawing], name: str = "") -> TopologyModel:
    """Pool relation statistics of (long-subset) drawings into a model."""
    m = TopologyModel(name=name)
    lengths, inks, kinds = [], [], []
    tu, ta, ld, ng, xpi, pps, po, pl, cf, cov, sds, cors, wr = ([] for _ in range(13))
    for d in drawings:
        if len(d.strokes) < 2:
            continue
        t = relation_graph(d)
        if t.n == 0:
            continue
        ink = float(sum(t.lengths))
        lengths += t.lengths
        inks.append(ink)
        kinds += [e["kind"] for e in t.ends if e["kind"] != "self"]
        tu += [e["u"] for e in t.ends if e["kind"] == "T"]
        ta += [e["angle"] for e in t.ends if e["kind"] == "T"]
        ld += [e["defl"] for e in t.ends if e["kind"] == "L"]
        ng += [e["gap"] for e in t.ends if e["kind"] == "near"]
        xpi.append(len(t.crosses) / ink)
        pairs = {(min(p["a"], p["b"]), max(p["a"], p["b"])) for p in t.parallels}
        pps.append(len(pairs) / t.n)
        po += [p["offset"] for p in t.parallels]
        pl += [p["length"] for p in t.parallels]
        cf.append(float(np.mean(t.closed)))
        cov.append(t.field.get("cover", 0.5))
        s_, c_ = path_wind(d)
        sds += s_
        cors += c_
        wr.append(t.w / t.R)
    if not inks:
        return m
    m.lengths, m.inks = lengths, inks
    m.end_p = {k: kinds.count(k) / max(len(kinds), 1) for k in ("T", "L", "near", "free")}
    m.t_u, m.t_angle, m.l_defl, m.near_gap = tu or m.t_u, ta or m.t_angle, ld or m.l_defl, ng or m.near_gap
    m.x_per_ink, m.par_per_stroke = xpi, pps
    m.par_offset, m.par_length = po or m.par_offset, pl or m.par_length
    m.closed_frac, m.cover = cf, cov
    if sds:
        m.wind_sd = float(np.median(sds))
    if cors:
        m.wind_corr = float(np.median(cors))
    m.w_over_R = float(np.median(wr))
    return m


# ---------------------------------------------------------------------------
# the structural generator
# ---------------------------------------------------------------------------

class _Raster:
    """Occupancy raster: owner stroke id and sample sequence per cell."""

    def __init__(self, W, H, h):
        self.h = h
        self.nx, self.ny = int(W / h) + 3, int(H / h) + 3
        self.own = np.full((self.ny, self.nx), -1, np.int32)
        self.seq = np.zeros((self.ny, self.nx), np.int32)

    def mark(self, p, sid, seq):
        ix, iy = int(p[0] / self.h + 0.5), int(p[1] / self.h + 0.5)
        if 0 <= ix < self.nx and 0 <= iy < self.ny:
            self.own[iy, ix] = sid
            self.seq[iy, ix] = seq

    def hits(self, p, r, sid, seq_now, skip, ignore=()):
        """Owners within r of p, excluding sid's own last `skip` samples and
        `ignore`d strokes. Returns a set of owner ids (sid included for
        self-hits)."""
        h = self.h
        ix, iy, k = int(p[0] / h + 0.5), int(p[1] / h + 0.5), int(math.ceil(r / h))
        x0, x1, y0, y1 = max(ix - k, 0), min(ix + k + 1, self.nx), max(iy - k, 0), min(iy + k + 1, self.ny)
        if x0 >= x1 or y0 >= y1:
            return set()
        o = self.own[y0:y1, x0:x1]
        m = o >= 0
        if not m.any():
            return set()
        s = self.seq[y0:y1, x0:x1]
        m &= ~((o == sid) & (s > seq_now - skip))
        out = set(np.unique(o[m]).tolist())
        return out - set(ignore)


@dataclass
class _Params:
    lw: float
    clr: float
    step: float
    wind_sd: float          # κ·R
    wind_corr: float        # R units
    p_T: float              # on meeting ink: end on it
    p_cross: float          # ... or cross it (subject to budget)
    attract: float          # steering toward empty space (rad per R of travel)
    kmax: float             # max |κ|·R
    margin: float


class _Sheet:
    def __init__(self, W, H, R, prm: _Params, envelope: np.ndarray | None, x_rate: float):
        self.W, self.H, self.R, self.prm = W, H, R, prm
        self.ras = _Raster(W, H, prm.clr / 2)
        self.strokes: list[np.ndarray] = []
        self.meta: list[dict] = []
        self.cg = 24
        self.dens = np.zeros((self.cg, self.cg))
        self.env = envelope
        self.crossings = 0
        self.ink = 0.0
        self.x_rate = x_rate
        self._field = None
        self._dirty = 0
        self.tree = None

    # coarse density and its steering field
    def _cell(self, p):
        return (min(max(int(p[1] / self.H * self.cg), 0), self.cg - 1),
                min(max(int(p[0] / self.W * self.cg), 0), self.cg - 1))

    def field(self):
        if self._field is None or self._dirty > 60:
            d = gaussian_filter(self.dens, 1.5)
            d = d / max(d.max(), 1e-9)
            if self.env is not None:
                d = d - 0.8 * self.env
            gy, gx = np.gradient(d)
            self._field = (gx, gy, d)
            self._dirty = 0
        return self._field

    def inside(self, p, m=None):
        m = self.prm.margin if m is None else m
        return m <= p[0] <= self.W - m and m <= p[1] <= self.H - m

    def add(self, pts: np.ndarray, meta: dict) -> int:
        sid = len(self.strokes)
        self.strokes.append(pts)
        self.meta.append(meta)
        for j, p in enumerate(pts):
            self.ras.mark(p, sid, j)
            self.dens[self._cell(p)] += 1
        self.ink += float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1))) / self.R
        self._dirty += len(pts)
        self.tree = cKDTree(np.vstack(self.strokes))
        return sid

    def nearest_on(self, sid, p):
        q = self.strokes[sid]
        j = int(np.argmin(np.sum((q - p) ** 2, axis=1)))
        return j, q[j]

    def emptiest(self, rng, k=12):
        """A point in an empty part of the envelope: best of k candidates."""
        _gx, _gy, d = self.field()
        best, bv = None, np.inf
        m = self.prm.margin
        for _ in range(k):
            p = np.array([rng.uniform(m, self.W - m), rng.uniform(m, self.H - m)])
            i, j = self._cell(p)
            v = d[i, j] + 0.05 * rng.standard_normal()
            if v < bv and not self.ras.hits(p, 2 * self.prm.clr, -2, 0, 0):
                best, bv = p, v
        return best


def _grow(sheet: _Sheet, rng, start, heading, length, prm: _Params, *, sid_next: int,
          host: int | None = None, curl: float = 0.0, ignore_start: float = 0.0,
          wind_scale: float = 1.0, goal: float | None = None, goal_gain: float = 0.0,
          edge_stop: bool = False, seek_gap: float | None = None) -> tuple[np.ndarray, dict]:
    """Grow one smooth line (not yet added to the sheet). Returns (points,
    end info {"end": budget|T|blocked|edge|closed, "host", "crosses"})."""
    R, step, clr = sheet.R, prm.step, prm.clr
    p = np.asarray(start, float).copy()
    th = float(heading)
    pts = [p.copy()]
    tau = max(prm.wind_corr * R, 4 * step)
    sd = prm.wind_sd * wind_scale / R
    k = rng.normal(0, sd)
    kmax = prm.kmax / R
    n = int(length / step)
    if seek_gap is not None:
        n = int(1.6 * length / step)        # may run on a little to find ink to stop near
    skip = int(3 * clr / step) + 2
    ignore_until: dict[int, int] = {}
    if host is not None:
        ignore_until[host] = int(max(ignore_start, 3 * clr) / step) + 2
    look = 2.2 * clr
    info = {"end": "budget", "host": None, "crosses": 0, "cross_hosts": []}
    own_pts = []                         # own samples (for self-avoidance via raster-free check)
    own_tree_every = 25
    own_tree = None
    curl_k = curl / R
    for i in range(n):
        k += -k * step / tau + sd * math.sqrt(2 * step / tau) * rng.standard_normal()
        steer = 0.0
        d = np.array([math.cos(th), math.sin(th)])
        ahead = p + look * 3 * d
        # sheet edge
        if edge_stop and not sheet.inside(p + look * d):
            info["end"] = "edge"                     # runs off the sheet rather than along its border
            break
        if not edge_stop and not sheet.inside(ahead):
            c = np.array([sheet.W / 2, sheet.H / 2]) - p
            cr = d[0] * c[1] - d[1] * c[0]
            steer += (1.0 if cr >= 0 else -1.0) * 0.6 * kmax
        # empty-space attraction
        if prm.attract > 0:
            gx, gy, _ = sheet.field()
            ci, cj = sheet._cell(p)
            g = np.array([gx[ci, cj], gy[ci, cj]])
            ng = np.linalg.norm(g)
            if ng > 1e-9:
                want = -g / ng
                cr = d[0] * want[1] - d[1] * want[0]
                steer += prm.attract / R * cr
        # end-seeking: past the planned length, home in on the nearest ink and stop at a gap
        if seek_gap is not None and i * step > 0.75 * length and sheet.tree is not None:
            dq, jq = sheet.tree.query(p)
            if dq <= seek_gap and i * step > length * 0.9:
                info["end"] = "near"
                break
            v = sheet.tree.data[jq] - p
            nv = float(np.linalg.norm(v))
            if nv > 0 and nv < 0.08 * R:
                cr = d[0] * v[1] / nv - d[1] * v[0] / nv
                steer += 0.5 * kmax * cr
        elif seek_gap is None and i * step >= length:
            break
        # tropism: a persistent pull toward a goal heading (trees grow somewhere)
        if goal is not None and goal_gain > 0:
            steer += goal_gain / R * math.sin(goal - th)
        # obstacles ahead
        ign = [h for h, until in ignore_until.items() if i < until]
        probe = p + look * d
        hit = sheet.ras.hits(probe, clr, -1, 0, 0, ignore=ign)
        self_hit = False
        if own_tree is not None and len(own_pts) > skip:
            dd, jj = own_tree.query(probe)
            self_hit = dd < clr and jj < len(own_pts) - skip
        if hit or self_hit:
            target = min(hit, key=lambda h: np.min(np.sum((sheet.strokes[h] - probe) ** 2, axis=1))) if hit else None
            r = rng.random()
            snap = None
            if target is not None and r < prm.p_T and i * step > 2 * clr:
                _j, q = sheet.nearest_on(target, probe)
                v = q - p
                nv = float(np.linalg.norm(v))
                if nv > 0 and float(np.dot(v / nv, d)) > math.cos(0.8):
                    snap = q                      # the host lies ahead: end on it (T)
            if snap is not None:
                q = snap
                seg = np.linalg.norm(q - p)
                m_ = max(int(seg / step), 1)
                for t in np.linspace(0, 1, m_ + 1)[1:]:
                    pts.append(p + t * (q - p))
                info.update(end="T", host=target)
                break
            ht = None
            if target is not None:
                j, q = sheet.nearest_on(target, probe)
                qq = sheet.strokes[target]
                tv = qq[min(j + 2, len(qq) - 1)] - qq[max(j - 2, 0)]
                ht = tv / max(np.linalg.norm(tv), 1e-9)
            allow_x = (target is not None and r < prm.p_T + prm.p_cross
                       and sheet.crossings + info["crosses"] < sheet.x_rate * (sheet.ink + i * step / R) + 1
                       and ht is not None and abs(float(np.dot(ht, d))) < math.cos(np.deg2rad(30)))
            if allow_x:
                ignore_until[target] = i + int(4 * clr / step) + 2
                info["crosses"] += 1
                info["cross_hosts"].append(target)
            else:
                # avoid: the freest of a fan of headings within the turn limit
                best, bf = None, -1.0
                for dth in (0.25, -0.25, 0.5, -0.5, 0.85, -0.85, 1.2, -1.2):
                    if rng.random() < 0.5:
                        dth = -dth
                    dd_ = np.array([math.cos(th + dth), math.sin(th + dth)])
                    free = 0
                    for r_ in (1.0, 2.0, 3.0):
                        q = p + r_ * look * dd_
                        if not sheet.inside(q, prm.margin * 0.5) or sheet.ras.hits(q, clr, -1, 0, 0, ignore=ign):
                            break
                        if own_tree is not None and len(own_pts) > skip:
                            o, oj = own_tree.query(q)
                            if o < clr and oj < len(own_pts) - skip:
                                break
                        free += 1
                    if free > bf:
                        best, bf = dth, free
                    if free == 3:
                        break
                if bf <= 0:
                    info["end"] = "blocked"
                    break
                steer += best / max(look, step) * 0.8
                k *= 0.5
        kk = float(np.clip(k + curl_k + steer, -kmax, kmax))
        th += kk * step
        p = p + step * np.array([math.cos(th), math.sin(th)])
        if not sheet.inside(p, prm.margin * 0.5):
            info["end"] = "edge"
            break
        pts.append(p.copy())
        own_pts.append(p.copy())
        if len(own_pts) % own_tree_every == 0:
            own_tree = cKDTree(np.array(own_pts))
        if curl and i * step > 0.6 * length and np.linalg.norm(p - pts[0]) < 1.5 * clr:
            info["end"] = "closed"
            break
    return np.array(pts), info


def _envelope(rng, cg: int, cover: float) -> np.ndarray:
    """A smooth random 'figure' mass on the coarse grid: a few anisotropic
    blobs thresholded to cover ≈ `cover` of the sheet. 1 inside, 0 outside."""
    yy, xx = np.mgrid[0:cg, 0:cg] / (cg - 1)
    f = np.zeros((cg, cg))
    for _ in range(int(rng.integers(2, 6))):
        c = rng.uniform(0.2, 0.8, 2)
        s = rng.uniform(0.08, 0.3, 2)
        a = rng.uniform(0, np.pi)
        dx, dy = xx - c[0], yy - c[1]
        u = (dx * np.cos(a) + dy * np.sin(a)) / s[0]
        v = (-dx * np.sin(a) + dy * np.cos(a)) / s[1]
        f += rng.uniform(0.5, 1.0) * np.exp(-0.5 * (u ** 2 + v ** 2))
    f += 0.15 * gaussian_filter(rng.standard_normal((cg, cg)), 2)
    thr = np.quantile(f, 1 - min(max(cover, 0.1), 1.0))
    return gaussian_filter((f >= thr).astype(float), 0.8)


def _pick(xs, rng, default):
    xs = [x for x in xs if x is not None]
    return float(xs[int(rng.integers(len(xs)))]) if xs else default


def _offset_curve(q: np.ndarray, off: float, rng, step: float) -> np.ndarray:
    t = _tangents(q, 3)
    nrm = np.column_stack([-t[:, 1], t[:, 0]])
    var = 1 + 0.15 * gaussian_filter1d(rng.standard_normal(len(q)), max(len(q) / 6, 1), mode="nearest") * 3
    out = q + nrm * (off * var)[:, None]
    return resample(gaussian_filter1d(out, 2, axis=0, mode="nearest"), step)


def _drawing(sheet: _Sheet, size, kind, meta) -> Drawing:
    lw = sheet.prm.lw
    strokes = [Stroke(p, width=np.full(len(p), lw), meta=m) for p, m in zip(sheet.strokes, sheet.meta) if len(p) >= 2]
    return Drawing(strokes, source=f"topology:{kind}", size=size,
                   meta={"kind": kind, "line_width_px": lw, "ref_length_gen": sheet.R,
                         "crossings": sheet.crossings, "ink_R": sheet.ink, **meta})


def generate_structure(model: TopologyModel | None, rng: np.random.Generator, size=(1200, 1200), *,
                       kind: str = "learned", ink: float | None = None, margin_frac: float = 0.04,
                       **params) -> Drawing:
    """A skeleton drawing (smooth hand-less structural polylines).

    kind="learned": relations from `model` (see module docstring).
        params: ink (R units; default sampled from model), cover (envelope
        coverage), clearance_w (default 2.5 line widths), attract.
    kind="oehlen_tree": params: trunks (1–3), depth (4), ratio (0.62),
        fork_every (0.25 of a branch), fork_angle (0.6 rad), wind (κ·R sd,
        4), clearance_r (0.01), fill (target lattice coverage 0.85),
        p_meet_T (0.2), p_cross (0.15), trunk_len (1.1 R), max_strokes (220),
        tropism (8: pull toward up for trunks / the initial heading for
        branches, ÷ (1 + order)), min_branch_r (0.08). Tree lines stop at
        the sheet edge instead of turning along it.
    """
    W, H = (int(size), int(size)) if np.isscalar(size) else (int(size[0]), int(size[1]))
    margin = margin_frac * min(W, H)
    R = 0.95 * float(np.hypot(W - 2 * margin, H - 2 * margin))
    if kind == "learned":
        return _gen_learned(model or TopologyModel(), rng, (W, H), R, margin, ink, **params)
    if kind == "oehlen_tree":
        return _gen_tree(model, rng, (W, H), R, margin, ink, **params)
    raise ValueError(f"unknown kind {kind!r}")


def _gen_learned(m: TopologyModel, rng, size, R, margin, ink, *, cover=None, clearance_w=2.5,
                 attract=1.5, max_strokes=300, min_len_r=None) -> Drawing:
    W, H = size
    lw = m.w_over_R * R
    clr = max(clearance_w * lw, 0.004 * R)
    step = max(clr / 2.5, 0.5)
    if ink is None:
        ink = _pick(m.inks, rng, 5.0)
    cov = _pick(m.cover, rng, 0.55) if cover is None else cover
    ep = dict(m.end_p)
    tot = sum(ep.values()) or 1.0
    ep = {k: v / tot for k, v in ep.items()}
    ep["L"] = ep.get("L", 0.0) / 2               # one join start makes two L ends
    p_seek = ep.get("near", 0) / max(ep.get("near", 0) + ep.get("free", 0), 1e-9)
    p_T_meet = min(0.9, ep.get("T", 0) / max(ep.get("T", 0) + ep.get("near", 0), 1e-9) * 1.2)
    xr = float(np.median(m.x_per_ink)) if m.x_per_ink else 0.2
    prm = _Params(lw=lw, clr=clr, step=step, wind_sd=m.wind_sd, wind_corr=m.wind_corr, p_T=p_T_meet,
                  p_cross=0.5, attract=attract, kmax=max(40.0, 3 * m.wind_sd), margin=margin)
    sheet = _Sheet(W, H, R, prm, _envelope(rng, 24, cov), xr)
    pp = float(np.median(m.par_per_stroke)) if m.par_per_stroke else 0.2
    p_par = min(0.6, pp * 0.8)
    p_closed = float(np.mean(m.closed_frac)) if m.closed_frac else 0.0
    min_len = (min_len_r if min_len_r is not None else max(float(np.quantile(m.lengths, 0.1)), 0.02)) * R
    fails = 0
    while sheet.ink < ink and len(sheet.strokes) < max_strokes and fails < 40:
        L = _pick(m.lengths, rng, 0.1) * R
        n = len(sheet.strokes)
        r = rng.random()
        # start relation, drawn from the learned end distribution (+ parallels, closed forms)
        host, curl, meta = None, 0.0, {}
        start = heading = None
        pre = None
        if n and rng.random() < p_par:
            h = int(rng.integers(n))
            q = sheet.strokes[h]
            ql = arclength(q)
            ov = min(_pick(m.par_length, rng, 0.08) * R, 0.9 * ql[-1])
            if ov > 4 * step:
                s0 = rng.uniform(0, ql[-1] - ov)
                a, b = np.searchsorted(ql, [s0, s0 + ov])
                off = max(_pick(m.par_offset, rng, 0.02) * R, 1.3 * clr) * (1 if rng.random() < 0.5 else -1)
                seg = _offset_curve(q[a:b + 1], off, rng, step)
                ok = [sheet.inside(x) and not sheet.ras.hits(x, 0.8 * clr, -1, 0, 0) for x in seg]
                cut = int(np.argmin(ok)) if not all(ok) else len(seg)
                if cut * step > 4 * clr:
                    pre = seg[:cut]
                    start, meta = pre[-1], {"relation": "P", "host": h, "offset": float(off / R)}
                    tv = pre[-1] - pre[-min(4, len(pre))]
                    heading = math.atan2(tv[1], tv[0])
                    L = max(L - cut * step, 0.0) if rng.random() < 0.6 else 0.0
        if start is None and n and r < ep.get("T", 0):
            h = int(rng.integers(n))
            q = sheet.strokes[h]
            ql = arclength(q)
            u = _pick(m.t_u, rng, 0.5)
            j = int(np.searchsorted(ql, u * ql[-1]))
            j = min(max(j, 1), len(q) - 2)
            tv = q[j + 1] - q[j - 1]
            ang = _pick(m.t_angle, rng, 0.8)
            side = 1 if rng.random() < 0.5 else -1
            heading = math.atan2(tv[1], tv[0]) + side * (np.pi - ang if rng.random() < 0.5 else ang)
            start, host, meta = q[j], h, {"relation": "T", "host": h, "u": u}
        elif start is None and n and r < ep.get("T", 0) + ep.get("L", 0):
            h = int(rng.integers(n))
            q = sheet.strokes[h]
            if sheet.meta[h].get("closed"):
                continue
            end = int(rng.integers(2))
            e, e2 = (q[0], q[min(6, len(q) - 1)]) if end == 0 else (q[-1], q[-min(7, len(q))])
            tv = e - e2
            defl = _pick(m.l_defl, rng, 0.5) * (1 if rng.random() < 0.5 else -1)
            heading = math.atan2(tv[1], tv[0]) + defl
            start, host, meta = e, h, {"relation": "L", "host": h}
        elif start is None and n and r < ep.get("T", 0) + ep.get("L", 0) + ep.get("near", 0):
            g = max(_pick(m.near_gap, rng, 0.01) * R, 1.3 * clr)
            for _ in range(30):
                h = int(rng.integers(n))
                q = sheet.strokes[h]
                c = q[int(rng.integers(len(q)))] + g * np.array([math.cos(a := rng.uniform(0, 2 * np.pi)), math.sin(a)])
                if sheet.inside(c) and not sheet.ras.hits(c, 0.9 * g, -1, 0, 0):
                    start, heading = c, rng.uniform(0, 2 * np.pi)
                    meta = {"relation": "near", "host": h, "gap": float(g / R)}
                    break
        if start is None:
            c = sheet.emptiest(rng)
            if c is None:
                fails += 1
                continue
            start, heading, meta = c, rng.uniform(0, 2 * np.pi), {"relation": "free"}
        if pre is None and L >= 0.15 * R and rng.random() < p_closed:
            curl = (2 * np.pi / max(L / R, 0.05)) * (1 if rng.random() < 0.5 else -1)
            meta["closed"] = True
        if L > 0:
            sg = max(_pick(m.near_gap, rng, 0.01) * R, 1.2 * clr) if rng.random() < p_seek and not curl else None
            pts, info = _grow(sheet, rng, start, heading, L, prm, sid_next=n, host=host, curl=curl,
                              seek_gap=sg)
        else:
            pts, info = start[None, :], {"end": "budget", "host": None, "crosses": 0}
        if pre is not None:
            pts = np.vstack([pre, pts[1:]]) if len(pts) > 1 else pre
        if arclength(pts)[-1] < min_len:
            fails += 1
            continue
        fails = 0
        meta.update(end=info["end"], end_host=info.get("host"))
        sheet.crossings += info.get("crosses", 0)
        sheet.add(pts, meta)
    return _drawing(sheet, (W, H), "learned", {"model": m.name, "ink_budget": float(ink), "cover": cov})


def _gen_tree(m, rng, size, R, margin, ink, *, trunks=None, depth=4, ratio=0.62, fork_every=0.25,
              fork_angle=0.6, wind=4.0, wind_corr=0.1, clearance_r=0.01, fill=0.85, p_meet_T=0.2,
              p_cross=0.15, trunk_len=1.1, max_strokes=220, attract=2.0, twig_wind=1.25,
              min_branch_r=0.08, line_w_r=0.002, fork_skip=0.15, tropism=8.0) -> Drawing:
    W, H = size
    lw = line_w_r * R
    clr = clearance_r * R
    step = max(clr / 2.5, 0.5)
    prm = _Params(lw=lw, clr=clr, step=step, wind_sd=wind, wind_corr=wind_corr, p_T=p_meet_T,
                  p_cross=p_cross, attract=attract, kmax=max(30.0, 3 * wind), margin=margin)
    sheet = _Sheet(W, H, R, prm, None, x_rate=0.5)
    if trunks is None:
        trunks = int(rng.integers(1, 4))
    budget = np.inf if ink is None else ink
    queue = []                                   # (order, start, heading, length, host, ignore)
    for t in range(trunks):
        x = rng.uniform(0.2, 0.8) * W if trunks == 1 else (t + 0.5 + rng.uniform(-0.3, 0.3)) / trunks * W
        y = H - margin * 1.2
        side = rng.random()
        if side < 0.15:                          # occasionally from a side edge
            x, y = margin * 1.2, rng.uniform(0.4, 0.9) * H
            hd = -0.4 + rng.normal(0, 0.2)
        elif side < 0.3:
            x, y = W - margin * 1.2, rng.uniform(0.4, 0.9) * H
            hd = np.pi + 0.4 + rng.normal(0, 0.2)
        else:
            hd = -np.pi / 2 + rng.normal(0, 0.25)
        queue.append((0, np.array([x, y]), hd, trunk_len * R * rng.uniform(0.8, 1.2), None, 0.0, -np.pi / 2))
    min_len = min_branch_r * R
    resprouts = 0
    while len(sheet.strokes) < max_strokes and sheet.ink < budget:
        if not queue:
            # re-sprout toward the emptiest region until the lattice coverage reaches `fill`
            cov = _coverage(sheet)
            if cov >= fill or resprouts > 60:
                break
            resprouts += 1
            target = sheet.emptiest(rng, k=24)
            if target is None:
                break
            best = None
            for sid, q in enumerate(sheet.strokes):
                j = int(np.argmin(np.sum((q - target) ** 2, axis=1)))
                dd = float(np.sum((q[j] - target) ** 2))
                if best is None or dd < best[0]:
                    best = (dd, sid, j)
            if best is None:
                break
            _, sid, j = best
            q = sheet.strokes[sid]
            j = min(max(j, 1), len(q) - 2)
            v = target - q[j]
            o = sheet.meta[sid].get("order", 0) + 1
            queue.append((min(o, depth), q[j], math.atan2(v[1], v[0]),
                          max(np.linalg.norm(v) * 1.3, 2 * min_len) * rng.uniform(0.8, 1.3), sid, 3 * clr,
                          math.atan2(v[1], v[0])))
            continue
        queue.sort(key=lambda t: t[0])
        order, start, hd, L, host, ign, goal = queue.pop(0)
        ws = twig_wind ** order
        pts, info = _grow(sheet, rng, start, hd, L, prm, sid_next=len(sheet.strokes), host=host,
                          ignore_start=ign, wind_scale=ws, goal=goal, goal_gain=tropism / (1 + order),
                          edge_stop=True)
        if arclength(pts)[-1] < min_len:
            continue
        sid = sheet.add(pts, {"relation": "trunk" if host is None else "branch", "order": int(order),
                              "host": host, "end": info["end"], "end_host": info.get("host")})
        sheet.crossings += info.get("crosses", 0)
        if order >= depth:
            continue
        # forks along this branch: alternate sides, spacing ~ fork_every × length
        s = arclength(pts)
        Lb = s[-1]
        pos = rng.uniform(0.15, 0.35) * Lb
        side = 1 if rng.random() < 0.5 else -1
        while pos < 0.85 * Lb:
            if rng.random() < fork_skip * order:      # twigs fork less
                pos += fork_every * Lb * rng.uniform(0.6, 1.5)
                continue
            j = int(np.searchsorted(s, pos))
            j = min(max(j, 1), len(pts) - 2)
            tv = pts[j + 1] - pts[j - 1]
            ang = fork_angle * rng.uniform(0.6, 1.4)
            hd_c = math.atan2(tv[1], tv[0]) + side * ang
            Lc = (Lb - pos) * ratio * rng.uniform(0.7, 1.3) + ratio * 0.3 * Lb
            up = -np.pi / 2
            g_c = hd_c + 0.35 * math.sin(up - hd_c)         # branches keep their side, lean upward a little
            queue.append((order + 1, pts[j], hd_c, Lc, sid, 3 * clr, g_c))
            side = -side
            pos += fork_every * Lb * rng.uniform(0.6, 1.5)
    return _drawing(sheet, (W, H), "oehlen_tree",
                    {"params": {"trunks": trunks, "depth": depth, "ratio": ratio, "fork_every": fork_every,
                                "fork_angle": fork_angle, "wind": wind, "clearance_r": clearance_r,
                                "fill": fill, "p_meet_T": p_meet_T, "p_cross": p_cross, "tropism": tropism},
                     "coverage": _coverage(sheet)})


def _coverage(sheet: _Sheet) -> float:
    if not sheet.strokes:
        return 0.0
    allp = np.vstack(sheet.strokes)
    m = sheet.prm.margin
    u = np.clip((allp - m) / np.array([sheet.W - 2 * m, sheet.H - 2 * m]), 0, 1 - 1e-9)
    H, _, _ = np.histogram2d(u[:, 0], u[:, 1], bins=GRID, range=[[0, 1], [0, 1]])
    return float(np.mean(H > 0))
