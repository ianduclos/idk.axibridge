"""Synthetic, source-pixel checks for the frozen research Light recipe."""

from types import SimpleNamespace

import numpy as np
from shapely.geometry import LineString

from axibridge.linedraw.reference_light import _select, render_light
from axibridge.linedraw.reference_trace import trace_candidates, trace_face_candidates


def _candidate(identity, x, y, score=1):
    return {"id": identity, "points": [[x, y], [x + 4, y]],
            "length": 4, "confidence": .5, "score": score}


def test_native_map_trace_keeps_source_affine_and_research_fields():
    image = np.ones((24, 24), dtype=float)
    image[12, 3:21] = .2
    found = trace_candidates(image, (10, 20, 58, 68), (80, 90))
    assert found
    assert set(found[0]) == {"id", "points", "length", "confidence", "score"}
    assert found == sorted(found, key=lambda q: (-q["score"], q["id"]))
    assert all(10 <= x <= 58 and 20 <= y <= 68
               for q in found for x, y in q["points"])
    assert any(q["length"] > 25 for q in found)


def test_face_candidates_are_clipped_and_reranked_before_budget(monkeypatch):
    whiteness = np.full((40, 40), .2)
    raw = [
        {"id": "face-crop-00000", "points": [[0, 23.5], [40, 23.5]],
         "length": 40, "confidence": .8, "score": 20},
        {"id": "face-crop-00001", "points": [[17, 17], [23, 17]],
         "length": 6, "confidence": .8, "score": 4},
    ]
    monkeypatch.setattr("axibridge.linedraw.reference_trace._trace_candidates",
                        lambda *args, **kwargs: raw)
    found = trace_face_candidates(whiteness, (0, 0, 40, 40), (40, 40),
                                  "face", (20, 20, 4, 4))
    assert len(found) == 2
    assert found[0]["id"] == "face-crop-00001-00"
    assert found[1]["length"] < 40
    assert all(16 <= x <= 24 and 16 <= y <= 24
               for q in found for x, y in q["points"])


def test_foreground_weighted_grid_selection_is_nested():
    fg = np.zeros((90, 90), dtype=bool)
    fg[0:30, 0:30] = True
    fg[0:10, 60:70] = True
    pool = [_candidate(f"left-{i}", 4 + i, 8) for i in range(6)]
    pool += [_candidate(f"right-{i}", 64 + i, 8) for i in range(6)]
    short = _select(pool, 4, fg)
    long = _select(pool, 8, fg)
    assert short == long[:4]
    assert [q["id"].split("-")[0] for q in short] == ["left", "left", "left", "right"]


def test_light_preserves_selected_contour_exactly_without_shadow():
    h, w = 48, 48
    contour = _candidate("contour", 8, 20)
    evidence = SimpleNamespace(rgb=np.ones((h, w, 3)), foreground=np.ones((h, w), bool),
                               normals=np.zeros((h, w, 3)),
                               reference_whole=[contour], reference_tiles=[])
    paths = render_light(evidence, SimpleNamespace(contour_budget=1))
    assert len(paths) == 1
    np.testing.assert_array_equal(paths[0], contour["points"])


def test_hatch_clearance_from_contour(monkeypatch):
    h, w = 64, 64
    contour = _candidate("contour", 12, 30)
    contour["points"] = [[12, 30], [50, 30]]
    rgb = np.ones((h, w, 3))
    rgb[8:56, 8:56] = .1
    evidence = SimpleNamespace(rgb=rgb, foreground=np.ones((h, w), bool),
                               normals=np.zeros((h, w, 3)),
                               reference_whole=[contour], reference_tiles=[])
    monkeypatch.setattr("axibridge.linedraw.reference_light.shapes",
                        lambda field, fg, sigma, minarea, cap, threshold, checkpoint:
                        ([], np.ones((h, w), bool)))
    monkeypatch.setattr("axibridge.linedraw.reference_light.flow_hatch",
                        lambda room, normals, spacing, checkpoint: [np.array([[20., 10.], [20., 50.]])])
    paths = render_light(evidence, SimpleNamespace(contour_budget=1))
    assert np.array_equal(paths[0], np.asarray(contour["points"]))
    assert len(paths) > 1
    protected = LineString(contour["points"])
    assert all(LineString(q).distance(protected) >= 3 * h * .001 - .01 for q in paths[1:])
