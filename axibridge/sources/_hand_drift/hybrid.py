"""Frozen: the drift line (research `gesture/hybrid.py` at c897f28).

`drift_line` grows ONE line whose hand drifts along a route of hands: the
weights of the hands follow `route_weights` over the line's arc length (each
hand pure on a plateau, linear cross-fades between). The line is grown in
chunks — each chunk a training-length "virtual stroke" of the hand that
dominates there, the best of K proposals (score: leaving the box, crowding
the line already drawn, distance from the centre).

blend (research `mode`): `mixture` — each token is drawn from one hand with
probability = its weight, from that hand's own pool; `interp` — each token is
drawn from a hand and its params moved toward the nearest same-kind token of
the other hand by that hand's share.

joins (research `context`): `kappa` (the bench's "smooth") — every chunk
starts fresh and κ is made continuous at the joint; `chain` — each chunk's
k-NN is conditioned on the previous chunk's last two tokens. In short-stroke
hands that throws the chain into a corner / straight-run attractor: the
"failure" Ian kept (round-8 review), a machine voice entering the line.

Dropped from the research module: data merging (the drift's `mixture` and
`interp` never read the merged tables; only the rng draw that seeded it is
kept, so the random stream is unchanged), the crossover/pooled methods, panel
statistics and plotting helpers.
"""
from __future__ import annotations

from typing import Callable, Sequence

import numpy as np
from scipy.spatial import cKDTree

from . import grammar as gm

METHODS = ("mixture", "interp")


class HybridGrammar:
    """Lets the parent hands speak token by token by `method`, with weights
    from `weight_fn(global s)`; `s_offset` is added to the s that `draw`
    receives. Record indices returned by `draw` index the concatenation of
    the parents' tables, so follows stay inside one parent."""

    def __init__(self, hands: Sequence[gm.Grammar], weights, method: str = "mixture"):
        if method not in METHODS:
            raise ValueError(f"unknown method {method!r} ({METHODS})")
        self.hands = list(hands)
        self.method = method
        self.weights = np.asarray(weights, float) / np.sum(weights)
        self.offsets = np.cumsum([0] + [len(g.trans.get("p1", [])) for g in hands])
        self.weight_fn: Callable | None = None
        self.s_offset = 0.0
        self.log: list | None = None

    def _w(self, s: float) -> np.ndarray:
        if self.weight_fn is None:
            return self.weights
        w = np.clip(np.asarray(self.weight_fn(self.s_offset + s), float), 0, None)
        return w / w.sum() if w.sum() > 0 else self.weights

    def _decode(self, rec):
        if rec is None:
            return None, None
        h = int(np.searchsorted(self.offsets, rec, side="right") - 1)
        return h, int(rec - self.offsets[h])

    def draw(self, p2, p1, s, length, rng, prev_rec=None, p_follow=0.0, kmatch=0.0, knn=gm.KNN,
             weights=None, dscale=None, w_ds=0.0):
        w = self._w(s)
        h = int(rng.choice(len(w), p=w))
        ph, prec = self._decode(prev_rec)
        g = self.hands[h]
        kind, par, j = g.draw(p2, p1, s, length, rng, prev_rec=prec if ph == h else None,
                              p_follow=p_follow if ph == h else 0.0, kmatch=kmatch, knn=knn, weights=weights)
        if self.method == "interp" and len(self.hands) > 1:
            wo = w.copy()
            wo[h] = -1
            o = int(np.argmax(wo))
            a = float(w[o] / max(w[o] + w[h], 1e-12))
            par = interp_params(kind, par, g, self.hands[o], a)
        if self.log is not None:
            self.log.append((self.s_offset + s, h))
        return kind, par, int(self.offsets[h] + j)


def interp_params(kind: str, par: list, gA: gm.Grammar, gB: gm.Grammar, a: float) -> list:
    """Move a token of hand A toward its nearest same-kind token in hand B by
    a ∈ [0, 1]: log length, κ·R (k0, k1) and corner angle linearly."""
    if a <= 0:
        return list(par)
    nb = gm._nearest(gB, kind, [kind] + list(par), gB.scale)
    if nb is None:
        return list(par)
    if kind == "corner":
        return [(1 - a) * par[0] + a * nb[0]]
    l = float(np.exp((1 - a) * np.log(max(par[0], 1e-9)) + a * np.log(max(nb[0], 1e-9))))
    k0 = (1 - a) * par[1] + a * nb[1]
    k1 = (1 - a) * par[2] + a * nb[2]
    if kind == "arc":
        k1 = k0
    if kind == "line":
        k0 = k1 = 0.0
    return [l, k0, k1]


def route_weights(u: float, k: int, plateau: float = 0.12) -> np.ndarray:
    """Weights of k hands at position u ∈ [0, 1] of a route: hand i is pure
    around u = i/(k−1) (± plateau/2), linear cross-fades in between."""
    if k == 1:
        return np.ones(1)
    x = np.clip(u, 0, 1) * (k - 1)
    i = int(min(np.floor(x), k - 2))
    f = x - i
    h = plateau * (k - 1) / 2
    f = float(np.clip((f - h) / max(1 - 2 * h, 1e-9), 0, 1))
    w = np.zeros(k)
    w[i], w[i + 1] = 1 - f, f
    return w


def drift_line(hands: Sequence[gm.Grammar], rng, *, total: float = 6.0, mode: str = "mixture",
               size=(1000, 1200), margin: float = 40.0, K: int = 8, plateau: float = 0.12,
               context: str = "kappa", checkpoint: Callable[[], None] | None = None) -> dict:
    """One line of `total` R whose hand drifts along `hands`, in the research
    frame `size` (px). Returns {"points" (N, 2), "u" per point, "hand_log"
    [(s, hand index)], "tokens", "R"}. `checkpoint` (app:) is called once per
    chunk so a cancelled preview can stop early; it never changes output."""
    k = len(hands)
    _ = int(rng.integers(1 << 30))     # research: seed of the (unused here) merged tables
    hy = HybridGrammar(hands, np.ones(k) / k, mode if mode in METHODS else "mixture")
    hy.weight_fn = lambda s: route_weights(s / total, k, plateau)
    W, H = size
    R = 0.95 * float(np.hypot(W - 2 * margin, H - 2 * margin))
    step = 1.0
    lo, hi = np.array([margin, margin]), np.array([W - margin, H - margin])
    pos = lo + (hi - lo) * rng.uniform(0.3, 0.7, 2)
    heading = float(rng.uniform(0, 2 * np.pi))
    toks: list = []
    pts = [pos[None, :]]
    s_done = 0.0
    log: list = []
    clear = 6.0
    while s_done < total - 1e-6:
        if checkpoint is not None:
            checkpoint()
        # a training-length "virtual stroke" of the hand that dominates here
        wn = route_weights(s_done / total, k, plateau)
        gh = hands[int(rng.choice(k, p=wn))]
        Ls = gh.stroke_lengths or [0.1]
        L = min(float(Ls[int(rng.integers(len(Ls)))]), total - s_done)
        L = max(L, 1e-3)
        ctx = (toks[-2] if len(toks) >= 2 else ["START"], toks[-1]) if (toks and context == "chain") else None
        drawn = np.vstack(pts)
        tree = cKDTree(drawn[:-int(4 * clear / step) or None]) if len(drawn) > 8 * clear / step else None
        best = None
        for _ in range(K):
            hy.s_offset = s_done
            hy.log = []
            c, _n = gm.generate_tokens(hy, rng, length=L, context=ctx, p_follow=gm.P_FOLLOW, end_fit=gm.END_FIT)
            if not c:
                continue
            if context == "kappa" and toks and toks[-1][0] in gm.SEG_KINDS and c[0][0] in gm.SEG_KINDS:
                _p, first = gm._continuity(toks[-1], c[0], lock_prev=True)
                c = [first] + c[1:]
            p = gm.tokens_to_points(c, R, start=pos, heading=heading, step=step)
            out = np.sum(np.clip(lo - p, 0, None) + np.clip(p - hi, 0, None)) / R
            crowd = float(np.mean(tree.query(p, k=1)[0] < clear)) if tree is not None else 0.0
            pull = float(np.linalg.norm(p[-1] - (lo + hi) / 2) / R)
            score = 50 * out + 2.0 * crowd + 0.3 * pull + 0.05 * rng.random()
            if best is None or score < best[0]:
                best = (score, c, p, hy.log)
        if best is None:
            break
        _, c, p, lg = best
        toks += c
        pts.append(p[1:])
        log += lg
        heading = gm.end_heading(c, heading)
        pos = p[-1]
        s_done += gm.stroke_length(c)
    P = np.vstack(pts)
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    u = seg / max(seg[-1], 1e-9)
    return {"points": P, "u": u, "hand_log": log, "tokens": toks, "R": R}
