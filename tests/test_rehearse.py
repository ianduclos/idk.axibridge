"""Pentimento: several moments of one process, on one sheet, in one undo step.

Pass 1's §2 has been open since July waiting for a time axis to point real
sweep machinery at. ``Session.rehearse_layer`` closes it by generating N
ordinary generator layers, each the same generator at a different point on
its declared time axis — nothing baked, nothing tweened, and (per Task 3's
trajectory cache, which excludes the axis from its key) one process run
serves every moment."""

import pytest

from axibridge.session import session


# The session is a module-level SINGLETON, and every session test in this repo
# uses it directly (see tests/test_tween.py). `AXIBRIDGE_CONFIG_DIR` in
# tests/conftest.py isolates the machine-level stores; `fresh_session` (also
# in conftest.py) resets the project + history before every test.


def venation_layer(session):
    return session.add_generated_layer(
        "venation", {"steps": 200, "attractors": 200, "seed": 4})


def test_rehearsing_produces_one_layer_per_moment():
    layer = venation_layer(session)
    out = session.rehearse_layer(layer.id, moments=4)
    assert len(out) == 4


def test_each_moment_contains_the_one_before_it():
    """Accumulative growth, so the rehearsal is a nesting — which is exactly
    what makes pencil-under-ink read as rehearsal rather than as four
    unrelated drawings. ``out`` comes back in ascending-axis-value order, so
    the point counts of the resolved geometry must be non-decreasing."""
    layer = venation_layer(session)
    out = session.rehearse_layer(layer.id, moments=4)
    resolved = session.resolved()
    counts = [sum(len(p.points) for p in resolved[l.id]) for l in out]
    assert counts == sorted(counts)
    assert counts[-1] > counts[0]  # the sweep must actually cover the axis


def test_rehearsing_is_one_undo_step():
    """Exactly ONE call to undo() must fully reverse the rehearsal — not
    "the layer count eventually settles after undoing some number of times".
    A multi-checkpoint implementation (e.g. one that composes several other
    checkpointing session methods) would need more than one undo() here."""
    layer = venation_layer(session)
    before = len(session.project.layers)
    out = session.rehearse_layer(layer.id, moments=5)
    assert len(out) == 5
    assert len(session.project.layers) == before + 5
    session.undo()
    assert len(session.project.layers) == before
    assert session.project.layer(layer.id) is not None  # original untouched


def test_a_layer_with_no_time_axis_cannot_be_rehearsed():
    layer = session.add_generated_layer("polygon", {"sides": 5})
    with pytest.raises(Exception, match="time axis"):
        session.rehearse_layer(layer.id, moments=3)


def test_moments_inherit_the_effect_stack():
    """A process read through ``freehand`` must rehearse in the same hand —
    each moment's effect stack must match the original layer's, not come
    back empty."""
    layer = venation_layer(session)
    session.update_layer(layer.id, {"effects": [
        {"effect": "freehand", "params": {}, "enabled": True}]})
    out = session.rehearse_layer(layer.id, moments=3)
    for moment in out:
        assert [e.effect for e in moment.effects] == ["freehand"]
        assert moment.effects[0].enabled is True


def test_moments_inherit_effects_by_copy_not_by_reference():
    """Editing a moment's effect stack after the fact must not reach back
    into the original layer's — ``model_copy(deep=True)``, not aliasing."""
    layer = venation_layer(session)
    session.update_layer(layer.id, {"effects": [
        {"effect": "freehand", "params": {"seed": 1}, "enabled": True}]})
    out = session.rehearse_layer(layer.id, moments=2)
    out[0].effects[0].params["seed"] = 999
    assert session.project.layer(layer.id).effects[0].params["seed"] == 1


def test_moments_do_not_inherit_pen_occluder_or_region():
    """The pen is precisely what you want to differ (pencil under ink), and
    occluder/region are layer ROLES rather than appearance — inheriting them
    would make every moment clip the layers below it."""
    layer = venation_layer(session)
    session.update_layer(layer.id, {
        "pen_id": "some-pen",
        "occluder": True,
        "region": True,
    })
    out = session.rehearse_layer(layer.id, moments=3)
    for moment in out:
        assert moment.pen_id is None
        assert moment.occluder is False
        assert moment.region is False
