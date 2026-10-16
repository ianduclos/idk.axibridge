"""Orientation-field streamline tracing (a light cousin of PolyVector-field
vectorisation, Bessmeltsev & Solomon 2019).

Pipeline
--------
1. Ink mask (default `mask="bg"`): paper level by a coarse 90th-percentile
   filter, darkness = paper − gray blurred at `blur` px, thresholded at
   max(`nsig` robust σ, `rel` × local max) — fuses grainy crayon into solid
   strokes and keeps faint lines Sauvola drops. `mask="sauvola"` reproduces
   the bench's reference mask. Small objects removed, pinholes filled;
   global line width w = median 2·DT on the mask skeleton.
   Re-centring weights = the top 40% (`core`) of each cross-section's
   darkness profile — markedly lower κ error than whole-profile centroids.
2. Orientation field: structure tensor of the grayscale (derivative σ≈1,
   integration ρ≈0.6 w). Line direction = minor eigenvector, coherence =
   (λ1−λ2)/(λ1+λ2).
3. Seeds: skeleton pixels, coherent ones first (by coherence·min(DT, w/2)),
   then the rest; a seed already inside a traced tube is skipped.
4. Tracing, both ways from a seed, RK2 steps of h ≈ 0.4 w along the field
   direction whose sign matches the current heading. Every step the point is
   re-centred along the normal onto the darkness-weighted centroid of the
   contiguous ink cross-section through it.
   * The cross-section doubles as the crossing detector: where it is much
     wider than the running local width (another line runs along our
     normal: X crossing, T bar, corner blob) or the field is incoherent /
     disagrees with the heading, the tracer COASTS — heading frozen, no
     re-centring — which is what carries a stroke straight through an X.
     (The "second direction" of a PolyVector field is never computed
     explicitly; choosing the branch closest to the heading reduces to
     keeping the heading while the cross-section is ambiguous.)
   * Stops: leaving ink; a wide (junction) coast longer than `max_wide_w`·w
     or one that exits into paper (T end / corner) — then the stroke is
     trimmed back to the middle of the wide run; a turn > `turn_deg` over
     2 w of arc; entering ink already traced by a stroke running PARALLEL
     to us (crossing someone else's ink at an angle is allowed); returning
     to its own start → closed stroke.
5. Every step paints a tube (radius ≈ half the local width + 1 px) into an
   owner/orientation/arc-length raster, so the same line is never traced
   twice. Strokes shorter than `min_len_w`·w are dropped (specks, spurs).
   Output is lightly Gaussian-smoothed; width = cross-section run length.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import (distance_transform_edt, gaussian_filter, gaussian_filter1d,
                           maximum_filter, percentile_filter, zoom)
from skimage.filters import threshold_sauvola
from skimage.morphology import remove_small_holes, remove_small_objects, skeletonize

from .core import Drawing, Stroke


# --------------------------------------------------------------------------
# fields
# --------------------------------------------------------------------------

def _background(gray: np.ndarray, k: int = 8) -> np.ndarray:
    """Paper level: 90th percentile over ~9k px blocks, smoothed, upsampled."""
    H, W = gray.shape
    k = max(1, min(k, H // 4, W // 4))
    h2, w2 = H // k, W // k
    small = gray[:h2 * k, :w2 * k].reshape(h2, k, w2, k).mean(axis=(1, 3))
    bs = gaussian_filter(percentile_filter(small, 90, size=9), 2.0)
    bg = zoom(bs, (H / h2, W / w2), order=1)
    out = np.empty_like(gray)
    hh, ww = min(H, bg.shape[0]), min(W, bg.shape[1])
    out[:hh, :ww] = bg[:hh, :ww]
    out[hh:, :] = out[hh - 1:hh, :]
    out[:, ww:] = out[:, ww - 1:ww]
    return out


def _ink_sauvola(gray: np.ndarray, min_area: int):
    """The bench's reference-style mask (kept for comparison runs)."""
    H, W = gray.shape
    win = max(15, (min(H, W) // 60) | 1)
    thr = threshold_sauvola(gray, window_size=win, k=0.2)
    mask = remove_small_objects(gray < thr, max_size=min_area)
    skel = skeletonize(mask)
    dt = distance_transform_edt(mask)
    w = max(float(np.median(2 * dt[skel])) if skel.any() else 3.0, 1.5)
    mask = remove_small_holes(mask, max_size=max(4, int(0.6 * w * w)))
    return mask, np.clip(thr - gray, 0.0, None) * mask, w


def _ink(gray: np.ndarray, sigma: float, rel: float, nsig: float, min_area: int):
    """Ink mask from background-subtracted, lightly blurred darkness.

    Unlike Sauvola, this keeps faint grainy crayon (lithographs) as ONE
    solid stroke instead of a scatter of grains. Threshold = the larger of
    `nsig` robust noise sigmas and `rel` × the local darkness maximum (so a
    crisp etched line is cut near its half-maximum and does not swell into
    its neighbours)."""
    d = gaussian_filter(_background(gray) - gray, sigma)
    med = float(np.median(d))
    mad = 1.4826 * float(np.median(np.abs(d - med)))
    lm = maximum_filter(d, size=15)
    mask = (d > med + nsig * max(mad, 1e-4)) & (d > rel * lm)
    mask = remove_small_objects(mask, max_size=min_area)
    skel = skeletonize(mask)
    dt = distance_transform_edt(mask)
    w = float(np.median(2 * dt[skel])) if skel.any() else 3.0
    w = max(w, 1.5)
    mask = remove_small_holes(mask, max_size=max(4, int(0.6 * w * w)))
    dark = np.clip(d - med, 0.0, None) * mask
    return mask, dark, w


def _tensor(gray: np.ndarray, w: float, sigma: float):
    sd = math.hypot(1.0, sigma)
    gx = gaussian_filter(gray, sd, order=(0, 1))
    gy = gaussian_filter(gray, sd, order=(1, 0))
    rho = 0.6 * w + 0.5
    jxx = gaussian_filter(gx * gx, rho)
    jxy = gaussian_filter(gx * gy, rho)
    jyy = gaussian_filter(gy * gy, rho)
    T = np.stack([jxx, jxy, jyy], axis=-1).astype(np.float64)
    tr = jxx + jyy
    coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / np.maximum(tr, 1e-12)
    coh[tr < 1e-10] = 0.0
    return T, coh


# --------------------------------------------------------------------------
# tracer
# --------------------------------------------------------------------------

class _Tracer:
    def __init__(self, gray, *, mask="bg", blur=1.0, rel=0.4, nsig=5.0, min_area=30, step=None, core=0.6, shift_frac=0.625, tol_w=0.0, coh_min=0.3,
                 align_deg=30.0, wide_factor=1.7, max_wide_w=4.5, turn_deg=60.0,
                 min_len_w=4.0, smooth_steps=1.0):
        self.gray = gray
        self.H, self.W = gray.shape
        if mask == "sauvola":
            self.mask, self.dark, self.w = _ink_sauvola(gray, min_area)
        else:
            self.mask, self.dark, self.w = _ink(gray, blur, rel, nsig, min_area)
        self.maskf = self.mask.astype(np.float64)
        self.T, self.coh = _tensor(gray, self.w, blur)
        w = self.w
        self.h = float(step) if step else float(np.clip(0.4 * w, 0.75, 3.0))
        self.coh_min = coh_min
        self.core = core
        self.cos_align = math.cos(math.radians(align_deg))
        self.wide_factor = wide_factor
        self.max_wide = max_wide_w * w + 2.0
        self.cos_turn = math.cos(math.radians(turn_deg))
        self.turn_k = max(2, int(round(2.0 * w / self.h)))
        self.exit_k = max(2, int(math.ceil((1.5 * w + 2.0) / self.h)))
        self.cos_exit = math.cos(math.radians(35.0))
        self.mod_factor = 1.35
        self.min_len = min_len_w * w
        self.smooth_steps = smooth_steps
        # normal profile: offsets in px at 0.5 px spacing
        R = 2.5 * w + 3.0
        self.offs = np.arange(-R, R + 1e-9, 0.5)
        self.c = int(np.argmin(np.abs(self.offs)))
        self.max_shift = max(0.5, shift_frac * self.h)
        self.tol = max(2, int(round(tol_w * w / 0.5)))     # off-ink tolerance, samples
        # consumed rasters
        self.owner = np.full((self.H, self.W), -1, np.int32)
        self.ori = np.zeros((self.H, self.W), np.float32)     # line angle mod pi
        self.sst = np.zeros((self.H, self.W), np.float32)     # arc-length stamp
        self.lag = 2.5 * w + 3.0
        self.cos_par = math.cos(math.radians(25.0))
        self._discs = {}

    # -- sampling ----------------------------------------------------------
    def _bilinear_T(self, x, y):
        H, W = self.H, self.W
        if x < 0 or y < 0 or x > W - 1 or y > H - 1:
            return None
        x0 = min(int(x), W - 2); y0 = min(int(y), H - 2)
        fx = x - x0; fy = y - y0
        q = self.T[y0:y0 + 2, x0:x0 + 2]
        v = ((1 - fy) * ((1 - fx) * q[0, 0] + fx * q[0, 1])
             + fy * ((1 - fx) * q[1, 0] + fx * q[1, 1]))
        return v

    def field(self, x, y, hx, hy):
        """Line direction at (x, y) signed to match heading; (dx, dy, coh)."""
        v = self._bilinear_T(x, y)
        if v is None:
            return hx, hy, 0.0
        a, b, c = v
        tr = a + c
        if tr <= 1e-12:
            return hx, hy, 0.0
        coh = math.sqrt((a - c) ** 2 + 4 * b * b) / tr
        phi = 0.5 * math.atan2(2 * b, a - c)
        dx, dy = -math.sin(phi), math.cos(phi)
        if dx * hx + dy * hy < 0:
            dx, dy = -dx, -dy
        return dx, dy, coh

    def _sample(self, arr, xs, ys):
        H, W = self.H, self.W
        xs = np.clip(xs, 0, W - 1.001); ys = np.clip(ys, 0, H - 1.001)
        x0 = xs.astype(np.intp); y0 = ys.astype(np.intp)
        fx = xs - x0; fy = ys - y0
        return ((1 - fy) * ((1 - fx) * arr[y0, x0] + fx * arr[y0, x0 + 1])
                + fy * ((1 - fx) * arr[y0 + 1, x0] + fx * arr[y0 + 1, x0 + 1]))

    def profile(self, x, y, nx, ny):
        """Cross-section along the normal through (x, y).
        Returns (run_len_px, centroid_offset_px, saturated) or None if the
        point is not on ink."""
        o = self.offs
        xs = x + o * nx; ys = y + o * ny
        m = self._sample(self.maskf, xs, ys) >= 0.5
        c = self.c
        if not m[c]:
            # tolerate being up to 1 px off the ink
            t = self.tol
            near = np.nonzero(m[c - t:c + t + 1])[0]
            if len(near) == 0:
                return None
            c = c - t + int(near[np.argmin(np.abs(near - t))])
        left = np.nonzero(~m[:c])[0]
        right = np.nonzero(~m[c + 1:])[0]
        a = left[-1] + 1 if len(left) else 0
        b = c + right[0] if len(right) else len(m) - 1
        sat = (not len(left)) or (not len(right))
        run = (b - a + 1) * 0.5
        d = self._sample(self.dark, xs[a:b + 1], ys[a:b + 1])
        d = np.clip(d - self.core * d.max(), 0.0, None)   # the profile's core
        sw = d.sum()
        cen = float((d * o[a:b + 1]).sum() / sw) if sw > 1e-12 else 0.5 * (o[a] + o[b])
        return run, cen, sat

    # -- consumed tube -----------------------------------------------------
    def _disc(self, r):
        if r not in self._discs:
            yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
            sel = xx * xx + yy * yy <= r * r + 0.5
            self._discs[r] = (yy[sel], xx[sel])
        return self._discs[r]

    def paint(self, sid, x, y, ang, s, width):
        r = int(math.ceil(0.5 * width + 1.0))
        dy, dx = self._disc(r)
        yi = int(round(y)) + dy; xi = int(round(x)) + dx
        ok = (yi >= 0) & (yi < self.H) & (xi >= 0) & (xi < self.W)
        yi = yi[ok]; xi = xi[ok]
        free = self.owner[yi, xi] < 0
        yi = yi[free]; xi = xi[free]
        self.owner[yi, xi] = sid
        self.ori[yi, xi] = ang
        self.sst[yi, xi] = s
        return yi, xi

    # -- one direction -----------------------------------------------------
    def trace_dir(self, sid, x, y, hx, hy, width0, s_sign, closable):
        """Trace one way from (x, y) with heading (hx, hy).
        Returns (points, widths, closed, stop_reason)."""
        h = self.h
        pts = []; wid = []; heads = []; painted = []
        wl = width0                     # running local width
        s = 0.0
        frozen = False                  # heading frozen (junction / blob)
        cdx = cdy = 0.0                 # the frozen heading
        wide_start = None               # first wide step of this junction
        wide_last = 0
        wide_len = 0.0
        calm = 0                        # normal cross-sections since freezing
        closed = False
        trim_to = None
        reason = "maxsteps"
        for _ in range(200000):
            if frozen:
                d2x, d2y = cdx, cdy
            else:                       # RK2 along the field
                d1x, d1y, c1 = self.field(x, y, hx, hy)
                if c1 < self.coh_min or d1x * hx + d1y * hy < self.cos_align:
                    d1x, d1y = hx, hy
                d2x, d2y, c2 = self.field(x + 0.5 * h * d1x, y + 0.5 * h * d1y, d1x, d1y)
                if c2 < self.coh_min or d2x * hx + d2y * hy < self.cos_align:
                    d2x, d2y = d1x, d1y
            nx_, ny_ = x + h * d2x, y + h * d2y
            if not (0 <= nx_ <= self.W - 1 and 0 <= ny_ <= self.H - 1):
                reason = "border"; break
            prof = self.profile(nx_, ny_, -d2y, d2x)
            if prof is not None and not frozen:
                run = prof[0]
                if prof[2] or run > self.mod_factor * wl + 1.0:
                    # a junction starts: freeze the heading at the chord of
                    # the last ~2w (not the field, already blurred by it)
                    frozen = True
                    j = max(0, len(pts) - self.turn_k)
                    if len(pts) - j >= 2:
                        cdx, cdy = x - pts[j][0], y - pts[j][1]
                        n = math.hypot(cdx, cdy)
                        cdx, cdy = (cdx / n, cdy / n) if n > 1e-9 else (hx, hy)
                    else:
                        cdx, cdy = hx, hy
                    d2x, d2y = cdx, cdy
                    nx_, ny_ = x + h * d2x, y + h * d2y
                    calm = 0
                    if not (0 <= nx_ <= self.W - 1 and 0 <= ny_ <= self.H - 1):
                        reason = "border"; break
                    prof = self.profile(nx_, ny_, -d2y, d2x)
            px, py = -d2y, d2x
            if prof is None:            # left the ink
                reason = "paper"
                if wide_start is not None:
                    trim_to = (wide_start + wide_last) // 2
                    reason = "junction_end"
                break
            run, cen, sat = prof
            wide = sat or run > self.wide_factor * wl + 1.5
            normal = (not sat) and run <= self.mod_factor * wl + 1.0
            width_here = wl
            if wide:
                if wide_start is None:
                    wide_start = len(pts); wide_len = 0.0
                wide_len += h
                wide_last = len(pts); calm = 0
                if wide_len > self.max_wide:
                    trim_to = wide_start
                    reason = "wide"; break
            elif normal:
                if frozen:
                    calm += 1
                    if calm >= self.exit_k:
                        # clear of the junction and of the field's blur of
                        # it: the line we are on must continue our heading
                        fx_, fy_, cf = self.field(nx_, ny_, cdx, cdy)
                        if (wide_start is not None and cf >= self.coh_min
                                and fx_ * cdx + fy_ * cdy < self.cos_exit):
                            trim_to = (wide_start + wide_last) // 2
                            reason = "junction_turn"; break
                        frozen = False; wide_start = None
                if not frozen:
                    sh = max(-self.max_shift, min(self.max_shift, cen))
                    nx_ += sh * px; ny_ += sh * py
                    wl = 0.8 * wl + 0.2 * run
                    width_here = run
            else:
                calm = 0
            nx_ = min(max(nx_, 0.0), self.W - 1.0)
            ny_ = min(max(ny_, 0.0), self.H - 1.0)
            # displacement heading
            ddx, ddy = nx_ - x, ny_ - y
            dn = math.hypot(ddx, ddy)
            if dn < 1e-9:
                reason = "stall"; break
            ddx /= dn; ddy /= dn
            s_new = s + dn
            # consumed ink: stop if it is a parallel line (retrace / merge)
            yi, xi = int(round(ny_)), int(round(nx_))
            ow = self.owner[yi, xi]
            if ow >= 0:
                oa = float(self.ori[yi, xi])
                par = abs(math.cos(oa) * ddx + math.sin(oa) * ddy) > self.cos_par
                if ow != sid:
                    if par and not frozen:
                        reason = "merge"; break
                else:
                    st = float(self.sst[yi, xi])
                    if abs(s_sign * s_new - st) > self.lag and par:
                        if closable and abs(st) < 2.0 * wl + 2 * h and s_new > 4 * self.w:
                            closed = True
                        reason = "self"; break
            # sharp turn over ~2w of arc
            heads.append((ddx, ddy))
            if len(heads) > self.turn_k:
                ox, oy = heads[-1 - self.turn_k]
                if ox * ddx + oy * ddy < self.cos_turn:
                    reason = "turn"; break
            x, y, hx, hy, s = nx_, ny_, ddx, ddy, s_new
            pts.append((x, y)); wid.append(width_here)
            painted.append(self.paint(sid, x, y, math.atan2(hy, hx), s_sign * s, width_here))
        if trim_to is not None:
            pts = pts[:trim_to]; wid = wid[:trim_to]
            for yi, xi in painted[trim_to:]:     # give the overshoot back
                self.owner[yi, xi] = -1
        return pts, wid, closed, reason

    def trace(self, sid, x0, y0):
        dx, dy, coh = self.field(x0, y0, 1.0, 0.0)
        prof = self.profile(x0, y0, -dy, dx)
        if prof is None:
            return None
        run, cen, sat = prof
        if not sat:
            sh = max(-self.max_shift, min(self.max_shift, cen))
            x0 = min(max(x0 - sh * dy, 0.0), self.W - 1.0)
            y0 = min(max(y0 + sh * dx, 0.0), self.H - 1.0)
            w0 = run
        else:
            w0 = self.w
        w0 = min(w0, 2.0 * self.w) if sat else w0
        self.paint(sid, x0, y0, math.atan2(dy, dx), 0.0, w0)
        f, fw, closed, rf = self.trace_dir(sid, x0, y0, dx, dy, w0, +1.0, True)
        if closed:
            P = [(x0, y0)] + f
            Wd = [w0] + fw
            rb = "closed"
        else:
            b, bw, _, rb = self.trace_dir(sid, x0, y0, -dx, -dy, w0, -1.0, False)
            P = b[::-1] + [(x0, y0)] + f
            Wd = bw[::-1] + [w0] + fw
        return np.asarray(P, float), np.asarray(Wd, float), closed, (rb, rf)


def _smooth(p: np.ndarray, sd: float, closed: bool) -> np.ndarray:
    if sd <= 0 or len(p) < 5:
        return p
    mode = "wrap" if closed else "nearest"
    q = np.column_stack([gaussian_filter1d(p[:, 0], sd, mode=mode),
                         gaussian_filter1d(p[:, 1], sd, mode=mode)])
    if not closed:
        q[0], q[-1] = p[0], p[-1]
    return q


def extract(gray: np.ndarray, **kw) -> Drawing:
    """Scan (float [0, 1], ink dark) → Drawing of traced strokes, in px."""
    gray = np.asarray(gray, dtype=np.float64)
    H, W = gray.shape
    tr = _Tracer(gray, **kw)
    skel = skeletonize(tr.mask)
    dt = distance_transform_edt(tr.mask)
    ys, xs = np.nonzero(skel)
    coh = tr.coh[ys, xs]
    strength = coh * np.minimum(dt[ys, xs], 0.5 * tr.w)
    coherent = coh >= 0.5
    # coherent seeds first (strongest first), then everything else
    order = np.lexsort((np.arange(len(ys)), -strength, ~coherent))
    strokes = []
    sid = 0
    for i in order:
        y, x = int(ys[i]), int(xs[i])
        if tr.owner[y, x] >= 0:
            continue
        res = tr.trace(sid, float(x), float(y))
        if tr.owner[y, x] < 0:          # never let a failed seed be retried
            tr.owner[y, x] = sid
        sid += 1
        if res is None:
            continue
        P, Wd, closed, why = res
        if len(P) < 3:
            continue
        P = _smooth(P, tr.smooth_steps, closed)
        seg = np.linalg.norm(np.diff(np.vstack([P, P[:1]]) if closed else P, axis=0), axis=1)
        if seg.sum() < tr.min_len:
            continue
        strokes.append(Stroke(P, width=np.maximum(Wd, 0.5), closed=closed,
                              meta={"stop": list(why)}))
    return Drawing(strokes, source="", size=(W, H),
                   meta={"method": "flow", "w_px": tr.w, "step_px": tr.h})
