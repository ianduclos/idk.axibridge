"""Round 14 b4 `ccolour`: colour as structure — compositions whose pens carry what each line does.

    .local/gesture/.venv/bin/python tools/gesture/experiments/ccolour.py one <seed> [k=v ...]
    .local/gesture/.venv/bin/python tools/gesture/experiments/ccolour.py pop <seed0> <n> [cols]
    .local/gesture/.venv/bin/python tools/gesture/experiments/ccolour.py legend <seed>
    .local/gesture/.venv/bin/python tools/gesture/experiments/ccolour.py review   # the 5 review images

Working images go to .local/gesture/out/ccolour/ with the recipe (and the composer's log) beside each.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_ccolour as cc  # noqa: E402
from gesture.kit.core import PAPER, _font  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/ccolour"


def _val(v):
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def run(seed, **arr):
    sheet = kit.run(cc.recipe(seed, **arr))
    return sheet, sheet.marks[0].meta["ccolour"]


def save(sheet, log, path, px=6.0, quality=90):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = cc.render_pens(sheet, px_per_mm=px)
    im.save(path, quality=quality, optimize=True)
    sheet.save_recipe(path.with_suffix(".recipe.json"))
    path.with_suffix(".log.json").write_text(json.dumps(log, indent=1, default=str) + "\n")
    return im


def caption(log):
    p = log["plan"]
    pp = p["pens"]
    acts = [k for k in ("container", "traverse", "counter", "intruder") if p.get(k)]
    kinds = {}
    for e in log["events"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    n = len(log["pens_used"])
    return (f"{n} pen{'s' if n > 1 else ''} · {pp['mode']} · {p['density']['lines']} lines · "
            f"{'+'.join(f['kind'] for f in p['found'])}" + (f" · {', '.join(acts)}" if acts else "")
            + f" · events {sum(kinds.values())}")


def tile(items, cols, cell=(900, 640), title=None, pad=24):
    """Compositions of different frames on one sheet: each fitted into an equal cell, captioned."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    rows = -(-len(items) // cols)
    fs = 18
    th = 54 if title else 0
    cw, ch = cell
    capt = fs * 2
    sheet = Image.new("RGB", (cols * (cw + pad) + pad, th + rows * (ch + capt + pad) + pad), (0xF2, 0xF0, 0xE5))
    dr = ImageDraw.Draw(sheet)
    if title:
        dr.text((pad, 16), title, fill=(0x10, 0x0F, 0x0F), font=_font(24))
    for i, (im, text) in enumerate(items):
        r, c = divmod(i, cols)
        k = min(cw / im.width, ch / im.height)
        sm = im.resize((int(im.width * k), int(im.height * k)), Image.Resampling.LANCZOS)
        x = pad + c * (cw + pad) + (cw - sm.width) // 2
        y = th + pad + r * (ch + capt + pad) + (ch - sm.height) // 2
        sheet.paste(sm, (x, y))
        dr.rectangle([x - 1, y - 1, x + sm.width, y + sm.height], outline=(0xCE, 0xCD, 0xC3))
        dr.text((pad + c * (cw + pad), th + pad + r * (ch + capt + pad) + ch + 6), text, fill=(0x57, 0x56, 0x53),
                font=_font(fs))
    return sheet


def main(argv):
    cmd = argv[0] if argv else "one"
    if cmd == "one":
        seed = int(argv[1]) if len(argv) > 1 else 4401
        arr = dict(a.split("=", 1) for a in argv[2:])
        arr = {k: _val(v) for k, v in arr.items()}
        sheet, log = run(seed, **arr)
        tag = "".join(f"-{k}{v}" for k, v in arr.items())
        save(sheet, log, OUT / f"one-{seed}{tag}.jpg")
        print(seed, caption(log), sheet.meta["seconds"])
        for e in log["events"]:
            print("   ", e)
    elif cmd == "pop":
        s0 = int(argv[1]) if len(argv) > 1 else 4401
        n = int(argv[2]) if len(argv) > 2 else 12
        cols = int(argv[3]) if len(argv) > 3 else 4
        items = []
        for s in range(s0, s0 + n):
            sheet, log = run(s)
            im = save(sheet, log, OUT / f"pop-{s}.jpg", px=4.0)
            W, H = sheet.frame
            items.append((im, f"{s} · {W:g}×{H:g} · " + caption(log)))
            print(s, f"{W:g}x{H:g}", caption(log), sheet.meta["seconds"], flush=True)
        tile(items, cols, title=f"ccolour population · seeds {s0}–{s0 + n - 1} · one procedure").save(
            OUT / f"population-{s0}-{n}.jpg", quality=86, optimize=True)
    elif cmd == "legend":
        seed = int(argv[1]) if len(argv) > 1 else 4401
        a, la = run(seed)
        b, lb = run(seed, colouring="legend")
        ia = save(a, la, OUT / f"pair-{seed}-composed.jpg")
        ib = save(b, lb, OUT / f"pair-{seed}-legend.jpg")
        tile([(ib, "legend: every role always in its pen (the round-13 map)"),
              (ia, "composed: " + caption(la))], 2, cell=(1100, 780)).save(OUT / f"pair-{seed}.jpg", quality=88)
    elif cmd == "review":
        review()
    else:
        raise SystemExit(__doc__)


RES = HERE / "results"
POP = (4505, 16)                 # 16 consecutive seeds of the 24 rendered (4501–4524), one procedure
STRONG = [4520, 4507, 4511]
DUD = 4520


def _fit_save(im, path, long_side=2400, budget=395_000):
    """JPEG ≤ long_side px and under the review size budget."""
    from PIL import Image  # noqa: PLC0415
    k = min(1.0, long_side / max(im.size))
    if k < 1.0:
        im = im.resize((round(im.width * k), round(im.height * k)), Image.Resampling.LANCZOS)
    for q in (88, 84, 80, 76, 72, 68, 64, 60):
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < budget:
            break
    return path


def review():
    """The ≤ 5 review images in tools/gesture/results/, each with its recipe beside it."""
    import json as _j  # noqa: PLC0415
    s0, n = POP
    items, recipes = [], []
    for s in range(s0, s0 + n):
        sheet, log = run(s)
        im = cc.render_pens(sheet, px_per_mm=4.0, grain=False)
        W, H = sheet.frame
        pp = log["plan"]["pens"]
        items.append((im, f"{s} · {W:g}×{H:g} · {len(log['pens_used'])} pens · {pp['mode']} · "
                          f"{log['plan']['density']['lines']} lines · {len(log['events'])} events"))
        recipes.append(sheet.recipe)
    pop = tile(items, 4, cell=(560, 400), title=f"ccolour · one procedure · seeds {s0}–{s0 + n - 1} "
               "(16 consecutive of 24 rendered)", pad=18)
    _fit_save(pop, RES / "ccolour-1-population.jpg")
    (RES / "ccolour-1-population.recipe.json").write_text(_j.dumps(recipes, indent=1) + "\n")
    for i, s in enumerate(STRONG):
        sheet, log = run(s)
        W, H = sheet.frame
        im = cc.render_pens(sheet, px_per_mm=min(8.0, 2400 / max(W, H)), grain=False)
        path = RES / f"ccolour-{i + 2}-{s}.jpg"
        _fit_save(im, path)
        sheet.save_recipe(path.with_suffix(".recipe.json"))
        print(path.name, path.stat().st_size, caption(log))
    a, la = run(DUD)
    b, lb = run(DUD, colouring="legend")
    ia = cc.render_pens(a, px_per_mm=4.0, grain=False)
    ib = cc.render_pens(b, px_per_mm=4.0, grain=False)
    pair = tile([(ib, "dud · legend: every role always in its pen (the round-13 map as the rule)"),
                 (ia, "composed: the same sheet, the pen plan decides · " + caption(la))], 2,
                cell=(1150, 780))
    path = RES / f"ccolour-5-dud-legend-{DUD}.jpg"
    _fit_save(pair, path)
    path.with_suffix(".recipe.json").write_text(_j.dumps([b.recipe, a.recipe], indent=1) + "\n")
    for f in sorted(RES.glob("ccolour-*.jpg")):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    main(sys.argv[1:])
