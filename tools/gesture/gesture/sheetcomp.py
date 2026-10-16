"""Sheet-level composition statistics, and a density/emptiness controller
around `regime_field.compose`.

results/sheet_composition-2026-10-16.md. Everything here works on an INK
MASK of the whole sheet (bool, rows × cols, ink True), so scans and our own
renders go through one measurement. Statistics are dimensionless: lengths
are fractions of `side` = sqrt(rows · cols) of the mask, so the mask
resolution and the sheet's pixel size drop out (above the resolution floor:
a line must survive the area-averaged downscale, see `normalise_mask`).

The profile (`profile(mask)` → dict, keys in PROFILE_KEYS)
  cover          ink area share
  lac_032..lac_25  log gliding-box lacunarity at box = 1/32, 1/16, 1/8, 1/4
                 side (clustering vs dispersion of ink; 0 = perfectly even)
  empty16        share of cells on a ~16-per-side grid with < 5 % of the
                 mean coverage (how much of the sheet is left alone)
  void_max       largest empty disk radius / side (distance to nearest ink;
                 the sheet edge is NOT ink, so margins count)
  void_share     share of the sheet farther than 0.05 side from any ink
  com_dx, com_dy ink centre of mass minus sheet centre, in sheet widths /
                 heights (y down)
  spread         radius of gyration of ink / side
  margin_ratio   ink share in the outer 10 % band ÷ that band's area share
  islands_1/_3   log count of ink islands after closing gaps of 1 % / 3 %
                 side (one figure vs many separate units)
  big_island     area share of the largest island at the 3 % scale
  coherence      ink-weighted orientation coherence of the structure tensor
                 at 2 % side (1 = all lines parallel locally)
  width_rel      median line width / side
  mass_share     share of ink surviving an opening with radius 2 line widths
                 (masses vs lines, relative to the sheet's own line)
  ends_len, junc_len   skeleton end points / junctions per unit skeleton
                 length (length in units of side)

The controller (`compose_like`) never edits regime_field: it builds a
modulated field and structure, calls compose, then clears / thins by
region, and post-selects among candidates by a weighted distance to a
target profile. See its docstring.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None

LONG_SIDE = 1024                      # mask resolution for every statistic
LAC_SCALES = (1 / 32, 1 / 16, 1 / 8, 1 / 4)
PROFILE_KEYS = ("cover", "lac_032", "lac_06", "lac_12", "lac_25", "empty16", "void_max", "void_share",
                "com_dx", "com_dy", "spread", "margin_ratio", "islands_1", "islands_3", "big_island",
                "coherence", "width_rel", "mass_share", "ends_len", "junc_len")
# keys that describe COMPOSITION (layout/density/emptiness), not the hand or
# medium; the controller matches these. width_rel, mass_share, ends/junc are
# reported but not targeted (they are the hand's business).
COMPOSITION_KEYS = ("cover", "lac_032", "lac_06", "lac_12", "lac_25", "empty16", "void_max", "void_share",
                    "com_dx", "com_dy", "spread", "margin_ratio", "islands_1", "islands_3", "big_island")


# ---------------------------------------------------------------------------
# masks
# ---------------------------------------------------------------------------

def normalise_mask(mask: np.ndarray, long_side: int = LONG_SIDE, thresh: float = 0.25) -> np.ndarray:
    """Area-average a bool mask to `long_side` and re-threshold at `thresh`
    coverage (a line thinner than a working pixel survives as long as it
    covers a quarter of the cells it crosses)."""
    m = np.asarray(mask, dtype=np.float64)
    h, w = m.shape
    s = long_side / max(h, w)
    if s >= 1.0:
        return m > 0.5
    im = Image.fromarray((m * 255).astype(np.uint8)).resize((max(1, round(w * s)), max(1, round(h * s))),
                                                             Image.Resampling.BOX)
    return np.asarray(im, dtype=np.float64) / 255.0 >= thresh


def mask_from_gray(gray: np.ndarray, *, binarize: bool = True, inset: float = 0.0,
                   border_px: float = 2.0) -> np.ndarray:
    """gray float [0, 1] (ink dark) → bool ink mask at LONG_SIDE. binarize
    uses the extractor's own `_binarize` (local paper level, hysteresis);
    binarize=False thresholds at 0.5 (clean renders). `inset` crops a
    fraction off every side first (scan borders); components touching the
    border are dropped (mounts, sheet edges, rulers)."""
    g = np.asarray(gray, dtype=np.float64)
    if inset > 0:
        h, w = g.shape
        a, b = int(inset * h), int(inset * w)
        g = g[a:h - a, b:w - b]
    if binarize:
        from . import extract as ex
        p = ex.ExtractParams().resolved()
        m, _ = ex._binarize(g, p, None, border_px)
        m = m | solid_ink(g, border_px)
    else:
        m = g < 0.5
    return normalise_mask(m)


def solid_ink(g: np.ndarray, border_px: float = 2.0, depth: float = 0.6) -> np.ndarray:
    """Pixels darker than paper − depth·(paper − darkest ink): the solid
    masses. The extractor's binarisation is line-tuned (local paper level),
    and hollows out large solid blots — fine for centrelines, wrong for
    composition, where a mass is all ink. Components touching the border
    (mounts, scan edges) and specks are dropped."""
    paper = float(np.median(g))
    dark = float(np.percentile(g, 0.5))
    if paper - dark < 0.15:
        return np.zeros(g.shape, bool)
    m = g < paper - depth * (paper - dark)
    lab, n = ndi.label(m, structure=np.ones((3, 3)))
    if n == 0:
        return m
    b = int(max(border_px, 1))
    edge = np.unique(np.concatenate([lab[:b].ravel(), lab[-b:].ravel(), lab[:, :b].ravel(), lab[:, -b:].ravel()]))
    sizes = np.bincount(lab.ravel())
    keep = sizes >= max(16, 2e-5 * m.size)
    keep[0] = False
    keep[edge] = False
    return keep[lab]


def load_gray(path, *, max_side: int = 2000, ink: str = "lum", crop=None) -> np.ndarray:
    """Image → gray float (ink dark), area-downscaled to max_side. crop =
    (x0, y0, x1, y1) fractions. ink: "lum" or a calligraphy.to_gray mode."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        if crop is not None:
            W, H = im.size
            im = im.crop((int(crop[0] * W), int(crop[1] * H), int(crop[2] * W), int(crop[3] * H)))
        s = max_side / max(im.size)
        if s < 1:
            im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.Resampling.BOX)
        a = np.asarray(im, dtype=np.float64) / 255.0
    if ink == "lum":
        return a @ np.array([0.299, 0.587, 0.114])
    from .calligraphy import to_gray
    return to_gray(a, ink)


def render_mask(polylines: Sequence[np.ndarray], size, pen_px: float, long_side: int = LONG_SIDE,
                ss: int = 2) -> np.ndarray:
    """Polylines (px on a `size` = (W, H) sheet) → ink mask at long_side,
    lines drawn at pen width (supersampled, then thresholded like a scan)."""
    from PIL import ImageDraw
    W, H = size
    k = long_side * ss / max(W, H)
    im = Image.new("L", (max(1, round(W * k)), max(1, round(H * k))), 255)
    d = ImageDraw.Draw(im)
    lw = max(int(round(pen_px * k)), 1)
    for q in polylines:
        q = np.asarray(q, float)
        if len(q) >= 2:
            d.line([tuple(v) for v in q * k], fill=0, width=lw, joint="curve")
    a = np.asarray(im, dtype=np.float64) / 255.0
    return normalise_mask(a < 0.5, long_side)


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------

def lacunarity(mask: np.ndarray, box: int) -> float:
    """Gliding-box lacunarity Λ = E[S²] / E[S]² of box sums (box px)."""
    m = mask.astype(np.float64)
    box = max(int(box), 1)
    if box >= min(m.shape):
        return 1.0
    S = ndi.uniform_filter(m, size=box, mode="constant") * box * box
    a = box // 2
    S = S[a:m.shape[0] - (box - 1 - a), a:m.shape[1] - (box - 1 - a)]
    mu = S.mean()
    if mu <= 0:
        return float("nan")
    return float((S ** 2).mean() / mu ** 2)


def _cell_cover(mask: np.ndarray, n_long: int = 16) -> np.ndarray:
    h, w = mask.shape
    ny, nx = (n_long, max(1, round(n_long * w / h))) if h >= w else (max(1, round(n_long * h / w)), n_long)
    ys = np.linspace(0, h, ny + 1).astype(int)
    xs = np.linspace(0, w, nx + 1).astype(int)
    m = mask.astype(np.float64)
    return np.array([[m[ys[i]:ys[i + 1], xs[j]:xs[j + 1]].mean() for j in range(nx)] for i in range(ny)])


def density_map(mask: np.ndarray, n_long: int = 16) -> np.ndarray:
    """Coarse ink coverage grid (the sheet's layout), ~n_long cells on the long side."""
    return _cell_cover(mask, n_long)


def _skeleton_events(mask: np.ndarray) -> tuple[int, int, float]:
    from skimage.morphology import skeletonize
    sk = skeletonize(mask)
    n = ndi.convolve(sk.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - 1
    ends = int(np.sum(sk & (n == 1)))
    junc_px = sk & (n >= 3)
    junc = int(ndi.label(junc_px, structure=np.ones((3, 3)))[1])
    return ends, junc, float(sk.sum())


def profile(mask: np.ndarray) -> dict:
    """Composition statistics of an ink mask (module doc). The mask should
    already be at LONG_SIDE (normalise_mask / mask_from_gray / render_mask)."""
    m = np.asarray(mask, bool)
    h, w = m.shape
    side = math.sqrt(h * w)
    out: dict = {}
    cover = float(m.mean())
    out["cover"] = cover
    for sc, key in zip(LAC_SCALES, ("lac_032", "lac_06", "lac_12", "lac_25")):
        out[key] = float(np.log(lacunarity(m, round(sc * side)))) if cover > 0 else float("nan")
    cc = _cell_cover(m, 16)
    out["empty16"] = float(np.mean(cc < 0.05 * max(cover, 1e-9)))
    dist = ndi.distance_transform_edt(~m) if cover > 0 else np.full(m.shape, side)
    out["void_max"] = float(dist.max() / side)
    out["void_share"] = float(np.mean(dist > 0.05 * side))
    ys, xs = np.nonzero(m)
    if len(xs):
        out["com_dx"] = float(xs.mean() / w - 0.5)
        out["com_dy"] = float(ys.mean() / h - 0.5)
        out["spread"] = float(np.sqrt(((xs - xs.mean()) ** 2 + (ys - ys.mean()) ** 2).mean()) / side)
        band = (xs < 0.1 * w) | (xs > 0.9 * w) | (ys < 0.1 * h) | (ys > 0.9 * h)
        out["margin_ratio"] = float(band.mean() / 0.36)
    else:
        out.update(com_dx=0.0, com_dy=0.0, spread=0.0, margin_ratio=0.0)
    for frac, key in ((0.01, "islands_1"), (0.03, "islands_3")):
        r = max(1, round(frac * side / 2))
        closed = ndi.binary_dilation(m, iterations=r)
        lab, n = ndi.label(closed, structure=np.ones((3, 3)))
        out[key] = float(np.log(max(n, 1)))
        if key == "islands_3":
            if n:
                sizes = np.bincount(lab[m])[1:] if m.any() else np.zeros(1)
                out["big_island"] = float(sizes.max() / max(m.sum(), 1))
            else:
                out["big_island"] = 0.0
    # orientation coherence (structure tensor, ink-weighted)
    gy = ndi.sobel(m.astype(float), 0)
    gx = ndi.sobel(m.astype(float), 1)
    s = max(0.02 * side, 2.0)
    Jxx, Jyy, Jxy = (ndi.gaussian_filter(a, s) for a in (gx * gx, gy * gy, gx * gy))
    tr = Jxx + Jyy
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / np.maximum(tr, 1e-12)
    wgt = tr * ndi.gaussian_filter(m.astype(float), s)
    out["coherence"] = float((coh * wgt).sum() / max(wgt.sum(), 1e-12))
    # width and masses
    from skimage.morphology import skeletonize
    edt = ndi.distance_transform_edt(m)
    sk = skeletonize(m)
    wid = float(np.median(2 * edt[sk] - 1)) if sk.any() else 1.0
    wid = max(wid, 1.0)
    out["width_rel"] = wid / side
    r = max(2.0 * wid, 1.0)
    core = edt >= r                           # opening by a disc of radius r, via two EDTs
    opened = (ndi.distance_transform_edt(~core) <= r) & m if core.any() else np.zeros_like(m)
    out["mass_share"] = float(opened.sum() / max(m.sum(), 1))
    ends, junc, sklen = _skeleton_events(m)
    L = max(sklen / side, 1e-9)
    out["ends_len"] = ends / L
    out["junc_len"] = junc / L
    return out


def vector(p: dict, keys: Sequence[str] = PROFILE_KEYS) -> np.ndarray:
    return np.array([p.get(k, np.nan) for k in keys], dtype=np.float64)


@dataclass
class Scale:
    """Robust per-key centre / spread over a reference population (the
    corpora); distances are in these units."""
    keys: tuple
    centre: np.ndarray
    spread: np.ndarray

    @classmethod
    def fit(cls, profiles: Sequence[dict], keys: Sequence[str] = PROFILE_KEYS) -> "Scale":
        X = np.array([vector(p, keys) for p in profiles])
        c = np.nanmedian(X, axis=0)
        q = np.nanpercentile(X, 75, axis=0) - np.nanpercentile(X, 25, axis=0)
        return cls(tuple(keys), c, np.maximum(q / 1.349, 1e-6))

    def z(self, p: dict) -> np.ndarray:
        return (vector(p, self.keys) - self.centre) / self.spread


def target_of(profiles: Sequence[dict]) -> dict:
    """Median profile of a group."""
    keys = profiles[0].keys()
    return {k: float(np.nanmedian([p[k] for p in profiles])) for k in keys}


def distance(p: dict, target: dict, scale: Scale, keys: Sequence[str] = COMPOSITION_KEYS,
             weights: dict | None = None) -> float:
    """RMS standardised difference over `keys`."""
    idx = [scale.keys.index(k) for k in keys]
    a = vector(p, scale.keys)[idx]
    b = vector(target, scale.keys)[idx]
    d = (a - b) / scale.spread[idx]
    wv = np.array([(weights or {}).get(k, 1.0) for k in keys])
    ok = np.isfinite(d)
    return float(np.sqrt(np.sum(wv[ok] * d[ok] ** 2) / max(np.sum(wv[ok]), 1e-9)))


# ---------------------------------------------------------------------------
# the controller
# ---------------------------------------------------------------------------

def resize_map(dmap: np.ndarray, shape) -> np.ndarray:
    """Bilinear resize of a coarse map to (rows, cols)."""
    from scipy.ndimage import zoom
    z = (shape[0] / dmap.shape[0], shape[1] / dmap.shape[1])
    return np.clip(zoom(dmap, z, order=1, mode="nearest"), 0, None)[:shape[0], :shape[1]]


def layout_field(dmap: np.ndarray, *, empty_q: float, smooth: float = 0.6, flip: bool = False) -> np.ndarray:
    """A target layout (coarse density map) → emptiness E ∈ [0, 1] on the
    same grid: 1 where the target leaves the sheet alone. `empty_q` is the
    share of the sheet to clear (the target's empty16); the threshold is the
    matching quantile of the (smoothed) map, with a soft edge."""
    d = ndi.gaussian_filter(np.asarray(dmap, float), smooth)
    if flip:
        d = d[:, ::-1]
    if empty_q <= 0:
        return np.zeros_like(d)
    thr = float(np.quantile(d, min(empty_q, 0.95)))
    soft = 0.35 * max(float(np.std(d)), 1e-9)
    return 1.0 / (1.0 + np.exp((d - thr) / soft * 3.0))


class _GridLookup:
    """Bilinear lookup of a grid over the unit sheet (rows = y)."""

    def __init__(self, grid: np.ndarray):
        self.g = np.asarray(grid, float)

    def __call__(self, u: np.ndarray) -> np.ndarray:
        u = np.atleast_2d(np.clip(u, 0, 1))
        r = u[:, 1] * (self.g.shape[0] - 1)
        c = u[:, 0] * (self.g.shape[1] - 1)
        return ndi.map_coordinates(self.g, [r, c], order=1, mode="nearest")


def clear_composition(c, E_grid: np.ndarray, *, tau: float = 0.5, min_len_frac: float = 0.01,
                      whole_kinds=("fill", "sign", "echo", "drip")):
    """Remove ink where the emptiness map E > tau. Lines are CUT at the
    boundary (they stop at the void); whole marks (fills, signs, echoes,
    drips) are kept or dropped as a unit by the share of their points in the
    void (> 0.5 → dropped), so no mass ring is opened. Returns a new
    Composition (inputs untouched)."""
    from shapely.geometry import LineString, Polygon, MultiPolygon
    from shapely.ops import unary_union
    from skimage import measure
    from .regime_field import Composition
    W, H = c.size
    look = _GridLookup(E_grid)
    # void polygon from the E grid's tau contour, upsampled for a smooth edge
    up = resize_map(E_grid, (E_grid.shape[0] * 8, E_grid.shape[1] * 8))
    pad = np.pad(up, 1, constant_values=0.0)
    polys = []
    for ctr in measure.find_contours(pad, tau):
        if len(ctr) < 4:
            continue
        xy = np.column_stack([(ctr[:, 1] - 1) / (up.shape[1] - 1) * W, (ctr[:, 0] - 1) / (up.shape[0] - 1) * H])
        pg = Polygon(xy).buffer(0)
        if pg.area > 0:
            polys.append(pg)
    # contours of the void: nested rings → symmetric difference gives holes right
    void = None
    for pg in polys:
        void = pg if void is None else void.symmetric_difference(pg)
    keep_p, keep_g, keep_k = [], [], []
    group_void: dict = {}
    for q, g, k in zip(c.polylines, c.groups, c.kinds):
        if k in whole_kinds:
            group_void.setdefault(g, []).append(look(np.asarray(q, float) / np.array([W, H])))
    gv = {g: float(np.mean(np.concatenate(v) > tau)) for g, v in group_void.items()}
    min_len = min_len_frac * H
    for q, g, k in zip(c.polylines, c.groups, c.kinds):
        q = np.asarray(q, float)
        if k in whole_kinds:
            if gv.get(g, 0.0) <= 0.5:
                keep_p.append(q); keep_g.append(g); keep_k.append(k)
            continue
        if void is None or void.is_empty:
            keep_p.append(q); keep_g.append(g); keep_k.append(k)
            continue
        ls = LineString(q)
        if not ls.intersects(void):
            keep_p.append(q); keep_g.append(g); keep_k.append(k)
            continue
        rest = ls.difference(void)
        parts = [rest] if rest.geom_type == "LineString" else list(getattr(rest, "geoms", []))
        for prt in parts:
            if prt.geom_type == "LineString" and not prt.is_empty and prt.length >= min_len:
                keep_p.append(np.asarray(prt.coords, float)); keep_g.append(g); keep_k.append(k)
    meta = dict(c.meta)
    meta["cleared"] = {"tau": tau, "void_area_share": float(void.area / (W * H)) if void is not None else 0.0}
    return Composition(keep_p, c.size, meta, c.centrelines, c.regimes, groups=keep_g, kinds=keep_k), void


def modulated_field(base: str, E_grid: np.ndarray, *, halo: float = 1.0, seed: int = 0, aspect: float = 1.0,
                    mass_boost: float = 0.0, D_grid: np.ndarray | None = None, edge: str = "halo",
                    tau: float = 0.5, band: float = 0.18):
    """A field callable for compose(field=...).

    edge="halo": the preset `base` (built on the structure) times
    (1 − halo·E): lines approaching the void thin to wire before they stop.
    edge="pool": the opposite — r rises toward 2 in a band just outside the
    void edge (E ∈ [tau − band, tau]), so lines swell into masses as they
    arrive and are cut there: the void is drawn by the rim of what meets it.
    mass_boost > 0 pushes r toward 2 where the target layout is densest
    (D_grid normalised to [0, 1])."""
    from . import regime_field as rf
    lookE = _GridLookup(E_grid)
    lookD = _GridLookup(D_grid) if D_grid is not None else None

    def build(st):
        f0 = {**rf.PRESETS, **rf.EXTRA_PRESETS}[base](st, seed, aspect)

        def fn(u):
            e = lookE(u)
            if edge == "pool":
                rim = np.exp(-0.5 * ((e - (tau - 0.5 * band)) / (0.5 * band)) ** 2)
                r = f0(u) * (1.0 - 0.6 * e) + 2.2 * rim
            else:
                r = f0(u) * (1.0 - halo * e)
            if lookD is not None and mass_boost > 0:
                r = r + mass_boost * np.clip(lookD(u) - 0.6, 0, None) / 0.4
            return r
        return rf.Field(fn, name=f"{f0.name}×E[{edge}]", aspect=aspect)
    return build


def guided_tree(rng, size, E_grid: np.ndarray, **params):
    """topology's Oehlen tree grown with an ENVELOPE = 1 − E (the tree
    generator itself passes none, so it fills the sheet evenly): resprouts
    and steering prefer the target's dense regions. Done by wrapping
    topology._Sheet for the duration of the call (no file edit; proposed
    upstream as an `envelope=` parameter)."""
    from . import topology as tp
    env = 1.0 - resize_map(E_grid, (24, 24))
    orig = tp._Sheet.__init__

    def init(self, W, H, R, prm, envelope, x_rate):
        orig(self, W, H, R, prm, env if envelope is None else envelope, x_rate)
    tp._Sheet.__init__ = init
    try:
        prm = dict(params)
        prm.setdefault("trunks", 1)
        prm.setdefault("fill", 0.9)
        prm.setdefault("clearance_r", 0.008)
        return tp.generate_structure(None, rng, size, kind="oehlen_tree", **prm)
    finally:
        tp._Sheet.__init__ = orig


@dataclass
class Candidate:
    comp: object
    profile: dict
    dist: float
    spec: dict
    void: object = None
    mask: np.ndarray | None = dc_field(default=None, repr=False)


def make_candidate(spec: dict, size=(840, 1200)) -> tuple:
    """One controller candidate from a plain-data spec (picklable, for a
    process pool). spec keys: seed, structure ("tree"|"guided"|"forest"|
    "grammar"|"line"), structure_params, field (preset), hands (name or
    "by_regime"), E (emptiness grid, list) or None, tau, halo, mass_boost,
    D (density grid) , signs, echo, drip, tremor, script."""
    from . import regime_field as rf
    W, H = size
    E = np.asarray(spec["E"], float) if spec.get("E") is not None else None
    D = np.asarray(spec["D"], float) if spec.get("D") is not None else None
    hands = spec.get("hands", "hokusai")
    if hands == "by_regime":
        hands = lambda fobj, aspect, seed: rf.hand_by_field(  # noqa: E731
            fobj, {"matisse": 0.0, "shikasta": 1.0, "hokusai": 2.0}, width=0.45)
    structure = spec.get("structure", "tree")
    if structure == "guided":
        rng = np.random.default_rng([spec["seed"], 7])
        structure = guided_tree(rng, (W, H), E if E is not None else np.zeros((16, 12)),
                                **(spec.get("structure_params") or {}))
    field = spec.get("field", "strahler")
    if E is not None:
        field = modulated_field(field, E, halo=spec.get("halo", 1.0), seed=spec["seed"], aspect=H / W,
                                mass_boost=spec.get("mass_boost", 0.0), D_grid=D, edge=spec.get("edge", "halo"),
                                tau=spec.get("tau", 0.5))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        c = rf.compose(spec["seed"], (W, H), structure=structure, field=field, hands=hands,
                       signs=spec.get("signs", 6), tremor=spec.get("tremor", 0.0), echo=spec.get("echo", 0),
                       drip=spec.get("drip", 0), script=spec.get("script", 0),
                       structure_params=None if spec.get("structure") == "guided" else spec.get("structure_params"),
                       label=spec.get("label", ""))
    void = None
    if E is not None and spec.get("tau", 0.5) < 1.0:
        c, void = clear_composition(c, E, tau=spec.get("tau", 0.5))
    m = render_mask(c.polylines, (W, H), c.meta["pen_px"])
    return c, profile(m), void, m


# ---------------------------------------------------------------------------
# cheap post-operators + a feedback tuner (no recompose per step)
# ---------------------------------------------------------------------------

def zoom_composition(c, z: float):
    """Scale every polyline by z about the sheet centre and cut at the sheet
    edge (z > 1 pushes ink into the margins and off the sheet)."""
    from .regime_field import Composition, clip_to_sheet
    if abs(z - 1.0) < 1e-9:
        return c
    W, H = c.size
    ctr = np.array([W / 2, H / 2])
    P, G, K = [], [], []
    for q, g, k in zip(c.polylines, c.groups, c.kinds):
        for piece in clip_to_sheet((np.asarray(q, float) - ctr) * z + ctr, W, H):
            P.append(piece); G.append(g); K.append(k)
    return Composition(P, c.size, dict(c.meta), c.centrelines, c.regimes, groups=G, kinds=K)


def junction_gaps(c, n: int, rng: np.random.Generator, *, gap_frac: float = 0.012, near_pen: float = 4.0):
    """Lift the pen near junctions: open n gaps of gap_frac·H in LINE
    polylines at points where another mark passes within near_pen pens.
    A drawn T or X becomes a line that stops short of the one it meets —
    the commonest junction in the corpora (free ends, separate islands);
    our nets weld everything. Marks (fills, signs) are untouched."""
    from scipy.spatial import cKDTree
    from .regime_field import Composition
    if n <= 0:
        return c
    W, H = c.size
    pen = float(c.meta.get("pen_px", 1.5))
    idx = [i for i, k in enumerate(c.kinds) if k == "line" and len(c.polylines[i]) >= 4]
    if not idx:
        return c
    pts, owner = [], []
    for i, q in enumerate(c.polylines):
        q = np.asarray(q, float)
        pts.append(q); owner.append(np.full(len(q), i))
    pts = np.vstack(pts); owner = np.concatenate(owner)
    tree = cKDTree(pts)
    cand = []                                      # (line index, vertex index)
    for i in idx:
        q = np.asarray(c.polylines[i], float)
        for j, nb in enumerate(tree.query_ball_point(q, near_pen * pen)):
            if any(owner[t] != i for t in nb):
                cand.append((i, j))
    if not cand:
        return c
    pick = rng.choice(len(cand), size=min(n, len(cand)), replace=False)
    cuts: dict[int, list[int]] = {}
    for t in pick:
        i, j = cand[t]
        cuts.setdefault(i, []).append(j)
    half = 0.5 * gap_frac * H
    P, G, K = [], [], []
    for i, (q, g, k) in enumerate(zip(c.polylines, c.groups, c.kinds)):
        if i not in cuts:
            P.append(q); G.append(g); K.append(k)
            continue
        q = np.asarray(q, float)
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
        keep = np.ones(len(q), bool)
        for j in cuts[i]:
            keep &= np.abs(s - s[j]) > half
        start = None
        for a in range(len(q) + 1):
            if a < len(q) and keep[a]:
                start = a if start is None else start
            elif start is not None:
                if a - start >= 2:
                    P.append(q[start:a]); G.append(g); K.append(k)
                start = None
    return Composition(P, c.size, dict(c.meta), c.centrelines, c.regimes, groups=G, kinds=K)


def post(c, *, layout: np.ndarray | None, empty_q: float, gaps: int, zoom: float, seed: int = 0):
    """zoom → clear by the layout's emptiness → junction gaps."""
    c = zoom_composition(c, zoom)
    if layout is not None and empty_q > 0:
        E = layout_field(layout, empty_q=empty_q)
        c, _ = clear_composition(c, E, tau=0.5)
    return junction_gaps(c, gaps, np.random.default_rng(seed))


def tune(c, target: dict, scale: Scale, *, layout: np.ndarray | None, iters: int = 30, seed: int = 0,
         keys: Sequence[str] = COMPOSITION_KEYS):
    """Feedback search over the cheap post-knobs (empty_q, gaps, zoom) for
    one base composition: random start points then local perturbation of
    the best (each step = post-ops + render + profile, ~1 s). Returns
    (best composition, its profile, its knobs, history)."""
    rng = np.random.default_rng(seed)
    W, H = c.size
    pen = c.meta["pen_px"]
    hist = []

    def ev(k):
        cc = post(c, layout=layout, empty_q=k["empty_q"], gaps=int(k["gaps"]), zoom=k["zoom"], seed=seed)
        p = profile(render_mask(cc.polylines, (W, H), pen))
        d = distance(p, target, scale, keys)
        hist.append((d, dict(k)))
        return d, cc, p

    k0 = {"empty_q": 0.0, "gaps": 0, "zoom": 1.0}
    best = (*ev(k0), k0)
    for it in range(iters):
        if it < iters // 3:
            k = {"empty_q": float(rng.uniform(0, 0.6)) if layout is not None else 0.0,
                 "gaps": int(rng.integers(0, 160)), "zoom": float(rng.uniform(1.0, 1.2))}
        else:
            b = best[3]
            k = {"empty_q": float(np.clip(b["empty_q"] + rng.normal(0, 0.06), 0, 0.8)) if layout is not None else 0.0,
                 "gaps": int(np.clip(b["gaps"] + rng.normal(0, 20), 0, 300)),
                 "zoom": float(np.clip(b["zoom"] + rng.normal(0, 0.03), 0.9, 1.3))}
        d, cc, p = ev(k)
        if d < best[0]:
            best = (d, cc, p, k)
    return best[1], best[2], best[3], hist
