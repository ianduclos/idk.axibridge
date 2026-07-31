"""Text source: CamBam stick fonts (fontTools) + vpype Hershey fonts."""

import pytest

from axibridge.registry import get_source, sources


def _gen(**params):
    src = get_source("text")
    return src.generate(src.Params(**params))


def _paths(doc):
    return [p for layer in doc.layers for p in layer.paths]


def test_registered():
    assert "text" in sources()
    assert get_source("text").label == "Text"


def test_empty_text_is_an_empty_doc():
    doc = _gen(text="")
    assert doc.layers == [] or all(not layer.paths for layer in doc.layers)


def test_stick_font_renders_nonempty():
    doc = _gen(text="Hi", font="stick3")
    paths = _paths(doc)
    assert paths
    assert all(len(p.points) >= 2 for p in paths)


def test_all_stick_fonts_render():
    for i in range(10):
        doc = _gen(text="A9", font=f"stick{i}")
        assert _paths(doc), f"stick{i} produced no geometry"


def test_hershey_font_renders_nonempty():
    doc = _gen(text="Hi", font="futural")
    assert _paths(doc)


def test_block_top_left_at_origin():
    doc = _gen(text="Hi", font="stick0")
    xs = [x for p in _paths(doc) for x, _ in p.points]
    ys = [y for p in _paths(doc) for _, y in p.points]
    assert min(xs) == pytest.approx(0.0, abs=1e-6)
    assert min(ys) == pytest.approx(0.0, abs=1e-6)


def test_multiline_stacks_downward():
    one = _gen(text="AB", font="stick0")
    two = _gen(text="AB\nAB", font="stick0", size=10.0, line_spacing=1.5)
    y1 = max(y for p in _paths(one) for _, y in p.points)
    y2 = max(y for p in _paths(two) for _, y in p.points)
    # second copy of the same line lands ~one line-step (15mm) below the first
    assert y2 - y1 == pytest.approx(15.0, abs=0.5)


def test_dedupe_toggle_keeps_output_valid():
    on = _gen(text="Hello", font="stick0", dedupe=True)
    off = _gen(text="Hello", font="stick0", dedupe=False)
    n_on = sum(len(p.points) for p in _paths(on))
    n_off = sum(len(p.points) for p in _paths(off))
    assert n_on <= n_off  # dedupe only ever removes segments
    assert n_on > 0


def test_deterministic():
    a = _gen(text="The quick brown fox", font="stick5")
    b = _gen(text="The quick brown fox", font="stick5")
    assert [p.points for p in _paths(a)] == [p.points for p in _paths(b)]


def test_missing_glyph_is_blank_advance_not_a_crash():
    doc = _gen(text="AµB", font="stick0")  # µ is not in these fonts
    assert _paths(doc)


def test_text_length_capped():
    src = get_source("text")
    with pytest.raises(Exception):
        src.Params(text="x" * 2001)


def test_params_not_mutated():
    src = get_source("text")
    params = src.Params(text="Hi", font="stick0")
    before = params.model_dump()
    src.generate(params)
    assert params.model_dump() == before
