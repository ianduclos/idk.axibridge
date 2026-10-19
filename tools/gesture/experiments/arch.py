"""Round 15 C `arch`: past keeps in new roles inside ccolour's composer.

    .local/gesture/.venv/bin/python tools/gesture/experiments/arch.py one <seed> [k=v ...]
    .local/gesture/.venv/bin/python tools/gesture/experiments/arch.py pop <seed0> <n> [cols] [k=v ...]
    .local/gesture/.venv/bin/python tools/gesture/experiments/arch.py review     # the review images

Working images go to .local/gesture/out/arch/ with the recipe, the score and the log beside each.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_arch as ar  # noqa: E402
from gesture.kit._score import score_of  # noqa: E402

sys.path.insert(0, str(HERE / "experiments"))
from ccolour import _fit_save, tile  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/arch"


def _val(v):
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def run(seed, **arr):
    sheet = kit.run(ar.recipe(seed, **arr))
    return sheet, sheet.marks[0].meta["arch"]


def save(sheet, log, path, px=6.0, quality=90):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = ar.render(sheet, px_per_mm=px)
    im.save(path, quality=quality, optimize=True)
    sheet.save_recipe(path.with_suffix(".recipe.json"))
    path.with_suffix(".score.json").write_text(json.dumps(score_of(sheet), indent=1) + "\n")
    path.with_suffix(".log.json").write_text(json.dumps(log, indent=1, default=str) + "\n")
    return im


def caption(log):
    p = log["plan"]
    fam = [f for f in ("traverse", "intruder", "flicker", "passer") if p.get(f)]
    names = {"traverse": "danced", "intruder": "swell" + ("+duet" if (p.get("intruder") or {}).get("duet") else ""),
             "flicker": f"flicker×{len(log['flicker'])}",
             "passer": f"passer({(p.get('passer') or {}).get('from')})"}
    n = len(log["pens_used"])
    return (f"{n} pen{'s' if n > 1 else ''} · {p['pens']['mode']} · {p['density']['lines']} lines · "
            + " · ".join(names[f] for f in fam) + f" · events {len(log['events'])}")


def main(argv):
    cmd = argv[0] if argv else "one"
    if cmd == "one":
        seed = int(argv[1]) if len(argv) > 1 else 15001
        arr = {k: _val(v) for k, v in (a.split("=", 1) for a in argv[2:])}
        sheet, log = run(seed, **arr)
        tag = "".join(f"-{k}{v}" for k, v in arr.items()).replace(",", "+")
        save(sheet, log, OUT / f"one-{seed}{tag}.jpg")
        print(seed, caption(log), sheet.meta["seconds"])
    elif cmd == "pop":
        s0 = int(argv[1]) if len(argv) > 1 else 15001
        n = int(argv[2]) if len(argv) > 2 else 8
        cols = int(argv[3]) if len(argv) > 3 else 4
        arr = {k: _val(v) for k, v in (a.split("=", 1) for a in argv[4:])}
        tag = "".join(f"-{k}{v}" for k, v in arr.items()).replace(",", "+")
        items = []
        for s in range(s0, s0 + n):
            sheet, log = run(s, **arr)
            im = save(sheet, log, OUT / f"pop{tag}-{s}.jpg", px=4.0)
            W, H = sheet.frame
            items.append((im, f"{s} · {W:g}×{H:g} · " + caption(log)))
            print(s, f"{W:g}x{H:g}", caption(log), sheet.meta["seconds"], flush=True)
        tile(items, cols, title=f"arch population · seeds {s0}–{s0 + n - 1}{tag} · one procedure").save(
            OUT / f"population{tag}-{s0}-{n}.jpg", quality=86, optimize=True)
    elif cmd == "review":
        review()
    else:
        raise SystemExit(__doc__)


RES = HERE / "results"
POP = (15001, 8)                 # the first 8 consecutive seeds rendered, one procedure, unchosen
STRONG = [15002, 15006, 15008]   # the lead's read of that population: direction at a middle density
# one role per family, each from a population sheet: (seed, register, label)
ROLES = [(15006, "traverse", "danced chain as the traverse (T2): edge to edge through core and blank, beads at "
                             "the dancer's pauses"),
         (15002, "intruder", "bold swell as the heavy intruder (T3): round masses at the core's edge, the only "
                             "weight on the sheet"),
         (15005, "flicker", "limb signs as figure flicker (T7): the line stops, writes a figure, goes on"),
         (15001, "passer", "the passer: accrue 3966's free hand outside, the core's hand and the container's "
                           "pen inside the container")]


def roles_plate(path):
    """Each family in its role: the sheet greyed, the role in its own pens, cropped to it."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    from gesture.kit import arrangers_ccolour as cc  # noqa: PLC0415
    from gesture.kit.core import Ink, Sheet, _font  # noqa: PLC0415
    cc.FLEXOKI.setdefault("ui-2", "#CECDC3")
    cells, recipes = [], {}
    for seed, reg, label in ROLES:
        sh = kit.run(ar.recipe(seed))
        recipes[str(seed)] = sh.recipe
        keep = {reg, "container"} if reg == "passer" else {reg}
        inks, box = [], None
        for k in sh.inks:
            on = k.meta.get("role") in keep
            inks.append(Ink(k.points, k.closed, k.filled, k.pen if on else min(k.pen, 0.25),
                            {**k.meta, "colour": k.meta["colour"] if on else "ui-2"}))
            if k.meta.get("role") == reg:
                lo, hi = k.points.min(axis=0), k.points.max(axis=0)
                box = (lo, hi) if box is None else (np.minimum(box[0], lo), np.maximum(box[1], hi))
        px = 7.0
        im = cc.render_pens(Sheet(sh.frame, sh.marks, inks, sh.meta), px_per_mm=px)
        (lo, hi) = box
        pad = 8.0
        W, H = sh.frame
        x0, y0 = max(lo[0] - pad, 0), max(lo[1] - pad, 0)
        x1, y1 = min(hi[0] + pad, W), min(hi[1] + pad, H)
        cells.append((im.crop((int(x0 * px), int(y0 * px), int(x1 * px), int(y1 * px))), f"{seed} · {label}"))
    out = tile(cells, 2, cell=(1100, 760), title="arch · each revived family in its new role (the rest of the "
               "sheet greyed)")
    _fit_save(out, path)
    path.with_suffix(".recipe.json").write_text(json.dumps({"roles": [list(r) for r in ROLES],
                                                            "recipes": recipes}, indent=1) + "\n")


def review():
    """The ≤ 5 review images in tools/gesture/results/, each with its recipe beside it."""
    import numpy as _np  # noqa: PLC0415
    globals()["np"] = _np
    s0, n = POP
    items, recipes = [], {}
    for s in range(s0, s0 + n):
        sheet, lg = run(s)
        im = save(sheet, lg, OUT / f"pop-{s}.jpg", px=4.0)
        W, H = sheet.frame
        items.append((im, f"{s} · {W:g}×{H:g} · " + caption(lg)))
        recipes[str(s)] = sheet.recipe
    _fit_save(tile(items, 4, title=f"arch population · seeds {s0}–{s0 + n - 1} · one procedure, unchosen"),
              RES / "arch-1-population.jpg")
    (RES / "arch-1-population.recipe.json").write_text(json.dumps(recipes, indent=1) + "\n")
    for k, s in enumerate(STRONG):
        sheet, lg = run(s)
        im = save(sheet, lg, OUT / f"strong-{s}.jpg", px=8.0)
        path = RES / f"arch-{k + 2}-{s}.jpg"
        _fit_save(im, path)
        sheet.save_recipe(path.with_suffix(".recipe.json"))
        print(s, caption(lg))
    roles_plate(RES / "arch-5-roles.jpg")


if __name__ == "__main__":
    main(sys.argv[1:])
