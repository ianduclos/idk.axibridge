"""Recipe and cache isolation for the two preserved research choices."""
import pytest
from pydantic import ValidationError
from axibridge.linedraw.contracts import LinedrawV3Params
from axibridge.linedraw.runtime import evidence_key

REGION = dict(id='r', person_id='person-1', category='clothing',
              polygon=[[.1,.2],[.8,.2],[.8,.9],[.1,.9]])

def test_reference_recipes_roundtrip_regions_and_exclusions():
    p = LinedrawV3Params(style='regional_form', detail_regions=[REGION | {
        'exclude_polygons': [[[.2,.3],[.3,.3],[.3,.4],[.2,.4]]]}])
    restored = LinedrawV3Params.model_validate_json(p.model_dump_json())
    assert restored.detail_regions[0].exclude_polygons[0][0] == (.2,.3)
    assert restored.detail_regions[0].person_id == 'person-1'

@pytest.mark.parametrize('polygon', [
    [[0,0],[1,1],[0,1],[1,0]], [[0,0],[1,0],[.5,0]],
    [[-.1,0],[1,0],[1,1]], [[0,0],[float('nan'),1],[1,0]],
])
def test_invalid_polygons_rejected(polygon):
    with pytest.raises(ValidationError):
        LinedrawV3Params(style='regional_form',detail_regions=[REGION|{'polygon':polygon}])

def test_guides_change_evidence_but_display_allowances_do_not():
    p = LinedrawV3Params(style='regional_form',detail_regions=[REGION])
    key = evidence_key(b'one',p,'models')
    assert evidence_key(b'one',p.model_copy(update={'detail_budget':48,'detail_categories':[]}), 'models') == key
    moved = p.model_dump()
    moved['detail_regions'][0]['polygon'][0] = [.15,.2]
    assert evidence_key(b'one',LinedrawV3Params(**moved),'models') != key
    assert evidence_key(b'two',p,'models') != key
    assert evidence_key(b'one',p.model_copy(update={'style':'light_support'}),'models') != key

def test_ambiguous_owner_and_face_links_rejected():
    with pytest.raises(ValidationError):
        LinedrawV3Params(detail_regions=[REGION|{'person_id':'missing'}])
    with pytest.raises(ValidationError):
        LinedrawV3Params(people=[dict(id='a', face_id='missing',polygon=[[0,0],[1,0],[1,1],[0,1]])])

def test_light_support_does_not_alias_existing_evidence_profile():
    standard=LinedrawV3Params()
    reference=LinedrawV3Params(style='light_support')
    assert evidence_key(b'x',standard,'m') != evidence_key(b'x',reference,'m')
