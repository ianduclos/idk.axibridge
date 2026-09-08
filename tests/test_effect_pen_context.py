"""Assigned pen width reaches every effect context and its resolve caches."""

from pydantic import BaseModel

from axibridge import registry
from axibridge.model import Path
from axibridge.registry import EffectContext, EffectModule
from axibridge.session import session
from axibridge.stores import Pen, pen_library


class _NoParams(BaseModel):
    pass


class _WidthMarker(EffectModule):
    id = "test_width_marker"
    label = "test width marker"
    Params = _NoParams

    def apply(self, paths, params, ctx):
        return [*paths, Path(points=[(ctx.line_diameter_mm, 0.0)])]


def _install(monkeypatch):
    monkeypatch.setitem(registry._EFFECTS, _WidthMarker.id, _WidthMarker())


def _pen(width):
    return pen_library.upsert(Pen(name=f"test {width}", line_diameter_mm=width))


def _marker_x(paths):
    return paths[-1].points[0][0]


def test_effect_context_default_matches_compose_fallback():
    from axibridge.compose import DEFAULT_LINE_DIAMETER_MM

    assert EffectContext().line_diameter_mm == DEFAULT_LINE_DIAMETER_MM


def test_normal_effect_width_change_invalidates_shaped_cache(monkeypatch):
    _install(monkeypatch)
    layer = session.add_generated_layer("polygon", {"sides": 3, "radius": 5})
    pen = _pen(0.3)
    session.update_layer(layer.id, {
        "pen_id": pen.id,
        "effects": [{"effect": _WidthMarker.id, "enabled": True, "params": {}}],
    })

    assert _marker_x(session.resolved()[layer.id]) == 0.3
    assert session._shaped_cache[layer.id]
    session.project.pens_used[pen.id].line_diameter_mm = 1.7
    assert _marker_x(session.resolved()[layer.id]) == 1.7


def test_region_effect_receives_region_pen_width(monkeypatch):
    _install(monkeypatch)
    below = session.add_generated_layer(
        "grid", {"width": 10, "height": 10, "cells_x": 1, "cells_y": 1, "margin": 0})
    region = session.add_generated_layer("rectangle", {"width": 20, "height": 20})
    pen = _pen(2.2)
    session.update_layer(region.id, {
        "region": True,
        "pen_id": pen.id,
        "effects": [{"effect": _WidthMarker.id, "enabled": True, "params": {}}],
    })

    assert _marker_x(session.resolved()[below.id]) == 2.2
    session.project.pens_used[pen.id].line_diameter_mm = 3.4
    assert _marker_x(session.resolved()[below.id]) == 3.4


def test_tween_effect_width_change_invalidates_tween_cache(monkeypatch):
    _install(monkeypatch)
    a = session.add_generated_layer("polygon", {"sides": 3, "radius": 5})
    b = session.duplicate_layer(a.id)
    effect = [{"effect": _WidthMarker.id, "enabled": True, "params": {}}]
    session.update_layer(a.id, {"effects": effect})
    session.update_layer(b.id, {"effects": effect})
    tween = session.create_tween_layer(a.id, b.id)
    pen = _pen(0.6)
    session.update_layer(tween.id, {"pen_id": pen.id})

    assert _marker_x(session.resolved()[tween.id]) == 0.6
    first_entries = len(session._tween_cache[tween.id])
    session.project.pens_used[pen.id].line_diameter_mm = 1.9
    assert _marker_x(session.resolved()[tween.id]) == 1.9
    assert len(session._tween_cache[tween.id]) == first_entries + 1


def test_effect_preview_matches_resolve_with_assigned_pen(monkeypatch):
    _install(monkeypatch)
    layer = session.add_generated_layer("polygon", {"sides": 3, "radius": 5})
    pen = _pen(0.18)
    effects = [{"effect": _WidthMarker.id, "enabled": True, "params": {}}]
    session.update_layer(layer.id, {"pen_id": pen.id, "effects": effects})

    resolved = session.resolved()[layer.id]
    preview = session.preview_layer_effects(layer.id, effects)
    assert preview == resolved
    assert _marker_x(preview) == 0.18


def test_consolidate_preserves_pen_dependent_resolve(monkeypatch):
    _install(monkeypatch)
    layer = session.add_generated_layer("polygon", {"sides": 3, "radius": 5})
    pen = _pen(0.21)
    session.update_layer(layer.id, {
        "pen_id": pen.id,
        "effects": [{"effect": _WidthMarker.id, "enabled": True, "params": {}}],
    })
    before = session.resolved()[layer.id]

    session.consolidate_effects(layer.id)
    after = session.resolved()[layer.id]
    assert after == before
    assert _marker_x(after) == 0.21


def test_merge_shapes_each_layer_with_its_assigned_pen(monkeypatch):
    _install(monkeypatch)
    a = session.add_generated_layer("polygon", {"sides": 3, "radius": 5})
    b = session.add_generated_layer("polygon", {"sides": 4, "radius": 6})
    thin, broad = _pen(0.16), _pen(0.9)
    effect = [{"effect": _WidthMarker.id, "enabled": True, "params": {}}]
    session.update_layer(a.id, {"pen_id": thin.id, "effects": effect})
    session.update_layer(b.id, {"pen_id": broad.id, "effects": effect})

    merged = session.merge_layers([a.id, b.id])
    markers = [p.points[0][0] for p in session.source_geometry[merged.id]
               if len(p.points) == 1]
    assert markers == [0.16, 0.9]
