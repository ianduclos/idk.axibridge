# FROZEN from research commit 6f96418: tools/gesture/gesture/kit/voices_accrue.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 13, thread II-c `accrue` — morph by accumulation.

One line, grown by a learned hand token by token (the drift line's way: each
chunk is the best of K proposals), carries a small BODY of internal state that
compounds along the line. Nothing outside the line steers its gesture: no
driver, no field. The state bends the hand's tokens (a curvature bias; the
hand's own curvature damped as the habit takes over, or after a break) and is
written along the line as channels, so the modulator `accrue_ink` can ink it.

The body (integrated along arc length, all cumulative):

  habit (habit="loops", the piece)
                     a ratchet driven by the line's own completed loops. The
                     first full turn the hand happens to make sets a sense;
                     every further loop the same way tightens the curl bias
                     C (logistic: slow, then fast, then saturating at c_max);
                     a counter-turn of `relapse_turn` loosens it (× relapse).
                     So the curl is a staircase, one step per loop, not a
                     slide. `learn`: a habit that has broken before re-forms
                     faster. (habit="leaky", the dud: C = H·A, a leaky
                     average of the turning A fed back through a gain H that
                     grows with length — runaway or ramp.)
  press              self-density: the share of the line's newest stretch
                     within `press_r` of its own past. A tight coil sits on
                     itself, so press rises.
  tip                when the coil has choked (press over `press_on` with the
                     curl past 0.6·c_max, for `press_hold` mm) it becomes a
                     KNOT (mass) and the habit BREAKS: the curl drops to
                     keep·C, and the path's angular velocity is handed to the
                     nib: spin Ω += transfer·C/R (rad/mm), decaying with
                     half-life `spin_half`. The path runs straight-ish for
                     `release` mm while the nib spins: barbs → twisted rope →
                     calm ribbon → wire.
  fatigue F          counts the breaks: each next coil is tighter (c_max ×
                     1 + tire·F), each release shorter; after `exhaust`
                     breaks the habit is spent and the line goes free.
  paper memory       every stretch leaves its state (signed curl, loops, Ω)
                     where it was drawn. Passing within `recall` mm of a
                     stretch at least `recall_gap` mm older, the line takes on
                     part (`mix`) of it, at most once per recall_gap: an old
                     coil brings its habit back, a calm stretch loosens it, a
                     spinning ribbon sets the nib spinning.

Composition only (never a cause of morph): `route` = centre | ltr (a target
walking left → right, for a frieze), `pull`; `look` / `edge_k` keep the line
off the paper edge (that turn is kept out of the habit).

Channels written (per point, linear between chunk ends):
  acc_curl  |C| / c_max (0..1)          acc_habit loops in the current habit
  acc_press self-density (0..1)          acc_spin  nib spin Ω, rad/mm (signed)
  acc_knot  0..1 bump over each knot     acc_rel 1 inside a release (nearest)
  acc_recall share of paper memory taken  acc_s arc length, mm
meta["accrue"]: knots (s, pos, sign, C), loops (s, kind first|loop|relapse,
C, n), recalls (s, from_s, pos, the old state).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial import cKDTree

from ._research import grammar as gm
from .core import Mark, P, channel_kind, voice

channel_kind("acc_rel", "nearest")


def _bend(toks: list, bias: float, damp: float) -> list:
    """Hand tokens with κR × damp plus a constant bias (κR); corners × damp."""
    out = []
    for t in toks:
        if t[0] == "corner":
            out.append(["corner", float(t[1]) * damp])
        else:
            out.append([t[0], float(t[1]), float(t[2]) * damp + bias, float(t[3]) * damp + bias])
    return out


def walk(g, rng, *, length, R, box, K, step, chunk, clear, h0, h_len, h_use, lam, c_max, keep, transfer,
         spin_half, release, release_damp, press_r, press_on, press_hold, recall, mix,
         stereo=0.6, recall_gap=150.0, c_rate=0.0, habit="leaky", c0=3.0, grow=0.45, learn=1.0, relapse=0.5,
         relapse_turn=math.pi, knot_len=14.0, route="centre", pull=0.6, look=15.0, edge_k=40.0, tire=0.35, exhaust=6, start=None, heading=None):
    """Grow the line. Returns (points (N,2) mm, channels, events).
    `length`, `chunk`, `lam` in R units; everything else in mm."""
    x0, y0, w, h = box
    m_ = 0.02 * min(w, h)
    lo = np.array([x0 + m_, y0 + m_])
    hi = np.array([x0 + w - m_, y0 + h - m_])
    total_mm = float(length) * R

    def target(u):
        if route == "ltr":
            return np.array([x0 + (0.06 + 0.88 * u) * w, y0 + 0.5 * h])
        return np.array([x0 + w / 2, y0 + h / 2])

    if start is not None:
        pos = np.asarray(start, float)
    elif route == "ltr":
        pos = np.array([x0 + 0.04 * w, y0 + (0.35 + 0.3 * rng.random()) * h])
    else:
        pos = target(0) + (rng.random(2) - 0.5) * np.array([w, h]) * 0.4
    head = float(heading) if heading is not None else (float(rng.uniform(-0.5, 0.5)) if route == "ltr"
                                                         else float(rng.uniform(0, 2 * np.pi)))
    A, H, F, spin = 0.0, float(h0), 0, 0.0
    sigma, Cl, tacc, nl = 0.0, 0.0, 0.0, 0     # loops habit: sense, level (κR), turning since last event, loops
    loops: list = []
    C_prev, lprev = 0.0, 0.0
    rel_left = press = press_run = 0.0
    knots: list = []
    recalls: list = []
    pts = [pos[None, :]]
    st = [np.array([[0.0, H, 0.0, 0.0]])]     # deposited state per point: A, H, spin, s
    rec = [(0.0, 0.0, H, 0.0, 0.0, 0.0, 0.0)]  # s, curl, H, press, spin, rel, recall
    s_mm = 0.0
    lag = max(int(3 * max(press_r, recall, clear) / step), 8)
    toks_prev = None
    first_free = 0.0
    last_recall = -1e9
    while s_mm < total_mm - 1e-6:
        cm = c_max * (1.0 + tire * F)
        spent = F >= exhaust
        # leaky: the curl follows H·A (runaway past H = 1). loops: the curl is a ratchet that the
        # line's own completed loops tighten (logistic per loop) and its counter-turns loosen.
        # Either way it moves at most c_rate κR per mm, and the release run holds it at 0.
        if habit == "leaky":
            Ct = float(np.clip(H * A, -cm, cm))
        else:
            Ct = 0.0 if rel_left > 0 else sigma * min(Cl, cm)
        C = C_prev + float(np.clip(Ct - C_prev, -c_rate * lprev, c_rate * lprev)) if c_rate > 0 else Ct
        C_prev = C
        # a forming habit is stereotyped: the hand's own variety fades as the curl takes over
        damp = release_damp if rel_left > 0 else 1.0 - stereo * min(abs(C) / cm, 1.0)
        Ls = g.stroke_lengths or [0.1]
        L = max(min(float(Ls[int(rng.integers(len(Ls)))]), chunk, (total_mm - s_mm) / R), 1e-3)
        drawn = np.vstack(pts)
        tree = cKDTree(drawn[:-lag]) if len(drawn) > 2 * lag else None
        coil = abs(C) / cm
        tgt = target(min(s_mm / total_mm, 1.0))
        # the paper edge: if the line, held on its heading, would leave the sheet within `look`·3,
        # it turns toward the inside (composition, kept out of the turning memory)
        hv = np.array([math.cos(head), math.sin(head)])
        wall = 0.0
        for k_ in (1.0, 2.0, 3.0):
            a_ = pos + k_ * look * hv
            if np.any(a_ < lo) or np.any(a_ > hi):
                to = tgt - pos
                side = 1.0 if (hv[0] * to[1] - hv[1] * to[0]) >= 0 else -1.0
                wall = edge_k * side * (4.0 - k_) / 3.0
                if C * side < 0:          # a coil turning the wrong way is overruled near the edge
                    wall -= C
                break
        best = None
        for _ in range(K):
            c, _ = gm.generate_tokens(g, rng, length=L, context=None, p_follow=gm.P_FOLLOW, end_fit=gm.END_FIT)
            if not c:
                continue
            if toks_prev is not None and toks_prev[-1][0] in gm.SEG_KINDS and c[0][0] in gm.SEG_KINDS:
                _, first = gm._continuity(toks_prev[-1], c[0], lock_prev=True)
                c = [first] + c[1:]
            cb = _bend(c, C + wall, damp)
            p, _, _ = gm.tokens_to_points(cb, R, start=pos, heading=head, step=step)
            hd = float(gm.end_heading(cb, head))
            ahead = p[-1] + look * np.array([math.cos(hd), math.sin(hd)])
            q = np.vstack([p, ahead[None, :]])
            out = float(np.sum(np.clip(lo - q, 0, None) + np.clip(q - hi, 0, None))) / len(q)
            crowd = float(np.mean(tree.query(p, k=1)[0] < clear)) if tree is not None else 0.0
            pl = 0.0 if spent else pull
            sc = 4.0 * out + 2.0 * (1.0 - coil) * crowd + pl * float(np.linalg.norm(p[-1] - tgt)) / max(w, h) \
                + 0.05 * rng.random()
            if best is None or sc < best[0]:
                best = (sc, c, cb, p)
        if best is None:
            break
        _, c, cb, p = best
        lR = gm.stroke_length(cb)
        lmm = lR * R
        # self-density (the line's memory of where it has been)
        dens = float(np.mean(tree.query(p, k=1)[0] < press_r)) if tree is not None else 0.0
        a = math.exp(-lmm / (4.0 * press_r))
        press = press * a + dens * (1 - a)
        # turning memory → feedback through the habit
        tr = float(gm.end_heading(cb, 0.0)) / max(lR, 1e-6) - wall
        b = math.exp(-lR / lam)
        A = A * b + tr * (1 - b)
        H = H * math.exp(-lR / 0.15) if spent else H + (h_len + h_use * coil) * lR
        if habit == "loops":
            tacc += tr * lR
            if spent:
                Cl *= math.exp(-lR / 0.15)
            elif rel_left <= 0:
                if sigma == 0.0:
                    if abs(tacc) >= 2 * math.pi:          # the first loop the hand happens to make sets the sense
                        sigma, Cl, nl, tacc = (1.0 if tacc > 0 else -1.0), c0, 1, 0.0
                        loops.append({"s": s_mm + lmm, "kind": "first", "C": sigma * Cl})
                elif sigma * tacc >= 2 * math.pi:          # one more loop the same way: the habit tightens
                    nl += 1
                    gF = grow * (1.0 + learn * F)              # a habit that has formed before forms faster
                    Cl = min(Cl + gF * Cl * (1 - Cl / cm) + 0.5 * c0, cm)
                    tacc -= sigma * 2 * math.pi
                    loops.append({"s": s_mm + lmm, "kind": "loop", "C": sigma * Cl, "n": nl})
                elif sigma * tacc <= -relapse_turn:        # turned against it: the habit loosens
                    Cl *= relapse
                    tacc = 0.0
                    loops.append({"s": s_mm + lmm, "kind": "relapse", "C": sigma * Cl})
                    if Cl < c0:
                        sigma, Cl, nl = 0.0, 0.0, 0
            H = float(nl)
        # paper memory: take on part of the state an older stretch left here
        took = 0.0
        if tree is not None and recall > 0 and mix > 0 and rel_left <= 0 and s_mm > first_free \
                and s_mm - last_recall > recall_gap:
            S = np.vstack(st)[:-lag]
            d, j = tree.query(p[-1], k=1)
            if d < recall and (s_mm - S[j, 3]) > recall_gap:
                f = mix * (1 - 0.5 * d / recall)
                Ao, Ho, So, _ = S[j]
                if habit == "loops":
                    if abs(Ao) > Cl:                       # an older, stronger habit comes back
                        sg = 1.0 if Ao > 0 else -1.0
                        Cl = (Cl + f * (abs(Ao) - Cl)) if sg == sigma else f * abs(Ao)
                        sigma = sg
                    else:                                  # an older, calmer stretch loosens it
                        Cl += f * (abs(Ao) - Cl)
                A += f * (Ao - A)
                H += f * (Ho - H)
                spin += f * (So - spin)
                took = f
                last_recall = s_mm + lmm
                if not recalls or s_mm - recalls[-1]["s"] > 2 * recall:
                    recalls.append({"s": s_mm, "pos": [float(v) for v in p[-1]], "A_old": float(Ao), "H_old": float(Ho),
                                    "spin_old": float(So), "j": int(j)})
        spin *= 0.5 ** (lmm / spin_half)
        rel_left = max(rel_left - lmm, 0.0)
        press_run = press_run + lmm if (press > press_on and coil > 0.6) else 0.0
        if press_run > press_hold and not spent:
            knots.append({"s": s_mm + lmm, "pos": [float(v) for v in p[-1]], "sign": 1.0 if C >= 0 else -1.0,
                          "C": C, "coil_mm": press_run, "F": F})
            spin += transfer * C / R
            A = 0.0
            Cl, tacc, nl = keep * Cl, 0.0, 0
            C_prev = 0.0
            H = keep * H
            F += 1
            rel_left = release / (1.0 + tire * (F - 1))
            press_run = 0.0
        toks_prev = c
        pts.append(p[1:])
        sp = s_mm + np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))
        Ad = A if habit == "leaky" else sigma * Cl
        st.append(np.column_stack([np.full(len(sp), Ad), np.full(len(sp), H), np.full(len(sp), spin), sp]))
        head = float(gm.end_heading(cb, head))
        pos = p[-1]
        s_mm += lmm
        lprev = lmm
        rec.append((s_mm, min(coil, 1.0), H, press, spin, 1.0 if rel_left > 0 else 0.0, took))
    P_ = np.vstack(pts)
    seg = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))]
    R_ = np.array(rec)
    sc = R_[:, 0] * (seg[-1] / max(R_[-1, 0], 1e-9))
    ch = {"acc_curl": np.interp(seg, sc, R_[:, 1]), "acc_habit": np.interp(seg, sc, R_[:, 2]),
          "acc_press": np.interp(seg, sc, R_[:, 3]), "acc_spin": np.interp(seg, sc, R_[:, 4]),
          "acc_rel": R_[np.clip(np.searchsorted(sc, seg, side="left"), 0, len(sc) - 1), 5],
          "acc_recall": np.interp(seg, sc, R_[:, 6]), "acc_s": seg}
    knot = np.zeros(len(seg))
    for k in knots:
        L0 = max(min(k["coil_mm"], knot_len), 4.0)
        u = (seg - (k["s"] - 0.5 * L0)) / (0.5 * L0)
        knot = np.maximum(knot, np.clip(1 - np.abs(u) ** 2, 0, 1))
    ch["acc_knot"] = knot
    for r_ in recalls:          # the arc position the memory came from
        r_["from_s"] = float(seg[min(r_.pop("j"), len(seg) - 1)])
    return P_, ch, {"knots": knots, "recalls": recalls, "loops": loops, "length_mm": float(seg[-1])}


PARAMS = [
    P("hand", "ref", "river_belt", "the hand that speaks every token", kind="hand"),
    P("length", "float", 9.0, "line length, R units", min=0.3, max=60.0),
    P("scale", "float", 0.45, "gesture scale R × the box's research-frame scale (0.95·diagonal)", min=0.05, max=4.0),
    P("K", "int", 8, "proposals per chunk", min=1, max=40),
    P("step", "float", 0.3, "sampling step, mm", min=0.05, max=2.0),
    P("chunk", "float", 0.06, "longest chunk between decisions, R", min=0.01, max=2.0),
    P("clear", "float", 2.0, "a free line keeps this far from its own past, mm", min=0.1, max=20.0),
    P("h0", "float", 0.3, "leaky: habit gain at the start", min=0.0, max=3.0),
    P("h_len", "float", 0.25, "leaky: habit growth per R of line", min=0.0, max=10.0),
    P("h_use", "float", 1.5, "leaky: habit growth per R spent curling at c_max", min=0.0, max=40.0),
    P("lam", "float", 0.08, "leaky: turning memory length, R", min=0.005, max=2.0),
    P("c_max", "float", 32.0, "tightest curl, κR (coil radius = R / c_max)", min=2.0, max=400.0),
    P("habit", "choice", "loops", "leaky: curl = H·A, runs away past H = 1 | loops: each completed loop the same "
      "way tightens the curl (logistic), a counter-turn loosens it", choices=("leaky", "loops")),
    P("c0", "float", 3.0, "loops: curl (κR) the first loop leaves", min=0.0, max=100.0),
    P("grow", "float", 0.45, "loops: logistic growth of the curl per completed loop", min=0.0, max=4.0),
    P("learn", "float", 1.0, "loops: growth multiplier added per earlier break (a known habit forms faster)",
      min=0.0, max=10.0),
    P("relapse", "float", 0.5, "loops: share of the curl kept after a counter-turn", min=0.0, max=1.0),
    P("knot_len", "float", 14.0, "longest stretch of a choked coil that becomes mass, mm (short = a round bead)",
      min=2.0, max=200.0),
    P("relapse_turn", "float", 3.1416, "loops: counter-turning (rad) that counts as a relapse", min=0.1, max=12.0),
    P("c_rate", "float", 1.0, "fastest the curl may tighten, κR per mm of line (0 = free runaway)", min=0.0,
      max=50.0),
    P("keep", "float", 0.0, "share of the curl kept after a break (leaky: of H)", min=0.0, max=1.0),
    P("transfer", "float", 4.0, "path spin → nib spin gain at a break", min=0.0, max=40.0),
    P("spin_half", "float", 35.0, "nib spin half-life, mm", min=1.0, max=1000.0),
    P("release", "float", 40.0, "straight run after a break, mm", min=0.0, max=500.0),
    P("release_damp", "float", 0.35, "κ factor during the release", min=0.0, max=1.0),
    P("press_r", "float", 3.0, "self-density radius, mm", min=0.3, max=30.0),
    P("press_on", "float", 0.45, "press over which a coil is choking", min=0.01, max=1.0),
    P("press_hold", "float", 30.0, "mm of choking coil before the knot", min=0.5, max=500.0),
    P("tire", "float", 0.35, "fatigue per break: next coil tighter by this share, next release shorter",
      min=0.0, max=4.0),
    P("exhaust", "int", 2, "after this many breaks the habit is spent: H = 0, the line goes free", min=1, max=40),
    P("recall", "float", 6.0, "paper memory radius: an older stretch this close (mm) lends its state", min=0.0,
      max=100.0),
    P("recall_gap", "float", 150.0, "only stretches at least this much older (mm of line) are remembered",
      min=0.0, max=5000.0),
    P("mix", "float", 0.8, "share of the older stretch's state taken at a recall", min=0.0, max=1.0),
    P("stereo", "float", 0.6, "how much of the hand's own curvature the full curl suppresses", min=0.0, max=1.0),
    P("route", "choice", "ltr", "composition only: centre | ltr (a target walking left → right)",
      choices=("centre", "ltr")),
    P("pull", "float", 6.0, "how hard the composition target is followed", min=0.0, max=20.0),
    P("look", "float", 15.0, "look-ahead that keeps the line off the paper edge, mm", min=0.0, max=100.0),
    P("edge_k", "float", 40.0, "turn (κR) toward the inside when the edge is ahead (not remembered)", min=0.0,
      max=400.0),
]


@voice("accrue_walk", params=PARAMS,
       doc="one line whose own accumulated turning, habit, self-density, breaks and paper memory change its "
           "gesture type")
def accrue_walk(ctx, **kw):
    hand = kw.pop("hand")
    g = ctx.use("hand", hand)
    rng = np.random.default_rng([ctx.seed, 0xACC0E])
    x0, y0, w, h = ctx.box
    R = kw.pop("scale") * 0.95 * float(np.hypot(w, h))
    P_, ch, ev = walk(g, rng, R=R, box=ctx.box, **kw)
    meta = {"voices": [hand], "R_mm": R, "accrue": ev}
    return [Mark(P_, {"voice": np.zeros(len(P_)), **ch}, meta)]
