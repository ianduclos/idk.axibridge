"""Contact sheets of the synthetic scenes and of the nulls of a Matisse-like
scene, for eyeballing. Writes PNGs to .local/gesture/out/synth/.

    cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.show_synth
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from gesture import nulls, synth

OUT = Path(__file__).resolve().parents[3] / ".local" / "gesture" / "out" / "synth"
SIZE = (900, 700)


def sheet(tiles: list[tuple[str, np.ndarray]], cols: int, path: Path) -> None:
    h, w = tiles[0][1].shape
    rows = (len(tiles) + cols - 1) // cols
    pad, label = 12, 22
    img = Image.new("L", (cols * (w + pad) + pad, rows * (h + pad + label) + pad), 128)
    dr = ImageDraw.Draw(img)
    for i, (name, arr) in enumerate(tiles):
        x = pad + (i % cols) * (w + pad)
        y = pad + (i // cols) * (h + pad + label)
        dr.text((x, y + 4), name, fill=255)
        img.paste(Image.fromarray(arr), (x, y + label))
    img.save(path)
    print(f"wrote {path}  ({img.size[0]}×{img.size[1]})")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    scenes = [
        ("x_crossing", synth.scene_x_crossing(SIZE)),
        ("t_junction", synth.scene_t_junction(SIZE)),
        ("closed_loop", synth.scene_closed_loop(SIZE)),
        ("random (8, jitter 0.25)", synth.scene_random(rng, SIZE, 8)),
        ("matisse_like", synth.scene_matisse_like(np.random.default_rng(7), SIZE)),
        ("matisse_like (ink noise)", synth.scene_matisse_like(np.random.default_rng(8), SIZE)),
    ]
    tiles = []
    for i, (name, d) in enumerate(scenes):
        kw = {"width_jitter": 0.25} if "jitter" in name else {}
        if "ink noise" in name:
            kw = {"ink_noise": 0.35, "paper_noise": 0.06}
        tiles.append((name, synth.render(d, seed=i, **kw)))
    sheet(tiles, 3, OUT / "scenes.png")

    src = synth.scene_matisse_like(np.random.default_rng(7), SIZE)
    tiles = [("source: matisse_like", synth.render(src, seed=0))]
    for name, fn in nulls.NULLS.items():
        nd = fn(src, np.random.default_rng(1))
        tiles.append((f"{name}  (overflow {nd.meta['overflow']})", synth.render(nd, seed=0)))
    sheet(tiles, 3, OUT / "nulls_matisse.png")


if __name__ == "__main__":
    main()
