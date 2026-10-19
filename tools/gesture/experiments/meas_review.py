"""Thread D (`meas`, round 15): the five review images, each with its spec
(the drawing's full recipe + the device specs) beside it.

    .local/gesture/.venv/bin/python tools/gesture/experiments/meas_review.py [1 2 3 4 5]
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import meas_common as C  # noqa: E402

from gesture.kit._devices import _DEVICES, apply_devices  # noqa: E402

RES = C.RESULTS

CATALOGUE = [
    ("meas_stations", [{"id": "meas_stations", "place": "beside", "side": "bottom", "size": 30}]),
    ("meas_roll", [{"id": "meas_roll", "place": "beside", "side": "bottom", "size": 44}]),
    ("meas_inventory", [{"id": "meas_inventory", "place": "beside", "side": "right", "size": 70, "by": "line"}]),
    ("meas_air", [{"id": "meas_air", "place": "over", "level": "line"}]),
    ("meas_arcs", [{"id": "meas_arcs", "place": "beside", "side": "right", "size": 60, "ink": "source"},
                   {"id": "meas_arcs", "place": "over", "ink": "source"}]),
    ("meas_ledger", [{"id": "meas_ledger", "place": "beside", "side": "right", "size": 120, "by": "line",
                      "index": True}]),
    ("meas_turning", [{"id": "meas_turning", "place": "beside", "side": "bottom", "size": 60, "name": 4}]),
    # the general family (Codex, devices_measg*.py), laid on the same drawing
    ("scale_ruler", [{"id": "scale_ruler", "place": "margin", "side": "bottom", "size": 18}]),
    ("arc_ticks", [{"id": "arc_ticks", "place": "over"}]),
    ("density_isoline", [{"id": "density_isoline", "place": "under"}]),
    ("heading_rose", [{"id": "heading_rose", "place": "beside", "side": "right", "size": 60}]),
    ("misfit_grid", [{"id": "misfit_grid", "place": "under"}]),
    ("survey_marks", [{"id": "survey_marks", "place": "over"}]),
]


def _round14(name: str, *, constant_width: bool = False):
    rec = json.loads((RES / f"{name}.recipe.json").read_text())
    if "panels" in rec:
        rec = rec["panels"][0]
    if constant_width and rec.get("renderer", {}).get("id") == "rzoom_ink":
        rec = copy.deepcopy(rec)
        rec["renderer"]["pens"] = [0.35] * len(rec["renderer"]["pens"])   # Ian: constant width
    return C.kit.run(rec), f"tools/gesture/results/{name}.recipe.json"


def _spec(path, sheet, devices, *, source=None, note=""):
    C.save_spec(path, {"note": note, "drawing_source": source, "drawing": sheet.recipe, "devices": devices})


def _fit(im, size):
    """Scale a cell image to fit size (aspect kept), on paper, top-centred."""
    from PIL import Image  # noqa: PLC0415
    k = min(size[0] / im.width, size[1] / im.height)
    im = im.resize((max(int(im.width * k), 1), max(int(im.height * k), 1)), Image.Resampling.LANCZOS)
    return _pad(im, size)


def _pad(im, size):
    from PIL import Image  # noqa: PLC0415
    out = Image.new("RGB", size, C.PAPER)
    out.paste(im, ((size[0] - im.width) // 2, 0))
    return out


def img1():
    from PIL import Image  # noqa: PLC0415
    sh = C.kit.run(C.catalogue_recipe(15310))
    cells = [C.caption(C.render(sh, px_per_mm=3.2), "the drawing: river_zoom push, a drift, a dance, a fly")]
    used = []
    for name, specs in CATALOGUE:
        if specs[0]["id"] not in _DEVICES:
            continue
        out = apply_devices(sh, specs)
        fam = _DEVICES[specs[0]["id"]].family
        places = "+".join(s["place"] for s in specs)
        cells.append(C.caption(C.render(out, px_per_mm=3.2), f"{name}  ({fam}, {places})"))
        used.append({"cell": name, "family": fam, "specs": specs})
    cw, ch = 760, 520
    cells = [_fit(c, (cw, ch)) for c in cells]
    cols = 3
    rows = -(-len(cells) // cols)
    gap = 18
    sheet = Image.new("RGB", (cols * cw + (cols + 1) * gap, rows * ch + (rows + 1) * gap), C.PAPER)
    for i, c in enumerate(cells):
        r, k = divmod(i, cols)
        sheet.paste(_pad(c, (cw, ch)), (gap + k * (cw + gap), gap + r * (ch + gap)))
    path = RES / "meas-1-catalogue.jpg"
    C.save_budget(sheet, path)
    _spec(path, sh, used, note="every device on the same drawing; first row onwards: process family (meas_*), "
          "then the general family (devices_measg*.py)")
    return path


def img2():
    sh, src = _round14("rzoom-4-ornament", constant_width=True)
    dev = [{"id": "meas_stations", "place": "beside", "side": "bottom", "size": 40, "stations": 32,
            "label_every": 4, "tick": 1.8, "label_h": 2.6, "pen": 0.2, "ink": "black"}]
    out = apply_devices(sh, dev)
    im = C.caption(C.render(out, px_per_mm=3.6), "river_zoom push (free course, constant width) and its own km: "
                   "stations every 20 km of river, ticked on the line and on the line laid straight below")
    path = RES / "meas-2-river-km.jpg"
    C.save_budget(im, path)
    _spec(path, sh, dev, source=src + " (panel 0, pens made constant)")
    return path


def img3():
    sh, src = _round14("cimpro-4-sheet-14007")
    dev = [{"id": "meas_air", "place": "over", "level": "step", "ink": "red", "pen": 0.13, "label_h": 1.6},
           {"id": "meas_inventory", "place": "beside", "side": "right", "size": 120, "by": "step", "name": "both",
            "index": False}]
    out = apply_devices(sh, dev)
    im = C.caption(C.render(out, px_per_mm=4.2), "cimpro 14007 taken apart into its 19 steps (one scale, drawing "
                   "order, verb + hand); red: the pen's flight between steps, landing numbered as the plate")
    path = RES / "meas-3-14007-inventory-air.jpg"
    C.save_budget(im, path)
    _spec(path, sh, dev, source=src)
    return path


def img4():
    sh = C.kit.run(C.quartet_recipe(15500))
    dev = [{"id": "meas_turning", "place": "beside", "side": "bottom", "size": 64, "name": 4, "label_h": 2.0}]
    out = apply_devices(sh, dev)
    im = C.caption(C.render(out, px_per_mm=4.5), "four hands (oxbow, leaf miner, fly, mantis) and how each turns: "
                   "accumulated whole turns against arc length, from one origin (the κ chart, another version)")
    path = RES / "meas-4-quartet-turning.jpg"
    C.save_budget(im, path)
    _spec(path, sh, dev, note="quartet seed 15500 (first of 15500-15503)")
    return path


def img5():
    from PIL import Image  # noqa: PLC0415
    a, sa = _round14("ccolour-3-4507")
    da = [{"id": "meas_ledger", "place": "beside", "side": "right", "size": 105, "index": True, "bars": "source"},
          {"id": "meas_air", "place": "over", "level": "step", "ink": "red", "pen": 0.12, "number_every": 0,
           "ring": 0.0}]
    b, sb = _round14("cimpro-4-sheet-14007")
    db = [{"id": "meas_arcs", "place": "beside", "side": "bottom", "size": 46},
          {"id": "meas_arcs", "place": "over", "ink": "red", "kinds": "cross,cover,counterweight"}]
    ia = C.caption(C.render(apply_devices(a, da), px_per_mm=4.0),
                   "ccolour 4507 + its ledger (Matisse rules; rows ringed where each object starts) + the pen's flight")
    ib = C.caption(C.render(apply_devices(b, db), px_per_mm=3.2),
                   "cimpro 14007 + the relations its own log records (arcs) and where they happened")
    H = max(ia.height, ib.height)
    sheet = Image.new("RGB", (ia.width + ib.width + 30, H), C.PAPER)
    sheet.paste(ia, (0, 0))
    sheet.paste(ib, (ia.width + 30, 0))
    path = RES / "meas-5-layers-4507-14007.jpg"
    C.save_budget(sheet, path)
    C.save_spec(path, {"panels": [{"drawing_source": sa, "drawing": a.recipe, "devices": da},
                                  {"drawing_source": sb, "drawing": b.recipe, "devices": db}]})
    return path


if __name__ == "__main__":
    which = sys.argv[1:] or ["1", "2", "3", "4", "5"]
    for w in which:
        print(globals()[f"img{w}"]())
