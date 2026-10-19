# FROZEN from research commit 071aea1: tools/gesture/gesture/kit/modulators_place.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Synthesis bench S2a: `place`, a written placement for a whole line (listen's speakers and river).

listen's composer grew a speaker in a box of its own, then laid it on the sheet: turned so its own
long axis runs along the sheet's (plus a small tilt), its centre moved to a chosen point, then shrunk
and shifted until it sits inside the margin (`Composer.speaker` / `river` / `_settle`). As a score
writer it keeps that WRITTEN place (Ian, 2026-10-19: speakers keep their place; listeners follow), so
the place is a modulator on the speaker's part: swap the speaker's hand and the new line is laid the
same way (its own axis found again, the same centre and tilt).

    {"id": "place", "centre": [120, 80], "align": 0, "tilt": 12.5, "turn_by": "axis",
     "box": [0, 0, 250, 175], "margin": 7}

- turn_by "axis": turn = align − (the line's own principal axis) + tilt; "absolute": align + tilt.
- `longest` keeps only the longest mark (listen works on one whole line); `step` resamples it
  (listen's 0.5 mm working step; channels carried).
"""
from __future__ import annotations

import math

import numpy as np

from .core import P, modulator


@modulator("place", params=[
    P("centre", "floats", None, "where the line's centre goes, [x, y] mm (null = where it is)",
      min=0.0, max=2000.0, min_len=2, max_len=2, optional=True),
    P("align", "float", 0.0, "the direction the line is laid along, degrees", min=-360.0, max=360.0),
    P("tilt", "float", 0.0, "turned this much more, degrees", min=-180.0, max=180.0),
    P("turn_by", "choice", "axis", "axis: its own long axis goes to `align`; absolute: turned by align + tilt",
      choices=("axis", "absolute")),
    P("box", "floats", None, "settle inside [x, y, w, h] mm (null = the frame)", min=0.0, max=2000.0,
      min_len=4, max_len=4, optional=True),
    P("margin", "float", 7.0, "…this far inside it, mm (shrunk about its middle if it is too big)",
      min=0.0, max=60.0),
    P("longest", "bool", True, "keep only the longest mark"),
    P("step", "float", 0.5, "resample at this step, mm (0 = leave the samples)", min=0.0, max=5.0),
], doc="lay a line on the sheet: turned along an axis, centred on a point, settled inside the margin "
       "(listen's speaker placement, written)")
def place(ctx, marks, *, centre, align, tilt, turn_by, box, margin, longest, step):
    ms = [m for m in marks if len(m) >= 2]
    if not ms:
        return list(marks)
    if longest:
        ms = [max(ms, key=lambda m: m.length())]
    if step > 0:
        ms = [m.resampled(step) if m.length() > step else m for m in ms]
    ref = max(ms, key=lambda m: m.length()).points
    c0 = ref.mean(axis=0)
    if turn_by == "axis":
        ev = np.linalg.eigh(np.cov((ref - c0).T))[1][:, -1]
        turn = align - math.degrees(math.atan2(ev[1], ev[0])) + tilt
    else:
        turn = align + tilt
    a = math.radians(turn)
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    target = c0 if centre is None else np.asarray(centre, float)
    pts = [(m.points - c0) @ R.T + target for m in ms]       # rotate about the centre, then move it
    if box is None:
        W, H = ctx.frame
        x0, y0, x1, y1 = 0.0, 0.0, float(W), float(H)
    else:
        x0, y0, x1, y1 = box[0], box[1], box[0] + box[2], box[1] + box[3]
    allp = np.vstack(pts)
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    k = min(1.0, (x1 - x0 - 2 * margin) / max(hi[0] - lo[0], 1e-9), (y1 - y0 - 2 * margin) / max(hi[1] - lo[1], 1e-9))
    k = max(k, 1e-3)
    mid = (lo + hi) / 2
    pts = [(p - mid) * k + mid for p in pts]
    allp = np.vstack(pts)
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    shift = (np.clip(np.array([x0 + margin, y0 + margin]) - lo, 0, None)
             - np.clip(hi - np.array([x1 - margin, y1 - margin]), 0, None))
    return [m.evolve(points=p + shift, meta={"placed": {"turn_deg": round(turn, 2), "scale": round(k, 4)}})
            for m, p in zip(ms, pts)]
