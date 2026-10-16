"""Nib ribbons at real pen widths (results/penrender-2026-10-16.md).

Stages:
  eval     every strategy × pen width × ribbon: physical render vs the ideal
           solid ribbon, pen cost, estimated time  → out/penrender/eval.json
  sheets   overview sheets (one per pen width, rows = ribbons, columns =
           ideal + strategies), physically rendered at 20 px/mm and shown at
           6 px/mm → results/penrender-sheet-p*.jpg
  crops    1:1 crops at 20 px/mm (magnified detail) → results/penrender-crops.jpg
  blind    blinded pairs ideal vs strategy → .local/gesture/out/blind_nib/pairs,
           key /tmp/gesture_nib_key.json (outside the repo)

Pens: Ian's library (~/.axibridge/pens.json, read 2026-10-16) has a Uniball
at 0.2 mm and a black fineliner at 0.4 mm (plus a red brush pen entered at
0.4, its default). 0.8 mm is hypothetical; the two-pen marker is
max(1.0, 2.5·pen) mm, also hypothetical — no marker is in the library.

Run from tools/gesture:
  ../../.local/gesture/.venv/bin/python -m experiments.penrender_study eval sheets crops blind
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

from gesture import penrender as pr
from gesture import regime as rg

REPO = Path(os.environ.get("PENRENDER_REPO") or Path(__file__).resolve().parents[3])
OUT = REPO / ".local/gesture/out/penrender"
BLIND = REPO / ".local/gesture/out/blind_nib/pairs"
KEY = Path(os.environ.get("NIB_BLIND_KEY", "/tmp/gesture_nib_key.json"))
RESULTS = REPO / "tools/gesture/results"
PENS = (0.2, 0.4, 0.8)
REAL = {0.2: "Uniball 0.2 (library)", 0.4: "fineliner 0.4 (library)", 0.8: "0.8 (hypothetical)"}
ORDER = ("a", "b", "b+", "c", "d", "e", "f")
PX = 20.0
SPREAD = 0.04


def _wave(L=50.0, amp=4.0, n=400, per=30.0):
    x = np.linspace(0, L, n)
    return np.column_stack([x, amp * np.sin(2 * np.pi * x / per)])


def ribbons():
    """The test set: thin → thick nibs, nib angle varying, a loop, a width
    ramp, and regime transitions line → nib → mass → nib → line."""
    out = []
    for W in (1.2, 2.5, 4.0):
        out.append((f"nib W{W}", rg.make(_wave(46, 4.5, 400, 40), 1.0, phi=np.deg2rad(45), W=W)))
    t = np.linspace(0, 2.15 * np.pi, 400)
    loop = np.column_stack([16 + 9 * np.cos(t - np.pi / 2) + 2.0 * t, 8 + 7 * np.sin(t - np.pi / 2)])
    out.append(("loop W2.5 phi30", rg.make(loop, 1.0, phi=np.deg2rad(30), W=2.5)))
    p = _wave(46, 5.0, 400, 23)
    out.append(("nib angle 0-150 deg", rg.make(p, 1.0, phi=np.deg2rad(np.linspace(0, 150, 400)), W=3.0)))
    p = _wave(46, 3.0, 400, 60)
    out.append(("W 0.6-4.5 ramp", rg.make(p, 1.0, phi=np.deg2rad(60), W=np.linspace(0.6, 4.5, 400))))
    base = rg.make(_wave(46, 3.0, 400, 45), 0.0, phi=np.deg2rad(50), W=2.4)
    out.append(("line-nib-line", rg.thicken(base, 0.2, until=0.7)))
    out.append(("line-nib-mass-nib-line", rg.swell(rg.thicken(base, 0.08, until=0.82), 0.5, length=20, size=7)))
    return out


def _box(st, pad=2.5):
    P = st.points
    return (P[:, 0].min() - pad - 4, P[:, 1].min() - pad - 4, P[:, 0].max() + pad + 4, P[:, 1].max() + pad + 4)


def _render(key, st, pen):
    rend = pr.strategy(key)
    return rend(st, pen)


# ---------------------------------------------------------------------------

def _eval_job(args):
    key, ri, pen = args
    name, st = ribbons()[ri]
    paths = _render(key, st, pen)
    ev = pr.evaluate(st, paths, pen, px_per_mm=PX, spread=SPREAD)
    ev.update({"strategy": key, "ribbon": name, "pen": pen})
    return ev


def stage_eval():
    from multiprocessing import Pool
    jobs = [(k, i, p) for p in PENS for k in ORDER for i in range(len(ribbons()))]
    with Pool(3) as pool:
        rows = pool.map(_eval_job, jobs)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "eval.json").write_text(json.dumps(rows, indent=1))
    # summary per pen × strategy
    summ = {}
    for p in PENS:
        for k in ORDER:
            rs = [r for r in rows if r["pen"] == p and r["strategy"] == k]
            summ[f"{p}/{k}"] = {
                "coverage_mean": float(np.mean([r["coverage"] for r in rs])),
                "coverage_min": float(np.min([r["coverage"] for r in rs])),
                "gap_med_mm": float(np.median([r["gap_mm"] for r in rs])),
                "gap_max_mm": float(np.max([r["gap_mm"] for r in rs])),
                "edge_mm": float(np.mean([r["edge_mm"] for r in rs])),
                "spill": float(np.mean([r["spill"] for r in rs])),
                "length_mm": float(np.sum([r["length_mm"] for r in rs])),
                "paths": int(np.sum([r["paths"] for r in rs])),
                "time_s": float(np.sum([r["time_ex_swap_s"] for r in rs])),
            }
    (OUT / "eval_summary.json").write_text(json.dumps(summ, indent=1))
    print(f"{'pen':>4} {'s':>3} {'cov':>6} {'covmin':>6} {'gap50':>6} {'gapmax':>6} {'edge':>6} "
          f"{'len_m':>6} {'paths':>5} {'time_s':>7}")
    for kk, v in summ.items():
        p, k = kk.split("/")
        print(f"{p:>4} {k:>3} {v['coverage_mean']:6.3f} {v['coverage_min']:6.3f} {v['gap_med_mm']:6.2f} "
              f"{v['gap_max_mm']:6.2f} {v['edge_mm']:6.3f} {v['length_mm'] / 1000:6.2f} {v['paths']:5d} "
              f"{v['time_s']:7.1f}")


# ---------------------------------------------------------------------------
# sheets

def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except OSError:
        return ImageFont.load_default()


def _to_img(cov: np.ndarray):
    from PIL import Image
    return Image.fromarray((255 * (1.0 - cov)).astype(np.uint8), "L")


def _cell(key, st, pen, box, *, show_px: float, misreg=False):
    """Physically rendered cell at PX px/mm, resampled to show_px."""
    from PIL import Image
    if key == "ideal":
        cov = pr.ideal_raster(st, pen, box, px_per_mm=PX, spread=SPREAD)
    else:
        paths = _render(key, st, pen)
        off = None
        if misreg and key == "f":
            P = max(paths.pens)
            off = {P: (0.12, -0.08)}
        cov = pr.ink_raster(paths, box, px_per_mm=PX, spread=SPREAD, offsets=off)
    img = _to_img(cov)
    if show_px != PX:
        w, h = img.size
        img = img.resize((max(int(w * show_px / PX), 1), max(int(h * show_px / PX), 1)), Image.Resampling.BOX)
    return img


def _save_jpg(img, path: Path, max_kb: int = 600):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = img.convert("L")
    for q in (88, 82, 75, 68, 60, 50, 40):
        img.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024:
            return
    w, h = img.size
    img.resize((int(w * 0.8), int(h * 0.8))).save(path, quality=60, optimize=True)


def _sheet_job(pen):
    from PIL import Image, ImageDraw
    show = 6.0
    rib = ribbons()
    cols = ("ideal",) + ORDER
    cw, ch = 58, 30            # mm per cell
    lab_h, lab_w = 34, 150
    W = lab_w + int(cw * show) * len(cols)
    H = lab_h + int(ch * show) * len(rib) + 30
    sheet = Image.new("L", (W, H), 255)
    dr = ImageDraw.Draw(sheet)
    f = _font(15)
    for j, k in enumerate(cols):
        t = "ideal solid" if k == "ideal" else f"{k}: {pr.NAMES[k]}"
        dr.text((lab_w + j * int(cw * show) + 6, 8), t, fill=40, font=f)
    for i, (name, st) in enumerate(rib):
        P = st.points
        cx, cy = P[:, 0].mean(), P[:, 1].mean()
        cx = 0.5 * (P[:, 0].min() + P[:, 0].max())
        cy = 0.5 * (P[:, 1].min() + P[:, 1].max())
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        dr.text((6, lab_h + i * int(ch * show) + 10), name, fill=40, font=f)
        for j, k in enumerate(cols):
            img = _cell(k, st, pen, box, show_px=show, misreg=True)
            sheet.paste(img, (lab_w + j * int(cw * show), lab_h + i * int(ch * show)))
    dr.text((6, H - 24), f"pen {pen} mm — {REAL[pen]}; physical render 20 px/mm (disc sweep, +{SPREAD} mm "
            f"spread), shown at {show:g} px/mm; f: marker {max(1.0, 2.5 * pen):g} mm, misregistered "
            f"(0.12, −0.08) mm", fill=40, font=_font(14))
    _save_jpg(sheet, RESULTS / f"penrender-sheet-p{str(pen).replace('.', '')}.jpg")
    return pen


def stage_sheets():
    from multiprocessing import Pool
    with Pool(3) as pool:
        print(pool.map(_sheet_job, PENS))


def stage_crops():
    """Magnified detail: 12 × 9 mm windows at 20 px/mm on the thick part of
    'nib W2.5' and on the nib→mass shoulder of the transition ribbon."""
    from PIL import Image, ImageDraw
    rib = dict(ribbons())
    cw, ch = 12.0, 9.0
    st = rib["nib W2.5"]
    w = rg.ink_width(st, 0.4)
    n = len(w)
    c1 = st.points[n // 5 + int(np.argmax(w[n // 5: -n // 5]))]   # widest, away from the ends
    st = rib["line-nib-mass-nib-line"]
    c2 = st.points[int(np.argmax(st.r > 1.5))]          # where the nib becomes mass
    wins = [("nib W2.5", (c1[0] - cw / 2, c1[1] - ch / 2)),
            ("line-nib-mass-nib-line", (c2[0] - cw / 2, c2[1] - ch / 2))]
    cols = ("ideal",) + ORDER
    show = 14.0
    lab_w, lab_h = 160, 30
    rows = [(pen, w) for pen in PENS for w in wins]
    W = lab_w + int(cw * show) * len(cols)
    H = lab_h + int(ch * show) * len(rows) + 28
    sheet = Image.new("L", (W, H), 255)
    dr = ImageDraw.Draw(sheet)
    f = _font(14)
    for j, k in enumerate(cols):
        dr.text((lab_w + j * int(cw * show) + 4, 8), "ideal" if k == "ideal" else k, fill=40, font=f)
    for i, (pen, (name, (x0, y0))) in enumerate(rows):
        st = rib[name]
        box = (x0, y0, x0 + cw, y0 + ch)
        dr.text((6, lab_h + i * int(ch * show) + 8), f"pen {pen}", fill=40, font=f)
        dr.text((6, lab_h + i * int(ch * show) + 28), name[:18], fill=40, font=_font(12))
        for j, k in enumerate(cols):
            img = _cell(k, st, pen, box, show_px=show, misreg=True)
            sheet.paste(img, (lab_w + j * int(cw * show), lab_h + i * int(ch * show)))
            dr.rectangle([lab_w + j * int(cw * show), lab_h + i * int(ch * show),
                          lab_w + (j + 1) * int(cw * show) - 1, lab_h + (i + 1) * int(ch * show) - 1],
                         outline=200)
    dr.text((6, H - 22), f"12 × 9 mm windows, physical render at 20 px/mm shown at {show:g} px/mm "
            "(≈ 3.7× life size on a 96 dpi screen)", fill=40, font=_font(13))
    _save_jpg(sheet, RESULTS / "penrender-crops.jpg")


# ---------------------------------------------------------------------------
# blind pairs

def _panel(key, st, pen, box, show=10.0):
    return _cell(key, st, pen, box, show_px=show, misreg=True)


def stage_blind():
    """Ideal solid ribbon vs each strategy's physical render, every pen.
    Plus calibration pairs ideal vs ideal (should split ~50/50 with low
    confidence) — the judge's floor."""
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(16)
    rib = ribbons()
    use = [1, 2, 3, 4, 7]                     # W2.5, W4, loop, twist, transition
    BLIND.mkdir(parents=True, exist_ok=True)
    for old in BLIND.glob("pair_*.jpg"):
        old.unlink()
    items = []
    for pen in PENS:
        for k in ORDER:
            for ri in rng.choice(use, 2, replace=False):
                items.append((pen, k, int(ri)))
        for ri in rng.choice(use, 2, replace=False):
            items.append((pen, "ideal", int(ri)))
    rng.shuffle(items)
    key = {}
    for n, (pen, k, ri) in enumerate(items):
        name, st = rib[ri]
        P = st.points
        cx = 0.5 * (P[:, 0].min() + P[:, 0].max())
        cy = 0.5 * (P[:, 1].min() + P[:, 1].max())
        box = (cx - 29, cy - 15, cx + 29, cy + 15)
        ideal = _panel("ideal", st, pen, box)
        other = _panel(k, st, pen, box)
        left_ideal = bool(rng.random() < 0.5)
        A, B = (ideal, other) if left_ideal else (other, ideal)
        w, h = A.size
        img = Image.new("L", (2 * w + 30, h + 40), 255)
        img.paste(A, (0, 40))
        img.paste(B, (w + 30, 40))
        d = ImageDraw.Draw(img)
        d.text((w // 2 - 6, 8), "A", fill=0, font=_font(22))
        d.text((w + 30 + w // 2 - 6, 8), "B", fill=0, font=_font(22))
        d.line([(w + 15, 40), (w + 15, h + 40)], fill=180)
        fn = f"pair_{n:02d}.jpg"
        img.save(BLIND / fn, quality=92)
        key[fn] = {"ideal_side": "A" if left_ideal else "B", "strategy": k, "pen": pen, "ribbon": name}
    (BLIND.parent / "QUESTION.txt").write_text(
        "Each image shows two panels, A (left) and B (right): the same mark as it would look drawn on "
        "paper (about 10 pixels per millimetre). Which panel looks more like a SINGLE stroke of a brush "
        "or broad nib — one solid mark of ink — rather than a drawing made of lines? Answer A or B, "
        "with a confidence 1-5 (1 = can't tell, 5 = certain). If they look the same, still pick one "
        "and give confidence 1.\n")
    KEY.write_text(json.dumps(key, indent=1))
    print(f"{len(items)} pairs → {BLIND}; key → {KEY}")


STAGES = {"eval": stage_eval, "sheets": stage_sheets, "crops": stage_crops, "blind": stage_blind}

if __name__ == "__main__":
    for a in sys.argv[1:] or ["eval"]:
        STAGES[a]()
