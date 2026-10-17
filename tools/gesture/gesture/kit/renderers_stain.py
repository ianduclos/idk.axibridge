"""Mass from real stains (round 12, thread 3 `stain`, 2026-10-17).

A line that slows bleeds into the cloth. Where the pen dwells longer than
its own pace, ink wicks out through a woven medium (Washburn: wicked
distance ∝ √time) and the mass that forms is drawn by the SAME contiguous
line — never hatching, never a fill pattern.

The finished grammar (schedule `passes`, tide `rim`, the defaults): the line
arrives at the stain's edge, goes once round it (thin, rough, whole), then
sweeps the tide line as arcs back and forth over part of the ring — every
pass re-pinned somewhere else (stick-slip), so the passes cross instead of
nesting into contour lines — returns to where it came in, and goes on
THROUGH the stain along its own path (a dancer's pause shows inside as the
hand's own jitter). The longer the dwell, the bigger the stain and the more
of its dark ring closes (arc_min → arc_max): small hesitations leave open
crescents, long stillness a nearly closed ring.

From the corpus (library `stain/stain_fabric`, statistics only, measured by
`experiments/stain_measure.py` from 755 stains of the Fabric Stain Dataset,
which has boxes but no masks):

- the darkness profile: "mesa" stains (90 %: dark to a steep edge) vs tide
  lines (10 %: a dark ring at r ≈ 0.7–0.95 R round a core at 0.66 of it);
- the tide line is a CRESCENT: the dark ring covers a median 63 % of the
  circumference (arc_max 0.75 by default, a little above, on purpose);
- front roughness: 0.071 R median (IQR 0.036–0.12), spectral slope −2.5;
  the medium reproduces it (fiber 0.45 → 0.067, slope −2.7; the default
  fiber 0.3 → ≈0.045, the smoother quartile, for rounder beads);
- weave anisotropy is weak corpus-wide (median 1.03); thread `arms` exist
  only in a coarse-weave subset and are kept as an option (a dud: shards);
- satellites at 1.1–2.6 R, tiny (median 0.6 % of the main area) — off by
  default (they read as specks on the line).

The medium: a first-passage (Dijkstra, 16-neighbour) arrival field through a
weave — warp and weft threads with log-normal conductance over fibre-scale
noise. One weave per sheet (`ctx.sheet_seed`).

Where the line slows comes from its own clock: `dance_t` when the voice has
it (a dancer's pauses), else the 2/3 power law of drawing movements
(speed ∝ κ^-1/3: a hand lingers in its tight turns). Only time per mm above
(1 + wet) × the part's median counts.

Other schedules are kept as evidence: `density` and `pinned` (spiral laps
of the fronts — they read as a topographic map / tree rings), `iso`.

- renderer `stain`: line → stain → line, one polyline per mark.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from .core import Ink, P, renderer

# 16-neighbourhood (half of it; edges are added both ways)
_OFFS = [(0, 1), (1, 0), (1, 1), (1, -1), (1, 2), (2, 1), (1, -2), (2, -1)]


# ---------------------------------------------------------------------------
# the woven medium and the arrival field
# ---------------------------------------------------------------------------

def _rot(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s], [s, c]])


def _thread_g(sheet_seed: int, axis: int, idx: np.ndarray, sigma: float, weave: float, arms: float,
              arm_p: float) -> np.ndarray:
    """Per-thread conductance, a pure function of (sheet seed, axis, thread
    index): every stain on the sheet meets the same threads. Most threads
    conduct a little (weave × log-normal); a few (arm_p) are loose, wicking
    threads that carry ink far ahead of the front (arms)."""
    out = np.empty(len(idx))
    for k, i in enumerate(idx):
        r = np.random.default_rng([int(sheet_seed) & 0x7FFFFFFF, axis, int(i) + 100000])
        g = weave * np.exp(sigma * r.standard_normal() - 0.5 * sigma * sigma)
        if r.random() < arm_p:
            g += arms * (0.5 + r.random())
        out[k] = g
    return out


class Medium:
    """A patch of the woven medium in the WEAVE frame: grid, fibre-noise cost
    and thread conductances, as a sparse graph (16-neighbour). Built once per
    stain; `field` then runs one Dijkstra per set of sources."""

    def __init__(self, lo, hi, *, h, period, weave, fiber, elong, sheet_seed, rng, arms=0.0, arm_p=0.08):
        self.h = h
        self.lo = np.asarray(lo, float)
        nx, ny = int(np.ceil((hi[0] - lo[0]) / h)) + 1, int(np.ceil((hi[1] - lo[1]) / h)) + 1
        self.nx, self.ny = nx, ny
        xs = lo[0] + np.arange(nx) * h
        ys = lo[1] + np.arange(ny) * h
        # fibre noise (correlation ≈ half a thread period)
        z = ndi.gaussian_filter(rng.standard_normal((ny, nx)), max(0.6, 0.45 * period / h), mode="reflect")
        z = (z - z.mean()) / max(z.std(), 1e-9)
        cost = np.exp(fiber * z)
        # threads: rows (weft, along x) and columns (warp, along y) on a sheet-wide lattice
        row_k = np.round(ys / period).astype(int)
        on_row = np.abs(ys - row_k * period) < 0.5 * h
        col_k = np.round(xs / period).astype(int)
        on_col = np.abs(xs - col_k * period) < 0.5 * h
        g_row = np.zeros(ny)
        g_col = np.zeros(nx)
        if weave > 0 or arms > 0:
            g_row[on_row] = _thread_g(sheet_seed, 0, row_k[on_row], 1.1, weave, arms, arm_p)
            g_col[on_col] = _thread_g(sheet_seed, 1, col_k[on_col], 1.1, weave, arms, arm_p)
        N = nx * ny
        idx = np.arange(N).reshape(ny, nx)
        ex, ey = 1.0 / np.sqrt(elong), np.sqrt(elong)
        rows, cols, ws = [], [], []
        for dy, dx in _OFFS:
            ya, yb = max(0, -dy), ny - max(0, dy)
            xa, xb = max(0, -dx), nx - max(0, dx)
            a = idx[ya:yb, xa:xb]
            b = idx[ya + dy:yb + dy, xa + dx:xb + dx]
            L = h * np.hypot(dx * ex, dy * ey)
            w = L * 0.5 * (cost[ya:yb, xa:xb] + cost[ya + dy:yb + dy, xa + dx:xb + dx])
            if (dy, dx) == (0, 1):
                w = w / (1.0 + g_row[ya:yb, None])
            elif (dy, dx) == (1, 0):
                w = w / (1.0 + g_col[None, xa:xb])
            rows += [a.ravel(), b.ravel()]
            cols += [b.ravel(), a.ravel()]
            ws += [w.ravel(), w.ravel()]
        self._r = np.concatenate(rows)
        self._c = np.concatenate(cols)
        self._w = np.concatenate(ws)

    def field(self, sources_w, budgets):
        """U(x) = min_i (T_i(x) − b_i) through the medium: U ≤ 0 is wet, every
        front advances at the medium's speed and each source stops at its own
        budget (super-source edges b_max − b_i)."""
        nx, ny, h = self.nx, self.ny, self.h
        N = nx * ny
        budgets = np.asarray(budgets, float)
        gi = np.clip(np.round((sources_w[:, 1] - self.lo[1]) / h).astype(int), 0, ny - 1)
        gj = np.clip(np.round((sources_w[:, 0] - self.lo[0]) / h).astype(int), 0, nx - 1)
        node = gi * nx + gj
        bmax = float(budgets.max())
        best: dict[int, float] = {}
        for nd, b in zip(node.tolist(), budgets.tolist()):
            if b > best.get(nd, -1.0):
                best[nd] = b
        sn = np.array(sorted(best), int)
        r = np.concatenate([self._r, np.full(len(sn), N)])
        c = np.concatenate([self._c, sn])
        w = np.concatenate([self._w, np.maximum(bmax - np.array([best[k] for k in sn]), 1e-9)])
        G = csr_matrix((w, (r, c)), shape=(N + 1, N + 1))
        D = dijkstra(G, directed=True, indices=N)[:N].reshape(ny, nx)
        return D - bmax


def arrival(sources_w, budgets, *, h, pad, period, weave, fiber, elong, sheet_seed, rng, arms=0.0, arm_p=0.08):
    """First-passage field U on a grid in the WEAVE frame around the sources.
    Returns (U, x0, y0) with the grid origin."""
    budgets = np.asarray(budgets, float)
    lo = sources_w.min(0) - budgets.max() * pad - 2 * h
    hi = sources_w.max(0) + budgets.max() * pad + 2 * h
    med = Medium(lo, hi, h=h, period=period, weave=weave, fiber=fiber, elong=elong, sheet_seed=sheet_seed,
                 rng=rng, arms=arms, arm_p=arm_p)
    return med.field(sources_w, budgets), med.lo[0], med.lo[1]


# ---------------------------------------------------------------------------
# fronts → laps → one walking line
# ---------------------------------------------------------------------------

def _resample_closed(c: np.ndarray, M: int) -> np.ndarray:
    if np.hypot(*(c[0] - c[-1])) > 1e-9:
        c = np.vstack([c, c[:1]])
    s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(c, axis=0).T))]
    t = np.linspace(0, s[-1], M, endpoint=False)
    return np.column_stack([np.interp(t, s, c[:, 0]), np.interp(t, s, c[:, 1])])


def _smooth_closed(L: np.ndarray, sigma_mm: float) -> np.ndarray:
    """Circular Gaussian smoothing of a closed, evenly resampled front: takes
    the grid's facets off without taking the medium's roughness."""
    per = float(np.sum(np.hypot(*np.diff(np.vstack([L, L[:1]]), axis=0).T)))
    sp = max(per / len(L), 1e-9)
    sg = sigma_mm / sp
    if sg < 0.3:
        return L
    return ndi.gaussian_filter1d(L, sg, axis=0, mode="wrap")


def _front(U, lo, h, level, inside_w):
    """The closed front of U at `level` that encloses `inside_w` (weave mm),
    as (M, 2) weave-frame points, counter-clockwise; None if none."""
    from matplotlib.path import Path as MPath  # noqa: PLC0415
    from skimage import measure  # noqa: PLC0415
    cs = measure.find_contours(U, level)
    best, best_len = None, 0.0
    for c in cs:
        if len(c) < 6:
            continue
        xy = np.column_stack([lo[0] + c[:, 1] * h, lo[1] + c[:, 0] * h])
        if not MPath(xy).contains_point(inside_w):
            continue
        L = float(np.sum(np.hypot(*np.diff(xy, axis=0).T)))
        if L > best_len:
            best, best_len = xy, L
    if best is None:
        return None
    x, y = best[:, 0], best[:, 1]
    area = 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)
    return best[::-1] if area < 0 else best


def lap_levels(profile, s_bins, *, R, pitch, contrast, s_end=1.0):
    """Radius fractions of the laps: local gap = pitch / darkness^contrast, so
    the line's density follows the measured darkness profile."""
    out, s = [], max(pitch / R, 0.04)
    while s < s_end - 1e-9:
        out.append(s)
        d = max(float(np.interp(s, s_bins, profile)), 0.08) ** contrast
        s += max(pitch / R / d, 0.25 * pitch / R)
    out.append(s_end)
    return np.array(out)


def lap_schedule(schedule, profile, s_bins, *, R, pitch, contrast, rim_w, inner, pile=0.12):
    """Radius fractions of the laps under three readings of the corpus.

    density  line density ∝ measured darkness (dark core → dense core)
    pinned   Washburn spreading gives EVEN gaps (r ∝ √t at constant pen speed:
             gap = const), so the interior gets `inner` even laps; then the
             contact line pins and the pen keeps passing the final front: the
             laps pile up within the measured rim width (the coffee ring)
    iso      fronts at equal steps of the measured darkness: they crowd where
             the photo's darkness falls fastest — at the edge (iso-gaps 0.06 R
             at the edge vs 0.17 R inside)"""
    if schedule == "density":
        return lap_levels(profile, s_bins, R=R, pitch=pitch, contrast=contrast)
    g = pitch / R
    if schedule == "pinned":
        s_pin = 1.0 - pile
        inner_s = list(np.linspace(0.0, s_pin, inner + 1)[1:]) if inner > 0 else []
        n_pin = max(2, int(round(pile / g)) + 1)
        pile = list(s_pin + (1.0 - s_pin) * (np.arange(1, n_pin + 1) / n_pin) ** 0.6)
        return np.array(sorted(set(np.round(inner_s + pile, 6))))
    # iso: equal darkness steps on the (monotone envelope of the) profile
    pr = np.minimum.accumulate(np.asarray(profile, float))
    lo = float(np.interp(1.0, s_bins, pr))
    out = []
    n = 2
    while True:
        lv = np.linspace(pr[0], lo, n + 1)[1:]
        ss = [float(np.interp(-v, -pr, s_bins)) for v in lv]
        if n > 60 or min(np.diff([0.0] + ss)) < g:
            break
        out = ss
        n += 1
    return np.array(out or [1.0])


def _nearest(L, p):
    return int(np.argmin(np.hypot(L[:, 0] - p[0], L[:, 1] - p[1])))


def walk(laps, kinds, start, end, M, rim_dir, arc):
    """One contiguous path through the laps (inner → outer).

    kinds[k]: "full" laps are joined as a spiral (each lap blends into the
    next over one turn); "arc" laps are swept back and forth over `arc` of
    the circumference centred on `rim_dir` (a crescent tide line). The last
    lap is full and ends nearest `end`."""
    K = len(laps)
    # align the full laps backwards from the exit, so the spiral ends at `end`
    starts = [0] * K
    starts[-1] = _nearest(laps[-1], end)
    for k in range(K - 2, -1, -1):
        starts[k] = _nearest(laps[k], laps[k + 1][starts[k + 1]])
    rolled = [np.roll(L, -s, axis=0) for L, s in zip(laps, starts)]
    path = [np.asarray(start)[None, :]]
    if kinds[0] == "full" and K > 1:
        # out of the source: one turn that opens from the point onto the first front
        f = (np.arange(M) / M)[:, None]
        path.append((1 - f) * np.asarray(start)[None, :] + f * rolled[0])
    k = 0
    direction = 1
    while k < K:
        L = rolled[k]
        if kinds[k] == "full" and k < K - 1 and kinds[k + 1] == "full":
            f = (np.arange(M) / M)[:, None]
            fsm = f * f * (3 - 2 * f)
            path.append((1 - fsm) * L + fsm * rolled[k + 1])
            k += 1
            continue
        if kinds[k] == "full":
            # a full lap from the nearest point to the pen, ending where the lap was aligned
            j = _nearest(L, path[-1][-1])
            seq = np.r_[np.arange(j, M), np.arange(0, j)]
            if k == K - 1:
                # end exactly at the aligned exit index (0): go round from j to M
                seq = np.r_[np.arange(j, M), [0]]
                if len(seq) < M // 3:
                    seq = np.r_[np.arange(j, M), np.arange(0, M), [0]]
            path.append(L[seq])
            k += 1
            continue
        # arc lap: sweep `arc` of the lap centred on the rim direction
        c = L.mean(0)
        ang = np.arctan2(L[:, 1] - c[1], L[:, 0] - c[0])
        ic = int(np.argmin(np.abs(np.angle(np.exp(1j * (ang - rim_dir))))))
        half = int(0.5 * arc * M)
        seq = (ic + np.arange(-half, half + 1)) % M
        if direction < 0:
            seq = seq[::-1]
        direction = -direction
        path.append(L[seq])
        k += 1
    return np.vstack(path)


def walk_through(passes, p_in, M):
    """N closed passes, each blending into the next over one turn (so they
    cross instead of nesting), starting and ending at the entry point p_in:
    the line then goes on THROUGH the stain along its own path."""
    K = len(passes)
    starts = [0] * K
    starts[0] = _nearest(passes[0], p_in)
    for k in range(1, K):
        starts[k] = _nearest(passes[k], passes[k - 1][starts[k - 1]])
    rolled = [np.roll(L, -st, axis=0) for L, st in zip(passes, starts)]
    path = [np.asarray(p_in)[None, :]]
    f = (np.arange(M) / M)[:, None]
    fsm = f * f * (3 - 2 * f)
    for k in range(K - 1):
        path.append((1 - fsm) * rolled[k] + fsm * rolled[k + 1])
    path.append(np.vstack([rolled[-1], rolled[-1][:1]]))
    path.append(np.asarray(p_in)[None, :])
    return np.vstack(path)


def walk_open(passes, p_in, M, frac):
    """The stain's edge (passes[0], the final front) once round, whole and
    thin, from the entry back to it; then the tide line: the other passes as
    ARCS over `frac` of the circumference, centred where the line came in,
    swept back and forth with hairpin turns (the corpus' dark ring covers a
    median 63 %: it fails to close). Ends back at the entry p_in."""
    K = len(passes)
    half = max(2, int(0.5 * frac * M))
    path = [np.asarray(p_in)[None, :]]
    L0 = passes[0]
    j = _nearest(L0, p_in)
    path.append(L0[(j + np.arange(M + 1)) % M])
    ref = L0[j]
    arcs = passes[1:]
    for k, L in enumerate(arcs):
        ic = _nearest(L, ref)
        lo_i, hi_i = ic - half, ic + half
        if k == 0:
            seq = np.arange(ic, hi_i + 1)
        elif k == len(arcs) - 1:
            seq = np.arange(hi_i, ic - 1, -1) if k % 2 else np.arange(lo_i, ic + 1)
        else:
            seq = np.arange(hi_i, lo_i - 1, -1) if k % 2 else np.arange(lo_i, hi_i + 1)
        path.append(L[seq % M])
    path.append(np.asarray(p_in)[None, :])
    return np.vstack(path)


def pass_levels(tide, profile, s_bins, *, n, pile, rng):
    """Radius fractions of the passes. mesa: drawn from the measured darkness
    (density ∝ darkness × circumference, stratified), in a shuffled order so
    consecutive passes jump in and out (a knot); rim: most passes in the pile
    at the pinned front. The final front comes first."""
    sb = np.asarray(s_bins)
    k = sb <= 1.0
    if tide == "rim":
        # the corpus' rimmed stains have a pale core (0.66 of the rim's darkness): every pass is at the rim
        lv = 1.0 - pile * (np.arange(n) + rng.random(n)) / max(n, 1)
    else:
        w = np.asarray(profile)[k] * np.maximum(sb[k], 0.05)
        cdf = np.cumsum(w) / np.sum(w)
        u = (np.arange(n) + rng.random(n)) / n
        lv = np.clip(np.interp(u, cdf, sb[k]), 0.2, 0.97)
    rng.shuffle(lv)
    return [1.0] + list(lv)   # the final front first: the line meets the stain's edge before its ring


# ---------------------------------------------------------------------------
# where the line slows: its own clock, or the 2/3 power law
# ---------------------------------------------------------------------------

def line_time(pts: np.ndarray, dance_t=None) -> np.ndarray:
    """Cumulative time along a polyline. With a clock (dance_t), the clock;
    otherwise the 2/3 power law: v ∝ κ^(-1/3) (curvature from a light
    smoothing), so the line lingers in its tight turns."""
    if dance_t is not None:
        t = np.asarray(dance_t, float)
        return t - t[0]
    d = np.hypot(*np.diff(pts, axis=0).T)
    q = ndi.gaussian_filter1d(pts, 2.0, axis=0, mode="nearest")
    d1 = np.gradient(q, axis=0)
    d2 = np.gradient(d1, axis=0)
    sp = np.maximum(np.hypot(*d1.T), 1e-9)
    kappa = np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / sp ** 3
    v = np.clip(kappa, 1e-3, None) ** (-1.0 / 3.0)
    v = 0.5 * (v[1:] + v[:-1])
    return np.r_[0.0, np.cumsum(d / v)]


def dwell(s: np.ndarray, t: np.ndarray, window: float) -> np.ndarray:
    """Time spent within ± window mm of arc length around each point."""
    return np.interp(s + window, s, t) - np.interp(s - window, s, t)


def pick_events(D: np.ndarray, s: np.ndarray, n: int, sep: float, floor: float) -> list[int]:
    """Indices of the n strongest dwell maxima, ≥ sep mm apart along the line,
    each above `floor` × the strongest. Ties broken by index (deterministic)."""
    order = np.lexsort((np.arange(len(D)), -D))
    keep: list[int] = []
    top = float(D[order[0]]) if len(order) else 0.0
    for i in order:
        if len(keep) >= n or D[i] < floor * top:
            break
        if all(abs(s[i] - s[j]) >= sep for j in keep):
            keep.append(int(i))
    return sorted(keep)


# ---------------------------------------------------------------------------
# the renderer
# ---------------------------------------------------------------------------

def _digest(ctx, ref):
    return ctx.use("stain", ref)["entry"]["digest"]


def _sheet_weave(sheet_seed: int, angle):
    r = np.random.default_rng([int(sheet_seed) & 0x7FFFFFFF, 0x5741])
    a = float(r.uniform(0, np.pi / 2)) if angle is None else np.radians(angle)
    return a


def stain_event(c, src_pts, src_b, *, R, dig, tide, arc, rim_dir, pitch, contrast, halo, weave, fiber,
                elong, period, angle, sheet_seed, rng, exit_pts, M=360, schedule="density", inner=3, pile=0.12,
                arms=0.0, arm_p=0.08, slip=0.0, entry_pts=None, passes=6, closure=1.0, line_starts_here=False):
    """Fronts and the walking path of one stain.

    c: the source (deepest dwell) point; src_pts/src_b: every wet source on
    the line with its budget (the comet tail); exit_pts: the line after c
    (to find where it leaves the wet region). Returns (path, exit_index)
    where exit_index indexes exit_pts (the line resumes there), or None."""
    Rw = _rot(-angle)
    to_w = lambda p: (np.asarray(p) - c) @ Rw.T  # noqa: E731
    to_s = lambda q: np.asarray(q) @ _rot(angle).T + c  # noqa: E731
    sw = to_w(src_pts)
    h = float(np.clip(R / 40.0, 0.07, 0.3))
    pad = 1.7 + halo
    U, x0, y0 = arrival(sw, np.asarray(src_b, float), h=h, pad=pad, period=period, weave=weave, fiber=fiber,
                        elong=elong, sheet_seed=sheet_seed, rng=rng, arms=arms, arm_p=arm_p)
    bmax = float(np.max(src_b))
    sb = np.asarray(dig["s_bins"])
    prof = np.asarray(dig["profile_rim"] if tide == "rim" else dig["profile_mesa"])
    rw = float(np.interp(0.5, [0, 1], [dig["rim_w_q"][1], dig["rim_w_q"][3]]))
    if schedule == "passes":
        ss = np.array(pass_levels(tide, prof, sb, n=passes, pile=pile, rng=rng))
    else:
        ss = lap_schedule(schedule, prof, sb, R=bmax, pitch=pitch, contrast=contrast, rim_w=rw, inner=inner,
                          pile=pile)
    levels = [(s - 1.0) * bmax for s in ss]
    kinds = ["full"] * len(levels)
    if tide == "rim" and schedule != "pinned":
        # the tide line: laps inside the measured rim band are arcs; the final front stays whole
        for k, s in enumerate(ss[:-1]):
            if s >= 1.0 - rw - 1e-9:
                kinds[k] = "arc"
    if halo > 0 and schedule != "passes":
        # (passes: no halo — the line must enter on the stain's own edge, or it would hop across the gap)
        levels.append(halo * bmax)
        kinds.append("full")
    laps, lk = [], []
    s_pin = 1.0 - pile
    ny_, nx_ = U.shape
    gx = x0 + np.arange(nx_) * h
    gy = y0 + np.arange(ny_) * h
    phi = np.arctan2(gy[:, None], gx[None, :])                       # angle around the source (weave frame)
    if tide == "rim":
        # the pile only on an arc of the ring (the corpus: a median 63 %): elsewhere every pass
        # falls on the final front, one line — the ring fails to close
        dphi = np.angle(np.exp(1j * (phi - (rim_dir - angle))))
        wgt = 0.5 * (1 + np.tanh((np.pi * arc - np.abs(dphi)) / 0.35))
    else:
        wgt = np.ones_like(U)
    for li, (lv, kd) in enumerate(zip(levels, kinds)):
        field, level = U, lv
        if schedule == "passes" and lv < -1e-9:
            # each pass re-pins somewhere else (stick-slip); rim: the pile only on the dark arc
            z = ndi.gaussian_filter(rng.standard_normal(U.shape), max(1.0, 0.35 * bmax / h), mode="reflect")
            z = z / max(np.abs(z).max(), 1e-9)
            off = lv - slip * 0.08 * bmax * z
            field, level = (U - wgt * off, 0.0) if (tide == "rim" and closure >= 0.999) else (U - off, 0.0)
        elif schedule == "pinned" and (s_pin - 1.0) * bmax - 1e-9 <= lv <= 1e-9:
            # the pinned passes: inside the final front by (1 − s)·R where the ring is dark; with
            # stick-slip each pass re-pins elsewhere, so the passes cross instead of nesting
            off = np.full(U.shape, lv)
            if slip > 0:
                z = ndi.gaussian_filter(rng.standard_normal(U.shape), max(1.0, 0.35 * bmax / h), mode="reflect")
                z = z / max(np.abs(z).max(), 1e-9)
                off = off - slip * pile * bmax * 0.5 * (1 + z) * (lv < -1e-9)
            field, level = U - wgt * off, 0.0
        F = _front(field, (x0, y0), h, level, np.zeros(2))
        if F is None:
            continue
        laps.append(to_s(_smooth_closed(_resample_closed(F, M), 1.6 * h)))
        lk.append(kd)
    if not laps:
        return None
    from matplotlib.path import Path as MPath  # noqa: PLC0415
    if schedule == "passes":
        # the line enters where it crosses the outermost pass; the passes start and end there
        outer = MPath(np.vstack([laps[0], laps[0][:1]]))
        ent = 0
        if entry_pts is not None and len(entry_pts):
            ins = outer.contains_points(entry_pts)
            outside = np.flatnonzero(~ins)
            if not len(outside):
                if not line_starts_here:
                    return None       # the line is already inside (an earlier stain): no second stain here
                # the line BEGINS inside its stain: walk from the nearest edge point, then go to the start
                p_in = laps[0][_nearest(laps[0], entry_pts[0])]
                wk = walk_through(laps, p_in, M) if closure >= 0.999 else walk_open(laps, p_in, M, closure)
                return np.vstack([wk, entry_pts[:1]]), -1, laps
            ent = int(outside[-1])
            p_in = entry_pts[ent]
        else:
            p_in = laps[0][0]
        if closure >= 0.999:
            return walk_through(laps, p_in, M), ent, laps
        return walk_open(laps, p_in, M, closure), ent, laps
    # where the line leaves the outermost lap
    outer = MPath(np.vstack([laps[-1], laps[-1][:1]]))
    ex = len(exit_pts)
    if len(exit_pts):
        ins = outer.contains_points(exit_pts)
        out_idx = np.flatnonzero(~ins)
        ex = int(out_idx[0]) if len(out_idx) else len(exit_pts)
    end = exit_pts[ex] if ex < len(exit_pts) else laps[-1][0]
    path = walk(laps, lk, c, end, M, rim_dir, arc)
    return path, ex, laps


def _stain_reach(p):
    return p["R"] * (1.3 + p["halo"]) + 1.0


@renderer("stain", params=[
    P("pen", "float", 0.3, "pen width mm", min=0.05, max=3.0),
    P("stains", "ref", "stain_fabric", "the measured stain statistics", kind="stain"),
    P("events", "int", 6, "how many stains per line (the line's slowest places)", min=0, max=40),
    P("R", "float", 12.0, "radius of the strongest stain, mm (others scale by √dwell, Washburn)", min=0.5, max=60.0),
    P("R_min", "float", 1.8, "smallest stain radius drawn, mm", min=0.3, max=30.0),
    P("wet", "float", 0.5, "how much slower than its own median pace the line must be to wet the cloth "
      "(0.5 = 1.5 × the median time per mm)", min=0.0, max=20.0),
    P("window", "float", 3.0, "dwell window, ± mm of line (how much nearby time pools into one stain)",
      min=0.2, max=40.0),
    P("tail", "float", 0.8, "how far the approach bleeds before the stain: wet sources on the line before "
      "the dwell peak, × R of arc (0 = a stain from a point)", min=0.0, max=6.0),
    P("tide", "choice", "rim", "mesa: dark to the edge (90 % of the corpus) | rim: a tide line | auto: rim "
      "with probability rim_p", choices=("auto", "mesa", "rim")),
    P("rim_p", "float", 0.5, "auto: probability of a tide line (corpus: 0.10; raised on purpose)",
      min=0.0, max=1.0),
    P("arc", "float", 0.63, "tide line: share of the circumference the dark ring covers (corpus median 0.63)",
      min=0.1, max=1.0),
    P("pitch", "float", 0.55, "closest lap spacing, mm (where the stain is darkest)", min=0.1, max=5.0),
    P("contrast", "float", 1.6, "darkness → lap density exponent (1 = as measured)", min=0.3, max=5.0),
    P("halo", "float", 0.16, "faint outer front beyond the body, × R (corpus median 0.16; 0 = none)",
      min=0.0, max=1.0),
    P("weave", "float", 0.1, "thread conductance (0 = isotropic paper; high = arms along the threads)",
      min=0.0, max=20.0),
    P("period", "float", 0.9, "thread spacing, mm", min=0.1, max=10.0),
    P("fiber", "float", 0.3, "fibre-scale medium noise (0.45 → front roughness 0.067 R, slope −2.7, "
      "≈ the corpus median 0.071, −2.5; default 0.3 → 0.045, the corpus' smoother quartile: rounder beads)", min=0.0, max=2.0),
    P("elong", "float", 1.0, "warp/weft absorbency ratio (1 = round beads)", min=1.0, max=3.0),
    P("angle", "float", None, "weave angle, degrees (null: from the sheet seed)", min=0.0, max=180.0,
      optional=True),
    P("satellites", "int", 0, "most satellite blots per stain, dropped on the line as it leaves", min=0, max=8),
    P("schedule", "choice", "passes", "where the laps fall: pinned (even Washburn laps, then a pile at the pinned "
      "front: the coffee ring) | density (∝ measured darkness) | iso (equal darkness steps: crowd at the edge) "
      "| passes (closed passes that cross: a knot for mesa, a crescent pile for rim; the line runs on THROUGH "
      "the stain)", choices=("pinned", "density", "iso", "passes")),
    P("passes", "int", 7, "passes: how many passes per stain", min=1, max=60),
    P("arc_max", "float", 0.75, "passes: how much of the ring the STRONGEST stain closes (1 = a whole ring; "
      "corpus median of the dark arc 0.63)", min=0.05, max=1.0),
    P("arc_min", "float", 0.2, "passes: how much of the ring the WEAKEST stain closes (the strongest closes "
      "fully); < 1 makes small stains open crescents on the side the line came in from", min=0.05, max=1.0),
    P("inner", "int", 3, "pinned: even laps inside before the front pins", min=0, max=40),
    P("arms", "float", 0.0, "loose wicking threads: conductance of the few threads that carry ink ahead "
      "(0 = none; ≈ 6 gives the coarse-weave crosses)", min=0.0, max=60.0),
    P("arm_p", "float", 0.08, "share of threads that are loose", min=0.0, max=1.0),
    P("slip", "float", 1.5, "pinned: stick-slip — each pass of the tide line re-pins elsewhere (× pile); "
      "0 = the passes nest", min=0.0, max=4.0),
    P("pile", "float", 0.15, "pinned: width of the pile of passes at the pinned front, × R", min=0.01, max=0.8),
], reach=_stain_reach,
    doc="a line that slows bleeds into the cloth: the mass is one line walking the stain's wicking fronts "
        "(measured tide lines, crescents, roughness, satellites), then the line leaves")
def stain(ctx, marks, *, pen, stains, events, R, R_min, wet, window, tail, tide, rim_p, arc, pitch, contrast, halo,
          weave, period, fiber, elong, angle, satellites, schedule, inner, pile, arms, arm_p, slip, passes,
          arc_min, arc_max):
    dig = _digest(ctx, stains)
    ang = _sheet_weave(ctx.sheet_seed, angle)
    out: list[Ink] = []
    # one clock for the whole part: dwell IN EXCESS of the part's own median pace wets the cloth,
    # and the longest excess dwell anywhere in the part is the stain of radius R
    prep = []
    for m in marks:
        pts = np.asarray(m.points, float)
        s0 = np.r_[0.0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))] if len(pts) >= 3 else np.zeros(1)
        if len(pts) < 3 or s0[-1] <= 0.6:
            prep.append(None)
            continue
        # uniform 0.2 mm resampling keeps the clock (time interpolated by arc length)
        t0 = line_time(pts, m.channel("dance_t"))
        s = np.arange(0.0, s0[-1], 0.2)
        P_ = np.column_stack([np.interp(s, s0, pts[:, 0]), np.interp(s, s0, pts[:, 1])])
        t = np.interp(s, s0, t0)
        prep.append((m, s, P_, t, dwell(s, t, window)))
    live = [q for q in prep if q is not None]
    if not live:
        return out
    # a pause is time per mm above (1 + wet) × the part's median: an even clock (or a 3 % wobble of it)
    # never passes for one
    Dbase = (1.0 + wet) * float(np.median(np.concatenate([q[4] for q in live])))
    Dtop = max(max(float(q[4].max()) for q in live) - Dbase, 1e-9 * Dbase + 1e-12)
    for mi, q in enumerate(prep):
        if q is None:
            continue
        m, s, P_, t, D = q
        vid = m.meta.get("voice_id")
        Dx = np.clip(D - Dbase, 0, None) / max(Dtop, 1e-12)
        ev = pick_events(Dx, s, events, sep=3.0 * R, floor=0.0) if events else []
        b = R * np.sqrt(Dx)                                             # Washburn: reach ∝ √(excess time)
        ev = [e for e in ev if b[e] >= R_min]
        rng = ctx.rng("stain", mi)
        line: list[np.ndarray] = []
        cur = 0
        for e in ev:
            if e <= cur:
                continue
            # the approach bleeds (earlier ink has had longer to wick); the exit barely does
            lo_s = s[e] - tail * b[e]
            k = np.flatnonzero((s >= max(lo_s, s[cur])) & (s <= s[e]))
            # the stain's own ink runs back along the approach, tapering to the line (a comet, not a capsule)
            taper = np.clip(1.0 - (s[e] - s[k]) / max(tail * b[e], 1e-9), 0, 1)
            src_b = np.maximum(b[k], 0.75 * b[e] * taper ** 1.4)
            src_b[-1] = b[e]
            keep = src_b >= 0.5 * pen
            k, src_b = k[keep], src_b[keep]
            if len(k) == 0 or b[e] < R_min:
                continue
            td = tide if tide != "auto" else ("rim" if rng.random() < rim_p else "mesa")
            heading = P_[min(e + 3, len(P_) - 1)] - P_[max(e - 3, 0)]
            rim_dir = float(np.arctan2(heading[1], heading[0]) + rng.normal(0, 0.6))
            res = stain_event(P_[e], P_[k], src_b, R=b[e], dig=dig, tide=td, arc=arc, rim_dir=rim_dir,
                              pitch=pitch, contrast=contrast, halo=halo, weave=weave, fiber=fiber, elong=elong,
                              period=period, angle=ang, sheet_seed=ctx.sheet_seed, rng=rng,
                              exit_pts=P_[e + 1:], schedule=schedule, inner=inner, pile=pile,
                              arms=arms, arm_p=arm_p, slip=slip, entry_pts=P_[cur:e + 1], passes=passes,
                              closure=float(arc_min + (arc_max - arc_min) * np.clip((b[e] - R_min) / max(R - R_min, 1e-9),
                                                                              0, 1) ** 1.5),
                              line_starts_here=(cur == 0))
            if res is None:
                continue
            path, ex, _laps = res
            if schedule == "passes" and ex < 0:
                line.append(path)             # the line begins inside its first stain
                cur = 0
            elif schedule == "passes":
                line.append(P_[cur:cur + ex + 1])
                line.append(path)
                cur = cur + ex
            else:
                line.append(P_[cur:e + 1])
                line.append(path)
                cur = e + 1 + ex
            # satellites: small knots where the leaving line passes 1.1–2.6 R out (measured distances)
            nsat = int(min(satellites, rng.choice(len(dig["sat_n_hist"]),
                                                  p=np.asarray(dig["sat_n_hist"]) / np.sum(dig["sat_n_hist"]))))
            dq = dig["sat_d_q"]
            aq = dig["sat_a_q"]
            for _ in range(nsat):
                dist = float(np.interp(rng.random(), [0, .25, .5, .75, 1], [dq[0], dq[1], dq[2], dq[3], dq[4]]))
                area = float(np.interp(rng.random(), [0, .5, 1], [aq[0], aq[2], aq[4]]))
                rs = max(b[e] * np.sqrt(area) * 1.6, 4.0 * pen)
                after = max(cur, e)
                dd = np.hypot(P_[after:, 0] - P_[e, 0], P_[after:, 1] - P_[e, 1])
                j = np.flatnonzero(dd >= dist * b[e])
                if not len(j) or rs < pen:
                    continue
                j = after + int(j[0])
                if schedule == "passes":
                    # a satellite is a small open crescent the leaving line passes through
                    j0 = max(cur, e, j - int(3 * rs / 0.2) - 2)
                    knot = stain_event(P_[j], P_[j:j + 1], np.array([rs]), R=rs, dig=dig, tide="rim", arc=arc,
                                       rim_dir=0.0, pitch=pitch, contrast=contrast, halo=0.0, weave=weave,
                                       fiber=fiber, elong=elong, period=period, angle=ang,
                                       sheet_seed=ctx.sheet_seed, rng=rng, exit_pts=P_[j + 1:], M=160,
                                       schedule="passes", pile=pile, slip=slip, entry_pts=P_[j0:j + 1],
                                       passes=3, closure=arc_min)
                    if knot is None:
                        continue
                    kp, kent, _ = knot
                    if cur < j0:
                        line.append(P_[cur:j0])
                    line.append(P_[j0:j0 + kent + 1])
                    line.append(kp)
                    cur = j0 + kent
                    continue
                knot = stain_event(P_[j], P_[j:j + 1], np.array([rs]), R=rs, dig=dig, tide="mesa", arc=arc,
                                   rim_dir=0.0, pitch=pitch, contrast=contrast, halo=0.0, weave=weave,
                                   fiber=fiber, elong=elong, period=period, angle=ang,
                                   sheet_seed=ctx.sheet_seed, rng=rng, exit_pts=P_[j + 1:], M=120)
                if knot is None:
                    continue
                kp, kex, _ = knot
                line.append(P_[cur:j + 1])
                line.append(kp)
                cur = j + 1 + kex
        if cur < len(P_):
            line.append(P_[cur:])
        poly = np.vstack([q for q in line if len(q)])
        out.append(Ink(poly, pen=pen, meta={"voice": vid, "role": "stain_line", "events": len(ev)}))
    return out


# ---------------------------------------------------------------------------
# measuring what we drew (the same quantities as the corpus)
# ---------------------------------------------------------------------------

def front_roughness(F: np.ndarray, n_ang: int = 180) -> tuple[float, float]:
    """(rough, slope) of a closed front, as `stain_measure` measures a photo:
    std of the radius after removing modes ≤ 6, ÷ mean radius; and the
    log-log slope of the radius spectrum over k = 6…40."""
    c = F.mean(0)
    a = np.arctan2(F[:, 1] - c[1], F[:, 0] - c[0])
    r = np.hypot(F[:, 0] - c[0], F[:, 1] - c[1])
    th = np.linspace(-np.pi, np.pi, n_ang, endpoint=False)
    o = np.argsort(a)
    R = np.interp(th, a[o], r[o], period=2 * np.pi)
    Fk = np.fft.rfft(R) / len(R)
    Fs = Fk.copy()
    Fs[:7] = 0
    hi = np.fft.irfft(Fs * len(R), n=len(R))
    ks = np.arange(6, 41)
    slope = float(np.polyfit(np.log(ks), np.log(np.abs(Fk[ks]) ** 2 + 1e-12), 1)[0])
    return float(hi.std() / R.mean()), slope
