"""The two menu bars cannot drift apart.

The app shell shows the macOS menu bar and hides the in-page one, so the
in-page bar is the surface headless tests can see and the native bar is the
surface Ian actually uses. On 2026-08-07 they were two hand-written lists and
the Edit menu's Undo/Redo and the View menu's orientation never reached the
native one — the work looked undone from the app.

The native menu is derived now (`axibridge.menu_spec`), so that particular
divergence is impossible by construction. What these tests protect is the
derivation itself: an item the parser cannot address is dropped SILENTLY, and
a silently dropped item is a menu row that exists in a browser tab and not in
the app — the same bug wearing a different hat.
"""

import re
from pathlib import Path

from axibridge.menu_spec import MenuItem, menu_spec, parse_menubar

INDEX = Path(__file__).resolve().parent.parent / "axibridge" / "static" / "index.html"


def _markup_item_count() -> int:
    """`.menu-item` elements in the shipped markup, counted independently of
    the parser under test — a parser that miscounts must not be able to agree
    with itself."""
    body = INDEX.read_text(encoding="utf-8")
    bar = body[body.index('id="menubar"'):]
    bar = bar[:bar.index("</nav>")]
    return len(re.findall(r'class="[^"]*\bmenu-item\b', bar))


def test_every_menu_item_in_the_markup_is_addressable():
    """The failure this exists for: an item is added to index.html in a shape
    the parser can't turn into a selector, so it quietly never appears in the
    app shell's menu. Counts must agree exactly."""
    parsed = sum(len(m.actions) for m in menu_spec())
    assert parsed == _markup_item_count(), (
        "an item in #menubar produced no menu entry — it has no id, no "
        "checkbox and no recognised data-* attribute inside an element with "
        "an id, so the native menu would silently omit it"
    )


def test_the_menus_are_the_ones_the_page_shows():
    assert [m.title for m in menu_spec()] == ["File", "Edit", "View"]


def test_undo_and_redo_are_in_edit_and_carry_their_shortcut():
    """The two items whose absence started this. Their shortcut text is read
    from the page so the native menu can show what the page promises."""
    edit = next(m for m in menu_spec() if m.title == "Edit")
    assert edit.actions == (
        MenuItem("Undo", "#btn-undo", "action", "⌘Z"),
        MenuItem("Redo", "#btn-redo", "action", "⇧⌘Z"),
    )


def test_orientation_is_in_view_and_addresses_the_real_buttons():
    view = next(m for m in menu_spec() if m.title == "View")
    assert [i.label for i in view.actions] == ["Portrait", "Landscape"]
    for item in view.actions:
        assert item.kind == "radio"
        assert item.selector.startswith("#view-toggle button[data-view=")


# -- the shapes the parser must keep handling ------------------------------

def _one_menu(inner: str):
    return parse_menubar(
        f'<nav id="menubar"><div class="menu">'
        f'<button class="menu-trigger">T</button>'
        f'<div class="menu-panel">{inner}</div></div></nav>')


def test_a_moved_checkbox_is_addressed_by_its_own_input():
    """A control moved bodily into the menu keeps being the real control —
    the selector must point at the <input>, not the wrapping label, or the
    native menu would click a label and toggle nothing."""
    (menu,) = _one_menu(
        '<label class="menu-item"><span class="menu-check">✓</span>'
        '<input type="checkbox" id="show-guide" checked>Paper guide</label>')
    assert menu.actions == (MenuItem("Paper guide", "#show-guide", "check", None),)


def test_a_separator_survives_as_a_separator():
    (menu,) = _one_menu(
        '<button class="menu-item" id="a">A</button>'
        '<div class="menu-sep"></div>'
        '<button class="menu-item" id="b">B</button>')
    assert menu.items == (
        MenuItem("A", "#a", "action", None), None, MenuItem("B", "#b", "action", None))


def test_the_check_glyph_never_leaks_into_the_label():
    """The tick and the shortcut are chrome; a native menu that titled an item
    "✓Undo⌘Z" would be reading the page's decoration as its name."""
    (menu,) = _one_menu(
        '<button class="menu-item" id="x"><span class="menu-check">✓</span>'
        'Thing<span class="menu-key">⌘K</span></button>')
    assert menu.actions == (MenuItem("Thing", "#x", "action", "⌘K"),)


def test_an_unaddressable_item_is_dropped_rather_than_faked():
    """Better a missing row than a row that does nothing — and the count test
    above turns the drop into a failure."""
    (menu,) = _one_menu('<button class="menu-item">Nameless</button>')
    assert menu.actions == ()
