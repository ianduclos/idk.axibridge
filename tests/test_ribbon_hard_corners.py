"""Regression from Ian's sharp multi-corner pen path, 8 September."""
import json
import math
from itertools import combinations
from pathlib import Path as File

from axibridge.compose import _layer_seed, CanvasLayer, shape_layer
from axibridge.effects.ribbon import Ribbon
from axibridge.effects.ribbon import RibbonParams, _prepare, _points
from axibridge.effects._ribbon_geometry import envelope
from axibridge.registry import EffectContext
from axibridge.sources.pen import PenSource, PenParams
from shapely.geometry import LineString


def fixture():
    path = File(__file__).resolve().parents[1] / 'docs/reviews/ribbon-hard-corners-2026-09-08/input.json'
    layer = json.loads(path.read_text())
    source = PenSource().generate(PenParams(**layer['source']['params'])).layers[0].paths[0]
    params = RibbonParams(**layer['effects'][0]['params'])
    return _prepare(_points(source), params, EffectContext(seed=_layer_seed(layer['id'])))


def test_hard_corner_join_stations_never_backtrack_or_leave_long_fallback_spikes():
    data = fixture()
    for sign, widths in zip((1,-1), data['widths']):
        for level in (1, .5, .1):
            nodes = [{'p': (p[0]+n[0]*w*sign*level,p[1]+n[1]*w*sign*level), 's':s}
                     for p,n,w,s in zip(data['spine'],data['frame'],widths,data['ss'])]
            out = envelope(nodes,data['spine'],data['ss'],data['corners'],data['width'])
            assert all(a['s'] <= b['s'] for a,b in zip(out,out[1:]))
            # The source has sub-mm segments; joins must not invent the old
            # 17–29 mm fallback diagonals across the band.
            assert max(math.dist(a['p'],b['p'])/4 for a,b in zip(out,out[1:])) < 3


def test_user_hard_corner_ribbon_has_no_folded_or_crossing_strands():
    path = File(__file__).resolve().parents[1] / 'docs/reviews/ribbon-hard-corners-2026-09-08/input.json'
    layer = CanvasLayer(**json.loads(path.read_text()))
    source = PenSource().generate(PenParams(**layer.source.params)).layers[0].paths
    strands = [LineString(p.points) for p in shape_layer(layer,source)]
    assert len(strands) == 21
    assert all(line.is_simple for line in strands)
    assert not any(a.crosses(b) for a,b in combinations(strands,2))
