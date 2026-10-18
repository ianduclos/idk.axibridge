"""Round 13, thread II-c `accrue` — exploration runs.

    .local/gesture/.venv/bin/python tools/gesture/experiments/accrue_explore.py <stage> [k=v ...]

Every tile is kit.run + kit.preview (recipe beside it) under
.local/gesture/out/accrue/<stage>/.
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
OUT = ROOT / ".local/gesture/out/accrue"


def recipe(seed=3901, frame=(280.0, 200.0), voice=None, ink=None, renderer=None, margin=6.0):
    v = {"id": "accrue_walk", **(voice or {})}
    mods = [{"id": "accrue_ink", **(ink or {})}] if ink is not False else []
    return {"frame": list(frame), "seed": seed, "margin": margin,
            "parts": [{"voice": v, "modulators": mods}],
            "renderer": renderer or {"id": "wire", "pen": 0.4}}


def tile(stage, name, rec, label=None, px=4.0):
    sheet = kit.run(rec)
    p = OUT / stage / f"{name}.jpg"
    kit.preview(sheet, p, px_per_mm=px, label=label or name)
    ev = sheet.marks[0].meta.get("accrue", {})
    ks = ev.get("knots", [])
    print(f"{name}: L={ev.get('length_mm', 0):.0f}mm knots={len(ks)} at "
          f"{[round(k['s']) for k in ks]} recalls={[(round(r['s']), round(r['from_s'])) for r in ev.get('recalls', [])]}")
    return sheet, kit.render_image(sheet, px_per_mm=px, label=label or name)


def parse(argv):
    kv = {}
    for a in argv:
        k, v = a.split("=", 1)
        try:
            kv[k] = json.loads(v)
        except json.JSONDecodeError:
            kv[k] = v
    return kv


def stage_hands(kv):
    ims = []
    nib = kv.pop("nib", 0)
    seed = kv.pop("seed", 3901)
    frame = kv.pop("frame", [280.0, 200.0])
    ink = kv.pop("ink", {})
    for h in kv.pop("hands", ["river_meander", "dance_fluidity", "marden", "trail_grazer", "mime_monkey_hands",
                              "hokusai"]):
        _, im = tile("hands", h, recipe(seed=seed, frame=frame, voice={"hand": h, **kv}, ink=ink if nib else False,
                                        renderer={"id": "nib", "style": "e", "pen": 0.4} if nib else None))
        ims.append(im)
    kit.contact(ims, 3, title="accrue: hands, wire").save(OUT / "hands" / "contact.jpg", quality=85)


def stage_one(kv):
    seed = kv.pop("seed", 3901)
    name = kv.pop("name", "one")
    ink = kv.pop("ink", {})
    rend = kv.pop("renderer", {"id": "nib", "style": "e", "pen": 0.4})
    frame = kv.pop("frame", [280.0, 200.0])
    tile("one", name, recipe(seed=seed, frame=frame, voice=kv, ink=ink, renderer=rend))




def stage_seeds(kv):
    hand = kv.pop("hand", "river_meander")
    seeds = kv.pop("seeds", [3901, 3902, 3903, 3904, 3905, 3906])
    frame = kv.pop("frame", [290.0, 110.0])
    ink = kv.pop("ink", {})
    tag = kv.pop("tag", hand)
    kv.setdefault("route", "ltr")
    ims = []
    for sd in seeds:
        _, im = tile("seeds", f"{tag}-{sd}", recipe(seed=sd, frame=frame, voice={"hand": hand, **kv}, ink=ink,
                                                    renderer={"id": "nib", "style": "e", "pen": 0.4}), px=5.0)
        ims.append(im)
    kit.contact(ims, 2, title=f"accrue seeds: {tag}").save(OUT / "seeds" / f"contact-{tag}.jpg", quality=85)




def state_chart(sheet, path, title=""):
    """Diagnostic: the body's state along arc length (H, curl, press, |spin|), knots and recalls."""
    import matplotlib  # noqa: PLC0415
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415
    m = sheet.marks[0]
    c = m.channels
    s = c["acc_s"]
    ev = m.meta["accrue"]
    fig, ax = plt.subplots(figsize=(14, 3.2), dpi=110)
    ax.plot(s, c["acc_habit"], label="habit H", color="#205EA6")
    ax.plot(s, c["acc_curl"], label="curl |C|/cmax", color="#AF3029")
    ax.plot(s, c["acc_press"], label="press", color="#66800B")
    ax.plot(s, np.abs(c["acc_spin"]) * 5, label="|spin|×5 rad/mm", color="#BC5215")
    ax.plot(s, c["acc_recall"] * 5, label="recall×5", color="#5E409D", lw=0.8)
    ax.fill_between(s, 0, c["acc_rel"] * 0.15, color="#999", alpha=0.4, label="release")
    for k in ev["knots"]:
        ax.axvline(k["s"], color="k", lw=1.2)
    ax.set_xlim(0, s[-1])
    ax.set_ylim(0, 2.5)
    ax.legend(ncol=6, fontsize=8, loc="upper left")
    ax.set_title(title, fontsize=9)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def stage_chart(kv):
    p = Path(kv["recipe"])
    rec = json.loads(p.read_text())
    sheet = kit.run(rec)
    state_chart(sheet, p.with_name(p.stem.replace(".recipe", "") + "-state.png"), p.stem)


if __name__ == "__main__":
    st = sys.argv[1]
    globals()[f"stage_{st}"](parse(sys.argv[2:]))
