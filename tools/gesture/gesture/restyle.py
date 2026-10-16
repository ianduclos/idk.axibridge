"""Restyle as translation: keep a line's structure, redraw it in a hand.

Stage 6 operation 3 of docs/IDEAS-gesture-bank.md ("structure from A, hand
from B"), developed from grammar v3's minimal `restyle`. Results and the
method comparison: tools/gesture/results/restyle-2026-10-16.md.

Every stroke is handled as its **turning function** θ(s): a start point,
uniform arc-length samples (step h = `STEP`·R) and the heading of each step.
A restyle is

    θ_out = θ_structure + r_hand + δθ_fix

1. **Decomposition** (`method`) — what of the source is kept:
   - ``"gauss"``    θ low-passed at the structure scale σ_s (Gaussian on κ,
                    i.e. curvature scale space); positions pinned every
                    `SPACING`·σ_s.
   - ``"clothoid"`` θ of a clothoid fit (`clothoid.fit_stroke`) at σ_s:
                    lines/arcs/clothoids with sharp corners; positions pinned
                    as for gauss and at every fitted corner.
   - ``"anchors"``  only the curvature extrema of the σ_s view (Attneave
                    points: position + tangent), plus ends and fill-ins at
                    most `GAP_MAX`·σ_s apart. Between anchors the base is the
                    linear θ interpolation (the plainest arc/clothoid), and
                    the hand gets a wider band (`ANCHOR_HAND`·σ_s).
2. **Re-synthesis** (`source`) — where the hand detail r comes from:
   - ``"chain"``      a stroke of the same length from the grammar's order-2
                      chain, its θ high-passed at the residual scale.
   - ``"transplant"`` real residuals: the grammar's training strokes
                      (both directions), high-passed at the same scale, cut
                      into windows; for each window of the output the
                      training window with the most similar coarse κ profile
                      (random among the `TOP_K` nearest) is overlap-added
                      (Hann, 50 % hop). Quotes micro-texture, matched to
                      context (Kalnins' base path + learned residual).
3. **Structure-fidelity constraint** — a low-band correction δθ (Gaussian
   bumps at the structure scale) solved by damped Gauss–Newton so the line
   passes within `TOL`·σ_s of the pinned positions (and headings, for
   anchors). Closed strokes close exactly (position) and κ-continuously
   (periodic residual and basis). Step length is stretched by 1/⟨cos r⟩ so
   the wiggle does not pull the pins apart.

**The slider.** `amount` ∈ [0, 1] sets σ_s = `SIGMA_HI`·amount^`SIGMA_POW`·R:
0 returns the source unchanged; small amounts keep almost everything and
swap only the finest texture; 1 keeps the structure only at ~0.12 R (a few
pins per figure) and lets the hand own everything below.

Units follow the README contract: points in px, R = the drawing's
ref_length (bbox diagonal), grammar tokens dimensionless in R. Pure and
deterministic: inputs are never mutated; randomness via np.random.Generator
or a seed (one child stream per stroke, independent of `amount`).

Uses the FROZEN grammar v4 (`grammar_v4_frozen`, since the composite round
of 2026-10-16; v3 before). `source="chain"` uses v4's source-stroke runs
(`P_FOLLOW`, `MAX_RUN`), and so does `trace` (`TRACE_FOLLOW`): the runs carry
more of the hand (pairwise hand test 0.75–0.90 vs 0.45–0.80 without) at the
price of more corners (rate ≈ 3.9 vs 3.2; real 1.3–1.6). Any object with
the same `strokes`, `name` and v4 chain interface (`draw` returning
(kind, params, record)) works. `source="trace_ln"` takes a
`lognormal.Hand` instead and redraws the structure pulse by pulse.

**Junction welding** (`restyle_drawing(weld=True)`, default): an open end that
touched another stroke in the source (T-junction, branch start, end-to-end
join) is moved onto the *restyled* host at the same structural position,
with a cosine fade over ≈ 2 σ_s, so trees stay welded.

**Structure scale** (`scale`): ``"drawing"`` (default) σ_s in R of the
drawing; ``"stroke"`` σ_s in a per-stroke feature length ℓ = length per
quarter-turn of the stroke (smoothed at 0.01 R), capped at R — the slider
then means the same on a spiral as on a tree limb.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from scipy.spatial import cKDTree

from . import grammar_v4_frozen as gm
from .core import Drawing, Stroke
from .curvature import resample, smooth

METHODS = ("gauss", "clothoid", "anchors")
SOURCES = ("chain", "transplant", "trace")
SOURCES_ALL = SOURCES + ("trace_ln",)   # trace_ln: g is a lognormal.Hand

STEP = 1.0 / 2000.0      # sample spacing, R units
SIGMA0 = 0.0015          # light pre-smoothing of the source (≈ a line width), R units
SIGMA_HI = 0.12          # structure scale at amount = 1, R units
SIGMA_POW = 1.5          # σ_s = SIGMA_HI · amount^SIGMA_POW · R
SPACING = 2.0            # gauss/clothoid: pins every SPACING·σ_s
BASIS = 0.75             # correction bumps: width and spacing BASIS·σ_s
MAX_BASIS = 240          # cap on bumps per stroke (spacing grows instead)
TOL = 0.02               # pin tolerance, σ_s units (the fidelity constraint)
TOL_HEAD = 0.05          # anchor heading tolerance, rad
STRETCH_MAX = 1.6        # pin alignment may stretch an interval's steps at most this much
N_ITER = 8               # Gauss–Newton iterations
ANCHOR_PROM = 0.75       # anchor: |κ_c|·R peak prominence
GAP_MAX = 4.0            # anchors at most this many σ_s apart
ANCHOR_HAND = 1.5        # anchors: hand residual band = this × σ_s
WIN = 2.0                # transplant window = WIN·σ_r samples ...
WIN_MIN, WIN_MAX = 24, 320   # ... clamped to this many samples
TOP_K = 6                # transplant: random among the TOP_K nearest windows
CTX_N = 6                # transplant: coarse-κ context sampled at this many points
TRACE_KMAX = 16          # trace: proposals per token at amount → 0 ...
TRACE_KMIN = 2           # ... and at amount = 1 (k = KMIN + (KMAX−KMIN)(1−amount))
TRACE_LOOK = 0.03        # trace: look-ahead ray, R units
TRACE_FOLLOW = True      # trace: v4 source-stroke runs (P_FOLLOW, MAX_RUN); off = fewer corners, weaker hand identity (composite-2026-10-16.md)
WELD_R = 0.006           # weld: a source end this close (R units) to another stroke is a junction
WELD_FADE = 2.0          # weld: the end correction fades out over this many σ_s (≤ half the stroke)
STROKE_K = 2.0           # scale="stroke": σ_s = sigma_of(amount) · min(R, STROKE_K · ℓ)


def sigma_of(amount: float) -> float:
    """Structure scale σ_s in R units for a slider value."""
    a = float(np.clip(amount, 0.0, 1.0))
    return SIGMA_HI * a ** SIGMA_POW


# ---------------------------------------------------------------------------
# turning-function plumbing
# ---------------------------------------------------------------------------

def _resample_n(points: np.ndarray, n: int, closed: bool) -> np.ndarray:
    """n steps of equal arc length: n+1 points (open) or n points (closed)."""
    p = np.vstack([points, points[:1]]) if closed else points
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    t = np.linspace(0.0, s[-1], n + 1)
    if closed:
        t = t[:-1]
    return np.column_stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])])


def _headings(p: np.ndarray, closed: bool) -> np.ndarray:
    q = np.vstack([p, p[:1]]) if closed else p
    d = np.diff(q, axis=0)
    return np.unwrap(np.arctan2(d[:, 1], d[:, 0]))


def _integrate(p0, theta: np.ndarray, h) -> np.ndarray:
    """Positions from θ; h is a scalar step or one step per sample."""
    steps = np.column_stack([np.cos(theta), np.sin(theta)]) * np.reshape(h, (-1, 1))
    return np.vstack([np.asarray(p0, float)[None, :], np.asarray(p0, float) + np.cumsum(steps, axis=0)])


def _total_turn(theta: np.ndarray) -> float:
    """Turning of a closed θ sequence, a multiple of 2π (wrap step included)."""
    last = theta[-1] - theta[0]
    return float(2 * np.pi * np.round((last + _wrap(theta[0] - theta[-1])) / (2 * np.pi)))


def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def _lowpass(theta: np.ndarray, sd: float, closed: bool, turn: float = 0.0) -> np.ndarray:
    """θ with its κ = Δθ Gaussian-smoothed at sd samples (mean heading kept;
    closed: periodic, total turning kept)."""
    if sd <= 0 or len(theta) < 3:
        return theta.copy()
    if closed:
        d = np.diff(np.append(theta, theta[0] + turn))
        sm = gaussian_filter1d(d, sd, mode="wrap")
    else:
        sm = gaussian_filter1d(np.diff(theta), sd, mode="nearest")
    th = theta[0] + np.concatenate([[0.0], np.cumsum(sm[:len(theta) - 1])])
    return th + np.mean(theta - th)


@dataclass
class _Src:
    p: np.ndarray        # pins live here: (M+1, 2) open, (M, 2) closed (positions per index)
    theta: np.ndarray    # (M,)
    h: float
    closed: bool
    turn: float          # total turning (closed), 0 for open
    raw: np.ndarray      # untouched input points


def _source(points: np.ndarray, closed: bool, R: float) -> _Src | None:
    pts = np.array(points, dtype=np.float64, copy=True)
    h0 = STEP * R
    r = resample(pts, h0, closed=closed)
    if len(r) < 4:
        return None
    sm = smooth(r, SIGMA0 * R, h0, closed=closed)
    q = np.vstack([sm, sm[:1]]) if closed else sm
    L = float(np.sum(np.linalg.norm(np.diff(q, axis=0), axis=1)))
    M = max(int(round(L / h0)), 8)
    p = _resample_n(sm, M, closed)
    th = _headings(p, closed)
    return _Src(p, th, L / M, closed, _total_turn(th) if closed else 0.0, pts)


# ---------------------------------------------------------------------------
# hand residuals
# ---------------------------------------------------------------------------

def _hand_theta_chain(g, rng, M: int, R: float, h: float) -> np.ndarray:
    """θ (M samples, step h) of chain output, chained stroke after stroke
    until long enough (heading continuous across the joins)."""
    out: list[np.ndarray] = []
    got, last, tries = 0, 0.0, 0
    while got < M and tries < 50:
        tries += 1
        need = (M - got + 4) * h / R
        toks, _ = gm.generate_tokens(g, rng, length=need, p_follow=gm.P_FOLLOW)
        if not toks:
            continue
        pts, _, _ = gm.tokens_to_points(toks, R, step=h)
        if len(pts) < 3:
            continue
        L = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
        n = max(int(round(L / h)), 2)
        th = _headings(_resample_n(pts, n, False), False)
        th = th - th[0] + last
        out.append(th)
        got += len(th)
        last = th[-1]
    if not out:
        return np.zeros(M)
    th = np.concatenate(out)
    return th[:M] if len(th) >= M else np.concatenate([th, np.full(M - len(th), th[-1])])


def _highpass(theta: np.ndarray, sd: float) -> np.ndarray:
    r = theta - _lowpass(theta, sd, False)
    return r - r.mean()


def _periodic(r_ext: np.ndarray, M: int) -> np.ndarray:
    """A residual of length ≥ M+O made periodic over M by crossfading its
    tail into its head."""
    O = len(r_ext) - M
    r = r_ext[:M].copy()
    if O > 0:
        w = np.linspace(0.0, 1.0, O, endpoint=False)
        r[:O] = w * r_ext[:O] + (1 - w) * r_ext[M:M + O]
    return r - r.mean()


def residual_chain(g, rng, M: int, sd: float, R: float, h: float, closed: bool) -> np.ndarray:
    O = int(min(max(3 * sd, 8), M // 2)) if closed else 0
    th = _hand_theta_chain(g, rng, M + O, R, h)
    r = _highpass(th, sd)
    return _periodic(r, M) if closed else r


_POOL: dict = {}


def _pool_thetas(g) -> list[np.ndarray]:
    """Training strokes of a grammar as θ arrays at STEP (R = 1), both
    directions. Cached per grammar object."""
    key = ("theta", id(g), len(g.strokes))
    if key not in _POOL:
        out = []
        for toks in g.strokes:
            if gm.stroke_length(toks) < 8 * STEP:
                continue
            pts, _, _ = gm.tokens_to_points(toks, 1.0, step=STEP)
            L = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
            n = max(int(round(L / STEP)), 2)
            th = _headings(_resample_n(pts, n, False), False)
            out.append(th)
            out.append(th[::-1] + np.pi)
        _POOL[key] = out
    return _POOL[key]


def _ctx_feat(kc: np.ndarray, W: int) -> np.ndarray:
    """Coarse-κ context of a window: κ·R at CTX_N points, asinh-compressed."""
    idx = np.linspace(0, W - 1, CTX_N).astype(int)
    return np.arcsinh(kc[..., idx] / gm.KAPPA_SCALE)


def _pool_windows(g, sd: float, W: int):
    key = ("win", id(g), len(g.strokes), round(sd, 3), W)
    if key not in _POOL:
        res, ctx = [], []
        for th in _pool_thetas(g):
            if len(th) < W:
                continue
            lo = _lowpass(th, sd, False)
            r = th - lo
            kc = np.diff(np.append(lo, lo[-1])) / STEP          # κ·R (R = 1)
            for a in range(0, len(th) - W + 1, max(W // 4, 1)):
                res.append(r[a:a + W])
                ctx.append(_ctx_feat(kc[a:a + W], W))
        if len(res) < TOP_K:
            _POOL[key] = None
        else:
            C = np.array(ctx)
            _POOL[key] = (np.array(res), C, cKDTree(C))
    return _POOL[key]


def residual_transplant(g, rng, base: np.ndarray, sd: float, h: float, R: float,
                        closed: bool) -> np.ndarray:
    """Overlap-add real residual windows matched by coarse κ of `base`."""
    M = len(base)
    sd = float(np.exp(np.round(np.log(max(sd, 1.0)) * 10) / 10))   # quantised: pool cache key
    W = int(np.clip(round(WIN * sd), WIN_MIN, WIN_MAX))
    W = min(W, max(M, WIN_MIN))
    while True:
        pw = _pool_windows(g, sd, W)
        if pw is not None or W <= WIN_MIN // 2:
            break
        W //= 2
    if pw is None:
        return np.zeros(M)
    res, _C, tree = pw
    W = res.shape[1]
    turn = _total_turn(base) if closed else 0.0
    d = np.diff(np.append(base, base[0] + turn)) if closed else np.diff(np.append(base, base[-1]))
    kc = d / h * R                                            # κ·R of the structure
    hop = max(W // 2, 1)
    win = np.sin(np.pi * (np.arange(W) + 0.5) / W) ** 2       # Hann, sums to 1 at 50 % hop
    acc, wsum = np.zeros(M), np.zeros(M)
    starts = range(0, M, hop) if closed else range(-hop, M, hop)
    for a in starts:
        idx = np.arange(a, a + W)
        if closed:
            idx = idx % M
            q = kc[idx]
        else:
            valid = (idx >= 0) & (idx < M)
            q = kc[np.clip(idx, 0, M - 1)]
        k = min(TOP_K, len(res))
        _, nn = tree.query(_ctx_feat(q, W), k=k)
        j = int(np.atleast_1d(nn)[int(rng.integers(k))])
        piece = res[j] - np.average(res[j], weights=win)
        if closed:
            np.add.at(acc, idx, win * piece)
            np.add.at(wsum, idx, win)
        else:
            acc[idx[valid]] += (win * piece)[valid]
            wsum[idx[valid]] += win[valid]
    r = acc / np.maximum(wsum, 1e-9)
    return r - r.mean()


def _tok_points(tok, R, pos, heading, h):
    """Integrate one token from pos/heading: (points incl. start, end heading)."""
    if tok[0] == "corner":
        return pos[None, :], heading + tok[1]
    pts, _, _ = gm.tokens_to_points([tok], R, start=pos, heading=heading, step=h)
    return pts, gm.end_heading([tok], heading)


def trace_theta(g, rng, path: np.ndarray, theta_path: np.ndarray, h: float, R: float,
                k: int, look: float = TRACE_LOOK) -> np.ndarray:
    """The hand redraws `path` (positions at step h, M+1 points) token by
    token: the chain proposes k continuations from its own context; the one
    whose points (plus a look-ahead ray of `look`·R along its end tangent)
    stay closest to the path at matching arc length is kept. Nothing is
    inserted or bent: every kept token is one the chain proposed. Returns
    the traced line's θ resampled to M samples."""
    M = len(path) - 1
    L = M * h
    Lr = L / R
    pos, head = path[0].astype(float), float(theta_path[0])
    p2, p1 = ["START"], ["START"]
    toks: list = []
    pts_all = [pos[None, :]]
    s = 0.0
    nlook = max(int(look * R / h), 2)
    rec, run = None, 0
    for _ in range(4 * gm.MAX_TOKENS):
        if s >= L - h:
            break
        best, best_sc = None, np.inf
        pf = gm.P_FOLLOW if (TRACE_FOLLOW and run < gm.MAX_RUN) else 0.0
        for _k in range(max(k, 1)):
            kind, par, rec_k = g.draw(p2, p1, s / R, Lr, rng, prev_rec=rec, p_follow=pf)
            tok = gm._tok_corner(par[0]) if kind == "corner" else gm._tok_seg(kind, *par)
            if kind == "corner" and (not toks or toks[-1][0] == "corner"):
                continue
            newprev, tok = gm._continuity(p1 if p1[0] != "START" else None, tok)
            if tok[0] != "corner" and s + tok[1] * R > L:
                f = max(L - s, h) / (tok[1] * R)
                tok = gm._tok_seg(tok[0], tok[1] * f, tok[2], tok[2] + (tok[3] - tok[2]) * f)
            P, eh = _tok_points(tok, R, pos, head, h)
            n = len(P) - 1
            ray = P[-1] + np.outer(np.arange(1, nlook + 1) * h, [np.cos(eh), np.sin(eh)])
            Q = np.vstack([P[1:], ray]) if n > 0 else ray
            i0 = int(round(s / h)) + 1
            idx = np.clip(np.arange(i0, i0 + len(Q)), 0, M)
            sc = float(np.mean(np.linalg.norm(Q - path[idx], axis=1)))
            if sc < best_sc:
                best, best_sc = (tok, newprev, P, eh, rec_k), sc
            if k <= 1:
                break
        if best is None:
            continue
        tok, newprev, P, eh, rec_k = best
        run = run + 1 if (rec is not None and rec_k == rec + 1) else 0
        rec = rec_k
        if toks and newprev is not None and newprev is not p1 and toks[-1] is p1:
            toks[-1] = newprev
        toks.append(tok)
        if len(P) > 1:
            pts_all.append(P[1:])
        pos, head = P[-1].astype(float), eh
        if tok[0] != "corner":
            s += tok[1] * R
        p2, p1 = (toks[-2] if len(toks) >= 2 else p1), toks[-1]
    pts = np.vstack(pts_all)
    if len(pts) < 3:
        return theta_path.copy()
    th = _headings(_resample_n(pts, M, False), False)
    return th + 2 * np.pi * np.round((theta_path[0] - th[0]) / (2 * np.pi))


def trace_theta_ln(hand, rng, path: np.ndarray, theta_path: np.ndarray, h: float, R: float,
                   k: int, look: float = TRACE_LOOK) -> np.ndarray:
    """`trace_theta` with a kinematic hand (`lognormal.Hand`): the line grows
    pulse by pulse from the hand's own order-2 chain; of k proposed next
    pulses the one whose re-integrated window (plus a look-ahead ray) stays
    closest to the path at matching arc length is committed. Pulses overlap,
    so a commit also re-shapes the tail of the line drawn so far — the
    kinematic hand's characteristic smoothness."""
    from . import lognormal as ln
    M = len(path) - 1
    L = M * h
    line = ln._Line(path[0], h)
    nlook = max(int(look * R / h), 2)
    stride = 4

    def score(t_a, tg, Xw):
        _Tk, _Xk, sk = line.old_part(t_a)
        s0 = sk[-1] if len(sk) else 0.0
        ss = s0 + ln.arclength(Xw)
        if len(Xw) >= 2:
            d = Xw[-1] - Xw[-2]
            eh = float(np.arctan2(d[1], d[0]))
        else:
            eh = float(theta_path[0])
        ray = Xw[-1] + np.outer(np.arange(1, nlook + 1) * h, [np.cos(eh), np.sin(eh)])
        Q = np.vstack([Xw[::stride], ray])
        sq = np.concatenate([ss[::stride], ss[-1] + np.arange(1, nlook + 1) * h])
        idx = np.clip(np.round(sq / h).astype(int), 0, M)
        return float(np.mean(np.linalg.norm(Q - path[idx], axis=1)))

    for _ in range(ln.MAX_PULSES_LINE):
        if line.length() >= L - h:
            break
        u = min(line.length() / max(L, 1e-9), 1.0)
        best, best_sc = None, np.inf
        for _k in range(max(k, 1)):
            if not line.rows:
                row = hand.first(rng)
                newP = ln.first_pulse(row, R, float(theta_path[0]))
            else:
                row = hand.draw(np.asarray(line.rows[-1]), np.asarray(line.rows[-2]) if len(line.rows) >= 2 else None,
                                u, rng)
                newP = ln.next_pulse(line.P[-1], row, R)
            t_a, tg, Xw = line.propose(newP)
            if len(Xw) < 2 or not np.all(np.isfinite(Xw)):
                continue
            sc = score(t_a, tg, Xw)
            if sc < best_sc:
                best, best_sc = (newP, row, t_a, tg, Xw), sc
        if best is None:
            break
        newP, row, t_a, tg, Xw = best
        line.commit(newP, [row], t_a, tg, Xw)
    pts = line.X
    s = ln.arclength(pts)
    if len(pts) < 3 or s[-1] <= 0:
        return theta_path.copy()
    if s[-1] > L:                                   # cut at the structure's length
        j = int(np.searchsorted(s, L)) + 1
        pts = pts[:max(j, 3)]
    th = _headings(_resample_n(pts, M, False), False)
    return th + 2 * np.pi * np.round((theta_path[0] - th[0]) / (2 * np.pi))


# ---------------------------------------------------------------------------
# decompositions
# ---------------------------------------------------------------------------

@dataclass
class _Structure:
    theta: np.ndarray        # base θ (M,)
    pins: np.ndarray         # indices into positions 0..M (closed: M ≡ 0)
    heads: np.ndarray        # indices with a heading constraint
    head_tgt: np.ndarray
    sd_res: float            # residual band (samples)
    kind: str


def _uniform_pins(M: int, spacing: float, closed: bool) -> np.ndarray:
    n = max(int(np.ceil(M / max(spacing, 1.0))), 1 if closed else 1)
    return np.unique(np.round(np.linspace(0, M, n + 1)).astype(int))


def decompose(src: _Src, sd: float, method: str) -> _Structure:
    M = len(src.theta)
    if method == "gauss":
        th = _lowpass(src.theta, sd, src.closed, src.turn)
        return _Structure(th, _uniform_pins(M, SPACING * sd, src.closed), np.zeros(0, int),
                          np.zeros(0), sd, "gauss")
    if method == "clothoid":
        return _clothoid_structure(src, sd)
    if method == "anchors":
        return _anchor_structure(src, sd)
    raise ValueError(f"unknown method {method!r}")


def _clothoid_structure(src: _Src, sd: float) -> _Structure:
    from .clothoid import fit_stroke, reconstruct
    M = len(src.theta)
    sig = sd * src.h
    pts = src.p
    try:
        fit = fit_stroke(pts, sigma=sig, closed=src.closed)
        ok = (np.isfinite(fit.rms_position_error) and fit.rms_position_error <= 2 * sig
              and all(abs(a) <= np.pi for a in fit.corner_angles))
    except Exception:  # noqa: BLE001 — a failed fit falls back to gauss
        ok = False
    if not ok:
        st = decompose(src, sd, "gauss")
        st.kind = "clothoid->gauss"
        return st
    rec = reconstruct(fit, step=max(src.h / 2, 1e-6))
    if src.closed:
        rec = rec[:-1] if np.linalg.norm(rec[-1] - rec[0]) < 2 * src.h else rec
    q = _resample_n(rec, M, src.closed)
    th = _headings(q, src.closed)
    Lf = max(fit.length, 1e-9)
    cidx = [int(round((c % Lf if src.closed else c) / Lf * M)) for c in fit.corners]
    if src.closed:
        shift = int(round((fit.segments[0].s0 % Lf) / Lf * M)) if fit.segments else 0
        th = np.roll(th, shift)
        # roll moves the unwrap seam: re-unwrap, then match the source's branch
        th = np.unwrap(th)
        th = th + 2 * np.pi * np.round(np.mean(src.theta - th) / (2 * np.pi))
        off = np.angle(np.mean(np.exp(1j * (src.theta - th))))
        th = th + off
    else:
        th = th + np.angle(np.mean(np.exp(1j * (src.theta - th))))
    pins = np.unique(np.concatenate([_uniform_pins(M, SPACING * sd, src.closed),
                                     np.clip(cidx, 0, M)]).astype(int))
    return _Structure(th, pins, np.zeros(0, int), np.zeros(0), sd, "clothoid")


def _anchor_structure(src: _Src, sd: float) -> _Structure:
    M = len(src.theta)
    thc = _lowpass(src.theta, sd, src.closed, src.turn)
    R = src.h / STEP
    if src.closed:
        kc = np.diff(np.append(thc, thc[0] + src.turn)) / src.h * R
        ak = np.abs(np.concatenate([kc, kc, kc]))
        pk, _ = find_peaks(ak, prominence=ANCHOR_PROM, distance=max(int(sd), 1))
        pk = np.unique(pk[(pk >= M) & (pk < 2 * M)] - M)
    else:
        kc = np.diff(np.append(thc, thc[-1])) / src.h * R
        pk, _ = find_peaks(np.abs(kc), prominence=ANCHOR_PROM, distance=max(int(sd), 1))
        pk = np.concatenate([[0], pk, [M]])
    gap = GAP_MAX * sd
    if src.closed and len(pk) == 0:
        pk = np.array([0])
    anchors: list[int] = []
    seq = list(pk) + ([pk[0] + M] if src.closed else [])
    for a, b in zip(seq[:-1], seq[1:]):
        n = int(np.ceil((b - a) / gap)) if b > a else 1
        anchors += [int(round(a + (b - a) * i / n)) for i in range(n)]
    if not src.closed:
        anchors.append(M)
    anchors = np.unique(np.array(anchors) % (M if src.closed else M + 1))
    # base: θ linear between anchors (headings taken from the σ_s view)
    hidx = np.minimum(anchors, M - 1)
    hv = thc[hidx]
    if src.closed:
        xs = np.concatenate([anchors - M, anchors, anchors + M])
        ys = np.concatenate([hv - src.turn, hv, hv + src.turn])
        th = np.interp(np.arange(M), xs, ys)
    else:
        th = np.interp(np.arange(M), hidx, hv)
    return _Structure(th, anchors.astype(int), hidx.astype(int), hv, ANCHOR_HAND * sd, "anchors")


# ---------------------------------------------------------------------------
# the fidelity constraint
# ---------------------------------------------------------------------------

def _basis(M: int, sd_b: float, closed: bool) -> np.ndarray:
    sp = max(sd_b, M / MAX_BASIS, 1.0)
    c = np.arange(0.0, M + (0 if closed else sp * 0.5), sp)
    i = np.arange(M)
    d = i[None, :] - c[:, None]
    if closed:
        d = (d + M / 2) % M - M / 2
    return np.exp(-0.5 * (d / sp) ** 2)


def fit_pins(p0, theta, h, pin_idx, pin_tgt, head_idx, head_tgt, sd_b, closed,
             tol, tol_head=TOL_HEAD, iters=N_ITER):
    """Damped Gauss–Newton: the smallest low-band δθ (Gaussian bumps of
    width ≈ sd_b samples) that brings positions at pin_idx to pin_tgt
    (within tol px) and headings at head_idx to head_tgt. Returns θ."""
    th = np.array(theta, dtype=np.float64, copy=True)
    M = len(th)
    hv = np.broadcast_to(np.asarray(h, dtype=np.float64), (M,)).copy()
    if len(pin_idx) == 0 and len(head_idx) == 0:
        return th, hv
    th, hv = _align_intervals(p0, th, hv, pin_idx, pin_tgt, closed)
    h = hv
    B = _basis(M, sd_b, closed)
    K = len(B)
    wp, wh = 1.0 / max(tol, 1e-9), 1.0 / tol_head

    def err(t):
        P = _integrate(p0, t, h)
        ep = (pin_tgt - P[pin_idx]).ravel() * wp
        eh = (head_tgt - t[head_idx]) * wh if len(head_idx) else np.zeros(0)
        return np.concatenate([ep, eh])

    e = err(th)
    mu = 1e-3
    for _ in range(iters):
        if np.max(np.abs(e[:2 * len(pin_idx)]), initial=0.0) < 0.5 and \
                np.max(np.abs(e[2 * len(pin_idx):]), initial=0.0) < 0.5:
            break
        sn, cs = np.sin(th) * hv, np.cos(th) * hv
        Jx = np.concatenate([np.zeros((K, 1)), np.cumsum(-sn[None, :] * B, axis=1)], axis=1)
        Jy = np.concatenate([np.zeros((K, 1)), np.cumsum(cs[None, :] * B, axis=1)], axis=1)
        Jp = np.empty((2 * len(pin_idx), K))
        Jp[0::2] = Jx[:, pin_idx].T
        Jp[1::2] = Jy[:, pin_idx].T
        J = np.vstack([Jp * wp, (B[:, head_idx].T * wh) if len(head_idx) else np.zeros((0, K))])
        A = J.T @ J
        g = J.T @ e
        lam = mu * (np.trace(A) / K + 1e-12)
        improved = False
        for _ls in range(6):
            c = np.linalg.solve(A + lam * np.eye(K), g)
            cand = th + B.T @ c
            e2 = err(cand)
            if e2 @ e2 < e @ e:
                th, e, improved = cand, e2, True
                mu = max(mu / 3, 1e-6)
                break
            lam *= 10
            mu *= 10
        if not improved:
            break
    return th, hv


def _align_intervals(p0, th, hv, pin_idx, pin_tgt, closed, passes: int = 4):
    """Robust start for `fit_pins`: per pin interval, the rotation that turns
    the drawn chord onto the target chord and the step stretch that matches
    its length (clipped to [1/STRETCH_MAX, STRETCH_MAX]); both are spread as
    piecewise-linear functions of s (knots at interval midpoints), so the
    hand's shape inside an interval is kept up to a gentle similarity."""
    M = len(th)
    pins = np.asarray(pin_idx)
    if len(pins) < 2:
        return th, hv
    th, hv = th.copy(), hv.copy()
    for _ in range(passes):
        P = _integrate(p0, th, hv)
        a, b = pins[:-1], pins[1:]
        dd = P[b] - P[a]
        dt = pin_tgt[1:] - pin_tgt[:-1]
        nd, nt = np.linalg.norm(dd, axis=1), np.linalg.norm(dt, axis=1)
        ok = (nd > 1e-9) & (nt > 1e-9) & (b > a)
        if not np.any(ok):
            break
        rot = np.where(ok, _wrap(np.arctan2(dt[:, 1], dt[:, 0]) - np.arctan2(dd[:, 1], dd[:, 0])), 0.0)
        sc = np.where(ok, np.clip(nt / np.maximum(nd, 1e-9), 1 / STRETCH_MAX, STRETCH_MAX), 1.0)
        mid = 0.5 * (a + b)
        if closed:
            xs = np.concatenate([mid - M, mid, mid + M])
            rr, ss = np.tile(rot, 3), np.tile(np.log(sc), 3)
        else:
            xs, rr, ss = mid, rot, np.log(sc)
        i = np.arange(M) + 0.5
        th = th + np.interp(i, xs, rr)
        hv = hv * np.exp(np.interp(i, xs, ss))
        if np.max(np.abs(rot)) < 1e-3 and np.max(np.abs(np.log(sc))) < 1e-3:
            break
    return th, hv


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def feature_length(src: _Src, R: float) -> float:
    """ℓ = the stroke's length per quarter-turn of its θ smoothed at 0.01 R
    (px): a circle of radius r → 1.57 r, a spiral turn → a quarter of its
    circumference, a near-straight limb → its length."""
    L = src.h * len(src.theta)
    th = _lowpass(src.theta, 0.01 * R / src.h, src.closed, src.turn)
    tv = float(np.sum(np.abs(np.diff(th))))
    return L / max(1.0, tv / (np.pi / 2))


def restyle_points(points, g, rng, *, amount: float, ref_length: float, closed: bool = False,
                   method: str = "gauss", source: str = "chain", hand_gain: float = 1.0,
                   tol: float = TOL, scale: str = "drawing",
                   max_sigma: float | None = None) -> tuple[np.ndarray, dict]:
    """One polyline (px) → (new polyline, info). amount = 0 returns a copy.
    info["n_out"]/["M"] let a caller map output samples back to the source
    (sample i of the output ↔ arc fraction i/M of the source).
    max_sigma (px): cap on σ_s. A line shorter than ~2 σ_s gets only its two
    end pins; the hand then wanders and the pin fit stretches its steps
    (up to STRETCH_MAX^passes) into a long needle or loop — the chain fix
    caps σ_s at a fraction of each run's length (composite.restyle_chain)."""
    pts = np.array(points, dtype=np.float64, copy=True)
    R = float(ref_length)
    info = {"amount": float(amount), "method": method, "source": source}
    if amount <= 0 or len(pts) < 3:
        return pts, {**info, "kind": "identity"}
    src = _source(pts, closed, R)
    if src is None:
        return pts, {**info, "kind": "too_short"}
    if scale == "stroke":
        sig = sigma_of(amount) * min(R, STROKE_K * feature_length(src, R))
    elif scale == "drawing":
        sig = sigma_of(amount) * R
    else:
        raise ValueError(f"unknown scale {scale!r}")
    if max_sigma is not None:
        sig = min(sig, float(max_sigma))
    sd = max(sig / src.h, 1.0)
    st = decompose(src, sd, method)
    M = len(src.theta)
    pin_idx = st.pins[st.pins <= M] if not closed else np.unique(np.append(st.pins % M, M))
    tgt_pts = np.vstack([src.p, src.p[:1]]) if closed else src.p
    pin_tgt = tgt_pts[pin_idx]
    if source in ("trace", "trace_ln"):
        base, hb = fit_pins(src.p[0], st.theta, src.h, pin_idx, pin_tgt, st.heads, st.head_tgt,
                            BASIS * sd, closed, tol * sig)
        path = _integrate(src.p[0], base, hb)
        k = int(round(TRACE_KMIN + (TRACE_KMAX - TRACE_KMIN) * (1 - float(np.clip(amount, 0, 1)))))
        th_t = (trace_theta if source == "trace" else trace_theta_ln)(g, rng, path, base, src.h, R, k)
        r = hand_gain * (th_t - base)
        h_out = src.h
    else:
        if source == "chain":
            r = residual_chain(g, rng, M, st.sd_res, R, src.h, closed)
        elif source == "transplant":
            r = residual_transplant(g, rng, st.theta, st.sd_res, src.h, R, closed)
        else:
            raise ValueError(f"unknown source {source!r}")
        r = hand_gain * r
        h_out = src.h / max(float(np.mean(np.cos(r))), 0.5)
    traced = source in ("trace", "trace_ln")
    th0 = st.theta + r if not traced else base + r
    # the trace already followed the structure's tangents; pinning them again
    # fights the hand's own tangent at the anchors, so trace pins positions only
    heads, head_tgt = (st.heads, st.head_tgt) if not traced else (np.zeros(0, int), np.zeros(0))
    th, h_out = fit_pins(src.p[0], th0, h_out, pin_idx, pin_tgt, heads, head_tgt,
                         BASIS * sd, closed, tol * sig)
    out = _integrate(src.p[0], th, h_out)
    pin_err = float(np.max(np.linalg.norm(out[pin_idx] - pin_tgt, axis=1))) if len(pin_idx) else 0.0
    if closed:
        out = out[:-1]
    info.update(kind=st.kind, sigma_s=sig, M=int(M), n_pins=int(len(pin_idx)), pin_err=pin_err,
                stretch=float(np.mean(h_out) / src.h), r_rms=float(np.sqrt(np.mean(r ** 2))))
    return out, info


def restyle_stroke(stroke: Stroke, g, rng, *, amount: float, ref_length: float | None = None,
                   **kw) -> Stroke:
    """A Stroke redrawn in hand g. ref_length defaults to the stroke's own
    bbox diagonal (treat it as a whole drawing)."""
    R = ref_length if ref_length is not None else float(max(np.hypot(*np.ptp(stroke.points, axis=0)), 1e-9))
    pts, info = restyle_points(stroke.points, g, rng, amount=amount, ref_length=R,
                               closed=stroke.closed, **kw)
    if info["kind"] == "identity":
        return Stroke(pts, width=None if stroke.width is None else stroke.width.copy(),
                      closed=stroke.closed, meta={**stroke.meta, "restyle": info})
    return Stroke(pts, closed=stroke.closed,
                  meta={**{k: v for k, v in stroke.meta.items() if k not in ("tokens", "segments")},
                        "restyle": {**info, "hand": getattr(g, "name", "")}})


def restyle_drawing(drawing: Drawing, g, *, amount: float, seed: int = 0, method: str = "gauss",
                    source: str = "chain", ref_length: float | None = None, weld: bool = True,
                    **kw) -> Drawing:
    """Every stroke of a drawing restyled into hand g at one shared R (the
    drawing's ref_length), so the hand's scale is coherent across strokes.
    Stroke i draws from its own stream default_rng([seed, i]): the hand
    detail of a stroke does not depend on `amount` (chain source).
    weld: re-attach junction ends to their restyled hosts (`weld_junctions`)."""
    R = float(ref_length) if ref_length is not None else drawing.ref_length()
    out = [restyle_stroke(st, g, np.random.default_rng([int(seed), i]), amount=amount,
                          ref_length=R, method=method, source=source, **kw)
           for i, st in enumerate(drawing.strokes)]
    wmeta = {}
    if weld and amount > 0:
        out, wmeta = weld_junctions(drawing, out, R)
    return Drawing(out, source=f"{drawing.source}|restyle:{getattr(g, 'name', '')}:{method}:{source}:{amount:g}",
                   size=drawing.size, meta={**drawing.meta, "restyle": {
                       "hand": getattr(g, "name", ""), "amount": float(amount), "method": method,
                       "source": source, "seed": int(seed), "ref_length": R, **wmeta}})


# ---------------------------------------------------------------------------
# junction welding
# ---------------------------------------------------------------------------

def _arcfrac(p: np.ndarray, closed: bool) -> np.ndarray:
    q = np.vstack([p, p[:1]]) if closed else p
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
    return (s / max(s[-1], 1e-12))[:len(p)]


def find_junctions(drawing: Drawing, R: float, tol_r: float = WELD_R) -> list[tuple[int, int, int, float]]:
    """Open ends that touch another stroke in the source: (stroke, end 0|-1,
    host, u = arc fraction of the touching point along the host)."""
    from scipy.spatial import cKDTree
    S = drawing.strokes
    if len(S) < 2:
        return []
    P = np.vstack([s.points for s in S])
    own = np.concatenate([np.full(len(s.points), i) for i, s in enumerate(S)])
    loc = np.concatenate([np.arange(len(s.points)) for s in S])
    tree = cKDTree(P)
    fr = [_arcfrac(s.points, s.closed) for s in S]
    out = []
    for i, st in enumerate(S):
        if st.closed or len(st.points) < 2:
            continue
        for e in (0, -1):
            cand = [j for j in tree.query_ball_point(st.points[e], tol_r * R) if own[j] != i]
            if not cand:
                continue
            j = min(cand, key=lambda c: float(np.sum((P[c] - st.points[e]) ** 2)))
            out.append((i, e, int(own[j]), float(fr[own[j]][loc[j]])))
    return out


def _point_at(st: Stroke, u: float, near: np.ndarray | None = None) -> np.ndarray:
    """The point of a (restyled) stroke at structural position u: by sample
    index when restyled (sample i ↔ source arc fraction i/M), else by arc.
    With `near`, the point of the host closest to `near` within ±σ_s of that
    position (the restyled host may slip along itself; the weld should not
    drag the branch along with it)."""
    p = st.points
    info = st.meta.get("restyle", {})
    if info.get("kind") not in (None, "identity", "too_short") and "M" in info:
        M = info["M"]
        x = u * M
        if near is not None:
            Lh = float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)))
            w = max(int(np.ceil(info.get("sigma_s", 0.0) / max(Lh / max(M, 1), 1e-9))), 2)
            idx = np.arange(int(np.floor(x)) - w, int(np.ceil(x)) + w + 1)
            idx = idx % len(p) if st.closed else np.clip(idx, 0, len(p) - 1)
            return _nearest_on_polyline(p[np.unique(idx)] if not st.closed else p[idx], near)
        if st.closed:
            i0 = int(np.floor(x)) % len(p)
            i1, f = (i0 + 1) % len(p), x - np.floor(x)
        else:
            x = float(np.clip(x, 0, len(p) - 1))
            i0 = int(np.floor(x))
            i1, f = min(i0 + 1, len(p) - 1), x - i0
        return (1 - f) * p[i0] + f * p[i1]
    fr = _arcfrac(p, st.closed)
    if near is not None:                 # an unrestyled host: the junction already touches it
        return _nearest_on_polyline(np.vstack([p, p[:1]]) if st.closed else p, near)
    return np.array([np.interp(u, fr, p[:, 0]), np.interp(u, fr, p[:, 1])])


def _nearest_on_polyline(p: np.ndarray, x: np.ndarray) -> np.ndarray:
    if len(p) == 1:
        return p[0].copy()
    a, b = p[:-1], p[1:]
    ab = b - a
    t = np.clip(np.sum((x - a) * ab, axis=1) / np.maximum(np.sum(ab * ab, axis=1), 1e-12), 0, 1)
    q = a + t[:, None] * ab
    return q[int(np.argmin(np.sum((q - x) ** 2, axis=1)))]


def weld_junctions(src: Drawing, out: list[Stroke], R: float,
                   tol_r: float = WELD_R) -> tuple[list[Stroke], dict]:
    """Move every junction end of the restyled strokes onto its restyled host
    (cosine fade over WELD_FADE·σ_s, at most half the stroke). Hosts are
    welded before their dependents; the closing weld of a cycle (two ends
    joined to each other) is applied last. Returns (new strokes, {"welds", "weld_max_R"})."""
    J = find_junctions(src, R, tol_r)
    if not J:
        return out, {"welds": 0, "weld_max_R": 0.0}
    deps: dict[int, list] = {}
    for i, e, j, u in J:
        deps.setdefault(i, []).append((e, j, u))
    pts = [s.points.copy() for s in out]
    state: dict[int, int] = {}          # 1 = in progress, 2 = done
    moved, late = [], []

    def apply(i, e, j, u):
        host = Stroke(pts[j], closed=out[j].closed, meta=out[j].meta)
        tgt = _point_at(host, u, near=pts[i][e])
        p = pts[i]
        d = tgt - p[e]
        nd = float(np.linalg.norm(d))
        if nd < 1e-9:
            return
        seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
        s = np.concatenate([[0.0], np.cumsum(seg)])
        if e == -1:
            s = s[-1] - s
        sig = float(out[i].meta.get("restyle", {}).get("sigma_s", 0.0))
        Lf = min(max(WELD_FADE * sig, 3 * nd), 0.5 * float(s.max()))
        w = np.where(s < Lf, 0.5 * (1 + np.cos(np.pi * np.clip(s / max(Lf, 1e-9), 0, 1))), 0.0)
        pts[i] = p + w[:, None] * d[None, :]
        moved.append(nd)

    def visit(i):
        if state.get(i) == 2:
            return
        state[i] = 1
        for e, j, u in deps.get(i, []):
            if state.get(j) == 1:          # cycle: weld after everything else
                late.append((i, e, j, u))
                continue
            visit(j)
            apply(i, e, j, u)
        state[i] = 2

    for i in range(len(out)):
        visit(i)
    for jn in late:
        apply(*jn)
    new = [Stroke(p, width=None if s.width is None else s.width.copy(), closed=s.closed,
                  meta={**s.meta, "welded": True} if i in deps else s.meta)
           for i, (p, s) in enumerate(zip(pts, out))]
    return new, {"welds": len(moved), "weld_max_R": float(max(moved) / R) if moved else 0.0}


# ---------------------------------------------------------------------------
# structure fidelity
# ---------------------------------------------------------------------------

def _dense(points: np.ndarray, closed: bool, R: float, sigma_e: float) -> np.ndarray:
    h = STEP * R * 2
    r = resample(points, h, closed=closed)
    if len(r) >= 4 and sigma_e > 0:
        r = smooth(r, sigma_e * R, h, closed=closed)
    return r


def _frechet(a: np.ndarray, b: np.ndarray) -> float:
    D = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    n, m = D.shape
    F = np.empty_like(D)
    F[0] = np.maximum.accumulate(D[0])
    for i in range(1, n):
        F[i, 0] = max(F[i - 1, 0], D[i, 0])
        prev = F[i - 1]
        row = F[i]
        Di = D[i]
        for j in range(1, m):
            row[j] = max(Di[j], min(prev[j], prev[j - 1], row[j - 1]))
    return float(F[-1, -1])


def structure_distance(src: Drawing, out: Drawing, *, ref_length: float | None = None,
                       sigma_e: float = 0.01, n_frechet: int = 48) -> dict:
    """Stroke-by-stroke distance between a source and its restyle, both
    smoothed at sigma_e·R (removes pixel noise, keeps the hand's wiggle):
    {"mean": length-weighted symmetric mean closest-point distance / R,
     "frechet": length-weighted discrete Fréchet (n_frechet points) / R}."""
    R = float(ref_length) if ref_length is not None else src.ref_length()
    tot, dm, df = 0.0, 0.0, 0.0
    for a, b in zip(src.strokes, out.strokes):
        if len(a) < 2 or len(b) < 2:
            continue
        L = a.length()
        pa, pb = _dense(a.points, a.closed, R, sigma_e), _dense(b.points, b.closed, R, sigma_e)
        d1, _ = cKDTree(pb).query(pa)
        d2, _ = cKDTree(pa).query(pb)
        dm += L * 0.5 * (d1.mean() + d2.mean())
        if a.closed:
            fa = _resample_n(pa, n_frechet, True)
            fb = _resample_n(pb, n_frechet, True)
            fa, fb = np.vstack([fa, fa[:1]]), np.vstack([fb, fb[:1]])
        else:
            fa, fb = _resample_n(pa, n_frechet, False), _resample_n(pb, n_frechet, False)
        df += L * _frechet(fa, fb)
        tot += L
    if tot <= 0:
        return {"mean": 0.0, "frechet": 0.0}
    return {"mean": dm / tot / R, "frechet": df / tot / R}
