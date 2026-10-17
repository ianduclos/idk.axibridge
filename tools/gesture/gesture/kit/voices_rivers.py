"""River voices (round 11, exploration 1a, hands_rivers): loops that close on
themselves, and braided bundles. results/hands_rivers-2026-10-17.md.

A clothoid grammar (the `hand` voice) learns curvature along arc length but
cannot promise that a line comes back to where it started, and it draws one
line at a time. Two river behaviours need more:

`river_loops`   cut-off loops. The loop SHAPES are learned: library kind
                `river_loops` holds turning functions θ(u) of real oxbow
                outlines (OSM water=oxbow, closed) and of real cut-off bends
                (Li et al. 2026: neck and chute centrelines, open, nearly
                closed). A new loop = one training profile, nudged toward a
                near neighbour, jittered, integrated, and closed exactly
                (oxbow) or left with its own neck gap (neck). Modes:
                  knot    the host line, at its sharpest bends, runs once
                          round a closing loop and goes on (one contiguous
                          line; the bend pinching off as it happens)
                  beside  the host line with abandoned loops left beside its
                          bends, on the outer side (separate marks)
                  alone   loops only, scattered: the loop hand by itself
`river_braid`   a braided bundle. A backbone from any hand; K threads; each
                adjacent pair of threads opens and closes a run of islands
                (lenses) whose length/width and half-width profile along the
                long axis come from the Anavilhanas islands (library kind
                `river_braid`). Threads touch at the nodes between islands —
                they split and rejoin — and every thread is one contiguous
                line. Writes `emphasis` (a bump at every split, on one thread
                of the pair, for dev_beads: beads at the splits) and `thread`.

Host lines are the research drift line (`voices_base.grow`), so every
library hand can carry loops or a braid. Determinism: ctx.rng(tags) only.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from . import library as L
from .core import P, channel_kind, fitted, voice
from .voices_base import grow

N_PROFILE = 128
channel_kind("thread", "nearest")


# ---------------------------------------------------------------------------
# library kinds
# ---------------------------------------------------------------------------

@L.loader("river_loops")
def _load_loops(entry: dict, folder):
    return {k: np.asarray(v) for k, v in L.read_npz(folder / entry["files"]["loops"]).items()}


@L.loader("river_braid")
def _load_braid(entry: dict, folder):
    return {k: np.asarray(v) for k, v in L.read_npz(folder / entry["files"]["braid"]).items()}


# ---------------------------------------------------------------------------
# turning functions (shared with experiments/hands_rivers.py)
# ---------------------------------------------------------------------------

def resample_closed(p: np.ndarray, n: int = N_PROFILE) -> np.ndarray:
    """n points equally spaced along a closed curve (first point not repeated)."""
    q = np.vstack([p, p[:1]]) if not np.allclose(p[0], p[-1]) else np.asarray(p, float)
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
    t = np.linspace(0.0, s[-1], n + 1)[:-1]
    return np.column_stack([np.interp(t, s, q[:, 0]), np.interp(t, s, q[:, 1])])


def resample_open(p: np.ndarray, n: int = N_PROFILE) -> np.ndarray:
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    t = np.linspace(0.0, s[-1], n)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def turning(q: np.ndarray, closed: bool) -> np.ndarray:
    """Tangent angle per sample, unwrapped, starting at 0, turning
    counter-clockwise positive (a clockwise loop is mirrored first by the
    caller via `orient`)."""
    d = np.roll(q, -1, axis=0) - q if closed else np.gradient(q, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    return th - th[0]


def loop_profile(p: np.ndarray, closed: bool, n: int = N_PROFILE) -> tuple[np.ndarray, float]:
    """(φ(u), extra): closed → φ = θ(u) − 2πu for the loop traced turning
    positive (extra = elongation: sqrt of the outline's second-moment
    eigenvalue ratio, arc-length weighted — below the axis ratio); open →
    θ(u) (extra = gap / length)."""
    if closed:
        q = resample_closed(p, n)
        th = turning(q, True)
        if th[-1] + (th[1] - th[0]) < 0:            # clockwise → trace it the other way
            q = q[::-1]
            th = turning(q, True)
        u = np.arange(n) / n
        c = q - q.mean(0)
        ev = np.linalg.eigvalsh(np.cov(c.T))
        return th - 2 * np.pi * u, float(math.sqrt(ev[1] / max(ev[0], 1e-12)))
    q = resample_open(p, n)
    th = turning(q, False)
    if th[-1] < 0:
        th = -th
    L_ = float(np.sum(np.linalg.norm(np.diff(q, axis=0), axis=1)))
    return th, float(np.linalg.norm(q[-1] - q[0]) / max(L_, 1e-9))


def integrate(theta: np.ndarray, length: float = 1.0, close: bool = False) -> np.ndarray:
    """Points from tangent angles (uniform steps summing to `length`).
    close=True: the end returns to the start (the closure gap is taken out
    as a linear ramp in the TANGENT VECTORS, so the curvature character
    stays and no corner appears)."""
    n = len(theta)
    h = length / n
    v = np.column_stack([np.cos(theta), np.sin(theta)]) * h
    if close:
        v = v - v.sum(0) / n
    p = np.vstack([[0.0, 0.0], np.cumsum(v, axis=0)])
    return p


def sample_loop(data: dict, family: str, rng, *, jitter: float = 0.15, mix: float = 0.35) -> tuple[np.ndarray, str]:
    """One new loop in unit perimeter, as (points, family). Nonparametric:
    a training profile, moved toward one of its 3 nearest neighbours by a
    random share ≤ mix, plus smooth jitter (radians, sd `jitter`)."""
    fams = ("oxbow", "neck") if family == "both" else (family,)
    fam = fams[int(rng.integers(len(fams)))]
    X = data[f"{fam}_phi"]
    i = int(rng.integers(len(X)))
    d = np.linalg.norm(X - X[i], axis=1)
    nn = np.argsort(d, kind="stable")[1:4]
    j = int(nn[int(rng.integers(len(nn)))]) if len(nn) else i
    a = float(rng.uniform(0.0, mix))
    phi = (1 - a) * X[i] + a * X[j]
    n = len(phi)
    noise = gaussian_filter1d(rng.normal(0.0, 1.0, n), 6.0, mode="wrap" if fam == "oxbow" else "nearest")
    phi = phi + jitter * noise / max(np.std(noise), 1e-9)
    if fam == "oxbow":
        th = phi + 2 * np.pi * np.arange(n) / n
        pts = integrate(th, 1.0, close=True)
    else:
        pts = integrate(phi - phi[0], 1.0, close=False)
    return pts, fam


def _place(pts: np.ndarray, at: np.ndarray, heading: float, scale: float, mirror: bool) -> np.ndarray:
    """Loop points (start at origin, start tangent along +x) scaled, mirrored
    (turn the other way), rotated to `heading`, moved to `at`."""
    q = pts * scale
    if mirror:
        q = q * np.array([1.0, -1.0])
    t0 = q[min(3, len(q) - 1)] - q[0]
    a = heading - math.atan2(t0[1], t0[0])
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    return (q - q[0]) @ R.T + at


def _curv(p: np.ndarray, sig: float) -> tuple[np.ndarray, np.ndarray]:
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    ps = gaussian_filter1d(p, sig, axis=0, mode="nearest")
    d1 = np.gradient(ps, axis=0)
    d2 = np.gradient(d1, axis=0)
    k = (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / np.maximum(np.linalg.norm(d1, axis=1) ** 3, 1e-12)
    return k, s


def _apices(p: np.ndarray, n: int, min_gap: float, rng) -> list[int]:
    """Indices of the n sharpest bends of a line, at least min_gap (px of
    arc) apart, never at the ends."""
    k, s = _curv(p, 4.0)
    order = np.argsort(-np.abs(k), kind="stable")
    keep: list[int] = []
    L_ = s[-1]
    for i in order:
        if s[i] < 0.06 * L_ or s[i] > 0.94 * L_:
            continue
        if all(abs(s[i] - s[j]) >= min_gap for j in keep):
            keep.append(int(i))
        if len(keep) >= n:
            break
    return sorted(keep)


# ---------------------------------------------------------------------------
# river_loops
# ---------------------------------------------------------------------------

@voice("river_loops", params=[
    P("loops", "ref", "river_cutoffs", "the learned loop shapes (oxbow outlines, cut-off bends)", kind="river_loops"),
    P("family", "choice", "oxbow", "oxbow: closed lake outlines | neck: the bend at the moment of cut-off "
      "(open, a small neck gap) | both", choices=("oxbow", "neck", "both")),
    P("mode", "choice", "knot", "knot: the host line runs round each loop and goes on (contiguous) | beside: "
      "abandoned loops beside the host's bends | alone: loops only", choices=("knot", "beside", "alone")),
    P("host", "ref", "river_meander", "the hand drawing the host line (knot / beside)", kind="hand"),
    P("length", "float", 5.0, "host line length, R", min=0.2, max=12.0),
    P("n", "int", 6, "how many loops", min=0, max=60),
    P("size", "float", 0.8, "loop perimeter in R (alone) or × the host's mean bend spacing (knot/beside)",
      min=0.02, max=2.0),
    P("size_sd", "float", 0.35, "log-normal spread of loop sizes", min=0.0, max=1.5),
    P("gap", "float", 0.12, "beside: distance from the bend, × loop perimeter", min=0.0, max=1.0),
    P("jitter", "float", 0.15, "shape jitter (rad) on the learned turning function", min=0.0, max=1.0),
    P("loop_r", "float", 0.0, "regime written on loop points (0 wire, 1 nib, 2 mass); the host stays wire — "
      "loops as the stresses of another hand", min=0.0, max=2.0),
], doc="cut-off loops learned from oxbows and cut-off bends: a host line that ties them, leaves them, or loops alone")
def river_loops(ctx, *, loops, family, mode, host, length, n, size, size_sd, gap, jitter, loop_r):
    data = ctx.use("river_loops", loops)
    rng = ctx.rng("loops")
    meta = {"voices": [host] if mode != "alone" else [f"loops:{loops}"], "loops": loops, "family": family,
            "mode": mode, "library": [{"kind": "river_loops", "id": loops}]}
    if mode == "alone":
        R = 1000.0
        lines, chans, metas = [], [], []
        placed: list[tuple[np.ndarray, float]] = []
        for i in range(n):
            per = R * size * math.exp(size_sd * rng.normal())
            pts, fam = sample_loop(data, family, rng, jitter=jitter)
            for _ in range(30):
                at = rng.uniform(0, R, 2)
                q = _place(pts, at, rng.uniform(0, 2 * np.pi), per, bool(rng.integers(2)))
                c, r = q.mean(0), 0.5 * np.ptp(q, axis=0).max()
                if all(np.linalg.norm(c - c2) > 0.9 * (r + r2) for c2, r2 in placed):
                    break
            placed.append((q.mean(0), 0.5 * np.ptp(q, axis=0).max()))
            lines.append(q)
            chans.append({"voice": np.zeros(len(q)), "loop": np.ones(len(q)), "r": np.full(len(q), loop_r)})
            metas.append({**meta, "family_drawn": fam})
        return fitted(lines, ctx.box, chans, metas) if lines else []
    hp, hch, hmeta = grow(ctx, [host], length=length, blend="mixture", joins="smooth", plateau=0.12)
    hp = np.asarray(hp, float)
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(hp, axis=0), axis=1))]
    spacing = s[-1] / max(n, 1)
    k, _ = _curv(hp, 4.0)
    idx = _apices(hp, n, 0.5 * spacing, rng)
    meta.update({k_: v for k_, v in hmeta.items() if k_ not in ("voices", "library")})
    meta["library"] = hmeta["library"] + meta["library"]
    if mode == "knot":
        pieces, flags = [], []
        prev = 0
        for i in idx:
            per = spacing * size * math.exp(size_sd * rng.normal())
            pts, fam = sample_loop(data, family, rng, jitter=jitter)
            t = hp[min(i + 2, len(hp) - 1)] - hp[max(i - 2, 0)]
            q = _place(pts, hp[i], math.atan2(t[1], t[0]), per, mirror=bool(k[i] < 0))
            pieces += [hp[prev:i + 1], q[1:]]
            flags += [np.zeros(i + 1 - prev), np.ones(len(q) - 1)]
            if fam == "neck":            # the line jumps the neck back to its course: a short chute
                pieces.append(hp[i:i + 1])
                flags.append(np.ones(1))
            prev = i + 1
        pieces.append(hp[prev:])
        flags.append(np.zeros(len(hp) - prev))
        P_ = np.vstack(pieces)
        F = np.concatenate(flags)
        # the regime swells into a loop and out of it over a few samples, never a step
        r = loop_r * np.clip(gaussian_filter1d(F, 4.0, mode="nearest") * 1.6, 0, 1)
        return fitted([P_], ctx.box, [{"voice": np.zeros(len(P_)), "loop": F, "r": r}], [meta])
    # beside: abandoned loops on the outer side of each bend
    lines = [hp]
    chans = [{"voice": np.zeros(len(hp)), "loop": np.zeros(len(hp)), "r": np.zeros(len(hp))}]
    for i in idx:
        per = spacing * size * math.exp(size_sd * rng.normal())
        pts, fam = sample_loop(data, family, rng, jitter=jitter)
        t = hp[min(i + 2, len(hp) - 1)] - hp[max(i - 2, 0)]
        t = t / max(np.linalg.norm(t), 1e-9)
        nrm = np.array([-t[1], t[0]]) * (-1.0 if k[i] > 0 else 1.0)     # outer side of the bend
        q = _place(pts, np.zeros(2), math.atan2(t[1], t[0]), per, bool(rng.integers(2)))
        q = q - q.mean(0)
        ext = float(np.max(q @ -nrm))
        q = q + hp[i] + nrm * (ext + gap * per)
        lines.append(q)
        chans.append({"voice": np.zeros(len(q)), "loop": np.ones(len(q)), "r": np.full(len(q), loop_r)})
    return fitted(lines, ctx.box, chans, [meta] * len(lines))


# ---------------------------------------------------------------------------
# river_braid
# ---------------------------------------------------------------------------

def _lens_run(L_: float, data: dict, rng, b: float, node: float, open_p: float, smooth: float = 0.0) -> np.ndarray:
    """Gap between two adjacent threads along s ∈ [0, L_] (px): a run of
    islands. Each island: length = aspect × width (aspect drawn from the
    data), width ≤ 2b, half-width profile along its long axis from a real
    island (blunt head, tapering tail as the data has it); `node` px of
    contact between islands; with prob 1 − open_p a stretch stays closed
    (the two threads run as one)."""
    n = 512
    g = np.zeros(n)
    u = np.linspace(0, L_, n)
    asp, prof = data["aspect"], data["profile"]
    x = float(rng.uniform(0, 0.4)) * b
    while x < L_:
        wid = float(2 * b * rng.uniform(0.35, 1.0))
        a = float(asp[int(rng.integers(len(asp)))])
        ln = wid * a
        if rng.random() < open_p:
            pr = prof[int(rng.integers(len(prof)))]
            if smooth > 0:      # the real outlines' bays and spits, eased (ends stay closed)
                pr = gaussian_filter1d(np.r_[0.0, pr, 0.0], smooth, mode="constant")[1:-1]
                pr = pr / max(float(pr.max()), 1e-9)
            if rng.random() < 0.5:
                pr = pr[::-1]
            m = (u >= x) & (u <= x + ln)
            if m.any():
                t = (u[m] - x) / ln
                g[m] = np.maximum(g[m], wid * np.interp(t, np.linspace(0, 1, len(pr)), pr))
        x += ln + node * float(rng.uniform(0.5, 1.5))
    return g


@voice("river_braid", params=[
    P("braid", "ref", "river_anavilhanas", "island statistics (aspect, half-width profiles)", kind="river_braid"),
    P("host", "ref", "river_bend", "the hand drawing the backbone", kind="hand"),
    P("length", "float", 3.0, "backbone length, R", min=0.2, max=12.0),
    P("threads", "int", 4, "how many threads (contiguous lines)", min=2, max=9),
    P("width", "float", 0.05, "bundle half-width per thread gap, R", min=0.005, max=0.3),
    P("node", "float", 3.0, "contact length where threads touch, × gap half-width", min=0.0, max=6.0),
    P("open", "float", 0.6, "share of stretches where a pair of threads opens an island", min=0.0, max=1.0),
    P("wander", "float", 0.15, "each thread's own small meander, × gap half-width", min=0.0, max=1.0),
    P("smooth", "float", 0.0, "ease the island outlines (profile smoothing, bins of 32; 0 = as measured)",
      min=0.0, max=8.0),
], doc="a braided bundle: threads that split around learned island lenses and rejoin")
def river_braid(ctx, *, braid, host, length, threads, width, node, open, wander, smooth):
    data = ctx.use("river_braid", braid)
    rng = ctx.rng("braid")
    hp, _, hmeta = grow(ctx, [host], length=length, blend="mixture", joins="smooth", plateau=0.12)
    hp = np.asarray(hp, float)
    R = float(hmeta["ref_length_px"])
    b = width * R
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(hp, axis=0), axis=1))]
    L_ = float(s[-1])
    sm = gaussian_filter1d(hp, max(2.0 * b / max(np.median(np.diff(s)), 1e-9), 1.0), axis=0, mode="nearest")
    t = np.gradient(sm, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
    nrm = np.column_stack([-t[:, 1], t[:, 0]])
    uu = np.linspace(0, L_, 512)
    gaps = [np.interp(s, uu, _lens_run(L_, data, rng, b, node * b, open, smooth)) for _ in range(threads - 1)]
    off = np.zeros((threads, len(s)))
    for j, g in enumerate(gaps):
        off[j + 1] = off[j] + g
    off -= off.mean(0)
    # taper the bundle in and out over the first / last 4 % so it starts and ends as one line
    ramp = np.clip(np.minimum(s, L_ - s) / (0.04 * L_), 0, 1)
    lines, chans = [], []
    # emphasis: a bump at every SPLIT (a gap opening from contact), on the thread to its left only,
    # so a bead renderer puts one bead per split
    emph = np.zeros((threads, len(s)))
    for j, g in enumerate(gaps):
        op = (g > 0.02 * b).astype(float)
        split = np.flatnonzero(np.diff(op) > 0) + 1
        e = np.zeros(len(s))
        e[split] = 1.0
        emph[j] = gaussian_filter1d(e, 3.0, mode="nearest")
    emph = emph / max(float(emph.max()), 1e-9)
    for j in range(threads):
        wn = gaussian_filter1d(rng.normal(0, 1, len(s)), 25.0)
        wn = wander * b * wn / max(np.std(wn), 1e-9)
        # a thread wanders only where it is apart from its neighbours, so the nodes stay touching
        apart = np.minimum(gaps[j - 1] if j > 0 else gaps[0], gaps[j] if j < threads - 1 else gaps[-1])
        o = (off[j] + wn * np.clip(apart / b, 0, 1)) * ramp
        P_ = hp + nrm * o[:, None]
        lines.append(P_)
        chans.append({"voice": np.zeros(len(P_)), "thread": np.full(len(P_), float(j)),
                      "emphasis": emph[j]})
    meta = {"voices": [host], "braid": braid, "threads": threads,
            "library": hmeta["library"] + [{"kind": "river_braid", "id": braid}],
            "ref_length_px": R}
    return fitted(lines, ctx.box, chans, [meta] * len(lines))
