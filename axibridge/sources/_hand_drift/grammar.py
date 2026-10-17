"""Frozen: the clothoid-alphabet grammar's chain (research `gesture/grammar.py`
and `gesture/curvature.py` at c897f28), trimmed to what `drift_line` uses.

A hand is a non-parametric order-2 chain over tokens — segments
``[kind, l, k0, k1]`` (l = length / R, k = κ·R; kind line / arc / clothoid)
and corners ``["corner", angle]``. The next token is drawn from the k
nearest training transitions whose previous token has the same kind, in a
context of (previous token, the one before it, log remaining length,
position along the stroke); with probability `P_FOLLOW` the actual next
token of the source stroke is taken instead (runs of at most `MAX_RUN`
follows). κ continuity is enforced at segment joints; corners stay tokens.

Dropped from the research module: learning, sheet generation (relations,
growers), plans / budgets / segment-scale contexts (the drift runs with
none of them), translation and restyling.

Pure and deterministic: inputs never mutated; randomness via np.random.Generator.
"""
from __future__ import annotations

import numpy as np

SEG_KINDS = ("line", "arc", "clothoid")

KAPPA_SCALE = 5.0        # κ·R features go through asinh(κR / this)
KNN = 12                 # neighbours considered per draw
W_PREV2 = 0.5            # context weights (squared-distance multipliers)
W_REM = 0.5
W_U = 0.5
U_SCALE = 0.25
PEN_PREV2 = 2.0          # added squared distance when the token-before-previous kind differs
JITTER_LEN = 0.08        # log-normal sd of the length jitter
JITTER_K = 0.05          # κ jitter, fraction of the kind's κ·R spread
JITTER_ANGLE = 0.05      # corner angle jitter (rad)
MAX_TOKENS = 200
P_FOLLOW = 0.9           # chance to continue the source stroke of the last token ...
MAX_RUN = 1              # ... at most this many follows in a row
END_FIT = 0.5            # a last token cut to < this fraction is dropped, the previous stretched


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------

def _tok_seg(kind, l, k0, k1):
    return [kind, float(l), float(k0), float(k1)]


def _tok_corner(a):
    return ["corner", float(a)]


def stroke_length(toks) -> float:
    return float(sum(t[1] for t in toks if t[0] != "corner"))


def end_heading(toks: list[list], heading: float = 0.0) -> float:
    """Tangent angle at the end of a token stroke started at `heading`."""
    h = float(heading)
    for t in toks:
        h += t[1] if t[0] == "corner" else 0.5 * (t[2] + t[3]) * t[1]
    return h


def _feat(tok, scale) -> np.ndarray:
    """Context feature of a token (3 dims; START = zeros; corner = angle, 0, 0)."""
    if tok[0] == "START":
        return np.zeros(3)
    if tok[0] == "corner":
        return np.array([tok[1] / scale["angle"], 0.0, 0.0])
    l, k0, k1 = tok[1], tok[2], tok[3]
    return np.array([np.log(max(l, 1e-9)) / scale["logl"],
                     np.arcsinh(k0 / KAPPA_SCALE) / scale["ak"],
                     np.arcsinh(k1 / KAPPA_SCALE) / scale["ak"]])


def _ctx(p2, p1, rem, u, scale) -> np.ndarray:
    return np.concatenate([_feat(p1, scale), np.sqrt(W_PREV2) * _feat(p2, scale),
                           [np.sqrt(W_REM) * np.log(max(rem, 1e-6)) / scale["logl"],
                            np.sqrt(W_U) * u / U_SCALE]])


# ---------------------------------------------------------------------------
# the grammar
# ---------------------------------------------------------------------------

class Grammar:
    """A learned hand: the transition table (reversal-augmented column lists
    p2 / p1 / nx kinds, f2 / f1 context params, rem, u, par, sid), training
    stroke lengths, and the κ / length scales of its context space."""

    def __init__(self, name: str, trans: dict, stroke_lengths: list, scale: dict, spread: dict,
                 kind_params: dict[str, list] | None = None):
        self.name = name
        self.trans = trans
        self.stroke_lengths = stroke_lengths
        self.scale = scale
        self.spread = spread
        self._kp_src = kind_params or {}
        self._cache: dict = {}

    def _kind_params(self, kind: str) -> list:
        """The training strokes' token params of one kind, in stroke order
        (what the research `_kind_pool` reads from `Grammar.strokes`)."""
        return self._kp_src.get(kind, [])

    def _pool(self, p1kind: str):
        """(X context matrix, p2 kinds, next kinds, next params, record ids) for one previous kind."""
        key = ("pool", p1kind)
        if key not in self._cache:
            T = self.trans
            idx = [i for i, k in enumerate(T.get("p1", [])) if k == p1kind]
            if not idx:
                self._cache[key] = None
            else:
                X = np.array([_ctx([T["p2"][i]] + list(T["f2"][i]), [p1kind] + list(T["f1"][i]),
                                   T["rem"][i], T["u"][i], self.scale) for i in idx])
                self._cache[key] = (X, np.array([T["p2"][i] for i in idx]),
                                    [T["nx"][i] for i in idx], [T["par"][i] for i in idx],
                                    np.array(idx))
        return self._cache[key]

    def _kind_pool(self, kind):
        key = ("kind", kind)
        if key not in self._cache:
            P = [list(p) for p in self._kind_params(kind)]
            self._cache[key] = None if not P else (
                np.array([_feat([kind] + p, self.scale) for p in P]), P)
        return self._cache[key]

    def warm(self) -> "Grammar":
        """Build every derived pool now (load time), so concurrent previews
        only ever read the cache."""
        for k in ("START",) + SEG_KINDS + ("corner",):
            self._pool(k)
            if k != "START":
                self._kind_pool(k)
        return self

    def draw(self, p2, p1, s: float, length: float, rng, prev_rec: int | None = None,
             p_follow: float = 0.0, kmatch: float = 0.0, knn: int = KNN,
             weights=None, dscale=None, w_ds: float = 0.0) -> tuple[str, list[float], int]:
        """Next token (kind, params, record index) given the previous two
        tokens, arc length so far s and the stroke's target length (both R
        units). p_follow: with this probability, if the previous token came
        from training record prev_rec and its source stroke goes on, take
        that stroke's actual next token. (kmatch / weights / dscale are the
        research's ablations; the drift passes none of them.)"""
        T = self.trans
        if prev_rec is not None and p_follow > 0 and rng.random() < p_follow:
            sids = T.get("sid")
            j = prev_rec + 1
            if sids and j < len(sids) and sids[j] == sids[prev_rec] and T["p1"][j] == p1[0]:
                if weights is None or rng.random() < float(weights([T["nx"][j]], [T["par"][j]])[0]):
                    return T["nx"][j], _jitter(self, T["nx"][j], list(T["par"][j]), rng), j
        pool = self._pool(p1[0])
        if pool is None:
            pool = self._pool("START")
            p1, p2 = ["START"], ["START"]
        X, P2, NX, PAR, IDX = pool
        q = _ctx(p2, p1, max(length - s, 1e-6), min(s / max(length, 1e-9), 1.0), self.scale)
        d = np.sum((X - q) ** 2, axis=1) + PEN_PREV2 * (P2 != p2[0])
        k = min(knn, len(d))
        near = np.argpartition(d, k - 1)[:k]
        j = int(near[int(rng.integers(k))])
        return NX[j], _jitter(self, NX[j], list(PAR[j]), rng), int(IDX[j])


def _jitter(g: Grammar, kind: str, p: list, rng) -> list[float]:
    if kind == "corner":
        return [p[0] + rng.normal(0, JITTER_ANGLE)]
    l = p[0] * float(np.exp(rng.normal(0, JITTER_LEN)))
    sk = JITTER_K * g.spread.get(kind, 0.0)
    k0, k1 = p[1], p[2]
    if kind == "arc":
        k0 = k1 = k0 + rng.normal(0, sk)
    elif kind == "clothoid":
        k0, k1 = k0 + rng.normal(0, sk), k1 + rng.normal(0, sk)
    else:
        k0 = k1 = 0.0
    return [l, k0, k1]


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------

def _continuity(prev: list | None, tok: list, lock_prev: bool = False) -> tuple[list | None, list]:
    """Enforce κ continuity at a non-corner joint. Returns (prev, tok), both
    possibly modified copies. lock_prev: prev may not change (it belongs to
    an earlier chunk), so the new token absorbs the whole adjustment."""
    if prev is None or prev[0] in ("corner", "START") or tok[0] == "corner":
        return prev, tok
    kj = prev[3]
    kind, l, k0, k1 = tok
    if kind == "arc":
        if abs(kj) < 1e-9:
            return prev, _tok_seg("clothoid", l, 0.0, k1)
        r = float(np.clip(abs(k0) / abs(kj), 0.25, 4.0)) if abs(k0) > 1e-12 else 1.0
        return prev, _tok_seg("arc", l * r, kj, kj)
    if kind == "line":
        if abs(kj) < 1e-9:
            return prev, tok
        if prev[0] == "clothoid" and not lock_prev:
            pk = "line" if abs(prev[2]) < 1e-9 else "clothoid"
            return _tok_seg(pk, prev[1], prev[2], 0.0), tok
        return prev, _tok_seg("clothoid", l, kj, 0.0)
    return prev, _tok_seg("clothoid", l, kj, k1)


def generate_tokens(gA, rng, *, length: float, context: tuple | None = None,
                    max_tokens: int = MAX_TOKENS, p_follow: float = 0.0,
                    max_run: int = MAX_RUN, end_fit: float = 0.0) -> tuple[list, int]:
    """Run the order-2 chain to a target length (dimensionless). context =
    (token before last, last token) of a preceding chunk: conditions the
    first draws and makes the joint κ-continuous. end_fit > 0: a last token
    that would be cut to < end_fit of its length is dropped and the previous
    segment stretched by the remainder. Returns (tokens, len(tokens))."""
    p2, p1 = (list(context[0]), list(context[1])) if context else (["START"], ["START"])
    toks: list[list] = []
    s, g, draws, rec, run = 0.0, gA, 0, None, 0
    while len(toks) < max_tokens and draws < 4 * max_tokens:
        draws += 1
        kind, p, rec_ = g.draw(p2, p1, s, length, rng, prev_rec=rec,
                               p_follow=p_follow if run < max_run else 0.0, kmatch=0.0, knn=KNN,
                               weights=None, dscale=None, w_ds=0.0)
        run = run + 1 if (rec is not None and rec_ == rec + 1) else 0
        rec = rec_
        tok = _tok_corner(p[0]) if kind == "corner" else _tok_seg(kind, *p)
        if kind == "corner" and (not toks and p1[0] in ("START",)):
            continue
        if kind == "corner" and toks and toks[-1][0] == "corner":
            continue
        newprev, tok = _continuity(p1, tok, lock_prev=not toks)
        if toks and newprev is not p1:
            toks[-1] = newprev
        if tok[0] != "corner" and s + tok[1] >= length:
            frac = max(length - s, 1e-9) / tok[1]
            if end_fit > 0 and frac < end_fit and toks and toks[-1][0] in SEG_KINDS:
                pv = toks[-1]
                toks[-1] = _tok_seg(pv[0], pv[1] + max(length - s, 0.0), pv[2], pv[3])
                break
            if frac >= 0.3 or not toks:
                toks.append(_tok_seg(tok[0], tok[1] * frac, tok[2], tok[2] + (tok[3] - tok[2]) * frac))
            break
        toks.append(tok)
        if tok[0] != "corner":
            s += tok[1]
        p2, p1 = (toks[-2] if len(toks) >= 2 else p1), toks[-1]
    while toks and toks[-1][0] == "corner":
        toks.pop()
    return toks, len(toks)


def integrate_kappa(breaks: np.ndarray, kappas: np.ndarray, step: float,
                    start=(0.0, 0.0), heading: float = 0.0) -> np.ndarray:
    """Polyline from a piecewise-linear κ(s) (research `curvature.py`):
    points `step` apart along s; heading by trapezoid, position by midpoint."""
    breaks = np.asarray(breaks, dtype=np.float64)
    kappas = np.asarray(kappas, dtype=np.float64)
    total = breaks[-1]
    n = max(int(np.ceil(total / step)), 1)
    s = np.linspace(0.0, total, n + 1)
    k = np.interp(s, breaks, kappas)
    ds = np.diff(s)
    theta = heading + np.concatenate([[0.0], np.cumsum(0.5 * (k[1:] + k[:-1]) * ds)])
    mid = 0.5 * (theta[1:] + theta[:-1])
    steps = np.column_stack([np.cos(mid) * ds, np.sin(mid) * ds])
    return np.vstack([np.asarray(start, dtype=np.float64), np.asarray(start) + np.cumsum(steps, axis=0)])


def tokens_to_points(toks: list, R: float, *, start=(0.0, 0.0), heading: float = 0.0,
                     step: float = 0.5) -> np.ndarray:
    """Integrate a token list (dimensionless) at scale R. Corners turn
    instantaneously. (Research also returned segment / corner records.)"""
    pos = np.asarray(start, dtype=np.float64)
    h = float(heading)
    out = [pos[None, :]]
    run: list = []

    def flush():
        nonlocal pos, h
        if not run:
            return
        b = [0.0]
        k = [run[0][2] / R]
        for t in run:
            b.append(b[-1] + t[1] * R)
            k.append(t[3] / R)
        pts = integrate_kappa(np.array(b), np.array(k), step, start=pos, heading=h)
        out.append(pts[1:])
        pos = pts[-1]
        kk, bb = np.array(k), np.array(b)
        h += float(np.sum(0.5 * (kk[1:] + kk[:-1]) * np.diff(bb)))
        run.clear()

    for t in toks:
        if t[0] == "corner":
            flush()
            h += t[1]
            continue
        run.append(t)
    flush()
    return np.vstack(out)


def _nearest(g: Grammar, kind: str, tok: list, scale: dict):
    kp = g._kind_pool(kind)
    if kp is None:
        return None
    P = kp[1]
    F = np.array([_feat([kind] + p, scale) for p in P]) if scale is not g.scale else kp[0]
    d = np.sum((F - _feat(tok, scale)) ** 2, axis=1)
    return list(P[int(np.argmin(d))])
