# FROZEN from research commit c712045: tools/gesture/gesture/kit/modulators_base.py
# Written by tools/synthesis/freeze.py; do not edit by hand (changes marked "app:").
"""Seed modulators — they write channels on placed marks (sheet mm).

- `wire`      r = 0 everywhere (explicitly a dry line; undoes earlier r).
- `constant`  set any of r / phi / W / M to a constant.
- `timing`    a dancer's tempo (library `tempo`): the pen travels the part's
              marks, in order, at the dancer's speed and ink is deposited per
              unit TIME, so stillness pools ink (r → 2, mass ∝ √dwell),
              steady flow leaves a nib held at the wrist, speed a dry line;
              the hand's lateral residual becomes tremor (research
              gesture_timing.line_profiles; the bench's `regimes=timing`).
              Burst events (signs) are not applied in v1.
- `field`     a spatial regime field over the whole sheet (research
              regime_field presets; `noise` = the bench's `regimes=field`).
              Shared by every part: seeded from the SHEET seed.

Both `timing` and `field` resample marks (step = W/4, as the research does);
every other channel follows through `Mark.remap`, so unknown channels pass.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from ._research import gesture_timing as gt
from ._research import regime_field as rf
from .core import P, modulator


def _median_channel(marks, name: str) -> float:
    vals = [m.channels[name] for m in marks if len(m)]
    return float(np.median(np.concatenate(vals))) if vals else 0.0


@modulator("wire", doc="regime 0 everywhere: a dry line")
def wire(ctx, marks):
    return [m.evolve(channels={"r": np.zeros(len(m))}) for m in marks]


def _constant_reach(p: dict) -> float:
    w = p["W"] or 0.0
    m = (p["M"] or 0.0) if (p["r"] or 0.0) > 1.0 else 0.0
    return 0.5 * max(w, m)


@modulator("constant", params=[
    P("r", "float", 1.0, "regime: 0 wire, 1 nib, 2 mass (null = leave)", min=0.0, max=2.0, optional=True),
    P("phi", "float", None, "nib angle in degrees (null = leave)", min=-90.0, max=90.0, optional=True),
    P("W", "float", None, "nib width mm (null = leave)", min=0.1, max=30.0, optional=True),
    P("M", "float", None, "mass width mm (null = leave)", min=0.5, max=60.0, optional=True),
], doc="set channels to constants", reach=_constant_reach)
def constant(ctx, marks, *, r, phi, W, M):
    vals = {"r": r, "phi": None if phi is None else math.radians(phi) % math.pi, "W": W, "M": M}
    out = []
    for m in marks:
        out.append(m.evolve(channels={k: np.full(len(m), float(v)) for k, v in vals.items() if v is not None}))
    return out


def _timing_reach(p: dict) -> float:
    return 0.5 * 1.6 * p["mass_width"] + 3.5 * p["pen"] * p["jitter_gain"] if p["amount"] > 0 else 0.0


@modulator("timing", params=[
    P("tempo", "ref", "staccato", "dance tempo profile", kind="tempo"),
    P("amount", "float", 1.0, "scales r (0 = wire, 2 = twice as heavy)", min=0.0, max=2.0),
    P("wrist_nib", "bool", True, "the nib angle follows the dancer's wrist (off: keep phi)"),
    P("mass_width", "float", 9.0, "mass width at full dwell, mm (written to M)", min=1.0, max=30.0),
    P("pen", "float", 0.4, "pen width mm: the tremor's p95 is one pen × jitter_gain", min=0.1, max=2.0),
    P("jitter_gain", "float", 1.0, "tremor amplitude (0 = no lateral residual)", min=0.0, max=4.0),
    P("q_mass", "float", 6.0, "ink-per-length ratio (to median) that becomes a full mass", min=1.5, max=30.0),
], doc="a dancer's tempo: stillness → mass, flow → nib at the wrist, speed → dry line", reach=_timing_reach)
def timing(ctx, marks, *, tempo, amount, wrist_nib, mass_width, pen, jitter_gain, q_mass):
    tm = ctx.use("tempo", tempo)
    live = [i for i, m in enumerate(marks) if len(m) >= 2 and m.length() > 0]
    if not live:
        return list(marks)
    W = _median_channel([marks[i] for i in live], "W")
    step = max(W / 4.0, 0.05)
    rs = {i: marks[i].resampled(step) for i in live}
    lens = {i: rs[i].length() for i in live}
    Ltot = sum(lens.values())
    n = max(int(round(Ltot / step)), 2)
    s_grid = np.linspace(0.0, Ltot, n + 1)
    pr = gt.line_profiles(tm, s_grid, W=W, shape_w=mass_width, pen=pen, q_mass=q_mass, jitter_gain=jitter_gain,
                          nib_from="wrist")
    phi_u = np.unwrap(2 * pr["phi"]) / 2
    out, off = list(marks), 0.0
    for i in live:
        a = rs[i]
        sg = a.arclength() + off
        r = np.clip(amount * np.interp(sg, s_grid, pr["r"]), 0.0, 2.0)
        ms = np.interp(sg, s_grid, pr["mass"])
        jit = np.interp(sg, s_grid, pr["jitter"])
        tg = np.gradient(a.points, axis=0)
        tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
        nrm = np.column_stack([-tg[:, 1], tg[:, 0]])
        ch = {"r": r, "M": ms, "tremor": jit, "dance_t": np.interp(sg, s_grid, pr["t"])}
        if wrist_nib:
            ch["phi"] = np.mod(np.interp(sg, s_grid, phi_u), np.pi)
        out[i] = a.evolve(points=a.points + nrm * jit[:, None], channels=ch, meta={"tempo": tempo})
        off += lens[i]
    return out


PRESETS = ("noise", "axis", "bands", "radial", "margins")


def make_field(preset: str, seed: int, aspect: float, scale: float):
    """A research regime field (unit sheet coords, r ∈ [0, 2])."""
    if preset == "noise":
        return rf.noise_fronts(seed, scale=scale, aspect=aspect)
    if preset == "axis":
        return rf.axis(seed=seed, aspect=aspect)
    if preset == "bands":
        return rf.bands(seed=seed, aspect=aspect)
    if preset == "radial":
        return rf.radial(seed=seed, aspect=aspect)
    return rf.margins(seed=seed, aspect=aspect)


def _field_reach(p: dict) -> float:
    # the field writes r only: allow a default 9 mm mass, plus regime's rim growth (≈ 1.25×)
    return 0.5 * 1.25 * 9.0 + 0.4 if p["amount"] > 0 else 0.0


@modulator("field", params=[
    P("preset", "choice", "noise", "noise: soft noise fronts (the bench); axis/bands/radial/margins: authored "
      "research presets", choices=PRESETS),
    P("scale", "float", 0.13, "noise correlation length, sheet widths (noise only)", min=0.02, max=0.6),
    P("amount", "float", 1.0, "scales r", min=0.0, max=2.0),
    P("smooth", "float", None, "σ along the line, mm (null = the nib width W)", min=0.0, max=50.0, optional=True),
    P("seed_offset", "int", 0, "field seed = sheet seed + this (all parts share the field)", min=0,
      max=1_000_000),
], doc="a spatial regime field over the sheet", reach=_field_reach)
def field(ctx, marks, *, preset, scale, amount, smooth, seed_offset):
    FW, FH = ctx.frame
    f = make_field(preset, int(ctx.sheet_seed) + int(seed_offset), FH / FW, scale)
    live = [i for i, m in enumerate(marks) if len(m) >= 2 and m.length() > 0]
    if not live:
        return list(marks)
    W0 = _median_channel([marks[i] for i in live], "W")
    step = max(W0 / 4.0, 0.05)
    sm = W0 if smooth is None else smooth
    out = list(marks)
    for i in live:
        q = marks[i].resampled(step)
        r = f(q.points / np.array([FW, FH]))
        if sm > 0 and len(r) > 2:
            r = gaussian_filter1d(r, sm / step, mode="nearest")
        out[i] = q.evolve(channels={"r": np.clip(amount * r, 0.0, 2.0)}, meta={"field": preset})
    return out
