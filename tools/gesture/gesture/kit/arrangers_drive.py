"""Round 12, thread `drive` — the drawing beside its drivers.

`drive_beside` draws every part in a drawing box (one surface) and, unless
`show` = hidden, a measurement in the rest of the frame, laid out like a
drum record: each part's line STRAIGHTENED (arc length → x, wrapped into
rows; the same channels, so the same renderer inks it — width, pens, knots,
tremor as they fall along the line), and under each row the raw driver
values that steered it (one thin trace per drive_* modulator, normalised;
a pen trace is split into the pens it chose). The measurement is a chart
on purpose; the drawing is not. Same recipe, `show` = hidden → the drawing
alone (the honest test: does it still have a rhythm no hand makes?).
"""
from __future__ import annotations

import math

import numpy as np

from .core import Mark, P, arranger

SHOW = ("beside", "hidden", "measure")
LAYOUT = ("below", "right", "above", "left")


def _concat_s(marks):
    out, off = [], 0.0
    for m in marks:
        s = m.arclength()
        out.append(s + off)
        off += float(s[-1]) if len(s) else 0.0
    return out, off


def _band_h(marks, scale, pen=0.4):
    w = [float(np.max(m.channel("dw", pen))) for m in marks if len(m)]
    k = [float(np.max(m.channel("knot", 0.0))) for m in marks if len(m)]
    t = [float(np.max(np.abs(m.channel("tremor", 0.0)))) for m in marks if len(m)]
    return scale * max(max(w or [pen]), 6.0 * max(k or [0.0]), 2 * max(t or [0.0]) + pen) + 1.5


def _targets(marks):
    """One trace per distinct signal (a channel driving two targets is drawn once)."""
    seen, keys = [], []
    for m in marks:
        for r in m.meta.get("drive", []):
            key = (r["driver"], r["channel"], r["transform"], r["t0_s"], r["span_s"])
            if r["target"] not in [x["target"] for x in seen] and key not in keys:
                seen.append(r)
                keys.append(key)
    return seen


def _slice(m: Mark, idx: np.ndarray, pts: np.ndarray, meta: dict, scale: float) -> Mark:
    ch = {k: np.asarray(v)[idx] for k, v in m.channels.items()}
    if "dw" in ch:
        ch["dw"] = ch["dw"] * scale
    return Mark(pts, ch, {**m.meta, **meta})


def measurement(part_marks, box, *, scale, trace_h, row_gap, traces, unroll, max_traces):
    """Marks of the drum-record measurement for one part, in box."""
    x0, y0, W, H = box
    marks = [m for m in part_marks if len(m) >= 2]
    if not marks:
        return [], 0.0
    ss, L = _concat_s(marks)
    tg = _targets(marks)[:max_traces] if traces else []
    band = _band_h(marks, scale) if unroll else 0.0
    row_h = band + len(tg) * trace_h + row_gap
    Wr = W
    n_rows = max(int(math.ceil(L * scale / Wr - 1e-9)), 1)
    out = []
    for m, s in zip(marks, ss):
        x = s * scale
        row = np.minimum((x // Wr).astype(int), n_rows - 1)
        for r in np.unique(row):
            idx = np.nonzero(row == r)[0]
            if len(idx) < 2:
                continue
            xr = x0 + x[idx] - r * Wr
            yb = y0 + r * row_h
            if unroll:
                trem = np.asarray(m.channel("tremor", 0.0))[idx] * scale
                pts = np.column_stack([xr, yb + 0.5 * band + trem])
                out.append(_slice(m, idx, pts, {"drive_role": "unrolled", "drive_scale": scale,
                                                "drive_row": int(r)}, scale))
            for k, rec in enumerate(tg):
                u = np.asarray(m.channel(f"drv_{rec['target']}", 0.0))[idx]
                yt = yb + band + k * trace_h
                if rec.get("signed"):
                    yy = yt + 0.5 * trace_h * (1.0 - 0.85 * u)
                else:
                    yy = yt + trace_h * (0.92 - 0.85 * u)
                ch = {}
                meta = {"drive_role": "trace", "drive_target": rec["target"], "drive_row": int(r)}
                if rec["target"] == "pen" and "pen_i" in m.channels:
                    ch["pen_i"] = np.asarray(m["pen_i"])[idx]
                else:
                    meta["drive_pens"] = None
                out.append(Mark(np.column_stack([xr, yy]), {**ch, "r": np.zeros(len(idx))},
                                {**{k2: v for k2, v in m.meta.items() if k2 in ("part", "voice_id", "drive_pens")},
                                 **meta}))
    return out, n_rows * row_h - row_gap


def _fit_scale(part_marks, box, trace_h, row_gap, traces, unroll, max_traces, scale_max):
    x0, y0, W, H = box
    lo, hi = 0.01, scale_max
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        used = sum(measurement(pm, (x0, 0, W, 1e9), scale=mid, trace_h=trace_h, row_gap=row_gap, traces=traces,
                               unroll=unroll, max_traces=max_traces)[1] + row_gap for pm in part_marks) - row_gap
        if used <= H:
            lo = mid
        else:
            hi = mid
    return lo


@arranger("drive_beside", params=[
    P("show", "choice", "beside", "beside: drawing + its measurement | hidden: the drawing alone | measure: "
      "only the measurement", choices=SHOW),
    P("layout", "choice", "below", "where the measurement sits", choices=LAYOUT),
    P("share", "float", 0.36, "share of the frame the measurement takes", min=0.05, max=0.9),
    P("gap", "float", 8.0, "space between drawing and measurement, mm", min=0.0, max=100.0),
    P("scale", "float", None, "straightened line scale (null = the largest that fits, ≤ scale_max)",
      min=0.01, max=1.0, optional=True),
    P("scale_max", "float", 1.0, "auto scale never exceeds this", min=0.01, max=1.0),
    P("trace_h", "float", 6.0, "height of one driver trace, mm", min=1.0, max=60.0),
    P("row_gap", "float", 3.0, "space between drum rows, mm", min=0.0, max=40.0),
    P("traces", "bool", True, "draw the raw driver traces"),
    P("unroll", "bool", True, "draw the straightened line"),
    P("max_traces", "int", 4, "at most this many traces per part", min=0, max=12),
], doc="the drawing beside its drivers: the line straightened into drum rows over the raw signals that steered it")
def drive_beside(ctx, parts, *, show, layout, share, gap, scale, scale_max, trace_h, row_gap, traces, unroll,
                 max_traces):
    x0, y0, W, H = ctx.box
    if show == "hidden":
        dbox, mbox = ctx.box, None
    elif show == "measure":
        dbox, mbox = ctx.box, ctx.box
    elif layout in ("below", "above"):
        hm = H * share
        hd = H - hm - gap
        dbox = (x0, y0, W, hd) if layout == "below" else (x0, y0 + hm + gap, W, hd)
        mbox = (x0, y0 + hd + gap, W, hm) if layout == "below" else (x0, y0, W, hm)
    else:
        wm = W * share
        wd = W - wm - gap
        dbox = (x0, y0, wd, H) if layout == "right" else (x0 + wm + gap, y0, wd, H)
        mbox = (x0 + wd + gap, y0, wm, H) if layout == "right" else (x0, y0, wm, H)
    placed = [p.run(dbox) for p in parts]
    out = [] if show == "measure" else [m for grp in placed for m in grp]
    if mbox is None:
        return out
    sc = scale if scale is not None else _fit_scale(placed, mbox, trace_h, row_gap, traces, unroll, max_traces,
                                                     scale_max)
    y = mbox[1]
    for grp in placed:
        ms, used = measurement(grp, (mbox[0], y, mbox[2], mbox[3]), scale=sc, trace_h=trace_h, row_gap=row_gap,
                               traces=traces, unroll=unroll, max_traces=max_traces)
        out += [m.evolve(meta={"drive_measure_scale": sc}) for m in ms]
        y += used + row_gap
    return out
