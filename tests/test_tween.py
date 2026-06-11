"""Interpolation (tween) layers and the perspective effect."""

import math

import pytest

from axibridge.compose import Affine
from axibridge.model import Path
from axibridge.registry import EffectContext, get_effect
from axibridge.session import session
from axibridge.tween import compose_affine, decompose_affine, lerp_affine, lerp_params


def _pair(radius_b=30, move_b=(60.0, 25.0)):
    a = session.add_generated_layer("polygon", {"sides": 6, "radius": 15})
    b = session.add_generated_layer("polygon", {"sides": 6, "radius": radius_b})
    session.update_layer(b.id, {"transform": {
        "a": 1, "b": 0, "c": 0, "d": 1, "e": move_b[0], "f": move_b[1]}})
    return a, session.project.layer(b.id)


def _approx_equal(pa, pb, tol=1e-6):
    assert len(pa) == len(pb)
    for x, y in zip(pa, pb):
        assert len(x.points) == len(y.points)
        for (x0, y0), (x1, y1) in zip(x.points, y.points):
            assert x0 == pytest.approx(x1, abs=tol)
            assert y0 == pytest.approx(y1, abs=tol)


def test_tween_endpoints_reproduce_a_and_b():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    r = session.resolved()
    session.set_tween_params(tw.id, {"t": 0.0})
    _approx_equal(session.resolved()[tw.id], session.resolved()[a.id])
    session.set_tween_params(tw.id, {"t": 1.0})
    _approx_equal(session.resolved()[tw.id], session.resolved()[b.id])


def test_tween_midpoint_is_between():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 0.5})
    r = session.resolved()
    cx = sum(x for p in r[tw.id] for x, _ in p.points) / sum(len(p.points) for p in r[tw.id])
    ca = sum(x for p in r[a.id] for x, _ in p.points) / sum(len(p.points) for p in r[a.id])
    cb = sum(x for p in r[b.id] for x, _ in p.points) / sum(len(p.points) for p in r[b.id])
    assert min(ca, cb) < cx < max(ca, cb)


def test_tween_sweep_stamps_copies():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    single = len(session.resolved()[tw.id])
    session.set_tween_params(tw.id, {"sweep": 7})
    assert len(session.resolved()[tw.id]) == single * 7


def test_tween_follows_live_edits():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 1.0})
    before = session.resolved()[tw.id]
    session.regenerate_layer(b.id, {"sides": 6, "radius": 45})
    after = session.resolved()[tw.id]
    assert [p.points for p in before] != [p.points for p in after]


def test_tween_structural_mode_via_baked_duplicate():
    a = session.add_generated_layer("polygon", {"sides": 5, "radius": 20})
    b = session.duplicate_layer(a.id)
    session.update_layer(b.id, {"transform": {"a": 1, "b": 0, "c": 0, "d": 1, "e": 40, "f": 10}})
    session.consolidate_effects(b.id)  # baked: forces the pointwise-lerp branch
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"t": 1.0})
    _approx_equal(session.resolved()[tw.id], session.resolved()[b.id])


def test_tween_rejects_incompatible_layers():
    a = session.add_generated_layer("polygon", {"sides": 5})
    b = session.add_generated_layer("lissajous", {})
    with pytest.raises(RuntimeError, match="interpolatable"):
        session.create_tween_layer(a.id, b.id)
    with pytest.raises(RuntimeError):
        session.create_tween_layer(a.id, a.id)


def test_tween_blocks_deleting_referenced_layer():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    with pytest.raises(RuntimeError, match="referenced"):
        session.delete_layer(a.id)
    session.delete_layers([a.id, tw.id])  # together is fine
    assert a.id not in {l.id for l in session.project.layers}


def test_tween_missing_ref_resolves_empty_not_crashing():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    # bypass the guard the way a hand-edited project file could
    session.project.layers = [l for l in session.project.layers if l.id != a.id]
    assert session.resolved()[tw.id] == []


def test_lerp_affine_endpoints_and_shortest_arc():
    ma = Affine(a=2, b=0, c=0, d=2, e=10, f=5)            # scale 2
    rot = math.radians(170)
    mb = Affine(a=math.cos(rot), b=math.sin(rot),
                c=-math.sin(rot), d=math.cos(rot), e=-30, f=8)
    for m, ref in ((lerp_affine(ma, mb, 0.0), ma), (lerp_affine(ma, mb, 1.0), mb)):
        for f in "abcdef":
            assert getattr(m, f) == pytest.approx(getattr(ref, f), abs=1e-9)
    # decompose/compose round-trip on a sheared matrix
    ms = Affine(a=1.2, b=0.3, c=-0.5, d=0.9, e=4, f=-2)
    back = compose_affine(*decompose_affine(ms))
    for f in "abcdef":
        assert getattr(back, f) == pytest.approx(getattr(ms, f), abs=1e-9)


def test_lerp_params_rules():
    out = lerp_params({"n": 10, "s": 2.0, "seed": 1, "on": True},
                      {"n": 20, "s": 4.0, "seed": 9, "on": False}, 0.25,
                      {"n": 0, "s": 0.0, "seed": 0, "on": False})
    assert out["n"] == 12 and out["s"] == pytest.approx(2.5)
    assert out["seed"] == 1 and out["on"] is True  # step, not blend
    assert lerp_params({"seed": 1}, {"seed": 9}, 0.9, {"seed": 0})["seed"] == 9


def test_perspective_preserves_closure_and_foreshortens():
    eff = get_effect("perspective")
    sq = Path(points=[(50, 50), (150, 50), (150, 150), (50, 150), (50, 50)], filled=True)
    [out] = eff.apply([sq], eff.Params(tilt_x=45, distance=200), EffectContext())
    assert out.filled and out.points[0] == out.points[-1]
    ys = [y for _, y in out.points]
    xs_top = [x for x, y in out.points if y == min(ys)]
    xs_bot = [x for x, y in out.points if y == max(ys)]
    # the far (top) edge is narrower than the near (bottom) edge
    assert max(xs_top) - min(xs_top) < max(xs_bot) - min(xs_bot)
    # zero tilt is a no-op
    assert eff.apply([sq], eff.Params(tilt_x=0, tilt_y=0), EffectContext()) == [sq]


def test_explode_tween_creates_layer_per_step():
    a, b = _pair()
    tw = session.create_tween_layer(a.id, b.id)
    session.set_tween_params(tw.id, {"sweep": 5})
    per_step = len(session.resolved()[tw.id]) // 5
    created = session.explode_tween(tw.id)
    assert len(created) == 5
    assert all(l.source.type == "baked" for l in created)
    assert not session.project.layer(tw.id).visible  # tween kept, hidden
    r = session.resolved()
    assert all(len(r[l.id]) == per_step for l in created)
    assert session.undo()  # one step undoes the whole explode
    assert created[0].id not in {l.id for l in session.project.layers}
