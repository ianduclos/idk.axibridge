"""Perceived lines: merges across breaks, never at a T or between parallel
neighbours; provenance; determinism; purity."""
import copy

import numpy as np

from gesture.core import Drawing, Stroke
from gesture.perceive import perceive


def _line(a, b, n=200, w=3.0):
    a, b = np.asarray(a, float), np.asarray(b, float)
    t = np.linspace(0, 1, n)[:, None]
    return Stroke(a + t * (b - a), width=np.full(n, w))


def _arc(c, r, a0, a1, n=300, w=3.0):
    t = np.linspace(a0, a1, n)
    return Stroke(np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)]), width=np.full(n, w))


def _d(*strokes):
    return Drawing(list(strokes), size=(1000, 1000))


def _counts(d):
    return d.meta["perceive"]["counts"]


def test_broken_arc_is_one_line_with_provenance():
    # one arc (r = 300 px, w = 3 px) cut into three pieces, gaps ≈ 2 w and 4 w;
    # pieces given out of order and one reversed
    a = _arc((500, 500), 300, 0.2, 1.0)
    b = _arc((500, 500), 300, 1.02, 1.8)
    c = _arc((500, 500), 300, 1.84, 2.8)
    c = Stroke(c.points[::-1].copy(), width=c.width.copy())
    r = perceive(_d(c, a, b))
    assert len(r.strokes) == 1
    st = r.strokes[0]
    assert sorted(f for f, _ in st.meta["fragments"]) == [0, 1, 2]
    assert len(st.meta["joins"]) == 2
    assert all(j["kind"] in ("near", "gap", "join") for j in st.meta["joins"])
    full = _arc((500, 500), 300, 0.2, 2.8).length()
    assert abs(st.length() - full) / full < 0.01
    # bridge points lie on the arc
    for b0, b1 in st.meta["bridges"]:
        rr = np.linalg.norm(st.points[b0:b1] - 500, axis=1)
        assert np.all(np.abs(rr - 300) < 1.5)


def test_faint_gap_aligned_merges_but_misaligned_does_not():
    ok = perceive(_d(_line((100, 500), (480, 500)), _line((510, 500), (900, 500))))   # 10 w, straight
    assert len(ok.strokes) == 1 and ok.strokes[0].meta["joins"][0]["kind"] == "gap"
    bent = perceive(_d(_line((100, 500), (480, 500)), _line((510, 500), (900, 700))))  # 27° turn
    assert len(bent.strokes) == 2


def test_no_merge_at_t_junction():
    # stem ending on the host's interior; host intact
    r = perceive(_d(_line((100, 500), (900, 500)), _line((500, 100), (500, 500))))
    assert len(r.strokes) == 2
    # host split at the T (bends 3°): host halves merge, the stem stays separate
    r = perceive(_d(_line((100, 500), (500, 500)), _line((500, 500), (900, 520)), _line((500, 100), (500, 500))))
    assert len(r.strokes) == 2
    merged = [s for s in r.strokes if len(s.meta["fragments"]) == 2][0]
    assert sorted(f for f, _ in merged.meta["fragments"]) == [0, 1]
    # two lines ending at one point of a third line at 60°: a vertex, not a corner
    r = perceive(_d(_line((100, 500), (900, 500)), _line((300, 200), (500, 500)),
                    _line((500, 500), (500 + 300 * np.cos(-1.0), 500 + 300 * np.sin(-1.0)))))
    assert len(r.strokes) == 3


def test_no_merge_of_parallel_neighbours():
    side = perceive(_d(_line((100, 500), (500, 500)), _line((100, 509), (500, 509))))
    stagger = perceive(_d(_line((100, 500), (500, 500)), _line((505, 509), (900, 509))))
    double = perceive(_d(_arc((500, 500), 300, 0.2, 2.0), _arc((500, 500), 309, 0.3, 2.1)))
    for r in (side, stagger, double):
        assert len(r.strokes) == 2 and sum(_counts(r).values()) == 0


def test_corner_join_symmetric_y_and_crossing():
    v = perceive(_d(_line((100, 500), (500, 500)),
                    _line((500, 500), (500 + 300 * np.cos(1.0), 500 + 300 * np.sin(1.0)))))
    assert len(v.strokes) == 1 and _counts(v)["join"] == 1
    c = np.array([500.0, 500.0])
    y = perceive(_d(*[_line(c, c + 300 * np.array([np.cos(a), np.sin(a)]))
                      for a in (0, 2 * np.pi / 3, 4 * np.pi / 3)]))
    assert len(y.strokes) == 3                      # three-way tie: ambiguous, left alone
    x = perceive(_d(_line((100, 100), (900, 900)), _line((100, 900), (496, 504)), _line((504, 496), (900, 100))))
    assert len(x.strokes) == 2 and _counts(x)["cross"] == 1


def test_closure():
    r = perceive(_d(_arc((500, 500), 300, 0, np.pi - 0.02), _arc((500, 500), 300, np.pi + 0.01, 2 * np.pi - 0.02)))
    assert len(r.strokes) == 1 and r.strokes[0].closed
    assert not np.allclose(r.strokes[0].points[0], r.strokes[0].points[-1])


def test_deterministic_and_pure():
    rng = np.random.default_rng(3)
    S = []
    for _ in range(25):
        a = rng.uniform(100, 900, 2)
        h = rng.uniform(0, 2 * np.pi)
        S.append(_line(a, a + rng.uniform(40, 200) * np.array([np.cos(h), np.sin(h)]), n=60))
    d = _d(*S)
    snap = copy.deepcopy(d)
    r1, r2 = perceive(d), perceive(d)
    assert len(r1.strokes) == len(r2.strokes)
    for s1, s2 in zip(r1.strokes, r2.strokes):
        assert np.array_equal(s1.points, s2.points) and s1.meta == s2.meta
    for s0, s in zip(snap.strokes, d.strokes):
        assert np.array_equal(s0.points, s.points) and np.array_equal(s0.width, s.width) and s0.meta == s.meta
    assert snap.meta == d.meta
    # every input stroke appears exactly once in the provenance
    used = sorted(f for s in r1.strokes for f, _ in s.meta["fragments"])
    assert used == list(range(len(S)))
    # ink is conserved up to the bridges
    ink0 = sum(s.length() for s in d.strokes)
    ink1 = sum(s.length() for s in r1.strokes)
    assert ink0 - 1e-6 <= ink1 <= ink0 + sum(j["gap_w"] * 3.0 * 2 for s in r1.strokes for j in s.meta["joins"]) + 1e-6
