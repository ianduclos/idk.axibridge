import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import gesture_timing as gt  # noqa: E402
from gesture.core import Drawing, Stroke  # noqa: E402

BVH = """HIERARCHY
ROOT Hips
{
  OFFSET 0 0 0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT Neck
  {
    OFFSET 0 10 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT Head
    {
      OFFSET 0 5 0
      CHANNELS 3 Zrotation Xrotation Yrotation
      End Site
      {
        OFFSET 0 2 0
      }
    }
  }
}
MOTION
Frames: 3
Frame Time: 0.5
0 100 0 0 0 0 0 0 0 0 0 0
0 100 0 90 0 0 0 0 0 0 0 0
5 100 0 0 0 0 0 0 90 0 0 0
"""

ASF = """:version 1.10
:units
  mass 1.0
  length 0.45
  angle deg
:root
   order TX TY TZ RX RY RZ
   axis XYZ
   position 0 0 0
   orientation 0 0 0
:bonedata
  begin
     id 1
     name upper
     direction 0 1 0
     length 2
     axis 0 0 0 XYZ
    dof rx ry rz
  end
  begin
     id 2
     name head
     direction 0 1 0
     length 1
     axis 0 0 90 XYZ
    dof rx
  end
:hierarchy
  begin
    root upper
    upper head
  end
"""

AMC = """:FULLY-SPECIFIED
:DEGREES
1
root 0 0 0 0 0 0
upper 0 0 0
head 0
2
root 1 0 0 0 0 90
upper 0 0 0
head 30
"""


def test_bvh_fk(tmp_path):
    p = tmp_path / "t.bvh"
    p.write_text(BVH)
    m = gt.parse_bvh(p)
    assert m.names == ["Hips", "Neck", "Head", "Head_end"]
    assert m.fps == pytest.approx(2.0)
    np.testing.assert_allclose(m.joint("Head_end")[0], [0, 117, 0], atol=1e-9)
    # root Z-rotation 90° swings the +y chain onto −x
    np.testing.assert_allclose(m.joint("Head_end")[1], [-17, 100, 0], atol=1e-9)
    # Neck Y-rotation leaves a +y chain alone; root translation moves it
    np.testing.assert_allclose(m.joint("Head_end")[2], [5, 117, 0], atol=1e-9)
    assert m.up == 1


def test_asf_amc_fk(tmp_path):
    (tmp_path / "s.asf").write_text(ASF)
    (tmp_path / "s_01.amc").write_text(AMC)
    m = gt.load_motion(tmp_path / "s_01.amc")
    k = 2.54 / 0.45
    assert m.T == 2 and m.names == ["root", "upper", "head"]
    np.testing.assert_allclose(m.joint("head")[0], [0, 3 * k, 0], atol=1e-9)
    # bone lengths are preserved under any rotation
    for t in range(2):
        assert np.linalg.norm(m.joint("head")[t] - m.joint("upper")[t]) == pytest.approx(1 * k)
        assert np.linalg.norm(m.joint("upper")[t] - m.joint("root")[t]) == pytest.approx(2 * k)
    # frame 2: root at x = 1 unit, rotated 90° about z → chain points along −x
    np.testing.assert_allclose(m.joint("upper")[1], [k - 2 * k, 0, 0], atol=1e-9)


def test_kinematics_circle():
    fps, R, w = 100.0, 20.0, 2.0
    t = np.arange(0, 6, 1 / fps)
    x = np.column_stack([R * np.cos(w * t), R * np.sin(w * t), np.zeros_like(t)])
    k = gt.kinematics(x, fps, sigma_s=0.0)
    mid = slice(10, -10)
    np.testing.assert_allclose(k["speed"][mid], R * w, rtol=1e-3)
    np.testing.assert_allclose(k["kappa"][mid], 1 / R, rtol=1e-3)


def test_power_law_recovers_one_third():
    # ellipse traced under the 2/3 law: v = K κ^(-1/3)
    a, b = 30.0, 10.0
    th = np.linspace(0, 6 * np.pi, 20000)
    xy = np.column_stack([a * np.cos(th), b * np.sin(th)])
    ds = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    kap = a * b / (a * a * np.sin(th) ** 2 + b * b * np.cos(th) ** 2) ** 1.5
    v = 50.0 * kap ** (-1 / 3)
    tt = np.concatenate([[0], np.cumsum(ds / (0.5 * (v[1:] + v[:-1])))])
    fps = 200.0
    tg = np.arange(0, tt[-1], 1 / fps)
    tr = np.column_stack([np.interp(tg, tt, xy[:, 0]), np.interp(tg, tt, xy[:, 1])])
    k = gt.kinematics(tr, fps, sigma_s=0.0)
    r = gt.power_law(k["speed"][5:-5], k["kappa"][5:-5])
    assert r["slope"] == pytest.approx(-1 / 3, abs=0.02)
    assert r["r2"] > 0.98


def test_pauses():
    fps = 50.0
    sp = np.full(500, 40.0)
    sp[100:130] = 0.5            # 0.6 s still
    sp[300:303] = 0.5            # 0.06 s dip: too short
    mask, runs, thr = gt.pauses(sp, fps)
    assert runs == [(100, 130)]
    assert mask.sum() == 30


def _timing(speed, fps=50.0):
    n = len(speed)
    t = np.arange(n) / fps
    return gt.Timing(t, np.asarray(speed, float), np.full(n, 0.5), np.zeros(n), np.zeros(n),
                     np.asarray(speed) < 1.0, label="synthetic")


def test_ink_profile_still_becomes_mass():
    sp = np.full(1000, 30.0)
    sp[400:500] = 0.0                                 # 2 s of stillness at 40 % of the time
    tm = _timing(sp)
    s = np.linspace(0, 500, 2001)
    pr = gt.line_profiles(tm, s, W=6.0, shape_w=15.0, pen=1.0)
    # the pen has covered (400 frames of motion) / (900 frames) of the line when it stops
    s_still = 500 * 400 / 900
    i = int(np.argmax(pr["q"]))
    assert abs(s[i] - s_still) < 5.0
    assert pr["r"][i] == pytest.approx(2.0)
    assert np.median(pr["r"]) < 0.3                  # steady motion stays a line
    uni = gt.line_profiles(_timing(np.full(1000, 30.0)), s, W=6.0, shape_w=15.0, pen=1.0)
    assert np.max(uni["r"][50:-50]) < 0.2


def test_danced_strokes_pure_and_deterministic():
    rng = np.random.default_rng(0)
    sp = np.abs(rng.normal(30, 15, 1500))
    sp[600:700] = 0.0
    tm = _timing(sp)
    tm.jerk[:] = gt.gaussian_filter1d(rng.normal(0, 1, 1500), 3) ** 2
    lines = [np.column_stack([np.linspace(0, 300, 200), 50 + 10 * np.sin(np.linspace(0, 6, 200))]),
             np.column_stack([np.linspace(0, 200, 100), np.full(100, 120.0)])]
    keep = [q.copy() for q in lines]
    a, ia = gt.danced_strokes(lines, tm, W=6.0, shape_w=15.0, pen=1.0, rng=np.random.default_rng(1))
    b, ib = gt.danced_strokes(lines, tm, W=6.0, shape_w=15.0, pen=1.0, rng=np.random.default_rng(1))
    for q, k in zip(lines, keep):
        np.testing.assert_array_equal(q, k)
    assert len(a) == len(b) >= 2
    for x, y in zip(a, b):
        np.testing.assert_array_equal(x.points, y.points)
        np.testing.assert_array_equal(x.r, y.r)
        assert x.r.min() >= 0 and x.r.max() <= 2
    assert max(float(s.r.max()) for s in a) >= 1.9      # the stillness pooled somewhere


def test_width_curvature_detects_dwell_signal():
    rng = np.random.default_rng(2)

    def stroke(dwell):
        s = np.linspace(0, 40 * np.pi, 3000)
        th = 0.8 * np.sin(s / 15)                     # alternating bends
        p = np.cumsum(np.column_stack([np.cos(th), np.sin(th)]) * (s[1] - s[0]), axis=0) * 10
        k = np.abs(np.gradient(th, s[1] - s[0])) / 10
        w = 4.0 * (1 + 60.0 * k) if dwell else 4.0 + rng.normal(0, 0.05, len(s))
        return Stroke(p, width=w)
    flat = gt.width_curvature([Drawing([stroke(False) for _ in range(3)], size=(2000, 2000))])
    dw = gt.width_curvature([Drawing([stroke(True) for _ in range(3)], size=(2000, 2000))])
    assert abs(flat["rho_coarse"]) < 0.1
    assert dw["rho_coarse"] > 0.5 and dw["w_ratio_bend_vs_straight"] > 1.05
