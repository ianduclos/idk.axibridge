"""Round 14 thread b2 `cimpro`: the composer as improviser — populations, full sheets, process strips.

    .local/gesture/.venv/bin/python tools/gesture/experiments/cimpro.py run 14001 14002 ...
    .local/gesture/.venv/bin/python tools/gesture/experiments/cimpro.py population 14001 ... --out name
    .local/gesture/.venv/bin/python tools/gesture/experiments/cimpro.py strip 14003 --out name

Frame: 300 × 200 mm, the AxiDraw's full width at 3:2. One format for the whole
population on purpose: a series keeps its format (the composition note, "what a
series keeps"), so the sheets differ by the composition's decisions alone. The
format is large enough for the blank to be half the drawing and for a traverse
to be long.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_cimpro as ci  # noqa: E402
from gesture.kit import arrangers_oehlen_found as of  # noqa: E402

OUT = ROOT / ".local/gesture/out/cimpro"
FRAME = [300.0, 200.0]


def recipe(seed: int, **arr) -> dict:
    return {"label": f"cimpro {seed}", "frame": FRAME, "seed": int(seed), "margin": 0.0,
            "arranger": {"id": "cimpro", **arr},
            "parts": [{"voice": {"id": "hand", "hand": "river_bend", "length": 3.0}}],
            "renderer": {"id": "oehlen_found_ink", "pen": 0.4}}


def run(seed: int, **arr):
    t = time.perf_counter()
    sheet = kit.run(recipe(seed, **arr))
    return sheet, time.perf_counter() - t


def save_sheet(sheet, path, px_per_mm=6.0):
    path = Path(path)
    of.save(sheet, path, px_per_mm=px_per_mm, quality=88)
    log = ci.log_lines(sheet)
    path.with_suffix(".log.txt").write_text("\n".join(log) + "\n")
    return path


def cmd_run(seeds, px=4.0):
    for s in seeds:
        sheet, dt = run(s)
        p = save_sheet(sheet, OUT / f"sheet-{s}.jpg", px)
        T = sheet.marks[0].meta["cimpro"]["temperament"]
        print(f"== {s}  {dt:.1f}s  appetite {T['appetite']:.2f}  inks {len(sheet.inks)}  -> {p.name}")
        print("\n".join(ci.log_lines(sheet)))


def labelled(sheet, title, px=3.0):
    from PIL import Image, ImageDraw  # noqa: PLC0415
    im = of.render_colour(sheet, px_per_mm=px)
    strip = 26
    out = Image.new("RGB", (im.width, im.height + strip), (0xFF, 0xFC, 0xF0))
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    d.text((8, im.height + 6), title.replace("→", "->").replace("×", "x"), fill=(0x57, 0x56, 0x53), font=kit.core._font(15))
    # a hairline frame so the sheet's edge reads on the contact sheet
    d.rectangle([0, 0, im.width - 1, im.height - 1], outline=(0xDA, 0xD8, 0xCE))
    return out


def cmd_population(seeds, name, cols=3, px=3.0):
    imgs, logs, recs = [], [], []
    for s in seeds:
        sheet, dt = run(s)
        lg = ci.log_lines(sheet)
        n = len([x for x in lg if " stop " not in x])
        T = sheet.marks[0].meta["cimpro"]["temperament"]
        imgs.append(labelled(sheet, f"seed {s} · {n} moves · appetite {T['appetite']:.2f}", px))
        logs.append(f"== seed {s} ({dt:.1f}s, appetite {T['appetite']:.2f}, hands {', '.join(T['hands'])})\n" +
                    "\n".join(lg))
        recs.append(sheet.recipe)
        print(logs[-1], flush=True)
    im = kit.contact(imgs, cols, title=f"cimpro — the composer as improviser: {len(seeds)} runs of one procedure "
                                       "(300 × 200 mm each)")
    p = OUT / f"{name}.jpg"
    im.save(p, quality=86, optimize=True)
    p.with_suffix(".recipe.json").write_text(json.dumps(recs, indent=1))
    p.with_suffix(".log.txt").write_text("\n\n".join(logs) + "\n")
    print("->", p)


def cmd_strip(seed, name, cols=4, px=2.2, every=None):
    full, _ = run(seed)
    lg = full.marks[0].meta["cimpro"]["log"]
    n = len([e for e in lg if e["verb"] != "stop"])
    steps = list(range(1, n + 1)) if every is None else sorted(set(list(range(every, n + 1, every)) + [n]))
    imgs, recs = [], []
    for u in steps:
        sheet, _ = run(seed, upto=u)
        e = lg[u - 1]          # upto=u replays the same first u moves (a sheet can still be empty: a reserve)
        what = e.get("what", "")
        what = what if len(what) < 70 else what[:67] + "…"
        imgs.append(labelled(sheet, f"{u}. {e['verb']}: {what}", px))
        recs.append(sheet.recipe)
    im = kit.contact(imgs, cols, title=f"cimpro seed {seed}: the sheet after each move (perceive, decide, act)")
    p = OUT / f"{name}.jpg"
    im.save(p, quality=86, optimize=True)
    p.with_suffix(".recipe.json").write_text(json.dumps(recs, indent=1))
    p.with_suffix(".log.txt").write_text("\n".join(ci.log_lines(full)) + "\n")
    print("->", p)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    a = sys.argv[1:]
    name = a[a.index("--out") + 1] if "--out" in a else None
    seeds = [int(x) for x in a[1:] if x.isdigit()]
    if a[0] == "run":
        cmd_run(seeds)
    elif a[0] == "population":
        cmd_population(seeds, name or "population")
    elif a[0] == "strip":
        ev = int(a[a.index("--every") + 1]) if "--every" in a else None
        cmd_strip(seeds[0], name or f"strip-{seeds[0]}", every=ev)
