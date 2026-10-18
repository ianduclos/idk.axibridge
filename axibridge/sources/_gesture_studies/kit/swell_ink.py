# FROZEN from research commit efce219: tools/gesture/gesture/kit/swell_ink.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Round 11, exploration 2 — swelling into mass (thread `swell`).

Ian on round 10 (results/round10-review-2026-10-17.md): beads "slightly
better … more deliberate with the dots"; "smoother transitions when going to
those thicker shapes"; rosary "if the dotted shapes would be more interesting
perhaps, and bolder gestures". Round 6: one line becoming nib and mass.

`swell` — the line SWELLS into its mass instead of meeting a bead. The inked
shape is a sweep of discs along the line: at arc length s a disc of radius
r(s) centred on the line (or pushed off it, for `momentum` / `sag`). r(s) is
smooth, so the outline grows continuously from the pen width to the mass and
back. Profiles (per stress; the head sits where dev_beads would put its bead,
with the same diameter D, so the two compare one to one):

  bell      smootherstep up and down over `length`·D each side (C2). The
            naive smooth swell; its top is flat, so it is the sausage risk
  lens      two-rate exponential both sides: a slow thin tail, then a fast
            bloom into a round head (r' at the head = k_head < 1, so the
            outline is tangent to the head disc: C1)
  drop      lens with the slow tail coming IN only; the line exits the head
            thin on the far side, fast but still tangent (k 0.95)
  press     drop reversed: the pen lands heavy and lifts away in a long tail
  turn      r follows the line's own |curvature| near the stress (Lipschitz
            k_head, smoothed): the mass peaks at the turn and wraps it
  momentum  drop whose discs slide along the incoming tangent: the mass
            overshoots the stress (carry) and the line leaves from its side
  sag       lens whose discs hang below the line (gravity): a drop on a wire
  necklace  `lobes` lobes of falling size with smooth necks (a string of
            beads that is one swelling line)

The slow part of every lens/drop/press tail stays below `tail_w` wide (the
width of a nib, not of a mass); only the head blooms. That is how a swell can
be smooth AND round: the elongated part of the transition is a line, the
mass part is a disc.

`swell_dots` — dots placed by a rule the eye can follow (rule), in a small
size vocabulary (sizes: a pattern of L / m / s cycled along the line), each
size in its own shape (shape_L, shape_s): disc, ring (a dot with a hole —
the line shows through it), split (the line runs through the slit), comma (a
dot with a tail), wound (the line itself winds out and back in: a dot made
of the line, contiguous with it).

`swell_place` — parts in authored boxes (fractions of the frame), so one
bold gesture can fill a third of the sheet, overlap another, or sit apart.

Fills are line-built: the outline ring (filled=True) plus ONE inset spiral
per component (concentric insets joined; a split recurses), never hatching.
Disc-like dots use a true Archimedean spiral (one path, no jumps).
"""
from __future__ import annotations

import math

import numpy as np

from .core import P, arranger, renderer
from .dev_beads import bead_diameter, bead_emphasis, runs

STEP = 0.25                     # mm: sweep sampling
PROFILES = ("bell", "lens", "drop", "press", "turn", "momentum", "sag", "necklace")
AT = ("peak", "event", "end", "centre")
RULES = ("inflection", "turns", "beat", "count", "decel", "fullstop", "pauses")
DOTS = ("disc", "ring", "split", "comma", "wound")


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def _arcl(p):
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


def _resample(pts, step=STEP):
    s = _arcl(pts)
    if s[-1] <= 0:
        return pts.copy(), s
    n = max(int(math.ceil(s[-1] / step)) + 1, 2)
    u = np.linspace(0, s[-1], n)
    return np.column_stack([np.interp(u, s, pts[:, 0]), np.interp(u, s, pts[:, 1])]), u


def _tangents(p):
    t = np.gradient(p, axis=0)
    return t / (np.linalg.norm(t, axis=1, keepdims=True) + 1e-12)


def _curvature(p, s, sigma_mm=1.0):
    from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
    t = np.gradient(p, axis=0)
    th = np.unwrap(np.arctan2(t[:, 1], t[:, 0]))
    ds = max(float(np.median(np.diff(s))), 1e-6)
    return gaussian_filter1d(np.gradient(th) / ds, max(sigma_mm / ds, 0.5), mode="nearest")


def smootherstep(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * u * (u * (6 * u - 15) + 10)


def side(x, R, r0, k, tail, tail_w):
    """One side of a lens/drop, x ≥ 0 mm from the head: a fast exponential
    bloom (slope k at the head) plus a slow thin tail (reaches tail_w wide,
    e-folds over tail/3)."""
    x = np.maximum(x, 0.0)
    A = max(R - r0, 1e-6)
    A1 = float(np.clip(0.5 * tail_w - r0, 0.0, 0.6 * A)) if tail > 0 else 0.0
    A2 = A - A1
    out = r0 + A2 * np.exp(-x / max(A2 / max(k, 1e-3), 1e-3))
    if A1 > 0:
        out = out + A1 * np.exp(-x / max(tail / 3.0, 1e-3))
    return out


def lipschitz_up(r, s, k):
    """Smallest function ≥ r with slope ≤ k (peaks kept, flanks raised)."""
    out = r.copy()
    for i in range(1, len(r)):                     # forward then backward pass: max-plus with a cone
        out[i] = max(out[i], out[i - 1] - k * (s[i] - s[i - 1]))
    for i in range(len(r) - 2, -1, -1):
        out[i] = max(out[i], out[i + 1] - k * (s[i + 1] - s[i]))
    return out


def sweep(C, r):
    """Union of discs (C_i, r_i) and the hulls of consecutive pairs: the
    swept shape of a disc of varying radius along a polyline."""
    import shapely  # noqa: PLC0415
    if len(C) == 1:
        return shapely.buffer(shapely.points(C[0]), float(r[0]), quad_segs=12)
    d = shapely.buffer(shapely.points(C), r, quad_segs=12)
    hulls = shapely.convex_hull(shapely.union(d[:-1], d[1:]))
    return shapely.union_all(hulls)


def _pieces(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [q for q in getattr(g, "geoms", []) if q.geom_type == "Polygon" and not q.is_empty]


def _inset_paths(poly, step, here=None) -> list[np.ndarray]:
    """Concentric insets of poly (already pen-inset), joined into one open
    path per chain; a split recurses into one path per child."""
    paths, chain = [], []
    cur = [poly]
    while len(cur) == 1:
        g = cur[0]
        ring = np.asarray(g.exterior.coords)[:-1]
        if len(ring) >= 3:
            if here is not None:
                k = int(np.argmin(np.linalg.norm(ring - here, axis=1)))
                ring = np.roll(ring, -k, axis=0)
            ring = np.vstack([ring, ring[:1]])
            chain.append(ring)
            here = ring[-1]
        for hole in g.interiors:                    # a loop's eye: its rim as its own closed path
            paths.append(np.asarray(hole.coords))
        nxt = g.buffer(-step, quad_segs=8)
        cur = [q for q in _pieces(nxt) if q.area > 0.05 * step * step]
    if chain:
        paths.insert(0, np.vstack(chain))
    for q in cur:
        paths += _inset_paths(q, step, here)
    return paths


def line_fill(geom, pen, pitch) -> list[tuple[np.ndarray, bool, bool]]:
    """A shape inked line-built: per component its outline ring (closed,
    filled) and one inset spiral (open). → [(points, closed, filled)]."""
    out = []
    g = geom.buffer(-0.5 * pen, quad_segs=8)
    step = max(pitch * pen, 0.05)
    for piece in _pieces(g):
        ext = np.asarray(piece.exterior.coords)
        out.append((ext, True, True))
        for hole in piece.interiors:
            out.append((np.asarray(hole.coords), True, False))
        inner = piece.buffer(-step, quad_segs=8)
        for q in _pieces(inner):
            if q.area <= 0.05 * step * step:
                continue
            for p in _inset_paths(q, step, ext[0]):
                out.append((p, bool(np.allclose(p[0], p[-1])) and len(p) > 3, False))
        if not _pieces(inner):                     # thinner than two pitches: a centre dot
            c = np.asarray(piece.representative_point().coords[0])
            out.append((np.vstack([c, c + 1e-3]), False, False))
    return out


# ---------------------------------------------------------------------------
# swell profiles
# ---------------------------------------------------------------------------

def _head_index(e, i0, i1, at, pts):
    seg = e[i0:i1 + 1]
    if at == "event":
        return i0
    if at == "end":
        return i1
    if at == "centre":
        return (i0 + i1) // 2
    return i0 + int(np.argmax(seg))


def stress_profile(kind, s, pts, h, R, r0, prm, kappa):
    """r(s) (radius) and centre offsets (n, 2) for ONE stress whose head is at
    index h. Offsets are zero except for momentum / sag."""
    x = s - s[h]
    off = np.zeros((len(s), 2))
    k = prm["k_head"]
    tail, tw = prm["tail"], prm["tail_w"]
    if kind == "bell":
        L = max(prm["length"] * 2 * R, 1e-3)
        r = r0 + (R - r0) * (1 - smootherstep(np.abs(x) / L))
    elif kind in ("lens", "sag"):
        r = side(np.abs(x), R, r0, k, 0.5 * tail, tw)
    elif kind in ("drop", "momentum"):
        r = np.where(x < 0, side(-x, R, r0, k, tail, tw), side(np.maximum(x, 0), R, r0, 0.95, 0.0, tw))
    elif kind == "press":
        r = np.where(x > 0, side(x, R, r0, k, tail, tw), side(np.maximum(-x, 0), R, r0, 0.95, 0.0, tw))
    elif kind == "turn":
        win = np.abs(x) <= 2.5 * R + 0.5 * tail
        r = np.full(len(s), r0)
        if win.sum() >= 3:
            # shape relative to the tightest turn in reach (^3: secondary corners stay thin), amplitude gated
            # by how tight that turn is (full only when it turns tighter than ~1.5 head radii). Purely
            # relative made a gentle bend a sausage; purely absolute merged every chain corner into one.
            a = np.abs(kappa[win])
            g = (a / (a.max() + 1e-12)) ** 3 * min(1.0, float(a.max()) * 1.5 * R)
            rr = r0 + (R - r0) * g
            rr = lipschitz_up(rr, s[win], k)
            from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
            rr = np.minimum(gaussian_filter1d(rr, 0.6 / STEP, mode="nearest"), R)
            # fade the window edges so the swell ends on the pen width (C1)
            u = np.abs(x[win]) / (2.5 * R + 0.5 * tail)
            rr = r0 + (rr - r0) * (1 - smootherstep((u - 0.7) / 0.3))
            r[win] = rr
    elif kind == "necklace":
        n = int(prm["lobes"])
        radii = R * np.array([0.78 ** i for i in range(n)])
        cs = [0.0]
        for i in range(1, n):
            cs.append(cs[-1] + 1.18 * (radii[i - 1] + radii[i]))
        cs = np.asarray(cs) - 0.35 * cs[-1]
        r = np.full(len(s), r0)
        for c, rad in zip(cs, radii):
            r = np.maximum(r, side(np.abs(x - c), rad, r0, 0.9, 0.0, tw))
    else:
        raise ValueError(kind)
    g = np.clip((r - r0) / max(R - r0, 1e-9), 0.0, 1.0)
    if kind == "momentum":
        j = int(np.searchsorted(s, s[h] - 0.8 * R))
        j = int(np.clip(j, 0, max(h - 1, 0)))
        t_in = pts[h] - pts[j]
        t_in = t_in / (np.linalg.norm(t_in) + 1e-12)
        off = (prm["carry"] * 2 * R * smootherstep(g) )[:, None] * t_in[None, :]
    elif kind == "sag":
        off[:, 1] = prm["sag"] * R * g ** 2
    return r, off


def swell_geometry(mark, prm, rng=None):
    """→ (shapely geometry of the swelled masses or None, info dict). Pure."""
    import shapely  # noqa: PLC0415
    pts0 = np.asarray(mark.points)
    if len(pts0) < 2:
        return None, {"stresses": []}
    e0 = bead_emphasis(mark)
    s0 = _arcl(pts0)
    pts, s = _resample(pts0)
    e = np.interp(s, s0, e0)
    r0 = 0.5 * prm["pen"]
    rr = np.full(len(s), r0)
    off = np.zeros((len(s), 2))
    kappa = _curvature(pts, s) if prm["profile"] == "turn" else None
    info = []
    for i0, i1, peak in runs(e, prm["thr"]):
        L = float(s[i1] - s[i0])
        D = bead_diameter(prm["size"], peak, L, prm["length_gain"])
        R = 0.5 * D
        h = _head_index(e, i0, i1, prm["at"], pts)
        if prm["profile"] == "turn":
            lo = int(np.searchsorted(s, s[i0] - 0.5 * D))      # the tightest turn of the whole stressed stretch
            hi = int(np.searchsorted(s, s[i1] + 0.5 * D))
            h = lo + int(np.argmax(np.abs(kappa[lo:hi + 1]))) if hi > lo else h
        r, o = stress_profile(prm["profile"], s, pts, h, R, r0, prm, kappa)
        win = r > rr
        rr = np.where(win, r, rr)
        off[win] = o[win]
        info.append({"s": float(s[h]), "D": float(D), "peak": float(peak), "L": L})
    on = rr > 1.15 * r0
    if not on.any():
        return None, {"stresses": info}
    C = pts + off
    d = np.diff(np.r_[0, on.astype(np.int8), 0])
    a, b = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    geoms = [sweep(C[i:j], rr[i:j]) for i, j in zip(a, b) if j > i]
    g = shapely.union_all(geoms) if geoms else None
    return g, {"stresses": info}


def _swell_reach(p):
    push = {"momentum": p.get("carry", 0.0) * 2, "sag": 0.5 * p.get("sag", 0.0)}.get(p.get("profile"), 0.0)
    return 0.5 * p["size"] * 1.3 * (1.0 + push) + 0.5 * p["pen"] + 0.5


SWELL_PARAMS = [
    P("profile", "choice", "drop", " | ".join(PROFILES), choices=PROFILES),
    P("at", "choice", "peak", "where the head sits in the stressed stretch (peak = where dev_beads puts its bead)",
      choices=AT),
    P("line", "choice", "wire", "wire: the line is drawn through its swells | none: a ghost, only the masses",
      choices=("wire", "none")),
    P("pen", "float", 0.4, "pen width mm", min=0.05, max=3.0),
    P("thr", "float", 0.15, "emphasis above which a stretch swells", min=0.0, max=0.99),
    P("size", "float", 7.0, "head diameter at a loud stress, mm (dev_beads' bead size)", min=0.5, max=40.0),
    P("length_gain", "float", 0.25, "how much a longer stretch grows its head (dev_beads)", min=0.0, max=1.0),
    P("length", "float", 1.0, "bell: half-length of the swell, in head diameters", min=0.2, max=6.0),
    P("k_head", "float", 0.75, "slope dr/ds where the bloom meets the head (< 1 keeps it tangent; high = rounder)",
      min=0.05, max=0.98),
    P("tail", "float", 18.0, "length of the slow thin tail, mm (lens: half each side)", min=0.0, max=120.0),
    P("tail_w", "float", 1.6, "width the slow tail reaches before the head blooms, mm (keep < 3.2: a line, not a mass)",
      min=0.1, max=6.0),
    P("carry", "float", 0.45, "momentum: how far the mass overshoots along the incoming direction, in head diameters",
      min=0.0, max=1.5),
    P("sag", "float", 0.7, "sag: how far the mass hangs below the line, in head radii", min=0.0, max=1.5),
    P("lobes", "int", 3, "necklace: lobes per stress", min=2, max=6),
    P("pitch", "float", 0.85, "fill: inset spacing in pens (< 1 reads solid)", min=0.4, max=4.0),
]


# Occasional dots on a swelling line (round 12). Ian on round 11's dots: "I
# like 3 7" (dots counted 1, 2, 3 at the strongest events; the line winding
# into wound dots at its turns) and on the shapes: "not crazy about split and
# wound. others can be useful from time to time". So: an option, never the
# default — `dots: none` draws exactly what the swell renderer drew before.
SWELL_DOT_RULES = ("none", "count", "turns")
SWELL_DOT_SHAPES = ("disc", "ring", "comma", "wound")
SWELL_DOT_PARAMS = [
    P("dots", "choice", "none", "occasional deliberate dots on the swelling line: none | count (1, 2, 3 at its "
      "strongest events) | turns (at its turns)", choices=SWELL_DOT_RULES),
    P("dot_shape", "choice", "disc", "dots: their shape (wound: the line itself winds out and back in)",
      choices=SWELL_DOT_SHAPES),
    P("dot_size", "float", 6.0, "dots: large dot diameter, mm", min=0.5, max=30.0),
    P("dot_gap", "float", 24.0, "dots: minimum mm between dots (or groups)", min=0.0, max=500.0),
    P("dot_scale", "float", 2.0, "dots = turns: the scale the line is heard at, mm", min=0.5, max=60.0),
]


def _swell_dot_inks(ctx, mi, m, prm, line_ink, g=None):
    """Dots for one mark by the swell's dot option; a wound dot is spliced into
    the line (→ the replaced line ink), every other shape is its own ink. No
    dot is placed inside or against a swell's mass (`g`)."""
    avoid = None
    if g is not None:
        import shapely  # noqa: PLC0415
        clear = 0.5 * prm["dot_size"] + 2.0 * prm["pen"]

        def avoid(q, x):
            pts_, s_ = np.asarray(q.points), q.arclength()
            c = shapely.Point(float(np.interp(x, s_, pts_[:, 0])), float(np.interp(x, s_, pts_[:, 1])))
            return bool(g.distance(c) < clear)
    count = prm["dots"] == "count"
    plan, _, q = dot_plan(m, {"rule": prm["dots"], "sizes": "", "gap": prm["dot_gap"], "scale": prm["dot_scale"],
                              "period": 16.0, "phrase": 70.0, "decel_n": 6, "decel_q": 0.68, "thr": 0.15,
                              "size": prm["dot_size"]}, avoid=None if count else avoid)
    if count and avoid is not None and plan:
        # a count sits on the line's strongest events, which are where it swells:
        # each group slides on, in the direction of travel, until it is clear of
        # the mass — the mass, then its 1, 2 or 3 dots (dropped if none fits)
        L = float(q.arclength()[-1])
        moved = []
        for gi in sorted({g for _, _, g in plan}):
            grp = [(x, c) for x, c, g in plan if g == gi]
            for t in np.arange(0.0, 80.0, 1.0):
                if all(2.0 < x + t < L - 2.0 and not avoid(q, x + t) for x, _ in grp):
                    moved += [(float(x + t), c, gi) for x, c in grp]
                    break
        plan = moved
    if not plan:
        return line_ink, []
    vid = m.meta.get("voice_id")
    rng = ctx.rng("swell_dots", mi)
    pts = np.asarray(q.points)
    s = q.arclength()
    tg = _tangents(pts)
    frac = {"L": 1.0, "m": 0.68, "s": 0.4}
    pen, pitch, shp = prm["pen"], prm["pitch"], prm["dot_shape"]
    dots, wound_at = [], []
    for x, cls, g in plan:
        c = np.array([np.interp(x, s, pts[:, 0]), np.interp(x, s, pts[:, 1])])
        t = np.array([np.interp(x, s, tg[:, 0]), np.interp(x, s, tg[:, 1])])
        t = t / (np.linalg.norm(t) + 1e-12)
        d = prm["dot_size"] * frac[cls]
        if shp == "wound" and line_ink is not None:
            wound_at.append((x, c, t, d))
            continue
        for p, closed, filled in dot_shapes(shp, c, t, d, pen, pitch, rng, 0.05, 0.45):
            dots.append(Ink_(p, pen, {"voice": vid, "role": f"dot:{shp}:{cls}", "group": int(g)}, closed, filled))
    if wound_at:
        path = pts
        for x, c, t, d in sorted(wound_at, key=lambda w: -w[0]):
            k = int(np.searchsorted(s, x))
            path = np.vstack([path[:k], wound_path(c, t, 0.5 * d, pen, pitch, 0.0), path[k:]])
        line_ink = Ink_(path, pen, {"voice": vid, "role": "line"})
    return line_ink, dots


@renderer("swell", params=[*SWELL_PARAMS, *SWELL_DOT_PARAMS], reach=_swell_reach,
          doc="the line swells smoothly into round masses at its stresses (a sweep of growing discs), line-built")
def swell(ctx, marks, **prm):
    out = []
    for mi, m in enumerate(marks):
        if len(m) < 2:
            continue
        vid = m.meta.get("voice_id")
        li = None
        if prm["line"] == "wire":
            li = len(out)
            out.append(Ink_(m.points, prm["pen"], {"voice": vid, "role": "line"}))
        g, _ = swell_geometry(m, prm)
        dots = []
        if prm.get("dots", "none") != "none":
            line_ink, dots = _swell_dot_inks(ctx, mi, m, prm, out[li] if li is not None else None, g)
            if li is not None:
                out[li] = line_ink
        if g is not None:
            for p, closed, filled in line_fill(g, prm["pen"], prm["pitch"]):
                out.append(Ink_(p, prm["pen"], {"voice": vid, "role": f"swell:{prm['profile']}"}, closed, filled))
        out += dots
    return out


def Ink_(p, pen, meta, closed=False, filled=False):
    from .core import Ink  # noqa: PLC0415
    return Ink(np.asarray(p, dtype=np.float64), closed=closed, filled=filled, pen=pen, meta=meta)


# ---------------------------------------------------------------------------
# deliberate dots
# ---------------------------------------------------------------------------

def _harm(rng, wobble):
    ph = rng.uniform(0, 2 * np.pi, 2)
    am = rng.normal(0.0, wobble, 2)
    return lambda t: 1.0 + am[0] * np.cos(2 * t + ph[0]) + am[1] * np.cos(3 * t + ph[1])


def spiral_disc(c, R, pen, pitch, k, r_in=0.0, phase=0.0):
    """Outer ring (closed, filled) + ONE Archimedean spiral from the rim to
    r_in (+ the inner rim when r_in > 0). Radii are scaled by k(θ)."""
    ro = R - 0.5 * pen
    ri = r_in + 0.5 * pen if r_in > 0 else 0.0
    if ro <= 0.3 * pen:
        return [(np.vstack([c, c + 1e-3]), False, False)]
    n = max(int(2 * math.pi * ro / 0.25), 24)
    t = np.linspace(0, 2 * np.pi, n + 1) + phase
    ring = np.column_stack([c[0] + ro * k(t) * np.cos(t), c[1] + ro * k(t) * np.sin(t)])
    out = [(ring, True, True)]
    p = max(pitch * pen, 0.05)
    turns = max((ro - ri) / p, 0.0)
    if turns > 0.05:
        th = np.linspace(0, 2 * np.pi * turns, max(int(turns * n), 8)) + phase
        rad = ro - (ro - ri) * (th - phase) / (2 * np.pi * turns)
        out.append((np.column_stack([c[0] + rad * k(th) * np.cos(th), c[1] + rad * k(th) * np.sin(th)]), False, False))
    if r_in > 0:
        out.append((np.column_stack([c[0] + ri * k(t) * np.cos(t), c[1] + ri * k(t) * np.sin(t)]), True, False))
    return out


def wound_path(c, tang, R, pen, pitch, turns):
    """The line itself winds out from c and back in (two interleaved
    spirals): a dot made of the line, entered and left at its centre."""
    p = max(pitch * pen, 0.05)
    ro = max(R - 0.5 * pen, 0.5 * pen)
    nt = turns if turns > 0 else max(ro / (2 * p), 0.6)
    a0 = math.atan2(tang[1], tang[0])
    n = max(int(nt * 64), 24)
    th = np.linspace(0, 2 * np.pi * nt, n)
    out_r = ro * th / th[-1]
    back_r = ro * (1 - th / th[-1]) * (1 - 0.5 * p / ro)
    go = np.column_stack([out_r * np.cos(a0 + th), out_r * np.sin(a0 + th)])
    th2 = th[-1] + np.pi / max(nt, 1.0) + th
    back = np.column_stack([back_r * np.cos(a0 + th2), back_r * np.sin(a0 + th2)])
    # bridge the hand-over along the rim (an arc, not a chord)
    u = np.linspace(0, 1, 12)[1:-1]
    ab = th[-1] + u * (th2[0] - th[-1])
    rb = out_r[-1] + u * (back_r[0] - out_r[-1])
    arc = np.column_stack([rb * np.cos(a0 + ab), rb * np.sin(a0 + ab)])
    return c + np.vstack([go, arc, back])


def dot_shapes(shape, c, tang, d, pen, pitch, rng, wobble, hole):
    """→ list of (points, closed, filled) for one dot of diameter d."""
    from shapely.geometry import Polygon  # noqa: PLC0415
    R = 0.5 * d
    k = _harm(rng, wobble)
    nrm = np.array([-tang[1], tang[0]])
    if shape == "disc":
        return spiral_disc(c, R, pen, pitch, k)
    if shape == "ring":
        return spiral_disc(c, R, pen, pitch, k, r_in=max(hole * R, 1.5 * pen))
    if shape == "wound":
        return [(wound_path(c, tang, R, pen, pitch, 0.0), False, False)]
    t = np.linspace(0, 2 * np.pi, 96, endpoint=False)
    circ = np.column_stack([c[0] + R * k(t) * np.cos(t), c[1] + R * k(t) * np.sin(t)])
    disc = Polygon(circ).buffer(0)
    if shape == "split":
        gap = max(2.6 * pen, 0.16 * d)
        far = 2 * d
        a = c - far * tang
        b = c + far * tang
        strip = Polygon([a + 0.5 * gap * nrm, b + 0.5 * gap * nrm, b - 0.5 * gap * nrm, a - 0.5 * gap * nrm])
        g = disc.difference(strip)
        out = []
        for q in _pieces(g):
            out += line_fill(q, pen, pitch)
        return out
    if shape == "comma":
        side_ = 1.0 if rng.random() < 0.5 else -1.0
        L = 1.5 * d
        u = np.linspace(0, 1, 40)
        ang = math.atan2(-side_ * nrm[1] - 0.5 * tang[1], -side_ * nrm[0] - 0.5 * tang[0])
        turn = side_ * 1.6 * u ** 1.3
        dirs = np.column_stack([np.cos(ang + turn), np.sin(ang + turn)])
        path = c + np.vstack([[0, 0], np.cumsum(dirs[1:] * (L / 39), axis=0)])
        rad = np.maximum(0.62 * R * (1 - smootherstep(u)) , 0.5 * pen * 1.2)
        g = disc.union(sweep(path, rad))
        return line_fill(g, pen, pitch)
    raise ValueError(shape)


def _phrases(q, s, phrase):
    """Phrase ends (s mm): hand switches when the line has a voice channel,
    else the strongest events at least `phrase` apart; always the line's end."""
    from .prosody_modulators import line_events  # noqa: PLC0415
    L = float(s[-1])
    ends = []
    if "voice" in q.channels:
        v = np.round(np.asarray(q["voice"]))
        sw = s[np.nonzero(np.diff(v) != 0)[0] + 1]
        last = -1e9
        for x in sw:
            if x - last >= 0.5 * phrase and x > 0.5 * phrase and L - x > 0.5 * phrase:
                ends.append(float(x))
                last = x
    if not ends:
        evs = sorted(line_events(q), key=lambda e: (-e[1], e[0]))
        for x, _, _ in evs:
            if x > phrase * 0.6 and L - x > phrase * 0.6 and all(abs(x - y) >= phrase for y in ends):
                ends.append(float(x))
    return sorted(ends) + [L]


def shape_events(q, rule, scale):
    """Inflections / turns heard at a chosen scale (mm), so a big smooth hand
    is heard at its own size: [(s, salience 0..1, kind)]."""
    from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
    from scipy.signal import find_peaks  # noqa: PLC0415
    pts = np.asarray(q.points)
    s = q.arclength()
    ds = max(float(np.median(np.diff(s))), 1e-6)
    t = np.gradient(pts, axis=0)
    th = np.unwrap(np.arctan2(t[:, 1], t[:, 0]))
    k = gaussian_filter1d(np.gradient(th) / ds, scale / ds, mode="nearest")
    out = []
    if rule == "inflection":
        for i in np.nonzero(np.signbit(k[1:]) != np.signbit(k[:-1]))[0]:
            left = abs(th[i] - np.interp(s[i] - 2 * scale, s, th))
            right = abs(np.interp(s[i] + 2 * scale, s, th) - th[i])
            m = min(left, right)
            if m > 0.12:
                out.append((float(s[i]), float(min(1.0, m / 0.8)), "inflection"))
    else:
        a = np.abs(k)
        pk, _ = find_peaks(a, height=np.percentile(a, 75), distance=max(int(scale / ds), 1))
        hi = a.max() + 1e-12
        out = [(float(s[i]), float(a[i] / hi), "turn") for i in pk]
    return out


def dot_plan(mark, prm, avoid=None):
    """[(s mm, size class 'L'|'m'|'s', group)] along the mark, by `rule`, plus
    the phrase ends used (for fullstop). Deterministic. `avoid(q, s)` (optional)
    → True where an event must not take a dot (the swell option: not inside a
    mass)."""
    from .prosody_modulators import STEP as PSTEP  # noqa: PLC0415
    from .prosody_modulators import line_events  # noqa: PLC0415
    q = mark.resampled(PSTEP)
    s = q.arclength()
    L = float(s[-1])
    rule, gap = prm["rule"], prm["gap"]
    plan, ends = [], []

    def greedy(evs):
        keep = []
        for x, lv, kd in sorted(evs, key=lambda e: (-e[1], e[0])):
            if avoid is not None and avoid(q, x):
                continue
            if 2.0 < x < L - 2.0 and all(abs(x - y[0]) >= gap for y in keep):
                keep.append((x, lv, kd))
        return sorted(keep)

    if rule in ("inflection", "turns"):
        evs = greedy(shape_events(q, rule, prm["scale"]))
        if evs:
            lv = np.array([e[1] for e in evs])
            cut = np.quantile(lv, 0.67) if len(lv) > 2 else lv.max()
            plan = [(x, "L" if l >= cut else "s", i) for i, (x, l, _) in enumerate(evs)]
    elif rule == "beat":
        xs = np.arange(0.5 * prm["period"], L - 1.0, prm["period"])
        plan = [(float(x), "Lss"[i % 3], i) for i, x in enumerate(xs)]
    elif rule == "count":
        evs = greedy(line_events(q))
        for gi, (x, _, _) in enumerate(evs):
            n = gi % 3 + 1
            step = prm["size"] * 0.8
            for j in range(n):
                y = x + (j - 0.5 * (n - 1)) * step
                if 0 < y < L:
                    plan.append((float(y), "m", gi))
    elif rule in ("decel", "fullstop"):
        ends = _phrases(q, s, prm["phrase"])
        for gi, x in enumerate(ends):
            x = min(x, L - 0.01)
            if rule == "fullstop":
                plan.append((x, "L", gi))
                continue
            n, qq = int(prm["decel_n"]), prm["decel_q"]
            g0 = prm["size"] * 2.2
            gaps = g0 * qq ** np.arange(n - 1)
            pos = x - np.r_[0.0, np.cumsum(gaps[::-1])][::-1]
            for j, y in enumerate(pos):
                if y > 0:
                    plan.append((float(y), "L" if j == n - 1 else ("m" if j >= n - 3 else "s"), gi))
    elif rule == "pauses":
        e = bead_emphasis(q)
        from scipy.signal import find_peaks  # noqa: PLC0415
        pk, _ = find_peaks(np.r_[0, e, 0], height=prm["thr"], distance=max(int(gap / PSTEP), 1))
        pk = pk - 1
        top = float(e[pk].max()) if len(pk) else 1.0           # loud = among this hand's own loudest pauses
        plan = [(float(s[i]), "L" if e[i] >= 0.6 * top else "s", n) for n, i in enumerate(pk)]
    pat = prm["sizes"].strip()
    if pat:
        if rule == "count":
            plan = [(x, pat[g % len(pat)], g) for x, _, g in plan]
        else:
            plan = [(x, pat[i % len(pat)], g) for i, (x, _, g) in enumerate(plan)]
    plan = [(x, c, g) for x, c, g in plan if c in "Lms"]      # '.' in a pattern is a rest
    return plan, ends, q


def _dots_reach(p):
    return 0.5 * p["size"] * 1.6 + 0.5 * p["pen"] + 0.5


@renderer("swell_dots", params=[
    P("rule", "choice", "inflection", "inflection (the line's own inflections) | turns | beat (a metre: L s s) | "
      "count (groups of 1, 2, 3 at its events) | decel (dots close up like a slowing pen at each phrase end) | "
      "fullstop (each phrase ends in a dot, the pen lifts, the line resumes) | pauses (the hand's stresses: "
      "loud L, quiet s)", choices=RULES),
    P("sizes", "str", "", "size pattern cycled along the line, from L m s ('.' rests); empty = the rule's own"),
    P("shape_L", "choice", "disc", "shape of the large (and medium) dots: " + " | ".join(DOTS), choices=DOTS),
    P("shape_s", "choice", "disc", "shape of the small dots", choices=DOTS),
    P("line", "choice", "wire", "wire | none (ghost: dots only) | swell (the line also swells at its stresses)",
      choices=("wire", "none", "swell")),
    P("swell_profile", "choice", "drop", "line = swell: the profile", choices=PROFILES),
    P("swell_size", "float", 9.0, "line = swell: head diameter, mm", min=0.5, max=40.0),
    P("pen", "float", 0.4, "pen width mm", min=0.05, max=3.0),
    P("size", "float", 6.0, "large dot diameter, mm", min=0.5, max=30.0),
    P("medium", "float", 0.68, "medium dot / large", min=0.1, max=1.0),
    P("small", "float", 0.4, "small dot / large", min=0.05, max=1.0),
    P("gap", "float", 18.0, "minimum mm between dots (or groups) placed on events", min=0.0, max=500.0),
    P("scale", "float", 5.0, "inflection / turns: the scale the line is heard at, mm (big smooth hands: 6–12)",
      min=0.5, max=60.0),
    P("period", "float", 16.0, "beat: mm between beats", min=2.0, max=400.0),
    P("phrase", "float", 70.0, "decel / fullstop: shortest phrase, mm (hand switches end phrases first)",
      min=10.0, max=1000.0),
    P("space", "float", 7.0, "fullstop: pen-up gap after each full stop, mm", min=0.0, max=60.0),
    P("decel_n", "int", 6, "decel: dots per phrase end", min=2, max=14),
    P("decel_q", "float", 0.68, "decel: each gap is this times the previous (< 1: slowing down)", min=0.2, max=1.0),
    P("thr", "float", 0.15, "pauses: emphasis that counts as a pause", min=0.0, max=0.99),
    P("hole", "float", 0.45, "ring: hole radius / dot radius", min=0.1, max=0.85),
    P("pitch", "float", 0.85, "fill: spiral spacing in pens", min=0.4, max=4.0),
    P("wobble", "float", 0.05, "hand-made roundness irregularity", min=0.0, max=0.4),
], reach=_dots_reach, doc="dots placed by a rule you can see, in a small vocabulary of sizes and shapes")
def swell_dots(ctx, marks, *, rule, sizes, shape_L, shape_s, line, swell_profile, swell_size, pen, size, medium,
               small, gap, scale, period, phrase, space, decel_n, decel_q, thr, hole, pitch, wobble):
    prm = dict(rule=rule, sizes=sizes, gap=gap, scale=scale, period=period, phrase=phrase, decel_n=decel_n,
               decel_q=decel_q, thr=thr, size=size)
    frac = {"L": 1.0, "m": medium, "s": small}
    out = []
    for mi, m in enumerate(marks):
        if len(m) < 2:
            continue
        vid = m.meta.get("voice_id")
        rng = ctx.rng("dots", mi)
        plan, ends, q = dot_plan(m, prm)
        pts = np.asarray(q.points)
        s = q.arclength()
        tg = _tangents(pts)
        at = lambda x: (np.array([np.interp(x, s, pts[:, 0]), np.interp(x, s, pts[:, 1])]),  # noqa: E731
                        np.array([np.interp(x, s, tg[:, 0]), np.interp(x, s, tg[:, 1])]))
        wound_at = []
        for x, cls, g in plan:
            c, t = at(x)
            t = t / (np.linalg.norm(t) + 1e-12)
            d = size * frac[cls]
            shp = shape_L if cls in "Lm" else shape_s
            if shp == "wound" and line != "none":
                wound_at.append((x, c, t, d))
                continue
            for p, closed, filled in dot_shapes(shp, c, t, d, pen, pitch, rng, wobble, hole):
                out.append(Ink_(p, pen, {"voice": vid, "role": f"dot:{shp}:{cls}", "group": int(g)}, closed, filled))
        if line == "none":
            continue
        # the line: cut into phrases for fullstop; wound dots spliced in (contiguous)
        cuts = []
        if rule == "fullstop":
            for i, x in enumerate(ends[:-1]):
                cuts.append((x, min(x + space, s[-1])))
        segs, a = [], 0.0
        for x0, x1 in cuts:
            segs.append((a, x0))
            a = x1
        segs.append((a, float(s[-1])))
        for a, b in segs:
            if b - a < 0.5:
                continue
            sel = (s >= a) & (s <= b)
            path = pts[sel]
            # splice from the end backwards so earlier indices stay valid
            for x, c, t, d in sorted([w for w in wound_at if a <= w[0] <= b], key=lambda w: -w[0]):
                k = int(np.searchsorted(s[sel], x))
                path = np.vstack([path[:k], wound_path(c, t, 0.5 * d, pen, pitch, 0.0), path[k:]])
            out.append(Ink_(path, pen, {"voice": vid, "role": "line"}))
        if line == "swell":
            sprm = {**{p_.name: p_.default for p_ in SWELL_PARAMS}, "profile": swell_profile, "size": swell_size,
                    "pen": pen, "pitch": pitch}
            g, _ = swell_geometry(m, sprm)
            if g is not None:
                for p, closed, filled in line_fill(g, pen, pitch):
                    out.append(Ink_(p, pen, {"voice": vid, "role": f"swell:{swell_profile}"}, closed, filled))
    return out


# ---------------------------------------------------------------------------
# authored placement (bold gestures)
# ---------------------------------------------------------------------------

@arranger("swell_place", params=[
    P("boxes", "floats", [], "x0 y0 w h per part, as fractions of the (inset) frame; parts without a box fill it",
      min=-0.5, max=1.5),
    P("inks", "str", "black", "Flexoki ink per part (for colour previews), comma list, cycled"),
], doc="each part in its own authored box (may overlap): one bold gesture can fill a third of the sheet")
def swell_place(ctx, parts, *, boxes, inks):
    x0, y0, W, H = ctx.box
    out = []
    for i, p in enumerate(parts):
        b = boxes[4 * i:4 * i + 4]
        box = (x0 + b[0] * W, y0 + b[1] * H, max(b[2] * W, 1e-3), max(b[3] * H, 1e-3)) if len(b) == 4 else ctx.box
        out += p.run(box)
    return out


def part_inks(sheet) -> dict[int, str]:
    """Part → Flexoki ink name from a swell_place / dev_chorus recipe."""
    arr = sheet.recipe["arranger"]
    names = [x.strip() for x in str(arr.get("inks", "black")).split(",") if x.strip()] or ["black"]
    return {i: names[i % len(names)] for i in range(len(sheet.recipe["parts"]))}


