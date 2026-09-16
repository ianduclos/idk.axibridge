"""Plot preparation always removes sub-0.01 mm redundancy, including old projects."""
from axibridge.compose import PlotOptions
from axibridge.model import Layer, Path, PathDocument
from axibridge.session import session


def test_legacy_disabled_simplification_still_gets_baseline():
    session.project.plot_options = PlotOptions(sort=False,merge=False,simplify=False)
    points=[(i*.001,0.) for i in range(1001)]
    doc=PathDocument(layers=[Layer(id=1,paths=[Path(points=points)])])
    result=session._optimize(doc)
    assert result.layers[0].paths[0].points == [(0.,0.),(1.,0.)]
    assert doc.layers[0].paths[0].points == points


def test_baseline_preserves_separate_passages_and_visible_bend():
    session.project.plot_options = PlotOptions(sort=False,merge=False,simplify=False)
    doc=PathDocument(layers=[Layer(id=1,paths=[
        Path(points=[(0.,0.),(.5,.03),(1.,0.)]),
        Path(points=[(2.,0.),(2.5,0.),(3.,0.)]),
    ])])
    result=session._optimize(doc)
    assert len(result.layers[0].paths)==2
    assert result.layers[0].paths[0].points == doc.layers[0].paths[0].points
    assert result.layers[0].paths[1].points == [(2.,0.),(3.,0.)]


def test_extra_simplification_remains_available():
    session.project.plot_options=PlotOptions(sort=False,merge=False,simplify=True,simplify_tolerance_mm=.1)
    doc=PathDocument(layers=[Layer(id=1,paths=[Path(points=[(0.,0.),(.5,.03),(1.,0.)])])])
    assert session._optimize(doc).layers[0].paths[0].points == [(0.,0.),(1.,0.)]


def test_legacy_tolerance_below_baseline_does_not_disable_it():
    session.project.plot_options=PlotOptions(sort=False,merge=False,simplify=True,simplify_tolerance_mm=.001)
    doc=PathDocument(layers=[Layer(id=1,paths=[Path(points=[(0.,0.),(.5,.005),(1.,0.)])])])
    assert session._optimize(doc).layers[0].paths[0].points == [(0.,0.),(1.,0.)]


def test_baseline_preserves_dots_when_other_operations_disabled():
    session.project.plot_options = PlotOptions(sort=False, merge=False)
    doc = PathDocument(layers=[Layer(id=1, paths=[Path(points=[(10, 10)])])])
    assert session._optimize(doc) == doc
