"""Round 12, thread `revisit`: re-running round 7's "signs as line events"
with today's kit. Stages (run from the repo root):

    .local/gesture/.venv/bin/python tools/gesture/experiments/revisit_glyphs.py sweep
    .local/gesture/.venv/bin/python tools/gesture/experiments/revisit_glyphs.py <stage>

Scratch output: .local/gesture/out/revisit/. Review images are copied to
tools/gesture/results/revisit-*.jpg by the `review` stage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))

from PIL import Image  # noqa: E402

from gesture import kit  # noqa: E402

OUT = ROOT / ".local/gesture/out/revisit"
OUT.mkdir(parents=True, exist_ok=True)


def glyph_recipe(trail, host, *, seed=1201, frame=(200, 150), renderer=None, **kw):
    v = {"id": "revisit_glyph", "trail": trail, "host": host, **kw}
    return {"seed": seed, "frame": list(frame), "voice": v,
            "renderer": renderer or {"id": "nib", "style": "c+e", "pen": 0.35}}


def shot(recipe, name, px=5, label="auto"):
    sh = kit.run(recipe)
    p = OUT / f"{name}.jpg"
    kit.preview(sh, str(p), px_per_mm=px, label=label)
    return sh, Image.open(p)


def sweep():
    ims = []
    for tr, host in [("levitation", "head"), ("levitation", "rhand"), ("mantis", "head"), ("mantis", "lhand"),
                     ("outofbalance", "head"), ("particles", "lhand"), ("penguin", "head"), ("thrusting", "head")]:
        for limbs in ("loudest", "all"):
            r = glyph_recipe(tr, host, limbs=limbs, seconds=40, still=0.2, min_hold_s=0.25)
            sh, im = shot(r, f"g2_{tr}_{host}_{limbs}")
            m = sh.marks[0]
            print(tr, host, limbs, m.meta["glyphs"], m.meta["holds_s"][:8])
            ims.append(im)
    kit.contact(ims, 4, title="glyph v2 (fit sizes, figures ≤ 1.6 s)").save(OUT / "g2_contact.jpg")




def sweep2():
    ims = []
    for tr, host in [("levitation", "head"), ("levitation", "rhand"), ("levitation", "lhand"), ("mantis", "lhand"),
                     ("outofbalance", "rhand"), ("staccato", "rhand")]:
        for close in ("excursion", "carry"):
            r = glyph_recipe(tr, host, close=close, seconds=60, still=0.2, min_hold_s=0.25, max_glyphs=14)
            sh, im = shot(r, f"g3_{tr}_{host}_{close}")
            print(tr, host, close, sh.marks[0].meta["glyphs"])
            ims.append(im)
    kit.contact(ims, 4, title="glyph v3: excursion | carry, whole window").save(OUT / "g3_contact.jpg")


def colour_image(sheet, px=6.0, label="auto", ss=2):
    """kit.render_image, but each ink in its meta['colour'] (black if none);
    colours laid in order of first appearance."""
    import numpy as np
    from PIL import ImageDraw
    from gesture.kit.core import INK, PAPER, _font
    W, H = sheet.frame
    k = px * ss
    rgb = np.ones((int(round(H * px)), int(round(W * px)), 3)) * np.array(PAPER, float)
    order = []
    for ink in sheet.inks:
        c = ink.meta.get("colour", "#100F0F")
        if c not in order:
            order.append(c)
    for c in order:
        im = Image.new("L", (int(round(W * k)), int(round(H * k))), 0)
        dr = ImageDraw.Draw(im)
        for ink in sheet.inks:
            if ink.meta.get("colour", "#100F0F") != c:
                continue
            q = ink.points * k
            d = max(ink.pen * k, 1.0)
            if len(q) >= 2:
                dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
            r = d / 2
            for v in (q if d > 4 else q[[0, -1]]):
                dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
        im = im.resize((rgb.shape[1], rgb.shape[0]), Image.Resampling.BOX)
        a = np.asarray(im, float)[..., None] / 255.0
        col = np.array([int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], float)
        rgb = rgb * (1 - a) + col * a
    out = Image.fromarray(rgb.astype(np.uint8), "RGB")
    if label is None:
        return out
    if label == "auto":
        label = kit.render_image(sheet, px_per_mm=1, label="auto").info.get("label", "") or ""
    fs = max(12, int(out.width / 90))
    strip = Image.new("RGB", (out.width, int(fs * 2.0)), PAPER)
    ImageDraw.Draw(strip).text((int(fs * 0.6), int(fs * 0.45)), label, fill=INK, font=_font(fs))
    full = Image.new("RGB", (out.width, out.height + strip.height), PAPER)
    full.paste(out, (0, 0))
    full.paste(strip, (0, out.height))
    return full


def cshot(recipe, name, px=5, label=None):
    sh = kit.run(recipe)
    p = OUT / f"{name}.jpg"
    im = colour_image(sh, px=px, label=label or name)
    im.save(p, quality=90)
    sh.save_recipe(p.with_suffix(".recipe.json"))
    return sh, im


def sweep3():
    ims = []
    for tr, a, b in [("mantis", "lhand", "rhand"), ("levitation", "lhand", "rhand"), ("levitation", "head", "rhand"),
                     ("mantis", "head", "rfoot"), ("penguin", "lhand", "rhand"), ("dragon", "lhand", "head")]:
        r = glyph_recipe(tr, a, with_=b, seconds=60, still=0.2, min_hold_s=0.25, max_glyphs=10,
                         renderer={"id": "revisit_nib", "inks": "black,red"})
        sh, im = cshot(r, f"g4_{tr}_{a}_{b}")
        print(tr, a, b, [len(m.meta["figures"]) for m in sh.marks])
        ims.append(im)
    kit.contact(ims, 3, title="glyph v4: two hosts, two pens").save(OUT / "g4_contact.jpg")


RESULTS = ROOT / "tools/gesture/results"
SEED = 1201
PIECE = dict(frame=(150, 210), seconds=60, still=0.2, min_hold_s=0.25, max_glyphs=5, fig=0.07, spread=1.0)


def piece_recipe(trail="particles", host="rfoot", with_="head", **kw):
    r = glyph_recipe(trail, host, with_=with_, seed=SEED, **{**PIECE, **kw},
                     renderer={"id": "revisit_nib", "style": "c+e", "pen": 0.35, "inks": "black,red"})
    r["margin"] = 10
    r["label"] = "revisit: where one limb stops, its line writes what the others did"
    return r


def _fit(im, long_side=2400):
    k = long_side / max(im.size)
    return im.resize((int(im.width * k), int(im.height * k)), Image.Resampling.LANCZOS) if k < 1 else im


def _side_by_side(ims, gap=40, title=None, h=None):
    from PIL import ImageDraw
    from gesture.kit.core import INK, PAPER, _font
    h = h or max(i.height for i in ims)
    ims = [i.resize((int(i.width * h / i.height), h), Image.Resampling.LANCZOS) for i in ims]
    W = sum(i.width for i in ims) + gap * (len(ims) + 1)
    top = 60 if title else gap
    out = Image.new("RGB", (W, h + top + gap), PAPER)
    if title:
        ImageDraw.Draw(out).text((gap, 18), title, fill=INK, font=_font(26))
    x = gap
    for i in ims:
        out.paste(i, (x, top))
        x += i.width + gap
    return out


def _save(im, name, recipes):
    p = RESULTS / f"revisit-{name}.jpg"
    _fit(im).save(p, quality=88, optimize=True)
    side = p.with_suffix(".recipe.json")
    side.write_text(json.dumps(recipes, indent=1, default=str))
    print("wrote", p.relative_to(ROOT), _fit(im).size)


def review():
    lab = "Stocos Particles (45 s): right foot black, head red; 5 stops each; 150 x 210 mm; seed 1201"
    # 1. the finished piece
    r1 = piece_recipe()
    sh1 = kit.run(r1)
    im1 = colour_image(sh1, px=11, label="where one limb stops, its line writes what the others did — " + lab)
    _save(im1, "piece", sh1.recipe)
    # 2. old beside new: round-7 line events (tree seed 4) | the piece
    old = Image.open(RESULTS / "signs-events-tree.jpg")
    W, H = old.size
    old = old.crop((0, H // 2 + 20, W // 2 - 4, H))            # 'tree seed 4 - line events'
    _save(_side_by_side([old, colour_image(sh1, px=8, label=None)], title=(
        "round 7 (2026-10-16): signs as line events, 17 operators sampled from a fitted grammar  |  "
        "round 12: one sign per stop, its form the body's own motion")), "old-new",
        {"old": "tools/gesture/results/signs-events-tree.jpg (bottom-left panel; experiments/signs_study.py "
                "events_sheets)", "new": sh1.recipe})
    # 3. same stops, two answers: the round-7 operator 'body' vs the body's figure
    r3 = piece_recipe(draw="stops")
    r3["renderer"] = {"id": "revisit_signs", "pen": 0.35, "inks": "black,red"}
    r3["modulators"] = [{"id": "revisit_notate", "source": "stops", "code": "hold=body,end=none", "gap_mm": 0.0,
                         "size_mm": 1.4}]
    sh3 = kit.run(r3)
    _save(_side_by_side([colour_image(sh3, px=8, label="the stops answered by round 7's best operator ('body')"),
                         colour_image(sh1, px=8, label="the same stops answered by the other limbs' motion")],
                        title="same line, same five stops per limb: a fixed sign vs the body's own figure"),
          "same-stops", [sh3.recipe, sh1.recipe])
    # 4. variant: levitation, left hand (black) + left foot (red), landscape
    r4 = piece_recipe("levitation", "lhand", "lfoot", frame=(240, 180))
    sh4 = kit.run(r4)
    _save(colour_image(sh4, px=9, label="variant — levitation: left hand black, left foot red; 240 x 180 mm; seed 1201"),
          "variant-levitation", sh4.recipe)
    # 5. dud: every limb as a ruled row (a score) reads as writing
    r5 = glyph_recipe("mantis", "head", with_="others", layout="rows", row_gap=0.1, frame=(290, 200), seconds=60,
                      still=0.2, min_hold_s=0.25, max_glyphs=10, fig=0.05, seed=SEED,
                      renderer={"id": "revisit_nib", "inks": "black,red,blue,cyan,orange"})
    sh5 = kit.run(r5)
    _save(colour_image(sh5, px=7, label="dud — mantis, all five limbs as rows of a score (head, hands, feet): "
                       "ruled rows turn the figures into handwriting"), "dud-rows", sh5.recipe)


if __name__ == "__main__":
    for stage in sys.argv[1:] or ["sweep"]:
        globals()[stage]()
