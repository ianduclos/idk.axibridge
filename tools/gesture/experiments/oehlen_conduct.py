"""Round 12, thread oehlen_conduct: run recipes and write previews.

usage: python tools/gesture/experiments/oehlen_conduct.py <outdir> '<json recipe or list of recipes>'
Each recipe may carry "name"; images go to .local/gesture/out/oehlen_conduct/<outdir>/<name>.jpg
with the recipe beside them.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "tools/gesture")
from gesture import kit  # noqa: E402

OUT = ".local/gesture/out/oehlen_conduct/"


def go(outdir, recipes, px=6, label="auto"):
    paths = []
    for r in recipes:
        name = r.pop("name")
        t = time.time()
        sh = kit.run(r)
        p = kit.preview(sh, f"{OUT}{outdir}/{name}.jpg", px_per_mm=px, label=label)
        m = sh.marks[0].meta.get("conduct", {})
        print(name, round(time.time() - t, 1), "s", "lines", m.get("lines"),
              "cues", [c["kind"][0] for c in m.get("cues", [])], flush=True)
        paths.append(p)
    return paths





def debug(recipe, path, px=4):
    """The sheet with the scaled source (red) and cue points under it."""
    import numpy as np
    from PIL import ImageDraw
    sys.path.insert(0, "tools/gesture")
    from gesture.kit import voices_oehlen_conduct as vc  # noqa: PLC0415
    r = dict(recipe)
    r.pop("name", None)
    sh = kit.run(r)
    im = kit.render_image(sh, px_per_mm=px, label=None)
    d = ImageDraw.Draw(im)
    m0 = sh.marks[0].meta["conduct"]
    v = sh.recipe["parts"][0]["voice"]
    tr = kit.library.load("dance_trail", v["trail"])
    fps = float(tr["fps"])
    a0 = int(round(v["t0"] * fps))
    p = np.asarray(tr[v["effector"] + "_xy"][a0:a0 + int(round(v["seconds"] * fps))], float)
    lo, hi = p.min(0), p.max(0)
    sb = m0["source_box"]
    ks = min(sb[2] / (hi - lo)[0], sb[3] / (hi - lo)[1])
    W, H = sh.frame
    inset = sh.meta["inset"]
    bw, bh = W - 2 * inset, H - 2 * inset
    cen = np.array([inset + v["place"][0] * bw, inset + v["place"][1] * bh])
    big = (p - (lo + hi) / 2) * v["enlarge"] * ks + cen
    q = big * px
    d.line([tuple(x) for x in q], fill=(220, 60, 40), width=1)
    for c in m0["cues"]:
        i = min(int(round(c["t"] * fps)), len(q) - 1)
        col = {"stop": (40, 90, 220), "turn": (40, 160, 60), "burst": (230, 140, 0), "enter": (0, 0, 0),
               "end": (0, 0, 0), "return": (160, 0, 160)}[c["kind"]]
        x, y = q[i]
        d.ellipse([x - 4, y - 4, x + 4, y + 4], outline=col, width=2)
    for b in m0["blanks_mm"]:
        x, y, rr = (np.array(b) * px).tolist()
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=(150, 150, 150))
    im.save(path, quality=85)
    return sh


# ---------------------------------------------------------------------------
# the review images (round 12): python tools/gesture/experiments/oehlen_conduct.py review
# ---------------------------------------------------------------------------

RES = "tools/gesture/results/oehlen_conduct-"
REF = ".local/gesture/corpus/artists/albert_oehlen/"
FLEX = {"ink": (0x10, 0x0F, 0x0F), "paper": (0xFF, 0xFC, 0xF0), "grey": (0xB7, 0xB5, 0xAC),
        "mid": (0x87, 0x85, 0x80), "red": (0xAF, 0x30, 0x29), "blue": (0x20, 0x5E, 0xA6),
        "green": (0x66, 0x80, 0x0B), "orange": (0xBC, 0x52, 0x15)}

# the finished piece: 300 × 200 mm = the AxiDraw's whole reach at the 3:2 of the 2016 charcoals;
# the conductor (7 s of a dancer's right hand) at 34 mm in the corner, ≈ ×6 to the performance
PIECE = {"label": "oehlen_conduct: piece", "seed": 3323, "frame": [300, 200], "margin": 12,
         "voice": {"id": "oehlen_conduct", "trail": "staccato", "effector": "rhand", "t0": 5.0, "seconds": 7.0,
                   "hands": ["trail_miner"], "blanks": [0.1, 0.95, 0.42]},
         "renderer": {"id": "oehlen_conduct_ink"}}


def _with(base, **voice):
    r = json.loads(json.dumps(base))
    for k, v in voice.items():
        if k in ("seed", "label"):
            r[k] = v
        else:
            r["voice"][k] = v
    return r


def _caption(im, text, h=40):
    from PIL import Image, ImageDraw  # noqa: PLC0415
    out = Image.new("RGB", (im.width, im.height + h), FLEX["paper"])
    out.paste(im, (0, 0))
    ImageDraw.Draw(out).text((10, im.height + 9), text, fill=FLEX["ink"], font=kit.core._font(19))
    return out


def _mm(px):
    return lambda p: (float(p[0]) * px, float(p[1]) * px)


def _source_panel(sheet, W, H):
    """The conductor's line, enlarged to the panel, with its cues."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image, ImageDraw  # noqa: PLC0415
    v = sheet.recipe["parts"][0]["voice"]
    tr = kit.library.load("dance_trail", v["trail"])
    fps = float(tr["fps"])
    a0 = int(round(v["t0"] * fps))
    p = np.asarray(tr[v["effector"] + "_xy"][a0:a0 + int(round(v["seconds"] * fps))], float)
    lo, hi = p.min(0), p.max(0)
    k = 0.8 * min(W / (hi - lo)[0], H / (hi - lo)[1])
    q = (p - (lo + hi) / 2) * k + np.array([W / 2, H / 2])
    ss = 3
    im = Image.new("RGB", (W * ss, H * ss), FLEX["paper"])
    d = ImageDraw.Draw(im)
    d.line([tuple(x * ss) for x in q], fill=FLEX["ink"], width=2 * ss, joint="curve")
    col = {"stop": FLEX["blue"], "turn": FLEX["green"], "burst": FLEX["orange"], "enter": FLEX["ink"],
           "end": FLEX["ink"]}
    for c in sheet.marks[0].meta["conduct"]["cues"]:
        i = min(int(round(c["t"] * fps)), len(q) - 1)
        x, y = q[i] * ss
        r = 9 * ss
        d.ellipse([x - r, y - r, x + r, y + r], outline=col[c["kind"]], width=3 * ss)
    im = im.resize((W, H), Image.Resampling.LANCZOS)
    ImageDraw.Draw(im).text((12, 10), "blue: stop (tacet)   green: turn (land here)", fill=FLEX["mid"],
                            font=kit.core._font(17))
    return im


def _score_panel(sheet, px):
    """What the performer receives: the cue points ×6 and the chords between
    them, the reserved blank, the conductor in its corner."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    W, H = sheet.frame
    ss = 3
    im = Image.new("RGB", (int(W * px * ss), int(H * px * ss)), FLEX["paper"])
    d = ImageDraw.Draw(im)
    f = _mm(px * ss)
    m0 = sheet.marks[0].meta["conduct"]
    src = sheet.marks[0]
    d.line([f(x) for x in src.points], fill=FLEX["ink"], width=ss)
    for b in m0["blanks_mm"][:-1]:
        x, y = f(b[:2])
        r = b[2] * px * ss
        for a in range(0, 360, 8):                      # a dotted rim
            import math  # noqa: PLC0415
            u = math.radians(a)
            d.ellipse([x + r * math.cos(u) - ss, y + r * math.sin(u) - ss, x + r * math.cos(u) + ss,
                       y + r * math.sin(u) + ss], fill=FLEX["grey"])
    cues = m0["cues"]
    for c0, c1 in zip(cues[:-1], cues[1:]):
        d.line([f(c0["mm"]), f(c1["mm"])], fill=FLEX["grey"], width=2 * ss)
    col = {"stop": FLEX["blue"], "turn": FLEX["green"], "burst": FLEX["orange"], "enter": FLEX["ink"],
           "end": FLEX["ink"]}
    for c in cues:
        x, y = f(c["mm"])
        r = 7 * ss
        d.ellipse([x - r, y - r, x + r, y + r], outline=col[c["kind"]], width=3 * ss)
    return im.resize((int(W * px), int(H * px)), Image.Resampling.LANCZOS)


def _roles_panel(sheet, px):
    """The piece with its second passes in red over the first pass in grey."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    W, H = sheet.frame
    ss = 3
    im = Image.new("RGB", (int(W * px * ss), int(H * px * ss)), FLEX["paper"])
    d = ImageDraw.Draw(im)
    f = _mm(px * ss)
    for ink in sheet.inks:
        role = ink.meta.get("role", 1)
        colr = FLEX["red"] if role == 2 else (FLEX["grey"] if role == 1 else FLEX["ink"])
        w = max(int(round(ink.pen * px * ss)), 1)
        d.line([f(x) for x in ink.points], fill=colr, width=w, joint="curve")
    return im.resize((int(W * px), int(H * px)), Image.Resampling.LANCZOS)


def _ref_panel(W, H):
    from PIL import Image, ImageDraw  # noqa: PLC0415
    im = Image.new("RGB", (W, H), FLEX["paper"])
    a = Image.open(REF + "12-6908-Oehlen-Untitled_DJGqnNw.original.jpg").convert("RGB")
    b = Image.open(REF + "15-6836-Oehlen-Conduction_11_oqnDZXG.original.jpg").convert("RGB")
    ha = int(H * 0.42)
    a = a.resize((int(a.width * ha / a.height), ha))
    hb = int(H * 0.78)
    b = b.resize((int(b.width * hb / b.height), hb))
    if b.width > W - a.width - 30:
        s = (W - a.width - 30) / b.width
        b = b.resize((int(b.width * s), int(b.height * s)))
    im.paste(a, (8, 8))
    im.paste(b, (W - b.width - 8, H - b.height - 34))
    d = ImageDraw.Draw(im)
    fnt = kit.core._font(15)
    d.text((8, ha + 14), "Untitled, 2010, 29.8 × 27.9 cm", fill=FLEX["mid"], font=fnt)
    d.text((8, ha + 34), "enlarged by hand, as:", fill=FLEX["mid"], font=fnt)
    d.text((8, H - 26), "Albert Oehlen, Conduction 11, 2011, 210 × 270 cm. © Albert Oehlen / VG Bild-Kunst "
           "(Corbett vs. Dempsey); research thumbnails", fill=FLEX["mid"], font=kit.core._font(13))
    return im


def review():
    from PIL import Image  # noqa: PLC0415
    # 1. the piece
    sh = kit.run(PIECE)
    kit.preview(sh, RES + "piece.jpg", px_per_mm=8,
                label="oehlen_conduct: 7 s of a dancer's hand (corner) conducts a learned hand x6; blank "
                      "lower left; second passes; pens 2.2 / 0.5 mm; 300 x 200 mm; seed 3323")
    # 2. process
    px = 2.58
    W, H = int(300 * px), int(200 * px)
    one = kit.run(_with(PIECE, double=0.0, label="oehlen_conduct: one pass"))
    panels = [
        _caption(_ref_panel(W, H), "1  the procedure: small fast drawing, then enlarged by hand (reference)"),
        _caption(_source_panel(sh, W, H), "2  the conductor: staccato, right hand, 5–12 s, its cues"),
        _caption(_score_panel(sh, px), "3  the score: cue points ×6, blank reserved first"),
        _caption(kit.render_image(one, px_per_mm=px, label=None), "4  the performance: a learned hand, cue to cue"),
        _caption(_roles_panel(sh, px), "5  second passes (red) split off the first and rejoin"),
        _caption(kit.render_image(sh, px_per_mm=px, label=None), "6  the piece"),
    ]
    kit.contact(panels, 3, title="oehlen_conduct — process (one score, one performance, one second pass)").save(
        RES + "process.jpg", quality=88)
    one.save_recipe(RES + "process.recipe.json")
    # 3. one score, four performances
    vs = [("seed 3323 (the piece)", PIECE), ("seed 3322", _with(PIECE, seed=3322)),
          ("seed 3333", _with(PIECE, seed=3333)), ("seed 3334", _with(PIECE, seed=3334))]
    ims = []
    recs = []
    for name, r in vs:
        s = kit.run(r)
        ims.append(_caption(kit.render_image(s, px_per_mm=3.8, label=None), name))
        recs.append(s.recipe)
    kit.contact(ims, 2, title="oehlen_conduct — one score, four performances (same conductor, same cues)").save(
        RES + "performances.jpg", quality=88)
    Path(RES + "performances.recipe.json").write_text(json.dumps(recs, indent=1) + "\n")
    # 4. close-up of the doubled bold stretch, 1:1 at 14 px/mm
    big = kit.render_image(sh, px_per_mm=14, label=None)
    k = 14
    big.crop((int(145 * k), int(40 * k), int(265 * k), int(175 * k))).resize((1680, 1890)).save(
        RES + "closeup.jpg", quality=90)
    sh.save_recipe(RES + "closeup.recipe.json")
    # 5. the dud: the tree program
    trees = []
    trecs = []
    for seed in (5507, 5508, 5511):
        r = {"label": "oehlen_conduct: tree dud", "seed": seed, "frame": [145, 218], "margin": 10,
             "voice": {"id": "oehlen_conduct_tree"}, "renderer": {"id": "oehlen_conduct_ink"}}
        s = kit.run(r)
        trees.append(_caption(kit.render_image(s, px_per_mm=4.4, label=None), f"tree program, seed {seed}"))
        trecs.append(s.recipe)
    kit.contact(trees, 3, title="dud — the tree program (D4): reads as twig / crack, branches go barbed").save(
        RES + "dud-tree.jpg", quality=88)
    Path(RES + "dud-tree.recipe.json").write_text(json.dumps(trecs, indent=1) + "\n")
    for p in ("piece", "process", "performances", "closeup", "dud-tree"):
        im = Image.open(RES + p + ".jpg")
        print(p, im.size)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "review":
    review()
    sys.exit(0)


if __name__ == "__main__" and len(sys.argv) > 2:
    rs = json.loads(sys.argv[2])
    go(sys.argv[1], rs if isinstance(rs, list) else [rs], px=float(sys.argv[3]) if len(sys.argv) > 3 else 6)
