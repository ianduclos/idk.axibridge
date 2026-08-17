"""Colour separation: the channel decode, the tone window, and the stack.

Two things here are worth more than the rest, because they are what the whole
feature rests on:

* **Polarity.** Every plate comes back in ``grayscale``'s convention, 0 = draw
  hardest. If that ever inverts, every image generator inverts with it and no
  other test in the suite would say so.
* **Luma is untouched.** The default path has to be the code it always was, not
  a re-derivation that happens to agree. That is asserted directly rather than
  sampled.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from axibridge.app import create_app
from axibridge.assets import asset_store
from axibridge.registry import get_source
from axibridge.session import session
from axibridge.sources import _pixelgen


@pytest.fixture(autouse=True)
def small_working_canvas(monkeypatch):
    """Shrink the resample target so tests stay fast (test_plotterfun's pattern)."""
    monkeypatch.setattr(_pixelgen, "WORK_W", 80)
    monkeypatch.setattr(_pixelgen, "MAX_H", 160)


@pytest.fixture(autouse=True)
def colour_asset():
    """Four known pixels — black, white, pure cyan, pure red — plus a colour
    ramp big enough for a generator to draw on.

    ``swatch.png`` is for exact maths; ``photo.png`` is for "does a generator
    actually produce different geometry per plate".
    """
    from PIL import Image

    swatch = Image.new("RGB", (4, 1))
    swatch.putdata([(0, 0, 0), (255, 255, 255), (0, 255, 255), (255, 0, 0)])

    # left half saturated red, right half saturated cyan, with a vertical
    # luminance ramp on top so luma and the ink plates genuinely disagree
    photo = Image.new("RGB", (64, 48))
    photo.putdata([
        (255, v, v) if (i % 64) < 32 else (v, 255, 255)
        for i in range(64 * 48)
        for v in [int(255 * (i // 64) / 48)]
    ])

    before = asset_store.all()
    for name, img in (("swatch.png", swatch), ("photo.png", photo)):
        buf = io.BytesIO()
        img.save(buf, "PNG")
        asset_store.put(name, buf.getvalue())
    yield
    asset_store.replace_all(before)


def plate(channel, bg=1.0, name="swatch.png"):
    rows, _, _ = asset_store.channel(name, channel, black_generation=bg)
    return [round(v, 6) for v in rows[0]]


# -- decode: polarity and the CMYK maths --------------------------------------


def test_luma_delegates_to_grayscale():
    """Not "equivalent to" — the same call. Byte-identity for the default is
    the one thing that cannot be allowed to drift, and delegation is the only
    way to guarantee it rather than test for it."""
    assert asset_store.channel("photo.png", "luma") == asset_store.grayscale("photo.png")
    assert (asset_store.channel("photo.png", "luma", blur_px=1.5, rotate=90, size=(20, 20))
            == asset_store.grayscale("photo.png", 1.5, 90, (20, 20)))


def test_pure_cyan_draws_hardest_on_the_cyan_plate():
    """The polarity contract, on the pixel where it is unambiguous. A cyan
    pixel is full cyan ink and no magenta or yellow, and 'full ink' has to
    read as 0 (draw hardest) or every generator inverts."""
    assert plate("c")[2] == 0.0
    assert plate("m")[2] == 1.0
    assert plate("y")[2] == 1.0


def test_pure_red_is_magenta_plus_yellow():
    assert plate("c")[3] == 1.0  # no cyan in red
    assert plate("m")[3] == 0.0
    assert plate("y")[3] == 0.0


def test_white_is_blank_on_every_plate():
    for ch in ("c", "m", "y", "k", "r", "g", "b"):
        assert plate(ch)[1] == 1.0, f"{ch} put ink on white paper"


def test_full_black_generation_hands_the_darks_to_k():
    assert plate("k", bg=1.0)[0] == 0.0  # black pixel: K draws hardest
    for ch in ("c", "m", "y"):
        assert plate(ch, bg=1.0)[0] == 1.0  # ...and CMY stay clean


def test_zero_black_generation_moves_the_darks_into_cmy():
    assert plate("k", bg=0.0)[0] == 1.0  # K plate is empty...
    for ch in ("c", "m", "y"):
        assert plate(ch, bg=0.0)[0] == 0.0  # ...and CMY carry it by overprint


def test_black_generation_is_continuous():
    assert plate("k", bg=0.5)[0] == 0.5
    assert plate("c", bg=0.5)[0] == 0.5


def test_cmy_at_zero_black_generation_equals_rgb():
    """The identity that proves the maths rather than merely exercising it:
    'remove no black' means C = 1-r, so the plate (1-C) is exactly r."""
    for ink, raw in (("c", "r"), ("m", "g"), ("y", "b")):
        assert plate(ink, bg=0.0) == plate(raw), f"{ink} at bg=0 should be the {raw} plane"


def test_black_generation_does_not_move_rgb_planes():
    for ch in ("r", "g", "b"):
        assert plate(ch, bg=0.0) == plate(ch, bg=1.0)


def test_rgb_plane_is_the_raw_channel():
    # black, white, cyan (r=0), red (r=255)
    assert plate("r") == [0.0, 1.0, 0.0, 1.0]
    assert plate("g") == [0.0, 1.0, 1.0, 0.0]


def test_unknown_channel_raises():
    with pytest.raises(ValueError):
        asset_store.channel("swatch.png", "puce")


def test_missing_asset_returns_none():
    assert asset_store.channel("no-such.png", "c") is None


def test_cache_separates_channels_and_black_generation():
    assert plate("c", bg=1.0) != plate("c", bg=0.0)
    assert plate("c") != plate("m")


def test_reupload_invalidates_the_channel_cache():
    from PIL import Image

    assert plate("c")[0] == 1.0
    inverted = Image.new("RGB", (4, 1))
    inverted.putdata([(0, 255, 255)] * 4)  # all cyan now
    buf = io.BytesIO()
    inverted.save(buf, "PNG")
    asset_store.put("swatch.png", buf.getvalue())
    assert plate("c")[0] == 0.0, "channel() served a stale plate after re-upload"


# -- generators see the channel ------------------------------------------------


def _gen(module_id, **params):
    src = get_source(module_id)
    return src.generate(src.Params(image="photo.png", width=100, **params))


def test_default_channel_matches_omitting_it_entirely():
    """The regression pin for every project saved before this shipped: params
    with no channel key must resolve exactly as params that ask for luma."""
    src = get_source("halftone")
    implicit = src.generate(src.Params(**{"image": "photo.png", "width": 100}))
    explicit = src.generate(src.Params(image="photo.png", width=100, channel="luma"))
    pts = lambda d: [p.points for p in d.layers[0].paths]
    assert pts(implicit) == pts(explicit)


def test_channel_changes_the_geometry():
    luma = _gen("halftone", channel="luma")
    cyan = _gen("halftone", channel="c")
    pts = lambda d: [p.points for p in d.layers[0].paths]
    assert pts(luma) != pts(cyan)


def test_image_threshold_takes_a_channel_too():
    """image_threshold has its own params base, so it is the one that would
    silently miss out if the two declarations ever drift apart."""
    src = get_source("image_threshold")
    assert "channel" in src.Params.model_fields
    luma = src.generate(src.Params(image="photo.png", channel="luma"))
    cyan = src.generate(src.Params(image="photo.png", channel="c"))
    assert [p.points for p in luma.layers[0].paths] != [p.points for p in cyan.layers[0].paths]


def test_every_pixelgen_family_source_gained_a_channel():
    for module_id in ("halftone", "dots", "subline", "waves", "lineart_hatch",
                      "linedraw", "fast_marching_topo", "image_threshold"):
        assert "channel" in get_source(module_id).Params.model_fields, module_id


# -- the tone window -----------------------------------------------------------


def test_tone_window_defaults_are_identity():
    a = _gen("halftone")
    b = _gen("halftone", tone_from=0.0, tone_to=1.0)
    pts = lambda d: [p.points for p in d.layers[0].paths]
    assert pts(a) == pts(b)


def _ink(doc):
    """Total drawn length in mm. Point count is the wrong measure for a
    halftone — it emits a circle per grid cell whatever the darkness, so only
    the radii move."""
    return sum(
        ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        for p in doc.layers[0].paths
        for (x1, y1), (x2, y2) in zip(p.points, p.points[1:])
    )


def test_tone_window_drops_tones_outside_it():
    """Each band lays less ink than the whole tonal range.

    Only the inequality is asserted here, not additivity: halftone emits a
    minimum-radius circle per grid cell even at zero darkness, so two
    complementary bands re-pay that floor and land a few percent over the
    original. That floor is halftone's own, which is why exact partitioning is
    pinned one level down, on the LUT itself."""
    full = _ink(_gen("halftone"))
    assert _ink(_gen("halftone", tone_from=0.6, tone_to=1.0)) < full
    assert _ink(_gen("halftone", tone_from=0.0, tone_to=0.6)) < full


def test_tone_window_bands_add_back_up_to_the_whole():
    """Pass-through's promise, where it holds exactly: split the tone range in
    two and the plates together carry precisely the original ink. This is what
    stacking separated plates depends on, and what tone_rescale trades away."""
    P = get_source("halftone").Params
    whole = _pixelgen._tone_lut(P(image="photo.png"))
    lights = _pixelgen._tone_lut(P(image="photo.png", tone_from=0.0, tone_to=0.6))
    darks = _pixelgen._tone_lut(P(image="photo.png", tone_from=0.6, tone_to=1.0))
    for w, lo, hi in zip(whole, lights, darks):
        assert lo + hi == pytest.approx(w)


def test_tone_window_bands_are_disjoint():
    lut_lights = _pixelgen._tone_lut(
        get_source("halftone").Params(image="photo.png", tone_from=0.0, tone_to=0.3))
    lut_darks = _pixelgen._tone_lut(
        get_source("halftone").Params(image="photo.png", tone_from=0.6, tone_to=1.0))
    assert not any(a > 0 and b > 0 for a, b in zip(lut_lights, lut_darks))


def test_tone_rescale_reaches_full_density():
    """Pass-through keeps a narrow band faint so stacked bands add back up to
    the original; rescale stretches it so the band reads on its own. Both are
    wanted, which is why it is a checkbox and not a code decision."""
    params = dict(image="photo.png", tone_from=0.0, tone_to=0.3)
    P = get_source("halftone").Params
    passed = max(_pixelgen._tone_lut(P(**params, tone_rescale=False)))
    scaled = max(_pixelgen._tone_lut(P(**params, tone_rescale=True)))
    assert passed < 0.35 * 255
    assert scaled > 0.95 * 255


def test_tone_window_absent_where_it_would_not_work():
    """It lives on PixelGenParams, so it appears only on the sources whose
    tone actually runs through _tone_lut. The five with their own tone paths
    must NOT show a knob that would do nothing."""
    for module_id in ("lineart_hatch", "lineart_edges", "linedraw",
                      "fast_marching_topo", "image_threshold"):
        assert "tone_from" not in get_source(module_id).Params.model_fields, module_id


# -- the separation stack ------------------------------------------------------

CMYK = [{"name": n, "params": {"channel": c}}
        for n, c in (("cyan", "c"), ("magenta", "m"), ("yellow", "y"), ("black", "k"))]


def test_stack_creates_one_layer_per_plate():
    layers = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK)
    assert len(layers) == 4
    assert [l.source.params["channel"] for l in layers] == ["c", "m", "y", "k"]
    for layer in layers:
        assert layer.source.type == "generator", "a plate must stay live, not bake"
        assert layer.source.generator == "halftone"


def test_stack_names_carry_the_plate():
    layers = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK)
    assert "cyan" in layers[0].name and "Halftone" in layers[0].name.title()


def test_stack_is_one_undo_step():
    session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK)
    assert len(session.project.layers) == 4
    assert session.undo()
    assert len(session.project.layers) == 0


def test_stack_plates_share_identical_placement():
    """Plates are meant to overprint. Same image/width means _placement_transform
    must land every one of them in exactly the same place — a fraction of a
    millimetre of drift here is a visibly misregistered print."""
    layers = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK)
    transforms = {(round(l.transform.e, 9), round(l.transform.f, 9)) for l in layers}
    assert len(transforms) == 1, f"plates drifted apart: {transforms}"
    (e, f) = next(iter(transforms))
    assert not (e == 0.0 and f == 0.0)  # actually centred


def test_stack_plates_do_not_occlude_each_other():
    layers = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK)
    assert not any(l.occluder for l in layers), "plates must overprint, not knock out"


def test_stack_assigns_and_snapshots_pens():
    from axibridge.stores import Pen, pen_library

    pen = Pen(name="cyan felt", color="#00aeef")
    pen_library.upsert(pen)
    try:
        plates = [{"name": "cyan", "params": {"channel": "c"}, "pen_id": pen.id}]
        layers = session.add_separation_stack("halftone", {"image": "photo.png"}, plates)
        assert layers[0].pen_id == pen.id
        # frozen into the project so a moved folder still knows what drew it
        assert pen.id in session.project.pens_used
    finally:
        pen_library.delete(pen.id)


def test_stack_accepts_a_per_plate_generator():
    """Ian's regime-collision case: each plate rendered in a different mark
    language. Params carry across by intersection with the target's fields, so
    the merge can never build an invalid params dict."""
    plates = [
        {"name": "cyan", "generator": "halftone", "params": {"channel": "c"}},
        {"name": "magenta", "generator": "subline", "params": {"channel": "m"}},
    ]
    layers = session.add_separation_stack("halftone", {"image": "photo.png"}, plates)
    assert [l.source.generator for l in layers] == ["halftone", "subline"]
    # the base params that subline doesn't declare were dropped, not passed on
    assert set(layers[1].source.params) <= set(get_source("subline").Params.model_fields)


def test_stack_serves_tonal_separation_too():
    """The reason a plate carries a params override rather than a channel:
    colour and tone separation are the same operation."""
    plates = [
        {"name": "lights", "params": {"tone_from": 0.0, "tone_to": 0.5}},
        {"name": "darks", "params": {"tone_from": 0.5, "tone_to": 1.0}},
    ]
    layers = session.add_separation_stack("halftone", {"image": "photo.png"}, plates)
    assert len(layers) == 2
    assert layers[0].source.params["tone_to"] == 0.5


def test_stack_rejects_a_generator_with_no_channel():
    with pytest.raises(ValueError, match="no channel"):
        session.add_separation_stack("polygon", {}, CMYK)
    assert len(session.project.layers) == 0


def test_stack_rejects_no_plates():
    with pytest.raises(ValueError):
        session.add_separation_stack("halftone", {"image": "photo.png"}, [])


def test_stack_failure_leaves_nothing_behind():
    """Generation happens before the checkpoint, so a bad plate must abort the
    whole separation rather than leave half a stack and an undo entry."""
    plates = CMYK[:2] + [{"name": "broken", "params": {"image": "no-such.png"}}]
    with pytest.raises(Exception):
        session.add_separation_stack("halftone", {"image": "photo.png"}, plates)
    assert len(session.project.layers) == 0


# -- misregistration -----------------------------------------------------------


def test_misregistration_zero_is_exact_identity():
    a = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK)
    placements = [(l.transform.e, l.transform.f) for l in a]
    session.undo()
    b = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK,
                                     misregistration_mm=0.0)
    assert [(l.transform.e, l.transform.f) for l in b] == placements


def test_misregistration_offsets_each_plate_within_bounds():
    layers = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK,
                                          misregistration_mm=0.5, seed=7)
    placements = {(round(l.transform.e, 9), round(l.transform.f, 9)) for l in layers}
    assert len(placements) == 4, "every plate should drift differently"
    session.undo()
    clean = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK)
    base = (clean[0].transform.e, clean[0].transform.f)
    for e, f in placements:
        assert ((e - base[0]) ** 2 + (f - base[1]) ** 2) ** 0.5 <= 0.5 + 1e-9


def test_misregistration_is_reproducible_per_seed():
    a = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK,
                                     misregistration_mm=0.5, seed=3)
    placed = [(l.transform.e, l.transform.f) for l in a]
    session.undo()
    b = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK,
                                     misregistration_mm=0.5, seed=3)
    assert [(l.transform.e, l.transform.f) for l in b] == placed
    session.undo()
    c = session.add_separation_stack("halftone", {"image": "photo.png"}, CMYK,
                                     misregistration_mm=0.5, seed=4)
    assert [(l.transform.e, l.transform.f) for l in c] != placed


# -- API -----------------------------------------------------------------------


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def test_separate_api(client):
    r = client.post("/api/layers/separate", json={
        "module": "halftone", "params": {"image": "photo.png"}, "plates": CMYK})
    assert r.status_code == 200, r.text
    assert len(r.json()["layers"]) == 4


def test_separate_api_rejects_an_empty_plate_list(client):
    r = client.post("/api/layers/separate", json={
        "module": "halftone", "params": {"image": "photo.png"}, "plates": []})
    assert r.status_code == 422


def test_separate_api_maps_a_missing_asset_to_400(client):
    r = client.post("/api/layers/separate", json={
        "module": "halftone", "params": {"image": "no-such.png"}, "plates": CMYK})
    assert r.status_code == 400


def test_separate_api_maps_an_unknown_module_to_404(client):
    r = client.post("/api/layers/separate", json={
        "module": "no-such-generator", "params": {}, "plates": CMYK})
    assert r.status_code == 404


def test_separate_api_rejects_a_bogus_channel(client):
    r = client.post("/api/layers/separate", json={
        "module": "halftone", "params": {"image": "photo.png"},
        "plates": [{"name": "puce", "params": {"channel": "puce"}}]})
    assert r.status_code == 400


# -- seed rolling --------------------------------------------------------------
# Lives here because add_separation_stack is one of the paths that used to
# land on seed 0 every time. The rule it pins is general.


def test_layer_creation_rolls_a_seed():
    """Every stochastic module starts at seed 0, so without this two layers
    of the same generator draw the identical picture — the thing that makes
    plotter output look mechanical."""
    seeds = {session.add_generated_layer("flowfield", {}).source.params["seed"]
             for _ in range(8)}
    assert len(seeds) > 1, f"every flowfield layer got the same seed: {seeds}"


def test_an_explicit_seed_is_never_overwritten():
    layer = session.add_generated_layer("flowfield", {"seed": 42})
    assert layer.source.params["seed"] == 42


def test_modules_without_a_seed_are_left_alone():
    layer = session.add_generated_layer("polygon", {"sides": 5})
    assert "seed" not in layer.source.params


def test_positional_seed_fields_are_not_rolled():
    """fast_marching_topo's seed_x/seed_y are where the wavefront starts —
    floats, not an RNG seed. Rolling them would move the picture instead of
    varying its texture, so the rule is an INTEGER field named exactly 'seed'."""
    src = get_source("fast_marching_topo")
    assert "seed" not in src.Params.model_fields
    rolled = session._rolled_seed(src, {})
    assert rolled == {}


def test_rolled_seed_respects_the_schema_bound():
    src = get_source("lineart_hatch")  # caps at 9999, not 99999
    for _ in range(200):
        assert 0 <= session._rolled_seed(src, {})["seed"] <= 9999


def test_separation_plates_share_one_seed():
    """The plates are one artwork in several inks, so they get one hand
    between them. Per-plate variation should be something you dial in, not
    something you get by accident."""
    layers = session.add_separation_stack("misremembered", {"image": "photo.png"}, CMYK)
    seeds = {l.source.params["seed"] for l in layers}
    assert len(seeds) == 1, f"plates drew with different hands: {seeds}"
