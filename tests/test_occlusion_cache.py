"""The occlusion memo must never hand back a mask that is out of date.

A stale occlusion cache is the one failure this tool cannot have: it would
draw geometry the user has already hidden, over ink that is already on the
paper. So these tests do not check the cache's internals — they check the
only thing that matters, that the CACHED resolve is identical to an
uncached one, after every mutation that can possibly move a mask.

The ground truth is ``compose.resolve_project`` called with no caches at all,
which is the same code path the pre-cache version ran.
"""

import time

import pytest

from axibridge import compose
from axibridge.compose import Affine
from axibridge.session import session


def signature(res):
    """Exact geometry, not a summary — a stale clip is often the right path
    count with the wrong points."""
    return {k: [(p.filled, [(round(x, 9), round(y, 9)) for x, y in p.points])
                for p in v]
            for k, v in res.items()}


def ground_truth():
    """Resolve with no caches whatsoever."""
    return compose.resolve_project(session.project, session.source_geometry,
                                   session.pens())


def assert_cache_is_honest(what: str):
    assert signature(session.resolved()) == signature(ground_truth()), (
        f"cached resolve diverged from an uncached one after: {what}")


@pytest.fixture()
def stack():
    """Two receivers under one filled-hexagon occluder, all overlapping."""
    low = session.add_generated_layer("lissajous", {"size": 100, "margin": 5})
    high = session.add_generated_layer("lissajous", {"size": 80, "margin": 5})
    occ = session.add_generated_layer("polygon", {"sides": 6, "radius": 30, "filled": True})
    session.update_layer(occ.id, {
        "transform": Affine(e=20, f=20).model_dump(),
        "occluder": True,
    })
    session.resolved()  # prime the cache before every mutation below
    return low, high, occ


# -- the mutations --------------------------------------------------------

def test_occluder_move_invalidates(stack):
    low, high, occ = stack
    before = signature(session.resolved())
    session.update_layer(occ.id, {"transform": Affine(e=55, f=45).model_dump()})
    assert_cache_is_honest("occluder moved")
    assert signature(session.resolved()) != before, "moving the occluder must change output"


def test_receiver_move_invalidates(stack):
    low, high, occ = stack
    before = signature(session.resolved())
    session.update_layer(low.id, {"transform": Affine(e=25, f=15).model_dump()})
    assert_cache_is_honest("receiver moved")
    assert signature(session.resolved()) != before


def test_margin_change_invalidates(stack):
    low, high, occ = stack
    before = signature(session.resolved())
    session.update_layer(occ.id, {"occlusion_margin_mm": 4.0})
    assert_cache_is_honest("occlusion margin changed")
    assert signature(session.resolved()) != before


def test_occluder_flag_toggle_invalidates(stack):
    low, high, occ = stack
    occluded = signature(session.resolved())
    session.update_layer(occ.id, {"occluder": False})
    assert_cache_is_honest("occluder turned off")
    clear = signature(session.resolved())
    assert clear != occluded
    session.update_layer(occ.id, {"occluder": True})
    assert_cache_is_honest("occluder turned back on")
    assert signature(session.resolved()) == occluded


def test_receives_occlusion_toggle_invalidates(stack):
    low, high, occ = stack
    session.update_layer(low.id, {"receives_occlusion": False})
    assert_cache_is_honest("receiver stopped receiving")
    session.update_layer(low.id, {"receives_occlusion": True})
    assert_cache_is_honest("receiver started receiving again")


def test_group_changes_invalidate(stack):
    low, high, occ = stack
    session.update_layer(occ.id, {"occlude_groups": ["A"]})
    assert_cache_is_honest("occluder scoped to group A")
    session.update_layer(low.id, {"receives_groups": ["A"]})
    assert_cache_is_honest("receiver listening to A")
    session.update_layer(low.id, {"receives_groups": ["B"]})
    assert_cache_is_honest("receiver listening to B instead")
    session.update_layer(occ.id, {"occlude_groups": ["B"]})
    assert_cache_is_honest("occluder moved to group B")


def test_pen_line_diameter_invalidates(stack):
    """A stroke-only occluder masks a band at its pen's width — a fatter pen
    is a bigger mask, with no geometry change to notice."""
    low, high, occ = stack
    stroker = session.add_generated_layer("lissajous", {"size": 90, "margin": 5})
    session.update_layer(stroker.id, {"occluder": True})
    thin = compose.Pen(id="thin", name="thin", line_diameter_mm=0.3)
    fat = compose.Pen(id="fat", name="fat", line_diameter_mm=6.0)
    session.project.pens_used = {"thin": thin, "fat": fat}
    session.update_layer(stroker.id, {"pen_id": "thin"})
    assert_cache_is_honest("stroke occluder on a thin pen")
    thin_out = signature(session.resolved())
    session.update_layer(stroker.id, {"pen_id": "fat"})
    assert_cache_is_honest("same occluder on a fat pen")
    assert signature(session.resolved()) != thin_out, "pen width must change the mask"


def test_reorder_invalidates(stack):
    low, high, occ = stack
    before = signature(session.resolved())
    session.reorder_layers([occ.id, low.id, high.id])  # occluder to the bottom
    assert_cache_is_honest("occluder reordered to the bottom")
    assert signature(session.resolved()) != before


def test_visibility_toggle_invalidates(stack):
    low, high, occ = stack
    session.update_layer(occ.id, {"visible": False})
    assert_cache_is_honest("occluder hidden")
    session.update_layer(occ.id, {"visible": True})
    assert_cache_is_honest("occluder shown again")


def test_effect_on_occluder_invalidates(stack):
    low, high, occ = stack
    before = signature(session.resolved())
    session.update_layer(occ.id, {"effects": [
        {"effect": "hatch_fill", "params": {"spacing": 3.0}, "enabled": True}]})
    assert_cache_is_honest("occluder gained a hatch fill")
    assert signature(session.resolved()) != before


def test_regenerate_invalidates(stack):
    low, high, occ = stack
    before = signature(session.resolved())
    session.regenerate_layer(occ.id, {"sides": 3, "radius": 55, "filled": True})
    assert_cache_is_honest("occluder regenerated with new params")
    assert signature(session.resolved()) != before


def test_delete_invalidates(stack):
    low, high, occ = stack
    session.delete_layer(occ.id)
    assert_cache_is_honest("occluder deleted")


def test_undo_invalidates(stack):
    low, high, occ = stack
    before = signature(session.resolved())
    session.update_layer(occ.id, {"transform": Affine(e=45, f=35).model_dump()})
    session.resolved()
    assert session.undo()
    assert_cache_is_honest("undo")
    assert signature(session.resolved()) == before


def test_region_layer_stays_honest(stack):
    """Regions rewrite the shaped geometry of everything below them every
    resolve, so they legitimately miss the cache — they must not corrupt it."""
    low, high, occ = stack
    region = session.add_generated_layer("polygon", {"sides": 4, "radius": 40, "filled": True})
    session.update_layer(region.id, {
        "region": True,
        "transform": Affine(e=10, f=10).model_dump(),
        "effects": [{"effect": "coherent_jitter", "params": {}, "enabled": True}],
    })
    session.reorder_layers([low.id, region.id, high.id, occ.id])
    assert_cache_is_honest("a region layer sits mid-stack")
    session.update_layer(region.id, {"transform": Affine(e=30, f=25).model_dump()})
    assert_cache_is_honest("the region moved")


def test_draw_flag_is_not_cached_wrong(stack):
    """``draw`` selects between the clip result and nothing — it must not be
    baked into the cached clip."""
    low, high, occ = stack
    drawn = signature(session.resolved())
    session.update_layer(low.id, {"draw": False})
    assert session.resolved()[low.id] == []
    session.update_layer(low.id, {"draw": True})
    assert signature(session.resolved()) == drawn


# -- the point of the whole exercise --------------------------------------

def test_repeat_resolve_is_cheap(stack):
    """An unchanged project must not pay for occlusion twice. Timed, because
    'it is cached' has been asserted before and been wrong."""
    low, high, occ = stack
    session.update_layer(low.id, {"effects": [
        {"effect": "hatch_fill", "params": {"spacing": 0.8, "cross": True}, "enabled": True}]})
    session.update_layer(low.id, {"transform": Affine(e=5, f=5).model_dump()})

    t0 = time.perf_counter()
    session.resolved()
    cold = time.perf_counter() - t0

    warm = min(_time_one() for _ in range(3))
    assert warm < max(cold * 0.2, 0.002), (
        f"repeat resolve cost {warm*1000:.1f} ms against a cold {cold*1000:.1f} ms "
        "— the occlusion memo is not being hit")


def _time_one() -> float:
    t0 = time.perf_counter()
    session.resolved()
    return time.perf_counter() - t0
