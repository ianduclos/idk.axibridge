"""A test bed for the process devices (round 15, thread D `meas`): parts
placed in given boxes, and a score recorded of what actually happened
between them. Not a composer: the relations are measured, not decided.

arranger `meas_boxes`: part i runs in box i (fractions of the sheet box,
four numbers per part); every part becomes a score layer (role from
`roles`, default "line"), and between every later part and
every earlier one the score records what the geometry did:
- `cross`  the later line crosses the earlier (at = its first crossing in
           the later line's own order; s = the arc range on the earlier
           line between the first and last crossing; the note counts them);
- `near`   no crossing: the closest approach (at = its midpoint; the note
           gives the gap in mm).
Marks carry meta["score_layer"] = their layer id."""
from __future__ import annotations

import numpy as np

from ._score import Score
from .core import P, arranger


def _arc(points: np.ndarray) -> np.ndarray:
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]


def _relations(score: Score, ids: list[str], lines: list[list[np.ndarray]]) -> None:
    import shapely  # noqa: PLC0415
    from shapely.ops import nearest_points  # noqa: PLC0415
    geo = [shapely.MultiLineString([p for p in ls if len(p) >= 2]) if ls else None for ls in lines]
    for j in range(len(lines)):
        for i in range(j):
            if geo[i] is None or geo[j] is None or geo[i].is_empty or geo[j].is_empty:
                continue
            hit = geo[j].intersection(geo[i])
            pts = [np.asarray(g.coords[0]) for g in getattr(hit, "geoms", [hit]) if not g.is_empty
                   and g.geom_type == "Point"]
            if pts:
                # order along the later line (j), arc range on the earlier line (i)
                cat_j = np.vstack(lines[j])
                sj = _arc(cat_j)
                first = min(pts, key=lambda q: sj[int(np.argmin(np.linalg.norm(cat_j - q, axis=1)))])
                cat_i = np.vstack(lines[i])
                si = _arc(cat_i)
                s_on_i = sorted(float(si[int(np.argmin(np.linalg.norm(cat_i - q, axis=1)))]) for q in pts)
                score.relate("cross", ids[j], ids[i], at=first, s=(s_on_i[0], s_on_i[-1]),
                             note=f"{len(pts)} crossings")
            else:
                a, b = nearest_points(geo[j], geo[i])
                at = ((a.x + b.x) / 2, (a.y + b.y) / 2)
                score.relate("near", ids[j], ids[i], at=at, note=f"{a.distance(b):.1f} mm apart")


@arranger("meas_boxes", params=[
    P("boxes", "floats", [], "x, y, w, h per part, as fractions of the sheet box (empty = every part fills it)"),
    P("roles", "str", "", "comma-separated score role per part (missing = line)"),
], doc="parts in given boxes; records a score of what the geometry did between them (cross / near)")
def meas_boxes(ctx, parts, *, boxes, roles):
    x0, y0, w, h = ctx.box
    score = Score()
    ids, lines, out = [], [], []
    rl = [r.strip() for r in str(roles).split(",")] if roles else []
    for i, p in enumerate(parts):
        b = boxes[4 * i:4 * i + 4] if len(boxes) >= 4 * (i + 1) else [0.0, 0.0, 1.0, 1.0]
        box = (x0 + b[0] * w, y0 + b[1] * h, b[2] * w, b[3] * h)
        marks = p.run(box)
        v = p.spec["voice"]
        lid = score.layer(rl[i] if i < len(rl) and rl[i] else "line", v["id"], part=p.index,
                          pen=p.renderer.get("pen") if isinstance(p.renderer, dict) else None,
                          params={k: val for k, val in v.items() if k != "id"},
                          label=p.label)
        ids.append(lid)
        marks = [m.evolve(meta={"score_layer": lid}) for m in marks]
        lines.append([np.asarray(m.points, float) for m in marks if len(m) >= 2])
        out += marks
    _relations(score, ids, lines)
    score.decide(boxes=list(boxes), arranger="meas_boxes", relations="measured")
    ctx.note("score", score.to_json())
    return out
