"""Round 16 thread A `aware`: awareness as composable relations, tried on listen through the bridge.

    .local/gesture/.venv/bin/python tools/gesture/experiments/aware.py one <seed> [preset]
    .local/gesture/.venv/bin/python tools/gesture/experiments/aware.py pop [preset]       # 15101–15108
    .local/gesture/.venv/bin/python tools/gesture/experiments/aware.py close <seed> <kind> [preset]
    .local/gesture/.venv/bin/python tools/gesture/experiments/aware.py review              # the review images

Working images go to .local/gesture/out/aware/ with the written score (.recipe.json) and the played
score (.played.json) beside each.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from experiments.aware_bridge import score  # noqa: E402
from experiments.ccolour import tile  # noqa: E402
from gesture import kit  # noqa: E402
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit import arrangers_listen as al  # noqa: E402
from gesture.kit.arrangers_ccolour import render_pens  # noqa: E402
from gesture.kit.core import Ink, Sheet  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/aware"
RESULTS = HERE / "results"
SEEDS = list(range(15101, 15109))

PRESETS = {
    "none": [],
    "aware": [{"kind": "sympathy"}, {"kind": "crossing"}],
    "hard": [{"kind": "sympathy", "params": {"gain": 3.0, "reach": 8.0}},
             {"kind": "crossing", "params": {"w_gap_under": 0.4, "w_gap_over": 0.4, "w_cross": 0.0, "w_stop": 0.4,
                                             "w_sympathy": 0.2, "streak": 0.0, "gap": 5.0, "jitter": 0.8,
                                             "stop_max": 80.0, "lean": 3.0}}],
    "all": [{"kind": "make_room"}, {"kind": "accompany"}, {"kind": "sympathy"}, {"kind": "hesitate"},
            {"kind": "crossing"}],
    "more": [{"kind": "make_room"}, {"kind": "accompany"}, {"kind": "hesitate"}],
    "sympathy": [{"kind": "sympathy"}],
    "crossing": [{"kind": "crossing"}],
    "hesitate": [{"kind": "hesitate"}],
    "accompany": [{"kind": "accompany"}],
    "make_room": [{"kind": "make_room"}],
}


def run(seed, preset="aware"):
    specs = PRESETS[preset] if isinstance(preset, str) else preset
    return synth.run(score(seed, specs))


def original(seed):
    return kit.run(al.recipe(seed))


def counts(sheet) -> dict:
    """Outcomes per relation kind: crossing outcomes by name, the other relations by their kind."""
    c = collections.Counter()
    for e in synth.played(sheet)["log"]:
        if e["outcome"] == "silent":
            continue
        c[e["outcome"] if e["kind"] == "crossing" else e["kind"]] += 1
        if e["kind"] == "crossing" and e["outcome"] == "sympathy":
            c["sympathy"] -= 1
            c["bend"] += 1
    return {k: v for k, v in sorted(c.items()) if v}


def caption(seed, sheet):
    c = counts(sheet)
    short = {"gap_under": "under", "gap_over": "over", "cross": "through", "make_room": "room"}
    return f"{seed} · " + " ".join(f"{short.get(k, k)} {v}" for k, v in c.items())


def crop(sheet, box, px=24.0):
    """A close-up: the sheet's inks inside box (x0, y0, w, h) mm, at px per mm."""
    x0, y0, w, h = box
    inks = [Ink(i.points - [x0, y0], i.closed, i.filled, i.pen, dict(i.meta)) for i in sheet.inks
            if ((i.points[:, 0] > x0 - 2) & (i.points[:, 0] < x0 + w + 2)
                & (i.points[:, 1] > y0 - 2) & (i.points[:, 1] < y0 + h + 2)).any()]
    return render_pens(Sheet((w, h), [], inks, {}), px_per_mm=px, grain=False)


def save_score(sheet, path: Path):
    written = synth.played(sheet)["written"]
    path.with_suffix(".recipe.json").write_text(json.dumps(written, indent=1, default=float))
    pl = {k: v for k, v in synth.played(sheet).items() if k != "written"}
    path.with_suffix(".played.json").write_text(json.dumps(pl, indent=1, default=float))


def save_jpg(im, path: Path, max_side=2400, max_kb=390):
    from PIL import Image  # noqa: PLC0415
    path.parent.mkdir(parents=True, exist_ok=True)
    k = min(1.0, max_side / max(im.width, im.height))
    if k < 1:
        im = im.resize((int(im.width * k), int(im.height * k)), Image.Resampling.LANCZOS)
    for q in (88, 84, 80, 76, 72, 68, 64, 60):
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < max_kb * 1024:
            break
    return path


def population(preset="aware", seeds=SEEDS, with_originals=True, title=None, cols=4):
    """Each seed's round-15 original (listen's own weave/yield) directly above the bridge + preset."""
    items, sheets = [], []
    for r0 in range(0, len(seeds), cols):
        row = seeds[r0:r0 + cols]
        if with_originals:
            for sd in row:
                items.append((render_pens(original(sd), px_per_mm=4.0, grain=False), f"{sd} · round 15 (weave/yield)"))
        for sd in row:
            sh = run(sd, preset)
            sheets.append(sh)
            items.append((synth.render(sh, px_per_mm=4.0), caption(sd, sh)))
    im = tile(items, cols, cell=(900, 640), title=title)
    return im, sheets


KEY = {"sympathy": "peak_mm", "hesitate": "peak_mm", "accompany": "hold_mm", "make_room": "push_mm"}


def best_event(sheet, kind, outcome=None):
    key = KEY.get(kind, "peak_mm")
    evs = [e for e in synth.played(sheet)["log"] if e["kind"] == kind and e.get("at")
           and (outcome is None or e["outcome"] == outcome)]
    if outcome == "sympathy" and kind == "crossing":
        key = "lean_mm"
    elif outcome == "stop":
        key = "tail_mm"
    elif evs and outcome is not None:
        return evs[len(evs) // 2]
    if not evs:
        return None
    if kind == "crossing" and outcome is None:
        # the densest varied spot: the event with the most different outcomes within 20 mm
        at = np.array([e["at"] for e in evs])
        best, arg = -1, None
        for e, a in zip(evs, at):
            near = [f["outcome"] for f, b in zip(evs, at) if np.hypot(*(a - b)) < 20]
            sc = len(set(near)) * 10 + len(near)
            if sc > best:
                best, arg = sc, e
        return arg
    return max(evs, key=lambda e: e.get(key, 0) or 0)


def close(seed, kind, preset=None, box_wh=(56.0, 38.0), at=None, px=24.0, outcome=None):
    """[no awareness | with `kind`] at the same place, 4× the sheet's preview scale."""
    preset = preset or kind
    sh = run(seed, preset)
    base = run(seed, "none")
    if at is None:
        e = best_event(sh, kind, outcome)
        at = e["at"] if e else [sh.frame[0] / 2, sh.frame[1] / 2]
    W, H = sh.frame
    w, h = box_wh
    x0 = float(np.clip(at[0] - w / 2, 0, W - w))
    y0 = float(np.clip(at[1] - h / 2, 0, H - h))
    a = crop(base, (x0, y0, w, h), px)
    b = crop(sh, (x0, y0, w, h), px)
    return a, b, sh, (x0, y0, w, h)


def pair(a, b, labels, title=None):
    return tile([(a, labels[0]), (b, labels[1])], 2, cell=(a.width, a.height), title=title)


def _panels(path: Path, sheets):
    """The scores of a multi-panel image, compact: each panel's relations and decisions as written, its
    layers by id / role / pen (their literal lines are listen's for that seed, so the full score is
    `experiments.aware_bridge.score(seed, specs)` with the relations' kinds and params as specs)."""
    panels = []
    for s in sheets:
        w = synth.played(s)["written"]
        dec = {k: v for k, v in w["decisions"].items() if k != "listen_relations"}
        panels.append({"seed": w["seed"], "frame": w["frame"], "relations": w["relations"], "decisions": dec,
                       "layers": [{k: L[k] for k in ("id", "role", "pen", "label")} | {"lines": len(L["lines"]),
                                   "renderer": L.get("renderer")} for L in w["layers"]]})
    doc = {"rebuild": "experiments/aware_bridge.py: score(seed, [{kind, params} for each relation]) "
                      "(named-pair relations of a sheet with a void collapse to one spec per kind)",
           "panels": panels}
    path.with_suffix(".recipe.json").write_text(json.dumps(doc, indent=1, default=float) + "\n")


def _close_rows(rows, title):
    """rows: [(seed, kind, preset, outcome, label)] → one image of [no awareness | with] pairs."""
    items, sheets = [], []
    for seed, kind, preset, outcome, label in rows:
        a, b, sh, box = close(seed, kind, preset, outcome=outcome)
        sheets.append(sh)
        where = f"{seed} at ({box[0]:.0f}, {box[1]:.0f}) mm, {box[2]:.0f}×{box[3]:.0f} mm"
        items += [(a, f"{where} · no awareness"), (b, f"{where} · {label}")]
    return tile(items, 2, cell=(items[0][0].width, items[0][0].height), title=title), sheets


def review():
    """The six review images, into results/ with the scores beside them."""
    # 1. the population: each round-15 original above the same seed through the bridge + crossing + sympathy
    im, sheets = population("aware", title="listen 15101–15108 · each round-15 original (listen's own weave/yield) "
                                         "above the same sheet as a v2 score with crossing + sympathy")
    p = save_jpg(im, RESULTS / "aware-1-population.jpg")
    _panels(p, sheets)
    # 2. the range on the keeper: no awareness / default / pushed hard
    sh = [run(15102, k) for k in ("none", "aware", "hard")]
    items = [(synth.render(s, px_per_mm=5.0), f"15102 · {lab} · {caption(15102, s).split(' · ', 1)[-1]}")
             for s, lab in zip(sh, ("no awareness (lines simply cross)", "crossing + sympathy, defaults",
                                    "pushed hard (too much)"))]
    im = tile(items, 3, cell=(1250, 875), title="15102 · the range of the crossing weights")
    p = save_jpg(im, RESULTS / "aware-2-range-15102.jpg")
    _panels(p, sh)
    # 3. crossing and sympathy, close
    im, sheets = _close_rows([(15102, "crossing", "aware", None, "crossing: under, over, through, stop, bend"),
                              (15106, "crossing", "aware", "stop", "crossing: a stop (one line ends at the other)"),
                              (15102, "sympathy", "sympathy", None, "sympathy alone: lines take on the wiggle they pass")],
                             "crossing and sympathy, 4× the sheet (left: the same place with no awareness)")
    p = save_jpg(im, RESULTS / "aware-3-close-crossing-sympathy.jpg")
    _panels(p, sheets)
    # 4. the three new relations, close
    im, sheets = _close_rows([(15106, "hesitate", "hesitate", None, "hesitate: unsure as it closes in"),
                              (15103, "accompany", "accompany", None, "accompany: holds the distance, lets go"),
                              (15102, "make_room", "make_room", None, "make_room: the earlier line bows away")],
                             "three new awareness relations, 4× the sheet (left: no awareness)")
    p = save_jpg(im, RESULTS / "aware-4-close-new.jpg")
    _panels(p, sheets)
    # 5–6. the strongest sheets: all five relations
    for n, seed in ((5, 15102), (6, 15106)):
        s = run(seed, "all")
        p = RESULTS / f"aware-{n}-{seed}-all.jpg"
        im = synth.render(s, px_per_mm=2400 / s.frame[0])
        save_jpg(im, p)
        save_score(s, p)


def main(argv):
    cmd = argv[0] if argv else "one"
    OUT.mkdir(parents=True, exist_ok=True)
    if cmd == "one":
        seed = int(argv[1]) if len(argv) > 1 else 15102
        preset = argv[2] if len(argv) > 2 else "aware"
        sh = run(seed, preset)
        p = OUT / f"one-{seed}-{preset}.jpg"
        synth.preview(sh, p, label=caption(seed, sh))
        print(p, counts(sh), sh.meta["seconds"])
    elif cmd == "pop":
        preset = argv[1] if len(argv) > 1 else "aware"
        im, sheets = population(preset, title=f"listen 15101–15108: round 15 (top) · bridge + {preset} (bottom)")
        p = save_jpg(im, OUT / f"pop-{preset}.jpg")
        (p.with_suffix(".recipe.json")).write_text(json.dumps(
            {"panels": [synth.played(s)["written"] for s in sheets]}, indent=1, default=float))
        print(p, [counts(s) for s in sheets])
    elif cmd == "close":
        seed, kind = int(argv[1]), argv[2]
        preset = argv[3] if len(argv) > 3 and argv[3] != "-" else None
        outcome = argv[4] if len(argv) > 4 else None
        a, b, sh, box = close(seed, kind, preset, outcome=outcome)
        im = pair(a, b, ["no awareness", f"{kind}"], title=f"{seed} · {kind} · crop {box[2]:.0f}×{box[3]:.0f} mm at 4×")
        p = save_jpg(im, OUT / f"close-{seed}-{kind}{'-' + preset if preset else ''}{'-' + outcome if outcome else ''}.jpg")
        save_score(sh, p)
        print(p, box, counts(sh))
    elif cmd == "review":
        review()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
