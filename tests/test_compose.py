"""Compositor tests: the resolve invariant, occlusion semantics, effects,
pen-offset compensation, and project persistence."""

import pytest

from axibridge.compose import Affine
from axibridge.session import session
from axibridge.stores import Pen, pen_library, settings_store


def total_len(paths):
    return sum(p.length() for p in paths)


@pytest.fixture()
def liss_under_hexagon():
    """A lissajous with a filled hexagon occluder centred on top of it."""
    liss = session.add_generated_layer("lissajous", {"size": 100, "margin": 5})
    hexa = session.add_generated_layer("polygon", {"sides": 6, "radius": 25, "filled": True})
    session.update_layer(hexa.id, {
        "transform": Affine(e=30, f=30).model_dump(),
        "occluder": True,
    })
    return liss, hexa


def test_occlusion_clips(liss_under_hexagon):
    liss, hexa = liss_under_hexagon
    res = session.resolved()
    assert len(res[liss.id]) > 1, "occluder must cut the curve into pieces"
    assert total_len(res[liss.id]) < total_len(session.source_geometry[liss.id])
    # the occluder itself is drawn whole
    assert len(res[hexa.id]) >= 1


def test_receives_occlusion_exempts(liss_under_hexagon):
    liss, _ = liss_under_hexagon
    session.update_layer(liss.id, {"receives_occlusion": False})
    res = session.resolved()
    assert len(res[liss.id]) == 1


def test_signed_margin(liss_under_hexagon):
    liss, hexa = liss_under_hexagon
    session.update_layer(hexa.id, {"occlusion_margin_mm": -1.5})
    kept_bleed = total_len(session.resolved()[liss.id])
    session.update_layer(hexa.id, {"occlusion_margin_mm": 3.0})
    kept_gap = total_len(session.resolved()[liss.id])
    assert kept_bleed > kept_gap, "negative margin must remove less than positive"


def test_hidden_layer_neither_draws_nor_masks(liss_under_hexagon):
    liss, hexa = liss_under_hexagon
    session.update_layer(hexa.id, {"visible": False})
    res = session.resolved()
    assert hexa.id not in res
    assert len(res[liss.id]) == 1, "hidden occluder must not mask"


def test_z_order_governs_masking(liss_under_hexagon):
    liss, hexa = liss_under_hexagon
    # move the occluder BELOW the curve: it may no longer mask it
    session.reorder_layers([hexa.id, liss.id])
    res = session.resolved()
    assert len(res[liss.id]) == 1


def test_effect_paper_space_and_seed_stability():
    layer = session.add_generated_layer("polygon", {"sides": 4, "radius": 20, "filled": True})
    session.update_layer(layer.id, {
        "effects": [{"effect": "coherent_jitter", "enabled": True,
                     "params": {"amplitude": 1.0, "seed": 3}}],
    })
    a = session.resolved()[layer.id]
    b = session.resolved()[layer.id]
    assert a == b, "same seed + same layer => identical resolve"
    # layer-anchored noise: translating the layer translates the wobble with it
    session.update_layer(layer.id, {"transform": Affine(e=50, f=0).model_dump()})
    c = session.resolved()[layer.id]
    moved = [(x - 50, y) for x, y in c[0].points]
    orig = a[0].points
    assert all(abs(mx - ox) < 1e-6 and abs(my - oy) < 1e-6
               for (mx, my), (ox, oy) in zip(moved, orig))
    # closure preserved for the mask
    assert c[0].points[0] == c[0].points[-1]


def test_transform_then_effects_keeps_mm_amplitude():
    """Scaling a layer must NOT scale its jitter amplitude (paper-space):
    displacement off the ideal outline stays ≈ amplitude at any layer scale."""
    from shapely.geometry import LineString, Point as ShPoint

    layer = session.add_generated_layer("polygon", {"sides": 4, "radius": 20})
    fx = [{"effect": "coherent_jitter", "enabled": True,
           "params": {"amplitude": 2.0, "seed": 1, "step": 1.0, "wavelength": 10}}]

    def max_disp(scale):
        session.update_layer(layer.id, {
            "transform": Affine(a=scale, d=scale).model_dump(), "effects": [],
        })
        outline = LineString(session.resolved()[layer.id][0].points)
        session.update_layer(layer.id, {"effects": fx})
        wobbled = session.resolved()[layer.id][0].points
        return max(outline.distance(ShPoint(p)) for p in wobbled)

    d1 = max_disp(1.0)
    d3 = max_disp(3.0)
    assert d1 <= 2.2, f"displacement {d1:.2f} should be bounded by the 2mm amplitude"
    assert d3 <= 2.2, f"at 3x scale displacement {d3:.2f} must STILL be ~2mm, not ~6mm"


def test_pen_offset_compensation():
    layer = session.add_generated_layer("polygon", {"sides": 4, "radius": 10})
    pen = pen_library.upsert(Pen(name="test pen", barrel_diameter_mm=12.0))
    session.update_layer(layer.id, {"pen_id": pen.id})
    settings_store.update({"holder_calibration": {"dx_per_mm": 0.1, "dy_per_mm": -0.05}})
    plain = session.resolved_document(layer.id).layers[0].paths[0].points[0]
    comp = session.plot_document(layer.id).layers[0].paths[0].points[0]
    assert comp[0] - plain[0] == pytest.approx(-1.2)   # −0.1 × 12
    assert comp[1] - plain[1] == pytest.approx(0.6)    # +0.05 × 12
    # zero vector disables compensation entirely
    settings_store.update({"holder_calibration": {"dx_per_mm": 0, "dy_per_mm": 0}})
    again = session.plot_document(layer.id).layers[0].paths[0].points[0]
    assert again == pytest.approx(plain)


def test_pen_height_overrides_apply_per_layer():
    layer = session.add_generated_layer("polygon", {"sides": 3, "radius": 10})
    pen = pen_library.upsert(Pen(name="marker", pen_pos_down=33, pen_pos_up=77))
    session.update_layer(layer.id, {"pen_id": pen.id})
    single = session.effective_params("simulator", layer.id)
    assert single.pen_pos_down == 33 and single.pen_pos_up == 77
    everything = session.effective_params("simulator", "all")
    assert everything.pen_pos_down != 33  # overrides are per-layer-pass only


def test_project_save_load_identical_resolve(tmp_path):
    from pathlib import Path as FsPath

    from axibridge import project_io

    liss = session.add_generated_layer("lissajous", {"size": 80})
    hexa = session.add_generated_layer("polygon", {"sides": 6, "radius": 20, "filled": True})
    session.update_layer(hexa.id, {
        "transform": Affine(e=25, f=25).model_dump(),
        "occluder": True, "occlusion_margin_mm": 1.0,
        "effects": [{"effect": "coherent_jitter", "enabled": True, "params": {"seed": 9}}],
    })
    before = session.resolved()

    target = FsPath(tmp_path) / "proj"
    project_io.save_project(session.project, session.source_geometry, session.svg_files, target)
    assert (target / "project.json").exists()
    assert (target / f"sources/gen-{liss.id}.svg").exists()

    project, geometry, _, _ = project_io.load_project(target)
    session.project = project
    session.source_geometry = geometry
    session._shaped_cache.clear()
    after = session.resolved()

    for lid in (liss.id, hexa.id):
        assert len(before[lid]) == len(after[lid])
        for pa, pb in zip(before[lid], after[lid]):
            assert pa.filled == pb.filled
            assert len(pa.points) == len(pb.points)
            for (ax, ay), (bx, by) in zip(pa.points, pb.points):
                assert ax == pytest.approx(bx, abs=1e-3)
                assert ay == pytest.approx(by, abs=1e-3)


def test_zip_roundtrip(tmp_path):
    from pathlib import Path as FsPath

    from axibridge import project_io

    session.add_generated_layer("polygon", {"sides": 5, "radius": 15})
    src = FsPath(tmp_path) / "src"
    project_io.save_project(session.project, session.source_geometry, session.svg_files, src)
    blob = project_io.export_zip(src)
    out = project_io.import_zip(blob, FsPath(tmp_path) / "root", "copy")
    project, geometry, _, _ = project_io.load_project(out)
    assert len(project.layers) == 1
    assert geometry[project.layers[0].id]
