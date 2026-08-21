"""A generator's time axis: which param the master timeline scrubs.

`frame` was always this mechanism; it was just hardcoded and named after
video. These tests pin the generalisation AND the fact that the old path is
unchanged, because every image generator depends on it."""

from axibridge.compose import CanvasLayer, LayerSource
from axibridge.session import Session, session


def layer(generator: str, params: dict, **kw) -> CanvasLayer:
    return CanvasLayer(
        source=LayerSource(type="generator", generator=generator, params=params), **kw)


def test_an_undeclared_generator_has_no_time_axis():
    assert Session.time_axis("polygon") is None


def test_a_generator_with_a_frame_field_keeps_the_old_axis_without_declaring_it():
    """No migration: every image generator predates the declaration and must
    keep working whether or not anyone remembers to add one."""
    assert Session.time_axis("image_threshold") == "frame"


def test_grammar_declares_its_iteration_count_as_time():
    assert Session.time_axis("grammar") == "iterations"


def test_master_t_maps_onto_the_axis_own_bounds():
    """master_t is 0..1; the axis is whatever it is. Halfway through the
    timeline is halfway through the process."""
    lyr = layer("grammar", {"iterations": 1}, frame_follow=True)
    got = Session._effective_gen_params(lyr, master_t=0.5)
    # iterations is ge=1 le=8, and 1 + 0.5*(8-1) = 4.5 -> 4 (int field)
    assert got["iterations"] == 4


def test_an_integer_axis_is_rounded_not_handed_a_float():
    """Pydantic v2 REJECTS 4.5 for an int field rather than truncating it, so
    an unrounded fold would 422 on a scrub."""
    lyr = layer("grammar", {"iterations": 1}, frame_follow=True)
    for t in (0.0, 0.13, 0.5, 0.99, 1.0):
        got = Session._effective_gen_params(lyr, master_t=t)
        assert isinstance(got["iterations"], int)
        assert 1 <= got["iterations"] <= 8


def test_the_fold_never_leaves_the_axis_bounds():
    lyr = layer("grammar", {"iterations": 8}, frame_follow=True)
    got = Session._effective_gen_params(lyr, master_t=1.0)["iterations"]
    # `== 8` alone is satisfied by the float 8.0 too — that's exactly the
    # clamp-after-round bug this pins (min(8.0, max(1.0, 8)) widens an int
    # back to float). Assert the type, not just the value.
    assert got == 8 and type(got) is int


def test_a_frame_axis_is_byte_identical_to_the_old_behaviour():
    """frame is ge=0 le=1, so normalising against its own bounds is the
    identity — the old hardcoded path is the special case, not a parallel one."""
    lyr = layer("image_threshold", {"image": "x.png", "frame": 0.25},
                frame_follow=True)
    assert Session._effective_gen_params(lyr, master_t=0.5)["frame"] == 0.75


def test_the_stored_params_are_never_mutated():
    params = {"iterations": 2}
    lyr = layer("grammar", params, frame_follow=True)
    Session._effective_gen_params(lyr, master_t=1.0)
    assert params == {"iterations": 2}


# -- the generalisation reaching every caller, not just _effective_gen_params -

def _pts(paths):
    return [p.points for p in paths]


def test_a_frame_offset_change_on_a_non_frame_axis_regenerates():
    """update_layer's regen gate must recognise ANY declared time axis, not
    just a literal ``frame`` field — otherwise a grammar layer's frame_offset
    is stored but the geometry never resamples."""
    lyr = session.add_generated_layer("grammar", {"iterations": 1})
    before = _pts(session.resolved()[lyr.id])
    session.update_layer(lyr.id, {"frame_offset": 1.0})
    after = _pts(session.resolved()[lyr.id])
    assert before != after


def test_tween_folds_frame_offset_through_a_non_frame_axis():
    """The tween A/B parameter blend must fold frame_offset through
    ``fold_time_axis`` too, not a ``frame``-only hardcode — otherwise a
    grammar layer's frame_offset never plays through a tween at all, even
    though the per-layer path (above) already handles it."""
    # A fixed, equal, NONZERO seed on both sides: lerp_params treats an equal
    # zero seed as the "random" wildcard and re-hashes it per t regardless of
    # anything else, which would make t=0 and t=1 differ for a reason that
    # has nothing to do with the axis fold under test.
    a = session.add_generated_layer("grammar", {"iterations": 1, "seed": 7})
    b = session.add_generated_layer("grammar", {"iterations": 1, "seed": 7})
    session.update_layer(b.id, {"frame_offset": 1.0})  # same params, only offset differs
    tw = session.create_tween_layer(a.id, b.id)

    session.set_tween_params(tw.id, {"t": 0.0})
    at_t0 = _pts(session.resolved()[tw.id])
    session.set_tween_params(tw.id, {"t": 1.0})
    at_t1 = _pts(session.resolved()[tw.id])
    assert at_t0 != at_t1
