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
  File/View menus are served from the real system menu bar. Both are
  best-effort: if either fails the app still starts, with the standard title
  bar and the in-page menu.

Import-safe: no side effects at import time (unit tests import the helpers).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYTHON = REPO / ".venv" / "bin" / "python"
PORT = 2942
URL = f"http://127.0.0.1:{PORT}"


def probe(timeout: float = 1.0) -> dict | None:
    """The server's /api/state, or None if nothing is listening."""
    try:
        with urllib.request.urlopen(f"{URL}/api/state", timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


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

        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(apply)
        return True
    except Exception as exc:                        # noqa: BLE001
        _titlebar_status = f"unavailable: {type(exc).__name__}"
        return False


def build_menu(window):
    """The system menu bar, on the same rule as the in-page one (menu.js):
    every item proxy-clicks a control that already exists, so this can't drift
    out of sync with the app's own logic. Returns [] if pywebview's menu API
    isn't available.

    The in-page bar stays for browser tabs, where a native menu doesn't exist;
    `mark_native_shell` hides it here so the two never show at once.
    """
    try:
        from webview.menu import Menu, MenuAction, MenuSeparator
    except Exception:
        return []

    def click(selector: str):
        # json-free single-quote selector: all of ours are simple ids/attrs
        return lambda: window.evaluate_js(
            f"document.querySelector('{selector}')?.click()")

    view = lambda v: click(f'#view-toggle button[data-view="{v}"]')  # noqa: E731
    return [
        Menu("File", [
            MenuAction("Save", click("#btn-save")),
            MenuSeparator(),
            MenuAction("Download resolved SVG", click("#btn-svg")),
        ]),
        # NOT "View": pywebview installs its own app/Edit/View menus, and a
        # second View sat next to theirs in the bar. This is the sheet's
        # orientation, so name it for the thing it acts on.
        Menu("Canvas", [
            MenuAction("Portrait", view("portrait")),
            MenuAction("Landscape", view("landscape")),
        ]),
    ]


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
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: native.zoom_(None))
            return True
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

        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(apply)
        return True
    except Exception:
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
        order_menu_file_first()

    def on_loaded():
        mark_native_shell(window)

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
