# FROZEN COPY of gesture/grammar.py at commit 6e744ae (grammar v6), for research
# modules that must not break while grammar.py is being rewritten. Do not edit.
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

**v4 (results/grammar-v4.md).** The excess corners of generated lines were
traced to k-NN splicing and to steering, not to how corners are
represented. Two remedies are now the defaults:

1. **Source-stroke runs.** With probability `P_FOLLOW`, a draw takes the actual
   next token of the training stroke that the previous token came from. At most
   `MAX_RUN` follows happen in a row, so runs are ≤ 2 tokens; longer runs quote
   (memorisation check).
2. **"typical" steering.** When the chain's first proposal is blocked, the
   feasible proposal whose turning is closest to it is taken.

`round_corners` and `corner_round_w` exist for the ablation, default off.

**v5 (results/grammar-v5.md): joins and corners.** The relations layer takes
its targets from `topology.relation_graph` of the real long subsets
(`topology_summary` per drawing, pooled by `pool_topology` into
``relations["topo"]``): end types (T / L / near / free), join deflection,
near-end gap, T position and angle, kisses, parallel runs. Each new line
gets a **start relation** and an **end plan** sampled from those shares:

- L (join) starts at a free end **turned by a learned deflection** (real
  joins are corners, ~1.2 rad; v3/v4's smooth "continue" is gone);
- near starts at a learned gap beside a line, leaving at a learned aim;
- P (double contour) starts beside a host at a learned offset and is steered
  to keep that offset for a learned overlap (`p_double`);
- an end plan "T" or "near" makes the line **seek** ink near its planned
  length and stop on it (T) or at the learned gap short of it (near);
  "free" prefers an end with no ink within the near distance;
- hands without kisses keep lines clear of the topology's touch distance,
  so passing lines no longer graze (kisses only where the hand has them).

Corners: `corner_budget` (corner-aware steering — a proposal that adds a
panel-scale corner, ≥ 35° within ±2·7 w, beyond the hand's corner rate × the
line's length is avoided when an alternative is feasible), `kmatch`
(κ-matched splices: k-NN draws prefer records whose next token starts at the
current joint curvature) and `look_mult` (longer look-ahead ray).

**v6 (results/grammar-v6.md): lengths and a corner budget.** The corner
excess is already in the free chain (no steering, no relations): its k-NN
splices produce ~1.3–1.6× the real corner tokens per length. Each line now
gets a **plan** first (`plan_line`): length, corner rate and turning rate
taken jointly from one training stroke of the sheet's source drawing; a
`_Budget` re-weights the chain's proposals so corners (whole number, released
evenly along the line) and segment turning track the plan. Lengths are
protected: T/near ends are sought only within (1 ± SEEK_WIN) × the plan (a
line that finds no ink is cut back to its plan), and lines realised shorter
than LEN_KEEP × the plan are regrown with re-seeded starts. Flags:
`lengths="v5"`, `chain_budget=0` restore v5.

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
P_FOLLOW = 0.9           # v4: chance to continue the source stroke of the last token (runs) ...
MAX_RUN = 1              # ... at most this many follows in a row (runs of ≤ 2 tokens), then a splice
CORNER_ROUND_W = 0.0     # v4: corners drawn as two clothoids over this many line widths
# drawing
CLEAR_W = 3.0            # lines keep this many widths apart unless they cross/touch
MIN_FRAC = 0.5           # a walked stroke shorter than this × its target is retried
# v5: joins and corners
CORNER_SIGMA_W = 7.0     # panel-scale corner proxy: σ in widths (= medium.SIGMA_MIN_W) ...
CORNER_ANGLE = float(np.deg2rad(35.0))   # ... turning ≥ this within ±2σ is a corner
CORNER_BUDGET = 1.0      # corner-aware steering: allowed corners = this × hand rate × length
KMATCH = 0.0             # κ-matched splices: extra weight on the joint-κ mismatch (ablation: off by default)
LOOK_MULT = 1.0          # look-ahead ray length multiplier
SEEK_FROM = 0.85         # end plans T/near: start seeking ink at this × planned length ...
SEEK_EXT = 0.3           # ... and go on up to (1 + this) × planned length
SEEK_APPROACH = False    # past the planned length: take the candidate approaching ink most (ablation)
KISS_FREE = 0.08         # kisses per ink below this: the hand keeps clear of the touch distance
# v6: lengths and the chain's corner budget
SEEK_WIN = 0.15          # v6 end plans: seek ink only within (1 ± this) × the planned length; a
                         # line that finds none is cut back to its planned length (fails over to free)
LEN_KEEP = 0.75          # v6: a line realised shorter than this × its plan is regrown (re-seeded) ...
LEN_TRIES = 10           # ... up to this many tries, else it is not placed
CHAIN_BUDGET = 1.0       # v6: strength of the chain's corner/turning budget (0 = off; v5 chain)
BUDGET_GC = 2.0          # ... log-weight per corner token over budget
BUDGET_GT = 0.3          # ... log-weight per radian of segment turning over budget (1.0 over-smoothed H/I, memo +)


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


def round_corners(toks: list[list], Lc: float) -> list[list]:
    """Every corner → two clothoids of total length Lc (dimensionless) with
    the same turning, κ continuous from the previous segment's end to the
    next one's start (a leading corner starts from κ = 0)."""
    if Lc <= 0:
        return [list(t) for t in toks]
    out: list[list] = []
    for i, t in enumerate(toks):
        if t[0] != "corner":
            out.append(list(t))
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if nxt is None or nxt[0] == "corner":
            out.append(list(t))
            continue
        kp = out[-1][3] if out and out[-1][0] in SEG_KINDS else 0.0
        kn = nxt[2]
        k = 0.5 * (4.0 * t[1] / Lc - kp - kn)
        out += [_tok_seg("clothoid", Lc / 2, kp, k), _tok_seg("clothoid", Lc / 2, k, kn)]
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
# v5: topology targets and the panel-scale corner proxy
# ---------------------------------------------------------------------------

def _r(xs, nd=5):
    return [round(float(x), nd) for x in xs if x is not None and np.isfinite(x)]


def topology_summary(drawing: Drawing) -> dict:
    """Relation statistics of one long-subset drawing as `topology.relation_graph`
    measures them (the v5 targets), JSON-native. Lengths in R units."""
    from .topology import relation_graph
    t = relation_graph(drawing)
    ends = [e for e in t.ends if e["kind"] != "self"]
    pairs = {(min(p["a"], p["b"]), max(p["a"], p["b"])) for p in t.parallels}
    first = [p for p in t.parallels if p.get("first", True)]
    return {"n": int(t.n), "ink": float(sum(t.lengths)), "w_over_R": float(t.w / t.R) if t.R > 0 else 0.0,
            "kinds": [e["kind"] for e in ends],
            "l_defl": _r(e["defl"] for e in ends if e["kind"] == "L"),
            "near_gap": _r(e["gap"] for e in ends if e["kind"] == "near"),
            "near_aim": _r(e["aim"] for e in ends if e["kind"] == "near"),
            "t_u": _r(e["u"] for e in ends if e["kind"] == "T"),
            "t_angle": _r(e["angle"] for e in ends if e["kind"] == "T"),
            "n_kiss": int(sum(k["kind"] == "kiss" for k in t.kisses)),
            "n_cross": len(t.crosses),
            "par_pairs": len(pairs), "par_ink": float(t.par_ink),
            "par_offset": _r(p["offset"] for p in first), "par_length": _r(p["length"] for p in first)}


def pool_topology(summaries: list[dict], *, max_keep: int = 3000, seed: int = 0) -> dict:
    """Pool `topology_summary` outputs of one hand into generation targets:
    end-type shares, samples of join deflection, near gap/aim, T u/angle,
    parallel offset/overlap, and per-drawing medians of kisses per ink,
    parallel pairs per stroke and parallel ink share."""
    rng = np.random.default_rng(seed)
    S = [s for s in summaries if s and s.get("n", 0) >= 2]
    if not S:
        return {}
    kinds = [k for s in S for k in s["kinds"]]

    def pool(key):
        v = [x for s in S for x in s.get(key, [])]
        if len(v) > max_keep:
            v = list(rng.choice(v, max_keep, replace=False))
        return _r(v)

    return {"end_p": {k: kinds.count(k) / max(len(kinds), 1) for k in ("T", "L", "near", "free")},
            "l_defl": pool("l_defl"), "near_gap": pool("near_gap"), "near_aim": pool("near_aim"),
            "t_u": pool("t_u"), "t_angle": pool("t_angle"),
            "par_offset": pool("par_offset"), "par_length": pool("par_length"),
            "kiss_per_ink": float(np.median([s["n_kiss"] / max(s["ink"], 1e-9) for s in S])),
            "par_pairs_per_stroke": float(np.median([s["par_pairs"] / s["n"] for s in S])),
            "par_ink": float(np.median([s["par_ink"] for s in S])),
            "x_per_ink": float(np.median([s["n_cross"] / max(s["ink"], 1e-9) for s in S])),
            "n_drawings": len(S)}


def _corner_peaks(theta: np.ndarray, h: int, angle: float = CORNER_ANGLE) -> np.ndarray:
    """Indices of panel-scale corners in a heading sequence: |θ(i+h) − θ(i−h)|
    ≥ angle, local maxima at least 1.5 h apart (cf. clothoid._detect_corners)."""
    n = len(theta)
    if n < 2 * h + 1:
        return np.zeros(0, int)
    T = np.abs(theta[2 * h:] - theta[:-2 * h])
    idx = np.flatnonzero(T >= angle)
    out = []
    for i in idx[np.argsort(-T[idx])]:
        if all(abs(i - j) >= 1.5 * h for j in out):
            out.append(int(i))
    return np.array(sorted(out), int) + h


def corner_rate_proxy(token_strokes: list, w_over_R: float, *, step_w: float = 1.0) -> float:
    """Panel-scale corners per unit length (R) of token strokes drawn at line
    width w_over_R·R (the steering budget's reference: the hand's own rate,
    measured the way `_Grower` measures proposals)."""
    if not token_strokes or w_over_R <= 0:
        return 0.0
    R = 1.0 / w_over_R               # w = 1 px
    h = max(1, int(round(2 * CORNER_SIGMA_W / step_w)))
    n, L = 0, 0.0
    for toks in token_strokes:
        p, _, _ = tokens_to_points(toks, R, step=step_w)
        if len(p) < 3:
            continue
        th = np.unwrap(np.arctan2(*np.diff(p, axis=0).T[::-1]))
        n += len(_corner_peaks(th, h))
        L += stroke_length(toks)
    return float(n / L) if L > 0 else 0.0


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
                                    [T["nx"][i] for i in idx], [T["par"][i] for i in idx],
                                    np.array(idx))
        return self._cache[key]

    def _kind_pool(self, kind):
        key = ("kind", kind)
        if key not in self._cache:
            P = [list(t[1:]) for toks in self.strokes for t in toks if t[0] == kind]
            self._cache[key] = None if not P else (
                np.array([_feat([kind] + p, self.scale) for p in P]), P)
        return self._cache[key]

    def _next_k0(self, p1kind):
        """Per pool record: asinh-scaled starting κ of the next token (NaN for corners)."""
        key = ("nk0", p1kind)
        if key not in self._cache:
            pool = self._pool(p1kind)
            if pool is None:
                self._cache[key] = None
            else:
                self._cache[key] = np.array([np.arcsinh(p[1] / KAPPA_SCALE) / self.scale["ak"]
                                             if k != "corner" else np.nan for k, p in zip(pool[2], pool[3])])
        return self._cache[key]

    def draw(self, p2, p1, s: float, length: float, rng, prev_rec: int | None = None,
             p_follow: float = 0.0, kmatch: float = 0.0, knn: int = KNN,
             weights=None) -> tuple[str, list[float], int]:
        """Next token (kind, params, record index) given the previous two
        tokens, arc length so far s and the stroke's target length (both R
        units). p_follow (v4): with this probability, if the previous token
        came from training record prev_rec and its source stroke goes on,
        take that stroke's actual next token (a run of the training stroke,
        not a k-NN splice). kmatch (v5): extra squared-distance weight on the
        mismatch between the current joint κ (p1's end) and the next token's
        starting κ — a κ-matched splice."""
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
        if kmatch > 0 and p1[0] in SEG_KINDS:
            nk0 = self._next_k0(p1[0])
            if nk0 is not None and len(nk0) == len(d):
                d = d + kmatch * np.nan_to_num((nk0 - q[2]) ** 2, nan=0.0)
        k = min(knn, len(d))
        near = np.argpartition(d, k - 1)[:k]
        if weights is not None:          # v6: per-record re-weighting (corner budget)
            w = np.asarray(weights([NX[i] for i in near], [PAR[i] for i in near]), float)
            if w.max() < 0.2 and len(d) > k:     # every neighbour over budget: widen the pool once
                k2 = min(4 * k, len(d))
                near = np.argpartition(d, k2 - 1)[:k2]
                w = np.asarray(weights([NX[i] for i in near], [PAR[i] for i in near]), float)
                k = k2
            j = int(near[int(rng.choice(k, p=w / w.sum()))]) if w.sum() > 0 else int(near[int(rng.integers(k))])
        else:
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


def jitter_tokens(g: Grammar, toks: list, rng) -> list:
    """A token list with generation's jitter applied (the quoting floor of
    the memorisation check: what copying a training stroke looks like)."""
    return [_tok_corner(*_jitter(g, "corner", [t[1]], rng)) if t[0] == "corner"
            else _tok_seg(t[0], *_jitter(g, t[0], list(t[1:]), rng)) for t in toks]


def learn(drawings: list[Drawing] | None = None, *, prepared: list[dict] | None = None,
          name: str = "", sigma_w: float = SIGMA_W, shuffle: bool = False, seed: int = 0,
          max_keep: int = 4000, topo: list[dict] | None = None, **sel) -> Grammar:
    """Learn a Grammar from drawings (or from `prepare_drawing` outputs).
    shuffle=True: control grammar trained on segment-shuffled strokes.
    topo (v5): per-drawing `topology_summary` outputs (computed here from the
    drawings' long subsets when drawings are given and topo is None); pooled
    into relations["topo"], the relations layer's targets."""
    rng = np.random.default_rng(seed)
    if topo is None and drawings:
        topo = [topology_summary(long_drawing(d, **sel)) for d in drawings]
    if prepared is None:
        prepared = [prepare_drawing(d, sigma_w=sigma_w, **sel) for d in (drawings or [])]
    fi, ti = {k: i for i, k in enumerate(FROM)}, {k: i for i, k in enumerate(TO)}
    counts = np.zeros((len(FROM), len(TO)), dtype=int)
    T = {k: [] for k in ("p2", "p1", "nx", "f2", "f1", "rem", "u", "par", "sid")}
    strokes, lengths, spos, per = [], [], [], []
    rel = {"n": 0, "n_attached": 0, "u": [], "angle": [], "cross": [], "selfcross": [],
           "cross_per_ink_drawings": [], "gap_free": [], "n_ends": 0, "n_ends_attached": 0}
    for pd in prepared:
        sts = [s["tokens"] for s in pd["strokes"]]
        if shuffle:
            sts = [shuffle_tokens(t, rng) for t in sts]
        per.append({"ink": round(float(sum(stroke_length(t) for t in sts)), 6), "n": len(sts),
                    "w_over_R": pd["w"] / pd["R"] if pd["R"] > 0 else 0.0, "i0": len(strokes)})
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
            for di, seq in enumerate((toks, reverse_tokens(toks))):
                sid = 2 * (len(strokes) - 1) + di
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
                    T["sid"].append(sid)
                    if t[0] != "corner":
                        pos += t[1]
                    p2, p1 = p1, t
        per[-1]["i1"] = len(strokes)        # v6: this drawing's strokes are strokes[i0:i1]
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
    if topo:
        relations_["topo"] = pool_topology(topo, seed=seed)
    wr = [p["w_over_R"] for p in per if p["w_over_R"] > 0]
    if strokes and wr:
        sub = [strokes[i] for i in rng.choice(len(strokes), min(len(strokes), 400), replace=False)]
        relations_["corner_rate"] = corner_rate_proxy(sub, float(np.median(wr)))
    if len(spos) > max_keep:
        spos = [spos[i] for i in np.sort(rng.choice(len(spos), max_keep, replace=False))]
    return Grammar(
        name=name, version=6, trans=T, strokes=strokes, stroke_lengths=lengths, counts=counts.tolist(),
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


def token_budget_stats(toks) -> tuple[float, int, float]:
    """(length, corner tokens, Σ|segment turning| in rad) of a token stroke —
    the per-stroke quantities the v6 chain budget is learned from."""
    L = stroke_length(toks)
    nc = sum(1 for t in toks if t[0] == "corner")
    tt = float(sum(abs(0.5 * (t[2] + t[3]) * t[1]) for t in toks if t[0] != "corner"))
    return L, nc, tt


def _budget_table(g: Grammar):
    """Per training stroke (length, corners/length, turning/length), plus
    per-drawing index ranges (v6 grammars) — cached."""
    key = ("budget",)
    if key not in g._cache:
        st = np.array([token_budget_stats(t) for t in g.strokes]) if g.strokes else np.zeros((0, 3))
        L = np.maximum(st[:, 0], 1e-9) if len(st) else np.zeros(0)
        tab = np.column_stack([st[:, 0], st[:, 1] / L, st[:, 2] / L]) if len(st) else np.zeros((0, 3))
        segt = [abs(0.5 * (t[2] + t[3]) * t[1]) for toks in g.strokes[:2000] for t in toks if t[0] != "corner"]
        g._cache[key] = (tab, float(np.median(segt)) if segt else 0.3)
    return g._cache[key]


def plan_line(g: Grammar, rng, *, length: float | None = None, drawing: int | None = None) -> dict:
    """v6: a line's plan — its length and its corner/turning budget, drawn
    jointly from ONE training stroke (only these three scalars are taken).
    drawing: index into g.drawings (v6 grammars): sample from that drawing's
    strokes, so a sheet keeps one drawing's length scale and texture. With
    `length` given, the budget comes from a stroke of similar length."""
    tab, segt = _budget_table(g)
    if not len(tab):
        return {"length": float(length or 0.1), "rho_c": np.inf, "rho_t": np.inf, "slack_t": segt}
    idx = np.arange(len(tab))
    if drawing is not None and 0 <= drawing < len(g.drawings) and "i1" in g.drawings[drawing]:
        d = g.drawings[drawing]
        if d["i1"] > d["i0"]:
            idx = np.arange(d["i0"], d["i1"])
    if length is None:
        i = int(idx[int(rng.integers(len(idx)))])
        length = float(tab[i, 0])
    else:
        sub = idx[rng.choice(len(idx), min(len(idx), 40), replace=False)]
        dl = np.abs(np.log(np.maximum(tab[sub, 0], 1e-9) / max(length, 1e-9)))
        i = int(sub[int(rng.choice(np.argsort(dl)[:5]))])
    return {"length": float(length), "rho_c": float(tab[i, 1]), "rho_t": float(tab[i, 2]),
            "slack_t": segt, "src": i}


class _Budget:
    """v6 chain budget: re-weights the k-NN proposals so the stroke's
    corner tokens and segment turning track its plan. Corners: the plan's
    rate × the line's length, stochastically rounded to a whole number n,
    released evenly along the line (by arc length x the line may hold
    ceil(n·x/length) corners). Turning: rate × x plus a slack of up to one
    typical segment's turning. A proposal over either allowance is
    down-weighted by exp(−gc·corners over) · exp(−gt·radians over); within
    budget the chain's own propensities are untouched (follows included:
    an over-budget follow is accepted with its weight as probability)."""

    def __init__(self, plan: dict, rng, gain: float = CHAIN_BUDGET, length: float | None = None):
        self.L = max(float(length if length is not None else plan["length"]), 1e-9)
        self.rc, self.rt = plan["rho_c"], plan["rho_t"]
        self.n_c = int(np.floor(self.rc * self.L + rng.random())) if np.isfinite(self.rc) else 10 ** 6
        self.ut = float(rng.random()) * plan.get("slack_t", 0.3)
        self.gc, self.gt = BUDGET_GC * gain, BUDGET_GT * gain
        self.nc, self.tt = 0, 0.0

    def allowed_c(self, x: float) -> int:
        return int(np.ceil(self.n_c * min(max(x, 0.0) / self.L, 1.0) - 1e-9))

    def weights(self, s: float):
        def f(kinds, pars):
            w = np.empty(len(kinds))
            for i, (k, p) in enumerate(zip(kinds, pars)):
                if k == "corner":
                    dc, dt, dl = 1, 0.0, 0.0
                else:
                    dc, dt, dl = 0, abs(0.5 * (p[1] + p[2]) * p[0]), p[0]
                oc = self.nc + dc - max(self.allowed_c(s + dl), self.allowed_c(s + 1e-6) if dc else 0)
                ot = self.tt + dt - (self.rt * (s + dl) + self.ut)
                w[i] = np.exp(-self.gc * max(oc, 0.0) - self.gt * max(ot, 0.0))
            return w
        return f

    def spend(self, toks):
        for t in toks:
            if t[0] == "corner":
                self.nc += 1
            else:
                self.tt += abs(0.5 * (t[2] + t[3]) * t[1])


def generate_tokens(gA: Grammar, rng, *, gB: Grammar | None = None, switch_at: float | None = None,
                    length: float | None = None, context: tuple | None = None,
                    max_tokens: int = MAX_TOKENS, p_follow: float = 0.0,
                    max_run: int = MAX_RUN, kmatch: float = 0.0, continuity: bool = True,
                    knn: int = KNN, budget: float = 0.0, plan: dict | None = None) -> tuple[list, int]:
    """Run the order-2 chain to a target length (dimensionless; default: one
    of A's training lengths). The last segment is cut at the target unless
    that leaves < 30 % of it (then dropped). context = (token before last,
    last token) of a preceding chunk: conditions the first draws and makes
    the joint κ-continuous. With gB and switch_at, draws after
    switch_at·length come from gB. budget > 0 (v6): the chain's proposals are
    re-weighted by a per-stroke corner/turning budget (`plan`, default
    `plan_line(gA, rng, length=length)`) with this gain. Returns (tokens,
    index of first B token or len(tokens))."""
    bud = None
    if budget > 0:
        plan = plan or plan_line(gA, rng, length=length)
        length = plan["length"] if length is None else length
        bud = _Budget(plan, rng, budget, length=length)
    if length is None:
        L = gA.stroke_lengths or [0.1]
        length = float(L[int(rng.integers(len(L)))])
    p2, p1 = (list(context[0]), list(context[1])) if context else (["START"], ["START"])
    toks: list[list] = []
    s, g, switch_idx, draws, rec, run = 0.0, gA, None, 0, None, 0
    while len(toks) < max_tokens and draws < 4 * max_tokens:
        draws += 1
        if gB is not None and switch_idx is None and s >= (switch_at or 0.5) * length:
            g, switch_idx, rec = gB, len(toks), None
        kind, p, rec_ = g.draw(p2, p1, s, length, rng, prev_rec=rec,
                               p_follow=p_follow if run < max_run else 0.0, kmatch=kmatch, knn=knn,
                               weights=bud.weights(s) if bud is not None and g is gA else None)
        run = run + 1 if (rec is not None and rec_ == rec + 1) else 0
        rec = rec_
        tok = _tok_corner(p[0]) if kind == "corner" else _tok_seg(kind, *p)
        if kind == "corner" and (not toks and p1[0] in ("START",)):
            continue
        if kind == "corner" and toks and toks[-1][0] == "corner":
            continue
        newprev, tok = _continuity(p1, tok, lock_prev=not toks) if continuity else (p1, tok)
        if toks and newprev is not p1:
            toks[-1] = newprev
        if tok[0] != "corner" and s + tok[1] >= length:
            frac = max(length - s, 1e-9) / tok[1]
            if frac >= 0.3 or not toks:
                toks.append(_tok_seg(tok[0], tok[1] * frac, tok[2], tok[2] + (tok[3] - tok[2]) * frac))
            break
        toks.append(tok)
        if bud is not None:
            bud.spend([tok])
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
        self.keep: list[np.ndarray] = []      # v5: protected free ends ...
        self.keep_r = 0.0                     # ... no other line comes within this
        self._ktree = None

    def protect(self, pt, r):
        self.keep.append(np.asarray(pt, float))
        self.keep_r = float(r)
        self._ktree = cKDTree(np.array(self.keep))

    def unprotect(self, pt):
        pt = np.asarray(pt, float)
        self.keep = [k for k in self.keep if np.linalg.norm(k - pt) > 1e-9]
        self._ktree = cKDTree(np.array(self.keep)) if self.keep else None

    def dist_keep(self, pts):
        if self._ktree is None:
            return np.full(len(pts), np.inf)
        return self._ktree.query(pts)[0]

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
    integrated from the current pen position, and one is chosen among those
    that stay on the sheet and clear of other ink and of the line's own
    earlier part — preferring those that leave room ahead (end point ≥
    `look` from any obstacle). Crossing candidates join the pool while the
    drawing is under its crossing budget. Nothing is inserted: a needed turn
    can only come from a turning segment (or a corner) the chain itself
    proposed. The line stops at its planned length, or earlier only when
    every candidate is blocked.

    v5: `end_plan` {"kind": "T"|"near"|"free", "gap": px} — from SEEK_FROM ×
    the planned length a candidate that reaches ink (T: within 0.4 × touch;
    near: within the planned gap) is cut there and ends the line; past the
    planned length (up to 1 + SEEK_EXT) the candidate that approaches ink
    most is taken; "free" prefers a last step whose end has no ink within
    `near`. `guide` {"tree", "offset", "length"} (a double contour): for the
    first `length` px the candidate keeping closest to `offset` from the
    guide line is taken. `corner_budget` > 0: a candidate adding panel-scale
    corners beyond budget × the hand's corner rate × the line's length is
    skipped when a within-budget candidate is feasible."""

    def __init__(self, g, rng, sheet: _Sheet, R, step, clr, look, K=8, *, p_follow=0.0,
                 corner_len=0.0, steer="first", max_run=MAX_RUN, kmatch=0.0, corner_budget=0.0,
                 lw=1.0, touch=None, near=None, chain_budget=0.0, seek="v6"):
        self.g, self.rng, self.sheet, self.R, self.step = g, rng, sheet, R, step
        self.clr, self.look, self.K = clr, look, K
        self.p_follow, self.corner_len, self.steer, self.max_run = p_follow, corner_len, steer, max_run
        self.kmatch, self.corner_budget = kmatch, corner_budget
        self.chain_budget, self.seek = chain_budget, seek
        self.bud = None
        self.seek_approach = SEEK_APPROACH
        self.corner_rate = float((g.relations or {}).get("corner_rate", 0.0))
        self.h = max(1, int(round(2 * CORNER_SIGMA_W * lw / step)))
        self.touch = touch if touch is not None else 1.5 * lw
        self.near = near if near is not None else 0.02 * R
        self.join_r = 0.012 * R               # topology HOST_END_R: an end this close to a host end is a join
        self.run = 0
        self.stats = {"steps": 0, "steered": 0, "corners": 0, "corners_proposed_first": 0,
                      "followed": 0, "corner_avoided": 0, "panel_corners": 0, "guided": 0,
                      "plan_T": 0, "plan_near": 0, "plan_free": 0, "end_T": 0, "end_near": 0,
                      "end_free_ok": 0, "end_blocked": 0, "end_full": 0,
                      "past_steps": 0, "past_corners": 0, "start_steps": 0, "start_corners": 0,
                      "seek_failed": 0, "budget_lines": 0}

    def _candidate(self, p2, p1, s, length, rec):
        """(chain tokens, record index of the last one, followed?)."""
        g, rng = self.g, self.rng
        pf = self.p_follow if self.run < self.max_run else 0.0
        wf = self.bud.weights(s) if self.bud is not None else None
        for _ in range(6):
            kind, p, r = g.draw(p2, p1, s, length, rng, prev_rec=rec, p_follow=pf, kmatch=self.kmatch,
                                weights=wf)
            fol = rec is not None and r == rec + 1
            if kind != "corner":
                tok = _tok_seg(kind, *p)
                _pp, tok = _continuity(p1, tok, lock_prev=True)
                return [tok], r, fol
            if p1[0] in ("START", "corner"):
                continue
            c = _tok_corner(p[0])
            kind2, p2_, r2 = g.draw(p1, c, s, length, rng, prev_rec=r, p_follow=pf, kmatch=self.kmatch,
                                    weights=wf)
            if kind2 == "corner":
                continue
            return [c, _tok_seg(kind2, *p2_)], r2, fol
        return None

    def _geometry(self, seq, p1):
        """Tokens actually drawn for a chain proposal: with corner_len > 0 a
        corner becomes two clothoids of total length corner_len (R units)
        carrying the same turning, κ continuous from the previous token's
        end to the next segment's start — a corner as an ink line rounds it
        and as the clothoid fit then measures it."""
        if self.corner_len <= 0 or seq[0][0] != "corner":
            return seq
        return round_corners([p1] + seq, self.corner_len)[1:] if p1[0] in SEG_KINDS else \
            round_corners(seq, self.corner_len)

    def _new_corners(self, tail, P, sg, last_corner_s):
        """Panel-scale corners a candidate adds: peaks of the turning over
        ±2·7 w in (line tail + candidate) beyond the last counted corner.
        Returns (count, arc position px of the last one or None)."""
        C = np.vstack([tail, P])
        if len(C) < 2 * self.h + 2:
            return 0, None
        d = np.diff(C, axis=0)
        th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
        pk = _corner_peaks(th, self.h)
        if not len(pk):
            return 0, None
        m = len(tail)
        s_all = np.concatenate([np.full(m, np.nan), sg])
        # position of a heading sample ≈ arc length of its end point
        sp = np.array([s_all[i + 1] if i + 1 >= m else sg[0] - (m - 1 - i) * self.step for i in pk])
        new = sp > last_corner_s + 1.5 * self.h * self.step
        return int(new.sum()), (float(sp[new][-1]) if new.any() else None)

    def grow(self, start, heading, length, *, context=None, prior=None, s_skip=0.0, host=None,
             self_ok=False, cross_ok=lambda s: False, end_plan=None, guide=None, plan=None):
        """Returns (tokens, status, crosses). prior: points of an earlier part
        of the same line (single mode) — avoided like the line itself.
        status: full | blocked | T | near (v5 end plans). plan (v6): the
        line's `plan_line` — with chain_budget > 0 its corner/turning budget
        re-weights the chain's proposals. seek="v6": T/near ends are sought
        only within (1 ± SEEK_WIN) × length; a line that reaches no ink there
        is cut back to its planned length (the plan fails over to free)."""
        self.bud = _Budget(plan, self.rng, self.chain_budget, length=length) \
            if (plan is not None and self.chain_budget > 0) else None
        self.stats["budget_lines"] += int(self.bud is not None)
        sheet, R, step, clr = self.sheet, self.R, self.step, self.clr
        pos, h = np.asarray(start, float), float(heading)
        p2, p1 = (list(context[0]), list(context[1])) if context else (["START"], ["START"])
        rec = None
        self.run = 0
        toks: list = []
        line = [pos[None, :]]
        line_s = [np.zeros(1)]
        s_tot = 0.0           # px along this line
        s, crosses, status = 0.0, 0, "full"
        lag = 2 * clr
        prior = np.zeros((0, 2)) if prior is None else np.asarray(prior, float)
        st = self.stats
        plan = (end_plan or {}).get("kind")
        if plan:
            st[f"plan_{plan}"] += 1
        seeking = plan in ("T", "near")
        v6 = self.seek == "v6"
        seek_from = (1 - SEEK_WIN) if v6 else SEEK_FROM
        L_max = length * (1 + (SEEK_WIN if v6 else SEEK_EXT)) if seeking else length
        g_arr = None
        if plan == "T":
            g_arr = 0.4 * self.touch
        elif plan == "near":
            g_arr = float(np.clip(end_plan.get("gap", self.near / 2), 1.05 * clr, self.near))
        budget_u = float(self.rng.random())
        n_corn, last_cs = 0, -np.inf
        free_end_ok = None
        while s < L_max - 1e-9 and len(toks) < MAX_TOKENS:
            L = np.vstack(line)
            Ls = np.concatenate(line_s)
            old = np.vstack([prior, L[Ls < s_tot - lag]])
            otree = cKDTree(old) if len(old) else None
            tail = L[-(3 * self.h + 1):]
            pref, ok, selfx, inside_only, arrive = [], [], [], [], []
            first_corner, first_turn = None, None
            past = s >= length - 1e-9
            # past the planned length the chain is asked for a line that goes on
            # (a context of "nothing left" makes it propose corners)
            ctx_len = length if s < length - 1e-9 else s + 0.3 * length
            for _k in range(self.K):
                cand = self._candidate(p2, p1, s, ctx_len, rec)
                if cand is None:
                    continue
                cseq, crec, cfol = cand
                if first_corner is None:
                    first_corner = cseq[0][0] == "corner"
                    first_turn = end_heading(cseq, 0.0)
                seg = cseq[-1]
                last = s + seg[1] >= length - 1e-9
                if s + seg[1] > L_max:                       # end at the (extended) planned length
                    f = max(L_max - s, 1e-9) / seg[1]
                    cseq[-1] = seg = _tok_seg(seg[0], seg[1] * f, seg[2], seg[2] + (seg[3] - seg[2]) * f)
                elif not seeking and s + seg[1] > length:
                    f = max(length - s, 1e-9) / seg[1]
                    cseq[-1] = seg = _tok_seg(seg[0], seg[1] * f, seg[2], seg[2] + (seg[3] - seg[2]) * f)
                seq = self._geometry(cseq, p1)
                P, _, _ = tokens_to_points(seq, R, start=pos, heading=h, step=step)
                P = P[1:]
                if len(P) == 0:
                    continue
                ins = sheet.inside(P)
                sg = s_tot + _arclen(np.vstack([pos, P]))[1:]
                d_o, own = sheet.dist_own(P)
                skip = (sg < s_skip) & (own == (-2 if host is None else host))
                hit_o = (d_o < clr) & ~skip
                if sheet.keep:
                    hit_o = hit_o | (sheet.dist_keep(P) < sheet.keep_r)
                d_s = otree.query(P)[0] if otree is not None else np.full(len(P), np.inf)
                hit_s = d_s < clr
                # v5 end plans: a candidate reaching ink ends the line there
                if g_arr is not None and s + seg[1] >= seek_from * length:
                    reach = (~skip) & (d_o <= g_arr) & (sg >= s_skip + 2 * clr)
                    if v6:                                   # only in the last stretch of the plan
                        reach &= sg >= seek_from * length * R
                    if reach.any():
                        i = int(np.argmax(reach))
                        pre = slice(0, i + 1)
                        bad = (not ins[pre].all()) or (hit_s[pre].any() and not self_ok)
                        if plan == "T":
                            bad = bad or bool(((d_o[:i] < clr) & ~skip[:i] & (own[:i] != own[i])).any())
                            hp_ = sheet.P[sheet._ids.index(int(own[i]))] if int(own[i]) in sheet._ids else None
                            if hp_ is not None and min(np.linalg.norm(hp_[0] - P[i]),
                                                       np.linalg.norm(hp_[-1] - P[i])) < 1.25 * self.join_r:
                                bad = True
                        else:
                            bad = bad or bool(hit_o[:i].any())
                        if not bad:
                            cut = max((sg[i] - s_tot) / R, 1e-9)
                            tseq = truncate_tokens(seq, cut)
                            if tseq and tseq[0][0] != "corner" or len(tseq) > 1:
                                Pt, _, _ = tokens_to_points(tseq, R, start=pos, heading=h, step=step)
                                Pt = Pt[1:]
                                if len(Pt):
                                    sgt = s_tot + _arclen(np.vstack([pos, Pt]))[1:]
                                    arrive.append((tseq, Pt, sgt, 0, cseq, crec, cfol, _k, False))
                if not ins.all():
                    continue
                end_clear = d_o[-1] >= clr and d_s[-1] >= clr
                # look-ahead: a ray of length `look` along the end tangent must
                # stay on the sheet and clear, so the line keeps room to go on
                he = end_heading(seq, h)
                ray = P[-1] + np.outer(np.linspace(self.look / 4, self.look, 4), [np.cos(he), np.sin(he)])
                rd = np.minimum(sheet.dist(ray), otree.query(ray)[0] if otree is not None else np.inf)
                room = self.look if (sheet.inside(ray).all() and (rd >= clr).all()) else 0.0
                over = False
                ncs = (0, None)
                if self.corner_budget > 0:
                    ncs = self._new_corners(tail, P, sg, last_cs)
                    allow = self.corner_budget * self.corner_rate * (s + sum(
                        t[1] for t in seq if t[0] != "corner")) + budget_u
                    over = ncs[0] > 0 and n_corn + ncs[0] > allow
                fr = bool(last and plan == "free" and min(d_o[-1], d_s[-1]) >= self.near)
                item = (seq, P, sg, _bands(hit_o), cseq, crec, cfol, _k, over, ncs, fr, float(np.min(d_o)))
                inside_only.append(item)
                xok = cross_ok(s)
                if not hit_o.any() and not hit_s.any():
                    (pref if room >= self.look else ok).append(item)
                elif not hit_s.any() and end_clear and xok:
                    (pref if room >= self.look else ok).append(item)
                elif hit_s.any() and end_clear and self_ok:
                    selfx.append(item)
            if arrive:
                seq, P, sg, nb, cseq, crec, cfol, kidx, _o = arrive[0]
                st["steps"] += 1
                st["steered"] += int(kidx != 0)
                st["followed"] += int(cfol)
                toks += seq
                line.append(P)
                line_s.append(sg)
                status = plan
                st[f"end_{plan}"] += 1
                break
            cands = pref or ok or selfx
            if guide is not None and s_tot < guide["length"] and (pref or ok):
                gc = pref + ok
                dev = [float(np.mean(np.abs(guide["tree"].query(c[1])[0] - guide["offset"]))) for c in gc]
                pool = [gc[int(np.argmin(dev))]]
                st["guided"] += 1
            elif seeking and past and cands and self.seek_approach:
                pool = [min(cands, key=lambda c: c[11])]    # approach ink
            elif self.steer == "none":                      # ablation: no avoidance at all
                pool = inside_only[:1]
            else:
                if plan == "free" and any(c[10] for c in cands):
                    cands = [c for c in cands if c[10]]
                if self.corner_budget > 0 and cands and cands[0][8]:
                    within = [c for c in cands if not c[8]]
                    if within:
                        st["corner_avoided"] += 1
                        cands = within
                if self.steer == "typical":                 # blocked: the feasible proposal whose
                    if cands and cands[0][7] != 0 and first_turn is not None:   # turning is closest
                        cands = sorted(cands, key=lambda c: abs(end_heading(c[4], 0.0) - first_turn))
                    pool = cands[:1]
                elif self.steer == "plain":                 # blocked chain choice: prefer no corner
                    plain = [c for c in cands if c[4][0][0] != "corner"]
                    pool = cands[:1] if (cands and cands[0][7] == 0) else (plain or cands)[:1]
                else:
                    pool = cands[:1]
            if not pool:
                status = "blocked"
                break
            seq, P, sg, nb, cseq, crec, cfol, kidx, _over, ncs, fr, _dmin = pool[0]
            st["steps"] += 1
            st["steered"] += int(kidx != 0)
            st["corners"] += int(cseq[0][0] == "corner")
            st["corners_proposed_first"] += int(bool(first_corner))
            st["followed"] += int(cfol)
            st["past_steps"] += int(past)
            st["past_corners"] += int(past and cseq[0][0] == "corner")
            st["start_steps"] += int(not toks)
            st["start_corners"] += int(not toks and cseq[0][0] == "corner")
            if ncs[0]:
                n_corn += ncs[0]
                last_cs = ncs[1]
                st["panel_corners"] += ncs[0]
            free_end_ok = fr
            self.run = self.run + 1 if cfol else 0
            crosses += nb
            if self.bud is not None:
                self.bud.spend(cseq)
            toks += seq
            line.append(P)
            line_s.append(sg)
            s_tot = float(sg[-1])
            pos, h = P[-1], end_heading(seq, h)
            s += sum(t[1] for t in seq if t[0] != "corner")
            rec = crec
            p2, p1 = (cseq[-2] if len(cseq) > 1 else p1), cseq[-1]
        if status == "full" and seeking and v6 and stroke_length(toks) > length:
            toks = truncate_tokens(toks, length)       # no ink found: end where the plan said
            st["seek_failed"] += 1
        if status == "full":
            st["end_full"] += 1
            st["end_free_ok"] += int(bool(free_end_ok))
        elif status == "blocked":
            st["end_blocked"] += 1
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
                     cross_gain: float | None = None, K: int = 8, p_follow: float = P_FOLLOW,
                     corner_round_w: float = CORNER_ROUND_W, steer: str = "typical",
                     max_run: int = MAX_RUN, ends: str = "topo", join: str = "sharp",
                     kmatch: float = KMATCH, corner_budget: float = CORNER_BUDGET,
                     look_mult: float = LOOK_MULT, p_double: float | None = None,
                     kiss_clear: bool = True, lengths: str = "v6",
                     chain_budget: float = CHAIN_BUDGET) -> Drawing:
    """A drawing on a (W, H) px canvas, R = ref_frac × the diagonal inside
    the margin (≈ the ink's own bounding-box diagonal).

    mode="contiguous" (default): long lines until the ink budget (R units;
    default: one of the training drawings' long-stroke ink) or n_strokes.
    Every line has a planned length drawn from the long-stroke distribution
    and is grown with `_Grower` (look-ahead steering by choosing among the
    chain's own proposals; lines shorter than the shortest training stroke
    are retried, then dropped).

    relations="learned", ends="topo" (v5 default; needs relations["topo"],
    else falls back to ends="v4"): each line's start relation is drawn from
    the hand's topology — L (a join at a free end, turned by a learned
    deflection; join="smooth" restores v4's tangent ± N(0, 0.25)), P (a
    double contour beside a host, probability `p_double`, default
    relations["p_double"] or 0), T (branch from a host interior at a learned
    u and angle; `p_branch` overrides its probability), near (at a learned
    gap beside a line, leaving at a learned aim) or free (the emptiest of 8
    candidate points) — and its end plan (T / near / free) likewise; see
    `_Grower`. Hands without kisses (relations["topo"]["kiss_per_ink"] <
    KISS_FREE) keep lines 1.1 × the topology touch distance apart
    (kiss_clear). ends="v4": v4's starts (continue / branch / free at a
    learned gap), no end plans.
    relations="tree": `roots` free lines (default 1–3), every later one
    attaches (join or branch). Crossings: candidates that cross other ink
    are allowed while the drawing's crossings stay under cross_gain × the
    learned median crossings per unit ink; self-crossing lines are drawn
    with the learned share.
    Corners (v5): corner_budget, kmatch, look_mult — see the module docstring.
    v6: lengths="v6" (default) plans each line first — length AND corner /
    turning budget jointly from one stroke of ONE training drawing (the one
    whose ink budget the sheet takes), seeks T/near ends only within
    (1 ± SEEK_WIN) × the plan, regrows lines realised < LEN_KEEP × the plan
    (up to LEN_TRIES re-seeded tries, else the line is not placed);
    lengths="v5" restores v5's pooled lengths, seeking and acceptance.
    chain_budget (gain, 0 = off): the plan's budget re-weights the chain.
    mode="single": one line of that ink, grown chunk by chunk (each chunk a
    training-length "virtual stroke" conditioned on the previous two tokens,
    κ-continuous across chunks); `hands` = (gA, gB, ...) alternates hands
    every `switch_every` × a training stroke length of ink (meta["spans"]).
    Line width (px, in every stroke's width and meta) defaults to the
    training drawings' width/R × R."""
    from .topology import NEAR_R, TOUCH_R, TOUCH_W
    W, H = (int(size), int(size)) if np.isscalar(size) else (int(size[0]), int(size[1]))
    # R ≈ the bounding-box diagonal the ink will have (it fills the margin box),
    # so that lengths/R measured on the result match the learned ones
    R = ref_frac * float(np.hypot(W - 2 * margin, H - 2 * margin))
    if line_width is None:
        wr = [d["w_over_R"] for d in grammar.drawings if d.get("w_over_R")]
        line_width = (float(np.median(wr)) if wr else 0.002) * R
    lw = float(line_width)
    step = float(step) if step is not None else max(0.5, 0.5 * lw)
    rel = grammar.relations or {}
    topo = rel.get("topo") or {}
    if ends == "topo" and not topo.get("end_p"):
        ends = "v4"
    touch = max(TOUCH_R * R, TOUCH_W * lw)
    near = max(NEAR_R * R, 2 * touch)
    clr = max(clearance_w * lw, 2 * step)
    no_kiss = ends == "topo" and kiss_clear and topo.get("kiss_per_ink", 0.0) < KISS_FREE
    if no_kiss:
        clr = max(clr, 1.1 * touch)
    segl = [t[1] for toks in grammar.strokes[:2000] for t in toks if t[0] != "corner"]
    look = look_mult * max(4 * clr, (float(np.median(segl)) if segl else 0.03) * R)
    sheet = _Sheet(W, H, margin, clr)
    v6len = lengths == "v6"
    src_d = None
    if v6len:                        # v6: one training drawing sets ink, lengths and texture
        okd = [i for i, d in enumerate(grammar.drawings) if d["ink"] > 0 and d.get("i1", 1) > d.get("i0", 0)]
        src_d = okd[int(rng.integers(len(okd)))] if okd else None
        if ink is None and src_d is not None:
            ink = grammar.drawings[src_d]["ink"]
    if ink is None:
        inks = [d["ink"] for d in grammar.drawings if d["ink"] > 0]
        ink = _sample(inks, rng, 2.0)
    gain = rel.get("cross_gain", 1.0) if cross_gain is None else cross_gain
    cross_rate = gain * rel.get("cross_per_ink_median", rel.get("cross_per_ink", 0.0))
    meta = {"ref_length_gen": R, "hand": grammar.name, "mode": mode, "line_width_px": lw,
            "ink_budget": float(ink), "clearance_px": clr, "ends": ends, "lengths": lengths,
            "chain_budget": chain_budget, "source_drawing": src_d}
    gkw = {"p_follow": p_follow, "corner_len": corner_round_w * lw / R, "steer": steer, "max_run": max_run,
           "kmatch": kmatch, "corner_budget": corner_budget, "lw": lw, "touch": touch, "near": near,
           "chain_budget": chain_budget, "seek": "v6" if lengths == "v6" else "v5"}
    if mode == "single":
        st = _single_line(grammar, rng, sheet, R, lw, step, clr, look, float(ink), hands,
                          switch_every, K, gkw)
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
    if ends == "topo" and tree and p_continue is None:
        ep = topo["end_p"]
        pc = float(np.clip(ep["L"] / max(ep["L"] + ep["T"], 1e-9), 0.0, 1.0))
    self_frac = rel.get("selfcross_frac", 0.0)
    gaps = rel.get("gap_free") or []
    lengths_ = grammar.stroke_lengths or [0.1]
    min_len = grammar.min_length
    grower = _Grower(grammar, rng, sheet, R, step, clr, look, K, **gkw)
    placed: list[Stroke] = []
    free_ends: list[tuple[int, int]] = []
    protected: set = set()
    state = {"ink": 0.0, "crosses": 0}
    limit = max_strokes if n_strokes is None else min(n_strokes, max_strokes)
    fails = 0
    starts = {k: 0 for k in ("join", "double", "branch", "near", "free", "continue")}
    # v5 start/end shares
    if ends == "topo":
        eg = rel.get("end_gain") or {}       # calibrated: realised shares differ from planned ones
        ep = {k: v * float(eg.get(k, 1.0)) for k, v in topo["end_p"].items()}
        pd_ = float(rel.get("p_double", 0.0) if p_double is None else p_double)
        pL = float(np.clip(ep.get("L", 0.0), 0.0, 0.5))
        rest = max(1.0 - pL - pd_, 0.0)
        tnf = np.array([ep.get("T", 0.0), ep.get("near", 0.0), ep.get("free", 0.0)])
        tnf = tnf / tnf.sum() if tnf.sum() > 0 else np.array([0.2, 0.5, 0.3])
        if p_branch is not None:                              # override: T share of starts
            o = tnf[1:] / max(tnf[1:].sum(), 1e-9)
            start_p = {"join": pL * (1 - p_branch), "double": pd_ * (1 - p_branch), "branch": p_branch,
                       "near": rest * (1 - p_branch) * o[0], "free": rest * (1 - p_branch) * o[1]}
        else:
            start_p = {"join": pL, "double": pd_, "branch": rest * tnf[0], "near": rest * tnf[1],
                       "free": rest * tnf[2]}
        end_p = {"T": tnf[0], "near": tnf[1], "free": tnf[2]}
        meta.update(start_p=start_p, end_p=end_p)

    def crowd(pt):
        return int(sheet.tree.query_ball_point(pt, 0.08 * R, return_length=True)) if sheet.tree else 0

    def emptiest():
        if grammar.start_pos:
            sp = np.array([grammar.start_pos[int(rng.integers(len(grammar.start_pos)))]
                           for _ in range(8)])
            sp = np.clip(sp + rng.normal(0, 0.08, sp.shape), 0, 1)
        else:
            sp = rng.random((8, 2))
        cand = margin + sp * (np.array([W, H]) - 2 * margin)
        return sheet.free_point(rng, cand), rng.uniform(0, 2 * np.pi), 0.0, {"relation": "free"}

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
        return emptiest()

    def host_point(u_lo=0.08, u_hi=0.92, u=None):
        Ls = np.array([p.length() for p in placed])
        hi = int(rng.choice(len(placed), p=Ls / Ls.sum()))
        hp = placed[hi].points
        hs = _arclen(hp)
        u = float(rng.uniform(u_lo, u_hi)) if u is None else u
        j = int(np.clip(np.searchsorted(hs, u * hs[-1]), 0, len(hp) - 1))
        return hi, hp, hs, j

    def join_start():
        cands = [free_ends[int(rng.integers(len(free_ends)))] for _ in range(4)]
        cands = [(crowd(placed[f[0]].points[0 if f[1] == 0 else -1]), k, f) for k, f in enumerate(cands)]
        fe = min(cands)[2]
        if fe in protected:              # a joined end is no longer a free one
            protected.discard(fe)
            sheet.unprotect(placed[fe[0]].points[0 if fe[1] == 0 else -1])
        hp = placed[fe[0]].points
        hs = _arclen(hp)
        j = 0 if fe[1] == 0 else len(hp) - 1
        tan = _tangent(hp, hs, j, 5 * lw) * (-1 if fe[1] == 0 else 1)      # host outward
        if join == "sharp" and ends == "topo" and topo.get("l_defl"):
            a = abs(_sample(topo["l_defl"], rng, 1.2) + rng.normal(0, 0.05))
            a = a if rng.random() < 0.5 else -a
        else:
            a = rng.normal(0, 0.25)
        s_skip = clr * (2.0 + 1.0 / max(abs(np.sin(a)), 0.2)) if abs(a) > 0.3 else 2 * clr
        return hp[j], float(np.arctan2(tan[1], tan[0]) + a), s_skip, {
            "relation": "continue" if ends != "topo" else "join", "host": fe[0], "host_end": fe[1],
            "host_s": float(hs[j]), "branch_angle": float(a)}

    def branch_start():
        best_c = None
        uu_ = topo.get("t_u") if ends == "topo" else rel.get("u")
        for _k in range(6):
            u = float(np.clip(_sample(uu_, rng, float(rng.random())), 0.08, 0.92))
            hi, hp, hs, j = host_point(u=u)
            if ends == "topo":           # v5: away from the host's ends (else it reads as a join)
                e = min(1.1 * near, 0.45 * hs[-1])
                j = int(np.clip(np.searchsorted(hs, np.clip(hs[j], e, hs[-1] - e)), 0, len(hp) - 1))
            c = crowd(hp[j]) + (1000 if float(sheet.dist_keep(hp[j][None])[0]) < sheet.keep_r else 0)
            if best_c is None or c < best_c[0]:
                best_c = (c, hi, j)
        _c, hi, j = best_c
        hp = placed[hi].points
        hs = _arclen(hp)
        tan = _tangent(hp, hs, j, 3 * lw)
        aa = topo.get("t_angle") if ends == "topo" else rel.get("angle")
        a = abs(_sample(aa, rng, 0.6) + rng.normal(0, 0.05))
        if no_kiss:                      # v5: a branch that hugs its host reads as a kiss
            for _ in range(10):
                if a >= 0.55:
                    break
                a = abs(_sample(aa, rng, 0.6) + rng.normal(0, 0.05))
            a = max(a, 0.55)
        base = np.arctan2(tan[1], tan[0]) + (np.pi if rng.random() < 0.5 else 0.0)
        heading = float(base + (a if rng.random() < 0.5 else -a))
        s_skip = clr * (2.0 + 1.0 / max(np.sin(a), 0.2))
        if no_kiss:
            s_skip = max(2 * clr, 1.3 * clr / max(np.sin(a), 0.2))
        return hp[j], heading, s_skip, {"relation": "branch", "host": hi, "host_s": float(hs[j]),
                                        "branch_angle": float(a)}

    def near_start():
        for _ in range(12):
            hi, hp, hs, j = host_point(0.0, 1.0)
            tan = _tangent(hp, hs, j, 3 * lw)
            nrm = np.array([-tan[1], tan[0]]) * (1 if rng.random() < 0.5 else -1)
            g = float(np.clip(_sample(topo.get("near_gap"), rng, 0.012) * R, 1.05 * clr, near))
            c = hp[j] + g * nrm
            if not sheet.inside(c[None])[0] or float(sheet.dist(c[None])[0]) < 0.9 * g \
                    or float(sheet.dist_keep(c[None])[0]) < sheet.keep_r:
                continue
            a = _sample(topo.get("near_aim"), rng, 1.2) * (1 if rng.random() < 0.5 else -1)
            h0 = float(np.arctan2(nrm[1], nrm[0]) + a)
            return c, h0, 0.0, {"relation": "near", "gap": g / R}
        return emptiest()

    def double_start():
        for _ in range(8):
            ov = _sample(topo.get("par_length"), rng, 0.06) * R
            off = float(np.clip(_sample(topo.get("par_offset"), rng, 0.03) * R, 1.5 * clr, 0.06 * R))
            Ls = np.array([p.length() for p in placed])
            okh = Ls >= 1.2 * ov
            if not okh.any():
                return None
            pw = np.where(okh, Ls, 0.0)
            hi = int(rng.choice(len(placed), p=pw / pw.sum()))
            hp = placed[hi].points
            hs = _arclen(hp)
            fwd = rng.random() < 0.5
            u0 = float(rng.uniform(0.0, max(1e-6, 1 - ov / hs[-1])))
            sj = u0 * hs[-1] if fwd else (u0 * hs[-1] + ov)
            j = int(np.clip(np.searchsorted(hs, sj), 0, len(hp) - 1))
            tan = _tangent(hp, hs, j, 3 * lw) * (1 if fwd else -1)
            nrm = np.array([-tan[1], tan[0]]) * (1 if rng.random() < 0.5 else -1)
            c = hp[j] + off * nrm
            if not sheet.inside(c[None])[0] or float(sheet.dist(c[None])[0]) < 0.8 * off \
                    or float(sheet.dist_keep(c[None])[0]) < sheet.keep_r:
                continue
            guide = {"tree": cKDTree(hp), "offset": off, "length": ov}
            return c, float(np.arctan2(tan[1], tan[0])), 0.0, {"relation": "double", "host": hi,
                                                               "offset": off / R, "overlap": ov / R}, guide
        return None

    def pick_start():
        """(start, heading, s_skip, meta, guide) for the next line."""
        if ends != "topo" or tree:
            if placed and len(placed) >= roots and rng.random() < pb:
                if free_ends and rng.random() < pc:
                    return (*join_start(), None)
                return (*branch_start(), None)
            return (*free_start(), None) if ends != "topo" else (*emptiest(), None)
        ks = list(start_p)
        pv = np.array([start_p[k] for k in ks])
        k = ks[int(rng.choice(len(ks), p=pv / pv.sum()))] if pv.sum() > 0 else "free"
        if not placed or k == "free":
            return (*emptiest(), None)
        if k == "join":
            return (*join_start(), None) if free_ends else (*emptiest(), None)
        if k == "double":
            r = double_start()
            return r if r is not None else (*emptiest(), None)
        if k == "branch":
            return (*branch_start(), None)
        return (*near_start(), None)

    def pick_end():
        if ends != "topo":
            return None
        ks = list(end_p)
        pv = np.array([end_p[k] for k in ks])
        k = ks[int(rng.choice(len(ks), p=pv / pv.sum()))]
        return {"kind": k, "gap": _sample(topo.get("near_gap"), rng, 0.012) * R}

    n_tries = max(tries, LEN_TRIES) if v6len else tries
    while len(placed) < limit and fails < 4 * tries:
        if n_strokes is None and state["ink"] >= ink:
            break
        if v6len:
            lplan = plan_line(grammar, rng, drawing=src_d)
            target = lplan["length"]
        else:
            target = _sample(lengths_, rng, 0.1)
            lplan = plan_line(grammar, rng, length=target) if chain_budget > 0 else None
        self_ok = bool(rng.random() < self_frac)
        best = None
        for t in range(n_tries):
            start, heading, s_skip, rel_meta, guide = pick_start()
            plan = pick_end()
            tgt = max(target, 1.2 * guide["length"] / R) if guide else target
            c0, ink0 = state["crosses"], state["ink"]
            toks, how, nc = grower.grow(
                start, heading, tgt, s_skip=s_skip, host=rel_meta.get("host"), self_ok=self_ok,
                cross_ok=lambda s, c0=c0, ink0=ink0: c0 < cross_rate * (ink0 + s),
                end_plan=plan, guide=guide, plan=lplan)
            sc = stroke_length(toks)
            if v6len:                    # v6: the plan's length is protected
                good = sc >= max(min_len, LEN_KEEP * tgt)
            else:
                good = sc >= min_len and (how in ("T", "near") or sc >= 0.9 * tgt)
            if best is None or (good, sc) > (best[0], best[1]):
                best = (good, sc, toks, start, heading, nc, how, rel_meta, plan)
            if good:
                break
        if best is None or best[1] < min_len * 0.999 or (v6len and not best[0]):
            fails += 1                   # v6: a line that cannot reach its plan is not placed
            continue
        _good, sc, toks, start, heading, nc, how, rel_meta, plan = best
        st = _stroke(toks, R, start, heading, step,
                     {"hand": grammar.name, "end": how, "crosses": nc, "target": target,
                      "end_plan": (plan or {}).get("kind"), **rel_meta},
                     width=lw)
        d_ends = sheet.dist(st.points[[0, -1]])
        placed.append(st)
        sheet.add(st.points, len(placed) - 1)
        i = len(placed) - 1
        if ends == "topo":               # v5: free ends stay free — later lines keep `near` away
            if rel_meta["relation"] == "free" and d_ends[0] >= near:
                sheet.protect(st.points[0], near)
                protected.add((i, 0))
            if (plan or {}).get("kind") == "free" and how == "full" and d_ends[1] >= near:
                sheet.protect(st.points[-1], near)
                protected.add((i, 1))
        starts[rel_meta["relation"]] = starts.get(rel_meta["relation"], 0) + 1
        if rel_meta["relation"] in ("continue", "join"):
            free_ends.remove((rel_meta["host"], rel_meta["host_end"]))
        if rel_meta["relation"] == "free":
            free_ends.append((i, 0))
        if how not in ("T", "near"):
            free_ends.append((i, 1))
        state["ink"] += st.length() / R
        state["crosses"] += nc
    meta.update(grow_stats=grower.stats, starts=starts)
    meta.update(crosses=state["crosses"], ink=state["ink"], min_length=min_len,
                relations=relations, roots=roots, p_branch=pb, p_continue=pc, cross_rate=cross_rate)
    return Drawing(placed, source=f"grammar:{grammar.name}", size=(W, H), meta=meta)


def _single_line(g: Grammar, rng, sheet: _Sheet, R, lw, step, clr, look, ink, hands, switch_every, K,
                 gkw=None):
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
        target = min(_sample(gh.stroke_lengths or lengths, rng, 0.1) * 0.5 ** min(fails, 3),
                     ink - s_tot + 1e-6)             # shorter chunks after failures
        ctx = ((list(all_toks[-2]) if len(all_toks) >= 2 else ["START"]), list(all_toks[-1])) \
            if all_toks else None
        s_line = _arclen(pts_all)
        prior = pts_all[s_line < s_line[-1] - 4 * clr]
        grower = _Grower(gh, rng, sheet, R, step, clr, look, K, **(gkw or {}))
        best = None
        cplan = plan_line(gh, rng, length=target) if (gkw or {}).get("chain_budget", 0) > 0 else None
        for t in range(tries):
            toks, how, nc = grower.grow(pos, h, target, context=ctx, prior=prior,
                                        self_ok=t == tries - 1, plan=cplan if t < 2 else None)
            # (v6: the budget is a prior, not a wall — a boxed-in chunk retries without it)
            sc = stroke_length(toks)
            if best is None or sc > best[0]:
                best = (sc, toks, nc)
            if sc >= 0.9 * target:
                break
        sc, toks, nc = best
        if not toks or sc < 0.25 * target:
            fails += 1
            if not chunks:                          # boxed in at the start: start elsewhere
                start = m + rng.uniform(0.2, 0.8, 2) * (np.array([W, H]) - 2 * m)
                heading0 = rng.uniform(0, 2 * np.pi)
            if chunks and backtracks < 12:          # boxed in: back up one chunk, regrow
                popped = chunks.pop()
                backtracks += 1
                hand_i, next_switch = popped[5], None   # (v6 fix: the hand goes back with the chunk)
            continue
        pts, _, _ = tokens_to_points(toks, R, start=pos, heading=h, step=step)
        chunks.append((toks, pts, end_heading(toks, h), gh.name, nc, hand_i))
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
