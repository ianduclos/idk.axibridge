"""Physical calibration routines (each done once against the real machine).

**Holder offset calibration** — the V-cradle holder self-centres every barrel
on the vee's bisector, so a pen's nib offset is a single fixed direction in
carriage space scaled by barrel diameter. The wizard:

1. plot a registration mark with pen 1 (calipered diameter d₁);
2. swap to pen 2 (diameter d₂), plot the same mark;
3. caliper the on-paper displacement (Δx, Δy) of mark 2 relative to mark 1,
   in machine axes (x along the machine's long edge, y toward the user —
   same frame as the canvas);
4. ``vector = (Δx, Δy) / (d₂ − d₁)`` — one measurement captures both the
   bisector direction and the magnitude per mm of diameter.

Compensation then translates each pass by ``−vector × barrel_diameter``. The
constant part of the seating offset (same for every pen) cancels — only the
diameter-proportional term misregisters passes, and that's what this removes.
A zero vector disables compensation (deliberate, for when raw seating
misregistration is wanted as an artifact).

**Pen height testing** is interactive (live param changes + pen/stroke
actuation through the existing backend ops); only the test-stroke geometry is
built here.
"""

from __future__ import annotations

import math

from .model import Layer, Path, PathDocument
from .stores import HolderCalibration


def registration_mark(cx: float = 40.0, cy: float = 40.0) -> PathDocument:
    """A small crosshair + circle, plotted at a fixed bed position so two
    pens' marks can be compared with calipers."""
    arm = 6.0
    r = 3.0
    circle = [
        (cx + r * math.cos(t * math.pi / 18), cy + r * math.sin(t * math.pi / 18))
        for t in range(37)
    ]
    paths = [
        Path(points=[(cx - arm, cy), (cx + arm, cy)]),
        Path(points=[(cx, cy - arm), (cx, cy + arm)]),
        Path(points=circle),
    ]
    return PathDocument(
        layers=[Layer(id=1, name="registration mark", color="#26241f", paths=paths)],
        width=300, height=218, source="holder calibration mark",
    )


def test_stroke(x: float = 20.0, y: float = 20.0, length: float = 20.0) -> PathDocument:
    """A short line for verifying pen contact and line quality at the current
    heights."""
    return PathDocument(
        layers=[Layer(id=1, name="test stroke", color="#26241f",
                      paths=[Path(points=[(x, y), (x + length, y)])])],
        width=300, height=218, source="pen height test stroke",
    )


def compute_holder_vector(
    diameter_1: float, diameter_2: float, dx_mm: float, dy_mm: float
) -> HolderCalibration:
    """``(Δx, Δy) / (d₂ − d₁)`` with sanity checks."""
    dd = diameter_2 - diameter_1
    if abs(dd) < 0.5:
        raise ValueError(
            "pen diameters are too close to calibrate from "
            f"(Δd = {dd:.2f} mm); use two pens at least 0.5 mm apart"
        )
    return HolderCalibration(dx_per_mm=dx_mm / dd, dy_per_mm=dy_mm / dd)
