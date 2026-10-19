# FROZEN from research commit c712045: tools/gesture/gesture/kit/arrangers_arch.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Round 15 thread C `arch`: archaeology — four past keeps, each in a role it never had.

Ian (2026-10-19): "could be nice to give some love to stuff that worked and got left in the past
too and integrate them … keep it experimental, even if slightly more focused, feel free to go on a
limb." The composer is ccolour's (round 14's keeper; its decisions, pen plan and colour events are
IMPORTED from `arrangers_ccolour`, never copied). What changes is who plays which role:

    danced   Hand Drift / the danced chain (round 8 "closest to the idea I had in mind"; round 9
             "save the methods") as T2's TRAVERSE: one long line that crosses the core and the blank
             and belongs to neither. The drift line (matisse → shikasta → lichtenberg, chain joins)
             keeps its own turns, step for step, while a weak pull steers it from one edge region
             to the other (`steer`); the staccato dancer's tempo then weights it (stillness → round
             mass, flow → nib) and it is inked as a nib. Before, a drift line was a blob in a box.
    swell    the bold swell (round 11 "very nice, very promising") as T3's HEAVY INTRUDER, in place
             of ccolour's bars, Ls and stairs: one short hand line whose stresses bloom into round
             masses, at the core's edge, in the foreign pen. Round, never a capsule. Option
             `duet` (the chorus, round 10 "multiple pens"): a second swell voice in a second pen
             that may only stress where the first is quiet nearby (dev_chorus' listening).
    flicker  limb signs (round 12 "super nice. keeper") as T7's FIGURE FLICKER: where a made line
             passes, it stops and writes, small and upright, what a dancer's other limbs did
             during a hold (revisit_glyph's figures, cut out of the host trail), then goes on from
             the same point. The figure rises from wire into nib and falls back: a sign surfaces
             for a moment and returns to line.
    passer   handover / accrue 3966 / belt (round 13 "really good. keep", "love love", "line that
             morphs gesture type") as a line that CHANGES TYPE WHERE IT IS: outside the core it
             speaks its own hand (accrue's free walk 3966, Cohen's meander, or the river belt);
             inside the core it speaks the core's hand, feature by feature (tokens are never
             averaged: each turn comes whole from one hand, with a probability set by how deep in
             the core the pen is). It takes the core's pen while it speaks its hand (T6 by place).

Everything else is ccolour's (found_play core, container, counterweight, pen plan, colour events),
with three round-15 changes: the kappa chart never enters as found matter (retired inside
compositions: rivers and machine lines replace it), the density dial stays in the middle, and the
heavy intruder is always the swell. Every sheet records a `_score.Score` (layers, relations,
decisions) with `ctx.note("score", …)`; ccolour's log travels too, in `marks[0].meta["arch"]`.

Ink with `arch_ink` (renderers_arch.py: wire / nib / swell per mark, pen colour in Ink.meta);
preview with `arrangers_ccolour.render_pens` (pens multiply on paper).
"""
from __future__ import annotations

import copy
import math

import numpy as np

from . import arrangers_ccolour as cc
from ._score import Score
from .arrangers_oehlen_found import arclen, clip_rect, resample
from .core import Mark, P, arranger, get

FAMILIES = ("danced", "swell", "flicker", "passer")
PASSER_FROM = ("free3966", "meander69", "belt")
FLICKER_TRAILS = (("particles", "rfoot"), ("levitation", "lhand"), ("staccato", "head"), ("mantis", "rhand"))
SWELL_HANDS = ("shikasta", "meander69", "marden")


def _u(rng, a, b):
    return float(rng.uniform(a, b))


def _r(v):
    return [round(float(x), 1) for x in v]


def ray_exit(o, d, W, H, m):
    """Where a ray from o along d leaves the paper inset by m × its size (o must be inside)."""
    lo, hi = np.array([m * W, m * H]), np.array([(1 - m) * W, (1 - m) * H])
    o = np.clip(np.asarray(o, float), lo + 1e-6, hi - 1e-6)
    t = min(((hi[k] if d[k] > 0 else lo[k]) - o[k]) / d[k] for k in (0, 1) if abs(d[k]) > 1e-9)
    return o + d * t


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


# ---------------------------------------------------------------------------
# 1. the plan: ccolour's decisions, then the four revived roles
# ---------------------------------------------------------------------------

def plan_arch(rng, W: float, H: float, *, density: float = -1.0, families=FAMILIES, pens: int = 0,
              mode: str = "auto", duet: float = 0.25, hands=None) -> dict:
    """ccolour's composition with the revived families in their new roles (JSON-able)."""
    if density < 0:                                    # the middle of the dial only (round 14's bar)
        density = float(rng.choice([0.2, 0.3, 0.4]))
    plan = cc.decide(rng, W, H, density=density, pens=pens, mode=mode, hands=hands)
    cx, cy, cw, ch = plan["core"]
    plan["play"]["bold_pen"] = min(plan["play"]["bold_pen"], 0.5)   # weight belongs to the swell
    for m in plan["made"]:                   # shorter made lines: the core stays at a middle density
        m["length"] = round(min(m["length"], 1.2 + 0.4 * m["length"]), 1)
    # the kappa chart is retired as found matter inside a composition: a river or a machine line instead
    for f in plan["found"]:
        if f["kind"] != "chart":
            continue
        if rng.random() < 0.6:
            f["kind"] = "river"
            f["voice"] = {"id": "oehlen_found_river", "tile": "SB19", "rank": 0, "start": round(_u(rng, 0.0, 0.9), 3),
                          "span_w": int(cc._pick(rng, [350, 700, 1300, 2400, 3600])), "angle": 0.0,
                          "stems": "grwl_far_sb19"}
        else:
            f["kind"] = "machine"
            f["voice"] = {"id": "machine", "grammar": cc._pick(rng, ["stair", "ruler", "compass", "koch"]),
                          "hand": cc._pick(rng, list(hands or cc.HAND_POOL)), "length": round(_u(rng, 2.0, 5.0), 1)}
    kinds = [f["kind"] for f in plan["found"]]
    if len(kinds) != len(set(kinds)):                  # two rivers would overlay the same stem: keep one
        seen, keep = set(), []
        for f in plan["found"]:
            if f["kind"] not in seen:
                keep.append(f)
                seen.add(f["kind"])
        plan["found"] = keep
    fam = [f for f in FAMILIES if f in families]
    if len(fam) > 2:                         # focus: each sheet takes some of the families, never a museum
        keep = [f for f, q in zip(FAMILIES, (0.8, 0.75, 0.65, 0.55)) if f in fam and rng.random() < q]
        while len(keep) < 2:
            extra = [f for f in fam if f not in keep]
            keep.append(extra[int(rng.integers(len(extra)))])
        fam = [f for f in FAMILIES if f in keep]
    plan["families"] = fam
    c = np.array([cx, cy])
    # T2 traverse: the danced chain (replaces ccolour's belt/gmorph/passage/handover traverse); it runs
    # edge to edge by way of a point near (not at) the core's centre: through core AND blank
    plan["traverse"] = None
    if "danced" in fam:
        horiz = W >= H * 1.2 or rng.random() < 0.5
        ang = (0.0 if horiz else math.pi / 2) + _u(rng, -0.45, 0.45) + (math.pi if rng.random() < 0.5 else 0.0)
        via = c + np.array([_u(rng, -0.22, 0.22) * cw, _u(rng, -0.22, 0.22) * ch])
        d = np.array([math.cos(ang), math.sin(ang)])
        a, b = ray_exit(via, -d, W, H, 0.05), ray_exit(via, d, W, H, 0.05)
        hands3 = cc._pick(rng, [["matisse", "shikasta", "lichtenberg"], ["shikasta", "matisse", "lichtenberg"],
                                ["lichtenberg", "shikasta", "matisse"]], [0.6, 0.2, 0.2])
        plan["traverse"] = {"kind": "danced", "a": _r(a), "via": _r(via), "b": _r(b),
                            "hands": hands3, "zoom": round(_u(rng, 0.42, 0.62), 2),
                            "pull": round(_u(rng, 0.04, 0.07), 3), "ratio": 2.4, "tempo": "staccato",
                            "mass_w": round(_u(rng, 2.6, 4.2), 1), "nib_w": round(_u(rng, 0.8, 1.4), 2),
                            "amount": round(_u(rng, 0.6, 0.9), 2), "pen": 0.3}
    # T3 heavy intruder: the bold swell at the core's edge (replaces bars, Ls, stairs, knots)
    plan["intruder"] = None
    if "swell" in fam:
        ang = rng.uniform(0, 2 * math.pi)            # its centre at or just outside the core's rim: it cuts in
        at = [cx + math.cos(ang) * cw / 2 * _u(rng, 0.9, 1.2), cy + math.sin(ang) * ch / 2 * _u(rng, 0.9, 1.2)]
        sz = _u(rng, 0.42, 0.55) * min(W, H)
        bw, bh = sz * _u(rng, 1.0, 1.4), sz * _u(rng, 0.7, 0.95)
        x0 = float(np.clip(at[0] - bw / 2, 8.0, W - bw - 8.0))
        y0 = float(np.clip(at[1] - bh / 2, 8.0, H - bh - 8.0))
        size = round(float(np.clip(0.15 * sz, 10.0, 17.0)), 1)
        plan["intruder"] = {"kind": "swell", "box": [round(x0, 1), round(y0, 1), round(bw, 1), round(bh, 1)],
                            "hand": cc._pick(rng, list(SWELL_HANDS), [0.6, 0.25, 0.15]),
                            "length": round(_u(rng, 0.42, 0.72), 2),
                            "profile": cc._pick(rng, ["drop", "press", "turn", "lens"], [0.45, 0.2, 0.2, 0.15]),
                            "size": size, "tail": round(size * _u(rng, 2.0, 3.0), 1),
                            "duet": bool(rng.random() < duet), "pen": 0.6}
    # T7 figure flicker: limb signs spliced into made lines (decided now, placed after colour)
    plan["flicker"] = None
    if "flicker" in fam:
        trail, host = FLICKER_TRAILS[int(rng.integers(len(FLICKER_TRAILS)))]
        plan["flicker"] = {"trail": trail, "host": host, "n": int(cc._pick(rng, [2, 3], [0.5, 0.5])),
                           "size": [round(_u(rng, 14.0, 18.0), 1), round(_u(rng, 20.0, 28.0), 1)],
                           "nib_mm": round(_u(rng, 0.55, 0.85), 2), "on": cc._pick(rng, ["made", "made+traverse"],
                                                                                    [0.7, 0.3])}
    # the passer: a line that changes type where it is; edge → the core's centre → the opposite edge
    plan["passer"] = None
    if "passer" in fam:
        ang = rng.uniform(0, 2 * math.pi)
        d = np.array([math.cos(ang), math.sin(ang)])
        a, b = ray_exit(c, d, W, H, 0.06), ray_exit(c, -d, W, H, 0.06)
        made_h = [m["hand"] for m in plan["made"]]
        core_hand = max(sorted(set(made_h)), key=made_h.count) if made_h else "hokusai"
        # its zone is the container (T4): the frame inside the frame changes the line's grammar, where
        # the eye can see it (inside the core's tangle the change drowned, the first try)
        if not plan.get("container"):
            kw_, kh_ = cw * _u(rng, 0.45, 0.75), ch * _u(rng, 0.45, 0.8)
            a2 = rng.uniform(0, 2 * math.pi)
            kx = float(np.clip(cx + math.cos(a2) * cw * _u(rng, 0.25, 0.5), kw_ / 2 + 8, W - kw_ / 2 - 8))
            ky = float(np.clip(cy + math.sin(a2) * ch * _u(rng, 0.25, 0.5), kh_ / 2 + 8, H - kh_ / 2 - 8))
            plan["container"] = {"rect": [round(kx, 1), round(ky, 1), round(kw_, 1), round(kh_, 1)],
                                 "angle": round(_u(rng, -5, 5), 1), "pen": 0.3,
                                 "refuse": int(rng.integers(0, max(len(plan["made"]), 1))), "for": "passer"}
        k_ = plan["container"]["rect"]
        zc = np.array(k_[:2], float)
        a, b = ray_exit(zc, d, W, H, 0.06), ray_exit(zc, -d, W, H, 0.06)
        plan["passer"] = {"from": cc._pick(rng, list(PASSER_FROM), [0.45, 0.35, 0.2]), "core_hand": core_hand,
                          "zone": "container", "a": _r(a), "via": _r(zc), "b": _r(b),
                          "zoom": round(_u(rng, 0.5, 0.8), 2), "pull": round(_u(rng, 0.06, 0.09), 3), "ratio": 1.8,
                          "depth": round(_u(rng, 0.1, 0.3), 2), "pen": 0.3}
    # density stays in the middle: with three or four revived acts the counterweight steps out
    if sum(plan.get(k) is not None for k in ("traverse", "intruder", "flicker", "passer")) >= 3:
        plan["counter"] = None
    plan["pens"] = cc.pen_plan(rng, plan, pens=pens, mode=mode)
    pp = plan["pens"]
    pal = pp["palette"]
    if plan["passer"]:                       # its own pen; inside the container it takes the container's
        own = pp["own"]
        zone_ink = own.get("container", own.get("made", pal[0]))
        cand = [c for c in pal if c not in (zone_ink, own.get("intruder"))]
        plan["passer"]["ink"] = cand[-1] if cand else own.get("made", pal[0])
        plan["passer"]["core_ink"] = zone_ink if zone_ink != plan["passer"]["ink"] else "black"
    if plan["intruder"] and plan["intruder"]["duet"]:
        cand = [c for c in pal if c != pp["own"].get("intruder")]
        plan["intruder"]["duet_ink"] = cand[0] if (cand and len(pal) > 1) else "red"
    return plan


# ---------------------------------------------------------------------------
# 2. steering: a hand's own turns, pulled toward a goal (the traverse and the passer)
# ---------------------------------------------------------------------------

def turns(points, zoom: float, step: float = 0.5):
    """A line as its heading increments per `step` mm, after scaling by `zoom`."""
    p = resample(np.asarray(points, float) * zoom, step)
    if len(p) < 3:
        return np.zeros(0)
    d = np.diff(p, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    return np.diff(th)


def tokens(dth, step: float = 0.5, min_mm: float = 6.0):
    """Cut a turn sequence into features: boundaries where the smoothed |turn| is lowest (the line
    runs straight), at least `min_mm` apart. Returns [(i0, i1), …] covering the whole sequence."""
    if len(dth) < 4:
        return [(0, len(dth))]
    k = max(int(round(2.0 / step)), 1)
    a = np.convolve(np.abs(dth), np.ones(2 * k + 1) / (2 * k + 1), mode="same")
    thr = np.quantile(a, 0.3)
    gap = int(round(min_mm / step))
    cuts, last = [0], 0
    for i in range(gap, len(dth) - gap):
        if a[i] <= thr and i - last >= gap and a[i] <= a[max(i - 1, 0)] and a[i] <= a[min(i + 1, len(a) - 1)]:
            cuts.append(i)
            last = i
    cuts.append(len(dth))
    return list(zip(cuts[:-1], cuts[1:]))


def steer(sources: dict, pick, a, b, *, frame, via=None, pull: float = 0.05, ratio: float = 2.6,
          step: float = 0.5, wall: float = 9.0, max_mm: float = 4000.0):
    """Integrate a path from a toward b, one feature (token) at a time.

    sources: {name: (dth, [(i0, i1), …])}; pick(pos, k) -> name chooses whose next feature is drawn.
    Each feature keeps its own turns step for step; a weak pull `pull` rad/mm toward b (stronger
    when the line falls behind schedule) and a soft wall at the paper's edge bend it. Returns
    (points, source-name per point)."""
    W, H = frame
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    goals = ([np.asarray(via, float)] if via is not None else []) + [b]
    chord = max(float(sum(np.linalg.norm(q - p) for p, q in zip([a] + goals[:-1], goals))), 1.0)
    pos, h = a.copy(), math.atan2(goals[0][1] - a[1], goals[0][0] - a[0])
    cur = {n: 0 for n in sources}
    out, who = [pos.copy()], []
    walked, k = 0.0, 0
    while walked < max_mm:
        name = pick(pos, k)
        dth, toks = sources[name]
        j = cur[name] % len(toks)
        cur[name] += 1
        i0, i1 = toks[j]
        for i in range(i0, i1):
            to = goals[0] - pos
            dist = float(np.linalg.norm(to))
            if len(goals) > 1 and dist < 0.06 * chord:      # the waypoint is passed near, not hit
                goals.pop(0)
                to = goals[0] - pos
                dist = float(np.linalg.norm(to))
            if len(goals) == 1 and dist < 3.0:
                return np.array(out), who
            left = dist + sum(float(np.linalg.norm(q - p)) for p, q in zip(goals[:-1], goals[1:]))
            behind = max(walked / (ratio * chord) - (1 - left / chord), 0.0)
            h += dth[i] + pull * (1 + 6 * behind) * _wrap(math.atan2(to[1], to[0]) - h) * step
            ahead = pos + 4 * step * np.array([math.cos(h), math.sin(h)])
            if not (wall < ahead[0] < W - wall and wall < ahead[1] < H - wall):
                c = np.array([W / 2, H / 2]) - pos
                h += 0.3 * _wrap(math.atan2(c[1], c[0]) - h)
            pos = pos + step * np.array([math.cos(h), math.sin(h)])
            out.append(pos.copy())
            who.append(name)
            walked += step
        k += 1
    return np.array(out), who


# ---------------------------------------------------------------------------
# 3. the acts
# ---------------------------------------------------------------------------

def act_danced(ctx, plan):
    """T2: the danced chain, steered across the sheet; timing weights it; inked as a nib."""
    t = plan["traverse"]
    W, H = ctx.frame
    spec = {"id": "drift", "hands": t["hands"], "joins": "chain", "length": 12.0}
    src = cc._part(ctx, 300, spec, (0.0, 0.0, W, H)).voice((0.0, 0.0, W, H))
    dth = turns(src[0].points, t["zoom"])
    pts, _ = steer({"drift": (dth, tokens(dth))}, lambda pos, k: "drift", t["a"], t["b"], frame=(W, H), via=t.get("via"),
                   pull=t["pull"], ratio=t["ratio"])
    m = Mark(pts, {"r": np.zeros(len(pts)), "W": np.full(len(pts), t["nib_w"]),
                   "phi": np.full(len(pts), math.radians(35.0)), "M": np.full(len(pts), t["mass_w"])},
             {"voices": list(t["hands"])})
    tp = cc._part(ctx, 301, {"id": "hand", "hand": "matisse"}, ctx.box)
    tp.spec = {"voice": tp.spec["voice"], "modulators": [get("modulator", "timing").validate(
        {"id": "timing", "tempo": t["tempo"], "amount": t["amount"], "mass_width": t["mass_w"], "pen": 0.3,
         "jitter_gain": 0.6})]}
    q = tp.modulate([m], ctx.box)[0]
    return [Mark(q.points, q.channels, {"register": "traverse", "obj": ["traverse", 0], "pen": t["pen"],
                                        "of_role": "traverse", "draw": "nib"})]


def act_swell(ctx, plan):
    """T3: one bold swell gesture (sometimes a duet in two pens) at the core's edge."""
    t = plan["intruder"]
    box = tuple(t["box"])
    gap = round(t["size"] * 3.0, 1)
    pros = {"id": "prosody", "density": 0.4, "gap": gap, "span": round(t["size"] * 0.4, 1), "primary": 0.5,
            "W": 2.5, "M": 7.0}
    out = []
    voices = [(320, t["hand"], None)]
    if t["duet"]:
        voices.append((321, "shikasta" if t["hand"] != "shikasta" else "meander69", t.get("duet_ink")))
    placed = []
    for idx, hand, ink in voices:
        part = cc._part(ctx, idx, {"id": "hand", "hand": hand, "length": t["length"], "joins": "smooth"}, box)
        part.spec = {"voice": part.spec["voice"], "modulators": [get("modulator", "prosody").validate(pros)]}
        ms = part.run(box)
        if placed:                           # the chorus: the second voice stresses only where the first is quiet
            from .dev_chorus import _heard  # noqa: PLC0415
            from .prosody_arrangers import answer_mark  # noqa: PLC0415
            lead = [_heard(m) for m in placed[0]]
            ms = [answer_mark(m, lead, listen_by="space", radius=t["size"] * 1.6, answer=0.8, delay=0.05,
                              window=0.012)[0] for m in ms]
        placed.append(ms)
        for m in ms:
            out.append(Mark(m.points, m.channels, {"register": "intruder", "obj": ["intruder", len(placed) - 1],
                                                   "of_role": "intruder", "pen": t["pen"], "draw": "swell",
                                                   "voice_ink": ink, "prosody": m.meta.get("prosody", {}),
                                                   "swell": {"profile": t["profile"], "size": t["size"],
                                                             "tail": t["tail"], "pen": t["pen"], "k_head": 0.8,
                                                             "tail_w": 2.0}}))
    return out


def _core_depth(plan, pos, zone="core"):
    if zone == "container":
        cx, cy, cw, ch = plan["container"]["rect"]
        a = math.radians(-plan["container"]["angle"])
        dx, dy = pos[0] - cx, pos[1] - cy
        x, y = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
        return 1.0 - max(abs(x) / (cw / 2), abs(y) / (ch / 2))     # > 0 inside the rectangle
    cx, cy, cw, ch = plan["core"]
    d = ((pos[0] - cx) / (cw / 2)) ** 2 + ((pos[1] - cy) / (ch / 2)) ** 2
    return 1.0 - math.sqrt(d)                 # > 0 inside the core's ellipse, 1 at its centre


def act_passer(ctx, plan):
    """The line that changes type where it is: its own hand outside the core, the core's inside."""
    t = plan["passer"]
    W, H = ctx.frame
    big = (0.0, 0.0, W, H)
    if t["from"] == "free3966":
        from . import voices_passage as vp  # noqa: PLC0415
        own_pts, _ = vp.free_opening(ctx.use("hand", "river_belt"), (0.0, 0.0, 285.0, 93.5))
        own_pts = own_pts * (W / 285.0)
    elif t["from"] == "belt":
        own_pts = cc._part(ctx, 330, {"id": "belt", "hand": "river_belt", "length": 9.0, "gain": 1.0,
                                      "gain_end": 3.2}, big).voice(big)[0].points
    else:
        own_pts = cc._part(ctx, 330, {"id": "hand", "hand": "meander69", "length": 9.0, "joins": "smooth"},
                           big).voice(big)[0].points
    core_pts = cc._part(ctx, 331, {"id": "hand", "hand": t["core_hand"], "length": 9.0, "joins": "smooth"},
                        big).voice(big)[0].points
    d_own, d_core = turns(own_pts, t["zoom"]), turns(core_pts, t["zoom"])
    rng = ctx.rng("passer")
    depth = float(t["depth"])

    def pick(pos, k):
        x = float(np.clip(_core_depth(plan, pos, t.get("zone", "core")) / depth, 0.0, 1.0))
        p = x * x * (3 - 2 * x)
        return "core" if rng.random() < p else "own"
    pts, who = steer({"own": (d_own, tokens(d_own)), "core": (d_core, tokens(d_core))}, pick, t["a"], t["b"],
                     frame=(W, H), via=t.get("via"), pull=t["pull"], ratio=t["ratio"])
    src = np.array([1.0 if w == "core" else 0.0 for w in who[:1] + who], float)[:len(pts)]
    return [Mark(pts, {"src_core": src}, {"register": "passer", "obj": ["passer", 0], "of_role": "passer",
                                           "pen": t["pen"], "draw": "wire"})]


def colour_passer(plan, m, min_run: float):
    """Pen by place: the passer takes the core's pen over each stretch spoken in the core's hand
    (runs shorter than min_run are swallowed, so the colour never turns to confetti)."""
    t = plan["passer"]
    s = arclen(m.points)
    raw = np.where(np.asarray(m.channels["src_core"]) > 0.5, t["core_ink"], t["ink"]).astype(object)
    col = cc._settle(raw, s, t["ink"], min_run)
    out, cut = [], np.r_[0, np.flatnonzero(col[1:] != col[:-1]) + 1, len(col)]
    spans = []
    for a, b in zip(cut[:-1], cut[1:]):
        e = min(int(b) + 1, len(m.points))
        if e - int(a) < 2:
            continue
        out.append(Mark(m.points[int(a):e], {}, {**m.meta, "ink": str(col[a]), "pen": t["pen"], "part": 0}))
        if col[a] == t["core_ink"]:
            spans.append([float(s[int(a)]), float(s[e - 1])])
    return out, spans


def figures(ctx, plan):
    """The limb figures: revisit_glyph's excursions cut from the host trail, each starting and
    ending at its stop point (origin), with its rise-and-fall regime r."""
    f = plan["flicker"]
    spec = {"id": "revisit_glyph", "trail": f["trail"], "host": f["host"], "seconds": 60.0, "still": 0.2,
            "min_hold_s": 0.25, "max_glyphs": 20, "spread": 1.0}
    box = (0.0, 0.0, 200.0, 200.0)
    ms = cc._part(ctx, 340, spec, box).voice(box)
    out = []
    for m in ms:
        g = np.asarray(m["glyph"]).astype(int)
        r = np.asarray(m["r"])
        for k in sorted(set(g.tolist()) - {0}):
            idx = np.flatnonzero(g == k)
            i0, i1 = max(int(idx[0]) - 1, 0), min(int(idx[-1]) + 1, len(g) - 1)
            p = np.asarray(m.points[i0:i1 + 1], float)
            if len(p) < 6:
                continue
            p = p - p[0]
            ext = float(np.hypot(*np.ptp(p, axis=0)))
            if ext < 1e-6:
                continue
            # a figure, not a slash: it must open in both directions and turn
            q = p - p.mean(axis=0)
            ev = np.sqrt(np.maximum(np.linalg.eigvalsh(np.cov(q.T)), 0.0))
            d = np.diff(p, axis=0)
            th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
            turn = float(np.sum(np.abs(np.diff(th)))) / (2 * math.pi)
            score = float(ev[0] / max(ev[1], 1e-9)) * min(turn, 3.0)
            out.append((score, p / ext, r[i0:i1 + 1]))
    out.sort(key=lambda x: -x[0])
    return [(p, r) for sc, p, r in out[:6] if sc > 0.25]


def act_flicker(ctx, plan, marks):
    """Splice limb figures into lines (after colour): a stop, a small upright figure in the host's
    own pen that rises to nib and falls back, then the line goes on from the same point. A figure
    surfaces only where there is room for it to be seen: at the emptiest stretch of a line that
    reaches out of the core (in a tangle it would drown, which is what the first try did)."""
    from scipy.spatial import cKDTree  # noqa: PLC0415
    f = plan["flicker"]
    figs = figures(ctx, plan)
    if not figs:
        return marks, []
    rng = ctx.rng("flicker")
    roles = ("made", "traverse") if f["on"] == "made+traverse" else ("made",)
    W, H = ctx.frame
    allp, owner = [], []
    for i, m in enumerate(marks):
        q = resample(np.asarray(m.points, float), 1.5)
        allp.append(q)
        owner += [i] * len(q)
    tree = cKDTree(np.vstack(allp))
    owner = np.asarray(owner)
    size_hi = f["size"][1]
    spots = []                                       # (crowding, mark, index along it)
    for i, m in enumerate(marks):
        if m.meta.get("register") not in roles or m.meta.get("draw") == "swell" or len(m.points) < 8:
            continue
        s = arclen(m.points)
        if s[-1] < 25.0:
            continue
        for x in np.arange(0.15, 0.86, 0.05) * s[-1]:
            j = int(np.clip(np.searchsorted(s, x), 1, len(m.points) - 2))
            c = np.asarray(m.points[j], float)
            if not (size_hi + 3 < c[0] < W - size_hi - 3 and size_hi + 3 < c[1] < H - size_hi - 3):
                continue
            near = tree.query_ball_point(c + [0.0, -0.5 * size_hi], 0.9 * size_hi)
            crowd = int(np.sum(owner[near] != i)) if near else 0
            spots.append((crowd + rng.random() * 0.5, i, j))
    if not spots:
        return marks, []
    spots.sort()
    chosen, used = [], []
    for crowd, i, j in spots:
        c = np.asarray(marks[i].points[j], float)
        if any(np.linalg.norm(c - u) < 3 * size_hi for u in used) or any(i == ci for ci, _ in chosen):
            continue
        chosen.append((i, j))
        used.append(c)
        if len(chosen) >= f["n"]:
            break
    order = rng.permutation(len(figs))
    at_of = dict(chosen)
    events, out = [], []
    for i, m in enumerate(marks):
        if i not in at_of:
            out.append(m)
            continue
        k = [ci for ci, _ in chosen].index(i)
        p, r = figs[int(order[k % len(figs)])]
        s = arclen(m.points)
        at = at_of[i]
        stop = np.asarray(m.points[at], float)
        size = _u(rng, *f["size"])
        q = p * size + stop
        head = Mark(m.points[:at + 1], {kk: np.asarray(v)[:at + 1] for kk, v in m.channels.items()}, {**m.meta})
        tail = Mark(m.points[at:], {kk: np.asarray(v)[at:] for kk, v in m.channels.items()}, {**m.meta})
        rr = np.clip(np.asarray(r, float), 0.0, 1.4)
        fig = Mark(q, {"r": rr, "W": np.full(len(q), f["nib_mm"]), "M": np.full(len(q), f["nib_mm"] * 1.6),
                       "phi": np.full(len(q), math.radians(40.0))},
                   {"register": "flicker", "obj": ["flicker", k], "of_role": "flicker", "host": list(m.meta["obj"]),
                    "ink": m.meta.get("ink", "black"), "pen": 0.3, "draw": "nib", "nib_style": "c+e", "part": 0})
        out += [head, fig, tail]
        events.append({"host": list(m.meta["obj"]), "at": [round(float(stop[0]), 1), round(float(stop[1]), 1)],
                       "s": round(float(s[at]), 1), "size": round(size, 1), "ink": m.meta.get("ink", "black"),
                       "fig": k})
    return out, events


# ---------------------------------------------------------------------------
# 4. the score
# ---------------------------------------------------------------------------

def build_score(plan, order, events, flick, passer_spans, swell_info) -> dict:
    sc = Score()
    pp = plan["pens"]
    W, H = plan["frame"]
    lid: dict = {}
    region = sc.layer("region", "none", label="the core (undrawn): where the made lines gather; the passer "
                      "speaks its hand inside it", params={"core": plan["core"], "blank": plan["blank"]})
    for k, f in enumerate(plan["found"]):
        lid[("found", f["kind"])] = sc.layer("found", f["voice"]["id"], part=100 + k, pen=pp["own"].get("found"),
                                             params=f, label=f"found matter: {f['kind']}")
    for i, m in enumerate(plan["made"]):
        lid[("made", i)] = sc.layer("line", "hand", part=200 + i, pen=pp["line_pens"][i % len(pp["line_pens"])],
                                    params=m, label=f"made line {i}: {m['hand']}")
    if plan["play"]["cover_after"] >= 0:
        lid[("found", "cover")] = sc.layer("mask", "found_play:R5 cover", pen=pp["own"].get("found"),
                                           params={"after_line": plan["play"]["cover_after"],
                                                   "wh": plan["play"]["cover_wh"]},
                                           label="a torn cover cut out of the core after a made line")
    if plan.get("container"):
        lid[("container", 0)] = sc.layer("container", "rect", pen=pp["own"].get("container"),
                                         params=plan["container"], label="a frame inside the frame (T4)")
    if plan.get("counter"):
        lid[("counter", 0)] = sc.layer("counter", plan["counter"]["kind"], part=310, pen=pp["own"].get("counter"),
                                       params=plan["counter"], label="a smaller density away from the core (T7)")
    if plan.get("traverse"):
        t = plan["traverse"]
        lid[("traverse", 0)] = sc.layer("traverse", "drift(chain)+timing(staccato)+nib", part=300,
                                        pen=pp["own"].get("traverse"), params=t,
                                        label="the danced chain, steered edge to edge: belongs to neither "
                                              "core nor blank (T2)")
        sc.relate("cross", lid[("traverse", 0)], region, at=t["a"], note="crosses the core and the blank alike")
    if plan.get("intruder"):
        t = plan["intruder"]
        lid[("intruder", 0)] = sc.layer("intruder", f"hand({t['hand']})+prosody+swell({t['profile']})", part=320,
                                        pen=pp["own"].get("intruder"), params=t,
                                        label="bold swell at the core's edge: round masses, the foreign pen (T3)")
        bx = t["box"]
        sc.relate("intrude", lid[("intruder", 0)], region, at=[bx[0] + bx[2] / 2, bx[1] + bx[3] / 2],
                  note="heavy, round and foreign where everything else is hairline")
        if t["duet"]:
            lid[("intruder", 1)] = sc.layer("intruder", "hand+prosody+swell (answering)", part=321,
                                            pen=t.get("duet_ink"), params={"answers": "space"},
                                            label="the chorus: a second swell voice in a second pen")
            sc.relate("answer", lid[("intruder", 0)], lid[("intruder", 1)],
                      note=f"stresses only where the first voice is quiet nearby ({swell_info} answers)")
    if plan.get("passer"):
        t = plan["passer"]
        lid[("passer", 0)] = sc.layer("passer", f"steer(tokens: {t['from']} | {t['core_hand']})", part=330,
                                      pen=t["ink"], params=t,
                                      label=f"a line that changes type where it is: {t['from']} outside, "
                                            f"{t['core_hand']} inside the container")
        core_line = next((lid[("made", i)] for i, m in enumerate(plan["made"]) if m["hand"] == t["core_hand"]),
                         region)
        if ("container", 0) in lid:
            sc.relate("contain", lid[("container", 0)], lid[("passer", 0)],
                      note="the zone where the passer changes its grammar and its pen")
        for sp in passer_spans:
            sc.relate("translate", core_line, lid[("passer", 0)], s=sp,
                      note=f"inside the container speaks the core's hand ({t['core_hand']}) in the container's pen "
                           f"({t['core_ink']})")
    for fe in flick:
        host = lid.get(tuple(fe["host"]) if fe["host"][0] != "made" else ("made", int(fe["host"][1])))
        fl = sc.layer("flicker", f"revisit_glyph({plan['flicker']['trail']}, {plan['flicker']['host']})", part=340,
                      pen=fe["ink"], params={"size": fe["size"]}, label="a limb sign surfaces and falls back")
        if host:
            sc.relate("surface", fl, host, at=fe["at"], s=[fe["s"], fe["s"]],
                      note="the host stops, writes what the other limbs did, and goes on")
    for e in events:
        o = tuple(e["obj"])
        dst = lid.get(o) if o[0] != "made" else lid.get(("made", int(o[1])))
        if dst is None:
            continue
        src = dst
        why = e.get("why", "")
        if "line " in why:                   # carries / answers / is taken back by line j
            try:
                j = int(why.split("line ")[1].split("'")[0].split()[0])
                src = lid.get(("made", j), dst)
            except (ValueError, IndexError):
                pass
        elif "river" in why:
            src = lid.get(("found", "river"), dst)
        elif "container" in why:
            src = lid.get(("container", 0), dst)
        if src == dst:                       # the lender is found matter (a contour it left, a carried stem)
            src = next((v for k, v in lid.items() if k[0] == "found" and k[1] != "cover" and v != dst), region)
        kind = {"carry": "ride", "ride": "ride", "answer": "echo", "reverse": "ride", "contact": "contact",
                "spill": "spill"}.get(e["kind"], e["kind"])
        sc.relate(kind, src, dst, s=[e["at_mm"], e["at_mm"] + e["len_mm"]],
                  note=f"ccolour {e['kind']}: {why} (pen {e['pen']}, lies {e['lie']})")
    sc.decide(frame=[W, H], density=plan["density"], core=plan["core"], blank=plan["blank"],
              families=plan["families"], order=order, pens={k: pp[k] for k in ("n", "palette", "mode", "own")},
              kappa_chart="retired as found matter (round 15)")
    return sc.to_json()


# ---------------------------------------------------------------------------
# 5. the arranger
# ---------------------------------------------------------------------------

@arranger("arch", params=[
    P("families", "str", "danced,swell,flicker,passer", "which revived families enter (comma list of "
      "danced | swell | flicker | passer)"),
    P("density", "float", -1.0, "the density dial 0 … 1 (-1 = the middle: 0.2 / 0.3 / 0.4)", min=-1.0, max=1.0),
    P("pens", "int", 0, "how many pens 1–5 (0 = the composer decides)", min=0, max=5),
    P("mode", "choice", "auto", "who owns which pen (ccolour's modes)", choices=("auto",) + cc.MODES),
    P("duet", "float", 0.25, "chance the swell intruder is a duet (the chorus: two pens, answering)",
      min=0.0, max=1.0),
    P("acts", "str", "container,counter", "which of ccolour's other acts may enter (comma list)"),
], doc="round 15 C: ccolour's composer with past keeps in new roles — the danced chain as the traverse, "
        "the bold swell as the heavy intruder, limb signs as figure flicker, a passer that changes type where "
        "it is; writes a score")
def arch(ctx, parts, *, families, density, pens, mode, duet, acts):
    W, H = ctx.frame
    fam = [f.strip() for f in families.split(",") if f.strip()]
    bad = sorted(set(fam) - set(FAMILIES))
    if bad:
        raise ValueError(f"arch: unknown famil(ies) {bad}; choose from {FAMILIES}")
    allowed = {a.strip() for a in acts.split(",") if a.strip()}
    plan = plan_arch(ctx.rng("decide"), W, H, density=density, families=fam, pens=pens, mode=mode, duet=duet,
                     hands=[p.spec["voice"].get("hand") for p in parts if p.spec["voice"].get("hand")])
    for k in ("container", "counter"):
        if k not in allowed and not (k == "container" and plan["passer"]):
            plan[k] = None
    marks, play = cc.act_core(ctx, plan, parts)
    order = ["found", "made"]
    if plan["container"]:
        marks.append(Mark(cc.container_polygon(plan), {}, {"register": "container", "obj": ["container", 0],
                                                           "of_role": "container", "pen": plan["container"]["pen"]}))
        order.insert(1, "container")
    if plan["counter"]:
        marks += cc.act_counter(ctx, plan)
        order.append("counter")
    late = []
    if plan["traverse"]:
        late.append(("traverse", act_danced(ctx, plan)))
    if plan["passer"]:
        late.append(("passer", act_passer(ctx, plan)))
    rng = ctx.rng("order")
    if len(late) == 2 and rng.random() < 0.5:
        late.reverse()
    for name, ms in late:
        if name == "traverse":
            marks += ms
        order.append(name)
    out, events = cc.colour(ctx.rng("colour"), plan, marks, play)
    spans = []
    for name, ms in late:
        if name == "passer":
            pm, spans = colour_passer(plan, ms[0], plan["pens"]["min_run"])
            out += pm
    out = [m.evolve(meta={"draw": m.meta.get("draw", "wire")}) for m in out]
    flick = []
    if plan["flicker"]:
        out, flick = act_flicker(ctx, plan, out)
        order.append("flicker")
    swell_n = 0
    if plan["intruder"]:
        sw = act_swell(ctx, plan)
        own = plan["pens"]["own"].get("intruder", plan["pens"]["palette"][0])
        for m in sw:
            out.append(m.evolve(meta={"ink": m.meta.get("voice_ink") or own, "part": 0}))
        swell_n = sum(1 for m in sw if m.meta["obj"][1] == 1 and m.meta.get("prosody"))
        order.append("intruder")
    lo, hi = np.array([1.0, 1.0]), np.array([W - 1.0, H - 1.0])
    out = [m if (m.points.min(axis=0) >= lo).all() and (m.points.max(axis=0) <= hi).all()
           else m.evolve(points=np.clip(m.points, lo, hi)) for m in out]
    score = build_score(plan, order, events, flick, spans, swell_n)
    ctx.note("score", score)
    log = {"plan": plan, "order": order, "events": events, "flicker": flick, "passer_spans": spans,
           "pens_used": sorted({m.meta["ink"] for m in out}),
           "catches": len(play.get("infections", [])), "answers": len(play.get("answers", []))}
    if out:
        out[0] = out[0].evolve(meta={"arch": log})
    return out


def recipe(seed: int, *, frame=None, **arr) -> dict:
    """An arch recipe: ccolour's frames and made-hand pool; the frame is chosen per seed unless given."""
    r = cc.recipe(seed, frame=frame)
    a = {"id": "arch"}
    a.update(arr)
    r["arranger"] = a
    r["label"] = "arch"
    r["renderer"] = {"id": "arch_ink", "pen": 0.4}
    return copy.deepcopy(r)


def render(sheet, **kw):
    """Preview: pens multiply on paper (ccolour's)."""
    return cc.render_pens(sheet, **kw)
