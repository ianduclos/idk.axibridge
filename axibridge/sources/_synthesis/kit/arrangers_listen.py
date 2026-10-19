# FROZEN from research commit c712045: tools/gesture/gesture/kit/arrangers_listen.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 15 thread A `listen`: layers that listen to each other, built on ccolour.

Ian, 2026-10-19: "messing with regimes, layers, listening (not always imitating, can be exaggerating
or imitating on another line style, or perhaps other ideas im not thinking about)".

ccolour (the keeper) made colour carry what a line does. This composer makes the *relations between
layers* the material. A sheet is a short history: one or two speakers draw, then each later layer
takes an earlier layer's line as its input and does something with one of its gestures. Every
relation is a mechanism, and every one that fires is written into the sheet's score
(`_score.Score`, `ctx.note("score", …)`) with its kind, src, dst and where.

The vocabulary (kinds in the score):

  spliced into the listener's own line (the listener's hand runs, takes up the other's gesture for a
  stretch, then resumes; heading stays continuous, and the whole line is turned and placed so that the
  borrowed stretch sits beside the gesture it heard):
    imitate     the gesture, close beside the source (4–8 mm), in the listener's pen: two voices in
                unison for a stretch, then they part
    exaggerate  the gesture pushed: its turns amplified about their own trend and its scale enlarged;
                it starts on the source's gesture and swings wider, in a heavier pen
    translate   the same move in another line style: the gesture's course in the listener's own hand
                (the listener's small turns laid on the source's course), or ruled (the gesture as a
                few straight chords)
    refuse      the listener's own line, placed across the source; wherever it would come within r of
                the source it walks the source's halo instead (a detour at constant distance)

  separate small layers, later in the drawing order:
    echo        the gesture again, far away on the sheet, smaller, in the source's hue at 400; two or
                three repeats that decay in scale
    calm        (own) the understatement, exaggerate's opposite: the gesture with its turns flattened
                to a quiet arc whose two ends land on the gesture's own ends, a bowstring under it
    nest        (own) a small copy of the source's own gesture set inside a crook of the source's line,
                sized to the space the line encloses there
    bind        (own) a ligature from the end of one layer to the start of another, tangent at both
                ends; its pen hands over from the first layer's to the second's halfway

  the void:
    mask        the 4507 move: a torn void at an ambiguous point (where two layers overlap). Layers
                drawn before it are cut by it (kind `mask`); layers drawn after it cross it (kind
                `ignore`). Its edge is drawn only in part. Rare on purpose (`mask_p`).

  aware overlaps (every crossing between two different layers is handled, never left bare):
    weave       the two lines alternate which one passes under (a short gap in the under line), so the
                eye cannot settle which layer is in front
    yield       the later line always gives way: a wider gap in it at each crossing (cut away)

Middle density by default: the composer stops adding relation layers when the ink reaches the sheet's
density band and the band itself is bounded away from both extremes. Found matter is optional and
never the κ chart: `river_zoom` (free course, push schedule) at constant width.

Internal parts take seeds sheet seed + 400 + k (speakers / listeners) and + 460 + k (river), so the
recipe alone reproduces the sheet. Ink with `oehlen_found_ink`; preview with ccolour's `render_pens`.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter1d

from ._score import Score
from .arrangers_ccolour import DARK, FRAMES, HAND_POOL, HUE, LIGHT, _part, _pick, _u
from .arrangers_oehlen_found import arclen, cover_polygon, resample, rotate
from .core import Mark, P, arranger

# ccolour's pool minus meander69, whose closed polygons read as paint-program doodles at this scale
LISTEN_HANDS = [h for h in HAND_POOL if h != "meander69"]

STEP = 0.5                                   # mm between samples on every working line
SPLICED = ("imitate", "exaggerate", "translate", "refuse")
LATER = ("echo", "calm", "nest", "bind")
VOCAB = SPLICED + LATER
CAP = {"imitate": 2, "exaggerate": 1, "translate": 2, "refuse": 1, "echo": 1, "calm": 1, "nest": 1, "bind": 1}
WEIGHTS = {"imitate": 0.22, "exaggerate": 0.09, "translate": 0.2, "refuse": 0.13,
           "echo": 0.14, "calm": 0.1, "nest": 0.07, "bind": 0.05}


# ---------------------------------------------------------------------------
# heading geometry (every line is resampled at STEP, so ds is constant)
# ---------------------------------------------------------------------------

def headings(p: np.ndarray) -> np.ndarray:
    d = np.diff(p, axis=0)
    return np.unwrap(np.arctan2(d[:, 1], d[:, 0]))


def integrate(th: np.ndarray, start, step: float = STEP) -> np.ndarray:
    steps = step * np.c_[np.cos(th), np.sin(th)]
    return np.vstack([np.asarray(start, float)[None], np.asarray(start, float) + np.cumsum(steps, axis=0)])


def turning(p: np.ndarray) -> float:
    th = headings(p)
    return float(np.abs(np.diff(th)).sum()) if len(th) > 1 else 0.0


def chord_normal(p: np.ndarray) -> np.ndarray:
    c = p[-1] - p[0]
    n = np.array([-c[1], c[0]])
    L = float(np.linalg.norm(n))
    return n / L if L > 1e-9 else np.array([0.0, 1.0])


def similar_to(q: np.ndarray, a, b) -> np.ndarray:
    """q moved, turned and scaled so its first point lands on a and its last on b."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    u, v = q[-1] - q[0], b - a
    lu = float(np.linalg.norm(u))
    if lu < 1e-9:
        return q - q[0] + a
    k = float(np.linalg.norm(v)) / lu
    ang = math.atan2(v[1], v[0]) - math.atan2(u[1], u[0])
    R = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
    return (q - q[0]) @ R.T * k + a


def push(g: np.ndarray, gain: float, scale: float, trend_mm: float) -> np.ndarray:
    """Exaggerate (gain > 1) or calm (gain < 1): the turns amplified about their own trend."""
    th = headings(g)
    if trend_mm <= 0:
        base = np.full_like(th, math.atan2(*(g[-1] - g[0])[::-1]))
        base = base + np.round((th.mean() - base[0]) / (2 * math.pi)) * 2 * math.pi
    else:
        base = gaussian_filter1d(th, max(trend_mm / STEP, 1.0), mode="nearest")
    return integrate(base + gain * (th - base), g[0], STEP * scale)


def amplify(g: np.ndarray, amp: float, scale: float) -> np.ndarray:
    """Exaggerate: in the gesture's chord frame its sideways excursions are multiplied by amp, then the
    whole is enlarged by scale about its centre. The same shape, pushed (it stays recognisable)."""
    a, b = g[0], g[-1]
    c = b - a
    L = float(np.linalg.norm(c))
    if L < 1e-6:
        q = (g - g.mean(axis=0)) * amp * scale + g.mean(axis=0)
        return resample(q, STEP)
    u = c / L
    n = np.array([-u[1], u[0]])
    x, y = (g - a) @ u, (g - a) @ n
    q = a + np.outer(x, u) + np.outer(y * amp, n)
    m = q.mean(axis=0)
    return resample((q - m) * scale + m, STEP)


def ruled(g: np.ndarray, tol: float) -> np.ndarray:
    """The gesture as a few straight chords (Douglas–Peucker), resampled: the ruled line style."""
    from shapely.geometry import LineString  # noqa: PLC0415
    q = np.asarray(LineString(g).simplify(tol, preserve_topology=False).coords)
    return resample(q, STEP) if len(q) >= 2 else g


def in_hand(g: np.ndarray, own: np.ndarray, sigma_mm: float, amp: float) -> np.ndarray:
    """The gesture's course carrying the listener's own small turns (translate into another hand)."""
    th = headings(g)
    course = gaussian_filter1d(th, sigma_mm / STEP, mode="nearest")
    o = headings(own)
    reps = int(math.ceil(len(th) / max(len(o), 1)))
    o = np.tile(o, reps)[: len(th)] if reps > 1 else o[: len(th)]
    detail = o - gaussian_filter1d(o, sigma_mm / STEP, mode="nearest")
    return integrate(course + amp * detail, g[0])


def meander(g: np.ndarray, amp: float, wave_mm: float, sigma_mm: float) -> np.ndarray:
    """The gesture's course drawn as a meandering river line (bends of one wavelength along it)."""
    th = headings(g)
    course = gaussian_filter1d(th, sigma_mm / STEP, mode="nearest")
    s = np.arange(len(th)) * STEP
    th2 = course + amp * np.sin(2 * math.pi * s / wave_mm) * np.clip(np.sin(math.pi * s / max(s[-1], STEP)), 0.0, 1.0) ** 0.3
    q = integrate(th2, g[0])
    return similar_to(q, g[0], g[-1])


def pick_gesture(rng, line: np.ndarray, Lmin: float, Lmax: float, *, open_ends: bool = False, crowd=None,
                 min_turn: float = 2.0):
    """A stretch of the line with character: enough turning to be a gesture, not a scribble.
    `crowd(points) -> 0…1` (optional) prefers stretches where other layers are not already
    talking, so conversations spread over the sheet instead of piling up. Returns (i0, i1) or None."""
    n = len(line)
    best, arg = -1.0, None
    for _ in range(40):
        m = int(_u(rng, Lmin, Lmax) / STEP)
        if m >= n - 2:
            m = n - 3
        if m < 12:
            return None
        i0 = int(rng.integers(0, n - m))
        g = line[i0:i0 + m + 1]
        T = turning(g)
        lo, hi = g.min(axis=0), g.max(axis=0)
        span = float(np.linalg.norm(hi - lo))
        if span < 0.3 * m * STEP or T < min_turn:
            continue
        if open_ends and float(np.linalg.norm(g[-1] - g[0])) < 0.4 * m * STEP:
            continue
        sc = min(T, 6.5) - max(T - 8.0, 0.0) * 0.8
        sc *= _u(rng, 0.8, 1.2)
        if crowd is not None:
            sc *= 1.0 - 0.75 * crowd(g)
        if sc > best:
            best, arg = sc, (i0, i0 + m)
    return arg


# ---------------------------------------------------------------------------
# the sheet as layers
# ---------------------------------------------------------------------------

class Layer:
    def __init__(self, lid, role, technique, ink, pen, lines, part=None, params=None, label=""):
        self.lid, self.role, self.technique = lid, role, technique
        self.ink, self.pen = ink, float(pen)
        self.lines = [np.asarray(l, float) for l in lines]
        self.part, self.params, self.label = part, dict(params or {}), label
        self.inks = [ink] * len(self.lines)      # per-line pen (a listener's borrowed stretch, bind's halves)
        self.full = max(self.lines, key=lambda q: arclen(q)[-1]) if self.lines else None   # the whole line, uncut


def light_of(c: str) -> str:
    h = HUE.get(c, c)
    return "black" if h == "black" else f"{h}-400"


def _inside(p, W, H, m):
    return bool((p[:, 0] >= m).all() and (p[:, 0] <= W - m).all() and (p[:, 1] >= m).all()
                and (p[:, 1] <= H - m).all())


def fit_tails(line, i0, i1, W, H, m):
    """Keep a placed line on the paper without clipping it: its tails (before i0 and after i1) are
    scaled toward the borrowed stretch's ends (heading kept, so no corner) until they fit. None if
    even the borrowed stretch is off the paper or a tail would have to shrink below 0.3."""
    if not _inside(line[i0:i1 + 1], W, H, m):
        return None
    out = line.copy()
    for tail, anchor in ((slice(0, i0), line[i0]), (slice(i1 + 1, len(line)), line[i1])):
        seg = line[tail]
        if not len(seg):
            continue
        for f in (1.0, 0.85, 0.7, 0.58, 0.48, 0.4, 0.33):
            q = anchor + (seg - anchor) * f
            if _inside(q, W, H, m):
                out[tail] = q
                break
        else:
            return None
    return out


def raster(layers, W, H, cell=2.0, skip=()):
    nx, ny = int(math.ceil(W / cell)), int(math.ceil(H / cell))
    occ = np.zeros((ny, nx), bool)
    for L in layers:
        if L.lid in skip:
            continue
        for l in L.lines:
            ij = np.clip((l / cell).astype(int), 0, [nx - 1, ny - 1])
            occ[ij[:, 1], ij[:, 0]] = True
    return occ


def ink_mm(layers) -> float:
    return float(sum(arclen(l)[-1] for L in layers for l in L.lines if len(l) > 1))


# ---------------------------------------------------------------------------
# the composer
# ---------------------------------------------------------------------------

class Composer:
    def __init__(self, ctx, hands, *, density, mask_p, river_p, kinds, pens):
        self.ctx = ctx
        self.W, self.H = ctx.frame
        self.m = 7.0
        self.hands = list(hands or LISTEN_HANDS)
        self.rng = ctx.rng("compose")
        self.score = Score()
        self.layers: list[Layer] = []
        self.k = 0                                  # internal part counter
        self.density = float(density)
        # the density band, mm of ink per cm² (4507 sits near 18 with its heavy runs; 14007 lower)
        self.band = (8.0 + 6.0 * density, 12.0 + 8.0 * density)
        self.mask_p, self.river_p = float(mask_p), float(river_p)
        self.kinds = [k for k in VOCAB if k in kinds]
        self.palette = self._palette(pens)
        # who carries colour: accent = one pen for every voice and a second pen only where a line
        # listens (the borrowed stretch, the detour, the echo); pair = two speakers, two camps, a
        # borrowed stretch in its source's pen; mono = one pen, relations by shape alone
        self.mode = "mono" if len(self.palette) < 2 else _pick(self.rng, ["accent", "pair", "mono"], [0.55, 0.3, 0.15])
        self.mask = None
        rng = self.rng
        # a direction for the sheet: along its long axis, give or take
        a = (0.0 if self.W >= self.H else 90.0) + _u(rng, -35, 35) + (180.0 if rng.random() < 0.5 else 0.0)
        self.flow = np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])
        self.flow_deg = round(a % 360.0, 1)
        # weight: one bold voice at most (a speaker or the exaggeration), never everything
        self.bold = round(_pick(rng, [0.6, 0.8, 1.0], [0.35, 0.4, 0.25]), 2)
        self.bold_speaker = int(_pick(rng, [0, 1, -1], [0.7, 0.12, 0.18]))

    # -- pens ---------------------------------------------------------------
    def _palette(self, pens):
        rng = self.rng
        n = int(pens) if pens else int(rng.choice([2, 3], p=[0.55, 0.45]))
        first = _pick(rng, DARK[:6], [0.4, 0.15, 0.12, 0.1, 0.13, 0.1])
        pal = [first]
        pool = [c for c in DARK if HUE[c] != HUE[first]]
        while len(pal) < n and pool:
            c = _pick(rng, pool)
            pal.append(c)
            pool = [q for q in pool if HUE[q] != HUE[c]]
        return pal

    def pen_other_than(self, *cs):
        free = [c for c in self.palette if c not in cs]
        return _pick(self.rng, free) if free else self.palette[-1]

    @property
    def voice_pen(self):
        return self.palette[0]

    @property
    def accent(self):
        return self.palette[1] if len(self.palette) > 1 else self.palette[0]

    def own_pen(self, src):
        """The pen of a listener's own line."""
        if self.mode == "pair":
            return self.pen_other_than(src.ink) if src.ink in self.palette[:2] else self.palette[0]
        return self.voice_pen

    def heard_pen(self, src, own):
        """The pen of the stretch where a line listens."""
        return {"accent": self.accent, "pair": src.ink, "mono": own}[self.mode]

    # -- lines --------------------------------------------------------------
    def hand_line(self, hand, length, wh):
        k = self.k
        self.k += 1
        box = (0.0, 0.0, float(wh[0]), float(wh[1]))
        marks = _part(self.ctx, 400 + k, {"id": "hand", "hand": hand, "length": float(length), "joins": "smooth"},
                      box).voice(box)
        pts = max((m.points for m in marks), key=lambda q: arclen(q)[-1])
        return resample(pts, STEP), 400 + k

    def river_line(self, wh):
        k = self.k
        self.k += 1
        box = (0.0, 0.0, float(wh[0]), float(wh[1]))
        spec = {"id": "river_zoom", "mode": "magnify", "schedule": "push", "course": "free",
                "zoom": round(_u(self.rng, 10, 26), 1), "recur": int(self.rng.integers(2, 4)),
                "start": round(_u(self.rng, 0.0, 0.7), 3), "pace": 0.5,
                "max_mm": round(_u(self.rng, 0.9, 1.5) * (wh[0] + wh[1]) * 2, 0)}
        marks = _part(self.ctx, 460 + k, spec, box).voice(box)
        pts = max((m.points for m in marks), key=lambda q: arclen(q)[-1])
        return resample(pts, STEP), 460 + k, spec

    def add(self, role, technique, ink, pen, lines, part=None, params=None, label=""):
        lid = self.score.layer(role, technique, part=part, pen={"ink": ink, "mm": round(float(pen), 2)},
                               params=params, label=label)
        L = Layer(lid, role, technique, ink, pen, lines, part, params, label)
        self.layers.append(L)
        return L

    def crowd(self, skip=()):
        """A function: the share of a stretch's points that land on other layers' ink (dilated)."""
        from scipy.ndimage import binary_dilation  # noqa: PLC0415
        cell = 3.0
        occ = binary_dilation(raster(self.layers, self.W, self.H, cell, skip), iterations=2)

        def f(q):
            ij = np.clip((q / cell).astype(int), 0, [occ.shape[1] - 1, occ.shape[0] - 1])
            return float(occ[ij[:, 1], ij[:, 0]].mean())
        return f

    def echo_spot(self, gc):
        """Where an echo lands: 35–90 mm from what it echoes, at the fringe of the drawing (some ink
        near, none on top), never out alone in the blank where it would read as a stray mark."""
        cell = 2.0
        occ = raster(self.layers, self.W, self.H, cell)
        d = distance_transform_edt(~occ) * cell
        ny, nx = d.shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        cx, cy = (xx + 0.5) * cell, (yy + 0.5) * cell
        edge = np.minimum.reduce([cx, cy, self.W - cx, self.H - cy])
        dist = np.hypot(cx - gc[0], cy - gc[1])
        ok = (dist > 35.0) & (dist < 90.0) & (edge > 16.0) & (d > 6.0) & (d < 16.0)
        score = np.where(ok, d + self.rng.random(d.shape) * 3.0, -1.0)
        j = int(np.argmax(score))
        if score.ravel()[j] < 0:
            return None, 0.0                              # no fringe: no echo (never a lone mark in the blank)
        return np.array([cx.ravel()[j], cy.ravel()[j]]), float(d.ravel()[j])

    def density_now(self):
        return ink_mm(self.layers) / (self.W * self.H / 100.0)

    def empty_spot(self, avoid=None, far=0.0, skip=()):
        """A point in the emptiest part of the paper (distance to ink), away from `avoid` by `far`."""
        cell = 2.0
        occ = raster(self.layers, self.W, self.H, cell, skip)
        d = distance_transform_edt(~occ) * cell
        ny, nx = d.shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        cx, cy = (xx + 0.5) * cell, (yy + 0.5) * cell
        edge = np.minimum.reduce([cx, cy, self.W - cx, self.H - cy])
        score = np.minimum(d, edge - 6.0)
        if avoid is not None and far > 0:
            score = np.where(np.hypot(cx - avoid[0], cy - avoid[1]) < far, -1.0, score)
        flat = np.argsort(score.ravel())[::-1][:40]
        j = int(flat[int(self.rng.integers(0, min(8, len(flat))))])
        return np.array([cx.ravel()[j], cy.ravel()[j]]), float(score.ravel()[j])

    # -- acts ---------------------------------------------------------------
    def speaker(self, i):
        W, H, rng = self.W, self.H, self.rng
        hand = _pick(rng, self.hands)
        wh = (W * _u(rng, 0.65, 0.95), H * _u(rng, 0.65, 0.95))
        line, part = self.hand_line(hand, round(_u(rng, 3.0, 5.0), 1), wh)
        # first speaker off-centre, upstream of the flow; the second downstream, overlapping it a little
        f = self.flow
        if i == 0:
            c = np.array([W / 2, H / 2]) - f * np.array([W, H]) * _u(rng, 0.05, 0.18)
        else:
            c = np.array([W / 2, H / 2]) + f * np.array([W, H]) * _u(rng, 0.12, 0.25)
        c = c + rng.normal(0, 0.04, 2) * [W, H]
        # turned freely on a squarish sheet; on a strip or a tall sheet only a little, or it shrinks to fit
        tilt = 30.0 if max(W, H) / min(W, H) < 1.3 else 8.0
        # the line's own long axis laid along the sheet's long axis first, then turned a little
        ev = np.linalg.eigh(np.cov((line - line.mean(axis=0)).T))[1][:, -1]
        axis = math.degrees(math.atan2(ev[1], ev[0]))
        turn = (0.0 if W >= H else 90.0) - axis + _u(rng, -tilt, tilt)
        line = rotate(line, line.mean(axis=0), turn)
        line = self._settle(line - line.mean(axis=0) + c)
        ink = self.palette[1] if (i == 1 and self.mode == "pair") else self.palette[0]
        # weight hierarchy: the first speaker is usually the bold voice; listeners are hairlines
        pen = self.bold if i == self.bold_speaker else round(_pick(rng, [0.35, 0.45]), 2)
        return self.add("speaker", "hand", ink, pen, [line], part, {"hand": hand, "box_wh": [round(v, 1) for v in wh],
                                                                  "turn_deg": round(turn, 1),
                                                                  "centre": [round(float(v), 1) for v in line.mean(axis=0)]},
                        f"{hand} speaks")

    def river(self):
        W, H, rng = self.W, self.H, self.rng
        wh = (W * _u(rng, 0.6, 0.9), H * _u(rng, 0.18, 0.35))
        line, part, spec = self.river_line(wh)
        ang = math.degrees(math.atan2(self.flow[1], self.flow[0]))
        line = rotate(line, line.mean(axis=0), ang + _u(rng, -12, 12))
        c = np.array([W * _u(rng, 0.35, 0.65), H * _u(rng, 0.3, 0.7)])
        line = self._settle(line - line.mean(axis=0) + c)
        return self.add("found", "river_zoom", light_of(self.palette[-1]), 0.3, [line], part, spec,
                        "the river, zoomed (constant width)")

    def _settle(self, line):
        """Shrink about the centre and shift until the whole line sits inside the margin."""
        W, H, m = self.W, self.H, self.m
        lo, hi = line.min(axis=0), line.max(axis=0)
        k = min(1.0, (W - 2 * m) / max(hi[0] - lo[0], 1e-9), (H - 2 * m) / max(hi[1] - lo[1], 1e-9))
        mid = (lo + hi) / 2
        line = (line - mid) * k + mid
        lo, hi = line.min(axis=0), line.max(axis=0)
        shift = np.clip(np.array([m, m]) - lo, 0, None) - np.clip(hi - np.array([W - m, H - m]), 0, None)
        return line + shift

    def _borrow(self, kind, g, own, rng):
        """The borrowed stretch as the listener will draw it, and what was done to it."""
        info = {}
        if kind == "imitate":
            th = headings(g)
            th = th + gaussian_filter1d(rng.normal(0, 0.05, len(th)), 6)       # an imitation, not a copy
            return integrate(th, g[0]), info
        if kind == "exaggerate":
            gain, scale = _u(rng, 1.7, 2.5), _u(rng, 1.2, 1.5)
            info.update(gain=round(gain, 2), scale=round(scale, 2))
            return amplify(g, gain, scale), info
        style = _pick(rng, ["ruled", "meander", "hand"], [0.25, 0.4, 0.35])
        info["style"] = style
        if style == "ruled":
            return ruled(g, _u(rng, 1.2, 2.2)), info
        if style == "meander":
            return meander(g, _u(rng, 0.8, 1.2), _u(rng, 5.0, 9.0), _u(rng, 5.0, 9.0)), info
        return in_hand(g, own, _u(rng, 5.0, 8.0), _u(rng, 1.6, 2.2)), info

    def _coverage_cost(self, q, j0, j1, occ, cell=3.0):
        """How much of the listener's own line (outside the borrowed stretch) lands on existing ink,
        and how far its tails run with the sheet's flow (lower is better)."""
        tails = np.vstack([q[:j0], q[j1:]]) if j0 > 0 or j1 < len(q) else q
        ij = np.clip((tails / cell).astype(int), 0, [occ.shape[1] - 1, occ.shape[0] - 1])
        on = float(occ[ij[:, 1], ij[:, 0]].mean())
        mid = (q[j0] + q[j1]) / 2
        drift = float(np.dot(tails.mean(axis=0) - mid, self.flow)) / math.hypot(self.W, self.H)
        return on - 0.8 * drift

    def listener(self, kind, src: Layer):
        """A new line in its own hand that takes up src's gesture (spliced) and is placed beside it.
        Several candidate lines / splice points / sides are tried; the one whose own stretches cover
        the least existing ink and run furthest with the sheet's flow is kept."""
        from scipy.ndimage import binary_dilation  # noqa: PLC0415
        rng, W, H = self.rng, self.W, self.H
        s_line = src.full
        gi = pick_gesture(rng, s_line, *((35.0, 70.0) if kind == "exaggerate" else (55.0, 120.0)),
                          crowd=self.crowd(skip=(src.lid,)))
        if gi is None:
            return None
        i0, i1 = gi
        g = s_line[i0:i1 + 1]
        hand = _pick(rng, [h for h in self.hands if h != src.params.get("hand")] or self.hands)
        occ = binary_dilation(raster(self.layers, W, H, 3.0), iterations=1)
        n = chord_normal(g)
        gap = {"imitate": _u(rng, 3.0, 5.0), "exaggerate": _u(rng, 1.5, 3.0)}.get(kind, _u(rng, 6.0, 10.0))
        best = None
        for trial in range(3):
            # the listener's own voice is short: a lead-in and a tail around what it heard
            own, part = self.hand_line(hand, round(_u(rng, 1.4, 2.4), 1), (W * _u(rng, 0.35, 0.55), H * _u(rng, 0.35, 0.55)))
            ins, info = self._borrow(kind, g, own, rng)
            tho, thi = headings(own), headings(ins)
            for kf in (_u(rng, 0.15, 0.4), _u(rng, 0.6, 0.85)):
                # splice: own[:k] + ins (turned to continue the heading) + own[k:] (turned to continue again)
                k = int(len(tho) * kf)
                th_ins = thi - thi[0] + tho[k]
                th = np.concatenate([tho[:k], th_ins, tho[k:] - tho[k] + th_ins[-1]])
                line = integrate(th, [0.0, 0.0])
                j0, j1 = k, k + len(th_ins)
                line = rotate(line, line[j0], -math.degrees(tho[k] - thi[0]))
                for sgn in (1, -1):
                    off = n * sgn * gap
                    # exaggerate is centred on the source gesture (the pushed shape around the original);
                    # the others lie beside it, centred on its middle
                    if kind == "exaggerate":
                        q = line - line[j0:j1 + 1].mean(axis=0) + g.mean(axis=0) + off
                    else:
                        q = line - (line[j0] + line[j1]) / 2 + (g[0] + g[-1]) / 2 + off
                    q = fit_tails(q, j0, j1, W, H, self.m)
                    if q is None:
                        continue
                    cost = self._coverage_cost(q, j0, j1, occ) + 0.05 * rng.random()
                    if best is None or cost < best[0]:
                        best = (cost, q, j0, j1, part, info)
        if best is None:
            return None
        _, placed, j0, j1, part, info = best
        ink = self.own_pen(src)
        has_bold = any(L.pen >= self.bold for L in self.layers)
        pen = (0.5 if has_bold else self.bold) if kind == "exaggerate" else round(_pick(rng, [0.3, 0.35]), 2)
        # the stretch where the line listens takes the listening pen (accent / the source's / its own)
        heard = self.heard_pen(src, ink)
        carry = heard != ink
        lines = [placed[:j0 + 1], placed[j0:j1 + 1], placed[j1:]]
        inks = [ink, heard, ink]
        keep = [i for i, l in enumerate(lines) if len(l) >= 2]
        params = {"hand": hand, "splice_at_mm": round(j0 * STEP, 1), "carries_pen": carry,
                  "gesture_src_mm": [round(i0 * STEP, 1), round(i1 * STEP, 1)], **info}
        L = self.add("listener", f"listen.{kind}", ink, pen, [lines[i] for i in keep], part, params,
                     f"{hand} {kind}s {src.lid}")
        L.inks = [inks[i] for i in keep]
        L.full = placed
        at = placed[(j0 + j1) // 2]
        note = {"imitate": "the gesture in unison beside the source, then the line parts",
                "exaggerate": f"pushed ×{info.get('gain', 1):.1f} sideways, ×{info.get('scale', 1):.2f} scale, "
                              "centred on the source gesture",
                "translate": f"the same move in another line style ({info.get('style')})"}[kind]
        if carry:
            note += f", the heard stretch in {heard}"
        self.score.relate(kind, src.lid, L.lid, at=at, s=(j0 * STEP, j1 * STEP),
                          note=note + f"; heard at {i0 * STEP:.0f}–{i1 * STEP:.0f} mm of {src.lid}")
        return L

    def refuser(self, src: Layer, r=None):
        rng, W, H = self.rng, self.W, self.H
        r = float(r if r is not None else _u(rng, 2.5, 5.0))
        hand = _pick(rng, [h for h in self.hands if h != src.params.get("hand")] or self.hands)
        own, part = self.hand_line(hand, round(_u(rng, 1.4, 2.4), 1), (W * _u(rng, 0.3, 0.5), H * _u(rng, 0.3, 0.5)))
        s_line = src.full
        for _ in range(6):
            c = s_line[int(rng.integers(len(s_line)))] + rng.normal(0, 6.0, 2)
            q = rotate(own, own.mean(axis=0), _u(rng, 0, 360))
            q = self._settle(q - q.mean(axis=0) + c)
            out, where = detour(q, src.lines, r)
            if where and out is not None and _inside(out, W, H, 2.0):
                ink = self.own_pen(src)
                heard = self.heard_pen(src, ink)
                # the detours (where it listened, by refusing) in the listening pen
                sa = arclen(out)
                cuts = sorted({0} | {int(np.searchsorted(sa, v)) for _, s0, s1 in where for v in (s0, s1)}
                              | {len(out) - 1})
                lines, inks = [], []
                for i0, i1 in zip(cuts[:-1], cuts[1:]):
                    if i1 - i0 < 1:
                        continue
                    mid = sa[(i0 + i1) // 2]
                    lines.append(out[i0:i1 + 1])
                    inks.append(heard if any(s0 <= mid <= s1 for _, s0, s1 in where) else ink)
                L = self.add("listener", "listen.refuse", ink, round(_pick(rng, [0.3, 0.35]), 2), lines, part,
                             {"hand": hand, "halo_mm": round(r, 1), "detours": len(where)}, f"{hand} refuses {src.lid}")
                L.inks, L.full = inks, out
                for a, s0, s1 in where:
                    self.score.relate("refuse", src.lid, L.lid, at=a, s=(s0, s1),
                                      note=f"walks {src.lid}'s halo at {r:.1f} mm instead of meeting it")
                return L
        return None

    def echo(self, src: Layer):
        rng = self.rng
        s_line = src.full
        gi = pick_gesture(rng, s_line, 25.0, 55.0)
        if gi is None:
            return None
        g = s_line[gi[0]:gi[1] + 1]
        gc = g.mean(axis=0)
        spot, room = self.echo_spot(gc)
        if spot is None:
            return None
        reps = int(_pick(rng, [1, 2, 3], [0.25, 0.45, 0.3]))
        size = max(np.ptp(g, axis=0).max(), 1e-9)
        k0 = float(np.clip(_u(rng, 0.75, 1.0), min(28.0 / size, 1.0), 1.0))
        ang = _u(rng, -25, 25)
        lines, step_dir = [], np.array([math.cos(math.radians(_u(rng, 0, 360))), 0.0])
        step_dir[1] = math.sqrt(max(1 - step_dir[0] ** 2, 0)) * rng.choice([-1, 1])
        pos, k = spot.copy(), k0
        for _ in range(reps):
            q = rotate((g - gc) * k, np.zeros(2), ang) + pos
            if not _inside(q, self.W, self.H, self.m):
                break
            lines.append(q)
            pos = pos + step_dir * (np.ptp(q, axis=0).max() * 0.75 + 3.0)
            k *= _u(rng, 0.7, 0.82)
            if k * size < 20.0:
                break
        if not lines:
            return None
        L = self.add("echo", "listen.echo", light_of(self.accent if self.mode == "accent" else src.ink),
                     round(_pick(rng, [0.3, 0.35]), 2), lines, None,
                     {"scale": round(k0, 2), "repeats": len(lines), "turn_deg": round(ang, 1)}, f"echo of {src.lid}")
        self.score.relate("echo", src.lid, L.lid, at=lines[0].mean(axis=0), s=(0.0, arclen(lines[0])[-1]),
                          note=f"{len(lines)} repeat(s) from {gi[0] * STEP:.0f}–{gi[1] * STEP:.0f} mm of {src.lid}, "
                               f"×{k0:.2f} and decaying; heard at {gc[0]:.0f},{gc[1]:.0f}")
        return L

    def calm(self, src: Layer):
        rng = self.rng
        s_line = src.full
        gi = pick_gesture(rng, s_line, 30.0, 70.0, open_ends=True)
        if gi is None:
            return None
        g = s_line[gi[0]:gi[1] + 1]
        q = push(g, _u(rng, 0.12, 0.3), 1.0, trend_mm=0.0)
        q = similar_to(q, g[0], g[-1])
        q = resample(q, STEP)
        if not _inside(q, self.W, self.H, 3.0):
            return None
        ink = self.heard_pen(src, self.own_pen(src))
        L = self.add("calm", "listen.calm", ink, 0.3, [q], None,
                     {}, f"calm under {src.lid}")
        self.score.relate("calm", src.lid, L.lid, at=q[len(q) // 2], s=(0.0, arclen(q)[-1]),
                          note=f"the gesture at {gi[0] * STEP:.0f}–{gi[1] * STEP:.0f} mm of {src.lid}, flattened, "
                               "its ends on the gesture's ends")
        return L

    def nest(self, src: Layer):
        """A small copy of src's own gesture in a crook of src's line."""
        rng, cell = self.rng, 1.0
        occ = raster([src], self.W, self.H, cell)
        d = distance_transform_edt(~occ) * cell
        ny, nx = d.shape
        best = None
        cand = np.argwhere((d > 7.0) & (d < 18.0))
        if not len(cand):
            return None
        order = rng.permutation(len(cand))[:600]
        angs = np.linspace(0, 2 * math.pi, 12, endpoint=False)
        for j in order:
            y, x = cand[j]
            r = d[y, x]
            hits = 0
            for a in angs:
                for t in np.arange(r, 3.2 * r, cell):
                    xx, yy = int(x + math.cos(a) * t / cell), int(y + math.sin(a) * t / cell)
                    if not (0 <= xx < nx and 0 <= yy < ny):
                        break
                    if occ[yy, xx]:
                        hits += 1
                        break
            if hits >= 9 and (best is None or r > best[0]):
                best = (r, np.array([(x + 0.5) * cell, (y + 0.5) * cell]))
        if best is None:
            return None
        r, c = best
        s_line = src.full
        gi = pick_gesture(rng, s_line, 20.0, 45.0)
        if gi is None:
            return None
        g = s_line[gi[0]:gi[1] + 1]
        k = 0.62 * r / max(np.linalg.norm(g - g.mean(axis=0), axis=1).max(), 1e-9)
        q = rotate((g - g.mean(axis=0)) * k, np.zeros(2), _u(rng, 0, 360)) + c
        ink = self.heard_pen(src, self.own_pen(src))
        L = self.add("nest", "listen.nest", ink, round(_pick(rng, [0.3, 0.4, 0.5]), 2), [q], None,
                     {"radius_mm": round(float(r), 1), "scale": round(float(k), 3)}, f"nests in {src.lid}")
        self.score.relate("nest", src.lid, L.lid, at=c, s=(0.0, arclen(q)[-1]),
                          note=f"{src.lid}'s own gesture ×{k:.2f}, in a crook of {src.lid} {r:.0f} mm across")
        return L

    def bind(self, a: Layer, b: Layer):
        rng = self.rng
        la, lb = a.full, b.full
        best = None
        for ea, ta in ((la[-1], la[-1] - la[-8]), (la[0], la[0] - la[7])):
            for sb, tb in ((lb[0], lb[7] - lb[0]), (lb[-1], lb[-8] - lb[-1])):
                dist = float(np.linalg.norm(sb - ea))
                if 25.0 <= dist <= 150.0 and (best is None or dist < best[0]):
                    best = (dist, ea, ta, sb, tb)
        if best is None:
            return None
        dist, p0, t0, p1, t1 = best
        t0, t1 = t0 / max(np.linalg.norm(t0), 1e-9), t1 / max(np.linalg.norm(t1), 1e-9)
        h = dist * _u(rng, 0.35, 0.6)
        u = np.linspace(0, 1, max(int(dist * 3 / STEP), 20))[:, None]
        q = ((2 * u ** 3 - 3 * u ** 2 + 1) * p0 + (u ** 3 - 2 * u ** 2 + u) * h * t0 * 3
             + (-2 * u ** 3 + 3 * u ** 2) * p1 + (u ** 3 - u ** 2) * h * t1 * 3)
        q = resample(q, STEP)
        if not _inside(q, self.W, self.H, 2.0):
            return None
        mid = len(q) // 2
        L = self.add("bind", "listen.bind", a.ink, 0.35, [q[:mid + 1], q[mid:]], None,
                     {"from": a.lid, "to": b.lid}, f"binds {a.lid} into {b.lid}")
        L.inks = [a.ink, b.ink] if self.mode == "pair" else [self.accent, self.accent]
        L.full = q
        self.score.relate("bind", a.lid, b.lid, at=q[mid], s=None,
                          note=f"a ligature ({L.lid}) from {a.lid}'s end into {b.lid}'s start; the pen hands over halfway")
        return L

    def place_mask(self):
        """The torn void at an ambiguous point: where two layers overlap most."""
        rng, W, H = self.rng, self.W, self.H
        cell = 4.0
        rs = [raster([L], W, H, cell) for L in self.layers]
        from scipy.ndimage import binary_dilation  # noqa: PLC0415
        rs = [binary_dilation(r, iterations=2) for r in rs]
        cnt = np.sum(rs, axis=0).astype(float)
        ny, nx = cnt.shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        cx, cy = (xx + 0.5) * cell, (yy + 0.5) * cell
        central = np.exp(-(((cx - W / 2) / (0.35 * W)) ** 2 + ((cy - H / 2) / (0.35 * H)) ** 2))
        sc = (cnt >= 2) * cnt * central + rng.random(cnt.shape) * 0.2
        j = int(np.argmax(sc))
        c = np.array([cx.ravel()[j], cy.ravel()[j]])
        w = min(W, H) * _u(rng, 0.13, 0.22)
        h = min(W, H) * _u(rng, 0.28, 0.45)
        if rng.random() < 0.4:
            w, h = h, w
        poly = cover_polygon(rng, c, w, h, _pick(rng, ["torn", "cut"], [0.6, 0.4]), 8.0)
        # the edge drawn only in part: one or two runs of its perimeter
        ring = resample(poly, STEP)
        s = arclen(ring)
        runs = []
        for _ in range(int(_pick(rng, [0, 1, 2], [0.15, 0.5, 0.35]))):
            a = _u(rng, 0, s[-1])
            b = a + _u(rng, 0.15, 0.35) * s[-1]
            idx = np.flatnonzero((s >= a) & (s <= b)) if b <= s[-1] else np.r_[np.flatnonzero(s >= a), np.flatnonzero(s <= b - s[-1])]
            if len(idx) > 4:
                runs.append(ring[idx])
        ink = light_of(self.accent)
        L = self.add("mask", "listen.mask", ink, 0.3, runs, None,
                     {"polygon": [[round(float(x), 1), round(float(y), 1)] for x, y in poly], "edge_runs": len(runs)},
                     "the void")
        self.mask = (L, poly, len(self.layers) - 1)
        return L

    # -- the whole sheet ----------------------------------------------------
    def compose(self):
        """speakers → listeners (spliced; the void may come between them) → later small layers →
        the void cuts what came before it → every crossing made aware. Each kind fires at most
        CAP times per sheet, so no relation becomes the sheet's style."""
        rng = self.rng
        n_speak = int(_pick(rng, [1, 2], [0.4, 0.6]))
        if rng.random() < self.river_p:
            self.river()
        for i in range(n_speak):
            self.speaker(i)
        n_listen = int(_pick(rng, [3, 4], [0.6, 0.4]))
        mask_after = None
        if rng.random() < self.mask_p:
            # late: most of the sheet is already drawn (and cut by it); the last listener and the
            # small later layers cross it, so the eye cannot settle which layer is in front
            mask_after = max(n_listen - int(rng.integers(1, 3)), 1)
        n_later = int(_pick(rng, [1, 2], [0.5, 0.5]))
        used = {k: 0 for k in VOCAB}
        heard, tries = 0, 0
        # listeners: the drawn count, one more if the sheet is still under its density floor
        while tries < 16:
            tries += 1
            want = n_listen + (1 if self.density_now() < self.band[0] else 0)
            if heard >= min(want, 5) or self.density_now() > self.band[1]:
                break
            if mask_after is not None and heard == mask_after and self.mask is None:
                self.place_mask()
            spliced = [k for k in self.kinds if k in SPLICED and used[k] < CAP[k]]
            if not spliced:
                break
            kind = _pick(rng, spliced, [WEIGHTS[k] for k in spliced])
            # listen to a recent layer more often than an old one (chains: C hears B hearing A)
            cands = [L for L in self.layers if L.role in ("speaker", "listener", "found")]
            w = np.array([1.0 + 1.0 * i for i in range(len(cands))])
            src = cands[int(rng.choice(len(cands), p=w / w.sum()))]
            L = self.refuser(src) if kind == "refuse" else self.listener(kind, src)
            if L is not None:
                heard += 1
                used[kind] += 1
        if mask_after is not None and self.mask is None:
            self.place_mask()
        done, tries = 0, 0
        while done < n_later and tries < 10:
            tries += 1
            later = [k for k in self.kinds if k in LATER and used[k] < CAP[k]]
            if not later or self.density_now() > self.band[1]:
                break
            kind = _pick(rng, later, [WEIGHTS[k] for k in later])
            cands = [L for L in self.layers if L.role in ("speaker", "listener", "found")]
            src = cands[int(rng.integers(len(cands)))]
            if kind == "bind":
                if len(cands) < 2:
                    continue
                i, j = rng.choice(len(cands), 2, replace=False)
                L = self.bind(cands[int(i)], cands[int(j)])
            else:
                L = getattr(self, kind)(src)
            if L is not None:
                done += 1
                used[kind] += 1
        self.apply_mask()
        self.overlaps()

    def apply_mask(self):
        """Layers drawn before the void are cut by it, later ones cross it; an occasional exception
        either way. If nothing would cross (or nothing be cut) the void is no longer ambiguous, so the
        last-drawn layer over it crosses (or the first is cut) instead, and the note says so."""
        if self.mask is None:
            return
        M, poly, at_index = self.mask
        from shapely.geometry import Polygon  # noqa: PLC0415
        P = Polygon(poly)
        plan = []
        for i, L in enumerate(self.layers):
            if L is M:
                continue
            hit = [l for l in L.lines if _crosses(l, P)]
            if not hit:
                continue
            before = i < at_index
            respect = before
            why = ""
            if self.rng.random() < 0.15:
                respect = not respect
                why = "an exception, so the order stays ambiguous"
            where = np.vstack(hit)
            where = where[_contains(P, where)]
            at = where.mean(axis=0) if len(where) else np.asarray(P.centroid.coords[0])
            plan.append([L, before, respect, at, why])
        if len(plan) >= 2 and all(p[2] for p in plan):
            plan[-1][2], plan[-1][4] = False, "the last layer over the void crosses it, or the void would be a plain hole"
        if len(plan) >= 2 and not any(p[2] for p in plan):
            plan[0][2], plan[0][4] = True, "the first layer under the void is cut, or the void would not exist"
        for L, before, respect, at, why in plan:
            order = "drawn before the void" if before else "drawn after the void"
            if respect:
                cut = [(_cut_by([l], P, 3.0), ink) for l, ink in zip(L.lines, L.inks)]
                L.lines = [q for qs, _ in cut for q in qs]
                L.inks = [ink for qs, ink in cut for _ in qs]
                self.score.relate("mask", M.lid, L.lid, at=at, note=f"{order}: cut by it" + (f" ({why})" if why else ""))
            else:
                self.score.relate("ignore", M.lid, L.lid, at=at, note=f"{order}: crosses it" + (f" ({why})" if why else ""))

    def overlaps(self):
        """Every crossing between two different layers is aware: weave (alternate gaps) or yield (the
        later line gives way). Recorded once per pair, at the crossings' centre."""
        from shapely.geometry import LineString  # noqa: PLC0415
        rng = self.rng
        gaps: dict = {}
        ls = {(i, j): LineString(l) for i, L in enumerate(self.layers) for j, l in enumerate(L.lines) if len(l) > 1}
        for a in range(len(self.layers)):
            for b in range(a + 1, len(self.layers)):
                A, B = self.layers[a], self.layers[b]
                if A.role == "mask" or B.role == "mask":
                    continue
                pts = []
                for ja in range(len(A.lines)):
                    for jb in range(len(B.lines)):
                        la, lb = ls.get((a, ja)), ls.get((b, jb))
                        if la is None or lb is None:
                            continue
                        x = la.intersection(lb)
                        for p in _points(x):
                            pts.append((la.project(p), (a, ja), lb.project(p), (b, jb), (p.x, p.y)))
                if not pts:
                    continue
                mode = _pick(rng, ["weave", "yield"], [0.6, 0.4])
                if B.role in ("echo", "calm", "nest") and mode == "weave":
                    mode = _pick(rng, ["weave", "yield"], [0.5, 0.5])
                pts.sort(key=lambda t: (t[1], t[0]))
                for n, (sa, ka, sb, kb, _) in enumerate(pts):
                    if mode == "weave":
                        under, s, over = (kb, sb, A) if n % 2 == 0 else (ka, sa, B)
                        half = over.pen / 2 + 0.5
                    else:
                        under, s, over = kb, sb, A
                        half = over.pen / 2 + _u(rng, 1.0, 1.6)
                    gaps.setdefault(under, []).append((s - half, s + half))
                c = np.mean([p[4] for p in pts], axis=0)
                self.score.relate(mode, A.lid, B.lid, at=c,
                                  note=f"{len(pts)} crossing(s); " + ("they alternate which passes under"
                                                                     if mode == "weave" else f"{B.lid} gives way each time"))
        for (i, j), cuts in gaps.items():
            L = self.layers[i]
            L.lines[j] = _gapped(L.lines[j], cuts)
        for L in self.layers:
            flat, inks = [], []
            for l, ink in zip(L.lines, L.inks):
                for q in (l if isinstance(l, list) else [l]):
                    if len(q) >= 2 and arclen(q)[-1] >= 1.5:
                        flat.append(q)
                        inks.append(ink)
            L.lines, L.inks = flat, inks


# ---------------------------------------------------------------------------
# helpers: halo, cuts, gaps
# ---------------------------------------------------------------------------

def _points(x):
    if x.is_empty:
        return []
    t = x.geom_type
    if t == "Point":
        return [x]
    if t == "MultiPoint":
        return list(x.geoms)
    if t in ("GeometryCollection", "MultiLineString", "LineString"):
        out = []
        for g in getattr(x, "geoms", [x]):
            if g.geom_type == "Point":
                out.append(g)
            elif g.geom_type == "LineString":
                out.append(g.interpolate(0.5, normalized=True))
        return out
    return []


def _contains(P, xy):
    import shapely  # noqa: PLC0415
    return shapely.contains_xy(P, xy[:, 0], xy[:, 1])


def _crosses(l, P) -> bool:
    return bool(_contains(P, l).any())


def _cut_by(lines, P, min_stub):
    out = []
    for l in lines:
        inside = _contains(P, l)
        for a, b in _runs(~inside):
            q = l[a:b + 1]
            if len(q) >= 2 and (arclen(q)[-1] >= min_stub or (a == 0 and b == len(l) - 1)):
                out.append(q)
    return out


def _runs(mask):
    m = np.r_[False, np.asarray(mask, bool), False]
    d = np.diff(m.astype(int))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1))


def _gapped(l, cuts):
    s = arclen(l)
    keep = np.ones(len(l), bool)
    for a, b in cuts:
        keep &= ~((s > a) & (s < b))
    pieces = []
    for a, b in _runs(keep):
        if b > a:
            pieces.append(l[a:b + 1])
    return pieces


def detour(line, others, r):
    """The line, but wherever it comes within r of `others` it walks their halo (the r-offset boundary)
    instead. Returns (new line, [(at, s0, s1)]) or (None, []) when a run cannot be resolved."""
    import shapely  # noqa: PLC0415
    from shapely.geometry import LineString  # noqa: PLC0415
    from shapely.ops import unary_union  # noqa: PLC0415
    buf = unary_union([LineString(o).buffer(r, quad_segs=12) for o in others if len(o) > 1])
    inside = shapely.contains_xy(buf, line[:, 0], line[:, 1])
    if not inside.any():
        return line, []
    rings = []
    for poly in getattr(buf, "geoms", [buf]):
        rings.append(resample(np.asarray(poly.exterior.coords), STEP))
        for hole in poly.interiors:
            rings.append(resample(np.asarray(hole.coords), STEP))
    pieces, where = [], []
    runs = _runs(inside)
    a0 = 0
    for a, b in runs:
        if a == 0 or b == len(line) - 1:
            # a run at an end: the line stops short of the other instead
            if a == 0:
                a0 = b + 1
            else:
                pieces.append(line[a0:a])
                a0 = None
            continue
        p, q = line[a - 1], line[b + 1]
        best = None
        for R in rings:
            i0 = int(np.argmin(np.linalg.norm(R - p, axis=1)))
            i1 = int(np.argmin(np.linalg.norm(R - q, axis=1)))
            if np.linalg.norm(R[i0] - p) > 1.5 or np.linalg.norm(R[i1] - q) > 1.5:
                continue
            n = len(R) - 1
            fwd = (i1 - i0) % n
            bwd = (i0 - i1) % n
            path = R[[(i0 + t) % n for t in range(fwd + 1)]] if fwd <= bwd else R[[(i0 - t) % n for t in range(bwd + 1)]]
            if best is None or len(path) < len(best):
                best = path
        if best is None:
            return None, []
        straight = (b - a + 2) * STEP
        if len(best) * STEP > max(5.0 * straight, 12 * r):
            return None, []
        pieces.append(line[a0:a])
        pieces.append(best)
        s0 = sum(arclen(x)[-1] for x in pieces[:-1] if len(x) > 1)
        where.append((best[len(best) // 2], s0, s0 + arclen(best)[-1]))
        a0 = b + 1
    if a0 is not None:
        pieces.append(line[a0:])
    pieces = [x for x in pieces if len(x)]
    if not pieces:
        return None, []
    out = resample(np.vstack(pieces), STEP)
    if len(out) < 20:
        return None, []
    return out, where


def s_offset(L, piece) -> float | None:
    """Where a drawn piece starts along its layer's whole (uncut) line, mm: the score's `s` ranges
    are on that line, so a reader (the annotator, a future bench) can find the stretch again."""
    if L.full is None or not len(piece):
        return None
    d = np.linalg.norm(L.full - piece[0], axis=1)
    i = int(np.argmin(d))
    if d[i] > 0.05:
        return None
    return round(float(arclen(L.full)[i]), 2)


# ---------------------------------------------------------------------------
# the arranger
# ---------------------------------------------------------------------------

@arranger("listen", params=[
    P("density", "float", 0.5, "where in the middle band the sheet sits (0.2 … 0.8; the extremes are off)",
      min=0.2, max=0.8),
    P("mask_p", "float", 0.25, "chance of the void (the 4507 move); kept rare so it never becomes the style",
      min=0.0, max=1.0),
    P("river_p", "float", 0.3, "chance of found matter: river_zoom, free course, constant width", min=0.0, max=1.0),
    P("relations", "str", ",".join(VOCAB), "which relation kinds may fire (comma list)"),
    P("pens", "int", 0, "how many pens 2–4 (0 = the composer decides)", min=0, max=4),
], doc="A: layers that listen — imitate, exaggerate, translate, refuse (spliced into the listener's own line), "
        "echo, calm, nest, bind (small later layers), a rare partial void; every crossing woven or yielded; "
        "the score records every layer and relation")
def listen(ctx, parts, *, density, mask_p, river_p, relations, pens):
    W, H = ctx.frame
    hands = [p.spec["voice"].get("hand") for p in parts if p.spec["voice"].get("hand")]
    kinds = {k.strip() for k in relations.split(",") if k.strip()}
    C = Composer(ctx, hands, density=density, mask_p=mask_p, river_p=river_p, kinds=kinds, pens=pens)
    C.compose()
    out = []
    lo, hi = np.array([1.0, 1.0]), np.array([W - 1.0, H - 1.0])
    for L in C.layers:
        for j, l in enumerate(L.lines):
            ink = L.inks[j]
            out.append(Mark(np.clip(l, lo, hi), {}, {"ink": ink, "pen": L.pen, "layer": L.lid, "of_role": L.role,
                                                     "part": 0, "s0": s_offset(L, l)}))
    C.score.decide(frame=[W, H], palette=C.palette, colour_mode=C.mode, bold_mm=C.bold, density={"dial": density, "band_mm_per_cm2": [round(v, 1) for v in C.band],
                                                           "achieved": round(C.density_now(), 1)},
                   mask=None if C.mask is None else C.mask[0].lid, flow_deg=C.flow_deg, order=[L.lid for L in C.layers])
    ctx.note("score", C.score.to_json())
    return out


def recipe(seed: int, *, frame=None, **arr) -> dict:
    """A listen recipe: the frame is chosen per seed from ccolour's five, unless given."""
    rng = np.random.default_rng([0x115E, int(seed)])
    f = FRAMES[int(rng.choice(len(FRAMES), p=[0.32, 0.17, 0.17, 0.17, 0.17]))]
    W, H, why = (frame[0], frame[1], "given") if frame else f
    a = {"id": "listen"}
    a.update(arr)
    return {"label": "listen", "notes": f"frame {W:g}×{H:g}: {why}", "frame": [W, H], "seed": int(seed),
            "margin": 5.0, "arranger": a,
            "parts": [{"voice": {"id": "hand", "hand": h, "length": 3.0, "joins": "smooth"}} for h in LISTEN_HANDS],
            "renderer": {"id": "oehlen_found_ink", "pen": 0.4}}
