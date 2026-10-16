"""gesture/dance.py: mocap parsers, FK, structures, body regimes (synthetic data only)."""
import math

import numpy as np

from gesture import dance as D
from gesture.core import Drawing, Stroke

BVH = """HIERARCHY
ROOT Hips
{
  OFFSET 0 0 0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT Spine
  {
    OFFSET 0 10 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT Head
    {
      OFFSET 0 10 0
      CHANNELS 3 Zrotation Xrotation Yrotation
      End Site
      {
        OFFSET 0 5 0
      }
    }
  }
}
MOTION
Frames: 3
Frame Time: 0.01
0 90 0 0 0 0 0 0 0 0 0 0
1 90 0 0 0 0 90 0 0 0 0 0
2 90 0 0 0 0 90 0 0 -90 0 0
"""


def test_bvh_fk():
    m = D.parse_bvh(BVH)
    assert m.names == ["Hips", "Spine", "Head", "Head_end"]
    assert m.fps == 100.0 and m.T == 3
    np.testing.assert_allclose(m.pos[0, 2], [0, 110, 0], atol=1e-9)
    # frame 1: spine rotated +90° about z → the chain above it points along −x
    np.testing.assert_allclose(m.pos[1, 2], [1 - 10, 100, 0], atol=1e-9)
    # frame 2: head rotated back −90° → end site points up again
    np.testing.assert_allclose(m.pos[2, 3], [2 - 10, 100, 0] + np.array([0, 5, 0]), atol=1e-9)
    assert m.up_axis() == 1


ASF = """:version 1.10
:units
  length 1
  angle deg
:root
   order TX TY TZ RX RY RZ
   axis XYZ
   position 0 0 0
   orientation 0 0 0
:bonedata
  begin
     id 1
     name lowerback
     direction 0 1 0
     length 2
     axis 0 0 0  XYZ
    dof rx ry rz
  end
  begin
     id 2
     name head
     direction 0 1 0
     length 1
     axis 0 0 0  XYZ
    dof rz
  end
:hierarchy
  begin
    root lowerback
    lowerback head
  end
"""
AMC = """:FULLY-SPECIFIED
:DEGREES
1
root 0 0 0 0 0 0
lowerback 0 0 0
head 0
2
root 5 0 0 0 0 0
lowerback 0 0 90
head 0
"""


def test_asf_amc_fk():
    asf = D.parse_asf(ASF)
    m = D.parse_amc(AMC, asf)
    assert m.names == ["root", "lowerback", "head"]
    np.testing.assert_allclose(m.pos[0, 2], [0, 3, 0], atol=1e-9)
    # lowerback rz 90°: (0,1,0) → (−1,0,0), head inherits
    np.testing.assert_allclose(m.pos[1, 1], [5 - 2, 0, 0], atol=1e-9)
    np.testing.assert_allclose(m.pos[1, 2], [5 - 3, 0, 0], atol=1e-9)


def _toy_motion(T=600, fps=60.0, seed=0):
    """A stick body: root walks with pauses, arms swing, head bobs (y up)."""
    rng = np.random.default_rng(seed)
    t = np.arange(T) / fps
    env = (np.sin(2 * np.pi * t / 4.0) > -0.3).astype(float)       # pauses
    env = np.convolve(env, np.ones(15) / 15, mode="same")
    names = ["root", "thorax", "upperneck", "head", "lclavicle", "lhumerus", "lradius", "lfingers",
             "rclavicle", "rhumerus", "rradius", "rfingers", "lhipjoint", "lfemur", "ltibia", "ltoes",
             "rhipjoint", "rfemur", "rtibia", "rtoes"]
    par = [-1, 0, 1, 2, 1, 4, 5, 6, 1, 8, 9, 10, 0, 12, 13, 14, 0, 16, 17, 18]
    off = {"thorax": (0, 4, 0), "upperneck": (0, 1.5, 0), "head": (0, 1.5, 0), "lclavicle": (1.5, 0, 0),
           "lhumerus": (0, -3, 0), "lradius": (0, -3, 0), "lfingers": (0, -1, 0), "rclavicle": (-1.5, 0, 0),
           "rhumerus": (0, -3, 0), "rradius": (0, -3, 0), "rfingers": (0, -1, 0), "lhipjoint": (1, 0, 0),
           "lfemur": (0, -4, 0), "ltibia": (0, -4, 0), "ltoes": (0, 0, 1), "rhipjoint": (-1, 0, 0),
           "rfemur": (0, -4, 0), "rtibia": (0, -4, 0), "rtoes": (0, 0, 1)}
    pos = np.zeros((T, len(names), 3))
    pos[:, 0] = np.column_stack([np.cumsum(env) / fps, 9 + 0.2 * np.sin(5 * t), np.zeros(T)])
    ph = rng.uniform(0, 2 * np.pi, len(names))
    for j, n in enumerate(names[1:], start=1):
        o = np.array(off[n], float)
        wob = 0.8 * env * np.sin(3 * t + ph[j])
        pos[:, j] = pos[:, par[j]] + o + np.column_stack([wob, 0.3 * wob, 0.5 * wob * np.cos(t)])
    return D.Motion(names, np.array(par), pos, fps, "toy")


def test_views_and_trails():
    m = _toy_motion()
    B = D.view_basis(m, "front")
    assert B.shape == (3, 2) and B[1, 1] == -1.0         # page y points down
    d = D.trails(m, size=(400, 600))
    assert len(d.strokes) >= 5
    allp = np.vstack([s.points for s in d.strokes])
    assert allp.min() >= 0 and allp[:, 0].max() <= 400 and allp[:, 1].max() <= 600
    s = d.strokes[0]
    assert len(s.meta["speed"]) == len(s) and len(s.meta["acc"]) == len(s)
    cuts = D.phrase_cuts(m)
    assert len(cuts) >= 1 and np.all(np.diff(cuts) >= int(1.2 * m.fps))


def test_strobe_relative_graft():
    m = _toy_motion()
    st = D.strobe(m, n=5, size=(400, 400))
    assert len(st.strokes) == 5 * len(D.CHAINS)
    assert len(D.relative(m, (("lhand", "rfoot"),)).strokes) >= 1
    g = D.graft(m, _toy_motion(seed=3))
    assert len(g.strokes) >= 4


def test_chimera_contiguous_and_deterministic():
    m = _toy_motion()
    pcs = D.pieces_at_minima(D.trails(m, cut="none"), min_frac=0.01)
    assert len(pcs) >= 4
    a = D.chimera(pcs, np.random.default_rng(5), n_lines=2, per_line=5)
    b = D.chimera(pcs, np.random.default_rng(5), n_lines=2, per_line=5)
    assert len(a.strokes) == 2
    for sa, sb in zip(a.strokes, b.strokes):
        np.testing.assert_allclose(sa.points, sb.points)
        step = np.linalg.norm(np.diff(sa.points, axis=0), axis=1)
        assert step.max() < 0.1 * a.ref_length()            # one contiguous line, no jumps
        assert len(sa.meta["speed"]) == len(sa)


def test_impossible_tree():
    m = _toy_motion()
    d = D.impossible_tree(m, depth=3, branching=2, cut="none", min_len=0.0)
    assert len(d.strokes) == 8                                # 2^3 tip trails
    d2 = D.impossible_tree(m, depth=3, branching=2, cut="none", strobe_n=2, n_tips=3)
    bones = [s for s in d2.strokes if s.meta.get("joint") == "bone"]
    assert len(bones) == 2 * (2 + 4 + 8)


def test_kinematic_regimes():
    r = D.kinematic_r([0.0, 0.5, 1.0, 2.0], [0.0, 1.0, 0.0, 0.0], v_ref=1.0, a_ref=1.0)
    assert r[0] == 2.0                    # still → mass
    assert 0.5 < r[1] <= 1.0              # accelerating, not fast → nib
    assert r[3] == 0.0                    # fast → wire
    m = _toy_motion()
    d = D.trails(m, size=(400, 600))
    before = [s.points.copy() for s in d.strokes]
    f = D.kinematic_field(d)
    vals = f(np.random.default_rng(0).uniform(0, 1, (200, 2)))
    assert vals.min() >= 0 and vals.max() <= 2
    on = f.at_px(np.vstack([s.points for s in d.strokes]), d.size)
    assert on.max() > 1.5                 # the pauses make masses somewhere
    for s, p in zip(d.strokes, before):   # purity
        np.testing.assert_array_equal(s.points, p)


def test_find_aliases():
    m = _toy_motion()
    assert m.names[m.find("lhand")] == "lfingers"
    assert m.names[m.find("rfoot")] == "rtoes"
    assert math.isclose(m.window(1.0, 2.0).T, 60)
