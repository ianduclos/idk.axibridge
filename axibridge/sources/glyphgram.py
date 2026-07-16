"""Glyph grammar — Hershey typography pushed toward asemic writing.

Oehlen-pass item 4 (docs/IDEAS-oehlen-pass.md): single-stroke Hershey
letterforms (plotter-honest, no outlines to fill) put through a coherent
destruction pass with one master `abstraction` dial running from "almost
reads" to pure scaffold. The near-figuration device from the *Computer
Paintings*: shapes that almost resolve into letters and refuse.

v2 — the v1 pipeline gave every fragment an independent random rotation/
displacement, which reads as scattered font-confetti ("airbrush"), not
writing. Two changes make it coherent and continuous instead:

* every distortion (displacement, rotation, scale) is sampled from ONE
  smooth random field over the block — neighbouring strokes distort
  together, so letterforms warp and melt as a gesture while staying
  recognizable geometry;
* after distortion, stroke ends within reach are CHAINED into long
  continuous polylines (the pen stays down through the join), so the
  output reads as a hand writing almost-language, not stamped glyphs.
  `continuity` is the reach dial.

Empty text generates asemic glyph soup from the chosen font, so the source
works as pure mark-vocabulary with no message at all.
"""

from __future__ import annotations

import math
import random
from typing import Literal

import vpype
from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source

# curated: readable → increasingly alien. All ship inside vpype.
_Font = Literal["futural", "rowmant", "scriptc", "gothiceng", "greek",
                "japanese", "symbolic", "astrology", "music", "mathupp"]

_SOUP = "abcdefghijklmnopqrstuvwxyzABCDEFGHKMRSWX023589&?!#@"


class GlyphGramParams(BaseModel):
    text: str = Field(default="", title="Text",
                      description="Empty = asemic glyph soup from the font")
    font: _Font = Field(default="futural", title="Font")
    size: float = Field(default=18.0, ge=5.0, le=80.0, title="Glyph size (mm)")
    width: float = Field(default=160.0, ge=40.0, le=280.0, title="Block width (mm)")
    abstraction: float = Field(default=0.65, ge=0.0, le=1.0, title="Abstraction",
                               description="0 = almost reads · 1 = pure scaffold")
    continuity: float = Field(default=0.6, ge=0.0, le=1.0, title="Continuity",
                              description="Chain stroke ends into long continuous "
                                          "lines — the pen writes through the joins")
    echoes: int = Field(default=1, ge=0, le=4, title="Mirror echoes",
                        description="Re-stamp a fragment subset reflected about the centre")
    scatter: float = Field(default=12.0, ge=0.0, le=60.0, title="Scatter (mm)",
                           description="How far the distortion field may carry strokes",
                           json_schema_extra={"group": "Fine tuning"})
    soup_glyphs: int = Field(default=48, ge=8, le=200, title="Soup glyphs",
                             description="Glyph count when text is empty",
                             json_schema_extra={"group": "Fine tuning"})
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")


class _SmoothField:
    """Bilinearly-interpolated random grid, one value in [-1, 1] per channel
    per cell. Nearby points sample nearby values — the whole block distorts
    as one gesture instead of white noise per fragment."""

    def __init__(self, x0: float, y0: float, x1: float, y1: float,
                 cell: float, rng: random.Random, channels: int = 4):
        self.x0, self.y0 = x0, y0
        self.cell = max(cell, 1e-6)
        self.gw = int((x1 - x0) / self.cell) + 3
        self.gh = int((y1 - y0) / self.cell) + 3
        self.g = [[[rng.uniform(-1.0, 1.0) for _ in range(channels)]
                   for _ in range(self.gw)] for _ in range(self.gh)]

    def at(self, x: float, y: float, ch: int) -> float:
        fx = min(max((x - self.x0) / self.cell, 0.0), self.gw - 2.001)
        fy = min(max((y - self.y0) / self.cell, 0.0), self.gh - 2.001)
        ix, iy = int(fx), int(fy)
        tx, ty = fx - ix, fy - iy
        g = self.g
        return (g[iy][ix][ch] * (1 - tx) * (1 - ty) + g[iy][ix + 1][ch] * tx * (1 - ty)
                + g[iy + 1][ix][ch] * (1 - tx) * ty + g[iy + 1][ix + 1][ch] * tx * ty)


def _densify(pts: list[tuple[float, float]], step: float) -> list[tuple[float, float]]:
    """Subdivide segments to ~step spacing. Hershey strokes carry only a few
    vertices (straight runs) — without this the distortion field can only
    move endpoints and nothing ever bends or melts."""
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.dist(a, b) / step))
        for k in range(1, n + 1):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def _smooth(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(pts) < 3:
        return pts
    return ([pts[0]]
            + [((a[0] + 2 * b[0] + c[0]) / 4, (a[1] + 2 * b[1] + c[1]) / 4)
               for a, b, c in zip(pts, pts[1:], pts[2:])]
            + [pts[-1]])


def _cut(points: list[tuple[float, float]], piece_len: float,
         rng: random.Random) -> list[list[tuple[float, float]]]:
    """Split a polyline into ~piece_len fragments (vertex granularity,
    jittered so cuts don't align across strokes)."""
    if len(points) < 2:
        return [points]
    out: list[list[tuple[float, float]]] = []
    cur = [points[0]]
    budget = piece_len * rng.uniform(0.6, 1.4)
    for a, b in zip(points, points[1:]):
        cur.append(b)
        budget -= math.dist(a, b)
        if budget <= 0 and len(cur) >= 2:
            out.append(cur)
            cur = [b]
            budget = piece_len * rng.uniform(0.6, 1.4)
    if len(cur) >= 2:
        out.append(cur)
    return out


def _centroid(pts: list[tuple[float, float]]) -> tuple[float, float]:
    return (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts))


def _chain(strokes: list[list[tuple[float, float]]],
           join_r: float) -> list[list[tuple[float, float]]]:
    """Greedily link stroke ends within join_r into continuous polylines —
    the connecting segment is drawn (pen stays down through the join)."""
    if join_r <= 0 or len(strokes) < 2:
        return strokes
    pool = list(strokes)
    out: list[list[tuple[float, float]]] = []
    while pool:
        cur = list(pool.pop())
        grown = True
        while grown and pool:
            grown = False
            tx, ty = cur[-1]
            best_i, best_flip, best_d = -1, False, join_r
            for i, s in enumerate(pool):
                for flip, (px, py) in ((False, s[0]), (True, s[-1])):
                    d = math.hypot(px - tx, py - ty)
                    if d < best_d:
                        best_i, best_flip, best_d = i, flip, d
            if best_i >= 0:
                s = pool.pop(best_i)
                cur.extend(reversed(s) if best_flip else s)
                grown = True
        out.append(cur)
    return out


@register_source
class GlyphGram(SourceModule):
    id = "glyphgram"
    label = "Glyph grammar (asemic)"
    description = ("Hershey letterforms through a coherent distortion field, "
                   "chained into continuous lines. Almost reads; refuses.")
    Params = GlyphGramParams

    def generate(self, p: GlyphGramParams) -> PathDocument:
        rng = random.Random(p.seed * 7919 + 13)
        a = p.abstraction

        text = p.text.strip()
        if not text:
            words = []
            n = 0
            while n < p.soup_glyphs:
                w = "".join(rng.choice(_SOUP) for _ in range(rng.randint(2, 7)))
                words.append(w)
                n += len(w)
            text = " ".join(words)

        # vpype's units track `size` 1:1, so mm in ≈ mm out
        lc = vpype.text_block(text, width=p.width, font_name=p.font,
                              size=p.size, line_spacing=1.35)
        strokes = [[(float(z.real), float(z.imag)) for z in line] for line in lc]
        if not strokes:
            raise ValueError("the chosen font renders none of this text — try soup (empty text)")
        step = min(max(p.size / 12.0, 0.8), 2.5)
        strokes = [_densify(s, step) for s in strokes]

        xs = [x for s in strokes for x, _ in s]
        ys = [y for s in strokes for _, y in s]
        field = _SmoothField(min(xs), min(ys), max(xs), max(ys),
                             cell=p.size * 2.2, rng=rng)

        # --- coherent destruction, all strengths driven by `abstraction` ----
        # at a=0 strokes stay whole (letters nearly read); cutting only gets
        # aggressive past mid-abstraction, and even confetti stays field-bound
        piece_len = p.size * (2.6 - 2.2 * a)
        drop_p = 0.02 + 0.25 * a * a
        rot_max = math.pi * (a ** 1.6)                     # up to 180° at a=1
        drift = p.scatter * a
        swap_p = 0.5 * max(a - 0.5, 0.0)                   # recombination, late

        frags: list[list[tuple[float, float]]] = []
        for stroke in strokes:
            frags.extend(_cut(stroke, max(piece_len, 1.0), rng))
        frags = [f for f in frags if rng.random() > drop_p]
        if not frags:
            frags = [strokes[0]]

        # recombine: swap fragments' home positions across slots (high a only)
        homes = [_centroid(f) for f in frags]
        for i in range(len(frags)):
            if rng.random() < swap_p:
                j = rng.randrange(len(frags))
                homes[i], homes[j] = homes[j], homes[i]

        placed: list[list[tuple[float, float]]] = []
        for f, (hx, hy) in zip(frags, homes):
            cx, cy = _centroid(f)
            # rigid part from the field AT the fragment: neighbours rotate and
            # scale together (plus a whisper of private jitter so the warp
            # doesn't go laminar)
            ang = rot_max * field.at(cx, cy, 2) + rng.uniform(-0.08, 0.08) * rot_max
            scale = 1.0 + 0.6 * a * field.at(cx, cy, 3)
            c, s = math.cos(ang), math.sin(ang)
            warped = []
            for x, y in f:
                dx, dy = (x - cx) * scale, (y - cy) * scale
                rx, ry = cx + dx * c - dy * s, cy + dx * s + dy * c
                # displacement sampled AT EACH POINT: the differential bends
                # strokes — glyphs melt instead of teleporting
                px, py = rx + (hx - cx), ry + (hy - cy)
                warped.append((px + drift * field.at(px, py, 0),
                               py + drift * field.at(px, py, 1)))
            placed.append(warped)

        # mirror echoes BEFORE chaining: ghost fragments reflected about the
        # composition centre (echoing after would duplicate whole chained
        # lines — a dominating cross instead of a whisper)
        if placed and p.echoes:
            exs = [x for f in placed for x, _ in f]
            eys = [y for f in placed for _, y in f]
            mx, my = (min(exs) + max(exs)) / 2, (min(eys) + max(eys)) / 2
            for _ in range(p.echoes):
                subset = [f for f in placed if rng.random() < 0.3] or placed[:1]
                ang = rng.uniform(0, math.pi)
                c, s = math.cos(2 * ang), math.sin(2 * ang)
                for f in subset:
                    placed.append([
                        (mx + (x - mx) * c + (y - my) * s,
                         my + (x - mx) * s - (y - my) * c) for x, y in f
                    ])

        # continuity: chain stroke ends into long continuous lines — this is
        # what turns stamped glyph bits into one hand writing almost-language;
        # a single smoothing pass rounds the joins into the same gesture
        join_r = p.size * (0.12 + 1.1 * p.continuity)
        placed = [_smooth(f) for f in _chain(placed, join_r)]

        # machine frame: no negatives
        minx = min(x for f in placed for x, _ in f)
        miny = min(y for f in placed for _, y in f)
        shift_x, shift_y = max(0.0, -minx), max(0.0, -miny)
        paths = [Path(points=[(x + shift_x, y + shift_y) for x, y in f], filled=False)
                 for f in placed]

        return PathDocument(
            layers=[Layer(id=1, name="glyphgram", paths=paths)],
            source=f"glyphgram:{p.font} a={p.abstraction}",
        )
