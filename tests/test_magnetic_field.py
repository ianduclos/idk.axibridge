"""Magnetic-field source: bounded geometry and stable field routes."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from axibridge.registry import effective_bench, get_source, load_builtin_modules
from axibridge.sources.magnetic_field import (
    DEFAULT_MAGNETS,
    Magnet,
    MagneticFieldParams,
    MagneticFieldSource,
)


@pytest.fixture(scope="module")
def source() -> MagneticFieldSource:
    load_builtin_modules()
    return get_source("magnetic_field")


def _field_paths(doc):
    for layer in doc.layers:
        if layer.name == "Magnetic field":
            return layer.paths
    return []


def _annotation_paths(doc):
    for layer in doc.layers:
        if layer.name == "Magnets":
            return layer.paths
    return []


def _small(**updates) -> MagneticFieldParams:
    values = {
        "width": 80,
        "height": 60,
        "density": 24,
        "magnets": [
            {"kind": "bar", "x": 40, "y": 30, "length": 24,
             "thickness": 8, "rotation": 0, "strength": 1,
             "flipped": False},
        ],
    }
    values.update(updates)
    return MagneticFieldParams(**values)


def test_registration_schema_and_placement_contract(source):
    assert source.id == "magnetic_field"
    assert source.label == "Magnetic field"
    assert source.orientation == "geometry"
    assert effective_bench(source) == {
        "adapter": "magnetic-field", "version": 1, "modes": ["new", "resume"]
    }
    assert source.placement_frame({"width": 123, "height": 87}) == (123.0, 87.0)

    schema = source.Params.model_json_schema()
    props = schema["properties"]
    assert {key: props["width"][key] for key in ("default", "minimum", "maximum")} == {
        "default": 240.0, "minimum": 40.0, "maximum": 300.0
    }
    assert {key: props["height"][key] for key in ("default", "minimum", "maximum")} == {
        "default": 170.0, "minimum": 40.0, "maximum": 218.0
    }
    assert props["density"]["default"] == 72
    assert props["density"]["minimum"] == 24
    assert props["density"]["maximum"] == 100
    assert props["style"]["default"] == "continuous"
    assert props["show_magnets"]["default"] is True
    assert props["keep_silhouettes"]["default"] is True
    assert props["remove_escaping"]["default"] is False
    assert props["seed"]["default"] == 90826
    assert props["magnets"]["maxItems"] == 16
    assert props["magnets"]["hidden"] is True
    assert props["magnets"]["default"] == [m.model_dump() for m in DEFAULT_MAGNETS]
    assert {key: props["pole_spacing"][key]
            for key in ("default", "minimum", "maximum")} == {
        "default": 0.0, "minimum": 0.0, "maximum": 3.0,
    }
    assert props["presets"]["default"] == [None, None, None, None]
    assert props["presets"]["minItems"] == 4
    assert props["presets"]["maxItems"] == 4
    assert props["scatter_strength_min"]["default"] == 1.0
    assert props["scatter_strength_max"]["default"] == 1.0
    assert props["mix_x"]["default"] == 0.0
    assert props["mix_y"]["default"] == 0.0
    assert props["mix_active"]["default"] is False
    assert "hidden" not in props["pole_spacing"]
    assert all(props[name].get("hidden") is True for name in (
        "magnets", "scatter_strength_min", "scatter_strength_max", "presets",
        "mix_x", "mix_y", "mix_active",
    ))
    assert all("hidden" not in props[name] for name in (
        "width", "height", "density", "style", "show_magnets",
        "keep_silhouettes", "remove_escaping", "seed", "pole_spacing",
    ))
    magnet_schema = schema["$defs"]["Magnet"]["properties"]
    assert magnet_schema["kind"]["enum"] == ["bar", "north", "south"]
    for field, (low, high) in {
        "x": (0, 300), "y": (0, 218), "rotation": (-180, 180),
        "length": (8, 80), "thickness": (4, 24), "strength": (0.1, 3),
    }.items():
        assert magnet_schema[field]["minimum"] == low
        assert magnet_schema[field]["maximum"] == high
    assert magnet_schema["locked"]["default"] is False


@pytest.mark.parametrize("field,value", [
    ("x", math.nan), ("y", math.inf), ("rotation", -math.inf),
    ("length", math.nan), ("thickness", math.inf), ("strength", math.nan),
])
def test_magnet_rejects_nonfinite_numbers(field, value):
    with pytest.raises(ValidationError):
        Magnet(**{field: value})


@pytest.mark.parametrize("field,value", [
    ("width", math.nan), ("height", math.inf), ("seed", -math.inf),
    ("scatter_strength_min", math.nan), ("scatter_strength_max", math.inf),
    ("mix_x", -math.inf), ("mix_y", math.nan), ("pole_spacing", math.inf),
])
def test_params_reject_nonfinite_numbers(field, value):
    with pytest.raises(ValidationError):
        MagneticFieldParams(**{field: value})


def test_numeric_bounds_and_whole_magnet_frame_bounds_are_rejected():
    with pytest.raises(ValidationError):
        MagneticFieldParams(width=39)
    with pytest.raises(ValidationError):
        MagneticFieldParams(density=101)
    with pytest.raises(ValidationError, match="inside the frame"):
        MagneticFieldParams(width=80, height=60, magnets=[
            {"kind": "bar", "x": 10, "y": 30, "rotation": 45,
             "length": 32, "thickness": 10}
        ])
    with pytest.raises(ValidationError, match="inside the frame"):
        MagneticFieldParams(width=80, height=60, magnets=[
            {"kind": "north", "x": 2, "y": 30}
        ])
    with pytest.raises(ValidationError):
        MagneticFieldParams(magnets=[{"kind": "north", "x": 10 + i * 5, "y": 20}
                                     for i in range(17)])


def test_editor_metadata_is_bounded_strict_and_consistent():
    with pytest.raises(ValidationError):
        MagneticFieldParams(scatter_strength_min=1.2, scatter_strength_max=1.1)
    with pytest.raises(ValidationError):
        MagneticFieldParams(mix_x=1.01)
    with pytest.raises(ValidationError):
        MagneticFieldParams(pole_spacing=3.01)
    with pytest.raises(ValidationError):
        MagneticFieldParams(extra_recipe_value=True)
    with pytest.raises(ValidationError):
        Magnet(unknown=True)

    current = [{"kind": "bar", "x": 40, "y": 30, "length": 24,
                "thickness": 8, "flipped": False}]
    with pytest.raises(ValidationError):
        _small(presets=[None, None, None])
    with pytest.raises(ValidationError, match="magnet count"):
        _small(presets=[[current[0], current[0]], None, None, None])
    with pytest.raises(ValidationError, match="kind and flipped"):
        _small(presets=[[{**current[0], "kind": "north"}], None, None, None])
    with pytest.raises(ValidationError, match="kind and flipped"):
        _small(presets=[[{**current[0], "flipped": True}], None, None, None])
    with pytest.raises(ValidationError, match="inside the frame"):
        _small(presets=[[{**current[0], "x": 3}], None, None, None])
    with pytest.raises(ValidationError, match="all four presets"):
        _small(presets=[current, None, current, current], mix_active=True)

    # Preset dimensions and locks may differ when captures were fit to a small
    # frame; the editor owns interpolation and current locks win there.
    params = _small(presets=[
        [{**current[0], "length": 20, "thickness": 6, "locked": True}],
        current, current, current,
    ], mix_active=True)
    assert params.presets[0][0].locked is True


def test_editor_metadata_json_round_trip():
    magnet = {"kind": "bar", "x": 40, "y": 30, "length": 24,
              "thickness": 8, "locked": True}
    params = _small(
        magnets=[magnet], presets=[[magnet], [magnet], [magnet], [magnet]],
        scatter_strength_min=0.4, scatter_strength_max=2.7,
        mix_x=0.25, mix_y=0.75, mix_active=True, pole_spacing=1.2,
    )
    restored = MagneticFieldParams.model_validate_json(params.model_dump_json())
    assert restored == params


def test_editor_metadata_and_locks_do_not_change_geometry(source):
    baseline = source.generate(_small())
    current = {"kind": "bar", "x": 40, "y": 30, "length": 24,
               "thickness": 8, "locked": True}
    varied = [
        {**current, "x": 30, "rotation": -15, "strength": 0.4},
        {**current, "x": 50, "rotation": 15, "strength": 1.6},
        {**current, "y": 24, "length": 20, "thickness": 6},
        {**current, "y": 36, "length": 28, "thickness": 10},
    ]
    with_metadata = source.generate(_small(
        magnets=[current], presets=[[corner] for corner in varied],
        scatter_strength_min=0.4, scatter_strength_max=2.7,
        mix_x=0.25, mix_y=0.75, mix_active=True,
    ))
    assert with_metadata == baseline


def test_generate_is_deterministic_pure_and_clipped(source):
    params = _small()
    before = params.model_dump()
    a = source.generate(params)
    b = source.generate(params)
    assert a == b
    assert params.model_dump() == before
    assert a.width == 80 and a.height == 60
    assert _field_paths(a)
    for _, path in a.iter_paths():
        assert len(path.points) >= 2
        assert not path.filled
        assert path.length() > 0
        assert all(math.isfinite(v) for point in path.points for v in point)
        assert all(0 <= x <= 80 and 0 <= y <= 60 for x, y in path.points)


def test_hiding_magnets_only_removes_annotation_paths(source):
    shown = source.generate(_small(show_magnets=True))
    hidden = source.generate(_small(show_magnets=False))
    assert _annotation_paths(shown)
    assert not _annotation_paths(hidden)
    assert _field_paths(shown) == _field_paths(hidden)


def test_showing_magnets_forces_the_full_silhouette(source):
    kept = source.generate(_small(show_magnets=True, keep_silhouettes=True))
    forced = source.generate(_small(show_magnets=True, keep_silhouettes=False))
    assert _field_paths(kept) == _field_paths(forced)
    assert _annotation_paths(kept) == _annotation_paths(forced)


def test_hidden_silhouette_can_open_the_bar_while_retaining_small_pole_cores(source):
    params = _small(show_magnets=False, keep_silhouettes=False)
    doc = source.generate(params)
    paths = _field_paths(doc)
    assert paths
    # The former body is x=28..52, y=26..34. Routes may now cross it, while
    # the 0.7-mm numerical cores at x=28 and x=52 still stop integration.
    assert any(29 < x < 51 and 26 < y < 34
               for path in paths for x, y in path.points)
    for pole_x in (28, 52):
        distances = [math.hypot(x - pole_x, y - 30)
                     for path in paths for x, y in path.points]
        assert min(distances) >= 0.7
        assert min(distances) < 1.5


def test_annotation_geometry_is_stroke_only_and_has_labels(source):
    doc = source.generate(_small(magnets=[
        {"kind": "bar", "x": 25, "y": 30, "length": 20, "thickness": 8},
        {"kind": "north", "x": 55, "y": 20},
        {"kind": "south", "x": 55, "y": 40},
    ]))
    annotations = _annotation_paths(doc)
    assert len(annotations) >= 9  # three outlines plus N/S stroke glyphs
    assert all(not path.filled for path in annotations)


def test_annotation_labels_are_clipped_at_a_valid_edge_body(source):
    doc = source.generate(MagneticFieldParams(
        width=40, height=40, density=24, magnets=[
            {"kind": "bar", "x": 4, "y": 2, "length": 8, "thickness": 4}
        ]
    ))
    assert _annotation_paths(doc)
    assert all(0 <= x <= 40 and 0 <= y <= 40
               for path in _annotation_paths(doc) for x, y in path.points)


def test_short_thin_rotated_bar_labels_stay_inside_its_silhouette(source):
    magnet = {"kind": "bar", "x": 40, "y": 30, "rotation": 37,
              "length": 8, "thickness": 4}
    doc = source.generate(_small(magnets=[magnet]))
    angle = math.radians(magnet["rotation"])
    ux, uy = math.cos(angle), math.sin(angle)
    vx, vy = -uy, ux
    for path in _annotation_paths(doc):
        for x, y in path.points:
            dx, dy = x - magnet["x"], y - magnet["y"]
            assert abs(dx * ux + dy * uy) <= magnet["length"] / 2 + 1e-9
            assert abs(dx * vx + dy * vy) <= magnet["thickness"] / 2 + 1e-9


def test_empty_magnets_is_an_empty_document_with_the_requested_frame(source):
    doc = source.generate(MagneticFieldParams(
        width=111, height=77, density=24, magnets=[], show_magnets=True
    ))
    assert doc.layers == []
    assert doc.width == 111 and doc.height == 77


def test_coincident_opposite_poles_terminate_safely(source):
    doc = source.generate(_small(magnets=[
        {"kind": "north", "x": 40, "y": 30, "strength": 1},
        {"kind": "south", "x": 40, "y": 30, "strength": 1},
    ]))
    assert _field_paths(doc) == []
    assert _annotation_paths(doc)


def test_independent_poles_ignore_bar_only_fields(source):
    common = {"kind": "north", "x": 40, "y": 30, "strength": 1}
    a = source.generate(_small(show_magnets=False, magnets=[common]))
    b = source.generate(_small(show_magnets=False, magnets=[{
        **common, "length": 8, "thickness": 24, "rotation": 180, "flipped": True,
    }]))
    assert a == b


def test_remove_escaping_discards_the_whole_one_ended_route(source):
    # Every radial route from one pole ends at its body in one direction and
    # at the frame in the other. Removal must drop the whole joined route.
    magnets = [{"kind": "north", "x": 40, "y": 30}]
    kept = source.generate(_small(magnets=magnets, show_magnets=False,
                                  remove_escaping=False))
    removed = source.generate(_small(magnets=magnets, show_magnets=False,
                                     remove_escaping=True))
    assert len(_field_paths(kept)) > 0
    assert len(_field_paths(removed)) < len(_field_paths(kept))
    assert _field_paths(removed) == []


@pytest.mark.parametrize("style", ["continuous", "chains", "filings"])
def test_all_styles_are_deterministic_nonempty_and_bounded(source, style):
    a = source.generate(_small(style=style, show_magnets=False))
    b = source.generate(_small(style=style, show_magnets=False))
    assert a == b
    assert _field_paths(a)
    assert all(0 <= x <= a.width and 0 <= y <= a.height
               for path in _field_paths(a) for x, y in path.points)


def test_escaping_filter_is_applied_before_texture(source):
    magnets = [{"kind": "north", "x": 40, "y": 30}]
    for style in ("chains", "filings"):
        kept = source.generate(_small(magnets=magnets, style=style,
                                      show_magnets=False, remove_escaping=False))
        removed = source.generate(_small(magnets=magnets, style=style,
                                         show_magnets=False, remove_escaping=True))
        assert _field_paths(kept)
        assert _field_paths(removed) == []


def test_hidden_core_routes_still_apply_whole_route_escaping_filter(source):
    magnets = [{"kind": "north", "x": 40, "y": 30}]
    kept = source.generate(_small(
        magnets=magnets, show_magnets=False, keep_silhouettes=False,
        remove_escaping=False,
    ))
    removed = source.generate(_small(
        magnets=magnets, show_magnets=False, keep_silhouettes=False,
        remove_escaping=True,
    ))
    assert _field_paths(kept)
    assert _field_paths(removed) == []


def test_zero_pole_spacing_preserves_exact_existing_geometry(source):
    assert source.generate(_small()) == source.generate(_small(pole_spacing=0.0))


def test_pole_spacing_is_deterministic_bounded_whole_route_thinning(source):
    baseline = source.generate(_small(show_magnets=False, pole_spacing=0.0))
    spaced = source.generate(_small(show_magnets=False, pole_spacing=2.0))
    repeated = source.generate(_small(show_magnets=False, pole_spacing=2.0))
    baseline_routes = {tuple(path.points) for path in _field_paths(baseline)}
    spaced_routes = {tuple(path.points) for path in _field_paths(spaced)}

    assert spaced == repeated
    assert spaced_routes
    assert len(spaced_routes) < len(baseline_routes)
    assert spaced_routes < baseline_routes
    assert all(0 <= x <= spaced.width and 0 <= y <= spaced.height
               for path in _field_paths(spaced) for x, y in path.points)


def test_escaping_routes_are_removed_before_pole_spacing(monkeypatch, source):
    from axibridge.sources import magnetic_field

    escaping = magnetic_field._Route(
        points=((44.0, 30.0), (45.0, 30.0)), touches_boundary=True,
    )
    contained = magnetic_field._Route(
        points=((44.0, 30.4), (45.0, 30.4)), touches_boundary=False,
    )
    monkeypatch.setattr(
        magnetic_field, "_trace_routes",
        lambda scene, density, seed: [escaping, contained],
    )

    doc = source.generate(_small(
        show_magnets=False, remove_escaping=True, pole_spacing=1.0,
    ))
    assert [path.points for path in _field_paths(doc)] == [list(contained.points)]


def test_session_portrait_regenerate_and_project_recipe_round_trip(tmp_path):
    from axibridge import compose, project_io
    from axibridge.session import session

    recipe = _small(seed=1234).model_dump(mode="json")
    session.project.view = "portrait"
    layer = session.add_generated_layer("magnetic_field", recipe)
    assert layer.source.params == recipe

    placed = compose.transform_paths(session.source_geometry[layer.id], layer.transform)
    assert placed
    assert all(0 <= x <= compose.BED_WIDTH and 0 <= y <= compose.BED_HEIGHT
               for path in placed for x, y in path.points)
    before = session.resolved()[layer.id]

    changed = {**recipe, "magnets": [{**recipe["magnets"][0], "flipped": True}]}
    session.regenerate_layer(layer.id, changed)
    assert session.project.layer(layer.id).source.params["magnets"] == changed["magnets"]
    assert session.resolved()[layer.id] != before

    target = tmp_path / "magnetic-project"
    project_io.save_project(session.project, session.source_geometry,
                            session.svg_files, target)
    project, geometry, _, _, _, _ = project_io.load_project(target)
    restored = project.layer(layer.id)
    assert restored.source.generator == "magnetic_field"
    assert restored.source.params["magnets"] == changed["magnets"]
    assert len(geometry[layer.id]) == len(session.source_geometry[layer.id])


def test_preset_sizes_are_bounded_and_saved_without_affecting_field(source):
    baseline = _small()
    magnets = baseline.model_dump(mode='json')['magnets']
    sizes = [{'length': m['length'], 'thickness': m['thickness']} for m in magnets]
    recipe = MagneticFieldParams(**{
        **baseline.model_dump(), 'presets': [magnets]*4, 'preset_sizes': sizes,
    })
    restored = MagneticFieldParams.model_validate_json(recipe.model_dump_json())
    assert restored.preset_sizes == recipe.preset_sizes
    assert source.generate(restored) == source.generate(baseline)
    for bad in [[], [{'length': float('nan'), 'thickness': 12}], [{'length': 81, 'thickness': 12}]]:
        with pytest.raises(ValidationError):
            MagneticFieldParams(**{**baseline.model_dump(), 'preset_sizes': bad})
