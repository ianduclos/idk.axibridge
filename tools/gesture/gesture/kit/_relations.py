"""Relations (round 16 contract, lead-owned): what one layer of a score does
because of another. The synthesis bench's substructure is a list of layers
and the relations between them (`docs/synthesis-bench/design-2026-10-19.md`
§3 and §5); `_synth.py` plays them.

    from ._relations import relation, RelOut, crossings, cut
    from .core import P

    @relation("yield", phase="contact", params=[P("gap", "float", 1.2, "mm", min=0.1, max=6.0)],
              doc="the later line gives way at every crossing")
    def yield_(rctx, src, dst, *, gap):
        xs = crossings(src, dst)
        ...
        return RelOut(dst=new_dst, events=[{"outcome": "gap_under", "at": [x, y], "s": [s0, s1]}])

Two phases:
- "grow": shapes how the dst layer is drawn, reading earlier layers (imitate,
  echo, refuse, ride …). Runs right after the dst's own part, before any
  contact. May only return a new `dst` (the past is not rewritten here).
- "contact": resolves where two layers meet once both exist (crossing,
  sympathy, mask, depth). May return a new `src` and/or `dst`.

A relation never logs by itself: it returns `events`, the executor writes the
played log (who, when, which relation). Each event is a dict with "outcome"
(str) and optionally "at" [x, y] mm, "s" [s0, s1] mm on the dst's mark
"mark" (index into dst), "s_src", "note". Anything else JSON-able may ride
along.

Outcome names shared by crossing-type relations (so devices can count them
across relations): "gap_under" (the dst breaks: it passes under), "gap_over"
(the src breaks), "cross" (both run through), "stop" (one ends at the other),
"sympathy" (a pass bends with the other), "silent" (written by the executor
when `p` didn't fire). Other relations name their own outcomes.

Relations register in files named `relations_<prefix>.py` (discovered with
the rest of the kit). Ids are global; `relation_list()` shows them.

Wildcards, budgets, several sources (S0′, 2026-10-19): a relation's "*" side can
be narrowed with `except` (layer ids) and `roles` / `not_roles` (S0″: `src_…` / `dst_…`
for one side only); `budget` caps its
firings (non-neutral outcomes) across all pairs, read with `rctx.remaining()`; a
grow relation may hear a list of earlier layers (`"src": ["L1", "L2"]`, marks
merged in that order, each tagged `score_layer` so the relation can split them).
Every mark the executor grows carries a stable `mid` and `mid_s0`, and `pen_mm`
(its renderer's pen width). A relation may add marks with their own pen:
`meta["own_pen"] = {"colour": "red", "renderer": {"id": "wire", "pen": 0.3}}`.
Events that name a `mark` / `mark_src` gain `mid` / `mid_src` and the stretch on
the uncut line (`s_uncut` / `s_src_uncut`), written by the executor.

Determinism: draw only from `rctx.rng(*tags)` — seeded from (sheet seed,
relation instance id, src id, dst id, tags) — and order crossings by arc
length (`crossings` does), never by set or hash order. Editing one relation
re-rolls only that relation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, NamedTuple

import numpy as np

from .core import KitError, Mark, P, Param, RecipeError, tag

_RELATIONS: dict[str, "Relation"] = {}
PHASES = ("grow", "contact")


@dataclass(frozen=True)
class Relation:
    id: str
    fn: Callable
    phase: str
    params: tuple
    doc: str

    def validate(self, spec: Mapping | None, *, where: str = "") -> dict:
        spec = dict(spec or {})
        names = {p.name for p in self.params}
        bad = sorted(k for k in spec if k not in names)
        if bad:
            raise RecipeError(f"{where}: relation {self.id!r} has no param(s) {bad}; known: {sorted(names)}")
        return {p.name: p.validate(spec.get(p.name, p.default), where=f"{where} ({self.id})")
                for p in self.params}

    def spec(self) -> dict:
        return {"id": self.id, "phase": self.phase, "doc": self.doc, "params": [p.to_json() for p in self.params]}


class RelOut(NamedTuple):
    """What a relation returns. None = that side is unchanged."""
    dst: list | None = None
    src: list | None = None
    events: tuple | list = ()


@dataclass(frozen=True)
class RCtx:
    """What a relation knows. `ground` is every layer placed so far (id →
    marks, in drawing order, this step's layers included): read it for
    occupancy, never mutate it."""
    frame: tuple[float, float]
    sheet_seed: int
    rid: str
    kind: str
    src: str
    dst: str
    step: int
    run: Any = field(repr=False, compare=False)
    ground: Mapping[str, list] = field(repr=False, compare=False, default_factory=dict)
    left: int | None = None             # firings this relation may still make (its `budget`); None = no budget

    def remaining(self) -> int | None:
        """How many more changes this relation may make across the whole sheet (the score's `budget`
        key, counted over every pair by the executor; with a `budget_group`, the tighter of its own
        and the group's), or None when it has no budget. A relation
        that honours it stops changing lines once this reaches 0 in one application; the executor
        skips further applications by itself."""
        return self.left

    def rng(self, *tags) -> np.random.Generator:
        return np.random.default_rng([tag(self.sheet_seed), tag("relation"), tag(self.rid), tag(self.src),
                                      tag(self.dst), *map(tag, tags)])

    def use(self, kind: str, id: str, purpose: str = "generate"):
        return self.run.use(kind, id, purpose)


def relation(id: str, *, phase: str, params=(), doc: str = ""):
    if phase not in PHASES:
        raise KitError(f"relation {id!r}: phase must be one of {PHASES}")
    for p in params:
        if not isinstance(p, Param):
            raise KitError(f"relation {id!r}: params must be P(...)")
        if p.when is not None:
            _check_when(p.when, {q.name: q for q in params}, f"relation {id!r} param {p.name!r}: when")

    def wrap(fn):
        if id in _RELATIONS and _RELATIONS[id].fn is not fn:
            raise KitError(f"relation id {id!r} is already registered")
        _RELATIONS[id] = Relation(id, fn, phase, tuple(params), doc)
        return fn
    return wrap


def _check_when(w, params: Mapping, where: str, depth: int = 0) -> None:
    """A param's `when` (Gesture Studies' dialect, see `core.Param`): every key a sibling param, every
    value one that param takes."""
    if depth > 4 or not isinstance(w, Mapping):
        raise KitError(f"{where} must be an object (nested at most 4 deep)")
    say = w.get("say")
    if say is not None and (not isinstance(say, str) or not 0 < len(say) <= 120):
        raise KitError(f"{where}: say is a short sentence")
    ops = [k for k in ("is", "not", "in", "all", "any") if k in w]
    if set(w) - {"key", "is", "not", "in", "all", "any", "say"} or len(ops) != 1:
        raise KitError(f"{where} takes key + one of is / not / in, or all / any (got {sorted(w)})")
    op = ops[0]
    if op in ("all", "any"):
        if "key" in w or not isinstance(w[op], list) or not 1 <= len(w[op]) <= 8:
            raise KitError(f"{where}: {op} is a list of 1-8 conditions, without a key")
        for x in w[op]:
            _check_when(x, params, where, depth + 1)
        return
    if w.get("key") not in params:
        raise KitError(f"{where}: key {w.get('key')!r} names no sibling param")
    for v in (w[op] if op == "in" else [w[op]]):
        try:
            params[w["key"]].validate(v, where=where)
        except RecipeError as e:
            raise KitError(f"{where}: {v!r} is not a value of {w['key']!r} ({e})") from None


def get_relation(id: str) -> Relation:
    from .core import discover  # noqa: PLC0415
    discover()
    if id not in _RELATIONS:
        raise RecipeError(f"unknown relation {id!r}; known: {sorted(_RELATIONS)}")
    return _RELATIONS[id]


def relation_list() -> list[dict]:
    from .core import discover  # noqa: PLC0415
    discover()
    return [_RELATIONS[k].spec() for k in sorted(_RELATIONS)]


# ---------------------------------------------------------------------------
# helpers every relation needs
# ---------------------------------------------------------------------------

class Crossing(NamedTuple):
    at: tuple[float, float]
    i_src: int          # index of the src mark
    s_src: float        # arc length on it, mm
    i_dst: int
    s_dst: float


def _seg_hits(p: np.ndarray, q: np.ndarray):
    """All proper intersections between polyline p and polyline q:
    (ip, tp, iq, tq) with segment indices and fractions."""
    a0, a1 = p[:-1], p[1:]
    b0, b1 = q[:-1], q[1:]
    if not len(a0) or not len(b0):
        return []
    # bbox prefilter
    alo, ahi = np.minimum(a0, a1), np.maximum(a0, a1)
    blo, bhi = np.minimum(b0, b1), np.maximum(b0, b1)
    if (alo.min(0) > bhi.max(0)).any() or (blo.min(0) > ahi.max(0)).any():
        return []
    ox = (alo[:, None, 0] <= bhi[None, :, 0]) & (blo[None, :, 0] <= ahi[:, None, 0])
    oy = (alo[:, None, 1] <= bhi[None, :, 1]) & (blo[None, :, 1] <= ahi[:, None, 1])
    ii, jj = np.nonzero(ox & oy)
    if not len(ii):
        return []
    r = (a1 - a0)[ii]
    s = (b1 - b0)[jj]
    qp = b0[jj] - a0[ii]
    den = r[:, 0] * s[:, 1] - r[:, 1] * s[:, 0]
    ok = np.abs(den) > 1e-12
    t = np.where(ok, (qp[:, 0] * s[:, 1] - qp[:, 1] * s[:, 0]) / np.where(ok, den, 1), -1)
    u = np.where(ok, (qp[:, 0] * r[:, 1] - qp[:, 1] * r[:, 0]) / np.where(ok, den, 1), -1)
    hit = ok & (t >= 0) & (t < 1) & (u >= 0) & (u < 1)
    return list(zip(ii[hit].tolist(), t[hit].tolist(), jj[hit].tolist(), u[hit].tolist()))


def crossings(src: list[Mark], dst: list[Mark], *, min_sep: float = 0.0) -> list[Crossing]:
    """Every crossing between a src mark and a dst mark, ordered by
    (dst mark, arc length on it) — a deterministic order to draw outcomes in.
    `min_sep` drops crossings closer than that along the dst mark (a tangle
    counts once)."""
    out: list[Crossing] = []
    for jd, md in enumerate(dst):
        if len(md) < 2:
            continue
        sd = md.arclength()
        for js, ms in enumerate(src):
            if len(ms) < 2 or ms is md:
                continue
            ss = ms.arclength()
            for ip, tp, iq, tq in _seg_hits(md.points, ms.points):
                at = md.points[ip] + tp * (md.points[ip + 1] - md.points[ip])
                out.append(Crossing((float(at[0]), float(at[1])), js,
                                    float(ss[iq] + tq * (ss[iq + 1] - ss[iq])), jd,
                                    float(sd[ip] + tp * (sd[ip + 1] - sd[ip]))))
    out.sort(key=lambda c: (c.i_dst, c.s_dst, c.i_src, c.s_src))
    if min_sep > 0 and out:
        kept = [out[0]]
        for c in out[1:]:
            if c.i_dst != kept[-1].i_dst or c.s_dst - kept[-1].s_dst >= min_sep:
                kept.append(c)
        out = kept
    return out


def cut(mark: Mark, intervals, *, min_piece: float = 1.0) -> list[Mark]:
    """The mark with the arc-length intervals [(s0, s1), …] removed: the
    pieces that remain, each at least `min_piece` mm (a piece touching an end
    of the mark is kept whatever its length). Channels are carried."""
    s = mark.arclength()
    L = float(s[-1]) if len(s) else 0.0
    iv = sorted((max(0.0, float(a)), min(L, float(b))) for a, b in intervals if b > a)
    merged: list[list[float]] = []
    for a, b in iv:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    keep, x = [], 0.0
    for a, b in merged:
        if a > x:
            keep.append((x, a))
        x = max(x, b)
    if x < L:
        keep.append((x, L))
    out = []
    for a, b in keep:
        if b - a < min_piece and a > 0 and b < L:
            continue
        if b - a <= 1e-9:
            continue
        inner = s[(s > a) & (s < b)]
        sn = np.concatenate([[a], inner, [b]])
        # a stable mark id (`mid`, from the executor) survives the cut; `mid_s0` moves to where this piece starts
        meta = {"mid_s0": float(mark.meta.get("mid_s0", 0.0)) + float(a)} if "mid" in mark.meta else None
        out.append(mark.remap(sn, meta=meta))
    return out


def gap_marks(marks: list[Mark], cuts: Mapping[int, list], *, min_piece: float = 1.0) -> list[Mark]:
    """Apply `cut` per mark index: {mark index: [(s0, s1), …]}; marks without
    cuts pass through unchanged (same objects)."""
    out = []
    for i, m in enumerate(marks):
        out += cut(m, cuts[i], min_piece=min_piece) if cuts.get(i) else [m]
    return out


def pick(rng: np.random.Generator, weights: Mapping[str, float]) -> str:
    """One key of `weights`, drawn in sorted-key order (deterministic)."""
    keys = sorted(k for k, w in weights.items() if w > 0)
    if not keys:
        raise KitError("pick: every weight is zero")
    w = np.array([float(weights[k]) for k in keys])
    return keys[int(rng.choice(len(keys), p=w / w.sum()))]
