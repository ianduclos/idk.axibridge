"""Plotter path ordering: fewer pen-up metres and fewer lifts, same ink.

results/pathorder-2026-10-16.md. Used by experiments/regime_compose.py
(`order`, `polish`).

    order_paths(paths, groups=None, phases=None, layers=None, *, home=(0, 0),
                join_tol=0.0, chain_join_tol=0.0) -> Plan

Pipeline per layer (layers never mix: one pen each, each pass starts and
ends at home):

1. **Atoms.** A path with no group is a free atom: an open path may be drawn
   either way round, a closed ring (first == last) may start anywhere on
   itself (its seam is rotated). Paths that share a group id AND a phase form
   a **chain** atom: their order is kept exactly as given (a mass's concentric
   insets, outside-in), each element may still be reversed or re-seamed, and
   the chain as a whole is never reversed.
2. **Phases** run in ascending order (default: one phase). regime_compose
   draws lines, outlines and signs in phase 0 and mass fill in phase 1.
3. **Greedy nearest neighbour** from home over every legal entry point
   (both ends of an open path, every vertex of a ring), KD-tree backed.
4. **Improvement**: 2-opt (segment reversal, only across reversible atoms)
   and Or-opt (move a run of 1-3 atoms, optionally reversed) inside a phase,
   then a monotone **re-seam** sweep that re-picks each atom's orientation /
   ring seam / chain realisation against both neighbours. Repeated until no
   gain.
5. **Joining** (optional): consecutive paths whose pen-up gap is <= join_tol
   become one pen-down path (the gap is inked: keep it under a pen width).
   chain_join_tol applies only between consecutive elements of one chain
   (inside one mass), so open fill arcs are linked into one inked run.
6. **Guarantee**: if the result has more pen-up travel than the input order
   it is discarded and the input order is returned.

`estimate()` is a port of axibridge/estimate.py's model (trapezoidal
profiles, junction speed limits, servo swing times; plan_job's travel and
lift accounting) with the native backend's saved parameters as defaults; the
research venv has no pydantic, so the module cannot be imported here.
regime_compose cross-checks the port against the real module.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------
# basics
# ---------------------------------------------------------------------------


def is_closed(p: np.ndarray, tol: float = 1e-6) -> bool:
    return len(p) > 3 and float(np.linalg.norm(p[0] - p[-1])) <= tol


def plen(p: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1))) if len(p) > 1 else 0.0


def travel(paths, home=(0.0, 0.0), return_home: bool = True) -> float:
    """Pen-up distance home → paths in order → home (the estimator's model)."""
    pos = np.asarray(home, float)
    up = 0.0
    for p in paths:
        up += float(np.linalg.norm(p[0] - pos))
        pos = p[-1]
    if return_home and len(paths):
        up += float(np.linalg.norm(pos - np.asarray(home, float)))
    return up


def stats(paths, home=(0.0, 0.0)) -> dict:
    return {"paths": len(paths), "lifts": len(paths), "pen_down_mm": round(sum(plen(p) for p in paths), 1),
            "pen_up_mm": round(travel(paths, home), 1), "points": int(sum(len(p) for p in paths))}


def _roll_ring(p: np.ndarray, k: int) -> np.ndarray:
    """Closed ring (first == last) re-seamed to start at vertex k."""
    if k == 0:
        return p
    r = p[:-1]
    r = np.vstack([r[k:], r[:k]])
    return np.vstack([r, r[:1]])


def _best_seam(p: np.ndarray, a: np.ndarray, b: np.ndarray | None) -> int:
    r = p[:-1]
    c = np.linalg.norm(r - a, axis=1)
    if b is not None:
        c = c + np.linalg.norm(r - b, axis=1)
    return int(np.argmin(c))


# ---------------------------------------------------------------------------
# atoms
# ---------------------------------------------------------------------------


@dataclass
class _Atom:
    idx: list[int]                 # input indices (chain order)
    elems: list[np.ndarray]        # the paths themselves
    closed: list[bool]
    phase: int
    chain: bool
    # realisation
    pts: list[np.ndarray] = field(default_factory=list)     # oriented elements
    rev: list[bool] = field(default_factory=list)
    s: np.ndarray = None
    e: np.ndarray = None

    @property
    def reversible(self) -> bool:
        return not self.chain

    def internal(self) -> float:
        return sum(float(np.linalg.norm(a[-1] - b[0])) for a, b in zip(self.pts, self.pts[1:]))


def _orient(p: np.ndarray, closed: bool, a: np.ndarray, b: np.ndarray | None):
    """Element `p` oriented / re-seamed to start near a (and end near b)."""
    if closed:
        return _roll_ring(p, _best_seam(p, a, b)), False
    c_f = np.linalg.norm(p[0] - a) + (np.linalg.norm(p[-1] - b) if b is not None else 0.0)
    c_r = np.linalg.norm(p[-1] - a) + (np.linalg.norm(p[0] - b) if b is not None else 0.0)
    return (p[::-1].copy(), True) if c_r < c_f else (p, False)


def _realise_chain(at: _Atom, first: np.ndarray, first_rev: bool) -> None:
    pts, rev = [first], [first_rev]
    pos = first[-1]
    for p, c in zip(at.elems[1:], at.closed[1:]):
        q, r = _orient(p, c, pos, None)
        pts.append(q)
        rev.append(r)
        pos = q[-1]
    at.pts, at.rev = pts, rev
    at.s, at.e = pts[0][0], pts[-1][-1]


def _realise(at: _Atom, a: np.ndarray, b: np.ndarray | None, k_seams: int = 12) -> None:
    """Best realisation of an atom between predecessor exit a and successor
    entry b (b None = unknown): orientation, ring seam, or for a chain the
    first element's state (internal elements then follow greedily)."""
    if not at.chain:
        q, r = _orient(at.elems[0], at.closed[0], a, b)
        at.pts, at.rev = [q], [r]
        at.s, at.e = q[0], q[-1]
        return
    p0, c0 = at.elems[0], at.closed[0]
    if c0:
        r = p0[:-1]
        d = np.linalg.norm(r - a, axis=1)
        ks = np.argsort(d)[:k_seams]
        cands = [(_roll_ring(p0, int(k)), False) for k in ks]
    else:
        cands = [(p0, False), (p0[::-1].copy(), True)]
    best, bc = None, math.inf
    for q, rv in cands:
        _realise_chain(at, q, rv)
        c = float(np.linalg.norm(a - at.s)) + at.internal() + (float(np.linalg.norm(at.e - b)) if b is not None else 0.0)
        if c < bc - 1e-12:
            bc, best = c, (q, rv)
    _realise_chain(at, *best)


def nest_order(elems: list[np.ndarray], tol: float) -> tuple[list[int], list[int]]:
    """Outside-in order for one mass's concentric fill, given in depth order
    (regime.render's sweep: all insets at depth d, then d + 1). Each piece's
    parent is the nearest EARLIER piece within `tol` (the inset that
    encloses it, one pen out); the result is a depth-first walk of that
    nesting forest, nearest child first, so every inset is still drawn after
    the one around it but a long mass is filled end by end instead of the
    sweep's alternation between its two ends. Returns (order, parent) with
    parent[i] = -1 for a root."""
    from scipy.spatial import cKDTree
    n = len(elems)
    parent = [-1] * n
    trees = [cKDTree(e) for e in elems]
    for i in range(1, n):
        best, bj = tol, -1
        for j in range(i - 1, -1, -1):
            d, _ = trees[j].query(elems[i][:: max(1, len(elems[i]) // 32)], k=1)
            dm = float(np.min(d))
            if dm < best - 1e-12:
                best, bj = dm, j
        parent[i] = bj
    kids: dict[int, list[int]] = {}
    for i, pa in enumerate(parent):
        kids.setdefault(pa, []).append(i)
    order: list[int] = []
    pos = elems[0][0]

    def walk(i):
        nonlocal pos
        order.append(i)
        pos = elems[i][-1]
        rest = list(kids.get(i, []))
        while rest:
            k = min(rest, key=lambda c: float(np.min(np.linalg.norm(elems[c] - pos, axis=1))))
            rest.remove(k)
            walk(k)
    roots = list(kids.get(-1, []))
    while roots:
        r = min(roots, key=lambda c: float(np.min(np.linalg.norm(elems[c] - pos, axis=1))))
        roots.remove(r)
        walk(r)
    return order, parent


def _atoms(paths, groups, phases, nest_tol: float = 0.0) -> list[_Atom]:
    out, by_key = [], {}
    for i, p in enumerate(paths):
        g = groups[i] if groups is not None else None
        ph = int(phases[i]) if phases is not None else 0
        c = is_closed(p)
        if g is None:
            out.append(_Atom([i], [p], [c], ph, False))
            continue
        key = (g, ph)
        if key not in by_key:
            by_key[key] = _Atom([], [], [], ph, True)
            out.append(by_key[key])
        at = by_key[key]
        at.idx.append(i)
        at.elems.append(p)
        at.closed.append(c)
    for at in out:                       # a one-element chain is a free atom
        if at.chain and len(at.elems) == 1:
            at.chain = False
        if at.chain and nest_tol > 0:
            o, _ = nest_order(at.elems, nest_tol)
            at.idx = [at.idx[k] for k in o]
            at.elems = [at.elems[k] for k in o]
            at.closed = [at.closed[k] for k in o]
    return out


# ---------------------------------------------------------------------------
# construction and improvement
# ---------------------------------------------------------------------------


def _greedy(atoms: list[_Atom], home: np.ndarray) -> list[int]:
    from scipy.spatial import cKDTree
    order = []
    pos = home
    for ph in sorted({a.phase for a in atoms}):
        ids = [k for k, a in enumerate(atoms) if a.phase == ph]
        P, owner = [], []
        for k in ids:
            at = atoms[k]
            p, c = at.elems[0], at.closed[0]
            cand = p[:-1] if c else p[[0, -1]]
            P.append(cand)
            owner += [k] * len(cand)
        P = np.vstack(P)
        owner = np.asarray(owner)
        tree = cKDTree(P)
        left = set(ids)
        while left:
            kq = 8
            pick = None
            while pick is None:
                kk = min(kq, len(P))
                _, j = tree.query(pos, k=kk)
                j = np.atleast_1d(j)
                for jj in j:
                    if int(owner[jj]) in left:
                        pick = int(owner[jj])
                        break
                if pick is None:
                    if kk >= len(P):
                        pick = next(iter(left))
                    kq *= 4
            _realise(atoms[pick], pos, None)
            order.append(pick)
            left.discard(pick)
            pos = atoms[pick].e
    return order


def _se(atoms, tour, home):
    n = len(tour)
    S = np.empty((n + 2, 2))
    E = np.empty((n + 2, 2))
    S[0] = E[0] = home
    S[-1] = E[-1] = home
    for k, a in enumerate(tour):
        S[k + 1] = atoms[a].s
        E[k + 1] = atoms[a].e
    return S, E


def _cost(atoms, tour, home) -> float:
    S, E = _se(atoms, tour, home)
    return float(np.sum(np.linalg.norm(E[:-1] - S[1:], axis=1))) + sum(atoms[a].internal() for a in tour)


def _reverse_atom(at: _Atom) -> None:
    at.pts = [q[::-1].copy() for q in at.pts[::-1]]
    at.rev = [not r for r in at.rev[::-1]]
    at.s, at.e = at.pts[0][0], at.pts[-1][-1]


def _two_opt(atoms, tour, home, deadline) -> bool:
    n = len(tour)
    if n < 2:
        return False
    improved = False
    ph = np.array([-1] + [atoms[a].phase for a in tour] + [10 ** 9])
    rv = np.array([True] + [atoms[a].reversible for a in tour] + [True])
    for i in range(1, n + 1):
        if time.perf_counter() > deadline:
            break
        if not rv[i]:
            continue
        S, E = _se(atoms, tour, home)
        # j from i..jmax: same phase, all reversible
        j = i
        while j + 1 <= n and ph[j + 1] == ph[i] and rv[j + 1]:
            j += 1
        if j <= i:
            continue
        js = np.arange(i + 1, j + 1)
        old = np.linalg.norm(E[i - 1] - S[i]) + np.linalg.norm(E[js] - S[js + 1], axis=1)
        new = np.linalg.norm(E[i - 1] - E[js], axis=1) + np.linalg.norm(S[i] - S[js + 1], axis=1)
        d = new - old
        b = int(np.argmin(d))
        if d[b] < -1e-9:
            jj = int(js[b])
            seg = tour[i - 1:jj]
            for a in seg:
                _reverse_atom(atoms[a])
            tour[i - 1:jj] = seg[::-1]
            improved = True
    return improved


def _or_opt(atoms, tour, home, deadline, max_len: int = 3) -> bool:
    improved = False
    for L in range(1, max_len + 1):
        i = 1
        while i + L - 1 <= len(tour):
            if time.perf_counter() > deadline:
                return improved
            n = len(tour)
            ph = np.array([-1] + [atoms[a].phase for a in tour] + [10 ** 9])
            seg_ph = ph[i:i + L]
            if np.any(seg_ph != seg_ph[0]):
                i += 1
                continue
            b = seg_ph[0]
            S, E = _se(atoms, tour, home)
            gain = (np.linalg.norm(E[i - 1] - S[i]) + np.linalg.norm(E[i + L - 1] - S[i + L])
                    - np.linalg.norm(E[i - 1] - S[i + L]))
            g = np.arange(1, n + 2)                       # gap between positions g-1 and g
            ok = (ph[g - 1] <= b) & (ph[g] >= b) & ((g < i) | (g > i + L))
            if not np.any(ok):
                i += 1
                continue
            g = g[ok]
            base = np.linalg.norm(E[g - 1] - S[g], axis=1)
            ins_f = np.linalg.norm(E[g - 1] - S[i], axis=1) + np.linalg.norm(E[i + L - 1] - S[g], axis=1) - base
            best_f = int(np.argmin(ins_f))
            cand = [(float(ins_f[best_f]), int(g[best_f]), False)]
            if all(atoms[a].reversible for a in tour[i - 1:i - 1 + L]):
                ins_r = (np.linalg.norm(E[g - 1] - E[i + L - 1], axis=1) + np.linalg.norm(S[i] - S[g], axis=1)
                         - base)
                best_r = int(np.argmin(ins_r))
                cand.append((float(ins_r[best_r]), int(g[best_r]), True))
            c, gg, r = min(cand)
            if c - gain < -1e-9:
                seg = tour[i - 1:i - 1 + L]
                if r:
                    for a in seg:
                        _reverse_atom(atoms[a])
                    seg = seg[::-1]
                rest = tour[:i - 1] + tour[i - 1 + L:]
                pos = gg - 1 if gg < i else gg - 1 - L     # gap index in `rest`
                tour[:] = rest[:pos] + seg + rest[pos:]
                improved = True
            else:
                i += 1
    return improved


def _reseam(atoms, tour, home) -> None:
    """Monotone sweep: each atom re-realised against its current neighbours."""
    n = len(tour)
    for k in range(n):
        a = home if k == 0 else atoms[tour[k - 1]].e
        b = home if k == n - 1 else atoms[tour[k + 1]].s
        at = atoms[tour[k]]
        old = (at.pts, at.rev, at.s, at.e)
        c_old = float(np.linalg.norm(a - at.s) + np.linalg.norm(at.e - b)) + at.internal()
        _realise(at, a, b)
        c_new = float(np.linalg.norm(a - at.s) + np.linalg.norm(at.e - b)) + at.internal()
        if c_new > c_old + 1e-9:
            at.pts, at.rev, at.s, at.e = old


# ---------------------------------------------------------------------------
# public
# ---------------------------------------------------------------------------


@dataclass
class Plan:
    paths: list[np.ndarray]            # ordered, oriented, joined; all layers in layer order
    layers: list                       # layer of each output path
    source: list[list[tuple[int, bool]]]   # per output path: (input index, reversed) pieces
    before: dict
    after: dict
    meta: dict


def order_paths(paths, groups=None, phases=None, layers=None, *, home=(0.0, 0.0), join_tol: float = 0.0,
                chain_join_tol: float = 0.0, nest_tol: float = 0.0, improve: bool = True,
                time_budget_s: float = 20.0, rounds: int = 6) -> Plan:
    """Order, orient, re-seam and optionally join plotter polylines; see the
    module docstring. `groups[i]` None = free path; equal ids (within one
    phase) = chain kept in input order. Deterministic (no randomness)."""
    paths = [np.asarray(p, float) for p in paths]
    n = len(paths)
    home = np.asarray(home, float)
    lay = list(layers) if layers is not None else [0] * n
    lay_order = list(dict.fromkeys(lay))
    out_p, out_l, out_src = [], [], []
    before = {"paths": 0, "pen_up_mm": 0.0, "pen_down_mm": 0.0}
    after = {"paths": 0, "pen_up_mm": 0.0, "pen_down_mm": 0.0}
    t0 = time.perf_counter()
    meta = {"rounds": 0, "fallback": []}
    for L in lay_order:
        ids = [i for i in range(n) if lay[i] == L]
        sub = [paths[i] for i in ids]
        g = [groups[i] for i in ids] if groups is not None else None
        ph = [phases[i] for i in ids] if phases is not None else None
        atoms = _atoms(sub, g, ph, nest_tol)
        tour = _greedy(atoms, home)
        if improve and len(tour) > 1:
            deadline = time.perf_counter() + time_budget_s / max(len(lay_order), 1)
            best = _cost(atoms, tour, home)
            for _ in range(rounds):
                ch = _two_opt(atoms, tour, home, deadline)
                ch = _or_opt(atoms, tour, home, deadline) or ch
                _reseam(atoms, tour, home)
                c = _cost(atoms, tour, home)
                meta["rounds"] += 1
                if not ch and c >= best - 1e-9:
                    break
                best = min(best, c)
                if time.perf_counter() > deadline:
                    break
        # flatten, then join
        seq = []                                   # (points, [(idx, rev)], chain_id)
        for a in tour:
            at = atoms[a]
            for q, i, r in zip(at.pts, at.idx, at.rev):
                seq.append((q, [(ids[i], r)], a if at.chain else None))
        joined = []
        for q, src, cid in seq:
            if joined:
                pq, psrc, pcid = joined[-1]
                gap = float(np.linalg.norm(pq[-1] - q[0]))
                tol = max(join_tol, chain_join_tol if (cid is not None and cid == pcid) else 0.0)
                if tol > 0 and gap <= tol:
                    joined[-1] = (np.vstack([pq, q[1:]] if gap <= 1e-12 else [pq, q]), psrc + src, pcid)
                    continue
            joined.append((q, src, cid))
        res = [q for q, _, _ in joined]
        # guarantee: never more pen-up travel than the input order
        if travel(res, home) > travel(sub, home) + 1e-9:
            meta["fallback"].append(L)
            res, joined = sub, [(q, [(ids[k], False)], None) for k, q in enumerate(sub)]
        before["paths"] += len(sub)
        before["pen_up_mm"] += travel(sub, home)
        before["pen_down_mm"] += sum(plen(p) for p in sub)
        after["paths"] += len(res)
        after["pen_up_mm"] += travel(res, home)
        after["pen_down_mm"] += sum(plen(p) for p in res)
        out_p += res
        out_l += [L] * len(res)
        out_src += [s for _, s, _ in joined]
    for d in (before, after):
        d["lifts"] = d["paths"]
        d["pen_up_mm"] = round(d["pen_up_mm"], 1)
        d["pen_down_mm"] = round(d["pen_down_mm"], 1)
    meta["sec"] = round(time.perf_counter() - t0, 2)
    return Plan(out_p, out_l, out_src, before, after, meta)


def segments(paths, nd: int = 6) -> set:
    """Undirected segment set (rounded endpoints), for geometry checks."""
    out = set()
    for p in paths:
        q = np.round(np.asarray(p, float), nd)
        for a, b in zip(q[:-1], q[1:]):
            ta, tb = tuple(a), tuple(b)
            if ta != tb:
                out.add((ta, tb) if ta <= tb else (tb, ta))
    return out


# ---------------------------------------------------------------------------
# timing: a port of axibridge/estimate.py (plan_job) — keep in step with it
# ---------------------------------------------------------------------------

#: axibridge/estimate.py EstimatorConstants defaults (= ~/.axibridge settings)
CONSTS = {"max_speed_mm_s": 279.4, "max_accel_mm_s2": 4000.0, "pen_swing_s": 0.15}
#: the native backend's saved motion parameters (~/.axibridge/settings.json,
#: read 2026-10-16); cornering is not a native option: MotionParams default.
NATIVE = {"speed_pendown": 25.0, "speed_penup": 75.0, "accel": 100.0, "cornering": 10.0,
          "pen_pos_down": 20.0, "pen_pos_up": 60.0, "pen_rate_lower": 50.0, "pen_rate_raise": 75.0,
          "pen_delay_down": 0.0, "pen_delay_up": 0.0, "const_speed": False}


def _polyline_time(pts, v_max, a, cornering, const_speed) -> float:
    pts = [tuple(map(float, p)) for p in pts]
    segs = [math.dist(a_, b_) for a_, b_ in zip(pts, pts[1:])]
    segs = [s for s in segs if s > 1e-9]
    if not segs:
        return 0.0
    if const_speed:
        return sum(segs) / v_max
    n = len(segs)
    v_junc = [0.0] * (n + 1)
    for i in range(1, n):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        ux, uy = x1 - x0, y1 - y0
        wx, wy = x2 - x1, y2 - y1
        nu = math.hypot(ux, uy) or 1.0
        nw = math.hypot(wx, wy) or 1.0
        cos_t = max(-1.0, min(1.0, (ux * wx + uy * wy) / (nu * nw)))
        factor = (cos_t + 1.0) / 2.0
        v_junc[i] = v_max * (factor ** (1.0 / max(cornering / 25.0, 0.05)))
    v = [0.0] * (n + 1)
    for i in range(1, n + 1):
        v[i] = min(v_max if i < n else 0.0, v_junc[i] if i < n else 0.0)
        v[i] = min(v[i], math.sqrt(v[i - 1] ** 2 + 2 * a * segs[i - 1]))
    for i in range(n - 1, -1, -1):
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * a * segs[i]))
    t = 0.0
    for i, s in enumerate(segs):
        v0, v1 = v[i], v[i + 1]
        v_peak = math.sqrt(max((2 * a * s + v0 ** 2 + v1 ** 2) / 2.0, 0.0))
        v_peak = min(v_peak, v_max)
        t_acc = (v_peak - v0) / a
        t_dec = (v_peak - v1) / a
        d_acc = (v0 + v_peak) / 2.0 * t_acc
        d_dec = (v1 + v_peak) / 2.0 * t_dec
        d_cruise = max(s - d_acc - d_dec, 0.0)
        t += t_acc + t_dec + (d_cruise / v_peak if v_peak > 0 else 0.0)
    return t


def estimate(paths_mm, params: dict | None = None, consts: dict | None = None, home=(0.0, 0.0)) -> dict:
    """plan_job's totals for paths in mm (the same accounting: travel from
    home to each path start, pen lower + draw + raise per path, return home)."""
    p = {**NATIVE, **(params or {})}
    c = {**CONSTS, **(consts or {})}
    v_down = min(p["speed_pendown"], 110) / 100.0 * c["max_speed_mm_s"]
    v_up = min(p["speed_penup"], 110) / 100.0 * c["max_speed_mm_s"]
    a = p["accel"] / 100.0 * c["max_accel_mm_s2"]
    swing = abs(p["pen_pos_up"] - p["pen_pos_down"]) / 100.0
    t_lift = c["pen_swing_s"] * swing * (100.0 / p["pen_rate_raise"]) + max(p["pen_delay_up"], 0) / 1000.0
    t_lower = c["pen_swing_s"] * swing * (100.0 / p["pen_rate_lower"]) + max(p["pen_delay_down"], 0) / 1000.0
    pos = tuple(map(float, home))
    up_d = up_t = down_d = down_t = lift_t = 0.0
    for q in paths_mm:
        q0 = tuple(map(float, q[0]))
        d = math.dist(pos, q0)
        if d > 1e-9:
            up_d += d
            up_t += _polyline_time([pos, q0], v_up, a, p["cornering"], False)
        down_d += plen(q)
        down_t += _polyline_time(q, v_down, a, p["cornering"], p["const_speed"])
        lift_t += t_lower + t_lift
        pos = tuple(map(float, q[-1]))
    d = math.dist(pos, tuple(map(float, home)))
    if paths_mm and d > 1e-9:
        up_d += d
        up_t += _polyline_time([pos, tuple(map(float, home))], v_up, a, p["cornering"], False)
    tot = down_t + up_t + lift_t
    return {"lifts": len(paths_mm), "pen_down_mm": round(down_d, 1), "pen_up_mm": round(up_d, 1),
            "pen_down_s": round(down_t, 1), "travel_s": round(up_t, 1), "lift_s": round(lift_t, 1),
            "total_s": round(tot, 1), "total_min": round(tot / 60.0, 1)}
