import pytest
from axibridge.compose import Affine, CanvasLayer, LayerSource, Project
from axibridge.model import Path
from axibridge.session import Session


def scene():
    s = Session()
    for i in range(3):
        l = CanvasLayer(id=str(i), name=str(i), source=LayerSource(type='baked'))
        s.project.layers.append(l)
        s.source_geometry[l.id] = [Path(points=[(0, 0), (10, 0)])]
    return s


def target(i, kind='layer'):
    return {'kind': kind, 'id': i}


def pts(s, i='0', t=None):
    return [p.points for p in s.resolved(t).get(i, [])]


def test_identity_group_and_atomic_nested_transform():
    s = scene()
    before = s.resolved()
    g = s.create_group([target('0'), target('1')])
    assert s.resolved() == before
    h = s.create_group([target(g.id, 'group'), target('2')])
    n = len(s._history)
    s.transform_selection([target(h.id, 'group'), target('0')], Affine(e=7, f=3))
    assert len(s._history) == n + 1
    assert pts(s) == [[(7, 3), (17, 3)]]
    s.undo()
    assert s.resolved() == before
    s.redo()
    assert pts(s) == [[(7, 3), (17, 3)]]


def test_invalid_membership_and_singular_transform_do_not_mutate():
    s = scene()
    before = s.project.model_dump()
    with pytest.raises(ValueError):
        s.create_group([target('0'), target('2')])
    with pytest.raises(ValueError):
        s.transform_selection([target('0')], Affine(a=0, d=0))
    assert s.project.model_dump() == before
    assert not s.can_undo()


def test_nested_visibility_and_ungroup_preserve_placement():
    s = scene()
    s.project.layer('1').visible = False
    g = s.create_group([target('0'), target('1')])
    s.transform_selection([target(g.id, 'group')], Affine(a=2, d=3, e=5))
    before = pts(s)
    s.update_group(g.id, {'visible': False})
    assert not pts(s)
    s.update_group(g.id, {'visible': True})
    assert pts(s) == before
    assert not s.project.layer('1').visible
    s.ungroup(g.id)
    assert pts(s) == before
    assert not s.project.groups


def test_linked_tween_group_reparent_keeps_all_frames_and_live_refs():
    s = scene()
    s.project.layer('1').transform = Affine(e=20)
    tw = s.create_tween_layer('0', '1')
    s.set_tween_params(tw.id, {'follow_master': True})
    g = s.create_group([target(tw.id)])
    s.transform_selection([target(g.id, 'group')], Affine(a=2, d=3, e=5))
    frames = [pts(s, tw.id, t) for t in (0, .25, .5, .75, 1)]
    s.ungroup(g.id)
    assert [pts(s, tw.id, t) for t in (0, .25, .5, .75, 1)] == frames
    s.update_layer('1', {'transform': {'e': 40}})
    assert pts(s, tw.id, 1) != frames[-1]
    assert s.project.layer('0').transform == Affine()


def test_duplicate_group_remaps_internal_references_and_roundtrip():
    s = scene()
    tw = s.create_tween_layer('0', '1')
    g = s.create_group([target('0'), target(tw.id), target('1')])
    copies = s.duplicate_selection([target(g.id, 'group')])
    cg = copies[0]['id']
    members = [l for l in s.project.layers if l.group_id == cg]
    copy_tw = next(l for l in members if l.source.type == 'tween')
    assert set(copy_tw.source.params['keys'] or [copy_tw.source.params['a'], copy_tw.source.params['b']]) <= {l.id for l in members}
    loaded = Project.model_validate(s.project.model_dump())
    assert loaded.groups == s.project.groups
    s.delete_selection([target(cg, 'group')])
    assert len(s.project.layers) == 4


def test_legacy_mutations_keep_valid_group_hierarchy_and_world_placement():
    from axibridge.groups import validate_hierarchy
    s = scene()
    g = s.create_group([target('0'),target('1')])
    tw = s.create_tween_layer('0','1')
    assert tw.group_id == g.id
    validate_hierarchy(s.project)
    s.delete_layer(tw.id)
    s.transform_selection([target(g.id,'group')],Affine(a=2,d=3,e=20))
    before = pts(s)
    s.consolidate_effects('0')
    assert pts(s) == before
    before = pts(s)+pts(s,'2')
    survivor = s.merge_layers(['0','2'])
    assert pts(s,survivor.id) == before
    s.delete_layer('1')
    assert not s.project.groups
    Project.model_validate(s.project.model_dump())


def test_hidden_ungroup_preserves_member_flag_and_explicit_show_restores():
    s = scene()
    g = s.create_group([target('0')])
    s.update_group(g.id,{'visible':False})
    s.ungroup(g.id)
    assert s.project.layer('0').visible
    assert not pts(s)
    s.update_layer('0',{'visible':True})
    assert pts(s)


def test_multi_ungroup_and_animation_transform_are_one_operation():
    s = scene()
    a = s.create_group([target('0')])
    b = s.create_group([target('1')])
    n = len(s._history)
    s.ungroup_selection([target(a.id,'group'),target(b.id,'group')])
    assert len(s._history) == n+1
    master = s.animate_layer('0')
    before = pts(s,master.id, .5)
    s.transform_selection([target(master.id)],Affine(e=10))
    assert pts(s,master.id,.5) == [[(x+10,y) for x,y in p] for p in before]


def test_ancestor_selection_absorbs_owned_key_before_family_validation():
    s = scene()
    master = s.animate_layer('0')
    key = s._animation_keyframes_for(master)[0]
    g = s.create_group([target(master.id)])
    before = pts(s, master.id, .5)
    s.transform_selection([target(g.id, 'group'), target(key.id)], Affine(e=4))
    assert pts(s, master.id, .5) == [[(x+4,y) for x,y in p] for p in before]


def test_overflowing_placement_rejects_before_mutation():
    s = scene()
    s.project.layer('0').transform = Affine(a=1e200, d=1e200)
    before = s.project.model_dump()
    with pytest.raises(ValueError, match='finite'):
        s.transform_selection([target('0')], Affine(a=1e200, d=1e200))
    assert s.project.model_dump() == before
    assert not s.can_undo()


def test_unanimate_retains_atomic_master_and_reparented_placement():
    s = scene()
    master = s.animate_layer('0')
    g = s.create_group([target(master.id)])
    s.transform_selection([target(g.id, 'group')], Affine(a=2, d=3, e=5))
    s.transform_selection([target(master.id)], Affine(e=10, f=7))
    s.ungroup(g.id)
    before = pts(s, master.id, 0)
    survivor = s.unanimate_layer(master.id)
    assert pts(s, survivor.id) == before


def test_nested_tween_reference_reparent_preserves_frames():
    s = Session()
    a,b,c,d = [s.add_generated_layer('polygon', {'sides':6,'radius':r}) for r in (10,18,27,39)]
    left = s.create_tween_layer(a.id,b.id)
    right = s.create_tween_layer(c.id,d.id)
    outer = s.create_tween_layer(left.id,right.id)
    for tw in (left,right,outer): s.set_tween_params(tw.id,{'follow_master':True})
    common = s.create_group([target(l.id) for l in s.project.layers])
    s.transform_selection([target(common.id,'group')],Affine(a=1.5,d=.75,e=7,f=-4))
    destination = s.create_group([target(d.id)])
    s.transform_selection([target(destination.id,'group')],Affine(e=9))
    times = (0,.25,.5,.75,1)
    before = [pts(s,outer.id,t) for t in times]
    s.reparent_selection([target(a.id)],destination.id)
    after = [pts(s,outer.id,t) for t in times]
    for frame,wanted in zip(after,before):
        for path,expected in zip(frame,wanted):
            for point,goal in zip(path,expected): assert point == pytest.approx(goal)
    s.ungroup(destination.id)
    for frame,wanted in zip([pts(s,outer.id,t) for t in times],before):
        for path,expected in zip(frame,wanted):
            for point,goal in zip(path,expected): assert point == pytest.approx(goal)
