"""The Territory source replays the bench's kept strokes verbatim and bounded."""
import pytest
from pydantic import ValidationError

from axibridge.registry import describe_modules, get_source, load_builtin_modules

load_builtin_modules()


def _gen(params):
    src = get_source("territory")
    return src.generate(src.Params(**params))


def test_strokes_come_back_verbatim():
    strokes = [[(10.0, 20.0), (30.5, 40.25), (50.0, 60.0)], [(100.0, 100.0), (101.0, 102.0)]]
    doc = _gen({"strokes": strokes, "recipe": {"seed": 7, "density": 1.0, "continue": 1.4}})
    assert [p.points for p in doc.layers[0].paths] == [[tuple(q) for q in s] for s in strokes]
    assert (doc.width, doc.height) == (300.0, 218.0)


def test_recipe_accepts_the_bench_keys_and_bounds_them():
    src = get_source("territory")
    p = src.Params(recipe={"seed": 13, "continue": 2, "mutate": 1.5, "unknown": 3})
    assert p.recipe.cont == 2 and p.recipe.mutate == 1.5 and p.recipe.fill == "grown"
    assert src.Params(recipe={"fill": "v8"}).recipe.fill == "v8"
    with pytest.raises(ValidationError):
        src.Params(recipe={"fill": "other"})
    with pytest.raises(ValidationError):
        src.Params(recipe={"density": 3})
    with pytest.raises(ValidationError):
        src.Params(recipe={"seed": 0})


def test_points_are_clamped_to_the_bed_and_degenerate_strokes_dropped():
    doc = _gen({"strokes": [[(-5.0, 10.0), (400.0, 300.0)], [(1.0, 1.0)]]})
    assert doc.layers[0].paths[0].points == [(0.0, 10.0), (300.0, 218.0)]
    assert len(doc.layers[0].paths) == 1


def test_empty_is_a_valid_empty_document():
    assert _gen({}).layers == []


def test_declares_the_territory_bench():
    info = describe_modules()["sources"]
    entry = info["territory"] if isinstance(info, dict) else next(s for s in info if s["id"] == "territory")
    assert entry["bench"] == {"adapter": "territory", "version": 1, "modes": ["new", "resume"]}
