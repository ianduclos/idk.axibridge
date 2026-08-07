"""Shape grammar with a transgression budget — near-order as the subject.

A Stiny-style shape grammar obeys itself almost everywhere: an axiom, a
handful of rewrite rules, each rule replacing a placed motif with affine
copies of itself. Then a small ``budget`` of *deliberate, rule-aware
violations* is spent at salient locations — near the composition's center,
on its symmetry axes — each one a placed motif rotated a few degrees off,
scaled off-module, or swapped for another rule's vocabulary. A grid perfect
except one cell rotated 3° isn't glitch aesthetics; it's a wrongness you
feel before you can point at it. (See docs/IDEAS-generators.md §4.)

Geometry is authored in **cubic bézier space**: motifs are lists of cubic
segments, rules act on control points via affine frames, and the curves are
flattened to polylines only at output (adaptive de Casteljau subdivision to
``flatten_tol``). The IPR stays polylines; the béziers exist so the output
reads as drawn curves, not polyline scaffolds.
"""

from __future__ import annotations

import math
import random
from typing import Literal

from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source, report_progress

# an affine frame is (a, b, c, d, e, f): (x, y) -> (a x + c y + e, b x + d y + f)
Frame = tuple[float, float, float, float, float, float]
Point = tuple[float, float]
Cubic = tuple[Point, Point, Point, Point]
#: a motif is subpaths of contiguous cubics (each subpath is one pen-down)
Motif = list[list[Cubic]]

_IDENT: Frame = (1, 0, 0, 1, 0, 0)
_MAX_EMISSIONS = 1400  # hard cap on placed motifs — path count stays Pi-sane


def _compose(m: Frame, n: Frame) -> Frame:
    """m ∘ n (apply n first)."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def _apply(m: Frame, p: Point) -> Point:
    a, b, c, d, e, f = m
    return (a * p[0] + c * p[1] + e, b * p[0] + d * p[1] + f)


def _trs(tx: float, ty: float, rot: float = 0.0, s: float = 1.0) -> Frame:
    cs, sn = s * math.cos(rot), s * math.sin(rot)
    return (cs, sn, -sn, cs, tx, ty)


def _mirror_x() -> Frame:
    return (-1, 0, 0, 1, 0, 0)


def _flatten(c: Cubic, tol: float, out: list[Point]) -> None:
    """Adaptive de Casteljau: subdivide until the control polygon is flat."""
    p0, p1, p2, p3 = c
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    n = math.hypot(dx, dy)
    if n < 1e-12:
        d = max(math.dist(p1, p0), math.dist(p2, p0))
    else:
        d = max(abs((p1[0] - p0[0]) * dy - (p1[1] - p0[1]) * dx),
                abs((p2[0] - p0[0]) * dy - (p2[1] - p0[1]) * dx)) / n
    if d <= tol:
        out.append(p3)
        return
    mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)  # noqa: E731
    ab, bc, cd = mid(p0, p1), mid(p1, p2), mid(p2, p3)
    abc, bcd = mid(ab, bc), mid(bc, cd)
    abcd = mid(abc, bcd)
    _flatten((p0, ab, abc, abcd), tol, out)
    _flatten((abcd, bcd, cd, p3), tol, out)


# ---------------------------------------------------------------------------
# the built-in grammars: motif vocabulary + rewrite rules
# ---------------------------------------------------------------------------

def _c(*pts: tuple[float, float]) -> Cubic:
    assert len(pts) == 4
    return pts  # type: ignore[return-value]


#: a bowed stem, base (0,0) → tip (0,-1) — the branching grammar's word
_STEM: Motif = [[_c((0, 0), (0.10, -0.35), (-0.08, -0.68), (0, -1))]]

#: a closed leaf/petal, base (0,0) → tip (0,-1) and back
_PETAL: Motif = [[
    _c((0, 0), (0.22, -0.30), (0.18, -0.75), (0, -1)),
    _c((0, -1), (-0.18, -0.75), (-0.22, -0.30), (0, 0)),
]]

#: an ogee-wave tile in a unit box, continuous across tile joins — the band
#: grammar's word; a curl hangs off the wave's midpoint
_TILE: Motif = [
    [_c((0, 0.5), (0.30, 0.05), (0.70, 0.95), (1, 0.5))],
    [_c((0.5, 0.5), (0.62, 0.68), (0.55, 0.82), (0.42, 0.72)),
     _c((0.42, 0.72), (0.33, 0.65), (0.40, 0.56), (0.48, 0.58))],
]

#: a tight spiral curl — the vocabulary that gets swapped IN as a violation
_CURL: Motif = [[
    _c((0, 0), (0.30, -0.45), (0.42, -0.60), (0.18, -0.72)),
    _c((0.18, -0.72), (-0.06, -0.84), (-0.10, -0.55), (0.06, -0.50)),
]]


class _Emission:
    """One placed motif: the unit a rule rewrites, and a violation perturbs."""

    __slots__ = ("frame", "motif", "anchor", "depth")

    def __init__(self, frame: Frame, motif: Motif, anchor: Point, depth: int):
        self.frame = frame
        self.motif = motif
        self.anchor = _apply(frame, anchor)  # placed: salience is measured here
        self.depth = depth


def _grow_branching(iterations: int) -> list[_Emission]:
    out: list[_Emission] = []
    sites: list[Frame] = [_trs(0.0, 0.0, 0.0, 1.0)]
    for depth in range(iterations):
        nxt: list[Frame] = []
        for f in sites:
            out.append(_Emission(f, _STEM, (0, -0.5), depth))
            if len(out) >= _MAX_EMISSIONS:
                return out
            tip = _trs(0.0, -1.0)
            for ang in (0.55, -0.55):
                nxt.append(_compose(f, _compose(tip, _trs(0, 0, ang, 0.72))))
        sites = nxt
    return out


def _grow_band(iterations: int) -> list[_Emission]:
    out: list[_Emission] = []
    tiles = min(iterations * 4, 48)
    for row in range(2):
        for k in range(tiles):
            if row == 0:
                f: Frame = _trs(float(k), 0.0)
            else:  # second row mirrored vertically: a reflective band
                f = _compose(_trs(float(k), 2.0), (1, 0, 0, -1, 0, 0))
            if k % 2 == 1:  # alternating reflection along the row: pm frieze
                f = _compose(f, _compose(_trs(1.0, 0.0), _mirror_x()))
            out.append(_Emission(f, _TILE, (0.5, 0.5), k))
            if len(out) >= _MAX_EMISSIONS:
                return out
    return out


def _grow_radial(iterations: int) -> list[_Emission]:
    out: list[_Emission] = []
    n = 11
    radius, scale = 1.6, 1.0
    for ring in range(iterations):
        for k in range(n):
            theta = math.tau * k / n + (math.tau / n / 2) * (ring % 2)
            f = _compose(_trs(0, 0, theta), _compose(_trs(0, -radius), _trs(0, 0, 0, scale)))
            out.append(_Emission(f, _PETAL, (0, -0.5), ring))
            if len(out) >= _MAX_EMISSIONS:
                return out
        radius *= 0.62
        scale *= 0.62
    return out


def _shift(motif: Motif, dx: float, dy: float) -> Motif:
    t = _trs(dx, dy)
    return [[tuple(_apply(t, q) for q in seg) for seg in sub]  # type: ignore[misc]
            for sub in motif]


# alien vocabulary per grammar — what a rule-swap violation drops into the
# violated frame. Chosen to share the host motif's local space so the swap
# reads as a wrong *word*, not a misplaced one: stems and petals live
# base (0,0) → tip (0,-1); the tile's alien hangs a petal inside its box.
_GRAMMARS = {
    "branching": (_grow_branching, _CURL),
    "band": (_grow_band, _shift(_PETAL, 0.5, 1.0)),
    "radial": (_grow_radial, _STEM),  # a petal that forgot to close
}


class GrammarParams(BaseModel):
    grammar: Literal["branching", "band", "radial"] = Field(
        default="branching", title="Grammar",
        description="Which built-in rule system to run")
    iterations: int = Field(default=5, ge=1, le=8, title="Iterations",
                            description="Rewrite generations (emitted motifs are capped)")
    size: float = Field(default=120.0, ge=10.0, le=280.0, title="Size (mm)",
                        description="Longest side of the composition")
    budget: int = Field(default=2, ge=0, le=16, title="Transgression budget",
                        description="How many placed motifs get deliberately violated")
    violation: float = Field(default=0.2, ge=0.0, le=1.0, title="Violation",
                             description="Magnitude of each transgression — small values "
                                         "are felt before they can be pointed at")
    salience_bias: float = Field(default=0.7, ge=0.0, le=1.0, title="Salience bias",
                                 description="0 = spend violations anywhere, 1 = at the "
                                             "most salient sites (center, symmetry axes)")
    flatten_tol: float = Field(default=0.2, ge=0.05, le=1.0, title="Flatness (mm)",
                               description="Bézier flattening tolerance at output",
                               json_schema_extra={"group": "Fine tuning"})
    seed: int = Field(default=0, ge=0, le=99999, title="Seed",
                      json_schema_extra={"group": "Fine tuning"})


@register_source
class Grammar(SourceModule):
    id = "grammar"
    orientation = "none"  # a square-ish field of shapes with no dominant axis
    label = "Grammar (transgression budget)"
    description = ("A shape grammar that obeys itself almost everywhere — and spends a "
                   "small budget of rule-aware violations at the most salient sites.")
    Params = GrammarParams

    def generate(self, params: GrammarParams) -> PathDocument:
        p = params
        grow, alien = _GRAMMARS[p.grammar]
        emissions = grow(p.iterations)
        report_progress(0.3, "grammar grown")
        self._transgress(emissions, alien, p)
        report_progress(0.5, "transgressions spent")

        # place all control points, size the composition off their hull
        # (béziers stay inside their control hulls), then flatten at a
        # tolerance that is exactly `flatten_tol` mm after scaling
        subpaths: list[list[Cubic]] = []
        for em in emissions:
            for sub in em.motif:
                subpaths.append([tuple(_apply(em.frame, q) for q in seg)  # type: ignore[misc]
                                 for seg in sub])
        xs = [q[0] for sub in subpaths for seg in sub for q in seg]
        ys = [q[1] for sub in subpaths for seg in sub for q in seg]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        s = p.size / max(w, h, 1e-9)
        ox, oy = -min(xs) * s + 2.0, -min(ys) * s + 2.0
        polys: list[list[Point]] = []
        for i, sub in enumerate(subpaths):
            if i % 64 == 0:
                report_progress(0.5 + 0.4 * i / len(subpaths))
            pts: list[Point] = [sub[0][0]]
            for seg in sub:
                _flatten(seg, p.flatten_tol / s, pts)
            polys.append(pts)
        paths = []
        for poly in polys:
            pts = [(x * s + ox, y * s + oy) for x, y in poly]
            closed = math.dist(pts[0], pts[-1]) < 1e-6
            if closed:
                pts[-1] = pts[0]
            paths.append(Path(points=pts, filled=False))
        return PathDocument(
            layers=[Layer(id=1, name="grammar", color="#26241f", paths=paths)],
            width=w * s + 4.0, height=h * s + 4.0,
            source=f"grammar {p.grammar}",
        )

    def _transgress(self, emissions: list[_Emission], alien: Motif,
                    p: GrammarParams) -> None:
        """Spend the budget: rank sites by salience, violate the winners in
        their own frames — rotation off-true, scale off-module, or a swap
        into another grammar's vocabulary. Rule-aware: the perturbation acts
        on the placed motif as a unit, never on points."""
        if p.budget == 0 or not emissions:
            return
        rng = random.Random(p.seed * 31 + 7)
        xs = [em.anchor[0] for em in emissions]
        ys = [em.anchor[1] for em in emissions]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)

        scales = {id(em): math.sqrt(abs(em.frame[0] * em.frame[3]
                                        - em.frame[1] * em.frame[2]))
                  for em in emissions}
        max_scale = max(scales.values()) or 1.0

        def salience(em: _Emission) -> float:
            dc = math.dist(em.anchor, (cx, cy)) / span
            da = min(abs(em.anchor[0] - cx), abs(em.anchor[1] - cy)) / span
            positional = (0.6 * (1.0 - min(dc * 2, 1.0))
                          + 0.4 * (1.0 - min(da * 4, 1.0)))
            # a violation nobody can see isn't a transgression: discount
            # motifs too small to carry one
            return positional * (0.35 + 0.65 * scales[id(em)] / max_scale)

        scored = sorted(
            emissions,
            key=lambda em: p.salience_bias * salience(em)
                           + (1.0 - p.salience_bias) * rng.random(),
            reverse=True,
        )
        for em in scored[: p.budget]:
            kind = rng.random()
            # perturb about the motif's own anchor, in its placed frame
            ax, ay = em.anchor
            if kind < 0.45:  # rotated a few degrees
                ang = (0.08 + 0.45 * p.violation) * (1 if rng.random() < 0.5 else -1)
                delta = _compose(_trs(ax, ay, ang), _trs(-ax, -ay))
                em.frame = _compose(delta, em.frame)
            elif kind < 0.80:  # scaled off-module
                f = 1.0 + (0.12 + 0.50 * p.violation) * (1 if rng.random() < 0.5 else -1)
                delta = _compose(_trs(ax, ay, 0, f), _trs(-ax, -ay))
                em.frame = _compose(delta, em.frame)
            else:  # rule swap: another grammar's word in this one's frame
                em.motif = alien
