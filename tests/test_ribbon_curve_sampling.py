"""A flattened smooth curve must not acquire offset spikes at leaf boundaries."""
import math

import pytest

from axibridge.effects.ribbon import RibbonParams, _prepare
from axibridge.effects._ribbon_geometry import frames
from axibridge.registry import EffectContext


def turns(points):
    return [math.atan2((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]),
                       (b[0]-a[0])*(c[0]-b[0])+(b[1]-a[1])*(c[1]-b[1]))
            for a,b,c in zip(points,points[1:],points[2:])]


@pytest.mark.parametrize('sign', [-1, 1])
def test_gentle_arc_offsets_do_not_gain_reverse_turns_between_source_vertices(sign):
    source=[(200*math.cos(t*.09),200*math.sin(t*.09)) for t in range(18)]
    data=_prepare(source,RibbonParams(),EffectContext(seed=0))
    angles=[math.atan2(y,x) for x,y in data['frame']]
    # The known gentle arc advances ~0.01 radians per 2-unit station.
    # Concentrating a whole source-leaf turn into two samples is the artifact.
    jumps=[abs(math.atan2(math.sin(b-a),math.cos(b-a))) for a,b in zip(angles,angles[1:])]
    assert max(jumps[20:-20]) < .02
    offset=[(x+sign*32*nx,y+sign*32*ny) for (x,y),(nx,ny) in zip(data['spine'],data['frame'])]
    # Discard endpoint tangent settling. A concentric circular offset cannot
    # repeatedly reverse curvature just because its input was subdivided.
    interior=offset[20:-20]
    assert min(turns(interior)) >= -1e-8


def test_true_corner_frames_and_straight_source_remain_exact():
    for points in ([(0,0),(120,0)],[(0,0),(120,0),(120,100)]):
        data=_prepare(points,RibbonParams(),EffectContext(seed=0))
        assert data['frame']==frames(data['spine'])


def test_normal_blending_keeps_the_same_spine_stations_widths_and_lane_budget():
    source=[(200*math.cos(t*.09),200*math.sin(t*.09)) for t in range(18)]
    params=RibbonParams(width=12,steps=10)
    normal=_prepare(source,params,EffectContext(seed=0))
    historical=_prepare(source,params.model_copy(update={'fractured_edges':True}),EffectContext(seed=0))
    for key in ('spine','ss','total','widths','corners','required'):
        assert normal[key]==historical[key]


def test_redundant_collinear_vertices_do_not_change_curve_directions():
    from axibridge.effects._ribbon_geometry import curve_frames, sample_polyline
    source=[(200*math.cos(t*.09),200*math.sin(t*.09)) for t in range(18)]
    split=[]
    for a,b in zip(source,source[1:]):
        split.extend([a,((a[0]+b[0])/2,(a[1]+b[1])/2)])
    split.append(source[-1])
    spine,ss,_=sample_polyline(source,2)
    assert curve_frames(split,spine,ss)==curve_frames(source,spine,ss)
