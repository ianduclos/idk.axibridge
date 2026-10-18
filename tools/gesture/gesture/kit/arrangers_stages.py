"""Stages: a morph across a series, caused by events (round 13, thread II-d, prefix `stages`).

Metamorphosis (round 12, `arrangers_series`) changed its line at authored
progress values. Here nothing changes by index or by progress: the line's
gesture type changes only because of what it MEETS on the sheets, and each
change, once caused, runs on gradually as a process with a direction.

One line is integrated in curvature space across a row of sheets:

    θ'(s) = κ_src(s) − pull·sin(θ − θ_route) + walls

κ_src is spoken bend by bend (a bend = the stretch between two inflections,
kept whole) by one of its sources: a learned hand's own bends (`hand`, drift
taken out, as the `belt` voice reads them), or a grammar the line has
caught. The route only says roughly where the line should be; it never
changes what the line is.

Event layers are the other parts of the recipe, each a voice placed in its
own box on the row, inked in its own pen, with an EFFECT on the line:

- `grammar`  (e.g. the far river) — while listening, a near and aligned
             contour takes the line: it rides 0.9 mm beside it, leaves at a
             tangent, and from then on the layer's own bends (the river past
             the fragment's end, when the layer is the frozen far-view stem)
             come back into the line more and more often (infection
             p(s) = p_max·(1 − exp(−Δs/τ))). Bends are interleaved whole,
             never averaged.
- `nib`      (another voice) — every crossing of the layer sets the nib's
             angle to the crossed line's heading and adds width; width and
             angle then approach their new targets over `tau_nib` mm.
- `hand`     (another voice) — every crossing raises the share of the
             layer's own hand in the line (one hand turning into another).

And two events that come from the line itself:

- `pool`     where the wet nib (W ≥ `wet`) crosses its own earlier trace, ink
             pools into a round bead; each bead is bigger than the last.
- `ink`      beads and nib width spend a budget; when it is spent the pen is
             dry: width falls to a hairline and pooling stops.

The paper edge is the row's cut (`arrangers_series.cut`): a bead or a ride on
an edge is split by the paper.

Channels on the line: r, phi, W, M (for the `nib` renderer), `src` (0 hand,
1 caught grammar, 2 riding, 3 caught hand), `series_u`. The line's meta holds
`events` [(s mm, kind, x, y)] and `pools` [(x, y, d)].
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

from .core import P, Ink, Mark, arranger, channel_kind, fit, renderer, voice
from .voices_base import grow

channel_kind("src", "nearest")

EFFECTS = ("grammar", "nib", "hand", "none")


# ---------------------------------------------------------------------------
# curvature streams
# ---------------------------------------------------------------------------

def resample(p: np.ndarray, step: float) -> np.ndarray:
    p = np.asarray(p, float)
    d = np.linalg.norm(np.diff(p, axis=0), axis=1)
    keep = np.r_[True, d > 1e-9]
    p = p[keep]
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    if s[-1] <= step:
        return p
    u = np.arange(0.0, s[-1], step)
    return np.column_stack([np.interp(u, s, p[:, 0]), np.interp(u, s, p[:, 1])])


def kappa(p: np.ndarray, step: float, smooth: float = 2.0) -> np.ndarray:
    """κ (1/mm) of a polyline resampled at `step` (len = len(resampled) − 2)."""
    q = resample(p, step)
    th = np.unwrap(np.arctan2(*np.diff(q, axis=0).T[::-1]))
    k = np.diff(th) / step
    return gaussian_filter1d(k, smooth, mode="nearest") if smooth > 0 else k


class Stream:
    """A curvature stream spoken bend by bend (a bend = one sign of κ).
    Bends are whole; the pointer walks forward and wraps."""

    def __init__(self, k: np.ndarray, min_bend: int = 4):
        k = np.asarray(k, float)
        sg = np.where(k >= 0, 1, -1)
        cuts = np.flatnonzero(np.diff(sg)) + 1
        raw = np.split(k, cuts)
        bends: list[np.ndarray] = []
        for b in raw:                       # glue slivers onto the previous bend
            if bends and len(b) < min_bend:
                bends[-1] = np.r_[bends[-1], b]
            else:
                bends.append(b)
        self.bends = bends or [np.zeros(8)]
        self.i = 0

    def seek(self, idx: int) -> None:
        """Start at the bend that contains sample `idx` of the original stream."""
        n = 0
        for j, b in enumerate(self.bends):
            n += len(b)
            if n > idx:
                self.i = j
                return
        self.i = 0

    def next(self) -> np.ndarray:
        b = self.bends[self.i % len(self.bends)]
        self.i += 1
        return b


def hand_stream(ctx, hand: str, length: float, read_box, step: float, drift_mm: float) -> np.ndarray:
    pts, _ch, _meta = grow(ctx, [hand], length=length, blend="mixture", joins="smooth", plateau=0.12)
    s, off = fit([pts], read_box)
    line = np.asarray(pts, float) * s + off
    k = kappa(line, step)
    return k - gaussian_filter1d(k, drift_mm / step, mode="nearest")


# ---------------------------------------------------------------------------
# event layers
# ---------------------------------------------------------------------------

class Layer:
    def __init__(self, index: int, effect: str, marks: list[Mark], step: float, kstream: tuple | None,
                 hand: str | None):
        self.index = index
        self.effect = effect
        self.hand = hand
        polys = [resample(m.points, step) for m in marks if len(m) >= 2]
        polys = [q for q in polys if len(q) >= 3]
        self.polys = polys
        pts, tan, pid, idx = [], [], [], []
        for j, q in enumerate(polys):
            t = np.gradient(q, axis=0)
            t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
            pts.append(q)
            tan.append(t)
            pid.append(np.full(len(q), j))
            idx.append(np.arange(len(q)))
        self.P = np.vstack(pts) if pts else np.zeros((0, 2))
        self.T = np.vstack(tan) if tan else np.zeros((0, 2))
        self.pid = np.concatenate(pid) if pid else np.zeros(0, int)
        self.idx = np.concatenate(idx) if idx else np.zeros(0, int)
        self.tree = cKDTree(self.P) if len(self.P) else None
        self.kstream = kstream                      # grammar: (forward, backward) bends past the fragment, or None
        self.rides = 0
        self.crossings = 0
        self.last_cross = -1e9
        self.caught_at: float | None = None
        self.exit_idx = 0


# ---------------------------------------------------------------------------
# the line
# ---------------------------------------------------------------------------

def _axial_toward(a: float, b: float, f: float) -> float:
    """Move angle a toward b (period π) by fraction f."""
    d = (b - a + math.pi / 2) % math.pi - math.pi / 2
    return a + f * d


def grow_line(ctx, layers: list[Layer], *, frame, sheets: int, hand: str, hand_len: float, read_box, length_mm: float,
              route, pull: float, reach: float, gain: float, cross_gap: float, wall: float, step: float, drift_mm: float,
              capture: float, align: float, ride_mm: float, ride_gap: float, max_rides: int, listen_after: float,
              p_max: float, tau: float, pen: float, dW: float, W_max: float, tau_nib: float,
              wet: float, bead0: float, bead_grow: float, bead_max: float, pool_gap: float, ink: float,
              tau_dry: float, start_heading: float, share: str, extra_hands: dict, cause: str = "events") -> Mark:
    W_, H_ = frame
    sw = W_ / sheets
    rng = ctx.rng("stages")
    kA = hand_stream(ctx, hand, hand_len, read_box, step, drift_mm)
    A = Stream(kA)
    A.i = int(rng.integers(len(A.bends)))
    rt = np.asarray(route, float).reshape(-1, 2).copy()
    rt[:, 0] *= sw
    rt[:, 1] *= H_
    pos = rt[0].copy()
    wp = 1
    th = math.radians(start_heading)
    n = int(length_mm / step)

    # state
    W, W_t, phi, phi_t = pen, pen, math.radians(35.0), math.radians(35.0)
    spent, dry_at = 0.0, None
    src_cur, bend, bi = 0, A.next(), 0
    grammar_streams: dict[int, Stream] = {}
    hand_streams: dict[int, Stream] = {}
    ride: list | None = None                  # [points (k,2), cursor, layer]
    s = 0.0
    last_ride_end = -1e9
    pools: list[tuple[float, float, float]] = []
    last_pool = -1e9
    events: list = []
    out_p = [pos.copy()]
    out = {"W": [W], "phi": [phi], "src": [0.0]}
    lag = max(int(6.0 / step), 8)
    hist_tree, hist_n = None, 0
    edge_seen = int(np.clip(pos[0] // sw, 0, sheets - 1))

    def pick_source() -> tuple[int, np.ndarray]:
        """Next whole bend: a caught grammar / hand with its infection share, else the line's own hand."""
        best = None
        for L in layers:
            if L.caught_at is None:
                continue
            if L.effect == "grammar":
                p = p_max * (1.0 - math.exp(-(s - L.caught_at) / tau))
            elif L.effect == "hand":
                p = min(p_max, L.crossings * p_max / 3.0) * (1.0 - math.exp(-(s - L.caught_at) / tau))
            else:
                continue
            if best is None or p > best[0]:
                best = (p, L)
        q = 0.0
        if best is not None:
            p, L = best
            if share == "length":                # p is the share of LENGTH the caught grammar speaks
                other = grammar_streams.get(L.index) if L.effect == "grammar" else hand_streams.get(L.index)
                lA = float(np.mean([len(b) for b in A.bends]))
                lG = float(np.mean([len(b) for b in other.bends])) if other is not None else lA
                q = p * lA / max(p * lA + (1.0 - p) * lG, 1e-9)
            else:
                q = p
        if best is not None and rng.random() < q:
            L = best[1]
            if L.effect == "grammar":
                return 1, grammar_streams[L.index].next()
            return 3, hand_streams[L.index].next()
        return 0, A.next()

    for _ in range(n):
        if wp >= len(rt) - 1 and np.linalg.norm(pos - rt[-1]) < reach:
            break
        if ride is not None:
            q, c, L = ride
            nxt = q[c]
            d = nxt - pos
            if np.linalg.norm(d) > 1e-9:
                th = math.atan2(d[1], d[0])
            pos = nxt.copy()
            ride[1] += 1
            src_now = 2.0
            if ride[1] >= len(q):
                ride = None
                last_ride_end = s
                events.append((round(s, 2), f"leave:{L.index}", float(pos[0]), float(pos[1])))
                if L.caught_at is None:
                    L.caught_at = s
                st = grammar_streams.get(L.index)
                if st is not None:
                    st.seek(L.exit_idx)
                bend, bi, src_cur = np.zeros(1), 1, 0          # next bend chosen fresh
        else:
            if bi >= len(bend):
                src_cur, bend = pick_source()
                bi = 0
            k = gain * float(bend[bi]) if src_cur == 0 else float(bend[bi])
            bi += 1
            while wp < len(rt) - 1 and np.linalg.norm(pos - rt[wp]) < reach:
                wp += 1
                events.append((round(s, 2), f"waypoint:{wp}", float(pos[0]), float(pos[1])))
            tgt = rt[min(wp, len(rt) - 1)]
            th_t = math.atan2(tgt[1] - pos[1], tgt[0] - pos[0])
            dth = k - pull * math.sin(th - th_t)
            # walls: turn away from the paper's top / bottom and the row's ends
            m = wall
            for dist, away in ((pos[1], math.pi / 2), (H_ - pos[1], -math.pi / 2),
                               (pos[0], 0.0), (W_ - pos[0], math.pi)):
                if dist < m:
                    dth -= (m - dist) / m * 0.6 * math.sin(th - away)
            th += step * dth
            pos = pos + step * np.array([math.cos(th), math.sin(th)])
            src_now = float(src_cur)
        s += step

        # --- the control: the same effects keyed to the sheet index ---------------
        if cause == "edges":
            sheet_now = int(np.clip(pos[0] // sw, 0, sheets - 1))
            while sheet_now > edge_seen:
                edge_seen += 1
                events.append((round(s, 2), f"edge:{edge_seen}", float(pos[0]), float(pos[1])))
                k = 0
                for L in layers:
                    if L.effect not in ("grammar", "nib", "hand"):
                        continue
                    k += 1
                    if k != edge_seen:
                        continue
                    if L.effect == "grammar":
                        L.caught_at = s
                        ks = L.kstream[0] if L.kstream is not None else kappa(L.polys[0], step)
                        grammar_streams[L.index] = Stream(ks)
                    elif L.effect == "nib":
                        W_t = min(pen + 3 * dW, W_max)
                    else:
                        L.caught_at, L.crossings = s, 3
                        hand_streams[L.index] = Stream(hand_stream(ctx, L.hand, hand_len, read_box, step, drift_mm))
        # --- events the line meets -----------------------------------------
        if ride is None and cause == "events":
            for L in layers:
                if L.tree is None:
                    continue
                dist, j = L.tree.query(pos)
                if L.effect == "grammar":
                    if (dist < capture and L.rides < max_rides and s - last_ride_end > listen_after):
                        t = L.T[j]
                        cos = math.cos(th) * t[0] + math.sin(th) * t[1]
                        if abs(cos) >= align:
                            dirn = 1 if cos > 0 else -1
                            pid, i0 = int(L.pid[j]), int(L.idx[j])
                            poly = L.polys[pid]
                            kr = int(ride_mm / step)
                            ii = np.arange(i0, i0 + dirn * kr, dirn)
                            ii = ii[(ii >= 0) & (ii < len(poly))]
                            if len(ii) * step >= 0.4 * ride_mm:
                                tt = np.gradient(poly, axis=0)[ii]
                                tt /= np.linalg.norm(tt, axis=1, keepdims=True) + 1e-12
                                nv = np.column_stack([-tt[:, 1], tt[:, 0]])
                                side = 1.0 if np.dot(pos - poly[i0], nv[0]) >= 0 else -1.0
                                rq = poly[ii] + side * ride_gap * nv
                                # tangent entry over the first few mm
                                ne = min(int(2.5 / step), len(rq) - 1)
                                w = np.linspace(0, 1, ne + 1)[1:, None]
                                rq[:ne] = (1 - w) * (pos + np.outer(np.arange(1, ne + 1) * step,
                                                                    [math.cos(th), math.sin(th)])) + w * rq[:ne]
                                ride = [rq, 0, L]
                                L.rides += 1
                                # the river past the fragment's end, from where the line leaves it
                                L.exit_idx = int(ii[-1]) if dirn > 0 else int(len(poly) - 1 - ii[-1])
                                if L.index not in grammar_streams:
                                    if L.kstream is not None:
                                        ks = L.kstream[0] if dirn > 0 else L.kstream[1]
                                    else:
                                        ks = kappa(poly if dirn > 0 else poly[::-1], step)
                                    grammar_streams[L.index] = Stream(ks)
                                events.append((round(s, 2), f"ride:{L.index}", float(pos[0]), float(pos[1])))
                                break
                elif L.effect in ("nib", "hand"):
                    if dist < 0.6 * step + 0.05 and s - L.last_cross > cross_gap:
                        L.last_cross = s
                        L.crossings += 1
                        events.append((round(s, 2), f"cross:{L.index}", float(pos[0]), float(pos[1])))
                        if L.effect == "nib" and dry_at is None:
                            t = L.T[j]
                            phi_t = math.atan2(t[1], t[0]) % math.pi
                            W_t = min(W_t + dW, W_max)
                        if L.effect == "hand":
                            if L.caught_at is None:
                                L.caught_at = s
                            if L.index not in hand_streams:
                                hs = hand_stream(ctx, L.hand, hand_len, read_box, step, drift_mm)
                                hand_streams[L.index] = Stream(hs)

        # --- the line meets its own past (wet ink pools) ---------------------
        if len(out_p) - hist_n > 20 and len(out_p) > lag + 4:
            hist_n = len(out_p)
            hist_tree = cKDTree(np.asarray(out_p[:-lag]))
        if (dry_at is None and W >= wet and hist_tree is not None and s - last_pool > pool_gap):
            if hist_tree.query(pos)[0] < 0.6 * step + 0.05:
                d = min(bead0 * W * (1.0 + bead_grow) ** len(pools), bead_max)
                pools.append((float(pos[0]), float(pos[1]), float(d)))
                last_pool = s
                spent += math.pi * d * d / 4
                events.append((round(s, 2), "pool", float(pos[0]), float(pos[1])))

        # --- ink ----------------------------------------------------------------
        spent += max(W - pen, 0.0) * step
        if dry_at is None and spent > ink:
            dry_at = s
            W_t = pen
            events.append((round(s, 2), "dry", float(pos[0]), float(pos[1])))
        tau_w = tau_dry if dry_at is not None else tau_nib
        W += (W_t - W) * min(step / tau_w, 1.0)
        phi = _axial_toward(phi, phi_t, min(step / tau_nib, 1.0))

        out_p.append(pos.copy())
        out["W"].append(W)
        out["phi"].append(phi % math.pi)
        out["src"].append(src_now)

    P_ = np.asarray(out_p)
    Wc = np.asarray(out["W"])
    r = np.where(Wc > pen + 0.08, 1.0, 0.0)
    seg = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))]
    ch = {"r": r, "phi": np.asarray(out["phi"]), "W": np.maximum(Wc, pen), "M": np.full(len(P_), 9.0),
          "src": np.asarray(out["src"]), "series_u": seg / max(seg[-1], 1e-9)}
    meta = {"voices": [hand], "events": events, "pools": [list(p) for p in pools], "dry_at": dry_at,
            "ink_spent": round(spent, 1), "length_mm": float(seg[-1]), "sheets": int(sheets),
            "library": [{"kind": "hand", "id": hand}]}
    return Mark(P_, ch, meta)


LINE_PARAMS = [
    P("hand", "ref", "ingres", "the line's own hand (its bends, drift taken out)", kind="hand"),
    P("hand_len", "float", 12.0, "length of the hand line its bends are read from, R", min=1.0, max=12.0),
    P("read_box", "floats", [0.0, 0.0, 140.0, 200.0], "x0 y0 w h (mm) the hand line is read in (κ scale)"),
    P("length", "float", 2600.0, "the line, mm", min=50.0, max=12000.0),
    P("route", "floats", [0.3, 0.5, 4.7, 0.5], "waypoints (x in sheets, y share): roughly where; the line "
      "ends at the last one (or at `length`)"),
    P("pull", "float", 0.05, "pull of the heading toward the next waypoint, per mm", min=0.0, max=1.0),
    P("reach", "float", 25.0, "a waypoint is passed within this, mm", min=1.0, max=200.0),
    P("gain", "float", 1.0, "curvature gain on the line's own hand (< 1 calmer)", min=0.1, max=4.0),
    P("cross_gap", "float", 12.0, "crossings of one layer count once within this many mm of line", min=0.5,
      max=300.0),
    P("wall", "float", 14.0, "the line turns away within this distance of the row's outer edges, mm",
      min=0.0, max=60.0),
    P("step", "float", 0.25, "integration step, mm", min=0.1, max=1.0),
    P("drift_mm", "float", 40.0, "the hand's slow heading drift removed over this, mm", min=5.0, max=200.0),
    P("capture", "float", 3.0, "a grammar layer this near (mm) and aligned takes the line", min=0.2, max=20.0),
    P("align", "float", 0.6, "|cos| needed to be taken", min=0.0, max=1.0),
    P("ride_mm", "float", 30.0, "ride length beside a grammar layer, mm", min=2.0, max=300.0),
    P("ride_gap", "float", 0.9, "ride this far beside the layer, mm", min=0.0, max=5.0),
    P("max_rides", "int", 1, "rides per grammar layer", min=0, max=10),
    P("listen_after", "float", 20.0, "no new ride for this many mm after one, mm", min=0.0, max=500.0),
    P("p_max", "float", 0.9, "a caught grammar's final share of the bends", min=0.0, max=1.0),
    P("tau", "float", 160.0, "how fast a caught grammar takes the bends, mm", min=1.0, max=3000.0),
    P("share", "choice", "bends", "p counts bends (a long own bend outweighs many short caught ones) | length "
      "(p is the share of the line's length)", choices=("bends", "length")),
    P("pen", "float", 0.35, "pen, mm (the wire)", min=0.1, max=1.0),
    P("dW", "float", 0.7, "nib width added per crossing of a nib layer, mm", min=0.0, max=4.0),
    P("W_max", "float", 3.2, "widest nib, mm", min=0.2, max=8.0),
    P("tau_nib", "float", 30.0, "width / angle approach their target over this, mm", min=1.0, max=500.0),
    P("wet", "float", 1.4, "nib width from which a self-crossing pools a bead, mm", min=0.2, max=8.0),
    P("bead0", "float", 1.8, "first bead diameter, × nib width", min=0.5, max=6.0),
    P("bead_grow", "float", 0.18, "each bead this much bigger than the last", min=0.0, max=1.0),
    P("bead_max", "float", 9.0, "largest bead, mm", min=1.0, max=30.0),
    P("pool_gap", "float", 6.0, "beads at least this far apart along the line, mm", min=0.5, max=100.0),
    P("ink", "float", 900.0, "ink budget (mm² of nib excess + beads); spent → dry", min=1.0, max=1e6),
    P("tau_dry", "float", 12.0, "how fast the nib dries to a hairline, mm", min=0.5, max=500.0),
    P("start_heading", "float", 0.0, "degrees", min=-180.0, max=180.0),
]


@voice("stages_line", params=LINE_PARAMS,
       doc="a line in curvature space, its own hand's bends steered by a route; alone it meets nothing "
           "(arranger stages_row gives it event layers to meet)")
def stages_line(ctx, **p):
    W, H = ctx.frame
    return [grow_line(ctx, [], frame=(W, H), sheets=1, length_mm=p.pop("length"), extra_hands={}, **p)]


# ---------------------------------------------------------------------------
# the arranger
# ---------------------------------------------------------------------------

def _grammar_kstream(ctx, layer_marks: list[Mark], spec: dict, step: float):
    """For the far-view river: the WHOLE frozen stem's bends at the fragment's
    scale, (downstream from the fragment's start, upstream from its end), so a
    line that leaves the fragment goes on with the river past the paper."""
    if spec.get("id") != "oehlen_found_river" or not layer_marks:
        return None
    from .arrangers_oehlen_found import stem  # noqa: PLC0415
    fitm = layer_marks[0].meta.get("fit") or {}
    sc = float(fitm.get("scale", 0.0))
    if sc <= 0:
        return None
    _seg, _wm, q = stem(ctx, spec.get("stems"), spec.get("tile", "SB19"), int(spec.get("rank", 0)))
    n = min(4 * int(spec.get("span_w", 1600)), len(q))
    a = int(float(spec.get("start", 0.0)) * max(len(q) - n, 0))
    q = np.asarray(q, float) * sc
    fwd = kappa(q[a:], step)                       # downstream from the fragment's start
    back = kappa(q[:a + n][::-1], step)            # upstream from the fragment's end
    return fwd, back


@arranger("stages_row", params=[
    P("sheets", "int", 5, "sheets in the row (sheet width = frame W / sheets)", min=1, max=12),
    P("boxes", "floats", [], "per event part (parts 1…): x0, y0, w, h in SHEETS (x, w) and height shares (y, h)"),
    P("effects", "str", "grammar,nib", "per event part: grammar | nib | hand | none (comma list)"),
    P("inks", "str", "black,blue,red", "Flexoki ink per part (pen colours for previews), comma list"),
    P("cause", "choice", "events", "events: the line changes where it meets the layers | edges: the CONTROL — "
      "the same effects applied at sheet edges 1, 2, … in layer order, whatever the line meets",
      choices=("events", "edges")),
], doc="a row of sheets: part 0 (voice stages_line) is ONE line that changes only where it meets the other parts")
def stages_row(ctx, parts, *, sheets, boxes, effects, inks, cause):
    W, H = ctx.frame
    sw = W / sheets
    eff = [e.strip() for e in effects.split(",") if e.strip()]
    bad = [e for e in eff if e not in EFFECTS]
    if bad:
        raise ValueError(f"stages_row: unknown effect(s) {bad}; choose from {EFFECTS}")
    b = list(boxes)
    out: list[Mark] = []
    layers: list[Layer] = []
    lp = parts[0].spec["voice"]
    if lp["id"] != "stages_line":
        raise ValueError("stages_row: part 0 must be voice stages_line")
    step = float(lp["step"])
    for j, p in enumerate(parts[1:]):
        if 4 * j + 3 < len(b):
            x0, y0, w, h = b[4 * j: 4 * j + 4]
            box = (x0 * sw, y0 * H, w * sw, h * H)
        else:
            box = ctx.box
        ms = p.run(box)
        out += ms
        e = eff[j] if j < len(eff) else "none"
        vs = p.spec["voice"]
        ks = _grammar_kstream(p.ctx("voice", vs["id"], box), ms, vs, step) if e == "grammar" else None
        hand = vs.get("hand") if e == "hand" else None
        layers.append(Layer(p.index, e, ms, step, ks, hand))
    params = {k: v for k, v in lp.items() if k not in ("id", "length")}
    line = grow_line(parts[0].ctx("voice", "stages_line", ctx.box), layers, frame=(W, H), sheets=sheets,
                     length_mm=float(lp["length"]), extra_hands={}, cause=cause, **params)
    line = line.evolve(meta={"part": 0, "voice_id": "stages_line",
                             "layers": [{"part": L.index, "effect": L.effect, "rides": L.rides,
                                         "crossings": L.crossings} for L in layers]})
    return [*parts[0].modulate([line], ctx.box), *out]


# ---------------------------------------------------------------------------
# the renderer
# ---------------------------------------------------------------------------

def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    k = np.flatnonzero(mask)
    if not len(k):
        return []
    parts = np.split(k, np.flatnonzero(np.diff(k) > 1) + 1)
    return [(int(p[0]), int(p[-1])) for p in parts]


def nib_lanes(pts: np.ndarray, W: np.ndarray, phi: np.ndarray, pen: float, pitch: float) -> list[np.ndarray]:
    """A broad nib inked line-built: the nib's footprint at each point is the
    segment of length W at angle phi; its projection across the stroke is
    |sin(heading − phi)|·W. Lanes = parallel offsets of the centreline at
    `pitch`·pen across that width, joined into ONE boustrophedon path per run
    (contiguous lines along the stroke, never hatching)."""
    t = np.gradient(pts, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    nv = np.column_stack([-t[:, 1], t[:, 0]])
    hd = np.arctan2(t[:, 1], t[:, 0])
    half = 0.5 * np.maximum(np.abs(np.sin(hd - phi)) * W, pen)
    half = gaussian_filter1d(half, 3.0, mode="nearest")
    nl = int(max(np.ceil(2 * half.max() / (pitch * pen)), 1))
    if nl <= 1:
        return [pts]
    path = []
    for i in range(nl + 1):
        f = -1.0 + 2.0 * i / nl
        off = np.clip(f * half - np.sign(f) * 0.5 * pen, -half, half) if nl > 1 else 0 * half
        lane = pts + nv * off[:, None]
        path.append(lane if i % 2 == 0 else lane[::-1])
    return [np.vstack(path)]


@renderer("stages_ink", params=[
    P("pen", "float", 0.35, "pen, mm", min=0.05, max=2.0),
    P("pitch", "float", 0.85, "lane / spiral spacing, × pen", min=0.3, max=3.0),
    P("wobble", "float", 0.06, "bead roundness noise", min=0.0, max=0.3),
], doc="the stages line: wire where dry, a line-built broad nib (W, phi) where wet, round line-built beads "
       "at its pools", reach=lambda p: 5.0)
def stages_ink(ctx, marks, *, pen, pitch, wobble):
    from .dev_beads import blob, solid  # noqa: PLC0415
    out: list[Ink] = []
    rng = ctx.rng("beads")
    for m in marks:
        if len(m) < 2:
            continue
        pts = np.asarray(m.points)
        Wc = np.asarray(m["W"])
        phi = np.asarray(m["phi"])
        wet = Wc > pen * 1.6
        # the wire runs the whole line (the nib's lanes ride on it)
        out.append(Ink(pts, closed=False, filled=False, pen=pen, meta={"role": "line"}))
        for a, z in _runs(wet):
            if z - a < 4:
                continue
            a0, z0 = max(a - 1, 0), min(z + 2, len(pts))
            for q in nib_lanes(pts[a0:z0], Wc[a0:z0], phi[a0:z0], pen, pitch):
                out.append(Ink(q, closed=False, filled=False, pen=pen, meta={"role": "nib"}))
        for x, y, d in m.meta.get("pools", []):
            ring = blob(np.array([x, y]), d / 2, rng, wobble)
            for q, closed, filled in solid(ring, pen, pitch):
                out.append(Ink(q, closed=closed, filled=filled, pen=pen, meta={"role": "bead"}))
    return out


@renderer("stages_layer", params=[P("pen", "float", 0.3, "pen, mm", min=0.05, max=2.0)],
          doc="an event layer: one wire per mark", reach=lambda p: 0.5 * p["pen"])
def stages_layer(ctx, marks, *, pen):
    return [Ink(m.points, closed=False, filled=False, pen=pen, meta={"role": "layer"}) for m in marks if len(m) >= 2]


# ---------------------------------------------------------------------------
# run + cut (the series machinery)
# ---------------------------------------------------------------------------

def run_stages(recipe: dict):
    """(the row as one Sheet, its sheets) — sheet k's recipe is {"series": recipe, "sheet": k}."""
    from .arrangers_series import cut  # noqa: PLC0415
    from .core import run as kit_run  # noqa: PLC0415
    strip = kit_run(recipe)
    return strip, cut(strip, int(strip.recipe["arranger"]["sheets"]))


def run_stage_sheet(sheet_recipe: dict):
    """Rebuild one sheet from {"series": recipe, "sheet": k}."""
    _, sheets = run_stages(sheet_recipe["series"])
    return sheets[int(sheet_recipe["sheet"])]
