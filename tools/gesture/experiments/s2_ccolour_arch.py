"""S2b (synthesis bench): ccolour and arch as score writers, beside their own composers.

    .local/gesture/.venv/bin/python tools/gesture/experiments/s2_ccolour_arch.py            # everything
    .local/gesture/.venv/bin/python tools/gesture/experiments/s2_ccolour_arch.py pop ccolour|arch
    .local/gesture/.venv/bin/python tools/gesture/experiments/s2_ccolour_arch.py ripple
    .local/gesture/.venv/bin/python tools/gesture/experiments/s2_ccolour_arch.py two

Images go to .local/gesture/out/s2arch/: each writer sheet through `synth.preview` (its written score
<stem>.recipe.json and played score <stem>.played.json beside it), each composer sheet beside it, contact
sheets (`kit.contact`) of the pairs. Seeds are fresh and unpicked: ccolour 4541–4548 (round 14 used
4501–4524), arch 15041–15048 (round 15 used 15001–15010).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit import arrangers_arch as ar  # noqa: E402
from gesture.kit import arrangers_ccolour as cc  # noqa: E402
from gesture.kit._writers import compose  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/s2arch"
SEEDS = {"ccolour": range(4541, 4549), "arch": range(15041, 15049)}
MAX_KB = 400
PX = 4.0


def save_small(im, path, quality=84):
    """A JPG under MAX_KB (quality stepped down, then the image halved if it must be)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    q = quality
    while True:
        im.save(path, quality=q, optimize=True)
        if path.stat().st_size <= MAX_KB * 1000:
            return path
        if q > 50:
            q -= 8
        else:
            im = im.resize((im.width * 3 // 4, im.height * 3 // 4))


def preview_small(sheet, path, label=None):
    """synth.preview (the written and played scores beside the image), the JPG then kept under MAX_KB."""
    synth.preview(sheet, path, px_per_mm=PX)
    im = synth.render(sheet, px_per_mm=PX)
    return save_small(labelled(im, label) if label else im, path)


def labelled(im, text):
    from PIL import Image, ImageDraw  # noqa: PLC0415
    from gesture.kit.core import INK, PAPER, _font  # noqa: PLC0415
    fs = max(13, im.width // 60)
    strip = Image.new("RGB", (im.width, int(fs * 2.0)), PAPER)
    ImageDraw.Draw(strip).text((int(fs * 0.5), int(fs * 0.45)), text, fill=INK, font=_font(fs))
    full = Image.new("RGB", (im.width, im.height + strip.height), PAPER)
    full.paste(im, (0, 0))
    full.paste(strip, (0, im.height))
    return full


def fit_width(im, w):
    return im if im.width == w else im.resize((w, int(im.height * w / im.width)))


def summary(sheet):
    pl = synth.played(sheet)
    kinds = {}
    for e in pl["log"]:
        if e["outcome"] in ("silent", "spent", "cross"):
            continue
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    return kinds


def pair(writer, seed):
    mod = cc if writer == "ccolour" else ar
    rec = mod.recipe(seed)
    t0 = time.perf_counter()
    old = kit.run(rec)
    t1 = time.perf_counter()
    score = compose(writer, frame=rec["frame"], seed=seed)
    t2 = time.perf_counter()
    new = synth.run(score, cache=False)
    t3 = time.perf_counter()
    a = cc.render_pens(old, px_per_mm=PX)
    save_small(a, OUT / f"{writer}-{seed}-composer.jpg")
    old.save_recipe(OUT / f"{writer}-{seed}-composer.recipe.json")
    preview_small(new, OUT / f"{writer}-{seed}-writer.jpg", f"{writer} writer · seed {seed}")
    k = summary(new)
    pens = {x: k.get(x, 0) for x in ("carry", "ride", "reverse", "spill", "touch") if k.get(x)}
    info = {"seed": seed, "frame": rec["frame"], "composer_s": round(t1 - t0, 2), "compose_s": round(t2 - t1, 3),
            "play_s": round(t3 - t2, 2), "layers": len(score["layers"]), "relations": len(score["relations"]),
            "pen_events": pens, "catches": k.get("catch", 0), "answers": k.get("answer", 0)}
    w = 900
    cap_a = f"{seed} composer ({info['composer_s']} s)"
    cap_b = (f"{seed} writer: {info['layers']} layers, {info['relations']} relations ({info['play_s']} s) · pens "
             + (", ".join(f"{a} {b}" for a, b in pens.items()) or "none"))
    return labelled(fit_width(a, w), cap_a), labelled(fit_width(synth.render(new, px_per_mm=PX), w), cap_b), info


def pop(writer):
    tiles, infos = [], []
    for seed in SEEDS[writer]:
        a, b, info = pair(writer, seed)
        print(writer, json.dumps(info))
        infos.append(info)
        tiles += [a, b]
    for half in (0, 1):                        # two contact sheets of four pairs each; rows keep their own height
        s = list(SEEDS[writer])[half * 4:(half + 1) * 4]
        rows = [kit.contact(tiles[i:i + 2], 2) for i in range(half * 8, (half + 1) * 8, 2)]
        im = stack(rows, f"{writer}: composer (left) beside the score it writes, played (right) · "
                         f"seeds {s[0]}–{s[-1]}, unpicked")
        save_small(im, OUT / f"pop-{writer}-{half + 1}.jpg")
    (OUT / f"pop-{writer}.json").write_text(json.dumps(infos, indent=1))
    return infos


def stack(rows, title):
    """Rows (each a kit.contact of one pair) stacked at their own heights under a title."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    from gesture.kit.core import INK, PAPER, _font  # noqa: PLC0415
    w = max(r.width for r in rows)
    fs = max(14, w // 90)
    th = int(fs * 2.2)
    out = Image.new("RGB", (w, th + sum(r.height for r in rows)), PAPER)
    ImageDraw.Draw(out).text((16, int(fs * 0.6)), title, fill=INK, font=_font(fs))
    y = th
    for r in rows:
        out.paste(r, (0, y))
        y += r.height
    return out


def ripple(seed=4545):
    """Edits ripple ("Follow"): swap the hand of a made line that later lines hear; they re-derive from it.
    Pinned, a hearing line holds still."""
    rec = cc.recipe(seed)
    score = compose("ccolour", frame=rec["frame"], seed=seed, params={"density": 0.45})
    made = [L for L in score["layers"] if L["role"] == "made"]
    hears = {R["dst"]: (R["src"] if isinstance(R["src"], list) else [R["src"]])
             for R in score["relations"] if R["kind"] == "catch"}
    edit = next(L["id"] for L in made if any(L["id"] in v for k, v in hears.items()))
    followers = [k for k, v in hears.items() if edit in v]
    old_hand = next(L for L in made if L["id"] == edit)["part"]["voice"]["hand"]
    new_hand = "hokusai" if old_hand != "hokusai" else "river_bend"

    def swapped(s):
        s = json.loads(json.dumps(s))
        for L in s["layers"]:
            if L["id"] == edit:
                L["part"]["voice"]["hand"] = new_hand
        s.pop("parts", None)
        return s
    pinned = synth.pin(score, followers[:1])
    a = synth.run(score, cache=False)
    b = synth.run(swapped(score), cache=False)
    c = synth.run(swapped(pinned), cache=False)
    for sh, tag in ((a, "before"), (b, "follow"), (c, "pinned")):
        preview_small(sh, OUT / f"ripple-{seed}-{tag}.jpg", f"seed {seed} · {tag}")
    w = 900
    ims = [labelled(fit_width(synth.render(a, px_per_mm=PX), w), f"{seed}: as written ({edit} speaks {old_hand})"),
           labelled(fit_width(synth.render(b, px_per_mm=PX), w),
                    f"{edit} now speaks {new_hand}: {', '.join(followers)} hear it and follow"),
           labelled(fit_width(synth.render(c, px_per_mm=PX), w),
                    f"the same edit with {followers[0]} locked (pinned): it holds still")]
    save_small(kit.contact(ims, 3, title=f"ccolour writer · edit ripple · seed {seed}"), OUT / f"ripple-{seed}.jpg")
    print("ripple", edit, old_hand, "→", new_hand, "followers", followers)


def two(seed=15201):
    """Two writers on one sheet: listen in the left half, arch in the right (crossings between them by each
    writer's own awareness relations)."""
    W, H = 300.0, 200.0
    left, right = [5.0, 5.0, 142.5, 190.0], [152.5, 5.0, 142.5, 190.0]
    try:
        g = compose("listen", frame=[W, H], seed=seed, region=left)
        first = "listen"
    except Exception as e:                    # noqa: BLE001 — listen is another thread's work in progress
        print("listen writer failed, ccolour instead:", type(e).__name__, e)
        g = compose("ccolour", frame=[W, H], seed=seed, region=left)
        first = "ccolour"
    both = compose("arch", frame=[W, H], seed=seed + 1, region=right, ground=g)
    t = time.perf_counter()
    sh = synth.run(both, cache=False)
    print("two", first, "+ arch", round(time.perf_counter() - t, 2), "s", len(both["layers"]), "layers")
    preview_small(sh, OUT / f"two-{first}-arch-{seed}.jpg",
                  f"{first} (left) and arch (right) written onto one sheet · seed {seed}")


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    what = argv[0] if argv else "all"
    if what in ("pop", "all"):
        for w in ([argv[1]] if what == "pop" and len(argv) > 1 else ["ccolour", "arch"]):
            pop(w)
    if what in ("ripple", "all"):
        ripple()
    if what in ("two", "all"):
        two()


if __name__ == "__main__":
    main(sys.argv[1:])
