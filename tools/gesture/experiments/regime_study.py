"""Regime metamorphosis study (results/regime-2026-10-16.md).

Stages:
  fit        width profiles from data: calligraphy strokes (broadnib widths)
             and Ian's reference image (extract_hybrid, calligraphy settings)
  catalogue  sheet (a): every transition operator on simple strokes
  grammar    sheet (b): grammar-v6 lines (Matisse / Hokusai) under rising and
             falling r(s) profiles
  tree       sheet (c): oehlen_tree with r following depth
  cost       pen-length cost per regime (table)

Run from tools/gesture:
  ../../.local/gesture/.venv/bin/python -m experiments.regime_study <stage> [...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d

from gesture import regime as rg

REPO = Path(__file__).resolve().parents[3]
OUTROOT = REPO / ".local/gesture/out"
OUT = OUTROOT / "regime"
RESULTS = Path(__file__).resolve().parents[1] / "results"
REF = REPO / ".local/gesture/ref/ian-regimes-sd-2024.png"
PEN = 0.35                      # mm
PXMM = 8.0                      # preview raster px per mm


# ---------------------------------------------------------------------------
# drawing helpers
# ---------------------------------------------------------------------------

def draw(paths, box, *, pxmm=PXMM, pen=PEN, img=None, offset=(0, 0), color=0):
    """Draw plotter paths (mm) with a round pen into a PIL image."""
    from PIL import Image, ImageDraw
    x0, y0, x1, y1 = box
    if img is None:
        img = Image.new("L", (int((x1 - x0) * pxmm), int((y1 - y0) * pxmm)), 255)
    dr = ImageDraw.Draw(img)
    lw = max(int(round(pen * pxmm)), 1)
    rad = pen * pxmm / 2
    for p in paths:
        q = (np.asarray(p) - [x0, y0]) * pxmm + offset
        if len(q) >= 2:
            dr.line([tuple(v) for v in q], fill=color, width=lw, joint="curve")
        for v in (q[0], q[-1]):
            dr.ellipse([v[0] - rad, v[1] - rad, v[0] + rad, v[1] + rad], fill=color)
    return img


def label(img, xy, text, size=14):
    from PIL import ImageDraw, ImageFont
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except OSError:
        f = ImageFont.load_default()
    ImageDraw.Draw(img).text(xy, text, fill=90, font=f)


def save_jpg(img, path: Path, max_kb: int = 600):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = img.convert("L")
    for q in (88, 82, 75, 68, 60, 50, 40):
        img.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024:
            return
    w, h = img.size
    img.resize((int(w * 0.8), int(h * 0.8))).save(path, quality=60, optimize=True)


def _wave(L=50.0, amp=4.0, n=400, per=30.0, start=(0, 0)):
    x = np.linspace(0, L, n)
    return np.column_stack([x, amp * np.sin(2 * np.pi * x / per)]) + start


# ---------------------------------------------------------------------------
# stage: fit (data-derived width profiles)
# ---------------------------------------------------------------------------

def _profile_stats(strokes, w_unit: float, *, min_len_w=8.0, sigma_w=0.75) -> dict:
    """Width profiles along strokes (widths in units of w_unit):
    ramp: arc length (in units of the stroke's thick width) over which the
    width climbs from 25 % to 75 % of the way between its thin (q10) and thick
    (q90) levels, for strokes with contrast q90/q10 ≥ 1.6;
    end ratio: terminal width (first/last 1 w, max) over the interior median;
    rate: max |dw/ds| (dimensionless)."""
    ramps, ramp_rel, ends, rates, contrasts, thick = [], [], [], [], [], []
    for st in strokes:
        if st.width is None or len(st) < 8:
            continue
        p = st.points
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
        w = st.width / w_unit
        wm = float(np.median(w))
        if s[-1] < min_len_w * wm * w_unit:
            continue
        step = 0.25 * wm * w_unit
        t = np.arange(0, s[-1], step)
        if len(t) < 12:
            continue
        ww = gaussian_filter1d(np.interp(t, s, w), sigma_w * wm * w_unit / step, mode="nearest")
        lo, hi = np.quantile(ww, 0.1), np.quantile(ww, 0.9)
        contrasts.append(hi / max(lo, 1e-9))
        thick.append(hi)
        dw = np.gradient(ww, step / w_unit)
        rates.append(float(np.max(np.abs(dw))))
        k = max(int(round(1.0 * wm * w_unit / step)), 1)
        inner = float(np.median(ww[k:-k])) if len(ww) > 2 * k + 2 else wm
        ends.append(max(ww[:k].max(), ww[-k:].max()) / max(inner, 1e-9))
        if hi / max(lo, 1e-9) < 1.6:
            continue
        a, b = lo + 0.25 * (hi - lo), lo + 0.75 * (hi - lo)
        # upward and downward passages a ↔ b (each read in the rising direction)
        for seq in (ww, ww[::-1]):
            i = 0
            while i < len(seq):
                if seq[i] <= a:
                    j = i
                    while j < len(seq) and seq[j] < b:
                        if seq[j] <= a:
                            i = j
                        j += 1
                    if j < len(seq):
                        L = (j - i) * step / w_unit
                        ramps.append(L / hi)
                        ramp_rel.append(L)
                    i = j + 1
                else:
                    i += 1
    q = lambda v, qq: float(np.quantile(v, qq)) if len(v) else float("nan")
    return {"n_strokes": len(contrasts), "n_ramps": len(ramps),
            "ramp_thick_q": [q(ramps, x) for x in (0.25, 0.5, 0.75)],
            "contrast_q": [q(contrasts, x) for x in (0.25, 0.5, 0.75, 0.9)],
            "end_ratio_q": [q(ends, x) for x in (0.1, 0.25, 0.5, 0.75, 0.9)],
            "bulb_share": float(np.mean(np.array(ends) > 1.3)) if ends else float("nan"),
            "taper_share": float(np.mean(np.array(ends) < 0.75)) if ends else float("nan"),
            "rate_q": [q(rates, x) for x in (0.5, 0.9)],
            "_ramps": ramps}


def stage_fit():
    from gesture.core import Drawing
    from gesture import calligraphy as cg
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    # (1) calligraphy: generative-allowed shikasta sheets drive the defaults;
    #     the other genres are measured for comparison only (policy)
    ext = OUTROOT / "calligraphy/extract"
    groups = {"shikasta_gen": [ext / "shikasta" / f"{k}.json" for k in ("wc-12", "wc-13", "wc-15")],
              "nastaliq": sorted((ext / "nastaliq").glob("*[!e].json")),
              "baghdadi": sorted((ext / "baghdadi").glob("*[!e].json"))}
    for name, files in groups.items():
        sts, n = [], 0
        for f in files:
            if not f.exists() or f.name.endswith(".outline.json"):
                continue
            d = cg.pen_strokes(Drawing.load(f))
            wm = float(np.median([np.median(s.width) for s in d.strokes])) if d.strokes else 1.0
            sts += [(s, wm) for s in d.strokes]
            n += 1
        # each sheet in its own median width
        by = {}
        for s, wm in sts:
            by.setdefault(wm, []).append(s)
        allr = {}
        parts = [_profile_stats(v, k) for k, v in by.items()]
        ramps = sum((p["_ramps"] for p in parts), [])
        merged = _profile_stats([s for v in by.values() for s in v], 1.0)  # end ratios etc (unit-free)
        merged["ramp_thick_q"] = [float(np.quantile(ramps, x)) if ramps else float("nan") for x in (0.25, .5, .75)]
        merged["n_ramps"] = len(ramps)
        merged["sheets"] = n
        merged.pop("_ramps")
        res[name] = merged
        print(name, json.dumps(merged))
    # (2) Ian's reference image
    res["reference"] = fit_reference()
    (OUT / "fit.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["reference"], indent=1))


def fit_reference(save_overlay: bool = True) -> dict:
    """Extract the reference with the calligraphy settings (black ink mode),
    then measure: width distribution (thin vs thick), thin→thick ramps,
    terminal bulbs, masses (inradius ≫ thin line) and what attaches to them."""
    from PIL import Image
    from scipy import ndimage as ndi
    from gesture import calligraphy as cg
    from gesture import extract_hybrid
    rgb = np.asarray(Image.open(REF).convert("RGB"), dtype=np.float64) / 255.0
    g = cg.to_gray(rgb, "black")
    kw = dict(cg.EXTRACT_DEFAULTS)
    d = extract_hybrid.extract(g, scale=1.0, source="ref", **kw)
    mask, w0 = cg.ink_mask(g, **cg.EXTRACT_DEFAULTS)
    edt = ndi.distance_transform_edt(mask)
    ws = np.concatenate([s.width for s in d.strokes if s.width is not None])
    Ls = np.array([s.length() for s in d.strokes])
    wmed = np.array([np.median(s.width) for s in d.strokes])
    # thin line width: length-weighted q25 of stroke median widths
    o = np.argsort(wmed)
    c = np.cumsum(Ls[o]) / Ls.sum()
    w_thin = float(wmed[o][np.searchsorted(c, 0.25)])
    w_q = {k: float(wmed[o][np.searchsorted(c, k)]) for k in (0.1, 0.25, 0.5, 0.75, 0.9)}
    thick = [s for s, w in zip(d.strokes, wmed) if w > 2.0 * w_thin]
    prof = _profile_stats(d.strokes, w_thin)
    prof.pop("_ramps")
    # masses: connected regions where the ink is deeper than 3 thin widths
    deep = edt > 1.5 * w_thin * 2.0     # inradius > 3 w_thin  → diameter > 6 w_thin
    lab, nlab = ndi.label(deep)
    masses = []
    sk_attach = []
    from skimage.morphology import skeletonize
    for k in range(1, nlab + 1):
        reg = lab == k
        area = int(reg.sum())
        if area < 20:
            continue
        ys, xs = np.nonzero(reg)
        inr = float(edt[reg].max())
        # the full ink blob of this mass = deep core dilated by its own inradius
        core = ndi.binary_dilation(reg, iterations=int(np.ceil(inr)) + 1) & mask
        ring = ndi.binary_dilation(core, iterations=int(max(2, 1.5 * w_thin))) & mask & ~core
        rl, nr = ndi.label(ring)
        # count line exits: ring components that are thin
        exits = 0
        for j in range(1, nr + 1):
            if (rl == j).sum() > 3:
                exits += 1
        masses.append({"diam_thin": 2 * inr / w_thin, "area_thin2": float(core.sum()) / w_thin ** 2,
                       "elong": float(np.sqrt(max(np.linalg.eigvalsh(np.cov(np.vstack([xs, ys])))) /
                                              max(min(np.linalg.eigvalsh(np.cov(np.vstack([xs, ys])) + 1e-9)), 1e-9)))
                       if area > 3 else 1.0, "exits": exits})
    diam = [m["diam_thin"] for m in masses]
    exits = [m["exits"] for m in masses]
    out = {"strokes": len(d.strokes), "w_thin_px": w_thin, "w_median_q_px": w_q,
           "thick_share_len": float(sum(s.length() for s in thick) / max(Ls.sum(), 1e-9)),
           "thick_over_thin_q": [float(np.quantile(wmed[wmed > 2 * w_thin] / w_thin, x)) if (wmed > 2 * w_thin).any()
                                 else float("nan") for x in (0.25, 0.5, 0.75, 0.9)],
           "profile": prof,
           "masses": {"n": len(masses),
                      "diam_thin_q": [float(np.quantile(diam, x)) for x in (0.25, 0.5, 0.75, 0.9)] if diam else [],
                      "exits_hist": {str(k): int(np.sum(np.array(exits) == k)) for k in range(0, 6)},
                      "exits_ge3_share": float(np.mean(np.array(exits) >= 3)) if exits else float("nan")}}
    if save_overlay:
        from PIL import Image, ImageDraw
        im = Image.fromarray((np.clip(g, 0, 1) * 255).astype(np.uint8)).convert("RGB")
        dr = ImageDraw.Draw(im)
        for s, w in zip(d.strokes, wmed):
            col = (220, 40, 40) if w > 2 * w_thin else (40, 120, 220)
            dr.line([tuple(v) for v in s.points], fill=col, width=2)
        im.save(OUT / "ref_overlay.jpg", quality=80)
        Drawing_save = getattr(d, "save")
        Drawing_save(OUT / "ref_extract.json")
    return out


# ---------------------------------------------------------------------------
# sheet (a): catalogue of operators
# ---------------------------------------------------------------------------

def catalogue_items(rng):
    W = 2.4
    base = rg.make(_wave(50, 3.0, 400, 45), 0.0, phi=np.deg2rad(50), W=W)
    straight = rg.make(np.column_stack([np.linspace(0, 50, 300), np.zeros(300)]), 0.0,
                       phi=np.deg2rad(50), W=W)
    down = rg.make(np.column_stack([3 * np.sin(np.linspace(0, 2, 300)), np.linspace(0, 45, 300)]), 0.0,
                   phi=np.deg2rad(40), W=W)
    items = []
    # 1. thickening: line → nib → line
    items.append(("thicken: line → nib → line", rg.thicken(base, 0.25, until=0.75)))
    # 2. r ramps all the way 0 → 2 along a wave
    s, L = rg._s_frac(base)
    items.append(("r rises 0 → 1 → 2 along the stroke", rg.replace(base, r=np.clip(2.2 * s / L, 0, 2))))
    # 3. bead on a line
    items.append(("swell: bead on a line", rg.swell(straight, 0.55, length=14, size=6)))
    # 4. bead on a nib stroke
    items.append(("swell: nib swells into a mass and back", rg.swell(rg.thicken(base, 0.1, until=0.9), 0.5,
                                                                     length=22, size=9)))
    # 5. vessel / goblet
    items.append(("swell: vessel (stem flares into a foot)", rg.swell(rg.thicken(down, 0.15, to=0.6), 0.35,
                                                                      kind="vessel", size=8)))
    # 6. closing-and-filling, partial and full
    items.append(("close_fill 0.5: loop thickens, counter shrinks", rg.close_fill(straight, radius=3.5, amount=0.5)))
    items.append(("close_fill 1.0: loop closes into a dot", rg.close_fill(straight, radius=3.0, amount=1.0)))
    # 7. eye
    items.append(("eye: loop spirals in, swells to a pupil", rg.eye(straight, radius=5.0)))
    # 8. terminal lozenge / drop
    items.append(("terminal lozenge (nuqta) after a nib stroke",
                  rg.terminal_drop(rg.thicken(base, 0.15), kind="lozenge", size=3.0)))
    items.append(("terminal drop: line ends in a teardrop", rg.terminal_drop(base, kind="drop", size=4.5)))
    # 9. shedding
    mass = rg.swell(rg.thicken(straight, 0.1, until=0.95), 0.5, length=30, size=10)
    items.append(("shed drips from a mass", rg.shed(mass, rng, n=5, kind="drips", length=14, where=(0.3, 0.7))))
    items.append(("shed hairs: a heavy stroke ends in dry hairs",
                  rg.shed(rg.thicken(base, 0.05, to=1.5), rng, n=6, kind="hairs", length=10)))
    return items


def stage_catalogue():
    from PIL import Image
    rng = np.random.default_rng(7)
    items = catalogue_items(rng)
    cols, cw, ch = 3, 78.0, 62.0
    rows = int(np.ceil(len(items) / cols))
    sheet = Image.new("L", (int(cols * cw * PXMM), int(rows * ch * PXMM)), 255)
    costs = []
    for k, (name, st) in enumerate(items):
        paths = rg.render(st, PEN)
        allp = np.vstack(paths)
        lo, hi = allp.min(0), allp.max(0)
        c = 0.5 * (lo + hi)
        cx, cy = (k % cols) * cw + cw / 2, (k // cols) * ch + ch / 2 + 3
        moved = [p - c + [cx, cy] for p in paths]
        draw(moved, (0, 0, cols * cw, rows * ch), img=sheet)
        label(sheet, ((k % cols) * cw * PXMM + 10, (k // cols) * ch * PXMM + 8), f"{k + 1}. {name}", 15)
        pc = rg.pen_cost(paths)
        costs.append({"item": name, **pc, "regime": rg.regime_cost(st, paths)})
    save_jpg(sheet, RESULTS / "regime-catalogue.jpg")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "catalogue_costs.json").write_text(json.dumps(costs, indent=1))
    for c in costs:
        print(f"{c['item'][:44]:44s} paths {c['paths']:3d}  pen {c['length']:7.1f} mm")


# ---------------------------------------------------------------------------
# sheet (b): grammar-v6 lines with r(s) profiles
# ---------------------------------------------------------------------------

def _grammar(art):
    from gesture import grammar_v6_frozen as gm6
    return gm6.Grammar.load(OUTROOT / "grammar_v6_frozen" / f"grammar_{art}.json")


def _tremor(art):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from experiments import composite
    return composite.tremor_model(art)


def profile_r(s, L, kind, rng):
    """Rising-and-falling r(s) profiles over arc length s (mm)."""
    u = s / max(L, 1e-9)
    if kind == "rise_fall":           # line → nib → line
        c, wdt = rng.uniform(0.35, 0.65), rng.uniform(0.15, 0.3)
        return 1.0 * np.exp(-0.5 * ((u - c) / wdt) ** 2) * 1.1
    if kind == "through_mass":        # line → nib → mass → nib → line
        c = rng.uniform(0.4, 0.6)
        return 2.05 * np.exp(-0.5 * ((u - c) / 0.18) ** 2)
    if kind == "pulses":              # several swellings: beads / pressure pulses
        # round 7: no capsule rhythm — irregular spacing, unequal heights and
        # lengths, and asymmetric pulses (mostly a slow swell and an abrupt
        # end: the ink pools where the pressure lets go)
        k = int(rng.integers(2, 5))
        cs = np.sort(rng.uniform(0.12, 0.88, k))
        out = np.zeros_like(u)
        for c in cs:
            a_, b_ = rng.uniform(0.04, 0.13), rng.uniform(0.012, 0.035)
            if rng.random() < 0.3:
                a_, b_ = b_, a_
            wdt = np.where(u < c, a_, b_)
            out = np.maximum(out, rng.uniform(1.25, 2.0) * np.exp(-0.5 * ((u - c) / wdt) ** 2))
        return 0.6 * np.clip((u - 0.05) / 0.2, 0, 1) * (1 - np.clip((u - 0.8) / 0.2, 0, 1)) + out * (1 - 0.0)
    if kind == "crescendo":           # line → nib → mass at the end (a drop)
        return 2.0 * np.clip((u - 0.2) / 0.8, 0, 1) ** 1.6
    raise ValueError(kind)


def stage_grammar(wet=None, out_name: str = "regime-grammar.jpg"):
    from PIL import Image
    from gesture import tremor as tr
    from gesture import grammar_v6_frozen as gm6
    from gesture.core import Drawing, Stroke
    kinds = ["rise_fall", "through_mass", "pulses", "crescendo"]
    arts = ["matisse", "hokusai"]
    cw, ch = 95.0, 80.0
    sheet = Image.new("L", (int(len(kinds) * cw * PXMM), int(len(arts) * 2 * ch * PXMM)), 255)
    costs = []
    for ai, art in enumerate(arts):
        g = _grammar(art)
        model, mode, _lab = _tremor(art)
        for row in range(2):
            for ki, kind in enumerate(kinds):
                rng = np.random.default_rng([ai, row, ki, 11])
                # one generated line, longest of a few draws, scaled to the cell
                best = None
                for _ in range(6):
                    st = gm6.generate_stroke(g, rng, ref_length=1000.0, step=0.5)
                    if best is None or st.length() > best.length():
                        best = st
                p = best.points
                lo, hi = p.min(0), p.max(0)
                sc = min((cw - 22) / max(hi[0] - lo[0], 1e-9), (ch - 22) / max(hi[1] - lo[1], 1e-9))
                p = (p - 0.5 * (lo + hi)) * sc
                # tremor at the hand's line width (≈ pen) before regimes
                w = PEN
                d = tr.apply_tremor(Drawing([Stroke(p, width=np.full(len(p), w))], size=(1, 1)), model,
                                    rng, 1.0, mode=mode)
                p = d.strokes[0].points
                s = rg.arclength(p)[:len(p)]
                r = profile_r(s, s[-1], kind, rng)
                W = 2.2 if art == "hokusai" else 1.8
                # the swelling diameter follows r too, so a mass is an oval, not a capsule
                mass = 2.6 * W * (0.45 + 0.55 * np.clip(r - 1.0, 0, 1))
                st = rg.make(p, r, phi=np.deg2rad(55 if art == "hokusai" else 70), W=W, mass=mass)
                if kind == "crescendo":
                    st = rg.terminal_drop(st, kind="drop", size=2.2 * W)
                paths = rg.render(st, PEN, wet=wet, fill_style="spiral" if wet else "concentric")
                cx, cy = ki * cw + cw / 2, (ai * 2 + row) * ch + ch / 2 + 4
                draw([q + [cx, cy] for q in paths], (0, 0, len(kinds) * cw, len(arts) * 2 * ch), img=sheet)
                label(sheet, (ki * cw * PXMM + 10, (ai * 2 + row) * ch * PXMM + 8), f"{art} · {kind}", 15)
                costs.append({"art": art, "kind": kind, **rg.pen_cost(paths), "regime": rg.regime_cost(st, paths)})
    save_jpg(sheet, RESULTS / out_name)
    (OUT / out_name.replace(".jpg", "_costs.json")).write_text(json.dumps(costs, indent=1))
    print("ok", len(costs))


# ---------------------------------------------------------------------------
# sheet (c): tree with r following depth
# ---------------------------------------------------------------------------

def tree_strokes(seed=101, *, size_mm=180.0, r_by_order=(2.0, 1.2, 0.8, 0.25, 0.0), W=2.6,
                 phi_deg=60.0, smooth_w=3.0, art: str | None = "hokusai"):
    """oehlen_tree skeleton → RegimeStrokes. r follows depth: each branch
    starts at its host's r at the attachment and relaxes to its own order's
    level over a few nib widths (continuity at the fork), then tapers to
    a line at a free tip."""
    from gesture import topology
    from gesture import tremor as tr
    from gesture.core import Drawing, Stroke
    rng = np.random.default_rng(seed)
    d = topology.generate_structure(None, rng, (1200, 1200), kind="oehlen_tree", depth=4)
    sc = size_mm / 1200.0
    if art:
        model, mode, _ = _tremor(art)
        lw = d.meta["line_width_px"]
        d = tr.apply_tremor(Drawing([Stroke(s.points, width=np.full(len(s), lw), meta=s.meta) for s in d.strokes],
                                    size=d.size, meta=d.meta), model, rng, 1.0, mode=mode)
    out = []
    host_r = {}
    for i, s in enumerate(d.strokes):
        p = s.points * sc
        o = int(s.meta.get("order", 0))
        lvl = r_by_order[min(o, len(r_by_order) - 1)]
        sl = rg.arclength(p)[:len(p)]
        L = sl[-1]
        r = np.full(len(p), lvl)
        h = s.meta.get("host")
        if h is not None and h in host_r:
            # host's r at the attachment point
            hp, hr = host_r[h]
            j = int(np.argmin(np.linalg.norm(hp - p[0], axis=1)))
            r0 = hr[j]
            ramp = smooth_w * W * 2
            r = lvl + (min(r0, lvl + 0.9) - lvl) * (1 - rg._smoothstep(sl / ramp))
        if s.meta.get("end") in ("budget", "edge") and o > 0:
            # free tip: thins out to a line
            r = r * (1 - rg._smoothstep((sl - (L - 3 * W)) / (3 * W)) * (1 - 0.0))
        mass = np.full(len(p), 2.0 * W)
        if o == 0:
            # trunk: a mass at the ground that tapers (cone) and becomes a nib
            # ribbon over its upper half — one long metamorphosis, not a club
            u = sl / max(L, 1e-9)
            r = 2.0 - 1.0 * rg._smoothstep(u / 0.75)
            mass = W * (4.5 - 3.2 * u)
        host_r[i] = (p, r)
        out.append(rg.make(p, r, phi=np.deg2rad(phi_deg), W=W * (1.0 if o else 1.3),
                           mass=mass, meta={"order": o}))
    return out


def stage_tree():
    from PIL import Image
    cw, ch = 190.0, 190.0
    sheet = Image.new("L", (int(2 * cw * PXMM), int(ch * PXMM)), 255)
    costs = []
    for k, (seed, art) in enumerate([(101, "hokusai"), (7, "matisse")]):
        sts = tree_strokes(seed, art=art)
        paths = rg.render(sts, PEN)
        draw([q + [k * cw + 5, 5] for q in paths], (0, 0, 2 * cw, ch), img=sheet)
        label(sheet, (k * cw * PXMM + 10, 8), f"oehlen_tree seed {seed}, {art} tremor: r follows depth", 16)
        rc = rg.regime_cost(sts, paths)
        costs.append({"seed": seed, **rg.pen_cost(paths), "regime": rc})
        print(seed, rg.pen_cost(paths), {k2: round(v["per_mm"], 2) for k2, v in rc.items()})
    save_jpg(sheet, RESULTS / "regime-tree.jpg")
    (OUT / "tree_costs.json").write_text(json.dumps(costs, indent=1))


def stage_cost():
    """Pen cost per mm of stroke at constant r (straight and wavy strokes)."""
    rows = []
    for W in (1.5, 2.5, 4.0):
        for r in (0.0, 0.5, 1.0, 1.5, 2.0):
            for shape in ("straight", "wave"):
                p = (np.column_stack([np.linspace(0, 80, 400), np.zeros(400)]) if shape == "straight"
                     else _wave(80, 6, 400, 40))
                st = rg.make(p, r, phi=np.deg2rad(60), W=W)
                paths = rg.render(st, PEN)
                c = rg.pen_cost(paths)
                rows.append({"W": W, "r": r, "shape": shape, "per_mm": c["length"] / st.length(),
                             "paths": c["paths"]})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cost.json").write_text(json.dumps(rows, indent=1))
    for row in rows:
        print(row)


# ---------------------------------------------------------------------------
# stage: edges — wet mass edges measured in data (results/regime-masses-*.md)
# ---------------------------------------------------------------------------

EDGE_OUT = OUTROOT / "regime_masses"


def _ink_mask_generic(g: np.ndarray):
    """gray (ink dark, [0,1]) → (mask, blurred gray). Background-normalised
    (large grey closing) then Otsu; a 0.8 px blur first so the threshold does
    not trace JPEG blocks."""
    from scipy import ndimage as ndi
    from skimage.filters import threshold_otsu
    gb = ndi.gaussian_filter(g, 0.8)
    size = max(31, int(0.04 * max(g.shape)) | 1)
    small = gb[::4, ::4]
    bg = ndi.grey_closing(small, size=(size // 4 | 1, size // 4 | 1))
    bg = ndi.zoom(bg, (g.shape[0] / bg.shape[0], g.shape[1] / bg.shape[1]), order=1)[:g.shape[0], :g.shape[1]]
    n = np.clip(gb / np.maximum(bg, 0.05), 0, 1.2)
    t = threshold_otsu(n[::2, ::2])
    t = min(t, 0.72)
    return n < t, n


def _contour(reg: np.ndarray, nrm: np.ndarray | None = None):
    """Sub-pixel outer contour of a boolean region (largest), (M, 2) xy."""
    from skimage.measure import find_contours
    from scipy import ndimage as ndi
    f = ndi.gaussian_filter(np.pad(reg.astype(float), 2), 0.7)
    cs = find_contours(f, 0.5)
    if not cs:
        return None
    c = max(cs, key=len)[:, ::-1] - 2.0
    return c


def _resample_closed(c: np.ndarray, n: int) -> np.ndarray:
    c = np.vstack([c, c[:1]]) if not np.allclose(c[0], c[-1]) else c
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(c, axis=0), axis=1))])
    t = np.linspace(0, s[-1], n, endpoint=False)
    return np.column_stack([np.interp(t, s, c[:, 0]), np.interp(t, s, c[:, 1])]), float(s[-1])


def edge_profile(c: np.ndarray, D: float, *, n: int = 1024, sigma_core: float = 0.25):
    """Deviation of a closed outline from its smoothed core outline.
    Returns dict: delta (n,) in units of D (outward +), s_D (arc step in D),
    normals, core. sigma_core is the smoothing in units of D (arc length)."""
    z, P = _resample_closed(c, n)
    ds = P / n
    sig = sigma_core * D / ds
    core = np.column_stack([gaussian_filter1d(z[:, 0], sig, mode="wrap"), gaussian_filter1d(z[:, 1], sig, mode="wrap")])
    t = np.gradient(np.vstack([core[-1:], core, core[:1]]), axis=0)[1:-1]
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    nrm = np.column_stack([t[:, 1], -t[:, 0]])
    # outward: area sign (image coords, y down)
    area2 = np.sum(core[:, 0] * np.roll(core[:, 1], -1) - np.roll(core[:, 0], -1) * core[:, 1])
    if area2 < 0:
        nrm = -nrm
    delta = np.sum((z - core) * nrm, axis=1) / D
    return {"delta": delta, "ds_D": ds / D, "P_D": P / D, "nrm": nrm, "core": core, "z": z, "sigma": sigma_core}


BANDS = ((0.5, 1.0), (1.0, 2.0), (2.0, 4.0), (4.0, 8.0), (8.0, 16.0))


def edge_spectrum(ep: dict, px_D: float):
    """Band RMS of the deviation (units of D) per octave of spatial frequency
    in cycles per D, corrected for the core smoothing's high-pass; bands
    above the pixel floor (f > D/(5 px)) are NaN."""
    d = ep["delta"] - ep["delta"].mean()
    n = len(d)
    F = np.fft.rfft(d)
    f = np.fft.rfftfreq(n, d=ep["ds_D"])            # cycles per D
    pw = (np.abs(F) ** 2) * 2 / n ** 2             # variance per bin (one-sided)
    H = 1.0 - np.exp(-2 * np.pi ** 2 * ep["sigma"] ** 2 * f ** 2)
    ok = H > 0.25
    out = []
    fmax = px_D / 5.0
    for lo, hi in BANDS:
        sel = (f >= lo) & (f < hi) & ok
        if hi > fmax or not sel.any():
            out.append(float("nan"))
            continue
        out.append(float(np.sqrt(np.sum(pw[sel] / H[sel] ** 2))))
    # slope of the PSD (power per log-frequency) over the valid bands
    return out


def _extrema(d: np.ndarray, prom: float):
    from scipy.signal import find_peaks
    dd = np.concatenate([d, d, d])
    n = len(d)
    pk, _ = find_peaks(dd, prominence=prom)
    tr, _ = find_peaks(-dd, prominence=prom)
    return int(np.sum((pk >= n) & (pk < 2 * n))), int(np.sum((tr >= n) & (tr < 2 * n)))


def measure_masses(g: np.ndarray, *, source: str, sheet: str, min_D_px: float = 28.0,
                   deep_w: float = 1.5, max_masses: int = 60) -> tuple[list[dict], dict]:
    """Masses in one gray image and their edge statistics (see the results
    doc for definitions). Returns (rows, sheet info)."""
    from scipy import ndimage as ndi
    from skimage.morphology import skeletonize, disk
    from scipy.ndimage import binary_opening
    mask, nrm = _ink_mask_generic(g)
    edt = ndi.distance_transform_edt(mask)
    sk = skeletonize(mask)
    if sk.sum() < 50:
        return [], {"sheet": sheet, "w_px": float("nan")}
    w = float(np.median(2 * edt[sk]))
    w = max(w, 1.5)
    deep = edt > deep_w * w
    ro = max(1, int(round(0.9 * w)))
    opened = binary_opening(mask, structure=disk(ro))
    lab, nl = ndi.label(opened)
    has_deep = np.unique(lab[deep & opened])
    rows = []
    objs = ndi.find_objects(lab)
    info = {"sheet": sheet, "source": source, "w_px": w, "shape": list(g.shape)}
    # line edges (tremor comparison): thin ink away from masses
    line_rms = []
    for k in has_deep:
        if k == 0:
            continue
        sl = objs[k - 1]
        pad = 6
        y0, x0 = max(sl[0].start - pad, 0), max(sl[1].start - pad, 0)
        y1, x1 = min(sl[0].stop + pad, g.shape[0]), min(sl[1].stop + pad, g.shape[1])
        reg = lab[y0:y1, x0:x1] == k
        A = float(reg.sum())
        D = float(np.sqrt(4 * A / np.pi))
        if D < min_D_px:
            continue
        # touching the image border: outline not trustworthy
        if y0 == 0 or x0 == 0 or y1 == g.shape[0] or x1 == g.shape[1]:
            continue
        c = _contour(reg)
        if c is None or len(c) < 30:
            continue
        ep = edge_profile(c, D)
        d = ep["delta"]
        ys, xs = np.nonzero(reg)
        cov = np.cov(np.vstack([xs, ys]))
        ev, evec = np.linalg.eigh(cov)
        elong = float(np.sqrt(ev[1] / max(ev[0], 1e-9)))
        major = evec[:, 1]
        # ends vs sides roughness (anisotropy): normal ∥ major axis = ends
        cosang = np.abs(ep["nrm"] @ major)
        ends, sides = cosang > 0.7, cosang < 0.4
        aniso = float(np.std(d[ends]) / max(np.std(d[sides]), 1e-9)) if ends.sum() > 20 and sides.sum() > 20 else float("nan")
        # concavity
        from shapely.geometry import Polygon, Point
        poly = Polygon(ep["z"]).buffer(0)
        if poly.geom_type != "Polygon":
            poly = max(poly.geoms, key=lambda q: q.area)
        sol = float(poly.area / max(poly.convex_hull.area, 1e-9))
        dsm = gaussian_filter1d(d, 0.02 / ep["ds_D"], mode="wrap")
        lobes, _ = _extrema(dsm, 0.03)
        # bays: pockets of (convex hull − mass) deeper than 0.06 D
        pockets = poly.convex_hull.difference(poly)
        bays = 0
        bay_depth = []
        for pk_ in getattr(pockets, "geoms", [pockets]):
            if pk_.is_empty or pk_.geom_type != "Polygon":
                continue
            dep = max((poly.convex_hull.exterior.distance(Point(xy)) for xy in pk_.exterior.coords), default=0.0) / D
            if dep > 0.06:
                bays += 1
                bay_depth.append(dep)
        deep_bays = int(sum(dd > 0.15 for dd in bay_depth))
        cpoly = Polygon(ep["core"]).buffer(0)
        core_bays = 0
        if cpoly.geom_type == "Polygon":
            cpk = cpoly.convex_hull.difference(cpoly)
            for pk_ in getattr(cpk, "geoms", [cpk]):
                if pk_.is_empty or pk_.geom_type != "Polygon":
                    continue
                dep = max((cpoly.convex_hull.exterior.distance(Point(xy)) for xy in pk_.exterior.coords), default=0.0) / D
                core_bays += int(dep > 0.06)
        # pooling: darkness-weighted centroid vs geometric centroid
        dark = np.clip(1.0 - nrm[y0:y1, x0:x1][reg], 0, None)
        cx, cy = xs.mean(), ys.mean()
        if dark.sum() > 0:
            px = float(np.sum(xs * dark) / dark.sum() - cx) / D
            py = float(np.sum(ys * dark) / dark.sum() - cy) / D
        else:
            px = py = 0.0
        dark_cv = float(np.std(dark) / max(np.mean(dark), 1e-9))
        # end asymmetry along the major axis: width in the two end thirds
        proj = (xs - cx) * major[0] + (ys - cy) * major[1]
        lo_, hi_ = np.quantile(proj, [0.0, 1.0])
        span = hi_ - lo_
        bins = np.linspace(lo_, hi_, 10)
        cnt = np.histogram(proj, bins)[0].astype(float)
        wa, wb = cnt[1:4].mean(), cnt[-4:-1].mean()
        heavy = max(wa, wb) / max(min(wa, wb), 1e-9)
        # which end is lower on the page (y down): end b is at +major
        b_lower = (major[1] > 0)
        heavy_lower = bool((wb > wa) == b_lower) if abs(major[1]) > 0.5 else None
        # exits: thin ink leaving the mass, within 0.6 D of its outline
        ring_out = ndi.binary_dilation(reg, iterations=max(2, int(0.6 * D)))
        seam = ndi.binary_dilation(reg, iterations=2) & ~reg
        thin = mask[y0:y1, x0:x1] & ring_out & ~reg
        # crop may cut exits; that's fine (pad is small; exits measured up to the crop)
        tl, nt = ndi.label(thin)
        exits = []
        if nt:
            dist_out = ndi.distance_transform_edt(~reg)
            edt_l = edt[y0:y1, x0:x1]
            touching = np.unique(tl[seam & (tl > 0)])
            for j in touching:
                if j == 0:
                    continue
                cj = tl == j
                ln = float(dist_out[cj].max()) / D
                wj = float(np.median(2 * edt_l[cj]))
                if ln < 0.05:
                    continue
                exits.append((ln, wj / w))
        hairs = [e for e in exits if e[1] < 0.8]
        rows.append({
            "source": source, "sheet": sheet, "D_px": D, "D_w": D / w, "elong": elong, "solidity": sol,
            "rms": float(np.std(d)), "bands": edge_spectrum(ep, D), "skew": float(
                np.mean((d - d.mean()) ** 3) / max(np.std(d) ** 3, 1e-12)),
            "kurt": float(np.mean((d - d.mean()) ** 4) / max(np.std(d) ** 4, 1e-12)),
            "lobes": lobes, "bays": bays, "deep_bays": deep_bays, "core_bays": core_bays, "bay_depth_D": [round(x, 3) for x in bay_depth], "perim_D": ep["P_D"],
            "aniso_end_side": aniso, "pool_dx": px, "pool_dy": py, "dark_cv": dark_cv,
            "end_ratio": float(heavy), "heavy_end_lower": heavy_lower,
            "exits": len(exits), "hairs": len(hairs),
            "exit_len_D": [round(e[0], 3) for e in exits], "exit_w": [round(e[1], 2) for e in exits],
            # fine edge rms (σ = 1 w high-pass), in units of w: compare with line edges
            "rms_w_fine": float(np.std(edge_profile(c, D, n=max(256, int(ep["P_D"] * D / 0.5)),
                                                    sigma_core=w / D)["delta"]) * D / w),
        })
        if len(rows) >= max_masses:
            break
    # line edges: contours of mask components with no deep core, length ≥ 20 w
    thin_lab = lab.copy()
    lines = mask & ~ndi.binary_dilation(opened, iterations=2)
    ll, nll = ndi.label(lines)
    sizes = ndi.sum(lines, ll, index=np.arange(1, nll + 1))
    order = np.argsort(-sizes)[:40]
    lobjs = ndi.find_objects(ll)
    for o in order:
        k = o + 1
        if sizes[o] < 20 * w * w:
            break
        sl = lobjs[o]
        reg = ll[sl] == k
        c = _contour(reg)
        if c is None or len(c) < 50:
            continue
        L = _resample_closed(c, 16)[1]
        if L < 40 * w:
            continue
        ep = edge_profile(c, w, n=max(256, int(L / 0.5)), sigma_core=1.0)
        line_rms.append(float(np.std(ep["delta"])))
    info["line_rms_w_fine"] = line_rms
    info["n_masses"] = len(rows)
    return rows, info


def _edge_sheets():
    """(source, sheet id, path-or-sheet-id, max side) for every source of masses."""
    from gesture import calligraphy as cg
    items = [("reference", "ian-regimes-sd-2024", str(REF), 4000)]
    for p in sorted((REPO / ".local/gesture/corpus/artists/brice_marden").glob("*.jpg")):
        items.append(("marden", p.stem, str(p), 4000))
    for p in sorted((REPO / ".local/gesture/corpus/hokusai").glob("*.jpg")):
        items.append(("hokusai", p.stem, str(p), 2400))
    for sid in cg.SHEETS:
        if not sid.startswith("nyu-"):
            items.append(("calligraphy", sid, sid, 2400))
    return items


def _edge_load(item) -> np.ndarray:
    from PIL import Image
    from gesture import calligraphy as cg
    source, sheet, arg, max_side = item
    if source == "calligraphy":
        return cg.load_sheet(arg, max_side=max_side)[0]
    im = Image.open(arg).convert("RGB")
    if max(im.size) > max_side:
        sc = max_side / max(im.size)
        im = im.resize((round(im.size[0] * sc), round(im.size[1] * sc)), Image.Resampling.BOX)
    return cg.to_gray(np.asarray(im, dtype=np.float64) / 255.0, "black")


EDGE_DEEP_W = {"marden": 1.0}     # Marden's pools are 2-3 line widths: a lower depth bar


def _edge_job(item):
    source, sheet = item[0], item[1]
    try:
        rows, info = measure_masses(_edge_load(item), source=source, sheet=sheet,
                                    deep_w=EDGE_DEEP_W.get(source, 1.5), min_D_px=24.0)
    except Exception as e:  # noqa: BLE001 — one bad sheet must not stop the stage
        return [], {"sheet": sheet, "source": source, "error": repr(e)}
    return rows, info


def _q(v, qs=(0.25, 0.5, 0.75)):
    v = [x for x in v if x is not None and np.isfinite(x)]
    return [round(float(np.quantile(v, q)), 4) for q in qs] if v else [None] * len(qs)


def summarise_edges(rows: list[dict], infos: list[dict]) -> dict:
    out = {}
    for src in sorted({r["source"] for r in rows} | {"calligraphy_gen"}):
        if src == "calligraphy_gen":
            from gesture import calligraphy as cg
            man = {**cg.load_manifest("print"), **cg.load_manifest("calligraphy")}
            ok = {sid for sid in cg.SHEETS if cg._manifest_id(sid) in man and cg.generative_allowed(man[cg._manifest_id(sid)])}
            R = [r for r in rows if r["source"] == "calligraphy" and r["sheet"] in ok]
            if R:
                cg.require_generative(sorted({r["sheet"] for r in R}))
        else:
            R = [r for r in rows if r["source"] == src]
        if not R:
            continue
        I = [i for i in infos if i.get("source") == (src if src != "calligraphy_gen" else "calligraphy")]
        bands = np.array([r["bands"] for r in R], dtype=float)
        out[src] = {
            "n": len(R), "sheets": len({r["sheet"] for r in R}),
            "D_w": _q([r["D_w"] for r in R]), "elong": _q([r["elong"] for r in R]),
            "rms_D": _q([r["rms"] for r in R]),
            "band_rms_D": [None if not np.isfinite(bands[:, k]).any() else round(float(np.nanmedian(bands[:, k])), 4)
                           for k in range(len(BANDS))],
            "band_n": [int(np.isfinite(bands[:, k]).sum()) for k in range(len(BANDS))],
            "solidity": _q([r["solidity"] for r in R]), "skew": _q([r["skew"] for r in R]),
            "kurt": _q([r["kurt"] for r in R]),
            "lobes_per_perimD": _q([r["lobes"] / r["perim_D"] for r in R]),
            "bays": _q([r["bays"] for r in R]),
            "edge_bays": _q([max(r["bays"] - r["core_bays"], 0) for r in R]),
            "edge_bays_mean": round(float(np.mean([max(r["bays"] - r["core_bays"], 0) for r in R])), 3),
            "bay_depth_D": _q([x for r in R for x in r["bay_depth_D"]]),
            "rough_rms_D": _q([float(np.sqrt(np.nansum(np.square(r["bands"][1:])))) for r in R]),
            "deep_bays": _q([r["deep_bays"] for r in R]),
            "aniso_end_side": _q([r["aniso_end_side"] for r in R]),
            "pool_offset_D": _q([float(np.hypot(r["pool_dx"], r["pool_dy"])) for r in R]),
            "pool_down_share": round(float(np.mean([r["pool_dy"] > 0 for r in R])), 3),
            "dark_cv": _q([r["dark_cv"] for r in R]),
            "end_ratio": _q([r["end_ratio"] for r in R]),
            "heavy_end_lower": (lambda v: [round(float(np.mean(v)), 3) if v else None, len(v)])(
                [r["heavy_end_lower"] for r in R if r["heavy_end_lower"] is not None]),
            "exits": _q([r["exits"] for r in R]), "hairs": _q([r["hairs"] for r in R]),
            "hair_share": round(float(np.mean([r["hairs"] > 0 for r in R])), 3),
            "exit_len_D": _q([x for r in R for x in r["exit_len_D"]]),
            "hair_len_D": _q([x for r in R for x, w in zip(r["exit_len_D"], r["exit_w"]) if w < 0.8]),
            "exit_w": _q([x for r in R for x in r["exit_w"]]),
            "mass_rms_w_fine": _q([r["rms_w_fine"] for r in R]),
            "line_rms_w_fine": _q([x for i in I for x in i.get("line_rms_w_fine", [])]),
        }
    return out


def edge_floor() -> dict:
    """Measurement floor: perfect discs / ellipses rasterised at mass sizes."""
    out = {}
    for D in (30, 60, 120, 240):
        yy, xx = np.mgrid[0:D + 20, 0:int(1.6 * D) + 20]
        reg = ((xx - (0.8 * D + 10)) / (0.8 * D)) ** 2 + ((yy - (D / 2 + 10)) / (D / 2)) ** 2 < 1
        Deq = float(np.sqrt(4 * reg.sum() / np.pi))
        ep = edge_profile(_contour(reg), Deq)
        out[D] = {"rms_D": float(np.std(ep["delta"])), "bands": edge_spectrum(ep, Deq)}
    return out


def stage_edges():
    from multiprocessing import Pool
    EDGE_OUT.mkdir(parents=True, exist_ok=True)
    items = _edge_sheets()
    with Pool(3) as pool:
        res = pool.map(_edge_job, items, chunksize=1)
    rows = [r for rr, _ in res for r in rr]
    infos = [i for _, i in res]
    (EDGE_OUT / "edges_rows.json").write_text(json.dumps(rows, indent=0))
    (EDGE_OUT / "edges_infos.json").write_text(json.dumps(infos, indent=0))
    summ = summarise_edges(rows, infos)
    summ["_floor"] = edge_floor()
    (EDGE_OUT / "edges_summary.json").write_text(json.dumps(summ, indent=1))
    for k, v in summ.items():
        print(k, json.dumps(v))
    for i in infos:
        if "error" in i:
            print("ERROR", i)


# ---------------------------------------------------------------------------
# sheets: wet masses (results/regime-masses-2026-10-16.md)
# ---------------------------------------------------------------------------

def _r6_module():
    """Round-6 regime.py (saved copy) for the 'before' column."""
    import importlib.util
    path = EDGE_OUT / "regime_r6.py"
    spec = importlib.util.spec_from_file_location("regime_r6", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["regime_r6"] = mod
    spec.loader.exec_module(mod)
    return mod


def mass_items(M, seed: int = 7):
    """(name, strokes, render kwargs for the AFTER column) built with module M."""
    rng = np.random.default_rng(seed)
    W = 2.4
    straight = M.make(np.column_stack([np.linspace(0, 40, 200), np.zeros(200)]), 0.0, W=W)
    base = M.make(_wave(50, 4, 300, 50), 0.0, phi=np.deg2rad(50), W=W)
    vert = M.make(np.column_stack([np.zeros(240) + 0.6 * np.sin(np.linspace(0, 3, 240)), np.linspace(0, 48, 240)]),
                  0.0, phi=np.deg2rad(30), W=W)
    items = [
        ("bead on a line", M.swell(straight, 0.5, length=12, size=6)),
        ("nib swells into a mass and back", M.swell(M.thicken(base, 0.1, until=0.95), 0.35, length=20, size=9)),
        ("line closes into a dot", M.close_fill(straight, radius=3.0, amount=1.0)),
        ("terminal drop", M.terminal_drop(base, kind="drop", size=4.5)),
        ("vessel", M.swell(M.thicken(vert, 0.1, to=0.6), 0.45, kind="vessel", size=8)),
        ("big vertical mass (r 2 most of its length)",
         M.replace(vert, r=np.clip(2.2 * np.sin(np.linspace(0.05, 3.0, 240)) ** 0.5, 0, 2),
                   mass=np.linspace(5, 9, 240))),
    ]
    mass = M.swell(M.thicken(straight, 0.1, until=0.95), 0.5, length=30, size=10)
    items.append(("drips from a mass", M.shed(mass, rng, n=5, kind="drips", length=14, where=(0.3, 0.7))))
    items.append(("dry exits: a heavy stroke ends in hairs",
                  M.shed(M.thicken(base, 0.05, to=2.0), rng, n=6, kind="hairs", length=10)))
    return items


def _place(paths, cx, cy):
    allp = np.vstack(paths)
    lo, hi = allp.min(0), allp.max(0)
    c = 0.5 * (lo + hi)
    return [p - c + [cx, cy] for p in paths]


def stage_masses():
    """Before/after catalogue: round-6 render vs wet edges (reference
    profile) + rim fix + spiral fill; plus Oehlen-style edge events."""
    from PIL import Image
    old = _r6_module()
    EDGE_OUT.mkdir(parents=True, exist_ok=True)
    before = mass_items(old)
    after = mass_items(rg)
    extra = [
        ("scallop: 7 bumps on one side (Baum 44), clean edge otherwise", mass_items(rg)[5][1],
         {"edge": {"mode": "scallop", "count": 7, "amp": 0.16, "extent": (0.2, 0.75), "side": 1}}),
        ("notches: 9 V cuts on one side (Baum 92)", mass_items(rg)[5][1],
         {"wet": "hokusai", "edge": {"mode": "notch", "count": 9, "amp": 0.22, "extent": (0.15, 0.8), "side": -1}}),
    ]
    cols = 4                 # (before, after) × 2 per row
    cw, ch = 62.0, 64.0
    n = len(before) + len(extra)
    rows = int(np.ceil(n / 2))
    sheet = Image.new("L", (int(cols * cw * PXMM), int(rows * ch * PXMM)), 255)
    costs = []
    k = 0
    for (name, sb), (_, sa) in zip(before, after):
        pb = old.render(sb, PEN)
        pa = rg.render(sa, PEN, wet="reference", fill_style="spiral", seed=11 + k)
        for col, (pp, tag) in enumerate(((pb, "before"), (pa, "after"))):
            cx = ((2 * (k % 2) + col) + 0.5) * cw
            cy = (k // 2 + 0.5) * ch + 3
            draw(_place(pp, cx, cy), (0, 0, cols * cw, rows * ch), img=sheet)
            label(sheet, (((2 * (k % 2) + col)) * cw * PXMM + 8, (k // 2) * ch * PXMM + 6),
                  f"{k + 1}{'ab'[col]}. {name} — {tag}", 13)
        costs.append({"item": name, "before": rg.pen_cost(pb), "after": rg.pen_cost(pa),
                      "after_concentric": rg.pen_cost(rg.render(sa, PEN, wet="reference", seed=11 + k)),
                      "rim_before": rg.rim_gap(sa, [np.asarray(p) for p in pb], PEN),
                      "rim_after": rg.rim_gap(sa, pa, PEN)})
        k += 1
    for name, st, kw in extra:
        pp = rg.render(st, PEN, fill_style="spiral", seed=5, **kw)
        cx = ((2 * (k % 2) + 0.5) + 0.5) * cw
        cy = (k // 2 + 0.5) * ch + 3
        draw(_place(pp, cx, cy), (0, 0, cols * cw, rows * ch), img=sheet)
        label(sheet, ((2 * (k % 2)) * cw * PXMM + 8, (k // 2) * ch * PXMM + 6), f"{k + 1}. {name}", 13)
        costs.append({"item": name, "after": rg.pen_cost(pp)})
        k += 1
    save_jpg(sheet, RESULTS / "regime-masses-catalogue.jpg")
    (EDGE_OUT / "catalogue_costs.json").write_text(json.dumps(costs, indent=1))
    for c in costs:
        print(json.dumps(c))


def _blob_strokes(kind: str, rng) -> list:
    """Base strokes for the source comparison: the same few mass shapes."""
    if kind == "oval":
        p = np.column_stack([np.linspace(0, 10, 60), np.zeros(60)])
        return [rg.make(p, 2.0, W=1e-3, mass=np.full(60, 9.0))]
    if kind == "club":
        p = np.column_stack([np.linspace(0, 24, 120), 1.5 * np.sin(np.linspace(0, 2, 120))])
        return [rg.make(p, np.clip(np.linspace(0.6, 3.2, 120), 0, 2), W=2.0, mass=np.linspace(3, 9, 120))]
    if kind == "bar":
        p = np.column_stack([0.8 * np.sin(np.linspace(0, 2.5, 200)), np.linspace(0, 40, 200)])
        return [rg.make(p, 2.0, W=1e-3, mass=np.linspace(7, 5, 200))]
    if kind == "kidney":
        t = np.linspace(-1.1, 1.1, 120)
        p = np.column_stack([9 * np.sin(t), -6 * np.cos(t)])
        return [rg.make(p, 2.0, W=1e-3, mass=np.full(120, 6.5))]
    raise ValueError(kind)


def stage_sources():
    """Masses with each data source's fitted edge profile, side by side; the
    same four base shapes, three seeds each (variety)."""
    from PIL import Image
    srcs = ["none", "calligraphy", "hokusai", "marden", "reference"]
    shapes = ["oval", "club", "bar", "kidney"]
    seeds = [1, 2, 3]
    cw, ch = 34.0, 50.0
    ncol = len(shapes) * len(seeds)
    sheet = Image.new("L", (int(ncol * cw * PXMM + 150), int(len(srcs) * ch * PXMM)), 255)
    rng = np.random.default_rng(0)
    for i, src in enumerate(srcs):
        label(sheet, (8, int((i + 0.45) * ch * PXMM)), src, 16)
        for a, shp in enumerate(shapes):
            for b, sd in enumerate(seeds):
                st = _blob_strokes(shp, rng)
                kw = {} if src == "none" else {"wet": src}
                pp = rg.render(st, PEN, seed=100 * a + sd, fill_style="spiral", **kw)
                cx = 150 / PXMM + (a * len(seeds) + b + 0.5) * cw
                draw(_place(pp, cx, (i + 0.5) * ch), (0, 0, ncol * cw + 150 / PXMM, len(srcs) * ch), img=sheet)
    save_jpg(sheet, RESULTS / "regime-masses-sources.jpg")


def stage_masstree():
    """Strahler tree: trunk = wet mass with drips and a scallop run, before/after."""
    from PIL import Image
    cw, ch = 190.0, 190.0
    sheet = Image.new("L", (int(2 * cw * PXMM), int(ch * PXMM)), 255)
    costs = []
    sts = tree_strokes(101, art="hokusai")
    old = _r6_module()
    # before: round-6 renderer on the same strokes (rebuilt as old-module strokes)
    ost = [old.RegimeStroke(s.points, s.r, s.phi, s.W, s.mass, s.w_min, s.closed, s.fill, s.meta) for s in sts]
    pb = old.render(ost, PEN)
    # after: the trunk (stroke with the highest mean r) gets drips and a scallop run
    k_tr = int(np.argmax([float(np.mean(s.r)) * s.length() for s in sts]))
    trunk = rg.replace(sts[k_tr], meta={**sts[k_tr].meta, "edge": {"mode": "scallop", "count": 6, "amp": 0.14,
                                                                     "extent": (0.15, 0.45), "side": -1}})
    rng = np.random.default_rng(4)
    drips = rg.shed(trunk, rng, n=4, kind="drips", length=16, where=(0.05, 0.4))[1:]
    pa = rg.render(sts[:k_tr] + [trunk] + sts[k_tr + 1:] + drips, PEN, wet="reference", fill_style="spiral", seed=3)
    for col, pp in enumerate((pb, pa)):
        draw([q + [col * cw + 5, 5] for q in pp], (0, 0, 2 * cw, ch), img=sheet)
        label(sheet, (col * cw * PXMM + 10, 8), ["before (round 6)", "after: wet edges, drips, scallop run, spiral fill"][col], 16)
        costs.append(rg.pen_cost(pp))
    save_jpg(sheet, RESULTS / "regime-masses-tree.jpg")
    (EDGE_OUT / "tree_costs.json").write_text(json.dumps(costs, indent=1))
    print(costs)


STAGES = {"fit": stage_fit, "catalogue": stage_catalogue, "grammar": stage_grammar, "tree": stage_tree,
          "cost": stage_cost, "edges": stage_edges,
          "masses": stage_masses, "grammarwet": lambda: stage_grammar("reference", "regime-masses-grammar.jpg"), "sources": stage_sources, "masstree": stage_masstree}

if __name__ == "__main__":
    for a in sys.argv[1:] or ["catalogue"]:
        STAGES[a]()
