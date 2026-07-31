"""Interpolation (tween) layers and the perspective effect."""

import math

import pytest

from axibridge.compose import Affine
from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect
from axibridge.session import session
from axibridge.tween import (
    _NO_BLEND, _blend_geometry, compose_affine, decompose_affine, lerp_affine,
    lerp_params, map_time_curve,
)


def _pair(radius_b=30, move_b=(60.0, 25.0)):
    a = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    b = session.add_generated_layer("polygon", {"sides": 6, "radius": radius_b})
    session.update_layer(b.id, {"transform": {
        "a": 1, "b": 0, "c": 0, "d": 1, "e": move_b[0], "f": move_b[1]}})
    return a, session.project.layer(b.id)


def _approx_equal(pa, pb, tol=1e-6):
    assert len(pa) == len(pb)
    for x, y in zip(pa, pb):
        assert len(x.points) == len(y.points)
        for (x0, y0), (x1, y1) in zip(x.points, y.points):
            assert x0 == pytest.approx(x1, abs=tol)
            assert y0 == pytest.approx(y1, abs=tol)


def test_tween_endpoints_reproduce_a_and_b():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    r = session.resolved()
    session.set_tween_params(tw.id, {"t": 0.0})
    _approx_equal(session.resolved()[tw.id], session.resolved()[a.id])
    session.set_tween_params(tw.id, {"t": 1.0})
    _approx_equal(session.resolved()[tw.id], session.resolved()[b.id])


def test_tween_midpoint_is_between():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 0.5})
    r = session.resolved()
    cx = sum(x for p in r[tw.id] for x, _ in p.points) / sum(len(p.points) for p in r[tw.id])
    ca = sum(x for p in r[a.id] for x, _ in p.points) / sum(len(p.points) for p in r[a.id])
    cb = sum(x for p in r[b.id] for x, _ in p.points) / sum(len(p.points) for p in r[b.id])
    assert min(ca, cb) < cx < max(ca, cb)


def test_tween_sweep_stamps_copies():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    single = len(session.resolved()[tw.id])
    session.set_tween_params(tw.id, {"sweep": 7})
    assert len(session.resolved()[tw.id]) == single * 7


def test_tween_follows_live_edits():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 1.0})
    before = session.resolved()[tw.id]
    session.regenerate_layer(b.id, {"sides": 6, "radius": 45})
    after = session.resolved()[tw.id]
    assert [p.points for p in before] != [p.points for p in after]


def test_tween_structural_mode_via_baked_duplicate():
    a = session.add_generated_layer("polygon", {"sides": 5, "radius": 20})
    b = session.duplicate_layer(a.id)
    session.update_layer(b.id, {"transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 40, "f": 10}})
    session.consolidate_effects(b.id)  # baked: forces the pointwise-lerp branch
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 1.0})
    _approx_equal(session.resolved()[tw.id], session.resolved()[b.id])


def test_tween_rejects_incompatible_layers():
    a = session.add_generated_layer("polygon", {"sides": 5})
    b = session.add_generated_layer("lissajous", {})
    with pytest.raises(RuntimeError, match="interpolatable"):
        session.create_tween_layer(a.id, b.id)
    with pytest.raises(RuntimeError):
        session.create_tween_layer(a.id, a.id)


def test_tween_cascade_false_blocks_deleting_referenced_layer():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    with pytest.raises(RuntimeError, match="referenced"):
        session.delete_layers([a.id], cascade=False)
    session.delete_layers([a.id, tw.id], cascade=False)  # together is fine
    assert a.id not in {l.id for l in session.project.layers}


def test_cascade_delete_keyframe_a_takes_tween_and_b():
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    original_name = layer.name
    tw = session.animate_layer(layer.id)
    b_id = tw.source.params["b"]
    assert len(session.project.layers) == 3
    session._history.clear()
    deleted = session.delete_layer(layer.id)  # delete keyframe A (original id)
    assert set(deleted) == {layer.id, b_id, tw.id}
    assert len(session.project.layers) == 0
    # ONE undo restores all three with names + visibility intact
    assert session.undo()
    assert len(session.project.layers) == 3
    a, b, twr = (session.project.layer(layer.id), session.project.layer(b_id),
                 session.project.layer(tw.id))
    assert a.name == f"{original_name} ▸ A" and not a.visible
    assert b.name == f"{original_name} ▸ B" and not b.visible
    assert twr.name == original_name and twr.visible


def test_un_animate_deleting_tween_restores_keyframe_a():
    """Directly deleting an animate-created tween un-animates: keyframe A is
    RESTORED (un-hidden, un-suffixed, same id + geometry) rather than swept; B
    goes. One undo brings the whole animation back."""
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    original_name = layer.name
    a_id = layer.id
    geo = session.source_geometry[a_id]  # the exact list object A owns
    tw = session.animate_layer(layer.id)
    b_id = tw.source.params["b"]
    session._history.clear()

    deleted = session.delete_layer(tw.id)  # DIRECT tween deletion -> un-animate

    assert set(deleted) == {b_id, tw.id}      # A restored, not deleted
    assert a_id not in deleted
    survivors = [l.id for l in session.project.layers]
    assert survivors == [a_id]                # exactly the original layer
    a = session.project.layer(a_id)
    assert a.visible and a.name == original_name          # un-hidden, un-suffixed
    assert session.source_geometry[a_id] is geo           # same geometry object
    assert b_id not in {l.id for l in session.project.layers}

    assert session.undo()  # ONE undo restores tween + A + B
    assert len(session.project.layers) == 3
    assert not session.project.layer(a_id).visible
    assert session.project.layer(a_id).name == f"{original_name} ▸ A"


def test_un_animate_only_on_direct_tween_deletion():
    """Deleting keyframe A directly still cascades the whole group (the
    un-animate restore is only for a DIRECTLY targeted tween)."""
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    a_id = layer.id
    tw = session.animate_layer(layer.id)
    b_id = tw.source.params["b"]
    deleted = session.delete_layer(a_id)  # delete keyframe A directly
    assert set(deleted) == {a_id, b_id, tw.id}
    assert len(session.project.layers) == 0


def test_cascade_delete_manual_tween_keeps_visible_sources():
    a, b = _pair()  # both VISIBLE
    tw = session.create_tween_layer(a.id, b.id)
    deleted = session.delete_layer(tw.id)
    assert deleted == [tw.id]  # visible sources are never swept
    assert {a.id, b.id} <= {l.id for l in session.project.layers}


def test_cascade_spares_hidden_keyframe_referenced_by_surviving_tween():
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    tw1 = session.animate_layer(layer.id)
    a_id, b_id = tw1.source.params["a"], tw1.source.params["b"]
    tw2 = session.create_tween_layer(a_id, b_id)  # 2nd tween over the same pair
    deleted = session.delete_layer(tw1.id)
    assert deleted == [tw1.id]  # A/B still referenced by surviving tw2 -> spared
    survivors = {l.id for l in session.project.layers}
    assert {a_id, b_id, tw2.id} <= survivors


def test_multiple_tweens_over_same_pair_coexist():
    a, b = _pair()
    tw1 = session.create_tween_layer(a.id, b.id)
    tw2 = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw1.id, {"t": 0.25})
    session.set_tween_params(tw2.id, {"t": 0.75})
    r = session.resolved()
    assert r[tw1.id] and r[tw2.id]
    assert [p.points for p in r[tw1.id]] != [p.points for p in r[tw2.id]]


# -- Stage A: timeline windows -----------------------------------------------


def test_window_holds_a_before_and_b_after():
    a, b, tw = _follow_pair()  # own t = 0.5, follow_master
    session.set_tween_params(tw.id, {"window_from": 0.25, "window_to": 0.75})
    for mt in (0.0, 0.25):  # before/at window start -> A exactly
        _approx_equal(session.resolved(master_t=mt)[tw.id], session.resolved()[a.id])
    for mt in (0.75, 1.0):  # at/after window end -> B exactly
        _approx_equal(session.resolved(master_t=mt)[tw.id], session.resolved()[b.id])
    # master_t 0.5 -> local (0.5-0.25)/0.5 = 0.5 == the tween's own t=0.5 output
    _approx_equal(session.resolved(master_t=0.5)[tw.id], session.resolved()[tw.id])


def test_window_degenerate_steps_a_to_b():
    a, b, tw = _follow_pair()
    session.set_tween_params(tw.id, {"window_from": 0.5, "window_to": 0.5})
    _approx_equal(session.resolved(master_t=0.49)[tw.id], session.resolved()[a.id])
    _approx_equal(session.resolved(master_t=0.5)[tw.id], session.resolved()[b.id])
    _approx_equal(session.resolved(master_t=0.51)[tw.id], session.resolved()[b.id])


def test_window_ignored_without_follow_master():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 0.3, "window_from": 0.25, "window_to": 0.75})
    base = session.resolved()[tw.id]
    scrubbed = session.resolved(master_t=0.0)[tw.id]
    assert [p.points for p in base] == [p.points for p in scrubbed]  # windows unused


def test_cosine_pingpong_curve_goes_a_to_b_to_a():
    a, b, tw = _follow_pair()
    session.set_tween_params(tw.id, {"time_curve": "cosine_pingpong"})

    _approx_equal(session.resolved(master_t=0.0)[tw.id], session.resolved()[a.id])
    _approx_equal(session.resolved(master_t=0.5)[tw.id], session.resolved()[b.id])
    _approx_equal(session.resolved(master_t=1.0)[tw.id], session.resolved()[a.id])
    # quarter timeline maps to morph t=0.5, matching the tween's own t.
    _approx_equal(session.resolved(master_t=0.25)[tw.id], session.resolved()[tw.id])


def test_time_curve_mapping():
    assert map_time_curve(0.0, "linear") == pytest.approx(0.0)
    assert map_time_curve(1.0, "linear") == pytest.approx(1.0)
    assert map_time_curve(0.0, "cosine_pingpong") == pytest.approx(0.0)
    assert map_time_curve(0.5, "cosine_pingpong") == pytest.approx(1.0)
    assert map_time_curve(1.0, "cosine_pingpong") == pytest.approx(0.0)
    assert map_time_curve(0.5, "future_curve") == pytest.approx(0.5)


def test_time_curve_cosine_ease_is_monotonic_a_to_b():
    # cosine ease: endpoints exact, midpoint = 0.5, eased (slower near the ends)
    assert map_time_curve(0.0, "cosine") == pytest.approx(0.0)
    assert map_time_curve(1.0, "cosine") == pytest.approx(1.0)
    assert map_time_curve(0.5, "cosine") == pytest.approx(0.5)
    # ease-in: a quarter of the way through time is less than a quarter of the morph
    assert map_time_curve(0.25, "cosine") < 0.25
    assert map_time_curve(0.75, "cosine") > 0.75  # ease-out symmetric


# -- captured-geometry (shape) morph ----------------------------------------

def _pen_subpath(pts, closed=False):
    return [{"anchors": [{"x": x, "y": y, "in_handle": None, "out_handle": None}
                         for x, y in pts], "closed": closed}]


def test_blend_geometry_lerps_matching_anchor_structure():
    a = _pen_subpath([(0, 0), (10, 0)])
    b = _pen_subpath([(0, 20), (10, 20)])
    mid = _blend_geometry(a, b, 0.5)
    assert mid is not _NO_BLEND
    ys = [anchor["y"] for sp in mid for anchor in sp["anchors"]]
    assert ys == [10.0, 10.0]  # halfway between A and B
    # endpoints reproduce A / B exactly
    assert _blend_geometry(a, b, 0.0) == a
    assert _blend_geometry(a, b, 1.0) == b


def test_blend_geometry_lerps_handles_and_corner_to_curve():
    a = [{"anchors": [{"x": 0, "y": 0, "in_handle": [4, 0], "out_handle": None}], "closed": False}]
    b = [{"anchors": [{"x": 0, "y": 0, "in_handle": [6, 2], "out_handle": [8, 0]}], "closed": False}]
    mid = _blend_geometry(a, b, 0.5)
    anchor = mid[0]["anchors"][0]
    assert anchor["in_handle"] == [5.0, 1.0]         # two real handles lerp
    assert anchor["out_handle"] == [4.0, 0.0]        # None (corner) grows from [0,0]


def test_blend_geometry_steps_bool_without_blocking_the_morph():
    # a subpath's `closed` can't be half-set: it steps, but the anchors still morph
    a = _pen_subpath([(0, 0)], closed=False)
    b = _pen_subpath([(0, 20)], closed=True)
    mid = _blend_geometry(a, b, 0.6)
    assert mid is not _NO_BLEND
    assert mid[0]["closed"] is True                  # bool stepped (t >= 0.5)
    assert mid[0]["anchors"][0]["y"] == pytest.approx(12.0)  # anchor still morphed


def test_blend_geometry_refuses_mismatched_structure():
    a = _pen_subpath([(0, 0), (10, 0)])
    b = _pen_subpath([(0, 0), (10, 0), (20, 0)])  # extra anchor
    assert _blend_geometry(a, b, 0.5) is _NO_BLEND


def _pen_pair(y_b=20.0):
    a = session.add_generated_layer("pen", {"subpaths": _pen_subpath([(0, 0), (10, 0), (20, 0)])})
    b = session.add_generated_layer("pen", {"subpaths": _pen_subpath([(0, y_b), (10, y_b), (20, y_b)])})
    return a, session.project.layer(b.id)


def _mean_y(paths):
    pts = [p for path in paths for p in path.points]
    return sum(y for _, y in pts) / len(pts)


def test_pen_tween_morphs_shape_continuously_not_stepped():
    a, b = _pen_pair(y_b=20.0)
    tw = session.create_tween_layer(a.id, b.id)
    # endpoints exact
    session.set_tween_params(tw.id, {"t": 0.0})
    assert _mean_y(session.resolved()[tw.id]) == pytest.approx(0.0, abs=1e-6)
    session.set_tween_params(tw.id, {"t": 1.0})
    assert _mean_y(session.resolved()[tw.id]) == pytest.approx(20.0, abs=1e-6)
    # the whole point: t=0.4 lands PART-WAY (≈8), not stepped to A(0) or B(20)
    session.set_tween_params(tw.id, {"t": 0.4})
    assert _mean_y(session.resolved()[tw.id]) == pytest.approx(8.0, abs=1e-6)
    session.set_tween_params(tw.id, {"t": 0.6})
    assert _mean_y(session.resolved()[tw.id]) == pytest.approx(12.0, abs=1e-6)


def test_pen_tween_falls_back_to_step_on_structure_mismatch():
    a = session.add_generated_layer("pen", {"subpaths": _pen_subpath([(0, 0), (10, 0)])})
    b = session.add_generated_layer("pen", {"subpaths": _pen_subpath([(0, 20), (10, 20), (20, 20)])})
    tw = session.create_tween_layer(a.id, session.project.layer(b.id).id)
    # different anchor counts: can't morph → steps at 0.5 (A below, B at/after)
    session.set_tween_params(tw.id, {"t": 0.4})
    assert _mean_y(session.resolved()[tw.id]) == pytest.approx(0.0, abs=1e-6)   # A
    session.set_tween_params(tw.id, {"t": 0.6})
    assert _mean_y(session.resolved()[tw.id]) == pytest.approx(20.0, abs=1e-6)  # B


def test_tween_missing_ref_resolves_empty_not_crashing():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    # bypass the guard the way a hand-edited project file could
    session.project.layers = [l for l in session.project.layers if l.id != a.id]
    assert session.resolved()[tw.id] == []


def test_lerp_affine_endpoints_and_shortest_arc():
    ma = Affine(a=2, b=0, c=0, d=2, e=10, f=5)            # scale 2
    rot = math.radians(170)
    mb = Affine(a=math.cos(rot), b=math.sin(rot),
                c=-math.sin(rot), d=math.cos(rot), e=-30, f=8)
    for m, ref in ((lerp_affine(ma, mb, 0.0), ma), (lerp_affine(ma, mb, 1.0), mb)):
        for f in "abcdef":
            assert getattr(m, f) == pytest.approx(getattr(ref, f), abs=1e-9)
    # decompose/compose round-trip on a sheared matrix
    ms = Affine(a=1.2, b=0.3, c=-0.5, d=0.9, e=4, f=-2)
    back = compose_affine(*decompose_affine(ms))
    for f in "abcdef":
        assert getattr(back, f) == pytest.approx(getattr(ms, f), abs=1e-9)


def test_lerp_params_rules():
    out = lerp_params({"n": 10, "s": 2.0, "seed": 1, "on": True},
                      {"n": 20, "s": 4.0, "seed": 1, "on": False}, 0.25,
                      {"n": 0, "s": 0.0, "seed": 0, "on": False})
    assert out["n"] == 12 and out["s"] == pytest.approx(2.5)
    assert out["seed"] == 1 and out["on"] is True  # equal seeds stay constant; bool steps


def test_lerp_params_seed_per_frame():
    # differing endpoint seeds: a fresh deterministic seed per frame, no 0.5 snap
    seeds = [lerp_params({"seed": 1}, {"seed": 9}, t, {})["seed"]
             for t in (0.2, 0.4, 0.6, 0.8)]
    assert len(set(seeds)) == 4
    assert all(s not in (1, 9) for s in seeds)
    assert all(0 <= s <= 9999 for s in seeds)  # fits every module's seed bound
    # same t reproduces the same seed (preview == plot, scrub-stable)
    again = [lerp_params({"seed": 1}, {"seed": 9}, t, {})["seed"]
             for t in (0.2, 0.4, 0.6, 0.8)]
    assert seeds == again
    # endpoint fidelity: t=0 is A's seed, t=1 is B's
    assert lerp_params({"seed": 1}, {"seed": 9}, 0.0, {})["seed"] == 1
    assert lerp_params({"seed": 1}, {"seed": 9}, 1.0, {})["seed"] == 9
    # a manually zeroed seed is the "random" wildcard — hashed even at endpoints
    assert lerp_params({"seed": 0}, {"seed": 0}, 0.0, {})["seed"] not in (0,)
    assert lerp_params({"seed": 0}, {"seed": 5}, 0.0, {})["seed"] != 0
    assert lerp_params({"seed": 5}, {"seed": 0}, 1.0, {})["seed"] != 0


def test_perspective_preserves_closure_and_foreshortens():
    eff = get_effect("perspective")
    sq = Path(points=[(50, 50), (150, 50), (150, 150), (50, 150), (50, 50)], filled=True)
    [out] = eff.apply([sq], eff.Params(tilt_x=45, distance=200), EffectContext())
    assert out.filled and out.points[0] == out.points[-1]
    ys = [y for _, y in out.points]
    xs_top = [x for x, y in out.points if y == min(ys)]
    xs_bot = [x for x, y in out.points if y == max(ys)]
    # the far (top) edge is narrower than the near (bottom) edge
    assert max(xs_top) - min(xs_top) < max(xs_bot) - min(xs_bot)
    # zero tilt is a no-op
    assert eff.apply([sq], eff.Params(tilt_x=0, tilt_y=0), EffectContext()) == [sq]


def _follow_pair():
    """A follow_master tween between two same-generator layers (radius differs
    so t drives visibly different geometry)."""
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 0.5, "follow_master": True})
    return a, b, tw


def test_master_t_endpoints_match_the_tweens_own_t():
    a, b, tw = _follow_pair()
    # master_t=0 reproduces A exactly (== the tween at its own t=0); master_t=1, B
    _approx_equal(session.resolved(master_t=0.0)[tw.id], session.resolved()[a.id])
    _approx_equal(session.resolved(master_t=1.0)[tw.id], session.resolved()[b.id])
    ends = [session.resolved(master_t=t)[tw.id] for t in (0.0, 1.0)]
    assert [p.points for p in ends[0]] != [p.points for p in ends[1]]


def test_master_t_clamped_out_of_range():
    a, b, tw = _follow_pair()
    _approx_equal(session.resolved(master_t=-2.0)[tw.id], session.resolved(master_t=0.0)[tw.id])
    _approx_equal(session.resolved(master_t=5.0)[tw.id], session.resolved(master_t=1.0)[tw.id])


def test_master_t_ignored_without_follow_master():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 0.3})  # follow_master defaults False
    base = session.resolved()[tw.id]
    scrubbed = session.resolved(master_t=1.0)[tw.id]
    assert [p.points for p in base] == [p.points for p in scrubbed]  # byte-identical


def test_scrub_leaves_history_and_params_untouched():
    a, b, tw = _follow_pair()
    hist_before = len(session._history)
    params_before = dict(session.project.layer(tw.id).source.params)
    session.resolved(master_t=0.2)
    session.resolved(master_t=0.8)
    assert len(session._history) == hist_before        # no checkpoint on scrub
    after = session.project.layer(tw.id).source.params
    assert after == params_before                      # stored params byte-identical
    assert after["t"] == 0.5                            # the tween's own t is untouched


def test_master_t_cache_invalidates_then_hits():
    a, b, tw = _follow_pair()
    session.resolved(master_t=0.2)
    g_low = session.source_geometry[tw.id]
    session.resolved(master_t=0.8)
    g_high = session.source_geometry[tw.id]
    # a different master_t invalidates the tween cache -> new geometry
    assert [p.points for p in g_low] != [p.points for p in g_high]
    # resolving again at the same master_t hits the cache: same list object, no recompute
    session.resolved(master_t=0.8)
    assert session.source_geometry[tw.id] is g_high


def test_animate_layer_wires_up_a_b_tween():
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    original_name = layer.name
    pre_geo = session.resolved()[layer.id]  # captured while the layer is still visible
    session._history.clear()  # isolate the checkpoint count from the history maxlen cap
    hist_before = len(session._history)

    tw = session.animate_layer(layer.id)

    assert len(session._history) == hist_before + 1  # exactly one undo step
    assert len(session.project.layers) == 3
    a = session.project.layer(layer.id)  # original id, renamed + hidden
    p = tw.source.params
    b = session.project.layer(p["b"])

    assert a.name == f"{original_name} ▸ A" and not a.visible
    assert b.id != a.id and b.name == f"{original_name} ▸ B" and not b.visible
    assert tw.source.type == "tween" and tw.visible
    assert tw.name == original_name
    assert p["a"] == a.id and p["b"] == b.id and p["follow_master"] is True

    r = session.resolved()
    assert r[tw.id]  # tween resolves non-empty
    # endpoint fidelity: master_t=0 reproduces the pre-animate geometry exactly
    _approx_equal(session.resolved(master_t=0.0)[tw.id], pre_geo)

    assert session.undo()  # single undo restores the original single-layer state
    assert len(session.project.layers) == 1
    restored = session.project.layer(layer.id)
    assert restored.name == original_name and restored.visible


def test_animate_parent_transform_moves_hidden_keyframes():
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    tw = session.animate_layer(layer.id)
    p = tw.source.params
    a = session.project.layer(p["a"])
    b = session.project.layer(p["b"])
    before = session.resolved()[tw.id]

    session.update_layer(tw.id, {"transform": Affine(e=20, f=5).model_dump()})

    tw_after = session.project.layer(tw.id)
    a_after = session.project.layer(a.id)
    b_after = session.project.layer(b.id)
    assert tw_after.transform == Affine()
    assert (a_after.transform.e, a_after.transform.f) == pytest.approx((20, 5))
    assert (b_after.transform.e, b_after.transform.f) == pytest.approx((20, 5))
    after = session.resolved()[tw.id]
    assert after[0].points[0][0] == pytest.approx(before[0].points[0][0] + 20)
    assert after[0].points[0][1] == pytest.approx(before[0].points[0][1] + 5)


def test_animate_layer_refuses_a_tween():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    with pytest.raises(RuntimeError):
        session.animate_layer(tw.id)


def test_explode_tween_creates_layer_per_step():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"sweep": 5})
    per_step = len(session.resolved()[tw.id]) // 5
    created = session.explode_tween(tw.id)
    assert len(created) == 5
    assert all(l.source.type == "baked" for l in created)
    assert not session.project.layer(tw.id).visible  # tween kept, hidden
    r = session.resolved()
    assert all(len(r[l.id]) == per_step for l in created)
    assert session.undo()  # one step undoes the whole explode
    assert created[0].id not in {l.id for l in session.project.layers}


# -- region x tween interaction ----------------------------------------------
# ARCHITECTURE.md claims "since regions are ordinary layers, they transform,
# tween, and follow the master timeline for free" — these two tests actually
# exercise that claim rather than trusting the docstring (nothing else in the
# suite combines the two features).


def test_region_flag_on_a_tween_layer_shapes_layers_below():
    """A tween layer with region=True should mask/effect layers below it in
    z-order exactly like an ordinary region layer — the tween materializes
    A/B into source_geometry same as any other resolve, so the region pass
    (which only looks at CanvasLayer.region + source_geometry) shouldn't
    care that the source happens to be a live interpolation."""
    victim = session.add_generated_layer("polygon", {"sides": 6, "radius": 5})
    session.update_layer(victim.id, {"transform": {
        "a": 1, "b": 0, "c": 0, "d": 1, "e": 55.0, "f": 55.0}})  # centered inside the region below
    a = session.add_generated_layer("polygon", {"sides": 6, "radius": 60})
    b = session.add_generated_layer("polygon", {"sides": 6, "radius": 60})  # identical to A: deterministic silhouette at any t
    tw = session.create_tween_layer(a.id, b.id)  # appended last -> above victim in z-order
    session.update_layer(tw.id, {
        "effects": [{"effect": "multipass", "enabled": True, "params": {"count": 3}}],
    })

    before = len(session.resolved()[victim.id][0].points)  # region still False (default)
    session.update_layer(tw.id, {"region": True})
    after_with_region = len(session.resolved()[victim.id][0].points)
    session.update_layer(tw.id, {"region": False})
    after_without_region = len(session.resolved()[victim.id][0].points)

    assert after_with_region > before        # region=True shapes the layer below
    assert after_without_region == before    # turning it back off releases it


def test_tween_endpoints_can_themselves_be_region_layers():
    """Marking A and/or B as region=True is orthogonal to tweening them —
    materialize() only reads source.type/params, never .region — so this
    must resolve cleanly. A/B, being regions, still never draw themselves."""
    a, b = _pair()
    session.update_layer(a.id, {"region": True})
    session.update_layer(b.id, {"region": True})
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 0.5})

    r = session.resolved()
    assert r[a.id] == [] and r[b.id] == []  # region endpoints never draw on their own
    assert r[tw.id]                          # the tween itself still resolves non-empty


def test_deleting_the_whole_group_explicitly_deletes_everything():
    """Selecting tween + BOTH keyframes and deleting must honour the explicit
    ask — no un-animate resurrection of a directly-targeted keyframe."""
    a = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    tw = session.animate_layer(a.id)
    b_id = tw.source.params["b"]
    deleted = session.delete_layers([tw.id, a.id, b_id])
    assert set(deleted) == {tw.id, a.id, b_id}
    assert session.project.layers == []


# -- nested tweens: the bilinear (time x sweep) morph -------------------------
#
# X and Y are each their own tween (Xa->Xb, Ya->Yb); a third tween sweeps
# between X and Y. Same generator throughout (polygon 'radius'), so a stamp at
# (master t, sweep s) is a bilinear blend of the four corner radii. Hexagon
# width scales linearly with radius, so width is a faithful readout of radius.


def _hex(radius):
    return session.add_generated_layer("polygon", {"sides": 6, "radius": radius})


def _width(paths):
    xs = [x for p in paths for x, _ in p.points]
    return max(xs) - min(xs)


def _nested(xa=10, xb=20, ya=30, yb=40):
    """Return (X, Y, O) where X=tween(xa,xb), Y=tween(ya,yb), O=tween(X,Y)."""
    x = session.create_tween_layer(_hex(xa).id, _hex(xb).id)
    y = session.create_tween_layer(_hex(ya).id, _hex(yb).id)
    o = session.create_tween_layer(x.id, y.id)
    return x, y, o


def test_nested_tween_creation_is_allowed_same_generator():
    x, y, o = _nested()
    assert o.source.type == "tween"
    assert session.resolved()[o.id]  # non-empty, no crash


def test_nested_tween_of_different_generators_refused():
    x = session.create_tween_layer(
        session.add_generated_layer("polygon", {"sides": 5}).id,
        session.add_generated_layer("polygon", {"sides": 6}).id)
    y = session.create_tween_layer(
        session.add_generated_layer("lissajous", {}).id,
        session.add_generated_layer("lissajous", {}).id)
    with pytest.raises(RuntimeError, match="same generator"):
        session.create_tween_layer(x.id, y.id)


def test_nested_endpoints_reproduce_inner_tweens():
    """O at t=0 reproduces X's morph; O at t=1 reproduces Y's morph, for any
    master value (the inner tweens are static here, follow_master off)."""
    x, y, o = _nested()
    session.set_tween_params(o.id, {"t": 0.0})
    _approx_equal(session.resolved()[o.id], session.resolved()[x.id])
    session.set_tween_params(o.id, {"t": 1.0})
    _approx_equal(session.resolved()[o.id], session.resolved()[y.id])


def test_nested_sweep_stamps_ordered_bilinear():
    """A sweep across X(0)->Y(0): 4 stamps whose radii march monotonically from
    just above Xa(10) toward Ya(30) — a genuine parameter interpolation, not a
    step at 0.5."""
    x, y, o = _nested()
    session.set_tween_params(x.id, {"t": 0.0})
    session.set_tween_params(y.id, {"t": 0.0})
    session.set_tween_params(o.id, {"sweep": 4})
    r = session.resolved()[o.id]
    single = len(session.resolved()[x.id])
    assert len(r) == single * 4
    widths = [_width(r[i * single:(i + 1) * single]) for i in range(4)]
    assert widths == sorted(widths)          # monotonic across the sweep
    assert widths[0] != pytest.approx(widths[-1])  # actually spread, not stepped


def test_nested_master_timeline_drives_inner_tweens():
    """The two-axis morph: with the inner tweens on follow_master, scrubbing the
    master moves X(t) and Y(t), so the outer sweep's stamps get wider over time
    (Xa..Ya at t=0 -> Xb..Yb at t=1)."""
    x, y, o = _nested()
    session.set_tween_params(x.id, {"follow_master": True})
    session.set_tween_params(y.id, {"follow_master": True})
    session.set_tween_params(o.id, {"sweep": 4})

    total_at0 = _width(session.resolved(master_t=0.0)[o.id])
    total_at1 = _width(session.resolved(master_t=1.0)[o.id])
    # widest stamp at t=1 draws from Yb(40) > widest at t=0 from Ya(30)
    assert total_at1 > total_at0


def test_nested_follows_live_grandchild_edits():
    """Editing a grandchild (an inner tween's endpoint) must update the outer
    tween — the dependency-ordered materialise keeps the cache honest."""
    x, y, o = _nested()
    session.set_tween_params(o.id, {"t": 1.0})  # O reproduces Y
    before = session.resolved()[o.id]
    yb_id = y.source.params["b"]
    session.regenerate_layer(yb_id, {"sides": 6, "radius": 80})
    after = session.resolved()[o.id]
    assert [p.points for p in before] != [p.points for p in after]
