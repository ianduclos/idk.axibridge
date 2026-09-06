"""Reproduce the first comparison study; never connects to the plotter."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from axibridge.sources.second_reading import SecondReading, SecondReadingParams
from axibridge.trajectory import clear_cache


def draw(ax, document):
    ax.set_facecolor("#f7f4ee")
    for path in document.layers[0].paths:
        x, y = zip(*path.points)
        ax.plot(x, y, color="#24221e", linewidth=.65)
    ax.set_xlim(0, document.width)
    ax.set_ylim(document.height, 0)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("shots/second-reading-latest"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    module = SecondReading()
    seeds = (1, 4, 12, 23, 42, 91)
    overview, axs = plt.subplots(6, 5, figsize=(20, 18), facecolor="#e9e5dd")
    measurements = []
    for row, seed in enumerate(seeds):
        base = {"seed": seed, "turns": 4}
        cases = [("Opening at turn 4", base)]
        for i, salt in enumerate((11, 29, 71)):
            cases.append((f"Continuation {chr(65+i)}", {**base, "turns": 12,
                          "events": [{"kind": "branch", "turn": 5, "seed": salt}]}))
        cases.append(("Human turn + continuation A", {**base, "turns": 12, "events": [
            {"kind": "branch", "turn": 5, "seed": 11},
            {"kind": "stroke", "turn": 5, "points": [[42, 147], [112, 120], [184, 138], [242, 72]]}]}))
        figure, panels = plt.subplots(1, 5, figsize=(20, 3.6), facecolor="#e9e5dd")
        recipes = []
        for col, (name, recipe) in enumerate(cases):
            params = SecondReadingParams(**recipe)
            clear_cache()
            start = time.perf_counter()
            doc = module.generate(params)
            cold = time.perf_counter()-start
            start = time.perf_counter()
            module.generate(params)
            warm = time.perf_counter()-start
            measurements.append({"seed": seed, "case": name, "cold_seconds": cold,
                                 "warm_seconds": warm,
                                 "points": sum(len(p.points) for p in doc.layers[0].paths)})
            for ax in (axs[row, col], panels[col]):
                draw(ax, doc)
                ax.set_title(f"Seed {seed} · {name}", fontsize=9)
            recipes.append({"name": name, "module": module.id, "params": params.model_dump(),
                            "decisions": module.trajectory(params).metadata[:params.turns+1]})
            svg_paths = "\n".join('<polyline points="'+" ".join(f"{x:.6f},{y:.6f}" for x, y in p.points)+'"/>'
                                  for p in doc.layers[0].paths)
            (args.output/f"seed-{seed:02d}-{col}.svg").write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{params.width}mm" height="{params.height}mm" '
                f'viewBox="0 0 {params.width} {params.height}"><g fill="none" stroke="#24221e" stroke-width="0.3">'
                +svg_paths+'</g></svg>')
        figure.tight_layout()
        figure.savefig(args.output/f"seed-{seed:02d}.png", dpi=130)
        plt.close(figure)
        (args.output/f"seed-{seed:02d}.json").write_text(json.dumps(recipes, indent=2)+"\n")
    overview.tight_layout()
    overview.savefig(args.output/"overview.png", dpi=110)
    plt.close(overview)
    (args.output/"measurements.json").write_text(json.dumps(measurements, indent=2)+"\n")
    print(f"Wrote six reproducible comparisons to {args.output}")


if __name__ == "__main__":
    main()
