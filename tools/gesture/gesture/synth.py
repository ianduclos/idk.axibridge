"""Synthetic ground truth: known strokes → rendered ink raster (stage 0).

Everything is in canvas **pixels** (see ../README.md). Raster convention:
pixel centres sit at integer coordinates, so point (x, y) lands in array
element [round(y), round(x)] of the rendered image.

Strokes built here carry their exact generating model in `meta`, so an
extractor or a κ(s) fitter can be scored against the truth:
    meta = {"breaks": [...], "kappas": [...], "step": float, "types": [...],
            "start": [x, y], "heading": float}
`breaks`/`kappas` are the piecewise-linear κ(s) knots in px / 1/px, exactly
as `curvature.integrate_kappa` takes them. Translating a stroke (as scene
builders do) updates `start`; κ(s) is invariant under translation.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter, gaussian_filter1d, zoom
from shapely.geometry import LineString
from shapely.ops import nearest_points

from .core import Drawing, Stroke
from .curvature import arclength, integrate_kappa

FINE_STEP = 0.5  # px; integration step for ground-truth strokes

Size = tuple[int, int]


def _size(size) -> Size:
    if np.isscalar(size):
        return (int(size), int(size))
    return (int(size[0]), int(size[1]))


# --------------------------------------------------------------------------
# strokes
# --------------------------------------------------------------------------

def _knots(rng: np.random.Generator, length: float, n: int) -> np.ndarray:
    """n segments with random lengths, none shorter than 0.3·length/n."""
    min_frac = 0.3 / n
    gaps = min_frac + (1.0 - n * min_frac) * rng.dirichlet(np.ones(n))
    return np.concatenate([[0.0], np.cumsum(gaps) * length])


def _kappa_sequence(rng: np.random.Generator, n: int, kappa_max: float,
                    p_line: float = 0.25, p_arc: float = 0.25,
                    sign: float | None = None, p_flip: float = 0.5,
                    k_min_frac: float = 0.1) -> np.ndarray:
    """Knot values for a continuous piecewise-linear κ(s).

    Each segment picks a target: 0 (line, or a clothoid easing to zero), the
    current κ (arc), or a fresh random κ (clothoid). With `sign` given, fresh
    values keep that sign except with probability `p_flip` (an inflection).
    """
    def fresh(cur_sign):
        mag = rng.uniform(k_min_frac, 1.0) * kappa_max
        if sign is None:
            return rng.choice([-1.0, 1.0]) * mag, cur_sign
        s = -cur_sign if rng.random() < p_flip else cur_sign
        return s * mag, s

    cur_sign = 1.0 if sign is None else float(np.sign(sign) or 1.0)
    k = np.zeros(n + 1)
    if sign is None:
        k[0] = 0.0 if rng.random() < 0.4 else fresh(cur_sign)[0]
    else:
        k[0], cur_sign = fresh(cur_sign)
    for i in range(n):
        r = rng.random()
        if r < p_line:
            k[i + 1] = 0.0
        elif r < p_line + p_arc:
            k[i + 1] = k[i]
        else:
            k[i + 1], cur_sign = fresh(cur_sign)
    return k


def _segment_types(kappas: np.ndarray) -> list[str]:
    out = []
    for a, b in zip(kappas[:-1], kappas[1:]):
        if a == 0.0 and b == 0.0:
            out.append("line")
        elif a == b:
            out.append("arc")
        else:
            out.append("clothoid")
    return out


def _is_simple(points: np.ndarray) -> bool:
    p = points[:: max(1, len(points) // 1500)]
    if len(p) < 3:
        return True
    if not np.array_equal(p[-1], points[-1]):
        p = np.vstack([p, points[-1:]])
    return LineString(p).is_simple


def _model_stroke(breaks, kappas, step, start, heading, extra_meta=None) -> Stroke:
    pts = integrate_kappa(breaks, kappas, step, start=start, heading=heading)
    meta = {
        "breaks": [float(b) for b in breaks],
        "kappas": [float(k) for k in kappas],
        "step": float(breaks[-1] / (len(pts) - 1)),
        "types": _segment_types(np.asarray(kappas)),
        "start": [float(start[0]), float(start[1])],
        "heading": float(heading),
    }
    if extra_meta:
        meta.update(extra_meta)
    return Stroke(pts, meta=meta)


def random_clothoid_stroke(rng: np.random.Generator, length: float, n_segments: int,
                           kappa_max: float, start=(0.0, 0.0), heading: float = 0.0,
                           *, step: float = FINE_STEP, sign: float | None = None,
                           p_flip: float = 0.5, max_tries: int = 12) -> Stroke:
    """A random line/arc/clothoid stroke with exact piecewise-linear κ(s).

    length in px, kappa_max in 1/px, heading in radians. The stroke is
    rejected and redrawn if it crosses itself; after `max_tries` the κ knots
    are shrunk toward zero (a line is always simple) until it does not.
    `sign`/`p_flip` bias the κ sign (see `_kappa_sequence`).
    """
    breaks = _knots(rng, length, n_segments)
    kappas = np.zeros(n_segments + 1)
    for _ in range(max_tries):
        breaks = _knots(rng, length, n_segments)
        kappas = _kappa_sequence(rng, n_segments, kappa_max, sign=sign, p_flip=p_flip)
        pts = integrate_kappa(breaks, kappas, step, start=start, heading=heading)
        if _is_simple(pts):
            return _model_stroke(breaks, kappas, step, start, heading)
    while True:
        kappas = kappas * 0.7
        pts = integrate_kappa(breaks, kappas, step, start=start, heading=heading)
        if _is_simple(pts) or np.max(np.abs(kappas)) < 1e-9:
            return _model_stroke(breaks, kappas, step, start, heading, {"shrunk": True})


# --------------------------------------------------------------------------
# geometric helpers
# --------------------------------------------------------------------------

def _translate(stroke: Stroke, d) -> Stroke:
    d = np.asarray(d, dtype=np.float64)
    meta = dict(stroke.meta)
    if "start" in meta:
        meta["start"] = [float(meta["start"][0] + d[0]), float(meta["start"][1] + d[1])]
    return Stroke(stroke.points + d, width=None if stroke.width is None else stroke.width.copy(),
                  closed=stroke.closed, meta=meta)


def _rotate(stroke: Stroke, angle: float, about) -> Stroke:
    c, s = np.cos(angle), np.sin(angle)
    R = np.array([[c, -s], [s, c]])
    about = np.asarray(about, dtype=np.float64)
    pts = (stroke.points - about) @ R.T + about
    meta = dict(stroke.meta)
    if "heading" in meta:
        meta["heading"] = float(meta["heading"] + angle)
    if "start" in meta:
        meta["start"] = [float(v) for v in ((np.asarray(meta["start"]) - about) @ R.T + about)]
    return Stroke(pts, width=None if stroke.width is None else stroke.width.copy(),
                  closed=stroke.closed, meta=meta)


def _random_fit(stroke: Stroke, size: Size, margin: float,
                rng: np.random.Generator) -> Stroke | None:
    """Translate (rotating if needed) to a random position fully inside the
    canvas with `margin` px clearance; None if it cannot fit."""
    W, H = size
    for k in range(24):
        st = stroke if k == 0 else _rotate(stroke, rng.uniform(0, 2 * np.pi),
                                           stroke.points.mean(axis=0))
        lo, hi = st.points.min(axis=0), st.points.max(axis=0)
        free = np.array([W - 1 - 2 * margin, H - 1 - 2 * margin]) - (hi - lo)
        if np.all(free >= 0):
            target = margin + rng.uniform(0, 1, 2) * free
            return _translate(st, target - lo)
    return None


def _line(stroke: Stroke) -> LineString:
    p = stroke.points
    if stroke.closed:
        p = np.vstack([p, p[:1]])
    return LineString(p)


# --------------------------------------------------------------------------
# scenes
# --------------------------------------------------------------------------

def _centred_arc(length: float, kappa: float, heading: float, centre, step=FINE_STEP) -> Stroke:
    st = _model_stroke(np.array([0.0, length]), np.array([kappa, kappa]), step, (0.0, 0.0), heading)
    mid = st.points[len(st) // 2]
    return _translate(st, np.asarray(centre, dtype=np.float64) - mid)


def scene_x_crossing(size) -> Drawing:
    """Two gentle arcs crossing once near the canvas centre."""
    W, H = _size(size)
    m = min(W, H)
    c = (W / 2, H / 2)
    a = _centred_arc(0.7 * m, 0.6 / m, np.deg2rad(35), c)
    b = _centred_arc(0.7 * m, -0.4 / m, np.deg2rad(140), (c[0] + 0.03 * m, c[1] - 0.02 * m))
    return Drawing([a, b], source="synth:x_crossing", size=(W, H), meta={"scene": "x_crossing"})


def scene_t_junction(size) -> Drawing:
    """Stroke 0 is a long gentle arc; stroke 1 comes in from above and ENDS on
    stroke 0's interior (at 45% of its arc length)."""
    W, H = _size(size)
    m = min(W, H)
    a = _centred_arc(0.75 * m, 0.5 / m, np.deg2rad(5), (W / 2, H * 0.6))
    i = int(0.45 * (len(a) - 1))
    p = a.points[i]
    # build the stem outward from the junction, then reverse it so it ends there
    stem_len = 0.35 * m
    stem = _model_stroke(np.array([0.0, stem_len]), np.array([0.0, 1.2 / m]), FINE_STEP,
                         p, -np.pi / 2 + 0.15)
    rev = stem.points[::-1].copy()
    end_heading = float(np.arctan2(*(rev[-1] - rev[-2])[::-1]))
    b = Stroke(rev, meta={**stem.meta, "reversed": True, "ends_on": 0,
                          "junction": [float(p[0]), float(p[1])],
                          "end_heading": end_heading})
    return Drawing([a, b], source="synth:t_junction", size=(W, H), meta={"scene": "t_junction"})


def scene_closed_loop(size) -> Drawing:
    """One smooth closed blob (radius = Fourier-perturbed circle), closed=True."""
    W, H = _size(size)
    R = 0.3 * min(W, H)
    n = int(np.ceil(2 * np.pi * R * 1.3 / FINE_STEP))
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = R * (1 + 0.12 * np.cos(2 * t + 0.4) + 0.07 * np.cos(3 * t + 1.9) + 0.03 * np.sin(5 * t))
    pts = np.column_stack([W / 2 + r * np.cos(t), H / 2 + r * np.sin(t)])
    st = Stroke(pts, closed=True, meta={"shape": "fourier_blob", "R": R})
    return Drawing([st], source="synth:closed_loop", size=(W, H), meta={"scene": "closed_loop"})


def scene_random(rng: np.random.Generator, size, n_strokes: int = 8, *,
                 length_frac=(0.15, 0.5), n_segments=(2, 7), kappa_max_frac: float = 8.0,
                 margin: float = 8.0) -> Drawing:
    """Random clothoid strokes inside the canvas. Strokes may cross each other
    but never themselves. length_frac is relative to min(size); kappa_max is
    kappa_max_frac / min(size)."""
    W, H = _size(size)
    m = min(W, H)
    strokes = []
    while len(strokes) < n_strokes:
        L = rng.uniform(*length_frac) * m
        st = random_clothoid_stroke(rng, L, int(rng.integers(n_segments[0], n_segments[1] + 1)),
                                    kappa_max_frac / m, heading=rng.uniform(0, 2 * np.pi))
        placed = _random_fit(st, (W, H), margin, rng)
        if placed is not None:
            strokes.append(placed)
    return Drawing(strokes, source="synth:random", size=(W, H), meta={"scene": "random"})


def scene_matisse_like(rng: np.random.Generator, size, n_strokes: int | None = None, *,
                       line_width: float = 4.0, margin: float = 10.0) -> Drawing:
    """A few long, gently curving contour strokes: one κ sign per stroke with
    rare inflections, mostly arcs/clothoids, some strokes placed so they
    nearly touch a neighbour (gap of 1.5–3 line widths, centre to centre).
    Strokes get a tapered width profile from `with_width`."""
    W, H = _size(size)
    m = min(W, H)
    n_strokes = n_strokes if n_strokes is not None else int(rng.integers(3, 7))
    strokes: list[Stroke] = []
    near_pairs = []
    tries = 0
    while len(strokes) < n_strokes:
        tries += 1
        L = rng.uniform(0.6, 1.3) * m if tries < 200 else 0.4 * m
        st = random_clothoid_stroke(rng, L, int(rng.integers(3, 7)), 3.5 / m,
                                    heading=rng.uniform(0, 2 * np.pi),
                                    sign=rng.choice([-1.0, 1.0]), p_flip=0.15)
        placed = _random_fit(st, (W, H), margin, rng)
        if placed is None:
            continue
        lines = [_line(s) for s in strokes]
        cand = _line(placed)
        if strokes and rng.random() < 0.6:
            j = int(rng.integers(len(strokes)))
            pa, pb = nearest_points(cand, lines[j])
            v = np.array([pb.x - pa.x, pb.y - pa.y])
            d = float(np.hypot(*v))
            gap = rng.uniform(1.5, 3.0) * line_width
            if d > 1e-6:
                moved = _translate(placed, v * (1 - gap / d))
                lo, hi = moved.points.min(axis=0), moved.points.max(axis=0)
                inside = np.all(lo >= margin) and hi[0] <= W - 1 - margin and hi[1] <= H - 1 - margin
                ml = _line(moved)
                if inside and all(not ml.intersects(o) and ml.distance(o) >= 0.9 * gap for o in lines):
                    placed, cand = moved, ml
                    near_pairs.append((len(strokes), j, gap))
        if any(cand.intersects(o) for o in lines) and tries < 200:
            continue
        strokes.append(placed)
    strokes = [with_width(s, line_width, rng, taper=True, pool=bool(rng.random() < 0.3))
               for s in strokes]
    return Drawing(strokes, source="synth:matisse_like", size=(W, H),
                   meta={"scene": "matisse_like", "near_pairs": near_pairs})


# --------------------------------------------------------------------------
# width
# --------------------------------------------------------------------------

def _smooth_noise(rng: np.random.Generator, n: int, sd_samples: float, closed=False) -> np.ndarray:
    if n < 2:
        return np.zeros(n)
    z = gaussian_filter1d(rng.standard_normal(n), max(sd_samples, 0.5),
                          mode="wrap" if closed else "reflect")
    sdev = z.std()
    return z / sdev if sdev > 0 else z


def with_width(stroke: Stroke, base: float, rng: np.random.Generator,
               taper: bool = True, pool: bool = False) -> Stroke:
    """New Stroke with a plausible width profile (px, full width).

    base·(1 + 8% low-frequency wobble); `taper`: the last 10–25% of the arc
    length narrows smoothly to ~25% of base (pen lifting); `pool`: an ink blob
    at the start, up to ~1.8·base, decaying over ~2·base of arc length.
    """
    p = stroke.points
    s = arclength(np.vstack([p, p[:1]]) if stroke.closed else p)[: len(p)]
    L = max(s[-1], 1e-9)
    step = L / max(len(p) - 1, 1)
    w = base * (1 + 0.08 * _smooth_noise(rng, len(p), 25.0 / step, stroke.closed))
    model: dict = {"base": float(base)}
    if taper:
        frac = rng.uniform(0.10, 0.25)
        u = np.clip((s - (1 - frac) * L) / (frac * L), 0, 1)
        w = w * (1 - 0.75 * (0.5 - 0.5 * np.cos(np.pi * u)))
        model["taper_frac"] = float(frac)
    if pool:
        amp = rng.uniform(0.5, 0.8)
        w = w * (1 + amp * np.exp(-s / (2 * base)))
        model["pool_amp"] = float(amp)
    meta = dict(stroke.meta)
    meta["width_model"] = model
    return Stroke(p.copy(), width=np.maximum(w, 0.3), closed=stroke.closed, meta=meta)


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

def _norm_field(rng: np.random.Generator, shape, sigma: float) -> np.ndarray:
    """Unit-std Gaussian random field with correlation σ px. Large σ is
    generated on a coarse grid and bilinearly upsampled (same look, fast)."""
    f = max(1, int(sigma // 4))
    H, W = shape
    small = (H // f + 2, W // f + 2) if f > 1 else (H, W)
    z = rng.standard_normal(small).astype(np.float32)
    if sigma > 0:
        z = gaussian_filter(z, sigma / f)
    if f > 1:
        z = zoom(z, f, order=1)[:H, :W]
    return z / max(float(z.std()), 1e-9)


def render(drawing: Drawing, *, line_width: float = 4.0, width_jitter: float = 0.0,
           supersample: int = 4, blur_sigma: float = 0.6, paper_noise: float = 0.03,
           ink_noise: float = 0.0, seed: int = 0, use_stroke_width: bool = True) -> np.ndarray:
    """Rasterise a Drawing as ink on paper: uint8 (H, W), paper ≈ 255, ink ≈ 0.

    Strokes are unions of discs (round caps and joins) of diameter = per-point
    width (stroke.width if present and `use_stroke_width`, else `line_width`
    with low-frequency jitter of relative std `width_jitter` along s), drawn at
    `supersample`× and box-downsampled to coverage. Then Gaussian blur of
    `blur_sigma` px, paper grain/fibre texture of strength `paper_noise`, and
    low-frequency ink-density variation `ink_noise`. Deterministic per seed.
    Pixel centres are at integer coordinates.
    """
    W, H = _size(drawing.size)
    rng = np.random.default_rng(seed)
    ss = max(int(supersample), 1)
    img = Image.new("L", (W * ss, H * ss), 0)
    dr = ImageDraw.Draw(img)
    off = (ss - 1) / 2.0
    for st in drawing.strokes:
        p = st.points
        if len(p) == 0:
            continue
        has_w = use_stroke_width and st.width is not None
        wv = st.width if has_w else None
        if st.closed and len(p) > 1:
            p = np.vstack([p, p[:1]])
            if wv is not None:
                wv = np.concatenate([wv, wv[:1]])
        s = arclength(p)
        L = s[-1]
        w_min = float(np.min(wv)) if wv is not None else line_width * max(1 - 3 * width_jitter, 0.3)
        step = max(0.25, w_min / 8.0) / (ss / 4.0)  # ~1 supersampled px at ss=4
        n = max(int(np.ceil(L / step)), 1) + 1
        t = np.linspace(0, L, n)
        x = np.interp(t, s, p[:, 0]) if L > 0 else np.full(n, p[0, 0])
        y = np.interp(t, s, p[:, 1]) if L > 0 else np.full(n, p[0, 1])
        if wv is not None:
            w = np.interp(t, s, wv) if L > 0 else np.full(n, wv[0])
        else:
            w = np.full(n, float(line_width))
            if width_jitter > 0:
                w = w * (1 + width_jitter * _smooth_noise(rng, n, 30.0 / max(L / (n - 1), 1e-9),
                                                         st.closed))
                w = np.maximum(w, 0.3 * line_width)
        cx, cy, r = x * ss + off, y * ss + off, np.maximum(w * ss / 2.0 - 0.5, 0.0)
        for xi, yi, ri in zip(cx.tolist(), cy.tolist(), r.tolist()):
            dr.ellipse((xi - ri, yi - ri, xi + ri, yi + ri), fill=255)
    cov = np.asarray(img.resize((W, H), Image.Resampling.BOX), dtype=np.float32) / 255.0
    if blur_sigma > 0:
        cov = gaussian_filter(cov, blur_sigma)
    paper = np.ones((H, W), dtype=np.float32)
    if paper_noise > 0:
        tex = 0.6 * _norm_field(rng, (H, W), 0.0) + 0.8 * _norm_field(rng, (H, W), 3.0)
        paper = np.clip(1.0 - paper_noise * (1.0 + 0.5 * tex), 0.0, 1.0)
    dens = np.ones((H, W), dtype=np.float32)
    if ink_noise > 0:
        # low-frequency density variation, bounded: never fully drops out
        dens = 1.0 - ink_noise * np.clip(np.abs(_norm_field(rng, (H, W), 20.0)) / 2.5, 0.0, 1.0)
    out = paper * (1.0 - np.clip(cov, 0, 1) * dens)
    return np.clip(np.round(out * 255.0), 0, 255).astype(np.uint8)
