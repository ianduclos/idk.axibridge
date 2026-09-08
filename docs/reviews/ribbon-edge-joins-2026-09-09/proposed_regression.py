"""Corner joins must support lanes that change sides of their source."""
import math
from shapely.geometry import LineString
from axibridge.effects._ribbon_geometry import sample_polyline, frames, sharp_corners, envelope


def test_signed_lane_does_not_collapse_onto_source_at_corner():
    spine, stations, total = sample_polyline([(0,0),(40,0),(40,40)],1)
    normals = frames(spine)
    widths = [6*math.sin(2*math.pi*s/total+.5) for s in stations]
    widths[0] = widths[-1] = 0
    nodes = [{'p':(p[0]+n[0]*w,p[1]+n[1]*w),'s':s}
             for p,n,w,s in zip(spine,normals,widths,stations)]
    joined = envelope(nodes,spine,stations,sharp_corners(spine,stations),6)
    line = LineString([n['p'] for n in joined])
    assert line.intersection(LineString(spine)).length < 1e-8
    assert all(a['s'] <= b['s'] for a,b in zip(joined,joined[1:]))
    assert line.is_simple
