"""A frozen Gesture Studies hand follows an arbitrary line.

The kit's own `grammar.restyle` smooths a line's corners away and puts no
bound on how far the result strays, and a pursuit search costs seconds per
metre. So this engine keeps the line and *offsets it sideways* by the hand's
turning instead:

1. resample the input by arc length; a lightly smoothed copy is the base
   (corners round a little — σ = ½·stray);
2. the hand draws a stroke as long as the line at scale R = bend_mm; its
   heading θ(s), high-passed (the hand's slow wander is the line's job),
   integrates into a lateral offset d(s);
3. d is scaled to a typical band (× stray) and squashed with tanh under a
   ceiling (× stray), tapered to zero at open ends / made seamless when
   closed (the stroke runs past the seam and cross-fades into its start),
   and laid along the base's normal; an inward offset deeper than a bend's
   radius is soft-limited there and the arms that still cross are cut at
   their crossing, so corners never grow loops;
4. a KD-tree over the input enforces the ceiling exactly: no output point is
   ever farther than ceiling·stray from the input polyline.

Pure numpy/scipy; one hand stream per call. Hands are read only through
`sources/_gesture_studies/frozen_library.py`.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

from ...render_work import checkpoint
from ...sources._gesture_studies import frozen_library as FL
from ...sources._gesture_studies.kit import library as _kl
from ...sources._gesture_studies.kit._research import grammar as gm

#: mode -> (typical-band factor, ceiling factor, high-pass cutoff in units of bend_mm)
MODES = {"follow": (0.6, 2.0, 1.5), "wander": (1.8, 5.0, 4.0)}

_MAX_TOKENS_PER_CHUNK = 400


def load_hand(hand_id: str, pin_hash: str | None):
    """The decoded grammar of library hand `hand_id` (pinned to `pin_hash`
    when given), or None when the library has no such hand / version or it
    may not be used for generation. Decoding is cached by the library."""
    try:
        lib = FL.FrozenLibrary(None, {("hand", hand_id): pin_hash} if pin_hash else None)
        return lib.load("hand", hand_id, purpose="generate")
    except (_kl.LibraryError, _kl.PolicyError, KeyError, ValueError):
        return None


# ---------------------------------------------------------------------------
# small geometry helpers
# ---------------------------------------------------------------------------

def _arclen(p: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def _resample(p: np.ndarray, step: float, closed: bool) -> np.ndarray:
    """Even arc-length samples, spacing ≤ step. Open: both ends included.
    Closed (p already ends at its start): the period [0, L), end excluded."""
    s = _arclen(p)
    L = s[-1]
    if closed:
        n = max(int(np.ceil(L / step)), 1)
        t = np.arange(n) * (L / n)
    else:
        n = max(int(np.ceil(L / step)), 1) + 1
        t = np.linspace(0.0, L, n)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _gauss(a: np.ndarray, sigma: float, closed: bool) -> np.ndarray:
    """Gaussian low-pass along axis 0 (σ in samples); periodic when closed,
    odd (point) reflection at open ends so straight runs stay straight."""
    if sigma <= 0:
        return a.copy()
    if closed:
        return gaussian_filter1d(a, sigma, axis=0, mode="wrap")
    pad = min(int(np.ceil(4 * sigma)), len(a) - 1)
    if pad <= 0:
        return a.copy()
    head = 2 * a[0] - a[pad:0:-1]
    tail = 2 * a[-1] - a[-2:-pad - 2:-1]
    ext = np.concatenate([head, a, tail], axis=0)
    return gaussian_filter1d(ext, sigma, axis=0, mode="nearest")[pad:pad + len(a)]


def _seg_cross(p0, p1, q0, q1):
    """The crossing point of segments p0p1 and q0q1, or None (parallel)."""
    r, q = p1 - p0, q1 - q0
    den = r[0] * q[1] - r[1] * q[0]
    if abs(den) < 1e-15:
        return None
    w = q0 - p0
    t = (w[0] * q[1] - w[1] * q[0]) / den
    return p0 + np.clip(t, 0.0, 1.0) * r


def _unfold(out: np.ndarray, closed: bool, window: int) -> np.ndarray:
    """Cut the loops an inward offset folds into at a bend tighter than it.

    A crossing between two segments at most `window` samples apart along the
    line is such a fold (the offset is a scalar laid along the normal, so it
    cannot loop any other way): the points between are replaced by the
    crossing, which leaves a clean inner corner — the arms meeting, as an
    inside offset of a corner does. Crossings farther apart are the line
    meeting itself (a spiral, close hatching) and stay. Open ends are never
    touched; a closed line keeps its starting sample when it survives."""
    import shapely  # noqa: PLC0415 — only needed here

    M = len(out)
    ring = np.vstack([out, out[:1]]) if closed else out
    nseg = len(ring) - 1
    if nseg < 4:
        return out
    segs = shapely.linestrings(np.stack([ring[:-1], ring[1:]], axis=1))
    a, b = shapely.STRtree(segs).query(segs, predicate="intersects")
    keep = a < b
    a, b = a[keep], b[keep]
    gap = b - a
    if closed:
        fwd = gap <= nseg - gap
        a, b = np.where(fwd, a, b), np.where(fwd, b, a)
        gap = np.minimum(gap, nseg - gap)
    sel = (gap >= 2) & (gap <= window)
    if not np.any(sel):
        return out
    a, gap = a[sel], gap[sel]
    shift = 0
    if closed:                       # start at a sample no fold covers
        cover = np.zeros(nseg, bool)
        for i, g in zip(a, gap):
            cover[(np.arange(i, i + g + 1)) % nseg] = True
        free = np.flatnonzero(~cover)
        if len(free) == 0:
            return out
        shift = int(free[0])
        a = (a - shift) % nseg
        ring = np.vstack([np.roll(out, -shift, axis=0), np.roll(out, -shift, axis=0)[:1]])
    idx = (np.arange(len(ring)) + shift) % M
    order = np.lexsort((-gap, a))
    a, gap = a[order], gap[order]
    pts, ids = [], []
    cur = 0
    k = 0
    while k < len(a):
        i, g = int(a[k]), int(gap[k])
        j = i + g
        while k + 1 < len(a) and a[k + 1] <= j:      # nested / overlapping: the outermost wins
            if a[k + 1] + gap[k + 1] > j:
                j = int(a[k + 1] + gap[k + 1])
            k += 1
        k += 1
        if i + 1 < cur:
            continue
        pts.append(ring[cur:i + 1])
        ids.append(idx[cur:i + 1])
        x = _seg_cross(ring[i], ring[i + 1], ring[j], ring[j + 1]) if j == i + g else None
        if x is None:
            x = 0.5 * (ring[i + 1] + ring[j])
        pts.append(x[None, :])
        ids.append(idx[i + 1:i + 2])
        cur = j + 1
    pts.append(ring[cur:len(ring) - (1 if closed else 0)])
    ids.append(idx[cur:len(ring) - (1 if closed else 0)])
    res, rid = np.vstack(pts), np.concatenate(ids)
    if closed:
        r0 = int(np.argmin(rid))
        res = np.roll(res, -r0, axis=0)
    return res


# ---------------------------------------------------------------------------
# the hand's stream
# ---------------------------------------------------------------------------

def _hand_heading(g, rng, length: float, R: float, step: float) -> tuple[np.ndarray, np.ndarray]:
    """(arc length, unwrapped heading) of a stroke the hand draws, `length`
    in R units, at scale R mm. Drawn in chunks (the chain stops at a token
    cap); each chunk continues from the last two tokens of the one before,
    so the joins are κ-continuous like the chain's own draws."""
    toks: list = []
    have = 0.0
    while have < length * (1 - 1e-9):
        ctx = (toks[-2], toks[-1]) if len(toks) >= 2 else None
        chunk, _ = gm.generate_tokens(g, rng, length=length - have, context=ctx,
                                      max_tokens=_MAX_TOKENS_PER_CHUNK)
        got = sum(t[1] for t in chunk if t[0] != "corner")
        if got <= 0:
            break
        toks.extend(chunk)
        have += got
    if not toks:
        return np.array([0.0, max(length * R, step)]), np.zeros(2)
    pts, _, _ = gm.tokens_to_points(toks, R, start=(0.0, 0.0), heading=0.0, step=step)
    d = np.diff(pts, axis=0)
    seg = np.linalg.norm(d, axis=1)
    keep = seg > 1e-9
    d, seg = d[keep], seg[keep]
    if len(seg) == 0:
        return np.array([0.0, max(length * R, step)]), np.zeros(2)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    s = np.cumsum(seg) - 0.5 * seg          # heading lives at segment midpoints
    return s, th


# ---------------------------------------------------------------------------
# follow
# ---------------------------------------------------------------------------

def follow(points: np.ndarray, closed: bool, grammar, rng: np.random.Generator,
           stray_mm: float, bend_mm: float, wander: bool, step: float = 0.3) -> np.ndarray:
    """One line drawn by `grammar` along `points` (N, 2 mm). Every output
    point lies within ceiling·stray_mm of the input polyline; closed → the
    last row equals the first exactly; open → the input's exact end points.
    Inputs too short to carry a hand (< 3 samples or < 2·step long) come back
    as an unchanged copy."""
    checkpoint()
    pts = np.array(points, dtype=np.float64, copy=True)
    if pts.ndim != 2 or len(pts) < 2 or not np.all(np.isfinite(pts)):
        return pts
    band_f, ceil_f, cut_f = MODES["wander" if wander else "follow"]
    stray, bend = float(stray_mm), float(bend_mm)
    work = pts
    if closed and not np.array_equal(work[0], work[-1]):
        work = np.vstack([work, work[:1]])
    L = float(_arclen(work)[-1])
    if L < 2 * step or stray <= 0 or bend <= 0:
        return pts
    P = _resample(work, step, closed)
    N = len(P)
    if N < 3:
        return pts
    ds = L / N if closed else L / (N - 1)
    s = np.arange(N) * ds

    # 2. base: the input, corners rounded a little; open ends pinned
    sig_b = 0.5 * stray / ds
    base = _gauss(P, sig_b, closed)
    if not closed:
        w = _smoothstep(np.minimum(s, L - s) / max(3 * sig_b * ds, 1e-9))[:, None]
        base = w * base + (1 - w) * P

    # 3. the hand's heading, by arc-length fraction onto the samples. A closed
    #    line draws No samples past its end, cross-faded into its start in
    #    step 7, so the seam is smooth (a ramp alone leaves a visible cusp).
    No = min(int(round(min(L / 3, 2 * cut_f * bend) / ds)), N - 1) if closed else 0
    Ne = N + No
    Le = Ne * ds if closed else L
    se = np.arange(Ne) * ds
    hs, hth = _hand_heading(grammar, rng, Le / bend, bend, step)
    u = (se + 0.5 * ds) / Le if closed else se / Le
    th = np.interp(u * hs[-1], hs, hth) if len(hs) > 1 else np.zeros(Ne)

    # 4. high-pass: the slow turning is the input line's, not the hand's
    th_hp = th - _gauss(th[:, None], cut_f * bend / ds, False)[:, 0]

    # 5. lateral offset, slow drift removed
    d = np.cumsum(np.sin(th_hp)) * ds
    d = d - d[0]
    d = d - _gauss(d[:, None], 2 * cut_f * bend / ds, False)[:, 0]

    # 6. band, then a soft ceiling
    C = ceil_f * stray
    rms = float(np.sqrt(np.mean(d * d)))
    d = d * (band_f * stray / max(rms, 1e-9))
    d = C * np.tanh(d / C)

    # 7. ends
    if closed:
        head = d[:N].copy()
        if No > 0:
            w = _smoothstep((np.arange(No) + 0.5) / No)
            head[:No] = w * d[:No] + (1 - w) * d[N:N + No]
        d = head
    else:
        e = min(L / 4, 3 * bend)
        d = d * _smoothstep(s / e) * _smoothstep((L - s) / e)

    # 8. along the base's normal. Where an inward offset is deeper than a
    #    bend's radius it folds: near the bend it is soft-limited to 0.8 ×
    #    the radius (no cusp), and the arms that still cross are cut there.
    if closed:
        t = (np.roll(base, -1, axis=0) - np.roll(base, 1, axis=0)) / 2
        acc = np.roll(base, -1, axis=0) - 2 * base + np.roll(base, 1, axis=0)
    else:
        t = np.gradient(base, axis=0)
        acc = np.gradient(t, axis=0)
    tn = np.linalg.norm(t, axis=1)
    ok = tn > 1e-12
    kap = np.where(ok, (t[:, 0] * acc[:, 1] - t[:, 1] * acc[:, 0]) / np.maximum(tn, 1e-12) ** 3, 0.0)
    inward = d * kap > 0
    if np.any(inward):
        m = 0.8 / np.abs(kap[inward])
        d[inward] = np.sign(d[inward]) * m * np.tanh(np.abs(d[inward]) / m)
    t = np.where(ok[:, None], t / np.maximum(tn, 1e-12)[:, None], 0.0)
    nrm = np.column_stack([-t[:, 1], t[:, 0]])
    out = _unfold(base + nrm * d[:, None], closed, int(np.ceil(4 * C / ds)))

    # 9. the hard ceiling: never farther than C from the input
    dense = _resample(work, step / 2, closed)
    if not closed:
        dense = np.vstack([dense, work[-1:]])
    dist, idx = cKDTree(dense).query(out)
    far = dist > C
    if np.any(far):
        q = dense[idx[far]]
        out[far] = q + (out[far] - q) * (C / dist[far])[:, None]

    # 10. ends / closure exact
    if closed:
        out = np.vstack([out, out[:1]])
    else:
        out[0], out[-1] = pts[0], pts[-1]
    return out
