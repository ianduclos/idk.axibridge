"""Two synthetic "artists" for self-testing the panel + discrimination run
before real extractions exist. Writes Drawing JSON to
.local/gesture/out/synthetic_artists/{A,B}/:

  A — synth.scene_matisse_like: few long, gently curving, mostly one-sign
      strokes with near-touches; tapered widths, some ink pools.
  B — synth.scene_random with tighter κ and shorter strokes; flat widths
      (with_width, no taper/pool) so width groups exist for both.

  cd tools/gesture && ../../.local/gesture/.venv/bin/python -m experiments.make_synthetic_artists
  ../../.local/gesture/.venv/bin/python -m experiments.discriminate --name synthetic \\
      --group A=../../.local/gesture/out/synthetic_artists/A \\
      --group B=../../.local/gesture/out/synthetic_artists/B --null-source A
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from gesture import synth
from gesture.core import Drawing

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / ".local/gesture/out/synthetic_artists"
SIZE = (900, 700)


def artist_a(seed: int) -> Drawing:
    rng = np.random.default_rng(1000 + seed)
    return synth.scene_matisse_like(rng, SIZE)


def artist_b(seed: int) -> Drawing:
    rng = np.random.default_rng(2000 + seed)
    d = synth.scene_random(rng, SIZE, n_strokes=int(rng.integers(5, 10)),
                           length_frac=(0.2, 0.6), n_segments=(3, 8), kappa_max_frac=12.0)
    strokes = [synth.with_width(st, 4.0, rng, taper=False, pool=False) for st in d.strokes]
    return Drawing(strokes, source="synth:artist_B", size=d.size, meta={"scene": "random_B"})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=20, help="drawings per artist")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    for name, make in (("A", artist_a), ("B", artist_b)):
        d = a.out / name
        d.mkdir(parents=True, exist_ok=True)
        for i in range(a.n):
            make(i).save(d / f"{name}_{i:03d}.json")
        print(f"wrote {a.n} drawings to {d}")


if __name__ == "__main__":
    main()
