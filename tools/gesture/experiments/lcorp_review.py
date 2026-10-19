"""lcorp (round 15, thread B): rebuild the five review images.

Run from the repo root:
    .local/gesture/.venv/bin/python tools/gesture/experiments/lcorp_review.py [1 2 3 4 5]
Writes tools/gesture/results/lcorp-*.jpg, each with <stem>.recipe.json beside it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "tools/gesture")
from PIL import Image, ImageDraw  # noqa: E402

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_oehlen_found as OF  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit.core import PAPER, INK, _font  # noqa: E402

RES = Path("tools/gesture/results")
MAX_PX = 2400


def labelled(im, text, fs=None):
    fs = fs or max(12, im.width // 60)
    strip = Image.new("RGB", (im.width, int(fs * 1.9)), PAPER)
    ImageDraw.Draw(strip).text((int(fs * 0.5), int(fs * 0.4)), text, fill=INK, font=_font(fs))
    out = Image.new("RGB", (im.width, im.height + strip.height), PAPER)
    out.paste(im, (0, 0))
    out.paste(strip, (0, im.height))
    return out


def save(im, stem, recipe):
    if max(im.size) > MAX_PX:
        k = MAX_PX / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)), Image.Resampling.LANCZOS)
    path = RES / f"{stem}.jpg"
    for q in (88, 82, 76, 70, 64):
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < 400_000:
            break
    (RES / f"{stem}.recipe.json").write_text(json.dumps(recipe, indent=1))
    print(path, im.size, path.stat().st_size // 1000, "KB")


# ---------------------------------------------------------------------------
# 1. the zoom across the library
# ---------------------------------------------------------------------------

def zoom_recipe(src: dict, seed=1491, frame=(480, 120)):
    return {"frame": list(frame), "seed": seed, "margin": 6,
            "voice": {"id": "lcorp_zoom", "schedule": "push", "zoom": 24, "reveal": 0.4, **src},
            "renderer": {"id": "lcorp_ink", "pen": 0.45}}


def classify(m):
    inner, con = m["inner"], m["contrast"]
    if inner < 0.065:
        return "balloon"
    if inner > 0.5 or con < 4.0:
        return "flat"
    return "yields"


def image1():
    srcs = [("river", {"source": "river"})] + [(e["id"], {"source": "hand", "hand": e["id"]})
                                               for e in L.entries("hand") if e["policy"] == "generative"]
    rows = []
    for name, src in srcs:
        rec = zoom_recipe(src)
        sh = kit.run(rec)
        meas = sh.marks[0].meta["measure"]
        rows.append((name, rec, meas, classify(meas), sh))
    order = {"yields": 0, "balloon": 1, "flat": 2}
    rows.sort(key=lambda r: (order[r[3]], r[0] != "river", -r[2]["contrast"]))
    ims = [labelled(kit.render_image(sh, px_per_mm=2.6, label=None),
                    f"{name}   {cls}   contrast {m['contrast']}   inner {m['inner']}")
           for name, _, m, cls, sh in rows]
    sheet = kit.contact(ims, 4, title="the zoom on every hand: push, zoom 24, reveal 0.4, constant width 0.45 mm, "
                                      "free course (sorted: yields, balloon, flat)")
    save(sheet, "lcorp-1-zoom-specimen",
         {"panels": [r[1] for r in rows], "class": {r[0]: r[3] for r in rows},
          "measures": {r[0]: r[2] for r in rows}})


# ---------------------------------------------------------------------------
# 2. gradual scaling as composition: the lens
# ---------------------------------------------------------------------------

LENS_HANDS = ["hokusai", "matisse", "dancer_amber", "mime_dragon", "trail_slime"]


def lens_recipe(seed=2201, aware="none"):
    return {"label": "lcorp lens", "frame": [267, 180], "seed": seed, "margin": 10,
            "arranger": {"id": "lcorp_lens", "field": "lens", "far_turn_mm": 0.8, "zoom": 24, "lod": 0.6,
                         "aware": aware},
            "parts": [{"voice": {"id": "lcorp_zoom", "source": "hand", "hand": h}} for h in LENS_HANDS],
            "renderer": {"id": "lcorp_ink", "pen": 0.3}}


def image2():
    rec = lens_recipe()
    sh = kit.run(rec)
    im = OF.render_colour(sh, px_per_mm=8.8)
    save(im, "lcorp-2-lens", sh.recipe | {"score": sh.meta["notes"]["score"]})


# ---------------------------------------------------------------------------
# 3. applied style
# ---------------------------------------------------------------------------

RIVER_COURSE = {"id": "lcorp_zoom", "source": "river", "zoom": 1.0, "river_share": 0.6}
RIVER_OWN = {"id": "lcorp_zoom", "source": "river", "zoom": 1.0, "river_share": 0.12, "river_start": 0.3}
STYLE_ROWS = [
    ("the river's course", RIVER_COURSE, "Hokusai", {"id": "hand", "hand": "hokusai"},
     {"source": "hand", "hand": "hokusai"}),
    ("a dance trail (mantis, right hand, 25 s)", {"id": "dance", "trail": "mantis", "effectors": "rhand",
                                                  "cut": "none", "seconds": 25.0},
     "the river", RIVER_OWN, {"source": "river"}),
    ("a Hokusai line", {"id": "hand", "hand": "hokusai"}, "the river", RIVER_OWN, {"source": "river"}),
    ("the river's course", RIVER_COURSE, "Lichtenberg", {"id": "hand", "hand": "lichtenberg"},
     {"source": "hand", "hand": "lichtenberg"}),
]


def image3():
    ims, recs = [], []
    for cname, course, sname, own, style in STYLE_ROWS:
        base = {"frame": [220, 110], "seed": 4101, "margin": 6, "renderer": {"id": "lcorp_ink", "pen": 0.3}}
        r_course = base | {"voice": course}
        r_own = base | {"voice": own}
        r_app = base | {"voice": course, "modulators": [{"id": "lcorp_style", "split_mm": 12.0,
                                                          "style_turn_mm": 2.2, **style}]}
        for r, lab in ((r_course, cname), (r_own, f"{sname}, its own line"),
                       (r_app, f"{cname} in {sname}'s bends")):
            sh = kit.run(r)
            # the applied line is longer than its course: refit it into the panel
            ims.append(labelled(kit.render_image(_refit(sh), px_per_mm=3.4, label=None), lab))
            recs.append(sh.recipe)
    sheet = kit.contact(ims, 3, title="applied style: course (left), the style's own line (middle), the course "
                                      "drawn in the style's bends (right); split 12 mm, constant width")
    save(sheet, "lcorp-3-style", {"panels": recs})


def _refit(sh):
    import numpy as np  # noqa: PLC0415

    from gesture.kit.core import Ink, Sheet  # noqa: PLC0415
    from gesture.kit.voices_rzoom import shrink_fit  # noqa: PLC0415
    W, H = sh.frame
    allp = np.vstack([i.points for i in sh.inks])
    _, k, off = shrink_fit(allp, (6, 6, W - 12, H - 12), grow=True)
    return Sheet(frame=sh.frame, marks=[], inks=[Ink(i.points * k + off, closed=False, filled=False, pen=i.pen,
                                                     meta=dict(i.meta)) for i in sh.inks], meta=sh.meta)


# ---------------------------------------------------------------------------
# 4. aware overlaps, close up (the round-14 piece at constant width)
# ---------------------------------------------------------------------------

CROPS = [(15, 180, 125, 260), (55, 105, 140, 175)]


def image4():
    r0 = json.loads((RES / "rzoom-1-piece.recipe.json").read_text())
    r0["renderer"] = {"id": "lcorp_ink", "pen": 0.3}
    recs, ims = [], []
    for crop in CROPS:
        for mode in (None, "depth", "sympathy"):
            r = json.loads(json.dumps(r0))
            if mode:
                r["parts"][0]["modulators"] = [{"id": "lcorp_aware", "mode": mode, "gap": 1.0, "reach": 5.0,
                                                "gain": 1.5}]
            sh = kit.run(r)
            lab = {None: "as round 14 (constant width)", "depth": "depth: the nearer pass cuts the farther",
                   "sympathy": "sympathy: the near pass takes on the far twist it runs over"}[mode]
            ims.append(labelled(OF.render_colour(sh, px_per_mm=7.0, crop=crop), lab))
            recs.append({"recipe": sh.recipe, "crop_mm": list(crop)})
    sheet = kit.contact(ims, 3, title="rzoom-1 close up: aware overlaps (lcorp_aware); crops in mm of the 190 x 270 "
                                      "sheet")
    save(sheet, "lcorp-4-aware", {"panels": recs})


# ---------------------------------------------------------------------------
# 5. free choice: relays, hands passing into one another at the pinches
# ---------------------------------------------------------------------------

RELAY = ["matisse", "lichtenberg", "dancer_cristel", "trail_slime"]


def image5():
    ims, recs, scores = [], [], []
    for seed in (3001, 3002, 3003):
        rec = {"frame": [600, 150], "seed": seed, "margin": 8,
               "voice": {"id": "lcorp_zoom", "source": "relay", "hands": RELAY, "schedule": "pinch", "zoom": 24,
                         "drawn_mm": 1800},
               "renderer": {"id": "lcorp_ink", "by": "voice", "inks": "black,blue,red,green"}}
        sh = kit.run(rec)
        ims.append(labelled(OF.render_colour(sh, px_per_mm=3.6), f"seed {seed}", fs=22))
        recs.append(sh.recipe)
        scores.append(sh.meta["notes"]["score"])
    sheet = kit.contact(ims, 1, title="relay: matisse > lichtenberg > dancer_cristel > trail_slime "
                                      "(black, blue, red, green)")
    save(sheet, "lcorp-5-relay", {"panels": recs, "scores": scores})


if __name__ == "__main__":
    which = sys.argv[1:] or ["1", "2", "3", "4", "5"]
    for w in which:
        globals()[f"image{w}"]()
