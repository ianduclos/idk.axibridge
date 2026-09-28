"""Procedural fixtures only: no photographs, model maps or reference geometry."""
import numpy as np
import pytest
from shapely.geometry import LineString, box, Polygon
from tools.linedraw_research.flow_hatch import flow_hatch
from tools.linedraw_research.geometry import fit
from tools.linedraw_research.shadows import (
    shadow_field, shapes, clear_hatching, cut_shadow,
)


def test_shadow_proxy_is_pure_and_requires_supported_samples():
    rgb = np.zeros((48, 64, 3))
    rgb[:] = [.8, .6, .4]
    rgb *= np.linspace(.65, 1., 64)[None, :, None]
    fg = np.ones((48, 64), dtype=bool)
    face = np.zeros_like(fg)
    face[8:24, 24:48] = True
    before = rgb.copy()
    field, materials = shadow_field(rgb, fg, [face])
    np.testing.assert_array_equal(before, rgb)
    assert field.shape == fg.shape and np.isfinite(field).all()
    assert np.all((field >= 0) & (field <= 1))
    assert not np.any(materials['skin'] & materials['light'])
    assert field.max() > .01
    with pytest.raises(ValueError, match='unavailable'):
        shadow_field(rgb, fg, [np.zeros_like(fg)])


def test_shadow_shapes_retain_hole_and_ignore_background():
    yy, xx = np.mgrid[:64, :64]
    ring = ((xx-32)**2+(yy-32)**2 < 24**2) & ((xx-32)**2+(yy-32)**2 > 10**2)
    fg = np.ones_like(ring)
    fg[:, :4] = False
    field = ring.astype(float)
    field[:, :4] = 1.
    groups, mask = shapes(field, fg, 1., 10, 8, .5)
    assert len(groups) == 1 and len(groups[0][1]) == 2
    assert not mask[32, 32] and not mask[:, :4].any()
    assert mask[32, 48]
    assert all(Polygon(q).is_valid for _, loops in groups for q in loops)


def test_flow_hatch_is_deterministic_and_stays_in_components():
    mask = np.zeros((60, 70), dtype=bool)
    mask[3:57, 3:32] = True
    mask[3:57, 38:67] = True
    normals = np.zeros((60, 70, 3))
    a, b = flow_hatch(mask, normals, 5), flow_hatch(mask, normals, 5)
    assert a and len(a) == len(b)
    for p, q in zip(a, b):
        np.testing.assert_array_equal(p, q)
        assert np.isfinite(p).all()
        xy = np.rint(p).astype(int)
        # Mask cells are centered at integer pixels, matching the tracer.
        assert np.all(xy[:, 0] < 32) or np.all(xy[:, 0] >= 38)
        assert mask[xy[:, 1], xy[:, 0]].all()
    assert flow_hatch(np.zeros_like(mask), normals) == []


def test_clearance_splits_without_moving_retained_segments():
    line = LineString([(0, 5), (20, 5)])
    protected = LineString([(10, 0), (10, 10)])
    out = clear_hatching([line], [protected], 1)
    assert len(out) == 2 and sum(x.length for x in out) < line.length
    assert all(x.difference(line).is_empty for x in out)
    assert all(x.distance(protected) >= 1.5-1e-9 for x in out)
    assert list(line.coords) == [(0, 5), (20, 5)]


def test_shadow_cut_is_a_real_hole_and_stays_inside_edit_region():
    mass = box(0, 0, 20, 20)
    feature = LineString([(5, 10), (15, 10)])
    edit = box(3, 3, 17, 17)
    result, removed = cut_shadow(mass, [feature], edit, 2.)
    assert result.is_valid and len(result.interiors) == 1
    assert result.union(removed).equals(mass)
    assert removed.difference(edit).is_empty
    assert result.difference(edit).equals(mass.difference(edit))
    assert mass.area == 400


def test_curve_fit_outputs_finite_sampled_geometry():
    x = np.linspace(0, 30, 31)
    p = np.column_stack((x, np.sin(x/8)*3))
    d, fitted = fit(p, .5)
    assert d.startswith('M') and 'C' in d
    assert np.isfinite(fitted).all()
    np.testing.assert_allclose(fitted[[0, -1]], p[[0, -1]], atol=1e-8)
