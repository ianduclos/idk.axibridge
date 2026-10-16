"""Shapes → signs and masses: a learned shape vocabulary
(results/shape_lexicon-2026-10-16.md, module gesture/shape_lexicon.py).

Stages (outputs in .local/gesture/out/shape_lexicon/):
  extract   bodies + counters from every corpus sheet → shapes.json
  atlas     shape space (t-SNE of PCA(EFD)), coloured by source → atlas
  odd       the less obvious shapes: between clusters, atypical-yet-
            coherent, migrants (a shape from one corpus in another's region)
  vocab     sampler population sheet per shape class / per source
  sheets    same lines + same events: hand-made operators | learned shapes
            (all sources | Marden | calligraphy-generative | early computer)
  compose   regime_field.compose, same seed: stamps | learned shapes
  language  LIMB: neighbour co-occurrence of shape clusters per corpus,
            mutual information vs a shuffle null; generated "sentences"

  cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.shape_lexicon all
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import calligraphy as cg  # noqa: E402
from gesture import shape_lexicon as sl  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / ".local/gesture/corpus"
OUT = ROOT / ".local/gesture/out/shape_lexicon"
RESULTS = Path(__file__).resolve().parents[1] / "results"
REF = ROOT / ".local/gesture/ref/ian-regimes-sd-2024.png"
JOBS = 2
PAPER = (255, 252, 240)
INK = (16, 15, 15)
COL = {  # Flexoki 400 (axibridge/static/css/flexoki.css)
    "marden": "#D14D41", "cohen": "#DA702C", "henry": "#D0A215", "early_computer": "#879A39",
    "kelly": "#3AA99F", "matisse": "#4385BE", "hokusai": "#8B7EC8", "calligraphy": "#CE5D97",
    "print": "#9F9D96", "reference": "#100F0F",
}
ARTIST_SRC = {"brice_marden": "marden", "harold_cohen": "cohen", "desmond_paul_henry": "henry",
              "a_michael_noll": "early_computer", "frieder_nake": "early_computer", "nake_frieder": "early_computer",
              "vera_molnar": "early_computer", "molnar_vera": "early_computer", "ellsworth_kelly": "kelly"}


def _font(sz=16):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", sz)
    except OSError:
        return ImageFont.load_default()


def _save_jpg(img: Image.Image, path: Path, max_kb=900):
    q = 88
    while True:
        img.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024 or q < 40:
            break
        q -= 8
    print("wrote", path, path.stat().st_size // 1024, "KB")


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

def sheet_items():
    """(source, sheet id, loader arg, ink mode, generative)."""
    items = [("reference", "ian-regimes-sd-2024", str(REF), "black", False)]
    for d, src in ARTIST_SRC.items():
        for p in sorted((CORPUS / "artists" / d).glob("*.jpg")):
            mode = "colour" if src == "cohen" else ("white" if p.stem == "va-O499535" else "black")
            items.append((src, p.stem, str(p), mode, True))
    for p in sorted((CORPUS / "matisse").glob("*.jpg")):
        items.append(("matisse", p.stem, str(p), "black", True))
    for p in sorted((CORPUS / "hokusai").glob("*.jpg")):
        items.append(("hokusai", p.stem, str(p), "black", True))
    man = {**cg.load_manifest("print"), **cg.load_manifest("calligraphy")}
    for sid in cg.SHEETS:
        if sid.startswith("nyu-"):
            continue
        items.append(("calligraphy", sid, sid, "sheet", bool(cg.generative_allowed(man[cg._manifest_id(sid)]))))
    for book, n in (("AL08", 4), ("AL04", 4), ("AL01", 3)):
        ps = sorted((CORPUS / "print/scans" / book).glob("*.jp2"))
        for p in ps[2:2 + n]:
            items.append(("print", p.stem, str(p), "black", False))
    for p in sorted((CORPUS / "print/scans/AP03").glob("*_1.jpg"))[:6]:
        items.append(("print", p.stem, str(p), "lum", False))
    return items


def _load(item, max_side=2400):
    source, sheet, arg, mode, _ = item
    if mode == "sheet":
        return cg.load_sheet(arg, max_side=max_side)[0]
    if source == "print":
        max_side = 3600
    im = Image.open(arg).convert("RGB")
    if source in ARTIST_SRC.values():       # photographed frames / mounts
        mx, my = int(0.06 * im.size[0]), int(0.06 * im.size[1])
        im = im.crop((mx, my, im.size[0] - mx, im.size[1] - my))
    if max(im.size) > max_side:
        sc = max_side / max(im.size)
        im = im.resize((round(im.size[0] * sc), round(im.size[1] * sc)), Image.Resampling.BOX)
    return sl.ink_gray(np.asarray(im), mode)


def _extract_job(item):
    try:
        g = _load(item)
        shapes, info = sl.extract_shapes(g, source=item[0], sheet=item[1], generative=item[4],
                                         seed=sum(map(ord, item[1])),
                                         min_D_px=10.0 if item[0] == "print" else 14.0)
        return [s.to_json() for s in shapes], info
    except Exception as e:  # noqa: BLE001
        return [], {"sheet": item[1], "source": item[0], "error": repr(e)}


def stage_extract():
    OUT.mkdir(parents=True, exist_ok=True)
    items = sheet_items()
    rows, infos = [], []
    with ProcessPoolExecutor(JOBS) as ex:
        for r, info in ex.map(_extract_job, items):
            rows += r
            infos.append(info)
            print(info.get("source"), info.get("sheet"), info.get("bodies"), info.get("marks"), info.get("counters"),
                  info.get("error", ""), flush=True)
    (OUT / "shapes.json").write_text(json.dumps(rows))
    (OUT / "sheets.json").write_text(json.dumps(infos, indent=1))
    print("shapes", len(rows))


def load_shapes() -> list[sl.Shape]:
    return [sl.Shape.from_json(d) for d in json.loads((OUT / "shapes.json").read_text())]


_LEX = None


def load_lexicon(seed=0) -> sl.Lexicon:
    global _LEX
    if _LEX is None:
        _LEX = sl.Lexicon(load_shapes(), seed=seed)
    return _LEX


STAGES = {"extract": stage_extract}


# ---------------------------------------------------------------------------
# drawing helpers
# ---------------------------------------------------------------------------

def _glyph(d: ImageDraw.ImageDraw, sh_outline, kind, cx, cy, r, fill=INK, width=2):
    q = np.asarray(sh_outline, float)
    q = q - q.mean(0)
    sc = r / max(np.abs(q).max(), 1e-9)
    pts = [tuple(v) for v in (q * sc + (cx, cy))]
    if kind == "counter":
        d.line(pts + [pts[0]], fill=fill, width=width, joint="curve")
    else:
        d.polygon(pts, fill=fill)


def draw_paths(paths, size_mm, *, pxmm=3.0, pen=0.5, ss=2, img=None, offset=(0.0, 0.0), ink=20):
    """Plotter paths (mm) drawn with a round pen (as signs_study.draw_paths)."""
    Wd, Hd = int(size_mm[0] * pxmm), int(size_mm[1] * pxmm)
    big = Image.new("L", (Wd * ss, Hd * ss), 255)
    d = ImageDraw.Draw(big)
    lw = max(int(round(pen * pxmm * ss)), 1)
    r = pen * pxmm * ss / 2
    for p in paths:
        q = (np.asarray(p, float) + offset) * pxmm * ss
        if len(q) >= 2:
            d.line([tuple(v) for v in q], fill=ink, width=lw, joint="curve")
        for v in (q[0], q[-1]):
            d.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=ink)
    out = big.resize((Wd, Hd), Image.Resampling.LANCZOS)
    if img is not None:
        return Image.fromarray(np.minimum(np.asarray(img), np.asarray(out)))
    return out


def _paper(gray: Image.Image) -> Image.Image:
    """Gray (255 paper) → ink on warm paper."""
    a = np.asarray(gray, float) / 255.0
    pap, ink = np.array(PAPER, float), np.array(INK, float)
    return Image.fromarray((ink + (pap - ink) * a[..., None]).astype(np.uint8))


def _stratified(lex: sl.Lexicon, per_source: int, rng) -> np.ndarray:
    idx = []
    by = {}
    for i, s in enumerate(lex.shapes):
        by.setdefault(s.source, []).append(i)
    for src, ii in by.items():
        ii = np.array(ii)
        idx += list(ii if len(ii) <= per_source else rng.choice(ii, per_source, replace=False))
    return np.array(sorted(idx))


# ---------------------------------------------------------------------------
# atlas
# ---------------------------------------------------------------------------

def stage_atlas():
    from sklearn.manifold import TSNE
    lex = load_lexicon()
    rng = np.random.default_rng(1)
    idx = _stratified(lex, 260, rng)
    Z = TSNE(n_components=2, perplexity=35, init="pca", random_state=0).fit_transform(lex.Y[idx])
    Z = (Z - Z.min(0)) / (Z.max(0) - Z.min(0))
    S, M = 2600, 120
    img = Image.new("RGB", (S, S + 200), PAPER)
    d = ImageDraw.Draw(img)
    for k, i in enumerate(idx):
        sh = lex.shapes[i]
        cx, cy = M + Z[k, 0] * (S - 2 * M), 160 + M + Z[k, 1] * (S - 2 * M)
        _glyph(d, sh.outline, sh.kind, cx, cy, 19, fill=_rgb(COL[sh.source]), width=2)
    d.text((40, 30), "Shape atlas — t-SNE of the elliptic-Fourier shape space (scale, rotation, start point removed)",
           fill=INK, font=_font(34))
    d.text((40, 76), f"{len(idx)} of {len(lex.shapes)} shapes, ≤ 260 per source. Filled = ink body or thin mark; "
           "outline = counter (paper enclosed by ink). Colour = corpus.", fill=INK, font=_font(24))
    x = 40
    counts = {}
    for s in lex.shapes:
        counts[s.source] = counts.get(s.source, 0) + 1
    for src, c in COL.items():
        d.rectangle([x, 118, x + 22, 140], fill=_rgb(c))
        lab = f"{src.replace('_', ' ')} {counts.get(src, 0)}"
        d.text((x + 30, 114), lab, fill=INK, font=_font(24))
        x += 34 + int(d.textlength(lab, font=_font(24))) + 26
    _save_jpg(img, RESULTS / "shape_lexicon-atlas.jpg")

    # clusters × members, with source mix
    k = lex.km.n_clusters
    per = 16
    cw, ch = 110, 118
    W2 = 330 + per * cw
    img = Image.new("RGB", (W2, 110 + k * ch), PAPER)
    d = ImageDraw.Draw(img)
    d.text((30, 20), f"Shape clusters (k-means, k={k}) — members drawn at random; bar = corpus mix of the cluster, "
           "base-rate weighted", fill=INK, font=_font(28))
    base = np.array([counts.get(s, 0) for s in COL], float)
    base = base / base.sum()
    order = np.argsort([np.mean([lex.shapes[i].coeffs[0, 3] for i in np.where(lex.labels == c)[0]]) for c in range(k)])
    for row, c in enumerate(order):
        y = 80 + row * ch
        mem = np.where(lex.labels == c)[0]
        mix = np.array([np.sum([lex.shapes[i].source == s for i in mem]) for s in COL], float)
        mixw = (mix / max(mix.sum(), 1)) / np.maximum(base, 1e-9)
        mixw = mixw / max(mixw.sum(), 1e-9)
        x0 = 30
        for share, col in zip(mixw, COL.values()):
            wpx = share * 260
            d.rectangle([x0, y + 40, x0 + wpx, y + 70], fill=_rgb(col))
            x0 += wpx
        kinds = {kk: int(np.sum([lex.shapes[i].kind == kk for i in mem])) for kk in ("body", "mark", "counter")}
        d.text((30, y + 8), f"c{c}  n={len(mem)}  b{kinds['body']} m{kinds['mark']} c{kinds['counter']}",
               fill=INK, font=_font(20))
        pick = rng.choice(mem, min(per, len(mem)), replace=False)
        for j, i in enumerate(pick):
            sh = lex.shapes[i]
            _glyph(d, sh.outline, sh.kind, 330 + j * cw + cw / 2, y + ch / 2, 44, fill=INK, width=3)
            d.rectangle([330 + j * cw + 30, y + ch - 12, 330 + j * cw + cw - 30, y + ch - 7], fill=_rgb(COL[sh.source]))
    _save_jpg(img, RESULTS / "shape_lexicon-clusters.jpg")


# ---------------------------------------------------------------------------
# the less obvious shapes
# ---------------------------------------------------------------------------

def odd_sets(lex: sl.Lexicon, n: int = 14, seed: int = 3):
    rng = np.random.default_rng(seed)
    Y = lex.Y
    D = lex.km.transform(Y)
    Ds = np.sort(D, axis=1)
    border = Ds[:, 0] / np.maximum(Ds[:, 1], 1e-9)
    dk, nn = lex.tree.query(Y, k=16)
    atyp = dk[:, 1:].mean(1)
    co = np.array([s.coeffs for s in lex.shapes])
    hi = np.sum(co[:, 7:] ** 2, axis=(1, 2))
    tot = np.sum(co ** 2, axis=(1, 2))
    rough = hi / tot
    sources = np.array([s.source for s in lex.shapes])
    names = list(COL)
    base = np.array([np.mean(sources == s) for s in names])
    enrich = np.zeros((len(Y), len(names)))
    for j, s in enumerate(names):
        enrich[:, j] = np.mean(sources[nn[:, 1:]] == s, axis=1) / max(base[j], 1e-9)
    own = np.array([enrich[i, names.index(sources[i])] for i in range(len(Y))])
    host = np.argmax(enrich, axis=1)
    ok = np.array([s.source != "reference" for s in lex.shapes])

    def diverse(cands, score, by_host=False):
        cands = [c for c in cands if ok[c]]
        cands = sorted(cands, key=lambda c: -score[c])
        out, seen = [], {}
        for c in cands:
            key = (sources[c], host[c] if by_host else lex.labels[c])
            if seen.get(key, 0) >= 1:
                continue
            seen[key] = seen.get(key, 0) + 1
            out.append(c)
            if len(out) >= n:
                break
        return out

    b_c = list(np.where(border > 0.97)[0])
    a_c = list(np.where((atyp > np.quantile(atyp, 0.85)) & (rough < np.quantile(rough, 0.7)))[0])
    hostn = np.array([np.sum(sources[nn[i, 1:]] == names[host[i]]) for i in range(len(Y))])
    m_c = list(np.where((own < 0.4) & (enrich[np.arange(len(Y)), host] > 3.0) & (hostn >= 6))[0])
    sets = {
        "between clusters (equidistant from two cluster centres)": (diverse(b_c, border), border),
        "atypical yet coherent (sparse neighbourhood, smooth outline)": (diverse(a_c, atyp), atyp),
        "migrants (a shape whose neighbours are another corpus's)": (diverse(m_c, enrich.max(1) - own, by_host=True), None),
    }
    stats = {"n": len(Y), "border_gt_0.97": len(b_c), "atypical_coherent": len(a_c), "migrants": len(m_c),
             "migrant_pairs": {}}
    for c in m_c:
        k = f"{sources[c]} → {names[host[c]]}"
        stats["migrant_pairs"][k] = stats["migrant_pairs"].get(k, 0) + 1
    ref = [i for i in range(len(Y)) if sources[i] == "reference"]
    if ref:
        e = enrich[ref].mean(0)
        stats["reference_neighbour_enrichment"] = {names[j]: round(float(e[j]), 2) for j in np.argsort(-e)}
    return sets, stats, names, host


def stage_odd():
    lex = load_lexicon()
    sets, stats, names, host = odd_sets(lex)
    cw, ch = 175, 215
    per = 14
    img = Image.new("RGB", (40 + per * cw, 110 + len(sets) * (ch + 70)), PAPER)
    d = ImageDraw.Draw(img)
    d.text((30, 20), "The less obvious shapes — measured outlines, ink = body or mark, outline = counter",
           fill=INK, font=_font(30))
    d.text((30, 60), "label: corpus · sheet · class (migrants: 'in' = the corpus whose region it sits in)",
           fill=INK, font=_font(22))
    y = 110
    for title, (ids, _) in sets.items():
        d.text((30, y), title, fill=INK, font=_font(26))
        y += 44
        for j, i in enumerate(ids):
            sh = lex.shapes[i]
            cx = 40 + j * cw + cw / 2
            _glyph(d, sh.outline, sh.kind, cx, y + 80, 70, fill=INK, width=3)
            lab = f"{sh.source.replace('_', ' ')}"
            d.text((cx - cw / 2 + 6, y + 160), lab, fill=_rgb(COL[sh.source]), font=_font(17))
            sub = f"{sh.sheet[:12]} · {sh.klass}"
            if title.startswith("migrants"):
                sub = f"in {names[host[i]].replace('_', ' ')}"
                d.text((cx - cw / 2 + 6, y + 180), sub, fill=_rgb(COL[names[host[i]]]), font=_font(17))
            else:
                d.text((cx - cw / 2 + 6, y + 180), sub, fill=INK, font=_font(15))
        y += ch + 26
    _save_jpg(img, RESULTS / "shape_lexicon-odd.jpg")
    (OUT / "odd_stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1))


# ---------------------------------------------------------------------------
# vocabulary: sampler population
# ---------------------------------------------------------------------------

GEN_SOURCES = {"all": None, "marden": {"marden"}, "calligraphy": {"calligraphy"},
               "early computer + Cohen": {"early_computer", "cohen"}, "hokusai": {"hokusai"},
               "matisse": {"matisse"}, "henry": {"henry"}}


def stage_vocab():
    lex = load_lexicon()
    rng = np.random.default_rng(11)
    rows = [(f"class: {k}", dict(klass=k)) for k in ("dot", "terminal", "through", "node", "mark", "loop")]
    rows += [(f"source: {k}", dict(sources=v, kind="body")) for k, v in GEN_SOURCES.items() if v]
    rows += [(f"counters: {k}", dict(sources=v, klass="loop")) for k, v in GEN_SOURCES.items() if v]
    per, cw, ch = 14, 120, 120
    img = Image.new("RGB", (300 + per * cw, 90 + len(rows) * ch), PAPER)
    d = ImageDraw.Draw(img)
    d.text((24, 18), "Sampler population — every glyph is NEW (base + neighbour mix + harmonic noise), "
           "red dots = learned line exits", fill=INK, font=_font(26))
    stats = {}
    for r, (lab, kw) in enumerate(rows):
        y = 70 + r * ch
        d.text((24, y + ch / 2 - 12), lab, fill=INK, font=_font(20))
        srcs = []
        for j in range(per):
            try:
                U, ex, info = lex.sample(rng, **kw)
            except ValueError:
                continue
            srcs.append(info["source"])
            kind = "counter" if info.get("kind") == "counter" else "body"
            cx, cy = 300 + j * cw + cw / 2, y + ch / 2
            q = U - U.mean(0)
            sc = 46 / max(np.abs(q).max(), 1e-9)
            _glyph(d, U, kind, cx, cy, 46, fill=INK, width=3)
            for e in ex:
                v = (e - U.mean(0)) * sc + (cx, cy)
                d.ellipse([v[0] - 5, v[1] - 5, v[0] + 5, v[1] + 5], fill=_rgb("#D14D41"))
        stats[lab] = {s: srcs.count(s) for s in set(srcs)}
    _save_jpg(img, RESULTS / "shape_lexicon-vocab.jpg")
    print(json.dumps(stats, indent=1))


# ---------------------------------------------------------------------------
# same lines, same events: hand-made | learned
# ---------------------------------------------------------------------------

EV_W, EV_PEN = 0.6, 0.5


def _lines_for(src: str, seed: int):
    from experiments import signs_study as ss
    return ss.structure_lines(src, seed)


def _panels(src, seed, lex, columns):
    from gesture import signs
    lines = _lines_for(src, seed)
    evs = signs.plan_events(lines, np.random.default_rng(seed), None, w=EV_W)
    out = []
    for name, srcs in columns:
        if name == "hand-made":
            sts = signs.apply_events(lines, evs, np.random.default_rng(seed + 7), w=EV_W)
            paths = signs.render_events(sts, EV_PEN)
            info = None
        else:
            paths, info = sl.grow_events(lines, evs, lex, np.random.default_rng(seed + 7), w=EV_W, pen=EV_PEN,
                                         sources=srcs)
        out.append((name, paths, info))
    return lines, evs, out


def stage_sheets():
    lex = load_lexicon()
    cols = [("hand-made", None), ("learned · all", None), ("learned · Marden", {"marden"}),
            ("learned · calligraphy", {"calligraphy"}), ("learned · early computer + Cohen", {"early_computer", "cohen"})]
    rows = [("v6:matisse", 21), ("v6:hokusai", 22), ("tree", 4)]
    pxmm = 2.6
    pw, ph = int(180 * pxmm), int(240 * pxmm)
    img = Image.new("L", (len(cols) * pw, 70 + len(rows) * (ph + 40)), 255)
    d = ImageDraw.Draw(img)
    d.text((16, 14), "Same lines, same event sites/sizes/sides (signs.plan_events). Only the operator differs: "
           "hand-made (signs.py) vs shapes sampled from the learned vocabulary.", fill=0, font=_font(22))
    log = {}
    for r, (src, seed) in enumerate(rows):
        lines, evs, panels = _panels(src, seed, lex, cols)
        for c, (name, paths, info) in enumerate(panels):
            tile = draw_paths(paths, (180, 240), pxmm=pxmm, pen=EV_PEN)
            img.paste(tile, (c * pw, 70 + r * (ph + 40) + 34))
            d.text((c * pw + 12, 70 + r * (ph + 40) + 6), f"{src} s{seed} · {name}", fill=0, font=_font(20))
            if info is not None:
                log[f"{src}|{name}"] = {"events": len(evs), "filled": sum(g.filled for g in info),
                                        "classes": {k: sum(g.klass == k for g in info) for k in
                                                    sorted({g.klass for g in info})},
                                        "sources": {k: sum(g.info.get("source") == k for g in info) for k in
                                                    sorted({g.info.get("source") for g in info})}}
        for c in range(1, len(cols)):
            d.line([(c * pw, 70), (c * pw, img.size[1])], fill=200, width=2)
    _save_jpg(_paper(img), RESULTS / "shape_lexicon-sheets.jpg")
    (OUT / "sheets_log.json").write_text(json.dumps(log, indent=1))

    # detail: one structure at plot-ish scale, hand-made | learned all
    lines, evs, panels = _panels("v6:hokusai", 22, lex, cols[:2])
    pxmm = 7.0
    box = (40, 60, 140, 160)                     # mm window
    tiles = []
    for name, paths, _ in panels:
        sh = [np.asarray(p) - box[:2] for p in paths]
        t = draw_paths(sh, (box[2] - box[0], box[3] - box[1]), pxmm=pxmm, pen=EV_PEN)
        ImageDraw.Draw(t).text((12, 10), f"{name} (detail, 100 × 100 mm, pen 0.5 mm)", fill=0, font=_font(24))
        tiles.append(t)
    det = Image.new("L", (sum(t.size[0] for t in tiles) + 20, tiles[0].size[1]), 255)
    det.paste(tiles[0], (0, 0))
    det.paste(tiles[1], (tiles[0].size[0] + 20, 0))
    ImageDraw.Draw(det).line([(tiles[0].size[0] + 10, 0), (tiles[0].size[0] + 10, det.size[1])], fill=180, width=3)
    _save_jpg(_paper(det), RESULTS / "shape_lexicon-detail.jpg")


# ---------------------------------------------------------------------------
# compose wrapper: same seed, stamps vs learned shapes
# ---------------------------------------------------------------------------

def _draw_px(polys, size, pen_px, scale):
    W, H = int(size[0] * scale), int(size[1] * scale)
    big = Image.new("L", (W * 2, H * 2), 255)
    d = ImageDraw.Draw(big)
    lw = max(int(round(pen_px * scale * 2)), 1)
    for q in polys:
        q = np.asarray(q) * scale * 2
        if len(q) >= 2:
            d.line([tuple(v) for v in q], fill=20, width=lw, joint="curve")
    return big.resize((W, H), Image.Resampling.LANCZOS)


def stage_compose():
    from gesture import regime_field as rf
    lex = load_lexicon()
    specs = [(5, "tree", "strahler", "hokusai"), (8, "grammar", "noise", "matisse")]
    scale = 0.6
    tiles = []
    meta = {}
    for seed, structure, fld, hand in specs:
        kw = dict(size=(840, 1200), structure=structure, field=fld, hands=hand, signs=14)
        a = rf.compose(seed, **kw)
        b = sl.compose_learned(seed, lex, **kw)
        c = sl.compose_learned(seed, lex, sources={"marden", "hokusai", "matisse"}, **kw)
        for lab, comp in (("stamps (place_signs)", a), ("learned · all", b), ("learned · Marden+Hokusai+Matisse", c)):
            t = _draw_px(comp.polylines, comp.size, comp.meta["pen_px"], scale)
            ImageDraw.Draw(t).text((10, 8), f"seed {seed} · {structure}/{fld}/{hand} · {lab}", fill=0, font=_font(16))
            tiles.append(t)
            meta[f"{seed}|{lab}"] = {k: comp.meta[k] for k in ("n_polylines", "n_signs", "signs_engine")}
    tw, th = tiles[0].size
    img = Image.new("L", (3 * tw + 20, 2 * th + 10), 255)
    for k, t in enumerate(tiles):
        img.paste(t, ((k % 3) * (tw + 10), (k // 3) * (th + 10)))
    _save_jpg(_paper(img), RESULTS / "shape_lexicon-compose.jpg")
    print(json.dumps(meta, indent=1))


STAGES.update({"atlas": stage_atlas, "odd": stage_odd, "vocab": stage_vocab, "sheets": stage_sheets,
               "compose": stage_compose})


# ---------------------------------------------------------------------------
# LIMB: shapes as a language
# ---------------------------------------------------------------------------

LANG_SOURCES = ["marden", "hokusai", "matisse", "calligraphy", "print", "cohen", "early_computer", "henry",
                "reference"]


def _sheet_pairs(lex):
    infos = {i["sheet"]: i for i in json.loads((OUT / "sheets.json").read_text())}
    by = {}
    for i, s in enumerate(lex.shapes):
        by.setdefault((s.source, s.sheet), []).append(i)
    out = {}
    for (src, sheet), ii in by.items():
        w = infos.get(sheet, {}).get("w_px", 3.0)
        pr = sl.neighbour_pairs([lex.shapes[i] for i in ii], gap_w=2.5, w_px=w)
        ii = np.array(ii)
        out.setdefault(src, []).append((sheet, ii, np.array(pr, int).reshape(-1, 2)))
    return out


def language_stats(lex, n_null=200, seed=0, gen_only=False):
    rng = np.random.default_rng(seed)
    k = lex.km.n_clusters
    lab = lex.labels
    res = {}
    for src, lst in _sheet_pairs(lex).items():
        if gen_only:
            lst = [x for x in lst if lex.shapes[x[1][0]].generative]
        A = np.concatenate([ii[pr[:, 0]] for _, ii, pr in lst if len(pr)] or [np.zeros(0, int)])
        B = np.concatenate([ii[pr[:, 1]] for _, ii, pr in lst if len(pr)] or [np.zeros(0, int)])
        if len(A) < 30:
            continue
        st = sl.transition_stats(lab[A], lab[B], k)
        null = []
        for _ in range(n_null):
            la, lb = [], []
            for _, ii, pr in lst:
                if not len(pr):
                    continue
                perm = dict(zip(ii, rng.permutation(lab[ii])))
                la.append([perm[ii[a]] for a in pr[:, 0]])
                lb.append([perm[ii[b]] for b in pr[:, 1]])
            null.append(sl.transition_stats(np.concatenate(la), np.concatenate(lb), k)["mi"])
        null = np.array(null)
        # a same-kind control: how much of the MI is just "bodies next to
        # bodies, counters next to counters"?
        kinds = np.array([{"body": 0, "mark": 1, "counter": 2}[s.kind] for s in lex.shapes])
        kst = sl.transition_stats(kinds[A], kinds[B], 3)
        C = st["counts"]
        top = []
        for a in range(k):
            for b in range(a, k):
                if C[a, b] >= 6:
                    top.append((float(st["lift"][a, b]), a, b, int(C[a, b])))
        top.sort(reverse=True)
        res[src] = {"pairs": int(len(A)), "sheets": len(lst), "mi_bits": round(st["mi"], 4),
                    "null_mean": round(float(null.mean()), 4), "null_sd": round(float(null.std()), 4),
                    "z": round(float((st["mi"] - null.mean()) / max(null.std(), 1e-9)), 1),
                    "excess_bits": round(float(st["mi"] - null.mean()), 4),
                    "kind_mi_bits": round(kst["mi"], 4), "top_lift": top[:5], "counts": C.tolist()}
    return res


def _medoid(lex, c):
    mem = np.where(lex.labels == c)[0]
    d = np.linalg.norm(lex.Y[mem] - lex.km.cluster_centers_[c], axis=1)
    return int(mem[np.argmin(d)])


def _sentence(lex, src_counts, rng, length=7):
    C = np.asarray(src_counts, float) + 0.05
    P = C / C.sum(1, keepdims=True)
    m = C.sum(1) / C.sum()
    seq = [int(rng.choice(len(m), p=m))]
    for _ in range(length - 1):
        seq.append(int(rng.choice(len(m), p=P[seq[-1]])))
    return seq


def _instance(lex, c, rng, sources):
    pool = lex.generative_pool(sources=sources)
    mem = [i for i in pool if lex.labels[i] == c]
    if not mem:
        mem = [i for i in lex.generative_pool() if lex.labels[i] == c]
    if not mem:
        return None
    base = int(mem[rng.integers(len(mem))])
    U, ex, info = lex.sample(rng, base=base)
    return info["coeffs"], lex.shapes[base].kind


def stage_language():
    lex = load_lexicon()
    res = language_stats(lex)
    gen = language_stats(lex, n_null=1, gen_only=True)
    slim = {s: {k: v for k, v in r.items() if k != "counts"} for s, r in res.items()}
    (OUT / "language.json").write_text(json.dumps({"all": res, "gen_only_counts": {s: r["counts"] for s, r in
                                                                                 gen.items()}}, indent=1))
    print(json.dumps(slim, indent=1))
    rng = np.random.default_rng(5)
    srcs = [s for s in ["marden", "hokusai", "calligraphy", "matisse", "cohen"] if s in gen]
    pxmm = 4.0
    Wmm, rowmm = 300.0, 34.0
    rows = []
    for src in srcs:
        for variant in ("sequence", "morph"):
            rows.append((src, variant))
    img = Image.new("L", (int(Wmm * pxmm), int((len(rows) * 2 * rowmm + 36) * pxmm)), 255)
    d = ImageDraw.Draw(img)
    d.text((14, 8), "Shapes as a language (limb): Markov walks over shape clusters; transitions = neighbouring\n"
           "shapes on each corpus's sheets (calligraphy: generative-allowed sheets only). sequence = each cluster\n"
           "a new sampled shape on one line; morph = EFD interpolation from shape to shape, fill depth\n"
           "ramping mass <-> nib rim <-> line loop", fill=0, font=_font(19))
    y0 = 36.0
    t = np.linspace(0, 1, 600)
    sents = {}
    for r, (src, variant) in enumerate(rows):
        for rep in range(2):
            yb = y0 + (r * 2 + rep) * rowmm + rowmm * 0.55
            line = np.column_stack([12 + (Wmm - 24) * t, yb + 2.0 * np.sin(2 * np.pi * (1.3 * t + rep * 0.3))])
            seed_r = np.random.default_rng([r, rep, 7])
            seq = _sentence(lex, gen[src]["counts"], seed_r, length=7 if variant == "sequence" else 5)
            sents.setdefault(src, []).append(seq)
            sources = {src}
            inst = [x for x in (_instance(lex, c, seed_r, sources) for c in seq) if x is not None]
            items = []
            if variant == "sequence":
                gap = (Wmm - 60) / max(len(inst), 1)
                for j, (co, kind) in enumerate(inst):
                    items.append(dict(s=30 + j * gap, size=seed_r.uniform(6, 11), side=seed_r.choice([-1, 1]),
                                      coeffs=co, rings=0 if kind == "counter" else None))
            else:
                n_mid = 3
                chain = []
                for j in range(len(inst) - 1):
                    (ca, ka), (cb, kb) = inst[j], inst[j + 1]
                    m = min(len(ca), len(cb))
                    fa = 1.0 if ka != "counter" else 0.0
                    fb = 1.0 if kb != "counter" else 0.0
                    for q in range(n_mid + (1 if j == len(inst) - 2 else 0) + 1):
                        lam = q / (n_mid + 1)
                        if j > 0 and q == 0:
                            continue
                        co = (1 - lam) * ca[:m] + lam * cb[:m]
                        f = (1 - lam) * fa + lam * fb
                        chain.append((co, f))
                gap = (Wmm - 40) / max(len(chain), 1)
                side = 1
                for j, (co, f) in enumerate(chain):
                    size = 7.5 + 2.5 * math.sin(j * 0.9)
                    rings = None if f > 0.85 else (0 if f < 0.15 else max(1, int(round(f * 5))))
                    items.append(dict(s=22 + j * gap, size=size, side=side, coeffs=co, rings=rings))
                    side = -side if seed_r.random() < 0.3 else side
            path = sl.grow_sequence(line, items, EV_PEN, seed_r)
            img = draw_paths([path], (Wmm, img.size[1] / pxmm), pxmm=pxmm, pen=EV_PEN, img=img)
            if rep == 0:
                ImageDraw.Draw(img).text((14, int((yb - rowmm * 0.5) * pxmm)), f"{src} · {variant}", fill=0,
                                         font=_font(20))
    _save_jpg(_paper(img), RESULTS / "shape_lexicon-language.jpg")
    (OUT / "sentences.json").write_text(json.dumps(sents))

    # lift heat panels (diagnostic): per source, top lifted pairs as glyphs
    show = [s for s in LANG_SOURCES if s in res]
    cw = 130
    img = Image.new("RGB", (330 + 5 * 3 * cw, 90 + len(show) * 150), PAPER)
    d = ImageDraw.Draw(img)
    d.text((20, 16), "What sits next to what — top lifted cluster pairs per corpus (observed ÷ expected; "
           "pairs = shapes within 2.5 line widths); MI excess over a within-sheet shuffle", fill=INK,
           font=_font(24))
    for r, src in enumerate(show):
        y = 70 + r * 150
        R = res[src]
        d.text((20, y + 30), src.replace("_", " "), fill=_rgb(COL[src]), font=_font(24))
        d.text((20, y + 64), f"MI {R['mi_bits']:.3f} b, null {R['null_mean']:.3f}", fill=INK, font=_font(18))
        d.text((20, y + 88), f"z {R['z']}, pairs {R['pairs']}", fill=INK, font=_font(18))
        for j, (lift, a, b, n) in enumerate(R["top_lift"][:5]):
            x = 330 + j * 3 * cw
            for q, c in enumerate((a, b)):
                sh = lex.shapes[_medoid(lex, c)]
                _glyph(d, sh.outline, sh.kind, x + q * cw + cw / 2, y + 60, 46, fill=INK, width=3)
                d.text((x + q * cw + 40, y + 112), f"c{c}", fill=INK, font=_font(16))
            d.text((x + 2 * cw + 4, y + 50), f"×{lift:.1f}\nn={n}", fill=INK, font=_font(18))
    _save_jpg(img, RESULTS / "shape_lexicon-language-pairs.jpg")


STAGES["language"] = stage_language


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stages", nargs="+")
    a = ap.parse_args()
    names = list(STAGES) if a.stages == ["all"] else a.stages
    for n in names:
        STAGES[n]()


if __name__ == "__main__":
    main()
