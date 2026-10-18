"""rzoom review images (round 14, thread c1): the far Amazon stem zooming in and out along itself.

    .local/gesture/.venv/bin/python tools/gesture/experiments/rzoom_review.py

Writes tools/gesture/results/rzoom-*.jpg, each with its recipe(s) beside it
(<stem>.recipe.json: one recipe, or {"panels": [...]} for a composite).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, "tools/gesture")
from gesture import kit  # noqa: E402
from gesture.kit.arrangers_oehlen_found import render_colour, save  # noqa: E402
from gesture.kit.core import _font  # noqa: E402

RES = Path("tools/gesture/results")
INK = {"id": "rzoom_ink", "pens": [0.25, 0.35, 0.5, 0.7], "inks": "blue,blue,black,black"}   # reading aid
INK_PIECE = {"id": "rzoom_ink", "pens": [0.2, 0.3, 0.45, 0.6, 0.8], "inks": "black", "min_run": 4.0}
FRAME = (190, 270)
PIECE = {"schedule": "push", "zoom": 32, "recur": 4, "pace": 0.6, "angle": 90, "far_mm_per_km": 0.8}
SEED = 1461


def recipe(frame, voice, seed, renderer=INK, margin=8):
    return {"frame": list(frame), "seed": seed, "margin": margin, "voice": {"id": "river_zoom", **voice},
            "renderer": renderer}


def label(im, text):
    fs = max(12, im.width // 64)
    strip = Image.new("RGB", (im.width, int(fs * 1.9)), (0xFF, 0xFC, 0xF0))
    ImageDraw.Draw(strip).text((int(fs * 0.5), int(fs * 0.4)), text, fill=(0x10, 0x0F, 0x0F), font=_font(fs))
    out = Image.new("RGB", (im.width, im.height + strip.height), (0xFF, 0xFC, 0xF0))
    out.paste(im, (0, 0))
    out.paste(strip, (0, im.height))
    return out


def write_panels(path, recs):
    Path(path).with_suffix(".recipe.json").write_text(json.dumps({"panels": recs}, indent=1) + "\n")


def piece():
    s = kit.run(recipe(FRAME, PIECE, SEED, renderer=INK_PIECE))
    save(s, RES / "rzoom-1-piece.jpg", px_per_mm=6)
    m = s.marks[0]
    print("piece", {k: round(float(m.meta[k]), 2) for k in ("river_km", "drawn_mm", "far_mm_per_km")},
          "zoom", round(float(m["zoom"].min()), 2), round(float(m["zoom"].max()), 2))
    return s


def population():
    ims, recs = [], []
    for i, sch in enumerate(("push", "pulses", "drift", "dive", "steps", "ramp_in", "swell", "breath")):
        r = recipe(FRAME, {**PIECE, "schedule": sch}, SEED + 10 + i)
        s = kit.run(r)
        m = s.marks[0]
        ctl = "  (control: symmetric)" if sch in ("swell", "breath") else ""
        ims.append(label(render_colour(s, px_per_mm=2.5), f"{sch}{ctl}  {m.meta['drawn_mm']:.0f} mm drawn"))
        recs.append(s.recipe)
    out = RES / "rzoom-2-population.jpg"
    kit.contact(ims, 4, title="river_zoom: 8 zoom schedules, the same 547 km of the Amazon stem each time "
                "(steer, zoom 1-32, pace 0.6, 190x270 mm)").save(out, quality=86, optimize=True)
    write_panels(out, recs)


def _crop_panel(m, uc, W, H, K, pen, title):
    """Crop of mark m centred on stem position uc (km): the line at `pen` mm,
    the stem's own samples (every ~59.5 m of river) as red dots."""
    from gesture.kit import library as L
    SS = 3
    pts, u_km = m.points, m["u_km"]
    j = int(np.argmin(np.abs(u_km - uc)))
    x0, y0 = pts[j][0] - W / 2, pts[j][1] - H / 2
    im = Image.new("RGB", (int(W * K * SS), int(H * K * SS)), (0xFF, 0xFC, 0xF0))
    dr = ImageDraw.Draw(im)
    q2 = (pts - [x0, y0]) * K * SS
    pad = 200
    inside = (q2[:, 0] > -pad) & (q2[:, 0] < W * K * SS + pad) & (q2[:, 1] > -pad) & (q2[:, 1] < H * K * SS + pad)
    idx = np.flatnonzero(inside)
    r = pen * K * SS / 2
    for rn in (np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []):
        v = q2[rn]
        dr.line([tuple(p) for p in v], fill=(0x10, 0x0F, 0x0F), width=max(int(round(2 * r)), 1))
        for p in v:
            dr.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=(0x10, 0x0F, 0x0F))
    q = L.load("river_stems", "grwl_far_sb19")["stems"][("SB19", 0)][2]
    un = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))] / 1000.0
    us = un[(un >= u_km.min()) & (un <= u_km.max())]
    s_line = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    sp = np.interp(us, u_km, s_line)
    px = np.column_stack([np.interp(sp, s_line, q2[:, 0]), np.interp(sp, s_line, q2[:, 1])])
    rr = 2.2 * SS
    for v in px:
        if 0 <= v[0] <= W * K * SS and 0 <= v[1] <= H * K * SS:
            dr.ellipse([v[0] - rr, v[1] - rr, v[0] + rr, v[1] + rr], fill=(0xD1, 0x4D, 0x41))
    im = im.resize((int(W * K), int(H * K)), Image.Resampling.LANCZOS)
    return label(im, f"{title}  zoom {float(m['zoom'][j]):.0f}x, {W:.0f}x{H:.0f} mm, pen {pen} mm"), [x0, y0, W, H]


def _sharpest(m):
    """Stem position (km) of the far stem's sharpest sample turn among the
    stretches this line draws at ≥ 70% of its top zoom (the worst case for
    facets)."""
    from gesture.kit import library as L
    q = L.load("river_stems", "grwl_far_sb19")["stems"][("SB19", 0)][2]
    d = np.diff(q, axis=0)
    un = np.r_[0.0, np.cumsum(np.linalg.norm(d, axis=1))] / 1000.0
    turn = np.abs(np.diff(np.unwrap(np.arctan2(d[:, 1], d[:, 0]))))       # at stem nodes 1..n-2
    z = np.interp(un[1:-1], m["u_km"], m["zoom"], left=0.0, right=0.0)
    turn = turn * (z >= 0.7 * float(m["zoom"].max()))
    return float(un[1 + int(np.argmax(turn))])


def closeup():
    """Sampling check: naive magnification (each stem segment keeps its
    heading: the far polyline magnified) vs the voice (heading interpolated),
    at the sharpest bend of the piece's top zoom (32x) and at the voice's
    largest allowed zoom (80x); the stem's own samples in red; thin pen so
    any facet shows."""
    panels, recs = [], []
    for zoom in (32, 80):
        uc = None
        for heading in ("step", "linear"):
            r = recipe(FRAME, {**PIECE, "zoom": zoom, "heading": heading}, SEED)
            s = kit.run(r)
            m = s.marks[0]
            uc = _sharpest(m) if uc is None else uc
            name = "naive: far polyline magnified" if heading == "step" else "river_zoom: heading interpolated"
            im, crop = _crop_panel(m, uc, 36.0, 24.0, 30, 0.3, name)
            panels.append(im)
            recs.append({**s.recipe, "closeup": {"u_km": uc, "crop_mm": crop, "px_per_mm": 30, "pen": 0.3}})
    out = RES / "rzoom-3-closeup.jpg"
    kit.contact(panels, 2, title="sampling check: the sharpest bend at the top zoom (the far stem's largest turn between two samples there); top row the piece (32x), bottom "
                "row the voice's ceiling (80x); red dots = the far stem's own samples (59.5 m of river apart)"
                ).save(out, quality=86, optimize=True)
    write_panels(out, recs)


def scroll():
    ims, recs = [], []
    for sch, sd in (("push", 1491), ("swell", 1491), ("breath", 1491)):
        r = recipe((600, 150), {"schedule": sch, "zoom": 24, "recur": 3, "pace": 0.5, "course": "free",
                                "far_mm_per_km": 0.8}, sd)
        s = kit.run(r)
        m = s.marks[0]
        tag = {"push": "push: 3 uneven pushes in, quick pulls out (asymmetric)",
               "swell": "swell: one symmetric far-close-far (control)",
               "breath": "breath: 3 regular symmetric in-and-outs (control)"}[sch]
        ims.append(label(render_colour(s, px_per_mm=3.2), f"{tag}  - course free: every heading the river's own"))
        recs.append(s.recipe)
    out = RES / "rzoom-4-ornament.jpg"
    kit.contact(ims, 1, title="the ornament test, course free (no steering), 600x150 mm: asymmetric vs "
                "symmetric zoom on the same river").save(out, quality=86, optimize=True)
    write_panels(out, recs)


def window():
    r = recipe((300, 200), {"mode": "window", "frames": 6, "zoom": 24, "span_w": 1600, "pan": 0.25,
                            "start": 0.25}, 1495, renderer={**INK, "min_run": 0.0})
    s = kit.run(r)
    out = RES / "rzoom-5-window-dud.jpg"
    im = label(render_colour(s, px_per_mm=6), "camera window: 6 frames of a window narrowing 24x while it "
               "pans along the stem, superimposed - one line per frame (dud)")
    im.save(out, quality=86, optimize=True)
    s.save_recipe(out.with_suffix(".recipe.json"))


if __name__ == "__main__":
    which = sys.argv[1:] or ["piece", "population", "closeup", "scroll", "window"]
    for w in which:
        globals()[w]()
