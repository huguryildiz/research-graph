"""Real-browser regressions for the local control room.

These tests are isolated behind ``RGRAPH_BROWSER_TESTS=1``. The ordinary test
matrix needs no browser binary; CI has a dedicated Chromium job for this file.
"""

from __future__ import annotations

import os
import pathlib
import threading

import pytest

from rgraph.webui.server import create_server


pytestmark = pytest.mark.skipif(
    os.environ.get("RGRAPH_BROWSER_TESTS") != "1",
    reason="set RGRAPH_BROWSER_TESTS=1 in the dedicated browser environment",
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def browser_server(example_run):
    server, app = create_server(ROOT, example_run, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    app.jobs.shutdown()
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


@pytest.fixture
def playwright_runtime():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as runtime:
        yield runtime


def _open_workspace(runtime, url: str, viewport: dict[str, int]):
    browser = runtime.chromium.launch()
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    errors: list[str] = []
    page.on(
        "console",
        lambda message: errors.append(message.text) if message.type == "error" else None,
    )
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url, wait_until="networkidle")
    page.locator('body[data-mode="workspace"]').wait_for()
    return browser, page, errors


def test_desktop_drawer_traps_focus_and_restores_its_trigger(
    browser_server, playwright_runtime,
):
    browser, page, errors = _open_workspace(
        playwright_runtime, browser_server, {"width": 1440, "height": 900},
    )
    try:
        trigger = page.locator(".gate-row").first
        trigger.focus()
        trigger.click()
        drawer = page.locator("#drawer")
        assert drawer.get_attribute("aria-hidden") == "false"
        assert page.locator("#drawer-close").evaluate(
            "element => document.activeElement === element"
        )

        page.keyboard.press("Shift+Tab")
        assert drawer.evaluate("element => element.contains(document.activeElement)")
        page.keyboard.press("Tab")
        assert drawer.evaluate("element => element.contains(document.activeElement)")

        page.keyboard.press("Escape")
        assert drawer.get_attribute("aria-hidden") == "true"
        assert trigger.evaluate("element => document.activeElement === element")
        assert errors == []
    finally:
        browser.close()


def test_mobile_view_has_no_document_overflow_and_keeps_touch_targets_usable(
    browser_server, playwright_runtime,
):
    browser, page, errors = _open_workspace(
        playwright_runtime, browser_server, {"width": 390, "height": 844},
    )
    try:
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        page.locator(".gate-row").first.click()
        close_box = page.locator("#drawer-close").bounding_box()
        assert close_box is not None
        assert close_box["width"] >= 44 and close_box["height"] >= 44
        assert page.locator("#drawer-title").is_visible()
        assert errors == []
    finally:
        browser.close()
