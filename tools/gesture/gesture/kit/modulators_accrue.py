"""Round 13, thread II-c `accrue` — ink the accumulated state.

`accrue_ink` reads the `acc_*` channels that `accrue_walk` writes and turns
them into the regime channels r / phi / W / M:

  free line            wire (r = 0)
  curl building        the pen presses: r rises toward nib as |C| nears c_max
  knot                 mass (r → 2): the choked coil becomes a bead
  release              the nib carries the spin it was handed: phi turns at
                       Ω rad/mm (integrated along the line), r = nib while
                       |Ω| is above `spin_floor`, so the ribbon goes barbs →
                       twist → calm and then dries back to wire.

Nothing here is a driver: every input is the line's own history.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .core import P, modulator


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _sm(v: np.ndarray, sigma_mm: float, step: float) -> np.ndarray:
    if sigma_mm <= 0 or len(v) < 3:
        return v
    return gaussian_filter1d(v, max(sigma_mm / max(step, 1e-6), 0.5), mode="nearest")


def ink_channels(m, *, curl_on, curl_r, spin_floor, spin_full, W, M, phi0, smooth):
    c = m.channels
    s = m.arclength()
    step = float(np.median(np.diff(s))) if len(s) > 2 else 1.0
    curl = c["acc_curl"]
    spin = c["acc_spin"]
    knot = c["acc_knot"]
    r_curl = curl_r * _ss((curl - curl_on) / max(1 - curl_on, 1e-6))
    a = np.abs(spin)
    r_spin = _ss((a - spin_floor) / max(spin_full - spin_floor, 1e-9))
    r = np.maximum(r_curl, r_spin)
    r = _sm(r, smooth, step)
    r = np.maximum(r, 1.0 + _sm(knot, smooth * 0.5, step)) * (knot > 1e-3) + r * (knot <= 1e-3)
    r = np.clip(r, 0, 2)
    ds = np.r_[0.0, np.diff(s)]
    phi = np.deg2rad(phi0) + np.cumsum(spin * ds)
    return {"r": r, "phi": phi, "W": np.full(len(s), W), "M": np.full(len(s), M)}


def _reach(p):
    return 0.5 * max(p["W"], p["M"])


@modulator("accrue_ink", params=[
    P("curl_on", "float", 0.35, "curl share (|C|/c_max) where the pen starts to press", min=0.0, max=0.99),
    P("curl_r", "float", 1.0, "regime reached at full curl (1 = nib)", min=0.0, max=1.6),
    P("spin_floor", "float", 0.04, "nib spin (rad/mm) below which the ribbon dries to wire", min=0.0, max=5.0),
    P("spin_full", "float", 0.15, "nib spin at which the ribbon is full nib", min=0.001, max=10.0),
    P("W", "float", 2.2, "nib width, mm", min=0.2, max=20.0),
    P("M", "float", 4.0, "knot (mass) width, mm", min=0.5, max=40.0),
    P("phi0", "float", 35.0, "nib angle before any spin, degrees", min=-90.0, max=90.0),
    P("smooth", "float", 6.0, "σ of the regime along the line, mm", min=0.0, max=60.0),
], doc="ink accrue_walk's accumulated state: curl presses, knots are masses, the released spin turns the nib",
    reach=_reach)
def accrue_ink(ctx, marks, *, curl_on, curl_r, spin_floor, spin_full, W, M, phi0, smooth):
    out = []
    for m in marks:
        if "acc_curl" not in m.channels or len(m) < 2:
            out.append(m)
            continue
        out.append(m.evolve(channels=ink_channels(m, curl_on=curl_on, curl_r=curl_r, spin_floor=spin_floor,
                                                  spin_full=spin_full, W=W, M=M, phi0=phi0, smooth=smooth)))
    return out
