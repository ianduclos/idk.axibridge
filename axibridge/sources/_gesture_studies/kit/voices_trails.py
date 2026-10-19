# FROZEN from research commit f59eac4: tools/gesture/gesture/kit/voices_trails.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Trails and bodies (research round 11, exploration hands_trails, 2026-10-17).

- voice `trail_sheet`     a hand's WHOLE sheet: `grammar.generate_drawing` with the
                          hand's learned relations (joins, branches, near-ends),
                          several lines — where a trail hand keeps its branching
- voice `trail_brood`     a bark-beetle brood gallery as a voice: one mother line in
                          one hand, larval lines leaving it on both sides in another
                          hand, fanning toward the ends; each larval line is aged
                          (channel `age` 0→1) so the gallery renderer widens it
- renderer `trail_gallery` a line as a mine: the tunnel widens with age (the larva
                          grows), a frass line runs down its middle, and it ends in a
                          round chamber — a line swelling smoothly into a bead
- arranger `trail_specimen` the grid at one common scale + a scale bar (mm on the sheet)

Channels added: `age` (0 at a gallery's start → 1 at its end; trail_brood writes it,
trail_gallery reads it and falls back to arc length). Determinism: every draw comes
from np.random.default_rng(ctx.seed) or ctx.rng(tags).
"""
from __future__ import annotations

import math

import numpy as np

from ._research import grammar as gm
from ._research import hybrid as hy
from .arrangers_base import grid as _grid
from .core import Ink, Mark, P, arranger, channel_kind, fitted, renderer, voice

RESEARCH_SIZE = (1000.0, 1200.0)
channel_kind("age", "linear")


# ---------------------------------------------------------------------------
# voice: trail_sheet
# ---------------------------------------------------------------------------

@voice("trail_sheet", params=[
    P("hand", "ref", "lichtenberg", "the grammar", kind="hand"),
    P("relations", "choice", "learned", "learned: the hand's own joins / branches / near-ends | tree: every "
      "later line attaches to an earlier one", choices=("learned", "tree")),
    P("lines", "int", 0, "number of lines (0 = the hand's own ink budget)", min=0, max=80),
    P("ink", "float", 1.0, "ink budget × the hand's own (lines = 0 only)", min=0.2, max=4.0),
], doc="a hand's whole sheet: several lines with the hand's learned relations (joins, branches, near-ends)")
def trail_sheet(ctx, *, hand, relations, lines, ink):
    g = ctx.use("hand", hand)
    rng = np.random.default_rng(ctx.seed)
    kw = {"relations": relations}
    if lines:
        kw["n_strokes"] = int(lines)
    elif ink != 1.0:
        per = [d["ink"] for d in g.drawings if d.get("ink")] or [6.0]
        kw["ink"] = float(np.median(per)) * float(ink)
    import warnings  # noqa: PLC0415
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = gm.generate_drawing(g, rng, RESEARCH_SIZE, **kw)
    pts = [s.points for s in d.strokes if len(s.points) >= 2]
    if not pts:
        return []
    meta = {"voices": [hand], "library": [{"kind": "hand", "id": hand}], "relations": relations}
    return fitted(pts, ctx.box, [{"voice": np.zeros(len(p))} for p in pts], [dict(meta) for _ in pts])


# ---------------------------------------------------------------------------
# voice: trail_brood
# ---------------------------------------------------------------------------

def _resample(p: np.ndarray, n: int) -> np.ndarray:
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    t = np.linspace(0, s[-1], n)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def _rot(v: np.ndarray, a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return v @ np.array([[c, s], [-s, c]])


@voice("trail_brood", params=[
    P("mother", "ref", "bubble", "the mother gallery's hand", kind="hand"),
    P("larvae", "ref", "lichtenberg", "the larval galleries' hand", kind="hand"),
    P("mother_length", "float", 1.2, "mother gallery length, reference lengths", min=0.2, max=6.0),
    P("larva_length", "float", 0.3, "longest larval gallery, reference lengths", min=0.05, max=3.0),
    P("count", "int", 14, "larval galleries (both sides together)", min=1, max=60),
    P("fan", "float", 40.0, "how far the end larvae lean toward the ends, degrees", min=0.0, max=85.0),
    P("straighten", "float", 0.85, "mother gallery: 0 = as the hand drew it, 1 = its chord (beetles bore "
      "nearly straight; the hand then only wobbles it)", min=0.0, max=1.0),
], doc="a brood gallery: one mother line, larval lines leaving it on both sides and fanning, each aged so the "
       "gallery renderer widens it")
def trail_brood(ctx, *, mother, larvae, mother_length, larva_length, count, fan, straighten):
    gm_ = ctx.use("hand", mother)
    gl = ctx.use("hand", larvae)
    rng = np.random.default_rng(ctx.seed)
    st, _ = hy.drift_line([gm_], rng, total=float(mother_length), size=RESEARCH_SIZE)
    M = _resample(st.points, 400)
    # straighten by damping the hand's turning (arc length kept): heading deviations × (1 − straighten)
    d = np.diff(M, axis=0)
    step = np.linalg.norm(d, axis=1)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    th = th[0] + (th - th[0]) * (1.0 - straighten)
    M = np.vstack([M[:1], M[0] + np.cumsum(np.column_stack([np.cos(th), np.sin(th)]) * step[:, None], axis=0)])
    sM = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(M, axis=0), axis=1))]
    Lm = sM[-1]
    lines, chans, metas = [M], [{"voice": np.zeros(len(M)), "age": np.zeros(len(M))}], [
        {"voices": [mother, larvae], "role": "mother", "library": [{"kind": "hand", "id": mother},
                                                                   {"kind": "hand", "id": larvae}]}]
    r2 = ctx.rng("larvae")
    for k in range(count):
        side = 1.0 if k % 2 == 0 else -1.0
        q = (k // 2 + 0.5 + r2.uniform(-0.25, 0.25)) / max(math.ceil(count / 2), 1)   # position along mother
        q = float(np.clip(0.04 + 0.92 * q, 0.02, 0.98))
        x = q * Lm
        i = int(np.clip(np.searchsorted(sM, x), 1, len(M) - 1))
        p0 = M[i]
        tg = M[min(i + 1, len(M) - 1)] - M[i - 1]
        tg = tg / max(np.linalg.norm(tg), 1e-9)
        nrm = np.array([-tg[1], tg[0]]) * side
        env = 0.45 + 0.55 * math.sin(math.pi * q)                   # middle eggs laid first: longest
        Ll = float(larva_length) * env * r2.uniform(0.8, 1.15)
        sl, _ = hy.drift_line([gl], np.random.default_rng([ctx.seed, k]), total=max(Ll, 0.05),
                              size=RESEARCH_SIZE)
        P_ = sl.points - sl.points[0]
        if len(P_) < 3:
            continue
        lean = math.radians(fan) * (2 * q - 1)                      # end larvae lean toward the ends
        want = _rot(nrm[None, :], -side * lean)[0]
        have = P_[-1] / max(np.linalg.norm(P_[-1]), 1e-9)
        ang = math.atan2(want[1], want[0]) - math.atan2(have[1], have[0])
        P_ = _rot(P_, -ang) + p0
        lines.append(P_)
        sp = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))]
        chans.append({"voice": np.ones(len(P_)), "age": sp / max(sp[-1], 1e-9)})
        metas.append({"voices": [mother, larvae], "role": "larva", "q": round(q, 4), "side": int(side)})
    return fitted(lines, ctx.box, chans, metas)


# ---------------------------------------------------------------------------
# renderer: trail_gallery
# ---------------------------------------------------------------------------

def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def gallery_radius(age: np.ndarray, w0: float, w1: float, grow: float, chamber: float, ramp: float,
                   s: np.ndarray) -> np.ndarray:
    """Half-width along a gallery: w0 → w1 as age^grow, then (chamber > 0) a smooth
    swell over the last `ramp` chamber-diameters into the chamber's radius."""
    h = 0.5 * (w0 + (w1 - w0) * np.clip(age, 0, 1) ** grow)
    if chamber > 0:
        rc = 0.5 * chamber * w1
        L = s[-1]
        z = 1.0 - np.clip((L - s) / max(ramp * 2 * rc, 1e-9), 0, 1)       # 0 … 1 over the ramp
        h = np.maximum(h, h + (rc - h) * _smoothstep(z) ** 1.5)
    return h


def _arcl(p):
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


@renderer("trail_gallery", params=[
    P("pen", "float", 0.35, "pen width mm", min=0.05, max=3.0),
    P("w0", "float", 0.5, "gallery width at its start (the young larva), mm", min=0.0, max=20.0),
    P("w1", "float", 3.2, "gallery width at its end (the grown larva), mm", min=0.1, max=30.0),
    P("grow", "float", 1.6, "how late the widening comes (1 linear, >1 late)", min=0.3, max=5.0),
    P("chamber", "float", 2.2, "end chamber diameter × w1 (0 = none)", min=0.0, max=6.0),
    P("ramp", "float", 1.5, "length of the swell into the chamber, chamber diameters", min=0.2, max=6.0),
    P("fill", "choice", "chamber", "chamber: only the chamber is solid | none | late: solid from age `solid_from`",
      choices=("chamber", "none", "late")),
    P("solid_from", "float", 0.85, "fill = late: age from which the mine is solid", min=0.0, max=1.0),
    P("frass", "choice", "line", "line: the centre-line runs down the mine | wander: a frass line weaving "
      "inside it | none", choices=("line", "wander", "none")),
    P("mother_w", "float", 1.2, "trail_brood mother gallery width, mm (constant)", min=0.1, max=20.0),
    P("pitch", "float", 0.85, "solid fill inset spacing in pens", min=0.4, max=4.0),
], reach=lambda p: 0.5 * max(p["w1"] * max(p["chamber"], 1.0), p["mother_w"]) + 0.5 * p["pen"] + 0.5,
    doc="a line as a mine: widens with age, frass line inside, ends in a round chamber (line swelling into a bead)")
def trail_gallery(ctx, marks, *, pen, w0, w1, grow, chamber, ramp, fill, solid_from, frass, mother_w, pitch):
    from shapely.geometry import LineString, Point  # noqa: PLC0415
    from shapely.ops import unary_union  # noqa: PLC0415
    from .dev_beads import solid  # noqa: PLC0415
    out: list[Ink] = []
    for mi, m in enumerate(marks):
        pts = np.asarray(m.points)
        if len(pts) < 2:
            continue
        vid = m.meta.get("voice_id")
        if m.meta.get("role") == "scalebar":
            out.append(Ink(pts, pen=pen, meta={"voice": vid, "role": "scalebar"}))
            continue
        s = _arcl(pts)
        if s[-1] <= 1e-6:
            continue
        if m.meta.get("role") == "mother":
            g = LineString(pts).buffer(0.5 * mother_w, quad_segs=8)
            ring = np.asarray(g.exterior.coords)
            out.append(Ink(ring, closed=True, filled=False, pen=pen, meta={"voice": vid, "role": "mother"}))
            continue
        age = m.channel("age")
        age = s / s[-1] if age is None else np.asarray(age)
        h = gallery_radius(age, w0, w1, grow, chamber if fill != "none" or chamber > 0 else 0.0, ramp, s)
        # union of discs along the line, step ∝ local radius (smooth outline, cheap)
        step_s = np.maximum(0.45 * h, 0.15)
        xs, x = [], 0.0
        while x < s[-1]:
            xs.append(x)
            x += float(np.interp(x, s, step_s))
        xs.append(s[-1])
        xs = np.asarray(xs)
        cx, cy = np.interp(xs, s, pts[:, 0]), np.interp(xs, s, pts[:, 1])
        rr = np.maximum(np.interp(xs, s, h), 0.5 * pen)
        discs = [Point(a, b).buffer(r, quad_segs=10) for a, b, r in zip(cx, cy, rr)]
        geom = unary_union(discs).buffer(0.15, quad_segs=6).buffer(-0.15, quad_segs=6)
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        solid_geom = None
        if fill == "chamber" and chamber > 0:
            rc = 0.5 * chamber * w1
            solid_geom = Point(*pts[-1]).buffer(rc * 0.98, quad_segs=16).intersection(geom)
        elif fill == "late":
            j = age >= solid_from
            if j.sum() >= 2:
                k = np.flatnonzero(xs >= np.interp(solid_from, age, s))
                if len(k):
                    solid_geom = unary_union([discs[i] for i in k])
        for pg in polys:
            ring = np.asarray(pg.exterior.coords)
            out.append(Ink(ring, closed=True, filled=False, pen=pen, meta={"voice": vid, "role": "mine"}))
        if solid_geom is not None and not solid_geom.is_empty:
            sg = list(solid_geom.geoms) if solid_geom.geom_type == "MultiPolygon" else [solid_geom]
            for pg in sg:
                for p_, closed, filled in solid(pg, pen, pitch):
                    out.append(Ink(p_, closed=closed, filled=filled, pen=pen, meta={"voice": vid, "role": "chamber"}))
        if frass == "line":
            stop = s[-1] - (0.5 * chamber * w1 if chamber > 0 else 0.0)
            k = s <= max(stop, 0.5 * s[-1])
            if k.sum() >= 2:
                out.append(Ink(pts[k], pen=pen, meta={"voice": vid, "role": "frass"}))
        elif frass == "wander":
            rng = ctx.rng("frass", mi)
            xs2 = np.arange(0.0, s[-1], 0.4)
            if len(xs2) >= 2:
                c = np.column_stack([np.interp(xs2, s, pts[:, 0]), np.interp(xs2, s, pts[:, 1])])
                tg = np.gradient(c, axis=0)
                nv = np.column_stack([-tg[:, 1], tg[:, 0]]) / np.maximum(np.linalg.norm(tg, axis=1), 1e-9)[:, None]
                hh = np.interp(xs2, s, h)
                ph = np.cumsum(rng.uniform(0.25, 0.6, len(xs2)))
                off = 0.55 * np.maximum(hh - pen, 0) * np.sin(ph)
                k = xs2 <= s[-1] - (0.5 * chamber * w1 if chamber > 0 else 0.0)
                if k.sum() >= 2:
                    out.append(Ink((c + nv * off[:, None])[k], pen=pen, meta={"voice": vid, "role": "frass"}))
    return out


# ---------------------------------------------------------------------------
# arranger: trail_specimen
# ---------------------------------------------------------------------------

@arranger("trail_specimen", params=[
    P("cols", "int", 0, "columns (0 = auto)", min=0, max=12),
    P("gap", "float", 4.0, "gap between cells, mm", min=0.0, max=40.0),
    P("bar", "float", 10.0, "scale bar length, mm on the sheet", min=1.0, max=100.0),
], doc="one part per cell at one common scale, with a scale bar (mm) under the grid")
def trail_specimen(ctx, parts, *, cols, gap, bar):
    x0, y0, W, H = ctx.box
    zone = 6.0
    inner = ctx.with_box((x0, y0, W, H - zone))
    marks = _grid(inner, parts, cols=cols, scale="common", gap=gap)
    yb = y0 + H - 1.5
    pts = np.array([[x0, yb - 2.0], [x0, yb], [x0 + bar, yb], [x0 + bar, yb - 2.0]])
    meta = {"part": parts[0].index, "voice_id": "scalebar", "role": "scalebar", "bar_mm": bar}
    ch = {k: np.zeros(4) for k in marks[0].channels} if marks else {}
    return marks + [Mark(pts, ch, meta)]
