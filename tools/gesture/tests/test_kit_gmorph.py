"""Round 13, II-a (gmorph): one hand's grammar morphed continuously along its line."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from gesture import kit  # noqa: E402
from gesture.kit import voices_gmorph as gmv  # noqa: E402

RESULTS = HERE / "results"


def _run(seed=13102, length=4.0, **voice):
    return kit.run({"frame": [200.0, 40.0], "seed": seed,
                    "voice": {"id": "gmorph", "hand": "river_belt", "length": length, **voice},
                    "renderer": {"id": "wire", "pen": 0.35}})


def _log(sh):
    return sh.marks[0].meta["gmorph"]["log"]


def test_registered_and_validates():
    assert "gmorph" in kit.registry("voice")
    rec = kit.validate({"voice": {"id": "gmorph"}})
    v = rec["parts"][0]["voice"]
    assert v["hand"] == "river_belt" and v["span"] is None and v["corners"] is None
    assert not kit.DISCOVERY_ERRORS


def test_schedule_knots_ease_and_hold():
    u = np.array([0.0, 0.1, 0.2, 0.4, 0.7, 0.9, 1.0])
    v = gmv.schedule([0.1, 2.0, 0.7, 4.0], u)
    assert v[0] == 2.0 and v[1] == 2.0                  # held before the first knot
    assert v[-1] == 4.0 and v[-2] == 4.0                # held after the last
    assert v[3] == pytest.approx(3.0)                   # cosine midpoint
    assert 2.0 < v[2] < 2.5                             # eased: slow out of a knot
    assert gmv.schedule(None, u, None) is None
    assert np.all(gmv.schedule([], u, 1.0) == 1.0)
    assert np.all(gmv.schedule([0.5, 7.0], u) == 7.0)
    with pytest.raises(ValueError):
        gmv.schedule([0.1, 1.0, 0.2], u)


def test_odd_schedule_refused_by_voice():
    with pytest.raises(ValueError):
        _run(span=[0.0, 0.5, 1.0])


def test_deterministic():
    a, b = _run(span=[0, .8, 1, .2], sign=[0, 1, 1, -1]), _run(span=[0, .8, 1, .2], sign=[0, 1, 1, -1])
    assert np.array_equal(a.marks[0].points, b.marks[0].points)
    c = _run(seed=13103, span=[0, .8, 1, .2], sign=[0, 1, 1, -1])
    assert not np.array_equal(a.marks[0].points, c.marks[0].points)


def test_corner_dial_removes_and_multiplies_corners():
    none = sum(1 for r in _log(_run(corners=[0, 0])) if r[1] == "corner")
    own = sum(1 for r in _log(_run()) if r[1] == "corner")
    many = sum(1 for r in _log(_run(corners=[0, 6])) if r[1] == "corner")
    assert none == 0
    assert many > 1.5 * max(own, 1)


def test_sign_dial_zigzag_vs_coil():
    zig = np.nanmean([m["zigzag"] for m in gmv.measure(_log(_run(sign=[0, 1], corners=[0, 0])), 4)])
    coil = np.nanmean([m["zigzag"] for m in gmv.measure(_log(_run(sign=[0, -1], corners=[0, 0])), 4)])
    assert zig > 0.85 and coil < 0.35


def test_span_and_turn_select_from_the_hands_own_vocabulary():
    short = np.median([r[2] for r in _log(_run(span=[0, .1])) if r[1] != "corner"])
    long_ = np.median([r[2] for r in _log(_run(span=[0, .9])) if r[1] != "corner"])
    assert long_ > 1.8 * short
    calm = np.median([abs(r[3]) for r in _log(_run(turn=[0, .1], sign=[0, 1])) if r[1] != "corner"])
    tight = np.median([abs(r[3]) for r in _log(_run(turn=[0, .9], sign=[0, 1])) if r[1] != "corner"])
    assert tight > 3 * calm
    # every segment length is one of the hand's (jittered) lengths: no scaling of the vocabulary
    g = kit.library.load("hand", "river_belt")
    lo = min(t[1] for s in g.strokes for t in s if t[0] != "corner")
    hi = max(t[1] for s in g.strokes for t in s if t[0] != "corner")
    segs = [r for r in _log(_run(span=[0, .9])) if r[1] != "corner"]
    assert all(r[2] <= 4.5 * hi for r in segs) and np.median([r[2] for r in segs]) >= lo


def test_channels_u_and_optional_r():
    sh = _run(r=[0, 0, 1, 2])
    m = sh.marks[0]
    u = np.asarray(m.channels["u"])
    assert u[0] == 0.0 and u[-1] == pytest.approx(1.0) and np.all(np.diff(u) >= -1e-12)
    r = np.asarray(m.channels["r"])
    assert r.min() >= 0.0 and r.max() <= 2.0 and r[-1] > r[0]
    assert "r" in _run().marks[0].channels   # filled with the wire default when not scheduled
    assert np.all(np.asarray(_run().marks[0].channels["r"]) == 0.0)


def test_fits_box_and_runs_along_the_valley():
    sh = _run(length=6.0)
    p = sh.marks[0].points
    assert p[:, 0].min() >= -1e-6 and p[:, 0].max() <= 200.0 + 1e-6
    assert p[:, 1].min() >= -1e-6 and p[:, 1].max() <= 40.0 + 1e-6
    assert p[-1, 0] > p[0, 0]


@pytest.mark.parametrize("name", ["gmorph-piece", "gmorph-close", "gmorph-schedule"])
def test_review_recipe_rebuilds(name):
    path = RESULTS / f"{name}.recipe.json"
    if not path.exists():
        pytest.skip("review recipe not written")
    rec = json.loads(path.read_text())
    sh = kit.run(rec)
    m = sh.marks[0]
    assert m.meta["gmorph"]["length_R"] == pytest.approx(rec["parts"][0]["voice"]["length"], rel=1e-6)
    assert len(m.points) > 1000
