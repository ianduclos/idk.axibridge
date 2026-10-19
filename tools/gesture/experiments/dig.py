"""Round 16 C `dig`: archaeology further — revivals as v2 relations.

    .local/gesture/.venv/bin/python tools/gesture/experiments/dig.py try [name]
    .local/gesture/.venv/bin/python tools/gesture/experiments/dig.py review

Working images go to .local/gesture/out/dig/; `review` writes the review set
to tools/gesture/results/dig-*.jpg with the score (.recipe.json) and the
played score (.played.json) beside each.
"""
from __future__ import annotations

import copy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "gesture"))

from gesture.kit import _synth as synth  # noqa: E402

OUT = ROOT / ".local" / "gesture" / "out" / "dig"
RES = ROOT / "tools" / "gesture" / "results"
FRAME = [250, 175]


def layer(i, hand, pen, region=None, length=3.0, joins="smooth", renderer=None, mods=None, role="line"):
    d = {"id": f"L{i}", "role": role, "pen": pen,
         "part": {"voice": {"id": "hand", "hand": hand, "length": length, "joins": joins}}}
    if region:
        d["region"] = list(region)
    if renderer:
        d["part"]["renderer"] = renderer
    if mods:
        d["part"]["modulators"] = mods
    return d


def base(seed, rend=None, hands=("dance_thrusting", "trail_miner", "river_bend"), pens=("black", "red", "blue")):
    return {"version": 2, "frame": FRAME, "seed": seed,
            "layers": [layer(0, hands[0], pens[0], [10, 15, 200, 140], 4.0, renderer=rend),
                       layer(1, hands[1], pens[1], [60, 40, 170, 120], 3.0, renderer=rend),
                       layer(2, hands[2], pens[2], [20, 60, 130, 100], 2.5, renderer=rend)],
            "relations": []}


WET = {"id": "dig_wet", "style": "e", "pen": 0.4, "wet": "reference", "fill": "spiral"}


def tries() -> dict:
    out = {}
    s = base(16301, WET)
    s["relations"] = [{"id": "P", "kind": "dig_pool", "src": "*", "dst": "*", "params": {"count": 1}}]
    out["pool"] = s
    s = base(16301)
    s["relations"] = [{"id": "RS", "kind": "dig_restate", "src": "L0", "dst": "L1", "params": {"n": 2}}]
    out["restate"] = s
    s = base(16301)
    s["relations"] = [{"id": "T", "kind": "dig_tremble", "src": "*", "dst": "*"}]
    out["tremble"] = s
    s = base(16301)
    s["relations"] = [{"id": "S", "kind": "dig_stiffen", "src": "*", "dst": "*"}]
    out["stiffen"] = s
    s = base(16301)
    s["relations"] = [{"id": "K", "kind": "dig_knot", "src": "*", "dst": "*"}]
    out["knot"] = s
    return out


def run_one(name, score, path, px=6.0, label=None):
    t = time.time()
    sh = synth.run(score, cache=False)
    synth.preview(sh, path, px_per_mm=px, label=label)
    log = synth.played(sh)["log"]
    outs = {}
    for e in log:
        outs[e["outcome"]] = outs.get(e["outcome"], 0) + 1
    print(f"{name}: {time.time() - t:.2f}s  {outs}  → {path}")
    return sh


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = argv[1] if len(argv) > 1 else "try"
    if cmd == "review":
        review()
        return
    if cmd == "pop":
        for name in argv[2:] or list(HANDS):
            pop(name)
        return
    if cmd == "try":
        want = argv[2:] or None
        for name, s in tries().items():
            if want and name not in want:
                continue
            run_one(name, s, OUT / f"try-{name}.jpg", px=5)




def crop(sheet, at, half=22.0, px=14.0):
    """A close-up (PIL image) of the sheet round `at` (mm)."""
    im = synth.render(sheet, px_per_mm=px)
    x, y = at
    box = [int(max((x - half) * px, 0)), int(max((y - half) * px, 0)),
           int(min((x + half) * px, im.width)), int(min((y + half) * px, im.height))]
    return im.crop(box)


def closeups(name, score, outcomes=None, half=22.0, px=14.0, k=4):
    sh = synth.run(score, cache=False)
    evs = [e for e in synth.played(sh)["log"] if e.get("at") and (outcomes is None or e["outcome"] in outcomes)]
    for i, e in enumerate(evs[:k]):
        crop(sh, e["at"], half, px).save(OUT / f"close-{name}-{i}.jpg", quality=88)
        print(name, i, e)
    return sh


# ---------------------------------------------------------------------------
# the pieces: one score per revival, each a relation in a v2 score
# ---------------------------------------------------------------------------

HANDS = {"pool": ("dance_thrusting", "trail_miner", "river_meander"),
         "restate": ("hokusai", "trail_miner", "river_bend"),
         "tremble": ("dance_thrusting", "trail_miner", "river_bend"),
         "stiffen": ("river_meander", "dance_thrusting", "trail_slime"),
         "knot": ("meander69", "river_bend", "dance_thrusting")}
PENS = {"pool": ("black", "red", "blue"), "restate": ("black", "red", "blue"), "tremble": ("black", "red", "blue"),
        "stiffen": ("black", "blue", "orange"), "knot": ("black", "blue", "red")}


def piece(name, seed) -> dict:
    rend = WET if name == "pool" else None
    s = base(seed, rend, HANDS[name], PENS[name])
    s["label"] = f"dig {name} {seed}"
    if name == "pool":
        s["relations"] = [{"id": "R0", "kind": "dig_pool", "src": "*", "dst": "*",
                           "params": {"size": 11.0, "w_wet": 1.0, "w_coil": 0.0, "sheet_max": 1}}]
    elif name == "restate":
        s["relations"] = [{"id": "R0", "kind": "dig_restate", "src": "L0", "dst": "L1", "params": {"n": 2}},
                          {"id": "R1", "kind": "dig_restate", "src": "L1", "dst": "L2", "params": {"n": 1}}]
    elif name == "tremble":
        s["relations"] = [{"id": "R0", "kind": "dig_tremble", "src": "*", "dst": "*"}]
    elif name == "stiffen":
        s["relations"] = [{"id": "R0", "kind": "dig_stiffen", "src": "*", "dst": "*"}]
    elif name == "knot":
        s["relations"] = [{"id": "R0", "kind": "dig_knot", "src": "*", "dst": "*"}]
    return s


def pop(name, seeds=(16301, 16302, 16303, 16304), px=4.0):
    from gesture import kit  # noqa: PLC0415
    ims = []
    for sd in seeds:
        sh = synth.run(piece(name, sd), cache=False)
        outs = {}
        for e in synth.played(sh)["log"]:
            outs[e["outcome"]] = outs.get(e["outcome"], 0) + 1
        print(name, sd, outs)
        ims.append(synth.render(sh, px_per_mm=px))
    kit.contact(ims, 2, title=f"dig {name} {seeds[0]}-{seeds[-1]}").save(OUT / f"pop-{name}.jpg", quality=85)


COMBO_HANDS = ("river_meander", "dance_thrusting", "trail_slime")
COMBO_PENS = ("black", "blue", "orange")


def combo(seed) -> dict:
    """Four revivals listening at once: an echo, tremor on contact, the
    machine at one contact, and one weight (wet or coiled) at a junction."""
    s = base(seed, WET, COMBO_HANDS, COMBO_PENS)
    s["label"] = f"dig combo {seed}"
    s["relations"] = [
        {"id": "R0", "kind": "dig_restate", "src": "L0", "dst": "L1",
         "params": {"n": 1, "w_shuttle": 0.0, "w_copies": 0.0, "w_echo": 1.0}},
        {"id": "R1", "kind": "dig_tremble", "src": "*", "dst": "*"},
        {"id": "R2", "kind": "dig_stiffen", "src": "L1", "dst": "L2"},
        {"id": "R3", "kind": "dig_pool", "src": "*", "dst": "*", "params": {"size": 11.0, "roundness": 1.0, "sheet_max": 1}}]
    return s


def knot_sparse(seed) -> dict:
    return {"version": 2, "frame": FRAME, "seed": seed, "label": f"dig knot {seed}",
            "layers": [layer(0, "river_meander", "black", [10, 15, 230, 145], 4.0),
                       layer(1, "dance_thrusting", "blue", [30, 30, 200, 130], 3.0)],
            "relations": [{"id": "R0", "kind": "dig_knot", "src": "*", "dst": "*",
                           "params": {"count": 2, "size": 6.0, "side_src": 0.4}}]}


def _save(im, stem, scores, sheets):
    import json  # noqa: PLC0415
    path = RES / f"{stem}.jpg"
    im = im.convert("RGB")
    if max(im.size) > 2400:
        k = 2400 / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)))
    q = 86
    while True:
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size < 390_000 or q <= 50:
            break
        q -= 6
    written = [synth.played(sh)["written"] for sh in sheets]
    played = [{k: v for k, v in synth.played(sh).items() if k != "written"} for sh in sheets]
    rec = written[0] if len(written) == 1 else {"population": written}
    pl = played[0] if len(played) == 1 else {"population": played}
    path.with_suffix(".recipe.json").write_text(json.dumps(rec, indent=1, default=float))
    path.with_suffix(".played.json").write_text(json.dumps(pl, indent=1, default=float))
    print(f"{path.name}: {im.size} {path.stat().st_size // 1000} KB q{q}")


def _label(im, text):
    from PIL import Image, ImageDraw  # noqa: PLC0415
    from gesture.kit import core  # noqa: PLC0415
    fs = max(14, im.width // 70)
    out = Image.new("RGB", (im.width, im.height + int(fs * 2)), core.PAPER)
    out.paste(im, (0, 0))
    ImageDraw.Draw(out).text((int(fs * 0.6), im.height + int(fs * 0.4)), text, fill=core.INK, font=core._font(fs))
    return out


def with_closeups(sh, events, *, px=9.6, half=16.0, cpx=18.0, title=""):
    """The piece, and below it a strip of close-ups at the given events."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    from gesture.kit import core  # noqa: PLC0415
    top = synth.render(sh, px_per_mm=px)
    crops = []
    for e, cap in events:
        c = crop(sh, e["at"], half, cpx)
        crops.append(_label(c, cap))
    if not crops:
        return _label(top, title)
    w = (top.width - 12 * (len(crops) - 1)) // len(crops)
    crops = [c.resize((w, int(c.height * w / c.width))) for c in crops]
    h = max(c.height for c in crops)
    out = Image.new("RGB", (top.width, top.height + 12 + h), core.PAPER)
    out.paste(top, (0, 0))
    x = 0
    for c in crops:
        out.paste(c, (x, top.height + 12))
        ImageDraw.Draw(out).rectangle([x, top.height + 12, x + c.width - 1, top.height + 11 + c.height],
                                      outline=(206, 205, 195))
        x += c.width + 12
    return _label(out, title)


def _first(log, outcome, side=None, k=1):
    evs = [e for e in log if e["outcome"] == outcome and e.get("at") and (side is None or e.get("side") == side)]
    return evs[:k]


def review():
    from gesture import kit  # noqa: PLC0415
    RES.mkdir(parents=True, exist_ok=True)
    seeds = (16301, 16302, 16303, 16304)
    # 1. the population: four revivals in one score, consecutive seeds, not chosen
    shs = [synth.run(combo(sd), cache=False) for sd in seeds]
    ims = [synth.render(sh, px_per_mm=4.6) for sh in shs]
    _save(kit.contact(ims, 2, title="dig 1: echo + tremble + stiffen + one pool (wet or coil), seeds 16301-16304"),
          "dig-1-population", None, shs)
    # 2. the single weight at full strength (combo 16304, the black wet pool), with its events
    sh = shs[3]
    log = synth.played(sh)["log"]
    ev = (_first(log, "pool_over") or _first(log, "pool_under"))
    ev = [(ev[0], "the pool: one weight, at a junction")] if ev else []
    ev += [(e, "tremble near the other line") for e in _first(log, "tremble", "dst", 1)]
    ev += [(e, "the machine at the contact") for e in _first(log, "stiffen")]
    ev += [(e, "echo of the black's sweep") for e in _first(log, "echo")]
    _save(with_closeups(sh, ev, title="dig 2: combo 16304 — the single wet weight at full strength, and its events"),
          "dig-2-weight", None, [sh])
    # 3. restate
    sh = synth.run(piece("restate", 16301), cache=False)
    log = synth.played(sh)["log"]
    ev = [(e, f"{e['outcome']} ({e['src']} restated by {e['dst']})") for e in log if e["kind"] == "dig_restate"]
    _save(with_closeups(sh, ev, half=20.0, cpx=14.0,
                        title="dig 3: restate 16301 — a later voice restates an earlier one's sweep (shuttle / copies / echo)"),
          "dig-3-restate", None, [sh])
    # 4. tremble
    sh = synth.run(piece("tremble", 16301), cache=False)
    log = synth.played(sh)["log"]
    ev = [(e, "tremble") for e in _first(log, "tremble", "dst", 2)] + [(e, "still") for e in _first(log, "still", "dst", 2)]
    _save(with_closeups(sh, ev, half=14.0, cpx=20.0,
                        title="dig 4: tremble 16301 — near the other line the dst trembles (or goes still)"),
          "dig-4-tremble", None, [sh])
    # 5. stiffen
    sh = synth.run(piece("stiffen", 16301), cache=False)
    log = synth.played(sh)["log"]
    ev = [(e, f"stiffen: {e['grammar']}, {e['where']}") for e in _first(log, "stiffen", None, 3)]
    _save(with_closeups(sh, ev, half=16.0, cpx=18.0,
                        title="dig 5: stiffen 16301 — the machine at the point of contact, then the hand resumes"),
          "dig-5-stiffen", None, [sh])
    # 6. the dud: knot
    shs = [synth.run(knot_sparse(sd), cache=False) for sd in seeds]
    ims = [synth.render(sh, px_per_mm=4.6) for sh in shs]
    _save(kit.contact(ims, 2, title="dig 6 (dud): knot — a learned oxbow lassoed round a crossing, seeds 16301-16304"),
          "dig-6-knot-dud", None, shs)


if __name__ == "__main__":
    main(sys.argv)
