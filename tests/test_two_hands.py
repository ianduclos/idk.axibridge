"""Two-hands source: contract (determinism, bounds) + the pen-split trick."""

from axibridge.registry import get_source


def _gen(**params):
    src = get_source("two_hands")
    return src.generate(src.Params(**params))


def test_registered_and_generates():
    doc = _gen(rounds=8)
    paths = doc.layers[0].paths
    assert paths
    assert all(len(p.points) >= 2 for p in paths)


def test_deterministic():
    a = _gen(rounds=8, seed=4)
    b = _gen(rounds=8, seed=4)
    assert [p.points for p in a.layers[0].paths] == [p.points for p in b.layers[0].paths]


def test_seed_varies_conversation():
    a = _gen(rounds=8, seed=1)
    b = _gen(rounds=8, seed=2)
    assert [p.points for p in a.layers[0].paths] != [p.points for p in b.layers[0].paths]


def test_pen_split_is_a_pure_filter():
    """Same seed ⇒ the identical conversation; `draw` only selects whose
    strokes are emitted. This is what makes the two-layer/two-pen recipe
    physically registered."""
    both = _gen(rounds=10, seed=7, draw="both")
    a = _gen(rounds=10, seed=7, draw="hand_a")
    b = _gen(rounds=10, seed=7, draw="hand_b")
    pts_both = [p.points for p in both.layers[0].paths]
    pts_a = [p.points for p in a.layers[0].paths]
    pts_b = [p.points for p in b.layers[0].paths]
    assert pts_a and pts_b
    assert len(pts_a) + len(pts_b) == len(pts_both)
    # every filtered stroke appears in the full conversation, in order
    it = iter(pts_both)
    assert all(any(x == y for y in it) for x in pts_a)
    it = iter(pts_both)
    assert all(any(x == y for y in it) for x in pts_b)


def test_stays_on_the_sheet():
    doc = _gen(rounds=12, size=100, a_length=80, b_length=80, seed=3)
    for p in doc.layers[0].paths:
        for x, y in p.points:
            assert 0 <= x <= 100 and 0 <= y <= 100


def test_rounds_dial():
    small = _gen(rounds=3, seed=5)
    big = _gen(rounds=30, seed=5)
    assert len(big.layers[0].paths) > len(small.layers[0].paths)


def test_agreeableness_changes_the_drawing():
    agree = _gen(rounds=10, agreeableness=1.0, seed=6)
    argue = _gen(rounds=10, agreeableness=0.0, seed=6)
    assert ([p.points for p in agree.layers[0].paths]
            != [p.points for p in argue.layers[0].paths])


def test_lifts_split_strokes():
    calm = _gen(rounds=10, a_lifts=0.0, b_lifts=0.0, seed=8)
    breathy = _gen(rounds=10, a_lifts=1.0, b_lifts=1.0, seed=8)
    assert len(breathy.layers[0].paths) > len(calm.layers[0].paths)
