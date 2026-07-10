"""Misremembered image — lossy *recall*, not reproduction.

Not thresholding, not halftone: the generator looks at the image the way
memory does. It extracts a cheap structure field (gradient magnitude over
the toned grayscale), then greedily spends a small ``budget`` of primitives
on it — long strokes traced along strong coherent edges, closed blobs
dropped on dark masses. Each primitive carries a confidence from the
structure it explains, and confidence controls the mark: high → one long
firm polyline; low → short, broken, searching marks with lateral scatter.
Big masses come out right; the details are confabulated, the way memory
confabulates. ``budget`` is THE dial (≈40 = dream of the image, ≈400 =
portrait) and is numeric so an animation can literally remember harder
over master_t. (See docs/IDEAS-generators.md §3.)
"""

from __future__ import annotations

import math
import random

import numpy as np
from pydantic import Field

from ..model import Layer, Path, PathDocument
from ..registry import SourceModule, register_source, report_progress
from ._pixelgen import ImageSampler, PixelGenParams

# mark geometry scales with the working canvas (~800 px wide normally):
_TUBE_FRAC = 0.009   # of width: radius a stroke "explains" around itself
_ARM_FRAC = 0.11     # of width: cap on one traced arm — long contours come
                     # out as several overlapping recalled pieces, not one trace
_BLOB_FRAC = 0.11    # of width: largest mass one blob may claim
_BLOB_SHARE = 0.12   # fraction of the budget the dark masses may claim


class MisrememberedParams(PixelGenParams):
    budget: int = Field(default=120, ge=10, le=800, title="Primitive budget",
                        description="Strokes + blobs to spend — 40 is a dream of the "
                                    "image, 400 a portrait; tweenable")
    detail: float = Field(default=0.5, ge=0.0, le=1.0, title="Detail",
                          description="Edge sensitivity — high traces faint structure "
                                      "too, low keeps only the big masses")
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


@register_source
class Misremembered(SourceModule):
    id = "misremembered"
    label = "Misremembered image"
    description = ("Recalls the image with a budget of strokes and blobs — masses right, "
                   "details confabulated; confidence sets the character of every mark.")
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
        floor = (0.30 - 0.24 * p.detail) * peak  # tracing stops below this
        tube_r = max(2.0, sam.w * _TUBE_FRAC)
        max_steps = max(20, int(sam.w * _ARM_FRAC))
        blob_r_max = max(6.0, sam.w * _BLOB_FRAC)
        paths: list[Path] = []
        # masses first — the few big dark shapes are what memory keeps
        spent = 0
        for _ in range(max(1, round(p.budget * _BLOB_SHARE))):
            if float(mass.max()) < 110.0:
                break
            paths.append(self._blob(mass, blob_r_max, rng))
            spent += 1
        # the rest of the budget goes to strokes along coherent edges; when
        # the strong structure is spent, recall strains — the threshold drops
        # and fainter (lower-confidence) details get confabulated in
        for i in range(spent, p.budget):
            report_progress(i / p.budget, "remembering")
            while float(edge.max()) <= floor:
                floor *= 0.55
                if floor < 0.03 * peak:
                    break
            if floor < 0.03 * peak:
                break  # nothing left that could plausibly be remembered
            stroke = self._trace(edge, gx, gy, floor, tube_r, max_steps)
            if stroke is not None:
                conf = stroke[1] / peak
                paths.extend(self._mark(stroke[0], conf, rng))
        s = p.width / sam.w
        out = [Path(points=[(max(x * s, 0.0), max(y * s, 0.0)) for x, y in path.points],
                    filled=path.filled) for path in paths]
        return PathDocument(
            layers=[Layer(id=1, name="misremembered", color="#26241f", paths=out)],
            width=p.width, height=sam.h * s, source=f"misremembered {p.image}",
        )

    def _trace(self, edge: np.ndarray, gx: np.ndarray, gy: np.ndarray,
               floor: float, tube_r: float, max_steps: int):
        """Trace a streamline along the strongest remaining edge; returns
        (points, mean-explained-magnitude) or None."""
        iy, ix = np.unravel_index(int(np.argmax(edge)), edge.shape)
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

    def _mark(self, pts: list[tuple[float, float]], conf: float,
              rng: random.Random) -> list[Path]:
        """Confidence → character. Firm single polyline when sure; short,
        broken, laterally-scattered searching marks when not."""
        conf = min(max(conf, 0.0), 1.0)
        if conf > 0.55:
            # one firm stroke — but recalled, not traced: a slow lateral
            # drift keeps even confident lines slightly off-true
            amp = (1.0 - conf) * 5.0 + 0.8
            phase = rng.random() * math.tau
            drifted = []
            for j, (x, y) in enumerate(pts):
                a, b = pts[max(j - 1, 0)], pts[min(j + 1, len(pts) - 1)]
                tx, ty = b[0] - a[0], b[1] - a[1]
                tn = math.hypot(tx, ty) or 1.0
                lat = math.sin(j * 0.06 + phase) * amp
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
            phase = rng.random() * math.tau
            jittered = []
            for j, (x, y) in enumerate(seg):
                a, b = seg[max(j - 1, 0)], seg[min(j + 1, len(seg) - 1)]
                tx, ty = b[0] - a[0], b[1] - a[1]
                tn = math.hypot(tx, ty) or 1.0
                lat = math.sin(j * 0.22 + phase) * wander  # searching wobble
                jittered.append((x + ox - ty / tn * lat, y + oy + tx / tn * lat))
            out.append(Path(points=_smooth(jittered), filled=False))
        return out

    def _blob(self, mass: np.ndarray, r_max: float, rng: random.Random) -> Path:
        """Amoeba around the strongest remaining mass: probe 8 directions for
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
