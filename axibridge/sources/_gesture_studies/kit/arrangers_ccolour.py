# FROZEN from research commit f59eac4: tools/gesture/gesture/kit/arrangers_ccolour.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Round 14 b4 `ccolour`: colour as structure — a composer whose pens carry what each line is doing.

Ian on Study A's diagnostic map (round 13): "looks pretty nice with color". This thread turns that
map from a legend into a compositional layer. The composer decides a whole sheet per seed (core,
blank, density dial, found matter, made lines, container, traverse, counterweight, heavy intruder)
and then a PEN PLAN for it: how many pens (1–5), which registers own which pen, which events let a
colour cross over, and whether a colour lies (outlasts the carrying that earned it).

From the lead's composition note (results/oehlen-composition-2026-10-18.md):

    T6  registers contaminate each other, "local and brief, not a style": a register owns a pen and
        LENDS it briefly. A made line that carries the river, the chart or another line's hand takes
        the lender's pen for that stretch; where it rode a found contour, the contour may take the
        line's pen back (the reverse borrow); a crossing can infect a traverse or a counterweight.
    T4  container and spill: a drawn frame inside the frame stains what passes inside it with its own
        pen; leaving, a line keeps the stain for a while (the spill); one line refuses the container.
    T3  the heavy intruder: heavy straight / stepped / knotted marks at the core's edge, foreign in
        regime, weight and pen together.

Against the legend failure: the palette, the number of pens, which registers get colour and which
event kinds are on are all re-decided per sheet; events are a budget (a few per sheet, at most a
few per line), every borrowed run is at least `min_run` mm (a pen change is an event, never
confetti), and a colour may lie (persist `lie_mm`, sometimes to the line's end). `colouring:
"legend"` is the dud control: every role always in its fixed pen, as the round-13 map.

The acts reuse the techniques that work and never copy their code:
    core     `found_play` (Study A: rules over found ground, catches, answers) with per-sheet
             found matter (kappa chart / Amazon stem at a per-sheet zoom / a machine line), hands,
             boxes, density and weights
    traverse one long line across the sheet: `belt` (gain ramp: the line morphs), `gmorph`
             (erratic dials), `passage` (many real hands), accrue's free hand (seed 3966, scaled),
             `morph_handover`
    counter  a small dense counterweight: `mutual` soup, accrue's knots, river oxbows, a dense hand
    container, intruder: drawn here (geometry only, no hands)

Recipe parts are the made-hand POOL (`hand` voices); the composer picks from it. Internal parts
take seeds sheet seed + 100 + k (found), + 200 + k (made), + 300 (traverse), + 310 (counter), so
the recipe alone reproduces the sheet. Every decision is logged in `marks[0].meta["ccolour"]`.
Ink with `oehlen_found_ink` (meta `ink`, `pen`); preview with `render_pens` (pens multiply on paper).
"""
from __future__ import annotations

import copy
import math
from dataclasses import replace

import numpy as np

from .arrangers_oehlen_found import FLEXOKI, arclen, clip_rect, rect_polygon, resample, rotate
from .core import PAPER, Mark, P, Part, _module_spec, arranger, get

# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------

# Hands Ian praised in made-line use (rules piece, four-hands sheet, Study A) plus passage's hands.
HAND_POOL = ["dance_thrusting", "river_bend", "trail_miner", "dancer_madeline", "mime_mantis", "fly_fru",
             "meander69", "hokusai", "dance_staccato", "mime_roadrunner", "river_belt", "trail_slime"]
# Pens: Flexoki 600 (dark) and 400 (light) accents; hexes from the kit's FLEXOKI (kepano/flexoki).
DARK = ["black", "blue", "red", "green", "purple", "magenta", "cyan", "orange"]
LIGHT = ["blue-400", "red-400", "green-400", "purple-400", "magenta-400", "cyan-400", "orange-400", "yellow-400"]
HUE = {c: c.split("-")[0] for c in DARK + LIGHT + ["yellow"]}
FRAMES = [  # (W, H, why) — the frame is chosen on purpose, per sheet (AxiDraw ≤ 300 × 218)
    (300.0, 200.0, "landscape: a core and a reserved blank side by side"),
    (300.0, 125.0, "strip: the traverse leads, the scale ladder laid out along it"),
    (205.0, 205.0, "square: an all-over field, or one core against a counterweight"),
    (160.0, 215.0, "portrait: strata stacked, the core high and the blank below"),
    (250.0, 175.0, "small landscape: the same vocabulary, denser per area"),
]
MODES = ("registers", "lines", "mono", "inverted", "pair")
EVENTS = ("carry", "ride", "answer", "reverse", "contact", "spill")
REGISTERS = ("found", "made", "traverse", "counter", "container", "intruder")
LEGEND = {0: "black", 1: "orange", 3: "black", 5: "green", 6: "cyan", 7: "blue", 8: "red", 9: "purple",
          10: "magenta"}


def _u(rng, a, b):
    return float(rng.uniform(a, b))


def _pick(rng, items, p=None):
    items = list(items)
    if p is not None:
        p = np.asarray(p, float) / np.sum(p)
    return items[int(rng.choice(len(items), p=p))]


# ---------------------------------------------------------------------------
# 1. the composition: every decision, per sheet
# ---------------------------------------------------------------------------

def decide(rng, W: float, H: float, *, density: float = -1.0, pens: int = 0, mode: str = "auto",
           hands=None) -> dict:
    """A whole composition as JSON-able decisions (nothing drawn yet)."""
    hands = list(hands or HAND_POOL)
    plan: dict = {"frame": [W, H]}
    # density dial, extremes allowed (T1)
    if density < 0:
        density = float(rng.choice([0.05, 0.25, 0.45, 0.65, 0.85, 1.0], p=[0.14, 0.18, 0.2, 0.2, 0.16, 0.12]))
    lines = int(np.clip(round(1 + density * 10 + rng.normal(0, 0.8)), 1, 12))
    plan["density"] = {"dial": round(density, 2), "lines": lines}
    # core, off-centre; the blank is the far side
    sx, sy = rng.choice([-1, 1]), rng.choice([-1, 1])
    cx = W * (0.5 + sx * _u(rng, 0.04, 0.3))
    cy = H * (0.5 + sy * _u(rng, 0.0, 0.28))
    share = _u(rng, 0.3, 0.5) + 0.35 * density
    cw, ch = min(W * share * _u(rng, 0.8, 1.1), W * 0.92), min(H * share * _u(rng, 0.8, 1.15), H * 0.92)
    plan["core"] = [round(cx, 1), round(cy, 1), round(cw, 1), round(ch, 1)]
    plan["blank"] = [round(W - cx, 1), round(H - cy, 1)]          # the far point the composer leaves open
    # found matter (0–2 + sometimes a machine line); at least one so the made lines have ground
    kinds = []
    if rng.random() < 0.62:
        kinds.append("chart")
    if rng.random() < 0.5:
        kinds.append("river")
    if rng.random() < 0.28:
        kinds.append("machine")
    if not kinds:
        kinds.append(_pick(rng, ["chart", "river", "machine"], [0.45, 0.35, 0.2]))
    found = []
    for k in kinds:
        a = rng.uniform(0, 2 * math.pi)
        off = _u(rng, 0.15, 0.55)
        fx = (cx + math.cos(a) * off * cw / 2) / W
        fy = (cy + math.sin(a) * off * ch / 2) / H
        if k == "chart":
            fw, fh = _u(rng, 0.3, 0.75), _u(rng, 0.2, 0.55)
            ang = _pick(rng, [_u(rng, -6, 6), _u(rng, -25, 25), 90 + _u(rng, -5, 5)], [0.6, 0.3, 0.1])
            spec = {"id": "diagram", "chart": "kappa", "rows": int(rng.integers(2, 7)), "label_h": 2.2,
                    "hands": [_pick(rng, hands)], "length": round(_u(rng, 3.0, 8.0), 1)}
        elif k == "river":
            fw, fh = _u(rng, 0.45, 1.05), _u(rng, 0.1, 0.32)
            ang = _pick(rng, [_u(rng, -12, 12), _u(rng, -50, 50), 90 + _u(rng, -10, 10)], [0.5, 0.35, 0.15])
            # the stem at a per-sheet zoom (never the one fixed far view): span 300–3000 channel widths
            spec = {"id": "oehlen_found_river", "tile": "SB19", "rank": 0, "start": round(_u(rng, 0.0, 0.9), 3),
                    "span_w": int(_pick(rng, [350, 700, 1300, 2400, 3600])), "angle": 0.0, "stems": "grwl_far_sb19"}
        else:
            fw, fh = _u(rng, 0.25, 0.7), _u(rng, 0.12, 0.4)
            ang = _u(rng, -20, 20)
            spec = {"id": "machine", "grammar": _pick(rng, ["stair", "ruler", "compass", "koch"]),
                    "hand": _pick(rng, hands), "length": round(_u(rng, 2.0, 5.0), 1)}
        fw, fh = min(fw, 0.94), min(fh, 0.94)
        found.append({"kind": k, "voice": spec,
                      "box": [round(float(np.clip(fx, fw / 2 + 0.03, 1 - fw / 2 - 0.03)), 3),
                              round(float(np.clip(fy, fh / 2 + 0.03, 1 - fh / 2 - 0.03)), 3),
                              round(fw, 3), round(fh, 3), round(float(ang), 1)]})
    plan["found"] = found
    # made lines: hands and boxes about the core (some tight knots, some long reaches into the blank)
    made = []
    for i in range(lines):
        r = rng.random()
        if r < 0.3:
            bw, bh = _u(rng, 0.1, 0.25), _u(rng, 0.1, 0.25)          # a tight knot of a line
        elif r < 0.8:
            bw, bh = _u(rng, 0.25, 0.6), _u(rng, 0.25, 0.6)
        else:
            bw, bh = _u(rng, 0.6, 0.95), _u(rng, 0.4, 0.9)            # a long reach (trails off)
        mx = (cx + rng.normal(0, 0.22) * cw) / W
        my = (cy + rng.normal(0, 0.22) * ch) / H
        if rng.random() < 0.15:                                       # a line elsewhere, in the blank
            mx, my = _u(rng, 0.15, 0.85), _u(rng, 0.15, 0.85)
        made.append({"hand": _pick(rng, hands), "length": round(_u(rng, 1.6, 4.5), 1),
                     "box": [round(float(np.clip(mx, bw / 2, 1 - bw / 2)), 3),
                             round(float(np.clip(my, bh / 2, 1 - bh / 2)), 3), round(bw, 3), round(bh, 3)]})
    plan["made"] = made
    heavy = _pick(rng, [0.7, 1.0, 1.4], [0.3, 0.45, 0.25])
    plan["play"] = {"answers": int(rng.integers(1, 4)), "answer_p": round(_u(rng, 0.3, 0.9), 2),
                    "catches": int(rng.integers(2, 6)), "ride": round(_u(rng, 12, 30), 1),
                    "cover_after": int(_pick(rng, [-1, 1, 2, max(lines - 1, 0)], [0.35, 0.25, 0.2, 0.2])),
                    "cover_wh": [round(_u(rng, 16, 40), 1), round(_u(rng, 40, 90), 1)],
                    "bold_pen": heavy, "hair_pen": round(_pick(rng, [0.2, 0.25, 0.3]), 2),
                    "found_pen": round(_pick(rng, [0.2, 0.25, 0.35]), 2)}
    # container (T4): overlaps the core, never wholly contains it
    plan["container"] = None
    if rng.random() < 0.5:
        a = rng.uniform(0, 2 * math.pi)
        kx, ky = cx + math.cos(a) * cw * _u(rng, 0.1, 0.35), cy + math.sin(a) * ch * _u(rng, 0.1, 0.35)
        kw, kh = cw * _u(rng, 0.35, 0.75), ch * _u(rng, 0.35, 0.8)
        kx = float(np.clip(kx, kw / 2 + 8, W - kw / 2 - 8))
        ky = float(np.clip(ky, kh / 2 + 8, H - kh / 2 - 8))
        plan["container"] = {"rect": [round(kx, 1), round(ky, 1), round(kw, 1), round(kh, 1)],
                             "angle": round(_u(rng, -5, 5), 1), "pen": 0.3,
                             "refuse": int(rng.integers(0, max(lines, 1)))}
    # traverse (T2): one long line through core and blank alike
    plan["traverse"] = None
    if rng.random() < 0.72:
        kind = _pick(rng, ["belt", "gmorph", "passage", "free3966", "handover"], [0.25, 0.25, 0.2, 0.15, 0.15])
        if W >= H * 1.3 or rng.random() < 0.5:
            a = [_u(rng, 0.0, 0.12) * W, _u(rng, 0.1, 0.9) * H]
            b = [W - _u(rng, 0.0, 0.12) * W, _u(rng, 0.1, 0.9) * H]
        else:
            a = [_u(rng, 0.1, 0.9) * W, _u(rng, 0.0, 0.1) * H]
            b = [_u(rng, 0.1, 0.9) * W, H - _u(rng, 0.0, 0.1) * H]
        if rng.random() < 0.5:
            a, b = b, a
        band = _u(rng, 0.08, 0.3) * min(W, H)
        plan["traverse"] = {"kind": kind, "a": [round(v, 1) for v in a], "b": [round(v, 1) for v in b],
                            "band": round(band, 1), "pen": round(_pick(rng, [0.25, 0.6, 1.0], [0.4, 0.3, 0.3]), 2),
                            "hand": _pick(rng, ["river_belt", "river_bend", "meander69", "river_meander", "hokusai"])}
    # counterweight (T7): a second, smaller density away from the core
    plan["counter"] = None
    if rng.random() < 0.5:
        kind = _pick(rng, ["mutual", "accrue", "loops", "knot"], [0.3, 0.3, 0.15, 0.25])
        s = _u(rng, 0.18, 0.34)
        bw, bh = W * s * _u(rng, 0.9, 1.4), H * s * _u(rng, 0.9, 1.4)
        qx = float(np.clip(W - cx + rng.normal(0, 0.08) * W, bw / 2 + 6, W - bw / 2 - 6))
        qy = float(np.clip(H - cy + rng.normal(0, 0.08) * H, bh / 2 + 6, H - bh / 2 - 6))
        plan["counter"] = {"kind": kind, "box": [round(qx - bw / 2, 1), round(qy - bh / 2, 1), round(bw, 1),
                                                 round(bh, 1)], "hand": _pick(rng, hands)}
    # heavy intruder (T3): at the core's edge, cutting across it
    plan["intruder"] = None
    if rng.random() < 0.6:
        marks = []
        for _ in range(int(_pick(rng, [1, 2, 3], [0.5, 0.35, 0.15]))):
            a = rng.uniform(0, 2 * math.pi)
            p = [cx + math.cos(a) * cw / 2 * _u(rng, 0.75, 1.1), cy + math.sin(a) * ch / 2 * _u(rng, 0.75, 1.1)]
            toward = math.degrees(math.atan2(cy - p[1], cx - p[0]))
            marks.append({"shape": _pick(rng, ["bar", "L", "stair", "knot"], [0.4, 0.2, 0.2, 0.2]),
                          "at": [round(p[0], 1), round(p[1], 1)],
                          "angle": round(toward + _u(rng, -50, 50), 1),
                          "length": round(_u(rng, 0.12, 0.3) * min(W, H) + 10, 1)})
        plan["intruder"] = {"marks": marks, "pen": round(_pick(rng, [1.2, 1.6, 2.0]), 2)}
    plan["pens"] = pen_plan(rng, plan, pens=pens, mode=mode)
    return plan


def pen_plan(rng, plan: dict, *, pens: int = 0, mode: str = "auto") -> dict:
    """The colour layer as decisions: pens, who owns them, which crossings are allowed."""
    n = int(pens) if pens else int(rng.choice([1, 2, 3, 4, 5], p=[0.04, 0.26, 0.31, 0.25, 0.14]))
    first = _pick(rng, DARK, [0.42, 0.13, 0.1, 0.08, 0.1, 0.06, 0.06, 0.05])
    pal = [first]
    pool = [c for c in DARK + LIGHT if HUE[c] != HUE[first]]
    while len(pal) < n and pool:
        c = _pick(rng, pool)
        pal.append(c)
        pool = [q for q in pool if HUE[q] != HUE[c]]
    present = ["found", "made"] + [r for r in ("traverse", "counter", "container", "intruder") if plan.get(r)]
    if mode == "auto":
        mode = "mono" if n == 1 else _pick(rng, MODES, [0.3, 0.24, 0.13, 0.13, 0.2])
    own: dict = {}
    lines = plan["density"]["lines"]
    line_pens = [pal[0]] * lines
    if mode == "mono" or n == 1:
        own = {r: pal[0] for r in present}
        if n > 1 and "intruder" in present:
            own["intruder"] = pal[-1]                     # the only foreign pen on the sheet (T3)
        if n > 2 and "container" in present:
            own["container"] = pal[1]
    elif mode == "registers":
        order = list(present)
        rng.shuffle(order)
        order.remove("made")
        own["made"] = pal[0]
        for i, r in enumerate(order):
            own[r] = pal[(i + 1) % n] if n > 1 else pal[0]
    elif mode == "lines":
        k = int(min(n, rng.integers(2, 4))) if n > 1 else 1
        line_pens = [pal[i % k] for i in range(lines)]
        rng.shuffle(line_pens)
        own = {r: pal[min(k, n - 1)] if r != "made" else pal[0] for r in present}
        own["intruder"] = pal[0]
    elif mode == "inverted":
        own = {r: pal[1 % n] for r in present}
        own["found"] = pal[0]
        own["intruder"] = pal[0]
    else:  # pair: two camps that swap pens through their events
        camp = {r: int(rng.integers(2)) for r in present}
        camp["found"], camp["made"] = 0, 1
        own = {r: pal[camp[r] % n] for r in present}
        if n > 2 and "intruder" in present:
            own["intruder"] = pal[2]
    if mode != "lines":
        line_pens = [own["made"]] * lines
    if n > 1 and "container" in present and own["container"] in line_pens:
        own["container"] = next((c for c in pal[::-1] if c not in line_pens), pal[-1])   # its stain must show
    # what each register LENDS when another line borrows its behaviour; by default its own pen, but
    # in mono the found matter keeps a latent pen that shows only when it is carried away (T6)
    lend: dict = {}
    if mode == "mono" and n > 1:
        acc = pal[1:]
        for i, f in enumerate(plan["found"]):
            lend["found:" + f["kind"]] = acc[i % len(acc)]
        if rng.random() < 0.5:
            lend["line:" + str(int(rng.integers(lines)))] = acc[-1]
    on = [e for e, p in zip(EVENTS, (0.75, 0.4, 0.5, 0.35, 0.45, 0.85)) if rng.random() < p]
    if "spill" in on and not plan.get("container"):
        on.remove("spill")
    if n > 1 and not on:
        on = ["carry"]
    weights = {"found": plan["play"]["found_pen"], "traverse": (plan.get("traverse") or {}).get("pen", 0.4),
               "counter": 0.3, "container": 0.3, "intruder": (plan.get("intruder") or {}).get("pen", 1.6)}
    return {"n": n, "palette": pal, "mode": mode, "own": own, "line_pens": line_pens, "lend": lend, "events": on,
            "budget": int(rng.integers(2, 4) + round(lines * _u(rng, 0.1, 0.4))),
            "per_line": int(_pick(rng, [1, 2, 3], [0.35, 0.45, 0.2])),
            "min_run": round(_u(rng, 10.0, 24.0), 1),
            "p_lie": float(_pick(rng, [0.0, 0.35, 0.75], [0.3, 0.4, 0.3])), "lie_mm": round(_u(rng, 15, 90), 1),
            "p_end": float(_pick(rng, [0.0, 0.2], [0.7, 0.3])), "weights": weights}


# ---------------------------------------------------------------------------
# 2. the acts
# ---------------------------------------------------------------------------

def _part(ctx, index: int, voice_spec: dict, box) -> Part:
    spec = {"voice": _module_spec("voice", copy.deepcopy(voice_spec), f"ccolour part {index}"), "modulators": []}
    return Part(index, spec, {"id": "wire", "pen": 0.4}, ctx.frame, ctx.sheet_seed, ctx.run, box)


def _inner(ctx):
    x0, y0, w, h = ctx.box
    return rect_polygon(x0 + w / 2, y0 + h / 2, w, h, 0.0)


def act_core(ctx, plan, pool):
    """found_play with this sheet's found matter, hands, boxes and dials."""
    W, H = ctx.frame
    fparts = [_part(ctx, 100 + k, f["voice"], ctx.box) for k, f in enumerate(plan["found"])]
    mparts = []
    for i, m in enumerate(plan["made"]):
        base = next((p.spec["voice"] for p in pool if p.spec["voice"].get("hand") == m["hand"]), None)
        v = dict(base) if base else {"id": "hand", "hand": m["hand"], "joins": "smooth"}
        v["length"] = m["length"]
        mparts.append(_part(ctx, 200 + i, v, ctx.box))
    fb = sum((f["box"] for f in plan["found"]), [])
    mb = sum((m["box"] for m in plan["made"]), [])
    fp = get("arranger", "found_play")
    pl = plan["play"]
    params = fp.validate({"id": "found_play", "found": len(fparts), "found_boxes": fb, "made_boxes": mb,
                          "lines": len(mparts), "answers": pl["answers"], "answer_p": pl["answer_p"],
                          "catches": pl["catches"], "ride": pl["ride"], "cover_after": pl["cover_after"],
                          "cover_wh": pl["cover_wh"], "bold_pen": pl["bold_pen"], "hair_pen": pl["hair_pen"],
                          "found_pen": pl["found_pen"], "cover_edge": "drawn", "inset": 9.0})
    params.pop("id")
    sub = replace(ctx, module="found_play")
    marks = fp.fn(sub, fparts + mparts, **params)
    kind_of = {100 + k: f["kind"] for k, f in enumerate(plan["found"])}
    out = []
    inner = _inner(ctx)
    for m in marks:
        role = m.meta.get("of_role")
        if "found_play" in m.meta or "rules" in m.meta:     # the logs travel once, in the composer's log
            m = Mark(m.points, m.channels, {k: v for k, v in m.meta.items() if k not in ("found_play", "rules")})
        if role == "found" and not m.meta.get("text"):     # a rotated paste never reaches past the paper
            for q in clip_rect([m.points], inner, 3.0):
                out.append(Mark(q, {}, {**m.meta, "register": "found",
                                        "obj": ["found", kind_of.get(m.meta["part"], "chart")]}))
            continue
        if role == "found":
            reg, key = "found", ("found", kind_of.get(m.meta["part"], "chart"))
        elif role == "edge":
            reg, key = "found", ("found", "cover")
        else:
            reg, key = "made", ("made", int(m.meta.get("line", 0)))
        out.append(m.evolve(meta={"register": reg, "obj": list(key)}))
    play = next((m.meta["found_play"] for m in marks if "found_play" in m.meta), {})
    return out, play


def act_traverse(ctx, plan):
    t = plan["traverse"]
    a, b = np.array(t["a"]), np.array(t["b"])
    L = float(np.linalg.norm(b - a))
    band = float(t["band"])
    box = (0.0, 0.0, L, band)
    kind = t["kind"]
    if kind == "free3966":
        from . import voices_passage as vp  # noqa: PLC0415
        pts, _ = vp.free_opening(ctx.use("hand", "river_belt"), (0.0, 0.0, 285.0, 93.5))
        from .core import fit  # noqa: PLC0415
        s, off = fit([pts], box)
        lines = [pts * s + off]
    else:
        spec = {"belt": {"id": "belt", "hand": t["hand"], "length": 7.0, "gain": 1.0, "gain_end": 3.2},
                "gmorph": {"id": "gmorph", "hand": t["hand"], "length": 8.0,
                           "sign": [0.0, 0.0, 0.35, -1.0, 0.5, 0.6, 0.8, 1.0, 1.0, -0.5],
                           "gain": [0.0, 1.0, 0.4, 2.2, 0.7, 0.8, 1.0, 2.6]},
                "passage": {"id": "passage", "opening": "none", "rows": 1, "max_mm": max(L * 2.2, 200.0)},
                "handover": {"id": "morph_handover", "hands": [t["hand"], "fly_open"], "rows": 1}}[kind]
        lines = [m.points for m in _part(ctx, 300, spec, box).voice(box)]
    ang = math.degrees(math.atan2(*(b - a)[::-1]))
    c = (a + b) / 2
    qs = [rotate(np.asarray(l) - [L / 2, band / 2], np.zeros(2), ang) + c for l in lines if len(l) >= 2]
    # kept whole: shrunk about its centre and moved inside the paper, never clipped into stray pieces
    allq = np.vstack(qs)
    lo, hi = allq.min(axis=0), allq.max(axis=0)
    x0, y0, w, h = ctx.box
    k = min(1.0, (w - 4.0) / max(hi[0] - lo[0], 1e-9), (h - 4.0) / max(hi[1] - lo[1], 1e-9))
    mid = (lo + hi) / 2
    qs = [(q - mid) * k + mid for q in qs]
    allq = np.vstack(qs)
    lo, hi = allq.min(axis=0), allq.max(axis=0)
    blo, bhi = np.array([x0 + 2.0, y0 + 2.0]), np.array([x0 + w - 2.0, y0 + h - 2.0])
    shift = np.clip(blo - lo, 0, None) - np.clip(hi - bhi, 0, None)
    return [Mark(q + shift, {}, {"register": "traverse", "obj": ["traverse", 0], "pen": t["pen"],
                                 "of_role": "traverse"}) for q in qs]


def act_counter(ctx, plan):
    c = plan["counter"]
    box = tuple(c["box"])
    spec = {"mutual": {"id": "mutual", "T": 110},
            "accrue": {"id": "accrue_walk", "hand": "river_belt", "length": 5.0},
            "loops": {"id": "river_loops"},
            "knot": {"id": "hand", "hand": c["hand"], "length": 9.0, "joins": "chain"}}[c["kind"]]
    marks = _part(ctx, 310, spec, box).voice(box)
    out = []
    for m in marks:
        pen = float(m.meta.get("pen", 0.3))
        for piece in clip_rect([m.points], _inner(ctx), 3.0):
            out.append(Mark(piece, {}, {"register": "counter", "obj": ["counter", 0], "pen": pen,
                                        "of_role": "counter"}))
    return out


def container_polygon(plan):
    k = plan["container"]
    cx, cy, w, h = k["rect"]
    return rect_polygon(cx, cy, w, h, k["angle"])


def intruder_lines(plan, box=None):
    out = []
    for m in plan["intruder"]["marks"]:
        p = np.array(m["at"], float)
        L = float(m["length"])
        if m["shape"] == "bar":
            q = np.array([[-L / 2, 0.0], [L / 2, 0.0]])
        elif m["shape"] == "L":
            q = np.array([[-L / 2, 0.0], [L / 2, 0.0], [L / 2, -0.45 * L]])
        elif m["shape"] == "stair":
            k = 4
            st = L / k
            q = [[-L / 2, 0.0]]
            for i in range(k):
                q += [[-L / 2 + (i + 1) * st, -i * st * 0.45], [-L / 2 + (i + 1) * st, -(i + 1) * st * 0.45]]
            q = np.array(q[:-1])
        else:  # knot: a round bead, a tight coil a few mm across
            r = float(np.clip(L * 0.06, 2.0, 4.0))
            t = np.linspace(0, 2 * math.pi * 3.2, 140)
            rr = r * (1 - 0.55 * t / t[-1])
            q = np.c_[rr * np.cos(t), rr * np.sin(t)]
        q = resample(rotate(q, np.zeros(2), m["angle"]) + p, 0.4)
        if box is not None:                       # kept inside the paper, never a stray mark at the edge
            lo = np.array(box[:2]) + 3.0
            hi = np.array(box[:2]) + np.array(box[2:]) - 3.0
            q = q + np.clip(lo - q.min(axis=0), 0, None) - np.clip(q.max(axis=0) - hi, 0, None)
        out.append(q)
    return out


# ---------------------------------------------------------------------------
# 3. the colour layer
# ---------------------------------------------------------------------------

class _Obj:
    """One line as the colour layer sees it: its marks in order, joined by arc length."""

    def __init__(self, key, register, marks):
        self.key, self.register, self.marks = tuple(key), register, marks
        self.pts = np.vstack([m.points for m in marks])
        self.codes = np.concatenate([np.asarray(m.channels["neg"], float) if "neg" in m.channels
                                     else np.zeros(len(m.points)) for m in marks]).astype(int)
        s, off = [], 0.0
        for m in marks:
            a = arclen(m.points)
            s.append(a + off)
            off += a[-1]
        self.s = np.concatenate(s)
        self.bounds = np.cumsum([0] + [len(m.points) for m in marks])


def _runs(mask):
    m = np.r_[False, np.asarray(mask, bool), False]
    d = np.diff(m.astype(int))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1))


def colour(rng, plan: dict, marks: list[Mark], play: dict, *, legend: bool = False):
    """Split every mark into pen runs. Returns (marks, events)."""
    from scipy.spatial import cKDTree  # noqa: PLC0415
    pp = plan["pens"]
    groups: dict = {}
    for m in marks:
        groups.setdefault(tuple(m.meta["obj"]), []).append(m)
    objs = [_Obj(k, ms[0].meta["register"], ms) for k, ms in groups.items()]

    def own_pen(o):
        if legend:
            return {"found": "blue-400", "traverse": "black", "counter": "black", "container": "black",
                    "intruder": "black"}.get(o.register, "black")
        if o.register == "made":
            lp = pp["line_pens"]
            return lp[o.key[1] % len(lp)]
        return pp["own"].get(o.register, pp["palette"][0])

    pen_of = {o.key: own_pen(o) for o in objs}

    def lend_of(o):
        key = f"found:{o.key[1]}" if o.register == "found" else (
            f"line:{o.key[1]}" if o.register == "made" else o.register)
        return pp.get("lend", {}).get(key, pen_of[o.key])

    def line_lend(j):
        return pp.get("lend", {}).get(f"line:{j}", pp["line_pens"][j % len(pp["line_pens"])])
    col = {o.key: np.array([pen_of[o.key]] * len(o.pts), dtype=object) for o in objs}
    events: list[dict] = []
    if legend:
        for o in objs:
            if o.register == "made":
                col[o.key] = np.array([LEGEND.get(int(c), "black") for c in o.codes], dtype=object)
        return _split(objs, col, pp, plan), [{"kind": "legend"}]
    if pp["n"] <= 1:
        return _split(objs, col, pp, plan), events

    # a KD index of every object's points, to name who is touched
    allp = np.vstack([o.pts for o in objs])
    owner = np.concatenate([[i] * len(o.pts) for i, o in enumerate(objs)])
    tree = cKDTree(allp)
    found_pen = {o.key[1]: lend_of(o) for o in objs if o.register == "found"}
    any_found = next(iter(found_pen.values()), pp["palette"][0])
    hand_inf: dict = {}
    for inf in play.get("infections", []):
        if str(inf.get("caught", "")).startswith("line"):
            hand_inf.setdefault(int(inf["line"]), []).append(int(inf["caught"][4:]))
    answers = {int(a["line"]): int(a["to"]) for a in play.get("answers", [])}

    def nearest_other(oi, idx, r=2.5, register=None):
        for j in tree.query_ball_point(objs[oi].pts[idx], r):
            k = int(owner[j])
            if k != oi and (register is None or objs[k].register == register):
                return objs[k]
        return None

    cands = []
    on = set(pp["events"])
    for oi, o in enumerate(objs):
        mine = pen_of[o.key]
        if o.register == "made":
            li = o.key[1]
            hand_seen = 0
            for code in (1, 5, 6, 7, 8, 9, 10):
                for a, b in _runs(o.codes == code):
                    if b - a < 2:
                        continue
                    kind, lender, why = None, None, ""
                    if code in (6, 7, 8) and "carry" in on:
                        kind = "carry"
                        lender = found_pen.get("river" if code == 6 else "chart", any_found)
                        why = "carries the river" if code == 6 else "carries the chart"
                    elif code == 9 and "carry" in on:
                        src = hand_inf.get(li, [])
                        j = src[hand_seen] if hand_seen < len(src) else max(li - 1, 0)
                        hand_seen += 1
                        kind, lender, why = "carry", line_lend(j), f"carries line {j}'s hand"
                    elif code == 5 and "carry" in on:
                        nb = nearest_other(oi, a, 8.0, "found")
                        kind, lender, why = "carry", lend_of(nb) if nb else any_found, "plays the found contour it left"
                    elif code == 1 and "ride" in on:
                        nb = nearest_other(oi, (a + b) // 2, 2.5)
                        if nb is not None:
                            kind, lender, why = "ride", lend_of(nb), f"rides {nb.register} {nb.key[1]}"
                    elif code == 10 and "answer" in on and li in answers:
                        j = answers[li]
                        kind, lender, why = "answer", line_lend(j), f"answers line {j}"
                    if kind and lender != mine:
                        cands.append({"obj": oi, "a": int(a), "b": int(b), "pen": lender, "kind": kind, "why": why})
            if "reverse" in on:
                for a, b in _runs(o.codes == 1):
                    nb = nearest_other(oi, (a + b) // 2, 2.5, "found")
                    back = lend_of(o)
                    if nb is None or pen_of[nb.key] == back:
                        continue
                    seg = cKDTree(o.pts[a:b + 1])
                    d, _ = seg.query(nb.pts)
                    for ra, rb in _runs(d < 2.0):
                        if nb.s[rb] - nb.s[ra] > 4.0:
                            cands.append({"obj": objs.index(nb), "a": int(ra), "b": int(rb), "pen": back,
                                          "kind": "reverse", "why": f"the {nb.key[1]} takes back line {li}'s pen"})
        if "contact" in on and o.register in ("traverse", "counter"):
            others = np.flatnonzero(owner != oi)
            if len(others):
                sub = cKDTree(allp[others])
                d, j = sub.query(o.pts[::4])
                hit = np.flatnonzero(d < 0.6) * 4
                last = -1e9
                for i in hit:
                    if o.s[i] - last < 40.0:
                        continue
                    nb = objs[int(owner[others[j[i // 4]]])]
                    if lend_of(nb) != mine and nb.register != o.register:
                        cands.append({"obj": oi, "a": int(i), "b": int(i), "pen": lend_of(nb), "kind": "contact",
                                      "why": f"touches {nb.register} and catches its pen"})
                        last = o.s[i]
        if "spill" in on and plan.get("container") and o.register in ("made", "traverse", "counter"):
            if not (o.register == "made" and o.key[1] == plan["container"]["refuse"]):
                from shapely import contains_xy  # noqa: PLC0415
                from shapely.geometry import Polygon  # noqa: PLC0415
                inside = contains_xy(Polygon(container_polygon(plan)), o.pts[:, 0], o.pts[:, 1])
                kp = pp["own"].get("container", pp["palette"][-1])
                for a, b in _runs(inside):          # only a line that crosses the edge is stained
                    if 6.0 < o.s[b] - o.s[a] < 0.6 * o.s[-1] and kp != mine:
                        cands.append({"obj": oi, "a": int(a), "b": int(b), "pen": kp, "kind": "spill",
                                      "why": "stained inside the container, spills out"})

    # the budget: a few events per sheet, at most `per_line` per object; longer ones likelier
    order = sorted(range(len(cands)), key=lambda i: (cands[i]["obj"], cands[i]["a"], cands[i]["kind"]))
    w = np.array([max(objs[cands[i]["obj"]].s[cands[i]["b"]] - objs[cands[i]["obj"]].s[cands[i]["a"]], 4.0) ** 0.5
                  * (2.0 if cands[i]["kind"] in ("spill", "carry") else 1.0) for i in order])
    chosen, per = [], {}
    if len(order):
        k = min(len(order), pp["budget"] * 3)
        pick = rng.choice(len(order), size=k, replace=False, p=w / w.sum())
        for q in pick:
            c = cands[order[int(q)]]
            if per.get(c["obj"], 0) >= pp["per_line"] or len(chosen) >= pp["budget"]:
                continue
            per[c["obj"]] = per.get(c["obj"], 0) + 1
            chosen.append(c)
    chosen.sort(key=lambda c: (c["obj"], c["a"]))
    for c in chosen:
        o = objs[c["obj"]]
        a, b = c["a"], c["b"]
        lie = "none"
        r = rng.random()
        if c["kind"] in ("contact", "spill") or r < pp["p_lie"]:
            extra = float(np.clip(rng.lognormal(math.log(pp["lie_mm"]), 0.5), 8.0, 400.0))
            b = int(np.searchsorted(o.s, o.s[b] + extra))
            lie = f"{extra:.0f} mm"
        if rng.random() < pp["p_end"] and c["kind"] != "reverse":
            b, lie = len(o.pts) - 1, "to the end"
        b = min(b, len(o.pts) - 1)
        col[o.key][a:b + 1] = c["pen"]
        events.append({"obj": list(o.key), "kind": c["kind"], "pen": c["pen"], "why": c["why"],
                       "at_mm": round(float(o.s[a]), 1), "len_mm": round(float(o.s[b] - o.s[a]), 1), "lie": lie})
    for o in objs:
        col[o.key] = _settle(col[o.key], o.s, pen_of[o.key], pp["min_run"])
    return _split(objs, col, pp, plan), events


def _settle(c, s, own, min_run):
    """A pen change is an event: one forward pass holds each borrowed pen for at least min_run mm
    (blips inside a held run are swallowed), a run cut short by the line's end grows backwards, and
    short own gaps between two runs of the same borrowed pen are filled (no confetti)."""
    n = len(c)
    out = np.array([own] * n, dtype=object)
    i = 0
    while i < n:
        if c[i] == own:
            i += 1
            continue
        p, j = c[i], i
        while j + 1 < n and c[j + 1] == p:
            j += 1
        end_s = max(s[j], s[i] + min_run)
        k = j
        while k + 1 < n and s[k + 1] <= end_s:
            k += 1
        out[i:k + 1] = p
        if s[k] - s[i] < min_run:
            a = int(np.searchsorted(s, s[k] - min_run))
            back = np.arange(a, i)
            out[back[out[back] == own]] = p
        i = k + 1
    cut = np.r_[0, np.flatnonzero(out[1:] != out[:-1]) + 1, n]
    runs = [(int(a), int(b) - 1, out[a]) for a, b in zip(cut[:-1], cut[1:])]
    for k in range(1, len(runs) - 1):
        a, b, p = runs[k]
        if p == own and runs[k - 1][2] == runs[k + 1][2] and s[b] - s[a] < min_run:
            out[a:b + 1] = runs[k - 1][2]
    return out


def _split(objs, col, pp, plan):
    out = []
    for o in objs:
        c = col[o.key]
        for mi, m in enumerate(o.marks):
            a0, b0 = int(o.bounds[mi]), int(o.bounds[mi + 1])
            cm = c[a0:b0]
            cut = np.r_[0, np.flatnonzero(cm[1:] != cm[:-1]) + 1, len(cm)]
            pen = float(m.meta.get("pen", pp["weights"].get(o.register, 0.4)))
            if o.register in pp["weights"] and o.register not in ("found", "counter"):
                pen = float(pp["weights"][o.register])
            for a, b in zip(cut[:-1], cut[1:]):
                e = min(int(b) + 1, len(m.points))          # runs share their boundary point: one line
                if e - int(a) < 2:
                    continue
                ch = {k: np.asarray(v)[int(a):e] for k, v in m.channels.items()}
                out.append(Mark(m.points[int(a):e], ch, {**{k: v for k, v in m.meta.items() if k != "fit"},
                                                          "ink": str(cm[a]), "pen": pen, "part": 0}))
    return out


# ---------------------------------------------------------------------------
# 4. the arranger
# ---------------------------------------------------------------------------

@arranger("ccolour", params=[
    P("density", "float", -1.0, "the density dial 0 … 1 (-1 = the composer decides, extremes allowed)",
      min=-1.0, max=1.0),
    P("pens", "int", 0, "how many pens 1–5 (0 = the composer decides)", min=0, max=5),
    P("mode", "choice", "auto", "who owns which pen: registers | lines | mono | inverted | pair | auto",
      choices=("auto",) + MODES),
    P("colouring", "choice", "composed", "composed: the pen plan (events, budget, lies) | legend: every role "
      "always in its fixed pen, the round-13 map (the dud control)", choices=("composed", "legend")),
    P("acts", "str", "core,traverse,counter,container,intruder", "which acts may enter (comma list)"),
], doc="b4: a composer whose pens carry what each line is doing — registers own pens and lend them briefly "
        "(T6), a container stains and spills (T4), a heavy intruder in its own pen (T3); decided per sheet")
def ccolour(ctx, parts, *, density, pens, mode, colouring, acts):
    W, H = ctx.frame
    allowed = {a.strip() for a in acts.split(",") if a.strip()}
    plan = decide(ctx.rng("decide"), W, H, density=density, pens=pens, mode=mode,
                  hands=[p.spec["voice"].get("hand") for p in parts if p.spec["voice"].get("hand")])
    for k in ("traverse", "counter", "container", "intruder"):
        if k not in allowed:
            plan[k] = None
    if any(k not in allowed for k in ("traverse", "counter", "container", "intruder")):
        plan["pens"] = pen_plan(ctx.rng("pens"), plan, pens=pens, mode=mode)
    marks, play = act_core(ctx, plan, parts)
    order = ["found", "made"]
    if plan["container"]:
        poly = container_polygon(plan)
        marks.append(Mark(poly, {}, {"register": "container", "obj": ["container", 0], "of_role": "container",
                                     "pen": plan["container"]["pen"]}))
        order.insert(1, "container")
    if plan["counter"]:
        marks += act_counter(ctx, plan)
        order.append("counter")
    late = []
    if plan["traverse"]:
        late.append(("traverse", act_traverse(ctx, plan)))
    if plan["intruder"]:
        ink = [Mark(q, {}, {"register": "intruder", "obj": ["intruder", i], "of_role": "intruder",
                            "pen": plan["intruder"]["pen"]}) for i, q in enumerate(intruder_lines(plan, ctx.box))]
        late.append(("intruder", ink))
    rng = ctx.rng("order")
    if len(late) == 2 and rng.random() < 0.4:
        late.reverse()                                   # T5: sometimes the traverse crosses the intruder
    for name, ms in late:
        marks += ms
        order.append(name)
    out, events = colour(ctx.rng("colour"), plan, marks, play, legend=(colouring == "legend"))
    # a last guarantee that nothing touches the paper's edge (an entry step can graze it by a hair)
    lo, hi = np.array([1.0, 1.0]), np.array([W - 1.0, H - 1.0])
    out = [m if (m.points.min(axis=0) >= lo).all() and (m.points.max(axis=0) <= hi).all()
           else m.evolve(points=np.clip(m.points, lo, hi)) for m in out]
    pens_used = sorted({m.meta["ink"] for m in out})
    log = {"plan": plan, "order": order, "events": events, "pens_used": pens_used,
           "catches": len(play.get("infections", [])), "answers": len(play.get("answers", []))}
    if out:
        out[0] = out[0].evolve(meta={"ccolour": log})
    return out


def recipe(seed: int, *, frame=None, **arr) -> dict:
    """A ccolour recipe: the frame is chosen per seed, on purpose (FRAMES), unless given."""
    rng = np.random.default_rng([0xCC01, int(seed)])
    f = FRAMES[int(rng.choice(len(FRAMES), p=[0.32, 0.17, 0.17, 0.17, 0.17]))]
    W, H, why = (frame[0], frame[1], "given") if frame else f
    a = {"id": "ccolour"}
    a.update(arr)
    return {"label": "ccolour", "notes": f"frame {W:g}×{H:g}: {why}", "frame": [W, H], "seed": int(seed),
            "margin": 5.0, "arranger": a,
            "parts": [{"voice": {"id": "hand", "hand": h, "length": 3.0, "joins": "smooth"}} for h in HAND_POOL],
            "renderer": {"id": "oehlen_found_ink", "pen": 0.4}}


# ---------------------------------------------------------------------------
# 5. preview: pens multiply on paper
# ---------------------------------------------------------------------------

def _hex(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def render_pens(sheet, *, px_per_mm: float = 6.0, ss: int = 2, grain: bool = True):
    """PIL image: each ink at its pen width in its Flexoki pen, pens multiplied (as inks on paper)."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    W, H = sheet.frame
    k = px_per_mm * ss
    size = (int(round(W * k)), int(round(H * k)))
    out_size = (size[0] // ss, size[1] // ss)
    rgb = np.ones((out_size[1], out_size[0], 3)) * np.array(PAPER, float)
    if grain:
        g = np.random.default_rng(0xCC0).normal(0, 1.2, (out_size[1], out_size[0], 1))
        rgb = np.clip(rgb + g, 0, 255)
    colours = sorted({(ink.meta.get("colour") or "black") for ink in sheet.inks})
    for c in colours:
        im = Image.new("L", size, 0)
        dr = ImageDraw.Draw(im)
        for ink in sheet.inks:
            if (ink.meta.get("colour") or "black") != c or len(ink.points) < 2:
                continue
            q = ink.points * k
            d = max(ink.pen * k, 1.0)
            dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
            r = d / 2
            for v in q[[0, -1]]:
                dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
        im = im.resize(out_size, Image.Resampling.BOX)
        a = np.asarray(im, float)[..., None] / 255.0 * 0.94
        pen = _hex(FLEXOKI.get(c, FLEXOKI["black"])) / 255.0
        rgb = rgb * (1 - a * (1 - pen))
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
