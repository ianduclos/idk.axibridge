"""A LEARNED shape vocabulary: closed shapes measured from the corpora, a
shape space, a sampler, and a line-event operator that grows a sampled
shape out of a line (results/shape_lexicon-2026-10-16.md).

Shapes (per sheet, `extract_shapes`):
  body     an ink mass: a component of the ink opened by a disc of 0.9 w
           (lines removed), deeper than 1.2 w. Its EXITS are the thin ink
           pieces that touch it (0 = a dot, 1 = terminal, 2 = through,
           ≥ 3 = node); exit positions are kept in the shape's own frame,
           so a sampled shape knows where a line may enter it.
  mark     a whole thin ink component (tick, hook, short stroke, small
           loop): the outline of a short nib stroke.
  counter  paper enclosed by ink (a background component off the border):
           the closed forms that LINES draw (Matisse's, Marden's loops,
           bowls and counters of letters, faces of Nake/Noll polygons).

Shape space: elliptic Fourier descriptors (Kuhl & Giardina 1982), contour
made counter-clockwise, normalised for position, scale, rotation and start
point; the 180° ambiguity is fixed by a sign rule on harmonic 2. Features =
harmonics 1–10 minus the three fixed terms (37 numbers); generation keeps
ORDER = 20 harmonics, so the wet low-order lumpiness survives.

Sampler (`Lexicon.sample`): a base shape from the generative-allowed pool
(optionally one shape class / one source), mixed with one of its k nearest
neighbours in feature space (λ ∈ [0.25, 0.75]) plus harmonic noise scaled to
the neighbourhood's spread. Accepted only if the outline is simple and — for
anything calligraphic — farther from every calligraphy shape than the q25
of the calligraphy nearest-neighbour distances: variation, never a copy of a
letter body or counter.

POLICY. Arabic calligraphy and print are measured (atlas, statistics) from
every sheet, but only shapes from `calligraphy.generative_allowed` sheets
enter the generative pool; `Lexicon.generative_pool` re-checks with
`calligraphy.require_generative`. Ian's reference image is atlas-only.

Growing (`grow_events`): takes `signs.plan_events` events (same sites,
sizes, sides as the hand-made operators) and replaces each operator with a
sampled shape. Heavy ops become filled BODIES (contour + inward rings, one
contiguous path: the mass regime); light ops become, half and half, COUNTER
loops drawn by the line itself (line regime) or filled MARKS (a short
learned nib stroke: the nib regime).
The insertion starts and ends at the line point, so the line stays one
polyline: L[:k] + shape + L[k:]. Junctions get a node body centred on the
crossing, rotated so its learned exits meet the lines.

`compose_learned(seed, lexicon, ...)` wraps `regime_field.compose` (not
edited): the composition's sign hook is swapped for line events grown from
the lexicon, so the same seed renders hand-made stamps vs learned shapes.
"""
from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass, field, replace

import numpy as np
from scipy import ndimage as ndi

ORDER = 20             # harmonics kept for generation
FEAT_ORDER = 10        # harmonics used as features
N_PTS = 160            # outline samples of a normalised shape

# operator → shape class wanted (fallbacks in Lexicon.sample)
HEAVY_TO_CLASS = {
    "drop": "terminal", "lozenge": "terminal", "block": "terminal", "vessel": "terminal",
    "detached": "dot", "bead": "through", "vessel_mid": "through", "knot": "through", "drip": "terminal",
    "body": "node", "junction_mass": "node", "comma": "terminal", "fill_loop": "through",
}
LIGHT_OPS = frozenset({"hook", "ring", "eye", "comb", "nib", "pupil"})


# ---------------------------------------------------------------------------
# elliptic Fourier descriptors
# ---------------------------------------------------------------------------

def signed_area(c: np.ndarray) -> float:
    x, y = c[:, 0], c[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def resample_closed(c: np.ndarray, n: int = N_PTS) -> np.ndarray:
    """n points uniformly by arc length on a closed outline (no repeat)."""
    c = np.asarray(c, float)
    if np.allclose(c[0], c[-1]):
        c = c[:-1]
    cc = np.vstack([c, c[:1]])
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(cc, axis=0), axis=1))])
    t = np.linspace(0.0, s[-1], n, endpoint=False)
    return np.column_stack([np.interp(t, s, cc[:, 0]), np.interp(t, s, cc[:, 1])])


def efd(c: np.ndarray, order: int = ORDER) -> np.ndarray:
    """(order, 4) coefficients [a, b, c, d] of a closed outline."""
    c = np.asarray(c, float)
    if not np.allclose(c[0], c[-1]):
        c = np.vstack([c, c[:1]])
    d = np.diff(c, axis=0)
    dt = np.linalg.norm(d, axis=1)
    keep = dt > 1e-12
    d, dt = d[keep], dt[keep]
    t = np.concatenate([[0.0], np.cumsum(dt)])
    T = t[-1]
    phi = 2.0 * np.pi * t / T
    out = np.zeros((order, 4))
    for n in range(1, order + 1):
        k = T / (2.0 * n * n * np.pi * np.pi)
        pn = n * phi
        dc = np.cos(pn[1:]) - np.cos(pn[:-1])
        ds = np.sin(pn[1:]) - np.sin(pn[:-1])
        out[n - 1] = k * np.array([np.sum(d[:, 0] / dt * dc), np.sum(d[:, 0] / dt * ds),
                                   np.sum(d[:, 1] / dt * dc), np.sum(d[:, 1] / dt * ds)])
    return out


def normalize_efd(coeffs: np.ndarray) -> tuple[np.ndarray, dict]:
    """Start point, rotation and scale normalised coefficients (a1 = 1,
    b1 = c1 = 0), plus the parameters {theta, psi, scale, flip}."""
    co = np.array(coeffs, float)
    a1, b1, c1, d1 = co[0]
    th = 0.5 * math.atan2(2 * (a1 * b1 + c1 * d1), a1 * a1 - b1 * b1 + c1 * c1 - d1 * d1)
    for n in range(1, len(co) + 1):
        ct, st = math.cos(n * th), math.sin(n * th)
        m = np.array([[co[n - 1, 0], co[n - 1, 1]], [co[n - 1, 2], co[n - 1, 3]]]) @ np.array([[ct, -st], [st, ct]])
        co[n - 1] = m.ravel()
    psi = math.atan2(co[0, 2], co[0, 0])
    R = np.array([[math.cos(psi), math.sin(psi)], [-math.sin(psi), math.cos(psi)]])
    for n in range(len(co)):
        co[n] = (R @ co[n].reshape(2, 2)).ravel()
    scale = abs(co[0, 0])
    co /= scale
    # 180° ambiguity: rotation by π + half-period start shift = sign flip of
    # even harmonics. Canonical: the largest |coefficient| of harmonic 2 is > 0.
    flip = False
    if len(co) > 1:
        h2 = co[1]
        if h2[np.argmax(np.abs(h2))] < 0:
            co[1::2] *= -1.0
            flip = True
    return co, {"theta": th, "psi": psi, "scale": scale, "flip": flip}


def reconstruct(coeffs: np.ndarray, n: int = N_PTS, order: int | None = None) -> np.ndarray:
    """Outline (n, 2) of normalised coefficients, centred at 0 (no repeat)."""
    co = coeffs[:order] if order else coeffs
    t = np.linspace(0, 1, n, endpoint=False)
    k = np.arange(1, len(co) + 1)[:, None]
    C, S = np.cos(2 * np.pi * k * t), np.sin(2 * np.pi * k * t)
    x = (co[:, 0:1] * C + co[:, 1:2] * S).sum(0)
    y = (co[:, 2:3] * C + co[:, 3:4] * S).sum(0)
    return np.column_stack([x, y])


def features(coeffs: np.ndarray, order: int = FEAT_ORDER) -> np.ndarray:
    """Shape-space vector: normalised harmonics 1..order without the fixed
    a1, b1, c1 (so d1 = minor/major of the first ellipse leads)."""
    return np.asarray(coeffs[:order], float).ravel()[3:]


def _to_unit_frame(raw: np.ndarray, norm: np.ndarray):
    """Similarity transform taking a raw outline onto its normalised
    reconstruction. Tries the four rotation candidates (±psi, +0/π) by
    nearest-point distance — robust to the sign conventions above.
    Returns f(points) → unit-frame points."""
    from scipy.spatial import cKDTree
    z = resample_closed(raw, 256)
    centre = z.mean(axis=0)
    tree = cKDTree(norm)
    best = None
    for ang in _candidate_angles(z - centre, norm):
        for refl in (False,):
            ca, sa = math.cos(ang), math.sin(ang)
            Rm = np.array([[ca, -sa], [sa, ca]])
            sc = _scale_guess(z - centre, norm)
            q = (z - centre) @ Rm.T * sc
            e = float(np.mean(tree.query(q)[0]))
            if best is None or e < best[0]:
                best = (e, Rm, sc)
    _, Rm, sc = best
    return lambda p: (np.asarray(p, float) - centre) @ Rm.T * sc


def _scale_guess(zc, norm):
    return math.sqrt(np.mean(np.sum(norm ** 2, 1)) / max(np.mean(np.sum(zc ** 2, 1)), 1e-12))


def _candidate_angles(zc, norm):
    # principal axis of both, then the four sign/π options (+ fine search)
    def ax(p):
        w, v = np.linalg.eigh(np.cov(p.T))
        return math.atan2(v[1, -1], v[0, -1])
    base = ax(norm) - ax(zc)
    return [base + k * math.pi / 2 + e for k in range(4) for e in np.radians(np.arange(-20, 21, 5))]


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------

def ink_gray(rgb: np.ndarray, mode: str = "black") -> np.ndarray:
    """RGB → gray, ink dark. 'black'/'lum'/'white' as calligraphy.to_gray;
    'colour': dark OR saturated is ink (Cohen's painted shapes)."""
    from . import calligraphy as cg
    if mode != "colour":
        return cg.to_gray(rgb, mode)
    a = np.asarray(rgb, float)
    a = a / 255.0 if a.max() > 1 else a
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1e-3)
    lum = a @ np.array([0.299, 0.587, 0.114])
    return np.clip(np.minimum(lum, 1.0 - 1.4 * sat), 0, 1)


def ink_mask(g: np.ndarray) -> np.ndarray:
    """Background-normalised Otsu (as regime_study._ink_mask_generic)."""
    from skimage.filters import threshold_otsu
    gb = ndi.gaussian_filter(g, 0.8)
    size = max(31, int(0.04 * max(g.shape)) | 1)
    small = gb[::4, ::4]
    bg = ndi.grey_closing(small, size=(size // 4 | 1, size // 4 | 1))
    bg = ndi.zoom(bg, (g.shape[0] / bg.shape[0], g.shape[1] / bg.shape[1]), order=1)[:g.shape[0], :g.shape[1]]
    n = np.clip(gb / np.maximum(bg, 0.05), 0, 1.2)
    t = min(threshold_otsu(n[::2, ::2]), 0.72)
    return n < t


def _disk(r: float) -> np.ndarray:
    R = max(int(math.ceil(r)), 1)
    y, x = np.mgrid[-R:R + 1, -R:R + 1]
    return x * x + y * y <= r * r + 1e-9


def _outer_contour(reg: np.ndarray):
    from skimage.measure import find_contours
    f = ndi.gaussian_filter(np.pad(reg.astype(float), 2), 0.7)
    cs = find_contours(f, 0.5)
    if not cs:
        return None
    c = max(cs, key=len)[:, ::-1] - 2.0
    return c


@dataclass
class Shape:
    source: str
    sheet: str
    kind: str                    # body | counter
    klass: str                   # dot | terminal | through | node | loop
    coeffs: np.ndarray           # (ORDER, 4) normalised
    outline: np.ndarray          # (N_PTS, 2) measured outline in the unit frame
    exits: np.ndarray            # (k, 2) exit points in the unit frame
    D_w: float                   # equivalent diameter / line width
    solidity: float
    generative: bool
    bbox: tuple = ()             # (x0, y0, x1, y1) px in the sheet raster
    meta: dict = field(default_factory=dict)

    def feat(self) -> np.ndarray:
        return features(self.coeffs)

    def to_json(self) -> dict:
        return {"source": self.source, "sheet": self.sheet, "kind": self.kind, "klass": self.klass,
                "coeffs": np.round(self.coeffs, 5).tolist(), "outline": np.round(self.outline, 4).tolist(),
                "exits": np.round(self.exits, 4).tolist(), "D_w": round(self.D_w, 3),
                "solidity": round(self.solidity, 4), "generative": self.generative,
                "bbox": list(self.bbox), "meta": self.meta}

    @staticmethod
    def from_json(d: dict) -> "Shape":
        return Shape(d["source"], d["sheet"], d["kind"], d["klass"], np.asarray(d["coeffs"], float),
                     np.asarray(d["outline"], float), np.asarray(d["exits"], float).reshape(-1, 2), d["D_w"],
                     d["solidity"], d["generative"], tuple(d.get("bbox", ())), d.get("meta", {}))


def shape_from_contour(c: np.ndarray, *, exits_px=None, **kw) -> Shape | None:
    """Normalise one closed contour (px) into a Shape. None if degenerate."""
    from shapely.geometry import Polygon
    c = np.asarray(c, float)
    if len(c) < 12:
        return None
    if signed_area(c) < 0:
        c = c[::-1]
    co = efd(c, ORDER)
    if not np.all(np.isfinite(co)) or np.linalg.norm(co[0]) < 1e-9:
        return None
    nco, _ = normalize_efd(co)
    if not np.all(np.isfinite(nco)):
        return None
    rec = reconstruct(nco, N_PTS)
    f = _to_unit_frame(c, rec)
    outline = resample_closed(f(c), N_PTS)
    ex = f(np.asarray(exits_px, float).reshape(-1, 2)) if exits_px is not None and len(exits_px) else np.zeros((0, 2))
    poly = Polygon(c).buffer(0)
    sol = float(poly.area / max(poly.convex_hull.area, 1e-9)) if not poly.is_empty else 0.0
    return Shape(coeffs=nco, outline=outline, exits=ex, solidity=sol, **kw)


def _klass(kind: str, n_exits: int) -> str:
    if kind == "counter":
        return "loop"
    return {0: "dot", 1: "terminal", 2: "through"}.get(n_exits, "node")


def extract_shapes(g: np.ndarray, *, source: str, sheet: str, generative: bool, max_per_kind: int = 150,
                   seed: int = 0, min_D_px: float = 14.0, deep_w: float = 1.2) -> tuple[list[Shape], dict]:
    """Bodies (with exits) and counters of one sheet. g: gray, ink dark."""
    from . import signs
    mask = ink_mask(g)
    H, W = mask.shape
    if mask.mean() > 0.6 or mask.sum() < 50:
        return [], {"sheet": sheet, "source": source, "skipped": "mask"}
    w = max(signs.line_width(mask), 1.0)
    rng = np.random.default_rng(seed)
    out: list[Shape] = []
    info = {"sheet": sheet, "source": source, "w_px": w, "shape": [H, W], "ink_frac": float(mask.mean())}

    # bodies
    opened = ndi.binary_opening(mask, structure=_disk(0.9 * w / 2 + 0.5))
    edt = ndi.distance_transform_edt(opened)
    lab, n = ndi.label(opened)
    thin = mask & ~opened
    sl = ndi.find_objects(lab)
    cand = []
    for k in range(1, n + 1):
        s = sl[k - 1]
        if s is None:
            continue
        y0, y1, x0, x1 = s[0].start, s[0].stop, s[1].start, s[1].stop
        if y0 == 0 or x0 == 0 or y1 == H or x1 == W:
            continue
        reg = lab[s] == k
        A = int(reg.sum())
        D = math.sqrt(4 * A / math.pi)
        if D < max(min_D_px, 2.5 * w) or D > 0.25 * max(H, W):
            continue
        if edt[s][reg].max() < deep_w * w:
            continue
        cand.append((k, s, D))
    if len(cand) > max_per_kind:
        cand = [cand[i] for i in rng.choice(len(cand), max_per_kind, replace=False)]
    for k, s, D in cand:
        pad = int(3 * w) + 3
        y0, x0 = max(s[0].start - pad, 0), max(s[1].start - pad, 0)
        y1, x1 = min(s[0].stop + pad, H), min(s[1].stop + pad, W)
        reg = lab[y0:y1, x0:x1] == k
        ring = ndi.binary_dilation(reg, structure=_disk(2.5)) & ~reg
        touch = ring & thin[y0:y1, x0:x1]
        tl, tn = ndi.label(touch, structure=np.ones((3, 3)))
        exits = []
        if tn:
            sizes = ndi.sum(touch, tl, range(1, tn + 1))
            cms = ndi.center_of_mass(touch, tl, range(1, tn + 1))
            exits = [(cx, cy) for (cy, cx), sz in zip(cms, sizes) if sz >= max(2.0, 0.5 * w)]
        c = _outer_contour(reg)
        if c is None:
            continue
        sh = shape_from_contour(c, exits_px=exits, source=source, sheet=sheet, kind="body",
                                klass=_klass("body", len(exits)), D_w=D / w, generative=generative,
                                bbox=(x0 + int(c[:, 0].min()), y0 + int(c[:, 1].min()),
                                      x0 + int(c[:, 0].max()), y0 + int(c[:, 1].max())),
                                meta={"n_exits": len(exits)})
        if sh is not None:
            out.append(sh)
    info["bodies"] = len(out)

    # marks: whole thin components (ticks, hooks, short strokes, small
    # loops) — the outline of a short nib stroke
    full_edt = ndi.distance_transform_edt(mask)
    lab2, n2 = ndi.label(mask, structure=np.ones((3, 3)))
    sl2 = ndi.find_objects(lab2)
    cand = []
    for k in range(1, n2 + 1):
        s = sl2[k - 1]
        if s is None or s[0].start == 0 or s[1].start == 0 or s[0].stop == H or s[1].stop == W:
            continue
        if max(s[0].stop - s[0].start, s[1].stop - s[1].start) > 30 * w:
            continue
        reg = lab2[s] == k
        A = int(reg.sum())
        if A < (1.5 * w) ** 2 or math.sqrt(4 * A / math.pi) < 0.6 * min_D_px:
            continue
        if full_edt[s][reg].max() >= deep_w * w:
            continue
        cand.append((k, s, math.sqrt(4 * A / math.pi)))
    if len(cand) > max_per_kind:
        cand = [cand[i] for i in rng.choice(len(cand), max_per_kind, replace=False)]
    nm = 0
    for k, s, D in cand:
        reg = np.pad(lab2[s] == k, 2)
        c = _outer_contour(reg)
        if c is None:
            continue
        c = c - 2.0
        sh = shape_from_contour(c, source=source, sheet=sheet, kind="mark", klass="mark", D_w=D / w,
                                generative=generative, bbox=(s[1].start, s[0].start, s[1].stop, s[0].stop))
        if sh is not None:
            out.append(sh)
            nm += 1
    info["marks"] = nm

    # counters (paper enclosed by ink)
    bgl, nb = ndi.label(~mask)
    slb = ndi.find_objects(bgl)
    cand = []
    amin, amax = (2.5 * w) ** 2, 0.04 * H * W
    for k in range(1, nb + 1):
        s = slb[k - 1]
        if s is None:
            continue
        if s[0].start == 0 or s[1].start == 0 or s[0].stop == H or s[1].stop == W:
            continue
        reg = bgl[s] == k
        A = int(reg.sum())
        if A < amin or A > amax:
            continue
        D = math.sqrt(4 * A / math.pi)
        if D < min_D_px:
            continue
        cand.append((k, s, D))
    if len(cand) > max_per_kind:
        cand = [cand[i] for i in rng.choice(len(cand), max_per_kind, replace=False)]
    nc = 0
    for k, s, D in cand:
        reg = bgl[s] == k
        c = _outer_contour(reg)
        if c is None:
            continue
        sh = shape_from_contour(c, source=source, sheet=sheet, kind="counter", klass="loop", D_w=D / w,
                                generative=generative,
                                bbox=(s[1].start, s[0].start, s[1].stop, s[0].stop))
        if sh is not None and sh.coeffs[0, 3] > 0.06:        # not a sliver
            out.append(sh)
            nc += 1
    info["counters"] = nc
    return out, info


# ---------------------------------------------------------------------------
# the lexicon: shape space, clusters, sampler
# ---------------------------------------------------------------------------

def is_calligraphic(source: str) -> bool:
    return source in ("calligraphy", "print")


class Lexicon:
    """Shape space over a list of Shapes: PCA coordinates, clusters, kNN,
    and a sampler over the generative pool."""

    def __init__(self, shapes: list[Shape], *, n_pca: int = 12, k_clusters: int = 16, seed: int = 0):
        from sklearn.cluster import KMeans
        from sklearn.decomposition import PCA
        from scipy.spatial import cKDTree
        self.shapes = list(shapes)
        X = np.array([s.feat() for s in self.shapes])
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-6
        Z = (X - self.mu) / self.sd
        self.pca = PCA(n_components=min(n_pca, Z.shape[1], len(Z)), random_state=seed).fit(Z)
        self.Y = self.pca.transform(Z)
        self.km = KMeans(n_clusters=min(k_clusters, len(Z)), n_init=4, random_state=seed).fit(self.Y)
        self.labels = self.km.labels_
        self.tree = cKDTree(self.Y)
        cal = [i for i, s in enumerate(self.shapes) if is_calligraphic(s.source)]
        self.cal_idx = np.array(cal, int)
        if len(cal) > 3:
            self.cal_tree = cKDTree(self.Y[cal])
            d, _ = self.cal_tree.query(self.Y[cal], k=2)
            self.copy_floor = float(np.quantile(d[:, 1], 0.25))
        else:
            self.cal_tree, self.copy_floor = None, 0.0

    def embed(self, coeffs: np.ndarray) -> np.ndarray:
        return self.pca.transform(((features(coeffs) - self.mu) / self.sd)[None])[0]

    def generative_pool(self, *, klass=None, kind=None, sources=None) -> np.ndarray:
        from . import calligraphy as cg
        idx = []
        for i, s in enumerate(self.shapes):
            if not s.generative:
                continue
            if klass is not None and s.klass not in (klass if isinstance(klass, (set, tuple, list)) else {klass}):
                continue
            if kind is not None and s.kind != kind:
                continue
            if sources is not None and s.source not in sources:
                continue
            idx.append(i)
        cal_sheets = sorted({self.shapes[i].sheet for i in idx if self.shapes[i].source == "calligraphy"})
        if cal_sheets:
            cg.require_generative(cal_sheets)      # raises on any measure-only sheet
        if any(self.shapes[i].source == "print" for i in idx):
            raise cg.PolicyError("print shapes are measure-only (books / cassettes)")
        return np.array(idx, int)

    def sample(self, rng: np.random.Generator, *, klass=None, kind=None, sources=None, k: int = 8,
               noise: float = 0.35, tries: int = 30, order: int = ORDER, base: int | None = None):
        """→ (outline (N_PTS, 2) unit frame, exits (m, 2), info). Mix of a
        base shape and a neighbour + harmonic noise; simple outlines only;
        calligraphic bases must land farther than `copy_floor` from every
        calligraphy shape."""
        from shapely.geometry import Polygon
        pool = None
        for kl in _fallbacks(klass):
            pool = self.generative_pool(klass=kl, kind=kind, sources=sources)
            if len(pool):
                break
        if pool is None or not len(pool):
            raise ValueError("empty generative pool")
        from scipy.spatial import cKDTree
        ptree = cKDTree(self.Y[pool])
        for _ in range(tries):
            i = int(base) if base is not None else int(pool[rng.integers(len(pool))])
            kk = min(k + 1, len(pool))
            _, nn = ptree.query(self.Y[i], k=kk)
            nn = np.atleast_1d(nn)
            nb = [int(pool[j]) for j in nn if int(pool[j]) != i] or [i]
            j = nb[rng.integers(len(nb))]
            lam = rng.uniform(0.25, 0.75)
            ci, cj = self.shapes[i].coeffs, self.shapes[j].coeffs
            co = (1 - lam) * ci + lam * cj
            spread = np.std(np.stack([self.shapes[m].coeffs for m in [i] + nb]), axis=0)
            co = co + noise * spread * rng.standard_normal(co.shape)
            co[0] = [1.0, 0.0, 0.0, co[0, 3]]
            U = reconstruct(co, N_PTS, order)
            P = Polygon(U)
            if not P.is_valid or P.area < 0.05:
                continue
            calli = is_calligraphic(self.shapes[i].source) or is_calligraphic(self.shapes[j].source)
            if calli and self.cal_tree is not None:
                d, _ = self.cal_tree.query(self.embed(co))
                if d < self.copy_floor:
                    continue
            ex = self.shapes[i].exits
            if len(ex):
                ex = U[[int(np.argmin(np.linalg.norm(U - e, axis=1))) for e in ex]]
            return U, ex, {"base": i, "mix": j, "lam": float(lam), "source": self.shapes[i].source,
                           "klass": self.shapes[i].klass, "kind": self.shapes[i].kind, "coeffs": co}
        s = self.shapes[int(pool[rng.integers(len(pool))])]
        U = reconstruct(s.coeffs, N_PTS, 8)          # fallback: a heavily smoothed shape
        return U, np.zeros((0, 2)), {"base": -1, "source": s.source, "klass": s.klass, "kind": s.kind,
                                     "coeffs": s.coeffs[:8]}


def _fallbacks(klass):
    if klass is None:
        return [None]
    order = {"terminal": ["terminal", "through", "dot"], "through": ["through", "terminal", "node"],
             "node": ["node", "through", "terminal"], "dot": ["dot", "terminal"], "loop": ["loop"], "mark": ["mark", "loop"]}
    return order.get(klass, [klass]) + [None]


# ---------------------------------------------------------------------------
# growing shapes out of lines
# ---------------------------------------------------------------------------

def _rot(p: np.ndarray, ang: float) -> np.ndarray:
    c, s = math.cos(ang), math.sin(ang)
    return np.asarray(p, float) @ np.array([[c, s], [-s, c]])


def _arc(p: np.ndarray) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def _at(p: np.ndarray, s: float):
    S = _arc(p)
    s = float(np.clip(s, 0, S[-1]))
    k = int(np.clip(np.searchsorted(S, s), 1, len(p) - 1))
    f = (s - S[k - 1]) / max(S[k] - S[k - 1], 1e-12)
    P = p[k - 1] + f * (p[k] - p[k - 1])
    a, b = np.searchsorted(S, s - 1.0), np.searchsorted(S, s + 1.0)
    a, b = max(min(a, len(p) - 2), 0), min(max(b, a + 1), len(p) - 1)
    t = p[b] - p[a]
    t = t / max(np.linalg.norm(t), 1e-12)
    return P, t, k


def fill_path(Q: np.ndarray, pen: float, *, rings: int | None = None, start=None) -> np.ndarray:
    """Outline Q (closed, no repeat) traced from the vertex nearest `start`,
    then inward rings every 0.8 pen (all of them, or `rings`), each entered
    at its point nearest the previous end: ONE contiguous path. Concentric
    rings run along the outline — no hatching."""
    from shapely.geometry import Polygon
    Q = np.asarray(Q, float)
    i0 = int(np.argmin(np.linalg.norm(Q - start, axis=1))) if start is not None else 0
    out = [np.vstack([np.roll(Q, -i0, axis=0), Q[i0:i0 + 1]])]
    poly = Polygon(Q).buffer(0)
    k = 1
    while rings is None or k <= rings:
        g = poly.buffer(-0.8 * pen * k, join_style=1)
        if g.is_empty or g.area < (0.3 * pen) ** 2:
            break
        parts = list(g.geoms) if hasattr(g, "geoms") else [g]
        for part in sorted(parts, key=lambda q: -q.area):
            r = np.asarray(part.exterior.coords)[:-1]
            if len(r) < 3:
                continue
            j = int(np.argmin(np.linalg.norm(r - out[-1][-1], axis=1)))
            out.append(np.vstack([np.roll(r, -j, axis=0), r[j:j + 1]]))
        k += 1
        if k > 400:
            break
    return np.vstack(out)


def place_attached(U: np.ndarray, ia: int, P: np.ndarray, direction: np.ndarray, size: float) -> np.ndarray:
    """Scale U to diameter ≈ size, put U[ia] on P with the body extending
    along `direction` (centroid − attach point ∥ direction)."""
    D = 2.0 * math.sqrt(abs(signed_area(U)) / math.pi)
    sc = size / max(D, 1e-9)
    v = U.mean(0) - U[ia]
    ang = math.atan2(direction[1], direction[0]) - math.atan2(v[1], v[0])
    return _rot((U - U[ia]) * sc, ang) + P


def place_centred(U: np.ndarray, P: np.ndarray, size: float, ang: float) -> np.ndarray:
    D = 2.0 * math.sqrt(abs(signed_area(U)) / math.pi)
    return _rot((U - U.mean(0)) * size / max(D, 1e-9), -ang) + P


@dataclass
class GrownEvent:
    op: str
    site: str
    klass: str
    filled: bool
    info: dict


def _shape_for(ev, lex: Lexicon, rng, sources, light_as_loop=True):
    if ev.op in LIGHT_OPS and light_as_loop:
        if rng.random() < 0.5:
            return lex.sample(rng, klass="loop", sources=sources), "loop", False
        return lex.sample(rng, klass="mark", sources=sources), "mark", True
    kl = HEAVY_TO_CLASS.get(ev.op, "terminal")
    return lex.sample(rng, klass=kl, kind="body", sources=sources), kl, True


def grow_events(lines, events, lex: Lexicon, rng: np.random.Generator, *, w: float, pen: float,
                sources=None, splice: bool = True, size_k: float = 1.0) -> tuple[list[np.ndarray], list[GrownEvent]]:
    """Polylines: the lines with learned shapes grown at the events' sites.
    splice=True: end/interior shapes are inserted INTO their line (one
    polyline per line); junction nodes and detached dots are separate
    paths. splice=False: lines untouched, only the added paths (each
    starting on its line) — for compose's sign hook."""
    arrs = [np.asarray(p, float) for p in lines]
    inserts: dict[int, list] = {i: [] for i in range(len(arrs))}
    extra: list[np.ndarray] = []
    log: list[GrownEvent] = []
    for ev in events:
        p = arrs[ev.line]
        size = max(ev.size * size_k, 2.5 * pen)
        (U, ex, info), kl, filled = _shape_for(ev, lex, rng, sources)
        if ev.site == "junction" and ev.other is not None:
            P, t, _ = _at(p, ev.s)
            j, sj = ev.other
            dirs = [t, -t]
            Pj, tj, _ = _at(arrs[j], sj)
            dirs += [tj, -tj]
            ang = _best_rotation(U, ex, dirs)
            Q = place_centred(U, P, size, ang)
            extra.append(fill_path(Q, pen) if filled else np.vstack([Q, Q[:1]]))
            log.append(GrownEvent(ev.op, ev.site, kl, filled, info))
            continue
        if ev.site == "end":
            s = 0.0 if ev.end == 0 else _arc(p)[-1]
            P, t, k = _at(p, s)
            fwd = -t if ev.end == 0 else t
            if ev.op == "detached" or kl == "dot":
                gap = 0.9 * size
                Q = place_centred(U, P + fwd * (gap + 0.5 * size), size, rng.uniform(0, 2 * np.pi))
                extra.append(fill_path(Q, pen) if filled else np.vstack([Q, Q[:1]]))
                log.append(GrownEvent(ev.op, ev.site, kl, filled, info))
                continue
            ia = _attach_index(U, ex, rng)
            Q = place_attached(U, ia, P, fwd, size)
            path = fill_path(Q, pen, start=P) if filled else _loop_from(Q, P)
            inserts[ev.line].append((s, path, ev.end))
            log.append(GrownEvent(ev.op, ev.site, kl, filled, info))
            continue
        # interior / loop / corner: the shape hangs off the line on ev.side
        P, t, k = _at(p, ev.s)
        nrm = np.array([-t[1], t[0]]) * (1.0 if ev.side >= 0 else -1.0)
        ia = _attach_index(U, ex, rng)
        if filled and kl == "through" and len(ex) >= 2:
            ang = _best_rotation(U, ex[:2], [t, -t])
            Q = place_centred(U, P, size, ang)
        else:
            Q = place_attached(U, ia, P, nrm, size)
        path = fill_path(Q, pen, start=P) if filled else _loop_from(Q, P)
        inserts[ev.line].append((ev.s, np.vstack([P, path, P]), -1))
        log.append(GrownEvent(ev.op, ev.site, kl, filled, info))
    out: list[np.ndarray] = []
    for i, p in enumerate(arrs):
        ins = sorted(inserts[i], key=lambda x: x[0])
        if not splice:
            out += [q for _, q, _ in ins]
            continue
        if not ins:
            out.append(p)
            continue
        S = _arc(p)
        pieces, s_prev = [], -1.0
        head = [q for s, q, e in ins if e == 0]
        if head:            # start-end shape: drawn first, then the line leaves it
            pieces.append(head[0][::-1])
        for s, q, e in ins:
            if e != -1:
                continue
            seg = p[(S > s_prev) & (S < s)]
            pieces += [seg, q]
            s_prev = s
        pieces.append(p[S > s_prev])
        tail = [q for s, q, e in ins if e == 1]
        if tail:
            pieces.append(tail[0])
        out.append(np.vstack([x for x in pieces if len(x)]))
    if not splice:
        return out + extra, log
    return out + extra, log


def _loop_from(Q: np.ndarray, P: np.ndarray) -> np.ndarray:
    i0 = int(np.argmin(np.linalg.norm(Q - P, axis=1)))
    return np.vstack([np.roll(Q, -i0, axis=0), Q[i0:i0 + 1]])


def _attach_index(U, ex, rng) -> int:
    if len(ex):
        e = ex[rng.integers(len(ex))]
        return int(np.argmin(np.linalg.norm(U - e, axis=1)))
    # no learned exit (counters): attach where the outline is flattest, so
    # the line meets the shape on a side, not on a cusp
    d = np.roll(U, -1, 0) - 2 * U + np.roll(U, 1, 0)
    k = np.linalg.norm(ndi.gaussian_filter1d(d, 3, axis=0, mode="wrap"), axis=1)
    cand = np.argsort(k)[: max(len(U) // 6, 1)]
    return int(cand[rng.integers(len(cand))])


def _best_rotation(U, ex, dirs) -> float:
    """Rotation of U (about its centroid) that best points its learned exits
    along the given directions."""
    if not len(ex):
        return math.atan2(dirs[0][1], dirs[0][0])
    c = U.mean(0)
    ea = np.array([math.atan2(*(e - c)[::-1]) for e in ex])
    da = np.array([math.atan2(d[1], d[0]) for d in dirs])
    best, ba = 1e9, 0.0
    for a in np.linspace(0, 2 * np.pi, 72, endpoint=False):
        # place_centred(.., ang) rotates by -ang: exits at ea - a
        diff = np.abs((ea[:, None] - a - da[None, :] + np.pi) % (2 * np.pi) - np.pi)
        sc = float(diff.min(axis=1).sum())
        if sc < best:
            best, ba = sc, a
    return ba


# ---------------------------------------------------------------------------
# compose wrapper (regime_field is not edited: its engine factory is swapped
# for the call)
# ---------------------------------------------------------------------------

@contextmanager
def _patched_engine(lex: Lexicon, sources=None, size_k: float = 1.0):
    from . import regime_field as rf
    from . import signs
    orig = rf.engine

    def patched(which: str = "auto", nib_renderer=None):
        e = orig(which, nib_renderer=nib_renderer)

        def grown(lines, rng, *, n, w, pen, grouped=False):
            ev_w = w / 0.6 * 0.6          # compose's sign_w is already a line width
            evs = signs.plan_events(lines, rng, None, w=ev_w, n=n)
            paths, _ = grow_events(lines, evs, lex, rng, w=ev_w, pen=pen, sources=sources, splice=False,
                                   size_k=size_k)
            return [[q] for q in paths] if grouped else paths

        return replace(e, signs=grown, signs_name="shape_lexicon")

    rf.engine = patched
    try:
        yield
    finally:
        rf.engine = orig


def compose_learned(seed: int, lex: Lexicon, *, sources=None, size_k: float = 1.0, **kw):
    """regime_field.compose with the sign hook replaced by learned shapes
    grown at line-event sites. Same seed + kwargs as a plain compose call →
    the same structure, hands and regimes; only the signs differ."""
    from . import regime_field as rf
    with _patched_engine(lex, sources, size_k):
        return rf.compose(seed, **kw)


# ---------------------------------------------------------------------------
# shapes as a language: adjacency of shapes on a sheet
# ---------------------------------------------------------------------------

def neighbour_pairs(shapes: list[Shape], *, gap_w: float = 2.5, w_px: float = 1.0) -> list[tuple[int, int]]:
    """Index pairs of shapes on ONE sheet whose bounding boxes come within
    gap_w line widths (a cheap stand-in for "joined by a line or a shared
    wall"); each pair once."""
    out = []
    g = gap_w * w_px
    for a in range(len(shapes)):
        xa0, ya0, xa1, ya1 = shapes[a].bbox
        for b in range(a + 1, len(shapes)):
            xb0, yb0, xb1, yb1 = shapes[b].bbox
            if xa0 - g <= xb1 and xb0 - g <= xa1 and ya0 - g <= yb1 and yb0 - g <= ya1:
                out.append((a, b))
    return out


def transition_stats(labels_a: np.ndarray, labels_b: np.ndarray, k: int) -> dict:
    """Symmetric co-occurrence of cluster labels over neighbour pairs:
    counts, lift (observed / independent expectation) and mutual
    information (bits)."""
    C = np.zeros((k, k))
    for a, b in zip(labels_a, labels_b):
        C[a, b] += 1
        C[b, a] += 1
    tot = C.sum()
    if tot == 0:
        return {"counts": C, "lift": np.ones_like(C), "mi": 0.0}
    P = C / tot
    pa = P.sum(1)
    E = np.outer(pa, pa)
    with np.errstate(divide="ignore", invalid="ignore"):
        lift = np.where(E > 0, P / E, 1.0)
        mi = float(np.nansum(np.where(P > 0, P * np.log2(P / np.maximum(E, 1e-300)), 0.0)))
    return {"counts": C, "lift": lift, "mi": mi}


def grow_sequence(line: np.ndarray, items: list[dict], pen: float, rng: np.random.Generator) -> np.ndarray:
    """One polyline: `line` with a given sequence of shapes hung off it.
    items: dicts with s (arc), size, side (±1), coeffs (normalised EFD),
    rings (None = filled, 0 = outline only = the line draws the shape,
    k = k inward rings = a thick rim, the nib between line and mass)."""
    p = np.asarray(line, float)
    S = _arc(p)
    pieces, s_prev = [], -1.0
    for it in sorted(items, key=lambda d: d["s"]):
        P, t, _ = _at(p, it["s"])
        nrm = np.array([-t[1], t[0]]) * (1.0 if it.get("side", 1) >= 0 else -1.0)
        U = reconstruct(np.asarray(it["coeffs"], float), N_PTS)
        ia = _attach_index(U, np.zeros((0, 2)), rng)
        Q = place_attached(U, ia, P, nrm, it["size"])
        rings = it.get("rings")
        path = _loop_from(Q, P) if rings == 0 else fill_path(Q, pen, rings=rings, start=P)
        pieces += [p[(S > s_prev) & (S < it["s"])], P[None], path, P[None]]
        s_prev = it["s"]
    pieces.append(p[S > s_prev])
    return np.vstack([x for x in pieces if len(x)])
