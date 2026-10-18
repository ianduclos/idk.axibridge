# FROZEN from research commit efce219: tools/gesture/gesture/kit/poly_converse.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""poly_converse — conversation as a composition rule (round 9 limb, thread
polyphonic_sheets; results/polyphonic_sheets-2026-10-17.md).

Units take turns. The speakers cycle through the recipe's parts (minus the
annotator). Turn 0 speaks as written. Every later turn is a REPLY DERIVED
FROM THE PREVIOUS UNIT, from statistics measured on the line it drew:

- **hand**: the previous unit's line statistics (turning per radius of
  gyration, straight share, compactness: all scale-free) are compared with
  a probe line of every hand in the pool. `contrast` answers in the
  most unlike hand; `echo` in the most alike (never the same hand);
  `alternate` switches between them turn by turn. A voice with a `hand` ref
  param gets the hand; one with `hands` refs gets the route
  [the caller's hand → the reply hand], so the reply begins in the caller's
  voice and drifts away (`continue`). Other voices keep their own grammar
  and are only placed, sized and weighted by the rule.
- **length**: a busy call (high turning) gets a short reply, a calm one a
  long reply (voices with a `length` param).
- **weight** (`weight: invert`): a heavy call (mean regime r > 0.5 after its
  modulators) gets a dry reply (a `wire` modulator appended); a dry call
  keeps the speaker's own chain.
- **place**: the reply starts where the call ended, a gap away, along the
  call's last heading; among 8 orientations it takes the one that keeps
  its first heading closest to the call's while overlapping least and
  staying on the sheet. If no orientation fits, the reply starts a new
  topic in the emptiest place.

Annotation (`annotate` …) as in poly_sheets, over the finished exchange.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from .core import P, RecipeError, arranger, get
from .poly_sheets import (_ANNOT_PARAMS, Unit, _annotator_index, _at_native, _bbox, _native_size, _overlap,
                          _rotate, annotate_units, clip_marks)

REPLIES = ("contrast", "echo", "alternate")


def line_stats(marks) -> np.ndarray:
    """Scale-free statistics of a unit's line(s): [log turning per radius of
    gyration, straight share, log compactness (rg / length)]."""
    pts = [m.points for m in marks if len(m) >= 3]
    if not pts:
        return np.zeros(3)
    allp = np.vstack(pts)
    rg = float(np.sqrt(((allp - allp.mean(axis=0)) ** 2).sum(axis=1).mean())) + 1e-9
    L, turn, straight, nseg = 0.0, 0.0, 0.0, 0
    for p in pts:
        d = np.diff(p, axis=0)
        sl = np.linalg.norm(d, axis=1)
        keep = sl > 1e-9
        d, sl = d[keep], sl[keep]
        if len(d) < 2:
            continue
        # resample-free turning: angle change per segment
        a = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
        da = np.abs(np.diff(a))
        L += float(sl.sum())
        turn += float(da.sum())
        k = da / np.maximum(0.5 * (sl[1:] + sl[:-1]), 1e-9)          # curvature per mm
        straight += float(np.sum(sl[1:] * (k * rg < 0.5)))
        nseg += 1
    if L <= 0:
        return np.zeros(3)
    return np.array([math.log(turn * rg / L + 1e-6), straight / L, math.log(rg / L)])


def _ends(marks):
    """(start point, start heading, end point, end heading) of a unit."""
    first = max(marks[:1], key=len)
    last = marks[-1]

    def head(p, rev):
        n = len(p)
        k = max(2, n // 30)
        v = (p[-1] - p[-1 - k]) if rev else (p[k] - p[0])
        nv = np.linalg.norm(v)
        return v / nv if nv > 1e-9 else np.array([1.0, 0.0])
    return first.points[0], head(first.points, False), last.points[-1], head(last.points, True)


def _hand_param(module, kind="hand"):
    for p in module.params:
        if p.kind == kind and p.type in ("ref", "refs"):
            return p
    return None


def _reply_spec(spec, prev_hand, new_hand, length_k, dry):
    vs = copy.deepcopy(spec["voice"])
    mod = get("voice", vs["id"])
    hp = _hand_param(mod)
    if hp is not None and new_hand is not None:
        if hp.type == "ref":
            vs[hp.name] = new_hand
        else:
            route = [h for h in (prev_hand, new_hand) if h]
            if len(route) == 2 and route[0] == route[1]:
                route = route[:1]
            vs[hp.name] = route[:hp.max_len] if hp.max_len else route
    try:
        lp = mod.param("length")
        vs["length"] = float(np.clip(vs.get("length", lp.default) * length_k, lp.min, lp.max))
    except KeyError:
        pass
    out = copy.deepcopy(spec)
    out["voice"] = mod.validate(vs, where=f"poly_converse reply ({vs['id']})")
    if dry:
        out["modulators"] = list(out["modulators"]) + [{"id": "wire"}]
    return out


@arranger("poly_converse", params=[
    P("turns", "int", 12, "number of units in the exchange", min=2, max=40),
    P("reply", "choice", "contrast", "contrast: answer in the most unlike hand; echo: the most alike (never the "
      "same); alternate: contrast, echo, contrast, …", choices=REPLIES),
    P("pool", "str", "", "space-separated hands a reply may use (empty: every generative library hand)"),
    P("size", "float", 0.25, "a unit's long side, share of the sheet's short side", min=0.04, max=0.9),
    P("memory", "int", 2, "a reply avoids the hands of the last N turns (0 = only the caller's), so a contrast "
      "exchange travels instead of ping-ponging between two extremes", min=0, max=8),
    P("gap", "float", 10.0, "distance from the call's end to the reply's start, mm", min=0.0, max=60.0),
    P("weight", "choice", "invert", "invert: a heavy call gets a dry reply; keep: replies keep their chain",
      choices=("invert", "keep")),
    P("length_follow", "float", 0.5, "how strongly reply length answers the call's busyness "
      "(0 = fixed length)", min=0.0, max=1.5),
    *_ANNOT_PARAMS,
], doc="units take turns; each reply's hand, length, weight and start derive from the previous unit")
def poly_converse(ctx, parts, *, turns, reply, pool, size, memory, gap, weight, length_follow,
                  annotate, annotator, n_annot, annot_amp):
    a_idx = _annotator_index(parts, annotator, annotate)
    speakers = [i for i in range(len(parts)) if i != a_idx]
    lib = ctx.run.library
    hands = pool.split() or [h for h in lib.ids("hand") if lib.entry("hand", h).get("policy") == "generative"]
    missing = [h for h in hands if not lib.has("hand", h)]
    if missing:
        raise RecipeError(f"poly_converse pool: no library hand {missing}")
    x0, y0, W, H = ctx.box
    short = min(W, H)
    rng = ctx.rng("converse")
    # probe statistics per hand: one short line each, the same seed for all
    probe_mod = get("voice", "hand")
    probes = {}
    for h in hands:
        pm = probe_mod.fn(parts[speakers[0]].ctx("voice", "poly_probe", ctx.box), hand=h, length=1.2,
                          joins="smooth")
        probes[h] = line_stats(pm)
    P_ = np.array([probes[h] for h in hands])
    spread = np.maximum(P_.std(axis=0), 1e-6)
    turn_ref = float(np.median(P_[:, 0]))
    units, out, log = [], [], []
    prev = None
    for t in range(turns):
        si = speakers[t % len(speakers)]
        part = parts[si]
        spec = part.spec
        new_hand, prev_hand, mode_t = None, None, None
        if prev is not None:
            f_prev = prev["stats"]
            prev_hand = prev["hand"]
            mode_t = reply if reply != "alternate" else ("contrast" if t % 2 else "echo")
            recent = {e["hand"] for e in log[-memory:]} if memory else set()
            cands = [h for h in hands if h != prev_hand and h not in recent] or \
                    [h for h in hands if h != prev_hand] or hands
            d = [float(np.linalg.norm((probes[h] - f_prev) / spread)) for h in cands]
            new_hand = cands[int(np.argmax(d) if mode_t == "contrast" else np.argmin(d))]
            busy = f_prev[0] - turn_ref
            length_k = float(np.exp(-length_follow * busy))
            dry = weight == "invert" and prev["r"] > 0.5
            spec = _reply_spec(spec, prev_hand, new_hand, length_k, dry)
            if not all(lib.has("hand", h) for h in [new_hand]):
                raise RecipeError(f"poly_converse: hand {new_hand} vanished from the library")
        from .poly_sheets import _variant
        q = _variant(part, t, spec=spec)
        grown = q.voice(ctx.box)
        if not grown:
            continue
        n_ = _native_size(grown)
        k = size * short * rng.uniform(0.85, 1.15) / max(float(n_.max()), 1e-9)
        base = _at_native(grown, k, (0.0, 0.0))
        best = None
        for turn in range(4):
            for flip in (False, True):
                cand = _rotate(base, turn, flip)
                s0, h0, _, _ = _ends(cand)
                if prev is None:
                    anchor = np.array([x0 + rng.uniform(0.2, 0.45) * W, y0 + rng.uniform(0.3, 0.7) * H])
                    off = anchor - (np.vstack([m.points for m in cand]).mean(axis=0))
                    align = 0.0
                else:
                    off = prev["end"] + gap * prev["head"] - s0
                    align = float(np.dot(h0, prev["head"]))
                lo, hi = _bbox(cand)
                bx = (lo[0] + off[0], lo[1] + off[1], hi[0] - lo[0], hi[1] - lo[1])
                ov = sum(_overlap(bx, u.box, 0.0) for u in units)
                ix = max(0.0, min(bx[0] + bx[2], x0 + W) - max(bx[0], x0))
                iy = max(0.0, min(bx[1] + bx[3], y0 + H) - max(bx[1], y0))
                inside = ix * iy / max(bx[2] * bx[3], 1e-9)
                cost = 4.0 * ov + 2.0 * (1 - inside) - 0.6 * align + 0.01 * rng.random()
                if best is None or cost < best[0]:
                    best = (cost, cand, off, inside, ov)
        cost, cand, off, inside, ov = best
        topic = False
        if prev is not None and (inside < 0.45 or ov > 0.35):
            topic = True                                  # a new topic: the emptiest place
            pts = np.vstack([m.points[::max(1, len(m) // 100)] for u in units for m in u.marks])
            trial = rng.uniform([x0, y0], [x0 + W, y0 + H], size=(200, 2))
            far = trial[np.argmax(np.min(np.linalg.norm(trial[:, None] - pts[None], axis=2), axis=1))]
            cand = _rotate(base, int(rng.integers(4)))
            off = far - np.vstack([m.points for m in cand]).mean(axis=0)
        placed = [m.transformed(1.0, off).evolve(meta={"turn": t, "reply": mode_t, "hand_reply": new_hand,
                                                        "new_topic": topic})
                  for m in cand]
        placed = clip_marks(placed, ctx.box)
        if not placed:
            continue
        u = Unit(len(units), si, placed)
        mod = q.modulate(placed, u.box)
        units.append(u)
        out += mod
        r_mean = float(np.mean(np.concatenate([m.channels["r"] for m in mod]))) if mod else 0.0
        _, _, e, he = _ends(placed)
        hand_used = new_hand
        if hand_used is None:
            hp = _hand_param(get("voice", spec["voice"]["id"]))
            v = spec["voice"].get(hp.name) if hp else None
            hand_used = v[-1] if isinstance(v, list) else v
        prev = {"stats": line_stats(placed), "hand": hand_used, "r": r_mean, "end": e, "head": he}
        log.append({"turn": t, "hand": hand_used, "reply": mode_t, "r": round(r_mean, 2), "topic": topic})
    if out:
        out[0] = out[0].evolve(meta={"converse_log": log})
    if a_idx is not None:
        out += annotate_units(ctx, parts, units, a_idx, annotate, n_annot, annot_amp)
    return out
