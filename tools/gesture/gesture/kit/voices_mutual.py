"""Round 13, thread I-b `mutual` — mutual awareness among regimes.

Ian (2026-10-18): "It really seems like the interlocking regimes are aware of
one another, the way an improvisatory painter like oehlen would approach
stuff." In found ground the found layer is printed first and stays passive;
here NO regime is passive. Four regimes draw one sheet together in
interleaved turns (a tick = every regime takes one turn, in the order graph,
river, bold, wire), and every turn reads what is on the paper so far.

    river   a far view of a real stem (GRWL SB19, frozen in the library). Its
            meander is kept whole: every stem point is held in the stem's own
            valley frame (s along a smoothed axis, u along and n across it)
            and re-laid along a COURSE the regime steers. On its own the
            course follows the stem's own valley bends and the way it flows.
    graph   a seismograph needle along a band; x is the clock. It writes the
            pre-event noise of a real record (FDSN IU.ANMO LHZ, local corpus)
            and, when cued, the arrival of a real earthquake (a different one
            each time).
    bold    a bold learned hand (default `dance_thrusting`). Each of its lines
            is a WHOLE line of that hand (`hybrid.drift_line`), never steered
            chunk by chunk; awareness only decides where a line is placed and
            turned (room on the paper, off the blank, ending where the river
            can reach), when it stops (a held knot), and what it does next.
    wire    a slow hairline in another hand (default `trail_slime`), whole
            lines too.

Awareness is a sparse table of DISCRETE events and responses, never a field:

    bold  stop    > river  turns its course to the knot and wraps it (an island)
    river arrive  > bold   re-enters from its knot, RIDES the river 0.9 mm beside
                           it, leaves at a tangent into a new whole line;
                           when tired (appetite), it refuses and turns its back
    bold  turn    > graph  plays an earthquake arrival at the clock
    graph burst   > wire   wakes, crosses to the burst, RIDES the trace (as a
                           mis-registered second print), leaves for the blank
    wire  ride    > graph  lifts its needle while touched (a gap in the trace)
    bold  stop    > wire   comes to look (if free); its refusal keeps it off
                           bold ink: the rest of its line turns away (`refuse`)
    ignored       river ignores the wire; graph ignores river and wire's lines;
                  a busy, ringing or spent regime lets its cue pass (logged)

Every point carries channel `tick` (the turn it was drawn in) and `neg` (0
own, 1 riding another regime), so a process strip can show the paper at any
turn. The event board (who fired what, who answered, refused or ignored) is
in `marks[0].meta["mutual"]` with the regimes' positions per turn. Marks carry
meta ink / pen / of_role, so the `oehlen_found_ink` renderer and
`arrangers_oehlen_found.render_colour` draw them. Use with the `single`
arranger; the voice places everything in sheet mm.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

from .. import hybrid as hy
from .core import P, Mark, channel_kind, voice

channel_kind("tick", "nearest")
channel_kind("neg", "nearest")

REGIMES = ("graph", "river", "bold", "wire")          # turn order within a tick
QUAKES = ("tohoku2011", "maule2010", "sumatra2004", "nepal2015")
FDSN = Path(__file__).resolve().parents[4] / ".local/gesture/corpus/earth/fdsn-particle-motion"


# ---------------------------------------------------------------------------
# polyline helpers
# ---------------------------------------------------------------------------

def arcl(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float)
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))] if len(p) > 1 else np.zeros(len(p))


def resample(p: np.ndarray, step: float) -> np.ndarray:
    p = np.asarray(p, float)
    s = arcl(p)
    if len(p) < 2 or s[-1] <= 0:
        return p.copy()
    n = max(int(round(s[-1] / step)), 1)
    t = np.linspace(0.0, s[-1], n + 1)
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def tangents(p: np.ndarray, k: int = 3) -> np.ndarray:
    n = len(p)
    if n < 2:
        return np.tile([1.0, 0.0], (n, 1))
    i = np.arange(n)
    d = p[np.minimum(i + k, n - 1)] - p[np.maximum(i - k, 0)]
    return d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)


def bridge(a, ta, b, tb, step: float) -> np.ndarray:
    """Cubic Bézier a (heading ta) → b (heading tb), interior points only."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = float(np.linalg.norm(b - a))
    if d < 1e-6:
        return np.empty((0, 2))
    h = d / 2.6
    c1, c2 = a + np.asarray(ta) * h, b - np.asarray(tb) * h
    n = max(int(d / step) + 2, 3)
    t = np.linspace(0, 1, n)[1:-1, None]
    return ((1 - t) ** 3) * a + 3 * ((1 - t) ** 2) * t * c1 + 3 * (1 - t) * t * t * c2 + t ** 3 * b


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def beside(seg: np.ndarray, gap: float, side: float, smooth: float = 0.0) -> np.ndarray:
    """seg offset `gap` mm to one side (the ride stays visible beside what it rides)."""
    if len(seg) < 3 or gap <= 0:
        return seg.copy()
    t = tangents(seg, 3)
    if smooth > 0:
        t = gaussian_filter1d(t, smooth, axis=0, mode="nearest")
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    return seg + side * gap * np.c_[-t[:, 1], t[:, 0]]


def heading_change(p: np.ndarray, i: int, w: int) -> float:
    a = p[max(i - w, 0)]
    b = p[i]
    c = p[min(i + w, len(p) - 1)]
    u, v = b - a, c - b
    if np.linalg.norm(u) < 1e-9 or np.linalg.norm(v) < 1e-9:
        return 0.0
    return abs(wrap_angle(math.atan2(v[1], v[0]) - math.atan2(u[1], u[0])))


# ---------------------------------------------------------------------------
# the board: discrete events, and who listens to what
# ---------------------------------------------------------------------------

RELATIONS = {
    "river": {("bold", "stop"): "wrap"},
    "bold": {("river", "arrive"): "ride"},
    "graph": {("bold", "turn"): "burst", ("wire", "ride"): "lift"},
    "wire": {("graph", "burst"): "wake", ("bold", "stop"): "approach"},
}
# the relations that are deliberately absent are indifference (logged once, as a rule)
IGNORES = [("river", "wire", "crosses the wire as if it were not there"),
           ("graph", "river", "never registers the river"),
           ("wire", "bold", "refuses: keeps clear of bold ink, turns away")]


class Board:
    def __init__(self):
        self.events: list[dict] = []
        self.seen: dict[str, int] = {r: 0 for r in REGIMES}

    def post(self, t: int, src: str, kind: str, pos, **info) -> dict:
        e = {"id": len(self.events), "t": int(t), "src": src, "kind": kind,
             "pos": [round(float(pos[0]), 2), round(float(pos[1]), 2)], "answers": [], **info}
        self.events.append(e)
        return e

    def inbox(self, who: str) -> list[dict]:
        """Events posted since `who`'s last turn that it listens to."""
        new = self.events[self.seen[who]:]
        self.seen[who] = len(self.events)
        rel = RELATIONS.get(who, {})
        return [e for e in new if (e["src"], e["kind"]) in rel]

    def answer(self, e: dict, who: str, how: str, t: int, **info):
        e["answers"].append({"by": who, "how": how, "t": int(t), **info})


# ---------------------------------------------------------------------------
# paper: what has been drawn so far (every turn reads it)
# ---------------------------------------------------------------------------

class Paper:
    def __init__(self):
        self.lines: dict[str, list[list]] = {r: [] for r in REGIMES}   # regime → [[pts list], ...] (open lines)
        self.ticks: dict[str, list[list]] = {r: [] for r in REGIMES}
        self.negs: dict[str, list[list]] = {r: [] for r in REGIMES}
        self._tree: dict[str, tuple] = {}

    def new_line(self, who: str):
        self.lines[who].append([])
        self.ticks[who].append([])
        self.negs[who].append([])

    def add(self, who: str, pts: np.ndarray, t: int, neg: float = 0.0):
        if not len(pts):
            return
        if not self.lines[who]:
            self.new_line(who)
        self.lines[who][-1].extend(np.asarray(pts, float).tolist())
        self.ticks[who][-1].extend([t] * len(pts))
        self.negs[who][-1].extend([neg] * len(pts))
        self._tree.pop(who, None)

    def points(self, who: str) -> np.ndarray:
        a = [np.asarray(l) for l in self.lines[who] if len(l)]
        return np.vstack(a) if a else np.zeros((0, 2))

    def tree(self, who: str):
        if who not in self._tree:
            p = self.points(who)
            self._tree[who] = (cKDTree(p) if len(p) > 2 else None, p)
        return self._tree[who]

    def near(self, who: str, q: np.ndarray, r: float) -> np.ndarray:
        """(len(q),) bool: q within r of `who`'s ink."""
        tr, _ = self.tree(who)
        if tr is None:
            return np.zeros(len(q), bool)
        return tr.query(q, k=1)[0] < r


# ---------------------------------------------------------------------------
# a learned hand's OWN line, whole (its grammar is never steered chunk by chunk)
# ---------------------------------------------------------------------------

RESEARCH = (1000.0, 1200.0)


def own_line(g, rng, length_R: float, k_mm: float, step: float) -> np.ndarray:
    """One whole line of a hand (`hybrid.drift_line` with that hand alone, the
    `hand` voice's growth), in mm at k_mm per research px, starting at the
    origin with its first heading along +x."""
    st, _ = hy.drift_line([g], rng, total=float(length_R), size=RESEARCH)
    p = resample((np.asarray(st.points, float) - st.points[0]) * k_mm, step)
    if len(p) < 4:
        return p
    t0 = p[min(int(3.0 / step), len(p) - 1)] - p[0]
    a = -math.atan2(t0[1], t0[0])
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    return p @ R.T


def pose(line: np.ndarray, start, heading: float) -> np.ndarray:
    R = np.array([[math.cos(heading), -math.sin(heading)], [math.sin(heading), math.cos(heading)]])
    return line @ R.T + np.asarray(start, float)


def plan_line(g, rng, *, n_cand: int, length_R, k_mm, step, start, headings, score):
    """The best of n_cand whole lines × headings by `score(points) -> float`
    (the regime reads the paper: room, blank, crowding, where it wants to go)."""
    best = None
    for c in range(n_cand):
        own = own_line(g, rng, length_R, k_mm, step)
        if len(own) < 4:
            continue
        for h in headings:
            q = pose(own, start, h)
            sc = float(score(q))
            if best is None or sc < best[0]:
                best = (sc, q, h)
    return best


def knot(pos, heading, size, rng, step):
    """A held stop: the line winds once on the spot (a round bead of line)."""
    turns = 1.0 + 0.5 * rng.random()
    n = max(int(turns * 2 * math.pi * size / step), 16)
    side = 1.0 if rng.random() < 0.5 else -1.0
    a = np.linspace(0, turns * 2 * math.pi, n)
    r = size * (0.6 + 0.4 * np.sin(np.linspace(0, math.pi, n)))
    c = np.asarray(pos) + size * np.array([math.cos(heading + side * math.pi / 2), math.sin(heading + side * math.pi / 2)])
    ang0 = heading - side * math.pi / 2
    pts = c + np.column_stack([r * np.cos(ang0 + side * a), r * np.sin(ang0 + side * a)])
    pts = pts - pts[0] + pos
    return pts[1:]


class Pen:
    """A regime's pen: a queue of planned pieces (points, neg) drawn `speed`
    mm per turn. Everything a turn draws goes on the paper with its tick."""

    def __init__(self, who: str, step: float):
        self.who, self.step = who, float(step)
        self.queue: list[list] = []
        self.pos = None
        self.heading = 0.0

    def plan(self, pieces, replace: bool = True):
        if replace:
            self.queue = []
        for pts, neg in pieces:
            if len(pts):
                self.queue.append([np.asarray(pts, float), float(neg)])

    def own_ahead(self, mm: float) -> np.ndarray:
        """The next `mm` of what is planned (any kind)."""
        out, s = [], 0.0
        for pts, _ in self.queue:
            out.append(pts)
            s += float(arcl(pts)[-1]) if len(pts) > 1 else 0.0
            if s >= mm:
                break
        if not out:
            return np.zeros((0, 2))
        a = np.vstack(out)
        k = int(np.searchsorted(arcl(a), mm))
        return a[: max(k, 2)]

    def draw(self, mm: float, t: int, paper: "Paper") -> list[tuple[np.ndarray, float]]:
        """Draw up to `mm` of the queue. Returns the pieces drawn this turn."""
        drawn = []
        left = mm
        while left > 1e-6 and self.queue:
            pts, neg = self.queue[0]
            prev = self.pos if self.pos is not None else pts[0]
            s = arcl(np.vstack([prev[None, :], pts]))[1:]
            k = max(int(np.searchsorted(s, left, side="right")), 1)
            take = pts[:k]
            if len(take):
                paper.add(self.who, take, t, neg)
                drawn.append((take, neg))
                if len(take) >= 2:
                    d = take[-1] - take[-2]
                    if np.linalg.norm(d) > 1e-9:
                        self.heading = math.atan2(d[1], d[0])
                self.pos = take[-1].copy()
                left -= float(s[k - 1])
            if k >= len(pts):
                self.queue.pop(0)
            else:
                self.queue[0][0] = pts[k:]
                break
        return drawn


# ---------------------------------------------------------------------------
# the river regime: a found meander re-laid along a steered course
# ---------------------------------------------------------------------------

def valley_frame(q_mm: np.ndarray, sigma_mm: float, ds: float = 0.25):
    """The stem in its own valley frame: a heavily smoothed axis; every stem
    point as (s along the axis, n across it); the axis' own curvature κ(s)."""
    q = resample(q_mm, 0.2)
    sig = max(sigma_mm / 0.2, 1.0)
    a = resample(gaussian_filter1d(q, sig, axis=0, mode="nearest"), ds)
    sa = arcl(a)
    ta = tangents(a, 2)
    # s along the axis: the nearest projection, smoothed and made monotone (a free nearest search jumps
    # across a loop's medial line; a jump in s tears the meander as soon as the axis is re-curved). The
    # point is then kept EXACTLY by both its components in the axis frame at that s: u along, n across.
    _, j = cKDTree(a).query(q)
    s = np.maximum.accumulate(gaussian_filter1d(sa[j], 2.0 * sig, mode="nearest"))
    ax = np.column_stack([np.interp(s, sa, a[:, 0]), np.interp(s, sa, a[:, 1])])
    tt = np.column_stack([np.interp(s, sa, ta[:, 0]), np.interp(s, sa, ta[:, 1])])
    tt /= np.maximum(np.linalg.norm(tt, axis=1, keepdims=True), 1e-9)
    v = q - ax
    u = tt[:, 0] * v[:, 0] + tt[:, 1] * v[:, 1]
    n = tt[:, 0] * v[:, 1] - tt[:, 1] * v[:, 0]
    h = np.unwrap(np.arctan2(ta[:, 1], ta[:, 0]))
    kap = gaussian_filter1d(np.gradient(h, sa), 4.0)
    return {"s": s, "u": u, "n": n, "sa": sa, "kap": kap, "h0": float(h[0])}


class River:
    def __init__(self, ctx, frame_vf, rng, *, start, heading, speed, kmax, nat, wrap_r, wrap_deg, box, blanks,
                 step, lag):
        self.vf = frame_vf
        self.rng = rng
        self.speed = float(speed)
        self.kmax = float(kmax)
        self.nat = float(nat)
        self.wrap_r = float(wrap_r)
        self.wrap_deg = float(wrap_deg)
        self.box = box
        self.blanks = blanks
        self.step = float(step)
        self.lag = float(lag)
        self.ds = 0.25
        self.axis = [np.asarray(start, float)]
        self.theta = float(heading)
        self.S = 0.0
        self.i_emit = int(np.argmax(self.vf["s"] >= 0.0))
        self.order = np.arange(len(self.vf["s"]))
        self.target = None          # the event being answered
        self.orbit = 0.0
        self.orbit_side = 1.0
        self.done = False
        self.Smax = float(self.vf["sa"][-1])
        self.rush = 1.0
        self.kfold = 1.0 / (1.3 * max(float(np.quantile(np.hypot(self.vf["n"], self.vf["u"]), 0.99)), 1e-6))
        self.base = float(heading)
        self.flow = 0.0

    def _steer(self, p) -> float:
        """Desired heading change per mm (bounded by kmax)."""
        want = None
        if self.target is not None:
            c = np.asarray(self.target["pos"], float)
            d = c - p
            dist = float(np.linalg.norm(d))
            if dist < self.wrap_r * 1.5 or self.orbit > 0:
                # orbit: tangent of the circle around the knot, radial correction toward wrap_r
                rad = math.atan2(-d[1], -d[0])                 # from centre to p
                tang = rad + self.orbit_side * math.pi / 2
                corr = (dist - self.wrap_r) / self.wrap_r
                want = tang + self.orbit_side * max(min(corr, 1.0), -1.0) * 0.9
            else:
                want = math.atan2(d[1], d[0])
                # approach on a tangent line to the circle (so the wrap starts smoothly)
                off = math.asin(min(self.wrap_r / max(dist, 1e-6), 1.0))
                want += -self.orbit_side * off
        if want is None:
            # its own way: the valley's bends, and a slow memory of the way it flows (downslope)
            gain = wrap_angle(self.base - self.theta) * self.flow
        else:
            gain = wrap_angle(want - self.theta) * 0.35
        # the sheet and the blank are known to every regime: soft avoidance
        x0, y0, w, h = self.box
        mg = 22.0
        look = p + 18.0 * np.array([math.cos(self.theta), math.sin(self.theta)])
        push = np.zeros(2)
        push[0] += max(x0 + mg - look[0], 0) - max(look[0] - (x0 + w - mg), 0)
        push[1] += max(y0 + mg - look[1], 0) - max(look[1] - (y0 + h - mg), 0)
        for b in self.blanks:
            d = look - b[:2]
            L = float(np.linalg.norm(d))
            if L < b[2] + 12:
                push += d / max(L, 1e-6) * (b[2] + 12 - L)
        if np.any(push):
            want_e = math.atan2(push[1], push[0])
            k = 0.12 if self.target is not None else 0.5          # answering a call outranks keeping off the edge
            gain += wrap_angle(want_e - self.theta) * min(float(np.linalg.norm(push)) / 10.0, 1.0) * k
        return max(min(gain, self.kmax), -self.kmax)

    def turn(self, t, board: Board, paper: Paper, log: list):
        if self.done:
            for e in board.inbox("river"):
                board.answer(e, "river", "ignored (the river has run out)", t)
            return
        for e in board.inbox("river"):
            if self.target is None:
                self.target = e
                c = np.asarray(e["pos"], float)
                p = self.axis[-1]
                d = c - p
                cross = math.cos(self.theta) * d[1] - math.sin(self.theta) * d[0]
                self.orbit_side = 1.0 if cross > 0 else -1.0
                self.orbit = 0.0
                board.answer(e, "river", "turns its course toward the knot", t)
            else:
                board.answer(e, "river", "ignored (busy wrapping another)", t)
        # advance the course
        n = int(round(self.speed * (self.rush if self.target is not None else 1.0) / self.ds))
        for _ in range(n):
            if self.S + self.ds >= self.Smax:
                self.done = True
                break
            p = self.axis[-1]
            k_nat = float(np.interp(self.S, self.vf["sa"], self.vf["kap"])) * self.nat
            st = self._steer(p)
            dk = k_nat * (0.15 if self.target is not None else 1.0) + st
            dk = max(min(dk, self.kfold), -self.kfold)      # never tighter than the meander is wide: no folds
            self.theta += dk * self.ds
            q = p + self.ds * np.array([math.cos(self.theta), math.sin(self.theta)])
            if self.target is not None:
                c = np.asarray(self.target["pos"], float)
                if np.linalg.norm(q - c) < self.wrap_r * 1.6:
                    a0 = math.atan2(*(p - c)[::-1])
                    a1 = math.atan2(*(q - c)[::-1])
                    self.orbit += abs(wrap_angle(a1 - a0))
                # it has gone round the knot, and leaves it the moment it faces downstream again
                if math.degrees(self.orbit) >= self.wrap_deg and (
                        abs(wrap_angle(self.theta - self.base)) < math.radians(75) or math.degrees(self.orbit) >= 400):
                    ev = board.post(t, "river", "arrive", q, wrapped=int(self.target["id"]))
                    board.answer(self.target, "river", "wrapped the knot", t, arrive=ev["id"])
                    self.target = None
                    self.orbit = 0.0
            self.axis.append(q)
            self.S += self.ds
        self._emit(t, paper, final=self.done)

    def _emit(self, t, paper: Paper, final=False):
        s, nn = self.vf["s"], self.vf["n"]
        lim = self.S if final else self.S - self.lag
        if lim <= 0:
            return
        A = np.asarray(self.axis)
        sa = np.arange(len(A)) * self.ds
        T = tangents(A, 2)
        N = np.c_[-T[:, 1], T[:, 0]]
        i0 = self.i_emit
        i1 = i0
        while i1 < len(s) and s[i1] <= lim:
            i1 += 1
        if i1 <= i0:
            return
        ss = s[i0:i1]
        ax = np.column_stack([np.interp(ss, sa, A[:, 0]), np.interp(ss, sa, A[:, 1])])
        nr = np.column_stack([np.interp(ss, sa, N[:, 0]), np.interp(ss, sa, N[:, 1])])
        tg = np.column_stack([nr[:, 1], -nr[:, 0]])
        pts = ax + nr * nn[i0:i1, None] + tg * self.vf["u"][i0:i1, None]
        paper.add("river", pts, t)
        self.i_emit = i1


# ---------------------------------------------------------------------------
# the graph regime: a seismograph needle; x is the clock
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def quake(name: str, station: str = "IU.ANMO"):
    """(pre-event noise, arrival) of one FDSN vertical record (LHZ, 1 Hz),
    demeaned; both in counts. Research only: reads the local corpus."""
    f = FDSN / f"fdsn-{name}-{station}" / f"fdsn-{name}-{station}_counts.npz"
    x = np.load(f)["LHZ"].astype(float)
    x = x - np.median(x[:400])
    a = np.abs(x)
    env = np.array([a[i:i + 30].max() for i in range(0, len(a), 30)])
    noise = float(np.median(env[:12]))
    first = int(np.argmax(env > 8 * noise)) * 30
    pre = x[: max(first - 60, 120)]
    arr = x[first: first + 2400]
    return pre, arr


class Graph:
    def __init__(self, rng, *, x0, x1, y, T, amp, noise_amp, burst_ticks, refractory, quakes, step, decim):
        self.rng = rng
        self.x0, self.x1, self.y = float(x0), float(x1), float(y)
        self.dx = (self.x1 - self.x0) / T
        self.amp, self.noise_amp = float(amp), float(noise_amp)
        self.burst_ticks = int(burst_ticks)
        self.refractory = int(refractory)
        self.quakes = list(quakes)
        self.step = float(step)
        self.decim = int(decim)
        self.x = self.x0
        self.queue: list[float] = []         # pending burst samples (mm offsets), one per `step` of x
        self.cool = 0
        self.nq = 0
        self.lifted = 0
        pre, _ = quake(self.quakes[0])
        self.pre = gaussian_filter1d(pre, 1.2) / max(np.quantile(np.abs(pre), 0.98), 1e-9)
        self.pi = int(rng.integers(len(self.pre)))
        self.pending_burst = None

    def _burst(self, k: int) -> np.ndarray:
        _, arr = quake(self.quakes[k % len(self.quakes)])
        n = int(self.burst_ticks * self.dx / self.step)
        a = arr[: n * self.decim]
        a = gaussian_filter1d(a, self.decim * 0.5)[:: self.decim][:n]
        a = a / max(np.abs(a).max(), 1e-9)
        ramp = np.clip(np.arange(len(a)) / 4.0, 0, 1)
        return a * ramp * self.amp

    def turn(self, t, board: Board, paper: Paper, log: list):
        for e in board.inbox("graph"):
            if e["src"] == "wire":
                self.lifted = max(self.lifted, int(e.get("ticks", 3)))
                board.answer(e, "graph", "the needle lifts while it is touched", t)
            elif self.queue or self.cool > 0:
                board.answer(e, "graph", "ignored (still ringing / refractory)", t)
            else:
                b = self._burst(self.nq)
                self.queue = list(b)
                self.b_i = 0
                self.peak_i = int(np.argmax(np.abs(b)))
                self.pending_burst = {"cause": int(e["id"]), "quake": self.quakes[self.nq % len(self.quakes)]}
                board.answer(e, "graph", f"plays an arrival ({self.pending_burst['quake']})", t)
                self.nq += 1
        if self.x >= self.x1 - 1e-6:
            return
        n = max(int(round(self.dx / self.step)), 1)
        xs = self.x + np.arange(1, n + 1) * (self.dx / n)
        ys = []
        peak_j = None
        for i in range(n):
            nz = self.pre[self.pi % len(self.pre)] * self.noise_amp
            self.pi += 1
            if self.queue:
                if self.pending_burst is not None and self.b_i == self.peak_i:
                    peak_j = i
                ys.append(self.y - self.queue.pop(0) + 0.3 * nz)
                self.b_i += 1
            else:
                ys.append(self.y - nz)
        pts = np.column_stack([xs, ys])
        self.x = xs[-1]
        if self.lifted > 0:                       # the needle is up: the clock runs, nothing is written
            if paper.lines["graph"] and paper.lines["graph"][-1]:
                paper.new_line("graph")
            self.lifted -= 1
        else:
            paper.add("graph", pts, t)
        if peak_j is not None:
            board.post(t, "graph", "burst", pts[peak_j], lifted=bool(self.lifted), **self.pending_burst)
            self.pending_burst = None
            self.cool = self.refractory
        elif not self.queue and self.cool > 0:
            self.cool -= 1

    def trace_near(self, paper: Paper, x_lo: float, x_hi: float) -> np.ndarray | None:
        """The drawn trace between x_lo and x_hi (the longest contiguous piece)."""
        best = None
        for l in paper.lines["graph"]:
            if len(l) < 3:
                continue
            a = np.asarray(l)
            m = (a[:, 0] >= x_lo) & (a[:, 0] <= x_hi)
            if m.sum() > 3 and (best is None or m.sum() > len(best)):
                best = a[m]
        return best


# ---------------------------------------------------------------------------
# the bold regime
# ---------------------------------------------------------------------------

def _inside(q, box, inset=3.0):
    x0, y0, w, h = box
    lo, hi = np.array([x0 + inset, y0 + inset]), np.array([x0 + w - inset, y0 + h - inset])
    return float(np.mean(np.any((q < lo) | (q > hi), axis=1)))


def _in_blank(q, blanks):
    return float(sum(np.mean(np.linalg.norm(q - b[:2], axis=1) < b[2]) for b in blanks)) if len(blanks) else 0.0


class Bold:
    def __init__(self, g, rng, *, k_mm, length_R, n_cand, speed, box, blanks, ride_mm, ride_gap, turn_deg,
                 turn_gap, knot_mm, patience, appetite_cost, appetite_gain, refuse_below, start_tick, entries, step,
                 invite):
        self.g, self.rng = g, rng
        self.k_mm, self.length_R, self.n_cand = float(k_mm), float(length_R), int(n_cand)
        self.speed, self.box, self.blanks, self.step = float(speed), box, blanks, float(step)
        self.ride_mm, self.ride_gap = float(ride_mm), float(ride_gap)
        self.turn_rad, self.turn_gap = math.radians(turn_deg), float(turn_gap)
        self.knot_mm, self.patience = float(knot_mm), int(patience)
        self.appetite = 1.0
        self.appetite_cost, self.appetite_gain, self.refuse_below = appetite_cost, appetite_gain, refuse_below
        self.start_tick = int(start_tick)
        self.entries = list(entries)
        self.invite = float(invite)
        self.pen = Pen("bold", step)
        self.state = "wait"
        self.rest_since = 0
        self.knot_pos = None
        self.knot_event = None
        self.since_turn = 0.0
        self.cur: list = []
        self.cur_neg: list = []
        self.lines = 0

    def _score(self, paper: Paper, river_head, leave=None):
        x0, y0, w, h = self.box

        def f(q):
            out = _inside(q, self.box)
            bl = _in_blank(q, self.blanks)
            crowd = 0.0
            for who in REGIMES:
                crowd += float(np.mean(paper.near(who, q[::3], 3.0)))
            e = q[-1]
            edge = min(e[0] - x0, x0 + w - e[0], e[1] - y0, y0 + h - e[1])
            inv = 0.0
            if self.invite > 0:
                # it ends (stops) where an answer can come: off the edge, within the river's reach
                inv = self.invite * max(25.0 - edge, 0.0) / 10.0
                if river_head is not None:
                    inv += self.invite * max(float(np.linalg.norm(e - river_head)) - 60.0, 0.0) / 40.0
            lv = 0.0
            if leave is not None:                 # a refusal: it does not linger where it was called
                lv = 8.0 * float(np.mean(np.linalg.norm(q - leave, axis=1) < 30.0))
            return 60.0 * out + 60.0 * bl + 6.0 * crowd + inv + lv
        return f

    def _plan_own(self, paper, start, heading=None, spread=math.pi, river_head=None, leave=None):
        x0, y0, w, h = self.box
        L = self.length_R * (0.8 + 0.4 * self.rng.random())
        f = self._score(paper, river_head, leave)
        if start is None:                      # a free entry: anywhere with room, any heading
            best = None
            for _ in range(8):
                st = np.array([x0 + w * self.rng.uniform(0.08, 0.92), y0 + h * self.rng.uniform(0.2, 0.92)])
                b = plan_line(self.g, self.rng, n_cand=max(self.n_cand // 2, 1), length_R=L, k_mm=self.k_mm,
                              step=self.step, start=st, headings=np.linspace(-math.pi, math.pi, 8, endpoint=False),
                              score=f)
                if b is not None and (best is None or b[0] < best[0]):
                    best = b
            b = best
        else:
            hs = np.linspace(-math.pi, math.pi, 12, endpoint=False) if heading is None else \
                heading + np.linspace(-spread, spread, 7)
            b = plan_line(self.g, self.rng, n_cand=self.n_cand, length_R=L, k_mm=self.k_mm, step=self.step,
                          start=start, headings=hs, score=f)
        if b is None:
            return np.zeros((0, 2))
        q = b[1]
        lo = np.array([x0 + 1.0, y0 + 1.0])
        hi = np.array([x0 + w - 1.0, y0 + h - 1.0])
        bad = np.flatnonzero(np.any((q < lo) | (q > hi), axis=1))
        return q[: bad[0]] if len(bad) and bad[0] > 4 else q          # never past the sheet's edge

    def _new_line(self, t, paper):
        paper.new_line("bold")
        self.cur, self.cur_neg = [], []
        self.since_turn = 0.0
        self.lines += 1

    def turn(self, t, board: Board, paper: Paper, log: list, river_head):
        for e in board.inbox("bold"):
            if self.state != "rest":
                board.answer(e, "bold", "ignored (busy drawing)", t)
                continue
            if self.appetite < self.refuse_below:
                board.answer(e, "bold", "refuses (tired): turns its back on the river, goes its own way", t)
                away = self.pen.pos - np.asarray(e["pos"], float)          # away from where the river arrived
                own = self._plan_own(paper, self.pen.pos, heading=math.atan2(away[1], away[0]), spread=0.7,
                                     river_head=None, leave=self.pen.pos.copy())
                self.pen.plan([(own[1:], 0.0)])
                self.state = "draw"
                self.since_turn = 0.0
                continue
            self._ride_from_knot(t, e, board, paper, river_head)
        if self.state == "wait":
            if t < self.start_tick:
                return
            x0, y0, w, h = self.box
            if self.entries:
                e = self.entries[0]
                start = np.array([x0 + e[0] * w, y0 + e[1] * h])
                own = self._plan_own(paper, start, heading=math.radians(e[2]), spread=0.5, river_head=river_head)
            else:
                own = self._plan_own(paper, None, river_head=river_head)
            start = own[0]
            self._new_line(t, paper)
            self.pen.pos = start.copy()
            paper.add("bold", start[None, :], t)
            self.pen.plan([(own[1:], 0.0)])
            self.state = "draw"
            self.cur = [start.tolist()]
            self.cur_neg = [0.0]
        if self.state == "rest":
            self.appetite = min(self.appetite + self.appetite_gain, 1.0)
            if t - self.rest_since > self.patience:
                log.append({"t": t, "who": "bold", "what": "gives up waiting for the river; goes on from its knot"})
                if self.knot_event is not None:
                    board.answer(self.knot_event, "bold", "gave up waiting", t)
                own = self._plan_own(paper, self.pen.pos, heading=self.pen.heading, spread=1.2, river_head=river_head)
                self.pen.plan([(own[1:], 0.0)])
                self.state = "draw"
                self.since_turn = 0.0
            else:
                return
        drawn = self.pen.draw(self.speed, t, paper)
        for pts, neg in drawn:
            n0 = len(self.cur)
            self.cur += pts.tolist()
            self.cur_neg += [neg] * len(pts)
            if neg == 0:
                self.since_turn += float(arcl(pts)[-1]) if len(pts) > 1 else 0.0
            self._detect_turn(t, board, n0)
        if not self.pen.queue and self.state == "draw":
            self._stop(t, board, paper)

    def _detect_turn(self, t, board, n0):
        cur = np.asarray(self.cur)
        w = max(int(2.5 / self.step), 2)
        if len(cur) < 3 * w or self.since_turn < self.turn_gap:
            return
        for i in range(max(n0 - w, w), len(cur) - w):
            if self.cur_neg[i] > 0 or self.cur_neg[max(i - w, 0)] > 0 or self.cur_neg[min(i + w, len(cur) - 1)] > 0:
                continue
            if heading_change(cur, i, w) >= self.turn_rad:
                board.post(t, "bold", "turn", cur[i])
                self.since_turn = 0.0
                return

    def _stop(self, t, board, paper):
        pts = knot(self.pen.pos, self.pen.heading, self.knot_mm, self.rng, self.step)
        paper.add("bold", pts, t)
        self.cur += pts.tolist()
        self.cur_neg += [0.0] * len(pts)
        self.pen.pos = pts[-1].copy()
        self.knot_pos = pts.mean(axis=0)
        self.knot_event = board.post(t, "bold", "stop", self.knot_pos)
        self.appetite = max(self.appetite - self.appetite_cost, 0.0)
        self.state = "rest"
        self.rest_since = t

    def _ride_from_knot(self, t, e, board, paper: Paper, river_head):
        """The river came: re-enter at the knot, ride the river beside it, leave at a tangent."""
        lines = [np.asarray(l) for l in paper.lines["river"] if len(l) > 10]
        if not lines:
            board.answer(e, "bold", "ignored (no river to ride)", t)
            return
        c = self.knot_pos
        Rl = min(lines, key=lambda l: float(np.min(np.linalg.norm(l - c, axis=1))))
        Rl = resample(Rl, self.step)
        j = int(np.argmin(np.linalg.norm(Rl - c, axis=1)))
        n = int(self.ride_mm * (0.8 + 0.4 * self.rng.random()) / self.step)
        if j - n >= 0 and (len(Rl) - 1 - j < n or self.rng.random() < 0.5):
            seg = Rl[max(j - n, 0): j + 1][::-1]
        else:
            seg = Rl[j: j + n + 1]
        if len(seg) < 8:
            board.answer(e, "bold", "ignored (river too short here)", t)
            return
        t0, v0 = tangents(seg, 3)[0], c - seg[0]
        side = 1.0 if float(t0[0] * v0[1] - t0[1] * v0[0]) >= 0 else -1.0
        seg = beside(seg, self.ride_gap, side, smooth=1.0)
        h0 = np.array([math.cos(self.pen.heading), math.sin(self.pen.heading)])
        tseg = tangents(seg, 6)
        br = bridge(self.pen.pos, h0, seg[0], tseg[0], self.step)
        hl = math.atan2(tseg[-1][1], tseg[-1][0])
        own = self._plan_own(paper, seg[-1], heading=hl, spread=0.35, river_head=None)
        self.pen.plan([(br, 0.0), (seg, 1.0), (own[1:], 0.0)])
        self.state = "draw"
        self.since_turn = 0.0
        self.appetite = max(self.appetite - 0.3 * self.appetite_cost, 0.0)
        board.answer(e, "bold", "re-enters from its knot and rides the river", t,
                     ride_mm=round(float(arcl(seg)[-1]), 1))


# ---------------------------------------------------------------------------
# the wire regime
# ---------------------------------------------------------------------------

class Wire:
    def __init__(self, g, rng, *, k_mm, length_R, n_cand, speed, awake_speed, box, blanks, refuse_r, ride_gap,
                 start, heading, blank_target, wake_max, start_tick, step, look, lift_max):
        self.g, self.rng = g, rng
        self.k_mm, self.length_R, self.n_cand = float(k_mm), float(length_R), int(n_cand)
        self.speed, self.awake_speed = float(speed), float(awake_speed)
        self.box, self.blanks, self.step = box, blanks, float(step)
        self.refuse_r, self.ride_gap = float(refuse_r), float(ride_gap)
        self.start, self.heading0 = np.asarray(start, float), float(heading)
        self.blank_target = np.asarray(blank_target, float)
        self.wake_max, self.start_tick = int(wake_max), int(start_tick)
        self.look, self.lift_max = float(look), int(lift_max)
        self.ride_before, self.ride_after = 10.0, 10.0
        self.late_tick = 10 ** 9
        self.curious = True
        self.pen = Pen("wire", step)
        self.state = "wait"            # wait / slow / awake / leave
        self.wake_event = None
        self.wakes = 0
        self.refusals = 0
        self.last_refusal = -99
        self.in_blank = False
        self.ride_posted = True
        self.ride_mm = 0.0

    def _clear(self, paper, q):
        return float(np.mean(paper.near("bold", q, self.refuse_r))) if len(q) else 0.0

    def _plan_own(self, paper, start, heading, spread, goal=None):
        hs = heading + np.linspace(-spread, spread, 7)

        def f(q):
            sc = 60.0 * _inside(q, self.box) + 40.0 * self._clear(paper, q)
            sc += 2.0 * float(np.mean(paper.near("wire", q[::3], 2.0)))
            if goal is not None:
                sc += float(np.min(np.linalg.norm(q - goal, axis=1))) / 10.0
            return sc
        b = plan_line(self.g, self.rng, n_cand=self.n_cand, length_R=self.length_R, k_mm=self.k_mm, step=self.step,
                      start=start, headings=hs, score=f)
        return b[1] if b is not None else np.zeros((0, 2))

    def turn(self, t, board: Board, paper: Paper, log: list, graph: Graph):
        for e in board.inbox("wire"):
            if e["src"] == "bold":
                # curiosity without contact: it comes to look at the knot; refusal keeps it off the ink
                if self.state == "slow" and self.curious:
                    goal = np.asarray(e["pos"], float)
                    d = goal - self.pen.pos
                    own = self._plan_own(paper, self.pen.pos, math.atan2(d[1], d[0]), 0.7, goal=goal)
                    self.pen.plan([(own[1:], 0.0)])
                    board.answer(e, "wire", "comes to look at the knot", t)
                else:
                    board.answer(e, "wire", "ignored (busy)", t)
                continue
            if self.state == "awake" or self.wakes >= self.wake_max or self.state == "wait":
                board.answer(e, "wire", "ignored (already answering / spent)", t)
                continue
            if self._wake(t, e, board, paper, graph):
                self.wakes += 1
        if self.state == "wait":
            if t < self.start_tick:
                return
            own = self._plan_own(paper, self.start, self.heading0, 0.4)
            paper.new_line("wire")
            paper.add("wire", self.start[None, :], t)
            self.pen.pos = self.start.copy()
            self.pen.heading = self.heading0
            self.pen.plan([(own[1:], 0.0)])
            self.state = "slow"
        if self.state in ("slow", "leave"):
            self._maybe_refuse(t, board, paper, log)
        speed = self.awake_speed if self.state == "awake" else (0.6 * self.awake_speed if self.state == "leave" else self.speed)
        drawn = self.pen.draw(speed, t, paper)
        for pts, neg in drawn:
            if neg == 1 and not self.ride_posted:
                ev = board.post(t, "wire", "ride", pts[0], on="graph", ticks=self.lift_max, ride_mm=self.ride_mm)
                if self.wake_event is not None:
                    board.answer(self.wake_event, "wire", "rides the trace", t, ride=ev["id"])
                self.ride_posted = True
            self._check_blank(t, board, pts)
        # the ride is drawn and only the leaving line is left: it goes its own way
        if self.state == "awake" and self.ride_posted and len(self.pen.queue) == 1 and self.pen.queue[0][1] == 0.0:
            self.state = "leave"
            log.append({"t": t, "who": "wire", "what": "leaves the trace at a tangent, for the blank"})
        if not self.pen.queue:
            # spent (or late): its own way somewhere else, into the blank that only it may enter
            late = self.wakes >= self.wake_max or t >= self.late_tick
            goal = self.blank_target if late else None
            own = self._plan_own(paper, self.pen.pos, self.pen.heading, 0.9 if late else 0.3, goal=goal)
            self.pen.plan([(own[1:], 0.0)])
            if self.state in ("awake", "leave"):
                self.state = "slow"

    def _maybe_refuse(self, t, board, paper, log):
        ahead = self.pen.own_ahead(self.look)
        if len(ahead) < 3 or not np.any(paper.near("bold", ahead, self.refuse_r)):
            return
        rest = np.vstack([p for p, _ in self.pen.queue]) if self.pen.queue else np.zeros((0, 2))
        if len(rest) < 5:
            return
        pos = self.pen.pos
        best = None
        for a in (25, 45, 70, 100, 135, 160):
            for sgn in (1, -1):
                ang = math.radians(a * sgn)
                Rm = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
                q = (rest - pos) @ Rm.T + pos
                head = q[: int(40.0 / self.step)]
                bad = self._clear(paper, head) + 2.0 * _inside(head, self.box)
                if bad == 0.0 and (best is None or a < best[0]):
                    best = (a, sgn, q)
            if best is not None:
                break
        if best is None:
            if t - self.last_refusal > 6:
                log.append({"t": t, "who": "wire", "what": "cannot turn away: crosses the bold line"})
                self.last_refusal = t
            return
        a, sgn, q = best
        k = max(int(2.0 / self.step), 2)
        h0 = np.array([math.cos(self.pen.heading), math.sin(self.pen.heading)])
        tq = tangents(q, 3)
        br = bridge(pos, h0, q[k], tq[k], self.step)
        self.pen.plan([(br, 0.0), (q[k:], 0.0)])
        self.refusals += 1
        self.last_refusal = t
        board.post(t, "wire", "refuse", pos, of="bold", turned_deg=int(a * sgn))

    def _wake(self, t, e, board, paper, graph: Graph) -> bool:
        px, py = float(e["pos"][0]), float(graph.y)
        tr = graph.trace_near(paper, px - self.ride_before, px + self.ride_after)
        if tr is None or len(tr) < 10:
            board.answer(e, "wire", "found no trace to ride", t)
            return False
        tr = resample(tr, self.step)
        pos = self.pen.pos
        # ride from the trace end nearer the wire, through the burst, to the other end
        if np.linalg.norm(tr[0] - pos) > np.linalg.norm(tr[-1] - pos):
            tr = tr[::-1]
        below = 1.0 if pos[1] > py else -1.0
        # a function graph is ridden as a second, mis-registered print of itself (a shift, not a normal
        # offset: offsetting spikes along their normals boxes them in)
        ride = tr + np.array([0.6, below * 0.8]) * self.ride_gap
        goal = ride[0] + np.array([0.0, below * 8.0])
        d0 = goal - pos
        own = self._plan_own(paper, pos, math.atan2(d0[1], d0[0]), 0.6, goal=goal)
        if len(own) < 4:
            return False
        j = int(np.argmin(np.linalg.norm(own - goal, axis=1)))
        appr = own[1: max(j, 2)]
        hA = tangents(own, 3)[max(j - 1, 0)]
        tr0 = tangents(ride, 4)[0]
        br = bridge(appr[-1] if len(appr) else pos, hA, ride[0], tr0, self.step)
        tl = tangents(ride, 6)[-1]
        leave = self._plan_own(paper, ride[-1], math.atan2(tl[1], tl[0]), 0.8, goal=self.blank_target)
        self.pen.plan([(appr, 0.0), (br, 0.0), (ride, 1.0), (leave[1:], 0.0)])
        self.state = "awake"
        self.wake_event = e
        self.ride_posted = False
        self.ride_mm = round(float(arcl(ride)[-1]), 1)
        board.answer(e, "wire", "wakes and crosses to the burst", t)
        return True

    def _check_blank(self, t, board, p):
        for b in self.blanks:
            inside = np.linalg.norm(p - b[:2], axis=1) < b[2]
            if np.any(inside) and not self.in_blank:
                board.post(t, "wire", "enter_blank", p[int(np.argmax(inside))])
                self.in_blank = True
            elif len(p) and not np.any(inside) and self.in_blank:
                self.in_blank = False


# ---------------------------------------------------------------------------
# the voice
# ---------------------------------------------------------------------------

def run_mutual(ctx, *, T, river_scale, river_sigma, river_start, river_heading, river_speed, river_kmax,
               river_nat, river_rush, river_flow, wrap_r, wrap_deg, graph_band, graph_amp, graph_noise, burst_ticks, refractory, lift_max,
               quakes, bold_hand, bold_k, bold_len, bold_speed, ride_mm, ride_gap, turn_deg, turn_gap, knot_mm,
               patience, appetite_cost, appetite_gain, refuse_below, bold_start, bold_entries, invite,
               wire_hand, wire_k, wire_len, wire_speed, wire_awake, refuse_r, wire_gap, wire_start,
               wire_heading, wire_start_tick, wake_max, wire_curious, blank, n_cand, step, pens, inks, upto):
    x0, y0, bw, bh = ctx.box
    rng = {r: np.random.default_rng([int(ctx.seed), i, 0x3171A]) for i, r in enumerate(REGIMES)}
    blanks = np.array([[x0 + blank[0] * bw, y0 + blank[1] * bh, blank[2] * min(bw, bh)]]) if blank else np.zeros((0, 3))
    board, paper, log = Board(), Paper(), []
    fz = ctx.use("river_stems", "grwl_far_sb19")
    _, _, q = fz["stems"][("SB19", 0)]
    vf = valley_frame(np.asarray(q, float) * river_scale / 1000.0, river_sigma)
    river = River(ctx, vf, rng["river"], start=(x0 + river_start[0] * bw, y0 + river_start[1] * bh),
                  heading=math.radians(river_heading), speed=river_speed, kmax=river_kmax, nat=river_nat,
                  wrap_r=wrap_r, wrap_deg=wrap_deg, box=ctx.box, blanks=blanks, step=step, lag=6.0)
    river.rush = float(river_rush)
    river.flow = float(river_flow)
    gx0, gx1, gy = x0 + graph_band[0] * bw, x0 + graph_band[1] * bw, y0 + graph_band[2] * bh
    graph = Graph(rng["graph"], x0=gx0, x1=gx1, y=gy, T=T, amp=graph_amp, noise_amp=graph_noise,
                  burst_ticks=burst_ticks, refractory=refractory, quakes=quakes, step=0.3, decim=6)
    paper.new_line("graph")
    bold = Bold(ctx.use("hand", bold_hand), rng["bold"], k_mm=bold_k, length_R=bold_len, n_cand=n_cand,
                speed=bold_speed, box=ctx.box, blanks=blanks, ride_mm=ride_mm, ride_gap=ride_gap, turn_deg=turn_deg,
                turn_gap=turn_gap, knot_mm=knot_mm, patience=patience, appetite_cost=appetite_cost,
                appetite_gain=appetite_gain, refuse_below=refuse_below, start_tick=bold_start,
                entries=np.asarray(bold_entries, float).reshape(-1, 3).tolist(), step=step, invite=invite)
    wire = Wire(ctx.use("hand", wire_hand), rng["wire"], k_mm=wire_k, length_R=wire_len, n_cand=n_cand,
                speed=wire_speed, awake_speed=wire_awake, box=ctx.box, blanks=blanks, refuse_r=refuse_r,
                ride_gap=wire_gap, start=(x0 + wire_start[0] * bw, y0 + wire_start[1] * bh),
                heading=math.radians(wire_heading),
                blank_target=(blanks[0, :2] if len(blanks) else (x0 + bw * 0.8, y0 + bh * 0.8)),
                wake_max=wake_max, start_tick=wire_start_tick, step=step, look=8.0, lift_max=lift_max)
    wire.late_tick = int(0.7 * T)
    wire.curious = bool(wire_curious)
    last = T if upto <= 0 else min(T, upto)
    heads = []
    for t in range(last):
        graph.turn(t, board, paper, log)
        river.turn(t, board, paper, log)
        bold.turn(t, board, paper, log, (river.axis[-1] + 50.0 * np.array([math.cos(river.theta), math.sin(river.theta)]))
                  if not river.done else None)
        wire.turn(t, board, paper, log, graph)
        heads.append({"graph": [round(graph.x, 2), round(graph.y, 2)],
                      "river": np.round(river.axis[-1], 2).tolist(),
                      "bold": None if bold.pen.pos is None else np.round(bold.pen.pos, 2).tolist(),
                      "wire": None if wire.pen.pos is None else np.round(wire.pen.pos, 2).tolist(),
                      "states": {"river": "answer" if river.target is not None else ("done" if river.done else "own"),
                                 "bold": bold.state, "wire": wire.state}})
    marks = []
    roles = {"graph": 0, "river": 1, "bold": 2, "wire": 3}
    for who in REGIMES:
        for li, (l, tk, ng) in enumerate(zip(paper.lines[who], paper.ticks[who], paper.negs[who])):
            if len(l) < 2:
                continue
            pts = np.asarray(l, float)
            keep = np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-9]
            pts, tk_, ng_ = pts[keep], np.asarray(tk, float)[keep], np.asarray(ng, float)[keep]
            if len(pts) < 2:
                continue
            marks.append(Mark(pts, {"tick": tk_, "neg": ng_, "r": np.zeros(len(pts))},
                              {"of_role": who, "ink": inks[roles[who]], "pen": float(pens[roles[who]]),
                               "line": li, "voices": [who]}))
    meta = {"T": T, "ran": last, "events": board.events, "log": log, "heads": heads,
            "relations": {k: {f"{a}.{b}": v for (a, b), v in d.items()} for k, d in RELATIONS.items()},
            "ignores": IGNORES, "blanks_mm": blanks.round(2).tolist(),
            "graph": {"x0": gx0, "x1": gx1, "y": gy}, "river_scale_mm_per_km": river_scale,
            "wire_refusals": wire.refusals, "bold_appetite": round(bold.appetite, 3)}
    if marks:
        marks[0] = marks[0].evolve(meta={"mutual": meta})
    return marks


@voice("mutual", params=[
    P("T", "int", 150, "ticks: in each tick every regime takes one turn (graph, river, bold, wire)", min=10, max=400),
    P("upto", "int", 0, "stop after this many ticks (0 = all): a process-strip state of the same run", min=0, max=400),
    P("river_scale", "float", 1.5, "river: mm per km of the far-view stem (≈ 1 keeps the zigzag tight)",
      min=0.3, max=3.0),
    P("river_sigma", "float", 9.0, "river: valley-axis smoothing, mm (the meander lives across it)", min=2.0, max=40.0),
    P("river_start", "floats", [0.0, 0.62], "river: where its course starts (fractions of the box)"),
    P("river_heading", "float", 0.0, "river: initial course heading, degrees (0 = east)", min=-180.0, max=180.0),
    P("river_speed", "float", 1.8, "river: course mm per turn", min=0.2, max=20.0),
    P("river_kmax", "float", 0.07, "river: steepest course turn, rad per mm (keeps the meander unfolded)",
      min=0.005, max=0.5),
    P("river_nat", "float", 1.0, "river: how much of the stem's own valley bending the course keeps", min=0.0, max=2.0),
    P("river_rush", "float", 2.3, "river: speed × this while it answers a call", min=0.2, max=6.0),
    P("river_flow", "float", 0.08, "river: on its own, how strongly it returns to the way it flows (its first "
      "heading), rad per mm per rad", min=0.0, max=1.0),
    P("wrap_r", "float", 13.0, "river: radius at which it wraps a knot, mm", min=3.0, max=60.0),
    P("wrap_deg", "float", 160.0, "river: how far round the knot it goes at least before it 'arrives' (then it "
      "leaves as soon as it faces downstream), degrees",
      min=30.0, max=500.0),
    P("graph_band", "floats", [0.05, 0.95, 0.12], "graph: x from, x to (fractions of the box), baseline y (fraction)"),
    P("graph_amp", "float", 9.0, "graph: burst amplitude, mm", min=0.5, max=40.0),
    P("graph_noise", "float", 0.5, "graph: pre-event noise amplitude, mm", min=0.0, max=5.0),
    P("burst_ticks", "int", 7, "graph: an arrival lasts this many ticks of the clock", min=1, max=40),
    P("refractory", "int", 6, "graph: after a burst it ignores cues for this many ticks", min=0, max=60),
    P("lift_max", "int", 4, "graph: the needle stays lifted this many ticks when the wire touches it", min=0, max=40),
    P("quakes", "str", ",".join(QUAKES), "graph: the arrivals it plays, in order (FDSN IU.ANMO LHZ)"),
    P("bold_hand", "ref", "dance_thrusting", "bold: the hand", kind="hand"),
    P("bold_k", "float", 0.21, "bold: mm per research px (its gesture scale)", min=0.01, max=1.0),
    P("bold_len", "float", 1.0, "bold: one line, in R of its hand (± 20 %)", min=0.1, max=6.0),
    P("bold_speed", "float", 7.0, "bold: mm per turn", min=0.5, max=60.0),
    P("ride_mm", "float", 45.0, "bold: a ride along the river, mm (± 20 %)", min=3.0, max=400.0),
    P("ride_gap", "float", 0.9, "bold: rides this far beside the river, mm", min=0.0, max=5.0),
    P("turn_deg", "float", 80.0, "bold: a heading change ≥ this within ±2.5 mm is a 'turn' event", min=20.0, max=180.0),
    P("turn_gap", "float", 60.0, "bold: turn events at least this far apart along its line, mm", min=0.0, max=1000.0),
    P("knot_mm", "float", 2.2, "bold: the knot at a stop, mm", min=0.3, max=12.0),
    P("patience", "int", 50, "bold: turns it waits at a knot for the river before it gives up", min=1, max=400),
    P("appetite_cost", "float", 0.35, "bold: appetite spent per line", min=0.0, max=1.0),
    P("appetite_gain", "float", 0.012, "bold: appetite regained per resting turn", min=0.0, max=1.0),
    P("refuse_below", "float", 0.25, "bold: below this appetite it refuses the river's call", min=0.0, max=1.0),
    P("bold_start", "int", 4, "bold: first turn it draws", min=0, max=400),
    P("bold_entries", "floats", [], "bold: its first entry (x, y fractions of the box, heading deg); empty = it "
      "chooses a place with room"),
    P("invite", "float", 1.0, "bold: how much it prefers to end (stop) where the river could come", min=0.0, max=10.0),
    P("wire_hand", "ref", "trail_slime", "wire: the hand", kind="hand"),
    P("wire_k", "float", 0.12, "wire: mm per research px", min=0.01, max=1.0),
    P("wire_len", "float", 1.2, "wire: one planned stretch, in R of its hand", min=0.1, max=6.0),
    P("wire_speed", "float", 3.0, "wire: mm per turn, asleep (slow)", min=0.2, max=60.0),
    P("wire_awake", "float", 9.0, "wire: mm per turn once woken", min=0.2, max=60.0),
    P("refuse_r", "float", 5.0, "wire: keeps this far from bold ink (refusal), mm", min=0.0, max=40.0),
    P("wire_gap", "float", 1.1, "wire: rides this far beside the graph's trace, mm", min=0.0, max=5.0),
    P("wire_start", "floats", [0.08, 1.0], "wire: where it enters (fractions of the box)"),
    P("wire_heading", "float", -60.0, "wire: entry heading, degrees", min=-180.0, max=180.0),
    P("wire_start_tick", "int", 0, "wire: first turn it draws", min=0, max=400),
    P("wire_curious", "bool", True, "wire: a bold stop draws it to look (and its refusal turns it away)"),
    P("wake_max", "int", 2, "wire: answers at most this many bursts", min=0, max=20),
    P("blank", "floats", [0.8, 0.8, 0.17], "the reserved blank: cx, cy (fractions of the box), r (× short side); "
      "only the wire may enter it; empty = none"),
    P("n_cand", "int", 6, "whole-line candidates a hand regime weighs per plan", min=1, max=40),
    P("step", "float", 0.4, "sampling step, mm", min=0.1, max=2.0),
    P("pens", "floats", [0.3, 0.3, 1.0, 0.25], "pen widths: graph, river, bold, wire"),
    P("inks", "str", "red,blue,black,black", "Flexoki inks: graph, river, bold, wire"),
], doc="mutual awareness: river, seismograph, bold hand and slow wire draw in interleaved turns; each one's "
       "discrete events (stop, turn, arrive, burst, ride) cue another's reply, and some refuse or ignore")
def mutual(ctx, *, quakes, inks, **kw):
    q = tuple(x.strip() for x in quakes.split(",") if x.strip())
    for x in q:
        if x not in QUAKES:
            raise ValueError(f"mutual: unknown quake {x!r}; choose from {QUAKES}")
    ik = [x.strip() for x in inks.split(",")]
    if len(ik) != 4:
        raise ValueError("mutual: inks needs four names (graph, river, bold, wire)")
    pens = list(kw.pop("pens"))
    if len(pens) != 4:
        raise ValueError("mutual: pens needs four widths (graph, river, bold, wire)")
    return run_mutual(ctx, quakes=q or QUAKES, inks=ik, pens=pens, **kw)
