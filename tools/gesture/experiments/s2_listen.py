"""Synthesis bench S2a: listen as a score writer, judged against round-15 listen and integ16.

    .local/gesture/.venv/bin/python tools/gesture/experiments/s2_listen.py            # all three
    .local/gesture/.venv/bin/python tools/gesture/experiments/s2_listen.py population # or ripple / recompose

Images go to `.local/gesture/out/s2listen/`; every v2 cell is written with `synth.preview`, so its
written score (<stem>.recipe.json, playable) and played score (<stem>.played.json) sit beside it.

(a) population  seeds 15101–15108, unpicked; each row: round-15 listen / integ16 at the same balance
                (`integ16.dial`) / the score written by `writers_listen` — one sheet at balance
                `one`, one at `speakers`.
(b) ripple      one seed: the written score; speaker X's hand swapped (its listeners follow); the
                same edit with the speaker's first listener pinned first (`synth.pin`).
(c) recompose   one speaker locked (pinned), three new seeds recomposed around it.
"""
from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from PIL import Image, ImageDraw  # noqa: E402

from experiments import integ16  # noqa: E402
from gesture import kit  # noqa: E402
from gesture.kit import _synth as synth  # noqa: E402
from gesture.kit import arrangers_listen as al  # noqa: E402
from gesture.kit import core  # noqa: E402
from gesture.kit._writers import compose, recompose  # noqa: E402
from gesture.kit.arrangers_ccolour import render_pens  # noqa: E402

OUT = HERE.parents[1] / ".local/gesture/out/s2listen"
SEEDS = range(15101, 15109)
PX = 2.4
LIMIT = 400_000
TIMES: dict = {}


def labelled(im, label):
    fs = max(12, int(im.width / 60))
    strip = Image.new("RGB", (im.width, int(fs * 2.0)), core.PAPER)
    ImageDraw.Draw(strip).text((int(fs * 0.6), int(fs * 0.45)), label, fill=core.INK, font=core._font(fs))
    full = Image.new("RGB", (im.width, im.height + strip.height), core.PAPER)
    full.paste(im, (0, 0))
    full.paste(strip, (0, im.height))
    return full


def save_under(im, path, limit=LIMIT):
    """JPEG under `limit` bytes: lower the quality, then the size."""
    path = Path(path)
    for scale in (1.0, 0.85, 0.72, 0.6, 0.5, 0.42):
        cur = im if scale == 1.0 else im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        for q in (85, 78, 70, 62, 55):
            cur.save(path, quality=q, optimize=True)
            if path.stat().st_size <= limit:
                return path, scale, q
    return path, scale, q


def write(seed, balance, **params):
    frame = al.recipe(seed)["frame"]
    t0 = time.perf_counter()
    s = compose("listen", frame=frame, seed=seed, params={"balance": balance, **params})
    t1 = time.perf_counter()
    synth.clear_cache()
    sh = synth.run(s, cache=False)
    t2 = time.perf_counter()
    TIMES.setdefault("written", []).append({"seed": seed, "balance": balance, "write_s": round(t1 - t0, 2),
                                            "play_s": round(t2 - t1, 2), "layers": len(s["layers"])})
    return s, sh


def cell(sheet, path, label):
    synth.preview(sheet, path, px_per_mm=PX, label=label)
    return Image.open(path).convert("RGB")


def population():
    d = OUT / "a"
    d.mkdir(parents=True, exist_ok=True)
    r15 = {}
    for balance in ("one", "speakers"):
        cells = []
        for seed in SEEDS:
            if seed not in r15:
                r15[seed] = labelled(render_pens(kit.run(al.recipe(seed)), px_per_mm=PX), f"{seed} · round-15 listen")
            cells.append(r15[seed])
            t0 = time.perf_counter()
            ish = synth.run(integ16.score(seed, cls=integ16.dial(balance)))
            TIMES.setdefault("integ16", []).append({"seed": seed, "balance": balance,
                                                    "s": round(time.perf_counter() - t0, 2)})
            cells.append(cell(ish, d / f"integ16-{balance}-{seed}.jpg", f"{seed} · integ16 dial {balance}"))
            s, sh = write(seed, balance)
            cells.append(cell(sh, d / f"written-{balance}-{seed}.jpg", f"{seed} · written score, balance {balance}"))
            print(seed, balance, TIMES["written"][-1], flush=True)
        sheet = kit.contact(cells, 3, title=f"S2a · left: round-15 listen · middle: integ16, dial {balance} · right: "
                                            f"listen as a score writer, balance {balance} · 15101–15108, unpicked")
        print(save_under(sheet, OUT / f"s2listen-a-{balance}.jpg"))


def _swap(score, lid, hand):
    s = copy.deepcopy(score)
    s.pop("parts", None)
    for L in s["layers"]:
        if L["id"] == lid:
            L["part"]["voice"] = {**L["part"]["voice"], "hand": hand}
    return s


def ripple(seed=15102, balance="one"):
    d = OUT / "b"
    d.mkdir(parents=True, exist_ok=True)
    s, sh = write(seed, balance)
    rels = s["decisions"]["writers"][0]["decisions"]["relations"]
    roles = {L["id"]: L["role"] for L in s["layers"]}
    heard = [r for r in rels if isinstance(r["src"], str) and roles.get(r["src"]) == "speaker"]
    spk = max(sorted({r["src"] for r in heard}), key=lambda x: sum(r["src"] == x for r in heard))
    lis = next(r["layer"] for r in heard if r["src"] == spk)
    L = next(x for x in s["layers"] if x["id"] == spk)
    old = L["part"]["voice"]["hand"]
    pool = al.LISTEN_HANDS
    new = pool[(pool.index(old) + 3) % len(pool)] if old in pool else pool[0]
    edited = synth.run(_swap(s, spk, new), cache=False)
    pinned = synth.pin(s, [lis])
    held = synth.run(_swap(pinned, spk, new), cache=False)
    cells = [cell(sh, d / f"ripple-{seed}-0-written.jpg", f"{seed} · written ({spk}: {old})"),
             cell(edited, d / f"ripple-{seed}-1-swapped.jpg", f"{spk}'s hand to {new}: its listeners follow"),
             cell(held, d / f"ripple-{seed}-2-pinned.jpg", f"the same edit, {lis} pinned first")]
    sheet = kit.contact(cells, 3, title=f"S2a edit ripple · {seed} · speaker {spk} {old} to {new}; "
                                        f"{lis} hears {spk} (right: {lis} pinned)")
    print(save_under(sheet, OUT / "s2listen-b-ripple.jpg"))
    return {"seed": seed, "speaker": spk, "hand": [old, new], "listener": lis}


def recomposing(seed=15106, balance="one", seeds=(15201, 15202, 15203)):
    d = OUT / "c"
    d.mkdir(parents=True, exist_ok=True)
    s, sh = write(seed, balance)
    spk = next(L["id"] for L in s["layers"] if L["role"] == "speaker")
    pinned = synth.pin(s, [spk])
    cells = [cell(sh, d / f"recompose-{seed}-0.jpg", f"{seed} · written; {spk} locked")]
    for k in seeds:
        t0 = time.perf_counter()
        again = recompose(pinned, locked=[spk], seed=k)
        t1 = time.perf_counter()
        synth.clear_cache()
        ash = synth.run(again, cache=False)
        TIMES.setdefault("recompose", []).append({"seed": k, "write_s": round(t1 - t0, 2),
                                                  "play_s": round(time.perf_counter() - t1, 2)})
        cells.append(cell(ash, d / f"recompose-{seed}-{k}.jpg", f"recomposed, seed {k}; {spk} kept"))
    sheet = kit.contact(cells, 2, title=f"S2a recompose · {seed}: speaker {spk} locked, three new seeds around it")
    print(save_under(sheet, OUT / "s2listen-c-recompose.jpg"))
    return {"seed": seed, "locked": spk, "seeds": list(seeds)}


def main(which=("population", "ripple", "recompose")):
    OUT.mkdir(parents=True, exist_ok=True)
    info = {}
    if "population" in which:
        population()
    if "ripple" in which:
        info["ripple"] = ripple()
    if "recompose" in which:
        info["recompose"] = recomposing()
    (OUT / "s2listen-times.json").write_text(json.dumps({"times": TIMES, **info}, indent=1))
    print(json.dumps(info))


if __name__ == "__main__":
    main(tuple(sys.argv[1:]) or ("population", "ripple", "recompose"))
