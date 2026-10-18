"""Round 13 phase 2, Study A: the rules over found ground, with catches and answers (`found_play`).

    .local/gesture/.venv/bin/python tools/gesture/experiments/study_a.py sweep [seed0 n] [lines]
    .local/gesture/.venv/bin/python tools/gesture/experiments/study_a.py one <seed> [lines]
    .local/gesture/.venv/bin/python tools/gesture/experiments/study_a.py map <seed> [lines]

Working images go to .local/gesture/out/study_a/ with the recipe beside each.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_oehlen_found as of  # noqa: E402
from gesture.kit.core import PAPER, Sheet, _font  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/study_a"
FRAME = [300.0, 200.0]
# the rules piece's two hands first, then the four-hands sheet's (Ian: "amazing"), in turns
HANDS = ["dance_thrusting", "river_bend", "trail_miner", "dancer_madeline", "mime_mantis", "fly_fru"]
MADE_BOXES = [0.4, 0.5, 0.55, 0.75, 0.55, 0.5, 0.5, 0.7, 0.35, 0.55, 0.5, 0.7, 0.62, 0.45, 0.55, 0.7]
MAP_CODES = [(0, "own / entry", "black"), (1, "ride", "orange"), (6, "carried river", "cyan"),
             (7, "chart rule", "blue"), (8, "chart needle", "red"), (9, "carried hand", "purple"),
             (10, "answer trace", "magenta"), (5, "R2 motif", "green")]


def recipe(seed, lines=4, hands=HANDS, **arr):
    a = {"id": "found_play", "found": 2,
         "found_boxes": [0.33, 0.33, 0.48, 0.42, -3.0, 0.42, 0.7, 0.6, 0.11, -7.0],
         "made_boxes": MADE_BOXES, "lines": lines, "cover_wh": [24.0, 72.0], "cover_edge": "drawn"}
    a.update(arr)
    parts = [{"voice": {"id": "diagram", "chart": "kappa", "rows": 4, "label_h": 2.2, "hands": ["trail_miner"],
                        "length": 6.0}},
             {"voice": {"id": "oehlen_found_river", "tile": "SB19", "rank": 0, "start": 0.0, "span_w": 2400,
                        "angle": 0.0, "stems": "grwl_far_sb19"}}]
    if not hands:
        raise ValueError("Study A needs at least one made hand")
    count = max(len(hands), int(lines))
    parts += [{"voice": {"id": "hand", "hand": hands[i % len(hands)], "length": 3.0, "joins": "smooth"}}
              for i in range(count)]
    return {"label": "found play", "frame": FRAME, "seed": seed, "margin": 4.0, "arranger": a, "parts": parts,
            "renderer": {"id": "oehlen_found_ink", "pen": 0.4}}


def render(r, name, px=5.0):
    sheet = kit.run(r)
    p = of.save(sheet, OUT / f"{name}.jpg", px_per_mm=px)
    fp = sheet.marks[0].meta.get("found_play", {})
    print(f"{name}: {len(fp.get('infections', []))} catches, {len(fp.get('answers', []))} answers, "
          f"{len(fp.get('refusals', []))} refusals, {sheet.meta['seconds']}", flush=True)
    return p, sheet


def save_map(sheet, path, px=6.0):
    """Diagnostic colour by destination-point neg code; the piece's geometry is unchanged."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ss = 2
    k = px * ss
    ground = Sheet(sheet.frame, [], [i for i in sheet.inks if i.meta.get("role") != "made"], sheet.meta)
    im = of.render_colour(ground, px_per_mm=k, ss=1)
    im = Image.blend(Image.new("RGB", im.size, PAPER), im, 0.28)
    dr = ImageDraw.Draw(im)
    colours = {code: of.FLEXOKI[name] for code, _, name in MAP_CODES}
    colours.update({3: colours[0], 4: colours[1]})
    for m in sheet.marks:
        if m.meta.get("of_role") != "made" or len(m.points) < 2:
            continue
        codes = np.asarray(m["neg"], int)[1:]
        cuts = np.r_[0, np.flatnonzero(np.diff(codes)) + 1, len(codes)]
        for a, b in zip(cuts[:-1], cuts[1:]):
            pts = [tuple(v) for v in m.points[a:b + 1] * k]
            dr.line(pts, fill=colours[int(codes[a])], width=max(1, round(m.meta["pen"] * k)), joint="curve")
    im = im.resize((round(sheet.frame[0] * px), round(sheet.frame[1] * px)), Image.Resampling.LANCZOS)
    fs = max(12, round(2.5 * px))
    strip = Image.new("RGB", (im.width, fs * 5), PAPER)
    dr = ImageDraw.Draw(strip)
    title = f"Study A · seed {sheet.recipe['seed']} · {sheet.recipe['arranger']['lines']} lines · colour key"
    dr.text((fs, fs // 2), title, fill=of.FLEXOKI["black"], font=_font(fs))
    for i, (_, label, name) in enumerate(MAP_CODES):
        x, y = fs + (i % 4) * (im.width // 4), fs * (2 + i // 4)
        dr.line((x, y + fs // 2, x + fs * 2, y + fs // 2), fill=of.FLEXOKI[name], width=max(2, round(px / 2)))
        dr.text((x + fs * 3, y), label, fill=of.FLEXOKI["black"], font=_font(fs))
    dr.text((fs, fs * 4), "Found chart, river and cover edge are pale blue.",
            fill=of.FLEXOKI["blue"], font=_font(fs))
    full = Image.new("RGB", (im.width, im.height + strip.height), PAPER)
    full.paste(im, (0, 0))
    full.paste(strip, (0, im.height))
    full.save(path, quality=92)
    sheet.save_recipe(path.with_suffix(".recipe.json"))
    return path


def main(argv):
    cmd = argv[0] if argv else "one"
    if cmd == "one":
        seed = int(argv[1]) if len(argv) > 1 else 1317
        lines = int(argv[2]) if len(argv) > 2 else 4
        render(recipe(seed, lines), f"one-{seed}-L{lines}")
    elif cmd == "sweep":
        s0 = int(argv[1]) if len(argv) > 1 else 1317
        n = int(argv[2]) if len(argv) > 2 else 8
        lines = int(argv[3]) if len(argv) > 3 else 4
        from PIL import Image  # noqa: PLC0415
        ims = []
        for s in range(s0, s0 + n):
            p, _ = render(recipe(s, lines), f"sweep-{s}-L{lines}", px=3.0)
            ims.append(Image.open(p))
        sheet = kit.contact(ims, cols=4, title=f"found_play sweep {s0}… lines={lines}")
        sheet.save(OUT / f"contact-{s0}-L{lines}.jpg", quality=88)
    elif cmd == "map":
        seed = int(argv[1]) if len(argv) > 1 else 1322
        lines = int(argv[2]) if len(argv) > 2 else 4
        p = save_map(kit.run(recipe(seed, lines)), OUT / f"map-{seed}-L{lines}.jpg")
        print(p)
    else:
        raise SystemExit("usage: study_a.py one [seed lines] | sweep [seed0 n lines] | map [seed lines]")


if __name__ == "__main__":
    main(sys.argv[1:])
