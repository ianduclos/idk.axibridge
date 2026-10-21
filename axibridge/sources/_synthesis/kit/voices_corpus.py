# FROZEN from research commit d5ccd75: tools/gesture/gesture/kit/voices_corpus.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Voices from corpora (round 9, thread voices_corpus, 2026-10-17).

- library kind `dance_trail`: frozen end-effector trails of one dance window
  (front view, body-height units, y down) with per-frame speed /
  acceleration and whole-body energy. Built by
  `experiments/voices_corpus.py learn`; decoded here.
- voice `dance`: the dance drawing itself — the trails as they were danced,
  cut into phrases at whole-body stillness. Keeps the dance's own clock:
  channels `dance_t` (s into the window), `dance_speed` (body heights / s)
  and `dance_acc` (/ s²), so a modulator can read the body's timing instead
  of a borrowed tempo.
- modulator `own_tempo`: regimes from the line's OWN dance channels
  (research `dance.kinematic_r`): stillness → mass bead, acceleration while
  slow → nib, speed → dry wire. Default `beads="pauses"`: one bead at the
  slowest point of each pause, so a standing foot is one bead, not a bar. Mostly wire with sparse beads, as in the
  round-8 dance drawing Ian singled out. Marks without dance channels pass
  unchanged.

The new hands (dance qualities, CMU-55 mimes, early computer art) are plain
library `hand` entries: use them with the seed `hand` / `drift` voices.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.ndimage import maximum_filter1d

from . import library
from .core import P, fitted, modulator, voice

EFFECTORS = ("lhand", "rhand", "lfoot", "rfoot", "head")
EFFECTOR_SETS = {
    "all": EFFECTORS, "hands": ("lhand", "rhand"), "feet": ("lfoot", "rfoot"),
    "hands+head": ("lhand", "rhand", "head"), "lhand": ("lhand",), "rhand": ("rhand",), "head": ("head",),
}


@library.loader("dance_trail")
def _load_dance_trail(entry: dict, folder: Path):
    arrays = library.read_npz(folder / entry["files"]["trail"])
    for v in arrays.values():
        v.setflags(write=False)
    return {"entry": entry, "fps": float(entry["provenance"]["fps"]), **arrays}


def phrase_cuts(energy: np.ndarray, fps: float, *, q: float = 0.3, min_gap_s: float = 1.2) -> np.ndarray:
    """Frame indices of phrase boundaries (research `dance.phrase_cuts`, on
    the frozen energy): local minima below the q-quantile, ≥ min_gap_s apart,
    lowest kept first."""
    e = np.asarray(energy, float)
    if len(e) < 3:
        return np.zeros(0, int)
    thr = np.quantile(e, q)
    loc = np.where((e[1:-1] <= e[:-2]) & (e[1:-1] <= e[2:]) & (e[1:-1] < thr))[0] + 1
    gap = int(min_gap_s * fps)
    keep: list[int] = []
    for i in loc[np.lexsort((loc, e[loc]))]:          # by energy, ties by index: deterministic
        if all(abs(int(i) - k) >= gap for k in keep):
            keep.append(int(i))
    return np.array(sorted(keep), int)


def _dedupe(p, t, v, a, eps):
    """Drop points closer than eps to the last kept one; speed folds by MIN
    (a pause keeps its stillness), acceleration by MAX, time keeps the first."""
    keep = [0]
    for i in range(1, len(p)):
        if np.hypot(*(p[i] - p[keep[-1]])) >= eps:
            keep.append(i)
    k = np.array(keep)
    return p[k], t[k], np.minimum.reduceat(v, k), np.maximum.reduceat(a, k)


@voice("dance", params=[
    P("trail", "ref", "levitation", "the frozen dance window", kind="dance_trail"),
    P("effectors", "choice", "all", "which body ends draw", choices=tuple(EFFECTOR_SETS)),
    P("t0", "float", 0.0, "start, seconds into the frozen window", min=0.0, max=60.0),
    P("seconds", "float", 15.0, "how much of the dance (longer windows overdraw into scribble)", min=1.0, max=60.0),
    P("cut", "choice", "phrase", "phrase: one line per effector per phrase (cut at whole-body stillness); "
      "none: one line per effector", choices=("phrase", "none")),
], doc="the dance drawing itself: end-effector trails with the dance's own clock as channels")
def dance(ctx, *, trail, effectors, t0, seconds, cut):
    tr = ctx.use("dance_trail", trail)
    fps = tr["fps"]
    n = len(tr["energy"])
    a0 = min(int(round(t0 * fps)), max(n - 3, 0))
    a1 = min(a0 + max(int(round(seconds * fps)), 3), n)
    cuts = phrase_cuts(tr["energy"][a0:a1], fps) if cut == "phrase" else np.zeros(0, int)
    bounds = [0, *cuts.tolist(), a1 - a0 - 1]
    t_all = np.arange(a1 - a0) / fps
    polys, chans, metas = [], [], []
    for name in EFFECTOR_SETS[effectors]:
        p = np.asarray(tr[f"{name}_xy"][a0:a1], float)
        v = np.asarray(tr[f"{name}_v"][a0:a1], float)
        acc = np.asarray(tr[f"{name}_a"][a0:a1], float)
        for k, (b0, b1) in enumerate(zip(bounds[:-1], bounds[1:])):
            if b1 - b0 < 3:
                continue
            sl = slice(b0, b1 + 1)
            q, tt, vv, aa = _dedupe(p[sl], t_all[sl], v[sl], acc[sl], 0.0008)
            if len(q) < 3:
                continue
            polys.append(q)
            chans.append({"dance_t": tt + t0, "dance_speed": vv, "dance_acc": aa})
            metas.append({"joint": name, "phrase": k, "voices": [f"dance:{trail}"], "trail": trail})
    if not polys:
        raise ValueError(f"dance trail {trail!r}: nothing in [{t0}, {t0 + seconds}) s")
    # drop specks: lines shorter than 4 % of the longest bbox side (README contract of research trails)
    allp = np.vstack(polys)
    R = float(np.hypot(*(allp.max(0) - allp.min(0))))
    keep = [i for i, q in enumerate(polys) if np.sum(np.hypot(*np.diff(q, axis=0).T)) >= 0.04 * R] or [0]
    return fitted([polys[i] for i in keep], ctx.box, [chans[i] for i in keep], [metas[i] for i in keep])


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _own_tempo_reach(p: dict) -> float:
    return 0.5 * 1.25 * p["mass_width"] + 0.4 if p["amount"] > 0 else 0.0


@modulator("own_tempo", params=[
    P("amount", "float", 1.0, "scales r (0 = wire)", min=0.0, max=2.0),
    P("still", "float", 0.12, "speed (share of the reference speed) below which the body is still → mass",
      min=0.01, max=0.6),
    P("nib", "float", 0.25, "how much acceleration while slow becomes nib (0 = beads on wire only)",
      min=0.0, max=1.0),
    P("norm", "choice", "self", "self: reference speed = this sheet's p90; absolute: v_ref body heights/s "
      "(so Staccato and Levitation keep their different weights)", choices=("self", "absolute")),
    P("v_ref", "float", 1.5, "reference speed for norm=absolute, body heights / s", min=0.05, max=20.0),
    P("a_ref", "float", 8.0, "reference acceleration for norm=absolute, body heights / s²", min=0.1, max=200.0),
    P("beads", "choice", "pauses", "pauses: one bead at the slowest point of each pause (sparse beads on wire); "
      "dwell: every still sample is mass (a standing foot becomes a bar)", choices=("pauses", "dwell")),
    P("min_pause_s", "float", 0.25, "beads=pauses: shortest stillness (dance seconds) that earns a bead",
      min=0.0, max=5.0),
    P("merge_s", "float", 0.6, "beads=pauses: stillnesses closer than this (dance seconds) are one pause",
      min=0.0, max=5.0),
    P("bead_mm", "float", 1.2, "a pause is dilated over ± this much arc so it gets visible size", min=0.0,
      max=10.0),
    P("mass_width", "float", 3.0, "bead (mass) width, mm (written to M)", min=0.5, max=30.0),
], doc="regimes from the line's own dance clock: stillness → bead, slow acceleration → nib, speed → wire",
    reach=_own_tempo_reach)
def own_tempo(ctx, marks, *, amount, still, nib, norm, v_ref, a_ref, beads, min_pause_s, merge_s, bead_mm, mass_width):
    live = [i for i, m in enumerate(marks) if "dance_speed" in m.channels and len(m) >= 2 and m.length() > 0]
    if not live:
        return list(marks)
    if norm == "self":
        v_ref = float(np.percentile(np.concatenate([marks[i]["dance_speed"] for i in live]), 90))
        a_ref = float(np.percentile(np.concatenate([marks[i]["dance_acc"] for i in live]), 90)) \
            if all("dance_acc" in marks[i].channels for i in live) else 1.0
    step = 0.25
    out = list(marks)
    for i in live:
        m = marks[i]
        # keep the slowest sample in each step bin: resampling must not interpolate a pause away
        s = m.arclength()
        q = m.resampled(step)
        sq = q.arclength()
        b = np.clip(np.searchsorted(sq, s), 0, len(sq) - 1)
        vmin = np.array(q["dance_speed"], float)
        np.minimum.at(vmin, b, np.asarray(m["dance_speed"], float))
        acc = np.array(q["dance_acc"], float) if "dance_acc" in q.channels else np.zeros(len(q))
        vn = vmin / max(v_ref, 1e-9)
        an = acc / max(a_ref, 1e-9)
        mass = _smoothstep((still - vn) / (0.6 * still))
        if beads == "pauses":
            # one bead per pause: a run below the stillness threshold keeps only its slowest point
            # (a foot standing for seconds is ONE bead, not a solid bar)
            below = vn < still
            peak = np.zeros_like(mass)
            idx = np.flatnonzero(below)
            tq = np.asarray(q["dance_t"], float) if "dance_t" in q.channels else np.arange(len(q)) * 0.01
            if len(idx):
                runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
                merged = [runs[0]]
                for run in runs[1:]:                   # pauses closer than merge_s (dance time) are one pause
                    if tq[run[0]] - tq[merged[-1][-1]] < merge_s:
                        merged[-1] = np.r_[merged[-1], run]
                    else:
                        merged.append(run)
                for run in merged:
                    dur = tq[min(run[-1] + 1, len(tq) - 1)] - tq[run[0]]
                    if dur < min_pause_s:              # a flicker below threshold is not a pause
                        continue
                    j = run[int(np.argmin(vn[run]))]
                    peak[j] = mass[j]
            mass = peak
        d = int(round(bead_mm / step))
        if d > 0:
            mass = maximum_filter1d(mass, 2 * d + 1, mode="nearest")
        nb = nib * _smoothstep((an - 0.3) / 0.45) * (1 - _smoothstep((vn - 0.75) / 0.35))
        r = np.clip(amount * (2.0 * mass + nb * (1 - mass)), 0.0, 2.0)
        out[i] = q.evolve(channels={"r": r, "M": np.full(len(q), float(mass_width))},
                          meta={"own_tempo": {"norm": norm, "v_ref": v_ref}})
    return out
