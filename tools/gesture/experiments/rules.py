"""Round 13, thread I-a `rules`: rules read off Oehlen's works on paper, played as breakable rules.

    .local/gesture/.venv/bin/python tools/gesture/experiments/rules.py <name> [<name> ...]

Each name is a recipe builder (or `review`, which rebuilds the review images).
Working images go to .local/gesture/out/rules/ with the recipe beside each.
Write-up: tools/gesture/results/rules-2026-10-18.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_oehlen_found as of  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/rules"
RES = HERE / "results"
FRAME = [300.0, 200.0]     # the AxiDraw's whole bed at 3:2: R3's "edge" is the paper's real edge


def chart(hands=("trail_miner",), chart_="kappa"):
    return {"voice": {"id": "diagram", "chart": chart_, "hands": list(hands)}}


def river(span_w=2400, angle=0.0, start=0.0):
    return {"voice": {"id": "oehlen_found_river", "span_w": span_w, "angle": angle, "start": start}}


def hand(h, length=4.0, joins="smooth"):
    return {"voice": {"id": "hand", "hand": h, "length": length, "joins": joins}}


def base(seed, parts, **arr):
    a = {"id": "rules"}
    a.update(arr)
    return {"label": "rules", "frame": FRAME, "seed": seed, "margin": 4.0, "arranger": a, "parts": parts,
            "renderer": {"id": "oehlen_found_ink"}}


RECIPES = {}


def recipe(fn):
    RECIPES[fn.__name__] = fn
    return fn


@recipe
def r1():
    return base(1301, [chart(), river(), hand("trail_miner", 4.0), hand("marden", 4.0), hand("river_bend", 3.0)],
                found=2, found_boxes=[0.36, 0.34, 0.5, 0.42, -3.0, 0.6, 0.66, 0.62, 0.12, -8.0],
                made_boxes=[0.3, 0.5, 0.5, 0.8, 0.65, 0.45, 0.55, 0.7, 0.7, 0.6, 0.5, 0.7], cover_after=2)


@recipe
def piece():
    """The piece: a dancer's thrusting hand and a river-bend hand, played by the five rules over a found chart
    and a far river, the cover's torn outline drawn in the found pen. Seed 1317."""
    r = r2()
    r["seed"] = 1317
    r["parts"][2] = hand("dance_thrusting", 3.0)
    r["parts"][3] = hand("river_bend", 3.0)
    r["arranger"]["cover_edge"] = "drawn"
    r["label"] = "rules: piece"
    return r


@recipe
def piece_noedge():
    r = piece()
    r["arranger"]["cover_edge"] = "none"
    return r


@recipe
def raw():
    """No rule in play: the found pasted, the two hands placed as they came (one thin pen)."""
    r = piece()
    r["arranger"].update(rules="", bold_pen=0.25, hair_pen=0.25)
    r["label"] = "rules: no rule yet"
    return r


@recipe
def dud_crowded():
    """Dud: three hands over the whole sheet, no blank decided: every rule fires everywhere."""
    r = r1()
    r["label"] = "rules: dud, crowded"
    return r


HANDS = [("trail_miner", "dancer_madeline", 1346), ("lichtenberg", "trail_grazer", 1343),
         ("marden", "dance_levitation", 1342), ("mime_mantis", "fly_fru", 1347)]


def other_hands(a, b, sd):
    r = piece()
    r["seed"] = sd
    r["parts"][2] = hand(a, 3.0)
    r["parts"][3] = hand(b, 3.0)
    r["label"] = f"rules: {a} + {b}"
    return r

@recipe
def rulebook():
    """The same recipe with every rule obeyed (no breaks)."""
    r = piece()
    r["arranger"]["breaks"] = False
    r["label"] = "rules: rulebook (no breaks)"
    return r


def build(name, recipe_=None, *, crop=None, px=6.0, tag=None):
    r = recipe_ or RECIPES[name]()
    sh = kit.run(r)
    p = of.save(sh, OUT / f"{tag or name}.jpg", px_per_mm=px, crop=crop)
    meta = sh.marks[0].meta.get("rules", {}) if sh.marks else {}
    (OUT / f"{tag or name}.log.json").write_text(json.dumps(meta, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
    return sh, p, meta


TAGC = {1: (0xDA, 0x70, 0x2C), 3: (0x87, 0x9A, 0x39), 4: (0xD1, 0x4D, 0x41), 5: (0x8B, 0x7E, 0xC8)}
EVC = {"fire": (0x20, 0x5E, 0xA6), "break": (0xD1, 0x4D, 0x41)}


def overlay(sheet, *, px=4.0, crop=None, marks_only=False, numbers=True, r1_ticks=True):
    """The colour preview with what the rules did: stretches coloured by the rule that shaped them
    (orange ride R4, red ride by break, green entry step R3, purple exit motif R2), the cover outline,
    and every logged event as a numbered marker (blue fired, red broke)."""
    import numpy as np
    from PIL import ImageDraw
    x0, y0 = (crop[0], crop[1]) if crop else (0.0, 0.0)
    im = of.render_colour(sheet, px_per_mm=px, crop=crop)
    dr = ImageDraw.Draw(im)
    meta = sheet.marks[0].meta.get("rules", {})
    P = lambda v: ((v[0] - x0) * px, (v[1] - y0) * px)   # noqa: E731
    for c in meta.get("covers", []):
        q = [P(v) for v in c["polygon"]]
        dr.line(q, fill=EVC["break"] if c["cuts_made"] else (0x6F, 0x6E, 0x69), width=max(int(px / 2), 1))
    for m in sheet.marks:
        if m.meta.get("of_role") != "made" or "neg" not in m.channels:
            continue
        g = np.asarray(m["neg"]).astype(int)
        Q = [P(v) for v in m.points]
        w = max(int(round(m.meta.get("pen", 0.4) * px * 1.6)), 3)
        for i in range(len(Q) - 1):
            if g[i] in TAGC and g[i + 1] == g[i]:
                dr.line([Q[i], Q[i + 1]], fill=TAGC[g[i]], width=w)
    if marks_only:
        return im, []
    font = kit.core._font(max(int(px * 2.6), 10))
    events = [e for e in meta.get("log", []) if e["rule"] != "R1" or e["event"] == "break"]
    if r1_ticks:
        for e in meta.get("log", []):
            if e["rule"] == "R1" and e["event"] == "fire":
                x, y = P(e["xy"])
                r = px * 0.9
                dr.ellipse([x - r, y - r, x + r, y + r], outline=(0x6F, 0x6E, 0x69), width=1)
    for n, e in enumerate(events, 1):
        x, y = P(e["xy"])
        col = EVC[e["event"]]
        r = px * 2.2
        dr.ellipse([x - r, y - r, x + r, y + r], outline=col, width=max(int(px / 2), 2))
        if numbers:
            dr.text((x + r + 2, y - r - 2), f"{n} {e['rule']}{'' if e['event'] == 'fire' else ' broke'}", fill=col,
                    font=font)
    return im, events


def summary(meta):
    from collections import Counter
    c = Counter((e["rule"], e["event"]) for e in meta.get("log", []))
    return " ".join(f"{r}{'+' if e == 'fire' else 'x'}{n}" for (r, e), n in sorted(c.items()))



@recipe
def r2():
    """Two hands, the found on the left two thirds, the right third a decided blank."""
    return base(1302, [chart(), river(), hand("trail_miner", 3.5), hand("marden", 3.0)],
                found=2, found_boxes=[0.33, 0.33, 0.48, 0.42, -3.0, 0.42, 0.7, 0.6, 0.11, -7.0],
                made_boxes=[0.4, 0.5, 0.55, 0.75, 0.55, 0.5, 0.5, 0.7], cover_after=1, cover_wh=[24.0, 72.0])


def sweep_hands(pairs=None, seeds=(1310, 1311, 1312), lengths=(3.5, 3.0), tag="sweep_hands"):
    pairs = pairs or [("dance_thrusting", "trail_grazer"), ("trail_miner", "dancer_madeline"),
                      ("river_bend", "mime_mantis"), ("dance_thrusting", "river_bend"),
                      ("lichtenberg", "trail_miner"), ("dancer_madeline", "fly_fru")]
    ims = []
    for a, b in pairs:
        for sd in seeds:
            r = r2()
            r["seed"] = sd
            r["parts"][2] = hand(a, lengths[0])
            r["parts"][3] = hand(b, lengths[1])
            sh = kit.run(r)
            im, _ = overlay(sh, px=2.5, numbers=False, r1_ticks=False)
            meta = sh.marks[0].meta.get("rules", {})
            ims.append(_label(im, f"{a} + {b} · {sd} · {summary(meta)}"))
    kit.contact(ims, len(seeds), title=tag).save(OUT / f"{tag}.jpg", quality=80)


def _label(im, text):
    from PIL import Image, ImageDraw
    fs = max(12, im.width // 50)
    out = Image.new("RGB", (im.width, im.height + int(fs * 1.8)), kit.core.PAPER)
    out.paste(im, (0, 0))
    ImageDraw.Draw(out).text((6, im.height + 3), text, fill=(0x10, 0x0F, 0x0F), font=kit.core._font(fs))
    return out


def sweep_seeds(a="dance_thrusting", b="river_bend", seeds=range(1316, 1332), la=3.0, lb=3.0, tag=None):
    ims = []
    for sd in seeds:
        r = r2()
        r["seed"] = sd
        r["parts"][2] = hand(a, la)
        r["parts"][3] = hand(b, lb)
        sh = kit.run(r)
        im = of.render_colour(sh, px_per_mm=2.5)
        ims.append(_label(im, f"{sd} · {summary(sh.marks[0].meta.get('rules', {}))}"))
    kit.contact(ims, 4, title=f"{a} + {b}").save(OUT / f"{tag or 'sweep_seeds'}.jpg", quality=80)


def _log_panel(events, n_r1, size, title):
    from PIL import Image, ImageDraw
    W, H = size
    im = Image.new("RGB", (W, H), kit.core.PAPER)
    dr = ImageDraw.Draw(im)
    fs = max(14, W // 64)
    f = kit.core._font(fs)
    fb = kit.core._font(int(fs * 1.15))
    y = 18
    dr.text((18, y), title, fill=(0x10, 0x0F, 0x0F), font=fb)
    y += int(fs * 2.2)
    for n, e in enumerate(events, 1):
        col = EVC[e["event"]]
        head = f"{n:>2}  {e['rule']} {'fired' if e['event'] == 'fire' else 'BROKE'}  line {e['line'] + 1}"
        dr.text((18, y), head, fill=col, font=f)
        why = e["why"]
        dr.text((18 + fs * 13, y), why[:84] + ("…" if len(why) > 84 else ""), fill=(0x40, 0x3E, 0x3C), font=f)
        y += int(fs * 1.45)
    y += int(fs * 0.8)
    dr.text((18, y), f"R1 fired {n_r1} times: the pen changes where the line meets or leaves found ink "
                     "(small grey rings)", fill=(0x6F, 0x6E, 0x69), font=f)
    y += int(fs * 2.0)
    for k, (c, t) in enumerate([(TAGC[3], "R3 entry step"), (TAGC[1], "R4 ride"), (TAGC[4], "R4 ride by a break"),
                                (TAGC[5], "R2 becomes the found")]):
        x = 18 + k * (W - 36) // 4
        dr.line([(x, y + fs // 2), (x + fs * 2, y + fs // 2)], fill=c, width=max(fs // 3, 3))
        dr.text((x + fs * 2 + 8, y), t, fill=(0x40, 0x3E, 0x3C), font=f)
    return im


def _jpg(im, path, max_kb=390, max_px=2400):
    from PIL import Image
    if max(im.size) > max_px:
        k = max_px / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)), Image.Resampling.LANCZOS)
    for q in (88, 84, 80, 76, 72, 68, 64, 60):
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size <= max_kb * 1024:
            return path
    return path


def review():
    """Rebuild the four review images into tools/gesture/results/ (recipe JSON beside each)."""
    import numpy as np  # noqa: F401
    RES.mkdir(parents=True, exist_ok=True)
    # 1. the piece
    sh = kit.run(piece())
    im = of.render_colour(sh, px_per_mm=8.0)
    _jpg(im, RES / "rules-1-piece.jpg")
    sh.save_recipe(RES / "rules-1-piece.recipe.json")
    (OUT / "piece.log.json").write_text(json.dumps(sh.marks[0].meta["rules"], indent=1))
    # 2. process: no rule yet | every rule obeyed | the piece with its log | the log
    px = 4.0
    raw_sh = kit.run(raw())
    book = kit.run(rulebook())
    a = _label(of.render_colour(raw_sh, px_per_mm=px), "1  found pasted (blue); the two hands placed as they came, no rule yet")
    b_im, _ = overlay(book, px=px, numbers=False)
    b = _label(b_im, "2  every rule obeyed, none broken (the rulebook drawing): rings = rules firing")
    c_im, events = overlay(sh, px=px)
    c = _label(c_im, "3  the piece with its log: blue fired, red broke (numbers as in 4)")
    n_r1 = sum(1 for e in sh.marks[0].meta["rules"]["log"] if e["rule"] == "R1" and e["event"] == "fire")
    d = _log_panel(events, n_r1, c.size, "4  the log (line 1 = the dancer's thrusting hand, line 2 = the river-bend hand)")
    strip = kit.contact([a, b, c, d], 2, title="rules · process: the same recipe without rules, with every rule "
                        "obeyed, and as played (seed 1317)")
    _jpg(strip, RES / "rules-2-process.jpg")
    json.dump({"panels": [raw(), rulebook(), piece(), "log of panel 3"]}, open(RES / "rules-2-process.recipe.json", "w"),
              indent=1)
    # 3. same rules, other hands
    ims, recs = [], []
    for ha, hb, sd in HANDS:
        r = other_hands(ha, hb, sd)
        s2 = kit.run(r)
        ims.append(_label(of.render_colour(s2, px_per_mm=px), f"{ha} + {hb} · seed {sd} · "
                          f"{summary(s2.marks[0].meta['rules'])}"))
        recs.append(r)
    _jpg(kit.contact(ims, 2, title="rules · the same five rules and found ground, four other pairs of hands"),
         RES / "rules-3-hands.jpg")
    json.dump({"panels": recs}, open(RES / "rules-3-hands.recipe.json", "w"), indent=1)
    # 4. dud
    sd_ = kit.run(dud_crowded())
    d_im, _ = overlay(sd_, px=px, numbers=False)
    dud = kit.contact([_label(of.render_colour(sd_, px_per_mm=px), "the sheet"),
                       _label(d_im, f"what the rules did · {summary(sd_.marks[0].meta['rules'])}")], 2,
                      title="rules · dud: three hands over the whole sheet, no blank decided")
    _jpg(dud, RES / "rules-4-dud-crowded.jpg")
    sd_.save_recipe(RES / "rules-4-dud-crowded.recipe.json")
    for f in sorted(RES.glob("rules-*.jpg")):
        print(f.name, f.stat().st_size // 1024, "KB")


# MAIN
if __name__ == "__main__":
    for nm in sys.argv[1:] or ["r1"]:
        if nm in globals() and nm.startswith(("sweep", "review")):
            globals()[nm]()
            continue
        sh, p, meta = build(nm)
        overlay(sh)[0].save(OUT / f"{nm}-debug.jpg", quality=85)
        print(nm, p, summary(meta))
