"""Fast Marching Contours: edge-seeded travel time, per-level extraction,
boundary threading, and the image-source integration."""

from __future__ import annotations

import io
import statistics

import numpy as np
import pytest

from axibridge.assets import asset_store
from axibridge.registry import get_source, progress_scope, sources
from axibridge.sources import _fast_marching as fmm
from axibridge.sources import _fm_threading as fmt
from axibridge.sources import _pixelgen


# -- engine: multi-seed travel time ---------------------------------------


def test_travel_time_multi_single_seed_matches_travel_time():
    speed = np.random.default_rng(0).uniform(0.2, 1.0, size=(15, 21))
    single = fmm.travel_time(speed, 6, 9)
    multi = fmm.travel_time_multi(speed, [(6, 9)])
    assert np.array_equal(single, multi)


def test_travel_time_multi_edge_seed_is_a_flat_front_on_a_uniform_field():
    """Seeding an entire row at once is a genuinely different problem from a
    point seed: on a uniform speed field the front must stay perfectly flat
    (T depends only on row, never on column) instead of forming the
    diamond/circle a single point source produces. This is the regression
    guard for "no diamond/point-source artifact"."""
    h, w = 12, 17
    speed = np.ones((h, w))
    seeds = [(x, 0) for x in range(w)]
    times = fmm.travel_time_multi(speed, seeds)
    expected = np.tile(np.arange(h, dtype=np.float64).reshape(h, 1), (1, w))
    assert np.array_equal(times, expected)


def test_travel_time_multi_dedupes_and_clamps_out_of_range_seeds():
    speed = np.ones((5, 6))
    times = fmm.travel_time_multi(speed, [(-9, -9), (0, 0), (0, 0), (999, 999)])
    assert times[0, 0] == 0.0
    assert np.isfinite(times).all()


# -- engine: optional skfmm acceleration -----------------------------------


def test_solver_name_reports_python_when_use_skfmm_false(monkeypatch):
    monkeypatch.setattr(fmm, "USE_SKFMM", False)
    assert fmm.solver_name() == "python"


def test_skfmm_matches_python_solver_on_a_smooth_field(monkeypatch):
    """skfmm is a different discretization (sub-cell-accurate level-set
    initialization vs our first-order upwind heap solve), so exact agreement
    isn't the bar — see the module docstring for how the constant seed-offset
    was found and corrected. What must hold is that, away from the seed
    edge, the two solvers land close together on a smooth field.

    Deviation is concentrated at the seed row and its immediate neighbour
    (that's exactly where the two solvers' seed-initialization schemes
    differ most): excluding the first two rows, empirical measurement on
    this field gave a max deviation of ~0.27 and a mean of ~0.04 grid-time
    units; the assertions below use roughly 1.5x that as headroom rather
    than the exact measured numbers, so the test isn't brittle to harmless
    floating point/BLAS variation across machines.
    """
    pytest.importorskip("skfmm")
    h, w = 64, 64
    xs = np.linspace(0.0, 1.0, w)
    ys = np.linspace(0.0, 1.0, h)
    x, y = np.meshgrid(xs, ys)
    speed = 0.3 + 0.7 * (0.5 + 0.5 * np.sin(3 * x) * np.cos(2 * y))
    seeds = [(sx, 0) for sx in range(w)]

    monkeypatch.setattr(fmm, "USE_SKFMM", False)
    python_times = fmm.travel_time_multi(speed, seeds)
    monkeypatch.setattr(fmm, "USE_SKFMM", True)
    skfmm_times = fmm.travel_time_multi(speed, seeds)

    assert fmm.solver_name() == "skfmm"
    diff = np.abs(skfmm_times - python_times)[2:, :]  # away from the seed edge
    assert diff.max() < 0.4
    assert diff.mean() < 0.08


def test_skfmm_and_python_agree_a_speed_zero_wall_is_unreachable_in_both(monkeypatch):
    h, w = 20, 20
    speed = np.ones((h, w))
    speed[:, 10] = 0.0  # a wall splitting the grid in two
    seeds = [(2, 2)]  # seed on the near (left) side of the wall

    monkeypatch.setattr(fmm, "USE_SKFMM", False)
    python_times = fmm.travel_time_multi(speed, seeds)
    assert np.isfinite(python_times[:, :10]).all()
    assert np.isinf(python_times[:, 10:]).all()

    pytest.importorskip("skfmm")
    monkeypatch.setattr(fmm, "USE_SKFMM", True)
    skfmm_times = fmm.travel_time_multi(speed, seeds)
    assert np.isfinite(skfmm_times[:, :10]).all()
    assert np.isinf(skfmm_times[:, 10:]).all()


# -- engine: per-level contours --------------------------------------------


def test_iso_contour_levels_flattens_to_iso_contours():
    times = fmm.travel_time(np.ones((25, 31)), 12, 12)
    levels = fmm.iso_contour_levels(times, 10)
    flat = fmm.iso_contours(times, 10)
    assert [line for group in levels for line in group] == flat
    assert len(levels) == 10


def test_iso_contour_levels_reports_progress_monotonically():
    times = fmm.travel_time(np.ones((21, 21)), 10, 10)
    seen: list[float] = []
    fmm.iso_contour_levels(times, 6, seen.append)
    assert seen == sorted(seen)
    assert seen[-1] == pytest.approx(1.0)


# -- engine: boundary threading, hand-built cases --------------------------


def test_thread_boundary_inserts_exact_corner_point_for_a_diagonal_join():
    """A hand-built pair of fragments where the nearest continuation is
    across a corner. Fully deterministic — the connector must be exactly
    the corner point (never a diagonal shortcut) followed by the next
    fragment's own (possibly diagonal) geometry untouched."""
    frag_a = [(0.0, 2.0), (10.0, 2.0)]
    frag_b = [(5.0, 10.0), (0.0, 3.0)]
    result = fmt.thread_boundary(
        [[frag_a], [frag_b]], w=11, h=11, max_join=50.0, tol=0.01, prefer_axis="x",
    )
    assert result == [[(0.0, 2.0), (10.0, 2.0), (10.0, 10.0), (5.0, 10.0), (0.0, 3.0)]]


def test_thread_boundary_closes_trail_when_join_exceeds_max():
    frag_a = [(0.0, 2.0), (10.0, 2.0)]
    frag_b = [(5.0, 10.0), (0.0, 3.0)]
    result = fmt.thread_boundary(
        [[frag_a], [frag_b]], w=11, h=11, max_join=5.0, tol=0.01, prefer_axis="x",
    )
    assert len(result) == 2
    assert result[0] == frag_a
    assert result[1] == [(0.0, 3.0), (5.0, 10.0)]  # reoriented as a new trail start


def test_thread_boundary_passes_closed_rings_through_untouched():
    ring = [(2.0, 2.0), (4.0, 2.0), (4.0, 4.0), (2.0, 2.0)]
    frag = [(0.0, 1.0), (10.0, 1.0)]
    result = fmt.thread_boundary([[ring, frag]], w=11, h=11, max_join=50.0, tol=0.01)
    assert ring in result
    assert len(result) == 2


def test_thread_boundary_passes_through_interior_only_fragments():
    interior = [(3.0, 3.0), (4.0, 4.0)]  # touches neither edge
    result = fmt.thread_boundary([[interior]], w=11, h=11, max_join=50.0, tol=0.01)
    assert result == [interior]


def test_thread_boundary_is_deterministic():
    frag_a = [(0.0, 2.0), (10.0, 2.0)]
    frag_b = [(10.0, 2.5), (0.0, 2.7)]
    first = fmt.thread_boundary([[frag_a], [frag_b]], w=11, h=11, max_join=50.0, tol=0.01)
    second = fmt.thread_boundary([[frag_a], [frag_b]], w=11, h=11, max_join=50.0, tol=0.01)
    assert first == second


# -- engine: boundary threading on real fast-marching output --------------


def test_thread_boundary_collapses_uniform_field_into_one_alternating_trail():
    w, h = 120, 80
    times = fmm.travel_time_multi(np.ones((h, w)), [(x, 0) for x in range(w)])
    levels = fmm.iso_contour_levels(times, 30)
    raw_count = sum(len(group) for group in levels)
    threaded = fmt.thread_boundary(levels, w, h, max_join=30.0, tol=1.5, prefer_axis="x")

    assert raw_count == 30
    assert len(threaded) <= 3  # a handful of trails, not one lift per level

    trail = max(threaded, key=len)
    assert len(trail) > raw_count  # it actually absorbed multiple levels

    # No duplicate consecutive points, everything finite and inside the frame.
    for i in range(1, len(trail)):
        assert trail[i] != trail[i - 1]
    assert all(np.isfinite(x) and np.isfinite(y) for x, y in trail)
    assert all(0.0 <= x <= w - 1 and 0.0 <= y <= h - 1 for x, y in trail)

    # Alternation: collapse consecutive edge-touch runs and check the edge
    # (left x=0 vs right x=w-1) flips every time — the serpentine signature.
    frame_w = w - 1
    touches = [x for x, _y in trail if x == 0.0 or x == float(frame_w)]
    collapsed = [touches[0]]
    for x in touches[1:]:
        if x != collapsed[-1]:
            collapsed.append(x)
    assert len(collapsed) >= 10
    assert all(collapsed[i] != collapsed[i + 1] for i in range(len(collapsed) - 1))


# -- source module: fixtures ------------------------------------------------


@pytest.fixture(autouse=True)
def pin_python_solver(monkeypatch):
    # These tests pin exact geometry against the pure-Python heap solver —
    # that is the tested reference. Force it regardless of whether
    # scikit-fmm happens to be installed in the test environment.
    monkeypatch.setattr(fmm, "USE_SKFMM", False)


@pytest.fixture(autouse=True)
def small_working_canvas(monkeypatch):
    monkeypatch.setattr(_pixelgen, "WORK_W", 72)
    monkeypatch.setattr(_pixelgen, "MAX_H", 144)


def _png_bytes(mode: str, size: tuple[int, int], data) -> bytes:
    from PIL import Image

    img = Image.new(mode, size)
    img.putdata(data)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def image_assets():
    w, h = 72, 48

    uniform = _png_bytes("L", (w, h), [180] * (w * h))

    # Bright top and bottom thirds, dark band across the middle third —
    # front travels top->bottom, so the band should compress contour rows.
    band = []
    for y in range(h):
        v = 40 if h // 3 <= y < 2 * h // 3 else 220
        band.extend([v] * w)
    band_bytes = _png_bytes("L", (w, h), band)

    # Bright field with a dark disk in the middle — should bend contours.
    disk = []
    cx, cy, r = w / 2, h / 2, min(w, h) / 4
    for y in range(h):
        for x in range(w):
            v = 30 if (x - cx) ** 2 + (y - cy) ** 2 <= r * r else 220
            disk.append(v)
    disk_bytes = _png_bytes("L", (w, h), disk)

    # Mid-gray so the opaque and (white-composited) transparent halves have
    # comparable wave speed — otherwise the front barely reaches the
    # transparent half at all and clipping has nothing to prove.
    rgba = []
    for y in range(h):
        for x in range(w):
            rgba.append((150, 150, 150, 255 if x < w // 2 else 0))
    alpha_bytes = _png_bytes("RGBA", (w, h), rgba)

    before = asset_store.all()
    asset_store.put("fmc-uniform.png", uniform)
    asset_store.put("fmc-band.png", band_bytes)
    asset_store.put("fmc-disk.png", disk_bytes)
    asset_store.put("fmc-alpha.png", alpha_bytes)
    yield
    asset_store.replace_all(before)


def _generate(image="fmc-uniform.png", **params):
    source = get_source("fast_marching_contours")
    values = dict(image=image, width=120, line_count=24, resolution=1.0, min_length=0.0)
    values.update(params)
    return source.generate(source.Params(**values))


def _points(doc):
    return [path.points for path in doc.layers[0].paths]


# -- source module: geometry behavior ---------------------------------------


def test_uniform_top_edge_gives_evenly_spaced_near_horizontal_contours():
    doc = _generate(threading="off", line_count=16)
    paths = doc.layers[0].paths
    assert len(paths) >= 10

    means = []
    for path in paths:
        ys = [y for _x, y in path.points]
        spread = max(ys) - min(ys)
        assert spread < doc.height * 0.05  # near-horizontal, no bowing
        means.append(statistics.fmean(ys))

    means.sort()
    spacings = [b - a for a, b in zip(means, means[1:])]
    assert min(spacings) > 0
    assert max(spacings) / min(spacings) < 2.0  # roughly uniform spacing


def test_dark_band_compresses_contours_relative_to_bright_areas():
    doc = _generate("fmc-band.png", threading="off", line_count=40)
    paths = doc.layers[0].paths
    means = sorted(statistics.fmean(y for _x, y in p.points) for p in paths)
    spacings = [b - a for a, b in zip(means, means[1:])]

    band_lo, band_hi = doc.height / 3, 2 * doc.height / 3
    inside = [s for s, m in zip(spacings, means) if band_lo < m < band_hi]
    outside = [s for s, m in zip(spacings, means) if m < band_lo or m > band_hi]
    assert inside and outside
    assert statistics.fmean(inside) < statistics.fmean(outside) * 0.7


def test_dark_disk_bends_a_contour_off_the_straight_line():
    doc = _generate("fmc-disk.png", threading="off", line_count=30)
    paths = doc.layers[0].paths
    spreads = [max(y for _x, y in p.points) - min(y for _x, y in p.points) for p in paths]
    assert max(spreads) > doc.height * 0.1  # a straight front would be near-flat


# -- source module: threading integration ------------------------------------


def test_threading_reduces_path_count_and_paths_stay_open():
    off = _generate(threading="off", line_count=40)
    on = _generate(threading="boundary", line_count=40, max_join=30.0)
    assert len(off.layers[0].paths) == 40
    assert len(on.layers[0].paths) <= 5
    assert all(not p.filled for p in on.layers[0].paths)


def test_threading_off_path_count_matches_level_count_for_uniform_image():
    doc = _generate(threading="off", line_count=24)
    assert len(doc.layers[0].paths) == 24


def test_threading_connectors_are_axis_aligned_and_on_the_frame():
    """Re-derive the working grid the source used and confirm every point
    that isn't part of the natural contour geometry (i.e. every point lying
    exactly on the frame rectangle) only ever moves axis-aligned relative to
    its neighbors — the no-diagonal-through-the-interior guarantee."""
    source = get_source("fast_marching_contours")
    p = source.Params(image="fmc-uniform.png", width=120, line_count=24,
                       resolution=1.0, threading="boundary", min_length=0.0)
    doc = source.generate(p)
    s = p.width / 72  # mm per working px, matches pixel_doc's scale

    # Recompute the actual working grid dims the same way luma_grid does.
    from axibridge.sources._pixelgen import working_dims
    w, h = working_dims(p)
    frame_x_max = (w - 1) * s
    frame_y_max = (h - 1) * s

    def on_frame(pt):
        x, y = pt
        return (
            abs(x) < 1e-6 or abs(x - frame_x_max) < 1e-6
            or abs(y) < 1e-6 or abs(y - frame_y_max) < 1e-6
        )

    for path in doc.layers[0].paths:
        pts = path.points
        for i in range(1, len(pts)):
            a, b = pts[i - 1], pts[i]
            if on_frame(a) and on_frame(b):
                same_x = abs(a[0] - b[0]) < 1e-6
                same_y = abs(a[1] - b[1]) < 1e-6
                assert same_x or same_y, f"non-axis-aligned frame segment {a}->{b}"


# -- source module: determinism, bounds, errors ------------------------------


def test_generator_is_deterministic():
    first = _generate(threading="boundary")
    second = _generate(threading="boundary")
    assert _points(first) == _points(second)


def test_generator_bounds_and_stroke_only():
    doc = _generate(threading="boundary")
    assert doc.layers[0].paths
    assert all(not path.filled for path in doc.layers[0].paths)
    assert all(
        0.0 <= x <= doc.width and 0.0 <= y <= doc.height
        for path in doc.layers[0].paths
        for x, y in path.points
    )
    assert all(
        np.isfinite(x) and np.isfinite(y)
        for path in doc.layers[0].paths
        for x, y in path.points
    )


def test_generator_requires_an_existing_image():
    source = get_source("fast_marching_contours")
    with pytest.raises(ValueError, match="upload an image"):
        source.generate(source.Params(image=""))
    with pytest.raises(ValueError, match="no asset named"):
        source.generate(source.Params(image="missing.png"))


def test_generator_clips_transparent_areas_before_threading():
    # A gentle speed ratio so the front actually reaches the transparent
    # (white-composited) half before any of the 16 levels are exhausted —
    # otherwise clipping would have nothing observable to remove.
    common = dict(image="fmc-alpha.png", line_count=16, max_speed_ratio=3.0, smoothing=0.0)
    clipped = _generate(threading="boundary", **common)
    unclipped = _generate(threading="boundary", clip_transparent=False, **common)
    clipped_x = [x for path in clipped.layers[0].paths for x, _y in path.points]
    unclipped_x = [x for path in unclipped.layers[0].paths for x, _y in path.points]
    assert clipped_x and max(clipped_x) < unclipped.width * 0.6
    assert max(unclipped_x) > unclipped.width * 0.8


# -- source module: registration, schema, progress ---------------------------


def test_generator_is_registered_with_declared_param_orientation():
    source = get_source("fast_marching_contours")
    assert sources()["fast_marching_contours"] is source
    assert source.orientation == "param"
    props = source.Params.model_json_schema()["properties"]
    assert props["rotate"]["viewRotate"] is True


def test_generator_schema_is_bounded_and_grouped():
    source = get_source("fast_marching_contours")
    props = source.Params.model_json_schema()["properties"]
    assert props["image"]["format"] == "asset"
    assert props["line_count"]["minimum"] == 10 and props["line_count"]["maximum"] == 500
    assert props["max_speed_ratio"]["minimum"] == 2 and props["max_speed_ratio"]["maximum"] == 200
    assert props["max_join"]["group"] == "Computation"
    assert props["gamma"]["group"] == "Image processing"
    assert set(props["source_edge"]["enum"]) == {"top", "bottom", "left", "right"}
    assert set(props["threading"]["enum"]) == {"off", "boundary"}


def test_generator_progress_covers_solve_extraction_and_threading():
    seen: list[tuple[float, str]] = []
    with progress_scope(lambda frac, msg="": seen.append((frac, msg))):
        _generate(line_count=12, threading="boundary")
    fractions = [frac for frac, _ in seen]
    assert fractions == sorted(fractions)
    assert fractions[0] >= 0.0 and fractions[-1] >= 0.99
    messages = {msg for _, msg in seen}
    assert "Fast marching" in messages
    assert "Tracing contours" in messages
    assert "Threading" in messages
