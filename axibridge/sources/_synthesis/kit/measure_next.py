# FROZEN from research commit d5ccd75: tools/gesture/gesture/kit/measure_next.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Measurement, next versions (round 11, exploration `measure_next`).

Round 10's numbered atlas pairing (`measure_pair`, chart atlas) is frozen as a
study. This file makes NEW VERSIONS beside it, developing both sides:

- specimen side: specimens cut by something other than turning (pauses /
  speed minima, hand changes, self-crossings, the loops, closest approaches
  of the line to itself); specimens normalised (principal axis, common size);
  each specimen with its own tiny κ trace; a true frieze packed by width like
  writing; the exploded layout with a length cap; specimens grouped into
  families (a taxonomy plate); a count/size histogram drawn on the plate
  (as a staircase, or as a tally made of the specimen numbers themselves).
- drawing side: a drawing of two voices (`measure_next_duet`), a drawing
  that changes hand at its specimen boundaries (`measure_next_rehand`), the
  drawing with merged-shadow beads, and the risk — a drawing redrawn FROM its
  atlas (`measure_next_rechain`: specimens re-chained in a new order, each
  rotated so its start tangent continues the chain).
- pairings: the plate drawn by a hand with some lines kept machine-straight
  (`straight`), the plate as the bigger element (`split`), a sheet of three
  (drawing | atlas | the atlas re-chained, numbered on both drawings).
- index numbers that avoid each other and the line (`avoid`).

Modules: modulator `measure_next` (the pair, v2), modulator
`measure_next_rechain`, modulator `measure_next_rehand`, voice
`measure_next_duet`. Rendering: round 10's `measure_wire` (role "chart" /
"index" at chart_pen; drawing / rechain / shadow at pen).
"""
from __future__ import annotations

import bisect
import math
from dataclasses import replace

import numpy as np
from scipy.ndimage import gaussian_filter1d

from . import measure_pairs as mp
from . import voices_machine_diagram as vd
from .core import Mark, P, channel_kind, fitted, modulator, refit, voice

CUTS = ("turning", "inflection", "pause", "hand", "crossing", "loops", "approach")
NORMS = ("chord", "axis", "size", "axis+size")
PLATES = ("grid", "frieze", "exploded", "taxonomy")
PAGES = ("diptych", "margin", "triptych")
RECHAIN = ("time", "turning", "length", "sign", "match", "reverse", "family", "shuffle")
STRAIGHT = {"rules+labels": {"rule", "label"}, "labels": {"label"},
            "rules+labels+specimens": {"rule", "label", "specimen"}, "none": set()}

channel_kind("mn_specimen", "nearest")


# ---------------------------------------------------------------------------
# measurement + channels aligned to it
# ---------------------------------------------------------------------------

def _live(marks):
    return [m for m in marks if len(m) >= 3 and m.length() > 0]


def measure_plus(marks) -> dict:
    """vd.measure + the dance's own speed (if every mark carries it) + every
    channel resampled on the same samples (M["ch"][name])."""
    live = _live(marks)
    M = vd.measure(live)
    if M["L"] <= 0:
        return M
    common = sorted(set.intersection(*(set(m.channels) for m in live)))
    ch = {c: [] for c in common}
    for m in live:
        q = m.resampled(M["h"])
        for c in common:
            ch[c].append(q.channels[c])
    M["ch"] = {c: np.concatenate(v) for c, v in ch.items()}
    if "dance_speed" in M["ch"] and len(M["ch"]["dance_speed"]) == len(M["s"]):
        M["speed"] = M["ch"]["dance_speed"]
    return M


# ---------------------------------------------------------------------------
# specimen cuts
# ---------------------------------------------------------------------------

def _sigma(grain: float) -> float:
    return max(6.0 * grain / 0.012, 1.0)


def _spec(M: dict, a: int, b: int, kind: str) -> dict:
    turn = float(np.sum(M["kappa"][a:b]) * M["h"])
    vals, cnt = np.unique(M["voice"][a:b].astype(int), return_counts=True)
    return {"a": int(a), "b": int(b), "p": M["p"][a:b], "turn": turn, "s0": float(M["s"][a]),
            "s1": float(M["s"][b - 1]), "s_mid": float(M["s"][(a + b) // 2]),
            "length": float(M["s"][b - 1] - M["s"][a]), "voice": int(vals[np.argmax(cnt)]), "cut": kind}


def _hard(M: dict) -> list[int]:
    return (np.flatnonzero(np.diff(M["mark"]) != 0) + 1).tolist()


def _select(idx, score, s, sep: float) -> list[int]:
    """Greedy: best score first (ascending), keeping cuts ≥ sep apart in arc length."""
    order = np.lexsort((np.asarray(idx), np.asarray(score)))
    got: list[float] = []
    out: list[int] = []
    for o in order:
        i = int(idx[o])
        si = float(s[i])
        if all(abs(si - g) >= sep for g in got):
            got.append(si)
            out.append(i)
    return sorted(out)


def _cover(M: dict, cuts, grain: float, kind: str) -> list[dict]:
    """Specimens covering the whole line: cut at `cuts` (sample indices) and
    at mark ends; a cut closer than grain·L to the last one or to the next
    mark end is skipped, so nothing is dropped."""
    N, s = len(M["s"]), M["s"]
    minlen = grain * M["L"]
    hard = _hard(M)
    hs = set(hard)
    allc = sorted(set(int(c) for c in cuts if 0 < c < N) | hs)
    edges = [0]
    for c in allc:
        if c <= edges[-1]:
            continue
        if c in hs:
            edges.append(c)
            continue
        j = bisect.bisect_right(hard, c)
        nxt = hard[j] if j < len(hard) else N
        if s[c] - s[edges[-1]] >= minlen and s[nxt - 1] - s[c] >= minlen:
            edges.append(c)
    edges.append(N)
    return [_spec(M, a, b, kind) for a, b in zip(edges[:-1], edges[1:]) if b - a >= 4]


def self_crossings(M: dict) -> list[tuple[int, int]]:
    """(i, j), i < j: segment i crosses segment j (same or different marks), deduplicated."""
    import shapely  # noqa: PLC0415
    p, mk = M["p"], M["mark"]
    if len(p) < 4:
        return []
    ok = np.flatnonzero(mk[:-1] == mk[1:])
    segs = shapely.linestrings(np.stack([p[ok], p[ok + 1]], axis=1))
    tree = shapely.STRtree(segs)
    a, b = tree.query(segs, predicate="intersects")
    i, j = ok[a], ok[b]
    keep = j > i + 2
    pairs = sorted(zip(i[keep].tolist(), j[keep].tolist()))
    out: list[tuple[int, int]] = []
    for i_, j_ in pairs:
        if out and abs(i_ - out[-1][0]) <= 2 and abs(j_ - out[-1][1]) <= 2:
            continue
        out.append((int(i_), int(j_)))
    return out


def closest_approaches(M: dict, grain: float) -> list[tuple[int, int, float]]:
    """(i, j, d): places where the line comes closest to another stretch of
    itself without crossing (local minima of the distance to the nearest
    sample ≥ 50 samples away along the line, or on another mark)."""
    from scipy.spatial import cKDTree  # noqa: PLC0415
    p, s, mk, h = M["p"], M["s"], M["mark"], M["h"]
    n = len(p)
    if n < 20:
        return []
    k = min(n, 96)
    d, nb = cKDTree(p).query(p, k=k)
    far = (np.abs(s[nb] - s[:, None]) > 50 * h) | (mk[nb] != mk[:, None])
    dd = np.where(far, d, np.inf)
    jj = np.argmin(dd, axis=1)
    dmin = dd[np.arange(n), jj]
    part = nb[np.arange(n), jj]
    fin = np.isfinite(dmin)
    if not fin.any():
        return []
    thr = min(float(np.percentile(dmin[fin], 25)), 0.04 * M["R"])
    cand = [i for i in range(1, n - 1) if fin[i] and 0.25 < dmin[i] <= thr
            and dmin[i] <= dmin[i - 1] and dmin[i] <= dmin[i + 1]]
    if not cand:
        return []
    sel = _select(np.array(cand), dmin[cand], s, 2.0 * grain * M["L"])
    return [(int(i), int(part[i]), float(dmin[i])) for i in sel]


def cut_specimens(M: dict, cut: str, grain: float = 0.012, loop_max: float = 0.25) -> list[dict]:
    """The measured line cut into specimens (time order).

    turning     round 10 exactly (`measure_pairs.specimens`: inflections, short bits dropped)
    inflection  inflections, covering the whole line (short bits merged)
    pause       speed minima: the dance's own speed, else the 2/3 power law (= turn apexes)
    hand        where the speaking hand changes
    crossing    where the line crosses itself
    loops       the loops themselves (crossing to crossing, shortest first, non-overlapping)
    approach    where the line comes closest to itself without crossing (both places cut)"""
    if M.get("L", 0) <= 0:
        return []
    s, L, sig = M["s"], M["L"], _sigma(grain)
    if cut == "turning":
        return [{**t, "cut": cut} for t in mp.specimens(M, min_frac=grain, sigma=sig)]
    if cut == "inflection":
        k = gaussian_filter1d(M["kappa"], sig, mode="nearest")
        return _cover(M, np.flatnonzero(np.diff(np.sign(k)) != 0) + 1, grain, cut)
    if cut == "pause":
        v = M.get("speed")
        if v is None:
            v = (np.abs(gaussian_filter1d(M["kappa"], sig, mode="nearest")) * M["R"] + 0.5) ** (-1.0 / 3.0)
        v = gaussian_filter1d(np.asarray(v, float), sig, mode="nearest")
        mins = np.flatnonzero((v[1:-1] < v[:-2]) & (v[1:-1] <= v[2:])) + 1
        sel = _select(mins, v[mins], s, grain * L) if len(mins) else []
        return _cover(M, sel, grain, cut)
    if cut == "hand":
        return _cover(M, np.flatnonzero(np.diff(M["voice"]) != 0) + 1, grain, cut)
    if cut == "crossing":
        cs = [c for ij in self_crossings(M) for c in (ij[0] + 1, ij[1] + 1)]
        return _cover(M, cs, grain, cut)
    if cut == "loops":
        cand = []
        for i, j in self_crossings(M):
            if M["mark"][i] != M["mark"][j]:
                continue
            ln = s[j] - s[i]
            if 1.5 * grain * L <= ln <= loop_max * L:
                cand.append((ln, i, j))
        cand.sort()
        taken: list[tuple[int, int]] = []
        for _, i, j in cand:
            if all(j + 1 < a or i > b for a, b in taken):
                taken.append((i, j + 1))
        return sorted((_spec(M, a, b + 1, cut) for a, b in taken), key=lambda t: t["s0"])
    if cut == "approach":
        cs = [c for i, j, _ in closest_approaches(M, grain) for c in (i, j)]
        return _cover(M, cs, grain, cut)
    raise ValueError(f"unknown cut {cut!r}")


# ---------------------------------------------------------------------------
# normalisation + families
# ---------------------------------------------------------------------------

def _rot(q: np.ndarray, a: float) -> np.ndarray:
    c, s_ = math.cos(a), math.sin(a)
    return q @ np.array([[c, s_], [-s_, c]])


def norm_geom(p: np.ndarray, norm: str) -> np.ndarray:
    """chord: chord level, start at the origin (round 10); axis: principal axis
    level, centred (start left of end); size: scaled to a common extent of 1."""
    p = np.asarray(p, float)
    if norm in ("chord", "size"):
        q = mp._chord_frame(p)
    else:
        q = p - p.mean(axis=0)
        w, V = np.linalg.eigh(np.cov(q.T) + 1e-12 * np.eye(2))
        v = V[:, int(np.argmax(w))]
        q = _rot(q, -math.atan2(v[1], v[0]))
        if q[-1, 0] < q[0, 0]:
            q = -q
    if "size" in norm:
        q = q / max(float(np.ptp(q, axis=0).max()), 1e-9)
    return q


def _turning_fn(p: np.ndarray, n: int = 16) -> np.ndarray:
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    t = np.linspace(0, s[-1], n + 1)
    q = np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])
    th = np.unwrap(np.arctan2(np.diff(q[:, 1]), np.diff(q[:, 0])))
    return th - th[0]


def families(sp: list[dict], k: int) -> list[int]:
    """Family index per specimen (0 = calmest family): Ward clustering of the
    turning function θ(u)−θ(0), relative length and straightness."""
    if len(sp) <= 1:
        return [0] * len(sp)
    from scipy.cluster.hierarchy import fcluster, linkage  # noqa: PLC0415
    med = float(np.median([t["length"] for t in sp])) or 1.0
    F = []
    for t in sp:
        p = t["p"]
        chord = float(np.linalg.norm(p[-1] - p[0]))
        F.append(np.r_[_turning_fn(p) / math.pi, 0.6 * math.log(max(t["length"], 1e-6) / med),
                       1.5 * chord / max(t["length"], 1e-9)])
    lab = fcluster(linkage(np.array(F), "ward"), min(k, len(sp)), "maxclust")
    groups = sorted(set(lab.tolist()))
    mean_turn = {g: float(np.mean([abs(sp[i]["turn"]) for i in range(len(sp)) if lab[i] == g])) for g in groups}
    rank = {g: r for r, g in enumerate(sorted(groups, key=lambda g: (mean_turn[g], g)))}
    return [rank[int(g)] for g in lab]


_families = families


# ---------------------------------------------------------------------------
# plates: lists of (polyline, role); role in specimen / trace / rule / label / hist
# ---------------------------------------------------------------------------

def _text(s, x, y, h, anchor="centre"):
    return [(p, "label") for p in vd.text(s, x, y, h, anchor=anchor)]


def _trace(k: np.ndarray, x0: float, x1: float, yc: float, amp: float, kref: float) -> list:
    """A specimen's own κ(s) as a tiny seismograph on a baseline (square-root
    compressed, so the quiet turning shows beside the spikes)."""
    k = gaussian_filter1d(np.asarray(k, float), 1.5, mode="nearest") if len(k) > 4 else np.asarray(k, float)
    if len(k) > 120:
        k = np.interp(np.linspace(0, len(k) - 1, 120), np.arange(len(k)), k)
    x = np.linspace(x0, x1, len(k))
    z = np.sign(k) * np.sqrt(np.clip(np.abs(k) / max(kref, 1e-12), 0, 1.6))
    y = yc - z * amp
    return [(mp._rule(x0, yc, x1, yc), "rule"), (np.column_stack([x, y]), "trace")]


def _cell(item: dict, cx0: float, cy0: float, cw: float, ch: float, sc: float, *, trace: bool, kref: float,
          label_h: float) -> list:
    q = item["q"]
    out = []
    geo_h = 0.46 if trace else 0.7
    yc = 0.27 if trace else 0.40
    s_ = min(sc, 0.92 * cw / max(np.ptp(q[:, 0]), 1e-9), geo_h * ch / max(np.ptp(q[:, 1]), 1e-9))
    mid = (q.min(axis=0) + q.max(axis=0)) / 2
    out.append(((q - mid) * s_ + np.array([cx0 + cw / 2, cy0 + yc * ch]), "specimen"))
    if trace:
        out += _trace(item["k"], cx0 + 0.2 * cw, cx0 + 0.8 * cw, cy0 + 0.635 * ch, 0.065 * ch, kref)
    out += _text(item["label"], cx0 + cw / 2, cy0 + (0.80 if trace else 0.78) * ch, 0.85 * label_h)
    return out


def _grid_scale(items, cw, ch, trace):
    ext_w = max(float(np.percentile([np.ptp(it["q"][:, 0]) for it in items], 92)), 1e-9)
    ext_h = max(float(np.percentile([np.ptp(it["q"][:, 1]) for it in items], 92)), 1e-9)
    return min(0.82 * cw / ext_w, (0.5 if trace else 0.6) * ch / ext_h)


def plate_grid(items: list[dict], box, *, label_h: float, trace: bool, kref: float) -> list:
    """Round 10's grid (same cells, same scale rule), optionally a κ trace under each specimen."""
    x0, y0, w, h = box
    n = len(items)
    if not n:
        return []
    cols = max(int(round(math.sqrt(n * w / h))), 1)
    rows = -(-n // cols)
    cw, ch = w / cols, h / rows
    sc = _grid_scale(items, cw, ch, trace)
    out = []
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        out += _cell(it, x0 + c * cw, y0 + r * ch, cw, ch, sc, trace=trace, kref=kref, label_h=label_h)
    return out


def plate_frieze(items: list[dict], box, *, label_h: float, trace: bool, kref: float, gap: float = 2.5) -> list:
    """A true frieze: specimens set left to right on a baseline (chord on the
    line, like writing), each as wide as it is, wrapping into rows; the
    tallest are capped at the 80th percentile height so one arc cannot
    shrink the page."""
    x0, y0, w, h = box
    if not items:
        return []
    hs = np.array([max(np.ptp(it["q"][:, 1]), 1e-9) for it in items])
    Hq = float(np.percentile(hs, 80))
    lab_w = [vd.text_width(it["label"], 0.85 * label_h) for it in items]
    th = 2.4 * label_h if trace else 0.0

    def lay(s):
        rows, cur, xw = [], [], 0.0
        for i, it in enumerate(items):
            si = s * min(1.0, Hq / hs[i])
            wi = max(np.ptp(it["q"][:, 0]) * si, lab_w[i])
            if cur and xw + wi > w:
                rows.append(cur)
                cur, xw = [], 0.0
            cur.append((i, si, wi))
            xw += wi + gap
        rows.append(cur)
        tot, meta = 0.0, []
        for r in rows:
            above = max(max(-items[i]["q"][:, 1].min() * si, 0.0) for i, si, _ in r)
            below = max(max(items[i]["q"][:, 1].max() * si, 0.0) for i, si, _ in r)
            rh = above + below + 1.9 * label_h + th + 1.2
            meta.append((above, below, rh))
            tot += rh
        return rows, meta, tot

    lo, hi = 1e-3, 1e3
    for _ in range(50):
        mid = math.sqrt(lo * hi)
        if lay(mid)[2] <= h:
            lo = mid
        else:
            hi = mid
    rows, meta, tot = lay(lo)
    out = []
    y = y0 + (h - tot) / 2
    for r, (above, below, rh) in zip(rows, meta):
        base = y + above
        xw = sum(wi for _, _, wi in r) + gap * (len(r) - 1)
        x = x0 + (w - xw) / 2
        for i, si, wi in r:
            q = items[i]["q"]
            qw = np.ptp(q[:, 0]) * si
            off = np.array([x + (wi - qw) / 2 - q[:, 0].min() * si, base])
            out.append((q * si + off, "specimen"))
            yl = base + below + 0.5 * label_h
            if trace:
                out += _trace(items[i]["k"], x + 0.05 * wi, x + 0.95 * wi, yl + 0.9 * label_h, 0.7 * label_h, kref)
                yl += th
            out += _text(items[i]["label"], x + wi / 2, yl, 0.85 * label_h)
            x += wi + gap
        y += rh
    return out


def plate_exploded(sp: list[dict], labels: list[str], box, *, centre, explode: float, cap: float,
                   label_h: float) -> list:
    """Each specimen where it was, pushed out from the centre; with cap > 0
    every specimen longer than cap × the median length is shrunk about its
    own centre to that length (round 10's big arcs stop dominating)."""
    x0, y0, w, h = box
    if not sp:
        return []
    c = np.asarray(centre, float)
    med = float(np.median([t["length"] for t in sp])) or 1.0
    moved = []
    for t in sp:
        mid = t["p"].mean(axis=0)
        f = min(1.0, cap * med / max(t["length"], 1e-9)) if cap > 0 else 1.0
        moved.append(mid + (t["p"] - mid) * f + explode * (mid - c))
    allp = np.vstack(moved)
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    hh = h - 1.6 * label_h
    k = min(w / max(hi[0] - lo[0], 1e-9), hh / max(hi[1] - lo[1], 1e-9))
    off = np.array([x0 + w / 2, y0 + hh / 2]) - (lo + hi) / 2 * k
    out = []
    cc = c * k + off
    for q, lab in zip(moved, labels):
        qq = q * k + off
        out.append((qq, "specimen"))
        far = qq[int(np.argmax(np.linalg.norm(qq - cc, axis=1)))]
        u = far - cc
        u = u / (np.linalg.norm(u) + 1e-9)
        out += _text(lab, *(far + u * 1.3 * label_h + np.array([0.0, -0.5 * 0.8 * label_h])), 0.8 * label_h)
    return out


def plate_taxonomy(items: list[dict], fam: list[int], box, *, label_h: float, trace: bool, kref: float,
                   names: list[str] | None = None) -> list:
    """Families in rows, a letter and a count in the gutter, a fine rule between
    families (a natural-history plate). `items` are already in family order."""
    x0, y0, w, h = box
    nf = max(fam) + 1 if fam else 0
    if not items:
        return []
    members = [[i for i, f in enumerate(fam) if f == g] for g in range(nf)]
    gut = 2.6 * label_h
    ww = w - gut
    best = None
    for cols in range(2, max(len(items), 3) + 1):
        rows = sum(-(-len(m) // cols) for m in members if m)
        cw, ch = ww / cols, h / rows
        score = abs(math.log((cw / ch) / 1.15))
        if best is None or score < best[0] - 1e-9:
            best = (score, cols, rows)
    _, cols, rows = best
    cw, ch = ww / cols, h / rows
    sc = _grid_scale(items, cw, ch, trace)
    out = []
    r0 = 0
    for g, mem in enumerate(members):
        if not mem:
            continue
        nr = -(-len(mem) // cols)
        fy = y0 + r0 * ch
        if r0 > 0:
            out.append((mp._rule(x0, fy, x0 + w, fy), "rule"))
        letter = chr(ord("A") + g)
        out += _text(letter, x0 + gut * 0.42, fy + 0.30 * ch - 0.8 * label_h, 1.6 * label_h)
        sub = f"{len(mem)}" if not names else f"{vd.short(names[g])} {len(mem)}"
        out += _text(sub, x0 + gut * 0.42 + (vd.text_width(sub, 0.6 * label_h) / 2 - 0.3 * gut if names else 0.0),
                     fy + 0.30 * ch + 1.3 * label_h, (0.6 if names else 0.75) * label_h)
        for j, i in enumerate(mem):
            r, c = divmod(j, cols)
            out += _cell(items[i], x0 + gut + c * cw, fy + r * ch, cw, ch, sc, trace=trace, kref=kref,
                         label_h=label_h)
        r0 += nr
    return out


def plate_hist(values: list[float], labels: list[str], box, *, what: str, style: str, label_h: float) -> list:
    """A histogram of the specimens drawn on the plate: `steps` (one staircase
    line standing on its baseline) or `tally` (each bar is the stack of the
    specimen numbers that fall in it — the count made of provenance).
    Lengths are binned on a log scale (one long arc must not crush the rest)."""
    x0, y0, w, h = box
    v = np.asarray(values, float)
    if len(v) == 0:
        return []
    logx = what == "length"
    u = np.log(np.maximum(v, 1e-3)) if logx else v
    nb = int(np.clip(round(math.sqrt(len(v))) + 1, 4, 10 if style == "tally" else 14))
    lo, hi = float(u.min()), float(u.max())
    if hi - lo < 1e-9:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, nb + 1)
    b = np.clip(np.searchsorted(edges, u, side="right") - 1, 0, nb - 1)
    cnt = np.bincount(b, minlength=nb)
    bx0, bx1 = x0 + 1.0, x0 + w - 1.0
    base = y0 + h - 1.8 * label_h
    top = y0 + 1.6 * label_h
    bw = (bx1 - bx0) / nb
    out = []
    unit = "MM, LOG" if logx else "DEG"
    out += _text(f"{what.upper()} ({unit})  N {len(v)}", x0, y0, 0.75 * label_h, anchor="left")
    out += _text(vd.num(float(v.min()), 0), bx0, base + 0.6 * label_h, 0.75 * label_h, anchor="left")
    out += _text(vd.num(float(v.max()), 0), bx1, base + 0.6 * label_h, 0.75 * label_h, anchor="right")
    mx = max(int(cnt.max()), 1)
    if style == "tally":
        lh = min(0.85 * label_h, (base - top) / (mx * 1.3), bw / max(vd.text_width("A10", 1.0) * 1.2, 1e-9))
        if lh >= 0.9:
            out.append((mp._rule(bx0, base, bx1, base), "rule"))
            for i in range(nb):
                mem = [labels[j] for j in np.flatnonzero(b == i)]
                for r, lab in enumerate(mem):
                    out += _text(lab, bx0 + (i + 0.5) * bw, base - 0.4 - (r + 1) * 1.3 * lh, lh)
            return out
    uy = (base - top - 1.4 * label_h) / mx
    pts = [(bx0, base)]
    for i in range(nb):
        y = base - cnt[i] * uy
        pts += [(bx0 + i * bw, y), (bx0 + (i + 1) * bw, y)]
    pts.append((bx1, base))
    pts.append((bx0, base))
    out.append((np.array(pts, float), "hist"))
    for i in range(nb):
        if cnt[i]:
            out += _text(str(int(cnt[i])), bx0 + (i + 0.5) * bw, base - cnt[i] * uy - 1.3 * label_h, 0.7 * label_h)
    return out


def plate_strip(sp_all: list[dict], sp: list[dict], labels: list[str], box, *, label_h: float) -> list:
    """The graph under the plate drawn by the drawing's own line (round 12; Ian
    on the taxonomy's length histogram: "feels detached"). Every specimen, in
    the order the line drew them, is turned so its chord lies on one baseline
    and set where the previous one ended: the drawing laid straight, cut where
    the plate cuts it. Each piece starts and ends on the baseline, so the strip
    is one continuous line; one scale for all, so each span's width is that
    specimen's chord and the long and short ones read straight off it. A tick
    at every cut, and under each span the specimen's label (A3, C1 …) — the
    same names as the plate above and the numbers on the drawing beside it."""
    x0, y0, w, h = box
    if not sp_all:
        return []
    pieces, chords = [], []
    for t in sorted(sp_all, key=lambda t: t["s0"]):
        p = np.asarray(t["p"], float)
        if len(p) < 2:
            continue
        d = p[-1] - p[0]
        c = float(np.hypot(*d))
        if c < 1e-9:                                   # a closed loop: lay it on its widest axis
            j = int(np.argmax(np.linalg.norm(p - p[0], axis=1)))
            d = p[j] - p[0]
            c = 0.0
        q = _rot(p - p[0], -math.atan2(d[1], d[0]))
        pieces.append((t, q))
        chords.append(c)
    if not pieces:
        return []
    head = 1.6 * label_h
    lh = 0.7 * label_h
    lab_of = {id(t): lab for t, lab in zip(sp, labels)}
    ext = [(float(np.ptp(q[:, 0])) if c == 0.0 else c, max(-q[:, 1].min(), 0.0), max(q[:, 1].max(), 0.0))
           for (_, q), c in zip(pieces, chords)]

    def lay(k):
        """Rows like writing (a row breaks between specimens) → rows, labels per row, height."""
        rows, cur, xw = [], [], 0.0
        for i, (wi, _, _) in enumerate(ext):
            if cur and xw + wi * k > w - 2.0:
                rows.append(cur)
                cur, xw = [], 0.0
            cur.append(i)
            xw += wi * k
        rows.append(cur)
        tot, meta = head, []
        for r in rows:
            up_ = max(ext[i][1] for i in r) * k
            dn_ = max(ext[i][2] for i in r) * k
            ends, x, slots = [], 0.0, []
            for i in r:
                xc = x + ext[i][0] * k / 2
                x += ext[i][0] * k
                lab = lab_of.get(id(pieces[i][0]))
                if lab is None:
                    slots.append(None)
                    continue
                half = vd.text_width(lab, lh) / 2
                j = next((j for j, e in enumerate(ends) if xc - half > e + 0.35 * lh), len(ends))
                if j == len(ends):
                    ends.append(-1e9)
                ends[j] = xc + half
                slots.append(j)
            rh = up_ + dn_ + (0.6 + 1.3 * max(len(ends), 1)) * lh + 0.8 * label_h
            meta.append((up_, dn_, slots, rh))
            tot += rh
        return rows, meta, tot

    lo, hi = 1e-4, 1e2
    for _ in range(50):
        mid = math.sqrt(lo * hi)
        if lay(mid)[2] <= h and len(lay(mid)[0]) <= 4:
            lo = mid
        else:
            hi = mid
    k = lo
    rows, meta, _ = lay(k)
    out = _text("THE LINE LAID STRAIGHT, CUT AS THE PLATE", x0, y0, 0.75 * label_h, anchor="left")
    y = y0 + head
    tk = 0.9 * lh
    for r, (up_, dn_, slots, rh) in zip(rows, meta):
        base = y + up_
        x = x0 + 1.0
        line = []
        for n, i in enumerate(r):
            (t, q), c = pieces[i], chords[i]
            qq = q * k + np.array([x, base])
            if c == 0.0:
                qq[:, 0] -= qq[:, 0].min() - x
            line.append(qq if not line else qq[1:])
            if n:
                out.append((mp._rule(x, base - 0.5 * tk, x, base + 0.5 * tk), "rule"))
            xc = x + ext[i][0] * k / 2
            x += ext[i][0] * k
            if slots[n] is not None:
                out += _text(lab_of[id(t)], xc, base + dn_ + 0.6 * lh + slots[n] * 1.3 * lh, lh)
        out.append((np.vstack(line), "specimen"))
        y += rh
    return [(p_, r_) for p_, r_ in out if len(p_) >= 2]


# ---------------------------------------------------------------------------
# index numbers on a drawing, avoiding each other and the line
# ---------------------------------------------------------------------------

def _rect_dist(pts: np.ndarray, rect) -> np.ndarray:
    cx, cy, hw, hh = rect
    dx = np.maximum(np.abs(pts[:, 0] - cx) - hw, 0.0)
    dy = np.maximum(np.abs(pts[:, 1] - cy) - hh, 0.0)
    return np.hypot(dx, dy)


def _rect_gap(a, b) -> float:
    dx = max(abs(a[0] - b[0]) - a[2] - b[2], 0.0)
    dy = max(abs(a[1] - b[1]) - a[3] - b[3], 0.0)
    return math.hypot(dx, dy) if (dx > 0 or dy > 0) else -min(a[2] + b[2] - abs(a[0] - b[0]),
                                                                a[3] + b[3] - abs(a[1] - b[1]))


def round10_rects(M: dict, ss, labels, *, label_h: float, tick: float) -> list[tuple]:
    """Where round 10's `index_on_drawing` put each number (for the collision count)."""
    out = []
    for s_, lab in zip(ss, labels):
        p, nrm, _ = mp._at(M, s_)
        best = None
        for sg in (1.0, -1.0):
            c = p + sg * nrm * (tick + 0.9 * label_h)
            d = float(np.min(np.linalg.norm(M["p"] - c, axis=1)))
            if best is None or d > best[0] + 1e-9:
                best = (d, sg)
        c = p + best[1] * nrm * (tick + 0.6 + 0.55 * label_h)
        out.append((float(c[0]), float(c[1]), vd.text_width(lab, label_h) / 2, label_h / 2))
    return out


def label_stats(pts: np.ndarray, rects: list[tuple]) -> dict:
    """overlaps: pairs of number boxes that touch; on_line: boxes the line runs through."""
    ov = sum(1 for i in range(len(rects)) for j in range(i + 1, len(rects)) if _rect_gap(rects[i], rects[j]) < 0.0)
    on = sum(1 for r in rects if float(_rect_dist(pts, (r[0], r[1], max(r[2] - 0.1, 0), max(r[3] - 0.1, 0))).min())
             <= 0.0)
    return {"labels": len(rects), "overlaps": ov, "on_line": on}


def place_labels(M: dict, ss, labels, *, label_h: float, tick: float = 1.6, avoid: bool = True,
                 extra_pts: np.ndarray | None = None, bounds=None, taken: list | None = None):
    """Numbers tied to places on the drawing. avoid=False: round 10's rule (a
    tick on the emptier side). avoid=True: candidates further out, on both
    sides and slid along the line are tried in order of preference; the first
    whose box clears the line (and shadow), every number already placed and
    the bounds wins, joined to its place by a leader. → (polys, rects)."""
    from scipy.spatial import cKDTree  # noqa: PLC0415
    pts = M["p"] if extra_pts is None or not len(extra_pts) else np.vstack([M["p"], extra_pts])
    tree = cKDTree(pts)
    rects = list(taken or [])
    mine = []
    out = []
    if not avoid:
        rr = round10_rects(M, ss, labels, label_h=label_h, tick=tick)
        out = mp.index_on_drawing(M, list(ss), list(labels), label_h=label_h, tick=tick)
        return out, rr
    base = tick + 0.6 + 0.55 * label_h
    for s_, lab in zip(ss, labels):
        p, nrm, _ = mp._at(M, s_)
        tg = np.array([nrm[1], -nrm[0]])
        hw, hh = vd.text_width(lab, label_h) / 2 + 0.25, label_h / 2 + 0.25
        cands = []
        for k, f in enumerate((1.0, 1.4, 1.9, 2.6, 3.5, 4.6, 6.0, 8.0)):
            for t in (0.0, 0.8, -0.8, 1.6, -1.6, 2.4, -2.4):
                for sg in (1.0, -1.0):
                    cands.append((k + 0.6 * abs(t), p + sg * nrm * base * f + tg * t * 2 * hw))
        cands.sort(key=lambda c: c[0])
        best, pick = None, None
        for cost, c in cands:
            rect = (float(c[0]), float(c[1]), hw, hh)
            if bounds is not None:
                bx0, by0, bw, bh = bounds
                if c[0] - hw < bx0 - 2 or c[0] + hw > bx0 + bw + 2 or c[1] - hh < by0 - 2 or c[1] + hh > by0 + bh + 2:
                    continue
            near = tree.query_ball_point(c, hw + hh + 2.0)
            lc = float(_rect_dist(pts[near], rect).min()) if near else 9.0
            q = np.array([np.clip(p[0], c[0] - hw, c[0] + hw), np.clip(p[1], c[1] - hh, c[1] + hh)])
            seg = np.linspace(p, q, 7)[2:-1]
            lead = np.linalg.norm(q - p)
            if lead > 2.5 and len(seg):
                dl, _ = tree.query(seg)
                lc = min(lc, float(dl.min()) + 0.25)
            gc = min((_rect_gap(rect, r) for r in rects), default=9.0)
            score = min(lc - 0.35, gc - 0.6)
            if score >= 0:
                pick = (rect, q)
                break
            if best is None or score > best[0]:
                best = (score, (rect, q))
        rect, q = pick if pick is not None else best[1]
        rects.append(rect)
        mine.append(rect)
        c = np.array(rect[:2])
        d = q - p
        dn = float(np.linalg.norm(d))
        if dn > 1.0:
            u = d / dn
            out.append(np.array([p + u * 0.5, q - u * 0.15]))
        out += vd.text(lab, c[0], c[1] - label_h / 2, label_h, anchor="centre")
    return out, mine


# ---------------------------------------------------------------------------
# rechain: the drawing redrawn from its atlas
# ---------------------------------------------------------------------------

def rechain_order(sp: list[dict], order: str, M: dict, rng=None, fam=None) -> list[int]:
    n = len(sp)
    idx = list(range(n))
    if order == "time":
        return idx
    if order == "reverse":
        return idx[::-1]
    if order == "turning":
        return sorted(idx, key=lambda i: (abs(sp[i]["turn"]), sp[i]["s0"]))
    if order == "length":
        return sorted(idx, key=lambda i: (sp[i]["length"], sp[i]["s0"]))
    if order == "family":
        f = fam if fam is not None else families(sp, 5)
        return sorted(idx, key=lambda i: (f[i], sp[i]["s0"]))
    if order == "shuffle":
        r = rng if rng is not None else np.random.default_rng(0)
        return [int(i) for i in r.permutation(n)]
    if order == "sign":
        pos = [i for i in idx if sp[i]["turn"] >= 0]
        neg = [i for i in idx if sp[i]["turn"] < 0]
        pos.sort(key=lambda i: sp[i]["s0"])                 # each sign keeps its own time order;
        neg.sort(key=lambda i: sp[i]["s0"])                 # the chain alternates them
        out = []
        while pos or neg:
            for lst in (pos, neg):
                if lst:
                    out.append(lst.pop(0))
        return out
    if order == "match":
        k = M["kappa"]
        ks = [float(np.mean(k[t["a"]:min(t["a"] + 4, t["b"])])) for t in sp]
        ke = [float(np.mean(k[max(t["b"] - 4, t["a"]):t["b"]])) for t in sp]
        out, left = [0], set(range(1, n))
        while left:
            cur = out[-1]
            nxt = min(sorted(left), key=lambda i: (abs(ks[i] - ke[cur]), sp[i]["s0"]))
            out.append(nxt)
            left.discard(nxt)
        return out
    raise ValueError(order)


def _ext(M: dict, t: dict) -> np.ndarray:
    """A specimen with the sample before it and the one after it (its entry and
    exit chords as the original line drew them; straight on at a mark end)."""
    p, mk, a, b = M["p"], M["mark"], t["a"], t["b"]
    pre = p[a - 1] if a > 0 and mk[a - 1] == mk[a] else p[a] - (p[min(a + 1, b - 1)] - p[a])
    post = p[b] if b < len(p) and mk[b] == mk[b - 1] else p[b - 1] + (p[b - 1] - p[max(b - 2, a)])
    return np.vstack([pre, p[a:b], post])


def _ang(v) -> float:
    return math.atan2(v[1], v[0])


def _tangent(M: dict, i: int, win: float) -> np.ndarray:
    """Unit tangent of the original line at sample i, from the chord over ±win
    mm (clipped to i's own mark): steadier than one chord on a jittery trail."""
    mk, n = M["mark"], len(M["p"])
    k = max(int(round(win / M["h"])), 1)
    lo = i
    while lo > 0 and i - lo < k and mk[lo - 1] == mk[i]:
        lo -= 1
    hi = i
    while hi < n - 1 and hi - i < k and mk[hi + 1] == mk[i]:
        hi += 1
    if hi == lo:
        return np.array([1.0, 0.0])
    d = M["p"][hi] - M["p"][lo]
    return d / (np.linalg.norm(d) + 1e-12)


def _rotm(a: float) -> np.ndarray:
    c, s_ = math.cos(a), math.sin(a)
    return np.array([[c, -s_], [s_, c]])


def rechain(M: dict, sp: list[dict], seq: list[int], *, rotate: bool = True, mirror: bool = False,
            blend: float = 0.0, win: float = 1.0) -> dict:
    """Chain specimens in `seq` order into one line. Each specimen keeps its own
    geometry and its entry/exit as the original drew them (`_ext`); rotate: the
    next specimen is turned so its tangent where it began (over ±win mm of the
    original) continues the chain's tangent where the last one ended — the time
    order reproduces the original exactly, any other order is G1 at every join;
    False = translated only (the collage baseline). mirror: a specimen turning
    the same way as the one before is reflected about its entry tangent, so
    turns keep alternating. blend > 0 smooths ±blend mm round each join.
    → {"p", "ids" (specimen per point), "src" (source sample per point),
       "joins" (point index where each joined specimen starts), "spans" {id: (i0, i1)}}."""
    pts: list = []
    ids: list = []
    src: list = []
    joins: list = []
    spans: dict = {}
    exit_v, prev_sign = None, None
    for sid in seq:
        t = sp[sid]
        e = _ext(M, t)
        si = np.arange(t["a"], t["b"])
        sign = 1.0 if t["turn"] >= 0 else -1.0
        A = np.eye(2)
        v_in = _tangent(M, t["a"], win)
        if mirror and prev_sign is not None and sign == prev_sign:
            a2 = 2.0 * _ang(v_in)
            A = np.array([[math.cos(a2), math.sin(a2)], [math.sin(a2), -math.cos(a2)]])
            sign = -sign
        if pts:
            if rotate:
                w_in = A @ v_in
                A = _rotm(_ang(exit_v) - _ang(w_in)) @ A
            e = (e - e[0]) @ A.T + np.asarray(pts[-1])
            joins.append(len(pts))
        i0 = len(pts)
        pts += e[1:-1].tolist()
        ids += [sid] * (len(e) - 2)
        src += si.tolist()
        spans[sid] = (i0, len(pts))
        b = t["b"]
        nxt = b if b < len(M["p"]) and M["mark"][b] == M["mark"][b - 1] else b - 1
        exit_v = A @ _tangent(M, nxt, win)               # where the original went on from here
        prev_sign = sign
    P_ = np.array(pts, float)
    if blend > 0 and joins and len(P_) > 8:
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))]
        h = max(float(np.median(np.diff(s))), 1e-6)
        sig = max(blend / h / 2.0, 1.0)
        sm = np.column_stack([gaussian_filter1d(P_[:, 0], sig, mode="nearest"),
                              gaussian_filter1d(P_[:, 1], sig, mode="nearest")])
        wgt = np.zeros(len(P_))
        for jn in joins:
            wgt = np.maximum(wgt, np.exp(-0.5 * ((s - s[jn]) / blend) ** 2))
        wgt[0] = wgt[-1] = 0.0
        P_ = P_ + wgt[:, None] * (sm - P_)
    return {"p": P_, "ids": np.array(ids), "src": np.array(src), "joins": joins, "spans": spans}


_rechain = rechain


def _theta_at(p: np.ndarray, s: np.ndarray, at: float, d: float, side: int) -> float:
    a, b = (at - d, at) if side < 0 else (at, at + d)
    pa = np.array([np.interp(a, s, p[:, 0]), np.interp(a, s, p[:, 1])])
    pb = np.array([np.interp(b, s, p[:, 0]), np.interp(b, s, p[:, 1])])
    return math.atan2(pb[1] - pa[1], pb[0] - pa[0])


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def continuity(p: np.ndarray, at_s, d: float = 1.0, s: np.ndarray | None = None) -> dict:
    """At each arc length: tangent jump |θ(s, s+d) − θ(s−d, s)| (deg) and the
    curvature jump |κ̄₊ − κ̄₋| with κ̄ the mean turning over the next / last d
    (via chords of d/2), 1/mm. `s`: the arc length of each point (default: cumulative chord)."""
    if s is None:
        s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    tj, kj = [], []
    for a in at_s:
        if a - 2 * d < 0 or a + 2 * d > s[-1]:
            continue
        t_m = _theta_at(p, s, a, d, -1)
        t_p = _theta_at(p, s, a, d, +1)
        tj.append(abs(math.degrees(_wrap(t_p - t_m))))
        k_m = _wrap(_theta_at(p, s, a - d / 2, d / 2, +1) - _theta_at(p, s, a - d, d / 2, +1)) / (d / 2)
        k_p = _wrap(_theta_at(p, s, a + d / 2, d / 2, +1) - _theta_at(p, s, a, d / 2, +1)) / (d / 2)
        kj.append(abs(k_p - k_m))
    return {"tangent_deg": np.array(tj), "dkappa": np.array(kj)}


def join_report(M: dict, sp: list[dict], ch: dict, d: float = 1.0) -> dict:
    """Continuity at the re-chained joins vs at the same cuts in the original
    line (where it is really continuous) vs everywhere along the original."""
    s_new = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(ch["p"], axis=0), axis=1))]
    new = continuity(ch["p"], [s_new[j] for j in ch["joins"]], d)

    def inside(a):                                   # the window round a stays on one mark
        i0 = int(np.clip(np.searchsorted(M["s"], a - 3 * d), 0, len(M["s"]) - 1))
        i1 = int(np.clip(np.searchsorted(M["s"], a + 3 * d), 0, len(M["s"]) - 1))
        return M["mark"][i0] == M["mark"][i1]

    cuts = [t["s0"] for t in sp[1:] if t["a"] > 0 and inside(t["s0"])]
    old = continuity(M["p"], cuts, d, s=M["s"])
    grid = [a for a in np.linspace(3 * d, M["L"] - 3 * d, 600) if inside(a)]
    every = continuity(M["p"], grid, d, s=M["s"])
    t95 = float(np.percentile(every["tangent_deg"], 95)) if len(every["tangent_deg"]) else 0.0
    k95 = float(np.percentile(every["dkappa"], 95)) if len(every["dkappa"]) else 0.0

    def med(a):
        return round(float(np.median(a)), 3) if len(a) else None

    return {"joins": len(new["tangent_deg"]),
            "tangent_deg_median": med(new["tangent_deg"]), "tangent_deg_max": round(float(new["tangent_deg"].max()), 1)
            if len(new["tangent_deg"]) else None,
            "dkappa_median": med(new["dkappa"]),
            "orig_cut_tangent_deg_median": med(old["tangent_deg"]), "orig_cut_dkappa_median": med(old["dkappa"]),
            "line_tangent_deg_p95": round(t95, 2), "line_dkappa_p95": round(k95, 4),
            "visible_kinks": int(np.sum(new["tangent_deg"] > t95)) if len(new["tangent_deg"]) else 0,
            "orig_visible_kinks": int(np.sum(old["tangent_deg"] > t95)) if len(old["tangent_deg"]) else 0,
            "visible_kappa_jumps": int(np.sum(new["dkappa"] > k95)) if len(new["dkappa"]) else 0}


def _chain_mark(M: dict, ch: dict, template, meta: dict) -> Mark:
    chans = {}
    for c in template:
        if c in M.get("ch", {}):
            chans[c] = np.asarray(M["ch"][c], float)[ch["src"]]
    chans["mn_specimen"] = ch["ids"].astype(float)
    return Mark(ch["p"], chans, meta)


# ---------------------------------------------------------------------------
# hand-drawing a plate, with some lines kept straight
# ---------------------------------------------------------------------------

def _hand_roles(ctx, polys_roles: list, drawn_by, amount, keep, straight) -> list:
    if not drawn_by:
        return polys_roles
    keep_straight = STRAIGHT[straight]
    idx = [i for i, (p, r) in enumerate(polys_roles) if r not in keep_straight and len(p) >= 2]
    if not idx:
        return polys_roles
    redrawn = vd.hand_drawn([np.asarray(polys_roles[i][0], float) for i in idx], ctx.use("hand", drawn_by),
                            ctx.rng("drawn_by", drawn_by), amount=amount, keep=keep)
    out = list(polys_roles)
    for i, q in zip(idx, redrawn):
        out[i] = (q, out[i][1])
    return out


# ---------------------------------------------------------------------------
# modulator: measure_next (the numbered atlas pairing, next versions)
# ---------------------------------------------------------------------------

_HAND = [
    P("drawn_by", "ref", None, "draw the plate through this hand (null = the machine draws it)", kind="hand",
      optional=True),
    P("straight", "choice", "rules+labels", "drawn_by: what stays machine-straight — rules + labels | labels | "
      "rules + labels + specimens (only traces and histogram are drawn by hand) | none",
      choices=tuple(STRAIGHT)),
    P("amount", "float", 1.5, "drawn_by: how much fine turning the hand owns", min=0.0, max=3.0),
    P("keep", "float", 0.006, "drawn_by: coarse scale the hand must keep (small = faithful)", min=0.001, max=0.2),
]


def _items(M, sp, labels, norm):
    return [{"q": norm_geom(t["p"], norm), "k": M["kappa"][t["a"]:t["b"]], "label": lab}
            for t, lab in zip(sp, labels)]


@modulator("measure_next", params=[
    P("cut", "choice", "turning", "where specimens are cut: turning (round 10) | inflection (whole line) | pause "
      "(speed minima) | hand (hand changes) | crossing | loops | approach (closest approaches)", choices=CUTS),
    P("grain", "float", 0.012, "finest specimen, share of the line's length", min=0.002, max=0.08),
    P("plate", "choice", "grid", "grid (round 10) | frieze (packed by width like writing) | exploded (with a "
      "length cap) | taxonomy (families in rows)", choices=PLATES),
    P("order", "choice", "time", "plate order (grid / frieze / exploded)", choices=mp.ORDERS),
    P("norm", "choice", "chord", "specimen geometry: chord (round 10) | axis (principal axis level) | size "
      "(common size) | axis+size", choices=NORMS),
    P("cells", "int", 24, "specimens shown (evenly sampled over the order)", min=2, max=120),
    P("families", "int", 5, "taxonomy: number of families", min=2, max=10),
    P("group", "choice", "shape", "taxonomy: families by shape (clustered) or by the hand speaking",
      choices=("shape", "hand")),
    P("trace", "bool", False, "each specimen with its own κ trace under it"),
    P("hist", "choice", "none", "graph under the plate: none | length | turning (histograms) | strip (the "
      "line's own turning on one baseline, cut and labelled as the plate: tied to the drawing)",
      choices=("none", "length", "turning", "strip")),
    P("hist_style", "choice", "steps", "steps (a staircase line) | tally (bars built of specimen numbers)",
      choices=("steps", "tally")),
    P("page", "choice", "diptych", "diptych (plate right) | margin (plate below) | triptych (drawing | plate | the "
      "drawing re-chained from its plate)", choices=PAGES),
    P("split", "float", 0.4, "share of the box the plate takes", min=0.15, max=0.8),
    P("rechain", "choice", "sign", "triptych: order of the re-chained specimens", choices=RECHAIN),
    P("mirror", "bool", False, "triptych: reflect specimens so the re-chained turning keeps alternating"),
    P("blend", "float", 0.0, "triptych: smoothing round each re-chained join, mm", min=0.0, max=10.0),
    P("shadow", "choice", "none", "the drawing with merged-shadow beads: none | turns (inner side of each turn) | "
      "left", choices=("none", "turns", "left")),
    P("shadow_gain", "float", 5.0, "shadow: extra distance at the strongest turn, mm", min=0.0, max=30.0),
    P("degrees", "bool", True, "grid/frieze: print each specimen's turning after its number"),
    P("explode", "float", 0.6, "exploded: push-out factor", min=0.0, max=3.0),
    P("cap", "float", 2.5, "exploded: longest specimen as a multiple of the median (0 = no cap)", min=0.0,
      max=20.0),
    P("label_h", "float", 2.0, "plate label height, mm", min=0.8, max=8.0),
    P("index_h", "float", 2.0, "index number height on the drawing, mm", min=0.6, max=6.0),
    P("avoid", "bool", True, "index numbers avoid each other and the line (False = round 10 placement)"),
    P("numbers", "choice", "all", "which drawings carry the specimen numbers: all | drawing (not the re-chained "
      "one) | rechain (only the re-chained one) | none (only the plate is labelled)",
      choices=("all", "drawing", "rechain", "none")),
    *_HAND,
], doc="a drawing paired with its specimen plate, next versions: new cuts, normalised specimens, κ traces, "
       "packed frieze, capped explosion, taxonomy, histogram, a re-chained third drawing", reach=lambda p: 2.0)
def measure_next(ctx, marks, *, cut, grain, plate, order, norm, cells, families, group, trace, hist, hist_style, page,
                 split, rechain, mirror, blend, shadow, shadow_gain, degrees, explode, cap, label_h, index_h, avoid,
                 drawn_by, straight, amount, keep, numbers="all"):
    live = _live(marks)
    if not live:
        return list(marks)
    template = mp._template(marks)
    part = marks[0].meta.get("part")
    x0, y0, w, h = ctx.box
    rbox = None
    if page == "margin":
        pad = 0.04 * h
        dbox = (x0, y0, w, h * (1 - split) - pad / 2)
        pbox = (x0, y0 + h * (1 - split) + pad / 2, w, h * split - pad / 2)
    elif page == "triptych":
        pad = 0.035 * w
        side = (1 - split) / 2
        dbox = (x0, y0, w * side - pad / 2, h)
        pbox = (x0 + w * side + pad / 2, y0, w * split - pad, h)
        rbox = (x0 + w * (side + split) + pad / 2, y0, w * side - pad / 2, h)
    else:
        pad = 0.04 * w
        dbox = (x0, y0, w * (1 - split) - pad / 2, h)
        pbox = (x0 + w * (1 - split) + pad / 2, y0, w * split - pad / 2, h)
    drawing = refit(list(marks), dbox)
    M = measure_plus(drawing)
    if M["L"] <= 0:
        return list(marks)
    sp_all = cut_specimens(M, cut, grain)
    if not sp_all:
        return drawing
    kref = max(float(np.percentile(np.abs(gaussian_filter1d(M["kappa"], 2.0, mode="nearest")), 97)), 1e-9)
    hb = None
    if hist != "none":
        hh = max(0.2 * pbox[3], 6.0 * label_h)
        hb = (pbox[0], pbox[1] + pbox[3] - hh, pbox[2], hh)
        pbox = (pbox[0], pbox[1], pbox[2], pbox[3] - hh - 0.03 * pbox[3])
    fam = None
    if plate == "taxonomy":
        sp = mp.order_specimens(sp_all, "time", cells)
        if group == "hand":
            seen = sorted({t["voice"] for t in sp}, key=lambda v: min(t["s0"] for t in sp if t["voice"] == v))
            fam_ = [seen.index(t["voice"]) for t in sp]
            fam_names = [M["voices"][v] if v < len(M["voices"]) else "?" for v in seen]
        else:
            fam_ = _families(sp, families)
            fam_names = None
        order_ = sorted(range(len(sp)), key=lambda i: (fam_[i], sp[i]["s0"]))
        sp = [sp[i] for i in order_]
        fam = [fam_[i] for i in order_]
        cnt: dict[int, int] = {}
        labels = []
        for f in fam:
            cnt[f] = cnt.get(f, 0) + 1
            labels.append(f"{chr(ord('A') + f)}{cnt[f]}")
    else:
        sp = mp.order_specimens(sp_all, order, cells)
        labels = [f"{i + 1:02d}" for i in range(len(sp))]
    plate_labels = [lab + (f" {math.degrees(t['turn']):+.0f}" if degrees and plate in ("grid", "frieze") else "")
                    for t, lab in zip(sp, labels)]
    items = _items(M, sp, plate_labels, "axis+size" if (plate == "taxonomy" and norm == "chord") else norm)
    if plate == "grid":
        pr = plate_grid(items, pbox, label_h=label_h, trace=trace, kref=kref)
    elif plate == "frieze":
        pr = plate_frieze(items, pbox, label_h=label_h, trace=trace, kref=kref)
    elif plate == "exploded":
        pr = plate_exploded(sp, labels, pbox, centre=M["p"].mean(axis=0), explode=explode, cap=cap,
                            label_h=label_h)
    else:
        pr = plate_taxonomy(items, fam, pbox, label_h=label_h, trace=trace, kref=kref, names=fam_names)
    if hb is not None and hist == "strip":
        pr += plate_strip(sp_all, sp, labels, hb, label_h=label_h)
    elif hb is not None:
        vals = [t["length"] if hist == "length" else math.degrees(t["turn"]) for t in sp]
        pr += plate_hist(vals, labels, hb, what=hist, style=hist_style, label_h=label_h)
    pr = _hand_roles(ctx, pr, drawn_by, amount, keep, straight)
    out: list[Mark] = []
    extra = None
    if shadow != "none":
        pairs = mp.shadow_lines(M, law="kappa", side=shadow, gap=0.6 if shadow == "turns" else 1.2,
                                gain=shadow_gain)
        rings, opened, _ = mp.merged_rings(pairs, close=1.0)
        src = {"p": M["p"], "voice": M["voice"], "r": M["r"]}
        out += mp._new_marks(rings + opened, template, "shadow", {"law": "kappa", "side": shadow, "merged": True},
                             part, src=src)
        extra = np.vstack(rings) if rings else None
    else:
        out += drawing
    idx = []
    if numbers in ("all", "drawing"):
        idx, _ = place_labels(M, [t["s_mid"] for t in sp], labels, label_h=index_h, avoid=avoid, extra_pts=extra,
                              bounds=dbox)
    polys = [np.asarray(p, float) for p, _ in pr if len(p) >= 2]
    roles = [r for p, r in pr if len(p) >= 2]
    for p_, r_ in zip(polys, roles):
        out += mp._new_marks([p_], template, "chart", {"chart": f"next:{plate}", "plate_role": r_, "cut": cut,
                                                       "drawn_by": drawn_by}, part)
    out += mp._new_marks(idx, template, "index", {"chart": f"next:{plate}"}, part)
    if rbox is not None:
        seq = rechain_order(sp_all, rechain, M, ctx.rng("rechain"), None)
        ch = _rechain(M, sp_all, seq, mirror=mirror, blend=blend)
        mk = _chain_mark(M, ch, template, {"measure_role": "rechain", "voice_id": "measure:rechain",
                                           "voices": M["voices"], "rechain": rechain, "part": part})
        mk2 = refit([mk], rbox)[0]
        M2 = vd.measure([mk2])
        k_ = mk2.length() / max(mk.length(), 1e-9)
        s_ch = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(ch["p"], axis=0), axis=1))]
        pos = {id(t): i for i, t in enumerate(sp_all)}
        ss2, lab2 = [], []
        for t, lab in zip(sp, labels):
            i0, i1 = ch["spans"][pos[id(t)]]
            ss2.append(float(s_ch[(i0 + i1 - 1) // 2]) * k_)
            lab2.append(lab)
        out.append(mk2)
        if numbers in ("all", "rechain"):
            idx2, _ = place_labels(M2, ss2, lab2, label_h=index_h, avoid=avoid, bounds=rbox)
            out += mp._new_marks(idx2, template, "index", {"chart": "next:rechain"}, part)
    return out


# ---------------------------------------------------------------------------
# modulator: measure_next_rechain (the drawing redrawn from its atlas)
# ---------------------------------------------------------------------------

@modulator("measure_next_rechain", params=[
    P("cut", "choice", "inflection", "specimen cut (as measure_next)", choices=CUTS),
    P("grain", "float", 0.012, "finest specimen, share of the line's length", min=0.002, max=0.08),
    P("order", "choice", "sign", "the new order", choices=RECHAIN),
    P("rotate", "bool", True, "turn each specimen so it continues the chain's tangent (False = collage)"),
    P("mirror", "bool", False, "reflect specimens so the turning keeps alternating"),
    P("blend", "float", 0.0, "smoothing round each join, mm", min=0.0, max=10.0),
], doc="the drawing redrawn from its own atlas: specimens re-chained in a new order into one line")
def measure_next_rechain(ctx, marks, *, cut, grain, order, rotate, mirror, blend):
    live = _live(marks)
    if not live:
        return list(marks)
    template = mp._template(marks)
    M = measure_plus(live)
    sp = cut_specimens(M, cut, grain)
    if len(sp) < 2:
        return list(marks)
    seq = rechain_order(sp, order, M, ctx.rng("rechain"))
    ch = rechain(M, sp, seq, rotate=rotate, mirror=mirror, blend=blend)
    md = {k: v for k, v in live[0].meta.items() if k not in ("fit",)}
    md.update({"voices": M["voices"], "rechain": order, "rechain_cut": cut,
               "rechain_joins": join_report(M, sp, ch)})
    mk = _chain_mark(M, ch, template, md)
    return refit([mk], ctx.box)


# ---------------------------------------------------------------------------
# modulator: measure_next_rehand (the hand changes at specimen boundaries)
# ---------------------------------------------------------------------------

@modulator("measure_next_rehand", params=[
    P("hands", "refs", ["matisse", "lichtenberg", "shikasta"], "the hands taking turns, specimen by specimen",
      kind="hand", min_len=1, max_len=6),
    P("cut", "choice", "inflection", "where the hand changes (a specimen cut)", choices=CUTS),
    P("grain", "float", 0.02, "finest specimen, share of the line's length", min=0.002, max=0.08),
    P("amount", "float", 2.0, "how much fine turning each hand owns", min=0.0, max=3.0),
    P("keep", "float", 0.02, "coarse scale each hand must keep (small = the course stays)", min=0.001, max=0.2),
    P("blend", "float", 1.5, "smoothing round each hand change, mm", min=0.0, max=10.0),
], doc="the drawing re-spoken specimen by specimen, the hand changing at every specimen boundary")
def measure_next_rehand(ctx, marks, *, hands, cut, grain, amount, keep, blend):
    from ._research import grammar as gm  # noqa: PLC0415
    from .voices_machine import resample  # noqa: PLC0415
    live = _live(marks)
    if not live:
        return list(marks)
    template = mp._template(marks)
    M = measure_plus(live)
    sp = [t for t in cut_specimens(M, cut, grain)]
    if cut in ("loops",) or not sp:
        return list(marks)
    grams = [ctx.use("hand", hd) for hd in hands]
    lo = M["p"].min(axis=0)
    k = 1000.0 / max(M["R"], 1e-9)
    out = []
    for mi in range(int(M["mark"].max()) + 1):
        mine = [t for t in sp if M["mark"][t["a"]] == mi]
        if not mine:
            continue
        pts, vc, src, joins = [], [], [], []
        for j, t in enumerate(mine):
            i = sp.index(t)
            hi = i % len(grams)
            q = resample((t["p"] - lo) * k, 1.0)
            try:
                st = gm.restyle(q, grams[hi], ctx.rng("rehand", i), ref_length=1000.0 / 0.9, amount=amount,
                                coarse_frac=keep, step=1.0)
                Q = st.points / k + lo
            except Exception:  # noqa: BLE001 — a degenerate specimen keeps its own shape
                Q = np.array(t["p"], float)
            Q = Q - Q[0] + t["p"][0]
            ramp = np.linspace(0, 1, len(Q))[:, None]
            Q = Q + ramp * ((t["p"][-1] - Q[-1]))
            if pts:
                joins.append(len(pts))
                Q = Q[1:]
            n = len(Q)
            pts += Q.tolist()
            vc += [float(hi)] * n
            src += np.round(np.linspace(t["a"], t["b"] - 1, n)).astype(int).tolist()
        P_ = np.array(pts, float)
        if blend > 0 and joins and len(P_) > 8:
            s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))]
            hstep = max(float(np.median(np.diff(s))), 1e-6)
            sig = max(blend / hstep / 2.0, 1.0)
            sm = np.column_stack([gaussian_filter1d(P_[:, 0], sig, mode="nearest"),
                                  gaussian_filter1d(P_[:, 1], sig, mode="nearest")])
            wgt = np.zeros(len(P_))
            for jn in joins:
                wgt = np.maximum(wgt, np.exp(-0.5 * ((s - s[jn]) / blend) ** 2))
            wgt[0] = wgt[-1] = 0.0
            P_ = P_ + wgt[:, None] * (sm - P_)
        src_ = np.array(src)
        chans = {c: np.asarray(M["ch"][c], float)[src_] for c in template if c in M["ch"]}
        chans["voice"] = np.array(vc)
        md = {kk: v for kk, v in live[mi].meta.items()}
        md.update({"voices": list(hands), "rehand": list(hands), "rehand_cut": cut,
                   "voice_id": "measure_next_rehand"})
        out.append(Mark(P_, chans, md))
    return out


# ---------------------------------------------------------------------------
# voice: measure_next_duet (a drawing that is itself two voices)
# ---------------------------------------------------------------------------

@voice("measure_next_duet", params=[
    P("hand_a", "ref", "matisse", "first voice", kind="hand"),
    P("hand_b", "ref", "lichtenberg", "second voice", kind="hand"),
    P("length", "float", 3.5, "each line's length in reference lengths", min=0.2, max=12.0),
    P("apart", "float", 0.35, "how far the second line is set off to the right (share of the first's width)",
      min=0.0, max=1.2),
    P("joins", "choice", "smooth", "drift joins", choices=("smooth", "chain")),
], doc="a drawing of two voices: two hands, two whole lines on one surface")
def measure_next_duet(ctx, *, hand_a, hand_b, length, apart, joins):
    from .voices_base import grow  # noqa: PLC0415
    pa, ca, _ = grow(ctx, [hand_a], length=length, blend="mixture", joins=joins, plateau=0.12)
    pb, cb, _ = grow(replace(ctx, seed=ctx.seed + 7919), [hand_b], length=length, blend="mixture", joins=joins,
                     plateau=0.12)
    wa = float(np.ptp(pa[:, 0]))
    pb = pb - pb.min(axis=0) + np.array([pa[:, 0].min() + apart * wa, pa[:, 1].min()])
    voices = [hand_a, hand_b]
    md = {"voices": voices, "route": voices, "library": [{"kind": "hand", "id": v} for v in voices]}
    return fitted([pa, pb], ctx.box, [{"voice": np.zeros(len(pa))}, {"voice": np.ones(len(pb))}], [md, md])
