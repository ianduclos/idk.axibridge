# FROZEN from research commit 6f96418: tools/gesture/gesture/kit/voices_hdist.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 16, thread B (`hdist`): distinct hands under the zoom.

lcorp's zoom (round 15, `voices_lcorp`) made 33 of 44 hands "yield", but by
eye they shared one look: fine fuzz plus one or two big bends. Ian: "maybe you
smoothed it out too much?". Measured (experiments/hdist_measure.py), three
things together made the hands converge, and none of them is the hand:

1. **One far scale for every hand.** Every source was calibrated so one
   quarter-turn spans the river's far quarter-turn (2.2 mm, ≈ 1.6 mm after
   the fit). A hand's own character (its corners, curls, straight runs) lives
   at 7 to 30 mm per quarter-turn in its own drawings, so the far stretches
   showed every hand ~7× too small: the same fuzz.
2. **One camera resolution for every hand.** σ = res / (c·z^0.4) with
   res = 1.76 mm smoothed a zoomed stretch at res·z^0.6 on paper (≈ 12 mm at
   z = 24): every corner became an arc, every curl a bend.
3. **A zoom (×24) set by the river, not the hand.** Most hands span about
   three octaves of bends; ×24 pushes past them into the balloon.

This voice keeps lcorp's mechanism (heading θ(u) re-integrated at
ds = c·z·du, the same schedules, constant width) and sets the three things
from each hand's own scale ladder instead (`ladder`):

- far scale: the hand's finest real band (the scale at which smoothing first
  loses `fine_loss` of its turning) is drawn at `fine_mm` on paper, so the far
  view is the hand at a readable size, never fuzz;
- camera: the true camera at the pen's resolution (`res_mm`, reveal 1): no
  smoothing a pen could show;
- zoom: from the far quarter-turn to `top_mm` (the hand's own range on this
  sheet), never past it, capped at `zoom_max`.

Grammars stay whole: nothing is exaggerated or mixed; the hand's chain is
lcorp's `hand_chain` and its heading is never reshaped except by the valley
(course straightening, as lcorp, but at `valley` quarter-turns so loops, which
need 4 quarter-turns of steady turning, survive).

Voice `hdist_zoom`. Channels as lcorp_zoom: `zoom`, `u_src`, `voice`.
Meta `hdist`: the ladder and the scales chosen.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .core import Mark, P, voice
from .voices_lcorp import UNIT, _len, hand_chain, magnify_lod, profile, turn_length, zoom_measures
from .voices_rzoom import SHAPES, shrink_fit, zoom_shape

LADDER_K = np.arange(-5.0, 3.01, 0.25)   # octaves of ℓ_turn the ladder is read at


# ---------------------------------------------------------------------------
# the hand's own scale ladder
# ---------------------------------------------------------------------------

def ladder(th: np.ndarray, h: float, lt: float, *, fine_loss: float = 0.12, coarse_keep: float = 0.35) -> dict:
    """Where a heading's turning lives, in octaves of its quarter-turn ℓ_turn.

    T(k) = total turning with θ smoothed at σ = ℓ_turn·2**k, over T at the
    finest level. `k_fine`: the octave where smoothing has lost `fine_loss`
    of the turning (below it: nothing a pen needs); `k_coarse`: where only
    `coarse_keep` survives (above it: the course). `span` = k_coarse − k_fine,
    the hand's range in octaves: how far a zoom can open it before it is a
    balloon (smooth inside)."""
    T = []
    for k in LADDER_K:
        s = lt * 2.0 ** k / h
        ts = gaussian_filter1d(th, s, mode="nearest") if s >= 0.5 else th
        T.append(float(np.sum(np.abs(np.diff(ts)))))
    T = np.asarray(T) / max(T[0], 1e-12)
    k_fine = _cross(LADDER_K, T, 1.0 - fine_loss)
    k_coarse = _cross(LADDER_K, T, coarse_keep)
    return {"k_fine": round(k_fine, 3), "k_coarse": round(k_coarse, 3), "span": round(k_coarse - k_fine, 3),
            "T": np.round(T, 3).tolist()}


def _cross(k: np.ndarray, T: np.ndarray, level: float) -> float:
    """First octave where the falling curve T(k) drops to `level` (linear
    interpolation; the ends when it never does)."""
    below = np.flatnonzero(T <= level)
    if not len(below):
        return float(k[-1])
    i = int(below[0])
    if i == 0:
        return float(k[0])
    a, b = T[i - 1], T[i]
    f = (a - level) / max(a - b, 1e-12)
    return float(k[i - 1] + f * (k[i] - k[i - 1]))


def scales(lad: dict, *, fine_mm: float, top_mm: float, far_min_mm: float, far_max_mm: float,
           zoom_max: float) -> tuple[float, float]:
    """(far quarter-turn on paper, zoom) from the ladder: the finest band at
    fine_mm (clamped), the zoom opening the far quarter-turn to top_mm."""
    far = float(np.clip(fine_mm / 2.0 ** lad["k_fine"], far_min_mm, far_max_mm))
    zoom = float(np.clip(top_mm / far, 1.0, zoom_max))
    return far, zoom


# ---------------------------------------------------------------------------
# the zoom with the hand's own scales
# ---------------------------------------------------------------------------

def hand_zoom(q: np.ndarray, g: np.ndarray, *, fine_mm: float, top_mm: float, far_min_mm: float,
              far_max_mm: float, zoom_max: float, zoom: float, far_turn_mm: float, res_mm: float,
              reveal: float, valley: float, pace: float, drawn_mm: float, angle: float = 0.0,
              calib: str = "ladder", R_mm: float = 40.0, peak_fine_mm: float = 4.0, unit: float = UNIT,
              start: float = 0.0) -> dict:
    """q (source units, R = `unit`) zoomed at the hand's own scales. zoom /
    far_turn_mm > 0 override the choice. Returns magnify_lod's dict plus
    "hdist" (the ladder, far, zoom, c).

    calib "ladder": the finest band at fine_mm, the zoom to top_mm, the
    valley in quarter-turns (every hand starts equally readable; its
    curliness is still normalised away: one quarter-turn sets the scale).
    calib "R": one reference length of the hand (the size of its own
    drawings) is R_mm on paper at z = 1, so a curly hand turns many times
    in it and a sweeping one barely once (its curliness is kept); the
    zoom runs until the hand's finest band reaches peak_fine_mm (past it
    the hand has nothing smaller to show: a balloon); the valley is in
    reference lengths (the course is straightened only above one drawing
    of the hand, never inside it)."""
    _, th0, h0 = profile(q, max(_len(q) / 20000.0, 1e-9))
    lt = turn_length(th0, h0)
    r, th, h = profile(q, lt / 32.0)
    lad = ladder(th, h, lt)
    if calib == "R":
        far = R_mm * lt / unit
        finest = far * 2.0 ** lad["k_fine"]
        z = float(np.clip(peak_fine_mm / max(finest, 1e-9), 1.0, zoom_max))
        sv = valley * unit / h
    else:
        far, z = scales(lad, fine_mm=fine_mm, top_mm=top_mm, far_min_mm=far_min_mm, far_max_mm=far_max_mm,
                        zoom_max=zoom_max)
        sv = valley * lt / h
    if far_turn_mm > 0:
        far = far_turn_mm
    if zoom > 0:
        z = zoom
    if valley > 0:
        low = gaussian_filter1d(th, sv, mode="nearest")
        th = th - low + low.mean()
        r = np.vstack([[0.0, 0.0], np.cumsum(h * np.column_stack([np.cos(th), np.sin(th)]), axis=0)])
    c = far / lt
    out = magnify_lod(r, g, zoom=z, c=c, res_mm=res_mm, pace=pace, max_mm=drawn_mm, angle=angle,
                      reveal=reveal, step_mm=min(0.12, res_mm / 3), start=start, share=1.0 - start)
    out["turn_len"] = lt
    out["u_share"] = out["u"] / max(_len(r), 1e-9)
    out["hdist"] = {"calib": calib, "far_turn_mm": round(far, 3), "zoom": round(z, 2), "k_fine": lad["k_fine"],
                    "k_coarse": lad["k_coarse"], "span": lad["span"], "c_mm_per_unit": c}
    return out


# ---------------------------------------------------------------------------
# the line on the sheet: drawn length and course chosen so it fills its box
# ---------------------------------------------------------------------------

def _chain(gram, seed: int, length_R: float, memo: dict):
    if length_R not in memo:
        memo[length_R] = hand_chain(gram, np.random.default_rng(seed), length_R=length_R)[0]
    return memo[length_R]


def fitted_zoom(ctx, gram, g, *, valley: float, pace: float, drawn_mm: float, fill: float, width_fill: float = 0.0,
                **kw) -> tuple[dict, np.ndarray]:
    """hand_zoom with the drawn length and the course set for the box.

    `fill` > 0: a second pass sets the drawn length so the fit scale is
    about `fill` (the far scale then IS the sheet's scale, × fill). If the
    fitted line spans under `width_fill` of the box width, the course is
    straightened (valley × 0.6, up to twice): a course choice above the
    valley scale, never a change to the hand's bends below it. Returns
    (the hand_zoom dict, the source chain)."""
    memo: dict = {}
    box = ctx.box
    best = None
    for v in (valley, valley * 0.6, valley * 0.36) if (valley > 0 and width_fill > 0) else (valley,):
        length_R, target = 30.0, drawn_mm
        for attempt in range(8):
            q = _chain(gram, ctx.seed, length_R, memo)
            r = hand_zoom(q, g, valley=v, pace=pace, drawn_mm=target, **kw)
            if r["length_mm"] < 0.99 * target and length_R < 1600:
                length_R *= 2
                continue
            if fill > 0 and attempt < 7:
                _, k, _ = shrink_fit(r["points"], box, grow=True)
                if abs(k / fill - 1.0) > 0.08 and target == drawn_mm:
                    target = float(np.clip(target * k / fill, 200.0, 12000.0))
                    continue
            break
        pts, _, _ = shrink_fit(r["points"], box, grow=True)
        wf = float(np.ptp(pts[:, 0]) / max(box[2], 1e-9))
        r["hdist"]["valley"] = round(v, 2)
        r["hdist"]["width_fill"] = round(wf, 3)
        if best is None or wf > best[0]["hdist"]["width_fill"] + 1e-9:
            best = (r, q)
        if wf >= width_fill:
            break
    return best


def relay_zoom(ctx, grams, *, valley: float, pace: float, drawn_mm: float, **kw):
    """Hands in turn, each WHOLE and each at ITS OWN scales: hand k's chain
    zoomed with its own far scale and zoom (one push, far at both ends), the
    next hand continuing the heading where both are far. The handover is a
    change of grammar AND of scale ladder. Returns (a hand_zoom-like dict,
    the joined source points); "voice_pts" is the hand index per drawn point."""
    n = len(grams)
    pts_all, z_all, u_all, vc_pts = [], [], [], []
    srcs = []
    pos, head = np.zeros(2), 0.0
    info = []
    for i, gram in enumerate(grams):
        q, _ = hand_chain(gram, np.random.default_rng(ctx.seed * 7 + i), length_R=120.0)
        srcs.append(q)
        gi = zoom_shape("push", 4000, ctx.rng("relay", i), 1)
        gi = gi * np.sin(np.linspace(0, np.pi, len(gi))) ** 0.5          # far at both ends: the handover
        best = None
        for st in np.linspace(0.0, 0.6, 7):     # where in the hand's chain to begin: the one whose stretch,
            r = hand_zoom(q, gi, valley=valley, pace=pace, drawn_mm=drawn_mm / n, start=float(st), **kw)
            p = np.asarray(r["points"], float)   # turned to continue the heading, travels most along +x
            d0 = p[min(3, len(p) - 1)] - p[0]
            p = p - p[0]
            a = head - math.atan2(d0[1], d0[0])
            c_, s_ = math.cos(a), math.sin(a)
            p = p @ np.array([[c_, s_], [-s_, c_]]) + pos
            score = (p[-1, 0] - p[0, 0]) / max(float(np.ptp(p[:, 1])), 1.0)
            if best is None or score > best[0]:
                best = (score, r, p)
        _, r, p = best
        if pts_all:
            p, zz, uu = p[1:], r["zoom"][1:], r["u_share"][1:]
        else:
            zz, uu = r["zoom"], r["u_share"]
        pts_all.append(p)
        z_all.append(zz)
        u_all.append((i + np.clip(uu, 0, 1)) / n)
        vc_pts.append(np.full(len(p), float(i)))
        dd = p[-1] - p[-4]
        head = math.atan2(dd[1], dd[0])
        pos = p[-1]
        info.append({k: r["hdist"][k] for k in ("far_turn_mm", "zoom", "k_fine", "span")})
    P = np.vstack(pts_all)
    cen = P.mean(axis=0)
    ev = np.linalg.eigh(np.cov((P - cen).T))[1][:, -1]
    from .voices_rzoom import rotate  # noqa: PLC0415
    P = rotate(P, cen, kw.get("angle", 0.0) - math.degrees(math.atan2(ev[1], ev[0])))
    out = {"points": P, "zoom": np.concatenate(z_all), "u_share": np.concatenate(u_all),
           "length_mm": float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1))),
           "turn_len": float(np.mean([turn_length(*profile(q, _len(q) / 20000)[1:]) for q in srcs])),
           "hdist": {"far_turn_mm": info[0]["far_turn_mm"], "zoom": max(x["zoom"] for x in info),
                     "k_fine": info[0]["k_fine"], "span": info[0]["span"], "relay": info},
           "voice_pts": np.concatenate(vc_pts)}
    return out, np.vstack(srcs)


@voice("hdist_zoom", params=[
    P("source", "choice", "hand", "hand: one hand's long chain; relay: hands in turn, each whole",
      choices=("hand", "relay")),
    P("hand", "ref", "hokusai", "source hand", kind="hand"),
    P("hands", "refs", ["hokusai", "matisse"], "relay: the hands in turn", kind="hand", min_len=1, max_len=6),
    P("schedule", "choice", "push", "zoom schedule over the drawn line (as lcorp_zoom; a relay always gives "
      "each hand one push, far at both ends, so every handover falls where both hands are far)",
      choices=SHAPES),
    P("recur", "int", 3, "pushes / pulses / breaths", min=1, max=8),
    P("calib", "choice", "R", "far scale: ladder (the finest band readable; one quarter-turn sets the "
      "scale) or R (one reference length of the hand = R_mm: its curliness kept)", choices=("ladder", "R")),
    P("R_mm", "float", 80.0, "calib R: one reference length of the hand on paper at z = 1, mm", min=5.0,
      max=400.0),
    P("peak_fine_mm", "float", 4.0, "calib R: the zoom stops when the hand's finest band reaches this, mm",
      min=0.5, max=40.0),
    P("fine_mm", "float", 0.8, "the hand's finest real band drawn at this size at z = 1, mm (sets the far "
      "scale per hand: the far view is the hand readable, never fuzz)", min=0.3, max=8.0),
    P("top_mm", "float", 50.0, "the zoomed quarter-turn, mm: the zoom opens the far quarter-turn to this "
      "(sets the zoom per hand)", min=5.0, max=200.0),
    P("far_min_mm", "float", 2.2, "far quarter-turn floor, mm (lcorp's one far scale was 2.2)", min=0.5,
      max=20.0),
    P("far_max_mm", "float", 8.0, "far quarter-turn ceiling, mm", min=2.0, max=40.0),
    P("zoom_max", "float", 24.0, "zoom ceiling (lcorp's one zoom)", min=1.0, max=64.0),
    P("zoom", "float", 0.0, "fixed zoom (0 = the hand's own, from its ladder)", min=0.0, max=64.0),
    P("far_turn_mm", "float", 0.0, "fixed far quarter-turn, mm (0 = the hand's own)", min=0.0, max=40.0),
    P("res_mm", "float", 0.45, "camera resolution on paper, mm, the same at every zoom (reveal 1): the pen",
      min=0.1, max=4.0),
    P("reveal", "float", 1.0, "1: the true camera (detail down to res_mm at every zoom); lcorp used 0.4 "
      "with a 1.76 mm camera", min=0.0, max=1.0),
    P("valley", "float", 6.0, "calib ladder: straighten the course above this many quarter-turns (lcorp: 4, "
      "which unrolls loops; 0 = the hand's own drift)", min=0.0, max=400.0),
    P("valley_R", "float", 1.0, "calib R: straighten the course above this many reference lengths (above "
      "one drawing of the hand, never inside it; 0 = the hand's own drift)", min=0.0, max=40.0),
    P("pace", "float", 0.5, "0: zoom keyed to the drawn line; 1: keyed to the source", min=0.0, max=1.0),
    P("angle", "float", 0.0, "principal axis angle, deg", min=-180.0, max=180.0),
    P("drawn_mm", "float", 1500.0, "drawn length before fitting, mm", min=100.0, max=20000.0),
    P("span", "float", 0.8, "straighten the course (valley × 0.6, up to twice) until the line spans this share "
      "of its box's width (0 = never: the hand's own course at `valley`; straightening makes hands travel "
      "alike, the river's way)", min=0.0, max=1.0),
    P("fill", "float", 1.0, "two passes: the second sets the drawn length so the fit scale is about this "
      "(1: the far scale is the scale on the sheet; lower: a longer line, fitted smaller; 0 = one pass)",
      min=0.0, max=1.0),
], doc="a hand zoomed at its OWN scales (far scale, zoom and camera from its scale ladder), constant width, "
       "free course: the zoom shows each hand's range instead of one river-set range for every hand")
def hdist_zoom(ctx, *, source, hand, hands, schedule, recur, fine_mm, top_mm, far_min_mm, far_max_mm, zoom_max,
               zoom, far_turn_mm, res_mm, reveal, valley, valley_R, pace, angle, drawn_mm, span, fill, calib,
               R_mm, peak_fine_mm):
    valley = valley_R if calib == "R" else valley
    if source == "relay":
        grams = [ctx.use("hand", x) for x in hands]
        voices = list(hands)
    else:
        grams = [ctx.use("hand", hand)]
        voices = [hand]
    kw = dict(fine_mm=fine_mm, top_mm=top_mm, far_min_mm=far_min_mm, far_max_mm=far_max_mm, zoom_max=zoom_max,
              zoom=zoom, far_turn_mm=far_turn_mm, res_mm=res_mm, reveal=reveal, angle=angle, calib=calib, R_mm=R_mm,
              peak_fine_mm=peak_fine_mm)
    if source == "relay":
        r, q = relay_zoom(ctx, grams, valley=valley, pace=pace, drawn_mm=drawn_mm, **kw)
    else:
        g = zoom_shape(schedule, 4000, ctx.rng("schedule", schedule), recur)
        r, q = fitted_zoom(ctx, grams[0], g, valley=valley, pace=pace, drawn_mm=drawn_mm, fill=fill,
                           width_fill=span, **kw)
    meas = zoom_measures(r, r["hdist"]["zoom"])
    meas["source_turns"] = round(_len(q) / r["turn_len"], 1)
    pts, k, off = shrink_fit(r["points"], ctx.box, grow=True)
    ch = {"zoom": r["zoom"], "u_src": np.clip(r["u_share"], 0, 1)}
    ch["voice"] = r["voice_pts"] if "voice_pts" in r else np.zeros(len(pts))
    hd = dict(r["hdist"])
    hd["fit"] = round(k, 3)
    hd["far_on_sheet_mm"] = round(hd["far_turn_mm"] * k, 2)
    return [Mark(pts, ch, {"source": f"{source}:{'>'.join(voices)}", "voices": voices, "measure": meas,
                           "hdist": hd, "turn_len": r["turn_len"], "drawn_mm": r["length_mm"] * k,
                           "fit": {"scale": k, "offset": [float(off[0]), float(off[1])]}})]
