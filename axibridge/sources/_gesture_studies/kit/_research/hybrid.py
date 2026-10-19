# FROZEN from research commit ecd64f8: tools/gesture/gesture/hybrid.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Hybrid hands: two (or more) learned grammars made into one hand.

Research round 8 (results/hybrid_hands-2026-10-16.md). Nothing in
`grammar.py` changes: a hybrid is a `grammar.Grammar` whose data are the
parents' concatenated (so every generator — `generate_drawing`, `restyle`,
`generate_tokens` — runs on it unchanged) and whose `draw` decides, per
token, which parent speaks. Four methods:

- **pooled** — one k-NN pool over both parents' transitions; the context
  (previous two tokens, remaining length, position) decides which parent's
  record comes next. Sheet-level data (drawings → ink budget and line plans,
  relations, start positions) are mixed by weight.
- **mixture** — each token is drawn from parent i with probability w_i, from
  that parent's own pool (conditioned on the previous tokens whatever hand
  drew them). Follows (source-stroke runs) only continue within a parent.
- **crossover** — the line is cut into arc-length blocks of `period` (R
  units); each block is spoken entirely by one parent (low-discrepancy
  assignment with shares w), so segment runs of each hand alternate.
- **interp** — each token is drawn from a parent (chosen by weight) and its
  parameters moved toward its nearest same-kind token in the other parent
  (log length, κ·R, corner angle) by the other parent's share: a token that
  neither hand has.

Weights can be a function of the line's global arc length (`weight_fn`,
used by `drift_line`, the limb: one line whose hand drifts along a route of
parents).

Panel helpers place real groups and generated sheets in the standard
preprocessed panel space (`medium`: σ ≥ 7 w + INLP medium projection, fitted
on real drawings only) and measure where a hybrid lands relative to its
parents: position t along the parent axis, off-axis distance relative to the
parents' own off-axis spread, classifier P(B), and AUC of hybrid vs each
parent.

Pure and deterministic: inputs never mutated; randomness via np.random.Generator.
"""
from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from . import grammar as gm
from .core import Drawing, Stroke

METHODS = ("pooled", "mixture", "crossover", "interp")
CROSS_PERIOD = 0.06      # crossover block length (R units) ≈ 2 Matisse segments
GOLDEN = 0.6180339887498949


# ---------------------------------------------------------------------------
# merging data
# ---------------------------------------------------------------------------

def _resample_list(lists: Sequence[list], w: np.ndarray, rng, cap: int = 3000) -> list:
    """Pool sample lists by weight: n_i = round(w_i · N) draws (with
    replacement) from list i, N = min(cap, max len)."""
    lens = [len(x) for x in lists]
    N = min(cap, max(lens) if lens else 0)
    out: list = []
    for x, wi in zip(lists, w):
        k = int(round(wi * N))
        if k and len(x):
            idx = rng.integers(len(x), size=k)
            out += [x[i] for i in idx]
    return out


def _mix_dict(dicts: Sequence[dict], w: np.ndarray, rng) -> dict:
    """Weighted mix of relation-style dicts: numbers averaged, lists pooled
    by weight, dicts recursed; a key missing in some parents comes from the
    others (weights renormalised)."""
    keys = []
    for d in dicts:
        for k in d:
            if k not in keys:
                keys.append(k)
    out = {}
    for k in keys:
        have = [(d[k], wi) for d, wi in zip(dicts, w) if k in d and d[k] is not None]
        if not have:
            continue
        vals, ws = [h[0] for h in have], np.array([h[1] for h in have], float)
        ws = ws / ws.sum() if ws.sum() > 0 else np.full(len(ws), 1 / len(ws))
        v0 = vals[0]
        if isinstance(v0, bool):
            out[k] = bool(vals[int(np.argmax(ws))])
        elif isinstance(v0, (int, float)):
            out[k] = float(np.sum([float(v) * wi for v, wi in zip(vals, ws)]))
        elif isinstance(v0, list):
            out[k] = _resample_list(vals, ws, rng)
        elif isinstance(v0, dict):
            out[k] = _mix_dict(vals, ws, rng)
        else:
            out[k] = vals[int(np.argmax(ws))]
    return out


def merge_data(hands: Sequence[gm.Grammar], weights, *, seed: int = 0) -> dict:
    """The fields of a Grammar that concatenates `hands` (transitions,
    strokes, drawings with re-based stroke ranges) and mixes their
    sheet-level statistics by `weights`. Drawings are replicated so each
    parent's share of the drawing list equals its weight (generate_drawing
    picks the source drawing uniformly)."""
    rng = np.random.default_rng(seed)
    w = np.asarray(weights, float)
    w = w / w.sum()
    T = {k: [] for k in ("p2", "p1", "nx", "f2", "f1", "rem", "u", "par", "sid")}
    strokes, lengths, spos, drawings = [], [], [], []
    counts = None
    nt = max((len(g.drawings) / wi for g, wi in zip(hands, w) if wi > 0 and g.drawings), default=1.0)
    for g, wi in zip(hands, w):
        s0 = len(strokes)
        for k in T:
            col = g.trans.get(k, [])
            T[k] += [v + 2 * s0 for v in col] if k == "sid" else list(col)
        strokes += g.strokes
        lengths += g.stroke_lengths
        C = np.asarray(g.counts, int) if g.counts else 0
        counts = C if counts is None else counts + C
        D = [dict(d, i0=d.get("i0", 0) + s0, i1=d.get("i1", 0) + s0, hand=g.name) for d in g.drawings]
        if D and wi > 0:
            reps = max(1, int(round(wi * nt / len(D))))
            drawings += D * reps
    spos = _resample_list([g.start_pos for g in hands], w, rng, cap=2000)
    rel = _mix_dict([g.relations or {} for g in hands], w, rng)
    scale = {k: float(np.exp(np.sum([wi * np.log(max(g.scale.get(k, 1.0), 1e-9)) for g, wi in zip(hands, w)])))
             for k in hands[0].scale}
    spread = {k: float(np.sum([wi * g.spread.get(k, 0.0) for g, wi in zip(hands, w)])) for k in gm.SEG_KINDS}
    return dict(trans=T, strokes=strokes, stroke_lengths=lengths,
                counts=(counts.tolist() if isinstance(counts, np.ndarray) else []),
                drawings=drawings, relations=rel, start_pos=spos, scale=scale, spread=spread)


# ---------------------------------------------------------------------------
# the hybrid grammar
# ---------------------------------------------------------------------------

class HybridGrammar(gm.Grammar):
    """A Grammar over the concatenated data of `hands`, whose `draw` lets
    the parents speak by `method` (see module docstring). Record indices
    returned by `draw` index the concatenated `trans`, so follows work.

    weight_fn: optional callable(global_s) → weights; `s_offset` is added to
    the s that `draw` receives (drift_line sets it per chunk). Tokens drawn
    are logged in `self.log` as (global s, hand index) when `log` is a list.
    """

    def __init__(self, hands: Sequence[gm.Grammar], weights, method: str = "mixture", *,
                 period: float = CROSS_PERIOD, seed: int = 0, name: str | None = None, **_):
        if method not in METHODS:
            raise ValueError(f"unknown method {method!r} ({METHODS})")
        data = merge_data(hands, weights, seed=seed)
        nm = name or ("x".join(g.name for g in hands) + f"[{method}]")
        super().__init__(name=nm, version=6, meta={"hybrid": method, "parents": [g.name for g in hands],
                                                   "weights": [float(x) for x in np.asarray(weights, float)]},
                         **data)
        self.hands = list(hands)
        self.method = method
        self.weights = np.asarray(weights, float) / np.sum(weights)
        self.period = float(period)
        self.offsets = np.cumsum([0] + [len(g.trans.get("p1", [])) for g in hands])
        self.weight_fn: Callable | None = None
        self.s_offset = 0.0
        self.log: list | None = None

    # -- helpers --
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

    def _pick(self, w: np.ndarray, s: float, length: float, rng) -> int:
        if self.method == "crossover":
            b = np.floor((self.s_offset + s) / self.period)
            off = (length * 997.13) % 1.0
            x = (off + b * GOLDEN) % 1.0
            return int(min(np.searchsorted(np.cumsum(w), x, side="right"), len(w) - 1))
        return int(rng.choice(len(w), p=w))

    def draw(self, p2, p1, s, length, rng, prev_rec=None, p_follow=0.0, kmatch=0.0, knn=gm.KNN,
             weights=None, dscale=None, w_ds=0.0):
        if self.method == "pooled":
            out = super().draw(p2, p1, s, length, rng, prev_rec=prev_rec, p_follow=p_follow, kmatch=kmatch,
                               knn=knn, weights=weights)
            if self.log is not None:
                self.log.append((self.s_offset + s, self._decode(out[2])[0]))
            return out
        w = self._w(s)
        h = self._pick(w, s, length, rng)
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


def make_hybrid(gA: gm.Grammar, gB: gm.Grammar, method: str, *, t: float = 0.5, seed: int = 0,
                period: float = CROSS_PERIOD) -> HybridGrammar:
    """Two-parent hybrid with B's share t."""
    return HybridGrammar([gA, gB], [1 - t, t], method, seed=seed, period=period)


# ---------------------------------------------------------------------------
# data helpers
# ---------------------------------------------------------------------------

def tile_drawing(d: Drawing, nx: int, ny: int, min_strokes: int = 5) -> list[Drawing]:
    """Split one big figure into nx × ny drawings by stroke centroid (one
    Lichtenberg figure → several 'sheets' so line plans and ink budgets
    vary). Strokes are not cut; tiles with < min_strokes are dropped."""
    P = np.vstack([s.points for s in d.strokes]) if d.strokes else np.zeros((1, 2))
    lo, hi = P.min(0), P.max(0)
    span = np.maximum(hi - lo, 1e-9)
    buckets: dict = {}
    for s in d.strokes:
        c = (s.points.mean(0) - lo) / span
        key = (min(int(c[0] * nx), nx - 1), min(int(c[1] * ny), ny - 1))
        buckets.setdefault(key, []).append(s)
    return [Drawing(v, source=f"{d.source}#{k[0]}{k[1]}", size=d.size, meta=dict(d.meta))
            for k, v in sorted(buckets.items()) if len(v) >= min_strokes]


def structure_from(d: Drawing) -> Drawing:
    """The fixed skeleton every hand redraws: the drawing's long strokes."""
    return gm.long_drawing(d)


def restyle_drawing(struct: Drawing, g: gm.Grammar, rng, *, amount: float = 1.0) -> Drawing:
    """Every stroke of `struct` redrawn with hand g's fine turning
    (`grammar.restyle`; coarse path and end points kept)."""
    R = struct.ref_length()
    out = []
    for s in struct.strokes:
        if len(s.points) < 4 or s.length() < 1e-6:
            continue
        try:
            out.append(gm.restyle(s.points, g, rng, ref_length=R, amount=amount))
        except Exception:  # noqa: BLE001 — degenerate stroke: keep it as is
            out.append(Stroke(np.array(s.points, copy=True)))
    return Drawing(out, source=f"restyle:{g.name}", size=struct.size)


# ---------------------------------------------------------------------------
# the limb: a line whose hand drifts
# ---------------------------------------------------------------------------

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


def route_colours(u: np.ndarray, k: int, palette) -> list:
    pal = np.asarray(palette[:k], float)
    return [tuple(int(v) for v in route_weights(x, k) @ pal) for x in np.asarray(u)]


def drift_line(hands: Sequence[gm.Grammar], rng, *, total: float = 6.0, mode: str = "mixture",
               size=(1000, 1200), margin: float = 40.0, chunk: float = 0.0, K: int = 8,
               plateau: float = 0.12, context: str = "kappa") -> tuple[Stroke, dict]:
    """One line of `total` R whose hand drifts along `hands` (route_weights
    over the line's arc length). Grown in chunks of `chunk` R (0 = default: a
    training stroke length of the hand that dominates at that point), each the best
    of K chain proposals (κ-continuous with the previous chunk via the
    chain's context): score = points outside the margin box + crowding of
    the line drawn so far. Returns the stroke (meta: tokens, per-point u,
    per-token hand log) and an info dict."""
    k = len(hands)
    hy = HybridGrammar(hands, np.ones(k) / k, mode if mode in METHODS else "mixture", seed=int(rng.integers(1 << 30)))
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
    from scipy.spatial import cKDTree
    while s_done < total - 1e-6:
        if chunk > 0:
            L = min(chunk, total - s_done)
        else:   # a training-length "virtual stroke" of the hand that dominates here (a chunk far longer
            # than a hand's strokes sends its k-NN into extrapolated remaining-length contexts: lines + corners)
            wn = route_weights(s_done / total, k, plateau)
            gh = hands[int(rng.choice(k, p=wn))]
            Ls = gh.stroke_lengths or [0.1]
            L = min(float(Ls[int(rng.integers(len(Ls)))]), total - s_done)
        L = max(L, 1e-3)
        # context="chain" conditions each chunk's k-NN on the previous chunk's last two tokens (as
        # grammar's single mode does); in short-stroke hands (shikasta, Lichtenberg) that sends the chain
        # into a corner/line attractor (|κ| median 0, corners 3-15x the hand's). Default "kappa": fresh
        # chunk, κ made continuous at the joint afterwards, heading continuous.
        ctx = (toks[-2] if len(toks) >= 2 else ["START"], toks[-1]) if (toks and context == "chain") else None
        drawn = np.vstack(pts)
        tree = cKDTree(drawn[:-int(4 * clear / step) or None]) if len(drawn) > 8 * clear / step else None
        best = None
        for _ in range(K):
            hy.s_offset = s_done
            hy.log = []
            c, _ = gm.generate_tokens(hy, rng, length=L, context=ctx, p_follow=gm.P_FOLLOW, end_fit=gm.END_FIT)
            if not c:
                continue
            if context == "kappa" and toks and toks[-1][0] in gm.SEG_KINDS and c[0][0] in gm.SEG_KINDS:
                _, first = gm._continuity(toks[-1], c[0], lock_prev=True)
                c = [first] + c[1:]
            p, _, _ = gm.tokens_to_points(c, R, start=pos, heading=heading, step=step)
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
    u = (seg / max(seg[-1], 1e-9)).tolist()
    st = Stroke(P, width=None, meta={"tokens": toks, "u": u, "hand_log": log, "ref_length": R,
                                     "route": [g.name for g in hands]})
    shares = np.zeros((10, k))
    for s, h in log:
        b = min(int(s / total * 10), 9)
        shares[b, h] += 1
    shares = shares / np.maximum(shares.sum(1, keepdims=True), 1)
    return st, {"route": [g.name for g in hands], "mode": mode, "length_R": gm.stroke_length(toks),
                "tokens": len(toks), "hand_share_by_decile": np.round(shares, 2).tolist()}


def window_stats(toks: list, n_win: int = 10) -> list[dict]:
    """Per arc-length window of a token line: corners per R, median segment
    length (R), median |κ|·R of segments, share of corner tokens."""
    L = gm.stroke_length(toks)
    rows = [{"corners": 0, "segl": [], "k": []} for _ in range(n_win)]
    s = 0.0
    for t in toks:
        b = min(int(s / max(L, 1e-9) * n_win), n_win - 1)
        if t[0] == "corner":
            rows[b]["corners"] += 1
            continue
        rows[b]["segl"].append(t[1])
        rows[b]["k"].append(abs(0.5 * (t[2] + t[3])))
        s += t[1]
    wl = L / n_win
    return [{"corners_per_R": r["corners"] / max(wl, 1e-9),
             "seg_q50": float(np.median(r["segl"])) if r["segl"] else float("nan"),
             "absk_q50": float(np.median(r["k"])) if r["k"] else float("nan")} for r in rows]


def hand_stats(g: gm.Grammar) -> dict:
    """The same quantities over a grammar's training strokes (reference levels)."""
    segl = [t[1] for toks in g.strokes for t in toks if t[0] != "corner"]
    k = [abs(0.5 * (t[2] + t[3])) for toks in g.strokes for t in toks if t[0] != "corner"]
    nc = sum(1 for toks in g.strokes for t in toks if t[0] == "corner")
    return {"corners_per_R": nc / max(sum(g.stroke_lengths), 1e-9), "seg_q50": float(np.median(segl)),
            "absk_q50": float(np.median(k))}


# ---------------------------------------------------------------------------
# panel space
# ---------------------------------------------------------------------------

def _matrix(feats: dict, names: list[str] | None = None):
    keys = [k for k in feats if feats[k]]
    if names is None:
        names = sorted({n for k in keys for n in feats[k] if n.split("_", 1)[0] not in ("w", "end")})
    X = np.array([[feats[k].get(n, np.nan) for n in names] for k in keys], float)
    return keys, names, X


def projector(real: dict):
    """MediumProjector fitted on the real drawings (keys 'group|stem');
    returns (transform(X) → Z, names)."""
    from .medium import MediumProjector, load_media, load_pairs
    keys, names, X = _matrix(real)
    ok = ~np.all(np.isnan(X), axis=0)
    names = [n for n, o in zip(names, ok) if o]
    X = X[:, ok]
    media = load_media()
    grp = np.array([k.split("|")[0] for k in keys])
    med = np.array([media.get(tuple(k.split("|", 1)), "unknown") for k in keys])
    P = MediumProjector(load_pairs()).fit(X, grp, med)
    return (lambda Y: np.nan_to_num(P.transform(Y))), names, keys, np.nan_to_num(P.transform(X))


def cv_auc(Z: np.ndarray, y: np.ndarray, reps: int = 5, seed: int = 0) -> float:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold
    nmin = int(min(y.sum(), (1 - y).sum()))
    if nmin < 3:
        return float("nan")
    k = min(5, nmin)
    sc = []
    for r in range(reps):
        pr = np.zeros(len(y))
        for tr, te in StratifiedKFold(k, shuffle=True, random_state=seed + r).split(Z, y):
            clf = LogisticRegression(C=0.5, max_iter=4000).fit(Z[tr], y[tr])
            pr[te] = clf.predict_proba(Z[te])[:, 1]
        sc.append(roc_auc_score(y, pr))
    return float(np.mean(sc))


def place_groups(real: dict, focus: str) -> dict:
    """Where `focus` sits among the real groups: CV AUC focus vs each group,
    centroid distance / mean within-group RMS radius, and the share of
    focus sheets whose nearest other-group centroid is each group."""
    tf, names, keys, Z = projector(real)
    grp = np.array([k.split("|")[0] for k in keys])
    groups = sorted(set(grp))
    cen = {g: Z[grp == g].mean(0) for g in groups}
    rad = {g: float(np.sqrt(np.mean(np.sum((Z[grp == g] - cen[g]) ** 2, 1)))) for g in groups}
    out = {"n": {g: int((grp == g).sum()) for g in groups}, "auc": {}, "dist": {}, "nearest_share": {}}
    f = grp == focus
    for g in groups:
        if g == focus:
            continue
        m = f | (grp == g)
        out["auc"][g] = round(cv_auc(Z[m], (grp[m] == focus).astype(int)), 3)
        out["dist"][g] = round(float(np.linalg.norm(cen[focus] - cen[g]) / (0.5 * (rad[focus] + rad[g]))), 3)
    others = [g for g in groups if g != focus]
    C = np.array([cen[g] for g in others])
    nn = [others[int(np.argmin(np.sum((C - z) ** 2, 1)))] for z in Z[f]]
    out["nearest_share"] = {g: round(nn.count(g) / max(len(nn), 1), 3) for g in others if nn.count(g)}
    # 2-D view: PCA of all group centroids' space
    from sklearn.decomposition import PCA
    pca = PCA(2, random_state=0).fit(Z)
    out["pca"] = {k: [round(float(v), 4) for v in pca.transform(Z[i:i + 1])[0]] for i, k in enumerate(keys)}
    return out


def axis_position(Zh: np.ndarray, ZA: np.ndarray, ZB: np.ndarray) -> dict:
    """Position of sheets Zh relative to parents A, B: t = projection on the
    A→B centroid axis (0 = A, 1 = B), off = distance from the axis line
    divided by the parents' own median off-axis distance (1 = as far off as
    a parent sheet)."""
    a, b = ZA.mean(0), ZB.mean(0)
    v = b - a
    vv = float(v @ v) or 1e-12

    def tt(Z):
        t = (Z - a) @ v / vv
        r = Z - a - np.outer(t, v)
        return t, np.linalg.norm(r, axis=1)

    _, offA = tt(ZA)
    _, offB = tt(ZB)
    ref = float(np.median(np.r_[offA, offB])) or 1e-12
    t, off = tt(Zh)
    return {"t_q50": float(np.median(t)), "t_q25": float(np.quantile(t, .25)), "t_q75": float(np.quantile(t, .75)),
            "off_ratio": float(np.median(off) / ref)}


def hybrid_positions(gen: dict, real: dict, pairs, methods) -> dict:
    """Per pair and method: axis position (generated-parent axis and real-parent
    axis), classifier P(B) trained on generated parents, and CV AUC of the
    hybrid vs each generated parent."""
    from sklearn.linear_model import LogisticRegression
    tf, names, rkeys, Zr = projector(real)
    rgrp = np.array([k.split("|")[0] for k in rkeys])
    keys = [k for k in gen if gen[k]]
    X = np.array([[gen[k].get(n, np.nan) for n in names] for k in keys], float)
    Z = tf(X)
    out = {}
    for A, B in pairs:
        sel = {m: np.array([k.startswith(f"{A}__{B}__{m}__") for k in keys]) for m in methods}
        ZA, ZB = Z[sel["parentA"]], Z[sel["parentB"]]
        if len(ZA) < 3 or len(ZB) < 3:
            continue
        clf = LogisticRegression(C=0.5, max_iter=4000).fit(np.vstack([ZA, ZB]), np.r_[np.zeros(len(ZA)), np.ones(len(ZB))])
        RA, RB = Zr[rgrp == A], Zr[rgrp == B]
        row = {"n": {m: int(sel[m].sum()) for m in methods},
               "parents_auc": round(cv_auc(np.vstack([ZA, ZB]), np.r_[np.zeros(len(ZA)), np.ones(len(ZB))].astype(int)), 3)}
        for m in methods:
            Zh = Z[sel[m]]
            if len(Zh) < 3:
                continue
            r = {"gen_axis": axis_position(Zh, ZA, ZB), "pB": float(np.mean(clf.predict_proba(Zh)[:, 1]))}
            if len(RA) >= 3 and len(RB) >= 3:
                r["real_axis"] = axis_position(Zh, RA, RB)
            if m not in ("parentA", "parentB"):
                r["auc_vs_A"] = round(cv_auc(np.vstack([ZA, Zh]), np.r_[np.zeros(len(ZA)), np.ones(len(Zh))].astype(int)), 3)
                r["auc_vs_B"] = round(cv_auc(np.vstack([ZB, Zh]), np.r_[np.zeros(len(ZB)), np.ones(len(Zh))].astype(int)), 3)
            row[m] = r
        out[f"{A}|{B}"] = row
    return out


def positions_table(rep: dict) -> str:
    L = ["| # | pair | method | t (gen axis) | off-axis ratio | P(B) | AUC vs A | AUC vs B | t (real axis) |",
         "|---|---|---|---|---|---|---|---|---|"]
    i = 0
    for pair, row in rep.items():
        for m, r in row.items():
            if not isinstance(r, dict) or "gen_axis" not in r:
                continue
            i += 1
            ga, ra = r["gen_axis"], r.get("real_axis", {})
            L.append(f"| {i} | {pair} | {m} | {ga['t_q50']:.2f} ({ga['t_q25']:.2f}–{ga['t_q75']:.2f}) | "
                     f"{ga['off_ratio']:.2f} | {r['pB']:.2f} | {r.get('auc_vs_A', float('nan')):.2f} | "
                     f"{r.get('auc_vs_B', float('nan')):.2f} | {ra.get('t_q50', float('nan')):.2f} |")
        L.append(f"|  | {pair} | (parents AUC) | {row.get('parents_auc')} | | | | | |")
    return "\n".join(L) + "\n"
