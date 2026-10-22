"""Curve fitter (pen v2, task 2): a sampled stroke -> editable pen anchors
(Schneider's algorithm), plus POST /api/geometry/fit. Later tasks use it for
sketch-then-fit and for turning found fill areas into pen paths, so these
tests lean on messy and degenerate input as much as on clean curves."""

from __future__ import annotations

import math
import random
import time

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge import curvefit
from axibridge.curvefit import fit_bezier
from axibridge.sources import pen


def _flatten(anchors: list[dict], closed: bool) -> list[tuple[float, float]]:
    sp = pen.PenSubpath(anchors=[pen.PenAnchor(**a) for a in anchors], closed=closed)
    return pen._flatten_subpath(sp, 0.05)


def _seg_dist(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    d2 = dx * dx + dy * dy
    t = 0.0 if d2 < 1e-18 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / d2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _dist_to_polyline(p, poly) -> float:
    return min(_seg_dist(p, a, b) for a, b in zip(poly, poly[1:]))


def _all_finite(anchors: list[dict]) -> bool:
    vals = []
    for a in anchors:
        vals += [a["x"], a["y"]]
        for h in (a["in_handle"], a["out_handle"]):
            if h is not None:
                vals += list(h)
    return all(math.isfinite(v) for v in vals)


def _quarter_circle(n=200, r=50.0, cx=100.0, cy=100.0):
    return [(cx + r * math.cos(0.5 * math.pi * i / (n - 1)),
             cy + r * math.sin(0.5 * math.pi * i / (n - 1))) for i in range(n)]


def test_fit_quarter_circle_is_close():
    pts = _quarter_circle()
    anchors = fit_bezier(pts, closed=False, detail=0.5)
    assert 2 <= len(anchors) <= 4
    assert anchors[0]["in_handle"] is None and anchors[-1]["out_handle"] is None
    flat = _flatten(anchors, closed=False)
    worst = max(_dist_to_polyline(p, flat) for p in pts)
    assert worst <= 0.5, worst
    # anchors land on the stroke's ends
    assert math.dist((anchors[0]["x"], anchors[0]["y"]), pts[0]) < 1e-6
    assert math.dist((anchors[-1]["x"], anchors[-1]["y"]), pts[-1]) < 1e-6


def test_anchors_are_shaped_like_pen_anchors():
    anchors = fit_bezier(_quarter_circle(), closed=False, detail=0.5)
    for a in anchors:
        assert set(a) == {"x", "y", "in_handle", "out_handle", "join"}
        assert pen.PenAnchor(**a).model_dump() == a


def _wavy(n=300):
    return [(10 + 180 * i / (n - 1), 100 + 8 * math.sin(i / (n - 1) * 6 * math.pi)) for i in range(n)]


def test_detail_controls_anchor_count():
    pts = _wavy()
    lo, hi = fit_bezier(pts, False, 0.0), fit_bezier(pts, False, 1.0)
    assert len(hi) > len(lo)
    # and detail=1 really is close (tolerance 0.05 mm, parametric error bound)
    flat = _flatten(hi, closed=False)
    assert max(_dist_to_polyline(p, flat) for p in pts) <= 0.06


def _square(x0=20.0, y0=20.0, side=40.0, step=0.5):
    corners = [(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)]
    pts = []
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):
        n = int(round(side / step))
        pts += [(ax + (bx - ax) * i / n, ay + (by - ay) * i / n) for i in range(n)]
    # start mid-edge, so the fitter has to find the corners rather than inherit one
    k = len(pts) // 8
    return pts[k:] + pts[:k], corners


def test_square_keeps_corners():
    pts, corners = _square()
    anchors = fit_bezier(pts, closed=True, detail=0.5)
    assert len(anchors) == 4
    assert all(a["join"] == "corner" for a in anchors)
    for c in corners:
        assert min(math.dist(c, (a["x"], a["y"])) for a in anchors) <= 0.5
    flat = _flatten(anchors, closed=True)
    assert max(_dist_to_polyline(p, flat) for p in pts) <= 0.5


def test_closed_loop_is_a_loop():
    n = 400
    pts = [(150 + 40 * math.cos(2 * math.pi * i / n), 100 + 40 * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    pts.append(pts[0])  # a closing duplicate is tolerated, not doubled
    anchors = fit_bezier(pts, closed=True, detail=0.5)
    assert len(anchors) >= 2
    first, last = anchors[0], anchors[-1]
    assert math.dist((first["x"], first["y"]), (last["x"], last["y"])) > 1.0  # no duplicate end anchor
    assert all(a["in_handle"] is not None and a["out_handle"] is not None for a in anchors)
    assert all(a["join"] == "smooth" for a in anchors)  # a circle has no corners
    flat = _flatten(anchors, closed=True)
    assert max(_dist_to_polyline(p, flat) for p in pts) <= 0.5


def test_hand_jitter_does_not_make_corners():
    rng = random.Random(7)
    pts = [(20 + 0.3 * i + rng.uniform(-0.08, 0.08), 80 + rng.uniform(-0.08, 0.08))
           for i in range(400)]
    anchors = fit_bezier(pts, closed=False, detail=0.3)
    assert not any(a["join"] == "corner" for a in anchors)


def test_open_v_has_one_corner():
    pts = [(10 + i * 0.5, 10 + i * 0.5) for i in range(61)] + \
          [(40 + i * 0.5, 40 - i * 0.5) for i in range(1, 60)]
    anchors = fit_bezier(pts, closed=False, detail=0.5)
    corners = [a for a in anchors if a["join"] == "corner"]
    assert len(corners) == 1
    assert math.dist((corners[0]["x"], corners[0]["y"]), (40, 40)) <= 0.5


def test_corner_between_samples_is_still_one_corner():
    # the tip fell between two samples: the turn is split over a 1 mm chamfer
    pts = [(10 + i * 0.5, 10 + i * 0.5) for i in range(60)] + \
          [(40 + i * 0.5, 40 - i * 0.5) for i in range(1, 60)]
    anchors = fit_bezier(pts, closed=False, detail=0.5)
    corners = [a for a in anchors if a["join"] == "corner"]
    assert len(corners) == 1
    assert math.dist((corners[0]["x"], corners[0]["y"]), (40, 40)) <= 1.0


def test_cusp_corner_sits_on_the_tip():
    # a stroke that doubles back: every sample within a window of the tip
    # turns ~180 degrees at the coarse scale; the corner must be the tip itself
    pts = [(10 + i * 0.2, 10) for i in range(100)] + [(30 - i * 0.2, 10.0) for i in range(1, 100)]
    anchors = fit_bezier(pts, closed=False, detail=0.5)
    corners = [a for a in anchors if a["join"] == "corner"]
    assert len(corners) == 1
    assert math.dist((corners[0]["x"], corners[0]["y"]), (29.8, 10)) <= 0.25
    assert len(anchors) == 3  # two straight strokes need nothing more


def test_degenerate_inputs():
    for pts, closed in (([(5, 5), (5, 5), (5, 5)], False), ([(5, 5), (5, 5), (5, 5)], True),
                        ([(10, 10), (30, 20)], False), ([(10, 10), (30, 20)], True)):
        anchors = fit_bezier(pts, closed=closed, detail=0.5)
        assert len(anchors) >= 2, (pts, closed)
        assert _all_finite(anchors)
        for a in anchors:
            pen.PenAnchor(**a)


def test_rejects_non_finite_points():
    with pytest.raises(ValueError):
        fit_bezier([(0, 0), (float("nan"), 1), (3, 3)], closed=False, detail=0.5)


def _random_walk(n=20000):
    rng = random.Random(3)
    pts, x, y, a = [], 150.0, 100.0, 0.0
    for _ in range(n):
        a += rng.uniform(-0.4, 0.4)
        x += 0.05 * math.cos(a) + rng.uniform(-0.03, 0.03)
        y += 0.05 * math.sin(a) + rng.uniform(-0.03, 0.03)
        pts.append((x, y))
    return pts


def _white_noise(n=20000):
    rng = random.Random(5)
    return [(rng.uniform(0, 300), rng.uniform(0, 218)) for _ in range(n)]


def _jitter_line(n=20000):
    rng = random.Random(9)
    return [(10 + 280 * i / (n - 1) + rng.uniform(-0.3, 0.3), 100 + rng.uniform(-0.3, 0.3))
            for i in range(n)]


def test_fitter_cap_matches_the_pen_source():
    assert curvefit.MAX_ANCHORS == pen._MAX_ANCHORS


@pytest.mark.parametrize("make", [_random_walk, _white_noise, _jitter_line])
@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize("detail", [0.0, 1.0])
def test_huge_messy_input_is_fast_finite_and_editable(make, closed, detail):
    # always an editable path: never more anchors than the pen source accepts
    pts = make()
    t0 = time.perf_counter()
    anchors = fit_bezier(pts, closed=closed, detail=detail)
    assert time.perf_counter() - t0 < 3.0
    assert 2 <= len(anchors) <= pen._MAX_ANCHORS
    assert _all_finite(anchors)
    pen.PenSource().generate(pen.PenParams(subpaths=[pen.PenSubpath(
        anchors=[pen.PenAnchor(**a) for a in anchors], closed=closed)]))


def _antiparallel(a) -> bool:
    (ix, iy), (ox, oy) = a["in_handle"], a["out_handle"]
    return (ix * ox + iy * oy) / (math.hypot(ix, iy) * math.hypot(ox, oy)) < -0.999


@pytest.mark.parametrize("pts, closed", [
    ([(10, 10), (30, 20)], True),
    ([(10, 10), (30, 20), (10, 10.0000001)], True),
    (_quarter_circle(), False),
    (_square()[0], True),
    ([(150 + 40 * math.cos(2 * math.pi * i / 400), 100 + 40 * math.sin(2 * math.pi * i / 400))
      for i in range(400)], True),
    (_white_noise(300), True),
])
def test_join_labels_match_the_handles(pts, closed):
    # "smooth" is a promise the handles are collinear: a retracing cusp
    # (both handles pointing the same way) must say "corner"
    for a in fit_bezier(pts, closed=closed, detail=0.5):
        if a["in_handle"] is not None and a["out_handle"] is not None and a["join"] == "smooth":
            assert _antiparallel(a), a


def test_two_point_loop_is_cornered():
    anchors = fit_bezier([(10, 10), (30, 20)], closed=True, detail=0.5)
    assert len(anchors) == 2
    assert all(a["join"] == "corner" for a in anchors)


def test_non_finite_handle_raises_rather_than_vanishing():
    with pytest.raises(ValueError):
        curvefit._anchor((1.0, 2.0), (float("nan"), 0.0), (1.0, 0.0), "smooth")


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def test_route_fits_and_bounds(client):
    pts = [list(p) for p in _quarter_circle()]
    r = client.post("/api/geometry/fit", json={"points": pts, "closed": False, "detail": 0.5})
    assert r.status_code == 200, r.text
    anchors = r.json()["anchors"]
    assert 2 <= len(anchors) <= 4
    for a in anchors:
        pen.PenAnchor(**a)

    assert client.post("/api/geometry/fit",
                       json={"points": pts, "closed": False, "detail": 2}).status_code == 422
    assert client.post("/api/geometry/fit",
                       json={"points": pts[:1], "closed": False, "detail": 0.5}).status_code == 422
    assert client.post("/api/geometry/fit",
                       json={"points": [[0, 0]] * 20001, "closed": False,
                             "detail": 0.5}).status_code == 422


@pytest.mark.parametrize("body", [
    '{"points": [[0, 0], [NaN, 1], [3, 3]], "closed": false, "detail": 0.5}',
    '{"points": [[0, 0], [1, Infinity], [3, 3]], "closed": false, "detail": 0.5}',
    '{"points": [[0, 0], [1, 1], [3, 3]], "closed": false, "detail": NaN}',
])
def test_route_rejects_non_finite(client, body):
    # a clean 422, not a 500 from echoing NaN back in the error body
    r = client.post("/api/geometry/fit", content=body,
                    headers={"content-type": "application/json"})
    assert r.status_code == 422, r.text
