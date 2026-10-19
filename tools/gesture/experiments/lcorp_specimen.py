"""lcorp: the zoom across the library (working sheets + measures).

Run from the repo root:
    .local/gesture/.venv/bin/python tools/gesture/experiments/lcorp_specimen.py [reveal] [zoom]
Writes .local/gesture/out/lcorp/specimen/*.jpg and measures.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "tools/gesture")
from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402

OUT = Path(".local/gesture/out/lcorp/specimen")


def sources():
    out = [("river", {"source": "river"})]
    for e in L.entries("hand"):
        if e["policy"] == "generative":
            out.append((e["id"], {"source": "hand", "hand": e["id"]}))
    for e in L.entries("dance_trail"):
        out.append(("dance:" + e["id"], {"source": "dance", "trail": e["id"], "effector": "rhand"}))
    return out


def recipe(src: dict, *, reveal, zoom, seed=1491, schedule="push", frame=(600, 150)):
    v = {"id": "lcorp_zoom", "zoom": zoom, "schedule": schedule, "reveal": reveal, **src}
    return {"frame": list(frame), "seed": seed, "margin": 8, "voice": v, "renderer": {"id": "wire", "pen": 0.3}}


def main():
    reveal = float(sys.argv[1]) if len(sys.argv) > 1 else 0.4
    zoom = float(sys.argv[2]) if len(sys.argv) > 2 else 16.0
    OUT.mkdir(parents=True, exist_ok=True)
    meas, ims = {}, []
    for name, src in sources():
        sh = kit.run(recipe(src, reveal=reveal, zoom=zoom))
        m = sh.marks[0]
        meas[name] = dict(m.meta["measure"])
        meas[name]["drawn_mm"] = round(m.meta["drawn_mm"])
        ims.append(kit.render_image(sh, px_per_mm=2.0, label=f"{name}  contrast {m.meta['measure']['contrast']}  inner {m.meta['measure']['inner']}"))
    for i in range(0, len(ims), 12):
        kit.contact(ims[i:i + 12], 2).save(OUT / f"r{reveal:g}_z{zoom:g}_{i // 12}.jpg", quality=85)
    (OUT / f"measures_r{reveal:g}_z{zoom:g}.json").write_text(json.dumps(meas, indent=1))


if __name__ == "__main__":
    main()
