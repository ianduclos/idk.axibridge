"""Series voices (round 12, thread `series`): lines that belong to a SET of
sheets rather than to one sheet.

- `series_travel`  one line that travels across a row of sheets. It is grown
                   the way the drift line is grown (a learned hand speaks every
                   token; each chunk is the best of K proposals), but the
                   choice among proposals is steered by a ROUTE — a target
                   that moves along the strip as the line gets longer — instead
                   of by a pull to the centre of one frame. The hand's grammar
                   stays whole; only *where it goes* is the series' business.
                   The gesture scale R is the scale of ONE sheet (as if each
                   sheet were the research frame), so a strip of seven sheets
                   is seven sheets' worth of gestures, not one shrunk drawing.
- `series_stretch` a placeholder voice: the part takes a stretch of part 0's
                   line (see arranger `series_row`) instead of growing its own.

Hands can change along the route at authored positions (`hand_at`), so a
handover happens at a chosen moment of the series, not at even spacing.
Channels: `voice` (hand index at each point), `series_u` (0…1 along the
whole line). Coordinates: sheet mm of the whole strip (frame = the row).
"""
from __future__ import annotations

import numpy as np

from .. import grammar as gm
from .. import hybrid as hyb
from .core import P, Mark, voice


def _route_xy(route: list[float], u: float, frame) -> np.ndarray:
    """Target point (mm) at progress u from route triples (u, x_sheets, y_frac)."""
    W, H = frame
    r = np.asarray(route, float).reshape(-1, 3)
    x = np.interp(u, r[:, 0], r[:, 1])
    y = np.interp(u, r[:, 0], r[:, 2])
    return np.array([x, y * H])


def _hand_weights(u: float, at: list[float], fade: float) -> np.ndarray:
    """Weights of k hands at progress u: hand i owns [at[i-1], at[i]) (at has
    k-1 switch positions); linear cross-fade of width `fade` around each."""
    k = len(at) + 1
    w = np.zeros(k)
    if k == 1:
        w[0] = 1.0
        return w
    i = int(np.searchsorted(np.asarray(at), u, side="right"))
    w[min(i, k - 1)] = 1.0
    if fade > 0:
        for j, a in enumerate(at):
            d = (u - a) / fade
            if -0.5 <= d <= 0.5:
                f = d + 0.5
                w[:] = 0.0
                w[j], w[j + 1] = 1 - f, f
    return w


def travel(ctx, *, hands, hand_at, fade, length, sheets, route, pull, clear, K, scale, exit, step, chunk):
    W, H = ctx.frame
    sw = W / sheets
    grams = [ctx.use("hand", h) for h in hands]
    at = list(hand_at)[: len(hands) - 1]
    if len(at) < len(hands) - 1:              # even switch points by default
        at = [(i + 1) / len(hands) for i in range(len(hands) - 1)]
    rng = np.random.default_rng([ctx.seed, 0x5E1E5])
    hy = hyb.HybridGrammar(grams, np.ones(len(grams)) / len(grams), "mixture", seed=int(rng.integers(1 << 30)))
    total = float(length)
    hy.weight_fn = lambda s: _hand_weights(s / total, at, fade)
    R = scale * 0.95 * float(np.hypot(sw, H))         # one sheet's research-frame scale, in mm
    rt = [float(v) for v in route]
    rt = [rt[i] if i % 3 != 1 else rt[i] * sw for i in range(len(rt))]          # x in sheets → mm
    if len(rt) < 6 or len(rt) % 3:
        raise ValueError("series_travel: route is triples (u, x_sheets, y_frac), at least two")
    m = 0.04 * min(sw, H)
    lo = np.array([m, m])
    hi = np.array([W - m, H - m])
    free = np.array([-np.inf, -np.inf]), np.array([np.inf, np.inf])
    pos = _route_xy(rt, 0.0, (W, H))
    heading = float(rng.uniform(0, 2 * np.pi))
    toks: list = []
    pts = [pos[None, :]]
    s_done = 0.0
    log: list = []
    from scipy.spatial import cKDTree  # noqa: PLC0415
    lag = max(int(3 * clear / step), 4)
    while s_done < total - 1e-6:
        wn = _hand_weights(s_done / total, at, fade)
        gh = grams[int(rng.choice(len(grams), p=wn / wn.sum()))]
        Ls = gh.stroke_lengths or [0.1]
        L = max(min(float(Ls[int(rng.integers(len(Ls)))]), chunk, total - s_done), 1e-3)
        drawn = np.vstack(pts)
        tree = cKDTree(drawn[:-lag]) if len(drawn) > 2 * lag else None
        tgt = _route_xy(rt, min((s_done + L) / total, 1.0), (W, H))
        best = None
        for _ in range(K):
            hy.s_offset = s_done
            hy.log = []
            c, _ = gm.generate_tokens(hy, rng, length=L, context=None, p_follow=gm.P_FOLLOW, end_fit=gm.END_FIT)
            if not c:
                continue
            if toks and toks[-1][0] in gm.SEG_KINDS and c[0][0] in gm.SEG_KINDS:
                _, first = gm._continuity(toks[-1], c[0], lock_prev=True)
                c = [first] + c[1:]
            p, _, _ = gm.tokens_to_points(c, R, start=pos, heading=heading, step=step)
            lo_, hi_ = free if (exit and (s_done + L) / total > float(rt[-6])) else (lo, hi)
            out = np.sum(np.clip(lo_ - p, 0, None) + np.clip(p - hi_, 0, None)) / R
            crowd = float(np.mean(tree.query(p, k=1)[0] < clear)) if tree is not None else 0.0
            d = float(np.linalg.norm(p[-1] - tgt) / R)
            score = 50 * out + 2.0 * crowd + pull * d + 0.05 * rng.random()
            if best is None or score < best[0]:
                best = (score, c, p, hy.log)
        if best is None:
            break
        _, c, p, lg = best
        toks += c
        pts.append(p[1:])
        log += lg
        heading = gm.end_heading(c, heading)
        pos = p[-1]
        s_done += gm.stroke_length(c)
    P_ = np.vstack(pts)
    seg = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))]
    u = seg / max(seg[-1], 1e-9)
    if log:
        ls = np.array([float(e[0]) for e in log]) / total
        lh = np.array([int(e[1]) for e in log], float)
        o = np.argsort(ls, kind="stable")
        j = np.clip(np.searchsorted(ls[o], u, side="right") - 1, 0, len(lh) - 1)
        vc = lh[o][j]
    else:
        vc = np.zeros(len(P_))
    meta = {"voices": list(hands), "hand_at": at, "R_mm": R, "tokens": len(toks), "length_R": float(total),
            "sheets": int(sheets), "library": [{"kind": "hand", "id": h} for h in hands]}
    return [Mark(P_, {"voice": vc, "series_u": u}, meta)]


@voice("series_travel", params=[
    P("hands", "refs", ["trail_miner"], "hands in the order they take the line", kind="hand", min_len=1, max_len=6),
    P("hand_at", "floats", [], "progress (0…1) where each next hand takes over; empty = even"),
    P("fade", "float", 0.04, "width of each handover cross-fade, in progress", min=0.0, max=0.5),
    P("length", "float", 14.0, "whole line, in one sheet's reference lengths", min=0.5, max=80.0),
    P("sheets", "int", 7, "sheets in the row (the frame is the whole row)", min=1, max=12),
    P("route", "floats", [0.0, 0.5, 0.5, 1.0, 6.5, 0.5],
      "triples (u, x in sheets, y as a fraction of the height): where the line is meant to be at progress u"),
    P("pull", "float", 3.0, "how hard the route steers the choice among proposals", min=0.0, max=40.0),
    P("clear", "float", 1.0, "crowding radius, mm (the line avoids its own past within this)", min=0.1, max=20.0),
    P("K", "int", 8, "proposals per chunk", min=1, max=40),
    P("scale", "float", 1.0, "gesture scale × one sheet's research-frame scale", min=0.1, max=4.0),
    P("exit", "bool", False, "the line may leave the row (past any edge) once it is on the route's last leg"),
    P("step", "float", 0.25, "sampling step, mm", min=0.05, max=2.0),
    P("chunk", "float", 0.4, "longest chunk grown between route decisions, R (a hand's own strokes are cut "
      "to this; long-stroke hands such as the flies otherwise walk off the route)", min=0.02, max=8.0),
], doc="one line that travels a row of sheets: a learned hand steered by a route, hands handed over at set moments")
def series_travel(ctx, *, hands, hand_at, fade, length, sheets, route, pull, clear, K, scale, exit, step, chunk):
    return travel(ctx, hands=hands, hand_at=hand_at, fade=fade, length=length, sheets=sheets, route=route,
                  pull=pull, clear=clear, K=K, scale=scale, exit=exit, step=step, chunk=chunk)


@voice("series_stretch", doc="placeholder: this part takes a stretch of part 0's line (arranger series_row)")
def series_stretch(ctx):
    return []
