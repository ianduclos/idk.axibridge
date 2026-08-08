"""Smoothen: Catmull-Rom re-curving of flattened polylines.

The load-bearing claim is that it *interpolates* — it passes through the
points it was given and only invents the arc between them. Most of what is
asserted here is that claim in one form or another.
"""

import math

from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect

CX, CY, R = 50.0, 50.0, 20.0


def _eff():
    return get_effect("smoothen")


def _ring(n=8, closed=True):
    """A coarsely flattened circle — exactly the input this effect exists for."""
    pts = [(CX + R * math.cos(2 * math.pi * i / n), CY + R * math.sin(2 * math.pi * i / n))
           for i in range(n)]
    if closed:
        pts.append(pts[0])
    return pts


def _densify(pts, per_seg=20):
    """Walk the polyline itself, not just its vertices — the faceting error
    lives in the middle of each chord, not at its ends."""
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        for i in range(per_seg):
            f = i / per_seg
            out.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
    out.append(pts[-1])
    return out


def _radial_error(pts):
    return max(abs(math.dist(p, (CX, CY)) - R) for p in pts)


def test_closed_shape_stays_closed_and_filled():
    eff = _eff()
    src = Path(points=_ring(), filled=True)
    out = eff.apply([src], eff.Params(), EffectContext())
    assert len(out) == 1
    got = out[0]
    assert got.filled
    assert got.is_closed                        # the canonical definition
    assert got.points[0] == got.points[-1]      # exactly — occlusion masks depend on it


def test_open_endpoints_are_bit_identical():
    eff = _eff()
    src = Path(points=[(0.0, 0.0), (10.0, 3.0), (20.0, 0.0), (30.0, 5.0)])
    got = eff.apply([src], eff.Params(), EffectContext())[0]
    assert not got.is_closed
    assert got.points[0] == (0.0, 0.0)
    assert got.points[-1] == (30.0, 5.0)


def test_short_paths_pass_through_untouched():
    eff = _eff()
    dot = Path(points=[(5.0, 5.0)])
    seg = Path(points=[(0.0, 0.0), (10.0, 0.0)], filled=False)
    out = eff.apply([dot, seg], eff.Params(), EffectContext())
    assert out[0].points == dot.points
    assert out[1].points == seg.points


def test_consecutive_duplicate_points_do_not_raise():
    # centripetal parameterisation divides by a chord length; a repeated point
    # is a zero chord. shapely ops and resampling emit these routinely.
    eff = _eff()
    src = Path(points=[(0.0, 0.0), (0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (10.0, 10.0)])
    got = eff.apply([src], eff.Params(), EffectContext())[0]
    assert len(got.points) > 3


def test_it_actually_recurves_a_flattened_circle():
    """The whole point: the spline is far closer to the true arc than the
    chords it was built from."""
    eff = _eff()
    ring = _ring(n=8)
    facet_error = _radial_error(_densify(ring))
    got = eff.apply([Path(points=ring)], eff.Params(resolution=0.25), EffectContext())[0]
    assert _radial_error(got.points) < facet_error / 5


def test_resolution_controls_density():
    eff = _eff()
    src = Path(points=_ring(n=8))
    coarse = eff.apply([src], eff.Params(resolution=2.0), EffectContext())[0]
    fine = eff.apply([src], eff.Params(resolution=0.25), EffectContext())[0]
    assert len(fine.points) > len(coarse.points) * 4


def test_relax_zero_keeps_every_original_vertex_on_the_curve():
    """Interpolating, not averaging: with relax at 0 the original points are
    still on the output, which is what separates this from a smoothing filter."""
    eff = _eff()
    ring = _ring(n=8)
    got = eff.apply([Path(points=ring)], eff.Params(relax=0.0, resolution=0.5), EffectContext())[0]
    for v in ring[:-1]:
        assert min(math.dist(v, p) for p in got.points) < 1e-9


def test_relax_moves_points_inward():
    """...and with relax up, it does move them — a relaxed ring is smaller."""
    eff = _eff()
    ring = _ring(n=8)
    got = eff.apply([Path(points=ring)],
                    eff.Params(relax=1.0, relax_passes=4), EffectContext())[0]
    assert max(math.dist(p, (CX, CY)) for p in got.points) < R


def test_input_is_not_mutated():
    eff = _eff()
    pts = _ring()
    src = Path(points=list(pts), filled=True)
    eff.apply([src], eff.Params(relax=0.8), EffectContext())
    assert src.points == pts
