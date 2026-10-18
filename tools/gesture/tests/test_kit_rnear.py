"""river_approach (round 14, thread c2 `rnear`): the far Amazon stem, approached and left."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gesture import kit  # noqa: E402
from gesture.kit import library as L  # noqa: E402
from gesture.kit import voices_rnear as vr  # noqa: E402

FRAME = [300, 160]
PIECE = {"approaches": 4, "peak": 40.0, "vary": 0.7, "share": 0.5}


@pytest.fixture(scope="module")
def geom():
    _, wm, q = L.load("river_stems", "grwl_far_sb19")["stems"][("SB19", 0)]
    return vr.stem_geom(q, wm)


@pytest.fixture(scope="module")
def chains(geom):
    return [vr.HandChain(L.load("hand", h), np.random.default_rng([11, i]), z, geom.diag_w(z))
            for i, (h, z) in enumerate(vr.HAND_ZOOM.items())]


def _approaches(seed=3, n=3, peak=30.0):
    return vr.make_approaches(np.random.default_rng(seed), n=n, peak=peak, width=0.8, skew=0.5, vary=0.6)


def _headings(P_):
    d = np.diff(P_, axis=0)
    d = d[np.linalg.norm(d, axis=1) > 1e-9]
    return np.unwrap(np.arctan2(d[:, 1], d[:, 0]))


def test_registered_and_validates():
    assert not kit.DISCOVERY_ERRORS
    from gesture.kit.core import registry
    assert "river_approach" in registry()["voice"]
    rec = kit.validate({"seed": 1, "voice": {"id": "river_approach"}})
    v = rec["parts"][0]["voice"]
    assert v["stems"] == "grwl_far_sb19" and v["handover"] == "ladder" and v["event"] == "neck"


def test_schedule_starts_and_ends_far_and_reaches_peak():
    ap = _approaches()
    t = np.linspace(0, 1, 4001)
    k = vr.zoom_at(t, ap)
    assert k[0] == pytest.approx(1.0, abs=1e-6) and k[-1] == pytest.approx(1.0, abs=1e-6)
    assert k.max() == pytest.approx(max(a["peak"] for a in ap), rel=1e-3)
    assert k.min() >= 1.0 - 1e-9
    for a in ap:                                    # asymmetric: rise and fall differ
        assert 0.0 < a["c"] - a["rise"] and a["c"] + a["fall"] < 1.0


def test_carrier_is_the_stem_magnified(geom):
    """With no handover and no event the paper heading IS the stem heading:
    total turning equals the stem's between the stretch ends, and the line
    has no heading jump anywhere (one contiguous line)."""
    P_, ch, info = vr.approach_line(geom, start=0.0, length_w=7000, approaches=_approaches(), hands=[],
                                    handover="none", share=0.0, loops=None, event="none", events=0,
                                    rng=np.random.default_rng(0), h=0.1)
    U0, U1 = info["U"]
    th = _headings(P_)
    stem_turn = float(geom.theta(U1) - geom.theta(U0))
    assert th[-1] - th[0] == pytest.approx(stem_turn, abs=math.radians(3))
    assert np.abs(np.diff(th)).max() < math.radians(8)
    assert (ch["src"] == 0).all()
    assert ch["zoom"].max() > 20 and ch["zoom"][0] == pytest.approx(1.0, abs=0.05)


def test_handover_whole_bends_continuous_and_handed(geom, chains):
    P_, ch, info = vr.approach_line(geom, start=0.0, length_w=7000, approaches=_approaches(5), hands=chains,
                                    handover="ladder", share=0.95, loops=None, event="none", events=0,
                                    rng=np.random.default_rng(1), h=0.1)
    assert info["handed"], "the ladder should hand some bends over at share 0.95"
    th = _headings(P_)
    assert np.abs(np.diff(th)).max() < math.radians(20)          # heading continuous at every joint
    B = [(max(a, info["U"][0]), min(b, info["U"][1])) for a, b in geom.bends
         if b > info["U"][0] and a < info["U"][1]]
    B = [(a, b) for a, b in B if b - a > 1e-6]
    for d in info["handed"]:
        a, b = B[d["bend"]]
        stem_sign = np.sign(geom.net(a, b)) or 1.0
        c = chains[d["hand"]]
        s0, n = d["window"]
        first = c.sgn[s0] * (-1.0 if d["mirror"] else 1.0)
        assert first == stem_sign                                 # bend handedness inherited at the joint


def test_window_never_crosses_itself(chains):
    from shapely.geometry import LineString
    c = chains[0]
    c.ptr = 0
    for k in range(20):
        got = c.take(1.0 if k % 2 else -1.0, 1.2, 0.15, R=100.0, step=0.5)
        assert got is not None
        assert LineString(got[0]).is_simple


def test_neck_event_only_at_nearest_approach(geom, chains):
    loops = L.load("river_loops", "river_cutoffs")
    ap = _approaches(7)
    P_, ch, info = vr.approach_line(geom, start=0.0, length_w=7000, approaches=ap, hands=chains,
                                    handover="none", share=0.0, loops=loops, event="neck", events=2,
                                    rng=np.random.default_rng(2), h=0.1)
    assert 1 <= len(info["events"]) <= 2
    deepest = max(a["peak"] for a in ap)
    for e in info["events"]:
        assert e["kind"] == "neck" and e["zoom"] >= deepest ** 0.5


def test_voice_in_frame_deterministic_contiguous():
    rec = {"seed": 6204, "frame": FRAME, "margin": 10.0, "voice": {"id": "river_approach", **PIECE, "plan": 3}}
    a, b = kit.run(rec), kit.run(rec)
    assert len(a.marks) == 1
    m = a.marks[0]
    assert np.array_equal(m.points, b.marks[0].points)
    x0, y0 = 10.0 - 1e-6, 10.0 - 1e-6
    assert m.points[:, 0].min() >= x0 and m.points[:, 1].min() >= y0
    assert m.points[:, 0].max() <= FRAME[0] - 10 + 1e-6 and m.points[:, 1].max() <= FRAME[1] - 10 + 1e-6
    seg = np.linalg.norm(np.diff(m.points, axis=0), axis=1)
    assert seg.max() < 1.0                                       # one line, no jumps
    for c in ("zoom", "src", "stem_u", "voice", "r", "phi", "W", "M"):
        assert c in m.channels
    assert m.meta["voices"][0].startswith("grwl:SB19")


def test_window_points_end_where_end_heading_says(chains):
    """A window joins segments from different strokes; integrated token by
    token its last tangent is end_heading's, so the stem resumes without a
    cusp (grammar.tokens_to_points carries curvature across tokens and made
    a 178° cusp here before the fix)."""
    from gesture import grammar as gm
    c = chains[1]
    for a in range(0, 60, 3):
        toks = c.tokens(a, 3, 1.0)
        p, h_end = vr.integrate_tokens(toks, 500.0, heading=0.3, step=0.1)
        d = p[-1] - p[-2]
        err = (math.atan2(d[1], d[0]) - gm.end_heading(toks, 0.3) + math.pi) % (2 * math.pi) - math.pi
        assert abs(err) < math.radians(2)
        assert h_end == pytest.approx(gm.end_heading(toks, 0.3))


def test_no_seam_anywhere_with_hands_and_cutoff(geom):
    loops = L.load("river_loops", "river_cutoffs")
    for sd in (2, 8, 10):
        ch = [vr.HandChain(L.load("hand", h), np.random.default_rng([sd, i]), z, geom.diag_w(z))
              for i, (h, z) in enumerate(vr.HAND_ZOOM.items())]
        P_, c, info = vr.approach_line(geom, start=0.0, length_w=7000, approaches=_approaches(sd, n=4, peak=40),
                                       hands=ch, handover="ladder", share=0.95, loops=loops, event="neck",
                                       events=1, rng=np.random.default_rng(sd), h=0.1)
        d = np.diff(P_, axis=0)
        th = np.arctan2(d[:, 1], d[:, 0])
        jump = np.abs((np.diff(th) + np.pi) % (2 * np.pi) - np.pi)
        assert jump.max() < math.radians(15), (sd, math.degrees(jump.max()))
