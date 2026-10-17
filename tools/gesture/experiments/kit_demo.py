"""Gesture kit demo: four recipes on one 2×2 sheet.

    .local/gesture/.venv/bin/python -m tools.gesture.experiments.kit_demo

1. the Hand Drift bench default — matisse → shikasta → lichtenberg drift,
   seed 7000, smooth joins, wire;
2. the same route with chain joins, danced by Staccato, inked with nib e;
3. a grid of four single hands at one common scale (the bench's "each");
4. polyphony on one surface: a Hokusai → nasta'liq interp drift under a
   noise-front field inked with nib lanes (c), crossed by a bubble-chamber
   hand in chain joins kept as a dry wire (its own renderer).

Each recipe JSON is saved beside its image in .local/gesture/out/kit/
(<name>.recipe.json, by kit.preview); the
sheet goes to tools/gesture/results/kit-demo-2026-10-17.jpg.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / ".local/gesture/out/kit"
SHEET = HERE / "results/kit-demo-2026-10-17.jpg"

BENCH = ["matisse", "shikasta", "lichtenberg"]
RECIPES = {
    "1-bench-default": {
        "label": "1  bench default: matisse > shikasta > lichtenberg drift, seed 7000, wire",
        "frame": [267, 180], "seed": 7000,
        "parts": [{"voice": {"id": "drift", "hands": BENCH, "joins": "smooth"}, "modulators": []}],
        "renderer": {"id": "wire", "pen": 0.4}},
    "2-chain-staccato-nib-e": {
        "label": "2  same route, chain joins, danced by Staccato, nib e",
        "frame": [267, 180], "seed": 7000,
        "parts": [{"voice": {"id": "drift", "hands": BENCH, "joins": "chain"},
                   "modulators": [{"id": "timing", "tempo": "staccato"}]}],
        "renderer": {"id": "nib", "style": "e", "pen": 0.4}},
    "3-grid-each": {
        "label": "3  grid of four single hands at one scale: matisse, shikasta, lichtenberg, bubble (bench 'each')",
        "frame": [267, 180], "seed": 7000, "arranger": {"id": "grid"},
        "parts": [{"voice": {"id": "hand", "hand": h}} for h in ("matisse", "shikasta", "lichtenberg", "bubble")],
        "renderer": {"id": "wire", "pen": 0.4}},
    "4-polyphony": {
        "label": "4  one surface, two voices: hokusai > nastaliq interp drift under a noise field (nib c) "
                 "x bubble hand, chain joins, dry wire",
        "frame": [267, 180], "seed": 7300,
        "parts": [
            {"label": "field drift",
             "voice": {"id": "drift", "hands": ["hokusai", "nastaliq"], "blend": "interp", "length": 5.0},
             "modulators": [{"id": "constant", "r": None, "W": 3.0, "M": 8.0},
                            {"id": "field", "preset": "noise", "scale": 0.16, "amount": 0.75}],
             "renderer": {"id": "nib", "style": "c", "pen": 0.4}},
            {"label": "machine wire",
             "voice": {"id": "hand", "hand": "bubble", "length": 4.0, "joins": "chain"},
             "modulators": [{"id": "wire"}],
             "renderer": {"id": "wire", "pen": 0.3}}],
        "renderer": {"id": "wire", "pen": 0.4}},
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    images = []
    for name, recipe in RECIPES.items():
        t = time.perf_counter()
        sheet = kit.run(recipe)
        path = kit.preview(sheet, OUT / f"{name}.jpg", px_per_mm=4.0, label=recipe["label"])
        images.append(kit.render_image(sheet, px_per_mm=4.0, label=recipe["label"]))
        print(f"{name:<24} {len(sheet.inks):5d} inks  {time.perf_counter() - t:5.1f} s  "
              f"library {[e['id'] for e in sheet.meta['library']]}  -> {path.relative_to(ROOT)}")
    title = ("gesture kit, 2026-10-17: four recipes from one library "
             "(voices / modulators / renderers / arrangers; recipe JSON beside each image in .local/gesture/out/kit)")
    sheet_img = kit.contact(images, 2, title=title)
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    for q in (88, 80, 72, 64):
        sheet_img.save(SHEET, quality=q, optimize=True)
        if SHEET.stat().st_size < 1_000_000:
            break
    print(f"sheet -> {SHEET.relative_to(ROOT)} ({SHEET.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
