"""The composite pipeline: structure → hand → (single line) → (tremor).

results/composite-2026-10-16.md. Library functions (imported by
tests/test_composite.py) plus subcommands (run from tools/gesture):

  composite(structure, hand, rng, ...)  one drawing:
      1. structure: `topology.generate_structure` — kind "oehlen_tree"
         (complexity params) or "learned" (the hand's own TopologyModel) —
         or any given Drawing (e.g. a real drawing's long strokes);
      2. restyle into the hand (`restyle.restyle_drawing`, FROZEN v6 grammar
         by default — `GRAMMAR_VERSION`, `grammar_version="v4"` for the
         round-3/4 numbers — gauss/trace with v6's corner budget, junctions
         welded) or `model="lognormal"` (the kinematic hand, `source="trace_ln"`);
      3. chain (optional): `chain_paths` joins the lines into as few
         continuous pen paths as possible (Euler path on the junction graph,
         odd ends paired by a min-weight matching = minimal retrace);
         chain="before" chains the skeleton and restyles the single line;
      4. tremor (optional): `gesture.tremor` with the per-hand default model
         (`TREMOR_DEFAULT`: v2 bursty for Hokusai/Ingres, v1 for Matisse),
         applied AFTER chaining; single lines go through `tremor_chain`
         (offset return passes follow their outward pass's displacement, so
         the double line keeps its spacing). results/composite-v6-2026-10-16.md.

  pairwise   panel pairwise hand test: same structure in hand A and hand B;
             a classifier trained on REAL drawings of A vs B says which is A.
  judge      blinded image pairs for a visual judge (key outside the repo).
  sheets     the composite sheets (trees × hands, chained, learned, translation).
  bench      cost per drawing of each pipeline stage.

    ../../.local/gesture/.venv/bin/python -m experiments.composite pairwise
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import grammar_v4_frozen as gm  # noqa: E402  (long_drawing, v4 baseline)
from gesture import grammar_v6_frozen as gm6  # noqa: E402,F401  (default hand grammar)
from gesture import restyle as rs  # noqa: E402
from gesture import topology  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUTROOT = ROOT / ".local/gesture/out"
GRAMMARS = OUTROOT / "grammar_v4_frozen"     # v4 snapshot: line widths (hand_w, w_common) and the v4 hands
GRAMMAR_DIRS = {"v4": GRAMMARS, "v6": OUTROOT / "grammar_v6_frozen"}
GRAMMAR_VERSION = "v6"                        # default hand grammar (composite-v6-2026-10-16.md); "v4" = rounds 3–4
TOPO = OUTROOT / "topology"
LOGN = OUTROOT / "lognormal"
EXTRACT = OUTROOT / "extract_hybrid"
OUT = OUTROOT / "composite"
RESULTS = Path(__file__).resolve().parents[1] / "results"
ARTISTS = ("matisse", "hokusai", "ingres")
JOBS = 3                                    # shared machine: keep pools small

_CACHE: dict = {}


def grammar(art: str, version: str | None = None):
    """The frozen learned grammar of a hand: version "v6" (default,
    `GRAMMAR_VERSION`) loads grammar_v6_frozen.Grammar from the v6 snapshot,
    "v4" the round-3/4 grammar."""
    v = version or GRAMMAR_VERSION
    k = ("g", art, v)
    if k not in _CACHE:
        mod = {"v4": gm, "v6": gm6}[v]
        _CACHE[k] = mod.Grammar.load(GRAMMAR_DIRS[v] / f"grammar_{art}.json")
    return _CACHE[k]


def topo_model(art: str):
    k = ("t", art)
    if k not in _CACHE:
        p = TOPO / f"model_{art}.json"
        _CACHE[k] = topology.TopologyModel.load(p) if p.exists() else None
    return _CACHE[k]


def ln_hand(art: str):
    k = ("l", art)
    if k not in _CACHE:
        from gesture import lognormal as ln
        _CACHE[k] = ln.Hand.load(LOGN / f"hand_{art}.json")
    return _CACHE[k]


# ---------------------------------------------------------------------------
# chaining: as few continuous pen paths as possible
# ---------------------------------------------------------------------------

def _arclen(p):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def _crossing_splits(S: list[np.ndarray], closed: list[bool]) -> dict[int, list]:
    """Insert X-crossing points: {stroke: [(segment index, point), ...]}."""
    from shapely import STRtree
    from shapely.geometry import LineString
    geoms = [LineString(np.vstack([p, p[:1]]) if c else p) for p, c in zip(S, closed)]
    tree = STRtree(geoms)
    out: dict[int, list] = {}
    for i, gi in enumerate(geoms):
        for j in tree.query(gi):
            j = int(j)
            if j <= i:
                continue
            x = gi.intersection(geoms[j])
            pts = [x] if x.geom_type == "Point" else [g for g in getattr(x, "geoms", []) if g.geom_type == "Point"]
            for pt in pts:
                c = np.array(pt.coords[0])
                for k in (i, j):
                    q = S[k] if not closed[k] else np.vstack([S[k], S[k][:1]])
                    a, b = q[:-1], q[1:]
                    ab = b - a
                    t = np.clip(np.sum((c - a) * ab, 1) / np.maximum(np.sum(ab * ab, 1), 1e-12), 0, 1)
                    seg = int(np.argmin(np.sum((a + t[:, None] * ab - c) ** 2, 1)))
                    out.setdefault(k, []).append((seg, c))
    return out


TURN_D_R = 0.01        # tangent estimation length at a node (R units), for turn angles


def _piece_dirs(pc: np.ndarray, d: float) -> tuple[np.ndarray, np.ndarray]:
    """(direction leaving the piece's start, direction arriving at its end),
    each a unit vector estimated over arc length d (at most the piece)."""
    s = _arclen(pc)
    dd = min(d, 0.5 * s[-1]) if s[-1] > 0 else 0.0
    j0 = int(np.clip(np.searchsorted(s, dd), 1, len(pc) - 1))
    j1 = int(np.clip(np.searchsorted(s, s[-1] - dd), 0, len(pc) - 2))
    a, b = pc[j0] - pc[0], pc[-1] - pc[j1]
    return a / max(np.linalg.norm(a), 1e-12), b / max(np.linalg.norm(b), 1e-12)


def _walk_min_turn(H, start, pieces: list, node: list, d: float) -> list:
    """An Euler trail/circuit of multigraph H from `start` (Fleury's rule:
    never cross a bridge while another edge is left) that, among the allowed
    edges, always continues with the smallest turning angle — the way a hand
    would carry on through a junction. Edges with piece −1 (virtual pen-up
    links) carry no direction. Returns [(u, v, key), ...]."""
    import networkx as nx
    H = H.copy()
    dirs = {k: _piece_dirs(pc, d) for k, pc in enumerate(pieces)}
    walk, u, arrive = [], start, None

    def leave_arrive(e):
        uu, vv, kk = e
        k0 = H.edges[uu, vv, kk]["piece"]
        if k0 < 0:
            return None, None
        a, b = dirs[k0]
        if node[2 * k0] == uu:
            return a, b
        return -b, -a

    def is_bridge(e):
        uu, vv, kk = e
        if uu == vv or H.number_of_edges(uu, vv) > 1:
            return False
        data = H.edges[uu, vv, kk]
        H.remove_edge(uu, vv, kk)
        ok = nx.has_path(H, uu, vv)
        H.add_edge(uu, vv, key=kk, **data)
        return not ok

    while H.degree(u) > 0:
        cands = sorted(H.edges(u, keys=True), key=lambda e: (str(e[1]), str(e[2])))
        if len(cands) > 1:
            nb = [e for e in cands if not is_bridge(e)]
            cands = nb or cands
        if arrive is not None and len(cands) > 1:
            def turn(e):
                lv, _ = leave_arrive(e)
                return 9.0 if lv is None else float(np.arccos(np.clip(np.dot(arrive, lv), -1, 1)))
            cands = sorted(cands, key=turn)
        e = cands[0]
        _, arrive = leave_arrive(e)
        walk.append(e)
        H.remove_edge(*e)
        u = e[1]
    return walk


def chain_paths(drawing: Drawing, *, tol_r: float = rs.WELD_R, at_crossings: bool = False,
                max_retrace: float | None = None, walk: str = "any", connect: bool = False,
                max_paths: int | None = None) -> Drawing:
    """Join a drawing's lines into as few continuous pen paths as possible.

    Graph: nodes are stroke ends, junction points (an end touching another
    line within tol_r·R splits that line there) and, with at_crossings, X
    crossings; edges are the line pieces between them. Per connected
    component, odd-degree nodes are paired by a min-weight matching on
    shortest-path length, with two virtual ends that may take any odd node
    for free (the exact open Chinese-postman pairing: the path's two ends
    are chosen optimally); the matched shortest paths are duplicated (that
    is the retrace, minimal) and an Euler path is walked. Every input
    line is drawn exactly once plus the retraces; the pen lifts only between
    components. max_retrace (fraction of the ink): add pen paths (2 more
    virtual ends each) until the retrace is below it — the
    trade between one line and doubled twigs. Pure; geometry in, geometry
    out (no smoothing).
    walk: "any" (networkx's Euler walk) | "min_turn" (`_walk_min_turn`:
    at every node continue with the smallest turn — fewer reversals and
    sharp junction turns for a hand to redraw).
    connect: join separate components with straight connector lines
    (minimum spanning tree over the closest node pairs) so a drawing of
    loose lines can still be ONE line; connectors are flagged. With
    max_paths, only the shortest connectors needed to get down to
    max_paths components are added.
    max_paths: at most this many pen paths (more trails for the largest
    component, zero retrace once every odd node has its own end).
    Returns a Drawing with one stroke per path, meta n_in / n_paths /
    ink / retrace (R units); each stroke's meta["chain_pieces"] lists
    (i0, i1, piece, forward, repeat, connector) for every piece it walks —
    the node passages that `restyle_chain` pins."""
    import networkx as nx
    from scipy.spatial import cKDTree
    S = [s.points.astype(float) for s in drawing.strokes if len(s.points) >= 2]
    C = [bool(s.closed) for s in drawing.strokes if len(s.points) >= 2]
    R = drawing.ref_length()
    tol = tol_r * R
    if not S:
        return Drawing([], source=drawing.source, size=drawing.size, meta={**drawing.meta, "chain": {}})
    # 0. optional crossing points, inserted as vertices
    if at_crossings:
        ins = _crossing_splits(S, C)
        for k, lst in ins.items():
            p = S[k]
            for seg, c in sorted(lst, key=lambda t: -t[0]):
                p = np.insert(p, seg + 1, c, axis=0)
            S[k] = p
    # 1. split indices per stroke where another stroke's end touches it
    P = np.vstack(S)
    own = np.concatenate([np.full(len(p), i) for i, p in enumerate(S)])
    loc = np.concatenate([np.arange(len(p)) for p in S])
    tree = cKDTree(P)
    cuts: list[set] = [set() for _ in S]
    for i, p in enumerate(S):
        if C[i]:
            continue
        for e in (0, len(p) - 1):
            cand = [j for j in tree.query_ball_point(p[e], tol) if own[j] != i]
            if cand:
                j = min(cand, key=lambda c: float(np.sum((P[c] - p[e]) ** 2)))
                cuts[own[j]].add(int(loc[j]))
    if at_crossings:
        for k in range(len(S)):
            # inserted crossing vertices are exact: find them as near-duplicates of other strokes' points
            d, _ = tree.query(S[k], k=2)
            for idx in np.where(d[:, 1] < 1e-9)[0]:
                cuts[k].add(int(idx))
    # 2. pieces
    pieces: list[np.ndarray] = []
    for i, p in enumerate(S):
        n = len(p)
        if C[i]:
            cs = sorted(cuts[i])
            if not cs:
                pieces.append(np.vstack([p, p[:1]]))
                continue
            q = np.vstack([p[cs[0]:], p[:cs[0]], p[cs[0]:cs[0] + 1]])
            rel = sorted({(c - cs[0]) % n for c in cs} | {n})
            for a, b in zip(rel[:-1], rel[1:]):
                pieces.append(q[a:b + 1])
        else:
            cs = sorted({c for c in cuts[i] if 0 < c < n - 1} | {0, n - 1})
            for a, b in zip(cs[:-1], cs[1:]):
                if b > a:
                    pieces.append(p[a:b + 1])
    # 3. nodes: piece ends clustered within tol (union-find)
    ends = np.vstack([[pc[0], pc[-1]] for pc in pieces])
    parent = list(range(len(ends)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, b in cKDTree(ends).query_pairs(tol):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    node = [find(a) for a in range(len(ends))]
    G = nx.MultiGraph()
    for k, pc in enumerate(pieces):
        G.add_edge(node[2 * k], node[2 * k + 1], key=k, piece=k, length=float(_arclen(pc)[-1]))
    connectors: set[int] = set()
    if connect and nx.number_connected_components(G) > 1:
        pos = {node[a]: ends[a] for a in range(len(ends))}
        comps = [sorted(c, key=str) for c in nx.connected_components(G)]
        CG = nx.Graph()
        for i in range(len(comps)):
            Pi = np.array([pos[v] for v in comps[i]])
            ti = cKDTree(Pi)
            for j in range(i + 1, len(comps)):
                Pj = np.array([pos[v] for v in comps[j]])
                dd, ii = ti.query(Pj)
                m = int(np.argmin(dd))
                CG.add_edge(i, j, weight=float(dd[m]), a=comps[i][int(ii[m])], b=comps[j][m])
        step = 0.002 * R
        mst = sorted(nx.minimum_spanning_edges(CG, data=True), key=lambda t: (t[2]["weight"], t[0], t[1]))
        if max_paths is not None:                    # only as many connectors as the path budget needs
            mst = mst[:max(0, len(comps) - int(max_paths))]
        for i, j, e in mst:
            pa, pb = pos[e["a"]], pos[e["b"]]
            n = max(int(np.ceil(np.linalg.norm(pb - pa) / step)), 1)
            k = len(pieces)
            pieces.append(pa + np.linspace(0, 1, n + 1)[:, None] * (pb - pa))
            node += [e["a"], e["b"]]
            connectors.add(k)
            G.add_edge(e["a"], e["b"], key=k, piece=k, length=float(np.linalg.norm(pb - pa)))
    ink = sum(d["length"] for _u, _v, d in G.edges(data=True))
    paths, retrace = [], 0.0
    path_pieces: list[list] = []
    seen: set[int] = set()
    nxt = len(pieces)
    comps_all = sorted(nx.connected_components(G), key=lambda c: -sum(
        d["length"] for _u, _v, d in G.subgraph(c).edges(data=True)))
    for ci, comp in enumerate(comps_all):
        H = G.subgraph(comp).copy()
        odd = [v for v in H.nodes if H.degree(v) % 2]
        if len(odd) > 2:
            dist, route = {}, {}
            for a in odd:
                dd, pp = nx.single_source_dijkstra(H, a, weight="length")
                for b in odd:
                    if b != a and b in dd:
                        dist[(a, b)], route[(a, b)] = dd[b], pp[b]
            comp_ink = sum(d["length"] for _u, _v, d in H.edges(data=True))

            def match(k):
                """Optimal pairing with k open trails: 2k virtual ends, each free
                to take any odd node at no cost (exact open Chinese postman)."""
                K = nx.Graph()
                for (a, b), w in dist.items():
                    if a < b:
                        K.add_edge(a, b, weight=w)
                for v in range(2 * k):
                    for a in odd:
                        K.add_edge(("virtual", v), a, weight=0.0)
                return [(a, b) for a, b in nx.min_weight_matching(K, weight="weight")
                        if not isinstance(a, tuple) and not isinstance(b, tuple)]
            k = 1
            if max_paths is not None and ci == 0:
                k = max(1, min(int(max_paths) - (len(comps_all) - 1), len(odd) // 2))
            keep = match(k)
            if max_retrace is not None:
                while keep and sum(dist[(x, y)] for x, y in keep) > max_retrace * comp_ink:
                    k += 1                           # one more pen path instead of the longest retraces
                    keep = match(k)
            for a, b in keep:
                r = route[(a, b)]
                for x, y in zip(r[:-1], r[1:]):
                    kk, dmin = min(((k_, d_) for k_, d_ in H.get_edge_data(x, y).items()),
                                   key=lambda t: t[1]["length"])
                    H.add_edge(x, y, key=nxt, piece=dmin["piece"], length=dmin["length"], retrace=True)
                    retrace += dmin["length"]
                    nxt += 1
        odd = [v for v in H.nodes if H.degree(v) % 2]
        multi = len(odd) > 2
        if multi:                                    # several trails: a virtual node makes it Eulerian
            for v in odd:
                H.add_edge(-1, v, key=nxt, piece=-1, length=0.0)
                nxt += 1
        start = -1 if multi else (odd[0] if odd else min(H.nodes, key=str))
        if not H.number_of_edges():
            walk_ = []
        elif walk == "min_turn":
            walk_ = _walk_min_turn(H, start, pieces, node, TURN_D_R * R)
        elif multi:
            walk_ = list(nx.eulerian_circuit(H, source=-1, keys=True))
        else:
            walk_ = list(nx.eulerian_path(H, source=start, keys=True))
        seq, meta_p, n_pts = [], [], 0
        for u, v, k in walk_:
            k0 = H.edges[u, v, k]["piece"]
            if k0 < 0:                               # through the virtual node: lift the pen
                if seq:
                    paths.append(np.vstack(seq))
                    path_pieces.append(meta_p)
                seq, meta_p, n_pts = [], [], 0
                continue
            pc = pieces[k0]
            fwd = node[2 * k0] == u
            pc = pc if fwd else pc[::-1]
            i0 = n_pts
            if seq and np.linalg.norm(seq[-1][-1] - pc[0]) < 1e-9:
                pc = pc[1:]
                i0 = n_pts - 1
            seq.append(pc)
            n_pts += len(pc)
            meta_p.append((i0, n_pts - 1, int(k0), bool(fwd), k0 in seen, k0 in connectors))
            seen.add(k0)
        if seq:
            paths.append(np.vstack(seq))
            path_pieces.append(meta_p)
    strokes = [Stroke(p, meta={"chain": True, "chain_pieces": mp}) for p, mp in zip(paths, path_pieces)
               if len(p) >= 2]
    conn = sum(float(_arclen(pieces[k])[-1]) for k in connectors)
    return Drawing(strokes, source=f"{drawing.source}|chain", size=drawing.size,
                   meta={**drawing.meta, "chain": {"n_in": len(S), "n_paths": len(strokes),
                                                   "ink_R": ink / R, "retrace_R": retrace / R,
                                                   "connector_R": conn / R, "walk": walk,
                                                   "at_crossings": at_crossings, "max_retrace": max_retrace,
                                                   "max_paths": max_paths}})


# ---------------------------------------------------------------------------
# chain fix: restyle a single line through a structure without balloons
# ---------------------------------------------------------------------------

PIN_REVERSAL = 150.0     # deg: a node turn this sharp is a reversal (always pinned unless pin="none")
OFFSET_W = 1.5           # retrace="offset": the return runs this many line widths beside the outward pass
RUN_SIGMAS = 3.0         # σ_s of a run ≤ its length / RUN_SIGMAS (≥ 3 pins; restyle_points max_sigma)


def node_turns(path: np.ndarray, pieces: list, d: float) -> np.ndarray:
    """Turn (deg, 0 = straight on, 180 = reversal) at every internal piece
    boundary of a chained path: boundary b sits between pieces b−1 and b."""
    out = []
    for b in range(1, len(pieces)):
        _, arr = _piece_dirs(path[pieces[b - 1][0]:pieces[b - 1][1] + 1], d)
        lv, _ = _piece_dirs(path[pieces[b][0]:pieces[b][1] + 1], d)
        out.append(float(np.degrees(np.arccos(np.clip(np.dot(arr, lv), -1, 1)))))
    return np.array(out)


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def offset_return(p: np.ndarray, delta: float, taper: float, side: float = 1.0) -> np.ndarray:
    """A return pass `delta` px beside polyline p (left of its direction for
    side = +1), the offset easing in from 0 over `taper` px at both ends —
    a narrow hairpin at the tip, a clean rejoin at the junction. Normals
    come from the tangent smoothed over ≈ 2 delta, so the offset follows
    the line's course, not its pixel noise."""
    from scipy.ndimage import gaussian_filter1d
    p = np.asarray(p, float)
    if len(p) < 3 or delta <= 0:
        return p.copy()
    s = _arclen(p)
    L = s[-1]
    if L <= 0:
        return p.copy()
    step = max(float(np.median(np.diff(s))), 1e-9)
    t = np.gradient(p, axis=0)
    t = gaussian_filter1d(t, max(2.0 * delta / step, 1.0), axis=0, mode="nearest")
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    n = np.column_stack([-t[:, 1], t[:, 0]])
    tp = max(min(taper, L / 3), 1e-9)
    w = _smoothstep(s / tp) * _smoothstep((L - s) / tp)
    return p + side * delta * w[:, None] * n


def _end_fix(out: np.ndarray, a: np.ndarray, b: np.ndarray, fade: float) -> np.ndarray:
    """Translate the two ends of `out` exactly onto a and b with cosine fades
    (the weld rule of restyle.weld_junctions, applied at both ends)."""
    s = _arclen(out)
    L = s[-1]
    d0, d1 = a - out[0], b - out[-1]
    f = max(min(max(fade, 3 * max(np.linalg.norm(d0), np.linalg.norm(d1))), 0.5 * L), 1e-9)
    w0 = np.where(s < f, 0.5 * (1 + np.cos(np.pi * np.clip(s / f, 0, 1))), 0.0)
    w1 = np.where(L - s < f, 0.5 * (1 + np.cos(np.pi * np.clip((L - s) / f, 0, 1))), 0.0)
    o = out + w0[:, None] * d0[None, :] + w1[:, None] * d1[None, :]
    o[0], o[-1] = a, b
    return o


def restyle_chain(chained: Drawing, g, *, amount: float, seed: int = 0, ref_length: float | None = None,
                  method: str = "gauss", source: str = "trace", scale: str = "drawing",
                  pin: str = "turns", pin_angle: float = 60.0, retrace: str = "offset",
                  offset_w: float = OFFSET_W, w: float | None = None,
                  run_sigmas: float | None = RUN_SIGMAS, budget: float | None = None) -> Drawing:
    """Redraw a chained skeleton (`chain_paths` output) in hand g as single
    lines that keep the structure — the chain fix.

    The one long line is cut at **anchors**, node passages the hand must not
    smooth through, and each run between anchors is restyled on its own
    (restyle_points: same decomposition / hand / pin fit as restyle_drawing)
    with both ends then moved exactly onto its anchors (cosine fade over
    WELD_FADE·σ_s); the runs are welded end to end, so the output is still
    one continuous line per path, with a hard corner at every anchor.
      pin: "none"  — no anchors (the old chain="before": one run per path);
           "tips"  — reversals only (a piece walked straight back, or a node
                     turn ≥ PIN_REVERSAL);
           "turns" — reversals and every node turn ≥ pin_angle (deg);
           "nodes" — every node passage.
      retrace: how a piece walked a second time is drawn:
           "redraw" — restyled again, independently (a second, different
                      pass of the hand);
           "exact"  — the first pass's drawn geometry, reversed (a true
                      retrace in the hand: invisible on paper);
           "offset" — that geometry `offset_w` line widths beside itself
                      (`offset_return`: a draughtsman's out-and-back, an
                      Oehlen-like double line). exact/offset add anchors
                      where the walk switches between first and repeat pieces.
    run_sigmas: cap σ_s at run length / run_sigmas, so a short run (a twig
    between two anchors) still gets interior pins; None = no cap.
    w: line width in px (default 0.0017 R, the corpus median).
    budget: v6 corner/turning budget gain inside trace (restyle.TRACE_BUDGET).
    Output stroke meta: "anchors" (point indices), "runs" ([i0, i1, is_return]
    per run, inclusive point indices; neighbouring runs share their anchor).
    Pure and deterministic (run r of path i draws from default_rng([seed, i, r]))."""
    R = float(ref_length) if ref_length is not None else chained.ref_length()
    w = float(w) if w is not None else 0.0017 * R
    sig = rs.sigma_of(amount) * R
    fade = rs.WELD_FADE * sig
    d_turn = TURN_D_R * R
    store: dict[int, np.ndarray] = {}      # piece → its drawn geometry, piece-forward orientation
    strokes, n_runs, n_anchor, n_ret, n_rev = [], 0, 0, 0, 0
    for pi, st in enumerate(chained.strokes):
        P = st.points
        mp = st.meta.get("chain_pieces")
        if not mp:
            o = rs.restyle_points(P, g, np.random.default_rng([int(seed), pi, 0]), amount=amount, ref_length=R,
                                  method=method, source=source, scale=scale, budget=budget)[0]
            strokes.append(Stroke(o, meta={"chain": True}))
            continue
        turns = node_turns(P, mp, d_turn)
        cut = []
        for b in range(1, len(mp)):
            rev = mp[b][2] == mp[b - 1][2] or turns[b - 1] >= PIN_REVERSAL
            n_rev += int(rev)
            a = (pin != "none" and rev) or (pin == "turns" and turns[b - 1] >= pin_angle) or pin == "nodes" \
                or (retrace != "redraw" and mp[b][4] != mp[b - 1][4])
            if a:
                cut.append(b)
        n_anchor += len(cut)
        bounds = [0] + cut + [len(mp)]
        parts, anchors_out, spans = [], [], []
        for r, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
            i_s, i_e = mp[a][0], mp[b - 1][1]
            src = P[i_s:i_e + 1]
            is_ret = retrace != "redraw" and all(mp[t][4] for t in range(a, b)) and \
                all(mp[t][2] in store for t in range(a, b))
            if is_ret:
                geo = []
                for t in range(a, b):
                    q = store[mp[t][2]]
                    q = q if mp[t][3] else q[::-1]
                    if geo and np.linalg.norm(geo[-1][-1] - q[0]) < 1e-9:
                        q = q[1:]
                    geo.append(q)
                out = np.vstack(geo)
                if retrace == "offset":
                    out = offset_return(out, offset_w * w, max(4 * offset_w * w, 0.004 * R))
                out = _end_fix(out, src[0], src[-1], fade)
                n_ret += 1
            else:
                s = _arclen(src)
                cap = s[-1] / run_sigmas if run_sigmas else None
                o, info = rs.restyle_points(src, g, np.random.default_rng([int(seed), pi, r]), amount=amount,
                                            ref_length=R, closed=False, method=method, source=source, scale=scale,
                                            max_sigma=cap, budget=budget)
                out = _end_fix(o, src[0], src[-1], rs.WELD_FADE * min(sig, cap or sig))
                M = info.get("M")
                for t in range(a, b):
                    if mp[t][2] in store:
                        continue
                    if M is not None and len(out) == M + 1:
                        j0 = int(round(s[mp[t][0] - i_s] / max(s[-1], 1e-12) * M))
                        j1 = int(round(s[mp[t][1] - i_s] / max(s[-1], 1e-12) * M))
                    else:
                        j0, j1 = mp[t][0] - i_s, mp[t][1] - i_s
                    q = out[j0:max(j1, j0 + 1) + 1]
                    store[mp[t][2]] = q if mp[t][3] else q[::-1]
            n_runs += 1
            i0 = sum(len(x) for x in parts) - 1 if parts else 0
            if parts:
                out = out[1:]
            parts.append(out)
            anchors_out.append(sum(len(x) for x in parts) - 1)
            spans.append([int(i0), int(anchors_out[-1]), bool(is_ret)])
        strokes.append(Stroke(np.vstack(parts), meta={"chain": True, "anchors": anchors_out[:-1],
                                                      "n_runs": len(parts), "runs": spans}))
    return Drawing(strokes, source=f"{chained.source}|restyle_chain:{getattr(g, 'name', '')}:{amount:g}",
                   size=chained.size, meta={**chained.meta, "restyle_chain": {
                       "pin": pin, "pin_angle": pin_angle, "retrace": retrace, "offset_w": offset_w,
                       "run_sigmas": run_sigmas,
                       "runs": n_runs, "anchors": n_anchor, "return_runs": n_ret, "reversals": n_rev,
                       "amount": float(amount), "sigma_s_R": sig / R}})


# ---------------------------------------------------------------------------
# the composite
# ---------------------------------------------------------------------------

def structure_of(kind, hand: str | None, rng, size, params: dict | None = None) -> Drawing:
    if isinstance(kind, Drawing):
        return kind
    if kind == "oehlen_tree":
        return topology.generate_structure(None, rng, size, kind="oehlen_tree", **(params or {}))
    if kind == "learned":
        return topology.generate_structure(topo_model(hand) if hand else None, rng, size, kind="learned",
                                           **(params or {}))
    raise ValueError(f"unknown structure kind {kind!r}")


def hand_w(art: str) -> float:
    """The hand's median line width w/R over its real drawings (corpus
    median 0.0017 for an unnamed hand). Read from the v4 snapshot for every
    grammar version, so offsets and measurements stay comparable."""
    if art in ARTISTS and GRAMMARS.exists():
        try:
            return float(np.median([x["w_over_R"] for x in grammar(art, "v4").drawings if x["w_over_R"] > 0]))
        except Exception:  # noqa: BLE001
            pass
    return 0.0017


# per-hand default tremor (tremor-v2-2026-10-16.md §7): v2 (bursty) where it
# closes the burst gap, v1 for Matisse (v2 overshoots there). (dir, model, apply_tremor mode)
TREMOR_DIRS = {"v1": OUTROOT / "tremor" / "models", "v2": OUTROOT / "tremor_v2" / "models"}
TREMOR_DEFAULT = {"matisse": ("v1", "matisse", "v1"), "hokusai": ("v2", "hokusai", "auto"),
                  "ingres": ("v2", "ingres", "auto")}
TREMOR_CHOICES = {"v1": lambda art: ("v1", art, "v1"), "v2": lambda art: ("v2", art, "auto"),
                  "v2_etching": lambda art: ("v2", "matisse_etching", "auto"),
                  "default": lambda art: TREMOR_DEFAULT.get(art, ("v1", art, "v1"))}


def tremor_model(art: str, which: str = "default"):
    """(TremorModel, apply mode, label) for a hand: which = "default" (per
    hand, `TREMOR_DEFAULT`), "v1", "v2" or "v2_etching" (Matisse etching v2,
    no kinks). Raises if the model file is missing."""
    from gesture import tremor as tr
    ver, name, mode = TREMOR_CHOICES[which](art)
    p = TREMOR_DIRS[ver] / f"{name}.json"
    k = ("tremor", str(p))
    if k not in _CACHE:
        _CACHE[k] = tr.TremorModel.load(p)
    return _CACHE[k], mode, f"{ver}:{name}"


def _arc_index(s_from: np.ndarray, s_to: np.ndarray) -> np.ndarray:
    """For each arc position in s_from, the nearest sample index in s_to."""
    j = np.clip(np.searchsorted(s_to, s_from), 1, len(s_to) - 1)
    return np.where(np.abs(s_to[j - 1] - s_from) <= np.abs(s_to[j] - s_from), j - 1, j)


def tremor_chain(d: Drawing, model, rng: np.random.Generator, amount: float, *, w: float, mode: str = "auto",
                 returns: str = "follow", pin_w: float = 0.0) -> Drawing:
    """Tremor on chained single lines (`restyle_chain` output), AFTER the
    chain. Each pen path gets one tremor displacement (gesture.tremor's
    per-stroke synthesis: ends pinned, κ/end envelope, v2 regime + kinks).
    returns: "follow" — a return pass (meta "runs" is_return) takes the
    displacement *vector* of the nearest outward-pass sample, so an offset
    return keeps its spacing exactly (one hand-tremor field over the
    double line); "independent" — each pass trembles on its own (plain
    apply_tremor on the path; the passes can touch).
    pin_w: ramp the displacement to 0 within pin_w line widths of every
    anchor (junction passage), 0 = off. Strokes without "runs" meta fall
    back to plain apply_tremor for that stroke. Pure; deterministic in rng."""
    from scipy.spatial import cKDTree

    from gesture import tremor as tr
    out, rms = [], []
    v2 = mode != "v1" and getattr(model, "version", 1) >= 2
    for st in d.strokes:
        if len(st) < 3 or st.length() < 4 * w:
            out.append(Stroke(st.points.copy(), closed=st.closed, meta=dict(st.meta)))
            continue
        q, P, disp = tr._perturb_stroke(st, w, model, rng, amount, v2=v2)
        disp = disp.copy()
        runs = st.meta.get("runs")
        s0, s1 = _arclen(st.points), _arclen(P)
        if returns == "follow" and runs and any(r[2] for r in runs):
            ret = np.zeros(len(P), bool)
            for i0, i1, is_ret in runs:
                if is_ret:
                    ret |= (s1 >= s0[i0]) & (s1 <= s0[i1])
            if (~ret).sum() >= 2 and ret.any():
                _, j = cKDTree(P[~ret]).query(P[ret])
                disp[ret] = disp[~ret][j]
        elif returns not in ("follow", "independent"):
            raise ValueError(f"unknown returns {returns!r}")
        an = st.meta.get("anchors") or []
        if pin_w > 0 and an:
            sa = s0[np.asarray(an, int)]
            dmin = np.min(np.abs(s1[:, None] - sa[None, :]), axis=1) if len(sa) < 4000 else \
                np.abs(s1 - sa[np.clip(_arc_index(s1, sa), 0, len(sa) - 1)])
            disp *= _smoothstep(dmin / (pin_w * w))[:, None]
        rms.append(float(np.sqrt(np.mean(np.sum(disp ** 2, 1)))))
        m = dict(st.meta)
        if runs:     # re-index runs / anchors onto the resampled points
            m["runs"] = [[int(_arc_index(np.array([s0[a]]), s1)[0]), int(_arc_index(np.array([s0[b]]), s1)[0]), r]
                         for a, b, r in runs]
            m["anchors"] = [int(x) for x in _arc_index(s0[np.asarray(an, int)], s1)] if an else []
        m["tremor"] = {"model": model.name, "amount": float(amount), "mode": mode, "returns": returns}
        out.append(Stroke(P + disp, closed=st.closed, meta=m))
    return Drawing(out, source=d.source, size=d.size,
                   meta={**d.meta, "tremor": {"model": model.name, "amount": float(amount), "mode": mode,
                                              "returns": returns, "w": float(w),
                                              "disp_rms_px": float(np.median(rms)) if rms else 0.0}})


def _tangents(P: np.ndarray) -> np.ndarray:
    t = np.gradient(P, axis=0)
    return t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)


def return_spacing(d: Drawing, w: float, R: float, offset_w: float = OFFSET_W) -> dict:
    """The double line's spacing: for every return-pass sample (meta "runs"
    is_return) outside its taper zones (taper as in restyle_chain), the
    distance to its **counterpart** — the nearest OUTWARD-pass sample running
    the opposite way (tangent dot < −0.7) within 4 w — in line widths: min,
    q01, q50, share below 1.0 / 0.5 w, and the share of return samples with
    no counterpart (`sp_unpaired`, e.g. where a return passes a node). Other
    lines crossing the return are structure, not spacing, and are ignored.
    Without return runs: empty dict."""
    from scipy.spatial import cKDTree
    taper = max(4 * offset_w * w, 0.004 * R)
    vals, unpaired, tot = [], 0, 0
    for st in d.strokes:
        runs = st.meta.get("runs")
        if not runs or not any(r[2] for r in runs):
            continue
        P = st.points
        T = _tangents(P)
        first = np.ones(len(P), bool)
        for i0, i1, ret in runs:
            if ret:
                first[i0 + 1:i1] = False
        if first.sum() < 2:
            continue
        F, TF = P[first], T[first]
        tree = cKDTree(F)
        for i0, i1, ret in runs:
            if not ret or i1 - i0 < 4:
                continue
            q, tq = P[i0:i1 + 1], T[i0:i1 + 1]
            s = _arclen(q)
            m = np.flatnonzero((s > taper) & (s < s[-1] - taper))
            if not len(m):
                continue
            dd, jj = tree.query(q[m], k=24, distance_upper_bound=4 * w)
            for row, (dr, jr) in enumerate(zip(dd, jj)):
                tot += 1
                ok = np.isfinite(dr)
                if ok.any():
                    jr, dr = jr[ok], dr[ok]
                    anti = (TF[jr] @ tq[m[row]]) < -0.7
                    if anti.any():
                        vals.append(dr[anti].min() / w)
                        continue
                unpaired += 1
    if not vals:
        return {}
    v = np.asarray(vals)
    return {"sp_min": float(v.min()), "sp_q01": float(np.quantile(v, 0.01)), "sp_q50": float(np.median(v)),
            "sp_lt1": float(np.mean(v < 1.0)), "sp_lt05": float(np.mean(v < 0.5)), "sp_n": int(len(v)),
            "sp_unpaired": unpaired / max(tot, 1)}


def _tremor(d: Drawing, art: str, rng, amount: float, which: str = "default", returns: str = "follow",
            pin_w: float = 0.0):
    """Tremor stage (after the chain): the hand's default model
    (`tremor_model`), line width w = the hand's own median w/R × R so the
    tremor is at the hand's scale. Single lines (strokes with "runs" meta)
    go through `tremor_chain`, everything else through apply_tremor (which
    re-snaps contacts). Returns (drawing, note)."""
    try:
        from gesture import tremor as tr
        model, mode, lab = tremor_model(art, which)
    except Exception as e:  # noqa: BLE001
        return d, f"tremor unavailable: {e}"
    w = hand_w(art) * d.ref_length()
    if any(st.meta.get("runs") for st in d.strokes):
        return tremor_chain(d, model, rng, amount, w=w, mode=mode, returns=returns, pin_w=pin_w), \
            f"tremor {lab} ({mode}) x{amount:g}, chain, returns {returns}"
    return tr.apply_tremor(d, model, rng, amount, w=w, mode=mode), f"tremor {lab} ({mode}) x{amount:g}"


def composite(structure, hand, rng: np.random.Generator, *, size=1200, amount: float = 0.6,
              chain: bool | str = False, tremor: float | None = None, model: str = "grammar",
              method: str = "gauss", scale: str = "drawing", weld: bool = True,
              structure_params: dict | None = None, at_crossings: bool = False,
              structure_hand: str | None = None, max_retrace: float | None = None,
              pin: str = "none", pin_angle: float = 60.0, retrace: str = "redraw", offset_w: float = OFFSET_W,
              walk: str = "any", connect: bool = False, max_paths: int | None = None,
              run_sigmas: float | None = RUN_SIGMAS, grammar_version: str | None = None,
              budget: float | None = None, tremor_which: str = "default", tremor_returns: str = "follow",
              tremor_pin_w: float = 0.0) -> Drawing:
    """structure ("oehlen_tree" | "learned" | a Drawing) → restyled into
    `hand` (artist name, or a Grammar / lognormal.Hand object; model
    "grammar" = frozen grammar (`grammar_version`, default GRAMMAR_VERSION
    "v6", with v6's corner budget at gain `budget`, default
    restyle.TRACE_BUDGET) + trace, "lognormal" =
    kinematic trace) → optional chain (True/"after": chain the restyled
    lines; "before": chain the skeleton, restyle the single line) →
    optional tremor amount. "learned" uses structure_hand's TopologyModel
    (default: the hand's own). Deterministic in rng; inputs never mutated.
    Chain options (`chain_paths`): walk ("any" | "min_turn"), connect,
    max_paths, max_retrace. chain="before" with pin/retrace other than
    "none"/"redraw" is the chain fix (`restyle_chain`: anchors at reversals /
    sharp node turns, offset or exact return passes); line width for the
    offset = the hand's own median w/R × R.
    tremor: amount (None/0 = off), model `tremor_which` (default per hand),
    single lines via `tremor_chain` (returns `tremor_returns`, pins
    `tremor_pin_w`).
    meta["composite"] records stages and seconds per stage."""
    t0 = time.perf_counter()
    s_seed, r_seed, t_seed = (int(x) for x in rng.integers(0, 2 ** 31, 3))
    named = isinstance(hand, str)
    st = structure_of(structure, structure_hand or (hand if named else None), np.random.default_rng(s_seed), size,
                      structure_params)
    t1 = time.perf_counter()
    g = hand if not named else grammar(hand, grammar_version) if model == "grammar" else ln_hand(hand)
    hname = hand if named else getattr(hand, "name", "")
    src = "trace" if model == "grammar" else "trace_ln"
    R = st.ref_length()
    cm = {}
    ckw = dict(at_crossings=at_crossings, max_retrace=max_retrace, walk=walk, connect=connect, max_paths=max_paths)
    if chain == "before":
        sk = chain_paths(st, **ckw)
        cm = sk.meta.get("chain", {})
        if pin == "none" and retrace == "redraw":
            o = rs.restyle_drawing(sk, g, amount=amount, seed=r_seed, method=method, source=src,
                                   ref_length=R, scale=scale, weld=False, budget=budget)
        else:
            o = restyle_chain(sk, g, amount=amount, seed=r_seed, ref_length=R, method=method, source=src,
                              scale=scale, pin=pin, pin_angle=pin_angle, retrace=retrace, offset_w=offset_w,
                              w=hand_w(hname) * R, run_sigmas=run_sigmas, budget=budget)
            cm = {**cm, **o.meta.get("restyle_chain", {})}
        t2 = t3 = time.perf_counter()
    else:
        o = rs.restyle_drawing(st, g, amount=amount, seed=r_seed, method=method, source=src,
                               ref_length=R, scale=scale, weld=weld, budget=budget)
        t2 = time.perf_counter()
        if chain:
            o = chain_paths(o, **ckw)
            cm = o.meta.get("chain", {})
        t3 = time.perf_counter()
    note = ""
    if tremor:
        o, note = _tremor(o, hname, np.random.default_rng(t_seed), float(tremor), tremor_which, tremor_returns,
                          tremor_pin_w)
    t4 = time.perf_counter()
    kind = structure if isinstance(structure, str) else "given"
    return Drawing(o.strokes, source=f"composite:{kind}:{hname}:{model}:{amount:g}", size=st.size,
                   meta={"composite": {"structure": kind, "hand": hname, "model": model, "amount": amount,
                                       "grammar": (grammar_version or GRAMMAR_VERSION) if model == "grammar" else None,
                                       "tremor_meta": o.meta.get("tremor"),
                                       "chain": chain, "tremor": tremor, "tremor_note": note,
                                       "n_structure": len(st.strokes), "n_out": len(o.strokes),
                                       "chain_meta": cm, "welds": o.meta.get("restyle", {}).get("welds"),
                                       "sec": {"structure": t1 - t0, "restyle": t2 - t1,
                                               "chain": t3 - t2, "tremor": t4 - t3}},
                         "structure_meta": {k: v for k, v in st.meta.items() if k in ("kind", "params", "coverage")}})


# ---------------------------------------------------------------------------
# plot readiness: SVG in millimetres (no plotting, no app integration)
# ---------------------------------------------------------------------------

PAPERS = {"A5": (210.0, 148.0), "A4": (297.0, 210.0), "A3": (420.0, 297.0)}   # landscape, mm
PLOT_SPEED = 25.0        # mm/s, nominal pen-down speed for the time estimate
PEN_CYCLE_S = 0.5        # s per pen lift + lower (nominal)


def to_mm(drawing: Drawing, *, paper: str | tuple = "A4", portrait: bool = False, margin_mm: float = 10.0,
          simplify_mm: float = 0.02) -> list[np.ndarray]:
    """The drawing's strokes as polylines in mm on the paper (y down, origin
    top-left), fitted into the paper minus `margin_mm` with the aspect ratio
    kept and centred; stroke (= pen path) order preserved; each polyline
    Douglas–Peucker simplified at `simplify_mm` (far below a pen width).
    Closed strokes are closed explicitly."""
    from shapely.geometry import LineString
    W, H = PAPERS[paper] if isinstance(paper, str) else paper
    if portrait:
        W, H = min(W, H), max(W, H)
    ss = [np.vstack([s.points, s.points[:1]]) if s.closed else s.points for s in drawing.strokes if len(s) >= 2]
    if not ss:
        return []
    P = np.vstack(ss)
    lo, hi = P.min(0), P.max(0)
    span = np.maximum(hi - lo, 1e-9)
    k = min((W - 2 * margin_mm) / span[0], (H - 2 * margin_mm) / span[1])
    off = np.array([W, H]) / 2 - (lo + hi) / 2 * k
    out = []
    for p in ss:
        q = p * k + off
        if simplify_mm > 0 and len(q) > 2:
            q = np.asarray(LineString(q).simplify(simplify_mm, preserve_topology=False).coords)
        out.append(q)
    return out


def plot_stats(paths_mm: list[np.ndarray], *, speed: float = PLOT_SPEED, pen_cycle_s: float = PEN_CYCLE_S,
               home=(0.0, 0.0)) -> dict:
    """Pen-down length, pen-up travel (home → paths in order → home), lifts
    and a nominal time: (down + up travel) / speed + one pen cycle per path."""
    down = float(sum(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)) for p in paths_mm))
    pos, up = np.asarray(home, float), 0.0
    for p in paths_mm:
        up += float(np.linalg.norm(p[0] - pos))
        pos = p[-1]
    up += float(np.linalg.norm(pos - np.asarray(home, float))) if paths_mm else 0.0
    n = len(paths_mm)
    t = (down + up) / speed + n * pen_cycle_s
    return {"paths": n, "lifts": max(n - 1, 0), "pen_down_mm": round(down, 1), "pen_up_mm": round(up, 1),
            "points": int(sum(len(p) for p in paths_mm)), "est_min": round(t / 60.0, 1),
            "speed_mm_s": speed, "pen_cycle_s": pen_cycle_s}


def to_svg(drawing: Drawing, path: str | Path | None = None, *, paper: str | tuple = "A4", portrait: bool = False,
           margin_mm: float = 10.0, pen_mm: float = 0.4, simplify_mm: float = 0.02,
           title: str = "") -> tuple[str, dict]:
    """A composite Drawing as an SVG in millimetres for the given paper
    (default A4 landscape, 10 mm margin): one <path> per pen path, in pen
    order, stroke width `pen_mm`. Returns (svg text, plot_stats + paper);
    writes it when `path` is given."""
    W, H = PAPERS[paper] if isinstance(paper, str) else paper
    if portrait:
        W, H = min(W, H), max(W, H)
    paths = to_mm(drawing, paper=(W, H), margin_mm=margin_mm, simplify_mm=simplify_mm)
    st = {**plot_stats(paths), "paper_mm": [W, H], "margin_mm": margin_mm, "pen_mm": pen_mm}
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:g}mm" height="{H:g}mm" viewBox="0 0 {W:g} {H:g}">',
         f"<title>{title or drawing.source}</title>",
         f"<!-- {json.dumps(st)} -->",
         f'<g fill="none" stroke="black" stroke-width="{pen_mm:g}" stroke-linecap="round" stroke-linejoin="round">']
    for i, p in enumerate(paths):
        d = "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in p)
        L.append(f'<path id="p{i:03d}" d="{d}"/>')
    L += ["</g>", "</svg>", ""]
    svg = "\n".join(L)
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(svg)
    return svg, st


def read_svg_paths(svg: str) -> tuple[tuple[float, float], list[np.ndarray]]:
    """((width, height) in mm, polylines) of an SVG written by `to_svg`."""
    import re
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    paths = []
    for d in re.findall(r'<path id="[^"]*" d="([^"]*)"', svg):
        pts = [tuple(float(v) for v in t.split(",")) for t in re.findall(r"[ML]([-\d.]+,[-\d.]+)", d)]
        paths.append(np.array(pts))
    return (float(m.group(1)), float(m.group(2))), paths


def real_structure(art: str, stem: str, size: int = 1200) -> Drawing:
    """A real drawing's long strokes (the grammar's training domain), fitted
    into a size-px canvas with a 4 % margin."""
    d = gm.long_drawing(Drawing.load(EXTRACT / art / f"{stem}.json"))
    P = np.vstack([s.points for s in d.strokes])
    lo, hi = P.min(0), P.max(0)
    m = 0.04 * size
    k = (size - 2 * m) / max(float((hi - lo).max()), 1e-9)
    off = m + 0.5 * ((size - 2 * m) - (hi - lo) * k)
    return Drawing([Stroke((s.points - lo) * k + off, closed=s.closed) for s in d.strokes],
                   source=f"real:{art}:{stem}", size=(size, size))


# ---------------------------------------------------------------------------
# measurement helpers (shared with restyle_study's conventions)
# ---------------------------------------------------------------------------

TEXTURE_GROUPS = ("k", "ext", "infl", "turn", "cl")


def feats(d: Drawing, clothoid: bool = True) -> dict:
    """Panel features at the standard σ floor. clothoid=False skips the cl
    group (its fit takes minutes on a 20 000-point single line)."""
    from gesture import medium, panel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W, clothoid=clothoid)
    return f


def with_width(d: Drawing, wr: float) -> Drawing:
    R = d.ref_length()
    return Drawing([Stroke(s.points, width=np.full(len(s), wr * R), closed=s.closed) for s in d.strokes
                    if len(s) >= 2], source=d.source, size=d.size)


def w_common() -> float:
    ws = []
    for art in ARTISTS:
        ws += [d["w_over_R"] for d in grammar(art, "v4").drawings if d["w_over_R"] > 0]
    return float(np.median(ws))


def _real_job(args):
    art, path = args
    d = gm.long_drawing(Drawing.load(path))
    if len(d.strokes) < 2:
        return None
    return art, Path(path).stem, feats(d)


def real_feats() -> list:
    p = OUT / "real_feats.json"
    if p.exists():
        return [tuple(r) for r in json.loads(p.read_text())]
    OUT.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(JOBS) as ex:
        real = [r for r in ex.map(_real_job, [(a, str(q)) for a in ARTISTS
                                              for q in sorted((EXTRACT / a).glob("*.json"))]) if r]
    p.write_text(json.dumps(real))
    return real


class PairClassifier:
    """Logistic regression on texture panel features of REAL long-stroke
    drawings of two hands, standard preprocessing (σ ≥ 7 w floor in `feats`
    + medium projection)."""

    def __init__(self, real, a: str, b: str, seed: int = 0, groups: tuple = TEXTURE_GROUPS):
        from sklearn.linear_model import LogisticRegression

        from gesture import medium, panel
        real = [r for r in real if r[0] in (a, b)]
        allk = set.intersection(*[set(f) for _a, _s, f in real])
        self.names = sorted(n for n in allk if panel.group_of(n) in groups)
        X = self.matrix([f for _a, _s, f in real])
        ok = ~np.all(np.isnan(X), axis=0)
        self.names = [n for n, o in zip(self.names, ok) if o]
        X = X[:, ok]
        art = np.array([r[0] for r in real])
        lut = medium.load_media()
        med = np.array([lut.get((r[0], r[1]), "unknown") for r in real])
        self.pj = medium.MediumProjector(medium.load_pairs(), seed=seed).fit(X, art, med)
        self.Z, self.y = self.pj.transform(X), (art == a).astype(int)
        self.a, self.b = a, b
        self.clf = LogisticRegression(C=0.3, max_iter=5000).fit(self.Z, self.y)

    def matrix(self, fs):
        return np.array([[f.get(n, np.nan) for n in self.names] for f in fs], dtype=float)

    def score(self, fs) -> np.ndarray:
        """P(hand a) per feature dict."""
        return self.clf.predict_proba(self.pj.transform(self.matrix(fs)))[:, 1]

    def cv_pairwise(self, seed: int = 0, n_pairs: int = 400) -> tuple[float, float]:
        """(CV accuracy, CV pairwise accuracy: random held-out real a vs real b)."""
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import StratifiedKFold, cross_val_predict
        p = cross_val_predict(LogisticRegression(C=0.3, max_iter=5000), self.Z, self.y,
                              cv=StratifiedKFold(5, shuffle=True, random_state=seed), method="predict_proba")[:, 1]
        acc = float(np.mean((p > 0.5) == self.y))
        rng = np.random.default_rng(seed)
        ia, ib = np.where(self.y == 1)[0], np.where(self.y == 0)[0]
        pa, pb = p[rng.choice(ia, n_pairs)], p[rng.choice(ib, n_pairs)]
        return acc, float(np.mean(pa > pb) + 0.5 * np.mean(pa == pb))


# ---------------------------------------------------------------------------
# pairwise hand test (panel)
# ---------------------------------------------------------------------------

def pair_structures(n_tree: int, n_learned: int, size: int = 1200) -> dict[str, Drawing]:
    S = {}
    for i in range(n_tree):
        rng = np.random.default_rng([31, i])
        prm = {"depth": int(3 + i % 3), "fill": float(0.7 + 0.1 * (i % 3)), "trunks": int(1 + (i // 3) % 3)}
        S[f"tree{i:02d}"] = topology.generate_structure(None, rng, size, kind="oehlen_tree", **prm)
    for i in range(n_learned):
        art = ARTISTS[i % 3]
        S[f"learned_{art}{i:02d}"] = topology.generate_structure(topo_model(art), np.random.default_rng([32, i]),
                                                                 size, kind="learned")
    return S


def _pair_job(args):
    name, d, hand, amount, seed, wr, model, chain = args
    t0 = time.time()
    g = grammar(hand) if model == "grammar" else ln_hand(hand)
    o = rs.restyle_drawing(d, g, amount=amount, seed=seed, source="trace" if model == "grammar" else "trace_ln")
    if chain:
        o = chain_paths(o)
    return {"src": name, "hand": hand, "amount": amount, "model": model, "chain": bool(chain),
            "time": time.time() - t0, "feats": feats(with_width(o, wr))}


def _gen_job(args):
    hand, seed, wr = args
    d = gm.generate_drawing(grammar(hand, "v4"), np.random.default_rng(seed), (1200, 1200))
    return hand, feats(with_width(d, wr))


def cmd_pairwise(a):
    OUT.mkdir(parents=True, exist_ok=True)
    real = real_feats()
    wr = w_common()
    S = pair_structures(a.n_tree, a.n_learned)
    amounts = [float(x) for x in a.amounts.split(",")]
    models = a.models.split(",")
    jobs = [(n, d, h, amt, a.seed, wr, m, False) for n, d in S.items() for h in ARTISTS for amt in amounts
            for m in models]
    cache = OUT / "pairwise_rows.jsonl"
    done = {}
    if cache.exists():
        for line in cache.read_text().splitlines():
            try:
                r = json.loads(line)
                done[r["key"]] = r
            except Exception:  # noqa: BLE001
                pass
    key = lambda j: f"{j[0]}|{j[2]}|{j[3]:g}|{j[6]}|{j[4]}"   # noqa: E731
    todo = [j for j in jobs if key(j) not in done]
    print(f"pairwise: {len(S)} structures, {len(done)} cached, {len(todo)} to run", flush=True)
    t0 = time.time()
    from concurrent.futures import as_completed
    with ProcessPoolExecutor(JOBS) as ex, open(cache, "a") as fh:
        futs = {ex.submit(_pair_job, j): key(j) for j in todo}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            r["key"] = futs[f]
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            done[r["key"]] = r
            if i % 20 == 0:
                print(f"  {i}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    rows = [done[key(j)] for j in jobs]
    with ProcessPoolExecutor(JOBS) as ex:
        gens = list(ex.map(_gen_job, [(h, 500 + i, wr) for h in ARTISTS for i in range(a.n_gen)]))
    rep = {"n_structures": len(S), "amounts": amounts, "models": models, "w_common": wr, "pairs": []}
    from scipy.stats import binomtest
    for A, B in (("matisse", "hokusai"), ("matisse", "ingres"), ("hokusai", "ingres")):
        pc = PairClassifier(real, A, B)
        cv, cvp = pc.cv_pairwise()
        gA = [f for h, f in gens if h == A]
        gB = [f for h, f in gens if h == B]
        sA, sB = pc.score(gA), pc.score(gB)
        gen_pair = float(np.mean(sA[:, None] > sB[None, :]))
        ent = {"A": A, "B": B, "n_real": int(len(pc.y)), "n_feat": len(pc.names), "cv_acc": cv,
               "cv_pairwise_real": cvp, "gen_pairwise": gen_pair, "cells": []}
        for m in models:
            for amt in amounts:
                for fam in ("all", "tree", "learned"):
                    ok, n, margins = 0, 0, []
                    for name in S:
                        if fam != "all" and not name.startswith(fam):
                            continue
                        ra = next(r for r in rows if r["src"] == name and r["hand"] == A and r["amount"] == amt
                                  and r["model"] == m)
                        rb = next(r for r in rows if r["src"] == name and r["hand"] == B and r["amount"] == amt
                                  and r["model"] == m)
                        pa, pb = pc.score([ra["feats"], rb["feats"]])
                        ok += int(pa > pb)
                        n += 1
                        margins.append(float(pa - pb))
                    if n:
                        ent["cells"].append({"model": m, "amount": amt, "family": fam, "n": n, "acc": ok / n,
                                             "p_binom": float(binomtest(ok, n, 0.5, alternative="greater").pvalue),
                                             "margin_med": float(np.median(margins))})
        rep["pairs"].append(ent)
    rep["time_med"] = {f"{m}@{amt:g}": float(np.median([r["time"] for r in rows if r["model"] == m
                                                         and r["amount"] == amt])) for m in models for amt in amounts}
    (OUT / "pairwise.json").write_text(json.dumps(rep, indent=1))
    md = pairwise_md(rep)
    (OUT / "pairwise.md").write_text(md)
    print(md)


def pairwise_md(rep) -> str:
    L = ["| # | pair (A vs B) | model | amount | family | n | pairwise acc | p (> 0.5) | median P_A margin |",
         "|---|---|---|---|---|---|---|---|---|"]
    k = 0
    for e in rep["pairs"]:
        for c in e["cells"]:
            k += 1
            L.append(f"| P{k} | {e['A']} vs {e['B']} | {c['model']} | {c['amount']:g} | {c['family']} | {c['n']} | "
                     f"{c['acc']:.2f} | {c['p_binom']:.3f} | {c['margin_med']:+.3f} |")
    L += ["", "| # | pair | real drawings | features | real CV acc | real held-out pairwise acc | grammar-v4 own drawings pairwise |",
          "|---|---|---|---|---|---|---|"]
    for i, e in enumerate(rep["pairs"], 1):
        L.append(f"| C{i} | {e['A']} vs {e['B']} | {e['n_real']} | {e['n_feat']} | {e['cv_acc']:.2f} | "
                 f"{e['cv_pairwise_real']:.2f} | {e['gen_pairwise']:.2f} |")
    L.append("")
    L.append("Restyle seconds per drawing (median): " + ", ".join(f"{k} {v:.2f}" for k, v in rep["time_med"].items()))
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# rendering + sheets
# ---------------------------------------------------------------------------

def render_cell(d: Drawing, size: int, lw: float = 1.4, frame: Drawing | None = None) -> np.ndarray:
    """Render into a size² image; `frame` (default d) fixes the bbox → the
    same structure lands on the same pixels in every hand."""
    from gesture import synth
    ref = frame if frame is not None else d
    pts = np.vstack([s.points for s in ref.strokes if len(s)])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    m = 0.05 * size
    sc = (size - 2 * m) / max(float(np.max(hi - lo)), 1e-9)
    off = m + 0.5 * ((size - 2 * m) - (hi - lo) * sc)
    ss = [Stroke((s.points - lo) * sc + off, closed=s.closed) for s in d.strokes if len(s) >= 2]
    return synth.render(Drawing(ss, size=(size, size)), line_width=lw, paper_noise=0.0,
                        blur_sigma=0.4, use_stroke_width=False)


def _label(img, text):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((6, 4), text, fill=60)
    return np.asarray(im)


def _cell_job(args):
    spec, size = args
    kind = spec["kind"]
    if kind == "structure":
        d = spec["drawing"]
        lab = spec["label"] + f" [{len(d.strokes)} lines]"
        return _label(render_cell(d, size), lab), {"label": lab}
    d = composite(spec["structure"], spec["hand"], np.random.default_rng(spec["seed"]), size=1200,
                  amount=spec["amount"], chain=spec.get("chain", False), model=spec.get("model", "grammar"),
                  structure_params=spec.get("params"), structure_hand=spec.get("structure_hand"),
                  at_crossings=spec.get("at_crossings", False), tremor=spec.get("tremor"),
                  max_retrace=spec.get("max_retrace"))
    c = d.meta["composite"]
    lab = spec["label"] + f" [{c['n_out']} path{'s' if c['n_out'] != 1 else ''}]"
    if c["chain_meta"]:
        lab += f" retrace {c['chain_meta']['retrace_R'] / max(c['chain_meta']['ink_R'], 1e-9):.0%}"
    if spec.get("big"):
        from PIL import Image
        Image.fromarray(render_cell(d, 1200, lw=2.0)).save(spec["big"], quality=90)
    return _label(render_cell(d, size), lab), {"label": lab, "sec": c["sec"], "n_out": c["n_out"],
                                               "chain": c["chain_meta"]}


def grid_sheet(rows, path: Path, size: int) -> list:
    from PIL import Image
    flat = [s for r in rows for s in r]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_cell_job, [(s, size) for s in flat], chunksize=1))
    ncol = max(len(r) for r in rows)
    sheet = np.full((size * len(rows), size * ncol), 255, np.uint8)
    k = 0
    for i, r in enumerate(rows):
        for j in range(len(r)):
            sheet[i * size:(i + 1) * size, j * size:(j + 1) * size] = res[k][0]
            sheet[i * size:(i + 1) * size, j * size] = 190
            k += 1
        sheet[i * size, :] = 190
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet).save(path, quality=90)
    print("wrote", path, flush=True)
    return [m for _i, m in res]


TREE_LEVELS = (("simple", {"depth": 3, "trunks": 1, "fill": 0.6}),
               ("medium", {"depth": 4, "trunks": 2, "fill": 0.8}),
               ("complex", {"depth": 5, "trunks": 3, "fill": 0.92}))


def cmd_sheets(a):
    OUT.mkdir(parents=True, exist_ok=True)
    sd = OUT / "sheets"
    sd.mkdir(parents=True, exist_ok=True)
    size, amt = a.size, a.amount
    log = {}
    which = set(a.which.split(","))
    # (i)/(ii) Oehlen-tree complexity × hands, chain off / on
    # chained: chain="before" — one continuous line through the skeleton, redrawn
    # by the hand (chain="after" retraces exactly and looks identical to "trees")
    for tag, chain in (("trees", False), ("trees-chained", "before")):
        if tag not in which:
            continue
        rows = []
        for lvl, prm in TREE_LEVELS:
            seed = 100 + len(rows)
            st = topology.generate_structure(None, np.random.default_rng(
                np.random.default_rng(seed).integers(0, 2 ** 31, 3)[0]), 1200, kind="oehlen_tree", **prm)
            r = [{"kind": "structure", "drawing": st, "label": f"tree {lvl} (skeleton)"}]
            r += [{"kind": "comp", "structure": "oehlen_tree", "params": prm, "hand": h, "seed": seed,
                   "amount": amt, "chain": chain, "label": f"{h} {amt:g}{' chained' if chain else ''}",
                   "big": str(sd / f"big-{tag}-{lvl}-{h}.jpg")} for h in ARTISTS]
            if chain:
                r.append({"kind": "comp", "structure": "oehlen_tree", "params": prm, "hand": "matisse",
                          "seed": seed, "amount": amt, "chain": chain, "max_retrace": 0.15,
                          "label": f"matisse {amt:g} chained, retrace<=15%"})
            rows.append(r)
        log[tag] = grid_sheet(rows, sd / f"composite-{tag}.jpg", size)
    # (iii) learned-topology composites per hand (own topology), 2 seeds; plus chained
    if "learned" in which:
        rows = []
        for h in ARTISTS:
            r = []
            for sdx in (1, 2):
                r.append({"kind": "comp", "structure": "learned", "hand": h, "seed": 200 + sdx, "amount": amt,
                          "label": f"{h} topology+hand s{sdx}"})
            r.append({"kind": "comp", "structure": "learned", "hand": h, "seed": 201, "amount": amt,
                      "chain": True, "at_crossings": True, "label": f"{h} s1 chained@X"})
            r.append({"kind": "comp", "structure": "learned", "hand": h, "seed": 201, "amount": amt,
                      "model": "lognormal", "label": f"{h} s1 lognormal hand"})
            rows.append(r)
        log["learned"] = grid_sheet(rows, sd / "composite-learned.jpg", size)
    # (iv) translation: a real drawing's long strokes → the other hands
    if "translation" in which:
        rows = []
        for src in a.translate.split(","):
            art, stem = src.split(":")
            st = real_structure(art, stem)
            r = [{"kind": "structure", "drawing": st, "label": f"real {art} {stem} (long strokes)"}]
            r += [{"kind": "comp", "structure": st, "hand": h, "seed": 300, "amount": amt,
                   "label": f"-> {h} {amt:g}", "big": str(sd / f"big-translation-{stem}-{h}.jpg")} for h in ARTISTS]
            r += [{"kind": "comp", "structure": st, "hand": h, "seed": 300, "amount": amt, "chain": "before",
                   "label": f"-> {h} chained skeleton"} for h in ARTISTS if h != art][:1]
            rows.append(r)
        log["translation"] = grid_sheet(rows, sd / "composite-translation.jpg", size)
    # model comparison: tree into each hand, grammar vs lognormal, single line
    if "models" in which:
        prm = TREE_LEVELS[1][1]
        rows = []
        for h in ARTISTS:
            rows.append([{"kind": "comp", "structure": "oehlen_tree", "params": prm, "hand": h, "seed": 101,
                          "amount": amt, "model": m, "chain": c,
                          "label": f"{h} {m}{' chained' if c else ''}"}
                         for m in ("grammar", "lognormal") for c in (False, True)])
        log["models"] = grid_sheet(rows, sd / "composite-models.jpg", size)
    old = json.loads((sd / "sheets_log.json").read_text()) if (sd / "sheets_log.json").exists() else {}
    old.update(log)
    (sd / "sheets_log.json").write_text(json.dumps(old, indent=1, default=float))


# ---------------------------------------------------------------------------
# judge pairs
# ---------------------------------------------------------------------------

SIDE, LW, CROP, SMOOTH = 1200, 3.0, 480, 5.0


def _fit(d: Drawing, frame: Drawing | None = None) -> Drawing:
    """blind_pairs.fit_canvas logic (copied: that file is read-only), with a
    shared frame so two hands of one structure land on the same pixels."""
    from gesture.curvature import resample, smooth
    ref = frame if frame is not None else d
    P = np.vstack([s.points for s in ref.strokes])
    lo, hi = P.min(0), P.max(0)
    k = (SIDE - 80) / max((hi - lo).max(), 1e-9)
    st = []
    for s in d.strokes:
        q = (s.points - lo) * k + 40
        if len(q) >= 3:
            r = resample(q, 1.0, closed=s.closed)
            if len(r) >= 5:
                q = smooth(r, SMOOTH, 1.0, closed=s.closed)
        L = float(np.sum(np.linalg.norm(np.diff(q, axis=0), axis=1))) if len(q) > 1 else 0.0
        chord = float(np.linalg.norm(q[-1] - q[0])) if len(q) > 1 else 0.0
        if L > 0.25 * SIDE and chord > 0.995 * L:
            continue                                   # plate marks
        st.append(Stroke(q, closed=s.closed))
    W, H = (np.ceil((hi - lo) * k) + 80).astype(int)
    return Drawing(st, size=(int(W), int(H)))


def _render(d: Drawing) -> np.ndarray:
    from gesture import synth
    return synth.render(d, line_width=LW, use_stroke_width=False, paper_noise=0.0, blur_sigma=0.6, seed=1)


def _crop_xy(imgs, rng, min_ink=0.012, tries=300):
    H = min(i.shape[0] for i in imgs)
    W = min(i.shape[1] for i in imgs)
    best = None
    for _ in range(tries):
        y = int(rng.integers(0, max(H - CROP, 1)))
        x = int(rng.integers(0, max(W - CROP, 1)))
        cs = [i[y:y + CROP, x:x + CROP] for i in imgs]
        if any(c.shape != (CROP, CROP) for c in cs):
            continue
        ink = min(float((c < 128).mean()) for c in cs)
        if ink >= min_ink:
            return cs
        if best is None or ink > best[0]:
            best = (ink, cs)
    return best[1] if best else None


def _pair_panel(a, b, refM, refH):
    from PIL import Image, ImageDraw
    rs_ = 300
    im = Image.new("L", (2 * CROP + 60, CROP + 60 + rs_ + 40), 255)
    dr = ImageDraw.Draw(im)
    im.paste(Image.fromarray(a), (20, 30))
    im.paste(Image.fromarray(b), (CROP + 40, 30))
    dr.text((20 + CROP // 2, 10), "A", fill=0)
    dr.text((CROP + 40 + CROP // 2, 10), "B", fill=0)
    dr.line([(CROP + 30, 30), (CROP + 30, CROP + 30)], fill=180)
    y0 = CROP + 70
    dr.line([(10, y0 - 15), (2 * CROP + 50, y0 - 15)], fill=200)
    for k, (ref, txt) in enumerate(((refM, "reference: real Matisse"), (refH, "reference: real Hokusai"))):
        x0 = 20 + k * (CROP + 20)
        im.paste(Image.fromarray(ref).resize((rs_, rs_), Image.LANCZOS), (x0, y0 + 20))
        dr.text((x0, y0), txt, fill=0)
    return im


def cmd_judge(a):
    from collections import Counter
    rng = np.random.default_rng(a.seed)
    out = OUTROOT / "blind_hand" / "pairs"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.png"):
        f.unlink()
    reals = {}
    for art in ("matisse", "hokusai"):
        imgs = []
        for p in sorted((EXTRACT / art).glob("*.json")):
            ld = gm.long_drawing(Drawing.load(p))
            if len(ld.strokes) >= 3:
                imgs.append(_render(_fit(ld)))
        reals[art] = imgs
    print("real renders", {k: len(v) for k, v in reals.items()}, flush=True)

    def real_crop(art, avoid=()):
        imgs = reals[art]
        j = int(rng.choice([i for i in range(len(imgs)) if i not in avoid] or range(len(imgs))))
        return _crop_xy([imgs[j]], rng)[0], j

    # composites: structure → Matisse and Hokusai (and Matisse twice for calib_neg)
    specs = []
    for i in range(a.n_test + a.n_neg):
        kind = "oehlen_tree" if i % 2 == 0 else "learned"
        sh = ("matisse", "hokusai", "ingres")[i % 3]
        st = structure_of(kind, sh, np.random.default_rng([41, i]), 1200,
                          TREE_LEVELS[i % 3][1] if kind == "oehlen_tree" else None)
        specs.append((i, kind, sh, st))
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_judge_job, [(i, st, a.amount, i >= a.n_test) for i, _k, _s, st in specs]))
    jobs = []
    for (i, kind, sh, st), (imgA, imgB) in zip(specs, res):
        cs = _crop_xy([imgA, imgB], rng)
        if cs is None:
            continue
        cond = "test" if i < a.n_test else "calib_neg"
        refM, jm = real_crop("matisse")
        refH, _ = real_crop("hokusai")
        jobs.append((cond, f"{kind}:{sh}", cs[0], cs[1], refM, refH))
    for i in range(a.n_pos):
        m, jm = real_crop("matisse")
        h, jh = real_crop("hokusai")
        refM, _ = real_crop("matisse", avoid=(jm,))
        refH, _ = real_crop("hokusai", avoid=(jh,))
        jobs.append(("calib_pos", "real", m, h, refM, refH))
    order = rng.permutation(len(jobs))
    key = {}
    for n, j in enumerate(order, 1):
        cond, what, m, other, refM, refH = jobs[j]
        m_left = bool(rng.integers(2))
        img = _pair_panel(m, other, refM, refH) if m_left else _pair_panel(other, m, refM, refH)
        name = f"pair_{n:03d}.png"
        img.save(out / name)
        ans = ("A" if m_left else "B") if cond != "calib_neg" else "none (both Matisse)"
        key[name] = {"condition": cond, "structure": what, "matisse": ans,
                     "other": "hokusai" if cond != "calib_neg" else "matisse (other seed)"}
    Path(a.key).write_text(json.dumps(key, indent=1))
    print(len(key), "pairs ->", out, "| key ->", a.key, "|", dict(Counter(v["condition"] for v in key.values())))


def _judge_job(args):
    i, st, amount, neg = args
    R = st.ref_length()
    gM = grammar("matisse")
    oM = rs.restyle_drawing(st, gM, amount=amount, seed=1000 + i, source="trace", ref_length=R)
    oB = rs.restyle_drawing(st, gM if neg else grammar("hokusai"), amount=amount,
                            seed=(2000 + i) if neg else (1000 + i), source="trace", ref_length=R)
    return _render(_fit(oM, st)), _render(_fit(oB, st))


# ---------------------------------------------------------------------------
# bench
# ---------------------------------------------------------------------------

def cmd_bench(a):
    rows = []
    for kind, prm in (("oehlen_tree", TREE_LEVELS[0][1]), ("oehlen_tree", TREE_LEVELS[1][1]),
                      ("oehlen_tree", TREE_LEVELS[2][1]), ("learned", None)):
        for model in ("grammar", "lognormal"):
            for chain in (False, True):
                for h in ARTISTS:
                    d = composite(kind, h, np.random.default_rng(7), amount=a.amount, chain=chain, model=model,
                                  structure_params=prm)
                    c = d.meta["composite"]
                    rows.append({"kind": kind, "params": prm, "model": model, "chained": chain, "hand": h,
                                 "n_structure": c["n_structure"], "n_out": c["n_out"], **c["sec"],
                                 "retrace": (c["chain_meta"] or {}).get("retrace_R", 0.0) /
                                 max((c["chain_meta"] or {}).get("ink_R", 1.0), 1e-9)})
                    print(rows[-1], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bench.json").write_text(json.dumps(rows, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("pairwise")
    q.add_argument("--n-tree", type=int, default=15)
    q.add_argument("--n-learned", type=int, default=15)
    q.add_argument("--amounts", default="0.5,0.8")
    q.add_argument("--models", default="grammar")
    q.add_argument("--n-gen", type=int, default=8)
    q.add_argument("--seed", type=int, default=1)
    s = sp.add_parser("sheets")
    s.add_argument("--size", type=int, default=400)
    s.add_argument("--amount", type=float, default=0.7)
    s.add_argument("--which", default="trees,trees-chained,learned,translation,models")
    s.add_argument("--translate", default="matisse:KKS1971-302,matisse:KKS13418_2,hokusai:57263")
    j = sp.add_parser("judge")
    j.add_argument("--n-test", type=int, default=30)
    j.add_argument("--n-neg", type=int, default=10)
    j.add_argument("--n-pos", type=int, default=10)
    j.add_argument("--amount", type=float, default=0.8)
    j.add_argument("--seed", type=int, default=5)
    j.add_argument("--key", default="/tmp/gesture_hand_key.json")
    b = sp.add_parser("bench")
    b.add_argument("--amount", type=float, default=0.7)
    a = p.parse_args(argv)
    {"pairwise": cmd_pairwise, "sheets": cmd_sheets, "judge": cmd_judge, "bench": cmd_bench}[a.cmd](a)


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    main()
