"""Round 11, exploration 3: solid abstract script.

Stages (python -m tools.gesture.experiments.script_solid <stage> ...), run
from the repo root with the research venv:

  measure    texture of real writing (calligraphy + Bulaq print, measure-only
             sheets included: statistics only) → corpus.json
  baseline   the round-9/10 shikasta rows (P1) measured the same way
  scripts    the five scripts, rows each, + their texture numbers
  compare    comparison sheet: P1 shikasta rows as cell 1, then the scripts
  threshold  where a row starts to read as writing: sweeps of weight, grouping,
             frequency (+ the seismograph and blob controls), with numbers
  page       a full abstract page (a letter) at the 267×180 frame
  closeup    10 px/mm crops
  combos     script as a margin beside a drawing; script answering a drawing
  legibility enlarged rows for the self-check

Images only. Every sheet made by kit.run + kit.preview (recipe beside it);
contact sheets carry their cell recipes in <name>.recipe.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gesture import kit  # noqa: E402
from gesture.kit import script_solid_measure as tm  # noqa: E402
from gesture.kit.core import Sheet  # noqa: E402

ROOT = HERE.parents[2]
OUT = ROOT / ".local/gesture/out/script_solid"
RES = ROOT / "tools/gesture/results"
NUM: dict = {}
PAPER = (0xFF, 0xFC, 0xF0)
GREY = (0x6F, 0x6E, 0x69)
RED = (0xAF, 0x30, 0x29)

# ---------------------------------------------------------------------------
# the scripts: a hand + a syntax. Each is a grammar, never a font.
# ---------------------------------------------------------------------------

BASE = {"id": "script_solid"}
SCRIPTS = {
    # A: the hanging hand made solid — words slope and cascade, dense overlap, nib dots
    "A_hanging": {**BASE, "hand": "shikasta", "direction": "rtl", "baseline": "hanging", "tilt": 8.0,
                  "nib_angle": 70.0, "nib_w": 0.42, "word_mean": 3.0, "join_gap": 0.08, "word_gap": 0.7,
                  "turn_lo": 1.7, "turn_hi": 3.4, "glyph_w": 1.8, "asc_rate": 0.16, "desc_rate": 0.1,
                  "dots": 0.22, "dot_shape": "nib", "connector_w": 0.9, "inventory": 14},
    # B: a Matisse script — big round bodies, loops, slanted, bead dots, wide spaces
    "B_matisse": {**BASE, "hand": "matisse", "direction": "ltr", "baseline": "wander", "tilt": 10.0,
                  "slant": 14.0, "nib_angle": 30.0, "nib_w": 0.46, "word_mean": 2.6, "join_gap": 0.25,
                  "word_gap": 1.0, "turn_lo": 2.2, "turn_hi": 4.5, "glyph_w": 2.2, "smooth": 0.12, "asc_rate": 0.1,
                  "desc_rate": 0.08, "dots": 0.1, "dot_shape": "bead", "inventory": 12, "zipf": 0.8},
    # C: a dance script (mantis) — short words, sharp turns, baseline ignored often
    "C_dance": {**BASE, "hand": "mime_mantis", "direction": "ltr", "baseline": "wander", "tilt": 22.0,
                "slant": -8.0, "nib_angle": 95.0, "nib_w": 0.4, "word_mean": 2.6, "word_sd": 0.6,
                "join_gap": 0.15, "word_gap": 0.85, "turn_lo": 0.8, "turn_hi": 2.0, "glyph_w": 1.2,
                "asc_rate": 0.2, "desc_rate": 0.12, "ignore": 0.1, "smooth": 0.02, "dots": 0.0, "inventory": 10,
                "jitter": 1.0},
    # D: a machine script (Cohen's meanders; polygon_walk made X/V shapes) — corners, horizontal nib edge (stems thick, bars hair),
    #    ruled, uniform words, flat frequencies
    "D_machine": {**BASE, "hand": "meander69", "simple_only": True, "direction": "ltr", "baseline": "ruled", "slant": 0.0,
                  "nib_angle": 0.0, "nib_w": 0.3, "word_mean": 4.0, "word_sd": 0.25, "join_gap": 0.1,
                  "word_gap": 0.8, "gap_sd": 0.1, "turn_lo": 1.4, "turn_hi": 2.4, "glyph_w": 1.4, "smooth": 0.0,
                  "asc_rate": 0.1, "desc_rate": 0.1, "ignore": 0.0, "dots": 0.0, "zipf": 0.2,
                  "inventory": 9, "jitter": 0.15, "line_end": "compress"},
    # E: a physics script (bubble-chamber tracks) — tight joins, rtl, slight slant. Molnar's hand
    #    was tried here first and produced a readable Latin fragment ("Don"): see results.
    "E_physics": {**BASE, "hand": "bubble", "simple_only": True, "direction": "rtl", "baseline": "ruled", "slant": 6.0,
                  "nib_angle": 45.0, "nib_w": 0.3, "word_mean": 4.5, "join_gap": 0.05, "word_gap": 0.6,
                  "turn_lo": 1.4, "turn_hi": 3.0, "glyph_w": 1.2, "asc_rate": 0.12, "desc_rate": 0.05,
                  "dots": 0.06, "dot_shape": "nib", "inventory": 18},
}
NIB = {"id": "script_solid_nib", "pen": 0.3, "pitch": 0.75}


def save(im: Image.Image, name: str, maxw: int = 1600, quality: int = 86) -> Path:
    if im.width > maxw:
        im = im.resize((maxw, int(im.height * maxw / im.width)), Image.Resampling.LANCZOS)
    p = OUT / f"{name}.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    im.save(p, quality=quality, optimize=True)
    return p


def strip_label(im: Image.Image, text: str, sub: str = "") -> Image.Image:
    fs = max(14, im.width // 70)
    h = int(fs * (3.2 if sub else 1.9))
    t = Image.new("RGB", (im.width, im.height + h), PAPER)
    d = ImageDraw.Draw(t)
    d.text((10, 4), text, fill=(0x10, 0x0F, 0x0F), font=kit.core._font(fs))
    if sub:
        d.text((10, 4 + int(fs * 1.3)), sub, fill=GREY, font=kit.core._font(int(fs * 0.8)))
    t.paste(im, (0, h))
    return t


def mask_of(sheet: Sheet, px_per_mm: float = 10.0, inks=None) -> np.ndarray:
    sub = sheet if inks is None else Sheet(sheet.frame, [], inks, sheet.meta)
    im = kit.render_image(sub, px_per_mm=px_per_mm, label=None).convert("L")
    return np.asarray(im) < 128


def texture(sheet: Sheet, inks=None) -> dict:
    return tm.summarize(tm.measure(mask_of(sheet, 10.0, inks)))


def corpus_ref() -> dict:
    return json.loads((OUT / "corpus.json").read_text())


def tex_line(s: dict) -> str:
    def g(k, f="{:.2f}"):
        v = s.get(k)
        return f.format(v[0]) if v else "–"
    return (f"band cov {g('cov_core')}  runs/10W {g('freq_W', '{:.1f}')}  x-height {g('Hb_W', '{:.1f}')} W  "
            f"word {g('word_W', '{:.0f}')} W (cv {g('word_cv')})  space {g('gap_W', '{:.1f}')} W  "
            f"contrast {g('contrast', '{:.1f}')}  colfill {g('colfill')}")


def dist_all(s: dict, ref: dict) -> dict:
    return {g: round(tm.distance(s, ref["genres"][g]), 2) for g in sorted(ref["genres"])}


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------

def stage_measure():
    from experiments import script_syntax as SX  # noqa: PLC0415  (sheet loading + baseline angles, read only)
    jobs = [(g, s) for g, ids in SX.CALL_SHEETS.items() for s in ids if s not in SX.SKIP]
    jobs += [("bulaq_print", p) for p in SX.PRINT_PAGES]
    per = {}
    for genre, sid in jobs:
        t = time.time()
        try:
            m, _ = SX.sheet_mask(sid)
        except Exception as e:  # noqa: BLE001
            print("skip", sid, e)
            continue
        a = SX.ANGLES.get(sid)
        if a is None:
            from gesture import script_syntax as ss  # noqa: PLC0415
            a = ss.baseline_angle(m, ss.pen_width(m), span=12.0)
        recs = tm.measure(m, angle=a)
        per.setdefault(genre, []).extend(recs)
        print(f"{genre:12s} {sid:16s} angle {a:+.0f} lines {len(recs):3d}  {time.time() - t:.1f}s", flush=True)
    out = {"genres": {g: tm.summarize(r) for g, r in per.items()},
           "all": tm.summarize([x for r in per.values() for x in r]),
           "note": "measure-only statistics; Qur'anic/devotional sheets included as numbers only"}
    # a pooled 'calligraphy' reference (hand-written genres, not print)
    out["genres"]["all_hand"] = tm.summarize([x for g, r in per.items() if g != "bulaq_print" for x in r])
    (OUT / "corpus.json").write_text(json.dumps(out, indent=1))
    for g, s in out["genres"].items():
        print(f"{g:12s} n={s['lines']:4d}  {tex_line(s)}")


def p1_sheet():
    rec = json.loads((ROOT / ".local/gesture/out/polyphonic_sheets/page-P1-interlinear.recipe.json").read_text())
    return kit.run(rec)


def p1_rows(sh):
    body = [k for k in sh.inks if k.meta.get("part") == 0]
    yc = np.array([float(np.mean(k.points[:, 1])) for k in body])
    order = np.argsort(yc)
    rows, cur = [], [order[0]]
    for a, b in zip(order[:-1], order[1:]):
        if yc[b] - yc[a] > 4.0:
            rows.append(cur)
            cur = []
        cur.append(b)
    rows.append(cur)
    return [[body[i] for i in r] for r in rows if len(r) >= 4]


def stage_baseline():
    sh = p1_sheet()
    rows = p1_rows(sh)
    allrecs = []
    for inks in rows:
        allrecs += tm.measure(mask_of(sh, 10.0, inks))
    s = tm.summarize(allrecs)
    NUM["baseline_P1_shikasta"] = {"texture": s, "dist": dist_all(s, corpus_ref())}
    print("P1 shikasta rows:", tex_line(s))
    print("  distance:", NUM["baseline_P1_shikasta"]["dist"])


def row_recipe(name: str, spec: dict, *, seed: int = 11000, rows: int = 3, frame=(267.0, 70.0), x=6.5,
               renderer=None, **kw) -> dict:
    v = {**spec, "x_height": x, "rows": rows, "leading": 3.0, **kw}
    return {"label": f"script {name}", "frame": list(frame), "seed": seed, "margin": 6.0, "voice": v,
            "renderer": renderer or NIB}


def stage_scripts():
    ref = corpus_ref()
    for name, spec in SCRIPTS.items():
        t = time.time()
        sh = kit.run(row_recipe(name, spec))
        kit.preview(sh, OUT / f"scripts/{name}.jpg", px_per_mm=6, label=f"{name}  ({spec['hand']})")
        s = texture(sh)
        NUM.setdefault("scripts", {})[name] = {"texture": s, "dist": dist_all(s, ref),
                                               "seconds": round(time.time() - t, 1)}
        print(f"{name:10s} {time.time() - t:5.1f}s  {tex_line(s)}")
        print("           dist", NUM["scripts"][name]["dist"])


def _crop_strip(sh, y0, y1, px=8):
    im = kit.render_image(sh, px_per_mm=px, label=None)
    return im.crop((0, max(int(y0 * px), 0), im.width, min(int(y1 * px), im.height)))


def stage_compare():
    ref = corpus_ref()
    cells, recipes = [], {}
    sh = p1_sheet()
    rows = p1_rows(sh)
    inks = [k for r in rows[:3] for k in r]
    ys = np.vstack([k.points for k in inks])[:, 1]
    sub = Sheet(sh.frame, [], inks, sh.meta)
    s = tm.summarize([x for r in rows for x in tm.measure(mask_of(sh, 10.0, r))])
    cells.append(strip_label(_crop_strip(sub, ys.min() - 3, ys.max() + 3),
                             "1  round 9/10: P1 shikasta rows (nib c, W 1.4 mm) — 'boring and blocky'", tex_line(s)))
    recipes["1_P1_shikasta"] = sh.recipe
    for i, (name, spec) in enumerate(SCRIPTS.items(), start=2):
        r = row_recipe(name, spec)
        sh = kit.run(r)
        s = texture(sh)
        d = tm.distance(s, ref["genres"]["all_hand"])
        cells.append(strip_label(kit.render_image(sh, px_per_mm=8, label=None),
                                 f"{i}  {name}  (hand: {spec['hand']}; nib {spec['nib_angle']:.0f}°, "
                                 f"W {spec['nib_w']:.2f}·x)", tex_line(s) + f"   texture distance to hand-written "
                                                                           f"pages {d:.2f}"))
        recipes[f"{i}_{name}"] = sh.recipe
    W = max(c.width for c in cells)
    cells = [c if c.width == W else c.resize((W, int(c.height * W / c.width))) for c in cells]
    im = kit.contact(cells, 1, title="Solid abstract script — comparison (cell 1 = what Ian called blocky)")
    save(im, "compare", maxw=1800)
    (OUT / "compare.recipe.json").write_text(json.dumps(recipes, indent=1))


# ---------------------------------------------------------------------------
# legibility: an OCR probe (tesseract, English model only — the machine
# check is Latin-only; Arabic is checked by eye) + positive controls
# ---------------------------------------------------------------------------

def _dict_words() -> set:
    p = Path("/usr/share/dict/words")
    return {w.strip().lower() for w in p.read_text().split() if len(w.strip()) >= 3} if p.exists() else set()


def ocr(im: Image.Image, tag: str) -> dict:
    import subprocess  # noqa: PLC0415
    d = OUT / "ocr"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{tag}.png"
    im.convert("L").save(f)
    r = subprocess.run(["tesseract", str(f), "stdout", "--psm", "6", "tsv"], capture_output=True, text=True,
                       timeout=300)
    words = _dict_words()
    toks = []
    for ln in r.stdout.splitlines()[1:]:
        c = ln.split("\t")
        if len(c) == 12 and c[11].strip():
            toks.append((c[11].strip(), float(c[10])))
    alpha = [(t, cf) for t, cf in toks if t.isalpha()]
    conf = [(t, cf) for t, cf in alpha if cf >= 60]
    real = sorted({t.lower() for t, cf in conf if t.lower() in words})
    return {"tokens": len(toks), "alpha": len(alpha), "alpha_conf60": len(conf), "dict_words_conf60": real,
            "median_conf": float(np.median([cf for _, cf in toks])) if toks else None}


def control_image(font: str, text: str, px: int = 64) -> Image.Image:
    from PIL import ImageFont  # noqa: PLC0415
    f = ImageFont.truetype(font, px)
    im = Image.new("RGB", (2400, int(px * 1.8 * 3)), PAPER)
    d = ImageDraw.Draw(im)
    for i in range(3):
        d.text((20, int(10 + i * px * 1.7)), text[i * 48:(i + 1) * 48], fill=(0x10, 0x0F, 0x0F), font=f)
    return im


CONTROL_TEXT = ("the quick brown fox jumps over the lazy dog while a small letter waits "
                "on the table near the open window and nobody reads it aloud today")


def stage_evidence():
    """The legibility failures, cropped at 10 px/mm, for the self-check."""
    cells = []
    # 1. Molnar's hand (first E script): a 'Do…' fragment
    mol = {**SCRIPTS["E_physics"], "hand": "molnar_letters", "simple_only": False, "turn_lo": 1.4,
           "turn_hi": 3.0, "glyph_w": 1.2, "join": "row"}
    sh = kit.run(row_recipe("molnar", mol, rows=4, frame=(267.0, 100.0)))
    rec1 = sh.recipe
    im = kit.render_image(sh, px_per_mm=10, label=None)
    cells.append(strip_label(im.crop((1150, 330, 2650, 760)), "1  E with Molnar's hand, rows joined: reads 'Don…' "
                                                              "(tesseract said 'daring', conf 61)"))
    # 2. the physics script as a letter: 'bit', 'Und'
    rec = page_recipes()["page-letter"]
    rec = json.loads(json.dumps(rec))
    for p_ in rec["parts"]:
        p_["voice"].update({k: v for k, v in SCRIPTS["E_physics"].items() if k not in ("x_height", "rows")})
        p_["voice"]["simple_only"] = False
    sh = kit.run(rec)
    im = kit.render_image(sh, px_per_mm=10, label=None)
    cells.append(strip_label(im.crop((1150, 950, 2650, 1250)), "2  E (bubble hand) as a letter: Latin letter pairs "
                                                               "('de', 'ne', 'ue') by eye; an earlier run showed "
                                                               "'bit', 'Und'; OCR found nothing"))
    save(kit.contact(cells, 1, title="Legibility failures kept as evidence (10 px/mm)"), "legibility-evidence",
         maxw=1500)
    (OUT / "legibility-evidence.recipe.json").write_text(json.dumps({"1": rec1, "2": sh.recipe}, indent=1))


def stage_legibility():
    out = {}
    for name, font in (("control_chancery", "/System/Library/Fonts/Supplemental/Apple Chancery.ttf"),
                       ("control_brush", "/System/Library/Fonts/Supplemental/Brush Script.ttf"),
                       ("control_bradley", "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf")):
        try:
            out[name] = ocr(control_image(font, CONTROL_TEXT), name)
        except OSError as e:
            out[name] = {"error": str(e)}
        print(name, out[name])
    for name, spec in SCRIPTS.items():
        for join in ("word", "row"):
            sh = kit.run(row_recipe(name, {**spec, "join": join}, rows=4, frame=(267.0, 100.0)))
            im = kit.render_image(sh, px_per_mm=8, label=None)
            for mir in (False, True):
                k = f"{name}_{join}" + ("_mirrored" if mir else "")
                out[k] = ocr(im.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if mir else im, k)
                print(k, out[k])
    for name, rec in {**page_recipes(), **combo_recipes()}.items():
        im = kit.render_image(kit.run(rec), px_per_mm=8, label=None)
        for mir in (False, True):
            k = name + ("_mirrored" if mir else "")
            out[k] = ocr(im.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if mir else im, k)
            print(k, out[k])
    NUM["legibility_ocr"] = out


def _one_row(spec, **kw):
    return row_recipe("sweep", spec, rows=1, frame=(267.0, 30.0), x=6.0, **kw)


SWEEPS = {
    "weight": [(f"nib_w {w:.2f}·x", {"nib_w": w}) for w in (0.06, 0.12, 0.2, 0.3, 0.42, 0.6, 0.85)],
    "grouping": [
        ("seismograph: one line, even spacing, no words", {"join": "row", "kashida_w": 0.7, "word_gap": 0.2,
                                                            "gap_sd": 0.0, "word_sd": 0.0}),
        ("confetti: lone glyphs (the P1 condition)", {"min_glyphs": 1, "word_mean": 1.0, "word_sd": 0.0,
                                                      "word_gap": 1.1}),
        ("even words, even spaces", {"word_sd": 0.0, "gap_sd": 0.0}),
        ("grouped (default)", {}),
        ("grouped, wild spacing", {"word_sd": 0.9, "gap_sd": 0.9}),
        ("long words", {"word_mean": 7.0, "word_gap": 1.1}),
        ("row as one line (kashidas)", {"join": "row"}),
        ("no alphabet: every glyph a fresh window, no recurrence", {"inventory": 48, "zipf": 0.0}),
        ("true seismograph: no alphabet, one even line", {"inventory": 48, "zipf": 0.0, "join": "row",
                                                           "kashida_w": 0.7, "word_gap": 0.2, "gap_sd": 0.0,
                                                           "word_sd": 0.0, "asc_rate": 0.0, "desc_rate": 0.0,
                                                           "dots": 0.0}),
        ("no baseline (wander 40°)", {"baseline": "wander", "tilt": 40.0, "ignore": 0.5}),
    ],
    "frequency": [(f"glyph_w {g:.1f}", {"glyph_w": g}) for g in (0.5, 0.8, 1.2, 1.8, 2.6, 3.6)],
}


def stage_threshold(only=None):
    ref = corpus_ref()["genres"]["all_hand"]
    base = SCRIPTS["A_hanging"]
    for sweep, cells in SWEEPS.items():
        if only and sweep not in only:
            continue
        ims, recs, nums = [], {}, []
        for i, (lab, over) in enumerate(cells):
            r = _one_row({**base, **over})
            sh = kit.run(r)
            kit.preview(sh, OUT / f"threshold/{sweep}-{i}.jpg", px_per_mm=6, label=lab)
            s = texture(sh)
            d = tm.distance(s, ref)
            nums.append({"cell": lab, "texture": s, "dist_all_hand": round(d, 2)})
            ims.append(strip_label(kit.render_image(sh, px_per_mm=6, label=None), f"{chr(97 + i)}  {lab}",
                                   tex_line(s) + f"   distance {d:.2f}"))
            recs[f"{chr(97 + i)}"] = sh.recipe
            print(f"{sweep:9s} {lab:44s} d={d:.2f}  {tex_line(s)}", flush=True)
        im = kit.contact(ims, 1, title=f"Threshold: {sweep} (script A, one row; hand-written pages: band cov "
                                       f"{ref['cov_core'][0]:.2f}, runs/10W {ref['freq_W'][0]:.1f}, "
                                       f"colfill {ref['colfill'][0]:.2f}, contrast {ref['contrast'][0]:.1f})")
        save(im, f"threshold-{sweep}", maxw=1600)
        (OUT / f"threshold-{sweep}.recipe.json").write_text(json.dumps(recs, indent=1))
        NUM.setdefault("threshold", {})[sweep] = nums


WIRE = {"id": "wire", "pen": 0.35}


def _part(spec, renderer=None, **kw):
    return {"voice": {**spec, **kw}, "modulators": [], "renderer": renderer or NIB}


def page_recipes() -> dict:
    A, B = SCRIPTS["A_hanging"], SCRIPTS["B_matisse"]
    E_ = {**SCRIPTS["D_machine"], "direction": "rtl", "dots": 0.06, "dot_shape": "nib", "line_end": "both"}
    return {
        # a letter: a heading row, the body, a closing block with a swash (physics script)
        "page-letter": {"label": "a letter in the machine script (Cohen meander hand): heading, body, closing",
                        "frame": [267.0, 180.0], "seed": 11300, "margin": 12.0,
                        "arranger": {"id": "script_solid_stack", "heights": [0.13, 0.72, 0.15],
                                     "insets": [0.35, 0.0, 0.0], "right": [0.0, 0.0, 0.5]},
                        "parts": [_part(E_, x_height=7.5, rows=1, line_end="none"),
                                  _part(E_, x_height=4.6, leading=2.5, indent=True, swash_rate=0.08),
                                  _part(E_, x_height=4.6, leading=2.5, rows=2, line_end="swash")]},
        # a manuscript page: the hanging script, rows joined as one line each, a diagonal marginal gloss
        "page-manuscript": {"label": "a manuscript page: script A as joined rows + a diagonal marginal gloss",
                            "frame": [267.0, 180.0], "seed": 11310, "margin": 10.0,
                            "arranger": {"id": "script_solid_page", "layout": "diagonal", "split": 0.7,
                                         "side": "left", "clear": 6.0, "angle": 50.0},
                            "parts": [_part(A, x_height=5.2, leading=2.7, join="row", tilt=6.0),
                                      _part(A, x_height=3.4, leading=2.4, join="word", tilt=4.0,
                                            asc_rate=0.1)]},
        # Matisse script, word mode, a full page
        "page-matisse": {"label": "a page of the Matisse script", "frame": [267.0, 180.0], "seed": 11320,
                         "margin": 12.0, "voice": {**B, "x_height": 5.5, "leading": 2.7, "indent": True},
                         "renderer": NIB},
    }


def stage_page():
    ref = corpus_ref()["genres"]["all_hand"]
    for name, rec in page_recipes().items():
        t = time.time()
        sh = kit.run(rec)
        kit.preview(sh, OUT / f"{name}.jpg", px_per_mm=6, label=rec["label"])
        s = tm.summarize(tm.measure(mask_of(sh, 10.0)))
        cov = float(mask_of(sh, 4.0).mean())
        NUM.setdefault("pages", {})[name] = {"texture": s, "dist_all_hand": round(tm.distance(s, ref), 2),
                                             "page_coverage": round(cov, 3), "inks": len(sh.inks),
                                             "seconds": round(time.time() - t, 1)}
        print(f"{name:16s} {time.time() - t:5.1f}s inks {len(sh.inks)} page cov {cov:.3f}  {tex_line(s)}")


def stage_closeup():
    for name, box in (("page-manuscript", (150, 20, 100, 50)), ("page-letter", (14, 40, 100, 50))):
        rec = page_recipes()[name]
        sh = kit.run(rec)
        im = kit.render_image(sh, px_per_mm=10, label=None)
        x, y, w, h = box
        c = im.crop((x * 10, y * 10, (x + w) * 10, (y + h) * 10))
        c = strip_label(c, f"close-up 10 px/mm: {name}, x {x}–{x + w} mm, y {y}–{y + h} mm",
                        "pen 0.3 mm; thick parts are contour-parallel insets joined into paths; centreline = hairline")
        save(c, f"closeup-{name.split('-')[1]}", maxw=1000)
        sh.save_recipe(OUT / f"closeup-{name.split('-')[1]}.recipe.json")


def combo_recipes() -> dict:
    B, C = SCRIPTS["B_matisse"], SCRIPTS["C_dance"]
    return {
        "combo-margin": {"label": "a loose Matisse drawing + its own script in the margin",
                         "frame": [267.0, 180.0], "seed": 11400, "margin": 10.0,
                         "arranger": {"id": "script_solid_page", "layout": "margin", "split": 0.66,
                                      "side": "right", "clear": 8.0},
                         "parts": [{"voice": {"id": "hand", "hand": "matisse", "length": 7.0}, "modulators": [],
                                    "renderer": WIRE},
                                   _part(B, x_height=4.2, leading=2.6, glyph_w=1.7, direction="rtl")]},
        "combo-answer": {"label": "a mantis dance drawing; the dance script answers around it",
                         "frame": [267.0, 180.0], "seed": 11410, "margin": 10.0,
                         "arranger": {"id": "script_solid_page", "layout": "wrap", "clear": 5.0,
                                      "drawing_box": [0.3, 0.12, 0.42, 0.72]},
                         "parts": [{"voice": {"id": "hand", "hand": "mime_mantis", "length": 5.0}, "modulators": [],
                                    "renderer": WIRE},
                                   _part(C, x_height=4.6, leading=2.5, direction="ltr")]},
        "combo-machine": {"label": "a Cohen meander drawing; the machine script wraps it",
                          "frame": [267.0, 180.0], "seed": 11420, "margin": 10.0,
                          "arranger": {"id": "script_solid_page", "layout": "wrap", "clear": 4.0,
                                       "drawing_box": [0.05, 0.08, 0.5, 0.6]},
                          "parts": [{"voice": {"id": "hand", "hand": "meander69", "length": 4.0}, "modulators": [],
                                     "renderer": WIRE},
                                    _part(SCRIPTS["D_machine"], x_height=4.2, leading=2.4)]},
    }


def stage_combos():
    for name, rec in combo_recipes().items():
        t = time.time()
        sh = kit.run(rec)
        kit.preview(sh, OUT / f"{name}.jpg", px_per_mm=6, label=rec["label"])
        print(f"{name:14s} {time.time() - t:5.1f}s inks {len(sh.inks)}")


RADICAL = {
    "a_rowline_A": ("A: each row ONE continuous line (hairline kashidas)", "A_hanging", {"join": "row"}, None),
    "b_rowline_B": ("B: Matisse script, each row one line", "B_matisse", {"join": "row"}, None),
    "c_bar_word_A": ("A carved: words close into round slugs, the writing white", "A_hanging", {},
                     {"id": "script_solid_bar", "merge": "word"}),
    "d_bar_word_D": ("D carved: machine words as slugs", "D_machine", {},
                     {"id": "script_solid_bar", "merge": "word", "swell": 0.35, "carve": 0.35}),
    "e_bar_row_E": ("E carved: each row one black bar", "E_physics", {},
                    {"id": "script_solid_bar", "merge": "row", "swell": 0.7}),
    "f_bar_row_A_rowline": ("A rows as one line, then carved out of one bar", "A_hanging", {"join": "row"},
                            {"id": "script_solid_bar", "merge": "row", "swell": 0.55, "carve": 0.6}),
}


def stage_radical():
    ims, recs = [], {}
    for key, (lab, sc, over, rnd) in RADICAL.items():
        r = row_recipe(key, {**SCRIPTS[sc], **over}, renderer=rnd)
        sh = kit.run(r)
        kit.preview(sh, OUT / f"radical/{key}.jpg", px_per_mm=6, label=lab)
        s = texture(sh)
        NUM.setdefault("radical", {})[key] = {"texture": s}
        ims.append(strip_label(kit.render_image(sh, px_per_mm=6, label=None), f"{key[0]}  {lab}", tex_line(s)))
        recs[key] = sh.recipe
        print(key, tex_line(s))
    save(kit.contact(ims, 1, title="Radical moves: the row as one line; the writing carved out of black"),
         "radical", maxw=1600)
    (OUT / "radical.recipe.json").write_text(json.dumps(recs, indent=1))


STAGES = {"evidence": stage_evidence, "page": stage_page, "closeup": stage_closeup, "combos": stage_combos, "radical": stage_radical,
          "threshold": stage_threshold, "legibility": stage_legibility, "measure": stage_measure, "baseline": stage_baseline, "scripts": stage_scripts,
          "compare": stage_compare}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    todo = sys.argv[1:] or list(STAGES)
    for st in todo:
        print(f"== {st}", flush=True)
        STAGES[st.split(":")[0]](*([st.split(":")[1].split(",")] if ":" in st else []))
    p = OUT / "numbers.json"
    old = json.loads(p.read_text()) if p.exists() else {}
    old.update(NUM)
    p.write_text(json.dumps(old, indent=1, default=str))
