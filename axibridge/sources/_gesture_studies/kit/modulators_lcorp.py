# FROZEN from research commit ecd64f8: tools/gesture/gesture/kit/modulators_lcorp.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Round 15, thread B (`lcorp`): the zoom as a modulator, applied style, and
aware overlaps.

- modulator `lcorp_zoom_mod`  any voice's marks through the zoom (the voice
  wrapper): each mark's own heading is re-integrated at z(τ) with the level
  of detail of `voices_lcorp.magnify_lod`, then fitted back into the mark's
  own bounding box. Channels follow the source position (remap).
- modulator `lcorp_style`     apply style: each mark keeps its coarse course
  (heading low-passed at `split` mm) and takes its fine bends whole from a
  hand's chain (heading high-passed at the same split). The two bands are
  never mixed at one scale.
- modulator `lcorp_aware`     overlaps that know about each other (Ian on
  rzoom-1: "replaying or intermingling (shouldn't be obvious)"):
    depth     zoom read as nearness: where two passes come within `gap`, the
              farther one (lower z) is interrupted around the nearer; passes at
              equal zoom simply cross (the far twists touching themselves are
              texture, not overlap).
    sympathy  where a pass runs over or along a FARTHER pass, it takes on that
              pass's own twist (the far pass's lateral wiggle, copied across
              with a soft falloff): alongside, it replays it; across, it
              shivers once. The far pass is untouched.
    both      sympathy, then depth.
  `aware_marks` (pure) does the work on any list of marks, so arrangers can
  apply it across parts.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

from .core import Mark, P, modulator
from .voices_lcorp import (SHAPES, _len, hand_chain, profile, restyle_theta, turn_length, zoom_line,
                           zoom_shape)
from .voices_rzoom import shrink_fit

AWARE_MODES = ("depth", "sympathy", "both")


# ---------------------------------------------------------------------------
# the zoom as a modulator
# ---------------------------------------------------------------------------

@modulator("lcorp_zoom_mod", params=[
    P("schedule", "choice", "push", "zoom schedule over the drawn line", choices=SHAPES),
    P("recur", "int", 2, "pushes / pulses / breaths", min=1, max=8),
    P("zoom", "float", 12.0, "largest magnification", min=1.0, max=64.0),
    P("pace", "float", 0.5, "0: keyed to the drawn line; 1: keyed to the source", min=0.0, max=1.0),
    P("far_turn_mm", "float", 1.2, "a quarter-turn at z = 1 before refitting, mm", min=0.2, max=20.0),
    P("lod", "float", 0.8, "camera resolution in far quarter-turns", min=0.0, max=3.0),
    P("reveal", "float", 0.4, "finer detail shown when zoomed", min=0.0, max=1.0),
    P("valley", "float", 0.0, "course straightening, quarter-turns (0 = the mark's own headings)",
      min=0.0, max=400.0),
    P("min_mm", "float", 20.0, "marks shorter than this pass unchanged", min=0.0, max=1000.0),
], doc="any voice's marks zooming in and out along themselves, refitted into their own bounding box")
def lcorp_zoom_mod(ctx, marks, *, schedule, recur, zoom, pace, far_turn_mm, lod, reveal, valley, min_mm):
    out = []
    for i, m in enumerate(marks):
        if m.length() < min_mm or len(m) < 8:
            out.append(m)
            continue
        g = zoom_shape(schedule, 4000, ctx.rng("schedule", i), recur)
        r = zoom_line(m.points, g, zoom=zoom, far_turn_mm=far_turn_mm, pace=pace, max_mm=20000.0,
                      valley=valley, lod=lod, reveal=reveal)
        lo, hi = m.points.min(axis=0), m.points.max(axis=0)
        pts, k, off = shrink_fit(r["points"], (lo[0], lo[1], hi[0] - lo[0], hi[1] - lo[1]), grow=True)
        s_new = np.clip(r["u_share"], 0, 1) * m.length()
        out.append(m.remap(s_new, points=pts, channels={"zoom": r["zoom"]}, meta={"lcorp_zoom": {"zoom": zoom}}))
    return out


# ---------------------------------------------------------------------------
# applied style
# ---------------------------------------------------------------------------

def apply_style(course: np.ndarray, style_q: np.ndarray, *, split_mm: float, style_turn_mm: float,
                amount: float = 1.0, step: float = 0.2, lod_mm: float = 0.0) -> np.ndarray:
    """course (mm): kept above split_mm. style_q (any units): its heading is
    rescaled so one of its quarter-turns spans style_turn_mm of the course,
    high-passed at split_mm, added. lod_mm > 0 smooths the style's heading
    at that paper scale first (corners finer than the pen open into arcs).
    End points are re-pinned to the course's (a slow linear correction)."""
    cr, th_c, h = profile(course, step)
    _, th0, h0 = profile(style_q, max(_len(style_q) / 20000.0, 1e-9))
    lt_s = turn_length(th0, h0)
    k = style_turn_mm / lt_s                                   # mm of course per style unit
    _, th_s, _ = profile(style_q, h / k)                       # style sampled at the course's step
    if lod_mm > 0:
        th_s = gaussian_filter1d(th_s, lod_mm / h, mode="nearest")
    th = restyle_theta(th_c, th_s, h=h, split=split_mm, amount=amount)
    pts = np.vstack([cr[:1], cr[0] + np.cumsum(h * np.column_stack([np.cos(th), np.sin(th)]), axis=0)])
    w = np.linspace(0, 1, len(pts))[:, None]
    return pts + w * (cr[-1] - pts[-1])


@modulator("lcorp_style", params=[
    P("source", "choice", "hand", "whose bends are applied: a hand's chain, or the far river stem's meanders",
      choices=("hand", "river")),
    P("hand", "ref", "hokusai", "source hand (source = hand)", kind="hand"),
    P("split_mm", "float", 12.0, "scale that divides the course (kept, above) from the bends (applied, below)",
      min=1.0, max=200.0),
    P("style_turn_mm", "float", 2.5, "the applied hand's quarter-turn on paper, mm", min=0.2, max=50.0),
    P("amount", "float", 1.0, "gain on the applied bends", min=0.0, max=2.0),
    P("lod_mm", "float", 0.4, "smooth the applied hand below this paper scale", min=0.0, max=5.0),
], doc="apply style: keep each mark's course, take its fine bends whole from a hand's chain")
def lcorp_style(ctx, marks, *, source, hand, split_mm, style_turn_mm, amount, lod_mm):
    if source == "river":
        from .arrangers_oehlen_found import FAR_STEMS, stem  # noqa: PLC0415
        q_river = stem(ctx, FAR_STEMS, "SB19", 0)[2]
    else:
        g = ctx.use("hand", hand)
    out = []
    for i, m in enumerate(marks):
        if m.length() < 2 * split_mm:
            out.append(m)
            continue
        if source == "river":
            q = q_river                 # cycled by restyle_theta if the course is longer than the stem
        else:
            need = m.length() / style_turn_mm * 1.3
            q, _ = hand_chain(g, ctx.rng("style", i), length_R=8.0)
            L = 8.0
            while _len(q) / max(_turn_len_units(q), 1e-9) < need and L < 1600:
                L *= 2
                q, _ = hand_chain(g, ctx.rng("style", i), length_R=L)
        pts = apply_style(m.points, q, split_mm=split_mm, style_turn_mm=style_turn_mm, amount=amount,
                          lod_mm=lod_mm)
        s_new = np.linspace(0, m.length(), len(pts))
        out.append(m.remap(s_new, points=pts, meta={"lcorp_style": {"source": source if source == "river" else hand,
                                                                   "split_mm": split_mm}}))
    return out


def _turn_len_units(q):
    _, th, h = profile(q, max(_len(q) / 20000.0, 1e-9))
    return turn_length(th, h)


# ---------------------------------------------------------------------------
# aware overlaps
# ---------------------------------------------------------------------------

def _resample_mark(m: Mark, step: float) -> Mark:
    return m.resampled(step) if m.length() > 3 * step else m


def aware_marks(marks: list[Mark], *, mode: str, gap: float = 0.9, reach: float = 4.0, minsep: float = 10.0,
                gain: float = 1.0, min_piece: float = 1.5, step: float = 0.25, tie: float = 0.15,
                tie_z: float = 0.0) -> tuple:
    """Overlaps that know about each other, across every mark given (self-
    overlaps and other lines alike). Returns (marks, log): log lists the
    contacts as {"kind", "at", "front", "back"} for a score.

    Nearness is `zoom` (channel; 1 when absent). tie_z > 1: passes of equal
    zoom that are both opened (z ≥ tie_z) cut too, the later in front (a
    spatial zoom field gives every pass at one place the same zoom). Two samples are different
    passes when they belong to different marks or lie ≥ minsep mm apart
    along the same mark."""
    ms = [_resample_mark(m, step) for m in marks]
    if not ms:
        return [], []
    ids = np.concatenate([np.full(len(m), i) for i, m in enumerate(ms)])
    pts = np.vstack([m.points for m in ms])
    ss = np.concatenate([m.arclength() for m in ms])
    zz = np.concatenate([np.asarray(m.channel("zoom", 1.0) if m.channel("zoom") is not None
                                    else np.ones(len(m))) for m in ms])
    lz = np.log(np.maximum(zz, 1.0))
    tree = cKDTree(pts)
    log = []

    def other(i, js):
        js = np.asarray(js, int)
        return js[(ids[js] != ids[i]) | (np.abs(ss[js] - ss[i]) >= minsep)]

    if mode in ("sympathy", "both"):
        hp_all = np.vstack([_lateral(m) for m in ms])
        new = []
        for mi, m in enumerate(ms):
            p = m.points
            if len(p) < 6:
                new.append(m)
                continue
            # this mark's normals
            d = np.gradient(p, axis=0)
            t = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
            nrm = np.column_stack([-t[:, 1], t[:, 0]])
            disp = np.zeros(len(p))
            base = sum(len(x) for x in ms[:mi])
            for k in range(len(p)):
                gi = base + k
                js = other(gi, tree.query_ball_point(p[k], reach))
                if not len(js):
                    continue
                js = js[lz[js] < lz[gi] - tie]                   # only farther passes are heard
                if not len(js):
                    continue
                rel = pts[js] - p[k]
                along = np.abs(rel @ t[k])                  # the far sample straight across, not the nearest
                jj = int(np.argmin(along))                  # (the nearest is biased to the far wiggle's crests)
                if along[jj] > 2 * step:                    # nothing straight across: no wiggle to hear
                    continue
                j = int(js[jj])
                w = 0.5 * (1 + math.cos(math.pi * min(abs(float(rel[jj] @ nrm[k])) / reach, 1.0)))
                disp[k] = w * float(np.dot(hp_all[j], nrm[k]))
            disp = gaussian_filter1d(disp, 0.8 / step, mode="nearest") * gain        # no kinks: the twist arrives smoothly
            if np.any(disp != 0):
                hit = np.flatnonzero(np.abs(disp) > 0.05)
                if len(hit):
                    log.append({"kind": "intermingle", "at": p[hit[len(hit) // 2]].tolist(), "front": mi,
                                "back": None, "s": [float(m.arclength()[hit[0]]), float(m.arclength()[hit[-1]])]})
            new.append(m.evolve(points=p + disp[:, None] * nrm))
        ms = new
        pts = np.vstack([m.points for m in ms])
        tree = cKDTree(pts)

    if mode in ("depth", "both"):
        hidden = np.zeros(len(pts), bool)
        for gi in range(len(pts)):
            js = other(gi, tree.query_ball_point(pts[gi], gap))
            if not len(js):
                continue
            front = lz[js] > lz[gi] + tie            # equal zoom never cuts: a twist touching itself is texture ...
            if tie_z > 1:                            # ... unless both passes are opened (z ≥ tie_z): the later in front
                both_open = (zz[gi] >= tie_z) & (zz[js] >= tie_z) & (np.abs(lz[js] - lz[gi]) <= tie)
                front = front | (both_open & (js > gi))
            if np.any(front):
                hidden[gi] = True
        out = []
        base = 0
        for mi, m in enumerate(ms):
            hm = hidden[base:base + len(m)]
            base += len(m)
            if not hm.any():
                out.append(m)
                continue
            s = m.arclength()
            runs = _runs(~hm)
            for a, b in runs:
                if s[b - 1] - s[a] >= min_piece:
                    out.append(m.remap(s[a:b]))
            cuts = _runs(hm)
            for a, b in cuts:
                log.append({"kind": "mask", "at": m.points[(a + b) // 2].tolist(), "front": None, "back": mi,
                            "s": [float(s[a]), float(s[b - 1])]})
        ms = out
    return ms, log


def _lateral(m: Mark, sigma_mm: float = 3.0) -> np.ndarray:
    """A pass's own wiggle: its points minus their 3 mm smoothing."""
    p = m.points
    s = m.arclength()
    if len(p) < 4:
        return np.zeros_like(p)
    stp = max(float(np.median(np.diff(s))), 1e-6)
    sm = np.column_stack([gaussian_filter1d(p[:, i], sigma_mm / stp, mode="nearest") for i in (0, 1)])
    return p - sm


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    m = np.r_[False, np.asarray(mask, bool), False]
    d = np.diff(m.astype(int))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


@modulator("lcorp_aware", params=[
    P("mode", "choice", "depth", "depth: the nearer pass (higher zoom) cuts the farther; sympathy: a pass takes "
      "on the twist of the farther pass it runs over or along; both", choices=AWARE_MODES),
    P("gap", "float", 0.9, "depth: half-width of the cut around the nearer pass, mm", min=0.1, max=6.0),
    P("reach", "float", 4.0, "sympathy: how far a pass hears the one beneath, mm", min=0.5, max=20.0),
    P("gain", "float", 1.0, "sympathy: how much of the far twist is taken on", min=0.0, max=3.0),
    P("minsep", "float", 10.0, "samples closer than this along one mark are the same pass, mm", min=1.0, max=100.0),
], doc="self-overlaps that know about each other: the nearer pass cuts the farther, or takes on its twist")
def lcorp_aware(ctx, marks, *, mode, gap, reach, gain, minsep):
    out, _ = aware_marks(list(marks), mode=mode, gap=gap, reach=reach, gain=gain, minsep=minsep)
    return out
