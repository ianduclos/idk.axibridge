# FROZEN from research commit 4aa0ed1: tools/gesture/gesture/kit/voices_machine.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Machine voices: deliberate, self-consistent machine grammars (round 9).

The round-8 "failure" — chained k-NN context throwing straight runs and
corners into a cursive drift line, which Ian called "one of the best" — is
generalised here into machine grammars that obey ONE rule everywhere
(coherent) and are not a hand (strange). Each grammar is a pure rewrite

    rewrite(points, rng, unit, opts) -> points'     (starts where `points` starts)

of a polyline, so the same rule can speak a whole line (the `machine` voice:
a learned hand's line re-spoken by the machine) or take over stretches of an
existing Mark (the `handover` modulator: the hand passes the pen to the
machine and takes it back — a conversation, never a blend).

Grammars (`GRAMMARS`):
- compass   only k headings exist (odd k: no way straight back); a turtle
            follows the source and turns only when its error exceeds unit/2
- ruler     least-squares straight runs, corners at the runs' intersections,
            each corner overshot by a draftsman's tick (out and back)
- stair     rook moves on a rotated grid of pitch `unit`: x-run, y-run, …
- koch      the source decimated to a polygon, every edge replaced
            recursively by ONE motif (drawn once per line from rng)
- lsys      the source's turns tokenised L/S/R and rewritten by `rules`,
            then drawn by a turtle at a fixed angle and step; the result is
            fitted onto the source's chord
- codebook  the source cut into unit-length tokens, k-means'd into a few
            prototypes; every token is redrawn as its nearest prototype — the
            k-NN attractor exploited on purpose: a vocabulary of 6 gestures

Channels written: `machine` (0 = the hand, i = GRAMMARS index + 1; nearest)
and `voice` (machines are appended to meta["voices"] as "machine:<id>", so
every diagram of the voice channel shows the machine speaking).
"""
from __future__ import annotations

import math

import numpy as np

from .core import P, channel_kind, fitted, modulator, voice
from .voices_base import grow

channel_kind("machine", "nearest")

GRAMMARS = ("compass", "ruler", "stair", "koch", "lsys", "codebook")


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def _arc(p: np.ndarray) -> np.ndarray:
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


def resample(p: np.ndarray, step: float) -> np.ndarray:
    p = np.asarray(p, float)
    s = _arc(p)
    L = s[-1]
    if L <= 0 or len(p) < 2:
        return p.copy()
    n = max(int(math.ceil(L / max(step, 1e-9))), 1)
    t = np.linspace(0, L, n + 1)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def rdp(p: np.ndarray, tol: float) -> np.ndarray:
    """Ramer–Douglas–Peucker vertex indices (iterative, deterministic)."""
    n = len(p)
    if n < 3:
        return np.arange(n)
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        d = p[b] - p[a]
        nd = math.hypot(*d)
        seg = p[a + 1:b] - p[a]
        if nd < 1e-12:
            dist = np.linalg.norm(seg, axis=1)
        else:
            dist = np.abs(seg[:, 0] * d[1] - seg[:, 1] * d[0]) / nd
        j = int(np.argmax(dist))
        if dist[j] > tol:
            k = a + 1 + j
            keep[k] = True
            stack += [(a, k), (k, b)]
    return np.flatnonzero(keep)


def _rot(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s], [s, c]])


def land(q: np.ndarray, A: np.ndarray, B: np.ndarray, unit: float) -> np.ndarray:
    """Make q run from A to B: a small end error is sheared out linearly in
    arc length (straight runs stay straight); a large one by a similarity on
    the chord (the machine's figure kept, rotated/scaled onto A→B)."""
    q = np.asarray(q, float)
    if len(q) < 2:
        return np.vstack([A, B])
    q = q - q[0] + A
    err = B - q[-1]
    cq, cp = q[-1] - q[0], B - A
    nq, np_ = math.hypot(*cq), math.hypot(*cp)
    if math.hypot(*err) <= 0.5 * unit or nq < 1e-9 or not 0.4 <= np_ / max(nq, 1e-9) <= 2.5:
        s = _arc(q)
        w = (s / max(s[-1], 1e-12))[:, None]
        return q + w * err
    ang = math.atan2(cp[1], cp[0]) - math.atan2(cq[1], cq[0])
    return (q - q[0]) @ _rot(ang).T * (np_ / nq) + A


def _dedupe(q: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    q = np.asarray(q, float)
    if len(q) < 2:
        return q
    keep = np.r_[True, np.linalg.norm(np.diff(q, axis=0), axis=1) > eps]
    return q[keep]


# ---------------------------------------------------------------------------
# the grammars — each obeys one rule everywhere
# ---------------------------------------------------------------------------

def g_compass(p, rng, unit, o):
    k = int(o.get("k", 5))
    off = float(o.get("phase", rng.uniform(0, 2 * math.pi / k)))
    H = off + 2 * math.pi * np.arange(k) / k
    dirs = np.column_stack([np.cos(H), np.sin(H)])
    d = unit / 10.0
    T = resample(p, d)
    n = len(T)
    look = max(int(round(unit / d)), 2)
    e = 0.5 * unit
    pos = T[0].copy()
    out = [pos.copy()]
    i = 0

    def best(excl=None):
        tgt = T[min(i + look, n - 1)] - pos
        sc = dirs @ tgt
        if excl is not None:
            sc[excl] = -np.inf
        return int(np.argmax(sc))

    h = best()
    run = 0
    for _ in range(40 * n):
        pos = pos + d * dirs[h]
        run += 1
        lo, hi = i, min(i + 4 * look, n)
        j = lo + int(np.argmin(np.linalg.norm(T[lo:hi] - pos, axis=1)))
        i = max(i, j)
        err = np.linalg.norm(T[i] - pos)
        if i >= n - 1 and err < e:
            break
        if err > e and run >= 3:
            out.append(pos.copy())
            nh = best(excl=h)
            h, run = nh, 0
    out.append(pos.copy())
    return _dedupe(np.array(out))


def g_ruler(p, rng, unit, o):
    over = float(o.get("overshoot", 0.25)) * unit
    v = rdp(p, 0.3 * unit)
    # merge runs shorter than unit/2
    keep = [v[0]]
    s = _arc(p)
    for j in v[1:-1]:
        if s[j] - s[keep[-1]] >= 0.5 * unit:
            keep.append(j)
    if s[v[-1]] - s[keep[-1]] < 0.5 * unit and len(keep) > 1:
        keep.pop()
    keep.append(v[-1])
    keep = np.array(keep)
    lines = []
    for a, b in zip(keep[:-1], keep[1:]):
        seg = p[a:b + 1]
        c = seg.mean(axis=0)
        u, sv, vt = np.linalg.svd(seg - c, full_matrices=False)
        dvec = vt[0]
        if np.dot(p[b] - p[a], dvec) < 0:
            dvec = -dvec
        lines.append((c, dvec))
    verts = [p[0]]
    for (c1, d1), (c2, d2) in zip(lines[:-1], lines[1:]):
        M = np.column_stack([d1, -d2])
        if abs(np.linalg.det(M)) < 1e-6:
            x = 0.5 * (c1 + c2)
        else:
            t = np.linalg.solve(M, c2 - c1)
            x = c1 + t[0] * d1
        verts.append(x)
    verts.append(p[-1])
    verts = np.array(verts)
    # clamp runaway intersections (near-parallel runs) to the source vertex
    for i in range(1, len(verts) - 1):
        if np.linalg.norm(verts[i] - p[keep[i]]) > 1.5 * unit:
            verts[i] = p[keep[i]]
    out = [verts[0]]
    for i in range(1, len(verts)):
        out.append(verts[i])
        if over > 0 and i < len(verts) - 1:
            dv = verts[i] - verts[i - 1]
            nv = np.linalg.norm(dv)
            if nv > 1e-9:
                out.append(verts[i] + over * dv / nv)
                out.append(verts[i])
    return np.array(out)


def g_stair(p, rng, unit, o):
    a = float(o.get("phase", rng.uniform(0, math.pi / 2)))
    g = 0.6 * unit
    R = _rot(-a)
    q = (p - p[0]) @ R.T
    T = resample(q, g / 6)
    cells = np.round(T / g).astype(int)
    out = [np.zeros(2)]
    cur = np.zeros(2, int)
    for c in cells[1:]:
        if np.all(c == cur):
            continue
        dx, dy = c - cur
        first_x = abs(dx) >= abs(dy)
        if first_x:
            out.append(np.array([c[0], cur[1]], float) * g)
        else:
            out.append(np.array([cur[0], c[1]], float) * g)
        out.append(c.astype(float) * g)
        cur = c
    q2 = _dedupe(np.array(out))
    # merge collinear vertices
    if len(q2) > 2:
        d = np.diff(q2, axis=0)
        cr = d[:-1, 0] * d[1:, 1] - d[:-1, 1] * d[1:, 0]
        q2 = np.vstack([q2[:1], q2[1:-1][np.abs(cr) > 1e-9], q2[-1:]])
    return q2 @ R + p[0]


def _motif(rng, o):
    n = int(o.get("motif_pts", 3))
    xs = np.sort(rng.uniform(0.15, 0.85, n))
    ys = rng.uniform(-0.38, 0.38, n)
    ys[np.argmax(np.abs(ys))] = math.copysign(0.38, ys[np.argmax(np.abs(ys))])
    return np.vstack([[0, 0], np.column_stack([xs, ys]), [1, 0]])


def g_koch(p, rng, unit, o):
    depth = int(o.get("depth", 2))
    mot = _motif(rng, o)
    v = rdp(p, 0.4 * unit)
    poly = p[v]

    def sub(a, b, dep, sign):
        d = b - a
        L = math.hypot(*d)
        if dep == 0 or L < 0.35 * unit:
            return [b]
        nrm = np.array([-d[1], d[0]])
        pts = [a + m[0] * d + sign * m[1] * nrm for m in mot]
        out = []
        for i in range(len(pts) - 1):
            out += sub(pts[i], pts[i + 1], dep - 1, sign)
        return out

    out = [poly[0]]
    for i in range(len(poly) - 1):
        out += sub(poly[i], poly[i + 1], depth, 1.0 if i % 2 == 0 else -1.0)
    return np.array(out)


def _symbols(p, unit, t_deg=15.0):
    v = rdp(p, 0.25 * unit)
    q = p[v]
    if len(q) < 3:
        return "S"
    d = np.diff(q, axis=0)
    h = np.arctan2(d[:, 1], d[:, 0])
    turn = (np.diff(h) + np.pi) % (2 * np.pi) - np.pi
    t = math.radians(t_deg)
    return "".join("L" if x > t else "R" if x < -t else "S" for x in turn)


def _rules(text: str) -> dict:
    out = {}
    for part in text.replace(" ", "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            if k in ("L", "R", "S") and all(c in "LRS" for c in v):
                out[k] = v
    return out


def g_lsys(p, rng, unit, o):
    rules = _rules(str(o.get("rules", "L=LSR,R=RRS,S=SL")))
    s = _symbols(p, unit)[:60] or "S"
    for _ in range(int(o.get("depth", 2))):
        s = "".join(rules.get(c, c) for c in s)
        if len(s) > 900:
            s = s[:900]
            break
    A = math.radians(float(o.get("angle", 72.0)))
    step = 0.5 * unit
    pos, h = np.zeros(2), 0.0
    out = [pos.copy()]
    for c in s:
        if c == "L":
            h -= A
        elif c == "R":
            h += A
        pos = pos + step * np.array([math.cos(h), math.sin(h)])
        out.append(pos.copy())
    q = np.array(out)
    # orient the figure along the source's chord; `land` fits it on
    return q


def g_codebook(p, rng, unit, o):
    K = int(o.get("k", 6))
    m = 12
    T = resample(p, unit / m)
    n_tok = (len(T) - 1) // m
    if n_tok < 2:
        return T
    toks, heads = [], []
    for i in range(n_tok):
        seg = T[i * m:(i + 1) * m + 1]
        d = seg - seg[0]
        h0 = math.atan2(*(seg[1] - seg[0])[::-1])
        toks.append((d @ _rot(-h0).T).ravel())
        heads.append(h0)
    X = np.array(toks)
    K = min(K, len(X))
    C = X[rng.choice(len(X), K, replace=False)]
    for _ in range(25):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        for k in range(K):
            if np.any(lab == k):
                C[k] = X[lab == k].mean(axis=0)
    lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
    pos = T[0].copy()
    out = [pos.copy()]
    for i in range(n_tok):
        shape = C[lab[i]].reshape(-1, 2) @ _rot(heads[i]).T
        out += list(shape[1:] + pos)
        pos = out[-1].copy()
    if len(T) - 1 > n_tok * m:
        out += list(T[n_tok * m + 1:] - T[n_tok * m] + pos)
    return np.array(out)


REWRITE = {"compass": g_compass, "ruler": g_ruler, "stair": g_stair, "koch": g_koch, "lsys": g_lsys,
           "codebook": g_codebook}


def speak(grammar: str, points, rng, unit: float, opts: dict | None = None, land_end: bool = True) -> np.ndarray:
    """Re-speak `points` in a machine grammar; starts at points[0] and (if
    land_end) ends at points[-1]."""
    p = _dedupe(np.asarray(points, float))
    if len(p) < 3 or _arc(p)[-1] < 1e-9:
        return p.copy()
    q = REWRITE[grammar](p, rng, float(unit), dict(opts or {}))
    q = _dedupe(np.asarray(q, float))
    if len(q) < 2:
        q = p[[0, -1]]
    return land(q, p[0], p[-1], unit) if land_end else q - q[0] + p[0]


# ---------------------------------------------------------------------------
# params shared by the voice and the modulator
# ---------------------------------------------------------------------------

_OPTS = [
    P("k", "int", 5, "compass: headings / codebook: prototypes", min=2, max=16),
    P("angle", "float", 72.0, "lsys: turtle turn, degrees", min=5.0, max=175.0),
    P("rules", "str", "L=LSR,R=RRS,S=SL", "lsys: rewrite rules over L/S/R"),
    P("depth", "int", 2, "koch / lsys: rewrite depth", min=0, max=4),
    P("overshoot", "float", 0.25, "ruler: corner tick, in units", min=0.0, max=1.5),
]


def _opts(k, angle, rules, depth, overshoot):
    return {"k": k, "angle": angle, "rules": rules, "depth": depth, "overshoot": overshoot}


@voice("machine", params=[
    P("grammar", "choice", "compass", "the machine rule", choices=GRAMMARS),
    P("hand", "ref", "matisse", "the hand whose line the machine listens to", kind="hand"),
    P("length", "float", 4.0, "line length in reference lengths", min=0.2, max=12.0),
    P("unit", "float", 0.035, "the machine's unit, as a share of the line's bbox diagonal (codebook ×3)",
      min=0.005, max=0.3),
    P("source_part", "int", None, "grow the listened-to line at the seed of this part (sheet seed + n) "
      "instead of this part's, so several machines can speak the SAME line", min=0, max=999, optional=True),
    *_OPTS], doc="a learned hand's line re-spoken by one machine rule")
def machine(ctx, *, grammar, hand, length, unit, source_part, k, angle, rules, depth, overshoot):
    if source_part is not None:
        from dataclasses import replace  # noqa: PLC0415
        ctx = replace(ctx, seed=int(ctx.sheet_seed) + int(source_part))
    pts, ch, meta = grow(ctx, [hand], length=length, blend="mixture", joins="smooth", plateau=0.12)
    diag = float(np.hypot(*np.ptp(pts, axis=0)))
    u = unit * diag * (3.0 if grammar == "codebook" else 1.0)
    q = speak(grammar, pts, ctx.rng("speak", grammar), u, _opts(k, angle, rules, depth, overshoot),
              land_end=grammar != "lsys")
    gi = GRAMMARS.index(grammar) + 1
    meta = {**meta, "voices": [f"machine:{grammar}"], "machines": [grammar], "listens_to": hand,
            "unit_px": u}
    return fitted([q], ctx.box, [{"voice": np.zeros(len(q)), "machine": np.full(len(q), float(gi))}], [meta])


# ---------------------------------------------------------------------------
# handover: the machine takes stretches of an existing line
# ---------------------------------------------------------------------------

def _kappa(p: np.ndarray, step: float) -> np.ndarray:
    d = np.diff(p, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    k = np.gradient(th) / step
    return np.r_[k, k[-1:]]


def choose_stretches(mark, rng, *, share: float, stretch: float, at: str) -> list[tuple[float, float]]:
    """Non-overlapping (s0, s1) arc intervals handed to the machine."""
    s = mark.arclength()
    L = float(s[-1])
    if L <= 0 or share <= 0:
        return []
    ln = min(stretch, 0.45 * L)
    n = max(int(round(share * L / ln)), 1)
    cands: list[float] = []
    if at == "seams" and "voice" in mark.channels:
        v = mark.channels["voice"]
        cands = [float(s[i]) for i in np.flatnonzero(np.diff(v) != 0)]
    elif at == "straight":
        step = 0.5
        q = mark.resampled(step)
        kq = np.abs(_kappa(q.points, step))
        from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
        ks = gaussian_filter1d(kq, ln / step / 3, mode="nearest")
        sq = q.arclength()
        order = np.argsort(ks, kind="stable")
        cands = [float(sq[i]) for i in order]
    elif at == "random":
        cands = list(np.sort(rng.uniform(0.5 * ln, L - 0.5 * ln, 4 * n)))
        rng.shuffle(cands)
    if at in ("seams",) and len(cands) < n:
        cands += list(np.linspace(0, L, n + 2)[1:-1])
    if at == "even" or not cands:
        cands = list(np.linspace(0, L, n + 2)[1:-1])
    chosen: list[tuple[float, float]] = []
    for c in cands:
        a, b = max(c - ln / 2, 0.0), min(c + ln / 2, L)
        if b - a < 0.3 * ln:
            continue
        if any(not (b + 0.4 * ln < x0 or a - 0.4 * ln > x1) for x0, x1 in chosen):
            continue
        chosen.append((a, b))
        if len(chosen) >= n:
            break
    return sorted(chosen)


def hand_over(mark, intervals, grammars, rng, unit, opts):
    """One Mark with the given arc intervals re-spoken by machines (cycled)."""
    if not intervals:
        return mark.evolve(channels={"machine": np.zeros(len(mark))})
    s = mark.arclength()
    voices = list(mark.meta.get("voices", ["hand"]))
    vidx = {}
    for g in grammars:
        name = f"machine:{g}"
        if name not in voices:
            voices.append(name)
        vidx[g] = voices.index(name)
    pts, s_src, mach, vo = [], [], [], []
    base_v = mark.channels.get("voice", np.zeros(len(mark)))
    cur = 0.0
    log = []
    for j, (a, b) in enumerate(intervals):
        g = grammars[j % len(grammars)]
        sel = (s >= cur) & (s < a)
        pts.append(mark.points[sel]); s_src.append(s[sel])
        mach.append(np.zeros(sel.sum())); vo.append(base_v[sel])
        A = np.array([np.interp(a, s, mark.points[:, 0]), np.interp(a, s, mark.points[:, 1])])
        B = np.array([np.interp(b, s, mark.points[:, 0]), np.interp(b, s, mark.points[:, 1])])
        inner = (s > a) & (s < b)
        seg = np.vstack([A, mark.points[inner], B])
        q = speak(g, seg, rng, unit, opts)
        sq = _arc(q)
        ss = a + (b - a) * sq / max(sq[-1], 1e-12)
        pts.append(q); s_src.append(ss)
        mach.append(np.full(len(q), float(GRAMMARS.index(g) + 1))); vo.append(np.full(len(q), float(vidx[g])))
        log.append({"s0": round(a, 3), "s1": round(b, 3), "grammar": g, "n": int(len(q))})
        cur = b
    sel = s > cur
    pts.append(mark.points[sel]); s_src.append(s[sel])
    mach.append(np.zeros(sel.sum())); vo.append(base_v[sel])
    P_ = np.vstack([x for x in pts if len(x)])
    S_ = np.concatenate(s_src)
    keep = np.r_[True, np.linalg.norm(np.diff(P_, axis=0), axis=1) > 1e-9]
    machines = sorted(set(mark.meta.get("machines", [])) | set(grammars), key=GRAMMARS.index)
    return mark.remap(S_[keep], points=P_[keep],
                      channels={"machine": np.concatenate(mach)[keep], "voice": np.concatenate(vo)[keep]},
                      meta={"voices": voices, "machines": machines,
                            "handover": list(mark.meta.get("handover", [])) + log})


@modulator("handover", params=[
    P("a", "choice", "ruler", "first machine", choices=GRAMMARS),
    P("b", "choice", "compass", "second machine (alternates with a; 'none' = a only)", choices=(*GRAMMARS, "none")),
    P("share", "float", 0.35, "share of the line handed to the machines", min=0.0, max=0.95),
    P("stretch", "float", 30.0, "length of one machine stretch, mm", min=2.0, max=400.0),
    P("at", "choice", "seams", "where: seams (where the drift changes hand) | even | random | straight "
      "(where the hand is straightest — the attractor's own taste)", choices=("seams", "even", "random", "straight")),
    P("unit", "float", 3.0, "machine unit, mm", min=0.3, max=40.0),
    *_OPTS], doc="the hand passes the pen to a machine for stretches and takes it back")
def handover(ctx, marks, *, a, b, share, stretch, at, unit, k, angle, rules, depth, overshoot):
    grammars = [a] if b == "none" else [a, b]
    opts = _opts(k, angle, rules, depth, overshoot)
    out = []
    for i, m in enumerate(marks):
        if len(m) < 3 or m.length() <= 0:
            out.append(m.evolve(channels={"machine": np.zeros(len(m))}))
            continue
        rng = ctx.rng("handover", i)
        iv = choose_stretches(m, rng, share=share, stretch=stretch, at=at)
        out.append(hand_over(m, iv, grammars, rng, unit, opts))
    return out
