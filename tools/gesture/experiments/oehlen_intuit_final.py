"""oehlen_intuit: the review images (finished piece + supporting), built from kit recipes.

    .local/gesture/.venv/bin/python tools/gesture/experiments/oehlen_intuit_final.py

Each image has <stem>.recipe.json beside it (kit) or <stem>.params.json (session
working images, rebuilt by experiments/oehlen_intuit_session.py).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, "tools/gesture")
from gesture import kit  # noqa: E402

OUT = Path(".local/gesture/out/oehlen_intuit")
RES = Path("tools/gesture/results")
PAPER = (0xFF, 0xFC, 0xF0)
SEED = 4127

FINAL = {"label": "oehlen_intuit — sheet 1", "frame": [200, 300], "seed": SEED, "margin": 0,
         "notes": "drawn on the AxiDraw in landscape (300 x 200, turn=false), seen turned to portrait. "
                  "Three pens: 0.3 fine liner, 1.6 marker (the pixel stretches), 0.5 red-400.",
         "voice": {"id": "oehlen_intuit_sheet"},
         "renderer": {"id": "oehlen_intuit_pens"}}


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def render(sheet, px_per_mm=8.0, ss=2, crop=None):
    W, H = sheet.frame
    k = px_per_mm * ss
    im = Image.new("RGB", (int(W * k), int(H * k)), PAPER)
    d = ImageDraw.Draw(im)
    for ink in sheet.inks:
        q = ink.points * k
        w = max(1, int(round(ink.pen * k)))
        col = hexrgb(ink.meta.get("colour", "#100F0F"))
        d.line([tuple(v) for v in q], fill=col, width=w, joint="curve")
        r = w / 2
        for v in q[[0, -1]]:
            d.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=col)
    im = im.resize((im.width // ss, im.height // ss), Image.LANCZOS)
    if crop:
        x0, y0, x1, y1 = (int(c * px_per_mm) for c in crop)
        im = im.crop((x0, y0, x1, y1))
    return im


def save(im, sheet, stem, cap=2400):
    if max(im.size) > cap:
        k = cap / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    p = RES / f"{stem}.jpg"
    im.save(p, quality=90)
    sheet.save_recipe(RES / f"{stem}.recipe.json")
    return p


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    final = kit.run(FINAL)
    roles = {}
    for ink in final.inks:
        roles[ink.meta["role"]] = roles.get(ink.meta["role"], 0) + 1
    print("final inks", len(final.inks), roles)
    print("final", save(render(final), final, "oehlen_intuit-1-sheet1"))

    # close-up: the burst against the wall and the foot of the pixel stretch (mm crop in the viewed frame)
    print("close", save(render(final, px_per_mm=14, crop=(4, 95, 104, 205)), final, "oehlen_intuit-3-closeup"))

    # the plotter's view: the same recipe untouched by the turn (what the machine draws, landscape)
    machine = kit.run({**FINAL, "label": "oehlen_intuit — sheet 1, machine orientation", "frame": [300, 200],
                       "voice": {"id": "oehlen_intuit_sheet", "turn": False}})
    machine.to_svg(OUT / "oehlen_intuit_sheet1_machine.svg")
    final.to_svg(OUT / "oehlen_intuit_sheet1_viewed.svg")

    # process strip: session working images, in order
    steps = ["s01_typed_blind", "s05_typed_charcoal", "s07_knot_on_horizon", "s09_turned",
             "s12_without_swoosh", "s15b_no_arrow", "s19_ragged_bare"]
    ims = [Image.open(OUT / f"{s}.jpg").convert("RGB") for s in steps]
    h = 700
    ims = [i.resize((int(i.width * h / i.height), h), Image.LANCZOS) for i in ims]
    fin = render(final, px_per_mm=4)
    fin = fin.resize((int(fin.width * h / fin.height), h), Image.LANCZOS)
    ims.append(fin)
    labels = ["1 typed blind", "5 smoothed = a logo", "7 the stork's nest", "9 turned", "12 without the swoosh",
              "15 pixel stretch", "19 the accident", "final"]
    gap, lab = 16, 40
    rows = [list(zip(ims[:4], labels[:4])), list(zip(ims[4:], labels[4:]))]
    Wt = max(sum(i.width for i, _ in r) + gap * (len(r) + 1) for r in rows)
    strip = Image.new("RGB", (Wt, 2 * (h + lab + gap) + gap), (0xF2, 0xF0, 0xE5))
    d = ImageDraw.Draw(strip)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
    except OSError:
        font = ImageFont.load_default()
    for ri, r in enumerate(rows):
        x, y = gap, gap + ri * (h + lab + gap)
        for im, t in r:
            strip.paste(im, (x, y))
            d.text((x, y + h + 8), t, fill=(0x10, 0x0F, 0x0F), font=font)
            x += im.width + gap
    if max(strip.size) > 2400:
        k = 2400 / max(strip.size)
        strip = strip.resize((int(strip.width * k), int(strip.height * k)), Image.LANCZOS)
    p = RES / "oehlen_intuit-2-process.jpg"
    strip.save(p, quality=90)
    (RES / "oehlen_intuit-2-process.params.json").write_text(json.dumps(
        {"made_by": "tools/gesture/experiments/oehlen_intuit_final.py",
         "frames": [f".local/gesture/out/oehlen_intuit/{s}.jpg (+ .params.json; rebuild: "
                    f"experiments/oehlen_intuit_session.py)" for s in steps] + ["final: oehlen_intuit-1-sheet1.recipe.json"]},
        indent=1))
    print("strip", p)

    # dud: sheet 2, typed only (no indifferent other) — a stick figure
    src = OUT / "s25_sheet2_round3.jpg"
    if src.exists():
        shutil.copy(src, RES / "oehlen_intuit-4-dud-typed-only.jpg")
        shutil.copy(OUT / "s25_sheet2_round3.params.json", RES / "oehlen_intuit-4-dud-typed-only.params.json")
        print("dud", RES / "oehlen_intuit-4-dud-typed-only.jpg")


if __name__ == "__main__":
    main()
