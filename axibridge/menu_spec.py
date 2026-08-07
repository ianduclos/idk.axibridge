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

#: HTML void elements: they have no end tag, so `handle_endtag` never fires
#: for them and a naive tag stack never unwinds past one. The checkbox inside
#: a moved menu item is exactly this case — with `<input>` left on the stack,
#: every depth comparison after it was off by one and the View menu vanished
#: from the spec entirely (silently, which is this parser's whole hazard).
VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img",
                       "input", "link", "meta", "param", "source", "track", "wbr"})

#: kinds that carry a visible state — the only ones worth probing or ticking.
#: An "action" has nothing to show, and giving it a checkmark would invent
#: state the app does not have.
STATEFUL = ("check", "radio")

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

        if attrs.get("data-target"):
            # The item names the control it drives, because that control lives
            # somewhere else — the Machine menu's Pen up is the Pen up BUTTON
            # in Settings › Jog & pen. Without this the parser would derive the
            # menu item's own id and the item would click itself. Checked
            # before `id` for exactly that reason.
            selector, kind = attrs["data-target"], "action"
        elif self._item_input:                    # a real checkbox moved here
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

        if tag in VOID_TAGS:
            self._stack.pop()          # no end tag is coming; balance it here

    def handle_startendtag(self, tag: str, attrlist) -> None:
        self.handle_starttag(tag, attrlist)
        if tag not in VOID_TAGS:       # handle_starttag already popped it
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


def stateful_items(spec: list[MenuDef] | None = None) -> list[tuple[MenuDef, MenuItem]]:
    """Every item that has a state to show, with the menu it lives in."""
    spec = spec if spec is not None else menu_spec()
    return [(m, i) for m in spec for i in m.actions if i.kind in STATEFUL]


def state_probe_js(spec: list[MenuDef] | None = None) -> str:
    """A JS expression evaluating to ``{selector: is_it_on}`` for every item.

    The app shell's system menu has to SHOW state (a ticked "Paper guide"),
    and the page is the only thing that knows it. This generates the probe
    rather than shipping a hand-written one in `menu.js`, for the same reason
    the menu itself is derived: how an item's state is read follows from its
    kind, and a second implementation in JS would be a second place to get
    the mapping wrong.

    The page therefore only has to say *when* something changed; what to look
    at, and where, comes from here.
    """
    parts = []
    for _menu, item in stateful_items(spec):
        # a real checkbox carries its own state; a radio wears the `.on` class
        # main.js already maintains for the in-page menu
        read = "!!el.checked" if item.kind == "check" else "el.classList.contains('on')"
        sel = _js_string(item.selector)
        parts.append(f"(() => {{ const el = document.querySelector({sel});"
                     f" return el ? [{sel}, {read}] : null; }})()")
    return "Object.fromEntries([" + ", ".join(parts) + "].filter(Boolean))"


def _js_string(text: str) -> str:
    """A JS string literal. Selectors here are ours, but generating code from
    data without quoting it is how a stray apostrophe becomes a syntax error
    in a window you cannot open a console on."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def item_index(spec: list[MenuDef] | None = None) -> dict[str, tuple[str, str]]:
    """selector -> (menu title, item label), for pointing a native menu item
    at the state the probe reports."""
    return {i.selector: (m.title, i.label) for m, i in stateful_items(spec)}
