"""S2: every built-in Gesture Study as a sealed layer beside a marden hand, one contact sheet.

Run from the repo root: .local/gesture/.venv/bin/python tools/gesture/experiments/s2_sealed.py
Writes .local/gesture/out/s2sealed/sealed.jpg (under 400 KB). Studies are read as JSON data only.
"""
import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw  # noqa: E402
from gesture import kit  # noqa: E402
from gesture.kit import _synth as synth  # noqa: E402

STUDIES = REPO / "axibridge" / "sources" / "_gesture_studies" / "studies"
OUT = REPO / ".local" / "gesture" / "out" / "s2sealed"
FRAME, REGION = [250, 175], [125, 10, 115, 155]
PX = 3


def build(recipe):
    composer = {k: copy.deepcopy(v) for k, v in recipe.items() if k not in ("frame", "seed")}
    return {"version": 2, "frame": FRAME, "seed": 16001,
            "layers": [{"id": "A", "pen": "black", "part": {"voice": {"id": "hand", "hand": "marden"}}},
                       {"id": "S", "role": "sealed", "pen": "blue", "region": REGION, "composer": composer}],
            "relations": [{"id": "X", "kind": "crossing", "src": "*", "dst": "*"}]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cells = []
    for sid in json.loads((STUDIES / "index.json").read_text())["order"]:
        d = json.loads((STUDIES / sid / "study.json").read_text())
        if d.get("engine") != "kit":
            print(f"skip {sid}: engine {d.get('engine')!r}")
            continue
        t0 = time.time()
        try:
            im = synth.render(synth.run(build(d["recipe"]), cache=False), px_per_mm=PX).convert("RGB")
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {sid}: {type(e).__name__}: {e}")
            continue
        dr = ImageDraw.Draw(im)
        dr.text((8, 6), sid, fill=(16, 15, 15))
        cells.append(im)
        print(f"{sid}: {time.time() - t0:.1f}s")
    sheet = kit.contact(cells, 4, title="Gesture Studies as sealed layers (A = marden hand, S = study in region)")
    p = OUT / "sealed.jpg"
    width = sheet.width
    while True:                                    # shrink until the file is under 400 KB at a decent quality
        im = sheet if width == sheet.width else sheet.resize((width, round(sheet.height * width / sheet.width)),
                                                             Image.LANCZOS)
        im.save(p, quality=72, optimize=True)
        if p.stat().st_size < 400_000 or width < 800:
            break
        width = int(width * 0.88)
    q = 72
    print(p, p.stat().st_size // 1024, "KB, q", q, sheet.size)


if __name__ == "__main__":
    main()
