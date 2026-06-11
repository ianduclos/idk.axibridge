"""Undo history, consolidate (bake), bulk delete, and the depth-map effect."""

import io

import pytest

from axibridge.assets import asset_store
from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect
from axibridge.session import session


def test_undo_restores_deleted_layer():
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 20})
    before = session.resolved()[layer.id]
    session.delete_layer(layer.id)
    assert layer.id not in {l.id for l in session.project.layers}
    assert session.undo()
    assert layer.id in {l.id for l in session.project.layers}
    after = session.resolved()[layer.id]
    assert [p.points for p in before] == [p.points for p in after]


def test_undo_depth_is_eight():
    layer = session.add_generated_layer("polygon", {})
    session.clear_history()
    for i in range(12):
        session.update_layer(layer.id, {"name": f"n{i}"})
    undone = 0
    while session.undo():
        undone += 1
    assert undone == 8
    assert session.project.layer(layer.id).name == "n3"  # 12 edits, last 8 undone


def test_bulk_delete_is_one_undo_step():
    a = session.add_generated_layer("polygon", {})
    b = session.add_generated_layer("polygon", {})
    session.clear_history()
    session.delete_layers([a.id, b.id])
    assert not session.project.layers
    assert session.undo()
    assert {l.id for l in session.project.layers} == {a.id, b.id}
    assert not session.undo()  # exactly one step


def test_consolidate_bakes_without_changing_resolved():
    layer = session.add_generated_layer("polygon", {"sides": 5, "radius": 18})
    session.update_layer(layer.id, {
        "transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 40, "f": 25},
        "effects": [{"effect": "coherent_jitter", "params": {"amplitude": 1.5, "seed": 3}}],
    })
    before = session.resolved()[layer.id]
    baked = session.consolidate_effects(layer.id)
    assert baked.source.type == "baked"
    assert baked.effects == [] and baked.transform.e == 0
    after = session.resolved()[layer.id]
    assert [p.points for p in before] == [p.points for p in after]
    # regenerate returns to live generator output (un-jittered, un-moved)
    regen = session.regenerate_layer(layer.id)
    assert regen.source.type == "generator"
    assert session.resolved()[layer.id] != after


def _png_gradient() -> bytes:
    """8x8 horizontal black→white gradient."""
    from PIL import Image

    img = Image.new("L", (8, 8))
    img.putdata([min(x * 36, 255) for _ in range(8) for x in range(8)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_depth_displace_moves_by_brightness():
    asset_store.replace_all({})
    name = asset_store.put("ramp.png", _png_gradient())
    eff = get_effect("depth_displace")
    # horizontal line across a map placed at x∈[0,80]: white end pushes down
    line = Path(points=[(0.0, 40.0), (80.0, 40.0)])
    params = eff.Params(image=name, x=0, y=0, width=80, amplitude=10, angle_deg=90, step=2)
    [out] = eff.apply([line], params, EffectContext())
    ys = [y for _, y in out.points]
    assert ys[0] < 40.0 + 1  # dark end ≈ neutral-or-up
    assert max(ys) > 45.0    # bright end pushed down hard
    assert ys[-1] > ys[0]    # monotone-ish along the gradient
    # outside the map: neutral
    far = Path(points=[(300.0, 40.0), (320.0, 40.0)])
    [unmoved] = eff.apply([far], params, EffectContext())
    assert all(y == pytest.approx(40.0) for _, y in unmoved.points)


def test_depth_displace_without_image_passes_through():
    eff = get_effect("depth_displace")
    line = Path(points=[(0.0, 0.0), (10.0, 0.0)])
    assert eff.apply([line], eff.Params(), EffectContext()) == [line]


def test_depth_displace_normal_mode_affects_parallel_lines():
    asset_store.replace_all({})
    name = asset_store.put("ramp.png", _png_gradient())
    eff = get_effect("depth_displace")
    # a line running ALONG the fixed displacement direction barely changes
    # shape; in normal mode it bows sideways instead
    vline = Path(points=[(40.0, 0.0), (40.0, 80.0)])
    fixed = eff.Params(image=name, x=0, y=0, width=80, amplitude=10,
                       angle_deg=90, direction="fixed angle", step=2, smoothing=0)
    norm = fixed.model_copy(update={"direction": "path normal"})
    [out_f] = eff.apply([vline], fixed, EffectContext())
    [out_n] = eff.apply([vline], norm, EffectContext())
    assert all(x == pytest.approx(40.0) for x, _ in out_f.points)   # invisible
    assert max(abs(x - 40.0) for x, _ in out_n.points) > 3.0        # visible bow


def test_depth_displace_bias_pulls_dark_back():
    asset_store.replace_all({})
    name = asset_store.put("ramp.png", _png_gradient())
    eff = get_effect("depth_displace")
    line = Path(points=[(0.0, 40.0), (80.0, 40.0)])
    p = eff.Params(image=name, x=0, y=0, width=80, amplitude=10,
                   bias=0.5, angle_deg=90, step=2, smoothing=0)
    [out] = eff.apply([line], p, EffectContext())
    ys = [y for _, y in out.points]
    assert min(ys) < 39.0 and max(ys) > 41.0  # signed around mid-gray


def test_image_threshold_traces_closed_filled_outlines():
    from axibridge.registry import get_source

    asset_store.replace_all({})
    name = asset_store.put("ramp.png", _png_gradient())
    src = get_source("image_threshold")
    doc = src.generate(src.Params(image=name, width=80, threshold=0.5,
                                  smoothing=0, detail=1.0, min_area=4))
    paths = doc.layers[0].paths
    assert len(paths) == 1  # the dark left half, closed along the image edge
    p = paths[0]
    assert p.filled and p.points[0] == p.points[-1]
    xs = [x for x, _ in p.points]
    assert max(xs) < 45  # the 0.5-brightness boundary sits near x = 80*(127/255/0.18)... mid-left
    assert min(xs) >= -1.5  # closes just outside the left edge (padding ring)


def test_image_threshold_respects_alpha():
    import io as _io

    from PIL import Image

    from axibridge.registry import get_source

    # all-black image, right half transparent -> only the left half traces
    img = Image.new("LA", (8, 8), (0, 255))
    for y in range(8):
        for x in range(4, 8):
            img.putpixel((x, y), (0, 0))
    buf = _io.BytesIO(); img.save(buf, "PNG")
    asset_store.replace_all({})
    name = asset_store.put("mask.png", buf.getvalue())
    src = get_source("image_threshold")
    doc = src.generate(src.Params(image=name, width=80, smoothing=0, detail=1.0, min_area=4))
    [p] = doc.layers[0].paths
    assert max(x for x, _ in p.points) < 50  # transparent right half excluded


def test_image_threshold_requires_image():
    from axibridge.registry import get_source

    with pytest.raises(ValueError):
        get_source("image_threshold").generate(get_source("image_threshold").Params())


def test_depth_displace_background_and_crop():
    asset_store.replace_all({})
    name = asset_store.put("ramp.png", _png_gradient())
    eff = get_effect("depth_displace")
    line = Path(points=[(-20.0, 40.0), (100.0, 40.0)])  # extends past the 0..80 map
    # background depth: off-map treated as brightness 1 -> displaced like white
    p_bg = eff.Params(image=name, x=0, y=0, width=80, amplitude=10, background=1.0,
                      angle_deg=90, step=2, smoothing=0)
    [out] = eff.apply([line], p_bg, EffectContext())
    assert out.points[0][1] == pytest.approx(50.0)  # off-map start pushed by full depth
    # crop: off-map points dropped, path split away from the overhang
    p_crop = p_bg.model_copy(update={"crop": "outside map"})
    pieces = eff.apply([line], p_crop, EffectContext())
    assert all(0 <= x <= 80 for piece in pieces for x, _ in piece.points)


def test_duplicate_layer():
    layer = session.add_generated_layer("polygon", {"sides": 3, "radius": 10})
    copy = session.duplicate_layer(layer.id)
    assert copy.id != layer.id and copy.name == f"{layer.name} copy"
    ids = [l.id for l in session.project.layers]
    assert ids.index(copy.id) == ids.index(layer.id) + 1
    r = session.resolved()
    assert [p.points for p in r[layer.id]] == [p.points for p in r[copy.id]]
    assert session.undo()
    assert copy.id not in {l.id for l in session.project.layers}
