"""Glyph grammar — Hershey typography pushed to total abstraction.

Oehlen-pass item 4 (docs/IDEAS-oehlen-pass.md): single-stroke Hershey
letterforms (plotter-honest, no outlines to fill) fed through destruction
rules — fragment, drop, displace, over-rotate, re-scale, recombine across
slots, mirror-echo — with one master `abstraction` dial running from
"almost reads" to pure scaffold. The near-figuration device from the
*Computer Paintings*: shapes that almost resolve into letters and refuse.

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
    echoes: int = Field(default=1, ge=0, le=4, title="Mirror echoes",
                        description="Re-stamp a fragment subset reflected about the centre")
    scatter: float = Field(default=12.0, ge=0.0, le=60.0, title="Scatter (mm)",
                           description="How far displaced fragments may travel",
                           json_schema_extra={"group": "Fine tuning"})
    soup_glyphs: int = Field(default=48, ge=8, le=200, title="Soup glyphs",
                             description="Glyph count when text is empty",
                             json_schema_extra={"group": "Fine tuning"})
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")


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


def _place(pts, cx, cy, angle, scale, tx, ty):
    """Rotate+scale about (cx, cy), then translate — one fragment's chaos."""
    c, s = math.cos(angle), math.sin(angle)
    out = []
    for x, y in pts:
        dx, dy = (x - cx) * scale, (y - cy) * scale
        out.append((cx + dx * c - dy * s + tx, cy + dx * s + dy * c + ty))
    return out


@register_source
class GlyphGram(SourceModule):
    id = "glyphgram"
    label = "Glyph grammar (asemic)"
    description = ("Hershey letterforms through destruction rules — fragment, "
                   "displace, recombine, mirror-echo. Almost reads; refuses.")
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

        # --- destruction pipeline, all strengths driven by `abstraction` ----
        piece_len = p.size * (1.6 - 1.45 * a)              # long → confetti
        drop_p = 0.04 + 0.38 * a
        rot_max = math.pi * (a ** 1.4)                     # up to 180° at a=1
        scale_lo, scale_hi = 1.0 - 0.55 * a, 1.0 + 0.75 * a
        swap_p = 0.55 * a                                  # recombination
        drift = p.scatter * a

        frags: list[list[tuple[float, float]]] = []
        for stroke in strokes:
            frags.extend(_cut(stroke, max(piece_len, 1.0), rng))
        frags = [f for f in frags if rng.random() > drop_p]
        if not frags:
            frags = [strokes[0]]

        # recombine: swap fragments' home positions across slots
        homes = [_centroid(f) for f in frags]
        idx = list(range(len(frags)))
        for i in idx:
            if rng.random() < swap_p:
                j = rng.randrange(len(frags))
                homes[i], homes[j] = homes[j], homes[i]

        placed: list[list[tuple[float, float]]] = []
        for f, (hx, hy) in zip(frags, homes):
            cx, cy = _centroid(f)
            placed.append(_place(
                f, cx, cy,
                angle=rng.uniform(-rot_max, rot_max),
                scale=rng.uniform(scale_lo, scale_hi),
                tx=(hx - cx) + rng.uniform(-drift, drift),
                ty=(hy - cy) + rng.uniform(-drift, drift),
            ))

        # mirror echoes: ghost subsets reflected about the composition centre
        if placed and p.echoes:
            xs = [x for f in placed for x, _ in f]
            ys = [y for f in placed for _, y in f]
            mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            for _ in range(p.echoes):
                subset = [f for f in placed if rng.random() < 0.3] or placed[:1]
                ang = rng.uniform(0, math.pi)
                c, s = math.cos(2 * ang), math.sin(2 * ang)
                for f in subset:
                    placed.append([
                        (mx + (x - mx) * c + (y - my) * s,
                         my + (x - mx) * s - (y - my) * c) for x, y in f
                    ])

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
