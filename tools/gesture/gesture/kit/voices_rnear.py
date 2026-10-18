"""Round 14, thread c2 `rnear`: the Amazon river line, approached and left.

The line is the frozen far-view GRWL stem (`river_stems/grwl_far_sb19`, the
`oehlen_found_river` river). It starts and ends at the far zoom. Between, a
camera moves in and out along it:

    carrier   the stem's own heading θ(u), u in channel widths along the
              channel, drawn at paper speed ds = k(u)·du. Where k is 1 the
              far view's dense twists stay dense; where k grows the same
              bends open (curvature on paper = κ/k). Heading is continuous
              by construction. k(u) is a few asymmetric approaches.
    handover  as k reaches the zoom a closer river hand was learned at
              (round 11: `river_belt` 400 w, `river_meander` 150 w,
              `river_bend` 60 w per drawing; k_h = 1600 / zoom), whole
              stem BENDS (inflection to inflection) are handed to that hand,
              one stem bend for a contiguous window of 1–4 of the hand's own
              bends, never an average:
                - the window starts turning the way the stem bend turns
                  (mirrored if needed: handedness at the joint);
                - it is drawn at the paper scale the local zoom implies
                  (R_h measured on the stem itself, × k): apparent scale;
                - among windows of the hand's running chain, the one whose
                  net turn and length best match the stem bend it replaces
                  (plus the course error so far) is taken whole, so the
                  river's course comes back after the hand has spoken.
    event     at the nearest approach, the tightest stem bend becomes a
              real cut-off bend (Li et al. neck centrelines, `river_loops`
              kind): the bend at the moment it pinches off, at its own
              length in channel widths × k. Or an oxbow (`oxbow`): the line
              runs round a closed lake outline at the bend apex and goes on.

Frame: `plan` candidate lines (start, approach centres and a ±20° turn
jittered) are built; the one that fits ctx.box at the largest scale (≤
far_mm), then fills it best, is kept. A high-zoom bend is planned against
the frame, never clipped. Hand windows are integrated token by token
(`integrate_tokens`) so the stem resumes without a cusp, and a window that
would cross itself is refused (`simple`, the river law).

Channels: `zoom` (k, × the far zoom), `src` (0 stem, 1.. hand j+1, last =
event; nearest), `voice` (same index into meta["voices"]), `stem_u`
(channel widths along the stem; nearest).
Pure geometry for tests: `approach_line(...)`.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.ndimage import gaussian_filter1d

from .. import grammar as gm
from . import voices_handover as vh
from .arrangers_oehlen_found import FAR_STEMS, rotate, stem
from .core import Mark, P, channel_kind, voice

FAR_W = 1600.0                 # the far view's span (oehlen_found_river default): k = 1
HAND_ZOOM = {"river_belt": 400.0, "river_meander": 150.0, "river_bend": 60.0}
DEFAULT_ZOOM = 60.0
KINK = 120.0                   # max |κ|·window length above which a hand window draws a visible kink            # hands without a learned zoom are treated as the nearest
for _c in ("src", "voice", "stem_u"):
    channel_kind(_c, "nearest")


# ---------------------------------------------------------------------------
# the stem as a turning function
# ---------------------------------------------------------------------------

class StemGeom:
    """Heading spline θ(u) of a stem in metres; u in channel widths."""

    def __init__(self, q: np.ndarray, wm: float):
        q = np.asarray(q, float)
        d = np.linalg.norm(np.diff(q, axis=0), axis=1)
        self.u = np.r_[0.0, np.cumsum(d)] / wm
        g = np.gradient(q, axis=0)
        th = np.unwrap(np.arctan2(g[:, 1], g[:, 0]))
        self.theta = CubicSpline(self.u, th)
        self.L = float(self.u[-1])
        self.wm = float(wm)
        self.q = q
        # bends: inflection to inflection of κ smoothed at ~1 w
        du = float(np.median(np.diff(self.u)))
        kap = gaussian_filter1d(np.gradient(th, self.u), 1.0 / du, mode="nearest")
        sg = np.where(kap >= 0, 1, -1)
        cuts = np.flatnonzero(np.diff(sg) != 0) + 1
        edges = np.r_[0, cuts, len(sg) - 1]
        bends = []
        for a, b in zip(edges[:-1], edges[1:]):
            ua, ub = self.u[a], self.u[b]
            if bends and ub - ua < 2.0:                   # a sub-2 w wobble: part of the previous bend
                bends[-1][1] = ub
                continue
            bends.append([ua, ub])
        self.bends = np.array(bends)

    def net(self, ua: float, ub: float) -> float:
        return float(self.theta(ub) - self.theta(ua))

    def diag_w(self, span_w: float) -> float:
        """Median bounding-box diagonal (w) of stretches span_w long: the R a
        hand learned at that zoom was drawn at (R = drawing's diagonal)."""
        n = int(span_w / max(np.median(np.diff(self.u)), 1e-9))
        if n >= len(self.q):
            return float(np.hypot(*np.ptp(self.q, axis=0))) / self.wm
        out = [float(np.hypot(*np.ptp(self.q[a:a + n], axis=0))) / self.wm
               for a in range(0, len(self.q) - n, max(n // 2, 1))]
        return float(np.median(out))


@lru_cache(maxsize=4)
def _geom_cached(key: str, wm: float, data: bytes, shape: tuple) -> StemGeom:
    return StemGeom(np.frombuffer(data, float).reshape(shape), wm)


def stem_geom(q, wm) -> StemGeom:
    q = np.ascontiguousarray(q, float)
    return _geom_cached(f"{len(q)}", float(wm), q.tobytes(), q.shape)


# ---------------------------------------------------------------------------
# zoom schedule
# ---------------------------------------------------------------------------

def _smoother(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * x * (x * (6 * x - 15) + 10)


def zoom_at(t, approaches) -> np.ndarray:
    """k(t), t = share of the stretch: 1 = far; each approach is a bump in
    log k (rise then fall, smootherstep); overlapping approaches take the max."""
    t = np.asarray(t, float)
    lk = np.zeros_like(t)
    for a in approaches:
        c, r, f, pk = a["c"], max(a["rise"], 1e-3), max(a["fall"], 1e-3), math.log(a["peak"])
        up = _smoother((t - (c - r)) / r)
        down = 1.0 - _smoother((t - c) / f)
        b = np.where(t <= c, up, down)
        lk = np.maximum(lk, pk * b)
    return np.exp(lk)


def make_approaches(rng, *, n: int, peak: float, width: float, skew: float, vary: float) -> list[dict]:
    """n approaches across the stretch: uneven peaks, widths and skews.
    The deepest approach is at a random place; the others are shallower."""
    deep = int(rng.integers(n))
    slots = np.linspace(0.0, 1.0, n + 1)
    out = []
    for j in range(n):
        pk = peak if j == deep else peak ** float(1.0 - vary * rng.uniform(0.25, 0.7))
        w = width * float(1.0 + vary * rng.uniform(-0.4, 0.4)) / n
        sk = float(np.clip(skew * (-1.0 if rng.random() < 0.3 * vary else 1.0) + vary * rng.normal(0, 0.2), -0.92, 0.92))
        rise, fall = w * (1 + sk) / 2, w * (1 - sk) / 2
        room = (slots[j + 1] - slots[j]) - 0.08                 # never touch the far ends of the line
        if rise + fall > room:
            rise, fall = rise * room / (rise + fall), fall * room / (rise + fall)
        lo, hi = slots[j] + 0.04 + rise, slots[j + 1] - 0.04 - fall
        c = float(rng.uniform(lo, hi)) if hi > lo else float(0.5 * (slots[j] + slots[j + 1]))
        out.append({"c": c, "rise": rise, "fall": fall, "peak": float(max(pk, 1.0))})
    return out


# ---------------------------------------------------------------------------
# hands as bends
# ---------------------------------------------------------------------------

def integrate_tokens(toks: list, R: float, *, start=(0.0, 0.0), heading: float = 0.0, step: float = 0.1):
    """Points of a token list, each token integrated on its own (as passage
    does): grammar.tokens_to_points carries one token's end curvature into
    the next within a run, which disagrees with end_heading when a window
    joins segments from different strokes. Here the heading after each
    token is exactly end_heading's, so the joint back to the stem is smooth."""
    pos = np.asarray(start, float)
    h = float(heading)
    out = [pos[None, :]]
    for t in toks:
        if t[0] == "corner":
            h += float(t[1])
            continue
        p, _, _ = gm.tokens_to_points([t], R, start=pos, heading=h, step=step)
        out.append(p[1:])
        pos = p[-1]
        h = gm.end_heading([t], h)
    return np.vstack(out), h


class HandChain:
    """One hand's running chain cut into bends (runs of one handedness).
    Windows are taken in chain order: the pointer only moves forward."""

    def __init__(self, g, rng, zoom_w: float, R_w: float, n_segs: int = 900):
        segs = vh.stream(g, rng, n_segs)
        self.bends: list[list[dict]] = []
        cur = None
        for s in segs:
            if cur is None or s["sgn"] != cur[0]["sgn"]:
                cur = [s]
                self.bends.append(cur)
            else:
                cur.append(s)
        self.net = np.array([sum(0.5 * (s["k0"] + s["k1"]) * s["l"] + (s["corner"] or 0.0) * (i > 0)
                                 for i, s in enumerate(b)) for b in self.bends])
        self.len = np.array([sum(s["l"] for s in b) for b in self.bends])
        self.sgn = np.array([b[0]["sgn"] for b in self.bends])
        self.corners = np.array([sum(s["corner"] is not None for s in b[1:]) for b in self.bends])
        self.kmax = np.array([max(max(abs(s["k0"]), abs(s["k1"])) for s in b) for b in self.bends])
        self.zoom_w, self.R_w = float(zoom_w), float(R_w)
        self.ptr = 0

    def candidates(self, sign: float, target_net: float, target_len_R: float, look: int = 80, max_n: int = 4,
                   keep: int = 12) -> list[tuple]:
        """Contiguous windows (1..max_n bends) ahead of the pointer, best
        first: (cost, start, n, mirror, net). Mirrored so the first bend
        turns `sign`; cost on net turn and length; a window holding one of
        the hand's piece-end corners (not a river feature) comes last."""
        nb = len(self.bends)
        if self.ptr >= nb - 1:                          # chain exhausted: wrap round
            self.ptr = 0
        out = []
        for a in range(self.ptr, min(self.ptr + look, nb)):
            m = sign * self.sgn[a]                      # +1 keep, -1 mirror
            for n in range(1, max_n + 1):
                if a + n > nb:
                    break
                net = m * float(self.net[a:a + n].sum())
                ln = float(self.len[a:a + n].sum())
                c = ((net - target_net) / 0.6) ** 2 + (math.log(max(ln, 1e-9) / max(target_len_R, 1e-9)) / 0.5) ** 2
                c += 0.02 * (a - self.ptr)               # prefer the chain as it runs
                c += 100.0 * float(self.corners[a:a + n].sum())
                if float(self.kmax[a:a + n].max()) * ln > KINK:          # a hairpin token: a kink at any scale
                    c += 100.0
                out.append((c, a, n, m, net))
        out.sort(key=lambda t: (t[0], t[1], t[2]))
        return out[:keep]

    def tokens(self, a: int, n: int, m: float) -> list:
        segs = [dict(s) for b in self.bends[a:a + n] for s in b]
        if m < 0:
            for s in segs:
                s["k0"], s["k1"], s["sgn"] = -s["k0"], -s["k1"], -s["sgn"]
                if s["corner"] is not None:
                    s["corner"] = -s["corner"]
        toks = vh.to_tokens(segs, True)
        return gm.round_corners(toks, 0.05) if any(t[0] == "corner" for t in toks) else toks

    def take(self, sign: float, target_net: float, target_len_R: float, R: float = 1.0, step: float = 0.01,
             start=(0.0, 0.0), heading: float = 0.0, simple: bool = True):
        """The best window that, drawn at scale R, does not cross itself (a
        river never does); None if none of the candidates qualifies.
        Returns (points, tokens, net, info) and advances the pointer."""
        from shapely.geometry import LineString  # noqa: PLC0415
        for c, a, n, m, net in self.candidates(sign, target_net, target_len_R):
            toks = self.tokens(a, n, m)
            p, _ = integrate_tokens(toks, R, start=start, heading=heading, step=step)
            if simple and len(p) > 3 and not LineString(p).is_simple:
                continue
            self.ptr = a + n
            return p, toks, net, {"window": [int(a), int(n)], "mirror": bool(m < 0), "cost": round(float(c), 3)}
        return None


# ---------------------------------------------------------------------------
# events at the nearest approach
# ---------------------------------------------------------------------------

def _from_turning(th: np.ndarray, n_out: int, close: bool = False) -> np.ndarray:
    """Unit-length polyline from a turning function sampled at len(th)
    steps, resampled to n_out steps (cubic in θ, so a big loop has no
    facets); close=True takes the closure gap out of the tangent vectors."""
    n = len(th)
    u = (np.arange(n) + 0.5) / n
    uu = (np.arange(n_out) + 0.5) / n_out
    t2 = CubicSpline(u, th)(uu) if n >= 4 else np.interp(uu, u, th)
    v = np.column_stack([np.cos(t2), np.sin(t2)]) / n_out
    if close:
        v = v - v.sum(0) / n_out
    return np.vstack([[0.0, 0.0], np.cumsum(v, axis=0)])


def neck_loop(loops: dict, target_net: float, rng, n_out: int = 128) -> tuple[np.ndarray, float, float, int]:
    """A real cut-off bend whole: the profile whose net turn is nearest the
    target (ties broken by rng among the 5 nearest). Unit length, start at
    origin heading +x, turning positive. Returns (pts, net, La_w, index)."""
    X = loops["neck_phi"]
    net = X[:, -1] - X[:, 0]
    order = np.argsort(np.abs(net - abs(target_net)), kind="stable")[:5]
    i = int(order[int(rng.integers(len(order)))])
    pts = _from_turning(X[i] - X[i, 0], n_out)
    La = float(loops["neck_La_w"][i])
    return pts, float(net[i]), La if np.isfinite(La) else float("nan"), i


def oxbow_loop(loops: dict, rng, n_out: int = 128) -> tuple[np.ndarray, int]:
    """A real oxbow lake outline whole (closed exactly), unit perimeter."""
    X = loops["oxbow_phi"]
    i = int(rng.integers(len(X)))
    n = X.shape[1]
    th = X[i] + 2 * np.pi * np.arange(n) / n
    return _from_turning(th - th[0], n_out, close=True), i


def _place(pts, at, heading, scale, sign):
    q = np.asarray(pts, float) * scale
    if sign < 0:
        q = q * np.array([1.0, -1.0])
    R = np.array([[math.cos(heading), -math.sin(heading)], [math.sin(heading), math.cos(heading)]])
    return q @ R.T + at


# ---------------------------------------------------------------------------
# the line
# ---------------------------------------------------------------------------

def approach_line(geom: StemGeom, *, start: float, length_w: float, approaches: list[dict],
                  hands: list[HandChain], handover: str, share: float, loops: dict | None,
                  event: str, events: int, rng, h: float = 0.1, persist: float = 0.5,
                  simple: bool = True):
    """Pure geometry. Paper units: 1 = one channel width at the far zoom.
    The schedule k(τ) is over the line AS DRAWN (τ = paper share), so the
    twists grow and shrink gradually on the page; the stem consumed is
    ∫ dτ·length / k. Returns (points (N,2), channels {zoom, src, stem_u}, info)."""
    tau = np.linspace(0.0, 1.0, 20001)
    ktau = zoom_at(tau, approaches)
    du = np.r_[0.0, np.cumsum(0.5 * (1 / ktau[1:] + 1 / ktau[:-1]) * np.diff(tau))] * length_w
    span_w = float(du[-1])
    if span_w > geom.L - 1.0:                  # the stem is finite: the line gets shorter, never runs off it
        du = du * (geom.L - 1.0) / span_w
        span_w = float(du[-1])
    U0 = start * (geom.L - span_w)
    U1 = U0 + span_w
    u_grid, k_grid = U0 + du, ktau
    kfun = lambda u: np.interp(np.asarray(u, float), u_grid, k_grid)  # noqa: E731
    # stem bends inside the stretch, clipped to it
    B = [(max(a, U0), min(b, U1)) for a, b in geom.bends if b > U0 and a < U1]
    B = [(a, b) for a, b in B if b - a > 1e-6]
    mids = np.array([(a + b) / 2 for a, b in B])
    kmid = kfun(mids)
    kmax = np.array([float(kfun(np.linspace(a, b, 24)).max()) for a, b in B])
    nets = np.array([geom.net(a, b) for a, b in B])
    # which approach each bend belongs to (nearest centre in t)
    tm = np.interp(mids, u_grid, tau)
    owner = np.argmin(np.abs(tm[:, None] - np.array([a["c"] for a in approaches])[None, :]), axis=1) \
        if approaches else np.zeros(len(B), int)
    # events: per approach, the tightest bends near its peak
    ev_set: set[int] = set()
    if event != "none" and loops is not None and events > 0:
        deepest = max(a["peak"] for a in approaches)
        for j, a in enumerate(approaches):
            if a["peak"] < deepest - 1e-9:          # the event belongs to the nearest approach only
                continue
            near = [i for i in range(len(B)) if kmax[i] >= a["peak"] ** 0.75 and a["peak"] > 2.0]
            near.sort(key=lambda i: (-abs(nets[i]), i))
            picked: list[int] = []
            for i in near:
                if all(abs(i - p) > 2 for p in picked):
                    picked.append(i)
                if len(picked) >= events:
                    break
            ev_set.update(picked)
    # hand ladder
    kh = np.array([FAR_W / c.zoom_w for c in hands]) if hands else np.zeros(0)
    pts = [np.zeros((1, 2))]
    ch_zoom, ch_src, ch_u = [np.ones(1)], [np.zeros(1)], [np.full(1, U0)]
    pos = np.zeros(2)
    off = 0.0                                  # paper heading − stem heading (course error)
    resid = 0.0
    state = False
    info = {"bends": len(B), "handed": [], "events": [], "U": [float(U0), float(U1)]}
    n_src = len(hands) + 1
    first_heading = float(geom.theta(U0))

    def stem_piece(ua, ub):
        nonlocal pos
        ug = np.linspace(ua, ub, max(int((ub - ua) / 0.02) + 2, 2))
        k = kfun(ug)
        S = np.r_[0.0, np.cumsum(0.5 * (k[1:] + k[:-1]) * np.diff(ug))]
        n = max(int(S[-1] / h), 1)
        s = np.linspace(0.0, S[-1], n + 1)
        uu = np.interp(s, S, ug)
        th = geom.theta(uu) - first_heading + off
        thm = 0.5 * (th[1:] + th[:-1])
        ds = np.diff(s)
        p = pos + np.vstack([np.zeros((1, 2)), np.cumsum(np.column_stack([np.cos(thm), np.sin(thm)]) * ds[:, None], axis=0)])
        pos = p[-1]
        return p[1:], kfun(uu[1:]), uu[1:]

    for i, (ua, ub) in enumerate(B):
        km = float(kmid[i])
        heading = float(geom.theta(ua)) - first_heading + off
        sign = 1.0 if nets[i] >= 0 else -1.0
        L_paper = float(np.trapezoid(kfun(np.linspace(ua, ub, 16)), np.linspace(ua, ub, 16)))
        # --- event
        if i in ev_set:
            if event == "neck":
                pick = int(rng.integers(1 << 31))                       # same profile for the size and the points
                _, _, La, _ = neck_loop(loops, nets[i] - resid, np.random.default_rng(pick), n_out=8)
                ratio = La / max(ub - ua, 1e-9) if np.isfinite(La) else 1.0
                size = L_paper * float(np.clip(ratio, 0.6, 1.1))       # the cut-off at the bend's own scale
                lp, lnet, La, li = neck_loop(loops, nets[i] - resid, np.random.default_rng(pick),
                                             n_out=int(np.clip(size / h, 64, 20000)))
                q = _place(lp, pos, heading, size, sign)
                pts.append(q[1:])
                ch_zoom.append(np.full(len(q) - 1, km))
                ch_src.append(np.full(len(q) - 1, float(n_src)))
                ch_u.append(np.full(len(q) - 1, (ua + ub) / 2))
                pos = q[-1]
                end_h = heading + sign * lnet
                resid += sign * lnet - nets[i]
                off = end_h - (float(geom.theta(ub)) - first_heading)
                info["events"].append({"bend": i, "kind": "neck", "profile": li, "La_w": La, "zoom": km})
                state = False
                continue
            if event == "oxbow":
                um = (ua + ub) / 2
                p1, z1, u1 = stem_piece(ua, um)
                pts.append(p1); ch_zoom.append(z1); ch_src.append(np.zeros(len(p1))); ch_u.append(u1)
                hd = float(geom.theta(um)) - first_heading + off
                lp, li = oxbow_loop(loops, rng, n_out=int(np.clip(0.8 * L_paper / h, 64, 20000)))
                q = _place(lp, pos, hd, 0.8 * L_paper, -sign)        # the lake bulges outward of the bend
                pts.append(q[1:])
                ch_zoom.append(np.full(len(q) - 1, km)); ch_src.append(np.full(len(q) - 1, float(n_src)))
                ch_u.append(np.full(len(q) - 1, um))
                pos = q[-1]
                p2, z2, u2 = stem_piece(um, ub)
                pts.append(p2); ch_zoom.append(z2); ch_src.append(np.zeros(len(p2))); ch_u.append(u2)
                info["events"].append({"bend": i, "kind": "oxbow", "profile": li, "zoom": km})
                continue
        # --- handover
        j = -1
        if hands and handover != "none":
            lk = math.log(max(km, 1.0))
            jn = int(np.argmin(np.abs(np.log(kh) - lk)))
            if handover == "ladder":
                lo = math.log(kh.min()) - math.log(2.0)
                p = share * float(np.clip((lk - lo) / math.log(2.0), 0.0, 1.0))
            else:                                               # peak
                pk = approaches[owner[i]]["peak"] if approaches else 1.0
                p = share if (pk > 2.0 and km >= pk ** 0.75) else 0.0
            pon = p + persist * (1 - p) if state else p * (1 - persist)
            state = bool(rng.random() < pon) and p > 0
            if state:
                j = jn
        if j >= 0:
            c = hands[j]
            R_paper = c.R_w * km                               # mm per R at this zoom
            got = c.take(sign, nets[i] - resid, L_paper / R_paper, R=R_paper, step=h, start=pos, heading=heading,
                         simple=simple)
            if got is not None:
                p_, toks, wnet, winfo = got
                end_h = gm.end_heading(toks, heading)
                pts.append(p_[1:])
                ch_zoom.append(np.full(len(p_) - 1, km))
                ch_src.append(np.full(len(p_) - 1, float(j + 1)))
                ch_u.append(np.linspace(ua, ub, len(p_) - 1))
                pos = p_[-1]
                resid += (end_h - heading) - nets[i]
                off = end_h - (float(geom.theta(ub)) - first_heading)
                info["handed"].append({"bend": i, "hand": j, "zoom": km, **winfo})
                continue
        p_, z_, u_ = stem_piece(ua, ub)
        pts.append(p_); ch_zoom.append(z_); ch_src.append(np.zeros(len(p_))); ch_u.append(u_)
    P_ = np.vstack(pts)
    ch = {"zoom": np.concatenate(ch_zoom), "src": np.concatenate(ch_src), "stem_u": np.concatenate(ch_u)}
    info["resid_deg"] = math.degrees(resid)
    return P_, ch, info


def resample_line(P_: np.ndarray, ch: dict, step: float, nearest=("src", "stem_u")):
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P_, axis=0), axis=1))]
    keep = np.r_[True, np.diff(s) > 0]
    P_, s = P_[keep], s[keep]
    ch = {k: v[keep] for k, v in ch.items()}
    n = max(int(s[-1] / step), 2)
    t = np.linspace(0.0, s[-1], n + 1)
    out = np.column_stack([np.interp(t, s, P_[:, 0]), np.interp(t, s, P_[:, 1])])
    idx = np.clip(np.searchsorted(s, t), 0, len(s) - 1)
    chn = {k: (v[idx] if k in nearest else np.interp(t, s, v)) for k, v in ch.items()}
    return out, chn


def frame_fit(P_: np.ndarray, box, angle_deg: float, mm: float) -> tuple[np.ndarray, float, float]:
    """Principal axis → horizontal, then angle; at `mm` per unit. Returns
    (rotated pts, scale actually used ≤ mm, coverage of the box)."""
    c = P_.mean(axis=0)
    ev = np.linalg.eigh(np.cov((P_ - c).T))[1][:, -1]
    Q = rotate(P_, c, angle_deg - math.degrees(math.atan2(ev[1], ev[0])))
    span = np.ptp(Q, axis=0)
    s = min(mm, box[2] / max(span[0], 1e-9), box[3] / max(span[1], 1e-9))
    return Q, float(s), float(span[0] * span[1] * s * s / (box[2] * box[3]))


# ---------------------------------------------------------------------------
# the voice
# ---------------------------------------------------------------------------

@voice("river_approach", params=[
    P("stems", "ref", FAR_STEMS, "frozen far-view stem (library kind river_stems)", kind="river_stems"),
    P("tile", "choice", "SB19", "GRWL tile", choices=("SB18", "SB19", "SB20", "SC18", "SC20")),
    P("rank", "int", 0, "which stem, longest first", min=0, max=20),
    P("start", "float", 0.0, "where the stretch starts along the stem (share)", min=0.0, max=1.0),
    P("length_w", "int", 7000, "the line's length on paper, in channel widths at the far zoom (the stem consumed "
      "is less: ∫ 1/k)", min=300, max=12000),
    P("approaches", "int", 4, "how many times the camera moves in", min=1, max=4),
    P("peak", "float", 40.0, "nearest approach, × the far zoom", min=1.0, max=60.0),
    P("width", "float", 0.8, "share of the drawn line inside approaches (split between them)", min=0.05, max=0.95),
    P("skew", "float", 0.55, "> 0: slow approach, quick retreat; < 0 the reverse", min=-0.9, max=0.9),
    P("vary", "float", 0.7, "how unequal the approaches are (peak, width, skew)", min=0.0, max=1.0),
    P("handover", "choice", "ladder", "none: the magnified stem only | ladder: each closer hand takes stem bends "
      "in its own zoom band | peak: the nearest hand only, near each peak", choices=("none", "ladder", "peak")),
    P("hands", "refs", ["river_belt", "river_meander", "river_bend"], "closer-zoom hands (round 11)", kind="hand",
      min_len=1, max_len=5),
    P("share", "float", 0.5, "share of stem bends handed over inside a hand's zoom band", min=0.0, max=1.0),
    P("simple", "bool", True, "river law: a handed window may not cross itself (false lets the belt's curls in)"),
    P("persist", "float", 0.5, "how sticky a handover is from bend to bend", min=0.0, max=0.95),
    P("event", "choice", "neck", "at the nearest approach: none | neck (a real cut-off bend) | oxbow",
      choices=("none", "neck", "oxbow")),
    P("events", "int", 1, "event bends at the nearest approach", min=0, max=3),
    P("loops", "ref", "river_cutoffs", "learned cut-off bends and oxbows", kind="river_loops"),
    P("far_mm", "float", 1.0, "cap on mm per channel width at the far zoom: the planned line is drawn as large "
      "as the box allows, never larger than this (0.25 ≈ the found river's far view)", min=0.05, max=1.5),
    P("plan", "int", 10, "candidate lines tried against the frame", min=1, max=40),
    P("angle", "float", 0.0, "turn the line from its principal axis, degrees", min=-180.0, max=180.0),
], doc="the far Amazon stem, approached and left: zoom grows along the line and closer river hands take whole bends")
def river_approach(ctx, *, stems, tile, rank, start, length_w, approaches, peak, width, skew, vary, handover,
                   hands, share, simple, persist, event, events, loops, far_mm, plan, angle):
    seg, wm, q = stem(ctx, stems, tile, rank)
    geom = stem_geom(q, wm)
    grams = [ctx.use("hand", hid) for hid in hands] if handover != "none" else []
    zooms = [HAND_ZOOM.get(hid, DEFAULT_ZOOM) for hid in hands]
    Rws = [geom.diag_w(z) for z in zooms]
    loop_data = ctx.use("river_loops", loops) if event != "none" else None
    box = ctx.box

    def build(c: int, h: float):
        rng = ctx.rng("plan", c)
        st = float(np.clip(start + (0.0 if c == 0 else rng.uniform(-0.08, 0.08)), 0.0, 1.0))
        ap = make_approaches(rng, n=approaches, peak=peak, width=width, skew=skew, vary=vary)
        chains = [HandChain(g, ctx.rng("hand", c, k), zooms[k], Rws[k]) for k, g in enumerate(grams)]
        P_, ch, info = approach_line(geom, start=st, length_w=length_w, approaches=ap, hands=chains,
                                     handover=handover, share=share, loops=loop_data, event=event, events=events,
                                     rng=ctx.rng("line", c), h=h, persist=persist, simple=simple)
        info.update(start=st, approaches=ap)
        return P_, ch, info

    def turn(c):
        return angle + (0.0 if c == 0 else float(ctx.rng("turn", c).uniform(-20.0, 20.0)))

    best = None
    for c in range(plan):
        P_, ch, info = build(c, 0.5)
        _, s, cov = frame_fit(P_, box, turn(c), far_mm)
        key = (round(s / far_mm, 2), cov)                     # fits at full scale first, then fills the box
        if best is None or key > best[0]:
            best = (key, c)
    c = best[1]
    P_, ch, info = build(c, 0.1)
    Q, s, cov = frame_fit(P_, box, turn(c), far_mm)
    Q, ch = resample_line(Q, ch, 0.12 / s)
    lo, hi = Q.min(axis=0), Q.max(axis=0)
    off = np.array([box[0] + box[2] / 2, box[1] + box[3] / 2]) - (lo + hi) / 2 * s
    voices = [f"grwl:{tile}:seg{seg}"] + list(hands if handover != "none" else []) + [f"{event}:{loops}"]
    ch["voice"] = np.minimum(ch["src"], len(voices) - 1)
    meta = {"voices": voices, "found": f"grwl:{tile}:seg{seg}", "channel_w_m": wm, "plan_pick": c,
            "approach": info, "R_w": dict(zip(hands, Rws)), "far_mm_used": s, "coverage": cov, "turn": turn(c),
            "rights": "GRWL V01.01, Allen & Pavelsky 2018, CC BY 4.0",
            "fit": {"scale": s, "offset": [float(off[0]), float(off[1])]}}
    return [Mark(Q * s + off, ch, meta)]
