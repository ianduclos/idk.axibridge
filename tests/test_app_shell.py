"""Server log ring (+ /api/logs) and the pywebview app shell's helpers.
The webview event loop itself is manually verified — these tests cover
everything up to the window."""

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import pytest

from axibridge import logbuf


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from axibridge.app import create_app

    with TestClient(create_app()) as c:
        yield c


# NOTE: pytest's logging plugin restores the ROOT level to WARNING around
# tests, undoing install()'s INFO bump (a production concern only uvicorn
# sees). The tests pin their own logger's level so they don't depend on it,
# and filter to that logger — other libraries (httpx) also log into the ring.
def _test_logger():
    lg = logging.getLogger("axibridge.test")
    lg.setLevel(logging.INFO)
    return lg


def _ours(entries):
    return [e for e in entries if e["logger"] == "axibridge.test"]


def test_logbuf_captures_and_filters():
    logbuf.install()
    _test_logger().info("ring me %s", "once")
    entries = logbuf.entries()
    assert any(e["msg"] == "ring me once" for e in entries)
    last = entries[-1]["id"]
    assert logbuf.entries(after=last) == []
    _test_logger().warning("newer")
    newer = _ours(logbuf.entries(after=last))
    assert [e["msg"] for e in newer] == ["newer"]
    assert newer[0]["level"] == "WARNING"


def test_logbuf_install_is_idempotent():
    logbuf.install()
    logbuf.install()
    _test_logger().info("exactly one entry")
    added = [e for e in logbuf.entries() if e["msg"] == "exactly one entry"]
    assert len(added) == 1  # two installs must not mean two handlers


def test_logs_endpoint(client):
    _test_logger().info("visible through the api")
    r = client.get("/api/logs")
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert any(e["msg"] == "visible through the api" for e in entries)
    last = entries[-1]["id"]
    later = client.get(f"/api/logs?after={last}").json()["entries"]
    assert _ours(later) == []  # cursor works (httpx logs its own requests)
    assert client.get("/api/logs?after=-1").status_code == 422


def test_app_shell_imports_without_side_effects():
    """Importing the shell must not probe, spawn, or open anything."""
    sys.path.insert(0, "launch")
    try:
        import axibridge_app
    finally:
        sys.path.pop(0)
    assert axibridge_app.PORT == 2942
    assert axibridge_app.PYTHON.name == "python"
    assert axibridge_app.REPO.joinpath("axibridge").is_dir()


def test_app_shell_spawn_probe_terminate_cycle():
    """The ownership lifecycle end-to-end, minus the window: nothing on the
    port -> spawn -> ready -> probe sees state -> terminate -> port free."""
    sys.path.insert(0, "launch")
    try:
        import axibridge_app as shell
    finally:
        sys.path.pop(0)
    if shell.probe() is not None:
        pytest.skip("a real axibridge server is already running on 2942")
    proc = shell.spawn_server()
    try:
        shell.wait_ready(proc)
        state = shell.probe()
        assert state and "machine" in state
        assert shell.plot_running() is False  # fresh server: idle
    finally:
        shell.terminate(proc)
    assert proc.poll() is not None
    deadline = time.monotonic() + 5
    while shell.probe(0.3) is not None and time.monotonic() < deadline:
        time.sleep(0.2)
    assert shell.probe(0.3) is None  # port released


def test_app_shell_wait_ready_reports_early_exit():
    sys.path.insert(0, "launch")
    try:
        import axibridge_app as shell
    finally:
        sys.path.pop(0)
    dead = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
    dead.wait()
    with pytest.raises(RuntimeError, match="exited during startup"):
        shell.wait_ready(dead, timeout=2)


# -- macOS chrome integration -------------------------------------------------
#
# Both tweaks poke at AppKit and pywebview internals, so they are written to
# degrade rather than raise: a failure must leave the stock title bar and the
# in-page menu, never stop the window opening. These tests pin that contract
# (they run headless on any platform — no window is created).

def _shell():
    sys.path.insert(0, "launch")
    try:
        import axibridge_app
        return axibridge_app
    finally:
        sys.path.pop(0)


class _FakeWindow:
    """A window with no native handle — the degraded path."""

    native = None

    def __init__(self):
        self.js = []

    def evaluate_js(self, src):
        self.js.append(src)


def test_integrate_titlebar_degrades_without_a_native_window():
    assert _shell().integrate_titlebar(_FakeWindow()) is False


def test_integrate_titlebar_survives_a_hostile_window():
    """Anything unexpected from pywebview must be swallowed, not raised."""
    class Boom:
        @property
        def native(self):
            raise RuntimeError("no window yet")

    assert _shell().integrate_titlebar(Boom()) is False


def test_menu_items_only_proxy_existing_controls():
    """Same rule as the in-page bar (menu.js): every item clicks a control that
    already exists, so the native menu cannot drift from the app's own logic.
    No item may call an API directly.

    The titles are now the page's own — File / Edit / View — rather than the
    invented History / Canvas. Ian's call, 2026-08-07: those names were chosen
    to dodge pywebview's own Edit and View menus, and the cost was that he
    never found Undo or the orientation toggle in the app at all.
    `merge_native_menus` folds ours into pywebview's after start instead."""
    shell = _shell()
    win = _FakeWindow()
    menus = shell.build_menu(win)
    if not menus:
        pytest.skip("pywebview menu API unavailable")

    from axibridge.menu_spec import menu_spec
    assert [m.title for m in menus] == [m.title for m in menu_spec()], \
        "the native bar is derived from the page's; it does not choose its own menus"
    assert "Edit" in {m.title for m in menus} and "View" in {m.title for m in menus}
    assert set(shell._MERGE_INTO_NATIVE) <= {m.title for m in menus}, \
        "every title we merge into must be one we actually contribute"

    index = (Path("axibridge/static/index.html")).read_text()
    clicked = 0
    for menu in menus:
        for item in menu.items:
            fn = getattr(item, "function", None)
            if fn is None:      # separator
                continue
            win.js.clear()
            fn()
            (src,) = win.js
            assert ".click()" in src, f"{item.title!r} must proxy a real control"
            assert "/api/" not in src, f"{item.title!r} must not call the API directly"
            selector = json.loads(src[src.index("(") + 1:src.rindex(")?")])
            token = selector.split("[")[0].split()[0].lstrip("#")  # "#a b[c]" -> "a"
            assert token in index, f"{item.title!r} targets {selector}, absent from index.html"
            clicked += 1
    assert clicked >= 4


def test_merging_the_native_menus_never_takes_the_app_down():
    """Every AppKit poke in the shell is best-effort by contract — a menu that
    fails to merge must leave the app running with both menus showing, which
    is exactly the behaviour before the merge existed."""
    shell = _shell()
    assert shell.merge_native_menus() in (True, False)  # never raises


# -- the merge itself, against the menu shape pywebview really builds -------
#
# The detail that is the whole point, and that two fix attempts died on:
# pywebview titles its OWN Edit/View on the SUBMENU, and the wrapping
# NSMenuItem keeps the default title `NSMenuItem` gives an item built with
# plain `init` — the literal string "NSMenuItem", NOT the empty string. So
# reading item.title() finds a truthy placeholder, and "fall back when the
# title is empty" never fires. The fakes below carry that placeholder for
# exactly that reason; a fake using "" would pass code that fails on the
# real thing, which is what happened. `test_merge_against_real_appkit_menus`
# closes the loop with actual NSMenu objects.

class _FakeMenu:
    def __init__(self, title="", items=None):
        self._title, self._items = title, list(items or [])
        self.autoenables = True          # NSMenu's default, and the trap
        for it in self._items:
            it._parent = self

    def setAutoenablesItems_(self, v):
        self.autoenables = v

    def title(self):
        return self._title

    def numberOfItems(self):
        return len(self._items)

    def itemAtIndex_(self, i):
        return self._items[i]

    def insertItem_atIndex_(self, item, i):
        self._items.insert(i, item)

    def removeItemAtIndex_(self, i):
        del self._items[i]

    def titles(self):
        return [it.title() for it in self._items]


class _FakeItem:
    #: what NSMenuItem.alloc().init() really leaves behind
    def __init__(self, title="NSMenuItem", submenu=None):
        self._title, self._submenu = title, submenu
        self._parent = None
        self.state = None
        self.enabled = True

    def menu(self):
        return self._parent

    def setState_(self, v):
        self.state = v

    def setEnabled_(self, v):
        self.enabled = v

    def title(self):
        return self._title

    def submenu(self):
        return self._submenu

    def retain(self):
        pass

    def release(self):
        pass


def _bar():
    """app | File | (pywebview Edit) | (pywebview View) | our Edit | our View"""
    native_edit = _FakeMenu("Edit", [_FakeItem("Cut"), _FakeItem("Paste")])
    native_view = _FakeMenu("View", [_FakeItem("Enter Full Screen")])
    ours_edit = _FakeMenu("Edit", [_FakeItem("Undo"), _FakeItem("Redo")])
    ours_view = _FakeMenu("View", [_FakeItem("Portrait"), _FakeItem("Landscape")])
    main = _FakeMenu("", [
        _FakeItem("AxiBridge", _FakeMenu()),
        _FakeItem("File", _FakeMenu("File", [_FakeItem("Save")])),
        _FakeItem(submenu=native_edit),  # pywebview: submenu titled, item is
        _FakeItem(submenu=native_view),  # the "NSMenuItem" placeholder
        _FakeItem("Edit", ours_edit),    # ours: both titled
        _FakeItem("View", ours_view),
    ])
    return main, native_edit, native_view


def test_our_items_move_into_pywebviews_menus_and_the_duplicate_goes():
    shell = _shell()
    main, native_edit, native_view = _bar()

    merged = shell.merge_menus_into_native(
        main, ("Edit", "View"), lambda: _FakeItem("---"))

    assert merged == ["Edit", "View"]
    assert len(main._items) == 4, "the duplicate Edit and View are gone from the bar"
    assert native_edit.titles() == ["Undo", "Redo", "---", "Cut", "Paste"], \
        "ours land on top, above a separator, where macOS puts Undo"
    assert native_view.titles() == ["Portrait", "Landscape", "---", "Enter Full Screen"]


def test_the_title_comes_from_the_submenu_not_the_item():
    """The exact lookup that failed, twice. A menu in the bar shows its
    SUBMENU's title, and pywebview's items carry the useless-but-truthy
    "NSMenuItem" placeholder — so the item's title can never be trusted first,
    and an emptiness check on it is not enough either."""
    shell = _shell()
    assert shell.menu_title(_FakeItem("NSMenuItem", _FakeMenu("Edit"))) == "Edit"
    assert shell.menu_title(_FakeItem("View", _FakeMenu("View"))) == "View"
    assert shell.menu_title(_FakeItem("File", None)) == "File"
    assert shell.menu_title(_FakeItem("NSMenuItem", _FakeMenu(""))) == "NSMenuItem"


def test_merge_against_real_appkit_menus():
    """The fakes above encode what I believed about NSMenu; this builds the
    real thing. Both prior fixes passed a model and failed the machine, so the
    model is not allowed to be the last word.

    Reproduces pywebview's construction exactly — its View then Edit inserted
    at index 1 with only the submenu titled, our three appended with both
    titled — and asserts the bar Ian sees afterwards."""
    AppKit = pytest.importorskip("AppKit", reason="not macOS")
    shell = _shell()

    main = AppKit.NSMenu.alloc().init()
    app_item = AppKit.NSMenuItem.alloc().init()
    main.insertItem_atIndex_(app_item, 0)
    app_item.setSubmenu_(AppKit.NSMenu.alloc().init())

    def native(title, labels, index):
        menu = AppKit.NSMenu.alloc().init()
        menu.setTitle_(title)                 # submenu only, as pywebview does
        item = AppKit.NSMenuItem.alloc().init()
        item.setSubmenu_(menu)
        main.insertItem_atIndex_(item, index)
        for label in labels:
            menu.addItemWithTitle_action_keyEquivalent_(label, None, "")
        return menu

    view = native("View", ["Enter Full Screen"], 1)
    edit = native("Edit", ["Cut", "Copy", "Paste", "Select All"], 1)
    for title, labels in [("File", ["Save"]), ("Edit", ["Undo", "Redo"]),
                          ("View", ["Portrait", "Landscape"])]:
        sub = AppKit.NSMenu.alloc().init()
        sub.setTitle_(title)
        item = AppKit.NSMenuItem.alloc().init()
        item.setTitle_(title)                 # ours: item AND submenu titled
        item.setSubmenu_(sub)
        main.addItem_(item)
        for label in labels:
            sub.addItemWithTitle_action_keyEquivalent_(label, None, "")

    assert shell.merge_menus_into_native(
        main, ("Edit", "View"), AppKit.NSMenuItem.separatorItem) == ["Edit", "View"]

    bar = [shell.menu_title(main.itemAtIndex_(i)) for i in range(main.numberOfItems())]
    assert bar[1:] == ["Edit", "View", "File"], f"duplicates left in the bar: {bar}"
    assert [str(edit.itemAtIndex_(i).title()) for i in range(edit.numberOfItems())] == \
        ["Undo", "Redo", "", "Cut", "Copy", "Paste", "Select All"]
    assert [str(view.itemAtIndex_(i).title()) for i in range(view.numberOfItems())] == \
        ["Portrait", "Landscape", "", "Enter Full Screen"]

    # -- and the state, on the same real objects ---------------------------
    # A toggle that cannot show its state, or an item that looks available
    # while its button is disabled, is worse in a menu than in a panel.
    index = {"#sel-portrait": ("View", "Portrait"),
             "#sel-landscape": ("View", "Landscape")}
    on, off = AppKit.NSControlStateValueOn, AppKit.NSControlStateValueOff
    rep = lambda o, e=True: {"on": o, "enabled": e}   # noqa: E731

    assert shell.set_menu_states(
        main, {"#sel-portrait": rep(True), "#sel-landscape": rep(False)},
        index, on, off) == 2
    assert view.itemAtIndex_(0).state() == on
    assert view.itemAtIndex_(1).state() == off

    # the tick must FOLLOW the page, not accumulate
    shell.set_menu_states(main, {"#sel-portrait": rep(False), "#sel-landscape": rep(True)},
                          index, on, off)
    assert view.itemAtIndex_(0).state() == off
    assert view.itemAtIndex_(1).state() == on

    # availability, and the autoenable trap that would silently undo it
    shell.set_menu_states(main, {"#sel-portrait": rep(True, False)}, index, on, off)
    assert view.itemAtIndex_(0).isEnabled() is False, "an unavailable item greys out"
    assert view.autoenablesItems() is False, \
        "AppKit would re-enable it on open unless autoenabling is off"
    shell.set_menu_states(main, {"#sel-portrait": rep(True, True)}, index, on, off)
    assert view.itemAtIndex_(0).isEnabled() is True, "and comes back"

    # an action reports on=None: it must not be given a checkmark slot
    act_index = {"#act": ("View", "Enter Full Screen")}
    before = view.itemAtIndex_(3).state()
    shell.set_menu_states(main, {"#act": rep(None, False)}, act_index, on, off)
    assert view.itemAtIndex_(3).state() == before, "no tick invented for an action"
    assert view.itemAtIndex_(3).isEnabled() is False, "but availability still applies"

    # a selector the page reports but the bar has no item for is ignored,
    # not an exception on the main thread
    assert shell.set_menu_states(main, {"#gone": rep(True)}, index, on, off) == 0
    assert shell.set_menu_states(main, {"#sel-portrait": True}, index, on, off) == 0, \
        "a bare bool is the OLD shape — ignored, never crashed on"
    assert shell.find_menu_item(main, "View", "Nope") is None
    assert shell.find_menu_item(main, "Nope", "Portrait") is None


def test_a_menu_with_no_counterpart_is_left_alone():
    """If pywebview stops shipping an Edit menu, ours must survive as its own
    menu rather than being dropped or merged into something arbitrary."""
    shell = _shell()
    ours = _FakeMenu("Edit", [_FakeItem("Undo")])
    main = _FakeMenu("", [_FakeItem("AxiBridge", _FakeMenu()), _FakeItem("Edit", ours)])

    assert shell.merge_menus_into_native(main, ("Edit",), lambda: _FakeItem("---")) == []
    assert main.titles() == ["AxiBridge", "Edit"]
    assert ours.titles() == ["Undo"]


def test_refresh_frontend_build_never_creates_one(tmp_path, monkeypatch):
    """It keeps an existing build fresh; with no build it must leave the
    source alone, or a machine with no npm would be worse off than before
    there was a build step at all."""
    shell = _shell()
    monkeypatch.setattr(shell, "REPO", tmp_path)
    (tmp_path / "axibridge").mkdir()
    called = []
    monkeypatch.setattr(shell.subprocess, "run",
                        lambda *a, **k: called.append(a) or _Ran(0))

    assert "no build" in shell.refresh_frontend_build()
    assert not called, "must not build when there is no build"

    dist = tmp_path / "axibridge" / "static_dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>")
    (tmp_path / "node_modules").mkdir()
    monkeypatch.setattr(shell.shutil, "which", lambda _: "/usr/bin/npm")
    assert shell.refresh_frontend_build() == "built (refreshed)"
    assert called, "an existing build must be refreshed"


def test_refresh_frontend_build_survives_a_broken_toolchain(tmp_path, monkeypatch):
    """A failed build must never stop the window opening."""
    shell = _shell()
    monkeypatch.setattr(shell, "REPO", tmp_path)
    dist = tmp_path / "axibridge" / "static_dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>")
    (tmp_path / "node_modules").mkdir()
    monkeypatch.setattr(shell.shutil, "which", lambda _: "/usr/bin/npm")
    monkeypatch.setattr(shell.subprocess, "run",
                        lambda *a, **k: _Ran(1, err="vite exploded"))
    assert "REFRESH FAILED" in shell.refresh_frontend_build()


class _Ran:
    def __init__(self, code, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_mark_native_shell_publishes_shell_and_titlebar_state():
    """The title-bar tweak is a best-effort AppKit poke, and three separate
    rounds of it failed by doing nothing at all rather than raising. Its
    outcome is published to the DOM so a no-op is inspectable."""
    shell = _shell()
    win = _FakeWindow()
    shell.integrate_titlebar(win)          # no native window -> degraded path
    shell.mark_native_shell(win)
    (src,) = win.js
    assert "dataset.shell = 'native'" in src
    assert "dataset.titlebar = 'no-native-window'" in src


# -- main-queue blocks must never return a value ---------------------------

_BLOCK_PROBE = """
import sys
sys.path.insert(0, {repo!r})
sys.path.insert(0, {launch!r})
import AppKit
import axibridge_app as shell

ran = []
shell.on_main(lambda: (ran.append(1), 42)[1], "probe")   # returns 42
AppKit.NSRunLoop.currentRunLoop().runUntilDate_(
    AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.6))
print("RAN" if ran else "NOTRUN")
"""


def test_a_main_queue_block_that_returns_a_value_does_not_kill_the_app():
    """The crash that took the app down on 2026-08-07.

    PyObjC type-checks a void block's return: give `addOperationWithBlock_` a
    function that returns something and it raises an uncaught ObjC exception
    on the main thread — "did not return None, expecting void return value" —
    and `libc++abi` terminates the process. `apply_menu_states` returned its
    count, so the shell logged a successful menu sync and then vanished.

    Run in a subprocess on purpose: a regression does not fail an assertion,
    it kills the interpreter, and that must show up as one red test rather
    than as the whole suite disappearing.
    """
    pytest.importorskip("AppKit", reason="not macOS")
    repo = str(Path(__file__).resolve().parent.parent)
    src = _BLOCK_PROBE.format(repo=repo, launch=str(Path(repo) / "launch"))

    r = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, (
        "a value-returning block took the process down — on_main must discard "
        f"the return value.\nstdout={r.stdout}\nstderr={r.stderr[-600:]}")
    assert "RAN" in r.stdout, f"the block never executed: {r.stdout!r}"


def test_on_main_never_raises_when_appkit_is_missing(monkeypatch):
    """Scheduling is best-effort like everything else here: on a machine with
    no AppKit the shell must carry on, not fail to open."""
    shell = _shell()
    monkeypatch.setitem(sys.modules, "AppKit", None)
    assert shell.on_main(lambda: None, "probe") is False