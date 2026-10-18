"""Round 14, thread b1 `cproc` — composer as procedure.

Ian (2026-10-18): the round-13 studies "do what they're supposed to" but he
"would have thought they were more dynamic … making full compositions which
are different every time". A fixed layout with a varying line is a template.
So here the COMPOSITION is decided per sheet, from the seed, before a line is
drawn, and the kit's praised techniques are played into it as players.

The lead's composition note (results/oehlen-composition-2026-10-18.md) gives
this thread three tensions, used as dials whose settings vary per sheet:

  T1 core against blank   "Density is a dial set per sheet, and the dial has
                          extremes." The density dial is drawn from a U-shaped
                          Beta(0.45, 0.45), so the extremes (a few lines on an
                          empty sheet / all-over) come up often. Core position,
                          core count (one, or a counterweight), blank kind
                          (side / corner / band / island / none) and its share
                          are decided per sheet.
  T2 a ladder of scales   at least three rungs (small periodic matter, middle
                          hands, the long traverse); the ladder's spread is a
                          dial. The traverse is a strip voice laid along a
                          spine that runs through the core AND the blank: it
                          "belongs to neither".
  T5 order with reversals the habit found → structure → hand → heavy, perturbed
                          by a per-sheet disorder dial (a found piece that
                          arrives after the hands is pasted over them and cuts
                          them); one late act cuts back (cover, tint, band or
                          pasted patch), then a line crosses the cover.

Players (techniques that work, mechanisms not looks):
  found      oehlen_found_river at a per-sheet zoom (never one fixed far zoom),
             river_braid, river_loops, diagram (the chart), trail_sheet
  structure  handover specimen rows (Cohen key, bowed key, coiled, waves), chart
  hand       negotiate (found ground: grow / ride / ignore), catch
             (contagion_walk: river, chart, specimen and earlier hands carried
             away and shed), answer (found_play's call: grow out of an earlier
             line's end in the air), passage (one line through many hands),
             free (accrue's seed-3966 free hand, quoted whole at any scale),
             limb (limb signs), soup (mutual's dense call and response)
  traverse   belt (gain morphing along the line), passage (one row), waves
             (handover specimen 5), arc (one hand at the scale of the sheet),
             river (a strip of the stem)
  heavy      re-ink a stretch at the core's edge, a heavy gesture, a heavy limb
  reversal   cover (cut), tint, band (a torn strip: erasure), paste (found matter
             pasted late, cutting what is under it)
  cross      a line through the cover; it may ride the cover's (undrawn) edge

Use: `recipe(seed)` decides the frame on purpose and returns a recipe;
`kit.run(recipe)` decides everything else from the seed (ctx.rng) and
executes. The decisions are in `marks[0].meta["cproc"]` (`plan`, `acts`).
Render with `render(sheet)` / `save(sheet, path)` (colour by meta ink).
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from . import voices_accrue as va
from .arrangers_contagion import contagion_walk, river_grammar
from .arrangers_found_play import HAND_CODE, HAND_RIDE, chart_grammar, hand_gen
from .arrangers_oehlen_found import (FLEXOKI, Ground, arclen, clip_rect, cover_polygon, negotiate, rect_polygon,
                                     resample, rotate, tangents)
from .arrangers_oehlen_found import render_colour as _render_colour
from .core import Ink, Mark, P, Part, _module_spec, arranger, renderer, tag, voice

STEP = 0.4

# ---------------------------------------------------------------------------
# the vocabulary (kept across the series; the distribution varies per sheet)
# ---------------------------------------------------------------------------

HANDS = ("dance_thrusting", "river_bend", "trail_miner", "dancer_madeline", "mime_mantis", "hokusai",
         "meander69", "fly_open", "dance_staccato", "mime_roadrunner", "river_meander", "mime_monkey")
HEAVY_HANDS = ("dance_thrusting", "mime_mantis", "hokusai", "dance_staccato", "mime_roadrunner")
# handover specimen keys (results/handover-3-specimens; Ian: "really love 5" = waves; 1/2/4 promising)
SPECIMENS = {"cohen_key": [2.0, 2.0, 2.0, 2.0, 2.0, 2.0], "bowed_key": [-1.0, -1.0, 2.0, 2.0, 2.0, 2.0],
             "coiled": [-1.0, -1.0, -1.0, -1.0, 2.0, 2.0], "waves": [-1.0, -1.0, 2.0, 2.0, -1.0, -1.0]}
SPECIMEN_HAND = {"cohen_key": "meander69", "bowed_key": "fly_open", "coiled": "fly_open", "waves": "fly_open"}
FOUND_KINDS = ("river", "braid", "loops", "chart", "trail")
RIVERISH = ("river", "braid", "loops")
FOUND_INKS = ("blue", "cyan", "green", "purple", "orange")

# frames chosen on purpose (all inside the AxiDraw's 300 × 218, either way up)
FRAMES = (
    ("strip", (300.0, 80.0), "a strip: the traverse is longer than the eye takes in at once"),
    ("landscape", (300.0, 200.0), "the full bed: room for a decided blank"),
    ("square", (210.0, 200.0), "near square: no direction is given, the core decides it"),
    ("portrait", (200.0, 290.0), "portrait: a high core and a lower blank, or the reverse"),
    ("small", (150.0, 105.0), "a small sheet: density compresses, every scale is near"),
    ("column", (105.0, 290.0), "a column: the traverse falls, the scales stack"),
    ("band", (300.0, 140.0), "a low band: wide, but short enough that density meets both edges"),
)


def frame_for(seed: int) -> tuple[list[float], str, str]:
    """The frame, decided from the seed alone (before kit.run, which needs it)."""
    rng = np.random.default_rng([int(seed), tag("cproc"), tag("frame")])
    w = np.array([0.6, 1.2, 1.0, 1.1, 0.8, 0.6, 0.8])
    k = int(rng.choice(len(FRAMES), p=w / w.sum()))
    name, wh, why = FRAMES[k]
    return [float(wh[0]), float(wh[1])], name, why


def recipe(seed: int, **dials) -> dict:
    """A full cproc recipe: the frame decided on purpose, the rest at run time."""
    frame, name, why = frame_for(seed)
    arr = {"id": "cproc", "frame_name": name}
    arr.update(dials)
    return {"label": f"cproc {seed}", "frame": frame, "seed": int(seed), "margin": 4.0, "arranger": arr,
            "parts": [{"voice": {"id": "cproc_score"}}], "renderer": {"id": "cproc_ink", "pen": 0.4},
            "notes": f"frame: {name} — {why}"}


@voice("cproc_score", params=[], doc="placeholder part: the cproc arranger composes the whole sheet itself")
def cproc_score(ctx):
    return []


# ---------------------------------------------------------------------------
# the score: what is on the paper so far
# ---------------------------------------------------------------------------

class Score:
    """Everything drawn so far, in order, as Marks with their role meta."""

    def __init__(self, W, H):
        self.W, self.H = W, H
        self.items: list[dict] = []

    def add(self, pts_or_mark, *, role, ink, pen, act, player, regime=None, hand=None, nib=None, **extra):
        if isinstance(pts_or_mark, Mark):
            m = pts_or_mark if nib else Mark(resample(pts_or_mark.points, STEP), {}, {})
            if nib:
                m = m.resampled(STEP) if len(m.points) > 2 else m
        else:
            p = np.asarray(pts_or_mark, float)
            if len(p) < 2:
                return None
            m = Mark(resample(p, STEP), {}, {})
        if len(m.points) < 2:
            return None
        it = {"mark": m, "role": role, "ink": ink, "pen": float(pen), "act": act, "player": player,
              "regime": regime, "hand": hand, "nib": nib, **extra}
        self.items.append(it)
        return it

    def lines(self, roles=None, regimes=None):
        return [it["mark"].points for it in self.items
                if (roles is None or it["role"] in roles) and (regimes is None or it["regime"] in regimes)]

    def cut(self, polys, modes, tint_ink, min_stub=3.0):
        """A late act cuts back: points under a cut polygon go; under a tint polygon they are re-inked."""
        from shapely import contains_xy  # noqa: PLC0415
        from shapely.geometry import Polygon  # noqa: PLC0415
        cutP = [Polygon(q) for q, md in zip(polys, modes) if md == "cut"]
        tintP = [Polygon(q) for q, md in zip(polys, modes) if md == "tint"]
        out, removed = [], 0.0
        for it in self.items:
            m = it["mark"]
            p = m.points
            inc = np.zeros(len(p), bool)
            for P_ in cutP:
                inc |= contains_xy(P_, p[:, 0], p[:, 1])
            int_ = np.zeros(len(p), bool)
            for P_ in tintP:
                int_ |= contains_xy(P_, p[:, 0], p[:, 1])
            int_ &= ~inc
            if not inc.any() and not int_.any():
                out.append(it)
                continue
            state = np.where(inc, 0, np.where(int_, 2, 1))       # 0 gone, 1 kept, 2 tinted
            cuts = np.r_[0, np.flatnonzero(np.diff(state)) + 1, len(p)]
            s = arclen(p)
            for a, b in zip(cuts[:-1], cuts[1:]):
                st = int(state[a])
                if st == 0:
                    removed += float(s[b - 1] - s[a])
                    continue
                if b - a < 2 or (s[b - 1] - s[a] < min_stub and b - a < len(p)):
                    continue
                sub = Mark(p[a:b], {k: v[a:b] for k, v in m.channels.items()}, dict(m.meta))
                out.append({**it, "mark": sub, "ink": tint_ink if st == 2 else it["ink"],
                            "tinted": st == 2 or it.get("tinted", False)})
        self.items = out
        return removed


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def _poly_area(q):
    q = np.asarray(q, float)
    return 0.5 * abs(float(np.dot(q[:, 0], np.roll(q[:, 1], 1)) - np.dot(q[:, 1], np.roll(q[:, 0], 1))))


def bezier(P0, P1, P2, P3, n=600):
    t = np.linspace(0, 1, n)[:, None]
    return ((1 - t) ** 3) * P0 + 3 * ((1 - t) ** 2) * t * P1 + 3 * (1 - t) * t * t * P2 + t ** 3 * P3


def lay_along(lines, spine, x0=0.0, yc=0.0):
    """Lines drawn in a strip (x along, y across, mm) laid along a spine:
    x → arc length along it, y − yc → offset along its normal."""
    sp = resample(spine, 0.5)
    s = arclen(sp)
    t = tangents(sp, 6)
    nrm = np.c_[-t[:, 1], t[:, 0]]
    out = []
    for l in lines:
        u = l[:, 0] - x0
        ok = (u >= 0) & (u <= s[-1])
        if ok.sum() < 2:
            continue
        cuts = np.r_[0, np.flatnonzero(np.diff(ok.astype(int))) + 1, len(u)]
        for a, b in zip(cuts[:-1], cuts[1:]):
            if not ok[a] or b - a < 2:
                continue
            uu, vv = u[a:b], l[a:b, 1] - yc
            px = np.interp(uu, s, sp[:, 0]) + vv * np.interp(uu, s, nrm[:, 0])
            py = np.interp(uu, s, sp[:, 1]) + vv * np.interp(uu, s, nrm[:, 1])
            out.append(np.c_[px, py])
    return out


def inside_runs(pts, bounds, min_mm=3.0):
    """The stretches of a line inside bounds (never clamped onto the edge: no stray runs along it)."""
    p = resample(np.asarray(pts, float), STEP)
    if len(p) < 2:
        return []
    x0, y0, x1, y1 = bounds
    ok = (p[:, 0] >= x0) & (p[:, 0] <= x1) & (p[:, 1] >= y0) & (p[:, 1] <= y1)
    if ok.all():
        return [p]
    cuts = np.r_[0, np.flatnonzero(np.diff(ok.astype(int))) + 1, len(p)]
    return [p[a:b] for a, b in zip(cuts[:-1], cuts[1:]) if ok[a] and b - a >= 2 and arclen(p[a:b])[-1] >= min_mm]


def inside_rect(rect, bounds):
    cx, cy, w, h, ang = rect
    q = rect_polygon(cx, cy, w, h, ang)
    x0, y0, x1, y1 = bounds
    return bool(q[:, 0].min() >= x0 and q[:, 1].min() >= y0 and q[:, 0].max() <= x1 and q[:, 1].max() <= y1)


def fit_rect(rect, bounds, shrink=0.9, tries=12):
    """Shrink (then pull toward the sheet) a rotated rect until it lies inside bounds."""
    cx, cy, w, h, ang = rect
    x0, y0, x1, y1 = bounds
    for _ in range(tries):
        if inside_rect((cx, cy, w, h, ang), bounds):
            return (cx, cy, w, h, ang)
        q = rect_polygon(cx, cy, w, h, ang)
        dx = max(x0 - q[:, 0].min(), 0) - max(q[:, 0].max() - x1, 0)
        dy = max(y0 - q[:, 1].min(), 0) - max(q[:, 1].max() - y1, 0)
        cx, cy = cx + dx, cy + dy
        if not inside_rect((cx, cy, w, h, ang), bounds):
            w, h = w * shrink, h * shrink
    return (cx, cy, w, h, ang)


@lru_cache(maxsize=1)
def free_hand_3966() -> np.ndarray:
    """Accrue's seed-3966 free hand (Ian: "love love"), exactly as voices_passage.free_opening
    evaluates it, at its recorded 285 × 93 mm: a quotation the composer may place at any scale."""
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from . import library as L  # noqa: PLC0415
    path = Path(__file__).resolve().parents[2] / "results/accrue-3-variants.recipe.json"
    rec = json.loads(path.read_text())[2]["recipe"]
    kw = dict(rec["parts"][0]["voice"])
    kw.pop("id")
    kw.pop("hand")
    R = kw.pop("scale") * 0.95 * float(np.hypot(285, 93))
    g = L.load("hand", "river_belt")
    pts, _c, _e = va.walk(g, np.random.default_rng([3966, 0xACC0E]), R=R, box=(0, 0, 285, 93), **kw)
    return np.asarray(pts, float)


# ---------------------------------------------------------------------------
# the decision: one plan per sheet
# ---------------------------------------------------------------------------

def _density_label(d):
    return "sparse" if d < 0.12 else "open" if d < 0.45 else "dense" if d < 0.88 else "all-over"


def decide(rng: np.random.Generator, W: float, H: float, *, density=None, frame_name="given") -> dict:
    """Every compositional decision for one sheet, as JSON."""
    S, Lg = min(W, H), max(W, H)
    d = float(rng.beta(0.45, 0.45)) if density is None else float(density)
    lab = _density_label(d)
    plan: dict = {"frame": [W, H], "frame_name": frame_name, "density": round(d, 3), "density_label": lab}

    # --- T1: cores and blank
    def off_centre():
        for _ in range(50):
            c = rng.uniform(0.14, 0.86, 2)
            if abs(c[0] - 0.5) > 0.12 or abs(c[1] - 0.5) > 0.12:
                return c
        return c
    c1 = off_centre() * [W, H]
    rc = S * (0.16 + 0.42 * d) * float(rng.uniform(0.75, 1.25))
    if lab == "all-over":
        rc = 0.75 * float(np.hypot(W, H))
    cores = [{"xy": c1.round(1).tolist(), "r": round(rc, 1), "weight": 1.0}]
    two = rng.random() < (0.25 + 0.3 * (0.2 < d < 0.85))
    bw = {"sparse": [3, 3, 1, 0, 0.3], "open": [3, 2, 2, 1, 0.5], "dense": [2, 1.5, 2, 1.5, 1],
          "all-over": [0.3, 0.3, 0.6, 2, 3]}[lab]
    kinds = ("side", "corner", "band", "island", "none")
    p = np.array(bw, float)
    bkind = kinds[int(rng.choice(5, p=p / p.sum()))]
    blank = None
    if bkind == "side":
        dist = {"left": c1[0], "right": W - c1[0], "top": c1[1], "bottom": H - c1[1]}
        side = max(sorted(dist), key=lambda k: dist[k] / (W if k in ("left", "right") else H))
        share = float(rng.uniform(0.3, 0.45) if d > 0.15 else rng.uniform(0.45, 0.72))
        if side == "left":
            blank = [[0, 0], [share * W, 0], [share * W, H], [0, H]]
        elif side == "right":
            blank = [[W * (1 - share), 0], [W, 0], [W, H], [W * (1 - share), H]]
        elif side == "top":
            blank = [[0, 0], [W, 0], [W, share * H], [0, share * H]]
        else:
            blank = [[0, H * (1 - share)], [W, H * (1 - share)], [W, H], [0, H]]
        binfo = {"kind": "side", "side": side, "share": round(share, 2)}
    elif bkind == "corner":
        cx = 0.0 if c1[0] > W / 2 else W
        cy = 0.0 if c1[1] > H / 2 else H
        fw, fh = rng.uniform(0.4, 0.7, 2) * [W, H] * (1.15 if d < 0.15 else 1.0)
        x0, x1 = sorted([cx, cx + (fw if cx == 0 else -fw)])
        y0, y1 = sorted([cy, cy + (fh if cy == 0 else -fh)])
        blank = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
        binfo = {"kind": "corner", "at": [cx, cy], "share": round(float(fw * fh / (W * H)), 2)}
    elif bkind == "band":
        ang = float(rng.uniform(0, 180))
        u = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
        nrm = np.array([-u[1], u[0]])
        sgn = 1.0 if np.dot(np.array([W / 2, H / 2]) - c1, nrm) >= 0 else -1.0
        q0 = c1 + sgn * nrm * (rc + S * float(rng.uniform(0.05, 0.2)))
        bw_ = S * float(rng.uniform(0.14, 0.3))
        Lb = 2 * Lg
        q = np.array([q0 - u * Lb, q0 + u * Lb, q0 + u * Lb + sgn * nrm * bw_, q0 - u * Lb + sgn * nrm * bw_])
        blank = q.tolist()
        two = True
        binfo = {"kind": "band", "angle": round(ang, 1), "width": round(bw_, 1)}
    elif bkind == "island":
        for _ in range(40):
            ce = rng.uniform(0.2, 0.8, 2) * [W, H]
            if np.linalg.norm(ce - c1) > 0.3 * S:
                break
        rx, ry = S * rng.uniform(0.1, 0.22, 2)
        a = np.linspace(0, 2 * math.pi, 40, endpoint=False)
        blank = np.c_[ce[0] + rx * np.cos(a), ce[1] + ry * np.sin(a)].tolist()
        binfo = {"kind": "island", "at": ce.round(1).tolist()}
    else:
        binfo = {"kind": "none"}
    plan["blank"] = {**binfo, "poly": None if blank is None else np.round(blank, 1).tolist()}

    if two:
        # a counterweight: smaller, elsewhere (across the band when there is one)
        for _ in range(60):
            c2 = rng.uniform(0.12, 0.88, 2) * [W, H]
            if np.linalg.norm(c2 - c1) < 0.45 * S:
                continue
            if blank is not None:
                from shapely.geometry import Point, Polygon  # noqa: PLC0415
                if Polygon(blank).buffer(4).contains(Point(*c2)):
                    continue
            break
        cores.append({"xy": c2.round(1).tolist(), "r": round(rc * float(rng.uniform(0.3, 0.6)), 1),
                      "weight": round(float(rng.uniform(0.25, 0.5)), 2)})
    plan["cores"] = cores

    # --- T2: the ladder of scales (mm); its spread is a dial
    spread = float(rng.uniform(0.0, 1.0))
    small = S * (0.035 + 0.05 * (1 - spread)) * float(rng.uniform(0.8, 1.2))
    mid = S * (0.28 + 0.3 * rng.random())
    plan["ladder"] = {"spread": round(spread, 2), "small_mm": round(small, 1), "mid_mm": round(mid, 1),
                      "large_mm": round(0.95 * Lg, 1)}

    # --- the vocabulary's distribution on this sheet
    hands = list(rng.choice(HANDS, size=int(rng.integers(2, 5)), replace=False))
    plan["hands"] = [str(h) for h in hands]
    plan["found_ink"] = str(rng.choice(FOUND_INKS))
    plan["made_ink"] = "black"
    plan["second_ink"] = str(rng.choice([c for c in ("red", "orange", "blue", "purple") if c != plan["found_ink"]]))
    plan["tint_ink"] = str(rng.choice([c for c in ("red", "green", "orange", "magenta") if c != plan["found_ink"]]))
    plan["disorder"] = round(float(rng.uniform(0.15, 1.5)), 2)
    plan["weight_follows_ground"] = bool(rng.random() < 0.45)

    # --- which register dominates this sheet (the series varies it: lead's note)
    dw = {"found": 1.0, "structure": 0.8, "traverse": 1.0, "hand": 1.0, "soup": 0.7 if d > 0.45 else 0.0}
    dn = sorted(dw)
    dp = np.array([dw[n] for n in dn])
    dom = str(rng.choice(dn, p=dp / dp.sum()))
    plan["dominant"] = dom

    # --- acts (T5): habit order, perturbed by the disorder dial
    acts = []
    nf = {"sparse": int(rng.integers(0, 2)), "open": int(rng.integers(1, 3)), "dense": int(rng.integers(1, 4)),
          "all-over": int(rng.integers(2, 5))}[lab]
    fw = np.array([1.0, 0.8, 0.8, 1.0, 0.4])
    fk = list(rng.choice(FOUND_KINDS, size=min(nf, 5), replace=False, p=fw / fw.sum()))
    if dom == "found" and not fk:
        fk = [str(rng.choice(FOUND_KINDS, p=fw / fw.sum()))]
    for j, k in enumerate(fk):
        acts.append({"act": "found", "player": str(k), "habit": 0.0, **({"dominant": True} if dom == "found" and j == 0
                                                                       else {})})
    if dom == "structure" or rng.random() < 0.25 + 0.45 * d:
        st = "specimens" if ("chart" in fk or rng.random() < 0.65) else "chart"
        acts.append({"act": "structure", "player": st, "habit": 1.0, **({"dominant": True} if dom == "structure" else {})})
    nh = int(np.clip(round(0.6 + 8.5 * d + rng.normal(0, 0.8)), 1, 10))
    if dom in ("found", "structure", "traverse"):
        nh = max(1, int(round(nh * 0.6)))         # the dominant register keeps the weight: fewer hands
    hp = {"negotiate": 1.0, "catch": 1.4 if fk else 0.3, "answer": 0.9, "passage": 0.5, "free": 0.45,
          "limb": 0.45}
    names = sorted(hp)
    pr = np.array([hp[n] for n in names])
    for i in range(nh):
        pl = str(rng.choice(names, p=pr / pr.sum()))
        if pl == "answer" and i == 0:
            pl = "negotiate"
        acts.append({"act": "hand", "player": pl, "habit": 2.0})
    if dom == "soup" or (d > 0.5 and rng.random() < 0.4):
        acts.append({"act": "hand", "player": "soup", "habit": 1.8, **({"dominant": True} if dom == "soup" else {})})
    if len(cores) > 1:
        acts.append({"act": "counter", "player": "cluster", "habit": 2.2})
    if dom == "traverse" or rng.random() < 0.8 or lab == "sparse":
        tp = {"belt": 1.2, "passage": 0.8, "waves": 1.0, "arc": 1.0, "river": 0.35}
        tn = sorted(tp)
        tpr = np.array([tp[n] for n in tn])
        for j in range(2 if (dom == "traverse" and rng.random() < 0.5) else 1):
            acts.append({"act": "traverse", "player": str(rng.choice(tn, p=tpr / tpr.sum())), "habit": 2.5,
                         **({"dominant": True} if dom == "traverse" else {})})
    if blank is not None and rng.random() < 0.55:
        acts.append({"act": "trail_off", "player": "hand", "habit": 3.0})
    if rng.random() < 0.78:
        acts.append({"act": "heavy", "player": str(rng.choice(["reink", "gesture", "limb"], p=[0.4, 0.4, 0.2])),
                     "habit": 4.0})
    rev = str(rng.choice(["cover", "tint", "band", "paste"], p=[0.35, 0.2, 0.25, 0.2]))
    sig = plan["disorder"]
    for a in acts:
        a["key"] = a["habit"] + float(rng.normal(0, sig))
    acts.sort(key=lambda a: a["key"])
    # the reversal comes late: after at least 60 % of what is drawn; then the crossing
    cut_at = int(math.ceil(0.6 * len(acts))) + int(rng.integers(0, max(len(acts) - int(math.ceil(0.6 * len(acts))), 0) + 1))
    cut_at = min(cut_at, len(acts))
    acts.insert(cut_at, {"act": "reversal", "player": rev, "habit": 5.0})
    acts.insert(cut_at + 1, {"act": "cross", "player": "hand", "habit": 6.0})
    seen_made = False
    for a in acts:
        a.pop("key", None)
        if a["act"] == "found" and seen_made:
            a["pasted_over"] = bool(rng.random() < 0.75)      # found arriving late: pasted over the hands
        seen_made |= a["act"] in ("hand", "traverse", "counter")
    plan["acts"] = acts
    return plan


# ---------------------------------------------------------------------------
# players
# ---------------------------------------------------------------------------

class Composer:
    def __init__(self, ctx, part_index, plan):
        self.ctx = ctx
        self.part_index = part_index
        self.plan = plan
        self.W, self.H = ctx.frame
        self.S = min(self.W, self.H)
        x0, y0, w, h = ctx.box
        self.bounds = (x0, y0, x0 + w, y0 + h)
        self.score = Score(self.W, self.H)
        self.k = 0
        self.log: list[dict] = []
        self.made: list[dict] = []           # made lines (calls are their ends)
        self.blank = None
        if plan["blank"]["poly"]:
            from shapely.geometry import Polygon  # noqa: PLC0415
            from shapely.geometry import box as sbox  # noqa: PLC0415
            self.blank = Polygon(plan["blank"]["poly"]).intersection(sbox(0, 0, self.W, self.H))
        self.covers: list[np.ndarray] = []

    # -- running a kit voice as a player
    def play(self, vspec, box, modulators=()):
        self.k += 1
        lib = self.ctx.run.library
        spec = {"voice": _module_spec("voice", vspec, f"cproc player {self.k}", lib),
                "modulators": [_module_spec("modulator", m, f"cproc player {self.k}", lib) for m in modulators]}
        p = Part(100 + self.k, spec, {"id": "wire", "pen": 0.4}, self.ctx.frame, self.ctx.sheet_seed, self.ctx.run,
                 tuple(float(v) for v in box))
        return p.run(tuple(float(v) for v in box))

    def rng(self, *tags):
        return self.ctx.rng("act", *tags)

    # -- where things go
    def blank_share(self, poly):
        if self.blank is None or self.blank.is_empty:
            return 0.0
        from shapely.geometry import Polygon  # noqa: PLC0415
        P_ = Polygon(poly)
        return float(P_.intersection(self.blank).area / max(P_.area, 1e-9))

    def rect_near(self, rng, core, w, h, *, spread=0.6, ang_sd=10.0, avoid=0.12, ang=None):
        cxy = np.array(core["xy"], float)
        best = None
        for t in range(80):
            c = cxy + rng.normal(0, spread * core["r"], 2)
            a = float(rng.normal(0, ang_sd)) if ang is None else float(ang)
            r = fit_rect((float(c[0]), float(c[1]), w, h, a), self.bounds)
            sh = self.blank_share(rect_polygon(*r))
            if sh <= avoid:
                return r
            if best is None or sh < best[0]:
                best = (sh, r)
            if t % 20 == 19:
                w, h = w * 0.85, h * 0.85
        return best[1]

    def core(self, rng, weight_main=0.8):
        cs = self.plan["cores"]
        if len(cs) == 1 or rng.random() < weight_main:
            return cs[0]
        return cs[1]

    def placed(self, vspec, rect, modulators=()):
        """A voice fitted into a (rotated) rect: generated axis-aligned, turned about its centre."""
        cx, cy, w, h, ang = rect
        ms = self.play(vspec, (cx - w / 2, cy - h / 2, w, h), modulators)
        c = np.array([cx, cy])
        out = []
        for m in ms:
            q = rotate(m.points, c, ang) if ang else np.asarray(m.points, float)
            out.append(m.evolve(points=q) if len(q) == len(m.points) else Mark(q, {}, dict(m.meta)))
        return out

    # -- grounds a made line can meet
    def grounds_for_catch(self, hand_id=None):
        grounds, grammars = {}, {}
        riv = [l for l in self.score.lines(roles=("found",), regimes=RIVERISH) if arclen(l)[-1] > 20]
        if riv:
            try:
                grammars["river"] = river_grammar(riv, axis_mm=10.0, omega_max=120.0)
                grounds["river"] = Ground(riv, STEP, tag=1)
            except ValueError:
                pass
        ch = [l for l in self.score.lines(roles=("found", "structure"), regimes=("chart",)) if arclen(l)[-1] > 30]
        if ch:
            try:
                grammars["plate"] = chart_grammar(ch)
                grounds["plate"] = Ground(ch, STEP, tag=2)
            except (ValueError, IndexError):
                pass
        sp = [it for it in self.score.items if it["role"] == "structure" and it["regime"] == "specimen"]
        if sp:
            h = SPECIMEN_HAND[sp[0]["player"].split(":")[-1]] if ":" in sp[0]["player"] else "fly_open"
            grounds["spec"] = Ground([it["mark"].points for it in sp], STEP, tag=3)
            grammars["spec"] = {"gen": hand_gen(self.ctx.use("hand", h), 40.0, step=0.2, pull=0.25, axis_mm=8.0,
                                                amp_max=5.0), "code": HAND_CODE, "ride_code": HAND_RIDE, "hand": h}
        for d in self.made[-2:]:
            if d.get("hand") and d["hand"] != hand_id:
                key = f"line{d['n']}"
                grounds[key] = Ground([d["pts"]], STEP, tag=4)
                grammars[key] = {"gen": hand_gen(self.ctx.use("hand", d["hand"]), d["R"] * 0.3, step=0.2, pull=0.2,
                                                 axis_mm=10.0, amp_max=7.0),
                                 "code": HAND_CODE, "ride_code": HAND_RIDE, "hand": d["hand"]}
        return grounds, grammars

    # ------------------------------------------------------------------ acts
    def act_found(self, a, i):
        rng = self.rng("found", i)
        kind = a["player"]
        d = self.plan["density"]
        big = rng.random() < (0.15 + 0.5 * d) or a.get("dominant", False)
        core = self.core(rng, 0.7)
        if kind == "river":
            span = int(np.exp(rng.uniform(math.log(260), math.log(3200))))
            asp = float(rng.uniform(2.5, 5.5)) if span > 900 else float(rng.uniform(1.4, 2.8))
            w = self.S * (rng.uniform(0.7, 1.4) if big else rng.uniform(0.3, 0.6)) * (1.4 if asp > 3 else 1.0)
            h = w / asp
            vs = {"id": "oehlen_found_river", "span_w": span, "start": round(float(rng.uniform(0, 0.9)), 3)}
            a["zoom_span_w"] = span
        elif kind == "braid":
            w = self.S * (rng.uniform(0.6, 1.1) if big else rng.uniform(0.3, 0.55))
            h = w / float(rng.uniform(1.6, 3.2))
            vs = {"id": "river_braid", "threads": int(rng.integers(3, 7)), "length": float(rng.uniform(2.0, 4.5))}
        elif kind == "loops":
            w = self.S * (rng.uniform(0.6, 1.1) if big else rng.uniform(0.3, 0.55))
            h = w / float(rng.uniform(1.2, 2.5))
            vs = {"id": "river_loops", "n": int(rng.integers(3, 12)), "family": str(rng.choice(["oxbow", "neck", "both"])),
                  "host": "river_meander"}
        elif kind == "chart":
            w = self.S * (rng.uniform(0.7, 1.2) if big else rng.uniform(0.35, 0.6))
            h = w / float(rng.uniform(1.0, 2.0))
            vs = {"id": "diagram", "chart": str(rng.choice(["kappa", "kappa", "phase"])), "rows": int(rng.integers(2, 6)),
                  "label_h": 2.0, "hands": [str(rng.choice(self.plan["hands"]))], "length": 6.0}
        else:
            w = self.S * (rng.uniform(0.5, 1.0) if big else rng.uniform(0.3, 0.5))
            h = w / float(rng.uniform(0.9, 1.8))
            vs = {"id": "trail_sheet", "hand": str(rng.choice(["trail_miner", "trail_borer", "trail_grazer",
                                                               "trail_beetle"]))}
        ang = float(rng.choice([0.0, rng.normal(0, 8), rng.normal(90, 6), rng.uniform(-35, 35)], p=[0.2, 0.45, 0.15, 0.2]))
        if kind == "chart":
            ang = float(np.clip(ang if abs(ang) < 40 else rng.normal(0, 6), -15, 15))   # a turned chart's spikes read as hatching
        rect = self.rect_near(rng, core, w, h, spread=0.5 if not big else 0.3, ang=ang,
                              avoid=0.35 if big else 0.1)
        crop = float(rng.uniform(0.9, 1.5)) if not a.get("dominant") else float(rng.uniform(1.2, 2.0))
        if a.get("dominant"):
            w, h = rect[2], rect[3]
            k = min(self.W * rng.uniform(0.75, 1.0) / max(w, 1e-6), self.H * rng.uniform(0.7, 1.0) / max(h, 1e-6))
            rect = fit_rect((rect[0], rect[1], w * max(k, 1.0), h * max(k, 1.0), rect[4]), self.bounds)
        cx, cy, w, h, ang = rect
        inner = (cx, cy, w * crop, h * crop, 0.0)
        ms = self.placed(vs, inner)
        rp = rect_polygon(cx, cy, w, h, ang)
        if a.get("pasted_over"):
            removed = self.score.cut([rp], ["cut"], self.plan["tint_ink"])
            a["cut_mm"] = round(removed, 1)
        n = 0
        for m in ms:
            q = rotate(m.points, np.array([cx, cy]), ang)
            for piece in clip_rect([q], rp, 3.0):
                ext = float(np.linalg.norm(piece.max(axis=0) - piece.min(axis=0)))
                self.score.add(piece, role="found", ink=self.plan["found_ink"], pen=0.5 if a.get("dominant") else 0.28,
                               act=i, player=kind,
                               regime="text" if (kind == "chart" and ext < 5) else kind)
                n += 1
        a["rect"] = [round(v, 1) for v in rect]
        a["lines"] = n

    def act_structure(self, a, i):
        rng = self.rng("structure", i)
        core = self.core(rng, 0.6)
        lad = self.plan["ladder"]
        if a["player"] == "specimens":
            dom = a.get("dominant", False)
            keys = list(rng.choice(sorted(SPECIMENS), size=int(rng.integers(3, 7) if dom else rng.integers(2, 5)),
                                   replace=True))
            bw = self.W * (float(rng.uniform(0.75, 1.0)) if dom else float(rng.uniform(0.3, 0.85)))
            row_h = float(np.clip(0.155 * bw * rng.uniform(0.6, 1.0), 5.0, 40.0))
            gfrac = float(rng.uniform(0.15, 0.8))
            bh = len(keys) * row_h * (1 + gfrac) - row_h * gfrac
            ang = float(rng.choice([rng.normal(0, 3), rng.normal(90, 3), rng.uniform(-20, 20)], p=[0.6, 0.2, 0.2]))
            rect = self.rect_near(rng, core, bw, bh, spread=0.7, ang=ang, avoid=0.15)
            cx, cy, bw, bh, ang = rect
            row_h = bh / (len(keys) * (1 + gfrac) - gfrac)
            gap = row_h * gfrac
            ink = str(rng.choice([self.plan["found_ink"], "black"]))
            for r, key in enumerate(keys):
                y = cy - bh / 2 + r * (row_h + gap)
                ms = self.play({"id": "morph_handover", "hands": ["meander69", "fly_open"], "order": "bend,turn,corner",
                                "rows": 1, "R_mm": float(np.clip(85.0 * bw / 297.0, 10.0, 200.0)),
                                "band": float(np.clip(14.0 * bw / 297.0, 1.0, 40.0)), "ease": 1.3, "run": 4.0,
                                "windows": SPECIMENS[key]},
                               (cx - bw / 2, y, bw, row_h))
                for m in ms:
                    q = rotate(m.points, np.array([cx, cy]), ang)
                    self.score.add(q, role="structure", ink=ink, pen=0.25, act=i, player=f"specimen:{key}",
                                   regime="specimen")
            a["rows"] = [str(k) for k in keys]
            a["rect"] = [round(v, 1) for v in rect]
        else:
            w = self.S * float(rng.uniform(0.4, 0.8))
            rect = self.rect_near(rng, core, w, w / float(rng.uniform(1.2, 2.2)), spread=0.6, avoid=0.15)
            vs = {"id": "diagram", "chart": str(rng.choice(["kappa", "route"])), "rows": int(rng.integers(3, 7)),
                  "label_h": 2.0, "hands": [str(rng.choice(self.plan["hands"]))], "length": 6.0}
            for m in self.placed(vs, rect):
                ext = float(np.linalg.norm(m.points.max(axis=0) - m.points.min(axis=0)))
                self.score.add(m.points, role="structure", ink="black", pen=0.25, act=i, player="chart",
                               regime="text" if ext < 5 else "chart")
            a["rect"] = [round(v, 1) for v in rect]

    def _hand_rect(self, rng, core, scale=1.0):
        mid = self.plan["ladder"]["mid_mm"] * scale * (1.35 if self.plan.get("dominant") == "hand" else 1.0)
        asp = float(np.exp(rng.normal(0, 0.45)))
        w, h = mid * math.sqrt(asp) * float(rng.uniform(0.7, 1.5)), mid / math.sqrt(asp) * float(rng.uniform(0.7, 1.5))
        if self.plan["density_label"] == "all-over":
            c = {"xy": [self.W / 2, self.H / 2], "r": 0.35 * max(self.W, self.H)}
            return self.rect_near(rng, c, w, h, spread=0.9, ang_sd=25.0, avoid=0.2)
        return self.rect_near(rng, core, w, h, spread=0.75, ang_sd=25.0, avoid=0.15)

    def _pen(self, rng):
        if self.plan.get("dominant") == "hand":
            return float(rng.choice([0.35, 0.5, 0.7, 1.0], p=[0.25, 0.3, 0.3, 0.15]))
        return float(rng.choice([0.25, 0.35, 0.45, 0.6, 0.8], p=[0.2, 0.3, 0.25, 0.15, 0.1]))

    def _neg(self, M, rng, grow, capture=4.0):
        lines = self.score.lines(roles=("found", "structure", "made"))
        lines = [l for l in lines if arclen(l)[-1] > 8]
        if not lines:
            return resample(M, STEP), np.zeros(len(resample(M, STEP))), []
        G = Ground(lines, STEP, tag=1)
        return negotiate(M, [G], rng, step=STEP, capture=capture, align=0.7, ride=float(rng.uniform(12, 40)),
                         ride_sd=0.6, min_ride=5.0, listen=float(rng.uniform(25, 70)),
                         ignore=float(rng.uniform(30, 110)), return_mm=30.0, ramp=2.5, grow=grow,
                         grow_reach=float(rng.uniform(20, 60)), max_rides=int(rng.integers(2, 8)), max_offset=20.0,
                         ride_gap=float(rng.choice([0.0, 0.8])), bounds=self.bounds)

    def _keep_made(self, pts, hand, R, i, player, rng, pen=None, ink=None, record=True):
        pen = self._pen(rng) if pen is None else pen
        ink = ink or (self.plan["second_ink"] if rng.random() < 0.12 else self.plan["made_ink"])
        runs = inside_runs(pts, self.bounds)
        for r in runs:
            self.score.add(r, role="made", ink=ink, pen=pen, act=i, player=player, regime="made", hand=hand)
        if runs and record:
            self.made.append({"pts": resample(runs[-1], STEP), "hand": hand, "R": R, "n": len(self.made)})
        return pen

    def act_hand(self, a, i):
        rng = self.rng("hand", i)
        pl = a["player"]
        core = self.core(rng, 0.85)
        hand = str(rng.choice(self.plan["hands"]))
        if pl == "soup":
            rect = self._hand_rect(rng, core, scale=float(rng.uniform(1.2, 2.0)) * (1.6 if a.get("dominant") else 1.0))
            cx, cy, w, h, _ = rect
            w, h = max(w, h * 1.3), max(h, 60.0)
            rect = fit_rect((cx, cy, w, h, float(rng.normal(0, 6))), self.bounds)
            for m in self.placed({"id": "mutual", "T": int(rng.integers(90, 160)), "bold_hand": "dance_thrusting",
                                  "patience": 8, "appetite_cost": 0.05, "appetite_gain": 0.004,
                                  "refuse_below": 0.0, "wake_max": 20, "lift_max": 2, "burst_ticks": 3,
                                  "refractory": 0, "turn_gap": 12.0, "turn_deg": 55.0, "bold_len": 0.35,
                                  "wire_awake": 14.0},
                                 rect):
                self.score.add(m.points, role="made", ink=m.meta.get("ink", "black"), pen=m.meta.get("pen", 0.4),
                               act=i, player="soup", regime="made" if m.meta.get("of_role") != "river" else "river")
            a["rect"] = [round(v, 1) for v in rect]
            a["hand"] = "mutual"
            return
        if pl == "limb":
            rect = self._hand_rect(rng, core, scale=float(rng.uniform(0.6, 1.3)))
            ms = self.placed({"id": "revisit_glyph", "trail": str(rng.choice(["particles", "levitation"])),
                              "host": str(rng.choice(["rfoot", "lfoot", "rhand", "head"])), "with_": "head",
                              "seconds": float(rng.uniform(20, 60)), "t0": float(rng.uniform(0, 20)),
                              "max_glyphs": int(rng.integers(3, 8)), "scale": 0.35, "spread": 1.0,
                              "nib_mm": float(rng.uniform(0.6, 1.4)), "mass_mm": 1.6},
                             rect)
            inks = ["black", str(rng.choice([self.plan["second_ink"], "red", "black"]))]
            for j, m in enumerate(ms):
                self.score.add(m, role="made", ink=inks[j % 2], pen=0.35, act=i, player="limb", regime="made",
                               nib="c+e")
            a["rect"] = [round(v, 1) for v in rect]
            return
        if pl == "free":
            pts = free_hand_3966()
            s = float(rng.uniform(0.3, 1.0)) * min(1.0, (self.bounds[2] - self.bounds[0]) / 290)
            ang = float(rng.choice([rng.normal(0, 10), rng.uniform(-90, 90)]))
            q = (pts - pts.mean(axis=0)) * s
            q = rotate(q, np.zeros(2), ang)
            ext = q.max(axis=0) - q.min(axis=0)
            rect = self.rect_near(rng, core, float(ext[0]), float(ext[1]), spread=0.6, ang=0.0, avoid=0.25)
            q = q - (q.max(axis=0) + q.min(axis=0)) / 2 + [rect[0], rect[1]]
            k = min(1.0, (self.bounds[2] - self.bounds[0]) / max(ext[0], 1e-6), (self.bounds[3] - self.bounds[1]) / max(ext[1], 1e-6))
            if k < 1:
                q = (q - q.mean(axis=0)) * k * 0.98 + q.mean(axis=0)
            q = q + np.clip(np.array(self.bounds[:2]) - q.min(axis=0), 0, None) - np.clip(q.max(axis=0) - np.array(self.bounds[2:]), 0, None)
            self._keep_made(q, "river_belt", 120.0, i, "free", rng)
            a["scale"], a["angle"] = round(s, 2), round(ang, 1)
            return
        if pl == "passage":
            rect = self._hand_rect(rng, core, scale=float(rng.uniform(1.0, 1.6)))
            cx, cy, w, h, ang = rect
            hs = list(dict.fromkeys(["meander69", "fly_open", "river_belt", "hokusai", "dance_staccato",
                                     "mime_roadrunner"]))
            ms = self.placed({"id": "passage", "hands": hs, "opening": "none", "rows": int(rng.integers(1, 4)),
                              "erratic": float(rng.uniform(0.2, 0.9)), "many": float(rng.uniform(0.1, 0.6)),
                              "max_mm": float(np.clip(w * h / 12, 400, 2500))},
                             rect)
            for m in ms:
                self._keep_made(m.points, "fly_open", w, i, "passage", rng, pen=float(rng.choice([0.25, 0.35, 0.45])))
            a["rect"] = [round(v, 1) for v in rect]
            return
        # negotiate / catch / answer: one hand's line, then it meets what is there
        # the hand's rung on the ladder: a small knot, a middle hand, or a large fast sweep (spread dial)
        spread = self.plan["ladder"]["spread"]
        p_s, p_l = 0.12 + 0.28 * spread, 0.1 + 0.25 * spread
        rung = str(rng.choice(["small", "mid", "large"], p=[p_s, 1 - p_s - p_l, p_l]))
        fast = rung == "large" or (rung == "mid" and rng.random() < 0.3)
        scale = {"small": float(rng.uniform(0.18, 0.4)), "mid": float(rng.uniform(0.7, 1.3)),
                 "large": float(rng.uniform(1.8, 2.8))}[rung]
        rect = self._hand_rect(rng, core, scale=scale)
        length = float(rng.uniform(0.8, 1.9)) if fast else float(rng.uniform(3.5, 8.0))
        a["speed"] = "fast" if fast else "slow"
        a["rung"] = rung
        ms = self.placed({"id": "hand", "hand": hand, "length": length}, rect)
        if not ms:
            return
        M = resample(ms[0].points, STEP)
        R = float(arclen(M)[-1]) / max(length, 0.2)
        a["hand"] = hand
        if pl == "answer" and self.made:
            call = self.made[-1]
            e = call["pts"][-1]
            te = tangents(call["pts"], 4)[-1]
            if np.linalg.norm(M[-1] - e) < np.linalg.norm(M[0] - e):
                M = M[::-1].copy()
            t0 = tangents(M, 4)[0]
            rot = math.degrees(math.atan2(te[1], te[0]) - math.atan2(t0[1], t0[0]))
            Q = rotate(M - M[0], np.zeros(2), rot)
            for sc in (1.0, 0.8, 0.6, 0.45, 0.3):
                Qs = Q * sc + e + te * 1.5
                if np.all(Qs.min(axis=0) >= np.array(self.bounds[:2])) and np.all(Qs.max(axis=0) <= np.array(self.bounds[2:])):
                    M = np.vstack([e, Qs])
                    a["answers"] = call["n"]
                    a["answer_scale"] = sc
                    break
            pts, _t, lg = self._neg(M, rng, grow=False)
        elif pl == "catch":
            grounds, grammars = self.grounds_for_catch(hand)
            if grounds:
                full = {k: float(rng.uniform(25, 60)) for k in grounds}
                decay = {k: float(rng.uniform(40, 100)) for k in grounds}
                pitch = grammars.get("plate", {}).get("pitch_mm", 6.3) * 1.5
                pts, codes, lg = contagion_walk(
                    M, grounds, grammars, rng, step=0.3, capture=5.0, align=0.5, listen=float(rng.uniform(40, 90)),
                    ignore=float(rng.uniform(30, 80)), ride=16.0, ride_sd=0.45, min_ride=6.0, ride_gap=0.9,
                    return_mm=30.0, ramp=2.0, max_offset=18.0, catches=int(rng.integers(2, 5)), full=full,
                    decay=decay, tick_linger=1.5, own_mm=6.0, rule_tol=3.5, snap=10.0, tick_pitch=pitch,
                    immune_mm=50.0, omega_max=120.0, rule_shared=9.0, regimes=tuple(grounds), carry=True)
                a["caught"] = sorted({inf["regime"] for inf in lg.get("infections", [])})
                if "plate" in grammars:
                    from .arrangers_found_play import chart_needles  # noqa: PLC0415
                    pts = chart_needles(pts, codes, grammars["plate"])
            else:
                pts, _t, lg = self._neg(M, rng, grow=True)
        else:
            pts, _t, lg = self._neg(M, rng, grow=bool(rng.random() < 0.6))
            a["rides"] = len(lg)
            if self.plan["weight_follows_ground"] and len(_t) == len(pts) and np.any(_t > 0):
                # rules' R1, as a per-sheet dial: heavy while riding the ground, a hairline in the blank
                pen0 = self._pen(rng)
                flags = _t > 0
                cuts = np.r_[0, np.flatnonzero(np.diff(flags.astype(int))) + 1, len(pts)]
                for a_, b_ in zip(cuts[:-1], cuts[1:]):
                    seg = pts[max(a_ - 1, 0):b_]
                    self._keep_made(seg, hand, R, i, pl, rng, pen=(max(0.8, 2 * pen0) if flags[a_] else 0.25),
                                    ink=self.plan["made_ink"], record=False)
                self.made.append({"pts": resample(pts, STEP), "hand": hand, "R": R, "n": len(self.made)})
                a["rect"] = [round(v, 1) for v in rect]
                a["weight"] = "follows ground"
                return
        pen = {"small": float(rng.choice([0.25, 0.35])), "large": float(rng.choice([0.5, 0.7, 1.0]))}.get(rung)
        self._keep_made(pts, hand, R, i, pl, rng, pen=pen)
        a["rect"] = [round(v, 1) for v in rect]

    def act_counter(self, a, i):
        """The counterweight: a smaller, second density elsewhere (a fragment + a line or two)."""
        rng = self.rng("counter", i)
        c2 = self.plan["cores"][1]
        n = int(rng.integers(1, 4))
        a["lines"] = n
        for j in range(n):
            hand = str(rng.choice(self.plan["hands"]))
            rect = self.rect_near(rng, c2, c2["r"] * float(rng.uniform(1.0, 2.2)), c2["r"] * float(rng.uniform(0.8, 1.8)),
                                  spread=0.4, ang_sd=30.0, avoid=0.1)
            length = float(rng.uniform(1.0, 4.0))
            ms = self.placed({"id": "hand", "hand": hand, "length": length}, rect)
            if ms:
                pts, _t, _l = self._neg(ms[0].points, rng, grow=False, capture=3.0)
                self._keep_made(pts, hand, float(arclen(ms[0].points)[-1]) / length, i, "counter", rng,
                                pen=float(rng.choice([0.25, 0.35, 0.5])))

    def _spine(self, rng, through_blank=True):
        """A spine for the long traverse: from one edge region, through the core, through the blank, out."""
        W, H = self.W, self.H
        c = np.array(self.plan["cores"][0]["xy"], float)
        if self.blank is not None and not self.blank.is_empty and through_blank:
            b = np.array(self.blank.representative_point().coords[0])
        else:
            b = np.array([W, H]) - c
        u = b - c
        if np.linalg.norm(u) < 1e-6:
            u = np.array([1.0, 0.0])
        u = u / np.linalg.norm(u)
        # endpoints: behind the core and beyond the blank, on the sheet's inset edge
        x0, y0, x1, y1 = self.bounds

        def to_edge(p, v):
            ts = []
            for ax, lo, hi in ((0, x0, x1), (1, y0, y1)):
                if abs(v[ax]) > 1e-9:
                    ts.append(((hi if v[ax] > 0 else lo) - p[ax]) / v[ax])
            return p + v * max(min(ts), 0.0)
        jit = rng.normal(0, 0.25, 2)
        P0 = to_edge(c, -u + jit)
        P3 = to_edge(b, u + rng.normal(0, 0.25, 2))
        P1 = c + rng.normal(0, 0.15 * self.S, 2)
        P2 = b + rng.normal(0, 0.15 * self.S, 2)
        sp = bezier(P0, P1, P2, P3)
        sp = np.clip(sp, [x0, y0], [x1, y1])
        return sp

    def act_traverse(self, a, i):
        rng = self.rng("traverse", i)
        pl = a["player"]
        lad = self.plan["ladder"]
        pen = float(rng.choice([0.3, 0.45, 0.7, 1.0], p=[0.2, 0.3, 0.3, 0.2]))
        ink = self.plan["made_ink"] if rng.random() < 0.75 else self.plan["second_ink"]
        if pl == "arc":
            # one hand at the scale of the sheet: long arcs that cross everything
            hand = str(rng.choice(HEAVY_HANDS + tuple(self.plan["hands"])))
            x0, y0, x1, y1 = self.bounds
            ms = self.play({"id": "hand", "hand": hand, "length": float(rng.uniform(0.8, 2.2))},
                           (x0, y0, x1 - x0, y1 - y0))
            for m in ms:
                self.score.add(m.points, role="traverse", ink=ink, pen=pen, act=i, player="arc", regime="made",
                               hand=hand)
            a["hand"] = hand
            return
        sp = self._spine(rng)
        Ls = float(arclen(resample(sp, 0.5))[-1])
        h = float(np.clip(lad["small_mm"] * rng.uniform(1.5, 4.0), 6.0, 0.22 * self.S + 6))
        if a.get("dominant"):
            h = float(self.S * rng.uniform(0.12, 0.3))
            pen = float(rng.uniform(0.7, 1.2))
        box = (0.0, 0.0, Ls, h)
        if pl == "belt":
            g0, g1 = sorted([float(rng.uniform(0.6, 1.4)), float(rng.uniform(1.8, 3.0))])
            if rng.random() < 0.5:
                g0, g1 = g1, g0
            vs = {"id": "belt", "hand": "river_belt", "length": float(rng.uniform(6.0, 11.0)), "gain": g0,
                  "gain_end": g1, "pull": float(rng.uniform(0.15, 0.35))}
            a["gain"] = [round(g0, 2), round(g1, 2)]
        elif pl == "passage":
            vs = {"id": "passage", "hands": ["meander69", "fly_open", "river_belt", "hokusai", "dance_staccato",
                                             "mime_roadrunner"], "opening": "none", "rows": 1,
                  "erratic": float(rng.uniform(0.3, 0.9)), "max_mm": float(np.clip(Ls * 3, 300, 2500)),
                  "band": float(max(h / 2, 4.0))}
        elif pl == "waves":
            vs = {"id": "morph_handover", "hands": ["meander69", "fly_open"], "order": "bend,turn,corner", "rows": 1,
                  "R_mm": float(np.clip(85.0 * Ls / 297.0, 10.0, 200.0)), "band": float(np.clip(14.0 * Ls / 297.0, 1.0, 40.0)), "ease": 1.3, "run": 4.0, "windows": SPECIMENS["waves"],
                  "max_mm": float(np.clip(Ls * 2.5, 300, 2000))}
        else:
            span = int(np.exp(rng.uniform(math.log(400), math.log(3000))))
            vs = {"id": "oehlen_found_river", "span_w": span, "start": round(float(rng.uniform(0, 0.9)), 3)}
            a["zoom_span_w"] = span
        ms = self.play(vs, box)
        lines = lay_along([m.points for m in ms], sp, 0.0, h / 2)
        for l in lines:
            self.score.add(l, role="traverse", ink=ink if pl != "river" else self.plan["found_ink"],
                           pen=pen if pl != "river" else 0.3, act=i, player=pl, regime="river" if pl == "river" else "made")
        a["strip_h"] = round(h, 1)
        a["spine_mm"] = round(Ls, 1)

    def act_trail_off(self, a, i):
        """A line runs out of the core into the blank and stops in the air."""
        rng = self.rng("trail", i)
        c = np.array(self.plan["cores"][0]["xy"], float)
        b = np.array(self.blank.representative_point().coords[0])
        u = b - c
        L = float(np.linalg.norm(u)) * float(rng.uniform(0.8, 1.3))
        ang = math.degrees(math.atan2(u[1], u[0])) + float(rng.normal(0, 12))
        mid = c + (b - c) * 0.55
        h = float(rng.uniform(6, 22))
        rect = fit_rect((float(mid[0]), float(mid[1]), L, h, ang), self.bounds)
        hand = str(rng.choice(self.plan["hands"]))
        ms = self.placed({"id": "hand", "hand": hand, "length": float(rng.uniform(2.5, 7.0))}, rect)
        for m in ms:
            self.score.add(m.points, role="made", ink=self.plan["made_ink"], pen=0.25, act=i, player="trail_off",
                           regime="made", hand=hand)
        a["rect"] = [round(v, 1) for v in rect]

    def act_heavy(self, a, i):
        rng = self.rng("heavy", i)
        c = self.plan["cores"][0]
        cxy, rc = np.array(c["xy"], float), float(c["r"])
        pen = float(rng.uniform(1.3, 2.4))
        if a["player"] == "reink":
            cands = [it for it in self.score.items if it["role"] in ("made", "traverse") and not it.get("nib")]
            if cands:
                best = None
                for it in cands:
                    p = it["mark"].points
                    d = np.abs(np.linalg.norm(p - cxy, axis=1) - rc * float(rng.uniform(0.5, 1.0)))
                    j = int(np.argmin(d))
                    if best is None or d[j] < best[0]:
                        best = (float(d[j]), it, j)
                _, it, j = best
                p = it["mark"].points
                L = float(rng.uniform(30, 110))
                k = int(L / STEP / 2)
                seg = p[max(j - k, 0):j + k]
                if len(seg) >= 3:
                    self.score.add(seg, role="heavy", ink="black", pen=pen, act=i, player="reink", regime="heavy")
                    a["mm"] = round(float(arclen(seg)[-1]), 1)
                    a["at"] = np.round(p[j], 1).tolist()
                    a["pen"] = round(pen, 2)
                    return
            a["player"] = "gesture"
        ang = float(rng.uniform(0, 2 * math.pi))
        at = cxy + rc * float(rng.uniform(0.6, 1.1)) * np.array([math.cos(ang), math.sin(ang)])
        sz = float(rng.uniform(22, 60)) * (self.S / 200) ** 0.5
        rect = fit_rect((float(at[0]), float(at[1]), sz * float(rng.uniform(0.7, 1.6)), sz, float(rng.uniform(-60, 60))),
                        self.bounds)
        at = np.array(rect[:2])                         # where it landed, once pulled onto the paper
        if a["player"] == "limb":
            ms = self.placed({"id": "revisit_glyph", "trail": "particles", "host": str(rng.choice(["rfoot", "rhand"])),
                              "with_": "none", "seconds": float(rng.uniform(4, 12)), "t0": float(rng.uniform(0, 40)),
                              "max_glyphs": 3, "nib_mm": float(rng.uniform(1.6, 3.0)), "mass_mm": 2.4}, rect)
            for m in ms:
                self.score.add(m, role="heavy", ink="black", pen=0.45, act=i, player="limb", regime="heavy", nib="c+e")
        else:
            hand = str(rng.choice(HEAVY_HANDS))
            ms = self.placed({"id": "hand", "hand": hand, "length": float(rng.uniform(0.5, 1.3))}, rect)
            for m in ms:
                self.score.add(m.points, role="heavy", ink="black", pen=pen, act=i, player="gesture", regime="heavy",
                               hand=hand)
            a["hand"] = hand
        a["at"] = np.round(at, 1).tolist()
        a["pen"] = round(pen, 2)

    def act_reversal(self, a, i):
        rng = self.rng("reversal", i)
        S = self.S
        c = self.plan["cores"][0]
        cxy, rc = np.array(c["xy"], float), float(c["r"])
        where = str(rng.choice(["core", "core_edge", "blank_edge", "anywhere"], p=[0.3, 0.35, 0.2, 0.15]))
        if where == "core":
            at = cxy + rng.normal(0, 0.2 * rc, 2)
        elif where == "core_edge":
            t = float(rng.uniform(0, 2 * math.pi))
            at = cxy + rc * float(rng.uniform(0.6, 1.0)) * np.array([math.cos(t), math.sin(t)])
        elif where == "blank_edge" and self.blank is not None and not self.blank.is_empty:
            ring = self.blank.exterior
            at = np.array(ring.interpolate(float(rng.uniform(0, ring.length))).coords[0])
        else:
            at = rng.uniform(0.2, 0.8, 2) * [self.W, self.H]
        at = np.clip(at, [0.12 * self.W, 0.12 * self.H], [0.88 * self.W, 0.88 * self.H])
        kind = a["player"]
        size = S * float(np.exp(rng.uniform(math.log(0.2), math.log(0.65))))
        if kind == "band":
            w, h = max(self.W, self.H) * float(rng.uniform(0.5, 1.0)), float(rng.uniform(8, 30))
            shape, mode = "torn", "cut"
        elif kind == "tint":
            w, h = size, size / float(rng.uniform(0.6, 1.6))
            shape, mode = "sheet", "tint"
        else:
            w, h = size, size / float(rng.uniform(0.5, 1.8))
            shape, mode = str(rng.choice(["cut", "torn"])), "cut"
        poly = cover_polygon(rng, at, w, h, shape, 40.0 if kind == "band" else 14.0)
        removed = self.score.cut([poly], [mode], self.plan["tint_ink"])
        self.covers.append(poly)
        if kind != "band" and rng.random() < 0.3:
            # its edge drawn, hairline, in the found pen: the patch shows as a patch
            for r in inside_runs(poly, self.bounds):
                self.score.add(r, role="edge", ink=self.plan["found_ink"], pen=0.2, act=i, player="cover_edge",
                               regime="edge")
            a["edge"] = "drawn"
        a.update(where=where, mode=mode, size=[round(w, 1), round(h, 1)], at=np.round(at, 1).tolist(),
                 cut_mm=round(removed, 1), share=round(_poly_area(poly) / (self.W * self.H), 3))
        if kind == "paste":
            # found matter pasted late, inside the patch
            vk = str(rng.choice(["river", "chart", "braid", "trail"]))
            sub = {"act": "found", "player": vk}
            cx, cy = poly[:-1].mean(axis=0)
            vs = {"river": {"id": "oehlen_found_river", "span_w": int(rng.integers(300, 2500)),
                            "start": round(float(rng.uniform(0, 0.9)), 3)},
                  "chart": {"id": "diagram", "chart": "kappa", "rows": 3, "label_h": 2.0,
                            "hands": [str(rng.choice(self.plan["hands"]))], "length": 6.0},
                  "braid": {"id": "river_braid"},
                  "trail": {"id": "trail_sheet", "hand": "trail_miner"}}[vk]
            ms = self.play(vs, (cx - w * 0.65, cy - h * 0.65, w * 1.3, h * 1.3))
            from shapely.geometry import LineString, Polygon  # noqa: PLC0415
            Pp = Polygon(poly)
            for m in ms:
                g = LineString(m.points).intersection(Pp)
                for x in ([g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))):
                    if x.geom_type == "LineString" and x.length > 3:
                        self.score.add(np.asarray(x.coords), role="found", ink=self.plan["found_ink"], pen=0.28, act=i,
                                       player=f"paste:{vk}", regime=vk if vk != "chart" else "chart")
            a["pasted"] = sub["player"]

    def act_cross(self, a, i):
        rng = self.rng("cross", i)
        if not self.covers:
            return
        poly = self.covers[-1]
        from shapely.geometry import LineString, Polygon  # noqa: PLC0415
        Pp = Polygon(poly)
        c = np.array(Pp.centroid.coords[0])
        ext = poly.max(axis=0) - poly.min(axis=0)
        hand = str(rng.choice(self.plan["hands"]))
        for t in range(6):
            w, h = ext * float(rng.uniform(1.4, 2.6)) + 20
            rect = fit_rect((float(c[0]), float(c[1]), float(w), float(h), float(rng.normal(0, 20))), self.bounds)
            ms = self.placed({"id": "hand", "hand": hand, "length": float(rng.uniform(1.5, 4.0))}, rect)
            if ms and LineString(ms[0].points).intersects(Pp):
                break
        if not ms:
            return
        Ge = Ground([resample(poly, STEP)], STEP, tag=2)
        pts, _t, lg = negotiate(ms[0].points, [Ge], rng, step=STEP, capture=6.0, align=0.7, ride=20.0, ride_sd=0.5,
                                min_ride=5.0, listen=40.0, ignore=40.0, return_mm=30.0, ramp=2.5, grow=False,
                                grow_reach=10.0, max_rides=2, max_offset=18.0, ride_gap=0.0, bounds=self.bounds)
        pen = float(rng.choice([0.3, 0.5, 0.7, 0.9]))
        for r in inside_runs(pts, self.bounds):
            self.score.add(r, role="late", ink=self.plan["made_ink"], pen=pen, act=i, player="cross", regime="made",
                           hand=hand)
        a.update(hand=hand, edge_rides=len(lg), pen=pen,
                 crosses=bool(LineString(pts).intersects(Pp)))

    def run(self):
        for i, a in enumerate(self.plan["acts"]):
            fn = getattr(self, "act_" + a["act"])
            if a["act"] == "trail_off" and (self.blank is None or self.blank.is_empty):
                continue
            n0 = len(self.score.items)
            fn(a, i)
            a["items"] = len(self.score.items) - n0
        return self.emit()

    def emit(self):
        out = []
        for it in self.score.items:
            m = it["mark"]
            meta = {"part": self.part_index, "of_role": it["role"], "ink": it["ink"], "pen": it["pen"], "act": it["act"],
                    "player": it["player"]}
            if it.get("nib"):
                meta["nib"] = it["nib"]
            out.append(Mark(m.points, dict(m.channels) if it.get("nib") else {}, meta))
        return out


# ---------------------------------------------------------------------------
# arranger + renderer
# ---------------------------------------------------------------------------

@arranger("cproc", params=[
    P("frame_name", "str", "given", "the frame's name as decided by cproc.frame_for (a record; the recipe's frame is used)"),
    P("density", "float", None, "override the density dial (0 = a few lines, 1 = all-over); null = decide",
      min=0.0, max=1.0, optional=True),
], doc="b1 composer as procedure: decides the composition from the seed (cores, blank, density dial, scale ladder, "
        "acts and their order with a late reversal) and plays the kit's techniques into it")
def cproc(ctx, parts, *, frame_name, density):
    W, H = ctx.frame
    plan = decide(ctx.rng("plan"), W, H, density=density, frame_name=frame_name)
    comp = Composer(ctx, parts[0].index, plan)
    out = comp.run()
    if out:
        out[0] = out[0].evolve(meta={"cproc": plan})
    return out


@renderer("cproc_ink", params=[P("pen", "float", 0.4, "pen for marks that carry none, mm", min=0.05, max=3.0)],
          doc="one wire per mark at its meta pen and ink; marks with meta['nib'] inked as a broad nib",
          reach=lambda p: 1.0)
def cproc_ink(ctx, marks, *, pen):
    from .renderers_base import nib  # noqa: PLC0415
    out = []
    for m in marks:
        col = m.meta.get("ink", "black")
        pw = float(m.meta.get("pen", pen))
        if m.meta.get("nib"):
            for ink in nib(ctx, [m], style=m.meta["nib"], pen=pw):
                out.append(Ink(ink.points, ink.closed, ink.filled, ink.pen, {**ink.meta, "colour": col,
                                                                            "role": m.meta.get("of_role")}))
        elif len(m.points) >= 2:
            out.append(Ink(m.points, closed=False, filled=False, pen=pw, meta={"colour": col, "player": m.meta.get("player"),
                                                                              "role": m.meta.get("of_role")}))
    return out


def render(sheet, *, px_per_mm: float = 6.0):
    return _render_colour(sheet, px_per_mm=px_per_mm)


def save(sheet, path, *, px_per_mm: float = 6.0, quality: int = 90):
    from pathlib import Path  # noqa: PLC0415
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = render(sheet, px_per_mm=px_per_mm)
    im.save(path, quality=quality, optimize=True)
    sheet.save_recipe(path.with_suffix(".recipe.json"))
    return path


def table_row(sheet) -> dict:
    """The sheet's decisions, for the write-up's table."""
    plan = sheet.marks[0].meta["cproc"] if sheet.marks else {}
    acts = plan.get("acts", [])
    order = " → ".join(f"{a['act'][:5]}:{a['player']}" + ("*" if a.get("pasted_over") else "") for a in acts)
    heavy = [a for a in acts if a["act"] == "heavy"]
    rev = [a for a in acts if a["act"] == "reversal"]
    c = plan.get("cores", [{}])
    return {"seed": sheet.recipe["seed"], "frame": f"{plan.get('frame_name')} {int(plan['frame'][0])}×{int(plan['frame'][1])}",
            "density": f"{plan.get('density_label')} {plan.get('density')}",
            "core": " + ".join(f"({x['xy'][0]:.0f},{x['xy'][1]:.0f}) r{x['r']:.0f}" for x in c),
            "blank": plan.get("blank", {}).get("kind"),
            "dominant": plan.get("dominant"),
            "crosses": [a.get("crosses") for a in acts if a["act"] == "cross"],
            "order": order,
            "intruder": (f"{heavy[0]['player']} {heavy[0].get('pen', '')}" if heavy else "none"),
            "reversal": (f"{rev[0]['player']} at {rev[0].get('where')} ({rev[0].get('share')} of sheet, cut "
                         f"{rev[0].get('cut_mm')} mm)" if rev else "none")}
