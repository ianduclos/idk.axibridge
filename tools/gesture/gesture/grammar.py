"""Clothoid-alphabet grammar v2: learn a hand from long lines, draw long lines.

Stage 3 + stage 6 of docs/IDEAS-gesture-bank.md (representation A). v1 (the
2026-10-16 preview) fitted at σ = 0.01·ref, where 90–96 % of strokes are one
segment, learned from every fragment (hatching included) and scattered
strokes on the sheet. v2 changes all three (results/grammar-v2.md):

**Training set — long contiguous strokes only** (`select_long`). A stroke is
kept if its length ≥ max(`MIN_LEN_W` line widths, the drawing's
`LEN_QUANTILE` stroke-length quantile) and it is not hatching
(`hatch_mask`: a near-straight stroke with ≥ `HATCH_MIN_NEIGH` near-parallel,
similar-length, near-straight neighbours within about its own length). The
grammar's "drawing" is that subset; R = its `ref_length()`.

**Scale — σ in line widths.** Each stroke is fitted at σ = `SIGMA_W` × its
own median width (the extractor's residual wander is ~0.03–0.2 w, so 2 w
sits safely above it while long strokes carry several segments; the scale
study in experiments/grammar_eval.py picks the value).

**Alphabet and order.** Tokens as v1: segments ``[kind, l, k0, k1]``
(l = length/R, k = κ·R; kind line/arc/clothoid) and ``["corner", angle]``.
The chain is a **non-parametric order-2 model**: the next token (kind AND
params jointly) is drawn from the k nearest training transitions whose
previous token has the same kind, in a context space of
(previous token's params, the token before it — with a kind-mismatch
penalty —, log remaining length, position u = s/length in the stroke).
Every training stroke is also added reversed (direction is unknowable from
a scan). κ continuity is enforced inside corner-free runs; corners stay
tokens. Stroke lengths come from the long strokes' empirical distribution.

**Relations layer** (`generate_drawing(mode="contiguous")`, the default).
Learned per drawing from the long strokes: share of strokes with an end
attached to another stroke (endpoint within `ATTACH_W` widths), where on the
host they attach (u = s/L) and at what angle (folded to [0, π/2]); X
crossings per unit ink; share of self-crossing strokes; long-stroke ink and
count per drawing; line width / R. Generation places strokes until the ink
budget is spent: each stroke either **branches** from an existing stroke
(start on it at a learned u, heading = local tangent ± a learned angle) or
starts free at the emptiest of several candidate points. It is then walked
against the ink already down: leaving the sheet ends it; meeting another
line either **crosses** (only while the drawing's crossings stay under the
learned rate × ink) or **ends on that line** (a T-junction); meeting itself
ends it unless this stroke was drawn as a self-crossing one. Strokes shorter
than the shortest training stroke are discarded. `mode="single"` draws ONE
line of the same ink, chunk by chunk (each chunk conditioned on the previous
two tokens, κ-continuous across chunks), steering by retrying chunks that
would run into the line already drawn.

Juxtaposition (stage 6): `code_switch` (hand A → hand B along one stroke),
`generate_drawing(mode="single", hands=(gA, gB))` (alternating hands along
one long line), `translate`/`translate_tokens` (each token → its nearest of
the same kind in B), `restyle` (coarse path kept, fine turning from B).
`nearest_training_distance` is the memorisation measure.

Pure and deterministic: inputs never mutated; randomness via np.random.Generator.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree

from .clothoid import _runs, fit_stroke
from .core import Drawing, Stroke
from .curvature import integrate_kappa, resample, smooth

SEG_KINDS = ("line", "arc", "clothoid")
KINDS = ("START", "line", "arc", "clothoid", "corner")
FROM = ("START", "line", "arc", "clothoid", "corner")
TO = ("line", "arc", "clothoid", "corner", "END")

# training set
SIGMA_W = 2.0            # fit σ in line widths (scale study: results/grammar-v2.md)
MIN_LEN_W = 40.0         # long stroke: ≥ this many line widths ...
LEN_QUANTILE = 0.5       # ... and ≥ this quantile of the drawing's stroke lengths
HATCH_ANGLE = np.deg2rad(20.0)   # hatching: orientation within this of a neighbour
HATCH_LEN_RATIO = 2.5    # ... length ratio within this
HATCH_STRAIGHT = 0.8     # ... chord / length ≥ this (both strokes)
HATCH_MIN_NEIGH = 3      # ... at least this many such neighbours
HATCH_RADIUS = 1.0       # ... centroids within this × own length (≥ 15 w)
HATCH_MAX_LEN_W = 150.0  # strokes longer than this are never hatching
ATTACH_W = 2.0           # an end within this many widths of another stroke is attached
# chain
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
# drawing
CLEAR_W = 3.0            # lines keep this many widths apart unless they cross/touch
MIN_FRAC = 0.5           # a walked stroke shorter than this × its target is retried


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------

def _tok_seg(kind, l, k0, k1):
    return [kind, float(l), float(k0), float(k1)]


def _tok_corner(a):
    return ["corner", float(a)]


def fit_tokens(fit, R: float) -> list[list]:
    """A Fit (px) as a dimensionless token list: segments [kind, l, k0, k1]
    and corners ["corner", angle]. Closed fits are read as open."""
    out: list[list] = []
    for i, (run, turn) in enumerate(_runs(fit)):
        if i > 0:
            out.append(_tok_corner(turn))
        for g in run:
            if g.length <= 0:
                continue
            out.append(_tok_seg(g.kind, g.length / R, g.k0 * R, g.k1 * R))
    while out and out[0][0] == "corner":
        out.pop(0)
    while out and out[-1][0] == "corner":
        out.pop()
    return out


def reverse_tokens(toks: list[list]) -> list[list]:
    """The same stroke traversed backwards: order flipped, κ and corner
    angles negated, k0/k1 swapped."""
    out = []
    for t in reversed(toks):
        if t[0] == "corner":
            out.append(_tok_corner(-t[1]))
        else:
            out.append(_tok_seg(t[0], t[1], -t[3], -t[2]))
    return out


def shuffle_tokens(toks: list[list], rng) -> list[list]:
    """Control: the same segments and corners in a random order (corners
    only between segments, never adjacent). Destroys order, keeps the bag."""
    segs = [t for t in toks if t[0] != "corner"]
    cors = [t for t in toks if t[0] == "corner"]
    segs = [segs[i] for i in rng.permutation(len(segs))]
    gaps = sorted(rng.choice(max(len(segs) - 1, 0), min(len(cors), max(len(segs) - 1, 0)),
                         replace=False).tolist()) if len(segs) > 1 else []
    out = []
    for i, s in enumerate(segs):
        out.append(list(s))
        if i in gaps:
            out.append(list(cors[gaps.index(i)]))
    return out


def stroke_length(toks) -> float:
    return float(sum(t[1] for t in toks if t[0] != "corner"))


_stroke_len = stroke_length


def n_segments(toks) -> int:
    return sum(1 for t in toks if t[0] != "corner")


def truncate_tokens(toks: list[list], length: float) -> list[list]:
    """Tokens cut at arc length `length` (dimensionless): the last segment
    shortened with κ interpolated; trailing corners dropped."""
    out, s = [], 0.0
    for t in toks:
        if t[0] == "corner":
            out.append(list(t))
            continue
        if s + t[1] >= length:
            f = max(length - s, 0.0) / t[1] if t[1] > 0 else 0.0
            if f > 1e-9:
                out.append(_tok_seg(t[0], t[1] * f, t[2], t[2] + (t[3] - t[2]) * f))
            break
        out.append(list(t))
        s += t[1]
    while out and out[-1][0] == "corner":
        out.pop()
    return out


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
# training set: long strokes, no hatching
# ---------------------------------------------------------------------------

def stroke_width(st: Stroke, drawing: Drawing) -> float:
    if st.width is not None and len(st.width):
        return float(np.median(st.width))
    w = drawing.meta.get("line_width_px")
    return float(w) if w else 0.0025 * drawing.ref_length()


def drawing_width(drawing: Drawing) -> float:
    ws = [stroke_width(s, drawing) for s in drawing.strokes if len(s) >= 2]
    return float(np.median(ws)) if ws else 1.0


def _orient(p: np.ndarray) -> tuple[float, float]:
    """(principal-axis angle mod π, chord/length)."""
    c = p - p.mean(axis=0)
    _u, _s, vt = np.linalg.svd(c, full_matrices=False)
    a = float(np.arctan2(vt[0, 1], vt[0, 0]) % np.pi)
    L = float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)))
    return a, float(np.linalg.norm(p[-1] - p[0]) / L) if L > 0 else 0.0


def hatch_mask(drawing: Drawing) -> np.ndarray:
    """Per stroke: True if it reads as hatching — near-straight, ≤
    HATCH_MAX_LEN_W widths, with ≥ HATCH_MIN_NEIGH near-straight neighbours
    of similar length and orientation whose centroids lie within
    HATCH_RADIUS × its length (at least 15 widths)."""
    S = drawing.strokes
    n = len(S)
    out = np.zeros(n, bool)
    if n < HATCH_MIN_NEIGH + 1:
        return out
    L = np.array([s.length() for s in S])
    W = np.array([stroke_width(s, drawing) for s in S])
    C = np.array([s.points.mean(axis=0) if len(s) else [0.0, 0.0] for s in S])
    ori = [(_orient(s.points) if len(s) >= 3 and L[i] > 0 else (0.0, 0.0)) for i, s in enumerate(S)]
    A = np.array([o[0] for o in ori])
    Q = np.array([o[1] for o in ori])
    cand = (Q >= HATCH_STRAIGHT) & (L <= HATCH_MAX_LEN_W * W) & (L > 0)
    tree = cKDTree(C)
    for i in np.flatnonzero(cand):
        r = max(HATCH_RADIUS * L[i], 15 * W[i])
        nb = np.array([j for j in tree.query_ball_point(C[i], r) if j != i and cand[j]], dtype=int)
        if len(nb) < HATCH_MIN_NEIGH:
            continue
        da = np.abs(A[nb] - A[i]) % np.pi
        da = np.minimum(da, np.pi - da)
        ratio = L[nb] / L[i]
        ok = (da <= HATCH_ANGLE) & (ratio <= HATCH_LEN_RATIO) & (ratio >= 1 / HATCH_LEN_RATIO)
        out[i] = int(ok.sum()) >= HATCH_MIN_NEIGH
    return out


def select_long(drawing: Drawing, *, min_len_w: float = MIN_LEN_W,
                len_quantile: float = LEN_QUANTILE, exclude_hatching: bool = True) -> tuple[list[int], dict]:
    """Indices of the long, non-hatching strokes, plus counts/ink of all,
    hatching and kept (ink in px)."""
    S = drawing.strokes
    L = np.array([s.length() for s in S]) if S else np.zeros(0)
    W = np.array([stroke_width(s, drawing) for s in S]) if S else np.zeros(0)
    hm = hatch_mask(drawing) if exclude_hatching else np.zeros(len(S), bool)
    q = float(np.quantile(L, len_quantile)) if len(L) else 0.0
    keep = [i for i in range(len(S)) if len(S[i]) >= 3 and L[i] >= max(min_len_w * W[i], q) and not hm[i]]
    info = {"n_all": len(S), "ink_all": float(L.sum()), "n_hatch": int(hm.sum()),
            "ink_hatch": float(L[hm].sum()) if len(L) else 0.0,
            "n_long": len(keep), "ink_long": float(L[keep].sum()) if keep else 0.0,
            "width": float(np.median(W)) if len(W) else 0.0}
    return keep, info


def long_drawing(drawing: Drawing, **kw) -> Drawing:
    """The subset the grammar learns from, as a Drawing (strokes untouched)."""
    keep, info = select_long(drawing, **kw)
    return Drawing([drawing.strokes[i] for i in keep], source=drawing.source, size=drawing.size,
                   meta={**drawing.meta, "long_subset": info})


def fit_drawing(drawing: Drawing, *, sigma_w: float = SIGMA_W, sigma_frac: float | None = None,
                select: bool = True, **sel):
    """Fit the long strokes of a drawing (all strokes if select=False).
    σ = sigma_w × the stroke's median width, or sigma_frac × R if given.
    R = ref_length of the selected subset. Returns (R, [(stroke, fit, tokens)]).
    Guards (relaxed since the clothoid scan-stroke fix): finite values only."""
    d = long_drawing(drawing, **sel) if select else drawing
    R = d.ref_length()
    out = []
    for st in d.strokes:
        if len(st) < 3:
            continue
        w = stroke_width(st, d)
        sg = sigma_frac * R if sigma_frac is not None else sigma_w * w
        if st.length() < 2 * sg:
            continue
        try:
            f = fit_stroke(st.points, sigma=sg, closed=st.closed)
        except Exception:  # noqa: BLE001 — a fit failure just drops the stroke
            continue
        toks = fit_tokens(f, R)
        if not toks or not np.isfinite(f.rms_position_error):
            continue
        if not np.all(np.isfinite([v for t in toks for v in t[1:]])):
            continue
        out.append((st, f, toks))
    return R, out


def _tangent(p: np.ndarray, s: np.ndarray, i: int, half: float) -> np.ndarray:
    a = int(np.searchsorted(s, s[i] - half))
    b = min(int(np.searchsorted(s, s[i] + half)), len(p) - 1)
    a = min(a, i)
    v = p[b] - p[a]
    n = np.linalg.norm(v)
    return v / n if n > 0 else np.array([1.0, 0.0])


def relations(strokes: list[Stroke], R: float, w: float) -> dict:
    """Inter-stroke relations of a set of (long) strokes: attached ends
    (endpoint within ATTACH_W·w of another stroke): host position u and
    branch angle (folded to [0, π/2]); X crossings per unit ink (ink in R)
    and share of self-crossing strokes (as panel's rel_ group measures them)."""
    from .panel import _rel_group
    n = len(strokes)
    res = {"n": n, "attached": [], "u": [], "angle": [], "gap": [], "cross_per_ink": 0.0,
           "selfcross_frac": 0.0, "attach_w_over_R": ATTACH_W * w / R, "panel_rel": {},
           "ink": float(sum(s.length() for s in strokes) / R)}
    if n == 0:
        return res
    step = max(w / 2, 0.5)
    P, O, Sx = [], [], []
    for i, st in enumerate(strokes):
        p = resample(st.points, step)
        s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
        P.append(p)
        O.append(np.full(len(p), i))
        Sx.append(s)
    allp, own = np.vstack(P), np.concatenate(O)
    tree = cKDTree(allp)
    off = np.concatenate([[0], np.cumsum([len(p) for p in P])])
    for i, st in enumerate(strokes):
        att = 0
        p, s = P[i], Sx[i]
        if st.closed or len(p) < 3:
            res["attached"].append(0)
            continue
        for end in (0, len(p) - 1):
            k = min(len(allp), 64)
            dd, jj_ = tree.query(p[end], k=k)
            dd, jj_ = np.atleast_1d(dd), np.atleast_1d(jj_)
            oth = own[jj_] != i
            g = float(dd[oth][0]) if oth.any() else (
                float(np.min(np.linalg.norm(allp[own != i] - p[end], axis=1))) if (own != i).any() else np.inf)
            if np.isfinite(g):
                res["gap"].append(g / R)
            idx = tree.query_ball_point(p[end], ATTACH_W * w)
            other = [j for j in idx if own[j] != i]
            if not other:
                continue
            j = min(other, key=lambda j: np.linalg.norm(allp[j] - p[end]))
            h = int(own[j])
            jj = j - off[h]
            hs = Sx[h]
            att += 1
            res["u"].append(float(hs[jj] / hs[-1]) if hs[-1] > 0 else 0.5)
            t_out = _tangent(p, s, end, 5 * w) * (1 if end == 0 else -1)
            t_h = _tangent(P[h], hs, jj, 3 * w)
            c = abs(float(np.dot(t_out, t_h)))
            res["angle"].append(float(np.arccos(min(c, 1.0))))
        res["attached"].append(att)
    if n >= 2:
        rg = _rel_group(strokes, R)
        cpl = rg.get("rel_cross_per_len", 0.0)
        res["cross_per_ink"] = float(cpl) if np.isfinite(cpl) else 0.0
        sc = rg.get("rel_selfcross_frac", 0.0)
        res["selfcross_frac"] = float(sc) if np.isfinite(sc) else 0.0
        res["panel_rel"] = {k: (float(v) if np.isfinite(v) else None) for k, v in rg.items()}
    return res


def prepare_drawing(drawing: Drawing, *, sigma_w: float = SIGMA_W, **sel) -> dict:
    """Everything `learn` needs from one drawing, JSON-native (cacheable):
    selection counts, long-stroke tokens with start pos/heading, relations."""
    keep, info = select_long(drawing, **sel)
    d = Drawing([drawing.strokes[i] for i in keep], source=drawing.source, size=drawing.size,
                meta=drawing.meta)
    R, fitted = fit_drawing(d, sigma_w=sigma_w, select=False)
    w = drawing_width(d) if d.strokes else info["width"]
    out = {"source": drawing.source, "size": list(drawing.size), "R": float(R), "w": float(w),
           "sigma_w": sigma_w, "select": info, "strokes": []}
    if not d.strokes:
        out["relations"] = relations([], R, w)
        return out
    allp = np.vstack([s.points for s in d.strokes])
    lo, span = allp.min(axis=0), np.maximum(np.ptp(allp, axis=0), 1e-9)
    for st, f, toks in fitted:
        p = st.points
        k = min(len(p) - 1, max(2, len(p) // 20))
        dv = p[k] - p[0]
        out["strokes"].append({
            "tokens": [[t[0]] + [round(v, 7) for v in t[1:]] for t in toks],
            "length": round(stroke_length(toks), 7),
            "start": [round(float(v), 4) for v in (p[0] - lo) / span],
            "heading": round(float(np.arctan2(dv[1], dv[0])), 4),
            "fit_err_w": round(float(f.rms_position_error / max(stroke_width(st, d), 1e-9)), 4)})
    out["relations"] = relations(d.strokes, R, w)
    return out


# ---------------------------------------------------------------------------
# the grammar
# ---------------------------------------------------------------------------

@dataclass
class Grammar:
    """A learned hand. All fields JSON-native.

    trans: training transitions (reversal-augmented), column lists:
        p2/p1/nx kind names, f2/f1 context params (token params, START = []),
        rem (remaining length before the next token, R units), u (position
        s/length), par (next token params).
    strokes: training strokes as token lists (originals, not reversed).
    stroke_lengths: their lengths (R). counts: first-order kind counts
        (FROM × TO) for summaries.
    drawings: per training drawing {ink, n, w_over_R}.
    relations: pooled relation statistics (see `relations`).
    start_pos: stroke starts normalised to the subset's bbox.
    """
    name: str = ""
    version: int = 2
    trans: dict = field(default_factory=dict)
    strokes: list = field(default_factory=list)
    stroke_lengths: list = field(default_factory=list)
    counts: list = field(default_factory=list)
    drawings: list = field(default_factory=list)
    relations: dict = field(default_factory=dict)
    start_pos: list = field(default_factory=list)
    scale: dict = field(default_factory=dict)
    spread: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        self._cache: dict = {}

    _FIELDS = ("name", "version", "trans", "strokes", "stroke_lengths", "counts", "drawings",
               "relations", "start_pos", "scale", "spread", "meta")

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in self._FIELDS}

    @staticmethod
    def from_json(d: dict) -> "Grammar":
        return Grammar(**{k: d[k] for k in Grammar._FIELDS if k in d})

    def save(self, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_json()))

    @staticmethod
    def load(path) -> "Grammar":
        return Grammar.from_json(json.loads(Path(path).read_text()))

    # -- derived --
    def transition(self) -> np.ndarray:
        """First-order row-stochastic kind matrix (FROM × TO), for summaries."""
        C = np.asarray(self.counts, dtype=float) if self.counts else np.zeros((len(FROM), len(TO)))
        s = C.sum(axis=1, keepdims=True)
        return np.divide(C, s, out=np.zeros_like(C), where=s > 0)

    def segment_counts(self) -> dict:
        c = {k: 0 for k in SEG_KINDS + ("corner",)}
        for toks in self.strokes:
            for t in toks:
                c[t[0]] += 1
        return c

    @property
    def min_length(self) -> float:
        return float(min(self.stroke_lengths)) if self.stroke_lengths else 0.0

    def _pool(self, p1kind: str):
        """(X context matrix, p2 kinds, next kinds, next params) for one previous kind."""
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
                                    [T["nx"][i] for i in idx], [T["par"][i] for i in idx])
        return self._cache[key]

    def _kind_pool(self, kind):
        key = ("kind", kind)
        if key not in self._cache:
            P = [list(t[1:]) for toks in self.strokes for t in toks if t[0] == kind]
            self._cache[key] = None if not P else (
                np.array([_feat([kind] + p, self.scale) for p in P]), P)
        return self._cache[key]

    def draw(self, p2, p1, s: float, length: float, rng) -> tuple[str, list[float]]:
        """Next token (kind, params) given the previous two tokens, arc
        length so far s and the stroke's target length (both R units)."""
        pool = self._pool(p1[0])
        if pool is None:
            pool = self._pool("START")
            p1, p2 = ["START"], ["START"]
        X, P2, NX, PAR = pool
        q = _ctx(p2, p1, max(length - s, 1e-6), min(s / max(length, 1e-9), 1.0), self.scale)
        d = np.sum((X - q) ** 2, axis=1) + PEN_PREV2 * (P2 != p2[0])
        k = min(KNN, len(d))
        near = np.argpartition(d, k - 1)[:k]
        j = int(near[int(rng.integers(k))])
        return NX[j], _jitter(self, NX[j], list(PAR[j]), rng)


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


def jitter_tokens(g: Grammar, toks: list, rng) -> list:
    """A token list with generation's jitter applied (the quoting floor of
    the memorisation check: what copying a training stroke looks like)."""
    return [_tok_corner(*_jitter(g, "corner", [t[1]], rng)) if t[0] == "corner"
            else _tok_seg(t[0], *_jitter(g, t[0], list(t[1:]), rng)) for t in toks]


def learn(drawings: list[Drawing] | None = None, *, prepared: list[dict] | None = None,
          name: str = "", sigma_w: float = SIGMA_W, shuffle: bool = False, seed: int = 0,
          max_keep: int = 4000, **sel) -> Grammar:
    """Learn a Grammar from drawings (or from `prepare_drawing` outputs).
    shuffle=True: control grammar trained on segment-shuffled strokes."""
    rng = np.random.default_rng(seed)
    if prepared is None:
        prepared = [prepare_drawing(d, sigma_w=sigma_w, **sel) for d in (drawings or [])]
    fi, ti = {k: i for i, k in enumerate(FROM)}, {k: i for i, k in enumerate(TO)}
    counts = np.zeros((len(FROM), len(TO)), dtype=int)
    T = {k: [] for k in ("p2", "p1", "nx", "f2", "f1", "rem", "u", "par")}
    strokes, lengths, spos, per = [], [], [], []
    rel = {"n": 0, "n_attached": 0, "u": [], "angle": [], "cross": [], "selfcross": [],
           "cross_per_ink_drawings": [], "gap_free": [], "n_ends": 0, "n_ends_attached": 0}
    for pd in prepared:
        sts = [s["tokens"] for s in pd["strokes"]]
        if shuffle:
            sts = [shuffle_tokens(t, rng) for t in sts]
        per.append({"ink": round(float(sum(stroke_length(t) for t in sts)), 6), "n": len(sts),
                    "w_over_R": pd["w"] / pd["R"] if pd["R"] > 0 else 0.0})
        r = pd["relations"]
        rel["n"] += r["n"]
        rel["n_attached"] += int(sum(1 for a in r["attached"] if a > 0))
        rel["u"] += r["u"]
        rel["angle"] += r["angle"]
        rel["cross_per_ink_drawings"].append(r["cross_per_ink"])
        rel["selfcross"].append(r["selfcross_frac"])
        thr = r.get("attach_w_over_R", 0.0)
        gaps = r.get("gap", [])
        rel["n_ends"] += len(gaps)
        rel["n_ends_attached"] += int(sum(1 for x in gaps if x <= thr))
        rel["gap_free"] += [x for x in gaps if x > thr]
        for s, toks in zip(pd["strokes"], sts):
            if not toks:
                continue
            strokes.append(toks)
            L = stroke_length(toks)
            lengths.append(round(L, 7))
            spos.append(s["start"])
            for seq in (toks, reverse_tokens(toks)):
                p2, p1, pos = ["START"], ["START"], 0.0
                for t in seq + [["END"]]:
                    counts[fi[p1[0]], ti[t[0]]] += 1
                    if t[0] == "END":
                        break
                    T["p2"].append(p2[0])
                    T["p1"].append(p1[0])
                    T["nx"].append(t[0])
                    T["f2"].append([round(v, 7) for v in p2[1:]])
                    T["f1"].append([round(v, 7) for v in p1[1:]])
                    T["rem"].append(round(max(L - pos, 1e-7), 7))
                    T["u"].append(round(pos / L if L > 0 else 0.0, 5))
                    T["par"].append([round(v, 7) for v in t[1:]])
                    if t[0] != "corner":
                        pos += t[1]
                    p2, p1 = p1, t
    segs = [t for toks in strokes for t in toks if t[0] != "corner"]
    corners = [t[1] for toks in strokes for t in toks if t[0] == "corner"]
    if segs:
        ll = np.log(np.maximum([t[1] for t in segs], 1e-9))
        ak = np.arcsinh(np.array([[t[2], t[3]] for t in segs]).ravel() / KAPPA_SCALE)
        scale = {"logl": float(max(np.std(ll), 1e-3)), "ak": float(max(np.std(ak), 1e-3))}
    else:
        scale = {"logl": 1.0, "ak": 1.0}
    scale["angle"] = float(max(np.std(corners), 0.1)) if corners else 0.5
    spread = {}
    for k in SEG_KINDS:
        v = np.array([[t[2], t[3]] for t in segs if t[0] == k]).ravel()
        spread[k] = float(1.4826 * np.median(np.abs(v - np.median(v)))) if len(v) > 1 else 0.0
    ink_tot = sum(p["ink"] for p in per)
    cross_tot = sum(c * p["ink"] for c, p in zip(rel["cross_per_ink_drawings"], per))
    relations_ = {
        "p_attached": rel["n_attached"] / rel["n"] if rel["n"] else 0.0,
        "u": [round(x, 4) for x in rel["u"]], "angle": [round(x, 4) for x in rel["angle"]],
        "cross_per_ink": cross_tot / ink_tot if ink_tot > 0 else 0.0,
        "selfcross_frac": float(np.mean(rel["selfcross"])) if rel["selfcross"] else 0.0,
        # per-endpoint view (v3): share of ends attached to another stroke, and
        # the gap (R units) of the unattached ones — free starts sample it
        "p_end_attached": rel["n_ends_attached"] / rel["n_ends"] if rel["n_ends"] else 0.0,
        "gap_free": [round(x, 5) for x in (rel["gap_free"] if len(rel["gap_free"]) <= max_keep else
                                           list(rng.choice(rel["gap_free"], max_keep, replace=False)))],
        "cross_per_ink_median": float(np.median(rel["cross_per_ink_drawings"]))
        if rel["cross_per_ink_drawings"] else 0.0,
        "cross_gain": 1.0,
    }
    if len(spos) > max_keep:
        spos = [spos[i] for i in np.sort(rng.choice(len(spos), max_keep, replace=False))]
    return Grammar(
        name=name, trans=T, strokes=strokes, stroke_lengths=lengths, counts=counts.tolist(),
        drawings=per, relations=relations_, start_pos=spos, scale=scale, spread=spread,
        meta={"sigma_w": sigma_w, "shuffle": shuffle, "n_drawings": len(prepared),
              "n_strokes": len(strokes), "selection": {k: v for k, v in sel.items()},
              "sources": [p["source"] for p in prepared][:200]})


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


def generate_tokens(gA: Grammar, rng, *, gB: Grammar | None = None, switch_at: float | None = None,
                    length: float | None = None, context: tuple | None = None,
                    max_tokens: int = MAX_TOKENS) -> tuple[list, int]:
    """Run the order-2 chain to a target length (dimensionless; default: one
    of A's training lengths). The last segment is cut at the target unless
    that leaves < 30 % of it (then dropped). context = (token before last,
    last token) of a preceding chunk: conditions the first draws and makes
    the joint κ-continuous. With gB and switch_at, draws after
    switch_at·length come from gB. Returns (tokens, index of first B token
    or len(tokens))."""
    if length is None:
        L = gA.stroke_lengths or [0.1]
        length = float(L[int(rng.integers(len(L)))])
    p2, p1 = (list(context[0]), list(context[1])) if context else (["START"], ["START"])
    toks: list[list] = []
    s, g, switch_idx, draws = 0.0, gA, None, 0
    while len(toks) < max_tokens and draws < 4 * max_tokens:
        draws += 1
        if gB is not None and switch_idx is None and s >= (switch_at or 0.5) * length:
            g, switch_idx = gB, len(toks)
        kind, p = g.draw(p2, p1, s, length, rng)
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
            if frac >= 0.3 or not toks:
                toks.append(_tok_seg(tok[0], tok[1] * frac, tok[2], tok[2] + (tok[3] - tok[2]) * frac))
            break
        toks.append(tok)
        if tok[0] != "corner":
            s += tok[1]
        p2, p1 = (toks[-2] if len(toks) >= 2 else p1), toks[-1]
    while toks and toks[-1][0] == "corner":
        toks.pop()
    return toks, (switch_idx if switch_idx is not None else len(toks))


def tokens_to_points(toks: list, R: float, *, start=(0.0, 0.0), heading: float = 0.0,
                     step: float = 0.5, k_start: float | None = None) -> tuple[np.ndarray, list, list]:
    """Integrate a token list (dimensionless) at scale R (px). Returns
    (points (N,2), segments [dict kind/s0/s1/k0/k1 in px], corners
    [dict s/angle]). Corners turn instantaneously."""
    pos = np.asarray(start, dtype=np.float64)
    h = float(heading)
    out = [pos[None, :]]
    segs, corners = [], []
    s = 0.0
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
            corners.append({"s": s, "angle": float(t[1])})
            continue
        L = t[1] * R
        segs.append({"kind": t[0], "s0": s, "s1": s + L, "k0": t[2] / R, "k1": t[3] / R})
        s += L
        run.append(t)
    flush()
    return np.vstack(out), segs, corners


def _stroke(toks, R, start, heading, step, extra=None, width=None) -> Stroke:
    pts, segs, corners = tokens_to_points(toks, R, start=start, heading=heading, step=step)
    meta = {"segments": segs, "corners": corners, "tokens": toks, "ref_length": float(R),
            "start": [float(start[0]), float(start[1])], "heading": float(heading)}
    if extra:
        meta.update(extra)
    return Stroke(pts, width=None if width is None else np.full(len(pts), float(width)), meta=meta)


def generate_stroke(grammar: Grammar, rng, *, ref_length: float, start=(0.0, 0.0),
                    heading: float = 0.0, step: float = 0.5,
                    length: float | None = None) -> Stroke:
    """One stroke from the chain at drawing scale `ref_length` (px)."""
    toks, _ = generate_tokens(grammar, rng, length=length)
    return _stroke(toks, ref_length, start, heading, step, {"hand": grammar.name})


# ---------------------------------------------------------------------------
# drawings: the relations layer
# ---------------------------------------------------------------------------

def _arclen(p):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


class _Sheet:
    """Ink already on the sheet: points, owner stroke, KD-tree."""

    def __init__(self, W, H, margin, clearance):
        self.W, self.H, self.m, self.clr = W, H, margin, clearance
        self.P: list[np.ndarray] = []
        self.tree = None
        self.allp = np.zeros((0, 2))
        self.own = np.zeros(0, int)
        self._ids: list[int] = []

    def add(self, pts, sid=0):
        self.P.append(np.asarray(pts, float))
        self._ids.append(sid)
        self.allp = np.vstack(self.P)
        self.own = np.concatenate([np.full(len(p), i) for p, i in zip(self.P, self._ids)])
        self.tree = cKDTree(self.allp)

    def inside(self, pts):
        return ((pts[:, 0] >= self.m) & (pts[:, 0] <= self.W - self.m)
                & (pts[:, 1] >= self.m) & (pts[:, 1] <= self.H - self.m))

    def edge_dist(self, p):
        return float(min(p[0] - self.m, self.W - self.m - p[0], p[1] - self.m, self.H - self.m - p[1]))

    def dist(self, pts):
        if self.tree is None:
            return np.full(len(pts), np.inf)
        return self.tree.query(pts)[0]

    def dist_own(self, pts):
        """(distance to nearest ink, owner stroke id of that ink)."""
        if self.tree is None:
            return np.full(len(pts), np.inf), np.full(len(pts), -1)
        d, j = self.tree.query(pts)
        return d, self.own[j]

    def free_point(self, rng, cand):
        """The candidate farthest from existing ink."""
        if self.tree is None or len(cand) == 1:
            return cand[0]
        d, _ = self.tree.query(cand)
        return cand[int(np.argmax(d))]


def _bands(mask: np.ndarray) -> int:
    """Number of runs of True in a boolean array."""
    if not mask.any():
        return 0
    m = mask.astype(np.int8)
    return int(m[0] + np.sum(np.diff(m) == 1))


class _Grower:
    """Grows one line token by token with look-ahead steering in the hand's
    own vocabulary: at every step `K` candidate continuations are drawn from
    the chain (same context, so the same conditional distribution), each is
    integrated from the current pen position, and one is chosen at random
    among those that stay on the sheet and clear of other ink and of the
    line's own earlier part — preferring those that leave room ahead (end
    point ≥ `look` from any obstacle). Crossing candidates join the pool
    while the drawing is under its crossing budget. Nothing is inserted: a
    needed turn can only come from a turning segment (or a corner) the chain
    itself proposed. The line stops at its planned length, or earlier only
    when every candidate is blocked."""

    def __init__(self, g, rng, sheet: _Sheet, R, step, clr, look, K=8):
        self.g, self.rng, self.sheet, self.R, self.step = g, rng, sheet, R, step
        self.clr, self.look, self.K = clr, look, K

    def _candidate(self, p2, p1, s, length):
        g, rng = self.g, self.rng
        for _ in range(6):
            kind, p = g.draw(p2, p1, s, length, rng)
            if kind != "corner":
                tok = _tok_seg(kind, *p)
                _pp, tok = _continuity(p1, tok, lock_prev=True)
                return [tok]
            if p1[0] in ("START", "corner"):
                continue
            c = _tok_corner(p[0])
            kind2, p2_ = g.draw(p1, c, s, length, rng)
            if kind2 == "corner":
                continue
            return [c, _tok_seg(kind2, *p2_)]
        return None

    def grow(self, start, heading, length, *, context=None, prior=None, s_skip=0.0, host=None,
             self_ok=False, cross_ok=lambda s: False):
        """Returns (tokens, status, crosses). prior: points of an earlier part
        of the same line (single mode) — avoided like the line itself."""
        sheet, R, step, clr = self.sheet, self.R, self.step, self.clr
        pos, h = np.asarray(start, float), float(heading)
        p2, p1 = (list(context[0]), list(context[1])) if context else (["START"], ["START"])
        toks: list = []
        line = [pos[None, :]]
        line_s = [np.zeros(1)]
        s_tot = 0.0           # px along this line
        s, crosses, status = 0.0, 0, "full"
        lag = 2 * clr
        prior = np.zeros((0, 2)) if prior is None else np.asarray(prior, float)
        while s < length - 1e-9 and len(toks) < MAX_TOKENS:
            L = np.vstack(line)
            Ls = np.concatenate(line_s)
            old = np.vstack([prior, L[Ls < s_tot - lag]])
            otree = cKDTree(old) if len(old) else None
            pref, ok, cross, selfx = [], [], [], []
            for _k in range(self.K):
                seq = self._candidate(p2, p1, s, length)
                if seq is None:
                    continue
                seg = seq[-1]
                if s + seg[1] > length:                      # end at the planned length
                    f = max(length - s, 1e-9) / seg[1]
                    seq[-1] = seg = _tok_seg(seg[0], seg[1] * f, seg[2], seg[2] + (seg[3] - seg[2]) * f)
                P, _, _ = tokens_to_points(seq, R, start=pos, heading=h, step=step)
                P = P[1:]
                if len(P) == 0 or not sheet.inside(P).all():
                    continue
                sg = s_tot + _arclen(np.vstack([pos, P]))[1:]
                d_o, own = sheet.dist_own(P)
                hit_o = (d_o < clr) & ~((sg < s_skip) & (own == (-2 if host is None else host)))
                d_s = otree.query(P)[0] if otree is not None else np.full(len(P), np.inf)
                hit_s = d_s < clr
                end_clear = d_o[-1] >= clr and d_s[-1] >= clr
                # look-ahead: a ray of length `look` along the end tangent must
                # stay on the sheet and clear, so the line keeps room to go on
                he = end_heading(seq, h)
                ray = P[-1] + np.outer(np.linspace(self.look / 4, self.look, 4), [np.cos(he), np.sin(he)])
                rd = np.minimum(sheet.dist(ray), otree.query(ray)[0] if otree is not None else np.inf)
                room = self.look if (sheet.inside(ray).all() and (rd >= clr).all()) else 0.0
                item = (seq, P, sg, _bands(hit_o))
                xok = cross_ok(s)
                if not hit_o.any() and not hit_s.any():
                    (pref if room >= self.look else ok).append(item)
                elif not hit_s.any() and end_clear and xok:
                    (pref if room >= self.look else ok).append(item)
                elif hit_s.any() and end_clear and self_ok:
                    selfx.append(item)
            # first feasible in draw order = rejection sampling: the chain's own
            # proposal is kept unless it is blocked (steering only where needed)
            pool = (pref or ok or selfx)[:1]
            if not pool:
                status = "blocked"
                break
            seq, P, sg, nb = pool[0]
            crosses += nb
            toks += seq
            line.append(P)
            line_s.append(sg)
            s_tot = float(sg[-1])
            pos, h = P[-1], end_heading(seq, h)
            s += seq[-1][1]
            p2, p1 = (seq[-2] if len(seq) > 1 else p1), seq[-1]
        while toks and toks[-1][0] == "corner":
            toks.pop()
        return toks, status, crosses


def _sample(xs, rng, default):
    return float(xs[int(rng.integers(len(xs)))]) if xs else default


def generate_drawing(grammar: Grammar, rng, size, *, mode: str = "contiguous",
                     ink: float | None = None, n_strokes: int | None = None, max_strokes: int = 400,
                     ref_frac: float = 0.95, margin: float = 20.0, step: float | None = None,
                     tries: int = 6, clearance_w: float = CLEAR_W, line_width: float | None = None,
                     hands: tuple | None = None, switch_every: float = 1.0,
                     relations: str = "learned", roots: int | None = None,
                     p_branch: float | None = None, p_continue: float | None = None,
                     cross_gain: float | None = None, K: int = 8) -> Drawing:
    """A drawing on a (W, H) px canvas, R = ref_frac × the diagonal inside
    the margin (≈ the ink's own bounding-box diagonal).

    mode="contiguous" (default): long lines until the ink budget (R units;
    default: one of the training drawings' long-stroke ink) or n_strokes.
    Every line has a planned length drawn from the long-stroke distribution
    and is grown with `_Grower` (look-ahead steering by choosing among the
    chain's own proposals; it stops early only when boxed in; lines shorter
    than the shortest training stroke are retried, then dropped).
    Starts — relations="learned" (default): a line attaches at its start to
    an existing one with probability 2 × the learned share of attached ends
    (`p_branch` overrides): it **continues** from a free end (tangent ±
    N(0, 0.25) rad; share `p_continue`, default the learned share of
    attachments at a host's end) or **branches** from its interior (learned
    u, angle); otherwise it starts free, at a gap from existing ink drawn
    from the learned gaps of unattached ends (wide gaps: the emptiest of 8
    candidates). relations="tree": `roots` free lines (default 1–3), every
    later one attaches. Crossings: candidates that cross other ink are
    allowed while the drawing's crossings stay under cross_gain × the
    learned median crossings per unit ink; self-crossing lines are drawn
    with the learned share.
    mode="single": one line of that ink, grown chunk by chunk (each chunk a
    training-length "virtual stroke" conditioned on the previous two tokens,
    κ-continuous across chunks); `hands` = (gA, gB, ...) alternates hands
    every `switch_every` × a training stroke length of ink (meta["spans"]).
    Line width (px, in every stroke's width and meta) defaults to the
    training drawings' width/R × R."""
    W, H = (int(size), int(size)) if np.isscalar(size) else (int(size[0]), int(size[1]))
    # R ≈ the bounding-box diagonal the ink will have (it fills the margin box),
    # so that lengths/R measured on the result match the learned ones
    R = ref_frac * float(np.hypot(W - 2 * margin, H - 2 * margin))
    if line_width is None:
        wr = [d["w_over_R"] for d in grammar.drawings if d.get("w_over_R")]
        line_width = (float(np.median(wr)) if wr else 0.002) * R
    lw = float(line_width)
    step = float(step) if step is not None else max(0.5, 0.5 * lw)
    clr = max(clearance_w * lw, 2 * step)
    segl = [t[1] for toks in grammar.strokes[:2000] for t in toks if t[0] != "corner"]
    look = max(4 * clr, (float(np.median(segl)) if segl else 0.03) * R)
    sheet = _Sheet(W, H, margin, clr)
    if ink is None:
        inks = [d["ink"] for d in grammar.drawings if d["ink"] > 0]
        ink = _sample(inks, rng, 2.0)
    rel = grammar.relations or {}
    gain = rel.get("cross_gain", 1.0) if cross_gain is None else cross_gain
    cross_rate = gain * rel.get("cross_per_ink_median", rel.get("cross_per_ink", 0.0))
    meta = {"ref_length_gen": R, "hand": grammar.name, "mode": mode, "line_width_px": lw,
            "ink_budget": float(ink), "clearance_px": clr}
    if mode == "single":
        st = _single_line(grammar, rng, sheet, R, lw, step, clr, look, float(ink), hands,
                          switch_every, K)
        meta["crosses"] = st.meta.get("crosses", 0)
        return Drawing([st] if len(st) >= 2 else [], source=f"grammar:{grammar.name}:single",
                       size=(W, H), meta=meta)
    if mode != "contiguous":
        raise ValueError(f"unknown mode {mode!r}")
    if relations not in ("tree", "learned"):
        raise ValueError(f"unknown relations {relations!r}")
    tree = relations == "tree"
    pea = rel.get("p_end_attached", rel.get("p_attached", 0.3) / 2)
    pb = (1.0 if tree else min(1.0, 2.0 * pea)) if p_branch is None else p_branch
    if roots is None:
        roots = int(rng.integers(1, 4)) if tree else 0
    uu = np.asarray(rel.get("u") or [], float)
    pc = (float(np.mean((uu < 0.08) | (uu > 0.92))) if len(uu) else 0.3) if p_continue is None else p_continue
    self_frac = rel.get("selfcross_frac", 0.0)
    gaps = rel.get("gap_free") or []
    lengths = grammar.stroke_lengths or [0.1]
    min_len = grammar.min_length
    grower = _Grower(grammar, rng, sheet, R, step, clr, look, K)
    placed: list[Stroke] = []
    free_ends: list[tuple[int, int]] = []
    state = {"ink": 0.0, "crosses": 0}
    limit = max_strokes if n_strokes is None else min(n_strokes, max_strokes)
    fails = 0

    def crowd(pt):
        return int(sheet.tree.query_ball_point(pt, 0.08 * R, return_length=True)) if sheet.tree else 0

    def free_start():
        g = _sample(gaps, rng, 1.0) * R
        if sheet.tree is not None and g < 0.1 * R:
            for _ in range(30):                       # a point at gap ≈ g from existing ink
                q = sheet.allp[int(rng.integers(len(sheet.allp)))]
                a = rng.uniform(0, 2 * np.pi)
                c = q + max(g, 1.2 * clr) * np.array([np.cos(a), np.sin(a)])
                if not sheet.inside(c[None])[0]:
                    continue
                d = float(sheet.dist(c[None])[0])
                if 0.7 * g <= d <= 1.4 * max(g, 1.2 * clr) and d >= clr:
                    return c, rng.uniform(0, 2 * np.pi), 0.0, {"relation": "free", "gap": d / R}
        if grammar.start_pos:
            sp = np.array([grammar.start_pos[int(rng.integers(len(grammar.start_pos)))]
                           for _ in range(8)])
            sp = np.clip(sp + rng.normal(0, 0.08, sp.shape), 0, 1)
        else:
            sp = rng.random((8, 2))
        cand = margin + sp * (np.array([W, H]) - 2 * margin)
        return sheet.free_point(rng, cand), rng.uniform(0, 2 * np.pi), 0.0, {"relation": "free"}

    def attach():
        if free_ends and rng.random() < pc:
            cands = [free_ends[int(rng.integers(len(free_ends)))] for _ in range(4)]
            cands = [(crowd(placed[f[0]].points[0 if f[1] == 0 else -1]), k, f) for k, f in enumerate(cands)]
            fe = min(cands)[2]
            hp = placed[fe[0]].points
            hs = _arclen(hp)
            j = 0 if fe[1] == 0 else len(hp) - 1
            tan = _tangent(hp, hs, j, 5 * lw) * (-1 if fe[1] == 0 else 1)
            a = rng.normal(0, 0.25)
            return hp[j], float(np.arctan2(tan[1], tan[0]) + a), 2 * clr, {
                "relation": "continue", "host": fe[0], "host_end": fe[1], "host_s": float(hs[j]),
                "branch_angle": float(a)}
        Ls = np.array([p.length() for p in placed])
        best_c = None
        for _k in range(6):
            hi = int(rng.choice(len(placed), p=Ls / Ls.sum()))
            hp = placed[hi].points
            hs = _arclen(hp)
            u = float(np.clip(_sample(rel.get("u"), rng, float(rng.random())), 0.08, 0.92))
            j = int(np.clip(np.searchsorted(hs, u * hs[-1]), 0, len(hp) - 1))
            c = crowd(hp[j])
            if best_c is None or c < best_c[0]:
                best_c = (c, hi, j)
        _c, hi, j = best_c
        hp = placed[hi].points
        hs = _arclen(hp)
        tan = _tangent(hp, hs, j, 3 * lw)
        a = abs(_sample(rel.get("angle"), rng, 0.6) + rng.normal(0, 0.05))
        base = np.arctan2(tan[1], tan[0]) + (np.pi if rng.random() < 0.5 else 0.0)
        heading = float(base + (a if rng.random() < 0.5 else -a))
        s_skip = clr * (2.0 + 1.0 / max(np.sin(a), 0.2))
        return hp[j], heading, s_skip, {"relation": "branch", "host": hi, "host_s": float(hs[j]),
                                        "branch_angle": float(a)}

    while len(placed) < limit and fails < 4 * tries:
        if n_strokes is None and state["ink"] >= ink:
            break
        target = _sample(lengths, rng, 0.1)
        self_ok = bool(rng.random() < self_frac)
        best = None
        for t in range(tries):
            if placed and len(placed) >= roots and rng.random() < pb:
                start, heading, s_skip, rel_meta = attach()
            else:
                start, heading, s_skip, rel_meta = free_start()
            c0, ink0 = state["crosses"], state["ink"]
            toks, how, nc = grower.grow(
                start, heading, target, s_skip=s_skip, host=rel_meta.get("host"), self_ok=self_ok,
                cross_ok=lambda s, c0=c0, ink0=ink0: c0 < cross_rate * (ink0 + s))
            sc = stroke_length(toks)
            if best is None or sc > best[0]:
                best = (sc, toks, start, heading, nc, how, rel_meta)
            if sc >= max(0.9 * target, min_len):
                break
        if best is None or best[0] < min_len * 0.999:
            fails += 1
            continue
        sc, toks, start, heading, nc, how, rel_meta = best
        st = _stroke(toks, R, start, heading, step,
                     {"hand": grammar.name, "end": how, "crosses": nc, "target": target, **rel_meta},
                     width=lw)
        placed.append(st)
        sheet.add(st.points, len(placed) - 1)
        i = len(placed) - 1
        if rel_meta["relation"] == "continue":
            free_ends.remove((rel_meta["host"], rel_meta["host_end"]))
        if rel_meta["relation"] == "free":
            free_ends.append((i, 0))
        free_ends.append((i, 1))
        state["ink"] += st.length() / R
        state["crosses"] += nc
    meta.update(crosses=state["crosses"], ink=state["ink"], min_length=min_len,
                relations=relations, roots=roots, p_branch=pb, p_continue=pc, cross_rate=cross_rate)
    return Drawing(placed, source=f"grammar:{grammar.name}", size=(W, H), meta=meta)


def _single_line(g: Grammar, rng, sheet: _Sheet, R, lw, step, clr, look, ink, hands, switch_every, K):
    """One long line in chunks (see generate_drawing). Chunks are grown with
    the same steering as contiguous strokes, against the line drawn so far;
    a chunk that is boxed in is retried, and on the last try may cross the
    line (an occasional self-approach) — no inserted turns."""
    hands = tuple(hands) if hands else (g,)
    W, H, m = sheet.W, sheet.H, sheet.m
    if g.start_pos:
        sp = np.clip(np.array(g.start_pos[int(rng.integers(len(g.start_pos)))]), 0.15, 0.85)
    else:
        sp = rng.uniform(0.3, 0.7, 2)
    start = m + sp * (np.array([W, H]) - 2 * m)
    heading0 = rng.uniform(0, 2 * np.pi)
    lengths = g.stroke_lengths or [0.1]
    tries, backtracks = 6, 0
    # chunk stack: (tokens, points incl. start, end heading, hand name, crosses)
    chunks: list = []
    hand_i, next_switch, fails = 0, None, 0

    def state():
        toks = [t for c in chunks for t in c[0]]
        pts = np.vstack([np.asarray(start, float)[None, :]] + [c[1][1:] for c in chunks])
        pos = pts[-1]
        h = chunks[-1][2] if chunks else heading0
        return toks, pts, pos, h, sum(stroke_length(c[0]) for c in chunks)

    while fails < 8:
        all_toks, pts_all, pos, h, s_tot = state()
        if s_tot >= ink:
            break
        gh = hands[hand_i % len(hands)]
        if next_switch is None:
            next_switch = s_tot + switch_every * _sample(lengths, rng, 0.1)
        target = min(_sample(gh.stroke_lengths or lengths, rng, 0.1), ink - s_tot + 1e-6)
        ctx = ((list(all_toks[-2]) if len(all_toks) >= 2 else ["START"]), list(all_toks[-1])) \
            if all_toks else None
        s_line = _arclen(pts_all)
        prior = pts_all[s_line < s_line[-1] - 4 * clr]
        grower = _Grower(gh, rng, sheet, R, step, clr, look, K)
        best = None
        for t in range(tries):
            toks, how, nc = grower.grow(pos, h, target, context=ctx, prior=prior,
                                        self_ok=t == tries - 1)
            sc = stroke_length(toks)
            if best is None or sc > best[0]:
                best = (sc, toks, nc)
            if sc >= 0.9 * target:
                break
        sc, toks, nc = best
        if not toks or sc < 0.25 * target:
            fails += 1
            if chunks and backtracks < 12:          # boxed in: back up one chunk, regrow
                chunks.pop()
                backtracks += 1
            continue
        pts, _, _ = tokens_to_points(toks, R, start=pos, heading=h, step=step)
        chunks.append((toks, pts, end_heading(toks, h), gh.name, nc))
        if len(hands) > 1 and s_tot + sc >= next_switch:
            hand_i, next_switch = hand_i + 1, None
    all_toks, _pts, _pos, _h, _s = state()
    spans, s0 = [], 0.0
    for c in chunks:
        L = stroke_length(c[0])
        spans.append([s0 * R, (s0 + L) * R, c[3]])
        s0 += L
    crosses = sum(c[4] for c in chunks)
    return _stroke(all_toks, R, start, heading0, step,
                   {"hand": "+".join(x.name for x in hands), "mode": "single", "spans": spans,
                    "crosses": crosses}, width=lw)


# ---------------------------------------------------------------------------
# juxtaposition (stage 6)
# ---------------------------------------------------------------------------

def _long_length(g: Grammar, rng, q: float = 0.75) -> float:
    L = np.array(g.stroke_lengths or [0.2])
    big = L[L >= np.quantile(L, q)]
    return float(big[int(rng.integers(len(big)))])


def code_switch(gA: Grammar, gB: Grammar, rng, switch_at: float = 0.5, *,
                ref_length: float, start=(0.0, 0.0), heading: float = 0.0,
                step: float = 0.5, length: float | None = None) -> Stroke:
    """One stroke: A's chain up to switch_at·length, then B's, κ continuous
    across the switch (B's first draw is conditioned on A's last tokens).
    meta["switch_s"] = arc length (px) of the switch."""
    length = _long_length(gA, rng) if length is None else float(length)
    toks, si = generate_tokens(gA, rng, gB=gB, switch_at=switch_at, length=length)
    s_sw = sum(t[1] for t in toks[:si] if t[0] != "corner") * ref_length
    return _stroke(toks, ref_length, start, heading, step,
                   {"hand": f"{gA.name}->{gB.name}", "switch_index": si, "switch_s": s_sw})


def _nearest(g: Grammar, kind: str, tok: list, scale: dict):
    kp = g._kind_pool(kind)
    if kp is None:
        return None
    P = kp[1]
    F = np.array([_feat([kind] + p, scale) for p in P]) if scale is not g.scale else kp[0]
    d = np.sum((F - _feat(tok, scale)) ** 2, axis=1)
    return list(P[int(np.argmin(d))])


def translate_tokens(src: list, gA: Grammar, gB: Grammar) -> list:
    """Every token → its nearest neighbour of the same kind in B's pool
    (features scaled by the mean of A's and B's scales), κ continuity re-imposed."""
    scale = {k: 0.5 * (gA.scale[k] + gB.scale[k]) for k in gA.scale}
    out: list = []
    for t in src:
        nb = _nearest(gB, t[0], t, scale)
        tok = list(t) if nb is None else ([t[0]] + nb)
        prev = out[-1] if out else None
        newprev, tok = _continuity(prev, tok)
        if out and newprev is not prev:
            out[-1] = newprev
        out.append(tok)
    return out


def translate(fit, gA: Grammar, gB: Grammar, *, ref_length: float, start=(0.0, 0.0),
              heading: float = 0.0, step: float = 0.5) -> Stroke:
    """Re-express a clothoid.Fit (px, drawing scale ref_length) in hand B."""
    src = fit_tokens(fit, ref_length)
    out = translate_tokens(src, gA, gB)
    return _stroke(out, ref_length, start, heading, step,
                   {"hand": f"{gA.name}=>{gB.name}", "source_tokens": src})


def _kabsch(src: np.ndarray, dst: np.ndarray):
    ms, md = src.mean(axis=0), dst.mean(axis=0)
    Hm = (src - ms).T @ (dst - md)
    U, _, Vt = np.linalg.svd(Hm)
    d = np.sign(np.linalg.det(Vt.T @ U.T)) or 1.0
    Rm = Vt.T @ np.diag([1.0, d]) @ U.T
    return lambda p: (p - ms) @ Rm.T + md


def restyle(points, g: Grammar, rng, *, ref_length: float | None = None,
            coarse_frac: float = 0.04, detail_frac: float = 0.015, amount: float = 1.0,
            step: float = 0.5) -> Stroke:
    """Keep a path's coarse shape, replace its fine turning with hand g
    (Kalnins' base path + learned residual). Base: `fit_stroke` at
    σ_c = coarse_frac·length re-integrated and aligned (or the smoothed input
    if that fit is implausible); residual: a same-length stroke from g's
    chain, its θ(s) high-passed at σ_d = detail_frac·R and added × amount.
    End points pinned to the input's."""
    from .clothoid import reconstruct
    pts = np.array(points, dtype=np.float64, copy=True)
    L = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
    if ref_length is None:
        ref_length = float(np.hypot(*np.ptp(pts, axis=0))) / 0.4
    R = float(ref_length)
    sc = max(coarse_frac * L, 1e-6)
    base_fit = fit_stroke(pts, sigma=sc)
    rin = resample(pts, step)
    ok = (all(abs(a) <= np.pi for a in base_fit.corner_angles)
          and np.isfinite(base_fit.rms_position_error) and base_fit.rms_position_error <= sc)
    if ok:
        base = reconstruct(base_fit, step=step)
        n = min(len(base), len(rin))
        u_b = np.linspace(0, len(base) - 1, n).astype(int)
        u_i = np.linspace(0, len(rin) - 1, n).astype(int)
        base = _kabsch(base[u_b], rin[u_i])(base)
    else:
        base = smooth(rin, sc, step)
    base = resample(base, step)
    T = float(np.sum(np.linalg.norm(np.diff(base, axis=0), axis=1)))
    db = np.diff(base, axis=0)
    th_b = np.unwrap(np.arctan2(db[:, 1], db[:, 0]))
    toks, _ = generate_tokens(g, rng, length=T / R)
    rp, _, _ = tokens_to_points(toks, R, step=step)
    rp = resample(rp, step)
    dr = np.diff(rp, axis=0)
    th_r = np.unwrap(np.arctan2(dr[:, 1], dr[:, 0]))
    m = len(th_b)
    if len(th_r) < m:
        th_r = np.concatenate([th_r, np.full(m - len(th_r), th_r[-1] if len(th_r) else 0.0)])
    th_r = th_r[:m]
    sd = max(detail_frac * R, step) / step
    hp = th_r - gaussian_filter1d(th_r, sd, mode="nearest")
    th = th_b + amount * hp
    seg = np.diff(np.linspace(0, T, m + 1))
    new = np.vstack([base[:1], base[0] + np.cumsum(np.column_stack(
        [np.cos(th) * seg, np.sin(th) * seg]), axis=0)])
    w = np.linspace(0, 1, len(new))[:, None]
    new = new + (1 - w) * (pts[0] - new[0]) + w * (pts[-1] - new[-1])
    return Stroke(new, meta={"hand": g.name, "restyle": True, "coarse_sigma": sc,
                             "base": "fit" if ok else "smoothed", "detail_sigma": sd * step,
                             "tokens": toks, "ref_length": R})


# ---------------------------------------------------------------------------
# memorisation check
# ---------------------------------------------------------------------------

SIG_N = 48
SIG_LEN_W = 0.5      # rad per e-fold of stroke-length mismatch


def turning_signature(toks: list) -> np.ndarray | None:
    """Dimensionless κ(s) signature of a token stroke: the turning function
    θ(u) (∫κ ds plus corner steps, mean removed) at SIG_N points of
    u = s/length, scaled by 1/√SIG_N, plus SIG_LEN_W·log(length)."""
    segs = [t for t in toks if t[0] != "corner"]
    if not segs:
        return None
    L = stroke_length(toks)
    if L <= 0:
        return None
    u = (np.arange(SIG_N) + 0.5) / SIG_N * L
    th = np.zeros(SIG_N)
    s = 0.0
    acc = 0.0
    for t in toks:
        if t[0] == "corner":
            th[u >= s] += t[1]
            continue
        l, k0, k1 = t[1], t[2], t[3]
        inside = (u >= s) & (u < s + l)
        x = u[inside] - s
        th[inside] += acc + k0 * x + 0.5 * (k1 - k0) / l * x * x
        acc += 0.5 * (k0 + k1) * l
        s += l
    th[u >= s] += acc
    th -= th.mean()
    return np.concatenate([th / np.sqrt(SIG_N), [SIG_LEN_W * np.log(L)]])


def _sig_matrix(token_lists) -> np.ndarray:
    S = [turning_signature(t) for t in token_lists]
    return np.array([s for s in S if s is not None])


def _min_dist(Q: np.ndarray, T: np.ndarray, chunk: int = 256) -> np.ndarray:
    """Min distance from each row of Q to rows of T and T's reversals."""
    Trev = T.copy()
    Trev[:, :-1] = T[:, -2::-1]
    TT = np.vstack([T, Trev])
    out = np.empty(len(Q))
    tn = np.einsum("ij,ij->i", TT, TT)
    for i in range(0, len(Q), chunk):
        q = Q[i:i + chunk]
        d2 = np.einsum("ij,ij->i", q, q)[:, None] + tn[None, :] - 2 * q @ TT.T
        out[i:i + chunk] = np.sqrt(np.maximum(d2.min(axis=1), 0))
    return out


def nearest_training_distance(generated_strokes, grammar_or_tokens) -> np.ndarray:
    """For each stroke (a Stroke with meta["tokens"], or a token list), the
    minimum turning-signature distance (either direction) to the training
    strokes (a Grammar, or a list of token lists). Small = near-copy."""
    toks = [s.meta["tokens"] if isinstance(s, Stroke) else s for s in generated_strokes]
    train = grammar_or_tokens.strokes if isinstance(grammar_or_tokens, Grammar) else grammar_or_tokens
    Q = _sig_matrix(toks)
    T = _sig_matrix(train)
    if len(Q) == 0 or len(T) == 0:
        return np.zeros(0)
    return _min_dist(Q, T)
