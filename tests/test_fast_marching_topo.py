"""Fast Marching Topo engine and image-source integration."""

from __future__ import annotations

import io

import numpy as np
import pytest

from axibridge.assets import asset_store
from axibridge.registry import get_source, progress_scope
from axibridge.sources import _fast_marching as fmm
from axibridge.sources import _pixelgen


def test_travel_time_uniform_field_is_symmetric_and_cardinally_exact():
    times = fmm.travel_time(np.ones((9, 9)), 4, 4)
    assert times[4, 4] == 0.0
    assert times[4, 7] == pytest.approx(3.0)
    assert np.array_equal(times, times[::-1, :])
    assert np.array_equal(times, times[:, ::-1])
    # The first-order grid solve approaches Euclidean distance and must stay
    # strictly below Manhattan distance away from a cardinal axis.
    assert np.hypot(3, 3) < times[7, 7] < 6.0


def test_travel_time_slow_region_compresses_equal_time_levels():
    speed = np.ones((41, 81))
    speed[:, :40] = 0.2
    times = fmm.travel_time(speed, 40, 20)
    # One pixel through the dark/slow half consumes about five times as much
    # travel time, so evenly spaced iso-times land about five times closer.
    slow_step = np.mean(np.diff(times[20, 10:30]))
    fast_step = np.mean(np.diff(times[20, 50:70]))
    assert abs(slow_step) > abs(fast_step) * 4.5


def test_travel_time_clamps_seed_and_leaves_zero_speed_unreachable():
    speed = np.ones((5, 6))
    speed[:, 3] = 0.0
    times = fmm.travel_time(speed, -20, 99)
    assert times[4, 0] == 0.0
    assert np.isfinite(times[:, :3]).all()
    assert np.isinf(times[:, 3:]).all()


def test_iso_contours_are_deterministic_closed_inside_and_report_progress():
    times = fmm.travel_time(np.ones((31, 31)), 15, 15)
    seen: list[float] = []
    first = fmm.iso_contours(times, 8, seen.append)
    second = fmm.iso_contours(times, 8)
    assert first == second
    assert first
    assert any(line[0] == line[-1] for line in first)
    assert all(len(line) >= 2 for line in first)
    assert seen == sorted(seen) and seen[-1] == 1.0


def test_alpha_clipping_splits_lines_and_preserves_opaque_closed_ring():
    alpha = np.ones((6, 8))
    alpha[:, 4:] = 0.0
    crossing = [[(0.0, 2.0), (2.0, 2.0), (4.0, 2.0), (6.0, 2.0)]]
    assert fmm.clip_to_alpha(crossing, alpha) == [[(0.0, 2.0), (2.0, 2.0)]]

    alpha[:] = 1.0
    ring = [[(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 1.0)]]
    assert fmm.clip_to_alpha(ring, alpha) == ring


@pytest.fixture(autouse=True)
def small_working_canvas(monkeypatch):
    monkeypatch.setattr(_pixelgen, "WORK_W", 72)
    monkeypatch.setattr(_pixelgen, "MAX_H", 144)


@pytest.fixture(autouse=True)
def image_assets():
    from PIL import Image

    gradient = Image.new("L", (72, 48))
    gradient.putdata([
        round(255 * (x / 71))
        for _y in range(48)
        for x in range(72)
    ])
    grad_buf = io.BytesIO()
    gradient.save(grad_buf, "PNG")

    rgba = Image.new("RGBA", (72, 48), (100, 100, 100, 255))
    rgba.putdata([
        (100, 100, 100, 255 if x < 36 else 0)
        for _y in range(48)
        for x in range(72)
    ])
    alpha_buf = io.BytesIO()
    rgba.save(alpha_buf, "PNG")

    before = asset_store.all()
    asset_store.put("fmm-gradient.png", grad_buf.getvalue())
    asset_store.put("fmm-alpha.png", alpha_buf.getvalue())
    yield
    asset_store.replace_all(before)


def _generate(image="fmm-gradient.png", **params):
    source = get_source("fast_marching_topo")
    values = dict(
        image=image,
        width=120,
        line_count=24,
        resolution=1.0,
    )
    values.update(params)
    return source.generate(source.Params(**values))


def _points(doc):
    return [path.points for path in doc.layers[0].paths]


def test_generator_is_deterministic_in_bounds_and_stroke_only():
    first = _generate()
    second = _generate()
    assert _points(first) == _points(second)
    assert first.layers[0].paths
    assert first.width == 120
    assert first.height == pytest.approx(80)
    assert all(not path.filled for path in first.layers[0].paths)
    assert all(
        0.0 <= x <= first.width and 0.0 <= y <= first.height
        for path in first.layers[0].paths
        for x, y in path.points
    )


def test_generator_seed_and_invert_change_geometry():
    centered = _generate(seed_x=0.5, seed_y=0.5)
    moved = _generate(seed_x=0.15, seed_y=0.8)
    inverted = _generate(invert=True)
    assert _points(centered) != _points(moved)
    assert _points(centered) != _points(inverted)


def test_generator_clips_resampled_alpha_by_default():
    clipped = _generate("fmm-alpha.png")
    unclipped = _generate("fmm-alpha.png", clip_transparent=False)
    clipped_x = [x for path in clipped.layers[0].paths for x, _ in path.points]
    unclipped_x = [x for path in unclipped.layers[0].paths for x, _ in path.points]
    assert clipped_x and max(clipped_x) < 65.0
    assert max(unclipped_x) > 100.0


def test_generator_requires_an_existing_image():
    source = get_source("fast_marching_topo")
    with pytest.raises(ValueError, match="upload an image"):
        source.generate(source.Params(image=""))
    with pytest.raises(ValueError, match="no asset named"):
        source.generate(source.Params(image="missing.png"))


def test_generator_schema_is_bounded_grouped_and_orientation_ready():
    source = get_source("fast_marching_topo")
    props = source.Params.model_json_schema()["properties"]
    assert source.orientation == "param"
    assert props["image"]["format"] == "asset"
    assert props["rotate"]["viewRotate"] is True
    assert props["resolution"]["minimum"] == 0.25
    assert props["resolution"]["maximum"] == 2.0
    assert props["line_count"]["group"] == "Computation"
    assert props["gamma"]["group"] == "Image processing"


def test_generator_progress_is_monotonic_across_stages():
    seen: list[tuple[float, str]] = []
    with progress_scope(lambda frac, msg="": seen.append((frac, msg))):
        _generate(line_count=10)
    fractions = [frac for frac, _ in seen]
    assert fractions == sorted(fractions)
    assert fractions[0] >= 0.0 and fractions[-1] >= 0.99
    assert {msg for _, msg in seen} >= {"Fast marching", "Tracing contours"}
