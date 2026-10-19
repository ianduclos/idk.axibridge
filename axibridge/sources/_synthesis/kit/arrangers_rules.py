# FROZEN from research commit a66c6a5: tools/gesture/gesture/kit/arrangers_rules.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 13, thread I-a `rules` — rules from the sheets, played as breakable rules.

Ian on the Oehlen conduction strip: "understand what he's doing (probably
intuitively, but that's a complex process with certain unnamed (breakable)
rules i would hypothesize) and then harness the compositional technique to
use other hand styles, techniques, regimes."

Each rule below is a hypothesis read off the 29 works on paper
(results/rules-2026-10-18.md has the table: support, contradiction). Here it
is a RELATION between layers, decided event by event on the project's own
material (a measurement chart, a far river) and the project's own hands.
Every rule has one reason to break, taken from the sheets that contradict
it; a break is a visible event and goes into the log.

    R1 weight follows ground   a made line is heavy (bold pen) while it is over
                               pasted found matter, a hairline in the blank.
                               BREAK (carry): after a long ride the line
                               carries the weight it took out into the blank.
    R2 exit carries the found  where a line leaves the found matter for the last
                               time, it takes the shape of the last found
                               contour it touched (the contour's own wiggle,
                               at its own scale) into the blank, the motif
                               growing in gradually; then it stops in the air.
                               BREAK (no blank left): the line ends over found
                               matter, and the motif is played there instead.
    R3 enter from the edge     a line starts at the sheet's edge with a small
                               orthogonal step (two right angles), then turns
                               free. BREAK (born of the found): a found
                               contour's end is within reach of the line's
                               start, so the line grows out of it instead.
    R4 curves listen           a line can be taken by a found contour (rides it,
                               0.9 mm beside, leaves at a tangent) only while
                               it is curving; straight stretches ignore.
                               BREAK (straight meets straight): a straight
                               stretch meets a straight found row running
                               parallel, and rides it anyway.
    R5 cover the densest       a cut cover (torn paper) lands on the densest
                               passage, after line `cover_after`, and cuts the
                               found matter only (the made line is never
                               covered). BREAK (own knot): when the densest
                               passage is mostly made ink, the cover cuts the
                               made lines too.

Channels on made marks: `neg` (0 own, 1 ride, 3 entry step, 4 ride by
break, 5 motif). Mark meta: `of_role` (found / made), `ink`, `pen`, `bold`.
The log is `sheet.marks[0].meta["rules"]["log"]`: one entry per event
{rule, event: fire|break, line, xy, s_mm, why}. `oehlen_found_ink` inks the
marks; `arrangers_oehlen_found.save` previews in colour.
"""
from __future__ import annotations

import math

import numpy as np

from .arrangers_oehlen_found import (FLEXOKI, Ground, arclen, bridge, clip_rect, cover_polygon, join, rect_polygon,
                                     resample, rotate, split_by_covers, tangents)
from .core import Mark, P, arranger, channel_kind

channel_kind("bold", "nearest")
RULES = {
    "R1": "weight follows ground",
    "R2": "exit carries the found",
    "R3": "enter from the edge",
    "R4": "curves listen",
    "R5": "cover the densest",
}
BREAKS = {
    "R1": "carry: a long ride's weight carried into the blank",
    "R2": "no blank left: the motif played over the found",
    "R3": "born of the found: the line grows out of a found end",
    "R4": "straight meets straight: a straight stretch rides a parallel row",
    "R5": "own knot: the densest passage is made ink, the cover cuts it",
}


# ---------------------------------------------------------------------------
# small geometry
# ---------------------------------------------------------------------------

def turning(p: np.ndarray, step: float, win_mm: float) -> np.ndarray:
    """|dθ/ds| (rad/mm), the heading change over ±win_mm around each point."""
    n = len(p)
    if n < 3:
        return np.zeros(n)
    t = tangents(p, 2)
    th = np.unwrap(np.arctan2(t[:, 1], t[:, 0]))
    k = max(int(round(win_mm / step)), 1)
    i = np.arange(n)
    a, b = np.maximum(i - k, 0), np.minimum(i + k, n - 1)
    return np.abs(th[b] - th[a]) / np.maximum((b - a) * step, 1e-9)


def residual(line: np.ndarray, step: float, sigma_mm: float) -> np.ndarray:
    """The contour's own wiggle: signed offset from its smoothed course (mm)."""
    from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
    sm = gaussian_filter1d(line, max(sigma_mm / step, 1.0), axis=0, mode="nearest")
    t = tangents(sm, 3)
    nrm = np.c_[-t[:, 1], t[:, 0]]
    return np.einsum("ij,ij->i", line - sm, nrm)


def _smoothstep(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


def _runs(flags: np.ndarray):
    """[(a, b, value)] index runs (b exclusive)."""
    if not len(flags):
        return []
    cut = np.flatnonzero(np.diff(flags.astype(int))) + 1
    a = np.r_[0, cut]
    b = np.r_[cut, len(flags)]
    return [(int(x), int(y), bool(flags[x])) for x, y in zip(a, b)]


def _merge_short(flags: np.ndarray, k_min: int) -> np.ndarray:
    """Runs shorter than k_min points take their neighbours' value (hysteresis)."""
    f = flags.copy()
    for _ in range(len(f)):
        runs = [r for r in _runs(f) if r[1] - r[0] < k_min and not (r[0] == 0 and r[1] == len(f))]
        if not runs:
            break
        a, b, v = min(runs, key=lambda r: (r[1] - r[0], r[0]))      # the shortest run gives way first
        f[a:b] = not v
    return f


# ---------------------------------------------------------------------------
# the walk: R4 (curves listen) over a Ground
# ---------------------------------------------------------------------------

def _name(found_kind, part) -> str:
    return {"chart": "the chart", "river": "the river"}.get(found_kind.get(part, ""), f"found part {part}")


def walk(M, G: Ground, owner: list[int], rng, *, found_kind=None, step, capture, align, ride, ride_sd, min_ride, max_offset,
         return_mm, ramp, ride_gap, listen_k, listen_win, max_rides, breaks, straight_k, line_id, log):
    """Re-walk the made line M against the found contours. Returns (points,
    tags, rides) with tags 0 own / 1 ride / 4 ride by break (R4)."""
    found_kind = found_kind or {}
    M = resample(M, step)
    n = len(M)
    tM = tangents(M, max(int(2.0 / step), 2))
    k_own = turning(M, step, listen_win)
    k_found = [turning(l, step, listen_win) for l in G.lines]
    pieces: list[tuple[np.ndarray, int]] = []
    rides = []
    d0 = np.zeros(2)
    i_leave = 0
    cur: list = []

    def disp(ii):
        if not np.any(d0):
            return np.zeros(2)
        u = (ii - i_leave) * step / max(return_mm, 1e-6)
        return np.zeros(2) if u >= 1 else d0 * (1 - (3 * u * u - 2 * u ** 3))

    def lognorm(mean):
        return float(mean * math.exp(rng.normal(0, ride_sd) - ride_sd ** 2 / 2))

    def contact(p, t):
        best = None
        for k in G.near(p, capture):
            j, ii = G.ids[k]
            c = abs(float(np.dot(G.tan[j][ii], t)))
            if c < align:
                continue
            dist = float(np.linalg.norm(G.pts[k] - p))
            score = dist - 2.0 * c
            if best is None or score < best[0]:
                best = (score, int(j), int(ii), 1 if float(np.dot(G.tan[j][ii], t)) > 0 else -1, c)
        return best

    i, cool = 0, 0
    while i < n:
        p = M[i] + disp(i)
        cur.append(p)
        if cool > 0:
            cool -= 1
            i += 1
            continue
        if len(rides) < max_rides and G.tree is not None:
            c = contact(p, tM[i])
            kind = None
            if c is not None:
                _, j, i0, direc, cosv = c
                if k_own[i] >= listen_k:
                    kind = "fire"
                elif (breaks and k_own[i] < straight_k and k_found[j][i0] < straight_k and cosv >= 0.985):
                    kind = "break"
            if kind is not None:
                _, j, i0, direc, _ = c
                line = G.lines[j]
                avail = (len(line) - 1 - i0) if direc > 0 else i0
                L = min(lognorm(ride), avail * step)
                if L >= min_ride:
                    m = int(round(L / step))
                    seg = line[i0:i0 + m + 1] if direc > 0 else line[max(i0 - m, 0):i0 + 1][::-1]
                    jj = np.minimum(i + np.arange(len(seg)), n - 1)
                    off = np.linalg.norm(seg - M[jj], axis=1)
                    k_min = int(round(min_ride / step))
                    ok = np.flatnonzero(off[k_min:] <= max_offset) + k_min
                    if len(ok):
                        seg = seg[: ok[-1] + 1]
                        if ride_gap > 0 and len(seg) >= 3:
                            tt = tangents(seg, 3)
                            nrm = np.c_[-tt[:, 1], tt[:, 0]]
                            side = 1.0 if float(np.dot(p - seg[0], nrm[0])) >= 0 else -1.0
                            seg = seg + side * ride_gap * nrm
                        if cur:
                            pieces.append((np.array(cur), 0))
                        tag = 1 if kind == "fire" else 4
                        pieces.append((seg, tag))
                        L_done = float(arclen(seg)[-1])
                        rides.append({"ground_line": int(j), "found_part": int(owner[j]), "len": L_done, "tag": tag,
                                      "end_index": int(min(i0 + (len(seg) - 1) * direc, len(line) - 1))
                                      if direc > 0 else int(max(i0 - (len(seg) - 1), 0))})
                        log.append({"rule": "R4", "event": kind, "line": line_id,
                                    "xy": [round(float(p[0]), 1), round(float(p[1]), 1)],
                                    "s_mm": round(i * step, 1), "ride_mm": round(L_done, 1),
                                    "why": (f"curving, taken by {_name(found_kind, owner[j])}" if kind == "fire"
                                            else BREAKS["R4"] + f" ({_name(found_kind, owner[j])})")})
                        i_new = min(i + len(seg), n - 1)
                        d0 = seg[-1] - M[i_new]
                        i_leave = i_new
                        cur = []
                        i = i_new + 1
                        cool = int(round(max(25.0, 2 * ramp) / step))
                        continue
        i += 1
    if cur:
        pieces.append((np.array(cur), 0))
    pts, tags = join(pieces, ramp, step)
    return pts, tags, rides


# ---------------------------------------------------------------------------
# R3: the entry
# ---------------------------------------------------------------------------

def _edge_point(p, frame, inset):
    W, H = frame
    cands = [((inset, p[1]), (1.0, 0.0)), ((W - inset, p[1]), (-1.0, 0.0)),
             ((p[0], inset), (0.0, 1.0)), ((p[0], H - inset), (0.0, -1.0))]
    d = [abs(p[0] - inset), abs(W - inset - p[0]), abs(p[1] - inset), abs(H - inset - p[1])]
    k = int(np.argmin(d))
    return np.array(cands[k][0], float), np.array(cands[k][1], float), float(d[k])


def entry(M, G, owner, found_kind, rng, *, frame, box, step, inset, grow_reach, breaks, ride, ride_gap,
          line_id, log):
    """Orient M to start near an edge, then either enter from the edge with an
    orthogonal step (R3 fire) or grow out of a nearby found end (R3 break).
    Returns (pieces [(pts, tag)], M possibly shifted)."""
    x0, y0, bw, bh = box
    lo, hi = np.array([x0, y0]), np.array([x0 + bw, y0 + bh])
    # the end nearer an edge starts the line (a plotted line has no direction)
    if _edge_point(M[-1], frame, inset)[2] < _edge_point(M[0], frame, inset)[2]:
        M = M[::-1].copy()
    if breaks and G.tree is not None:
        best = None
        for j, line in enumerate(G.lines):
            if (len(line) - 1) * step < 30.0 or found_kind[owner[j]] == "text":
                continue
            for end in (0, 1):
                e = line[-1] if end else line[0]
                d = float(np.linalg.norm(e - M[0]))
                if d <= grow_reach and (best is None or d < best[0]):
                    best = (d, j, end)
        if best is not None:
            _, j, end = best
            line = G.lines[j]
            k = int(round(min(ride, (len(line) - 1) * step) / step))
            tail = line[-k - 1:] if end else line[: k + 1][::-1]
            if ride_gap > 0 and len(tail) >= 3:
                t = tangents(tail, 3)
                tail = tail + ride_gap * np.c_[-t[:, 1], t[:, 0]]
            log.append({"rule": "R3", "event": "break", "line": line_id,
                        "xy": [round(float(tail[0][0]), 1), round(float(tail[0][1]), 1)], "s_mm": 0.0,
                        "why": BREAKS["R3"] + f" of {_name(found_kind, owner[j])} ({best[0]:.0f} mm away)",
                        "found_part": owner[j]})
            br = bridge(tail[-1], tangents(tail, 3)[-1], M[0], tangents(resample(M, step), 3)[0], step)
            tail = np.vstack([tail, br, M[:1]]) if len(br) else np.vstack([tail, M[:1]])
            return [(tail, 1)], M, {"grown_from": owner[j]}
    E, nrm, _ = _edge_point(M[0], frame, inset)
    tng = np.array([-nrm[1], nrm[0]])
    along = float(np.dot(M[0] - E, tng))
    sgn = 1.0 if along >= 0 else -1.0
    a1, b, a2 = rng.uniform(9, 20), rng.uniform(4, 9), rng.uniform(5, 12)
    stair = [E, E + nrm * a1, E + nrm * a1 + tng * sgn * b, E + nrm * (a1 + a2) + tng * sgn * b]
    s_end = stair[-1]
    # bring the line to the stair (at most 60 mm, inside its box), so the bridge stays short
    want = s_end + nrm * 8.0 - M[0]
    for f in (1.0, 0.7, 0.45, 0.25, 0.0):
        Mt = M + f * want * min(1.0, 60.0 / max(float(np.linalg.norm(want)), 1e-9))
        if np.all(Mt.min(axis=0) >= lo) and np.all(Mt.max(axis=0) <= hi):
            M = Mt
            break
    st = np.vstack([resample(np.array([stair[q], stair[q + 1]]), step)[:-1] for q in range(3)] + [s_end[None]])
    br = bridge(s_end, nrm, M[0], tangents(resample(M, step), 3)[0], step)
    st = np.vstack([st, br, M[:1]]) if len(br) else np.vstack([st, M[:1]])
    log.append({"rule": "R3", "event": "fire", "line": line_id,
                "xy": [round(float(E[0]), 1), round(float(E[1]), 1)], "s_mm": 0.0,
                "why": "enters from the edge with an orthogonal step"})
    return [(st, 3)], M, {}


# ---------------------------------------------------------------------------
# R2: the exit
# ---------------------------------------------------------------------------

def signed_turn(p: np.ndarray) -> np.ndarray:
    """Heading change per point (rad), len(p) values (0 at the ends)."""
    if len(p) < 3:
        return np.zeros(len(p))
    d = np.diff(p, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    return np.r_[0.0, np.diff(th), 0.0]


def feature_start(src, i0, *, step, window_mm, search_mm):
    """Where on the found contour the line reads its shape: within ±search_mm
    of the touch, the start of the window with the most turning (nearest on a
    tie) — a straight row is read at its nearest spike, a river at its
    nearest tight bend."""
    tr = np.abs(signed_turn(src))
    n = len(tr)
    w = max(int(round(window_mm / step)), 2)
    if n <= w:
        return 0
    c = np.r_[0.0, np.cumsum(tr)]
    k = int(round(search_mm / step))
    cand = np.arange(max(i0 - k, 0), min(i0 + k, n - w) + 1)
    if not len(cand):
        return 0
    tot = c[cand + w] - c[cand]
    best = np.flatnonzero(tot >= tot.max() - 1e-9)
    return int(cand[best[np.argmin(np.abs(cand[best] - i0))]])


def become(seg, src, i0, env, *, step, scale, sigma, bounds):
    """Re-integrate seg so that its turning goes from its own to the found
    contour src's own turning (read from index i0 on, `scale` times larger).
    If the result leaves `bounds`, the found turning is mirrored; if it still
    leaves, the line stops at the bound."""
    from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
    m = len(seg)
    own = signed_turn(seg)
    kf = signed_turn(src)
    if sigma > 0:
        kf = gaussian_filter1d(kf, max(sigma / step / 4, 0.5), mode="wrap")
    j = (i0 + (np.arange(m) / max(scale, 1e-6)).astype(int)) % max(len(kf), 1)
    x0, y0, x1, y1 = bounds
    best = None
    for sgn in (1.0, -1.0):
        turn = (1 - env) * own + env * sgn * kf[j] / max(scale, 1e-6)
        d0 = seg[1] - seg[0] if m > 1 else np.array([1.0, 0.0])
        h = math.atan2(d0[1], d0[0]) + np.cumsum(turn)
        q = seg[0] + np.vstack([[0.0, 0.0], np.cumsum(step * np.c_[np.cos(h[:-1]), np.sin(h[:-1])], axis=0)])
        ok = (q[:, 0] >= x0) & (q[:, 0] <= x1) & (q[:, 1] >= y0) & (q[:, 1] <= y1)
        k = int(np.argmin(ok)) if not ok.all() else m
        if best is None or k > best[0]:
            best = (k, q)
        if k == m:
            break
    k, q = best
    return q[:max(k, 2)]


def exit_motif(pts, tags, inside, region_of, G, owner, found_kind, rides, rng, *, step, motif_len, lead, sigma,
               motif_scale, bounds, breaks, line_id, log, loops_r, loops_p):
    """Find the last exit from found matter; the line takes the last found
    contour's own wiggle into the blank over motif_len, then stops."""
    n = len(pts)
    exits = [i for i in range(1, n) if inside[i - 1] and not inside[i]]
    s = arclen(pts)
    src_part, src_line, src_idx = None, None, None
    if rides:
        rd = rides[-1]
        src_part, src_line, src_idx = rd["found_part"], rd["ground_line"], rd["end_index"]
    where = None
    if exits:
        ie = exits[-1]
        part = int(region_of[ie - 1])
        if G.tree is not None:
            ks = [k for k in G.near(pts[ie - 1], 25.0) if owner[G.ids[k][0]] == part
                  and found_kind[owner[G.ids[k][0]]] != "text"]
            if ks:
                kbest = min(ks, key=lambda k: float(np.linalg.norm(G.pts[k] - pts[ie - 1])))
                if src_part is None or s[ie] - s[max(_last_ride_idx(tags), 0)] > 60.0:
                    src_part, src_line, src_idx = part, int(G.ids[kbest][0]), int(G.ids[kbest][1])
        tail = s[-1] - s[ie]
        if tail >= lead + 0.5 * motif_len:
            a = int(np.searchsorted(s, s[ie] + lead))
            where = "blank"
    if where is None:
        if not np.any(inside):
            # never touched the found: its own loops, at its end, in the blank (R2 fires, nothing to carry)
            a = int(np.searchsorted(s, max(s[-1] - motif_len, 0.0)))
            where = "own"
        else:
            # too little blank after the last exit: the motif takes the line's end, wherever that is
            a = int(np.searchsorted(s, max(s[-1] - motif_len, 0.0)))
            b0 = min(int(np.searchsorted(s, s[a] + motif_len)), n - 1)
            where = "over" if float(np.mean(inside[a:b0 + 1])) > 0.5 else "blank"
            if where == "over" and not breaks:
                return pts, tags, None
    b = int(np.searchsorted(s, s[a] + motif_len))
    b = min(b, n - 1)
    if b - a < 8:
        return pts, tags, None
    seg = resample(pts[a:b + 1], step)
    m = len(seg)
    t = tangents(seg, 3)
    nrm = np.c_[-t[:, 1], t[:, 0]]
    u = np.linspace(0, 1, m)
    env = _smoothstep(u / 0.55)
    if where != "own" and src_line is not None:
        # BECOME the found contour: from the exit on, the line's turning is handed over (env ramps 0 → 1)
        # from its own to the found contour's own turning, read from where the line last touched it and
        # played `motif_scale` times larger; the line keeps its own heading at the hand-over
        src_idx = feature_start(G.lines[src_line], int(src_idx or 0), step=step,
                                window_mm=motif_len / max(motif_scale, 1e-6), search_mm=40.0)
        new = become(seg, G.lines[src_line], src_idx, env, step=step, scale=motif_scale,
                     sigma=sigma, bounds=bounds)
        kind = f"becomes {_name(found_kind, src_part)}"
    else:
        th = 2 * math.pi * (u * motif_len) / loops_p
        rr = loops_r * env
        new = seg + rr[:, None] * ((np.cos(th) - 1)[:, None] * t + np.sin(th)[:, None] * nrm)
        kind = "its own loop train (no found touched)"
    out = np.vstack([pts[:a], new])
    otags = np.r_[tags[:a], np.full(len(new), 5.0)]
    unplayed = float(s[-1] - s[b])
    ev = "fire" if where in ("blank", "own") else "break"
    log.append({"rule": "R2", "event": ev, "line": line_id,
                "xy": [round(float(new[0][0]), 1), round(float(new[0][1]), 1)], "s_mm": round(float(s[a]), 1),
                "why": (f"leaves the found for the blank; {kind}; stops in the air"
                        if ev == "fire" else BREAKS["R2"] + f"; {kind}"),
                "unplayed_mm": round(unplayed, 1), "found_part": src_part})
    return out, otags, {"start": int(a), "where": where, "src_part": src_part}


def _last_ride_idx(tags):
    k = np.flatnonzero((tags == 1) | (tags == 4))
    return int(k[-1]) if len(k) else -1


# ---------------------------------------------------------------------------
# R5: density → cover
# ---------------------------------------------------------------------------

def densest(lines_by_role, frame, cw, ch, margin, cell=4.0):
    W, H = frame
    gx, gy = int(math.ceil(W / cell)), int(math.ceil(H / cell))
    grids = {}
    for role, lines in lines_by_role.items():
        g = np.zeros((gy, gx))
        for l in lines:
            if len(l) < 2:
                continue
            seg = np.linalg.norm(np.diff(l, axis=0), axis=1)
            mid = (l[1:] + l[:-1]) / 2
            ix = np.clip((mid[:, 0] / cell).astype(int), 0, gx - 1)
            iy = np.clip((mid[:, 1] / cell).astype(int), 0, gy - 1)
            np.add.at(g, (iy, ix), seg)
        grids[role] = g
    tot = sum(grids.values())
    kx, ky = max(int(cw / cell), 1), max(int(ch / cell), 1)
    S = np.pad(tot, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    best = None
    for iy in range(int(margin / cell), gy - ky - int(margin / cell) + 1):
        for ix in range(int(margin / cell), gx - kx - int(margin / cell) + 1):
            v = S[iy + ky, ix + kx] - S[iy, ix + kx] - S[iy + ky, ix] + S[iy, ix]
            if best is None or v > best[0]:
                best = (v, ix, iy)
    if best is None:
        return None
    v, ix, iy = best
    made = grids.get("made", np.zeros_like(tot))[iy:iy + ky, ix:ix + kx].sum()
    return ((ix + kx / 2) * cell, (iy + ky / 2) * cell), float(v), float(made / max(v, 1e-9))


# ---------------------------------------------------------------------------
# R2 then R1 on a walked line; emitting
# ---------------------------------------------------------------------------

def finish_line(d, *, on, G, owner, found_kind, r1_region, r2_region, rng, step, motif_len, lead, sigma, motif_scale, bounds, breaks,
                log, loops_r, loops_p, min_run, carry_min, carry_k):
    pts, tags = d["pts"], np.asarray(d["tags"], float)
    reg = r2_region(pts)
    if "R2" in on:
        p2, t2, info = exit_motif(pts, tags, reg >= 0, reg, G, owner, found_kind, d["rides"], rng, step=step,
                                  motif_len=motif_len, lead=lead, sigma=sigma, motif_scale=motif_scale, bounds=bounds,
                                  breaks=breaks, line_id=d["line"], log=log, loops_r=loops_r, loops_p=loops_p)
        if info is not None:
            pts, tags, d["motif"] = p2, t2, info
    reg = r1_region(pts)
    riding = (tags == 1) | (tags == 4)
    if "R1" in on:
        bold = _merge_short((reg >= 0) | riding, max(int(round(min_run / step)), 1))
        for a, b, v in _runs(bold)[1:]:
            log.append({"rule": "R1", "event": "fire", "line": d["line"],
                        "xy": [round(float(pts[a][0]), 1), round(float(pts[a][1]), 1)],
                        "s_mm": round(a * step, 1),
                        "why": "heavy over the found" if v else "a hairline into the blank"})
        if breaks:
            s = arclen(pts)
            for a, b, v in _runs(riding):
                if not v:
                    continue
                L = float(s[b - 1] - s[a])
                if L < carry_min or b >= len(pts):
                    continue
                reach = carry_k * L
                j = b
                added = 0
                while j < len(pts) and s[j] - s[b] < reach:
                    if not bold[j] and reg[j] < 0:
                        bold[j] = True
                        added += 1
                    j += 1
                if added * step >= 6.0:
                    log.append({"rule": "R1", "event": "break", "line": d["line"],
                                "xy": [round(float(pts[b][0]), 1), round(float(pts[b][1]), 1)],
                                "s_mm": round(float(s[b]), 1),
                                "why": BREAKS["R1"] + f" ({added * step:.0f} mm after a {L:.0f} mm ride)"})
    else:
        bold = np.ones(len(pts), bool)
    d.update(pts=pts, tags=tags, bold=bold)


def _emit(ctx, found_lines, made, covers, min_stub, step, found_ink, found_pen, made_ink, bold_pen, hair_pen, log,
          on, breaks):
    out: list[Mark] = []
    polys = [c for c, _ in covers]
    for pi, l, txt in found_lines:
        if polys:
            if txt:      # lettering is cut whole or left whole
                from shapely.geometry import LineString, Polygon  # noqa: PLC0415
                if any(LineString(l).intersects(Polygon(q)) for q in polys):
                    continue
                pieces = [l]
            else:
                pieces = [q for _, q, _ in split_by_covers([l], polys, min_stub, "cut")]
        else:
            pieces = [l]
        for q in pieces:
            out.append(Mark(q, {}, {"part": pi, "of_role": "found", "ink": found_ink, "pen": found_pen,
                                    "text": bool(txt)}))
    from scipy.spatial import cKDTree  # noqa: PLC0415
    for d in made:
        pts, tags, bold = d["pts"], d["tags"], d["bold"]
        cut_polys = [polys[k] for k in d.get("cut_by", [])]
        for a, b, v in _runs(bold):
            q = pts[a:min(b + 1, len(pts))]
            qt = tags[a:min(b + 1, len(pts))]
            if len(q) < 2:
                continue
            subs = [(q, qt)]
            if cut_polys:
                tree = cKDTree(q)
                subs = []
                for _, r, _ in split_by_covers([q], cut_polys, min_stub, "cut"):
                    r = resample(r, step)
                    subs.append((r, qt[tree.query(r)[1]]))
            for r, rt in subs:
                if len(r) < 2:
                    continue
                out.append(Mark(r, {"neg": rt, "bold": np.full(len(r), float(v))},
                                {"part": d["part"], "of_role": "made", "ink": made_ink,
                                 "pen": bold_pen if v else hair_pen, "bold": bool(v), "line": d["line"]}))
    meta = {"log": log, "rules": sorted(on), "breaks": bool(breaks),
            "covers": [{"polygon": np.round(c, 2).tolist(), "cuts_made": bool(cm)} for c, cm in covers],
            "lines": [{"line": d["line"], "part": d["part"], "len_mm": round(float(arclen(d["pts"])[-1]), 1),
                       "rides": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()}
                                 for r in d["rides"]],
                       "motif": d.get("motif"), "entry": d.get("info")}
                      for d in made]}
    if out:
        out[0] = out[0].evolve(meta={"rules": meta})
    return out


# ---------------------------------------------------------------------------
# the arranger
# ---------------------------------------------------------------------------

def _kind_of(part) -> str:
    vid = part.spec.get("voice", {}).get("id") if hasattr(part, "spec") else None
    return {"oehlen_found_river": "river", "diagram": "chart"}.get(vid or "", "printed")


@arranger("rules", params=[
    P("found", "int", 2, "the first n parts are found matter, pasted first", min=0, max=6),
    P("found_boxes", "floats", [0.5, 0.5, 0.9, 0.9, 0.0],
      "per found part: cx, cy, w, h (shares of the frame), angle (deg) of its pasted rectangle"),
    P("made_boxes", "floats", [], "per made part: cx, cy, w, h (shares); empty = the sheet box"),
    P("rules", "str", "R1,R2,R3,R4,R5", "which rules are in play (comma list)"),
    P("breaks", "bool", True, "rules may break (False = every rule obeyed: the rulebook drawing)"),
    P("step", "float", 0.4, "resampling step, mm", min=0.1, max=2.0),
    # R4
    P("capture", "float", 5.0, "R4: a found contour this near (mm) and aligned can take the line", min=0.2, max=30.0),
    P("align", "float", 0.6, "R4: |cos| between headings needed to ride", min=0.0, max=1.0),
    P("listen_k", "float", 0.05, "R4: the line listens while it turns at least this much (rad/mm)", min=0.0, max=2.0),
    P("straight_k", "float", 0.012, "R4 break: both stretches turn less than this (rad/mm)", min=0.0, max=1.0),
    P("listen_win", "float", 4.0, "R4: turning is measured over ± this many mm", min=0.5, max=40.0),
    P("ride", "float", 30.0, "R4: mean ride, mm", min=1.0, max=300.0),
    P("ride_sd", "float", 0.5, "R4: log-normal spread of ride lengths", min=0.0, max=1.5),
    P("min_ride", "float", 10.0, "R4: shorter rides are refused, mm", min=0.5, max=100.0),
    P("max_rides", "int", 4, "R4: most rides per line", min=0, max=40),
    P("max_offset", "float", 18.0, "R4: a ride ends before it carries the line further than this from its path",
      min=1.0, max=300.0),
    P("return_mm", "float", 35.0, "R4: after a ride the line swims back to its own path over this, mm",
      min=1.0, max=400.0),
    P("ramp", "float", 2.5, "tangent bridge at each enter/leave, mm", min=0.0, max=20.0),
    P("ride_gap", "float", 0.9, "R4: ride this far beside the found contour, mm", min=0.0, max=5.0),
    # R1
    P("min_run", "float", 14.0, "R1: a weight change holds at least this long, mm", min=0.0, max=200.0),
    P("carry_min", "float", 28.0, "R1 break: a ride at least this long carries its weight out", min=1.0, max=400.0),
    P("carry_k", "float", 1.0, "R1 break: carried weight = this × the ride's length, mm", min=0.0, max=5.0),
    P("region", "choice", "ink", "R1: what counts as 'over the found': ink (near found ink) | rect (inside a "
      "pasted rectangle)", choices=("ink", "rect")),
    P("region_pad", "float", 6.0, "R1 (ink): this near found ink counts as over it, mm",
      min=0.0, max=30.0),
    # R2
    P("exit_pad", "float", 10.0, "R2: the line has left the found when it is this far from found ink, mm",
      min=1.0, max=60.0),
    P("motif_len", "float", 70.0, "R2: the carried motif's length, mm", min=5.0, max=300.0),
    P("lead", "float", 10.0, "R2: the motif starts this far past the exit, mm", min=0.0, max=100.0),
    P("sigma", "float", 1.0, "R2: the found contour's turning is smoothed over this, mm", min=0.0, max=40.0),
    P("motif_scale", "float", 1.5, "R2: the found contour's turning is played this many times larger", min=0.25,
      max=10.0),
    P("loops_r", "float", 2.2, "R2 (nothing touched): loop radius, mm", min=0.1, max=20.0),
    P("loops_p", "float", 5.5, "R2 (nothing touched): loop period, mm", min=0.5, max=50.0),
    # R3
    P("inset", "float", 4.0, "R3: the edge is this far inside the paper's edge, mm", min=0.0, max=40.0),
    P("grow_reach", "float", 22.0, "R3 break: a found end this near the line's start bears it, mm",
      min=0.0, max=200.0),
    # R5
    P("cover_after", "int", 1, "R5: the cover comes after this many made lines (0 = before all; -1 = none)",
      min=-1, max=12),
    P("cover_wh", "floats", [34.0, 50.0], "R5: cover width, height, mm"),
    P("cover_tilt", "float", 8.0, "R5: tilt ±deg", min=0.0, max=60.0),
    P("cover_margin", "float", 14.0, "R5: covers keep this far inside the sheet, mm", min=0.0, max=80.0),
    P("made_share", "float", 0.45, "R5 break: the densest passage is this share made ink or more", min=0.0, max=1.0),
    P("cover_edge", "choice", "none", "R5: none (the cover shows only through what stops at it) | drawn (its "
      "outline in the found pen: the pasted paper's edge is found matter too)", choices=("none", "drawn")),
    P("min_stub", "float", 4.0, "a cut piece shorter than this (mm) is dropped", min=0.0, max=50.0),
    # pens
    P("found_ink", "str", "blue", "Flexoki pen for the found matter"),
    P("found_pen", "float", 0.3, "found pen, mm", min=0.05, max=3.0),
    P("made_ink", "str", "black", "Flexoki pen for the made lines"),
    P("bold_pen", "float", 0.9, "R1: heavy pen, mm", min=0.05, max=3.0),
    P("hair_pen", "float", 0.3, "R1: hairline pen, mm", min=0.05, max=3.0),
], doc="rules read off Oehlen's works on paper (R1 weight follows ground, R2 exit carries the found, R3 enter "
        "from the edge, R4 curves listen, R5 cover the densest), each breakable for a reason; the log says "
        "which fired or broke where")
def rules_arranger(ctx, parts, *, found, found_boxes, made_boxes, rules, breaks, step, capture, align, listen_k,
                   straight_k, listen_win, ride, ride_sd, min_ride, max_rides, max_offset, return_mm, ramp, ride_gap,
                   min_run, carry_min, carry_k, region, region_pad, exit_pad, motif_len, lead, sigma, motif_scale, loops_r,
                   loops_p, inset, grow_reach, cover_after, cover_wh, cover_tilt, cover_margin, made_share, cover_edge, min_stub,
                   found_ink, found_pen, made_ink, bold_pen, hair_pen):
    from shapely import contains_xy  # noqa: PLC0415
    from shapely.geometry import Polygon  # noqa: PLC0415
    for nm in (found_ink, made_ink):
        if nm not in FLEXOKI:
            raise ValueError(f"rules: unknown ink {nm!r}; choose from {sorted(FLEXOKI)}")
    on = {r.strip() for r in rules.split(",") if r.strip()}
    bad = on - set(RULES)
    if bad:
        raise ValueError(f"rules: unknown rule(s) {sorted(bad)}; choose from {sorted(RULES)}")
    W, H = ctx.frame
    found = min(found, len(parts))
    f_parts, m_parts = parts[:found], parts[found:]
    log: list[dict] = []

    # 1. found matter, pasted and cut to its rectangles
    fb = [found_boxes[i:i + 5] for i in range(0, len(found_boxes) - 4, 5)] or [[0.5, 0.5, 0.9, 0.9, 0.0]]
    found_lines, rects, kinds = [], [], {}
    for k, p in enumerate(f_parts):
        cx, cy, bw, bh, ang = fb[min(k, len(fb) - 1)]
        cx, cy, bw, bh = cx * W, cy * H, bw * W, bh * H
        rect = rect_polygon(cx, cy, bw, bh, ang)
        rects.append((p.index, rect))
        kinds[p.index] = _kind_of(p)
        for m in p.run((cx - bw / 2, cy - bh / 2, bw, bh)):
            q = rotate(m.points, np.array([cx, cy]), ang)
            for piece in clip_rect([q], rect, min_stub):
                ext = float(np.linalg.norm(piece.max(axis=0) - piece.min(axis=0)))
                found_lines.append((p.index, piece, ext < 5.0))      # short marks are lettering: never ridden
    ridable = [(pi, l) for pi, l, txt in found_lines if not txt]
    G = Ground([l for _, l in ridable], step, tag=1)
    # Ground drops lines shorter than 4 steps: rebuild the owner list on what it kept
    owner = []
    for pi, l in ridable:
        if len(l) >= 2 and arclen(np.asarray(l))[-1] > 4 * step:
            owner.append(pi)
    from shapely.geometry import MultiLineString  # noqa: PLC0415
    rect_pads = [(pi, Polygon(r).buffer(2.0)) for pi, r in rects]
    ink_pads, exit_pads = [], []
    for pi, _ in rects:
        ls = [l for q, l, txt in found_lines if q == pi and not txt and len(l) >= 2]
        if ls:
            mls = MultiLineString([x.tolist() for x in ls])
            ink_pads.append((pi, mls.buffer(region_pad, 8)))
            exit_pads.append((pi, mls.buffer(exit_pad, 8)))

    def _regions(pads):
        def f(points):
            reg = np.full(len(points), -1)
            for pi, poly in pads:
                hit = contains_xy(poly, points[:, 0], points[:, 1])
                reg[(reg < 0) & hit] = pi
            return reg
        return f
    r1_region = _regions(ink_pads if region == "ink" else rect_pads)
    r2_region = _regions(exit_pads)


    # 2. made lines, one after another; the cover comes between them
    mb = [made_boxes[i:i + 4] for i in range(0, len(made_boxes) - 3, 4)]
    made = []          # dicts: pts, tags, bold, part, covered_by (cover index or None)
    covers = []        # (poly, cuts_made)
    found_kind = {**kinds}

    def place_cover():
        lines_by_role = {"found": [l for _, l, _ in found_lines], "made": [d["pts"] for d in made]}
        cw, ch = (cover_wh + [34.0, 50.0])[:2]
        res = densest(lines_by_role, ctx.frame, cw, ch, cover_margin)
        if res is None:
            return
        c, v, share = res
        rng = ctx.rng("cover", len(covers))
        poly = cover_polygon(rng, c, cw, ch, "torn", cover_tilt)
        cuts_made = bool(breaks and share >= made_share)
        covers.append((poly, cuts_made))
        log.append({"rule": "R5", "event": "break" if cuts_made else "fire", "line": len(made),
                    "xy": [round(float(c[0]), 1), round(float(c[1]), 1)], "s_mm": 0.0,
                    "why": (BREAKS["R5"] if cuts_made else "a torn cover on the densest passage; it cuts the found "
                            "only") + f" (made share {share:.2f})", "made_share": round(share, 2)})
        if cuts_made:
            for d in made:
                d.setdefault("cut_by", []).append(len(covers) - 1)

    for li, p in enumerate(m_parts):
        if "R5" in on and cover_after == li:
            place_cover()
        box = ctx.box
        if li < len(mb):
            cx, cy, bw, bh = mb[li]
            box = (cx * W - bw * W / 2, cy * H - bh * H / 2, bw * W, bh * H)
        rng = ctx.rng("made", p.index)
        for m in p.run(box):
            M = resample(m.points, step)
            pieces, info = [], {}
            if "R3" in on:
                pieces, M, info = entry(M, G, owner, found_kind, rng, frame=ctx.frame, box=ctx.box, step=step,
                                        inset=inset, grow_reach=grow_reach, breaks=breaks, ride=ride,
                                        ride_gap=ride_gap, line_id=li, log=log)
            if "R4" in on:
                pts, tags, rides = walk(M, G, owner, rng, found_kind=found_kind, step=step, capture=capture, align=align, ride=ride,
                                        ride_sd=ride_sd, min_ride=min_ride, max_offset=max_offset,
                                        return_mm=return_mm, ramp=ramp, ride_gap=ride_gap, listen_k=listen_k,
                                        listen_win=listen_win, max_rides=max_rides, breaks=breaks,
                                        straight_k=straight_k, line_id=li, log=log)
            else:
                pts, tags, rides = M, np.zeros(len(M)), []
            if pieces:
                ent, etag = pieces[0]
                pts = np.vstack([ent[:-1], pts])
                tags = np.r_[np.full(len(ent) - 1, float(etag)), tags]
            d = {"pts": pts, "tags": tags, "rides": rides, "part": p.index, "info": info, "line": li}
            finish_line(d, on=on, G=G, owner=owner, found_kind=found_kind, r1_region=r1_region, r2_region=r2_region, rng=rng, step=step,
                        motif_len=motif_len, lead=lead, sigma=sigma, motif_scale=motif_scale,
                        bounds=(ctx.box[0], ctx.box[1], ctx.box[0] + ctx.box[2], ctx.box[1] + ctx.box[3]),
                        breaks=breaks, log=log, loops_r=loops_r, loops_p=loops_p, min_run=min_run,
                        carry_min=carry_min, carry_k=carry_k)
            made.append(d)
    if "R5" in on and cover_after >= len(m_parts):
        place_cover()
    out = _emit(ctx, found_lines, made, covers, min_stub, step, found_ink, found_pen, made_ink, bold_pen, hair_pen,
                log, on, breaks)
    if cover_edge == "drawn":
        for poly, _ in covers:
            out.append(Mark(poly, {}, {"part": f_parts[0].index if f_parts else 0, "of_role": "edge",
                                       "ink": found_ink, "pen": min(found_pen, 0.25)}))
    return out
