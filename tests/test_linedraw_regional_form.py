from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import LineString

from axibridge.linedraw import regional_form
from axibridge.linedraw.regional_allocation import prepare_case, select_details


def _candidate(name, points):
    return {"id": name, "points": points, "confidence": 0.8, "score": 10.0}


def _fixture():
    square_left = [(0, 0), (.5, 0), (.5, 1), (0, 1)]
    square_right = [(.5, 0), (1, 0), (1, 1), (.5, 1)]
    faces = [dict(id="left", cx=.2, cy=.2, rx=.08, ry=.08, enabled=True),
             dict(id="right", cx=.8, cy=.2, rx=.08, ry=.08, enabled=True)]
    people = [dict(id="a", face_id="left", polygon=square_left),
              dict(id="b", face_id="right", polygon=square_right)]
    regions = [dict(id="a-hand", person_id="a", category="hands_feet",
                    polygon=[(0, .45), (.45, .45), (.45, .65), (0, .65)], enabled=True),
               dict(id="a-body", person_id="a", category="body",
                    polygon=[(0, .7), (.45, .7), (.45, .9), (0, .9)], enabled=True),
               dict(id="b-hand", person_id="b", category="hands_feet",
                    polygon=[(.55, .45), (1, .45), (1, .65), (.55, .65)], enabled=True)]
    params = SimpleNamespace(faces=faces, people=people, detail_regions=regions,
                             face_budget=48, detail_budget=2,
                             detail_categories=["hands_feet", "clothing", "hair"])
    evidence = SimpleNamespace(rgb=np.ones((100, 100, 3)), foreground=np.ones((100, 100)),
                               alpha=None, normals=np.ones((100, 100, 3)),
                               reference_base=[], reference_whole=[],
                               reference_faces={"left": [_candidate("lf", [[10, 20], [30, 20]])],
                                                "right": [_candidate("rf", [[70, 20], [90, 20]])]},
                               reference_regions={"a-hand": [_candidate("ah", [[5, 50], [40, 50]])],
                                                  "a-body": [_candidate("ab", [[5, 80], [40, 80]])],
                                                  "b-hand": [_candidate("bh", [[60, 50], [95, 50]])]})
    return params, evidence


def _tuple_lines(paths):
    return tuple(tuple(map(tuple, q)) for q in paths)


def test_per_person_budget_and_category_toggle_preserve_base(monkeypatch):
    params, evidence = _fixture()
    hatch = LineString([(5, 75), (40, 75)])
    contour = LineString([(5, 50), (40, 50)])
    monkeypatch.setattr(regional_form, "_baseline",
                        lambda *_: ([(hatch, "hatch"), (contour, "contour")],
                                    LineString([(0, 0), (1, 1)]).buffer(1)))
    default = _tuple_lines(regional_form.render_regional(evidence, params))
    params.detail_categories = ["hands_feet", "clothing", "hair", "body"]
    with_body = _tuple_lines(regional_form.render_regional(evidence, params))
    params.detail_categories = ["clothing", "hair"]
    hidden = _tuple_lines(regional_form.render_regional(evidence, params))
    assert any(q[0][1] == 75 for q in default)  # hatching is fixed
    assert any(q[0][1] == 75 for q in with_body)
    assert any(q[0][1] == 75 for q in hidden)
    assert any(q[0][1] == 80 for q in with_body)
    assert not any(q[0][1] == 80 for q in default)
    assert any(q[0][1] == 50 and q[-1][0] == 40 for q in hidden)  # original contour restores
    params.detail_categories = ["hands_feet", "clothing", "hair"]
    assert default == _tuple_lines(regional_form.render_regional(evidence, params))
    # Both owners spend their own allowance despite the left person's body candidate.
    assert any(q[0][0] >= 60 and q[0][1] == 50 for q in with_body)


def test_explicit_ownership_required_for_multiple_faces():
    params, evidence = _fixture()
    params.people = []
    with pytest.raises(ValueError, match="explicit person ownership"):
        regional_form.render_regional(evidence, params)


def test_region_selection_protects_faces_and_independent_budgets():
    case = {"id": "test", "width": 100, "height": 100, "people": [
        {"id": "a", "owner_polygon": [(0, 0), (49, 0), (49, 99), (0, 99)],
         "face": {"id": "a-face", "ellipse": [20, 20, 8, 8]},
         "regions": [{"id": "ar", "category": "body", "polygon": [(0, 0), (49, 0), (49, 99), (0, 99)]}]},
        {"id": "b", "owner_polygon": [(50, 0), (99, 0), (99, 99), (50, 99)],
         "regions": [{"id": "br", "category": "body", "polygon": [(50, 0), (99, 0), (99, 99), (50, 99)]}]},
    ]}
    prepared = prepare_case(case, np.ones((100, 100)))
    source = {"case_id": "test", "regions": {
        "ar": [_candidate("across-face", [[5, 20], [40, 20]]),
               _candidate("a-safe", [[5, 70], [40, 70]])],
        "br": [_candidate("b-one", [[60, 70], [90, 70]]),
               _candidate("b-two", [[60, 80], [90, 80]])]}}
    result = select_details(source, case, prepared, "regional", 2)
    assert result["counts"] == {"a": 2, "b": 2}
    for q in result["selected"]:
        for x, y in q["points"]:
            assert not (12 <= x <= 28 and 12 <= y <= 28)


def test_material_base_renders_without_private_assets():
    rgb = np.ones((64, 64, 3), float) * [.75, .53, .4]
    rgb *= .95 + np.linspace(0, .1, 64)[:, None, None]
    rgb[30:50, 10:50] *= .65
    evidence = SimpleNamespace(rgb=rgb, foreground=np.ones((64, 64)), alpha=None,
        normals=np.zeros((64, 64, 3)), reference_base=None,
        reference_faces={}, reference_regions={})
    params = SimpleNamespace(faces=[dict(id="f", cx=.5, cy=.25, rx=.2, ry=.15, enabled=True)],
        people=[], detail_regions=[], face_budget=48, detail_budget=192,
        detail_categories=["hands_feet", "clothing", "hair"])
    paths = regional_form.render_regional(evidence, params)
    assert paths
    assert all(q.ndim == 2 and q.shape[1] == 2 and np.isfinite(q).all() for q in paths)
