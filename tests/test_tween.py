"""Interpolation (tween) layers and the perspective effect."""

import math

import pytest

from axibridge.compose import Affine
from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect
from axibridge.session import session
from axibridge.tween import compose_affine, decompose_affine, lerp_affine, lerp_params


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


def test_cascade_delete_tween_takes_hidden_keyframes():
    layer = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    a_id = layer.id
    tw = session.animate_layer(layer.id)
    b_id = tw.source.params["b"]
    deleted = session.delete_layer(tw.id)
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
                      {"n": 20, "s": 4.0, "seed": 9, "on": False}, 0.25,
                      {"n": 0, "s": 0.0, "seed": 0, "on": False})
    assert out["n"] == 12 and out["s"] == pytest.approx(2.5)
    assert out["seed"] == 1 and out["on"] is True  # step, not blend
    assert lerp_params({"seed": 1}, {"seed": 9}, 0.9, {"seed": 0})["seed"] == 9


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


# -- Stage 4: contact-sheet bake ---------------------------------------------


def _bbox(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), max(xs), min(ys), max(ys)


def test_bake_contact_sheet_layer_count_and_within_bed():
    from axibridge import compose

    a, b, tw = _follow_pair()
    created = session.bake_contact_sheet(cols=2, rows=2, frames=4, margin_mm=5.0)
    assert len(created) == 4
    assert all(l.source.type == "baked" for l in created)
    assert all(l.visible for l in created)
    # previously-visible layers (a, b, tw) are hidden — the bake replaces them
    assert not session.project.layer(a.id).visible
    assert not session.project.layer(b.id).visible
    assert not session.project.layer(tw.id).visible
    for l in created:
        for p in session.source_geometry[l.id]:
            for x, y in p.points:
                assert 0.0 <= x <= compose.BED_WIDTH
                assert 0.0 <= y <= compose.BED_HEIGHT


def test_bake_contact_sheet_cells_disjoint_and_no_size_jitter():
    a, b, tw = _follow_pair()
    session.update_layer(b.id, {"transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 150, "f": 100}})
    created = session.bake_contact_sheet(cols=3, rows=1, frames=3, margin_mm=5.0)
    boxes = [_bbox([pt for p in session.source_geometry[l.id] for pt in p.points]) for l in created]
    # adjacent cells' bounding boxes don't overlap on x (margin > 0 guarantees a gap)
    for (x0a, x1a, _, _), (x0b, x1b, _, _) in zip(boxes, boxes[1:]):
        assert x1a < x0b
    # shared scale: every frame's baked bbox is the same size (no per-frame jitter)
    sizes = [(round(x1 - x0, 6), round(y1 - y0, 6)) for x0, x1, y0, y1 in boxes]
    assert len(set(sizes)) == 1


def test_bake_contact_sheet_one_undo_restores_prior_state():
    a, b, tw = _follow_pair()
    layers_before = [l.id for l in session.project.layers]
    session._history.clear()  # isolate the checkpoint count from the history maxlen cap
    hist_before = len(session._history)
    session.bake_contact_sheet(cols=2, rows=2, frames=3, margin_mm=5.0)
    assert len(session._history) == hist_before + 1  # exactly one undo step
    assert session.undo()
    assert [l.id for l in session.project.layers] == layers_before
    assert session.project.layer(tw.id).visible


def test_bake_contact_sheet_bounds_validation():
    a, b, tw = _follow_pair()
    with pytest.raises(ValueError):
        session.bake_contact_sheet(cols=0, rows=2, frames=2, margin_mm=5.0)
    with pytest.raises(ValueError):
        session.bake_contact_sheet(cols=13, rows=2, frames=2, margin_mm=5.0)
    with pytest.raises(ValueError):
        session.bake_contact_sheet(cols=2, rows=2, frames=1, margin_mm=5.0)  # < 2
    with pytest.raises(ValueError):
        session.bake_contact_sheet(cols=2, rows=2, frames=5, margin_mm=5.0)  # > cols*rows
    with pytest.raises(ValueError):
        session.bake_contact_sheet(cols=2, rows=2, frames=2, margin_mm=31.0)
    with pytest.raises(ValueError):
        session.bake_contact_sheet(cols=2, rows=2, frames=2, margin_mm=5.0, t_from=-0.1)
