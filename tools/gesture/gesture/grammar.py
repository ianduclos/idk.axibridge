"""Clothoid-alphabet grammar: learn a hand, generate with it, juxtapose hands.

Stage 3 + stage 6 of docs/IDEAS-gesture-bank.md (representation A). A hand is
modelled as

1. a first-order **Markov chain over tokens** — segment kinds ``line``,
   ``arc``, ``clothoid`` plus ``corner``, framed by ``START`` / ``END`` —
   counted from `clothoid.fit_stroke` decompositions of real strokes, with
   additive smoothing over the structurally allowed transitions
   (START→corner, START→END, corner→corner and corner→END are impossible);
2. per transition ``prev>next``, the **empirical pool of observed
   (prev params, next params) pairs**. The next token's parameters are drawn
   by nearest-neighbour resampling: the k pairs whose *prev* params are
   closest to the current token's, one picked at random, its *next* params
   copied with a small jitter. κ continuity is then enforced: inside a
   corner-free run the next segment starts at the previous one's end κ
   (arcs take that κ, a line after a clothoid pulls the clothoid's end to 0).

Everything is **dimensionless** (README "Units"): a segment is
``[length/R, k0·R, k1·R]`` and a corner is ``[angle]`` (rad), R the source
drawing's `ref_length()`. Stroke direction is unknowable from a scan, so every
training stroke is also added **reversed** (order flipped, κ negated): the
chain is direction-free and κ-sign symmetric by construction.

Smoothing scale: σ = sigma_frac·R as everywhere else, except that a stroke
shorter than 10σ is fitted at σ = max(length/10, width/2, 0.002·R) — at the
drawing-level σ such a stroke is smoothed flat and `fit_stroke` returns its
one-segment fallback with a κ biased toward 0. This mixes scales for short
strokes; it is recorded in the grammar (``meta["short_sigma"]``).

Generation integrates κ(s) with `curvature.integrate_kappa` and applies
corners as instantaneous turns. Composition (where strokes go) is modelled
only loosely: empirical start positions/headings and stroke counts.

Juxtaposition (stage 6): `code_switch` (hand A → hand B along one stroke,
κ-continuous at the switch), `translate` (each segment of a fit replaced by
its nearest neighbour of the same kind in B's pool), `restyle` (a path's
coarse shape kept, its fine turning replaced by B's — Kalnins' base path +
learned residual). `nearest_training_distance` is the memorisation check.

Pure and deterministic: inputs never mutated; randomness via np.random.Generator.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .clothoid import fit_stroke, _runs
from .core import Drawing, Stroke
from .curvature import integrate_kappa, resample, smooth

SEG_KINDS = ("line", "arc", "clothoid")
FROM = ("START", "line", "arc", "clothoid", "corner")
TO = ("line", "arc", "clothoid", "corner", "END")
_FORBIDDEN = {("START", "corner"), ("START", "END"), ("corner", "corner"), ("corner", "END")}

KAPPA_SCALE = 5.0        # κ·R features go through asinh(κR / this) before scaling
MAX_KAPPA_R = 2000.0     # |κ|·R beyond this (radius < R/2000) = a degenerate fit
MAX_POS_ERR = 1.0        # fit quality: rms_position_error ≤ this · σ
SHORT_SIGMAS = 10.0      # strokes shorter than this many σ get a stroke-level σ
CTX_W = 0.5              # weight of the stroke-length context in k-NN (logl-std units)
KNN = 16                 # neighbours considered when resampling a transition
JITTER_LEN = 0.08        # log-normal sd of the length jitter
JITTER_K = 0.05          # κ jitter, as a fraction of the pool's κ·R spread
JITTER_ANGLE = 0.05      # corner angle jitter (rad)
MAX_TOKENS = 80


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------

def _tok_seg(kind, l, k0, k1):
    return [kind, float(l), float(k0), float(k1)]


def _tok_corner(a):
    return ["corner", float(a)]


def fit_tokens(fit, R: float) -> list[list]:
    """A Fit (px) as a dimensionless token list: segments [kind, l, k0, k1]
    and corners ["corner", angle]. Closed fits are read as open from their
    first segment (closure is not modelled)."""
    out: list[list] = []
    for i, (run, turn) in enumerate(_runs(fit)):
        if i > 0:
            out.append(_tok_corner(turn))
        for g in run:
            if g.length <= 0:
                continue
            out.append(_tok_seg(g.kind, g.length / R, g.k0 * R, g.k1 * R))
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


def _feat(tok, scale) -> np.ndarray:
    """Conditioning feature of a token, scaled (segment: log l, asinh κ0,
    asinh κ1; corner: angle)."""
    if tok[0] == "corner":
        return np.array([tok[1] / scale["angle"]])
    l, k0, k1 = tok[1], tok[2], tok[3]
    return np.array([np.log(max(l, 1e-9)) / scale["logl"],
                     np.arcsinh(k0 / KAPPA_SCALE) / scale["ak"],
                     np.arcsinh(k1 / KAPPA_SCALE) / scale["ak"]])


def _stroke_len(toks) -> float:
    return float(sum(t[1] for t in toks if t[0] != "corner"))


# ---------------------------------------------------------------------------
# the grammar
# ---------------------------------------------------------------------------

@dataclass
class Grammar:
    """A learned hand. All fields JSON-native (lists, dicts, floats).

    counts: raw transition counts, rows FROM, columns TO (reversal-augmented).
    pairs: "prev>next" → {"prev": [params...], "next": [params...]};
        segment params [l, k0, k1] (dimensionless), corner params [angle],
        START prev params [stroke length] (so a first segment can be drawn
        conditioned on how long the stroke will be).
    strokes: training strokes as token lists (originals, not reversed).
    stroke_lengths: Σ segment length / R per training stroke.
    strokes_per_drawing: usable strokes per training drawing;
        ink_per_drawing: their summed length / R per drawing.
    start_pos: stroke start points normalised to the drawing's stroke bbox
        ([0,1]²); start_heading: initial tangent angles (rad).
    scale: feature scaling (see `_feat`), spread: per-kind κ·R spread used
        for jitter.
    """
    name: str = ""
    alpha: float = 0.5
    counts: list = field(default_factory=list)
    pairs: dict = field(default_factory=dict)
    strokes: list = field(default_factory=list)
    stroke_lengths: list = field(default_factory=list)
    strokes_per_drawing: list = field(default_factory=list)
    ink_per_drawing: list = field(default_factory=list)
    start_pos: list = field(default_factory=list)
    start_heading: list = field(default_factory=list)
    scale: dict = field(default_factory=dict)
    spread: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    # -- derived (cached, not serialised) --
    def __post_init__(self):
        self._cache: dict = {}

    def transition(self) -> np.ndarray:
        """Row-stochastic matrix (FROM × TO) with additive smoothing `alpha`
        on allowed transitions; forbidden ones stay exactly 0."""
        C = np.asarray(self.counts, dtype=float)
        if C.size == 0:
            C = np.zeros((len(FROM), len(TO)))
        A = np.array([[0.0 if (f, t) in _FORBIDDEN else 1.0 for t in TO] for f in FROM])
        P = (C + self.alpha) * A
        return P / P.sum(axis=1, keepdims=True)

    def _pool(self, key):
        """(prev_feats (n,d) or None, next params list, stroke-length context
        feature (n,) or None) for a transition."""
        if key not in self._cache:
            d = self.pairs.get(key)
            if not d or not d["next"]:
                self._cache[key] = None
            else:
                pk = key.split(">")[0]
                if pk == "START":          # conditioned on the stroke's total length
                    F = (np.array([[np.log(max(p[0], 1e-9)) / self.scale["logl"]]
                                   for p in d["prev"]]) if d["prev"] and d["prev"][0] else None)
                else:
                    F = np.array([_feat([pk] + list(p), self.scale) for p in d["prev"]])
                C = (np.log(np.maximum(np.asarray(d["ctx"], dtype=float), 1e-9)) / self.scale["logl"]
                     if d.get("ctx") else None)
                self._cache[key] = (F, d["next"], C)
        return self._cache[key]

    def _kind_pool(self, kind):
        """All segments (or corners) of one kind: (feats, params)."""
        key = ("kind", kind)
        if key not in self._cache:
            P = []
            for toks in self.strokes:
                for t in toks:
                    if t[0] == kind:
                        P.append(list(t[1:]))
            if not P:
                self._cache[key] = None
            else:
                F = np.array([_feat([kind] + p, self.scale) for p in P])
                self._cache[key] = (F, P)
        return self._cache[key]

    def segment_counts(self) -> dict:
        c = {k: 0 for k in SEG_KINDS + ("corner",)}
        for toks in self.strokes:
            for t in toks:
                c[t[0]] += 1
        return c

    _FIELDS = ("name", "alpha", "counts", "pairs", "strokes", "stroke_lengths",
               "strokes_per_drawing", "ink_per_drawing", "start_pos", "start_heading",
               "scale", "spread", "meta")

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


def _stroke_width(st: Stroke, drawing: Drawing) -> float:
    if st.width is not None and len(st.width):
        return float(np.median(st.width))
    return float(drawing.meta.get("line_width_px", 0.0) or 0.0)


def fit_drawing(drawing: Drawing, *, sigma_frac: float = 0.01, min_len_w: float = 8.0):
    """Fit every usable stroke of a drawing. Returns (R, [(stroke, fit, tokens)]).

    Usable: length ≥ min_len_w · line width (stroke.width median, else the
    drawing's meta line_width_px, else no width floor) and ≥ 2·σ_eff; fit
    finite, rms_position_error ≤ MAX_POS_ERR·σ_eff, |κ| ≤ 1/width (and
    |κ|·R ≤ MAX_KAPPA_R), every segment turning ≤ 2π, every corner ≤ π.
    """
    R = drawing.ref_length()
    sigma = sigma_frac * R
    out = []
    for st in drawing.strokes:
        if len(st) < 3:
            continue
        L = st.length()
        w = _stroke_width(st, drawing)
        if L < min_len_w * w:
            continue
        sg = sigma if L >= SHORT_SIGMAS * sigma else max(L / SHORT_SIGMAS, 0.5 * w, 0.002 * R)
        if L < 2 * sg:
            continue
        try:
            f = fit_stroke(st.points, sigma=sg, closed=st.closed)
        except Exception:  # noqa: BLE001 — a fit failure just drops the stroke
            continue
        if not np.isfinite(f.rms_position_error) or f.rms_position_error > MAX_POS_ERR * sg:
            continue
        toks = fit_tokens(f, R)
        segs = [t for t in toks if t[0] != "corner"]
        if not segs:
            continue
        vals = np.array([v for t in toks for v in t[1:]])
        if not np.all(np.isfinite(vals)):
            continue
        # physical plausibility: radius ≥ one line width, no segment turning
        # more than a full circle, no corner beyond a hairpin (scan blobs and
        # wash outlines produce tight fitted spirals otherwise)
        kmax = MAX_KAPPA_R if w <= 0 else min(MAX_KAPPA_R, R / w)
        if max(max(abs(t[2]), abs(t[3])) for t in segs) > kmax:
            continue
        if any(abs(0.5 * (t[2] + t[3]) * t[1]) > 2 * np.pi for t in segs):
            continue
        if any(t[0] == "corner" and abs(t[1]) > np.pi for t in toks):
            continue
        out.append((st, f, toks))
    return R, out


def learn(drawings: list[Drawing], *, sigma_frac: float = 0.01, min_len_w: float = 8.0,
          alpha: float = 0.5, name: str = "", max_keep: int = 4000,
          seed: int = 0) -> Grammar:
    """Learn a Grammar from drawings (module docstring). `max_keep` caps the
    stroke-level lists stored for composition (subsampled with `seed`);
    pools and training strokes are kept whole."""
    rng = np.random.default_rng(seed)
    fi, ti = {k: i for i, k in enumerate(FROM)}, {k: i for i, k in enumerate(TO)}
    counts = np.zeros((len(FROM), len(TO)), dtype=int)
    pairs: dict[str, dict] = {}
    strokes, lengths, per_drawing, ink, spos, shead = [], [], [], [], [], []
    n_fit = n_short = 0
    for d in drawings:
        R, fitted = fit_drawing(d, sigma_frac=sigma_frac, min_len_w=min_len_w)
        per_drawing.append(len(fitted))
        ink.append(round(float(sum(_stroke_len(t) for _s, _f, t in fitted)), 6))
        if not fitted:
            continue
        allp = np.vstack([s.points for s in d.strokes if len(s)])
        lo, span = allp.min(axis=0), np.maximum(np.ptp(allp, axis=0), 1e-9)
        for st, f, toks in fitted:
            n_fit += 1
            n_short += int(f.sigma < sigma_frac * R * 0.999)
            strokes.append(toks)
            lengths.append(_stroke_len(toks))
            p = st.points
            spos.append([float(v) for v in ((p[0] - lo) / span).round(4)])
            k = min(len(p) - 1, max(2, len(p) // 20))
            dv = p[k] - p[0]
            shead.append(float(np.arctan2(dv[1], dv[0])))
            for seq in (toks, reverse_tokens(toks)):
                prev = ["START", lengths[-1]]
                for t in seq + [["END"]]:
                    counts[fi[prev[0]], ti[t[0]]] += 1
                    key = f"{prev[0]}>{t[0]}"
                    if t[0] != "END":
                        dd = pairs.setdefault(key, {"prev": [], "next": [], "ctx": []})
                        dd["ctx"].append(round(lengths[-1], 7))
                        dd["prev"].append([round(v, 7) for v in prev[1:]])
                        dd["next"].append([round(v, 7) for v in t[1:]])
                    prev = t
    # feature scaling and jitter spreads
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

    def cap(xs):
        if len(xs) <= max_keep:
            return xs
        idx = np.sort(rng.choice(len(xs), max_keep, replace=False))
        return [xs[i] for i in idx]

    return Grammar(
        name=name, alpha=float(alpha), counts=counts.tolist(), pairs=pairs,
        strokes=strokes, stroke_lengths=[round(x, 6) for x in lengths],
        strokes_per_drawing=per_drawing, ink_per_drawing=ink, start_pos=cap(spos),
        start_heading=[round(x, 4) for x in cap(shead)], scale=scale, spread=spread,
        meta={"sigma_frac": sigma_frac, "min_len_w": min_len_w, "n_drawings": len(drawings),
              "n_strokes": n_fit, "short_sigma": n_short,
              "sources": [d.source for d in drawings][:200]})


# ---------------------------------------------------------------------------
# sampling
# ---------------------------------------------------------------------------

def _sample_kind(g: Grammar, prev_kind: str, rng, forbid_end=False, force_end=False) -> str:
    if force_end and prev_kind != "corner":
        return "END"
    if "P" not in g._cache:
        P = g.transition()
        for i, k in enumerate(TO[:-1]):    # a hand never produces a token it never used
            if g._kind_pool(k) is None:
                P[:, i] = 0.0
        g._cache["P"] = P
    p = g._cache["P"][FROM.index(prev_kind)].copy()
    if forbid_end:
        p[TO.index("END")] = 0.0
    if force_end:                      # after a corner: a segment must follow
        p[TO.index("corner")] = 0.0
    if p.sum() <= 0:
        return "END"
    return TO[int(rng.choice(len(TO), p=p / p.sum()))]


def _sample_start(g: Grammar, length: float, rng) -> tuple[str, list[float]]:
    """First segment of a stroke that will be `length` long: k-NN over the
    START pairs of every kind by log stroke length (kind and params jointly)."""
    cand = []
    for kind in SEG_KINDS:
        pool = g._pool(f"START>{kind}")
        if pool is None or pool[0] is None:
            continue
        d = (pool[0][:, 0] - np.log(max(length, 1e-9)) / g.scale["logl"]) ** 2
        cand += [(float(v), kind, i) for i, v in enumerate(d)]
    if not cand:
        kind = _sample_kind(g, "START", rng)
        return kind, _sample_params(g, ["START"], kind, rng)
    dist = np.array([c[0] for c in cand])
    k = min(KNN, len(dist))
    near = np.argpartition(dist, k - 1)[:k]
    _d, kind, i = cand[int(near[int(rng.integers(k))])]
    return kind, _jitter(g, kind, list(g._pool(f"START>{kind}")[1][i]), rng)


def _sample_params(g: Grammar, prev: list, kind: str, rng, ctx: float | None = None) -> list[float]:
    """Next token params given the previous token (k-NN resampling; the
    START row is drawn unconditionally here — see `_sample_start`)."""
    pool = g._pool(f"{prev[0]}>{kind}")
    if pool is None:                   # unseen transition: unconditional draw
        kp = g._kind_pool(kind)
        if kp is None:
            return [0.0] if kind == "corner" else [0.01, 0.0, 0.0]
        return list(kp[1][int(rng.integers(len(kp[1])))])
    F, nxt, C = pool
    if F is None or prev[0] == "START":
        j = int(rng.integers(len(nxt)))
    else:
        f = _feat(prev, g.scale)
        d = np.sum((F - f) ** 2, axis=1)
        if C is not None and ctx is not None:   # stroke-length context
            d = d + (CTX_W * (C - np.log(max(ctx, 1e-9)) / g.scale["logl"])) ** 2
        k = min(KNN, len(d))
        near = np.argpartition(d, k - 1)[:k]
        j = int(near[int(rng.integers(k))])
    return _jitter(g, kind, list(nxt[j]), rng)


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


def _continuity(prev: list | None, tok: list) -> tuple[list | None, list]:
    """Enforce κ continuity at a non-corner joint. Returns (prev, tok), both
    possibly modified copies (relabelled if their kind can no longer hold)."""
    if prev is None or prev[0] in ("corner", "START") or tok[0] == "corner":
        return prev, tok
    kj = prev[3]
    kind, l, k0, k1 = tok
    if kind == "arc":
        if abs(kj) < 1e-9:             # an arc cannot touch a line: ease in
            return prev, _tok_seg("clothoid", l, 0.0, k1)
        # the arc takes the joint κ but keeps its sampled turning (no curls)
        r = float(np.clip(abs(k0) / abs(kj), 0.25, 4.0)) if abs(k0) > 1e-12 else 1.0
        return prev, _tok_seg("arc", l * r, kj, kj)
    if kind == "line":
        if abs(kj) < 1e-9:
            return prev, tok
        if prev[0] == "clothoid":      # pull the clothoid's end to zero
            pk = "line" if abs(prev[2]) < 1e-9 else "clothoid"
            return _tok_seg(pk, prev[1], prev[2], 0.0), tok
        return prev, _tok_seg("clothoid", l, kj, 0.0)
    # clothoid
    return prev, _tok_seg("clothoid", l, kj, k1)


def generate_tokens(gA: Grammar, rng, *, gB: Grammar | None = None, switch_at: float | None = None,
                    length: float | None = None, max_len: float | None = None) -> tuple[list, int]:
    """Run the chain. Every draw is conditioned on a stroke-length context:
    `length` if given (END suppressed before it, the last segment cut at it
    unless that leaves < 30 % of it — then it is dropped),
    else a length drawn from the training strokes (END free). With gB and switch_at, tokens after
    switch_at·length come from gB's chain (conditioned on A's last token).
    Returns (tokens, index of the first B token or len(tokens))."""
    if max_len is None:
        ml = max(gA.stroke_lengths or [1.0])
        if gB is not None:
            ml = max(ml, max(gB.stroke_lengths or [1.0]))
        max_len = 1.2 * ml if length is None else 1.5 * length
    ctx = length if length is not None else float(
        gA.stroke_lengths[int(rng.integers(len(gA.stroke_lengths)))]) if gA.stroke_lengths else 0.05
    toks: list[list] = []
    prev: list = ["START"]
    s = 0.0
    switch_idx = None
    g = gA
    while len(toks) < MAX_TOKENS:
        if gB is not None and switch_idx is None and s >= switch_at * length:
            g, switch_idx = gB, len(toks)
        forbid = length is not None and s < length
        if prev[0] == "START":
            kind, p = _sample_start(g, ctx, rng)
        else:
            kind = _sample_kind(g, prev[0], rng, forbid_end=forbid, force_end=s >= max_len)
            if kind == "END":
                break
            p = _sample_params(g, prev, kind, rng, ctx)
        tok = _tok_corner(p[0]) if kind == "corner" else _tok_seg(kind, *p)
        newprev, tok = _continuity(prev, tok)
        if toks and newprev is not prev:
            toks[-1] = newprev
        if length is not None and tok[0] != "corner" and s + tok[1] >= length:
            frac = max(length - s, 1e-9) / tok[1]      # end at the target ...
            if frac >= 0.3 or not toks:                 # ... but never on a sliver
                k1 = tok[2] + (tok[3] - tok[2]) * frac
                toks.append(_tok_seg(tok[0], tok[1] * frac, tok[2], k1))
            break
        toks.append(tok)
        if tok[0] != "corner":
            s += tok[1]
        prev = tok
    while toks and toks[-1][0] == "corner":
        toks.pop()
    return toks, (switch_idx if switch_idx is not None else len(toks))


def tokens_to_points(toks: list, R: float, *, start=(0.0, 0.0), heading: float = 0.0,
                     step: float = 0.5) -> tuple[np.ndarray, list, list]:
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
        # κ is continuous inside a run: knot i = k1 of segment i-1 = k0 of segment i
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


def _stroke(toks, R, start, heading, step, extra=None) -> Stroke:
    pts, segs, corners = tokens_to_points(toks, R, start=start, heading=heading, step=step)
    meta = {"segments": segs, "corners": corners, "tokens": toks, "ref_length": float(R)}
    if extra:
        meta.update(extra)
    return Stroke(pts, meta=meta)


def generate_stroke(grammar: Grammar, rng, *, ref_length: float, start=(0.0, 0.0),
                    heading: float = 0.0, step: float = 0.5,
                    length: float | None = None) -> Stroke:
    """One stroke from the grammar's chain, at drawing scale `ref_length`
    (px). `length` (dimensionless, optional) suppresses END until reached.
    meta: segments (px), corners, tokens (dimensionless), ref_length."""
    toks, _ = generate_tokens(grammar, rng, length=length)
    return _stroke(toks, ref_length, start, heading, step, {"hand": grammar.name})


def _fits_canvas(pts, W, H, margin):
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    return (hi[0] - lo[0] <= W - 2 * margin) and (hi[1] - lo[1] <= H - 2 * margin)


def generate_drawing(grammar: Grammar, rng, size, *, n_strokes: int | None = None,
                     budget: str = "ink", max_strokes: int = 400, ref_frac: float = 0.85, margin: float = 20.0,
                     clearance: float = 6.0, step: float = 0.75, tries: int = 25) -> Drawing:
    """Strokes on a (W, H) px canvas. R = ref_frac·diagonal.

    budget="ink" (default): stroke target lengths are drawn from the
    training strokes with probability ∝ length (what the eye sees is ink,
    not fragment counts) and each stroke is generated length-conditioned;
    strokes are added until the summed length reaches an empirical
    per-drawing ink total. budget="count": n_strokes (or an empirical
    per-drawing count) unconditioned strokes — on fragment-heavy scans this
    is mostly short bits. At most max_strokes either way. Start position/heading from the empirical ones (jittered);
    each stroke is shifted to fit inside the margin and redrawn (up to
    `tries`) if it comes within ~`clearance` px of an earlier one (occupancy
    grid; the last try is kept regardless). Naive
    layout — composition is not modelled."""
    W, H = (int(size), int(size)) if np.isscalar(size) else (int(size[0]), int(size[1]))
    R = ref_frac * float(np.hypot(W, H))
    ink_budget = np.inf
    lengths = np.array(grammar.stroke_lengths or [0.1])
    if budget == "ink" and n_strokes is None:
        c = [x for x in grammar.ink_per_drawing if x > 0] or [float(lengths.sum())]
        ink_budget = float(c[int(rng.integers(len(c)))])
        n_strokes = max_strokes
    elif n_strokes is None:
        c = [x for x in grammar.strokes_per_drawing if x > 0] or [8]
        n_strokes = int(c[int(rng.integers(len(c)))])
    n_strokes = max(1, min(n_strokes, max_strokes))
    wlen = lengths / lengths.sum()
    ink = 0.0
    cell = max(clearance / 2.0, 1.0)            # occupancy grid: cells within clearance
    occ = np.zeros((int(H / cell) + 2, int(W / cell) + 2), dtype=bool)
    rad = int(np.ceil(clearance / cell))
    placed: list[Stroke] = []
    for _ in range(n_strokes):
        if ink >= ink_budget:
            break
        target = float(rng.choice(lengths, p=wlen)) if budget == "ink" else None
        best = None
        for t in range(tries):
            if grammar.start_pos:
                sp = np.array(grammar.start_pos[int(rng.integers(len(grammar.start_pos)))])
                sp = np.clip(sp + rng.normal(0, 0.05, 2), 0, 1)
            else:
                sp = rng.random(2)
            hd = (grammar.start_heading[int(rng.integers(len(grammar.start_heading)))]
                  if grammar.start_heading else rng.uniform(0, 2 * np.pi)) + rng.normal(0, 0.3)
            start = (margin + sp[0] * (W - 2 * margin), margin + sp[1] * (H - 2 * margin))
            st = generate_stroke(grammar, rng, ref_length=R, start=start, heading=hd, step=step,
                                 length=target)
            p = st.points
            if len(p) < 2 or not _fits_canvas(p, W, H, margin):
                continue
            lo, hi = p.min(axis=0), p.max(axis=0)
            shift = np.zeros(2)
            shift -= np.minimum(lo - margin, 0)
            shift -= np.maximum(hi - (np.array([W, H]) - margin), 0)
            if np.any(shift):
                st = Stroke(p + shift, meta=st.meta)
            ij = np.unique(np.floor(st.points[:, ::-1] / cell).astype(int), axis=0)
            if not occ[ij[:, 0], ij[:, 1]].any() or t == tries - 1:
                best = (st, ij)
                break
        if best is not None:
            placed.append(best[0])
            ink += best[0].length() / R
            ij = best[1]
            for di in range(-rad, rad + 1):
                for dj in range(-rad, rad + 1):
                    if di * di + dj * dj <= rad * rad:
                        occ[np.clip(ij[:, 0] + di, 0, occ.shape[0] - 1),
                            np.clip(ij[:, 1] + dj, 0, occ.shape[1] - 1)] = True
    return Drawing(placed, source=f"grammar:{grammar.name}", size=(W, H),
                   meta={"ref_length_gen": R, "hand": grammar.name})


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
    """One stroke: A's chain up to switch_at·length, then B's chain, κ
    continuous across the switch (B's first transition is conditioned on
    A's last token). length (dimensionless) defaults to one of A's longer
    strokes (top quartile). meta["switch_s"] = arc length (px) of the switch."""
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


def translate(fit, gA: Grammar, gB: Grammar, *, ref_length: float, start=(0.0, 0.0),
              heading: float = 0.0, step: float = 0.5) -> Stroke:
    """Re-express a stroke fitted in hand A (a clothoid.Fit, px, at drawing
    scale ref_length) in hand B: every segment → its nearest neighbour of
    the same kind in B's pool, every corner → B's nearest corner angle, in
    a feature space scaled by the mean of A's and B's scales; then κ
    continuity re-imposed. Deterministic."""
    scale = {k: 0.5 * (gA.scale[k] + gB.scale[k]) for k in gA.scale}
    src = fit_tokens(fit, ref_length)
    out: list = []
    for t in src:
        nb = _nearest(gB, t[0], t, scale)
        tok = list(t) if nb is None else ([t[0]] + nb)
        prev = out[-1] if out else None
        newprev, tok = _continuity(prev, tok)
        if out and newprev is not prev:
            out[-1] = newprev
        out.append(tok)
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
    """Keep a path's coarse shape, replace its fine turning with hand g.

    Base: `fit_stroke` at σ_c = coarse_frac·length, re-integrated and
    rigidly aligned onto the input (if that fit is implausible — a corner
    beyond π or position error > σ_c — the input smoothed at σ_c). Residual: a stroke of the same
    dimensionless length from g's chain; its tangent angle θ(s) high-passed
    at σ_d = detail_frac·R (θ − G_σd*θ, corners included as steps) and
    added (× amount) to the base's θ(s). The hand thus contributes only its
    turning below ~σ_d; at larger scales the base path rules. Positions integrate the new θ; a linear rubber-band
    correction pins both end points to the input's. ref_length (px) sets the
    hand's scale; default: the path's bounding-box diagonal / 0.4."""
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
        # align the base onto the input by arc-length correspondence
        n = min(len(base), len(rin))
        u_b = np.linspace(0, len(base) - 1, n).astype(int)
        u_i = np.linspace(0, len(rin) - 1, n).astype(int)
        base = _kabsch(base[u_b], rin[u_i])(base)
    else:   # implausible fit (e.g. runaway corner angles): the smoothed path
        base = smooth(rin, sc, step)
    base = resample(base, step)
    T = float(np.sum(np.linalg.norm(np.diff(base, axis=0), axis=1)))
    db = np.diff(base, axis=0)
    th_b = np.unwrap(np.arctan2(db[:, 1], db[:, 0]))
    # residual from the hand
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
                             "base": "fit" if ok else "smoothed",
                             "detail_sigma": sd * step,
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
    L = _stroke_len(toks)
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
    """Min Euclidean distance from each row of Q to rows of T, also against
    T's reversed strokes (θ(1-u), mean removed; same length)."""
    Trev = T.copy()
    # reversing traversal maps θ(u) → θ(1-u) + π; after mean removal that is
    # the same values in reverse order
    Trev[:, :-1] = T[:, -2::-1]
    TT = np.vstack([T, Trev])
    out = np.empty(len(Q))
    tn = np.einsum("ij,ij->i", TT, TT)
    for i in range(0, len(Q), chunk):
        q = Q[i:i + chunk]
        d2 = np.einsum("ij,ij->i", q, q)[:, None] + tn[None, :] - 2 * q @ TT.T
        out[i:i + chunk] = np.sqrt(np.maximum(d2.min(axis=1), 0))
    return out


def nearest_training_distance(generated_strokes, grammar: Grammar) -> np.ndarray:
    """For each stroke (a Stroke with meta["tokens"], or a token list),
    the minimum turning-signature distance (`turning_signature`, either
    direction) to the grammar's training strokes. Small = near-copy."""
    toks = [s.meta["tokens"] if isinstance(s, Stroke) else s for s in generated_strokes]
    Q = _sig_matrix(toks)
    T = _sig_matrix(grammar.strokes)
    if len(Q) == 0 or len(T) == 0:
        return np.zeros(0)
    return _min_dist(Q, T)
