"""Boundary threading: join per-level Fast Marching iso-contours into a few
long serpentine pen-down paths instead of one pen-lift per level.

This is original to axibridge — reverse-engineered from reference SVGs of a
known plotter-artist technique (contour lines from an edge-seeded travel-time
field, successive levels stitched along the image frame into long connected
strokes) rather than ported from any published source. The published
padcrafting/ContourTool project establishes the speed mapping this family of
generators uses but has no threading and seeds from a point, not an edge; no
code from it appears here.

The idea: iso-contours from an edge-seeded wavefront are (mostly) open lines
that each touch the frame rectangle at both ends, and consecutive levels
touch the frame at nearly the same point (the front barely moved between two
close-together levels). So walking the shortest way *along the frame* from
one level's exit point to the next level's nearest entry point is almost
always a short hop down one edge — chaining levels this way produces a
serpentine: draw a level across the image, hop a little way down the frame,
draw the next level back across, hop again. The direction alternation is not
special-cased; it falls out of always taking the nearer of a fragment's two
orientations.
"""

from __future__ import annotations

from collections.abc import Callable

Point = tuple[float, float]
Line = list[Point]
Progress = Callable[[float], None]

# Rectangle corners in clockwise order starting at the origin, used to walk
# "around the corner" without ever cutting a diagonal through the interior.
_CORNER_ORDER = (0, 1, 2, 3)


def _snap(v: float, hi: float, tol: float) -> float:
    if abs(v) <= tol:
        return 0.0
    if abs(v - hi) <= tol:
        return hi
    return v


def thread_boundary(
    levels: list[list[Line]],
    w: int,
    h: int,
    max_join: float = 30.0,
    tol: float = 1.5,
    prefer_axis: str | None = None,
    progress: Progress | None = None,
) -> list[Line]:
    """Join per-level contour groups (as returned by
    :func:`_fast_marching.iso_contour_levels`, already in arrival-time order)
    into threaded polylines.

    ``w, h`` are the grid dimensions contourpy traced against — its frame is
    ``x in [0, w-1]``, ``y in [0, h-1]``. Endpoints within ``tol`` grid units
    of that rectangle snap exactly onto it so float noise from the Eikonal
    solve never leaves a connector a hair off the edge.

    Closed rings (``first == last``) and lines with neither endpoint on the
    frame (interior fragments left behind by alpha clipping) are never
    threaded — they pass through as their own single-fragment output lines.

    For everything else: process levels in order, keep a "current trail"
    whose live end sits on the frame, and repeatedly attach the closest
    still-unused fragment (in whichever of its two orientations starts
    nearer) whose start point is reachable by walking *along the frame
    perimeter* — through corners, never a diagonal — within ``max_join``
    grid units. When nothing is within reach the trail closes and a new one
    starts from the next unused fragment. Search covers the whole
    not-yet-used pool rather than strictly "the next level": in the common
    case (one fragment per level) that's the same thing, but it also lets an
    obstacle-split level's second piece get picked up without derailing the
    main trail.

    ``prefer_axis`` ('x' or 'y') only orients the very first fragment of
    each *new* trail — e.g. 'x' for a top/bottom-seeded front makes the
    first line run left-to-right, matching how the wavefront actually
    crosses the image. Every later attachment orientation is decided purely
    by which end is nearer; that's what produces the alternating serpentine,
    not this hint.
    """
    frame_w = w - 1
    frame_h = h - 1
    if frame_w <= 0 or frame_h <= 0:
        return [line for group in levels for line in group]

    perim_len = 2.0 * frame_w + 2.0 * frame_h
    corners: list[Point] = [
        (0.0, 0.0),
        (float(frame_w), 0.0),
        (float(frame_w), float(frame_h)),
        (0.0, float(frame_h)),
    ]
    corner_coords: list[float] = [
        0.0,
        float(frame_w),
        float(frame_w + frame_h),
        float(2 * frame_w + frame_h),
    ]

    def snap_pt(pt: Point) -> Point:
        x, y = pt
        return (_snap(x, float(frame_w), tol), _snap(y, float(frame_h), tol))

    def on_frame(pt: Point) -> bool:
        x, y = pt
        return x == 0.0 or x == float(frame_w) or y == 0.0 or y == float(frame_h)

    def perim_coord(pt: Point) -> float | None:
        x, y = pt
        if y == 0.0 and x < frame_w:
            return x
        if x == frame_w and y < frame_h:
            return frame_w + y
        if y == frame_h and x > 0.0:
            return frame_w + frame_h + (frame_w - x)
        if x == 0.0:
            return 2 * frame_w + frame_h + (frame_h - y)
        return None

    def walk(a_pt: Point, b_pt: Point, forward: bool) -> tuple[list[Point], float]:
        """Points strictly between a and b along the frame (corners only,
        b included, a excluded), walking clockwise if forward else
        counter-clockwise, plus the walked distance."""
        a = perim_coord(a_pt)
        b = perim_coord(b_pt)
        assert a is not None and b is not None
        total = (b - a) % perim_len if forward else (a - b) % perim_len
        hits: list[tuple[float, Point]] = []
        for cp, cc in zip(corners, corner_coords):
            rel = ((cc - a) % perim_len) if forward else ((a - cc) % perim_len)
            if 1e-9 < rel < total - 1e-9:
                hits.append((rel, cp))
        hits.sort(key=lambda t: t[0])
        pts = [p for _, p in hits]
        pts.append(snap_pt(b_pt))
        return pts, total

    # -- build the fragment pool -------------------------------------------------
    output: list[Line] = []
    pool: list[dict] = []
    for group in levels:
        for line in group:
            if len(line) < 2:
                continue
            closed = len(line) >= 3 and line[0] == line[-1]
            if closed:
                output.append(list(line))
                continue
            pts = list(line)
            pts[0] = snap_pt(pts[0])
            pts[-1] = snap_pt(pts[-1])
            start_on = on_frame(pts[0])
            end_on = on_frame(pts[-1])
            if not start_on and not end_on:
                output.append(pts)
                continue
            pool.append({
                "points": pts, "start_on": start_on, "end_on": end_on, "used": False,
            })

    total = len(pool)
    if total == 0:
        return output
    done = 0

    def report() -> None:
        if progress is not None:
            progress(done / total)

    def find_new_start() -> int | None:
        for i, frag in enumerate(pool):
            if not frag["used"]:
                return i
        return None

    def start_trail() -> tuple[list[Point], Point | None]:
        i = find_new_start()
        if i is None:
            return [], None
        frag = pool[i]
        pts = frag["points"]
        end_on = frag["end_on"]
        if prefer_axis == "x" and pts[0][0] > pts[-1][0]:
            pts = list(reversed(pts))
            end_on = frag["start_on"]
        elif prefer_axis == "y" and pts[0][1] > pts[-1][1]:
            pts = list(reversed(pts))
            end_on = frag["start_on"]
        frag["used"] = True
        return list(pts), (pts[-1] if end_on else None)

    def best_continuation(end_pt: Point):
        best = None
        for i, frag in enumerate(pool):
            if frag["used"]:
                continue
            for reversed_, start_valid in ((False, frag["start_on"]), (True, frag["end_on"])):
                if not start_valid:
                    continue
                cand_start = frag["points"][-1] if reversed_ else frag["points"][0]
                for forward in (True, False):
                    walk_pts, dist = walk(end_pt, cand_start, forward)
                    if dist <= max_join and (best is None or dist < best[0]):
                        best = (dist, i, reversed_, walk_pts)
        return best

    current: list[Point] | None = None
    current_end: Point | None = None

    while True:
        if current is None:
            current, current_end = start_trail()
            if not current:
                current = None
                break
            done += 1
            report()
            if current_end is None:
                output.append(current)
                current = None
            continue

        best = best_continuation(current_end)
        if best is None:
            output.append(current)
            current = None
            continue

        _dist, i, reversed_, walk_pts = best
        frag = pool[i]
        frag["used"] = True
        done += 1
        frag_pts = list(reversed(frag["points"])) if reversed_ else list(frag["points"])
        for pt in walk_pts + frag_pts:
            if current and current[-1] == pt:
                continue
            current.append(pt)
        far_on = frag["start_on"] if reversed_ else frag["end_on"]
        current_end = frag_pts[-1] if far_on else None
        report()
        if current_end is None:
            output.append(current)
            current = None

    if current:
        output.append(current)
    return output
