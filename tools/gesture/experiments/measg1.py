"""Reproduce the three general measuring devices; run from the repo root.

    PYTHONDONTWRITEBYTECODE=1 .local/gesture/.venv/bin/python tools/gesture/experiments/measg1.py

The single JSON sidecar contains the normalized recipe AND device specs, keeping
this experiment within its assigned file ownership (no extra .recipe.json).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "tools/gesture")

from gesture import kit  # noqa: E402
from gesture.kit._devices import _drawing_box, apply_devices  # noqa: E402


SPECS = [
    {"id": "scale_ruler", "place": "margin", "side": "bottom", "size": 22.0,
     "anchor": "drawing", "label_h": 1.5, "pen": 0.2},
    {"id": "density_isoline", "place": "over", "cell": 1.5, "sigma": 3.0,
     "levels": 3, "min_length": 8.0, "pen": 0.18},
    {"id": "heading_rose", "place": "beside", "side": "right", "size": 66.0,
     "bins": 36, "smooth": 1.0, "pen": 0.2},
]
OUT = Path("tools/gesture/results/measg1-devices.jpg")
BOTTOM_MARGIN_MM = 22.0


def build():
    s = kit.run({"seed": 4242, "voice": {"id": "drift", "hands": ["hokusai", "meander69"], "length": 6.0}})
    # The source drawing uses the full frame height. Extend the paper below
    # it, preserving every source point and its true scale, to provide an
    # actual blank bottom margin instead of colliding with its last strokes.
    s = kit.Sheet((s.frame[0], s.frame[1] + BOTTOM_MARGIN_MM),
                  list(s.marks), list(s.inks), dict(s.meta))
    return apply_devices(s, SPECS)


def main():
    sheet = build()
    # The plotter text is already Ink geometry. Omit the preview's optional
    # font-rendered recipe strip; the complete recipe lives in the sidecar.
    kit.preview(sheet, "tools/gesture/results/measg1-devices.jpg", px_per_mm=6,
                label=None, recipe_beside=False, quality=85)
    from PIL import Image
    with Image.open(OUT) as im:
        image_size = list(im.size)
    if max(image_size) > 2400 or OUT.stat().st_size >= 400_000:
        raise RuntimeError("Preview exceeds the experiment's image budget")
    counts = {spec["id"]: sum(k.meta.get("device") == spec["id"] for k in sheet.inks) for spec in SPECS}
    contours = [k for k in sheet.inks if k.meta.get("device") == "density_isoline"]
    rose = next(k for k in sheet.inks if k.meta.get("role") == "heading")
    sidecar = {
        "recipe": sheet.recipe,
        "paper_extension_mm": {"bottom": BOTTOM_MARGIN_MM},
        "devices": SPECS,
        "applied_devices": sheet.meta["devices"],
        "drawing_box_mm": list(_drawing_box(sheet)),
        "frame_mm": list(sheet.frame),
        "readings": {"ink_counts": counts, "contour_lengths_mm": [k.meta["length_mm"] for k in contours],
                     "density_levels": sorted({k.meta["level"] for k in contours}),
                     "heading_histogram_mm": rose.meta["histogram_mm"],
                     "total_mark_length_mm": rose.meta["total_length_mm"]},
        "preview": {"path": str(OUT), "size_px": image_size, "bytes": OUT.stat().st_size},
    }
    OUT.with_suffix(".json").write_text(json.dumps(sidecar, indent=2) + "\n")
    print(json.dumps({"preview": sidecar["preview"], "device_inks": counts,
                      "drawing_box_mm": sidecar["drawing_box_mm"]}, indent=2))


if __name__ == "__main__":
    main()
