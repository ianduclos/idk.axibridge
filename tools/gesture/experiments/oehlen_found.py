"""Round 12, thread oehlen_found: D1 found ground + D2 cover cuts (after Oehlen's works on paper).

    .local/gesture/.venv/bin/python tools/gesture/experiments/oehlen_found.py <name> [<name> ...]

Each name is a recipe builder below; images go to .local/gesture/out/oehlen_found/
with the recipe beside each. Write-up: tools/gesture/results/oehlen_found-2026-10-17.md.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_oehlen_found as of  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/oehlen_found"
FRAME = [205.0, 297.0]     # portrait, 1:1 with Oehlen's 2013 collage-drawing (29.7 × 20.5 cm)


def plate(hand="hokusai", length=4.0, plate_kind="taxonomy", split=0.4, page="diptych"):
    """The project's own printed matter: a measurement plate (numbered atlas)."""
    return {"voice": {"id": "hand", "hand": hand, "length": length},
            "modulators": [{"id": "measure_next", "cut": "inflection", "plate": plate_kind, "page": "diptych",
                            "families": 5, "straight": "rules+labels", "hist": "none",
                            "split": split}]}


def river(tile="SB19", rank=0, start=0.0, span_w=1600, angle=0.0):
    return {"voice": {"id": "oehlen_found_river", "tile": tile, "rank": rank, "start": start, "span_w": span_w,
                      "angle": angle}}


def hand(h, length=5.0, joins="smooth"):
    return {"voice": {"id": "hand", "hand": h, "length": length, "joins": joins}}


def base(seed, parts, **arr):
    a = {"id": "oehlen_found"}
    a.update(arr)
    return {"label": "oehlen_found", "frame": FRAME, "seed": seed, "margin": 10.0, "arranger": a,
            "parts": parts, "renderer": {"id": "oehlen_found_ink"}}


RECIPES = {}


def recipe(fn):
    RECIPES[fn.__name__] = fn
    return fn


@recipe
def v1():
    return base(2611, [plate(), river(span_w=1600, angle=-25), hand("ingres", 5.0), hand("marden", 4.0)],
                found=2, late=1,
                found_boxes=[0.55, 0.33, 0.78, 0.5, -4.0, 0.42, 0.72, 0.62, 0.22, 7.0], crop=1.15)


@recipe
def v2():
    return base(2611, [plate(), river(span_w=2400, angle=0), hand("ingres", 5.0), hand("marden", 4.0)],
                found=2, late=1,
                found_boxes=[0.42, 0.27, 0.72, 0.36, -3.0, 0.55, 0.64, 0.98, 0.26, -16.0], crop=1.0)


@recipe
def v3():
    return base(2611, [plate(length=4.0), river(span_w=2400, angle=0), hand("ingres", 5.0), hand("hokusai", 2.0)],
                found=2, late=1,
                found_boxes=[0.5, 0.40, 0.88, 0.62, -2.5, 0.5, 0.56, 0.92, 0.15, -12.0], crop=1.0,
                made_box=[0.5, 0.42, 0.9, 0.62], late_box=[0.5, 0.66, 0.92, 0.5],
                cover_boxes=[0.5, 0.88, 1.3, 0.4, 2.0, 1, 0, 0.72, 0.30, 0.30, 0.2, 9.0, 2, 0],
                capture=5.0, align=0.6, ride=30.0, listen=50.0, ignore=60.0)


@recipe
def v4():
    r = v3()
    r["parts"] = [plate(length=4.0), river(span_w=2400, angle=0), hand("ingres", 5.0), hand("trail_miner", 4.0),
                  hand("dance_thrusting", 2.0)]
    r["arranger"].update(found=2, late=1, made_pen=0.45, late_pen=0.8,
                         cover_boxes=[0.5, 0.88, 1.3, 0.4, 2.0, 1, 0,
                                      0.30, 0.50, 0.36, 0.24, -7.0, 5, 1])
    return r


@recipe
def v5():
    r = v4()
    r["parts"].pop(3)
    r["arranger"].update(ride_gap=0.9, late_box=[0.5, 0.62, 0.92, 0.42],
                         cover_boxes=[0.52, 0.42, 0.12, 0.66, 7.0, 4, 0,
                                      0.76, 0.58, 0.40, 0.22, 6.0, 5, 1])
    return r


@recipe
def v6():
    r = v5()
    r["seed"] = 8317
    r["arranger"].update(cover_boxes=[0.78, 0.40, 0.10, 0.62, 5.0, 4, 0,
                                      0.30, 0.60, 0.40, 0.20, -6.0, 5, 1])
    return r


@recipe
def v7():
    r = v6()
    r["seed"] = 3907
    r["parts"] = [plate(length=4.0, split=0.68), river(span_w=2400, angle=0), hand("river_bend", 5.0),
                  hand("dance_thrusting", 3.0)]
    return r


@recipe
def v8():
    r = v7()
    r["arranger"].update(capture=7.0, align=0.5, ride=35.0, listen=60.0, ignore=50.0, grow_reach=120.0,
                         min_ride=12.0)
    return r


@recipe
def v9():
    """One bold gesture over printed matter: the plate + the far river are found; the only made line is
    drawn last, grows out of a found contour, rides found contours and the covers' edges."""
    return base(3907, [plate(length=4.0, split=0.6), river(span_w=2400, angle=0), hand("dance_thrusting", 3.0)],
                found=2, late=1,
                found_boxes=[0.5, 0.40, 0.9, 0.66, -2.5, 0.5, 0.60, 0.95, 0.15, -10.0], crop=1.0,
                late_box=[0.5, 0.55, 0.9, 0.7],
                cover_boxes=[0.70, 0.36, 0.13, 0.62, 6.0, 4, 0,
                             0.30, 0.62, 0.40, 0.20, -6.0, 5, 1],
                late_borrow="all", late_grow=True, late_capture=6.0, align=0.5, ride=35.0, ride_gap=0.9,
                min_ride=12.0, listen=60.0, ignore=50.0, grow_reach=120.0, late_pen=0.9)


@recipe
def v10():
    """v9 at seed 4441: the cut strip across the river band, the plastic sheet over the plate's drawing."""
    r = v9()
    r["seed"] = 4441
    r["arranger"].update(late_grow=False, cover_boxes=[0.66, 0.55, 0.09, 0.36, 12.0, 4, 0,
                                                       0.30, 0.40, 0.42, 0.22, -5.0, 5, 1])
    return r


def build(name: str, recipe_: dict | None = None, *, crop=None, px=6.0):
    r = recipe_ or RECIPES[name]()
    sh = kit.run(r)
    p = of.save(sh, OUT / f"{name}.jpg", px_per_mm=px, crop=crop)
    log = sh.marks[0].meta.get("oehlen_found", {}) if sh.marks else {}
    (OUT / f"{name}.log.json").write_text(json.dumps(log, indent=1))
    return sh, p, log


def debug(sheet, path, px=4.0):
    """The colour preview with the covers (red) and the rides (orange) shown."""
    from PIL import ImageDraw
    import numpy as np
    im = of.render_colour(sheet, px_per_mm=px)
    dr = ImageDraw.Draw(im)
    log = sheet.marks[0].meta.get("oehlen_found", {})
    for c in log.get("covers", []):
        q = np.asarray(c["polygon"]) * px
        dr.line([tuple(v) for v in q], fill=(0xD1, 0x4D, 0x41), width=2)
    for m in sheet.marks:
        if "neg" in m.channels:
            g = np.asarray(m["neg"])
            P = m.points * px
            for i in range(len(P) - 1):
                if g[i] > 0 and g[i + 1] > 0:
                    dr.line([tuple(P[i]), tuple(P[i + 1])], fill=(0xDA, 0x70, 0x2C) if g[i] == 1 else (0x87, 0x9A, 0x39), width=4)
    im.save(path, quality=85)
    return path


# ---------------------------------------------------------------------------
# the review images (tools/gesture/results/oehlen_found-*.jpg, recipes beside)
# ---------------------------------------------------------------------------

RES = HERE / "results"
REF = ROOT / ".local/gesture/corpus/artists/albert_oehlen"


def _captioned(im, text, fs=None):
    from PIL import Image, ImageDraw
    fs = fs or max(13, im.width // 48)
    font = kit.core._font(fs)
    lines = text.split("\n")
    h = int(fs * 1.35 * len(lines) + fs * 0.9)
    out = Image.new("RGB", (im.width, im.height + h), kit.core.PAPER)
    out.paste(im, (0, 0))
    dr = ImageDraw.Draw(out)
    for i, ln in enumerate(lines):
        dr.text((int(fs * 0.5), im.height + int(fs * 0.45 + i * fs * 1.35)), ln, fill=kit.core.INK, font=font)
    return out


def _row(ims, gap=24, bg=None):
    from PIL import Image
    h = max(i.height for i in ims)
    out = Image.new("RGB", (sum(i.width for i in ims) + gap * (len(ims) + 1), h + 2 * gap), bg or kit.core.PAPER)
    x = gap
    for i in ims:
        out.paste(i, (x, gap))
        x += i.width + gap
    return out


def _fit(im, long_side=2400):
    im = im.copy()
    im.thumbnail((long_side, long_side))
    return im


def _save(im, name, recipe):
    p = RES / f"oehlen_found-{name}.jpg"
    _fit(im).save(p, quality=88, optimize=True)
    (RES / f"oehlen_found-{name}.recipe.json").write_text(json.dumps(recipe, indent=1) + "\n")
    return p


def stages():
    """The procedure in four recipes: pasted / covered / the gesture as drawn / negotiated."""
    r = v10()
    a = copy.deepcopy(r)
    a["parts"] = a["parts"][:2]
    a["arranger"].update(late=0, cover_boxes=[])
    b = copy.deepcopy(a)
    b["arranger"]["cover_boxes"] = r["arranger"]["cover_boxes"]
    c = copy.deepcopy(r)
    c["arranger"]["late_borrow"] = "none"
    return [("1  found, pasted: a measurement plate + a far view of a river", a),
            ("2  covered: a torn strip cuts; a plastic sheet re-inks", b),
            ("3  the gesture as the hand drew it, over everything", c),
            ("4  negotiated: it rides the river, the torn edge, the sheet", r)]


def final():
    out = []
    # 1. the piece
    sh = kit.run(v10())
    im = of.render_colour(sh, px_per_mm=8.0)
    out.append(_save(im, "1-piece", sh.recipe))
    # 2. process strip
    panels, recs = [], []
    for lab, rr in stages():
        s2 = kit.run(rr)
        recs.append(s2.recipe)
        panels.append(_captioned(of.render_colour(s2, px_per_mm=3.0), lab, fs=15))
    out.append(_save(_row(panels), "2-process", {"panels": recs}))
    # 3. close-up: the river borrowed, the torn edge ridden, the sheet's corner
    out.append(_save(_captioned(of.render_colour(sh, px_per_mm=14.0, crop=(4, 112, 160, 222)),
                                "close-up, 156 × 110 mm of the piece: the black rides the river's tight zigzag 0.9 mm "
                                "beside it and leaves; rides the torn edge of the cut strip (the river stops at that "
                                "edge and resumes after the gap);\nthe plastic sheet's lower corner, where blue becomes "
                                "green", fs=20), "3-closeup", sh.recipe))
    # 4. the dud
    sd = kit.run(v2())
    left = of.render_colour(sd, px_per_mm=4.0)
    right = debug_image(sd, px=4.0)
    out.append(_save(_captioned(_row([left, right]),
                                "dud (v2): covers placed by SEARCH (on the late line's path, most lines ending at the edge) + two made "
                                "voices of one character. Right: covers (red), rides (orange).\nThe search puts covers "
                                "where the drawing is already busy, so the gap reads as nothing; the bold line loops "
                                "inside a cover; the plate is wallpaper behind two scribbles.", fs=17),
                      "4-dud", sd.recipe))
    # 5. the reference works beside the piece
    from PIL import Image
    refs = [(REF / "14-p-2013-28-invnr-76298-photo-def-image-srgb.jpg", (300, 300, 3260, 3260),
             "Albert Oehlen, Untitled, 2013\npencil, ink, collage on paper, 29.7 × 20.5 cm\n"
             "© Albert Oehlen / VG Bild-Kunst (Galerie Max Hetzler)"),
            (REF / "28-oehlen2.jpg", None,
             "Albert Oehlen, Untitled, 2022\npaper and plastic sheet on paper, 30.5 × 22.9 cm\n"
             "© Albert Oehlen / VG Bild-Kunst (via drawingsandnotes)")]
    tiles = []
    H = 1100
    for p, box, cap in refs:
        r_im = Image.open(p).convert("RGB")
        if box:
            r_im = r_im.crop(box)
        r_im = r_im.resize((int(r_im.width * H / r_im.height), H))
        tiles.append(_captioned(r_im, cap, fs=19))
    mine = of.render_colour(sh, px_per_mm=H / 297.0)
    tiles.append(_captioned(mine, "oehlen_found, the piece (205 × 297 mm)\nfound: plate + far river; cut: torn strip;"
                                  "\ntint: a plastic sheet; one late gesture", fs=19))
    out.append(_save(_row(tiles), "5-reference", sh.recipe))
    return out


def debug_image(sheet, px=4.0):
    from PIL import ImageDraw
    import numpy as np
    im = of.render_colour(sheet, px_per_mm=px)
    dr = ImageDraw.Draw(im)
    log = sheet.marks[0].meta.get("oehlen_found", {})
    for c in log.get("covers", []):
        q = np.asarray(c["polygon"]) * px
        dr.line([tuple(v) for v in q], fill=(0xD1, 0x4D, 0x41), width=2)
    for m in sheet.marks:
        if "neg" in m.channels:
            g = np.asarray(m["neg"])
            P_ = m.points * px
            for i in range(len(P_) - 1):
                if g[i] > 0 and g[i + 1] > 0:
                    dr.line([tuple(P_[i]), tuple(P_[i + 1])], fill=(0xDA, 0x70, 0x2C), width=4)
    return im


if __name__ == "__main__":
    if sys.argv[1:] == ["final"]:
        for p in final():
            print(p)
        sys.exit(0)
    for nm in sys.argv[1:]:
        sh, p, log = build(nm)
        debug(sh, OUT / f"{nm}.debug.jpg")
        print(nm, p, "marks", len(sh.marks), "rides", [len(x["rides"]) for x in log.get("rides", [])],
              "covers", [{k: v for k, v in c.items() if k != "polygon"} for c in log.get("covers", [])], "secs", sh.meta["seconds"])



def sweep(name, variants, cols=4, px=2.5):
    """Contact sheet of recipe variants: [(label, recipe)]."""
    from PIL import ImageDraw
    ims = []
    for lab, r in variants:
        sh = kit.run(r)
        sh.meta["recipe"] = sh.recipe
        im = of.render_colour(sh, px_per_mm=px)
        ImageDraw.Draw(im).text((6, 6), lab, fill=(0x10, 0x0F, 0x0F), font=kit.core._font(14))
        ims.append(im)
        sh.save_recipe(OUT / "sweep" / f"{name}-{lab}.recipe.json")
    c = kit.contact(ims, cols)
    (OUT / "sweep").mkdir(parents=True, exist_ok=True)
    c.save(OUT / f"{name}.jpg", quality=85)
    return OUT / f"{name}.jpg"

