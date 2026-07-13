"""Engine-level tests for axibridge/sources/_lineart.py (lineart v2).

Pure numpy-array tests — no assets, no generators. Kept fast: small arrays
(~100x100 or smaller), few streamlines per case. A second agent appends
generator-level tests (the Pydantic-wrapped sources built on this engine)
below the marker at the bottom of this file.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from axibridge.sources import _lineart as L


# -- flow_field ---------------------------------------------------------


def test_flow_field_horizontal_stripes_gives_horizontal_angle():
    # luma varies with y only (horizontal stripes) -> structure runs
    # horizontally -> tangent angle ~ 0.
    luma = np.tile(np.linspace(0, 255, 60), (60, 1)).T
    field = L.flow_field(luma, smooth_px=2.0)
    assert np.median(np.abs(field)) < np.radians(15)


def test_flow_field_vertical_stripes_gives_vertical_angle():
    # luma varies with x only (vertical stripes) -> tangent runs vertically,
    # i.e. angle ~ +/- pi/2 (angles are mod pi, so compare distance to pi/2).
    luma = np.tile(np.linspace(0, 255, 60), (60, 1))
    field = L.flow_field(luma, smooth_px=2.0)
    dist_to_half_pi = np.abs(np.abs(field) - np.pi / 2)
    assert np.median(dist_to_half_pi) < np.radians(15)


def test_flow_field_flat_image_is_zero():
    luma = np.full((30, 30), 128.0)
    field = L.flow_field(luma, smooth_px=2.0)
    assert np.all(field == 0.0)


def test_flow_field_empty_input_does_not_crash():
    assert L.flow_field(np.zeros((0, 0)), smooth_px=2.0).shape == (0, 0)
    assert L.flow_field(np.zeros((1, 5)), smooth_px=2.0).shape == (1, 5)


# -- xdog / sobel_edges ---------------------------------------------------


def _step_luma(w=60, h=40, edge_x=30):
    luma = np.zeros((h, w))
    luma[:, :edge_x] = 255.0
    return luma


def test_xdog_ink_near_step_none_far_away():
    luma = _step_luma()
    ink = L.xdog(luma, sigma=2.0)
    assert ink.dtype == bool
    assert ink.any()
    xs = np.where(ink.any(axis=0))[0]
    assert xs.min() > 20 and xs.max() < 40  # clustered near the x=30 step
    assert not ink[:, :15].any()  # far left: no ink
    assert not ink[:, 45:].any()  # far right: no ink


def test_xdog_threshold_monotone():
    # a Gaussian-softened step so the gradient response is graded, not a
    # single-column spike (which would make any threshold look identical).
    luma = gaussian_filter(_step_luma(), sigma=3)
    lo = L.xdog(luma, sigma=2.0, threshold=0.1)
    hi = L.xdog(luma, sigma=2.0, threshold=0.9)
    assert lo.sum() >= hi.sum()


def test_xdog_flat_image_no_ink():
    assert not L.xdog(np.full((20, 20), 128.0), sigma=2.0).any()


def test_xdog_empty_input():
    out = L.xdog(np.zeros((0, 0)), sigma=2.0)
    assert out.shape == (0, 0) and out.dtype == bool


def test_sobel_edges_contract_and_monotone():
    luma = gaussian_filter(_step_luma(), sigma=3)
    ink = L.sobel_edges(luma)
    assert ink.dtype == bool and ink.any()
    lo = L.sobel_edges(luma, threshold=0.1)
    hi = L.sobel_edges(luma, threshold=0.9)
    assert lo.sum() >= hi.sum()


def test_sobel_edges_flat_image_no_crash_no_ink():
    assert not L.sobel_edges(np.full((20, 20), 50.0)).any()


# -- trace ------------------------------------------------------------------


def test_trace_one_pixel_line_single_polyline():
    edge = np.zeros((40, 100), dtype=bool)
    edge[20, 10:90] = True
    lines = L.trace(edge, smooth=0.0)
    assert len(lines) == 1  # not fragmented, not doubled by the V-scan pass
    assert len(lines[0]) > 40


def test_trace_min_len_culls_small_blob():
    blob = np.zeros((20, 20), dtype=bool)
    blob[10, 10] = True
    blob[10, 11] = True
    blob[11, 10] = True
    assert L.trace(blob, min_len_px=6.0) == []


def test_trace_join_angle_merges_collinear_gap():
    edge = np.zeros((20, 50), dtype=bool)
    edge[5, 10:21] = True
    edge[5, 22:33] = True  # 1px gap at x=21
    lines = L.trace(edge, join_angle_deg=50.0, smooth=0.0)
    assert len(lines) == 1


def test_trace_join_angle_rejects_perpendicular():
    edge = np.zeros((30, 30), dtype=bool)
    edge[5, 5:16] = True   # horizontal segment ending near (15, 5)
    edge[6:17, 17] = True  # vertical segment starting near (17, 6)
    lines = L.trace(edge, join_angle_deg=50.0, min_len_px=2.0, smooth=0.0)
    assert len(lines) == 2  # perpendicular ends must NOT merge


def test_trace_empty_and_all_false():
    assert L.trace(np.zeros((0, 0), dtype=bool)) == []
    assert L.trace(np.zeros((20, 20), dtype=bool)) == []


# -- streamlines --------------------------------------------------------


def _gradient_darkness(h=80, w=80):
    # dark on the right (x large), light on the left
    return np.tile(np.linspace(0, 255, w), (h, 1))


def test_streamlines_deterministic_per_seed():
    darkness = _gradient_darkness()
    field = np.zeros_like(darkness)
    a = L.streamlines(darkness, field, (0, 1), 6, 40, seed=5, direction="fixed", angle_deg=0)
    b = L.streamlines(darkness, field, (0, 1), 6, 40, seed=5, direction="fixed", angle_deg=0)
    c = L.streamlines(darkness, field, (0, 1), 6, 40, seed=6, direction="fixed", angle_deg=0)
    assert a == b
    assert a != c


def test_streamlines_band_partitions_by_side():
    darkness = _gradient_darkness()  # dark on right
    field = np.zeros_like(darkness)
    light = L.streamlines(darkness, field, (0.0, 0.5), 6, 40, seed=1,
                          direction="fixed", angle_deg=90)  # vertical: stays in its column
    dark = L.streamlines(darkness, field, (0.5, 1.0), 6, 40, seed=1,
                         direction="fixed", angle_deg=90)
    assert light and dark
    mean_x = lambda lines: np.mean([x for line in lines for x, _ in line])
    assert mean_x(light) < mean_x(dark)


def test_streamlines_spacing_enforced():
    darkness = np.full((100, 100), 200.0)  # uniformly dark: whole image in band
    field = np.zeros_like(darkness)
    spacing = 8.0
    lines = L.streamlines(darkness, field, (0, 1), spacing, 60, seed=2,
                          direction="fixed", angle_deg=0)
    assert len(lines) >= 2
    pts = [np.array(line[::3]) for line in lines]  # subsample for a fast check
    min_d = np.inf
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = np.sqrt(((pts[i][:, None, :] - pts[j][None, :, :]) ** 2).sum(-1))
            if d.size:
                min_d = min(min_d, float(d.min()))
    assert min_d >= spacing / 3.0


def test_streamlines_dash_more_shorter_lines():
    darkness = np.full((100, 100), 200.0)
    field = np.zeros_like(darkness)
    solid = L.streamlines(darkness, field, (0, 1), 8, 60, seed=3,
                          direction="fixed", angle_deg=0, dash=0.0)
    dashed = L.streamlines(darkness, field, (0, 1), 8, 60, seed=3,
                           direction="fixed", angle_deg=0, dash=0.7)
    assert len(dashed) > len(solid)
    avg = lambda lines: np.mean([len(line) for line in lines])
    assert avg(dashed) < avg(solid)
    assert all(len(line) >= 3 for line in dashed)


def test_streamlines_cross_hatch_adds_perpendicular_population():
    darkness = np.full((100, 100), 200.0)
    field = np.zeros_like(darkness)

    def angle(line):
        (x0, y0), (x1, y1) = line[0], line[-1]
        return np.degrees(np.arctan2(y1 - y0, x1 - x0)) % 180

    single = L.streamlines(darkness, field, (0, 1), 10, 60, seed=4,
                           direction="fixed", angle_deg=0, cross_hatch=False)
    both = L.streamlines(darkness, field, (0, 1), 10, 60, seed=4,
                         direction="fixed", angle_deg=0, cross_hatch=True)
    single_angles = {round(angle(l) / 10) * 10 for l in single if len(l) >= 2}
    both_angles = {round(angle(l) / 10) * 10 for l in both if len(l) >= 2}
    assert single_angles == {0}
    assert both_angles == {0, 90}


def test_streamlines_empty_darkness_no_crash():
    assert L.streamlines(np.zeros((0, 0)), np.zeros((0, 0)), (0, 1), 6, 40, seed=1) == []


def test_streamlines_flow_field_required_for_flow_direction():
    # all-white image: no ink anywhere in a dark band -> empty, not a crash
    darkness = np.zeros((30, 30))
    field = np.zeros((30, 30))
    assert L.streamlines(darkness, field, (0.5, 1.0), 6, 20, seed=1) == []


# -- hand -----------------------------------------------------------------


def _straight_line(n=40, y=20.0):
    return [(float(x), y) for x in range(n)]


def test_hand_wobble_scale_zero_is_identity():
    lines = [_straight_line()]
    out = L.hand(lines, None, tight=0.2, loose=2.0, wobble_scale=0, seed=1)
    assert out == lines
    assert out[0] is not lines[0]  # copies, not the same objects


def test_hand_tight_near_edges_loose_far_away():
    line = _straight_line()
    edge = np.zeros((40, 40), dtype=bool)
    edge[20, 0] = True  # the only edge pixel sits at the line's x=0 end
    out = L.hand([line], edge, tight=0.2, loose=3.0, wobble_scale=1.0, seed=1)[0]
    disp = [abs(x - ox) + abs(y - oy) for (x, y), (ox, oy) in zip(out, line)]
    assert np.mean(disp[:5]) < np.mean(disp[-5:])


def test_hand_deterministic_per_seed():
    lines = [_straight_line()]
    edge = np.zeros((40, 40), dtype=bool)
    edge[20, 0] = True
    a = L.hand(lines, edge, 0.2, 3.0, 1.0, seed=7)
    b = L.hand(lines, edge, 0.2, 3.0, 1.0, seed=7)
    c = L.hand(lines, edge, 0.2, 3.0, 1.0, seed=8)
    assert a == b
    assert a != c


def test_hand_no_edge_map_uses_loose_everywhere():
    lines = [_straight_line()]
    out = L.hand(lines, None, tight=0.2, loose=3.0, wobble_scale=1.0, seed=1)
    assert out and len(out[0]) == len(lines[0])


def test_hand_empty_lines_no_crash():
    assert L.hand([], None, 0.2, 3.0, 1.0, seed=1) == []


# -- progress reporting -----------------------------------------------------


def test_report_progress_is_noop_outside_scope():
    # no progress_scope installed -> report_progress must not raise
    luma = np.tile(np.linspace(0, 255, 30), (30, 1))
    L.flow_field(luma, smooth_px=1.0)  # calls report_progress internally


def test_progress_reported_inside_scope():
    from axibridge.registry import progress_scope

    seen = []
    luma = np.tile(np.linspace(0, 255, 30), (30, 1))
    with progress_scope(lambda frac, msg="": seen.append(frac)):
        L.flow_field(luma, smooth_px=1.0)
    assert seen and all(0 <= f <= 1 for f in seen)


# =====================================================================
# Generator-level tests (lineart v2 Source modules) go below this line.
# =====================================================================

import io

from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.assets import asset_store
from axibridge.registry import get_source
from axibridge.session import session
from axibridge.sources import _pixelgen

GEN_IDS = ["lineart_edges", "lineart_hatch"]


@pytest.fixture(autouse=True)
def small_working_canvas(monkeypatch):
    """Generators resample to WORK_W px wide; shrink it so tests stay fast
    (same pattern as test_plotterfun.py)."""
    monkeypatch.setattr(_pixelgen, "WORK_W", 80)
    monkeypatch.setattr(_pixelgen, "MAX_H", 160)


@pytest.fixture(autouse=True)
def gradient_asset():
    """Left-to-right white -> black gradient, same construction as
    test_plotterfun.py's fixture: the dark side is x > half."""
    from PIL import Image

    img = Image.new("L", (64, 48))
    img.putdata([255 - int(255 * (i % 64) / 64) for i in range(64 * 48)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    before = asset_store.all()
    asset_store.put("grad.png", buf.getvalue())
    yield
    asset_store.replace_all(before)


@pytest.fixture()
def step_asset():
    """A hard vertical edge (left white / right black). XDoG's response to a
    perfectly smooth linear ramp is ~zero by construction (difference of two
    Gaussians of a linear function is itself ~linear, no curvature to flag
    as ink) — the gradient fixture above legitimately produces an empty
    lineart_edges/xdog result, per the engine's "empty is fine" contract.
    The edges-specific assertions below (xdog-vs-sobel, threshold monotone)
    need an actual edge, so they opt into this fixture instead."""
    from PIL import Image

    img = Image.new("L", (64, 48))
    img.putdata([255 if (i % 64) < 32 else 0 for i in range(64 * 48)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    before = asset_store.all()
    asset_store.put("step.png", buf.getvalue())
    yield
    asset_store.replace_all(before)


def _gen(module_id, **params):
    src = get_source(module_id)
    return src.generate(src.Params(image="grad.png", **params))


def _gen_step(module_id, **params):
    src = get_source(module_id)
    return src.generate(src.Params(image="step.png", **params))


# -- both generators: bounds, ValueError, determinism, width -----------------


@pytest.mark.parametrize("module_id", GEN_IDS)
def test_requires_image(module_id):
    src = get_source(module_id)
    with pytest.raises(ValueError):
        src.generate(src.Params(image=""))
    with pytest.raises(ValueError):
        src.generate(src.Params(image="no-such-asset.png"))


@pytest.mark.parametrize("module_id", GEN_IDS)
def test_width_honored(module_id):
    doc = _gen(module_id, width=123)
    assert doc.width == 123
    assert abs(doc.height - 123 * 48 / 64) < 2  # aspect preserved


def test_hatch_generates_paths_in_bounds():
    doc = _gen("lineart_hatch", width=100)
    paths = doc.layers[0].paths
    assert paths, "lineart_hatch produced nothing on the gradient"
    assert all(len(p.points) >= 2 for p in paths)
    xs = [x for p in paths for x, _ in p.points]
    ys = [y for p in paths for _, y in p.points]
    assert -15 < min(xs) and max(xs) < 115
    assert -15 < min(ys) and max(ys) < doc.height + 15


def test_hatch_deterministic_per_seed():
    a = _gen("lineart_hatch", seed=3)
    b = _gen("lineart_hatch", seed=3)
    c = _gen("lineart_hatch", seed=4)
    pts = lambda d: [p.points for p in d.layers[0].paths]
    assert pts(a) == pts(b)
    assert pts(a) != pts(c)


def test_edges_generates_paths_in_bounds():
    # xdog's default is near-silent on a smooth linear ramp (see step_asset's
    # docstring); sobel's plain gradient-magnitude threshold isn't, so it's
    # the mode that exercises "produces real ink on the shared gradient".
    doc = _gen("lineart_edges", width=100, edge_mode="sobel")
    paths = doc.layers[0].paths
    assert paths, "lineart_edges (sobel) produced nothing on the gradient"
    assert all(len(p.points) >= 2 for p in paths)
    xs = [x for p in paths for x, _ in p.points]
    ys = [y for p in paths for _, y in p.points]
    assert -15 < min(xs) and max(xs) < 115
    assert -15 < min(ys) and max(ys) < doc.height + 15


def test_edges_deterministic_per_seed():
    a = _gen("lineart_edges", edge_mode="sobel", seed=3)
    b = _gen("lineart_edges", edge_mode="sobel", seed=3)
    c = _gen("lineart_edges", edge_mode="sobel", seed=4)
    pts = lambda d: [p.points for p in d.layers[0].paths]
    assert pts(a) == pts(b)
    assert pts(a) != pts(c)


# -- band partition through the generator -------------------------------------


def test_hatch_band_partition_through_generator():
    light = _gen("lineart_hatch", width=100, band_from=0.0, band_to=0.5,
                 direction="fixed", angle_deg=90)
    dark = _gen("lineart_hatch", width=100, band_from=0.5, band_to=1.0,
               direction="fixed", angle_deg=90)
    assert light.layers[0].paths and dark.layers[0].paths
    mean_x = lambda d: sum(x for p in d.layers[0].paths for x, _ in p.points) / sum(
        len(p.points) for p in d.layers[0].paths
    )
    assert mean_x(light) < mean_x(dark)  # gradient: dark side is x > half


# -- edges: xdog vs sobel, threshold monotone (needs a real edge) ------------


def test_edges_xdog_vs_sobel_differ(step_asset):
    xdog_doc = _gen_step("lineart_edges", width=100, edge_mode="xdog", wobble=0)
    sobel_doc = _gen_step("lineart_edges", width=100, edge_mode="sobel", wobble=0)
    xdog_pts = [p.points for p in xdog_doc.layers[0].paths]
    sobel_pts = [p.points for p in sobel_doc.layers[0].paths]
    assert xdog_pts != sobel_pts


def test_edges_higher_threshold_fewer_points(step_asset):
    # post-skeletonization both thresholds collapse the step's single strong
    # edge to the same centreline, so traced-point counts stop discriminating;
    # ink_fill renders the pre-thinning ink WIDTH, which is what strictness
    # actually shrinks (the mask-level monotonicity test lives engine-side)
    lo = _gen_step("lineart_edges", width=100, edge_mode="xdog", edge_threshold=0.1,
                   ink_fill=True, fill_spacing=2.0)
    hi = _gen_step("lineart_edges", width=100, edge_mode="xdog", edge_threshold=0.9,
                   ink_fill=True, fill_spacing=2.0)
    total = lambda d: sum(len(p.points) for p in d.layers[0].paths)
    assert total(hi) < total(lo)


# -- one-click stack -----------------------------------------------------------


def test_stack_faithful_four_layers():
    layers = session.add_lineart_stack("grad.png", "faithful")
    assert len(layers) == 4
    names = " ".join(layer.name for layer in layers)
    for word in ("lights", "mids", "darks", "edges"):
        assert word in names
    for layer in layers:
        assert layer.source.type == "generator"
        assert layer.source.generator in ("lineart_hatch", "lineart_edges")
        assert layer.source.params
    assert session.undo()
    assert len(session.project.layers) == 0  # one undo removes all 4


def test_stack_artistic_three_layers():
    layers = session.add_lineart_stack("grad.png", "artistic")
    assert len(layers) == 3
    names = " ".join(layer.name for layer in layers)
    for word in ("mids", "darks", "edges"):
        assert word in names


# -- API -----------------------------------------------------------------------


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def test_lineart_stack_api(client):
    r = client.post("/api/layers/lineart_stack", json={"image": "grad.png", "flavor": "faithful"})
    assert r.status_code == 200, r.text
    assert len(r.json()["layers"]) == 4

    bad = client.post("/api/layers/lineart_stack", json={"image": "grad.png", "flavor": "bogus"})
    assert bad.status_code == 422

    # missing asset: match add_generated_layer's endpoint, which maps the
    # generator's plain ValueError (via luma_grid -> working_dims) to 400.
    missing = client.post("/api/layers/lineart_stack",
                          json={"image": "no-such-asset.png", "flavor": "faithful"})
    assert missing.status_code == 400


# -- edges detail round: thinning, resolution, ink mass/fill -------------------


def test_thin_mask_reduces_thick_bar_to_skeleton():
    mask = np.zeros((30, 60), dtype=bool)
    mask[12:19, 5:55] = True  # 7 px thick bar
    skel = L.thin_mask(mask)
    assert skel.sum() < mask.sum() / 3  # genuinely thinned, not nibbled
    # spans the bar horizontally (Zhang-Suen rounds the ends by a few px)
    cols = np.where(skel.any(axis=0))[0]
    assert cols.min() <= 10 and cols.max() >= 48
    # rows collapse to (near) a single centreline
    assert skel.any(axis=1).sum() <= 3


def test_thin_mask_empty_and_thin_inputs_stable():
    empty = np.zeros((10, 10), dtype=bool)
    assert not L.thin_mask(empty).any()
    line = np.zeros((10, 20), dtype=bool)
    line[5, 2:18] = True  # already 1 px: survives (endpoints may erode a px)
    out = L.thin_mask(line)
    assert out.sum() >= line.sum() - 2


def _total_points(doc):
    return sum(len(p.points) for layer in doc.layers for p in layer.paths)


def test_edges_resolution_increases_detail(step_asset):
    lo = _gen_step("lineart_edges", resolution=1.0)
    hi = _gen_step("lineart_edges", resolution=2.0)
    assert _total_points(hi) > _total_points(lo)
    # mm output size is resolution-independent
    assert abs(lo.width - hi.width) < 1e-6


def test_edges_ink_fill_adds_mass(step_asset):
    outline = _gen_step("lineart_edges", mass=1.0, edge_threshold=0.3)
    filled = _gen_step("lineart_edges", mass=1.0, edge_threshold=0.3,
                       ink_fill=True, fill_spacing=2.0)
    assert _total_points(filled) > _total_points(outline)


def test_edges_mass_grows_ink(step_asset):
    lean = _gen_step("lineart_edges", mass=0.0, edge_threshold=0.3,
                     ink_fill=True, fill_spacing=2.0)
    massy = _gen_step("lineart_edges", mass=1.0, edge_threshold=0.3,
                      ink_fill=True, fill_spacing=2.0)
    assert _total_points(massy) > _total_points(lean)


# -- clip-backed layers follow the timeline by default --------------------------


@pytest.fixture()
def clip_asset():
    """Three-frame gradient sequence under the ``seq#`` prefix."""
    from PIL import Image

    before = asset_store.all()
    for i in range(3):
        img = Image.new("L", (64, 48))
        img.putdata([255 - int(255 * ((x % 64) / 64)) for x in range(64 * 48)])
        buf = io.BytesIO()
        img.save(buf, "PNG")
        asset_store.put(f"seq#{i:04d}.png", buf.getvalue())
    yield
    asset_store.replace_all(before)


def test_sequence_layer_follows_timeline_by_default(clip_asset):
    layer = session.add_generated_layer("lineart_hatch", {"image": "seq#"})
    assert layer.frame_follow is True
    still = session.add_generated_layer("lineart_hatch", {"image": "grad.png"})
    assert still.frame_follow is False


def test_stack_on_sequence_follows_timeline(clip_asset):
    layers = session.add_lineart_stack("seq#", "artistic")
    assert layers and all(l.frame_follow for l in layers)
