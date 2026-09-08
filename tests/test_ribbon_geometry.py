from __future__ import annotations

from math import isclose

from shapely.geometry import Polygon

from axibridge.effects._ribbon_geometry import clip_paths, frames, sample_polyline, self_mask, sharp_corners, silhouette


def n(p, s): return {"p": p, "s": s}


def test_sampling_frames_and_sharp_corner_match_ribbon_contract():
    spine, stations, total = sample_polyline([(0, 0), (10, 0), (10, 10)], 3)
    assert spine == [(0.0, 0.0), (2.5, 0.0), (5.0, 0.0), (7.5, 0.0), (10.0, 0.0), (10.0, 2.5), (10.0, 5.0), (10.0, 7.5), (10.0, 10.0)]
    assert stations[-1] == total == 20
    assert sharp_corners(spine, stations) == [{"s": 10.0, "turn": 1.5707963267948966}]
    assert frames(spine)[4] == (-1.0, 1.0)


def test_silhouette_sweep_preserves_loop_hole_and_clip_blocks_boundary():
    spine = [n(p, i) for i, p in enumerate([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])]
    left = [n(p, i) for i, p in enumerate([(2, 2), (8, 2), (8, 8), (2, 8), (2, 2)])]
    right = [n(p, i) for i, p in enumerate([(-2, -2), (12, -2), (12, 12), (-2, 12), (-2, -2)])]
    mask = silhouette(left, right, spine)
    assert isclose(mask.area, 160.0)
    assert len(mask.interiors) == 1
    assert clip_paths([[(-5, 5), (15, 5)]], mask) == [[(-5.0, 5.0), (-2.0, 5.0)], [(2.0, 5.0), (8.0, 5.0)], [(12.0, 5.0), (15.0, 5.0)]]
    assert clip_paths([[(-5, -2), (15, -2)]], Polygon([(0, -2), (10, -2), (10, 2), (0, 2)])) == [[(-5.0, -2.0), (0.0, -2.0)], [(10.0, -2.0), (15.0, -2.0)]]


def test_self_mask_removes_later_crossing_but_not_accepted_loop():
    stations = [0.0, 10.0, 20.0, 30.0]
    # First and final passages cross.  The station exclusion keeps adjacent
    # faces drawable while the order choice controls the crossing passage.
    left = [n((-11, -9), 0), n((9, 11), 10), n((-11, 11), 20), n((9, -9), 30)]
    right = [n((-9, -11), 0), n((11, 9), 10), n((-9, 9), 20), n((11, -11), 30)]
    paths = [[n((-10, -10), 0), n((10, 10), 10), n((-10, 10), 20), n((10, -10), 30)]]
    visible = self_mask(paths, left, right, stations, [], 4)
    reversed_visible = self_mask(paths, left, right, stations, [], 4, reverse=True)
    assert visible and visible[0][0] == (-10.0, -10.0)
    assert visible[-1][-1] == (10.0, -10.0)
    assert reversed_visible and reversed_visible != visible
