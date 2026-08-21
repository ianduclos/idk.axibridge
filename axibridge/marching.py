"""Marching squares: a scalar lattice in, closed contour loops out.

Extracted from ``sources.image_threshold``, which traced an image's dark
regions with it, when a second caller appeared: ``effects.eigen_fill`` traces
the ZERO level set of a vibrational mode with the same machinery. The move was
verbatim — an image contour and a nodal line are the same problem once the
field is on a lattice, and there is no version of "a second marching squares"
that stays in step with the first.

The two rules a caller has to know, both inherited from the image tracer:

* the field must already be **padded** with a ring of values on the outside
  of the level being traced, or a region touching the lattice edge never
  closes and its loop is dropped;
* "inside" is ``value < t`` strictly, so a padding value EQUAL to ``t`` reads
  as outside. Loops come back closed (first == last) in mm, at ``cell`` pitch,
  in lattice coordinates — the caller subtracts its own padding offset.

Saddle cells (marching-squares cases 5 and 10) are disambiguated by the mean
of the four corners, which is the standard bilinear-centre rule and keeps
adjacent cells consistent.
"""

from __future__ import annotations


def trace_contours(field: list[list[float]], t: float, cell: float) -> list[list[tuple[float, float]]]:
    """Marching squares with interpolation. ``field`` is padded already; the
    returned loops are in mm, closed (first == last)."""
    ny, nx = len(field), len(field[0])
    pts: dict[tuple, tuple[float, float]] = {}     # edge key -> crossing point
    seg: dict[tuple, list[tuple]] = {}             # edge key -> connected edge keys

    def cross(a, b, fa, fb):
        """Interpolated crossing on the lattice edge a->b (lattice coords)."""
        frac = 0.5 if fb == fa else (t - fa) / (fb - fa)
        return ((a[0] + (b[0] - a[0]) * frac) * cell, (a[1] + (b[1] - a[1]) * frac) * cell)

    def link(e1, e2):
        seg.setdefault(e1, []).append(e2)
        seg.setdefault(e2, []).append(e1)

    for j in range(ny - 1):
        row0, row1 = field[j], field[j + 1]
        for i in range(nx - 1):
            tl, tr, br, bl = row0[i], row0[i + 1], row1[i + 1], row1[i]
            case = (tl < t) | ((tr < t) << 1) | ((br < t) << 2) | ((bl < t) << 3)
            if case in (0, 15):
                continue
            top, right = ("h", i, j), ("v", i + 1, j)
            bottom, left = ("h", i, j + 1), ("v", i, j)
            if top not in pts and case in (1, 2, 5, 6, 9, 10, 13, 14):
                pts[top] = cross((i, j), (i + 1, j), tl, tr)
            if right not in pts and case in (2, 3, 4, 5, 10, 11, 12, 13):
                pts[right] = cross((i + 1, j), (i + 1, j + 1), tr, br)
            if bottom not in pts and case in (4, 5, 6, 7, 8, 9, 10, 11):
                pts[bottom] = cross((i, j + 1), (i + 1, j + 1), bl, br)
            if left not in pts and case in (1, 3, 5, 7, 8, 10, 12, 14):
                pts[left] = cross((i, j), (i, j + 1), tl, bl)
            if case in (5, 10):  # saddle: split by the cell-centre value
                centre_dark = (tl + tr + br + bl) / 4 < t
                if (case == 5) == centre_dark:
                    link(top, right); link(bottom, left)
                else:
                    link(top, left); link(bottom, right)
            else:
                edges = {
                    1: (left, top), 2: (top, right), 3: (left, right),
                    4: (right, bottom), 6: (top, bottom), 7: (left, bottom),
                    8: (bottom, left), 9: (bottom, top), 11: (bottom, right),
                    12: (right, left), 13: (right, top), 14: (top, left),
                }[case]
                link(*edges)

    loops: list[list[tuple[float, float]]] = []
    used: set[tuple] = set()
    for start in seg:
        if start in used:
            continue
        loop_keys = [start]
        used.add(start)
        prev, cur = None, start
        while True:
            nxt = next((k for k in seg[cur] if k != prev and k not in used), None)
            if nxt is None:
                break
            loop_keys.append(nxt)
            used.add(nxt)
            prev, cur = cur, nxt
        if len(loop_keys) >= 3 and loop_keys[0] in seg[loop_keys[-1]]:
            loop = [pts[k] for k in loop_keys]
            loop.append(loop[0])
            loops.append(loop)
    return loops


def shoelace(loop: list[tuple[float, float]]) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(loop, loop[1:]))) / 2
