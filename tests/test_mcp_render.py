import io

import pytest

pytest.importorskip("mcp")
from PIL import Image  # noqa: E402

from axibridge_mcp import render  # noqa: E402

PAPER = (0xFF, 0xFC, 0xF0)
LINE = [{"id": "a", "visible": True, "color": "#100F0F", "line_diameter_mm": 0.5,
         "paths": [{"points": [[10.0, 10.0], [290.0, 208.0]], "filled": False}]}]


def decode(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGB")


def test_landscape_render_is_bed_shaped_and_draws_the_path():
    img = decode(render.render_layers(LINE, bed=(300.0, 218.0), guide=None, travel=None,
                                      view="landscape", size=600))
    assert img.size == (600, round(218 * 600 / 300))
    mid = img.getpixel((300, round(109 * 2)))  # (150, 109) mm lies on the diagonal
    assert mid != PAPER


def test_portrait_render_swaps_axes_and_puts_origin_top_right():
    dot = [{"id": "o", "visible": True, "color": "#100F0F", "line_diameter_mm": 2.0,
            "paths": [{"points": [[1.0, 1.0], [6.0, 1.0]], "filled": False}]}]
    img = decode(render.render_layers(dot, bed=(300.0, 218.0), guide=None, travel=None,
                                      view="portrait", size=600))
    w, h = img.size
    assert (w, h) == (round(218 * 600 / 300), 600)
    assert img.getpixel((w - 3, 6)) != PAPER      # near top-right
    assert img.getpixel((3, 6)) == PAPER          # top-left stays empty


def test_hidden_layers_are_not_drawn():
    hidden = [{**LINE[0], "visible": False}]
    img = decode(render.render_layers(hidden, bed=(300.0, 218.0), guide=None, travel=None,
                                      view="landscape", size=600))
    assert img.getpixel((300, 218)) == PAPER


def test_contact_sheet_lays_tiles_in_a_grid_with_captions():
    tiles = [(render.fit_lines([[[0, 0], [10, 10]]], 100), f"{i}") for i in range(3)]
    img = decode(render.contact_sheet(tiles))
    assert img.size[0] == 2 * 100          # ceil(sqrt(3)) = 2 columns
    assert img.size[1] > 2 * 100           # two rows plus caption strips


def test_fit_lines_survives_empty_and_degenerate_input():
    assert render.fit_lines([], 50).size == (50, 50)
    assert render.fit_lines([[[5, 5]]], 50).size == (50, 50)
