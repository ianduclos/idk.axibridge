"""Run from the repo root with .local/gesture/.venv/bin/python -B.

The single results JSON holds both the normalized recipe and device specs, so
reproduction does not require an extra, unowned .recipe.json in results/.
Additional neutral review views stay in the assigned scratch directory.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "tools/gesture")

from PIL import Image

from gesture import kit
from gesture.kit._devices import apply_devices


RECIPE = {"seed": 4243, "voice": {"id": "drift", "hands": ["hokusai", "meander69"], "length": 6.0}}
DEVICES = [
    {"id": "misfit_grid", "place": "under", "pitch": 14.0, "blur": 8.0,
     "strength": -5.0, "clear": 1.0, "min_stub": 3.0, "pen": 0.15},
    {"id": "arc_ticks", "place": "over", "which": "longest", "every": 16.0,
     "major_every": 5, "tick": 1.1, "offset": 0.9, "label_h": 1.6, "pen": 0.18},
    {"id": "survey_marks", "place": "over", "cross": 1.8, "label_h": 1.5,
     "principal_axis": True, "dash": 3.0, "gap": 2.0, "pen": 0.18},
]
TARGET = Path("tools/gesture/results/measg2-devices.jpg")
SCRATCH = Path(".local/gesture/out/measg2")


def main():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    s = kit.run(RECIPE)
    measured = apply_devices(s, DEVICES)
    # No raster lettering: every visible coordinate and number is an Ink.
    kit.preview(measured, TARGET, label=None, recipe_beside=False, quality=86)
    payload = {"recipe": measured.recipe, "devices": DEVICES,
               "applied_devices": measured.meta["devices"],
               "measurements": {"source_polylines": len(s.inks),
                                "device_polylines": len(measured.inks) - len(s.inks)}}
    TARGET.with_suffix(".json").write_text(json.dumps(payload, indent=2) + "\n")

    # Neutral views for the independent image-first review: a matched control
    # with the gradient disabled and an unmeasured drawing, same frame and scale.
    kit.preview(measured, SCRATCH / "A.jpg", label=None, recipe_beside=False, quality=86)
    control = [dict(spec, strength=0) if spec["id"] == "misfit_grid" else dict(spec) for spec in DEVICES]
    kit.preview(apply_devices(s, control), SCRATCH / "B.jpg", label=None, recipe_beside=False, quality=86)
    kit.preview(s, SCRATCH / "C.jpg", label=None, recipe_beside=False, quality=86)
    with Image.open(TARGET) as image:
        assert image.format == "JPEG" and max(image.size) <= 2400
        dimensions = image.size
    assert TARGET.stat().st_size < 400_000
    print(json.dumps({"image": str(TARGET), "pixels": dimensions,
                      "bytes": TARGET.stat().st_size, **payload["measurements"]}, indent=2))


if __name__ == "__main__":
    main()
