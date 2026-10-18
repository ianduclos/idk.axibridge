# FROZEN from research commit efce219: tools/gesture/gesture/signs.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Sign-like shapes and how they relate to lines (research; see
results/signs-2026-10-16.md and docs/IDEAS-gesture-bank.md, "Direction:
three regimes that become one another in space").

Small forms — beads, an eye holding a dot, a lozenge at a nib's end, a
line swelling into a vessel, hooks, commas, a knot that fills in — read as
marks *belonging to* lines when they keep a relation to them. This module
has three parts:

1. **Vocabulary** (`vocabulary`, `make_sign`). Every sign is generated from
   parameters, never from letterforms or faces. Geometry is in units of the
   host line width `w` (so signs scale with the line), in a LOCAL frame:
   anchor at the origin, +x = the host tangent (for a terminal: the
   outward tangent at the line end; the sign starts at x = 0 and grows
   along +x). Filled parts are shapely polygons; plotter paths come from
   `broadnib.outline_paths` / `concentric_paths` (outline or concentric
   insets at pen spacing — never hatching). Monoline parts (an eye's loop, a
   tick) are open/closed polylines drawn with the line's own pen.

2. **Placement grammar** (`PlacementGrammar`, `learn_grammar`,
   `place_signs`, `place_random`). Five relations, measured on Ian's
   reference image and on secular calligraphy:
     terminal  — attached at a free line end (lozenge, drop, vessel, hook,
                 pendant block, tick);
     interior  — attached inside a line (bead, string of beads, knot);
     enclosed  — inside a loop of the line network (dot in a loop = eye);
     adjacent  — beside a line at a gap, like a diacritic (nuqta, stacked
                 dots, crescent, comma, small eye, ring, ticks);
     free      — floating, away from lines.
   The adjacent relation (gap normal to the line, side, along-line
   position, size, axis angle relative to the baseline, clustering) is
   learned from dot geometry in calligraphy sheets whose content_type is
   exercise / poetry / document ONLY: `learn_grammar` runs every source id
   through `calligraphy.require_generative` and raises `PolicyError` for
   anything else (Qur'anic, devotional, album, manuscript, unverified).
   Font dot glyphs contribute dot SHAPE statistics only (aspect, corner
   angle), never placement.

3. **Measurement** (`ink_components`, `inventory`, `measure_dots`): connected
   components of an ink mask, split into thick masses and thin ink, with
   their relation to the lines around them.

4. **Line events** (`plan_events`, `apply_events`, `place_events`,
   `render_events`; results/signs-events-2026-10-16.md). Replaces stamping:
   the grammar picks WHERE on the line network (end / interior / loop /
   junction / corner, arc position, side) and WHICH `gesture.regime`
   operator turns that part of the line into the sign; clusters grow
   responsively along a line. Output is RegimeStrokes (the edited lines +
   children grown from them); only rare detached dots leave the line.

Pure and deterministic: randomness only through the `rng` argument; inputs
are never mutated. Coordinates follow the README contract (pixels, y down).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy import ndimage as ndi
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import polygonize, unary_union

from . import broadnib

__all__ = ["EventGrammar", "LineEvent", "learn_event_grammar", "plan_events", "apply_events", "place_events",
           "render_events", "DEFAULT_EVENT_GRAMMAR", "EVENT_OPS", "EVENT_SITES", "REFERENCE_EVENTS",
           "vocabulary", "make_sign", "Sign", "PlacedSign", "PlacementGrammar", "DEFAULT_GRAMMAR",
           "learn_grammar", "place_signs", "place_random", "sign_paths", "ink_components",
           "inventory", "measure_dots", "RELATIONS"]

RELATIONS = ("terminal", "interior", "enclosed", "adjacent", "free")


# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

# parameter ranges, all lengths in host line widths w. Ranges were set from
# the reference inventory (size of small masses / w) and the calligraphy dot
# statistics (lozenge size, aspect); see results/signs-2026-10-16.md §3.
_VOCAB: dict[str, dict] = {
    "lozenge": {"relations": ("adjacent", "terminal", "enclosed"),
                "doc": "rhombic nuqta-like dot, long diagonal at a nib angle",
                "params": {"size": (2.2, 4.2), "aspect": (0.55, 0.95), "skew": (-0.25, 0.25),
                           "round": (0.05, 0.3), "nib": (-0.6, 0.6)}},
    "drop": {"relations": ("terminal", "adjacent", "free"),
             "doc": "teardrop: round body tapering into a short point",
             "params": {"size": (2.5, 5.5), "tail": (1.2, 2.6), "bend": (-0.6, 0.6)}},
    "comma": {"relations": ("adjacent", "terminal"),
              "doc": "comma / hook: heavy head, tail curling with rising curvature",
              "params": {"size": (2.5, 5.0), "tail": (2.5, 5.5), "curl": (0.6, 1.8)}},
    "bead": {"relations": ("interior",),
             "doc": "lens-shaped swelling threaded on the line",
             "params": {"size": (1.8, 3.4), "length": (2.5, 5.0), "count": (1, 4), "spacing": (4.0, 8.0)}},
    "eye": {"relations": ("adjacent", "free"),
            "doc": "almond/irregular closed loop holding an off-centre dot",
            "params": {"length": (5.0, 10.0), "height": (0.45, 0.8), "dot": (0.7, 1.4),
                       "dot_dx": (-0.3, 0.3), "wobble": (0.0, 0.12)}},
    "vessel": {"relations": ("terminal",),
               "doc": "the line swells into a goblet/bulb with a concave rim",
               "params": {"length": (6.0, 14.0), "belly": (2.0, 4.5), "neck": (0.3, 0.55),
                          "rim": (0.0, 0.5)}},
    "knot": {"relations": ("interior", "free"),
             "doc": "a small curl of the line whose loop fills in",
             "params": {"size": (3.0, 7.0), "loop": (1.4, 2.4), "fill": (0.5, 1.0)}},
    "crescent": {"relations": ("adjacent",),
                 "doc": "crescent cupped toward or away from its line",
                 "params": {"size": (4.0, 8.0), "thick": (0.3, 0.55), "cup": (-1.0, 1.0)}},
    "stack": {"relations": ("adjacent",),
              "doc": "two or three small lozenges in a cluster (pair or triangle)",
              "params": {"count": (2, 3), "size": (1.4, 2.4), "spacing": (1.6, 2.6)}},
    "tick": {"relations": ("terminal", "adjacent"),
             "doc": "one to three short parallel strokes (notch at a line end, or a small comb)",
             "params": {"count": (1, 3), "length": (2.0, 4.5), "spacing": (1.2, 2.0),
                        "angle": (0.9, 2.2)}},
    "pendant": {"relations": ("terminal",),
                "doc": "irregular rounded block hanging from a line end",
                "params": {"size": (4.0, 10.0), "irregular": (0.05, 0.18), "round": (0.15, 0.45),
                           "turn": (-0.4, 0.4)}},
    "ring": {"relations": ("adjacent", "free"),
             "doc": "small open or closed monoline ring",
             "params": {"size": (4.0, 9.0), "aspect": (0.6, 1.0), "gap": (0.0, 0.9)}},
}


def vocabulary() -> dict[str, dict]:
    """kind → {relations, doc, params: {name: (lo, hi)}} (lengths in line
    widths). A copy: callers may mutate it freely."""
    return {k: {"relations": tuple(v["relations"]), "doc": v["doc"], "params": dict(v["params"])}
            for k, v in _VOCAB.items()}


@dataclass
class Sign:
    """A sign in its LOCAL frame (anchor (0, 0), +x = host tangent), already
    scaled by w. `fill` = filled region (shapely, may be None); `lines` =
    monoline polylines; `closed_lines` flags them."""
    kind: str
    fill: object | None
    lines: list[np.ndarray] = field(default_factory=list)
    closed_lines: list[bool] = field(default_factory=list)
    w: float = 1.0
    params: dict = field(default_factory=dict)
    spine: list = field(default_factory=list)   # [(centre (N, 2), radii (N,))]: swelling parts

    @property
    def scale(self) -> float:
        """Characteristic size (max bbox side) in absolute units."""
        b = self.bounds()
        return float(max(b[2] - b[0], b[3] - b[1]))

    def bounds(self):
        geoms = [] if self.fill is None else [self.fill]
        geoms += [LineString(np.vstack([p, p[:1]]) if c else p) for p, c in zip(self.lines, self.closed_lines)
                  if len(p) >= 2]
        return unary_union(geoms).bounds if geoms else (0.0, 0.0, 0.0, 0.0)

    def footprint(self, pad: float = 0.0):
        geoms = [] if self.fill is None else [self.fill]
        geoms += [LineString(np.vstack([p, p[:1]]) if c else p).buffer(self.w / 2)
                  for p, c in zip(self.lines, self.closed_lines) if len(p) >= 2]
        g = unary_union(geoms)
        return g.buffer(pad) if pad > 0 else g


def _rng_u(rng, lo, hi):
    return float(rng.uniform(lo, hi))


def _p(kind: str, rng, p: dict, name: str):
    """Parameter: explicit value in p, else uniform over the vocabulary range
    (integer ranges draw integers)."""
    if name in p and p[name] is not None:
        return p[name]
    lo, hi = _VOCAB[kind]["params"][name]
    if isinstance(lo, int) and isinstance(hi, int):
        return int(rng.integers(lo, hi + 1))
    return _rng_u(rng, lo, hi)


def _tube(centre: np.ndarray, radii: np.ndarray):
    """Union of convex hulls of consecutive discs along a centreline: a
    swelling/tapering ribbon with round ends (radii ≥ 0)."""
    parts = []
    for i in range(len(centre) - 1):
        a = Point(centre[i]).buffer(max(radii[i], 1e-3), 16)
        b = Point(centre[i + 1]).buffer(max(radii[i + 1], 1e-3), 16)
        parts.append(unary_union([a, b]).convex_hull)
    return unary_union(parts)


def _curve(length: float, k0: float, k1: float, n: int = 40, heading: float = 0.0, start=(0.0, 0.0)):
    """Clothoid-ish centreline: curvature linear from k0 to k1 over length."""
    s = np.linspace(0, length, n)
    kap = k0 + (k1 - k0) * s / max(length, 1e-9)
    th = heading + np.concatenate([[0.0], np.cumsum(0.5 * (kap[1:] + kap[:-1]) * np.diff(s))])
    ds = np.diff(s)
    x = np.concatenate([[0.0], np.cumsum(np.cos(th[:-1]) * ds)]) + start[0]
    y = np.concatenate([[0.0], np.cumsum(np.sin(th[:-1]) * ds)]) + start[1]
    return np.column_stack([x, y])


def _lozenge_poly(size, aspect, skew, rnd):
    a, b = size / 2.0, aspect * size / 2.0
    pts = np.array([[a, 0.0], [skew * a, b], [-a, 0.0], [skew * a, -b]])
    g = Polygon(pts)
    r = rnd * b
    if r > 0:
        g = g.buffer(-r, join_style="round").buffer(r, join_style="round")
    return g


def make_sign(kind: str, rng: np.random.Generator, *, w: float = 1.0, **p) -> Sign:
    """One sign of `kind` (see `vocabulary`) with parameters drawn from the
    vocabulary ranges unless given. Lengths scale with the line width `w`."""
    if kind not in _VOCAB:
        raise ValueError(f"unknown sign kind {kind!r}")
    fill = None
    lines: list[np.ndarray] = []
    closed: list[bool] = []
    spine: list = []
    used: dict = {}

    def P(name):
        used[name] = _p(kind, rng, p, name)
        return used[name]

    if kind == "lozenge":
        size, aspect, skew, rnd, nib = P("size"), P("aspect"), P("skew"), P("round"), P("nib")
        g = _lozenge_poly(size, aspect, skew, rnd)
        fill = affinity.rotate(g, nib, origin=(0, 0), use_radians=True)
    elif kind == "drop":
        size, tail, bend = P("size"), P("tail"), P("bend")
        r = size / 2
        c = _curve(r + tail * r, 0.0, bend / max(r, 1e-9), n=30)
        t = np.linspace(0, 1, len(c))
        radii = r * np.where(t < 0.35, np.sqrt(np.clip(1 - ((0.35 - t) / 0.35) ** 2, 0, 1)) * 0.25 + 0.75,
                             np.clip(1 - (t - 0.35) / 0.65, 0, 1) ** 1.3)
        radii = np.maximum(radii, 0.06)
        fill = _tube(c, radii)
        spine.append((c, radii))
    elif kind == "comma":
        size, tail, curl = P("size"), P("tail"), P("curl")
        r = size / 2
        L = tail * r
        c = _curve(L, 0.1 / r, curl * 2.0 / L * math.pi / 2, n=40)
        t = np.linspace(0, 1, len(c))
        radii = r * np.clip(1.0 - t, 0.0, 1.0) ** 1.6 + 0.12
        radii[0] = r
        fill = _tube(c, radii)
        spine.append((c, radii))
    elif kind == "bead":
        size, length, count, spacing = P("size"), P("length"), P("count"), P("spacing")
        parts = []
        for i in range(int(count)):
            x0 = (i - (count - 1) / 2) * spacing * size / 2.6
            c = np.column_stack([np.linspace(x0 - length / 2, x0 + length / 2, 21), np.zeros(21)])
            t = np.linspace(0, 1, 21)
            prof = np.sin(np.pi * t) ** 0.8
            asym = 1 + 0.25 * (rng.random() - 0.5) * (t - 0.5)
            rr = np.maximum(prof * asym * size / 2, 0.5)
            parts.append(_tube(c, rr))
            spine.append((c, rr))
        fill = unary_union(parts)
    elif kind == "eye":
        L, hh, dot, dx, wob = P("length"), P("height"), P("dot"), P("dot_dx"), P("wobble")
        n = 64
        tt = np.linspace(0, 2 * np.pi, n, endpoint=False)
        # almond: |sin|^0.7 vertical profile, slightly pointed at one end
        x = (L / 2) * np.cos(tt)
        y = (hh * L / 2) * np.sign(np.sin(tt)) * np.abs(np.sin(tt)) ** 0.75 * (1 - 0.18 * np.cos(tt))
        noise = 1 + wob * np.sin(3 * tt + rng.uniform(0, 2 * np.pi))
        loop = np.column_stack([x * noise, y * noise])
        lines.append(loop)
        closed.append(True)
        fill = Point(dx * L / 2, rng.uniform(-0.15, 0.15) * hh * L / 2).buffer(dot, 20)
    elif kind == "vessel":
        L, belly, neck, rim = P("length"), P("belly"), P("neck"), P("rim")
        c = np.column_stack([np.linspace(0, L, 40), np.zeros(40)])
        t = np.linspace(0, 1, 40)
        # neck at the line width, swelling to the belly, then closing at the rim
        swell = np.clip((t - neck) / (1 - neck), 0, 1)
        radii = 0.5 + (belly - 0.5) * np.sin(np.pi * np.clip(swell * 0.85, 0, 1)) ** 1.2
        g = _tube(c, radii)
        if rim > 0.05:          # a concave rim: bite a disc out of the end
            g = g.difference(Point(L + belly * (0.55 - 0.35 * rim), 0).buffer(belly * 0.6, 24))
        else:
            spine.append((c, radii))
        fill = g
    elif kind == "knot":
        size, loop, fl = P("size"), P("loop"), P("fill")
        lam = loop
        tt = np.linspace(-1.05 * np.pi, 1.05 * np.pi, 120)     # one loop, centred
        x = (tt - lam * np.sin(tt)) * size / (2 * np.pi)
        y = (-lam * np.cos(tt) + lam) * size / (2 * np.pi) * 0.9
        cur = np.column_stack([x - x[0], y - y[0]])
        cur[:, 0] -= (cur[-1, 0]) / 2
        lines.append(cur)
        closed.append(False)
        faces = list(polygonize(unary_union(LineString(cur))))
        if faces:
            face = max(faces, key=lambda f: f.area)
            if fl >= 0.99:
                fill = face
            else:       # partially filled: the part of the loop beyond a chord
                minx, miny, maxx, maxy = face.bounds
                cut = miny + (maxy - miny) * (1 - fl)
                fill = face.intersection(Polygon([(minx - 1, cut), (maxx + 1, cut), (maxx + 1, maxy + 1),
                                                  (minx - 1, maxy + 1)]))
                if fill.is_empty:
                    fill = None
    elif kind == "crescent":
        size, thick, cup = P("size"), P("thick"), P("cup")
        R = size / 2
        d = Point(0, 0).buffer(R, 32)
        bite = Point(0, -np.sign(cup if cup != 0 else 1) * R * thick * 1.6).buffer(R * 0.95, 32)
        g = d.difference(bite)
        fill = affinity.scale(g, 1.0, 0.75 + 0.25 * abs(cup), origin=(0, 0))
    elif kind == "stack":
        count, size, spacing = P("count"), P("size"), P("spacing")
        arr = p.get("arrangement") or ("pair" if count == 2 else str(rng.choice(["triangle", "row"],
                                                                                 p=[0.75, 0.25])))
        used["arrangement"] = arr
        sp = spacing * size / 2
        if count == 2:
            ang = p.get("pair_angle", 0.0) or 0.0
            offs = [np.array([-sp / 2, 0]), np.array([sp / 2, 0])]
            offs = [np.array([o[0] * math.cos(ang), o[0] * math.sin(ang)]) for o in offs]
        elif arr == "triangle":
            offs = [np.array([-sp / 2, sp * 0.3]), np.array([sp / 2, sp * 0.3]), np.array([0, -sp * 0.55])]
        else:
            offs = [np.array([(i - 1) * sp, 0.0]) for i in range(3)]
        nib = p.get("nib", rng.uniform(-0.6, 0.6))
        used["nib"] = nib
        parts = []
        for o in offs:
            g = _lozenge_poly(size * rng.uniform(0.9, 1.1), rng.uniform(0.6, 0.85), rng.uniform(-0.2, 0.2), 0.15)
            parts.append(affinity.translate(affinity.rotate(g, nib, origin=(0, 0), use_radians=True), *o))
        fill = unary_union(parts)
    elif kind == "tick":
        count, length, spacing, ang = P("count"), P("length"), P("spacing"), P("angle")
        d = np.array([math.cos(ang), math.sin(ang)])
        for i in range(int(count)):
            base = np.array([0.6 + i * spacing, 0.0])
            ll = length * rng.uniform(0.8, 1.1)
            seg = np.array([base - d * ll * 0.15, base + d * ll * 0.85])
            lines.append(seg)
            closed.append(False)
    elif kind == "pendant":
        size, irr, rnd, turn = P("size"), P("irregular"), P("round"), P("turn")
        h = size / 2
        corners = np.array([[0, -h], [size, -h], [size, h], [0, h]], float)
        corners += rng.normal(0, irr * size, corners.shape)
        g = Polygon(corners)
        if not g.is_valid:
            g = g.buffer(0)
        r = rnd * h
        g = g.buffer(-r, join_style="round").buffer(r, join_style="round")
        g = affinity.rotate(g, turn, origin=(0, 0), use_radians=True)
        stem = LineString([(-0.2, 0), (1.2, 0)]).buffer(0.5)
        fill = unary_union([affinity.translate(g, xoff=0.8), stem])
    elif kind == "ring":
        size, aspect, gap = P("size"), P("aspect"), P("gap")
        tt = np.linspace(gap / 2, 2 * np.pi - gap / 2, 60)
        ring = np.column_stack([size / 2 * np.cos(tt), aspect * size / 2 * np.sin(tt)])
        lines.append(ring)
        closed.append(gap < 0.05)
    # scale to the line width
    if fill is not None:
        fill = affinity.scale(fill, w, w, origin=(0, 0))
        if fill.is_empty:
            fill = None
    lines = [np.asarray(q, float) * w for q in lines]
    spine = [(np.asarray(c, float) * w, np.asarray(r, float) * w) for c, r in spine]
    return Sign(kind=kind, fill=fill, lines=lines, closed_lines=closed, w=float(w), params=used, spine=spine)


def _xf_geom(g, angle, xy):
    if g is None:
        return None
    return affinity.translate(affinity.rotate(g, angle, origin=(0, 0), use_radians=True), *xy)


def _xf_pts(p, angle, xy):
    c, s = math.cos(angle), math.sin(angle)
    return p @ np.array([[c, s], [-s, c]]) + np.asarray(xy, float)


def sign_paths(sign: "Sign | PlacedSign", *, pen: float | None = None, mode: str = "fill",
               engine: str = "regime") -> tuple[list, list]:
    """Plotter paths of a sign: (paths, closed flags). Filled parts become
    concentric insets at pen spacing (mode "fill", pen defaults to w) or
    their outline only (mode "outline"); monoline parts pass through.
    engine="regime" (default): swelling kinds (drop, comma, bead, vessel
    without a rim) are rendered as regime.RegimeStroke masses (r = 2,
    mass = local diameter) with regime.render, when gesture/regime.py is
    importable; engine="own" always uses this module's insets."""
    fill = sign.fill
    pen = sign.w if pen is None else pen
    paths, closed = [], []
    spine = getattr(sign, "spine", None)
    if spine and mode == "fill" and engine == "regime":
        try:
            from . import regime
        except ImportError:        # regime.py absent: own concentric insets
            regime = None
        if regime is not None:
            # swelling parts as regime-2 (mass) strokes: direction-free
            # width = mass, filled by regime.render's concentric insets
            sts = [regime.make(c, r=2.0, W=1e-3 * pen, mass=np.maximum(2 * rad, pen)) for c, rad in spine]
            ps = regime.render(sts, pen=pen)
            paths += ps
            closed += [False] * len(ps)        # regime closes contours by repeating point 0
            paths += [np.asarray(q, float) for q in sign.lines]
            closed += list(sign.closed_lines)
            return paths, closed
    if fill is not None and not fill.is_empty:
        ps = broadnib.concentric_paths(fill, pen) if mode == "fill" else broadnib.outline_paths(fill)
        paths += ps
        closed += [True] * len(ps)
    paths += [np.asarray(q, float) for q in sign.lines]
    closed += list(sign.closed_lines)
    return paths, closed


# ---------------------------------------------------------------------------
# placement grammar
# ---------------------------------------------------------------------------

@dataclass
class PlacementGrammar:
    """How signs sit relative to lines. Distances in line widths w; angles
    in radians. Learned fields are lists of samples (non-parametric: drawn
    with replacement + a little jitter)."""
    relation_p: dict = field(default_factory=dict)          # relation → probability
    kind_p: dict = field(default_factory=dict)              # relation → {kind: p}
    density: float = 0.0          # signs per line width of line length
    gap_w: list = field(default_factory=list)               # adjacent: clear gap to the line / w
    side_up: float = 0.5          # adjacent: P(sign on the page-up side of a near-horizontal line)
    along_u: list = field(default_factory=list)             # adjacent: position along host, 0..1
    size_w: list = field(default_factory=list)              # adjacent dot size (equiv. diameter) / w
    axis_rel: list = field(default_factory=list)            # dot long axis vs local baseline (rad, ±π/2)
    cluster_p: dict = field(default_factory=dict)           # "1"/"2"/"3" → p
    pair_angle: list = field(default_factory=list)          # pair axis vs baseline (rad, folded 0..π/2)
    pair_spacing_w: list = field(default_factory=list)      # pair centre spacing / dot size
    mass_size_w: dict = field(default_factory=dict)         # relation → list of size/w (reference)
    end_share: float = 0.5        # reference: attached masses at line ends / all attached
    sources: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_json(d: dict) -> "PlacementGrammar":
        return PlacementGrammar(**d)

    def sample(self, name: str, rng, default: float, jitter: float = 0.08) -> float:
        xs = getattr(self, name)
        if not xs:
            return float(default)
        v = float(xs[int(rng.integers(len(xs)))])
        return v * (1 + jitter * rng.normal()) if jitter else v


def _norm(d: dict) -> dict:
    s = float(sum(d.values()))
    return {k: v / s for k, v in d.items()} if s > 0 else dict(d)


# kind given relation: a DESIGN prior, informed by the reference reading
# (which forms occur where) — not learned. Counts behind it: §1 of the
# results note.
KIND_GIVEN_RELATION = {
    "terminal": {"lozenge": 0.18, "drop": 0.18, "vessel": 0.18, "comma": 0.12, "pendant": 0.12, "tick": 0.12,
                 "knot": 0.0},
    "interior": {"bead": 0.65, "knot": 0.35},
    "enclosed": {"lozenge": 0.6, "drop": 0.4},
    "adjacent": {"lozenge": 0.30, "stack": 0.2, "comma": 0.12, "crescent": 0.1, "eye": 0.1, "ring": 0.1,
                 "tick": 0.08},
    "free": {"eye": 0.3, "ring": 0.25, "knot": 0.25, "drop": 0.2},
}


def learn_grammar(dot_records: list[dict], *, reference: dict | None = None,
                  shape_records: list[dict] | None = None, manifest: dict | None = None) -> PlacementGrammar:
    """Placement grammar from calligraphy dot records (`measure_dots`) and
    the reference inventory (`inventory`).

    POLICY GATE: every distinct `source` of `dot_records` must pass
    `calligraphy.require_generative` (exercise / poetry / document,
    nothing flagged) — otherwise PolicyError, before anything is learned.
    `shape_records` (font dot glyphs or allowed sheets) only set the
    lozenge shape statistics in meta, never placement."""
    from . import calligraphy as cg

    srcs = sorted({r["source"] for r in dot_records})
    cg.require_generative(srcs, manifest)
    adj = [r for r in dot_records if r.get("host_gap_w") is not None]
    g = PlacementGrammar()
    g.sources = srcs
    g.gap_w = [round(float(r["host_gap_w"]), 4) for r in adj]
    up = [r["side_up"] for r in adj if r.get("side_up") is not None]
    g.side_up = float(np.mean(up)) if up else 0.5
    g.along_u = [round(float(r["along_u"]), 4) for r in adj if r.get("along_u") is not None]
    g.size_w = [round(float(r["size_w"]), 4) for r in adj]
    g.axis_rel = [round(float(r["axis_rel"]), 4) for r in adj if r.get("axis_rel") is not None
                  and r.get("aspect", 1) < 0.85]
    cl = [int(r.get("cluster", 1)) for r in adj if r.get("cluster_lead", True)]
    cnt = {str(k): cl.count(k) for k in (1, 2, 3)}
    g.cluster_p = _norm({k: float(v) for k, v in cnt.items()})
    g.pair_angle = [round(float(r["pair_angle"]), 4) for r in adj if r.get("pair_angle") is not None]
    g.pair_spacing_w = [round(float(r["pair_spacing"]), 4) for r in adj if r.get("pair_spacing") is not None]
    if reference:
        rel = reference.get("relation_counts", {})
        g.relation_p = _norm({k: float(rel.get(k, 0)) + 0.5 for k in RELATIONS})
        g.density = float(reference.get("signs_per_w", 0.0))
        g.mass_size_w = {k: list(v) for k, v in reference.get("size_w_by_relation", {}).items()}
        g.end_share = float(reference.get("end_share", 0.5))
    else:
        g.relation_p = _norm({"terminal": 0.25, "interior": 0.15, "enclosed": 0.1, "adjacent": 0.4, "free": 0.1})
        g.density = 0.004
    g.kind_p = {k: _norm(v) for k, v in KIND_GIVEN_RELATION.items()}
    if shape_records:
        asp = [r["aspect"] for r in shape_records if r.get("aspect")]
        g.meta["lozenge_aspect"] = [float(np.percentile(asp, 10)), float(np.percentile(asp, 90))] if asp else None
        g.meta["shape_sources"] = sorted({r["source"] for r in shape_records})
    return g


# ---------------------------------------------------------------------------
# placement
# ---------------------------------------------------------------------------

@dataclass
class PlacedSign:
    kind: str
    relation: str
    fill: object | None
    lines: list
    closed_lines: list
    anchor: tuple
    orientation: float
    scale: float
    w: float
    host: int = -1
    params: dict = field(default_factory=dict)
    spine: list = field(default_factory=list)
    local: object = None            # the Sign in its local frame (for place_random)

    def to_json(self) -> dict:
        paths, closed = sign_paths(self, mode="outline")
        return {"kind": self.kind, "relation": self.relation, "anchor": [round(float(v), 3) for v in self.anchor],
                "orientation": round(float(self.orientation), 4), "scale": round(float(self.scale), 3),
                "host": self.host, "paths": [np.round(p, 3).tolist() for p in paths], "closed": closed}


def _as_arrays(lines) -> list[np.ndarray]:
    out = []
    for ln in lines:
        p = getattr(ln, "points", ln)
        p = np.asarray(p, float)
        if getattr(ln, "closed", False) and len(p) > 2:
            p = np.vstack([p, p[:1]])
        if len(p) >= 2:
            out.append(p)
    return out


class _Host:
    """The line network: resampled points, tangents, free ends, loops."""

    def __init__(self, lines: list[np.ndarray], w: float):
        from scipy.spatial import cKDTree
        self.w = w
        self.lines = lines
        step = max(w / 2, 1e-3)
        P, T, own, U = [], [], [], []
        for i, p in enumerate(lines):
            seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
            s = np.concatenate([[0], np.cumsum(seg)])
            if s[-1] <= 0:
                continue
            ss = np.arange(0, s[-1] + 1e-9, step)
            q = np.column_stack([np.interp(ss, s, p[:, 0]), np.interp(ss, s, p[:, 1])])
            t = np.gradient(q, axis=0) if len(q) > 1 else np.array([[1.0, 0.0]])
            t = ndi.gaussian_filter1d(t, 2.0, axis=0, mode="nearest") if len(q) > 4 else t
            t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
            P.append(q); T.append(t); own.append(np.full(len(q), i)); U.append(ss / s[-1])
        self.P = np.vstack(P) if P else np.zeros((0, 2))
        self.T = np.vstack(T) if T else np.zeros((0, 2))
        self.own = np.concatenate(own) if own else np.zeros(0, int)
        self.U = np.concatenate(U) if U else np.zeros(0)
        self.tree = cKDTree(self.P) if len(self.P) else None
        self.length = float(sum(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)) for p in lines))
        self.union = unary_union([LineString(p) for p in lines]) if lines else None
        # free ends: endpoint not within 2.5 w of any other line's points
        self.ends = []
        for i, p in enumerate(lines):
            if np.allclose(p[0], p[-1]):
                continue
            for e, nb in ((p[0], p[min(len(p) - 1, 4)]), (p[-1], p[max(0, len(p) - 5)])):
                idx = self.tree.query_ball_point(e, 2.5 * w)
                if all(self.own[j] == i for j in idx):
                    d = e - nb
                    self.ends.append((i, e, math.atan2(d[1], d[0])))
        # loops: faces of the line arrangement of moderate size
        self.loops = []
        if self.union is not None:
            for f in polygonize(self.union):
                A = f.area
                if 12 * w * w <= A <= 900 * w * w and 4 * math.pi * A / max(f.length, 1e-9) ** 2 > 0.25:
                    self.loops.append(f)
        xy = self.P
        self.bbox = (xy[:, 0].min(), xy[:, 1].min(), xy[:, 0].max(), xy[:, 1].max()) if len(xy) else (0, 0, 1, 1)

    def clear_of_lines(self, geom, host: int | None, pad: float, host_ok_radius=None, anchor=None) -> bool:
        """True if geom (buffered by pad) touches no line point, except points
        of `host` within host_ok_radius of anchor."""
        b = geom.bounds
        c = np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])
        r = 0.5 * math.hypot(b[2] - b[0], b[3] - b[1]) + pad
        idx = self.tree.query_ball_point(c, r)
        if not idx:
            return True
        gb = geom.buffer(pad) if pad > 0 else geom
        from shapely import contains_xy
        pts = self.P[idx]
        hit = contains_xy(gb, pts[:, 0], pts[:, 1])
        if not hit.any():
            return True
        if host is None or host_ok_radius is None:
            return False
        own = self.own[idx][hit]
        d = np.linalg.norm(pts[hit] - np.asarray(anchor), axis=1)
        return bool(np.all((own == host) & (d <= host_ok_radius)))


def _placed(sign: Sign, relation, angle, xy, host) -> PlacedSign:
    return PlacedSign(kind=sign.kind, relation=relation, fill=_xf_geom(sign.fill, angle, xy),
                      lines=[_xf_pts(q, angle, xy) for q in sign.lines], closed_lines=list(sign.closed_lines),
                      anchor=(float(xy[0]), float(xy[1])), orientation=float(angle), scale=sign.scale, w=sign.w,
                      host=int(host), params=dict(sign.params),
                      spine=[(_xf_pts(c, angle, xy), r) for c, r in sign.spine], local=sign)


def _choice(d: dict, rng):
    ks = list(d)
    p = np.array([d[k] for k in ks], float)
    p = p / p.sum()
    return ks[int(rng.choice(len(ks), p=p))]


def _baseline_side(t: np.ndarray, rng, side_up: float) -> np.ndarray:
    """Unit normal to tangent t on the chosen side: page-up (y < 0) with
    probability side_up."""
    n = np.array([-t[1], t[0]])
    up = n if n[1] < 0 else -n
    return up if rng.random() < side_up else -up


def _make_for(kind, rng, w, grammar: PlacementGrammar, relation):
    """A sign sized by the grammar where it has data, else the vocabulary."""
    p = {}
    if kind in ("lozenge",) and relation == "adjacent" and grammar.size_w:
        p["size"] = float(np.clip(grammar.sample("size_w", rng, 2.0) * 1.15, 1.2, 4.0))
    if kind == "lozenge" and grammar.axis_rel:
        p["nib"] = grammar.sample("axis_rel", rng, 0.0, jitter=0.0) + rng.normal(0, 0.08)
    if kind == "stack":
        if grammar.cluster_p:
            c3 = grammar.cluster_p.get("3", 0.0)
            c2 = grammar.cluster_p.get("2", 0.0)
            p["count"] = 3 if rng.random() < c3 / max(c2 + c3, 1e-9) else 2
        if grammar.pair_angle:
            p["pair_angle"] = grammar.sample("pair_angle", rng, 0.0, jitter=0.0)
        if grammar.pair_spacing_w:
            p["spacing"] = float(np.clip(grammar.sample("pair_spacing_w", rng, 2.0) * 2 / 2, 1.3, 3.0))
        if grammar.size_w:
            p["size"] = float(np.clip(grammar.sample("size_w", rng, 1.8), 1.2, 3.0))
        if grammar.axis_rel:
            p["nib"] = grammar.sample("axis_rel", rng, 0.0, jitter=0.0)
    sg = make_sign(kind, rng, w=w * _spread(kind, rng, grammar), **p)
    sg.w = w
    return sg


def _spread(kind, rng, grammar) -> float:
    """Heavy-tailed size factor for non-dot kinds: the reference holds many
    small forms and a few large ones (blocks, ovals, combs at 10–20 w)."""
    if kind in ("lozenge", "stack", "tick"):
        return 1.0
    sd = float(grammar.meta.get("size_spread", 0.3))
    return float(np.clip(np.exp(rng.normal(0.0, sd)), 0.65, 2.2))


def place_signs(lines, rng: np.random.Generator, grammar: PlacementGrammar | None = None, *,
                w: float = 4.0, n: int | None = None, tries: int = 40,
                relations: dict | None = None) -> list[PlacedSign]:
    """Signs placed in relation to `lines` (list of (N, 2) arrays or
    Strokes) by the placement grammar. `w` = the line width in the lines'
    units; `n` defaults to grammar.density × line length / w. Every sign
    keeps clear of every line except its host near its anchor, and of
    other signs."""
    g = grammar or DEFAULT_GRAMMAR
    arrs = _as_arrays(lines)
    if not arrs:
        return []
    H = _Host(arrs, w)
    if n is None:
        n = max(1, int(round(g.density * H.length / w)))
    rel_p = dict(relations or g.relation_p)
    if not H.loops:
        rel_p.pop("enclosed", None)
    if not H.ends:
        rel_p.pop("terminal", None)
    used_ends: set = set()
    used_loops: set = set()
    placed: list[PlacedSign] = []
    taken = []

    def ok_vs_signs(fp):
        return all(not fp.intersects(t) for t in taken)

    p_con = float(g.meta.get("constellation_p", 0.0))
    con_r = float(g.meta.get("constellation_r_w", 18.0)) * w

    def host_index():
        """A line sample: near the previous sign with probability p_con
        (signs gather in small heterogeneous constellations), else anywhere."""
        if placed and rng.random() < p_con:
            idx = H.tree.query_ball_point(np.asarray(placed[-1].anchor), con_r)
            if idx:
                return int(idx[int(rng.integers(len(idx)))])
        return int(rng.integers(len(H.P)))

    rel = kind = None
    for _ in range(n):
        rel = None
        for _attempt in range(tries):
            # keep the drawn relation for several position tries, so that
            # easy relations (free) are not over-represented by retries
            if _attempt % 10 == 0 or rel not in rel_p:
                rel = _choice(rel_p, rng)
                kind = _choice(g.kind_p.get(rel, KIND_GIVEN_RELATION[rel]), rng)
            if kind not in _VOCAB:
                continue
            sg = _make_for(kind, rng, w, g, rel)
            ps = None
            if rel == "terminal":
                free = [k for k in range(len(H.ends)) if k not in used_ends]
                if not free:
                    break
                if placed and rng.random() < p_con:
                    a0 = np.asarray(placed[-1].anchor)
                    near = [q for q in free if np.linalg.norm(H.ends[q][1] - a0) < 2 * con_r]
                    free = near or free
                k = free[int(rng.integers(len(free)))]
                host, e, ang = H.ends[k]
                xy = e - 0.3 * w * np.array([math.cos(ang), math.sin(ang)])
                ps = _placed(sg, rel, ang, xy, host)
                fp = _footprint(ps)
                if H.clear_of_lines(fp, host, 0.8 * w, host_ok_radius=1.5 * w, anchor=e) and ok_vs_signs(fp):
                    used_ends.add(k)
                else:
                    ps = None
            elif rel == "interior":
                j = host_index()
                if not (0.12 < H.U[j] < 0.88):
                    continue
                t = H.T[j]
                ang = math.atan2(t[1], t[0])
                ps = _placed(sg, rel, ang, H.P[j], H.own[j])
                fp = _footprint(ps)
                if not (H.clear_of_lines(fp, int(H.own[j]), 0.8 * w, host_ok_radius=sg.scale * 0.75 + w,
                                         anchor=H.P[j]) and ok_vs_signs(fp)):
                    ps = None
            elif rel == "enclosed":
                free = [k for k in range(len(H.loops)) if k not in used_loops]
                if not free:
                    rel_p.pop("enclosed", None)
                    break
                k = free[int(rng.integers(len(free)))]
                f = H.loops[k]
                inner = f.buffer(-1.2 * w)
                if inner.is_empty:
                    used_loops.add(k)
                    continue
                # an off-centre point: between the pole of inaccessibility
                # and a random interior point (eyes rarely centre the pupil)
                from shapely.ops import polylabel
                pole = np.array((polylabel(inner if inner.geom_type == "Polygon" else
                                           max(inner.geoms, key=lambda q: q.area), 0.5 * w)).coords[0])
                minx, miny, maxx, maxy = inner.bounds
                q = np.array([rng.uniform(minx, maxx), rng.uniform(miny, maxy)])
                xy = pole + rng.uniform(0.0, 0.45) * (q - pole)
                r_in = f.exterior.distance(Point(xy))
                scl = min(1.0, 0.55 * r_in / max(sg.scale / 2, 1e-9))
                if scl < 0.45:
                    used_loops.add(k)
                    continue
                sg = make_sign(kind, rng, w=w * scl, **{k2: v for k2, v in sg.params.items()
                                                       if k2 in _VOCAB[kind]["params"]})
                sg.w = w
                ps = _placed(sg, rel, rng.uniform(-0.6, 0.6), xy, -1)
                fp = _footprint(ps)
                if H.clear_of_lines(fp, None, 0.6 * w) and ok_vs_signs(fp):
                    used_loops.add(k)
                else:
                    ps = None
            elif rel == "adjacent":
                j = host_index()
                if H.U[j] < 0.05 or H.U[j] > 0.95:
                    continue
                t = H.T[j]
                nrm = _baseline_side(t, rng, g.side_up)
                gap = float(np.clip(g.sample("gap_w", rng, 1.2), 0.3, 6.0)) * w
                ang = math.atan2(t[1], t[0])
                if ang > math.pi / 2:
                    ang -= math.pi
                elif ang < -math.pi / 2:
                    ang += math.pi
                if kind == "crescent":
                    # cup toward or away from the line: local +y of the
                    # crescent points along nrm (toward the line when cup<0)
                    ang2 = math.atan2(nrm[1], nrm[0]) - math.pi / 2
                    ang = ang2 if rng.random() < 0.5 else ang2 + math.pi
                tmp = _placed(sg, rel, ang, (0.0, 0.0), H.own[j])
                fp0 = _footprint(tmp)
                # push off the line until the clear gap is reached
                ext = max(0.0, max(np.dot(np.asarray(c), -nrm) for c in _hull_pts(fp0)))
                xy = H.P[j] + nrm * (gap + ext)
                ps = _placed(sg, rel, ang, xy, H.own[j])
                fp = _footprint(ps)
                if not (H.clear_of_lines(fp, None, 0.85 * gap) and ok_vs_signs(fp)):
                    ps = None
            else:   # free
                b = H.bbox
                best = None
                for _c in range(12):
                    q = np.array([rng.uniform(b[0], b[2]), rng.uniform(b[1], b[3])])
                    d = H.tree.query(q)[0]
                    if best is None or d > best[0]:
                        best = (d, q)
                if best[0] < sg.scale + 3 * w:
                    continue
                ps = _placed(sg, rel, rng.uniform(-math.pi, math.pi), best[1], -1)
                fp = _footprint(ps)
                if not ok_vs_signs(fp):
                    ps = None
            if ps is not None:
                placed.append(ps)
                taken.append(_footprint(ps).buffer(1.0 * w))
                break
    return placed


def _hull_pts(g):
    h = g.convex_hull
    if h.geom_type == "Polygon":
        return list(h.exterior.coords)
    return list(h.coords) if hasattr(h, "coords") else [(0, 0)]


def _footprint(ps: PlacedSign):
    geoms = [] if ps.fill is None else [ps.fill]
    geoms += [LineString(np.vstack([p, p[:1]]) if c else p).buffer(ps.w / 2)
              for p, c in zip(ps.lines, ps.closed_lines) if len(p) >= 2]
    return unary_union(geoms)


def place_random(lines, rng: np.random.Generator, like: list[PlacedSign], *, w: float = 4.0,
                 tries: int = 60) -> list[PlacedSign]:
    """The null for `place_signs`: the SAME signs (kind, geometry, size) at
    uniformly random positions and orientations inside the lines' bounding
    box, still clear of every line (≥ 1 w) and of each other — only the
    relation is removed."""
    arrs = _as_arrays(lines)
    H = _Host(arrs, w)
    b = H.bbox
    out, taken = [], []
    for s in like:
        sg = s.local
        if sg is None:
            raise ValueError("place_random needs signs from place_signs (with .local)")
        for _ in range(tries):
            xy = np.array([rng.uniform(b[0], b[2]), rng.uniform(b[1], b[3])])
            ps = _placed(sg, "random", rng.uniform(-math.pi, math.pi), xy, -1)
            fp = _footprint(ps)
            if H.clear_of_lines(fp, None, 1.0 * w) and all(not fp.intersects(t) for t in taken):
                out.append(ps)
                taken.append(fp.buffer(w))
                break
    return out


# ---------------------------------------------------------------------------
# measurement: ink components and their relation to lines
# ---------------------------------------------------------------------------

def _disk(r: float) -> np.ndarray:
    R = int(math.ceil(r))
    y, x = np.mgrid[-R:R + 1, -R:R + 1]
    return x * x + y * y <= r * r + 1e-9


def _axis(ys, xs):
    """Major-axis angle (image frame, rad) and aspect (minor/major) of a
    pixel set."""
    if len(xs) < 3:
        return 0.0, 1.0
    c = np.cov(np.vstack([xs, ys]))
    ev, evec = np.linalg.eigh(c)
    v = evec[:, 1]
    asp = float(math.sqrt(max(ev[0], 1e-9) / max(ev[1], 1e-9)))
    return float(math.atan2(v[1], v[0])), asp


def _fold_half(a):
    """Angle folded to (−π/2, π/2] (an axis, not a direction)."""
    a = (a + math.pi / 2) % math.pi - math.pi / 2
    return a


def line_width(mask: np.ndarray) -> float:
    """Median full width of the ink at its skeleton (px)."""
    from skimage.morphology import skeletonize
    edt = ndi.distance_transform_edt(mask)
    sk = skeletonize(mask)
    return float(2 * np.median(edt[sk])) if sk.any() else 1.0


def ink_components(mask: np.ndarray, w: float, *, mass_r: float = 0.95, min_area_w2: float = 1.2,
                   max_size_w: float = 12.0, min_thin_w2: float = 1.5) -> list[dict]:
    """Small forms of an ink mask, each with its relation to the lines.

    Masses = components of the opening of the ink by a disc of radius
    mass_r·w (ink thicker than ~2·mass_r line widths). Each mass that is
    small (equivalent diameter ≤ max_size_w·w) is classified by the thin
    ink of the same component touching it: 0 branches → free / adjacent /
    enclosed (by gap and hole test), 1 → terminal (a line ends in it), 2 →
    interior (a bead / swelling on a line), ≥ 3 → junction (usually a thick
    piece of a nib stroke, not a sign; reported apart). Small components
    with no mass (extent ≤ 8 w, area ≥ min_thin_w2 w²; dashes of broken
    lines — aspect < 0.3 without a hole — and ragged specks are dropped)
    are kind 'thin' (dots, rings, ticks, hooks) with the same relation
    tests.

    Returns dicts with: kind (mass/thin), relation, size_w (equivalent
    diameter / w), aspect, solidity, holes, branches, gap_w (to other ink),
    rel_angle (form axis vs nearest line tangent, folded to [0, π/2]),
    centroid (x, y), bbox."""
    from skimage import measure
    m = np.asarray(mask, bool)
    opened = ndi.binary_opening(m, structure=_disk(mass_r * w))
    lab_all, _ = ndi.label(m, structure=np.ones((3, 3)))
    lab_m, nm = ndi.label(opened, structure=np.ones((3, 3)))
    thin = m & ~ndi.binary_dilation(opened, structure=_disk(1.5))
    out = []
    H, W = m.shape

    def ctx(sl, pad):
        r0, r1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, H)
        c0, c1 = max(sl[1].start - pad, 0), min(sl[1].stop + pad, W)
        return (slice(r0, r1), slice(c0, c1))

    def relation_of(comp_full, sl_ctx, size_px, cy, cx):
        """free / adjacent / enclosed for a form not attached to lines;
        gap (px) and tangent of the nearest other ink."""
        other = m[sl_ctx] & ~comp_full
        if not other.any():
            return "free", float("inf"), None
        edt, (iy, ix) = ndi.distance_transform_edt(~other, return_indices=True)
        ys, xs = np.nonzero(comp_full)
        k = int(np.argmin(edt[ys, xs]))
        gap = float(edt[ys[k], xs[k]])
        ny, nx = iy[ys[k], xs[k]], ix[ys[k], xs[k]]
        # tangent of the nearest ink: PCA of other ink within 3 w
        rr = int(3 * w)
        yy, xx = np.nonzero(other[max(ny - rr, 0):ny + rr + 1, max(nx - rr, 0):nx + rr + 1])
        tang, _ = _axis(yy, xx)
        filled = ndi.binary_fill_holes(other)
        enclosed = bool(filled[int(round(cy)) - sl_ctx[0].start, int(round(cx)) - sl_ctx[1].start]) \
            if 0 <= int(round(cy)) - sl_ctx[0].start < filled.shape[0] and \
            0 <= int(round(cx)) - sl_ctx[1].start < filled.shape[1] else False
        if enclosed:
            return "enclosed", gap, tang
        if gap <= max(4.0 * w, 1.5 * size_px):
            return "adjacent", gap, tang
        return "free", gap, tang

    big_masses = 0
    for i, sl in enumerate(ndi.find_objects(lab_m), start=1):
        if sl is None:
            continue
        comp = lab_m[sl] == i
        area = float(comp.sum())
        deq = math.sqrt(4 * area / math.pi)
        if deq > max_size_w * w:
            big_masses += 1
            continue
        if area < min_area_w2 * w * w:
            continue
        ys, xs = np.nonzero(comp)
        cy, cx = ys.mean() + sl[0].start, xs.mean() + sl[1].start
        ang, asp = _axis(ys, xs)
        props = measure.regionprops(comp.astype(int))[0]
        pad = int(6 * w + deq)
        sc = ctx(sl, pad)
        blob = np.zeros((sc[0].stop - sc[0].start, sc[1].stop - sc[1].start), bool)
        blob[sl[0].start - sc[0].start:sl[0].stop - sc[0].start,
             sl[1].start - sc[1].start:sl[1].stop - sc[1].start] = comp
        zone = ndi.binary_dilation(blob, structure=_disk(0.6 * w + 3)) & ~ndi.binary_dilation(blob, structure=_disk(1))
        full_id = int(np.bincount(lab_all[sl][comp]).argmax())
        same = lab_all[sc] == full_id          # branches must be ink of the SAME component
        br_lab, nbr = ndi.label(thin[sc] & zone & same, structure=np.ones((3, 3)))
        sizes = ndi.sum(np.ones_like(br_lab), br_lab, range(1, nbr + 1)) if nbr else []
        nbr = int(sum(1 for s in sizes if s >= 0.5 * w))
        rec = {"kind": "mass", "size_w": deq / w, "aspect": asp, "solidity": float(props.solidity),
               "holes": int(1 - props.euler_number), "branches": nbr,
               "centroid": (float(cx), float(cy)), "bbox": (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)}
        if nbr == 0:
            # the full ink component containing the mass, minus nothing: the
            # form stands alone if its full component ≈ the mass
            comp_full = same
            rel, gap, tang = relation_of(comp_full, sc, deq, cy, cx)
        else:
            rel = {1: "terminal", 2: "interior"}.get(nbr, "junction")
            gap, tang = 0.0, None
            yb, xb = np.nonzero(thin[sc] & zone)
            if len(yb) > 3:
                tang, _ = _axis(yb, xb)
        rec["relation"] = rel
        rec["gap_w"] = gap / w if math.isfinite(gap) else None
        rec["rel_angle"] = None if tang is None else abs(_fold_half(ang - tang))
        out.append(rec)
    # small thin forms (no mass inside)
    has_mass = np.unique(lab_all[opened])
    for i, sl in enumerate(ndi.find_objects(lab_all), start=1):
        if sl is None or i in has_mass:
            continue
        h, wd = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if max(h, wd) > 8 * w:
            continue
        comp = lab_all[sl] == i
        area = float(comp.sum())
        if area < min_thin_w2 * w * w:
            continue
        props = measure.regionprops(comp.astype(int))[0]
        ys, xs = np.nonzero(comp)
        cy, cx = ys.mean() + sl[0].start, xs.mean() + sl[1].start
        ang, asp = _axis(ys, xs)
        holes = int(1 - props.euler_number)
        if holes == 0 and asp < 0.3:
            continue            # a dash / fragment of a broken line, not a form
        if area < 3 * w * w and props.solidity < 0.8:
            continue
        sc = ctx(sl, int(10 * w))
        comp_full = lab_all[sc] == i
        rel, gap, tang = relation_of(comp_full, sc, max(h, wd), cy, cx)
        out.append({"kind": "thin", "size_w": max(h, wd) / w, "aspect": asp, "solidity": float(props.solidity),
                    "holes": int(1 - props.euler_number), "branches": 0, "relation": rel,
                    "gap_w": gap / w if math.isfinite(gap) else None,
                    "rel_angle": None if tang is None else abs(_fold_half(ang - tang)),
                    "centroid": (float(cx), float(cy)), "bbox": (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop)})
    for r in out:
        r["_big_masses"] = big_masses
    return out


def inventory(mask: np.ndarray, *, w: float | None = None) -> dict:
    """Summary of `ink_components` over an image: counts by relation and
    kind, sizes / gaps / angles, signs per line width of skeleton length."""
    from skimage.morphology import skeletonize
    m = np.asarray(mask, bool)
    w = line_width(m) if w is None else w
    comps = ink_components(m, w)
    sk_len = float(skeletonize(m).sum())
    rel = {}
    for c in comps:
        rel[c["relation"]] = rel.get(c["relation"], 0) + 1

    def q(xs):
        xs = [x for x in xs if x is not None]
        return [round(float(v), 3) for v in np.percentile(xs, [10, 25, 50, 75, 90])] if xs else None

    by = {}
    for c in comps:
        by.setdefault(c["relation"], []).append(c["size_w"])
    attached = [c for c in comps if c["relation"] in ("terminal", "interior", "junction")]
    summary = {
        "w_px": w, "n": len(comps), "big_masses": comps[0]["_big_masses"] if comps else 0,
        "relation_counts": rel,
        "kind_counts": {k: sum(1 for c in comps if c["kind"] == k) for k in ("mass", "thin")},
        "relation_by_kind": {k: {r: sum(1 for c in comps if c["kind"] == k and c["relation"] == r)
                                 for r in sorted(rel)} for k in ("mass", "thin")},
        "size_w_q": {r: q(v) for r, v in by.items()},
        "size_w_by_relation": {r: [round(float(x), 3) for x in v] for r, v in by.items()},
        "gap_w_q": {r: q([c["gap_w"] for c in comps if c["relation"] == r]) for r in ("adjacent", "enclosed", "free")},
        "rel_angle_deg_q": {r: q([None if c["rel_angle"] is None else math.degrees(c["rel_angle"])
                                  for c in comps if c["relation"] == r]) for r in rel},
        "end_share": (sum(1 for c in attached if c["relation"] == "terminal") / len(attached)) if attached else 0.0,
        "holes_share": sum(1 for c in comps if c["holes"] > 0) / max(len(comps), 1),
        "skeleton_px": sk_len,
        "signs_per_w": len(comps) / max(sk_len / w, 1e-9),
        "components": [{k: v for k, v in c.items() if k != "_big_masses"} for c in comps],
    }
    return summary


def measure_dots(mask: np.ndarray, *, source: str, w: float | None = None, min_area_w2: float = 0.35,
                 max_area_w2: float = 7.0, min_solidity: float = 0.82, neigh_w: float = 14.0) -> list[dict]:
    """Dot (nuqta-like) geometry relative to letter bodies in one ink mask.

    Dots: compact components (area min..max_area_w2 · w², solidity ≥
    min_solidity, extent ≤ 4.5 w). Bodies: components with area ≥ 10 w².
    For each dot: equivalent diameter / w (size_w), aspect, long-axis angle
    relative to the LOCAL baseline (axis_rel; baseline = PCA axis of body ink
    within neigh_w·w), clear gap to the nearest body (host_gap_w), side
    (side_up: the dot is on the page-up side of the local baseline),
    along-host position u (projection on the host's principal axis), and
    clustering (dots whose centres lie within 2.6 dot sizes: count, pair
    axis angle vs baseline, pair spacing / dot size). `source` is carried
    on every record for the policy gate in `learn_grammar`."""
    from skimage import measure
    m = np.asarray(mask, bool)
    w = line_width(m) if w is None else w
    lab, n = ndi.label(m, structure=np.ones((3, 3)))
    areas = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
    objs = ndi.find_objects(lab)
    body_ids = {i + 1 for i, a in enumerate(areas) if a >= 10 * w * w}
    body = np.isin(lab, list(body_ids)) if body_ids else np.zeros_like(m)
    if not body.any():
        return []
    edt, (iy, ix) = ndi.distance_transform_edt(~body, return_indices=True)
    dots = []
    for i, a in enumerate(areas, start=1):
        if not (min_area_w2 * w * w <= a <= max_area_w2 * w * w):
            continue
        sl = objs[i - 1]
        h, wd = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if max(h, wd) > 4.5 * w:
            continue
        comp = lab[sl] == i
        props = measure.regionprops(comp.astype(int))[0]
        if props.solidity < min_solidity:
            continue
        ys, xs = np.nonzero(comp)
        ys = ys + sl[0].start
        xs = xs + sl[1].start
        k = int(np.argmin(edt[ys, xs]))
        gap = float(edt[ys[k], xs[k]])
        if gap > 6 * w:            # too far from any body to be a diacritic
            continue
        cy, cx = float(ys.mean()), float(xs.mean())
        hy, hx = int(iy[ys[k], xs[k]]), int(ix[ys[k], xs[k]])
        rr = int(neigh_w * w)
        r0, c0 = max(int(cy) - rr, 0), max(int(cx) - rr, 0)
        by_, bx_ = np.nonzero(body[r0:int(cy) + rr + 1, c0:int(cx) + rr + 1])
        if len(by_) < 10:
            continue
        base, _ = _axis(by_ + r0, bx_ + c0)
        base = _fold_half(base)
        bc = np.array([bx_.mean() + c0, by_.mean() + r0])
        ang, asp = _axis(ys, xs)
        nrm = np.array([-math.sin(base), math.cos(base)])
        if nrm[1] > 0:
            nrm = -nrm             # page-up normal
        # side relative to the nearest host point's local baseline line
        side = float(np.dot(np.array([cx, cy]) - np.array([hx, hy]), nrm))
        host = lab[hy, hx]
        hs = objs[host - 1]
        hyy, hxx = np.nonzero(lab[hs] == host)
        hang, _ = _axis(hyy, hxx)
        d = np.array([math.cos(hang), math.sin(hang)])
        proj = (np.column_stack([hxx + hs[1].start, hyy + hs[0].start]) @ d)
        u = (float(np.dot([cx, cy], d)) - proj.min()) / max(proj.max() - proj.min(), 1e-9)
        dots.append({"source": source, "size_w": math.sqrt(4 * a / math.pi) / w, "aspect": asp,
                     "axis_rel": _fold_half(ang - base), "host_gap_w": gap / w, "side_up": bool(side > 0),
                     "normal_off_w": float(np.dot(np.array([cx, cy]) - bc, nrm)) / w,
                     "along_u": float(np.clip(u, 0, 1)), "centroid": (cx, cy), "baseline": base,
                     "solidity": float(props.solidity), "w_px": w})
    # clustering
    if dots:
        C = np.array([d["centroid"] for d in dots])
        S = np.array([d["size_w"] * w for d in dots])
        parent = list(range(len(dots)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for a in range(len(dots)):
            for b in range(a + 1, len(dots)):
                if np.linalg.norm(C[a] - C[b]) <= 2.6 * max(S[a], S[b]):
                    parent[find(a)] = find(b)
        groups: dict = {}
        for a in range(len(dots)):
            groups.setdefault(find(a), []).append(a)
        for mem in groups.values():
            for j, a in enumerate(mem):
                dots[a]["cluster"] = min(len(mem), 3)
                dots[a]["cluster_lead"] = j == 0
            if len(mem) == 2:
                a, b = mem
                v = C[b] - C[a]
                pa = abs(_fold_half(math.atan2(v[1], v[0]) - dots[a]["baseline"]))
                dots[a]["pair_angle"] = pa
                dots[a]["pair_spacing"] = float(np.linalg.norm(v) / np.mean(S[mem]))
    return dots


def dot_shape_from_polygons(polys: list, *, source: str) -> list[dict]:
    """Dot SHAPE stats (aspect, rhombicity = area / (L·W) of the rotated
    bbox: 0.5 rhombus, 0.785 ellipse, 1 rectangle) of small isolated glyph
    contours (font dots). Shape only — never placement."""
    out = []
    for p in polys:
        if p.is_empty or p.area <= 0:
            continue
        r = p.minimum_rotated_rectangle
        xy = np.asarray(r.exterior.coords)[:4]
        e = [np.linalg.norm(xy[(i + 1) % 4] - xy[i]) for i in range(2)]
        L, Wd = max(e), min(e)
        out.append({"source": source, "aspect": Wd / max(L, 1e-9), "rhombicity": p.area / max(L * Wd, 1e-9),
                    "size": math.sqrt(4 * p.area / math.pi)})
    return out


# Fallback when no learned grammar is at hand: deciles of the grammar
# learned on 2026-10-16 by experiments/signs_study.py (stage `grammar`; 299
# dots from 11 secular sheets + the reference's relation mix). The study's
# own .local/gesture/out/signs/grammar.json holds the full samples.
DEFAULT_GRAMMAR = PlacementGrammar(
    relation_p={"terminal": 0.298, "interior": 0.123, "enclosed": 0.123, "adjacent": 0.333, "free": 0.123},
    kind_p={k: _norm(v) for k, v in KIND_GIVEN_RELATION.items()},
    density=0.0114, gap_w=[0.57, 0.84, 1.2, 1.81, 2.5, 3.36, 4.71], side_up=0.515,
    along_u=[0.0, 0.15, 0.55, 0.89, 1.0], size_w=[1.3, 1.57, 1.81, 2.16, 2.73],
    axis_rel=[-1.341, -0.979, -0.232, 0.575, 1.162], cluster_p={"1": 0.884, "2": 0.084, "3": 0.032},
    pair_angle=[0.127, 0.179, 0.438, 0.778, 1.343], pair_spacing_w=[1.17, 1.23, 1.41, 2.24, 2.56],
    end_share=0.065, sources=["default (deciles of the 2026-10-16 fit)"],
    meta={"constellation_p": 0.6, "constellation_r_w": 16.0, "size_spread": 0.4})


# ===========================================================================
# LINE EVENTS — signs as the line itself changing (results/signs-events-2026-10-16.md)
# ===========================================================================
#
# Round 6 stamped separate sign objects next to lines; the reference's forms
# are the LINE changing (a goblet is the line swelling, a knot is the line
# filling in). Here the placement grammar only chooses WHERE (a free line
# end, an interior stretch, a loop, a junction, a corner; arc position; side)
# and WHICH regime operator turns that part of the line into the sign:
#
#   site      op            what the line does there (gesture.regime)
#   end       drop          r → 2 at the end: a teardrop          terminal_drop("drop")
#             lozenge       thickens to nib (fitted ramp), nuqta press   thicken + terminal_drop
#             hook          ends in a nib loop whose counter shrinks     close_fill(0.5)
#             ring          ends in a plain line loop                    close_fill(0)
#             block         ends in a loop that closes into a dot        close_fill(1)
#             vessel        the end flares into a goblet                 swell("vessel")
#             eye           loop + inward spiral swelling to a pupil      eye
#             detached      line stops; a dot continues it after a gap (calligraphic gap)
#   interior  bead          asymmetric swelling (rise/fall drawn separately)
#             vessel_mid    slow rise (fitted nib ramp), fast fall: an oval mass on the line
#             nib           a stretch thickens to nib and back (fitted ramp)
#             knot          the line makes a small loop that fills in
#             comb / tick   the line sheds 1–3 short tapering ticks
#             drip          the line sheds a hanging drip ending in a drop
#             body          Oehlen's body rule: a thick core on the line with
#                           2–4 thinning exits moving away from it
#   loop      fill_loop     a small loop of the line closes and fills
#             pupil         a short stalk grows from the loop's rim into a pupil
#   junction  junction_mass the lines thicken into one mass where they meet (exits = the lines)
#   corner    comma         the line thickens through a corner into a hook / comma
#
# Rates, sizes, cluster sizes and spacings come from the reference reading
# (26 forms, each mapped to the event above that makes it, + the 16 masses
# with ≥ 3 exits); the detached-dot gap from calligraphic dots (policy
# gate); thin→thick ramps from regime.PROFILE_DEFAULTS. Groups are grown
# RESPONSIVELY: each event in a cluster sits a characteristic spacing along
# the line from the previous one and its op, side and size are conditioned
# on the previous event's.

EVENT_SITES = ("end", "interior", "loop", "junction", "corner")
EVENT_OPS = {
    "end": ("drop", "lozenge", "hook", "ring", "block", "vessel", "eye", "detached"),
    "interior": ("bead", "vessel_mid", "nib", "knot", "comb", "drip", "body"),
    "loop": ("fill_loop", "pupil"),
    "junction": ("junction_mass", "body"),
    "corner": ("comma",),
}
HEAVY_OPS = frozenset({"vessel", "block", "vessel_mid", "junction_mass", "body", "knot", "fill_loop", "bead", "eye"})

# The 26 clear forms of the reference (signs_study.MANUAL_REF order), each
# read as the line event that would make it. None = not representable (a
# negative eye inside a mass). Group ids: the four constellations.
REFERENCE_EVENTS = [
    ("loop", "pupil", None), ("loop", "pupil", 3), ("end", "drop", 3), ("end", "detached", 3),
    ("end", "lozenge", None), ("end", "drop", None), ("interior", "knot", 2), ("end", "detached", 2),
    ("end", "drop", None), ("corner", "comma", None), ("interior", "knot", None), ("interior", "bead", None),
    ("interior", "bead", 4), ("end", "vessel", 4), ("interior", "vessel_mid", 4), ("end", "block", 1),
    ("end", "ring", 1), ("corner", "comma", 1), ("interior", "comb", 1), ("end", "hook", 1),
    ("loop", "pupil", None), ("end", "detached", None), ("interior", "nib", None), (None, None, None),
    ("end", "hook", None), ("end", "drop", None),
]


@dataclass
class EventGrammar:
    """Where line events happen and which operator makes them. Sizes and
    spacings in units of w (the reference's thin-line width). Learned fields
    are sample lists (drawn with replacement + jitter)."""
    site_p: dict = field(default_factory=dict)
    op_p: dict = field(default_factory=dict)              # site → {op: p}
    size_w: dict = field(default_factory=dict)            # op → [size / w]
    density: float = 0.009                                # events per w of line
    group_p: float = 0.5                                  # P(an event starts a group of ≥ 2)
    group_sizes: list = field(default_factory=list)       # sizes of groups (≥ 2)
    spacing_w: list = field(default_factory=list)         # neighbour spacing inside a group / w
    size_ratio: list = field(default_factory=list)        # log(size_next / size_prev) inside groups
    same_op_damp: float = 0.25                            # responsive: an answer rarely repeats
    contrast_boost: float = 1.6                           # heavy answers light and vice versa
    side_flip_p: float = 0.6                              # the next event answers on the other side
    gap_ratio: list = field(default_factory=list)         # detached: clear gap / dot size (calligraphy)
    nib_ratio: tuple = (3.01, 3.35, 4.13)                 # nib W / w (reference thick/thin q25-50-75)
    sources: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_json(d: dict) -> "EventGrammar":
        d = dict(d)
        d["nib_ratio"] = tuple(d.get("nib_ratio", (3.01, 3.35, 4.13)))
        return EventGrammar(**d)


def learn_event_grammar(forms: list[dict], *, junction_masses: dict | None = None, skeleton_w: float,
                        dot_records: list[dict] | None = None, manifest: dict | None = None,
                        auto_sizes: dict | None = None, body_share: float = 0.12) -> EventGrammar:
    """Event grammar from the reference reading and calligraphic dots.

    forms: [{site, op, extent_w, group, centre_w (x, y)}] — the reference's
    clear forms mapped to events (REFERENCE_EVENTS + the study's boxes).
    junction_masses: {"n": masses with ≥ 3 exits, "diam_w": [..]}.
    skeleton_w: the reference's line length in w (for the density).
    dot_records: calligraphy dots (`measure_dots`) for the detached-dot gap;
    POLICY GATE: every source must pass `calligraphy.require_generative`.
    body_share: design share (not measured) of Oehlen's body op among
    interior and junction events.
    auto_sizes: the automated inventory's mass sizes / w by relation
    (`inventory()["size_w_by_relation"]`): "interior" swellings set the bead
    diameter (the read forms' boxes include the line, so they overstate
    it); "junction" thickenings (≥ 2 w) join the junction masses, giving the
    heavy tail many small knots + a few large masses."""
    from . import calligraphy as cg
    g = EventGrammar()
    if dot_records:
        srcs = sorted({r["source"] for r in dot_records})
        cg.require_generative(srcs, manifest)
        g.sources = srcs
        g.gap_ratio = [round(float(r["host_gap_w"]) / max(float(r["size_w"]), 1e-6), 4)
                       for r in dot_records if r.get("host_gap_w") is not None and r.get("size_w")]
        g.meta["dot_size_w"] = [round(float(r["size_w"]), 3) for r in dot_records if r.get("size_w")]
    fs = [f for f in forms if f.get("site")]
    site_n: dict = {}
    op_n: dict = {}
    for f in fs:
        site_n[f["site"]] = site_n.get(f["site"], 0) + 1
        op_n.setdefault(f["site"], {})
        op_n[f["site"]][f["op"]] = op_n[f["site"]].get(f["op"], 0) + 1
        g.size_w.setdefault(f["op"], []).append(round(float(f["extent_w"]), 3))
    nj = int((junction_masses or {}).get("n", 0))
    if nj:
        site_n["junction"] = site_n.get("junction", 0) + nj
        op_n.setdefault("junction", {})["junction_mass"] = nj
        g.size_w["junction_mass"] = [round(float(v), 3) for v in junction_masses.get("diam_w", [])]
    if auto_sizes:
        if auto_sizes.get("interior"):
            g.size_w["bead"] = [round(float(v), 3) for v in auto_sizes["interior"]]
        if auto_sizes.get("junction"):
            g.size_w.setdefault("junction_mass", [])
            g.size_w["junction_mass"] += [round(float(v), 3) for v in auto_sizes["junction"] if v >= 2.0]
    # Oehlen's body rule: a design share, carved out of interior + junction
    for site in ("interior", "junction"):
        if site in op_n:
            tot = sum(op_n[site].values())
            op_n[site]["body"] = body_share * tot / max(1 - body_share, 1e-9)
    g.size_w.setdefault("body", [6.0, 8.0, 10.0, 13.0])
    if g.meta.get("dot_size_w"):
        # a detached dot is a calligraphic dot: its size relative to the
        # line is the calligraphic dot/line ratio (×1.5: the line's end is
        # taken as slightly pressed, as a nib stroke ends) — not the
        # reference's box extents, which include the specks' spread
        g.size_w["detached"] = [round(1.5 * v, 3) for v in g.meta["dot_size_w"]]
    g.site_p = _norm({k: float(v) for k, v in site_n.items()})
    g.op_p = {k: _norm({o: float(c) for o, c in v.items()}) for k, v in op_n.items()}
    n_events = len(fs) + nj
    g.density = n_events / max(skeleton_w, 1e-9)
    # groups: sizes, nearest-neighbour spacing, consecutive size ratios
    groups: dict = {}
    for f in fs:
        if f.get("group") is not None:
            groups.setdefault(f["group"], []).append(f)
    n_grouped = sum(len(v) for v in groups.values())
    g.group_sizes = sorted(len(v) for v in groups.values())
    # P(a group starts) such that the grouped share of events matches
    mean_k = float(np.mean(g.group_sizes)) if g.group_sizes else 2.0
    share = n_grouped / max(len(fs), 1)
    g.group_p = float(share / mean_k / max(share / mean_k + (1 - share), 1e-9))
    sp, rat = [], []
    for v in groups.values():
        C = np.array([f["centre_w"] for f in v], float)
        for i in range(len(v)):
            d = np.linalg.norm(C - C[i], axis=1)
            d[i] = np.inf
            j = int(np.argmin(d))
            sp.append(round(float(d[j]), 3))
            rat.append(round(float(np.log(v[j]["extent_w"] / v[i]["extent_w"])), 4))
    g.spacing_w, g.size_ratio = sp, rat
    g.meta.update({"n_forms": len(fs), "n_junction_masses": nj, "n_grouped": n_grouped,
                   "body_share_design": body_share})
    return g


@dataclass
class LineEvent:
    site: str
    op: str
    line: int
    s: float                     # arc length (mm) on the line; ends: 0 or the line length
    size: float                  # characteristic size (mm)
    side: float = 1.0            # +1 / −1: left / right of the line's direction
    end: int = -1                # 0 = start, 1 = end (site "end")
    other: tuple | None = None   # junction: (line j, s_j)
    group: int = -1
    params: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        d = asdict(self)
        d["s"] = round(float(self.s), 3)
        d["size"] = round(float(self.size), 3)
        return d


class _Net:
    """Sites of a line network (mm): free ends, junctions (T and X),
    corners, self-loops, multi-line faces."""

    def __init__(self, lines: list[np.ndarray], w: float):
        from scipy.spatial import cKDTree
        from shapely import STRtree
        self.w = w
        self.lines = lines
        self.L = [float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1))) for p in lines]
        self.S = [np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]) for p in lines]
        step = max(w / 2, 1e-3)
        P, own, ss = [], [], []
        self.res = []
        for i, p in enumerate(lines):
            s = self.S[i]
            t = np.arange(0, s[-1] + 1e-9, step)
            q = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
            self.res.append((t, q))
            P.append(q); own.append(np.full(len(q), i)); ss.append(t)
        self.P = np.vstack(P)
        self.own = np.concatenate(own)
        self.ss = np.concatenate(ss)
        self.tree = cKDTree(self.P)
        self.geoms = [LineString(p) for p in lines]
        self.total = float(sum(self.L))
        # free ends and T-junctions
        self.ends = []                      # (line, end, point, heading)
        self.junctions = []                 # (line i, s_i, line j, s_j, point)
        for i, p in enumerate(lines):
            if np.allclose(p[0], p[-1]) or self.L[i] < 6 * w:
                continue
            for e, sidx in ((0, 0), (1, -1)):
                pt = p[sidx]
                idx = [k for k in self.tree.query_ball_point(pt, 2.5 * w) if self.own[k] != i]
                if not idx:
                    t, q = self.res[i]
                    nb = q[min(4, len(q) - 1)] if e == 0 else q[max(len(q) - 5, 0)]
                    d = pt - nb
                    self.ends.append((i, e, pt, math.atan2(d[1], d[0])))
                else:
                    k = min(idx, key=lambda kk: np.linalg.norm(self.P[kk] - pt))
                    self.junctions.append((i, 0.0 if e == 0 else self.L[i], int(self.own[k]), float(self.ss[k]),
                                           self.P[k].copy()))
        # crossings
        st = STRtree(self.geoms)
        for i, gi in enumerate(self.geoms):
            for j in st.query(gi):
                j = int(j)
                if j <= i:
                    continue
                x = gi.intersection(self.geoms[j])
                pts = [x] if x.geom_type == "Point" else [q for q in getattr(x, "geoms", []) if q.geom_type == "Point"]
                for q in pts:
                    si, sj = gi.project(q), self.geoms[j].project(q)
                    if min(si, self.L[i] - si) < 3 * w or min(sj, self.L[j] - sj) < 3 * w:
                        continue
                    self.junctions.append((i, float(si), j, float(sj), np.array(q.coords[0])))
        # corners: turning ≥ 70° within ±2 w, local maxima, ≥ 4 w from the ends
        self.corners = []                   # (line, s, turn sign)
        for i, (t, q) in enumerate(self.res):
            if len(q) < 12:
                continue
            k = max(int(round(2 * w / step)), 2)
            d1 = q[k:-k] - q[:-2 * k]
            d2 = q[2 * k:] - q[k:-k]
            a1 = np.arctan2(d1[:, 1], d1[:, 0])
            a2 = np.arctan2(d2[:, 1], d2[:, 0])
            turn = np.angle(np.exp(1j * (a2 - a1)))
            at = np.abs(turn)
            for m in range(1, len(at) - 1):
                if at[m] >= np.deg2rad(70) and at[m] >= at[m - 1] and at[m] > at[m + 1]:
                    s0 = t[m + k]
                    if 4 * w < s0 < self.L[i] - 4 * w:
                        if not self.corners or self.corners[-1][0] != i or s0 - self.corners[-1][1] > 4 * w:
                            self.corners.append((i, float(s0), float(np.sign(turn[m]))))
        # self-loops of one line (arc range) and faces of the arrangement
        self.selfloops = []                 # (line, s0, s1, polygon)
        self.faces = []                     # (polygon, boundary line, s on it)
        U = unary_union(self.geoms)
        for f in polygonize(U):
            A = f.area
            if not (6 * w * w <= A <= 900 * w * w) or 4 * math.pi * A / max(f.length, 1e-9) ** 2 < 0.25:
                continue
            bd = np.asarray(f.exterior.coords)
            ii = self.tree.query(bd)[1]
            owners = np.unique(self.own[ii])
            if len(owners) == 1:
                i = int(owners[0])
                s_on = self.ss[ii]
                self.selfloops.append((i, float(s_on.min()), float(s_on.max()), f))
            c = np.asarray(f.centroid.coords[0])
            k = int(self.tree.query(c)[1])
            self.faces.append((f, int(self.own[k]), float(self.ss[k])))

    def loop_sites(self, used: set) -> list[tuple]:
        """(line, s0, s1[, polygon]) for self-loops (polygon looked up) and
        faces of several lines (root = the boundary line nearest the centroid)."""
        out = [(i, s0, s1) for (i, s0, s1, _) in self.selfloops if (i, round(s0, 2)) not in used]
        for f, i, s in self.faces:
            if (i, round(s, 2)) not in used and not any(q[3].equals(f) for q in self.selfloops):
                out.append((i, s, s, f))
        return out

    def point(self, i: int, s: float) -> tuple[np.ndarray, np.ndarray]:
        """Point and unit tangent on line i at arc length s."""
        t, q = self.res[i]
        s = float(np.clip(s, 0, self.L[i]))
        x = np.array([np.interp(s, t, q[:, 0]), np.interp(s, t, q[:, 1])])
        j = int(np.clip(np.searchsorted(t, s), 1, len(t) - 1))
        a, b = q[max(j - 3, 0)], q[min(j + 3, len(q) - 1)]
        d = b - a
        return x, d / (np.linalg.norm(d) + 1e-12)

    def site_at(self, i: int, s: float, used_ends: set) -> tuple[str, dict]:
        """Which site a position on a line is, read off the line there."""
        w = self.w
        for (li, e, pt, h) in self.ends:
            if li == i and abs((0.0 if e == 0 else self.L[i]) - s) < 3 * w and (li, e) not in used_ends:
                return "end", {"end": e}
        for (a, sa, b, sb, pt) in self.junctions:
            if (a == i and abs(sa - s) < 2.5 * w) or (b == i and abs(sb - s) < 2.5 * w):
                return "junction", {"j": (a, sa, b, sb)}
        for (li, sc, sg) in self.corners:
            if li == i and abs(sc - s) < 2.5 * w:
                return "corner", {"s": sc, "turn": sg}
        for (li, s0, s1, f) in self.selfloops:
            if li == i and s0 <= s <= s1:
                return "loop", {"loop": (li, s0, s1)}
        return "interior", {}


def _lognormal_q(rng, q):
    """Log-normal through a quartile triple, clipped to [0.7·q25, 1.4·q75]
    (an unclipped tail draw once made a 'nib' 1 mm long)."""
    lo, med, hi = q
    sd = (math.log(hi) - math.log(lo)) / (2 * 0.674)
    v = float(math.exp(math.log(med) + sd * rng.standard_normal()))
    return float(np.clip(v, 0.7 * lo, 1.4 * hi))


def _sample_list(rng, xs, default, jitter=0.12):
    if not xs:
        return float(default)
    return float(xs[int(rng.integers(len(xs)))]) * float(math.exp(jitter * rng.standard_normal()))


_SIZE_CLIP_W = {"detached": (1.5, 5.0), "drop": (2.5, 9.0), "lozenge": (2.5, 7.0), "hook": (4.0, 12.0),
                "ring": (4.0, 10.0), "block": (4.0, 12.0), "vessel": (10.0, 26.0), "eye": (6.0, 14.0),
                "bead": (2.2, 8.0), "vessel_mid": (5.0, 14.0), "nib": (4.0, 10.0), "knot": (4.0, 12.0),
                "comb": (3.0, 8.0), "drip": (4.0, 12.0), "body": (5.0, 13.0), "fill_loop": (3.0, 14.0),
                "pupil": (1.4, 4.0), "junction_mass": (2.0, 10.0), "comma": (3.0, 12.0)}


def _op_size(rng, g: EventGrammar, op: str, w: float) -> float:
    lo, hi = _SIZE_CLIP_W.get(op, (2.0, 10.0))
    default = 0.5 * (lo + hi)
    xs = g.size_w.get(op, [])
    v = _sample_list(rng, xs, default, jitter=0.3) if xs else default * math.exp(0.3 * rng.standard_normal())
    return float(np.clip(v, lo, hi)) * w


def _choose_op(rng, g: EventGrammar, site: str, prev: "LineEvent | None") -> str | None:
    ops = dict(g.op_p.get(site, {}))
    if site == "end":
        ops.pop("junction_mass", None)
    if not ops:
        return None
    if prev is not None:      # responsive: answer the previous event, don't repeat it
        for o in list(ops):
            if o == prev.op:
                ops[o] *= g.same_op_damp
            if (o in HEAVY_OPS) != (prev.op in HEAVY_OPS):
                ops[o] *= g.contrast_boost
    return _choice(ops, rng)


def plan_events(lines, rng: np.random.Generator, grammar: EventGrammar | None = None, *, w: float = 1.0,
                n: int | None = None, mode: str = "grammar", like: list[LineEvent] | None = None) -> list[LineEvent]:
    """Choose events on `lines` ((N, 2) arrays, mm). mode "grammar": sites
    by the grammar, events in responsive groups along lines. mode "random"
    (the null; needs `like`): the SAME ops and sizes at random positions —
    uniform along the network for interior-type ops, a random free end for
    end ops, a random loop for loop ops; no groups."""
    g = grammar or DEFAULT_EVENT_GRAMMAR
    arrs = _as_arrays(lines)
    if not arrs:
        return []
    N = _Net(arrs, w)
    occupied: dict = {}               # line → [(s0, s1)]
    used_ends: set = set()
    used_loops: set = set()
    anchors: list = []
    out: list[LineEvent] = []

    def ext_of(op, size):
        k = {"vessel": 1.2, "vessel_mid": 2.5, "nib": 3.5, "bead": 2.2, "body": 1.4, "junction_mass": 1.6,
             "comma": 2.0, "knot": 1.2, "comb": 1.0, "drip": 0.8, "fill_loop": 0.5, "pupil": 0.5}.get(op, 1.0)
        return k * size

    def free(i, s, e):
        return all(s + e < a or s - e > b for a, b in occupied.get(i, []))

    def clear(xy, size):
        return all(np.linalg.norm(xy - a) > 0.7 * (size + sa) for a, sa in anchors)

    def commit(ev: LineEvent, xy):
        e = ext_of(ev.op, ev.size)
        if ev.site == "end":
            used_ends.add((ev.line, ev.end))
            a = (0.0, e + 2 * w) if ev.end == 0 else (N.L[ev.line] - e - 2 * w, N.L[ev.line])
            occupied.setdefault(ev.line, []).append(a)
        elif ev.site == "loop":
            used_loops.add(ev.params.get("loop_key"))
            occupied.setdefault(ev.line, []).append((ev.s - e, ev.s + e))
        else:
            occupied.setdefault(ev.line, []).append((ev.s - e, ev.s + e))
            if ev.other is not None:
                j, sj = ev.other
                occupied.setdefault(j, []).append((sj - e, sj + e))
        anchors.append((np.asarray(xy, float), ev.size))
        out.append(ev)

    def build(site, op, i, s, size, side, info, group):
        """A concrete event at line i, arc s; None if it doesn't fit."""
        if site == "end":
            e = info["end"]
            if (i, e) in used_ends:
                return None
            s = 0.0 if e == 0 else N.L[i]
            if N.L[i] < 3 * ext_of(op, size) + 6 * w:
                return None
            ev = LineEvent(site, op, i, s, size, side, end=e, group=group)
        elif site == "loop":
            li, s0, s1 = info["loop"][:3]
            poly = info["loop"][3] if len(info["loop"]) > 3 else None
            key = (li, round(s0, 2))
            if key in used_loops:
                return None
            if poly is not None and op != "pupil":
                op = "pupil"                 # a face of several lines: only a pupil can grow into it
            ev = LineEvent(site, op, li, 0.5 * (s0 + s1), size, side, group=group,
                           params={"s0": s0, "s1": s1, "loop_key": key})
            if op == "pupil":
                if poly is None:
                    f = [q for q in N.selfloops if q[0] == li and abs(q[1] - s0) < 1e-6]
                    if not f:
                        return None
                    poly = f[0][3]
                r_in = poly.exterior.distance(poly.representative_point())
                ev.size = float(np.clip(min(size, 0.75 * r_in), 0.8 * w, 4 * w))
                c = np.asarray(poly.centroid.coords[0])
                ev.params["centre"] = [float(c[0]), float(c[1])]
            else:
                ev.size = float(max(size, 2.0 * w))
        elif site == "junction":
            a, sa, b, sb = info["j"]
            if op == "body":
                ev = LineEvent(site, op, a, sa, size, side, other=(b, sb), group=group)
            else:
                ev = LineEvent(site, op, a, sa, size, side, other=(b, sb), group=group)
            if not free(b, sb, ext_of(op, size)):
                return None
            i, s = a, sa
        elif site == "corner":
            ev = LineEvent(site, op, i, info["s"], size, info["turn"], group=group)
            s = info["s"]
        else:
            if not (0.06 * N.L[i] < s < 0.94 * N.L[i]) or N.L[i] < 2.5 * ext_of(op, size):
                return None
            ev = LineEvent(site, op, i, s, size, side, group=group)
        if ev.site != "end" and not free(ev.line, ev.s, ext_of(op, ev.size)):
            return None
        xy, _ = N.point(ev.line, ev.s)
        if not clear(xy, ev.size):
            return None
        return ev

    if mode == "random":
        if like is None:
            raise ValueError("mode='random' needs like=")
        for ev0 in like:
            for _ in range(60):
                if ev0.site == "end":
                    cand = [(li, e) for (li, e, _, _) in N.ends if (li, e) not in used_ends]
                    if not cand:
                        break
                    li, e = cand[int(rng.integers(len(cand)))]
                    ev = build("end", ev0.op, li, 0.0, ev0.size, ev0.side, {"end": e}, -1)
                elif ev0.site == "loop" and N.loop_sites(used_loops):
                    cand = N.loop_sites(used_loops)
                    ev = build("loop", ev0.op, 0, 0.0, ev0.size, ev0.side, {"loop": cand[int(rng.integers(len(cand)))]}, -1)
                else:
                    k = int(rng.integers(len(N.P)))
                    i, s = int(N.own[k]), float(N.ss[k])
                    op = {"junction_mass": "bead", "fill_loop": "knot", "pupil": "knot",
                          "comma": "comma"}.get(ev0.op, ev0.op)
                    ev = build("interior", op, i, s, ev0.size, float(rng.choice([-1.0, 1.0])), {}, -1)
                if ev is not None:
                    commit(ev, N.point(ev.line, ev.s)[0])
                    break
        return out

    if n is None:
        n = max(1, int(round(g.density * N.total / w)))
    avail = {"end": bool(N.ends), "interior": True, "loop": bool(N.selfloops or N.faces), "junction": bool(N.junctions),
             "corner": bool(N.corners)}
    site_p = {k: v for k, v in g.site_p.items() if avail.get(k)}
    gid = 0
    stall = 0
    while len(out) < n and stall < 40 * n:
        k_group = 1
        if rng.random() < g.group_p and g.group_sizes:
            k_group = int(g.group_sizes[int(rng.integers(len(g.group_sizes)))])
        # first event of the group: a site drawn by the grammar
        site = _choice(site_p, rng)
        op = _choose_op(rng, g, site, None)
        size = _op_size(rng, g, op, w)
        side = float(rng.choice([-1.0, 1.0]))
        if site == "end":
            cand = [(li, e) for (li, e, _, _) in N.ends if (li, e) not in used_ends]
            if not cand:
                site_p.pop("end", None); stall += 1; continue
            li, e = cand[int(rng.integers(len(cand)))]
            ev = build(site, op, li, 0.0, size, side, {"end": e}, gid)
        elif site == "loop":
            cand = N.loop_sites(used_loops)
            if not cand:
                site_p.pop("loop", None); stall += 1; continue
            ev = build(site, op, 0, 0.0, size, side, {"loop": cand[int(rng.integers(len(cand)))]}, gid)
        elif site == "junction":
            a, sa, b, sb, _ = N.junctions[int(rng.integers(len(N.junctions)))]
            ev = build(site, op, a, sa, size, side, {"j": (a, sa, b, sb)}, gid)
        elif site == "corner":
            li, sc, sg = N.corners[int(rng.integers(len(N.corners)))]
            ev = build(site, op, li, sc, size, side, {"s": sc, "turn": sg}, gid)
        else:
            kk = int(rng.integers(len(N.P)))
            ev = build(site, op, int(N.own[kk]), float(N.ss[kk]), size, side, {}, gid)
        if ev is None:
            stall += 1
            continue
        commit(ev, N.point(ev.line, ev.s)[0])
        prev = ev
        direction = float(rng.choice([-1.0, 1.0]))
        # followers: responsive, along the line at the characteristic spacing
        for _m in range(k_group - 1):
            if len(out) >= n:
                break
            placed = False
            for _t in range(12):
                d = _sample_list(rng, g.spacing_w, 12.0, jitter=0.25) * w
                i = prev.line
                s = prev.s + direction * d
                if s < 0 or s > N.L[i]:
                    # off the line's end: hop to the nearest other line near there
                    x, _ = N.point(i, float(np.clip(s, 0, N.L[i])))
                    idx = [kk for kk in N.tree.query_ball_point(x, d) if N.own[kk] != i]
                    if not idx:
                        direction = -direction
                        continue
                    kk = idx[int(rng.integers(len(idx)))]
                    i, s = int(N.own[kk]), float(N.ss[kk])
                site2, info = N.site_at(i, s, used_ends)
                op2 = _choose_op(rng, g, site2, prev)
                if op2 is None:
                    continue
                lo, hi = _SIZE_CLIP_W.get(op2, (2.0, 10.0))
                r = _sample_list(rng, g.size_ratio, 0.0, jitter=0.0) + 0.15 * rng.standard_normal()
                size2 = float(np.clip(prev.size * math.exp(r), lo * w, hi * w))
                side2 = -prev.side if rng.random() < g.side_flip_p else prev.side
                ev2 = build(site2, op2, i, s, size2, side2, info, gid)
                if ev2 is None:
                    continue
                ev2.params["answers"] = prev.op
                commit(ev2, N.point(ev2.line, ev2.s)[0])
                prev = ev2
                placed = True
                break
            if not placed:
                break
        gid += 1
    return out


# --- applying events: the line itself changes ------------------------------

def _rg():
    from . import regime
    return regime


def _bump(s, c, rise, fall):
    """Asymmetric smooth bump in [0, 1]: smoothstep up over `rise` before c,
    down over `fall` after c."""
    rg = _rg()
    up = rg._smoothstep((s - (c - rise)) / max(rise, 1e-9))
    dn = 1.0 - rg._smoothstep((s - c) / max(fall, 1e-9))
    return np.where(s <= c, up, dn)


def _swell_at(st, c, size, rise, fall, peak=2.0):
    rg = _rg()
    s = rg.arclength(st.points, st.closed)[:len(st)]
    b = _bump(s, c, rise, fall)
    r = np.maximum(st.r, peak * b)
    mass = np.where(b > 0.02, np.maximum(size, st.mass * (st.r > 1.5)), st.mass)
    return replace_stroke(st, r=r, mass=mass)


def replace_stroke(st, **kw):
    from dataclasses import replace as _r
    return _r(st, **kw)


def _slice(st, i0, i1):
    rg = _rg()
    f = st.fill
    return rg.RegimeStroke(st.points[i0:i1], st.r[i0:i1], st.phi[i0:i1], st.W[i0:i1], st.mass[i0:i1], st.w_min,
                           False, None if f is None else f[i0:i1], st.meta)


def _child(root, direction, length, rng, *, r_root, W, mass, phi, curl=0.0, step=None, drop=0.0, wobble=0.08):
    """A thin stroke grown from `root` along `direction` (unit), curling by
    `curl` rad over its length; r falls from r_root to 0 over the first 45 %,
    optionally ending in a small drop (diameter `drop`)."""
    rg = _rg()
    step = step or max(length / 40, 0.05)
    m = max(int(length / step), 8)
    t = np.linspace(0, 1, m)
    h0 = math.atan2(direction[1], direction[0])
    h = h0 + curl * t ** 1.5 + np.cumsum(rng.normal(0, wobble / math.sqrt(m), m))
    d = np.column_stack([np.cos(h), np.sin(h)]) * (length / (m - 1))
    pts = root + np.vstack([[0, 0], np.cumsum(d[:-1], axis=0)])
    r = r_root * (1 - rg._smoothstep(t / 0.45))
    ms = np.full(m, mass)
    if drop > 0:
        x2 = (t - 0.93) / 0.09
        r = np.maximum(r, 2.0 * np.where(np.abs(x2) < 1, 0.5 * (1 + np.cos(np.pi * x2)), 0))
        ms = np.where(t > 0.6, drop, ms)
    return rg.RegimeStroke(pts, r, np.full(m, phi), np.full(m, W), ms, 0.0, False, None, {})


def _loop_pts(start, heading, radius, side, step, turns=1.0):
    n = max(int(math.ceil(2 * math.pi * radius * turns / step)), 12)
    t = np.linspace(0, 2 * math.pi * turns, n + 1)
    nrm = np.array([-math.sin(heading), math.cos(heading)]) * side
    c = start + nrm * radius
    a0 = math.atan2(start[1] - c[1], start[0] - c[0])
    ang = a0 + side * t
    return c + np.column_stack([np.cos(ang), np.sin(ang)]) * radius


def apply_events(lines, events: list[LineEvent], rng: np.random.Generator, *, w: float = 1.0,
                 phi: float = math.radians(55.0), W: float | None = None, grammar: EventGrammar | None = None):
    """The lines as RegimeStrokes with the events applied. Returns a list:
    one stroke per input line (meta: line, events, mark) followed by child
    strokes (shed ticks/drips, body exits, pupils, detached dots; meta:
    parent, event, mark). `mark` ids group strokes that render as ONE mark
    (unioned): a line with its children and the lines meeting in a junction
    mass. W: nib width (mm); default w × the reference thick/thin ratio
    drawn per line."""
    rg = _rg()
    arrs = _as_arrays(lines)
    strokes = []
    for i, p in enumerate(arrs):
        Wi = W if W is not None else w * _lognormal_q(rng, (grammar or DEFAULT_EVENT_GRAMMAR).nib_ratio)
        strokes.append(rg.make(p, 0.0, phi=phi, W=Wi, mass=2.6 * Wi, meta={"line": i, "events": []}))
    children = []
    parent = list(range(len(arrs)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    ramp_q = (1.11, 1.49, 2.88)          # reference: thin→thick 25–75 % in thick widths

    def nib_ramp(size):
        # ink width climbs 25 → 75 % over ≈ 0.22 of a smoothstep r ramp
        # (calibrated with regime.ink_width), so a measured ramp of q thick
        # widths needs an r ramp of q / 0.22 × size
        return _lognormal_q(rng, ramp_q) / 0.22 * size

    def compact_ramp(size):
        # beads / knots / junction masses: the reference's compact masses are
        # rounder than its nib transitions — same fitted shape, a quarter of the length
        return 0.25 * nib_ramp(size)

    by_line: dict = {}
    for ev in events:
        by_line.setdefault(ev.line, []).append(ev)
        if ev.other is not None:
            by_line.setdefault(ev.other[0], []).append(LineEvent(ev.site, "junction_peer" if ev.op != "body"
                                                                 else "body_peer", ev.other[0], ev.other[1],
                                                                 ev.size, ev.side, group=ev.group))
            parent[find(ev.other[0])] = find(ev.line)

    for i, evs in by_line.items():
        st = strokes[i]
        L = st.length()
        log = []
        # 1. r edits on the original geometry (and children rooted on it)
        for ev in sorted(evs, key=lambda e: e.s):
            if ev.site == "end" or ev.op == "knot":
                continue
            s, size = ev.s, ev.size
            x, tng = _Net.point_on(st.points, s)
            nrm = np.array([-tng[1], tng[0]]) * ev.side
            if ev.op == "bead":
                st = _swell_at(st, s, size, compact_ramp(size), compact_ramp(size))
            elif ev.op in ("junction_mass", "junction_peer"):
                # rounder than a bead: the mass sits where the lines meet
                st = _swell_at(st, s, size, 0.6 * compact_ramp(size), 0.6 * compact_ramp(size))
            elif ev.op == "vessel_mid":
                st = _swell_at(st, s, size, nib_ramp(size) * 0.6, compact_ramp(size) * 0.6)
            elif ev.op == "nib":
                # a stretch turns into a broad nib stroke (W ∝ size) and back,
                # over the fitted thin→thick ramp; r ≈ 1.3 pools a little so
                # the ribbon doesn't read as a hollow pipe
                Wn = 0.45 * size
                ramp = _lognormal_q(rng, rg.PROFILE_DEFAULTS["ramp_w_q"]) * Wn * 0.5
                sl = rg.arclength(st.points)[:len(st)]
                st = replace_stroke(st, W=np.where(np.abs(sl - s) < 1.6 * ramp, Wn, st.W))
                st = _swell_at(st, s, 0.9 * Wn, ramp, ramp * float(np.exp(0.3 * rng.standard_normal())),
                               peak=float(rng.uniform(1.15, 1.4)))
            elif ev.op == "comma":
                # thickens INTO the corner, holds through it, drops fast after
                # a comma: the head pools AT the corner (short rise), the tail
                # thins out along the outgoing leg over the fitted nib ramp
                st = _swell_at(st, s, size, compact_ramp(size) * 0.5, nib_ramp(size) * 0.3,
                               peak=float(rng.uniform(1.7, 2.0)))
            elif ev.op == "fill_loop":
                s0, s1 = ev.params["s0"], ev.params["s1"]
                sl = rg.arclength(st.points)[:len(st)]
                inside = rg._smoothstep((sl - s0) / max(0.35 * (s1 - s0), 1e-6))
                inside = inside * (1 - rg._smoothstep((sl - s1) / max(compact_ramp(size), 1e-6)))
                r = np.maximum(st.r, float(rng.uniform(1.6, 2.0)) * inside)
                st = replace_stroke(st, r=r, mass=np.where(inside > 0.02, size, st.mass))
            elif ev.op in ("body", "body_peer"):
                st = _swell_at(st, s, size, compact_ramp(size) * 1.3, compact_ramp(size) * 1.3)
                if ev.op == "body":
                    k = int(rng.integers(2, 5))
                    base = math.atan2(nrm[1], nrm[0])
                    lens = []
                    for m in range(k):
                        # exits move AWAY from the core, alternating sides, each answering the last
                        sd = 1 if m % 2 == 0 else -1
                        ang = base * 1.0 + (0 if sd > 0 else math.pi) + rng.normal(0, 0.55)
                        ln = (size * float(rng.uniform(1.3, 2.8)) if not lens
                              else lens[-1] * float(np.exp(rng.normal(-0.15, 0.3))))
                        ln = float(np.clip(ln, 0.8 * size, 3.2 * size))
                        lens.append(ln)
                        dvec = np.array([math.cos(ang), math.sin(ang)])
                        root = x + dvec * 0.15 * size
                        c = _child(root, dvec, ln, rng, r_root=1.8, W=0.5 * size, mass=0.8 * size, phi=float(st.phi[0]),
                                   curl=float(rng.normal(0, 0.7)))
                        c.meta.update({"parent": i, "event": "body_exit"})
                        children.append((i, c))
            elif ev.op == "comb":
                k = int(rng.integers(1, 4))
                sp = max(0.35 * size, 1.4 * w)
                ang0 = float(rng.uniform(0.9, 1.6))
                for m in range(k):
                    xm, tm = _Net.point_on(st.points, s + (m - (k - 1) / 2) * sp)
                    nm = np.array([-tm[1], tm[0]]) * ev.side
                    dvec = math.cos(ang0) * tm + math.sin(ang0) * nm
                    ln = size * float(rng.uniform(0.55, 1.0))
                    c = _child(xm, dvec, ln, rng, r_root=1.3, W=1.3 * w, mass=1.4 * w, phi=float(st.phi[0]))
                    c.meta.update({"parent": i, "event": "tick"})
                    children.append((i, c))
            elif ev.op == "drip":
                st = _swell_at(st, s, 0.8 * size, compact_ramp(0.5 * size), compact_ramp(0.5 * size), peak=1.6)
                c = _child(x, np.array([0.0, 1.0]), size * float(rng.uniform(1.0, 1.8)), rng, r_root=1.6,
                           W=0.4 * size, mass=0.6 * size, phi=float(st.phi[0]), drop=0.35 * size, wobble=0.04)
                c.meta.update({"parent": i, "event": "drip"})
                children.append((i, c))
            elif ev.op == "pupil":
                cen = np.asarray(ev.params["centre"])
                sl = rg.arclength(st.points)[:len(st)]
                band = (sl >= ev.params["s0"]) & (sl <= ev.params["s1"])
                cand = np.flatnonzero(band)
                j = int(cand[int(rng.integers(len(cand)))]) if len(cand) else int(np.argmin(np.abs(sl - s)))
                root = st.points[j]
                tgt = cen + rng.normal(0, 0.15 * size, 2)
                dvec = tgt - root
                dl = float(np.linalg.norm(dvec))
                if dl > 1e-6:
                    c = _child(root, dvec / dl, dl, rng, r_root=0.0, W=0.5 * w, mass=size, phi=float(st.phi[0]),
                               curl=float(rng.choice([-1, 1]) * rng.uniform(0.8, 1.6)), wobble=0.03)
                    c = replace_stroke(c, r=2.0 * rg._smoothstep((np.linspace(0, 1, len(c)) - 0.55) / 0.4))
                    c.meta.update({"parent": i, "event": "pupil"})
                    children.append((i, c))
            log.append(ev.op)
        # 2. knots: the line makes a small loop that fills (geometry insert), from the far end back
        for ev in sorted([e for e in evs if e.op == "knot"], key=lambda e: -e.s):
            sl = rg.arclength(st.points)[:len(st)]
            j = int(np.clip(np.searchsorted(sl, ev.s), 2, len(st) - 3))
            _, tng = _Net.point_on(st.points, ev.s)
            h = math.atan2(tng[1], tng[0])
            rad = 0.5 * ev.size * float(rng.uniform(0.6, 0.9))
            step = max(rad / 8, 0.05)
            loop = _loop_pts(st.points[j], h, rad, ev.side, step)[1:-1]
            g = np.linspace(0, 1, len(loop))
            amount = float(rng.uniform(0.7, 1.0))
            rl = 2.0 * amount * rg._smoothstep(g / 0.6)
            a = _slice(st, 0, j + 1)
            b = _slice(st, j, len(st))
            # rise into the knot along the incoming line, fall along the outgoing one
            sa = rg.arclength(a.points)[:len(a)]
            a = replace_stroke(a, r=np.maximum(a.r, 1.0 * rg._smoothstep((sa - (sa[-1] - compact_ramp(ev.size)))
                                                                          / max(compact_ramp(ev.size), 1e-6))))
            sb = rg.arclength(b.points)[:len(b)]
            b = replace_stroke(b, r=np.maximum(b.r, 2.0 * amount * (1 - rg._smoothstep(sb / max(compact_ramp(ev.size), 1e-6)))),
                               mass=np.where(sb < compact_ramp(ev.size), 2.2 * rad, b.mass))
            mid = rg.RegimeStroke(loop, rl, np.full(len(loop), st.phi[j]), np.full(len(loop), st.W[j]),
                                  np.full(len(loop), 2.2 * rad * amount), st.w_min, False, None, {})
            st = rg.concat(rg.concat(a, mid), b)
            log.append("knot")
        # 3. ends (start end first, via reversal)
        for ev in sorted([e for e in evs if e.site == "end"], key=lambda e: e.end):
            rev = ev.end == 0
            cur = rg.reverse(st) if rev else st
            size = ev.size
            Wl = float(np.median(cur.W))
            cur, kids = _end_op(cur, ev, rng, w, Wl, nib_ramp, compact_ramp, grammar)
            st = rg.reverse(cur) if rev else cur
            for c in kids:
                c.meta.update({"parent": i, "event": ev.op})
                children.append((i, c))
            log.append(ev.op)
        st.meta["events"] = log
        strokes[i] = st
    for k, st in enumerate(strokes):
        st.meta["line"] = k
        st.meta.setdefault("events", [])
        st.meta["mark"] = find(k)
    out = list(strokes)
    for i, c in children:
        c.meta["mark"] = find(i)
        out.append(c)
    return out


def _tail_W(st, s_from: float, value: float):
    """Nib width `value` from arc length s_from on (the rest of the line keeps its W)."""
    rg = _rg()
    sl = rg.arclength(st.points)[:len(st)]
    return replace_stroke(st, W=np.where(sl >= s_from, value, st.W))


def _end_op(st, ev: LineEvent, rng, w, Wl, nib_ramp, compact_ramp, g=None):
    """Apply an end event to the LAST point of st. Returns (stroke, children)."""
    rg = _rg()
    size = ev.size
    L = st.length()
    if ev.op == "drop":
        # the end pools: a short rise along the line (compact), then the drop
        pre = min(compact_ramp(size), 0.3 * L)
        st = rg.thicken(st, at=max(0.0, 1 - pre / L), ramp=pre, to=float(rng.uniform(0.3, 0.9)))
        return rg.terminal_drop(st, kind="drop", size=size), []
    if ev.op == "lozenge":
        pre = min(nib_ramp(0.6 * size), 0.45 * L)
        st = rg.thicken(_tail_W(st, L - pre - 0.5 * size, 0.7 * size), at=max(0.0, 1 - pre / L), ramp=pre * 0.8)
        return rg.terminal_drop(st, kind="lozenge", size=0.6 * size), []
    if ev.op in ("hook", "ring", "block"):
        amount = {"hook": float(rng.uniform(0.4, 0.6)), "ring": 0.0, "block": 1.0}[ev.op]
        rad = 0.5 * size * (0.55 if ev.op == "block" else 0.75)
        if amount > 0:
            pre = min(compact_ramp(size), 0.3 * L)
            st = rg.thicken(_tail_W(st, L - pre - 0.5 * size, max(0.45 * size, 1.5 * w)),
                            at=max(0.0, 1 - pre / L), ramp=pre, to=0.6 * amount + 0.2)
        return rg.close_fill(st, radius=rad, amount=amount, side=ev.side), []
    if ev.op == "vessel":
        Lv = min(size, 0.5 * L)
        at = max(0.0, 1 - Lv / L)
        sl = rg.arclength(st.points)[:len(st)]
        Wv = np.where(sl >= at * L, 0.22 * size, st.W)
        st = replace_stroke(st, W=Wv, mass=np.where(sl >= at * L, 0.35 * size, st.mass))
        return rg.swell(st, at=at, kind="vessel", size=0.35 * size), []
    if ev.op == "eye":
        return rg.eye(st, radius=0.5 * size, pupil=0.32 * size, side=ev.side), []
    if ev.op == "detached":
        # the line stops; a dot continues it after the calligraphic gap
        g = g or DEFAULT_EVENT_GRAMMAR
        u, h = rg._tangent_end(st.points, 2 * w)
        gap = float(np.clip(_sample_list(rng, g.gap_ratio, 1.0, jitter=0.1), 0.3, 3.0)) * size
        h2 = h + rng.normal(0, 0.35)
        d = np.array([math.cos(h2), math.sin(h2)])
        c0 = st.points[-1] + d * (gap + 0.5 * size)
        ln = 0.45 * size
        pts = c0 + np.outer(np.linspace(-0.5, 0.5, 12) * ln, d)
        dot = rg.make(pts, 2.0, phi=float(st.phi[-1]), W=0.5 * size, mass=0.75 * size)
        dot.meta["detached"] = True
        return st, [dot]
    raise ValueError(f"unknown end op {ev.op!r}")


def _point_on(points: np.ndarray, s: float):
    seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
    sl = np.concatenate([[0.0], np.cumsum(seg)])
    s = float(np.clip(s, 0, sl[-1]))
    x = np.array([np.interp(s, sl, points[:, 0]), np.interp(s, sl, points[:, 1])])
    j = int(np.clip(np.searchsorted(sl, s), 1, len(points) - 1))
    k0 = int(np.searchsorted(sl, s - 1.0))
    k1 = int(np.searchsorted(sl, s + 1.0))
    a, b = points[max(min(k0, j - 1), 0)], points[min(max(k1, j), len(points) - 1)]
    d = b - a
    return x, d / (np.linalg.norm(d) + 1e-12)


_Net.point_on = staticmethod(_point_on)


def place_events(lines, rng: np.random.Generator, grammar: EventGrammar | None = None, *, w: float = 1.0,
                 n: int | None = None, phi: float = math.radians(55.0), W: float | None = None):
    """Signs as line events: plan with the grammar (WHERE + WHICH operator)
    and apply them, so the line itself changes. Returns RegimeStrokes (see
    `apply_events`): the input lines edited in place of stamps, plus child
    strokes grown from them; the only strokes not connected to their line
    are the rare detached dots (meta["detached"])."""
    evs = plan_events(lines, rng, grammar, w=w, n=n)
    return apply_events(lines, evs, rng, w=w, phi=phi, W=W, grammar=grammar)


def render_events(strokes, pen: float = 0.35) -> list[np.ndarray]:
    """Plotter polylines: strokes grouped by meta["mark"], each group rendered
    as one mark (regime.render unions the ribbons). Lines without events and
    without children are drawn as their own centreline."""
    rg = _rg()
    groups: dict = {}
    for st in strokes:
        groups.setdefault(st.meta.get("mark", id(st)), []).append(st)
    out = []
    for _, sts in sorted(groups.items(), key=lambda kv: str(kv[0])):
        if all(float(s.r.max()) <= 0.0 for s in sts) and len(sts) == 1:
            out.append(np.asarray(sts[0].points, float))
            continue
        out += rg.render(sts, pen)
    return out


DEFAULT_EVENT_GRAMMAR = EventGrammar(
    # fitted 2026-10-16 by experiments/signs_study.py `events_grammar` (deciles
    # of the sample lists; the study's .local/gesture/out/signs_events/
    # event_grammar.json holds the full samples). 25 read reference forms +
    # 16 masses with ≥ 3 exits; detached-dot gap from 299 calligraphic dots
    # on 11 generative-allowed sheets; body share = design (Oehlen).
    site_p={'loop': 0.0732, 'end': 0.3171, 'interior': 0.1707, 'corner': 0.0488, 'junction': 0.3902},
    op_p={'loop': {'pupil': 1.0}, 'end': {'drop': 0.3077, 'detached': 0.2308, 'lozenge': 0.0769, 'vessel': 0.0769, 'block': 0.0769, 'ring': 0.0769, 'hook': 0.1538}, 'interior': {'knot': 0.2514, 'bead': 0.2514, 'vessel_mid': 0.1257, 'comb': 0.1257, 'nib': 0.1257, 'body': 0.12}, 'corner': {'comma': 1.0}, 'junction': {'junction_mass': 0.88, 'body': 0.12}},
    size_w={'pupil': [10.277, 10.277, 17.393], 'drop': [3.479, 4.743, 5.534, 6.325], 'detached': [1.365, 2.237, 2.364, 2.518, 2.716, 2.957, 3.185, 3.757, 4.292], 'lozenge': [5.218], 'knot': [9.487, 15.021], 'comma': [5.534, 21.345], 'bead': [2.363, 2.52, 2.596, 2.705, 3.082, 3.452, 3.837, 4.567, 7.787], 'vessel': [63.246], 'vessel_mid': [19.764], 'block': [12.175], 'ring': [9.961], 'comb': [7.589], 'hook': [7.115, 11.384], 'nib': [22.136], 'junction_mass': [2.003, 2.141, 2.484, 2.62, 2.975, 4.522, 5.33, 7.695, 9.936], 'body': [6.0, 8.0, 10.0, 13.0]},
    density=0.009, group_p=0.25, group_sizes=[2, 3, 3, 5],
    spacing_w=[6.743, 6.817, 10.001, 10.238, 12.76, 12.873, 13.083, 16.719, 18.315], size_ratio=[-1.342, -1.153, -0.748, -0.514, -0.201, 0.272, 0.623, 1.153, 1.572],
    gap_ratio=[0.231, 0.347, 0.488, 0.655, 0.925, 1.238, 1.811, 2.536, 3.584], nib_ratio=(3.014, 3.349, 4.134),
    sources=["default (deciles of the 2026-10-16 fit)"],
    meta={"dot_size_w": [0.91, 1.491, 1.576, 1.678, 1.811, 1.971, 2.123, 2.505, 2.861], "body_share_design": 0.12})
