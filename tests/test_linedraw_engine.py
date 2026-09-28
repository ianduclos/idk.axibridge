import numpy as np
import pytest
from axibridge.linedraw.contracts import Evidence, LinedrawV3Params


@pytest.fixture
def evidence():
    rgb = np.ones((64, 64, 3), dtype=np.float32) * 0.8
    rgb[16:48, 16:48] = 0.18
    lines = np.ones((64, 64), dtype=np.float32)
    lines[10:54, 30] = 0
    normals = np.zeros((64, 64, 3), dtype=np.float32)
    normals[..., 2] = 1
    return Evidence(rgb, np.ones((64, 64), dtype=np.float32), normals, lines, lines)


def test_light_keeps_contours(evidence):
    from axibridge.linedraw.engine import render_document

    p = LinedrawV3Params(width=64, contour_budget=12, clearance=2)
    plain = render_document(evidence, p.model_copy(update={"style": "contours"}))
    light = render_document(evidence, p)
    a = [x.points for _, x in plain.iter_paths()]
    b = [x.points for _, x in light.iter_paths()]
    assert a and b[: len(a)] == a
    assert all(not p.filled for _, p in light.iter_paths())


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
def test_paper_bounds_and_determinism(evidence, rotate):
    from axibridge.linedraw.engine import render_document

    p = LinedrawV3Params(width=40, rotate=rotate, style="shadow_shapes")
    doc = render_document(evidence, p)
    assert doc == render_document(evidence, p)
    points = np.array([pt for _, path in doc.iter_paths() for pt in path.points])
    assert len(points) > 0 and np.isfinite(points).all()
    assert points.min() >= 0 and points.max() <= 40
    assert all(not path.filled for _, path in doc.iter_paths())


def test_empty_foreground(evidence):
    from axibridge.linedraw.engine import render_document
    from dataclasses import replace

    doc = render_document(
        replace(evidence, foreground=np.zeros((64, 64))), LinedrawV3Params()
    )
    assert not list(doc.iter_paths())


def test_material_without_faces_reports_error(evidence):
    from axibridge.linedraw.engine import render_document

    with pytest.raises(ValueError, match="face"):
        render_document(evidence, LinedrawV3Params(shadow_proxy="material"))


def test_fill_preserves_hole():
    from axibridge.linedraw.engine import fill_lines
    from shapely.geometry import Polygon, LineString

    shape = Polygon(
        [(0, 0), (20, 0), (20, 20), (0, 20)],
        holes=[[(5, 5), (15, 5), (15, 15), (5, 15)]],
    )
    paths = fill_lines(shape, 1, lambda: None)
    assert paths and all(shape.covers(LineString(p)) for p in paths)
