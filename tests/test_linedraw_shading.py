"""Component and opt-in shading behavior on synthetic evidence."""

import numpy as np
from shapely.geometry import LineString

from axibridge.linedraw.contracts import Candidate, Evidence, LinedrawV3Params
from axibridge.linedraw.engine import _smooth_path_mm, render_document
from axibridge.linedraw.flow_hatch import flow_hatch
from axibridge.linedraw.shading import scanline_mask


def _evidence():
    rgb = np.full((64, 64, 3), .8, dtype=np.float32)
    rgb[12:52, 12:52] = .12
    fg = np.ones((64, 64), dtype=np.float32)
    blank = np.ones((64, 64), dtype=np.float32)
    normals = np.zeros((64, 64, 3), dtype=np.float32)
    normals[..., 0] = .6
    normals[..., 2] = .8
    contour = Candidate(np.array([[8., 32.], [56., 32.]]), 1., "line")
    return Evidence(rgb, fg, normals, blank, blank,
                    whole_candidates=(contour,), tiled_candidates=())


def _geometry(doc):
    return [path.points for _, path in doc.iter_paths()]


def test_default_components_keep_original_contour_coordinates():
    evidence = _evidence()
    doc = render_document(evidence, LinedrawV3Params(style="contours", width=64))
    assert [(layer.id, layer.name) for layer in doc.layers] == [
        (1, "contours"), (2, "form"), (3, "cores")]
    assert doc.layers[0].paths
    assert any(path.points[0] == (8., 32.) and path.points[-1] == (56., 32.)
               for path in doc.layers[0].paths)
    assert not doc.layers[1].paths and not doc.layers[2].paths


def test_component_filter_is_exact_union_of_default_groups():
    evidence = _evidence()
    params = LinedrawV3Params(style="face_form", width=64, hatch_spacing=.5,
                               fill_spacing=.4)
    full = render_document(evidence, params)
    assert _geometry(full)
    pieces = [render_document(evidence, params.model_copy(
        update={"ink_components": [name]})) for name in ("contours", "form", "cores")]
    assert _geometry(full) == sum((_geometry(piece) for piece in pieces), [])
    assert [(piece.layers[0].id, piece.layers[0].name) for piece in pieces] == [
        (1, "contours"), (2, "form"), (3, "cores")]


def test_tonal_core_scanlines_preserve_hole_and_contour_clearance():
    mask = np.ones((24, 24), bool)
    mask[8:16, 8:16] = False
    contour = LineString([(2, 2), (22, 2)])
    protected = contour.buffer(1)
    lines = [part for q in scanline_mask(mask, 2) for part in
             [LineString(q).difference(protected)] if not part.is_empty]
    assert lines
    hole = LineString([(8, 12), (16, 12)])
    assert all(line.intersection(hole).is_empty for line in lines)
    assert all(line.distance(contour) >= 1 - 1e-9 for line in lines)


def test_coherent_flow_and_smoothing_are_finite_bounded_and_opt_in():
    mask = np.ones((32, 32), bool)
    normals = np.zeros((32, 32, 3), float)
    normals[..., 0] = .6
    original = flow_hatch(mask, normals, 5)
    coherent = flow_hatch(mask, normals, 5, coherent=True)
    assert original and coherent
    assert all(np.isfinite(q).all() for q in coherent)
    assert any(not np.array_equal(a, b) for a, b in zip(original, coherent))
    q = np.array([[0., 0.], [1., 1.], [2., 0.], [3., 1.]])
    assert np.array_equal(_smooth_path_mm(q, 0), q)
    smooth = _smooth_path_mm(q, .2)
    np.testing.assert_array_equal(smooth[[0, -1]], q[[0, -1]])
    assert np.max(np.linalg.norm(smooth - q, axis=1)) <= .2 + 1e-9


def test_tonal_density_field_changes_local_form_coverage():
    mask = np.ones((64, 64), bool)
    normals = np.zeros((64, 64, 3), float)
    light = flow_hatch(mask, normals, 5, density_field=np.zeros(mask.shape))
    dark = flow_hatch(mask, normals, 5, density_field=np.ones(mask.shape))
    assert len(dark) > len(light)
    assert all(np.isfinite(q).all() for q in light + dark)
