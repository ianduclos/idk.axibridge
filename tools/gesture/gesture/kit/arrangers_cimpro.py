"""Round 14 thread b2, `cimpro` — the composer as improviser.

The round-12 intuition session (results/oehlen_intuit-2026-10-17.md) made into a
procedure that runs every time: the arranger LOOKS at the sheet so far, decides
the next move, plays it, and looks again. A run is a sequence of
perceive → decide → act steps, and the sequence differs per seed and per state.

perceive   the sheet so far rasterised on a coarse grid (`cell` mm): ink per
           cell weighted by pen, blurred twice (local and core scale). Read off:
           coverage, the core (where, how big, what share of the ink), a
           competing second density, the centroid's offset from the middle, the
           largest blank disk, the scales already played (tiny / mid / large),
           the registers present, open ends in the air (calls), covers.
           `settled` is high when the eye can rest: centroid near the middle and
           no competing density. The improviser steers AWAY from it (T7).
decide     a weighted, stochastic choice among the moves the state allows. The
           weights are the sheet's temperament (drawn once per sheet: density
           appetite, a dominant register, how much it intrudes, covers, answers)
           times what the state invites. Never an argmax, never a score that
           is optimised: the same state can lead to different moves.
act        the move, placed from what is there:
             found      paste found matter (a river stem at a chosen zoom, or a
                        seismograph chart) into a rotated rectangle, cut to it
             seed       a core: several hands into one small box, each walking
                        the sheet (contagion: catches the river / the chart /
                        an earlier hand)
             thicken    more lines into the core that is there (density begets density)
             traverse   one long line (belt, gmorph, the 3966 free hand, passage
                        or a hand) across the whole sheet, through the core and
                        out over the blank
             intrude    T3: a heavy, geometric mark (bar, bent bar, two dashes)
                        or a heavy knot at the EDGE of the core, cutting across
                        it from the side of the largest blank
             counterweight  a smaller density elsewhere, at another scale
             cover      a torn cover over part of the core: cuts what is under it
             cross      a line that crosses the cover as if it were not there
             answer     a line that grows out of an earlier line's end in the air
             trail      from the core's edge out into the blank, to an edge or
                        stopping in the air
             ladder     a scale the sheet lacks (tiny periodic matter: a handover
                        specimen band, a thumb-sized river; or a large traverse)
             sign       a limb sign (revisit_glyph), glyphs in the heavy pen
             reserve    decide the blank: dense moves keep out of it, lines may cross
             stop
The log (`marks[0].meta["cimpro"]["log"]`) names every move with the reason read
off the sheet. `upto` stops after n moves (process strips of the same run).

Recipe parts are GUESTS: the improviser may also play any recipe part as a made
line (`guest` move); every mark is attributed to part 0 for rendering. Ink with
`oehlen_found_ink` (marks carry `ink` and `pen` in meta).
"""
from __future__ import annotations

import math
import numpy as np

from . import core
from .arrangers_contagion import contagion_walk, river_grammar
from .arrangers_found_play import HAND_CODE, HAND_RIDE, chart_grammar, chart_needles, hand_gen
from .arrangers_oehlen_found import (FLEXOKI, arclen, clip_rect, cover_polygon, rect_polygon, resample, rotate,
                                     split_by_covers, tangents)
from .core import Ctx, Mark, P, arranger

SEED_MAX = core.SEED_MAX
VERBS = ("found", "seed", "thicken", "traverse", "intrude", "counterweight", "cover", "cross", "answer", "trail",
         "ladder", "sign", "reserve", "guest", "stop")
HANDS = ("dance_thrusting", "dance_staccato", "river_bend", "river_meander", "river_oxbow", "hokusai", "meander69",
         "fly_open", "mime_roadrunner", "mime_mantis", "trail_miner", "trail_slime", "trail_grazer", "ingres")
KNOT_HANDS = ("fly_open", "dance_staccato", "trail_slime", "mime_mantis", "fly_fru")
LINE_PLAYERS = ("hand", "belt", "gmorph", "free", "passage", "sweep")
SPECIMENS = {               # morph_handover windows (bend, turn, corner): A = meander69, B = fly_open
    "waves": [-1.0, -1.0, 2.0, 2.0, -1.0, -1.0],
    "cohen_key": [2.0, 2.0, 2.0, 2.0, 2.0, 2.0],
    "bowed_key": [-1.0, -1.0, 2.0, 2.0, 2.0, 2.0],
    "coiled_key": [-1.0, -1.0, -1.0, -1.0, 2.0, 2.0],
}
TRAILS = ("particles", "levitation", "staccato", "thrusting", "mantis")
TIERS = ("tiny", "mid", "large")
_NEG = {0: 0, 1: 1, 2: 1, 3: 3, 4: 4, 5: 5, 6: 1, 9: 9}


# ---------------------------------------------------------------------------
# small geometry helpers
# ---------------------------------------------------------------------------

def _seed(ctx, k: int, j: int) -> int:
    return int((int(ctx.sheet_seed) * 7919 + 104729 * (k + 1) + 613 * j) % SEED_MAX)


def _voice(ctx, spec: dict, box, seed: int) -> list[np.ndarray]:
    """Run a registered voice into `box` (through the run's library gate) → polylines in mm."""
    m = core.get("voice", spec["id"])
    params = m.validate(spec, where=f"cimpro voice {spec['id']!r}")
    params.pop("id")
    c = Ctx(ctx.frame, tuple(float(v) for v in box), int(seed), ctx.sheet_seed, 0, "voice", m.id, ctx.run)
    return [np.asarray(mk.points, float) for mk in m.fn(c, **params) if len(mk.points) >= 2]


def _voice_marks(ctx, spec: dict, box, seed: int) -> list[Mark]:
    m = core.get("voice", spec["id"])
    params = m.validate(spec, where=f"cimpro voice {spec['id']!r}")
    params.pop("id")
    c = Ctx(ctx.frame, tuple(float(v) for v in box), int(seed), ctx.sheet_seed, 0, "voice", m.id, ctx.run)
    return [mk for mk in m.fn(c, **params) if len(mk.points) >= 2]


def fit_box(lines: list[np.ndarray], box, angle: float = 0.0) -> list[np.ndarray]:
    """Rotate the lines about their common centre, then fit them (uniform scale) into box."""
    P_ = np.vstack(lines)
    c = (P_.min(axis=0) + P_.max(axis=0)) / 2
    rl = [rotate(l, c, angle) for l in lines]
    s, off = core.fit(rl, box)
    return [l * s + off for l in rl]


def fit_rot(lines: list[np.ndarray], box, angle: float = 0.0) -> list[np.ndarray]:
    """Fit the lines into box (a band keeps its length), then turn them about the box's centre."""
    s_, off = core.fit(lines, box)
    c = np.array([box[0] + box[2] / 2, box[1] + box[3] / 2])
    return [rotate(l * s_ + off, c, angle) for l in lines]


def place_along(lines: list[np.ndarray], A, B, max_half: float | None = None) -> list[np.ndarray]:
    """Lay the lines along the segment A→B from A: their principal axis onto AB, uniform scale so the
    extent along the axis is |AB|. If the lateral half-width would exceed `max_half` mm the scale is
    reduced (uniformly, never squeezed: the grammar stays whole) and the line ends short of B, in the air."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    P_ = np.vstack(lines)
    c = P_.mean(axis=0)
    _, _, vt = np.linalg.svd(P_ - c, full_matrices=False)
    ax = vt[0]
    first, last = lines[0][0], lines[-1][-1]
    if np.dot(last - first, ax) < 0:
        ax = -ax
    nx = np.array([-ax[1], ax[0]])
    pr = (P_ - c) @ ax
    L = max(float(pr.max() - pr.min()), 1e-6)
    AB = B - A
    d = AB / max(float(np.linalg.norm(AB)), 1e-9)
    n = np.array([-d[1], d[0]])
    s = float(np.linalg.norm(AB)) / L
    lat = np.abs((P_ - c) @ nx).max() * s
    if max_half is not None and lat > max_half:
        s *= max_half / lat
    out = []
    for l in lines:
        u = ((l - c) @ ax - pr.min()) * s
        v = ((l - c) @ nx) * s
        out.append(A + np.outer(u, d) + np.outer(v, n))
    return out


def start_at(line: np.ndarray, xy, heading: float, size: float) -> np.ndarray:
    """Rotate/scale a line so it starts at xy, leaving at `heading` (rad), its extent ≈ size mm."""
    l = np.asarray(line, float)
    ext = float(np.max(np.ptp(l, axis=0)))
    l = (l - l[0]) * (size / max(ext, 1e-6))
    t = tangents(resample(l, 0.3), 6)[0]
    rot = math.degrees(heading - math.atan2(t[1], t[0]))
    return rotate(l, np.zeros(2), rot) + np.asarray(xy, float)


def clip_ragged(line: np.ndarray, rect, rng, *, min_stub: float = 6.0, pull=(3.0, 25.0)) -> list[np.ndarray]:
    """Clip to the inner rectangle; a cut end is pulled back a random 3–25 mm (round 12's ragged cut ends:
    lines that leave do not draw the frame's edge)."""
    x0, y0, x1, y1 = rect
    p = np.asarray(line, float)
    inside = (p[:, 0] >= x0) & (p[:, 0] <= x1) & (p[:, 1] >= y0) & (p[:, 1] <= y1)
    if inside.all():
        return [p]
    out = []
    cut = np.flatnonzero(np.diff(inside.astype(int))) + 1
    for seg in np.split(np.arange(len(p)), cut):
        if not len(seg) or not inside[seg[0]]:
            continue
        q = p[seg]
        s = arclen(q)
        a, b = 0.0, s[-1]
        if seg[0] > 0:
            a = float(rng.uniform(*pull))
        if seg[-1] < len(p) - 1:
            b = s[-1] - float(rng.uniform(*pull))
        if b - a < min_stub:
            continue
        keep = (s >= a) & (s <= b)
        if keep.sum() >= 2:
            out.append(q[keep])
    return out


def offset_passes(path: np.ndarray, width: float, pen: float) -> np.ndarray:
    """A heavy mark `width` mm wide as ONE contiguous line: parallel passes of the path (each pen
    `pen` wide, overlapping, so it reads solid), joined end to end alternately (no hatching gaps)."""
    from shapely.geometry import LineString  # noqa: PLC0415
    n = max(1, int(math.ceil(max(width - pen, 0.0) / (0.7 * pen))) + 1)
    if n == 1:
        return np.asarray(path, float)
    ls = LineString(path)
    out = []
    for i, d in enumerate(np.linspace(-(width - pen) / 2, (width - pen) / 2, n)):
        g = ls.offset_curve(float(d), join_style=2, mitre_limit=3.0) if abs(d) > 1e-9 else ls
        q = np.asarray(g.coords) if g.geom_type == "LineString" else np.asarray(path, float)
        if len(q) < 2:
            continue
        # shapely ≥ 2 keeps the direction of the input for both sides
        out.append(q if i % 2 == 0 else q[::-1])
    return np.vstack(out)


# ---------------------------------------------------------------------------
# the sheet so far, and how it is looked at
# ---------------------------------------------------------------------------

class SheetState:
    def __init__(self, frame, inner):
        self.frame = frame
        self.inner = inner                    # (x0, y0, x1, y1) mm
        self.lines: list[dict] = []           # pts, pens (per point), ink, role, reg, move, tier, hand, codes
        self.covers: list[dict] = []
        self.calls: list[dict] = []
        self.reserve: dict | None = None
        self.log: list[dict] = []
        self.counts: dict[str, int] = {}
        self.tiers: dict[str, int] = {t: 0 for t in TIERS}
        self.cores: list[dict] = []           # boxes of seeded cores (cx, cy, r)
        self._grammar_cache: dict = {}

    def add(self, pts, *, pen, ink, role, reg, move, tier=None, hand=None, codes=None, pens=None):
        pts = np.asarray(pts, float)
        if len(pts) < 2:
            return None
        d = {"pts": pts, "pens": np.full(len(pts), float(pen)) if pens is None else np.asarray(pens, float),
             "ink": ink, "role": role, "reg": reg, "move": move, "hand": hand,
             "codes": np.zeros(len(pts)) if codes is None else np.asarray(codes, float)}
        self.lines.append(d)
        if tier:
            self.tiers[tier] += 1
        return d


def look(S: SheetState, cell: float) -> dict:
    """Perceive the sheet so far on a coarse grid. Cheap: one weighted histogram + two blurs."""
    from scipy.ndimage import distance_transform_edt, gaussian_filter, label  # noqa: PLC0415
    W, H = S.frame
    nx, ny = int(math.ceil(W / cell)), int(math.ceil(H / cell))
    grid = np.zeros((ny, nx))
    for d in S.lines:
        p = d["pts"]
        seg = np.diff(p, axis=0)
        L = np.linalg.norm(seg, axis=1)
        mid = (p[1:] + p[:-1]) / 2
        w = L * np.maximum(d["pens"][1:], 0.3) / 0.3
        h, _, _ = np.histogram2d(mid[:, 1], mid[:, 0], bins=[ny, nx], range=[[0, ny * cell], [0, nx * cell]],
                                 weights=w)
        grid += h
    total = float(grid.sum())
    x0, y0, x1, y1 = S.inner
    jj, ii = np.meshgrid((np.arange(nx) + 0.5) * cell, (np.arange(ny) + 0.5) * cell)
    inner = (jj >= x0) & (jj <= x1) & (ii >= y0) & (ii <= y1)
    occ = grid > 0
    coverage = float(occ[inner].mean()) if inner.any() else 0.0
    per = {"cell": cell, "grid": grid, "total": total, "coverage": coverage, "n_lines": len(S.lines)}
    # the blank: largest disk free of ink (inside the inner frame)
    free = ~occ & inner
    dist = distance_transform_edt(free) * cell
    # the frame's edge bounds a blank too
    edge_d = np.minimum.reduce([jj - x0, x1 - jj, ii - y0, y1 - ii])
    dist = np.minimum(dist, np.maximum(edge_d, 0))
    bi = np.unravel_index(int(np.argmax(dist)), dist.shape)
    per["blank"] = {"xy": (float(jj[bi]), float(ii[bi])), "r": float(dist[bi])}
    per["dist"] = dist
    per["jj"], per["ii"] = jj, ii
    if total <= 0:
        per.update({"core": None, "core2": None, "off": 0.0, "settled": 1.0, "centroid": (W / 2, H / 2)})
        return per
    cy = float((grid * ii).sum() / total)
    cx = float((grid * jj).sum() / total)
    off = math.hypot(cx - W / 2, cy - H / 2) / (0.5 * math.hypot(W, H))
    sig = 0.07 * min(W, H) / cell
    Dc = gaussian_filter(grid, sig)
    k = np.unravel_index(int(np.argmax(Dc)), Dc.shape)
    lab, _ = label(Dc > 0.45 * Dc[k])
    reg = lab == lab[k]
    share = float(grid[reg].sum() / total)
    rcx = float((grid[reg] * jj[reg]).sum() / max(grid[reg].sum(), 1e-9))
    rcy = float((grid[reg] * ii[reg]).sum() / max(grid[reg].sum(), 1e-9))
    area = float(reg.sum()) * cell * cell
    core_ = {"xy": (rcx, rcy), "peak": (float(jj[k]), float(ii[k])), "r": max(math.sqrt(area / math.pi), 8.0),
             "share": share, "mask": reg}
    # boundary cells of the core region (its edge)
    from scipy.ndimage import binary_erosion  # noqa: PLC0415
    edge = reg & ~binary_erosion(reg)
    core_["edge"] = np.c_[jj[edge], ii[edge]]
    # a competing density outside the core
    from scipy.ndimage import binary_dilation  # noqa: PLC0415
    away = ~binary_dilation(reg, iterations=max(int(round(10.0 / cell)), 1))
    core2 = None
    if away.any() and Dc[away].max() > 0.35 * Dc[k]:
        k2 = np.unravel_index(int(np.argmax(np.where(away, Dc, -1))), Dc.shape)
        core2 = {"xy": (float(jj[k2]), float(ii[k2])), "ratio": float(Dc[k2] / Dc[k])}
    per.update({"core": core_, "core2": core2, "off": off, "centroid": (cx, cy)})
    # settled: the eye can rest (centred mass, one evenly spread density, no competing pull)
    competing = core2 is not None and core2["ratio"] > 0.6
    # the eye rests when the mass is centred, when one lone core is all there is, or when the ink is spread
    # evenly with nothing pulling; it does not rest between two pulls (a competing density, a heavy mark
    # away from the core, or a counterweight)
    centred = max(0.0, 1.0 - off / 0.12)
    lone = 0.75 if (share > 0.6 and core2 is None) else 0.0
    even = 0.6 if (share < 0.3 and core2 is None) else 0.0
    settled = max(centred, lone, even)
    heavy_away = any(d["role"] == "heavy" for d in S.lines)
    if competing:
        settled *= 0.35
    elif core2 is not None:
        settled *= 0.7
    if heavy_away:
        settled *= 0.6
    per["settled"] = float(settled)
    per["competing"] = competing
    return per


def in_reserve(S: SheetState, xy, pad: float = 0.0) -> bool:
    R = S.reserve
    if R is None:
        return False
    return math.hypot(xy[0] - R["xy"][0], xy[1] - R["xy"][1]) < R["r"] + pad


def _softpick(rng, cands, scores, temp: float = 1.0):
    s = np.asarray(scores, float)
    s = (s - s.max()) / max(temp, 1e-6)
    p = np.exp(s)
    p /= p.sum()
    return cands[int(rng.choice(len(cands), p=p))]


def _rand_points(rng, S, n):
    x0, y0, x1, y1 = S.inner
    return np.c_[rng.uniform(x0, x1, n), rng.uniform(y0, y1, n)]


def _density_at(per, xy) -> float:
    c = per["cell"]
    g = per["grid"]
    j = int(np.clip(xy[0] // c, 0, g.shape[1] - 1))
    i = int(np.clip(xy[1] // c, 0, g.shape[0] - 1))
    return float(g[max(i - 2, 0):i + 3, max(j - 2, 0):j + 3].sum())


def _blank_at(per, xy) -> float:
    c = per["cell"]
    d = per["dist"]
    j = int(np.clip(xy[0] // c, 0, d.shape[1] - 1))
    i = int(np.clip(xy[1] // c, 0, d.shape[0] - 1))
    return float(d[i, j])


# ---------------------------------------------------------------------------
# temperament (per sheet) and the decision
# ---------------------------------------------------------------------------

def temperament(rng, appetite, hands_k) -> dict:
    """Drawn once per sheet: the dials whose settings vary between sheets of one series, to extremes."""
    lo, hi = math.log(0.05), math.log(0.62)
    a = appetite if appetite is not None else math.exp(lo + (hi - lo) * float(rng.random()) ** 1.15)
    verbs = {v: float(rng.gamma(0.9, 1.0)) for v in VERBS if v != "stop"}
    players = dict(zip(LINE_PLAYERS, rng.dirichlet([0.6] * len(LINE_PLAYERS)).tolist()))
    hands = [HANDS[i] for i in sorted(rng.choice(len(HANDS), size=hands_k, replace=False).tolist())]
    found_ink = str(rng.choice(["blue", "blue", "blue", "red", "cyan"]))
    forms = rng.dirichlet([0.7] * 5)
    return {"appetite": float(a), "verbs": verbs, "players": players, "hands": hands, "found_ink": found_ink,
            "bold_ride": bool(rng.random() < 0.6), "second_ink": str(rng.choice(["red", "red-400", "blue"])),
            "forms": [float(x) for x in forms], "river_zoom": float(math.exp(rng.uniform(math.log(320), math.log(3400))))}


def decide(S: SheetState, per: dict, T: dict, k: int, rng, *, min_moves: int, moves_max: int) -> tuple[str, str]:
    """A weighted draw among the moves the state allows. Returns (verb, why)."""
    v = T["verbs"]
    c = S.counts
    cov, app = per["coverage"], T["appetite"]
    hungry = cov < app
    hunger = max(app - cov, 0.0) / max(app, 1e-6)
    core_ = per["core"]
    settled = per.get("settled", 1.0)
    n_found = c.get("found", 0)
    w: dict[str, float] = {}
    why: dict[str, str] = {}
    if k == 0:
        # the opening: what the empty sheet invites is anything; the temperament decides
        for verb, base in (("found", 1.6), ("seed", 1.2), ("traverse", 0.9), ("sign", 0.35), ("reserve", 0.5),
                           ("ladder", 0.3)):
            w[verb] = base * (0.4 + v[verb])
        why = {x: "empty sheet" for x in w}
    else:
        if n_found < 2:
            w["found"] = v["found"] * (1.0 if n_found == 0 else 0.35) * (1.4 if k < 4 else 0.5)
            why["found"] = "no found matter yet" if n_found == 0 else "a second found ground"
        if core_ is None or core_["share"] < 0.25 or c.get("seed", 0) == 0:
            w["seed"] = v["seed"] * 1.3
            why["seed"] = "no core yet" if core_ is None or c.get("seed", 0) == 0 else "the ink is spread, no core"
        else:
            w["seed"] = v["seed"] * (0.15 + 0.9 * hunger * min(app / 0.35, 1.5))
            why["seed"] = "a second core" + (" (far from the appetite)" if hunger > 0.5 else "")
        if core_ is not None:
            w["thicken"] = v["thicken"] * (2.4 if hungry else 0.4) * (1.0 + core_["share"])
            why["thicken"] = f"core holds {core_['share']:.0%}; coverage {cov:.2f} < appetite {app:.2f}" if hungry \
                else "the core takes more"
        tr = c.get("traverse", 0)
        w["traverse"] = v["traverse"] * (1.6 if tr == 0 and k >= 1 else 0.35 / (1 + tr)) * (1.3 if hungry else 0.7)
        why["traverse"] = "nothing crosses the whole sheet yet" if tr == 0 else "another crossing"
        if core_ is not None:
            ni = c.get("intrude", 0)
            w["intrude"] = v["intrude"] * (0.8 + 2.2 * settled) * (1.0 if ni == 0 else 0.25 / ni) * (k >= 2)
            why["intrude"] = f"settled {settled:.2f}: a heavy foreign mark at the core's edge"
            if core_["share"] > 0.55 and not per.get("competing"):
                w["counterweight"] = v["counterweight"] * (0.8 + 2.0 * settled + core_["share"]) / \
                    (1 + c.get("counterweight", 0))
                why["counterweight"] = f"one core holds {core_['share']:.0%}: a smaller density elsewhere"
            if core_["share"] > 0.3 and per["n_lines"] >= 4:
                w["cover"] = v["cover"] * 0.9 / (1 + 2 * c.get("cover", 0))
                why["cover"] = "the core is dense enough to cut back into"
            if per["blank"]["r"] > 25.0:
                w["trail"] = v["trail"] * (0.6 + per["blank"]["r"] / 60.0) * (1.0 if c.get("trail", 0) < 3 else 0.3)
                why["trail"] = f"a blank of r {per['blank']['r']:.0f} mm beside the core"
        open_calls = [q for q in S.calls if not q["used"]]
        if open_calls:
            w["answer"] = v["answer"] * min(len(open_calls), 3) * 0.45 / (1 + 0.35 * c.get("answer", 0))
            why["answer"] = f"{len(open_calls)} line ends stop in the air"
        if S.covers and not any(cv["crossed"] for cv in S.covers):
            w["cross"] = 2.5
            why["cross"] = "a cover nobody has crossed"
        missing = [t for t in TIERS if S.tiers[t] == 0]
        if missing:
            w["ladder"] = v["ladder"] * 0.7 * len(missing)
            why["ladder"] = "no " + "/".join(missing) + " scale yet"
        w["sign"] = v["sign"] * (0.35 if c.get("sign", 0) == 0 else 0.08)
        why["sign"] = "a limb sign"
        if S.reserve is None and k <= 3 and per["blank"]["r"] > 30:
            w["reserve"] = v["reserve"] * 0.6
            why["reserve"] = f"keep the blank of r {per['blank']['r']:.0f} mm"
        if k >= min_moves:
            ratio = cov / max(app, 1e-6)
            # stop more readily when the sheet is unresolved (T7), less when the eye can rest
            stop = 3.0 / (1 + math.exp(-10.0 * (ratio - 1.0))) * (1.6 - settled)
            if k >= moves_max - 1:
                stop = 1e6
            w["stop"] = stop
            why["stop"] = f"coverage {cov:.2f} vs appetite {app:.2f}, settled {settled:.2f}"
        if c.get("guest", -1) >= 0:
            w["guest"] = v["guest"] * 0.25
            why["guest"] = "a guest player"
    # habituation: a verb just played several times loses its pull (boredom), so no move runs on forever
    recent = [e["verb"] for e in S.log[-4:]]
    for n_ in w:
        if n_ != "stop":
            w[n_] *= 0.7 ** recent.count(n_)
    names = sorted(w)
    p = np.array([max(w[n], 0.0) for n in names])
    if p.sum() <= 0:
        return "stop", "nothing invites a move"
    verb = names[int(rng.choice(len(names), p=p / p.sum()))]
    return verb, why.get(verb, "")


# ---------------------------------------------------------------------------
# the walk: a made line against what is there
# ---------------------------------------------------------------------------

WALK = dict(capture=5.0, align=0.55, listen=60.0, ignore=35.0, ride=18.0, ride_sd=0.45, min_ride=7.0, ride_gap=0.9,
            return_mm=30.0, ramp=2.0, max_offset=18.0, catches=3, tick_linger=1.0, own_mm=6.0, rule_tol=3.5, snap=8.0,
            immune_mm=50.0, omega_max=120.0, rule_shared=9.0)


def walk(ctx, S: SheetState, M: np.ndarray, rng, *, step: float, listen_to: int = 2):
    """The line walks the sheet: contacts with the found river / chart / recent hands are caught and
    carried (contagion), else it passes. Returns (points, codes)."""
    from .arrangers_oehlen_found import Ground  # noqa: PLC0415
    M = resample(M, step)
    if len(M) < 8:
        return M, np.zeros(len(M))
    grounds, grammars, full, decay = {}, {}, {}, {}
    river = [d["pts"] for d in S.lines if d["reg"] == "river" and d["role"] == "found"]
    chart = [d["pts"] for d in S.lines if d["reg"] == "chart" and d["role"] == "found"
             and arclen(d["pts"])[-1] > 30.0]
    key = (len(river), len(chart))
    if key not in S._grammar_cache:
        gr = {}
        if river:
            try:
                gr["river"] = river_grammar(river, axis_mm=10.0, omega_max=120.0)
            except ValueError:
                pass
        if chart:
            try:
                gr["plate"] = chart_grammar(chart)
            except (ValueError, IndexError):
                pass
        S._grammar_cache = {key: gr}
    gr = S._grammar_cache[key]
    if "river" in gr:
        grounds["river"], grammars["river"] = Ground(river, step, tag=1), gr["river"]
        full["river"], decay["river"] = 45.0, 80.0
    if "plate" in gr:
        grounds["plate"], grammars["plate"] = Ground(chart, step, tag=2), gr["plate"]
        full["plate"], decay["plate"] = 25.0, 35.0
    made = [d for d in S.lines if d["role"] == "made" and d.get("hand")][-listen_to:] if listen_to else []
    for d in made:
        kk = f"line{len(grounds)}"
        g = ctx.use("hand", d["hand"])
        R = max(float(arclen(d["pts"])[-1]) / 4.0, 20.0)
        grounds[kk] = Ground([d["pts"]], step, tag=3)
        grammars[kk] = {"gen": hand_gen(g, R * 0.3, step=0.2, pull=0.2, axis_mm=10.0, amp_max=7.0),
                        "code": HAND_CODE, "ride_code": HAND_RIDE, "hand": d["hand"]}
        full[kk], decay[kk] = 35.0, 60.0
    if not grounds:
        return M, np.zeros(len(M))
    tick = gr["plate"]["pitch_mm"] * 1.5 if "plate" in gr else 6.3
    pts, codes, _ = contagion_walk(M, grounds, grammars, rng, step=step, full=full, decay=decay, tick_pitch=tick,
                                   regimes=tuple(grounds), carry=True, **WALK)
    if "plate" in grammars and len(pts):
        pts = chart_needles(pts, codes, grammars["plate"])
    return pts, np.array([_NEG.get(int(c), 0) for c in codes], float)


# ---------------------------------------------------------------------------
# players: what a move plays
# ---------------------------------------------------------------------------

_FREE: dict = {}


def free_line(ctx) -> np.ndarray:
    """Accrue's free hand, seed 3966 (Ian: "love love"), exact geometry at its recorded half-A4 size
    (computed once per process; the hand is still loaded through the gate so the run records it)."""
    from .voices_passage import free_opening  # noqa: PLC0415
    g = ctx.use("hand", "river_belt")
    if "pts" not in _FREE:
        pts, _ = free_opening(g, (0.0, 0.0, 285.0, 94.0), 3966)
        _FREE["pts"] = np.asarray(pts, float)
    return _FREE["pts"].copy()


def player_lines(ctx, player: str, T: dict, rng, k: int, j: int, box, *, length=None) -> tuple[list, str | None, str]:
    """Run a line player into box → (polylines, hand id or None, description)."""
    sd = _seed(ctx, k, j)
    if player == "hand":
        h = str(rng.choice(T["hands"]))
        L = float(length if length is not None else rng.uniform(1.5, 5.5))
        return _voice(ctx, {"id": "hand", "hand": h, "length": L}, box, sd), h, f"hand {h} ×{L:.1f}R"
    if player == "belt":
        g0 = float(rng.uniform(0.8, 2.2))
        g1 = float(np.clip(g0 * math.exp(rng.normal(0, 0.5)), 0.6, 3.2))
        L = float(length if length is not None else rng.uniform(4.0, 9.0))
        return (_voice(ctx, {"id": "belt", "hand": "river_belt", "length": L, "gain": g0, "gain_end": g1,
                             "pull": float(rng.uniform(0.12, 0.35))}, box, sd), "river_belt",
                f"belt gain {g0:.1f}→{g1:.1f}")
    if player == "gmorph":
        h = str(rng.choice(("dance_staccato", "river_belt", "hokusai", "meander69", "fly_open")))
        n = int(rng.integers(3, 7))
        us = np.sort(rng.uniform(0, 1, n))
        sched = lambda lo, hi: [float(x) for u in us for x in (u, rng.uniform(lo, hi))]  # noqa: E731
        spec = {"id": "gmorph", "hand": h, "length": float(length if length is not None else rng.uniform(5, 12)),
                "turn": sched(0.05, 0.95), "span": sched(0.2, 0.9), "sign": sched(-1.0, 1.0),
                "gain": sched(0.8, 1.8)}
        return _voice(ctx, spec, box, sd), h, f"gmorph {h}, {n} erratic stations"
    if player == "sweep":        # a hand at its slowest: under two of its reference lengths, laid out large
        h = str(rng.choice(T["hands"]))
        L = float(rng.uniform(0.6, 1.6))
        return _voice(ctx, {"id": "hand", "hand": h, "length": L}, box, sd), h, f"sweep {h} ×{L:.1f}R"
    if player == "free":
        return [free_line(ctx)], "river_belt", "the 3966 free hand"
    if player == "passage":
        mm = float(rng.uniform(500, 1400))
        return (_voice(ctx, {"id": "passage", "opening": "none", "max_mm": mm, "rows": 1,
                             "erratic": float(rng.uniform(0.2, 0.8))}, box, sd), None, f"passage {mm:.0f} mm")
    raise ValueError(f"cimpro: unknown player {player!r}")


def pick_player(rng, T, allowed=LINE_PLAYERS) -> str:
    p = np.array([T["players"][a] for a in allowed]) + 0.03
    return allowed[int(rng.choice(len(allowed), p=p / p.sum()))]


# ---------------------------------------------------------------------------
# the arranger
# ---------------------------------------------------------------------------

@arranger("cimpro", params=[
    P("upto", "int", 0, "stop after this many moves (0 = until the improviser stops): process strips", min=0,
      max=200),
    P("moves_max", "int", 60, "hard cap on moves", min=2, max=200),
    P("min_moves", "int", 4, "the improviser may stop after this many moves", min=1, max=60),
    P("appetite", "float", None, "density dial (target coverage share of grid cells); null = drawn per sheet, "
      "0.05–0.62, extremes allowed", min=0.01, max=0.95, optional=True),
    P("cell", "float", 4.0, "perception grid, mm", min=1.0, max=20.0),
    P("hands_k", "int", 3, "hands in this sheet's vocabulary", min=1, max=8),
    P("step", "float", 0.35, "walk resampling step, mm", min=0.15, max=1.0),
    P("inset", "float", 7.0, "inner frame (lines leaving it are cut ragged), mm", min=0.0, max=40.0),
    P("heavy", "floats", [1.6, 2.8], "heavy pen range, mm"),
    P("allow", "str", "", "comma list of verbs allowed (empty = all)"),
], doc="the composer as improviser: looks at the sheet so far (coarse density grid: core, blank, balance, "
        "scales, open ends) and decides the next move, every time; steers away from a settled sheet")
def cimpro(ctx, parts, *, upto, moves_max, min_moves, appetite, cell, hands_k, step, inset, heavy, allow):
    W, H = ctx.frame
    inner = (inset, inset, W - inset, H - inset)
    S = SheetState((W, H), inner)
    T = temperament(ctx.rng("temper"), appetite, hands_k)
    allowed = {a.strip() for a in allow.split(",") if a.strip()} or set(VERBS)
    bad = allowed - set(VERBS)
    if bad:
        raise ValueError(f"cimpro: unknown verb(s) {sorted(bad)}; choose from {VERBS}")
    if parts[1:]:
        S.counts["guest"] = 0
    hv = (float(min(heavy)), float(max(heavy))) if heavy else (1.6, 2.8)
    S._bold_ride = T["bold_ride"]
    n_moves = moves_max if upto == 0 else min(upto, moves_max)
    import time  # noqa: PLC0415
    for k in range(n_moves):
        t0 = time.perf_counter()
        per = look(S, cell)
        t_look = time.perf_counter() - t0
        rng = ctx.rng("move", k)
        verb, why = decide(S, per, T, k, rng, min_moves=min_moves, moves_max=moves_max)
        tries = 0
        while verb not in allowed and tries < 20:
            verb, why = decide(S, per, T, k, rng, min_moves=min_moves, moves_max=moves_max)
            tries += 1
        if verb not in allowed:
            verb, why = "stop", "no allowed move"
        entry = {"k": k, "verb": verb, "why": why, "coverage": round(per["coverage"], 3),
                 "settled": round(per.get("settled", 1.0), 2)}
        if verb == "stop":
            S.log.append(entry)
            break
        n0 = len(S.lines)
        act = ACTS[verb]
        what = act(ctx, S, per, T, rng, k, parts=parts, step=step, heavy=hv)
        entry["what"] = what
        entry["lines"] = len(S.lines) - n0
        entry["ms"] = {"look": round(1000 * t_look), "act": round(1000 * (time.perf_counter() - t0 - t_look))}
        S.counts[verb] = S.counts.get(verb, 0) + 1
        S.log.append(entry)
    return emit(S, parts, T)


def emit(S: SheetState, parts, T) -> list[Mark]:
    part = parts[0].index
    out = []
    for li, d in enumerate(S.lines):
        p, pens = d["pts"], d["pens"]
        cut = np.flatnonzero(np.diff(pens) != 0) + 1
        bounds = [0, *cut.tolist(), len(p)]
        for a, b in zip(bounds[:-1], bounds[1:]):
            a0 = max(a - 1, 0)                     # runs share their junction point: one contiguous line
            if b - a0 < 2:
                continue
            out.append(Mark(p[a0:b], {"neg": d["codes"][a0:b]},
                            {"part": part, "of_role": d["role"], "ink": d["ink"], "pen": float(pens[a]),
                             "reg": d["reg"], "move": d["move"], "line": li}))
    if out:
        out[0] = out[0].evolve(meta={"cimpro": {
            "log": S.log, "temperament": {k: v for k, v in T.items()},
            "reserve": S.reserve, "covers": [{"xy": c["xy"], "crossed": c["crossed"]} for c in S.covers]}})
    return out


# ---------------------------------------------------------------------------
# acts
# ---------------------------------------------------------------------------

def _xy(p):
    return [round(float(p[0]), 1), round(float(p[1]), 1)]


def _made(ctx, S, rng, lines, *, k, verb, tier, hand, pen, ink="black", step, walk_it=True, bold=None,
          call=True, role="made", reg="hand"):
    """Walk (optionally), clip ragged, weight and add made lines; register their ends as calls."""
    n = 0
    for l in lines:
        if len(l) < 2:
            continue
        if walk_it:
            pts, codes = walk(ctx, S, l, ctx.rng("walk", k, n), step=step)
        else:
            pts, codes = resample(l, step), np.zeros(len(resample(l, step)))
        for q in clip_ragged(pts, S.inner, rng):
            # codes follow the clipped piece by nearest index
            from scipy.spatial import cKDTree  # noqa: PLC0415
            idx = cKDTree(pts).query(q)[1] if len(pts) else np.zeros(len(q), int)
            cq = codes[idx] if len(codes) else np.zeros(len(q))
            pens = np.full(len(q), pen)
            if bold is not None and T_bold_ride(S):
                ride = np.isin(cq, (1,))
                pens[ride] = bold
            d = S.add(q, pen=pen, pens=pens, ink=ink, role=role, reg=reg, move=k, tier=tier if n == 0 else None,
                      hand=hand, codes=cq)
            if d is None:
                continue
            n += 1
            if call:
                e = q[-1]
                x0, y0, x1, y1 = S.inner
                if min(e[0] - x0, x1 - e[0], e[1] - y0, y1 - e[1]) > 12.0:
                    t = tangents(q[-min(len(q), 30):], 4)[-1]
                    S.calls.append({"xy": e, "head": math.atan2(t[1], t[0]), "line": len(S.lines) - 1,
                                    "used": False, "hand": hand})
    return n


def T_bold_ride(S):
    return S.__dict__.get("_bold_ride", True)


def inside(S, c, w, h, slack: float = 0.0):
    """Clamp a centre so a w × h box sits inside the inner frame (things placed whole, not cut at the edge)."""
    x0, y0, x1, y1 = S.inner
    hw, hh = max(w / 2 - slack, 0.0), max(h / 2 - slack, 0.0)
    cx = float(np.clip(c[0], x0 + hw, x1 - hw)) if x1 - x0 > 2 * hw else (x0 + x1) / 2
    cy = float(np.clip(c[1], y0 + hh, y1 - hh)) if y1 - y0 > 2 * hh else (y0 + y1) / 2
    return np.array([cx, cy])


def _box_at(c, size, aspect=1.0):
    w = size * math.sqrt(aspect)
    h = size / math.sqrt(aspect)
    return (c[0] - w / 2, c[1] - h / 2, w, h)


def _tier_of(size):
    return "tiny" if size < 28 else "mid" if size < 95 else "large"


def _pen_for(rng, tier):
    if tier == "tiny":
        return float(rng.choice([0.25, 0.3, 0.35]))
    if tier == "mid":
        return float(rng.choice([0.25, 0.3, 0.4, 0.5]))
    return float(rng.choice([0.25, 0.3, 0.5, 0.8]))


def act_found(ctx, S, per, T, rng, k, *, step, **_):
    W, H = S.frame
    have = {d["reg"] for d in S.lines if d["role"] == "found"}
    kinds = ["river", "braid", "loops", "chart"]
    pk = np.array([0.38, 0.2, 0.15, 0.27]) * np.array([0.25 if x in have else 1.0 for x in kinds])
    kind = kinds[int(rng.choice(4, p=pk / pk.sum()))]
    # where: the first found matter sits anywhere off the middle; later ones go where the ink is not
    cands = _rand_points(rng, S, 30)
    if per["total"] > 0:
        sc = [0.04 * _blank_at(per, c) * float(rng.choice([1, -1])) - (20.0 if in_reserve(S, c, 20.0) else 0.0)
              for c in cands]                                     # into the blank or onto ink; not the reserve
    else:
        sc = [0.03 * math.hypot(c[0] - W / 2, c[1] - H / 2) for c in cands]
    c = _softpick(rng, cands, sc, 1.0)
    if kind == "river":
        w = float(rng.uniform(0.35, 1.05)) * W
        h = w * float(rng.uniform(0.12, 0.42))
        ang = float(rng.normal(0, 14)) if rng.random() < 0.8 else float(rng.choice([-1, 1]) * rng.uniform(55, 90))
        # the Amazon stem zooming in and out along itself (thread c1's river_zoom), never at one fixed far zoom;
        # asymmetric schedules only (a symmetric swell reads as an ornament)
        sch = str(rng.choice(["push", "pulses", "drift", "dive", "steps", "ramp_in", "ramp_out"]))
        zm = float(math.exp(rng.uniform(math.log(4.0), math.log(40.0))))
        spec = {"id": "river_zoom", "mode": "magnify", "schedule": sch, "recur": int(rng.integers(1, 5)), "zoom": zm,
                "start": float(rng.uniform(0.0, 0.8)), "river": float(rng.uniform(0.12, 0.45)), "course": "free"}
        lines = _voice(ctx, spec, (0, 0, w, h), _seed(ctx, k, 0))
        what = f"found river zooming ({sch}, up to ×{zm:.0f})"
    elif kind in ("braid", "loops"):
        w = float(rng.uniform(0.3, 0.9)) * W
        h = w * float(rng.uniform(0.18, 0.5))
        ang = float(rng.normal(0, 18))
        if kind == "braid":
            spec = {"id": "river_braid", "braid": "river_anavilhanas", "host": "river_bend",
                    "length": float(rng.uniform(2.0, 4.5)), "threads": int(rng.integers(3, 7))}
        else:
            spec = {"id": "river_loops", "loops": "river_cutoffs", "family": "oxbow", "mode": "knot",
                    "host": "river_meander", "length": float(rng.uniform(3.0, 7.0)), "n": int(rng.integers(3, 9))}
        lines = _voice(ctx, spec, (0, 0, w, h), _seed(ctx, k, 0))
        what = f"found {'braided river' if kind == 'braid' else 'oxbow river'}"
    else:
        w = float(rng.uniform(0.32, 0.75)) * W
        h = float(rng.uniform(0.18, 0.5)) * H
        ang = float(rng.normal(0, 6))
        spec = {"id": "diagram", "chart": "kappa", "rows": int(rng.integers(2, 6)),
                "hands": [str(rng.choice(T["hands"]))], "length": float(rng.uniform(4, 8))}
        lines = _voice(ctx, spec, (0, 0, w, h), _seed(ctx, k, 0))
        lines = [l for l in lines if float(np.max(np.ptp(l, axis=0))) >= 5.0]   # drop the lettering
        what = f"found chart, {spec['rows']} rows"
    # pasted: centred on c, rotated, cut to its rectangle (and the sheet)
    cx = float(np.clip(c[0], S.inner[0] + 0.25 * w * 0.5, S.inner[2] - 0.25 * w * 0.5))
    cy = float(np.clip(c[1], S.inner[1] + 0.25 * h * 0.5, S.inner[3] - 0.25 * h * 0.5))
    rect = rect_polygon(cx, cy, w * 0.98, h * 0.98, ang)
    placed = [rotate(l + [cx - w / 2, cy - h / 2], np.array([cx, cy]), ang) for l in lines]
    n = 0
    for l in clip_rect(placed, rect, 6.0):          # the paste's own edge is a clean cut (a container) …
        for q in clip_ragged(l, S.inner, rng):       # … the sheet's edge never is
            if S.add(q, pen=0.3, ink=T["found_ink"], role="found", reg=kind, move=k,
                     tier=_tier_of(max(w, h)) if n == 0 else None) is not None:
                n += 1
    return f"{what} in a {w:.0f}×{h:.0f} mm paste at {_xy((cx, cy))}, {ang:+.0f}°"


def _core_point(rng, S, per, T):
    """Where a new core goes: off the middle, out of the reserve; on top of found matter or in blank."""
    W, H = S.frame
    cands = _rand_points(rng, S, 40)
    sc = []
    for c in cands:
        s = 0.025 * math.hypot(c[0] - W / 2, c[1] - H / 2)          # off-centre
        if in_reserve(S, c, 10.0):
            s -= 20.0
        if per["core"] is not None:
            s += 0.01 * math.hypot(c[0] - per["core"]["xy"][0], c[1] - per["core"]["xy"][1])
        sc.append(s + float(rng.normal(0, 0.6)))
    return _softpick(rng, cands, sc, 1.0)


def _hunger(S, per, T) -> float:
    """How far the sheet is from its density dial, weighted by how dense the dial is (0 … ~1.5): a
    hungry dense sheet plays more elements per move, so the all-over extreme is reachable."""
    app = T["appetite"]
    return max(app - per["coverage"], 0.0) / max(app, 1e-6) * min(app / 0.4, 1.5)


CORE_FORMS = ("hands", "coil", "specimens", "beads", "found")


def core_form(ctx, S, T, rng, k, c, size, form, n, *, step, verb, j0=0) -> str:
    """Play n elements of one core form around c (a box of `size` mm). Forms differ in grammar, speed and
    weight, so two cores (or two sheets' cores) need not be the same scribble ball."""
    tier = _tier_of(size)
    descs = []
    for j in range(j0, j0 + n):
        cj = c + rng.normal(0, 0.18 * size, 2)
        sz = size * float(rng.uniform(0.55, 1.15))
        asp = float(rng.uniform(0.6, 1.6))
        ang = float(rng.uniform(0, 360))
        if form == "hands":
            player = "hand" if rng.random() < 0.8 else pick_player(rng, T, ("hand", "belt", "gmorph"))
            lines, h, d = player_lines(ctx, player, T, rng, k, j, _box_at(cj, sz, asp),
                                       length=float(rng.uniform(1.5, 4.0)) if player == "hand" else
                                       float(rng.uniform(3.0, 6.0)))
            lines = fit_box(lines, _box_at(cj, sz, asp), ang)
            _made(ctx, S, rng, lines, k=k, verb=verb, tier=tier if j == j0 else None, hand=h,
                  pen=_pen_for(rng, tier), step=step, bold=0.9)
        elif form == "coil":       # a long travelling line pressed into a small box: a dense coiled mass
            player = str(rng.choice(["belt", "gmorph"]))
            lines, h, d = player_lines(ctx, player, T, rng, k, j, _box_at(cj, sz, asp),
                                       length=float(rng.uniform(7.0, 12.0)))
            lines = fit_box(lines, _box_at(cj, sz * 0.8, asp), ang)
            _made(ctx, S, rng, lines, k=k, verb=verb, tier=tier if j == j0 else None, hand=h,
                  pen=float(rng.choice([0.25, 0.3, 0.5])), step=step, walk_it=False)
        elif form == "specimens":  # tiny periodic matter crossing itself: a knot of specimen bands
            name = str(rng.choice(list(SPECIMENS)))
            L = float(np.clip(sz * rng.uniform(1.0, 1.8), 30, 200))
            hh = L * float(rng.uniform(0.07, 0.15))
            spec = {"id": "morph_handover", "hands": ["meander69", "fly_open"], "order": "bend,turn,corner",
                    "rows": 1, "R_mm": max(85.0 * L / 290.0, 10.0), "band": max(14.0 * L / 290.0, 2.5), "ease": 1.3,
                    "run": 4.0, "windows": SPECIMENS[name], "max_mm": 4 * L, "K": 5}
            lines = fit_rot(_voice(ctx, spec, (0, 0, L, hh), _seed(ctx, k, j)),
                            (cj[0] - L / 2, cj[1] - hh / 2, L, hh), ang)
            _made(ctx, S, rng, lines, k=k, verb=verb, tier=tier if j == j0 else None, hand=None,
                  pen=float(rng.choice([0.25, 0.3, 0.35])), step=step, walk_it=False, call=False, reg="specimen")
            d = f"specimen {name}"
        elif form == "beads":      # round knots, a few heavy: masses as beads, never capsules
            kz = float(rng.uniform(5, 15))
            h = str(rng.choice(KNOT_HANDS))
            lines = _voice(ctx, {"id": "hand", "hand": h, "length": float(rng.uniform(0.8, 1.8))},
                           _box_at(cj, kz), _seed(ctx, k, j))
            lines = fit_box(lines, _box_at(c + rng.normal(0, 0.16 * size, 2), kz), ang)
            pen = float(rng.choice([0.3, 0.6, 0.9, 1.3]))
            for l in lines:
                for q in clip_ragged(resample(l, 0.25), S.inner, rng):
                    S.add(q, pen=pen, ink="black", role="made", reg="bead", move=k, tier="tiny" if j == j0 else None)
            d = f"beads {h}"
        else:                      # found: windows of the river at different zooms piled into one place
            zoom = int(np.clip(T["river_zoom"] * math.exp(rng.normal(0, 0.8)), 250, 4000))
            spec = {"id": "oehlen_found_river", "tile": "SB19", "rank": 0, "start": float(rng.uniform(0, 0.9)),
                    "span_w": zoom, "angle": 0.0, "stems": "grwl_far_sb19"}
            L = sz * float(rng.uniform(0.9, 1.6))
            hh = L * float(rng.uniform(0.15, 0.4))
            lines = fit_rot(_voice(ctx, spec, (0, 0, L, hh), _seed(ctx, k, j)),
                            (cj[0] - L / 2, cj[1] - hh / 2, L, hh), ang)
            for l in lines:
                for q in clip_ragged(l, S.inner, rng):
                    S.add(q, pen=0.3, ink=T["found_ink"], role="found", reg="river", move=k,
                          tier=tier if j == j0 else None)
            d = f"river window zoom {zoom}"
        descs.append(d)
    return "; ".join(sorted(set(descs))[:3])


def act_seed(ctx, S, per, T, rng, k, *, step, **_):
    c = _core_point(rng, S, per, T)
    size = float(math.exp(rng.uniform(math.log(24), math.log(110))))
    c = inside(S, c, size * 1.2, size * 1.2)
    form = str(rng.choice(CORE_FORMS, p=T["forms"]))
    nl = {"hands": int(np.clip(round(rng.normal(2 + 6 * T["appetite"], 1.2)), 2, 9)),
          "coil": int(rng.integers(1, 3)), "specimens": int(rng.integers(2, 6)),
          "beads": int(rng.integers(3, 9)), "found": int(rng.integers(2, 5))}[form]
    nl = int(round(nl * (1 + 1.5 * _hunger(S, per, T))))
    desc = core_form(ctx, S, T, rng, k, c, size, form, nl, step=step, verb="seed")
    S.cores.append({"xy": (float(c[0]), float(c[1])), "r": size / 2, "form": form})
    return f"a core ({form}) of {nl}, {size:.0f} mm at {_xy(c)} ({desc})"


def act_thicken(ctx, S, per, T, rng, k, *, step, **_):
    core_ = per["core"]
    cc = np.array(core_["xy"])
    near = min(S.cores, key=lambda q: math.hypot(*(np.array(q["xy"]) - cc))) if S.cores else None
    form = near["form"] if (near is not None and rng.random() < 0.7) else str(rng.choice(CORE_FORMS, p=T["forms"]))
    c = cc + rng.normal(0, 0.35 * core_["r"], 2)
    size = float(np.clip(core_["r"] * rng.uniform(1.0, 2.6), 14, 160))
    c = inside(S, c, size, size, slack=0.2 * size)
    nl = int(rng.integers(1, 4)) if form != "beads" else int(rng.integers(2, 6))
    nl = int(round(nl * (1 + 1.5 * _hunger(S, per, T))))
    desc = core_form(ctx, S, T, rng, k, c, size, form, nl, step=step, verb="thicken")
    return f"{nl} more ({form}) into the core at {_xy(core_['xy'])} (core r {core_['r']:.0f} mm; {desc})"


def _edge_hits(S, A, d):
    """Where the ray A + t·d leaves the inner frame (t > 0)."""
    x0, y0, x1, y1 = S.inner
    ts = []
    for ax, lo, hi in ((0, x0, x1), (1, y0, y1)):
        if abs(d[ax]) > 1e-9:
            for b in (lo, hi):
                t = (b - A[ax]) / d[ax]
                if t > 0:
                    q = A + t * d
                    if x0 - 1e-6 <= q[0] <= x1 + 1e-6 and y0 - 1e-6 <= q[1] <= y1 + 1e-6:
                        ts.append(t)
    return min(ts) if ts else 0.0


def act_traverse(ctx, S, per, T, rng, k, *, step, **_):
    W, H = S.frame
    through = np.array(per["core"]["xy"]) if per["core"] is not None else np.array([W, H]) * rng.uniform(0.3, 0.7, 2)
    through = inside(S, through + rng.normal(0, 0.15 * min(W, H), 2), 20.0, 20.0)
    long_ax = 0.0 if W >= H else 90.0
    th = math.radians(long_ax + float(rng.normal(0, 22)) + (180.0 if rng.random() < 0.5 else 0.0))
    d = np.array([math.cos(th), math.sin(th)])
    t1, t0 = _edge_hits(S, through, d), _edge_hits(S, through, -d)
    # exits: past the edge (cut ragged) or stopping in the air
    A = through - d * (t0 + (12.0 if rng.random() < 0.6 else -float(rng.uniform(5, 0.4 * t0 + 6))))
    B = through + d * (t1 + (12.0 if rng.random() < 0.6 else -float(rng.uniform(5, 0.4 * t1 + 6))))
    player = pick_player(rng, T)
    span = float(np.linalg.norm(B - A))
    lines, h, desc = player_lines(ctx, player, T, rng, k, 0, (0, 0, span, span * 0.4),
                                  length=float(rng.uniform(4, 9)) if player == "hand" else None)
    lines = place_along(lines, A, B, max_half=float(rng.uniform(0.12, 0.4)) * min(W, H))
    pen = float(rng.choice([0.25, 0.3, 0.5, 0.8, 1.0]))
    _made(ctx, S, rng, lines, k=k, verb="traverse", tier="large", hand=h, pen=pen, step=step, bold=max(pen, 0.9))
    return f"traverse: {desc}, {span:.0f} mm through {_xy(through)}, pen {pen}"


def act_intrude(ctx, S, per, T, rng, k, *, step, heavy, **_):
    """T3: heavy, geometric, at the edge of the core, cutting across it, from the side of the blank."""
    core_ = per["core"]
    E = core_["edge"]
    cc = np.array(core_["xy"])
    bl = np.array(per["blank"]["xy"])
    if len(E) == 0:
        E = cc[None, :] + rng.normal(0, core_["r"], (8, 2))
    tob = bl - cc
    tob = tob / max(float(np.linalg.norm(tob)), 1e-9)
    sc = [2.0 * float(np.dot((e - cc) / max(float(np.linalg.norm(e - cc)), 1e-9), tob)) + float(rng.normal(0, 0.7))
          for e in E]
    p = np.asarray(_softpick(rng, list(E), sc, 0.7), float)
    inward = cc - p
    inward /= max(float(np.linalg.norm(inward)), 1e-9)
    a = math.atan2(inward[1], inward[0]) + math.radians(float(rng.choice([-1, 1])) * float(rng.uniform(25, 75)))
    d = np.array([math.cos(a), math.sin(a)])
    L = float(np.clip(core_["r"] * rng.uniform(0.6, 1.6), 18.0, 140.0))
    u = float(rng.uniform(0.3, 0.6))
    A = p - d * L * u
    B = p + d * L * (1 - u)
    shape = str(rng.choice(["bar", "bar", "ell", "dashes", "knot"]))
    pen = float(rng.uniform(*heavy))
    width = pen * float(rng.choice([1.0, 1.0, 2.2, 3.5]))
    paths = []
    if shape == "bar":
        paths = [np.array([A, B])]
    elif shape == "ell":
        bend = math.radians(float(rng.choice([-1, 1])) * float(rng.uniform(70, 115)))
        L2 = L * float(rng.uniform(0.25, 0.6))
        d2 = np.array([math.cos(a + bend), math.sin(a + bend)])
        paths = [np.array([A, B, B + d2 * L2])]
    elif shape == "dashes":
        nrm = np.array([-d[1], d[0]])
        g = float(rng.uniform(4, 10))
        Ld = L * float(rng.uniform(0.2, 0.35))
        for s in (-0.5, 0.5):
            m = p + nrm * g * s + d * float(rng.normal(0, 3))
            paths.append(np.array([m - d * Ld / 2, m + d * Ld / 2]))
        width = pen
    else:  # a heavy knot at the core's edge: round, a bead, not a capsule
        sz = float(rng.uniform(7, 16))
        h = str(rng.choice(KNOT_HANDS))
        lines = _voice(ctx, {"id": "hand", "hand": h, "length": float(rng.uniform(0.8, 1.8))}, _box_at(p, sz),
                       _seed(ctx, k, 1))
        lines = fit_box(lines, _box_at(p, sz), float(rng.uniform(0, 360)))
        for l in lines:
            for q in clip_ragged(resample(l, 0.25), S.inner, rng):
                S.add(q, pen=pen, ink="black", role="heavy", reg="knot", move=k, tier="tiny")
        return f"heavy knot ({h}, {sz:.0f} mm, pen {pen:.1f}) at the core's edge {_xy(p)}, the blank side"
    for path in paths:
        q = offset_passes(resample(path, 0.5), width, pen)
        for qq in clip_ragged(q, S.inner, rng, pull=(0.0, 0.01)):
            S.add(qq, pen=pen, ink="black", role="heavy", reg=shape, move=k, tier=_tier_of(L))
    ang = (math.degrees(a) + 360) % 360
    return (f"heavy {shape} {L:.0f} mm × {width:.1f} mm (pen {pen:.1f}) at the core's edge {_xy(p)}, "
            f"cutting in at {ang:.0f}° from the blank side")


def act_counterweight(ctx, S, per, T, rng, k, *, step, heavy, **_):
    W, H = S.frame
    core_ = per["core"]
    cc = np.array(core_["xy"])
    cands = _rand_points(rng, S, 50)
    sc = []
    for c in cands:
        dist = math.hypot(*(c - cc))
        s = 0.03 * dist + 0.02 * math.hypot(c[0] - W / 2, c[1] - H / 2)       # away, and not centred
        mirror = 2 * np.array([W / 2, H / 2]) - cc                            # not the point-mirror (symmetry)
        s -= 3.0 * math.exp(-(math.hypot(*(c - mirror)) / 30.0) ** 2)
        if in_reserve(S, c, 8.0):
            s -= 20.0
        sc.append(s + float(rng.normal(0, 0.5)))
    c = np.asarray(_softpick(rng, cands, sc, 1.0), float)
    # another scale than the core's
    size = float(np.clip(core_["r"] * 2 * math.exp(rng.choice([-1, 1]) * rng.uniform(0.5, 1.2)), 10.0, 120.0))
    c = inside(S, c, size * 1.2, size * 1.2)
    tier = _tier_of(size)
    form = str(rng.choice(["knot", "knot", "specimen", "sign", "lines"]))
    if form == "specimen":
        return act_ladder(ctx, S, per, T, rng, k, step=step, at=c, size=size, form="specimen") + " (counterweight)"
    if form == "sign":
        return act_sign(ctx, S, per, T, rng, k, step=step, at=c, size=size) + " (counterweight)"
    nl = int(rng.integers(2, 6)) if form == "knot" else int(rng.integers(1, 3))
    for j in range(nl):
        h = str(rng.choice(KNOT_HANDS if form == "knot" else T["hands"]))
        L = float(rng.uniform(1.0, 2.5)) if form == "knot" else float(rng.uniform(2, 5))
        lines = _voice(ctx, {"id": "hand", "hand": h, "length": L}, _box_at(c, size), _seed(ctx, k, j))
        lines = fit_box(lines, _box_at(c + rng.normal(0, 0.12 * size, 2), size * float(rng.uniform(0.6, 1.1))),
                        float(rng.uniform(0, 360)))
        pen = _pen_for(rng, tier) if j else float(rng.choice([0.3, 0.5, 0.9, 1.4]))
        _made(ctx, S, rng, lines, k=k, verb="counterweight", tier=tier if j == 0 else None, hand=h, pen=pen,
              step=step, walk_it=False)
    return f"counterweight: {nl}-line {form}, {size:.0f} mm at {_xy(c)} against the core at {_xy(cc)}"


def act_cover(ctx, S, per, T, rng, k, *, step, **_):
    core_ = per["core"]
    cc = np.array(core_["xy"])
    off = rng.normal(0, 1, 2)
    off = off / max(float(np.linalg.norm(off)), 1e-9) * core_["r"] * float(rng.uniform(0.3, 0.9))
    c = cc + off
    w = float(np.clip(core_["r"] * rng.uniform(0.5, 1.3), 12, 110))
    h = float(np.clip(w * math.exp(rng.normal(0, 0.6)), 10, 140))
    mode = "tint" if rng.random() < 0.25 else "cut"
    poly = cover_polygon(ctx.rng("cover", k), c, w, h, "torn", 14.0)
    lines = [d["pts"] for d in S.lines]
    pieces = split_by_covers(lines, [poly], 6.0, mode)
    old = S.lines
    S.lines = []
    for li, q, tinted in pieces:
        d = dict(old[li])
        from scipy.spatial import cKDTree  # noqa: PLC0415
        idx = cKDTree(d["pts"]).query(q)[1]
        d["pts"] = np.asarray(q, float)
        d["pens"] = d["pens"][idx]
        d["codes"] = d["codes"][idx]
        if tinted:
            d["ink"] = T["second_ink"] if d["role"] != "found" else "green-400"
            d["pens"] = np.minimum(d["pens"], 0.5)
        S.lines.append(d)
    from shapely import contains_xy  # noqa: PLC0415
    from shapely.geometry import Polygon  # noqa: PLC0415
    for q in S.calls:          # an end under a cut cover is gone
        if mode == "cut" and contains_xy(Polygon(poly), q["xy"][0], q["xy"][1]):
            q["used"] = True
    S.covers.append({"poly": poly, "xy": _xy(c), "crossed": False, "mode": mode})
    return f"torn {mode} cover {w:.0f}×{h:.0f} mm on the core's side at {_xy(c)}; {len(old)}→{len(S.lines)} pieces"


def act_cross(ctx, S, per, T, rng, k, *, step, **_):
    cv = next(c for c in S.covers if not c["crossed"])
    poly = cv["poly"]
    c = poly.mean(axis=0)
    ext = float(np.max(np.ptp(poly, axis=0)))
    a = float(rng.uniform(0, math.pi))
    d = np.array([math.cos(a), math.sin(a)])
    L = ext * float(rng.uniform(1.6, 3.5))
    A, B = c - d * L / 2, c + d * L / 2
    player = pick_player(rng, T, ("hand", "belt", "gmorph", "free", "sweep"))
    lines, h, desc = player_lines(ctx, player, T, rng, k, 0, (0, 0, L, L * 0.4),
                                  length=float(rng.uniform(2, 5)) if player == "hand" else None)
    lines = place_along(lines, A, B, max_half=ext * 0.4)
    pen = float(rng.choice([0.3, 0.5, 0.9]))
    _made(ctx, S, rng, lines, k=k, verb="cross", tier=_tier_of(L), hand=h, pen=pen, step=step, walk_it=False)
    cv["crossed"] = True
    return f"crosses the cover at {cv['xy']} as if it were not there: {desc}, {L:.0f} mm"


def act_answer(ctx, S, per, T, rng, k, *, step, **_):
    open_calls = [q for q in S.calls if not q["used"]]
    q = open_calls[int(rng.integers(len(open_calls)))] if rng.random() < 0.5 else open_calls[-1]
    q["used"] = True
    size = float(math.exp(rng.uniform(math.log(20), math.log(150))))
    hand = q["hand"] if (q["hand"] and q["hand"] in HANDS and rng.random() < 0.4) else str(rng.choice(T["hands"]))
    lines = _voice(ctx, {"id": "hand", "hand": hand, "length": float(rng.uniform(1.5, 5))}, (0, 0, size, size),
                   _seed(ctx, k, 0))
    if not lines:
        return "answer: nothing grew"
    l = start_at(lines[0], q["xy"], q["head"] + float(rng.normal(0, 0.35)), size)
    _made(ctx, S, rng, [l], k=k, verb="answer", tier=_tier_of(size), hand=hand, pen=_pen_for(rng, _tier_of(size)),
          step=step, bold=0.9)
    return f"answers the end at {_xy(q['xy'])} with {hand}, {size:.0f} mm"


def act_trail(ctx, S, per, T, rng, k, *, step, **_):
    core_ = per["core"]
    cc = np.array(core_["xy"])
    bl = np.array(per["blank"]["xy"])
    tob = bl - cc
    a = math.atan2(tob[1], tob[0]) + float(rng.normal(0, 0.5))
    d = np.array([math.cos(a), math.sin(a)])
    A = cc + d * core_["r"] * float(rng.uniform(0.4, 1.0))
    t_edge = _edge_hits(S, A, d)
    to_edge = rng.random() < 0.55
    L = t_edge + 15.0 if to_edge else t_edge * float(rng.uniform(0.35, 0.85))
    L = max(L, 25.0)
    B = A + d * L
    player = pick_player(rng, T, ("hand", "belt", "free", "gmorph", "sweep"))
    lines, h, desc = player_lines(ctx, player, T, rng, k, 0, (0, 0, L, L * 0.35),
                                  length=float(rng.uniform(1.5, 4)) if player == "hand" else None)
    lines = place_along(lines, A, B, max_half=float(rng.uniform(0.08, 0.3)) * L)
    pen = float(rng.choice([0.25, 0.3, 0.3, 0.5]))
    _made(ctx, S, rng, lines, k=k, verb="trail", tier=_tier_of(L), hand=h, pen=pen, step=step, walk_it=False)
    return (f"trails off from the core into the blank: {desc}, {L:.0f} mm, "
            f"{'to the edge' if to_edge else 'stops in the air'}")


def act_ladder(ctx, S, per, T, rng, k, *, step, at=None, size=None, form=None, **_):
    W, H = S.frame
    missing = [t for t in TIERS if S.tiers[t] == 0]
    tier = str(rng.choice(missing)) if (missing and form is None) else (_tier_of(size) if size else "tiny")
    if tier == "large" and form is None:
        return act_traverse(ctx, S, per, T, rng, k, step=step)
    if at is None:
        cands = _rand_points(rng, S, 30)
        sc = [(0.0 if not in_reserve(S, c) else -20.0) + float(rng.normal(0, 1)) +
              (0.02 * -math.hypot(*(c - np.array(per["core"]["xy"]))) if per["core"] and rng.random() < 0.5 else 0)
              for c in cands]
        at = np.asarray(_softpick(rng, cands, sc), float)
    form = form or str(rng.choice(["specimen", "specimen", "river"]))
    ang = float(rng.normal(0, 10)) if rng.random() < 0.7 else float(rng.uniform(0, 180))
    if form == "specimen":
        name = str(rng.choice(list(SPECIMENS)))
        L = float(size if size else rng.uniform(45, 120)) * (1.0 if tier != "tiny" else 1.0)
        L = float(np.clip(L * 1.8, 60, 0.9 * max(W, H)))
        h = max(L * float(rng.uniform(0.07, 0.16)), 6.0)
        a_ = math.radians(ang)
        at = inside(S, at, abs(L * math.cos(a_)) + abs(h * math.sin(a_)) + 4, abs(L * math.sin(a_)) +
                    abs(h * math.cos(a_)) + 4)
        spec = {"id": "morph_handover", "hands": ["meander69", "fly_open"], "order": "bend,turn,corner", "rows": 1,
                "R_mm": max(85.0 * L / 290.0, 10.0), "band": max(14.0 * L / 290.0, 2.5), "ease": 1.3, "run": 4.0,
                "windows": SPECIMENS[name], "max_mm": 4 * L, "K": 5}
        lines = _voice(ctx, spec, (0, 0, L, h), _seed(ctx, k, 0))
        lines = fit_rot(lines, (at[0] - L / 2, at[1] - h / 2, L, h), ang)
        _made(ctx, S, rng, lines, k=k, verb="ladder", tier=_tier_of(h * 2), hand=None, pen=0.3, step=step,
              walk_it=False, call=False, reg="specimen")
        return f"tiny matter: handover specimen '{name}', {L:.0f}×{h:.0f} mm at {_xy(at)}, {ang:+.0f}°"
    L = float(rng.uniform(25, 70))
    h = L * float(rng.uniform(0.15, 0.3))
    a_ = math.radians(ang)
    at = inside(S, at, abs(L * math.cos(a_)) + abs(h * math.sin(a_)) + 4, abs(L * math.sin(a_)) +
                abs(h * math.cos(a_)) + 4)
    spec = {"id": "oehlen_found_river", "tile": "SB19", "rank": 0, "start": float(rng.uniform(0, 0.9)),
            "span_w": int(rng.uniform(1600, 4000)), "angle": 0.0, "stems": "grwl_far_sb19"}
    lines = fit_rot(_voice(ctx, spec, (0, 0, L, h), _seed(ctx, k, 0)), (at[0] - L / 2, at[1] - h / 2, L, h), ang)
    for l in lines:
        for q in clip_ragged(l, S.inner, rng):
            S.add(q, pen=0.3, ink=T["found_ink"], role="found", reg="river_thumb", move=k, tier="tiny")
    return f"tiny matter: the river shrunk to a thumb, {L:.0f} mm at {_xy(at)}"


def act_sign(ctx, S, per, T, rng, k, *, step, at=None, size=None, **_):
    W, H = S.frame
    if at is None:
        cands = _rand_points(rng, S, 30)
        sc = [0.03 * _blank_at(per, c) * float(rng.choice([1, -1])) + float(rng.normal(0, 0.8)) -
              (20.0 if in_reserve(S, c, 0.3 * 60.0) else 0.0) for c in cands]
        at = np.asarray(_softpick(rng, cands, sc), float)
    size = max(float(size if size else math.exp(rng.uniform(math.log(35), math.log(140)))), 40.0)
    at = inside(S, at, size * 1.15, size * 1.15)
    trail = str(rng.choice(TRAILS))
    host = str(rng.choice(["rfoot", "lfoot", "rhand", "lhand", "head"]))
    others = [x for x in ("head", "rhand", "lhand", "rfoot", "lfoot") if x != host]
    w_ = str(rng.choice(others)) if rng.random() < 0.5 else "none"
    spec = {"id": "revisit_glyph", "trail": trail, "host": host, "with_": w_, "layout": "body",
            "seconds": float(rng.uniform(20, 60)), "t0": 0.0, "max_glyphs": int(rng.integers(3, 8))}
    try:
        marks = _voice_marks(ctx, spec, _box_at(at, size), _seed(ctx, k, 0))
    except Exception as e:  # noqa: BLE001 — a trail too short for its window simply plays nothing
        return f"limb sign refused ({type(e).__name__})"
    if not marks:
        return "limb sign: nothing"
    ang = float(rng.normal(0, 20))
    lines = fit_box([m.points for m in marks], _box_at(at, size), ang)
    for mi, (m, l) in enumerate(zip(marks, lines)):
        r = np.asarray(m["r"])
        pens = np.where(r > 1.05, float(rng.choice([0.9, 1.2])), 0.3)
        ink = "black" if mi == 0 else T["second_ink"]
        pts = np.asarray(l, float)
        for q in clip_ragged(pts, S.inner, rng):
            from scipy.spatial import cKDTree  # noqa: PLC0415
            idx = cKDTree(pts).query(q)[1]
            S.add(q, pen=0.3, pens=pens[idx], ink=ink, role="made", reg="limb", move=k,
                  tier=_tier_of(size) if mi == 0 else None)
    return f"limb sign: {trail} {host}{' + ' + w_ if w_ != 'none' else ''}, {size:.0f} mm at {_xy(at)}"


def act_reserve(ctx, S, per, T, rng, k, *, step, **_):
    W, H = S.frame
    if per["total"] <= 0:
        # an empty sheet: reserve a side, a decision before any ink
        side = int(rng.integers(4))
        r = float(rng.uniform(0.28, 0.45)) * min(W, H)
        xy = [(W * rng.uniform(0.25, 0.75), H - r * 0.6), (W - r * 0.6, H * rng.uniform(0.3, 0.7)),
              (W * rng.uniform(0.25, 0.75), r * 0.6), (r * 0.6, H * rng.uniform(0.3, 0.7))][side]
    else:
        xy, r = per["blank"]["xy"], per["blank"]["r"] * float(rng.uniform(0.75, 1.0))
    S.reserve = {"xy": [float(xy[0]), float(xy[1])], "r": float(r)}
    return f"reserves the blank at {_xy(xy)}, r {r:.0f} mm (dense moves keep out; lines may cross)"


def act_guest(ctx, S, per, T, rng, k, *, parts, step, **_):
    gp = parts[1 + int(rng.integers(len(parts) - 1))]
    c = _core_point(rng, S, per, T)
    size = float(math.exp(rng.uniform(math.log(25), math.log(180))))
    c = inside(S, c, size, size)
    q = core.Part(gp.index, gp.spec, gp.renderer, ctx.frame, ctx.sheet_seed + 1009 * (k + 1), ctx.run, ctx.box)
    lines = [np.asarray(m.points, float) for m in q.run(_box_at(c, size)) if len(m.points) >= 2]
    if not lines:
        return "guest: nothing"
    lines = fit_box(lines, _box_at(c, size), float(rng.uniform(0, 360)))
    _made(ctx, S, rng, lines, k=k, verb="guest", tier=_tier_of(size), hand=None, pen=_pen_for(rng, _tier_of(size)),
          step=step)
    return f"guest part {gp.index} ({gp.spec['voice']['id']}), {size:.0f} mm at {_xy(c)}"


ACTS = {"found": act_found, "seed": act_seed, "thicken": act_thicken, "traverse": act_traverse,
        "intrude": act_intrude, "counterweight": act_counterweight, "cover": act_cover, "cross": act_cross,
        "answer": act_answer, "trail": act_trail, "ladder": act_ladder, "sign": act_sign, "reserve": act_reserve,
        "guest": act_guest}


def log_lines(sheet) -> list[str]:
    """The move log in short form (for write-ups and contact labels)."""
    m = next((mk for mk in sheet.marks if "cimpro" in mk.meta), None)
    if m is None:
        return []
    out = []
    for e in m.meta["cimpro"]["log"]:
        out.append(f"{e['k']:>2} {e['verb']:<13} {e.get('what', e['why'])}")
    return out
