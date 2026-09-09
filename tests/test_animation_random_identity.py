"""Animation duplication must be visually static until a parameter is changed."""
import pytest
from pydantic import BaseModel, Field

from axibridge import registry
from axibridge.compose import EffectStep, Project, _layer_seed, shape_layer
from axibridge.model import Path, Layer, PathDocument
from axibridge.session import session
from axibridge.tween import lerp_params


class ProbeParams(BaseModel):
    seed: int = Field(0, ge=0, le=9999)
    amount: float = Field(1., ge=0, le=10)


class ContextProbe(registry.EffectModule):
    id = 'animation_context_probe'
    Params = ProbeParams

    def apply(self, paths, params, ctx):
        x = (ctx.seed % 100000) / 1000 + params.seed
        return [Path(points=[(x, 0), (x, params.amount)])]


def test_new_effect_uses_shared_random_identity_through_animation_and_chain(monkeypatch):
    monkeypatch.setitem(registry._EFFECTS, ContextProbe.id, ContextProbe())
    layer = session.add_generated_layer('polygon', {'sides': 3})
    session.update_layer(layer.id, {'effects': [EffectStep(effect=ContextProbe.id).model_dump()]})
    before = session.resolved()[layer.id]
    tw = session.animate_layer(layer.id)
    for t in (0, .25, .4999, .5, .5001, .75, 1):
        assert session.resolved(master_t=t)[tw.id] == before
    c = session.add_chain_keyframe(tw.id)
    for t in (0, .25, .5, .75, 1):
        assert session.resolved(master_t=t)[tw.id] == before
    assert c.effect_seed == _layer_seed(layer.id)
    restored = Project.model_validate_json(session.project.model_dump_json())
    assert restored.layer(c.id).effect_seed == c.effect_seed
    session.project = restored
    assert session.resolved(master_t=.75)[tw.id] == before


def test_random_identity_change_invalidates_shape_and_tween_caches(monkeypatch):
    monkeypatch.setitem(registry._EFFECTS, ContextProbe.id, ContextProbe())
    layer = session.add_generated_layer('polygon', {'sides': 3})
    layer = session.update_layer(layer.id, {'effects': [EffectStep(effect=ContextProbe.id).model_dump()]})
    before = session.resolved()[layer.id]
    session.update_layer(layer.id, {'effect_seed': 42})
    assert session.resolved()[layer.id] != before
    tw = session.animate_layer(layer.id)
    before = session.resolved(master_t=.75)[tw.id]
    session.update_layer(tw.source.params['b'], {'effect_seed': 99})
    assert session.resolved(master_t=.75)[tw.id] != before


def test_animate_random_identity_is_one_undo_and_does_not_reshuffle_original(monkeypatch):
    monkeypatch.setitem(registry._EFFECTS, ContextProbe.id, ContextProbe())
    layer = session.add_generated_layer('polygon', {'sides': 3})
    session.update_layer(layer.id, {'effects': [EffectStep(effect=ContextProbe.id).model_dump()]})
    before = session.resolved()[layer.id]
    session.animate_layer(layer.id)
    session.undo()
    assert session.project.layer(layer.id).effect_seed is None
    assert session.resolved()[layer.id] == before


def test_equal_zero_seed_is_stable_at_every_frame():
    assert [lerp_params({'seed': 0}, {'seed': 0}, t, {})['seed'] for t in (0, .25, .5, .75, 1)] == [0]*5


class GeneratorProbe(registry.SourceModule):
    id = 'animation_generator_probe'
    label = 'Animation generator probe'
    orientation = 'none'
    Params = ProbeParams

    def generate(self, params):
        return PathDocument(layers=[Layer(id=0, paths=[Path(points=[(params.seed, 0), (params.seed, params.amount)])])])


def test_new_generator_equal_zero_seed_is_static_and_float_amount_blends(monkeypatch):
    monkeypatch.setitem(registry._SOURCES, GeneratorProbe.id, GeneratorProbe())
    layer = session.add_generated_layer(GeneratorProbe.id, {'seed': 0, 'amount': 1})
    before = session.resolved()[layer.id]
    tw = session.animate_layer(layer.id)
    for t in (0, .25, .4999, .5, .5001, .75, 1):
        assert session.resolved(master_t=t)[tw.id] == before
    session.regenerate_layer(tw.source.params['b'], {'seed': 0, 'amount': 2})
    for t in (.25, .5, .75):
        paths = session.resolved(master_t=t)[tw.id]
        assert paths[0].points[-1] == (0, 1+t)


def test_ordinary_duplicate_of_keyframe_has_independent_field(monkeypatch):
    monkeypatch.setitem(registry._EFFECTS, ContextProbe.id, ContextProbe())
    layer = session.add_generated_layer('polygon', {'sides': 3})
    session.update_layer(layer.id, {'effects': [EffectStep(effect=ContextProbe.id).model_dump()]})
    tw = session.animate_layer(layer.id)
    b = session.project.layer(tw.source.params['b'])
    duplicate = session.duplicate_layer(b.id)
    assert duplicate.effect_seed is None
    assert shape_layer(duplicate, session.source_geometry[duplicate.id]) != shape_layer(b, session.source_geometry[b.id])


def test_ribbon_animate_keeps_original_field_at_midpoint():
    layer = session.add_generated_layer('pen', {'subpaths': [{'anchors': [{'x': 10, 'y': 10}, {'x': 90, 'y': 10}]}]})
    session.update_layer(layer.id, {'effects': [{'effect': 'ribbon', 'params': {'seed': 7, 'seed_b': 19, 'steps': 3}}]})
    before = session.resolved()[layer.id]
    tw = session.animate_layer(layer.id)
    for t in (0, .4999, .5, .5001, 1):
        assert session.resolved(master_t=t)[tw.id] == before


def test_independent_split_and_exploded_layers_reset_identity():
    layer = session.add_generated_layer('polygon', {'sides': 3, 'filled': True})
    session.update_layer(layer.id, {'effect_seed': 42, 'effects': [{'effect': 'hatch_fill', 'params': {'spacing': 5}}]})
    fill = session.split_hatch_layer(layer.id)
    assert fill.effect_seed is None
    assert session.project.layer(layer.id).effect_seed == 42
    tw = session.animate_layer(layer.id)
    session.update_layer(tw.id, {'effect_seed': 99})
    assert all(layer.effect_seed is None for layer in session.explode_tween(tw.id))


def test_capture_interpolation_preserves_changed_identity_at_endpoints(monkeypatch):
    monkeypatch.setitem(registry._EFFECTS, ContextProbe.id, ContextProbe())
    layer = session.add_generated_layer('polygon', {'sides': 3})
    a = session.update_layer(layer.id, {'effect_seed': 42, 'effects': [EffectStep(effect=ContextProbe.id).model_dump()]})
    b = a.model_copy(update={'effect_seed': 99})
    source = session.source_geometry[a.id]
    for t, expected in ((0, a), (1, b)):
        result, geometry = session._interpolate_layer(a, b, source, source, t, [])
        assert shape_layer(result, geometry) == shape_layer(expected, source)
