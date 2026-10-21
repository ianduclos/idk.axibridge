# FROZEN from research commit d5ccd75: tools/gesture/gesture/kit/relations_aware_more.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 16 thread A `aware`: three more awareness relations, in sympathy's register (felt before
named, never obvious). Ian on the sympathy close-up: "perhaps there are other ideas".

- `hesitate` (contact)   a line grows unsure as it closes in on another (nearness × the rate it
  approaches, so running calmly beside it does nothing): a fine tremor that rises before it arrives (`before` mm ahead) and settles after (`after` mm), strongest where they meet. The
  hand slowing down, written as denser turning. The other line is untouched.
- `accompany` (contact)  where the dst already runs beside the src (within `reach`, nearly
  parallel), it holds the distance it arrived at for a while (`hold` mm, varied), copying the
  src's course, then lets go and returns to its own. Not every such run: `chance` each.
- `make_room` (contact)  the past makes room for the future: when a line is placed, an earlier
  line (the src) that passes close to it without crossing bows away to `room` mm, as if it had
  known the later line was coming. It rewrites the src, which only a contact relation may do.
  Near a crossing the push fades out (a crossing cannot be avoided by bowing).

All three are smoothed so no kink appears, and none hears a line continued in another layer
(a join, see `relations_aware`).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from ._relations import RelOut, crossings, relation
from .core import P
from .relations_aware import _ends, _fine, _frame, _join_mask, _moved, _pool, _runs


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _envelope(near: np.ndarray, s: np.ndarray, before: float, after: float) -> np.ndarray:
    """Asymmetric hold of `near` along s: it rises `before` mm ahead of a contact and decays over
    `after` mm behind it (exponential running maxima, both directions)."""
    n = len(near)
    f = near.copy()
    b = near.copy()
    for k in range(1, n):
        ds = s[k] - s[k - 1]
        f[k] = max(f[k], f[k - 1] * (math.exp(-ds / after) if after > 0 else 0.0))
    for k in range(n - 2, -1, -1):
        ds = s[k + 1] - s[k]
        b[k] = max(b[k], b[k + 1] * (math.exp(-ds / before) if before > 0 else 0.0))
    return np.maximum(f, b)


def tremor(rng, s: np.ndarray, wave: float) -> np.ndarray:
    """A hand's tremor along s: a wavering of about `wave` mm whose phase drifts and whose size
    breathes (never a clean sine), unit amplitude."""
    n = len(s)
    if n < 3:
        return np.zeros(n)
    stp = max(float(np.median(np.diff(s))), 1e-6)
    drift = gaussian_filter1d(rng.standard_normal(n), 2.0 * wave / stp, mode="wrap")
    drift = drift / max(float(np.std(drift)), 1e-9) * 1.2
    size = gaussian_filter1d(rng.standard_normal(n), 3.0 * wave / stp, mode="wrap")
    size = 0.75 + 0.25 * size / max(float(np.max(np.abs(size))), 1e-9)
    ph = float(rng.random()) * 2 * math.pi
    return np.sin(2 * math.pi * s / wave + ph + drift) * size


@relation("hesitate", phase="contact", params=[
    P("reach", "float", 3.0, "it begins to hesitate this close to the other line, mm", min=0.5, max=15.0),
    P("amp", "float", 0.16, "the tremor at its strongest, mm", min=0.0, max=1.5),
    P("wave", "float", 1.3, "the tremor's wavelength, mm", min=0.4, max=8.0),
    P("before", "float", 6.0, "how far ahead of the meeting it starts, mm", min=0.0, max=40.0),
    P("after", "float", 2.5, "how fast it settles after, mm", min=0.0, max=40.0),
    P("join", "float", 4.0, "a line continued in another layer is not heard this near the join, mm",
      min=0.0, max=20.0),
], doc="a line grows unsure as it nears another: a fine tremor that rises before it arrives and "
       "settles after")
def hesitate(rctx, src, dst, *, reach, amp, wave, before, after, join):
    H = _pool(src, other_ends=_ends(dst), join=join)
    if H.tree is None or amp <= 0:
        return RelOut()
    src_ends = _ends(src)
    out, events, moved = [], [], False
    for i, m0 in enumerate(dst):
        if len(m0) < 4:
            out.append(m0)
            continue
        m = _fine(m0, min(0.5, wave / 5.0))
        p, s = m.points, m.arclength()
        d, _ = H.tree.query(p, distance_upper_bound=reach)
        dd = np.where(np.isfinite(d), d, reach)
        stp = max(float(np.median(np.diff(s))), 1e-6)
        # nearness × approach: it hesitates while closing in on the other (or crossing it), not while
        # running calmly beside it
        closing = np.clip(-np.gradient(gaussian_filter1d(dd, 0.5 / stp, mode="nearest"), s), 0.0, 1.0)
        closing = gaussian_filter1d(closing, 1.0 / stp, mode="nearest")
        near = np.clip(1.0 - dd / reach, 0.0, 1.0) ** 1.5 * np.clip(closing * 2.0, 0.0, 1.0)
        near[_join_mask(m, src_ends, join)] = 0.0
        if near.max() <= 0:
            out.append(m0)
            continue
        env = _envelope(near, s, before, after)
        env = np.clip((env - 0.03) / 0.97, 0.0, 1.0)      # the exponential tails end: far away it is untouched
        env = gaussian_filter1d(env, 0.5 / stp, mode="nearest")
        tr = tremor(rctx.rng("hesitate", i), s, wave)
        disp = amp * env * tr
        disp = gaussian_filter1d(disp, wave / 8.0 / stp, mode="nearest")
        _, nrm = _frame(p)
        out.append(_moved(m, disp[:, None] * nrm, rctx.frame))
        moved = True
        for a, b in _runs(env > 0.25):
            if s[b - 1] - s[a] < 1.0:
                continue
            k = a + int(np.argmax(env[a:b]))
            events.append({"outcome": "hesitate", "at": p[k].tolist(), "s": [float(s[a]), float(s[b - 1])],
                           "mark": i, "peak_mm": round(float(np.max(np.abs(disp[a:b]))), 3)})
    return RelOut(dst=out, events=events) if moved else RelOut()


@relation("accompany", phase="contact", params=[
    P("reach", "float", 6.0, "it only accompanies a line it already runs this close to, mm", min=1.0, max=20.0),
    P("angle", "float", 25.0, "…and this nearly parallel to, degrees", min=1.0, max=60.0),
    P("hold", "float", 22.0, "how long it holds the distance, mm", min=2.0, max=200.0),
    P("hold_var", "float", 0.5, "the hold varies by up to this share", min=0.0, max=0.9),
    P("ease", "float", 5.0, "it falls into step and lets go over this, mm", min=0.5, max=30.0),
    P("chance", "float", 0.7, "chance each run beside the other is taken up", min=0.0, max=1.0),
    P("join", "float", 4.0, "a line continued in another layer is not heard this near the join, mm",
      min=0.0, max=20.0),
], doc="two lines keep a constant distance for a while, then let go: where the dst already runs "
       "beside the src it holds the distance it arrived at, then returns to its own course")
def accompany(rctx, src, dst, *, reach, angle, hold, hold_var, ease, chance, join):
    H = _pool(src, other_ends=_ends(dst), join=join)
    if H.tree is None:
        return RelOut()
    src_ends = _ends(src)
    cosmax = math.cos(math.radians(angle))
    out, events, moved = [], [], False
    rng = rctx.rng("accompany")
    for i, m0 in enumerate(dst):
        if len(m0) < 6 or m0.length() < 2 * ease + 2:
            out.append(m0)
            continue
        m = _fine(m0)
        p, s = m.points, m.arclength()
        t, _ = _frame(p)
        d, j = H.tree.query(p, distance_upper_bound=reach)
        ok = np.isfinite(d)
        jj = np.where(ok, j, 0)
        ok &= np.abs(np.sum(t * H.tan[jj], axis=1)) >= cosmax
        ok &= ~_join_mask(m, src_ends, join)
        # one pass of the src at a time: the nearest src sample must move on smoothly
        hop = np.r_[False, (H.mark[jj[1:]] != H.mark[jj[:-1]]) | (np.abs(H.s[jj[1:]] - H.s[jj[:-1]]) > 3.0)]
        ok &= ~hop
        disp = np.zeros_like(p)
        for a, b in _runs(ok):
            L = s[b - 1] - s[a]
            u_take, u_hold = (float(v) for v in rng.random(2))
            if L < 2 * ease + 2.0 or u_take >= chance:
                continue
            j0 = int(jj[a])
            dist = float((p[a] - H.pts[j0]) @ H.nrm[j0])
            hold_mm = hold * (1.0 + hold_var * (2.0 * u_hold - 1.0))
            s_go = min(s[a] + ease + hold_mm, s[b - 1] - ease)
            w = _smoothstep((s - s[a]) / ease) * (1.0 - _smoothstep((s - s_go) / ease))
            w[:a] = 0.0
            w[b:] = 0.0
            seg = slice(a, b)
            q = H.pts[jj[seg]] + dist * H.nrm[jj[seg]]
            stp = max(float(np.median(np.diff(s))), 1e-6)
            q = np.column_stack([gaussian_filter1d(q[:, c], 1.0 / stp, mode="nearest") for c in (0, 1)])
            disp[seg] += w[seg, None] * (q - p[seg])
            k = a + int(np.argmax(w[seg]))
            events.append({"outcome": "accompany", "at": p[k].tolist(), "s": [float(s[a]), float(s_go + ease)],
                           "mark": i, "dist_mm": round(abs(dist), 2), "hold_mm": round(hold_mm, 1)})
        if not np.any(disp):
            out.append(m0)
            continue
        stp = max(float(np.median(np.diff(s))), 1e-6)
        disp = np.column_stack([gaussian_filter1d(disp[:, c], 0.6 / stp, mode="nearest") for c in (0, 1)])
        out.append(_moved(m, disp, rctx.frame))
        moved = True
    return RelOut(dst=out, events=events) if moved else RelOut()


@relation("make_room", phase="contact", params=[
    P("room", "float", 2.0, "the earlier line bows away until this much room is left, mm", min=0.5, max=10.0),
    P("strength", "float", 0.6, "how much of the missing room it makes", min=0.0, max=1.0),
    P("clear", "float", 5.0, "near a crossing the bow fades out over this, mm", min=0.5, max=30.0),
    P("join", "float", 4.0, "a line continued in another layer is not heard this near the join, mm",
      min=0.0, max=20.0),
], doc="the past makes room for the future: an earlier line that passes close to a later one bows "
       "away from it, as if it had known")
def make_room(rctx, src, dst, *, room, strength, clear, join):
    H = _pool(dst, other_ends=_ends(src), join=join)
    if H.tree is None or strength <= 0:
        return RelOut()
    dst_ends = _ends(dst)
    out, events, moved = [], [], False
    for i, m0 in enumerate(src):
        if len(m0) < 6:
            out.append(m0)
            continue
        m = _fine(m0)
        p, s = m.points, m.arclength()
        d, j = H.tree.query(p, distance_upper_bound=room)
        near = np.isfinite(d) & ~_join_mask(m, dst_ends, join)
        if not near.any():
            out.append(m0)
            continue
        jj = np.where(near, j, 0)
        _, nrm = _frame(p)
        away = p - H.pts[jj]
        away = away / np.maximum(np.linalg.norm(away, axis=1, keepdims=True), 1e-9)
        push = np.where(near, (room - np.where(near, d, room)) * strength, 0.0) * np.sum(away * nrm, axis=1)
        # near a crossing the bow fades out (a crossing cannot be bowed away from), and near the
        # line's own ends too (an end that flicks away reads as a hook)
        taper = _smoothstep(s / clear) * _smoothstep((s[-1] - s) / clear)
        for c in crossings(dst, [m]):
            taper *= _smoothstep(np.abs(s - c.s_dst) / clear)
        push = np.clip(push, -0.6 * room, 0.6 * room)
        stp = max(float(np.median(np.diff(s))), 1e-6)
        disp = gaussian_filter1d(push * taper, max(room / 2.0, 0.5) / stp, mode="nearest")
        if float(np.max(np.abs(disp))) < 0.03:
            out.append(m0)
            continue
        out.append(_moved(m, disp[:, None] * nrm, rctx.frame))
        moved = True
        for a, b in _runs(np.abs(disp) > 0.08):
            if s[b - 1] - s[a] < 1.0:
                continue
            k = a + int(np.argmax(np.abs(disp[a:b])))
            events.append({"outcome": "make_room", "at": p[k].tolist(), "s_src": [float(s[a]), float(s[b - 1])],
                           "mark_src": i, "push_mm": round(float(np.max(np.abs(disp[a:b]))), 3)})
    return RelOut(src=out, events=events) if moved else RelOut()
