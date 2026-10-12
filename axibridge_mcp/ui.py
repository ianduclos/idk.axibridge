"""The agent's eyes on the interface: headless Chromium against a target's
UI, for dogfooding. Mac bench only (needs `playwright install chromium`).
Clicks are real: on `live` they edit Ian's project — prefer the sandbox."""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field


class UiStep(BaseModel):
    action: Literal["click", "fill", "press", "wait"]
    selector: str | None = None
    text: str | None = None
    ms: int = Field(default=500, ge=0, le=5000)


def screenshot(base_url: str, tab: str | None, steps: list[UiStep],
               width: int, height: int) -> bytes:
    try:
        from playwright.sync_api import Error as PwError, sync_playwright
    except ImportError:
        raise ToolError("playwright isn't installed in the venv") from None
    with sync_playwright() as p:  # function-scoped on purpose (CLAUDE.md)
        try:
            browser = p.chromium.launch(headless=True)
        except PwError as e:
            raise ToolError("no chromium — run `.venv/bin/python -m playwright install chromium` "
                            f"({str(e)[:120]})") from None
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(base_url, wait_until="domcontentloaded")  # SSE: never networkidle
            page.wait_for_function(
                "() => document.querySelectorAll('#gen-select option').length > 0",
                timeout=20_000)
            if tab:
                page.click(f'button[data-tab="{tab}"]', timeout=5_000)
            for i, step in enumerate(steps, 1):
                try:
                    if step.action == "click":
                        page.click(step.selector or "", timeout=5_000)
                    elif step.action == "fill":
                        page.fill(step.selector or "", step.text or "", timeout=5_000)
                    elif step.action == "press":
                        page.keyboard.press(step.text or "")
                    page.wait_for_timeout(step.ms if step.action == "wait" else 150)
                except PwError as e:
                    raise ToolError(f"step {i} ({step.action} {step.selector or step.text}) "
                                    f"failed: {str(e).splitlines()[0][:200]}") from None
            return page.screenshot()
        finally:
            browser.close()
