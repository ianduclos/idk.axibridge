"""Render the captured Second Reading exchange as an iteration sheet.

The input recipes are saved bench captures.  This tool only replays them: it
does not recreate strokes or choose an alternate geometry.  The iteration
cells stay in the raw fit workspace; the final panel is the module's single
whole-element fitted document.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from axibridge.model import Path as InkPath
from axibridge.sources._second_reading_experiment import frame
from axibridge.sources.second_reading import SecondReading, SecondReadingParams


RECIPE_NAMES = {
    "opening": "bench-opening.json",
    "first": "bench-first-exchange.json",
    "second": "bench-second-exchange.json",
    "third": "bench-third-exchange-kept.json",
}
DEFAULT_OUTPUT = Path("shots/second-reading-recovery-final-0906")
RECIPE_DIRECTORY = Path("shots/second-reading-recovery-final-0906")
PAPER = "#f7f4ee"
EXISTING = "#b4b0a8"
MACHINE = "#26241f"
HUMAN = "#9b4933"


def read_recipe(directory: Path, name: str) -> SecondReadingParams:
    return SecondReadingParams(**{**json.loads((directory / RECIPE_NAMES[name]).read_text()), "historical_stacks": True})


def draw_paths(ax, paths: list[InkPath], color: str, *, width: float = 0.72) -> None:
    for path in paths:
        if len(path.points) >= 2:
            x, y = zip(*path.points)
            ax.plot(x, y, color=color, linewidth=width, solid_capstyle="round")


def prepare(ax, work_frame: tuple[float, float, float, float]) -> None:
    x, y, width, height = work_frame
    ax.set_xlim(x, x + width)
    ax.set_ylim(y + height, y)
    ax.set_aspect("equal")
    ax.set_facecolor(PAPER)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#d8d3ca")
        spine.set_linewidth(0.55)


def iteration_cell(
    ax,
    *,
    trajectory,
    current_turn: int,
    existing_through: int | None,
    human_turn: int | None,
    machine_start: int | None,
    work_frame: tuple[float, float, float, float],
    title: str,
    subtitle: str,
) -> None:
    """Show a fixed raw workspace, with the latest human/machine additions clear."""
    prepare(ax, work_frame)
    if existing_through is not None:
        draw_paths(ax, trajectory.state(existing_through), EXISTING, width=0.58)
    if human_turn is not None:
        draw_paths(ax, trajectory.steps[human_turn], HUMAN, width=0.9)
    if machine_start is not None:
        for turn in range(machine_start, current_turn + 1):
            draw_paths(ax, trajectory.steps[turn], MACHINE, width=0.82)
    ax.set_title(title, loc="left", y=1.13, fontsize=10, fontweight="bold", color="#36332e", pad=0)
    ax.text(0.0, 1.035, subtitle, transform=ax.transAxes, fontsize=7.4, color="#706b63",
            ha="left", va="bottom")


def render(output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    module = SecondReading()
    recipes = {name: read_recipe(RECIPE_DIRECTORY, name) for name in RECIPE_NAMES}
    trajectories = {name: module.trajectory(recipe) for name, recipe in recipes.items()}

    # All captured recipes use boundary=fit.  This is deliberately the raw
    # working frame, rather than a per-cell fit, so passage sizes stay legible.
    work_frame = frame(recipes["opening"].width, recipes["opening"].height, recipes["opening"].boundary)
    if any(frame(r.width, r.height, r.boundary) != work_frame for r in recipes.values()):
        raise ValueError("The exchange recipes need one shared raw work frame")

    fig = plt.figure(figsize=(14, 15.6), facecolor=PAPER)
    grid = fig.add_gridspec(4, 2, hspace=0.42, wspace=0.17)
    axes = [fig.add_subplot(grid[row, col]) for row in range(4) for col in range(2)]

    iteration_cell(axes[0], trajectory=trajectories["opening"], current_turn=4, existing_through=None,
                   human_turn=None, machine_start=0, work_frame=work_frame, title="t4  whole element",
                   subtitle="machine opening · raw workspace")
    iteration_cell(axes[1], trajectory=trajectories["first"], current_turn=5, existing_through=4,
                   human_turn=5, machine_start=None, work_frame=work_frame, title="t5  input",
                   subtitle="human stroke · first exchange")
    iteration_cell(axes[2], trajectory=trajectories["first"], current_turn=7, existing_through=4,
                   human_turn=5, machine_start=6, work_frame=work_frame, title="t7  answer",
                   subtitle="machine response to the t5 input")
    iteration_cell(axes[3], trajectory=trajectories["second"], current_turn=8, existing_through=7,
                   human_turn=8, machine_start=None, work_frame=work_frame, title="t8  input",
                   subtitle="human stroke · reading changes to relations")
    iteration_cell(axes[4], trajectory=trajectories["second"], current_turn=11, existing_through=7,
                   human_turn=8, machine_start=9, work_frame=work_frame, title="t11  answer",
                   subtitle="machine links the input with an earlier echo")
    iteration_cell(axes[5], trajectory=trajectories["third"], current_turn=12, existing_through=11,
                   human_turn=12, machine_start=None, work_frame=work_frame, title="t12  input",
                   subtitle="human stroke · third exchange")
    iteration_cell(axes[6], trajectory=trajectories["third"], current_turn=15, existing_through=11,
                   human_turn=12, machine_start=13, work_frame=work_frame, title="t15  answer",
                   subtitle="machine continues older ink; latest input left alone")

    final_ax = axes[7]
    prepare(final_ax, (0, 0, recipes["third"].width, recipes["third"].height))
    raw_final = trajectories["third"].state(15)
    fitted_final = module.document(recipes["third"], raw_final).layers[0].paths
    draw_paths(final_ax, fitted_final, MACHINE, width=0.78)
    final_ax.set_title("t15  answer · fitted final view", loc="left", y=1.13, fontsize=10,
                       fontweight="bold", color="#36332e", pad=0)
    final_ax.text(0.0, 1.035, "one uniform fit of the whole element",
                  transform=final_ax.transAxes, fontsize=7.4, color="#706b63", ha="left", va="bottom")

    fig.suptitle("Second Reading — alternating exchange", x=0.055, y=0.982, ha="left",
                 fontsize=16, fontweight="bold", color="#292722")
    fig.text(0.055, 0.956, "Captured bench recipes, seed 12 · every iteration panel shares the raw fit workspace",
             ha="left", fontsize=8.5, color="#706b63")
    fig.legend(handles=[Line2D([0], [0], color=EXISTING, lw=2, label="existing ink"),
                        Line2D([0], [0], color=HUMAN, lw=2, label="human input"),
                        Line2D([0], [0], color=MACHINE, lw=2, label="machine addition / answer")],
               loc="upper right", bbox_to_anchor=(0.947, 0.974), ncol=3, fontsize=8, frameon=False)

    png = output / "alternating-exchange.png"
    svg = output / "alternating-exchange.svg"
    fig.savefig(png, dpi=180, facecolor=PAPER, bbox_inches="tight", pad_inches=0.18)
    fig.savefig(svg, facecolor=PAPER, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    return png, svg


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the saved Second Reading exchange recipes.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="directory receiving the PNG and SVG (the saved bench recipes stay in their capture directory)")
    args = parser.parse_args()
    png, svg = render(args.output)
    print(f"wrote {png} and {svg}")


if __name__ == "__main__":
    main()
