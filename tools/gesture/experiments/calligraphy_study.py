"""Calligraphy + Arabic print as hands: extraction, broad-nib width model,
plotter width rendering, hand statistics, a first generative glimpse.

    .local/gesture/.venv/bin/python -m tools.gesture.experiments.calligraphy_study <stage> [...]

stages: extract | synth | nib | render | panel | generate | all
Outputs: .local/gesture/out/calligraphy/ (JSON drawings, overlays, figures,
summary JSON). Write-up: tools/gesture/results/calligraphy-2026-10-16.md.

POLICY: `generate` goes through calligraphy.require_generative — only
exercise / poetry / document rows with nothing flagged for verification can
reach the grammar. Everything else is measured only. Fonts are shaped with
calligraphy.NEUTRAL_STRINGS only.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import broadnib as bn  # noqa: E402
from gesture import calligraphy as C  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/calligraphy"
EXT = OUT / "extract"
PAPER = (255, 252, 240)
INK = (16, 15, 15)
ACC = [(0xAF, 0x30, 0x29), (0x20, 0x5E, 0xA6), (0x66, 0x80, 0x0B), (0xBC, 0x52, 0x15),
       (0x5E, 0x40, 0x9D), (0x24, 0x83, 0x7B), (0xA0, 0x2F, 0x6F), (0xAD, 0x83, 0x01)]
JOBS = 3

PRINT_PAGES = {
    "AL08": ["p0018", "p0028", "p0031", "p0038", "p0045", "p0051", "p0058", "p0065"],
    "AL09": ["p0086", "p0143", "p0181", "p0199", "p0218", "p0275", "p0294", "p0313"],
    "AL04": ["p0080", "p0185", "p0290", "p0394", "p0499", "p0604"],
    "AL01": ["p0056", "p0124", "p0193", "p0261", "p0330", "p0398"],
}
PRINT_CROP = (0.10, 0.08, 0.90, 0.90)
PRINT_KW = {"crop_to_plate": False, "drop_frames": False}
FONTS = {"amiri": "Amiri-Regular.ttf", "notokufi": "NotoKufiArabic_wght.ttf",
         "arefruqaa": "ArefRuqaa-Regular.ttf", "amiritype": "AmiriTypewriter-Regular.ttf"}


# ---------------------------------------------------------------------------
# small drawing helpers
# ---------------------------------------------------------------------------

def overlay(gray: np.ndarray, d: Drawing, scale: float, max_side: int = 1400) -> Image.Image:
    """Working gray faded + strokes in Flexoki accents (drawn in the working
    frame, so the overlay cannot drift)."""
    H, W = gray.shape
    f = min(1.0, max_side / max(H, W))
    base = Image.fromarray((np.clip(0.55 + 0.45 * gray, 0, 1) * 255).astype(np.uint8)).convert("RGB")
    base = base.resize((max(1, int(W * f)), max(1, int(H * f))), Image.Resampling.BOX)
    dr = ImageDraw.Draw(base)
    for i, st in enumerate(d.strokes):
        q = ((st.points + 0.5) * scale - 0.5) * f
        if st.closed:
            q = np.vstack([q, q[:1]])
        if len(q) >= 2:
            dr.line([tuple(v) for v in q], fill=ACC[i % len(ACC)], width=2)
    return base


def label(img: Image.Image, text: str) -> Image.Image:
    out = Image.new("RGB", (img.width, img.height + 22), PAPER)
    out.paste(img, (0, 22))
    ImageDraw.Draw(out).text((6, 5), text, fill=INK)
    return out


def grid(tiles, cols, title="", pad=8) -> Image.Image:
    tiles = [t for t in tiles]
    w = max(t.width for t in tiles if t is not None)
    h = max(t.height for t in tiles if t is not None)
    rows = (len(tiles) + cols - 1) // cols
    top = 30 if title else 0
    S = Image.new("RGB", (cols * (w + pad) + pad, rows * (h + pad) + pad + top), PAPER)
    if title:
        ImageDraw.Draw(S).text((pad, 8), title, fill=INK)
    for i, t in enumerate(tiles):
        if t is not None:
            S.paste(t, (pad + (i % cols) * (w + pad), top + pad + (i // cols) * (h + pad)))
    return S


def save_jpg(img: Image.Image, path: Path, max_kb: int = 600, max_side: int = 2400):
    path.parent.mkdir(parents=True, exist_ok=True)
    if max(img.size) > max_side:
        f = max_side / max(img.size)
        img = img.resize((int(img.width * f), int(img.height * f)), Image.Resampling.LANCZOS)
    q = 88
    while True:
        img.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024 or q < 40:
            break
        q -= 8


# ---------------------------------------------------------------------------
# stage: extract
# ---------------------------------------------------------------------------

def _extract_sheet_job(sid: str) -> dict:
    t = time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d, g = C.extract_sheet(sid, max_side=2000)
        s = d.meta["scale"]
        ol = C.outlines(g, scale=s, source=sid, original_size=d.size)
    genre = C.SHEETS[sid]["genre"]
    od = EXT / genre
    od.mkdir(parents=True, exist_ok=True)
    stem = sid.replace("#", "_")
    d.save(od / f"{stem}.json")
    ol.save(od / f"{stem}.outline.json")
    overlay(g, d, s).save(od / f"{stem}.jpg", quality=80)
    overlay(g, ol, s).save(od / f"{stem}.outline.jpg", quality=80)
    L = np.array([st.length() for st in d.strokes]) if d.strokes else np.zeros(1)
    w = d.meta.get("line_width_px", 1.0)
    return {"id": sid, "genre": genre, "strokes": len(d.strokes), "w_px": round(w, 2),
            "median_len_w": round(float(np.median(L) / w), 1), "p90_len_w": round(float(np.quantile(L, 0.9) / w), 1),
            "outline_contours": len(ol.strokes), "holes": sum(st.meta.get("hole", False) for st in ol.strokes),
            "rules_erased": d.meta.get("rules_erased", 0), "seconds": round(time.perf_counter() - t, 1)}


def _extract_print_job(args) -> dict:
    book, page = args
    from gesture import extract_hybrid
    t = time.perf_counter()
    path = C.CORPUS / f"print/scans/{book}/{book}_{page}.jp2"
    with Image.open(path) as im:
        im = im.convert("RGB")
        Wf, Hf = im.size
        c = PRINT_CROP
        im = im.crop((int(c[0] * Wf), int(c[1] * Hf), int(c[2] * Wf), int(c[3] * Hf)))
        size = im.size
        g = C.to_gray(np.asarray(im), "lum")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g, nr = C.remove_rules(g)
        # body text is sparse and thin: the default hysteresis binarisation
        # (Otsu reads the page shading of faint pages as ink)
        d = extract_hybrid.extract(g, scale=1.0, source=f"{book}_{page}", original_size=size, **PRINT_KW)
        ol = C.outlines(g, source=f"{book}_{page}", original_size=size, params=PRINT_KW)
    od = EXT / f"print_{book}"
    od.mkdir(parents=True, exist_ok=True)
    d.save(od / f"{book}_{page}.json")
    ol.save(od / f"{book}_{page}.outline.json")
    overlay(g, d, 1.0).save(od / f"{book}_{page}.jpg", quality=80)
    return {"id": f"{book}_{page}", "genre": f"print_{book}", "strokes": len(d.strokes),
            "w_px": round(d.meta.get("line_width_px", 0), 2), "seconds": round(time.perf_counter() - t, 1)}


def font_pages(font: str, n_pages: int = 6, px_per_em: float = 64.0, seed: int = 0):
    """Neutral-string 'pages' for a font: each page = 6 lines drawn (seeded)
    from NEUTRAL_STRINGS."""
    rng = np.random.default_rng(seed)
    path = C.CORPUS / "print/fonts" / FONTS[font]
    var = {"wght": 400} if "wght" in FONTS[font] else None
    out = []
    for k in range(n_pages):
        lines = [C.NEUTRAL_STRINGS[i] for i in rng.choice(len(C.NEUTRAL_STRINGS), 6, replace=True)]
        g, geoms = C.render_font_lines(path, lines, px_per_em=px_per_em, variations=var)
        out.append((f"{font}_{k}", g, geoms))
    return out


def _extract_font_job(args) -> list[dict]:
    font, px = args
    from gesture import extract_hybrid
    rows = []
    for name, g, _ in font_pages(font, px_per_em=px):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = extract_hybrid.extract(g, source=name, **C.EXTRACT_DEFAULTS)
            ol = C.outlines(g, source=name)
        od = EXT / f"font_{font}"
        od.mkdir(parents=True, exist_ok=True)
        d.save(od / f"{name}.json")
        ol.save(od / f"{name}.outline.json")
        overlay(g, d, 1.0).save(od / f"{name}.jpg", quality=80)
        rows.append({"id": name, "genre": f"font_{font}", "strokes": len(d.strokes),
                     "w_px": round(d.meta.get("line_width_px", 0), 2)})
    return rows


def _outline_job(sid: str) -> dict:
    g, s, info = C.load_sheet(sid, max_side=2000)
    g, _ = C.remove_rules(g)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ol = C.outlines(g, scale=s, source=sid, original_size=info["size"])
    genre = C.SHEETS[sid]["genre"]
    stem = sid.replace("#", "_")
    ol.save(EXT / genre / f"{stem}.outline.json")
    overlay(g, ol, s).save(EXT / genre / f"{stem}.outline.jpg", quality=80)
    return {"id": sid, "outline_contours": len(ol.strokes),
            "holes": int(sum(st.meta.get("hole", False) for st in ol.strokes))}


def stage_fonts(a):
    """Re-render + extract the neutral-string font pages (e.g. at another
    --font-px to match the print scans' line width)."""
    with ProcessPoolExecutor(JOBS) as ex:
        for rr in ex.map(_extract_font_job, [(f, a.font_px) for f in FONTS]):
            print(rr, flush=True)


def stage_outline(a):
    """Re-run only the outline view of the calligraphy sheets."""
    with ProcessPoolExecutor(JOBS) as ex:
        rows = list(ex.map(_outline_job, [s for s in C.SHEETS if (not a.only or s in a.only)]))
    for r in rows:
        print(r)
    (OUT / "outline_summary.json").write_text(json.dumps(rows, indent=1))


def stage_extract(a):
    EXT.mkdir(parents=True, exist_ok=True)
    rows = []
    sids = [s for s in C.SHEETS if (not a.only or s in a.only)]
    with ProcessPoolExecutor(JOBS) as ex:
        for r in ex.map(_extract_sheet_job, sids):
            print(r, flush=True)
            rows.append(r)
        if not a.only:
            jobs = [(b, p) for b, ps in PRINT_PAGES.items() for p in ps]
            for r in ex.map(_extract_print_job, jobs):
                print(r, flush=True)
                rows.append(r)
            for rr in ex.map(_extract_font_job, [(f, a.font_px) for f in FONTS]):
                print(rr, flush=True)
                rows += rr
    (OUT / "extract_summary.json").write_text(json.dumps(rows, indent=1))
    # contact sheet of overlays, one per genre
    tiles = []
    for genre in sorted({r["genre"] for r in rows}):
        for p in sorted((EXT / genre).glob("*.jpg"))[:2]:
            if ".outline" in p.name:
                continue
            im = Image.open(p)
            im.thumbnail((520, 520))
            tiles.append(label(im, f"{genre}: {p.stem}"))
    if tiles:
        grid(tiles, 5, "extraction overlays (centreline view), one or two sheets per genre").save(
            OUT / "extract_contact.jpg", quality=85)


def load_group(genre: str, outline: bool = False) -> dict[str, Drawing]:
    out = {}
    for p in sorted((EXT / genre).glob("*.json")):
        is_ol = p.name.endswith(".outline.json")
        if is_ol != outline:
            continue
        stem = p.name.replace(".outline.json", "").replace(".json", "")
        out[stem.replace("_p", "#p") if stem.startswith("nyu-baghdadi") else stem] = Drawing.load(p)
    return out


# ---------------------------------------------------------------------------
# stage: synth (nib model validation on renders with known nib)
# ---------------------------------------------------------------------------

def synth_scene(rng, phi, W, w0, *, twist=0.0, n=5, size=900, noise=0.0):
    geoms, cls = [], []
    for k in range(n):
        c = bn.synth_centreline(rng, length=rng.uniform(450, 800), kappa_sd=rng.uniform(0.006, 0.014),
                                corr=rng.uniform(50, 110), start=rng.uniform(150, size - 150, 2))
        c = c - c.mean(0) + rng.uniform(250, size - 250, 2)
        c = np.clip(c, 30, size - 30)
        cls.append(c)
        geoms.append(bn.sweep_polygon(c, phi, W, w0, twist=twist))
    g = bn.render_mask(geoms, (size, size))
    if noise > 0:
        from scipy.ndimage import gaussian_filter
        g = np.clip(gaussian_filter(g, 0.8) + rng.normal(0, noise, g.shape), 0, 1)
    return g, cls, geoms


def stage_synth(a):
    from gesture import extract_hybrid
    rng = np.random.default_rng(7)
    rows = []
    cases = []
    for phi_deg in (0, 30, 45, 70, 110, 150):
        for W, w0 in ((14, 2.0), (24, 3.0), (8, 1.5)):
            cases.append((phi_deg, W, w0, 0.0, 0.0))
    for twist in (np.deg2rad(20), np.deg2rad(40)):
        cases.append((40, 18, 2.0, twist, 0.0))
    cases.append((40, 18, 2.0, 0.0, 0.08))
    for phi_deg, W, w0, twist, noise in cases:
        g, cls, geoms = synth_scene(rng, np.deg2rad(phi_deg), W, w0, twist=twist, noise=noise)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = extract_hybrid.extract(g, **C.EXTRACT_DEFAULTS)
        r = bn.fit_drawing(d)
        f = r["sheet"]
        wm = r["w_med"]
        # ground-truth-centreline control: EDT width on the true centrelines
        from scipy import ndimage as ndi
        edt = ndi.distance_transform_edt(g < 0.5)
        TH, WI = [], []
        for c in cls:
            q, _, _ = bn._resample(c, 2.0)
            th = bn.page_angle(q, sigma=W / 2)
            ij = np.clip(np.round(q[:, ::-1]).astype(int), 0, g.shape[0] - 1)
            wv = 2 * edt[ij[:, 0], ij[:, 1]]
            TH.append(th[10:-10]); WI.append(wv[10:-10])
        fg = bn.fit_nib(np.concatenate(TH), np.concatenate(WI))
        err = (f.phi_deg - phi_deg + 90) % 180 - 90
        rows.append({"phi": phi_deg, "W": W, "w0": w0, "twist_deg": round(np.rad2deg(twist)), "noise": noise,
                     "fit_phi": round(f.phi_deg, 1), "phi_err": round(err, 1),
                     "fit_W": round(f.W * wm, 1), "fit_w0": round(f.w_min * wm, 1), "r2": round(f.r2, 3),
                     "r2_null": round(f.r2_null, 3), "gt_phi": round(fg.phi_deg, 1), "gt_W": round(fg.W, 1),
                     "gt_w0": round(fg.w_min, 1), "strokes": len(d.strokes)})
        print(rows[-1], flush=True)
        if phi_deg == 45 and W == 14 and twist == 0 and noise == 0:
            img = Image.fromarray((g * 255).astype(np.uint8)).convert("RGB")
            dr = ImageDraw.Draw(img)
            for i, st in enumerate(d.strokes):
                dr.line([tuple(v) for v in st.points], fill=ACC[i % 8], width=2)
            img.save(OUT / "synth_example.jpg", quality=85)
    (OUT / "synth_nib.json").write_text(json.dumps(rows, indent=1))
    e = np.array([abs(r["phi_err"]) for r in rows if r["twist_deg"] == 0 and r["noise"] == 0])
    print("median |phi err|", np.median(e), "max", e.max())


# ---------------------------------------------------------------------------
# stage: nib (fits per sheet / genre / font)
# ---------------------------------------------------------------------------

def stage_nib(a):
    groups = sorted(p.name for p in EXT.iterdir() if p.is_dir())
    rows = []
    hist = {}
    for gname in groups:
        for sid, d in load_group(gname).items():
            r = bn.fit_drawing(d, min_rel_width=0.4)
            f = r["sheet"]
            base = C.dominant_direction(d)
            row = {"group": gname, "id": sid, **f.as_dict(), "phi_spread_deg": round(r["phi_spread_deg"], 1),
                   "n_stroke_fits": len(r["strokes"]), "baseline_deg": round(base, 1),
                   "phi_rel_deg": round(float((f.phi_deg - base) % 180), 1) if np.isfinite(f.phi) else float("nan")}
            if r["strokes"]:
                ph = np.array([s["phi_deg"] for s in r["strokes"]])
                good = [s for s in r["strokes"] if s["r2"] > 0.3]
                row["stroke_r2_med"] = round(float(np.median([s["r2"] for s in r["strokes"]])), 3)
                row["frac_strokes_r2_gt_.3"] = round(len(good) / len(r["strokes"]), 2)
                hist.setdefault(gname, []).extend([(s["phi_deg"], s["len_w"]) for s in r["strokes"]])
            rows.append(row)
            print(gname, sid, {k: row[k] for k in ("phi_deg", "W", "w_min", "r2", "r2_null", "span", "phi_spread_deg")},
                  flush=True)
    (OUT / "nib_fits.json").write_text(json.dumps(rows, indent=1))
    # figure: per-genre width-vs-direction scatter of one representative + φ roses
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    show = [g for g in ("naskh", "baghdadi", "nastaliq", "shikasta", "diwani", "karalama", "maghribi", "kufic",
                        "font_amiri", "font_notokufi", "print_AL08", "tughra") if g in hist]
    ncol = 6
    nrow = 2 * int(np.ceil(len(show) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.6 * ncol, 2.2 * nrow), facecolor="#FFFCF0", squeeze=False)
    for ax in axes.ravel():
        ax.set_visible(False)
    for j, gname in enumerate(show):
        best = max((r for r in rows if r["group"] == gname and r["n"] > 400), key=lambda r: r["r2"], default=None)
        ax = axes[2 * (j // ncol), j % ncol]
        ax.set_visible(True)
        if best:
            d = load_group(gname)[best["id"]]
            res = bn.fit_drawing(d, min_rel_width=0.4, per_stroke=False)
            th, wi = res["samples"]
            th = np.rad2deg(th) % 180
            idx = np.random.default_rng(0).choice(len(th), min(3000, len(th)), replace=False)
            ax.scatter(th[idx], wi[idx], s=1, c="#6F6E69", alpha=0.35)
            tt = np.linspace(0, 180, 181)
            f = res["sheet"]
            ax.plot(tt, bn.nib_width(np.deg2rad(tt), f.phi, f.W, f.w_min), c="#AF3029", lw=1.5)
            ax.set_title(f"{gname}: {best['id'][:18]}\nφ={f.phi_deg:.0f}° R²={f.r2:.2f} (null {f.r2_null:.2f})", fontsize=7)
            ax.set_ylim(0, np.percentile(wi, 99) * 1.1)
        ax.set_xlabel("stroke direction θ (deg, page)", fontsize=6)
        ax.set_ylabel("width / median", fontsize=6)
        ax.tick_params(labelsize=6)
        ax2 = axes[2 * (j // ncol) + 1, j % ncol]
        ax2.set_visible(True)
        ph = np.array([p for p, _ in hist[gname]])
        wt = np.array([w for _, w in hist[gname]])
        ax2.hist(ph, bins=np.arange(0, 181, 10), weights=wt, color="#205EA6")
        ax2.set_title(f"{gname}: per-stroke φ, all sheets", fontsize=7)
        ax2.tick_params(labelsize=6)
    fig.tight_layout()
    fig.savefig(OUT / "nib_genres.jpg", dpi=130)
    plt.close(fig)
    # direct font-outline check: widths measured on the vector render, not via the extractor
    print(json.dumps(summarise_nib(rows), indent=1))


def summarise_nib(rows):
    out = {}
    for gname in sorted({r["group"] for r in rows}):
        rs = [r for r in rows if r["group"] == gname and np.isfinite(r["r2"]) and r["n"] >= 50]
        if not rs:
            continue
        ph = np.deg2rad([r["phi_deg"] for r in rs])
        wts = np.array([r["n"] for r in rs], float)
        z = np.sum(wts * np.exp(2j * ph)) / wts.sum()
        zr = np.sum(wts * np.exp(2j * np.deg2rad([r["phi_rel_deg"] for r in rs]))) / wts.sum()
        out[gname] = {"sheets": len(rs), "phi_mean_deg": round(float(np.rad2deg(np.angle(z) / 2) % 180), 1),
                      "phi_rel_mean_deg": round(float(np.rad2deg(np.angle(zr) / 2) % 180), 1),
                      "phi_rel_R": round(float(abs(zr)), 2),
                      "phis_rel": [round(r["phi_rel_deg"]) for r in rs],
                      "baselines": [round(r["baseline_deg"]) for r in rs],
                      "phi_R": round(float(abs(z)), 2),
                      "r2_med": round(float(np.median([r["r2"] for r in rs])), 3),
                      "r2_null_med": round(float(np.median([r["r2_null"] for r in rs])), 3),
                      "contrast_med": round(float(np.median([r["contrast"] for r in rs])), 2),
                      "spread_med": round(float(np.nanmedian([r["phi_spread_deg"] for r in rs])), 1),
                      "phis": [round(r["phi_deg"]) for r in rs]}
    (OUT / "nib_summary.json").write_text(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------------------
# stage: render (thickness-gap options)
# ---------------------------------------------------------------------------

def stage_render(a):
    """Compare (a) outline, (b) concentric fill, (c) multipass on a nib-swept
    stroke at plotter scale: 10 px/mm, pen 0.35 mm, nib 3 mm."""
    pxmm = 10.0
    pen = 0.35 * pxmm
    rng = np.random.default_rng(3)
    tiles, rows = [], []
    phi = np.deg2rad(40)
    # a real-hand centreline: the longest shikasta stroke from a sheet the
    # policy allows (exercise); falls back to a synthetic curve
    src = None
    try:
        dd = load_group("shikasta")
        ok = C.filter_generative(dd)
        cands = []
        for k, d in ok.items():
            Wd, Hd = d.size
            for st in d.strokes:
                p = st.points
                m = 0.03 * max(Wd, Hd)
                if (p[:, 0].min() < m or p[:, 1].min() < m or p[:, 0].max() > Wd - m or p[:, 1].max() > Hd - m):
                    continue                      # frame / ruling remnants hug the crop edge
                chord = np.linalg.norm(p[-1] - p[0]) / max(st.length(), 1e-9)
                if chord < 0.85:
                    cands.append((k, st))
        if cands:
            src = max(cands, key=lambda kv: kv[1].length())
    except FileNotFoundError:
        pass
    scenes = []
    c = bn.synth_centreline(rng, length=900, kappa_sd=0.012, corr=90)
    scenes.append(("synthetic centreline", c))
    if src is not None:
        p = src[1].points
        p = (p - p.min(0)) / max(np.ptp(p, axis=0).max(), 1e-9) * 700
        scenes.append((f"shikasta stroke ({src[0]}), refit nib", p))
    for name, c in scenes:
        c = c - c.min(0) + 80
        size = tuple(int(v) for v in (c.max(0) + 80))
        for W_mm in (3.0, 1.5):
            W = W_mm * pxmm
            w0 = 0.25 * pxmm
            geom = bn.sweep_polygon(c, phi, W, w0)
            target = bn.render_mask(geom, size)
            A = bn.outline_paths(geom)
            B = bn.concentric_paths(geom, pen)
            Cc = bn.multipass_paths(c, bn.model_widths(c, phi, W, w0, sigma=W / 2), pen)
            opts = [("ribbon (target)", None, None), ("a outline", A, True), ("b concentric", B, True),
                    ("c multipass", Cc, False)]
            for oname, paths, closed in opts:
                if paths is None:
                    img = target
                    st = {}
                    fid = {}
                else:
                    img = bn.draw_paths(paths, size, pen, closed=closed)
                    st = bn.paths_stats(paths, closed)
                    fid = bn.fidelity(img, target)
                    rows.append({"scene": name, "nib_mm": W_mm, "option": oname, "paths": st["paths"],
                                 "pen_m": round(st["length"] / pxmm / 1000, 3),
                                 **{k: round(v, 3) for k, v in fid.items()}})
                    print(rows[-1], flush=True)
                im = Image.fromarray((img * 255).astype(np.uint8)).convert("RGB")
                im.thumbnail((420, 420))
                lab = oname if not st else f"{oname}: {st['paths']} paths, {st['length'] / pxmm / 1000:.2f} m, IoU {fid['iou']:.2f}"
                tiles.append(label(im, f"nib {W_mm} mm · {lab}"))
    save_jpg(grid(tiles, 4, "width with a 0.35 mm pen: ribbon target | (a) nib outline | (b) concentric inset fill | (c) multipass centreline offsets"),
             OUT / "render_options.jpg")
    (OUT / "render_options.json").write_text(json.dumps(rows, indent=1))


# ---------------------------------------------------------------------------
# stage: panel (hand statistics)
# ---------------------------------------------------------------------------

def _panel_job(args):
    key, path = args
    from gesture import panel
    from gesture.medium import SIGMA_MIN_W
    d = Drawing.load(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fs, _ = panel.features_with_info(d, sigma_min_w=SIGMA_MIN_W)
        fr, _ = panel.features_with_info(d, sigma_min_w=0.0)
    return key, fs, fr


def _texture(d_outline: Drawing, w: float) -> dict:
    """Edge texture of outline contours: lateral residual of each contour
    about its own Gaussian smoothing at 1 line width, in line widths
    (rms, p90), plus corner rounding proxy (fraction of contour with
    |κ|·w > 1)."""
    from scipy.ndimage import gaussian_filter1d
    res, kk = [], []
    for st in d_outline.strokes:
        if st.length() < 20 * w:
            continue
        q, _, _ = bn._resample(np.vstack([st.points, st.points[:1]]), max(w / 4, 0.5))
        q = q[:-1]
        sd = w / max(w / 4, 0.5)
        sm = np.column_stack([gaussian_filter1d(q[:, 0], sd, mode="wrap"), gaussian_filter1d(q[:, 1], sd, mode="wrap")])
        t = np.gradient(sm, axis=0)
        t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
        n = np.column_stack([-t[:, 1], t[:, 0]])
        r = np.sum((q - sm) * n, axis=1) / w
        res.append(r)
        d1 = np.gradient(sm, axis=0); d2 = np.gradient(d1, axis=0)
        k = (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / (np.linalg.norm(d1, axis=1) ** 3 + 1e-12)
        kk.append(np.abs(k) * w)
    if not res:
        return {"tex_rms": np.nan, "tex_p90": np.nan, "tex_sharp": np.nan}
    r = np.concatenate(res)
    k = np.concatenate(kk)
    return {"tex_rms": float(np.sqrt(np.mean(r * r))), "tex_p90": float(np.quantile(np.abs(r), 0.9)),
            "tex_sharp": float(np.mean(k > 1.0))}


def stage_panel(a):
    from gesture.medium import MediumProjector, load_media, load_pairs
    from sklearn.decomposition import PCA
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold

    jobs, labels = [], {}
    for art in ("matisse", "hokusai", "ingres"):
        for p in sorted((ROOT / ".local/gesture/out/extract_hybrid" / art).glob("*.json")):
            jobs.append(((art, p.stem), p))
    for gdir in sorted(p for p in EXT.iterdir() if p.is_dir()):
        for p in sorted(gdir.glob("*.json")):
            if p.name.endswith(".outline.json"):
                continue
            jobs.append(((gdir.name, p.stem), p))
    print(len(jobs), "drawings", flush=True)
    feats = {}
    with ProcessPoolExecutor(JOBS) as ex:
        for key, fs, fr in ex.map(_panel_job, jobs, chunksize=2):
            feats[key] = (fs, fr)
    keys = sorted(feats)
    media = load_media()
    out = {}
    for mode, ix in (("standard", 0), ("raw", 1)):
        names = sorted(set().union(*[feats[k][ix].keys() for k in keys]))
        X = np.array([[feats[k][ix].get(n, np.nan) for n in names] for k in keys])
        grp = np.array([k[0] for k in keys])
        med = np.array([media.get(k, "unknown") if k[0] in ("matisse", "hokusai", "ingres") else "unknown"
                        for k in keys])
        geo = [i for i, n in enumerate(names) if n.split("_", 1)[0] not in ("w", "end")]
        res = {}
        for view, cols in (("geometry", geo), ("with_width", list(range(len(names))))):
            Xv = X[:, cols]
            keepc = ~np.all(np.isnan(Xv), axis=0)
            Xv = Xv[:, keepc]
            if mode == "standard":
                P = MediumProjector(load_pairs()).fit(Xv, grp, med)
                Z = P.transform(Xv)
            else:
                mdn = np.nan_to_num(np.nanmedian(Xv, axis=0))
                Xi = np.where(np.isnan(Xv), mdn, Xv)
                sd = Xi.std(0)
                Z = (Xi - Xi.mean(0)) / np.where(sd > 0, sd, 1)
            Z = np.nan_to_num(Z)
            gl = sorted(set(grp))
            # pairwise AUCs (repeated stratified CV, logistic regression)
            auc = {}
            for i1, g1 in enumerate(gl):
                for g2 in gl[i1 + 1:]:
                    m = np.isin(grp, [g1, g2])
                    y = (grp[m] == g2).astype(int)
                    nmin = min(y.sum(), (1 - y).sum())
                    if nmin < 3:
                        continue
                    k = int(min(5, nmin))
                    sc = []
                    for rep in range(3):
                        pr = np.zeros(len(y))
                        for tr, te in StratifiedKFold(k, shuffle=True, random_state=rep).split(Z[m], y):
                            clf = LogisticRegression(C=0.5, max_iter=4000).fit(Z[m][tr], y[tr])
                            pr[te] = clf.predict_proba(Z[m][te])[:, 1]
                        sc.append(roc_auc_score(y, pr))
                    auc[f"{g1}|{g2}"] = (round(float(np.mean(sc)), 3), int((1 - y).sum()), int(y.sum()))
            # embedding figure
            Zp = PCA(2, random_state=0).fit_transform(Z)
            big = [g for g in gl if (grp == g).sum() >= 3]
            mm = np.isin(grp, big)
            try:
                Zl = LinearDiscriminantAnalysis(n_components=2).fit(Z[mm], grp[mm]).transform(Z)
            except Exception:  # noqa: BLE001
                Zl = Zp
            res[view] = {"auc": auc, "pca": Zp.tolist(), "lda": Zl.tolist()}
        out[mode] = {"keys": [list(k) for k in keys], **res}
    # texture: print vs font from outlines
    tex = []
    for gname in ("print_AL08", "print_AL09", "print_AL04", "print_AL01", "font_amiri", "font_amiritype",
                  "shikasta", "nastaliq", "naskh"):
        gd = EXT / gname
        if not gd.exists():
            continue
        for p in sorted(gd.glob("*.outline.json")):
            od = Drawing.load(p)
            cd = Drawing.load(p.with_name(p.name.replace(".outline.json", ".json")))
            ws = [float(np.median(s.width)) for s in cd.strokes if s.width is not None]
            w = float(np.median(ws)) if ws else 3.0
            tex.append({"group": gname, "id": p.stem.replace(".outline", ""), "w": round(w, 2), **_texture(od, w)})
    out["texture"] = tex
    (OUT / "panel.json").write_text(json.dumps(out, indent=1))
    _panel_figure(out)
    _panel_print(out)


def _panel_figure(out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    keys = [tuple(k) for k in out["standard"]["keys"]]
    grp = np.array([k[0] for k in keys])
    gl = sorted(set(grp))
    cols = {g: c for g, c in zip(gl, ["#AF3029", "#205EA6", "#66800B", "#BC5215", "#5E409D", "#24837B",
                                       "#A02F6F", "#AD8301", "#100F0F", "#6F6E69", "#D14D41", "#4385BE",
                                       "#879A39", "#DA702C", "#8B7EC8", "#3AA99F", "#CE5D97", "#D0A215",
                                       "#575653", "#B7B5AC"] * 2)}
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.6), facecolor="#FFFCF0")
    for ax, (mode, view, emb) in zip(axes, (("standard", "geometry", "pca"), ("standard", "geometry", "lda"),
                                            ("standard", "with_width", "lda"))):
        Z = np.array(out[mode][view][emb])
        for g in gl:
            m = grp == g
            ax.scatter(Z[m, 0], Z[m, 1], s=16 if g in ("matisse", "hokusai", "ingres") else 22,
                       c=cols[g], label=f"{g} ({m.sum()})", alpha=0.8,
                       marker="o" if g in ("matisse", "hokusai", "ingres") else ("s" if g.startswith(("print", "font")) else "^"))
        ax.set_title(f"{mode} preprocessing, {view}, {emb.upper()}", fontsize=9)
        ax.tick_params(labelsize=7)
    axes[-1].legend(fontsize=6, loc="center left", bbox_to_anchor=(1.0, 0.5))
    fig.tight_layout()
    fig.savefig(OUT / "panel_scatter.jpg", dpi=120)
    plt.close(fig)


def _panel_print(out):
    for mode in ("standard", "raw"):
        for view in ("geometry", "with_width"):
            print(f"== {mode} / {view}")
            for k, v in sorted(out[mode][view]["auc"].items()):
                print(f"  {k:32s} {v}")
    tex = out["texture"]
    for g in sorted({t["group"] for t in tex}):
        ts = [t for t in tex if t["group"] == g]
        print(g, len(ts), {k: round(float(np.nanmedian([t[k] for t in ts])), 4) for k in ("w", "tex_rms", "tex_p90", "tex_sharp")})


# ---------------------------------------------------------------------------
# stage: generate (policy-gated)
# ---------------------------------------------------------------------------

def stage_generate(a):
    import gesture.grammar_v6_frozen as gm

    dd = {}
    for genre in a.genres:
        dd.update(load_group(genre))
    allowed = C.filter_generative(dd)
    C.require_generative(list(allowed))          # hard gate: raises on anything restricted
    excluded = sorted(set(dd) - set(allowed))
    print("training sheets:", sorted(allowed), "\nexcluded (measure-only):", excluded, flush=True)
    drawings = [C.pen_strokes(d) for d in allowed.values()]
    print("pen strokes kept:", [d.meta["pen_strokes"] for d in drawings], flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = gm.learn(drawings, name="+".join(a.genres), min_len_w=a.min_len_w)
    print("grammar strokes:", len(g.strokes) if hasattr(g, "strokes") else "?", g.meta, flush=True)
    # nib for rendering: the training sheet whose |sin| fit is best (pooling
    # sheets of different scale/contrast flattens the thick-thin contrast)
    best = None
    for d in drawings:
        r = bn.fit_drawing(d, per_stroke=False)
        ld = gm.long_drawing(d, min_len_w=a.min_len_w)
        if r["sheet"].n >= 1000 and ld.strokes and (best is None or r["sheet"].r2 > best[0].r2):
            best = (r["sheet"], r["w_med"] / ld.ref_length(), d.source)
    nib, w_over_R, nib_src = best
    print("nib from", nib_src, flush=True)
    print("nib", nib.as_dict(), "w/R", w_over_R, flush=True)
    size = (1100, 1100)
    rng = np.random.default_rng(a.seed)
    tiles_line, tiles_nib, gens = [], [], []
    for i in range(6):
        mode = "single" if i < 3 else "contiguous"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            d = gm.generate_drawing(g, rng, size, mode=mode)
        gens.append(d)
        R = d.meta.get("ref_length_gen", float(np.hypot(*size)) * 0.95)
        # rendering scale (a choice, not hand data): the widest nib mark is
        # 1.2 % of the drawing's diagonal; φ and the thick/thin ratio are fitted
        wpx = 0.012 * R / (nib.W + nib.w_min)
        img = Image.new("RGB", size, PAPER)
        dr = ImageDraw.Draw(img)
        for st in d.strokes:
            dr.line([tuple(v) for v in st.points], fill=INK, width=2)
        tiles_line.append(label(img.resize((520, 520), Image.Resampling.LANCZOS), f"{mode} {i % 3 + 1}: centreline"))
        geoms = [bn.sweep_polygon(st.points, nib.phi, nib.W * wpx, nib.w_min * wpx) for st in d.strokes
                 if len(st.points) > 2]
        paths = [p for gg in geoms for p in bn.outline_paths(gg, min_area=wpx * wpx)]
        oimg = bn.draw_paths(paths, size, 1.6, closed=True)
        im2 = Image.fromarray((oimg * 255).astype(np.uint8)).convert("RGB")
        tiles_nib.append(label(im2.resize((520, 520), Image.Resampling.LANCZOS),
                               f"{mode} {i % 3 + 1}: nib outline (a), phi {nib.phi_deg:.0f}"))
        fill = bn.render_mask(geoms, size, ss=2)
        tiles_nib.append(label(Image.fromarray((fill * 255).astype(np.uint8)).convert("RGB").resize((520, 520)),
                               f"{mode} {i % 3 + 1}: swept ribbon (reference)"))
    # real long strokes of one training sheet for comparison
    ref = gm.long_drawing(drawings[0], min_len_w=a.min_len_w)
    pts = np.vstack([s.points for s in ref.strokes])
    f = 1000 / np.ptp(pts, axis=0).max()
    img = Image.new("RGB", size, PAPER)
    dr = ImageDraw.Draw(img)
    for st in ref.strokes:
        dr.line([tuple(v) for v in (st.points - pts.min(0)) * f + 50], fill=INK, width=2)
    real_tile = label(img.resize((520, 520), Image.Resampling.LANCZOS), f"REAL long strokes, {sorted(allowed)[0]}")
    tag = "-".join(a.genres)
    save_jpg(grid(tiles_line[:3] + [real_tile] + tiles_line[3:], 4,
                  f"line studies after the {tag} hand (grammar v6 frozen; trained on {len(drawings)} exercise/document sheets only)"),
             OUT / f"generate_{tag}_lines.jpg")
    save_jpg(grid(tiles_nib, 4, f"line studies after the {tag} hand, rendered with the fitted nib (phi {nib.phi_deg:.0f} deg)"),
             OUT / f"generate_{tag}_nib.jpg")
    # memorisation check
    try:
        dist = gm.nearest_training_distance([s for d in gens for s in d.strokes], g)
        print("nearest-training distance median", float(np.median(dist)), flush=True)
    except Exception as e:  # noqa: BLE001
        print("memorisation check skipped:", e)
    (OUT / f"generate_{tag}.json").write_text(json.dumps({"train": sorted(allowed), "excluded": excluded,
                                                           "nib": nib.as_dict(), "nib_sheet": nib_src, "w_over_R": w_over_R}, indent=1))


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["extract", "outline", "fonts", "synth", "nib", "render", "panel", "generate", "all"])
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--font-px", type=float, default=64.0)
    ap.add_argument("--genres", nargs="*", default=["shikasta"])
    ap.add_argument("--min-len-w", type=float, default=12.0)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    stages = ["extract", "synth", "nib", "render", "panel", "generate"] if a.stage == "all" else [a.stage]
    for s in stages:
        t = time.perf_counter()
        globals()[f"stage_{s}"](a)
        print(f"[{s}] {time.perf_counter() - t:.0f} s", flush=True)


if __name__ == "__main__":
    main()
