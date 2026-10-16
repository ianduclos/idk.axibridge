"""Hybrid and non-human hands (research round 8, 2026-10-16).

    cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.hybrid_hands <stage>

stages:
  extract  — a handful of Marden sheets, one Lichtenberg figure and two
             bubble-chamber prints through extract_hybrid (overlays written)
  learn    — grammars: Marden, Lichtenberg, bubble chamber, shikasta and
             nasta'liq EXERCISE sheets (policy gate: calligraphy.require_generative);
             Matisse / Hokusai / Ingres are the v7 grammars on disk
  panel    — real hands in panel space (standard preprocessing): where Marden sits
  hybrids  — generated sheets for every parent and every hybrid method, panel
             positions (axis t, off-axis ratio, classifier P(B)), the
             "A | hybrid | B" restyle sheets
  drift    — the limb: one line whose hand drifts Matisse -> shikasta -> Lichtenberg
  all

Outputs: .local/gesture/out/hybrid_hands/. Write-up:
tools/gesture/results/hybrid_hands-2026-10-16.md.

POLICY: Arabic material reaches a grammar only through
calligraphy.require_generative (exercise / poetry / document sheets).
Bulaq print pages are content_type "book" (measure-only): they are placed in
panel space but never learned from.
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

from gesture import grammar as gm  # noqa: E402
from gesture import hybrid as hy  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/hybrid_hands"
RES = HERE / "results"
CORPUS = ROOT / ".local/gesture/corpus"
V7 = ROOT / ".local/gesture/out/grammar_v7"
EXH = ROOT / ".local/gesture/out/extract_hybrid"
CAL = ROOT / ".local/gesture/out/calligraphy/extract"
JOBS = 2
PAPER, INK = (0xFF, 0xFC, 0xF0), (0x10, 0x0F, 0x0F)
BLUE, RED, GREEN, ORANGE = (0x43, 0x85, 0xBE), (0xD1, 0x4D, 0x41), (0x87, 0x9A, 0x39), (0xDA, 0x70, 0x2C)
GREY = (0x87, 0x85, 0x80)

# (file, crop fractions x0 y0 x1 y1, invert, max_side)
MARDEN = {
    "moma-102386": ((0.08, 0.06, 0.92, 0.94), False, None),
    "moma-102387": ((0.08, 0.06, 0.92, 0.94), False, None),
    "moma-102388": ((0.08, 0.06, 0.92, 0.94), False, None),
    "moma-96607": ((0.08, 0.06, 0.92, 0.94), False, None),
    "moma-35286": ((0.03, 0.03, 0.97, 0.90), False, None),
    "moma-37245": ((0.04, 0.03, 0.96, 0.93), False, None),
    "moma-69038": ((0.12, 0.15, 0.88, 0.82), False, None),
    "moma-69053": ((0.12, 0.15, 0.88, 0.82), False, None),
}
EARTH = {
    "lichtenberg-02": ((0.03, 0.03, 0.97, 0.97), True, None),
    "bc-04": ((0.03, 0.03, 0.97, 0.97), False, 2400),
    "bc-06": ((0.03, 0.03, 0.97, 0.97), False, 2400),
}
# dense figures (ink cover ≫ a line drawing's): calligraphy's Otsu + wide paper window
EXTRACT_KW = {"lichtenberg-02": {"method": "otsu", "paper_window_frac": 0.08, "spur_factor": 2.5,
                                 "crop_to_plate": False, "drop_frames": False}}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_crop(path: Path, crop, invert, max_side):
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as im:
        im = im.convert("L")
        W, H = im.size
        x0, y0, x1, y1 = crop
        im = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
        if max_side and max(im.size) > max_side:
            f = max_side / max(im.size)
            im = im.resize((int(im.size[0] * f), int(im.size[1] * f)), Image.Resampling.LANCZOS)
        g = np.asarray(im, dtype=np.float64) / 255.0
    return (1.0 - g) if invert else g


def _extract_job(args):
    name, path, crop, invert, max_side, group = args
    from gesture import extract_hybrid
    from gesture.extract import debug_overlay
    t = time.perf_counter()
    g = _load_crop(path, crop, invert, max_side)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = extract_hybrid.extract(g, source=name, **EXTRACT_KW.get(name, {}))
    od = OUT / "extract" / group
    od.mkdir(parents=True, exist_ok=True)
    d.save(od / f"{name}.json")
    Image.fromarray(debug_overlay(g, d, max_side=1400)).save(od / f"{name}.jpg", quality=80)
    L = [s.length() for s in d.strokes]
    return {"name": name, "group": group, "strokes": len(d.strokes),
            "w_px": round(float(d.meta.get("line_width_px", 0)), 2),
            "med_len_w": round(float(np.median(L) / max(d.meta.get("line_width_px", 1), 1e-9)), 1) if L else 0,
            "secs": round(time.perf_counter() - t, 1)}


def load_dir(d: Path) -> dict[str, Drawing]:
    return {p.stem: Drawing.load(p) for p in sorted(d.glob("*.json")) if not p.name.endswith(".outline.json")}


def render(d: Drawing, size, lw=2.2, colors=None, scale=1.0) -> Image.Image:
    img = Image.new("RGB", size, PAPER)
    dr = ImageDraw.Draw(img)
    for i, st in enumerate(d.strokes):
        if len(st.points) < 2:
            continue
        c = colors[i] if colors is not None else INK
        if isinstance(c, (list, np.ndarray)) and len(c) == len(st.points) - 1:   # per-segment colours
            P = st.points * scale
            for j in range(len(P) - 1):
                dr.line([tuple(P[j]), tuple(P[j + 1])], fill=tuple(int(v) for v in c[j]), width=int(round(lw)))
        else:
            dr.line([tuple(v) for v in st.points * scale], fill=c, width=int(round(lw)), joint="curve")
    return img


def fit_drawing(d: Drawing, size, margin=30) -> Drawing:
    P = np.vstack([s.points for s in d.strokes if len(s.points)])
    lo, hi = P.min(0), P.max(0)
    k = min((size[0] - 2 * margin) / max(hi[0] - lo[0], 1e-9), (size[1] - 2 * margin) / max(hi[1] - lo[1], 1e-9))
    off = margin + 0.5 * (np.array(size) - 2 * margin - k * (hi - lo))
    return Drawing([Stroke((s.points - lo) * k + off, width=s.width, meta=s.meta) for s in d.strokes],
                   source=d.source, size=size, meta=d.meta)


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:       # Pillow < 10.1
        return ImageFont.load_default()


def label(img, text, sub=None, size=None):
    img = img.copy()
    dr = ImageDraw.Draw(img)
    fs = size or max(14, img.size[0] // 30)
    dr.text((10, 8), text, fill=INK, font=_font(fs))
    if sub:
        dr.text((10, 12 + fs), sub, fill=GREY, font=_font(int(fs * 0.8)))
    return img


def grid(tiles, cols, title, tile=(380, 440), pad=8, top=40):
    rows = (len(tiles) + cols - 1) // cols
    W, H = tile
    sheet = Image.new("RGB", (cols * W + (cols + 1) * pad, rows * H + (rows + 1) * pad + top), (0xF2, 0xF0, 0xE5))
    ImageDraw.Draw(sheet).text((10, 8), title, fill=INK, font=_font(max(14, top // 2)))
    for i, t in enumerate(tiles):
        if t is None:
            continue
        r, c = divmod(i, cols)
        sheet.paste(t.resize(tile, Image.Resampling.LANCZOS), (pad + c * (W + pad), top + pad + r * (H + pad)))
    return sheet


def save_jpg(img: Image.Image, path: Path, max_kb=900, max_side=2600):
    img = img.copy()
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    for q in (88, 82, 75, 68, 60, 50):
        img.save(path, quality=q)
        if path.stat().st_size <= max_kb * 1024:
            break


# ---------------------------------------------------------------------------
# stage: extract
# ---------------------------------------------------------------------------

def stage_extract(a):
    jobs = [(n, CORPUS / "artists/brice_marden" / f"{n}.jpg", *v, "marden") for n, v in MARDEN.items()]
    if a.only:
        jobs = []
    jobs += [(n, CORPUS / "earth" / n / f"{n}.jpg", *v, "lichtenberg" if n.startswith("lich") else "bubble")
             for n, v in EARTH.items() if not a.only or n in a.only.split(",")]
    rows = []
    with ProcessPoolExecutor(JOBS) as ex:
        for r in ex.map(_extract_job, jobs):
            print(r, flush=True)
            rows.append(r)
    (OUT / "extract" / "summary.json").write_text(json.dumps(rows, indent=1))


# ---------------------------------------------------------------------------
# stage: learn
# ---------------------------------------------------------------------------

def _calligraphy_drawings(genre: str) -> tuple[list[Drawing], list[str], list[str]]:
    from gesture import calligraphy as C
    dd = load_dir(CAL / genre)
    allowed = C.filter_generative(dd)
    C.require_generative(list(allowed))          # hard gate
    return [C.pen_strokes(d) for d in allowed.values()], sorted(allowed), sorted(set(dd) - set(allowed))


def stage_learn(a):
    (OUT / "grammars").mkdir(parents=True, exist_ok=True)
    meta = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for genre, key in (("shikasta", "shikasta"), ("nastaliq", "nastaliq")):
            ds, tr, ex = _calligraphy_drawings(genre)
            g = gm.learn(ds, name=key, min_len_w=12)
            g.save(OUT / "grammars" / f"{key}.json")
            meta[key] = {"train": tr, "excluded_measure_only": ex, "strokes": len(g.strokes), "min_len_w": 12}
            print(key, meta[key], flush=True)
        for group, min_len_w in (("marden", 12), ("lichtenberg", 12), ("bubble", 12)):
            dd = load_dir(OUT / "extract" / group)
            if group == "bubble":
                dd = {k: v for k, v in dd.items() if k != "bc-04"}   # bc-04 extracts as 16 blobs
            ds = list(dd.values())
            if group in ("lichtenberg", "bubble"):
                ds = [t for d in ds for t in hy.tile_drawing(d, 2, 2)]   # one figure → quadrant "sheets"
            g = gm.learn(ds, name=group, min_len_w=min_len_w)
            g.save(OUT / "grammars" / f"{group}.json")
            meta[group] = {"train": sorted(dd), "strokes": len(g.strokes), "min_len_w": min_len_w,
                           "drawings": len(ds)}
            print(group, meta[group], flush=True)
    (OUT / "grammars" / "meta.json").write_text(json.dumps(meta, indent=1))


def grammars() -> dict[str, gm.Grammar]:
    G = {a: gm.Grammar.load(V7 / f"grammar_{a}.json") for a in ("matisse", "hokusai", "ingres")}
    for k in ("shikasta", "nastaliq", "marden", "lichtenberg", "bubble"):
        p = OUT / "grammars" / f"{k}.json"
        if p.exists():
            G[k] = gm.Grammar.load(p)
    return G


# ---------------------------------------------------------------------------
# stage: panel (real hands)
# ---------------------------------------------------------------------------

def _feat_job(args):
    key, path_or_d = args
    from gesture import medium, panel
    d = Drawing.load(path_or_d) if isinstance(path_or_d, (str, Path)) else path_or_d
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if len(d.strokes) < 2:
            return key, {}
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W)
    return key, f


def real_items():
    items = []
    for art in ("matisse", "hokusai", "ingres"):
        for p in sorted((EXH / art).glob("*.json")):
            items.append(((art, p.stem), p))
    for grp in ("shikasta", "nastaliq", "print_AL08", "print_AL09"):
        for p in sorted((CAL / grp).glob("*.json")):
            if not p.name.endswith(".outline.json"):
                items.append(((grp, p.stem), p))
    for grp in ("marden", "lichtenberg", "bubble"):
        for p in sorted((OUT / "extract" / grp).glob("*.json")):
            items.append(((grp, p.stem), p))
    return items


def stage_panel(a):
    items = real_items()
    feats = {}
    with ProcessPoolExecutor(JOBS) as ex:
        for k, f in ex.map(_feat_job, items, chunksize=2):
            feats["|".join(k)] = f
    (OUT / "panel_real.json").write_text(json.dumps(feats))
    print(len(feats), "real drawings measured", flush=True)
    rep = hy.place_groups(feats, focus="marden")
    (OUT / "panel_real_report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1)[:3000])


# ---------------------------------------------------------------------------
# stage: hybrids
# ---------------------------------------------------------------------------

PAIRS = [("matisse", "shikasta"), ("hokusai", "nastaliq"), ("ingres", "matisse"), ("marden", "shikasta"),
         ("matisse", "lichtenberg")]
METHODS = ("pooled", "mixture", "crossover", "interp")
SIZE = (1000, 1200)


def _gen_job(args):
    key, A, B, method, t, seed = args
    G = grammars()
    g = G[A] if method == "parentA" else G[B] if method == "parentB" else hy.make_hybrid(G[A], G[B], method, t=t, seed=seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            d = gm.generate_drawing(g, np.random.default_rng(seed), SIZE)
        except Exception as e:  # noqa: BLE001
            return key, None, repr(e)
    if len(d.strokes) < 2:
        return key, None, "empty"
    from gesture import medium, panel
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, _ = panel.features_with_info(d, sigma_min_w=medium.SIGMA_MIN_W)
    d.save(OUT / "sheets" / f"{key}.json")
    return key, f, None


def stage_hybrids(a):
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    jobs = []
    for A, B in PAIRS:
        for rep in range(a.n):
            seed = 1000 + rep
            for m in ("parentA", "parentB") + METHODS:
                jobs.append((f"{A}__{B}__{m}__{rep}", A, B, m, 0.5, seed))
    if a.only:
        jobs = [j for j in jobs if any(o in j[0] for o in a.only.split(","))]
    done = {}
    pf = OUT / "panel_gen.json"
    if pf.exists() and not a.fresh:
        done = json.loads(pf.read_text())
    jobs = [j for j in jobs if j[0] not in done]
    print(len(jobs), "sheets to generate", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(JOBS) as ex:
        for i, (k, f, err) in enumerate(ex.map(_gen_job, jobs)):
            if err:
                print("FAIL", k, err, flush=True)
                continue
            done[k] = f
            if i % 20 == 0:
                print(i, k, round(time.time() - t0), flush=True)
                pf.write_text(json.dumps(done))
    pf.write_text(json.dumps(done))
    real = json.loads((OUT / "panel_real.json").read_text())
    rep = hy.hybrid_positions(done, real, PAIRS, ("parentA", "parentB") + METHODS)
    (OUT / "hybrid_positions.json").write_text(json.dumps(rep, indent=1))
    print(hy.positions_table(rep))
    (OUT / "hybrid_positions.md").write_text(hy.positions_table(rep))


def stage_sheets(a):
    """Labelled sheets: A | hybrids | B, population tiles and restyle on one structure."""
    G = grammars()
    rng_seed = 20261016
    # 1. population: one row per pair, columns parentA, methods, parentB
    tiles = []
    cols = ("parentA",) + METHODS + ("parentB",)
    for A, B in PAIRS:
        for m in cols:
            p = OUT / "sheets" / f"{A}__{B}__{m}__0.json"
            if not p.exists():
                tiles.append(None)
                continue
            d = Drawing.load(p)
            name = A if m == "parentA" else B if m == "parentB" else f"{A} x {B}: {m}"
            tiles.append(label(render(fit_drawing(d, SIZE), SIZE, lw=2.4), name))
    save_jpg(grid(tiles, len(cols), "Hybrid hands — each row: parent A | pooled k-NN | token mixture | "
                  "segment crossover | interpolated tokens | parent B (grammar v7 contiguous sheets, seed 1000)",
                  tile=(300, 360)), OUT / "hybrid-population.jpg")
    # 2. restyle: one structure in every hand
    struct = hy.structure_from(Drawing.load(EXH / "matisse" / f"{a.structure}.json"))
    R0 = struct.ref_length()
    struct = Drawing([s for s in struct.strokes            # drop the plate-mark frame (long, dead straight)
                      if not (s.length() > 0.15 * R0 and np.linalg.norm(s.points[-1] - s.points[0]) > 0.97 * s.length())
                      and not (s.length() > 0.5 * R0)], source=struct.source, size=struct.size)

    def zoom(d, f=2.2):
        c = np.array(SIZE) / 2
        return Drawing([Stroke((st.points - c) * f + c) for st in d.strokes], source=d.source, size=SIZE)
    tiles = [label(render(fit_drawing(struct, SIZE), SIZE, lw=2.4), "STRUCTURE (whole)", f"long strokes of matisse/{a.structure}"),
             label(render(zoom(fit_drawing(struct, SIZE)), SIZE, lw=2.6), "STRUCTURE", "centre detail, x2.2")]
    for A, B in PAIRS:
        row = []
        for nm, g in ((A, G[A]), (f"{A} x {B} (mixture .5)", hy.make_hybrid(G[A], G[B], "mixture", t=0.5)),
                      (f"{A} x {B} (interp .5)", hy.make_hybrid(G[A], G[B], "interp", t=0.5)), (B, G[B])):
            d = hy.restyle_drawing(struct, g, np.random.default_rng(rng_seed), amount=1.0)
            row.append(label(render(zoom(fit_drawing(d, SIZE)), SIZE, lw=2.6), nm, "centre detail, x2.2"))
        tiles += row
    tiles = tiles[:2] + [None] * 2 + tiles[2:]
    save_jpg(grid(tiles, 4, f"One structure redrawn: parent A | mixture | interpolation | parent B "
                  f"(restyle: coarse path kept, fine turning from the hand)", tile=(330, 396)),
             OUT / "hybrid-restyle.jpg")


# ---------------------------------------------------------------------------
# stage: drift (the limb)
# ---------------------------------------------------------------------------

def stage_drift(a):
    G = grammars()
    route = [x for x in a.route.split(",")]
    hands = [G[r] for r in route]
    tiles = []
    meta = []
    for i in range(a.n_drift):
        rng = np.random.default_rng(7000 + i)
        st, info = hy.drift_line(hands, rng, total=a.total, mode=a.drift_mode, size=SIZE, chunk=a.chunk, context=a.context)
        d = Drawing([st], source="drift", size=SIZE)
        dd = fit_drawing(d, SIZE)
        u = np.asarray(st.meta["u"])
        cols = hy.route_colours(u[:-1], len(route), [BLUE, RED, GREEN, ORANGE])
        img_c = render(dd, SIZE, lw=2.4, colors=[cols])
        img_k = render(dd, SIZE, lw=2.6)
        tiles += [label(img_k, f"drift {i + 1}: " + " -> ".join(route), f"{a.drift_mode}, {a.total:.0f} R of line"),
                  label(img_c, "same line, coloured by hand weight", " / ".join(
                      f"{n}={c}" for n, c in zip(route, ("blue", "red", "green", "orange"))))]
        meta.append(info)
    save_jpg(grid(tiles, 4, f"The limb: one line whose hand drifts {' -> '.join(route)} "
                  f"(hand weight moves along the line's arc length)", tile=(420, 504)),
             OUT / f"drift-{a.drift_mode}{a.tag}-{'-'.join(route)}.jpg")
    (OUT / f"drift-{a.drift_mode}{a.tag}-{'-'.join(route)}.json").write_text(json.dumps(meta, indent=1))
    # token statistics along the line vs the parents' own levels
    if a.trace:
        drift_trace(hands, route, a)


def drift_trace(hands, route, a, n_win=20):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = []
    for i in range(a.trace):
        st, _ = hy.drift_line(hands, np.random.default_rng(9000 + i), total=a.total, mode=a.drift_mode, size=SIZE, chunk=a.chunk, context=a.context)
        rows.append(hy.window_stats(st.meta["tokens"], n_win))
    ref = {n: hy.hand_stats(g) for n, g in zip(route, hands)}
    keys = (("corners_per_R", "corner tokens per R"), ("seg_q50", "median segment length (R)"),
            ("absk_q50", "median |kappa| x R"))
    cols = ["#4385BE", "#D14D41", "#879A39", "#DA702C"]
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6), facecolor="#FFFCF0")
    u = (np.arange(n_win) + 0.5) / n_win
    out = {"route": route, "ref": ref, "u": u.tolist()}
    for j, (k, t) in enumerate(keys):
        M = np.array([[r[k] for r in row] for row in rows], float)
        med = np.nanmedian(M, 0)
        q1, q3 = np.nanquantile(M, .25, 0), np.nanquantile(M, .75, 0)
        A = ax[j]
        A.set_facecolor("#FFFCF0")
        A.fill_between(u, q1, q3, color="#B7B5AC", alpha=.5, lw=0)
        A.plot(u, med, color="#100F0F", lw=1.8, label="drift line (median, IQR)")
        for c, n in zip(cols, route):
            A.axhline(ref[n][k], color=c, ls="--", lw=1.2, label=f"{n} (training)")
        A.set_title(t, fontsize=10)
        A.set_xlabel("position along the line (0 = start)")
        out[k] = med.tolist()
        for x in np.linspace(0, 1, len(route)):
            A.axvline(x, color="#DAD8CE", lw=.8, zorder=0)
    ax[0].legend(fontsize=7, frameon=False)
    fig.suptitle(f"Drift {' -> '.join(route)} ({a.drift_mode}): token statistics along {a.trace} lines, "
                 f"20 windows; dashed = each parent's training level", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / f"drift-trace-{a.drift_mode}{a.tag}-{'-'.join(route)}.jpg", dpi=110)
    (OUT / f"drift-trace-{a.drift_mode}{a.tag}-{'-'.join(route)}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("ref",)}, indent=1))


def stage_figures(a):
    """Marden among the real hands (PCA of standard-preprocessed panel)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rep = json.loads((OUT / "panel_real_report.json").read_text())
    pca = rep["pca"]
    col = {"matisse": "#D14D41", "hokusai": "#4385BE", "ingres": "#879A39", "shikasta": "#DA702C",
           "nastaliq": "#CE5D97", "print_AL08": "#878580", "print_AL09": "#B7B5AC", "marden": "#100F0F",
           "lichtenberg": "#8B7EC8", "bubble": "#3AA99F"}
    fig, ax = plt.subplots(figsize=(8, 6.4), facecolor="#FFFCF0")
    ax.set_facecolor("#FFFCF0")
    for g, c in col.items():
        P = np.array([v for k, v in pca.items() if k.split("|")[0] == g])
        if not len(P):
            continue
        big = g in ("marden", "lichtenberg", "bubble")
        ax.scatter(P[:, 0], P[:, 1], s=60 if big else 22, c=c, marker="*" if big else "o",
                   label=f"{g} ({len(P)})", alpha=.9 if big else .6, edgecolors="none")
        if g == "marden":
            for k, v in pca.items():
                if k.startswith("marden|"):
                    ax.annotate(k.split("|")[1].replace("moma-", ""), v, fontsize=7, color="#403E3C",
                                xytext=(3, 3), textcoords="offset points")
    ax.legend(fontsize=8, frameon=False, loc="best")
    auc = rep["auc"]
    ax.set_title("Real hands in panel space (standard preprocessing, geometry only; PCA 1-2)\n"
                 "Marden vs: " + ", ".join(f"{k} {v:.2f}" for k, v in auc.items() if v == v) + " (CV AUC)",
                 fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "marden-panel.jpg", dpi=110)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--only", default="")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--structure", default="KKS13418_3")
    ap.add_argument("--route", default="matisse,shikasta,lichtenberg")
    ap.add_argument("--total", type=float, default=6.0)
    ap.add_argument("--n-drift", type=int, default=4)
    ap.add_argument("--drift-mode", default="mixture")
    ap.add_argument("--trace", type=int, default=0)
    ap.add_argument("--chunk", type=float, default=0.0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--context", default="kappa")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    stages = {"extract": stage_extract, "learn": stage_learn, "panel": stage_panel, "hybrids": stage_hybrids,
              "sheets": stage_sheets, "drift": stage_drift, "figures": stage_figures}
    if a.stage == "all":
        for s in ("extract", "learn", "panel", "hybrids", "sheets", "drift"):
            stages[s](a)
    else:
        stages[a.stage](a)


if __name__ == "__main__":
    main()
