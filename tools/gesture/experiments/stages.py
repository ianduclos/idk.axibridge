"""Round 13, thread II-d (prefix `stages`): a morph across a series, caused by events.

    .local/gesture/.venv/bin/python tools/gesture/experiments/stages.py try NAME [seed]
    .local/gesture/.venv/bin/python tools/gesture/experiments/stages.py review

Recipes live in RECIPES; every build writes the row image, a debug image
(events marked), row.recipe.json and sheet-k.recipe.json under
.local/gesture/out/stages/<name>/.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/gesture"))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_series as S  # noqa: E402
from gesture.kit import arrangers_stages as ST  # noqa: E402

OUT = ROOT / ".local/gesture/out/stages"
RES = ROOT / "tools/gesture/results"

SW, SH = 148.0, 210.0          # A5 portrait


def river(box_angle=-8.0, span_w=1400, start=0.18):
    return {"voice": {"id": "oehlen_found_river", "tile": "SB19", "rank": 0, "start": start, "span_w": span_w,
                      "angle": box_angle},
            "renderer": {"id": "stages_layer", "pen": 0.3}, "label": "found: far river"}


def voice_layer(hand, length=1.4, label="another voice"):
    return {"voice": {"id": "hand", "hand": hand, "length": length},
            "renderer": {"id": "stages_layer", "pen": 0.35}, "label": label}


def line(**kw):
    v = {"id": "stages_line"}
    v.update(kw)
    return {"voice": v, "renderer": {"id": "stages_ink", "pen": 0.35}, "label": "the line"}


def base(seed: int, sheets: int, parts, boxes, effects, inks, label):
    return {"frame": [SW * sheets, SH], "seed": seed, "margin": 0.0,
            "arranger": {"id": "stages_row", "sheets": sheets, "boxes": boxes, "effects": effects, "inks": inks},
            "parts": parts, "renderer": {"id": "wire", "pen": 0.35}, "label": label}


ROUTE_A = [0.25, 0.25,
           0.55, 0.4,
           0.75, 0.62,
           1.3, 0.68,
           1.6, 0.45,
           1.92, 0.35,
           2.25, 0.5,
           2.6, 0.42,
           2.9, 0.5,
           3.25, 0.45,
           3.58, 0.3,
           3.75, 0.52,
           3.5, 0.7,
           3.3, 0.52,
           3.62, 0.42,
           4.15, 0.45,
           4.5, 0.22,
           4.6, 0.08]


def r_main(seed=5316, red_box=(2.08, 0.08, 0.84, 0.84), river_box=(0.55, 0.56, 1.0, 0.2), **over):
    """wire → river zigzag → nib → beads → dry: river (ride) → red voice (crossings) → own past (pools) → ink."""
    lp = dict(hand="ingres", length=6000.0, route=ROUTE_A, read_box=[0.0, 0.0, 280.0, 400.0], pull=0.07,
              reach=20.0, ride_mm=55.0, tau=150.0, p_max=0.92, dW=0.55, W_max=2.6, ink=1700.0,
              pool_gap=10.0)
    lp.update(over)
    parts = [line(**lp), river(), voice_layer("hokusai", 0.6)]
    boxes = [*river_box, *red_box]
    return base(seed, 5, parts, boxes, "grammar,nib", "black,blue,red", "stages: wire -> river -> nib -> beads -> dry")


def r_missed(seed=5316, **over):
    """counterfactual: the same line, the red voice moved (same shape, smaller, lower) so the line never meets it."""
    rec = r_main(seed, red_box=(2.15, 0.6, 0.7, 0.36), **over)
    rec["label"] = "stages, counterfactual: the red voice moved; the line never meets it"
    return rec


def r_control(seed=5316, **over):
    """the CONTROL (dud): the same effects keyed to the sheet edges, whatever the line meets."""
    rec = r_main(seed, **over)
    rec["arranger"]["cause"] = "edges"
    rec["label"] = "stages, control: the same changes at the sheet edges (cause = sheet index)"
    return rec


ROUTE_H = [0.25, 0.3,
           0.6, 0.5,
           1.0, 0.45,
           1.35, 0.3,
           1.6, 0.6,
           1.9, 0.5,
           2.3, 0.35,
           2.7, 0.55,
           3.1, 0.45,
           3.45, 0.62,
           3.7, 0.4,
           4.1, 0.5,
           4.5, 0.3,
           4.7, 0.12]


def r_hands(seed=5331, **over):
    """variant route: one hand turning into another, and that one into a third, by crossings."""
    lp = dict(hand="ingres", length=6000.0, route=ROUTE_H, read_box=[0.0, 0.0, 280.0, 400.0], pull=0.07,
              reach=20.0, tau=120.0, p_max=0.9, dW=0.0, W_max=0.35, ink=1e5, cross_gap=10.0)
    lp.update(over)
    parts = [line(**lp), voice_layer("mime_mantis", 0.7, "voice: mantis"), voice_layer("fly_open", 0.6, "voice: fly")]
    boxes = [1.1, 0.12, 0.8, 0.76,
             3.1, 0.15, 0.8, 0.7]
    return base(seed, 5, parts, boxes, "hand,hand", "black,red,blue", "stages, variant: ingres -> mantis -> fly")


def r_swap(seed=5341, grammar_hand="fly_open", **over):
    """variant route, the relations swapped: a voice's own loops caught by riding it (grammar), then the far
    river CROSSED (its heading sets the nib), then pools, then dry."""
    lp = dict(hand="ingres", length=6000.0, route=ROUTE_A, read_box=[0.0, 0.0, 280.0, 400.0], pull=0.07,
              reach=20.0, ride_mm=45.0, tau=150.0, p_max=0.92, dW=0.55, W_max=2.6, ink=1700.0,
              pool_gap=10.0, capture=4.0, align=0.5)
    lp.update(over)
    parts = [line(**lp), voice_layer(grammar_hand, 0.6, "voice: " + grammar_hand), river(box_angle=78.0)]
    parts[1]["renderer"]["pen"] = 0.3
    boxes = [0.55, 0.42, 1.0, 0.48,
             2.25, 0.06, 0.55, 0.88]
    return base(seed, 5, parts, boxes, "grammar,nib", "black,red,blue",
                f"stages, variant: wire -> {grammar_hand}'s loops -> nib (river crossed) -> beads -> dry")


def r_dry_river(seed=5316, **over):
    """counterfactual: the river moved down (same fragment) so the line never rides it."""
    rec = r_main(seed, river_box=(0.55, 0.84, 1.0, 0.13), **over)
    rec["label"] = "stages, counterfactual: the river moved; the line never rides it"
    return rec


RECIPES = {"main": r_main, "missed": r_missed, "noriver": r_dry_river, "control": r_control, "hands": r_hands, "swap": r_swap}


def build(rec: dict, name: str, *, debug: bool = True, px=5.0):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    strip, sheets = ST.run_stages(rec)
    imgs = [S.render(sh, px_per_mm=px) for sh in sheets]
    wall = S.assemble(imgs, title=rec.get("label"))
    wall.save(d / "row.jpg", quality=88)
    (d / "row.recipe.json").write_text(json.dumps(strip.recipe, indent=1) + "\n")
    for k, sh in enumerate(sheets):
        S.save_sheet_recipe(sh, d / f"sheet-{k + 1}.recipe.json")
    line = [m for m in strip.marks if m.meta.get("part") == 0][0]
    if debug:
        from PIL import ImageDraw  # noqa: PLC0415
        im = S.render(strip, px_per_mm=2.5)
        dr = ImageDraw.Draw(im)
        for k in range(1, int(strip.recipe["arranger"]["sheets"])):
            x = k * SW * 2.5
            dr.line([(x, 0), (x, im.height)], fill=(200, 200, 200))
        col = {"ride": (36, 131, 123), "leave": (36, 131, 123), "cross": (175, 48, 41), "pool": (94, 64, 157),
               "dry": (188, 82, 21)}
        for s, kind, x, y in line.meta["events"]:
            c = col.get(kind.split(":")[0], (0, 0, 0))
            dr.ellipse([x * 2.5 - 5, y * 2.5 - 5, x * 2.5 + 5, y * 2.5 + 5], outline=c, width=2)
        im.save(d / "debug.jpg", quality=85)
    ev = line.meta["events"]
    print(name, "len", round(line.meta["length_mm"]), "spent", line.meta["ink_spent"], "dry", line.meta["dry_at"],
          "pools", len(line.meta["pools"]), "layers", line.meta["layers"])
    print("  events", [(e[0], e[1]) for e in ev][:60])
    return strip, sheets, imgs


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "try"
    if cmd == "try":
        name = sys.argv[2] if len(sys.argv) > 2 else "main"
        seed = int(sys.argv[3]) if len(sys.argv) > 3 else None
        over = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        fn = RECIPES[name]
        rec = fn(seed, **over) if seed is not None else fn(**over)
        build(rec, f"{name}-{rec['seed']}" + ("-" + sys.argv[5] if len(sys.argv) > 5 else ""))


# ---------------------------------------------------------------------------
# review images
# ---------------------------------------------------------------------------

def _counts(line, sheets: int, sw: float):
    """Per sheet: the events in it, the caught-grammar share of its length, its mean nib width."""
    import numpy as np  # noqa: PLC0415
    ev = [{} for _ in range(sheets)]
    for _s, kind, x, _y in line.meta["events"]:
        k = int(min(max(x // sw, 0), sheets - 1))
        key = kind.split(":")[0]
        if key == "waypoint":
            continue
        ev[k][key] = ev[k].get(key, 0) + 1
    x = line.points[:, 0]
    src = np.asarray(line["src"])
    W = np.asarray(line["W"])
    out = []
    for k in range(sheets):
        sel = (x >= k * sw) & (x < (k + 1) * sw)
        out.append((ev[k], float(np.mean(src[sel] == 1)) if sel.any() else 0.0,
                    float(np.mean(src[sel] == 3)) if sel.any() else 0.0,
                    float(np.max(W[sel])) if sel.any() else 0.0, int(sel.sum() * 0.25)))
    return out


WORDS = {"ride": "rides the {g}", "cross": "crosses the {n}", "pool": "crosses itself wet", "dry": "ink spent: dry",
         "edge": "sheet edge", "leave": None}


def captions(line, sheets: int, sw: float, grammar_name="blue", nib_name="red", caught="river bends"):
    rows = []
    for ev, g, h, wmax, mm in _counts(line, sheets, sw):
        a = []
        for key in ("ride", "edge", "cross", "pool", "dry"):
            if key in ev and WORDS.get(key):
                w = WORDS[key].format(g=grammar_name, n=nib_name)
                a.append(w + (f" x{ev[key]}" if ev[key] > 1 and key in ("cross", "pool", "edge") else ""))
        b = f"{caught} {g * 100:.0f} %  ·  nib up to {wmax:.1f} mm  ·  {mm} mm of line"
        rows.append(("; ".join(a) if a else "(nothing met)", b))
    return rows


def wall(imgs, caps, title, *, gap=22, pad=34, fs=None):
    from PIL import Image, ImageDraw  # noqa: PLC0415
    from gesture.kit.core import _font  # noqa: PLC0415
    cw, ch = imgs[0].width, imgs[0].height
    fs = fs or max(12, int(cw / 26))
    th = int(fs * 2.2)
    capH = int(fs * 3.2)
    Wt = 2 * pad + len(imgs) * cw + (len(imgs) - 1) * gap
    Ht = 2 * pad + th + ch + capH
    im = Image.new("RGB", (Wt, Ht), S.WALL)
    dr = ImageDraw.Draw(im)
    dr.text((pad, pad // 2), title, fill=(0x57, 0x56, 0x53), font=_font(int(fs * 1.1)))
    for i, (s_im, (c1, c2)) in enumerate(zip(imgs, caps)):
        x = pad + i * (cw + gap)
        y = pad + th
        dr.rectangle([x + 3, y + 3, x + cw + 3, y + ch + 3], fill=S.EDGE)
        im.paste(s_im, (x, y))
        dr.text((x, y + ch + int(fs * 0.4)), f"{i + 1}  {c1}", fill=(0x40, 0x3E, 0x3C), font=_font(fs))
        dr.text((x, y + ch + int(fs * 1.6)), c2, fill=(0x87, 0x85, 0x80), font=_font(int(fs * 0.85)))
    return im


def series_image(rec, title, px=3.0, **capkw):
    strip, sheets = ST.run_stages(rec)
    line = [m for m in strip.marks if m.meta.get("part") == 0][0]
    n = len(sheets)
    imgs = [S.render(sh, px_per_mm=px) for sh in sheets]
    return strip, sheets, line, wall(imgs, captions(line, n, SW, **capkw), title)


def save(im, name, recipe, quality=84):
    p = RES / f"{name}.jpg"
    q = quality
    while True:
        im.save(p, quality=q, optimize=True)
        if p.stat().st_size < 395_000 or q < 50:
            break
        q -= 6
    (RES / f"{name}.recipe.json").write_text(json.dumps(recipe, indent=1) + "\n")
    print(p.name, im.size, p.stat().st_size // 1000, "KB q", q)


def review():
    from PIL import Image, ImageDraw  # noqa: PLC0415
    from gesture.kit.core import _font  # noqa: PLC0415
    # 1. the piece
    rec = r_main()
    strip, sheets, line, im = series_image(
        rec, "Stages: one line across five A5 sheets; it changes only where it meets something (seed 5316)")
    save(im, "stages-1-series", strip.recipe)
    # 2. close-up: sheets 1 and 2 (the ride, the river's bends coming in)
    imgs = [S.render(sheets[k], px_per_mm=5.6) for k in (0, 1)]
    cap = captions(line, 5, SW)[:2]
    im = wall(imgs, cap, "Stages, sheets 1-2: the line rides 0.9 mm beside the river, leaves at a tangent, "
                         "and the river's own bends come back into it, more and more", fs=24)
    save(im, "stages-2-closeup-sheets1-2", {"series": strip.recipe, "sheets": [1, 2], "px_per_mm": 5.6})
    # 3. variant route
    rv = r_swap(5344)
    strip3, _sh3, line3, im = series_image(
        rv, "Stages, variant route (seed 5344): rides the red fly and takes its loops; crosses the blue river, "
            "whose heading sets the nib; pools; dry", grammar_name="red", nib_name="blue", caught="fly bends")
    save(im, "stages-3-variant", strip3.recipe)
    # 4. counterfactuals + the control
    rows, recs = [], {}
    for name, fn, title in (
            ("noriver", r_dry_river, "a. the river moved down: never ridden, so no river bends; the red still "
                                     "gives a nib, but a calm line seldom crosses itself, so few beads"),
            ("missed", r_missed, "b. the red voice moved down: never crossed, so the same path stays a hairline; "
                                 "no wet ink, so no beads, no dry-out"),
            ("control", r_control, "c. DUD, the control: the same changes applied at sheet edges 1 and 2 "
                                   "(by index), whatever the line meets")):
        r = fn()
        st, _s, ln, w = series_image(r, title, px=3.0)
        recs[name] = st.recipe
        rows.append(w)
    Wt = max(r.width for r in rows)
    H = sum(r.height for r in rows)
    out = Image.new("RGB", (Wt, H), S.WALL)
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height
    save(out, "stages-4-counterfactuals", recs, quality=80)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "review":
    review()
