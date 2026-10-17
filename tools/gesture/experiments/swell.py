"""Round 11, exploration 2 — swelling into mass (thread `swell`).

    .local/gesture/.venv/bin/python -m tools.gesture.experiments.swell [stage ...]

Stages (default: all):
  profiles   one line, the round-10 gather beads (cell a) against 8 swell profiles
  closeup    the three longest stresses at 10 px/mm, five ways
  threshold  where a smooth swell tips into a sausage: elongation vs swell length / head slope
  dots       deliberate dots: rules, sizes, shapes
  bold       3–4 bold single-gesture pieces
  combo      two hands, one swelling; the rosary redone (bold + interesting dots)
Every tile is `kit.run` + `kit.preview` (recipe beside it in .local/gesture/out/swell/);
sheets go to .local/gesture/out/swell/sheet-*.jpg (a few copied to results/);
numbers to .local/gesture/out/swell/numbers.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit.dev_chorus import FLEXOKI  # noqa: E402
from gesture.kit.swell_ink import part_inks  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/swell"
RES = HERE / "results"
NUM: dict = {}

ROUTE = ["matisse", "shikasta", "lichtenberg"]
V = {"id": "drift_tokens", "hands": ROUTE, "joins": "chain", "length": 3.0}
SEG = {"id": "prosody", "unit": "segment", "span": 8.0}
PULSE = {"id": "prosody", "unit": "pulse", "span": 5.0}
BASE = {"frame": [267, 180], "seed": 7000, "margin": 5.25, "voice": V, "modulators": [SEG]}  # margin = round-10 beads' reach: one line for every cell
GATHER = {"id": "dev_beads", "line": "nib", "shape": "gather"}
SAUSAGE = {"id": "nib", "style": "e", "pen": 0.4}


# ---------------------------------------------------------------------------
# images
# ---------------------------------------------------------------------------

def render_colour(sheet, *, px_per_mm=6.0, label=None, ss=2):
    """Each part in its recipe ink (swell_place / dev_chorus `inks`)."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    from gesture.kit.core import INK, PAPER, _font  # noqa: PLC0415
    W, H = sheet.frame
    k = px_per_mm * ss
    names = part_inks(sheet)
    hexc = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # noqa: E731
    rgb = np.ones((int(round(H * px_per_mm)), int(round(W * px_per_mm)), 3)) * np.array(PAPER, float)
    for pi in sorted({int(i.meta.get("part", 0)) for i in sheet.inks}):
        im = Image.new("L", (int(round(W * k)), int(round(H * k))), 0)
        dr = ImageDraw.Draw(im)
        for ink in sheet.inks:
            if int(ink.meta.get("part", 0)) != pi:
                continue
            q = ink.points * k
            d = max(ink.pen * k, 1.0)
            if len(q) >= 2:
                dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
            r = d / 2
            for v in (q if d > 4 else q[[0, -1]]):
                dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
        im = im.resize((rgb.shape[1], rgb.shape[0]), Image.Resampling.BOX)
        a = np.asarray(im, float)[..., None] / 255.0
        rgb = rgb * (1 - a) + np.array(hexc(FLEXOKI.get(names.get(pi, "black"), "#100F0F")), float) * a
    out = Image.fromarray(rgb.astype(np.uint8), "RGB")
    if label is None:
        return out
    fs = max(12, int(out.width / 80))
    strip = Image.new("RGB", (out.width, int(fs * 2.0)), PAPER)
    ImageDraw.Draw(strip).text((int(fs * 0.6), int(fs * 0.45)), label, fill=INK, font=_font(fs))
    full = Image.new("RGB", (out.width, out.height + strip.height), PAPER)
    full.paste(out, (0, 0))
    full.paste(strip, (0, out.height))
    return full


def tile(name, recipe, label, *, colour=False, px=4.0):
    sheet = kit.run({"label": label, **recipe})
    kit.preview(sheet, OUT / f"{name}.jpg", px_per_mm=6, label=label)
    if colour:
        render_colour(sheet, px_per_mm=6, label=label).save(OUT / f"{name}-colour.jpg", quality=88)
        return sheet, render_colour(sheet, px_per_mm=px, label=label)
    return sheet, kit.render_image(sheet, px_per_mm=px, label=label)


def save(img, name, *, results=False, maxw=2400, recipes=None):
    if img.width > maxw:
        img = img.resize((maxw, int(img.height * maxw / img.width)))
    p = OUT / f"sheet-{name}.jpg"
    img.save(p, quality=86, optimize=True)
    if recipes is not None:
        (OUT / f"sheet-{name}.recipe.json").write_text(json.dumps(recipes, indent=1))
    if results:
        q = RES / f"swell-{name}.jpg"
        im2 = img if img.width <= 1800 else img.resize((1800, int(img.height * 1800 / img.width)))
        qual = 82
        while True:
            im2.save(q, quality=qual, optimize=True)
            if q.stat().st_size < 400_000 or qual <= 35:
                break
            qual -= 6
        print("  ->", q.relative_to(ROOT), f"{q.stat().st_size / 1e3:.0f} kB")
    print("  ->", p.relative_to(ROOT))


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def mass_shapes(sheet, px: float = 6.0, open_mm: float = 1.6) -> dict:
    """Identical to experiments/developments.mass_shapes (round 10): rasterise,
    open with a 1.6 mm-radius disc, label blobs, elongation = √(λmax/λmin)."""
    from scipy import ndimage as ndi  # noqa: PLC0415
    im = np.asarray(kit.render_image(sheet, px_per_mm=px, label=None).convert("L")) < 128
    r = int(round(open_mm * px))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    blobs = ndi.binary_opening(im, structure=(xx * xx + yy * yy) <= r * r)
    lab, n = ndi.label(blobs)
    el, ln = [], []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if len(xs) < (2 * r) ** 2:
            continue
        ev = np.linalg.eigvalsh(np.cov(np.vstack([xs, ys])))
        el.append(float(np.sqrt(ev[1] / max(ev[0], 1e-9))))
        ln.append(float(np.hypot(np.ptp(xs), np.ptp(ys)) / px))
    if not el:
        return {"masses": 0}
    el = np.array(el)
    return {"masses": len(el), "elong_median": round(float(np.median(el)), 2),
            "elong_max": round(float(el.max()), 2), "share_round(<1.3)": round(float(np.mean(el < 1.3)), 2),
            "longest_mm": round(float(max(ln)), 1)}


def ink_geometry(sheet, part=None):
    import shapely  # noqa: PLC0415
    from shapely.geometry import LineString, Polygon  # noqa: PLC0415
    gs = []
    for k in sheet.inks:
        if part is not None and int(k.meta.get("part", 0)) != part:
            continue
        p = np.asarray(k.points)
        if len(p) < 2:
            continue
        if k.filled and k.closed and len(p) >= 4:
            gs.append(shapely.make_valid(Polygon(p)).buffer(0.5 * k.pen))
        else:
            gs.append(LineString(p).buffer(0.5 * k.pen, quad_segs=4))
    gs = [shapely.make_valid(g) for g in gs]
    try:
        return shapely.union_all(gs)
    except shapely.errors.GEOSException:
        return shapely.union_all(gs, grid_size=0.005)


def width_profile(sheet, mark, step=0.25):
    """Visible half-thickness rho(s): distance from each centreline point to
    the edge of the ink around it (the inscribed radius). Unlike a normal
    section it does not spike at corners or crossings; a bead that meets the
    line shows as a slope break (0 -> 1), a swell as a ramp."""
    import shapely  # noqa: PLC0415
    from gesture.kit.swell_ink import _resample  # noqa: PLC0415
    geom = ink_geometry(sheet, mark.meta.get("part"))
    bd = geom.boundary
    shapely.prepare(bd)
    pts, s = _resample(np.asarray(mark.points), step)
    rho = shapely.distance(shapely.points(pts), bd)
    return s, np.asarray(rho)


def smoothness(sheet, mi=0, pad=12.0):
    """Per stress window [start - pad, end + pad], on the flanks (rho below
    70 % of the window's max: every round mass has an apex, which is not a
    transition): max |drho/ds| and the slope break max |drho/ds(s+0.5) -
    drho/ds(s-0.5)|. A bead meeting the line breaks by ~1; a C1 swell by little."""
    from gesture.kit.dev_beads import bead_emphasis, runs  # noqa: PLC0415
    m = sheet.marks[mi]
    s, w = width_profile(sheet, m)
    e = np.interp(s, m.arclength(), bead_emphasis(m))
    dw = np.gradient(w, s)
    k = int(round(0.5 / (s[1] - s[0])))
    slopes, jumps = [], []
    for i0, i1, _ in runs(e, 0.15):
        idx = np.nonzero((s >= s[i0] - pad) & (s <= s[i1] + pad))[0]
        if len(idx) < 2 * k + 2:
            continue
        a = idx[k:-k]
        a = a[w[a] < 0.7 * w[idx].max()]
        if not len(a):
            continue
        slopes.append(float(np.max(np.abs(dw[a]))))
        jumps.append(float(np.max(np.abs(dw[a + k] - dw[a - k]))))
    if not slopes:
        return {}
    return {"slope_median": round(float(np.median(slopes)), 2), "slope_max": round(float(np.max(slopes)), 2),
            "break_median": round(float(np.median(jumps)), 2), "break_max": round(float(np.max(jumps)), 2)}


def ink_mm(sheet) -> float:
    return round(sum(float(np.sum(np.linalg.norm(np.diff(k.points, axis=0), axis=1))) for k in sheet.inks), 1)


def measure(name, sh, *, smooth=True):
    d = {**mass_shapes(sh), "ink_mm": ink_mm(sh), "paths": len(sh.inks)}
    if smooth:
        d.update(smoothness(sh))
    print(f"  {name:28s} {d}")
    return d


# ---------------------------------------------------------------------------
# 1 profiles
# ---------------------------------------------------------------------------

SW = {"id": "swell"}
PROFILE_ROWS = [
    ("p1-gather", "a  round 10: gather beads at the peak (reference: the bead meets the line)", GATHER),
    ("p2-bell", "b  bell: smootherstep up and down, 1 head diameter each side (the naive swell)",
     {**SW, "profile": "bell"}),
    ("p3-lens", "c  lens: slow thin tails both sides, a fast bloom into a round head", {**SW, "profile": "lens"}),
    ("p4-drop", "d  drop: a thin tail thickens INTO the head; the line exits thin", {**SW, "profile": "drop"}),
    ("p5-press", "e  press: the pen lands heavy and lifts away in a long tail", {**SW, "profile": "press"}),
    ("p6-turn", "f  turn: width follows the line's own curvature near the stress", {**SW, "profile": "turn"}),
    ("p7-momentum", "g  momentum: the mass overshoots along the incoming direction",
     {**SW, "profile": "momentum", "carry": 0.6}),
    ("p8-sag", "h  sag: the mass hangs below the line, a drop on a wire", {**SW, "profile": "sag", "sag": 1.1}),
    ("p9-necklace", "i  necklace: three lobes of falling size on smooth necks", {**SW, "profile": "necklace"}),
]


def stage_profiles():
    ims, num, recs = [], {}, {}
    for name, label, rnd in PROFILE_ROWS:
        sh, im = tile(name, {**BASE, "renderer": rnd}, label)
        num[name] = measure(name, sh)
        recs[name] = sh.recipe
        ims.append(im)
    sh = kit.run({**BASE, "renderer": SAUSAGE})
    num["p0-sausage-round9"] = measure("p0-sausage-round9", sh)
    NUM["profiles"] = num
    save(kit.contact(ims, 3, title="swelling into mass — one drift line (matisse > shikasta > lichtenberg, chain, "
                                   "seed 7000), the SAME segment stresses and head sizes; only the transition differs"),
         "profiles", results=True, recipes=recs)


# ---------------------------------------------------------------------------
# 2 close-up at 10 px/mm
# ---------------------------------------------------------------------------

def stage_closeup():
    from PIL import Image, ImageDraw  # noqa: PLC0415
    variants = [("gather (round 10)", GATHER), ("bell", {**SW, "profile": "bell"}),
                ("drop", {**SW, "profile": "drop"}), ("press", {**SW, "profile": "press"}),
                ("momentum", {**SW, "profile": "momentum", "carry": 0.6}),
                ("necklace", {**SW, "profile": "necklace"})]
    sheets = [(lab, kit.run({**BASE, "renderer": r})) for lab, r in variants]
    m = sheets[0][1].marks[0]
    st = sorted(m.meta["prosody"]["stresses"], key=lambda x: -(x[2] - x[0]))[:3]
    s = m.arclength()
    k = 10
    rows = []
    for lab, sh in sheets:
        im = kit.render_image(sh, px_per_mm=k, label=None)
        cells = []
        for a, lv, b in st:
            c = np.array([np.interp(a, s, m.points[:, 0]), np.interp(a, s, m.points[:, 1])])
            half = 18.0
            box = [int((c[0] - half) * k), int((c[1] - half * 0.75) * k), int((c[0] + half) * k),
                   int((c[1] + half * 0.75) * k)]
            pad = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (0xFF, 0xFC, 0xF0))
            pad.paste(im, (-box[0], -box[1]))
            cells.append(pad)
        cw, ch = cells[0].size
        row = Image.new("RGB", (cw * 3 + 230, ch), (0xFF, 0xFC, 0xF0))
        ImageDraw.Draw(row).text((10, ch // 2 - 10), lab, fill=(0x10, 0x0F, 0x0F), font=kit.core._font(20))
        for i, c in enumerate(cells):
            row.paste(c, (230 + cw * i, 0))
        rows.append(row)
    save(kit.contact(rows, 1, title="close up, 10 px/mm — the three LONGEST stresses, centred on the head; "
                                    "how the line goes into its mass"), "closeup", results=True, maxw=3000)


# ---------------------------------------------------------------------------
# 3 where smooth tips into sausage
# ---------------------------------------------------------------------------

def stage_threshold():
    from PIL import Image  # noqa: PLC0415
    num = {}
    rows = []
    for L in (0.35, 0.6, 1.0, 1.5, 2.2, 3.2):
        sh = kit.run({**BASE, "renderer": {**SW, "profile": "bell", "length": L}})
        num[f"bell length {L}"] = measure(f"bell length {L}", sh, smooth=False)
        rows.append((f"bell length {L} D", sh))
    for kh in (0.15, 0.3, 0.5, 0.75, 0.95):
        sh = kit.run({**BASE, "renderer": {**SW, "profile": "drop", "k_head": kh}})
        num[f"drop k_head {kh}"] = measure(f"drop k_head {kh}", sh, smooth=False)
        rows.append((f"drop k_head {kh}", sh))
    for tw in (1.0, 2.4, 3.6, 5.0):
        sh = kit.run({**BASE, "renderer": {**SW, "profile": "drop", "tail_w": tw}})
        num[f"drop tail_w {tw}"] = measure(f"drop tail_w {tw}", sh, smooth=False)
        rows.append((f"drop tail_w {tw} mm", sh))
    NUM["threshold"] = num
    # a strip: the longest stress under each setting
    m = rows[0][1].marks[0]
    st = sorted(m.meta["prosody"]["stresses"], key=lambda x: -(x[2] - x[0]))[0]
    s = m.arclength()
    c = np.array([np.interp(st[0], s, m.points[:, 0]), np.interp(st[0], s, m.points[:, 1])])
    k, half = 8, 20.0
    cells = []
    for lab, sh in rows:
        im = kit.render_image(sh, px_per_mm=k, label=None)
        box = [int((c[0] - half) * k), int((c[1] - half * 0.75) * k), int((c[0] + half) * k), int((c[1] + half * 0.75) * k)]
        pad = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (0xFF, 0xFC, 0xF0))
        pad.paste(im, (-box[0], -box[1]))
        mm = num[{"bell": f"bell length {lab.split()[2]}"}.get(lab.split()[0], "")] if False else None
        from PIL import ImageDraw  # noqa: PLC0415
        key = lab.replace(" D", "").replace(" mm", "")
        e = num[key]
        ImageDraw.Draw(pad).text((8, 8), f"{lab}   elong med {e.get('elong_median', '-')} / max {e.get('elong_max', '-')}",
                                 fill=(0x10, 0x0F, 0x0F), font=kit.core._font(15))
        cells.append(pad)
    save(kit.contact(cells, 5, title="where a smooth swell tips into a sausage — the longest stress under each "
                                     "setting; numbers over the whole line"), "threshold", results=True)


# ---------------------------------------------------------------------------
# 4 deliberate dots
# ---------------------------------------------------------------------------

def stage_dots():
    D = {"id": "swell_dots"}
    hand = lambda h, length=2.2, joins="smooth": {"id": "hand", "hand": h, "length": length, "joins": joins}  # noqa
    rows = [
        ("d1-inflection", "a  dots at the line's own inflections: loud L (ring), the rest s (disc) — roadrunner",
         {"seed": 7500, "voice": hand("mime_roadrunner"), "renderer": {**D, "rule": "inflection", "shape_L": "ring", "scale": 6.0, "gap": 12.0}}),
        ("d2-beat", "b  a metre: a dot every 16 mm, L s s (a waltz) — matisse",
         {"seed": 7501, "voice": hand("matisse"), "renderer": {**D, "rule": "beat", "period": 16.0, "sizes": "Lss"}}),
        ("d3-count", "c  counted: 1, 2, 3 dots at its strongest events — shikasta",
         {"seed": 7502, "voice": hand("shikasta"), "renderer": {**D, "rule": "count", "gap": 26.0}}),
        ("d4-decel", "d  a slowing pen: dots close up and grow toward each phrase end (hand switches) — drift",
         {"seed": 7000, "voice": {**V, "length": 2.4},
          "renderer": {**D, "rule": "decel", "size": 5.0, "decel_n": 7}}),
        ("d5-fullstop", "e  full stops: each phrase ends in a dot, the pen lifts, the line resumes — drift",
         {"seed": 7000, "voice": {**V, "length": 2.4}, "renderer": {**D, "rule": "fullstop", "size": 5.5}}),
        ("d6-pauses", "f  the hand's own pauses: Staccato dwell peaks, loud = split, quiet = small disc — drift",
         {"seed": 7003, "voice": {"id": "drift", "hands": ["hokusai", "meander69"], "length": 2.4},
          "modulators": [{"id": "timing", "tempo": "staccato"}],
          "renderer": {**D, "rule": "pauses", "shape_L": "split", "gap": 10.0, "size": 7.5}}),
        ("d7-wound", "g  wound dots: the line itself winds out and back in at its turns — meander69",
         {"seed": 7504, "voice": hand("meander69", 2.0, "chain"),
          "renderer": {**D, "rule": "turns", "shape_L": "wound", "shape_s": "wound", "gap": 22.0, "scale": 2.0}}),
        ("d8-commas", "h  commas: dots with tails at the inflections, L m s cycling — hokusai",
         {"seed": 7505, "voice": hand("hokusai"),
          "renderer": {**D, "rule": "inflection", "sizes": "Lms", "shape_L": "comma", "shape_s": "disc", "scale": 5.0, "gap": 12.0}}),
        ("d9-vocab", "i  the vocabulary in one line: beat L . s m . s, ring / split — marden",
         {"seed": 7506, "voice": hand("marden"),
          "renderer": {**D, "rule": "beat", "period": 11.0, "sizes": "L.sm.s", "shape_L": "ring", "shape_s": "split"}}),
    ]
    ims, num, recs = [], {}, {}
    for name, label, rec in rows:
        sh, im = tile(name, {"frame": [267, 180], **rec}, label)
        dots = sum(1 for k in sh.inks if k.meta.get("role", "").startswith("dot"))
        num[name] = {**measure(name, sh, smooth=False), "dot_paths": dots}
        recs[name] = sh.recipe
        ims.append(im)
    NUM["dots"] = num
    save(kit.contact(ims, 3, title="deliberate dots — each placed by a rule you can see, in a vocabulary of sizes "
                                   "(L m s) and shapes (disc, ring, split, comma, wound)"), "dots", results=True,
         recipes=recs)


# ---------------------------------------------------------------------------
# 5 bold gestures
# ---------------------------------------------------------------------------

def stage_bold():
    hand = lambda h, length, joins="smooth": {"id": "hand", "hand": h, "length": length, "joins": joins}  # noqa
    pros = lambda density=0.35, unit="pulse", gap=60.0: {"id": "prosody", "unit": unit, "span": 8.0,  # noqa
                                                          "density": density, "gap": gap, "primary": 0.5}
    rows = [
        ("b1-one-drop", "a  one gesture, the sheet: shikasta, two loud stresses, drop (head 22 mm), pen 0.6",
         {"seed": 7601, "voice": hand("shikasta", 0.9), "modulators": [pros(0.4)],
          "renderer": {"id": "swell", "profile": "drop", "size": 22.0, "pen": 0.6, "tail": 55.0, "tail_w": 2.6,
                       "k_head": 0.8}}),
        ("b2-thirds", "b  three gestures, a third of the page each: hokusai drop / roadrunner press / matisse momentum",
         {"seed": 7610, "arranger": {"id": "swell_place", "boxes": [0.0, 0.05, 0.42, 0.9, 0.3, 0.0, 0.42, 1.0,
                                                                    0.6, 0.05, 0.4, 0.9]},
          "parts": [{"voice": hand("hokusai", 0.8), "modulators": [pros(0.5)],
                     "renderer": {"id": "swell", "profile": "drop", "size": 16.0, "pen": 0.55, "tail": 40.0,
                                  "tail_w": 2.2}},
                    {"voice": hand("mime_roadrunner", 0.9), "modulators": [pros(0.5)],
                     "renderer": {"id": "swell", "profile": "press", "size": 15.0, "pen": 0.55, "tail": 45.0,
                                  "tail_w": 2.2}},
                    {"voice": hand("matisse", 0.8), "modulators": [pros(0.5)],
                     "renderer": {"id": "swell", "profile": "momentum", "size": 15.0, "pen": 0.55, "carry": 0.55,
                                  "tail": 35.0, "tail_w": 2.2}}]}),
        ("b3-press-sweep", "c  one long press: meander69 lands at its loudest turn and lifts across the sheet",
         {"seed": 7620, "voice": hand("meander69", 1.0, "chain"), "modulators": [pros(0.25, gap=90.0)],
          "renderer": {"id": "swell", "profile": "press", "size": 24.0, "pen": 0.7, "tail": 90.0, "tail_w": 3.0,
                       "k_head": 0.85}}),
        ("b4-turn-knots", "d  marden, large, the mass sits on its tightest turns (turn profile, 18 mm)",
         {"seed": 7630, "voice": hand("marden", 0.9), "modulators": [pros(0.35)],
          "renderer": {"id": "swell", "profile": "turn", "size": 18.0, "pen": 0.6, "tail": 30.0, "k_head": 0.85}}),
    ]
    ims, num, recs = [], {}, {}
    for name, label, rec in rows:
        sh, im = tile(name, {"frame": [267, 180], **rec}, label)
        num[name] = measure(name, sh)
        # the round-10 opening (1.6 mm) is fixed; at 15-24 mm heads a 3 mm tail survives it. Opening at
        # 0.2 x head size asks the same question at the gesture's own scale.
        sizes = [r["size"] for r in ([rec.get("renderer")] + [p.get("renderer") for p in rec.get("parts", [])])
                 if r and "size" in r]
        sc = mass_shapes(sh, open_mm=0.2 * min(sizes))
        num[name]["scaled_open_mm"] = round(0.2 * min(sizes), 1)
        num[name]["scaled"] = sc
        print(f"    scaled opening {0.2 * min(sizes):.1f} mm: {sc}")
        recs[name] = sh.recipe
        ims.append(im)
    NUM["bold"] = num
    save(kit.contact(ims, 2, title="bold gestures — few long marks, hairline to big mass and back"), "bold",
         results=True, recipes=recs)


# ---------------------------------------------------------------------------
# 6 combinations
# ---------------------------------------------------------------------------

def stage_combo():
    hand = lambda h, length, joins="smooth": {"id": "hand", "hand": h, "length": length, "joins": joins}  # noqa
    A = {"id": "dev_chorus", "answer_to": "all", "listen_by": "space", "radius": 14.0}
    pros = {"id": "prosody", "unit": "pulse", "span": 8.0, "density": 0.5, "gap": 40.0, "primary": 0.5}
    rows = [
        ("c1-one-swells", "a  two hands, one surface: roadrunner stays a dry line (black); shikasta swells "
                          "where roadrunner is silent (red)",
         {"seed": 7700, "arranger": {**A, "inks": "black,red"},
          "parts": [{"voice": hand("mime_roadrunner", 1.6), "modulators": [{**pros, "density": 0.6}],
                     "renderer": {"id": "wire", "pen": 0.4}},
                    {"voice": hand("shikasta", 1.2), "modulators": [pros],
                     "renderer": {"id": "swell", "profile": "drop", "size": 14.0, "pen": 0.5, "tail": 40.0,
                                  "tail_w": 2.2}}]}),
        ("c2-rosary-bold", "b  rosary redone: one bold line that swells (black); two ghost hands told only "
                           "in deliberate dots — meander69 on a metre in rings L s s (red), hokusai in commas L s (blue)",
         {"seed": 7710, "arranger": {"id": "swell_place", "inks": "black,red,blue",
                                     "boxes": [0.05, 0.0, 0.9, 1.0, 0.0, 0.05, 0.62, 0.9, 0.4, 0.05, 0.6, 0.9]},
          "parts": [{"voice": hand("mime_roadrunner", 1.0), "modulators": [{**pros, "density": 0.3, "gap": 70.0}],
                     "renderer": {"id": "swell", "profile": "drop", "size": 18.0, "pen": 0.6, "tail": 50.0,
                                  "tail_w": 2.4}},
                    {"voice": hand("meander69", 1.4, "chain"),
                     "renderer": {"id": "swell_dots", "rule": "beat", "period": 13.0, "sizes": "Lss", "line": "none",
                                  "shape_L": "ring", "shape_s": "disc", "size": 6.0, "pen": 0.4}},
                    {"voice": hand("hokusai", 1.2),
                     "renderer": {"id": "swell_dots", "rule": "beat", "period": 15.0, "sizes": "Ls", "line": "none",
                                  "shape_L": "comma", "shape_s": "disc", "size": 5.5, "pen": 0.4}}]}),
        ("c3-sentence", "c  a sentence: the drift writes in phrases ended by full stops (ring), and swells "
                        "(drop) inside them",
         {"seed": 7000, "voice": {**V, "length": 2.6}, "modulators": [{**SEG, "density": 0.5, "gap": 35.0}],
          "renderer": {"id": "swell_dots", "rule": "fullstop", "line": "swell", "shape_L": "ring", "size": 6.5,
                       "swell_size": 8.0, "space": 9.0}}),
    ]
    ims, num, recs = [], {}, {}
    for name, label, rec in rows:
        sh, im = tile(name, {"frame": [267, 180], **rec}, label, colour=True)
        num[name] = measure(name, sh, smooth=False)
        recs[name] = sh.recipe
        ims.append(im)
        ims.append(kit.render_image(sh, px_per_mm=4.0, label=label.split(":")[0] + " — one pen"))
    NUM["combo"] = num
    save(kit.contact(ims, 2, title="combinations — colour (left) and one pen (right)"), "combo", results=True,
         recipes=recs)


def stage_dotshapes():
    """The dot vocabulary at 10 px/mm: each shape, large and small, on the same line."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    rows = []
    base = {"frame": [267, 180], "seed": 7501, "voice": {"id": "hand", "hand": "matisse", "length": 2.2}}
    for shp in ("disc", "ring", "split", "comma", "wound"):
        rec = {**base, "renderer": {"id": "swell_dots", "rule": "beat", "period": 19.0, "sizes": "Ls",
                                    "shape_L": shp, "shape_s": shp, "size": 7.0, "small": 0.5}}
        sh, _ = tile(f"s-{shp}", rec, f"dot shape: {shp}")
        m = sh.marks[0]
        sm = m.arclength()
        c = np.array([np.interp(0.5 * sm[-1], sm, m.points[:, 0]), np.interp(0.5 * sm[-1], sm, m.points[:, 1])])
        k, hw, hh = 10, 45.0, 20.0
        im = kit.render_image(sh, px_per_mm=k, label=None)
        box = [int((c[0] - hw) * k), int((c[1] - hh) * k), int((c[0] + hw) * k), int((c[1] + hh) * k)]
        pad = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (0xFF, 0xFC, 0xF0))
        pad.paste(im, (-box[0], -box[1]))
        ImageDraw.Draw(pad).text((10, 8), shp, fill=(0x10, 0x0F, 0x0F), font=kit.core._font(22))
        rows.append(pad)
    save(kit.contact(rows, 1, title="the dot vocabulary, 10 px/mm — L and s alternating on a metre (matisse); "
                                    "every fill is one spiral or inset path"), "dotshapes", results=True, maxw=2000)


STAGES = {"profiles": stage_profiles, "closeup": stage_closeup, "threshold": stage_threshold, "dots": stage_dots,
          "bold": stage_bold, "combo": stage_combo, "dotshapes": stage_dotshapes}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    todo = sys.argv[1:] or list(STAGES)
    p = OUT / "numbers.json"
    if p.exists():
        NUM.update(json.loads(p.read_text()))
    for st in todo:
        print(f"== {st}")
        STAGES[st]()
        p.write_text(json.dumps(NUM, indent=1))
