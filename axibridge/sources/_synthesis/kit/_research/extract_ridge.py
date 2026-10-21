# FROZEN from research commit d5ccd75: tools/gesture/gesture/extract_ridge.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Hessian ridge extractor (bake-off entry): grayscale → sub-pixel centrelines,
no binarisation of the geometry.

Pipeline
1. Ink signal I = 1 − gray. Typical line width w = median FWHM of the ink
   profile across the line at sample points (a rough Sauvola skeleton only
   says where to measure); `width=` overrides. Scale σ = 0.4 w (Steger needs
   σ ≥ w/(2√3); larger merges near-parallel lines). `n_scales` > 1 adds a
   ladder around it with per-pixel γ-normalised scale selection — off by
   default: per-pixel selection lets crayon grain win at fine scales.
2. Steger ridge points: Hessian of the Gaussian-smoothed image; the
   eigenvector of the most negative eigenvalue λ₁ is the line normal n; a
   2nd-order Taylor step t = −(∇I·n)/λ₁ along n gives the sub-pixel centre;
   the pixel is a candidate when that centre falls inside it (±0.55 px).
   Strength is the scale-normalised σ²·(−λ₁).
3. Hysteresis thresholds relative to the image's own noise (MAD of σ²λ₁ over
   all pixels), with small absolute floors. Seeds must also be anisotropic
   (|λ₂| < ½|λ₁|), so dots/specks never start a line.
4. Steger linking: from the strongest unused seed, walk both ways along the
   tangent choosing among the three forward neighbours (then a radius-2
   forward cone, bridging one-pixel dropouts) by distance + bending. A step
   ends the line if its tangent bends > `max_turn` from the current heading
   OR from the chord over the last ~3σ — the second test is what stops a walk
   from swinging onto the other line at a crossing. Meeting an already-linked
   pixel ends it too. Lateral duplicate responses are suppressed as it goes.
5. Good-continuation pairing: each open end is judged from its trusted part
   (position/tangent measured ~0.75 w back from the tip, where the ridge is
   not yet pulled toward a crossing). Ends ≤ 3 w apart that face each other
   (tangents anti-parallel within 30°, small lateral offsets) are paired
   greedily by cost and joined with a cubic Hermite bridge after trimming the
   distorted tips. Unpaired ends stay ends (T-junction stems). A chain that
   returns to itself becomes a closed stroke.
6. Filtering: a stroke must be ≥ 3 w long, have median strength ≥ the seed
   threshold, and if shorter than 8 w its median strength must be ≥ 20× the
   noise (short faint ridges are paper grain / plate tone). Free ends are
   trimmed where ink contrast falls below half the stroke's median (a coarse
   ridge runs on ~σ past the ink tip).
7. Width per point: FWHM of the ink profile along the normal, above a local
   paper level; median-smoothed along s.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates, minimum_filter
from scipy.signal import medfilt
from scipy.spatial import cKDTree
from skimage.filters import threshold_sauvola
from skimage.morphology import remove_small_objects, skeletonize

from .core import Drawing, Stroke
from .curvature import arclength


# --------------------------------------------------------------------------
# width / scale
# --------------------------------------------------------------------------

def estimate_width(gray: np.ndarray, n_samples: int = 4000) -> float:
    """Typical full line width (px), measured as the FWHM of the ink profile
    across the line at sample points of a rough Sauvola skeleton (the mask
    only says WHERE to measure; its own thickness is not used — Sauvola
    shaves crayon lines to their dark core). Falls back to 3 px."""
    H, W = gray.shape
    win = max(15, (min(H, W) // 60) | 1)
    gs = gaussian_filter(gray, 1.0)
    mask = gs < threshold_sauvola(gs, window_size=win, k=0.2)
    mask = remove_small_objects(mask, max_size=30)
    if mask.sum() < 50:
        return 3.0
    rc = np.column_stack(np.nonzero(skeletonize(mask)))
    if len(rc) < 20:
        return 3.0
    rc = rc[np.linspace(0, len(rc) - 1, min(n_samples, len(rc))).astype(int)]
    I = (1.0 - gs).astype(np.float32)
    sg = 1.5
    Ixx = gaussian_filter(I, sg, order=(0, 2))[rc[:, 0], rc[:, 1]]
    Iyy = gaussian_filter(I, sg, order=(2, 0))[rc[:, 0], rc[:, 1]]
    Ixy = gaussian_filter(I, sg, order=(1, 1))[rc[:, 0], rc[:, 1]]
    theta = 0.5 * np.arctan2(2 * Ixy, Ixx - Iyy)
    nrm = np.column_stack([-np.sin(theta), np.cos(theta)])
    pts = rc[:, ::-1].astype(np.float64)
    # snap each sample to the profile maximum along the normal first
    off = np.arange(-2.0, 2.01, 0.25)
    xs = pts[:, 0:1] + off[None] * nrm[:, 0:1]
    ys = pts[:, 1:2] + off[None] * nrm[:, 1:2]
    v = map_coordinates(I, [ys.ravel(), xs.ravel()], order=1, mode="nearest").reshape(xs.shape)
    k = v.argmax(axis=1)
    pts = np.column_stack([xs[np.arange(len(k)), k], ys[np.arange(len(k)), k]])
    fw = _fwhm(I, _paper(I, 4.0), pts, nrm, 30.0)
    return float(np.clip(np.median(fw), 1.5, 40.0))


# --------------------------------------------------------------------------
# ridge field
# --------------------------------------------------------------------------

def _hessian_at(I: np.ndarray, sigma: float):
    g = lambda o: gaussian_filter(I, sigma, order=o, mode="nearest")
    Ix, Iy = g((0, 1)), g((1, 0))
    Ixx, Iyy, Ixy = g((0, 2)), g((2, 0)), g((1, 1))
    half = 0.5 * (Ixx + Iyy)
    rad = np.sqrt((0.5 * (Ixx - Iyy)) ** 2 + Ixy ** 2)
    lam1 = half - rad                       # most negative: across the line
    lam2 = half + rad
    theta = 0.5 * np.arctan2(2 * Ixy, Ixx - Iyy)   # eigvec of lam2 = tangent
    tx, ty = np.cos(theta), np.sin(theta)
    nx, ny = -ty, tx
    den = Ixx * nx * nx + 2 * Ixy * nx * ny + Iyy * ny * ny   # == lam1
    with np.errstate(divide="ignore", invalid="ignore"):
        t = -(Ix * nx + Iy * ny) / den
    t = np.where(np.isfinite(t), t, 9.0)
    s = np.where(lam1 < 0, -lam1 * sigma * sigma, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        aniso = np.where(lam1 < 0, 1.0 - np.maximum(-lam2, 0.0) / -lam1, 0.0)
    return s.astype(np.float32), (t * nx).astype(np.float32), (t * ny).astype(np.float32), \
        tx.astype(np.float32), ty.astype(np.float32), aniso.astype(np.float32), \
        (lam1 * sigma * sigma).astype(np.float32)


def _ridge_field(I: np.ndarray, sigmas: list[float], tol: float = 0.55, gamma: float = 2.0):
    """Per-pixel scale selection, then the Steger centre test at that scale.

    The scale is the argmax over `sigmas` of σ^γ·(−λ₁); with γ = 2 a bar of
    full width w peaks at σ = w/2, so crayon/litho lines pick a coarse scale
    and their grain does not survive as fine-scale ridges. The inside-the-pixel
    test is applied only at the chosen scale (testing first and then taking
    the max would let grain win wherever the coarse centre is elsewhere).
    Returns ([S, OX, OY, TX, TY, AN, SIG], noise) where S is the normalised
    strength (0 for non-candidates) and noise the MAD of σ²λ₁ at the finest
    scale."""
    best = None
    noise = None
    for sg in sigmas:
        s, ox, oy, tx, ty, an, l1 = _hessian_at(I, sg)
        if noise is None:
            sub = l1[::2, ::2]
            noise = float(1.4826 * np.median(np.abs(sub - np.median(sub))))
        sel = s * (sg ** (gamma - 2.0))
        sig = np.full(s.shape, sg, np.float32)
        if best is None:
            best = [sel, s, ox, oy, tx, ty, an, sig]
            continue
        m = sel > best[0]
        for k, arr in enumerate((sel, s, ox, oy, tx, ty, an, sig)):
            best[k] = np.where(m, arr, best[k])
    _, s, ox, oy, tx, ty, an, sig = best
    inside = (np.abs(ox) <= tol) & (np.abs(oy) <= tol) & (s > 0)
    s = np.where(inside, s, 0.0).astype(np.float32)
    return [s, ox, oy, tx, ty, an, sig], noise


# --------------------------------------------------------------------------
# linking
# --------------------------------------------------------------------------

_DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]  # (dx, dy)
_RING2 = [(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3) if max(abs(dx), abs(dy)) == 2]


def _link(S, OX, OY, TX, TY, AN, SIG, lo, hi, max_turn_deg=40.0, min_pts=3,
          memory_sigmas=3.0, seed_aniso=0.5):
    """Steger-style linking. Returns a list of flat-index arrays, one per line."""
    H, W = S.shape
    cand = S > lo
    flat_s = S.ravel()
    seeds = np.flatnonzero(((S > hi) & (AN > seed_aniso)).ravel())
    seeds = seeds[np.argsort(-flat_s[seeds], kind="stable")]
    used = np.zeros(H * W, dtype=np.int32)   # 0 free, >0 line id + 1, -1 suppressed
    candf = cand.ravel()
    OXf, OYf, TXf, TYf, SGf = OX.ravel(), OY.ravel(), TX.ravel(), TY.ravel(), SIG.ravel()
    cos_max = math.cos(math.radians(max_turn_deg))
    lines = []

    def pos(i):
        r, c = divmod(i, W)
        return c + float(OXf[i]), r + float(OYf[i])

    def tan(i, dx, dy):
        tx, ty = float(TXf[i]), float(TYf[i])
        return (tx, ty) if tx * dx + ty * dy >= 0 else (-tx, -ty)

    def suppress_lateral(i, tx, ty, lid):
        r, c = divmod(i, W)
        kmax = max(2, int(math.ceil(float(SGf[i]))))
        for sgn in (1, -1):
            for k in range(1, kmax + 1):
                cc = c + int(round(-ty * k * sgn))
                rr = r + int(round(tx * k * sgn))
                if 0 <= rr < H and 0 <= cc < W:
                    j = rr * W + cc
                    if candf[j] and used[j] == 0:
                        # only a parallel duplicate response, not a crossing line
                        if abs(float(TXf[j]) * tx + float(TYf[j]) * ty) > 0.8:
                            used[j] = -1
                        else:
                            break
                else:
                    break

    def walk(i0, dx, dy, lid):
        pts = []
        idx = []
        hist = [pos(i0)]
        memory = max(3.0, memory_sigmas * float(SGf[i0]))
        i = i0
        while True:
            r, c = divmod(i, W)
            px, py = pos(i)
            # reference heading: chord over the last `memory` px of the walk —
            # a ridge that swings onto a crossing line turns faster than that
            rx, ry = dx, dy
            for k in range(len(hist) - 2, -1, -1):
                hx, hy = hist[k]
                dd = math.hypot(px - hx, py - hy)
                if dd >= memory:
                    rx, ry = (px - hx) / dd, (py - hy) / dd
                    break
            best, best_cost, best_t = -1, 1e9, None
            hit = False
            # direction index nearest to (dx, dy)
            a = math.atan2(dy, dx)
            k0 = int(round(a / (math.pi / 4))) % 8
            for ring in (0, 1):
                offs = ([_DIRS[(k0 - 1) % 8], _DIRS[k0], _DIRS[(k0 + 1) % 8]] if ring == 0 else
                        [o for o in _RING2 if (o[0] * dx + o[1] * dy) / math.hypot(*o) > 0.75])
                for ox, oy in offs:
                    cc, rr = c + ox, r + oy
                    if not (0 <= rr < H and 0 <= cc < W):
                        continue
                    j = rr * W + cc
                    if not candf[j]:
                        continue
                    if used[j] != 0:
                        if used[j] > 0 and used[j] != lid:
                            hit = True
                        continue
                    tx, ty = tan(j, dx, dy)
                    ct = tx * dx + ty * dy
                    if ct < cos_max or tx * rx + ty * ry < cos_max:
                        continue
                    qx, qy = pos(j)
                    vx, vy = qx - px, qy - py
                    d = math.hypot(vx, vy)
                    if d < 1e-6 or (vx * dx + vy * dy) / d < 0.3:
                        continue
                    cost = d + 2.0 * (1.0 - ct) * 4
                    if cost < best_cost:
                        best, best_cost, best_t = j, cost, (tx, ty)
                if best >= 0 or hit:
                    break
            if best < 0:
                return idx
            used[best] = lid
            dx, dy = best_t
            suppress_lateral(best, dx, dy, lid)
            idx.append(best)
            hist.append(pos(best))
            i = best

    for i0 in seeds.tolist():
        if used[i0] != 0:
            continue
        lid = len(lines) + 1
        used[i0] = lid
        tx, ty = float(TXf[i0]), float(TYf[i0])
        suppress_lateral(i0, tx, ty, lid)
        fwd = walk(i0, tx, ty, lid)
        bwd = walk(i0, -tx, -ty, lid)
        ids = bwd[::-1] + [i0] + fwd
        lines.append(np.asarray(ids, dtype=np.int64) if len(ids) >= min_pts else None)
    return [ln for ln in lines if ln is not None]


# --------------------------------------------------------------------------
# continuation across junction gaps
# --------------------------------------------------------------------------

def _end_tangent(p: np.ndarray, at_end: bool, reach: float):
    """Unit outgoing tangent at one end, from the chord over `reach` px."""
    q = p if at_end else p[::-1]
    s = arclength(q[::-1])          # distance from the end backwards
    k = int(np.searchsorted(s, reach))
    k = min(max(k, 1), len(q) - 1)
    v = q[-1] - q[-1 - k]
    n = np.hypot(*v)
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


def _end_frame(p: np.ndarray, at_end: bool, skip: float, reach: float):
    """(position, unit outgoing tangent) of one end, measured `skip` px back
    from the tip over a chord of `reach` px (falls back to the whole line)."""
    q = p if at_end else p[::-1]
    s = arclength(q[::-1])
    if s[-1] < skip + 2.0:
        skip = 0.0
    k0 = min(int(np.searchsorted(s, skip)), len(q) - 1)
    k1 = min(max(int(np.searchsorted(s, skip + reach)), k0 + 1), len(q) - 1)
    a, b = q[-1 - k0], q[-1 - k1]
    v = a - b
    n = float(np.hypot(*v))
    if n < 1e-9:
        return a.copy(), _end_tangent(p, at_end, reach)
    return a.copy(), v / n


def _trim(p: np.ndarray, at_end: bool, amount: float) -> np.ndarray:
    if amount <= 0 or len(p) < 4:
        return p
    q = p if at_end else p[::-1]
    s = arclength(q[::-1, :2])
    keep = len(q) - int(np.searchsorted(s, amount))
    keep = max(keep, max(2, len(q) // 2))
    q = q[:keep]
    return q if at_end else q[::-1]


def _hermite(p0, t0, p1, t1, step=1.0):
    d = float(np.hypot(*(p1 - p0)))
    n = max(int(math.ceil(d / step)), 1)
    u = np.linspace(0, 1, n + 1)[1:-1, None]
    m0, m1 = t0 * d, t1 * d
    h00 = 2 * u**3 - 3 * u**2 + 1
    h10 = u**3 - 2 * u**2 + u
    h01 = -2 * u**3 + 3 * u**2
    h11 = u**3 - u**2
    return h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1


def _continue(lines, wls, gap_widths=3.0, max_angle_deg=30.0, trim_widths=0.75):
    """Pair collinear ends across gaps ≤ gap_widths·w_local and join chains.
    `wls` = per-point local line width of each line. Returns a list of
    (points, widths, closed)."""
    n = len(lines)
    if n == 0:
        return []
    # end e = 2*i (start, outgoing = backwards) or 2*i+1 (end). Each end is
    # judged from its "trusted" part: position and tangent are taken after
    # skipping the last trim_widths·w, where a ridge bends toward a crossing.
    P = np.zeros((2 * n, 2))      # raw end position (for the neighbour query)
    Q = np.zeros((2 * n, 2))      # trusted end position
    T = np.zeros((2 * n, 2))      # trusted outgoing tangent
    WE = np.zeros(2 * n)
    L = np.array([arclength(p)[-1] for p in lines])
    for i, (p, wl) in enumerate(zip(lines, wls)):
        k = min(len(wl), 6)
        WE[2 * i], WE[2 * i + 1] = np.median(wl[:k]), np.median(wl[-k:])
        for e, at_end in ((2 * i, False), (2 * i + 1, True)):
            P[e] = p[-1] if at_end else p[0]
            Q[e], T[e] = _end_frame(p, at_end, trim_widths * WE[e], max(3.0, 2.0 * WE[e]))
    tree = cKDTree(P)
    cosA = math.cos(math.radians(max_angle_deg))
    cand = []
    for a, b in tree.query_pairs(max(4.0, gap_widths * float(WE.max()))):
        ia, ib = a // 2, b // 2
        w = max(WE[a], WE[b])
        gap = max(4.0, gap_widths * w)
        if float(np.hypot(*(P[b] - P[a]))) > gap or (ia == ib and L[ia] < 4 * gap):
            continue
        ta, tb = T[a], T[b]
        anti = -float(ta @ tb)               # 1 = perfectly collinear, facing
        if anti < cosA:
            continue
        v = Q[b] - Q[a]
        d = float(np.hypot(*v))
        fa, fb = float(ta @ v), float(-tb @ v)            # forward progress
        la = abs(ta[0] * v[1] - ta[1] * v[0])               # lateral offsets
        lb = abs(tb[0] * v[1] - tb[1] * v[0])
        lat = max(1.5, 0.5 * w + 0.15 * d)
        if fa < -0.5 * w or fb < -0.5 * w or la > lat or lb > lat:
            continue
        cost = d / w + 3.0 * math.acos(min(1.0, anti)) + (la + lb) / w
        cand.append((cost, a, b))
    cand.sort()
    partner = -np.ones(2 * n, dtype=int)
    for _, a, b in cand:
        if partner[a] < 0 and partner[b] < 0:
            partner[a], partner[b] = b, a
    # build chains
    seen = np.zeros(n, bool)
    out = []

    def oriented(i, enter_end):
        """Points (with width as a 3rd column) of line i walked so that we
        enter at end `enter_end`."""
        p = np.column_stack([lines[i], wls[i]])
        return p if enter_end == 2 * i else p[::-1]

    def chain_from(i, enter):
        seq = []
        cur, ent = i, enter
        closed = False
        while True:
            seen[cur] = True
            ex = 2 * cur + 1 if ent == 2 * cur else 2 * cur
            seq.append((cur, ent, ex))
            nxt = partner[ex]
            if nxt < 0:
                break
            j = nxt // 2
            if seen[j]:
                closed = (j == seq[0][0] and nxt == seq[0][1])
                break
            cur, ent = j, nxt
        return seq, closed

    order = []
    for i in range(n):
        if seen[i]:
            continue
        # start from a free end if the component has one
        e = 2 * i
        start, ent = i, e
        cur_e = e
        visited = {i}
        while partner[cur_e] >= 0:
            j = partner[cur_e] // 2
            if j in visited:
                break
            visited.add(j)
            other = 2 * j + 1 if partner[cur_e] == 2 * j else 2 * j
            start, ent = j, other
            cur_e = other
        order.append(chain_from(start, ent))

    def bridge(a, b):
        wa, wb = float(a[-1, 2]), float(b[0, 2])
        ta = _end_tangent(a[:, :2], True, max(3.0, 2.0 * wa))
        tb = -_end_tangent(b[:, :2], False, max(3.0, 2.0 * wb))
        h = _hermite(a[-1, :2], ta, b[0, :2], tb)
        u = np.linspace(0, 1, len(h) + 2)[1:-1, None]
        return np.column_stack([h, wa + (wb - wa) * u[:, 0]])

    for seq, closed in order:
        pieces = []
        for k, (i, ent, ex) in enumerate(seq):
            p = oriented(i, ent)
            if k > 0 or closed:
                p = _trim(p, False, trim_widths * WE[ent])
            if k < len(seq) - 1 or closed:
                p = _trim(p, True, trim_widths * WE[ex])
            pieces.append(p)
        pts = [pieces[0]]
        for k in range(1, len(pieces)):
            pts.append(bridge(pieces[k - 1], pieces[k]))
            pts.append(pieces[k])
        if closed:
            pts.append(bridge(pieces[-1], pieces[0]))
        q = np.vstack(pts)
        out.append((q[:, :2], q[:, 2], closed))
    return out


# --------------------------------------------------------------------------
# width along the normal
# --------------------------------------------------------------------------

def _fwhm(I, bg, pts, nrm, R):
    """Full width at half maximum of the ink profile through each point along
    its normal; the peak is the value at the point, above the paper level bg."""
    off = np.arange(0.0, R + 1e-9, 0.25)
    b = map_coordinates(bg, [pts[:, 1], pts[:, 0]], order=1, mode="nearest")
    halfw = []
    for sgn in (1.0, -1.0):
        xs = pts[:, 0:1] + sgn * off[None, :] * nrm[:, 0:1]
        ys = pts[:, 1:2] + sgn * off[None, :] * nrm[:, 1:2]
        v = map_coordinates(I, [ys.ravel(), xs.ravel()], order=1, mode="nearest").reshape(xs.shape)
        v = v - b[:, None]
        half = 0.5 * np.maximum(v[:, 0], 1e-6)
        below = v < half[:, None]
        below[:, 0] = False
        k = np.where(below.any(axis=1), below.argmax(axis=1), len(off) - 1)
        k = np.maximum(k, 1)
        v0 = v[np.arange(len(v)), k - 1]
        v1 = v[np.arange(len(v)), k]
        fr = np.clip((v0 - half) / np.maximum(v0 - v1, 1e-9), 0, 1)
        halfw.append(off[k - 1] + fr * (off[k] - off[k - 1]))
    return halfw[0] + halfw[1]


def _paper(I, w):
    """Local paper level of the ink signal (a smoothed local minimum)."""
    return gaussian_filter(minimum_filter(I, size=int(max(9, 6 * w)) | 1), 2 * w)


def _widths(I, bg, pts, wl):
    """FWHM width at each stroke point (px), median-smoothed along s; `wl`
    is the scale-derived width, used to bound the search."""
    w = float(np.median(wl))
    if len(pts) < 2:
        return np.asarray(wl, dtype=np.float64).copy()
    d = np.gradient(pts, axis=0)
    n = np.hypot(d[:, 0], d[:, 1])[:, None]
    t = d / np.maximum(n, 1e-9)
    nrm = np.column_stack([-t[:, 1], t[:, 0]])
    out = _fwhm(I, bg, pts, nrm, max(3.0, 2.5 * w))
    if len(out) >= 5:
        out = medfilt(out, 5)
    return np.clip(out, 0.5, 4 * w)


def _trim_tails(pts, wl, Is, bg, frac=0.5, max_trim=6.0):
    """Drop points at the two free ends whose ink contrast is below `frac` of
    the stroke's median: a coarse-scale ridge runs on ~σ past the ink tip."""
    c = (map_coordinates(Is, [pts[:, 1], pts[:, 0]], order=1, mode="nearest")
         - map_coordinates(bg, [pts[:, 1], pts[:, 0]], order=1, mode="nearest"))
    thr = frac * float(np.median(c))
    s = arclength(pts)
    ok = c >= thr
    i0 = int(np.argmax(ok)) if ok.any() else len(pts)
    i1 = len(pts) - int(np.argmax(ok[::-1])) if ok.any() else 0
    i0 = min(i0, int(np.searchsorted(s, max_trim)))
    i1 = max(i1, int(np.searchsorted(s, s[-1] - max_trim)))
    return pts[i0:i1], wl[i0:i1]


# --------------------------------------------------------------------------
# public
# --------------------------------------------------------------------------

def extract(gray: np.ndarray, *, width: float | None = None, sigma_frac: float = 0.4,
            n_scales: int = 1, scale_ratio: float = 2 ** 0.5, gamma: float = 1.5,
            k_hi: float = 12.0, k_lo: float = 5.0, hi_floor: float = 0.004,
            lo_floor: float = 0.002, max_turn: float = 40.0, gap_widths: float = 3.0,
            min_len_widths: float = 3.0, long_widths: float = 8.0, k_short: float = 20.0,
            fwhm_width: bool = True) -> Drawing:
    """gray float (H, W) in [0, 1], ink dark → Drawing of sub-pixel centrelines.

    width: typical line width (px) — only bounds the scale ladder and the
    minimum stroke length; estimated from the image when None.
    """
    g = np.asarray(gray, dtype=np.float64)
    H, W = g.shape
    w = float(width) if width else estimate_width(g)
    I = (1.0 - g).astype(np.float32)
    s0 = max(0.7, sigma_frac * w)
    sigmas = [s0 * scale_ratio ** (k - (n_scales - 1) / 2) for k in range(max(1, n_scales))]
    sigmas = [max(0.7, x) for x in sigmas]
    (S, OX, OY, TX, TY, AN, SIG), noise = _ridge_field(I, sigmas, gamma=gamma)
    hi = max(k_hi * noise, hi_floor)
    lo = max(k_lo * noise, lo_floor)
    idx_lines = _link(S, OX, OY, TX, TY, AN, SIG, lo, hi, max_turn_deg=max_turn)
    OXf, OYf, SGf = OX.ravel(), OY.ravel(), SIG.ravel()
    lines, wls = [], []
    for ids in idx_lines:
        r, c = np.divmod(ids, W)
        lines.append(np.column_stack([c + OXf[ids], r + OYf[ids]]).astype(np.float64))
        # the selected scale stands in for the local width (σ = sigma_frac·w)
        wls.append(SGf[ids].astype(np.float64) / sigma_frac)
    joined = _continue(lines, wls, gap_widths=gap_widths)
    bg = _paper(I, w)
    Is = gaussian_filter(I, 0.5)
    strokes = []
    for pts, wl, closed in joined:
        if len(pts) < 2:
            continue
        L = arclength(np.vstack([pts, pts[:1]]) if closed else pts)[-1]
        wm = float(np.median(wl))
        if L < max(3.0, min_len_widths * wm):
            continue
        ri = np.clip(np.round(pts[:, 1]).astype(int), 0, H - 1)
        ci = np.clip(np.round(pts[:, 0]).astype(int), 0, W - 1)
        med_s = float(np.median(S[ri, ci]))
        # a line is a seed-strength ridge for most of its length (hysteresis
        # only carries it through weak passages), and short marks must be
        # strong: faint short ridges are paper grain / plate tone
        if med_s < hi or (L < long_widths * wm and med_s < max(k_short * noise, hi)):
            continue
        if not closed:
            pts, wl = _trim_tails(pts, wl, Is, bg, max_trim=2.0 * wm)
            if len(pts) < 2:
                continue
        wd = _widths(Is, bg, pts, wl) if fwhm_width else wl
        strokes.append(Stroke(pts, width=wd, closed=bool(closed)))
    return Drawing(strokes, source="", size=(W, H),
                   meta={"method": "ridge", "w_px": w, "sigmas": [round(x, 3) for x in sigmas],
                         "hi": hi, "lo": lo, "noise": noise})
