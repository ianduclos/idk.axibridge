"""Round 9 — prosody and accumulation (thread `prosody_accumulation`).

    .local/gesture/.venv/bin/python -m tools.gesture.experiments.prosody_accumulation [stage ...]

Stages (default: all):
  field     field / timing vs prosody rhythms on ONE drift line (nib e)
  solid     solid regime masses vs line-built accumulation on the same stresses
  sign      the sign threshold: restatement count sweep, coverage + legibility
  duet      the limb — call and response between two voices
Every tile is `kit.run` + `kit.preview` (recipe JSON beside it in
.local/gesture/out/prosody_accumulation/); the sheets go to
tools/gesture/results/prosody_accumulation-*.jpg; numbers to stdout and
.local/gesture/out/prosody_accumulation/numbers.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit.prosody_modulators import STEP, line_events  # noqa: E402
from gesture.kit.prosody_renderers import stretches  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/prosody_accumulation"
RES = HERE / "results"
NUM: dict = {}

ROUTE = ["matisse", "shikasta", "lichtenberg"]
V = {"id": "drift_tokens", "hands": ROUTE, "joins": "chain", "length": 3.0}
PROS = {"id": "prosody", "unit": "segment", "span": 8.0}
NIB = {"id": "nib", "style": "e", "pen": 0.4}


def tile(name: str, recipe: dict, label: str, px: float = 4.0):
    sheet = kit.run(recipe)
    kit.preview(sheet, OUT / f"{name}.jpg", px_per_mm=6, label=label)
    return sheet, kit.render_image(sheet, px_per_mm=px, label=label)


def save(img, name: str, maxw: int = 2400):
    if img.width > maxw:
        img = img.resize((maxw, int(img.height * maxw / img.width)))
    p = RES / f"prosody_accumulation-{name}.jpg"
    q = 85
    while True:
        img.save(p, quality=q, optimize=True)
        if p.stat().st_size < 1_000_000 or q <= 50:
            break
        q -= 7
    print("  ->", p.relative_to(ROOT), f"{p.stat().st_size / 1e3:.0f} kB")


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def weight_stats(mark, thr: float = 0.5) -> dict:
    """Share of line weighted (r > thr), number of heavy runs, and how often a
    heavy run contains an event of the line (corner/κ/switch/token/inflection)
    vs chance (random windows of the same lengths)."""
    q = mark.resampled(STEP)
    s = q.arclength()
    r = q["r"]
    runs = stretches(r / 2.0, thr / 2.0)
    ev = line_events(q)
    strong = np.array([e[0] for e in ev if e[1] >= 0.6])
    heavy = r > thr
    # lift: strong events per mm inside the weighted stretches / per mm over the whole line
    near = np.zeros(len(s), bool)
    for x in strong:
        near |= np.abs(s - x) <= 3.0
    inside = float(np.sum([heavy[np.argmin(np.abs(s - x))] for x in strong]))
    lift = (inside / max(heavy.sum(), 1)) / (len(strong) / len(s)) if len(strong) and heavy.any() else None
    return {"weighted_share": round(float(np.mean(heavy)), 3), "heavy_runs": len(runs),
            "strong_events": int(len(strong)), "lift": round(lift, 2) if lift is not None else None,
            "heavy_near_event": round(float(np.mean(near[heavy])), 2) if heavy.any() else None,
            "line_near_event": round(float(np.mean(near)), 2)}


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------

def stage_field():
    base = {"frame": [267, 180], "seed": 7000, "renderer": NIB}
    pre = {"id": "constant", "r": None, "W": 2.5, "M": 7.0}
    rows = [
        ("f1-field-noise", "a  field: noise fronts (the bench's regimes=field)",
         [pre, {"id": "field", "preset": "noise"}]),
        ("f2-timing-staccato", "b  timing: Staccato (stillness pools)", [pre, {"id": "timing", "tempo": "staccato"}]),
        ("f3-event-pulse", "c  prosody event, pulse: a swell on each chosen event",
         [{**PROS, "unit": "pulse", "span": 5.0}]),
        ("f4-event-segment", "d  prosody event, segment: the stretch the event opens", [PROS]),
        ("f5-regular", "e  prosody regular, metre 3 (beats snap to events; empty beats rest)",
         [{**PROS, "rhythm": "regular", "metre": 3}]),
        ("f6-syncopated", "f  prosody syncopated: loud off-beat, quiet downbeat", [{**PROS, "rhythm": "syncopated"}]),
        ("f7-phrase", "g  prosody phrase: end-weighted (loud last, quiet before)", [{**PROS, "rhythm": "phrase"}]),
        ("f8-anticipate", "h  prosody event, pulse, lead -8 mm: the swell anticipates",
         [{**PROS, "unit": "pulse", "span": 6.0, "lead": -8.0}]),
        ("f9-staccato-then-prosody", "i  timing Staccato heard as tempo events, then prosody decides",
         [pre, {"id": "timing", "tempo": "staccato", "jitter_gain": 0.5}, {**PROS, "rhythm": "event"}]),
    ]
    ims, num = [], {}
    for name, label, mods in rows:
        sh, im = tile(name, {**base, "voice": V, "modulators": mods}, label)
        st = weight_stats(sh.marks[0])
        num[name] = st
        print(f"  {name:28s} {st}")
        ims.append(im)
    NUM["field"] = num
    save(kit.contact(ims, 3, title="field / timing vs prosody — one drift line (matisse > shikasta > lichtenberg, "
                                   "chain, seed 7000), nib e"), "field-vs-prosody")


def stage_solid():
    base = {"frame": [267, 180], "seed": 7000, "voice": V, "modulators": [PROS]}
    rows = [
        ("s1-nib-a", "a  solid: regime mass, outline (nib a)", {"id": "nib", "style": "a"}),
        ("s2-nib-b+", "b  solid: regime mass, concentric insets (nib b+)", {"id": "nib", "style": "b+"}),
        ("s3-restate6", "c  restate x6 (mashq): the stretch written again", {"id": "restate", "copies": 6}),
        ("s4-restate6-contour", "d  restate x6 + contour bound: process closed into an object",
         {"id": "restate", "copies": 6, "bound": "contour"}),
        ("s5-coil-spiral", "e  coil, spiral: one line winding out of the stretch", {"id": "coil", "rings": 5}),
        ("s6-restate3-hull", "f  restate x3 + hull bound (a cartouche)",
         {"id": "restate", "copies": 3, "bound": "hull", "bound_gap": 1.5}),
    ]
    ims, num = [], {}
    for name, label, rnd in rows:
        sh, im = tile(name, {**base, "renderer": rnd}, label)
        L = sum(float(np.sum(np.linalg.norm(np.diff(k.points, axis=0), axis=1))) for k in sh.inks)
        num[name] = {"inks": len(sh.inks), "ink_mm": round(L, 1)}
        print(f"  {name:24s} {num[name]}")
        ims.append(im)
    NUM["solid"] = num
    save(kit.contact(ims, 3, title="solid vs line-built — the same stresses (prosody event, segment), six ways "
                                   "of giving them weight"), "solid-vs-linebuilt")


def _count_raster(lines, lo, k, shape):
    from PIL import Image, ImageDraw  # noqa: PLC0415
    acc = np.zeros(shape[::-1], dtype=np.int32)
    for ln in lines:
        im = Image.new("L", shape, 0)
        ImageDraw.Draw(im).line([tuple(v) for v in (ln - lo) * k], fill=1, width=max(int(round(0.4 * k)), 1))
        acc += np.asarray(im, dtype=np.int32)
    return acc


def sign_metrics(sheet, k: float = 12.0) -> dict:
    """Per loud stretch: coverage of a FIXED region (the stretch ± 2.5 mm) and
    legibility (inked pixels crossed by exactly ONE line / inked pixels)."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    from shapely.geometry import MultiLineString  # noqa: PLC0415
    m = sheet.marks[0]
    covs, legs = [], []
    for ri, (i0, i1, peak) in enumerate(stretches(m["emphasis"], 0.15)):
        if peak < 0.99:
            continue
        lines = [np.asarray(m.points[i0:i1 + 1])] + [np.asarray(x.points) for x in sheet.inks
                                                      if x.meta.get("role") == "restate" and x.meta.get("stretch") == ri]
        g = MultiLineString(lines[:1]).buffer(2.5)        # fixed region: the stretch ± 2.5 mm, same for every n
        lo = np.array(g.bounds[:2]) - 1
        hi = np.array(g.bounds[2:]) + 1
        shape = tuple(int(v) for v in np.ceil((hi - lo) * k))
        cnt = _count_raster(lines, lo, k, shape)
        msk = Image.new("L", shape, 0)
        polys = g.geoms if g.geom_type == "MultiPolygon" else [g]
        for pg in polys:
            ImageDraw.Draw(msk).polygon([tuple(v) for v in (np.asarray(pg.exterior.coords) - lo) * k], fill=1)
        area = np.asarray(msk, bool)
        ink = cnt > 0
        covs.append(float(ink[area].mean()) if area.any() else 0.0)
        legs.append(float((cnt == 1).sum() / max(ink.sum(), 1)))
    return {"stretches": len(covs), "coverage": round(float(np.mean(covs)), 3) if covs else None,
            "legibility": round(float(np.mean(legs)), 3) if legs else None}


def stage_sign():
    base = {"frame": [267, 180], "seed": 7000, "voice": {**V, "length": 1.2},
            "modulators": [{**PROS, "span": 12.0, "density": 1.2, "primary": 1.0}]}
    ims, num = [], {}
    crops = []
    for n in (1, 2, 3, 5, 8, 12, 20, 40):
        name = f"g-restate{n:02d}"
        rec = {**base, "renderer": {"id": "restate", "copies": n}}
        sh = kit.run(rec)
        kit.preview(sh, OUT / f"{name}.jpg", px_per_mm=6, label=f"restate x{n}")
        mt = sign_metrics(sh)
        num[n] = mt
        print(f"  copies {n:3d}  {mt}")
        im = kit.render_image(sh, px_per_mm=12, label=None)
        crops.append((n, mt, im, sh))
    # crop around the longest loud stretch (same stresses in every run: only the renderer changes)
    m = crops[0][3].marks[0]
    runs = [r for r in stretches(m["emphasis"], 0.15) if r[2] >= 0.99]
    i0, i1, _ = max(runs, key=lambda r: r[1] - r[0])
    seg = np.asarray(m.points[i0:i1 + 1])
    c = (seg.min(0) + seg.max(0)) / 2
    half = max(np.ptp(seg, axis=0).max() / 2 + 6, 14)
    from PIL import ImageDraw  # noqa: PLC0415
    for n, mt, im, _ in crops:
        box = [int((c[0] - half) * 12), int((c[1] - half * 0.7) * 12), int((c[0] + half) * 12),
               int((c[1] + half * 0.7) * 12)]
        from PIL import Image  # noqa: PLC0415
        pad = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (0xFF, 0xFC, 0xF0))
        pad.paste(im, (-box[0], -box[1]))
        cr = pad.resize((720, int(720 * 0.7)))
        lab = Image.new("RGB", (720, 40), (0xFF, 0xFC, 0xF0))
        ImageDraw.Draw(lab).text((10, 10), f"x{n}   coverage {mt['coverage']}   legibility {mt['legibility']}",
                                 fill=(0x10, 0x0F, 0x0F), font=kit.core._font(18))
        t = Image.new("RGB", (720, cr.height + 40), (0xFF, 0xFC, 0xF0))
        t.paste(cr, (0, 0))
        t.paste(lab, (0, cr.height))
        ims.append(t)
    NUM["sign"] = num
    save(kit.contact(ims, 4, title="the sign threshold — one loud stretch restated 1…40 times (mashq by machine); "
                                   "coverage of the heap, legibility = share of ink crossed by one line only"),
         "sign-threshold")
    # the whole sheets at x5 and x20, side by side
    full = [kit.render_image(crops[i][3], px_per_mm=4, label=f"restate x{crops[i][0]} (whole line)") for i in (3, 6)]
    save(kit.contact(full, 2, title="restate x5 vs x20 on the whole line"), "sign-whole")


def stage_duet():
    lead = {"label": "leader", "voice": V, "modulators": [PROS]}
    foll = {"label": "follower", "voice": {**V, "hands": ["bubble", "hokusai"], "length": 3.0},
            "modulators": [PROS]}
    base = {"frame": [267, 180], "seed": 7100, "parts": [lead, foll], "renderer": NIB}
    rows = [
        ("d1-rows-independent", "a  two voices, rows, each stressing its own events (no listening)",
         {"id": "call_response", "answer": 0.0, "window": 0.0, "layout": "rows", "listen_by": "space",
          "radius": 0.5}),
        ("d2-rows-time", "b  rows, call and response in time: the lower line stresses where the upper is silent",
         {"id": "call_response", "listen_by": "time", "layout": "rows"}),
        ("d3-single-independent", "c  one surface, no listening", {"id": "single"}),
        ("d4-single-space", "d  one surface, call and response in space: stress only beside the other's silence",
         {"id": "call_response", "listen_by": "space", "radius": 15.0}),
    ]
    ims, num = [], {}
    for name, label, arr in rows:
        sh, im = tile(name, {**base, "arranger": arr}, label)
        a, b = sh.marks[0], sh.marks[1]
        uu = np.linspace(0, 1, 1001)
        ea = np.interp(uu, a.arclength() / a.length(), a["emphasis"])
        eb = np.interp(uu, b.arclength() / b.length(), b["emphasis"])
        both = float(np.mean((ea > 0.15) & (eb > 0.15)))
        from scipy.spatial import cKDTree  # noqa: PLC0415
        tree = cKDTree(a.points)
        lb = b["emphasis"] > 0.15
        crowd = [float(a["emphasis"][tree.query_ball_point(p, 15.0)].max(initial=0.0)) for p in b.points[lb]]
        num[name] = {"time_overlap": round(both, 4), "corr_u": round(float(np.corrcoef(ea, eb)[0, 1]), 3),
                     "follower_stress_beside_loud_leader": round(float(np.mean(np.array(crowd) > 0.5)), 3)
                     if crowd else None,
                     "stresses": [len(a.meta["prosody"]["stresses"]), len(b.meta["prosody"]["stresses"])]}
        print(f"  {name:24s} {num[name]}")
        ims.append(im)
    NUM["duet"] = num
    # restate rendering of the space duet: the answer built from line
    sh, im = tile("d5-single-space-restate", {**base, "arranger": rows[3][2],
                                              "renderer": {"id": "restate", "copies": 6, "bound": "contour"}},
                  "e  d, inked by restatement + contour bound")
    sh2, im2 = tile("d6-rows-time-coil", {**base, "arranger": rows[1][2], "renderer": {"id": "coil", "rings": 5}},
                    "f  b, inked as coils")
    two = {**base, "arranger": rows[3][2],
           "parts": [{**lead, "renderer": NIB},
                     {**foll, "renderer": {"id": "restate", "copies": 8, "bound": "contour"}}]}
    sh3, im3 = tile("d7-single-space-two-inks", two,
                    "g  d with two weights: leader nib e (masses), follower restated + bound (it answers in line)")
    two_t = {**base, "arranger": rows[1][2],
             "parts": [{**lead, "renderer": NIB}, {**foll, "renderer": {"id": "coil", "rings": 6}}]}
    sh4, im4 = tile("d8-rows-time-two-inks", two_t, "h  b with two weights: leader nib e, follower coils")
    ims += [im, im2, im3, im4]
    strips(OUT / "d-time-strips", [("a  no listening", kit.run({**base, "arranger": rows[0][2]})),
                                   ("b  call and response in time", kit.run({**base, "arranger": rows[1][2]}))])
    save(kit.contact(ims, 2, title="the limb — call and response: leader matisse > shikasta > lichtenberg, "
                                   "follower bubble > hokusai (seed 7100)"), "call-response")


def strips(stem: Path, runs):
    """The duet as a score: emphasis of leader (above) and follower (below)
    along the share u of each line. Recipe of each run saved beside."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    Wd, hh, gap = 1600, 70, 30
    im = Image.new("RGB", (Wd, len(runs) * (2 * hh + gap + 30) + 10), (0xFF, 0xFC, 0xF0))
    dr = ImageDraw.Draw(im)
    ink, mid = (0x10, 0x0F, 0x0F), (0xB7, 0xB5, 0xAC)
    y = 10
    for i, (lab, sh) in enumerate(runs):
        dr.text((10, y), lab, fill=ink, font=kit.core._font(18))
        y += 26
        for j, m in enumerate(sh.marks[:2]):
            u = m.arclength() / m.length()
            e = m["emphasis"]
            base_y = y + (j + 1) * hh
            dr.line([(40, base_y), (Wd - 10, base_y)], fill=mid, width=1)
            pts = [(40 + float(a) * (Wd - 50), base_y - float(b) * (hh - 8)) for a, b in zip(u[::2], e[::2])]
            dr.line(pts, fill=ink, width=2)
            dr.text((8, base_y - 22), "AB"[j], fill=ink, font=kit.core._font(16))
        y += 2 * hh + gap
        sh.save_recipe(stem.parent / f"{stem.name}-{i}.recipe.json")
    p = RES / f"prosody_accumulation-{stem.name}.jpg"
    im.save(p, quality=88)
    print("  ->", p.relative_to(ROOT))


STAGES = {"field": stage_field, "solid": stage_solid, "sign": stage_sign, "duet": stage_duet}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    todo = sys.argv[1:] or list(STAGES)
    for st in todo:
        print(f"== {st}")
        STAGES[st]()
    p = OUT / "numbers.json"
    old = json.loads(p.read_text()) if p.exists() else {}
    old.update({k: v for k, v in NUM.items()})
    p.write_text(json.dumps(old, indent=1, default=str))
