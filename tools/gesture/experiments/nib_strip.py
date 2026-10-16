"""Nib test strip as an image (Ian, 2026-10-16: "not on paper, image is enough").

Five test ribbons × four renderings at the 0.4 mm fineliner — outline (a),
full inset (b+), passes along the stroke (c), nib-point traces (e) — plus the
ideal solid ribbon for reference, each simulated as ink on paper
(penrender.ink_raster: pen width + 0.04 mm bleed). One overview sheet and one
close-up of the line → nib → mass transition.

  cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.nib_strip
  ... -m experiments.nib_strip combos     # b+, c, e and their combinations
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from experiments.penrender_study import ribbons  # noqa: E402
from gesture import penrender as pr  # noqa: E402

PEN = 0.4
COLS = [("ideal", "ideal solid ribbon"), ("a", "a  outline (current)"), ("b+", "b+ full inset"),
        ("c", "c  passes along stroke"), ("e", "e  nib-point traces")]
COMBO_COLS = [("ideal", "ideal"), ("b+", "b+"), ("c", "c"), ("e", "e"), (("c", "e"), "c + e"),
              (("b+", "c"), "b+ + c"), (("b+", "e"), "b+ + e"), (("b+", "c", "e"), "b+ + c + e"),
              ({"c": .5, "e": .5}, "mix c/e per mark")]
ROWS = ["nib W2.5", "loop W2.5 phi30", "nib angle 0-150 deg", "W 0.6-4.5 ramp", "line-nib-mass-nib-line"]
RESULTS = HERE.parent / "results"


def font(size):
    for f in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def panel(key, st, box, pxmm):
    if key == "ideal":
        cov = pr.ideal_raster(st, PEN, box, px_per_mm=pxmm)
        t = None
    else:
        paths = pr.nib_style(list(key) if isinstance(key, tuple) else key)(st, PEN)
        cov = pr.ink_raster(paths, box, px_per_mm=pxmm)
        t = pr.plot_time(paths)
    img = Image.fromarray((255 * (1 - 0.93 * cov)).astype(np.uint8)).convert("RGB")
    paper = np.array([250, 248, 240], dtype=np.float64)
    arr = np.asarray(img, dtype=np.float64) / 255.0 * paper
    return Image.fromarray(arr.astype(np.uint8)), t


def box_of(st, pad=4.0):
    P = st.points
    return (P[:, 0].min() - pad, P[:, 1].min() - pad - 4, P[:, 0].max() + pad, P[:, 1].max() + pad + 4)


def main(cols=COLS, tag=""):
    rib = dict(ribbons())
    pxmm = 12.0
    keyname = lambda k: k if isinstance(k, str) else repr(k)  # noqa: E731
    cells, times = [], {keyname(k): 0.0 for k, _ in cols}
    for name in ROWS:
        st = rib[name]
        b = box_of(st)
        row = []
        for key, _ in cols:
            im, t = panel(key, st, b, pxmm)
            if t is not None:
                times[keyname(key)] += float(t["down_s"] + t["lift_s"])
            row.append(im)
        cells.append(row)
    cw = max(im.width for r in cells for im in r)
    rh = [max(im.height for im in r) for r in cells]
    head, side, gap = 70, 170, 12
    W = side + len(cols) * (cw + gap)
    H = head + sum(h + gap for h in rh) + 40
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    f, fs = font(22), font(17)
    d.text((10, 10), f"Nib test strip — 0.4 mm fineliner, simulated on paper ({pxmm:g} px/mm)", fill=(0, 0, 0), font=f)
    for j, (key, lab) in enumerate(cols):
        x = side + j * (cw + gap)
        tt = "" if key == "ideal" else f"  (~{times[keyname(key)]:.0f} s)"
        d.text((x, 42), lab + tt, fill=(0, 0, 0), font=fs)
    y = head
    for i, name in enumerate(ROWS):
        d.text((8, y + rh[i] // 2 - 10), name, fill=(60, 60, 60), font=fs)
        for j, im in enumerate(cells[i]):
            sheet.paste(im, (side + j * (cw + gap), y))
        y += rh[i] + gap
    d.text((10, H - 30), "Times: pen-down + lifts for the 5 ribbons of each column (app motion model; travel excluded).",
           fill=(90, 90, 90), font=fs)
    out = RESULTS / f"nib-strip{tag}-0.4mm.jpg"
    sheet.save(out, quality=85)

    # close-up: the nib -> mass shoulder of the transition ribbon, 40 px/mm
    st = rib["line-nib-mass-nib-line"]
    P = st.points
    cx = P[:, 0].min() + 0.36 * (P[:, 0].max() - P[:, 0].min())
    cy = P[:, 1].mean()
    b = (cx - 9, cy - 7, cx + 9, cy + 7)
    tiles = [panel(k, st, b, 40.0)[0] for k, _ in cols]
    tw, th = tiles[0].size
    close = Image.new("RGB", (len(tiles) * (tw + 10) + 10, th + 60), (255, 255, 255))
    dc = ImageDraw.Draw(close)
    for j, (im, (_, lab)) in enumerate(zip(tiles, cols)):
        close.paste(im, (10 + j * (tw + 10), 50))
        dc.text((10 + j * (tw + 10), 18), lab, fill=(0, 0, 0), font=fs)
    out2 = RESULTS / f"nib-strip{tag}-0.4mm-closeup.jpg"
    close.save(out2, quality=85)
    print(out, out2, {k: round(v, 1) for k, v in times.items()})


if __name__ == "__main__":
    if sys.argv[1:] == ["combos"]:
        main(COMBO_COLS, "-combos")
    else:
        main()
