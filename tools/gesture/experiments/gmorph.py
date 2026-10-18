"""Round 13, thread II-a (gmorph): one hand's grammar morphed continuously.

Run from the repo root:  .local/gesture/.venv/bin/python tools/gesture/experiments/gmorph.py <stage>
Scratch output: .local/gesture/out/gmorph/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "tools/gesture")

import numpy as np  # noqa: E402

from gesture import kit  # noqa: E402

OUT = Path(".local/gesture/out/gmorph")

# Route 2, five types of one hand with overlapping dials:
#   A calm long bends -> B tight meander -> C sawtooth (meander bends turn into corners, still alternating)
#   -> D angular walk (alternation let go) -> E loops (corners gone, coiling).
ROUTE2 = {
    "span":    [0, .85, .08, .85, .14, .5, .34, .5, .42, .3, .58, .3, .66, .5],
    "turn":    [0, .25, .08, .25, .14, .95, .34, .95, .42, .1, .64, .1, .74, .85],
    "corners": [0, 0, .34, 0, .42, 5, .62, 4, .72, 0],
    "sharp":   [.46, .2, .54, .2, .60, .75],
    "sign":    [0, 0, .08, 0, .14, 1, .48, 1, .56, 0, .66, 0, .74, -.95],
    "gain":    [0, 1, .08, 1, .16, 1.5, .34, 1.5, .44, 1],
    "pull":    [0, .25, .66, .25, .76, .16],
}
# Route 3: D becomes an angular coil (corners still on, the side rule turned to coiling), the bridge
# from the sawtooth to round loops: A calm -> B hairpin meander -> C sawtooth -> D angular coil -> E loops.
ROUTE3 = {
    "span":    [0, .85, .08, .85, .14, .5, .34, .5, .42, .3, .52, .3, .60, .6, .72, .6, .80, .5],
    "turn":    [0, .45, .08, .45, .14, .95, .34, .95, .42, .1, .68, .1, .78, .85],
    "corners": [0, 0, .34, 0, .42, 5, .66, 4, .78, 0],
    "sharp":   [.48, .2, .56, .2, .62, .55],
    "sign":    [0, 0, .08, 0, .14, 1, .50, 1, .60, -.9, 1, -.95],
    "gain":    [0, 1, .08, 1, .16, 1.5, .34, 1.5, .44, 1],
    "pull":    [0, .15, .08, .15, .14, .25, .60, .25, .70, .16],
}
ROUTE1 = ROUTE2


def recipe(hand, sched, *, seed, frame=(400, 70), length=14.0, **kw):
    v = {"id": "gmorph", "hand": hand, "length": length, **sched, **kw}
    return {"label": f"gmorph {hand}", "frame": list(frame), "seed": seed, "voice": v,
            "renderer": {"id": "wire", "pen": 0.45}}


def crops(path, n=3):
    from PIL import Image
    im = Image.open(path)
    w = im.width // n
    for i in range(n):
        im.crop((i * w, 0, (i + 1) * w, im.height)).save(path.with_name(path.stem + f"-c{i}.jpg"), quality=85)


def stage_try():
    ims = []
    for hand in sys.argv[2:] or ["river_belt"]:
        for seed, sched in [(sd, ROUTE3) for sd in range(13101, 13109)]:
            sh = kit.run(recipe(hand, sched, seed=seed))
            name = f"try-{hand}-{seed}"
            kit.preview(sh, OUT / f"{name}.jpg", px_per_mm=8)
            log = sh.marks[0].meta["gmorph"]["log"]
            from gesture.kit.voices_gmorph import measure
            print(name, "len_R", round(sh.marks[0].meta["gmorph"]["length_R"], 2))
            for i, m in enumerate(measure(log, 8)):
                print("  ", i, {k: round(v, 3) for k, v in m.items()})
            ims.append(kit.render_image(sh, px_per_mm=5, label=name))
    kit.contact(ims, 1).save(OUT / "try-contact.jpg", quality=85)


def stage_close():
    """The piece at 3x, cut into three rows that overlap by 6 mm, so the transitions can be read."""
    from PIL import Image, ImageDraw
    from gesture.kit.core import _font

    sh = kit.run(piece_recipe())
    k = 15.0
    big = kit.render_image(sh, px_per_mm=k, label=None)
    P_ = sh.marks[0].points
    x0, x1 = float(P_[:, 0].min()) - 2, float(P_[:, 0].max()) + 2
    cuts = np.linspace(x0, x1, 4)
    f = _font(26)
    rows = []
    names = ["A long calm bends, B hairpin meander begins", "B meander gets teeth, C sawtooth",
             "C sawtooth, D angular coil, E loops"]
    for i in range(3):
        a, b = cuts[i] - 3, cuts[i + 1] + 3
        sel = (P_[:, 0] >= a) & (P_[:, 0] <= b)
        ya, yb = float(P_[sel, 1].min()) - 3, float(P_[sel, 1].max()) + 3
        crop = big.crop((int(a * k), int(ya * k), int(b * k), int(yb * k)))
        row = Image.new("RGB", (crop.width, crop.height + 40), FLEX["paper"])
        row.paste(crop, (0, 0))
        ImageDraw.Draw(row).text((14, crop.height + 4), f"{i + 1}/3  x {a:.0f}-{b:.0f} mm  ·  {names[i]}",
                                 fill=FLEX["tx2"], font=f)
        rows.append(row)
    W = max(r.width for r in rows)
    H = sum(r.height for r in rows) + 12 * 4 + 50
    im = Image.new("RGB", (W + 24, H), FLEX["paper"])
    dr = ImageDraw.Draw(im)
    dr.text((12, 10), f"gmorph close-up — the piece at 3x ({k:.0f} px/mm), read in three rows", fill=FLEX["ink"],
            font=_font(30))
    y = 56
    for r in rows:
        im.paste(r, (12, y))
        dr.rectangle([11, y - 1, 12 + r.width, y + r.height], outline=FLEX["ui"])
        y += r.height + 12
    if im.width > 2400 or im.height > 2400:
        sc = 2400 / max(im.width, im.height)
        im = im.resize((int(im.width * sc), int(im.height * sc)), Image.Resampling.LANCZOS)
    save_jpg(im, OUT / "gmorph-close.jpg", sh.recipe)


def stage_hands():
    from gesture.kit.voices_gmorph import measure
    ims = []
    for hand in sys.argv[2:]:
        sh = kit.run(recipe(hand, ROUTE3, seed=13103))
        name = f"hands-{hand}"
        kit.preview(sh, OUT / f"{name}.jpg", px_per_mm=8)
        m = measure(sh.marks[0].meta["gmorph"]["log"], 8)
        print(name, [round(r["corners_per_R"], 1) for r in m], [round(r["turn"], 2) for r in m])
        ims.append(kit.render_image(sh, px_per_mm=5, label=hand))
    kit.contact(ims, 1).save(OUT / "hands-contact.jpg", quality=85)


# ---------------------------------------------------------------------------
# review images
# ---------------------------------------------------------------------------

RES = Path("tools/gesture/results")
PIECE_SEED = 13102
FRAME = (460, 70)          # a scroll strip: five types of one hand, read left to right, ~90 mm each
MARGIN = 10.0
# where each type sits (u = share of the line's length) and its name
TYPES = [(0.04, "A", "long calm bends"), (0.24, "B", "hairpin meander"), (0.47, "C", "sawtooth"),
         (0.67, "D", "angular coil"), (0.89, "E", "loops")]
DIAL_ORDER = ["span", "turn", "corners", "sharp", "sign", "gain", "pull"]
DIAL_TEXT = {"span": "span: which of its segment lengths (0 shortest, 1 longest)",
             "turn": "turn: which of its bends (0 calmest, 1 tightest)",
             "corners": "corners: weight of its corner tokens (1 = its own share)",
             "sharp": "sharp: which of its corners (0 blunt, 1 hairpin)",
             "sign": "sign: +1 each turn against the last (zigzag), -1 the same way (coil)",
             "gain": "gain on its curvature",
             "pull": "pull back to the valley axis (per mm)"}
FLEX = {"paper": (0xFF, 0xFC, 0xF0), "ink": (0x10, 0x0F, 0x0F), "ui": (0xE6, 0xE4, 0xD9),
        "tx2": (0x6F, 0x6E, 0x69), "tx3": (0xB7, 0xB5, 0xAC),
        "red": (0xAF, 0x30, 0x29), "orange": (0xBC, 0x52, 0x15), "yellow": (0xAD, 0x83, 0x01),
        "green": (0x66, 0x80, 0x0B), "cyan": (0x24, 0x83, 0x7B), "blue": (0x20, 0x5E, 0xA6),
        "purple": (0x5E, 0x40, 0x9D), "magenta": (0xA0, 0x2F, 0x6F)}
DIAL_COL = {"span": "blue", "turn": "red", "corners": "orange", "sharp": "yellow", "sign": "purple",
            "gain": "magenta", "pull": "cyan"}
PX = 5.0


def piece_recipe(hand="river_belt", sched=None, seed=PIECE_SEED, label=None):
    r = recipe(hand, ROUTE3 if sched is None else sched, seed=seed, frame=FRAME)
    r["margin"] = MARGIN
    r["label"] = label or f"gmorph piece: {hand}, five types of one hand"
    return r


def save_jpg(im, path, recipes):
    path = Path(path)
    q = 90
    while True:
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < 390_000 or q <= 50:
            break
        q -= 5
    path.with_suffix(".recipe.json").write_text(json.dumps(recipes, indent=1, default=float))
    print(path, im.size, path.stat().st_size // 1000, "KB q", q)


def stage_piece():
    sh = kit.run(piece_recipe())
    im = kit.render_image(sh, px_per_mm=PX, label=f"gmorph — one hand (river_belt), its grammar morphed "
                          f"along the line: long calm bends, then hairpin meander, sawtooth, angular coil, loops"
                          f"   ·   {FRAME[0]} × {FRAME[1]} mm, seed {PIECE_SEED}")
    OUT.mkdir(parents=True, exist_ok=True)
    save_jpg(im, OUT / "gmorph-piece.jpg", sh.recipe)


def _x_of_u(sh):
    """Monotone map u -> x (px) along the drawn line, for aligning lanes under it."""
    m = sh.marks[0]
    u = np.asarray(m.channels["u"])
    x = np.maximum.accumulate(m.points[:, 0])
    grid = np.linspace(0, 1, 401)
    return grid, np.interp(grid, u, x) * PX


def stage_schedule():
    from PIL import Image, ImageDraw
    from gesture.kit.core import _font
    from gesture.kit.voices_gmorph import measure, schedule

    sh = kit.run(piece_recipe())
    line = kit.render_image(sh, px_per_mm=PX, label=None)
    W = line.width
    grid, gx = _x_of_u(sh)
    sched = sh.marks[0].meta["gmorph"]["schedules"]
    log = sh.marks[0].meta["gmorph"]["log"]
    f_s, f_m = _font(17), _font(21)
    lane_h, lane_gap, top = 66, 10, 62
    meas = measure(log, 40)
    mrows = [("corners_per_R", "measured: corners per R", 0, None),
             ("turn", "measured: median turning per bend (rad)", 0, None),
             ("zigzag", "measured: share of turns (bends and corners) against the last", 0, 1)]
    H = top + line.height + 30 + (len(DIAL_ORDER) + len(mrows)) * (lane_h + lane_gap) + 80
    im = Image.new("RGB", (W, H), FLEX["paper"])
    dr = ImageDraw.Draw(im)
    dr.text((16, 14), "gmorph schedule — which dial of the hand moves where (x = position along the line; "
            "every dial on its own knots, cosine-eased)", fill=FLEX["ink"], font=f_m)
    im.paste(line, (0, top))
    y_line_bot = top + line.height
    # type labels and guides
    for u, k, name in TYPES:
        x = float(np.interp(u, grid, gx))
        dr.text((x - 6, top + 4), f"{k}  {name}", fill=FLEX["ink"], font=f_m)
    y = y_line_bot + 30
    lanes_top = y

    def lane_box(y0):
        dr.rectangle([0, y0, W - 1, y0 + lane_h], fill=(0xF2, 0xF0, 0xE5))

    for name in DIAL_ORDER:
        lane_box(y)
        kn = sched.get(name)
        default = {"corners": 1.0, "sign": 0.0, "gain": 1.0, "pull": 0.12}.get(name)
        vals = schedule(kn, grid, default)
        lo, hi = {"span": (0, 1), "turn": (0, 1), "sharp": (0, 1), "sign": (-1, 1), "corners": (0, 5.2),
                  "gain": (0.9, 1.6), "pull": (0, 0.3)}[name]
        col = FLEX[DIAL_COL[name]]
        if vals is None:
            dr.text((12, y + 4), DIAL_TEXT[name] + " — not moved (the hand's own)", fill=FLEX["tx2"], font=f_s)
        else:
            if name == "sign":
                y0 = y + lane_h * 0.5
                dr.line([(0, y0), (W, y0)], fill=FLEX["tx3"], width=1)
            pts = [(float(x), y + lane_h - 6 - (lane_h - 30) * (float(v) - lo) / (hi - lo)) for x, v in zip(gx, vals)]
            dr.line(pts, fill=col, width=4, joint="curve")
            if kn:
                k = np.asarray(kn, float).reshape(-1, 2)
                for uk, vk in k:
                    xk = float(np.interp(uk, grid, gx))
                    yk = y + lane_h - 6 - (lane_h - 30) * (vk - lo) / (hi - lo)
                    dr.ellipse([xk - 5, yk - 5, xk + 5, yk + 5], outline=col, width=2, fill=FLEX["paper"])
            dr.text((12, y + 3), DIAL_TEXT[name], fill=col, font=f_s)
        y += lane_h + lane_gap
    # measured lanes
    xs = [float(np.interp((i + 0.5) / len(meas), grid, gx)) for i in range(len(meas))]
    bw = W / len(meas) * 0.6
    for key, text, lo, hi in mrows:
        lane_box(y)
        v = np.array([m[key] for m in meas], float)
        hi_ = hi if hi is not None else float(np.nanmax(v)) * 1.05 + 1e-9
        for x, val in zip(xs, v):
            if not np.isfinite(val):
                continue
            hgt = (lane_h - 28) * (val - lo) / (hi_ - lo)
            dr.rectangle([x - bw / 2, y + lane_h - 4 - hgt, x + bw / 2, y + lane_h - 4], fill=FLEX["tx2"])
        dr.text((12, y + 3), text, fill=FLEX["ink"], font=f_s)
        y += lane_h + lane_gap
    # type guides across the lanes
    for u, k, _ in TYPES:
        x = float(np.interp(u, grid, gx))
        dr.text((x - 6, y + 2), k, fill=FLEX["ink"], font=f_m)
        for yy in range(lanes_top - 18, y, 10):
            dr.line([(x, yy), (x, yy + 4)], fill=FLEX["tx3"], width=1)
    dr.text((12, y + 36), f"river_belt · seed {PIECE_SEED} · knots are the circles; lanes below are "
            "measured from the drawn tokens", fill=FLEX["tx2"], font=f_s)
    save_jpg(im, OUT / "gmorph-schedule.jpg", sh.recipe)


def stage_close():
    """The piece at 3x, cut into three rows that overlap by 6 mm, so the transitions can be read."""
    from PIL import Image, ImageDraw
    from gesture.kit.core import _font

    sh = kit.run(piece_recipe())
    k = 15.0
    big = kit.render_image(sh, px_per_mm=k, label=None)
    P_ = sh.marks[0].points
    x0, x1 = float(P_[:, 0].min()) - 2, float(P_[:, 0].max()) + 2
    cuts = np.linspace(x0, x1, 4)
    f = _font(26)
    rows = []
    names = ["A long calm bends, B hairpin meander begins", "B meander gets teeth, C sawtooth",
             "C sawtooth, D angular coil, E loops"]
    for i in range(3):
        a, b = cuts[i] - 3, cuts[i + 1] + 3
        sel = (P_[:, 0] >= a) & (P_[:, 0] <= b)
        ya, yb = float(P_[sel, 1].min()) - 3, float(P_[sel, 1].max()) + 3
        crop = big.crop((int(a * k), int(ya * k), int(b * k), int(yb * k)))
        row = Image.new("RGB", (crop.width, crop.height + 40), FLEX["paper"])
        row.paste(crop, (0, 0))
        ImageDraw.Draw(row).text((14, crop.height + 4), f"{i + 1}/3  x {a:.0f}-{b:.0f} mm  ·  {names[i]}",
                                 fill=FLEX["tx2"], font=f)
        rows.append(row)
    W = max(r.width for r in rows)
    H = sum(r.height for r in rows) + 12 * 4 + 50
    im = Image.new("RGB", (W + 24, H), FLEX["paper"])
    dr = ImageDraw.Draw(im)
    dr.text((12, 10), f"gmorph close-up — the piece at 3x ({k:.0f} px/mm), read in three rows", fill=FLEX["ink"],
            font=_font(30))
    y = 56
    for r in rows:
        im.paste(r, (12, y))
        dr.rectangle([11, y - 1, 12 + r.width, y + r.height], outline=FLEX["ui"])
        y += r.height + 12
    if im.width > 2400 or im.height > 2400:
        sc = 2400 / max(im.width, im.height)
        im = im.resize((int(im.width * sc), int(im.height * sc)), Image.Resampling.LANCZOS)
    save_jpg(im, OUT / "gmorph-close.jpg", sh.recipe)


def stage_hands():
    rows, recs = [], []
    for hand, seed in [(h.split(":")[0], int(h.split(":")[1]) if ":" in h else PIECE_SEED) for h in sys.argv[2:]]:
        sh = kit.run(piece_recipe(hand, seed=seed, label=f"gmorph {hand}"))
        rows.append(kit.render_image(sh, px_per_mm=PX, label=f"{hand} · seed {seed} · the same schedule"))
        recs.append(sh.recipe)
    im = kit.contact(rows, 1, title="gmorph — the same schedule given to other hands: each type comes out "
                     "in that hand's own vocabulary", gap=10)
    save_jpg(im, OUT / "gmorph-hands.jpg", {"rows": recs})


def stage_dud():
    rows, recs = [], []
    one = {"turn": [0, .1, 1, .95]}
    sh = kit.run(piece_recipe("river_belt", sched=one, label="dud: one dial"))
    rows.append(kit.render_image(sh, px_per_mm=PX, label="dud 1 — one dial alone (turn 0.1 to 0.95, one steady "
                                 "ramp), the rest the hand's own: its usual mix, curlier toward the end; no sequence of types"))
    recs.append(sh.recipe)
    r = {"label": "dud: belt gain ramp", "frame": list(FRAME), "seed": PIECE_SEED, "margin": MARGIN,
         "voice": {"id": "belt", "hand": "river_belt", "length": 12.0, "gain": 1.0, "gain_end": 2.6},
         "renderer": {"id": "wire", "pen": 0.45}}
    sh = kit.run(r)
    rows.append(kit.render_image(sh, px_per_mm=PX, label="dud 2 — the morphing_belt study's one ramp "
                                 "(gain 1.0 to 2.6): the bends tighten, the type stays the same"))
    recs.append(sh.recipe)
    im = kit.contact(rows, 1, title="the slider failure, for comparison with the piece", gap=10)
    save_jpg(im, OUT / "gmorph-dud.jpg", {"rows": recs})


if __name__ == "__main__":
    globals()["stage_" + sys.argv[1]]()
