# FROZEN from research commit 6f96418: tools/gesture/gesture/kit/writers_listen.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Synthesis bench S2a: `listen` as a score writer (`_writers.writer`).

Round 15's listen composer drew whole sheets. This writer writes the same history as a v2 score and
lets the executor play it (`docs/synthesis-bench/design-2026-10-19.md` §6; build plan S2a):

    found matter (maybe)  a river_zoom part, laid along the sheet's flow           role "found"
    speakers (1–2)        hand parts with a WRITTEN place (`modulators_place.place`) role "speaker"
    listeners (3–5)       imitate / exaggerate / translate / refuse: a part (the listener's own
                          hand) + a grow relation from an earlier layer that places it  role "listener"
    the void (maybe)      a `lines` layer (its edge drawn in part) + a `mask` contact  role "mask"
                          relation; listeners after it cross it, layers before are cut
    later small layers    echo / calm / nest / bind: relation-only layers             roles = kind
    awareness             sympathy, crossing, hesitate, accompany, make_room over "*"→"*",
                          the void skipped (`not_roles: ["mask"]`; Ian: awareness everywhere)

It writes as it plays: every listener is added, played through `wctx.play` (cached prefixes, so a try
costs one layer), and kept only if its relation placed it; the density band reads the played ground.
What listen decided from its own arrays (palette, colour mode, flow, the bold voice, counts, which
kinds) is decided here the same way and recorded in `decisions`.

Balance (Ian, round 16: "both are nice as options"): how many grown lines are distinct hands
(voice `hdist_zoom`) instead of listen's own `hand` — none / one (the first speaker) / speakers / all
(every speaker and every listener's own voice); integ16's `dial`, now a writer param.

Seeds: a layer grown from a part takes `seed` = writer seed + 400 + k (speakers, listeners) or
+ 460 + k (the river), listen's own internal part seeds. The first writer on a sheet (prefix "")
draws its composition from listen's own arranger stream (`ctx.rng("compose")` of the round-15
arranger: seed, "arranger", "listen", "compose"), so for the same seed it opens with round-15
listen's decisions — frame, palette, colour mode, flow, bold voice, speaker count, river and the
speakers themselves (same hands, seeds, boxes, place). Everything after the first listener diverges,
because placements now happen at play time with their own relation streams. A writer with a prefix
draws from `wctx.rng("compose")`.

Locks (`wctx.keep`): kept found/speaker layers open the sheet (and count as speakers); other kept
layers follow the speakers; all are included verbatim and heard like any earlier layer. The palette
is built around the kept pens (`_writers.palette_around`, after listen's own draws, so the stream is
unchanged): a kept line belongs to the recomposed drawing (Ian, 2026-10-19).

On a ground (another writer's layers already on the sheet), every relation this writer adds leaves
the ground's own pairs alone (`except`: the ground's ids); the ground's own `*` relations already
reach the new layers.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import binary_dilation

from . import _synth
from ._writers import palette_around, writer
from .arrangers_ccolour import DARK, HUE, _pick, _u
from .arrangers_listen import CAP, LATER, LISTEN_HANDS, SPLICED, STEP, VOCAB, WEIGHTS, light_of
from .arrangers_oehlen_found import arclen, cover_polygon, resample
from .core import SEED_MAX, P, tag
from .relations_listen import _raster

BALANCE = ("none", "one", "speakers", "all")
AWARE = ("sympathy", "crossing", "hesitate", "accompany", "make_room")
MM_PER_LENGTH = 200.0           # integ16: listen's hand length (R units) → hdist drawn length
HEARD_BY = ("speaker", "listener", "found")


def _r(v, n=2):
    return round(float(v), n)


class _ListenWriter:
    def __init__(self, wctx, *, balance, density, mask_p, river_p, kinds, pens, awareness):
        self.w = wctx
        fx, fy = wctx.frame
        rx, ry, rw, rh = wctx.region
        mg = wctx.margin
        # listen composes on the frame with a 7 mm margin; the writer's box is its region grown back by
        # the score margin (the whole frame for the default region), so the margin stays listen's
        x0, y0 = max(rx - mg, 0.0), max(ry - mg, 0.0)
        x1, y1 = min(rx + rw + mg, float(fx)), min(ry + rh + mg, float(fy))
        self.B = (x0, y0, x1, y1)
        self.box = [_r(x0, 3), _r(y0, 3), _r(x1 - x0, 3), _r(y1 - y0, 3)]
        self.W, self.H = x1 - x0, y1 - y0
        self.m = 7.0
        self.balance = balance
        self.awareness = bool(awareness)
        self.hands = list(LISTEN_HANDS)
        if wctx.prefix == "":
            self.rng = np.random.default_rng([tag(wctx.seed), tag("arranger"), tag("listen"), tag("compose")])
        else:
            self.rng = wctx.rng("compose")
        rng = self.rng
        self.density = float(density)
        self.band = (8.0 + 6.0 * density, 12.0 + 8.0 * density)
        self.mask_p, self.river_p = float(mask_p), float(river_p)
        self.kinds = [k for k in VOCAB if k in kinds]
        # the same draws, in the same order, as Composer.__init__
        self.palette = self._palette(pens)
        self.mode = "mono" if len(self.palette) < 2 else _pick(rng, ["accent", "pair", "mono"], [0.55, 0.3, 0.15])
        if wctx.keep:                   # Ian 2026-10-19: recompose builds its palette around the locked pens
            kept = [next((d for d in DARK if HUE[d] == HUE.get(L.get("pen"), "")), None) for L in wctx.keep]
            self.palette, _ = palette_around(self.palette, [c for c in kept if c])
        a = (0.0 if self.W >= self.H else 90.0) + _u(rng, -35, 35) + (180.0 if rng.random() < 0.5 else 0.0)
        self.flow = np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])
        self.flow_deg = round(a % 360.0, 1)
        self.bold = round(_pick(rng, [0.6, 0.8, 1.0], [0.35, 0.4, 0.25]), 2)
        self.bold_speaker = int(_pick(rng, [0, 1, -1], [0.7, 0.12, 0.18]))
        self.k = 0                      # listen's internal part counter (seeds + 400 + k / + 460 + k)
        self.n_grown = 0                # grown lines so far (the balance dial counts them)
        self.layers: list[dict] = []
        self.grow: list[dict] = []
        self.mask_rel: dict | None = None
        self.void = None
        self.aware: list[dict] = []
        self.meta: dict[str, dict] = {}
        self.taken = {L["id"] for L in wctx.keep} | set(wctx.ground_ids())
        self.n_layer = 0
        self.n_rel = 0
        self.log = {"kinds": [], "unplaced": [], "distinct": [], "held": []}
        self.ground_ids = wctx.ground_ids()
        if self.awareness:
            have = {R["kind"] for R in (wctx.ground or {}).get("relations", []) if R["src"] == "*" and R["dst"] == "*"}
            for kind in AWARE:
                if kind in have:
                    continue           # the ground's own "*" relation already reaches every new layer
                R = {"id": wctx.id(f"A_{kind}"), "kind": kind, "src": "*", "dst": "*", "not_roles": ["mask"]}
                if self.ground_ids:
                    R["except"] = list(self.ground_ids)
                self.aware.append(R)

    # -- pens (Composer's) ------------------------------------------------------------------------
    def _palette(self, pens):
        rng = self.rng
        n = int(pens) if pens else int(rng.choice([2, 3], p=[0.55, 0.45]))
        first = _pick(rng, DARK[:6], [0.4, 0.15, 0.12, 0.1, 0.13, 0.1])
        pal = [first]
        pool = [c for c in DARK if HUE[c] != HUE[first]]
        while len(pal) < n and pool:
            c = _pick(rng, pool)
            pal.append(c)
            pool = [q for q in pool if HUE[q] != HUE[c]]
        return pal

    def pen_other_than(self, *cs):
        free = [c for c in self.palette if c not in cs]
        return _pick(self.rng, free) if free else self.palette[-1]

    @property
    def accent(self):
        return self.palette[1] if len(self.palette) > 1 else self.palette[0]

    def own_pen(self, src_ink):
        if self.mode == "pair":
            return self.pen_other_than(src_ink) if src_ink in self.palette[:2] else self.palette[0]
        return self.palette[0]

    def heard_pen(self, src_ink, own):
        return {"accent": self.accent, "pair": src_ink, "mono": own}[self.mode]

    def heard_param(self):
        """The relation's `heard`: the accent by name, "src" (the source's pen, read at play time), or ""."""
        return {"accent": self.accent, "pair": "src", "mono": ""}[self.mode]

    # -- bookkeeping ------------------------------------------------------------------------------
    def new_id(self):
        while True:
            lid = self.w.id(f"L{self.n_layer}")
            self.n_layer += 1
            if lid not in self.taken:
                self.taken.add(lid)
                return lid

    def new_rid(self):
        self.n_rel += 1
        return self.w.id(f"R{self.n_rel - 1}")

    def seed(self, off):
        return int((self.w.seed + off) % (SEED_MAX + 1))

    def relations(self):
        return self.grow + ([self.mask_rel] if self.mask_rel else []) + self.aware

    def fragment(self):
        return {"layers": list(self.layers), "relations": self.relations()}

    def play(self):
        return self.w.play(self.fragment())

    def include(self, L):
        """A layer Ian locked, verbatim."""
        self.layers.append(L)
        part = L.get("part") or {}
        v = part.get("voice") or {}
        pen = (part.get("renderer") or L.get("renderer") or {}).get("pen", 0.35)
        self.meta[L["id"]] = {"role": L.get("role", "line"), "ink": L.get("pen", "black"), "pen": float(pen),
                              "hand": v.get("hand"), "kept": True}
        if not any(L.get(k) is not None for k in ("part", "lines", "composer", "pin")):
            # a relation-only layer (echo, calm, nest, bind) locked WITHOUT a pin still needs a grow relation to
            # validate: an inert one from the first earlier layer (a pinned one validates on its pin)
            earlier = [x["id"] for x in self.layers[:-1]] + list(self.ground_ids)
            if earlier:
                self.grow.append({"id": self.new_rid(), "kind": "echo", "src": earlier[0], "dst": L["id"],
                                  "note": "inert: holds a locked relation-only layer"})
                self.log["held"].append(L["id"])

    def voice(self, hand, length, k):
        """The balance dial: this grown line in listen's own hand, or as a distinct hand (hdist_zoom)."""
        i = self.n_grown
        self.n_grown += 1
        b = self.balance
        on = b == "all" or (b == "speakers" and float(length) >= 3.0) or (b == "one" and i == 0)
        if on:
            return {"id": "hdist_zoom", "source": "hand", "hand": hand,
                    "drawn_mm": round(float(length) * MM_PER_LENGTH, 1),
                    "recur": int(self.w.rng("hdist_recur", k).integers(1, 4))}, True
        return {"id": "hand", "hand": hand, "length": float(length), "joins": "smooth"}, False

    def density_now(self, sheet):
        x0, y0, x1, y1 = self.B
        mm = 0.0
        for m in sheet.marks:
            if m.meta.get("of_role") == "unseen" or len(m) < 2:
                continue
            c = m.points.mean(axis=0)
            if x0 <= c[0] <= x1 and y0 <= c[1] <= y1:
                mm += m.length()
        return mm / (self.W * self.H / 100.0)

    def attempt(self, layer, rel, kind):
        """Add a layer and the relation that draws it, play, keep it only if the relation placed it."""
        self.layers.append(layer)
        self.grow.append(rel)
        sheet = self.play()
        outs = [e["outcome"] for e in _synth.played(sheet)["log"] if e["relation"] == rel["id"]]
        if kind in outs:
            self.log["kinds"].append({"layer": layer["id"], "kind": kind, "src": rel["src"], "relation": rel["id"]})
            return self.void_meets(sheet, [layer["id"]])
        self.layers.pop()
        self.grow.pop()
        self.taken.discard(layer["id"])
        self.log["unplaced"].append({"kind": kind, "src": rel["src"], "outcomes": outs})
        return None

    def heard_by(self):
        return [L["id"] for L in self.layers if self.meta[L["id"]]["role"] in HEARD_BY]

    # -- acts ---------------------------------------------------------------------------------------
    def river(self):
        rng, W, H = self.rng, self.W, self.H
        x0, y0 = self.B[:2]
        wh = (W * _u(rng, 0.6, 0.9), H * _u(rng, 0.18, 0.35))
        k = self.k
        self.k += 1
        spec = {"id": "river_zoom", "mode": "magnify", "schedule": "push", "course": "free",
                "zoom": round(_u(rng, 10, 26), 1), "recur": int(rng.integers(2, 4)),
                "start": round(_u(rng, 0.0, 0.7), 3), "pace": 0.5,
                "max_mm": round(_u(rng, 0.9, 1.5) * (wh[0] + wh[1]) * 2, 0)}
        ang = math.degrees(math.atan2(self.flow[1], self.flow[0]))
        tilt = _u(rng, -12, 12)
        c = [x0 + W * _u(rng, 0.35, 0.65), y0 + H * _u(rng, 0.3, 0.7)]
        lid = self.new_id()
        ink = light_of(self.palette[-1])
        self.layers.append({
            "id": lid, "role": "found", "pen": ink, "label": "the river, zoomed (constant width)",
            "region": [0.0, 0.0, _r(wh[0]), _r(wh[1])], "seed": self.seed(460 + k),
            "part": {"voice": spec, "renderer": {"id": "wire", "pen": 0.3},
                     "modulators": [{"id": "place", "centre": [_r(c[0]), _r(c[1])], "align": _r(ang),
                                     "tilt": _r(tilt), "turn_by": "absolute", "box": self.box, "margin": self.m}]}})
        self.meta[lid] = {"role": "found", "ink": ink, "pen": 0.3, "hand": None}
        return lid

    def speaker(self, i):
        rng, W, H = self.rng, self.W, self.H
        x0, y0 = self.B[:2]
        hand = _pick(rng, self.hands)
        wh = (W * _u(rng, 0.65, 0.95), H * _u(rng, 0.65, 0.95))
        length = round(_u(rng, 3.0, 5.0), 1)
        k = self.k
        self.k += 1
        voice, distinct = self.voice(hand, length, k)
        f = self.flow
        mid = np.array([x0 + W / 2, y0 + H / 2])
        if i == 0:
            c = mid - f * np.array([W, H]) * _u(rng, 0.05, 0.18)
        else:
            c = mid + f * np.array([W, H]) * _u(rng, 0.12, 0.25)
        c = c + rng.normal(0, 0.04, 2) * [W, H]
        tilt = 30.0 if max(W, H) / min(W, H) < 1.3 else 8.0
        tilt_deg = _u(rng, -tilt, tilt)
        ink = self.palette[1] if (i == 1 and self.mode == "pair") else self.palette[0]
        pen = self.bold if i == self.bold_speaker else round(_pick(rng, [0.35, 0.45]), 2)
        lid = self.new_id()
        self.layers.append({
            "id": lid, "role": "speaker", "pen": ink, "label": f"{hand} speaks",
            "region": [0.0, 0.0, _r(wh[0]), _r(wh[1])], "seed": self.seed(400 + k),
            "part": {"voice": voice, "renderer": {"id": "wire", "pen": float(pen)},
                     "modulators": [{"id": "place", "centre": [_r(c[0]), _r(c[1])],
                                     "align": 0.0 if W >= H else 90.0, "tilt": _r(tilt_deg), "turn_by": "axis",
                                     "box": self.box, "margin": self.m}]}})
        self.meta[lid] = {"role": "speaker", "ink": ink, "pen": float(pen), "hand": hand}
        if distinct:
            self.log["distinct"].append(lid)
        return lid

    def listener(self, kind, src):
        rng, W, H = self.rng, self.W, self.H
        s = self.meta[src]
        hand = _pick(rng, [h for h in self.hands if h != s["hand"]] or self.hands)
        length = round(_u(rng, 1.4, 2.4), 1)
        lo, hi = (0.3, 0.5) if kind == "refuse" else (0.35, 0.55)
        wh = (W * _u(rng, lo, hi), H * _u(rng, lo, hi))
        k = self.k
        self.k += 1
        voice, distinct = self.voice(hand, length, k)
        ink = self.own_pen(s["ink"])
        if kind == "exaggerate":
            has_bold = any(v["pen"] >= self.bold for v in self.meta.values())
            pen = 0.5 if has_bold else self.bold
        else:
            pen = round(_pick(rng, [0.3, 0.35]), 2)
        lid = self.new_id()
        layer = {"id": lid, "role": "listener", "pen": ink, "label": f"{hand} {kind}s {src}",
                 "region": [0.0, 0.0, _r(wh[0]), _r(wh[1])], "seed": self.seed(400 + k),
                 "part": {"voice": voice, "renderer": {"id": "wire", "pen": float(pen)}}}
        params = {"heard": self.heard_param(), "box": self.box, "margin": self.m}
        if kind != "refuse":
            params["flow_deg"] = self.flow_deg
        rel = {"id": self.new_rid(), "kind": kind, "src": src, "dst": lid, "params": params}
        self.meta[lid] = {"role": "listener", "ink": ink, "pen": float(pen), "hand": hand, "kind": kind}
        sheet = self.attempt(layer, rel, kind)
        if sheet is None:
            del self.meta[lid]
        elif distinct:
            self.log["distinct"].append(lid)
        return sheet

    def later(self, kind, src):
        """echo / calm / nest from one earlier layer; bind from a pair ([a, b])."""
        rng = self.rng
        if kind == "bind":
            a, b = src
            ink = self.meta[a]["ink"] if self.mode == "pair" else self.accent
            layer = {"id": self.new_id(), "role": "bind", "pen": ink, "label": f"binds {a} into {b}",
                     "renderer": {"id": "wire", "pen": 0.35}}
            params = {"second": "src" if self.mode == "pair" else "", "box": self.box}
            pen = 0.35
        else:
            s = self.meta[src]
            if kind == "echo":
                ink = light_of(self.accent if self.mode == "accent" else s["ink"])
                pen = round(_pick(rng, [0.3, 0.35]), 2)
                label, params = f"echo of {src}", {"box": self.box, "margin": self.m}
            elif kind == "calm":
                ink = self.heard_pen(s["ink"], self.own_pen(s["ink"]))
                pen = 0.3
                label, params = f"calm under {src}", {"box": self.box}
            else:
                ink = self.heard_pen(s["ink"], self.own_pen(s["ink"]))
                pen = round(_pick(rng, [0.3, 0.4, 0.5]), 2)
                label, params = f"nests in {src}", {}
            layer = {"id": self.new_id(), "role": kind, "pen": ink, "label": label,
                     "renderer": {"id": "wire", "pen": float(pen)}}
        rel = {"id": self.new_rid(), "kind": kind, "src": list(src) if kind == "bind" else src,
               "dst": layer["id"], "params": params}
        self.meta[layer["id"]] = {"role": kind, "ink": ink, "pen": float(pen), "hand": None, "kind": kind}
        sheet = self.attempt(layer, rel, kind)
        if sheet is None:
            del self.meta[layer["id"]]
        return sheet

    def place_void(self, sheet):
        """`Composer.place_mask`: the torn void where two of this writer's layers overlap most, central."""
        rng, W, H = self.rng, self.W, self.H
        x0, y0, x1, y1 = self.B
        cell = 4.0
        fr = self.w.frame
        by: dict[str, list] = {}
        for m in sheet.marks:
            if m.meta.get("layer") in self.meta and len(m) >= 2:
                by.setdefault(m.meta["layer"], []).append(m.points)
        rs = [binary_dilation(_raster(by[L["id"]], fr, cell), iterations=2) for L in self.layers if L["id"] in by]
        if not rs:
            return None
        cnt = np.sum(rs, axis=0).astype(float)
        ny, nx = cnt.shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        cx, cy = (xx + 0.5) * cell, (yy + 0.5) * cell
        central = np.exp(-(((cx - (x0 + W / 2)) / (0.35 * W)) ** 2 + ((cy - (y0 + H / 2)) / (0.35 * H)) ** 2))
        inside = (cx >= x0) & (cx <= x1) & (cy >= y0) & (cy <= y1)
        sc = (cnt >= 2) * cnt * central * inside + rng.random(cnt.shape) * 0.2 * inside - (~inside)
        j = int(np.argmax(sc))
        c = np.array([cx.ravel()[j], cy.ravel()[j]])
        w = min(W, H) * _u(rng, 0.13, 0.22)
        h = min(W, H) * _u(rng, 0.28, 0.45)
        if rng.random() < 0.4:
            w, h = h, w
        poly = cover_polygon(rng, c, w, h, _pick(rng, ["torn", "cut"], [0.6, 0.4]), 8.0)
        poly = np.clip(poly, 0.0, [fr[0], fr[1]])
        ring = resample(poly, STEP)
        s = arclen(ring)
        runs = []
        for _ in range(int(_pick(rng, [0, 1, 2], [0.15, 0.5, 0.35]))):
            a = _u(rng, 0, s[-1])
            b = a + _u(rng, 0.15, 0.35) * s[-1]
            idx = (np.flatnonzero((s >= a) & (s <= b)) if b <= s[-1]
                   else np.r_[np.flatnonzero(s >= a), np.flatnonzero(s <= b - s[-1])])
            if len(idx) > 4:
                runs.append(ring[idx])
        ink = light_of(self.accent)
        lid = self.new_id()
        self.layers.append({"id": lid, "role": "mask", "pen": ink, "label": "the void",
                            "lines": [[[_r(x, 3), _r(y, 3)] for x, y in q] for q in runs],
                            "renderer": {"id": "wire", "pen": 0.3}})
        self.meta[lid] = {"role": "mask", "ink": ink, "pen": 0.3, "hand": None}
        self.mask_rel = {"id": self.w.id("V"), "kind": "mask", "src": lid, "dst": "*", "not_roles": ["mask"],
                         "params": {"polygon": [_r(v, 3) for v in poly.ravel()], "flip": ""}}
        if self.ground_ids:
            self.mask_rel["except"] = list(self.ground_ids)
        self.void = {"layer": lid, "edge_runs": len(runs), "centre": [_r(c[0], 1), _r(c[1], 1)]}
        self.plan: list[list] = []
        return self.void_meets(self.play(), [L["id"] for L in self.layers[:-1]])

    def void_meets(self, sheet, ids):
        """`Composer.apply_mask`, decided as the sheet is written: a layer the void meets is cut if drawn
        before it and crosses it if drawn after, with listen's 15% exception per layer (written into the
        mask relation's `flip`). Deciding each layer when it is placed (not at the end) keeps what later
        listeners heard the same as what the final score plays."""
        if self.mask_rel is None:
            return sheet
        new = []
        for e in _synth.played(sheet)["log"]:
            if e["relation"] == self.mask_rel["id"] and e["dst"] in ids and e["outcome"] in ("mask", "ignore"):
                before = e["outcome"] == "mask"
                cut_it = before if self.rng.random() >= 0.15 else not before
                self.plan.append([e["dst"], before, cut_it])
                new.append(cut_it != before)
        if any(new):
            self.mask_rel["params"]["flip"] = ",".join(d for d, b, c in self.plan if b != c)
            return self.play()
        return sheet

    def finish_void(self):
        """listen's last rule: never all one way, or the void would be a plain hole (all cut) or not
        exist (none cut). The latest layer it met changes (listen changes the last / the first; the
        latest disturbs the fewest listeners), and only if no listener loses its place by it."""
        if self.mask_rel is None:
            return None
        plan = self.plan
        fix = None
        if len(plan) >= 2 and all(p[2] for p in plan):
            fix = "the last layer over the void crosses it, or the void would be a plain hole"
        elif len(plan) >= 2 and not any(p[2] for p in plan):
            fix = "the last layer the void meets is cut by it, or the void would not exist"
        if fix:
            before = self.play()
            ok0 = self.placed(before)
            plan[-1][2] = not plan[-1][2]
            self.mask_rel["params"]["flip"] = ",".join(d for d, b, c in plan if b != c)
            if self.placed(self.play()) < ok0:
                plan[-1][2] = not plan[-1][2]
                self.mask_rel["params"]["flip"] = ",".join(d for d, b, c in plan if b != c)
                fix = "skipped: " + fix + " (a listener would lose its place)"
        self.void.update(cut=[d for d, _, c in plan if c], crosses=[d for d, _, c in plan if not c],
                         flip=[d for d, b, c in plan if b != c], rule=fix)
        return None

    def placed(self, sheet) -> int:
        mine = {R["id"] for R in self.grow}
        return sum(1 for e in _synth.played(sheet)["log"] if e["relation"] in mine and e["outcome"] == e["kind"])

    # -- the whole history (Composer.compose) -------------------------------------------------------
    def write(self):
        rng = self.rng
        keep = list(self.w.keep)
        lead = [L for L in keep if L.get("role") in ("found", "speaker")]
        rest = [L for L in keep if L.get("role") not in ("found", "speaker")]
        for L in lead:
            self.include(L)
        n_speak = int(_pick(rng, [1, 2], [0.4, 0.6]))
        river = None
        if rng.random() < self.river_p and not any(L.get("role") == "found" for L in lead):
            river = self.river()
        kept_speakers = sum(L.get("role") == "speaker" for L in lead)
        for i in range(kept_speakers, n_speak):
            self.speaker(i)
        for L in rest:
            self.include(L)
        n_listen = int(_pick(rng, [3, 4], [0.6, 0.4]))
        mask_after = None
        if rng.random() < self.mask_p:
            mask_after = max(n_listen - int(rng.integers(1, 3)), 1)
        n_later = int(_pick(rng, [1, 2], [0.5, 0.5]))
        used = {k: 0 for k in VOCAB}
        heard, tries = 0, 0
        sheet = self.play()
        while tries < 16:
            tries += 1
            d = self.density_now(sheet)
            want = n_listen + (1 if d < self.band[0] else 0)
            if heard >= min(want, 5) or d > self.band[1]:
                break
            if mask_after is not None and heard == mask_after and self.void is None:
                sheet = self.place_void(sheet) or sheet
            spliced = [k for k in self.kinds if k in SPLICED and used[k] < CAP[k]]
            if not spliced:
                break
            kind = _pick(rng, spliced, [WEIGHTS[k] for k in spliced])
            # listen to a recent layer more often than an old one (chains: C hears B hearing A)
            cands = self.heard_by()
            if not cands:
                break
            w = np.array([1.0 + 1.0 * i for i in range(len(cands))])
            src = cands[int(rng.choice(len(cands), p=w / w.sum()))]
            got = self.listener(kind, src)
            if got is not None:
                sheet = got
                heard += 1
                used[kind] += 1
        if mask_after is not None and self.void is None:
            sheet = self.place_void(sheet) or sheet
        done, tries2 = 0, 0
        while done < n_later and tries2 < 10:
            tries2 += 1
            later = [k for k in self.kinds if k in LATER and used[k] < CAP[k]]
            if not later or self.density_now(sheet) > self.band[1]:
                break
            kind = _pick(rng, later, [WEIGHTS[k] for k in later])
            cands = self.heard_by()
            if not cands:
                break
            src = cands[int(rng.integers(len(cands)))]
            if kind == "bind":
                if len(cands) < 2:
                    continue
                i, j = rng.choice(len(cands), 2, replace=False)
                got = self.later("bind", [cands[int(i)], cands[int(j)]])
            else:
                got = self.later(kind, src)
            if got is not None:
                sheet = got
                done += 1
                used[kind] += 1
        achieved = self.density_now(sheet)
        self.finish_void()
        decisions = {
            "box": self.box, "palette": list(self.palette), "colour_mode": self.mode, "bold_mm": self.bold,
            "bold_speaker": self.bold_speaker, "flow_deg": self.flow_deg, "balance": self.balance,
            "density": {"dial": self.density, "band_mm_per_cm2": [_r(v, 1) for v in self.band],
                        "achieved": _r(achieved, 1)},
            "speakers": n_speak, "river": river, "void": self.void,
            "planned": {"listeners": n_listen, "later": n_later, "void_after": mask_after},
            "counts": {k: v for k, v in used.items() if v}, "relations": self.log["kinds"],
            "unplaced": self.log["unplaced"], "distinct": self.log["distinct"],
            "awareness": [R["kind"] for R in self.aware],
            "kept": [L["id"] for L in keep], "held": self.log["held"],
            "order": [L["id"] for L in self.layers],
            "rng": "round-15 listen's arranger stream" if self.w.prefix == "" else "wctx.rng('compose')",
        }
        return {"layers": self.layers, "relations": self.relations(), "decisions": decisions}


@writer("listen", params=[
    P("balance", "choice", "one", "how many grown lines are distinct hands (hdist_zoom) instead of listen's own: "
      "none · one (the first speaker) · speakers · all", choices=BALANCE),
    P("density", "float", 0.5, "where in the middle band the sheet sits (0.2 … 0.8; the extremes are off)",
      min=0.2, max=0.8),
    P("mask_p", "float", 0.25, "chance of the void (the 4507 move); kept rare so it never becomes the style",
      min=0.0, max=1.0),
    P("river_p", "float", 0.3, "chance of found matter: river_zoom, free course, constant width", min=0.0, max=1.0),
    P("relations", "str", ",".join(VOCAB), "which relation kinds may be written (comma list)"),
    P("pens", "int", 0, "how many pens 2–4 (0 = the writer decides)", min=0, max=4),
    P("awareness", "bool", True, "the five awareness relations over every pair of layers, the void skipped"),
], doc="listen as a score: speakers, listeners spliced beside what they heard (imitate, exaggerate, "
       "translate, refuse), a rare void, later small layers (echo, calm, nest, bind); awareness everywhere")
def listen(wctx, *, balance, density, mask_p, river_p, relations, pens, awareness):
    kinds = {k.strip() for k in relations.split(",") if k.strip()}
    return _ListenWriter(wctx, balance=balance, density=density, mask_p=mask_p, river_p=river_p, kinds=kinds,
                         pens=pens, awareness=awareness).write()
