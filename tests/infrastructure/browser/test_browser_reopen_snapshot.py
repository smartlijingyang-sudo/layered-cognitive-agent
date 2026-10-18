"""A preview viewer must get pixels even when the Playwright page was lost."""

from __future__ import annotations

import pytest

from lca.contracts.models.browser.stream import BrowserSessionStatus, BrowserSessionSummary
from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver, choose_chromium_proxy
from lca.infrastructure.browser.screencast_relay import CDPScreencastRelay


class _FakePage:
    def __init__(self) -> None:
        self.url = "https://muse.ai/join"

    async def screenshot(self, **kwargs: object) -> bytes:
        del kwargs
        return b"\xff\xd8\xffmuse"


class _FakeSocket:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)


@pytest.mark.asyncio
async def test_navigate_reopens_missing_page() -> None:
    driver = PlaywrightCDPDriver()
    driver._sessions["brw_lost"] = BrowserSessionSummary(
        session_id="brw_lost",
        url="https://muse.ai/join",
        title="New Tab",
        status=BrowserSessionStatus.IDLE,
        has_active_stream=True,
    )
    driver._relays["brw_lost"] = CDPScreencastRelay("brw_lost")

    async def fake_init(session_id: str, url: str) -> None:
        driver._pages[session_id] = _FakePage()
        old = driver._sessions[session_id]
        driver._sessions[session_id] = BrowserSessionSummary(
            session_id=old.session_id,
            url=url,
            title="Muse",
            status=old.status,
            has_active_stream=True,
        )

    driver._init_cdp_for_session = fake_init  # type: ignore[method-assign]

    summary = await driver.navigate("brw_lost", "https://muse.ai/join")

    assert summary.title == "Muse"
    assert summary.url == "https://muse.ai/join"
    assert driver.has_page("brw_lost")


@pytest.mark.asyncio
async def test_push_snapshot_sends_jpeg_to_connected_viewer() -> None:
    driver = PlaywrightCDPDriver()
    relay = CDPScreencastRelay("brw_live")
    socket = _FakeSocket()
    relay.register_client(socket)
    driver._relays["brw_live"] = relay
    driver._pages["brw_live"] = _FakePage()

    sent = await driver.push_snapshot("brw_live")

    assert sent is True
    assert socket.sent[0][0] == 0x01
    assert socket.sent[0][1:] == b"\xff\xd8\xffmuse"


def test_has_page_drops_a_closed_playwright_page() -> None:
    driver = PlaywrightCDPDriver()

    class _Closed:
        def is_closed(self) -> bool:
            return True

    driver._pages["brw_dead"] = _Closed()
    assert driver.has_page("brw_dead") is False
    assert "brw_dead" not in driver._pages


def test_chrome_proxy_prefers_mihomo_when_env_proxy_resets_chrome() -> None:
    assert (
        choose_chromium_proxy("http://127.0.0.1:7890", mihomo_open=True) == "http://127.0.0.1:7891"
    )
    assert (
        choose_chromium_proxy("http://127.0.0.1:7890", mihomo_open=False) == "http://127.0.0.1:7890"
    )
    assert (
        choose_chromium_proxy("http://127.0.0.1:8888", mihomo_open=True) == "http://127.0.0.1:8888"
    )
