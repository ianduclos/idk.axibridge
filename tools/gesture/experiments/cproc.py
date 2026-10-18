"""Round 14 b1 `cproc`: composer as procedure — population sheets and full-size renders.

    .local/gesture/.venv/bin/python tools/gesture/experiments/cproc.py one <seed>
    .local/gesture/.venv/bin/python tools/gesture/experiments/cproc.py pop <name> <seed> <seed> ...
    .local/gesture/.venv/bin/python tools/gesture/experiments/cproc.py plan <seed> ...

Working images go to .local/gesture/out/cproc/ with the recipe beside each.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_cproc as cp  # noqa: E402
from gesture.kit.core import PAPER, _font  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/cproc"


def one(seed, px=6.0, name=None, **dials):
    t = time.time()
    sheet = kit.run(cp.recipe(seed, **dials))
    p = cp.save(sheet, OUT / f"{name or f'one-{seed}'}.jpg", px_per_mm=px)
    row = cp.table_row(sheet)
    (OUT / f"{name or f'one-{seed}'}.plan.json").write_text(json.dumps(sheet.marks[0].meta["cproc"], indent=1))
    print(f"{seed}: {time.time() - t:.1f}s  {json.dumps(row)}", flush=True)
    return p, sheet, row


def tile(paths, rows, title, out, cell=520):
    """A population sheet: every composition at ONE common scale (mm → px), so frames read as sizes."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    ims = [Image.open(p) for p in paths]
    # common scale: the largest frame side fits the cell
    frames = [r["frame"].split()[1].split("×") for r in rows]
    mm = max(max(float(a), float(b)) for a, b in frames)
    k = cell / mm
    cols = 4
    gap = 26
    fs = 15
    lab_h = fs * 3
    nrows = (len(ims) + cols - 1) // cols
    W = cols * cell + (cols + 1) * gap
    Hh = nrows * (cell + lab_h) + (nrows + 1) * gap + 40
    sheet = Image.new("RGB", (W, Hh), (232, 229, 216))
    dr = ImageDraw.Draw(sheet)
    dr.text((gap, 12), title, fill=(16, 15, 15), font=_font(18))
    for n, (im, r, (a, b)) in enumerate(zip(ims, rows, frames)):
        w, h = round(float(a) * k), round(float(b) * k)
        im = im.resize((w, h))
        cx = gap + (n % cols) * (cell + gap)
        cy = 40 + gap + (n // cols) * (cell + lab_h + gap)
        sheet.paste(im, (cx + (cell - w) // 2, cy + (cell - h) // 2))
        dr.text((cx, cy + cell + 4), f"{r['seed']} · {r['frame']} · {r['density']}", fill=(16, 15, 15), font=_font(fs))
        dr.text((cx, cy + cell + 4 + fs + 2), f"dominant {r.get('dominant')} · blank {r['blank']} · "
                f"{r['reversal'].split(' (')[0]} · intruder {r['intruder'].split(' ')[0]}",
                fill=(87, 86, 83), font=_font(fs - 2))
    sheet.save(out, quality=86, optimize=True)
    return out


POP = [50011, 51013, 52027, 53039, 54049, 55057, 56069, 57077, 58089, 59093, 60101, 61109]
PICKS = [(50011, "cproc-2-dense-ladder"), (55057, "cproc-3-soup-chart-rows"), (60101, "cproc-4-sparse-tint")]
DUD = (59093, "cproc-5-dud-small-structure")
RESULTS = HERE / "results"


def _fit_jpeg(im, path, limit=400_000):
    for q in (90, 86, 82, 78, 74, 70, 65, 60):
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < limit:
            return q
    return q


def final():
    """The review images: the population sheet, three full-size picks and one dud (recipes beside)."""
    from PIL import Image  # noqa: PLC0415
    paths, rows, recs = [], [], []
    for sd in POP:
        p, sheet, row = one(sd, px=4.0, name=f"final-{sd}")
        paths.append(p)
        rows.append(row)
        recs.append({"seed": sd, "decisions": row, "recipe": sheet.recipe})
    out = RESULTS / "cproc-1-population.jpg"
    tile(paths, rows, "cproc: one procedure, 12 seeds (50011–61109, none left out), all at one common scale",
         OUT / "final-population.jpg")
    im = Image.open(OUT / "final-population.jpg")
    _fit_jpeg(im, out)
    (RESULTS / "cproc-1-population.recipe.json").write_text(json.dumps(recs, indent=1))
    for sd, name in PICKS + [DUD]:
        sheet = kit.run(cp.recipe(sd))
        W, H = sheet.frame
        px = 2400.0 / max(W, H) if max(W, H) > 200 else 12.0
        im = cp.render(sheet, px_per_mm=px)
        q = _fit_jpeg(im, RESULTS / f"{name}.jpg")
        sheet.save_recipe(RESULTS / f"{name}.recipe.json")
        print(name, im.size, q, (RESULTS / f"{name}.jpg").stat().st_size, flush=True)


def main(argv):
    cmd = argv[0]
    if cmd == "one":
        for s in argv[1:]:
            one(int(s))
    elif cmd == "pop":
        name, seeds = argv[1], [int(s) for s in argv[2:]]
        paths, rows = [], []
        for s in seeds:
            p, _, row = one(s, px=4.0, name=f"{name}-{s}")
            paths.append(p)
            rows.append(row)
        (OUT / f"{name}-table.json").write_text(json.dumps(rows, indent=1))
        tile(paths, rows, f"cproc population {name}: one procedure, {len(seeds)} seeds, shown at one common scale",
             OUT / f"{name}-population.jpg")
    elif cmd == "final":
        final()
    elif cmd == "plan":
        for s in argv[1:]:
            frame, nm, why = cp.frame_for(int(s))
            print(s, nm, frame)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
