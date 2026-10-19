"""Round 15, thread B (`lcorp`): line corpora as compositional technique.

The river zoom (round 14, `voices_rzoom.magnify`) generalised to ANY line:
a hand's chain, a drift of hands, a dance trail, the river stem. Every
source is reduced to one thing, its heading θ(u) along its own arc length,
and re-integrated at paper speed ds = c·z(τ)·du with z = zoom ** g(τ): the
far stretches stay dense twists, the zoomed ones open the same bends large.
Constant width throughout (the renderer is a plain wire; width never
follows zoom).

Pure functions (used by the modulators and arrangers of this thread too):

`source_line`    a long source polyline in its own units, from a hand chain,
                 a relay of hands, a dance trail or the river stem
`profile`        uniform resample at a grain → (u mid, θ, length, step)
`turn_length`    ℓ_turn: arc length per quarter turn of heading (the
                 source's own "bend size"; calibrates the far scale)
`scale_range`    turning density across octave scales → `range` (octaves
                 of fine structure under the bend size) and `zoom_cap`
                 (the zoom above which the source has no finer detail: the
                 balloons of round 14's c1)
`zoom_line`      any polyline through `magnify` at a calibrated far scale
`restyle_theta`  apply style: coarse heading of one line + the fine heading
                 of another (each band taken whole from one source)

Voice `lcorp_zoom`: any source through the zoom, free course, one line.
Channels: `zoom` (z per point), `u_src` (share along the source),
`voice` (index into meta["voices"] for relays).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .. import grammar as gm
from .core import Mark, P, channel_kind, voice
from .voices_rzoom import SHAPES, magnify, shrink_fit, zoom_shape

channel_kind("u_src", "linear")

SOURCES = ("hand", "relay", "dance", "river")
EFFECTORS = ("lhand", "rhand", "lfoot", "rfoot", "head")
RIVER_TURN_MM = None          # filled lazily: the river's own far quarter-turn at 0.8 mm/km (the round-14 scale)
UNIT = 1000.0                 # hand chains are integrated at R = 1000 units


# ---------------------------------------------------------------------------
# sources (pure given their inputs)
# ---------------------------------------------------------------------------

def hand_chain(g, rng, *, length_R: float, max_tokens: int = 40000) -> tuple[np.ndarray, list]:
    """One long κ-continuous chain of hand g, `length_R` reference lengths,
    grown chunk by chunk at the hand's own training-stroke lengths (as
    `hybrid.drift_line` with context "kappa", but unsteered: only θ(s)
    matters for the zoom). Returns (points in units, R = UNIT; tokens)."""
    toks: list = []
    total = 0.0
    Ls = g.stroke_lengths or [0.2]
    while total < length_R and len(toks) < max_tokens:
        Lc = min(float(Ls[int(rng.integers(len(Ls)))]), length_R - total + 1e-3)
        c, _ = gm.generate_tokens(g, rng, length=max(Lc, 1e-3), p_follow=gm.P_FOLLOW, end_fit=gm.END_FIT)
        if not c:
            continue
        if toks and toks[-1][0] in gm.SEG_KINDS and c[0][0] in gm.SEG_KINDS:
            _, first = gm._continuity(toks[-1], c[0], lock_prev=True)
            c = [first] + c[1:]
        toks += c
        total += gm.stroke_length(c)
    pts, _, _ = gm.tokens_to_points(toks, UNIT, step=1.0)
    return pts, toks


def relay_chain(grams, rng, *, length_R: float, turns_each=None) -> tuple[np.ndarray, np.ndarray]:
    """Hands in sequence, each WHOLE for its share of the line (never mixed):
    hand k's chain, then hand k+1's, heading continuous at the joint.
    Returns (points, voice index per point)."""
    k = len(grams)
    share = np.ones(k) / k if turns_each is None else np.asarray(turns_each, float) / np.sum(turns_each)
    out, vc = [], []
    pos, head = np.zeros(2), 0.0
    for i, g in enumerate(grams):
        p, _ = hand_chain(g, rng, length_R=float(length_R * share[i]))
        d = np.diff(p, axis=0)
        th0 = math.atan2(d[0, 1], d[0, 0])
        p = _rot(p - p[0], head - th0) + pos
        if out:
            p = p[1:]
        out.append(p)
        vc.append(np.full(len(p), float(i)))
        d = np.diff(np.vstack(out)[-3:], axis=0)
        head = math.atan2(d[-1, 1], d[-1, 0])
        pos = out[-1][-1]
    return np.vstack(out), np.concatenate(vc)


def dance_line(tr: dict, effector: str, *, t0: float = 0.0, seconds: float = 45.0, smooth_s: float = 0.08):
    """One effector's whole trail as one polyline (body heights), stillness
    deduped, lightly smoothed in time (the capture's jitter is not a bend)."""
    fps = tr["fps"]
    p = np.asarray(tr[f"{effector}_xy"], float)
    a0 = min(int(round(t0 * fps)), len(p) - 4)
    a1 = min(a0 + int(round(seconds * fps)), len(p))
    p = p[a0:a1]
    p = np.column_stack([gaussian_filter1d(p[:, j], smooth_s * fps, mode="nearest") for j in (0, 1)])
    keep = [0]
    for i in range(1, len(p)):
        if np.hypot(*(p[i] - p[keep[-1]])) >= 2e-4:
            keep.append(i)
    return p[np.asarray(keep)]


def _rot(p: np.ndarray, a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return p @ np.array([[c, s], [-s, c]])


# ---------------------------------------------------------------------------
# heading profile and scale measures
# ---------------------------------------------------------------------------

def resample(q: np.ndarray, h: float) -> np.ndarray:
    q = np.asarray(q, float)
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
    n = max(int(s[-1] / h), 3) + 1
    t = np.linspace(0, s[-1], n)
    return np.column_stack([np.interp(t, s, q[:, 0]), np.interp(t, s, q[:, 1])])


def profile(q: np.ndarray, grain: float):
    """(uniformly resampled points, θ unwrapped per segment, step h)."""
    r = resample(q, grain)
    d = np.diff(r, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    h = float(np.mean(np.linalg.norm(d, axis=1)))
    return r, th, h


def turn_length(th: np.ndarray, h: float, sigma: float = 2.0) -> float:
    """Arc length per quarter turn of heading, θ lightly smoothed (σ samples)
    so that sampling jitter does not count as turning."""
    ts = gaussian_filter1d(th, sigma, mode="nearest") if sigma > 0 else th
    turning = float(np.sum(np.abs(np.diff(ts))))
    return h * len(th) / max(turning / (math.pi / 2), 1e-9)


OCTAVES = np.arange(-4, 4)        # scales ℓ_turn · 2**k


def scale_spectrum(th: np.ndarray, h: float, lt: float) -> np.ndarray:
    """Turning density (rad per ℓ_turn) of θ smoothed at σ = ℓ_turn·2**k for
    k in OCTAVES: how much bending survives at each scale. A source with one
    bend size falls off a cliff below ℓ_turn's octave; a source with bends
    inside bends keeps turning at fine scales."""
    out = []
    for k in OCTAVES:
        sig = lt * 2.0 ** k / h
        ts = gaussian_filter1d(th, sig, mode="nearest") if sig >= 0.5 else th
        out.append(float(np.sum(np.abs(np.diff(ts)))) / (len(th) * h / lt))
    return np.asarray(out)


def fine_detail(th: np.ndarray, h: float, lt: float) -> dict:
    """Structure finer than the bend size, from the heading itself:

    `fine`     share of the line's turning that lives at scales under ℓ_turn/4
               (turning lost when θ is smoothed at ℓ_turn/4)
    `range`    octaves under ℓ_turn over which the band-limited turning is
               ≥ 15 % of its value at ℓ_turn/2 (wide range: bends in bends)
    `zoom_cap` the zoom at which the finest such octave reaches ~1 ℓ_turn on
               paper relative to the far view (2 ** range · 2): above it,
               a zoomed stretch has no smaller bends inside it (a balloon)."""
    spec = scale_spectrum(th, h, lt)
    total = spec[0]
    q = gaussian_filter1d(th, max(lt / 4 / h, 0.5), mode="nearest")
    fine = 1.0 - float(np.sum(np.abs(np.diff(q)))) / max(float(np.sum(np.abs(np.diff(th)))), 1e-9)
    # band turning per octave below ℓ_turn: spec[k] - spec[k+1]
    band = spec[:-1] - spec[1:]
    ks = OCTAVES[:-1]
    ref = band[ks == -1][0] if np.any(ks == -1) else band.max()
    rng_oct = 0
    for k in range(-1, OCTAVES[0] - 1, -1):
        b = band[ks == k]
        if len(b) and b[0] >= 0.15 * max(ref, 1e-9):
            rng_oct += 1
        else:
            break
    cap = float(2.0 ** (rng_oct + 1) * 2.0)
    return {"fine": round(fine, 3), "range": rng_oct, "zoom_cap": cap, "spectrum": np.round(spec, 3).tolist(),
            "total_turn_per_lt": round(float(total), 3)}


def detail_density(th: np.ndarray, h: float, lt: float, *, window: float = 3.0) -> np.ndarray:
    """Where the source has detail, in [0, 1] per sample: turning per length
    in a window of `window` quarter-turn lengths, as a log ratio to the
    line's median (½× median → 0, 4× → 1), eased. Smooth runs and long
    lines read 0; clusters of curls and corners read 1. The zoom leans in
    where there is something to open (round 14: zooming a smooth stretch
    gives a balloon)."""
    t = np.abs(np.diff(th, prepend=th[0]))
    dens = gaussian_filter1d(t, max(window * lt / h, 1.0), mode="nearest")
    med = max(float(np.median(dens)), 1e-12)
    x = (np.log2(np.maximum(dens, 1e-12) / med) + 1.0) / 3.0
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def river_turn_mm(q_river: np.ndarray, grain: float) -> float:
    """The round-14 river's far quarter-turn on paper (mm) at 0.8 mm/km: the
    default far scale every source is calibrated to."""
    _, th, h = profile(q_river, grain)
    return turn_length(th, h) * 0.8 / 1000.0


# ---------------------------------------------------------------------------
# the zoom on any line
# ---------------------------------------------------------------------------

def zoom_line(q: np.ndarray, g: np.ndarray, *, zoom: float, far_turn_mm: float, grain_turns: float = 1 / 24,
              pace: float = 0.5, max_mm: float = 9000.0, angle: float = 0.0, start: float = 0.0,
              share: float = 1.0, valley: float = 0.0, keep: float = 0.0, lead: float = 0.0,
              window: float = 3.0, lod: float = 0.0, reveal: float = 0.5) -> dict:
    """Any polyline q (any units) through the zoom.

    The source is resampled at grain = ℓ_turn × grain_turns (so a corner
    opens into an arc of z·grain on paper, never a facet), and its far scale
    c (mm per unit) is set so one quarter-turn of the source spans
    `far_turn_mm` at z = 1: every source starts equally dense, whatever its
    units. valley > 0 straightens the course: θ minus its low-pass at
    σ = valley·ℓ_turn plus that low-pass damped toward its mean (a hand
    chain has no valley, so it would wander; the river has one).
    Returns magnify's dict plus "turn_len", "c_mm_per_unit"."""
    _, th0, h0 = profile(q, max(_len(q) / 20000.0, 1e-9))
    lt = turn_length(th0, h0)
    r, th, h = profile(q, lt * grain_turns)
    th_raw = th
    if valley > 0:
        sv = valley * lt / h
        low = gaussian_filter1d(th, sv, mode="nearest")
        th = th - low + keep * (low - low.mean()) + low.mean()
        r = np.vstack([[0.0, 0.0], np.cumsum(h * np.column_stack([np.cos(th), np.sin(th)]), axis=0)])
    if lead > 0:
        d = detail_density(th_raw, h, lt, window=window)
        gu = np.interp(np.linspace(0, 1, len(g)), np.linspace(0, 1, len(d)), d)
        g = np.clip((1 - lead) * np.asarray(g, float) + lead * gu, 0.0, 1.0)
        pace = 1.0                                   # g is now written over the source: keyed to it
    if lod > 0:
        res = lod * far_turn_mm                      # paper resolution, mm: detail finer than this is unseen
        c = far_turn_mm / lt
        for _ in range(6):                           # calibrate on the turning the far view can SHOW
            lt_vis = turn_length(gaussian_filter1d(th_raw, max(res / c / h, 0.5), mode="nearest"), h, 0)
            c = far_turn_mm / lt_vis
        lt = lt_vis
        out = magnify_lod(r, g, zoom=zoom, c=c, res_mm=res, pace=pace, max_mm=max_mm, angle=angle,
                          start=start, share=share, reveal=reveal)
    else:
        c = far_turn_mm / lt
        out = magnify(r, g, zoom=zoom, start=start, river=share, far_mm_per_km=c * 1000.0, channel_w=4 * h,
                      pace=pace, max_mm=max_mm, course="free", angle=angle)
    out["turn_len"] = lt
    out["c_mm_per_unit"] = c
    out["u_share"] = (out["u"] / max(_len(r), 1e-9))
    return out


def magnify_lod(r: np.ndarray, g: np.ndarray, *, zoom: float, c: float, res_mm: float, pace: float = 0.5,
                max_mm: float = 9000.0, angle: float = 0.0, start: float = 0.0, share: float = 1.0,
                step_mm: float = 0.12, reveal: float = 0.5) -> dict:
    """`magnify` with a level of detail: the camera has a fixed resolution
    on paper (res_mm, the pen's scale), so at zoom z it shows the source's
    heading smoothed at σ = res_mm / (c·z**reveal) source units (reveal 1:
    the true camera, every zoom shows detail down to the pen, and a source
    with bends in bends looks the same at every zoom: the zoom disappears;
    reveal 0: one fixed band limit, the zoomed bends open into smooth
    balloons; between: the bends open large and carry some smaller ones). Far stretches are
    band-limited twists (as the river stem was smoothed at 1.5 w); a zoomed
    stretch shows the finer bends and corners the far view hid. A source
    with bends inside bends reveals new structure as it zooms; a uniform
    one has nothing new to show (its zoomed stretches are balloons).
    r: uniformly resampled source (step h). Free course only."""
    from .voices_rzoom import _thin, heading_profile, pace_warp, rotate  # noqa: PLC0415
    um, th, Ltot = heading_profile(r)
    h = Ltot / max(len(r) - 1, 1)
    zoom = max(float(zoom), 1.0)
    u0 = start * Ltot
    U = max(min(share * Ltot, Ltot - u0 - 2 * h), 10 * h)
    gt = pace_warp(g, zoom, pace, 20000)
    F1 = float(np.mean(1.0 / zoom ** gt))
    length_mm = c * U / F1
    if length_mm > max_mm:
        U *= max_mm / length_mm
        length_mm = max_mm
    ds = min(step_mm, c * h / 3.0)
    n = max(int(round(length_mm / ds)), 64) + 1
    ds = length_mm / (n - 1)
    zt = zoom ** np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(gt)), gt)
    F = np.r_[0.0, np.cumsum(0.5 * (1 / zt[1:] + 1 / zt[:-1]))]
    u = u0 + U * F / F[-1]
    ums = 0.5 * (u[1:] + u[:-1])
    zm = 0.5 * (zt[1:] + zt[:-1])
    sig = res_mm / (c * zm ** reveal) / h                          # samples
    smax = max(float(sig.max()), 1.0)
    levels = np.r_[0.0, np.geomspace(0.5, smax * 1.001, 14)]
    stack = np.vstack([np.interp(ums, um, th if s == 0 else gaussian_filter1d(th, s, mode="nearest"))
                       for s in levels])
    idx = np.interp(sig, levels, np.arange(len(levels)))
    i0 = np.clip(np.floor(idx).astype(int), 0, len(levels) - 1)
    i1 = np.clip(i0 + 1, 0, len(levels) - 1)
    f = idx - i0
    cols = np.arange(len(ums))
    theta = stack[i0, cols] * (1 - f) + stack[i1, cols] * f
    pts = np.vstack([[0.0, 0.0], np.cumsum(ds * np.column_stack([np.cos(theta), np.sin(theta)]), axis=0)])
    cen = pts.mean(axis=0)
    ev = np.linalg.eigh(np.cov((pts - cen).T))[1][:, -1]
    pts = rotate(pts, cen, angle - math.degrees(math.atan2(ev[1], ev[0])))
    keep = _thin(np.arange(n) * ds, u, step_mm, h / 2.0)
    return {"points": pts[keep], "zoom": zt[keep], "u": u[keep], "length_mm": float(length_mm),
            "river_km": float(U / 1000.0), "far_mm_per_km": float(c * 1000.0)}


def _len(q) -> float:
    return float(np.sum(np.linalg.norm(np.diff(np.asarray(q, float), axis=0), axis=1)))


# ---------------------------------------------------------------------------
# apply style: one line's course, another's bends
# ---------------------------------------------------------------------------

def restyle_theta(th_course: np.ndarray, th_style: np.ndarray, *, h: float, split: float, amount: float = 1.0):
    """θ = low-pass(course, σ=split) + amount × high-pass(style, σ=split),
    both on the same uniform step h (the style heading is cycled/cut to the
    course length). Each band is taken whole from one source: the course's
    turns above `split`, the style's bends below it. Never a mean of two
    headings at one scale."""
    n = len(th_course)
    s = np.asarray(th_style, float)
    if len(s) < n:
        reps = int(math.ceil(n / len(s)))
        parts, off = [], 0.0
        for _ in range(reps):
            parts.append(s - s[0] + off)
            off = parts[-1][-1]
        s = np.concatenate(parts)
    s = s[:n]
    sig = max(split / h, 0.5)
    lo = gaussian_filter1d(th_course, sig, mode="nearest")
    hi = s - gaussian_filter1d(s, sig, mode="nearest")
    return lo + amount * hi


def integrate(th: np.ndarray, h: float, start=(0.0, 0.0)) -> np.ndarray:
    return np.vstack([[start[0], start[1]], np.asarray(start, float) +
                      np.cumsum(h * np.column_stack([np.cos(th), np.sin(th)]), axis=0)])


# ---------------------------------------------------------------------------
# the voice
# ---------------------------------------------------------------------------

def get_source(ctx, *, source: str, hand: str, hands: list, trail: str, effector: str, length_R: float,
               river_start: float, river_share: float):
    """(points, voice channel or None, voices list, meta) for any source."""
    from .arrangers_oehlen_found import FAR_STEMS, stem  # noqa: PLC0415
    rng = np.random.default_rng(ctx.seed)
    if source == "hand":
        g = ctx.use("hand", hand)
        p, toks = hand_chain(g, rng, length_R=length_R)
        return p, None, [hand], {"source": f"hand:{hand}", "tokens": len(toks)}
    if source == "relay":
        grams = [ctx.use("hand", h) for h in hands]
        p, vc = relay_chain(grams, rng, length_R=length_R)
        return p, vc, list(hands), {"source": "relay:" + ">".join(hands)}
    if source == "dance":
        tr = ctx.use("dance_trail", trail)
        p = dance_line(tr, effector)
        return p, None, [f"dance:{trail}"], {"source": f"dance:{trail}:{effector}"}
    if source == "river":
        _, wm, q = stem(ctx, FAR_STEMS, "SB19", 0)
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
        a, b = river_start * s[-1], min(river_start + river_share, 1.0) * s[-1]
        m = (s >= a) & (s <= b)
        return q[m], None, ["river:grwl_sb19"], {"source": "river:grwl_far_sb19", "channel_w_m": wm,
                                                 "rights": "GRWL V01.01, Allen & Pavelsky 2018, CC BY 4.0"}
    raise ValueError(f"source must be one of {SOURCES}")


ZOOM_PARAMS = [
    P("schedule", "choice", "push", "zoom schedule over the drawn line; pinch (relay only): one push per "
      "hand, every handover in the far twists", choices=SHAPES + ("pinch",)),
    P("recur", "int", 3, "pushes / pulses / breaths", min=1, max=8),
    P("zoom", "float", 24.0, "largest magnification over the far view", min=1.0, max=64.0),
    P("pace", "float", 0.5, "0: zoom keyed to the drawn line; 1: keyed to the source", min=0.0, max=1.0),
    P("far_turn_mm", "float", 0.0, "a source quarter-turn on paper at z = 1, mm (0 = the round-14 river's, "
      "2.2 mm)", min=0.0, max=20.0),
    P("lod", "float", 0.8, "level of detail: the camera's resolution on paper in far quarter-turns (detail "
      "finer than lod × far_turn_mm is smoothed away; 0 = none, the raw source)", min=0.0, max=3.0),
    P("reveal", "float", 0.4, "how much finer detail a zoomed stretch shows: σ ∝ 1/z**reveal (0: one band "
      "limit, zoomed bends open into smooth balloons; 1: the true camera, the zoom hides itself in "
      "self-similar detail)", min=0.0, max=1.0),
    P("valley", "float", 4.0, "straighten the course: the heading's drift above this many quarter-turns is "
      "removed (0 = every heading the source's own; the river has a valley of its own and ignores it)",
      min=0.0, max=400.0),
    P("lead", "float", 0.0, "0: the schedule alone; 1: the zoom leans in where the source has detail "
      "(evens the line out: a dud kept as a control)", min=0.0, max=1.0),
    P("angle", "float", 0.0, "principal axis angle, deg", min=-180.0, max=180.0),
    P("drawn_mm", "float", 1500.0, "drawn length before fitting (hand sources grow until they reach it; "
      "others are capped at it)", min=100.0, max=20000.0),
]


def river_far_turn(ctx) -> float:
    global RIVER_TURN_MM
    if RIVER_TURN_MM is None:
        from .arrangers_oehlen_found import FAR_STEMS, stem  # noqa: PLC0415
        _, _, q = stem(ctx, FAR_STEMS, "SB19", 0)
        RIVER_TURN_MM = river_turn_mm(q, _len(q) / 20000.0)
    return RIVER_TURN_MM


def zoom_measures(r: dict, zoom: float) -> dict:
    """What the zoom did, read off the drawn line (paper mm, before fit):
    `contrast`  paper length of a quarter-turn in the top-zoom stretches
                over that in the far stretches (the river ≈ z: its bends
                open; a self-similar source ≈ 1: the zoom hides itself)
    `inner`     share of the top-zoom stretches' turning carried by features
                under 4 mm (0: balloons, smooth inside)"""
    p, z = np.asarray(r["points"]), np.asarray(r["zoom"])
    d = np.diff(p, axis=0)
    seg = np.linalg.norm(d, axis=1)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    dth = np.abs(np.diff(th, prepend=th[0]))
    zm = 0.5 * (z[1:] + z[:-1])
    lz = np.log(np.maximum(zm, 1.0)) / max(math.log(max(zoom, 1.0001)), 1e-9)
    hi, lo = lz >= 0.75, lz <= 0.15

    def qt(m):
        return float(seg[m].sum() / max(dth[m].sum() / (math.pi / 2), 1e-9)) if m.sum() > 10 else float("nan")

    step = max(float(np.median(seg)), 1e-6)
    ths = gaussian_filter1d(th, 4.0 / step, mode="nearest")
    dths = np.abs(np.diff(ths, prepend=ths[0]))
    inner = 1.0 - float(dths[hi].sum() / max(dth[hi].sum(), 1e-9)) if hi.sum() > 10 else float("nan")
    return {"contrast": round(qt(hi) / max(qt(lo), 1e-9), 2), "inner": round(inner, 3)}


def pinch_schedule(vc: np.ndarray, n: int = 4000, *, rng=None, peak=(0.55, 0.8)) -> np.ndarray:
    """A zoom schedule over the SOURCE for a relay: each hand gets one push
    (in slowly, out quickly) and every handover falls where the zoom is 1,
    in the far twists, so one hand passes into the next where both are
    smallest (whole, never averaged)."""
    vc = np.asarray(vc, float)
    t = np.linspace(0, 1, n)
    edges = [0.0] + [i / len(vc) for i in range(1, len(vc)) if vc[i] != vc[i - 1]] + [1.0]
    g = np.zeros(n)
    rng = rng if rng is not None else np.random.default_rng(0)
    for a, b in zip(edges[:-1], edges[1:]):
        ph = (t - a) / max(b - a, 1e-9)
        m = (ph >= 0) & (ph < 1)
        pk = rng.uniform(*peak)
        x = ph[m]
        up = _ss((x - 0.12) / max(pk - 0.12, 1e-6)) ** 1.4
        down = 1 - _ss((x - pk) / max(0.9 - pk, 1e-6))
        g[m] = np.where(x < pk, up, down) * rng.uniform(0.75, 1.0)
    return g / max(g.max(), 1e-9)


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def run_zoom(ctx, q, *, schedule, recur, zoom, pace, far_turn_mm, lod, reveal, valley, lead, angle, drawn_mm,
             tag="schedule", regrow=None, g_fn=None, keep_all=False):
    """The zoom on q with the voice's params; returns (zoom_line dict, measures). regrow(n) → a longer
    source, called while the source is too short to reach drawn_mm (hand chains). keep_all: never cut the
    source to drawn_mm (a relay keeps every hand)."""
    ftm = far_turn_mm if far_turn_mm > 0 else river_far_turn(ctx)
    g = zoom_shape(schedule, 4000, ctx.rng(tag, schedule), recur)
    tries = 0
    while True:
        if g_fn is not None:                       # a schedule written over the source (keyed to it)
            g, pace = g_fn(q), 1.0
        r = zoom_line(q, g, zoom=zoom, far_turn_mm=ftm, pace=pace, max_mm=20000.0 if keep_all else drawn_mm, angle=angle, valley=valley,
                      lod=lod, reveal=reveal, lead=lead)
        if regrow is None or r["length_mm"] >= 0.99 * drawn_mm or tries >= 4:
            break
        tries += 1
        q = regrow(tries)
    meas = zoom_measures(r, zoom)
    meas["source_turns"] = round(_len(q) / r["turn_len"], 1)
    return r, meas


@voice("lcorp_zoom", params=[
    P("source", "choice", "hand", "hand: one hand's long chain; relay: hands in turn, each whole; dance: one "
      "effector's trail; river: the frozen far Amazon stem", choices=SOURCES),
    P("hand", "ref", "hokusai", "source hand", kind="hand"),
    P("hands", "refs", ["hokusai", "matisse"], "relay: the hands in turn", kind="hand", min_len=1, max_len=6),
    P("trail", "ref", "mantis", "dance: the frozen dance window", kind="dance_trail"),
    P("effector", "choice", "rhand", "dance: which body end", choices=EFFECTORS),
    P("length_R", "float", 30.0, "hand / relay: starting chain length in reference lengths (doubled until the "
      "line reaches drawn_mm)", min=2.0, max=200.0),
    P("river_start", "float", 0.05, "river: where along the stem (share)", min=0.0, max=0.95),
    P("river_share", "float", 1.0, "river: share of the stem", min=0.02, max=1.0),
    *ZOOM_PARAMS,
], doc="any line (hand chain, relay of hands, dance trail, river) zooming in and out along itself at constant "
       "width, free course, with a level of detail; the far scale is calibrated so every source starts "
       "equally dense")
def lcorp_zoom(ctx, *, source, hand, hands, trail, effector, length_R, river_start, river_share, schedule, recur,
               zoom, pace, far_turn_mm, lod, reveal, valley, lead, angle, drawn_mm):
    kw = dict(source=source, hand=hand, hands=hands, trail=trail, effector=effector, river_start=river_start,
              river_share=river_share)
    q, vc, voices, meta = get_source(ctx, length_R=length_R, **kw)
    box = {}

    def regrow(i):
        q2, vc2, _, _ = get_source(ctx, length_R=min(length_R * 2 ** i, 1600.0), **kw)
        box["vc"] = vc2
        return q2

    if source == "river":
        valley, lod = 0.0, 0.0            # the stem has its own valley and was band-limited at 1.5 w
    box["vc"] = vc
    g_fn = None
    if source == "relay" and schedule == "pinch":
        g_fn = lambda _q: pinch_schedule(box["vc"], rng=ctx.rng("pinch"))  # noqa: E731
    r, meas = run_zoom(ctx, q, schedule="push" if schedule == "pinch" else schedule, recur=recur, zoom=zoom,
                       pace=pace, far_turn_mm=far_turn_mm, lod=lod, reveal=reveal, valley=valley, lead=lead,
                       angle=angle, drawn_mm=drawn_mm, regrow=regrow if source in ("hand", "relay") else None,
                       g_fn=g_fn, keep_all=(source == "relay"))
    vc = box.get("vc", vc)
    pts, k, off = shrink_fit(r["points"], ctx.box, grow=True)
    ch = {"zoom": r["zoom"], "u_src": np.clip(r["u_share"], 0, 1)}
    if vc is not None:
        sq = np.linspace(0, 1, len(vc))
        ch["voice"] = vc[np.clip(np.searchsorted(sq, ch["u_src"]), 0, len(vc) - 1)].astype(float)
    else:
        ch["voice"] = np.zeros(len(pts))
    if source == "relay":
        from ._score import Score  # noqa: PLC0415
        sc = Score()
        lids = [sc.layer("line", "lcorp_zoom", part=ctx.part, params={"hand": h}, label=f"relay hand {k}: {h}")
                for k, h in enumerate(voices)]
        s_mm = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        v = ch["voice"]
        for i in np.flatnonzero(np.diff(v) != 0):
            a, b = int(v[i]), int(v[i + 1])
            sc.relate("handover", lids[a], lids[b], at=pts[i + 1], s=(s_mm[i + 1], s_mm[i + 1]),
                      note=f"at z={ch['zoom'][i + 1]:.1f}: the next hand takes over in the far twists, whole")
        sc.decide(schedule=schedule, zoom=zoom, reveal=reveal, density="one line")
        ctx.note("score", sc.to_json())
    return [Mark(pts, ch, {**meta, "voices": voices, "measure": meas, "turn_len": r["turn_len"],
                           "drawn_mm": r["length_mm"] * k,
                           "fit": {"scale": k, "offset": [float(off[0]), float(off[1])]}})]
