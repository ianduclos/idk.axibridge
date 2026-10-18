"""Round 14, thread b3 `cgram`: compositions as a grammar.

A composition is a SENTENCE: a sequence of compositional moves, each acting on
the sheet so far. The moves come from the lead's Oehlen note
(results/oehlen-composition-2026-10-18.md: "reserve · seed · traverse ·
intrude · contain · spill · cover · cross the cover · contaminate · trail off ·
stop in the air · counterweight · repeat") plus the plan's (paste, answer,
zoom, morph). The players are the techniques Ian kept (found ground's ride,
contagion's catch, found_play's answers, mutual's soup, passage, the handover
specimens, accrue's seed-3966 free hand, belt / gmorph morphing, limb signs).

The arranger `cgram` only reads a sentence and plays it. The sentence is made
by `sample_sentence(seed)`, a sampler with a per-sheet TEMPERAMENT: sentence
length (3 … ~44 moves), move weights (a sparse Dirichlet draw, so each sheet
has a dominant few moves), density dial (extremes allowed), core and blank,
dominant players, intruder yes/no, how strictly the habitual order (found →
structure → hand → accents) is kept. Sampled, never scored or bred
(GESTURE-BANK-PROCESS §7). `sample_sentence(seed, uniform=True)` is the
control: one flat temperament for every sheet.

Sentence syntax (plain text, the recipe's `sentence` param):

    move key=value key=value ; move key=value ...

values are numbers, names, or `@k` (a reference to move k, 0-based). Moves:

    paste    src=<player> x y w h rot [zoom at crop edge]  found matter, thin, cut to its pasted rectangle
    reserve  x y w h                  a decided blank: later placements are pushed out of it
    contain  x y w h rot drawn        a frame inside the frame
    seed     p x y r n len pen play [in]   a core: n lines of one player, overlapping
    line     p x y w h rot len pen play [in]  one free line
    morph    p x y w h rot len pen    one line whose gesture type changes (gmorph, belt, passage, waves, free)
    soup     x y w h                  mutual's dense call and response, as a block
    traverse p x y ang len pen play   one long line through (x, y), edge to edge
    spill    from=@contain p len pen  a line that starts inside a container and leaves to the margin
    cover    x y w h rot shape mode [at=@k]   cut (or tint) everything so far inside a torn shape
    cross    over=@cover p len pen    a line through a cover as if it were not there
    answer   to=@k p len pen          grows out of k's end (its call), then goes its own way
    trail    on=@k len                k's end trails off, thinning, into blank and to an edge
    stop     on=@k at                 k stops in the air (cut where it is farthest from other ink)
    contaminate on=@k with=stair|rule|river|coil at len   a stretch of k borrows another register
    zoom     of=@k at len s x y rot   a passage of k redrawn at another scale elsewhere
    repeat   of=@k x y s [rot]        k's move again, elsewhere, at another scale: a rhyme
    counter  of=@k p s                a smaller density opposite core k
    intrude  kind=bar|el|knot|dashes|sign at=@k ang len pen   a heavy foreign mark at a core's edge

Players are the recipe's parts, named by their `label` (see `PLAYERS`), so
the vocabulary is the same for every sheet of a series. Each use of a player
grows a fresh line (seed = recipe seed + an index from the move number).
Marks carry meta `of_role` (found / made / heavy / edge), `ink`, `pen`,
`move`; ink with `oehlen_found_ink`, preview with
`arrangers_oehlen_found.save`. The arranger's log, `marks[0].meta["cgram"]`,
lists every move with the ink it touched (mm) so a move that did nothing
shows up.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from .arrangers_contagion import contagion_walk, gen_meander, river_grammar
from .arrangers_found_play import chart_grammar, chart_needles, hand_gen
from .arrangers_oehlen_found import (FLEXOKI, Ground, arclen, bridge, cover_polygon, negotiate, rect_polygon,
                                     resample, rotate, tangents)
from .arrangers_contagion import Carrier
from .core import Mark, P, Part, _module_spec, arranger, fitted, voice

# ---------------------------------------------------------------------------
# the vocabulary (players) — one recipe part each, named by label
# ---------------------------------------------------------------------------

def _spec(k, **v):
    return {"label": k, "voice": v}


PLAYERS = [
    _spec("river", id="oehlen_found_river", tile="SB19", rank=0, start=0.0, span_w=1600, angle=0.0,
          stems="grwl_far_sb19"),
    _spec("chart", id="diagram", chart="kappa", rows=4, label_h=2.2, hands=["trail_miner"], length=6.0),
    _spec("key", id="morph_handover", hands=["meander69", "fly_open"], order="bend,turn,corner", rows=1,
          R_mm=85.0, band=14.0, ease=1.3, run=4.0, windows=[2.0, 2.0, 2.0, 2.0, 2.0, 2.0], max_mm=900.0),
    _spec("waves", id="morph_handover", hands=["meander69", "fly_open"], order="bend,turn,corner", rows=1,
          R_mm=85.0, band=14.0, ease=1.3, run=4.0, windows=[-1.0, -1.0, 2.0, 2.0, -1.0, -1.0], max_mm=900.0),
    _spec("coiled", id="morph_handover", hands=["meander69", "fly_open"], order="bend,turn,corner", rows=1,
          R_mm=85.0, band=14.0, ease=1.3, run=4.0, windows=[-1.0, -1.0, -1.0, -1.0, 2.0, 2.0], max_mm=900.0),
    _spec("thrusting", id="hand", hand="dance_thrusting", length=3.0, joins="smooth"),
    _spec("bend", id="hand", hand="river_bend", length=3.0, joins="smooth"),
    _spec("miner", id="hand", hand="trail_miner", length=3.0, joins="smooth"),
    _spec("mantis", id="hand", hand="mime_mantis", length=3.0, joins="smooth"),
    _spec("fly", id="hand", hand="fly_fru", length=3.0, joins="smooth"),
    _spec("hokusai", id="hand", hand="hokusai", length=3.0, joins="smooth"),
    _spec("madeline", id="hand", hand="dancer_madeline", length=3.0, joins="smooth"),
    _spec("free", id="cgram_free", free_seed=3966),
    _spec("passage", id="passage", opening="none", rows=1, max_mm=900.0),
    _spec("gmorph", id="gmorph", hand="river_belt", length=6.0, turn=[0.0, 0.2, 0.5, 0.9, 1.0, 0.3],
          gain=[0.0, 1.0, 0.6, 2.6, 1.0, 1.2]),
    _spec("belt", id="belt", hand="river_belt", length=6.0, gain=1.2, gain_end=3.2),
    _spec("signs", id="revisit_glyph", trail="particles", host="rfoot", seconds=40.0),
    _spec("loops", id="river_loops", mode="knot", n=5),
    _spec("soup", id="mutual", T=150),
]
HANDS = ("thrusting", "bend", "miner", "mantis", "fly", "hokusai", "madeline")
MORPHS = ("gmorph", "belt", "passage", "waves", "coiled", "free")
FOUND = ("river", "chart", "key", "waves")
LINEISH = HANDS + ("free", "signs", "loops", "waves", "key", "coiled", "passage", "gmorph", "belt")


def _len_override(vid: str, length: float) -> dict:
    """A move's `len` (a scale-free 'how much line') as the voice's own param."""
    if vid in ("hand", "gmorph", "belt"):
        return {"length": float(np.clip(length, 0.4, 12.0))}
    if vid in ("morph_handover", "passage"):
        return {"max_mm": float(np.clip(length * 180.0, 120.0, 3000.0))}
    if vid == "revisit_glyph":
        return {"seconds": float(np.clip(length * 12.0, 8.0, 60.0))}
    if vid == "river_loops":
        return {"length": float(np.clip(length, 1.0, 9.0)), "n": int(np.clip(round(length * 1.5), 2, 10))}
    return {}


@voice("cgram_free", params=[P("free_seed", "int", 3966, "accrue seed; 3966 is Ian's kept free hand",
                               min=0, max=2147483647)],
       doc="accrue's seed-3966 free hand (no habit forms), exact geometry, fitted into the box")
def cgram_free(ctx, *, free_seed):
    from .voices_passage import free_opening  # noqa: PLC0415
    g = ctx.use("hand", "river_belt")
    pts, info = free_opening(g, (0.0, 0.0, 285.0, 94.0), free_seed)
    return fitted([pts], ctx.box, metas=[{"voices": ["river_belt"], "free": {"seed": info["seed"],
                                                                               "length_mm": info["length_mm"]}}])


# ---------------------------------------------------------------------------
# sentences
# ---------------------------------------------------------------------------

MOVES = ("paste", "reserve", "contain", "seed", "line", "morph", "soup", "traverse", "spill", "cover", "cross",
         "answer", "trail", "stop", "contaminate", "zoom", "repeat", "counter", "intrude")
# the habitual order (note T5): found matter, then structure, then the free hand, then accents
PHASE = {"reserve": 0, "paste": 0, "contain": 0, "soup": 1, "traverse": 1, "morph": 1, "seed": 1, "line": 2,
         "counter": 2, "answer": 2, "spill": 2, "repeat": 2, "zoom": 2, "contaminate": 2, "cover": 3,
         "cross": 3, "intrude": 3, "trail": 3, "stop": 3}


def _val(v: str):
    if v.startswith("@"):
        return ("ref", int(v[1:]))
    try:
        f = float(v)
    except ValueError:
        return v
    return int(f) if f.is_integer() and "." not in v else f


def parse(sentence: str) -> list[dict]:
    """'move k=v k=v ; move …' → [{'move': name, args…}]. Raises ValueError on an unknown move."""
    out = []
    for chunk in sentence.split(";"):
        toks = chunk.split()
        if not toks:
            continue
        if toks[0] not in MOVES:
            raise ValueError(f"cgram: unknown move {toks[0]!r}; moves are {MOVES}")
        d = {"move": toks[0]}
        for t in toks[1:]:
            if "=" not in t:
                raise ValueError(f"cgram: argument {t!r} of {toks[0]} is not key=value")
            k, v = t.split("=", 1)
            d[k] = _val(v)
        out.append(d)
    return out


def _fmt(v) -> str:
    if isinstance(v, tuple) and v and v[0] == "ref":
        return f"@{v[1]}"
    if isinstance(v, float):
        s = f"{v:.3f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-0") else "0"
    return str(v)


def speak(moves: list[dict]) -> str:
    """The inverse of `parse`."""
    return " ; ".join(" ".join([m["move"]] + [f"{k}={_fmt(v)}" for k, v in m.items() if k != "move"]) for m in moves)


# ---------------------------------------------------------------------------
# the sheet being composed
# ---------------------------------------------------------------------------

def _L_of(p) -> float:
    return float(arclen(np.asarray(p))[-1]) if len(p) >= 2 else 0.0


def runs_by_mask(pts, poly):
    """Split a polyline into (run, inside) by a polygon, point by point, with the crossing point
    interpolated on the boundary segment. Unlike shapely's intersection, a line that crosses ITSELF is
    never noded into fragments (a dense knot stays one line where it is not cut)."""
    from shapely import contains_xy  # noqa: PLC0415
    from shapely.geometry import LineString, Polygon  # noqa: PLC0415
    p = np.asarray(pts, float)
    if len(p) < 2:
        return []
    P_ = Polygon(poly)
    ins = contains_xy(P_, p[:, 0], p[:, 1])
    cut = np.flatnonzero(ins[1:] != ins[:-1]) + 1
    if not len(cut):
        return [(p, bool(ins[0]))]
    edge = P_.exterior
    out, a = [], 0
    xs = []
    for c in cut:                              # boundary point between p[c-1] and p[c]
        import shapely  # noqa: PLC0415
        xy = shapely.get_coordinates(LineString([p[c - 1], p[c]]).intersection(edge))
        xs.append(np.asarray(xy[0], float) if len(xy) else (p[c - 1] + p[c]) / 2)
    starts = [0] + list(cut)
    ends = list(cut) + [len(p)]
    for i, (a, b) in enumerate(zip(starts, ends)):
        run = p[a:b]
        if i > 0:
            run = np.vstack([xs[i - 1], run])
        if i < len(cut):
            run = np.vstack([run, xs[i]])
        out.append((run, bool(ins[a])))
    return out


def clip_keep(pts, poly, min_stub):
    """The runs of a polyline inside a polygon; a run the boundary shortened below min_stub mm is dropped."""
    L0 = _L_of(pts)
    return [r for r, inside in runs_by_mask(pts, poly) if inside and (_L_of(r) >= min_stub or _L_of(r) >= L0 - 1e-6)]


def cover_split(pts, poly, min_stub, mode):
    """[(piece, tinted)]: cut removes what is inside; tint keeps it, flagged. Pieces the cut shortened below
    min_stub are dropped."""
    out = []
    for r, inside in runs_by_mask(pts, poly):
        if inside:
            if mode == "tint" and _L_of(r) >= min_stub:
                out.append((r, True))
        elif _L_of(r) >= min_stub:
            out.append((r, False))
    return out


class Comp:
    """The sheet so far: elements (polylines with pen, ink, role, move), covers, containers, reserves,
    cores. Every move returns the ink it touched (mm) for the log."""

    def __init__(self, ctx, parts, *, step, found_ink, chart_ink, made_ink, tint_ink, tint_found_ink, min_stub):
        self.ctx = ctx
        self.W, self.H = ctx.frame
        self.box = ctx.box
        self.parts = {p.label: p for p in parts if p.label}
        self.part0 = parts[0].index
        self.step = step
        self.inks = {"found": found_ink, "chart": chart_ink, "made": made_ink, "tint": tint_ink,
                     "tint_found": tint_found_ink}
        self.min_stub = min_stub
        self.el: list[dict] = []
        self.covers: list[tuple] = []           # (poly, mode, move)
        self.containers: dict[int, np.ndarray] = {}
        self.reserves: list[tuple] = []         # (x0, y0, x1, y1) mm
        self.cores: dict[int, tuple] = {}       # move → (centre, radius)
        self.players: dict[int, str] = {}       # move → player label
        self.args: dict[int, dict] = {}
        self.log: list[dict] = []
        self._grammar_cache: dict = {}
        x0, y0, w, h = self.box
        self.sheet_rect = np.array([[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h], [x0, y0]])

    # -- geometry helpers -------------------------------------------------
    def mm(self, x, y):
        return np.array([float(x) * self.W, float(y) * self.H])

    def clamp_pt(self, p, pad=0.0):
        x0, y0, w, h = self.box
        return np.array([min(max(p[0], x0 + pad), x0 + w - pad), min(max(p[1], y0 + pad), y0 + h - pad)])

    def place(self, cx, cy, w, h, avoid=True):
        """A box (x0, y0, w, h) mm centred near (cx, cy) mm, pushed out of the reserves, kept on the sheet."""
        x0, y0, bw, bh = self.box
        w, h = min(w, bw), min(h, bh)
        c = np.array([cx, cy], float)
        if avoid:
            for (a0, b0, a1, b1) in self.reserves:
                for _ in range(6):          # pushed out of the blank; a box too big to fit beside it shrinks
                    lo, hi = c - [w / 2, h / 2], c + [w / 2, h / 2]
                    ov = max(0.0, min(hi[0], a1) - max(lo[0], a0)) * max(0.0, min(hi[1], b1) - max(lo[1], b0))
                    if ov <= 0.1 * w * h:
                        break
                    moves = [(a0 - hi[0], 0.0), (a1 - lo[0], 0.0), (0.0, b0 - hi[1]), (0.0, b1 - lo[1])]
                    moves.sort(key=lambda d: abs(d[0]) + abs(d[1]))
                    done = False
                    for d in moves:
                        cc = c + d
                        if x0 + w / 2 <= cc[0] <= x0 + bw - w / 2 and y0 + h / 2 <= cc[1] <= y0 + bh - h / 2:
                            c = cc
                            self._displaced += 1
                            done = True
                            break
                    if done:
                        break
                    w, h = 0.8 * w, 0.8 * h
        c[0] = min(max(c[0], x0 + w / 2), x0 + bw - w / 2)
        c[1] = min(max(c[1], y0 + h / 2), y0 + bh - h / 2)
        return (c[0] - w / 2, c[1] - h / 2, w, h)

    _displaced = 0

    def ink_len(self) -> float:
        return sum(_L_of(e["pts"]) for e in self.el)

    # -- players ----------------------------------------------------------
    def grow(self, label, box, k, j=0, length=None, extra=None):
        """Fresh marks of player `label` fitted into box (x0, y0, w, h); its seed = recipe seed + an index
        made from (move k, use j) only."""
        if label not in self.parts:
            raise ValueError(f"cgram: no player {label!r}; players: {sorted(self.parts)}")
        src = self.parts[label]
        if label == "free" and box[2] < 150.0:
            # the free hand drawn small reads as cursive writing (§5: never legible): at least 150 mm wide
            c = (box[0] + box[2] / 2, box[1] + box[3] / 2)
            w, h = 150.0, max(box[3], 150.0 * 94.0 / 285.0)
            box = (c[0] - w / 2, c[1] - h / 2, w, h)
        v = dict(src.spec["voice"])
        if length is not None:
            v.update(_len_override(v["id"], length))
        if extra:
            v.update(extra)
        v = _module_spec("voice", v, f"cgram move {k}", self.ctx.run.library)
        spec = {"voice": v, "modulators": []}
        part = Part(1000 + 40 * k + j, spec, src.renderer, self.ctx.frame, self.ctx.sheet_seed, self.ctx.run, box)
        return part.voice(box)

    def lines_of(self, label, box, k, j=0, length=None, extra=None, rot=0.0):
        ms = self.grow(label, box, k, j, length, extra)
        c = np.array([box[0] + box[2] / 2, box[1] + box[3] / 2])
        out = []
        for m in ms:
            p = np.asarray(m.points, float)
            if rot:
                p = rotate(p, c, rot)
            out.append((p, m.meta))
        return out

    # -- elements ---------------------------------------------------------
    def add(self, pts, *, pen, ink, role, k, part=None, clip=True, **meta) -> float:
        pts = np.asarray(pts, float)
        if len(pts) < 2:
            return 0.0
        # a piece the paper edge leaves shorter than 12 mm would be a stray mark at the edge: dropped
        pieces = clip_keep(pts, self.sheet_rect, max(self.min_stub, 12.0)) if clip else [pts]
        tot = 0.0
        for q in pieces:
            if len(q) < 2:
                continue
            self.el.append({"pts": q, "pen": float(pen), "ink": ink, "role": role, "move": k,
                            "part": self.part0 if part is None else part, **meta})
            tot += _L_of(q)
        return tot

    def of_move(self, k, roles=("made",)):
        return [e for e in self.el if e["move"] == k and e["role"] in roles]

    def longest(self, k, roles=("made",)):
        es = self.of_move(k, roles)
        return max(es, key=lambda e: _L_of(e["pts"])) if es else None

    def all_pts(self, exclude=None):
        ps = [resample(e["pts"], 1.0) for e in self.el if e is not exclude and len(e["pts"]) >= 2]
        return np.vstack(ps) if ps else np.empty((0, 2))

    def densest(self, cell=10.0):
        P_ = self.all_pts()
        if not len(P_):
            return self.mm(0.5, 0.5)
        from scipy.ndimage import gaussian_filter  # noqa: PLC0415
        nx, ny = int(self.W // cell) + 1, int(self.H // cell) + 1
        Hh, _, _ = np.histogram2d(P_[:, 0], P_[:, 1], bins=(nx, ny), range=((0, nx * cell), (0, ny * cell)))
        Hh = gaussian_filter(Hh, 1.5)
        i, j = np.unravel_index(int(np.argmax(Hh)), Hh.shape)
        return np.array([(i + 0.5) * cell, (j + 0.5) * cell])

    # -- listening (the techniques that work) --------------------------------
    def grounds(self, made=True):
        found = [e["pts"] for e in self.el if e["role"] == "found" and e.get("ridable", True)]
        out = []
        if found:
            out.append(Ground(found, self.step, tag=1))
        if self.covers:
            out.append(Ground([resample(p, self.step) for p, _, _ in self.covers], self.step, tag=2))
        if made:
            ms = [e["pts"] for e in self.el if e["role"] == "made"]
            if ms:
                out.append(Ground(ms, self.step, tag=3))
        return [g for g in out if g.tree is not None]

    def listen(self, M, play, k, j=0, grow=False):
        """The line M against the sheet so far: 'none' as drawn | 'ride' (found ground: ride, leave at a
        tangent, ignore) | 'catch' (contagion: a contact infects the line with the regime, carried
        away and shed whole). Returns (points, codes)."""
        M = resample(np.asarray(M, float), self.step)
        if play == "none" or len(M) < 8:
            return M, np.zeros(len(M))
        rng = self.ctx.rng("listen", k, j)
        bounds = (self.box[0], self.box[1], self.box[0] + self.box[2], self.box[1] + self.box[3])
        if play == "catch":
            gr, gm_ = self._contagion()
            if gr:
                full = {r: 40.0 for r in gr}
                decay = {r: 60.0 for r in gr}
                try:
                    pts, codes, _ = contagion_walk(
                        M, gr, gm_, rng, step=self.step, capture=5.0, align=0.55, listen=70.0, ignore=40.0,
                        ride=20.0, ride_sd=0.45, min_ride=7.0, ride_gap=0.9, return_mm=30.0, ramp=2.0,
                        max_offset=18.0, catches=4, full=full, decay=decay, tick_linger=1.0, own_mm=6.0,
                        rule_tol=3.5, snap=8.0, tick_pitch=self._tick_pitch, immune_mm=50.0, omega_max=120.0,
                        rule_shared=9.0, regimes=tuple(gr), carry=True)
                    if "plate" in gm_:
                        pts = chart_needles(pts, codes, gm_["plate"])
                    return pts, np.asarray(codes, float)
                except (ValueError, IndexError):
                    pass
            play = "ride"
        gs = self.grounds()
        if not gs:
            return M, np.zeros(len(M))
        pts, tags, _ = negotiate(M, gs, rng, step=self.step, capture=3.5, align=0.6, ride=26.0, ride_sd=0.6,
                                 min_ride=6.0, listen=45.0, ignore=55.0, return_mm=30.0, ramp=2.5, grow=grow,
                                 grow_reach=30.0, max_rides=6, max_offset=18.0, ride_gap=0.9, bounds=bounds)
        return pts, tags

    _tick_pitch = 9.0

    def _contagion(self):
        gr, gm_ = {}, {}
        river = [e["pts"] for e in self.el if e["role"] == "found" and e.get("src") == "river"]
        chart = [e["pts"] for e in self.el if e["role"] == "found" and e.get("src") == "chart"
                 and _L_of(e["pts"]) > 30.0]
        if river:
            key = ("river", len(river), round(sum(_L_of(r) for r in river), 1))
            if key not in self._grammar_cache:
                try:
                    self._grammar_cache[key] = river_grammar(river, axis_mm=10.0, omega_max=120.0)
                except ValueError:
                    self._grammar_cache[key] = None
            if self._grammar_cache[key] is not None:
                gr["river"], gm_["river"] = Ground(river, self.step, tag=1), self._grammar_cache[key]
        if chart:
            try:
                gm_["plate"] = chart_grammar(chart)
                gr["plate"] = Ground(chart, self.step, tag=2)
                self._tick_pitch = gm_["plate"]["pitch_mm"] * 1.5
            except ValueError:
                gm_.pop("plate", None)
        for k, lab in sorted(self.players.items()):
            if lab not in HANDS:
                continue
            e = self.longest(k)
            if e is None:
                continue
            hid = self.parts[lab].spec["voice"]["hand"]
            R = max(_L_of(e["pts"]) / 3.0, 20.0)
            key = f"line{k}"
            gr[key] = Ground([e["pts"]], self.step, tag=3)
            gm_[key] = {"gen": hand_gen(self.ctx.use("hand", hid), R * 0.3, step=0.2, pull=0.2, axis_mm=10.0,
                                        amp_max=7.0), "code": 9, "ride_code": 6, "hand": hid}
        return {k: v for k, v in gr.items() if v.tree is not None}, gm_

    # -- covers -----------------------------------------------------------
    def apply_cover(self, poly, mode) -> float:
        touched = 0.0
        new = []
        for e in self.el:
            if e["role"] == "edge" and e.get("of_cover"):
                new.append(e)
                continue
            pieces = cover_split(e["pts"], poly, self.min_stub, mode)
            L0 = _L_of(e["pts"])
            Lk = 0.0
            for q, tinted in pieces:
                d = dict(e)
                d["pts"] = q
                if tinted:
                    d["ink"] = self.inks["tint_found"] if e["role"] == "found" else self.inks["tint"]
                    d["under_cover"] = True
                    touched += _L_of(q)
                else:
                    Lk += _L_of(q)
                new.append(d)
            if mode == "cut":
                touched += max(L0 - Lk, 0.0)
        self.el = new
        return touched


# ---------------------------------------------------------------------------
# small geometry
# ---------------------------------------------------------------------------

def stretch_between(pts, A, B, max_lat=0.55):
    """The stretch of a line between the extremes of its principal axis, mapped by a similarity so it
    runs from A to B. A lateral extent beyond max_lat × |AB| is pressed in (an affine squeeze)."""
    p = np.asarray(pts, float)
    c = p.mean(axis=0)
    ev = np.linalg.eigh(np.cov((p - c).T))[1][:, -1] if len(p) > 2 else np.array([1.0, 0.0])
    u = (p - c) @ ev
    a, b = int(np.argmin(u)), int(np.argmax(u))
    q = p[min(a, b):max(a, b) + 1]
    if a > b:
        q = q[::-1]
    if len(q) < 4:
        q = p
    A, B = np.asarray(A, float), np.asarray(B, float)
    d0 = q[-1] - q[0]
    L0 = float(np.linalg.norm(d0))
    d1 = B - A
    L1 = float(np.linalg.norm(d1))
    if L0 < 1e-6 or L1 < 1e-6:
        return q - q[0] + A
    ex = d0 / L0
    ey = np.array([-ex[1], ex[0]])
    loc = np.c_[(q - q[0]) @ ex, (q - q[0]) @ ey] / L0
    lat = float(np.max(np.abs(loc[:, 1])))
    if lat > max_lat:
        loc[:, 1] *= max_lat / lat
    fx = d1 / L1
    fy = np.array([-fx[1], fx[0]])
    return A + L1 * (loc[:, :1] * fx + loc[:, 1:2] * fy)


def edge_hit(p, d, box):
    """Where the ray p + t·d (t > 0) leaves the box (x0, y0, w, h)."""
    x0, y0, w, h = box
    ts = []
    for ax, lo, hi in ((0, x0, x0 + w), (1, y0, y0 + h)):
        if abs(d[ax]) > 1e-9:
            for e in (lo, hi):
                t = (e - p[ax]) / d[ax]
                if t > 1e-6:
                    q = p + t * d
                    if x0 - 1e-6 <= q[0] <= x0 + w + 1e-6 and y0 - 1e-6 <= q[1] <= y0 + h + 1e-6:
                        ts.append(t)
    return p + (min(ts) if ts else 0.0) * d


def join_lines(a, b, step, ramp=3.0):
    """a then b, joined by a tangent-continuous bridge (b's first `ramp` mm trimmed)."""
    a, b = np.asarray(a, float), resample(np.asarray(b, float), step)
    k = max(int(ramp / step), 1)
    if len(b) > k + 3:
        b = b[k:]
    br = bridge(a[-1], tangents(a, 3)[-1], b[0], tangents(b, 3)[0], step)
    return np.vstack([a, br, b]) if len(br) else np.vstack([a, b])


def staircase(seg, q):
    p = resample(seg, q)
    out = [p[0]]
    for a, b in zip(p[:-1], p[1:]):
        out.append(np.array([b[0], a[1]]))
        out.append(b)
    return resample(np.array(out), 0.3)


def coil(seg, step, r, period):
    C = Carrier(resample(seg, step), step)
    n = len(C.p)
    s = np.arange(n) * step
    th = 2 * math.pi * s / period
    ramp = np.minimum(1.0, np.minimum(s, s[-1] - s) / max(period, 1e-6))
    tN = C.t
    nN = C.n
    return C.p + (r * ramp)[:, None] * (np.sin(th)[:, None] * tN + (1 - np.cos(th))[:, None] * 0.5 * nN)


def needled(seg, pitch, h, step):
    """A ruled run from seg's start to its end, with chart needles out and back every `pitch` mm."""
    A, B = seg[0], seg[-1]
    L = float(np.linalg.norm(B - A))
    if L < 1e-6:
        return resample(seg, step)
    t = (B - A) / L
    nrm = np.array([-t[1], t[0]])
    pts = [A]
    s = pitch / 2
    side = 1.0
    while s < L - 0.6:
        base = A + t * s
        pts += [base - t * 0.3, base + side * h * nrm, base + t * 0.3]
        side = -side if np.random.default_rng(int(s * 10)).random() < 0.6 else side
        s += pitch
    pts.append(B)
    return np.array(pts)


def spiral_knot(c, r0, turns, rng):
    th = np.linspace(0, 2 * math.pi * turns, int(60 * turns))
    r = r0 * (0.35 + 0.65 * (th / th[-1])) * (1 + 0.12 * np.sin(3.1 * th + rng.uniform(0, 6)))
    drift = np.c_[np.linspace(0, rng.uniform(-1, 1) * r0, len(th)), np.linspace(0, rng.uniform(-1, 1) * r0, len(th))]
    return c + np.c_[r * np.cos(th), r * np.sin(th)] + drift


# ---------------------------------------------------------------------------
# the moves
# ---------------------------------------------------------------------------

def _f(a, k, d):
    v = a.get(k, d)
    return float(v) if not isinstance(v, str) else d


def _ref(a, k):
    v = a.get(k)
    return v[1] if isinstance(v, tuple) else None


def _player(a, default="thrusting"):
    p = a.get("p", default)
    return p if isinstance(p, str) else default


def mv_paste(S: Comp, k, a):
    src = a.get("src", "river")
    cx, cy = S.mm(_f(a, "x", .5), _f(a, "y", .5))
    w, h = _f(a, "w", .6) * S.W, _f(a, "h", .3) * S.H
    rot, crop = _f(a, "rot", 0.0), _f(a, "crop", 1.0)
    if S.reserves:                          # pasted matter keeps out of the blank too (its turned extent)
        cr, sr = abs(math.cos(math.radians(rot))), abs(math.sin(math.radians(rot)))
        ew, eh = w * cr + h * sr, w * sr + h * cr
        bx = S.place(cx, cy, ew, eh)
        cx, cy = bx[0] + bx[2] / 2, bx[1] + bx[3] / 2
        f = min(bx[2] / ew, bx[3] / eh, 1.0)
        w, h = w * f, h * f
    extra = {}
    if src == "river":
        extra = {"span_w": int(np.clip(_f(a, "zoom", 1600), 100, 4000)), "start": float(np.clip(_f(a, "at", 0.0), 0, .95))}
    elif src == "chart" and isinstance(a.get("chart"), str):
        extra = {"chart": a["chart"]}
    inner = (cx - w * crop / 2, cy - h * crop / 2, w * crop, h * crop)
    lines = S.lines_of(src, inner, k, length=a.get("len") if isinstance(a.get("len"), (int, float)) else None,
                       extra=extra)
    rect = rect_polygon(cx, cy, w, h, rot)
    ink = S.inks["chart"] if src == "chart" else S.inks["found"]
    pen = _f(a, "pen", 0.3)
    tot = 0.0
    for p, md in lines:
        q = rotate(p, np.array([cx, cy]), rot)
        for piece in clip_keep(q, rect, S.min_stub):
            ext = float(np.linalg.norm(piece.max(axis=0) - piece.min(axis=0)))
            tot += S.add(piece, pen=pen, ink=ink, role="found", k=k, part=S.parts[src].index, src=src,
                         ridable=ext >= 5.0)
    if int(_f(a, "edge", 0)):
        tot += S.add(rect, pen=0.2, ink=ink, role="edge", k=k)
    return tot


def mv_reserve(S: Comp, k, a):
    x, y, w, h = _f(a, "x", .5), _f(a, "y", .8), _f(a, "w", .8), _f(a, "h", .3)
    S.reserves.append(((x - w / 2) * S.W, (y - h / 2) * S.H, (x + w / 2) * S.W, (y + h / 2) * S.H))
    # a blank decided late is a white-out: what is there (except a traverse or a trail) goes, no edge drawn
    removed = 0.0

    def white_out():
        x0, y0, x1, y1 = S.reserves[-1]
        poly = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]])
        keep = [e for e in S.el if S.args.get(e["move"], {}).get("move") in ("traverse", "trail")]
        kid = {id(e) for e in keep}
        S.el = [e for e in S.el if id(e) not in kid]
        out = S.apply_cover(poly, "cut")
        S.el += keep
        return out
    if S.el:
        removed = white_out()
        if removed < 5.0:                   # nothing there to clear: the late blank is cut into the core instead
            c = S.densest()
            hw, hh = w * S.W / 2, h * S.H / 2
            S.reserves[-1] = (c[0] - hw, c[1] - hh, c[0] + hw, c[1] + hh)
            removed = white_out()
    S._displaced = 0
    return removed


def mv_contain(S: Comp, k, a):
    cx, cy = S.mm(_f(a, "x", .5), _f(a, "y", .4))
    w, h = _f(a, "w", .4) * S.W, _f(a, "h", .3) * S.H
    bx = S.place(cx, cy, w * 1.06, h * 1.06, avoid=False)          # a container sits on the sheet
    cx, cy = bx[0] + bx[2] / 2, bx[1] + bx[3] / 2
    w, h = min(w, bx[2] / 1.06), min(h, bx[3] / 1.06)
    rect = rect_polygon(cx, cy, w, h, _f(a, "rot", 0.0))
    S.containers[k] = rect
    if int(_f(a, "drawn", 1)):
        return S.add(rect, pen=_f(a, "pen", 0.25), ink=a.get("ink", S.inks["made"]) if isinstance(a.get("ink"), str)
                     else S.inks["made"], role="edge", k=k)
    return 0.0


def _in_box(S, a, cx, cy, w, h, avoid=True):
    ci = _ref(a, "in")
    if ci is not None and ci in S.containers:
        r = S.containers[ci]
        lo, hi = r.min(axis=0), r.max(axis=0)
        cx = min(max(cx, lo[0] + w / 2), hi[0] - w / 2) if hi[0] - lo[0] > w else (lo[0] + hi[0]) / 2
        cy = min(max(cy, lo[1] + h / 2), hi[1] - h / 2) if hi[1] - lo[1] > h else (lo[1] + hi[1]) / 2
        return S.place(cx, cy, min(w, hi[0] - lo[0]), min(h, hi[1] - lo[1]), avoid=False), r
    return S.place(cx, cy, w, h, avoid=avoid), None


def _clip_to(points, rect, min_stub):
    return clip_keep(points, rect, min_stub) if rect is not None else [points]


def _draw_lines(S, k, label, boxes, a, rot=0.0):
    tot = 0.0
    pen = _f(a, "pen", 0.45)
    play = a.get("play", "ride") if isinstance(a.get("play"), str) else "ride"
    length = _f(a, "len", 3.0)
    for j, (box, rect) in enumerate(boxes):
        for p, md in S.lines_of(label, box, k, j, length=length, rot=rot):
            if label == "soup":
                continue
            pts, _ = S.listen(p, play, k, j, grow=bool(int(_f(a, "grow", 0))))
            for q in _clip_to(pts, rect, S.min_stub):
                tot += S.add(q, pen=pen, ink=S.inks["made"], role="made", k=k, part=S.parts[label].index)
    return tot


def mv_seed(S: Comp, k, a):
    label = _player(a)
    c = S.mm(_f(a, "x", .5), _f(a, "y", .4))
    r = _f(a, "r", .25) * min(S.W, S.H)
    n = int(np.clip(_f(a, "n", 3), 1, 12))
    rng = S.ctx.rng("seed", k)
    boxes = []
    for j in range(n):
        s = r * rng.uniform(0.55, 1.15)
        asp = rng.uniform(0.6, 1.6)
        cc = c + rng.normal(0, 0.28 * r, 2)
        boxes.append(_in_box(S, a, cc[0], cc[1], s * asp, s / asp))
    bx = boxes[0][0]
    S.cores[k] = (np.array([bx[0] + bx[2] / 2, bx[1] + bx[3] / 2]) if S._displaced else c, r)
    S.players[k] = label
    tot = _draw_lines(S, k, label, boxes, a, rot=_f(a, "rot", 0.0))
    if tot < 1.0 and label not in HANDS:
        # a long-form player (passage, a specimen, the soup) has no line at this size: a hand speaks instead
        S.players[k] = "miner"
        tot = _draw_lines(S, k, "miner", boxes, a, rot=_f(a, "rot", 0.0))
    return tot


def mv_line(S: Comp, k, a):
    label = _player(a)
    cx, cy = S.mm(_f(a, "x", .5), _f(a, "y", .5))
    box = _in_box(S, a, cx, cy, _f(a, "w", .4) * S.W, _f(a, "h", .25) * S.H)
    S.players[k] = label
    return _draw_lines(S, k, label, [box], a, rot=_f(a, "rot", 0.0))


def mv_morph(S: Comp, k, a):
    label = _player(a, "gmorph")
    return mv_line(S, k, {**a, "p": label, "play": a.get("play", "none")})


def mv_soup(S: Comp, k, a):
    cx, cy = S.mm(_f(a, "x", .5), _f(a, "y", .4))
    box = S.place(cx, cy, _f(a, "w", .5) * S.W, _f(a, "h", .35) * S.H)
    tot = 0.0
    S.cores[k] = (np.array([box[0] + box[2] / 2, box[1] + box[3] / 2]), 0.5 * min(box[2], box[3]))
    for m in S.grow("soup", box, k, extra={"T": int(np.clip(_f(a, "T", 150), 30, 260))}):
        ink = m.meta.get("ink", "black")
        role = "made" if ink == "black" else "found"
        tot += S.add(m.points, pen=float(m.meta.get("pen", 0.4)), ink=ink, role=role, k=k,
                     part=S.parts["soup"].index, src="river" if ink == "blue" else "chart" if ink == "red" else None)
    return tot


def mv_traverse(S: Comp, k, a):
    label = _player(a)
    c = S.mm(_f(a, "x", .5), _f(a, "y", .5))
    ang = math.radians(_f(a, "ang", 10.0))
    d = np.array([math.cos(ang), math.sin(ang)])
    A, B = edge_hit(c, -d, S.box), edge_hit(c, d, S.box)
    A, B = A - d * 6.0, B + d * 6.0
    L = float(np.linalg.norm(B - A))
    box = S.place(c[0], c[1], min(L, S.box[2]), min(L, S.box[3]) * 0.4, avoid=False)
    S.players[k] = label
    tot = 0.0
    for j, (p, _) in enumerate(S.lines_of(label, box, k, 0, length=_f(a, "len", 5.0))[:1]):
        q = stretch_between(p, A, B, max_lat=_f(a, "lat", 0.3))
        pts, _ = S.listen(q, a.get("play", "ride") if isinstance(a.get("play"), str) else "ride", k, j)
        tot += S.add(pts, pen=_f(a, "pen", 0.7), ink=S.inks["made"], role="made", k=k, part=S.parts[label].index)
    return tot


def mv_spill(S: Comp, k, a):
    ci = _ref(a, "from")
    if ci is None or ci not in S.containers:
        return 0.0
    r = S.containers[ci]
    lo, hi = r[:-1].min(axis=0), r[:-1].max(axis=0)
    rng = S.ctx.rng("spill", k)
    A = lo + (hi - lo) * rng.uniform(0.25, 0.75, 2)
    d = rng.normal(0, 1, 2)
    d /= max(float(np.linalg.norm(d)), 1e-9)
    B = edge_hit(A, d, S.box)
    if np.linalg.norm(B - A) < 25:
        B = edge_hit(A, -d, S.box)
    label = _player(a)
    S.players[k] = label
    box = S.place(*(A + B) / 2, max(np.linalg.norm(B - A), 30), max(np.linalg.norm(B - A), 30) * 0.4, avoid=False)
    tot = 0.0
    for p, _ in S.lines_of(label, box, k, length=_f(a, "len", 2.5))[:1]:
        q = stretch_between(p, A, B, max_lat=0.35)
        tot += S.add(resample(q, S.step), pen=_f(a, "pen", 0.45), ink=S.inks["made"], role="made", k=k,
                     part=S.parts[label].index)
    return tot


def mv_cover(S: Comp, k, a):
    at = _ref(a, "at")
    if at is not None and at in S.cores:
        c = S.cores[at][0] + S.ctx.rng("cover", k).normal(0, 6.0, 2)
    elif a.get("at") == "dense":
        c = S.densest()
    else:
        c = S.mm(_f(a, "x", .5), _f(a, "y", .5))
    w, h = _f(a, "w", .25) * S.W, _f(a, "h", .2) * S.H
    c = S.clamp_pt(c, pad=min(w, h) / 3)
    shape = a.get("shape", "torn") if isinstance(a.get("shape"), str) else "torn"
    mode = a.get("mode", "cut") if a.get("mode") in ("cut", "tint") else "cut"
    poly = cover_polygon(S.ctx.rng("cover", k, "shape"), c, w, h, shape, 0.0, angle=_f(a, "rot", 0.0))
    S.covers.append((poly, mode, k))
    t = S.apply_cover(poly, mode)
    if t < 5.0 and S.el:                    # nothing under it: the cover goes onto the densest passage instead
        S.covers.pop()
        poly = cover_polygon(S.ctx.rng("cover", k, "shape"), S.clamp_pt(S.densest(), pad=min(w, h) / 3), w, h,
                             shape, 0.0, angle=_f(a, "rot", 0.0))
        S.covers.append((poly, mode, k))
        t = S.apply_cover(poly, mode)
    if int(_f(a, "edge", 0)):
        t += S.add(poly, pen=0.2, ink=S.inks["found"], role="edge", k=k, clip=False, of_cover=True)
    return t


def mv_cross(S: Comp, k, a):
    ci = _ref(a, "over")
    cov = [c for c in S.covers if c[2] == ci] or S.covers[-1:]
    if not cov:
        return 0.0
    poly = cov[0][0]
    c = poly[:-1].mean(axis=0)
    D = float(np.linalg.norm(poly.max(axis=0) - poly.min(axis=0)))
    label = _player(a)
    S.players[k] = label
    rng = S.ctx.rng("cross", k)
    from shapely.geometry import LineString, Polygon  # noqa: PLC0415
    Pg = Polygon(poly)
    best = None
    for j in range(5):
        ang = rng.uniform(0, math.pi)
        d = np.array([math.cos(ang), math.sin(ang)])
        span = D * rng.uniform(1.4, 2.6)
        A, B = S.clamp_pt(c - d * span / 2), S.clamp_pt(c + d * span / 2)
        if np.linalg.norm(B - A) < 0.8 * D:
            continue
        box = S.place(*(A + B) / 2, float(np.linalg.norm(B - A)), float(np.linalg.norm(B - A)) * 0.45, avoid=False)
        ls = S.lines_of(label, box, k, j, length=_f(a, "len", 2.5))
        if not ls:
            continue
        q = stretch_between(ls[0][0], A, B, max_lat=0.3)
        inside = LineString(q).intersection(Pg).length
        if best is None or inside > best[0]:
            best = (inside, q)
        if inside > 0.6 * D:
            break
    if best is None:
        return 0.0
    play = a.get("play", "none") if isinstance(a.get("play"), str) else "none"
    pts, _ = S.listen(best[1], play, k, 9)
    return S.add(pts, pen=_f(a, "pen", 0.8), ink=S.inks["made"], role="made", k=k, part=S.parts[label].index)


def mv_answer(S: Comp, k, a):
    to = _ref(a, "to")
    e = S.longest(to) if to is not None else None
    if e is None:
        return 0.0
    rng = S.ctx.rng("answer", k)
    cp = resample(e["pts"], S.step)
    trace = min(_f(a, "trace", 16.0), _L_of(cp) * 0.5)
    kk = max(int(trace / S.step), 3)
    tail = cp[-kk - 1:]
    t = tangents(tail, 3)
    gap = 1.8 * (1 - np.linspace(0, 1, len(tail)))
    side = 1.0 if rng.random() < 0.5 else -1.0
    tail = tail + side * gap[:, None] * np.c_[-t[:, 1], t[:, 0]]
    E, tE = tail[-1], t[-1]
    th = rng.uniform(-1.0, 1.0)
    dirn = np.array([tE[0] * math.cos(th) - tE[1] * math.sin(th), tE[0] * math.sin(th) + tE[1] * math.cos(th)])
    Lb = _f(a, "reach", 0.45) * min(S.W, S.H) * rng.uniform(0.6, 1.4)
    B = S.clamp_pt(E + dirn * Lb, pad=4.0)
    A = E + tE * 6.0
    label = _player(a)
    S.players[k] = label
    if np.linalg.norm(B - A) < 15:
        B = S.clamp_pt(E - dirn * Lb, pad=4.0)
    box = S.place(*(A + B) / 2, max(float(np.linalg.norm(B - A)), 20), max(float(np.linalg.norm(B - A)), 20) * 0.5,
                  avoid=False)
    ls = S.lines_of(label, box, k, length=_f(a, "len", 2.5))
    if not ls:
        return 0.0
    own = stretch_between(ls[0][0], A, B, max_lat=0.45)
    pts = join_lines(np.vstack([tail, E + tE * np.linspace(0.3, 4.0, 8)[:, None]]), own, S.step)
    return S.add(pts, pen=_f(a, "pen", e["pen"]), ink=S.inks["made"], role="made", k=k, part=S.parts[label].index)


def mv_trail(S: Comp, k, a):
    on = _ref(a, "on")
    x0b, y0b, wb, hb = S.box

    def free_end(q):
        return min(q[0] - x0b, q[1] - y0b, x0b + wb - q[0], y0b + hb - q[1]) > 10.0

    # the line's end, or its start if the end already reached the paper's edge (a plotted line has no
    # direction); a line with both ends on the edge hands the move on to the nearest line that can trail
    cands = [S.longest(on)] if on is not None else []
    cands += [S.longest(kk) for kk in sorted({x["move"] for x in S.el}, reverse=True)]
    e, p = None, None
    for c in cands:
        if c is None or _L_of(c["pts"]) < 10.0:
            continue
        q = resample(c["pts"], S.step)
        if free_end(q[-1]):
            e, p = c, q
            break
        if free_end(q[0]):
            c["pts"] = q[::-1].copy()
            e, p = c, c["pts"]
            break
    if e is None:
        return 0.0
    on = e["move"]
    E, tE = p[-1], tangents(p, 4)[-1]
    if S.reserves:
        x0, y0, x1, y1 = S.reserves[-1]
        d = np.array([(x0 + x1) / 2, (y0 + y1) / 2]) - E
        d = d / max(float(np.linalg.norm(d)), 1e-9)
        d = 0.6 * d + 0.4 * tE
    else:
        d = tE + S.ctx.rng("trail", k).normal(0, 0.35, 2)
    d = d / max(float(np.linalg.norm(d)), 1e-9)
    T = edge_hit(E, d, S.box)
    if np.linalg.norm(T - E) < 40:          # too near an edge that way: the longest way out within ±100°
        best = None
        for t_ in np.radians(np.linspace(-100, 100, 11)):
            dd = np.array([d[0] * math.cos(t_) - d[1] * math.sin(t_), d[0] * math.sin(t_) + d[1] * math.cos(t_)])
            TT = edge_hit(E, dd, S.box)
            if best is None or np.linalg.norm(TT - E) > best[0]:
                best = (float(np.linalg.norm(TT - E)), TT)
        T = best[1]
    if np.linalg.norm(T - E) < 15:
        return 0.0
    label = S.players.get(on, "thrusting")
    if label not in S.parts or label == "soup":
        label = "thrusting"
    box = S.place(*(E + T) / 2, float(np.linalg.norm(T - E)), float(np.linalg.norm(T - E)) * 0.4, avoid=False)
    ls = S.lines_of(label, box, k, length=_f(a, "len", 1.8))
    if not ls:
        return 0.0
    q = stretch_between(ls[0][0], E + tE * 5.0, T, max_lat=0.25)
    full = join_lines(p[-max(int(4 / S.step), 3):], q, S.step)[max(int(4 / S.step), 3) - 1:]
    s = arclen(full)
    pens = np.maximum(e["pen"] * (1 - s / s[-1]) ** 1.4, 0.1)
    tot = 0.0
    cuts = np.linspace(0, s[-1], 6)
    for c0, c1 in zip(cuts[:-1], cuts[1:]):
        idx = np.flatnonzero((s >= c0) & (s <= c1 + S.step))
        if len(idx) >= 2:
            tot += S.add(full[idx[0]:idx[-1] + 1], pen=float(np.mean(pens[idx])), ink=e["ink"], role="made", k=k,
                         part=e["part"])
    return tot


def _line_or_fallback(S, on, min_len, roles=("made",)):
    """Move `on`'s longest line; if it has none that long (cut, stopped, tiny), the most recent move's
    line that is (the move still acts, on the nearest thing it can)."""
    e = S.longest(on, roles) if on is not None else None
    if e is not None and _L_of(e["pts"]) >= min_len:
        return e
    for kk in sorted({x["move"] for x in S.el}, reverse=True):
        e = S.longest(kk, roles)
        if e is not None and _L_of(e["pts"]) >= min_len:
            return e
    return None


def mv_stop(S: Comp, k, a):
    e = _line_or_fallback(S, _ref(a, "on"), 30.0)
    if e is None:
        return 0.0
    p = resample(e["pts"], S.step)
    others = S.all_pts(exclude=e)
    s = arclen(p)
    lo, hi = _f(a, "at", 0.45), min(_f(a, "at", 0.45) + 0.35, 0.92)
    cand = np.flatnonzero((s >= lo * s[-1]) & (s <= hi * s[-1]))
    if not len(cand):
        return 0.0
    if len(others):
        from scipy.spatial import cKDTree  # noqa: PLC0415
        dist = cKDTree(others).query(p[cand])[0]
        i = int(cand[int(np.argmax(dist))])
    else:
        i = int(cand[len(cand) // 2])
    removed = s[-1] - s[i]
    e["pts"] = p[: i + 1]
    return float(removed)


def mv_contaminate(S: Comp, k, a):
    e = _line_or_fallback(S, _ref(a, "on"), 30.0, roles=("made", "found"))
    if e is None:
        return 0.0
    p = resample(e["pts"], S.step)
    s = arclen(p)
    Lc = float(np.clip(_f(a, "len", 40.0), 12.0, 0.6 * s[-1]))
    s0 = float(np.clip(_f(a, "at", 0.3), 0.0, 1.0)) * (s[-1] - Lc)
    i0, i1 = int(np.searchsorted(s, s0)), int(np.searchsorted(s, s0 + Lc))
    seg = p[i0:i1 + 1]
    if len(seg) < 6:
        return 0.0
    how = a.get("with", "stair")
    rng = S.ctx.rng("contaminate", k)
    if how == "stair":
        new = staircase(seg, _f(a, "q", 3.0))
    elif how == "rule":
        new = needled(seg, _f(a, "q", 6.0), _f(a, "h", 3.0), S.step)
    elif how == "coil":
        new = coil(seg, S.step, _f(a, "q", 2.2), _f(a, "per", 2.6))
    else:                                   # river: real far-river bends, carried along the stretch
        g = S._river_g()
        xy = gen_meander(rng, g, Lc + 4.0, omega_max=120.0)
        car = Carrier(resample(seg, S.step), S.step)
        new = car.map(0.0, xy)
        k1 = np.flatnonzero(xy[:, 0] <= (len(car.p) - 1) * S.step)
        new = new[: int(k1[-1]) + 1] if len(k1) else new
        new = np.vstack([new, bridge(new[-1], tangents(new, 3)[-1], seg[-1], tangents(seg, 3)[-1], S.step)])
    e["pts"] = np.vstack([p[:i0], new, p[i1 + 1:]])
    return Lc


def _river_g(self):
    if "far" not in self._grammar_cache:
        from .arrangers_oehlen_found import stem  # noqa: PLC0415
        _, _, q = stem(self.ctx, "grwl_far_sb19", "SB19", 0)
        q = q[: 4 * 1600]
        lo, hi = q.min(axis=0), q.max(axis=0)
        river = [(q - lo) * (140.0 / max(hi - lo))]
        self._grammar_cache["far"] = river_grammar(river, axis_mm=10.0, omega_max=120.0)
    own = self._contagion()[1].get("river")
    return own or self._grammar_cache["far"]


Comp._river_g = _river_g


def mv_zoom(S: Comp, k, a):
    of = _ref(a, "of")
    e = S.longest(of, roles=("made", "found", "heavy")) if of is not None else None
    if e is None:
        return 0.0
    p = resample(e["pts"], 0.25)
    s = arclen(p)
    Ls = float(np.clip(_f(a, "len", 30.0), 8.0, s[-1]))
    s0 = float(np.clip(_f(a, "at", 0.3), 0, 1)) * (s[-1] - Ls)
    seg = p[int(np.searchsorted(s, s0)): int(np.searchsorted(s, s0 + Ls)) + 1]
    if len(seg) < 5:
        return 0.0
    sc = float(np.clip(_f(a, "s", 3.0), 0.15, 8.0))
    if sc > 1.5:
        from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
        seg = gaussian_filter1d(seg, max(0.6 * sc, 1.0), axis=0, mode="nearest")
    c = seg.mean(axis=0)
    q = (seg - c) * sc
    q = rotate(q, np.zeros(2), _f(a, "rot", 0.0)) + S.mm(_f(a, "x", .5), _f(a, "y", .5))
    q = resample(q, S.step)
    pen = e["pen"] * (1.0 if sc < 1 else min(1.0 + 0.25 * sc, 2.2))
    return S.add(q, pen=_f(a, "pen", pen), ink=e["ink"], role=e["role"], k=k, part=e["part"], src=e.get("src"),
                 ridable=True)


def mv_repeat(S: Comp, k, a):
    of = _ref(a, "of")
    if of is None or of not in S.args:
        return 0.0
    src = dict(S.args[of])
    kind = src["move"]
    if kind not in ("seed", "line", "morph", "paste", "soup", "traverse", "intrude", "contain"):
        return 0.0
    sc = _f(a, "s", 0.6)
    src.update({"x": _f(a, "x", .5), "y": _f(a, "y", .5)})
    for key in ("r", "w", "h"):
        if key in src and isinstance(src[key], (int, float)):
            src[key] = float(src[key]) * sc
    if isinstance(src.get("len"), (int, float)) and kind != "paste":
        src["len"] = float(src["len"]) * (0.6 + 0.4 * sc)
    if "rot" in a:
        src["rot"] = a["rot"]
    src.pop("in", None)
    S.args[k] = src
    return HANDLERS[kind](S, k, src)


def mv_counter(S: Comp, k, a):
    of = _ref(a, "of")
    if of is None or of not in S.cores:
        return 0.0
    c, r = S.cores[of]
    rng = S.ctx.rng("counter", k)
    x0, y0, w, h = S.box
    ctr = np.array([2 * (x0 + w / 2) - c[0], 2 * (y0 + h / 2) - c[1]]) + rng.normal(0, 0.12, 2) * [w, h]
    s = _f(a, "s", 0.45)
    src = S.args.get(of, {})
    label = _player(a, S.players.get(of, "thrusting"))
    n = max(1, int(round(_f(src, "n", 3) * s)))
    return mv_seed(S, k, {"p": label, "x": ctr[0] / S.W, "y": ctr[1] / S.H,
                          "r": max(r * s / min(S.W, S.H), 0.07),
                          "n": n, "len": _f(a, "len", _f(src, "len", 3.0)), "pen": _f(a, "pen", 0.4),
                          "play": a.get("play", "ride")})


def mv_intrude(S: Comp, k, a):
    at = _ref(a, "at")
    rng = S.ctx.rng("intrude", k)
    if at is not None and at in S.cores:
        c, r = S.cores[at]
    else:
        c, r = S.densest(), 0.15 * min(S.W, S.H)
    phi = rng.uniform(0, 2 * math.pi)
    P0 = S.clamp_pt(c + r * 0.85 * np.array([math.cos(phi), math.sin(phi)]), pad=10.0)   # at the core's edge
    ang = math.radians(_f(a, "ang", math.degrees(phi) + 90 + rng.uniform(-35, 35)))
    d = np.array([math.cos(ang), math.sin(ang)])
    Ln = _f(a, "len", 50.0)
    pen = _f(a, "pen", 2.0)
    kind = a.get("kind", "bar")
    tot = 0.0
    if kind == "bar":
        tot += S.add(np.array([P0 - d * Ln / 2, P0 + d * Ln / 2]), pen=pen, ink=S.inks["made"],
                     role="heavy", k=k)
    elif kind == "el":
        turn = math.radians(rng.choice([-1, 1]) * rng.uniform(80, 115))
        d2 = np.array([d[0] * math.cos(turn) - d[1] * math.sin(turn), d[0] * math.sin(turn) + d[1] * math.cos(turn)])
        A = P0 - d * Ln * 0.6
        tot += S.add(np.array([A, P0, P0 + d2 * Ln * 0.4]), pen=pen, ink=S.inks["made"],
                     role="heavy", k=k)
    elif kind == "dashes":
        nrm = np.array([-d[1], d[0]])
        for j in range(int(rng.integers(2, 4))):
            o = P0 + nrm * (j - 0.5) * pen * 4.0 + d * rng.normal(0, 2.0)
            tot += S.add(np.array([o - d * Ln * 0.12, o + d * Ln * 0.12]), pen=pen, ink=S.inks["made"],
                         role="heavy", k=k)
    elif kind == "knot":
        tot += S.add(spiral_knot(P0, max(Ln / 14.0, 2.0), rng.uniform(2.5, 4.5), rng), pen=min(pen, 1.4),
                     ink=S.inks["made"], role="heavy", k=k)
    else:                                     # sign: a short heavy hand, a clef-like black sign
        label = _player(a, "hokusai")
        box = S.place(P0[0], P0[1], Ln * 0.6, Ln * 0.6, avoid=False)
        for p, _ in S.lines_of(label, box, k, length=_f(a, "slen", 0.6)):
            tot += S.add(p, pen=pen, ink=S.inks["made"], role="heavy", k=k, part=S.parts[label].index)
    return tot


HANDLERS = {"paste": mv_paste, "reserve": mv_reserve, "contain": mv_contain, "seed": mv_seed, "line": mv_line,
            "morph": mv_morph, "soup": mv_soup, "traverse": mv_traverse, "spill": mv_spill, "cover": mv_cover,
            "cross": mv_cross, "answer": mv_answer, "trail": mv_trail, "stop": mv_stop,
            "contaminate": mv_contaminate, "zoom": mv_zoom, "repeat": mv_repeat, "counter": mv_counter,
            "intrude": mv_intrude}


# ---------------------------------------------------------------------------
# the arranger
# ---------------------------------------------------------------------------

@arranger("cgram", params=[
    P("sentence", "str", "seed p=thrusting x=0.6 y=0.35 r=0.3 n=3 ; traverse p=bend x=0.5 y=0.5 ang=12 len=5 "
      "pen=0.8 ; intrude kind=bar at=@0", "the composition: moves separated by ';' (see the module doc)"),
    P("step", "float", 0.4, "resampling step, mm", min=0.2, max=1.5),
    P("min_stub", "float", 6.0, "a cut piece shorter than this (mm) is dropped", min=0.0, max=50.0),
    P("found_ink", "str", "blue", "Flexoki pen for found matter"),
    P("chart_ink", "str", "red", "Flexoki pen for a pasted chart"),
    P("made_ink", "str", "black", "Flexoki pen for made lines"),
    P("tint_ink", "str", "green", "made lines inside a tint cover"),
    P("tint_found_ink", "str", "green-400", "found matter inside a tint cover"),
], doc="compositions as a grammar: plays a sentence of compositional moves (paste, seed, traverse, intrude, "
        "contain, spill, cover, cross, answer, trail, stop, contaminate, zoom, repeat, counter, reserve, soup, "
        "morph, line) with the kept techniques as players")
def cgram(ctx, parts, *, sentence, step, min_stub, found_ink, chart_ink, made_ink, tint_ink, tint_found_ink):
    for nm in (found_ink, chart_ink, made_ink, tint_ink, tint_found_ink):
        if nm not in FLEXOKI:
            raise ValueError(f"cgram: unknown ink {nm!r}; choose from {sorted(FLEXOKI)}")
    S = Comp(ctx, parts, step=step, found_ink=found_ink, chart_ink=chart_ink, made_ink=made_ink, tint_ink=tint_ink,
             tint_found_ink=tint_found_ink, min_stub=min_stub)
    moves = parse(sentence)
    for k, a in enumerate(moves):
        S.args[k] = dict(a)
        S._displaced = 0
        before = S.ink_len()
        err = None
        try:
            touched = HANDLERS[a["move"]](S, k, a)
        except (ValueError, IndexError, np.linalg.LinAlgError) as ex:   # a move that cannot be played is logged
            touched, err = 0.0, f"{type(ex).__name__}: {ex}"[:160]
        rec = {"k": k, "move": a["move"], "touched_mm": round(float(touched), 1),
               "net_mm": round(S.ink_len() - before, 1)}
        if S._displaced:
            rec["displaced"] = S._displaced
        if err:
            rec["error"] = err
        S.log.append(rec)
    # a reserve made before anything was drawn acts by absence: log what it pushed away and what it kept out
    for rec in S.log:
        if rec["move"] == "reserve":
            later = [r.get("displaced", 0) for r in S.log if r["k"] > rec["k"]]
            x0, y0, x1, y1 = S.reserves[[r["k"] for r in S.log if r["move"] == "reserve"].index(rec["k"])]
            P_ = S.all_pts()
            inside = int(np.sum((P_[:, 0] > x0) & (P_[:, 0] < x1) & (P_[:, 1] > y0) & (P_[:, 1] < y1))) if len(P_) else 0
            share = (x1 - x0) * (y1 - y0) / (S.W * S.H)
            rec["displaced_later"] = int(sum(later))
            rec["ink_share_inside"] = round(inside / max(len(P_), 1), 3)
            rec["area_share"] = round(share, 3)
    out = []
    for e in S.el:
        if len(e["pts"]) < 2:
            continue
        out.append(Mark(np.asarray(e["pts"], float), {}, {
            "part": e["part"], "of_role": e["role"], "ink": e["ink"], "pen": e["pen"], "move": e["move"],
            **({"under_cover": True} if e.get("under_cover") else {})}))
    if not out:
        out.append(Mark(np.array([[ctx.box[0], ctx.box[1]], [ctx.box[0] + 0.01, ctx.box[1]]]), {},
                        {"part": parts[0].index, "of_role": "edge", "ink": made_ink, "pen": 0.05, "move": -1}))
    out[0] = out[0].evolve(meta={"cgram": {"moves": S.log, "sentence": sentence}})
    return out


# ---------------------------------------------------------------------------
# the sampler: a per-sheet temperament, then a sentence (sampled, never scored)
# ---------------------------------------------------------------------------

FRAME = (220.0, 300.0)
PRIOR = {"paste": 1.0, "reserve": 0.3, "contain": 0.4, "seed": 1.2, "line": 1.0, "morph": 0.7, "soup": 0.25,
         "traverse": 0.7, "spill": 0.6, "cover": 0.6, "cross": 0.6, "answer": 0.8, "trail": 0.6, "stop": 0.5,
         "contaminate": 0.7, "zoom": 0.5, "repeat": 0.6, "counter": 0.5, "intrude": 0.45}
CAPS = {"soup": 2, "reserve": 2, "intrude": 3, "cover": 3, "contain": 2, "paste": 5, "traverse": 4,
        "contaminate": 6, "repeat": 6}
NEEDS = {"spill": "container", "cross": "cover", "answer": "line", "trail": "line", "stop": "line",
         "contaminate": "line", "zoom": "ink", "repeat": "repeatable", "counter": "core", "intrude": "ink",
         "cover": "ink"}


def _r(rng, lo, hi, nd=2):
    return round(float(rng.uniform(lo, hi)), nd)


def temperament(rng, uniform: bool = False) -> dict:
    """The sheet's decisions, drawn before any move: how long the sentence is, which moves it favours,
    the density dial, the core, the blank, the dominant players, whether a heavy intruder comes, how
    strictly the habitual order holds, the weight contrast."""
    kinds = list(PRIOR)
    if uniform:
        return {"n": 14, "w": {m: 1.0 for m in kinds}, "density": 0.5, "core": [0.5, 0.45], "core2": None,
                "blank": None, "players": {p: 1.0 for p in LINEISH}, "found": {f: 1.0 for f in FOUND},
                "intruder": False, "habit": 0.0, "heavy": 0.8, "hair": 0.3, "play": {"ride": 1, "catch": 1, "none": 1},
                "scale": 1.0}
    n = int(round(math.exp(rng.uniform(math.log(3), math.log(44)))))
    dir_ = rng.dirichlet(np.full(len(kinds), 0.45))
    w = {m: float(PRIOR[m] * (0.15 + len(kinds) * d)) for m, d in zip(kinds, dir_)}
    pl = rng.dirichlet(np.full(len(LINEISH), 0.3))
    fd = rng.dirichlet(np.full(len(FOUND), 0.5))
    side = rng.choice(["high", "right", "left", "low", "centre", "corner"], p=[0.3, 0.25, 0.12, 0.13, 0.08, 0.12])
    core = {"high": [rng.uniform(0.3, 0.7), rng.uniform(0.18, 0.38)],
            "right": [rng.uniform(0.6, 0.78), rng.uniform(0.3, 0.6)],
            "left": [rng.uniform(0.22, 0.4), rng.uniform(0.3, 0.6)],
            "low": [rng.uniform(0.3, 0.7), rng.uniform(0.62, 0.8)],
            "centre": [rng.uniform(0.42, 0.58), rng.uniform(0.42, 0.58)],
            "corner": [rng.choice([0.25, 0.75]) + rng.normal(0, 0.04), rng.choice([0.22, 0.78]) + rng.normal(0, 0.04)]}[side]
    blank = None
    if rng.random() < 0.7:
        # the blank sits away from the core: the far third, or a far corner
        cx, cy = core
        if rng.random() < 0.6:
            if abs(cy - 0.5) >= abs(cx - 0.5) * 0.8:
                y = 0.83 if cy < 0.5 else 0.17
                blank = [0.5, y, rng.uniform(0.7, 1.0), rng.uniform(0.22, 0.4)]
            else:
                x = 0.82 if cx < 0.5 else 0.18
                blank = [x, 0.5, rng.uniform(0.25, 0.4), rng.uniform(0.6, 0.95)]
        else:
            blank = [0.78 if cx < 0.5 else 0.22, 0.8 if cy < 0.5 else 0.2, rng.uniform(0.3, 0.5), rng.uniform(0.25, 0.4)]
    plays = rng.dirichlet([0.7, 0.7, 0.5])
    return {"n": n, "w": w, "density": float(rng.beta(0.45, 0.45)), "core": [round(float(v), 3) for v in core],
            "core2": rng.random() < 0.35, "blank": None if blank is None else [round(float(v), 3) for v in blank],
            "players": {p: float(v) for p, v in zip(LINEISH, pl)}, "found": {f: float(v) for f, v in zip(FOUND, fd)},
            "intruder": bool(rng.random() < 0.55), "habit": float(rng.uniform(0.4, 0.97)),
            "heavy": round(float(rng.uniform(0.6, 1.5)), 2), "hair": round(float(rng.uniform(0.15, 0.35)), 2),
            "play": {"ride": float(plays[0]), "catch": float(plays[1]), "none": float(plays[2])},
            "scale": float(math.exp(rng.normal(0, 0.45)))}


def _pick(rng, d: dict):
    keys = list(d)
    p = np.array([d[k] for k in keys], float)
    return keys[int(rng.choice(len(keys), p=p / p.sum()))]


def sample_sentence(seed: int, uniform: bool = False) -> tuple[str, dict]:
    """One sentence for `seed`: the temperament first, then the moves one by one, each one's kind drawn
    from the temperament's weights among the moves the sheet so far allows (a cover needs ink, a cross
    needs a cover …), the habitual order kept with the temperament's `habit`, arguments drawn around
    the sheet's decisions (core, blank, density, weights). Deterministic in the seed."""
    rng = np.random.default_rng([int(seed), 0xC6A4])
    T = temperament(rng, uniform)
    d, sc = T["density"], T["scale"]
    moves: list[dict] = []
    have = {"ink": [], "line": [], "core": [], "cover": [], "container": [], "repeatable": []}
    counts: dict[str, int] = {}
    phase = 0
    cx, cy = T["core"]

    def jit(v, s=0.12):
        return round(float(np.clip(v + rng.normal(0, s), 0.06, 0.94)), 3)

    def pen_line():
        return round(float(np.clip(T["hair"] + (T["heavy"] - T["hair"]) * rng.beta(0.6, 0.9), 0.12, 1.6)), 2)

    def play():
        return _pick(rng, T["play"])

    def player(pool=None):
        pool = pool or LINEISH
        return _pick(rng, {p: T["players"][p] + 1e-3 for p in pool})

    def ref(key, recent=0.6):
        xs = have[key]
        if rng.random() < recent:
            return ("ref", xs[-1])
        return ("ref", xs[int(rng.integers(len(xs)))])

    if T["blank"] is not None and (uniform or rng.random() < 0.8):
        bx, by, bw, bh = T["blank"]
        moves.append({"move": "reserve", "x": bx, "y": by, "w": round(bw, 3), "h": round(bh, 3)})
        counts["reserve"] = 1
    found_first = (not uniform) and rng.random() < 0.75 * T["habit"]
    forced = []
    if T["intruder"]:
        forced.append("intrude")
    if T["core2"]:
        forced.append("counter")
    n_target = max(T["n"], len(moves) + 1)
    guard = 0
    while len(moves) < n_target and guard < 400:
        guard += 1
        ok = {}
        for m, wt in T["w"].items():
            if counts.get(m, 0) >= CAPS.get(m, 99):
                continue
            need = NEEDS.get(m)
            if need and not have[need]:
                continue
            f = 1.0 if PHASE[m] >= phase - 1 else (1.0 - T["habit"])
            ok[m] = wt * f
        if not have["ink"]:
            ok = {m: v for m, v in ok.items() if m in ("paste", "seed", "line", "morph", "soup", "traverse", "contain")}
            if found_first:                 # the habit (note T5): found matter first
                ok = {"paste": 1.0}
        left = n_target - len(moves)
        if forced and (left <= len(forced) or rng.random() < 0.08):
            m = forced.pop(0)
            if NEEDS.get(m) and not have[NEEDS[m]]:
                forced.append(m)
                m = _pick(rng, ok)
        else:
            m = _pick(rng, ok)
        k = len(moves)
        a: dict = {"move": m}
        if m == "paste":
            src = _pick(rng, T["found"])
            near = rng.random() < 0.6
            a.update({"src": src, "x": jit(cx if near else 0.5, 0.18), "y": jit(cy if near else 0.5, 0.2),
                      "w": _r(rng, 0.35, 0.95), "h": _r(rng, 0.1, 0.45),
                      "rot": round(float(rng.choice([0.0, rng.normal(0, 8), 90 + rng.normal(0, 6)], p=[.3, .55, .15])), 1)})
            if src == "river":
                a.update({"zoom": int(math.exp(rng.uniform(math.log(250), math.log(3600)))), "at": _r(rng, 0, 0.9)})
            elif src == "chart":
                a["chart"] = str(rng.choice(["kappa", "route", "atlas", "ledger", "phase"]))
            else:
                a["len"] = _r(rng, 1.0, 4.0, 1)
            if rng.random() < 0.25:
                a["crop"] = _r(rng, 1.1, 1.6)
            if rng.random() < 0.2:
                a["edge"] = 1
        elif m == "reserve":
            a.update({"x": jit(1 - cx, 0.1), "y": jit(1 - cy, 0.1), "w": _r(rng, 0.25, 0.6), "h": _r(rng, 0.15, 0.35)})
        elif m == "contain":
            a.update({"x": jit(cx, 0.15), "y": jit(cy, 0.15), "w": _r(rng, 0.25, 0.6), "h": _r(rng, 0.15, 0.4),
                      "rot": round(float(rng.normal(0, 4)), 1), "drawn": 1, "pen": _r(rng, 0.2, 0.5)})
        elif m in ("seed", "counter") or (m == "line" and False):
            pass
        if m == "seed":
            first = not have["core"]
            x, y = (cx, cy) if first or rng.random() < 0.5 else (rng.uniform(0.2, 0.8), rng.uniform(0.15, 0.85))
            a.update({"p": player(), "x": jit(x, 0.05), "y": jit(y, 0.05),
                      "r": round(float(np.clip((0.12 + 0.3 * rng.random()) * sc, 0.06, 0.6)), 3),
                      "n": int(np.clip(round(1 + d * 7 * rng.uniform(0.4, 1.3)), 1, 10)),
                      "len": _r(rng, 1.0, 3.0 + 6 * d, 1), "pen": pen_line(), "play": play()})
            if have["container"] and rng.random() < 0.5:
                a["in"] = ref("container")
        elif m == "line":
            a.update({"p": player(), "x": _r(rng, 0.15, 0.85), "y": _r(rng, 0.12, 0.88),
                      "w": round(float(np.clip(rng.uniform(0.15, 0.7) * sc, 0.05, 0.95)), 3),
                      "h": round(float(np.clip(rng.uniform(0.1, 0.5) * sc, 0.04, 0.9)), 3),
                      "rot": round(float(rng.normal(0, 25)), 1), "len": _r(rng, 0.8, 6.0, 1), "pen": pen_line(),
                      "play": play()})
            if have["container"] and rng.random() < 0.4:
                a["in"] = ref("container")
        elif m == "morph":
            a.update({"p": player(MORPHS), "x": _r(rng, 0.25, 0.75), "y": _r(rng, 0.15, 0.85),
                      "w": _r(rng, 0.4, 0.95), "h": _r(rng, 0.12, 0.45), "rot": round(float(rng.normal(0, 20)), 1),
                      "len": _r(rng, 3.0, 9.0, 1), "pen": pen_line()})
        elif m == "soup":
            a.update({"x": jit(cx, 0.1), "y": jit(cy, 0.1), "w": _r(rng, 0.4, 0.9), "h": _r(rng, 0.25, 0.5),
                      "T": int(rng.integers(60, 220))})
        elif m == "traverse":
            a.update({"p": player(), "x": jit(cx, 0.08), "y": jit(cy, 0.1),
                      "ang": round(float(rng.choice([rng.uniform(-30, 30), rng.uniform(60, 120), rng.uniform(-75, 75)])), 1),
                      "len": _r(rng, 3.0, 9.0, 1), "pen": pen_line(), "play": play(), "lat": _r(rng, 0.12, 0.45)})
        elif m == "spill":
            a.update({"from": ref("container"), "p": player(), "len": _r(rng, 1.0, 4.0, 1), "pen": pen_line()})
        elif m == "cover":
            r_ = rng.random()
            if r_ < 0.4 and have["core"]:
                a["at"] = ref("core")
            elif r_ < 0.7:
                a["at"] = "dense"
            else:
                a.update({"x": _r(rng, 0.2, 0.8), "y": _r(rng, 0.15, 0.85)})
            a.update({"w": _r(rng, 0.1, 0.45), "h": _r(rng, 0.08, 0.35), "rot": round(float(rng.normal(0, 10)), 1),
                      "shape": str(rng.choice(["torn", "cut", "sheet"], p=[.6, .25, .15])),
                      "mode": "tint" if rng.random() < 0.3 else "cut"})
        elif m == "cross":
            a.update({"over": ref("cover"), "p": player(), "len": _r(rng, 1.0, 4.0, 1),
                      "pen": round(min(T["heavy"] * rng.uniform(0.8, 1.2), 1.6), 2),
                      "play": str(rng.choice(["none", "ride"], p=[.6, .4]))})
        elif m == "answer":
            a.update({"to": ref("line"), "p": player(), "len": _r(rng, 0.8, 3.5, 1), "pen": pen_line(),
                      "reach": _r(rng, 0.2, 0.7)})
        elif m == "trail":
            a.update({"on": ref("line", 0.4), "len": _r(rng, 0.8, 2.5, 1)})
        elif m == "stop":
            a.update({"on": ref("line", 0.5), "at": _r(rng, 0.3, 0.6)})
        elif m == "contaminate":
            how = str(rng.choice(["stair", "rule", "river", "coil"], p=[.15, .27, .33, .25]))
            a.update({"on": ref("line", 0.4), "with": how, "at": _r(rng, 0.1, 0.9),
                      "len": _r(rng, 15.0, 70.0, 1)})
            if how == "stair":
                a["q"] = _r(rng, 1.5, 5.0, 1)
            elif how == "coil":
                a.update({"q": _r(rng, 1.2, 3.5, 1), "per": _r(rng, 1.6, 4.0, 1)})
        elif m == "zoom":
            big = rng.random() < 0.65
            a.update({"of": ref("ink"), "at": _r(rng, 0, 1), "len": _r(rng, 10.0, 40.0, 1) if big else _r(rng, 40, 160, 1),
                      "s": _r(rng, 2.0, 6.0) if big else _r(rng, 0.35, 0.6), "x": _r(rng, 0.2, 0.8),
                      "y": _r(rng, 0.15, 0.85), "rot": round(float(rng.uniform(-180, 180)), 1)})
        elif m == "repeat":
            a.update({"of": ref("repeatable", 0.3), "x": _r(rng, 0.15, 0.85), "y": _r(rng, 0.12, 0.88),
                      "s": round(float(math.exp(rng.normal(-0.3, 0.6))), 2)})
            if rng.random() < 0.4:
                a["rot"] = round(float(rng.uniform(-90, 90)), 1)
        elif m == "counter":
            a.update({"of": ref("core"), "s": _r(rng, 0.25, 0.7), "pen": pen_line(), "play": play()})
            if rng.random() < 0.5:
                a["p"] = player()
        elif m == "intrude":
            kind = str(rng.choice(["bar", "el", "knot", "dashes", "sign"], p=[.3, .2, .2, .12, .18]))
            a.update({"kind": kind, "len": _r(rng, 25.0, 90.0, 1), "pen": _r(rng, 1.4, 2.6)})
            if have["core"]:
                a["at"] = ref("core", 0.4)
        moves.append(a)
        counts[m] = counts.get(m, 0) + 1
        phase = max(phase, PHASE[m])
        if m in ("paste", "seed", "line", "morph", "soup", "traverse", "spill", "cross", "answer", "zoom",
                 "repeat", "counter", "intrude"):
            have["ink"].append(k)
        if m in ("seed", "line", "morph", "traverse", "spill", "cross", "answer", "counter"):
            have["line"].append(k)
        if m in ("seed", "soup", "counter"):
            have["core"].append(k)
        if m == "cover":
            have["cover"].append(k)
        if m == "contain":
            have["container"].append(k)
        if m in ("seed", "line", "morph", "paste", "intrude", "soup"):
            have["repeatable"].append(k)
    return speak(moves), T


def recipe(seed: int, uniform: bool = False, frame=FRAME) -> dict:
    """The whole recipe for `seed`: the fixed vocabulary as parts, the sampled sentence as the arranger."""
    sent, T = sample_sentence(seed, uniform)
    tag = "uniform" if uniform else f"n{T['n']} d{T['density']:.2f} habit{T['habit']:.2f}"
    return {"label": f"cgram {seed} ({tag})", "frame": list(frame), "seed": int(seed), "margin": 6.0,
            "arranger": {"id": "cgram", "sentence": sent}, "parts": copy.deepcopy(PLAYERS),
            "renderer": {"id": "oehlen_found_ink", "pen": 0.4},
            "notes": "temperament: " + ", ".join(f"{k}={v}" for k, v in sorted(T.items())
                                                 if k in ("n", "core", "blank", "intruder", "heavy", "hair"))}
