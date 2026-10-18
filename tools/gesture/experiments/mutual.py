"""Round 13, thread I-b `mutual`: mutual awareness among regimes.

    .local/gesture/.venv/bin/python tools/gesture/experiments/mutual.py <name> [<name> ...]

Each name is a recipe builder below (or `sweep`, `strip`, `final`); images go
to .local/gesture/out/mutual/ with the recipe and event log beside each.
Write-up: tools/gesture/results/mutual-2026-10-18.md.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

from gesture import kit  # noqa: E402
from gesture.kit import arrangers_oehlen_found as of  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/mutual"
FRAME = [300.0, 200.0]      # the AxiDraw's whole bed at 3:2: the long side is the graph's clock


def base(seed=1311, **v):
    return {"label": "mutual", "frame": FRAME, "seed": seed, "margin": 10.0,
            "arranger": {"id": "single"}, "voice": {"id": "mutual", **v},
            "renderer": {"id": "oehlen_found_ink"}}


RECIPES = {}


def recipe(fn):
    RECIPES[fn.__name__] = fn
    return fn


@recipe
def v1():
    return base(1311)


def events_of(sheet):
    return sheet.marks[0].meta.get("mutual", {}) if sheet.marks else {}


def build(name, r, *, px=5.0, crop=None):
    sh = kit.run(r)
    p = of.save(sh, OUT / f"{name}.jpg", px_per_mm=px, crop=crop)
    m = events_of(sh)
    (OUT / f"{name}.log.json").write_text(json.dumps(m, indent=1, default=float))
    return sh, p, m


def describe(m):
    out = []
    for e in m.get("events", []):
        ans = "; ".join(f"{a['by']}@{a['t']}: {a['how']}" for a in e["answers"]) or "-"
        out.append(f"  #{e['id']:>2} t{e['t']:>3} {e['src']:>5}.{e['kind']:<11} {e['pos']}  -> {ans}")
    for l in m.get("log", []):
        out.append(f"  log t{l['t']}: {l['who']} {l['what']}")
    return "\n".join(out)


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    for name in argv:
        if name == "final":
            final()
            continue
        if name.startswith("strip:"):
            _, rn, sd = name.split(":")
            r = RECIPES[rn]()
            r["seed"] = int(sd)
            sh = kit.run(r)
            c = cuts_of(sh)
            print(c)
            print(strip(sh, c, OUT / f"strip_{rn}_s{sd}.jpg", title=f"{rn} seed {sd}: turn by turn"))
            continue
        if name.startswith("seed="):
            for s in name[5:].split(","):
                r = base(int(s))
                sh, p, m = build(f"s{s}", r)
                print(p)
                print(describe(m))
            continue
        r = RECIPES[name]()
        sh, p, m = build(name, r)
        print(p)
        print(describe(m))




@recipe
def v2():
    return base(1311, river_scale=1.6, river_speed=2.0, river_rush=2.4, wrap_r=16.0, invite=2.0,
                blank=[0.85, 0.58, 0.22])


@recipe
def v3():
    """v2, longer (three bold lines), a bold that tires (refuses the third call), a curious wire."""
    r = v2()
    r["voice"].update(T=190, appetite_gain=0.004, refuse_below=0.3, refuse_r=7.0)
    return r


@recipe
def v4():
    """v2 with a bold that tires: it rides the river's first answer and refuses the second."""
    r = v2()
    r["voice"].update(appetite_gain=0.004, refuse_below=0.45)
    return r


@recipe
def soup():
    """The dud: every relation fires as often as it can (short bold lines, no refractory time, the wire
    answers every burst, no patience) -- awareness turned up into a field."""
    r = v4()
    r["voice"].update(bold_len=0.35, turn_gap=12.0, turn_deg=55.0, refractory=0, burst_ticks=3, wake_max=20,
                      patience=8, river_rush=3.0, wrap_r=9.0, appetite_cost=0.05, refuse_below=0.0,
                      wire_awake=14.0, lift_max=2)
    return r


def sweep_v(name, seeds):
    from PIL import Image
    ims = []
    for s in seeds:
        r = RECIPES[name]()
        r["seed"] = s
        sh, p, m = build(f"{name}_s{s}", r)
        ims.append(Image.open(p))
    kit.contact(ims, 2, title=f"{name}: seeds {seeds}").save(OUT / f"_{name}.jpg", quality=85)


# ---------------------------------------------------------------------------
# the process strip: the same run, read at chosen turns
# ---------------------------------------------------------------------------

ANNOT = "#DA702C"          # Flexoki orange-400: annotation only (never ink of the piece)
NAMES = {"bold": "bold", "river": "river", "graph": "graph", "wire": "wire"}


def render_state(sheet, t0, t1, *, px=4.0, ss=2, fade=0.22, crop=None):
    """The paper at the end of turn t1: ink of turns ≤ t0 faded, of (t0, t1] in full."""
    from PIL import Image, ImageDraw
    W, H = sheet.frame
    x0, y0, x1, y1 = crop if crop is not None else (0.0, 0.0, W, H)
    k = px * ss
    size = (int(round((x1 - x0) * k)), int(round((y1 - y0) * k)))
    rgb = np.ones((size[1] // ss, size[0] // ss, 3)) * np.array(of.PAPER, float)
    paper = np.array(of.PAPER, float)
    layers = []
    for m in sheet.marks:
        tk = np.asarray(m["tick"])
        col = np.array(of._hex(of.FLEXOKI.get(m.meta.get("ink", "black"), of.FLEXOKI["black"])), float)
        for old in (True, False):
            sel = (tk <= t0) if old else ((tk > t0) & (tk <= t1))
            if not sel.any():
                continue
            idx = np.flatnonzero(sel)
            runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
            c = paper + (col - paper) * fade if old else col
            for r in runs:
                a = max(r[0] - 1, 0) if not old else r[0]
                layers.append((old, tuple(c), m.points[a: r[-1] + 1], float(m.meta.get("pen", 0.4))))
    layers.sort(key=lambda L: not L[0])            # faded first, then the new ink on top
    for old, c, pts, pen in layers:
        if len(pts) < 2:
            continue
        im = Image.new("L", size, 0)
        dr = ImageDraw.Draw(im)
        q = (pts - [x0, y0]) * k
        d = max(pen * k, 1.0)
        dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
        im = im.resize((rgb.shape[1], rgb.shape[0]), Image.Resampling.BOX)
        a = np.asarray(im, float)[..., None] / 255.0
        rgb = rgb * (1 - a) + np.array(c) * a
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def _font(sz):
    from PIL import ImageFont
    for f in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def phrase(e, evs):
    """One event and what answered it, in plain words."""
    k = f"{e['src']} {e['kind'].replace('_', ' ')}"
    how = {("bold", "stop"): "bold stops in a knot", ("bold", "turn"): "bold turns sharply",
           ("river", "arrive"): "river has wrapped the knot", ("graph", "burst"): "graph: an arrival",
           ("wire", "ride"): "wire rides the trace", ("wire", "refuse"): "wire turns away from bold",
           ("wire", "enter_blank"): "wire enters the blank"}.get((e["src"], e["kind"]), k)
    ans = []
    for a in e["answers"]:
        h = a["how"]
        h = h.replace("turns its course toward the knot", "turns to the knot").replace(
            "re-enters from its knot and rides the river", "rides it from the knot").replace(
            "wakes and crosses to the burst", "wakes, crosses").replace(
            "the needle lifts while it is touched", "lifts its needle").replace(
            "plays an arrival", "answers with").replace("wrapped the knot", "wraps it")
        ans.append(f"{a['by']} {h}")
    return how, ans


def strip(sheet, cuts, path, *, px=3.2, title=None, legend=None):
    """Panels at turns `cuts` (each panel: (prev cut, cut]); events of the
    interval numbered in orange with arrows cause → answer, captions below."""
    from PIL import Image, ImageDraw
    m = events_of(sheet)
    evs = m["events"]
    byid = {e["id"]: e for e in evs}
    panels = []
    num = {}
    n = 0
    prev = -1
    W, H = sheet.frame
    for ci, t1 in enumerate(cuts):
        im = render_state(sheet, prev, t1, px=px)
        dr = ImageDraw.Draw(im)
        fs = max(int(im.width / 50), 12)
        f = _font(fs)
        lines = []
        for e in evs:
            if not (prev < e["t"] <= t1) or e["kind"] in ("enter_blank",):
                continue
            n += 1
            num[e["id"]] = n
            x, y = e["pos"][0] * px, e["pos"][1] * px
            r = px * 3.2
            dr.ellipse([x - r, y - r, x + r, y + r], outline=ANNOT, width=2)
            dr.text((x + r + 2, y - r - fs * 0.2), str(n), fill=ANNOT, font=f)
            # arrows from the cause to this event
            cause = e.get("cause", e.get("wrapped"))
            if cause is None and e["kind"] == "ride":
                cause = next((c["id"] for c in evs if any(a.get("ride") == e["id"] for a in c["answers"])), None)
            if cause is not None and cause in byid:
                c = byid[cause]
                cx, cy = c["pos"][0] * px, c["pos"][1] * px
                dr.line([(cx, cy), (x, y)], fill=ANNOT, width=1)
                v = np.array([x - cx, y - cy])
                L = float(np.linalg.norm(v))
                if L > 1:
                    u = v / L
                    tip = np.array([x, y]) - u * r
                    nrm = np.array([-u[1], u[0]])
                    a1 = tip - u * px * 2.5 + nrm * px * 1.2
                    a2 = tip - u * px * 2.5 - nrm * px * 1.2
                    dr.polygon([tuple(tip), tuple(a1), tuple(a2)], fill=ANNOT)
            how, ans = phrase(e, evs)
            cz = f" (from {num[cause]})" if cause in num else ""
            lines.append(f"{n}  t{e['t']}  {how}{cz}" + (f"  >  {'; '.join(ans)}" if ans else ""))
        # caption
        fs2 = max(int(im.width / 58), 11)
        f2 = _font(fs2)
        cap_h = int(fs2 * 1.45 * (len(lines) + 1.6))
        out = Image.new("RGB", (im.width, im.height + cap_h), of.PAPER)
        out.paste(im, (0, 0))
        d2 = ImageDraw.Draw(out)
        d2.text((8, im.height + 4), f"turns {prev + 1}–{t1}", fill=(0x10, 0x0F, 0x0F), font=_font(int(fs2 * 1.15)))
        for i, l in enumerate(lines):
            d2.text((8, im.height + 6 + int(fs2 * 1.45 * (i + 1.2))), l, fill=(0x40, 0x3E, 0x3C), font=f2)
        panels.append(out)
        prev = t1
    if legend:
        from PIL import Image, ImageDraw
        lg = Image.new("RGB", panels[0].size, of.PAPER)
        d3 = ImageDraw.Draw(lg)
        fs3 = max(int(lg.width / 50), 12)
        y = 10
        for i, l in enumerate(legend):
            d3.text((12, y), l, fill=(0x10, 0x0F, 0x0F) if i == 0 else (0x40, 0x3E, 0x3C),
                    font=_font(int(fs3 * (1.15 if i == 0 else 1.0))))
            y += int(fs3 * 1.55)
        panels.append(lg)
    if len(panels) % 3:
        from PIL import Image, ImageDraw
        whole = render_state(sheet, -1, cuts[-1], px=px)
        out = Image.new("RGB", panels[0].size, of.PAPER)
        out.paste(whole, (0, 0))
        fs4 = max(int(whole.width / 50), 12)
        ImageDraw.Draw(out).text((8, whole.height + 4), "the whole sheet (= the piece)", fill=(0x10, 0x0F, 0x0F),
                                 font=_font(fs4))
        panels.append(out)
    hmax = max(p.height for p in panels)
    panels = [p if p.height == hmax else _pad(p, hmax) for p in panels]
    sheet_im = kit.contact(panels, cols=len(panels) if len(panels) <= 3 else (len(panels) + 1) // 2, title=title)
    sheet_im.save(path, quality=86, optimize=True)
    return path


def _pad(im, h):
    from PIL import Image
    out = Image.new("RGB", (im.width, h), of.PAPER)
    out.paste(im, (0, 0))
    return out


def cuts_of(sheet, after=12):
    """Panel ends: each bold stop (the call), each river arrival + `after` turns (the answer and the
    reply to it), and the end."""
    m = events_of(sheet)
    c = [e["t"] if e["kind"] == "stop" else e["t"] + after for e in m["events"]
         if (e["src"], e["kind"]) in (("bold", "stop"), ("river", "arrive"))]
    end = m["ran"] - 1
    c = sorted(set(x for x in c if x < end - 10)) + [end]          # no near-empty last panel
    return c


LEGEND = [
    "Who listens to what (turn order in each tick: graph, river, bold, wire)",
    "bold stops in a knot > river turns its course and wraps the knot",
    "river has wrapped it > bold rides the river from its knot, leaves at a tangent;",
    "      when tired, bold refuses and turns its back on the river",
    "bold turns sharply > graph plays an earthquake arrival at the clock",
    "graph arrival > wire wakes, crosses, rides the trace, then leaves",
    "wire rides the trace > graph lifts its needle (a gap in the trace)",
    "bold stops > wire comes to look (if free); it never touches bold ink",
    "ignored by rule: river ignores the wire; graph ignores river and wire",
    "ignored by state: a busy, ringing or spent regime lets its cue pass",
    "",
    "orange: annotation only. Faded: drawn in earlier panels.",
]


PIECE = ("v4", 1313)
DUD = ("soup", 1313)
RES = ROOT / "tools/gesture/results"


def final():
    """Rebuild the four review images into tools/gesture/results/ (recipes beside)."""
    from PIL import Image
    rn, sd = PIECE
    r = RECIPES[rn]()
    r["seed"] = sd
    sh = kit.run(r)
    # 1. the piece
    p1 = of.save(sh, RES / "mutual-1-piece.jpg", px_per_mm=7.0, quality=84)
    # 2. the process strip
    c = cuts_of(sh)
    p2 = strip(sh, c, RES / "mutual-2-process.jpg", px=2.55,
               title=f"mutual, seed {sd}: the same run read turn by turn (numbers: events in order; arrows: cause > answer)",
               legend=LEGEND)
    sh.save_recipe(RES / "mutual-2-process.recipe.json")
    # 3. close-up: the ride from knot 1 and the refusal at knot 2
    crop = (30.0, 58.0, 192.0, 178.0)
    p3 = of.save(sh, RES / "mutual-3-closeup.jpg", px_per_mm=12.0, crop=crop, quality=82)
    # 4. the dud
    rn, sd = DUD
    r = RECIPES[rn]()
    r["seed"] = sd
    sd_sh = kit.run(r)
    p4 = of.save(sd_sh, RES / "mutual-4-dud-soup.jpg", px_per_mm=6.0, quality=84)
    for p in (p1, p2, p3, p4):
        im = Image.open(p)
        print(p.name, im.size, round(Path(p).stat().st_size / 1024), "KB")
    (OUT / "final.log.json").write_text(json.dumps(events_of(sh), indent=1, default=float))
    print(describe(events_of(sh)))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "sweep":
        sweep_v(sys.argv[2], [int(x) for x in sys.argv[3].split(",")])
    else:
        main(sys.argv[1:])
