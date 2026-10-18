"""Round 13, thread II-c `accrue` — the review images.

    .local/gesture/.venv/bin/python tools/gesture/experiments/accrue_final.py [piece state variants duds]

Writes tools/gesture/results/accrue-<n>-<name>.jpg (≤ 2400 px, < 400 kB) with
<stem>.recipe.json beside each (a list of tile recipes for sheets of tiles).
Every drawing is kit.run on a recipe; the state strips are read from the
channels and events the voice wrote (nothing is re-simulated).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402

ROOT = HERE.parents[1]
RES = HERE / "results"
OUT = ROOT / ".local/gesture/out/accrue/final"

# Flexoki (axibridge/static/css/flexoki.css)
PAPER, BLACK = "#FFFCF0", "#100F0F"
RED, ORANGE, GREEN, BLUE, PURPLE = "#AF3029", "#BC5215", "#66800B", "#205EA6", "#5E409D"
G300, G500, G700 = "#B7B5AC", "#878580", "#575653"

FRAME = [297.0, 105.0]
SEED = 3944
PX = 8.0


def recipe(seed=SEED, voice=None, ink=None, label=None):
    r = {"frame": FRAME, "seed": seed, "margin": 6.0,
         "parts": [{"voice": {"id": "accrue_walk", **(voice or {})},
                    "modulators": [{"id": "accrue_ink", **(ink or {})}]}],
         "renderer": {"id": "nib", "style": "e", "pen": 0.4}}
    if label:
        r["label"] = label
    return r


def save_jpg(im, path: Path, recipes):
    path.parent.mkdir(parents=True, exist_ok=True)
    if max(im.size) > 2400:
        k = 2400 / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)))
    q = 90
    while True:
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < 390_000 or q <= 40:
            break
        q -= 5
    path.with_suffix(".recipe.json").write_text(json.dumps(recipes, indent=1, default=float))
    print("->", path.relative_to(ROOT), f"{path.stat().st_size / 1e3:.0f} kB  {im.size}")


def moments(sheet):
    """The pointable moments of a line, from its own events and channels: [(s, text)]."""
    m = sheet.marks[0]
    c, ev = m.channels, m.meta["accrue"]
    s, r = c["acc_s"], c["r"]
    out = []
    loops = ev["loops"]
    knots = ev["knots"]
    k0 = knots[0]["s"] if knots else s[-1]
    first = [e for e in loops if e["kind"] == "first" and e["s"] < k0]
    if first:
        out.append((first[0]["s"], "first loop that sets a sense"))
    pressed = np.nonzero((r > 0.25) & (s < k0))[0]
    if len(pressed):
        out.append((float(s[pressed[0]]), "the pen starts to press as the loops tighten"))
    cm = float(sheet.recipe["parts"][0]["voice"]["c_max"])
    hard = [e for e in loops if e["kind"] == "loop" and abs(e["C"]) >= 0.99 * cm and e["s"] < k0]
    if hard:
        out.append((hard[0]["s"], "habit hardened: curl at its limit, a pressed loop chain"))
    for i, k in enumerate(knots):
        out.append((k["s"], "knot: the coil chokes, the habit breaks" if i == 0 else "second knot"))
        out.append((k["s"] + 12.0, "the curl handed to the nib: barbs, then twisted rope"))
        dry = np.nonzero((s > k["s"] + 20) & (r < 0.2))[0]
        if len(dry):
            out.append((float(s[dry[0]]), "spin decays: calm ribbon, dries to wire"))
        nxt = knots[i + 1]["s"] if i + 1 < len(knots) else s[-1]
        again = [e for e in loops if e["kind"] != "relapse" and k["s"] + 60 < e["s"] < nxt]
        if again:
            out.append((again[0]["s"], f"first loop of a new habit; it forms faster ({len(again)} loops by "
                                       f"{again[-1]['s']:.0f} mm)"))
    for rc in ev["recalls"]:
        out.append((rc["s"], f"paper memory: crosses its own stretch from {rc['from_s']:.0f} mm, takes its state"))
    out.sort(key=lambda t: t[0])
    return out


def strip(sheet, width_px, height_px, marks=None, curl_only=False, title=None):
    """The state along arc length, as a PIL image: curl staircase, regime r, nib spin, knots, loops."""
    import io

    import matplotlib  # noqa: PLC0415
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    m = sheet.marks[0]
    c, ev = m.channels, m.meta["accrue"]
    s = c["acc_s"]
    dpi = 100
    fig, ax = plt.subplots(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    ax.fill_between(s, 0, c["r"] / 2.0, color=G300, lw=0, label="regime r / 2  (wire 0 · nib 0.5 · mass 1)")
    loops_mode = sheet.recipe["parts"][0]["voice"].get("habit") == "loops"
    ax.plot(s, c["acc_curl"], color=RED, lw=1.6,
            label="curl |C| / c_max" + ("  (one step per completed loop)" if loops_mode else "  (leaky H·A)"))
    if not curl_only:
        sp = np.abs(c["acc_spin"])
        ax.plot(s, np.clip(sp / 0.6, 0, 1.05), color=ORANGE, lw=1.2, label="nib spin |Ω| / 0.6 rad·mm⁻¹")
        ax.plot(s, c["acc_press"], color=GREEN, lw=0.8, alpha=0.8, label="press (self-density)")
    for e in ev["loops"]:
        col = PURPLE if e["kind"] == "relapse" else G500
        ax.plot([e["s"], e["s"]], [-0.08, -0.02], color=col, lw=1.0)
    for k in ev["knots"]:
        ax.axvline(k["s"], color=BLACK, lw=1.4)
    for rc in ev["recalls"]:
        ax.annotate("", xy=(rc["s"], 1.12), xytext=(rc["from_s"], 1.12),
                    arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.0, connectionstyle="arc3,rad=-0.25"))
    if marks:
        for i, (sv, _) in enumerate(marks, 1):
            ax.text(sv, 1.25, str(i), color=RED, fontsize=11, ha="center", va="center", weight="bold")
    ax.set_xlim(0, s[-1])
    ax.set_ylim(-0.1, 1.35)
    ax.set_yticks([])
    ax.set_xlabel("arc length along the line, mm", fontsize=9, color=G700)
    ax.tick_params(colors=G700, labelsize=8)
    for sp_ in ax.spines.values():
        sp_.set_color(G300)
    ax.legend(loc="upper left", fontsize=8, ncol=4 if not curl_only else 2, frameon=False, bbox_to_anchor=(0, 0.93))
    if title:
        ax.set_title(title, fontsize=9, color=G700, loc="left")
    fig.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=PAPER)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB").resize((width_px, height_px))


def stack(ims, gap=0, bg=PAPER):
    from PIL import Image  # noqa: PLC0415
    W = max(i.width for i in ims)
    H = sum(i.height for i in ims) + gap * (len(ims) - 1)
    o = Image.new("RGB", (W, H), bg)
    y = 0
    for i in ims:
        o.paste(i, (0, y))
        y += i.height + gap
    return o


def stage_piece():
    rec = recipe(label="accrue: one line whose own loops form a habit, harden, break into a knot and hand their spin to "
                       "the nib")
    sheet = kit.run(rec)
    im = kit.render_image(sheet, px_per_mm=PX, label="accrue  ·  one line, river_belt hand, its habit formed and "
                                                     "broken from inside  ·  297 × 105 mm  ·  seed 3944")
    save_jpg(im, RES / "accrue-1-piece.jpg", sheet.recipe)
    return sheet


def stage_state():
    from PIL import ImageDraw  # noqa: PLC0415
    rec = recipe()
    sheet = kit.run(rec)
    marks = moments(sheet)
    im = kit.render_image(sheet, px_per_mm=PX, label=None)
    d = ImageDraw.Draw(im)
    pts = sheet.marks[0].points
    s = sheet.marks[0].channels["acc_s"]
    font = kit.core._font(26)
    placed = []
    for i, (sv, _) in enumerate(marks, 1):
        j = int(np.clip(np.searchsorted(s, sv), 0, len(s) - 1))
        p = pts[j]
        t = pts[min(j + 3, len(pts) - 1)] - pts[max(j - 3, 0)]
        nrm = np.array([-t[1], t[0]]) / (np.linalg.norm(t) + 1e-9)
        q = p + 7.5 * nrm
        for _ in range(8):               # keep the numbers from sitting on each other
            if all(np.linalg.norm(q - o) > 6.0 for o in placed):
                break
            q = q + 3.0 * nrm
        placed.append(q)
        x, y = q * PX
        d.line([tuple(p * PX), (x, y)], fill=RED, width=2)
        d.ellipse([x - 15, y - 15, x + 15, y + 15], fill=PAPER, outline=RED, width=2)
        d.text((x, y), str(i), fill=RED, font=font, anchor="mm")
    st = strip(sheet, im.width, 420, marks=marks)
    from PIL import Image  # noqa: PLC0415
    lines = [f"{i}  {txt}   ({sv:.0f} mm)" for i, (sv, txt) in enumerate(marks, 1)]
    leg = Image.new("RGB", (im.width, 34 * ((len(lines) + 1) // 2) + 60), PAPER)
    dl = ImageDraw.Draw(leg)
    f2 = kit.core._font(22)
    dl.text((24, 12), "where the accumulated state shows on the line (numbers on the drawing = numbers on the strip; "
                      "blue arrows = paper memory, from the old stretch to where it was taken up)", fill=G700, font=f2)
    for k, ln in enumerate(lines):
        col, row = k % 2, k // 2
        dl.text((24 + col * im.width // 2, 50 + 34 * row), ln, fill=BLACK, font=f2)
    save_jpg(stack([im, st, leg]), RES / "accrue-2-state.jpg", sheet.recipe)


def tile_with_trace(rec, label, curl_only=True, title=None):
    sheet = kit.run(rec)
    im = kit.render_image(sheet, px_per_mm=5.0, label=label)
    tr = strip(sheet, im.width, 190, curl_only=curl_only, title=title)
    return sheet, stack([im, tr])


def stage_variants():
    rows, recs = [], []
    for sd, why in [(3969, "same rule, seed 3969: loops tighten into a pressed chain, knot, a twisting release; "
                           "at the right the habit forms again, faster"),
                    (3965, "seed 3965: chain, knot, barbed release; the habit re-forms and knots again at the end"),
                    (3966, "seed 3966: the hand never repeats a turn the same way often enough; no habit forms")]:
        sheet, im = tile_with_trace(recipe(seed=sd), why)
        rows.append(im)
        recs.append({"label": why, "recipe": sheet.recipe})
    save_jpg(stack(rows, gap=24), RES / "accrue-3-variants.jpg", recs)


def stage_duds():
    rows, recs = [], []
    duds = [
        ({"habit": "leaky", "c_rate": 0.0, "keep": 0.7, "exhaust": 6, "transfer": 3.0, "spin_half": 30.0,
          "c_max": 45.0, "h0": 0.3, "h_len": 0.25, "h_use": 1.5},
         "dud a: leaky habit, uncapped (curl = H·A runs away): knot after knot, barbs over barbs — a clot"),
        ({"habit": "leaky", "c_rate": 0.2, "keep": 0.0, "exhaust": 2, "h0": 0.1, "h_use": 0.6},
         "dud b: leaky habit with a rate cap: the curl is a smooth slide — reads as a parameter ramp, not a habit"),
    ]
    for v, why in duds:
        sheet, im = tile_with_trace(recipe(voice=v), why)
        rows.append(im)
        recs.append({"label": why, "recipe": sheet.recipe})
    save_jpg(stack(rows, gap=24), RES / "accrue-4-duds.jpg", recs)


if __name__ == "__main__":
    for st in (sys.argv[1:] or ["piece", "state", "variants", "duds"]):
        globals()[f"stage_{st}"]()
