"""The pen as a particle in its own wet ink (round 12, thread 3 `stain`).

renderer `stain_particle`: one contiguous line per mark. The pen follows a
"carrot" that travels along the voice's centreline by the line's own clock
(`dance_t`, else the 2/3 power law). The pen itself moves at a constant
speed, so wherever the line slows the pen has SLACK — and spends it
wandering inside the wet region its own dwell has made: a first-passage
field through the woven medium of `renderers_stain`, growing with time
(Washburn, reach ∝ √time). The pen never draws the stain's edge: the edge
appears where the wandering line turns back from it.

The tide line is the coffee-ring effect: in the drying phase (after the
deepest dwell) capillary flow carries the particle outward, so its path
piles up against the front — only on an arc of the circumference
(the corpus: a median 63 % of the ring), so the ring fails to close.

Then the carrot moves on, the pen follows it out, and the line is a line
again.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi

from .core import Ink, P, renderer
from .renderers_stain import Medium, _digest, _rot, _sheet_weave, dwell, line_time


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


class _Grid:
    """Bilinear sampling of a field and its gradient (weave-frame mm)."""

    def __init__(self, U, lo, h):
        self.U = np.where(np.isfinite(U), U, 1e6)
        self.gy, self.gx = np.gradient(self.U, h)
        self.lo, self.h = np.asarray(lo, float), h
        self.ny, self.nx = U.shape

    def _ij(self, q):
        x = (q[0] - self.lo[0]) / self.h
        y = (q[1] - self.lo[1]) / self.h
        return y, x

    def at(self, A, q):
        y, x = self._ij(q)
        if not (0 <= x < self.nx - 1 and 0 <= y < self.ny - 1):
            return 1e6
        i, j = int(y), int(x)
        fy, fx = y - i, x - j
        return float((1 - fy) * ((1 - fx) * A[i, j] + fx * A[i, j + 1]) + fy * ((1 - fx) * A[i + 1, j]
                                                                                 + fx * A[i + 1, j + 1]))

    def u(self, q):
        return self.at(self.U, q)

    def grad(self, q):
        return np.array([self.at(self.gx, q), self.at(self.gy, q)])


def _pen_speed(dt, ds, slack):
    """Pen speed V so that Σ max(V·dt, ds) = (1 + slack) Σ ds (bisection)."""
    L = float(ds.sum())
    target = (1.0 + slack) * L
    lo, hi = 0.0, 1.0
    while np.maximum(hi * dt, ds).sum() < target and hi < 1e12:
        hi *= 2.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if np.maximum(mid * dt, ds).sum() < target:
            lo = mid
        else:
            hi = mid
    return hi


def _stretches(b, thr):
    """(i0, i1) index runs where b ≥ thr."""
    k = np.flatnonzero(b >= thr)
    if not len(k):
        return []
    cuts = np.flatnonzero(np.diff(k) > 1)
    starts = np.r_[k[0], k[cuts + 1]]
    ends = np.r_[k[cuts], k[-1]]
    return list(zip(starts.tolist(), ends.tolist()))


def _reach(p):
    return p["R"] * 1.4 + 1.0


@renderer("stain_particle", params=[
    P("pen", "float", 0.3, "pen width mm", min=0.05, max=3.0),
    P("stains", "ref", "stain_fabric", "the measured stain statistics", kind="stain"),
    P("R", "float", 6.0, "wet reach of the longest dwell, mm (others ∝ √dwell, Washburn)", min=0.5, max=60.0),
    P("wet", "float", 0.22, "dwell (share of the longest, after √) below which the line stays dry",
      min=0.01, max=0.95),
    P("window", "float", 2.5, "dwell window, ± mm of line", min=0.2, max=40.0),
    P("slack", "float", 2.0, "extra pen path spent wandering, × the line's length", min=0.0, max=40.0),
    P("persist", "float", 1.2, "the pen's persistence length, mm (how far it goes before its turning decorrelates)",
      min=0.05, max=20.0),
    P("curl", "float", 1.4, "turning noise (rad / √mm)", min=0.0, max=10.0),
    P("tide", "choice", "auto", "mesa | rim (coffee-ring drift while drying) | auto (rim with rim_p)",
      choices=("auto", "mesa", "rim")),
    P("rim_p", "float", 0.5, "auto: probability of a tide line (corpus 0.10; raised on purpose)", min=0.0, max=1.0),
    P("drift", "float", 3.0, "coffee-ring outward drift strength (rad / mm)", min=0.0, max=30.0),
    P("arc", "float", 0.63, "share of the ring the drift acts on (corpus median 0.63)", min=0.05, max=1.0),
    P("weave", "float", 0.25, "thread conductance (0 = paper)", min=0.0, max=20.0),
    P("period", "float", 0.9, "thread spacing, mm", min=0.1, max=10.0),
    P("fiber", "float", 0.55, "fibre noise (front roughness; 0.55 ≈ the corpus median 0.07 R)", min=0.0, max=2.0),
    P("elong", "float", 1.1, "warp/weft absorbency ratio", min=1.0, max=3.0),
    P("angle", "float", None, "weave angle, degrees (null: from the sheet seed)", min=0.0, max=180.0, optional=True),
    P("snapshots", "int", 6, "how many times the growing wet front is recomputed per stain", min=1, max=24),
    P("step", "float", 0.15, "pen step, mm", min=0.03, max=1.0),
    P("bounce", "choice", "specular", "how the pen turns back at the wet front: specular (a billiard: chords "
      "keep their angle, so the path rings the edge) | diffuse (a random new heading inward)",
      choices=("specular", "diffuse")),
    P("hold", "float", 0.7, "how far from the carrot the pen roams freely, × the current wet reach", min=0.1,
      max=3.0),
], reach=_reach,
    doc="the pen as a particle in its own wet ink: where the line slows the pen wanders inside the stain its "
        "dwell makes; the edge appears where the line turns back; coffee-ring drift makes a broken tide line")
def stain_particle(ctx, marks, *, pen, stains, R, wet, window, slack, persist, curl, tide, rim_p, drift, arc,
                   weave, period, fiber, elong, angle, snapshots, step, bounce, hold):
    dig = _digest(ctx, stains)  # noqa: F841  (recorded; profile used through rim/mesa choice)
    ang = _sheet_weave(ctx.sheet_seed, angle)
    Rw, Rs = _rot(-ang), _rot(ang)
    out: list[Ink] = []
    # one clock normalisation for the whole part: the longest dwell over every mark
    prepared = []
    for m in marks:
        pts = np.asarray(m.points, float)
        if len(pts) < 3:
            prepared.append(None)
            continue
        s0 = np.r_[0.0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
        if s0[-1] <= 1e-6:
            prepared.append(None)
            continue
        t0 = line_time(pts, m.channel("dance_t"))
        s = np.arange(0.0, s0[-1], 0.2)
        if len(s) < 3:
            prepared.append(None)
            continue
        P_ = np.column_stack([np.interp(s, s0, pts[:, 0]), np.interp(s, s0, pts[:, 1])])
        t = np.interp(s, s0, t0)
        prepared.append((m, s, P_, t, dwell(s, t, window)))
    live = [p for p in prepared if p is not None]
    if not live:
        return out
    # the line's own pace is the baseline: only dwell IN EXCESS of its median wets the cloth
    Dbase = float(np.median(np.concatenate([p[4] for p in live])))
    Dmax = max(max(float(p[4].max()) for p in live) - Dbase, 0.5 * Dbase)
    all_dt = np.concatenate([np.diff(p[3]) for p in live])
    all_ds = np.concatenate([np.diff(p[1]) for p in live])
    V = _pen_speed(all_dt, all_ds, slack)
    for mi, prep in enumerate(prepared):
        if prep is None:
            continue
        m, s, P_, t, D = prep
        rng = ctx.rng("particle", mi)
        b = R * np.sqrt(np.clip((D - Dbase) / max(Dmax, 1e-12), 0, None))   # Washburn: reach ∝ √(excess time)
        runs = _stretches(b, max(wet * R, 2.0 * pen))
        pieces: list[np.ndarray] = []
        cur = 0
        for i0, i1 in runs:
            # carry the dry approach up to the wet stretch
            i0 = max(i0, cur)
            if i1 - i0 < 2:
                continue
            pieces.append(P_[cur:i0 + 1])
            td = tide if tide != "auto" else ("rim" if rng.random() < rim_p else "mesa")
            path = _wander(P_[i0:i1 + 1], t[i0:i1 + 1], b[i0:i1 + 1], V=V, pen=pen, persist=persist, curl=curl,
                           tide=td, drift=drift, arc=arc, weave=weave, period=period, fiber=fiber, elong=elong,
                           Rw=Rw, Rs=Rs, sheet_seed=ctx.sheet_seed, rng=rng, snapshots=snapshots, step=step,
                           bounce=bounce, hold=hold)
            pieces.append(path)
            cur = i1
        pieces.append(P_[cur:])
        poly = np.vstack([q for q in pieces if len(q)])
        out.append(Ink(poly, pen=pen, meta={"voice": m.meta.get("voice_id"), "role": "stain_particle",
                                            "stains": len(runs)}))
    return out


def _wander(L, t, b, *, V, pen, persist, curl, tide, drift, arc, weave, period, fiber, elong, Rw, Rs, sheet_seed,
            rng, snapshots, step, bounce="specular", hold=0.7):
    """The pen through one wet stretch of the line L (times t, reaches b)."""
    c0 = L[int(np.argmax(b))]
    to_w = lambda p: (np.asarray(p) - c0) @ Rw.T  # noqa: E731
    to_s = lambda q: np.asarray(q) @ Rs.T + c0    # noqa: E731
    Lw = to_w(L)
    bmax = float(b.max())
    h = float(np.clip(bmax / 40.0, 0.07, 0.3))
    lo = Lw.min(0) - 1.35 * bmax - 2 * h
    hi = Lw.max(0) + 1.35 * bmax + 2 * h
    med = Medium(lo, hi, h=h, period=period, weave=weave, fiber=fiber, elong=elong, sheet_seed=sheet_seed, rng=rng)
    T0, T1 = float(t[0]), float(t[-1])
    span = max(T1 - T0, 1e-9)
    Tw = 0.6 * span                                            # wicking time: reach grows as √(age / Tw)
    tk = T0 + span * (np.arange(snapshots) + 1) / snapshots
    grids = []
    for tau in tk:
        on = t <= tau + 1e-12
        age = np.clip((tau - t[on]) / Tw, 0, 1)
        bud = np.maximum(b[on] * np.sqrt(age), 1.2 * pen)
        grids.append(_Grid(med.field(Lw[on], bud), med.lo, h))
    t_peak = float(t[int(np.argmax(b))])
    # the pen
    pos = Lw[0].copy()
    head = Lw[min(3, len(Lw) - 1)] - Lw[0]
    th = float(np.arctan2(head[1], head[0]))
    kap = 0.0
    tau = T0
    dtau = step / V
    path = [pos.copy()]
    sig = curl * np.sqrt(step)
    decay = np.exp(-step / persist)
    rim_dir = float(rng.uniform(-np.pi, np.pi))
    max_steps = int(40 * (np.sum(np.hypot(*np.diff(Lw, axis=0).T)) + V * span) / step) + 2000
    for _ in range(max_steps):
        tau += dtau
        k = min(int((tau - T0) / span * snapshots), snapshots - 1)
        G = grids[k]
        carrot = np.array([np.interp(min(tau, T1), t, Lw[:, 0]), np.interp(min(tau, T1), t, Lw[:, 1])])
        if tau >= T1 and np.hypot(*(pos - Lw[-1])) < 1.5 * step:
            break
        # OU curvature: persistent, smooth turning
        kap = kap * decay + sig * rng.standard_normal() / max(persist, 1e-6) ** 0.5
        # pursuit of the carrot, loose while near it
        dv = carrot - pos
        dist = float(np.hypot(*dv))
        bc = float(np.interp(min(tau, T1), t, b)) * np.sqrt(np.clip((min(tau, T1) - T0) / Tw, 0.05, 1))
        free = max(hold * bc, 2 * pen)
        gain = 4.0 * _smoothstep((dist - free) / free) if tau < T1 else 6.0
        dphi = np.angle(np.exp(1j * (np.arctan2(dv[1], dv[0]) - th)))
        turn = kap + gain * dphi
        # coffee ring: drying → outward along the front, on the arc side only
        if tide == "rim" and tau > t_peak:
            g = G.grad(pos)
            gn = float(np.hypot(*g))
            if gn > 1e-9:
                ph = float(np.arctan2(pos[1], pos[0]))
                w = _smoothstep((np.cos(np.angle(np.exp(1j * (ph - rim_dir)))) - np.cos(np.pi * arc))
                                / max(1 - np.cos(np.pi * arc), 1e-6) * 3)
                dry = _smoothstep((tau - t_peak) / max(T1 - t_peak, 1e-9) * 1.5)
                tn = np.arctan2(g[1], g[0])
                turn += drift * w * dry * np.sin(tn - th)
        th += turn * step
        nxt = pos + step * np.array([np.cos(th), np.sin(th)])
        if G.u(nxt) > 0 and tau < T1:
            g = G.grad(pos)
            gn = float(np.hypot(*g))
            n = g / gn if gn > 1e-9 else -pos / max(np.hypot(*pos), 1e-9)
            d = np.array([np.cos(th), np.sin(th)])
            if bounce == "specular":
                d = d - 2 * np.dot(d, n) * n
                th = float(np.arctan2(d[1], d[0]) + rng.normal(0, 0.12))
            else:
                th = float(np.arctan2(-n[1], -n[0]) + rng.uniform(-1.2, 1.2))
            kap *= -0.5
            nxt = pos + step * np.array([np.cos(th), np.sin(th)])
            if G.u(nxt) > 0:
                th = float(np.arctan2(-n[1], -n[0]))
                nxt = pos + step * np.array([np.cos(th), np.sin(th)])
        pos = nxt
        path.append(pos.copy())
    path.append(Lw[-1].copy())
    return to_s(np.asarray(path))
