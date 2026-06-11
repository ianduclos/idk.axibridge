"""The intermediate path representation (IPR) — the geometry/execution contract.

Everything in axibridge communicates through :class:`PathDocument`: SVG import
produces one, generator modules produce one, transform modules map one to
another, and execution backends consume one. It is deliberately minimal:

* **Polylines only.** Curves are flattened at ingestion with a configurable
  tolerance. The EBB executes nothing but timed straight-line segments, vpype's
  native model is polylines, and saxi flattens on input — so polylines are the
  representation every consumer already speaks, and keeping curves around would
  force every backend to re-flatten with its own (inconsistent) tolerance.
* **Millimetres, machine frame.** X grows right, Y grows *down* (matching both
  SVG and the AxiDraw's coordinate convention), origin at the carriage home
  corner. One unit convention everywhere kills an entire class of bugs.
* **Layers carry intent, not execution.** A layer has a name and a colour
  (pen separation / preview), never speeds or pen heights — those belong to
  the execution side and would otherwise leak planner assumptions into
  geometry.
* **Pen-up travel is implicit.** The gaps between paths are the travel moves;
  *deciding* how to traverse them (order, speed) is execution/planning
  territory. The planned form — with travel made explicit — is
  :class:`PlannedJob`, which is what previews render and the simulator runs.

All models are Pydantic, so the same types are the in-process contract, the
wire format, and the JSON Schema the frontend renders controls from.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

#: A coordinate pair in millimetres, machine frame (x right, y down).
Point = tuple[float, float]

# Fallback layer palette (vpype-style) used when an SVG carries no colour info.
LAYER_PALETTE = [
    "#0066cc", "#cc3300", "#00aa44", "#bb8800",
    "#7733cc", "#cc0099", "#008888", "#664422",
]


class Path(BaseModel):
    """A single pen-down polyline. One or more points; a 1-point path is a dot
    (pen down, pen up in place).

    ``filled`` is compose-side metadata only: it records that the original SVG
    element (or generator shape) was a filled region, which makes the path a
    solid mask when its layer occludes. Execution backends never read it.
    """

    points: list[Point] = Field(min_length=1)
    filled: bool = False

    def length(self) -> float:
        """Pen-down distance along the polyline, in mm."""
        return sum(
            math.dist(a, b) for a, b in zip(self.points, self.points[1:])
        )


class Layer(BaseModel):
    """A group of paths drawn with one pen. ``id`` is stable across transforms
    so layer-aware operations (e.g. occlusion across layers) can address it."""

    id: int
    name: str = ""
    color: str = "#0066cc"
    paths: list[Path] = Field(default_factory=list)


class PathDocument(BaseModel):
    """The IPR root: ordered layers of ordered polylines plus page metadata.

    Path order *is* draw order. Transforms that reorder paths (linesort) are
    therefore meaningful, and the preview can show order explicitly.
    """

    layers: list[Layer] = Field(default_factory=list)
    width: float | None = Field(default=None, description="Page width in mm, if known")
    height: float | None = Field(default=None, description="Page height in mm, if known")
    source: str = Field(default="", description="Provenance note (filename, generator, pipeline)")

    def iter_paths(self):
        """Yield ``(layer, path)`` pairs in draw order."""
        for layer in self.layers:
            for path in layer.paths:
                yield layer, path

    def bounds(self) -> tuple[float, float, float, float] | None:
        """(xmin, ymin, xmax, ymax) over all points, or None if empty."""
        xs: list[float] = []
        ys: list[float] = []
        for _, path in self.iter_paths():
            for x, y in path.points:
                xs.append(x)
                ys.append(y)
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def stats(self) -> DocumentStats:
        n_paths = 0
        n_points = 0
        pen_down = 0.0
        for _, path in self.iter_paths():
            n_paths += 1
            n_points += len(path.points)
            pen_down += path.length()
        return DocumentStats(
            layers=len(self.layers),
            paths=n_paths,
            points=n_points,
            pen_down_distance=pen_down,
            bounds=self.bounds(),
        )


class DocumentStats(BaseModel):
    """Cheap summary of a document, for UI display without shipping geometry."""

    layers: int
    paths: int
    points: int
    pen_down_distance: float
    bounds: tuple[float, float, float, float] | None


# ---------------------------------------------------------------------------
# Planned form: geometry + motion params -> explicit move list with timing.
# ---------------------------------------------------------------------------


class PlannedMove(BaseModel):
    """One contiguous move at a fixed pen state. ``pen_down=False`` moves are
    the travel segments the IPR keeps implicit."""

    pen_down: bool
    points: list[Point]
    layer_id: int | None = None
    distance: float = 0.0
    duration: float = Field(default=0.0, description="Estimated seconds, incl. pen lift/lower for pen-down moves")


class PlannedJob(BaseModel):
    """A fully ordered move list with time estimates.

    This is what the preview renders and what the simulator executes. The
    timing comes from :mod:`axibridge.estimate` and is an *estimate* of what
    the real planner will do, not a motion plan — execution backends do their
    own planning (pyaxidraw/plotink or saxi).
    """

    moves: list[PlannedMove] = Field(default_factory=list)
    total_duration: float = 0.0
    pen_down_duration: float = 0.0
    travel_duration: float = 0.0
    pen_lift_duration: float = 0.0
    pen_down_distance: float = 0.0
    travel_distance: float = 0.0
    pen_lifts: int = 0
