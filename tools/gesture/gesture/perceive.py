"""Perceived lines: merge extracted fragments into the lines an observer sees.

    perceive(drawing, **params) -> Drawing

The extractor (`extract.py`) cuts a drawn line wherever the skeleton graph
has a junction it cannot pair straight (turn > 45°), wherever the ink
breaks for more than 3 w or turns more than 25° across a break, and it
leaves the fragments of a figure's contour as separate strokes. Learning a
hand from those fragments learns a hand of fragments (grammar v4: generated
len_q10 0.66–0.85 × real, corners in excess). This module rebuilds the line
as drawn, from the fragments only (no raster):

**Candidates are end-to-end only.** Every pair of open ends within
`gap_w` line widths is a candidate. An end on another line's *interior*
(a T) has no end partner there, so a T stem is never merged into its host
by construction; a host that the extractor split at the T (three ends at
one junction) is resolved by good continuation, and a near-tie is left
alone (see ambiguity).

**Decisions** (w = the larger of the two strokes' median widths, ≥ 1 px;
end tangents are chords over the last `span_w` widths, outward):

- ``join`` — the ends touch (gap ≤ `touch_w`·w): accepted when the
  deflection (angle between A's outward tangent and B's inward tangent;
  0 = straight on, π = cusp) ≤ `join_deg`. A raster cannot tell a V
  corner of one stroke from two strokes meeting, and the extractor already
  returns a V with no third branch as one stroke; this does the same when a
  third branch made it stop.
- ``near`` / ``gap`` — the ends are apart: both must AIM across the gap
  (angle between each end tangent and the gap direction ≤ an aim limit
  that shrinks linearly from `aim_deg` at touch to `aim_far_deg` at
  `gap_w`), the total turn across the gap ≤ `defl_deg`, and the gap ≤
  `gap_len_frac` × the shorter stroke (a fragment's tangent cannot carry a
  gap longer than itself). Gaps ≤ `near_w`·w are reported as ``near``
  (aimed near-meetings), longer ones as ``gap`` (faint-ink breaks). A
  laterally offset pair — parallel neighbours, a staggered double contour
  — fails the aim test however close it is.
- ``cross`` — a ``near``/``gap`` merge whose bridge crosses another line:
  the extractor failed to pair an X and both halves stopped on the
  crossing line. Reported separately; same acceptance rule.
- ``close`` — a chain's two free ends meet the rule: the chain becomes a
  closed stroke.

**Cost and matching.** cost = turn/limit terms + gap/`gap_w` (each in
[0, 1] when acceptable). Candidates are taken greedily by cost, each end at
most once. **Ambiguity:** a candidate is skipped when either of its ends
has another acceptable, still-free partner whose cost is within
`amb_ratio` × its own — a symmetric Y or a three-way tie stays unmerged.

**Geometry.** A ⊕ bridge ⊕ B, the bridge a cubic Hermite from A's end
(tangent = A's outward direction) to B's end (tangent = B's inward
direction), sampled at ~1 px, widths interpolated. Open strokes start at
their left-most end (ties: top-most), as `extract` does; stroke order is by
start point (y, x).

**Provenance** (stroke meta): ``fragments`` = [[input index, reversed], …]
in order along the line, ``joins`` = [{kind, gap_w, defl, aim}], one per
junction between consecutive fragments (plus the closure),
``bridges`` = [[i0, i1], …] point-index ranges that are synthetic
bridge points. Drawing meta ``perceive`` = params + merge counts.

Pure (inputs never mutated) and deterministic (no randomness; ties broken
by index).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace

import numpy as np
from scipy.spatial import cKDTree

from .core import Drawing, Stroke
from .curvature import resample

__all__ = ["PerceiveParams", "perceive", "merge_candidates", "MERGE_KINDS"]

MERGE_KINDS = ("join", "near", "gap", "cross", "close")


@dataclass(frozen=True)
class PerceiveParams:
    touch_w: float = 1.5        # ends this close (· w) touch: a join, judged on deflection only
    join_deg: float = 75.0      # max deflection of a touching join (0 = straight on)
    gap_w: float = 12.0         # max gap (· w) for any merge
    near_w: float = 4.0         # gaps up to this are "near" (aimed near-meeting), longer "gap"
    aim_deg: float = 35.0       # max angle end tangent ↔ gap direction, at touch_w ...
    aim_far_deg: float = 12.0   # ... shrinking linearly to this at gap_w
    defl_deg: float = 45.0      # max total turn across a non-touching gap
    gap_len_frac: float = 1.0   # gap ≤ this × the shorter stroke's length
    span_w: float = 4.0         # end-tangent chord length (· w, ≥ 6 px)
    amb_ratio: float = 1.3      # skip when a rival partner is within this × cost
    cross_w: float = 0.6        # bridge within this (· w) of another line = crosses it
    busy_join_deg: float = 35.0 # a touching join at a vertex (a third line's end or interior
                                #   within touch): max deflection
    allow_close: bool = True

    def resolved(self, **kw) -> "PerceiveParams":
        bad = set(kw) - {f.name for f in fields(self)}
        if bad:
            raise TypeError(f"unknown perceive parameter(s): {sorted(bad)}")
        return replace(self, **kw)


def _arclen(p: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def _width(st: Stroke, fallback: float) -> float:
    if st.width is not None and len(st.width):
        return max(float(np.median(st.width)), 1.0)
    return max(fallback, 1.0)


def _drawing_width(d: Drawing) -> float:
    ws = [float(np.median(s.width)) for s in d.strokes if s.width is not None and len(s.width)]
    if ws:
        return float(np.median(ws))
    w = d.meta.get("line_width_px")
    return float(w) if w else max(0.0025 * d.ref_length(), 1.0)


def _end_dir(p: np.ndarray, s: np.ndarray, at_start: bool, span: float) -> np.ndarray:
    """Outward unit tangent at one end: chord from arc distance `span` in to the end."""
    if at_start:
        k = min(max(int(np.searchsorted(s, span)), 1), len(p) - 1)
        v = p[0] - p[k]
    else:
        k = max(min(int(np.searchsorted(s, s[-1] - span)), len(p) - 2), 0)
        v = p[-1] - p[k]
    n = np.linalg.norm(v)
    return v / n if n > 0 else np.array([1.0, 0.0])


def _ang(a: np.ndarray, b: np.ndarray) -> float:
    """Unsigned angle between unit vectors."""
    return float(np.arccos(np.clip(np.dot(a, b), -1.0, 1.0)))


@dataclass
class _End:
    stroke: int
    at_start: bool
    p: np.ndarray
    d: np.ndarray       # outward tangent
    w: float
    L: float


def _ends(d: Drawing, p: PerceiveParams) -> list[_End]:
    w0 = _drawing_width(d)
    out = []
    for i, st in enumerate(d.strokes):
        if st.closed or len(st) < 2:
            continue
        q = st.points
        s = _arclen(q)
        if s[-1] <= 0:
            continue
        w = _width(st, w0)
        span = min(max(p.span_w * w, 6.0), 0.5 * s[-1])
        for at_start in (True, False):
            out.append(_End(i, at_start, q[0] if at_start else q[-1], _end_dir(q, s, at_start, span), w, s[-1]))
    return out


def _judge(a: _End, b: _End, p: PerceiveParams) -> dict | None:
    """Acceptability of merging end a → end b; None if rejected."""
    w = max(a.w, b.w)
    v = b.p - a.p
    g = float(np.linalg.norm(v))
    defl = _ang(a.d, -b.d)                      # turn from A's travel into B's travel
    if g <= p.touch_w * w:
        lim = np.radians(p.join_deg)
        if defl > lim:
            return None
        return {"kind": "join", "gap_w": g / w, "defl": defl, "aim": None,
                "cost": defl / lim + 0.25 * g / (p.gap_w * w)}
    if g > p.gap_w * w or g > p.gap_len_frac * min(a.L, b.L):
        return None
    u = v / g
    al, be = _ang(a.d, u), _ang(u, -b.d)
    f = (g / w - p.touch_w) / max(p.gap_w - p.touch_w, 1e-9)
    aim_lim = np.radians(p.aim_deg + (p.aim_far_deg - p.aim_deg) * f)
    dlim = np.radians(p.defl_deg)
    if al > aim_lim or be > aim_lim or defl > dlim:
        return None
    kind = "near" if g <= p.near_w * w else "gap"
    cost = 0.5 * (al + be) / aim_lim + defl / dlim + g / (p.gap_w * w)
    return {"kind": kind, "gap_w": g / w, "defl": defl, "aim": [al, be], "cost": cost / 2.5}


def _ink_index(S: list[Stroke]):
    """Strokes resampled at 1 px: (KD-tree, owner, distance to own nearest end)."""
    pts, own, dend = [], [], []
    for i, st in enumerate(S):
        if len(st) >= 2:
            q = resample(st.points, 1.0, closed=st.closed)
            s = _arclen(q)
            pts.append(q)
            own.append(np.full(len(q), i))
            dend.append(np.full(len(q), np.inf) if st.closed else np.minimum(s, s[-1] - s))
    if not pts:
        return None, np.zeros(0, int), np.zeros(0)
    return cKDTree(np.vstack(pts)), np.concatenate(own), np.concatenate(dend)


def _busy(pt, tree, own, dend, skip, r) -> bool:
    """Is there a third line's INTERIOR within r of pt (a T location)?"""
    if tree is None:
        return False
    for j in tree.query_ball_point(pt, r):
        if own[j] not in skip and dend[j] > 2 * r:
            return True
    return False


def merge_candidates(drawing: Drawing, **params) -> tuple[list[_End], list[tuple[float, int, int, dict]]]:
    """All acceptable end pairs (cost, end a, end b, decision), sorted."""
    p = PerceiveParams().resolved(**params)
    ends = _ends(drawing, p)
    if len(ends) < 2:
        return ends, []
    P = np.array([e.p for e in ends])
    wmax = max(e.w for e in ends)
    tree = cKDTree(P)
    itree, iown, idend = _ink_index(drawing.strokes)
    cands = []
    for a, b in sorted(tree.query_pairs(p.gap_w * wmax)):
        ea, eb = ends[a], ends[b]
        if ea.stroke == eb.stroke and not p.allow_close:
            continue
        if ea.stroke == eb.stroke and ea.L < 3 * p.gap_w * max(ea.w, 1.0):
            continue          # a short stroke closing on itself is a blob, not a form
        r = _judge(ea, eb, p)
        if r is not None and r["kind"] == "join" and r["defl"] > np.radians(p.busy_join_deg):
            wj = max(ea.w, eb.w)
            mid = 0.5 * (ea.p + eb.p)
            third_end = any(k not in (a, b) and ends[k].stroke not in (ea.stroke, eb.stroke)
                            for k in tree.query_ball_point(mid, 2 * p.touch_w * wj))
            if third_end or _busy(mid, itree, iown, idend, {ea.stroke, eb.stroke}, p.touch_w * wj):
                r = None          # a vertex of three lines: good continuation only, no corner
        if r is not None:
            cands.append((r["cost"], a, b, r))
    cands.sort(key=lambda c: (c[0], c[1], c[2]))
    return ends, cands


def _hermite(p0, t0, p1, t1, n):
    """Cubic Hermite from p0 (unit tangent t0) to p1 (unit tangent t1), n interior points."""
    g = float(np.linalg.norm(p1 - p0))
    t = np.linspace(0, 1, n + 2)[1:-1, None]
    h00, h10 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t
    h01, h11 = -2 * t**3 + 3 * t**2, t**3 - t**2
    return h00 * p0 + h10 * g * t0 + h01 * p1 + h11 * g * t1


def _crosses(p0, p1, others_tree, others_own, skip, tol) -> bool:
    if others_tree is None:
        return False
    g = float(np.linalg.norm(p1 - p0))
    n = max(int(g), 2)
    t = np.linspace(0.15, 0.85, n)[:, None]
    seg = p0 + t * (p1 - p0)
    for lst in others_tree.query_ball_point(seg, tol):
        if any(others_own[j] not in skip for j in lst):
            return True
    return False


def _canonical(xy: np.ndarray, w: np.ndarray | None, closed: bool):
    """Open: start at the left-most end (ties top-most). Closed: unchanged."""
    if closed or len(xy) < 2:
        return xy, w, False
    a, b = xy[0], xy[-1]
    if (b[0], b[1]) < (a[0], a[1]):
        return xy[::-1].copy(), None if w is None else w[::-1].copy(), True
    return xy, w, False


def perceive(drawing: Drawing, **params) -> Drawing:
    """Merge fragments into perceived lines. See module docstring."""
    p = PerceiveParams().resolved(**params)
    S = drawing.strokes
    ends, cands = merge_candidates(drawing, **asdict(p))
    w0 = _drawing_width(drawing)
    tree, own_all, _dend = _ink_index(S)    # for crossing detection

    # -- greedy matching with an ambiguity guard -------------------------------
    by_end: dict[int, list[tuple[float, int]]] = {}
    for c, a, b, _r in cands:
        by_end.setdefault(a, []).append((c, b))
        by_end.setdefault(b, []).append((c, a))
    parent = list(range(len(S)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    used: set[int] = set()
    link: dict[int, tuple[int, dict]] = {}     # end index → (partner end index, decision)
    closures: dict[int, dict] = {}              # root stroke → decision (filled after)
    skipped_amb = 0
    for c, a, b, r in cands:
        if a in used or b in used:
            continue
        rival = False
        for e, other in ((a, b), (b, a)):
            for c2, x in by_end.get(e, []):
                if x != other and x not in used and c2 <= p.amb_ratio * c:
                    rival = True
                    break
            if rival:
                break
        if rival:
            skipped_amb += 1
            continue
        sa, sb = ends[a].stroke, ends[b].stroke
        r = dict(r)
        if find(sa) == find(sb):
            if not p.allow_close:
                continue
            r["kind"] = "close"
        elif r["kind"] in ("near", "gap") and _crosses(ends[a].p, ends[b].p, tree, own_all, {sa, sb},
                                                       p.cross_w * max(ends[a].w, ends[b].w)):
            r["kind"] = "cross"
        used.add(a)
        used.add(b)
        link[a] = (b, r)
        link[b] = (a, r)
        if r["kind"] != "close":
            parent[find(sa)] = find(sb)

    # end index of (stroke, at_start)
    eidx = {(e.stroke, e.at_start): k for k, e in enumerate(ends)}

    # -- assemble chains -------------------------------------------------------
    out: list[Stroke] = []
    counts = {k: 0 for k in MERGE_KINDS}
    done: set[int] = set()
    for i in range(len(S)):
        if i in done:
            continue
        st = S[i]
        if st.closed or (i, True) not in eidx:
            done.add(i)
            meta = dict(st.meta)
            meta.update(fragments=[[i, False]], joins=[], bridges=[])
            out.append(Stroke(st.points.copy(), None if st.width is None else st.width.copy(),
                              closed=st.closed, meta=meta))
            continue
        # walk to a free end of i's chain (or detect a cycle)
        cur, at_start = i, True
        seen = {i}
        cyclic = False
        while True:
            k = eidx[(cur, at_start)]
            if k not in link:
                break
            j_end, _r = link[k]
            nxt = ends[j_end].stroke
            if nxt in seen:
                cyclic = True
                break
            seen.add(nxt)
            cur, at_start = nxt, not ends[j_end].at_start
        # traverse from (cur, at_start): that end is the chain's start
        frags, joins, bridges = [], [], []
        P_parts, W_parts = [], []
        n_pts = 0
        entry = (cur, at_start)
        closing = None
        while True:
            k_s, from_start = entry
            done.add(k_s)
            F = S[k_s]
            q = F.points if from_start else F.points[::-1]
            wq = None if F.width is None else (F.width if from_start else F.width[::-1])
            frags.append([k_s, not from_start])
            if P_parts:
                prev_end = eidx[(frags[-2][0], frags[-2][1])]   # previous fragment's far end
                ea, eb = ends[prev_end], ends[eidx[(k_s, from_start)]]
                g = float(np.linalg.norm(eb.p - ea.p))
                nb = max(int(np.ceil(g)) - 1, 0)
                if nb > 0:
                    br = _hermite(ea.p, ea.d, eb.p, -eb.d, nb)
                    bridges.append([n_pts, n_pts + nb])
                    P_parts.append(br)
                    w_prev = W_parts[-1][-1] if len(W_parts[-1]) else ea.w
                    w_next = wq[0] if wq is not None and len(wq) else eb.w
                    W_parts.append(np.linspace(w_prev, w_next, nb + 2)[1:-1])
                    n_pts += nb
                elif np.allclose(q[0], P_parts[-1][-1]):
                    q = q[1:]
                    wq = None if wq is None else wq[1:]
            P_parts.append(q)
            W_parts.append(wq if wq is not None else np.full(len(q), _width(F, w0)))
            n_pts += len(q)
            far = eidx[(k_s, not from_start)]
            if far not in link:
                break
            j_end, r = link[far]
            nxt = ends[j_end].stroke
            if nxt == frags[0][0] and ends[j_end].at_start == (not frags[0][1]):
                closing = r
                break
            if nxt in done:
                break
            joins.append({k: (round(v, 4) if isinstance(v, float) else
                              ([round(x, 4) for x in v] if isinstance(v, list) else v))
                          for k, v in r.items() if k != "cost"})
            counts[r["kind"]] += 1
            entry = (nxt, ends[j_end].at_start)
        xy = np.vstack(P_parts)
        wv = np.concatenate(W_parts)
        closed = closing is not None
        if closed:
            counts[closing["kind"]] += 1
            joins.append({"kind": closing["kind"], "gap_w": round(closing["gap_w"], 4),
                          "defl": round(closing["defl"], 4), "closes": True})
            if np.allclose(xy[0], xy[-1]):
                xy, wv = xy[:-1], wv[:-1]
        if len(frags) == 1:
            meta = dict(S[frags[0][0]].meta)
        else:
            meta = {"median_width": round(float(np.median(wv)), 3), "min_width": round(float(wv.min()), 3)}
        rev = False
        if len(frags) > 1 and not closed:
            xy, wv, rev = _canonical(xy, wv, closed)
        if rev:
            n = len(xy)
            frags = [[f, not r_] for f, r_ in frags[::-1]]
            joins = joins[::-1]
            bridges = [[n - b1, n - b0] for b0, b1 in bridges[::-1]]
        if not any(S[f].width is not None for f, _ in frags):
            wv = None
        meta.update(fragments=frags, joins=joins, bridges=bridges)
        out.append(Stroke(xy, wv, closed=closed, meta=meta))
    out.sort(key=lambda s: (round(float(s.points[0, 1]), 3), round(float(s.points[0, 0]), 3), len(s)))
    meta = dict(drawing.meta)
    meta["perceive"] = {"params": asdict(p), "counts": counts, "n_in": len(S), "n_out": len(out),
                        "skipped_ambiguous": skipped_amb, "candidates": len(cands)}
    return Drawing(out, source=drawing.source, size=drawing.size, meta=meta)
