"""Glyph grammar: contract (determinism, frame, bounds) + the abstraction dial."""

from axibridge.registry import get_source


def _paths(doc):
    return [p for layer in doc.layers for p in layer.paths]


def test_registered_and_deterministic():
    g = get_source("glyphgram")
    a = g.generate(g.Params(text="AXI", seed=3))
    b = g.generate(g.Params(text="AXI", seed=3))
    assert [p.points for p in _paths(a)] == [p.points for p in _paths(b)]
    c = g.generate(g.Params(text="AXI", seed=4))
    assert [p.points for p in _paths(a)] != [p.points for p in _paths(c)]


def test_machine_frame_non_negative():
    g = get_source("glyphgram")
    doc = g.generate(g.Params(text="", abstraction=1.0, scatter=60.0, echoes=4, seed=9))
    pts = [pt for p in _paths(doc) for pt in p.points]
    assert pts and all(x >= 0 and y >= 0 for x, y in pts)


def test_abstraction_dial_changes_output():
    g = get_source("glyphgram")
    calm = _paths(g.generate(g.Params(text="OEHLEN", abstraction=0.0, echoes=0, seed=1)))
    wild = _paths(g.generate(g.Params(text="OEHLEN", abstraction=0.9, echoes=0, seed=1)))

    def area(ps):
        xs = [x for p in ps for x, _ in p.points]
        ys = [y for p in ps for _, y in p.points]
        return (max(xs) - min(xs)) * (max(ys) - min(ys))

    # displacement/rotation/scale blow the composition open with abstraction
    assert area(wild) > area(calm) * 1.3
    assert [p.points for p in calm] != [p.points for p in wild]


def test_soup_and_fonts():
    g = get_source("glyphgram")
    for font in ("gothiceng", "astrology", "japanese"):
        doc = g.generate(g.Params(text="", font=font, soup_glyphs=16, seed=2))
        assert _paths(doc), font
    assert all(not p.filled for p in _paths(doc))  # stroke-only vocabulary
