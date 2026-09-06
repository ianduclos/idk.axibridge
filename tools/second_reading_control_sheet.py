"""Render controlled Second Reading continuations from the public module."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from axibridge.model import Path as InkPath
from axibridge.sources.second_reading import SecondReading, SecondReadingParams


DEFAULT_OUTPUT = Path("shots/second-reading-recovery-final-0906")
PAPER = "#f7f4ee"
PREFIX = "#b4b0a8"
HUMAN = "#9b4933"
MACHINE = "#26241f"
STROKE = [[42, 147], [112, 120], [184, 138], [242, 72]]
CONTROLS = ("attention", "departure", "scale")
VALUES = (0.0, 0.5, 1.0)
SEEDS = (12, 23)


def draw_paths(ax, paths: list[InkPath], color: str, width: float) -> None:
    for path in paths:
        if len(path.points) >= 2:
            x, y = zip(*path.points)
            ax.plot(x, y, color=color, linewidth=width, solid_capstyle="round")


def setup(ax) -> None:
    ax.set_xlim(0, 280)
    ax.set_ylim(198, 0)
    ax.set_aspect("equal")
    ax.set_facecolor(PAPER)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#d8d3ca")
        spine.set_linewidth(0.55)


def recipe(seed: int, control: str, value: float) -> SecondReadingParams:
    return SecondReadingParams(
        reading="first", historical_stacks=True,
        seed=seed,
        turns=8,
        boundary="clip",
        events=[
            {"kind": "stroke", "turn": 5, "points": STROKE, "smoothing": 0.6},
            {"kind": "controls", "turn": 6, "reading": "relations", control: value},
        ],
    )


def render(output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    module = SecondReading()
    fig, axes = plt.subplots(6, 3, figsize=(12, 16), facecolor=PAPER)
    records = []

    for seed_index, seed in enumerate(SEEDS):
        for control_index, control in enumerate(CONTROLS):
            row = seed_index * len(CONTROLS) + control_index
            for column, value in enumerate(VALUES):
                params = recipe(seed, control, value)
                trajectory = module.trajectory(params)
                ax = axes[row, column]
                setup(ax)
                # t4 is the shared First-reading prefix.  t5 is the shared
                # human intervention; only t6 onward can vary by the control.
                draw_paths(ax, trajectory.state(4), PREFIX, 0.58)
                draw_paths(ax, trajectory.steps[5], HUMAN, 0.88)
                for turn in range(6, 9):
                    draw_paths(ax, trajectory.steps[turn], MACHINE, 0.78)
                ax.set_title(f"seed {seed} · {control} = {value:g}", loc="left", y=1.06,
                             fontsize=8.8, fontweight="bold", color="#36332e", pad=0)
                ax.text(0, 1.005, "t8 · First prefix → stroke → relations", transform=ax.transAxes,
                        ha="left", va="bottom", fontsize=6.7, color="#706b63")
                records.append({
                    "cell": f"seed-{seed}-{control}-{value:g}",
                    "seed": seed,
                    "control": control,
                    "value": value,
                    "params": params.model_dump(mode="json"),
                    "metadata": trajectory.metadata[:9],
                })

    fig.suptitle("Second Reading — relation control sheet", x=0.06, y=0.988, ha="left",
                 fontsize=16, fontweight="bold", color="#292722")
    fig.text(0.06, 0.969,
             "t8 after a shared First prefix and captured stroke at t5; relations begins at t6 · clip frame 280 × 198 mm",
             ha="left", fontsize=8.4, color="#706b63")
    fig.text(0.06, 0.948, "grey = prefix · rust = human stroke · dark = relation continuation",
             ha="left", fontsize=8.2, color="#706b63")
    fig.tight_layout(rect=(0.04, 0.02, 0.98, 0.935), h_pad=2.5, w_pad=1.15)

    image = output / "controls.png"
    recipes = output / "controls-recipes.json"
    fig.savefig(image, dpi=180, facecolor=PAPER, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    recipes.write_text(json.dumps(records, indent=2) + "\n")
    return image, recipes


def main() -> None:
    parser = argparse.ArgumentParser(description="Render controlled Second Reading relation continuations.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    image, recipes = render(args.output)
    print(f"wrote {image} and {recipes}")


if __name__ == "__main__":
    main()
