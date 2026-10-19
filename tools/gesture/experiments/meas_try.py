"""Thread D (`meas`): lay devices on a test drawing and write a working image.

    .local/gesture/.venv/bin/python tools/gesture/experiments/meas_try.py <drawing> <out-stem> '<json specs>'
drawing: cat (the catalogue drawing, seed 15310) | 4507 | 14007 | rzoom
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import meas_common as C  # noqa: E402

from gesture.kit._devices import apply_devices  # noqa: E402

NAMES = {"4507": "ccolour-3-4507", "14007": "cimpro-4-sheet-14007", "rzoom": "rzoom-4-ornament"}


def drawing(name: str):
    cache = C.OUT / f"_d-{name}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    sh = C.kit.run(C.catalogue_recipe(int(name[3:]) if name.startswith("cat") and len(name) > 3 else 15310)) \
        if name.startswith("cat") else C.round14(NAMES[name])
    C.OUT.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(sh))
    return sh


if __name__ == "__main__":
    name, stem, specs = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
    px = float(sys.argv[4]) if len(sys.argv) > 4 else 5.0
    out = apply_devices(drawing(name), specs)
    path = C.OUT / f"{stem}.jpg"
    C.render(out, px_per_mm=px).save(path, quality=88)
    C.save_spec(path, {"drawing": name, "devices": specs})
    print(path, out.frame, len(out.inks))
