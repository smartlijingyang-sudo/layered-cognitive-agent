"""Live Muse browser verification: page loads with content and can be operated (real Chromium)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver

_CHROMIUM_CANDIDATES = [
    Path("/home/lichao/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/chromium-browser"),
    Path("/usr/bin/chromium"),
]


def _chromium_available() -> bool:
    return any(p.is_file() for p in _CHROMIUM_CANDIDATES)


pytestmark = pytest.mark.skipif(
    not _chromium_available(), reason="No Chromium binary for live browser test"
)


@pytest.mark.asyncio
async def test_live_driver_loads_content_and_operates() -> None:
    """Prove a real Chromium page loads with content and can be clicked/screenshotted."""
    driver = PlaywrightCDPDriver(headless=True)
    sid = "live_ops_driver"
    try:
        await driver.create_session(sid, initial_url="https://example.com")
        if driver._pages.get(sid) is None:
            pytest.skip("Playwright did not launch in this environment")

        text = await driver.extract_text(sid)
        assert text, "Live page should expose body text"
        title = await driver._pages[sid].title()
        assert "Example Domain" in title

        link = driver._pages[sid].locator("a[href='https://www.iana.org/domains/example']")
        if await link.count() > 0:
            await link.click()
            await driver._pages[sid].wait_for_load_state("domcontentloaded")
            assert "iana.org" in driver._pages[sid].url

        shot = await driver.take_screenshot(sid)
        assert shot is not None and len(shot) > 100
    finally:
        await driver.close_all()


@pytest.mark.asyncio
async def test_live_browser_tools_operate_on_real_page() -> None:
    """Prove the Muse browser tools drive the same live page instead of returning canned stubs."""
    from lca.infrastructure.tools.browser.tools import (
        BrowserClickTool,
        BrowserFindTool,
        BrowserOpenTool,
        BrowserScreenshotTool,
    )

    driver = PlaywrightCDPDriver(headless=True)
    sid = "live_ops_tools"
    try:
        open_tool = BrowserOpenTool(driver=driver)
        obs = await open_tool.execute({"url": "https://example.com", "session_id": sid})
        assert obs.success is True
        if driver._pages.get(sid) is None:
            pytest.skip("Playwright did not launch")

        find_tool = BrowserFindTool(driver=driver)
        find_obs = await find_tool.execute({"query": "domain", "session_id": sid})
        assert find_obs.success is True
        assert find_obs.payload["details"]["matches_count"] >= 1

        shot_tool = BrowserScreenshotTool(driver=driver)
        shot_obs = await shot_tool.execute({"session_id": sid})
        assert shot_obs.success is True
        assert shot_obs.payload["details"]["live"] is True

        click_tool = BrowserClickTool(driver=driver)
        click_obs = await click_tool.execute(
            {
                "session_id": sid,
                "selector": "a[href='https://www.iana.org/domains/example']",
            }
        )
        link = driver._pages[sid].locator("a[href='https://www.iana.org/domains/example']")
        if await link.count() > 0:
            assert click_obs.success is True
        else:
            assert "live" in click_obs.payload["details"]
    finally:
        await driver.close_all()


@pytest.mark.asyncio
async def test_live_page_interaction_type_and_click() -> None:
    """Prove a real Chromium page can be typed into and clicked (offline, deterministic)."""
    import urllib.parse

    driver = PlaywrightCDPDriver(headless=True)
    sid = "live_ops_interact"
    html = (
        "<html><body><h1 id='greeting'>Hello</h1>"
        "<input id='name' placeholder='name'>"
        "<button id='go' onclick=\"document.getElementById('greeting').textContent='Hi '+"
        "document.getElementById('name').value\">Go</button>"
        "</body></html>"
    )
    url = "data:text/html," + urllib.parse.quote(html)
    try:
        await driver.create_session(sid, initial_url=url)
        if driver._pages.get(sid) is None:
            pytest.skip("Playwright did not launch in this environment")

        page = driver._pages[sid]
        await page.wait_for_load_state("domcontentloaded")

        typed = await driver.type_text(sid, "#name", "Muse")
        assert typed is True
        assert await page.input_value("#name") == "Muse"

        clicked = await driver.click(sid, "#go")
        assert clicked is True
        greeting = await page.locator("#greeting").inner_text()
        assert greeting == "Hi Muse"

        matches = await driver.find_text(sid, "Hi Muse", case_sensitive=True)
        assert matches >= 1
    finally:
        await driver.close_all()
