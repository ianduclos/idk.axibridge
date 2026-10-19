# FROZEN from research commit 071aea1: tools/gesture/gesture/kit/voices_gmorph.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""A grammar morphed continuously: one hand whose gesture type changes along its line (round 13, II-a).

Ian on the river belt with tighter curves: "loving this kinda stuff, line that
morphs gesture type. I'd love to explore this concept more." `belt` ramps one
number (the curvature gain), so the same gesture gets tighter. Here several of
the hand's own grammar dials move along the line, each on its own schedule, so
the *type* changes. The round-13 piece (experiments/gmorph.py, river_belt):
long calm bends, a hairpin meander, a sawtooth, an angular coil, loops.

voice `gmorph`: the hand's order-2 token chain (grammar v7, its k-NN over the
training transitions) is run in chunks of one training-stroke length, as the
drift line does. At every draw the chain's proposals are re-weighted by where
the line is (u = s / length):

- `span`   target quantile of the hand's OWN segment lengths (0 = its shortest
           segments, 1 = its longest). Selection, not scaling: the tokens are
           the hand's.
- `turn`   target quantile of the hand's own per-token turning |κ̄·l|.
- `corners` weight of the hand's corner tokens relative to its segments
           (0 = none, 1 = the hand's own share, 6 = six times it).
- `sharp`  target quantile of the hand's own corner angles (0 its blunt
           corners … 1 its hairpins).
- `sign`   −1 coil (each bend or corner turns the way the last one did) … 0
           the hand's own … +1 zigzag (each turns against the last). A bend
           put on the other side is the hand's token mirrored whole (tangent
           continuous, κ may jump, as a meander's reversing bend does); a
           corner keeps its angle and changes side. A coil lets go with a
           counter-turn after `loop_rad` of turning one way, so coils become
           loops that travel instead of rings.
- `gain`   curvature gain on top (1 = the hand's κ).
- `pull`   pull of the heading back to the valley axis, per mm (the belt's
           pull: high strings the line along, low lets it wander or curl).
- `r`      optional regime channel schedule (0 wire, 1 nib, 2 mass).

Each dial is a schedule ``[u0, v0, u1, v1, …]`` (u in [0, 1], cosine eased
between knots, held outside them); null = the hand's own (span/turn: no
preference; corners 1; sign 0; gain 1; pull `pull0`). Dials run on independent
schedules, so the middle of a line is a combination the start and the end
never had (zigzag + corners = sawtooth; coil + corners = angular coil; coil + high
turn = loops),
not an average of them.

Then the tokens become κ(s) in mm (R = `scale_mm`) and are integrated along a
valley as `belt` does — θ' = gain·κ − pull·sin(θ − θ*), θ* a weak pull back to
the axis line (`hold`), corners turning the heading at once — and the line is
fitted into ctx.box. Channels: `u` (0 → 1 along the line), `r` if scheduled.
meta["gmorph"] keeps the schedules and the token log (s, kind, l, signed
turning, u, end κ·R) for `measure`. Unknown hands work as-is; the dials are
quantiles of each hand's own vocabulary, so one schedule speaks every hand.
"""
from __future__ import annotations

import numpy as np

from ._research import grammar as gm
from .core import P, fitted, voice

DIALS = ("span", "turn", "corners", "sharp", "sign", "gain", "pull", "r")
NEUTRAL = {"corners": 1.0, "sign": 0.0, "gain": 1.0}


def schedule(knots, u, default: float | None = None) -> np.ndarray:
    """A dial's value at u (array) from a flat knot list [u0, v0, u1, v1, …]:
    cosine eased between knots, held before the first and after the last.
    None/empty → `default` (None stays None)."""
    u = np.asarray(u, float)
    if not knots:
        return None if default is None else np.full(u.shape, float(default))
    k = np.asarray(knots, float)
    if len(k) % 2:
        raise ValueError("gmorph: a schedule is a flat list of (u, value) pairs")
    k = k.reshape(-1, 2)
    k = k[np.argsort(k[:, 0], kind="stable")]
    ku, kv = k[:, 0], k[:, 1]
    if len(ku) == 1:
        return np.full(u.shape, kv[0])
    j = np.clip(np.searchsorted(ku, u, side="right") - 1, 0, len(ku) - 2)
    span = np.maximum(ku[j + 1] - ku[j], 1e-9)
    f = np.clip((u - ku[j]) / span, 0.0, 1.0)
    f = 0.5 - 0.5 * np.cos(np.pi * f)
    return kv[j] + (kv[j + 1] - kv[j]) * f


def _at(knots, u: float, default):
    v = schedule(knots, np.array([u]), default)
    return None if v is None else float(v[0])


def hand_tables(g: gm.Grammar) -> dict:
    """Sorted segment lengths and per-token turnings of a hand's training
    strokes (R units): its own vocabulary, for quantile targets."""
    segl = np.sort([t[1] for toks in g.strokes for t in toks if t[0] != "corner"])
    turn = np.sort([abs(0.5 * (t[2] + t[3]) * t[1]) for toks in g.strokes for t in toks if t[0] != "corner"])
    corner = np.sort([abs(t[1]) for toks in g.strokes for t in toks if t[0] == "corner"])
    return {"segl": segl, "turn": turn, "corner": corner,
            "corner_share": len(corner) / max(len(corner) + len(segl), 1)}


def _q(sorted_vals: np.ndarray, x: float) -> float:
    if not len(sorted_vals):
        return 0.5
    return float(np.searchsorted(sorted_vals, x) / len(sorted_vals))


def _realised(prev, kind, p):
    """(length, turning) of a proposal as it will be drawn after the chain's
    κ-continuity at the joint with `prev` (an arc takes the joint κ and keeps
    its turning; a clothoid or line starts at the joint κ)."""
    l, k0, k1 = p
    kj = prev[3] if (prev is not None and prev[0] in gm.SEG_KINDS) else None
    if kj is None or kind == "arc":
        return l, abs(0.5 * (k0 + k1) * l)
    if kind == "line":
        return l, abs(0.5 * kj * l)
    return l, abs(0.5 * (kj + k1) * l)


def _weights(tab, span, turn, corners, focus, prev, sharp=None):
    """The chain's proposals re-weighted toward the dials' targets, judged on
    each proposal as it will be drawn (after κ-continuity)."""
    def f(kinds, pars):
        w = np.ones(len(kinds))
        seg = np.array([k != "corner" for k in kinds])
        for i, (k, p) in enumerate(zip(kinds, pars)):
            if k == "corner":
                continue
            l, tr = _realised(prev, k, p)
            if span is not None:
                w[i] *= np.exp(-0.5 * ((_q(tab["segl"], l) - span) / focus) ** 2)
            if turn is not None:
                w[i] *= np.exp(-0.5 * ((_q(tab["turn"], tr) - turn) / focus) ** 2)
        base = float(w[seg].mean()) if seg.any() else 1.0
        w[~seg] = corners * max(base, 0.05)
        if sharp is not None and (~seg).any():
            gc = np.array([np.exp(-0.5 * ((_q(tab["corner"], abs(pars[i][0])) - sharp) / focus) ** 2)
                           for i in np.flatnonzero(~seg)])
            w[~seg] *= gc / max(float(gc.mean()), 1e-6)
        return np.maximum(w, 0.0)
    return f


def _signed(tok, want):
    """A segment that bends to side `want`: the hand's token, mirrored whole
    if it bends the other way (lines are left alone)."""
    kind, l, k0, k1 = tok
    km = 0.5 * (k0 + k1)
    side = np.sign(km) if abs(km) > 1e-9 else np.sign(k1)
    if kind == "line" or side == 0 or side == want:
        return tok
    return gm._tok_seg(kind, l, -k0, -k1)


def morph_tokens(g: gm.Grammar, rng, *, length: float, sched: dict, focus: float, knn: int,
                 tab: dict | None = None, loop_rad: float = 7.0) -> tuple[list, list]:
    """The hand's chain, chunk by chunk (one training-stroke length each),
    its proposals re-weighted by the dials at u = s / length; `sign` mirrors
    segments to coil or zigzag. Returns (tokens, log) — log rows
    (s, kind, l, turning signed, u, end κ·R)."""
    tab = tab or hand_tables(g)
    toks: list = []
    log: list = []
    s_done = 0.0
    last_sign = 1.0
    coil = 0.0                        # turning (rad) of the current same-sign run
    Ls = g.stroke_lengths or [0.1]
    guard = 0
    while s_done < length - 1e-6 and guard < 4000:
        guard += 1
        L = max(min(float(Ls[int(rng.integers(len(Ls)))]), length - s_done), 1e-3)
        p2, p1 = ["START"], ["START"]
        chunk: list = []
        s, rec, run, draws = 0.0, None, 0, 0
        while draws < 4 * gm.MAX_TOKENS and len(chunk) < gm.MAX_TOKENS:
            draws += 1
            u = min((s_done + s) / length, 1.0)
            span = _at(sched.get("span"), u, None)
            turn = _at(sched.get("turn"), u, None)
            cor = _at(sched.get("corners"), u, NEUTRAL["corners"])
            sgn = _at(sched.get("sign"), u, NEUTRAL["sign"])
            shp = _at(sched.get("sharp"), u, None)
            prevtok = chunk[-1] if chunk else (toks[-1] if toks else None)
            ruled = sgn != 0 and rng.random() < abs(sgn)     # this draw obeys the sign dial
            want = -last_sign if (sgn > 0 or coil >= loop_rad) else last_sign
            kind, p, rec_ = g.draw(p2, p1, s, L, rng, prev_rec=rec,
                                   p_follow=gm.P_FOLLOW if run < gm.MAX_RUN else 0.0, knn=knn,
                                   weights=_weights(tab, span, turn, max(cor, 0.0), focus,
                                                    None if ruled else prevtok, shp))
            run = run + 1 if (rec is not None and rec_ == rec + 1) else 0
            rec = rec_
            if kind == "corner":
                if not chunk and not toks:
                    continue
                prev = chunk[-1] if chunk else toks[-1]
                if prev[0] == "corner" or cor <= 0:
                    continue
                ang = float(p[0])
                if ruled:
                    ang = want * abs(ang)
                tok = gm._tok_corner(ang)
            elif ruled:
                # the hand's bend, put on the side the dial asks for; the tangent stays
                # continuous, κ may jump at the joint (a bend reversing, as in a meander)
                tok = _signed(gm._tok_seg(kind, *p), want)
            else:
                tok = gm._tok_seg(kind, *p)
                if prevtok is not None and prevtok[0] in gm.SEG_KINDS:
                    newprev, tok = gm._continuity(prevtok, tok, lock_prev=not chunk)
                    if chunk and newprev is not prevtok:
                        chunk[-1] = newprev
            if tok[0] != "corner" and s + tok[1] >= L:
                frac = max(L - s, 1e-9) / tok[1]
                if frac < gm.END_FIT and chunk and chunk[-1][0] in gm.SEG_KINDS:
                    pv = chunk[-1]
                    chunk[-1] = gm._tok_seg(pv[0], pv[1] + max(L - s, 0.0), pv[2], pv[3])
                else:
                    chunk.append(gm._tok_seg(tok[0], tok[1] * frac, tok[2], tok[2] + (tok[3] - tok[2]) * frac))
                break
            chunk.append(tok)
            if tok[0] != "corner":
                s += tok[1]
                tr = 0.5 * (tok[2] + tok[3]) * tok[1]
                if abs(tr) > 1e-3:
                    coil = coil + abs(tr) if np.sign(tr) == last_sign else abs(tr)
                    last_sign = float(np.sign(tr))
            elif abs(tok[1]) > 1e-9:
                coil = coil + abs(tok[1]) if np.sign(tok[1]) == last_sign else abs(tok[1])
                last_sign = float(np.sign(tok[1]))
            p2, p1 = (chunk[-2] if len(chunk) >= 2 else p1), chunk[-1]
        while chunk and chunk[-1][0] == "corner":
            chunk.pop()
        if not chunk:
            continue
        s0 = s_done
        for t in chunk:
            if t[0] == "corner":
                log.append([s0, "corner", 0.0, float(t[1]), min(s0 / length, 1.0), 0.0])
            else:
                log.append([s0, t[0], float(t[1]), float(0.5 * (t[2] + t[3]) * t[1]), min(s0 / length, 1.0),
                            float(t[3])])
                s0 += t[1]
        toks += chunk
        s_done += gm.stroke_length(chunk)
    return toks, log


def integrate(toks: list, *, scale_mm: float, step: float, sched: dict, length: float,
              pull0: float, hold: float) -> tuple[np.ndarray, np.ndarray]:
    """Tokens → points (mm) along a valley: θ' = gain(u)·κ − pull(u)·sin(θ − θ*),
    θ* = −atan(hold·y) (a weak return to the axis line); corners turn θ at once.
    Returns (points, u per point)."""
    R = float(scale_mm)
    th, x, y, s = 0.0, 0.0, 0.0, 0.0
    pts = [(x, y)]
    us = [0.0]
    Ltot = max(length * R, 1e-9)
    for t in toks:
        if t[0] == "corner":
            th += float(t[1])
            continue
        lmm = t[1] * R
        n = max(int(np.ceil(lmm / step)), 1)
        h = lmm / n
        for i in range(n):
            f = (i + 0.5) / n
            k = (t[2] + (t[3] - t[2]) * f) / R
            u = min(s / Ltot, 1.0)
            gain = _at(sched.get("gain"), u, NEUTRAL["gain"])
            pull = _at(sched.get("pull"), u, pull0)
            tgt = -np.arctan(hold * y)
            th += h * (gain * k - pull * np.sin(th - tgt))
            x += h * np.cos(th)
            y += h * np.sin(th)
            s += h
            pts.append((x, y))
            us.append(min(s / Ltot, 1.0))
    return np.asarray(pts), np.asarray(us)


def measure(log: list, n_win: int = 12) -> list[dict]:
    """Per arc-length window of a gmorph token log: median segment length
    (R), median |turning| per bend (rad), corners per R, zigzag share (turns
    — bends and corners — to the opposite side from the turn before), and
    the largest same-side run of turning in the window (rad)."""
    segs = [r for r in log if r[1] != "corner"]
    L = (segs[-1][0] + segs[-1][2]) if segs else 1.0
    rows = [{"l": [], "t": [], "c": 0, "alt": [], "run": 0.0} for _ in range(n_win)]
    prev, run = None, 0.0
    for r in log:
        b = min(int(r[0] / max(L, 1e-9) * n_win), n_win - 1)
        if r[1] == "corner":
            rows[b]["c"] += 1
        else:
            rows[b]["l"].append(r[2])
            rows[b]["t"].append(abs(r[3]))
        if abs(r[3]) > 1e-3:
            sg = np.sign(r[3])
            if prev is not None:
                rows[b]["alt"].append(float(sg != prev))
            run = run + abs(r[3]) if (prev is None or sg == prev) else abs(r[3])
            rows[b]["run"] = max(rows[b]["run"], run)
            prev = sg
    w = L / n_win
    return [{"seg": float(np.median(r["l"])) if r["l"] else float("nan"),
             "turn": float(np.median(r["t"])) if r["t"] else float("nan"),
             "corners_per_R": r["c"] / max(w, 1e-9),
             "zigzag": float(np.mean(r["alt"])) if r["alt"] else float("nan"),
             "coil": r["run"]} for r in rows]


_SCHED = "schedule [u0, v0, u1, v1, …] (u 0 → 1 along the line, cosine eased; null = the hand's own)"


@voice("gmorph", params=[
    P("hand", "ref", "river_belt", "the one hand whose grammar is morphed", kind="hand"),
    P("length", "float", 8.0, "line length in the hand's reference lengths R", min=0.5, max=40.0),
    P("span", "floats", None, "target quantile of the hand's own segment lengths (0 short … 1 long): " + _SCHED,
      optional=True),
    P("turn", "floats", None, "target quantile of the hand's own turning per token (0 calm … 1 tight): " + _SCHED,
      optional=True),
    P("corners", "floats", None, "corner weight vs the hand's own share (0 none, 1 own, 6 six times): " + _SCHED,
      optional=True),
    P("sharp", "floats", None, "target quantile of the hand's own corner angles (0 blunt … 1 hairpin): " + _SCHED,
      optional=True),
    P("sign", "floats", None, "−1 coil … 0 own … +1 zigzag: " + _SCHED, optional=True),
    P("gain", "floats", None, "curvature gain on top of the hand's: " + _SCHED, optional=True),
    P("pull", "floats", None, "valley pull per mm (null = pull0): " + _SCHED, optional=True),
    P("r", "floats", None, "regime channel 0 wire … 1 nib … 2 mass (null = no r channel): " + _SCHED,
      optional=True),
    P("loop_rad", "float", 7.0, "coiling (sign < 0) lets go after this much turning one way: one loop, then a "
      "counter-turn (rad)", min=3.5, max=60.0),
    P("pull0", "float", 0.12, "valley pull per mm when `pull` is null", min=0.0, max=1.5),
    P("hold", "float", 0.02, "weak return of the line to its axis, per mm of offset", min=0.0, max=0.5),
    P("focus", "float", 0.14, "selection width, in quantiles of the hand's vocabulary (small = strict)",
      min=0.03, max=1.0),
    P("knn", "int", 40, "chain neighbours considered per draw", min=4, max=200),
    P("scale_mm", "float", 100.0, "the hand's reference length R in mm while integrating", min=10.0, max=600.0),
    P("step", "float", 0.25, "integration step, mm", min=0.05, max=2.0),
], doc="one hand, several grammar dials moved along the line on independent schedules: its gesture type changes")
def gmorph(ctx, *, hand, length, span, turn, corners, sharp, sign, gain, pull, r, loop_rad, pull0, hold, focus, knn,
           scale_mm, step):
    g = ctx.use("hand", hand)
    sched = {"span": span, "turn": turn, "corners": corners, "sharp": sharp, "sign": sign, "gain": gain, "pull": pull, "r": r}
    for k, v in sched.items():
        if v is not None and len(v) % 2:
            raise ValueError(f"gmorph: {k} is a flat list of (u, value) pairs")
    rng = ctx.rng("chain")
    toks, log = morph_tokens(g, rng, length=float(length), sched=sched, focus=float(focus), knn=int(knn),
                             loop_rad=float(loop_rad))
    total = gm.stroke_length(toks)
    pts, u = integrate(toks, scale_mm=scale_mm, step=step, sched=sched, length=total, pull0=pull0, hold=hold)
    ch = {"u": u}
    if r:
        ch["r"] = np.clip(schedule(r, u), 0.0, 2.0)
    md = {"voices": [hand], "library": [{"kind": "hand", "id": hand}],
          "gmorph": {"schedules": sched, "length_R": total, "scale_mm": scale_mm, "log": log}}
    return fitted([pts], ctx.box, [ch], [md])
