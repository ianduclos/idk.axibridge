"""Round 15, thread B (`lcorp`): gradual scaling as composition.

The zoom moved off the line and onto the sheet. A zoom FIELD z(x, y) lies
over the paper; each line is integrated step by step, and the zoom at each
step is read from where the pen is. So every line passing through the same
region opens there, and closes again when it leaves: a lens, a ramp, a band.
The scaling is a compositional move shared by a group of lines, not a
schedule private to one.

`lens_line` (pure) integrates one source heading through a field: paper step
ds, source advance du = ds / (c·z(p)), heading θ(u) seen at the level of
detail σ = res / (c·z**reveal) (voices_lcorp.magnify_lod's camera), plus a
course ψ that keeps the line in its lane (it turns back toward the lane, at
most 1/turn_mm rad per mm, only when it strays beyond `slack`).

Arranger `lcorp_lens`: every part is one line (its voice gives the source:
an `lcorp_zoom` voice spec is read for its source fields; any other voice's
first mark is used as the source line), laid in lanes across the sheet.
Records a `_score.Score`: the field as a layer (role "field", not inked),
every line as a layer, and a relation `exaggerate` from the field to each
line over the arc range where the line is opened (z ≥ √zoom).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from ._score import Score
from .core import Mark, P, arranger
from .voices_lcorp import _len, get_source, profile, river_far_turn, turn_length

FIELDS = ("lens", "twin", "ramp", "band")


def field_fn(kind: str, frame, *, cx: float, cy: float, radius: float, rng=None):
    """f(p) ∈ [0, 1] over the sheet (z = zoom ** f).
    lens  one soft disc centred (cx, cy) (shares of the frame), radius share of the short side
    twin  two discs on a diagonal through (cx, cy)
    ramp  grows left → right (smoothstep across the width)
    band  a vertical band at cx, half-width radius"""
    W, H = frame
    r = radius * min(W, H)
    if kind == "lens":
        c = np.array([cx * W, cy * H])
        return lambda p: math.exp(-0.5 * ((p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2) / r ** 2)
    if kind == "twin":
        c1 = np.array([(cx - 0.18) * W, (cy - 0.12) * H])
        c2 = np.array([(cx + 0.2) * W, (cy + 0.14) * H])
        return lambda p: max(math.exp(-0.5 * ((p[0] - c1[0]) ** 2 + (p[1] - c1[1]) ** 2) / r ** 2),
                             0.8 * math.exp(-0.5 * ((p[0] - c2[0]) ** 2 + (p[1] - c2[1]) ** 2) / (0.8 * r) ** 2))
    if kind == "ramp":
        return lambda p: float(np.clip((p[0] / W - 0.1) / 0.8, 0, 1)) ** 1.5
    if kind == "band":
        return lambda p: math.exp(-0.5 * ((p[0] - cx * W) / r) ** 2)
    raise ValueError(f"field must be one of {FIELDS}")


def straighten(th: np.ndarray, h: float, lt: float, valley: float) -> np.ndarray:
    if valley <= 0:
        return th
    low = gaussian_filter1d(th, valley * lt / h, mode="nearest")
    return th - low


def lens_line(th: np.ndarray, h: float, c: float, f, zoom: float, *, start, lane_y: float, box,
              res_mm: float, reveal: float = 0.4, step: float = 0.15, turn_mm: float = 30.0,
              slack: float = 12.0, max_steps: int = 60000, x_end: float | None = None) -> dict:
    """One source heading th (uniform step h, source units, valley removed)
    through the field f. Starts at `start` heading +x; ends when it reaches
    the box's right edge or the source runs out. Returns {"points", "zoom",
    "u" (source share)}."""
    x0, y0, w, hb = box
    x_end = x0 + w if x_end is None else x_end
    N = len(th)
    smax = res_mm / c / h
    levels = np.r_[0.0, np.geomspace(0.5, max(smax, 1.0) * 1.001, 12)]
    stack = np.vstack([th if s == 0 else gaussian_filter1d(th, s, mode="nearest") for s in levels])
    p = np.array(start, float)
    u = 0.0
    psi = 0.0
    pts, zs, us = [p.copy()], [1.0], [0.0]
    lim = step / turn_mm
    for _ in range(max_steps):
        z = zoom ** f(p)
        sig = res_mm / (c * z ** reveal) / h
        li = float(np.interp(sig, levels, np.arange(len(levels))))
        i0 = min(int(li), len(levels) - 2)
        fl = li - i0
        ui = min(u, N - 1.001)
        j = int(ui)
        fu = ui - j
        a = stack[i0, j] * (1 - fu) + stack[i0, j + 1] * fu
        b = stack[i0 + 1, j] * (1 - fu) + stack[i0 + 1, j + 1] * fu
        theta = a * (1 - fl) + b * fl
        # the lane: turn back only beyond the slack, and never at the edges' expense
        dy = p[1] - lane_y
        edge = min(p[1] - y0, y0 + hb - p[1])
        want = 0.0
        if abs(dy) > slack or edge < 10.0:
            want = -math.copysign(min(1.2, (abs(dy) - slack) / 25.0 + (0.6 if edge < 10 else 0.0)), dy)
        d = (want - psi + math.pi) % (2 * math.pi) - math.pi
        psi += max(-lim, min(lim, d * 0.25))
        hd = theta + psi
        p = p + step * np.array([math.cos(hd), math.sin(hd)])
        u += step / (c * z) / h
        pts.append(p.copy())
        zs.append(z)
        us.append(u / N)
        if p[0] >= x_end or u >= N - 1.001:
            break
        if not (y0 < p[1] < y0 + hb and x0 < p[0]):     # never clipped: a line that would leave stops inside
            pts.pop(); zs.pop(); us.pop()
            break
    return {"points": np.asarray(pts), "zoom": np.asarray(zs), "u": np.asarray(us)}


@arranger("lcorp_lens", params=[
    P("field", "choice", "lens", "where the sheet zooms: lens (one soft disc), twin (two discs), ramp (left → "
      "right), band (a vertical band)", choices=FIELDS),
    P("zoom", "float", 12.0, "magnification at the field's peak", min=1.0, max=48.0),
    P("cx", "float", 0.55, "field centre x (share of the width)", min=0.0, max=1.0),
    P("cy", "float", 0.5, "field centre y (share of the height)", min=0.0, max=1.0),
    P("radius", "float", 0.22, "field radius (share of the short side)", min=0.05, max=1.0),
    P("far_turn_mm", "float", 2.0, "a source quarter-turn on paper outside the field, mm", min=0.3, max=10.0),
    P("lod", "float", 0.8, "camera resolution in far quarter-turns", min=0.1, max=3.0),
    P("reveal", "float", 0.4, "finer detail shown when zoomed (σ ∝ 1/z**reveal)", min=0.0, max=1.0),
    P("valley", "float", 2.0, "course straightening, quarter-turns", min=0.5, max=100.0),
    P("slack", "float", 0.35, "how far a line may stray from its lane before turning back (share of the lane "
      "gap)", min=0.05, max=3.0),
    P("turn_mm", "float", 30.0, "tightest lane-keeping turn, mm", min=5.0, max=200.0),
    P("aware", "choice", "none", "overlaps between lines (modulators_lcorp.aware_marks): none, depth (the nearer "
      "pass cuts the farther), sympathy (a pass takes on the twist of the farther one beneath), both",
      choices=("none", "depth", "sympathy", "both")),
    P("lanes", "choice", "even", "even: lanes spread over the height; close: lanes packed toward the field "
      "centre", choices=("even", "close")),
], doc="gradual scaling as composition: a zoom field over the sheet, every line opening where it crosses it")
def lcorp_lens(ctx, parts, *, field, zoom, cx, cy, radius, far_turn_mm, lod, reveal, valley, slack, turn_mm, aware,
               lanes):
    x0, y0, w, h = ctx.box
    frame = ctx.frame
    f = field_fn(field, frame, cx=cx, cy=cy, radius=radius)
    n = len(parts)
    if lanes == "close":
        ys = y0 + h * (cy + (np.arange(n) - (n - 1) / 2) * min(0.8 / max(n, 1), 0.14))
    else:
        ys = y0 + h * (np.arange(n) + 0.5) / n
    gap = h / max(n, 1)
    score = Score()
    fid = score.layer("field", "lcorp_lens", params={"field": field, "zoom": zoom, "cx": cx, "cy": cy,
                                                     "radius": radius}, label="zoom field (not inked)")
    score.decide(field=field, zoom=zoom, lanes=lanes, n_lines=n, far_turn_mm=far_turn_mm, reveal=reveal,
                 density="middle: one line per lane, the field opens them")
    out = []
    for i, part in enumerate(parts):
        spec = part.spec["voice"]
        if spec["id"] == "lcorp_zoom":
            q, _, voices, meta = get_source(part.ctx("voice", "lcorp_zoom"), source=spec["source"],
                                            hand=spec["hand"], hands=spec["hands"], trail=spec["trail"],
                                            effector=spec["effector"], length_R=max(spec["length_R"], 600.0),
                                            river_start=spec["river_start"], river_share=spec["river_share"])
        else:
            ms = part.voice()
            q = max(ms, key=lambda m: m.length()).points
            voices, meta = ms[0].meta.get("voices", [spec["id"]]), {"source": spec["id"]}
        _, th0, h0 = profile(q, max(_len(q) / 20000.0, 1e-9))
        lt = turn_length(th0, h0)
        _, th, hs = profile(q, lt / 24)
        c = far_turn_mm / lt
        res = lod * far_turn_mm
        for _ in range(4):
            lt_vis = turn_length(gaussian_filter1d(th, max(res / c / hs, 0.5), mode="nearest"), hs, 0)
            c = far_turn_mm / lt_vis
        ths = straighten(th, hs, lt_vis, valley)
        rng = part.ctx("arrange", "lcorp_lens").rng("start", i)
        start = (x0 + rng.uniform(0.0, 0.08) * w, float(ys[i] + rng.uniform(-0.15, 0.15) * gap))
        r = lens_line(ths, hs, c, f, zoom, start=start, lane_y=float(ys[i]), box=ctx.box, res_mm=res,
                      reveal=reveal, slack=slack * gap, turn_mm=turn_mm,
                      x_end=x0 + w * (1 - rng.uniform(0.0, 0.08)))
        pts = r["points"]
        m = Mark(pts, {"zoom": r["zoom"], "u_src": r["u"], "voice": np.zeros(len(pts))},
                 {**meta, "voices": voices, "part": part.index, "lane": i,
                  "fit": {"scale": 1.0, "offset": [0.0, 0.0]}})
        m = part.modulate([m])
        out += m
        lid = score.layer("line", spec["id"], part=part.index, pen=None,
                          params={k: spec[k] for k in ("source", "hand", "trail") if k in spec},
                          label=meta.get("source", spec["id"]))
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        opened = np.flatnonzero(r["zoom"] >= math.sqrt(zoom))
        if len(opened):
            k = int(opened[np.argmax(r["zoom"][opened])])
            score.relate("exaggerate", fid, lid, at=pts[k], s=(s[opened[0]], s[opened[-1]]),
                         note=f"opened to z={r['zoom'][opened].max():.1f} while crossing the field")
    if aware != "none":
        from .modulators_lcorp import aware_marks  # noqa: PLC0415
        lids = {lay["part"]: lay["id"] for lay in score.layers if lay["role"] == "line"}
        parts_of = [int(m.meta.get("part", 0)) for m in out]
        # note: in a field, passes crossing at one place share their zoom, so depth / sympathy only act where a
        # line's own far twist meets an opened pass of another (aware_marks' tie_z would cut the opened tangle
        # into fragments: tried, rejected, stray marks)
        out, log = aware_marks(out, mode=aware)
        aid = score.layer("rule", "lcorp_aware", params={"mode": aware}, label="overlap awareness (not inked)")
        for e in log:
            if e["kind"] == "mask":
                score.relate("mask", aid, lids.get(parts_of[e["back"]], "?"), at=e["at"], s=e["s"],
                             note="cut where a nearer (more zoomed) pass crosses")
            else:
                score.relate("intermingle", aid, lids.get(parts_of[e["front"]], "?"), at=e["at"], s=e["s"],
                             note="takes on the twist of the farther pass beneath")
        score.decide(aware=aware)
    ctx.note("score", score.to_json())
    return out
