"""Sign-like shapes and their relation to lines (results/signs-2026-10-16.md).

Stages (run in order; each writes to .local/gesture/out/signs/):
  reference  inventory of Ian's reference image (.local/gesture/ref/…, not
             committed): ink components, relation to lines, sizes / w
  dots       dot geometry in calligraphy sheets — POLICY-GATED: only
             content_type ∈ {exercise, poetry, document} (require_generative)
  fonts      dot SHAPE of OFL font glyphs (neutral isolated letters only)
  grammar    learn the placement grammar (signs.learn_grammar)
  catalogue  results/signs-catalogue.jpg
  sheets     results/signs-v6.jpg, results/signs-tree.jpg (learned | random)
  pairs      blinded judge pairs → .local/gesture/out/blind_signs/pairs/,
             key OUTSIDE the repo (/tmp/gesture_signs_key.json)
  events_grammar  line-event grammar (signs.learn_event_grammar) →
             .local/gesture/out/signs_events/event_grammar.json
  events_vocab    results/signs-events-vocabulary.jpg
  events_sheets   results/signs-events-v6.jpg (events | round-6 stamps),
                  results/signs-events-tree.jpg (events | random events)
  events_pairs    blinded pairs → .local/gesture/out/blind_events/pairs/,
                  key OUTSIDE the repo (/tmp/gesture_events_key.json)

  cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.signs_study all
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import calligraphy as cg  # noqa: E402
from gesture import signs  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / ".local/gesture/out/signs"
REF = ROOT / ".local/gesture/ref/ian-regimes-sd-2024.png"
RESULTS = Path(__file__).resolve().parents[1] / "results"
PAIRS = ROOT / ".local/gesture/out/blind_signs/pairs"
KEY = Path(os.environ.get("SIGNS_KEY", "/tmp/gesture_signs_key.json"))
JOBS = 3

# secular calligraphy sheets with usable dots. Excluded although allowed:
# wal-W672-5b/6a (overwritten karalama: dots merge into the tangle) and
# wc-06 (ferman: tughra fill ornament reads as dots).
DOT_SHEETS = ["met-716305", "met-716307", "met-716304", "wal-W668-66b", "wal-W668-74b", "cma-1983.1115.a",
              "wc-12", "wc-13", "wc-15", "wc-05", "wc-30"]

# The reference read by eye (full-res px boxes x0, y0, x1, y1; w ≈ 6 px).
# The automated inventory is noisy on this image (spray, grey washes, nib
# letters break into "junction" masses), so the relation mix of the
# grammar comes from this reading; sizes come from the automated pass.
MANUAL_REF = [
    ("eye: loop holding an off-centre dot", "enclosed", (395, 420, 455, 485)),
    ("small loop with a dot inside + drop at its line end", "enclosed", (860, 270, 960, 380)),
    ("drop at the end of that loop's line", "terminal", (868, 345, 890, 365)),
    ("two specks below the loop ('fly')", "adjacent", (860, 385, 905, 410)),
    ("nib wedge / lozenge ending a line", "terminal", (898, 515, 930, 548)),
    ("drop closing the T-bar's right end", "terminal", (935, 705, 960, 735)),
    ("filled knot with a white slit, beside the big stroke", "adjacent", (805, 895, 870, 990)),
    ("small block under the knot", "adjacent", (845, 1005, 875, 1035)),
    ("drop ending the '9' curve", "terminal", (968, 1040, 995, 1075)),
    ("comma beside the mid tangle", "adjacent", (505, 1005, 535, 1040)),
    ("knot that fills in, on a thin line", "interior", (185, 855, 245, 895)),
    ("beads / swellings on the mid lines", "interior", (540, 1170, 610, 1240)),
    ("bead on the vessel stem", "interior", (480, 1480, 505, 1525)),
    ("line swelling into a vessel/goblet", "terminal", (380, 1430, 545, 1830)),
    ("black oval beside the vessel", "adjacent", (330, 1580, 385, 1705)),
    ("block hanging on a line end", "terminal", (728, 1725, 805, 1800)),
    ("ring under the block", "adjacent", (775, 1785, 838, 1838)),
    ("comma / hook mass with a curling tail", "adjacent", (800, 1745, 935, 1830)),
    ("three ticks (comb) by the comma's tail", "adjacent", (932, 1700, 958, 1748)),
    ("ring + hook pair", "adjacent", (848, 1650, 895, 1722)),
    ("crossing loop with a dot", "enclosed", (640, 1560, 705, 1625)),
    ("free dot in the open", "free", (712, 1592, 728, 1608)),
    ("crescent (thick nib arc), standing alone", "free", (338, 115, 405, 255)),
    ("negative eye: white crescent inside the big mass", "free", (735, 175, 795, 245)),
    ("hook ends of thin lines (several)", "terminal", (130, 1300, 175, 1340)),
    ("drop at a thin line's end (lower left)", "terminal", (95, 1360, 135, 1390)),
]
# heterogeneous constellations seen: block+ring+comma+comb; knot+block;
# loop+drop+specks; vessel+oval+bead — 4 groups holding 13 of the 26.


def _ref_mask():
    im = np.asarray(Image.open(REF).convert("RGB"))
    g = cg.to_gray(im, "black")
    m = ndi.binary_opening(g < 0.38, iterations=1)
    return ndi.binary_closing(m, structure=signs._disk(2))


def stage_reference():
    OUT.mkdir(parents=True, exist_ok=True)
    m = _ref_mask()
    inv = signs.inventory(m)
    comps = inv["components"]
    man = {}
    for _, rel, _ in MANUAL_REF:
        man[rel] = man.get(rel, 0) + 1
    inv["manual_relation_counts"] = man
    inv["manual"] = [{"form": f, "relation": r, "box": b} for f, r, b in MANUAL_REF]
    # sizes of the manually read forms, from the mask: equivalent diameter /
    # w of the ink inside each box
    w = inv["w_px"]
    for e in inv["manual"]:
        x0, y0, x1, y1 = e["box"]
        sub = m[y0:y1, x0:x1]
        e["extent_w"] = round(max(x1 - x0, y1 - y0) / w, 2)
        e["ink_w2"] = round(float(sub.sum()) / (w * w), 1)
    (OUT / "reference.json").write_text(json.dumps(inv, indent=1))
    # overlay (stays in .local: the reference image is not committed)
    ov = Image.fromarray(np.where(m, 90, 235).astype(np.uint8)).convert("RGB")
    d = ImageDraw.Draw(ov)
    col = {"terminal": (220, 40, 40), "interior": (40, 160, 40), "enclosed": (160, 40, 200),
           "adjacent": (30, 90, 220), "free": (230, 150, 0), "junction": (150, 150, 150)}
    for c in comps:
        b = c["bbox"]
        d.rectangle([b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2], outline=col[c["relation"]],
                    width=3 if c["kind"] == "mass" else 1)
    for e in inv["manual"]:
        x0, y0, x1, y1 = e["box"]
        d.rectangle([x0 - 5, y0 - 5, x1 + 5, y1 + 5], outline=col[e["relation"]], width=5)
    ov.save(OUT / "reference_overlay.jpg", quality=85)
    keys = ["w_px", "n", "big_masses", "relation_counts", "relation_by_kind", "size_w_q", "gap_w_q",
            "rel_angle_deg_q", "end_share", "holes_share", "signs_per_w", "manual_relation_counts"]
    print(json.dumps({k: inv[k] for k in keys}, indent=1))


def _dots_one(sid):
    cg.require_generative([sid])
    g, s, info = cg.load_sheet(sid, max_side=2000)
    g, _ = cg.remove_rules(g)
    m, _ = cg.ink_mask(g, **cg.EXTRACT_DEFAULTS)
    w = signs.line_width(m)
    d = signs.measure_dots(m, source=sid, w=w)
    # diacritics sit OFF the writing line: drop small letter pieces lying on
    # the local ink centre line (|offset| < 0.8 w)
    return sid, w, [r for r in d if abs(r["normal_off_w"]) >= 0.8]


def stage_dots():
    OUT.mkdir(parents=True, exist_ok=True)
    ids = cg.require_generative(DOT_SHEETS)          # the gate, before any pixel is read
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_dots_one, ids))
    recs = []
    per = {}
    for sid, w, d in res:
        recs += d
        per[sid] = {"w_px": w, "n": len(d)}
    for r in recs:
        r["centroid"] = [round(v, 2) for v in r["centroid"]]
    (OUT / "dots.json").write_text(json.dumps({"per_sheet": per, "dots": recs}, indent=0))
    print(json.dumps(per, indent=1))
    print("total dots", len(recs))


def stage_fonts():
    """Dot SHAPE from fonts: isolated dotted letters from NEUTRAL_STRINGS
    (fonts are measure-only: shape statistics, never placement)."""
    from shapely.geometry import Polygon
    fonts = {"amiri": "Amiri-Regular.ttf", "arefruqaa": "ArefRuqaa-Regular.ttf",
             "amiritype": "AmiriTypewriter-Regular.ttf"}
    text = "ب ج ي ك ن ش ت ث خ ض ظ غ"
    assert cg.neutral_string_ok(text)
    out = []
    for name, fn in fonts.items():
        path = ROOT / ".local/gesture/corpus/print/fonts" / fn
        if not path.exists():
            continue
        cs = cg.shape_text(path, text)
        polys = [Polygon(c) for c in cs if len(c) >= 3]
        polys = [p if p.is_valid else p.buffer(0) for p in polys]
        amax = max(p.area for p in polys)
        dots = [p for p in polys if p.area < 0.06 * amax]
        out += signs.dot_shape_from_polygons(dots, source=f"font:{name}")
    (OUT / "font_dots.json").write_text(json.dumps(out))
    asp = [r["aspect"] for r in out]
    rh = [r["rhombicity"] for r in out]
    print("font dots", len(out), "aspect q", np.round(np.percentile(asp, [10, 50, 90]), 2),
          "rhombicity q", np.round(np.percentile(rh, [10, 50, 90]), 2))


def load_grammar() -> signs.PlacementGrammar:
    p = OUT / "grammar.json"
    return signs.PlacementGrammar.from_json(json.loads(p.read_text())) if p.exists() else signs.DEFAULT_GRAMMAR


def stage_grammar():
    dots = json.loads((OUT / "dots.json").read_text())["dots"]
    ref = json.loads((OUT / "reference.json").read_text())
    fonts = json.loads((OUT / "font_dots.json").read_text()) if (OUT / "font_dots.json").exists() else []
    refsum = {"relation_counts": ref["manual_relation_counts"],
              "signs_per_w": len(ref["manual"]) / max(ref["skeleton_px"] / ref["w_px"], 1e-9),
              "size_w_by_relation": ref["size_w_by_relation"],
              "end_share": ref["end_share"]}
    g = signs.learn_grammar(dots, reference=refsum, shape_records=fonts)
    # design settings on top of the learned values (results note §3):
    # constellations (13 of the 26 reference forms sit in 4 mixed groups),
    # a heavier size tail, and the sign density doubled — at the measured
    # 0.0057 signs / w a 900 px v6 drawing carries ~10 signs, which read as
    # stray specks on the first sheets
    g.meta["constellation_p"] = 0.6
    g.meta["constellation_r_w"] = 16.0
    g.meta["size_spread"] = 0.4
    g.meta["density_measured"] = g.density
    g.density = 2.0 * g.density
    (OUT / "grammar.json").write_text(json.dumps(g.to_json()))
    q = lambda xs: [round(float(v), 2) for v in np.percentile(xs, [10, 25, 50, 75, 90])] if xs else None  # noqa: E731
    print(json.dumps({"sources": g.sources, "n_dots": len(g.gap_w), "relation_p": g.relation_p,
                      "density_per_w": g.density, "gap_w_q": q(g.gap_w), "size_w_q": q(g.size_w),
                      "side_up": g.side_up, "axis_rel_deg_q": q([math.degrees(a) for a in g.axis_rel]),
                      "cluster_p": g.cluster_p, "pair_angle_deg_q": q([math.degrees(a) for a in g.pair_angle]),
                      "pair_spacing_q": q(g.pair_spacing_w), "along_u_q": q(g.along_u),
                      "font_lozenge_aspect": g.meta.get("lozenge_aspect")}, indent=1))


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def render(lines, placed, size, w, *, ss=2, bg=255, ink=20):
    """Lines drawn with a round pen of width w; signs as plotter paths
    (concentric fills at pen spacing w + monoline parts)."""
    Wd, Hd = size
    img = Image.new("L", (Wd * ss, Hd * ss), bg)
    d = ImageDraw.Draw(img)
    lw = max(int(round(w * ss)), 1)
    r = w * ss / 2

    def poly(p, closed=False):
        q = np.asarray(p, float) * ss
        if closed:
            q = np.vstack([q, q[:1]])
        if len(q) >= 2:
            d.line([tuple(v) for v in q], fill=ink, width=lw, joint="curve")
        for v in (q[0], q[-1]):
            d.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=ink)

    for p in lines:
        poly(getattr(p, "points", p), getattr(p, "closed", False))
    for s in placed:
        paths, closed = signs.sign_paths(s, pen=w * 0.9)
        for p, c in zip(paths, closed):
            poly(p, c)
    return img.resize((Wd, Hd), Image.Resampling.LANCZOS)


def _font(sz=18):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", sz)
    except OSError:
        return ImageFont.load_default()


def _save_jpg(img: Image.Image, path: Path, max_kb=600):
    q = 88
    while True:
        img.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024 or q < 40:
            break
        q -= 8
    print("wrote", path, path.stat().st_size // 1024, "KB")


def stage_catalogue():
    rng = np.random.default_rng(7)
    kinds = list(signs.vocabulary())
    w = 7.0
    cell = 150
    cols = 5
    W = 190 + cols * cell
    H = len(kinds) * cell + 20
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    f = _font(15)
    for i, k in enumerate(kinds):
        rel = signs.vocabulary()[k]["relations"][0]
        d.text((10, i * cell + 50), k, fill=0, font=_font(20))
        d.text((10, i * cell + 76), rel, fill=90, font=f)
        for j in range(cols):
            sg = signs.make_sign(k, rng, w=w)
            cx, cy = 190 + j * cell + cell / 2, i * cell + cell / 2 + 10
            # a host line stub showing the relation
            if rel == "terminal":
                host = [np.array([[cx - 60, cy], [cx - 20, cy]])]
                ps = signs._placed(sg, rel, 0.0, (cx - 20 - 0.3 * w, cy), 0)
            elif rel == "interior":
                host = [np.array([[cx - 65, cy], [cx + 65, cy]])]
                ps = signs._placed(sg, rel, 0.0, (cx, cy), 0)
            else:
                host = [np.array([[cx - 65, cy + 28], [cx + 65, cy + 28]])]
                b = sg.bounds()
                ps = signs._placed(sg, rel, 0.0, (cx - (b[0] + b[2]) / 2, cy + 28 - w * 1.5 - b[3]), 0)
            tile = render(host, [ps], (W, H), w)
            img = Image.fromarray(np.minimum(np.asarray(img), np.asarray(tile)))
            d = ImageDraw.Draw(img)
    _save_jpg(img.convert("RGB"), RESULTS / "signs-catalogue.jpg")


def v6_lines(art: str, seed: int, size=(900, 1200)):
    from gesture import grammar_v6_frozen as gm
    g = gm.Grammar.load(ROOT / f".local/gesture/out/grammar_v6_frozen/grammar_{art}.json")
    dr = gm.generate_drawing(g, np.random.default_rng(seed), size)
    return [s.points for s in dr.strokes]


def tree_lines(seed: int, size=(900, 1200)):
    from gesture import topology
    dr = topology.generate_structure(None, np.random.default_rng(seed), size, kind="oehlen_tree")
    return [s.points for s in dr.strokes]


def _label(img, text):
    d = ImageDraw.Draw(img)
    d.text((14, 10), text, fill=0, font=_font(22))
    return img


def stage_sheets():
    g = load_grammar()
    w = 5.0
    rows = []
    for art, seed in (("matisse", 3), ("hokusai", 5), ("ingres", 2)):
        L = v6_lines(art, seed)
        pl = signs.place_signs(L, np.random.default_rng(seed + 100), g, w=w)
        pr = signs.place_random(L, np.random.default_rng(seed + 200), pl, w=w)
        a = _label(render(L, pl, (900, 1200), w), f"{art} v6 — learned placement ({len(pl)} signs)")
        b = _label(render(L, pr, (900, 1200), w), f"{art} v6 — random placement ({len(pr)})")
        rows.append((a, b))
        print(art, {r: sum(1 for p in pl if p.relation == r) for r in signs.RELATIONS})
    sheet = Image.new("L", (1800, 1200 * len(rows)), 255)
    for i, (a, b) in enumerate(rows):
        sheet.paste(a, (0, i * 1200))
        sheet.paste(b, (900, i * 1200))
    sheet = sheet.resize((1350, 900 * len(rows)), Image.Resampling.LANCZOS)
    _save_jpg(sheet.convert("RGB"), RESULTS / "signs-v6.jpg")
    tiles = []
    for seed in (1, 4):
        L = tree_lines(seed)
        pl = signs.place_signs(L, np.random.default_rng(seed + 300), g, w=w)
        pr = signs.place_random(L, np.random.default_rng(seed + 400), pl, w=w)
        tiles += [_label(render(L, pl, (900, 1200), w), f"oehlen_tree — learned ({len(pl)})"),
                  _label(render(L, pr, (900, 1200), w), f"oehlen_tree — random ({len(pr)})")]
    sheet = Image.new("L", (1800, 2400), 255)
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 2) * 900, (i // 2) * 1200))
    sheet = sheet.resize((1350, 1800), Image.Resampling.LANCZOS)
    _save_jpg(sheet.convert("RGB"), RESULTS / "signs-tree.jpg")


# ---------------------------------------------------------------------------
# blinded judge pairs
# ---------------------------------------------------------------------------

QUESTION = ("Each image shows two panels, A (left) and B (right). In which panel do the small "
            "shapes (dots, drops, blocks, rings, ticks) seem to BELONG to the lines — to say "
            "something, like marks placed in relation to the lines — rather than being scattered "
            "over them? Answer A or B, with a confidence 1-5.")


def _pair_image(a: Image.Image, b: Image.Image, h=760):
    def fit(im):
        s = h / im.height
        return im.resize((int(im.width * s), h), Image.Resampling.LANCZOS)
    a, b = fit(a), fit(b)
    out = Image.new("L", (a.width + b.width + 60, h + 50), 255)
    out.paste(a, (0, 50))
    out.paste(b, (a.width + 60, 50))
    d = ImageDraw.Draw(out)
    d.text((10, 10), "A", fill=0, font=_font(30))
    d.text((a.width + 70, 10), "B", fill=0, font=_font(30))
    d.line([(a.width + 30, 50), (a.width + 30, h + 50)], fill=180, width=2)
    return out.convert("RGB")


def _calib_one(args):
    """Real calligraphy crop with its real dots vs the same crop with its
    dots moved to random places (rotated), each mask re-rendered."""
    sid, seed = args
    cg.require_generative([sid])
    rng = np.random.default_rng(seed)
    g, s, info = cg.load_sheet(sid, max_side=1600)
    g, _ = cg.remove_rules(g)
    m, _ = cg.ink_mask(g, **cg.EXTRACT_DEFAULTS)
    w = signs.line_width(m)
    dots = [r for r in signs.measure_dots(m, source=sid, w=w) if abs(r["normal_off_w"]) >= 0.8]
    if len(dots) < 4:
        return None
    # crop around a dense dot region: the window holding most dots
    H, W = m.shape
    cs = int(min(H, W) * 0.55)
    C = np.array([r["centroid"] for r in dots])
    best = None
    for _ in range(40):
        x0, y0 = int(rng.integers(0, max(W - cs, 1))), int(rng.integers(0, max(H - cs, 1)))
        k = int(np.sum((C[:, 0] >= x0 + 10) & (C[:, 0] < x0 + cs - 10) & (C[:, 1] >= y0 + 10) & (C[:, 1] < y0 + cs - 10)))
        if best is None or k > best[0]:
            best = (k, x0, y0)
    k, x0, y0 = best
    if k < 3:
        return None
    sub = m[y0:y0 + cs, x0:x0 + cs].copy()
    lab, _ = ndi.label(sub, structure=np.ones((3, 3)))
    moved = sub.copy()
    pieces = []
    for r in dots:
        cx, cy = r["centroid"][0] - x0, r["centroid"][1] - y0
        if not (0 <= cx < cs and 0 <= cy < cs):
            continue
        li = lab[int(cy), int(cx)] if sub[int(cy), int(cx)] else 0
        if li == 0:
            continue
        pc = lab == li
        moved &= ~pc
        sl = ndi.find_objects(pc.astype(int))[0]
        pieces.append(pc[sl])
    body = moved.copy()
    for pc in pieces:
        pc = ndi.rotate(pc.astype(float), rng.uniform(0, 360), order=1) > 0.5
        for _ in range(200):
            yy, xx = int(rng.integers(0, cs - pc.shape[0])), int(rng.integers(0, cs - pc.shape[1]))
            win = ndi.binary_dilation(body[yy:yy + pc.shape[0], xx:xx + pc.shape[1]], iterations=int(w))
            if not (win & pc).any():
                moved[yy:yy + pc.shape[0], xx:xx + pc.shape[1]] |= pc
                body[yy:yy + pc.shape[0], xx:xx + pc.shape[1]] |= pc
                break
    to_img = lambda mm: Image.fromarray(np.where(mm, 20, 255).astype(np.uint8))  # noqa: E731
    return sid, to_img(sub), to_img(moved), len(pieces)


def stage_pairs(n_test=12, n_calib=8):
    PAIRS.mkdir(parents=True, exist_ok=True)
    for f in PAIRS.glob("*.jpg"):
        f.unlink()
    g = load_grammar()
    w = 5.0
    rng = np.random.default_rng(2026)
    items = []
    srcs = [("v6", "matisse"), ("v6", "hokusai"), ("v6", "ingres"), ("tree", None)]
    for i in range(n_test):
        kind, art = srcs[i % len(srcs)]
        seed = 1000 + i
        L = v6_lines(art, seed) if kind == "v6" else tree_lines(seed)
        pl = signs.place_signs(L, np.random.default_rng(seed + 1), g, w=w)
        pr = signs.place_random(L, np.random.default_rng(seed + 2), pl, w=w)
        items.append({"cond": "test", "src": f"{kind}:{art or 'tree'}", "seed": seed,
                      "learned": render(L, pl, (900, 1200), w), "random": render(L, pr, (900, 1200), w),
                      "n_signs": [len(pl), len(pr)]})
    calib_ids = cg.require_generative(["met-716305", "wc-05", "wc-15", "met-716307", "wc-13", "wal-W668-74b",
                                       "cma-1983.1115.a", "wc-12"])
    with ProcessPoolExecutor(JOBS) as ex:
        res = [r for r in ex.map(_calib_one, [(s, 77 + j) for j, s in enumerate(calib_ids)]) if r]
    for sid, a, b, k in res[:n_calib]:
        items.append({"cond": "calib", "src": sid, "learned": a, "random": b, "n_signs": [k, k]})
    order = rng.permutation(len(items))
    key = {}
    for idx, j in enumerate(order):
        it = items[j]
        learned_left = bool(rng.random() < 0.5)
        A, B = (it["learned"], it["random"]) if learned_left else (it["random"], it["learned"])
        name = f"pair_{idx:02d}.jpg"
        _pair_image(A, B).save(PAIRS / name, quality=85)
        key[name] = {"cond": it["cond"], "src": it["src"], "belonging": "A" if learned_left else "B",
                     "n_signs": it["n_signs"]}
    (PAIRS / "QUESTION.txt").write_text(QUESTION + "\n")
    KEY.write_text(json.dumps(key, indent=1))
    print("pairs", len(key), "test", sum(1 for v in key.values() if v["cond"] == "test"),
          "calib", sum(1 for v in key.values() if v["cond"] == "calib"), "key", KEY)


# ---------------------------------------------------------------------------
# LINE EVENTS (results/signs-events-2026-10-16.md)
# ---------------------------------------------------------------------------

EV_OUT = ROOT / ".local/gesture/out/signs_events"
EV_PAIRS = ROOT / ".local/gesture/out/blind_events/pairs"
EV_KEY = Path(os.environ.get("EVENTS_KEY", "/tmp/gesture_events_key.json"))
MM_PER_PX = 0.2          # a 900 × 1200 px drawing = 180 × 240 mm
EV_W = 0.6               # sign sizes are in units of the drawn line (pen 0.5 mm inks ≈ 0.6 mm), as in round 6
EV_PEN = 0.5             # mm
EV_PXMM = 5.0            # preview px per mm


def reference_forms() -> list[dict]:
    """The 26 read forms as line events, with extents and centres in w."""
    ref = json.loads((OUT / "reference.json").read_text())
    w = ref["w_px"]
    forms = []
    for (form, rel, box), (site, op, grp) in zip(MANUAL_REF, signs.REFERENCE_EVENTS):
        x0, y0, x1, y1 = box
        forms.append({"form": form, "relation": rel, "site": site, "op": op, "group": grp,
                      "extent_w": max(x1 - x0, y1 - y0) / w, "centre_w": [(x0 + x1) / 2 / w, (y0 + y1) / 2 / w]})
    return forms


def stage_events_grammar():
    EV_OUT.mkdir(parents=True, exist_ok=True)
    ref = json.loads((OUT / "reference.json").read_text())
    fit = json.loads((ROOT / ".local/gesture/out/regime/fit.json").read_text())["reference"]
    dots = json.loads((OUT / "dots.json").read_text())["dots"]
    ms = fit["masses"]
    n_j = int(round(ms["n"] * ms["exits_ge3_share"]))
    thin_to_w = fit["w_thin_px"] / ref["w_px"]
    diam_w = [round(v * thin_to_w, 2) for v in ms["diam_thin_q"]]
    forms = reference_forms()
    g = signs.learn_event_grammar(forms, junction_masses={"n": n_j, "diam_w": diam_w},
                                  skeleton_w=ref["skeleton_px"] / ref["w_px"], dot_records=dots,
                                  auto_sizes={k: ref["size_w_by_relation"].get(k, [])
                                              for k in ("interior", "junction")})
    g.nib_ratio = tuple(round(v, 3) for v in fit["thick_over_thin_q"][:3])
    (EV_OUT / "event_grammar.json").write_text(json.dumps(g.to_json(), indent=1))
    q = lambda xs: [round(float(v), 2) for v in np.percentile(xs, [10, 25, 50, 75, 90])] if xs else None  # noqa: E731
    print(json.dumps({"site_p": g.site_p, "op_p": g.op_p, "density_per_w": g.density, "group_p": g.group_p,
                      "group_sizes": g.group_sizes, "spacing_w_q": q(g.spacing_w),
                      "size_ratio": g.size_ratio, "gap_ratio_q": q(g.gap_ratio), "n_gap": len(g.gap_ratio),
                      "size_w": {k: q(v) for k, v in g.size_w.items()}, "nib_ratio": g.nib_ratio,
                      "meta": g.meta}, indent=1))


def load_event_grammar() -> signs.EventGrammar:
    p = EV_OUT / "event_grammar.json"
    return signs.EventGrammar.from_json(json.loads(p.read_text())) if p.exists() else signs.DEFAULT_EVENT_GRAMMAR


def draw_paths(paths, size_mm, *, pxmm=EV_PXMM, pen=EV_PEN, ss=2, img=None, offset=(0.0, 0.0)):
    """Plotter paths (mm) drawn with a round pen."""
    Wd, Hd = int(size_mm[0] * pxmm), int(size_mm[1] * pxmm)
    big = Image.new("L", (Wd * ss, Hd * ss), 255)
    d = ImageDraw.Draw(big)
    lw = max(int(round(pen * pxmm * ss)), 1)
    r = pen * pxmm * ss / 2
    for p in paths:
        q = (np.asarray(p, float) + offset) * pxmm * ss
        if len(q) >= 2:
            d.line([tuple(v) for v in q], fill=20, width=lw, joint="curve")
        for v in (q[0], q[-1]):
            d.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=20)
    out = big.resize((Wd, Hd), Image.Resampling.LANCZOS)
    if img is not None:
        return Image.fromarray(np.minimum(np.asarray(img), np.asarray(out)))
    return out


def structure_lines(src: str, seed: int):
    """Lines in mm for a structure: v6:<hand>, tree."""
    if src.startswith("v6:"):
        L = v6_lines(src[3:], seed)
    elif src == "tree":
        L = tree_lines(seed)
    else:
        raise ValueError(src)
    return [np.asarray(p, float) * MM_PER_PX for p in L if len(p) >= 2]


def stamp_paths(lines_mm, placed):
    """Round-6 stamps as plotter paths at the events' pen."""
    out = []
    for s in placed:
        paths, closed = signs.sign_paths(s, pen=EV_PEN)
        for p, c in zip(paths, closed):
            out.append(np.vstack([p, p[:1]]) if c else p)
    return [np.asarray(p, float) for p in lines_mm] + out


def event_panel(lines_mm, seed, g, *, mode="grammar", like=None):
    rng = np.random.default_rng(seed)
    evs = signs.plan_events(lines_mm, rng, g, w=EV_W, mode=mode, like=like)
    sts = signs.apply_events(lines_mm, evs, np.random.default_rng(seed + 7), w=EV_W, grammar=g)
    return evs, signs.render_events(sts, EV_PEN)


def _vocab_items():
    """(label, lines, events) for each op on a simple host."""
    t = np.linspace(0, 1, 400)
    wave = np.column_stack([5 + 60 * t, 20 + 3 * np.sin(2 * np.pi * t)])
    E = signs.LineEvent
    w = EV_W
    items = []
    for op, size in (("drop", 5), ("lozenge", 5), ("hook", 9), ("ring", 8), ("block", 11), ("vessel", 24),
                     ("eye", 10), ("detached", 3)):
        items.append((f"end · {op}", [wave], [E("end", op, 0, 0.0, size * w, 1.0, end=1)]))
    for op, size in (("bead", 3.5), ("vessel_mid", 10), ("nib", 8), ("knot", 11), ("comb", 6), ("drip", 8),
                     ("body", 9)):
        items.append((f"interior · {op}", [wave], [E("interior", op, 0, 30.0, size * w, -1.0)]))
    host = np.column_stack([5 + 60 * t, 24 + 0 * t])
    stem = np.column_stack([35 + 0 * t, 4 + 20 * t])
    items.append(("junction · junction_mass", [host, stem],
                  [E("junction", "junction_mass", 1, 20.0, 6 * w, 1.0, other=(0, 30.0))]))
    u = np.linspace(0, 1, 200)
    corner = np.vstack([np.column_stack([5 + 30 * u, 10 + 18 * u]),
                        np.column_stack([35 + 30 * u[1:], 28 - 14 * u[1:]])])
    sc = float(np.sum(np.linalg.norm(np.diff(corner[:200], axis=0), axis=1)))
    items.append(("corner · comma", [corner], [E("corner", "comma", 0, sc, 8 * w, 1.0)]))
    # a line making its own small loop
    a = np.linspace(0, 2 * np.pi, 160)
    v = np.linspace(0, 1, 100)
    loop = np.vstack([np.column_stack([5 + 25 * v, 22 + 0 * v]),
                      np.column_stack([30 + 6 * np.sin(a), 16 + 6 * np.cos(a)]),
                      np.column_stack([30 + 35 * v, 22 + 0 * v])])
    S = signs._Net([loop], w)
    if S.selfloops:
        i, s0, s1, f = S.selfloops[0]
        items.append(("loop · fill_loop", [loop], [E("loop", "fill_loop", 0, (s0 + s1) / 2, 8 * w, 1.0,
                                                     params={"s0": s0, "s1": s1})]))
        c = np.asarray(f.centroid.coords[0])
        items.append(("loop · pupil", [loop], [E("loop", "pupil", 0, (s0 + s1) / 2, 2.5 * w, 1.0,
                                                 params={"s0": s0, "s1": s1, "centre": [c[0], c[1]]})]))
    return items


def _caption(img, xy, text, size=16):
    ImageDraw.Draw(img).text(xy, text, fill=70, font=_font(size))


def stage_events_vocab():
    items = _vocab_items()
    cols, cw, ch = 4, 72.0, 40.0
    rows = int(math.ceil(len(items) / cols))
    sheet = Image.new("L", (int(cols * cw * EV_PXMM), int(rows * ch * EV_PXMM)), 255)
    for k, (lab, lines, evs) in enumerate(items):
        sts = signs.apply_events(lines, evs, np.random.default_rng(k + 3), w=EV_W)
        paths = signs.render_events(sts, EV_PEN)
        off = ((k % cols) * cw, (k // cols) * ch + 4)
        sheet = draw_paths(paths, (cols * cw, rows * ch), img=sheet, offset=off)
        _caption(sheet, (int(off[0] * EV_PXMM) + 8, int((k // cols) * ch * EV_PXMM) + 4), f"{k + 1}. {lab}")
    _save_jpg(sheet.convert("RGB"), RESULTS / "signs-events-vocabulary.jpg")


def _panel_job(args):
    """One rendered panel: (src, seed, kind) → (PIL image, n marks, ops)."""
    src, seed, kind, n_like = args
    g = load_event_grammar()
    L = structure_lines(src, seed)
    evs, paths = event_panel(L, seed, g)
    if kind == "events":
        return draw_paths(paths, (180, 240)), len(evs), [e.op for e in evs]
    if kind == "random_events":
        rnd, rpaths = event_panel(L, seed + 50, g, mode="random", like=evs)
        return draw_paths(rpaths, (180, 240)), len(rnd), [e.op for e in rnd]
    pg = load_grammar()
    # round-6 stamps at matched VISUAL WEIGHT: the stamps' sizes follow
    # round 6's rules in units of w, which leaves them much lighter than the
    # events; scale their w so the sign ink (pixels beyond the bare lines)
    # roughly matches the events', so the judge can't pick on weight alone
    ev_img = draw_paths(paths, (180, 240))
    bare = np.asarray(draw_paths(L, (180, 240))) < 128
    ev_ink = max(int((np.asarray(ev_img) < 128).sum() - bare.sum()), 1)
    w_st = EV_W
    for _ in range(2):
        pl = signs.place_signs(L, np.random.default_rng(seed + 1), pg, w=w_st, n=len(evs))
        st_ink = max(int((np.asarray(draw_paths(stamp_paths(L, pl), (180, 240))) < 128).sum() - bare.sum()), 1)
        w_st = float(np.clip(w_st * math.sqrt(ev_ink / st_ink), EV_W, 4 * EV_W))
    pl = signs.place_signs(L, np.random.default_rng(seed + 1), pg, w=w_st, n=len(evs))
    if kind == "stamps":
        return draw_paths(stamp_paths(L, pl), (180, 240)), len(pl), [p.kind for p in pl]
    if kind == "scatter":
        pr = signs.place_random(L, np.random.default_rng(seed + 2), pl, w=w_st)
        return draw_paths(stamp_paths(L, pr), (180, 240)), len(pr), [p.kind for p in pr]
    raise ValueError(kind)


def stage_events_sheets():
    jobs = []
    for art, seed in (("matisse", 3), ("hokusai", 5), ("ingres", 2)):
        jobs += [(f"v6:{art}", seed, "events", None), (f"v6:{art}", seed, "stamps", None)]
    jobs += [("tree", 1, "events", None), ("tree", 1, "random_events", None),
             ("tree", 4, "events", None), ("tree", 4, "random_events", None)]
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_panel_job, jobs))
    labels = {"events": "line events", "stamps": "round-6 stamps", "random_events": "same events, random places"}
    tiles = []
    for (src, seed, kind, _), (img, n, ops) in zip(jobs, res):
        img = img.convert("L")
        _caption(img, (12, 8), f"{src} seed {seed} — {labels[kind]} ({n})", 20)
        tiles.append(img)
        print(src, seed, kind, n, {o: ops.count(o) for o in sorted(set(ops))})
    for name, part in (("v6", tiles[:6]), ("tree", tiles[6:])):
        rows = len(part) // 2
        sheet = Image.new("L", (1800, 1200 * rows), 255)
        for i, t in enumerate(part):
            sheet.paste(t, ((i % 2) * 900, (i // 2) * 1200))
            ImageDraw.Draw(sheet).line([(900, 0), (900, 1200 * rows)], fill=170, width=2)
        sheet = sheet.resize((1350, 900 * rows), Image.Resampling.LANCZOS)
        _save_jpg(sheet.convert("RGB"), RESULTS / f"signs-events-{name}.jpg")


EV_QUESTION = ("Each image shows two panels, A (left) and B (right), built on the same lines. In which panel "
               "do the small shapes (dots, drops, swellings, knots, hooks, ticks) seem to BELONG to the lines — "
               "to say something? Answer A or B, with a confidence 1-5.")


def stage_events_pairs(n_per=12):
    EV_PAIRS.mkdir(parents=True, exist_ok=True)
    for f in EV_PAIRS.glob("*.jpg"):
        f.unlink()
    srcs = ["v6:matisse", "v6:hokusai", "v6:ingres", "tree"]
    conds = {"a_events_vs_stamps": "stamps", "b_events_vs_random_events": "random_events",
             "c_calib_events_vs_scatter": "scatter"}
    jobs, meta = [], []
    for ci, (cond, other) in enumerate(conds.items()):
        for i in range(n_per):
            src = srcs[i % len(srcs)]
            seed = 3000 + 100 * ci + i
            jobs += [(src, seed, "events", None), (src, seed, other, None)]
            meta.append((cond, src, seed))
    with ProcessPoolExecutor(JOBS) as ex:
        res = list(ex.map(_panel_job, jobs))
    rng = np.random.default_rng(4242)
    order = rng.permutation(len(meta))
    key = {}
    for idx, j in enumerate(order):
        cond, src, seed = meta[j]
        (ev_img, n_ev, _), (ot_img, n_ot, _) = res[2 * j], res[2 * j + 1]
        left = bool(rng.random() < 0.5)
        A, B = (ev_img, ot_img) if left else (ot_img, ev_img)
        name = f"pair_{idx:02d}.jpg"
        _pair_image(A, B).save(EV_PAIRS / name, quality=85)
        key[name] = {"cond": cond, "src": src, "seed": seed, "events_panel": "A" if left else "B",
                     "n_marks": {"events": n_ev, "other": n_ot}}
    (EV_PAIRS / "QUESTION.txt").write_text(EV_QUESTION + "\n")
    EV_KEY.write_text(json.dumps(key, indent=1))
    print("pairs", len(key), {c: sum(1 for v in key.values() if v["cond"] == c) for c in conds}, "key", EV_KEY)


STAGES = {"reference": stage_reference, "dots": stage_dots, "fonts": stage_fonts, "grammar": stage_grammar,
          "catalogue": stage_catalogue, "sheets": stage_sheets, "pairs": stage_pairs,
          "events_grammar": stage_events_grammar, "events_vocab": stage_events_vocab,
          "events_sheets": stage_events_sheets, "events_pairs": stage_events_pairs}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stages", nargs="+", choices=[*STAGES, "all"])
    a = ap.parse_args()
    for s in (list(STAGES) if "all" in a.stages else a.stages):
        print(f"== {s}")
        STAGES[s]()
