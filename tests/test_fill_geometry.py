import pytest
from shapely.geometry import Polygon, Point
from axibridge.model import Path
from axibridge.fill_geometry import find_face, fit_face
from axibridge.sources.pen import PenSubpath, _flatten_subpath


def line(*pts):
    return Path(points=list(pts))


def square(x=0, y=0, size=10):
    return line((x,y),(x+size,y),(x+size,y+size),(x,y+size),(x,y))


def test_open_lines_duplicates_dangles_and_exterior():
    paths = [line((0,0),(10,0)), line((10,0),(10,10)), line((10,10),(0,10)), line((0,10),(0,0))]
    paths += [paths[0], line((5,0),(5,3))]
    assert find_face(paths, (2,2), 0).area == 100
    assert find_face(paths, (12,2), 0) is None
    assert find_face(paths, (0,2), 0) is None


def test_crossing_adjacent_faces():
    paths = [square(), line((5,-2),(5,12)), line((-2,5),(12,5))]
    face = find_face(paths, (2,2), 0)
    assert face.area == 25
    assert not face.contains(Point(7,2))


def test_nested_island_and_narrow_hole_stay_distinct():
    paths = [square(), square(4,4,0.2), square(10.1,0,2)]
    face = find_face(paths, (2,2), 0.3)
    assert len(face.interiors) == 1
    assert face.area == pytest.approx(99.96)
    assert find_face(paths, (4.1,4.1), 0.3).area == pytest.approx(.04)


@pytest.mark.parametrize('gap,closed', [(0,False),(.19,False),(.21,True)])
def test_endpoint_gap(gap, closed):
    paths = [line((0,0),(10,0),(10,10),(0,10),(0,.2))]
    assert (find_face(paths,(2,2),gap) is not None) == closed


def test_endpoint_to_segment_gap():
    paths = [line((-2,0),(12,0)),line((0,.1),(0,10),(10,10),(10,.1))]
    assert find_face(paths,(2,2),.11).area == pytest.approx(100)


@pytest.mark.parametrize('face', [Polygon([(0,0),(10,0),(10,10),(0,10)]), Polygon([(0,0),(10,0),(10,4),(4,4),(4,10),(0,10)]), Polygon([(0,0),(10,0),(10,10),(0,10)], [[(4,4),(4.2,4),(4.2,4.2),(4,4.2)]])])
def test_fit_topology(face):
    result = fit_face(face,1)
    rings = [_flatten_subpath(PenSubpath(**sp),.05) for sp in result]
    fitted = Polygon(rings[0],rings[1:])
    assert fitted.is_valid
    assert len(fitted.interiors) == len(face.interiors)
    assert fitted.covers(face.representative_point())
    assert all(sp['closed'] for sp in result)


def test_bad_fit_refused(monkeypatch):
    monkeypatch.setattr('axibridge.fill_geometry.fit_bezier', lambda *a, **k: [{'x':0,'y':0},{'x':1,'y':0},{'x':0,'y':1}])
    with pytest.raises(ValueError,match='Detail'):
        fit_face(Polygon([(0,0),(10,0),(10,10),(0,10)]),.5)


def test_workload_limit():
    with pytest.raises(ValueError,match='limit'):
        find_face([line((i,0),(i,1)) for i in range(20001)],(0,0),0)


def test_cancellation_checkpoint(monkeypatch):
    def stop():
        raise RuntimeError('cancelled')
    monkeypatch.setattr('axibridge.fill_geometry.checkpoint',stop)
    with pytest.raises(RuntimeError,match='cancelled'):
        find_face([square()],(1,1),0)


def test_curved_face_allows_bounded_inward_fitting():
    face = Point(20,20).buffer(10,quad_segs=48)
    result = fit_face(face,1)
    fitted = Polygon(_flatten_subpath(PenSubpath(**result[0]),.05))
    assert fitted.exterior.hausdorff_distance(face.exterior) <= .1


@pytest.mark.parametrize('detail', [-1, 2, float('nan'), float('inf')])
def test_detail_is_bounded(detail):
    with pytest.raises(ValueError,match='Detail'):
        fit_face(Polygon([(0,0),(10,0),(10,10),(0,10)]),detail)


def test_gap_search_limit():
    with pytest.raises(ValueError,match='gap search limit'):
        find_face([line((i*3,0),(i*3,1)) for i in range(1100)],(.2,.2),.2)


def test_fit_rejects_lost_hole(monkeypatch):
    from axibridge.fill_geometry import fit_bezier
    def collapse(points, **kwargs):
        if Polygon(points).area < 1:
            return [{'x':4,'y':4}]*3
        return fit_bezier(points, **kwargs)
    monkeypatch.setattr('axibridge.fill_geometry.fit_bezier',collapse)
    face = Polygon([(0,0),(10,0),(10,10),(0,10)], [[(4,4),(4.2,4),(4.2,4.2),(4,4.2)]])
    with pytest.raises(ValueError,match='Detail'):
        fit_face(face,1)


def test_degenerate_segments_still_count_towards_limit():
    with pytest.raises(ValueError,match='input segment limit'):
        find_face([line(*([(0,0)]*20002))],(1,1),0)


@pytest.mark.parametrize('gap', [-.1, 5.1, float('nan'), float('inf')])
def test_gap_is_bounded(gap):
    with pytest.raises(ValueError,match='Gap'):
        find_face([square()],(1,1),gap)


def test_gap_closure_is_invariant_under_collinear_sampling():
    sparse = line((0,0),(10,0),(10,10),(0,10),(0,.2))
    dense = line((0,0),(.01,0),(10,0),(10,10),(0,10),(0,.21),(0,.2))
    assert find_face([sparse],(2,2),.21).area == 100
    assert find_face([dense],(2,2),.21).area == 100


def test_gap_closure_ignores_shortcuts_along_local_bent_branch():
    bent = line((0,0),(.01,.01),(.02,0),(10,0),(10,10),(0,10),(0,.22),(.01,.21),(0,.2))
    face = find_face([bent],(2,2),.21)
    assert face is not None
    assert face.area > 99


def test_more_than_two_thousand_ordinary_segments_are_supported():
    points = [(i/250,0) for i in range(2501)]
    points += [(10,10),(0,10),(0,0)]
    assert find_face([line(*points)],(5,5),0).area == 100


def test_crossing_workload_is_refused_before_native_union(monkeypatch):
    called = []
    monkeypatch.setattr('axibridge.fill_geometry.unary_union',lambda *a: called.append(True))
    paths = [line((0,i),(1000,1000-i)) for i in range(800)]
    with pytest.raises(ValueError,match='candidate pair limit'):
        find_face(paths,(1,1),0)
    assert not called


def test_rounded_sparse_boundary_succeeds_at_max_detail():
    face = Polygon([(120,40),(180,40),(180,100),(120,100)]).buffer(2,quad_segs=8)
    result = fit_face(face,1)
    fitted = Polygon(_flatten_subpath(PenSubpath(**result[0]),.05))
    assert fitted.is_valid
    assert fitted.exterior.hausdorff_distance(face.exterior) <= .1


def test_repaired_union_is_preflighted_too(monkeypatch):
    from axibridge.fill_geometry import _preflight_union
    calls = []
    def record(segments):
        calls.append(len(segments))
        return _preflight_union(segments)
    monkeypatch.setattr('axibridge.fill_geometry._preflight_union',record)
    assert find_face([line((0,0),(10,0),(10,10),(0,10),(0,.2))],(2,2),.21) is not None
    assert len(calls) == 2
    assert calls[1] > calls[0]


def test_expanded_fit_samples_are_bounded():
    face = Polygon([(0,0),(3000,0),(3000,3000),(0,3000)])
    with pytest.raises(ValueError,match='resampled ring vertex limit'):
        fit_face(face,1)
