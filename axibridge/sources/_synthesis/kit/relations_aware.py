# FROZEN from research commit 071aea1: tools/gesture/gesture/kit/relations_aware.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 16 thread A `aware`: awareness as composable relations (v2 score).

Ian on round 15: "not always make gaps for the lines to go through. when you
do it could also be fun to have them go above and below unpredictably"; on the
sympathy close-up: "very subtle but very very good. this is the type of
awareness i want".

- `crossing` (contact)  every crossing between src and dst gets its own
  outcome, drawn from weights: gap_under (the dst breaks: it passes under),
  gap_over (the src breaks), cross (both run through), stop (one line ends at
  the other: the one whose tail beyond the crossing is shorter, and only when
  no other crossing lies on that tail), sympathy (no gap: near the crossing
  the dst is carried a little along the src's course and takes on its
  wiggle). Crossings of the same two marks closer than `tangle` along the dst
  are one tangle with one outcome, and no gap may leave a piece shorter than
  `min_dash` (no dashed lines through a knot or a crowd). `streak` lets an outcome repeat before it changes, so a pair of
  layers shows a behaviour rather than noise. Gaps are sized in pen widths.
- `sympathy` (contact)  lcorp's `aware_marks` sympathy over any two layers:
  where the bending line runs over or along the other within `reach`, it
  takes on the other's own wiggle (its points minus their smoothing), faded
  by distance and smoothed so no kink appears. Who bends is a param (dst,
  src, the later layer, the shorter layer), not the zoom channel.

The helpers here (`_pool`, `_join_masks`, `_frame`, …) are shared with
`relations_aware_more.py`. Two marks that touch end to end (a listen line
continued in another pen: the bridge splits it into two layers) are one
line, not neighbours: samples near such a join are never heard.
"""
from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

from ._relations import RelOut, crossings, cut, relation
from .core import Mark, P

OUTCOMES = ("cross", "gap_over", "gap_under", "stop", "sympathy")      # drawn in this (sorted) order
STEP = 0.25            # mm, the hearing side's sampling
FINE = 0.5             # a bending mark coarser than this is resampled to it first
JOIN_TOL = 0.75        # mm: ends closer than this are one line continued


# ---------------------------------------------------------------------------
# shared geometry
# ---------------------------------------------------------------------------

def _frame(p: np.ndarray):
    """Unit tangents and left normals of a polyline."""
    d = np.gradient(p, axis=0) if len(p) > 1 else np.zeros_like(p)
    t = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    return t, np.column_stack([-t[:, 1], t[:, 0]])


def _lateral(p: np.ndarray, s: np.ndarray, sigma: float) -> np.ndarray:
    """A line's own wiggle: its points minus their `sigma`-mm smoothing."""
    if len(p) < 4:
        return np.zeros_like(p)
    stp = max(float(np.median(np.diff(s))), 1e-6)
    sm = np.column_stack([gaussian_filter1d(p[:, i], sigma / stp, mode="nearest") for i in (0, 1)])
    return p - sm


def _fine(m: Mark, step: float = FINE) -> Mark:
    """The mark, resampled when it is coarser than `step` (channels carried)."""
    if len(m) < 2:
        return m
    s = m.arclength()
    if s[-1] > 3 * step and float(np.max(np.diff(s))) > step * 1.01:
        return m.resampled(step)
    return m


def _ends(marks) -> np.ndarray:
    e = [m.points[[0, -1]] for m in marks if len(m) >= 2]
    return np.vstack(e) if e else np.zeros((0, 2))


def _join_mask(m: Mark, other_ends: np.ndarray, reach: float) -> np.ndarray:
    """Samples of m within `reach` (arc) of one of its ends that touches an end of another layer's
    mark: there the two are one line continued, not two lines meeting."""
    out = np.zeros(len(m), bool)
    if not len(other_ends) or len(m) < 2:
        return out
    s = m.arclength()
    for e, sel in ((m.points[0], s <= reach), (m.points[-1], s >= s[-1] - reach)):
        if float(np.min(np.linalg.norm(other_ends - e, axis=1))) < JOIN_TOL:
            out |= sel
    return out


class Pool(NamedTuple):
    """The hearing side, resampled: every sample with its mark, arc length, tangent, normal, wiggle."""
    pts: np.ndarray
    mark: np.ndarray
    s: np.ndarray
    tan: np.ndarray
    nrm: np.ndarray
    lat: np.ndarray
    tree: cKDTree | None
    step: float


def _pool(marks, *, other_ends=np.zeros((0, 2)), join: float = 4.0, sigma: float = 3.0,
          step: float = STEP) -> Pool:
    P_, M_, S_, T_, N_, L_ = [], [], [], [], [], []
    for i, m in enumerate(marks):
        if len(m) < 2 or m.length() <= 0:
            continue
        r = m.resampled(step) if m.length() > 3 * step else m
        p, s = r.points, r.arclength()
        t, n = _frame(p)
        keep = ~_join_mask(r, other_ends, join)
        lat = _lateral(p, s, sigma)
        P_.append(p[keep]); M_.append(np.full(int(keep.sum()), i)); S_.append(s[keep])
        T_.append(t[keep]); N_.append(n[keep]); L_.append(lat[keep])
    if not P_ or not sum(len(x) for x in P_):
        z = np.zeros((0, 2))
        return Pool(z, np.zeros(0, int), np.zeros(0), z, z, z, None, step)
    pts = np.vstack(P_)
    return Pool(pts, np.concatenate(M_), np.concatenate(S_), np.vstack(T_), np.vstack(N_), np.vstack(L_),
                cKDTree(pts), step)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[a, b) index runs where mask is True."""
    m = np.r_[False, np.asarray(mask, bool), False]
    d = np.diff(m.astype(int))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def _clip(p: np.ndarray, frame) -> np.ndarray:
    W, H = frame
    return np.clip(p, [0.5, 0.5], [W - 0.5, H - 0.5])


def _moved(m: Mark, disp_vec: np.ndarray, frame) -> Mark:
    return m.evolve(points=_clip(m.points + disp_vec, frame))


def _pieces(marks: list[Mark], min_piece: float) -> list[Mark]:
    """No stray marks: pieces left by a cut shorter than min_piece are dropped."""
    return [m for m in marks if len(m) >= 2 and m.length() >= min_piece]


def _who_bends(rctx, src, dst, bends: str) -> str:
    """'dst' or 'src' for a depth rule."""
    if bends in ("dst", "src"):
        return bends
    if bends == "later":
        order = list(rctx.ground)
        if rctx.src in order and rctx.dst in order:
            return "src" if order.index(rctx.src) > order.index(rctx.dst) else "dst"
        return "dst"
    ls = sum(m.length() for m in src)
    ld = sum(m.length() for m in dst)
    return "src" if ls < ld else "dst"


# ---------------------------------------------------------------------------
# sympathy
# ---------------------------------------------------------------------------

def sympathy_disp(m: Mark, H: Pool, *, reach: float, excl: np.ndarray | None = None) -> np.ndarray:
    """Per-sample normal displacement of m that takes on H's wiggle where m runs over or along H
    within `reach` (lcorp's rule: the H sample straight across, not the nearest; a raised-cosine
    falloff with the distance across). Unsmoothed, ungained."""
    p = m.points
    disp = np.zeros(len(p))
    if H.tree is None or len(p) < 6:
        return disp
    t, n = _frame(p)
    d0, _ = H.tree.query(p, distance_upper_bound=reach)
    cand = np.flatnonzero(np.isfinite(d0))
    if excl is not None:
        cand = cand[~excl[cand]]
    if not len(cand):
        return disp
    lists = H.tree.query_ball_point(p[cand], reach)
    for k, js in zip(cand.tolist(), lists):
        if not js:
            continue
        js = np.asarray(js, int)
        rel = H.pts[js] - p[k]
        along = np.abs(rel @ t[k])
        jj = int(np.argmin(along))
        if along[jj] > 2 * H.step:
            continue
        j = int(js[jj])
        across = abs(float(rel[jj] @ n[k]))
        w = 0.5 * (1 + math.cos(math.pi * min(across / reach, 1.0)))
        disp[k] = w * float(H.lat[j] @ n[k])
    return disp


@relation("sympathy", phase="contact", params=[
    P("reach", "float", 4.0, "how far across a line hears the other one, mm", min=0.5, max=20.0),
    P("gain", "float", 0.8, "how much of the other's wiggle is taken on (subtle by default)", min=0.0, max=3.0),
    P("sigma", "float", 3.0, "the wiggle's scale: the other line minus its smoothing at this many mm",
      min=0.5, max=20.0),
    P("bends", "choice", "later", "who bends: dst, src, the later-drawn layer, or the shorter layer",
      choices=("later", "dst", "src", "shorter")),
    P("smooth", "float", 0.8, "the twist arrives over this many mm (no kinks)", min=0.2, max=5.0),
    P("join", "float", 4.0, "a line continued in another layer is not heard this near the join, mm",
      min=0.0, max=20.0),
], doc="where one line runs over or along another it takes on the other's own wiggle, faded by distance "
       "(lcorp's sympathy between any two layers; depth is a param)")
def sympathy(rctx, src, dst, *, reach, gain, sigma, bends, smooth, join):
    who = _who_bends(rctx, src, dst, bends)
    bend, hear = (dst, src) if who == "dst" else (src, dst)
    if not bend or not hear:
        return RelOut()
    H = _pool(hear, other_ends=_ends(bend), join=join, sigma=sigma)
    if H.tree is None:
        return RelOut()
    hear_ends = _ends(hear)
    out, events = [], []
    for i, m0 in enumerate(bend):
        m = _fine(m0)
        if len(m) < 6:
            out.append(m0)
            continue
        excl = _join_mask(m, hear_ends, join)
        disp = sympathy_disp(m, H, reach=reach, excl=excl)
        if not np.any(disp):
            out.append(m0)
            continue
        s = m.arclength()
        stp = max(float(np.median(np.diff(s))), 1e-6)
        disp = gaussian_filter1d(disp, smooth / stp, mode="nearest") * gain
        if float(np.max(np.abs(disp))) < 0.02:
            out.append(m0)
            continue
        _, nrm = _frame(m.points)
        out.append(_moved(m, disp[:, None] * nrm, rctx.frame))
        for a, b in _runs(np.abs(disp) > 0.03):
            if s[b - 1] - s[a] < 0.5:
                continue
            mid = (a + b) // 2
            ev = {"outcome": "sympathy", "at": m.points[mid].tolist(), "bends": who,
                  "peak_mm": round(float(np.max(np.abs(disp[a:b]))), 3)}
            if who == "dst":
                ev.update({"s": [float(s[a]), float(s[b - 1])], "mark": i})
            else:
                ev.update({"s_src": [float(s[a]), float(s[b - 1])], "mark_src": i})
            events.append(ev)
    if not events:
        return RelOut()
    return RelOut(dst=out, events=events) if who == "dst" else RelOut(src=out, events=events)


# ---------------------------------------------------------------------------
# crossing
# ---------------------------------------------------------------------------

def _draw(weights: dict, u: float) -> str:
    """One outcome by a uniform draw u, over the outcomes in sorted order (deterministic)."""
    keys = [k for k in OUTCOMES if weights.get(k, 0) > 0]
    if not keys:
        return "cross"
    w = np.array([weights[k] for k in keys], float)
    c = np.cumsum(w / w.sum())
    return keys[min(int(np.searchsorted(c, u, side="right")), len(keys) - 1)]


def _bend(c, ms: Mark, s0, td, nrm, reach: float, lean_mm: float) -> np.ndarray:
    """The crossing-sympathy displacement of a dst sampled at s0 (tangents td, normals nrm): a
    raised-cosine window of half-length `reach` around the crossing, in which the dst is carried
    `lean_mm` along the src's course (its drawing direction) and takes on the src's own wiggle, read
    from the src sample as far along the src as the dst sample is from the crossing (scaled by how
    parallel the two run: across, the wiggle at the crossing; along, the wiggle beside)."""
    ss = ms.arclength()
    ts, _ = _frame(ms.points)
    tv = _interp_vec([c.s_src], ss, ts)[0]
    tv = tv / max(float(np.linalg.norm(tv)), 1e-9)
    t0 = _interp_vec([c.s_dst], s0, td)[0]
    cos = float(np.dot(tv, t0 / max(float(np.linalg.norm(t0)), 1e-9)))
    w = np.where(np.abs(s0 - c.s_dst) < reach, 0.5 * (1 + np.cos(np.pi * (s0 - c.s_dst) / reach)), 0.0)
    lat = _lateral(ms.points, ss, 3.0)
    lv = _interp_vec(np.clip(c.s_src + (s0 - c.s_dst) * cos, 0, ss[-1]), ss, lat)
    tw = np.sum(lv * nrm, axis=1)
    return w[:, None] * (lean_mm * tv[None, :] + tw[:, None] * nrm)


def _room(cuts, keep, s: float, h: float, min_dash: float) -> bool:
    """A gap (s-h, s+h) leaves every piece of its mark at least min_dash long (the mark's ends, after any
    stop, and the gaps already cut in it)."""
    lo, hi = keep
    if s - h - lo < min_dash or hi - (s + h) < min_dash:
        return False
    return all(s + h + min_dash <= a or s - h - min_dash >= b for a, b in cuts)


def _interp_vec(s_q, s, v):
    return np.column_stack([np.interp(s_q, s, v[:, 0]), np.interp(s_q, s, v[:, 1])])


@relation("crossing", phase="contact", params=[
    P("w_gap_under", "float", 0.26, "weight: the dst breaks (passes under the src)", min=0.0, max=1.0),
    P("w_gap_over", "float", 0.22, "weight: the src breaks (the dst passes over)", min=0.0, max=1.0),
    P("w_cross", "float", 0.30, "weight: both run through", min=0.0, max=1.0),
    P("w_stop", "float", 0.10, "weight: one line ends at the other (when a short tail allows it)",
      min=0.0, max=1.0),
    P("w_sympathy", "float", 0.12, "weight: no gap; the dst bends with the src near the crossing",
      min=0.0, max=1.0),
    P("streak", "float", 0.45, "chance the last outcome repeats at the next crossing", min=0.0, max=0.95),
    P("gap", "float", 1.75, "gap either side beyond the over line's half width, in pen widths",
      min=0.0, max=10.0),
    P("pen", "float", 0.4, "the over line's pen width, mm (gaps scale with it)", min=0.05, max=3.0),
    P("jitter", "float", 0.3, "each gap's size varies by up to this share", min=0.0, max=0.9),
    P("stop_max", "float", 25.0, "longest tail a stop may drop, mm", min=1.0, max=200.0),
    P("min_left", "float", 12.0, "a stop never leaves a line shorter than this, mm", min=2.0, max=200.0),
    P("reach", "float", 5.0, "sympathy: half-length of the bend along the dst, mm", min=1.0, max=20.0),
    P("lean", "float", 0.8, "sympathy: how far the dst is carried along the src's course, mm",
      min=0.0, max=4.0),
    P("min_sep", "float", 0.0, "crossings closer than this along a line count once, mm", min=0.0, max=20.0),
    P("min_piece", "float", 2.5, "pieces a gap leaves shorter than this are dropped, mm", min=0.2, max=10.0),
    P("min_dash", "float", 8.0, "no gap that would leave a piece shorter than this (no dashed lines), mm",
      min=0.0, max=40.0),
    P("tangle", "float", 4.0, "crossings of the same two marks closer than this along the dst are one tangle: "
      "one outcome, at its first crossing (the rest run through), mm", min=0.0, max=30.0),
    P("weights", "weights", None, "all five outcome weights as one dict (overrides the w_ floats when given)",
      choices=OUTCOMES, min=0.0, max=1.0, optional=True),
    P("pen_from", "choice", "param", "the over line's width for gaps: `pen` (param) or each mark's own pen "
      "width (marks: `pen_mm`, tagged by the executor from its layer's renderer)", choices=("param", "marks")),
], doc="every crossing gets its own outcome (under, over, through, stop, sympathy), drawn from weights; "
       "a streak lets an outcome repeat so it reads as behaviour")
def crossing(rctx, src, dst, *, w_gap_under, w_gap_over, w_cross, w_stop, w_sympathy, streak, gap, pen,
             jitter, stop_max, min_left, reach, lean, min_sep, min_piece, min_dash, tangle, weights=None,
             pen_from="param"):
    xs = crossings(src, dst, min_sep=min_sep)
    if not xs:
        return RelOut()
    if weights is None:
        weights = {"gap_under": w_gap_under, "gap_over": w_gap_over, "cross": w_cross, "stop": w_stop,
                   "sympathy": w_sympathy}
    left = rctx.remaining() if hasattr(rctx, "remaining") else None

    def over_pen(c, who):
        """The width of the line that stays whole at a gap (the src for gap_under, the dst for gap_over)."""
        if pen_from != "marks":
            return pen
        m = src[c.i_src] if who == "gap_under" else dst[c.i_dst]
        v = m.meta.get("pen_mm")
        return float(v) if isinstance(v, (int, float)) and v > 0 else pen
    on_dst: dict[int, list[float]] = {}
    on_src: dict[int, list[float]] = {}
    for c in xs:
        on_dst.setdefault(c.i_dst, []).append(c.s_dst)
        on_src.setdefault(c.i_src, []).append(c.s_src)
    for v in (*on_dst.values(), *on_src.values()):
        v.sort()
    Ld = [m.length() for m in dst]
    Ls = [m.length() for m in src]
    keep_d = {i: [0.0, Ld[i]] for i in on_dst}          # what a stop has left of each mark
    keep_s = {i: [0.0, Ls[i]] for i in on_src}
    cuts_d: dict[int, list] = {}
    cuts_s: dict[int, list] = {}
    bends: dict[int, list] = {}
    rng = rctx.rng("crossing")
    events, prev = [], None

    def stop_options(c):
        opts = []
        for who, i, s, lst, keep in (("dst", c.i_dst, c.s_dst, on_dst[c.i_dst], keep_d[c.i_dst]),
                                     ("src", c.i_src, c.s_src, on_src[c.i_src], keep_s[c.i_src])):
            lo, hi = keep
            if s == lst[0] and s - lo <= stop_max and hi - s >= min_left:
                opts.append((s - lo, who, i, (lo - 1.0, s), "start"))
            if s == lst[-1] and hi - s <= stop_max and s - lo >= min_left:
                opts.append((hi - s, who, i, (s, hi + 1.0), "end"))
        return sorted(opts, key=lambda o: (o[0], o[1]))

    last = None
    for c in xs:
        if (last is not None and tangle > 0 and c.i_dst == last.i_dst and c.i_src == last.i_src
                and c.s_dst - last.s_dst < tangle):
            last = c
            events.append({"outcome": "cross", "at": list(c.at), "mark": c.i_dst, "mark_src": c.i_src,
                           "s": [c.s_dst, c.s_dst], "s_src": [c.s_src, c.s_src], "tangle": True})
            continue
        last = c
        u_streak, u_pick, u_size = (float(v) for v in rng.random(3))
        elig = dict(weights)
        opts = stop_options(c)
        if not opts:
            elig["stop"] = 0.0
        h = pen * (0.5 + gap) * (1.0 + jitter * (2.0 * u_size - 1.0))       # this exact float order (golden)
        h_u, h_o = h, h
        if pen_from == "marks":
            h_u = over_pen(c, "gap_under") * (0.5 + gap) * (1.0 + jitter * (2.0 * u_size - 1.0))
            h_o = over_pen(c, "gap_over") * (0.5 + gap) * (1.0 + jitter * (2.0 * u_size - 1.0))
        if not _room(cuts_d.get(c.i_dst, ()), keep_d[c.i_dst], c.s_dst, h_u, min_dash):
            elig["gap_under"] = 0.0
        if not _room(cuts_s.get(c.i_src, ()), keep_s[c.i_src], c.s_src, h_o, min_dash):
            elig["gap_over"] = 0.0
        if left is not None and left <= 0:              # the sheet-wide budget is spent: lines just cross
            elig = {"cross": 1.0}
        near = [s for s in on_dst[c.i_dst] if s != c.s_dst and abs(s - c.s_dst) < reach]
        if near or c.s_dst < reach * 0.5 or Ld[c.i_dst] - c.s_dst < reach * 0.5:
            elig["sympathy"] = 0.0                 # a bend must not move a neighbouring crossing's gap
        repeat = prev is not None and u_streak < streak and elig.get(prev, 0.0) > 0
        out = prev if repeat else _draw(elig, u_pick)
        ev = {"outcome": out, "at": list(c.at), "mark": c.i_dst, "mark_src": c.i_src, "streak": bool(repeat)}
        if left is not None and out != "cross":
            left -= 1
        if out == "gap_under":
            h = h_u
            cuts_d.setdefault(c.i_dst, []).append((c.s_dst - h, c.s_dst + h))
            ev.update({"s": [c.s_dst - h, c.s_dst + h], "s_src": [c.s_src, c.s_src], "gap_mm": round(2 * h, 3)})
        elif out == "gap_over":
            h = h_o
            cuts_s.setdefault(c.i_src, []).append((c.s_src - h, c.s_src + h))
            ev.update({"s": [c.s_dst, c.s_dst], "s_src": [c.s_src - h, c.s_src + h], "gap_mm": round(2 * h, 3)})
        elif out == "stop":
            tail, who, i, iv, side = opts[0]
            (cuts_d if who == "dst" else cuts_s).setdefault(i, []).append(iv)
            keep = (keep_d if who == "dst" else keep_s)[i]
            if side == "start":
                keep[0] = iv[1]
            else:
                keep[1] = iv[0]
            ev.update({"s": [c.s_dst, c.s_dst], "s_src": [c.s_src, c.s_src], "who": who, "tail_mm": round(tail, 2)})
        elif out == "sympathy":
            lean_mm = round(lean * (0.75 + 0.5 * u_size), 3)
            bends.setdefault(c.i_dst, []).append((c, lean_mm))
            ev.update({"s": [c.s_dst - reach, c.s_dst + reach], "s_src": [c.s_src, c.s_src], "lean_mm": lean_mm})
        else:
            ev.update({"s": [c.s_dst, c.s_dst], "s_src": [c.s_src, c.s_src]})
        events.append(ev)
        prev = out

    new_dst = list(dst)
    for i in sorted(set(cuts_d) | set(bends)):
        m = dst[i]
        if i in bends:
            m = _fine(m)
            s0 = m.arclength()
            p = m.points
            td, nrm = _frame(p)
            disp = np.zeros_like(p)
            for c, lean_mm in bends[i]:
                disp += _bend(c, src[c.i_src], s0, td, nrm, reach, lean_mm)
            m = _moved(m, disp, rctx.frame)
            s1 = m.arclength()
            ivs = [(float(np.interp(a, s0, s1)), float(np.interp(b, s0, s1))) for a, b in cuts_d.get(i, [])]
        else:
            ivs = cuts_d[i]
        new_dst[i] = _pieces(cut(m, ivs, min_piece=min_piece), min_piece) if ivs else [m]
    flat_d = []
    for x in new_dst:
        flat_d += x if isinstance(x, list) else [x]
    out_src = None
    if cuts_s:
        out_src = []
        for i, m in enumerate(src):
            out_src += _pieces(cut(m, cuts_s[i], min_piece=min_piece), min_piece) if cuts_s.get(i) else [m]
    return RelOut(dst=flat_d, src=out_src, events=events)
