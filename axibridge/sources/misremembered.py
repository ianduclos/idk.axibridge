"""Misremembered image — lossy *recall*, not reproduction.

Not thresholding, not halftone: the generator looks at the image the way
memory does. It extracts a cheap structure field (gradient magnitude over
the toned grayscale), then greedily spends a small ``budget`` of primitives
on it — long strokes traced along strong coherent edges, scrubbed-in
scribbles over the dark masses, searching hatches along the tonal contours
of the mid-dark regions. Each primitive carries a confidence from the
structure it explains, and confidence controls the mark: high → one long
firm polyline; low → short, broken, searching marks with lateral scatter.
Big masses come out right; the details are confabulated, the way memory
confabulates. ``budget`` is THE dial (≈40 = dream of the image, ≈400 =
portrait) and is numeric so an animation can literally remember harder
over master_t. (See docs/IDEAS-generators.md §3.)

v2 anti-blob-machine notes: masses follow the image's actual silhouette
(field-clipped serpentine scribble, not a radial amoeba), midtones get a
``tone`` share of the budget (isophote hatching — this is what makes two
different photographs recall differently), and the trace anchor is biased
by a per-seed field so each seed remembers a different reading of the
same image instead of the same argmax layout.
"""

from __future__ import annotations

import math
import random
from typing import Literal

import numpy as np
from pydantic import Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams

# mark geometry scales with the working canvas (~800 px wide normally):
_TUBE_FRAC = 0.009   # of width: radius a stroke "explains" around itself
_ARM_FRAC = 0.11     # of width: cap on one traced arm — long contours come
                     # out as several overlapping recalled pieces, not one trace
_BLOB_FRAC = 0.11    # of width: largest mass one scribble/blob may claim
_BLOB_SHARE = 0.12   # fraction of the budget the dark masses may claim


class MisrememberedParams(PixelGenParams):
    budget: int = Field(default=120, ge=10, le=800, title="Primitive budget",
                        description="Strokes + masses to spend — 40 is a dream of the "
                                    "image, 400 a portrait; tweenable")
    detail: float = Field(default=0.5, ge=0.0, le=1.0, title="Detail",
                          description="Edge sensitivity — high traces faint structure "
                                      "too, low keeps only the big masses")
    tone: float = Field(default=0.35, ge=0.0, le=1.0, title="Tonal recall",
                        description="Share of the stroke budget spent hatching mid-dark "
                                    "areas along their tonal contours — 0 = edges only")
    mass_style: Literal["scribble", "blob", "off"] = Field(
        default="scribble", title="Mass style",
        description="Dark masses: scrubbed-in serpentine that follows the actual "
                    "silhouette, closed amoeba blob (v1), or none")
    seed: int = Field(default=0, ge=0, le=99999, title="Seed",
                      json_schema_extra={"group": "Fine tuning"})


def _bilinear(a: np.ndarray, x: float, y: float) -> float:
    h, w = a.shape
    x = min(max(x, 0.0), w - 1.001)
    y = min(max(y, 0.0), h - 1.001)
    x0, y0 = int(x), int(y)
    fx, fy = x - x0, y - y0
    return float(a[y0, x0] * (1 - fx) * (1 - fy) + a[y0, x0 + 1] * fx * (1 - fy)
                 + a[y0 + 1, x0] * (1 - fx) * fy + a[y0 + 1, x0 + 1] * fx * fy)


def _stamp(a: np.ndarray, x: float, y: float, r: float, factor: float = 0.0) -> None:
    """Multiply a disk around (x, y) by ``factor`` — 'this structure is explained'."""
    h, w = a.shape
    x0, x1 = max(int(x - r), 0), min(int(x + r) + 1, w)
    y0, y1 = max(int(y - r), 0), min(int(y + r) + 1, h)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    mask = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
    a[y0:y1, x0:x1][mask] *= factor


def _bias_field(shape: tuple[int, int], rng: random.Random, lo: float = 0.5) -> np.ndarray:
    """Blocky per-seed multiplier in [lo, 1]: tilts every argmax so different
    seeds anchor their recall in different places (v1 chased one global argmax
    and produced the same layout for every seed)."""
    h, w = shape
    cell = 32
    gh, gw = h // cell + 2, w // cell + 2
    g = np.array([[lo + (1.0 - lo) * rng.random() for _ in range(gw)]
                  for _ in range(gh)])
    return np.repeat(np.repeat(g, cell, 0), cell, 1)[:h, :w]


@register_source
class Misremembered(SourceModule):
    id = "misremembered"
    label = "Misremembered image"
    description = ("Recalls the image with a budget of strokes, scribbled masses and "
                   "tonal hatching — masses right, details confabulated; confidence "
                   "sets the character of every mark.")
    Params = MisrememberedParams

    def generate(self, params: MisrememberedParams) -> PathDocument:
        p = params
        sam = ImageSampler(p, blur_px=2.0)
        dark = np.asarray(sam.grid, dtype=np.float64)  # darkness 0..255
        gy, gx = np.gradient(dark)
        edge = np.hypot(gx, gy)
        peak = float(edge.max())
        if peak < 1e-9:
            raise ValueError("image has no structure to remember (flat after processing)")
        # blob field: heavily pooled darkness, so masses beat outlines
        mass = dark.copy()
        for _ in range(2):
            mass = (mass + np.roll(mass, 3, 0) + np.roll(mass, -3, 0)
                    + np.roll(mass, 3, 1) + np.roll(mass, -3, 1)) / 5.0
        rng = random.Random(p.seed)
        bias = _bias_field(edge.shape, rng)
        floor = (0.30 - 0.24 * p.detail) * peak  # tracing stops below this
        tube_r = max(2.0, sam.w * _TUBE_FRAC)
        max_steps = max(20, int(sam.w * _ARM_FRAC))
        blob_r_max = max(6.0, sam.w * _BLOB_FRAC)
        paths: list[Path] = []
        # masses first — the few big dark shapes are what memory keeps
        spent = 0
        if p.mass_style != "off":
            for _ in range(max(1, round(p.budget * _BLOB_SHARE))):
                if float(mass.max()) < 110.0:
                    break
                if p.mass_style == "blob":
                    paths.append(self._blob(mass, blob_r_max, rng))
                else:
                    paths.extend(self._scrub(mass, blob_r_max, rng))
                spent += 1
        # split the stroke budget: edges carry the drawing, the tone share
        # hatches the mid-dark fields the edge pass is blind to
        stroke_budget = max(p.budget - spent, 0)
        n_tone = round(stroke_budget * p.tone)
        n_edge = stroke_budget - n_tone
        # strokes along coherent edges; when the strong structure is spent,
        # recall strains — the threshold drops and fainter (lower-confidence)
        # details get confabulated in
        for i in range(n_edge):
            report_progress((spent + i) / p.budget, "remembering")
            while float(edge.max()) <= floor:
                floor *= 0.55
                if floor < 0.03 * peak:
                    break
            if floor < 0.03 * peak:
                break  # nothing left that could plausibly be remembered
            stroke = self._trace(edge, gx, gy, bias, floor, tube_r, max_steps)
            if stroke is not None:
                conf = stroke[1] / peak
                paths.extend(self._mark(stroke[0], conf, rng))
        # tonal recall: searching hatches that ride the isophotes of the
        # darkness field — mid-gray masses stop vanishing from memory
        cover = np.ones_like(dark)
        for i in range(n_tone):
            report_progress((spent + n_edge + i) / p.budget, "remembering tone")
            stroke = self._tone_stroke(dark, gx, gy, cover, rng, tube_r, max_steps)
            if stroke is not None:
                paths.extend(self._mark(stroke[0], stroke[1], rng))
        s = p.width / sam.w
        out = [Path(points=[(max(x * s, 0.0), max(y * s, 0.0)) for x, y in path.points],
                    filled=path.filled) for path in paths]
        return PathDocument(
            layers=[Layer(id=1, name="misremembered", color="#26241f", paths=out)],
            width=p.width, height=sam.h * s, source=f"misremembered {p.image}",
        )

    def _trace(self, edge: np.ndarray, gx: np.ndarray, gy: np.ndarray,
               bias: np.ndarray, floor: float, tube_r: float, max_steps: int):
        """Trace a streamline along the strongest remaining (bias-tilted) edge;
        returns (points, mean-explained-magnitude) or None."""
        iy, ix = np.unravel_index(int(np.argmax(edge * bias)), edge.shape)
        seed_pt = (float(ix), float(iy))

        def arm(sign: float) -> tuple[list[tuple[float, float]], list[float]]:
            x, y = seed_pt
            dx, dy = _bilinear(gy, x, y), -_bilinear(gx, x, y)  # along-edge
            n = math.hypot(dx, dy)
            if n < 1e-9:
                return [], []
            dx, dy = sign * dx / n, sign * dy / n
            pts, mags = [], []
            for _ in range(max_steps):
                x, y = x + dx * 2.0, y + dy * 2.0
                if not (0 <= x < edge.shape[1] and 0 <= y < edge.shape[0]):
                    break
                m = _bilinear(edge, x, y)
                if m < floor:
                    break
                ndx, ndy = _bilinear(gy, x, y), -_bilinear(gx, x, y)
                nn = math.hypot(ndx, ndy)
                if nn < 1e-9:
                    break
                ndx, ndy = ndx / nn, ndy / nn
                if ndx * dx + ndy * dy < 0:
                    ndx, ndy = -ndx, -ndy  # keep marching the same way
                if ndx * dx + ndy * dy < 0.3:
                    break  # edge direction lost coherence
                dx, dy = ndx, ndy
                pts.append((x, y))
                mags.append(m)
            return pts, mags

        fwd, fmag = arm(1.0)
        bwd, bmag = arm(-1.0)
        pts = bwd[::-1] + [seed_pt] + fwd
        mags = bmag + [_bilinear(edge, *seed_pt)] + fmag
        # explained: fade the tube around the trace so the next argmax moves on
        for x, y in pts[::2]:
            _stamp(edge, x, y, tube_r, 0.08)
        _stamp(edge, *seed_pt, tube_r, 0.08)
        if len(pts) < 4:
            return None
        return pts, sum(mags) / len(mags)

    def _tone_stroke(self, dark: np.ndarray, gx: np.ndarray, gy: np.ndarray,
                     cover: np.ndarray, rng: random.Random,
                     tube_r: float, max_steps: int):
        """One tonal hatch: anchor on a dark-ish uncovered spot (probed, not
        argmax — tonal recall is diffuse), ride the isophote of the darkness
        field, stop when the ground turns light. Returns (points, conf)."""
        h, w = dark.shape
        best, bestv = None, 60.0  # ignore near-white ground entirely
        for _ in range(24):
            x, y = rng.uniform(1.0, w - 2.0), rng.uniform(1.0, h - 2.0)
            v = _bilinear(dark, x, y) * _bilinear(cover, x, y)
            if v > bestv:
                best, bestv = (x, y), v
        if best is None:
            return None
        x, y = best
        dx, dy = _bilinear(gy, x, y), -_bilinear(gx, x, y)  # isophote direction
        n = math.hypot(dx, dy)
        if n < 1e-9:  # flat patch: remember it in a made-up direction
            ang = rng.random() * math.tau
            dx, dy = math.cos(ang), math.sin(ang)
        else:
            dx, dy = dx / n, dy / n
        if rng.random() < 0.5:
            dx, dy = -dx, -dy
        pts = [(x, y)]
        darks = [_bilinear(dark, x, y)]
        steps = int(max_steps * (0.35 + 0.65 * darks[0] / 255.0))
        for _ in range(steps):
            ndx, ndy = _bilinear(gy, x, y), -_bilinear(gx, x, y)
            nn = math.hypot(ndx, ndy)
            if nn > 1e-9:
                ndx, ndy = ndx / nn, ndy / nn
                if ndx * dx + ndy * dy < 0:
                    ndx, ndy = -ndx, -ndy
                # blend keeps the stroke alive through flat tone instead of
                # dying the moment the gradient goes quiet
                bx, by = dx * 0.6 + ndx * 0.4, dy * 0.6 + ndy * 0.4
                bn = math.hypot(bx, by) or 1.0
                dx, dy = bx / bn, by / bn
            x, y = x + dx * 2.0, y + dy * 2.0
            if not (0 <= x < w - 1 and 0 <= y < h - 1):
                break
            d = _bilinear(dark, x, y)
            if d < 55.0:
                break  # ran into the light
            pts.append((x, y))
            darks.append(d)
        if len(pts) < 4:
            return None
        for px, py in pts[::3]:
            _stamp(cover, px, py, tube_r * 2.0, 0.25)
        mean_dark = sum(darks) / len(darks)
        return pts, 0.2 + 0.4 * mean_dark / 255.0  # always the searching hand

    def _mark(self, pts: list[tuple[float, float]], conf: float,
              rng: random.Random) -> list[Path]:
        """Confidence → character. Firm single polyline when sure; short,
        broken, laterally-scattered searching marks when not."""
        conf = min(max(conf, 0.0), 1.0)
        if conf > 0.55:
            # one firm stroke — but recalled, not traced: a slow lateral
            # drift keeps even confident lines slightly off-true
            amp = (1.0 - conf) * 5.0 + 0.8
            freq = 0.04 + rng.random() * 0.05  # each stroke drifts at its own pace
            phase = rng.random() * math.tau
            drifted = []
            for j, (x, y) in enumerate(pts):
                a, b = pts[max(j - 1, 0)], pts[min(j + 1, len(pts) - 1)]
                tx, ty = b[0] - a[0], b[1] - a[1]
                tn = math.hypot(tx, ty) or 1.0
                lat = math.sin(j * freq + phase) * amp
                drifted.append((x - ty / tn * lat, y + tx / tn * lat))
            return [Path(points=_smooth(drifted), filled=False)]
        n_seg = 2 + int((0.55 - conf) * 5)  # 2..4 fragments
        n_seg = min(n_seg, max(len(pts) // 4, 1), 4)
        chunk = len(pts) // n_seg
        out: list[Path] = []
        wander = (1.0 - conf) * 9.0   # px of lateral scatter — the confabulation
        drift = (0.9 - conf) * 16.0   # px each fragment may sit off-true
        for k in range(n_seg):
            seg = pts[k * chunk: (k + 1) * chunk]
            seg = seg[: max(int(len(seg) * 0.72), 2)]  # gaps between fragments
            if len(seg) < 2:
                continue
            ox = (rng.random() - 0.5) * drift
            oy = (rng.random() - 0.5) * drift
            freq = 0.15 + rng.random() * 0.14
            phase = rng.random() * math.tau
            jittered = []
            for j, (x, y) in enumerate(seg):
                a, b = seg[max(j - 1, 0)], seg[min(j + 1, len(seg) - 1)]
                tx, ty = b[0] - a[0], b[1] - a[1]
                tn = math.hypot(tx, ty) or 1.0
                lat = math.sin(j * freq + phase) * wander  # searching wobble
                jittered.append((x + ox - ty / tn * lat, y + oy + tx / tn * lat))
            out.append(Path(points=_smooth(jittered), filled=False))
        return out

    def _scrub(self, mass: np.ndarray, r_max: float, rng: random.Random) -> list[Path]:
        """Scrubbed-in mass: serpentine chords clipped by the mass field
        itself, so the scribble follows the actual silhouette (a tree stays
        tree-shaped) instead of the v1 radial amoeba. One continuous path,
        randomly oriented per mass."""
        peak = float(mass.max())
        iy, ix = np.unravel_index(int(np.argmax(mass)), mass.shape)
        cx, cy = float(ix), float(iy)
        ang = rng.random() * math.tau
        dxa, dya = math.cos(ang), math.sin(ang)          # chord direction
        nxa, nya = -dya, dxa                             # stepping direction
        spacing = max(2.5, r_max / rng.uniform(6.0, 11.0))  # each mass scrubs at its own density
        lvl = 0.55 * peak
        chords: list[list[tuple[float, float]]] = []
        o = -r_max
        while o <= r_max:
            run: list[tuple[float, float]] = []
            # each pass of the hand wobbles at its own pace — a fixed recipe
            # reads as chain-link fencing, not scrubbing
            freq = rng.uniform(0.28, 0.7)
            wob_amp = spacing * rng.uniform(0.25, 0.55)
            phase = rng.random() * math.tau
            s = -r_max
            j = 0
            while s <= r_max:
                x = cx + nxa * o + dxa * s
                y = cy + nya * o + dya * s
                inside = (0.0 <= x < mass.shape[1] - 1 and 0.0 <= y < mass.shape[0] - 1
                          and _bilinear(mass, x, y) > lvl)
                if inside:
                    lat = math.sin(j * freq + phase) * wob_amp
                    run.append((x + nxa * lat, y + nya * lat))
                    j += 1
                elif run:
                    break  # one contiguous run per chord — holes stay holes
                s += 2.0
            if len(run) >= 2:
                chords.append(run)
            o += spacing
        _stamp(mass, cx, cy, r_max * 1.2, 0.1)
        if not chords:
            return []
        pts: list[tuple[float, float]] = []
        for i, run in enumerate(chords):
            pts.extend(run if i % 2 == 0 else run[::-1])
        return [Path(points=_smooth(pts, passes=1), filled=False)]

    def _blob(self, mass: np.ndarray, r_max: float, rng: random.Random) -> Path:
        """v1 amoeba (kept as `mass_style="blob"`): probe 8 directions for
        where the darkness falls off, interpolate, wobble a little."""
        peak = float(mass.max())
        iy, ix = np.unravel_index(int(np.argmax(mass)), mass.shape)
        cx, cy = float(ix), float(iy)
        radii = []
        for k in range(8):
            t = math.tau * k / 8
            r = min(5.0, r_max)
            while r < r_max and _bilinear(mass, cx + r * math.cos(t),
                                          cy + r * math.sin(t)) > 0.55 * peak:
                r += 2.0
            radii.append(r)
        phase = rng.random() * math.tau
        pts = []
        for k in range(33):
            t = math.tau * k / 32
            f = t / math.tau * 8
            i0 = int(f) % 8
            fr = f - int(f)
            r = radii[i0] * (1 - fr) + radii[(i0 + 1) % 8] * fr
            rr = r * (1.0 + 0.14 * math.sin(3 * t + phase) + 0.07 * math.sin(5 * t - phase))
            pts.append((cx + rr * math.cos(t), cy + rr * math.sin(t)))
        pts.append(pts[0])
        _stamp(mass, cx, cy, max(radii) * 1.35, 0.1)
        return Path(points=pts, filled=True)


def _smooth(pts: list[tuple[float, float]], passes: int = 2) -> list[tuple[float, float]]:
    for _ in range(passes):
        if len(pts) < 3:
            return pts
        pts = ([pts[0]]
               + [((a[0] + 2 * b[0] + c[0]) / 4, (a[1] + 2 * b[1] + c[1]) / 4)
                  for a, b, c in zip(pts, pts[1:], pts[2:])]
               + [pts[-1]])
    return pts
