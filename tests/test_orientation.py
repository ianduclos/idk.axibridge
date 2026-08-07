"""Orientation coherence, option B: orientation is a LAYER property.

Three rounds of "mostly fixed" failed because participation was opt-in per
generator — a new module that forgot to tag a rotation param was silently
wrong in portrait, and `text`/`glyphgram` had no rotation param to tag at
all. So the declaration is now mandatory on `SourceModule.orientation`, the
correction happens once in `Session._placement_transform`, and the guard
below fails on any source that declares nothing.

Ian's acceptance, in his words: *"stuff appears in the position I'm facing
when I insert it — I shouldn't have to think about this."*
"""

import pytest

from axibridge.compose import BED_HEIGHT
from axibridge.registry import sources
from axibridge.session import session

DECLARED = {"none", "param", "geometry"}


def displayed(points):
    """Machine mm -> what the canvas actually draws in portrait.

    `canvas.js` wraps the bed in `translate(H 0) rotate(90)`, i.e.
    (x, y) -> (H - y, x). This is the whole reason the bug exists, so the
    tests measure through it rather than trusting a transform's numbers."""
    return [(BED_HEIGHT - y, x) for x, y in points]


def span(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (max(xs) - min(xs), max(ys) - min(ys))


def layer_points(layer):
    from axibridge import compose

    return [pt for path in compose.transform_paths(
        session.source_geometry[layer.id], layer.transform) for pt in path.points]


# -- the guard ------------------------------------------------------------

def test_every_source_declares_its_orientation():
    """THE regression guard. A new source module that says nothing about
    orientation fails here — that absence is what made this bug recur three
    times. Pick one of: "none" (no dominant axis), "param" (a tagged rotation
    param already handles it), "geometry" (the layer transform should)."""
    undeclared = sorted(m.id for m in sources().values()
                        if getattr(m, "orientation", None) not in DECLARED)
    assert not undeclared, (
        f"source modules with no orientation declaration: {undeclared}. "
        "Add `orientation = \"none\" | \"param\" | \"geometry\"` to the class — "
        "see SourceModule.orientation for what each one means.")


def test_param_sources_actually_have_a_tagged_rotation_param():
    """"param" is a promise that the display layer already handles it. If the
    tag is missing the promise is empty and the module is silently wrong —
    exactly the failure mode this pass exists to end."""
    missing = []
    for mod in sources().values():
        if getattr(mod, "orientation", None) != "param":
            continue
        props = mod.Params.model_json_schema().get("properties", {})
        if not any(p.get("viewRotate") or p.get("viewAngle") or p.get("viewOrient")
                   for p in props.values()):
            missing.append(mod.id)
    assert not missing, (
        f"sources claiming orientation='param' with no viewRotate/viewAngle/"
        f"viewOrient-tagged field: {missing}")


# -- the behaviour --------------------------------------------------------

@pytest.mark.parametrize("module,params", [
    ("text", {"text": "axibridge", "size": 12}),
    ("glyphgram", {"text": "axibridge", "size": 12}),
    ("rectangle", {"width": 120, "height": 40}),
    ("grid", {"width": 160, "height": 80, "cells_x": 4, "cells_y": 2}),
])
def test_oriented_output_reads_the_same_in_both_views(module, params):
    """The acceptance criterion: what you see when you insert a layer in
    portrait has the same dominant axis as in landscape."""
    session.project.view = "landscape"
    flat = layer_points(session.add_generated_layer(module, params))
    lw, lh = span(flat)  # landscape displays machine coords unrotated
    assert lw > lh, f"{module} should be wider than tall to begin with"

    session.project.view = "portrait"
    turned = layer_points(session.add_generated_layer(module, params))
    pw, ph = span(displayed(turned))
    assert pw > ph, (
        f"{module} reads {pw:.0f}x{ph:.0f} mm on a portrait sheet but "
        f"{lw:.0f}x{lh:.0f} mm on a landscape one — it arrived turned")
    assert pw == pytest.approx(lw) and ph == pytest.approx(lh)


def test_oriented_layer_lands_on_the_bed():
    """Turning a wide shape about its own centre can push it off the sheet;
    the placement transform slides it back."""
    session.project.view = "portrait"
    layer = session.add_generated_layer("grid", {"width": 200, "height": 150,
                                                 "cells_x": 4, "cells_y": 3})
    xs = [x for x, _ in layer_points(layer)]
    ys = [y for _, y in layer_points(layer)]
    assert min(xs) >= -0.001 and max(xs) <= 300.001
    assert min(ys) >= -0.001 and max(ys) <= BED_HEIGHT + 0.001


def test_param_and_none_sources_are_not_turned_as_well():
    """A source whose rotation param is remapped by viewmap.js must NOT also
    get the layer's quarter-turn, or portrait corrects twice and lands back
    where it started, rotated the wrong way."""
    session.project.view = "portrait"
    for module, params in [("polygon", {"sides": 6, "radius": 20}),
                           ("lissajous", {"size": 80, "margin": 5}),
                           ("two_hands", {"rounds": 2, "size": 60})]:
        layer = session.add_generated_layer(module, params)
        t = layer.transform
        assert (t.a, t.b, t.c, t.d) == (1.0, 0.0, 0.0, 1.0), (
            f"{module} declares orientation='none' but was rotated")


def test_landscape_never_rotates_anything():
    session.project.view = "landscape"
    for module, params in [("text", {"text": "hello", "size": 12}),
                           ("rectangle", {"width": 60, "height": 30}),
                           ("grid", {"width": 100, "height": 60})]:
        t = session.add_generated_layer(module, params).transform
        assert (t.a, t.b, t.c, t.d, t.e, t.f) == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def test_resolve_is_still_view_independent():
    """The correction is baked into the stored transform at creation. Toggling
    the view afterwards must still change nothing about the geometry — view
    rotation stays display-only (the guarantee tests/test_view_coherence.py
    locks at the API level)."""
    session.project.view = "portrait"
    layer = session.add_generated_layer("text", {"text": "axibridge", "size": 12})
    before = [p.points for p in session.resolved()[layer.id]]
    session.project.view = "landscape"
    assert [p.points for p in session.resolved()[layer.id]] == before
