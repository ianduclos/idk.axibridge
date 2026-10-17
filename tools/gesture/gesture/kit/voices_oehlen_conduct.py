"""Round 12, thread `oehlen_conduct` — after Albert Oehlen's works on paper.

Three procedures from the research (results/oehlen-research-2026-10-17.md,
D3 / D4 / D5), read as procedures, never as looks:

- **Conduction** (D3, after the small drawing-collages → *Conduction*
  canvases, 2009–11). A small, fast SOURCE — a few seconds of one dancer's
  hand — is re-performed about ×6 by a learned hand. The performer never
  sees the source's shape: it receives CUES only (Butch Morris's conduction:
  the conductor signals, the players improvise). Cues are fired by the
  source's own kinematics:
    stop    the hand nearly still   → tacet: the line ends; the next one
                                      re-enters there (or from the sheet's
                                      edge, `edge_p`) — or a held knot
    turn    a sharp heading change  → a place to land on
    burst   the hand at its fastest → change: the next performer hand
  Between two cues the performer knows only where the next cue sits and how
  long the source took; its own grammar draws the way there (K proposals per
  chunk, steered toward the chord; the stretch is then bent so it lands
  `land` of the way onto the cue). Slow source stretches are sustained
  (more line than the chord needs) and inked with the heaviest pen.
- **Tree program** (D4, after the 1988 rules): see `oehlen_conduct_tree`.

Weight comes from the source's own speed: the slowest third of the
performance is inked with the heaviest pen (channel `cw`, pen width mm,
read by the `oehlen_conduct_ink` renderer). Channel `role`: 0 source,
1 performance, 2 retrace (second pass), 3 tree. Everything is placed in sheet
mm by the voice itself (the source at its own small size in a corner, the
performance in the rest), so use it with the `single` arranger.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

from .. import grammar as gm
from .. import hybrid as hyb
from .core import P, Mark, channel_kind, voice

channel_kind("cw", "nearest")
channel_kind("role", "nearest")
channel_kind("cue", "nearest")

CORNERS = ("tl", "tr", "bl", "br", "none")
STOP_ACTIONS = ("tacet", "knot", "carry")
SOURCES = ("dance", "hand")


# ---------------------------------------------------------------------------
# small geometry helpers
# ---------------------------------------------------------------------------

def arcl(p: np.ndarray) -> np.ndarray:
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))] if len(p) else np.zeros(0)


def resample(p: np.ndarray, step: float) -> np.ndarray:
    s = arcl(p)
    if len(p) < 2 or s[-1] <= 0:
        return np.asarray(p, float)
    n = max(int(math.ceil(s[-1] / step)) + 1, 2)
    u = np.linspace(0, s[-1], n)
    return np.column_stack([np.interp(u, s, p[:, 0]), np.interp(u, s, p[:, 1])])


def normals(p: np.ndarray) -> np.ndarray:
    t = np.gradient(p, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    return np.column_stack([-t[:, 1], t[:, 0]])


def in_blanks(p: np.ndarray, blanks: np.ndarray) -> np.ndarray:
    """(N,) bool: points inside any blank disc (cx, cy, r in mm)."""
    if not len(blanks):
        return np.zeros(len(p), bool)
    d = np.linalg.norm(p[:, None, :] - blanks[None, :, :2], axis=2)
    return np.any(d < blanks[None, :, 2], axis=1)


def split_offset(s: np.ndarray, rng, *, amp: float, splits: float, near: float) -> np.ndarray:
    """A signed offset along arc length s (mm) for the second pass: it lies
    ON the first line (within `near` mm, drifting slowly through zero) and
    splits away from it in a few places — each split a smooth bump of its
    own length, side and height (up to `amp` mm), so the pair opens and
    closes like two passes of charcoal, never a parallel band."""
    L = float(s[-1]) if len(s) else 0.0
    if L <= 0:
        return np.zeros(len(s))
    x = s / L
    o = np.zeros(len(s))
    for k in range(3):                                   # the slow near-zero drift (crosses)
        o += near * rng.normal() / (k + 1) * np.sin(2 * np.pi * (k + 1) * rng.uniform(0.5, 1.5) * x
                                                    + rng.uniform(0, 2 * np.pi))
    n = int(rng.poisson(max(splits, 0.0)))
    n = max(n, 1) if splits > 0 else 0
    for _ in range(n):
        c = rng.uniform(0.1, 0.9)
        w = rng.uniform(0.06, 0.22)
        h = amp * rng.uniform(0.35, 1.0) * (1 if rng.random() < 0.5 else -1)
        u = np.clip(1 - ((x - c) / w) ** 2, 0, None)
        o += h * u * u                                   # C1 bump: opens and closes smoothly
    return o


def retrace(p: np.ndarray, rng, *, amp: float, memory: float, cover: tuple, splits: float = 2.0,
            near: float = 0.5, overshoot: float = 0.0, step: float = 0.4):
    """The second pass (D5) over a stretch of p, drawn from memory: detail
    below `memory` mm is forgotten (smoothing), it lies on the first line
    and splits off in a few places (split_offset), and may overshoot the end
    along its own tangent. cover = (start share, end share) of p.
    Returns (points, index into p for each point) or None."""
    q = resample(p, step)
    if len(q) < 8:
        return None
    a, b = int(cover[0] * (len(q) - 1)), int(cover[1] * (len(q) - 1))
    if b - a < 6:
        return None
    sig = max(memory / step, 0.5)
    sm = np.column_stack([gaussian_filter1d(q[:, 0], sig, mode="nearest"),
                          gaussian_filter1d(q[:, 1], sig, mode="nearest")])[a:b + 1]
    off = split_offset(arcl(sm), rng, amp=amp, splits=splits, near=near)
    r = sm + normals(sm) * off[:, None]
    # where each retrace point sits on the ORIGINAL polyline (for its pen)
    sp, sq = arcl(p), arcl(q)
    src_i = np.clip(np.searchsorted(sp, sq[a:b + 1]), 0, len(p) - 1)
    if overshoot > 0 and len(r) > 3:
        t = r[-1] - r[-4]
        h = math.atan2(t[1], t[0])
        n_ext = int(overshoot / step)
        bend = rng.normal() * 0.6 / max(overshoot, 1e-9)
        ext = [r[-1]]
        for _ in range(n_ext):
            h += bend * step
            ext.append(ext[-1] + step * np.array([math.cos(h), math.sin(h)]))
        if len(ext) > 1:
            r = np.vstack([r, np.array(ext[1:])])
            src_i = np.r_[src_i, np.full(len(ext) - 1, src_i[-1])]
    return r, src_i


# ---------------------------------------------------------------------------
# the source: a few seconds of one dancer's hand (or a tiny drawn line)
# ---------------------------------------------------------------------------

def dance_source(ctx, trail: str, effector: str, t0: float, seconds: float):
    """(points in body heights, t seconds, speed) of one effector window."""
    tr = ctx.use("dance_trail", trail)
    fps = float(tr["fps"])
    n = len(tr["energy"])
    a0 = min(int(round(t0 * fps)), max(n - 4, 0))
    a1 = min(a0 + max(int(round(seconds * fps)), 4), n)
    p = np.asarray(tr[f"{effector}_xy"][a0:a1], float)
    v = np.asarray(tr[f"{effector}_v"][a0:a1], float)
    t = np.arange(len(p)) / fps
    return p, t, v


def cues_of(p: np.ndarray, t: np.ndarray, v: np.ndarray, *, still_q: float, turn_deg: float, burst_q: float,
            min_gap_s: float, return_r: float):
    """Cue events fired by the source's own kinematics → list of dicts
    {i, kind, hold} sorted by time (i: sample index). First and last sample
    are always cues (kind 'enter' / 'end')."""
    n = len(p)
    vs = gaussian_filter1d(v, 1.0)
    thr_still = float(np.quantile(vs, still_q))
    thr_burst = float(np.quantile(vs, burst_q))
    d = np.gradient(gaussian_filter1d(p, 1.5, axis=0), axis=0)
    h = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    dt = float(np.median(np.diff(t))) if n > 1 else 0.04
    w = max(int(round(0.16 / dt)), 1)
    turn = np.abs(h[np.minimum(np.arange(n) + w, n - 1)] - h[np.maximum(np.arange(n) - w, 0)])
    cand = []
    # stops: runs below the still threshold, one cue at the slowest sample, with hold time
    below = vs < thr_still
    idx = np.flatnonzero(below)
    if len(idx):
        for run in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1):
            j = int(run[np.argmin(vs[run])])
            cand.append((j, "stop", float((run[-1] - run[0] + 1) * dt), 3))
    # turns: local maxima of turning above the angle
    tt = np.deg2rad(turn_deg)
    for j in range(1, n - 1):
        if turn[j] >= tt and turn[j] >= turn[j - 1] and turn[j] > turn[j + 1] and not below[j]:
            cand.append((j, "turn", 0.0, 2))
    # bursts: local speed maxima above the burst quantile
    for j in range(1, n - 1):
        if vs[j] >= thr_burst and vs[j] >= vs[j - 1] and vs[j] > vs[j + 1]:
            cand.append((j, "burst", 0.0, 1))
    # returns: the hand comes back within return_r of where it was ≥ 1 s ago
    if return_r > 0 and n > 10:
        lag = max(int(round(1.0 / dt)), 2)
        tree = None
        for j in range(lag, n):
            tree = cKDTree(p[: j - lag + 1]) if (j - lag) % 5 == 0 or tree is None else tree
            dd, k = tree.query(p[j])
            if dd < return_r and (j == lag or not cand or cand[-1][1] != "return" or j - cand[-1][0] > lag):
                cand.append((j, "return", float(k), 0))
    # keep by priority (stop > turn > burst > return), min gap apart, ties by index
    cand.sort(key=lambda c: (-c[3], c[0]))
    gap = max(int(round(min_gap_s / dt)), 1)
    keep: list = []
    for c in cand:
        if c[0] <= gap or c[0] >= n - 1 - gap:
            continue
        if all(abs(c[0] - k[0]) >= gap for k in keep):
            keep.append(c)
    keep.sort(key=lambda c: c[0])
    out = [{"i": 0, "kind": "enter", "hold": 0.0}]
    for j, kind, x, _ in keep:
        out.append({"i": j, "kind": kind, "hold": x if kind == "stop" else 0.0,
                    "ref": int(x) if kind == "return" else None})
    out.append({"i": n - 1, "kind": "end", "hold": 0.0})
    return out, {"still": thr_still, "burst": thr_burst}


def edge_point(cen: np.ndarray, at: np.ndarray, box, rng, jitter: float = 0.12) -> np.ndarray:
    """Where a line entering (or leaving) through `at` meets the box edge:
    the ray from the performance centre through `at`, turned a little."""
    x0, y0, w, h = box
    d = at - cen
    ang = math.atan2(d[1], d[0]) + rng.normal() * jitter * math.pi
    u = np.array([math.cos(ang), math.sin(ang)])
    ts = []
    for k, (lo_, hi_) in enumerate(((x0, x0 + w), (y0, y0 + h))):
        if abs(u[k]) > 1e-9:
            ts += [(lo_ - at[k]) / u[k], (hi_ - at[k]) / u[k]]
    t = min([v for v in ts if v > 0], default=0.0)
    return at + u * t * 0.985


def thin_cues(cues: list, big: np.ndarray, min_mm: float) -> list:
    """Drop cues that land closer than min_mm (performance mm) to the last
    kept one — a tangle in the small source would otherwise become a tight
    zigzag of landings (barbs). Stops are kept (they decide tacets); the
    end is kept."""
    if min_mm <= 0 or len(cues) < 3:
        return cues
    out = [cues[0]]
    for c in cues[1:-1]:
        if c["kind"] == "stop" or np.linalg.norm(big[c["i"]] - big[out[-1]["i"]]) >= min_mm:
            out.append(c)
    if np.linalg.norm(big[cues[-1]["i"]] - big[out[-1]["i"]]) < min_mm and len(out) > 1 and out[-1]["kind"] != "stop":
        out.pop()
    out.append(cues[-1])
    return out


# ---------------------------------------------------------------------------
# the performer: a learned hand steered from cue to cue
# ---------------------------------------------------------------------------

class Performer:
    """Grows lines with learned hands, chunk by chunk, each chunk the best of
    K proposals scored by: distance to a moving target on the chord to the
    next cue (pull), crowding of its own past (clear), entering a blank
    (hard), leaving the box (hard). Same mechanism as `series_travel`."""

    def __init__(self, grams, rng, *, R, step, K, pull, clear, box, blanks, chunk, corner_cost=0.0):
        self.grams = grams
        self.rng = rng
        self.R = float(R)
        self.step = float(step)
        self.K = int(K)
        self.pull = float(pull)
        self.clear = float(clear)
        x0, y0, w, h = box
        self.lo = np.array([x0, y0])
        self.hi = np.array([x0 + w, y0 + h])
        self.blanks = blanks
        self.chunk = float(chunk)
        self.corner_cost = float(corner_cost)
        self.drawn: list[np.ndarray] = []

    def _tree(self, cur: list[np.ndarray]):
        lag = max(int(3 * self.clear / self.step), 4)
        cur_p = np.vstack(cur) if cur else np.zeros((0, 2))
        old = [*self.drawn, cur_p[:-lag] if len(cur_p) > lag else np.zeros((0, 2))]
        allp = np.vstack([o for o in old if len(o)]) if any(len(o) for o in old) else None
        return cKDTree(allp) if allp is not None and len(allp) > 4 else None

    def segment(self, g, pos, heading, toks, A, B, length_mm, cur, land=0.0):
        """Grow ≈ length_mm of line from pos toward the chord A→B; then bend
        the grown stretch so its end lands `land` of the way onto B (a
        smooth displacement growing along the stretch: the hand's turning is
        kept, the cue is hit). Returns (pos, heading, toks); points go to cur."""
        total = max(length_mm / self.R, 1e-3)
        done = 0.0
        k0 = len(cur)
        while done < total - 1e-6:
            Ls = g.stroke_lengths or [0.1]
            L = max(min(float(Ls[int(self.rng.integers(len(Ls)))]), self.chunk, total - done), 1e-3)
            tree = self._tree(cur)
            tgt = A + (B - A) * min((done + L) / total, 1.0)
            best = None
            for _ in range(self.K):
                c, _ = gm.generate_tokens(g, self.rng, length=L, context=None, p_follow=gm.P_FOLLOW,
                                          end_fit=gm.END_FIT)
                if not c:
                    continue
                if toks and toks[-1][0] in gm.SEG_KINDS and c[0][0] in gm.SEG_KINDS:
                    _, first = gm._continuity(toks[-1], c[0], lock_prev=True)
                    c = [first] + c[1:]
                p, _, _ = gm.tokens_to_points(c, self.R, start=pos, heading=heading, step=self.step)
                out = np.sum(np.clip(self.lo - p, 0, None) + np.clip(p - self.hi, 0, None)) / self.R
                blank = float(np.mean(in_blanks(p, self.blanks))) if len(self.blanks) else 0.0
                crowd = float(np.mean(tree.query(p, k=1)[0] < self.clear)) if tree is not None else 0.0
                d = float(np.linalg.norm(p[-1] - tgt) / self.R)
                nc = sum(1 for tk in c if tk[0] == "corner" and abs(tk[1]) > 0.9)
                score = 50 * out + 200 * blank + 2.0 * crowd + self.pull * d + self.corner_cost * nc \
                    + 0.05 * self.rng.random()
                if best is None or score < best[0]:
                    best = (score, c, p)
            if best is None:
                break
            _, c, p = best
            toks = toks + c
            cur.append(p[1:])
            heading = gm.end_heading(c, heading)
            pos = p[-1]
            done += gm.stroke_length(c)
        if land > 0 and len(cur) > k0:
            seg = np.vstack(cur[k0:])
            s = arcl(np.vstack([cur[k0 - 1][-1:], seg]) if k0 > 0 else seg)[-len(seg):]
            u = s / max(s[-1], 1e-9)
            w = u * u * (3 - 2 * u)
            seg = seg + np.outer(w, (B - seg[-1]) * land)
            n_ = [len(c) for c in cur[k0:]]
            cur[k0:] = np.split(seg, np.cumsum(n_)[:-1])
            pos = seg[-1]
            if len(seg) > 2:
                d = seg[-1] - seg[-3]
                heading = math.atan2(d[1], d[0])
        return pos, heading, toks

    def knot(self, pos, heading, size, cur):
        """A held stop: the line winds once or twice on the spot (a round
        knot made of the line itself, contiguous with it)."""
        turns = 1.0 + 0.8 * self.rng.random()
        n = max(int(turns * 2 * math.pi * size / self.step), 12)
        side = 1.0 if self.rng.random() < 0.5 else -1.0
        a = np.linspace(0, turns * 2 * math.pi, n)
        r = size * (0.55 + 0.45 * np.sin(np.linspace(0, math.pi, n)))
        c = pos + size * np.array([math.cos(heading + side * math.pi / 2), math.sin(heading + side * math.pi / 2)])
        ang0 = heading - side * math.pi / 2
        pts = c + np.column_stack([r * np.cos(ang0 + side * a), r * np.sin(ang0 + side * a)])
        pts = pts - pts[0] + pos
        cur.append(pts[1:])
        return pts[-1], heading + side * turns * 2 * math.pi


# ---------------------------------------------------------------------------
# the voice
# ---------------------------------------------------------------------------

def _corner_box(frame, corner: str, size: float, aspect: float, inset: float):
    W, H = frame
    w = size if aspect >= 1 else size * aspect
    h = size / aspect if aspect >= 1 else size
    x = inset if corner in ("tl", "bl") else W - inset - w
    y = inset if corner in ("tl", "tr") else H - inset - h
    return (x, y, w, h)


def conduct(ctx, *, trail, effector, t0, seconds, hands, corner, src_size, enlarge, gesture, sustain, stop_action,
            hold_s, still_q, turn_deg, burst_q, min_gap_s, blanks, K, pull, clear, chunk, step,
            pens, double, double_amp, double_memory, place, land, double_splits, double_pen,
            corner_cost, change_on, min_cue_mm, edge_p, blank_hard):
    rng = np.random.default_rng([ctx.seed, 0x0E41E7])
    W, H = ctx.frame
    x0, y0, bw, bh = ctx.box
    # 1. the source, at its own small size in a corner
    p, t, v = dance_source(ctx, trail, effector, t0, seconds)
    lo, hi = p.min(0), p.max(0)
    ext = np.maximum(hi - lo, 1e-9)
    aspect = float(ext[0] / ext[1])
    if corner != "none":
        sb = _corner_box((W, H), corner, src_size, aspect, x0)
        ks = min(sb[2] / ext[0], sb[3] / ext[1])
        src = (p - lo) * ks + np.array(sb[:2])
    else:
        sb, ks, src = None, 1.0, None
    # 2. reserve the blanks FIRST (fractions of the box → mm), plus the source's corner
    bl = np.asarray(blanks, float).reshape(-1, 3) if blanks else np.zeros((0, 3))
    bl = np.column_stack([x0 + bl[:, 0] * bw, y0 + bl[:, 1] * bh, bl[:, 2] * min(bw, bh)]) if len(bl) else bl
    if sb is not None:
        c = np.array([sb[0] + sb[2] / 2, sb[1] + sb[3] / 2])
        bl = np.vstack([bl, [c[0], c[1], 0.62 * math.hypot(sb[2], sb[3]) + 4.0]]) if len(bl) else \
            np.array([[c[0], c[1], 0.62 * math.hypot(sb[2], sb[3]) + 4.0]])
    n_user = len(np.asarray(blanks, float).reshape(-1, 3)) if blanks else 0
    bl_hard = bl[:n_user] * np.array([1.0, 1.0, 0.97]) if (n_user and blank_hard) else np.zeros((0, 3))
    # 3. the cue track
    cues, thr = cues_of(p, t, v, still_q=still_q, turn_deg=turn_deg, burst_q=burst_q, min_gap_s=min_gap_s,
                        return_r=0.0)
    # 4. where the performance goes: the source ×enlarge, centred in the box at `place` (fractions)
    fit_k = 0.94 * min(bw / ext[0], bh / ext[1])            # the performance must fit the box
    kb = min(enlarge * ks, fit_k)
    enlarge = kb / ks
    cen = np.array([x0 + place[0] * bw, y0 + place[1] * bh])
    half = ext * kb / 2                                      # keep it inside, whatever `place` says
    cen = np.clip(cen, np.array([x0, y0]) + half, np.array([x0 + bw, y0 + bh]) - half)
    big = (p - (lo + hi) / 2) * kb + cen
    cues = thin_cues(cues, big, min_cue_mm)
    grams = [ctx.use("hand", h) for h in hands]
    R = gesture * 0.95 * math.hypot(bw, bh)
    perf = Performer(grams, rng, R=R, step=step, K=K, pull=pull, clear=clear, box=ctx.box, blanks=bl,
                     chunk=chunk, corner_cost=corner_cost)
    s_src = arcl(p)
    vmean = []
    lines: list[dict] = []
    gi = 0
    cur: list[np.ndarray] = []
    pos = big[0].copy()
    d0 = big[min(cues[1]["i"], len(big) - 1)] - pos
    heading = math.atan2(d0[1], d0[0]) + rng.normal() * 0.4
    toks: list = []
    cur = [pos[None, :]]
    cur_cw_runs = []
    mid_pen = pens[len(pens) // 2] if len(pens) else 0.4

    def approach(at):
        """A line that enters from the sheet's edge and reaches `at`."""
        nonlocal pos, heading, toks, cur
        e = edge_point(cen, at, ctx.box, rng)
        for _ in range(12):                                 # never out of the source's corner
            if not len(bl) or not np.any(np.linalg.norm(bl[:, :2] - e, axis=1) < bl[:, 2] + 12.0):
                break
            e = edge_point(cen, at, ctx.box, rng, jitter=0.35)
        dd = at - e
        heading = math.atan2(dd[1], dd[0]) + rng.normal() * 0.3
        pos = e
        cur = [pos[None, :]]
        cur_cw_runs.append((0, mid_pen))
        pos, heading, toks = perf.segment(grams[gi % len(grams)], pos, heading, [], e, at,
                                          float(np.linalg.norm(dd)) * 1.1, cur, land=1.0)

    if rng.random() < edge_p:
        approach(big[0])
    cue_log = []
    seg_speed = []
    for j in range(len(cues) - 1):
        a, b = cues[j]["i"], cues[j + 1]["i"]
        seg_speed.append(float(np.mean(v[a:b + 1])))
    sp = np.asarray(seg_speed)
    rank = np.argsort(np.argsort(sp)) / max(len(sp) - 1, 1)          # 0 slowest … 1 fastest
    pen_of = lambda r: pens[min(int((1 - r) * len(pens)), len(pens) - 1)] if len(pens) else 0.4  # noqa: E731

    def flush():
        """End the current line. A reserved blank is hard: whatever of the line
        still entered one is cut out there (pieces under 4 mm are dropped)."""
        nonlocal cur, cur_cw_runs, toks
        pts = np.vstack(cur) if cur else np.zeros((0, 2))
        if len(pts) >= 3:
            cw = np.zeros(len(pts))
            rr = list(cur_cw_runs) + [(len(pts), 0.0)]
            cw[:] = rr[0][1]
            for (s0, w0), (s1, _) in zip(rr[:-1], rr[1:]):
                cw[s0:s1] = w0
            inside = in_blanks(pts, bl_hard) if len(bl_hard) else np.zeros(len(pts), bool)
            idx = np.flatnonzero(~inside)
            pieces = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []
            for pc in pieces:
                if len(pc) >= 3 and arcl(pts[pc])[-1] > 4.0:
                    lines.append({"points": pts[pc], "cw": cw[pc], "hand": int(gi % len(hands))})
                    perf.drawn.append(pts[pc])
        cur, cur_cw_runs, toks = [], [], []

    skip_to = -1

    def reenter(at, j_next):
        """Tacet over: the next entry starts near `at`, heading for cue j_next."""
        nonlocal pos, heading, gi
        if change_on in ("tacet", "both"):
            gi += 1
        if rng.random() < edge_p:
            approach(at)
            return
        pos = at + rng.normal(size=2) * 0.02 * R
        if j_next < len(cues):
            dd = big[cues[j_next]["i"]] - pos
            heading = math.atan2(dd[1], dd[0]) + rng.normal() * 0.6

    for j in range(len(cues) - 1):
        if j < skip_to:
            continue
        c0, c1 = cues[j], cues[j + 1]
        A, B = big[c0["i"]], big[c1["i"]]
        chord = float(np.linalg.norm(B - A))
        src_len = float(s_src[c1["i"]] - s_src[c0["i"]]) * kb
        slow = 1.0 - rank[j]
        Lmm = max(chord * 1.05, src_len * (0.55 + sustain * slow))
        cw = pen_of(rank[j])
        g = grams[gi % len(grams)]
        if not cur:
            cur = [pos[None, :]]
        n_before = sum(len(c) for c in cur)
        # a cue that falls in a reserved blank is swallowed: the line breaks off toward it,
        # and the performance re-enters at the first cue outside the blank
        if len(bl) and in_blanks(B[None, :], bl)[0]:
            pos, heading, toks = perf.segment(g, pos, heading, toks, A, A + (B - A) * 0.4, 0.4 * Lmm, cur)
            cur_cw_runs.append((n_before, cw))
            flush()
            k = j + 1
            while k < len(cues) - 1 and in_blanks(big[cues[k]["i"]][None, :], bl)[0]:
                k += 1
            cue_log.append({"cue": c1["kind"], "action": "swallowed", "resume": int(k)})
            reenter(big[cues[k]["i"]], k + 1)
            skip_to = k
            continue
        pos, heading, toks = perf.segment(g, pos, heading, toks, A, B, Lmm, cur, land=land)
        cur_cw_runs.append((n_before, cw))
        kind = c1["kind"]
        if kind == "stop" and stop_action == "tacet" and c1["hold"] >= hold_s:
            flush()
            reenter(B, j + 2)
            cue_log.append({"cue": "stop", "action": "tacet", "hold": c1["hold"]})
        elif kind == "stop" and stop_action == "knot":
            n_b = sum(len(c) for c in cur)
            pos, heading = perf.knot(pos, heading, min(1.2 + 6.0 * c1["hold"], 5.0) * (kb / 40.0), cur)
            cur_cw_runs.append((n_b, pens[0] if len(pens) else cw))
            cur_cw_runs.append((sum(len(c) for c in cur), cw))
            cue_log.append({"cue": "stop", "action": "knot", "hold": c1["hold"]})
        elif kind == "burst" and change_on in ("burst", "both"):
            gi += 1
            cue_log.append({"cue": "burst", "action": "change", "hand": hands[gi % len(hands)]})
        else:
            cue_log.append({"cue": kind, "action": "aim"})
    if cur and rng.random() < edge_p:                       # the last line runs off to the edge
        e = edge_point(cen, pos, ctx.box, rng)
        n_b = sum(len(c) for c in cur)
        pos, heading, toks = perf.segment(grams[gi % len(grams)], pos, heading, toks, pos.copy(), e,
                                          float(np.linalg.norm(e - pos)) * 1.1, cur, land=1.0)
        cur_cw_runs.append((n_b, mid_pen))
    flush()
    # 5. second passes (D5): a drifting retrace of the longest lines
    marks = []
    for li, ln in enumerate(lines):
        pts = ln["points"]
        cw = np.asarray(ln["cw"], float)
        cw[cw <= 0] = pens[-1] if len(pens) else 0.4
        marks.append(Mark(pts, {"cw": cw, "role": np.ones(len(pts)), "r": np.zeros(len(pts))},
                          {"voices": list(hands), "line": li, "role": "performance"}))
    if double > 0:
        Ls = np.array([arcl(m.points)[-1] for m in marks])
        order = np.argsort(-Ls, kind="stable")
        nd = int(round(double * len(marks)))
        for li in sorted(order[:nd].tolist()):
            m = marks[li]
            a = float(rng.uniform(0.04, 0.35))
            b = float(rng.uniform(0.6, 0.96))
            rr = retrace(m.points, rng, amp=double_amp, memory=double_memory, cover=(a, b),
                         splits=double_splits, near=0.6, overshoot=float(rng.uniform(0, 0.05) * R))
            if rr is None:
                continue
            r, si = rr
            cw0 = np.asarray(m["cw"])[si]
            if double_pen == "thinner":                  # the next lighter pen, per point
                cw2 = np.array([max([pp for pp in pens if pp < w] or [w]) for w in cw0])
            else:
                cw2 = cw0
            marks.append(Mark(r, {"cw": cw2, "role": np.full(len(r), 2.0), "r": np.zeros(len(r))},
                              {"voices": list(hands), "line": int(li), "role": "retrace"}))
    if src is not None:
        pmin = min(pens) if len(pens) else 0.25
        marks.insert(0, Mark(src, {"cw": np.full(len(src), pmin), "role": np.zeros(len(src)),
                                   "r": np.zeros(len(src))},
                             {"voices": [f"dance:{trail}:{effector}"], "role": "source"}))
    meta = {"cues": [{"t": float(t[c["i"]]), "kind": c["kind"], "hold": c["hold"], "mm": big[c["i"]].tolist(),
                      "src_mm": (src[c["i"]].tolist() if src is not None else None)} for c in cues],
            "actions": cue_log, "thresholds": thr, "enlarge": enlarge, "R_mm": R, "lines": len(lines),
            "blanks_mm": bl.tolist(), "source_box": list(sb) if sb else None}
    return [m.evolve(meta={"conduct": meta if i == 0 else {"n": i}}) for i, m in enumerate(marks)]


@voice("oehlen_conduct", params=[
    P("trail", "ref", "staccato", "the dance whose hand is the source", kind="dance_trail"),
    P("effector", "choice", "rhand", "which body end is the source", choices=("lhand", "rhand", "lfoot", "rfoot",
                                                                               "head")),
    P("t0", "float", 5.0, "source start, seconds into the dance window", min=0.0, max=60.0),
    P("seconds", "float", 7.0, "how many seconds of the hand", min=1.0, max=30.0),
    P("hands", "refs", ["trail_miner"], "performer hands; a burst cue hands over to the next",
      kind="hand", min_len=1, max_len=5),
    P("corner", "choice", "tl", "where the source sits at its own small size (none = not shown)", choices=CORNERS),
    P("src_size", "float", 34.0, "the source's longer side, mm", min=10.0, max=120.0),
    P("enlarge", "float", 6.0, "performance scale ÷ source scale", min=1.0, max=12.0),
    P("place", "floats", [0.55, 0.52], "performance centre, fractions of the box"),
    P("gesture", "float", 0.6, "the performer's gesture scale R, × the box diagonal", min=0.05, max=3.0),
    P("sustain", "float", 0.3, "slow source stretches get this much more line than they took (fast ones less)",
      min=0.0, max=6.0),
    P("stop_action", "choice", "tacet", "a long stop: tacet (the line ends, re-enters) | knot | carry",
      choices=STOP_ACTIONS),
    P("hold_s", "float", 0.08, "a stop held at least this long (source seconds) is a tacet", min=0.0, max=5.0),
    P("still_q", "float", 0.12, "stop: speed below this quantile of the source's speed", min=0.0, max=0.5),
    P("turn_deg", "float", 75.0, "turn: heading change within ±0.16 s at least this", min=10.0, max=180.0),
    P("burst_q", "float", 0.93, "burst: speed peaks above this quantile", min=0.5, max=1.0),
    P("min_gap_s", "float", 0.35, "cues at least this far apart, source seconds", min=0.05, max=3.0),
    P("blanks", "floats", [], "reserved blank discs: triples (cx, cy as fractions of the box, r × min side)"),
    P("K", "int", 16, "proposals per chunk", min=1, max=40),
    P("pull", "float", 8.0, "how hard a cue steers the performer", min=0.0, max=40.0),
    P("clear", "float", 2.0, "the performer avoids its own past within this, mm", min=0.0, max=20.0),
    P("chunk", "float", 0.12, "longest chunk between steering decisions, R", min=0.01, max=4.0),
    P("step", "float", 0.35, "sampling step, mm", min=0.05, max=2.0),
    P("pens", "floats", [2.2, 0.5], "pen widths, heaviest first: slowest source stretches get the heaviest"),
    P("double", "float", 0.6, "share of the performance lines (longest first) retraced by a second pass",
      min=0.0, max=1.0),
    P("double_amp", "float", 8.0, "how far the second pass drifts off, mm", min=0.0, max=30.0),
    P("double_memory", "float", 3.0, "the second pass forgets detail below this, mm (smoothing σ)",
      min=0.0, max=60.0),
    P("double_splits", "float", 2.0, "mean number of places where the second pass splits off", min=0.0,
      max=12.0),
    P("double_pen", "choice", "same", "the second pass's pen: same as the line under it | thinner",
      choices=("same", "thinner")),
    P("min_cue_mm", "float", 20.0, "cues landing closer than this to the previous one are dropped (no barbs)",
      min=0.0, max=80.0),
    P("blank_hard", "bool", False, "blanks are hard: lines that still enter one are cut at its rim "
      "(soft: lines are only steered out of them and cues inside are swallowed)"),
    P("edge_p", "float", 1.0, "chance that an entry (first line, after a tacet) comes in from the sheet's edge, "
      "and that the last line runs off to it", min=0.0, max=1.0),
    P("change_on", "choice", "both", "when the next performer hand takes over: burst cues | each tacet | both",
      choices=("burst", "tacet", "both")),
    P("corner_cost", "float", 0.4, "penalty per sharp corner (> 50°) in a proposal: fewer barbs", min=0.0,
      max=20.0),
    P("land", "float", 0.75, "how exactly the performer lands on each cue (0 = only steered toward it)",
      min=0.0, max=1.0),
], doc="conduction: a few seconds of a dancer's hand, small in a corner, re-performed ×6 by a learned hand "
       "that get only its cues (stop, turn, burst); blanks reserved first; lines doubled by a drifting second pass")
def oehlen_conduct(ctx, **kw):
    return conduct(ctx, **kw)


# ---------------------------------------------------------------------------
# D4: the tree program
# ---------------------------------------------------------------------------

def narrowing(points: np.ndarray, mid: np.ndarray, reach: float, pens) -> np.ndarray:
    """Oehlen's 1988 rule as a weight program: the pen narrows with distance
    from the figure's midpoint (pens heaviest first, evenly by distance)."""
    d = np.linalg.norm(points - mid, axis=1) / max(reach, 1e-9)
    k = np.clip((d * len(pens)).astype(int), 0, len(pens) - 1)
    return np.asarray(pens, float)[k]


def tree(ctx, *, trail, effector, t0, seconds, hands, corner, src_size, gesture, K, pull, clear, chunk, step, pens,
         still_q, turn_deg, burst_q, min_gap_s, branch_len, orders, spread, land, double, double_amp, double_memory,
         double_splits):
    rng = np.random.default_rng([ctx.seed, 0x7EE])
    W, H = ctx.frame
    x0, y0, bw, bh = ctx.box
    p, t, v = dance_source(ctx, trail, effector, t0, seconds)
    cues, thr = cues_of(p, t, v, still_q=still_q, turn_deg=turn_deg, burst_q=burst_q, min_gap_s=min_gap_s,
                        return_r=0.0)
    lo, hi = p.min(0), p.max(0)
    ext = np.maximum(hi - lo, 1e-9)
    sb = None
    if corner != "none":
        sb = _corner_box((W, H), corner, src_size, float(ext[0] / ext[1]), x0)
        ks = min(sb[2] / ext[0], sb[3] / ext[1])
        src = (p - lo) * ks + np.array(sb[:2])
    grams = [ctx.use("hand", h) for h in hands]
    R = gesture * 0.95 * math.hypot(bw, bh)
    bl = np.zeros((0, 3))
    if sb is not None:
        c = np.array([sb[0] + sb[2] / 2, sb[1] + sb[3] / 2])
        bl = np.array([[c[0], c[1], 0.62 * math.hypot(sb[2], sb[3]) + 4.0]])
    perf = Performer(grams, rng, R=R, step=step, K=K, pull=pull, clear=clear, box=ctx.box, blanks=bl, chunk=chunk)
    cx = x0 + bw / 2
    mid = np.array([cx, y0 + bh * 0.5])
    # the trunk: vertical, centred, bottom to top; its stretches between cues keep the source's timing
    tt = np.array([t[c["i"]] for c in cues]) / max(t[-1], 1e-9)
    ys = y0 + bh * (0.98 - 0.9 * tt)
    sway = (p[[c["i"] for c in cues], 0] - (lo[0] + hi[0]) / 2) / ext[0] * bw * 0.12
    targets = np.column_stack([cx + sway, ys])
    lines = []
    pos = targets[0].copy()
    heading = -math.pi / 2
    toks: list = []
    cur = [pos[None, :]]
    events = []
    for j in range(len(cues) - 1):
        A, B = targets[j], targets[j + 1]
        L = float(np.linalg.norm(B - A)) * 1.15
        pos, heading, toks = perf.segment(grams[0], pos, heading, toks, A, B, L, cur, land=land)
        if cues[j + 1]["kind"] in ("stop", "burst", "turn"):
            events.append((pos.copy(), cues[j + 1], j + 1))
    trunk = np.vstack(cur)
    perf.drawn.append(trunk)
    lines.append((trunk, 0))
    # branches: fired at the trunk's cue points; side from the source's turning there, length from the event
    d = np.gradient(gaussian_filter1d(p, 1.5, axis=0), axis=0)
    hsrc = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    gen = [(e[0], e[1], 1) for e in events]
    while gen:
        at, cue, order = gen.pop(0)
        if order > orders:
            continue
        i = cue["i"]
        turn = float(hsrc[min(i + 3, len(hsrc) - 1)] - hsrc[max(i - 3, 0)])
        side = 1.0 if turn > 0 else -1.0
        if cue["kind"] == "burst":
            side = -side
        ang = -math.pi / 2 + side * (spread * (0.5 + 0.5 * rng.random()))
        Lb = branch_len * R * (1.4 if cue["kind"] == "stop" else 1.0) * (0.55 ** (order - 1)) * \
            (0.6 + 0.8 * rng.random())
        Bt = at + Lb * np.array([math.cos(ang), math.sin(ang)])
        cur = [at[None, :]]
        g = grams[order % len(grams)]
        pos2, h2, _ = perf.segment(g, at.copy(), ang, [], at, Bt, Lb, cur, land=land * 0.5)
        br = np.vstack(cur)
        if arcl(br)[-1] < 3:
            continue
        perf.drawn.append(br)
        lines.append((br, order))
        # a branch's own events: the next cue(s) after this one, spread along it
        later = [c for c in cues if c["i"] > i and c["kind"] in ("stop", "burst")][:1]
        for c in later:
            k = int(len(br) * (0.4 + 0.4 * rng.random()))
            gen.append((br[k], c, order + 1))
    reach = max(float(np.max(np.linalg.norm(np.vstack([ln for ln, _ in lines]) - mid, axis=1))), 1.0)
    marks = []
    for li, (ln, order) in enumerate(lines):
        cw = narrowing(ln, mid, reach, pens)
        marks.append(Mark(ln, {"cw": cw, "role": np.full(len(ln), 3.0), "r": np.zeros(len(ln))},
                          {"voices": list(hands), "order": order, "role": "tree"}))
    if double > 0:
        Ls = np.array([arcl(m.points)[-1] for m in marks])
        for li in sorted(np.argsort(-Ls, kind="stable")[: int(round(double * len(marks)))].tolist()):
            m = marks[li]
            rr = retrace(m.points, rng, amp=double_amp, memory=double_memory,
                         cover=(float(rng.uniform(0, 0.3)), float(rng.uniform(0.6, 1.0))), splits=double_splits)
            if rr is None:
                continue
            r, si = rr
            marks.append(Mark(r, {"cw": np.asarray(m["cw"])[si], "role": np.full(len(r), 2.0),
                                  "r": np.zeros(len(r))}, {"voices": list(hands), "role": "retrace"}))
    if sb is not None:
        marks.insert(0, Mark(src, {"cw": np.full(len(src), min(pens)), "role": np.zeros(len(src)),
                                   "r": np.zeros(len(src))}, {"role": "source"}))
    meta = {"cues": [{"t": float(t[c["i"]]), "kind": c["kind"], "hold": c["hold"]} for c in cues],
            "lines": len(lines), "R_mm": R, "orders": [o for _, o in lines], "source_box": list(sb) if sb else None,
            "blanks_mm": bl.tolist()}
    return [m.evolve(meta={"conduct": meta if i == 0 else {"n": i}}) for i, m in enumerate(marks)]


@voice("oehlen_conduct_tree", params=[
    P("trail", "ref", "staccato", "the dance whose hand fires the branches", kind="dance_trail"),
    P("effector", "choice", "rhand", "which body end", choices=("lhand", "rhand", "lfoot", "rfoot", "head")),
    P("t0", "float", 5.0, "source start, s", min=0.0, max=60.0),
    P("seconds", "float", 7.0, "source length, s", min=1.0, max=30.0),
    P("hands", "refs", ["trail_miner"], "hand of the trunk, then of each branch order", kind="hand",
      min_len=1, max_len=5),
    P("corner", "choice", "none", "show the source small in a corner", choices=CORNERS),
    P("src_size", "float", 30.0, "source size, mm", min=10.0, max=120.0),
    P("gesture", "float", 0.5, "gesture scale R × box diagonal", min=0.05, max=3.0),
    P("K", "int", 16, "proposals per chunk", min=1, max=40),
    P("pull", "float", 8.0, "steering", min=0.0, max=40.0),
    P("clear", "float", 2.0, "self-avoidance, mm", min=0.0, max=20.0),
    P("chunk", "float", 0.12, "chunk, R", min=0.01, max=4.0),
    P("step", "float", 0.35, "sampling step, mm", min=0.05, max=2.0),
    P("pens", "floats", [1.4, 0.8, 0.45, 0.25], "pens heaviest first: the line narrows away from the midpoint"),
    P("still_q", "float", 0.12, "stop quantile", min=0.0, max=0.5),
    P("turn_deg", "float", 75.0, "turn threshold, degrees", min=10.0, max=180.0),
    P("burst_q", "float", 0.93, "burst quantile", min=0.5, max=1.0),
    P("min_gap_s", "float", 0.35, "cue spacing, s", min=0.05, max=3.0),
    P("branch_len", "float", 0.3, "first-order branch length, R", min=0.02, max=2.0),
    P("orders", "int", 2, "branch orders", min=1, max=4),
    P("spread", "float", 1.2, "branch angle from vertical, rad", min=0.1, max=3.0),
    P("land", "float", 0.6, "how exactly the trunk lands on its cue points", min=0.0, max=1.0),
    P("double", "float", 0.3, "share of lines retraced", min=0.0, max=1.0),
    P("double_amp", "float", 6.0, "retrace drift, mm", min=0.0, max=30.0),
    P("double_memory", "float", 3.0, "retrace memory, mm", min=0.0, max=60.0),
    P("double_splits", "float", 2.0, "retrace splits", min=0.0, max=12.0),
], doc="the tree as a program (Oehlen 1988): vertical, centred trunk; branches fired by a dancer's hand's "
       "stops and bursts; every line narrows with distance from the figure's midpoint")
def oehlen_conduct_tree(ctx, **kw):
    return tree(ctx, **kw)


# ---------------------------------------------------------------------------
# D3 × D5: the conducted ensemble — the doubling is a second player
# ---------------------------------------------------------------------------

def ensemble(ctx, *, trail, effector, t0, seconds, players, pens, corner, src_size, enlarge, place, gesture, sustain,
             still_q, turn_deg, burst_q, min_gap_s, K, pull, clear, chunk, step, land, corner_cost, slow_solo,
             tutti_burst, blanks, spread, min_cue_mm):
    """Several learned hands (the players) get the SAME cue track from one
    dancer's hand (the conductor). At each cue the conductor decides who
    plays the next stretch: slow source stretches are solos, fast ones
    bring more players in, a burst is tutti, a stop changes the soloist.
    Every player lands near the same cue points (within `spread` mm) and
    fills the way between in its own grammar, so where two play the same
    stretch the line is doubled by a different hand: the pair meets at the
    cues and parts between them — never a parallel copy."""
    rng = np.random.default_rng([ctx.seed, 0xE45E])
    W, H = ctx.frame
    x0, y0, bw, bh = ctx.box
    p, t, v = dance_source(ctx, trail, effector, t0, seconds)
    lo, hi = p.min(0), p.max(0)
    ext = np.maximum(hi - lo, 1e-9)
    sb = _corner_box((W, H), corner, src_size, float(ext[0] / ext[1]), x0) if corner != "none" else None
    ks = min(sb[2] / ext[0], sb[3] / ext[1]) if sb else 1.0
    src = (p - lo) * ks + np.array(sb[:2]) if sb else None
    bl = np.asarray(blanks, float).reshape(-1, 3) if blanks else np.zeros((0, 3))
    bl = np.column_stack([x0 + bl[:, 0] * bw, y0 + bl[:, 1] * bh, bl[:, 2] * min(bw, bh)]) if len(bl) else bl
    soft = bl
    if sb is not None:
        c = np.array([sb[0] + sb[2] / 2, sb[1] + sb[3] / 2])
        soft = np.vstack([bl, [[c[0], c[1], 0.62 * math.hypot(sb[2], sb[3]) + 4.0]]])
    cues, thr = cues_of(p, t, v, still_q=still_q, turn_deg=turn_deg, burst_q=burst_q, min_gap_s=min_gap_s,
                        return_r=0.0)
    fit_k = 0.94 * min(bw / ext[0], bh / ext[1])
    kb = min(enlarge * ks, fit_k)
    cen = np.array([x0 + place[0] * bw, y0 + place[1] * bh])
    half = ext * kb / 2
    cen = np.clip(cen, np.array([x0, y0]) + half, np.array([x0 + bw, y0 + bh]) - half)
    big = (p - (lo + hi) / 2) * kb + cen
    cues = thin_cues(cues, big, min_cue_mm)
    s_src = arcl(p)
    n = len(players)
    grams = [ctx.use("hand", h) for h in players]
    R = gesture * 0.95 * math.hypot(bw, bh)
    shared: list[np.ndarray] = []
    perfs = []
    for i in range(n):
        pf = Performer([grams[i]], np.random.default_rng([ctx.seed, 0xE45E, i]), R=R, step=step, K=K, pull=pull,
                       clear=clear, box=ctx.box, blanks=soft, chunk=chunk, corner_cost=corner_cost)
        pf.drawn = shared                                  # players avoid each other's past too
        perfs.append(pf)
    seg_speed = np.array([float(np.mean(v[cues[j]["i"]:cues[j + 1]["i"] + 1])) for j in range(len(cues) - 1)])
    rank = np.argsort(np.argsort(seg_speed)) / max(len(seg_speed) - 1, 1)
    # the conductor's score: who plays each stretch
    solo = 0
    score = []
    for j in range(len(cues) - 1):
        kind = cues[j]["kind"]
        if kind == "stop":
            solo = (solo + 1) % n                          # a stop hands the solo on
        if kind == "burst" and tutti_burst:
            k = n
        elif rank[j] < slow_solo:
            k = 1
        else:
            k = 1 + int(round((rank[j] - slow_solo) / max(1 - slow_solo, 1e-9) * (n - 1)))
        score.append(sorted({(solo + q) % n for q in range(max(1, min(k, n)))}))
    state = [{"cur": [], "pos": None, "heading": 0.0, "toks": []} for _ in range(n)]
    lines = []

    def end(i):
        st = state[i]
        if st["cur"]:
            pts = np.vstack(st["cur"])
            inside = in_blanks(pts, bl) if len(bl) else np.zeros(len(pts), bool)
            idx = np.flatnonzero(~inside)
            for pc in (np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []):
                if len(pc) >= 3 and arcl(pts[pc])[-1] > 4.0:
                    lines.append((pts[pc], i))
                    shared.append(pts[pc])
        st["cur"], st["toks"], st["pos"] = [], [], None

    for j in range(len(cues) - 1):
        A, B = big[cues[j]["i"]], big[cues[j + 1]["i"]]
        chord = float(np.linalg.norm(B - A))
        src_len = float(s_src[cues[j + 1]["i"]] - s_src[cues[j]["i"]]) * kb
        Lmm = max(chord * 1.05, src_len * (0.55 + sustain * (1 - rank[j])))
        for i in range(n):
            st = state[i]
            if i not in score[j]:
                end(i)
                continue
            if st["pos"] is None:                         # entering: near the cue, own heading
                st["pos"] = A + rng.normal(size=2) * spread
                d = B - st["pos"]
                st["heading"] = math.atan2(d[1], d[0]) + rng.normal() * 0.7
                st["cur"] = [st["pos"][None, :]]
            Bi = B + rng.normal(size=2) * spread             # each player lands a little off the cue
            st["pos"], st["heading"], st["toks"] = perfs[i].segment(
                grams[i], st["pos"], st["heading"], st["toks"], A, Bi, Lmm * (0.9 + 0.25 * rng.random()),
                st["cur"], land=land)
    for i in range(n):
        end(i)
    marks = []
    for li, (pts, i) in enumerate(lines):
        marks.append(Mark(pts, {"cw": np.full(len(pts), float(pens[i % len(pens)])), "role": np.ones(len(pts)),
                                "voice": np.full(len(pts), float(i)), "r": np.zeros(len(pts))},
                          {"voices": list(players), "player": int(i), "role": "performance"}))
    if src is not None:
        marks.insert(0, Mark(src, {"cw": np.full(len(src), float(min(pens))), "role": np.zeros(len(src)),
                                   "voice": np.full(len(src), -1.0), "r": np.zeros(len(src))},
                             {"voices": list(players), "role": "source"}))
    meta = {"cues": [{"t": float(t[c["i"]]), "kind": c["kind"], "hold": c["hold"]} for c in cues],
            "score": score, "lines": len(lines), "R_mm": R, "enlarge": kb / ks, "thresholds": thr,
            "blanks_mm": bl.tolist(), "source_box": list(sb) if sb else None}
    return [m.evolve(meta={"conduct": meta if k == 0 else {"n": k}}) for k, m in enumerate(marks)]


@voice("oehlen_conduct_ensemble", params=[
    P("trail", "ref", "staccato", "the dance whose hand conducts", kind="dance_trail"),
    P("effector", "choice", "rhand", "which body end conducts", choices=("lhand", "rhand", "lfoot", "rfoot", "head")),
    P("t0", "float", 5.0, "source start, s", min=0.0, max=60.0),
    P("seconds", "float", 7.0, "source length, s", min=1.0, max=30.0),
    P("players", "refs", ["trail_miner", "dance_levitation", "trail_slime"], "the players (learned hands)",
      kind="hand", min_len=1, max_len=6),
    P("pens", "floats", [1.4, 0.6, 0.3], "each player's pen, mm (player i → pens[i])"),
    P("corner", "choice", "tl", "where the conductor's line sits, small", choices=CORNERS),
    P("src_size", "float", 34.0, "its longer side, mm", min=10.0, max=120.0),
    P("enlarge", "float", 6.0, "performance ÷ source scale (capped so it fits)", min=1.0, max=12.0),
    P("place", "floats", [0.6, 0.55], "performance centre, fractions of the box"),
    P("gesture", "float", 0.6, "players' gesture scale R × box diagonal", min=0.05, max=3.0),
    P("sustain", "float", 0.3, "slow stretches get this much more line", min=0.0, max=6.0),
    P("still_q", "float", 0.12, "stop quantile", min=0.0, max=0.5),
    P("turn_deg", "float", 75.0, "turn threshold, degrees", min=10.0, max=180.0),
    P("burst_q", "float", 0.9, "burst quantile", min=0.5, max=1.0),
    P("min_gap_s", "float", 0.35, "cue spacing, s", min=0.05, max=3.0),
    P("K", "int", 16, "proposals per chunk", min=1, max=40),
    P("pull", "float", 8.0, "steering", min=0.0, max=40.0),
    P("clear", "float", 1.5, "self- and mutual avoidance, mm", min=0.0, max=20.0),
    P("chunk", "float", 0.12, "chunk, R", min=0.01, max=4.0),
    P("step", "float", 0.35, "sampling step, mm", min=0.05, max=2.0),
    P("land", "float", 0.8, "how exactly players land on the cues", min=0.0, max=1.0),
    P("corner_cost", "float", 0.4, "penalty per sharp corner in a proposal", min=0.0, max=20.0),
    P("slow_solo", "float", 0.4, "stretches slower than this rank are solos", min=0.0, max=1.0),
    P("tutti_burst", "bool", True, "a burst cue brings every player in"),
    P("blanks", "floats", [], "reserved blank discs (cx, cy, r as fractions); lines are cut there"),
    P("spread", "float", 3.0, "players land this far (σ, mm) around each cue", min=0.0, max=30.0),
    P("min_cue_mm", "float", 12.0, "cues landing closer than this to the previous one are dropped (no barbs)",
      min=0.0, max=80.0),
], doc="conduction for an ensemble: one dancer's hand cues several learned hands; who plays each stretch "
       "follows the hand's speed, stops and bursts; doubled stretches are two players, meeting at the cues")
def oehlen_conduct_ensemble(ctx, **kw):
    return ensemble(ctx, **kw)
