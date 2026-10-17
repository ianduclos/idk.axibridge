"""oehlen_intuit session: each step is a function, in the order it was made.

Run one step:  .local/gesture/.venv/bin/python tools/gesture/experiments/oehlen_intuit_session.py s01
The log of why each step happened is in tools/gesture/results/oehlen_intuit-2026-10-17.md.
Typed coordinates are literal data typed blind (no function, no preview).
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "tools/gesture/experiments")
sys.path.insert(0, "tools/gesture")
from oehlen_intuit_tools import arr, chaikin, fit, length, resample, show  # noqa: E402

# --- step 1: typed blind, 0..100 units, no looking ---------------------------
TYPED_A = [(12, 80), (15, 78), (22, 77), (30, 79), (34, 74), (35, 60), (35, 58), (37, 57),
           (45, 57), (47, 55), (48, 40), (52, 30), (58, 22), (60, 21), (61, 23), (60, 35),
           (62, 50), (70, 62), (72, 63), (72, 70), (78, 71), (78, 64), (84, 64), (84, 71),
           (90, 70), (93, 50), (91, 20), (95, 5)]
TYPED_B = [(5, 40), (9, 41), (14, 39), (20, 44), (21, 52), (19, 60), (25, 66), (40, 68),
           (41, 69), (41, 90), (43, 91), (60, 92), (61, 88), (59, 85), (62, 83), (66, 85),
           (64, 88), (63, 99)]
TYPED_C = [(70, 10), (68, 11), (55, 12), (50, 15), (49, 15), (49, 18), (30, 18), (29, 30),
           (28, 31), (27, 30), (26, 31), (25, 30), (24, 31), (23, 30), (22, 31), (10, 33)]


def s01():
    frame = (200, 200)
    box = (15, 15, 170, 170)
    lines = [arr(t) * 1.7 + 15 for t in (TYPED_A, TYPED_B, TYPED_C)]
    return show(lines, frame, "s01_typed_blind", pens=0.5, params={"step": 1})



# --- step 3: a stork's arc slammed across the typed drawing ------------------
from oehlen_intuit_tools import stork  # noqa: E402

STORK_STARTS = [477, 2048, 10626, 12555, 12895, 14604, 19107, 19664, 23088, 23797, 24702, 26709]  # rng 4113


def s03():
    frame = (200, 200)
    typed = [arr(t) * 1.7 + 15 for t in (TYPED_A, TYPED_B, TYPED_C)]
    P = stork("Oduella")
    arc = fit(P[19107:19607], (-10, 40, 230, 120))
    return show(typed + [arc], frame, "s03_stork_over_typed", pens=[0.4, 0.4, 0.4, 1.4],
                params={"step": 3, "stork": ["Oduella", 19107, 500]})


# --- step 5: typed blind again, trying to type a loose charcoal line ---------
TYPED_L1 = [(20, 150), (40, 140), (70, 128), (95, 122), (110, 121), (118, 118), (121, 110), (119, 96),
            (113, 80), (112, 70), (117, 62), (126, 60), (134, 64), (137, 72), (135, 84), (131, 95),
            (133, 104), (142, 109), (160, 110), (185, 106), (205, 98), (220, 85), (226, 70), (224, 55),
            (216, 44), (205, 40), (199, 44), (200, 52), (209, 57), (230, 58), (250, 52), (262, 40), (268, 25)]
TYPED_L2 = [(150, 20), (152, 35), (151, 50), (155, 68), (162, 82), (170, 90), (172, 92)]
TYPED_L3 = [(60, 185), (90, 183), (120, 186), (150, 182), (152, 182), (152, 178), (156, 178), (156, 182),
            (160, 182), (160, 178), (164, 178), (164, 182), (190, 184), (240, 181), (280, 186)]


def s05():
    frame = (300, 200)
    lines = [chaikin(TYPED_L1, 4), arr(TYPED_L2), arr(TYPED_L3)]
    return show(lines, frame, "s05_typed_charcoal", pens=[0.9, 0.4, 0.4], params={"step": 5, "chaikin": 4})


# --- step 6: keep the wrong swoosh, cut it where it crosses itself, burn a stork knot there
def first_self_crossing(p):
    """Index i of the first segment that crosses an earlier non-adjacent one, and the point."""
    p = arr(p)
    for i in range(2, len(p) - 1):
        a, b = p[i], p[i + 1]
        for j in range(0, i - 1):
            c, d = p[j], p[j + 1]
            den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
            if abs(den) < 1e-12:
                continue
            t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
            u = ((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / den
            if 0 <= t <= 1 and 0 <= u <= 1:
                return i, a + t * (b - a)
    return None, None


def place(pts, anchor_src, anchor_dst, scale):
    return (arr(pts) - anchor_src) * scale + anchor_dst


def knot_window(start=4500, n=300):
    P = stork("Oduella")[start:start + n]
    # the knot centre = the median fix (the nest)
    return P, np.median(P, axis=0)


def s06():
    frame = (300, 200)
    sw = chaikin(TYPED_L1, 4)
    i, x = first_self_crossing(sw)
    sw_cut = np.vstack([sw[:i + 1], x])
    P, c = knot_window()
    knot = place(P, c, x, 0.12)
    lines = [sw_cut, arr(TYPED_L2), arr(TYPED_L3), knot]
    return show(lines, frame, "s06_cut_and_burn", pens=[0.9, 0.4, 0.4, 0.3],
                params={"step": 6, "knot": ["Oduella", 4500, 300, 0.12]})


# --- step 7: not timid. the knot big, in a dumb place (sitting on the horizon)
def s07():
    frame = (300, 200)
    P, c = knot_window(4500, 300)
    # scale so the inner 80% of fixes span ~45 mm
    q = np.percentile(np.linalg.norm(P - c, axis=1), 80)
    knot = place(P, c, np.array([158.0, 150.0]), 22.0 / q)
    lines = [chaikin(TYPED_L1, 4), arr(TYPED_L2), arr(TYPED_L3), knot]
    return show(lines, frame, "s07_knot_on_horizon", pens=[0.9, 0.4, 0.4, 0.3],
                params={"step": 7, "knot": ["Oduella", 4500, 300, "inner80%=22mm radius", [158, 150]]})


# --- step 8: a feeler typed while looking at s07, from the top-left to the knot; clip to frame
from oehlen_intuit_tools import clip  # noqa: E402

TYPED_L4 = [(10, 12), (30, 14), (48, 13), (60, 18), (66, 26), (64, 30), (67, 31), (75, 40), (82, 52),
            (86, 66), (84, 74), (88, 80), (96, 92), (104, 104), (112, 118), (116, 126), (121, 133),
            (125, 140), (127, 141), (131, 144)]


def knot07():
    P, c = knot_window(4500, 300)
    q = np.percentile(np.linalg.norm(P - c, axis=1), 80)
    return place(P, c, np.array([158.0, 150.0]), 22.0 / q)


def s08():
    frame = (300, 200)
    lines = [chaikin(TYPED_L1, 4), arr(TYPED_L2), arr(TYPED_L3), knot07(), arr(TYPED_L4)]
    pens = [0.9, 0.4, 0.4, 0.3, 0.25]
    cl, keep = clip(lines, frame, 4.0)
    return show(cl, frame, "s08_feeler", pens=[pens[k] for k in keep], params={"step": 8})


# --- step 9: it was turning into a polite composition. turn the sheet: s08 rotated 90 deg cw -> portrait 200 x 300
def s08_lines():
    frame = (300, 200)
    lines = [chaikin(TYPED_L1, 4), arr(TYPED_L2), arr(TYPED_L3), knot07(), arr(TYPED_L4)]
    pens = [0.9, 0.4, 0.4, 0.3, 0.25]
    cl, keep = clip(lines, frame, 4.0)
    return cl, [pens[k] for k in keep]


def rot_cw(p, H=200.0):
    p = arr(p)
    return np.c_[H - p[:, 1], p[:, 0]]


def s09():
    cl, pens = s08_lines()
    return show([rot_cw(l) for l in cl], (200, 300), "s09_turned", pens=pens, params={"step": 9})


# --- step 11: in the turned sheet, a far-away river (Uda, 64 km) the size of a thumb in the empty lower right;
#              and the same river absurdly close (30 m pixels -> the staircase) as a wall
from oehlen_intuit_tools import river_cl  # noqa: E402

UDA = "Uda_River/Uda_River/centerline_csv/Uda_River_2018_centerline.csv"


def s11():
    cl, pens = s08_lines()
    lines = [rot_cw(l) for l in cl]
    R = river_cl(UDA)
    far = fit(R, (120, 232, 52, 14))
    near = R[700:760]                     # 60 pixels of river, ~2 km
    near = fit(near, (150, 150, 30, 70))
    lines += [far, near]
    pens = list(pens) + [0.3, 0.5]
    return show(lines, (200, 300), "s11_river_far_and_near", pens=pens,
                params={"step": 11, "river": [UDA, "far: whole", "near: 700:760"]})


# --- step 12: the rivers were decoration (dud). Subtract instead: the swoosh (the one nice thing) goes.
def s12():
    cl, pens = s08_lines()
    keep = [(rot_cw(l), p) for l, p in zip(cl, pens) if p != 0.9]
    return show([k[0] for k in keep], (200, 300), "s12_without_swoosh", pens=[k[1] for k in keep],
                params={"step": 12})


# --- step 13: without the swoosh it is a thistle — one weight, legible. The wrong thing has to stay as the
#              opponent. Swoosh back, but in the fine pen; a second, fat pen goes over only its dumbest stretch.
def stretch(p, a, b):
    """Sub-polyline between arc fractions a..b."""
    p = resample(p, 0.5)
    n = len(p)
    return p[int(a * n):int(b * n)]


def s13(a=0.0, b=0.33, name="s13_fat_stretch"):
    cl, pens = s08_lines()
    lines, pp = [], []
    for l, p in zip(cl, pens):
        lines.append(rot_cw(l)); pp.append(0.3 if p == 0.9 else p)
        if p == 0.9:
            lines.append(rot_cw(stretch(l, a, b))); pp.append(1.6)
    return show(lines, (200, 300), name, pens=pp, params={"step": 13, "fat": [a, b, 1.6]})


# --- step 14: it is getting tasteful. Something stupid: a typed arrow (portrait coords) pointing at nothing.
TYPED_ARROW = [(38, 268), (52, 259), (61, 252), (75, 244), (96, 231), (88, 229), (96, 231), (93, 239)]


def s14_lines():
    cl, pens = s08_lines()
    lines, pp = [], []
    for l, p in zip(cl, pens):
        lines.append(rot_cw(l)); pp.append(0.3 if p == 0.9 else p)
        if p == 0.9:
            lines.append(rot_cw(stretch(l, 0.0, 0.33))); pp.append(1.6)
    return lines, pp


def s14():
    lines, pp = s14_lines()
    lines.append(arr(TYPED_ARROW)); pp.append(0.4)
    return show(lines, (200, 300), "s14_arrow", pens=pp, params={"step": 14})


# --- step 15: the staircase I failed to get from the river: the fat stretch of the swoosh pixelated
#              (3 mm cheap-mouse cells) — smooth thin line -> fat pixel line, inside one line.
from oehlen_intuit_tools import pixelate  # noqa: E402


def s15(cell=3.0, name="s15_pixel_stretch", arrow=True):
    cl, pens = s08_lines()
    lines, pp = [], []
    for l, p in zip(cl, pens):
        r = rot_cw(l)
        lines.append(r); pp.append(0.3 if p == 0.9 else p)
        if p == 0.9:
            lines.append(pixelate(rot_cw(stretch(l, 0.0, 0.33)), cell)); pp.append(1.6)
    if arrow:
        lines.append(arr(TYPED_ARROW)); pp.append(0.4)
    return show(lines, (200, 300), name, pens=pp, params={"step": 15, "cell": cell, "arrow": arrow})


# --- step 16: second sheet. Typed fast as a scribble, never re-reading the numbers.
TYPED_SCRIBBLE = [(50, 50), (53, 47), (49, 44), (46, 49), (52, 53), (55, 49), (51, 45), (47, 47), (48, 52),
                  (54, 54), (57, 50), (54, 44), (48, 42), (44, 46), (45, 53), (50, 57), (56, 56), (59, 51),
                  (57, 45), (52, 41), (46, 41), (42, 45), (42, 51), (46, 56), (52, 59), (58, 58), (61, 53),
                  (60, 47), (56, 42), (50, 39), (49, 40), (51, 47), (50, 50), (60, 52), (70, 53), (80, 52),
                  (81, 52), (81, 48), (85, 48), (85, 52), (97, 51)]


def s16():
    return show([arr(TYPED_SCRIBBLE) * 1.5 + 25], (200, 200), "s16_typed_scribble", pens=0.4, params={"step": 16})


# --- step 17: my scribble is a spiral with the notch again (my tic). Make it big, fat and cheap (pixels),
#              and let a long thin stork flight go through it without noticing.
def s17():
    frame = (300, 200)
    sc = fit(TYPED_SCRIBBLE, (40, 30, 200, 140))
    fat = pixelate(sc, 4.0)
    P = stork("Oduella")[12555:13055]
    fl = fit(P, (10, 10, 280, 180))
    lines, keep = clip([fat, fl], frame, 4.0)
    return show(lines, frame, "s17_fat_spiral", pens=[[1.6, 0.25][k] for k in keep],
                params={"step": 17, "cell": 4.0, "stork": ["Oduella", 12555, 500]})


# --- step 18: the knot's rays were all cut on one vertical at the left edge = a visible edge (Ian: no stray
#              marks at the edge). Lines now stop at their last vertex inside: in the air, uneven.
#              Try also without the feeler and the stub (the weakest lines).
from oehlen_intuit_tools import trim_inside  # noqa: E402

NAMES = ["swoosh", "stub", "horizon", "knot", "feeler"]


def sheet1(drop=(), arrow=False, cell=3.0, fat=(0.0, 0.33), trim="ragged", seed=4120, heart=None, crossings=None, stop_short=1.0):
    """Sheet 1 in its viewed (portrait 200 x 300) coordinates. Returns lines, pens, names."""
    frame = (300, 200)
    raw = [chaikin(TYPED_L1, 4), arr(TYPED_L2), arr(TYPED_L3), knot07(), arr(TYPED_L4)]
    pens = {"swoosh": 0.3, "stub": 0.4, "horizon": 0.4, "knot": 0.3, "feeler": 0.25}
    lines, pp, nn = [], [], []
    for nm, l in zip(NAMES, raw):
        if nm in drop:
            continue
        if nm == "knot" and crossings:
            runs = [r for r in drop_short_between_crossings(l, crossings) if length(r) >= 1.5]
            for r in runs:
                for q in ragged_clip([r], frame, 4.0, np.random.default_rng(seed + 3))[0]:
                    lines.append(rot_cw(q)); pp.append(pens[nm]); nn.append(nm)
            continue
        if nm == "knot" and heart:
            parts = [q for r in hollow(l, **heart) for q in ragged_clip([r], frame, 4.0,
                     np.random.default_rng(seed + 3 + len(r)))[0]]
            for q in parts:
                lines.append(rot_cw(q)); pp.append(pens[nm]); nn.append(nm)
            continue
        if nm == "swoosh":
            # the clip split at the self-crossing is part of the drawing now (step 13): keep that split
            parts, _ = clip([l], frame, 4.0)
            if stop_short < 1.0:   # step 24: the last piece stops short (fraction of its length kept)
                parts[-1] = stretch(parts[-1], 0.0, stop_short)
        elif trim == "vertex":
            parts, _ = trim_inside([l], frame, 4.0)
        else:
            parts, _ = ragged_clip([l], frame, 4.0, np.random.default_rng(seed + NAMES.index(nm)))
        for q in parts:
            lines.append(rot_cw(q)); pp.append(pens[nm]); nn.append(nm)
            if nm == "swoosh":
                lines.append(pixelate(rot_cw(stretch(q, *fat)), cell)); pp.append(1.6); nn.append("fat")
    if arrow:
        lines.append(arr(TYPED_ARROW)); pp.append(0.4); nn.append("arrow")
    return lines, pp, nn


def s18():
    a = sheet1(trim="vertex")
    b = sheet1(drop=("feeler", "stub"), trim="vertex")
    show(a[0], (200, 300), "s18a_trimmed", pens=a[1], params={"step": 18})
    return show(b[0], (200, 300), "s18b_trimmed_bare", pens=b[1], params={"step": 18, "drop": ["feeler", "stub"]})


# --- step 19: trimming at vertices threw away the best line (the flight ray from the left edge: its first
#              vertex was outside). Ragged clip instead: cut, then pull each cut end back 3–25 mm (rng 4120+i).
from oehlen_intuit_tools import ragged_clip  # noqa: E402


def s19():
    b = sheet1(drop=("feeler", "stub"))
    return show(b[0], (200, 300), "s19_ragged_bare", pens=b[1], params={"step": 19, "drop": ["feeler", "stub"], "seed": 4120})


# --- step 20: s19's accident (shapely noded the knot at its own crossings and dropped the < 0.5 mm bits:
#              a white heart, but 314 confetti fragments). Make the accident on purpose and contiguous:
#              walk the knot line, lift the pen inside an irregular heart around the nest (radius from a
#              low-frequency wobble, rng 4130), drop runs < 3 mm.
def hollow(line, centre=(158.0, 150.0), r=11.0, wob=0.3, seed=4130, min_run=3.0):
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * np.pi, 3)
    amp = rng.uniform(0.3, 1.0, 3) * wob
    p = resample(line, 0.3)
    v = p - np.asarray(centre)
    th = np.arctan2(v[:, 1], v[:, 0])
    rad = r * (1 + sum(a * np.sin((k + 1) * th + f) for k, (a, f) in enumerate(zip(amp, ph))) / 3)
    m = np.linalg.norm(v, axis=1) > rad
    runs, cur = [], []
    for q, o in zip(p, m):
        if o:
            cur.append(q)
        else:
            if len(cur) > 1 and length(cur) >= min_run:
                runs.append(np.array(cur))
            cur = []
    if len(cur) > 1 and length(cur) >= min_run:
        runs.append(np.array(cur))
    return runs


def s20():
    L, P, N = sheet1(drop=("feeler", "stub"), heart={"r": 11.0})
    print("knot runs", N.count("knot"))
    return show(L, (200, 300), "s20_white_heart", pens=P, params={"step": 20, "heart": {"r": 11.0, "seed": 4130}})


# --- step 21: the deliberate heart (s20) is a drawn circle, a bullet hole: the effect, competent. Back to
#              the accident's own logic: split the knot at its self-crossings, lift every piece shorter than
#              tau, keep the rest joined. The hole is where the bird crossed itself most.
from oehlen_intuit_tools import drop_short_between_crossings  # noqa: E402


def s21():
    out = []
    for tau in (2.0, 3.0):
        L, P, N = sheet1(drop=("feeler", "stub"), crossings=tau)
        print(tau, "knot runs", N.count("knot"))
        out.append(show(L, (200, 300), f"s21_crossings_tau{tau:g}", pens=P,
                        params={"step": 21, "crossings_tau": tau}))
    return out


# --- step 23: arrow dropped (a gag; the most obvious sign). The sheet is now elegant, which worries me.
#              Bring back the weakest line I removed (the feeler) in a wrong colour: blue-400, a second pen.
BLUE = (0x43, 0x85, 0xBE)   # flexoki blue-400 (axibridge/static/css/flexoki.css)
INKC = (0x10, 0x0F, 0x0F)


def s23(tau=2.0, blue=("feeler",), name="s23_blue_feeler", stop_short=1.0, colour=None):
    drop = tuple(n for n in ("feeler", "stub") if n not in blue)
    L, P, N = sheet1(drop=drop, crossings=tau, stop_short=stop_short)
    cols = [(colour or BLUE) if n in blue else INKC for n in N]
    P = [0.5 if n in blue else p for p, n in zip(P, N)]
    return show(L, (200, 300), name, pens=P, colors=cols,
                params={"step": 23, "crossings_tau": tau, "coloured": list(blue), "colour": list(colour or BLUE),
                        "stop_short": stop_short, "names": N})


# --- step 24: blue read as a river on a map; red (flexoki red-400) reads as a fuse into the burst — a
#              stupid story, but the colour stops the sheet being elegant. Keep red. And stop short: the tail
#              flourish after the pixel hook is "finishing"; the last piece keeps only part of its length.
RED = (0xD1, 0x4D, 0x41)    # flexoki red-400


def s24():
    out = []
    for f in (0.62, 0.75):
        out.append(s23(name=f"s24_red_stop{int(f*100)}", stop_short=f, colour=RED))
    return out


# --- sheet 2 (steps 25..): forbidden the sheet-1 vocabulary (no stork knot, no pixel stairs, no swoosh).
#     Only typed lines, one per round, each typed while looking at the previous round. Frame 110 x 210: a
#     door-shaped strip, an awkward proportion on purpose.
S2 = [
    [(15, 200), (18, 170), (16, 150), (22, 120), (40, 95), (44, 90), (44, 70), (60, 52), (62, 30), (58, 12), (70, 6)],
    # r2, after seeing a crack: a line that wants to cross it and turns back just before
    [(105, 60), (90, 62), (80, 66), (66, 70), (49, 74), (47, 76), (52, 82), (70, 85), (95, 96), (100, 110), (98, 140)],
    # r3, after seeing a mouth eating the crack: one fast line in long strides that loses its nerve at the end
    [(4, 30), (40, 60), (80, 100), (92, 122), (93, 123), (92, 125), (94, 126), (93, 128), (95, 129), (94, 131),
     (96, 132), (95, 134), (97, 135)],
]


def s2_round(k, pens=None):
    lines = [arr(t) for t in S2[:k]]
    return show(lines, (110, 210), f"s25_sheet2_round{k}", pens=pens or 0.4, params={"step": 24 + k, "rounds": k})


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(globals()[name]())
