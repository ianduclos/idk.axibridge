"""Round 12, thread `drive`: sources as drivers (modulators_drive, renderers_drive, arrangers_drive)."""
from __future__ import annotations

import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit import modulators_drive as MD  # noqa: E402
from gesture.kit import renderers_drive as RD  # noqa: E402

DRIVERS = ("drive_mosquito", "drive_stork", "drive_tropicbird", "drive_mosca", "drive_surrogate_mosquito")


def _rec(mods, *, show="hidden", ink=None, length=1.2, seed=4711, hand="river_meander"):
    return {"seed": seed, "frame": [160, 120], "margin": 5.0,
            "arranger": {"id": "drive_beside", "show": show, "layout": "right", "share": 0.4},
            "parts": [{"voice": {"id": "hand", "hand": hand, "length": length}, "modulators": mods,
                       "renderer": ink or {"id": "drive_ink", "pen": 0.4}}]}


STORK = {"id": "drive_regime", "driver": "drive_stork", "channel": "speed", "start": 0.37, "span": 0.05,
         "invert": True, "smooth": 0.5, "nib_at": 0.88, "mass_at": 1.01, "min_run": 3.0, "ramp": 2.0}
PHI = {"id": "drive_phi", "driver": "drive_mosquito", "channel": "heading", "start": 0.56, "span": 0.133,
       "gain": 0.5, "max_rate": 12.0}
PEN = {"id": "drive_pen", "driver": "drive_mosquito", "channel": "steer", "transform": "highpass", "tau": 3.0,
       "start": 0.5, "span": 0.27, "norm": "signed", "smooth": 6.0, "stretch": True, "thr": 0.3, "min_run": 20.0}
NIB = {"id": "drive_ink", "pen": 0.4, "body": "nib_e"}


def test_modules_registered_and_no_discovery_errors():
    kit.core.discover()
    assert not kit.DISCOVERY_ERRORS
    reg = kit.core.registry()
    for mid in ("drive_width", "drive_regime", "drive_pen", "drive_knots", "drive_tremor", "drive_phi"):
        assert mid in reg["modulator"]
    assert "drive_ink" in reg["renderer"] and "drive_beside" in reg["arranger"]


@pytest.mark.parametrize("did", DRIVERS)
def test_driver_entries_load(did):
    e = L.entry("drive_signal", did)
    assert e["policy"] == "generative" and e["channels"]
    d = L.load("drive_signal", did)
    assert np.all(np.diff(d["t"]) > 0)
    for ch in e["channels"]:
        assert d["series"][ch].shape == d["t"].shape and np.all(np.isfinite(d["series"][ch]))


def test_driver_never_stores_a_shape():
    """Drivers are time series only: no positions (lon/lat/x/y) are frozen."""
    for did in DRIVERS:
        names = set(L.load("drive_signal", did)["series"])
        assert not names & {"x", "y", "lon", "lat", "path"}


def test_hysteresis_and_min_runs():
    v = np.r_[np.zeros(10), np.full(3, 0.6), np.zeros(10), np.full(20, 0.9)]
    lev = MD.hysteresis_levels(v, [0.5], 0.05)
    assert lev.tolist() == [0] * 10 + [1] * 3 + [0] * 10 + [1] * 20
    lev2 = MD.min_runs(lev, 5)
    assert lev2[10:13].tolist() == [0, 0, 0]                     # the 3-sample run is absorbed
    noisy = 0.5 + 0.03 * np.sin(np.arange(200))
    assert len(set(MD.hysteresis_levels(noisy, [0.5], 0.05).tolist())) == 1


def test_piece_runs_deterministic_and_carries_channels():
    rec = _rec([STORK, PHI, PEN], ink=NIB)
    a, b = kit.run(rec), kit.run(rec)
    assert len(a.inks) == len(b.inks) > 0
    for x, y in zip(a.inks, b.inks):
        assert np.array_equal(x.points, y.points) and x.meta.get("colour") == y.meta.get("colour")
    m = a.marks[0]
    for ch in ("r", "phi", "pen_i", "drv_regime", "drv_phi", "drv_pen"):
        assert ch in m.channels
    assert [r["target"] for r in m.meta["drive"]] == ["regime", "phi", "pen"]
    assert {i.meta["colour"] for i in a.inks} <= {"black", "red", "blue"}


def test_regime_follows_the_stork():
    sh = kit.run(_rec([STORK], ink=NIB, length=4.0))
    m = sh.marks[0]
    r, u = np.asarray(m["r"]), np.asarray(m["drv_regime"])
    assert r.min() < 0.1 and r.max() > 0.9                      # both a hairline and a ribbon
    assert r[u > 0.6].mean() < r[u < 0.05].mean()               # flying → thinner


def test_phi_rate_is_capped():
    sh = kit.run(_rec([PHI], ink=NIB, length=3.0))
    m = sh.marks[0]
    phi = np.unwrap(2 * np.asarray(m["phi"])) / 2
    rate = np.degrees(np.abs(np.diff(phi))) / np.diff(m.arclength())
    assert rate.max() <= 12.0 + 1e-6


def test_pen_runs_respect_min_run():
    sh = kit.run(_rec([PEN], length=4.0))
    m = sh.marks[0]
    lev = np.asarray(m["pen_i"]).round().astype(int)
    s = m.arclength()
    cuts = np.nonzero(np.diff(lev))[0] + 1
    bounds = np.r_[0, cuts, len(lev) - 1]
    inner = [s[b] - s[a] for a, b in zip(bounds[1:-2], bounds[2:-1])]
    assert all(L_ >= 20.0 - 1.0 for L_ in inner)


def test_knots_on_tropicbird_pauses():
    k = {"id": "drive_knots", "driver": "drive_tropicbird", "channel": "speed", "norm": "record", "start": 0.0,
         "span": 1.0, "thr": 0.1, "min_s": 480.0, "merge_s": 180.0, "full_s": 2400.0, "smooth": 0.5}
    sh = kit.run(_rec([k], length=3.0, ink={"id": "drive_ink", "knots": "bead"}))
    rec = sh.marks[0].meta["drive"][0]
    assert rec["n_knots"] >= 3
    assert any(i.meta.get("role") == "knot" for i in sh.inks)


def test_width_sweeps_and_tremor_displaces():
    w = {"id": "drive_width", "driver": "drive_stork", "channel": "alt", "transform": "rate", "tau": 600.0,
         "norm": "signed", "side": "pos", "start": 0.37, "span": 0.09, "lo": 0.4, "hi": 5.0, "floor": 0.1}
    t = {"id": "drive_tremor", "driver": "drive_mosquito", "channel": "steer", "start": 0.1, "span": 0.1,
         "amount": 0.4, "band": 2.0, "gate": 2.0, "smooth": 0.0}
    sh = kit.run(_rec([w, t], length=3.0))
    m = sh.marks[0]
    assert np.asarray(m["dw"]).max() > 2.0 and np.asarray(m["dw"]).min() == pytest.approx(0.4)
    assert np.percentile(np.abs(m["tremor"]), 95) > 0.1
    assert any(i.meta.get("role") == "swell" and i.filled for i in sh.inks)


def test_beside_adds_measurement_keeps_drawing_whole():
    hidden = kit.run(_rec([STORK, PHI, PEN], ink=NIB, show="hidden"))
    beside = kit.run(_rec([STORK, PHI, PEN], ink=NIB, show="beside"))
    roles = [m.meta.get("drive_role") for m in beside.marks]
    assert "unrolled" in roles and roles.count("trace") >= 3
    drawing = [m for m in beside.marks if not m.meta.get("drive_role")]
    assert len(drawing) == len(hidden.marks)
    # the measurement sits right of the drawing, inside the frame
    xs_d = np.concatenate([m.points[:, 0] for m in drawing])
    xs_m = np.concatenate([m.points[:, 0] for m in beside.marks if m.meta.get("drive_role")])
    assert xs_m.min() > xs_d.max() - 1e-6 and xs_m.max() <= 160.0
    img = RD.render_colour(beside, px_per_mm=2.0)
    assert img.size == (320, 240)


def test_surrogate_differs_but_keeps_scale():
    a = L.load("drive_signal", "drive_mosquito")["series"]["steer"]
    b = L.load("drive_signal", "drive_surrogate_mosquito")["series"]["steer"]
    assert not np.allclose(a, b)
    assert math.isclose(float(np.std(a)), float(np.std(b)), rel_tol=0.02)
