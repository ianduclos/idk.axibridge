"""Numerical engine for the Fast Marching Topo image source.

The Fast Marching Method solves ``|grad(T)| * F = 1`` from one seed, where
``F`` is a positive per-pixel speed.  The source wrapper turns image luma into
``F``; this module owns only the travel-time solve and conversion of that map
to iso-lines.

The heap update is adapted from Roland Blok's FastMarchingTopoPlot
(https://github.com/rolandblok/FastMarchingTopoPlot, Unlicense).  Contour
extraction uses contourpy's compiled marching-squares implementation: tracing
hundreds of levels by scanning an 800 px image in Python would otherwise cost
more than the Fast Marching solve itself.

Solver selection: the travel-time solve itself (``travel_time_multi``) can
run on two backends. The pure-Python heap solver above is always available
and is the *tested reference* — every geometry-pinning test in
tests/test_fast_marching_topo.py and tests/test_fast_marching_contours.py
forces it via ``USE_SKFMM = False`` so results stay pinned to hand-verified
values regardless of what's installed. scikit-fmm (``import skfmm``) is an
OPTIONAL compiled accelerator — roughly an order of magnitude faster on
large grids (benchmarked ~12x on 800x1124) — used automatically when
importable (``USE_SKFMM`` defaults to ``skfmm is not None``). It is
deliberately NOT a hard dependency: the Pi has no compiler toolchain
pre-provisioned for it, and the pure-Python path must keep the Pi working
unaided. Install it with ``.venv/bin/pip install scikit-fmm`` (PyPI, has
wheels for common platforms) or via the ``fast`` extra
(``pip install axibridge[fast]``); call :func:`solver_name` to see which
backend actually ran.

skfmm/our-solver agreement, seed placement (empirically verified, see the
comment on ``_travel_time_multi_skfmm``): skfmm's sub-cell-accurate
initialization places the T=0 level set half a grid cell beyond the seed
pixel center rather than in it, so raw skfmm output equals ours minus a
constant 0.5 everywhere except at the seed cells themselves; we add 0.5
back and then force seed cells to exactly 0 to restore our contract. With
that correction, and ``order=1`` (matching the fallback's own first-order
upwind scheme rather than skfmm's default order=2, which tracked worse),
the two solvers agree with a smooth speed field to within a small fraction
of a grid cell away from the seed edge itself — see
test_fast_marching_contours.py's skfmm-agreement test for the measured
tolerance.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable, Iterable

import contourpy
import numpy as np

try:
    import skfmm
except ImportError:  # pragma: no cover - exercised on machines without it
    skfmm = None

# Runtime switch: True when scikit-fmm is importable. Tests that pin exact
# geometry monkeypatch this to False to force the pure-Python reference path
# regardless of what's installed in the test environment.
USE_SKFMM = skfmm is not None

Progress = Callable[[float], None]
Line = list[tuple[float, float]]


def solver_name() -> str:
    """Which travel-time backend is currently active: "skfmm" (compiled,
    optional) or "python" (pure-Python heap, always available). Lets callers
    and logs surface which one ran without reaching into module internals."""
    return "skfmm" if USE_SKFMM else "python"


def travel_time(
    speed: np.ndarray,
    seed_x: int,
    seed_y: int,
    progress: Progress | None = None,
) -> np.ndarray:
    """Solve the first-order upwind Eikonal equation on a 4-neighbour grid
    from a single seed. Delegates to :func:`travel_time_multi` — kept as a
    thin wrapper (not a copy) so the two paths cannot drift; output stays
    bit-identical to the pre-multi-seed implementation.
    """
    return travel_time_multi(speed, [(seed_x, seed_y)], progress)


def travel_time_multi(
    speed: np.ndarray,
    seeds: Iterable[tuple[int, int]],
    progress: Progress | None = None,
) -> np.ndarray:
    """Solve the first-order upwind Eikonal equation on a 4-neighbour grid
    from multiple seeds at once.

    ``speed`` is a 2-D array with positive values for reachable pixels.  Zero
    or negative values remain unreachable (``inf`` in the result).  Every
    seed is clamped to the grid and starts at ``T=0`` in the same heap, so
    the result is the pointwise minimum of the independent single-seed
    solves — computed in one pass instead of one per seed.  Out-of-range or
    duplicate seeds collapse harmlessly.  Fixed input always produces
    bit-identical output (tie-breaks are by flat index, not insertion order,
    since heap entries are ``(time, idx)`` and indices are unique).
    """
    field = np.asarray(speed, dtype=np.float64)
    if field.ndim != 2:
        raise ValueError("speed must be a 2-D array")
    h, w = field.shape
    if h == 0 or w == 0:
        return np.full((h, w), np.inf, dtype=np.float64)

    if USE_SKFMM and skfmm is not None:
        return _travel_time_multi_skfmm(field, seeds, progress)
    return _travel_time_multi_python(field, seeds, progress)


def _travel_time_multi_skfmm(
    field: np.ndarray,
    seeds: Iterable[tuple[int, int]],
    progress: Progress | None,
) -> np.ndarray:
    """scikit-fmm-backed solve — see the module docstring for how the seed
    placement / order choice were determined. A single compiled call, so
    progress is reported only before (0.0) and after (1.0); the pure-Python
    path keeps its per-cell incremental reporting.
    """
    h, w = field.shape

    if progress is not None:
        progress(0.0)

    seed_mask = np.zeros((h, w), dtype=bool)
    for seed_x, seed_y in seeds:
        sx = min(max(int(seed_x), 0), w - 1)
        sy = min(max(int(seed_y), 0), h - 1)
        seed_mask[sy, sx] = True

    if not seed_mask.any():
        return np.full((h, w), np.inf, dtype=np.float64)

    # Our contract: speed <= 0 or non-finite -> unreachable (inf), regardless
    # of what skfmm does with a zero/degenerate speed. Exclude those cells
    # from the domain via a masked phi (skfmm supports masked arrays) so
    # they come back masked, which we then fill as inf. A seed is always
    # reachable at T=0 even if the underlying pixel's own speed is bad (the
    # pure-Python solver never reads a seed's own speed either — only its
    # neighbours' — so a seed never needs to be masked out).
    bad_speed = ~np.isfinite(field) | (field <= 0.0)
    domain_mask = bad_speed & ~seed_mask
    safe_speed = np.where(bad_speed, 1.0, field)

    phi = np.ma.MaskedArray(np.ones((h, w), dtype=np.float64), mask=domain_mask)
    phi[seed_mask] = -1.0

    raw = skfmm.travel_time(phi, safe_speed, order=1)

    # skfmm's sub-cell-accurate initialization places the T=0 level set half
    # a grid cell beyond the seed pixel center: verified empirically by
    # seeding a uniform-speed edge row, where skfmm's raw output comes back
    # 0.5, 0.5, 1.5, 2.5, ... against the pure-Python solver's 0, 1, 2, 3,
    # ... — i.e. raw skfmm output equals ours minus a constant 0.5
    # everywhere except at the seed cells. Adding 0.5 back and then forcing
    # the seed cells to exactly 0 restores our "T=0 at seeds" contract.
    times = np.ma.filled(raw, np.inf).astype(np.float64) + 0.5
    times[seed_mask] = 0.0
    times[domain_mask] = np.inf

    if progress is not None:
        progress(1.0)
    return times


def _travel_time_multi_python(
    field: np.ndarray,
    seeds: Iterable[tuple[int, int]],
    progress: Progress | None,
) -> np.ndarray:
    """Pure-Python heap solve — the always-available fallback and the tested
    reference implementation. Byte-identical to the pre-skfmm code."""
    h, w = field.shape
    n = w * h
    speeds = field.ravel().tolist()
    times = [math.inf] * n
    frozen = bytearray(n)
    heap: list[tuple[float, int]] = []
    seen_idx: set[int] = set()
    for seed_x, seed_y in seeds:
        sx = min(max(int(seed_x), 0), w - 1)
        sy = min(max(int(seed_y), 0), h - 1)
        idx = sy * w + sx
        if idx in seen_idx:
            continue
        seen_idx.add(idx)
        times[idx] = 0.0
        heap.append((0.0, idx))
    heapq.heapify(heap)
    done = 0
    report_every = max(n // 100, 1)

    while heap:
        _, idx = heapq.heappop(heap)
        if frozen[idx]:
            continue
        frozen[idx] = 1
        done += 1
        if progress is not None and (done == n or done % report_every == 0):
            progress(done / n)

        iy, ix = divmod(idx, w)
        for nidx in (
            idx - w if iy > 0 else -1,
            idx + w if iy + 1 < h else -1,
            idx - 1 if ix > 0 else -1,
            idx + 1 if ix + 1 < w else -1,
        ):
            if nidx < 0 or frozen[nidx]:
                continue
            speed_here = speeds[nidx]
            if speed_here <= 0.0 or not math.isfinite(speed_here):
                continue

            ny, nx = divmod(nidx, w)
            tx = math.inf
            ty = math.inf
            if nx > 0 and frozen[nidx - 1]:
                tx = times[nidx - 1]
            if nx + 1 < w and frozen[nidx + 1]:
                tx = min(tx, times[nidx + 1])
            if ny > 0 and frozen[nidx - w]:
                ty = times[nidx - w]
            if ny + 1 < h and frozen[nidx + w]:
                ty = min(ty, times[nidx + w])

            step = 1.0 / speed_here
            if not math.isfinite(tx):
                new_time = ty + step
            elif not math.isfinite(ty):
                new_time = tx + step
            else:
                disc = 2.0 * step * step - (tx - ty) ** 2
                new_time = (
                    0.5 * (tx + ty + math.sqrt(disc))
                    if disc >= 0.0
                    else min(tx, ty) + step
                )

            if new_time < times[nidx]:
                times[nidx] = new_time
                heapq.heappush(heap, (new_time, nidx))

    return np.asarray(times, dtype=np.float64).reshape((h, w))


def iso_contour_levels(
    time_map: np.ndarray,
    count: int,
    progress: Progress | None = None,
) -> list[list[Line]]:
    """Extract ``count`` evenly spaced travel-time iso-lines, grouped by
    level in arrival-time order (one inner list per level).

    Levels exclude both extrema, matching the upstream generator.  Lines that
    meet the image edge remain open; closed interior rings repeat their first
    point exactly at the end, which keeps the path model's closure semantics
    honest even though these are stroke-only paths. ``iso_contours`` flattens
    this same grouping; callers that need per-level structure (boundary
    threading) use this directly instead of re-deriving it.
    """
    values = np.asarray(time_map, dtype=np.float64)
    if values.ndim != 2 or values.size == 0:
        return []
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return []
    low = float(finite.min())
    high = float(finite.max())
    if high <= low:
        return []

    number = max(int(count), 2)
    levels = np.linspace(low, high, number + 2, dtype=np.float64)[1:-1]
    generator = contourpy.contour_generator(
        z=values,
        name="serial",
        corner_mask=False,
        line_type="Separate",
    )
    result: list[list[Line]] = []
    for i, level in enumerate(levels):
        level_lines: list[Line] = []
        for raw in generator.lines(float(level)):
            if len(raw) < 2:
                continue
            line = [(float(x), float(y)) for x, y in raw]
            if len(line) >= 3 and np.array_equal(raw[0], raw[-1]):
                line[-1] = line[0]
            level_lines.append(line)
        result.append(level_lines)
        if progress is not None:
            progress((i + 1) / number)
    return result


def iso_contours(
    time_map: np.ndarray,
    count: int,
    progress: Progress | None = None,
) -> list[Line]:
    """Extract ``count`` evenly spaced travel-time iso-lines as a flat list.

    Delegates to :func:`iso_contour_levels` and flattens in the same order,
    so output stays bit-identical to the pre-grouping implementation.
    """
    lines: list[Line] = []
    for level_lines in iso_contour_levels(time_map, count, progress):
        lines.extend(level_lines)
    return lines


def clip_to_alpha(
    lines: list[Line],
    alpha: np.ndarray,
    threshold: float = 0.5,
) -> list[Line]:
    """Split contour lines wherever the nearest alpha sample is transparent.

    Closed rings are rotated to begin in transparent space before splitting;
    without that, an opaque run crossing the arbitrary first/last vertex would
    become two pen strokes.  Fully opaque rings keep their exact closure.
    """
    mask = np.asarray(alpha, dtype=np.float64)
    if mask.ndim != 2 or mask.size == 0:
        return []
    h, w = mask.shape

    def opaque(point: tuple[float, float]) -> bool:
        x, y = point
        xi = min(w - 1, max(0, int(round(x))))
        yi = min(h - 1, max(0, int(round(y))))
        return bool(mask[yi, xi] >= threshold)

    output: list[Line] = []
    for original in lines:
        if len(original) < 2:
            continue
        line = original
        closed = len(line) >= 3 and line[0] == line[-1]
        flags = [opaque(pt) for pt in line]
        if all(flags):
            output.append(list(line))
            continue
        if not any(flags):
            continue
        if closed:
            # Drop the repeated endpoint, rotate to a transparent sample, and
            # put that sample at both ends so no opaque run crosses the seam.
            body = line[:-1]
            body_flags = flags[:-1]
            cut = next(i for i, on in enumerate(body_flags) if not on)
            body = body[cut:] + body[:cut]
            line = body + [body[0]]

        segment: Line = []
        for point in line:
            if opaque(point):
                segment.append(point)
            else:
                if len(segment) >= 2:
                    output.append(segment)
                segment = []
        if len(segment) >= 2:
            output.append(segment)
    return output
