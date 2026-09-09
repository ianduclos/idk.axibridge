"""Animation ownership is independent of names, visibility and flat ordering."""
import pytest
from axibridge.compose import Project
from axibridge.session import session


def family(n=2):
    a = session.add_generated_layer('polygon', {'radius': 20, 'sides': 5})
    tw = session.animate_layer(a.id)
    for _ in range(n-2):
        session.add_chain_keyframe(tw.id)
    return tw, session._chain_keys(tw)


def test_child_delete_and_single_survivor_undo():
    tw, keys = family(3)
    session.update_layer(tw.id, {'occluder': True, 'occlusion_margin_mm': 2})
    session.delete_layer(keys[1])
    assert session._chain_keys(session.project.layer(tw.id)) == [keys[0], keys[2]]
    session.delete_layer(keys[0])
    assert [l.id for l in session.project.layers] == [keys[2]]
    survivor = session.project.layer(keys[2])
    assert survivor.animation_owner_id is None and survivor.visible
    assert survivor.occluder and survivor.occlusion_margin_mm == 2
    session.undo()
    assert session._chain_keys(session.project.layer(tw.id)) == [keys[0], keys[2]]
    session.redo()
    assert [l.id for l in session.project.layers] == [keys[2]]


def test_master_delete_and_explicit_unanimate():
    tw, keys = family()
    assert set(session.delete_layer(tw.id)) == {tw.id, *keys}
    assert not session.project.layers
    session.undo()
    result = session.unanimate_layer(tw.id)
    assert result.id == keys[0] and result.visible
    assert result.animation_owner_id is None


def test_family_order_ownership_and_copy():
    tw, keys = family(3)
    assert all(session.project.layer(k).animation_owner_id == tw.id for k in keys)
    session.update_layer(keys[0], {'name': 'renamed'})
    other = session.add_generated_layer('polygon', {'radius': 3})
    session.reorder_layers([keys[2], other.id, keys[1], keys[0], tw.id])
    assert [l.id for l in session.project.layers] == [other.id, *reversed(keys), tw.id]
    duplicate = session.duplicate_layer(tw.id)
    copied = session._chain_keys(duplicate)
    assert set(copied).isdisjoint(keys)
    assert all(session.project.layer(k).animation_owner_id == duplicate.id for k in copied)
    session.delete_layer(duplicate.id)
    assert session._chain_keys(session.project.layer(tw.id)) == keys


def test_legacy_adoption_and_roundtrip():
    tw, keys = family()
    data = session.project.model_dump()
    for l in data['layers']:
        l.pop('animation_owner_id', None)
    restored = Project.model_validate(data)
    assert all(restored.layer(k).animation_owner_id == tw.id for k in keys)
    assert Project.model_validate_json(restored.model_dump_json()) == restored
    data['layers'][0]['visible'] = True
    manual = Project.model_validate(data)
    assert all(l.animation_owner_id is None for l in manual.layers)


def test_owned_child_cannot_become_independent_or_control_mask():
    tw, keys = family()
    with pytest.raises((ValueError, RuntimeError)):
        session.update_layer(keys[0], {'visible': True})
    with pytest.raises((ValueError, RuntimeError)):
        session.update_layer(keys[0], {'occluder': True})
    with pytest.raises((ValueError, RuntimeError)):
        session.create_tween_layer(*keys)


def test_master_masking_uses_current_frame_and_survives_reload(tmp_path):
    from axibridge import project_io
    lower = session.add_generated_layer('polygon', {'radius': 35, 'sides': 5})
    baseline = session.resolved()[lower.id]
    a = session.add_generated_layer('polygon', {'radius': 20, 'sides': 5})
    session.update_layer(a.id, {'occluder': True, 'occlusion_margin_mm': 1})
    tw = session.animate_layer(a.id)
    keys = session._chain_keys(tw)
    assert tw.occluder and tw.occlusion_margin_mm == 1
    session.regenerate_layer(keys[-1], {'radius': 45, 'sides': 5})
    early = session.resolved(master_t=0)[lower.id]
    late = session.resolved(master_t=1)[lower.id]
    assert early != late and late != baseline
    session.update_layer(tw.id, {'occluder': False})
    assert session.resolved(master_t=1)[lower.id] == baseline
    session.update_layer(tw.id, {'occluder': True})
    project_io.save_project(session.project, session.source_geometry, {}, tmp_path)
    project, geometry, *_ = project_io.load_project(tmp_path)
    session.project, session.source_geometry = project, geometry
    assert session.project.layer(keys[0]).animation_owner_id == tw.id
    reloaded = session.resolved(master_t=1)[lower.id]
    assert len(reloaded) == len(late)
    for actual, expected in zip(reloaded, late):
        assert actual.filled == expected.filled
        assert len(actual.points) == len(expected.points)
        for point, original in zip(actual.points, expected.points):
            assert point == pytest.approx(original, abs=1e-6)


def test_ambiguous_legacy_sources_are_not_adopted():
    tw, keys = family()
    data = session.project.model_dump()
    for layer in data['layers']:
        layer.pop('animation_owner_id', None)
    extra = next(l for l in data['layers'] if l['id'] == tw.id).copy()
    extra['id'] = 'other-tween'
    data['layers'].append(extra)
    project = Project.model_validate(data)
    assert all(l.animation_owner_id is None for l in project.layers)


def test_reject_shared_or_orphan_explicit_ownership():
    tw, keys = family()
    data = session.project.model_dump()
    data['layers'][0]['animation_owner_id'] = 'missing'
    with pytest.raises(ValueError, match='ownership'):
        Project.model_validate(data)


def test_bulk_delete_and_reorder_are_one_undo_each():
    tw, keys = family(4)
    session.clear_history()
    session.delete_layers([keys[0], keys[2]])
    assert session._chain_keys(tw) == [keys[1], keys[3]]
    assert session.undo() and not session.undo()
    tw = session.project.layer(tw.id)
    session.reorder_chain_keyframes(tw.id, keys[::-1])
    assert [l.id for l in session.project.layers] == [*keys, tw.id]
    assert session.undo()
    assert session._chain_keys(session.project.layer(tw.id)) == keys


def test_unanimate_updates_external_tween_reference():
    tw, keys = family()
    other = session.duplicate_layer(tw.id)
    outer = session.create_tween_layer(tw.id, other.id)
    session.unanimate_layer(tw.id)
    assert keys[0] in session._chain_keys(outer)
    Project.model_validate_json(session.project.model_dump_json())


def test_consolidating_master_removes_owned_sources_and_undo_restores_them():
    tw, keys = family()
    before = session.resolved()[tw.id]
    session.consolidate_effects(tw.id)
    assert [l.id for l in session.project.layers] == [tw.id]
    assert session.resolved()[tw.id] == before
    Project.model_validate_json(session.project.model_dump_json())
    session.undo()
    assert session._chain_keys(session.project.layer(tw.id)) == keys


def test_owned_keys_cannot_be_merged_out_of_their_family():
    tw, keys = family()
    with pytest.raises(ValueError, match='owned keyframes'):
        session.merge_layers(keys)
    assert session._chain_keys(tw) == keys


def test_split_hatch_cannot_create_shared_owned_sources():
    tw, keys = family()
    session.update_layer(tw.id, {'effects': [{'effect': 'hatch_fill', 'params': {}}]})
    with pytest.raises(ValueError, match='animation'):
        session.split_hatch_layer(tw.id)
    assert session._chain_keys(tw) == keys


def test_capture_interpolation_across_animation_creation_keeps_ownership():
    a = session.add_generated_layer('polygon', {'radius': 20})
    before = session._capture_snapshot()
    tw = session.animate_layer(a.id)
    keys = session._chain_keys(tw)
    assert [l.id for l in session.project.layers] == [*reversed(keys), tw.id]
    after = session._capture_snapshot()
    for t in (0, .25, .5, .75, 1):
        project, *_ = session._interpolate_snapshots(before, after, t)
        if t < .5:
            assert project.layer(a.id).animation_owner_id is None
        else:
            assert project.layer(a.id).animation_owner_id == tw.id
        Project.model_validate_json(project.model_dump_json())
