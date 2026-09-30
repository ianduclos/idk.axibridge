"""Recovery choices exercised in a browser with isolated API module responses."""

from __future__ import annotations

from pathlib import Path

import pytest

from test_acceptance_ui import frontend_mode, server, ui


SOURCE = Path(__file__).resolve().parent.parent / "axibridge/static/js/recovery_ui.js"


@pytest.fixture
def recovery_module(ui):
    modules = {
        "recovery_ui.js": SOURCE.read_text(),
        "api.js": """export const api = {
          get: (path) => window.__recoveryMock.get(path),
          post: (path, body) => window.__recoveryMock.post(path, body),
        };""",
        "main.js": """export const actions = {
          refreshAll: async () => { window.__recoveryMock.refreshes++; },
          oops: (error) => { window.__recoveryMock.errors.push(error.message); },
        };""",
    }

    def serve(route):
        name = route.request.url.rsplit("/", 1)[-1]
        route.fulfill(status=200, content_type="text/javascript", body=modules[name])

    ui.route("**/test-recovery-modules/*", serve)
    ui.evaluate("""async () => {
      window.__recoveryMock = {
        payloads: {}, calls: [], errors: [], refreshes: 0, saveFailures: 0,
        restoreFailures: 0, ackFailures: 0,
        get(path) { this.calls.push(['GET', path]); return Promise.resolve(this.payloads[path]); },
        post(path, body) {
          this.calls.push(['POST', path, body]);
          if (path === '/api/project/save' && this.saveFailures-- > 0)
            return Promise.reject(new Error('save failed'));
          if (path.endsWith('/restore') && this.restoreFailures-- > 0)
            return Promise.reject(new Error('recovery unavailable'));
          if (path === '/api/recovery/ack' && this.ackFailures-- > 0)
            return Promise.reject(new Error('ack unavailable'));
          return Promise.resolve({});
        },
      };
      window.__recoveryModule = await import('/test-recovery-modules/recovery_ui.js');
    }""")
    return ui


def _start(page, method):
    page.evaluate("""(method) => {
      window.__recoveryResult = undefined;
      window.__recoveryModule[method]().then(value => { window.__recoveryResult = value; });
    }""", method)
    page.locator(".recovery-dialog[open]").wait_for()


def _entries():
    return [
        {"id": "aaaa", "name": "Newer", "created_at": "2026-09-30T10:00:00Z"},
        {"id": "bbbb", "name": "Older", "created_at": "2026-09-29T10:00:00Z"},
    ]


def test_startup_restores_selected_older_candidate(recovery_module):
    page = recovery_module
    page.evaluate("(entries) => window.__recoveryMock.payloads['/api/recovery'] = {entries, offered: true}", _entries())
    _start(page, "initRecoveryUI")
    dialog = page.get_by_role("dialog", name="Recover unfinished project")
    assert "Only kept project content survives" in dialog.inner_text()
    dialog.get_by_label("Older").check()
    dialog.get_by_role("button", name="Restore").click()
    page.wait_for_function("() => window.__recoveryResult?.action === 'restore'")
    state = page.evaluate("() => window.__recoveryMock")
    assert ["POST", "/api/recovery/bbbb/restore", {}] in state["calls"]
    assert ["POST", "/api/recovery/ack", {}] in state["calls"]
    assert state["refreshes"] == 1
    assert page.locator(".recovery-dialog").count() == 0


def test_start_fresh_discards_only_selected_and_keep_for_later_preserves_all(recovery_module):
    page = recovery_module
    page.evaluate("(entries) => window.__recoveryMock.payloads['/api/recovery'] = {entries, offered: true}", _entries())
    _start(page, "initRecoveryUI")
    page.get_by_role("dialog", name="Recover unfinished project").get_by_role(
        "button", name="Keep for later").click()
    page.wait_for_function("() => window.__recoveryResult === null")
    assert not [call for call in page.evaluate("() => window.__recoveryMock.calls")
                if call[0] == "POST" and call[1] != "/api/recovery/ack"]

    _start(page, "initRecoveryUI")
    dialog = page.get_by_role("dialog", name="Recover unfinished project")
    dialog.get_by_label("Older").check()
    dialog.get_by_role("button", name="Start fresh").click()
    page.wait_for_function("() => window.__recoveryResult?.action === 'discard'")
    calls = page.evaluate("() => window.__recoveryMock.calls")
    assert [call for call in calls if call[0] == "POST" and call[1] != "/api/recovery/ack"] == [
        ["POST", "/api/recovery/bbbb/discard", {}]
    ]


def test_startup_restore_error_stays_visible_and_escape_keeps_candidate(recovery_module):
    page = recovery_module
    page.evaluate("""(entries) => {
      window.__recoveryMock.payloads['/api/recovery'] = {entries, offered: true};
      window.__recoveryMock.restoreFailures = 1;
    }""", _entries())
    _start(page, "initRecoveryUI")
    dialog = page.get_by_role("dialog", name="Recover unfinished project")
    assert dialog.get_attribute("aria-modal") == "true"
    dialog.get_by_role("button", name="Restore").click()
    dialog.get_by_role("alert").get_by_text("recovery unavailable").wait_for()
    assert dialog.is_visible()
    page.keyboard.press("Escape")
    page.wait_for_function("() => window.__recoveryResult === null")
    assert page.locator(".recovery-dialog").count() == 0


def test_replacement_requires_successful_save_and_has_explicit_choices(recovery_module):
    page = recovery_module
    page.evaluate("""() => {
      window.__recoveryMock.payloads['/api/project'] = {dirty: true};
      window.__recoveryMock.saveFailures = 1;
    }""")
    _start(page, "resolveProjectReplacement")
    dialog = page.get_by_role("dialog", name="Replace unfinished project?")
    dialog.get_by_role("button", name="Save", exact=True).click()
    dialog.get_by_role("alert").get_by_text("save failed").wait_for()
    assert page.evaluate("() => window.__recoveryResult") is None
    assert dialog.is_visible()
    dialog.get_by_role("button", name="Save", exact=True).click()
    page.wait_for_function("() => window.__recoveryResult?.recovery_action === 'save'")

    for label, expected in [
        ("Continue with recovery", {"recovery_action": "recover"}),
        ("Discard", {"recovery_action": "discard"}),
        ("Cancel", None),
    ]:
        _start(page, "resolveProjectReplacement")
        page.get_by_role("dialog", name="Replace unfinished project?").get_by_role(
            "button", name=label, exact=True).click()
        page.wait_for_function("() => !document.querySelector('.recovery-dialog')")
        assert page.evaluate("() => window.__recoveryResult") == expected


def test_clean_replacement_needs_no_dialog(recovery_module):
    page = recovery_module
    page.evaluate("() => window.__recoveryMock.payloads['/api/project'] = {dirty: false}")
    result = page.evaluate("() => window.__recoveryModule.resolveProjectReplacement()")
    assert result == {}
    assert page.locator(".recovery-dialog").count() == 0


def test_reopen_forces_offer_and_passes_replacement_action_to_restore(recovery_module):
    page = recovery_module
    page.evaluate("""(entries) => {
      window.__recoveryMock.payloads['/api/project'] = {dirty: true};
      window.__recoveryMock.payloads['/api/recovery'] = {entries, offered: false};
    }""", _entries())
    _start(page, "reopenRecoveries")
    page.get_by_role("dialog", name="Replace unfinished project?").get_by_role(
        "button", name="Continue with recovery").click()
    dialog = page.get_by_role("dialog", name="Recover unfinished project")
    dialog.wait_for()
    dialog.get_by_label("Older").check()
    dialog.get_by_role("button", name="Restore").click()
    page.wait_for_function("() => window.__recoveryResult?.action === 'restore'")
    calls = page.evaluate("() => window.__recoveryMock.calls")
    assert ["POST", "/api/recovery/bbbb/restore", {"recovery_action": "recover"}] in calls
    assert ["POST", "/api/recovery/ack", {}] not in calls


def test_startup_ack_failure_is_quiet_after_dialog_opens(recovery_module):
    page = recovery_module
    page.evaluate("""(entries) => {
      window.__recoveryMock.payloads['/api/recovery'] = {entries, offered: true};
      window.__recoveryMock.ackFailures = 1;
    }""", _entries())
    _start(page, "initRecoveryUI")
    assert page.get_by_role("dialog", name="Recover unfinished project").is_visible()
    assert page.evaluate("() => window.__recoveryMock.errors") == []
    page.keyboard.press("Escape")
    page.wait_for_function("() => window.__recoveryResult === null")
