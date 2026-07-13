"""The plotterfun-ported image generators (sources/_pixelgen.py family).

Run against a tiny synthetic asset with the working resolution patched down,
so the whole module stays fast and hardware-free."""

import io

import pytest

from axibridge.assets import asset_store
from axibridge.registry import get_source, progress_scope
from axibridge.sources import _pixelgen

ALL_IDS = ["margins", "linescan", "longwave", "dots", "halftone",
           "waves", "subline", "linedraw", "polyspiral", "squiggle_lr"]


@pytest.fixture(autouse=True)
def small_working_canvas(monkeypatch):
    """Generators resample to WORK_W px wide; shrink it so tests stay fast."""
    monkeypatch.setattr(_pixelgen, "WORK_W", 80)
    monkeypatch.setattr(_pixelgen, "MAX_H", 160)


@pytest.fixture(autouse=True)
def gradient_asset():
    """Left-to-right white→black gradient: the dark side is x > half."""
    from PIL import Image

    img = Image.new("L", (64, 48))
    img.putdata([255 - int(255 * (i % 64) / 64) for i in range(64 * 48)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    before = asset_store.all()
    asset_store.put("grad.png", buf.getvalue())
    yield
    asset_store.replace_all(before)


def _gen(module_id, **params):
    src = get_source(module_id)
    return src.generate(src.Params(image="grad.png", **params))


@pytest.mark.parametrize("module_id", ALL_IDS)
def test_generates_paths_in_bounds(module_id):
    doc = _gen(module_id, width=100)
    paths = doc.layers[0].paths
    assert paths, f"{module_id} produced nothing on a gradient"
    assert all(len(p.points) >= 2 for p in paths)
    xs = [x for p in paths for x, _ in p.points]
    ys = [y for p in paths for _, y in p.points]
    # px-space arcs/wiggles may poke a little past the frame; not wildly
    assert -15 < min(xs) and max(xs) < 115
    assert -15 < min(ys) and max(ys) < doc.height + 15
    assert doc.width == 100
    assert abs(doc.height - 100 * 48 / 64) < 2  # aspect preserved


@pytest.mark.parametrize("module_id", ALL_IDS)
def test_requires_image(module_id):
    src = get_source(module_id)
    with pytest.raises(ValueError):
        src.generate(src.Params(image=""))
    with pytest.raises(ValueError):
        src.generate(src.Params(image="no-such-asset.png"))


def test_linescan_draws_the_dark_side():
    doc = _gen("linescan", threshold=128)
    xs = [x for p in doc.layers[0].paths for x, _ in p.points]
    assert min(xs) > 150.0 * 0.35  # gradient: dark half is x > width/2
    inv = _gen("linescan", threshold=128, invert=True)
    inv_xs = [x for p in inv.layers[0].paths for x, _ in p.points]
    assert max(inv_xs) < 150.0 * 0.65


def test_image_processing_group_and_gamma_affect_pixel_generators():
    src = get_source("linescan")
    props = src.Params.model_json_schema()["properties"]
    assert props["brightness"]["group"] == "Image processing"
    assert props["gamma"]["group"] == "Image processing"
    base = _gen("linescan", width=100, threshold=128)
    gamma = _gen("linescan", width=100, threshold=128, gamma=3)
    base_xs = [x for p in base.layers[0].paths for x, _ in p.points]
    gamma_xs = [x for p in gamma.layers[0].paths for x, _ in p.points]
    assert min(gamma_xs) < min(base_xs) - 10.0


def test_dots_seeded_and_denser_when_dark():
    a = _gen("dots", seed=7)
    b = _gen("dots", seed=7)
    c = _gen("dots", seed=8)
    pts = lambda d: [p.points for p in d.layers[0].paths]
    assert pts(a) == pts(b)
    assert pts(a) != pts(c)
    left = sum(1 for p in a.layers[0].paths if p.points[0][0] < 75)
    right = len(a.layers[0].paths) - left
    assert right > left * 2  # dark (right) side stipples much denser


def test_halftone_circles_closed():
    doc = _gen("halftone")
    for p in doc.layers[0].paths:
        assert p.points[0] == p.points[-1]


def test_polyspiral_single_continuous_path():
    doc = _gen("polyspiral")
    assert len(doc.layers[0].paths) == 1


def test_squiggle_join_ends_single_path():
    doc = _gen("squiggle_lr", join_ends=True)
    assert len(doc.layers[0].paths) == 1


def test_linedraw_deterministic_per_seed():
    a = _gen("linedraw", seed=3)
    b = _gen("linedraw", seed=3)
    assert [p.points for p in a.layers[0].paths] == [p.points for p in b.layers[0].paths]


def test_linedraw_image_processing_invert_flips_hatching():
    normal = _gen("linedraw", width=100, contours=False, hatching=True,
                  hatch_scale=6, noise_scale=0, seed=3)
    inverted = _gen("linedraw", width=100, contours=False, hatching=True,
                    hatch_scale=6, noise_scale=0, seed=3, invert=True)
    avg = lambda doc: sum(x for p in doc.layers[0].paths for x, _ in p.points) / sum(
        len(p.points) for p in doc.layers[0].paths
    )
    assert avg(normal) > 55.0
    assert avg(inverted) < 45.0


def test_progress_reported():
    seen = []
    with progress_scope(lambda frac, msg="": seen.append(frac)):
        _gen("linedraw")
    assert seen and all(0 <= f <= 1 for f in seen)
    assert seen == sorted(seen)  # monotonic per stage ordering


# -- live preview endpoint -----------------------------------------------------


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        yield c


def test_preview_returns_lines_without_touching_project(client):
    layers_before = client.get("/api/project").json()["layers"]
    r = client.post("/api/generators/preview",
                    json={"module": "linescan", "params": {"image": "grad.png"}})
    assert r.status_code == 200
    body = r.json()
    assert body["lines"] and all(len(line) >= 2 for line in body["lines"])
    assert body["points"] == sum(len(line) for line in body["lines"])
    assert not body["decimated"]
    assert client.get("/api/project").json()["layers"] == layers_before  # no layer, no mutation


def test_preview_decimates_heavy_output(client, monkeypatch):
    import axibridge.api as api_mod

    monkeypatch.setattr(api_mod, "_PREVIEW_MAX_PTS", 500)
    r = client.post("/api/generators/preview",
                    json={"module": "subline", "params": {"image": "grad.png"}})
    body = r.json()
    assert body["decimated"]
    assert body["points"] > 500                      # true count reported
    sent = sum(len(line) for line in body["lines"])
    assert sent <= 500 + 2 * len(body["lines"])      # stride cap (+ kept endpoints)
    assert all(len(line) >= 2 for line in body["lines"])


def test_preview_errors(client):
    assert client.post("/api/generators/preview", json={"module": "nope"}).status_code == 404
    r = client.post("/api/generators/preview", json={"module": "halftone", "params": {}})
    assert r.status_code == 400
    assert "image" in r.json()["detail"]


def test_effects_preview_is_read_only(client):
    layer = client.post("/api/layers/generate", json={"module": "grid", "params": {}}).json()
    candidate = [{"effect": "multipass", "enabled": True, "params": {}}]
    r = client.post(f"/api/layers/{layer['id']}/effects/preview", json={"effects": candidate})
    assert r.status_code == 200
    body = r.json()
    assert body["lines"]
    plain = client.post(f"/api/layers/{layer['id']}/effects/preview", json={"effects": []}).json()
    assert body["points"] > plain["points"]  # multipass added the return pass
    # nothing committed: the real layer still has no effects
    stored = next(l for l in client.get("/api/project").json()["layers"] if l["id"] == layer["id"])
    assert stored["effects"] == []
    assert client.post("/api/layers/zzzz/effects/preview", json={"effects": []}).status_code == 404


def test_exif_orientation_respected():
    """A 'sideways + EXIF rotate' photo must decode upright: browsers honour
    the tag when showing the ghost, so sampling has to as well."""
    from PIL import Image

    img = Image.new("L", (40, 20))  # landscape pixels...
    exif = Image.Exif()
    exif[274] = 6  # ...tagged "rotate 90 CW to view" (typical portrait phone shot)
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    asset_store.put("exif.jpg", buf.getvalue())
    _, w, h = asset_store.grayscale("exif.jpg")
    assert (w, h) == (20, 40)  # upright: portrait, not the raw landscape buffer


# -- image_threshold: min/max band ------------------------------------------


def _gen_threshold(**params):
    src = get_source("image_threshold")
    return src.generate(src.Params(image="grad.png", width=80, smoothing=0,
                                   detail=1.0, min_area=1, **params))


def test_image_threshold_legacy_param_matches_new_defaults():
    """A saved project's ``{"threshold": 0.5}`` dict must load and generate
    byte-identically to the NEW defaults (threshold_min=0.0,
    threshold_max=0.5): old inside was {v < t} = the band [0, t), and the
    min-trace at 0.0 yields no loops — old projects can't silently change
    on open."""
    src = get_source("image_threshold")
    legacy = src.generate(src.Params(image="grad.png", width=80, threshold=0.5,
                                     smoothing=0, detail=1.0, min_area=1))
    defaults = _gen_threshold()  # threshold_min=0.0, threshold_max=0.5
    explicit = _gen_threshold(threshold_min=0.0, threshold_max=0.5)
    legacy_pts = [p.points for p in legacy.layers[0].paths]
    assert legacy_pts == [p.points for p in defaults.layers[0].paths]
    assert legacy_pts == [p.points for p in explicit.layers[0].paths]
    assert [p.filled for p in legacy.layers[0].paths] == \
           [p.filled for p in defaults.layers[0].paths]


def test_image_threshold_legacy_param_populates_max_field():
    """The before-validator maps legacy ``threshold: t`` to the band [0, t]:
    threshold_max=t, threshold_min left at its 0.0 default (not just leaving
    the legacy key silently dropped by pydantic's extra="ignore" default)."""
    src = get_source("image_threshold")
    p = src.Params(image="grad.png", threshold=0.7)
    assert p.threshold_min == 0.0
    assert p.threshold_max == 0.7


def test_image_threshold_band_is_true_band_select():
    """inside = {min <= v <= max}, always: a mid band traces BOTH its edges —
    genuinely different geometry from the one-sided cutoff, and the dark
    region below min reads as a hole via even-odd parity."""
    cutoff = _gen_threshold(threshold_min=0.0, threshold_max=0.3)  # legacy-style {v < 0.3}
    band = _gen_threshold(threshold_min=0.3, threshold_max=0.7)
    cutoff_pts = [p.points for p in cutoff.layers[0].paths]
    band_pts = [p.points for p in band.layers[0].paths]
    assert band_pts != cutoff_pts
    # the band is bounded on both sides: two closed loops (min edge + max
    # edge), vs. the single one-sided cutoff's one loop
    assert len(band.layers[0].paths) == 2
    assert len(cutoff.layers[0].paths) == 1


def test_image_threshold_max_at_one_is_continuous_not_inverted():
    """max=1.0 must NOT flip back to the legacy dark-inside selection: it is
    the honest "everything from min up" band, continuous with max=0.999.
    (min, 1.0) = the min-edge loop PLUS the image-boundary rectangle (pure
    white counts as inside against the padding)."""
    cutoff = _gen_threshold(threshold_min=0.0, threshold_max=0.3)  # {v < 0.3}
    top = _gen_threshold(threshold_min=0.3, threshold_max=1.0)     # {0.3 <= v <= 1}
    near = _gen_threshold(threshold_min=0.3, threshold_max=0.999)
    # NOT the inverted legacy selection
    assert [p.points for p in top.layers[0].paths] != [p.points for p in cutoff.layers[0].paths]
    # same loop structure as just below the top: min edge + upper boundary
    assert len(top.layers[0].paths) == len(near.layers[0].paths) == 2
    # and the second loop is the image-boundary rectangle: spans ~full width
    spans = [max(x for x, _ in p.points) - min(x for x, _ in p.points)
             for p in top.layers[0].paths]
    assert max(spans) > 75.0  # ~the whole 80 mm image, not an interior contour


def test_image_threshold_band_paths_closed_and_filled():
    band = _gen_threshold(threshold_min=0.3, threshold_max=0.7)
    paths = band.layers[0].paths
    assert paths
    for p in paths:
        assert p.filled
        assert p.points[0] == p.points[-1]  # closed loop, unchanged semantics


def test_image_threshold_min_max_swaps_instead_of_crashing():
    """An inverted band (min > max, e.g. from a UI drag) must not raise —
    it swaps so old projects (and slider fat-fingers) never 500."""
    src = get_source("image_threshold")
    p = src.Params(image="grad.png", threshold_min=0.8, threshold_max=0.2)
    assert p.threshold_min == 0.2
    assert p.threshold_max == 0.8
    # and it still generates without error
    src.generate(p.model_copy(update={"image": "grad.png", "width": 80,
                                      "smoothing": 0, "detail": 1.0, "min_area": 1}))
