# FROZEN from research commit ecd64f8: tools/gesture/gesture/kit/arrangers_found_play.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Round 13 phase 2, Study A `found_play`: the rules played over found ground,
with contagion's catch and mutual's call and response between the hands.

Ian's gate (2026-10-18): "split the studies by axis". Study A is Axis I:
the `rules` arranger's breakable rules (his "keeper"; "amazing" for the four
hands sheet) over found ground, plus contagion's catch ("I like it a lot")
and mutual's dense call and response (the soup dud: "Really like this. It's
getting somewhere"). Density is wanted, not a failure of legibility.

Every made line, in turn:

    R3 enter    from the edge with an orthogonal step, or born of a found
                contour's end (rules' `entry`, unchanged)
    ANSWER      or, when an earlier line has stopped in the air near enough
                (its call), the line answers it: it starts beside the
                caller's last stretch, converges on its endpoint, and grows
                beyond it at a tangent before taking up its own hand.
                A line that does not take the call refuses it (logged)
    R4 + CATCH  the line walks the paper with contagion's walk: a contact is
                allowed only where the line curves (R4; straight meets
                straight breaks it), and a contact infects the line with the
                regime's grammar, generated fresh and carried along its own
                path, then shed in whole elements:
                  river  Langbein & Leopold bends measured on the far river
                  chart  the chart's ruling and its spikes (contagion's plate
                         grammar, ticks at the chart's own spike height)
                  hand   an earlier made line's HAND: a fresh stretch of that
                         hand's own grammar, integrated about the own path.
                         A line listens to the last `answers` lines before it
                         and refuses the rest (crossing them is logged)
    R2 exit     the last exit from found matter becomes the last found
                contour it touched, then stops in the air: the next call
    R1 weight   heavy over found ink and while riding, a hairline in the
                blank; a long ride carries its weight out (break). Caught
                chart needles retain their thin pen over found ink (break).
    R5 cover    a torn cover on the densest passage after `cover_after`
                lines; it cuts the made lines too when they own the passage

Channel `neg` on made marks: 0 own, 1 ride (found or made), 3 entry step,
4 ride by break (unused here: R4 breaks ride as 1), 5 R2 motif, 6 carried
river, 7 carried chart rule, 8 chart spike, 9 carried hand, 10 answer trace.
The log is `marks[0].meta["rules"]["log"]` (rules' events) plus
`marks[0].meta["found_play"]` (calls, answers, refusals, infections).
Ink with `oehlen_found_ink`.
"""
from __future__ import annotations

import math

import numpy as np

from ._research import grammar as gm
from .arrangers_contagion import contagion_walk, plate_grammar, river_grammar
from .arrangers_oehlen_found import (FLEXOKI, Ground, arclen, bridge, clip_rect, cover_polygon, rect_polygon,
                                     resample, rotate, tangents)
from .arrangers_rules import BREAKS, RULES, _emit, _kind_of, densest, entry, finish_line, turning
from .core import Mark, P, arranger

# contagion's per-point codes → this arranger's `neg` codes
_NEG = {0: 0.0, 1: 1.0, 2: 1.0, 3: 6.0, 4: 7.0, 5: 8.0, 6: 1.0, 9: 9.0}
HAND_RIDE, HAND_CODE = 6, 9


def chart_grammar(rows, step: float = 0.2) -> dict:
    """The chart's ruling with signed needle heights, base width and spike spacing."""
    g = plate_grammar(rows)
    a = math.radians(g["angle_deg"])
    hs, widths, gaps = [], [], []
    for l in rows:
        q = rotate(resample(np.asarray(l, float), step), np.zeros(2), -math.degrees(a))
        dev = q[:, 1] - np.median(q[:, 1])
        big = np.abs(dev) > 1.0
        cut = np.flatnonzero(np.diff(big.astype(int))) + 1
        runs = np.split(np.arange(len(q)), cut)
        xs = []
        for r in runs:
            if len(r) and big[r[0]]:
                k = r[np.argmax(np.abs(dev[r]))]
                hs.append(float(dev[k]))
                widths.append(abs(float(q[r[-1], 0] - q[r[0], 0])))
                xs.append(float(q[k, 0]))
        gaps += list(np.diff(sorted(xs)))
    if hs:
        g["tick_mm"] = round(float(np.clip(np.median(np.abs(hs)), 1.5, 9.0)), 2)
        g["needle_mm"] = [round(float(np.clip(np.median(np.abs([h for h in hs if h * side > 0])),
                                               1.5, 9.0)) * side, 2)
                          for side in (-1, 1) if any(h * side > 0 for h in hs)]
        g["needle_base_mm"] = round(float(np.clip(np.median(widths), 0.3, 1.0)), 2)
    g["pitch_mm"] = round(float(np.clip(np.median(gaps), 4.0, 60.0)), 2) if gaps else 12.0
    g["spikes"] = len(hs)
    return g


def chart_needles(points, codes, g):
    """Replace the walk's out-and-back ticks with narrow, signed chart needles.

    Keep every junction and channel in the contiguous line. The base fits between
    the adjacent carrier samples; alternating the measured sides avoids turning a
    two-sided measurement chart into a one-sided comb. No change to contagion's
    plate grammar is needed (its short leader ticks remain appropriate there).
    """
    p = np.array(points, float, copy=True)
    sides = g.get("needle_mm", [-g.get("tick_mm", 1.7), g.get("tick_mm", 1.7)])
    starts = np.flatnonzero((codes[1:] == 5) & (codes[:-1] != 5)) + 1
    for n, i in enumerate(starts):
        if i < 2 or i + 2 >= len(p) or codes[i + 1] != 5:
            continue
        base = (p[i - 1] + p[i + 1]) / 2
        if np.linalg.norm(p[i - 1] - p[i + 1]) > 1e-6:
            continue                         # a trimmed tick is not a whole needle
        t = p[i + 2] - p[i - 2]
        t /= max(float(np.linalg.norm(t)), 1e-9)
        half = min(g.get("needle_base_mm", 0.6) / 2,
                   0.8 * float(np.linalg.norm(base - p[i - 2])),
                   0.8 * float(np.linalg.norm(p[i + 2] - base)))
        p[i - 1], p[i + 1] = base - t * half, base + t * half
        p[i] = base + sides[n % len(sides)] * np.array([-t[1], t[0]])
    return p


def hand_gen(g: gm.Grammar, R_mm: float, *, step: float, pull: float, axis_mm: float, amp_max: float):
    """A carried hand: `gen(rng, length_mm)` → valley-frame xy. A fresh stretch of the hand's own
    chain (its training-length strokes, one after another), integrated with a pull back to the
    axis so it travels along x as the river does, detrended about a slow axis, cut to start at an
    axis crossing. Its lateral reach is capped at `amp_max` mm (scaled down whole, never clipped)."""
    from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415

    def gen(rng, length_mm):
        toks: list = []
        need = (length_mm * 2.5 + 40.0) / max(R_mm, 1e-6)
        guard = 0
        while gm.stroke_length(toks) < need and guard < 200:
            guard += 1
            Ls = g.stroke_lengths or [0.1]
            L = max(float(Ls[int(rng.integers(len(Ls)))]), 1e-3)
            t, _ = gm.generate_tokens(g, rng, length=L, p_follow=gm.P_FOLLOW, end_fit=gm.END_FIT)
            if toks and t and t[0][0] == "corner":
                t = t[1:]
            toks += t
        th, x, y = 0.0, 0.0, 0.0
        pts = [(0.0, 0.0)]
        for t in toks:
            if t[0] == "corner":
                th += float(t[1])
                continue
            lmm = t[1] * R_mm
            n = max(int(math.ceil(lmm / step)), 1)
            h = lmm / n
            for i in range(n):
                f = (i + 0.5) / n
                k = (t[2] + (t[3] - t[2]) * f) / R_mm
                th += h * (k - pull * math.sin(th))
                x += h * math.cos(th)
                y += h * math.sin(th)
                pts.append((x, y))
        xy = np.asarray(pts)
        xy[:, 1] -= gaussian_filter1d(xy[:, 1], 3 * axis_mm / step, mode="nearest")
        amp = float(np.max(np.abs(xy[:, 1]))) if len(xy) else 0.0
        if amp > amp_max:
            xy[:, 1] *= amp_max / amp
        zc = np.flatnonzero(np.diff(np.sign(xy[:, 1])) != 0)
        a = int(zc[0]) + 1 if len(zc) else 0
        xy = xy[a:] - [xy[a, 0], 0.0]
        xy[0, 1] = 0.0
        k = np.flatnonzero(xy[:, 0] >= length_mm)
        return xy[: int(k[0]) + 1] if len(k) else xy
    return gen


def _xy(p):
    return [round(float(p[0]), 1), round(float(p[1]), 1)]


def answer_bridge(a, ta, b, tb, step, bounds):
    """Keep an answer's Bézier inside the paper by shortening its handles.

    Its endpoints and tangent directions stay put. Bounded control points give
    a bounded curve, without clipping samples into a stray run along the edge.
    Leave already contained bridges exactly as they were.
    """
    q = bridge(a, ta, b, tb, step)
    lo, hi = np.asarray(bounds[:2]), np.asarray(bounds[2:])
    if not len(q) or (np.all(q >= lo) and np.all(q <= hi)):
        return q
    h = float(np.linalg.norm(b - a)) / 2.6

    def factor(p, t):
        reach = h
        for ax in range(2):
            if abs(t[ax]) > 1e-9:
                edge = hi[ax] if t[ax] > 0 else lo[ax]
                reach = min(reach, max(0.0, 0.95 * (edge - p[ax]) / t[ax]))
        return reach / max(h, 1e-9)

    return bridge(a, ta * factor(a, ta), b, tb * factor(b, -tb), step)


@arranger("found_play", params=[
    P("found", "int", 2, "the first n parts are found matter, pasted first", min=0, max=6),
    P("found_boxes", "floats", [0.5, 0.5, 0.9, 0.9, 0.0],
      "per found part: cx, cy, w, h (shares of the frame), angle (deg) of its pasted rectangle"),
    P("made_boxes", "floats", [], "per made line, cycling: cx, cy, w, h (shares); empty = the sheet box"),
    P("lines", "int", 2, "how many of the made parts draw (the rest wait): density", min=1, max=12),
    P("rules", "str", "R1,R2,R3,R4,R5", "which rules are in play (comma list)"),
    P("breaks", "bool", True, "rules may break"),
    P("step", "float", 0.3, "resampling step, mm", min=0.1, max=1.0),
    # contact (rules R4 + contagion)
    P("capture", "float", 5.0, "a contour this near (mm) and aligned can take the line", min=0.2, max=30.0),
    P("align", "float", 0.55, "|cos| between headings needed for contact", min=0.0, max=1.0),
    P("listen_k", "float", 0.05, "R4: the line listens while it turns at least this much (rad/mm)", min=0.0,
      max=2.0),
    P("straight_k", "float", 0.012, "R4 break: both stretches turn less than this (rad/mm)", min=0.0, max=1.0),
    P("listen_win", "float", 4.0, "R4: turning is measured over ± this many mm", min=0.5, max=40.0),
    P("ride", "float", 18.0, "mean contact ride, mm", min=1.0, max=200.0),
    P("ride_sd", "float", 0.45, "log-normal spread of rides and infections", min=0.0, max=1.5),
    P("min_ride", "float", 7.0, "shorter contacts are refused, mm", min=0.5, max=100.0),
    P("ride_gap", "float", 0.9, "rides trace this far beside the contour, mm", min=0.0, max=5.0),
    P("return_mm", "float", 30.0, "after a contact the line swims back to its own path over this, mm", min=1.0,
      max=400.0),
    P("ramp", "float", 2.0, "tangent bridge into and out of a contact, mm", min=0.0, max=20.0),
    P("max_offset", "float", 18.0, "a ride ends before it carries the line this far from its path, mm", min=1.0,
      max=300.0),
    P("catches", "int", 4, "most contacts (infections) per line", min=0, max=20),
    P("immune_mm", "float", 50.0, "after an infection ends the line cannot re-catch that regime for this long",
      min=0.0, max=500.0),
    # the grammars carried
    P("full_river", "float", 45.0, "river infection at full strength, mm", min=0.0, max=600.0),
    P("decay_river", "float", 80.0, "river infection wearing off, mm", min=1.0, max=600.0),
    P("full_chart", "float", 25.0, "chart infection at full strength, mm", min=0.0, max=600.0),
    P("decay_chart", "float", 35.0, "chart infection wearing off (its ruling), mm", min=1.0, max=600.0),
    P("tick_linger", "float", 1.0, "the chart's spikes outlast its ruling by this factor", min=1.0, max=5.0),
    P("spike_space", "float", 1.5, "carried spikes are this many times the chart's own spike spacing apart",
      min=0.3, max=10.0),
    P("full_hand", "float", 35.0, "a caught hand at full strength, mm", min=0.0, max=600.0),
    P("decay_hand", "float", 60.0, "a caught hand wearing off, mm", min=1.0, max=600.0),
    P("hand_amp", "float", 7.0, "a carried hand reaches at most this far either side of the own path, mm",
      min=0.5, max=40.0),
    P("hand_scale", "float", 0.3, "a carried hand is drawn at this share of its caller's own scale", min=0.05,
      max=2.0),
    P("hand_pull", "float", 0.2, "a carried hand's pull back to the own path's heading, per mm", min=0.0,
      max=2.0),
    P("own_mm", "float", 6.0, "own stretches between caught elements while wearing off, mean mm", min=1.0,
      max=60.0),
    P("rule_tol", "float", 3.5, "a ruled run may straighten the own path by this much, mm", min=0.2, max=20.0),
    P("snap", "float", 8.0, "a ruled run within this many degrees of the ruling snaps to it", min=0.0, max=45.0),
    P("rule_shared", "float", 9.0, "while two regimes are carried, a ruled run is at most this long, mm",
      min=6.0, max=200.0),
    P("omega_max", "float", 120.0, "a carried river swings at most this far from its axis, deg", min=30.0,
      max=160.0),
    P("river_axis", "float", 10.0, "valley scale the river's heading is measured about, mm", min=3.0, max=60.0),
    # call and response
    P("answers", "int", 2, "a line listens to the last n lines before it (catches their hands, answers their "
      "calls) and refuses the rest", min=0, max=12),
    P("answer_p", "float", 0.6, "chance a line takes the last call (else it refuses it)", min=0.0, max=1.0),
    P("call_reach", "float", 90.0, "a call (a line's end in the air) is heard this far, mm", min=0.0, max=400.0),
    P("trace_mm", "float", 18.0, "an answer traces the caller's last stretch this long, mm", min=2.0, max=200.0),
    # R1 / R2 / R3 / R5
    P("min_run", "float", 14.0, "R1: a weight change holds at least this long, mm", min=0.0, max=200.0),
    P("carry_min", "float", 28.0, "R1 break: a ride at least this long carries its weight out", min=1.0,
      max=400.0),
    P("carry_k", "float", 1.0, "R1 break: carried weight = this × the ride's length", min=0.0, max=5.0),
    P("region_pad", "float", 6.0, "R1: this near found ink counts as over it, mm", min=0.0, max=30.0),
    P("exit_pad", "float", 10.0, "R2: the line has left the found this far from found ink, mm", min=1.0,
      max=60.0),
    P("motif_len", "float", 60.0, "R2: the carried motif's length, mm", min=5.0, max=300.0),
    P("lead", "float", 10.0, "R2: the motif starts this far past the exit, mm", min=0.0, max=100.0),
    P("sigma", "float", 1.0, "R2: the found contour's turning is smoothed over this, mm", min=0.0, max=40.0),
    P("motif_scale", "float", 1.5, "R2: the found contour's turning played this many times larger", min=0.25,
      max=10.0),
    P("loops_r", "float", 2.2, "R2 (nothing touched): loop radius, mm", min=0.1, max=20.0),
    P("loops_p", "float", 5.5, "R2 (nothing touched): loop period, mm", min=0.5, max=50.0),
    P("inset", "float", 4.0, "R3: the edge is this far inside the paper's edge, mm", min=0.0, max=40.0),
    P("grow_reach", "float", 22.0, "R3 break: a found end this near the line's start bears it, mm", min=0.0,
      max=200.0),
    P("cover_after", "int", 1, "R5: the cover comes after this many made lines (-1 = none)", min=-1, max=12),
    P("cover_wh", "floats", [24.0, 72.0], "R5: cover width, height, mm"),
    P("cover_tilt", "float", 8.0, "R5: tilt ±deg", min=0.0, max=60.0),
    P("cover_margin", "float", 14.0, "R5: covers keep this far inside the sheet, mm", min=0.0, max=80.0),
    P("made_share", "float", 0.45, "R5 break: the densest passage is this share made ink or more", min=0.0,
      max=1.0),
    P("cover_edge", "choice", "drawn", "R5: none | drawn (its outline in the found pen)",
      choices=("none", "drawn")),
    P("min_stub", "float", 4.0, "a cut piece shorter than this (mm) is dropped", min=0.0, max=50.0),
    P("found_ink", "str", "blue", "Flexoki pen for the found matter"),
    P("found_pen", "float", 0.3, "found pen, mm", min=0.05, max=3.0),
    P("made_ink", "str", "black", "Flexoki pen for the made lines"),
    P("bold_pen", "float", 0.9, "R1: heavy pen, mm", min=0.05, max=3.0),
    P("hair_pen", "float", 0.3, "R1: hairline pen, mm", min=0.05, max=3.0),
], doc="Study A: rules' breakable rules over found ground; a contact infects the line with the regime's grammar "
        "(river, chart, or an earlier line's hand), carried away and shed whole; lines answer and refuse each "
        "other's calls")
def found_play(ctx, parts, *, found, found_boxes, made_boxes, lines, rules, breaks, step, capture, align, listen_k,
               straight_k, listen_win, ride, ride_sd, min_ride, ride_gap, return_mm, ramp, max_offset, catches,
               immune_mm, full_river, decay_river, full_chart, decay_chart, tick_linger, spike_space, full_hand, decay_hand,
               hand_amp, hand_scale, hand_pull, own_mm, rule_tol, snap, rule_shared, omega_max, river_axis, answers, answer_p,
               call_reach, trace_mm, min_run, carry_min, carry_k, region_pad, exit_pad, motif_len, lead, sigma,
               motif_scale, loops_r, loops_p, inset, grow_reach, cover_after, cover_wh, cover_tilt, cover_margin,
               made_share, cover_edge, min_stub, found_ink, found_pen, made_ink, bold_pen, hair_pen):
    from shapely import contains_xy  # noqa: PLC0415
    from shapely.geometry import LineString, MultiLineString  # noqa: PLC0415
    for nm in (found_ink, made_ink):
        if nm not in FLEXOKI:
            raise ValueError(f"found_play: unknown ink {nm!r}; choose from {sorted(FLEXOKI)}")
    on = {r.strip() for r in rules.split(",") if r.strip()}
    bad = on - set(RULES)
    if bad:
        raise ValueError(f"found_play: unknown rule(s) {sorted(bad)}; choose from {sorted(RULES)}")
    W, H = ctx.frame
    found = min(found, len(parts))
    f_parts, m_parts = parts[:found], parts[found:found + max(int(lines), 1)]
    log: list[dict] = []
    play: dict = {"calls": [], "answers": [], "refusals": [], "infections": []}

    # 1. found matter, pasted and cut to its rectangles (as rules)
    fb = [found_boxes[i:i + 5] for i in range(0, len(found_boxes) - 4, 5)] or [[0.5, 0.5, 0.9, 0.9, 0.0]]
    found_lines, kinds = [], {}
    for k, p in enumerate(f_parts):
        cx, cy, bw, bh, ang = fb[min(k, len(fb) - 1)]
        cx, cy, bw, bh = cx * W, cy * H, bw * W, bh * H
        rect = rect_polygon(cx, cy, bw, bh, ang)
        kinds[p.index] = _kind_of(p)
        for m in p.run((cx - bw / 2, cy - bh / 2, bw, bh)):
            q = rotate(m.points, np.array([cx, cy]), ang)
            for piece in clip_rect([q], rect, min_stub):
                ext = float(np.linalg.norm(piece.max(axis=0) - piece.min(axis=0)))
                found_lines.append((p.index, piece, ext < 5.0))      # short marks are lettering: never ridden
    ridable = [(pi, l) for pi, l, txt in found_lines if not txt]
    G = Ground([l for _, l in ridable], step, tag=1)
    owner = [pi for pi, l in ridable if len(l) >= 2 and arclen(np.asarray(l))[-1] > 4 * step]
    found_kind = dict(kinds)

    def pads(r):
        out = []
        for pi in kinds:
            ls = [l for q, l, txt in found_lines if q == pi and not txt and len(l) >= 2]
            if ls:
                out.append((pi, MultiLineString([x.tolist() for x in ls]).buffer(r, 8)))
        return out

    def regions(pp):
        def f(points):
            reg = np.full(len(points), -1)
            for pi, poly in pp:
                hit = contains_xy(poly, points[:, 0], points[:, 1])
                reg[(reg < 0) & hit] = pi
            return reg
        return f
    r1_region, r2_region = regions(pads(region_pad)), regions(pads(exit_pad))

    # 2. the regimes a contact can catch, and their grammars
    river = [l for pi, l in ridable if kinds[pi] == "river"]
    chart = [l for pi, l in ridable if kinds[pi] == "chart" and arclen(np.asarray(l))[-1] > 30.0]
    grounds, grammars = {}, {}
    if len(river):
        try:
            grammars["river"] = river_grammar(river, axis_mm=river_axis, omega_max=omega_max)
            grounds["river"] = Ground(river, step, tag=1)
        except ValueError:
            pass
    tick_pitch = 6.3
    if chart:
        grammars["plate"] = chart_grammar(chart)
        tick_pitch = grammars["plate"]["pitch_mm"] * spike_space
        grounds["plate"] = Ground(chart, step, tag=2)
    k_found = {r: [turning(l, step, listen_win) for l in Gr.lines] for r, Gr in grounds.items()}
    full = {"river": full_river, "plate": full_chart}
    decay = {"river": decay_river, "plate": decay_chart}

    # 3. made lines, in turns; the cover comes between them
    mb = [made_boxes[i:i + 4] for i in range(0, len(made_boxes) - 3, 4)]
    made, covers = [], []
    bounds = (ctx.box[0], ctx.box[1], ctx.box[0] + ctx.box[2], ctx.box[1] + ctx.box[3])

    def place_cover():
        res = densest({"found": [l for _, l, _ in found_lines], "made": [d["pts"] for d in made]}, ctx.frame,
                      *(list(cover_wh) + [34.0, 50.0])[:2], cover_margin)
        if res is None:
            return
        c, _, share = res
        poly = cover_polygon(ctx.rng("cover", len(covers)), c, *(list(cover_wh) + [34.0, 50.0])[:2], "torn",
                             cover_tilt)
        cuts_made = bool(breaks and share >= made_share)
        covers.append((poly, cuts_made))
        log.append({"rule": "R5", "event": "break" if cuts_made else "fire", "line": len(made), "xy": _xy(c),
                    "s_mm": 0.0, "why": (BREAKS["R5"] if cuts_made else "a torn cover on the densest passage; it "
                                         "cuts the found only") + f" (made share {share:.2f})"})
        if cuts_made:
            for d in made:
                d.setdefault("cut_by", []).append(len(covers) - 1)

    for li, p in enumerate(m_parts):
        if "R5" in on and cover_after == li:
            place_cover()
        box = ctx.box
        if mb:
            cx, cy, bw, bh = mb[li % len(mb)]
            box = (cx * W - bw * W / 2, cy * H - bh * H / 2, bw * W, bh * H)
        rng = ctx.rng("made", p.index)
        hand_id = (p.spec.get("voice", {}) if hasattr(p, "spec") else {}).get("hand")
        length_R = float((p.spec.get("voice", {}) if hasattr(p, "spec") else {}).get("length", 3.0))
        for m in p.run(box):
            M = resample(m.points, step)
            R_mm = float(arclen(M)[-1]) / max(length_R, 0.2)
            listened = made[-answers:] if answers > 0 else []
            refused = made[:len(made) - len(listened)]
            pre, pre_tag, info = None, None, {}
            # ANSWER: the last call heard (an earlier line's end in the air), taken or refused
            call = None              # the most recent line listened to whose end is within earshot
            for d in reversed(listened):
                e = d["pts"][-1]
                if min(float(np.linalg.norm(M[0] - e)), float(np.linalg.norm(M[-1] - e))) <= call_reach:
                    call = d
                    break
            if call is not None:
                e = call["pts"][-1]
                if rng.random() < answer_p:
                    if np.linalg.norm(M[-1] - e) < np.linalg.norm(M[0] - e):
                        M = M[::-1].copy()
                    cp = resample(call["pts"], step)
                    k = max(int(round(min(trace_mm, (len(cp) - 1) * step) / step)), 3)
                    tail = cp[-k - 1:]
                    t = tangents(tail, 3)
                    # A wider trace closes onto the actual endpoint, then grows
                    # beyond it. A uniform offset merely looked like another ride.
                    gap = 2 * ride_gap * (1 - np.linspace(0, 1, len(tail)))
                    tail = tail + gap[:, None] * np.c_[-t[:, 1], t[:, 0]]
                    tip = tail[-1].copy()
                    forward = min(8.0, trace_mm / 2)
                    lo, hi = np.array(bounds[:2]), np.array(bounds[2:])
                    for ax in range(2):
                        if abs(t[-1, ax]) > 1e-9:
                            edge = hi[ax] if t[-1, ax] > 0 else lo[ax]
                            forward = min(forward, max(0.0, 0.8 * (edge - tip[ax]) / t[-1, ax]))
                    extension = resample(np.array([tip, tip + t[-1] * forward]), step)
                    tail = np.vstack([tail, extension[1:]])
                    # bring the line toward the call (at most 60 mm, inside its box), so the bridge stays short
                    want = tail[-1] + t[-1] * 6.0 - M[0]
                    lo, hi = np.array(box[:2]), np.array(box[:2]) + box[2:]
                    for f in (1.0, 0.7, 0.45, 0.25, 0.0):
                        Mt = M + f * want * min(1.0, 60.0 / max(float(np.linalg.norm(want)), 1e-9))
                        if np.all(Mt.min(axis=0) >= lo - 1e-6) and np.all(Mt.max(axis=0) <= hi + 1e-6):
                            M = Mt
                            break
                    br = answer_bridge(tail[-1], t[-1], M[0], tangents(M, 3)[0], step, bounds)
                    pre = np.vstack([tail, br]) if len(br) else tail
                    pre_tag = 10.0
                    info = {"answers": call["line"]}
                    play["answers"].append({"line": li, "to": call["line"], "xy": _xy(tail[0]),
                                            "root": _xy(tip), "departure": _xy(tail[-1])})
                    log.append({"rule": "CALL", "event": "fire", "line": li, "xy": _xy(tail[0]), "s_mm": 0.0,
                                "why": f"answers line {call['line']}'s call: grows out of its end"})
                else:
                    play["refusals"].append({"line": li, "to": call["line"], "what": "call", "xy": _xy(e)})
                    log.append({"rule": "CALL", "event": "break", "line": li, "xy": _xy(e), "s_mm": 0.0,
                                "why": f"refuses line {call['line']}'s call"})
            if pre is None and "R3" in on:
                pieces, M, info = entry(M, G, owner, found_kind, rng, frame=ctx.frame, box=ctx.box, step=step,
                                        inset=inset, grow_reach=grow_reach, breaks=breaks, ride=ride,
                                        ride_gap=ride_gap, line_id=li, log=log)
                if pieces:
                    pre, pre_tag = pieces[0][0][:-1], float(pieces[0][1])
            # R4 + CATCH: the walk, against the found regimes and the hands listened to
            M = resample(M, step)
            k_own = turning(M, step, listen_win)
            gr, gm_, fl, dc = dict(grounds), dict(grammars), dict(full), dict(decay)
            kf = dict(k_found)
            for d in listened:
                if d.get("hand_gen") is None:
                    continue
                key = f"line{d['line']}"
                gr[key] = Ground([d["pts"]], step, tag=3)
                kf[key] = [turning(l, step, listen_win) for l in gr[key].lines]
                gm_[key] = {"gen": d["hand_gen"], "code": HAND_CODE, "ride_code": HAND_RIDE, "hand": d["hand"]}
                fl[key], dc[key] = full_hand, decay_hand

            def gate(i, reg, j, i0, c, k_own=k_own, kf=kf):
                if "R4" not in on:
                    return True
                i = min(i, len(k_own) - 1)
                if k_own[i] >= listen_k:
                    return True
                return bool(breaks and k_own[i] < straight_k and kf[reg][j][min(i0, len(kf[reg][j]) - 1)] < straight_k
                            and abs(c) >= 0.985)
            pts, codes, lg = contagion_walk(
                M, gr, gm_, rng, step=step, capture=capture, align=align, listen=1e6, ignore=0.0, ride=ride,
                ride_sd=ride_sd, min_ride=min_ride, ride_gap=ride_gap, return_mm=return_mm, ramp=ramp,
                max_offset=max_offset, catches=catches, full=fl, decay=dc, tick_linger=tick_linger, own_mm=own_mm,
                rule_tol=rule_tol, snap=snap, tick_pitch=tick_pitch, immune_mm=immune_mm, omega_max=omega_max,
                rule_shared=rule_shared, regimes=tuple(gr), carry=True, gate=gate)
            if "plate" in grammars:
                pts = chart_needles(pts, codes, grammars["plate"])
            tags = np.array([_NEG.get(int(c), 0.0) for c in codes])
            for inf in lg["infections"]:
                reg = inf["regime"]
                what = {"river": "the river", "plate": "the chart"}.get(reg) or f"line {reg[4:]}'s hand"
                play["infections"].append({"line": li, "caught": reg, **{k: inf[k] for k in
                                           ("contact", "onset", "end", "carried_mm")}})
                log.append({"rule": "CATCH", "event": "fire", "line": li, "xy": inf["contact"],
                            "s_mm": inf["on_mm"], "why": f"catches {what}; carried {inf['carried_mm']:.0f} mm"})
            if pre is not None and len(pre):
                pts = np.vstack([pre, pts])
                tags = np.r_[np.full(len(pre), pre_tag), tags]
            # refused hands: crossing a line it does not listen to is indifference, logged
            for d in refused:
                try:
                    if LineString(pts).intersects(LineString(d["pts"])):
                        play["refusals"].append({"line": li, "to": d["line"], "what": "crossed"})
                except Exception:          # noqa: BLE001 — a degenerate line simply is not checked
                    pass
            d = {"pts": pts, "tags": tags, "rides": [], "part": p.index, "info": info, "line": li,
                 "hand": hand_id}
            finish_line(d, on=on, G=G, owner=owner, found_kind=found_kind, r1_region=r1_region,
                        r2_region=r2_region, rng=rng, step=step, motif_len=motif_len, lead=lead, sigma=sigma,
                        motif_scale=motif_scale, bounds=bounds, breaks=breaks, log=log, loops_r=loops_r,
                        loops_p=loops_p, min_run=min_run, carry_min=carry_min, carry_k=carry_k)
            needle = d["tags"] == 8
            needle[:-1] |= needle[1:]       # both legs start in the thin pen, including the first base
            if breaks and np.any(needle & d["bold"]):
                if "R1" in on:
                    i = int(np.flatnonzero(needle & d["bold"])[0])
                    log.append({"rule": "R1", "event": "break", "line": li, "xy": _xy(d["pts"][i]),
                                "s_mm": round(float(arclen(d["pts"])[i]), 1),
                                "why": "the caught chart keeps its thin needles over the found"})
                d["bold"][needle] = False
            if hand_id:
                d["hand_gen"] = hand_gen(ctx.use("hand", hand_id), R_mm * hand_scale, step=0.2, pull=hand_pull,
                                         axis_mm=river_axis, amp_max=hand_amp)
            play["calls"].append({"line": li, "xy": _xy(d["pts"][-1])})
            made.append(d)
    if "R5" in on and cover_after >= len(m_parts):
        place_cover()
    out = _emit(ctx, found_lines, made, covers, min_stub, step, found_ink, found_pen, made_ink, bold_pen, hair_pen,
                log, on, breaks)
    if cover_edge == "drawn":
        for poly, _ in covers:
            out.append(Mark(poly, {}, {"part": f_parts[0].index if f_parts else 0, "of_role": "edge",
                                       "ink": found_ink, "pen": min(found_pen, 0.25)}))
    if out:
        play["grammars"] = {k: {kk: vv for kk, vv in v.items() if kk != "gen"} for k, v in grammars.items()}
        out[0] = out[0].evolve(meta={"found_play": play})
    return out
