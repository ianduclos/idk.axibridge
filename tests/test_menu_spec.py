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
    assert [m.title for m in menu_spec()] == ["File", "Edit", "View", "Machine"]


def test_undo_and_redo_are_in_edit_and_carry_their_shortcut():
    """The two items whose absence started this. Their shortcut text is read
    from the page so the native menu can show what the page promises."""
    edit = next(m for m in menu_spec() if m.title == "Edit")
    assert edit.actions == (
        MenuItem("Undo", "#btn-undo", "action", "⌘Z"),
        MenuItem("Redo", "#btn-redo", "action", "⇧⌘Z"),
    )


def test_the_view_menu_holds_the_controls_that_left_the_toolbar():
    """Two radio groups and three overlays, in that order, separated. Each is
    the control itself — the selectors address `#view-toggle`, `#mode-toggle`
    and the three real checkboxes, not menu-shaped copies of them."""
    view = next(m for m in menu_spec() if m.title == "View")
    assert [None if i is None else (i.label, i.kind) for i in view.items] == [
        ("Portrait", "radio"), ("Landscape", "radio"), None,
        ("Schematic", "radio"), ("Ink", "radio"), None,
        ("Travel moves", "check"), ("Draw order", "check"), ("Paper guide", "check"),
    ]
    by_label = {i.label: i.selector for i in view.actions}
    assert by_label["Portrait"].startswith("#view-toggle button[data-view=")
    assert by_label["Ink"].startswith("#mode-toggle button[data-mode=")
    assert by_label["Paper guide"] == "#show-guide"


# -- the shapes the parser must keep handling ------------------------------

def _one_menu(inner: str):
    return parse_menubar(
        f'<nav id="menubar"><div class="menu">'
        f'<button class="menu-trigger">T</button>'
        f'<div class="menu-panel">{inner}</div></div></nav>')


def test_a_moved_checkbox_is_addressed_by_its_own_input():
    """A control moved bodily into the menu keeps being the real control —
    the selector must point at the <input>, not the wrapping label, or the
    native menu would click a label and toggle nothing.

    The item AFTER it is the point. `<input>` is a void element with no end
    tag, so a tag stack that pushes it never unwinds, and every depth
    comparison downstream is off by one — which silently dropped the entire
    View menu from the spec the first time the real markup had a checkbox in
    it. A checkbox on its own would not have caught that."""
    (menu,) = _one_menu(
        '<label class="menu-item"><span class="menu-check">✓</span>'
        '<input type="checkbox" id="show-guide" checked>Paper guide</label>'
        '<button class="menu-item" id="after">After</button>')
    assert menu.actions == (
        MenuItem("Paper guide", "#show-guide", "check", None),
        MenuItem("After", "#after", "action", None),
    )
    assert menu.title == "T", "the menu itself still closed"


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


# -- state: what the native menu ticks -------------------------------------

def test_only_items_with_a_state_are_probed():
    """An action has nothing to show. Ticking one would invent state the app
    does not have — the exact thing the menu rule forbids."""
    from axibridge.menu_spec import item_index, stateful_items

    kinds = {i.kind for _m, i in stateful_items()}
    assert kinds <= {"check", "radio"}
    assert "#btn-undo" not in item_index(), "Undo is an action, not a toggle"


def test_the_probe_reads_a_checkbox_and_a_radio_differently():
    """A moved checkbox knows its own state; a radio wears the `.on` class
    main.js maintains. Getting these the wrong way round shows a menu that
    disagrees with the app."""
    from axibridge.menu_spec import state_probe_js

    (menu,) = _one_menu(
        '<div class="menu-group" id="g">'
        '<button class="menu-item on" data-mode="a">A</button></div>'
        '<label class="menu-item"><input type="checkbox" id="c">C</label>')
    js = state_probe_js([menu])
    assert "el.classList.contains('on')" in js
    assert "!!el.checked" in js


def test_the_probe_quotes_its_selectors():
    """It is generated code running in a window with no console — an unquoted
    selector would be a syntax error nobody could see."""
    from axibridge.menu_spec import state_probe_js

    js = state_probe_js()
    assert '"#view-toggle button[data-view=\\"portrait\\"]"' in js
    assert js.startswith("Object.fromEntries([") and js.endswith("].filter(Boolean))")


def test_the_probe_survives_a_control_that_is_not_on_the_page_yet():
    """Tabs render lazily; a probe that assumed every selector resolves would
    throw and take the whole state sync down with it."""
    from axibridge.menu_spec import state_probe_js

    assert "el ? [" in state_probe_js()
    assert ".filter(Boolean)" in state_probe_js()


def test_a_menu_item_may_name_a_control_that_lives_elsewhere():
    """The Machine menu's Pen up IS the Pen up button in Settings › Jog & pen.

    Without `data-target` the parser would fall through to the item's own id
    and the menu item would click itself — a control that appears to work and
    drives nothing. `data-target` is checked BEFORE `id` for that reason, and
    `menu.js` forwards the in-page click off the same attribute, so both bars
    drive the identical element."""
    machine = next(m for m in menu_spec() if m.title == "Machine")
    assert [None if i is None else (i.label, i.selector) for i in machine.items] == [
        ("Pen up", "#btn-pen-up"), ("Pen down", "#btn-pen-down"), None,
        ("Go to origin", "#btn-goto-origin"), ("Set origin", "#btn-set-origin"), None,
        ("Jog up", "#jog-up"), ("Jog down", "#jog-down"),
        ("Jog left", "#jog-left"), ("Jog right", "#jog-right"),
    ]
    assert not any(i.selector.startswith("#menu-") for i in machine.actions), \
        "an item addressing itself would be a control that does nothing"


def test_data_target_wins_over_the_items_own_id():
    (menu,) = _one_menu(
        '<button class="menu-item" id="menu-thing" data-target="#real-thing">Thing</button>')
    assert menu.actions == (MenuItem("Thing", "#real-thing", "action", None),)


def test_the_machine_menu_carries_no_forms():
    """The menu rule, applied: motion parameters and raw EBB are forms, soft
    limits belongs beside the millimetres it guards, holder calibration is a
    procedure. Only actions are in the menu — and none of them is a `check`,
    because nothing here has a state to show."""
    machine = next(m for m in menu_spec() if m.title == "Machine")
    assert {i.kind for i in machine.actions} == {"action"}
    labels = " ".join(i.label.lower() for i in machine.actions)
    for forbidden in ("raw", "ebb", "limit", "calibrat", "motion", "speed"):
        assert forbidden not in labels, f"{forbidden!r} is a panel, not a menu item"