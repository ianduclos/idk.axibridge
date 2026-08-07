"""Round-1 urgent fixes:

1. image-based generator output is centred on the bed instead of pinned at
   the machine origin (``Session.add_generated_layer`` / ``add_lineart_stack``).
2. ``image_threshold`` gets a min/max threshold BAND instead of a single
   one-sided cutoff (see tests/test_plotterfun.py for the band-specific
   generator tests — this file covers the session-level centering fix).
3. ``linedraw`` (v1) gets the same ``resolution`` knob as lineart v2's
   ``lineart_edges`` (see tests/test_lineart.py for that generator test).

Kept fast: a tiny synthetic asset, working resolution patched down, same
pattern as test_plotterfun.py / test_lineart.py.
"""

from __future__ import annotations

import io

import pytest

from axibridge.assets import asset_store
from axibridge.compose import BED_HEIGHT, BED_WIDTH
from axibridge.session import session
from axibridge.sources import _pixelgen


@pytest.fixture(autouse=True)
def small_working_canvas(monkeypatch):
    """Generators resample to WORK_W px wide; shrink it so tests stay fast
    (same pattern as test_plotterfun.py)."""
    monkeypatch.setattr(_pixelgen, "WORK_W", 80)
    monkeypatch.setattr(_pixelgen, "MAX_H", 160)


@pytest.fixture(autouse=True)
def gradient_asset():
    """Left-to-right white->black gradient, same construction as
    test_plotterfun.py's fixture."""
    from PIL import Image

    img = Image.new("L", (64, 48))
    img.putdata([255 - int(255 * (i % 64) / 64) for i in range(64 * 48)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    before = asset_store.all()
    asset_store.put("grad.png", buf.getvalue())
    yield
    asset_store.replace_all(before)


# -- Fix 1: centre image-based generator output on the bed -------------------


def test_add_generated_layer_centers_image_generator():
    """A fresh image_threshold layer lands centred on the bed, not pinned at
    the machine origin — transform.e/f follow (BED - doc_size)/2 exactly."""
    layer = session.add_generated_layer(
        "image_threshold", {"image": "grad.png", "width": 80, "detail": 1.0})
    doc = session.resolved()  # sanity: the layer actually has geometry
    assert doc[layer.id]
    doc_w = 80.0
    doc_h = 80.0 * 48 / 64  # aspect preserved, same math as pixel_doc/image_threshold
    assert layer.transform.e == pytest.approx((BED_WIDTH - doc_w) / 2)
    assert layer.transform.f == pytest.approx((BED_HEIGHT - doc_h) / 2)
    assert layer.transform.a == 1.0 and layer.transform.d == 1.0  # no scale/shear added


def test_add_generated_layer_plotterfun_generator_centers_too():
    """Not just image_threshold — any generator whose params expose an
    ``image`` field (the plotterfun/_pixelgen family, e.g. linedraw) gets
    the same treatment."""
    layer = session.add_generated_layer("linedraw", {"image": "grad.png", "width": 60})
    assert layer.transform.e == pytest.approx((BED_WIDTH - 60.0) / 2)
    assert layer.transform.f != 0.0 or layer.transform.e != 0.0


def test_add_generated_layer_non_image_generator_keeps_identity():
    """Procedural generators (no ``image`` param) are NOT re-centred — they
    place themselves via their own size/margin params, and existing tooling
    (compose/tween/sheet tests) depends on that identity transform.

    Checked in landscape, where nothing else touches the transform. In
    portrait a source declaring ``orientation = "geometry"`` also carries the
    quarter-turn — see tests/test_orientation.py."""
    session.project.view = "landscape"
    layer = session.add_generated_layer("rectangle", {"width": 40, "height": 20})
    assert layer.transform.e == 0.0
    assert layer.transform.f == 0.0

    layer2 = session.add_generated_layer("polygon", {"sides": 6, "radius": 10})
    assert layer2.transform.e == 0.0
    assert layer2.transform.f == 0.0

    # a source with no dominant axis stays at identity in portrait too
    session.project.view = "portrait"
    layer3 = session.add_generated_layer("polygon", {"sides": 6, "radius": 10})
    assert (layer3.transform.e, layer3.transform.f) == (0.0, 0.0)
    assert (layer3.transform.a, layer3.transform.d) == (1.0, 1.0)


def test_regenerate_layer_preserves_existing_transform():
    """regenerate_layer must NOT re-apply centering — an already-placed
    layer's transform (user-dragged or auto-centred at creation) survives a
    regenerate untouched."""
    layer = session.add_generated_layer(
        "image_threshold", {"image": "grad.png", "width": 80, "detail": 1.0})
    session.update_layer(layer.id, {"transform": {"a": 1, "b": 0, "c": 0, "d": 1,
                                                   "e": 12.5, "f": -3.0}})
    session.regenerate_layer(layer.id)
    after = session.project.layer(layer.id)
    assert after.transform.e == 12.5
    assert after.transform.f == -3.0


def test_lineart_stack_bands_share_identical_centering():
    """add_lineart_stack's bands all use the same image/rotate/width, so
    their PathDocuments share width/height — every band must land with the
    IDENTICAL centering transform (session-level check; the geometry-level
    version of this lives in test_lineart.py alongside the rest of the
    stack tests)."""
    layers = session.add_lineart_stack("grad.png", "faithful")
    assert len(layers) == 4
    coords = {(l.transform.e, l.transform.f) for l in layers}
    assert len(coords) == 1
    e, f = next(iter(coords))
    assert (e, f) != (0.0, 0.0)


def test_lineart_stack_on_sequence_keeps_identity():
    """Clip-backed stacks (sequence images) are spatial-ladder material —
    left at identity like any other sequence-driven generator layer, not
    auto-centred."""
    before = asset_store.all()
    from PIL import Image

    for i in range(2):
        img = Image.new("L", (64, 48))
        img.putdata([255 - int(255 * ((x % 64) / 64)) for x in range(64 * 48)])
        buf = io.BytesIO()
        img.save(buf, "PNG")
        asset_store.put(f"seq2#{i:04d}.png", buf.getvalue())
    try:
        layers = session.add_lineart_stack("seq2#", "artistic")
        for l in layers:
            assert l.transform.e == 0.0 and l.transform.f == 0.0
    finally:
        asset_store.replace_all(before)
