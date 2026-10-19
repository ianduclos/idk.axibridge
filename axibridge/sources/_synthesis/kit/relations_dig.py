# FROZEN from research commit c712045: tools/gesture/gesture/kit/relations_dig.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Round 16 C `dig`: archaeology further — early techniques as v2 relations.

Each revival takes a role it never had: it becomes something one layer does
BECAUSE of another, so it is a part of the synthesis bench, not a composer's
private step. Sources (rounds 2–11):

- `dig_pool`     round 6–7 regimes + wet edges. Round 6 measured that 84 % of
                 the reference's masses sit on junctions; round 7 measured what
                 a wet edge is (low-order lumpiness, cusped bays). Here a mass
                 is placed BY CONTACT: where two layers cross, one of them
                 pools into a round wet bead (line → nib → mass and back).
                 Ink it with `dig_wet` (nib + wet edges) so the bead is wet.
- `dig_restate`  round 9 restate (siyah mashq: mass by restatement), never
                 reviewed on its own; round 2–3 restyle (a path re-spoken in
                 another hand). Here a LATER layer restates an earlier one's
                 stressed stretch, in its own hand and pen: rehearsal by
                 another voice. Outcomes per stretch: shuttle (one
                 contiguous back-and-forth line), copies (separate lines),
                 echo (one copy set off at a distance).
- `dig_tremble`  rounds 3–4 tremor (the biggest perceptual lever found: a
                 blind judge spotted v4 29/30 without it, 20/30 with it;
                 v2: real tremor is a smooth log-normal amplitude modulation,
                 log-sd ≈ 0.3, correlated over ≈ 5 line widths). Here tremor
                 is a response to proximity: near the other line the dst
                 trembles, or (the other outcome) goes still.
- `dig_stiffen`  round 10 `dev_rare_machine` (rare machine events at
                 meaningful spots), never reviewed. Here the meaningful spot
                 is a contact: where it crosses another layer the line goes
                 mechanical for a short stretch (a stair, a ruler), then the
                 hand resumes.
- `dig_knot`     round 11 `river_loops` (learned oxbows and cut-off necks),
                 never reviewed. Here the loop is tied AT a crossing: the
                 line runs once round a learned oxbow from the crossing point
                 and goes on, so the knot sits on the other line.

All are contact relations except `dig_restate` (grow). Randomness comes only
from `rctx.rng(...)`; events are drawn in crossing / arc-length order.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from ._relations import RelOut, crossings, relation
from ._relations import pick as _pick
from .core import Mark, P

# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _fine(m: Mark, step: float) -> Mark:
    """The mark resampled at `step` mm when it is coarser than that."""
    if len(m) < 2:
        return m
    d = np.linalg.norm(np.diff(m.points, axis=0), axis=1)
    return m.resampled(step) if float(np.max(d)) > 1.5 * step else m


def _normals(p: np.ndarray, smooth: float = 2.0) -> np.ndarray:
    q = gaussian_filter1d(p, smooth, axis=0, mode="nearest") if len(p) > 4 else p
    t = np.gradient(q, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    return np.column_stack([-t[:, 1], t[:, 0]])


def _abs_kappa(p: np.ndarray) -> np.ndarray:
    d = np.diff(p, axis=0)
    if not len(d):
        return np.zeros(len(p))
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    ds = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    k = np.abs(np.gradient(th)) / ds
    return np.r_[k, k[-1:]]


def _ink_points(ground, step: float = 1.0) -> np.ndarray:
    """Every visible mark on the sheet so far, resampled at `step` mm."""
    pts = [m.resampled(step).points for lid in ground for m in ground[lid]
           if len(m) >= 2 and m.meta.get("of_role") != "unseen"]
    return np.vstack(pts) if pts else np.zeros((0, 2))


def _room(xs, ground, frame, margin: float = 6.0, src=None, dst=None) -> list[float]:
    """For each crossing: its clear room in mm — the distance to the nearest
    ink that is NOT one of the two crossing lines' own stretch through it
    (other layers, or the same lines elsewhere), and to the paper's edge.
    A mass or a loop wants room."""
    from scipy.spatial import cKDTree  # noqa: PLC0415
    W, H = frame
    pts = _ink_points(ground)
    tree = cKDTree(pts) if len(pts) else None
    out = []
    for c in xs:
        at = np.asarray(c.at, float)
        edge = min(at[0], W - at[0], at[1], H - at[1]) - margin
        best = 2.0 * max(edge, 0.0)
        if tree is not None:
            own = []
            for marks, i, s0 in ((src, c.i_src, c.s_src), (dst, c.i_dst, c.s_dst)):
                if marks is None:
                    continue
                m = marks[i].resampled(0.5)
                own.append((m, m.arclength(), s0 * m.length() / max(marks[i].length(), 1e-9)))
            for r in (3.0, 5.0, 8.0, 12.0, 18.0, 26.0):
                if r >= best:
                    break
                idx = tree.query_ball_point(at, r)
                q = pts[idx] if idx else np.zeros((0, 2))
                # discount points lying on the two lines' own pass through the crossing
                for m, s, s0 in own:
                    sel = (s > s0 - 1.6 * r) & (s < s0 + 1.6 * r)
                    if sel.any() and len(q):
                        d = np.min(np.linalg.norm(q[:, None, :] - m.points[sel][None, :, :], axis=2), axis=1)
                        q = q[d > 0.8]
                if len(q):
                    best = min(best, r)
                    break
            else:
                pass
        out.append(float(best))
    return out


def _order(xs, room, how: str, rng) -> list[int]:
    """Crossing indices, best first: room (most isolated), first (in arc
    order), random. Stable ties."""
    idx = list(range(len(xs)))
    if how == "room":
        return sorted(idx, key=lambda i: (-room[i], i))
    if how == "random":
        return [int(i) for i in rng.permutation(len(xs))]
    return idx


def _tangent_at(m: Mark, s: float) -> float:
    sm = m.arclength()
    i = int(np.clip(np.searchsorted(sm, s), 1, len(m) - 1))
    a, b = m.points[max(i - 3, 0)], m.points[min(i + 3, len(m) - 1)]
    return math.atan2(b[1] - a[1], b[0] - a[0])


# ---------------------------------------------------------------------------
# dig_pool: the wet junction mass
# ---------------------------------------------------------------------------

def pool_mark(m: Mark, s0: float, size: float, roundness: float) -> Mark:
    """`m` with a round mass centred at arc length s0: r rises through nib to
    mass (2) and falls back over `roundness`·size mm; M = size there."""
    m = _fine(m, 0.3)
    s = m.arclength()
    half = 0.5 * roundness * size
    x = (s - s0) / max(half, 1e-9)
    bump = np.where(np.abs(x) < 1, 0.5 * (1 + np.cos(np.pi * x)), 0.0)
    r = np.maximum(m["r"], 2.0 * bump)
    M = np.where(bump > 0, np.maximum(size, 0.0), m["M"])
    pool = np.maximum(m.channel("pool", 0.0), bump)
    return m.evolve(channels={"r": r, "M": M, "pool": pool})


def _pools(ground) -> list[tuple[float, float]]:
    """Centres of the pools already on the sheet (any layer), in layer order."""
    out = []
    for lid in ground:
        for m in ground[lid]:
            p = m.channel("pool")
            if p is None or float(np.max(p)) < 0.99:
                continue
            on = p >= 0.99
            dd = np.diff(np.r_[0, on.astype(np.int8), 0])
            for a, b in zip(np.flatnonzero(dd == 1), np.flatnonzero(dd == -1)):
                c = m.points[(a + b - 1) // 2]
                out.append((float(c[0]), float(c[1])))
    return out


def coil_mark(m: Mark, s0: float, at, size: float, spacing: float, rng) -> Mark | None:
    """`m` with its pass through `at` replaced by a line-built mass (round 9's
    coil): the line runs in to the crossing and winds out in one contiguous
    spiral, ring spacing `spacing`, to where its course leaves the disc."""
    m = _fine(m, 0.3)
    s, p = m.arclength(), m.points
    c = np.asarray(at, float)
    R = 0.5 * size
    d = np.linalg.norm(p - c, axis=1)
    k0 = int(np.clip(np.searchsorted(s, s0), 1, len(s) - 2))
    i_in, i_out = k0, k0
    while i_in > 0 and d[i_in] < R:
        i_in -= 1
    while i_out < len(p) - 1 and d[i_out] < R:
        i_out += 1
    if i_in <= 0 or i_out >= len(p) - 1:
        return None
    turns = max(R / max(spacing, 1e-3), 1.0)
    sign = 1.0 if rng.random() < 0.5 else -1.0
    a1 = math.atan2(p[i_out, 1] - c[1], p[i_out, 0] - c[0])
    n = max(int(2 * math.pi * R * turns / 0.25 / 2), 40)
    u = np.linspace(0.0, 1.0, n)
    th = a1 - sign * 2 * math.pi * turns * (1.0 - u)
    # a hand's coil, not a target: uneven ring spacing, low-order lobes (round 7's
    # wet-edge finding: wetness is lumpiness of the whole mass), a small wobble
    wob = gaussian_filter1d(rng.normal(0.0, 1.0, n), n / (turns * 3), mode="nearest")
    wob = wob / max(float(np.std(wob)), 1e-9) * 0.3 * spacing
    pace = np.cumsum(np.exp(0.35 * gaussian_filter1d(rng.normal(0.0, 1.0, n), n / turns, mode="nearest")))
    pace = (pace - pace[0]) / max(pace[-1] - pace[0], 1e-9)
    lobes = 1.0 + rng.uniform(0.04, 0.10) * np.cos(2 * th + rng.uniform(0, 2 * np.pi)) \
        + rng.uniform(0.02, 0.06) * np.cos(3 * th + rng.uniform(0, 2 * np.pi))
    rr = np.maximum(R * pace ** 0.9 * lobes + wob * np.sin(np.pi * u), 0.0)
    spiral = c + np.column_stack([np.cos(th), np.sin(th)]) * rr[:, None]
    lead = np.linspace(p[i_in], c, max(int(np.linalg.norm(p[i_in] - c) / 0.3), 2))[1:-1]
    ring = np.vstack([lead, spiral])
    P_ = np.vstack([p[:i_in + 1], ring, p[i_out + 1:]])
    S_ = np.r_[s[:i_in + 1], np.linspace(s[i_in], s[i_out], len(ring)), s[i_out + 1:]]
    keep = np.r_[True, np.linalg.norm(np.diff(P_, axis=0), axis=1) > 1e-9]
    flag = np.r_[np.zeros(i_in + 1), np.ones(len(ring)), np.zeros(len(p) - i_out - 1)]
    pool = np.maximum(np.interp(S_, s, m.channel("pool", 0.0)), flag)
    return m.remap(S_[keep], points=P_[keep], channels={"pool": pool[keep]})


@relation("dig_pool", phase="contact", params=[
    P("count", "int", 1, "pools per layer pair (one heavy mass as the single weight is the strong version)",
      min=0, max=8),
    P("size", "float", 8.0, "mass diameter, mm", min=1.5, max=24.0),
    P("size_sd", "float", 0.2, "log-normal spread of the size between pools", min=0.0, max=1.0),
    P("roundness", "float", 1.3, "length of the line→mass ramp, × size (≈1.2 keeps it a round bead, "
      "≥3 makes a capsule)", min=0.8, max=4.0),
    P("side_src", "float", 0.4, "chance the EARLIER line pools instead of the later one", min=0.0, max=1.0),
    P("w_wet", "float", 0.6, "weight: the pool is ink (line → nib → wet mass; ink with dig_wet)", min=0.0, max=1.0),
    P("w_coil", "float", 0.4, "weight: the pool is built from the line itself (a coil wound out from the "
      "crossing, one contiguous spiral)", min=0.0, max=1.0),
    P("spacing", "float", 0.7, "coil ring spacing, mm (≈ 1.5–2 pens keeps every ring legible)", min=0.2, max=4.0),
    P("pick", "choice", "room", "which crossing: room (the most isolated) | first | random",
      choices=("room", "first", "random")),
    P("sheet_max", "int", 1, "pools on the whole sheet, all pairs together (the single weight)", min=0, max=12),
    P("min_sep", "float", 3.0, "crossings closer than this along a line count once, mm", min=0.0, max=30.0),
], doc="where two layers cross, one pools into a round wet mass (masses sit on junctions)")
def dig_pool(rctx, src, dst, *, count, size, size_sd, roundness, side_src, w_wet, w_coil, spacing, pick,
             sheet_max, min_sep):
    xs = crossings(src, dst, min_sep=min_sep)
    if not xs or count <= 0:
        return RelOut()
    rng = rctx.rng("pool")
    room = _room(xs, rctx.ground, rctx.frame, src=src, dst=dst)
    taken = _pools(rctx.ground)
    count = min(count, sheet_max - len(taken))
    if count <= 0:
        return RelOut()
    chosen = []
    for i in _order(xs, room, pick, rng):
        c = xs[i]
        sz = size * float(math.exp(size_sd * rng.normal()))
        if any(math.dist(c.at, t) < 2.0 * sz for t in taken):
            continue
        chosen.append((c, sz))
        taken.append(c.at)
        if len(chosen) >= count:
            break
    new_dst, new_src = list(dst), list(src)
    events = []
    weights = {"wet": w_wet, "coil": w_coil} if (w_wet + w_coil) > 0 else {"wet": 1.0}
    plan = []
    for c, sz in chosen:
        plan.append((bool(rng.random() < side_src), _pick(rng, weights), c, sz))
    # far end first per mark, so a coil (which changes a mark's length) never shifts a later pool
    plan.sort(key=lambda t: (t[0], t[2].i_src if t[0] else t[2].i_dst, -(t[2].s_src if t[0] else t[2].s_dst)))
    for on_src, how, c, sz in plan:
        marks = new_src if on_src else new_dst
        mi, s0 = (c.i_src, c.s_src) if on_src else (c.i_dst, c.s_dst)
        if how == "coil":
            got = coil_mark(marks[mi], s0, c.at, sz, spacing, rctx.rng("coil", len(events)))
            if got is None:
                how, got = "wet", pool_mark(marks[mi], s0, sz, roundness)
        else:
            got = pool_mark(marks[mi], s0, sz, roundness)
        marks[mi] = got
        events.append({"outcome": "pool_over" if on_src else "pool_under", "at": c.at,
                       "s": [c.s_dst, c.s_dst], "mark": c.i_dst, "s_src": [c.s_src, c.s_src],
                       "size": round(sz, 2), "side": "src" if on_src else "dst", "how": how})
    events.sort(key=lambda e: (e["mark"], e["s"][0]))
    new_src = [m if "pool" in m.channels else m.evolve(channels={"pool": np.zeros(len(m))}) for m in new_src]
    new_dst = [m if "pool" in m.channels else m.evolve(channels={"pool": np.zeros(len(m))}) for m in new_dst]
    touched_src = any(e["side"] == "src" for e in events)
    return RelOut(dst=new_dst, src=new_src if touched_src else None, events=events)


# ---------------------------------------------------------------------------
# dig_restate: a later voice restates an earlier one's stressed stretch
# ---------------------------------------------------------------------------

def stress(m: Mark, span: float = 26.0) -> np.ndarray:
    """Per-point stress of a line: its emphasis channel when it has one, its
    regime when it is inked heavier than wire, else its sustained turning at
    the scale of the stretch (|κ| of the line smoothed at span/8, then
    averaged over span/4): a big sweep, not a kink — where a reader would
    say the line 'says' something."""
    e = m.channel("emphasis")
    if e is not None and float(np.max(e)) > 0.05:
        return np.clip(np.asarray(e, float), 0, None)
    r = np.asarray(m["r"], float)
    if float(np.max(r)) > 0.3:
        return r / 2.0
    s = m.arclength()
    step = max(float(np.median(np.diff(s))) if len(s) > 1 else 1.0, 1e-6)
    ps = gaussian_filter1d(m.points, max(span / 8 / step, 1.0), axis=0, mode="nearest")
    return gaussian_filter1d(_abs_kappa(ps), max(span / 4 / step, 1.0), mode="nearest")


def stressed_stretches(src: list[Mark], n: int, span: float, clear=None) -> list[tuple[int, float, float, float]]:
    """The n loudest stretches (mark, s0, s1, peak) of `span` mm, ≥ span
    apart. `clear(mark index, mark) -> mm per point` (optional) weights each by its room from
    other ink, so a restatement lands where it can be read."""
    cands = []
    for mi, m in enumerate(src):
        if len(m) < 4 or m.length() < 0.8 * span:
            continue
        st = stress(m, span)
        st = 0.5 + 0.5 * np.clip(st / max(float(np.quantile(st, 0.85)), 1e-12), 0.0, 1.0)  # loud is loud
        st = st * (1.0 - 0.8 * _cusps(m, span))          # a sweep, not a kink: room and grace decide
        if clear is not None:
            st = st * (0.05 + 0.95 * _smoothstep(clear(mi, m) / 9.0))
        s = m.arclength()
        L = float(s[-1])
        ok = (s > 0.5 * span) & (s < L - 0.5 * span)
        for j in np.flatnonzero(ok):
            cands.append((float(st[j]), mi, float(s[j])))
    cands.sort(key=lambda t: (-t[0], t[1], t[2]))
    out: list[tuple[int, float, float, float]] = []
    for v, mi, sc in cands:
        if any(mi == o[0] and abs(sc - 0.5 * (o[1] + o[2])) < span for o in out):
            continue
        out.append((mi, sc - 0.5 * span, sc + 0.5 * span, v))
        if len(out) >= n:
            break
    return out


def _cusps(m: Mark, span: float, r_min: float = 2.0) -> np.ndarray:
    """1 where a window of `span` mm round a point holds a cusp or a curl
    tighter than r_min mm, smoothly 0 elsewhere."""
    s = m.arclength()
    step = max(float(np.median(np.diff(s))) if len(s) > 1 else 1.0, 1e-6)
    ps = gaussian_filter1d(m.points, max(0.6 / step, 0.5), axis=0, mode="nearest")
    k = _abs_kappa(ps) > 1.0 / r_min
    from scipy.ndimage import maximum_filter1d  # noqa: PLC0415
    w = max(int(span / step), 1)
    return gaussian_filter1d(maximum_filter1d(k.astype(float), size=w, mode="nearest"), w / 6, mode="nearest")


def _clearance(others: dict, src: list[Mark], span: float):
    """clear(mi, m) → per point of src mark mi, the distance (mm) to the
    nearest ink of the other layers or of the src itself farther than `span`
    along its own line."""
    from scipy.spatial import cKDTree  # noqa: PLC0415
    rows = []
    for m in (m for lid in others for m in others[lid] if len(m) >= 2 and m.meta.get("of_role") != "unseen"):
        q = m.resampled(1.0).points
        rows.append(np.column_stack([q, np.full(len(q), -1.0), np.zeros(len(q))]))
    for j, m in enumerate(src):
        if len(m) >= 2:
            q = m.resampled(1.0)
            rows.append(np.column_stack([q.points, np.full(len(q), float(j)), q.arclength()]))
    if not rows:
        return None
    A = np.vstack(rows)
    tree = cKDTree(A[:, :2])

    def clear(mi, m):
        s = m.arclength()
        out = np.full(len(m), 40.0)
        for k, (p, sk) in enumerate(zip(m.points, s)):
            idx = tree.query_ball_point(p, 12.0)
            if not idx:
                continue
            q = A[idx]
            far = ~((q[:, 2] == mi) & (np.abs(q[:, 3] - sk) < 0.6 * span))
            if far.any():
                out[k] = float(np.min(np.linalg.norm(q[far, :2] - p, axis=1)))
        return out
    return clear


def _segment(m: Mark, s0: float, s1: float, step: float = 0.3) -> np.ndarray:
    s = m.arclength()
    ss = np.linspace(s0, s1, max(int((s1 - s0) / step), 4))
    return np.column_stack([np.interp(ss, s, m.points[:, 0]), np.interp(ss, s, m.points[:, 1])])


def _in_hand(seg: np.ndarray, g, rng, diag: float, amount: float) -> np.ndarray:
    """The segment re-spoken by hand g (research restyle at the sheet's
    scale: the sheet diagonal ↦ 1000 px, as measure_answer)."""
    from ._research import grammar as gm  # noqa: PLC0415
    from .voices_machine import resample  # noqa: PLC0415
    lo = seg.min(axis=0)
    kk = 1000.0 / max(diag, 1e-9)
    q = resample((seg - lo) * kk, 1.0)
    if len(q) < 8:
        return seg
    try:
        st = gm.restyle(q, g, rng, ref_length=1000.0 / 0.9, amount=amount, coarse_frac=0.02, step=1.0)
        return st.points / kk + lo
    except Exception:  # noqa: BLE001 — a degenerate stretch keeps its own shape
        return seg


def _copy(seg: np.ndarray, rng, *, drift, slide, turn, wobble, trim) -> np.ndarray:
    from .prosody_renderers import restated  # noqa: PLC0415
    return restated(seg, rng, drift=drift, slide=slide, turn=turn, wobble=wobble, trim=trim)


@relation("dig_restate", phase="grow", params=[
    P("n", "int", 1, "how many of the src's stressed stretches the dst restates", min=1, max=6),
    P("span", "float", 48.0, "length of a restated stretch, mm", min=6.0, max=160.0),
    P("copies", "float", 5.0, "statements per stretch (mean; drawn ±40 %)", min=1.0, max=20.0),
    P("in_hand", "bool", True, "each copy re-spoken in the dst's own hand (its fine turning)"),
    P("amount", "float", 1.4, "how much fine turning the dst's hand owns in a copy", min=0.0, max=3.0),
    P("drift", "float", 0.8, "σ across the stretch, mm", min=0.0, max=10.0),
    P("slide", "float", 1.5, "σ along the stretch, mm", min=0.0, max=20.0),
    P("turn", "float", 2.0, "σ of the turn, degrees", min=0.0, max=30.0),
    P("wobble", "float", 0.3, "smooth lateral wobble, mm", min=0.0, max=5.0),
    P("trim", "float", 3.0, "each copy's ends cut short by up to this, mm", min=0.0, max=30.0),
    P("w_shuttle", "float", 0.35, "weight: one contiguous back-and-forth line (mashq without lifting)",
      min=0.0, max=1.0),
    P("w_copies", "float", 0.45, "weight: separate copies, nearly on top of the stretch", min=0.0, max=1.0),
    P("w_echo", "float", 0.2, "weight: one copy, set off at a distance (an echo)", min=0.0, max=1.0),
    P("echo_mm", "float", 7.0, "how far an echo is set off, mm", min=1.0, max=40.0),
    P("keep_own", "bool", True, "the dst keeps its own line (false: the layer is only the restatement)"),
], doc="a later voice restates an earlier one's stressed stretch, in its own hand and pen")
def dig_restate(rctx, src, dst, *, n, span, copies, in_hand, amount, drift, slide, turn, wobble, trim,
                w_shuttle, w_copies, w_echo, echo_mm, keep_own):
    if not src or not dst:
        return RelOut()
    clear = _clearance({k: v for k, v in rctx.ground.items() if k != rctx.src}, src, span)
    stretches = stressed_stretches(src, n, span, clear)
    if not stretches:
        return RelOut()
    tmpl = dst[0]
    hand = (tmpl.meta.get("voices") or [None])[0]
    g = None
    if in_hand and hand:
        try:
            g = rctx.use("hand", hand)
        except Exception:  # noqa: BLE001 — not a library hand (a machine, a lines layer): plain copies
            g = None
    diag = float(math.hypot(*rctx.frame))
    weights = {"shuttle": w_shuttle, "copies": w_copies, "echo": w_echo}
    if not any(v > 0 for v in weights.values()):
        weights = {"copies": 1.0}
    chans = {k: float(np.median(v)) for k, v in tmpl.channels.items()}
    meta = {k: v for k, v in tmpl.meta.items() if k not in ("fit",)}
    out = list(dst) if keep_own else []
    events = []
    for k, (mi, s0, s1, peak) in enumerate(stretches):
        rng = rctx.rng("restate", k)
        seg = _segment(src[mi], s0, s1)
        how = _pick(rng, weights)
        nc = 1 if how == "echo" else max(2, int(round(copies * rng.uniform(0.6, 1.4))))
        lines = []
        for j in range(nc):
            base = _in_hand(seg, g, rng, diag, amount) if g is not None else seg
            c = _copy(base, rng, drift=drift, slide=slide, turn=turn, wobble=wobble, trim=trim)
            if how == "echo":
                nv = _normals(c, 6.0)
                side = 1.0 if rng.random() < 0.5 else -1.0
                c = c + side * echo_mm * nv.mean(axis=0) / (np.linalg.norm(nv.mean(axis=0)) + 1e-9)
            lines.append(c)
        if how == "shuttle":
            path = [lines[0]]
            for j, c in enumerate(lines[1:], 1):
                path.append(c[::-1] if j % 2 else c)
            lines = [np.vstack(path)]
        for c in lines:
            ch = {kk: np.full(len(c), v) for kk, v in chans.items()}
            ch["restate"] = np.ones(len(c))
            out.append(Mark(c, ch, {**meta, "restate": {"of": rctx.src, "how": how, "stretch": k}}))
        mid = seg[len(seg) // 2]
        events.append({"outcome": how, "at": [float(mid[0]), float(mid[1])], "s_src": [s0, s1],
                       "src_mark": mi, "copies": nc, "in_hand": g is not None, "stress": round(peak, 4)})
    if keep_own:
        for i, m in enumerate(out[:len(dst)]):
            if "restate" not in m.channels:
                out[i] = m.evolve(channels={"restate": np.zeros(len(m))})
    return RelOut(dst=out, events=events)


# ---------------------------------------------------------------------------
# dig_tremble: tremor as a response to proximity
# ---------------------------------------------------------------------------

def _unit_noise(n: int, sigma: float, rng) -> np.ndarray:
    x = gaussian_filter1d(rng.normal(0.0, 1.0, n + 64), max(sigma, 0.5), mode="wrap")[32:32 + n]
    return x / max(float(np.std(x)), 1e-9)


@relation("dig_tremble", phase="contact", params=[
    P("reach", "float", 5.0, "how near the other line must come, mm", min=0.5, max=40.0),
    P("amp", "float", 0.4, "tremor amplitude at contact (RMS lateral, mm)", min=0.0, max=3.0),
    P("base", "float", 0.0, "the line's own tremor away from the other (RMS, mm)", min=0.0, max=1.0),
    P("wave", "float", 5.0, "tremor wavelength, mm (a waver of a few line widths at the sheet's scale)", min=0.2, max=10.0),
    P("burst", "float", 0.35, "log-sd of the smooth amplitude modulation (tremor v2 measured ≈ 0.3)",
      min=0.0, max=1.5),
    P("burst_mm", "float", 2.5, "correlation length of that modulation, mm (≈ 5 line widths)",
      min=0.3, max=30.0),
    P("w_tremble", "float", 0.75, "weight: near the other, the line trembles", min=0.0, max=1.0),
    P("w_still", "float", 0.25, "weight: near the other, the line goes still (its tremor stops and its fine "
      "turning is smoothed away)",
      min=0.0, max=1.0),
    P("streak", "float", 0.5, "chance an encounter repeats the previous outcome", min=0.0, max=1.0),
    P("still_mm", "float", 2.0, "how much a still line smooths its own turning, mm", min=0.2, max=10.0),
    P("both", "bool", False, "the earlier line answers too (mutual nerves)"),
], doc="near another line the dst trembles (bursty tremor v2) or goes still; elsewhere its own small tremor")
def dig_tremble(rctx, src, dst, *, reach, amp, base, wave, burst, burst_mm, w_tremble, w_still, streak,
                still_mm, both):
    from scipy.spatial import cKDTree  # noqa: PLC0415
    if not src or not dst:
        return RelOut()
    step = 0.2
    weights = {"tremble": w_tremble, "still": w_still}
    if not any(v > 0 for v in weights.values()):
        weights = {"tremble": 1.0}
    events: list[dict] = []

    def shake(marks, others, side):
        pts = [m.resampled(1.0).points for m in others if len(m) >= 2]
        if not pts:
            return list(marks)
        tree = cKDTree(np.vstack(pts))
        rng = rctx.rng("tremble", side)
        last = None
        out = []
        for mi, m0 in enumerate(marks):
            if len(m0) < 3 or m0.length() < 2:
                out.append(m0.evolve(channels={"tremor": m0.channel("tremor", 0.0)}))
                continue
            m = m0.resampled(step)
            p = m.points
            d, _ = tree.query(p)
            g = _smoothstep((reach - d) / reach)
            s = m.arclength()
            near = d < reach
            on = np.zeros(len(p))
            still = np.zeros(len(p))
            dd = np.diff(np.r_[0, near.astype(np.int8), 0])
            for a, b in zip(np.flatnonzero(dd == 1), np.flatnonzero(dd == -1)):
                if s[b - 1] - s[a] < 1.0:
                    continue
                if last is not None and rng.random() < streak:
                    how = last
                else:
                    how = _pick(rng, weights)
                last = how
                # the encounter's own envelope: the gate, widened a little so it eases in
                (on if how == "tremble" else still)[a:b] = 1.0
                j = a + int(np.argmin(d[a:b]))
                ev = {"outcome": how, "at": [float(p[j, 0]), float(p[j, 1])], "side": side,
                      "closest": round(float(d[j]), 2)}
                if side == "dst":
                    ev.update({"s": [s[a], s[b - 1]], "mark": mi})
                else:
                    ev.update({"s_src": [s[a], s[b - 1]], "src_mark": mi})
                events.append(ev)
            t_env = np.clip(gaussian_filter1d(on * g, 1.0 / step, mode="nearest") * 1.2, 0, 1)
            s_env = np.clip(gaussian_filter1d(still, 2.0 / step, mode="nearest") * 1.2, 0, 1)
            A = np.maximum(base * (1.0 - s_env) + max(amp - base, 0.0) * t_env, 0.0)
            env = np.exp(burst * _unit_noise(len(p), burst_mm / step, rng) - 0.5 * burst ** 2)
            tr = A * env * _unit_noise(len(p), wave / step / 4.0, rng)
            # pinned ends: a tremor never moves where the line starts or stops
            tr *= _smoothstep(np.minimum(s, s[-1] - s) / 1.0)
            calm = gaussian_filter1d(p, still_mm / step, axis=0, mode="nearest")
            p = p + s_env[:, None] * (calm - p) * _smoothstep(np.minimum(s, s[-1] - s) / 1.0)[:, None]
            q = p + _normals(p, 3.0) * tr[:, None]
            prev = m.channel("tremor", 0.0)
            out.append(m.evolve(points=q, channels={"tremor": prev + tr}))
        return out

    new_dst = shake(dst, src, "dst")
    new_src = shake(src, dst, "src") if both else None
    return RelOut(dst=new_dst, src=new_src, events=events)


# ---------------------------------------------------------------------------
# dig_stiffen: the machine at the point of contact
# ---------------------------------------------------------------------------

@relation("dig_stiffen", phase="contact", params=[
    P("count", "int", 1, "machine events per layer pair", min=0, max=6),
    P("stretch", "float", 20.0, "length of one machine stretch, mm", min=2.0, max=80.0),
    P("unit", "float", 2.6, "machine unit (stair pitch), mm", min=0.3, max=10.0),
    P("w_stair", "float", 0.6, "weight: a stair", min=0.0, max=1.0),
    P("w_ruler", "float", 0.4, "weight: a ruler (straight runs, ticked corners)", min=0.0, max=1.0),
    P("w_after", "float", 0.5, "weight: the machine starts at the crossing (a shock)", min=0.0, max=1.0),
    P("w_around", "float", 0.5, "weight: the machine straddles the crossing", min=0.0, max=1.0),
    P("pick", "choice", "room", "which crossing: room | first | random", choices=("room", "first", "random")),
    P("min_sep", "float", 3.0, "crossings closer than this along a line count once, mm", min=0.0, max=30.0),
], doc="where it crosses another layer the line goes mechanical for a short stretch, then the hand resumes")
def dig_stiffen(rctx, src, dst, *, count, stretch, unit, w_stair, w_ruler, w_after, w_around, pick, min_sep):
    from .voices_machine import _opts, hand_over  # noqa: PLC0415
    xs = crossings(src, dst, min_sep=min_sep)
    if not xs or count <= 0:
        return RelOut()
    rng = rctx.rng("stiffen")
    room = _room(xs, rctx.ground, rctx.frame, src=src, dst=dst)
    opts = _opts(5, 72.0, "L=LSR,R=RRS,S=SL", 2, 0.25)
    per: dict[int, list] = {}
    events = []
    for i in _order(xs, room, pick, rng):
        if len(events) >= count:
            break
        c = xs[i]
        L = dst[c.i_dst].length()
        where = _pick(rng, {"after": w_after, "around": w_around}) if (w_after + w_around) > 0 \
            else "around"
        a, b = (c.s_dst, c.s_dst + stretch) if where == "after" else (c.s_dst - stretch / 2, c.s_dst + stretch / 2)
        if (rng.random() < 0.5) and where == "after":
            a, b = c.s_dst - stretch, c.s_dst                          # or it arrives stiff
        a, b = max(a, 2.0), min(b, L - 2.0)
        if b - a < 0.4 * stretch:
            continue
        if any(not (b + 4 < x0 or a - 4 > x1) for x0, x1, _ in per.get(c.i_dst, [])):
            continue
        g = _pick(rng, {"stair": w_stair, "ruler": w_ruler}) if (w_stair + w_ruler) > 0 else "stair"
        per.setdefault(c.i_dst, []).append((a, b, g))
        events.append({"outcome": "stiffen", "at": c.at, "s": [a, b], "mark": c.i_dst, "grammar": g,
                       "where": where})
    if not events:
        return RelOut()
    new = list(dst)
    for mi, ivs in sorted(per.items()):
        m = new[mi]
        for a, b, g in sorted(ivs, reverse=True):          # from the far end, so earlier s stay valid
            m = hand_over(m, [(a, b)], [g], rctx.rng("machine", mi, int(round(a * 100))), unit, opts)
        new[mi] = m
    if any("machine" in m.channels for m in new):
        new = [m if "machine" in m.channels else m.evolve(channels={"machine": np.zeros(len(m))}) for m in new]
    return RelOut(dst=new, events=sorted(events, key=lambda e: (e["mark"], e["s"][0])))


# ---------------------------------------------------------------------------
# dig_knot: a learned oxbow tied round the crossing (a lasso)
# ---------------------------------------------------------------------------

def _inner_radius(loop: np.ndarray) -> float:
    """Clear radius of a closed loop round its pole of inaccessibility (0 if degenerate)."""
    from shapely.geometry import Polygon  # noqa: PLC0415
    from shapely.ops import polylabel  # noqa: PLC0415
    body = loop[:-1] if np.allclose(loop[0], loop[-1]) else loop
    poly = Polygon(body).buffer(0)
    if poly.is_empty or poly.geom_type != "Polygon":
        return 0.0
    return float(poly.exterior.distance(polylabel(poly, tolerance=0.002)))


def _lasso(m: Mark, s0: float, at, loop: np.ndarray, turns: float) -> tuple[Mark, dict] | None:
    """`m` with its course near arc length s0 replaced by a loop centred on
    `at`: the line arrives at the loop's rim, runs round it (`turns` ≥ 1,
    the other line passing through the loop) and leaves from the rim where
    its course comes back out. None when the loop does not fit the line."""
    m = _fine(m, 0.3)
    s = m.arclength()
    p = m.points
    c = np.asarray(at, float)
    from shapely.geometry import Polygon  # noqa: PLC0415
    from shapely.ops import polylabel  # noqa: PLC0415
    body = loop[:-1] if np.allclose(loop[0], loop[-1]) else loop
    poly = Polygon(body).buffer(0)
    if poly.is_empty or poly.geom_type != "Polygon":
        return None
    pole = polylabel(poly, tolerance=0.05)
    inner = float(poly.exterior.distance(pole))          # the loop's clear radius round the crossing
    body = body - np.array([pole.x, pole.y]) + c
    rad = float(np.median(np.linalg.norm(body - c, axis=1)))
    if inner < 0.25 * rad:
        return None
    d = np.linalg.norm(p - c, axis=1)
    k0 = int(np.clip(np.searchsorted(s, s0), 1, len(s) - 2))
    out_ = d >= rad
    i_in = k0
    while i_in > 0 and not out_[i_in]:
        i_in -= 1
    i_out = k0
    while i_out < len(p) - 1 and not out_[i_out]:
        i_out += 1
    if i_in <= 0 or i_out >= len(p) - 1 or s[i_out] - s[i_in] > 6 * rad:
        return None
    n = len(body)
    j_in = int(np.argmin(np.linalg.norm(body - p[i_in], axis=1)))
    j_out = int(np.argmin(np.linalg.norm(body - p[i_out], axis=1)))
    # run the loop in the direction the line is already turning toward
    t_line = p[min(i_in + 2, len(p) - 1)] - p[max(i_in - 2, 0)]
    t_fwd = body[(j_in + 2) % n] - body[j_in]
    step_dir = 1 if float(np.dot(t_line, t_fwd)) >= 0 else -1
    run = (j_out - j_in) * step_dir % n
    total = int(round(turns * n)) + run
    idx = [(j_in + step_dir * q) % n for q in range(total + 1)]
    ring = body[idx]
    P_ = np.vstack([p[:i_in + 1], ring, p[i_out:]])
    S_ = np.r_[s[:i_in + 1], np.linspace(s[i_in], s[i_out], len(ring)), s[i_out:]]
    keep = np.r_[True, np.linalg.norm(np.diff(P_, axis=0), axis=1) > 1e-9]
    flag = np.r_[np.zeros(i_in + 1), np.ones(len(ring)), np.zeros(len(p) - i_out)]
    knot = np.maximum(np.interp(S_, s, m.channel("knot", 0.0)), flag)
    return (m.remap(S_[keep], points=P_[keep], channels={"knot": knot[keep]}),
            {"s_in": float(s[i_in]), "s_out": float(s[i_out]), "radius": round(rad, 2)})


@relation("dig_knot", phase="contact", params=[
    P("count", "int", 1, "knots per layer pair", min=0, max=6),
    P("size", "float", 4.5, "the loop's clear radius round the crossing, mm", min=1.0, max=30.0),
    P("size_sd", "float", 0.3, "log-normal spread of loop sizes", min=0.0, max=1.5),
    P("roundest", "float", 0.6, "chance the roundest of a few learned oxbows is taken (else any of them)",
      min=0.0, max=1.0),
    P("turns", "float", 1.0, "times round the loop (1 = once; the run to the exit is added)", min=0.0, max=4.0),
    P("jitter", "float", 0.15, "shape jitter on the learned turning function, rad", min=0.0, max=1.0),
    P("side_src", "float", 0.3, "chance the EARLIER line ties the knot", min=0.0, max=1.0),
    P("pick", "choice", "room", "which crossing: room | first | random", choices=("room", "first", "random")),
    P("min_sep", "float", 3.0, "crossings closer than this along a line count once, mm", min=0.0, max=30.0),
], doc="at a crossing one line lassos the other: it runs round a learned oxbow centred on the crossing and "
       "goes on; the other line passes through the loop")
def dig_knot(rctx, src, dst, *, count, size, size_sd, roundest, turns, jitter, side_src, pick, min_sep):
    from .voices_rivers import sample_loop  # noqa: PLC0415
    xs = crossings(src, dst, min_sep=min_sep)
    if not xs or count <= 0:
        return RelOut()
    data = rctx.use("river_loops", "river_cutoffs")
    rng = rctx.rng("knot")
    room = _room(xs, rctx.ground, rctx.frame, src=src, dst=dst)
    plan, taken = [], []
    for i in _order(xs, room, pick, rng):
        c = xs[i]
        rad = size * float(math.exp(size_sd * rng.normal()))
        if any(math.dist(c.at, t) < 3.0 * rad for t in taken) or room[i] < 1.2 * rad:
            continue
        on_src = bool(rng.random() < side_src)
        loops = []
        for _ in range(6):
            pts, _fam = sample_loop(data, "oxbow", rng, jitter=jitter)
            inner = _inner_radius(pts)
            if inner > 0:
                loops.append((inner * 2 * math.pi, pts, inner))        # roundness: 1 = a circle
        if not loops:
            continue
        j = int(np.argmax([lp[0] for lp in loops])) if rng.random() < roundest else int(rng.integers(len(loops)))
        _, pts, inner = loops[j]
        per = min(rad / inner, 120.0)
        if bool(rng.random() < 0.5):
            pts = pts * np.array([1.0, -1.0])
        plan.append((on_src, c, pts * per, per))
        taken.append(c.at)
        if len(plan) >= count:
            break
    new_dst, new_src = list(dst), list(src)
    events = []
    # tie from the far end of each mark backwards, so earlier arc lengths stay valid
    plan.sort(key=lambda t: (t[0], t[1].i_src if t[0] else t[1].i_dst, -(t[1].s_src if t[0] else t[1].s_dst)))
    for on_src, c, loop, per in plan:
        marks = new_src if on_src else new_dst
        mi, s0 = (c.i_src, c.s_src) if on_src else (c.i_dst, c.s_dst)
        got = _lasso(marks[mi], s0, c.at, loop, turns)
        if got is None:
            continue
        marks[mi], info = got
        events.append({"outcome": "knot_over" if on_src else "knot_under", "at": c.at, "s": [c.s_dst, c.s_dst],
                       "mark": c.i_dst, "s_src": [c.s_src, c.s_src], "perimeter": round(per, 1),
                       "side": "src" if on_src else "dst", **info})
    if not events:
        return RelOut()
    touched_src = any(e["side"] == "src" for e in events)
    if touched_src:
        new_src = [m if "knot" in m.channels else m.evolve(channels={"knot": np.zeros(len(m))}) for m in new_src]
    new_dst = [m if "knot" in m.channels else m.evolve(channels={"knot": np.zeros(len(m))}) for m in new_dst]
    return RelOut(dst=new_dst, src=new_src if touched_src else None,
                  events=sorted(events, key=lambda e: (e["mark"], e["s"][0])))
