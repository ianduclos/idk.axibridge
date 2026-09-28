import math
from tools.linedraw_research.guidance import select_balanced, select_guided


FACE = {"ellipse": [50, 50, 50, 50]}
GEOMETRY = {"status": "ok", "feature_contours": {
    "left_eye": [[10, 20], [30, 20]], "right_eye": [[70, 20], [90, 20]],
    "left_brow": [[10, 12], [30, 12]], "right_brow": [[70, 12], [90, 12]],
    "nose": [[50, 30], [50, 60]], "mouth": [[35, 75], [65, 75]],
    "face_contour": [[0, 0], [0, 100]],
}}


def candidate(id, points, score=10):
    return {"id": id, "points": points, "confidence": 0.8,
            "length": math.dist(points[0], points[-1]), "score": score}


def test_fallback_is_stable_and_untouched():
    candidates = [candidate("b", [[10, 20], [30, 20]], 2),
                  candidate("a", [[70, 20], [90, 20]], 3)]
    result = select_guided(candidates, FACE, {"status": "unavailable"}, 1)
    assert result["status"] == "unavailable"
    assert result["candidates"] == [candidates[1]]


def test_coverage_duplicate_and_maximum_displacement():
    candidates = [candidate("eye-a", [[10, 21], [30, 21]], 100),
                  candidate("eye-b", [[10, 21.2], [30, 21.2]], 90),
                  candidate("mouth", [[35, 76], [65, 76]], 5)]
    result = select_guided(candidates, FACE, GEOMETRY, 2)
    selected = result["candidates"]
    assert result["status"] == "ok"
    assert {c["id"] for c in selected} == {"eye-a", "mouth"}
    assert {c["feature"] for c in selected} == {"left_eye", "mouth"}
    assert all(math.dist(a, b) <= 1.5 + 1e-9
               for c in selected for a, b in zip(next(x for x in candidates if x["id"] == c["id"])["points"], c["points"]))
    for c in selected:
        original = next(x for x in candidates if x["id"] == c["id"])
        assert c["source_length"] == original["length"]
        assert c["source_score"] == original["score"]
        actual_length = sum(math.dist(a, b) for a, b in zip(c["points"], c["points"][1:]))
        assert math.isclose(c["length"], actual_length)
        assert math.isclose(c["score"], actual_length ** .67 * (.22 + c["confidence"]) ** .5)


def test_unsupported_stroke_stays_exactly_where_it_was():
    c = candidate("isolated", [[40, 40], [60, 40]])
    result = select_guided([c], FACE, GEOMETRY, 18)
    assert result["candidates"][0]["points"] == c["points"]
    assert "feature" not in result["candidates"][0]


def test_boundary_point_cannot_move_outside_ellipse():
    geometry = {"status": "ok", "feature_contours": {"face_contour": [[100.5, 40], [100.5, 60]]}}
    c = candidate("edge", [[99.7, 45], [99.7, 55]])
    result = select_guided([c], FACE, geometry, 1)
    assert result["candidates"][0]["points"] == c["points"]


def test_balanced_spends_extra_allowance_on_supported_eyes_and_mouth():
    long_unassigned = [candidate(f"unassigned-{i}", [[10, 48 + i * 2], [30, 48 + i * 2]], 100 - i)
                       for i in range(8)]
    eyes = [candidate(f"eye-{i}", [[10, 20 + i * 2], [30, 20 + i * 2]], 15 - i)
            for i in range(3)]
    mouths = [candidate(f"mouth-{i}", [[35, 75 + i * 2], [65, 75 + i * 2]], 15 - i)
              for i in range(3)]
    result = select_balanced(long_unassigned + eyes + mouths, FACE, GEOMETRY, 8)
    counts = result["diagnostics"]["class_counts"]
    assert len(result["candidates"]) == 8
    assert counts["left_eye"] >= 2
    assert counts["mouth"] >= 2
    assert counts["left_eye"] + counts["mouth"] > counts["unassigned"]
    assert all(c["id"] in {x["id"] for x in long_unassigned + eyes + mouths} for c in result["candidates"])
