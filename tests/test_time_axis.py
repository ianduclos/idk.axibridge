"""A generator's time axis: which param the master timeline scrubs.

`frame` was always this mechanism; it was just hardcoded and named after
video. These tests pin the generalisation AND the fact that the old path is
unchanged, because every image generator depends on it."""

import pytest

from axibridge.compose import CanvasLayer, LayerSource
from axibridge.session import Session


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
    assert Session._effective_gen_params(lyr, master_t=1.0)["iterations"] == 8


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
