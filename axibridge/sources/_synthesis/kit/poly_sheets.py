# FROZEN from research commit d5ccd75: tools/gesture/gesture/kit/poly_sheets.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Polyphonic sheets — arrangers that compose a sheet of separate UNITS, each
part its own grammar, plus annotation: one part comments on the others.

Round 9, thread polyphonic_sheets (results/polyphonic_sheets-2026-10-17.md).
Why: results/round8-review-2026-10-17.md (a sheet is a SET of distinct
grammars kept whole, side by side, some elements crossing or commenting on
others) and results/sheet_composition-2026-10-16.md (our sheets were one
welded net: 1-2 islands, few free ends, no edge contact; the corpora have
12-90 units and run into the margin; structure decides composition).

Arrangers (every one works with any voice by id):

- `poly_scatter`  units scattered over the sheet. Each part becomes `counts[i]`
                  units at its own size class (`sizes[i]`, one scale per voice:
                  a hand writes at one size), either CUT from one long line of
                  the voice (words of one utterance) or RESTATED (separate
                  growths, seeds derived from the part seed). Some units bleed
                  over an edge and are clipped there (free ends at the edge);
                  `pull: edges` sends marginal units to the rim around a
                  dominant one.
- `poly_page`     a page of writing: body voices cut into words laid on rows
                  (columns, ltr/rtl, ragged or justified, interlinear when
                  several body voices alternate rows), gloss voices set small
                  in a margin column beside the rows they gloss; rows may run
                  off the block into the sheet edge.
- `poly_converse` the limb: units take turns, and each reply is DERIVED from
                  what the previous unit did — its measured line statistics
                  choose the reply's hand (contrast / echo), its length and its
                  weight, and the reply starts where the call ended, across a
                  gap, along the call's last heading.

Annotation (all three arrangers: `annotate`, `annotator`, `n_annot`,
`annot_amp`): the annotator part speaks no unit of its own; its voice is grown
per annotation and its line is WARPED INTO A BAND along a route defined by
another unit — `underline`, `bracket` (a span of rows / a unit's side, with
hooks), `encircle`, `tether` (from one unit's free end to another unit of a
different voice), `point` (from the sheet edge to a unit, stopping short),
`echo` (a smoothed, offset paraphrase of the unit's own path). The band keeps
the annotator's grammar (its principal axis runs along the route, its minor
axis becomes the band's lateral motion), and its own modulators/renderer
apply, so a nib, a timing dance or a dry wire can all annotate.

Kit-core workarounds (proposed as core changes in the write-up):
- a part has one seed; restated units copy the Part with a derived seed
  (`_variant`), keeping its index so the core renders it with that part's
  renderer;
- the converse reply edits a copy of the part's voice spec and re-validates
  it through the voice module.
"""
from __future__ import annotations

import copy
import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .core import P, RecipeError, arclength, arranger, get, native_bbox, refit, tag

# ---------------------------------------------------------------------------
# parts
# ---------------------------------------------------------------------------


def _variant(part, k: int, spec: dict | None = None):
    """Part `part` restated: same index (renderer, meta["part"]) and spec,
    a seed derived from (part seed, k). k = 0 and no spec → the part itself."""
    if k == 0 and spec is None:
        return part
    q = copy.copy(part)
    if k:
        q.seed = int(np.random.default_rng([tag(int(part.seed)), 0x9017, int(k)]).integers(0, 2**31 - 1))
    if spec is not None:
        q.spec = spec
    return q


def _grow(part, box, k: int = 0):
    return _variant(part, k).voice(box)


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------


def _bbox(marks):
    Pts = np.vstack([m.points for m in marks if len(m)])
    return Pts.min(axis=0), Pts.max(axis=0)


def _move(marks, k: float, off):
    return [m.transformed(float(k), np.asarray(off, float)) for m in marks]


def _rotate(marks, quarter: int, flip: bool = False):
    """Rotate by quarter·90° (and mirror x first if flip) about the bbox centre.
    meta["fit"] is dropped (no longer a pure scale+offset)."""
    if not marks or (quarter % 4 == 0 and not flip):
        return list(marks)
    lo, hi = _bbox(marks)
    c = (lo + hi) / 2
    out = []
    for m in marks:
        q = m.points - c
        if flip:
            q = q * np.array([-1.0, 1.0])
        for _ in range(quarter % 4):
            q = np.column_stack([-q[:, 1], q[:, 0]])
        out.append(m.evolve(points=q + c, meta={"fit": None, "rot": int(quarter % 4), "flip": bool(flip)}))
    return out


def _inside(p, rect):
    x0, y0, w, h = rect
    return (p[..., 0] >= x0) & (p[..., 0] <= x0 + w) & (p[..., 1] >= y0) & (p[..., 1] <= y0 + h)


def _cross(p_out, p_in, s_out, s_in, rect) -> float:
    lo, hi = 0.0, 1.0                      # t: 0 at p_out (outside), 1 at p_in (inside)
    for _ in range(26):
        mid = 0.5 * (lo + hi)
        if _inside(p_out + mid * (p_in - p_out), rect):
            hi = mid
        else:
            lo = mid
    return float(s_out + hi * (s_in - s_out))


def clip_marks(marks, rect, min_len: float = 0.8):
    """Split marks at the rect boundary (exact crossings, every channel
    interpolated by Mark.remap); pieces shorter than min_len mm are dropped.
    A mark that was cut records meta["edge"] = True."""
    out = []
    for m in marks:
        p = m.points
        if len(p) < 2:
            continue
        ins = _inside(p, rect)
        if ins.all():
            out.append(m)
            continue
        if not ins.any():
            continue
        s = m.arclength()
        d = np.diff(np.r_[0, ins.astype(int), 0])
        for a, b in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1):
            sa = _cross(p[a - 1], p[a], s[a - 1], s[a], rect) if a > 0 else s[a]
            sb = _cross(p[b + 1], p[b], s[b + 1], s[b], rect) if b < len(p) - 1 else s[b]
            ss = np.unique(np.r_[sa, s[a:b + 1], sb])
            if len(ss) < 2 or ss[-1] - ss[0] < min_len:
                continue
            out.append(m.remap(ss).evolve(meta={"fit": None, "edge": True}))
    return out


def cut_marks(marks, cuts):
    """Cut a voice's marks (taken as one sequence) at global arc lengths
    `cuts` (sorted, inside (0, total)) → list of pieces (each a list of
    Marks). Pieces keep meta["fit"], so they can be refit at native scale."""
    lens = [m.length() for m in marks]
    starts = np.r_[0.0, np.cumsum(lens)]
    total = float(starts[-1])
    edges = np.r_[0.0, np.asarray(cuts, float), total]
    pieces = []
    for a, b in zip(edges[:-1], edges[1:]):
        piece = []
        for m, s0, L in zip(marks, starts[:-1], lens):
            lo, hi = max(a, s0), min(b, s0 + L)
            if hi - lo <= 1e-9:
                continue
            s = m.arclength()
            ss = np.unique(np.r_[lo - s0, s[(s > lo - s0) & (s < hi - s0)], hi - s0])
            if len(ss) >= 2:
                piece.append(m.remap(ss))
        if piece:
            pieces.append(piece)
    return pieces


def _native_size(marks):
    nb = native_bbox(marks)
    if nb is not None:
        return np.maximum(nb[1] - nb[0], 1e-9)
    lo, hi = _bbox(marks)
    return np.maximum(hi - lo, 1e-9)


def _at_native(marks, scale: float, centre):
    """marks placed with centre `centre` at native scale `scale` (falls back
    to scaling the current geometry by scale / current-size ratio)."""
    lo, hi = _bbox(marks)
    nb = native_bbox(marks)
    k = scale / nb[2] if nb is not None else scale
    off = np.asarray(centre, float) - (lo + hi) / 2 * k
    return [m.transformed(k, off) for m in marks]


def _smooth_path(path, sigma_pts: float):
    if sigma_pts <= 0 or len(path) < 3:
        return np.asarray(path, float)
    return np.column_stack([gaussian_filter1d(path[:, 0], sigma_pts, mode="nearest"),
                            gaussian_filter1d(path[:, 1], sigma_pts, mode="nearest")])


def _resample_path(path, n: int = 400):
    path = np.asarray(path, float)
    s = arclength(path)
    if s[-1] <= 0:
        return np.repeat(path[:1], n, axis=0)
    u = np.linspace(0, s[-1], n)
    return np.column_stack([np.interp(u, s, path[:, 0]), np.interp(u, s, path[:, 1])])


def band_warp(lines, path, amp: float, *, reverse: bool = False):
    """Lines (any units; taken together) warped into a band along `path`
    (mm): their principal axis maps onto the path's arc length, their
    minor-axis offset onto the path normal, scaled so the band's half-width
    is `amp` mm. Returns new point arrays, one per line (same lengths)."""
    allp = np.vstack(lines)
    c = allp.mean(axis=0)
    _, _, vt = np.linalg.svd(allp - c, full_matrices=False)
    ax, mn = vt[0], vt[1]
    a_all = (allp - c) @ ax
    first = (lines[0][0] - c) @ ax
    sgn = -1.0 if (first > np.median(a_all)) != reverse else 1.0     # start near the path's start
    a_lo, a_hi = float(np.min(sgn * a_all)), float(np.max(sgn * a_all))
    b_all = (allp - c) @ mn
    b_max = max(float(np.percentile(np.abs(b_all), 95)), 1e-9)      # one hairpin must not flatten the rest
    path = _resample_path(path, 600)
    sp = arclength(path)
    L = float(sp[-1])
    tg = np.gradient(path, axis=0)
    tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
    nrm = np.column_stack([-tg[:, 1], tg[:, 0]])
    out = []
    for q in lines:
        a = sgn * ((q - c) @ ax)
        b = ((q - c) @ mn) / b_max * amp
        u = (a - a_lo) / max(a_hi - a_lo, 1e-9) * L
        x = np.interp(u, sp, path[:, 0])
        y = np.interp(u, sp, path[:, 1])
        nx = np.interp(u, sp, nrm[:, 0])
        ny = np.interp(u, sp, nrm[:, 1])
        out.append(np.column_stack([x + nx * b, y + ny * b]))
    return out


def _overlap(a, b, gap: float) -> float:
    """Overlap of boxes a, b (x0, y0, w, h) inflated by gap, as a share of the smaller."""
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ix = min(ax0 + aw + gap, bx0 + bw + gap) - max(ax0 - gap, bx0 - gap)
    iy = min(ay0 + ah + gap, by0 + bh + gap) - max(ay0 - gap, by0 - gap)
    if ix <= 0 or iy <= 0:
        return 0.0
    return ix * iy / max(min(aw * ah, bw * bh), 1e-9)


# ---------------------------------------------------------------------------
# units + annotation
# ---------------------------------------------------------------------------


class Unit:
    """One placed unit: part index, marks (placed, unmodulated), box, group tag."""

    def __init__(self, uid: int, part: int, marks, group=None):
        self.uid, self.part, self.marks, self.group = uid, part, marks, group
        lo, hi = _bbox(marks)
        self.lo, self.hi = lo, hi

    @property
    def box(self):
        return (float(self.lo[0]), float(self.lo[1]), float(self.hi[0] - self.lo[0]), float(self.hi[1] - self.lo[1]))

    @property
    def centre(self):
        return (self.lo + self.hi) / 2

    def longest(self):
        return max(self.marks, key=lambda m: m.length())


ANNOT_MODES = ("none", "underline", "bracket", "encircle", "tether", "point", "echo", "mixed")
_MIXABLE = ("underline", "bracket", "encircle", "tether", "point", "echo")


def _annot_route(mode, tgt, units, frame_box, rng, gap):
    """(path mm, reverse) for one annotation of unit/group `tgt` = (lo, hi, units)."""
    lo, hi, members = tgt[:3]
    w, h = hi - lo
    x0, y0, W, H = frame_box
    if mode == "underline":
        y = hi[1] + gap
        sag = rng.uniform(-0.04, 0.04) * w
        xs = np.linspace(lo[0] - 0.06 * w, hi[0] + 0.06 * w, 50)
        return np.column_stack([xs, y + sag * np.sin(np.linspace(0, np.pi, 50))]), False
    if mode == "bracket":
        left_free = lo[0] - x0
        right_free = x0 + W - hi[0]
        side = -1.0 if left_free >= right_free else 1.0
        x = (lo[0] - gap) if side < 0 else (hi[0] + gap)
        t = -side * min(max(0.12 * w, 2.0), 8.0)
        return np.array([[x + t, lo[1]], [x, lo[1]], [x, hi[1]], [x + t, hi[1]]]), False
    if mode == "encircle":
        c = (lo + hi) / 2
        rx, ry = w / 2 * 1.18 + gap, h / 2 * 1.25 + gap
        a0 = rng.uniform(0, 2 * np.pi)
        turn = rng.uniform(1.05, 1.25) * 2 * np.pi
        th = a0 + np.linspace(0, turn, 160)
        grow = np.linspace(1.0, rng.uniform(1.06, 1.18), 160)
        return np.column_stack([c[0] + rx * grow * np.cos(th), c[1] + ry * grow * np.sin(th)]), False
    if mode == "echo":
        m = max((mk for u in members for mk in u.marks), key=lambda mk: mk.length())
        p = _resample_path(m.points, 500)
        p = _smooth_path(p, 500 * 0.035)
        tg = np.gradient(p, axis=0)
        tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
        nrm = np.column_stack([-tg[:, 1], tg[:, 0]])
        p = p + nrm * gap * rng.choice([-1.0, 1.0])
        a = rng.uniform(0.0, 0.4)
        b = min(1.0, a + rng.uniform(0.35, 0.6))
        return p[int(a * 499):int(b * 499) + 1], False
    if mode == "point":
        c = (lo + hi) / 2
        dists = {"l": c[0] - x0, "r": x0 + W - c[0], "t": c[1] - y0, "b": y0 + H - c[1]}
        edge = max(sorted(dists), key=lambda e: dists[e] * rng.uniform(0.3, 1.0))   # pointers come from afar
        along = rng.uniform(-0.25, 0.25)
        if edge == "l":
            start = np.array([x0 - 4.0, c[1] + along * H])
        elif edge == "r":
            start = np.array([x0 + W + 4.0, c[1] + along * H])
        elif edge == "t":
            start = np.array([c[0] + along * W, y0 - 4.0])
        else:
            start = np.array([c[0] + along * W, y0 + H + 4.0])
        v = c - start
        d = np.linalg.norm(v)
        r_stop = 0.5 * math.hypot(w, h) + gap
        end = start + v * max(d - r_stop, 0.3 * d) / max(d, 1e-9)
        return _bow(start, end, rng.uniform(-0.12, 0.12)), False
    # tether: from this unit's free end to the nearest unit of another voice
    src_mark = max((mk for u in members for mk in u.marks), key=lambda mk: mk.length())
    start = src_mark.points[-1]
    parts = {u.part for u in members}
    others = [u for u in units if u.part not in parts and u not in members] or \
             [u for u in units if u not in members]
    if not others:
        return None, False
    cand = sorted(others, key=lambda u: float(np.linalg.norm(u.centre - start)))[:3]
    o = cand[int(rng.integers(len(cand)))]
    pts = np.vstack([mk.points[::max(1, len(mk) // 200)] for mk in o.marks])
    end = pts[np.argmin(np.linalg.norm(pts - start, axis=1))]
    return _bow(start, end, rng.uniform(-0.25, 0.25)), False


def _bow(a, b, k):
    t = np.linspace(0, 1, 80)[:, None]
    v = b - a
    n = np.array([-v[1], v[0]])
    ctrl = (a + b) / 2 + n * k
    return (1 - t) ** 2 * a + 2 * (1 - t) * t * ctrl + t ** 2 * b


def annotate_units(ctx, parts, units, annotator: int, mode: str, n: int, amp: float, targets=None,
             gap: float | None = None):
    """Annotation marks: the annotator part's voice, grown per annotation
    (restated seeds), warped into a band along a route defined by a target
    unit (or group), clipped to the sheet, then modulated by the annotator's
    own chain. targets: list of (lo, hi, [units]) (default: single units,
    larger ones more likely)."""
    if mode == "none" or n <= 0 or not units:
        return []
    ap = parts[annotator]
    rng = ctx.rng("annotate", mode)
    if targets is None:
        sizes = np.array([float(np.prod(u.hi - u.lo)) ** 0.5 for u in units])
        pw = sizes / sizes.sum()
        k = min(n, len(units))
        pick = rng.choice(len(units), size=k, replace=False, p=pw)
        targets = [(units[i].lo, units[i].hi, [units[i]]) for i in sorted(pick)]
        targets = [targets[j] for j in rng.permutation(len(targets))]
    else:
        targets = list(targets)[:n]
    out = []
    for j, tgt in enumerate(targets):
        md = tgt[3] if len(tgt) > 3 else mode
        if md == "mixed":
            md = _MIXABLE[int(rng.integers(len(_MIXABLE)))]
        g = gap if gap is not None else max(1.2, 0.06 * float(np.hypot(*(tgt[1] - tgt[0]))))
        path, rev = _annot_route(md, tgt, units, ctx.box, rng, g)
        if path is None or arclength(path)[-1] < 1.0:
            continue
        marks = _grow(ap, ctx.box, 101 + j)
        if not marks:
            continue
        a = amp if md != "echo" else 0.4 * amp
        warped = band_warp([m.points for m in marks], path, a, reverse=rev)
        placed = [m.evolve(points=w, meta={"fit": None, "annotation": md,
                                           "annotates": [u.uid for u in tgt[2]]})
                  for m, w in zip(marks, warped)]
        placed = clip_marks(placed, ctx.box)
        if placed:
            out += ap.modulate(placed, ctx.box)
    return out


def _annotator_index(parts, annotator: int, mode: str) -> int | None:
    if mode == "none":
        return None
    if len(parts) < 2:
        raise RecipeError("annotation needs at least two parts (one speaks, one annotates)")
    a = len(parts) - 1 if annotator < 0 else annotator
    if a >= len(parts):
        raise RecipeError(f"annotator={annotator} but the recipe has {len(parts)} parts")
    return a


_ANNOT_PARAMS = [
    P("annotate", "choice", "none", "how the annotator part comments on the units: underline | bracket | "
      "encircle | tether (unit to unit of another voice) | point (from the edge) | echo (paraphrase of the "
      "unit's path) | mixed", choices=ANNOT_MODES),
    P("annotator", "int", -1, "index of the annotating part (-1 = the last part); it speaks no unit of its own",
      min=-1, max=11),
    P("n_annot", "int", 4, "number of annotations", min=0, max=40),
    P("annot_amp", "float", 2.2, "half-width of the annotation band, mm (the annotator's lateral motion)",
      min=0.1, max=12.0),
]


def _fill(lst, n, default):
    lst = list(lst) if lst else [default]
    return [lst[i % len(lst)] for i in range(n)]


# ---------------------------------------------------------------------------
# poly_scatter
# ---------------------------------------------------------------------------


def _unit_pieces(part, idx, count: int, mode: str, box, rng):
    """`count` pieces (lists of Marks with meta fit) of part's voice."""
    if mode == "restate" or count == 1:
        return [_grow(part, box, k) for k in range(count)]
    marks = _grow(part, box, 0)
    total = sum(m.length() for m in marks)
    w = rng.gamma(2.0, 1.0, size=count)
    cuts = np.cumsum(w / w.sum())[:-1] * total
    return cut_marks(marks, cuts)


@arranger("poly_scatter", params=[
    P("counts", "floats", [1, 5, 12], "units per part (cycled); the annotator's entry is ignored",
      min=1, max=60),
    P("sizes", "floats", [0.8, 0.3, 0.13], "unit size per part, as a share of the sheet's short side "
      "(one scale per voice: the median unit of that voice has this long side)", min=0.03, max=1.2),
    P("mode", "choice", "cut", "cut: a part's units are pieces of ONE long line (words of one utterance); "
      "restate: separate growths", choices=("cut", "restate")),
    P("bleed", "float", 0.2, "share of units pushed over a sheet edge (clipped there)", min=0.0, max=1.0),
    P("pull", "choice", "free", "free: anywhere; edges: smaller units seek the rim (a dominant voice with "
      "marginal ones)", choices=("free", "edges")),
    P("gap", "float", 3.0, "clearance between unit boxes, mm", min=0.0, max=40.0),
    P("overlap", "float", 0.15, "tolerated box overlap (share of the smaller box)", min=0.0, max=1.0),
    P("rotate", "choice", "none", "none | quarter: each unit turned by a random multiple of 90° | voice: one "
      "turn per voice", choices=("none", "quarter", "voice")),
    *_ANNOT_PARAMS,
], doc="separate units of each voice scattered over the sheet; some bleed off the edge; optional annotation")
def poly_scatter(ctx, parts, *, counts, sizes, mode, bleed, pull, gap, overlap, rotate,
                 annotate, annotator, n_annot, annot_amp):
    a_idx = _annotator_index(parts, annotator, annotate)
    x0, y0, W, H = ctx.box
    short = min(W, H)
    rng = ctx.rng("scatter")
    counts = [int(round(c)) for c in _fill(counts, len(parts), 1)]
    sizes = _fill(sizes, len(parts), 0.3)
    voice_turn = {i: int(rng.integers(4)) for i in range(len(parts))}
    pending = []                                   # (size, part index, piece marks)
    for i, p in enumerate(parts):
        if i == a_idx:
            continue
        pieces = _unit_pieces(p, i, counts[i], mode, ctx.box, ctx.rng("pieces", i))
        nat = [_native_size(pc) for pc in pieces]
        med = float(np.median([n.max() for n in nat]))
        scale = sizes[i] * short / max(med, 1e-9)
        for pc, n_ in zip(pieces, nat):
            k = scale
            if (n_ * k).max() > 0.98 * max(W, H) or (n_ * k).min() > 0.98 * short:
                k = min(0.98 * W / n_[0], 0.98 * H / n_[1])
            pending.append((float((n_ * k).max()), i, _at_native(pc, k, (0.0, 0.0))))
    pending.sort(key=lambda t: -t[0])
    placed_boxes, units = [], []
    big = pending[0][0] if pending else 1.0
    for uid, (sz, i, marks) in enumerate(pending):
        turn = voice_turn[i] if rotate == "voice" else int(rng.integers(4)) if rotate == "quarter" else 0
        marks = _rotate(marks, turn)
        lo, hi = _bbox(marks)
        w, h = hi - lo
        bleeder = rng.random() < bleed and (uid > 0 or len(pending) == 1)
        marginal = pull == "edges" and sz < 0.6 * big
        best, best_cost = None, None
        for _ in range(240):
            if bleeder:
                e = int(rng.integers(4))
                d = rng.uniform(0.15, 0.5)
                if e == 0:
                    cx, cy = x0 - w / 2 + d * w, rng.uniform(y0, y0 + H)
                elif e == 1:
                    cx, cy = x0 + W + w / 2 - d * w, rng.uniform(y0, y0 + H)
                elif e == 2:
                    cx, cy = rng.uniform(x0, x0 + W), y0 - h / 2 + d * h
                else:
                    cx, cy = rng.uniform(x0, x0 + W), y0 + H + h / 2 - d * h
            else:
                cx = rng.uniform(x0 + w / 2, x0 + W - w / 2) if w < W else x0 + W / 2
                cy = rng.uniform(y0 + h / 2, y0 + H - h / 2) if h < H else y0 + H / 2
            bx = (cx - w / 2, cy - h / 2, w, h)
            ov = max([_overlap(bx, b, gap) for b in placed_boxes] or [0.0])
            cost = max(ov - overlap, 0.0)
            if marginal:
                edge_d = min(bx[0] - x0, x0 + W - bx[0] - w, bx[1] - y0, y0 + H - bx[1] - h)
                cost += 0.02 * max(edge_d, 0.0) / short
            if best_cost is None or cost < best_cost - 1e-12:
                best, best_cost = bx, cost
            if cost <= 0.0 and not marginal:
                break
        bx = best
        marks = [m.transformed(1.0, np.array([bx[0], bx[1]]) - lo) for m in marks]
        placed_boxes.append(bx)
        marks = clip_marks(marks, ctx.box)
        if marks:
            units.append(Unit(uid, i, marks))
    out = []
    for u in units:
        out += parts[u.part].modulate(u.marks, u.box)
    if a_idx is not None:
        out += annotate_units(ctx, parts, units, a_idx, annotate, n_annot, annot_amp)
    return out


# ---------------------------------------------------------------------------
# poly_page
# ---------------------------------------------------------------------------


def _words(part, n_words: int, box, k: int, rng):
    marks = _grow(part, box, k)
    total = sum(m.length() for m in marks)
    w = rng.gamma(3.0, 1.0, size=n_words)
    cuts = np.cumsum(w / w.sum())[:-1] * total
    return cut_marks(marks, cuts)


def _word_stream(part, n_words, box, rng):
    k = 0
    while k < 80:
        for pc in _words(part, n_words, box, k, rng):
            yield pc
        k += 1


@arranger("poly_page", params=[
    P("roles", "str", "", "space-separated role per part: body | gloss (empty: part 0 body, part 1 gloss, "
      "the rest body); the annotator's role is ignored"),
    P("columns", "int", 1, "text columns in the block", min=1, max=4),
    P("rows", "int", 9, "rows per column", min=1, max=40),
    P("words", "int", 30, "words cut from each grown line (more = shorter words)", min=2, max=120),
    P("interlinear", "bool", True, "several body voices alternate rows (else: one after another)"),
    P("direction", "choice", "ltr", "writing direction", choices=("ltr", "rtl")),
    P("justify", "bool", False, "stretch word gaps so full rows end flush"),
    P("x_height", "float", 0.5, "a body word's median height, share of the row pitch", min=0.2, max=2.0),
    P("word_gap", "float", 0.35, "gap between words, share of the row pitch", min=0.0, max=3.0),
    P("margin", "choice", "outer", "gloss column side: left | right | outer (right for ltr, left for rtl)",
      choices=("left", "right", "outer")),
    P("gloss_width", "float", 0.24, "gloss column width, share of the sheet width", min=0.05, max=0.5),
    P("gloss_size", "float", 0.45, "gloss word height, share of the body's", min=0.1, max=1.5),
    P("gloss_share", "float", 0.5, "share of rows that carry a gloss", min=0.0, max=1.0),
    P("bleed", "float", 0.15, "share of rows that run past the block into the sheet edge", min=0.0, max=1.0),
    *_ANNOT_PARAMS,
], doc="a page of writing: body voices in rows (interlinear), gloss voices in the margin, annotation")
def poly_page(ctx, parts, *, roles, columns, rows, words, interlinear, direction, justify, x_height, word_gap,
              margin, gloss_width, gloss_size, gloss_share, bleed, annotate, annotator, n_annot, annot_amp):
    a_idx = _annotator_index(parts, annotator, annotate)
    rl = roles.split()
    bad = [r for r in rl if r not in ("body", "gloss", "annot")]
    if bad:
        raise RecipeError(f"poly_page roles: unknown {bad} (body | gloss)")
    if not rl:
        rl = ["body"] + (["gloss"] if len(parts) > 1 else []) + ["body"] * max(len(parts) - 2, 0)
    rl = _fill(rl, len(parts), "body")
    body = [i for i in range(len(parts)) if rl[i] == "body" and i != a_idx]
    gloss = [i for i in range(len(parts)) if rl[i] == "gloss" and i != a_idx]
    if not body:
        raise RecipeError("poly_page needs at least one body part")
    rng = ctx.rng("page")
    x0, y0, W, H = ctx.box
    side = {"left": -1, "right": 1, "outer": 1 if direction == "ltr" else -1}[margin] if gloss else 0
    gw = gloss_width * W if gloss else 0.0
    bx0 = x0 + (gw if side < 0 else 0.0)
    bw = W - gw
    col_gap = 0.05 * bw if columns > 1 else 0.0
    cw = (bw - col_gap * (columns - 1)) / columns
    pitch = H / rows
    xh = x_height * pitch
    streams = {i: _word_stream(parts[i], words, ctx.box, ctx.rng("words", i)) for i in body + gloss}
    scales = {}

    def scale_for(i, target_h, first):
        if i not in scales:
            hs = [_native_size(pc)[1] for pc in first]
            scales[i] = target_h / max(float(np.median(hs)), 1e-9)
        return scales[i]

    peek = {}
    for i in body + gloss:
        peek[i] = [next(streams[i]) for _ in range(min(words, 12))]
    units, row_units, uid = [], [], 0
    rows_total = columns * rows
    for r in range(rows_total):
        col, rr = divmod(r, rows)
        voice_i = body[r % len(body)] if interlinear else body[min(r * len(body) // rows_total, len(body) - 1)]
        s = scale_for(voice_i, xh, peek[voice_i])
        base_y = y0 + (rr + 0.5) * pitch
        cx0 = bx0 + col * (cw + col_gap)
        runs_off = rng.random() < bleed and (col == columns - 1 if direction == "ltr" else col == 0)
        limit = cw + (2 * W if runs_off else 0.0)
        line, width = [], 0.0
        while True:
            pc = peek[voice_i].pop(0) if peek[voice_i] else next(streams[voice_i])
            n_ = _native_size(pc)
            k = s
            if n_[1] * k > 1.25 * pitch:
                k = 1.25 * pitch / n_[1]
            if n_[0] * k > 0.6 * cw:
                k = min(k, 0.6 * cw / n_[0])
            ww = n_[0] * k
            g = word_gap * pitch * (rng.uniform(0.6, 1.4))
            if line and width + g + ww > limit:
                break
            line.append((pc, k, ww, g if line else 0.0))
            width += (g if len(line) > 1 else 0.0) + ww
            if width > cw + 2 * W:
                break
        extra = (cw - width) / max(len(line) - 1, 1) if justify and not runs_off and width < cw else 0.0
        x = 0.0
        this_row = []
        for j, (pc, k, ww, g) in enumerate(line):
            x += g + (extra if j else 0.0)
            cxw = x + ww / 2
            cx = cx0 + cxw if direction == "ltr" else cx0 + cw - cxw
            placed = clip_marks(_at_native(pc, k, (cx, base_y)), ctx.box)
            x += ww
            if placed:
                u = Unit(uid, voice_i, placed, group=("row", r))
                units.append(u)
                this_row.append(u)
                uid += 1
        row_units.append(this_row)
    # glosses: beside rows, in the margin column
    if gloss:
        gx0 = x0 if side < 0 else x0 + W - gw
        for r in range(rows_total):
            if rng.random() >= gloss_share or not row_units[r]:
                continue
            col, rr = divmod(r, rows)
            gi = gloss[int(rng.integers(len(gloss)))]
            s = scale_for(gi, gloss_size * xh, peek[gi])
            pc = peek[gi].pop(0) if peek[gi] else next(streams[gi])
            n_ = _native_size(pc)
            k = min(s, 0.9 * gw / n_[0], 1.6 * pitch / n_[1])
            jitter = rng.uniform(-0.25, 0.25) * pitch
            cx = gx0 + gw / 2 + rng.uniform(-0.2, 0.2) * (gw - n_[0] * k)
            placed = clip_marks(_at_native(pc, k, (cx, y0 + (rr + 0.5) * pitch + jitter)), ctx.box)
            if placed:
                units.append(Unit(uid, gi, placed, group=("gloss", r)))
                uid += 1
    out = []
    for u in units:
        out += parts[u.part].modulate(u.marks, u.box)
    if a_idx is not None:
        targets = _page_targets(units, row_units, annotate, n_annot, rng)
        out += annotate_units(ctx, parts, units, a_idx, annotate, n_annot, annot_amp, targets=targets,
                                     gap=0.18 * pitch)
    return out


def _group(us, mode=None):
    lo = np.min([u.lo for u in us], axis=0)
    hi = np.max([u.hi for u in us], axis=0)
    return (lo, hi, us) if mode is None else (lo, hi, us, mode)


def _page_targets(units, row_units, mode, n, rng):
    """Page annotation targets: brackets span 2-4 rows, underlines/encircles
    take a run of 1-3 words, tethers start at glosses, echo/point take words."""
    rows = [r for r in row_units if r]
    glosses = [u for u in units if u.group and u.group[0] == "gloss"]
    out = []
    for j in range(n):
        md = mode
        if md == "mixed":
            md = _MIXABLE[int(rng.integers(len(_MIXABLE)))]
        if md == "bracket" and rows:
            k = int(rng.integers(2, 5))
            a = int(rng.integers(max(len(rows) - k, 0) + 1))
            out.append(_group([u for r in rows[a:a + k] for u in r], md))
        elif md == "tether" and glosses:
            out.append(_group([glosses[int(rng.integers(len(glosses)))]], md))
        elif md in ("underline", "encircle") and rows:
            r = rows[int(rng.integers(len(rows)))]
            k = int(rng.integers(1, 4))
            a = int(rng.integers(max(len(r) - k, 0) + 1))
            out.append(_group(r[a:a + k], md))
        elif units:
            out.append(_group([units[int(rng.integers(len(units)))]], md if md != "tether" else "echo"))
    return out
