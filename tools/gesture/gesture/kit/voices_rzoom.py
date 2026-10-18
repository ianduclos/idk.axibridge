"""Round 14, thread c1 (`rzoom`): the far Amazon stem zooming in and out along itself.

Ian, 2026-10-18: the Amazon river line, "along the same line, zooming in and
out, so you get the small dense twists, and gradually they get larger, and
smaller". The line is always the frozen far-view GRWL stem
(`river_stems/grwl_far_sb19`, 9684 points in metres): only the zoom changes
along it, as if a camera moved in and out while the river was drawn.

Two mechanisms (results/rzoom-2026-10-18.md compares them):

`magnify`  (mode "magnify", the headline) — variable magnification along the
           stem. The stem's own heading θ(u) along its arc length u is
           re-integrated with paper speed ds = c·z·du: where the zoom z is 1
           the far view's dense twists stay dense; where z grows the same
           bends open into large ones. Heading is continuous everywhere,
           curvature scales by 1/z. The zoom schedule is written over the
           PAPER line (τ = share of the drawn length = the time the pen
           takes), because the camera moves while the river is drawn; the
           river consumed follows from it (du ∝ dτ / z).
           Direction of travel: `course="free"` keeps every heading of the
           real river (the zoomed stretches go wherever their bends point)
           and fits the whole line to the box; `course="steer"` keeps the
           meanders exactly (θ minus its valley-scale low-pass, σ =
           `valley_w` channel widths) and lets a course heading ψ carry the
           valley: ψ follows the river's own valley turns, plus a turn back
           toward the box only when a look-ahead point would leave it (the
           frame's budget). The steered line is drawn at an absolute far
           scale (`far_mm_per_km`) and only ever shrunk to fit, never
           clipped — no stubs at the edge.
`window`   (mode "window", the literal camera) — K frames of a window on the
           stem that narrows geometrically toward `zoom`; every frame is
           scaled so its window spans the same sheet width, all frames
           centred on one stem point, one camera orientation. Each frame is
           ONE contiguous line; the frames are separate lines, superimposed
           (a moving window is a sequence of frames: joining them would need
           bridges the river does not contain). A frame whose bends leave
           the box is shortened from both ends until it fits.

Sampling at high zoom: the stem is sampled every w/4 (≈ 60 m) and was
smoothed at 1.5 w. Heading is interpolated linearly in u between segment
midpoints, so curvature is piecewise constant and the drawn line has no
vertices at any zoom. `smooth_w` adds a heading smoothing that grows with
zoom (σ = smooth_w · w · ln z / ln zoom channel widths, so z = 1 is never
touched) for when the stem's residual wobble shows.

Writes the channels `zoom` (z at each point) and `u_km` (where along the
stem, km) on every mark; `rzoom_ink`
(renderers_rzoom.py) can weight or colour the pen by it.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .arrangers_oehlen_found import FAR_STEMS, STEM_TILES, rotate, stem
from .core import P, voice

SHAPES = ("push", "pulses", "drift", "dive", "steps", "ramp_in", "ramp_out", "swell", "breath")
SIGMAS = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0)       # heading smoothing levels, stem samples


# ---------------------------------------------------------------------------
# the zoom schedule: g(τ) ∈ [0, 1] over the paper line, z = zoom ** g
# ---------------------------------------------------------------------------

def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def zoom_shape(shape: str, n: int, rng: np.random.Generator, recur: int = 3) -> np.ndarray:
    """g(τ) on n samples of τ ∈ [0, 1], in [0, 1] (log-zoom share).

    push      `recur` camera pushes: each a slow push in (eased, uneven
              length and depth) and a quick pull back out
    pulses    `recur` irregular zoom-ins at random places, each with its own
              depth, width and attack/decay asymmetry, far between them
    drift     a handheld camera: low-passed noise in log zoom
    dive      long far view, one gradual zoom in, a held close-up, a fast
              pull out, a short far tail (proportions jittered)
    steps     the camera stops at a few zoom levels, eased between them
    ramp_in   one-way: far → close
    ramp_out  one-way: close → far
    swell     symmetric far → close → far (the ornament: the control)
    breath    `recur` regular symmetric in-and-outs (ornament control 2)
    """
    t = np.linspace(0.0, 1.0, n)
    k = max(int(recur), 1)
    if shape == "swell":
        return np.sin(np.pi * t) ** 2
    if shape == "breath":
        return np.sin(np.pi * k * t) ** 2
    if shape == "ramp_in":
        return _smoothstep(t) ** 1.3
    if shape == "ramp_out":
        return _smoothstep(1 - t) ** 1.3
    if shape == "push":
        w = rng.uniform(0.6, 1.4, k)
        edges = np.r_[0.0, np.cumsum(w) / w.sum()]
        g = np.zeros(n)
        for a, b in zip(edges[:-1], edges[1:]):
            depth = rng.uniform(0.55, 1.0)
            lead = rng.uniform(0.0, 0.25)                         # far before the push starts
            peak = rng.uniform(0.72, 0.9)                         # where the cut back out starts
            ph = (t - a) / (b - a)
            m = (ph >= 0) & (ph < 1)
            x = ph[m]
            up = _smoothstep((x - lead) / max(peak - lead, 1e-6)) ** 1.6
            down = 1 - _smoothstep((x - peak) / (1 - peak))
            g[m] = depth * np.where(x < peak, up, down)
        g *= 1.0 / max(g.max(), 1e-9)
        return g
    if shape == "pulses":
        g = np.zeros(n)
        cs = np.sort(rng.uniform(0.08, 0.92, k))
        for c in cs:
            h = rng.uniform(0.45, 1.0)
            att = rng.uniform(0.02, 0.16)
            dec = att * rng.choice([rng.uniform(0.2, 0.5), rng.uniform(2.0, 4.0)])
            x = np.where(t < c, (c - t) / att, (t - c) / dec)
            g = np.maximum(g, h * np.exp(-0.5 * x * x))
        return g / max(g.max(), 1e-9)
    if shape == "drift":
        x = gaussian_filter1d(rng.standard_normal(n), n / (4.0 * k), mode="reflect")
        x = (x - x.mean()) / max(x.std(), 1e-9)
        g = 1 / (1 + np.exp(-1.6 * (x - 0.3)))                     # far a bit more often than close
        return (g - g.min()) / max(np.ptp(g), 1e-9)
    if shape == "dive":
        a = rng.uniform(0.25, 0.4)                                 # far until a
        b = a + rng.uniform(0.25, 0.35)                            # zoomed in by b
        c = min(b + rng.uniform(0.12, 0.2), 0.93)                  # held until c
        d = c + rng.uniform(0.02, 0.05)                            # out by d
        g = _smoothstep((t - a) / (b - a)) ** 1.4
        return np.where(t < c, g, 1 - _smoothstep((t - c) / (d - c)))
    if shape == "steps":
        levels = rng.permutation(np.r_[0.0, 1.0, rng.uniform(0.2, 0.8, max(k - 1, 1))])
        w = rng.uniform(0.5, 1.5, len(levels))
        edges = np.r_[0.0, np.cumsum(w) / w.sum()]
        g = np.full(n, levels[0])
        for i in range(1, len(levels)):
            e, tw = edges[i], rng.uniform(0.03, 0.08)
            g = g + (levels[i] - levels[i - 1]) * _smoothstep((t - e + tw / 2) / tw)
        return np.clip(g, 0.0, 1.0)
    raise ValueError(f"unknown zoom shape {shape!r}; one of {SHAPES}")


# ---------------------------------------------------------------------------
# geometry (pure)
# ---------------------------------------------------------------------------

def heading_profile(q: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """(u at segment midpoints m, unwrapped heading θ rad, total length m)."""
    d = np.diff(np.asarray(q, float), axis=0)
    h = np.linalg.norm(d, axis=1)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    u = np.r_[0.0, np.cumsum(h)]
    return 0.5 * (u[:-1] + u[1:]), th, float(u[-1])


def _theta_at(um, stack, sig_idx, uq):
    """θ at uq from the smoothing stack, blending levels by fractional index."""
    i0 = np.clip(np.floor(sig_idx).astype(int), 0, len(stack) - 1)
    i1 = np.clip(i0 + 1, 0, len(stack) - 1)
    f = np.clip(sig_idx - i0, 0.0, 1.0)
    th = np.vstack([np.interp(uq, um, s) for s in stack])        # (levels, n)
    cols = np.arange(len(uq))
    return th[i0, cols] * (1 - f) + th[i1, cols] * f


def _sigma_index(sig_samples):
    s = np.asarray(SIGMAS)
    return np.interp(sig_samples, s, np.arange(len(s)))


def pace_warp(g: np.ndarray, zoom: float, pace: float, n: int) -> np.ndarray:
    """Re-time a schedule g(T) written over camera time T onto n uniform
    samples of the drawn line τ, where dτ ∝ z**pace dT. pace 0: the zoom is
    keyed to the drawn line (time = pen time); pace 1: keyed to the river
    (the camera flies along the river at a constant ground speed, so zoomed
    stretches take more paper). In between, both."""
    g = np.clip(np.asarray(g, float), 0.0, 1.0)
    w = zoom ** (pace * g)
    tau = np.r_[0.0, np.cumsum(0.5 * (w[1:] + w[:-1]))]
    tau /= tau[-1]
    return np.interp(np.linspace(0, 1, n), tau, g)


def magnify(q: np.ndarray, g: np.ndarray, *, zoom: float, start: float, river: float,
            far_mm_per_km: float, channel_w: float, pace: float = 0.0, smooth_w: float = 0.0,
            course: str = "free", box=None, angle: float = 0.0, valley_w: float = 100.0,
            turn_mm: float = 45.0, look_mm: float = 40.0, step_mm: float = 0.12,
            max_mm: float = 12000.0, rng=None, interp: str = "linear") -> dict:
    """The stem q (metres) re-integrated at zoom z(τ) = zoom ** g(τ).

    g: log-zoom share over camera time (any length; re-timed by `pace`).
    start: share of the stem where the line begins; river: share of the
    stem (from start) the line consumes. The drawn length follows from the
    river and the schedule at the absolute scale far_mm_per_km (capped at
    max_mm by consuming less river).
    course "free": real headings, principal axis turned to `angle`; "steer":
    meanders exact, valley heading steered inside box (x0, y0, w, h).
    interp "linear" (heading interpolated between stem segments: no
    vertices at any zoom) or "step" (each stem segment keeps its own
    heading: the naive magnification, kept for the sampling check).
    Returns {"points" (mm, before any fit), "zoom", "u" (m along the stem),
    "length_mm", "river_km", "far_mm_per_km"}."""
    um, th, Ltot = heading_profile(q)
    hstep = Ltot / max(len(q) - 1, 1)
    c = far_mm_per_km / 1000.0                                      # mm per metre at z = 1
    zoom = max(float(zoom), 1.0)
    u0 = start * Ltot
    U = max(min(river * Ltot, Ltot - u0 - 2 * hstep), 10 * hstep)  # river metres the line consumes
    gt = pace_warp(g, zoom, pace, 20000)
    z0 = zoom ** gt
    F1 = float(np.mean(1.0 / z0))                                   # ∫ dτ / z
    length_mm = c * U / F1
    if length_mm > max_mm:
        U *= max_mm / length_mm
        length_mm = max_mm
    # integrate finely enough that the far view never skips a stem sample
    # (≤ 1/3 sample of river per step at z = 1), then keep a point every
    # step_mm of paper or every half stem sample of river, whichever is first
    ds = min(step_mm, c * hstep / 3.0)
    n = max(int(round(length_mm / ds)), 64) + 1
    ds = length_mm / (n - 1)
    zt = zoom ** np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(gt)), gt)
    F = np.r_[0.0, np.cumsum(0.5 * (1 / zt[1:] + 1 / zt[:-1]))]
    u = u0 + U * F / F[-1]
    um_step = 0.5 * (u[1:] + u[:-1])                                # heading of each step at its middle
    zm = 0.5 * (zt[1:] + zt[:-1])
    # heading, smoothed more where zoomed (z = 1 untouched)
    stack = [th if s == 0 else gaussian_filter1d(th, s, mode="nearest") for s in SIGMAS]
    if smooth_w > 0 and zoom > 1:
        sig = smooth_w * channel_w / hstep * np.log(zm) / np.log(zoom)
    else:
        sig = np.zeros(n - 1)
    theta = _theta_at(um, stack, _sigma_index(sig), um_step)
    if interp == "step":
        theta = th[np.clip(np.searchsorted(um - 0.5 * hstep, um_step, side="right") - 1, 0, len(th) - 1)]
    if course == "free":
        pts = np.vstack([[0.0, 0.0], np.cumsum(ds * np.column_stack([np.cos(theta), np.sin(theta)]), axis=0)])
        cen = pts.mean(axis=0)
        ev = np.linalg.eigh(np.cov((pts - cen).T))[1][:, -1]
        pts = rotate(pts, cen, angle - math.degrees(math.atan2(ev[1], ev[0])))
    elif course == "steer":
        if box is None:
            raise ValueError("course 'steer' needs the box")
        sv = valley_w * channel_w / hstep
        valley = np.interp(um_step, um, gaussian_filter1d(th, sv, mode="nearest"))
        mean = theta - valley                                          # the meanders, exact
        pts = _steer(mean, valley, ds, box, angle, turn_mm, look_mm, rng)
    else:
        raise ValueError(f"course must be 'free' or 'steer', got {course!r}")
    keep = _thin(np.arange(n) * ds, u, step_mm, hstep / 2.0)
    pts, z, u = pts[keep], zt[keep], u[keep]
    return {"points": pts, "zoom": z, "u": u, "length_mm": float(length_mm), "river_km": float(U / 1000.0),
            "far_mm_per_km": float(far_mm_per_km)}


def _steer(mean, valley, ds, box, angle, turn_mm, look_mm, rng=None):
    """Walk the meanders with a course ψ: ψ follows the valley's own turns;
    when a look-ahead point along ψ would leave the box, the course commits
    to a turn (at most 1/turn_mm rad per mm) toward a point drawn in the
    box's central half, until it heads there within 20°: the line crosses
    the sheet instead of gliding along its walls. Starts just inside the
    box's edge opposite `angle`, heading `angle`."""
    rng = rng if rng is not None else np.random.default_rng(0)
    x0, y0, w, h = box
    cx, cy = x0 + w / 2, y0 + h / 2
    a = math.radians(angle)
    dx, dy = math.cos(a), math.sin(a)
    r = min((w / 2 * 0.85) / max(abs(dx), 1e-9), (h / 2 * 0.85) / max(abs(dy), 1e-9))
    px, py = cx - dx * r, cy - dy * r
    n = len(mean)
    dval = np.r_[0.0, np.diff(valley)]
    psi = a
    out = np.empty((n + 1, 2))
    lim = ds / turn_mm
    m = 0.06 * min(w, h)
    target = None
    for i in range(n):
        out[i] = (px, py)
        psi += dval[i]
        if target is None:
            lx, ly = px + look_mm * math.cos(psi), py + look_mm * math.sin(psi)
            if not (x0 + m < lx < x0 + w - m and y0 + m < ly < y0 + h - m):
                target = (x0 + w * rng.uniform(0.25, 0.75), y0 + h * rng.uniform(0.25, 0.75))
        if target is not None:
            want = math.atan2(target[1] - py, target[0] - px)
            d = (want - psi + math.pi) % (2 * math.pi) - math.pi
            psi += max(-lim, min(lim, d))
            if abs(d) < math.radians(20):
                target = None
        th = mean[i] + psi
        px += ds * math.cos(th)
        py += ds * math.sin(th)
    out[n] = (px, py)
    return out


def _thin(s, u, ds_max, du_max):
    """Indices to keep: a point every ds_max of paper or du_max of river
    (whichever comes first), ends always kept."""
    keep = [0]
    ls, lu = s[0], u[0]
    for i in range(1, len(s) - 1):
        if s[i] - ls >= ds_max or u[i] - lu >= du_max:
            keep.append(i)
            ls, lu = s[i], u[i]
    keep.append(len(s) - 1)
    return np.asarray(keep)


def shrink_fit(points: np.ndarray, box, grow: bool = False) -> tuple[np.ndarray, float, np.ndarray]:
    """Centre points in box, scaling down only (or also up when grow): (pts, k, offset)."""
    x0, y0, w, h = box
    lo, hi = points.min(axis=0), points.max(axis=0)
    k = min(w / max(hi[0] - lo[0], 1e-9), h / max(hi[1] - lo[1], 1e-9))
    if not grow:
        k = min(k, 1.0)
    off = np.array([x0 + w / 2, y0 + h / 2]) - (lo + hi) / 2 * k
    return points * k + off, float(k), off


def window_frames(q: np.ndarray, *, frames: int, zoom: float, start: float, span_w: float,
                  channel_w: float, box, angle: float = 0.0, pan: float = 0.0) -> list[dict]:
    """K frames of a narrowing window on the stem (the literal camera).

    Frame k shows the stem stretch of span_w / zoom**(k/(K-1)) channel
    widths centred on stem point u_c(k) (u_c moves by `pan` × the far span
    over the frames: the camera pans while it zooms), all in one camera
    orientation (the far frame's principal axis turned to `angle`), scaled so
    each window spans the box width, its centre point on the box centre. A
    frame that leaves the box is shortened from both ends until it fits."""
    x0, y0, w, h = box
    um, th, Ltot = heading_profile(q)
    u = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
    W0 = span_w * channel_w
    uc0 = start * Ltot + W0 / 2
    far = q[(u >= uc0 - W0 / 2) & (u <= uc0 + W0 / 2)]
    ev = np.linalg.eigh(np.cov((far - far.mean(axis=0)).T))[1][:, -1]
    rot = angle - math.degrees(math.atan2(ev[1], ev[0]))
    s0 = 0.96 * w / max(np.ptp(rotate(far, far.mean(axis=0), rot)[:, 0]), 1e-9)   # far frame fills the width
    K = max(int(frames), 1)
    out = []
    centre = np.array([x0 + w / 2, y0 + h / 2])
    for k in range(K):
        f = k / max(K - 1, 1)
        zk = zoom ** f
        Wk = W0 / zk
        uc = min(max(uc0 + pan * W0 * f, Wk / 2), Ltot - Wk / 2)
        pc = np.array([np.interp(uc, u, q[:, 0]), np.interp(uc, u, q[:, 1])])
        scale = s0 * zk
        half = Wk / 2
        for _ in range(60):
            m = (u >= uc - half) & (u <= uc + half)
            seg = (rotate(q[m], pc, rot) - pc) * scale
            if len(seg) < 4 or (np.abs(seg[:, 0]).max() <= w / 2 * 0.99 and np.abs(seg[:, 1]).max() <= h / 2 * 0.99):
                break
            half *= 0.95
        out.append({"points": seg + centre, "zoom": zk, "span_m": 2 * half, "u_c": uc, "u": u[m]})
    return out


# ---------------------------------------------------------------------------
# the voice
# ---------------------------------------------------------------------------

@voice("river_zoom", params=[
    P("mode", "choice", "magnify", "magnify: local magnification along the line (one line); window: frames of a "
      "narrowing camera window, superimposed (one line per frame)", choices=("magnify", "window")),
    P("schedule", "choice", "push", "zoom schedule over the drawn line (magnify)", choices=SHAPES),
    P("recur", "int", 3, "how many pushes / pulses / steps / breaths (shape-dependent)", min=1, max=8),
    P("zoom", "float", 24.0, "largest magnification over the far view", min=1.0, max=80.0),
    P("start", "float", 0.05, "where along the stem the line starts (share)", min=0.0, max=0.95),
    P("river", "float", 1.0, "magnify: share of the stem (from start) the line consumes; the drawn length "
      "follows from it and the schedule", min=0.02, max=1.0),
    P("pace", "float", 0.4, "magnify: 0 the zoom is keyed to the drawn line, 1 to the river (zoomed stretches "
      "take more paper, far ones less)", min=0.0, max=1.0),
    P("max_mm", "float", 9000.0, "magnify: cap on the drawn length (consumes less river)", min=100.0, max=20000.0),
    P("far_mm_per_km", "float", 0.8, "the far view's scale (z = 1), mm of paper per km of river", min=0.2, max=3.0),
    P("course", "choice", "steer", "free: real headings, fitted to the box; steer: meanders exact, valley "
      "course kept inside the box (absolute scale, shrink-only fit)", choices=("free", "steer")),
    P("angle", "float", 0.0, "free: principal axis angle; steer: entry heading; window: camera angle (deg)",
      min=-180.0, max=180.0),
    P("smooth_w", "float", 0.0, "extra heading smoothing at the top zoom, channel widths (grows with ln z)",
      min=0.0, max=12.0),
    P("valley_w", "float", 100.0, "steer: valley low-pass, channel widths", min=20.0, max=400.0),
    P("turn_mm", "float", 45.0, "steer: tightest course turn radius at the walls, mm", min=10.0, max=400.0),
    P("frames", "int", 5, "window: number of frames", min=2, max=12),
    P("span_w", "float", 1600.0, "window: far frame span, channel widths", min=100.0, max=8000.0),
    P("pan", "float", 0.0, "window: camera pan along the stem over the frames, share of the far span",
      min=-1.0, max=1.0),
    P("heading", "choice", "linear", "magnify: linear (heading interpolated along the stem, no vertices) or step "
      "(each stem segment keeps its heading: the naive magnification, for the sampling check)",
      choices=("linear", "step")),
    P("tile", "choice", "SB19", "GRWL tile", choices=STEM_TILES),
    P("rank", "int", 0, "which stem, longest first", min=0, max=20),
    P("stems", "ref", FAR_STEMS, "frozen far-view stems (library kind river_stems)", kind="river_stems",
      optional=True),
], doc="the far Amazon stem zooming in and out along itself (real bends throughout; only the zoom changes)")
def river_zoom(ctx, *, mode, schedule, recur, zoom, start, river, pace, max_mm, far_mm_per_km, course, angle, smooth_w,
               valley_w, turn_mm, frames, span_w, pan, heading, tile, rank, stems):
    from .core import Mark  # noqa: PLC0415
    seg, wm, q = stem(ctx, stems, tile, rank)
    src = {"found": f"grwl:{tile}:seg{seg}", "channel_w_m": wm, "rights": "GRWL V01.01, Allen & Pavelsky 2018, CC BY 4.0"}
    box = ctx.box
    if mode == "window":
        fr = window_frames(q, frames=frames, zoom=zoom, start=start, span_w=span_w, channel_w=wm, box=box,
                           angle=angle, pan=pan)
        return [Mark(f["points"], {"zoom": np.full(len(f["points"]), f["zoom"]), "u_km": f["u"] / 1000.0},
                     {**src, "frame": i, "span_km": f["span_m"] / 1000.0,
                      "fit": {"scale": 1.0, "offset": [0.0, 0.0]}}) for i, f in enumerate(fr)]
    g = zoom_shape(schedule, 4000, ctx.rng("schedule", schedule), recur)
    r = magnify(q, g, zoom=zoom, start=start, river=river, pace=pace, max_mm=max_mm, far_mm_per_km=far_mm_per_km,
                channel_w=wm,
                smooth_w=smooth_w, course=course, box=box, angle=angle, valley_w=valley_w, turn_mm=turn_mm,
                rng=ctx.rng("steer"), interp=heading)
    pts, k, off = shrink_fit(r["points"], box, grow=(course == "free"))
    return [Mark(pts, {"zoom": r["zoom"], "u_km": r["u"] / 1000.0},
                 {**src, "schedule": schedule, "river_km": r["river_km"], "drawn_mm": r["length_mm"] * k,
                  "far_mm_per_km": far_mm_per_km * k, "fit": {"scale": k, "offset": [float(off[0]), float(off[1])]}})]
