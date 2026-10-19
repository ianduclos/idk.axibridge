"""Round 15 thread A `listen`: layers that listen to each other.

    .local/gesture/.venv/bin/python tools/gesture/experiments/listen.py one <seed> [k=v ...]
    .local/gesture/.venv/bin/python tools/gesture/experiments/listen.py pop <seed0> <n> [cols]
    .local/gesture/.venv/bin/python tools/gesture/experiments/listen.py annotate <seed>
    .local/gesture/.venv/bin/python tools/gesture/experiments/listen.py review   # the review images

Working images go to .local/gesture/out/listen/ with the recipe and the score beside each.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from experiments.ccolour import tile  # noqa: E402
from gesture import kit  # noqa: E402
from gesture.kit import arrangers_listen as al  # noqa: E402
from gesture.kit._score import score_of  # noqa: E402
from gesture.kit.arrangers_ccolour import render_pens  # noqa: E402
from gesture.kit.arrangers_oehlen_found import FLEXOKI  # noqa: E402
from gesture.kit.core import _font  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/listen"
RESULTS = HERE / "results"


def _val(v):
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def run(seed, **arr):
    sheet = kit.run(al.recipe(seed, **arr))
    return sheet, score_of(sheet)


def save(sheet, path, px=6.0, quality=90):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = render_pens(sheet, px_per_mm=px)
    im.save(path, quality=quality, optimize=True)
    sheet.save_recipe(path.with_suffix(".recipe.json"))
    path.with_suffix(".score.json").write_text(json.dumps(score_of(sheet), indent=1) + "\n")
    return im


def caption(score):
    kinds = {}
    for r in score["relations"]:
        if r["kind"] in ("weave", "yield"):
            continue
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    d = score["decisions"]
    return (f"{len(score['layers'])} layers · {len(d['palette'])} pens · "
            + " ".join(f"{k}{'×' + str(v) if v > 1 else ''}" for k, v in kinds.items())
            + f" · {d['density']['achieved']} mm/cm²")


def _stretch(sheet, lid, s_range, px):
    """The drawn pieces of layer `lid` that fall in its arc-length range (the score's `s`)."""
    import numpy as np  # noqa: PLC0415
    from gesture.kit.arrangers_oehlen_found import arclen  # noqa: PLC0415
    out = []
    for m in sheet.marks:
        if m.meta.get("layer") != lid or m.meta.get("s0") is None:
            continue
        s = m.meta["s0"] + arclen(m.points)
        keep = (s >= s_range[0]) & (s <= s_range[1])
        if keep.sum() >= 2:
            out.append([tuple(v) for v in m.points[keep] * px])
    return out


RELCOL = {"imitate": "#205EA6", "exaggerate": "#AF3029", "translate": "#66800B", "refuse": "#5E409D",
          "echo": "#24837B", "calm": "#BC5215", "nest": "#A02F6F", "bind": "#AD8301", "mask": "#100F0F",
          "ignore": "#6F6E69"}


def annotate(sheet, px=6.0):
    """The sheet drawn faint; each relation labelled at its `at` from the sheet's own score, its dst
    stretch (score `s`) drawn bold in the relation's colour and the stretch it heard (dst params
    `gesture_src_mm`) drawn dashed-thin in the same colour. Aware crossings are small grey rings."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    base = render_pens(sheet, px_per_mm=px, grain=False)
    a = np.asarray(base, float)
    a = 255 - (255 - a) * 0.32
    im = Image.fromarray(a.astype("uint8"))
    dr = ImageDraw.Draw(im)
    sc = score_of(sheet)
    lay = {l["id"]: l for l in sc["layers"]}
    f = _font(int(px * 2.8))
    fs = _font(int(px * 2.1))
    n_cross = 0
    for r in sc["relations"]:
        if r["kind"] in ("weave", "yield") and r["at"]:
            n_cross += 1
            x, y = r["at"][0] * px, r["at"][1] * px
            dr.ellipse([x - 5, y - 5, x + 5, y + 5], outline=(0x9F, 0x9D, 0x96), width=2)
    placed = []
    # the void: its polygon dashed, one label naming who it cuts and who crosses it
    for l in sc["layers"]:
        poly = l.get("params", {}).get("polygon") if l["role"] == "mask" else None
        if not poly:
            continue
        q = [(x * px, y * px) for x, y in poly]
        for k in range(len(q) - 1):
            x0, y0 = q[k]
            x1, y1 = q[k + 1]
            n = max(int(math.hypot(x1 - x0, y1 - y0) / 14), 1)
            for t in range(0, n, 2):
                dr.line([(x0 + (x1 - x0) * t / n, y0 + (y1 - y0) * t / n),
                         (x0 + (x1 - x0) * (t + 1) / n, y0 + (y1 - y0) * (t + 1) / n)], fill=(0x10, 0x0F, 0x0F), width=3)
        cut = [r["dst"] for r in sc["relations"] if r["kind"] == "mask" and r["src"] == l["id"]]
        crossed = [r["dst"] for r in sc["relations"] if r["kind"] == "ignore" and r["src"] == l["id"]]
        tx, ty = min(x for x, _ in q), min(y for _, y in q) - px * 9
        for text in (f"mask {l['id']}: cuts {', '.join(cut) or '-'}", f"crossed by {', '.join(crossed) or '-'}"):
            dr.text((tx + 1, ty + 1), text, fill=(0xFF, 0xFC, 0xF0), font=f)
            dr.text((tx, ty), text, fill=(0x10, 0x0F, 0x0F), font=f)
            placed.append((tx, ty))
            ty += px * 4
    for r in sc["relations"]:
        if r["kind"] in ("weave", "yield", "mask", "ignore") or r["at"] is None:
            continue
        col = RELCOL.get(r["kind"], "#100F0F")
        if r["s"]:
            for q in _stretch(sheet, r["dst"], r["s"], px):
                dr.line(q, fill=col, width=int(px * 0.9), joint="curve")
        src_mm = lay.get(r["dst"], {}).get("params", {}).get("gesture_src_mm")
        if src_mm and r["kind"] in ("imitate", "exaggerate", "translate"):
            for q in _stretch(sheet, r["src"], src_mm, px):
                for k in range(0, len(q) - 1, 6):
                    dr.line(q[k:k + 4], fill=col, width=int(px * 0.5))
        x, y = r["at"][0] * px, r["at"][1] * px
        dr.ellipse([x - px * 1.6, y - px * 1.6, x + px * 1.6, y + px * 1.6], outline=col, width=3)
        text = f"{r['kind']} {r['src']} > {r['dst']}"
        tx, ty = x + px * 2 + 4, y - px * 2
        for (px0, py0) in placed:
            if abs(px0 - tx) < 200 and abs(py0 - ty) < 26:
                ty = py0 + 28
        placed.append((tx, ty))
        dr.text((tx + 1, ty + 1), text, fill=(0xFF, 0xFC, 0xF0), font=f)
        dr.text((tx, ty), text, fill=col, font=f)
    # the layer key, in a panel under the drawing
    rows = [f"{l['id']}  {l['role']:8s} {l['technique']:18s} {l['label']}" for l in sc["layers"]]
    rows.append(f"grey rings: {n_cross} aware crossings (weave / yield), one per pair of layers.  Bold: the "
                "stretch that listened (score s on dst).  Dashed: the stretch it heard (dst gesture_src_mm).")
    panel = Image.new("RGB", (im.width, 24 + 24 * len(rows)), (0xF2, 0xF0, 0xE5))
    full = Image.new("RGB", (im.width, im.height + panel.height), (0xF2, 0xF0, 0xE5))
    full.paste(im, (0, 0))
    full.paste(panel, (0, im.height))
    im = full
    dr = ImageDraw.Draw(im)
    y = im.height - panel.height + 12
    for k, text in enumerate(rows):
        if k < len(sc["layers"]):
            ink = (sc["layers"][k].get("pen") or {}).get("ink", "black")
            h = FLEXOKI.get(ink, FLEXOKI["black"]).lstrip("#")
            dr.rectangle([14, y + 5, 40, y + 15], fill=tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
        dr.text((48, y), text, fill=(0x10, 0x0F, 0x0F), font=fs)
        y += 24
    return im


POP = (15101, 12)          # held out: the composer was tuned on 15001–15016, never on these
STRONG = (15102, 15106, 15112)
ANNOTATED = 15102


def _fit_jpeg(im, path, limit=400_000, long_side=2400):
    from PIL import Image  # noqa: PLC0415
    k = min(1.0, long_side / max(im.size))
    if k < 1.0:
        im = im.resize((int(im.width * k), int(im.height * k)), Image.Resampling.LANCZOS)
    for q in (90, 86, 82, 78, 74, 70, 65, 60):
        im.save(path, quality=q, optimize=True)
        if Path(path).stat().st_size < limit:
            return q
    return q


def review():
    """The thread's review images, into tools/gesture/results/, with a recipe (and score) beside each."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    s0, n = POP
    items, recipes = [], []
    for s in range(s0, s0 + n):
        sheet, sc = run(s)
        im = render_pens(sheet, px_per_mm=4.0)
        W, H = sheet.frame
        items.append((im, f"{s} · {W:g}×{H:g} · " + caption(sc)))
        recipes.append(sheet.recipe)
    pop = tile(items, 4, title=f"listen · population · seeds {s0}–{s0 + n - 1} · one procedure, consecutive, unpicked")
    _fit_jpeg(pop, RESULTS / "listen-1-population.jpg")
    (RESULTS / "listen-1-population.recipe.json").write_text(json.dumps({"panels": recipes}, indent=1) + "\n")
    for k, s in enumerate(STRONG):
        sheet, sc = run(s)
        W, H = sheet.frame
        im = render_pens(sheet, px_per_mm=min(8.0, 2400.0 / max(W, H)))
        name = f"listen-{k + 2}-{s}"
        _fit_jpeg(im, RESULTS / f"{name}.jpg")
        sheet.save_recipe(RESULTS / f"{name}.recipe.json")
        (RESULTS / f"{name}.score.json").write_text(json.dumps(sc, indent=1) + "\n")
    sheet, sc = run(ANNOTATED)
    W, H = sheet.frame
    _fit_jpeg(annotate(sheet, px=min(8.0, 2400.0 / max(W, H))), RESULTS / f"listen-5-annotated-{ANNOTATED}.jpg")
    sheet.save_recipe(RESULTS / f"listen-5-annotated-{ANNOTATED}.recipe.json")
    (RESULTS / f"listen-5-annotated-{ANNOTATED}.score.json").write_text(json.dumps(sc, indent=1) + "\n")


def main(argv):
    cmd = argv[0] if argv else "one"
    if cmd == "one":
        seed = int(argv[1]) if len(argv) > 1 else 15001
        arr = {k: _val(v) for k, v in (a.split("=", 1) for a in argv[2:])}
        sheet, sc = run(seed, **arr)
        tag = "".join(f"-{k}{v}" for k, v in arr.items())
        save(sheet, OUT / f"one-{seed}{tag}.jpg")
        print(seed, caption(sc), sheet.meta["seconds"])
        for r in sc["relations"]:
            print("   ", r["kind"], r["src"], "→", r["dst"], r["at"], r["note"])
    elif cmd == "pop":
        s0 = int(argv[1]) if len(argv) > 1 else 15001
        n = int(argv[2]) if len(argv) > 2 else 12
        cols = int(argv[3]) if len(argv) > 3 else 4
        items = []
        for s in range(s0, s0 + n):
            sheet, sc = run(s)
            im = save(sheet, OUT / f"pop-{s}.jpg", px=4.0)
            W, H = sheet.frame
            items.append((im, f"{s} · {W:g}×{H:g} · " + caption(sc)))
            print(s, f"{W:g}x{H:g}", caption(sc), sheet.meta["seconds"], flush=True)
        tile(items, cols, title=f"listen population · seeds {s0}–{s0 + n - 1} · one procedure, unpicked").save(
            OUT / f"population-{s0}-{n}.jpg", quality=86, optimize=True)
    elif cmd == "annotate":
        seed = int(argv[1]) if len(argv) > 1 else 15001
        sheet, sc = run(seed)
        annotate(sheet).save(OUT / f"annotated-{seed}.jpg", quality=88)
    elif cmd == "review":
        review()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
