# FROZEN from research commit c712045: tools/gesture/gesture/kit/relations_listen.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Synthesis bench S2a: listen's vocabulary as score relations (grow), and its void (contact).

Round 15's `listen` composer (`arrangers_listen.Composer`) drew a whole sheet as a short history:
speakers, then layers that take an earlier layer's gesture and do something with it. Here every one of
its eight kinds is a GROW relation the executor (`_synth.run`) plays, so the score is the program
(`docs/synthesis-bench/design-2026-10-19.md` §5, §6). The geometry is listen's own (its helpers are
imported from `arrangers_listen`, not copied); what moved is WHEN it runs and WHAT it reads.

Spliced (the dst has its own voice: a `part` on the layer, so its hand can be swapped in the stack):
    imitate     the gesture in unison, close beside the source, then the line parts
    exaggerate  the gesture pushed (sideways ×gain, ×scale), centred on the source gesture
    translate   the same move in another line style (ruled / meander / the listener's own hand)
    refuse      the listener's own line laid across the source, walking its halo instead of meeting it
  The relation replaces the dst's raw part output with the placed line. It picks a gesture from the
  source (a stretch with character, away from where other layers already talk), splices it into the
  listener's own line (heading continuous), and tries splice points × sides × three variants of its
  own line (forward, reversed, forward again), keeping the placement whose own stretches cover the
  least existing ink (`rctx.ground`, the dst itself excluded) and run furthest with the sheet's flow
  (`flow_deg`). The heard stretch is inked in the listening pen with `own_pen` (`heard`: "" = the
  layer's own pen, "src" = the source layer's pen, or a Flexoki name).

Separate small layers (relation-only layers are fine: they start empty):
    echo        the gesture again at the fringe of the drawing, smaller, 1–3 decaying repeats
    calm        the gesture flattened to a quiet arc whose ends land on the gesture's ends
    nest        a small copy of the source's own gesture inside a crook of the source's line
    bind        a ligature from the end of one layer into the start of another (`src` is a LIST of two
                layers); the second half may carry the second layer's pen (`second`)

Follow (Ian, 2026-10-19): placement lives here and reads the source at PLAY time. Edit an earlier
layer and its listeners re-pick their gesture and re-place themselves beside it on replay; pin a
listener (`_synth.pin`) to hold it still. A listener that can no longer be placed (no gesture with
character, nowhere to lie) draws nothing and logs outcome "unplaced" — never its raw part in a corner.

Whole lines from pieces: earlier contact relations may have cut a source (crossing gaps, the void).
Marks that share the executor's stable `mid` are rejoined in `mid_s0` order (a gap bridged straight,
which keeps arc lengths), so a gesture is picked on the line as drawn, not on one piece of it.

The void (`mask`, contact): listen's torn void at an ambiguous point. The void itself is a WRITTEN
place (its polygon is a param, its partly drawn edge a `lines` layer, role "mask"), like a speaker's
centre; this relation does what the void does to the others: a layer drawn BEFORE it is cut by it
(outcome "mask"), a layer drawn AFTER it crosses it (outcome "ignore"); `flip` lists layers that do the
opposite (listen's exceptions, decided by the writer so the order stays ambiguous). Write it as
{"src": <void layer>, "dst": "*", "not_roles": ["mask"]}. The polygon is a param rather than read from
the void layer because a void may draw none of its edge (listen: 15% of voids), and then nothing on
the sheet would carry it.

Determinism: every draw from `rctx.rng(kind or tag)`; sources ordered by first appearance / arc length.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import binary_dilation, distance_transform_edt, gaussian_filter1d

from ._relations import RelOut, cut, relation
from .arrangers_ccolour import _pick, _u
from .arrangers_listen import (STEP, amplify, chord_normal, detour, headings, in_hand, integrate, meander,
                               pick_gesture, push, ruled, similar_to)
from .arrangers_oehlen_found import arclen, resample, rotate
from .core import Mark, P

SPLICED = ("imitate", "exaggerate", "translate", "refuse")
LATER = ("echo", "calm", "nest", "bind")
KINDS = SPLICED + LATER
UNPLACED = "unplaced"


# ---------------------------------------------------------------------------
# reading the ground
# ---------------------------------------------------------------------------

def _bounds(rctx, box) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1): the box the writer composes in (the frame when none)."""
    if box:
        x, y, w, h = (float(v) for v in box)
        return (x, y, x + w, y + h)
    W, H = rctx.frame
    return (0.0, 0.0, float(W), float(H))


def _inside(p, B, m) -> bool:
    return bool((p[:, 0] >= B[0] + m).all() and (p[:, 0] <= B[2] - m).all() and (p[:, 1] >= B[1] + m).all()
                and (p[:, 1] <= B[3] - m).all())


def _fit_tails(line, i0, i1, B, m):
    """`arrangers_listen.fit_tails` in a box: the tails scaled toward the borrowed stretch's ends until
    they fit (heading kept), or None."""
    if not _inside(line[i0:i1 + 1], B, m):
        return None
    out = line.copy()
    for tail, anchor in ((slice(0, i0), line[i0]), (slice(i1 + 1, len(line)), line[i1])):
        seg = line[tail]
        if not len(seg):
            continue
        for f in (1.0, 0.85, 0.7, 0.58, 0.48, 0.4, 0.33):
            q = anchor + (seg - anchor) * f
            if _inside(q, B, m):
                out[tail] = q
                break
        else:
            return None
    return out


def _settle(line, B, m):
    """`Composer._settle` in a box: shrink about the centre and shift until inside the margin."""
    lo, hi = line.min(axis=0), line.max(axis=0)
    k = min(1.0, (B[2] - B[0] - 2 * m) / max(hi[0] - lo[0], 1e-9), (B[3] - B[1] - 2 * m) / max(hi[1] - lo[1], 1e-9))
    mid = (lo + hi) / 2
    line = (line - mid) * k + mid
    lo, hi = line.min(axis=0), line.max(axis=0)
    shift = np.clip(np.array([B[0] + m, B[1] + m]) - lo, 0, None) - np.clip(hi - np.array([B[2] - m, B[3] - m]), 0, None)
    return line + shift


def whole_lines(marks) -> list[tuple[Mark, int]]:
    """Each drawn line rebuilt whole: marks sharing a stable `mid` joined in `mid_s0` order (a cut gap
    bridged straight), resampled at STEP. → [(line Mark, index of its first piece in `marks`)], in order
    of first appearance. Channels common to the pieces are carried; meta is the first piece's."""
    groups: dict[str, list] = {}
    order: list[str] = []
    for i, m in enumerate(marks):
        if len(m) < 2:
            continue
        key = str(m.meta.get("mid") or f"#{i}")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((float(m.meta.get("mid_s0", 0.0)), i, m))
    out = []
    for key in order:
        ps = sorted(groups[key], key=lambda t: (t[0], t[1]))
        names = set.intersection(*(set(t[2].channels) for t in ps))
        pts = np.vstack([t[2].points for t in ps])
        chs = {n: np.concatenate([t[2].channels[n] for t in ps]) for n in names}
        keep = np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-9]     # no zero-length steps
        if keep.sum() < 2:
            continue
        full = Mark(pts[keep], {n: v[keep] for n, v in chs.items()}, dict(ps[0][2].meta))
        if full.length() <= STEP:
            continue
        out.append((full.resampled(STEP), ps[0][1]))
    return out


def longest_line(marks):
    """(the longest whole line, index of its first piece) or (None, None)."""
    ls = whole_lines(marks)
    if not ls:
        return None, None
    best = max(range(len(ls)), key=lambda j: (round(ls[j][0].length(), 6), -j))
    return ls[best]


def _ground_lines(rctx, skip=()) -> list[np.ndarray]:
    out = []
    for lid, ms in rctx.ground.items():
        if lid in skip:
            continue
        for m in ms:
            if len(m) >= 2 and m.meta.get("of_role") != "unseen":
                out.append(m.points)
    return out


def _raster(lines, frame, cell):
    """listen's `raster`: cells a line passes through (lines densified so a coarse one leaves no holes)."""
    W, H = frame
    nx, ny = int(math.ceil(W / cell)), int(math.ceil(H / cell))
    occ = np.zeros((ny, nx), bool)
    for l in lines:
        q = np.asarray(l, float)
        if len(q) >= 2 and float(np.max(np.linalg.norm(np.diff(q, axis=0), axis=1))) > min(STEP, cell / 2):
            q = resample(q, min(STEP, cell / 2))
        ij = np.clip((q / cell).astype(int), 0, [nx - 1, ny - 1])
        occ[ij[:, 1], ij[:, 0]] = True
    return occ


def _crowd(rctx, skip):
    """listen's `crowd`: the share of a stretch's points on other layers' ink (dilated)."""
    cell = 3.0
    occ = binary_dilation(_raster(_ground_lines(rctx, skip), rctx.frame, cell), iterations=2)

    def f(q):
        ij = np.clip((q / cell).astype(int), 0, [occ.shape[1] - 1, occ.shape[0] - 1])
        return float(occ[ij[:, 1], ij[:, 0]].mean())
    return f


def _main_colour(marks) -> str | None:
    """A layer's pen as its marks carry it (its own marks, not ones with their own pen)."""
    for m in marks:
        if not m.meta.get("own_pen") and m.meta.get("colour"):
            return str(m.meta["colour"])
    return None


def _heard_colour(heard: str, src, dst) -> str | None:
    """The colour of the stretch where a line listens, or None when it is the layer's own."""
    if not heard:
        return None
    c = _main_colour(src) if heard == "src" else heard
    own = _main_colour(dst)
    return None if (not c or c == own) else c


def _piece(base: Mark, pts: np.ndarray, s_lo: float, s_hi: float, meta: dict) -> Mark:
    """New points carrying `base`'s channels (interpolated along base from s_lo to s_hi), fresh meta."""
    s_new = np.linspace(float(s_lo), float(s_hi), len(pts))
    m = base.remap(np.clip(s_new, 0.0, base.length()), points=pts)
    return Mark(m.points, m.channels, meta)


def _unit(deg):
    a = math.radians(float(deg))
    return np.array([math.cos(a), math.sin(a)])


def _unplaced(why: str, dst) -> RelOut:
    return RelOut(dst=[], events=[{"outcome": UNPLACED, "why": why, "had": len(dst)}])


def _src_ref(src, first, i0, i1):
    """mark_src + s_src for an event (the executor turns them into the uncut stretch)."""
    return {"mark_src": int(first), "s_src": [i0 * STEP, i1 * STEP]}


# ---------------------------------------------------------------------------
# spliced listeners
# ---------------------------------------------------------------------------

def _borrow(kind, g, own, rng, *, style, gain, scale):
    """`Composer._borrow`: the borrowed stretch as the listener will draw it, and what was done."""
    info = {}
    if kind == "imitate":
        th = headings(g)
        th = th + gaussian_filter1d(rng.normal(0, 0.05, len(th)), 6)       # an imitation, not a copy
        return integrate(th, g[0]), info
    if kind == "exaggerate":
        ga, sc = _u(rng, *gain), _u(rng, *scale)
        info.update(gain=round(ga, 2), scale=round(sc, 2))
        return amplify(g, ga, sc), info
    st = _pick(rng, ["ruled", "meander", "hand"], [0.25, 0.4, 0.35]) if style == "auto" else style
    info["style"] = st
    if st == "ruled":
        return ruled(g, _u(rng, 1.2, 2.2)), info
    if st == "meander":
        return meander(g, _u(rng, 0.8, 1.2), _u(rng, 5.0, 9.0), _u(rng, 5.0, 9.0)), info
    return in_hand(g, own, _u(rng, 5.0, 8.0), _u(rng, 1.6, 2.2)), info


def _coverage_cost(q, j0, j1, occ, flow, diag, cell=3.0):
    """`Composer._coverage_cost`: own stretches on existing ink, minus how far the tails run with the flow."""
    tails = np.vstack([q[:j0], q[j1:]]) if j0 > 0 or j1 < len(q) else q
    ij = np.clip((tails / cell).astype(int), 0, [occ.shape[1] - 1, occ.shape[0] - 1])
    on = float(occ[ij[:, 1], ij[:, 0]].mean())
    mid = (q[j0] + q[j1]) / 2
    drift = float(np.dot(tails.mean(axis=0) - mid, flow)) / diag
    return on - 0.8 * drift


def _listen(kind, rctx, src, dst, *, len_mm, gap_mm, flow_deg, heard, box, margin, style="auto",
            gain=(1.7, 2.5), scale=(1.2, 1.5)):
    rng = rctx.rng(kind)
    W, H = rctx.frame
    B = _bounds(rctx, box)
    full, first = longest_line(src)
    own_m, _ = longest_line(dst)
    if full is None or own_m is None:
        return _unplaced("no source line" if full is None else "no own line", dst)
    s_line = full.points
    gi = pick_gesture(rng, s_line, *len_mm, crowd=_crowd(rctx, {rctx.src, rctx.dst}))
    if gi is None:
        return _unplaced("no gesture with character on the source", dst)
    i0, i1 = gi
    g = s_line[i0:i1 + 1]
    occ = binary_dilation(_raster(_ground_lines(rctx, {rctx.dst}), (W, H), 3.0), iterations=1)
    n = chord_normal(g)
    gap = _u(rng, *gap_mm)
    flow, diag = _unit(flow_deg), math.hypot(W, H)
    own0 = own_m.points
    best = None
    for trial in range(3):
        # three variants of the listener's own voice: as drawn, drawn backwards, as drawn again
        own = own0[::-1] if trial == 1 else own0
        ins, info = _borrow(kind, g, own, rng, style=style, gain=gain, scale=scale)
        tho, thi = headings(own), headings(ins)
        if len(tho) < 4 or len(thi) < 2:
            continue
        for kf in (_u(rng, 0.15, 0.4), _u(rng, 0.6, 0.85)):
            # splice: own[:k] + ins (turned to continue the heading) + own[k:] (turned to continue again)
            k = int(len(tho) * kf)
            th_ins = thi - thi[0] + tho[k]
            th = np.concatenate([tho[:k], th_ins, tho[k:] - tho[k] + th_ins[-1]])
            line = integrate(th, [0.0, 0.0])
            j0, j1 = k, k + len(th_ins)
            line = rotate(line, line[j0], -math.degrees(tho[k] - thi[0]))
            for sgn in (1, -1):
                off = n * sgn * gap
                if kind == "exaggerate":           # the pushed shape around the original
                    q = line - line[j0:j1 + 1].mean(axis=0) + g.mean(axis=0) + off
                else:                              # beside it, centred on its middle
                    q = line - (line[j0] + line[j1]) / 2 + (g[0] + g[-1]) / 2 + off
                q = _fit_tails(q, j0, j1, B, margin)
                if q is None:
                    continue
                cost = _coverage_cost(q, j0, j1, occ, flow, diag) + 0.05 * rng.random()
                if best is None or cost < best[0]:
                    best = (cost, q, j0, j1, info, trial, sgn, kf)
    if best is None:
        return _unplaced("nowhere beside the source on the paper", dst)
    _, placed, j0, j1, info, trial, sgn, kf = best
    sq = arclen(placed)
    L = float(sq[-1])
    base_len = own_m.length()
    colour = _heard_colour(heard, src, dst)
    lid = rctx.dst

    def part(a, b, extra=None):
        meta = {"mid": f"{lid}:0", "mid_s0": float(sq[a]), "listen": kind}
        if extra:
            meta.update(extra)
        return _piece(own_m, placed[a:b + 1], sq[a] / L * base_len, sq[b] / L * base_len, meta)

    if colour is None:
        out = [part(0, len(placed) - 1)]
    else:
        out = [part(a, b, {"own_pen": {"colour": colour}, "heard": True} if h else None)
               for a, b, h in ((0, j0, False), (j0, j1, True), (j1, len(placed) - 1, False)) if b - a >= 1]
    ev = {"outcome": kind, "at": placed[(j0 + j1) // 2].tolist(), "s": [float(sq[j0]), float(sq[j1])],
          **_src_ref(src, first, i0, i1), "gap_mm": round(gap, 2), "side": int(sgn), "own": ["as drawn", "reversed",
                                                                                             "as drawn"][trial],
          "splice_at_mm": round(float(sq[j0]), 1), "heard_pen": colour, **info,
          "note": {"imitate": "the gesture in unison beside the source, then the line parts",
                   "exaggerate": "pushed sideways and enlarged, centred on the source gesture",
                   "translate": f"the same move in another line style ({info.get('style')})"}[kind]}
    return RelOut(dst=out, events=[ev])


def _spliced_params(len_mm, gap_mm):
    return [
        P("len_mm", "floats", list(len_mm), "the heard gesture's length range on the source, mm",
          min=8.0, max=400.0, min_len=2, max_len=2),
        P("gap_mm", "floats", list(gap_mm), "how far beside the source the borrowed stretch lies, mm",
          min=0.0, max=40.0, min_len=2, max_len=2),
        P("flow_deg", "float", 0.0, "the sheet's flow: the listener's own tails run with it", min=0.0, max=360.0),
        P("heard", "str", "", "the heard stretch's pen: \"\" = the layer's own, \"src\" = the source's, or a "
          "Flexoki pen name"),
        P("box", "floats", None, "the writer's box [x, y, w, h] (null = the frame)", min=0.0, max=2000.0,
          min_len=4, max_len=4, optional=True),
        P("margin", "float", 7.0, "keep the placed line this far inside the box, mm", min=0.0, max=40.0),
    ]


@relation("imitate", phase="grow", params=_spliced_params((55.0, 120.0), (3.0, 5.0)),
          doc="listen: the listener's own line takes up the source's gesture in unison, close beside it, "
              "then parts (placed at play time: it follows an edited source)")
def imitate(rctx, src, dst, *, len_mm, gap_mm, flow_deg, heard, box, margin):
    return _listen("imitate", rctx, src, dst, len_mm=len_mm, gap_mm=gap_mm, flow_deg=flow_deg, heard=heard,
                   box=box, margin=margin)


@relation("exaggerate", phase="grow", params=_spliced_params((35.0, 70.0), (1.5, 3.0)) + [
    P("gain", "floats", [1.7, 2.5], "sideways push range", min=1.0, max=5.0, min_len=2, max_len=2),
    P("scale", "floats", [1.2, 1.5], "enlargement range", min=1.0, max=3.0, min_len=2, max_len=2),
], doc="listen: the source's gesture pushed (turns amplified about their trend, enlarged), centred on it")
def exaggerate(rctx, src, dst, *, len_mm, gap_mm, flow_deg, heard, box, margin, gain, scale):
    return _listen("exaggerate", rctx, src, dst, len_mm=len_mm, gap_mm=gap_mm, flow_deg=flow_deg, heard=heard,
                   box=box, margin=margin, gain=tuple(gain), scale=tuple(scale))


@relation("translate", phase="grow", params=_spliced_params((55.0, 120.0), (6.0, 10.0)) + [
    P("style", "choice", "auto", "the other line style (auto: drawn per placement, as listen did)",
      choices=("auto", "ruled", "meander", "hand")),
], doc="listen: the same move in another line style — ruled chords, a meander, or the listener's own hand")
def translate(rctx, src, dst, *, len_mm, gap_mm, flow_deg, heard, box, margin, style):
    return _listen("translate", rctx, src, dst, len_mm=len_mm, gap_mm=gap_mm, flow_deg=flow_deg, heard=heard,
                   box=box, margin=margin, style=style)


@relation("refuse", phase="grow", params=[
    P("halo", "floats", [2.5, 5.0], "the halo it walks instead of meeting the source, mm (range)",
      min=0.5, max=20.0, min_len=2, max_len=2),
    P("heard", "str", "", "the detours' pen: \"\" = the layer's own, \"src\", or a Flexoki pen name"),
    P("box", "floats", None, "the writer's box [x, y, w, h] (null = the frame)", min=0.0, max=2000.0,
      min_len=4, max_len=4, optional=True),
    P("margin", "float", 7.0, "settle the line this far inside the box, mm", min=0.0, max=40.0),
], doc="listen: the listener's own line laid across the source; wherever it would come within the halo "
       "it walks the halo instead (a detour at constant distance)")
def refuse(rctx, src, dst, *, halo, heard, box, margin):
    rng = rctx.rng("refuse")
    B = _bounds(rctx, box)
    r = _u(rng, *halo)
    full, _ = longest_line(src)
    own_m, _ = longest_line(dst)
    if full is None or own_m is None:
        return _unplaced("no source line" if full is None else "no own line", dst)
    own = own_m.points
    s_line = full.points
    others = [m.points for m in src if len(m) > 1]
    colour = _heard_colour(heard, src, dst)
    for attempt in range(6):
        c = s_line[int(rng.integers(len(s_line)))] + rng.normal(0, 6.0, 2)
        q = rotate(own, own.mean(axis=0), _u(rng, 0, 360))
        q = _settle(q - q.mean(axis=0) + c, B, margin)
        out, where = detour(q, others, r)
        if not where or out is None or not _inside(out, B, 2.0):
            continue
        sa = arclen(out)
        L = float(sa[-1])
        base_len = own_m.length()
        cuts = sorted({0} | {min(int(np.searchsorted(sa, v)), len(out) - 1) for _, s0, s1 in where for v in (s0, s1)}
                      | {len(out) - 1})
        marks = []
        for a, b in zip(cuts[:-1], cuts[1:]):
            if b - a < 1:
                continue
            mid = sa[(a + b) // 2]
            h = any(s0 <= mid <= s1 for _, s0, s1 in where)
            meta = {"mid": f"{rctx.dst}:0", "mid_s0": float(sa[a]), "listen": "refuse"}
            if h and colour is not None:
                meta.update(own_pen={"colour": colour}, heard=True)
            marks.append(_piece(own_m, out[a:b + 1], sa[a] / L * base_len, sa[b] / L * base_len, meta))
        if colour is None:          # one pen: one line
            marks = [_piece(own_m, out, 0.0, base_len, {"mid": f"{rctx.dst}:0", "mid_s0": 0.0, "listen": "refuse"})]
        events = [{"outcome": "refuse", "at": np.asarray(a).tolist(), "s": [float(s0), float(s1)],
                   "halo_mm": round(r, 2), "detours": len(where), "attempt": attempt, "heard_pen": colour,
                   "note": f"walks the source's halo at {r:.1f} mm instead of meeting it"} for a, s0, s1 in where]
        return RelOut(dst=marks, events=events)
    return _unplaced("no crossing placement whose detours resolve", dst)


# ---------------------------------------------------------------------------
# later small layers
# ---------------------------------------------------------------------------

def _box_params(margin):
    return [P("box", "floats", None, "the writer's box [x, y, w, h] (null = the frame)", min=0.0, max=2000.0,
              min_len=4, max_len=4, optional=True),
            P("margin", "float", margin, "keep it this far inside the box, mm", min=0.0, max=40.0)]


def _echo_spot(rctx, gc, B, rng, dist):
    """`Composer.echo_spot`: 35–90 mm from what it echoes, at the fringe of the drawing (some ink near,
    none on top), never out alone in the blank."""
    cell = 2.0
    W, H = rctx.frame
    occ = _raster(_ground_lines(rctx, {rctx.dst}), (W, H), cell)
    d = distance_transform_edt(~occ) * cell
    ny, nx = d.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    cx, cy = (xx + 0.5) * cell, (yy + 0.5) * cell
    edge = np.minimum.reduce([cx - B[0], cy - B[1], B[2] - cx, B[3] - cy])
    dd = np.hypot(cx - gc[0], cy - gc[1])
    ok = (dd > dist[0]) & (dd < dist[1]) & (edge > 16.0) & (d > 6.0) & (d < 16.0)
    score = np.where(ok, d + rng.random(d.shape) * 3.0, -1.0)
    j = int(np.argmax(score))
    if score.ravel()[j] < 0:
        return None
    return np.array([cx.ravel()[j], cy.ravel()[j]])


@relation("echo", phase="grow", params=[
    P("len_mm", "floats", [25.0, 55.0], "the echoed gesture's length range, mm", min=8.0, max=300.0,
      min_len=2, max_len=2),
    P("dist_mm", "floats", [35.0, 90.0], "how far from what it echoes it lands, mm", min=5.0, max=400.0,
      min_len=2, max_len=2),
    *_box_params(7.0),
], doc="listen: the source's gesture again at the fringe of the drawing, smaller, 1–3 repeats that decay")
def echo(rctx, src, dst, *, len_mm, dist_mm, box, margin):
    rng = rctx.rng("echo")
    B = _bounds(rctx, box)
    full, first = longest_line(src)
    if full is None:
        return _unplaced("no source line", dst)
    s_line = full.points
    gi = pick_gesture(rng, s_line, *len_mm)
    if gi is None:
        return _unplaced("no gesture with character on the source", dst)
    g = s_line[gi[0]:gi[1] + 1]
    gc = g.mean(axis=0)
    spot = _echo_spot(rctx, gc, B, rng, dist_mm)
    if spot is None:
        return _unplaced("no fringe to land on (never a lone mark in the blank)", dst)
    reps = int(_pick(rng, [1, 2, 3], [0.25, 0.45, 0.3]))
    size = max(np.ptp(g, axis=0).max(), 1e-9)
    k0 = float(np.clip(_u(rng, 0.75, 1.0), min(28.0 / size, 1.0), 1.0))
    ang = _u(rng, -25, 25)
    step_dir = np.array([math.cos(math.radians(_u(rng, 0, 360))), 0.0])
    step_dir[1] = math.sqrt(max(1 - step_dir[0] ** 2, 0)) * rng.choice([-1, 1])
    pos, k, lines = spot.copy(), k0, []
    for _ in range(reps):
        q = rotate((g - gc) * k, np.zeros(2), ang) + pos
        if not _inside(q, B, margin):
            break
        lines.append(q)
        pos = pos + step_dir * (np.ptp(q, axis=0).max() * 0.75 + 3.0)
        k *= _u(rng, 0.7, 0.82)
        if k * size < 20.0:
            break
    if not lines:
        return _unplaced("the echo would leave the paper", dst)
    s0, s1 = gi[0] * STEP, gi[1] * STEP
    out = [_piece(full, q, s0, s1, {"mid": f"{rctx.dst}:{j}", "mid_s0": 0.0, "listen": "echo"})
           for j, q in enumerate(lines)]
    return RelOut(dst=out, events=[{"outcome": "echo", "at": lines[0].mean(axis=0).tolist(),
                                    "s": [0.0, float(arclen(lines[0])[-1])], **_src_ref(src, first, *gi),
                                    "repeats": len(lines), "scale": round(k0, 2), "turn_deg": round(ang, 1),
                                    "note": f"{len(lines)} repeat(s), ×{k0:.2f} and decaying"}])


@relation("calm", phase="grow", params=[
    P("len_mm", "floats", [30.0, 70.0], "the calmed gesture's length range, mm", min=8.0, max=300.0,
      min_len=2, max_len=2),
    P("gain", "floats", [0.12, 0.3], "how much of its turning is left", min=0.0, max=1.0, min_len=2, max_len=2),
    *_box_params(3.0),
], doc="listen: the understatement — the gesture's turns flattened to a quiet arc whose ends land on its ends")
def calm(rctx, src, dst, *, len_mm, gain, box, margin):
    rng = rctx.rng("calm")
    B = _bounds(rctx, box)
    full, first = longest_line(src)
    if full is None:
        return _unplaced("no source line", dst)
    s_line = full.points
    gi = pick_gesture(rng, s_line, *len_mm, open_ends=True)
    if gi is None:
        return _unplaced("no open gesture on the source", dst)
    g = s_line[gi[0]:gi[1] + 1]
    q = push(g, _u(rng, *gain), 1.0, trend_mm=0.0)
    q = resample(similar_to(q, g[0], g[-1]), STEP)
    if not _inside(q, B, margin):
        return _unplaced("the calm line would leave the paper", dst)
    m = _piece(full, q, gi[0] * STEP, gi[1] * STEP, {"mid": f"{rctx.dst}:0", "mid_s0": 0.0, "listen": "calm"})
    return RelOut(dst=[m], events=[{"outcome": "calm", "at": q[len(q) // 2].tolist(),
                                    "s": [0.0, float(arclen(q)[-1])], **_src_ref(src, first, *gi),
                                    "note": "the gesture flattened, its ends on the gesture's ends"}])


@relation("nest", phase="grow", params=[
    P("len_mm", "floats", [20.0, 45.0], "the nested gesture's length range, mm", min=8.0, max=300.0,
      min_len=2, max_len=2),
    P("crook_mm", "floats", [7.0, 18.0], "how far from the source's line a crook's centre lies, mm",
      min=2.0, max=60.0, min_len=2, max_len=2),
], doc="listen: a small copy of the source's own gesture set inside a crook of the source's line")
def nest(rctx, src, dst, *, len_mm, crook_mm):
    rng, cell = rctx.rng("nest"), 1.0
    full, first = longest_line(src)
    if full is None:
        return _unplaced("no source line", dst)
    occ = _raster([m.points for m in src if len(m) > 1], rctx.frame, cell)
    d = distance_transform_edt(~occ) * cell
    ny, nx = d.shape
    cand = np.argwhere((d > crook_mm[0]) & (d < crook_mm[1]))
    if not len(cand):
        return _unplaced("the source encloses no crook", dst)
    order = rng.permutation(len(cand))[:600]
    angs = np.linspace(0, 2 * math.pi, 12, endpoint=False)
    ca, sa = np.cos(angs), np.sin(angs)
    best = None
    for j in order:
        y, x = cand[j]
        r = d[y, x]
        if best is not None and r <= best[0]:
            continue                          # only a wider crook could win (listen keeps the widest)
        t = np.arange(r, 3.2 * r, cell)
        xs = (x + ca[:, None] * t[None, :] / cell).astype(int)
        ys = (y + sa[:, None] * t[None, :] / cell).astype(int)
        inb = (xs >= 0) & (xs < nx) & (ys >= 0) & (ys < ny)
        # a ray counts when it meets ink before it leaves the paper (listen walks each ray and stops there)
        hit = np.zeros(xs.shape, bool)
        hit[inb] = occ[ys[inb], xs[inb]]
        out_first = np.where((~inb).any(axis=1), np.argmax(~inb, axis=1), xs.shape[1])
        hit_first = np.where(hit.any(axis=1), np.argmax(hit, axis=1), xs.shape[1])
        hits = int(np.sum(hit_first < out_first))
        if hits >= 9:
            best = (r, np.array([(x + 0.5) * cell, (y + 0.5) * cell]))
    if best is None:
        return _unplaced("the source encloses no crook", dst)
    r, c = best
    s_line = full.points
    gi = pick_gesture(rng, s_line, *len_mm)
    if gi is None:
        return _unplaced("no gesture with character on the source", dst)
    g = s_line[gi[0]:gi[1] + 1]
    k = 0.62 * r / max(np.linalg.norm(g - g.mean(axis=0), axis=1).max(), 1e-9)
    q = rotate((g - g.mean(axis=0)) * k, np.zeros(2), _u(rng, 0, 360)) + c
    m = _piece(full, q, gi[0] * STEP, gi[1] * STEP, {"mid": f"{rctx.dst}:0", "mid_s0": 0.0, "listen": "nest"})
    return RelOut(dst=[m], events=[{"outcome": "nest", "at": c.tolist(), "s": [0.0, float(arclen(q)[-1])],
                                    **_src_ref(src, first, *gi), "radius_mm": round(float(r), 1),
                                    "scale": round(float(k), 3),
                                    "note": f"the source's own gesture ×{k:.2f}, in a crook {r:.0f} mm across"}])


@relation("bind", phase="grow", params=[
    P("dist_mm", "floats", [25.0, 150.0], "how far apart the two ends may be, mm", min=2.0, max=600.0,
      min_len=2, max_len=2),
    P("second", "str", "", "the second half's pen: \"\" = the layer's own, \"src\" = the second source's, "
      "or a Flexoki pen name (the pen hands over halfway)"),
    *_box_params(2.0),
], doc="listen: a ligature from the end of one layer into the start of another, tangent at both ends "
       "(src: a list of two layers)")
def bind(rctx, src, dst, *, dist_mm, second, box, margin):
    rng = rctx.rng("bind")
    B = _bounds(rctx, box)
    by: dict[str, list] = {}
    for m in src:
        by.setdefault(str(m.meta.get("score_layer", "")), []).append(m)
    ids = list(by)
    if len(ids) < 2:
        return _unplaced("needs two layers to bind", dst)
    A, Bm = by[ids[0]], by[ids[1]]
    la, _ = longest_line(A)
    lb, _ = longest_line(Bm)
    if la is None or lb is None or len(la) < 9 or len(lb) < 9:
        return _unplaced("a bound layer has no line", dst)
    pa, pb = la.points, lb.points
    best = None
    for ea, ta in ((pa[-1], pa[-1] - pa[-8]), (pa[0], pa[0] - pa[7])):
        for sb, tb in ((pb[0], pb[7] - pb[0]), (pb[-1], pb[-8] - pb[-1])):
            dist = float(np.linalg.norm(sb - ea))
            if dist_mm[0] <= dist <= dist_mm[1] and (best is None or dist < best[0]):
                best = (dist, ea, ta, sb, tb)
    if best is None:
        return _unplaced("the two layers' ends are too near or too far", dst)
    dist, p0, t0, p1, t1 = best
    t0, t1 = t0 / max(np.linalg.norm(t0), 1e-9), t1 / max(np.linalg.norm(t1), 1e-9)
    h = dist * _u(rng, 0.35, 0.6)
    u = np.linspace(0, 1, max(int(dist * 3 / STEP), 20))[:, None]
    q = ((2 * u ** 3 - 3 * u ** 2 + 1) * p0 + (u ** 3 - 2 * u ** 2 + u) * h * t0 * 3
         + (-2 * u ** 3 + 3 * u ** 2) * p1 + (u ** 3 - u ** 2) * h * t1 * 3)
    q = resample(q, STEP)
    if not _inside(q, B, margin):
        return _unplaced("the ligature would leave the paper", dst)
    mid = len(q) // 2
    sq = arclen(q)
    base_len = la.length()
    colour = (_main_colour(Bm) if second == "src" else second) or None
    meta0 = {"mid": f"{rctx.dst}:0", "listen": "bind"}
    halves = [_piece(la, q[:mid + 1], 0.0, base_len * 0.5, {**meta0, "mid_s0": 0.0})]
    m1 = {**meta0, "mid_s0": float(sq[mid])}
    if colour is not None:
        m1["own_pen"] = {"colour": colour}
    halves.append(_piece(la, q[mid:], base_len * 0.5, base_len, m1))
    return RelOut(dst=halves, events=[{"outcome": "bind", "at": q[mid].tolist(), "s": [0.0, float(sq[-1])],
                                       "from": ids[0], "to": ids[1], "second_pen": colour,
                                       "note": f"a ligature from {ids[0]}'s end into {ids[1]}'s start"}])


# ---------------------------------------------------------------------------
# the void
# ---------------------------------------------------------------------------

def _polygon(flat):
    a = np.asarray(flat or [], float)
    if len(a) < 6 or len(a) % 2:
        return None
    return a.reshape(-1, 2)


def _inside_intervals(m: Mark, poly) -> list[tuple[float, float]]:
    """Arc-length intervals of m inside the polygon (sampled finely, edges at the half-steps)."""
    import shapely  # noqa: PLC0415
    from shapely.geometry import Polygon  # noqa: PLC0415
    s = m.arclength()
    if len(s) < 2 or s[-1] <= 0:
        return []
    n = max(int(s[-1] / 0.25), 2)
    t = np.linspace(0.0, s[-1], n + 1)
    pts = np.column_stack([np.interp(t, s, m.points[:, 0]), np.interp(t, s, m.points[:, 1])])
    ins = shapely.contains_xy(Polygon(poly), pts[:, 0], pts[:, 1])
    out = []
    pad = np.r_[False, ins, False]
    d = np.diff(pad.astype(int))
    for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1):
        lo = 0.0 if a == 0 else (t[a - 1] + t[a]) / 2
        hi = float(s[-1]) if b == len(t) - 1 else (t[b] + t[b + 1]) / 2
        out.append((float(lo), float(hi)))
    return out


@relation("mask", phase="contact", params=[
    P("polygon", "floats", None, "the void, flat [x0, y0, x1, y1, …] mm (the writer's written place)",
      min=0.0, max=2000.0, optional=True),
    P("flip", "str", "", "layer ids (comma list) that do the opposite of their order: cut although drawn "
      "after the void, or crossing it although drawn before (listen's exceptions)"),
    P("min_stub", "float", 3.0, "pieces a cut leaves shorter than this are dropped, mm", min=0.0, max=30.0),
], doc="listen's void: layers drawn before it are cut by it, layers drawn after it cross it "
       "(src: the void layer, dst: \"*\" with not_roles [\"mask\"])")
def mask(rctx, src, dst, *, polygon, flip, min_stub):
    poly = _polygon(polygon)
    if poly is None or not dst:
        return RelOut()
    order = list(rctx.ground)
    before = order.index(rctx.dst) < order.index(rctx.src) if rctx.src in order and rctx.dst in order else True
    flipped = rctx.dst in {v.strip() for v in flip.split(",") if v.strip()}
    respect = before != flipped
    hit = {i: _inside_intervals(m, poly) for i, m in enumerate(dst)}
    hit = {i: v for i, v in hit.items() if v}
    if not hit:
        return RelOut()
    pts = np.vstack([dst[i].points for i in sorted(hit)])
    import shapely  # noqa: PLC0415
    from shapely.geometry import Polygon  # noqa: PLC0415
    inside = pts[shapely.contains_xy(Polygon(poly), pts[:, 0], pts[:, 1])]
    at = (inside.mean(axis=0) if len(inside) else poly.mean(axis=0)).tolist()
    how = "drawn before the void" if before else "drawn after the void"
    why = " (an exception, so the order stays ambiguous)" if flipped else ""
    if not respect:
        return RelOut(events=[{"outcome": "ignore", "at": at, "note": f"{how}: crosses it{why}"}])
    out = []
    for i, m in enumerate(dst):
        if i not in hit:
            out.append(m)
            continue
        whole = m.length()
        pieces = cut(m, hit[i], min_piece=min_stub)
        # listen's `_cut_by`: a stub shorter than min_stub goes, end pieces included (unless the line is whole)
        out += [p for p in pieces if p.length() >= min_stub or abs(p.length() - whole) < 1e-9]
    return RelOut(dst=out, events=[{"outcome": "mask", "at": at, "pieces_in": len(hit),
                                    "note": f"{how}: cut by it{why}"}])
