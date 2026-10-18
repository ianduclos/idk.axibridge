"""Round-12 keeps, second set (2026-10-18): one image per new built-in study.

Renders the study recipes (`axibridge/sources/_gesture_studies/studies/<id>/study.json`)
with the research kit, which matches the app's frozen copy by parity, in the
pens' colours, into tools/gesture/results/keeps13-<id>.jpg (≤ 2400 px).

    .local/gesture/.venv/bin/python tools/gesture/experiments/keeps13_images.py
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))
from PIL import Image, ImageDraw  # noqa: E402

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_oehlen_found as A  # noqa: E402

STUDIES = ROOT / "axibridge/sources/_gesture_studies/studies"
OUT = ROOT / "tools/gesture/results"
PAPER = (255, 252, 240)


def study(sid: str) -> dict:
    return json.loads((STUDIES / sid / "study.json").read_text())


def _revisit():
    spec = importlib.util.spec_from_file_location("revisit_glyphs", ROOT / "tools/gesture/experiments/revisit_glyphs.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def labelled(im: Image.Image, text: str) -> Image.Image:
    out = Image.new("RGB", (im.width, im.height + 44), PAPER)
    out.paste(im, (0, 0))
    ImageDraw.Draw(out).text((16, im.height + 14), text, fill=(16, 15, 15))
    return out


def row(ims, gap=30):
    h = max(i.height for i in ims)
    out = Image.new("RGB", (sum(i.width for i in ims) + gap * (len(ims) - 1), h), (242, 240, 229))
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + gap
    return out


def col(ims, gap=20):
    w = max(i.width for i in ims)
    out = Image.new("RGB", (w, sum(i.height for i in ims) + gap * (len(ims) - 1)), (242, 240, 229))
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + gap
    return out


def save(im: Image.Image, sid: str, recipes: dict) -> None:
    im = im.convert("RGB")
    im.thumbnail((2400, 2400))
    p = OUT / f"keeps13-{sid}.jpg"
    im.save(p, quality=88, optimize=True)
    p.with_suffix(".recipe.json").write_text(json.dumps(recipes, indent=1) + "\n")
    print(p, im.size)


def main() -> None:
    # 1. found ground: the default (= the round-12 piece) and the river alone
    r = study("found_ground")["recipe"]
    river = copy.deepcopy(r)
    river["arranger"]["found_on"] = "second"
    save(row([labelled(A.render_colour(kit.run(r), px_per_mm=5.0), "found_ground: default (the round-12 piece)"),
              labelled(A.render_colour(kit.run(river), px_per_mm=5.0), "Found ground: second (the river alone)")]),
         "found_ground", {"default": r, "river_only": river})
    # 2. limb signs + levitation variant
    rv = _revisit()
    a, b = study("limb_signs")["recipe"], study("limb_signs_levitation")["recipe"]
    save(rv.colour_image(kit.run(a), px=11, label="limb_signs: particles, right foot black, head red"),
         "limb_signs", a)
    save(rv.colour_image(kit.run(b), px=9, label="limb_signs_levitation: left hand black, left foot red"),
         "limb_signs_levitation", b)
    # 3. morphing belt: the default (gain 1.8) and a morph (1.0 -> 2.6)
    m = study("morphing_belt")["recipe"]
    morph = copy.deepcopy(m)
    morph["parts"][0]["voice"].update(gain=1.0, gain_end=2.6)
    save(col([kit.render_image(kit.run(m), px_per_mm=8.0, label="morphing_belt: default, tightness 1.8 (keeps12 row 3)"),
              kit.render_image(kit.run(morph), px_per_mm=8.0, label="tightness 1.0 at the start -> 2.6 at the end")]),
         "morphing_belt", {"default": m, "morph": morph})


if __name__ == "__main__":
    main()
