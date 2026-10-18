"""handover (round 13, II-b): the review images.

  1 piece      Cohen's 1969 meander becomes the fly, one feature at a time (A4, four rows, one line)
  2 stages     the same line coloured by stage, with each handover's first event and completion marked
  3 specimens  six of the 2^3 grammars between the two hands (each feature from A or B), the piece's route
               marked (the two with A's straight runs and B's absent corners are dropped: a nearly straight
               line that cannot follow any path, it runs off the strip)
  4 dud        the same hands, path and seed: blend (every number averaged), cut-and-paste (whole
               segments), and the handover

Run from the repo root: .local/gesture/.venv/bin/python tools/gesture/experiments/handover_review.py [out_dir]
"""
from __future__ import annotations

import copy
import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, "tools/gesture")
import numpy as np
from PIL import Image, ImageDraw

from gesture import kit
from gesture.kit.core import PAPER, _font

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ".local/gesture/out/handover/review")
INK = (0x10, 0x0F, 0x0F)
# Flexoki 600 accents, axibridge/static/css/flexoki.css
STAGE = [INK, (0xAF, 0x30, 0x29), (0xBC, 0x52, 0x15), (0x20, 0x5E, 0xA6)]
GREY = (0xB7, 0xB5, 0xAC)                                                   # flexoki-300

PIECE = {"label": "handover: Cohen's meander becomes the fly", "frame": [297, 210], "seed": 1442, "margin": 12,
         "voice": {"id": "morph_handover", "hands": ["meander69", "fly_open"], "order": "bend,turn,corner",
                   "rows": 4, "R_mm": 85, "band": 18, "ease": 1.3, "run": 4,
                   "windows": [0.27, 0.37, 0.52, 0.62, 0.75, 0.85]},
         "renderer": {"id": "wire", "pen": 0.35}}
ORDER = ["bend", "turn", "corner"]
NAMES = ["Cohen's key: straight runs, square corners either way (A, meander69)",
         "bowed key: B's bends between A's square corners",
         "coiled: + B's handedness, every bend and corner turns the same way",
         "the fly: + B's corners (none): loops (B, fly_open)"]


def save(im: Image.Image, path: Path, recipe) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    q = 88
    while True:
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < 390_000 or q <= 50:
            break
        q -= 6
    path.with_suffix(".recipe.json").write_text(json.dumps(recipe, indent=1))
    print(path, im.size, path.stat().st_size // 1000, "KB", flush=True)


def caption(im: Image.Image, text: str, fs: int = 18) -> Image.Image:
    out = Image.new("RGB", (im.width, im.height + int(fs * 2.2)), PAPER)
    out.paste(im, (0, 0))
    ImageDraw.Draw(out).text((int(fs * 0.7), im.height + int(fs * 0.5)), text, fill=INK, font=_font(fs))
    return out


def draw_line(dr, pts, cols, k, width):
    cut = np.r_[0, np.nonzero(np.any(np.diff(cols, axis=0) != 0, axis=1))[0] + 1, len(cols)]
    for a, b in zip(cut[:-1], cut[1:]):
        seg = pts[max(a - 1, 0):b] * k
        if len(seg) >= 2:
            dr.line([tuple(v) for v in seg], fill=tuple(int(c) for c in cols[a]), width=width, joint="curve")


# ---------------------------------------------------------------------------

def piece():
    sh = kit.run(PIECE)
    im = kit.render_image(sh, px_per_mm=8, label=None)
    save(caption(im, "handover — one line, Cohen's 1969 plotter meander becomes the fly, one feature at a time "
                     "(bends, then handedness, then corners).  A4, seed 1442", 20),
         OUT / "handover-1-piece.jpg", sh.recipe)
    return sh


def stages(sh):
    m = sh.marks[0]
    k, ss = 8.0, 2
    W, H = sh.frame
    im = Image.new("RGB", (int(W * k * ss), int(H * k * ss)), PAPER)
    dr = ImageDraw.Draw(im)
    st = m["stage"].astype(int)
    cols = np.array([STAGE[min(s, 3)] for s in st])
    draw_line(dr, m.points, cols, k * ss, int(0.45 * k * ss))
    # each handover: open ring = B's first event of that feature; dot = the feature is B's for good
    fs = _font(int(3.2 * k * ss))
    for i, f in enumerate(ORDER):
        src = m[f"src_{f}"]
        first = int(np.argmax(src > 0))
        last_a = len(src) - 1 - int(np.argmax(src[::-1] < 1))
        done = min(last_a + 1, len(src) - 1)
        for j, filled in ((first, False), (done, True)):
            x, y = m.points[j] * k * ss
            r = 1.6 * k * ss
            c = STAGE[i + 1]
            dr.ellipse([x - r, y - r, x + r, y + r], outline=c, width=int(0.5 * k * ss), fill=c if filled else None)
            dr.text((x + 2.2 * k * ss, y - 5.5 * k * ss), f"{i + 1}{'' if filled else '?'}", fill=c, font=fs)
    im = im.resize((im.width // ss, im.height // ss), Image.Resampling.LANCZOS)
    # legend
    fl = _font(19)
    rows = [(STAGE[i], f"{i}  {NAMES[i]}") for i in range(4)]
    leg = Image.new("RGB", (im.width, 30 * len(rows) + 50), PAPER)
    d2 = ImageDraw.Draw(leg)
    for r, (c, t) in enumerate(rows):
        d2.line([(24, 22 + 30 * r), (70, 22 + 30 * r)], fill=c, width=4)
        d2.text((84, 10 + 30 * r), t, fill=INK, font=fl)
    d2.text((24, 10 + 30 * len(rows) + 6), "ring n? = B's feature first appears as an event inside the line;  "
            "dot n = the last relapse to A: from here the feature is B's", fill=INK, font=_font(16))
    out = Image.new("RGB", (im.width, im.height + leg.height), PAPER)
    out.paste(im, (0, 0))
    out.paste(leg, (0, im.height))
    save(out, OUT / "handover-2-stages.jpg", sh.recipe)


def _specimen(bits):
    rec = copy.deepcopy(PIECE)
    rec.update({"frame": [297, 46], "margin": 3, "seed": 1442 + 7 * (bits[0] + 2 * bits[1] + 4 * bits[2])})
    v = rec["voice"]
    v.update({"rows": 1, "order": ",".join(ORDER), "band": 14,
              "windows": [w for b in bits for w in ((-1.0, -1.0) if b else (2.0, 2.0))]})
    rec["label"] = "specimen " + "".join("AB"[b] for b in bits)
    sh = kit.run(rec)
    return kit.render_image(sh, px_per_mm=3.9, label=None), rec


def specimens():
    combos = [c for c in itertools.product((0, 1), repeat=3)      # (bend, turn, corner) from A=0 / B=1
              if not (c[0] == 0 and c[2] == 1)]
    route = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1, 1)]
    combos.sort(key=lambda c: (sum(c), c not in route, c))
    with ProcessPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(_specimen, combos))
    fs = 17
    tiles = []
    for c, (im, _rec) in zip(combos, res):
        on = c in route
        txt = "  ".join(f"{f} {'AB'[b]}" for f, b in zip(ORDER, c))
        name = {(0, 0, 0): "Cohen's key (A)", (1, 0, 0): "bowed key", (1, 1, 0): "coiled",
                (1, 1, 1): "the fly (B)", (0, 1, 0): "boxes: the key turns one way", (0, 0, 1): "no corners: "
                "a straight line, nearly", (1, 0, 1): "waves: B's bends, A's handedness",
                (0, 1, 1): "straight, one way, no corners"}[c]
        lab = f"{'>' if on else ' '} {name}    [{txt}]" + ("   on the piece's route" if on else "")
        t = Image.new("RGB", (im.width, im.height + int(fs * 1.8)), PAPER)
        t.paste(im, (0, int(fs * 1.8)))
        ImageDraw.Draw(t).text((8, 4), lab, fill=STAGE[route.index(c)] if on else (0x6F, 0x6E, 0x69),
                               font=_font(fs))
        tiles.append(t)
    sheet = kit.contact(tiles, 2, title="the grammars between the two hands: each of bend / handedness / corners "
                                        "from A (Cohen's meander) or B (the fly); the piece walks the four marked >")
    save(sheet, OUT / "handover-3-specimens.jpg", [r[1] for r in res])


def _mode(mode):
    rec = copy.deepcopy(PIECE)
    rec["voice"]["mode"] = mode
    rec["label"] = f"handover control: {mode}"
    sh = kit.run(rec)
    return kit.render_image(sh, px_per_mm=3.2, label=None), rec


def dud():
    modes = ["average", "tokens", "features"]
    with ProcessPoolExecutor(max_workers=3) as ex:
        res = list(ex.map(_mode, modes))
    names = {"average": "blend: every number moved from A toward B (Hand Drift's interp) — the middle is a softened key",
             "tokens": "cut and paste: whole segments of A or B (Hand Drift's mixture) — loops pasted into the key",
             "features": "handover: one feature at a time — the middle is its own grammar (the piece)"}
    tiles = [caption(im, names[m], 15) for m, (im, _r) in zip(modes, res)]
    sheet = kit.contact(tiles, 1, title="same hands, path, seed and span: three ways for A to become B")
    save(sheet, OUT / "handover-4-dud.jpg", [r[1] for r in res])


if __name__ == "__main__":
    which = sys.argv[2].split(",") if len(sys.argv) > 2 else ["piece", "stages", "specimens", "dud"]
    sh = piece() if ("piece" in which or "stages" in which) else None
    if "stages" in which:
        stages(sh)
    if "specimens" in which:
        specimens()
    if "dud" in which:
        dud()
