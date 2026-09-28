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


def test_native_candidates_drive_contours_when_resized_map_is_blank():
    from axibridge.linedraw.contracts import Candidate
    from axibridge.linedraw.engine import render_document

    blank = np.ones((24, 24), dtype=np.float32)
    evidence = Evidence(
        np.ones((24, 24, 3)),
        blank,
        None,
        blank,
        blank,
        whole_candidates=(Candidate(np.array([[12, 3], [12, 20]]), 1, "native"),),
        tiled_candidates=(),
    )
    doc = render_document(evidence, LinedrawV3Params(style="contours", width=24))
    paths = [path for _, path in doc.iter_paths()]
    assert len(paths) == 1
    assert np.allclose(np.asarray(paths[0].points)[:, 0], 12)


def test_clipping_honors_cancellation():
    from axibridge.linedraw.contracts import Candidate
    from axibridge.linedraw.engine import clipped_candidates
    from axibridge.render_work import RenderCancelled

    def cancelled():
        raise RenderCancelled()

    with pytest.raises(RenderCancelled):
        clipped_candidates(
            [Candidate(np.array([[2, 2], [12, 12]]), 1, "line")],
            np.ones((24, 24), bool),
            checkpoint=cancelled,
        )
