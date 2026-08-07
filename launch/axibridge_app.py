"""axibridge app shell: a pywebview window instead of a browser tab.

Double-clicked via launch/AxiBridge.app (no Terminal). Lifecycle contract:

* If a server is already listening on the port (started from a terminal, or
  a second app window), ATTACH to it and leave it running on close — this
  shell never kills a server it didn't start.
* Otherwise SPAWN ``.venv/bin/python -m axibridge`` (bound to 127.0.0.1 —
  the windowed app is a desk tool; the wide-open LAN bind stays a choice of
  the terminal launcher) and terminate it when the window closes.
* Closing is refused while a plot is running on an owned server — stop the
  job first. The server log is readable in the UI (Settings → Server log).
* On macOS the window title bar is merged into the app's own header, and the
  menus are served from the real system menu bar — DERIVED from the in-page
  bar (`axibridge.menu_spec`), never written twice, and folded into
  pywebview's own Edit/View so the two bars read the same. All best-effort:
  if any of it fails the app still starts, with the standard title bar and
  the in-page menu.

Import-safe: no side effects at import time (unit tests import the helpers).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYTHON = REPO / ".venv" / "bin" / "python"
PORT = 2942
URL = f"http://127.0.0.1:{PORT}"

#: Every AppKit poke in this file is best-effort and swallows its exception,
#: because a failed cosmetic tweak must never stop the app opening. The cost
#: showed up on 2026-08-07: three menu bugs in a row that did nothing, raised
#: nothing and left no trace, and each one cost a round trip through Ian
#: relaunching the app to find out. Finder gives the bundle no stderr, so
#: "best-effort" has to mean "leaves a record", not "is invisible".
SHELL_LOG = Path.home() / "Library" / "Logs" / "axibridge-shell.log"


def on_main(fn, what: str) -> bool:
    """Run `fn` on the main queue, in a block that ALWAYS returns None.

    PyObjC type-checks a void block's return value. Hand `addOperationWithBlock_`
    a function that returns something and it raises an uncaught ObjC exception
    ON THE MAIN THREAD — `did not return None, expecting void return value` —
    which terminates the process. Not hypothetical: `apply_menu_states`
    returned its count, and the app died milliseconds after logging a
    successful sync, so the log said the feature worked and the app was gone.

    Every AppKit poke in this file goes through here now, which makes that
    class impossible to reintroduce and gives each block exception logging it
    otherwise would not have — an exception inside a main-queue block cannot
    be caught by the code that scheduled it.
    """
    try:
        import AppKit

        def block() -> None:
            try:
                fn()
            except Exception as exc:
                shell_log(f"{what} FAILED: {exc!r}")

        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(block)
        return True
    except Exception as exc:
        shell_log(f"{what} could not be scheduled: {exc!r}")
        return False


def shell_log(msg: str) -> None:
    """Append one line. Never raises — a logger that can break the app it is
    diagnosing is worse than no logger."""
    try:
        SHELL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SHELL_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def probe(timeout: float = 1.0) -> dict | None:
    """The server's /api/state, or None if nothing is listening."""
    try:
        with urllib.request.urlopen(f"{URL}/api/state", timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def refresh_frontend_build() -> str:
    """Keep an EXISTING frontend build fresh; never create one.

    The server prefers `axibridge/static_dist/` over the source when it
    exists (app.frontend_dir), so a build left over from before a `git pull`
    would quietly serve yesterday's UI — the exact "I restarted it and
    nothing changed" failure this repo already has a warning about. ~260 ms
    to rule out.

    Deliberately does NOT build when there is no build: that stays a decision
    you make once, with `npm run build`, and a machine with no npm keeps
    serving the source exactly as before. Never fatal — a broken toolchain
    must not stop the window opening.
    """
    dist = REPO / "axibridge" / "static_dist"
    if not (dist / "index.html").is_file():
        return "source (no build present)"
    if shutil.which("npm") is None or not (REPO / "node_modules").is_dir():
        return "built (stale? no npm here to refresh it)"
    r = subprocess.run(["npm", "run", "build"], cwd=str(REPO),
                       capture_output=True, text=True)
    return "built (refreshed)" if r.returncode == 0 else \
        f"built (REFRESH FAILED: {(r.stderr or r.stdout).strip()[-200:]})"


def spawn_server() -> subprocess.Popen:
    """Start the pinned interpreter's server, silenced (the in-app log ring
    is the log surface). stdin closed so nothing ever blocks on a tty."""
    return subprocess.Popen(
        [str(PYTHON), "-m", "axibridge", "--host", "127.0.0.1", "--port", str(PORT)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(REPO),
    )


def wait_ready(proc: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited during startup (code {proc.returncode})")
        if probe(0.5) is not None:
            return
        time.sleep(0.2)
    raise RuntimeError(f"server did not come up on {URL} within {timeout:.0f}s")


def terminate(proc: subprocess.Popen, grace: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()  # uvicorn's shutdown runs manager.shutdown(): pen up, port released
    try:
        proc.wait(grace)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# -- macOS chrome -------------------------------------------------------------
#
# Two cosmetic integrations, both deliberately best-effort: they poke at
# AppKit through pyobjc (which pywebview already depends on) and at pywebview
# internals, so they are wrapped rather than trusted. A failure here must never
# stop the app from opening — it just leaves the stock chrome.

#: what integrate_titlebar managed — published to the page by mark_native_shell
#: so a silent no-op is visible in the DOM instead of invisible. Three rounds
#: of this were lost to failures that raised nothing and did nothing.
_titlebar_status = "pending"


def integrate_titlebar(window) -> bool:
    """Merge the title bar into the page: transparent bar, no duplicated
    title, content running full height, and the title bar's own background
    cleared. The traffic lights stay where macOS puts them and keep working —
    they simply sit over the app's own header now.

    Three things have to happen together, and each was a separate bug:

    * the AppKit calls are dispatched to the main queue — pywebview fires
      window events from a worker thread, and window mutations from off the
      main thread silently do nothing;
    * the style mask gains FullSizeContentView so the page reaches y=0;
    * the title bar view's background is cleared. pywebview paints it
      `windowBackgroundColor` on purpose ("so that it does not change with the
      window color"), which sat as a lighter band over the header and clipped
      whatever was at the top of it. Transparency alone does not beat an
      explicit background.

    The header reserves room for the lights via `[data-shell="native"]` in
    style.css. Best-effort throughout: a failure leaves the stock title bar.
    """
    global _titlebar_status
    try:
        import AppKit

        native = getattr(window, "native", None)
        if native is None:
            _titlebar_status = "no-native-window"
            return False

        def apply() -> None:
            global _titlebar_status
            try:
                native.setTitlebarAppearsTransparent_(True)
                native.setTitleVisibility_(AppKit.NSWindowTitleHidden)
                native.setStyleMask_(
                    native.styleMask() | AppKit.NSWindowStyleMaskFullSizeContentView)
                # the band pywebview paints over our header
                titlebar = native.contentView().superview().subviews().lastObject()
                titlebar.setBackgroundColor_(AppKit.NSColor.clearColor())
                # hairline under the bar (macOS 11+)
                style_none = getattr(AppKit, "NSTitlebarSeparatorStyleNone", None)
                if style_none is not None:
                    native.setTitlebarSeparatorStyle_(style_none)
                _titlebar_status = "merged"
            except Exception as exc:               # noqa: BLE001 — reported, not raised
                _titlebar_status = f"failed: {type(exc).__name__}"

        return on_main(apply, "titlebar merge")
    except Exception as exc:                        # noqa: BLE001
        _titlebar_status = f"unavailable: {type(exc).__name__}"
        return False


def build_menu(window):
    """The system menu bar, DERIVED from the in-page one — see
    `axibridge.menu_spec` for why it is derived rather than written.

    This function no longer decides what is in the menu. It walks the spec
    parsed out of `index.html` and turns each item into a proxy click on the
    control the page already has, so the page stays the single implementation
    and the two bars cannot differ in membership. Returns [] if pywebview's
    menu API isn't available.

    Two deliberate limits, both because pywebview's `MenuAction` carries
    neither a shortcut nor a checkmark:

    * **No native key equivalents.** The page already handles ⌘Z, and it
      bails out when focus is in a text field (`main.js`, the INPUT/TEXTAREA
      guard) so ⌘Z in the project-name box is still the system's text undo.
      An NSMenuItem key equivalent fires regardless of focus and would take
      that away, trading a correct behaviour for a decoration.
    * **No native checkmarks.** A "check"/"radio" item acts correctly but
      does not show its state natively yet. Nothing that NEEDS a visible
      state should move into the menu until it does.

    The in-page bar stays for browser tabs, where a native menu doesn't exist;
    `mark_native_shell` hides it here so the two never show at once.
    """
    try:
        from webview.menu import Menu, MenuAction, MenuSeparator
    except Exception:
        return []

    sys.path.insert(0, str(REPO))
    from axibridge.menu_spec import menu_spec

    def click(selector: str):
        return lambda: window.evaluate_js(
            f"document.querySelector({json.dumps(selector)})?.click()")

    menus = []
    for m in menu_spec():
        items = [MenuSeparator() if i is None else MenuAction(i.label, click(i.selector))
                 for i in m.items]
        menus.append(Menu(m.title, items))
    return menus


#: Last state the page reported, so the two things that can set the ticks —
#: the page telling us something changed, and the merge finishing — do not
#: have to happen in a fixed order. They race: `loaded` (which installs the
#: probe and brings the first report) and `shown` (which merges) are separate
#: pywebview events. Whichever runs last re-applies, and the ticks are right
#: either way.
_menu_states: dict = {}

#: menus we contribute that pywebview also builds itself. Ian's call
#: (2026-08-07): ours merge INTO those rather than sitting beside them under
#: invented names, so the system bar reads the same as the in-page bar.
_MERGE_INTO_NATIVE = ("Edit", "View")


def menu_title(item) -> str:
    """The title macOS shows for a menu in the bar: the SUBMENU's, not the
    item's.

    Two attempts died on this. pywebview builds its own Edit and View with
    `NSMenuItem.alloc().init()` and titles only the submenu (cocoa.py
    `_add_edit_menu` / `_add_view_menu`), while custom menus are titled on
    both. Reading `item.title()` found ours and missed theirs. Falling back to
    the submenu only when the item's title was falsy missed them too — because
    `NSMenuItem.alloc().init()` does not leave the title empty, it leaves the
    literal string **"NSMenuItem"** (`init` is not the designated initialiser;
    `initWithTitle:action:keyEquivalent:` is). A truthy-looking placeholder is
    why both attempts failed silently and identically.

    Preferring the submenu is not a workaround for that, it is the correct
    reading: a menu in the bar displays its submenu's title, and for our own
    menus both titles are set to the same string anyway.
    """
    sub = item.submenu()
    if sub is not None and sub.title():
        return sub.title()
    return item.title() or ""


def merge_menus_into_native(main_menu, titles, separator) -> list[str]:
    """Move our items into the same-named menu that already exists, and drop
    our now-empty one. Returns the titles actually merged.

    Split out from `merge_native_menus` so it can be tested without AppKit:
    the failure this code exists for is a *title lookup* on menu objects, and
    no headless check catches that unless it models the shape pywebview really
    builds. `tests/test_app_shell.py` now does.
    """
    merged = []
    for title in titles:
        found = [i for i in range(main_menu.numberOfItems())
                 if menu_title(main_menu.itemAtIndex_(i)) == title]
        if len(found) < 2:
            continue  # pywebview changed, or we contribute nothing under this name
        native, ours = main_menu.itemAtIndex_(found[0]), main_menu.itemAtIndex_(found[-1])
        target, source = native.submenu(), ours.submenu()
        if target is None or source is None or target is source:
            continue
        moved = 0
        while source.numberOfItems():
            item = source.itemAtIndex_(0)
            item.retain()
            source.removeItemAtIndex_(0)
            target.insertItem_atIndex_(item, moved)
            item.release()
            moved += 1
        if moved:
            target.insertItem_atIndex_(separator(), moved)
        main_menu.removeItemAtIndex_(found[-1])
        merged.append(title)
    return merged


def find_menu_item(main_menu, menu_title_wanted: str, item_label: str):
    """The NSMenuItem for (menu, label), after the merge has moved ours into
    pywebview's menus. Returns None if it isn't there."""
    for i in range(main_menu.numberOfItems()):
        bar_item = main_menu.itemAtIndex_(i)
        if menu_title(bar_item) != menu_title_wanted:
            continue
        sub = bar_item.submenu()
        if sub is None:
            continue
        for j in range(sub.numberOfItems()):
            if sub.itemAtIndex_(j).title() == item_label:
                return sub.itemAtIndex_(j)
    return None


def set_menu_states(main_menu, states: dict, index: dict, on, off) -> int:
    """Make the native items tell the truth: ticked if the page says on,
    greyed if the control they drive is unavailable. Returns how many were set.

    `states` is ``{selector: {"on": bool|None, "enabled": bool}}`` straight
    from the page; `index` maps a selector to the (menu, label) that addresses
    its native item. Both come from `axibridge.menu_spec`, so what is ticked,
    what is greyed and what is clicked can never be three different opinions.

    `on` of None means the item has no state — an action. Its checkmark is
    left alone rather than set to off, because "Go to origin" should not carry
    a slot for a tick it can never have.

    **AppKit gotcha, and it would have silently undone all of this:** an NSMenu
    autoenables its items by default, deciding availability by asking the
    responder chain to validate each item's action. Our items are blocks, which
    validate as enabled, so every `setEnabled_(False)` here would be overwritten
    the moment the menu opened. `setAutoenablesItems_(False)` on the containing
    menu is what makes an explicit setting stick.
    """
    done = 0
    seen_menus = set()
    for selector, report in states.items():
        where = index.get(selector)
        if where is None or not isinstance(report, dict):
            continue
        item = find_menu_item(main_menu, *where)
        if item is None:
            continue
        parent = item.menu()
        if parent is not None and id(parent) not in seen_menus:
            parent.setAutoenablesItems_(False)   # or AppKit overrules us on open
            seen_menus.add(id(parent))
        is_on = report.get("on")
        if is_on is not None:
            item.setState_(on if is_on else off)
        item.setEnabled_(bool(report.get("enabled", True)))
        done += 1
    return done


def apply_menu_states() -> int:
    """Push `_menu_states` onto the native items. Main thread only — called
    from inside the blocks that already run there."""
    try:
        import AppKit

        from axibridge.menu_spec import item_index

        main_menu = AppKit.NSApplication.sharedApplication().mainMenu()
        if main_menu is None or not _menu_states:
            return 0
        index = item_index()
        n = set_menu_states(main_menu, _menu_states, index,
                            AppKit.NSControlStateValueOn, AppKit.NSControlStateValueOff)
        shell_log(f"menu state: set {n}/{len(index)} from {_menu_states}")
        return n
    except Exception as exc:
        shell_log(f"menu state FAILED: {exc!r}")
        return 0


def merge_native_menus() -> bool:
    """Fold our Edit/View items into pywebview's own menus of those names.

    pywebview builds an Edit (Cut/Copy/Paste/Select All) and a View (Enter
    Full Screen) before appending any custom menu, so contributing menus with
    those titles produces two of each. Rather than rename ours — which is
    what put Undo under "History" and orientation under "Canvas", where Ian
    never found them — the NSMenuItems are MOVED into pywebview's menus at the
    top, above a separator, which is where macOS puts Undo and where an app's
    own view options belong.

    Moving the items rather than recreating them is what keeps them working:
    they are the objects pywebview already wired to its post-start action
    handler, and a hand-built NSMenuItem would need that wiring redone.

    Best-effort and non-fatal, like every other AppKit poke here: on failure
    the bar simply shows both menus, which is the previous behaviour.
    """
    try:
        import AppKit

        def apply() -> None:
            main_menu = AppKit.NSApplication.sharedApplication().mainMenu()
            if main_menu is None:
                return
            merged = merge_menus_into_native(main_menu, _MERGE_INTO_NATIVE,
                                             AppKit.NSMenuItem.separatorItem)
            bar = [menu_title(main_menu.itemAtIndex_(i))
                   for i in range(main_menu.numberOfItems())]
            shell_log(f"menu merge: merged={merged} bar={bar}")
            # a state report that arrived before the merge looked into
            # pywebview's untouched menus and found none of our items
            apply_menu_states()

        return on_main(apply, "menu merge")
    except Exception as exc:
        shell_log(f"menu merge could not be scheduled: {exc!r}")
        return False


def install_menu_probe(window) -> bool:
    """Hand the page the expression that reads its own menu state.

    Generated in `axibridge.menu_spec` from the same spec that builds the
    native menu, so `menu.js` never has to know what a menu item is or how to
    read one — it only calls what it was given, and there is still exactly one
    definition to get wrong.
    """
    try:
        from axibridge.menu_spec import state_probe_js

        window.evaluate_js(f"window.__axbMenuProbe = () => ({state_probe_js()});")
        return True
    except Exception as exc:
        shell_log(f"menu probe could not be installed: {exc!r}")
        return False


def mark_native_shell(window) -> None:
    """Tell the page it's hosted in the app shell, not a browser tab, so the
    in-page menu bar can stand down and the header can leave room for the
    traffic lights. One flag, read by CSS."""
    try:
        window.evaluate_js(
            "document.documentElement.dataset.shell = 'native';"
            f"document.documentElement.dataset.titlebar = '{_titlebar_status}';")
    except Exception:
        pass


class ShellApi:
    """The bridge JS can call: `window.pywebview.api.<name>()`.

    Deliberately tiny — anything that isn't a *window* operation belongs in the
    HTTP API, not here, so the browser and the app shell keep the same
    surface. Window ops are the one thing a page genuinely cannot do itself.
    """

    def __init__(self) -> None:
        self.window = None  # set once create_window has returned

    def menu_changed(self, states: dict | None = None) -> bool:
        """The page reporting the state of every menu toggle.

        The page PASSES the states rather than the shell reading them back.
        Pulling would mean `evaluate_js` from inside a js_api handler, while
        the JS side is awaiting this very call to return — the classic way to
        deadlock a webview bridge, and a deadlock here is indistinguishable
        from the silent no-op this feature already failed as once.

        It still holds no opinion about the menu: the expression it evaluates
        is generated by `axibridge.menu_spec` and injected by
        `install_menu_probe`, so the page runs code it was handed and names
        nothing itself.

        A no-op in a browser tab, where `window.pywebview` does not exist.
        """
        try:
            import AppKit

            if isinstance(states, dict):
                _menu_states.clear()
                _menu_states.update(states)
            else:
                shell_log(f"menu state: page sent {states!r}, ignoring")
                return False
            return on_main(apply_menu_states, "menu state")
        except Exception as exc:
            shell_log(f"menu state could not be applied: {exc!r}")
            return False

    def set_title(self, project: str | None = None) -> bool:
        """Put the open project in the window title: `axibridge — <name>`.

        Review proposal 05's core insight, and the half of it that is
        actually available: the native title bar and the in-page header both
        said "axibridge", 40px apart, so one of them was carrying no
        information. Now it names the document.

        NOT the whole proposal. Deleting the in-page header is impossible in
        this shell — the header IS the title-bar band, it reserves the space
        the traffic lights sit in (`[data-shell="native"] header`), so it can
        only go in a browser tab. And the unsaved marker the proposal wants
        needs a dirty-state concept the app does not have: ROADMAP's
        "Unsaved-work guard" is still open, and inventing one here would
        resolve it by side effect.
        """
        try:
            name = (project or "").strip()
            self.window.set_title(f"axibridge — {name}" if name else "axibridge")
            return True
        except Exception as exc:
            shell_log(f"window title could not be set: {exc!r}")
            return False

    def zoom_window(self) -> bool:
        """Double-click on the title-bar band, same as the green button.

        The band is our own header now, so macOS's own double-click-to-zoom
        never sees the event — the web view swallows it.
        """
        try:
            import AppKit

            native = getattr(self.window, "native", None)
            if native is None:
                return False
            return on_main(lambda: native.zoom_(None), "zoom window")
        except Exception:
            return False


def order_menu_file_first() -> bool:
    """Put File right after the app menu.

    pywebview appends custom menus after its own app/View/Edit ones, so File
    landed fourth. The main menu is a plain NSMenu, so it can be reordered
    once pywebview has built it. Main queue, like every other AppKit poke here.
    """
    try:
        import AppKit

        def apply() -> None:
            main_menu = AppKit.NSApplication.sharedApplication().mainMenu()
            if main_menu is None:
                return
            for i in range(main_menu.numberOfItems()):
                item = main_menu.itemAtIndex_(i)
                if item.title() == "File" and i != 1:
                    item.retain()
                    main_menu.removeItemAtIndex_(i)
                    main_menu.insertItem_atIndex_(item, 1)  # 0 is the app menu
                    item.release()
                    return

        return on_main(apply, "menu reorder")
    except Exception as exc:
        shell_log(f"menu reorder could not be scheduled: {exc!r}")
        return False


def plot_running() -> bool:
    state = probe()
    return bool(state) and state.get("machine", {}).get("job_state") not in (None, "idle")


def main() -> None:
    import webview  # deferred: import cost + lets tests import this module headless

    owned: subprocess.Popen | None = None
    if probe() is None:
        if not PYTHON.exists():
            raise SystemExit(f"pinned interpreter not found: {PYTHON}")
        # before the server picks a frontend, not after — it decides once, at
        # create_app(). Skipped when attaching to somebody else's server.
        print(f"frontend: {refresh_frontend_build()}", flush=True)
        owned = spawn_server()
        try:
            wait_ready(owned)
        except Exception:
            terminate(owned)
            raise

    # Only the header bar's OWN empty space drags the window — direct-target-only
    # keeps every control inside it clickable. Without `draggable` the web view
    # covers the (now transparent) title bar and swallows the drag entirely.
    webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    api = ShellApi()
    window = webview.create_window("axibridge", URL, width=1440, height=900,
                                   draggable=True, js_api=api)
    api.window = window

    def on_shown():
        integrate_titlebar(window)
        merge_native_menus()   # before the reorder: it removes menu items
        order_menu_file_first()

    def on_loaded():
        mark_native_shell(window)
        # the probe must exist before the page's first report, and the page
        # re-pings whenever the bar mutates, so one install per load is enough
        install_menu_probe(window)
        api.menu_changed(window.evaluate_js("window.__axbMenuProbe()"))

    window.events.shown += on_shown
    window.events.loaded += on_loaded

    def on_closing():
        # never strand a moving plotter: an owned server mid-plot refuses to die
        if owned is not None and plot_running():
            window.evaluate_js(
                "alert('a plot is running — stop it (Plot tab) before closing the app')")
            return False  # cancels the close
        return True

    window.events.closing += on_closing
    try:
        webview.start(menu=build_menu(window))
    finally:
        if owned is not None:
            terminate(owned)


if __name__ == "__main__":
    sys.exit(main())
