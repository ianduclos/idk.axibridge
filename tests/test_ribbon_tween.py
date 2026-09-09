"""Whole-number JSON endpoints must not turn continuous effect sliders into steps."""
import pytest

from axibridge.compose import EffectStep
from axibridge.effects.ribbon import RibbonParams
from axibridge.tween import blend_effect_stacks


@pytest.mark.parametrize('t', [0, .25, .5, .75, 1])
def test_ribbon_seed_blend_uses_declared_float_type(t):
    a = EffectStep(effect='ribbon', params={'seed': 17, 'seed_b': 19, 'seed_blend': 1, 'steps': 10})
    b = EffectStep(effect='ribbon', params={'seed': 17, 'seed_b': 19, 'seed_blend': 0, 'steps': 12})
    stack, matched = blend_effect_stacks([a], [b], t)
    assert matched
    params = RibbonParams(**stack[0].params)
    assert params.seed_blend == 1-t
    assert params.seed == 17 and params.seed_b == 19
    assert params.steps == round(10+2*t)
    assert a.params['seed_blend'] == 1 and b.params['seed_blend'] == 0
