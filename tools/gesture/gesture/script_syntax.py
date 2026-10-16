"""Script as a syntax for non-linguistic gestures (research, round 8).

Arabic-script writing is, among other things, a system for joining marks
into a line: a baseline, connected bodies ("parts of words") separated by
gaps, ascender peaks rising out of a low band, bowls and tails dropping
below it, small dots (nuqta) and marks placed in relation to the bodies,
lines that step or climb (shikasta, diwani), and — in siyah mashq practice
sheets — lines overwritten until the page goes black.

This module measures that syntax from ink masks and represents it as SLOTS
that know nothing about letters: every quantity is in nuqta units w (the
pen width) and refers to bounding boxes, column-height profiles, gaps and
offsets. No glyph identity, no shapes of letters are stored. Then it
assembles foreign fragments (Matisse contours, Hokusai strokes) into those
slots: the bodies' curves are foreign, the joins, rhythm and dot placement
come from the script.

**Policy** (docs/research/gesture-corpus/calligraphy-arabic.md "Adopted
policy"; gesture/calligraphy.py). Syntax may be MEASURED on any sheet,
including measure-only material (Bulaq print, album pages), but a
`SyntaxModel` used for generation must be fitted only on sheets that pass
`calligraphy.require_generative`. `SyntaxModel.fit(..., generative=True)`
enforces that; the measure-only contrast uses `generative=False` and such a
model refuses to `sample_line`. Nothing here ever copies a stroke, contour
or letter shape from a calligraphy sheet into the output.

Measurement pipeline (`measure_mask`):
  1. pen width w = 2 × median distance-transform on the mask skeleton;
  2. baseline angle = the rotation (|a| ≤ 60°) that makes the ink's
     projection profile peakiest (Σh² / (Σh)²);
  3. connected components, classified by size in w: dot (area ≤ 2.6 w²,
     extent ≤ 2.4 w), mark (small, not dot-like: area ≤ 9 w²), body;
  4. text lines = peaks of the body-ink row profile (rotated frame), with
     the line spacing from the profile's autocorrelation; each body's own
     baseline is its densest row, and it joins the nearest line;
  5. per body: width, rise above / drop below its own baseline, offset of
     its baseline from the line's, ascender peaks of the column-top profile
     (relative x and height), gap to the next body leftward (negative =
     overlap); per dot/mark: nearest body, relative x within the body
     (0 = right edge, writing starts there), vertical offset from the body
     baseline, group size.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi
from scipy.signal import find_peaks

# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------

DOT_AREA_W2 = 2.6
MAX_WIDTH_W = 26.0
MAX_OFFSET_W = 5.0
MAX_RISE_W = 11.0
MAX_DROP_W = 7.0
FILL_GAP_W = 9.0
DOT_EXTENT_W = 2.4
MARK_AREA_W2 = 9.0
NOISE_AREA_W2 = 0.2


def pen_width(mask: np.ndarray) -> float:
    """Full pen width in px: 2 × median EDT at skeleton pixels."""
    from skimage.morphology import skeletonize

    m = np.asarray(mask, bool)
    if not m.any():
        return float("nan")
    edt = ndi.distance_transform_edt(m)
    sk = skeletonize(m)
    v = edt[sk]
    return float(2.0 * np.median(v)) if v.size else float("nan")


def _rot(xy: np.ndarray, a_deg: float) -> np.ndarray:
    """Rotate points by −a (so a line at page angle a becomes horizontal).
    Page angle a: counter-clockwise from rightward as the sheet is SEEN
    (image y points down)."""
    a = np.deg2rad(a_deg)
    c, s = np.cos(a), np.sin(a)
    x, y = xy[:, 0], xy[:, 1]
    # seen-CCW by a in y-down coords is (x, y) → (x c − y s·(−1)...) ; derive:
    # a direction (cos a, −sin a) in image coords must map to (1, 0).
    return np.column_stack([x * c - y * s, x * s + y * c])


def baseline_angle(mask: np.ndarray, w: float, *, span: float = 60.0, step: float = 1.0,
                   max_pts: int = 120_000, seed: int = 0) -> float:
    """Page angle (deg, seen CCW from rightward) of the writing lines: the
    rotation that makes the row projection profile peakiest."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return 0.0
    xy = np.column_stack([xs, ys]).astype(float)
    if len(xy) > max_pts:
        xy = xy[np.random.default_rng(seed).choice(len(xy), max_pts, replace=False)]
    best, best_a = -1.0, 0.0
    b = max(w, 1.0)
    for a in np.arange(-span, span + 1e-9, step):
        y = _rot(xy, a)[:, 1]
        h, _ = np.histogram(y, bins=np.arange(y.min(), y.max() + b, b))
        sc = float((h.astype(float) ** 2).sum() / max(h.sum(), 1) ** 2)
        if sc > best:
            best, best_a = sc, float(a)
    return best_a


@dataclass
class Comp:
    idx: int
    kind: str                 # body | dot | mark
    xy: np.ndarray            # pixel coords in the ROTATED frame (x right, y down)
    area: float
    line: int = -1
    body: int = -1            # for dot/mark: nearest body idx


def _components(mask: np.ndarray, w: float, angle: float) -> list[Comp]:
    lab, n = ndi.label(mask, structure=np.ones((3, 3), bool))
    out = []
    if n == 0:
        return out
    objs = ndi.find_objects(lab)
    for i, sl in enumerate(objs, start=1):
        sub = lab[sl] == i
        area = float(sub.sum())
        if area < NOISE_AREA_W2 * w * w:
            continue
        ys, xs = np.nonzero(sub)
        xy = np.column_stack([xs + sl[1].start, ys + sl[0].start]).astype(float)
        r = _rot(xy, angle)
        ext = r.max(axis=0) - r.min(axis=0) + 1
        if area <= DOT_AREA_W2 * w * w and ext.max() <= DOT_EXTENT_W * w:
            kind = "dot"
        elif area <= MARK_AREA_W2 * w * w and ext.max() <= 4.5 * w:
            kind = "mark"
        else:
            kind = "body"
        out.append(Comp(i, kind, r, area))
    return out


def _densest_row(y: np.ndarray, w: float) -> float:
    b = max(w / 2, 1.0)
    h, e = np.histogram(y, bins=np.arange(y.min() - b, y.max() + 2 * b, b))
    h = ndi.gaussian_filter1d(h.astype(float), 1.0)
    k = int(np.argmax(h))
    return float(0.5 * (e[k] + e[k + 1]))


def _line_peaks(bodies: list[Comp], w: float) -> np.ndarray:
    if not bodies:
        return np.zeros(0)
    y = np.concatenate([c.xy[:, 1] for c in bodies])
    pad = int(6 * w) + 4                  # so first/last lines are interior peaks
    y0 = y.min() - pad
    h = np.bincount(np.round(y - y0).astype(int), minlength=int(y.max() - y0) + pad + 1).astype(float)
    hs = ndi.gaussian_filter1d(h, max(w, 1.0))
    # line spacing from the autocorrelation of the profile
    z = hs - hs.mean()
    ac = np.correlate(z, z, mode="full")[len(z) - 1:]
    lo = int(4 * w)
    sp = None
    if len(ac) > lo + 3:
        pk, _ = find_peaks(ac[lo:])
        pk = pk[ac[lo:][pk] > 0]
        if len(pk):
            v = ac[lo:][pk]
            sp = float(pk[np.nonzero(v >= 0.5 * v.max())[0][0]] + lo)   # first strong period
    if sp is None:
        sp = 12 * w
    hs2 = ndi.gaussian_filter1d(h, max(0.12 * sp, w))
    pk, _ = find_peaks(hs2, distance=max(int(0.55 * sp), 2), prominence=0.08 * hs2.max())
    return pk.astype(float) + y0


def measure_mask(mask: np.ndarray, *, source: str = "", genre: str = "", w: float | None = None,
                 angle: float | None = None) -> dict:
    """Syntax record of one ink mask (see module docstring). All lengths
    in w units; 'x' increases to the LEFT inside bodies' relative coords
    (rx = 0 at the body's right edge), since the writing runs right→left."""
    m = np.asarray(mask, bool)
    w = float(w if w is not None else pen_width(m))
    a = float(angle if angle is not None else baseline_angle(m, w))
    comps = _components(m, w, a)
    bodies = [c for c in comps if c.kind == "body"]
    small = [c for c in comps if c.kind != "body"]
    peaks = _line_peaks(bodies, w)
    # per-body own baseline and line assignment
    binfo = []
    for c in bodies:
        base = _densest_row(c.xy[:, 1], w)
        li = int(np.argmin(np.abs(peaks - base))) if len(peaks) else 0
        c.line = li
        binfo.append(base)
    # dots/marks → nearest body (by nearest ink pixel, subsampled)
    if bodies and small:
        from scipy.spatial import cKDTree
        pts, owner = [], []
        for j, c in enumerate(bodies):
            p = c.xy[:: max(1, len(c.xy) // 400)]
            pts.append(p)
            owner.append(np.full(len(p), j))
        tree = cKDTree(np.vstack(pts))
        owner = np.concatenate(owner)
        for c in small:
            d, k = tree.query(c.xy.mean(axis=0))
            c.body = int(owner[k])
            c.line = bodies[c.body].line
    lines = []
    for li in range(len(peaks)):
        bl = [(j, c) for j, c in enumerate(bodies) if c.line == li]
        if not bl:
            continue
        bl.sort(key=lambda t: -t[1].xy[:, 0].max())          # right → left
        recs = []
        for k, (j, c) in enumerate(bl):
            x, y = c.xy[:, 0], c.xy[:, 1]
            base = binfo[j]
            xr, xl = x.max(), x.min()
            wid = (xr - xl + 1) / w
            # column-top profile (height above own baseline), right → left
            cols = np.round(xr - x).astype(int)
            top = np.full(cols.max() + 1, np.nan)
            np.fmin.at(top, cols, y)
            top = np.where(np.isnan(top), base, top)
            hgt = (base - top) / w
            hs = ndi.gaussian_filter1d(hgt, max(w / 3, 0.7))
            band = max(1.2, float(np.median(np.clip(hs, 0, None))))
            thr = max(3.2, 2.0 * band)
            pk, _ = find_peaks(hs, height=thr, distance=max(int(1.4 * w), 1), prominence=1.4)
            r_ = max(int(w), 1)                       # height from the raw profile near the peak
            asc = [(float(p * 1.0 / max(len(hs) - 1, 1)), float(hgt[max(p - r_, 0):p + r_ + 1].max()))
                   for p in pk]
            dots = []
            for c2 in small:
                if c2.body != j:
                    continue
                q = c2.xy.mean(axis=0)
                dots.append({"kind": c2.kind, "rx": float((xr - q[0]) / max(xr - xl, 1.0)),
                             "dy": float((q[1] - base) / w),
                             "size": float(np.sqrt(c2.area) / w)})
            recs.append({
                "width": float(wid), "rise": float((base - y.min()) / w), "drop": float((y.max() - base) / w),
                "offset": float((base - peaks[li]) / w), "area": float(c.area / (w * w)),
                "band": float(band), "asc": asc, "dots": _group_dots(dots),
                "xr": float(xr / w), "xl": float(xl / w),
            })
        for k in range(len(recs)):
            recs[k]["gap"] = float(recs[k]["xl"] - recs[k + 1]["xr"]) if k + 1 < len(recs) else None
        xs = np.array([0.5 * (r["xr"] + r["xl"]) for r in recs])
        offs = np.array([r["offset"] for r in recs])
        slope = float(np.polyfit(-xs, offs, 1)[0]) if len(recs) >= 3 else 0.0
        lines.append({"y": float(peaks[li] / w), "bodies": recs, "slope": slope,
                      "length": float((recs[0]["xr"] - recs[-1]["xl"]))})
    return {"source": source, "genre": genre, "w_px": w, "angle": a, "n_bodies": len(bodies),
            "n_dots": sum(c.kind == "dot" for c in small), "n_marks": sum(c.kind == "mark" for c in small),
            "lines": lines, "coverage": float(m.mean())}


def _group_dots(dots: list[dict], tol: float = 1.9) -> list[dict]:
    """Merge dots lying within tol·w of each other into groups (count)."""
    out = []
    used = [False] * len(dots)
    for i, d in enumerate(dots):
        if used[i]:
            continue
        grp = [d]
        used[i] = True
        if d["kind"] == "dot":
            for j in range(i + 1, len(dots)):
                e = dots[j]
                if used[j] or e["kind"] != "dot":
                    continue
                if abs(e["dy"] - d["dy"]) < tol and any(abs(e["dy"] - g["dy"]) < tol for g in grp):
                    # rx is relative; tolerance needs absolute: rely on dy + small rx diff
                    if abs(e["rx"] - d["rx"]) < 0.25:
                        grp.append(e)
                        used[j] = True
        out.append({"kind": d["kind"], "rx": float(np.mean([g["rx"] for g in grp])),
                    "dy": float(np.mean([g["dy"] for g in grp])), "size": float(np.mean([g["size"] for g in grp])),
                    "count": len(grp)})
    return out


def summarize(rec: dict | list[dict]) -> dict:
    """Genre-level numbers from one or more sheet records."""
    recs = rec if isinstance(rec, list) else [rec]
    B = [b for r in recs for ln in r["lines"] for b in ln["bodies"]]
    L = [ln for r in recs for ln in r["lines"] if len(ln["bodies"]) >= 3]
    if not B:
        return {}
    gaps = np.array([b["gap"] for b in B if b["gap"] is not None])
    nd = np.array([sum(d["count"] for d in b["dots"] if d["kind"] == "dot") for b in B])
    nm = np.array([sum(1 for d in b["dots"] if d["kind"] == "mark") for b in B])
    dys = np.array([d["dy"] for b in B for d in b["dots"] if d["kind"] == "dot"])
    na = np.array([len(b["asc"]) for b in B])
    widths = np.array([b["width"] for b in B])
    offs = np.array([b["offset"] for b in B])
    # within-line rhythm: lag-1 autocorrelation of body widths
    ac = []
    for ln in L:
        x = np.array([b["width"] for b in ln["bodies"]])
        if len(x) >= 4 and x.std() > 0:
            ac.append(np.corrcoef(x[:-1], x[1:])[0, 1])
    return {
        "sheets": len(recs), "lines": len(L), "bodies": len(B),
        "w_px": float(np.median([r["w_px"] for r in recs])),
        "width_med": float(np.median(widths)), "width_p90": float(np.percentile(widths, 90)),
        "rise_med": float(np.median([b["rise"] for b in B])), "drop_med": float(np.median([b["drop"] for b in B])),
        "gap_med": float(np.median(gaps)) if len(gaps) else float("nan"),
        "overlap_frac": float(np.mean(gaps < 0)) if len(gaps) else float("nan"),
        "asc_per_body": float(na.mean()), "asc_per_10w": float(na.sum() / max(widths.sum(), 1) * 10),
        "dots_per_body": float(nd.mean()), "marks_per_body": float(nm.mean()),
        "dot_above_frac": float(np.mean(dys < 0)) if len(dys) else float("nan"),
        "offset_sd": float(np.std(offs)),
        "slope_med": float(np.median([ln["slope"] for ln in L])) if L else float("nan"),
        "bodies_per_line": float(np.median([len(ln["bodies"]) for ln in L])) if L else float("nan"),
        "width_ac1": float(np.mean(ac)) if ac else float("nan"),
        "coverage": float(np.mean([r["coverage"] for r in recs])),
    }


# Sheets the manifest gate lets through but that the lead ruled measure-only
# (2026-10-16): wc-30 (1787 treaty) opens with a devotional invocation, and
# devotional text is measure-only, so it feeds no statistic that generation
# samples from. Keep in the measurement tables only.
EXCLUDE_GENERATIVE = frozenset({"wc-30"})


def generative_ok(source: str, manifest: dict | None = None) -> bool:
    """Manifest gate AND the local exclusions."""
    from .calligraphy import PolicyError, require_generative
    if source.split("#")[0] in EXCLUDE_GENERATIVE:
        return False
    try:
        require_generative([source], manifest)
    except PolicyError:
        return False
    return True


# ---------------------------------------------------------------------------
# the model: slot sequences (block bootstrap over measured lines)
# ---------------------------------------------------------------------------

@dataclass
class SyntaxModel:
    """A bank of measured lines as slot sequences. `generative` records
    whether every source passed the policy gate; only generative models may
    sample lines that drive output."""
    lines: list[list[dict]]
    genre: str = ""
    sources: list[str] = field(default_factory=list)
    generative: bool = False
    line_spacing: float = 12.0          # in w
    slope: float = 0.0

    @staticmethod
    def fit(records: list[dict], *, generative: bool, genre: str = "", min_bodies: int = 3,
            manifest: dict | None = None) -> "SyntaxModel":
        srcs = [r["source"] for r in records]
        if generative:
            from .calligraphy import PolicyError, require_generative
            bad = [x for x in srcs if x.split("#")[0] in EXCLUDE_GENERATIVE]
            if bad:
                raise PolicyError(f"measure-only (devotional) material in a generative model: {bad}")
            require_generative(srcs, manifest)
        lines, sp, sl = [], [], []
        for r in records:
            ys = sorted(ln["y"] for ln in r["lines"])
            spr = float(np.median(np.diff(ys))) if len(ys) >= 2 else 14.0
            sp.append(spr)
            lim = max(0.45 * spr, 4.0)      # bodies further off the line were mis-assigned
            for ln in r["lines"]:
                bs = [b for b in ln["bodies"] if abs(b["offset"]) <= lim]
                if len(bs) >= min_bodies:
                    lines.append([_slot(b) for b in bs])
                    sl.append(ln["slope"])
        if not lines:
            raise ValueError("no usable lines")
        return SyntaxModel(lines, genre, srcs, generative,
                           float(np.median(sp)) if sp else 12.0, float(np.median(sl)) if sl else 0.0)

    def sample_line(self, rng: np.random.Generator, length_w: float, *, block: int = 3) -> list[dict]:
        """Slots until the line is `length_w` long: blocks of `block`
        consecutive bodies from random measured lines (keeps the rhythm of
        neighbours: size alternation, gap/overlap runs, stepping)."""
        if not self.generative:
            from .calligraphy import PolicyError
            raise PolicyError("measure-only syntax model cannot drive generation")
        out, tot = [], 0.0
        while tot < length_w:
            ln = self.lines[int(rng.integers(len(self.lines)))]
            k = int(rng.integers(max(len(ln) - block + 1, 1)))
            for s in ln[k:k + block]:
                out.append(dict(s))
                tot += s["width"] + max(s["gap"] if s["gap"] is not None else 2.0, -0.6 * s["width"])
                if tot >= length_w:
                    break
        # re-centre offsets so each sampled line stays on its own baseline
        off = np.array([s["offset"] for s in out])
        for s, o in zip(out, off - np.median(off)):
            s["offset"] = float(o)
        return out


def _slot(b: dict) -> dict:
    return {k: b[k] for k in ("width", "rise", "drop", "offset", "band", "asc", "dots", "gap")}


# ---------------------------------------------------------------------------
# foreign fragments
# ---------------------------------------------------------------------------

@dataclass
class Fragment:
    pts: np.ndarray        # normalised: chord from (0,0) to (1,0) if open-ish; bulge to −y (up)
    bulge: float           # max height above the chord, in chord units
    depth: float           # max depth below the chord
    source: str = ""


def _normalise_fragment(p: np.ndarray) -> Fragment | None:
    a, b = p[0], p[-1]
    ch = b - a
    c = float(np.hypot(*ch))
    L = float(np.sum(np.hypot(*np.diff(p, axis=0).T)))
    if c < 0.15 * L or L <= 0:
        return None                      # loops: chord too short to orient
    u = ch / c
    n = np.array([u[1], -u[0]])          # left normal in y-down coords = "up" if chord points right
    q = p - a
    x = q @ u / c
    y = q @ n / c                        # positive = up
    if (y.clip(min=0).max()) < (-y).clip(min=0).max():
        y = -y                           # flip so the main bulge is up
    pts = np.column_stack([x, -y])       # y-down storage: up = negative
    return Fragment(pts, float(y.max()), float(max(-y.min(), 0.0)))


def fragment_bank(drawings, rng: np.random.Generator, *, n: int = 1500, len_frac=(0.03, 0.12),
                  step_frac: float = 0.004) -> list[Fragment]:
    """Cut n windows from the strokes of `drawings` (any corpus; NOT
    calligraphy), arc length a random fraction of each drawing's reference
    length, lightly smoothed, normalised by chord."""
    from .curvature import resample, smooth

    pool = []
    for d in drawings:
        R = d.ref_length()
        for st in d.strokes:
            if st.length() > len_frac[0] * R * 1.2 and len(st) >= 4:
                pool.append((d, st, R))
    if not pool:
        return []
    Ls = np.array([st.length() for _, st, _ in pool])
    pr = Ls / Ls.sum()
    out, tries = [], 0
    while len(out) < n and tries < n * 20:
        tries += 1
        d, st, R = pool[int(rng.choice(len(pool), p=pr))]
        step = step_frac * R
        p = resample(st.points, step)
        if len(p) < 8:
            continue
        p = smooth(p, 1.5 * step, step)
        Lw = rng.uniform(*len_frac) * R
        k = int(Lw / step)
        if k < 6 or k >= len(p):
            continue
        i0 = int(rng.integers(0, len(p) - k))
        f = _normalise_fragment(p[i0:i0 + k + 1])
        if f is not None and f.bulge > 0.04:
            f.source = d.source
            out.append(f)
    return out


def _pick(bank: list[Fragment], rng, aspect: float, k: int = 24, down: bool = False) -> Fragment:
    """A fragment whose bulge/chord is near `aspect` (best of k random)."""
    idx = rng.integers(len(bank), size=k)
    bul = np.array([bank[i].bulge for i in idx])
    j = idx[int(np.argmin(np.abs(np.log(bul + 1e-3) - np.log(aspect))))]
    return bank[int(j)]


# ---------------------------------------------------------------------------
# assembly: slots → marks
# ---------------------------------------------------------------------------

@dataclass
class Piece:
    """One placed element. kind: arch (foreign fragment), conn (script join
    along the baseline), dot (filled), mark (small foreign tick). `body`
    groups pieces of one body; contiguous bodies are drawn as one path."""
    kind: str
    pts: np.ndarray
    body: int
    filled: bool = False


def _place(f: Fragment, x0: float, base: float, chord: float, up: bool) -> np.ndarray:
    p = f.pts * chord
    if not up:
        p = p * np.array([1, -1])
    # writing runs right → left: start at x0 and go left
    return np.column_stack([x0 - p[:, 0], base + p[:, 1]])


def _blob(c: np.ndarray, r: float, rng, n: int = 14) -> np.ndarray:
    """A small irregular filled lozenge-ish blob (not a rhombus template:
    radius noise per vertex, random squash and angle)."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    rr = r * (1 + 0.18 * rng.standard_normal(n))
    sq = rng.uniform(0.55, 1.0)
    a = rng.uniform(0, np.pi)
    x, y = rr * np.cos(t), rr * sq * np.sin(t)
    ca, sa = np.cos(a), np.sin(a)
    return np.column_stack([c[0] + ca * x - sa * y, c[1] + sa * x + ca * y])


def assemble_line(slots: list[dict], bank: list[Fragment], rng: np.random.Generator, *,
                  x_right: float, base: float, w: float, slope: float = 0.0,
                  tick_bank: list[Fragment] | None = None) -> list[Piece]:
    """Lay slots right → left from x_right on baseline y=`base` (px), unit
    w px. Each body: baseline connectors (sagging slightly) between arches;
    one arch per measured ascender (height from the slot), a drop arch
    (bowl/tail below) if the slot drops ≥ 1.8 w, otherwise a low arch so
    every body carries at least one foreign gesture. Dots and marks at the
    measured relative positions."""
    pieces: list[Piece] = []
    x = x_right
    for bi, s in enumerate(slots):
        W = float(np.clip(s["width"], 1.5, MAX_WIDTH_W)) * w
        off = float(np.clip(s["offset"], -MAX_OFFSET_W, MAX_OFFSET_W))
        b0 = base + off * w + slope * (x_right - x)
        # events along the body: (rx, kind, height); heights capped (merged
        # components on dense sheets report impossible ascenders)
        ev = [(rx, "up", min(h, MAX_RISE_W)) for rx, h in s["asc"]]
        if not ev:
            ev.append((float(rng.uniform(0.2, 0.8)), "up", float(np.clip(s["rise"], 1.2, MAX_RISE_W))))
        ev.sort()
        # long event-free stretches get a low foreign arch (no bare kashida > FILL_GAP_W)
        filled, prev = [], 0.0
        for e in ev + [(1.0, "end", 0.0)]:
            while (e[0] - prev) * W > FILL_GAP_W * w:
                prev += FILL_GAP_W * w / W * rng.uniform(0.6, 0.9)
                filled.append((prev, "up", float(rng.uniform(0.8, 2.0))))
            if e[1] != "end":
                filled.append(e)
            prev = e[0]
        ev = filled
        cur = x
        for rx, kind, h in ev:
            hh = h * w
            aspect = float(np.clip(rng.uniform(1.2, 3.5) if h > 2.5 else rng.uniform(0.3, 1.0), 0.2, 6))
            f = _pick(bank, rng, aspect)
            chord = float(np.clip(hh / max(f.bulge, 0.05), 0.6 * w, 0.6 * W + w))
            target = x - rx * W + 0.5 * chord          # arch centred at rx
            if target < cur - 0.2 * w:                 # baseline connector up to the arch
                xs = np.linspace(cur, target, max(int((cur - target) / (0.5 * w)) + 2, 2))
                sag = rng.uniform(-0.25, 0.35) * w * np.sin(np.linspace(0, np.pi, len(xs)))
                pieces.append(Piece("conn", np.column_stack([xs, np.full(len(xs), b0) + sag]), bi))
                cur = target
            pieces.append(Piece("arch", _place(f, cur, b0, chord, up=True), bi))
            cur = cur - chord
        end = x - W
        if cur > end + 0.3 * w:
            xs = np.linspace(cur, end, max(int((cur - end) / (0.5 * w)) + 2, 2))
            tail = -rng.uniform(0, 0.6) * w * np.linspace(0, 1, len(xs)) ** 2
            pieces.append(Piece("conn", np.column_stack([xs, np.full(len(xs), b0) + tail]), bi))
            cur = end
        # a drop is a TERMINAL tail, chord tilted 35–70° down-left — not a
        # symmetric bowl (a bowl with a dot over it reads as a letter)
        if s["drop"] >= 1.8:
            dd = min(s["drop"], MAX_DROP_W) * w
            f = _pick(bank, rng, float(rng.uniform(0.15, 0.6)))
            th = np.deg2rad(rng.uniform(35, 70))
            q = f.pts * (dd / np.sin(th))
            if rng.random() < 0.5:
                q = q * np.array([1, -1])
            R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
            q = q @ R.T                                     # chord now points down-right
            q[:, 0] = -q[:, 0]                              # … mirrored to down-left
            pieces.append(Piece("arch", q + [cur, b0], bi))
        left = min(cur, end)
        # dots and marks
        for d in s["dots"]:
            cx = x - d["rx"] * (x - left)
            cy = b0 + d["dy"] * w
            if d["kind"] == "dot":
                k = d["count"]
                offs = {1: [(0, 0)], 2: [(-0.7, 0), (0.7, 0)], 3: [(-0.7, 0.4), (0.7, 0.4), (0, -0.6)]}
                for ox, oy in offs.get(k, [(0, 0)] * k):
                    r = 0.5 * float(np.clip(d["size"], 0.6, 1.6)) * w
                    pieces.append(Piece("dot", _blob(np.array([cx + ox * 1.2 * w, cy + oy * 1.2 * w]), r, rng),
                                        bi, filled=True))
            else:
                tb = tick_bank or bank
                f = tb[int(rng.integers(len(tb)))]
                ch = float(np.clip(d["size"], 1.0, 3.0)) * w
                p = f.pts * ch
                a = rng.uniform(-0.6, 0.6) + (np.pi / 2 if rng.random() < 0.3 else 0)
                R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
                p = (p - p.mean(axis=0)) @ R.T + [cx, cy]
                pieces.append(Piece("mark", p, bi))
        gap = s["gap"] if s["gap"] is not None else 2.0
        x = left - max(gap, -0.6 * s["width"]) * w
    return pieces


def body_paths(pieces: list[Piece]) -> list[np.ndarray]:
    """Contiguous polylines: consecutive arch/conn pieces of one body are
    joined end to start (the join is the script's)."""
    out, cur, cb = [], None, None
    for p in pieces:
        if p.kind not in ("arch", "conn"):
            continue
        if cur is not None and p.body == cb:
            cur = np.vstack([cur, p.pts])
        else:
            if cur is not None:
                out.append(cur)
            cur, cb = p.pts.copy(), p.body
    if cur is not None:
        out.append(cur)
    return out


# ---------------------------------------------------------------------------
# controls: the same pieces, script syntax removed
# ---------------------------------------------------------------------------

def _rand_rot(p: np.ndarray, rng) -> np.ndarray:
    a = rng.uniform(0, 2 * np.pi)
    R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    c = p.mean(axis=0)
    return (p - c) @ R.T


def scatter_control(pieces: list[Piece], band: tuple[float, float, float, float], rng) -> list[Piece]:
    """Every piece (arch, connector, dot, mark — same geometry, same ink
    length) at a uniform random position and rotation inside the band
    (x0, y0, x1, y1). No joins."""
    x0, y0, x1, y1 = band
    out = []
    for i, p in enumerate(pieces):
        q = _rand_rot(p.pts, rng) if p.kind != "dot" else p.pts - p.pts.mean(axis=0)
        c = rng.uniform([x0, y0], [x1, y1])
        out.append(Piece(p.kind, q + c, i, p.filled))
    return out


def chain_control(pieces: list[Piece], band: tuple[float, float, float, float], rng) -> list[Piece]:
    """The same arches and connectors chained end-to-start into contiguous
    runs (as many runs as the syntax line has bodies), each piece at a
    random rotation, runs started at random points in the band and folded
    back inside it; dots/marks scattered uniformly. Contiguity kept, script
    syntax (baseline, rhythm, placement) removed."""
    x0, y0, x1, y1 = band
    lines = [p for p in pieces if p.kind in ("arch", "conn")]
    others = [p for p in pieces if p.kind not in ("arch", "conn")]
    nb = len({p.body for p in lines}) or 1
    order = rng.permutation(len(lines))
    runs = np.array_split(order, nb)
    out = []
    for ri, run in enumerate(runs):
        cur = rng.uniform([x0, y0], [x1, y1])
        for i in run:
            q = _rand_rot(lines[i].pts, rng)
            q = q - q[0] + cur
            # fold back into the band (reflect the piece if it leaves)
            for ax, lo, hi in ((0, x0, x1), (1, y0, y1)):
                if q[:, ax].max() > hi or q[:, ax].min() < lo:
                    q[:, ax] = 2 * cur[ax] - q[:, ax]
            q[:, 0] = np.clip(q[:, 0], x0, x1)
            q[:, 1] = np.clip(q[:, 1], y0, y1)
            out.append(Piece(lines[i].kind, q, 10_000 + ri))
            cur = q[-1]
    for p in others:
        q = p.pts - p.pts.mean(axis=0)
        if p.kind != "dot":
            q = _rand_rot(p.pts, rng)
        out.append(Piece(p.kind, q + rng.uniform([x0, y0], [x1, y1]), -1, p.filled))
    return out


def ink_length(pieces: list[Piece]) -> float:
    return float(sum(np.sum(np.hypot(*np.diff(p.pts, axis=0).T)) for p in pieces if not p.filled))


# ---------------------------------------------------------------------------
# rendering (research raster: ink on warm paper)
# ---------------------------------------------------------------------------

PAPER = (255, 252, 240)
INK = (16, 15, 15)


def render(pieces: list[Piece], size: tuple[int, int], *, pen: float = 2.4, ss: int = 2,
           img=None, color=INK, masses: list[np.ndarray] | None = None):
    """PIL image. Contiguous body paths for syntax pieces (joined), every
    other piece drawn on its own; filled pieces as polygons; `masses`
    (list of exterior rings) filled solid."""
    from PIL import Image, ImageDraw

    W, H = size
    if img is None:
        big = Image.new("RGB", (W * ss, H * ss), PAPER)
    else:
        big = img.resize((W * ss, H * ss))
    dr = ImageDraw.Draw(big)
    lw = max(int(round(pen * ss)), 1)

    def line(p):
        q = [(float(x) * ss, float(y) * ss) for x, y in p]
        if len(q) >= 2:
            dr.line(q, fill=color, width=lw, joint="curve")
            r = lw / 2
            for e in (q[0], q[-1]):
                dr.ellipse([e[0] - r, e[1] - r, e[0] + r, e[1] + r], fill=color)

    joined = body_paths([p for p in pieces if p.body >= 0 and p.body < 10_000]) if pieces else []
    joined_ids = {id(p) for p in pieces if p.kind in ("arch", "conn") and 0 <= p.body < 10_000}
    for p in joined:
        line(p)
    for p in pieces:
        if id(p) in joined_ids:
            continue
        if p.filled:
            dr.polygon([(float(x) * ss, float(y) * ss) for x, y in p.pts], fill=color)
        else:
            line(p.pts)
    for ring in masses or []:
        dr.polygon([(float(x) * ss, float(y) * ss) for x, y in ring], fill=color)
    return big.resize((W, H), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------------------
# limb: siyah mashq — overwriting syntax lines until they become mass
# ---------------------------------------------------------------------------

def mashq_measure(mask: np.ndarray, w: float, *, tile_w: float = 40.0) -> dict:
    """Overwriting statistics of a practice sheet: global coverage, the
    distribution of local coverage in tiles of tile_w × w, and the fraction
    of tiles past 0.5 coverage (where lines have become mass)."""
    m = np.asarray(mask, bool)
    t = max(int(tile_w * w), 8)
    H, W = m.shape
    cov = [m[i:i + t, j:j + t].mean() for i in range(0, H - t + 1, t) for j in range(0, W - t + 1, t)]
    cov = np.array(cov) if cov else np.array([m.mean()])
    return {"coverage": float(m.mean()), "tile_p50": float(np.median(cov)), "tile_p90": float(np.percentile(cov, 90)),
            "tile_max": float(cov.max()), "frac_tiles_gt_0.35": float(np.mean(cov > 0.35))}


def density_masses(pieces: list[Piece], size: tuple[int, int], *, pen: float, sigma: float,
                   thresh: float, min_area: float) -> list[np.ndarray]:
    """Where overwritten ink is dense, the lines become mass: rasterise the
    pieces at 1 px, blur by sigma, threshold, return exterior rings
    (marching squares) of regions ≥ min_area px²."""
    from PIL import Image, ImageDraw
    from skimage import measure

    W, H = size
    im = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(im)
    for p in pieces:
        q = [(float(x), float(y)) for x, y in p.pts]
        if p.filled:
            dr.polygon(q, fill=255)
        elif len(q) >= 2:
            dr.line(q, fill=255, width=max(int(round(pen)), 1))
    a = np.asarray(im, float) / 255.0
    d = ndi.gaussian_filter(a, sigma)
    out = []
    for c in measure.find_contours(np.pad(d, 1), thresh):
        c = c[:, ::-1] - 1
        x, y = c[:, 0], c[:, 1]
        area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        if area >= min_area:
            out.append(c)
    return out
