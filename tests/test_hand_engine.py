"""The hand engine: a frozen library hand follows an arbitrary line.

Deviation is always measured the way the spec defines it — the distance from
an output point to the nearest point of the INPUT polyline (shapely, exact).
"""
from __future__ import annotations

import numpy as np
import pytest
import shapely

from axibridge.effects._hand import engine as E

HANDS = ("matisse", "river_meander", "dance_staccato")


def _s_curve(length: float = 400.0) -> np.ndarray:
    t = np.linspace(0.0, 1.0, 400)
    p = np.column_stack([280.0 * t, 70.0 * np.sin(2 * np.pi * t)])
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1).sum()
    p = p * (length / seg)
    return p + np.array([10.0, 109.0])


def _square(size: float = 80.0) -> np.ndarray:
    x0, y0 = 100.0, 60.0
    return np.array([[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]])


def _zigzag() -> np.ndarray:
    return np.array([[20.0 + 30 * i, 100.0 + (30.0 if i % 2 else 0.0)] for i in range(8)])


FIXTURES = {"s_curve": (_s_curve(), False), "square": (_square(), True), "zigzag": (_zigzag(), False)}


@pytest.fixture(scope="module")
def hands():
    out = {h: E.load_hand(h, None) for h in HANDS}
    assert all(g is not None for g in out.values())
    return out


def _deviation(out: np.ndarray, inp: np.ndarray) -> np.ndarray:
    line = shapely.LineString(inp)
    return shapely.distance(shapely.points(out), line)


def _run(g, fixture, seed=0, stray=3.0, bend=20.0, wander=False):
    pts, closed = FIXTURES[fixture]
    return E.follow(pts, closed, g, np.random.default_rng(seed), stray, bend, wander)


def test_never_beyond_ceiling(hands):
    for h, g in hands.items():
        for seed in range(2):
            for name, (pts, closed) in FIXTURES.items():
                for stray in (1.0, 20.0):
                    for wander in (False, True):
                        out = E.follow(pts, closed, g, np.random.default_rng(seed), stray, 20.0, wander)
                        ceiling = E.MODES["wander" if wander else "follow"][1]
                        dev = _deviation(out, pts)
                        assert np.all(np.isfinite(out))
                        assert dev.max() <= ceiling * stray + 1e-6, (h, seed, name, stray, wander, dev.max())


def test_typical_deviation_tracks_stray(hands):
    for h, g in hands.items():
        for name in ("s_curve", "square"):
            pts = FIXTURES[name][0]
            lo = np.median(_deviation(_run(g, name, stray=2.0), pts))
            hi = np.median(_deviation(_run(g, name, stray=10.0), pts))
            assert hi > lo, (h, name, lo, hi)
            assert lo <= 2.0 and hi <= 10.0, (h, name, lo, hi)


def _signed_offset(out: np.ndarray, inp: np.ndarray) -> np.ndarray:
    line = shapely.LineString(inp)
    s = shapely.line_locate_point(line, shapely.points(out))
    q = np.column_stack(shapely.get_coordinates(shapely.line_interpolate_point(line, s)).T)
    q2 = shapely.get_coordinates(shapely.line_interpolate_point(line, np.minimum(s + 0.5, line.length)))
    q1 = shapely.get_coordinates(shapely.line_interpolate_point(line, np.maximum(s - 0.5, 0.0)))
    t = q2 - q1
    v = out - q
    return t[:, 0] * v[:, 1] - t[:, 1] * v[:, 0]


def _sign_changes(d: np.ndarray, thresh: float) -> int:
    big = d[np.abs(d) > thresh]
    return int(np.count_nonzero(np.diff(np.sign(big)) != 0))


def test_bend_size_changes_scale(hands):
    pts = FIXTURES["s_curve"][0]
    for h, g in hands.items():
        small = sum(_sign_changes(_signed_offset(_run(g, "s_curve", seed=s, bend=5.0), pts), 0.3)
                    for s in range(2))
        large = sum(_sign_changes(_signed_offset(_run(g, "s_curve", seed=s, bend=60.0), pts), 0.3)
                    for s in range(2))
        assert small > large, (h, small, large)


def test_wander_departs_further(hands):
    for h, g in hands.items():
        for seed in range(2):
            pts = FIXTURES["s_curve"][0]
            f = np.median(_deviation(_run(g, "s_curve", seed=seed, stray=3.0), pts))
            w = np.median(_deviation(_run(g, "s_curve", seed=seed, stray=3.0, wander=True), pts))
            assert w > f, (h, seed, f, w)


def test_ends_and_closure(hands):
    for g in hands.values():
        for name, (pts, closed) in FIXTURES.items():
            for stray in (1.0, 20.0):
                out = _run(g, name, stray=stray)
                if closed:
                    assert np.array_equal(out[0], out[-1])
                else:
                    assert np.array_equal(out[0], pts[0]) and np.array_equal(out[-1], pts[-1])
                assert out.ndim == 2 and out.shape[1] == 2 and len(out) > len(pts)


def test_deterministic_and_finite(hands):
    for g in hands.values():
        for name in ("s_curve", "square"):
            a = _run(g, name, seed=7, wander=True)
            b = _run(g, name, seed=7, wander=True)
            assert np.array_equal(a, b)
            assert np.all(np.isfinite(a))
            c = _run(g, name, seed=8, wander=True)
            assert not (a.shape == c.shape and np.array_equal(a, c))


def test_degenerate_inputs_pass_through(hands):
    g = hands["matisse"]
    cases = [
        (np.array([[10.0, 10.0]]), False),
        (np.array([[10.0, 10.0], [10.0, 10.0]]), False),
        (np.array([[10.0, 10.0], [10.0, 10.0]]), True),
        (np.array([[10.0, 10.0], [10.1, 10.0]]), False),
    ]
    for pts, closed in cases:
        out = E.follow(pts, closed, g, np.random.default_rng(0), 3.0, 20.0, False)
        assert np.array_equal(out, pts)
        assert out is not pts


def test_unknown_hand_loads_none():
    assert E.load_hand("no_such_hand", None) is None
    assert E.load_hand("matisse", "000000000000") is None


def test_pinned_current_hash_loads():
    from axibridge.sources._gesture_studies import frozen_library as FL
    h = next(o["hash"] for o in FL.options("hand") if o["id"] == "matisse")
    assert E.load_hand("matisse", h) is not None


# --- the hard ceiling, on its own (the tanh band alone rarely reaches it) ---

def _clamp_case(work, closed, C):
    rng = np.random.default_rng(3)
    lo, hi = work.min(axis=0) - 4 * C, work.max(axis=0) + 4 * C
    out = rng.uniform(lo, hi, size=(400, 2))
    line = shapely.LineString(work)
    before = shapely.distance(shapely.points(out), line)
    got = E._clamp(out.copy(), work, C, 0.3, closed)
    after = shapely.distance(shapely.points(got), line)
    assert np.all(after <= C + 1e-9), after.max()
    inside = before <= 0.9 * C          # well inside: untouched
    assert np.array_equal(got[inside], out[inside])
    moved = before > C + 0.2            # pulled to the ceiling, not collapsed onto the line
    assert np.any(moved) and np.all(after[moved] >= 0.9 * C)
    return got


def test_clamp_open_and_closed():
    _clamp_case(FIXTURES["s_curve"][0], False, 6.0)
    _clamp_case(FIXTURES["square"][0], True, 10.0)
    _clamp_case(FIXTURES["zigzag"][0], False, 2.0)


def test_clamp_near_open_end():
    work = np.array([[0.0, 0.0], [50.0, 0.0]])
    out = np.array([[-30.0, 0.0], [-3.0, 4.0], [54.0, -1.0], [60.0, 20.0], [25.0, 9.0]])
    got = E._clamp(out.copy(), work, 5.0, 0.3, False)
    after = shapely.distance(shapely.points(got), shapely.LineString(work))
    assert np.all(after <= 5.0 + 1e-9)
    assert np.allclose(got[0], [-5.0, 0.0])        # beyond the end: pulled toward the end point
    assert np.array_equal(got[2], out[2])           # within C of the end point: untouched


# --- the input's own loops are not folds ---

def _curl_line():
    """A 200 mm line with one deliberate curl (prolate cycloid, ~10 mm loop)."""
    phi = np.linspace(-np.pi, np.pi, 200)
    loop = 1.7 * np.column_stack([3 * phi - 6 * np.sin(phi), 6 * np.cos(phi)])
    return np.vstack([[[-100.0, loop[0, 1]]], loop, [[100.0, loop[-1, 1]]]]) + [120.0, 100.0]


def _figure8():
    t = np.linspace(0, 2 * np.pi, 400)
    p = np.column_stack([150 + 40 * np.sin(t), 100 + 20 * np.sin(2 * t)])
    p[-1] = p[0]
    return p


def _loops(p):
    """(self-crossing count, total enclosed loop area) of a polyline."""
    line = shapely.LineString(p)
    noded = shapely.node(line)
    n_cross = len(shapely.get_parts(noded)) - 1
    area = sum(g.area for g in shapely.get_parts(shapely.polygonize(shapely.get_parts(noded))))
    return n_cross, area


def test_input_loops_survive(hands):
    """The input's own loops are not folds: a curl and a figure-8 keep their
    crossings and roughly their loop area (a curl much smaller than the stray
    can still pinch through the offset itself; that is the band, not a cut)."""
    for pts, closed in ((_curl_line(), False), (_figure8(), True)):
        n0, a0 = _loops(pts)
        assert n0 >= 1
        for h, g in hands.items():
            for seed in range(2):
                for stray in (3.0, 5.0):          # at 5 mm the curl lies inside the fold window
                    out = E.follow(pts, closed, g, np.random.default_rng(seed), stray, 20.0, False)
                    n, a = _loops(out)
                    assert n >= n0 and 0.25 * a0 <= a <= 4 * a0, (h, seed, stray, closed, n, n0, a, a0)


def test_figure8_keeps_its_lobes_when_wandering(hands):
    pts = _figure8()
    n0, _ = _loops(pts)
    for h, g in hands.items():
        out = E.follow(pts, True, g, np.random.default_rng(0), 20.0, 20.0, True)
        assert _loops(out)[0] >= n0, h


# --- closed shapes keep their size; folds never eat the line ---

def _circle(r: float, n: int = 64) -> np.ndarray:
    t = np.linspace(0.0, 2 * np.pi, n)
    p = np.column_stack([100.0 + r * np.cos(t), 100.0 + r * np.sin(t)])
    p[-1] = p[0]
    return p


def _area(p: np.ndarray) -> float:
    return float(shapely.make_valid(shapely.Polygon(p)).area)


def test_closed_shapes_keep_their_area(hands):
    """A closed line must not inset (and fold inside-out) or balloon as a
    whole: the ring's mean offset is zero. Small circles at the defaults
    were the worst case (σ of the drift filters ≫ the ring)."""
    for r in (3.0, 6.0):
        pts = _circle(r)
        a0 = _area(pts)
        for h, g in hands.items():
            for seed in range(3):
                out = E.follow(pts, True, g, np.random.default_rng([seed, 0]), 3.0, 20.0, False)
                ratio = _area(out) / a0
                assert 0.6 <= ratio <= 1.6, (r, h, seed, ratio)
    rect = np.array([[20.0, 20.0], [60.0, 20.0], [60.0, 55.0], [20.0, 55.0], [20.0, 20.0]])
    a0 = _area(rect)
    for h, g in hands.items():
        for seed in range(3):
            out = E.follow(rect, True, g, np.random.default_rng([seed, 1]), 8.0, 20.0, True)
            ratio = _area(out) / a0
            assert 0.6 <= ratio <= 1.6, ("rect", h, seed, ratio)


# the contact-sheet drawing: tighter than FIXTURES (a 40x35 square, a zigzag
# with 10 mm runs), where a too-wide fold window used to cut most of the line
SHEET = {
    "s_curve": (np.array([(5 + 110 * i / 80, 20 + 14 * np.sin(i / 80 * 2 * np.pi * 1.2))
                          for i in range(81)]), False),
    "square": (np.array([(10, 40), (50, 40), (50, 75), (10, 75), (10, 40)], float), True),
    "zigzag": (np.array([(65, 45), (75, 75), (85, 45), (95, 75), (105, 45), (115, 75)], float), False),
}


def test_unfold_never_eats_the_line(hands):
    """Cutting folds removes small loops, never most of the line."""
    for h, g in hands.items():
        for seed in range(2):
            for name, (pts, closed) in (*FIXTURES.items(), *SHEET.items()):
                for stray, wander in ((3.0, False), (8.0, True)):
                    out = E.follow(pts, closed, g, np.random.default_rng([seed, 2]), stray, 20.0, wander)
                    kept = E._arclen(out)[-1] / E._arclen(pts)[-1]
                    assert kept >= 0.7, (h, seed, name, stray, wander, kept)


# --- the hand's stroke is memoised (stray drags and tweens are numpy only) ---

def test_heading_stream_is_memoised(hands, monkeypatch):
    g = hands["matisse"]
    pts, closed = FIXTURES["s_curve"]
    calls = []
    real = E._draw_heading
    monkeypatch.setattr(E, "_draw_heading", lambda *a: calls.append(1) or real(*a))
    E.clear_heading_cache()
    E.follow(pts, closed, g, np.random.default_rng([4, 0]), 3.0, 20.0, False)
    rng = np.random.default_rng([4, 0])
    cached = E.follow(pts, closed, g, rng, 9.0, 20.0, False)       # another stray: same stroke
    assert len(calls) == 1
    E.clear_heading_cache()
    rng2 = np.random.default_rng([4, 0])
    fresh = E.follow(pts, closed, g, rng2, 9.0, 20.0, False)
    assert len(calls) == 2
    assert np.array_equal(cached, fresh)
    assert rng.bit_generator.state == rng2.bit_generator.state     # a hit leaves the rng where drawing would
    E.follow(pts, closed, g, np.random.default_rng([5, 0]), 9.0, 20.0, False)   # another seed: drawn
    E.follow(pts, closed, g, np.random.default_rng([4, 0]), 9.0, 30.0, False)   # another bend: drawn
    assert len(calls) == 4


def test_long_strokes_are_cancellable(hands, monkeypatch):
    calls = []
    monkeypatch.setattr(E, "checkpoint", lambda: calls.append(1))
    E._draw_heading(hands["matisse"], np.random.default_rng(0), 400.0, 5.0, 0.3)
    assert len(calls) >= 2
