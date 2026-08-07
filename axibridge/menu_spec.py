"""One menu definition, read out of the in-page menu bar.

The app has two menu bars: the in-page one (`static/index.html`'s `#menubar`,
the only menu a browser tab has) and the macOS system one (built in
`launch/axibridge_app.py`, the only menu the app shell shows — the in-page bar
is `display:none` under `[data-shell="native"]`). They were two hand-written
lists, and on 2026-08-07 that cost exactly what two lists always cost: the
Edit menu's Undo/Redo and the View menu's orientation existed in the page and
never appeared natively, so from the app shell the work looked undone.

The old defence was that every native item proxy-clicks a real control, so it
cannot drift. That is true of BEHAVIOUR and says nothing about MEMBERSHIP —
an item added to one list is simply absent from the other, which is the
failure that happened.

So the native menu is no longer written. It is DERIVED, here, by parsing the
in-page bar's markup: add an item to `index.html` and it appears in both. The
parse is a pure function over the HTML text with no browser and no server, so
`tests/test_menu_spec.py` can hold the two bars together in the ordinary
suite — which is the point, because the app shell is the one surface headless
tests cannot look at.

What an item carries is a *selector*, not a callback: the native menu clicks
the very control the page already has, so the in-page markup stays the single
implementation. Moving a control bodily into the menu (the `#view-toggle`
pattern) therefore keeps working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

#: attributes that distinguish one button in a radio group from its siblings.
#: Explicit rather than "any data-*" so a decorative data attribute added
#: later cannot silently become part of a selector.
RADIO_ATTRS = ("data-view", "data-mode", "data-tool")


@dataclass(frozen=True)
class MenuItem:
    label: str
    #: CSS selector for the control this item activates, in the page.
    selector: str
    #: "action" | "check" (has its own checkbox) | "radio" (one of a group)
    kind: str
    #: the shortcut as the page writes it ("⌘Z"), or None
    key: str | None = None


@dataclass(frozen=True)
class MenuDef:
    title: str
    #: items in order; ``None`` is a separator
    items: tuple[MenuItem | None, ...]

    @property
    def actions(self) -> tuple[MenuItem, ...]:
        return tuple(i for i in self.items if i is not None)


def _classes(attrs: dict[str, str]) -> set[str]:
    return set((attrs.get("class") or "").split())


class _MenubarParser(HTMLParser):
    """Walks `#menubar` and collects one MenuDef per `.menu`.

    Written against the shape the markup actually has rather than a general
    HTML query engine: a `.menu` holds one `.menu-trigger` and one
    `.menu-panel`, and the panel holds `.menu-item`s, `.menu-sep`s, and
    `.menu-group` wrappers that only exist to give a radio group an id.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.menus: list[MenuDef] = []
        self._stack: list[dict[str, str]] = []
        self._in_menubar = False
        self._title: str | None = None
        self._items: list[MenuItem | None] = []
        # the element currently being read as a trigger or an item
        self._reading: str | None = None   # "trigger" | "item"
        self._depth_at_read = 0
        self._text: list[str] = []
        self._key: list[str] = []
        self._skip_text = 0                # inside .menu-check / .menu-key
        self._item_attrs: dict[str, str] = {}
        self._item_input: str | None = None

    # -- helpers ---------------------------------------------------------

    def _enclosing_id(self) -> str | None:
        """The nearest ancestor carrying an id — how a radio button in a group
        is addressed (`#view-toggle button[data-view="portrait"]`).

        Called from `handle_endtag`, where the item itself has already been
        popped, so the whole remaining stack is ancestors."""
        for el in reversed(self._stack):
            if el.get("id"):
                return el["id"]
        return None

    def _finish_item(self, tag: str) -> None:
        label = "".join(self._text).strip()
        attrs = self._item_attrs
        key = "".join(self._key).strip() or None

        if self._item_input:                      # a real checkbox moved here
            selector, kind = f"#{self._item_input}", "check"
        elif attrs.get("id"):
            selector, kind = f"#{attrs['id']}", "action"
        else:
            radio = next(((a, attrs[a]) for a in RADIO_ATTRS if a in attrs), None)
            group = self._enclosing_id()
            if radio is None or group is None:
                # An item we cannot address is worse than no item: the native
                # menu would show a row that does nothing. Drop it, and let
                # the test that compares the two bars fail loudly.
                self._reading = None
                return
            selector = f'#{group} {tag}[{radio[0]}="{radio[1]}"]'
            kind = "radio"

        self._items.append(MenuItem(label=label, selector=selector, kind=kind, key=key))
        self._reading = None

    # -- parser hooks ----------------------------------------------------

    def handle_starttag(self, tag: str, attrlist) -> None:
        attrs = {k: (v or "") for k, v in attrlist}
        self._stack.append(attrs)
        cls = _classes(attrs)

        if attrs.get("id") == "menubar":
            self._in_menubar = True
        if not self._in_menubar:
            return

        if "menu" in cls and "menu-item" not in cls and self._title is None:
            self._title, self._items = "", []
        if "menu-trigger" in cls:
            self._reading, self._text, self._depth_at_read = "trigger", [], len(self._stack)
        elif "menu-item" in cls:
            self._reading, self._depth_at_read = "item", len(self._stack)
            self._text, self._key = [], []
            self._item_attrs, self._item_input = attrs, None
        elif "menu-sep" in cls:
            self._items.append(None)
        elif self._reading == "item":
            if "menu-check" in cls or "menu-key" in cls:
                self._skip_text += 1
            if tag == "input" and attrs.get("type") == "checkbox" and attrs.get("id"):
                self._item_input = attrs["id"]

    def handle_startendtag(self, tag: str, attrlist) -> None:
        self.handle_starttag(tag, attrlist)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if not self._in_menubar or self._reading is None:
            return
        if self._skip_text:
            if _classes(self._stack[-1]) & {"menu-key"}:
                self._key.append(data)
            return
        self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        attrs = self._stack.pop()
        cls = _classes(attrs)
        if not self._in_menubar:
            return

        if "menu-check" in cls or "menu-key" in cls:
            self._skip_text = max(0, self._skip_text - 1)

        if self._reading and len(self._stack) + 1 == self._depth_at_read:
            if self._reading == "trigger":
                self._title, self._reading = "".join(self._text).strip(), None
            else:
                self._finish_item(tag)
        elif "menu" in cls and "menu-item" not in cls and self._title is not None:
            self.menus.append(MenuDef(title=self._title, items=tuple(self._items)))
            self._title = None
        elif attrs.get("id") == "menubar":
            self._in_menubar = False


def parse_menubar(html: str) -> list[MenuDef]:
    """The in-page menu bar, as data. Pure — no browser, no server."""
    p = _MenubarParser()
    p.feed(html)
    return p.menus


def menu_spec(index_html: Path | None = None) -> list[MenuDef]:
    """The shipped menu bar. Reads the SOURCE `index.html`, never the build:
    the build only ever rewrites asset URLs, and the shell must work on a
    machine that has never run npm."""
    path = index_html or (Path(__file__).parent / "static" / "index.html")
    return parse_menubar(path.read_text(encoding="utf-8"))
