"""Round 14 thread c2 `rnear`: the Amazon river approached (kit voice `river_approach`).

    .local/gesture/.venv/bin/python tools/gesture/experiments/rnear.py probe [seed ...]
    .local/gesture/.venv/bin/python tools/gesture/experiments/rnear.py review

Scratch goes to .local/gesture/out/rnear/; `review` writes the ≤ 5 review
images to tools/gesture/results/rnear-*.jpg with a recipe beside each.
Colour previews: the stem in black, each closer hand in its own Flexoki
400 accent, the cut-off event in red — a diagnostic, the piece is one pen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from gesture import kit  # noqa: E402
from gesture.kit.arrangers_oehlen_found import FLEXOKI  # noqa: E402
from gesture.kit.core import INK, PAPER  # noqa: E402

OUT = ROOT / ".local/gesture/out/rnear"
RES = ROOT / "tools/gesture/results"
HAND_COL = ["blue-400", "green-400", "purple-400", "orange-400", "magenta-400"]


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def recipe(seed, frame=(290, 200), pen=0.35, margin=10.0, **voice):
    return {"label": "rnear", "seed": seed, "frame": list(frame), "margin": margin,
            "voice": {"id": "river_approach", **voice}, "renderer": {"id": "wire", "pen": pen}}


def draw(sheet, *, px_per_mm=6.0, colour=False, crop=None, ss=2, pen=None):
    """Image of the sheet's marks; colour=True colours by `src`."""
    W, H = sheet.frame
    x0, y0, x1, y1 = crop if crop is not None else (0.0, 0.0, W, H)
    k = px_per_mm * ss
    size = (int(round((x1 - x0) * k)), int(round((y1 - y0) * k)))
    im = Image.new("RGB", size, tuple(PAPER))
    dr = ImageDraw.Draw(im)
    pw = pen if pen is not None else (sheet.inks[0].pen if sheet.inks else 0.35)
    wd = max(int(round(pw * k)), 1)
    for m in sheet.marks:
        q = (m.points - [x0, y0]) * k
        src = m.channels.get("src", np.zeros(len(q)))
        nv = len(m.meta.get("voices", [])) - 1
        if not colour:
            dr.line([tuple(v) for v in q], fill=tuple(INK), width=wd, joint="curve")
            continue
        cuts = np.flatnonzero(np.diff(src) != 0) + 1
        for a, b in zip(np.r_[0, cuts], np.r_[cuts, len(q)]):
            sv = int(src[a])
            if sv == 0:
                col = tuple(INK)
            elif sv >= nv:
                col = _hex(FLEXOKI["red-400"])
            else:
                col = _hex(FLEXOKI[HAND_COL[(sv - 1) % len(HAND_COL)]])
            seg = q[max(a - 1, 0):b]
            if len(seg) >= 2:
                dr.line([tuple(v) for v in seg], fill=col, width=wd, joint="curve")
    return im.resize((size[0] // ss, size[1] // ss), Image.Resampling.LANCZOS)


def label(im, text, h=28):
    out = Image.new("RGB", (im.width, im.height + h), tuple(PAPER))
    out.paste(im, (0, 0))
    dr = ImageDraw.Draw(out)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    except OSError:
        f = ImageFont.load_default()
    dr.text((10, im.height + 6), text, fill=(90, 88, 80), font=f)
    return out


def save_jpg(im, path, max_kb=395, max_side=2400):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if max(im.size) > max_side:
        s = max_side / max(im.size)
        im = im.resize((int(im.width * s), int(im.height * s)), Image.Resampling.LANCZOS)
    for q in (90, 85, 80, 74, 68, 60, 52):
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024:
            break
    return path


def describe(sheet):
    m = sheet.marks[0]
    a = m.meta["approach"]
    return {"plan_pick": m.meta["plan_pick"], "bends": a["bends"], "handed": len(a["handed"]),
            "by_hand": np.bincount([d["hand"] for d in a["handed"]], minlength=3).tolist() if a["handed"] else [],
            "events": [(e["kind"], round(e["zoom"], 1)) for e in a["events"]],
            "resid_deg": round(a["resid_deg"], 1), "U": [round(x) for x in a["U"]],
            "peaks": [round(x["peak"], 1) for x in a["approaches"]], "fit": round(m.meta["fit"]["scale"], 3),
            "points": len(m.points)}


def probe(seeds, **voice):
    for sd in seeds:
        sh = kit.run(recipe(sd, **voice))
        tag = "-".join(f"{k}{v}" for k, v in sorted(voice.items()) if not isinstance(v, list)) or "default"
        p = OUT / f"probe-{sd}-{tag}.jpg"
        im = draw(sh, colour=True)
        save_jpg(label(im, f"seed {sd} {tag}"), p)
        sh.save_recipe(p.with_suffix(".recipe.json"))
        print(p.name, describe(sh))


def _main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "population":
        population(OUT / "population.jpg")
        return
    if cmd == "review":
        review(int(sys.argv[2]) if len(sys.argv) > 2 else 6204)
        return
    if cmd == "probe":
        args = sys.argv[2:]
        seeds = [int(a) for a in args if a.isdigit()]
        kv = {}
        for a in args:
            if "=" in a:
                k, v = a.split("=", 1)
                try:
                    kv[k] = json.loads(v)
                except json.JSONDecodeError:
                    kv[k] = v
        probe(seeds or [4410], **kv)


def joints(sheet):
    """(index, point, from_src, to_src) at every change of src along the line."""
    m = sheet.marks[0]
    src = m.channels["src"]
    idx = np.flatnonzero(np.diff(src) != 0) + 1
    return [(int(i), m.points[i], int(src[i - 1]), int(src[i])) for i in idx]


def closeups(sheet, path, n=6, w=70.0, h=46.0, px=10.0, colour=True):
    """A grid of crops around the first n handover joints (hand or event)."""
    js = [j for j in joints(sheet) if j[2] == 0][:n]
    tiles = []
    for i, p, a, b in js:
        crop = (p[0] - w / 2, p[1] - h / 2, p[0] + w / 2, p[1] + h / 2)
        im = draw(sheet, px_per_mm=px, colour=colour, crop=crop)
        tiles.append(label(im, f"joint at {p[0]:.0f},{p[1]:.0f} mm: stem -> src {b}  zoom {sheet.marks[0].channels['zoom'][i]:.1f}x"))
    if not tiles:
        return None
    cols = 2 if len(tiles) in (2, 4) else min(3, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    tw, th = tiles[0].size
    out = Image.new("RGB", (tw * cols + 8 * (cols - 1), th * rows + 8 * (rows - 1)), (230, 228, 217))
    for k, t in enumerate(tiles):
        out.paste(t, ((k % cols) * (tw + 8), (k // cols) * (th + 8)))
    return save_jpg(out, path)


PIECE = {"approaches": 4, "peak": 40.0, "vary": 0.7, "share": 0.5}
FRAME = (300, 160)
VARIANTS = [
    ("A carrier only: the magnified stem, no hands, no event", 7101, {"handover": "none", "event": "none"}),
    ("B ladder 0.5: hands take bends in their zoom band", 7102, {"event": "none"}),
    ("C ladder 0.95: the hands own the middle zooms", 7103, {"share": 0.95, "event": "none"}),
    ("D peak only: river_bend near each peak", 7104, {"handover": "peak", "hands": ["river_bend"], "event": "none"}),
    ("E ladder + a cut-off bend at the nearest approach", 7105, {}),
    ("F one approach, slow in, quick out", 7106, {"approaches": 1, "skew": 0.85, "width": 0.7}),
    ("G three approaches, quick in, slow out", 7107, {"approaches": 3, "skew": -0.6}),
    ("H never close: four shallow approaches (peak 10)", 7108, {"peak": 10.0}),
]
DUDS = [
    ("dud: oxbow lakes hung at the apex of the nearest bends (real OSM outlines, carrier only)", 7105,
     {"handover": "none", "event": "oxbow", "events": 2}),
]


def population(path, variants=VARIANTS, colour=True, frame=FRAME, base=PIECE, cols=2):
    tiles, recs = [], []
    for name, sd, kw in variants:
        sh = kit.run(recipe(sd, frame=frame, **{**base, **kw}))
        tiles.append(label(draw(sh, px_per_mm=3.2, colour=colour), f"{name}   (seed {sd})"))
        recs.append({"name": name, "recipe": sh.recipe, "describe": describe(sh)})
        print(name, describe(sh))
    rows = (len(tiles) + cols - 1) // cols
    tw, th = tiles[0].size
    out = Image.new("RGB", (tw * cols + 10 * (cols - 1), th * rows + 10 * (rows - 1)), (230, 228, 217))
    for k, t in enumerate(tiles):
        out.paste(t, ((k % cols) * (tw + 10), (k // cols) * (th + 10)))
    save_jpg(out, path)
    Path(path).with_suffix(".recipe.json").write_text(json.dumps(recs, indent=1, default=float))
    return path


def review(seed=6204):
    """The ≤ 5 review images, recipe beside each."""
    sh = kit.run(recipe(seed, frame=FRAME, **PIECE))
    print("piece", describe(sh))
    p = save_jpg(draw(sh, px_per_mm=7.0), RES / "rnear-1-piece.jpg")
    sh.save_recipe(p.with_suffix(".recipe.json"))
    im = label(draw(sh, px_per_mm=7.0, colour=True),
               "the same line by source: black = the far GRWL stem (magnified), blue = river_belt (400 w), "
               "green = river_meander (150 w), purple = river_bend (60 w), red = a real cut-off bend")
    p = save_jpg(im, RES / "rnear-2-map.jpg")
    sh.save_recipe(p.with_suffix(".recipe.json"))
    population(RES / "rnear-3-population.jpg")
    p = closeups(sh, RES / "rnear-4-joints.jpg", n=6, w=60.0, h=40.0, px=9.0)
    sh.save_recipe(p.with_suffix(".recipe.json"))
    population(RES / "rnear-5-dud.jpg", variants=DUDS, cols=1)


if __name__ == "__main__":
    _main()
