"""Thread 3 of round 12 (`stain`): mass from real stains."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import kit  # noqa: E402
from gesture.kit import renderers_stain as S  # noqa: E402
from gesture.kit.renderers_stain_particle import stain_particle  # noqa: E402

DANCE = {"id": "dance", "trail": "levitation", "effectors": "hands", "cut": "none", "seconds": 8, "t0": 15}


class _Ctx:
    def __init__(self, seed=1):
        self.seed = self.sheet_seed = seed

    def use(self, kind, id, purpose="generate"):
        return kit.library.load(kind, id, purpose)

    def rng(self, *tags):
        return np.random.default_rng([self.seed, *[kit.core.tag(t) for t in tags]])


def _slowing(L=60.0, slow=True):
    s = np.linspace(0, L, 600)
    pts = np.column_stack([5 + s, 20 + 3 * np.sin(s / 9)])
    v = 1 - (0.97 * np.exp(-((s - 0.5 * L) / 3) ** 2) if slow else np.zeros_like(s))
    t = np.r_[0, np.cumsum(np.diff(s) / (0.5 * (v[1:] + v[:-1])))]
    return kit.Mark(pts, {"dance_t": t})


def test_registered_and_imports():
    kit.discover()
    assert not kit.DISCOVERY_ERRORS
    assert "stain" in kit.core.registry("renderer")
    assert "stain_particle" in kit.core.registry("renderer")


def test_library_digest():
    d = kit.library.load("stain", "stain_fabric")["entry"]["digest"]
    assert d["n_stains"] > 500
    assert len(d["profile_mesa"]) == len(d["s_bins"]) == len(d["profile_rim"])
    assert 0 < d["rim_share"] < 0.5
    assert d["rough_q"][1] < d["rough_q"][2] < d["rough_q"][3]


def test_deterministic_and_one_line_per_mark():
    r = {"seed": 6620, "frame": [120, 120], "voice": DANCE, "renderer": {"id": "stain", "R": 8}}
    a, b = kit.run(r), kit.run(r)
    assert len(a.inks) == len(b.inks) == len(a.marks)
    for x, y in zip(a.inks, b.inks):
        assert np.array_equal(x.points, y.points)
        assert np.all(np.isfinite(x.points))


def test_medium_front_roughness_matches_corpus():
    rough = []
    for seed in range(4):
        rng = np.random.default_rng(seed)
        U, x0, y0 = S.arrival(np.zeros((1, 2)), np.array([6.0]), h=0.15, pad=2.2, period=0.9, weave=0.15,
                              fiber=0.45, elong=1.0, sheet_seed=seed, rng=rng)
        F = S._front(U, (x0, y0), 0.15, 0.0, np.zeros(2))
        assert F is not None
        rough.append(S.front_roughness(F)[0])
    d = kit.library.load("stain", "stain_fabric")["entry"]["digest"]
    assert d["rough_q"][1] <= float(np.median(rough)) <= d["rough_q"][3]


def test_pass_levels_final_front_first():
    rng = np.random.default_rng(0)
    d = kit.library.load("stain", "stain_fabric")["entry"]["digest"]
    for tide in ("rim", "mesa"):
        lv = S.pass_levels(tide, d["profile_rim" if tide == "rim" else "profile_mesa"], d["s_bins"], n=7,
                           pile=0.15, rng=rng)
        assert lv[0] == 1.0 and len(lv) == 8
        assert all(0.0 < v <= 1.0 for v in lv)


def test_walk_open_returns_to_entry():
    th = np.linspace(0, 2 * np.pi, 120, endpoint=False)
    passes = [np.column_stack([r * np.cos(th), r * np.sin(th)]) for r in (5.0, 4.8, 4.6, 4.7)]
    p_in = np.array([5.0, 0.0])
    path = S.walk_open(passes, p_in, 120, 0.4)
    assert np.allclose(path[0], p_in) and np.allclose(path[-1], p_in)
    # contiguous: no step longer than the gap between passes plus a sample spacing
    assert np.hypot(*np.diff(path, axis=0).T).max() < 0.6


def test_no_slowing_no_stain():
    """Only dwell IN EXCESS of the line's own pace wets the cloth."""
    mod = kit.core.get("renderer", "stain")
    prm = {k: v for k, v in mod.validate({}).items() if k != "id"}
    inks = S.stain(_Ctx(), [_slowing(slow=False)], **prm)
    assert len(inks) == 1
    L = inks[0].points
    assert len(L) <= 310            # the 0.2 mm resampled line, nothing added


def test_slowing_makes_a_stain_and_the_line_goes_on():
    mod = kit.core.get("renderer", "stain")
    prm = {k: v for k, v in mod.validate({"R": 6}).items() if k != "id"}
    line = _slowing()
    inks = S.stain(_Ctx(), [line], **prm)
    P = inks[0].points
    assert len(P) > 600
    assert np.allclose(P[0], line.points[0], atol=0.3) and np.allclose(P[-1], line.points[-1], atol=0.3)
    c = line.points[300]
    assert np.hypot(*(P - c).T).max() < 60             # stays near the line
    assert (np.hypot(*(P - c).T) > 4).sum() > 100       # and has a stain of some size round the pause


@pytest.mark.parametrize("tide", ["mesa", "rim"])
def test_particle_runs(tide):
    mod = kit.core.get("renderer", "stain_particle")
    prm = {k: v for k, v in mod.validate({"R": 5, "tide": tide, "slack": 2.0}).items() if k != "id"}
    inks = stain_particle(_Ctx(3), [_slowing()], **prm)
    assert len(inks) == 1 and np.all(np.isfinite(inks[0].points))
