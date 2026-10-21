# FROZEN from research commit d5ccd75: tools/gesture/gesture/kit/voices_handover.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Handover with a visible morph (round 13, thread II-b `handover`).

Hand A becomes hand B in one stroke, one FEATURE at a time, never a blend.

Hand Drift (round 8) mixed whole tokens by weight (`mixture`) or moved each
token toward the other hand's nearest token (`interp`). Both change every
property of the line at once, so the middle of a drift line is an average
of two hands: Ian later saw that kind of averaging "collapsing into a
style" (round 10). Here the two hands keep talking in parallel and the line
takes each of its properties from one of them, whole:

- `corner`  the breaks: whether a segment starts with a corner, and how
            sharp it is;
- `bend`    the shape of the segment: its kind and how far it turns
            (the turning angle is kept, so B's bend is drawn at A's size
            while length is still A's);
- `turn`    the handedness: which way each bend and corner turns — a
            hand that keeps turning the same way (the fly, 0.97 of
            consecutive turns) coils, one that alternates zigzags or waves;
- `length`  the tempo: the segment's length.

Both hands grow their own token streams (their order-2 chains, untouched).
Segment i of the line takes each feature from stream A or stream B, by a
per-feature switch. Each feature is handed over inside its own window of the line,
and the windows are staggered (`order`, `windows`), so between two windows
the line holds a pure intermediate grammar: A with B's corners, then A with
B's corners and bends, and so on. Inside a window the switch is a sticky
two-state chain whose share of B rises from 0 to 1 (`ease` shapes the
ramp): B's feature first appears as a rare short event inside A, then in
longer and longer runs, and A relapses in short runs at the end
(A A B A B B B). No number is ever averaged between the hands.

The line travels: each chunk of `chunk` segments is the best of K
proposals (fresh streams and switch draws) by progress toward a route
target, crowding of its own past and leaving the box (as `series_travel`
steers), so the stages are laid out in order along the paper instead of
curling over one another (the drift line's tangle hid its morph).

Channels: `src_corner`, `src_bend`, `src_turn`, `src_length` (0 = A, 1 = B,
nearest), `stage` (how many features are B's at that point, 0…4, nearest),
`handover_u` (0…1 along the line), `voice` (index into meta["voices"]:
the hand that owns the majority of the features).
Coordinates: sheet mm inside ctx.box (no refit).
"""
from __future__ import annotations

import numpy as np

from ._research import grammar as gm
from .core import P, Mark, channel_kind, voice

FEATURES = ("corner", "bend", "turn", "length")
for _c in ("src_corner", "src_bend", "src_turn", "src_length", "stage", "voice"):
    channel_kind(_c, "nearest")


# ---------------------------------------------------------------------------
# streams: a hand's tokens as segments carrying the corner before them
# ---------------------------------------------------------------------------

def segments(toks: list) -> list[dict]:
    """Token list → segments {corner: angle | None, kind, l, k0, k1, sgn}; a
    corner token attaches to the segment after it. sgn (±1) is the way the
    segment turns: its net turning if it bends, else its corner's, else the
    previous segment's."""
    out, pend, sg = [], None, 1.0
    for t in toks:
        if t[0] == "corner":
            pend = float(t[1])
            continue
        net = 0.5 * (float(t[2]) + float(t[3])) * float(t[1])
        if abs(net) > 0.02:
            sg = 1.0 if net > 0 else -1.0
        elif pend is not None and pend != 0:
            sg = 1.0 if pend > 0 else -1.0
        out.append({"corner": pend, "kind": t[0], "l": float(t[1]), "k0": float(t[2]), "k1": float(t[3]),
                    "sgn": sg})
        pend = None
    return out


def stream(g: gm.Grammar, rng, n: int) -> list[dict]:
    """≥ n segments of hand g: its own training-length strokes, each a
    fresh run of its chain, joined end to end (the drift line's chunks)."""
    out: list[dict] = []
    tries = 0
    while len(out) < n and tries < 200:
        tries += 1
        Ls = g.stroke_lengths or [0.1]
        L = max(float(Ls[int(rng.integers(len(Ls)))]), 1e-3)
        toks, _ = gm.generate_tokens(g, rng, length=L, p_follow=gm.P_FOLLOW, end_fit=gm.END_FIT)
        out += segments(toks)            # stroke joints stay smooth unless the hand cornered there
    if not out:
        out = [{"corner": None, "kind": "line", "l": 0.05, "k0": 0.0, "k1": 0.0}]
    while len(out) < n:
        out += out[: n - len(out)]
    return out[:n]


def compose(a: dict, b: dict, src: dict) -> dict:
    """One segment from two: each feature from the hand `src[f]` names
    (0 = a, 1 = b). The bend keeps its turning angle at the chosen length;
    the bend and the corner turn the way the `turn` hand turns."""
    pick = {f: (b if src[f] else a) for f in FEATURES}
    c = pick["bend"]
    l = pick["length"]["l"]
    sg = pick["turn"]["sgn"]
    r = c["l"] / max(l, 1e-9)
    net = c["k0"] + c["k1"]
    flip = sg * (-1.0 if net < 0 else 1.0)
    cor = pick["corner"]["corner"]
    return {"corner": None if cor is None else abs(cor) * sg, "kind": c["kind"], "l": l,
            "k0": c["k0"] * r * flip, "k1": c["k1"] * r * flip, "sgn": sg}


def average(a: dict, b: dict, w: float) -> dict:
    """CONTROL (mode `average`): one segment with every number moved from
    a's toward b's by w — the Hand Drift `interp` idea, the blend that
    collapses: log length, signed turning and corner angle averaged (a
    missing corner counts as 0 rad)."""
    la, lb = a["l"], b["l"]
    l = float(np.exp((1 - w) * np.log(max(la, 1e-9)) + w * np.log(max(lb, 1e-9))))
    k0 = ((1 - w) * a["k0"] * la + w * b["k0"] * lb) / l
    k1 = ((1 - w) * a["k1"] * la + w * b["k1"] * lb) / l
    ca, cb = a["corner"] or 0.0, b["corner"] or 0.0
    c = (1 - w) * ca + w * cb
    kind = a["kind"] if w < 0.5 else b["kind"]
    if kind == "line" and abs(k0) + abs(k1) > 1e-9:
        kind = "clothoid"
    return {"corner": c if abs(c) > 1e-3 else None, "kind": kind, "l": l, "k0": k0, "k1": k1,
            "sgn": 1.0 if (k0 + k1) >= 0 else -1.0}


def to_tokens(segs: list[dict], first: bool) -> list:
    out = []
    for i, s in enumerate(segs):
        if s["corner"] is not None and not (first and i == 0):
            out.append(["corner", float(s["corner"])])
        out.append([s["kind"], s["l"], s["k0"], s["k1"]])
    return out


# ---------------------------------------------------------------------------
# the schedule: staggered windows, a sticky switch per feature
# ---------------------------------------------------------------------------

def share_b(u: float, w0: float, w1: float, ease: float) -> float:
    """B's target share of a feature at progress u: 0 before its window,
    1 after it, (x)^ease inside (ease > 1: B arrives as rare events first)."""
    if u <= w0:
        return 0.0
    if u >= w1:
        return 1.0
    return float(((u - w0) / max(w1 - w0, 1e-9)) ** ease)


def step_switch(state: int, p: float, run: float, rng) -> int:
    """Sticky two-state switch with stationary share p of B: a run lasts
    about `run` segments at p = ½, A-runs grow as p → 0, B-runs as p → 1."""
    if p <= 0.0:
        return 0
    if p >= 1.0:
        return 1
    if state == 0:
        return 1 if rng.random() < p / run else 0
    return 0 if rng.random() < (1.0 - p) / run else 1


def parse_order(order: str) -> tuple[list[str], list[str]]:
    """(listed features in order, the unlisted rest). Unlisted features are
    handed over together with the last listed one."""
    fs = [f.strip() for f in order.split(",") if f.strip()]
    if not fs or len(set(fs)) != len(fs) or any(f not in FEATURES for f in fs):
        raise ValueError(f"morph_handover: order names features of {FEATURES}, each at most once, got {order!r}")
    return fs, [f for f in FEATURES if f not in fs]


def default_windows(k: int, gap: float = 0.06, lo: float = 0.1, hi: float = 0.92) -> list[float]:
    """k staggered windows over [lo, hi] with plateaus between them."""
    span = (hi - lo - gap * (k - 1)) / k
    out = []
    for i in range(k):
        a = lo + i * (span + gap)
        out += [a, a + span]
    return out


# ---------------------------------------------------------------------------
# the travelling line
# ---------------------------------------------------------------------------

def rows_path(rows: int, inset: float = 0.03) -> list[float]:
    """A boustrophedon path (x, y fractions of the box): `rows` rows, left to
    right, then right to left, …, joined at the margins."""
    pts = []
    for r in range(rows):
        y = (r + 0.5) / rows
        xs = (inset, 1 - inset) if r % 2 == 0 else (1 - inset, inset)
        pts += [xs[0], y, xs[1], y]
    return pts


def _dense(path: list[float], box, step: float = 0.5):
    """The path in mm, sampled every `step` mm: (points, cumulative length)."""
    x0, y0, w, h = box
    q = np.asarray(path, float).reshape(-1, 2) * [w, h] + [x0, y0]
    out = [q[:1]]
    for a, b in zip(q[:-1], q[1:]):
        n = max(int(np.ceil(np.linalg.norm(b - a) / step)), 1)
        out.append(a + (b - a) * (np.arange(1, n + 1)[:, None] / n))
    Q = np.vstack(out)
    return Q, np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]


def grow_handover(gA: gm.Grammar, gB: gm.Grammar, *, seed: int, box, R_mm: float, order: list[str],
                  windows: list[float], ease: float, run: float, path: list[float], ahead: float, band: float,
                  chunk: int, K: int, pull: float, clear: float, step: float, max_mm: float,
                  mode: str = "features"):
    """(points mm, per-point channels, info). The line follows `path`
    (x, y fractions of box); its progress v along the path (0…1, the
    line's position projected on the path, never going back) is what the
    handover windows are measured in, so the stages sit at chosen places
    on the paper. Deterministic in `seed`."""
    from scipy.spatial import cKDTree  # noqa: PLC0415

    rng = np.random.default_rng([int(seed), 0x4A4D0])
    win = {f: (float(windows[2 * i]), float(windows[2 * i + 1])) for i, f in enumerate(order)}
    for f in FEATURES:                      # unlisted features go with the last listed one
        win.setdefault(f, win[order[-1]])
    span = (min(v[0] for v in win.values()), max(v[1] for v in win.values()))   # the controls' one window
    x0, y0, w, h = box
    lo, hi = np.array([x0, y0]), np.array([x0 + w, y0 + h])
    Q, C = _dense(path, box)
    Lp = float(C[-1])
    pos = Q[0].copy()
    j1 = int(np.searchsorted(C, min(ahead, Lp)))
    heading = float(np.arctan2(*(Q[j1] - pos)[::-1]))
    state = {f: 0 for f in FEATURES}
    pts = [pos[None, :]]
    chans: dict[str, list] = {k: [np.zeros(1)] for k in ("src_corner", "src_bend", "src_turn", "src_length", "s", "v")}
    s_done, v_mm, first = 0.0, 0.0, True
    lag = max(int(3 * clear / step), 4)
    log = []                      # per segment: (s0 mm, v, src corner, bend, turn, length)
    n_chunks = 0
    while v_mm < Lp - 0.3 * ahead and s_done < max_mm and n_chunks < 4000:
        n_chunks += 1
        drawn = np.vstack(pts)
        tree = cKDTree(drawn[:-lag]) if len(drawn) > 2 * lag else None
        i0 = int(np.searchsorted(C, max(v_mm - 2 * ahead, 0.0)))
        i1 = int(np.searchsorted(C, min(v_mm + 4 * ahead, Lp))) + 1
        near = cKDTree(Q[i0:i1])
        tgt = Q[min(int(np.searchsorted(C, v_mm + ahead)), len(Q) - 1)]
        u = v_mm / Lp
        best = None
        for _k in range(K):
            sa, sb = stream(gA, rng, chunk), stream(gB, rng, chunk)
            st = dict(state)
            srcs, segs = [], []
            for i in range(chunk):
                if mode == "features":
                    for f in FEATURES:
                        st[f] = step_switch(st[f], share_b(u, *win[f], ease), run, rng)
                    segs.append(compose(sa[i], sb[i], st))
                elif mode == "tokens":          # control: whole segments of A or B (Hand Drift's mixture)
                    x = step_switch(st["bend"], share_b(u, span[0], span[1], ease), run, rng)
                    st = {f: x for f in FEATURES}
                    segs.append(dict(sb[i] if x else sa[i]))
                else:                           # control: every number averaged (the blend)
                    wv = share_b(u, span[0], span[1], 1.0)
                    st = {f: int(wv >= 0.5) for f in FEATURES}
                    segs.append(average(sa[i], sb[i], wv))
                srcs.append(dict(st))
            toks = to_tokens(segs, first)
            p, segm, _ = gm.tokens_to_points(toks, R_mm, start=pos, heading=heading, step=step)
            out = float(np.sum(np.clip(lo - p, 0, None) + np.clip(p - hi, 0, None))) / R_mm
            crowd = float(np.mean(tree.query(p, k=1)[0] < clear)) if tree is not None else 0.0
            dist, _ = near.query(p, k=1)
            stray = float(np.mean(np.clip(dist - band, 0, None))) / R_mm
            d = float(np.linalg.norm(p[-1] - tgt) / R_mm)
            score = 50 * out + 2.0 * crowd + 20.0 * stray + pull * d + 0.05 * rng.random()
            if best is None or score < best[0]:
                best = (score, toks, p, segm, srcs, st)
        _, toks, p, segm, srcs, st = best
        state = st
        sp = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
        s1 = np.array([sg["s1"] for sg in segm])
        jj = np.clip(np.searchsorted(s1, sp[1:], side="left"), 0, len(srcs) - 1)
        for f in FEATURES:
            chans[f"src_{f}"].append(np.array([srcs[i][f] for i in jj], float))
        chans["s"].append(s_done + sp[1:])
        chans["v"].append(np.full(len(p) - 1, u))
        for i, sg in enumerate(segm):
            log.append((s_done + sg["s0"], u, *(srcs[i][f] for f in FEATURES)))
        pts.append(p[1:])
        heading = gm.end_heading(toks, heading)
        pos = p[-1]
        s_done += float(sp[-1])
        _, jn = near.query(pos, k=1)
        v_mm = max(v_mm, float(C[i0 + int(jn)]))
        first = False
    P_ = np.vstack(pts)
    ch = {k: np.concatenate(v) for k, v in chans.items()}
    s = ch.pop("s")
    stage = sum(ch[f"src_{f}"] for f in FEATURES)
    ch["stage"] = stage
    ch["voice"] = (stage > len(FEATURES) / 2).astype(float)
    ch["handover_u"] = ch.pop("v")
    info = {"mode": mode, "segments": len(log), "length_mm": float(s[-1]), "path_mm": Lp, "windows": {f: list(win[f]) for f in order},
            "order": list(order),
            "segment_log": [[round(float(e[0]), 2), round(float(e[1]), 4), *map(int, e[2:])] for e in log]}
    return P_, ch, info


@voice("morph_handover", params=[
    P("hands", "refs", ["meander69", "fly_open"], "A then B: the hand that starts and the hand that ends",
      kind="hand", min_len=2, max_len=2),
    P("order", "str", "bend,turn,corner,length", "the order in which the features are handed to B "
      "(any of corner, bend, turn, length, each once; unlisted ones go with the last)"),
    P("windows", "floats", [], "per feature in `order`: start, end of its handover window as progress 0…1 "
      "along the path; empty = staggered with plateaus between"),
    P("ease", "float", 1.6, "shape of B's share inside a window (> 1: B arrives as rare events first)",
      min=0.3, max=5.0),
    P("run", "float", 3.0, "stickiness of each feature's switch: segments per run at an even share",
      min=1.0, max=30.0),
    P("R_mm", "float", 110.0, "the hands' reference length in mm (a token of length l is l·R_mm)",
      min=10.0, max=1000.0),
    P("rows", "int", 1, "the path: this many boustrophedon rows across the box (ignored if `route` is given)",
      min=1, max=12),
    P("route", "floats", [], "the path as x, y pairs (fractions of the box), in order; empty = `rows`"),
    P("ahead", "float", 25.0, "the route target sits this many mm ahead of the line's progress", min=2.0, max=300.0),
    P("band", "float", 20.0, "the line may stray this far (mm) from the path before it is pushed back",
      min=1.0, max=300.0),
    P("chunk", "int", 8, "segments grown between route decisions", min=2, max=60),
    P("K", "int", 10, "proposals per chunk", min=1, max=40),
    P("pull", "float", 3.0, "how hard the route target steers the choice among proposals", min=0.0, max=40.0),
    P("clear", "float", 1.2, "crowding radius, mm", min=0.1, max=20.0),
    P("step", "float", 0.3, "sampling step, mm", min=0.05, max=2.0),
    P("max_mm", "float", 20000.0, "safety cap on the line's arc length, mm", min=50.0, max=100000.0),
    P("mode", "choice", "features", "features: the handover, one feature at a time; controls over the same "
      "span: tokens = whole segments of A or B (Hand Drift's mixture, cut and paste), average = every "
      "number moved from A toward B (the blend)", choices=("features", "tokens", "average")),
], doc="hand A becomes hand B in one line, one feature at a time "
       "(corners, bends, handedness, tempo): staggered handovers leave readable intermediate grammars, never a blend")
def morph_handover(ctx, *, hands, order, windows, ease, run, R_mm, rows, route, ahead, band, chunk, K, pull, clear,
                   step, max_mm, mode):
    fs, _rest = parse_order(order)
    wn = list(windows) if windows else default_windows(len(fs))
    if len(wn) != 2 * len(fs) or any(wn[2 * i] > wn[2 * i + 1] for i in range(len(fs))):
        raise ValueError("morph_handover: windows are start, end pairs (start ≤ end), one per feature")
    path = [float(v) for v in route] if route else rows_path(int(rows))
    if len(path) < 4 or len(path) % 2:
        raise ValueError("morph_handover: route is x, y pairs, at least two")
    gA, gB = ctx.use("hand", hands[0]), ctx.use("hand", hands[1])
    pts, ch, info = grow_handover(gA, gB, seed=ctx.seed, box=ctx.box, R_mm=R_mm, order=fs, windows=wn, ease=ease,
                                  run=run, path=path, ahead=ahead, band=band, chunk=chunk, K=K, pull=pull,
                                  clear=clear, step=step, max_mm=max_mm, mode=mode)
    meta = {"voices": list(hands), "handover": info, "library": [{"kind": "hand", "id": h} for h in hands]}
    return [Mark(pts, ch, meta)]
