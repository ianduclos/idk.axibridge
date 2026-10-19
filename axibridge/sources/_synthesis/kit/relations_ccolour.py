# FROZEN from research commit 071aea1: tools/gesture/gesture/kit/relations_ccolour.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""S2b (synthesis bench, 2026-10-19): the relations `ccolour` and `arch` kept inside themselves, as
registered relations a v2 score names (`writers_ccolour.py` writes the scores).

Geometry (grow, run when their dst is drawn, hearing earlier layers):

- `paste`   found_play's paste: a part (an unseen layer) laid into a rotated rectangle and cut to it
            (found matter), or kept whole, shrunk and moved inside the paper (ccolour's traverse).
- `answer`  call and response. `by: call` is found_play's: a line hears the most recent call (an
            earlier line's end in the air) within reach and, by `answer_p`, grows out of it (traces the
            caller's last stretch, converges on its end, bridges into its own hand) or refuses it.
            `by: stress` is the chorus (dev_chorus, arch's swell duet): the dst's stresses are
            re-decided so it speaks only where the src is quiet nearby.
- `catch`   found_play's walk of a made line over the found ground and the lines it listens to: R3
            entry (unless it answered), R4 curves listen, the catch (a contact infects the line with
            the river's bends, the chart's ruling and needles, or an earlier line's HAND, carried and
            shed whole), R2 exit motif, R1 weight (heavy over found, hairline in the blank; bold runs
            carry `own_pen` with the bold renderer). Channel `neg` keeps found_play's codes.
- `cover`   R5: a torn cover on the densest passage of what is on the sheet so far (its edge drawn).
- `steer`   arch's steering: a source's own turns, feature by feature, pulled from a to b (by way of
            `via`); with two sources and a `zone`, the second speaks inside the zone (the passer), in
            the zone layer's pen (pen by place). Optional `timing` (the danced traverse's tempo).
- `flicker` arch's limb signs: figures cut from a revisit_glyph host (the first src) surface at the
            emptiest stretch of a host line, in the host's pen.

Pens (contact, one relation instance sheet-wide, so `budget` is ccolour's per-sheet event budget):

- `carry`    a made line takes the LENDER's pen where it carries something of it: the river's bends
             (code 6), the chart's ruling and needles (7, 8), an earlier line's hand (9), the found
             contour its exit motif plays (5), the caller's last stretch it answers (10).
- `ride`     a made line takes the pen of the line it rides (code 1: found or made, the nearest).
- `reverse`  the found contour a line rode takes the LINE's pen back, over the stretch it was ridden.
- `contain`  a container stains what passes inside it with its own pen (inside only).
- `spill`    as contain, and a line keeps the stain for a while after leaving (ccolour's spill).
- `touch`    a traverse or counterweight that touches another line catches its pen (ccolour's
             "contact" event).
- `cover_cut` what lies under a cover is cut away: found matter always, made lines when the cover
             decided so (R5's break). Contact, src "*" → the cover layer.

Budgets as ccolour's: every lent run is at least `min_run` mm (a pen change is an event, never
confetti), at most `per_line` events per line (counted across every pen relation on that line),
`budget` (the score key) caps each relation sheet-wide, and a colour may lie (`p_lie`: it outlasts the
carrying by about `lie_mm`; `p_end`: to the line's end). Lent stretches are marks with
`own_pen: {"colour"}` (+ the bold renderer when the stretch was bold), so they render with their
layer's renderer and keep `lent` / `lent_ev` in meta.

Determinism: every draw comes from `rctx.rng(*tags)`; candidates are taken in mark order and arc
length. Fidelity to the composers (never bit parity) is noted in `writers_ccolour.py`.
"""
from __future__ import annotations

import hashlib
import math
from collections import OrderedDict

import numpy as np
from scipy.spatial import cKDTree

from ._relations import RelOut, cut, relation
from .arrangers_arch import _core_depth, steer as _steer, tokens, turns
from .arrangers_ccolour import LEGEND
from .arrangers_contagion import contagion_walk, river_grammar
from .arrangers_found_play import HAND_CODE, HAND_RIDE, _NEG, answer_bridge, chart_grammar, chart_needles, hand_gen
from .arrangers_oehlen_found import Ground, arclen, clip_rect, cover_polygon, rect_polygon, resample, rotate, tangents
from .arrangers_rules import _merge_short, _runs as _flag_runs, densest, entry, finish_line, turning  # noqa: F401
from .core import DEFAULT_CHANNELS, Mark, P, Part, get

LEND_CODES = {"river": (6,), "chart": (7, 8), "hand": (9,), "motif": (5,), "call": (10,)}
UNSEEN = "unseen"


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def _groups(marks) -> "OrderedDict[str, list]":
    """Marks by score layer, in order of first appearance (a list src arrives merged in its order)."""
    out: "OrderedDict[str, list]" = OrderedDict()
    for m in marks:
        out.setdefault(str(m.meta.get("score_layer", m.meta.get("layer", "?"))), []).append(m)
    return out


def _need(*groups) -> set:
    ms = [m for g in groups for m in g]
    return set.intersection(*(set(m.channels) for m in ms)) if ms else set()


def _fill(ch: dict, n: int, need) -> dict:
    out = {k: np.asarray(v, float) for k, v in ch.items()}
    for k in need:
        if k not in out:
            out[k] = np.full(n, float(DEFAULT_CHANNELS.get(k, 0.0)))
    return out


def _ink(m) -> str:
    """The pen a mark is inked in now: its own pen, else its layer's."""
    return (m.meta.get("own_pen") or {}).get("colour") or m.meta.get("colour") or "black"


def _lend_map(text: str) -> dict:
    """'F0=blue-400,M3=red' → {layer id: pen} (what a layer lends instead of its own pen)."""
    out = {}
    for part in (text or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _lend_of(lid, marks, lend: dict) -> str:
    return lend.get(lid) or (marks[0].meta.get("colour") if marks else None) or "black"


def _box(v, rctx, inset=0.0):
    """[x, y, w, h] from a param; empty = the sheet (inset)."""
    if v and len(v) >= 4:
        return tuple(float(x) for x in v[:4])
    W, H = rctx.frame
    return (inset, inset, W - 2 * inset, H - 2 * inset)


def _piece(m: Mark, s: np.ndarray, a: float, b: float, meta=None) -> Mark:
    inner = s[(s > a + 1e-9) & (s < b - 1e-9)]
    sn = np.concatenate([[a], inner, [b]])
    md = dict(meta or {})
    if "mid" in m.meta:
        md["mid_s0"] = float(m.meta.get("mid_s0", 0.0)) + float(a)
    return m.remap(sn, meta=md)


def _apply_spans(m: Mark, spans) -> list[Mark]:
    """Split m at arc-length spans [(a, b, meta)], the spans' pieces taking their meta (contiguous:
    neighbouring pieces share their boundary point)."""
    if not spans:
        return [m]
    s = m.arclength()
    L = float(s[-1])
    out, x = [], 0.0
    for a, b, md in sorted(spans, key=lambda t: t[0]):
        a, b = max(a, x), min(b, L)
        if b - a < 1e-6:
            continue
        if a - x > 1e-6:
            out.append(_piece(m, s, x, a))
        out.append(_piece(m, s, a, b, md))
        x = b
    if L - x > 1e-6:
        out.append(_piece(m, s, x, L))
    return [p for p in out if len(p) >= 2]


def _lent_meta(m: Mark, colour: str, kind: str, ev: str) -> dict:
    return {"own_pen": {**(m.meta.get("own_pen") or {}), "colour": colour}, "lent": kind, "lent_ev": ev}


def _events_on(marks) -> int:
    return len({m.meta.get("lent_ev") for m in marks if m.meta.get("lent_ev")})


def _stretch(rng, s, a_s, b_s, *, always_lie, p_lie, lie_mm, p_end, min_run, may_end=True):
    """ccolour's lie and settle on one stretch: a colour may outlast the carrying (or run to the end),
    and a lent run is at least min_run mm (grown forward, then backward)."""
    L = float(s[-1])
    lie = "none"
    r = float(rng.random())
    if always_lie or r < p_lie:
        extra = float(np.clip(rng.lognormal(math.log(max(lie_mm, 1.0)), 0.5), 8.0, 400.0))
        b_s = min(L, b_s + extra)
        lie = f"{extra:.0f} mm"
    if may_end and float(rng.random()) < p_end:
        b_s, lie = L, "to the end"
    if b_s - a_s < min_run:
        b_s = min(L, a_s + min_run)
        if b_s - a_s < min_run:
            a_s = max(0.0, b_s - min_run)
    return a_s, b_s, lie


_TREES: "OrderedDict[str, cKDTree]" = OrderedDict()


def _content_key(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        if isinstance(p, np.ndarray):
            h.update(np.ascontiguousarray(p, float).tobytes())
        else:
            h.update(repr(p).encode())
    return h.hexdigest()


def _layer_tree(marks, step: float = 0.5):
    """A KD tree over a layer's marks resampled at `step` (cached by content: deterministic)."""
    pts = [resample(np.asarray(m.points, float), step) for m in marks if len(m) >= 2]
    if not pts:
        return None
    P_ = np.vstack(pts)
    k = _content_key(P_)
    t = _TREES.get(k)
    if t is None:
        t = cKDTree(P_)
        _TREES[k] = t
        while len(_TREES) > 256:
            _TREES.popitem(last=False)
    else:
        _TREES.move_to_end(k)
    return t


def _nearest_layer(rctx, p, r, exclude=(), roles=None):
    """The ground layer nearest to point p within r (unseen layers and `exclude` never count)."""
    best, bd = None, float(r)
    for lid, ms in rctx.ground.items():
        if lid in exclude or not ms or ms[0].meta.get("of_role") == UNSEEN:
            continue
        if roles is not None and ms[0].meta.get("of_role") not in roles:
            continue
        t = _layer_tree(ms)
        if t is None:
            continue
        d, _ = t.query(p, distance_upper_bound=bd)
        if np.isfinite(d) and d < bd:
            best, bd = lid, float(d)
    return best


def _code_runs(marks, codes):
    """Runs of one code in channel `neg` (any of `codes`) along a line given as consecutive marks, numbered
    per code in order (a run that continues into the next mark is one run): [(k, mark index, a, b, code)],
    b inclusive."""
    out, count, carry = [], {}, None
    for i, m in enumerate(marks):
        if "neg" not in m.channels or len(m) < 2:
            carry = None
            continue
        c = np.asarray(m["neg"]).astype(int)
        cut_ = np.r_[0, np.flatnonzero(c[1:] != c[:-1]) + 1, len(c)]
        for a, b in zip(cut_[:-1], cut_[1:]):
            code = int(c[a])
            if code not in codes:
                continue
            if not (a == 0 and carry == code):
                count[code] = count.get(code, -1) + 1
            out.append((count[code], i, int(a), int(b) - 1, code))
        carry = int(c[-1])
    return out


def _poly_intervals(m: Mark, poly: np.ndarray, step: float = 0.2):
    """Arc-length intervals of m inside a closed polygon."""
    from shapely import contains_xy  # noqa: PLC0415
    from shapely.geometry import Polygon  # noqa: PLC0415
    L = m.length()
    if L <= 0:
        return []
    n = max(int(L / step), 2)
    sq = np.linspace(0, L, n + 1)
    s = m.arclength()
    q = np.column_stack([np.interp(sq, s, m.points[:, 0]), np.interp(sq, s, m.points[:, 1])])
    ins = contains_xy(Polygon(poly), q[:, 0], q[:, 1])
    out = []
    for a, b, v in _flag_runs(ins):
        if v:
            s0 = 0.0 if a == 0 else float(sq[a - 1] + sq[a]) / 2
            s1 = L if b >= len(sq) else float(sq[b - 1] + sq[b]) / 2
            out.append((s0, s1))
    return out


# ---------------------------------------------------------------------------
# paste
# ---------------------------------------------------------------------------

@relation("paste", phase="grow", params=[
    P("from_box", "floats", [], "the src part's own box [x, y, w, h] (its region)"),
    P("to", "floats", [], "where it lands: [cx, cy, w, h, angle°] (w/h at the src's aspect)"),
    P("mode", "choice", "clip", "clip: cut to the rotated rectangle (found matter) | whole: kept whole, shrunk "
      "and moved inside `bounds` (a traverse) | keep: unchanged (a placeholder for a locked layer)",
      choices=("clip", "whole", "keep")),
    P("bounds", "floats", [], "the paper's inner box [x, y, w, h] (empty = the sheet less 5 mm)"),
    P("min_stub", "float", 4.0, "clip: a piece the rectangle shortened below this is dropped, mm", min=0.0, max=50.0),
    P("inner_stub", "float", 3.0, "clip: same, at the paper's inner box, mm", min=0.0, max=50.0),
    P("text_mm", "float", 5.0, "clip: pieces smaller than this are lettering (never ridden, never cut short)",
      min=0.0, max=30.0),
    P("kind", "choice", "printed", "what the found matter is (catch and carry read it)",
      choices=("river", "chart", "printed", "line")),
], doc="found_play's paste: a part laid into a rotated rectangle and cut to it, or kept whole inside the paper")
def paste(rctx, src, dst, *, from_box, to, mode, bounds, min_stub, inner_stub, text_mm, kind):
    if mode == "keep" or not src or len(to) < 5 or len(from_box) < 4:
        return RelOut()
    need = _need(src)
    fx, fy, fw, fh = from_box[:4]
    cx, cy, w, h, ang = to[:5]
    k = w / max(fw, 1e-9)
    bx = _box(bounds, rctx, 5.0)
    out, events = [], []
    if mode == "clip":
        rect = rect_polygon(cx, cy, w, h, ang)
        inner = rect_polygon(bx[0] + bx[2] / 2, bx[1] + bx[3] / 2, bx[2], bx[3], 0.0)
        for m in src:
            q = (np.asarray(m.points, float) - [fx, fy]) * k + [cx - w / 2, cy - h / 2]
            q = rotate(q, np.array([cx, cy]), ang)
            for piece in clip_rect([q], rect, min_stub):
                ext = float(np.linalg.norm(piece.max(axis=0) - piece.min(axis=0)))
                txt = ext < text_mm
                for p2 in ([piece] if txt else clip_rect([piece], inner, inner_stub)):
                    out.append(Mark(p2, _fill({}, len(p2), need), {"found_kind": kind, "text": bool(txt)}))
        events.append({"outcome": "pasted", "at": [cx, cy], "angle": ang, "pieces": len(out)})
    else:
        qs = []
        for m in src:
            u = (np.asarray(m.points, float) - [fx, fy]) * k
            qs.append(rotate(u - [w / 2, h / 2], np.zeros(2), ang) + [cx, cy])
        if not qs:
            return RelOut()
        allq = np.vstack(qs)
        lo, hi = allq.min(axis=0), allq.max(axis=0)
        x0, y0, bw, bh = bx
        f = min(1.0, (bw - 4.0) / max(hi[0] - lo[0], 1e-9), (bh - 4.0) / max(hi[1] - lo[1], 1e-9))
        mid = (lo + hi) / 2
        qs = [(q - mid) * f + mid for q in qs]
        allq = np.vstack(qs)
        lo, hi = allq.min(axis=0), allq.max(axis=0)
        blo, bhi = np.array([x0 + 2.0, y0 + 2.0]), np.array([x0 + bw - 2.0, y0 + bh - 2.0])
        shift = np.clip(blo - lo, 0, None) - np.clip(hi - bhi, 0, None)
        for m, q in zip(src, qs):
            if len(q) >= 2:
                out.append(m.evolve(points=q + shift, meta={"found_kind": kind}))
        events.append({"outcome": "laid", "at": [cx, cy], "angle": ang, "shrunk": round(float(f), 3)})
    return RelOut(dst=list(dst) + out, events=events)


# ---------------------------------------------------------------------------
# answer: found_play's call and response, and the chorus
# ---------------------------------------------------------------------------

@relation("answer", phase="grow", params=[
    P("by", "choice", "call", "call: grow out of the last call heard (found_play) | stress: speak only where the "
      "src is quiet nearby (the chorus)", choices=("call", "stress")),
    P("answer_p", "float", 0.6, "call: chance the line takes the call (else it refuses it)", min=0.0, max=1.0),
    P("call_reach", "float", 90.0, "call: a line's end in the air is heard this far, mm", min=0.0, max=400.0),
    P("trace_mm", "float", 18.0, "call: the answer traces the caller's last stretch this long, mm", min=2.0,
      max=200.0),
    P("ride_gap", "float", 0.9, "call: the trace starts this far beside the caller (×2, closing), mm", min=0.0,
      max=5.0),
    P("step", "float", 0.3, "call: resampling step, mm", min=0.1, max=1.0),
    P("box", "floats", [], "call: the line's own box [x, y, w, h] it may move inside (empty = the sheet)"),
    P("bounds", "floats", [], "call: the paper's inner box (empty = the sheet less 5 mm)"),
    P("listen_by", "choice", "space", "stress: hear what passes near (space) or along the course (time)",
      choices=("space", "time")),
    P("radius", "float", 15.0, "stress: how near the other voice is heard, mm", min=0.5, max=200.0),
    P("answer", "float", 0.8, "stress: bonus for a stress beside a quiet passage", min=0.0, max=5.0),
    P("delay", "float", 0.05, "stress (time): how long after a call the reply may come", min=0.0, max=0.5),
    P("window", "float", 0.012, "stress (time): quiet margin either side", min=0.0, max=0.2),
], doc="call and response: grow out of an earlier line's end in the air (or refuse it), or stress only where "
       "the other voice is quiet (the chorus)")
def answer(rctx, src, dst, *, by, answer_p, call_reach, trace_mm, ride_gap, step, box, bounds, listen_by, radius,
           answer, delay, window):
    if not src or not dst:
        return RelOut()
    if by == "stress":
        from .dev_chorus import _heard  # noqa: PLC0415
        from .prosody_arrangers import answer_mark  # noqa: PLC0415
        lead = [_heard(m) for m in src]
        out, events = [], []
        for i, m in enumerate(dst):
            if "prosody" not in m.meta:
                out.append(m)
                continue
            q, info = answer_mark(m, lead, listen_by=listen_by, radius=radius, answer=answer, delay=delay,
                                  window=window)
            out.append(q.evolve(meta={"chorus": {"listens_to": rctx.src, **info}}))
            events.append({"outcome": "answer", "mark": i, "by": "stress",
                           **{k: v for k, v in info.items() if isinstance(v, (int, float, str))}})
        return RelOut(dst=out, events=events)

    m0 = dst[0]
    need = _need(src, dst)
    M = resample(np.asarray(m0.points, float), step)
    if len(M) < 4:
        return RelOut()
    R_mm = float(arclen(M)[-1]) / max(float(m0.meta.get("length_R", 3.0)), 0.2)
    groups = _groups(src)
    call_id = None
    for lid in reversed(list(groups)):              # the most recent line listened to whose end is in earshot
        e = groups[lid][-1].points[-1]
        if min(float(np.linalg.norm(M[0] - e)), float(np.linalg.norm(M[-1] - e))) <= call_reach:
            call_id = lid
            break
    if call_id is None:
        return RelOut()
    rng = rctx.rng("answer")
    cpts = np.vstack([m.points for m in groups[call_id]])
    e = cpts[-1]
    if float(rng.random()) >= answer_p:
        return RelOut(events=[{"outcome": "refuse", "at": [float(e[0]), float(e[1])], "to": call_id}])
    bx = _box(box, rctx)
    bd = _box(bounds, rctx, 5.0)
    bnds = (bd[0], bd[1], bd[0] + bd[2], bd[1] + bd[3])
    if np.linalg.norm(M[-1] - e) < np.linalg.norm(M[0] - e):
        M = M[::-1].copy()
    cp = resample(cpts, step)
    k = max(int(round(min(trace_mm, (len(cp) - 1) * step) / step)), 3)
    tail = cp[-k - 1:]
    t = tangents(tail, 3)
    gap = 2 * ride_gap * (1 - np.linspace(0, 1, len(tail)))
    tail = tail + gap[:, None] * np.c_[-t[:, 1], t[:, 0]]
    tip = tail[-1].copy()
    forward = min(8.0, trace_mm / 2)
    lo, hi = np.array(bnds[:2]), np.array(bnds[2:])
    for ax in range(2):
        if abs(t[-1, ax]) > 1e-9:
            edge = hi[ax] if t[-1, ax] > 0 else lo[ax]
            forward = min(forward, max(0.0, 0.8 * (edge - tip[ax]) / t[-1, ax]))
    ext = resample(np.array([tip, tip + t[-1] * forward]), step)
    tail = np.vstack([tail, ext[1:]])
    want = tail[-1] + t[-1] * 6.0 - M[0]
    blo, bhi = np.array(bx[:2]), np.array(bx[:2]) + bx[2:]
    for f in (1.0, 0.7, 0.45, 0.25, 0.0):
        Mt = M + f * want * min(1.0, 60.0 / max(float(np.linalg.norm(want)), 1e-9))
        if np.all(Mt.min(axis=0) >= blo - 1e-6) and np.all(Mt.max(axis=0) <= bhi + 1e-6):
            M = Mt
            break
    br = answer_bridge(tail[-1], t[-1], M[0], tangents(M, 3)[0], step, bnds)
    pre = np.vstack([tail, br]) if len(br) else tail
    pts = np.vstack([pre, M])
    neg = np.r_[np.full(len(pre), 10.0), np.zeros(len(M))]
    mk = Mark(pts, _fill({"neg": neg}, len(pts), need),
              {**m0.meta, "answers": call_id, "R_mm": R_mm, "answer_info": {"answers": call_id}})
    s_pre = float(arclen(pre)[-1])
    return RelOut(dst=[mk] + list(dst[1:]),
                  events=[{"outcome": "answer", "at": [float(tail[0][0]), float(tail[0][1])], "to": call_id,
                           "mark": 0, "s": [0.0, s_pre], "root": [float(tip[0]), float(tip[1])]}])


# ---------------------------------------------------------------------------
# catch: found_play's walk of one made line
# ---------------------------------------------------------------------------

_FOUND: "OrderedDict[str, dict]" = OrderedDict()


def _found_ground(fgroups, step, region_pad, exit_pad, river_axis, omega_max, spike_space, o):
    """The found matter as found_play sees it (cached by content): the Ground, owners and kinds, the
    R1 / R2 regions and the grammars a contact can catch."""
    from shapely import contains_xy  # noqa: PLC0415
    from shapely.geometry import MultiLineString  # noqa: PLC0415
    lines, kinds = [], {}
    for pi, (lid, ms) in enumerate(fgroups.items()):
        kinds[pi] = str(ms[0].meta.get("found_kind") or "printed")
        for m in ms:
            if len(m) >= 2:
                lines.append((pi, np.asarray(m.points, float) - o, bool(m.meta.get("text"))))
    key = _content_key(step, region_pad, exit_pad, river_axis, omega_max, spike_space, sorted(kinds.items()),
                       *[x for pi, l, t in lines for x in (pi, t, l)])
    hit = _FOUND.get(key)
    if hit is not None:
        _FOUND.move_to_end(key)
        return hit
    ridable = [(pi, l) for pi, l, txt in lines if not txt]
    G = Ground([l for _, l in ridable], step, tag=1)
    owner = [pi for pi, l in ridable if len(l) >= 2 and arclen(l)[-1] > 4 * step]

    def pads(r):
        out = []
        for pi in kinds:
            ls = [l for q, l, txt in lines if q == pi and not txt and len(l) >= 2]
            if ls:
                out.append((pi, MultiLineString([x.tolist() for x in ls]).buffer(r, 8)))
        return out

    def regions(pp):
        def f(points):
            reg = np.full(len(points), -1)
            for pi, poly in pp:
                hit_ = contains_xy(poly, points[:, 0], points[:, 1])
                reg[(reg < 0) & hit_] = pi
            return reg
        return f
    river = [l for pi, l in ridable if kinds[pi] == "river"]
    chart = [l for pi, l in ridable if kinds[pi] == "chart" and arclen(l)[-1] > 30.0]
    grounds, grammars = {}, {}
    if river:
        try:
            grammars["river"] = river_grammar(river, axis_mm=river_axis, omega_max=omega_max)
            grounds["river"] = Ground(river, step, tag=1)
        except ValueError:
            pass
    tick_pitch = 6.3
    if chart:
        grammars["plate"] = chart_grammar(chart)
        tick_pitch = grammars["plate"]["pitch_mm"] * spike_space
        grounds["plate"] = Ground(chart, step, tag=2)
    out = {"lines": lines, "G": G, "owner": owner, "kinds": kinds, "r1": regions(pads(region_pad)),
           "r2": regions(pads(exit_pad)), "grounds": grounds, "grammars": grammars, "tick_pitch": tick_pitch,
           "ids": list(fgroups)}
    _FOUND[key] = out
    while len(_FOUND) > 16:
        _FOUND.popitem(last=False)
    return out


@relation("catch", phase="grow", params=[
    P("rules", "str", "R1,R2,R3,R4", "which of found_play's rules are in play (R5, the cover, is a layer)"),
    P("breaks", "bool", True, "rules may break"),
    P("catches", "int", 4, "most contacts (infections) per line", min=0, max=20),
    P("ride", "float", 18.0, "mean contact ride, mm", min=1.0, max=200.0),
    P("bold_pen", "float", 0.9, "R1: heavy pen over the found, mm", min=0.05, max=3.0),
    P("hair_pen", "float", 0.3, "R1: hairline pen in the blank, mm (the layer's own renderer should match)",
      min=0.05, max=3.0),
    P("inset", "float", 4.0, "R3: the edge is this far inside the composer's frame, mm", min=0.0, max=40.0),
    P("frame_box", "floats", [], "the composer's frame [x, y, w, h] (its edges, for R3); empty = the sheet"),
    P("bounds", "floats", [], "the paper's inner box [x, y, w, h] (empty = the sheet less 5 mm)"),
    P("legend", "bool", False, "ink every code in its fixed pen (the round-13 diagnostic map, ccolour's dud)"),
], doc="found_play's walk: a made line enters (R3), is taken only where it curves (R4), catches the river's "
       "bends, the chart's ruling or an earlier line's hand, carries them and sheds them whole, exits with the "
       "found contour's motif (R2) and is heavy over the found (R1)")
def catch(rctx, src, dst, *, rules, breaks, catches, ride, bold_pen, hair_pen, inset, frame_box, bounds, legend):
    if not dst:
        return RelOut()
    fp = get("arranger", "found_play").defaults()
    step = fp["step"]
    on = {r.strip() for r in rules.split(",") if r.strip()}
    W, H = rctx.frame
    F = _box(frame_box, rctx)
    o = np.array(F[:2], float)
    bd = _box(bounds, rctx, 5.0)
    bnds = (bd[0] - o[0], bd[1] - o[1], bd[0] + bd[2] - o[0], bd[1] + bd[3] - o[1])
    need = _need(src, dst)
    groups = _groups(src)
    fgroups = OrderedDict((k, v) for k, v in groups.items() if v[0].meta.get("of_role") == "found")
    heard = [k for k, v in groups.items() if k not in fgroups and v[0].meta.get("hand")]
    fg = _found_ground(fgroups, step, fp["region_pad"], fp["exit_pad"], fp["river_axis"], fp["omega_max"],
                       fp["spike_space"], o)
    G, owner, kinds = fg["G"], fg["owner"], fg["kinds"]

    m0 = dst[0]
    pts0 = np.asarray(m0.points, float) - o
    neg0 = np.asarray(m0.channels["neg"]).astype(int) if "neg" in m0.channels else np.zeros(len(pts0), int)
    k_pre = int(np.argmax(neg0 != 10)) if np.any(neg0 != 10) else len(neg0)
    pre = pts0[:k_pre] if k_pre else None
    M = resample(pts0[k_pre:] if k_pre else pts0, step)
    if len(M) < 4:
        return RelOut()
    length_R = float(m0.meta.get("length_R", 3.0))
    R_mm = float(m0.meta.get("R_mm") or float(arclen(M)[-1]) / max(length_R, 0.2))
    hand_id = m0.meta.get("hand") or (m0.meta.get("voices") or [None])[0]
    rng = rctx.rng("line")
    log: list[dict] = []
    pre_tag, info = 10.0, dict(m0.meta.get("answer_info") or {})
    if pre is None and "R3" in on:
        pieces, M, info = entry(M, G, owner, kinds, rng, frame=(F[2], F[3]), box=(bnds[0], bnds[1], bnds[2] - bnds[0],
                                bnds[3] - bnds[1]), step=step, inset=inset, grow_reach=fp["grow_reach"],
                                breaks=breaks, ride=ride, ride_gap=fp["ride_gap"], line_id=rctx.dst, log=log)
        if pieces:
            pre, pre_tag = pieces[0][0][:-1], float(pieces[0][1])
    M = resample(M, step)
    listen_win = fp["listen_win"]
    k_own = turning(M, step, listen_win)
    gr, gm_ = dict(fg["grounds"]), dict(fg["grammars"])
    fl = {"river": fp["full_river"], "plate": fp["full_chart"]}
    dc = {"river": fp["decay_river"], "plate": fp["decay_chart"]}
    kf = {r: [turning(l, step, listen_win) for l in Gr.lines] for r, Gr in gr.items()}
    for j, lid in enumerate(heard):
        ms = groups[lid]
        h = ms[0].meta.get("hand")
        Rs = float(ms[0].meta.get("R_mm") or 30.0)
        key = f"line{j}"
        gr[key] = Ground([np.asarray(m.points, float) - o for m in ms if len(m) >= 2], step, tag=3)
        if not gr[key].lines:
            gr.pop(key)
            continue
        kf[key] = [turning(l, step, listen_win) for l in gr[key].lines]
        gm_[key] = {"gen": hand_gen(rctx.use("hand", h), Rs * fp["hand_scale"], step=0.2, pull=fp["hand_pull"],
                                    axis_mm=fp["river_axis"], amp_max=fp["hand_amp"]),
                    "code": HAND_CODE, "ride_code": HAND_RIDE, "hand": h}
        fl[key], dc[key] = fp["full_hand"], fp["decay_hand"]

    def gate(i, reg, j, i0, c, k_own=k_own, kf=kf):
        if "R4" not in on:
            return True
        i = min(i, len(k_own) - 1)
        if k_own[i] >= fp["listen_k"]:
            return True
        return bool(breaks and k_own[i] < fp["straight_k"] and kf[reg][j][min(i0, len(kf[reg][j]) - 1)]
                    < fp["straight_k"] and abs(c) >= 0.985)
    pts, codes, lg = contagion_walk(
        M, gr, gm_, rng, step=step, capture=fp["capture"], align=fp["align"], listen=1e6, ignore=0.0, ride=ride,
        ride_sd=fp["ride_sd"], min_ride=fp["min_ride"], ride_gap=fp["ride_gap"], return_mm=fp["return_mm"],
        ramp=fp["ramp"], max_offset=fp["max_offset"], catches=catches, full=fl, decay=dc,
        tick_linger=fp["tick_linger"], own_mm=fp["own_mm"], rule_tol=fp["rule_tol"], snap=fp["snap"],
        tick_pitch=fg["tick_pitch"], immune_mm=fp["immune_mm"], omega_max=fp["omega_max"],
        rule_shared=fp["rule_shared"], regimes=tuple(gr), carry=True, gate=gate)
    if "plate" in fg["grammars"]:
        pts = chart_needles(pts, codes, fg["grammars"]["plate"])
    tags = np.array([_NEG.get(int(c), 0.0) for c in codes])
    events, caught = [], []
    for inf in lg["infections"]:
        reg = inf["regime"]
        if reg.startswith("line"):
            who = heard[int(reg[4:])]
            caught.append(who)
        else:
            who = next((fg["ids"][pi] for pi, kd in kinds.items() if kd == {"river": "river", "plate": "chart"}[reg]),
                       reg)
        c = np.asarray(inf["contact"], float) + o
        events.append({"outcome": "catch", "at": [float(c[0]), float(c[1])], "caught": who,
                       "what": {"river": "river", "plate": "chart"}.get(reg, "hand"),
                       "carried_mm": inf["carried_mm"], "mark": 0})
    if pre is not None and len(pre):
        pts = np.vstack([pre, pts])
        tags = np.r_[np.full(len(pre), pre_tag), tags]
    d = {"pts": pts, "tags": tags, "rides": [], "part": 0, "info": info, "line": rctx.dst, "hand": hand_id}
    finish_line(d, on=on, G=G, owner=owner, found_kind=kinds, r1_region=fg["r1"], r2_region=fg["r2"], rng=rng,
                step=step, motif_len=fp["motif_len"], lead=fp["lead"], sigma=fp["sigma"],
                motif_scale=fp["motif_scale"], bounds=bnds, breaks=breaks, log=log, loops_r=fp["loops_r"],
                loops_p=fp["loops_p"], min_run=fp["min_run"], carry_min=fp["carry_min"], carry_k=fp["carry_k"])
    needle = d["tags"] == 8
    needle[:-1] |= needle[1:]
    if breaks and np.any(needle & d["bold"]) and "R1" in on:
        i = int(np.flatnonzero(needle & d["bold"])[0])
        log.append({"rule": "R1", "event": "break", "xy": [float(x) for x in d["pts"][i]],
                    "why": "the caught chart keeps its thin needles over the found"})
    d["bold"][needle] = False
    for e in log:
        xy = np.asarray(e.get("xy", [0.0, 0.0]), float) + o
        events.append({"outcome": f"{e['rule']}_{e['event']}", "at": [float(xy[0]), float(xy[1])],
                       "why": e.get("why", "")})
    motif_from = None
    if d.get("motif") and d["motif"].get("src_part") is not None:
        sp = d["motif"]["src_part"]
        motif_from = fg["ids"][sp] if isinstance(sp, (int, np.integer)) and 0 <= sp < len(fg["ids"]) else None
    P_ = d["pts"] + o
    s_all = arclen(P_)
    meta = {**{k: v for k, v in m0.meta.items() if k not in ("answer_info",)},
            "hand": hand_id, "R_mm": R_mm, "caught": caught, "heard": heard, "motif_from": motif_from}
    out = []
    for a, b, v in _flag_runs(d["bold"]):
        e = min(b + 1, len(P_))
        if e - a < 2:
            continue
        q, qt = P_[a:e], d["tags"][a:e]
        md = {**meta, "bold": bool(v), "pen_mm": float(bold_pen if v else hair_pen), "mid_s0": float(s_all[a])}
        if v:
            md["own_pen"] = {"colour": meta.get("colour", "black"), "renderer": {"id": "wire", "pen": float(bold_pen)}}
        mk = Mark(q, _fill({"neg": qt, "bold": np.full(len(q), float(v))}, len(q), need), md)
        if legend:
            col = np.array([LEGEND.get(int(c), "black") for c in qt], dtype=object)
            cuts = np.r_[0, np.flatnonzero(col[1:] != col[:-1]) + 1, len(col)]
            s = mk.arclength()
            spans = [(float(s[x]), float(s[min(y, len(s) - 1)]),
                      {"own_pen": {**(md.get("own_pen") or {}), "colour": str(col[x])}})
                     for x, y in zip(cuts[:-1], cuts[1:])]
            out += _apply_spans(mk, spans)
        else:
            out.append(mk)
    return RelOut(dst=out + list(dst[1:]), events=events)


# ---------------------------------------------------------------------------
# R5 cover, and what lies under it
# ---------------------------------------------------------------------------

@relation("cover", phase="grow", params=[
    P("wh", "floats", [24.0, 72.0], "cover width, height, mm"),
    P("tilt", "float", 8.0, "tilt ± deg", min=0.0, max=60.0),
    P("margin", "float", 14.0, "the cover keeps this far inside the composer's frame, mm", min=0.0, max=80.0),
    P("made_share", "float", 0.45, "break: when the densest passage is this share made ink, it cuts the made "
      "lines too", min=0.0, max=1.0),
    P("breaks", "bool", True, "the rule may break"),
    P("frame_box", "floats", [], "the composer's frame [x, y, w, h]; empty = the sheet"),
], doc="R5: a torn cover lands on the densest passage of what is on the sheet so far; its edge is drawn")
def cover(rctx, src, dst, *, wh, tilt, margin, made_share, breaks, frame_box):
    F = _box(frame_box, rctx)
    o = np.array(F[:2], float)
    need = _need(src, dst)
    by = {"found": [], "made": []}
    for m in src:
        role = "found" if m.meta.get("of_role") == "found" else "made"
        by[role].append(np.asarray(m.points, float) - o)
    w, h = (list(wh) + [34.0, 50.0])[:2]
    res = densest(by, (F[2], F[3]), w, h, margin)
    if res is None:
        return RelOut()
    c, _, share = res
    poly = cover_polygon(rctx.rng("cover"), c, w, h, "torn", tilt) + o
    cuts_made = bool(breaks and share >= made_share)
    mk = Mark(poly, _fill({}, len(poly), need), {"cover": True, "cuts_made": cuts_made})
    cc = np.asarray(c, float) + o
    return RelOut(dst=list(dst) + [mk], events=[{"outcome": "cover_break" if cuts_made else "cover",
                                                 "at": [float(cc[0]), float(cc[1])],
                                                 "made_share": round(float(share), 2)}])


@relation("cover_cut", phase="contact", params=[
    P("min_stub", "float", 4.0, "a piece the cover shortened below this is dropped, mm", min=0.0, max=50.0),
    P("later", "bool", False, "also cut lines drawn after the cover (found_play's cover lands on what is there)"),
], doc="what lies under a cover is cut away: found matter always (lettering whole), made lines when the cover "
       "broke its rule")
def cover_cut(rctx, src, dst, *, min_stub, later):
    polys = [m for m in dst if m.meta.get("cover")]
    if not polys or not src:
        return RelOut()
    if not later and list(rctx.ground)[-1] != rctx.dst:       # a later layer: the cover is under it, not over it
        return RelOut()
    from shapely.geometry import LineString, Polygon  # noqa: PLC0415
    cuts_made = any(m.meta.get("cuts_made") for m in polys)
    out, events, changed = [], [], False
    for i, m in enumerate(src):
        role = m.meta.get("of_role")
        if role != "found" and not (cuts_made and role == "made"):
            out.append(m)
            continue
        if m.meta.get("text"):
            if any(LineString(m.points).intersects(Polygon(p.points)) for p in polys):
                changed = True
                events.append({"outcome": "cut", "mark_src": i, "at": [float(x) for x in m.points[0]], "whole": True})
                continue
            out.append(m)
            continue
        iv = [x for p in polys for x in _poly_intervals(m, p.points)]
        if not iv:
            out.append(m)
            continue
        changed = True
        out += [q for q in cut(m, iv, min_piece=min_stub) if q.length() >= min(min_stub, m.length())]
        a, b = iv[0]
        events.append({"outcome": "cut", "mark_src": i, "s_src": [a, b],
                       "at": [float(np.interp(a, m.arclength(), m.points[:, 0])),
                              float(np.interp(a, m.arclength(), m.points[:, 1]))]})
    return RelOut(src=out, events=events) if changed else RelOut()


# ---------------------------------------------------------------------------
# pens: carry, ride, reverse, contain / spill, touch
# ---------------------------------------------------------------------------

_LEND_PARAMS = [
    P("p", "float", 0.6, "chance each candidate stretch is taken up (the sheet's budget and per_line cap the rest)",
      min=0.0, max=1.0),
    P("per_line", "int", 2, "at most this many pen events on one line (counted across every pen relation)",
      min=1, max=12),
    P("min_run", "float", 14.0, "a lent run is at least this long, mm", min=0.0, max=200.0),
    P("p_lie", "float", 0.35, "chance the colour outlasts the stretch that earned it", min=0.0, max=1.0),
    P("lie_mm", "float", 40.0, "how long a lie lasts (log-normal about this), mm", min=1.0, max=400.0),
    P("p_end", "float", 0.0, "chance the lent colour runs to the line's end", min=0.0, max=1.0),
    P("lend", "str", "", "what a layer lends instead of its own pen: 'F0=blue-400,M3=red' (a latent pen)"),
]


def _lend_params(kw):
    return {k: kw[k] for k in ("p", "per_line", "min_run", "p_lie", "lie_mm", "p_end")}


def _take(rctx, cands, marks, kind, lp, *, always_lie=False, may_end=True):
    """Fire candidates [(mark index, a_s, b_s, colour, extra event fields)] in order, within the budget and
    the per-line cap; returns (new marks, events)."""
    rng = rctx.rng(kind)
    left = rctx.remaining()
    room = lp["per_line"] - _events_on(marks)
    spans: dict[int, list] = {}
    events = []
    n = 0
    for i, a_s, b_s, colour, extra in cands:
        u = float(rng.random())
        if room <= 0 or (left is not None and left <= 0):
            break
        if u >= lp["p"]:
            continue
        s = marks[i].arclength()
        a2, b2, lie = _stretch(rng, s, a_s, b_s, always_lie=always_lie, p_lie=lp["p_lie"], lie_mm=lp["lie_mm"],
                               p_end=lp["p_end"], min_run=lp["min_run"], may_end=may_end)
        if any(not (b2 <= x or a2 >= y) for x, y, _ in spans.get(i, [])):
            continue
        ev = f"{rctx.rid}:{rctx.src}>{rctx.dst}:{n}"
        n += 1
        spans.setdefault(i, []).append((a2, b2, _lent_meta(marks[i], colour, kind, ev)))
        at = [float(np.interp(a2, s, marks[i].points[:, 0])), float(np.interp(a2, s, marks[i].points[:, 1]))]
        events.append({"outcome": kind, "pen": colour, "at": at, "s": [a2, b2], "mark": i, "lie": lie, **extra})
        room -= 1
        if left is not None:
            left -= 1
    if not events:
        return None, []
    out = []
    for i, m in enumerate(marks):
        out += _apply_spans(m, spans[i]) if i in spans else [m]
    return out, events


@relation("carry", phase="contact", params=[
    P("what", "str", "river,chart,hand,motif,call", "what carried lends its pen: river (code 6), chart (7, 8), "
      "an earlier line's hand (9), the found contour an exit motif plays (5), the caller an answer traces (10)"),
    *_LEND_PARAMS,
], doc="a made line takes the lender's pen for the stretch it carries something of it (ccolour's carry)")
def carry(rctx, src, dst, **kw):
    if not src or not dst or dst[0].meta.get("of_role") != "made":
        return RelOut()
    lend = _lend_map(kw["lend"])
    s_id = rctx.src
    pen = _lend_of(s_id, src, lend)
    mine = dst[0].meta.get("colour")
    if pen == mine:
        return RelOut()
    what = {w.strip() for w in kw["what"].split(",") if w.strip()}
    codes = sorted({c for w in what for c in LEND_CODES.get(w, ())})
    src_kind = src[0].meta.get("found_kind") if src[0].meta.get("of_role") == "found" else None
    caught = list(dst[0].meta.get("caught") or [])
    heard = list(dst[0].meta.get("heard") or [])
    cands = []
    for k, i, a, b, code in _code_runs(dst, codes):
        if b - a < 2:
            continue
        m = dst[i]
        if code in (6, 7, 8):
            ok = src_kind == ("river" if code == 6 else "chart")
            why = "carries the river" if code == 6 else "carries the chart"
        elif code == 9:                      # the k-th caught hand, in the order the line caught them
            who = caught[k] if k < len(caught) else (heard[-1] if heard else None)
            ok, why = who == s_id, f"carries {s_id}'s hand"
        elif code == 5:
            who = m.meta.get("motif_from") or _nearest_layer(rctx, m.points[a], 8.0, exclude=(rctx.dst,),
                                                             roles=("found",))
            ok, why = who == s_id, "plays the found contour it left"
        else:
            ok, why = m.meta.get("answers") == s_id, f"answers {s_id}"
        if ok:
            s = m.arclength()
            what = next(w for w, cs in LEND_CODES.items() if code in cs)
            cands.append((i, float(s[a]), float(s[b]), pen, {"why": why, "code": code, "what": what}))
    out, events = _take(rctx, cands, list(dst), "carry", _lend_params(kw))
    return RelOut(dst=out, events=events) if out is not None else RelOut()


@relation("ride", phase="contact", params=[
    P("reach", "float", 2.5, "the ridden line is the nearest within this, mm", min=0.2, max=10.0),
    *_LEND_PARAMS,
], doc="a made line takes the pen of the line it rides, for the ride (ccolour's ride)")
def ride(rctx, src, dst, *, reach, **kw):
    if not src or not dst or dst[0].meta.get("of_role") != "made":
        return RelOut()
    pen = _lend_of(rctx.src, src, _lend_map(kw["lend"]))
    if pen == dst[0].meta.get("colour"):
        return RelOut()
    cands = []
    for k, i, a, b, code in _code_runs(dst, (1,)):
        if b - a < 2:
            continue
        m = dst[i]
        mid = (a + b) // 2
        if _nearest_layer(rctx, m.points[mid], reach, exclude=(rctx.dst,)) != rctx.src:
            continue
        s = m.arclength()
        cands.append((i, float(s[a]), float(s[b]), pen, {"why": f"rides {rctx.src}"}))
    out, events = _take(rctx, cands, list(dst), "ride", _lend_params(kw))
    return RelOut(dst=out, events=events) if out is not None else RelOut()


@relation("reverse", phase="contact", params=[
    P("reach", "float", 2.5, "the ridden contour is the nearest found within this, mm", min=0.2, max=10.0),
    P("near", "float", 2.0, "the contour takes the pen back where the rider passed this close, mm", min=0.2,
      max=10.0),
    *_LEND_PARAMS,
], doc="the reverse borrow: a found contour a made line rode takes the line's pen back, where it was ridden")
def reverse(rctx, src, dst, *, reach, near, **kw):
    if not src or not dst or src[0].meta.get("of_role") != "found" or dst[0].meta.get("of_role") != "made":
        return RelOut()
    back = _lend_of(rctx.dst, dst, _lend_map(kw["lend"]))
    if back == src[0].meta.get("colour"):
        return RelOut()
    cands = []
    seen = set()
    for k, i, a, b, code in _code_runs(dst, (1,)):
        m = dst[i]
        if b - a < 2 or _nearest_layer(rctx, m.points[(a + b) // 2], reach, exclude=(rctx.dst,),
                                       roles=("found",)) != rctx.src:
            continue
        seg = cKDTree(np.asarray(m.points[a:b + 1], float))
        for j, f in enumerate(src):
            if len(f) < 2 or f.meta.get("text"):
                continue
            d, _ = seg.query(np.asarray(f.points, float))
            sf = f.arclength()
            for ra, rb, v in _flag_runs(d < near):
                if v and sf[rb - 1] - sf[ra] > 4.0 and (j, ra) not in seen:
                    seen.add((j, ra))
                    cands.append((j, float(sf[ra]), float(sf[rb - 1]), back,
                                  {"why": f"{rctx.src} takes back {rctx.dst}'s pen"}))
    cands.sort(key=lambda c: (c[0], c[1]))
    out, events = _take(rctx, cands, list(src), "reverse", _lend_params(kw), may_end=False)
    for e in events:            # the stretch lies on the src: name it there
        e["mark_src"], e["s_src"] = e.pop("mark"), e.pop("s")
    return RelOut(src=out, events=events) if out is not None else RelOut()


def _stain(rctx, src, dst, *, rect, inside_min, inside_share, spill, kw):
    if not src or not dst or len(rect) < 5:
        return RelOut()
    from shapely import contains_xy  # noqa: PLC0415
    from shapely.geometry import Polygon  # noqa: PLC0415
    pen = _lend_of(rctx.src, src, _lend_map(kw["lend"]))
    if pen == dst[0].meta.get("colour"):
        return RelOut()
    poly = Polygon(rect_polygon(*rect[:5]))
    length_of: dict = {}
    for m in dst:
        length_of[m.meta.get("mid")] = length_of.get(m.meta.get("mid"), 0.0) + m.length()
    cands = []
    for i, m in enumerate(dst):
        if len(m) < 2:
            continue
        ins = contains_xy(poly, m.points[:, 0], m.points[:, 1])
        s = m.arclength()
        L = length_of.get(m.meta.get("mid"), m.length())
        for a, b, v in _flag_runs(ins):
            if v and inside_min < s[b - 1] - s[a] < inside_share * L:
                cands.append((i, float(s[a]), float(s[b - 1]), pen, {"why": "stained inside the container"
                                                                     + (", spills out" if spill else "")}))
    lp = _lend_params(kw)
    if not spill:
        lp = {**lp, "p_lie": 0.0, "p_end": 0.0}
    kind = "spill" if spill else "contain"
    out, events = _take(rctx, cands, list(dst), kind, lp, always_lie=spill)
    return RelOut(dst=out, events=events) if out is not None else RelOut()


_STAIN_PARAMS = [
    P("rect", "floats", [], "the container [cx, cy, w, h, angle°]"),
    P("inside_min", "float", 6.0, "only a stretch at least this long inside is stained, mm", min=0.0, max=100.0),
    P("inside_share", "float", 0.6, "…and shorter than this share of its line (only a line that crosses the "
      "edge is stained)", min=0.05, max=1.0),
]


@relation("contain", phase="contact", params=[*_STAIN_PARAMS, *_LEND_PARAMS],
          doc="a container stains what passes inside it with its own pen, inside only")
def contain(rctx, src, dst, *, rect, inside_min, inside_share, **kw):
    return _stain(rctx, src, dst, rect=rect, inside_min=inside_min, inside_share=inside_share, spill=False, kw=kw)


@relation("spill", phase="contact", params=[*_STAIN_PARAMS, *_LEND_PARAMS],
          doc="a container stains what passes inside it; leaving, a line keeps the stain for a while (T4)")
def spill(rctx, src, dst, *, rect, inside_min, inside_share, **kw):
    return _stain(rctx, src, dst, rect=rect, inside_min=inside_min, inside_share=inside_share, spill=True, kw=kw)


@relation("touch", phase="contact", params=[
    P("touched", "str", "traverse,counter", "roles that catch a pen by touching (comma list)"),
    P("reach", "float", 0.6, "touching: this close, mm", min=0.05, max=5.0),
    P("spacing", "float", 40.0, "touches closer than this along the line count once, mm", min=1.0, max=400.0),
    *_LEND_PARAMS,
], doc="a traverse or counterweight that touches another line catches its pen, and keeps it a while")
def touch(rctx, src, dst, *, touched, reach, spacing, **kw):
    if not src or not dst:
        return RelOut()
    roles = {r.strip() for r in touched.split(",") if r.strip()}
    rd, rs = dst[0].meta.get("of_role"), src[0].meta.get("of_role")
    if rd in roles and rd != rs:
        T, O, side, oid = dst, src, "dst", rctx.src
    elif rs in roles and rd != rs:
        T, O, side, oid = src, dst, "src", rctx.dst
    else:
        return RelOut()
    pen = _lend_of(oid, O, _lend_map(kw["lend"]))
    if pen == T[0].meta.get("colour"):
        return RelOut()
    tree = _layer_tree(O, 0.3)
    if tree is None:
        return RelOut()
    cands = []
    for i, m in enumerate(T):
        if len(m) < 2:
            continue
        s = m.arclength()
        d, _ = tree.query(m.points[::4], distance_upper_bound=reach)
        last = -1e9
        for j in np.flatnonzero(np.isfinite(d)) * 4:
            if s[j] - last < spacing:
                continue
            cands.append((i, float(s[j]), float(s[j]), pen, {"why": f"touches {oid} and catches its pen"}))
            last = s[j]
    out, events = _take(rctx, cands, list(T), "touch", _lend_params(kw), always_lie=True)
    if out is None:
        return RelOut()
    if side == "src":
        for e in events:
            e["mark_src"], e["s_src"] = e.pop("mark"), e.pop("s")
        return RelOut(src=out, events=events)
    return RelOut(dst=out, events=events)


# ---------------------------------------------------------------------------
# steer: arch's danced traverse and its passer
# ---------------------------------------------------------------------------

@relation("steer", phase="grow", params=[
    P("a", "floats", [], "start [x, y], mm"),
    P("via", "floats", [], "a waypoint [x, y] passed near (empty = none)"),
    P("b", "floats", [], "goal [x, y], mm"),
    P("zoom", "float", 0.5, "the source's turns are read at this scale", min=0.05, max=4.0),
    P("pull", "float", 0.05, "the weak pull toward the goal, rad/mm", min=0.0, max=1.0),
    P("ratio", "float", 2.4, "the line may be this many times its chord before the pull strengthens", min=1.0,
      max=10.0),
    P("frame_box", "floats", [], "the composer's frame [x, y, w, h] (its walls); empty = the sheet"),
    P("zone", "floats", [], "two sources: the zone [cx, cy, w, h, angle°] inside which the second speaks"),
    P("depth", "float", 0.2, "zone: the second hand takes over this deep inside it (share of its half size)",
      min=0.01, max=1.0),
    P("zone_pen", "bool", True, "zone: inside, the line takes the zone layer's pen (the third src)"),
    P("min_run", "float", 14.0, "zone: a pen change holds at least this long, mm", min=0.0, max=200.0),
    P("timing", "str", "", "a dance tempo (e.g. staccato) weighting the line: stillness → mass, flow → nib "
      "(empty = none)"),
    P("amount", "float", 0.75, "timing: how heavy", min=0.0, max=2.0),
    P("mass_w", "float", 3.4, "timing: mass width, mm", min=1.0, max=30.0),
    P("nib_w", "float", 1.1, "timing: nib width, mm", min=0.1, max=10.0),
    P("seed", "int", 0, "timing: its die", min=0, max=2**31 - 1),
], doc="arch's steering: a source's own turns, feature by feature, pulled from a to b; with two sources the "
       "second speaks inside a zone (the passer, in the zone's pen); a tempo can weight it (the danced traverse)")
def steer_rel(rctx, src, dst, *, a, via, b, zoom, pull, ratio, frame_box, zone, depth, zone_pen, min_run, timing,
              amount, mass_w, nib_w, seed):
    groups = _groups(src)
    ids = list(groups)
    if not ids or len(a) < 2 or len(b) < 2:
        return RelOut()
    need = _need(src, dst)
    F = _box(frame_box, rctx)
    o = np.array(F[:2], float)
    srcs = {}
    two = len(zone) >= 5 and len(ids) >= 2
    for name, lid in zip(("own", "core") if two else ("own",), ids):
        pts = max(groups[lid], key=lambda m: m.length()).points
        d = turns(pts, zoom)
        if len(d) < 4:
            return RelOut()
        srcs[name] = (d, tokens(d))
    rng = rctx.rng("steer")
    zplan = {"container": {"rect": list(zone[:4]), "angle": float(zone[4])}} if two else None

    def pick(pos, k):
        if not two:
            return "own"
        x = float(np.clip(_core_depth(zplan, pos + o, "container") / depth, 0.0, 1.0))
        return "core" if float(rng.random()) < x * x * (3 - 2 * x) else "own"
    pts, who = _steer(srcs, pick, np.asarray(a[:2]) - o, np.asarray(b[:2]) - o, frame=(F[2], F[3]),
                      via=(np.asarray(via[:2]) - o) if len(via) >= 2 else None, pull=pull, ratio=ratio)
    pts = pts + o
    core = np.array([1.0 if w == "core" else 0.0 for w in who[:1] + who], float)[:len(pts)]
    ch = {"src_core": core}
    if timing:
        ch.update({"r": np.zeros(len(pts)), "W": np.full(len(pts), nib_w), "phi": np.full(len(pts), math.radians(35.0)),
                   "M": np.full(len(pts), mass_w)})
    m = Mark(pts, _fill(ch, len(pts), need), {"steered": ids[:2], "voices": ids[:2]})
    events = [{"outcome": "steered", "at": [float(pts[0][0]), float(pts[0][1])], "len_mm": round(m.length(), 1)}]
    if timing:
        tp = Part(301, {"voice": {"id": "hand", "hand": "matisse"},
                        "modulators": [get("modulator", "timing").validate(
                            {"id": "timing", "tempo": timing, "amount": amount, "mass_width": mass_w, "pen": 0.3,
                             "jitter_gain": 0.6})]},
                  {"id": "wire"}, rctx.frame, rctx.sheet_seed, rctx.run, F)
        tp.seed = int(seed)
        m = tp.modulate([m], F)[0]
    out = [m]
    if two and zone_pen and len(ids) >= 3 and groups[ids[2]]:
        from .arrangers_ccolour import _settle  # noqa: PLC0415
        zcol = groups[ids[2]][0].meta.get("colour") or "black"
        own = "__own__"
        s = m.arclength()
        raw = np.where(np.asarray(m.channels["src_core"]) > 0.5, zcol, own).astype(object)
        col = _settle(raw, s, own, min_run)
        cuts = np.r_[0, np.flatnonzero(col[1:] != col[:-1]) + 1, len(col)]
        spans = []
        for x, y in zip(cuts[:-1], cuts[1:]):
            if col[x] != own:
                e = min(int(y), len(s) - 1)
                spans.append((float(s[x]), float(s[e]), {"own_pen": {"colour": zcol}, "lent": "zone"}))
                events.append({"outcome": "speaks", "mark": 0, "s": [float(s[x]), float(s[e])], "pen": zcol,
                               "at": [float(m.points[x][0]), float(m.points[x][1])]})
        out = _apply_spans(m, spans)
    return RelOut(dst=list(dst) + out, events=events)


# ---------------------------------------------------------------------------
# flicker: arch's limb signs
# ---------------------------------------------------------------------------

def _figures(marks):
    """revisit_glyph's excursions cut from the host trail, normalized, best first (arch's reading)."""
    out = []
    for m in marks:
        if "glyph" not in m.channels:
            continue
        g = np.asarray(m["glyph"]).astype(int)
        r = np.asarray(m["r"])
        for k in sorted(set(g.tolist()) - {0}):
            idx = np.flatnonzero(g == k)
            i0, i1 = max(int(idx[0]) - 1, 0), min(int(idx[-1]) + 1, len(g) - 1)
            p = np.asarray(m.points[i0:i1 + 1], float)
            if len(p) < 6:
                continue
            p = p - p[0]
            ext = float(np.hypot(*np.ptp(p, axis=0)))
            if ext < 1e-6:
                continue
            q = p - p.mean(axis=0)
            ev = np.sqrt(np.maximum(np.linalg.eigvalsh(np.cov(q.T)), 0.0))
            d = np.diff(p, axis=0)
            th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
            turn = float(np.sum(np.abs(np.diff(th)))) / (2 * math.pi)
            out.append((float(ev[0] / max(ev[1], 1e-9)) * min(turn, 3.0), p / ext, r[i0:i1 + 1]))
    out.sort(key=lambda x: -x[0])
    return [(p, r) for sc, p, r in out[:6] if sc > 0.25]


@relation("flicker", phase="grow", params=[
    P("n", "int", 2, "how many figures surface", min=1, max=8),
    P("size", "floats", [16.0, 24.0], "figure size range [lo, hi], mm"),
    P("nib_mm", "float", 0.7, "the figure's nib width, mm", min=0.1, max=3.0),
    P("hosts", "str", "made", "roles whose lines may host a figure (comma list)"),
], doc="arch's limb signs: where a line passes with room to be seen, a small upright figure (what a dancer's "
       "other limbs did during a hold) surfaces in the line's own pen")
def flicker(rctx, src, dst, *, n, size, nib_mm, hosts):
    groups = _groups(src)
    ids = list(groups)
    if len(ids) < 2:
        return RelOut()
    figs = _figures(groups[ids[0]])
    if not figs:
        return RelOut()
    need = _need(src, dst)
    roles = {r.strip() for r in hosts.split(",") if r.strip()}
    host_marks = [(lid, m) for lid in ids[1:] for m in groups[lid]
                  if m.meta.get("of_role") in roles and len(m) >= 8 and m.length() >= 25.0]
    if not host_marks:
        return RelOut()
    W, H = rctx.frame
    lo_hi = (list(size) + [16.0, 24.0])[:2]
    size_hi = lo_hi[1]
    allp, owner = [], []
    for lid, ms in rctx.ground.items():
        if not ms or ms[0].meta.get("of_role") == UNSEEN:
            continue
        for m in ms:
            if len(m) >= 2:
                q = resample(np.asarray(m.points, float), 1.5)
                allp.append(q)
                owner += [id(m)] * len(q)
    tree = cKDTree(np.vstack(allp))
    owner = np.asarray(owner)
    rng = rctx.rng("flicker")
    spots = []
    for hi, (lid, m) in enumerate(host_marks):
        s = m.arclength()
        for x in np.arange(0.15, 0.86, 0.05) * s[-1]:
            j = int(np.clip(np.searchsorted(s, x), 1, len(m.points) - 2))
            c = np.asarray(m.points[j], float)
            if not (size_hi + 3 < c[0] < W - size_hi - 3 and size_hi + 3 < c[1] < H - size_hi - 3):
                continue
            near = tree.query_ball_point(c + [0.0, -0.5 * size_hi], 0.9 * size_hi)
            crowd = int(np.sum(owner[near] != id(m))) if near else 0
            spots.append((crowd + float(rng.random()) * 0.5, hi, j))
    if not spots:
        return RelOut()
    spots.sort()
    chosen, used = [], []
    for crowd, hi, j in spots:
        c = np.asarray(host_marks[hi][1].points[j], float)
        if any(np.linalg.norm(c - u) < 3 * size_hi for u in used) or any(hi == ci for ci, _ in chosen):
            continue
        chosen.append((hi, j))
        used.append(c)
        if len(chosen) >= n:
            break
    order = rng.permutation(len(figs))
    out, events = [], []
    for k, (hi, j) in enumerate(chosen):
        lid, m = host_marks[hi]
        p, r = figs[int(order[k % len(figs)])]
        stop = np.asarray(m.points[j], float)
        sz = float(rng.uniform(*lo_hi))
        q = p * sz + stop
        rr = np.clip(np.asarray(r, float), 0.0, 1.4)
        ch = {"r": rr, "W": np.full(len(q), nib_mm), "M": np.full(len(q), nib_mm * 1.6),
              "phi": np.full(len(q), math.radians(40.0))}
        ink = _ink(m)
        out.append(Mark(q, _fill(ch, len(q), need), {"host": lid, "own_pen": {"colour": ink}, "figure": k}))
        events.append({"outcome": "surface", "at": [float(stop[0]), float(stop[1])], "host": lid,
                       "s_src": [float(m.arclength()[j])] * 2, "size": round(sz, 1), "pen": ink})
    return RelOut(dst=list(dst) + out, events=events)
