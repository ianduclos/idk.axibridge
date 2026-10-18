"""Round 14 b3, `cgram`: compositions as a grammar.

    .local/gesture/.venv/bin/python tools/gesture/experiments/cgram.py one <seed> [uniform]
    .local/gesture/.venv/bin/python tools/gesture/experiments/cgram.py sweep <seed0> <n> [uniform]
    .local/gesture/.venv/bin/python tools/gesture/experiments/cgram.py pop <name> <seed,seed,...> [uniform]
    .local/gesture/.venv/bin/python tools/gesture/experiments/cgram.py full <seed> <out.jpg>

Working images go to .local/gesture/out/cgram/ with the recipe beside each.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_cgram as cg  # noqa: E402
from gesture.kit import arrangers_oehlen_found as of  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/cgram"


def build(seed, uniform=False):
    r = cg.recipe(seed, uniform=uniform)
    sheet = kit.run(r)
    return r, sheet


def one(seed, uniform=False, px=4.0, out=None):
    r, sheet = build(seed, uniform)
    name = f"{'u' if uniform else 's'}{seed}"
    path = Path(out) if out else OUT / f"{name}.jpg"
    of.save(sheet, path, px_per_mm=px)
    log = sheet.marks[0].meta.get("cgram", {}).get("moves", [])
    dead = [m for m in log if m["touched_mm"] < 1.0]
    print(f"{name}: {len(log)} moves, {len(sheet.marks)} marks, {sheet.meta['seconds']}, dead={len(dead)} "
          f"{[(m['k'], m['move'], m.get('error', '')) for m in dead]}", flush=True)
    return path, sheet


def _job(args):
    seed, uniform = args
    try:
        p, s = one(seed, uniform)
        return seed, str(p), s.marks[0].meta.get("cgram", {}).get("moves", [])
    except Exception as e:  # noqa: BLE001
        return seed, None, repr(e)


def sweep(seeds, uniform=False, procs=6):
    from multiprocessing import Pool  # noqa: PLC0415
    with Pool(procs) as pool:
        res = pool.map(_job, [(s, uniform) for s in seeds])
    for seed, p, log in res:
        if p is None:
            print("FAIL", seed, log)
    return res


def population(name, seeds, uniform=False, cols=6, px=1.7):
    """Contact sheet of the seeds (each image labelled with its seed and move count) + a json of sentences."""
    from PIL import ImageDraw  # noqa: PLC0415

    from gesture.kit.core import INK, _font  # noqa: PLC0415
    ims, sents = [], {}
    for s in seeds:
        r, sheet = build(s, uniform)
        im = of.render_colour(sheet, px_per_mm=px)
        n = len(sheet.marks[0].meta["cgram"]["moves"])
        dr = ImageDraw.Draw(im)
        dr.text((8, 6), f"{s} · {n} moves", fill=INK, font=_font(15))
        ims.append(im)
        sents[s] = r["arranger"]["sentence"]
    title = f"cgram population ({'uniform control' if uniform else 'per-sheet temperament'}): {len(seeds)} seeds, one procedure"
    sheet_im = kit.contact(ims, cols, title=title)
    path = ROOT / "tools/gesture/results" / f"{name}.jpg" if name.startswith("cgram-") else OUT / f"{name}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet_im.save(path, quality=88, optimize=True)
    rec = [cg.recipe(s, uniform=uniform) for s in seeds]
    path.with_suffix(".recipe.json").write_text(json.dumps(rec, indent=1))
    print(path, sheet_im.size)
    return path


if __name__ == "__main__":
    cmd = sys.argv[1]
    uni = "uniform" in sys.argv[2:]
    if cmd == "one":
        one(int(sys.argv[2]), uni)
    elif cmd == "sweep":
        s0, n = int(sys.argv[2]), int(sys.argv[3])
        sweep(list(range(s0, s0 + n)), uni)
    elif cmd == "pop":
        population(sys.argv[2], [int(x) for x in sys.argv[3].split(",") if x], uni)
    elif cmd == "full":
        one(int(sys.argv[2]), uni, px=6.0, out=sys.argv[3])
