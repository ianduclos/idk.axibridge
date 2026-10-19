# FROZEN from research commit c712045: tools/gesture/gesture/kit/arrangers_oehlen_found.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Round 12, thread `oehlen_found` — D1 found ground, negotiated line + D2 cover cuts.

After Albert Oehlen's works on paper (results/oehlen-research-2026-10-17.md):
the Krebber leaves (1994: his line grows out of another artist's printed
drawing), the 2009–2013 collage-drawings (a line over found printed matter
that it borrows from or ignores) and the covered passages (pasted paper,
white smear, the 2022 plastic sheet). Procedures, never his forms.

    found parts   drawn first in a thin coloured pen, each "pasted" into its
                  own (rotated) rectangle and cut to it: the project's own
                  printed matter (a measurement plate) or a far view of a
                  river (`oehlen_found_river`, GRWL centrelines at
                  ~1000–2500 channel widths: a tight zigzag band, Ian's
                  ruling of 2026-10-17)
    made parts    a hand's line that NEGOTIATES the found layer as events,
                  not as a field:
                    grow    the line starts ON a found contour, rides it, leaves
                    borrow  while listening, it snaps onto an aligned found
                            contour within `capture` mm, rides it for a
                            stretch, leaves at a tangent and swims back to
                            its own path over `return_mm`
                    ignore  between listening windows it crosses anything
    covers        1–3 cut-paper shapes: everything drawn so far is cut
                  (removed) inside, or re-inked in another pen (`tint`,
                  the plastic sheet); pieces left shorter than `min_stub`
                  are dropped; covers sit on a late line's path, away from
                  the margin, so a later line always crosses them
    late parts    drawn after the covers, never cut; may borrow the
                  covers' (undrawn) edges — the edge shows only where the
                  late line rides it

The river's stems are FROZEN in the library (kind `river_stems`, entry
`grwl_far_sb19`: GRWL SB19's longest main stem, the one every recipe of the
thread draws), so the voice draws without the local corpus and the app can
run it (round-12 keeps, 2026-10-18). A tile/rank the entry does not hold is
still read from `.local/gesture/corpus/earth/grwl-vec-<tile>` (research
only); `stems: null` always reads the corpus. Same stem ⇒ same points either
way (`experiments/keeps13_river_stems.py` checks it before saving).

Channels written: `neg` on made/late marks (0 own, 1 riding a found
contour, 2 riding a cover edge). Mark meta: `of_role` (found / made / late
/ edge), `ink` (Flexoki name), `pen` (mm). `oehlen_found_ink` inks them;
`render_colour(sheet)` / `save(sheet, path)` preview in the pens' colours.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import library as L
from .core import INK, PAPER, Ink, Mark, P, arranger, channel_kind, fitted, renderer, voice
from .dev_chorus import FLEXOKI as _FX

FLEXOKI = {**_FX, "blue-400": "#4385BE", "cyan-400": "#3AA99F", "green-400": "#879A39",
           "red-400": "#D14D41", "orange-400": "#DA702C", "purple-400": "#8B7EC8",
           "magenta-400": "#CE5D97", "yellow-400": "#D0A215"}
ROLES = ("found", "made", "late", "edge")
channel_kind("neg", "nearest")


# ---------------------------------------------------------------------------
# polyline helpers
# ---------------------------------------------------------------------------

def arclen(p: np.ndarray) -> np.ndarray:
    if len(p) < 2:
        return np.zeros(len(p))
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


def resample(p: np.ndarray, step: float) -> np.ndarray:
    p = np.asarray(p, float)
    s = arclen(p)
    if len(p) < 2 or s[-1] <= 0:
        return p.copy()
    n = max(int(round(s[-1] / step)), 1)
    t = np.linspace(0.0, s[-1], n + 1)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def tangents(p: np.ndarray, k: int = 4) -> np.ndarray:
    """Unit tangents from a ±k-point chord (smoothed heading)."""
    n = len(p)
    if n < 2:
        return np.tile([1.0, 0.0], (n, 1))
    i = np.arange(n)
    d = p[np.minimum(i + k, n - 1)] - p[np.maximum(i - k, 0)]
    L = np.linalg.norm(d, axis=1, keepdims=True)
    return d / np.maximum(L, 1e-9)


def rotate(p: np.ndarray, c: np.ndarray, deg: float) -> np.ndarray:
    a = math.radians(deg)
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    return (np.asarray(p, float) - c) @ R.T + c


def bridge(a_end, ta, b_start, tb, step: float) -> np.ndarray:
    """Cubic Bézier from a_end (heading ta) to b_start (heading tb)."""
    d = float(np.linalg.norm(b_start - a_end))
    if d < 1e-6:
        return np.empty((0, 2))
    h = d / 2.6
    c1, c2 = a_end + ta * h, b_start - tb * h
    n = max(int(d / step) + 2, 3)
    t = np.linspace(0, 1, n)[1:-1, None]
    return ((1 - t) ** 3) * a_end + 3 * ((1 - t) ** 2) * t * c1 + 3 * (1 - t) * t * t * c2 + t ** 3 * b_start


def join(pieces: list[tuple[np.ndarray, int]], ramp: float, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Join (points, tag) pieces into one line: each junction trims `ramp`
    mm from both sides and bridges them with a tangent-continuous Bézier
    (the line LEAVES at a tangent). Returns points + per-point tag."""
    pieces = [(np.asarray(p, float), t) for p, t in pieces if len(p) >= 2]
    if not pieces:
        return np.empty((0, 2)), np.empty(0)
    k = max(int(round(ramp / step)), 0)
    trimmed = []
    for i, (p, t) in enumerate(pieces):
        a = k if i > 0 else 0
        b = len(p) - (k if i < len(pieces) - 1 else 0)
        if b - a < 2:                      # too short to trim on both sides: keep its middle point pair
            m = len(p) // 2
            a, b = max(m - 1, 0), min(m + 1, len(p))
        trimmed.append((p[a:b], t))
    pts, tags = [trimmed[0][0]], [np.full(len(trimmed[0][0]), trimmed[0][1], float)]
    for (pa, ta), (pb, tb) in zip(trimmed[:-1], trimmed[1:]):
        hA = tangents(pa, 3)[-1]
        hB = tangents(pb, 3)[0]
        br = bridge(pa[-1], hA, pb[0], hB, step)
        pts += [br, pb]
        tags += [np.full(len(br), min(ta, tb), float), np.full(len(pb), tb, float)]
    return np.vstack(pts), np.concatenate(tags)


# ---------------------------------------------------------------------------
# negotiation: a made line against found contours
# ---------------------------------------------------------------------------

class Ground:
    """Found contours as one KD-indexed point set (resampled at `step`)."""

    def __init__(self, lines: list[np.ndarray], step: float, tag: int = 1):
        from scipy.spatial import cKDTree  # noqa: PLC0415
        self.lines = [resample(l, step) for l in lines if len(l) >= 2 and arclen(np.asarray(l))[-1] > 4 * step]
        self.tan = [tangents(l, max(int(2.0 / step), 2)) for l in self.lines]
        self.tag = tag
        if self.lines:
            self.pts = np.vstack(self.lines)
            self.ids = np.concatenate([np.c_[np.full(len(l), j), np.arange(len(l))] for j, l in enumerate(self.lines)])
            self.tree = cKDTree(self.pts)
        else:
            self.pts, self.ids, self.tree = np.empty((0, 2)), np.empty((0, 2), int), None

    def near(self, p, r):
        if self.tree is None:
            return []
        return self.tree.query_ball_point(p, r)


def ride_along(G: Ground, j: int, i0: int, direction: int, length: float, step: float):
    line = G.lines[j]
    n = int(round(length / step))
    if direction > 0:
        seg = line[i0:i0 + n + 1]
    else:
        seg = line[max(i0 - n, 0):i0 + 1][::-1]
    return seg


def negotiate(M: np.ndarray, grounds: list[Ground], rng: np.random.Generator, *, step: float, capture: float,
              align: float, ride: float, ride_sd: float, min_ride: float, listen: float, ignore: float,
              return_mm: float, ramp: float, grow: bool, grow_reach: float, max_rides: int,
              max_offset: float = 1e9, ride_gap: float = 0.0, bounds=(-1e9, -1e9, 1e9, 1e9),
              grow_flip: bool = True):
    """The made line M (sheet mm) re-walked against found contours. Returns
    (points, neg tags, log)."""
    M = resample(M, step)
    tM = tangents(M, max(int(2.0 / step), 2))
    n = len(M)
    pieces: list[tuple[np.ndarray, int]] = []
    log = []
    d0 = np.zeros(2)
    i_leave = 0
    i = 0
    cur = []
    rides = 0

    def disp(ii):
        if not np.any(d0):
            return np.zeros(2)
        u = (ii - i_leave) * step / max(return_mm, 1e-6)
        if u >= 1:
            return np.zeros(2)
        w = 1 - (3 * u * u - 2 * u ** 3)
        return d0 * w

    def lognorm(mean):
        return float(mean * math.exp(rng.normal(0, ride_sd) - ride_sd ** 2 / 2))

    # windows: alternate ignore / listen, lengths in mm along the made line
    windows = []
    s_tot = (n - 1) * step
    s = 0.0
    mode = "ignore" if rng.random() < 0.5 else "listen"
    while s < s_tot:
        L = lognorm(ignore if mode == "ignore" else listen)
        windows.append((s, s + L, mode))
        s += L
        mode = "listen" if mode == "ignore" else "ignore"

    def listening(ii):
        si = ii * step
        for a, b, m in windows:
            if a <= si < b:
                return m == "listen"
        return False

    def best_contact(p, t, r):
        best = None
        for G in grounds:
            for k in G.near(p, r):
                j, ii = G.ids[k]
                c = float(np.dot(G.tan[j][ii], t))
                if abs(c) < align:
                    continue
                dist = float(np.linalg.norm(G.pts[k] - p))
                score = dist - 2.0 * abs(c)
                if best is None or score < best[0]:
                    best = (score, G, int(j), int(ii), 1 if c > 0 else -1)
        return best

    def start_ride(contact, ii, forced_len=None):
        nonlocal d0, i_leave, cur, rides
        _, G, j, i0, direc = contact
        avail = (len(G.lines[j]) - 1 - i0) if direc > 0 else i0
        L = forced_len if forced_len is not None else lognorm(ride)
        L = min(L, avail * step)
        if L < min_ride:
            return None
        seg = ride_along(G, j, i0, direc, L, step)
        # leave where the own line is nearest (a tangent exit back toward its own path), never beyond max_offset
        jj = np.minimum(ii + np.arange(len(seg)), n - 1)
        off = np.linalg.norm(seg - M[jj], axis=1)
        k_min = int(round(min_ride / step))
        if forced_len is None:
            ok = np.flatnonzero(off[k_min:] <= max_offset) + k_min
            if not len(ok):
                return None
            seg = seg[: ok[-1] + 1]
        if ride_gap > 0 and len(seg) >= 3:
            # trace BESIDE the found contour, on the side the line came from: the borrowing stays visible
            t = tangents(seg, 3)
            nrm = np.c_[-t[:, 1], t[:, 0]]
            ref = M[min(ii, n - 1)] + disp(ii)
            side = 1.0 if float(np.dot(ref - seg[0], nrm[0])) >= 0 else -1.0
            seg = seg + side * ride_gap * nrm
        if cur:
            pieces.append((np.array(cur), 0))
        pieces.append((seg, G.tag))
        rides += 1
        i_new = min(ii + len(seg), n - 1)
        d0 = seg[-1] - M[i_new]
        i_leave = i_new
        cur = []
        log.append({"at_mm": round(ii * step, 1), "ride_mm": round(L, 1), "ground": G.tag,
                    "offset_mm": round(float(np.linalg.norm(d0)), 1)})
        return i_new

    if grow:
        # GROW OUT OF the found layer (the Krebber move): the made line is moved (turned + shifted, at most
        # grow_reach mm) so that it starts at the END of a found contour, continuing its heading; it first
        # traces that contour's last stretch, then goes its own way
        best = None
        k0 = max(int(round(5.0 / step)), 2)
        h0 = M[min(k0, n - 1)] - M[0]
        a_own = math.atan2(h0[1], h0[0])
        x0, y0, x1, y1 = bounds
        for G in grounds:
            if G.tag != 1:                              # grow from found contours, never from a cover edge
                continue
            for j, line in enumerate(G.lines):
                Lj = (len(line) - 1) * step
                if Lj < max(2 * min_ride, 30.0):       # grow from a real contour, not a glyph
                    continue
                for end in (0, 1):
                    e = line[-1] if end else line[0]
                    t_out = (line[-1] - line[-1 - k0]) if end else (line[0] - line[k0])
                    rot = math.degrees(math.atan2(t_out[1], t_out[0]) - a_own)
                    move = float(np.linalg.norm(e - M[0]))
                    if move > grow_reach:
                        continue
                    for sc in (1.0, 0.9, 0.8):
                        Mt = (rotate(M, M[0], rot) - M[0]) * sc + e
                        lo, hi = Mt.min(axis=0), Mt.max(axis=0)
                        if lo[0] < x0 or lo[1] < y0 or hi[0] > x1 or hi[1] > y1:
                            continue
                        score = move + 0.15 * abs(((rot + 180) % 360) - 180) + 60.0 * (1 - sc)
                        if best is None or score < best[0]:
                            best = (score, G, j, end, rot, e, sc)
                        break
        if best is None:
            # no rigid move fits the sheet: keep the line where it is and let it begin from the nearest
            # found contour END instead (the tail is traced, then a tangent bridge joins the line's start)
            for G in grounds:
                if G.tag != 1:
                    continue
                for j, line in enumerate(G.lines):
                    if (len(line) - 1) * step < max(2 * min_ride, 30.0):
                        continue
                    for end in (0, 1):
                        e = line[-1] if end else line[0]
                        for flip in ((False, True) if grow_flip else (False,)):   # either end may start
                            move = float(np.linalg.norm(e - (M[-1] if flip else M[0])))
                            if move <= grow_reach and (best is None or move < best[0]):
                                best = (move, G, j, end, flip, None, 1.0, e)
            if best is not None:
                _, G, j, end, flip, _, _, e = best
                if flip:
                    M = M[::-1].copy()
                    tM = tangents(M, max(int(2.0 / step), 2))
                line = G.lines[j]
                k = int(round(min(lognorm(ride), (len(line) - 1) * step) / step))
                tail = line[-k - 1:] if end else line[: k + 1][::-1]
                pieces.append((tail, G.tag))
                rides += 1
                log.append({"at_mm": 0.0, "ride_mm": round(k * step, 1), "ground": G.tag, "grow": "bridge",
                            "gap_mm": round(float(np.linalg.norm(e - M[0])), 1)})
                best = None
        if best is not None:
            _, G, j, end, rot, e, sc = best
            m0 = M[0].copy()
            M = resample((rotate(M, M[0], rot) - M[0]) * sc + e, step)
            n = len(M)
            tM = tangents(M, max(int(2.0 / step), 2))
            line = G.lines[j]
            k = int(round(min(lognorm(ride), (len(line) - 1) * step) / step))
            tail = line[-k - 1:] if end else line[: k + 1][::-1]
            if ride_gap > 0 and len(tail) >= 3:
                t = tangents(tail, 3)
                tail = tail + ride_gap * np.c_[-t[:, 1], t[:, 0]]
            pieces.append((tail, G.tag))
            rides += 1
            log.append({"at_mm": 0.0, "ride_mm": round(k * step, 1), "ground": G.tag, "grow": True,
                        "moved_mm": round(float(np.linalg.norm(m0 - e)), 1), "turned_deg": round(rot, 1),
                        "scale": sc})
    cool = 0
    while i < n:
        p = M[i] + disp(i)
        cur.append(p)
        if cool > 0:
            cool -= 1
        elif rides < max_rides and listening(i):
            c = best_contact(p, tM[i], capture)
            if c is not None:
                r = start_ride(c, i)
                if r is not None:
                    i = r + 1
                    cool = int(round(max(listen, 2 * ramp) / step))
                    continue
        i += 1
    if cur:
        pieces.append((np.array(cur), 0))
    pts, tags = join(pieces, ramp, step)
    return pts, tags, log


# ---------------------------------------------------------------------------
# covers
# ---------------------------------------------------------------------------

def cover_polygon(rng, c, w, h, shape: str, tilt: float, edge: int | None = None,
                  angle: float | None = None) -> np.ndarray:
    """A cut-paper shape around centre c: `cut` (a skewed quadrilateral),
    `torn` (one edge torn), `sheet` (rounded corners, the plastic sheet)."""
    ang = float(rng.uniform(-tilt, tilt)) if angle is None else float(angle)
    if shape == "sheet":
        r = 0.12 * min(w, h)
        pts = []
        for cx, cy, a0 in ((w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0),
                           (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)):
            for a in np.radians(np.linspace(a0, a0 + 90, 10)):
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        poly = np.array(pts)
    else:
        jit = rng.normal(0, 0.035, (4, 2)) * [w, h]
        q = np.array([[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]]) + jit
        if shape == "torn":
            e = int(rng.integers(4)) if edge is None else int(edge) % 4
            a, b = q[e], q[(e + 1) % 4]
            L = float(np.linalg.norm(b - a))
            m = max(int(L / 0.8), 8)
            t = np.linspace(0, 1, m)
            nrm = np.array([-(b - a)[1], (b - a)[0]]) / max(L, 1e-9)
            walk = np.cumsum(rng.normal(0, 0.35, m))
            walk -= np.linspace(walk[0], walk[-1], m)
            fine = rng.normal(0, 0.25, m)
            edge = a + np.outer(t, b - a) + np.outer(walk + fine, nrm)
            poly = np.vstack([q[: e + 1], edge[1:-1], q[e + 1:]]) if e < 3 else np.vstack([q, edge[1:-1]])
        else:
            poly = q
    poly = rotate(poly, np.zeros(2), ang) + np.asarray(c)
    return np.vstack([poly, poly[:1]])


def boundary_runs(l, boundary, classify):
    """Cut a polyline ONLY where it meets `boundary` (a shapely linear geometry) → [(run, class)], with
    `classify(xy) → int array` naming each run by a point inside it (closed polygons, as shapely: a run
    lying ON the boundary counts as inside); neighbouring runs of one class (a
    touch, not a crossing) are joined. Each crossing is found on its own segment, so a long segment
    through a thin polygon is cut too. Unlike shapely's LineString ∩ / − Polygon, which also nodes a line
    at its OWN crossings, a self-crossing line stays one run wherever no boundary cuts it (2026-10-18)."""
    import shapely  # noqa: PLC0415
    p = np.asarray(l, float)
    n = len(p)
    if n < 2:
        return []
    a, b = p[:-1], p[1:]
    segs = shapely.linestrings(np.stack([a, b], axis=1))
    shapely.prepare(boundary)
    hit = np.flatnonzero(shapely.intersects(segs, boundary))
    vcut = np.zeros(n, bool)
    ins_s, ins_xy = np.zeros(0), np.zeros((0, 2))
    if len(hit):
        xy, k = shapely.get_coordinates(shapely.intersection(segs[hit], boundary), return_index=True)
        i = hit[k]
        d = b[i] - a[i]
        t = np.clip(np.einsum("ij,ij->i", xy - a[i], d) / np.maximum(np.einsum("ij,ij->i", d, d), 1e-300), 0, 1)
        eps = 1e-9
        vcut[i[t <= eps]] = True
        vcut[i[t >= 1 - eps] + 1] = True
        mid = (t > eps) & (t < 1 - eps)
        ins_s, first = np.unique(i[mid] + t[mid], return_index=True)
        ins_xy = (a[i] + d * t[:, None])[mid][first]
    S = np.r_[np.arange(n, dtype=float), ins_s]
    order = np.argsort(S, kind="stable")
    Q = np.vstack([p, ins_xy])[order]
    cut = np.r_[vcut, np.ones(len(ins_s), bool)][order]
    cut[0] = cut[-1] = True
    ends = np.flatnonzero(cut)
    runs = [Q[e0:e1 + 1] for e0, e1 in zip(ends[:-1], ends[1:])]
    probe = []
    for r in runs:                                     # the midpoint of a run's longest segment is off the boundary
        j = int(np.argmax(np.linalg.norm(np.diff(r, axis=0), axis=1)))
        probe.append((r[j] + r[j + 1]) / 2)
    cls = classify(np.asarray(probe))
    out = []
    for r, c in zip(runs, cls):
        if out and out[-1][1] == int(c):
            out[-1] = (np.vstack([out[-1][0], r[1:]]), int(c))
        else:
            out.append((r, int(c)))
    return out


def split_by_covers(lines, polys, min_stub: float, modes):
    """Cut polylines by the cover polygons → [(line index, piece, tinted)].
    `cut` covers remove what is under them; `tint` covers keep it, flagged
    tinted (re-inked). A piece shortened by the cut and left under
    min_stub mm is dropped."""
    import shapely  # noqa: PLC0415
    from shapely.geometry import LineString, Polygon  # noqa: PLC0415
    from shapely.ops import unary_union  # noqa: PLC0415
    if not polys:
        return [(i, l, False) for i, l in enumerate(lines)]
    modes = [modes] * len(polys) if isinstance(modes, str) else list(modes)
    U = unary_union([Polygon(p) for p in polys])
    tints = [Polygon(p) for p, m in zip(polys, modes) if m == "tint"]
    UT = unary_union(tints) if tints else None
    edge = U.boundary if UT is None else shapely.union_all([U.boundary, UT.boundary])

    def classify(xy):                                  # 0 outside every cover, 1 under a cut, 2 under a tint
        c = shapely.intersects_xy(U, xy[:, 0], xy[:, 1]).astype(int)
        if UT is not None:
            c[shapely.intersects_xy(UT, xy[:, 0], xy[:, 1])] = 2
        return c

    out = []
    for li, l in enumerate(lines):
        if len(l) < 2:
            continue
        L0 = float(arclen(l)[-1])
        if not LineString(l).intersects(U):
            out.append((li, l, False))
            continue
        runs = boundary_runs(l, edge, classify)
        for q, c in runs:
            Lq = float(arclen(q)[-1])
            if c == 0 and (Lq >= min_stub or Lq >= L0 - 1e-6):
                out.append((li, q, False))
        for q, c in runs:
            if c == 2 and float(arclen(q)[-1]) >= min_stub:
                out.append((li, q, True))
    return out


# ---------------------------------------------------------------------------
# the found river: a far view (GRWL centrelines)
# ---------------------------------------------------------------------------

STEM_TILES = ("SB18", "SB19", "SB20", "SC18", "SC20")


@lru_cache(maxsize=8)
def _stems(tile: str) -> tuple:
    """Single-channel main stems of a GRWL tile (median width 150–700 m,
    nchannels ≤ 1, lakes dropped), resampled at w/4 and smoothed at 1.5 w,
    longest first — hands_rivers.stems, here so the kit needs no experiment."""
    import warnings  # noqa: PLC0415

    from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415

    from ._research import earth_lines as el  # noqa: PLC0415
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, tab = el.load_grwl(tile)
    w, nc, lk = tab["width_m"], tab["nchannels"], tab["lakeFlag"]
    idx = np.flatnonzero(~(lk > 0))
    seg = tab["segmentID"][idx]
    order = np.lexsort((tab["segmentInd"][idx], seg))
    idx, seg = idx[order], seg[order]
    cuts = np.flatnonzero(np.diff(seg)) + 1
    lon0, lat0 = float(np.median(tab["lon"])), float(np.median(tab["lat"]))
    out = []
    for g in np.split(np.arange(len(idx)), cuts):
        ii = idx[g]
        wm = float(np.nanmedian(w[ii]))
        if not (150.0 <= wm <= 700.0) or float(np.nanmedian(nc[ii])) > 1:
            continue
        Pm = el.lonlat_to_m(tab["lon"][ii], tab["lat"][ii], lon0, lat0)
        gaps = np.flatnonzero(np.linalg.norm(np.diff(Pm, axis=0), axis=1) > 100.0) + 1
        for a, b in zip(np.r_[0, gaps], np.r_[gaps, len(Pm)]):
            p = Pm[a:b]
            if len(p) < 20:
                continue
            q = resample(p, wm / 4)
            if len(q) < 240:
                continue
            q = gaussian_filter1d(q, 6.0, axis=0, mode="nearest")
            out.append((int(seg[g[0]]), wm, q))
    out.sort(key=lambda t: (-len(t[2]), t[0]))
    return tuple(out)


FAR_STEMS = "grwl_far_sb19"          # library river_stems entry (experiments/keeps13_river_stems.py)


@L.loader("river_stems")
def _load_river_stems(entry: dict, folder: Path) -> dict:
    """{"n": {tile: stem count}, "stems": {(tile, rank): (segment, channel width m, points)}}."""
    z = L.read_npz(folder / entry["files"]["stems"])
    meta = entry["stems"]
    return {"n": {t: int(k) for t, k in meta["n_stems"].items()},
            "stems": {(s["tile"], int(s["rank"])): (int(s["segment"]), float(s["channel_w_m"]), z[s["array"]])
                      for s in meta["frozen"]}}


def stem(ctx, stems, tile: str, rank: int) -> tuple:
    """(segment, channel width m, points) of stem `rank` of `tile` (clamped to
    the tile's stem count, as `_stems` indexing does): from the frozen library
    entry when it holds it, else from the local GRWL corpus."""
    if stems is not None:
        fz = ctx.use("river_stems", stems)
        n = fz["n"].get(tile)
        if n is not None and (tile, min(rank, n - 1)) in fz["stems"]:
            return fz["stems"][(tile, min(rank, n - 1))]
    try:
        st = _stems(tile)
    except ImportError as e:                       # the app freezes the entry, never the corpus reader
        raise ValueError(f"oehlen_found_river: stem {tile}#{rank} is not frozen in river_stems/{stems}") from e
    return st[min(rank, len(st) - 1)]


@voice("oehlen_found_river", params=[
    P("tile", "choice", "SB19", "GRWL tile (Amazon main stems)", choices=STEM_TILES),
    P("rank", "int", 0, "which stem, longest first", min=0, max=20),
    P("start", "float", 0.0, "where the stretch starts along the stem (share)", min=0.0, max=0.95),
    P("span_w", "int", 1600, "stretch length in channel widths (far view: ≥ 1000 reads as a tight zigzag band)",
      min=100, max=4000),
    P("angle", "float", 0.0, "turn the stretch, degrees from horizontal (its principal axis), before fitting", min=-180.0, max=180.0),
    P("stems", "ref", FAR_STEMS, "frozen far-view stems (library kind river_stems); a tile/rank it does not hold, "
      "or null, reads the local GRWL corpus (research only)", kind="river_stems", optional=True),
], doc="found river: a far view of a real meandering stem, a tight zigzag band (Ian 2026-10-17: far views only)")
def oehlen_found_river(ctx, *, tile, rank, start, span_w, angle, stems):
    seg, wm, q = stem(ctx, stems, tile, rank)
    n = min(4 * span_w, len(q))
    a = int(start * max(len(q) - n, 0))
    p = q[a:a + n]
    c = p.mean(axis=0)
    ev = np.linalg.eigh(np.cov((p - c).T))[1][:, -1]          # principal axis → horizontal, then `angle`
    p = rotate(p, c, angle - math.degrees(math.atan2(ev[1], ev[0])))
    return fitted([p], ctx.box, metas=[{"found": f"grwl:{tile}:seg{seg}@{a}+{n}", "channel_w_m": wm,
                                        "rights": "GRWL V01.01, Allen & Pavelsky 2018, CC BY 4.0"}])


# ---------------------------------------------------------------------------
# the arranger
# ---------------------------------------------------------------------------

def frac_boxes(v, frame, k):
    v = list(v or [])
    out = []
    for i in range(0, len(v) - k + 1, k):
        out.append(v[i:i + k])
    return out


def clip_rect(lines, rect_poly, min_stub):
    """The pieces of each polyline inside the polygon, cut only at its edge (see `boundary_runs`); a
    piece the edge shortened below min_stub mm is dropped."""
    import shapely  # noqa: PLC0415
    from shapely.geometry import Polygon  # noqa: PLC0415
    R = Polygon(rect_poly)

    def inside(xy):
        return shapely.intersects_xy(R, xy[:, 0], xy[:, 1]).astype(int)

    out = []
    for l in lines:
        if len(l) < 2:
            continue
        L0 = float(arclen(l)[-1])
        for q, c in boundary_runs(l, R.boundary, inside):
            Lq = float(arclen(q)[-1])
            if c and (Lq >= min_stub or Lq >= L0 - 1e-6):
                out.append(q)
    return out


def rect_polygon(cx, cy, w, h, ang):
    q = np.array([[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2], [-w / 2, -h / 2]])
    return rotate(q + [cx, cy], np.array([cx, cy]), ang)


def make_mark(points, role, ink, pen, part, extra_meta=None, neg=None):
    ch = {} if neg is None else {"neg": neg}
    md = {"part": part, "of_role": role, "ink": ink, "pen": pen, **(extra_meta or {})}
    return Mark(points, ch, md)


# The helpers above are public (2026-10-18): `rules`, `contagion` and the Gesture
# Studies build on them, so their names and signatures are a contract. The old
# private names stay as aliases for the round-12/13 experiments and tests.
_arclen, _rot, _bridge, _ride = arclen, rotate, bridge, ride_along
_split, _frac_boxes, _clip_rect, _rect, _mk = split_by_covers, frac_boxes, clip_rect, rect_polygon, make_mark


@arranger("oehlen_found", params=[
    P("found", "int", 1, "the first n parts are found layers", min=0, max=6),
    P("late", "int", 1, "the last n parts are drawn after the covers", min=0, max=6),
    P("roles", "str", "", "explicit role per part, comma list of found / made / late (overrides found + late; "
      "lets a part keep its index, and so its seed, when others are added)"),
    P("found_boxes", "floats", [0.5, 0.5, 0.9, 0.9, 0.0],
      "per found part: cx, cy, w, h (shares of the frame) and angle (deg) of its pasted rectangle"),
    P("found_on", "choice", "all", "which found parts are pasted: all | first | second (only that one; the "
      "others are left out, and every part keeps its index, seed and pasted box)",
      choices=("all", "first", "second")),
    P("crop", "float", 1.0, "found content is grown to fill its rectangle ÷ crop, then cut to the rectangle "
      "(< 1 keeps a margin, > 1 cuts through the content)", min=0.6, max=2.5),
    P("made_box", "floats", [], "made parts' box: cx, cy, w, h shares (empty = the sheet box)"),
    P("late_box", "floats", [], "late parts' box: cx, cy, w, h shares (empty = the sheet box)"),
    P("step", "float", 0.4, "resampling step, mm", min=0.1, max=2.0),
    P("capture", "float", 3.0, "listening: a found contour this near (mm) and aligned can take the line",
      min=0.2, max=30.0),
    P("align", "float", 0.75, "|cos| between headings needed to ride (1 = only parallel)", min=0.0, max=1.0),
    P("ride", "float", 22.0, "mean ride along a found contour, mm", min=1.0, max=300.0),
    P("ride_sd", "float", 0.6, "log-normal spread of ride and window lengths", min=0.0, max=1.5),
    P("min_ride", "float", 5.0, "shorter rides are refused, mm", min=0.5, max=100.0),
    P("listen", "float", 40.0, "mean listening window, mm of made line", min=1.0, max=500.0),
    P("ignore", "float", 70.0, "mean ignoring window, mm of made line", min=0.0, max=1000.0),
    P("return_mm", "float", 35.0, "after a ride, the line swims back to its own path over this many mm",
      min=1.0, max=400.0),
    P("ramp", "float", 2.5, "tangent bridge at each enter/leave, mm (0 = a kink)", min=0.0, max=20.0),
    P("grow", "bool", True, "made lines start ON a found contour (the Krebber move)"),
    P("grow_reach", "float", 40.0, "grow: the made line may be moved this far (mm) to start at a found contour's end",
      min=1.0, max=300.0),
    P("max_rides", "int", 6, "most rides per made line", min=0, max=60),
    P("ride_gap", "float", 0.0, "while riding, trace this far beside the found contour (0 = on it), mm",
      min=0.0, max=5.0),
    P("max_offset", "float", 18.0, "a ride ends before it carries the line further than this from its own path, mm",
      min=1.0, max=300.0),
    P("covers", "int", 2, "cover shapes", min=0, max=4),
    P("cover_mode", "choice", "cut", "cut: lines beneath stop at the cover | tint: re-inked in tint_ink inside",
      choices=("cut", "tint")),
    P("cover_shape", "choice", "torn", "cut quadrilateral | torn (one edge torn) | sheet (rounded)",
      choices=("cut", "torn", "sheet")),
    P("cover_boxes", "floats", [], "explicit covers (composed, not searched): per cover cx, cy, w, h (shares of "
      "the frame), angle (deg), shape (0 cut, 1–4 torn top/right/bottom/left edge, 5 sheet), mode (0 cut, "
      "1 tint); empty = search"),
    P("cover_use", "choice", "all", "explicit covers: all (as composed) | cut / tint (only the covers of that "
      "mode) | none | all-cut / all-tint (every cover, in that mode)",
      choices=("all", "cut", "tint", "none", "all-cut", "all-tint")),
    P("cover_w", "floats", [0.28, 0.42], "cover size range, share of the frame's short side"),
    P("cover_aspect", "floats", [0.5, 1.6], "cover w/h range"),
    P("cover_tilt", "float", 14.0, "cover tilt range ±deg", min=0.0, max=90.0),
    P("cover_margin", "float", 12.0, "covers keep this far inside the sheet, mm", min=0.0, max=80.0),
    P("cover_cuts", "choice", "all", "which layers a cover cuts: all | found | made", choices=("all", "found", "made")),
    P("cover_edge", "choice", "none", "none (the edge shows only through what stops) | drawn (in the found pen)",
      choices=("none", "drawn")),
    P("late_borrow", "choice", "edges", "what late lines may ride: none | edges (the covers' edges) | all (edges + "
      "what is left of the found layer)", choices=("none", "edges", "all")),
    P("late_grow", "bool", False, "late lines also grow out of a found contour's end"),
    P("grow_flip", "bool", True, "grow may start the line from its other end (a plotted line has no direction)"),
    P("late_capture", "float", 6.0, "late lines: capture distance, mm", min=0.2, max=30.0),
    P("min_stub", "float", 4.0, "a cut piece shorter than this (mm) is dropped", min=0.0, max=50.0),
    P("found_ink", "str", "blue", "Flexoki pen for the found layer"),
    P("found_pen", "float", 0.3, "found pen, mm", min=0.05, max=3.0),
    P("made_ink", "str", "black", "Flexoki pen for the made lines"),
    P("made_pen", "float", 0.4, "made pen, mm", min=0.05, max=3.0),
    P("late_ink", "str", "black", "Flexoki pen for the late lines"),
    P("late_pen", "float", 0.7, "late pen, mm", min=0.05, max=3.0),
    P("tint_ink", "str", "green", "tint: the made lines' pen inside a tint cover"),
    P("tint_found_ink", "str", "green-400", "tint: the found layer's pen inside a tint cover"),
    P("edge_pen", "float", 0.25, "drawn cover edge pen, mm", min=0.05, max=3.0),
], doc="D1 + D2 after Oehlen's works on paper: found layers pasted and cut, made lines that grow from / ride / "
        "ignore them, cover cuts, a late line across the covers")
def oehlen_found(ctx, parts, *, found, late, roles, found_on, found_boxes, crop, made_box, late_box, step, capture, align, ride,
                 ride_sd, min_ride, listen, ignore, return_mm, ramp, grow, grow_reach, max_rides, ride_gap, max_offset, covers, cover_boxes,
                 cover_mode, cover_shape, cover_use, cover_w, cover_aspect, cover_tilt, cover_margin, cover_cuts, cover_edge,
                 late_borrow, late_grow, grow_flip, late_capture, min_stub, found_ink, found_pen, made_ink, made_pen, late_ink, late_pen, tint_ink, tint_found_ink,
                 edge_pen):
    for nm in (found_ink, made_ink, late_ink, tint_ink, tint_found_ink):
        if nm not in FLEXOKI:
            raise ValueError(f"oehlen_found: unknown ink {nm!r}; choose from {sorted(FLEXOKI)}")
    W, H = ctx.frame
    n = len(parts)
    found = min(found, n)
    late = min(late, n - found)
    f_parts, m_parts, l_parts = parts[:found], parts[found:n - late], parts[n - late:]
    if roles.strip():
        rl = [x.strip() for x in roles.split(",")]
        if len(rl) != n or any(x not in ("found", "made", "late") for x in rl):
            raise ValueError(f"oehlen_found: roles needs one of found/made/late per part ({n}), got {roles!r}")
        f_parts = [p for p, x in zip(parts, rl) if x == "found"]
        m_parts = [p for p, x in zip(parts, rl) if x == "made"]
        l_parts = [p for p, x in zip(parts, rl) if x == "late"]
    boxes = frac_boxes(found_boxes, ctx.frame, 5)
    out: list[Mark] = []
    meta_log = {"rides": [], "covers": []}

    # 1. found layers, pasted and cut to their rectangles
    found_lines = []        # (part index, points, mark meta)
    for k, p in enumerate(f_parts):
        if found_on != "all" and k != ("first", "second").index(found_on):
            continue                                # left out: its index (seed, box) stays reserved
        cx, cy, bw, bh, ang = boxes[min(k, len(boxes) - 1)] if boxes else (0.5, 0.5, 0.9, 0.9, 0.0)
        cx, cy, bw, bh = cx * W, cy * H, bw * W, bh * H
        inner =(cx - (bw * crop) / 2, cy - (bh * crop) / 2, bw * crop, bh * crop)
        ms = p.run(inner)
        rect = rect_polygon(cx, cy, bw, bh, ang)
        for m in ms:
            q = rotate(m.points, np.array([cx, cy]), ang)
            for piece in clip_rect([q], rect, min_stub):
                found_lines.append((p.index, piece, {kk: m.meta[kk] for kk in ("plate_role", "measure_role", "found")
                                                     if kk in m.meta}))

    def sub_box(v):
        if not v or len(v) < 4:
            return ctx.box
        cx, cy, bw, bh = v[:4]
        return (cx * W - bw * W / 2, cy * H - bh * H / 2, bw * W, bh * H)

    # 2. made lines negotiate the found layer
    # text (plate labels, index numbers) is printed matter but not a contour: the line never rides it
    G_found = Ground([l for _, l, md in found_lines
                      if md.get("plate_role") != "label" and md.get("measure_role") != "index"], step, tag=1)
    made_lines = []
    for p in m_parts:
        ms = p.run(sub_box(made_box))
        rng = ctx.rng("made", p.index)
        for mi, m in enumerate(ms):
            if found_lines:
                pts, tags, log = negotiate(m.points, [G_found], rng, step=step, capture=capture, align=align,
                                           ride=ride, ride_sd=ride_sd, min_ride=min_ride, listen=listen,
                                           ignore=ignore, return_mm=return_mm, ramp=ramp, grow=grow,
                                           grow_reach=grow_reach, max_rides=max_rides, max_offset=max_offset, ride_gap=ride_gap, grow_flip=grow_flip,
                                           bounds=(ctx.box[0], ctx.box[1], ctx.box[0] + ctx.box[2],
                                                   ctx.box[1] + ctx.box[3]))
            else:
                pts, tags, log = resample(m.points, step), np.zeros(len(resample(m.points, step))), []
            meta_log["rides"].append({"part": p.index, "mark": mi, "rides": log})
            made_lines.append((p.index, pts, tags))

    # 3. late lines (placed now, so the covers can sit on their path)
    late_raw = []
    for p in l_parts:
        for m in p.run(sub_box(late_box)):
            late_raw.append((p.index, resample(m.points, step)))

    # 4. covers: on a late line's path, inside the margin, over as much drawing as possible
    polys, modes = [], []
    if cover_boxes:
        rng = ctx.rng("covers", "explicit")
        for k in range(0, len(cover_boxes) - 6, 7):
            cx, cy, bw, bh, ang, code, md = cover_boxes[k:k + 7]
            code = int(round(code))
            modes.append("tint" if md >= 0.5 else "cut")
            shp = "cut" if code == 0 else "sheet" if code == 5 else "torn"
            polys.append(cover_polygon(rng, (cx * W, cy * H), bw * W, bh * H, shp, 0.0,
                                       edge=(code - 1) if shp == "torn" else None, angle=ang))
            meta_log["covers"].append({"explicit": True, "polygon": np.round(polys[-1], 2).tolist()})
        if cover_use != "all":
            # every polygon was drawn first (the rng runs as composed), then the use is applied
            keep = [cover_use in ("all-cut", "all-tint") or md == cover_use for md in modes]
            polys = [q for q, k in zip(polys, keep) if k]
            meta_log["covers"] = [c for c, k in zip(meta_log["covers"], keep) if k]
            modes = [cover_use[4:] if cover_use.startswith("all-") else md for md, k in zip(modes, keep) if k]
    elif covers and late_raw:
        from shapely.geometry import LineString, Polygon  # noqa: PLC0415
        rng = ctx.rng("covers")
        content = [l for _, l, _ in found_lines] + [l for _, l, _ in made_lines]
        content_g = [LineString(l) for l in content if len(l) >= 2]
        late_pts = np.vstack([l for _, l in late_raw])
        short = min(W, H)
        for c in range(covers):
            best = None
            for _ in range(160):
                cw = short * rng.uniform(*sorted(cover_w[:2] or [0.3, 0.4]))
                asp = rng.uniform(*sorted(cover_aspect[:2] or [0.6, 1.5]))
                w_, h_ = cw, cw / asp
                ctr = late_pts[rng.integers(len(late_pts))] + rng.normal(0, 0.15, 2) * [w_, h_]
                poly = cover_polygon(rng, ctr, w_, h_, cover_shape, cover_tilt)
                lo, hi = poly.min(axis=0), poly.max(axis=0)
                if lo[0] < cover_margin or lo[1] < cover_margin or hi[0] > W - cover_margin or hi[1] > H - cover_margin:
                    continue
                Pg = Polygon(poly)
                if any(Pg.intersects(Polygon(q)) for q in polys):
                    continue
                inside = sum(g.intersection(Pg).length for g in content_g)
                crossed = sum(LineString(l).intersection(Pg).length for _, l in late_raw)
                if crossed < 0.5 * min(w_, h_):
                    continue
                # legible covers: many lines stop at the edge (terminations), not "most ink swallowed"
                edge = Pg.exterior
                cuts_n = 0
                for g in content_g:
                    x = g.intersection(edge)
                    cuts_n += 0 if x.is_empty else len(getattr(x, "geoms", [x]))
                score = cuts_n - 0.004 * inside
                if best is None or score > best[0]:
                    best = (score, poly, inside, crossed)
            if best is not None:
                polys.append(best[1])
                modes.append(cover_mode)
                meta_log["covers"].append({"inside_mm": round(best[2], 1), "late_crossing_mm": round(best[3], 1),
                                           "polygon": np.round(best[1], 2).tolist()})

    # 5. cut what is beneath
    def emit(lines_tagged, role, ink, pen, cuts):
        for pi, l, extra in lines_tagged:
            if cuts and polys:
                for _, q, inside in split_by_covers([l], polys, min_stub, modes):
                    out.append(make_mark(q, role, tint_found_ink if inside else ink, pen, pi,
                                   {**extra, "under_cover": bool(inside)}))
            else:
                out.append(make_mark(l, role, ink, pen, pi, extra))

    def is_text(md):
        return md.get("plate_role") == "label" or md.get("measure_role") == "index"

    text = [t for t in found_lines if is_text(t[2])]
    emit([t for t in found_lines if not is_text(t[2])], "found", found_ink, found_pen,
         cover_cuts in ("all", "found"))
    # printed text is cut whole, never into stray glyph fragments: strokes within 1.2 mm form one word;
    # a word touching a cut cover goes, a word whose centre is under a tint cover is tinted
    if text and polys and cover_cuts in ("all", "found"):
        from shapely.geometry import LineString, Point, Polygon  # noqa: PLC0415
        boxes = [(l.min(axis=0) - 0.6, l.max(axis=0) + 0.6) for _, l, _ in text]
        parent = list(range(len(text)))

        def root(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for a in range(len(text)):
            for b in range(a + 1, len(text)):
                if np.all(boxes[a][0] <= boxes[b][1]) and np.all(boxes[b][0] <= boxes[a][1]):
                    parent[root(a)] = root(b)
        groups: dict[int, list[int]] = {}
        for a in range(len(text)):
            groups.setdefault(root(a), []).append(a)
        cutP = [Polygon(q) for q, md in zip(polys, modes) if md == "cut"]
        tintP = [Polygon(q) for q, md in zip(polys, modes) if md == "tint"]
        for g in sorted(groups.values()):
            geoms = [LineString(text[a][1]) for a in g if len(text[a][1]) >= 2]
            if any(G.intersects(P) for G in geoms for P in cutP):
                continue
            c = np.vstack([text[a][1] for a in g]).mean(axis=0)
            tinted = any(P.contains(Point(c)) for P in tintP)
            for a in g:
                pi, l, extra = text[a]
                out.append(make_mark(l, "found", tint_found_ink if tinted else found_ink, found_pen, pi,
                               {**extra, "under_cover": tinted}))
    else:
        emit(text, "found", found_ink, found_pen, False)
    for pi, l, tags in made_lines:
        if cover_cuts in ("all", "made") and polys:
            from scipy.spatial import cKDTree  # noqa: PLC0415
            tree = cKDTree(l)
            for _, q, inside in split_by_covers([l], polys, min_stub, modes):
                q = resample(q, step)
                neg = tags[tree.query(q)[1]]
                out.append(make_mark(q, "made", tint_ink if inside else made_ink, made_pen, pi,
                               {"under_cover": bool(inside)}, neg=neg))
        else:
            out.append(make_mark(l, "made", made_ink, made_pen, pi, None, neg=tags))

    # 6. late lines: drawn over everything; may ride the covers' edges
    grounds = []
    if late_borrow == "all":
        grounds.append(Ground([m.points for m in out if m.meta.get("of_role") == "found"
                               and m.meta.get("plate_role") != "label" and m.meta.get("measure_role") != "index"],
                              step, tag=1))
    if late_borrow in ("edges", "all") and polys:
        grounds.append(Ground([resample(p, step) for p in polys], step, tag=2))
    for pi, l in late_raw:
        rng = ctx.rng("late", pi)
        if grounds:
            pts, tags, log = negotiate(l, grounds, rng, step=step, capture=late_capture, align=align, ride=ride,
                                       ride_sd=ride_sd, min_ride=min_ride, listen=listen, ignore=ignore,
                                       return_mm=return_mm, ramp=ramp, grow=late_grow, grow_reach=grow_reach,
                                       max_rides=max_rides, max_offset=max_offset, ride_gap=ride_gap,
                                       grow_flip=grow_flip, bounds=(ctx.box[0], ctx.box[1], ctx.box[0] + ctx.box[2],
                                               ctx.box[1] + ctx.box[3]))
            meta_log["rides"].append({"part": pi, "late": True, "rides": log})
        else:
            pts, tags = l, np.zeros(len(l))
        out.append(make_mark(pts, "late", late_ink, late_pen, pi, None, neg=tags))

    if polys:
        from shapely.geometry import LineString, Polygon  # noqa: PLC0415
        lates = [LineString(m.points) for m in out if m.meta.get("of_role") == "late" and len(m.points) >= 2]
        for c, poly, md in zip(meta_log["covers"], polys, modes):
            c["late_crossing_mm"] = round(sum(g.intersection(Polygon(poly)).length for g in lates), 1)
            c["mode"] = md
    for poly in polys:
        if cover_edge == "drawn":
            out.append(make_mark(poly, "edge", found_ink, edge_pen, parts[-1].index))
    if out:
        out[0] = out[0].evolve(meta={"oehlen_found": meta_log})
    return out


# ---------------------------------------------------------------------------
# ink + colour preview
# ---------------------------------------------------------------------------

@renderer("oehlen_found_ink", params=[
    P("pen", "float", 0.4, "pen for marks that carry none, mm", min=0.05, max=3.0),
], doc="one wire per mark at its meta['pen'], in its meta['ink'] (Ink.meta['colour'])", reach=lambda p: 0.5)
def oehlen_found_ink(ctx, marks, *, pen):
    return [Ink(m.points, closed=False, filled=False, pen=float(m.meta.get("pen", pen)),
                meta={"colour": m.meta.get("ink", "black"), "role": m.meta.get("of_role")}) for m in marks]


def _hex(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def render_colour(sheet, *, px_per_mm: float = 6.0, ss: int = 2, crop=None):
    """PIL image: inks at their pen width in their Flexoki colour, layered
    in plotting order (found first, then made, late). crop: (x0, y0, x1, y1) mm."""
    from PIL import Image, ImageDraw  # noqa: PLC0415
    W, H = sheet.frame
    x0, y0, x1, y1 = crop if crop is not None else (0.0, 0.0, W, H)
    k = px_per_mm * ss
    size = (int(round((x1 - x0) * k)), int(round((y1 - y0) * k)))
    rgb = np.ones((size[1] // ss, size[0] // ss, 3)) * np.array(PAPER, float)
    order = []
    for ink in sheet.inks:
        c = ink.meta.get("colour") or "black"
        if c not in order:
            order.append(c)
    for c in order:
        col = _hex(FLEXOKI.get(c, FLEXOKI["black"])) if c in FLEXOKI else INK
        im = Image.new("L", size, 0)
        dr = ImageDraw.Draw(im)
        for ink in sheet.inks:
            if (ink.meta.get("colour") or "black") != c or len(ink.points) < 2:
                continue
            q = (ink.points - [x0, y0]) * k
            d = max(ink.pen * k, 1.0)
            dr.line([tuple(v) for v in q], fill=255, width=max(int(round(d)), 1), joint="curve")
            r = d / 2
            for v in q[[0, -1]]:
                dr.ellipse([v[0] - r, v[1] - r, v[0] + r, v[1] + r], fill=255)
        im = im.resize((rgb.shape[1], rgb.shape[0]), Image.Resampling.BOX)
        a = np.asarray(im, float)[..., None] / 255.0
        rgb = rgb * (1 - a) + np.array(col, float) * a
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def save(sheet, path, *, px_per_mm: float = 6.0, quality: int = 90, crop=None) -> Path:
    """Colour preview + the normalized recipe beside it (<stem>.recipe.json)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    im = render_colour(sheet, px_per_mm=px_per_mm, crop=crop)
    im.save(path, quality=quality, optimize=True) if path.suffix.lower() in (".jpg", ".jpeg") else im.save(path)
    sheet.save_recipe(path.with_suffix(".recipe.json"))
    return path
