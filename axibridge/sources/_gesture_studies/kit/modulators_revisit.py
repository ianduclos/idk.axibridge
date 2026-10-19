# FROZEN from research commit c712045: tools/gesture/gesture/kit/modulators_revisit.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""Notation: the body's events written as signs grown from its own line
(round 12, thread `revisit`, 2026-10-17).

Revisits round 7 ("signs as line events", `gesture/signs.py`): there the
sign vocabulary was sampled from a grammar fitted to a reference image, and
the blind judge showed the learned *placement* meant nothing (4/12, chance):
attachment carried "belonging", not the statistics. What round 7 never had
was a reason for *which* sign appears *where*.

Here the reason is the dance. The `dance` voice keeps the body's own clock
on every point (`dance_t`, `dance_speed`, `dance_acc`). This modulator reads
KINDS of event off that clock — a hold, a reversal, a launch, two limbs
meeting, a phrase ending — and writes them on the mark as discrete events
(`meta["revisit_events"]`), each kind always spelled by the same sign
operator (the `code`). The renderer `revisit_signs` grows the signs from the
line (round-7 operators). One kind, one sign, recurring with size by
intensity: the drawing becomes a notation whose code the eye half-reads.

Events (per mark, indices into its points):
- hold:    speed below `still` × the sheet's p90 for ≥ `min_hold_s`;
           strength = seconds held; sited at the slowest sample.
- reverse: a local speed minimum (not inside a hold) where the heading in
           and out (± `turn_s`) differ by ≥ `reverse_deg`; strength = angle.
- launch:  an acceleration peak above the sheet's `launch_q` quantile while
           still slow (speed < 0.6 × p90); strength = acc / p90 acc.
- meet:    a point within `meet_mm` of ANOTHER effector's line at nearly the
           same dance time (|Δt| < `meet_s`): two limbs touch; both lines get
           the sign (a junction event). strength = 1 − dist / meet_mm.
- end:     the mark's last point (each mark ends at a phrase cut, i.e. at
           whole-body stillness).
"""
from __future__ import annotations

import math

import numpy as np

from .core import P, modulator

KINDS = ("hold", "reverse", "launch", "meet", "end")
# ops the round-7 renderer knows, by where they may sit
INTERIOR_OPS = ("knot", "bead", "vessel_mid", "nib", "comma", "comb", "drip", "body", "junction_mass")
END_OPS = ("drop", "lozenge", "hook", "ring", "block", "vessel", "eye", "detached")
DEFAULT_CODE = "hold=knot,reverse=comma,launch=comb,meet=body,end=hook"
# base size per op (× size_mm): round-7 reference sizes in line widths, folded to a common scale
OP_SIZE = {"knot": 1.6, "bead": 0.9, "vessel_mid": 2.4, "nib": 3.0, "comma": 1.2, "comb": 1.1, "drip": 1.0,
           "body": 1.5, "junction_mass": 1.0, "drop": 0.9, "lozenge": 1.3, "hook": 1.6, "ring": 1.3,
           "block": 1.5, "vessel": 4.0, "eye": 1.6, "detached": 0.8, "none": 0.0}
PRIORITY = {"meet": 0, "hold": 1, "reverse": 2, "launch": 3}


def parse_code(code: str) -> dict:
    """'hold=knot,reverse=comma' -> {kind: op}; unknown kinds/ops raise.
    A kind left out (or mapped to 'none') is not written."""
    out = {}
    for item in [c.strip() for c in code.split(",") if c.strip()]:
        k, _, op = item.partition("=")
        k, op = k.strip(), op.strip()
        if k not in KINDS:
            raise ValueError(f"notation code: unknown event kind {k!r} (kinds: {KINDS})")
        ok = END_OPS if k == "end" else INTERIOR_OPS
        if op != "none" and op not in ok:
            raise ValueError(f"notation code: {k}={op!r} is not one of {ok}")
        if op != "none":
            out[k] = op
    return out


def _runs(idx: np.ndarray) -> list[np.ndarray]:
    if not len(idx):
        return []
    return np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)


def _at_time(t: np.ndarray, x: float) -> int:
    return int(np.clip(np.searchsorted(t, x), 0, len(t) - 1))


def detect(marks, *, still=0.12, min_hold_s=0.3, merge_s=0.35, reverse_deg=120.0, turn_s=0.15,
           launch_q=0.9, meet_mm=2.5, meet_s=0.4) -> list[list[dict]]:
    """Events per mark (lists of {kind, i, t, strength[, other]}). Marks
    without the dance clock get none. Deterministic: no randomness here."""
    live = [k for k, m in enumerate(marks) if "dance_speed" in m.channels and "dance_t" in m.channels
            and len(m) >= 4]
    out: list[list[dict]] = [[] for _ in marks]
    if not live:
        return out
    v_ref = float(np.percentile(np.concatenate([marks[k]["dance_speed"] for k in live]), 90)) or 1.0
    accs = [marks[k]["dance_acc"] for k in live if "dance_acc" in marks[k].channels]
    a_all = np.concatenate(accs) if accs else np.zeros(1)
    a_thr = float(np.quantile(a_all, launch_q))
    a_ref = float(np.percentile(a_all, 90)) or 1.0
    for k in live:
        m = marks[k]
        t = np.asarray(m["dance_t"], float)
        v = np.asarray(m["dance_speed"], float) / v_ref
        a = np.asarray(m["dance_acc"], float) if "dance_acc" in m.channels else np.zeros(len(m))
        pts = m.points
        ev = []
        # holds
        held = np.zeros(len(m), bool)
        runs = _runs(np.flatnonzero(v < still))
        merged: list[np.ndarray] = []
        for r in runs:
            if merged and t[r[0]] - t[merged[-1][-1]] < merge_s:
                merged[-1] = np.r_[merged[-1], r]
            else:
                merged.append(r)
        for r in merged:
            dur = float(t[min(r[-1] + 1, len(t) - 1)] - t[r[0]])
            held[r[0]:r[-1] + 1] = True
            if dur >= min_hold_s:
                j = int(r[int(np.argmin(v[r]))])
                ev.append({"kind": "hold", "i": j, "t": float(t[j]), "strength": dur})
        # reversals at speed minima outside holds
        for j in range(1, len(m) - 1):
            if held[j] or not (v[j] <= v[j - 1] and v[j] <= v[j + 1]):
                continue
            j0, j1 = _at_time(t, t[j] - turn_s), _at_time(t, t[j] + turn_s)
            if j0 >= j or j1 <= j:
                continue
            din, dout = pts[j] - pts[j0], pts[j1] - pts[j]
            if np.hypot(*din) < 1e-6 or np.hypot(*dout) < 1e-6:
                continue
            ang = math.degrees(abs(math.atan2(din[0] * dout[1] - din[1] * dout[0], float(din @ dout))))
            if ang >= reverse_deg:
                ev.append({"kind": "reverse", "i": j, "t": float(t[j]), "strength": ang})
        # launches: acc peaks while slow
        for j in range(1, len(m) - 1):
            if a[j] >= a_thr and a[j] >= a[j - 1] and a[j] >= a[j + 1] and v[j] < 0.6 and not held[j]:
                ev.append({"kind": "launch", "i": j, "t": float(t[j]), "strength": float(a[j] / a_ref)})
        ev.append({"kind": "end", "i": len(m) - 1, "t": float(t[-1]), "strength": 1.0})
        out[k] = ev
    # meetings between different effectors at nearly the same time
    from scipy.spatial import cKDTree
    for ai, k in enumerate(live):
        for l in live[ai + 1:]:
            jk, jl = marks[k].meta.get("joint"), marks[l].meta.get("joint")
            if jk is not None and jk == jl:
                continue
            tk, tl = np.asarray(marks[k]["dance_t"]), np.asarray(marks[l]["dance_t"])
            if tk[-1] < tl[0] - meet_s or tl[-1] < tk[0] - meet_s:
                continue
            tree = cKDTree(marks[l].points)
            d, j = tree.query(marks[k].points, distance_upper_bound=meet_mm)
            hit = np.flatnonzero(np.isfinite(d) & (np.abs(tk - tl[np.minimum(j, len(tl) - 1)]) < meet_s))
            for r in _runs(hit):
                b = int(r[int(np.argmin(d[r]))])
                st = float(1 - d[b] / meet_mm)
                out[k].append({"kind": "meet", "i": b, "t": float(tk[b]), "strength": st,
                               "other": [int(l), int(j[b])]})
    return out


def _space(evs, s, min_gap):
    """Keep events at least min_gap mm apart along the line (priority, then time)."""
    keep: list[dict] = []
    for e in sorted(evs, key=lambda e: (e["kind"] == "end", PRIORITY.get(e["kind"], 9), e["t"])):
        if e["kind"] == "end" or all(abs(s[e["i"]] - s[q["i"]]) >= min_gap for q in keep if q["kind"] != "end"):
            keep.append(e)
    return sorted(keep, key=lambda e: e["t"])


def _size(kind: str, op: str, strength: float, size_mm: float) -> float:
    base = OP_SIZE.get(op, 1.0) * size_mm
    f = {"hold": lambda x: float(np.clip(0.6 + 0.8 * math.sqrt(x), 0.7, 2.2)),
         "reverse": lambda x: float(np.clip((x - 90) / 90, 0.6, 1.3)),
         "launch": lambda x: float(np.clip(0.6 + 0.3 * x, 0.6, 1.6)),
         "meet": lambda x: float(np.clip(0.7 + 0.6 * x, 0.7, 1.3)),
         "end": lambda x: 1.0}[kind]
    return base * f(strength)


@modulator("revisit_notate", params=[
    P("code", "str", DEFAULT_CODE, "which sign spells which event: kind=op pairs; kinds hold / reverse / launch / "
      "meet / end; interior ops " + "/".join(INTERIOR_OPS) + "; end ops " + "/".join(END_OPS) + "; 'none' = silent"),
    P("size_mm", "float", 2.2, "sign scale, mm (× each op's base size × the event's strength)", min=0.3, max=20.0),
    P("still", "float", 0.12, "hold: speed below this share of the sheet's p90", min=0.01, max=0.6),
    P("min_hold_s", "float", 0.3, "hold: shortest stillness that is written (dance seconds)", min=0.0, max=5.0),
    P("reverse_deg", "float", 125.0, "reverse: heading change at a speed minimum", min=45.0, max=180.0),
    P("launch_q", "float", 0.9, "launch: acceleration quantile (of the whole sheet)", min=0.5, max=0.995),
    P("meet_mm", "float", 2.5, "meet: how close two limbs' lines come", min=0.0, max=20.0),
    P("meet_s", "float", 0.4, "meet: how close in dance time", min=0.0, max=10.0),
    P("gap_mm", "float", 6.0, "fewest mm between two signs on one line", min=0.0, max=60.0),
    P("source", "choice", "detect", "detect: read events off the dance clock | stops: write a `hold` at every stop "
      "the revisit_glyph voice recorded (meta['figures']), so other answers sit at exactly the same places",
      choices=("detect", "stops")),
    P("max_per_line", "int", 6, "most signs on one line (most important kinds first)", min=0, max=60),
], doc="notation: the body's events (hold, reversal, launch, meeting, phrase end) written on its own line, "
       "each kind always spelled by the same sign")
def revisit_notate(ctx, marks, *, code, size_mm, still, min_hold_s, reverse_deg, launch_q, meet_mm, meet_s,
                   gap_mm, source, max_per_line):
    cmap = parse_code(code)
    if source == "stops":
        raw = []
        for m in marks:
            t = np.asarray(m["dance_t"], float) if "dance_t" in m.channels else None
            evs = []
            for f in m.meta.get("figures", []) if t is not None else []:
                i = int(np.argmin(np.abs(t - f["t_stop"])))
                evs.append({"kind": "hold", "i": i, "t": float(t[i]), "strength": float(f["t1"] - f["t0"])})
            evs.append({"kind": "end", "i": len(m) - 1, "t": float(t[-1]) if t is not None else 0.0,
                        "strength": 1.0})
            raw.append(evs)
    else:
        raw = detect(marks, still=still, min_hold_s=min_hold_s, reverse_deg=reverse_deg, launch_q=launch_q,
                     meet_mm=meet_mm, meet_s=meet_s)
    out = []
    for k, m in enumerate(marks):
        s = m.arclength()
        evs = [e for e in raw[k] if e["kind"] in cmap]
        evs = _space(evs, s, gap_mm)
        inner = [e for e in evs if e["kind"] != "end"]
        if len(inner) > max_per_line:
            inner = sorted(sorted(inner, key=lambda e: (PRIORITY[e["kind"]], -e["strength"], e["t"]))[:max_per_line],
                           key=lambda e: e["t"])
        evs = inner + [e for e in evs if e["kind"] == "end"]
        written = []
        for e in evs:
            op = cmap[e["kind"]]
            d = {"kind": e["kind"], "op": op, "s": float(s[e["i"]]), "t": round(e["t"], 4),
                 "strength": round(float(e["strength"]), 4), "size": round(_size(e["kind"], op, e["strength"], size_mm), 4)}
            if "other" in e:
                l, j = e["other"]
                d["other"] = [l, float(marks[l].arclength()[j])]
            written.append(d)
        out.append(m.evolve(meta={"revisit_events": written}))
    return out
