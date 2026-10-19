# FROZEN from research commit 071aea1: tools/gesture/gesture/extract.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Stage 1: raster line drawing → ordered strokes with width.

Pipeline (see ../README.md for the Stroke/Drawing contract; every factor
below is a multiple of the measured line width w, defaults in ExtractParams):

1. load: grayscale float in [0, 1] (paper bright), optional invert for
   white-on-black prints, optional area-averaging downscale cap. All output
   geometry is in ORIGINAL pixels of the source raster.
2. binarize (`_binarize`): darkness D = local paper level − pixel, where the
   paper level is a box mean of non-ink pixels (stains, plate tone, uneven
   light drop out); hysteresis with per-pixel thresholds from a LOCAL noise
   map and the global ink contrast (seed > max(6σ, 0.25·C), grow > max(3σ,
   0.12·C)) — faint pencil connected to a stroke survives, isolated paper
   texture does not. The pre-blur σ is searched upward while most ink sits
   in small specks (crayon/litho grain read at too fine a scale). Then a
   1-px closing, hole fill, boundary smoothing, speck removal.
3. plate marks (`_plate_lines`): ruler-straight, near-axis-aligned lines in
   the outer 10 % of the sheet spanning ≥ 30 % of a side are erased, and
   (crop_to_plate) everything beyond them — signatures, edition numbers.
4. skeleton (`skimage.morphology.skeletonize`) and widths: topology decisions
   use the mask width 2·edt − 1; REPORTED widths are sub-pixel ink integrals
   across the line (`_width_map`), independent of the threshold.
5. graph (`_trace_skeleton`, sknw semantics without numba's ~20 s JIT):
   merge pass-through nodes, prune terminal spurs < 2w, contract
   junction–junction edges < 1w, and merge two degree-3 junctions joined by
   an edge ≤ 8w when their four outer branches pair straight across and both
   lines pass through the merged centre (a shallow X skeletonizes as two Y's).
6. junctions (`_Chainer`): each branch's tangent is a PCA fit to skeleton
   points OUTSIDE the junction zone (radius w + node spread; the skeleton
   kinks inside it); branches pair greedily by straightness (turn < 45°);
   unpaired branches END at the junction (T: the stem stops, the bar runs
   on). Paths are re-centred: the in-zone skeleton is dropped and bridged by
   a cubic Hermite from the two outside tangents; an unpaired end runs
   straight along its tangent to the junction centre. Free tips lose their
   skeleton hook (last 0.75w) and are re-extended straight.
7. chain paired edges into strokes; cycles with no free end become closed
   strokes. Collinear free ends < 3w apart are joined (etching breaks).
8. de-staircase: resample at 1 working px + Gaussian σ = 1 px with pinned
   endpoints (removes the 8-connected chain's length inflation; κ smoothing
   at line-width scale stays downstream in curvature.py). Drop strokes
   < 3w and strokes hugging the image border or a plate line.

What a raster cannot tell apart, and what this module does about it:

- a sharp V corner of ONE stroke vs TWO strokes whose ends touch: the ink is
  identical, so a V is returned as one stroke with a corner (κ spike).
  Splitting at corners is a downstream (segmentation) decision.
- stroke direction and global drawing order are unrecoverable: open strokes
  start at their left-most end (ties: top-most); recorded in
  ``Drawing.meta["conventions"]``.
- crossings shallower than ~20° merge into one ink band over > 8w and come
  out as a stroke plus two stubs.

Coordinates: skimage works in (row, col); every Stroke point is (x, y) =
(col, row), pixel-centre convention (pixel i spans [i−½, i+½]).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.ndimage import gaussian_filter1d
from skimage import filters, morphology

from .core import Drawing, Stroke

Image.MAX_IMAGE_PIXELS = None  # museum scans are large and trusted

__all__ = [
    "ExtractParams",
    "load_image",
    "extract",
    "extract_file",
    "debug_overlay",
]


# --------------------------------------------------------------------------
# parameters
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ExtractParams:
    """Every tunable of the pipeline. Factors are multiples of the measured
    median line width w (working pixels) unless the name says otherwise."""

    method: str = "hysteresis"         # "hysteresis" | "sauvola" | "otsu"
    hi_noise: float = 6.0              # hysteresis seed: darkness > max(hi_noise·σ_noise,
    hi_frac: float = 0.25              #   hi_frac·ink contrast)
    lo_noise: float = 3.0              # hysteresis grow: darkness > max(lo_noise·σ_noise,
    lo_frac: float = 0.12              #   lo_frac·ink contrast)
    paper_window_frac: float = 0.015   # local paper-level window, fraction of the diagonal (≥ 31 px)
    grain_sigmas: tuple = (1.0, 1.5, 2.5, 4.0, 6.0)  # pre-blur σ search, working px
    grain_max_frag: float = 0.35       # accept σ once ≤ this ink fraction is in small specks
    grain_small_frac: float = 0.008    # "small speck" = component < (this·diagonal)² px²
    sauvola_k: float = 0.2             # method="sauvola" only
    dark_gate: float = 0.6             # method="sauvola": darker than dark_gate·otsu is ink
    min_component_area: float | None = None   # px² (working); None → 3·w²
    fill_holes_area: float | None = None      # px² (working); None → 1·w²
    closing_radius: int = 1            # px (working); 0 disables
    mask_sigma_factor: float = 0.25    # boundary smoothing σ = this·w (0 disables)
    border_margin: float = 0.0         # px (ORIGINAL): drop components touching this band
    drop_frames: bool = True           # erase plate marks / scan edges (see _plate_lines)
    frame_min_frac: float = 0.3        # a frame line spans ≥ this fraction of the image side
    frame_max_outside: float = 0.1     # …and has ≤ this fraction of the ink beyond it
    frame_zone_frac: float = 0.1       # …and lies in the outer this-fraction of the image
    crop_to_plate: bool = True         # drop ink outside detected plate lines (signatures, numbers)
    border_band_frac: float = 0.004    # drop strokes lying ≥ 70 % within this band (·diagonal) of the edge
    spur_factor: float = 2.0           # prune terminal branches shorter than this·w
    cluster_factor: float = 1.0        # contract junction–junction edges shorter than this·w
    x_merge_factor: float = 8.0        # …and up to this·w when they form a consistent X
    junction_trim: float = 1.0         # junction zone radius = this·w + node spread
    tangent_span: float = 2.5          # tangent window length beyond the zone, ·w (≥ 6 px)
    max_turn_deg: float = 45.0         # max deviation from straight to chain through a junction
    tip_trim: float = 0.75             # free ends: replace the last this·w (skeleton hook) by a straight run
    min_stroke_factor: float = 3.0     # drop strokes shorter than this·w
    gap_join_factor: float = 3.0       # join collinear free ends closer than this·w (0 = off)
    gap_join_turn_deg: float = 25.0    # max tangent deviation for a gap join
    width_method: str = "gray"         # "gray" (sub-pixel ink integral) | "edt"
    resample_step: float = 1.0         # output spacing, working px (0 = raw skeleton pixels)
    smooth_sigma: float = 1.0          # de-staircase σ, working px (0 = off); endpoints pinned

    def resolved(self, **kw) -> "ExtractParams":
        names = {f.name for f in fields(self)}
        bad = set(kw) - names
        if bad:
            raise TypeError(f"unknown extract parameter(s): {sorted(bad)}")
        return replace(self, **kw)


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def _downscale(gray: np.ndarray, max_side: int | None) -> tuple[np.ndarray, float]:
    """Area-preserving downscale so max(H, W) ≤ max_side. Returns (array, scale)
    where scale = working px / original px (≤ 1)."""
    h, w = gray.shape
    if not max_side or max(h, w) <= max_side:
        return gray, 1.0
    s = max_side / max(h, w)
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    im = Image.fromarray(gray.astype(np.float32), mode="F")
    out = np.asarray(im.resize((nw, nh), Image.Resampling.BOX), dtype=np.float64)
    # the realised scale differs from s by rounding; use the per-axis mean
    scale = 0.5 * (nw / w + nh / h)
    return np.clip(out, 0.0, 1.0), scale


def load_image(path: str | Path, invert: bool = False,
               max_side: int | None = 3000) -> tuple[np.ndarray, float]:
    """Read a scan as grayscale float64 in [0, 1], paper bright / ink dark.

    invert: set for white-on-black prints (linocuts) so ink ends up dark.
    max_side: downscale cap in pixels (None = full resolution).
    Returns (gray, scale) with scale = working px / original px; geometry
    extracted from `gray` is divided back by `scale` by `extract`.
    """
    with Image.open(path) as im:
        g = np.asarray(im.convert("L"), dtype=np.float64) / 255.0
    if invert:
        g = 1.0 - g
    return _downscale(g, max_side)


# --------------------------------------------------------------------------
# binarization
# --------------------------------------------------------------------------

def _odd(n: float, lo: int = 3) -> int:
    n = max(int(round(n)), lo)
    return n if n % 2 else n + 1


def _median_width(mask: np.ndarray) -> float:
    """Median full line width (px) of a binary ink mask: 2·edt − 1 sampled
    on its skeleton. Returns 0 for an empty mask."""
    if not mask.any():
        return 0.0
    sk = morphology.skeletonize(mask)
    if not sk.any():
        return 1.0
    dt = ndi.distance_transform_edt(mask)
    return float(max(np.median(2.0 * dt[sk] - 1.0), 1.0))


def _width_map(gray: np.ndarray, mask: np.ndarray, skel: np.ndarray, w0: float,
               window: int, method: str) -> np.ndarray:
    """Full line width (working px) at every skeleton pixel; elsewhere the
    EDT estimate 2·edt − 1.

    method "gray" (default): sub-pixel, threshold-independent. Ink darkness
    D = paper − g (paper = local mean of non-ink pixels, D restricted to the
    ink mask grown by 2 px) is summed over a disk of radius R around each
    skeleton pixel and divided by 2R·contrast, contrast = paper − darkest
    value next to the pixel. For a straight line crossing the disk this is
    exactly the integral of the normalised cross-profile — the line's full
    width for a solid line, its "equivalent width" for a soft one. Falls
    back to the EDT where the line is too wide for the disk (> 1.6 R).
    method "edt": 2·edt − 1 only (odd-integer quantised).
    """
    dt = ndi.distance_transform_edt(mask)
    wmap = np.maximum(2.0 * dt - 1.0, 1.0)
    if method == "edt" or not skel.any():
        return wmap
    if method != "gray":
        raise ValueError(f"unknown width method {method!r}")
    paper_px = ~ndi.binary_dilation(mask, iterations=max(int(np.ceil(w0)), 1))
    size = max(window, 15)
    num = ndi.uniform_filter(np.where(paper_px, gray, 0.0), size=size)
    den = ndi.uniform_filter(paper_px.astype(np.float64), size=size)
    glob = float(np.median(gray[paper_px])) if paper_px.any() else 1.0
    paper = np.where(den > 1e-3, num / np.maximum(den, 1e-3), glob)
    grown = ndi.binary_dilation(mask, iterations=2)
    D = np.where(grown, np.clip(paper - gray, 0.0, None), 0.0)
    gmin = ndi.minimum_filter(filters.gaussian(gray, sigma=0.5, preserve_range=True), size=3)

    R = max(1.5 * w0, 3.0)
    Ri = int(np.ceil(R))
    rr, cc = np.nonzero(skel)
    H, W = gray.shape
    acc = np.zeros(len(rr))
    dy, dx = np.mgrid[-Ri:Ri + 1, -Ri:Ri + 1]
    inside = dy**2 + dx**2 <= R * R
    Dp = np.pad(D, Ri)
    for oy, ox in zip(dy[inside], dx[inside]):
        acc += Dp[rr + Ri + oy, cc + Ri + ox]
    contrast = np.maximum(paper[rr, cc] - gmin[rr, cc], 0.05)
    # the discrete disk holds n_px pixels, not πR²: rescale the diameter
    diam = 2.0 * np.sqrt(inside.sum() / np.pi)
    wg = acc / (diam * contrast)
    we = wmap[rr, cc]
    out = np.where(we > 1.6 * R, we, np.clip(wg, 1.0, None))
    wmap = wmap.copy()
    wmap[rr, cc] = out
    return wmap


def _darkness(gray: np.ndarray, sigma: float, window: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Ink darkness relative to the LOCAL paper level, a LOCAL noise map and
    a global ink-contrast estimate (all in gray units).

    paper = box mean over `window` of pixels that are not candidate ink
    (normalised convolution), so stains, plate tone and uneven lighting are
    removed at that scale. noise = RMS of the darkness over paper pixels in
    the same window (local, so a grainy plate tone raises its own threshold
    without deafening the clean margin), floored at half the global robust
    σ. contrast = 90th percentile darkness of clearly-ink pixels (> 8 σ),
    i.e. the darkness of line cores.
    """
    gs = filters.gaussian(gray, sigma=sigma, preserve_range=True) if sigma > 0 else gray
    p1 = ndi.uniform_filter(gs, size=window)
    r = gs - p1
    n0 = 1.4826 * float(np.median(np.abs(r - np.median(r)))) + 1e-6
    keep = ~ndi.binary_dilation(gs < p1 - 3.0 * n0, iterations=2)
    kf = keep.astype(np.float64)
    den = np.maximum(ndi.uniform_filter(kf, size=window), 0.05)
    paper = np.where(den > 0.05, ndi.uniform_filter(gs * kf, size=window) / den, p1)
    D = paper - gs
    dk = D[keep]
    gnoise = 1.4826 * float(np.median(np.abs(dk - np.median(dk)))) + 1e-6 if dk.size else 0.01
    var = ndi.uniform_filter(np.minimum(D, 4.0 * gnoise) ** 2 * kf, size=window) / den
    noise = np.maximum(np.sqrt(np.maximum(var, 0.0)), 0.5 * gnoise)
    strong = D > 8.0 * noise
    contrast = float(np.percentile(D[strong], 90)) if strong.sum() > 50 else float(D.max())
    return D, noise, max(contrast, 1e-6)


def _threshold(gray: np.ndarray, p: ExtractParams, sigma: float, window: int) -> tuple[np.ndarray, dict]:
    if p.method == "hysteresis":
        D, noise, C = _darkness(gray, sigma, window)
        hi = np.maximum(p.hi_noise * noise, p.hi_frac * C)
        lo = np.maximum(p.lo_noise * noise, p.lo_frac * C)
        # hysteresis with per-pixel thresholds: seeds D > hi, grown through D > lo
        low_mask = D > lo
        lab, n = ndi.label(low_mask, structure=np.ones((3, 3)))
        seeded = np.zeros(n + 1, dtype=bool)
        seeded[np.unique(lab[(D > hi) & low_mask])] = True
        seeded[0] = False
        ink = seeded[lab]
        return ink, {"noise_median": round(float(np.median(noise)), 5), "contrast": round(C, 4),
                     "low_median": round(float(np.median(lo)), 4),
                     "high_median": round(float(np.median(hi)), 4)}
    g = filters.gaussian(gray, sigma=sigma, preserve_range=True)
    t_otsu = float(filters.threshold_otsu(g)) if np.ptp(g) > 1e-6 else 0.5
    if p.method == "sauvola":
        t_loc = filters.threshold_sauvola(g, window_size=window, k=p.sauvola_k, r=0.5)
        ink = (g < t_loc) & (g < t_otsu + 0.5 * (1.0 - t_otsu))
        ink |= g < p.dark_gate * t_otsu
    elif p.method == "otsu":
        ink = g < t_otsu
    else:
        raise ValueError(f"unknown method {p.method!r}")
    return ink, {"otsu_threshold": round(t_otsu, 4)}


def _fragmentation(ink: np.ndarray, small_area: float) -> float:
    """Fraction of ink area that sits in components smaller than small_area
    px² — near 1 for crayon/grain read at too fine a scale, low for lines."""
    tot = int(ink.sum())
    if tot == 0:
        return 0.0
    lab, n = ndi.label(ink, structure=np.ones((3, 3)))
    if n == 0:
        return 0.0
    sizes = np.bincount(lab.ravel())[1:]
    return float(sizes[sizes < small_area].sum() / tot)


def _binarize(gray: np.ndarray, p: ExtractParams, w_hint: float | None,
              border_margin_px: float) -> tuple[np.ndarray, dict]:
    """gray float [0,1] (ink dark) → boolean ink mask + info dict.

    The smoothing scale is searched, not fixed: starting from σ = 1 px the
    mask is re-thresholded at growing σ (`grain_sigmas`) while more than
    `grain_max_frag` of the ink sits in small isolated components — the
    signature of a crayon/litho line read at grain scale. Thin clean lines
    stop at the first σ.
    """
    info: dict = {}
    H, W = gray.shape
    diag = float(np.hypot(H, W))
    window = _odd(max(31.0, p.paper_window_frac * diag))
    small = (p.grain_small_frac * diag) ** 2
    sig_list = [s for s in p.grain_sigmas] or [1.0]
    if w_hint is not None:
        sig_list = [float(np.clip(0.15 * w_hint, 0.5, 8.0))]
    tried = []
    ink = None
    for s in sig_list:
        ink, tinfo = _threshold(gray, p, s, window)
        frag = _fragmentation(ink, small)
        tried.append([s, round(frag, 3)])
        if frag <= p.grain_max_frag:
            break
    info.update(tinfo)
    info["paper_window"] = window
    info["sigma"] = tried[-1][0]
    info["sigma_search"] = tried

    if w_hint is None:
        w0 = _median_width(ink)
        w0 = float(np.clip(w0, 1.0, 200.0)) if w0 > 0 else 3.0
    else:
        w0 = float(w_hint)
    info["w_initial"] = round(w0, 3)
    info["_w0"] = w0
    info["_window"] = window

    if p.closing_radius > 0:
        ink = ndi.binary_closing(ink, structure=morphology.disk(p.closing_radius), border_value=0)
    holes = p.fill_holes_area if p.fill_holes_area is not None else w0 * w0
    if holes > 0:
        ink = morphology.remove_small_holes(ink, max_size=int(holes))
    if p.mask_sigma_factor > 0:
        ms = max(p.mask_sigma_factor * w0, 0.5)
        ink = filters.gaussian(ink.astype(np.float64), sigma=ms) > 0.5
    area = p.min_component_area if p.min_component_area is not None else 3.0 * w0 * w0
    area = max(int(area), 4)
    ink = morphology.remove_small_objects(ink, max_size=area, connectivity=2)

    if border_margin_px > 0:
        m = int(np.ceil(border_margin_px))
        lab, n = ndi.label(ink, structure=np.ones((3, 3)))
        edge = np.zeros_like(ink)
        edge[:m, :] = edge[-m:, :] = True
        edge[:, :m] = edge[:, -m:] = True
        bad = np.unique(lab[edge & ink])
        bad = bad[bad > 0]
        if len(bad):
            ink = ink & ~np.isin(lab, bad)
        info["border_components_dropped"] = int(len(bad))
    return ink, info


def _plate_lines(mask: np.ndarray, w: float, p: ExtractParams) -> list[dict]:
    """Find plate marks and scan/sheet-edge lines: near-axis-aligned (±2°),
    very straight runs of ink covering ≥ frame_min_frac of the image side,
    lying in the outer `frame_zone_frac` of the image, with ≤
    frame_max_outside of the skeleton beyond them. Hand-drawn long lines
    fail the straightness (they smear over many 1-px bins) or the zone test.
    A plate bevel prints as two parallel lines; every qualifying line in the
    zone on that side is returned, not only the outermost.

    Returns dicts {axis: "h"|"v", t: tan(angle), a0: offset, side: "lo"|"hi",
    count, band}; a point (r, c) lies on a horizontal line when
    |r − c·t − a0| ≤ band (vertical: swap r and c).
    """
    sk = morphology.skeletonize(mask)
    rr, cc = np.nonzero(sk)
    if len(rr) < 10:
        return []
    H, W = mask.shape
    band = max(2.0 * w, 4.0)
    half = 1                                   # ±1 px: only ruler-straight runs pile up
    found = []
    for axis in ("h", "v"):
        a, b, L, ext = (rr, cc, W, H) if axis == "h" else (cc, rr, H, W)
        zone = p.frame_zone_frac * ext
        cands = []
        for t in np.tan(np.radians(np.arange(-2.0, 2.0001, 0.05))):
            a2 = np.round(a - b * t).astype(int)
            off = -a2.min()
            hist = np.bincount(a2 + off)
            win = np.convolve(hist, np.ones(2 * half + 1), mode="same")
            for k in np.nonzero(win >= p.frame_min_frac * L)[0]:
                a0 = float(k - off)
                if a0 <= zone or a0 >= ext - 1 - zone:
                    cands.append((a0, float(t), float(win[k])))
        for side in ("lo", "hi"):
            cs = [c for c in cands if (c[0] < ext / 2) == (side == "lo")]
            # greedy non-maximum suppression: densest first, 3·band apart
            cs.sort(key=lambda c: -c[2])
            kept: list[tuple[float, float, float]] = []
            for c in cs:
                if all(abs(c[0] - k[0]) > 3 * band for k in kept):
                    kept.append(c)
            for a0, t, cnt in kept:
                d = a - b * t - a0
                beyond = (d < -band) if side == "lo" else (d > band)
                if beyond.mean() > p.frame_max_outside:
                    continue
                found.append({"axis": axis, "t": t, "a0": a0, "side": side,
                              "count": int(cnt), "band": band})
    return found


def _near_plate(rc: np.ndarray, lines: list[dict], dist: float) -> np.ndarray:
    """Boolean per point (row, col): within `dist` of any plate line."""
    near = np.zeros(len(rc), dtype=bool)
    for ln in lines:
        a, b = (rc[:, 0], rc[:, 1]) if ln["axis"] == "h" else (rc[:, 1], rc[:, 0])
        near |= np.abs(a - b * ln["t"] - ln["a0"]) <= dist
    return near


def _apply_plate(mask: np.ndarray, lines: list[dict], crop: bool) -> np.ndarray:
    """Erase plate/edge lines from the mask (and, if crop, everything beyond)."""
    if not lines:
        return mask
    H, W = mask.shape
    r, c = np.mgrid[0:H, 0:W]
    out = mask.copy()
    for ln in lines:
        a, b = (r, c) if ln["axis"] == "h" else (c, r)
        d = a - b * ln["t"] - ln["a0"]
        kill = np.abs(d) <= ln["band"]
        if crop:
            kill |= (d < 0) if ln["side"] == "lo" else (d > 0)
        out &= ~kill
        del a, b, d, kill
    return out


def _border_stroke(xy: np.ndarray, size: tuple[int, int], band: float) -> bool:
    """True if ≥ 70 % of a stroke's points lie within `band` px of the image
    edge (scan borders, torn paper edges)."""
    W, H = size
    d = np.minimum.reduce([xy[:, 0], xy[:, 1], W - 1 - xy[:, 0], H - 1 - xy[:, 1]])
    return bool(np.mean(d <= band) >= 0.7)


# --------------------------------------------------------------------------
# skeleton graph
# --------------------------------------------------------------------------

def _arclen(pts: np.ndarray) -> float:
    if len(pts) < 2:
        return 0.0
    return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))


def _trace_skeleton(skel: np.ndarray) -> tuple[list[np.ndarray], list[tuple[int, int, np.ndarray]]]:
    """Skeleton → (nodes, edges) with the same semantics as
    ``sknw.parse_struc(..., iso=False, ring=True)`` but in numpy + one plain
    Python walk, so there is no numba JIT (sknw's costs ~20 s of compile in
    every fresh process).

    A skeleton pixel with exactly two 8-neighbours is an edge pixel; any
    other is a node pixel; 8-connected node pixels form one node. Each edge
    is the ordered chain between two node pixels, INCLUDING those node
    pixels at both ends. A cycle of edge pixels with no node gets a
    pseudo-node at its first pixel (raster order) and becomes a self-loop.
    Returns nodes as (k, 2) int arrays of (row, col) pixels and edges as
    (u, v, pts) with pts (n, 2) (row, col) running from node u to node v.
    """
    sk = np.pad(np.asarray(skel, dtype=bool), 1)
    Hp, Wp = sk.shape
    flat = sk.ravel()
    offs = np.array([-Wp - 1, -Wp, -Wp + 1, -1, 1, Wp - 1, Wp, Wp + 1])
    P = np.flatnonzero(flat)
    if len(P) == 0:
        return [], []
    flags = flat[P[:, None] + offs[None, :]]
    count = flags.sum(axis=1)
    is_node = count != 2

    node_mask = np.zeros(Hp * Wp, dtype=bool)
    node_mask[P[is_node]] = True
    lab, n_nodes = ndi.label(node_mask.reshape(Hp, Wp), structure=np.ones((3, 3)))
    lab_flat = lab.ravel()
    NP = P[is_node]
    nl = lab_flat[NP] - 1
    order = np.argsort(nl, kind="stable")
    splits = np.flatnonzero(np.diff(nl[order])) + 1
    groups = np.split(NP[order], splits) if len(NP) else []
    nodes = [np.column_stack([g // Wp - 1, g % Wp - 1]) for g in groups]

    E = P[~is_node]
    fe = flags[~is_node]
    two = np.argsort(~fe, axis=1, kind="stable")[:, :2]
    nb = E[:, None] + offs[two]
    nb0 = dict(zip(E.tolist(), nb[:, 0].tolist()))
    nb1 = dict(zip(E.tolist(), nb[:, 1].tolist()))
    lab_l = lab_flat  # node label (1-based) per flat index, 0 for edge pixels
    visited: set[int] = set()
    edges_flat: list[tuple[int, int, list[int]]] = []

    def walk(prev: int, cur: int, stop: int | None) -> list[int]:
        chain = [prev]
        while True:
            chain.append(cur)
            visited.add(cur)
            a, b = nb0[cur], nb1[cur]
            nxt = b if a == prev else a
            if lab_l[nxt] or nxt == stop:
                chain.append(nxt)
                return chain
            if nxt in visited:            # degenerate: ran into a visited chain
                return chain
            prev, cur = cur, nxt

    # chains attached to nodes, in raster order of their first edge pixel
    for e in E.tolist():
        if e in visited:
            continue
        a, b = nb0[e], nb1[e]
        if lab_l[a]:
            chain = walk(a, e, None)
        elif lab_l[b]:
            chain = walk(b, e, None)
        else:
            continue
        if lab_l[chain[-1]]:
            edges_flat.append((int(lab_l[chain[0]]) - 1, int(lab_l[chain[-1]]) - 1, chain))
    # rings: remaining edge pixels
    for e in E.tolist():
        if e in visited:
            continue
        nid = len(nodes)
        nodes.append(np.array([[e // Wp - 1, e % Wp - 1]]))
        visited.add(e)
        chain = [e]
        prev, cur = e, nb0[e]
        while cur != e and cur not in visited:
            chain.append(cur)
            visited.add(cur)
            a, b = nb0[cur], nb1[cur]
            prev, cur = cur, (b if a == prev else a)
        chain.append(e)
        edges_flat.append((nid, nid, chain))
    edges = []
    for u, v, chain in edges_flat:
        c = np.asarray(chain)
        edges.append((u, v, np.column_stack([c // Wp - 1, c % Wp - 1])))
    return nodes, edges


class _Graph:
    """Small mutable multigraph over skeleton pixel chains, (row, col) floats.

    nodes[i] = {"o": centre (2,), "pts": node pixels (k, 2), "spread": float}
    edges[e] = {"u": node, "v": node, "pts": (n, 2) from u to v, "w": median width}
    adj[node] = list of (edge, side) with side 0 = edge's u end, 1 = v end.
    """

    def __init__(self, skel: np.ndarray, wmap: np.ndarray, wout: np.ndarray | None = None):
        nodes, edges = _trace_skeleton(skel)
        self.wmap = wmap                 # mask (EDT) width: drives topology decisions
        self.wout = wmap if wout is None else wout   # reported width
        self.nodes: dict[int, dict] = {}
        for i, npts in enumerate(nodes):
            q = np.asarray(npts, dtype=np.float64)
            self.nodes[i] = {"o": q.mean(axis=0), "pts": q, "spread": 0.0}
        self.edges: dict[int, dict] = {}
        self.adj: dict[int, list[tuple[int, int]]] = {i: [] for i in self.nodes}
        self._next_e = 0
        for s, e, pts in edges:
            self._add_edge(int(s), int(e), np.asarray(pts, dtype=np.float64))
        for i in self.nodes:
            self._update_spread(i)

    # ---- bookkeeping -------------------------------------------------------
    def _edge_width(self, pts: np.ndarray) -> float:
        ij = np.round(pts).astype(int)
        ij[:, 0] = np.clip(ij[:, 0], 0, self.wmap.shape[0] - 1)
        ij[:, 1] = np.clip(ij[:, 1], 0, self.wmap.shape[1] - 1)
        w = self.wmap[ij[:, 0], ij[:, 1]]
        if len(w) > 6:
            w = w[len(w) // 6: len(w) - len(w) // 6]   # ends sit in junction blobs
        return float(max(np.median(w), 1.0))

    def _add_edge(self, u: int, v: int, pts: np.ndarray) -> int:
        eid = self._next_e
        self._next_e += 1
        self.edges[eid] = {"u": u, "v": v, "pts": pts, "w": self._edge_width(pts)}
        self.adj[u].append((eid, 0))
        self.adj[v].append((eid, 1))
        return eid

    def _remove_edge(self, eid: int) -> None:
        e = self.edges.pop(eid)
        self.adj[e["u"]] = [x for x in self.adj[e["u"]] if x[0] != eid]
        if e["v"] in self.adj:
            self.adj[e["v"]] = [x for x in self.adj[e["v"]] if x[0] != eid]

    def _remove_node(self, n: int) -> None:
        assert not self.adj[n]
        del self.adj[n]
        del self.nodes[n]

    def _update_spread(self, n: int) -> None:
        nd = self.nodes[n]
        nd["spread"] = float(np.max(np.linalg.norm(nd["pts"] - nd["o"], axis=1))) if len(nd["pts"]) else 0.0

    def deg(self, n: int) -> int:
        return len(self.adj[n])

    def node_width(self, n: int, exclude: int | None = None) -> float:
        ws = [self.edges[e]["w"] for e, _ in self.adj[n] if e != exclude]
        if not ws:
            ws = [self.edges[e]["w"] for e, _ in self.adj[n]] or [1.0]
        return float(np.median(ws))

    def oriented(self, eid: int, side: int) -> np.ndarray:
        """Edge points starting at the given end."""
        p = self.edges[eid]["pts"]
        return p if side == 0 else p[::-1]

    def other_node(self, eid: int, side: int) -> int:
        e = self.edges[eid]
        return e["v"] if side == 0 else e["u"]

    # ---- simplifications --------------------------------------------------
    def merge_pass_through(self) -> int:
        """Concatenate the two edges at every degree-2 node (not pure rings)."""
        merged = 0
        for n in sorted(list(self.nodes)):
            if n not in self.nodes or self.deg(n) != 2:
                continue
            (e1, s1), (e2, s2) = self.adj[n]
            if e1 == e2:
                continue                       # isolated ring through a pseudo-node
            a = self.oriented(e1, s1)[::-1]    # ends at n
            b = self.oriented(e2, s2)          # starts at n
            pts = np.vstack([a, b])
            keep = np.ones(len(pts), bool)
            keep[1:] = np.any(np.diff(pts, axis=0) != 0, axis=1)
            pts = pts[keep]
            u = self.other_node(e1, s1)
            v = self.other_node(e2, s2)
            self._remove_edge(e1)
            self._remove_edge(e2)
            self._remove_node(n)
            self._add_edge(u, v, pts)
            merged += 1
        return merged

    def prune_spurs(self, factor: float) -> int:
        """Remove terminal branches (free end → junction) shorter than
        factor × the junction's width; iterate to a fixed point."""
        pruned = 0
        while True:
            cands = []
            for eid, e in self.edges.items():
                u, v = e["u"], e["v"]
                if u == v:
                    continue
                for tip, base in ((u, v), (v, u)):
                    if self.deg(tip) == 1 and self.deg(base) >= 3:
                        L = _arclen(e["pts"])
                        cands.append((L, eid, tip, base))
                        break
            cands.sort()
            changed = False
            for L, eid, tip, base in cands:
                if eid not in self.edges or self.deg(tip) != 1 or self.deg(base) < 3:
                    continue
                if L < factor * self.node_width(base, exclude=eid):
                    self._remove_edge(eid)
                    self._remove_node(tip)
                    pruned += 1
                    changed = True
            if not changed:
                break
            self.merge_pass_through()
        return pruned

    def _contract(self, eid: int) -> None:
        e = self.edges[eid]
        u, v = e["u"], e["v"]
        self._remove_edge(eid)
        nu, nv = self.nodes[u], self.nodes[v]
        nu["o"] = 0.5 * (nu["o"] + nv["o"])
        nu["pts"] = np.vstack([nu["pts"], nv["pts"], e["pts"]])
        for oe, side in list(self.adj[v]):
            ed = self.edges[oe]
            if side == 0:
                ed["u"] = u
            else:
                ed["v"] = u
            self.adj[u].append((oe, side))
        self.adj[v] = []
        self._remove_node(v)
        self._update_spread(u)

    def drop_small_loops(self, n: int, max_len: float) -> int:
        k = 0
        for eid, side in list(self.adj.get(n, [])):
            if eid in self.edges:
                e = self.edges[eid]
                if e["u"] == e["v"] == n and _arclen(e["pts"]) < max_len and self.deg(n) > 2:
                    self._remove_edge(eid)
                    k += 1
        return k

    def cluster_junctions(self, factor: float) -> int:
        """Contract short edges between two junction nodes (deg ≥ 3)."""
        merged = 0
        while True:
            cands = []
            for eid, e in self.edges.items():
                u, v = e["u"], e["v"]
                if u != v and self.deg(u) >= 3 and self.deg(v) >= 3:
                    L = _arclen(e["pts"])
                    w = 0.5 * (self.node_width(u, eid) + self.node_width(v, eid))
                    if L < factor * w:
                        cands.append((L, eid))
            if not cands:
                break
            changed = False
            for L, eid in sorted(cands):           # one pass, shortest first, re-validated
                if eid not in self.edges:
                    continue
                e = self.edges[eid]
                u, v = e["u"], e["v"]
                if u == v or self.deg(u) < 3 or self.deg(v) < 3:
                    continue
                L = _arclen(e["pts"])
                w = 0.5 * (self.node_width(u, eid) + self.node_width(v, eid))
                if L >= factor * w:
                    continue
                self._contract(eid)
                self.drop_small_loops(u, 2.0 * factor * w + 2.0)
                merged += 1
                changed = True
            if not changed:
                break
        return merged

    # ---- junction geometry ------------------------------------------------
    def zone_radius(self, n: int, trim: float) -> float:
        return trim * self.node_width(n) + self.nodes[n]["spread"]

    def branch_tangent(self, eid: int, side: int, o: np.ndarray, r0: float,
                       span: float) -> tuple[np.ndarray, int]:
        """Unit direction (row, col) pointing AWAY from a junction at `o`,
        from the edge's points beyond radius r0. Returns (dir, i0) where i0
        is the first index (in the oriented chain) outside the zone, or -1."""
        pts = self.oriented(eid, side)
        d = np.linalg.norm(pts - o, axis=1)
        out = np.nonzero(d > r0)[0]
        if len(out) == 0:
            v = pts[-1] - o
            nv = np.linalg.norm(v)
            return (v / nv if nv > 0 else np.array([1.0, 0.0])), -1
        i0 = int(out[0])
        seg = pts[i0:]
        s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(seg, axis=0), axis=1))])
        seg = seg[s <= span]
        if len(seg) < 3:
            v = pts[min(i0 + 2, len(pts) - 1)] - o
        else:
            c = seg - seg.mean(axis=0)
            _, _, vt = np.linalg.svd(c, full_matrices=False)
            v = vt[0]
            if np.dot(v, seg[-1] - seg[0]) < 0:
                v = -v
        nv = np.linalg.norm(v)
        return (v / nv if nv > 0 else np.array([1.0, 0.0])), i0

    def x_merge(self, factor: float, trim: float, span_f: float, max_turn: float) -> int:
        """Merge two degree-3 junctions joined by an edge ≤ factor·w when the
        four outer branches pair up straight across (one from each side) —
        the signature of a shallow X crossing."""
        cos_t = np.cos(np.radians(max_turn))
        merged = 0
        changed = True
        while changed:
            changed = False
            cands = []
            for eid, e in self.edges.items():
                u, v = e["u"], e["v"]
                if u == v or self.deg(u) != 3 or self.deg(v) != 3:
                    continue
                L = _arclen(e["pts"])
                w = 0.5 * (self.node_width(u, eid) + self.node_width(v, eid))
                if L <= factor * w:
                    cands.append((L, eid))
            for L, eid in sorted(cands):
                if eid not in self.edges:
                    continue
                e = self.edges[eid]
                u, v = e["u"], e["v"]
                if self.deg(u) != 3 or self.deg(v) != 3:
                    continue
                ends_u = [x for x in self.adj[u] if x[0] != eid]
                ends_v = [x for x in self.adj[v] if x[0] != eid]
                if len(ends_u) != 2 or len(ends_v) != 2:
                    continue
                o = 0.5 * (self.nodes[u]["o"] + self.nodes[v]["o"])
                w = 0.5 * (self.node_width(u, eid) + self.node_width(v, eid))
                r0 = trim * w + 0.5 * L
                span = max(span_f * w, 6.0)
                tu = [self.branch_tangent(a, s, o, r0, span)[0] for a, s in ends_u]
                tv = [self.branch_tangent(a, s, o, r0, span)[0] for a, s in ends_v]
                # straight-through: direction a ≈ −direction b → dot ≈ −1
                c1 = min(-np.dot(tu[0], tv[0]), -np.dot(tu[1], tv[1]))
                c2 = min(-np.dot(tu[0], tv[1]), -np.dot(tu[1], tv[0]))
                # both crossing lines must pass near the merged centre (a
                # staggered pair of T's has its stems offset by ~L/2)
                offs = []
                for (a, s), t in zip(ends_u + ends_v, tu + tv):
                    pts = self.oriented(a, s)
                    dd = np.linalg.norm(pts - o, axis=1)
                    k = np.nonzero(dd > r0)[0]
                    q = pts[k[0]] if len(k) else pts[-1]
                    rel = o - q
                    offs.append(abs(rel[0] * t[1] - rel[1] * t[0]))
                if max(offs) > 0.5 * w + 1.0:
                    continue
                if max(c1, c2) >= cos_t:
                    self._contract(eid)
                    self.drop_small_loops(u, 2.0 * factor * w + 2.0)
                    merged += 1
                    changed = True
        return merged


# --------------------------------------------------------------------------
# strokes
# --------------------------------------------------------------------------

def _hermite(p0: np.ndarray, t0: np.ndarray, p1: np.ndarray, t1: np.ndarray,
             step: float = 1.0) -> np.ndarray:
    """Interior points of a cubic Hermite from p0 (heading t0) to p1 (heading
    t1), tangent magnitudes = chord length. Endpoints excluded."""
    c = float(np.linalg.norm(p1 - p0))
    n = max(int(np.ceil(c / step)), 1)
    if n < 2:
        return np.zeros((0, 2))
    t = np.linspace(0.0, 1.0, n + 1)[1:-1][:, None]
    h00 = 2 * t**3 - 3 * t**2 + 1
    h10 = t**3 - 2 * t**2 + t
    h01 = -2 * t**3 + 3 * t**2
    h11 = t**3 - t**2
    return h00 * p0 + h10 * (t0 * c) + h01 * p1 + h11 * (t1 * c)


def _straight(p0: np.ndarray, d: np.ndarray, length: float, step: float = 1.0) -> np.ndarray:
    """Points p0 + d·k for k in (0, length], spacing ≈ step (p0 excluded)."""
    if length <= 0.25:
        return np.zeros((0, 2))
    n = max(int(np.ceil(length / step)), 1)
    k = np.linspace(0.0, length, n + 1)[1:, None]
    return p0 + d * k


class _Chainer:
    """Pairs branches at junctions and walks the paired edges into strokes."""

    def __init__(self, G: _Graph, p: ExtractParams):
        self.G, self.p = G, p
        self.cos_t = np.cos(np.radians(p.max_turn_deg))
        self.partner: dict[tuple[int, int], tuple[int, int]] = {}
        # per end: anchor index into the oriented chain, tangent away from node
        self.cut: dict[tuple[int, int], int] = {}
        self.tan: dict[tuple[int, int], np.ndarray] = {}
        self.junctions: list[int] = []
        self.tip_len: dict[tuple[int, int], float] = {}
        self._pair_all()

    def is_junction(self, n: int) -> bool:
        return self.G.deg(n) >= 3

    def _pair_all(self) -> None:
        G, p = self.G, self.p
        for n in sorted(G.nodes):
            ends = list(G.adj[n])
            if len(ends) == 2:
                self.partner[ends[0]] = ends[1]
                self.partner[ends[1]] = ends[0]
                for x in ends:
                    self.cut[x] = 0
                continue
            if len(ends) == 1:
                self._tip(ends[0])
                continue
            if len(ends) < 3:
                continue
            self.junctions.append(n)
            o = G.nodes[n]["o"]
            w = G.node_width(n)
            r0 = G.zone_radius(n, p.junction_trim)
            span = max(p.tangent_span * w, 6.0)
            for x in ends:
                d, i0 = G.branch_tangent(x[0], x[1], o, r0, span)
                self.tan[x] = d
                self.cut[x] = i0       # -1 → edge entirely inside the zone
            pairs = []
            for i in range(len(ends)):
                for j in range(i + 1, len(ends)):
                    c = -float(np.dot(self.tan[ends[i]], self.tan[ends[j]]))
                    if c >= self.cos_t:
                        pairs.append((-c, i, j))
            used: set[int] = set()
            for _, i, j in sorted(pairs):
                if i in used or j in used:
                    continue
                used |= {i, j}
                self.partner[ends[i]] = ends[j]
                self.partner[ends[j]] = ends[i]

    def _tip(self, x: tuple[int, int]) -> None:
        """Free end: skeletonize bends the last ~half width of a line toward
        a cap corner (a hook). Drop the chain within tip_trim·w of the tip
        and later re-extend straight along the tangent by the same length."""
        G, p = self.G, self.p
        eid, side = x
        self.cut[x] = 0
        if p.tip_trim <= 0:
            return
        pts = G.oriented(eid, side)
        w = G.edges[eid]["w"]
        s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
        L = p.tip_trim * w
        if s[-1] < 4.0 * L or L < 1.0:
            return
        i0 = int(np.searchsorted(s, L))
        span = max(p.tangent_span * w, 6.0)
        seg = pts[i0:][s[i0:] - s[i0] <= span]
        if len(seg) < 3:
            return
        c = seg - seg.mean(axis=0)
        v = np.linalg.svd(c, full_matrices=False)[2][0]
        if np.dot(v, seg[-1] - seg[0]) < 0:
            v = -v
        v = v / np.linalg.norm(v)                       # away from the tip, into the edge
        self.cut[x] = i0
        self.tan[x] = v
        # re-extend to the tip's projection on the tangent (not the hook's arc length)
        self.tip_len[x] = max(float(np.dot(pts[0] - pts[i0], -v)), 0.0)

    def _trimmed(self, eid: int, side: int) -> tuple[np.ndarray, int, int]:
        """Oriented chain from `side`, trimmed at junction ends. Returns
        (pts, lo, hi) indices into the oriented chain (inclusive)."""
        G = self.G
        pts = G.oriented(eid, side)
        n = len(pts)
        a = self.cut.get((eid, side), 0)
        b = self.cut.get((eid, 1 - side), 0)
        lo = a if a >= 0 else n          # -1 → fully inside
        hi = n - 1 - b if b >= 0 else -1
        if lo > hi:                      # trimmed to nothing: keep the middle
            m = n // 2
            lo = hi = m
        return pts, lo, hi

    def _end_info(self, eid: int, side: int) -> tuple[np.ndarray, np.ndarray]:
        """(anchor point, tangent pointing AWAY from the node) of an end."""
        pts, lo, _ = self._trimmed(eid, side)
        anchor = pts[lo]
        t = self.tan.get((eid, side))
        if t is None:
            k = min(lo + 3, len(pts) - 1)
            v = pts[k] - pts[lo] if k > lo else pts[lo] - pts[max(lo - 1, 0)]
            nv = np.linalg.norm(v)
            t = v / nv if nv > 0 else np.array([1.0, 0.0])
        return anchor, t

    def _node_of(self, eid: int, side: int) -> int:
        e = self.G.edges[eid]
        return e["u"] if side == 0 else e["v"]

    def _wat(self, pts: np.ndarray) -> np.ndarray:
        wm = self.G.wout
        ij = np.round(pts).astype(int)
        ij[:, 0] = np.clip(ij[:, 0], 0, wm.shape[0] - 1)
        ij[:, 1] = np.clip(ij[:, 1], 0, wm.shape[1] - 1)
        return np.maximum(wm[ij[:, 0], ij[:, 1]], 1.0)

    def _extension(self, eid: int, side: int) -> np.ndarray:
        """Straight continuation of a free end INTO its junction (towards the
        centre), ordered from the anchor outward. Empty for free tips."""
        n = self._node_of(eid, side)
        if not self.is_junction(n):
            if (eid, side) in self.tip_len:
                anchor, t = self._end_info(eid, side)
                return _straight(anchor, -t, self.tip_len[(eid, side)])
            return np.zeros((0, 2))
        anchor, t = self._end_info(eid, side)
        toward = -t
        L = float(np.dot(self.G.nodes[n]["o"] - anchor, toward))
        return _straight(anchor, toward, L)

    def walk(self, eid: int, side: int, visited: set[int]) -> dict:
        """Follow paired edges starting by entering `eid` at `side`."""
        start = (eid, side)
        pieces: list[np.ndarray] = []
        widths: list[np.ndarray] = []
        nodes_hit: list[int] = []
        n_edges = 0
        closed = False
        ext = self._extension(eid, side) if start not in self.partner else np.zeros((0, 2))
        if len(ext):
            pieces.append(ext[::-1])
            widths.append(np.full(len(ext), self._wat(self._end_info(eid, side)[0][None])[0]))
            if self.is_junction(self._node_of(eid, side)):
                nodes_hit.append(self._node_of(eid, side))
        cur = start
        while True:
            e, s = cur
            visited.add(e)
            n_edges += 1
            pts, lo, hi = self._trimmed(e, s)
            seg = pts[lo:hi + 1]
            pieces.append(seg)
            widths.append(self._wat(seg))
            end = (e, 1 - s)
            nxt = self.partner.get(end)
            node = self._node_of(e, 1 - s)
            if nxt is None:
                ext = self._extension(e, 1 - s)
                if len(ext):
                    pieces.append(ext)
                    widths.append(np.full(len(ext), widths[-1][-1]))
                    if self.is_junction(node):
                        nodes_hit.append(node)
                break
            if self.is_junction(node):
                nodes_hit.append(node)
                a0, ta = self._end_info(*end)
                a1, tb = self._end_info(*nxt)
                br = _hermite(a0, -ta, a1, tb)
                if len(br):
                    w0, w1 = widths[-1][-1], self._wat(a1[None])[0]
                    pieces.append(br)
                    widths.append(np.linspace(w0, w1, len(br) + 2)[1:-1])
            if nxt == start:
                closed = True
                break
            if nxt[0] in visited:
                break
            cur = nxt
        pts = np.vstack(pieces)
        w = np.concatenate(widths)
        return {"pts": pts, "w": w, "closed": closed, "nodes": nodes_hit, "n_edges": n_edges}

    def strokes(self) -> list[dict]:
        G = self.G
        visited: set[int] = set()
        out = []
        for eid in sorted(G.edges):
            for side in (0, 1):
                if eid in visited:
                    break
                if (eid, side) not in self.partner:
                    out.append(self.walk(eid, side, visited))
        for eid in sorted(G.edges):
            if eid not in visited:
                out.append(self.walk(eid, 0, visited))
        return out


def _clean_points(pts: np.ndarray, w: np.ndarray, closed: bool,
                  min_step: float = 0.25) -> tuple[np.ndarray, np.ndarray]:
    keep = [0]
    for i in range(1, len(pts)):
        if np.linalg.norm(pts[i] - pts[keep[-1]]) >= min_step:
            keep.append(i)
    pts, w = pts[keep], w[keep]
    if closed and len(pts) > 2 and np.linalg.norm(pts[-1] - pts[0]) < 0.75:
        pts, w = pts[:-1], w[:-1]
    return pts, w


def _destair(pts: np.ndarray, w: np.ndarray, closed: bool, step: float,
             sigma: float) -> tuple[np.ndarray, np.ndarray]:
    """Uniform arc-length resampling at `step` then Gaussian smoothing with
    σ = `sigma` (both working px) — removes the 8-connected staircase that
    inflates skeleton length by up to ~8 %, without the line-width-scale
    smoothing that would bias κ (that belongs to curvature.py downstream).
    Open strokes are padded by point reflection so endpoints stay put."""
    if step <= 0 or len(pts) < 3:
        return pts, w
    p = np.vstack([pts, pts[:1]]) if closed else pts
    ww = np.concatenate([w, w[:1]]) if closed else w
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = s[-1]
    if total <= 0:
        return pts, w
    n = max(int(round(total / step)), 3 if closed else 2)
    t = np.linspace(0.0, total, n + 1)
    if closed:
        t = t[:-1]
    q = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
    wq = np.interp(t, s, ww)
    if sigma > 0 and len(q) >= 3:
        sd = sigma * n / total             # σ in samples
        if closed:
            q = np.column_stack([gaussian_filter1d(q[:, k], sd, mode="wrap") for k in (0, 1)])
        else:
            k = min(int(4 * sd) + 1, len(q) - 1)
            left = 2 * q[0] - q[1:k + 1][::-1]
            right = 2 * q[-1] - q[-k - 1:-1][::-1]
            qq = np.vstack([left, q, right])
            qq = np.column_stack([gaussian_filter1d(qq[:, j], sd, mode="nearest") for j in (0, 1)])
            q = qq[k:k + len(q)]
    return q, wq


def _canonical(xy: np.ndarray, w: np.ndarray, closed: bool) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic orientation: open strokes start at the left-most end
    (ties: top-most); closed strokes start at the top-most point (ties:
    left-most) and run with positive shoelace area in (x, y) pixel coords."""
    if not closed:
        a, b = xy[0], xy[-1]
        if (b[0], b[1]) < (a[0], a[1]):
            return xy[::-1].copy(), w[::-1].copy()
        return xy, w
    x, y = xy[:, 0], xy[:, 1]
    area = 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    if area < 0:
        xy, w = xy[::-1], w[::-1]
    i = int(np.lexsort((xy[:, 0], xy[:, 1]))[0])
    return np.roll(xy, -i, axis=0).copy(), np.roll(w, -i).copy()


def _join_gaps(strokes: list[dict], max_gap: float, max_turn_deg: float,
               span: float) -> tuple[list[dict], int]:
    """Join open strokes whose free ends are within max_gap and point at each
    other (both end tangents and the gap direction within max_turn_deg of
    straight). Greedy by gap length over a one-off KD-tree query: joining two
    ends never changes the stroke's OTHER ends, so candidates stay valid; a
    union-find stops a chain from joining itself. Works in (row, col)."""
    if max_gap <= 0:
        return strokes, 0
    from scipy.spatial import cKDTree
    cos_t = np.cos(np.radians(max_turn_deg))

    def end_dir(q: np.ndarray) -> np.ndarray:
        s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
        k = min(max(int(np.searchsorted(s, span)), 1), len(q) - 1)
        v = q[0] - q[k]                  # outward from the stroke
        nv = np.linalg.norm(v)
        return v / nv if nv > 0 else np.zeros(2)

    ends = []                            # (stroke, at_start, point, outward dir)
    for i, s in enumerate(strokes):
        if s["closed"] or len(s["pts"]) < 3:
            continue
        ends.append((i, True, s["pts"][0], end_dir(s["pts"])))
        ends.append((i, False, s["pts"][-1], end_dir(s["pts"][::-1])))
    if len(ends) < 2:
        return strokes, 0
    tree = cKDTree(np.array([e[2] for e in ends]))
    cands = []
    for a, b in tree.query_pairs(max_gap):
        ia, _, pa, da = ends[a]
        ib, _, pb, db = ends[b]
        if ia == ib:
            continue
        g = pb - pa
        gl = float(np.linalg.norm(g))
        if gl > 1e-9:
            gu = g / gl
            if np.dot(da, gu) < cos_t or np.dot(db, -gu) < cos_t:
                continue
        if -np.dot(da, db) < cos_t:
            continue
        cands.append((gl, a, b))
    parent = list(range(len(strokes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    link: dict[tuple[int, bool], tuple[int, bool]] = {}
    joins = 0
    for gl, a, b in sorted(cands):
        ka, kb = ends[a][:2], ends[b][:2]
        if ka in link or kb in link or find(ka[0]) == find(kb[0]):
            continue
        link[ka], link[kb] = kb, ka
        parent[find(ka[0])] = find(kb[0])
        joins += 1
    if not joins:
        return strokes, 0

    out, used = [], set()
    for i in range(len(strokes)):
        if i in used:
            continue
        if strokes[i]["closed"]:
            out.append(strokes[i])
            used.add(i)
            continue
        # walk to one free end of the chain containing i
        cur, at_start = i, True
        seen = {i}
        while (cur, at_start) in link:
            j, t = link[(cur, at_start)]
            if j in seen:
                break
            seen.add(j)
            cur, at_start = j, (not t)
        # now traverse from (cur, at_start) — that end is free
        pts, ws, nodes, n_edges, gj = [], [], [], 0, 0
        entry = (cur, at_start)
        while True:
            k, from_start = entry
            used.add(k)
            S = strokes[k]
            P = S["pts"] if from_start else S["pts"][::-1]
            Wd = S["w"] if from_start else S["w"][::-1]
            if pts:
                prev_p, prev_d = pts[-1][-1], end_dir(pts[-1][::-1])
                nxt_d = end_dir(P)
                br = _hermite(prev_p, prev_d, P[0], -nxt_d)    # headings = travel direction
                pts.append(br)
                ws.append(np.linspace(ws[-1][-1], Wd[0], len(br) + 2)[1:-1])
                gj += 1
            pts.append(P)
            ws.append(Wd)
            nodes += S["nodes"]
            n_edges += S["n_edges"]
            gj += S.get("gap_joins", 0)
            far = (k, not from_start)
            if far not in link or link[far][0] in used:
                break
            j, t = link[far]
            entry = (j, t)
        out.append({"pts": np.vstack(pts), "w": np.concatenate(ws), "closed": False,
                    "nodes": nodes, "n_edges": n_edges, "gap_joins": gj})
    return out, joins


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def extract(gray: np.ndarray, *, line_width_hint: float | None = None,
            invert: bool = False, scale: float = 1.0, source: str = "",
            original_size: tuple[int, int] | None = None,
            max_side: int | None = None, **params) -> Drawing:
    """Raster line drawing → Drawing of ordered strokes.

    gray: 2-D float array in [0, 1], paper bright / ink dark (or uint8, which
        is divided by 255). Never modified.
    line_width_hint: full line width in ORIGINAL pixels; None = measured.
    invert: treat bright lines on dark ground as ink.
    scale: working px / original px of `gray` (as returned by `load_image`).
    original_size: (width, height) of the original raster; default derived
        from gray.shape / scale.
    max_side: optionally downscale `gray` further before processing.
    **params: any `ExtractParams` field.

    Returns a Drawing whose stroke points are (x, y) in ORIGINAL pixels and
    widths are full line widths in original pixels.
    """
    t_start = time.perf_counter()
    timings: dict[str, float] = {}

    def lap(name: str, t0: float) -> float:
        t = time.perf_counter()
        timings[name] = round(t - t0, 4)
        return t

    p = ExtractParams().resolved(**params)
    g = np.asarray(gray)
    if g.ndim == 3:
        g = g[..., :3].mean(axis=2)
    if g.ndim != 2:
        raise ValueError(f"gray must be 2-D, got shape {g.shape}")
    g = g.astype(np.float64) / (255.0 if g.dtype == np.uint8 else 1.0)
    if invert:
        g = 1.0 - g
    if original_size is None:
        original_size = (int(round(g.shape[1] / scale)), int(round(g.shape[0] / scale)))
    g, s2 = _downscale(g, max_side)
    scale = scale * s2

    t = time.perf_counter()
    hint = None if line_width_hint is None else line_width_hint * scale
    mask, binfo = _binarize(g, p, hint, p.border_margin * scale)
    t = lap("binarize", t)

    plate = []
    if p.drop_frames:
        plate = _plate_lines(mask, binfo["w_initial"], p)
        if plate:
            mask = _apply_plate(mask, plate, p.crop_to_plate)
            area = p.min_component_area if p.min_component_area is not None else 3.0 * binfo["w_initial"] ** 2
            mask = morphology.remove_small_objects(mask, max_size=max(int(area), 4), connectivity=2)
    binfo["plate_lines"] = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in ln.items()}
                            for ln in plate]
    t = lap("plate", t)

    n_components = int(ndi.label(mask, structure=np.ones((3, 3)))[1])
    skel = morphology.skeletonize(mask)
    w0 = binfo.pop("_w0")
    wout = _width_map(g, mask, skel, w0, binfo.pop("_window"), p.width_method)
    wtopo = np.maximum(2.0 * ndi.distance_transform_edt(mask) - 1.0, 1.0)
    w_med = float(np.median(wtopo[skel])) if skel.any() else (hint or 1.0)
    w_out_med = float(np.median(wout[skel])) if skel.any() else w_med
    t = lap("skeleton", t)

    G = _Graph(skel, wtopo, wout)
    n_merge0 = G.merge_pass_through()
    spurs = G.prune_spurs(p.spur_factor)
    clusters = G.cluster_junctions(p.cluster_factor)
    xmerged = G.x_merge(p.x_merge_factor, p.junction_trim, p.tangent_span, p.max_turn_deg)
    spurs += G.prune_spurs(p.spur_factor)
    G.merge_pass_through()
    t = lap("graph", t)

    ch = _Chainer(G, p)
    raw = ch.strokes()
    raw, joins = _join_gaps(raw, p.gap_join_factor * w_med, p.gap_join_turn_deg,
                            max(p.tangent_span * w_med, 6.0))
    t = lap("chain", t)

    inv = 1.0 / scale
    strokes: list[Stroke] = []
    dropped = 0
    dropped_border = 0
    min_len = p.min_stroke_factor * w_med
    W0, H0 = original_size
    border_band = p.border_band_frac * float(np.hypot(W0, H0))
    for r in raw:
        pts_rc, w = _clean_points(r["pts"], r["w"], r["closed"])
        if len(pts_rc) < 2:
            dropped += 1
            continue
        pts_rc, w = _destair(pts_rc, w, r["closed"], p.resample_step, p.smooth_sigma)
        if plate and np.mean(_near_plate(pts_rc, plate, 3.0 * plate[0]["band"])) >= 0.7:
            dropped_border += 1            # crumbs of an imperfectly erased plate mark
            continue
        xy = np.column_stack([pts_rc[:, 1], pts_rc[:, 0]])
        xy = (xy + 0.5) * inv - 0.5                     # pixel-centre convention
        wo = w * inv
        if r["closed"] and len(xy) < 3:
            dropped += 1
            continue
        L = _arclen(np.vstack([xy, xy[:1]]) if r["closed"] else xy)
        if L < min_len * inv:
            dropped += 1
            continue
        if border_band > 0 and _border_stroke(xy, (W0, H0), border_band):
            dropped_border += 1
            continue
        xy, wo = _canonical(xy, wo, r["closed"])
        jx = []
        for n in r["nodes"]:
            o = G.nodes[n]["o"]
            jx.append([round(float((o[1] + 0.5) * inv - 0.5), 2),
                       round(float((o[0] + 0.5) * inv - 0.5), 2)])
        strokes.append(Stroke(points=xy, width=wo, closed=bool(r["closed"]), meta={
            "junctions": jx,
            "n_edges": int(r["n_edges"]),
            "gap_joins": int(r.get("gap_joins", 0)),
            "min_width": round(float(wo.min()), 3),
            "median_width": round(float(np.median(wo)), 3),
        }))
    # deterministic stroke order: by start point (y, x)
    strokes.sort(key=lambda s: (round(s.points[0, 1], 3), round(s.points[0, 0], 3), len(s)))
    lap("output", t)
    timings["total"] = round(time.perf_counter() - t_start, 4)

    junction_nodes = [n for n in G.nodes if G.deg(n) >= 3]
    meta = {
        "params": asdict(p),
        "line_width_hint": line_width_hint,
        "invert": invert,
        "scale": scale,
        "working_shape": list(g.shape),
        "line_width_px": round(w_out_med * inv, 3),
        "mask_width_px": round(w_med * inv, 3),
        "binarize": binfo,
        "timings": timings,
        "counts": {
            "components": n_components,
            "skeleton_px": int(skel.sum()),
            "junctions": len(junction_nodes),
            "pass_through_merged": n_merge0,
            "spurs_pruned": spurs,
            "junction_clusters_merged": clusters,
            "x_merged": xmerged,
            "gap_joins": joins,
            "strokes": len(strokes),
            "strokes_closed": sum(s.closed for s in strokes),
            "strokes_dropped_short": dropped,
            "strokes_dropped_border": dropped_border,
            "plate_lines": len(binfo.get("plate_lines", [])),
        },
        "conventions": {
            "coords": "(x, y) original pixels, pixel-centre convention",
            "open_start": "left-most end (ties: top-most); direction NOT recovered",
            "closed_start": "top-most point; positive shoelace area in (x, y)",
            "v_corner": "a sharp V is one stroke with a corner (raster cannot tell)",
        },
    }
    return Drawing(strokes=strokes, source=source, size=tuple(int(v) for v in original_size), meta=meta)


def extract_file(path: str | Path, *, invert: bool = False, max_side: int | None = 3000,
                 **kw) -> Drawing:
    """`load_image` + `extract`; geometry in original pixels of the file."""
    with Image.open(path) as im:
        size = im.size
    gray, scale = load_image(path, invert=invert, max_side=max_side)
    return extract(gray, scale=scale, source=str(path), original_size=size, **kw)


_PALETTE = np.array([
    # Flexoki 600 accents (axibridge/static/css/flexoki.css)
    [0xAF, 0x30, 0x29], [0x20, 0x5E, 0xA6], [0x66, 0x80, 0x0B], [0xBC, 0x52, 0x15],
    [0x5E, 0x40, 0x9D], [0x24, 0x83, 0x7B], [0xA0, 0x2F, 0x6F], [0xAD, 0x83, 0x01],
], dtype=np.uint8)


def debug_overlay(gray: np.ndarray, drawing: Drawing, *, line_px: int = 2,
                  max_side: int | None = 2000) -> np.ndarray:
    """RGB uint8 image: the scan faded to 35 % contrast with every stroke in
    a distinct colour (cycling Flexoki accents), junction centres as black
    rings, free stroke ends as small dots, closed strokes drawn thicker.

    gray may be at any resolution (it is mapped to the drawing's original
    size); the output is downscaled to max_side.
    """
    from PIL import ImageDraw

    g = np.asarray(gray, dtype=np.float64)
    if g.max() > 1.0:
        g = g / 255.0
    W, H = drawing.size if drawing.size[0] else (g.shape[1], g.shape[0])
    s = 1.0
    if max_side and max(W, H) > max_side:
        s = max_side / max(W, H)
    ow, oh = max(int(round(W * s)), 1), max(int(round(H * s)), 1)
    base = Image.fromarray((np.clip(g, 0, 1) * 255).astype(np.uint8)).resize((ow, oh), Image.Resampling.BOX)
    b = np.asarray(base, dtype=np.float64) / 255.0
    b = 0.65 + 0.35 * b
    img = Image.fromarray(np.repeat((b * 255).astype(np.uint8)[..., None], 3, axis=2))
    dr = ImageDraw.Draw(img)
    for i, st in enumerate(drawing.strokes):
        col = tuple(int(c) for c in _PALETTE[i % len(_PALETTE)])
        q = (st.points + 0.5) * s - 0.5
        if st.closed:
            q = np.vstack([q, q[:1]])
        dr.line([tuple(v) for v in q], fill=col, width=line_px + (1 if st.closed else 0))
        if not st.closed:
            for e in (q[0], q[-1]):
                dr.ellipse([e[0] - 2, e[1] - 2, e[0] + 2, e[1] + 2], fill=col)
    seen = set()
    for st in drawing.strokes:
        for jx, jy in st.meta.get("junctions", []):
            k = (round(jx, 1), round(jy, 1))
            if k in seen:
                continue
            seen.add(k)
            x, y = (jx + 0.5) * s - 0.5, (jy + 0.5) * s - 0.5
            dr.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(16, 15, 15), width=1)
    return np.asarray(img)
