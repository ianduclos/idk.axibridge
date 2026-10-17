"""Developments (round 10): rare machine events.

Ian on the round-9 handover modulator: "mixed feelings. very occasional
stairs are interesting. as an option." Systematic structure is welcome as an
accessory or an OCCASIONAL EVENT, not a texture. `handover` hands a share of
the line (default 35 %) to machines at every seam; `dev_rare_machine` hands
over only `events` short stretches per line (0 = none; a fractional part is
the chance of one more), each placed at a meaningful spot of THAT line:

  salient   the line's single strongest heard event (prosody `line_events`:
            hand switch, sharp corner, curvature peak, inflection — merged and
            ranked by salience); the machine speaks at the line's loudest moment
  switch    the hand changes (the drift's seams), the most decisive first
  quiet     the middle of the calmest stretch (longest run with no event):
            the machine fills a silence
  straight  where the hand is straightest (the attractor's own taste)
  random    anywhere (control)

Events are kept ≥ `min_gap` mm apart and away from the line's ends, so they
read as interruptions of a hand that resumes. The machine rewrite itself is
`voices_machine.hand_over` (same grammars, channels `machine` and `voice`,
meta["handover"] log) — only WHERE and HOW OFTEN changed.
"""
from __future__ import annotations

import math

import numpy as np

from .core import P, modulator
from .prosody_modulators import line_events
from .voices_machine import GRAMMARS, _opts, hand_over

PLACES = ("salient", "switch", "quiet", "straight", "random")


def _kappa_abs(p: np.ndarray, step: float) -> np.ndarray:
    d = np.diff(p, axis=0)
    th = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    k = np.abs(np.gradient(th) / step)
    return np.r_[k, k[-1:]]


def candidates(mark, place: str, rng, stretch: float) -> list[float]:
    """Arc-length centres, best first, for one placement rule."""
    q = mark.resampled(0.4)
    s = q.arclength()
    L = float(s[-1])
    if place in ("salient", "switch", "quiet"):
        evs = line_events(q)
        if place == "salient":
            return [e[0] for e in sorted(evs, key=lambda e: (-e[1], e[0]))]
        if place == "switch":
            sw = [e for e in evs if "switch" in e[2]]
            return [e[0] for e in sorted(sw, key=lambda e: (-e[1], e[0]))]
        xs = [0.0] + sorted(e[0] for e in evs) + [L]
        gaps = sorted(((b - a, 0.5 * (a + b)) for a, b in zip(xs[:-1], xs[1:])), key=lambda g: (-g[0], g[1]))
        return [g[1] for g in gaps]
    if place == "straight":
        from scipy.ndimage import gaussian_filter1d  # noqa: PLC0415
        k = gaussian_filter1d(_kappa_abs(q.points, 0.4), max(stretch / 0.4 / 3, 1.0), mode="nearest")
        return [float(s[i]) for i in np.argsort(k, kind="stable")]
    c = list(rng.uniform(0, L, 32))
    return c


def place_events(mark, *, events: float, place: str, stretch: float, min_gap: float, rng) -> list[tuple[float, float]]:
    L = mark.length()
    n = int(math.floor(events)) + int(rng.random() < events - math.floor(events))
    if n <= 0 or L <= 0:
        return []
    ln = min(stretch, 0.3 * L)
    edge = max(0.5 * ln + 5.0, 0.04 * L)
    chosen: list[tuple[float, float]] = []
    for c in candidates(mark, place, rng, ln):
        if c < edge or c > L - edge:
            continue
        a, b = c - 0.5 * ln, c + 0.5 * ln
        if any(not (b + min_gap < x0 or a - min_gap > x1) for x0, x1 in chosen):
            continue
        chosen.append((a, b))
        if len(chosen) >= n:
            break
    return sorted(chosen)


@modulator("dev_rare_machine", params=[
    P("events", "float", 1.0, "machine events per line (0 = none; 1.5 = one, and half the lines a second)",
      min=0.0, max=12.0),
    P("place", "choice", "salient", "salient (the line's loudest moment) | switch (hand change) | quiet "
      "(fills the calmest stretch) | straight | random", choices=PLACES),
    P("grammar", "choice", "stair", "the machine", choices=GRAMMARS),
    P("second", "choice", "none", "a second machine alternating with the first", choices=(*GRAMMARS, "none")),
    P("stretch", "float", 14.0, "length of one event, mm", min=2.0, max=200.0),
    P("unit", "float", 1.8, "machine unit, mm (stair pitch)", min=0.3, max=20.0),
    P("min_gap", "float", 60.0, "minimum mm between two events on a line", min=0.0, max=1000.0),
    P("k", "int", 5, "compass headings / codebook prototypes", min=2, max=16),
    P("overshoot", "float", 0.25, "ruler: corner tick, in units", min=0.0, max=1.5),
], doc="occasional machine interruptions at meaningful spots of the line (rare stairs), with a rarity control")
def dev_rare_machine(ctx, marks, *, events, place, grammar, second, stretch, unit, min_gap, k, overshoot):
    grammars = [grammar] if second == "none" else [grammar, second]
    opts = _opts(k, 72.0, "L=LSR,R=RRS,S=SL", 2, overshoot)
    out = []
    for i, m in enumerate(marks):
        if len(m) < 3 or m.length() <= 0:
            out.append(m.evolve(channels={"machine": np.zeros(len(m))}))
            continue
        rng = ctx.rng("rare", i)
        iv = place_events(m, events=events, place=place, stretch=stretch, min_gap=min_gap, rng=rng)
        q = hand_over(m, iv, grammars, rng, unit, opts)
        out.append(q.evolve(meta={"rare_machine": {"events": len(iv), "place": place,
                                                   "at": [[round(a, 2), round(b, 2)] for a, b in iv]}}))
    return out
