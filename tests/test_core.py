"""Core unit tests: IPR, fill-aware SVG reader, estimator."""

import pytest

from axibridge.estimate import EstimatorConstants, MotionParams, plan_job
from axibridge.model import Layer, Path, PathDocument
from axibridge.svg_io import doc_from_svg, doc_to_svg


@pytest.fixture()
def square_doc() -> PathDocument:
    sq = [(10, 10), (60, 10), (60, 60), (10, 60), (10, 10)]
    return PathDocument(
        layers=[Layer(id=1, name="l", paths=[Path(points=sq)])],
        width=100, height=100,
    )


def test_path_length(square_doc):
    assert square_doc.stats().pen_down_distance == pytest.approx(200.0)


def test_fill_aware_svg_reader():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg"
        xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
        width="100mm" height="80mm" viewBox="0 0 100 80">
      <g inkscape:label="solids">
        <rect x="10" y="10" width="30" height="20" fill="red" stroke="blue"/>
        <circle cx="60" cy="30" r="15" fill="none" stroke="black"/>
      </g>
      <path d="M 5 70 L 95 70" stroke="black" fill="none"/>
    </svg>'''
    doc = doc_from_svg(svg, 0.1)
    assert doc.width == pytest.approx(100, abs=0.01)
    assert len(doc.layers) == 2  # named group + ungrouped catch-all
    solids = doc.layers[0]
    assert solids.name == "solids"
    rect, circle = solids.paths
    assert rect.filled and rect.points[0] == rect.points[-1]
    assert not circle.filled  # stroke-only
    # flattening respects the tolerance
    import math
    err = max(abs(math.dist(p, (60, 30)) - 15) for p in circle.points)
    assert err < 0.1


def test_svg_roundtrip(square_doc):
    back = doc_from_svg(doc_to_svg(square_doc))
    stats = back.stats()
    assert stats.paths == 1
    assert stats.pen_down_distance == pytest.approx(200.0, rel=1e-3)


def test_estimate_monotonic(square_doc):
    slow = plan_job(square_doc, MotionParams(speed_pendown=10))
    fast = plan_job(square_doc, MotionParams(speed_pendown=80))
    assert fast.total_duration < slow.total_duration
    assert slow.pen_down_distance == pytest.approx(200.0)
    assert all(m.duration > 0 for m in slow.moves)


def test_estimate_constants_injectable(square_doc):
    nominal = plan_job(square_doc, MotionParams())
    fast_machine = plan_job(
        square_doc, MotionParams(),
        consts=EstimatorConstants(max_speed_mm_s=600, max_accel_mm_s2=10000),
    )
    assert fast_machine.total_duration < nominal.total_duration
