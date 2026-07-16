"""Misremembered image source: contract (determinism, bounds, budget dial)."""

import io

import pytest

from axibridge.assets import asset_store
from axibridge.registry import get_source
from axibridge.sources import _pixelgen


@pytest.fixture(autouse=True)
def small_working_canvas(monkeypatch):
    monkeypatch.setattr(_pixelgen, "WORK_W", 120)
    monkeypatch.setattr(_pixelgen, "MAX_H", 240)


@pytest.fixture(autouse=True)
def scene_asset():
    """A dark disc on light ground: one mass, one clean circular edge."""
    from PIL import Image, ImageDraw

    img = Image.new("L", (96, 96), 230)
    ImageDraw.Draw(img).ellipse([20, 20, 76, 76], fill=35)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    before = asset_store.all()
    asset_store.put("disc.png", buf.getvalue())
    yield
    asset_store.replace_all(before)


def _gen(**params):
    src = get_source("misremembered")
    return src.generate(src.Params(image="disc.png", **params))


def test_registered_and_generates():
    doc = _gen(budget=60, width=100)
    paths = doc.layers[0].paths
    assert paths
    assert all(len(p.points) >= 2 for p in paths)


def test_deterministic_per_params():
    a = _gen(budget=60, width=100, seed=3)
    b = _gen(budget=60, width=100, seed=3)
    assert [p.points for p in a.layers[0].paths] == [p.points for p in b.layers[0].paths]


def test_seed_varies_marks():
    a = _gen(budget=60, width=100, seed=1)
    b = _gen(budget=60, width=100, seed=2)
    assert [p.points for p in a.layers[0].paths] != [p.points for p in b.layers[0].paths]


def test_coordinates_mm_nonnegative_and_bounded():
    doc = _gen(budget=60, width=100)
    for p in doc.layers[0].paths:
        for x, y in p.points:
            assert x >= 0 and y >= 0
            # confabulation may wander a little past the frame, never wildly
            assert x < doc.width + 15 and y < doc.height + 15


def test_budget_is_the_dial():
    sparse = _gen(budget=10, width=100)
    dense = _gen(budget=300, width=100)
    n_sparse = len(sparse.layers[0].paths)
    n_dense = len(dense.layers[0].paths)
    assert n_sparse <= 12  # low budget stays a sketch (fragments may split marks)
    assert n_dense > n_sparse


def test_dark_mass_is_scrubbed_by_default():
    doc = _gen(budget=60, width=100)
    # the disc is remembered as at least one long continuous scribble, not a fill
    longest = max(doc.layers[0].paths, key=lambda p: len(p.points))
    assert not longest.filled
    assert len(longest.points) > 40


def test_blob_style_keeps_v1_contract():
    doc = _gen(budget=60, width=100, mass_style="blob", tone=0.0)
    blobs = [p for p in doc.layers[0].paths if p.filled]
    assert blobs, "the dark disc should be remembered as at least one mass"
    for b in blobs:
        assert b.points[0] == b.points[-1]  # closed — occlusion masks need it


def test_tone_dial_changes_recall():
    a = _gen(budget=80, width=100, tone=0.0)
    b = _gen(budget=80, width=100, tone=0.8)
    assert [p.points for p in a.layers[0].paths] != [p.points for p in b.layers[0].paths]


def test_missing_asset_raises_helpfully():
    src = get_source("misremembered")
    with pytest.raises(ValueError):
        src.generate(src.Params(image="", budget=40))
    with pytest.raises(ValueError):
        src.generate(src.Params(image="nope.png", budget=40))
