"""Acceptance checks for public hierarchy edits and resolved drawing behavior."""

import pytest

from axibridge import project_io
from axibridge.compose import Affine, CanvasLayer, EffectStep, LayerSource
from axibridge.model import Path
from axibridge.session import Session


def item(ident, kind="layer"):
    return {"kind": kind, "id": ident}


def scene(count=3):
    session = Session()
    for index in range(count):
        ident = str(index)
        session.project.layers.append(CanvasLayer(
            id=ident, name=ident, source=LayerSource(type="baked")))
        session.source_geometry[ident] = [Path(points=[(0, 0), (10, 0)])]
    return session


def points(session, ident, t=None):
    return [path.points for path in session.resolved(master_t=t).get(ident, [])]


def shifted(paths, x, y):
    return [[(px + x, py + y) for px, py in path] for path in paths]


def assert_paths_close(actual, expected):
    assert len(actual) == len(expected)
    for path, wanted in zip(actual, expected):
        assert len(path) == len(wanted)
        for point, goal in zip(path, wanted):
            assert point == pytest.approx(goal, abs=1e-5)


def test_nested_affine_visibility_and_one_undo_entry():
    session = scene()
    inner = session.create_group([item("0"), item("1")], "inner")
    outer = session.create_group([item(inner.id, "group"), item("2")], "outer")
    before = points(session, "0")
    session.transform_selection([item(outer.id, "group"), item("0")],
                                Affine(a=2, d=3, e=7, f=4))
    assert_paths_close(points(session, "0"), [[(7, 4), (27, 4)]])
    session.undo()
    assert_paths_close(points(session, "0"), before)
    session.redo()
    session.project.layer("1").visible = False
    session.update_group(outer.id, {"visible": False})
    assert not points(session, "0")
    session.update_group(outer.id, {"visible": True})
    assert_paths_close(points(session, "0"), [[(7, 4), (27, 4)]])
    assert not points(session, "1")


def test_group_scale_places_geometry_before_millimetre_effect():
    session = scene(2)
    square = [Path(points=[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)], filled=True)]
    for ident in ("0", "1"):
        session.source_geometry[ident] = square
        session.project.layer(ident).effects = [EffectStep(
            effect="contract_expand", params={"offset": 1})]
    group = session.create_group([item("0")])
    session.transform_selection([item(group.id, "group")], Affine(a=2, d=3, e=20, f=15))
    session.transform_selection([item("1")], Affine(a=2, d=3, e=20, f=15))
    assert_paths_close(points(session, "0"), points(session, "1"))


def test_complete_animate_chain_moves_together_at_multiple_frames():
    session = Session()
    original = session.add_generated_layer("polygon", {"sides": 5, "radius": 12})
    master = session.animate_layer(original.id)
    third = session.add_chain_keyframe(master.id)
    session.regenerate_layer(third.id, {"sides": 5, "radius": 24})
    frames = {t: points(session, master.id, t) for t in (0, .25, .5, .75, 1)}
    group = session.create_group([item(master.id)], "animation")
    members = [layer for layer in session.project.layers
               if layer.id == master.id or layer.animation_owner_id == master.id]
    assert len(members) == 4 and {layer.group_id for layer in members} == {group.id}
    session.transform_selection([item(group.id, "group")], Affine(e=11, f=-6))
    for t, baseline in frames.items():
        assert_paths_close(points(session, master.id, t), shifted(baseline, 11, -6))


def test_linked_tween_resolves_independent_and_common_group_ancestry():
    session = scene(2)
    session.project.layer("1").transform = Affine(e=30)
    tween = session.create_tween_layer("0", "1")
    session.set_tween_params(tween.id, {"follow_master": True})
    left = session.create_group([item("0")], "left")
    right = session.create_group([item("1")], "right")
    session.transform_selection([item(left.id, "group")], Affine(e=5))
    session.transform_selection([item(right.id, "group")], Affine(e=15))
    assert_paths_close(points(session, tween.id, 0), points(session, "0"))
    assert_paths_close(points(session, tween.id, 1), points(session, "1"))
    frames = {t: points(session, tween.id, t) for t in (0, .5, 1)}
    assert frames[0] != frames[.5] != frames[1]
    common = session.create_group([item(left.id, "group"), item(tween.id),
                                   item(right.id, "group")], "common")
    session.transform_selection([item(common.id, "group")], Affine(a=2, d=2, e=3))
    for t, baseline in frames.items():
        expected = [[(x * 2 + 3, y * 2) for x, y in path] for path in baseline]
        assert_paths_close(points(session, tween.id, t), expected)


def test_reparent_and_ungroup_keep_tween_frames_and_live_references():
    session = scene(2)
    session.project.layer("1").transform = Affine(e=30)
    tween = session.create_tween_layer("0", "1")
    session.set_tween_params(tween.id, {"follow_master": True})
    owner = session.create_group([item(tween.id)], "moving")
    destination = session.create_group([item("1")], "destination")
    session.transform_selection([item(owner.id, "group")], Affine(a=1.5, d=2, e=5))
    frames = {t: points(session, tween.id, t) for t in (0, .25, .5, .75, 1)}
    assert len({tuple(tuple(point for point in path) for path in frames[t]) for t in frames}) == 5
    session.reparent_selection([item(owner.id, "group")], destination.id)
    for t, baseline in frames.items():
        assert_paths_close(points(session, tween.id, t), baseline)
    session.ungroup(owner.id)
    for t, baseline in frames.items():
        assert_paths_close(points(session, tween.id, t), baseline)
    session.update_layer("1", {"transform": {"e": 50}})
    assert points(session, tween.id, 1) != frames[1]


def nested_links():
    session = Session()
    corners = [session.add_generated_layer("polygon", {"sides": 6 + index, "radius": radius})
               for index, radius in enumerate((10, 18, 27, 39))]
    left = session.create_tween_layer(corners[0].id, corners[1].id)
    right = session.create_tween_layer(corners[2].id, corners[3].id)
    outer = session.create_tween_layer(left.id, right.id)
    for tween in (left, right, outer):
        session.set_tween_params(tween.id, {"follow_master": True})
    session.update_layer(left.id, {"transform": Affine(a=1.2, d=.8, e=8).model_dump()})
    session.update_layer(right.id, {"transform": Affine(a=.85, d=1.3, e=26, f=5).model_dump()})
    session.update_layer(outer.id, {"transform": Affine(a=1.1, d=.9, e=3).model_dump()})
    times = (0, .25, .5, .75, 1)
    frames = {t: points(session, outer.id, t) for t in times}
    assert len({tuple(tuple(path) for path in frames[t]) for t in times}) == len(times)
    assert len({tuple(len(path) for path in frames[t]) for t in times}) > 1
    return session, corners, left, right, outer, times, frames


def test_nested_linked_tweens_share_common_affine_at_every_frame():
    session, _, _, _, outer, times, frames = nested_links()

    common = session.create_group([item(layer.id) for layer in session.project.layers], "common")
    for t in times:
        assert_paths_close(points(session, outer.id, t), frames[t])
    placement = Affine(a=1.5, d=.75, e=7, f=-4)
    session.transform_selection([item(common.id, "group")], placement)
    placed = {t: points(session, outer.id, t) for t in times}
    for t in times:
        expected = [[placement.apply(x, y) for x, y in path] for path in frames[t]]
        assert_paths_close(placed[t], expected)


def test_nested_linked_reparent_ungroup_preserves_frames_and_live_input():
    session, corners, left, right, outer, times, _ = nested_links()
    session.create_group([item(layer.id) for layer in session.project.layers], "common")
    moving = session.create_group([item(left.id)], "moving")
    destination = session.create_group([item(right.id)], "destination")
    session.transform_selection([item(destination.id, "group")], Affine(e=9, f=2))
    before_reparent = {t: points(session, outer.id, t) for t in times}
    session.reparent_selection([item(moving.id, "group")], destination.id)
    for t in times:
        assert_paths_close(points(session, outer.id, t), before_reparent[t])
    session.ungroup(moving.id)
    for t in times:
        assert_paths_close(points(session, outer.id, t), before_reparent[t])
    session.regenerate_layer(corners[0].id, {"sides": 6, "radius": 15})
    assert points(session, outer.id, 0) != before_reparent[0]


def test_nested_linked_tween_with_singular_reference_interpolation_still_draws():
    session, corners, _, _, outer, _, _ = nested_links()
    session.update_layer(corners[0].id, {"transform": Affine().model_dump()})
    session.update_layer(corners[1].id, {"transform": Affine(d=-1).model_dump()})
    before = points(session, outer.id, .5)
    assert before
    common = session.create_group([item(layer.id) for layer in session.project.layers], "common")
    session.transform_selection([item(common.id, "group")], Affine(e=5, f=3))
    assert_paths_close(points(session, outer.id, .5), shifted(before, 5, 3))


def test_unanimate_retains_placed_first_key_under_nested_group_transform():
    session = Session()
    source = session.add_generated_layer("polygon", {"sides": 5, "radius": 12})
    master = session.animate_layer(source.id)
    session.update_layer(master.id, {"transform": Affine(a=1.1, d=.85, e=5).model_dump()})
    inner = session.create_group([item(master.id)], "inner")
    outer = session.create_group([item(inner.id, "group")], "outer")
    session.transform_selection([item(inner.id, "group")], Affine(a=1.3, d=.9, e=7))
    session.transform_selection([item(outer.id, "group")], Affine(a=.8, d=1.2, f=-4))
    before = points(session, master.id, 0)
    assert before
    survivor = session.unanimate_layer(master.id)
    assert_paths_close(points(session, survivor.id), before)


def test_nested_duplicate_remaps_family_and_delete_keeps_original():
    session = Session()
    original = session.add_generated_layer("polygon", {"sides": 5, "radius": 12})
    master = session.animate_layer(original.id)
    session.add_chain_keyframe(master.id)
    sibling = session.add_generated_layer("polygon", {"sides": 5, "radius": 8})
    inner = session.create_group([item(master.id)], "family")
    outer = session.create_group([item(inner.id, "group"), item(sibling.id)], "outer")
    original_ids = {layer.id for layer in session.project.layers}
    copied = session.duplicate_selection([item(outer.id, "group")])[0]
    copied_layers = [layer for layer in session.project.layers if layer.id not in original_ids]
    copied_master = next(layer for layer in copied_layers if layer.source.type == "tween")
    refs = copied_master.source.params.get("keys") or [copied_master.source.params["a"],
                                                        copied_master.source.params["b"]]
    assert set(refs) <= {layer.id for layer in copied_layers}
    assert all(session.project.layer(ref).animation_owner_id == copied_master.id for ref in refs)
    assert points(session, copied_master.id, .5)
    session.delete_selection([item(copied["id"], "group")])
    assert {layer.id for layer in session.project.layers} == original_ids
    assert points(session, master.id, .5)


def test_cycles_and_split_animation_family_reject_without_mutation():
    session = Session()
    original = session.add_generated_layer("polygon", {"sides": 5, "radius": 12})
    master = session.animate_layer(original.id)
    params = session.project.layer(master.id).source.params
    keys = params["keys"] or [params["a"], params["b"]]
    inner = session.create_group([item(master.id)], "inner")
    outer = session.create_group([item(inner.id, "group")], "outer")
    before = session.project.model_dump()
    with pytest.raises(ValueError, match="cycle"):
        session.reparent_selection([item(outer.id, "group")], inner.id)
    with pytest.raises(ValueError, match="complete animation family"):
        session.create_group([item(keys[0])])
    assert session.project.model_dump() == before


def test_hierarchy_survives_project_save_load_and_capture_recipe(tmp_path):
    session = scene(2)
    inner = session.create_group([item("0")], "inner")
    outer = session.create_group([item(inner.id, "group"), item("1")], "outer")
    session.transform_selection([item(outer.id, "group")], Affine(e=12, f=7))
    baseline = points(session, "0")
    capture = session.capture_to_staging(kind="plot", name="frozen")
    assert [(group.id, group.parent_id) for group in capture.snapshot.groups] == [
        (inner.id, outer.id), (outer.id, None)]
    project_io.save_project(session.project, session.source_geometry, {}, tmp_path,
                            staging_documents=session.staging_documents)
    loaded, geometry, _, _, _, _ = project_io.load_project(tmp_path)
    restored = Session()
    restored.project, restored.source_geometry = loaded, geometry
    assert_paths_close(points(restored, "0"), baseline)
    assert loaded.staging[0].snapshot.groups == capture.snapshot.groups
