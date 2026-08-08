"""Real-browser regressions for the local control room.

These tests are isolated behind ``RGRAPH_BROWSER_TESTS=1``. The ordinary test
matrix needs no browser binary; CI has a dedicated Chromium job for this file.
"""

from __future__ import annotations

import functools
import http.server
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


class _QuietStaticHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format, *args):
        pass


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
def public_site_server():
    handler = functools.partial(_QuietStaticHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
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


def test_mobile_view_reflows_when_text_is_enlarged_to_two_hundred_percent(
    browser_server, playwright_runtime,
):
    browser, page, errors = _open_workspace(
        playwright_runtime, browser_server, {"width": 390, "height": 844},
    )
    try:
        page.evaluate('document.documentElement.style.fontSize = "200%"')
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        assert page.locator("#home-button").is_visible()
        assert page.locator("#refresh-button").is_visible()
        assert page.locator(".gate-row").first.is_visible()
        assert errors == []
    finally:
        browser.close()


def test_reference_run_graph_explains_the_selected_real_stage(
    public_site_server, playwright_runtime,
):
    browser = playwright_runtime.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors: list[str] = []
    page.on(
        "console",
        lambda message: errors.append(message.text) if message.type == "error" else None,
    )
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(public_site_server + "reference-run.html", wait_until="networkidle")
        graph = page.frame_locator("#run-map")
        graph.locator('[data-node-id="c7"]').click()
        page.locator("#detail-title").wait_for()
        assert page.locator("#detail-title").text_content() == "Run the comparison"
        assert "25 of 25" in page.locator("#detail-result").text_content()

        graph.locator('[data-node-id="c10"]').click()
        assert page.locator("#detail-title").text_content() == (
            "Expose what could weaken the conclusion"
        )
        assert "15 of 25" in page.locator("#detail-result").text_content()
        assert errors == []
    finally:
        browser.close()
