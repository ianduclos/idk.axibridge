"""Round 13, thread I-c contagion: a line that catches a regime's grammar (kit/arrangers_contagion.py).

    .local/gesture/.venv/bin/python tools/gesture/experiments/contagion.py <name> [<name> ...]

Each name is a recipe builder below (or `sweep`, `final`); images go to .local/gesture/out/contagion/
with the recipe beside each. Write-up: tools/gesture/results/contagion-2026-10-18.md.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_contagion as cg  # noqa: E402
from gesture.kit import arrangers_oehlen_found as of  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/contagion"
RES = HERE / "results"


def plate(hand="hokusai", length=4.0, plate_kind="taxonomy", split=0.6):
    """found ground's printed matter: the measure_next plate of a hokusai line."""
    return {"voice": {"id": "hand", "hand": hand, "length": length},
            "modulators": [{"id": "measure_next", "cut": "inflection", "plate": plate_kind, "page": "diptych",
                            "families": 5, "straight": "rules+labels", "hist": "none", "split": split}]}


def river(span_w=2400, angle=0.0, start=0.0):
    """found ground's far river (frozen river_stems/grwl_far_sb19)."""
    return {"voice": {"id": "oehlen_found_river", "tile": "SB19", "rank": 0, "start": start, "span_w": span_w,
                      "angle": angle}}


def gesture(h="dance_thrusting", length=3.0):
    return {"voice": {"id": "hand", "hand": h, "length": length}}


def base(seed, frame, parts, **arr):
    a = {"id": "contagion"}
    a.update(arr)
    return {"label": "contagion", "frame": list(frame), "seed": seed, "margin": 10.0, "arranger": a,
            "parts": parts, "renderer": {"id": "oehlen_found_ink"}}


RECIPES = {}


def recipe(fn):
    RECIPES[fn.__name__] = fn
    return fn


@recipe
def c1():
    """found ground's sheet (205 × 297, seed 4441's layout, no covers): the mechanics on known ground."""
    return base(4441, (205, 297), [plate(), river(), gesture()],
                found_boxes=[0.5, 0.40, 0.9, 0.66, -2.5, 0.5, 0.60, 0.95, 0.15, -10.0],
                late_box=[0.5, 0.55, 0.9, 0.7])


def build(name, r=None, *, px=5.0, crop=None):
    r = r or RECIPES[name]()
    sh = kit.run(r)
    p = of.save(sh, OUT / f"{name}.jpg", px_per_mm=px, crop=crop)
    log = sh.marks[0].meta.get("contagion", {})
    slim = {"grammars": log.get("grammars"),
            "lines": [{k: v for k, v in l.items() if k != "own"} for l in log.get("lines", [])]}
    (OUT / f"{name}.log.json").write_text(json.dumps(slim, indent=1))
    return sh, p, slim


CODE_COL = {0: (0x10, 0x0F, 0x0F), 1: (0x87, 0x9A, 0x39), 2: (0x87, 0x9A, 0x39), 3: (0x20, 0x5E, 0xA6),
            4: (0xBC, 0x52, 0x15), 5: (0xBC, 0x52, 0x15)}


def last_caught(sheet):
    """Per infection: the last point of the line drawn in that regime's caught grammar (where it is
    actually gone), searched between its onset and the end of its window along the line."""
    m = next(m for m in sheet.marks if "catch" in m.channels)
    g = np.asarray(m["catch"]).astype(int)
    P = m.points
    out = []
    for f in sheet.marks[0].meta["contagion"]["lines"][0]["infections"]:
        i0 = int(np.argmin(np.linalg.norm(P - f["onset"], axis=1)))
        d_end = np.linalg.norm(P[i0:] - f["end"], axis=1)
        i1 = i0 + int(np.argmin(d_end))
        codes = (3,) if f["regime"] == "river" else (4, 5)
        hit = np.flatnonzero(np.isin(g[i0:i1 + 1], codes))
        out.append(np.round(P[i0 + hit[-1]], 2).tolist() if len(hit) else f["onset"])
    return out


def debug(sheet, path, px=4.0, crop=None):
    """Infection map: found layer faint, the late line coloured by what it is doing (own black, contact
    green, carried river blue, carried rule/ticks orange), contact/onset/full-end/end marked."""
    from PIL import Image, ImageDraw
    W, H = sheet.frame
    x0, y0, x1, y1 = crop or (0, 0, W, H)
    im = Image.new("RGB", (int((x1 - x0) * px), int((y1 - y0) * px)), (0xFF, 0xFC, 0xF0))
    dr = ImageDraw.Draw(im)

    def T(q):
        return [((float(a) - x0) * px, (float(b) - y0) * px) for a, b in q]
    for m in sheet.marks:
        if m.meta.get("of_role") == "found" and len(m.points) >= 2:
            dr.line(T(m.points), fill=(0xB7, 0xC9, 0xE0), width=max(int(px * 0.3), 1))
    for m in sheet.marks:
        if "catch" not in m.channels:
            continue
        own = m.meta.get("contagion")
        g = np.asarray(m["catch"]).astype(int)
        P = m.points
        for i in range(len(P) - 1):
            c = g[i + 1] if g[i] == 0 else g[i]
            dr.line(T(P[i:i + 2]), fill=CODE_COL[int(c)], width=max(int(px * 0.7), 2))
    log = sheet.marks[0].meta.get("contagion", {})
    for ln in log.get("lines", [])[:1]:
        for f, gone in zip(ln["infections"], last_caught(sheet)):
            f = {**f, "end": gone}
            for key, col, r in (("contact", (0x66, 0x80, 0x0B), 2.2), ("onset", (0xAF, 0x30, 0x29), 2.0),
                                ("full_end", (0xAD, 0x83, 0x01), 1.6), ("end", (0x6F, 0x6E, 0x69), 1.6)):
                x, y = T([f[key]])[0]
                rr = r * px
                dr.ellipse([x - rr, y - rr, x + rr, y + rr], outline=col, width=max(int(px * 0.4), 2))
    im.save(path, quality=88)
    return path


def run(names):
    for nm in names:
        sh, p, log = build(nm)
        debug(sh, OUT / f"{nm}-map.jpg")
        print(nm, p)
        for l in log["lines"]:
            print("  counts", l["counts"])
            for f in l["infections"]:
                print("  ", f["regime"], "contact", f["contact"], "ride", f["ride_mm"], "carried", f["carried_mm"])
        print("  grammars", json.dumps(log["grammars"])[:400])




# ---------------------------------------------------------------------------
# layouts + sweep
# ---------------------------------------------------------------------------

PORTRAIT = dict(frame=(205, 297), found_boxes=[0.5, 0.27, 0.9, 0.44, -2.5, 0.5, 0.55, 0.95, 0.13, -8.0],
                late_box=[0.5, 0.55, 0.9, 0.82])
LANDSCAPE = dict(frame=(297, 205), found_boxes=[0.3, 0.33, 0.52, 0.56, -2.5, 0.42, 0.7, 0.75, 0.16, 12.0],
                 late_box=[0.5, 0.5, 0.92, 0.88])


def lay(seed, layout, hand="dance_thrusting", length=3.0, **arr):
    L = dict(layout)
    frame = L.pop("frame")
    a = {**L, **arr}
    return base(seed, frame, [plate(), river(), gesture(hand, length)], **a)


def carried_away(sheet, far=15.0):
    """mm of caught grammar (carried river / rules / ticks) drawn farther than `far` mm from every found
    contour of its regime: how far the infection was carried from its source."""
    from scipy.spatial import cKDTree
    src = {"river": [], "plate": []}
    for m in sheet.marks:
        r = cg._regime_of(m.meta)
        if m.meta.get("of_role") == "found" and r:
            src[r].append(of.resample(m.points, 0.5))
    trees = {k: cKDTree(np.vstack(v)) for k, v in src.items() if v}
    out = {"river": 0.0, "plate": 0.0, "river_total": 0.0, "plate_total": 0.0}
    for m in sheet.marks:
        if "catch" not in m.channels:
            continue
        g = np.asarray(m["catch"]).astype(int)
        P = m.points
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
        for code, reg in ((3, "river"), (4, "plate"), (5, "plate")):
            sel = (g[1:] == code) & (g[:-1] == code)
            if not sel.any() or reg not in trees:
                continue
            d = trees[reg].query(P[1:][sel])[0]
            out[reg + "_total"] += float(seg[sel].sum())
            out[reg] += float(seg[sel][d > far].sum())
    return {k: round(v, 1) for k, v in out.items()}


def sweep(layout_name="PORTRAIT", seeds=range(5100, 5124), length=3.0, **arr):
    layout = globals()[layout_name]
    rows = []
    ims = []
    for sd in seeds:
        r = lay(sd, layout, length=length, **arr)
        sh = kit.run(r)
        ca = carried_away(sh)
        log = sh.marks[0].meta["contagion"]["lines"][0]
        regs = [f["regime"] for f in log["infections"]]
        inf = log["infections"]
        ca["double"] = round(sum(max(0.0, min(a["end_mm"], b["end_mm"]) - max(a["on_mm"], b["on_mm"]))
                                 for k, a in enumerate(inf) for b in inf[k + 1:] if a["regime"] != b["regime"]), 1)
        rows.append((sd, ca, regs))
        p = debug(sh, OUT / f"sweep_{layout_name}_{sd}.jpg", px=2.0)
        ims.append(p)
        print(sd, ca, regs, flush=True)
    from PIL import Image
    tiles = [Image.open(p) for p in ims]
    sheet = kit.contact(tiles, cols=6, title=f"contagion sweep {layout_name}")
    sheet.save(OUT / f"contact_{layout_name}_{seeds[0]}.jpg", quality=80)
    return rows


# ---------------------------------------------------------------------------
# the review images (tools/gesture/results/contagion-*.jpg, recipes beside)
# ---------------------------------------------------------------------------

PIECE_SEED = 5302


def piece_recipe():
    """The piece: found ground's found layer (plate + far river) lifted into the top three fifths of a
    205 × 297 sheet; one dance_thrusting line (length 4) catches what it touches."""
    return lay(PIECE_SEED, PORTRAIT, length=4.0)


def _captioned(im, text, fs=None):
    from PIL import Image, ImageDraw
    fs = fs or max(13, im.width // 48)
    font = kit.core._font(fs)
    lines = text.split("\n")
    h = int(fs * 1.35 * len(lines) + fs * 0.9)
    out = Image.new("RGB", (im.width, im.height + h), kit.core.PAPER)
    out.paste(im, (0, 0))
    dr = ImageDraw.Draw(out)
    for i, ln in enumerate(lines):
        dr.text((int(fs * 0.5), im.height + int(fs * 0.45 + i * fs * 1.35)), ln, fill=kit.core.INK, font=font)
    return out


def _row(ims, gap=24):
    from PIL import Image
    h = max(i.height for i in ims)
    out = Image.new("RGB", (sum(i.width for i in ims) + gap * (len(ims) + 1), h + 2 * gap), kit.core.PAPER)
    x = gap
    for i in ims:
        out.paste(i, (x, gap))
        x += i.width + gap
    return out


def _save(im, name, recipe, quality=86):
    im = im.copy()
    im.thumbnail((2400, 2400))
    p = RES / f"contagion-{name}.jpg"
    q = quality
    while True:
        im.save(p, quality=q, optimize=True)
        if p.stat().st_size < 390_000 or q <= 50:
            break
        q -= 6
    (RES / f"contagion-{name}.recipe.json").write_text(json.dumps(recipe, indent=1) + "\n")
    return p


def map_image(sheet, px=6.0):
    """The infections made legible: debug() plus numbered labels at contact and where it wore off."""
    from PIL import ImageDraw, Image
    p = OUT / "_map.jpg"
    debug(sheet, p, px=px)
    im = Image.open(p).convert("RGB")
    dr = ImageDraw.Draw(im)
    font = kit.core._font(int(px * 3.0))
    log = sheet.marks[0].meta["contagion"]["lines"][0]
    W = sheet.frame[0]
    for k, (f, gone) in enumerate(zip(log["infections"], last_caught(sheet)), 1):
        f = {**f, "end": gone}
        for key, txt, dy in (("contact", f"{k} touches the {f['regime']}", -6.0),
                             ("full_end", f"{k} starts to wear off", -1.5),
                             ("end", f"{k} gone", -5.0)):
            x, y = f[key]
            tw = dr.textlength(txt, font=font) / px
            dx = 3.0 if (x + 3.0 + tw < W - 2 and key != "end") else -3.0 - tw
            dr.text(((x + dx) * px, (y + dy) * px), txt, fill=(0x10, 0x0F, 0x0F), font=font)
    return im


def _line_im(lines, w_mm, h_mm, px=8.0, labels=()):
    """Polylines (points mm, colour, pen) drawn on paper; labels: (x, y, text) mm."""
    from PIL import Image, ImageDraw
    ss = 2
    k = px * ss
    im = Image.new("RGB", (int(w_mm * k), int(h_mm * k)), kit.core.PAPER)
    dr = ImageDraw.Draw(im)
    for pts, col, pen in lines:
        q = [(float(a) * k, float(b) * k) for a, b in pts]
        if len(q) >= 2:
            dr.line(q, fill=col, width=max(int(round(pen * k)), 1), joint="curve")
    font = kit.core._font(int(3.0 * k))
    for x, y, t in labels:
        dr.text((x * k, y * k), t, fill=(0x10, 0x0F, 0x0F), font=font)
    return im.resize((int(w_mm * px), int(h_mm * px)), Image.Resampling.LANCZOS)


def _ar_meander(rng, river_lines, length_x, step=0.4, axis_mm=10.0, order=6):
    """The first river generator (the dud): an AR(order) model of the river's heading about its axis,
    fit by Yule–Walker. Same rms swing and half-wavelength as the river; it reads as a wobble."""
    from scipy.linalg import solve_toeplitz
    from scipy.ndimage import gaussian_filter1d
    res = []
    for l in river_lines:
        p = of.resample(l, step)
        th = cg._heading(p)
        res.append(th - gaussian_filter1d(th, axis_mm / step, mode="nearest"))
    r = np.zeros(order + 1)
    n = 0
    for x in res:
        x = x - x.mean()
        for kk in range(order + 1):
            r[kk] += float(np.dot(x[: len(x) - kk], x[kk:]))
        n += len(x)
    r /= n
    phi = solve_toeplitz(r[:order], r[1:])
    sig = np.sqrt(max(r[0] - phi @ r[1:], 1e-9))
    m = 300 + int(length_x * 3.5 / step)
    th = np.zeros(m)
    e = rng.normal(0, sig, m)
    for i in range(order, m):
        th[i] = phi @ th[i - order:i][::-1] + e[i]
    th = th[300:]
    xy = np.r_[[[0.0, 0.0]], np.cumsum(np.c_[np.cos(th), np.sin(th)] * step, axis=0)]
    xy[:, 1] -= gaussian_filter1d(xy[:, 1], axis_mm / step, mode="nearest")
    return xy[xy[:, 0] <= length_x]


def _walk_demo(found_piece, own, grammars, regime, seed, **kw):
    """The kit's own walk on a demo own path `own` against one short found piece: the contact, the
    carried grammar, the way out. Returns (points, codes)."""
    P = dict(step=0.3, capture=4.0, align=0.5, listen=400.0, ignore=0.0, ride=8.0, ride_sd=0.2, min_ride=4.0,
             ride_gap=0.9, return_mm=20.0, ramp=2.0, max_offset=18.0, catches=1,
             full={"river": 40.0, "plate": 30.0}, decay={"river": 70.0, "plate": 30.0}, tick_linger=2.5,
             own_mm=6.0, rule_tol=3.5, snap=20.0, tick_pitch=6.3, immune_mm=60.0, omega_max=120.0)
    P.update(kw)
    G = cg.Ground([found_piece], 0.3, tag=1)
    pts, codes, _ = cg.contagion_walk(own, {regime: G}, grammars, np.random.default_rng(seed),
                                      regimes=(regime,), **P)
    return pts, codes


def grammar_image(sheet, px=8.0):
    """What 'whole' means, river and plate: the found grammar, the carried grammar and its way out,
    and the duds (averaged, faded, the AR wobble)."""
    log = sheet.marks[0].meta["contagion"]
    g = log["grammars"]["river"]
    riv = [m.points for m in sheet.marks if str(m.meta.get("found", "")).startswith("grwl")]
    W = 170.0
    blue, black, grey = (0x20, 0x5E, 0xA6), (0x10, 0x0F, 0x0F), (0x87, 0x85, 0x80)
    rows = []
    # 1. the found river, a 150 mm stretch turned level
    q = riv[0]
    c = q.mean(axis=0)
    ev = np.linalg.eigh(np.cov((q - c).T))[1][:, -1]
    q = of._rot(q, c, -np.degrees(np.arctan2(ev[1], ev[0])))
    x0 = q[:, 0].min() + 20
    q = q[(q[:, 0] >= x0) & (q[:, 0] <= x0 + 150)]
    q = q - [x0 - 10, q[:, 1].mean() - 15]
    rows.append(("found: the far river as pasted (blue 0.3 mm). Its grammar, measured: per half-bend the swing "
                 f"(median {g['omega_deg_p50']}°) and length (median {g['halfbend_mm_p50']} mm), "
                 f"{g['n_bends']} bends", [(q, blue, 0.3)]))
    rng = np.random.default_rng(PIECE_SEED)
    xy = cg.gen_meander(rng, g, 150.0)
    rows.append(("carried: a fresh river from that grammar on a straight own path (black 0.7 mm), whole",
                 [(xy + [10, 9], black, 0.7)]))
    # the way out, by the kit's own walk: contact with a 22 mm piece of found river, carried, shed
    q2 = q[(q[:, 0] >= 10) & (q[:, 0] <= 32)]
    piece = q2 - [q2[0, 0] - 10.0, q2[:, 1].mean() - 9.0]
    own = np.c_[np.linspace(4.0, 160.0, 600), np.full(600, 9.0)]
    pts, codes = _walk_demo(piece, own, log["grammars"], "river", PIECE_SEED + 1,
                            full={"river": 35.0, "plate": 30.0}, decay={"river": 80.0, "plate": 30.0})
    rows.append(("the way out, by the kit's walk: contact (0.9 mm beside a scrap of the found river), full, then "
                 "whole bends shed, rarer, each still a river bend",
                 [(piece, blue, 0.3), (pts, black, 0.7)]))
    fade = xy.copy()
    fade[:, 1] *= np.array([1.0 if x < 50 else 1 - cg._smooth((x - 50) / 90.0) for x in xy[:, 0]])
    rows.append(("dud: fading out instead: the bends shrink, and the middle is an average, a wobble",
                 [(fade + [10, 9], grey, 0.7)]))
    avg = xy.copy()
    avg[:, 1] *= 0.3
    rows.append(("dud: the river averaged into the line at 30 %: a texture, neither river nor line",
                 [(avg + [10, 9], grey, 0.7)]))
    ar = _ar_meander(np.random.default_rng(PIECE_SEED + 2), riv, 150.0)
    rows.append(("dud (my first generator): an AR(6) heading model, same swing rms and half-wave as the river; "
                 "jitter and knots, a wobble", [(ar + [10, 9], grey, 0.7)]))
    # plate: the kit's walk against a scrap of found rule, on a gently curving own path
    pg = log["grammars"]["plate"]
    t = np.linspace(0, 1, 800)
    own = np.c_[4 + 156 * t, 9 + 5 * np.sin(2 * np.pi * (t * 1.4 + 0.05)) * np.minimum(t * 6, 1)]
    a = np.radians(pg["angle_deg"])
    rule = np.array([[4.0, 9.0], [4.0 + 30 * np.cos(a), 9.0 + 30 * np.sin(a)]])
    pts, codes = _walk_demo(of.resample(rule, 0.3), own, log["grammars"], "plate", PIECE_SEED + 3,
                            full={"river": 40.0, "plate": 30.0}, decay={"river": 70.0, "plate": 30.0},
                            tick_linger=4.0)
    rows.append((f"plate, by the kit's walk: contact with a scrap of found rule (blue, {pg['angle_deg']}°); carried: "
                 f"dead-straight runs with {pg['tick_mm']} mm ticks; the ruling goes first, the ticks last",
                 [(rule, blue, 0.3), (pts, black, 0.7)]))
    from PIL import Image
    tiles = [_captioned(_line_im(L, W, 30.0 if k == 0 else 19.0, px=px), txt, fs=15)
             for k, (txt, L) in enumerate(rows)]
    h = sum(ti.height for ti in tiles)
    out = Image.new("RGB", (max(ti.width for ti in tiles), h), kit.core.PAPER)
    y = 0
    for ti in tiles:
        out.paste(ti, (0, y))
        y += ti.height
    return out


def final():
    """Rebuild the four review images in tools/gesture/results/."""
    r = piece_recipe()
    sh = kit.run(r)
    log = sh.marks[0].meta["contagion"]["lines"][0]
    ca = carried_away(sh)
    print("piece", ca, log["counts"])
    out = [_save(of.render_colour(sh, px_per_mm=6.0), "1-piece", sh.recipe)]
    mp = map_image(sh, px=6.0)
    cap = ("infection map. black own line; green: contact (the ride, 0.9 mm beside); blue: carried river; orange: "
           "carried rule and ticks.\nrings: green contact, red onset, yellow where it starts to wear off, grey its last caught element.\n"
           f"carried farther than 15 mm from its source: river {ca['river']:.0f} of {ca['river_total']:.0f} mm, "
           f"plate {ca['plate']:.0f} of {ca['plate_total']:.0f} mm")
    out.append(_save(_captioned(mp, cap, fs=17), "2-map", sh.recipe))
    panels, recs = [], []
    for lab, kw in (("the gesture over the found ground,\nnothing caught (regimes none)", {"regimes": "none"}),
                    ("ride only: contact rides 0.9 mm beside,\nnothing carried (catch = ride, the control)",
                     {"catch": "ride"}),
                    ("catch: the same contacts, the grammar\ncarried along the own path, then shed", {})):
        rr = lay(PIECE_SEED, PORTRAIT, length=4.0, **kw)
        s2 = kit.run(rr)
        panels.append(_captioned(of.render_colour(s2, px_per_mm=3.6), lab, fs=17))
        recs.append(s2.recipe)
    out.append(_save(_row(panels), "3-ride-vs-catch", {"panels": recs}))
    out.append(_save(grammar_image(sh), "4-grammar-and-duds",
                     {"piece": sh.recipe, "seeds": {"carried": PIECE_SEED, "way_out": PIECE_SEED + 1,
                                                    "ar_dud": PIECE_SEED + 2, "plate_walk": PIECE_SEED + 3},
                      "rebuild": "tools/gesture/experiments/contagion.py final (grammar_image)"}))
    for p in out:
        print(p, p.stat().st_size // 1024, "KB")
    return out


if __name__ == "__main__":
    args = sys.argv[1:] or ["c1"]
    if args[0] == "final":
        final()
    elif args[0] == "sweep":
        lo = int(args[2]) if len(args) > 2 else 5100
        sweep(args[1] if len(args) > 1 else "PORTRAIT", range(lo, lo + 24),
              length=float(args[3]) if len(args) > 3 else 3.0)
    else:
        run(args)
