"""Round 10 — developments from Ian's round-9 notes (thread `developments`).

    .local/gesture/.venv/bin/python -m tools.gesture.experiments.developments [stage ...]

Stages (default: all):
  beads    beads, not sausages: round stress shapes on the SAME line and stresses
  rare     rare machine events: none … round-9 handover density, on the saved kit-demo-2 method
  chorus   call and response, mixed: 2–4 voices, inks, beads answering lines
  corpus   corpus favourites forward (roadrunner, meander69 chain, shikasta, the one-surface sheet)
  rosary   the risk: ghost voices — hands that speak only in beads around one visible line
  check    the open question: shikasta nib rows of polyphonic P1, enlarged (legibility check)
Every tile is `kit.run` + `kit.preview` (recipe JSON beside it in
.local/gesture/out/developments/); multi-ink tiles also get a `-colour.jpg`
(dev_chorus.render_colour). Sheets go to tools/gesture/results/developments-*.jpg;
numbers to stdout and .local/gesture/out/developments/numbers.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit.core import Sheet  # noqa: E402
from gesture.kit.dev_chorus import render_colour  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/developments"
RES = HERE / "results"
NUM: dict = {}

ROUTE = ["matisse", "shikasta", "lichtenberg"]
V = {"id": "drift_tokens", "hands": ROUTE, "joins": "chain", "length": 3.0}
SEG = {"id": "prosody", "unit": "segment", "span": 8.0}
PULSE = {"id": "prosody", "unit": "pulse", "span": 5.0}
NIB = {"id": "nib", "style": "e", "pen": 0.4}
FAV = ["mime_roadrunner", "shikasta", "meander69"]


def tile(name: str, recipe: dict, label: str, *, colour: bool = False, px: float = 4.0):
    sheet = kit.run({"label": label, **recipe})
    kit.preview(sheet, OUT / f"{name}.jpg", px_per_mm=6, label=label)
    if colour:
        render_colour(sheet, px_per_mm=6, label=label).save(OUT / f"{name}-colour.jpg", quality=88)
        return sheet, render_colour(sheet, px_per_mm=px, label=label)
    return sheet, kit.render_image(sheet, px_per_mm=px, label=label)


def save(img, name: str, maxw: int = 2400):
    if img.width > maxw:
        img = img.resize((maxw, int(img.height * maxw / img.width)))
    p = RES / f"developments-{name}.jpg"
    q = 85
    while True:
        img.save(p, quality=q, optimize=True)
        if p.stat().st_size < 1_000_000 or q <= 40:
            break
        q -= 7
    print("  ->", p.relative_to(ROOT), f"{p.stat().st_size / 1e3:.0f} kB")


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def mass_shapes(sheet, px: float = 6.0, open_mm: float = 1.6) -> dict:
    """Masses as the eye sees them, for ANY renderer: rasterise the inks,
    open with a disc of radius `open_mm` (lines and nib strokes vanish, masses
    ≥ 2·open_mm stay), label the blobs; elongation = √(λmax/λmin) of each
    blob's pixel covariance (a disc 1, a 3:1 capsule ≈ 2.6), length = its
    longest extent. Beads ≈ 1, sausages ≫ 1."""
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
            "elong_max": round(float(el.max()), 2), "share_round(<1.5)": round(float(np.mean(el < 1.5)), 2),
            "longest_mm": round(float(max(ln)), 1)}


def ink_mm(sheet) -> float:
    return round(sum(float(np.sum(np.linalg.norm(np.diff(k.points, axis=0), axis=1))) for k in sheet.inks), 1)


# ---------------------------------------------------------------------------
# 1 beads
# ---------------------------------------------------------------------------

def stage_beads():
    base = {"frame": [267, 180], "seed": 7000, "voice": V}
    B = {"id": "dev_beads", "line": "nib"}
    rows = [
        ("b1-ref-segment-nibe", "a  round 9 (d): segment stresses, nib e — the 'sausages' (reference)", [SEG], NIB),
        ("b2-ref-pulse-nibe", "b  round 9 (c): pulse stresses, nib e — kept (reference)", [PULSE], NIB),
        ("b3-string", "c  same segment stresses -> string of beads (biggest mid-stretch)", [SEG],
         {**B, "shape": "string"}),
        ("b4-gather-peak", "d  -> gather: one round mass at the stretch's peak", [SEG], {**B, "shape": "gather"}),
        ("b5-gather-low", "e  -> gather at the LOWEST point: ink runs downhill and pools", [SEG],
         {**B, "shape": "gather", "at": "low"}),
        ("b6-pool", "f  -> pool: the line swells into a drop at the stretch end", [SEG], {**B, "shape": "pool"}),
        ("b7-cluster", "g  -> cluster: touching beads, a knot of grapes", [SEG], {**B, "shape": "cluster"}),
        ("b8-knot", "h  -> knot: the line itself ties loops at each stress (wire, no fill)", [SEG],
         {**B, "shape": "knot", "line": "wire"}),
        ("b9-syncopated-gather", "i  round 9 (f) syncopated, the sausagiest -> gather at the event",
         [{**SEG, "rhythm": "syncopated"}], {**B, "shape": "gather", "at": "event"}),
    ]
    ims, num = [], {}
    for name, label, mods, rnd in rows:
        sh, im = tile(name, {**base, "modulators": mods, "renderer": rnd}, label)
        num[name] = {**mass_shapes(sh), "ink_mm": ink_mm(sh)}
        print(f"  {name:24s} {num[name]}")
        ims.append(im)
    # extra: Staccato timing (kept) feeding beads — timing has no emphasis; dev_beads reads r−1
    sh, im = tile("b10-staccato-cluster", {**base, "voice": {**V, "id": "drift"},
                                           "modulators": [{"id": "timing", "tempo": "staccato"}],
                                           "renderer": {**B, "shape": "cluster", "size": 5.0}},
                  "j  Staccato timing (kept) -> its pools as clusters")
    num["b10-staccato-cluster"] = {**mass_shapes(sh), "ink_mm": ink_mm(sh)}
    print(f"  {'b10-staccato-cluster':24s} {num['b10-staccato-cluster']}")
    NUM["beads"] = num
    save(kit.contact(ims, 3, title="beads, not sausages — one drift line (matisse > shikasta > lichtenberg, chain, "
                                   "seed 7000), the SAME prosody stresses, round shapes at any stress length"),
         "beads")
    zoom_beads()


def zoom_beads():
    """Crops of three stresses at 12 px/mm: sausage vs gather vs cluster vs knot."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    base = {"frame": [267, 180], "seed": 7000, "voice": V, "modulators": [SEG]}
    variants = [("sausage (round 9)", NIB), ("gather", {"id": "dev_beads", "line": "nib", "shape": "gather"}),
                ("cluster", {"id": "dev_beads", "line": "nib", "shape": "cluster"}),
                ("pool", {"id": "dev_beads", "line": "nib", "shape": "pool"}),
                ("knot", {"id": "dev_beads", "line": "wire", "shape": "knot"})]
    sheets = [(lab, kit.run({**base, "renderer": r})) for lab, r in variants]
    m = sheets[0][1].marks[0]
    st = sorted(m.meta["prosody"]["stresses"], key=lambda x: -(x[2] - x[0]))[:3]
    s = m.arclength()
    k = 12
    rows = []
    for lab, sh in sheets:
        im = kit.render_image(sh, px_per_mm=k, label=None)
        cells = []
        for a, lv, b in st:
            c = np.array([np.interp(0.5 * (a + b), s, m.points[:, 0]), np.interp(0.5 * (a + b), s, m.points[:, 1])])
            half = 16.0
            box = [int((c[0] - half) * k), int((c[1] - half * 0.75) * k), int((c[0] + half) * k),
                   int((c[1] + half * 0.75) * k)]
            pad = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (0xFF, 0xFC, 0xF0))
            pad.paste(im, (-box[0], -box[1]))
            cells.append(pad.resize((480, 360)))
        row = Image.new("RGB", (480 * 3 + 200, 360), (0xFF, 0xFC, 0xF0))
        ImageDraw.Draw(row).text((10, 170), lab, fill=(0x10, 0x0F, 0x0F), font=kit.core._font(20))
        for i, c in enumerate(cells):
            row.paste(c, (200 + 480 * i, 0))
        rows.append(row)
    save(kit.contact(rows, 1, title="beads close up — the three LONGEST stresses of the line (12 px/mm), five "
                                    "ways of giving them weight"), "beads-closeup")


# ---------------------------------------------------------------------------
# 2 rare machine events
# ---------------------------------------------------------------------------

def stage_rare():
    base = {"frame": [267, 180], "seed": 7000,
            "renderer": {"id": "dev_beads", "shape": "gather", "line": "wire", "size": 6.0}}
    D = V
    T = PULSE
    R = {"id": "dev_rare_machine", "stretch": 18.0, "unit": 2.2}
    rows = [
        ("r1-none", "a  events 0 — the drift line, pulse prosody as round beads", []),
        ("r2-one-salient", "b  1 stair event at the line's loudest moment", [{**R, "events": 1}]),
        ("r3-one-switch", "c  1 stair event at the most decisive hand change", [{**R, "events": 1, "place": "switch"}]),
        ("r4-one-quiet", "d  1 stair event filling the calmest stretch", [{**R, "events": 1, "place": "quiet"}]),
        ("r5-two-salient", "e  2 events, 2 loudest moments, >= 60 mm apart", [{**R, "events": 2}]),
        ("r6-one-ruler", "f  1 event, ruler instead of stair (corner ticks)",
         [{**R, "events": 1, "grammar": "ruler", "unit": 3.0, "stretch": 22.0}]),
        ("r7-four", "g  4 events (getting systematic)", [{**R, "events": 4, "min_gap": 30.0}]),
        ("r8-round9", "h  round-9 handover density: 40 % of the line, stair, at seams",
         [{"id": "handover", "a": "stair", "b": "none", "at": "seams", "share": 0.4, "stretch": 16.0,
           "unit": 1.8}]),
        ("r9-long-stair", "i  1 long event (40 mm) at the loudest moment, coarse stair",
         [{**R, "events": 1, "stretch": 40.0, "unit": 3.5}]),
        ("r10-compass-quiet", "j  1.5 events (seeded: here 2), compass k=3, in the quiet stretches",
         [{**R, "events": 1.5, "grammar": "compass", "k": 3, "place": "quiet", "unit": 3.0}]),
    ]
    ims, num = [], {}
    for name, label, mods in rows:
        sh, im = tile(name, {**base, "voice": D, "modulators": mods + [T]}, label)
        m = sh.marks[0]
        mach = m.channel("machine")
        share = float(np.mean(mach > 0)) if mach is not None else 0.0
        num[name] = {"machine_share": round(share, 3),
                     "events": (m.meta.get("rare_machine") or {}).get("events", len(m.meta.get("handover", [])))}
        print(f"  {name:20s} {num[name]}")
        ims.append(im)
    NUM["rare"] = num
    save(kit.contact(ims[:9], 3, title="rare machine events — the hand lends the pen once or twice, at a meaningful "
                                       "spot; 0 events … the round-9 handover density (h). The machine speaks first, "
                                       "so prosody hears its edges as hand changes and may answer with a bead"),
         "rare")
    zoom_rare()


def zoom_rare():
    """Close-ups (10 px/mm) around each machine event of b, c, d, f, i."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    cells = []
    for name in ("r2-one-salient", "r3-one-switch", "r4-one-quiet", "r6-one-ruler", "r9-long-stair",
                 "r10-compass-quiet"):
        rec = json.loads((OUT / f"{name}.recipe.json").read_text())
        sh = kit.run(rec)
        m = sh.marks[0]
        mach = m["machine"] > 0
        if not mach.any():
            continue
        idx = np.flatnonzero(mach)
        c = m.points[idx[len(idx) // 2]]
        k = 10
        im = kit.render_image(sh, px_per_mm=k, label=None)
        half = 22.0
        box = [int((c[0] - half) * k), int((c[1] - half * 0.7) * k), int((c[0] + half) * k), int((c[1] + half * 0.7) * k)]
        pad = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (0xFF, 0xFC, 0xF0))
        pad.paste(im, (-box[0], -box[1]))
        lab = Image.new("RGB", (pad.width, 34), (0xFF, 0xFC, 0xF0))
        ImageDraw.Draw(lab).text((8, 8), rec.get("label", name)[:70], fill=(0x10, 0x0F, 0x0F), font=kit.core._font(16))
        t = Image.new("RGB", (pad.width, pad.height + 34), (0xFF, 0xFC, 0xF0))
        t.paste(pad, (0, 0))
        t.paste(lab, (0, pad.height))
        cells.append(t)
    save(kit.contact(cells, 3, title="rare machine events, close up (10 px/mm): the hand hands over and takes back"),
         "rare-closeup")


# ---------------------------------------------------------------------------
# 3 chorus
# ---------------------------------------------------------------------------

LEAD = {"label": "leader: drift, pulse, nib e masses", "voice": V, "modulators": [PULSE], "renderer": NIB}
F_RESTATE = {"label": "bubble > hokusai, restated + bound",
             "voice": {**V, "hands": ["bubble", "hokusai"]}, "modulators": [SEG],
             "renderer": {"id": "restate", "copies": 8, "bound": "contour"}}
F_BEADS = {"label": "meander69 chain, clusters",
           "voice": {"id": "hand", "hand": "meander69", "length": 3.0, "joins": "chain"},
           "modulators": [{**SEG, "density": 1.5}],
           "renderer": {"id": "dev_beads", "shape": "cluster", "pen": 0.35, "size": 6.0}}
F_GHOST = {"label": "shikasta ghost: beads only",
           "voice": {"id": "hand", "hand": "shikasta", "length": 3.0},
           "modulators": [{**PULSE, "density": 2.0, "gap": 12.0, "primary": 0.6}],
           "renderer": {"id": "dev_beads", "shape": "gather", "line": "none", "size": 6.0, "pen": 0.35}}


def chorus_stats(sh) -> dict:
    from scipy.spatial import cKDTree  # noqa: PLC0415
    marks = sh.marks
    parts = sorted({m.meta["part"] for m in marks})
    st = {p: sum(len(m.meta.get("prosody", {}).get("stresses", [])) for m in marks if m.meta["part"] == p)
          for p in parts}
    # clash: share of loud points of part p within 10 mm of a loud point of another part
    loud = {p: np.vstack([m.points[m.channel("emphasis", 0.0) > 0.5] for m in marks if m.meta["part"] == p]
                         or [np.zeros((0, 2))]) for p in parts}
    clash = {}
    for p in parts:
        others = [loud[q] for q in parts if q != p and len(loud[q])]
        if not len(loud[p]) or not others:
            clash[p] = None
            continue
        t = cKDTree(np.vstack(others))
        d, _ = t.query(loud[p])
        clash[p] = round(float(np.mean(d < 10.0)), 3)
    return {"stresses": st, "clash_10mm": clash}


def stage_chorus():
    base = {"frame": [267, 180], "seed": 7100}
    A = {"id": "dev_chorus", "listen_by": "space", "radius": 15.0}
    rows = [
        ("c1-two-indep", "a  two voices, no listening: leader nib masses (black) x restated follower (red)",
         {**A, "answer_to": "none", "inks": "black,red"}, [LEAD, F_RESTATE]),
        ("c2-two-answer", "b  two voices, the follower answers in line where the leader is silent (round-9 g, mixed)",
         {**A, "answer_to": "previous", "inks": "black,red"}, [LEAD, F_RESTATE]),
        ("c3-three-chain", "c  three: restated answers leader, clusters (blue) answer the restated",
         {**A, "answer_to": "previous", "inks": "black,red,blue"}, [LEAD, F_RESTATE, F_BEADS]),
        ("c4-three-all", "d  three, each speaks only where EVERY earlier voice is silent",
         {**A, "answer_to": "all", "inks": "black,red,blue"}, [LEAD, F_RESTATE, F_BEADS]),
        ("c5-four-ghost", "e  four: + a shikasta ghost (cyan) whose line is never drawn — beads answering lines",
         {**A, "answer_to": "all", "inks": "black,red,blue,cyan"}, [LEAD, F_RESTATE, F_BEADS, F_GHOST]),
        ("c6-four-leader", "f  four, everyone answers the leader only (followers may collide with each other)",
         {**A, "answer_to": "leader", "inks": "black,red,blue,cyan"}, [LEAD, F_RESTATE, F_BEADS, F_GHOST]),
        ("c7-inverse", "g  inverted: clusters lead (blue), the drift answers as a dry line with knots (black)",
         {**A, "answer_to": "all", "inks": "blue,black,red"},
         [F_BEADS, {**LEAD, "label": "drift, knots", "modulators": [SEG],
                    "renderer": {"id": "dev_beads", "shape": "knot", "line": "wire"}}, F_RESTATE]),
        ("c8-time", "h  four voices listening in TIME (as if drawn at once), not space",
         {**A, "answer_to": "all", "listen_by": "time", "inks": "black,red,blue,cyan"},
         [LEAD, F_RESTATE, F_BEADS, F_GHOST]),
    ]
    ims, num = [], {}
    for name, label, arr, parts in rows:
        sh, im = tile(name, {**base, "arranger": arr, "parts": parts}, label, colour=True)
        num[name] = chorus_stats(sh)
        print(f"  {name:18s} {num[name]}")
        ims.append(im)
    NUM["chorus"] = num
    save(kit.contact(ims, 2, title="chorus — call and response mixed: one ink and one weight per voice "
                                   "(leader matisse > shikasta > lichtenberg, seed 7100)"), "chorus")


# ---------------------------------------------------------------------------
# 4 corpus favourites
# ---------------------------------------------------------------------------

MANTIS = {"voice": {"id": "dance", "trail": "mantis", "effectors": "all", "seconds": 12.0},
          "modulators": [{"id": "own_tempo"}],
          "renderer": {"id": "dev_beads", "shape": "gather", "line": "nib", "nib_cap": 1.0, "size": 4.5,
                       "pen": 0.35}}


def stage_corpus():
    ims, num = [], {}
    none = {"id": "dev_chorus", "answer_to": "none"}
    rows = [
        ("k1-surface-v2", "a  one surface v2: mantis dance itself, its pauses as beads (black) x roadrunner wire (blue) x meander69 "
                          "chain wire (red) — the favourites in place of polygon_walk / aaron",
         {"seed": 7300, "arranger": {**none, "inks": "black,blue,red"},
          "parts": [MANTIS, {"voice": {"id": "hand", "hand": "mime_roadrunner", "length": 4.0},
                             "renderer": {"id": "wire", "pen": 0.3}},
                    {"voice": {"id": "hand", "hand": "meander69", "length": 4.0, "joins": "chain"},
                     "renderer": {"id": "wire", "pen": 0.3}}]}, True),
        ("k2-fav-drift-staccato", "b  one line through the favourites: roadrunner > shikasta > meander69, chain, "
                                  "danced by Staccato, nib e (kit demo 2's method)",
         {"seed": 7000, "voice": {"id": "drift", "hands": FAV, "joins": "chain", "length": 4.0},
          "modulators": [{"id": "timing", "tempo": "staccato"}], "renderer": NIB}, False),
        ("k3-fav-drift-beads-stair", "c  the same route, pulse prosody as clusters + one rare stair at the "
                                     "decisive hand change",
         {"seed": 7000, "voice": {"id": "drift_tokens", "hands": FAV, "joins": "chain", "length": 4.0},
          "modulators": [{"id": "dev_rare_machine", "events": 1, "place": "switch"}, PULSE],
          "renderer": {"id": "dev_beads", "shape": "cluster", "line": "nib", "size": 7.0}}, False),
        ("k4-shikasta-x-roadrunner", "d  two voices one surface (kit demo 4's method): shikasta nib c (black) x "
                                     "roadrunner dry wire (red)",
         {"seed": 7301, "arranger": {**none, "inks": "black,red"},
          "parts": [{"voice": {"id": "hand", "hand": "shikasta", "length": 4.0},
                     "modulators": [{"id": "constant", "r": 1.0, "W": 1.8}],
                     "renderer": {"id": "nib", "style": "c", "pen": 0.35}},
                    {"voice": {"id": "hand", "hand": "mime_roadrunner", "length": 5.0, "joins": "chain"},
                     "renderer": {"id": "wire", "pen": 0.25}}]}, True),
        ("k5-mantis-shikasta-meander", "e  mantis dance (black) x shikasta nib c (cyan) x meander69 chain wire (red)",
         {"seed": 7302, "arranger": {**none, "inks": "black,cyan,red"},
          "parts": [MANTIS, {"voice": {"id": "hand", "hand": "shikasta", "length": 3.0},
                             "modulators": [{"id": "constant", "r": 1.0, "W": 1.6}],
                             "renderer": {"id": "nib", "style": "c", "pen": 0.35}},
                    {"voice": {"id": "hand", "hand": "meander69", "length": 4.0, "joins": "chain"},
                     "renderer": {"id": "wire", "pen": 0.3}}]}, True),
        ("k6-meander-rare", "f  meander69 chain (5 R) — a machine-like hand — with one coarse stair in its "
                            "calmest stretch, beads where it corners",
         {"seed": 7001, "voice": {"id": "hand", "hand": "meander69", "length": 5.0, "joins": "chain"},
          "modulators": [{"id": "dev_rare_machine", "events": 1, "place": "quiet", "unit": 3.0, "stretch": 30.0},
                         {**PULSE, "listen": "corner", "density": 0.6}],
          "renderer": {"id": "dev_beads", "shape": "gather", "size": 4.0, "pen": 0.35}}, False),
    ]
    for name, label, rec, col in rows:
        sh, im = tile(name, {"frame": [267, 180], **rec}, label, colour=col)
        num[name] = {"marks": len(sh.marks), "inks": len(sh.inks), "ink_mm": ink_mm(sh), **mass_shapes(sh)}
        print(f"  {name:28s} {num[name]}")
        ims.append(im)
    NUM["corpus"] = num
    save(kit.contact(ims, 2, title="corpus favourites forward — roadrunner, meander69 chain, shikasta, the "
                                   "mantis one-surface sheet, recombined"), "corpus")


# ---------------------------------------------------------------------------
# 5 the risk: rosary — ghost voices
# ---------------------------------------------------------------------------

def ghost(hand, shape, extra=None, length=3.0, joins="smooth", density=1.6):
    return {"label": f"{hand} ghost ({shape})", "voice": {"id": "hand", "hand": hand, "length": length,
                                                          "joins": joins},
            "modulators": [{**PULSE, "density": density, "gap": 14.0, "primary": 0.6}],
            "renderer": {"id": "dev_beads", "shape": shape, "line": "none", "pen": 0.35, "size": 5.0,
                         **(extra or {})}}


def stage_rosary():
    A = {"id": "dev_chorus", "answer_to": "all", "listen_by": "space", "radius": 12.0}
    line = {"label": "roadrunner, the one visible line", "voice": {"id": "hand", "hand": "mime_roadrunner",
                                                                   "length": 5.0},
            "modulators": [{**PULSE, "density": 0.4}], "renderer": {"id": "wire", "pen": 0.35}}
    g1 = ghost("shikasta", "gather")
    g2 = ghost("meander69", "cluster", joins="chain")
    g3 = ghost("mime_mantis", "string", {"size": 6.0})
    chain = lambda hand, joins="smooth": {  # noqa: E731
        "label": f"{hand} ghost, bead chains", "voice": {"id": "hand", "hand": hand, "length": 3.0, "joins": joins},
        "modulators": [{**SEG, "density": 1.2, "gap": 18.0, "span": 14.0, "primary": 0.5}],
        "renderer": {"id": "dev_beads", "shape": "string", "line": "none", "pen": 0.35, "size": 4.5,
                     "spacing": 1.7, "length_gain": 0.0}}
    rows = [
        ("x1-rosary", "a  rosary: one visible line (roadrunner, black) + three hands that speak only in beads "
                      "(shikasta red, meander69 blue, mantis mime cyan), each where the others are silent",
         {"seed": 7400, "arranger": {**A, "inks": "black,red,blue,cyan"}, "parts": [line, g1, g2, g3]}),
        ("x2-rosary-mono", "b  the same, one pen",
         {"seed": 7400, "arranger": {**A, "inks": "black"}, "parts": [line, g1, g2, g3]}),
        ("x3-constellation", "c  no visible line at all: four ghost hands, beads only — the line is inferred",
         {"seed": 7401, "arranger": {**A, "inks": "black,red,blue,cyan"},
          "parts": [ghost("mime_roadrunner", "gather", {"size": 6.0}, length=5.0), g1, g2, g3]}),
        ("x4-knotted-line", "d  the visible line knots itself at its own stresses; the ghosts answer around it",
         {"seed": 7400, "arranger": {**A, "inks": "black,red,blue,cyan"},
          "parts": [{**line, "modulators": [{**PULSE, "density": 0.8}],
                     "renderer": {"id": "dev_beads", "shape": "knot", "line": "wire", "size": 6.0}},
                    g1, g2, g3]}),
        ("x5-bead-chains", "e  rosary proper: the ghosts tell long stretches of their course as chains of beads "
                           "(segment stresses, string) — dotted hands around one line",
         {"seed": 7402, "arranger": {**A, "inks": "black,red,blue"},
          "parts": [line, chain("shikasta"), chain("meander69", "chain")]}),
        ("x6-bead-chains-mono", "f  e, one pen",
         {"seed": 7402, "arranger": {**A, "inks": "black"},
          "parts": [line, chain("shikasta"), chain("meander69", "chain")]}),
    ]
    ims, num = [], {}
    for name, label, rec in rows:
        sh, im = tile(name, {"frame": [267, 180], **rec}, label, colour=True)
        beads = sum(1 for k in sh.inks if k.filled)
        num[name] = {"beads": beads, "ink_mm": ink_mm(sh), **chorus_stats(sh)}
        print(f"  {name:18s} {num[name]}")
        ims.append(im)
    NUM["rosary"] = num
    save(kit.contact(ims, 2, title="the risk — rosary: hands whose lines are never drawn, heard only as beads "
                                   "around (or without) one visible line"), "rosary")


# ---------------------------------------------------------------------------
# 6 the check: shikasta nib rows of P1, enlarged
# ---------------------------------------------------------------------------

def stage_check():
    from PIL import Image, ImageDraw  # noqa: PLC0415
    src = ROOT / ".local/gesture/out/polyphonic_sheets/page-P1-interlinear.recipe.json"
    rec = json.loads(src.read_text())
    sh = kit.run(rec)
    kit.preview(sh, OUT / "check-P1-full.jpg", px_per_mm=6, label="P1 (round 9), re-run from its recipe")
    body = [k for k in sh.inks if k.meta.get("part") == 0]
    # rows: cluster ink centres in y
    yc = np.array([float(np.mean(k.points[:, 1])) for k in body])
    order = np.argsort(yc)
    rows, cur = [], [order[0]]
    for a, b in zip(order[:-1], order[1:]):
        if yc[b] - yc[a] > 4.0:
            rows.append(cur)
            cur = []
        cur.append(b)
    rows.append(cur)
    rows = [r for r in rows if len(r) >= 4]
    k_px = 10
    strips = []
    W = sh.frame[0]
    for ri, r in enumerate(rows):
        inks = [body[i] for i in r]
        pts = np.vstack([k.points for k in inks])
        y0, y1 = pts[:, 1].min() - 2.0, pts[:, 1].max() + 2.0
        sub = Sheet(sh.frame, [], inks, sh.meta)
        im = kit.render_image(sub, px_per_mm=k_px, label=None)
        crop = Image.new("RGB", (int(W * k_px), int((y1 - y0) * k_px)), (0xFF, 0xFC, 0xF0))
        crop.paste(im, (0, -int(y0 * k_px)))
        half = crop.width // 2
        for hi, part in enumerate((crop.crop((0, 0, half, crop.height)), crop.crop((half, 0, crop.width,
                                                                                    crop.height)))):
            lab = Image.new("RGB", (part.width, 30), (0xFF, 0xFC, 0xF0))
            ImageDraw.Draw(lab).text((8, 6), f"row {ri + 1}, {'left' if hi == 0 else 'right'} half  "
                                              f"(shikasta hand, nib c, W 1.4 mm; 10 px/mm)",
                                     fill=(0x6F, 0x6E, 0x69), font=kit.core._font(16))
            t = Image.new("RGB", (part.width, part.height + 30), (0xFF, 0xFC, 0xF0))
            t.paste(lab, (0, 0))
            t.paste(part, (0, 30))
            strips.append(t)
    NUM["check"] = {"rows": len(rows), "inks": len(body)}
    print(f"  check: {len(rows)} shikasta rows, {len(body)} inks")
    head = Image.new("RGB", (strips[0].width, 70), (0xFF, 0xFC, 0xF0))
    ImageDraw.Draw(head).text((8, 8), "Question for Ian: does any row come too close to legible Arabic?",
                              fill=(0xAF, 0x30, 0x29), font=kit.core._font(22))
    ImageDraw.Draw(head).text((8, 40), "Line studies after the shikasta hand (generative library entry); "
                                       "not meant to be read; nothing was done to make them legible.",
                              fill=(0x6F, 0x6E, 0x69), font=kit.core._font(16))
    sheet_im = kit.contact([head] + strips, 1, title="CHECK, not a study: polyphonic P1, shikasta nib rows alone, "
                                                     "enlarged")
    save(sheet_im, "check-shikasta-rows", maxw=1400)


STAGES = {"beads": stage_beads, "rare": stage_rare, "chorus": stage_chorus, "corpus": stage_corpus,
          "rosary": stage_rosary, "check": stage_check}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    todo = sys.argv[1:] or list(STAGES)
    for st in todo:
        print(f"== {st}")
        STAGES[st]()
    p = OUT / "numbers.json"
    old = json.loads(p.read_text()) if p.exists() else {}
    old.update(NUM)
    p.write_text(json.dumps(old, indent=1, default=str))
