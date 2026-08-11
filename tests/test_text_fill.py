"""Text (filled) source: real font outlines as closed, fillable shapes."""

import pytest

from axibridge.registry import get_source, sources
from axibridge.sources import _fontglyph as fg


def _gen(**params):
    src = get_source("text_fill")
    return src.generate(src.Params(**params))


def _paths(doc):
    return [p for layer in doc.layers for p in layer.paths]


def test_registered():
    assert "text_fill" in sources()
    assert get_source("text_fill").label == "Text (filled)"


def test_empty_text_is_an_empty_doc():
    doc = _gen(text="")
    assert doc.layers == [] or all(not layer.paths for layer in doc.layers)


def test_renders_nonempty_and_every_ring_is_closed_and_filled():
    doc = _gen(text="Hi")
    paths = _paths(doc)
    assert paths
    for p in paths:
        assert p.filled
        assert p.is_closed
        assert len(p.points) >= 4


@pytest.mark.parametrize("ch,min_rings", [("o", 2), ("e", 2), ("a", 2), ("B", 3)])
def test_counters_produce_extra_rings(ch, min_rings):
    # "o"/"e"/"a" each have one counter (2 rings: outer + hole), "B" has two
    # (3 rings) -- with skia-pathops resolving Recursive's own overlapping
    # contour authoring correctly (see _fontglyph.py's docstring).
    doc = _gen(text=ch)
    assert len(_paths(doc)) >= min_rings


def test_block_top_left_at_origin():
    doc = _gen(text="Hi")
    paths = _paths(doc)
    xs = [x for p in paths for x, _ in p.points]
    ys = [y for p in paths for _, y in p.points]
    assert min(xs) == pytest.approx(0.0, abs=1e-6)
    assert min(ys) == pytest.approx(0.0, abs=1e-6)


def test_multiline_stacks_downward():
    one = _gen(text="AB")
    two = _gen(text="AB\nAB", size=10.0, line_spacing=1.5)
    y1 = max(y for p in _paths(one) for _, y in p.points)
    y2 = max(y for p in _paths(two) for _, y in p.points)
    assert y2 - y1 == pytest.approx(15.0, abs=0.5)


def test_missing_glyph_is_blank_advance_not_a_crash():
    doc = _gen(text="A\U0001F600B")  # an emoji isn't in Recursive
    assert _paths(doc)


def test_composite_glyphs_decompose_into_closed_rings():
    # accented characters are composite glyphs (base + mark component) in
    # most fonts, including Recursive -- exercises DecomposingRecordingPen
    doc = _gen(text="café Zürich")
    paths = _paths(doc)
    assert paths
    assert all(p.filled and p.is_closed for p in paths)


def test_weight_axis_changes_geometry():
    light = _gen(text="I", weight=300)
    bold = _gen(text="I", weight=1000)
    assert bold.width > light.width


def test_deterministic():
    a = _gen(text="The quick brown fox")
    b = _gen(text="The quick brown fox")
    assert [p.points for p in _paths(a)] == [p.points for p in _paths(b)]


def test_text_length_capped():
    src = get_source("text_fill")
    with pytest.raises(Exception):
        src.Params(text="x" * 2001)


def test_params_not_mutated():
    src = get_source("text_fill")
    params = src.Params(text="Hi")
    before = params.model_dump()
    src.generate(params)
    assert params.model_dump() == before


# -- overlap-resolution backend --------------------------------------------------


def test_solver_name_reports_raw_when_use_pathops_false(monkeypatch):
    monkeypatch.setattr(fg, "USE_PATHOPS", False)
    assert fg.solver_name() == "raw"


def test_fallback_without_pathops_still_produces_valid_closed_rings(monkeypatch):
    monkeypatch.setattr(fg, "USE_PATHOPS", False)
    doc = _gen(text="Bob")
    paths = _paths(doc)
    assert paths
    for p in paths:
        assert p.filled
        assert p.is_closed
        assert len(p.points) >= 4
