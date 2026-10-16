"""Earth and physics lines → structures, data-born regime fields, hands; and
the physics lines measured as if they were hands.

results/earth_lines-2026-10-16.md. Library: gesture/earth_lines.py.

Run from the repo root:
    .local/gesture/.venv/bin/python -m tools.gesture.experiments.earth_lines extract
    .local/gesture/.venv/bin/python -m tools.gesture.experiments.earth_lines structures
    .local/gesture/.venv/bin/python -m tools.gesture.experiments.earth_lines sheets
    .local/gesture/.venv/bin/python -m tools.gesture.experiments.earth_lines panel

  extract     scans + GRWL windows → .local/gesture/out/earth_lines/{scan_,river_}*.json
  structures  the four sheet structures, fitted, hosts attached, + figure
  sheets      structure × field (data-born vs preset) × hand → population sheets
  panel       the limb: physics lines in the 74-feature panel next to the
              artists and calligraphy hands (standard preprocessing)
≤ 2 worker processes.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import earth_lines as el  # noqa: E402
from gesture import regime_field as rf  # noqa: E402
from gesture.core import Drawing  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / ".local/gesture/out/earth_lines"
RESULTS = Path(__file__).resolve().parents[1] / "results"
JOBS = 2
SIZE = (840, 1200)
PAPER = (255, 252, 240)
INK = (16, 15, 15)
BLUE, RED, GREEN, ORANGE = (0x43, 0x85, 0xBE), (0xD1, 0x4D, 0x41), (0x87, 0x9A, 0x39), (0xDA, 0x70, 0x2C)

# --- sources ---------------------------------------------------------------

RIVERS = {   # name: (tile, bbox lon_min, lat_min, lon_max, lat_max)
    "ucayali-maranon": ("SB18", (-75.4, -6.3, -73.6, -4.5)),
    "purus": ("SB20", (-65.2, -7.3, -63.6, -5.4)),
    "ucayali": ("SB18", (-75.3, -7.9, -74.6, -6.3)),
    "solimoes-anabranch": ("SA20", (-65.1, -3.4, -63.6, -1.9)),
    "jurua": ("SB19", (-70.0, -7.6, -68.4, -6.6)),
    "madeira": ("SC20", (-65.0, -10.0, -63.5, -8.5)),
    "purus-upper": ("SC20", (-66.0, -9.5, -64.6, -8.0)),
    "ucayali-south": ("SC18", (-75.0, -10.5, -73.8, -8.5)),
}

# the same river at three window sizes (half-width in degrees): is the river
# measured as a hand only at one scale? (results §4)
ZOOM = {"purus": ("SB20", (-64.1, -5.6)), "ucayali": ("SB18", (-74.95, -7.1))}
ZOOM_HALF = (0.4, 0.2, 0.1)

SCANS = {   # name: (class, kwargs)
    "bc-03": ("bubble", dict(invert=True)), "bc-04": ("bubble", {}), "bc-06": ("bubble", dict(crop=(0, 0, 1, 0.8))),
    "bc-07": ("bubble", dict(invert=True, crop=(0, 0.1, 1, 0.95))),
    "bc-10": ("bubble", dict(invert=True, crop=(0.45, 0.05, 1, 0.95))),
    "bc-11": ("bubble", dict(invert=True, crop=(0, 0, 0.7, 1.0))), "bc-14": ("bubble", dict(invert=True)),
    "lichtenberg-01": ("discharge", dict(invert=True, channel="max", crop=(0.27, 0.12, 0.75, 0.86))),
    "lichtenberg-05": ("discharge", dict(invert=True, channel="max", crop=(0.2, 0.2, 0.9, 0.85))),
    "lightning-01": ("discharge", dict(invert=True, channel="max")),
    "lightning-02": ("discharge", dict(invert=True, channel="max")),
    "lightning-06": ("discharge", dict(invert=True, channel="max")),
    "slime-trails-forty-years": ("animal", dict(invert=True, crop=(0.15, 0.15, 0.75, 0.75))),
    "insect-02": ("animal", dict(crop=(0.3, 0.0, 1.0, 0.8))),
    "insect-03": ("animal", dict(crop=(0.08, 0.15, 0.48, 0.55))),
}


def _scan_job(name):
    cls, kw = SCANS[name]
    kw = dict(kw)
    ms = kw.pop("max_side", 1400)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = el.scan_structure(next((el.EARTH / name).glob("*.jpg")), max_side=ms, **kw)
    d = Drawing(d.strokes, d.source, d.size, {**d.meta, "class": cls})
    d.save(OUT / f"scan_{name}.json")
    return name, len(d.strokes)


def cmd_extract(a):
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (tile, bb) in RIVERS.items():
        d = el.grwl_window(tile, bb, px=1200)
        d = Drawing(d.strokes, d.source, d.size, {**d.meta, "class": "river"})
        d.save(OUT / f"river_{name}.json")
        print("river", name, len(d.strokes), d.size, flush=True)
    cmd_zoom(a)
    with ProcessPoolExecutor(JOBS) as ex:
        for name, n in ex.map(_scan_job, list(SCANS)):
            print("scan", name, n, flush=True)


def cmd_zoom(a):
    for name, (tile, (cx, cy)) in ZOOM.items():
        for h in ZOOM_HALF:
            d = el.grwl_window(tile, (cx - h, cy - h, cx + h, cy + h), px=1200, min_len_m=300.0)
            d = Drawing(d.strokes, d.source, d.size, {**d.meta, "class": "river-zoom"})
            d.save(OUT / f"zoom_{name}-{h:g}.json")
            print("zoom", name, h, len(d.strokes), flush=True)


# --- the four sheet structures ----------------------------------------------

def _river_sheet(name, keep=90):
    d = Drawing.load(OUT / f"river_{name}.json")
    d = el.prune(d, max_strokes=keep)
    return el.with_hosts(el.fit_to_sheet(d, SIZE))


def _scan_sheet(name, keep=80, min_len_frac=0.02):
    d = Drawing.load(OUT / f"scan_{name}.json")
    d = el.prune(d, max_strokes=keep, min_len_frac=min_len_frac)
    return el.with_hosts(el.fit_to_sheet(d, SIZE))


def structures() -> dict[str, tuple[Drawing, str, list]]:
    """name → (fitted structure, data label, per-point data values)."""
    out = {}
    for rn in ("ucayali-maranon", "purus"):
        d = _river_sheet(rn)
        out[f"river:{rn}"] = (d, "channel width", el.width_values(d))
    d = _scan_sheet("lichtenberg-01")
    out["lichtenberg-01"] = (d, "discharge width", el.width_values(d))
    d = _scan_sheet("bc-14", keep=90, min_len_frac=0.015)
    out["bubble:bc-14"] = (d, "curl radius (energy loss)", el.curl_values(d, sigma_frac=CURL_SIGMA))
    return out


# levels: rivers — the quantiles put the tributaries in wire and let the main
# stem straddle nib / mass as its width changes; curl — most track length is
# near-straight, so only the top of |κ| (spirals) pools.
DATA_Q = {"river": (0.6, 0.9), "lichtenberg": (0.5, 0.85), "bubble": (0.7, 0.9)}


CURL_SIGMA = 0.010        # κ smoothing for tracks: × sheet diagonal (dotted bubbles need it)
# bubble levels are absolute: radius of curvature < 8 % of the sheet width
# pools to mass, < 25 % is nib (a spiralling, slowing particle), else wire
CURL_LEVELS = (1 / (0.25 * SIZE[0]), 1 / (0.08 * SIZE[0]))


def data_field_for(name, d, vals):
    kind = name.split(":")[0].split("-")[0]
    if kind == "bubble":
        return el.data_field(d, vals, levels=CURL_LEVELS, soft=0.35, smooth=6.0, reach=0.02, name=name)
    return el.data_field(d, vals, q=DATA_Q[kind], soft=0.35, smooth=3.0, reach=0.02, name=name)


def preset_field(kind, d, seed):
    return rf.PRESETS[kind](d, seed, SIZE[1] / SIZE[0])


# --- drawing helpers ---------------------------------------------------------

def draw_structure(d: Drawing, r_pt=None, scale=0.5):
    """Centrelines at their width; coloured by data regime when r_pt given
    (black = wire, blue = nib, red = mass)."""
    from PIL import Image, ImageDraw
    W, H = d.size
    im = Image.new("RGB", (int(W * scale), int(H * scale)), PAPER)
    dr = ImageDraw.Draw(im)
    k = 0
    for s in d.strokes:
        p = s.points * scale
        w = s.width if s.width is not None else np.ones(len(p))
        for i in range(len(p) - 1):
            col = INK
            if r_pt is not None:
                r = r_pt[k + i]
                col = INK if r < 0.5 else (BLUE if r < 1.5 else RED)
            dr.line([tuple(p[i]), tuple(p[i + 1])], fill=col, width=max(1, int(round(w[i] * scale))))
        k += len(s)
    return np.asarray(im)


def field_tint(f, d, scale=0.5):
    from experiments.regime_compose import render  # noqa: F401 (uses the same tint)
    g = f.raster((int(d.size[1] * scale) // 2, int(d.size[0] * scale) // 2)) / 2.0
    from PIL import Image
    paper = np.array(PAPER, float)
    a1 = np.clip(g * 2, 0, 1)[..., None]
    a2 = np.clip(g * 2 - 1, 0, 1)[..., None]
    col = paper * (1 - 0.35 * a1) + np.array(BLUE) * 0.35 * a1
    col = col * (1 - 0.45 * a2) + np.array(RED) * 0.45 * a2
    return np.asarray(Image.fromarray(col.astype(np.uint8)).resize((int(d.size[0] * scale), int(d.size[1] * scale))))


def label(arr, text):
    from experiments.regime_compose import label as lab
    return lab(np.ascontiguousarray(arr), text)


def grid(cells, ncol, path, max_kb=900):
    from experiments.regime_compose import grid as g
    g(cells, ncol, path, max_kb=max_kb)


def title_strip(width, text, h=26):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (width, h), (0xF2, 0xF0, 0xE5))
    ImageDraw.Draw(im).text((6, 6), text, fill=INK)
    return np.asarray(im)


def stack(rows):
    w = max(r.shape[1] for r in rows)
    pad = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=200) for r in rows]
    return np.vstack(pad)


def save_jpg(arr, path, max_kb=900, max_side=2600):
    from PIL import Image
    im = Image.fromarray(arr)
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    q = 85
    while True:
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024 or q <= 40:
            break
        q -= 7
    print("wrote", path, f"{path.stat().st_size / 1024:.0f} KB", flush=True)


# --- structures figure + agreement numbers -----------------------------------

def _agreement(d, r_data, seed=3):
    """How much a data-born field says something the presets don't:
    Spearman ρ between data r and preset r at the structure's own points."""
    from scipy.stats import spearmanr
    pts = np.vstack([s.points for s in d.strokes])
    res = {}
    for k in ("strahler", "trunk"):
        rp = preset_field(k, d, seed).at_px(pts, d.size)
        rho = spearmanr(r_data, rp).statistic if np.std(rp) > 0 else float("nan")
        res[k] = {"rho": round(float(rho), 3), "share_mass": round(float(np.mean(rp >= 1.5)), 3),
                  "share_nib": round(float(np.mean((rp >= 0.5) & (rp < 1.5))), 3)}
    res["data"] = {"share_mass": round(float(np.mean(r_data >= 1.5)), 3),
                   "share_nib": round(float(np.mean((r_data >= 0.5) & (r_data < 1.5))), 3)}
    # along-line switching: regime changes per stroke (data vs strahler)
    return res


def cmd_structures(a):
    rows, rec = [], {}
    for name, (d, lab, vals) in structures().items():
        f, r_pt = data_field_for(name, d, vals)
        cells = [label(draw_structure(d), f"{name}: raw structure ({len(d.strokes)} lines, width drawn)"),
                 label(draw_structure(d, r_pt), f"data regime: {lab} → wire / nib(blue) / mass(red)")]
        for k in ("strahler", "trunk"):
            pf = preset_field(k, d, 3)
            pts = np.vstack([s.points for s in d.strokes])
            cells.append(label(draw_structure(d, pf.at_px(pts, d.size)), f"preset field '{k}' on the same lines"))
        rows.append(np.hstack(cells))
        rec[name] = {"n": len(d.strokes), "levels": f.meta["levels"], **_agreement(d, r_pt)}
        d.save(OUT / f"sheet_{name.replace(':', '_')}.json")
        print(name, json.dumps(rec[name]), flush=True)
    save_jpg(stack([title_strip(rows[0].shape[1], "Earth/physics structures. Colour = regime the field assigns "
                                "to each point: black wire, blue nib, red mass. Col 2 is born from the data; "
                                "cols 3-4 are regime_field presets.")] + rows),
             RESULTS / "earth_lines-structures.jpg")
    (OUT / "structures.json").write_text(json.dumps(rec, indent=1))


# --- sheets -----------------------------------------------------------------

HANDS = ("hokusai", "matisse", "shikasta")


def _compose_job(spec):
    name, field_kind, hand, seed = spec
    d = Drawing.load(OUT / f"sheet_{name.replace(':', '_')}.json")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if field_kind == "data":
            vals = el.curl_values(d, sigma_frac=CURL_SIGMA) if name.startswith("bubble") else el.width_values(d)
            f, _ = data_field_for(name, d, vals)
        else:
            f = field_kind
        t = time.perf_counter()
        c = rf.compose(seed, SIZE, structure=d, field=f, hands=hand, signs=4, amount=0.5,
                       label=f"{name}/{field_kind}/{hand}")
        sec = time.perf_counter() - t
    from experiments.regime_compose import render
    img = render(c, 0.5)
    hat = rf.hatching_families(c.polylines, max_len=0.06 * SIZE[1], solid_gap=1.25 * c.meta["pen_px"])
    sw = _switches(c)
    rec = {"name": name, "field": field_kind, "hand": hand, "seed": seed, "sec": round(sec, 1),
           "share": c.meta["regime_share"], "switches_per_line": sw, "n_polylines": len(c.polylines),
           "hatching_families": len(hat) if isinstance(hat, list) else hat}
    return spec, img, rec


def _switches(c):
    """Mean number of regime changes (line↔nib↔mass, at 0.5 / 1.5) per
    rendered centreline: how often a line *becomes* something else."""
    n = []
    for r in c.regimes:
        if len(r) < 2:
            continue
        lev = np.digitize(r, [0.5, 1.5])
        n.append(int(np.sum(lev[1:] != lev[:-1])))
    return round(float(np.mean(n)), 2) if n else 0.0


def cmd_sheets(a):
    names = list(json.loads((OUT / "structures.json").read_text()))
    specs = []
    for name in names:
        for hand in HANDS:
            specs.append((name, "data", hand, 3))
        specs.append((name, "strahler", "hokusai", 3))
        specs.append((name, "trunk", "hokusai", 3))
    if a.only:
        specs = [s for s in specs if any(o in s[0] for o in a.only.split(","))]
    res = {}
    with ProcessPoolExecutor(JOBS) as ex:
        for spec, img, rec in ex.map(_compose_job, specs):
            res[spec] = (img, rec)
            print(json.dumps(rec), flush=True)
    with open(OUT / f"sheets{'_' + a.only if a.only else ''}.jsonl", "w") as fh:
        for _, rec in res.values():
            fh.write(json.dumps(rec) + "\n")
    for name in [n for n in names if any(s[0] == n for s in specs)]:
        cells = []
        for spec in [s for s in specs if s[0] == name]:
            img, rec = res[spec]
            sh = rec["share"]
            cells.append(label(img, f"{spec[1].upper() if spec[1] == 'data' else 'preset ' + spec[1]} field · "
                                    f"{spec[2]} hand · l/n/m {sh['line']:.2f}/{sh['nib']:.2f}/{sh['shape']:.2f} "
                                    f"· switches/line {rec['switches_per_line']}"))
        row = np.hstack(cells)
        save_jpg(stack([title_strip(row.shape[1], f"{name}: cols 1-3 DATA-BORN regime field in Hokusai / Matisse "
                                    "/ shikasta hands; cols 4-5 PRESET fields (Strahler, trunk) in Hokusai. "
                                    "Same structure, same seed."), row]),
                 RESULTS / f"earth_lines-hands-{name.replace(':', '_').split('_')[-1]}.jpg", max_kb=800)


# --- the limb: panel ----------------------------------------------------------

def _panel_job(args):
    key, path = args
    from gesture import panel
    from gesture.medium import SIGMA_MIN_W
    d = Drawing.load(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f, info = panel.features_with_info(d, sigma_min_w=SIGMA_MIN_W)
    return key, f, info.get("n_eligible", 0)


CALLI = ("shikasta", "nastaliq", "maghribi", "kufic", "baghdadi")


def cmd_panel(a):
    from gesture.medium import MediumProjector, load_media, load_pairs
    jobs = []
    base = ROOT / ".local/gesture/out"
    for art in ("matisse", "hokusai", "ingres"):
        for p in sorted((base / "extract_hybrid" / art).glob("*.json")):
            jobs.append(((art, p.stem), p))
    for g in CALLI:
        for p in sorted((base / "calligraphy/extract" / g).glob("*.json")):
            if not p.name.endswith(".outline.json"):
                jobs.append((("calligraphy:" + g, p.stem), p))
    for p in sorted(OUT.glob("river_*.json")):
        jobs.append((("river", p.stem), p))
    for p in sorted(OUT.glob("zoom_*.json")):
        jobs.append((("river-zoom", p.stem), p))
    for p in sorted(OUT.glob("scan_*.json")):
        nm = p.stem[5:]
        if nm in SCANS:
            jobs.append(((SCANS[nm][0], nm), p))
    cache = OUT / "panel_feats.json"
    feats = {}
    if cache.exists() and not a.fresh:
        feats = {tuple(k.split("|", 1)): v for k, v in json.loads(cache.read_text()).items()}
    todo = [j for j in jobs if j[0] not in feats]
    print(len(jobs), "drawings,", len(todo), "to measure", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(JOBS) as ex:
        for i, (key, f, ne) in enumerate(ex.map(_panel_job, todo, chunksize=2)):
            feats[key] = f
            if i % 20 == 0:
                print(i, key, ne, f"{time.time() - t0:.0f}s", flush=True)
    cache.write_text(json.dumps({"|".join(k): v for k, v in feats.items()}))
    analyse_panel(feats)


HUMAN = ("matisse", "hokusai", "ingres", "calligraphy")
PHYS = ("river", "river-zoom", "bubble", "discharge", "animal")


def _coarse(k):
    return "calligraphy" if k[0].startswith("calligraphy:") else k[0]


def analyse_panel(feats):
    from gesture.medium import MediumProjector, load_media, load_pairs
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold
    keys = sorted(feats)
    names = sorted(set().union(*[feats[k].keys() for k in keys]))
    geo = [n for n in names if n.split("_", 1)[0] not in ("w", "end")]
    X = np.array([[feats[k].get(n, np.nan) for n in geo] for k in keys])
    grp = np.array([_coarse(k) for k in keys])
    fine = np.array([k[0] for k in keys])
    media = load_media()
    med = np.array([media.get(k, "unknown") if k[0] in ("matisse", "hokusai", "ingres") else "unknown"
                    for k in keys])
    ok = ~np.all(np.isnan(X), axis=0)
    X = X[:, ok]
    geo = [g for g, o in zip(geo, ok) if o]
    # impute with HUMAN medians, project medium (fitted on artist media only)
    hum = np.isin(grp, HUMAN)
    mdn = np.nanmedian(X[hum], axis=0)
    X = np.where(np.isnan(X), mdn, X)
    P = MediumProjector(load_pairs()).fit(X, grp, med)
    Z = np.nan_to_num(P.transform(X))
    # standardise on humans so "distance" is in human-spread units
    mu, sd = Z[hum].mean(0), Z[hum].std(0)
    Z = (Z - mu) / np.where(sd > 0, sd, 1)
    Z = np.clip(Z, -8, 8)     # physics rows can be far outside; keep the logistic sane
    # pairwise AUCs
    def auc(g1, g2, reps=5):
        m = np.isin(grp, [g1, g2])
        y = (grp[m] == g2).astype(int)
        nmin = int(min(y.sum(), (1 - y).sum()))
        if nmin < 3:
            return None
        k = min(5, nmin)
        sc = []
        for rep in range(reps):
            pr = np.zeros(len(y))
            for tr, te in StratifiedKFold(k, shuffle=True, random_state=rep).split(Z[m], y):
                clf = LogisticRegression(C=0.5, max_iter=4000).fit(Z[m][tr], y[tr])
                pr[te] = clf.predict_proba(Z[m][te])[:, 1]
            sc.append(roc_auc_score(y, pr))
        return round(float(np.mean(sc)), 3)
    groups = [g for g in HUMAN + PHYS if (grp == g).sum() >= 3]
    A = {f"{g1}|{g2}": auc(g1, g2) for i, g1 in enumerate(groups) for g2 in groups[i + 1:]}
    # LDA fitted on humans only; physics projected in
    lda = LinearDiscriminantAnalysis(n_components=2, solver="eigen", shrinkage="auto").fit(Z[hum], grp[hum])
    L = lda.transform(Z)
    post = lda.predict_proba(Z)
    nearest = {}
    for g in PHYS:
        m = grp == g
        if m.any():
            nearest[g] = {c: round(float(v), 3) for c, v in zip(lda.classes_, post[m].mean(0))}
            nearest[g]["per_drawing"] = {keys[i][1]: str(lda.classes_[int(np.argmax(post[i]))])
                                         for i in np.flatnonzero(m)}
    # centroid distances (human-standardised units, RMS over features)
    cent = {g: Z[grp == g].mean(0) for g in groups}
    D = {g1: {g2: round(float(np.sqrt(np.mean((cent[g1] - cent[g2]) ** 2))), 3) for g2 in groups} for g1 in groups}
    # which features make each physics class non-human (largest |mean z|)
    top = {g: sorted(((geo[j], round(float(Z[grp == g, j].mean()), 2)) for j in range(len(geo))),
                     key=lambda t: -abs(t[1]))[:6] for g in PHYS if (grp == g).any()}
    rep = {"n": {g: int((grp == g).sum()) for g in HUMAN + PHYS}, "auc": A, "lda_posterior_mean": nearest,
           "centroid_rms": D, "top_features": top, "n_features": len(geo)}
    (OUT / "panel_report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in ("n", "auc", "lda_posterior_mean")}, indent=1))
    print(json.dumps(top, indent=1))
    _panel_figure(L, grp, fine, keys, rep)


def _panel_figure(L, grp, fine, keys, rep):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    col = {"matisse": "#4385BE", "hokusai": "#D14D41", "ingres": "#879A39", "calligraphy": "#DA702C",
           "river": "#100F0F", "river-zoom": "#DA702C", "bubble": "#100F0F", "discharge": "#100F0F", "animal": "#100F0F"}
    mk = {"matisse": "o", "hokusai": "o", "ingres": "o", "calligraphy": "o",
          "river": "s", "river-zoom": "P", "bubble": "*", "discharge": "^", "animal": "D"}
    fig, ax = plt.subplots(figsize=(10, 8), facecolor="#FFFCF0")
    ax.set_facecolor("#FFFCF0")
    for g in HUMAN + PHYS:
        m = grp == g
        if not m.any():
            continue
        human = g in HUMAN
        ax.scatter(L[m, 0], L[m, 1], c=col[g], marker=mk[g], s=22 if human else 70, alpha=0.45 if human else 0.9,
                   label=f"{g} ({m.sum()})", edgecolors="none" if human else "#FFFCF0")
        if not human:
            for i in np.flatnonzero(m):
                ax.annotate(keys[i][1].replace("river_", "").replace("zoom_", "z:").replace("trails-forty-years", ""), L[i],
                            fontsize=6.5, xytext=(3, 3), textcoords="offset points")
    ax.legend(fontsize=8, frameon=False, loc="best")
    ax.set_title("Physics lines measured as hands: LDA fitted on the HUMAN hands only "
                 "(geometry panel, σ ≥ 7 w, medium projected); physics drawings projected in", fontsize=9)
    ax.set_xlabel("LD1")
    ax.set_ylabel("LD2")
    for s in ax.spines.values():
        s.set_color("#B7B5AC")
    fig.tight_layout()
    p = RESULTS / "earth_lines-panel.jpg"
    fig.savefig(p, dpi=110, facecolor="#FFFCF0", pil_kwargs={"quality": 85})
    print("wrote", p)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["extract", "zoom", "structures", "sheets", "panel", "analyse"])
    ap.add_argument("--only", default="")
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.cmd == "analyse":
        feats = {tuple(k.split("|", 1)): v for k, v in json.loads((OUT / "panel_feats.json").read_text()).items()}
        return analyse_panel(feats)
    {"extract": cmd_extract, "zoom": cmd_zoom, "structures": cmd_structures, "sheets": cmd_sheets, "panel": cmd_panel}[a.cmd](a)


if __name__ == "__main__":
    main()
