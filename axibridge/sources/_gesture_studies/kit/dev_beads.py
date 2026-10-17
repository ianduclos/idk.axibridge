# FROZEN from research commit 529a195: tools/gesture/gesture/kit/dev_beads.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Developments (round 10): beads, not sausages.

Ian on round 9 (results/round9-review-2026-10-17.md): field, Staccato timing
and pulse prosody kept; the segment / phrase / syncopated variants "too
sausagy" — a long stressed stretch inked as a mass becomes an elongated
capsule. Masses should be round beads and knots at ANY stress length.

`dev_beads` keeps the prosody timing (which stretches are stressed, how loud:
the `emphasis` channel, or (r − 1) where only a regime channel exists, e.g.
after `timing`) and changes only the SHAPE weight takes. Every shape stays
round however long the stretch is:

  string   a string of beads along the stretch, biggest mid-stretch
           (raised-cosine envelope), seed beads at its ends
  gather   ONE round mass at one point of the stretch (`at`): the stress
           event itself (start), the emphasis peak, the stretch end, or the
           lowest point on the sheet (ink runs downhill and pools)
  pool     the line swells into a round drop at the stretch end: a teardrop
           whose body is a disc (the tail is the line thickening into it)
  cluster  3–6 touching beads bunched around one point, unioned: a knotted,
           grape-like mass, round overall
  knot     the LINE itself ties a knot: at the stress it leaves its course,
           winds 2–7 small overlapping loops in place and goes on (line-built,
           contiguous, no fill)

Size grows with loudness and only weakly with stretch length
(d = size · peak^½ · clip((L/20)^length_gain, 0.7, 1.3)), so a 60 mm stress is
not a 60 mm capsule. Fills are line-built: concentric insets at `pitch`·pen
joined into one contiguous spiral, plus the outer ring (filled=True).

Base line (`line`): wire (the whole mark, dry), nib (the seed nib renderer
with r capped at `nib_cap` — stressed stretches show nib width under the beads, the
mass is replaced by the bead), or none (a GHOST voice: only its beads are
drawn; its line is never inked).
"""
from __future__ import annotations

import math

import numpy as np

from .core import Ink, P, renderer

SHAPES = ("string", "gather", "pool", "cluster", "knot")
AT = ("event", "peak", "end", "low")


# ---------------------------------------------------------------------------
# stresses as stretches
# ---------------------------------------------------------------------------

def bead_emphasis(mark) -> np.ndarray:
    """Emphasis 0..1: the prosody channel when present, else the mass part of
    the regime (r − 1), so `timing` / `field` / `own_tempo` drive beads too."""
    e = mark.channel("emphasis")
    if e is not None:
        return np.clip(e, 0.0, 1.0)
    return np.clip(np.asarray(mark["r"]) - 1.0, 0.0, 1.0)


def runs(e: np.ndarray, thr: float) -> list[tuple[int, int, float]]:
    on = e > thr
    if not on.any():
        return []
    d = np.diff(np.r_[0, on.astype(np.int8), 0])
    a, b = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1
    return [(int(i), int(j), float(e[i:j + 1].max())) for i, j in zip(a, b) if j >= i]


def _arcl(p):
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


def _at_s(p, s, x):
    return np.array([np.interp(x, s, p[:, 0]), np.interp(x, s, p[:, 1])])


def bead_diameter(size: float, peak: float, L: float, length_gain: float) -> float:
    return float(size * math.sqrt(max(peak, 0.0)) * np.clip((max(L, 1e-6) / 20.0) ** length_gain, 0.7, 1.3))


# ---------------------------------------------------------------------------
# round shapes, line-built
# ---------------------------------------------------------------------------

def blob(c, r: float, rng, wobble: float, n: int = 48) -> np.ndarray:
    """A hand-made round ring (closed): radius modulated by two low harmonics."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    k = 1.0
    for h in (2, 3):
        k = k + rng.normal(0.0, wobble) * np.cos(h * t + rng.uniform(0, 2 * np.pi))
    ring = np.column_stack([c[0] + r * k * np.cos(t), c[1] + r * k * np.sin(t)])
    return np.vstack([ring, ring[:1]])


def solid(poly, pen: float, pitch: float) -> list[tuple[np.ndarray, bool, bool]]:
    """A polygon inked line-built: its outer ring (closed, filled) + ONE spiral
    path through concentric insets (open). → [(points, closed, filled)]."""
    from shapely.geometry import Polygon  # noqa: PLC0415
    g = poly if not isinstance(poly, np.ndarray) else Polygon(poly)
    if g.is_empty:
        return []
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda q: q.area)
    g = g.buffer(-0.5 * pen, quad_segs=8)            # ink stays inside the shape
    if g.is_empty:
        return []
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda q: q.area)
    rings = []
    cur = g
    step = max(pitch * pen, 0.05)
    while not cur.is_empty and cur.area > 0.05 * step * step:
        if cur.geom_type == "MultiPolygon":
            cur = max(cur.geoms, key=lambda q: q.area)
        rings.append(np.asarray(cur.exterior.coords))
        cur = cur.buffer(-step, quad_segs=8)
    if not rings:
        return []
    out = [(rings[0], True, True)]
    if len(rings) > 1:
        path, here = [], rings[0][0]
        for r in rings[1:]:
            body = r[:-1]
            k = int(np.argmin(np.linalg.norm(body - here, axis=1)))
            body = np.roll(body, -k, axis=0)
            r2 = np.vstack([body, body[:1]])
            path.append(r2)
            here = r2[-1]
        out.append((np.vstack(path), False, False))
    else:
        # a bead smaller than two pitches: a single dot stroke at the centre
        c = np.asarray(g.centroid.coords[0])
        out.append((np.vstack([c, c + 1e-3]), False, False))
    return out


def knot_path(c, tangent, r: float, loops: int, rng, wobble: float) -> np.ndarray:
    """`loops` small overlapping loops wound in place around c, entering and
    leaving along `tangent` — a knot tied in the line."""
    t = tangent / (np.linalg.norm(tangent) + 1e-12)
    nv = np.array([-t[1], t[0]])
    side = 1.0 if rng.random() < 0.5 else -1.0
    th = np.linspace(0, 2 * np.pi * loops, 40 * loops)
    # every loop its own radius; the loop centre random-walks inside a small disc → a tangled,
    # round knot rather than a coil spring of equal rings
    per = rng.uniform(0.55, 1.0, loops + 1)
    rr = r * np.interp(th / (2 * np.pi), np.arange(loops + 1), per)
    walk = rng.normal(0.0, 0.45 * r, (loops + 1, 2))
    walk -= walk[0]
    cx = np.interp(th / (2 * np.pi), np.arange(loops + 1), walk[:, 0])
    cy = np.interp(th / (2 * np.pi), np.arange(loops + 1), walk[:, 1])
    rr = rr * (1 + wobble * np.sin(3 * th + rng.uniform(0, 6.3)))
    x = cx + rr * np.sin(th)
    y = cy + side * rr * (1 - np.cos(th))
    q = np.column_stack([x, y])
    return c + np.outer(q[:, 0], t) + np.outer(q[:, 1], nv)


# ---------------------------------------------------------------------------
# the renderer
# ---------------------------------------------------------------------------

def _reach(p):
    return 0.5 * p["size"] * 1.3 * (1.6 if p["shape"] == "cluster" else 1.0) + 0.5 * p["pen"] + 0.5


@renderer("dev_beads", params=[
    P("shape", "choice", "gather", "string | gather (one mass) | pool (teardrop at the end) | cluster "
      "(touching beads, a knot of grapes) | knot (the line ties loops)", choices=SHAPES),
    P("at", "choice", "peak", "gather/cluster: where the mass sits — event (stretch start) | peak | end | "
      "low (lowest point on the sheet: ink pools downhill)", choices=AT),
    P("line", "choice", "wire", "base line: wire | nib (r capped at 1) | none (ghost: beads only)",
      choices=("wire", "nib", "none")),
    P("nib_style", "choice", "e", "nib style when line = nib", choices=("a", "b+", "c", "e", "c+e")),
    P("nib_cap", "float", 0.5, "line = nib: r is capped here (1 = full nib width along the stress, which "
      "reads as a bar again; 0.5 keeps the stretch a swelling line)", min=0.0, max=1.0),
    P("pen", "float", 0.4, "pen width mm", min=0.05, max=3.0),
    P("thr", "float", 0.15, "emphasis above which a stretch earns weight", min=0.0, max=0.99),
    P("size", "float", 7.0, "bead diameter at a loud stress, mm", min=0.5, max=30.0),
    P("length_gain", "float", 0.25, "how much a longer stretch grows its bead (0 = never)", min=0.0, max=1.0),
    P("spacing", "float", 1.5, "string: centre spacing in bead diameters", min=0.6, max=6.0),
    P("pitch", "float", 0.85, "fill: inset spacing in pens (< 1 reads solid)", min=0.4, max=4.0),
    P("wobble", "float", 0.06, "hand-made roundness irregularity", min=0.0, max=0.4),
    P("loops", "int", 4, "knot: loops at a loud stress", min=1, max=12),
], reach=_reach, doc="weight as round beads / knots on the prosody stresses: never an elongated capsule")
def dev_beads(ctx, marks, *, shape, at, line, nib_style, nib_cap, pen, thr, size, length_gain, spacing, pitch, wobble,
              loops):
    from shapely.geometry import Point  # noqa: PLC0415
    from shapely.ops import unary_union  # noqa: PLC0415
    out: list[Ink] = []
    base_marks = []
    for mi, m in enumerate(marks):
        if len(m) < 2:
            continue
        vid = m.meta.get("voice_id")
        pts = np.asarray(m.points)
        s = _arcl(pts)
        e = bead_emphasis(m)
        rng = ctx.rng("beads", mi)
        rs = runs(e, thr)
        if shape == "knot":
            # the line itself is rewritten: knots inserted at each stress
            pieces, cur = [], 0
            for ri, (i0, i1, peak) in enumerate(rs):
                j = int(np.argmax(e[i0:i1 + 1])) + i0 if at == "peak" else i0 if at == "event" else i1
                if at == "low":
                    j = i0 + int(np.argmax(pts[i0:i1 + 1, 1]))
                if j <= cur:
                    continue
                pieces.append(pts[cur:j + 1])
                tg = pts[min(j + 1, len(pts) - 1)] - pts[max(j - 1, 0)]
                L = s[i1] - s[i0]
                d = bead_diameter(size, peak, L, length_gain)
                n = max(1, int(round(loops * math.sqrt(peak))))
                pieces.append(knot_path(pts[j], tg, 0.5 * d, n, rng, wobble))
                cur = j
            pieces.append(pts[cur:])
            path = np.vstack([p for p in pieces if len(p)])
            if line != "none":
                out.append(Ink(path, pen=pen, meta={"voice": vid, "role": "line+knots"}))
            continue
        if line == "wire":
            out.append(Ink(pts, pen=pen, meta={"voice": vid, "role": "line"}))
        elif line == "nib":
            base_marks.append(m.evolve(channels={"r": np.minimum(np.asarray(m["r"]), nib_cap)}))
        for ri, (i0, i1, peak) in enumerate(rs):
            L = float(s[i1] - s[i0])
            d = bead_diameter(size, peak, L, length_gain)
            seg = pts[i0:i1 + 1]
            shapes = []
            if shape == "string":
                nb = max(1, int(L // (spacing * d)) + 1)
                xs = [s[i0] + 0.5 * L] if nb == 1 else np.linspace(s[i0], s[i1], nb)
                for x in xs:
                    u = (x - s[i0]) / max(L, 1e-9)
                    env = 0.35 + 0.65 * math.sin(math.pi * u) if nb > 1 else 1.0
                    shapes.append(blob(_at_s(pts, s, x), 0.5 * d * env, rng, wobble))
            elif shape in ("gather", "cluster"):
                j = {"event": i0, "end": i1, "peak": i0 + int(np.argmax(e[i0:i1 + 1])),
                     "low": i0 + int(np.argmax(seg[:, 1]))}[at]
                c = pts[j]
                if shape == "gather":
                    shapes.append(blob(c, 0.5 * d, rng, wobble))
                else:
                    k = int(np.clip(round(3 + 3 * peak * min(1.0, L / 30.0)), 3, 6))
                    rad = 0.5 * d * np.sort(rng.uniform(0.45, 0.8, k))[::-1]
                    cs = [c]
                    for q in range(1, k):
                        a = rng.uniform(0, 2 * np.pi)
                        par = cs[int(rng.integers(0, len(cs)))]
                        dist = 0.8 * (rad[q] + rad[0] * 0.6)
                        cs.append(par + dist * np.array([math.cos(a), math.sin(a)]))
                    cs = np.asarray(cs)
                    cs = cs - (cs.mean(0) - c) * 0.6         # stay round about the stress point
                    shapes += [blob(cc, rr, rng, wobble) for cc, rr in zip(cs, rad)]
            elif shape == "pool":
                tail = min(L, 1.4 * d)
                x1 = s[i1]
                xs = np.linspace(x1 - tail, x1, 16)
                g = [Point(*_at_s(pts, s, x)).buffer(max(0.5 * pen, 0.5 * d * ((k / 15.0) ** 2.2)), quad_segs=8)
                     for k, x in enumerate(xs)]
                hulls = [unary_union([a, b]).convex_hull for a, b in zip(g[:-1], g[1:])]
                drop = unary_union(hulls + [Point(*_at_s(pts, s, x1)).buffer(0.5 * d, quad_segs=16)])
                shapes.append(drop)
            geom = unary_union([_poly(sh) for sh in shapes])
            polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
            for pg in polys:
                for p_, closed, filled in solid(pg, pen, pitch):
                    out.append(Ink(p_, closed=closed, filled=filled, pen=pen,
                                   meta={"voice": vid, "role": f"bead:{shape}", "stretch": ri}))
    if base_marks:
        from .renderers_base import nib  # noqa: PLC0415
        out = nib(ctx, base_marks, style=nib_style, pen=pen) + out
    return out


def _poly(sh):
    from shapely.geometry import Polygon  # noqa: PLC0415
    if isinstance(sh, np.ndarray):
        return Polygon(sh).buffer(0)
    return sh
