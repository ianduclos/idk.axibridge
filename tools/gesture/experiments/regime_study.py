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
                  rg.shed(rg.thicken(base, 0.05, to=1.5), rng, n=6, kind="hairs", length=14)))
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
        k = rng.integers(2, 4)
        cs = np.sort(rng.uniform(0.15, 0.85, k))
        out = np.zeros_like(u)
        for c in cs:
            out = np.maximum(out, rng.uniform(1.0, 2.0) * np.exp(-0.5 * ((u - c) / 0.05) ** 2))
        return 0.6 * np.clip((u - 0.05) / 0.2, 0, 1) * (1 - np.clip((u - 0.8) / 0.2, 0, 1)) + out * (1 - 0.0)
    if kind == "crescendo":           # line → nib → mass at the end (a drop)
        return 2.0 * np.clip((u - 0.2) / 0.8, 0, 1) ** 1.6
    raise ValueError(kind)


def stage_grammar():
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
                paths = rg.render(st, PEN)
                cx, cy = ki * cw + cw / 2, (ai * 2 + row) * ch + ch / 2 + 4
                draw([q + [cx, cy] for q in paths], (0, 0, len(kinds) * cw, len(arts) * 2 * ch), img=sheet)
                label(sheet, (ki * cw * PXMM + 10, (ai * 2 + row) * ch * PXMM + 8), f"{art} · {kind}", 15)
                costs.append({"art": art, "kind": kind, **rg.pen_cost(paths), "regime": rg.regime_cost(st, paths)})
    save_jpg(sheet, RESULTS / "regime-grammar.jpg")
    (OUT / "grammar_costs.json").write_text(json.dumps(costs, indent=1))
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


STAGES = {"fit": stage_fit, "catalogue": stage_catalogue, "grammar": stage_grammar, "tree": stage_tree,
          "cost": stage_cost}

if __name__ == "__main__":
    for a in sys.argv[1:] or ["catalogue"]:
        STAGES[a]()
