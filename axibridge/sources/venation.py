"""Venation growth (space colonisation) — branching lines that grow toward
scattered attractors, one step at a time.

Runions et al.'s leaf-venation algorithm, and the first ``ProcessModule`` in
the repo: scatter attractor points, grow a tree from a seed node, and let each
attractor pull the nearest node toward it until something gets close enough to
consume it. Branches appear where attractors disagree — the structure is a
consequence of the point cloud rather than a rule about branching.

It earns its place here twice over: the marks are continuous coherent lines
that follow a structure (not scatter), and each step only ADDS segments, which
is exactly the accumulative case the trajectory cache is built around.

**Vectorised, not the textbook double loop.** The plan this module was built
from wrote the nearest-node search as "for every attractor, scan every node"
in pure Python. At this module's declared bounds (``steps`` le=600,
``attractors`` up to 3000) that is on the order of a billion distance
computations for one trajectory — minutes, not seconds — and since
``trajectory()`` always runs a process to its time axis's declared upper
bound (that is what lets one cached run serve every scrub position), it would
block the very first ``generate()`` for that long. Every per-step
nearest-node search here is a broadcast distance matrix over numpy arrays
instead of a Python double loop; see ``tests/test_venation.py``'s
``test_a_full_trajectory_is_fast`` for the budget this is held to.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np
from pydantic import BaseModel, Field

from ..model import Layer, Path, PathDocument
from ..process import ProcessModule, Step
from ..registry import register_source

BED_WIDTH = 300.0
BED_HEIGHT = 218.0


class VenationParams(BaseModel):
    steps: int = Field(default=120, ge=0, le=600, title="Steps",
                       description="How far the growth has run. This is the time "
                                   "axis — bind it to the master timeline and the "
                                   "growth becomes an animation")
    attractors: int = Field(default=400, ge=10, le=3000, title="Attractors",
                            description="Points the growth reaches toward; more "
                                        "gives denser, finer venation")
    width: float = Field(default=160.0, ge=20.0, le=280.0, title="Width (mm)")
    height: float = Field(default=140.0, ge=20.0, le=200.0, title="Height (mm)")
    step_len: float = Field(default=2.0, ge=0.3, le=10.0, title="Step length (mm)",
                            description="How far a tip advances per step")
    attraction: float = Field(default=30.0, ge=2.0, le=120.0, title="Attraction (mm)",
                              description="How far an attractor can pull a tip")
    kill: float = Field(default=4.0, ge=0.5, le=40.0, title="Kill radius (mm)",
                        description="An attractor is consumed when growth comes "
                                    "this close — small values let branches crowd")
    seed: int = Field(default=0, ge=0, le=99999, title="Seed")


@register_source
class Venation(ProcessModule):
    id = "venation"
    orientation = "geometry"  # a width x height field
    label = "Venation (growth)"
    description = "Branching growth toward scattered attractors, one step at a time."
    Params = VenationParams
    time_axis = "steps"
    accumulative = True

    def run(self, params: VenationParams) -> Iterator[Step]:
        p = params
        rng = np.random.default_rng(p.seed)
        w = min(p.width, BED_WIDTH - 4.0)
        h = min(p.height, BED_HEIGHT - 4.0)
        ox, oy = 2.0, 2.0

        # (M, 2): every attractor, placed once up front.
        attractors = np.array([ox, oy]) + rng.uniform(
            [0.0, 0.0], [w, h], size=(p.attractors, 2))
        # (N, 2): the tree, starting from a single root at the bottom middle.
        # Grows by one row per surviving tip each step (np.vstack) — cheap at
        # the node counts this algorithm reaches within its declared bounds.
        nodes = np.array([[ox + w / 2.0, oy + h]])

        while True:
            if attractors.shape[0] == 0:
                yield Step(paths=[], telemetry={"attractors": 0.0, "tips": 0.0})
                return

            # Broadcast distance matrix (M attractors x N nodes), instead of
            # a Python double loop: each attractor votes for its nearest node,
            # if that node is within reach.
            delta = attractors[:, None, :] - nodes[None, :, :]      # (M, N, 2)
            dist = np.hypot(delta[..., 0], delta[..., 1])            # (M, N)
            nearest = np.argmin(dist, axis=1)                        # (M,) — ties
            # resolve to the lowest node index, deterministically.
            nearest_dist = dist[np.arange(dist.shape[0]), nearest]
            within = nearest_dist < p.attraction

            if not np.any(within):
                yield Step(paths=[], telemetry={"attractors": float(attractors.shape[0]),
                                                 "tips": 0.0})
                return

            # Group the in-reach attractors by the node they voted for, and
            # sum each group's pull direction — the vectorised form of
            # `votes.setdefault(best, []).append(a)` then summing `a - node`.
            voted_nodes = nearest[within]                            # (K,)
            pull = delta[np.arange(dist.shape[0]), nearest][within]   # (K, 2)
            voters, inverse = np.unique(voted_nodes, return_inverse=True)
            sums = np.zeros((voters.shape[0], 2))
            np.add.at(sums, inverse, pull)
            tips_count = voters.shape[0]

            mag = np.hypot(sums[:, 0], sums[:, 1])
            grew = mag > 1e-9
            grown_nodes = voters[grew]

            if grown_nodes.shape[0] == 0:
                yield Step(paths=[], telemetry={"attractors": float(attractors.shape[0]),
                                                 "tips": float(tips_count)})
                return

            direction = sums[grew] / mag[grew, None]
            old_tips = nodes[grown_nodes]                            # (K', 2)
            new_tips = old_tips + direction * p.step_len
            new_tips[:, 0] = np.clip(new_tips[:, 0], 0.0, BED_WIDTH)
            new_tips[:, 1] = np.clip(new_tips[:, 1], 0.0, BED_HEIGHT)

            old_tips_list = old_tips.tolist()
            new_tips_list = new_tips.tolist()
            added = [Path(points=[tuple(o), tuple(t)], filled=False)
                     for o, t in zip(old_tips_list, new_tips_list)]

            nodes = np.vstack([nodes, new_tips])

            # Consume attractors within `kill` of a NEWLY created node only
            # (not the whole tree) — a node that already had its chance to
            # attract and didn't consume nearby attractors shouldn't start
            # doing so just because it happens to still be part of the tree.
            d_to_new = attractors[:, None, :] - new_tips[None, :, :]   # (M, K', 2)
            dist_to_new = np.hypot(d_to_new[..., 0], d_to_new[..., 1])  # (M, K')
            keep = dist_to_new.min(axis=1) > p.kill
            attractors = attractors[keep]

            yield Step(paths=added,
                       telemetry={"attractors": float(attractors.shape[0]),
                                  "tips": float(tips_count)})

    def document(self, params: VenationParams, paths: list[Path]) -> PathDocument:
        return PathDocument(
            layers=[Layer(id=1, name="venation", color="#26241f", paths=list(paths))],
            width=params.width,
            height=params.height,
            source=f"venation {params.seed} @ {params.steps}",
        )
