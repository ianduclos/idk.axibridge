# FROZEN from research commit f59eac4: tools/gesture/gesture/kit/prosody_renderers.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Accumulation thread (round 9): mass built from visible line.

Round-8 principle 4 ("accumulation becomes a sign: restatement collapses into
a thing, and a bound turns process into an object") and Ian's preference for
the hand-made operators' line-built masses over learned solid blobs. Both
renderers draw every mark whole as a wire, then build weight ONLY over the
emphasised stretches (emphasis > thr; `emphasis` channel from `prosody`, or
r/2 when absent). The louder the stress, the more construction.

- `restate`  siyah mashq by machine: the stretch is written again n times,
             nearly on top of itself (slide along, drift across, a small turn,
             a smooth wobble, ends cut short differently) — n = 1 + (copies−1)·peak^γ.
             `bound` closes the accumulated process into an object:
             hull (convex, offset by bound_gap) | contour (the outline of the
             heap, smoothed) | none. Every copy is its own open, contiguous line.
- `coil`     a line-built mass whose core IS the line: rings offset outward from
             the stretch (k·spacing), each a little unsteady; `spiral` joins them
             into ONE contiguous line that winds out from the stretch.
             The outermost ring is marked filled (it is the object's edge).

The script-syntax finding these test: rewriting 3–8× builds weight in the
line's own shape; 20× collapses to a blob (`experiments/prosody_accumulation.py`
measures where, on drift lines).
"""
from __future__ import annotations

import math

import numpy as np

from .core import Ink, P, renderer


def emphasis_of(mark) -> np.ndarray:
    e = mark.channel("emphasis")
    return np.clip(e if e is not None else mark["r"] / 2.0, 0.0, 1.0)


def stretches(e: np.ndarray, thr: float) -> list[tuple[int, int, float]]:
    """Contiguous runs where e > thr: (i0, i1 inclusive, peak)."""
    on = e > thr
    if not on.any():
        return []
    d = np.diff(np.r_[0, on.astype(np.int8), 0])
    a, b = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1
    return [(int(i), int(j), float(e[i:j + 1].max())) for i, j in zip(a, b) if j - i >= 2]


def _normals(p: np.ndarray) -> np.ndarray:
    tg = np.gradient(p, axis=0)
    tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
    return np.column_stack([-tg[:, 1], tg[:, 0]])


def _arcl(p):
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


def _wobble(s: np.ndarray, amp: float, rng) -> np.ndarray:
    """Smooth lateral noise: two sinusoids, wavelengths 12–40 mm."""
    w = np.zeros(len(s))
    for _ in range(2):
        lam = rng.uniform(12.0, 40.0)
        w += rng.normal(0.0, amp) * np.sin(2 * np.pi * s / lam + rng.uniform(0, 2 * np.pi))
    return w


def restated(seg: np.ndarray, rng, *, drift: float, slide: float, turn: float, wobble: float,
             trim: float) -> np.ndarray:
    """One restatement of a stretch (mm)."""
    s = _arcl(seg)
    L = s[-1]
    a0, a1 = rng.uniform(0, trim), L - rng.uniform(0, trim)
    if a1 - a0 < 0.3 * L:
        a0, a1 = 0.0, L
    ss = np.linspace(a0, a1, max(int((a1 - a0) / 0.3), 3))
    p = np.column_stack([np.interp(ss, s, seg[:, 0]), np.interp(ss, s, seg[:, 1])])
    ch = seg[-1] - seg[0]
    t = ch / (np.linalg.norm(ch) + 1e-12) if np.linalg.norm(ch) > 1e-6 else np.array([1.0, 0.0])
    nv = np.array([-t[1], t[0]])
    c = seg.mean(axis=0)
    a = math.radians(rng.normal(0.0, turn))
    Rm = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    p = (p - c) @ Rm.T + c + t * rng.normal(0.0, slide) + nv * rng.normal(0.0, drift)
    return p + _normals(p) * _wobble(ss, wobble, rng)[:, None]


def bound_ring(lines: list[np.ndarray], kind: str, gap: float, pen: float) -> np.ndarray | None:
    import shapely  # noqa: PLC0415
    from shapely.geometry import MultiLineString  # noqa: PLC0415
    ml = MultiLineString([ln for ln in lines if len(ln) >= 2])
    if kind == "hull":
        g = ml.convex_hull.buffer(gap, quad_segs=12)
    else:
        g = ml.buffer(0.5 * pen + gap, quad_segs=8).buffer(1.5, quad_segs=8).buffer(-1.5, quad_segs=8)
    if g.is_empty:
        return None
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda q: q.area)
    g = g.simplify(0.05)
    return np.asarray(g.exterior.coords) if not shapely.is_empty(g) else None


BOUNDS = ("none", "hull", "contour")


def _restate_reach(p):
    return 0.5 * p["pen"] + 3.0 * (p["drift"] + p["wobble"]) + (p["bound_gap"] + 1.0 if p["bound"] != "none" else 0)


@renderer("restate", params=[
    P("pen", "float", 0.4, "pen width mm", min=0.05, max=3.0),
    P("thr", "float", 0.15, "emphasis above which a stretch is restated", min=0.0, max=0.99),
    P("copies", "int", 6, "statements at a loud stress (1 = wire only)", min=1, max=80),
    P("gamma", "float", 1.0, "copies = 1 + (copies−1)·peak^gamma (quiet stresses get fewer)", min=0.2, max=4.0),
    P("drift", "float", 0.7, "σ across the stretch, mm", min=0.0, max=10.0),
    P("slide", "float", 1.5, "σ along the stretch, mm", min=0.0, max=20.0),
    P("turn", "float", 1.5, "σ of the turn, degrees", min=0.0, max=30.0),
    P("wobble", "float", 0.35, "smooth lateral wobble amplitude, mm", min=0.0, max=5.0),
    P("trim", "float", 2.0, "each copy's ends cut short by up to this, mm", min=0.0, max=30.0),
    P("bound", "choice", "none", "close the heap into an object: none | hull | contour", choices=BOUNDS),
    P("bound_gap", "float", 1.2, "offset of the bound from the heap, mm", min=0.0, max=20.0),
], reach=_restate_reach, doc="mass by restatement: emphasised stretches written again n times "
                             "(mashq), optionally closed by a bound")
def restate(ctx, marks, *, pen, thr, copies, gamma, drift, slide, turn, wobble, trim, bound, bound_gap):
    out = []
    for mi, m in enumerate(marks):
        if len(m) < 2:
            continue
        vid = m.meta.get("voice_id")
        out.append(Ink(m.points, pen=pen, meta={"voice": vid, "role": "line"}))
        e = emphasis_of(m)
        for ri, (i0, i1, peak) in enumerate(stretches(e, thr)):
            seg = np.asarray(m.points[i0:i1 + 1])
            n = 1 + int(round((copies - 1) * peak ** gamma))
            rng = ctx.rng("restate", mi, ri)
            lines = [seg]
            for _ in range(n - 1):
                c = restated(seg, rng, drift=drift, slide=slide, turn=turn, wobble=wobble, trim=trim)
                lines.append(c)
                out.append(Ink(c, pen=pen, meta={"voice": vid, "role": "restate", "stretch": ri}))
            if bound != "none" and n > 1:
                ring = bound_ring(lines, bound, bound_gap, pen)
                if ring is not None and len(ring) >= 4:
                    out.append(Ink(ring, closed=True, filled=False, pen=pen,
                                   meta={"voice": vid, "role": "bound", "stretch": ri}))
    return out


def _ring_start(ring: np.ndarray, near: np.ndarray) -> np.ndarray:
    """Closed ring (first == last) re-started at its vertex nearest `near`."""
    body = ring[:-1]
    k = int(np.argmin(np.linalg.norm(body - near, axis=1)))
    body = np.roll(body, -k, axis=0)
    return np.vstack([body, body[:1]])


def coil_rings(seg: np.ndarray, k: int, spacing: float, jitter: float, rng) -> list[np.ndarray]:
    from shapely.geometry import LineString  # noqa: PLC0415
    ls = LineString(seg)
    rings = []
    for j in range(1, k + 1):
        g = ls.buffer(j * spacing, quad_segs=16)
        if g.geom_type == "MultiPolygon":
            g = max(g.geoms, key=lambda q: q.area)
        r = np.asarray(g.exterior.coords)
        if len(r) < 4:
            continue
        s = _arcl(r)
        n = max(int(s[-1] / 0.3), 8)
        ss = np.linspace(0, s[-1], n + 1)
        r = np.column_stack([np.interp(ss, s, r[:, 0]), np.interp(ss, s, r[:, 1])])
        if jitter > 0:
            w = _wobble(ss, jitter * spacing, rng)
            w -= np.linspace(0, 1, len(w)) * (w[-1] - w[0])        # keep it closed
            r = r + _normals(r) * w[:, None]
        r[-1] = r[0]
        rings.append(r)
    return rings


@renderer("coil", params=[
    P("pen", "float", 0.4, "pen width mm", min=0.05, max=3.0),
    P("thr", "float", 0.15, "emphasis above which a stretch is coiled", min=0.0, max=0.99),
    P("rings", "int", 5, "rings at a loud stress", min=1, max=60),
    P("gamma", "float", 1.0, "rings = rings·peak^gamma (≥ 1)", min=0.2, max=4.0),
    P("spacing", "float", 0.6, "ring spacing mm (≈ 1.5 pen keeps every ring legible)", min=0.1, max=10.0),
    P("jitter", "float", 0.25, "ring unsteadiness, in spacings", min=0.0, max=2.0),
    P("shape", "choice", "spiral", "spiral: one contiguous line winding out | rings: closed rings",
      choices=("spiral", "rings")),
], reach=lambda p: p["rings"] * p["spacing"] * (1 + p["jitter"]) + 0.5 * p["pen"],
   doc="a line-built mass whose core is the line: rings (or one spiral) offset out from emphasised stretches")
def coil(ctx, marks, *, pen, thr, rings, gamma, spacing, jitter, shape):
    out = []
    for mi, m in enumerate(marks):
        if len(m) < 2:
            continue
        vid = m.meta.get("voice_id")
        out.append(Ink(m.points, pen=pen, meta={"voice": vid, "role": "line"}))
        e = emphasis_of(m)
        for ri, (i0, i1, peak) in enumerate(stretches(e, thr)):
            seg = np.asarray(m.points[i0:i1 + 1])
            k = max(1, int(round(rings * peak ** gamma)))
            rs = coil_rings(seg, k, spacing, jitter, ctx.rng("coil", mi, ri))
            if not rs:
                continue
            if shape == "rings":
                for j, r in enumerate(rs):
                    out.append(Ink(r, closed=True, filled=j == len(rs) - 1, pen=pen,
                                   meta={"voice": vid, "role": "coil", "stretch": ri}))
                continue
            path, cur = [], seg[-1]
            for r in rs:
                r = _ring_start(r, cur)
                path.append(r)
                cur = r[-1]
            out.append(Ink(np.vstack(path), pen=pen, meta={"voice": vid, "role": "coil", "stretch": ri}))
    return out
