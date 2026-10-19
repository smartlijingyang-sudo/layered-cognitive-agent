"""Comprehensive Muse browser lifecycle scenario tests (open / operate / task / human takeover / captcha).

These scenarios drive the full browser stack end to end with a deterministic in-memory
fake page, so they run anywhere without launching Chromium:
- Scenario A: open a browser and confirm the page exposes real content.
- Scenario B: operate the live page (type, click, screenshot) through the browser subagent.
- Scenario C: browser task lifecycle via the task store (list / peek / steer / close); browser_spawn_task fails closed (RA-149).
- Scenario D: human takeover roundtrip over REST + WebSocket (screencast + input arbitration).
- Scenario E: CAPTCHA preference persistence.
- Scenario F: full agent-to-human-to-agent roundtrip across tools and arbitration.

The fake page implements only the Playwright async surface that PlaywrightCDPDriver uses
(locator click/fill/inner_text, input_value, screenshot, goto, title, keyboard), so the
real driver methods are exercised verbatim.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient

from lca.contracts.models.browser.models import BrowserAction, BrowserActionType
from lca.contracts.models.browser.stream import (
    BrowserInputEvent,
    BrowserInputEventType,
    BrowserSessionStatus,
    BrowserSessionSummary,
)
from lca.infrastructure.browser.arbitration import BrowserArbitrationEngine
from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver
from lca.infrastructure.browser.subagent import BrowserSubagent
from lca.infrastructure.tools.browser.tools import (
    BrowserClickTool,
    BrowserCloseTaskTool,
    BrowserCloseTool,
    BrowserFindTool,
    BrowserGetCaptchaPreferenceTool,
    BrowserListTasksTool,
    BrowserOpenTool,
    BrowserPeekTaskTool,
    BrowserScreenshotTool,
    BrowserSetCaptchaPreferenceTool,
    BrowserSteerTaskTool,
    BrowserTransferTaskTool,
)
from lca.plugins.transport.webserver.routes_browser import (
    close_browser_session_endpoint,
    create_browser_session_endpoint,
    get_browser_session_endpoint,
    list_browser_sessions_endpoint,
    navigate_browser_session_endpoint,
    stream_browser_session_ws,
)


class _FakeElement:
    """In-memory DOM element with text, input value, and an optional onclick handler."""

    def __init__(self, tag: str = "div", text: str = "", value: str = "") -> None:
        self.tag = tag
        self.text = text
        self.value = value
        self.onclick: Callable[[], None] | None = None


class _FakeKeyboard:
    """Minimal keyboard double that appends text to the focused element."""

    def __init__(self, page: _FakeDomPage) -> None:
        self._page = page

    async def type(self, text: str) -> None:
        if self._page._focused is not None:
            self._page._focused.value += text


class _FakeLocator:
    """Playwright locator double backed by the fake DOM."""

    def __init__(self, page: _FakeDomPage, selector: str) -> None:
        self._page = page
        self._selector = selector

    async def click(self, timeout: int | None = None) -> None:  # noqa: ASYNC109
        del timeout
        el = self._page._resolve(self._selector)
        if el is None:
            raise RuntimeError(f"Element not found: {self._selector}")
        if el.onclick is not None:
            el.onclick()
        self._page._focused = el

    async def fill(self, text: str, timeout: int | None = None) -> None:  # noqa: ASYNC109
        del timeout
        el = self._page._resolve(self._selector)
        if el is None:
            raise RuntimeError(f"Element not found: {self._selector}")
        el.value = text
        self._page._focused = el

    async def inner_text(self) -> str:
        el = self._page._resolve(self._selector)
        return el.text if el is not None else ""

    async def count(self) -> int:
        return 1 if self._page._resolve(self._selector) is not None else 0


class _FakeDomPage:
    """Deterministic stand-in for the Playwright page used by the browser driver."""

    def __init__(
        self,
        title: str = "Page",
        body_text: str = "",
        url: str = "about:blank",
    ) -> None:
        self.title_text = title
        self.url = url
        self._elements: dict[str, _FakeElement] = {"body": _FakeElement("body", text=body_text)}
        self._focused: _FakeElement | None = None
        self._closed = False

    def _resolve(self, selector: str) -> _FakeElement | None:
        if selector == "body":
            return self._elements["body"]
        return self._elements.get(selector)

    def add_element(self, selector: str, element: _FakeElement) -> None:
        self._elements[selector] = element

    @property
    def keyboard(self) -> _FakeKeyboard:
        return _FakeKeyboard(self)

    async def title(self) -> str:
        return self.title_text

    async def goto(
        self,
        url: str,
        timeout: int | None = None,  # noqa: ASYNC109
        wait_until: str | None = None,
    ) -> None:
        del timeout, wait_until
        self.url = url

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self, selector)

    async def input_value(self, selector: str) -> str:
        el = self._resolve(selector)
        return el.value if el is not None else ""

    async def wait_for_load_state(self, state: str | None = None) -> None:
        del state
        return None

    async def screenshot(
        self,
        type: str | None = None,
        quality: int | None = None,
    ) -> bytes:
        del type, quality
        return b"\xff\xd8\xff\xe0fake_jpeg_payload"

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self._closed = True


def install_fake_page(
    driver: PlaywrightCDPDriver,
    session_id: str,
    page: _FakeDomPage,
) -> None:
    """Inject a deterministic fake page so the real driver methods operate on it."""

    async def fake_init(target_session: str, url: str) -> None:
        driver._pages[target_session] = page
        old = driver._sessions.get(target_session)
        if old is not None:
            driver._sessions[target_session] = BrowserSessionSummary(
                session_id=old.session_id,
                run_id=old.run_id,
                url=url,
                title=page.title_text,
                status=old.status,
                viewport_width=old.viewport_width,
                viewport_height=old.viewport_height,
                has_active_stream=True,
            )

    driver._init_cdp_for_session = fake_init  # type: ignore[method-assign]


def make_app(driver: PlaywrightCDPDriver) -> Starlette:
    """Build the browser REST + WebSocket gateway app bound to a driver."""
    return Starlette(
        routes=[
            Route(
                "/lca-api/browser/sessions",
                list_browser_sessions_endpoint,
                methods=["GET", "OPTIONS"],
            ),
            Route(
                "/lca-api/browser/sessions",
                create_browser_session_endpoint,
                methods=["POST"],
            ),
            Route(
                "/lca-api/browser/sessions/{session_id}",
                get_browser_session_endpoint,
                methods=["GET", "OPTIONS"],
            ),
            Route(
                "/lca-api/browser/sessions/{session_id}/navigate",
                navigate_browser_session_endpoint,
                methods=["POST"],
            ),
            Route(
                "/lca-api/browser/sessions/{session_id}",
                close_browser_session_endpoint,
                methods=["DELETE"],
            ),
            WebSocketRoute(
                "/lca-api/browser/sessions/{session_id}/stream",
                stream_browser_session_ws,
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Scenario A: open a browser and confirm the page has real content.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_open_browser_page_has_content() -> None:
    driver = PlaywrightCDPDriver()
    page = _FakeDomPage(
        title="Muse Portal",
        body_text="Welcome to Muse browser. Login now.",
        url="about:blank",
    )
    sid = "scn_open"
    install_fake_page(driver, sid, page)

    open_tool = BrowserOpenTool(driver=driver)
    obs = await open_tool.execute({"url": "https://example.com", "session_id": sid})

    assert obs.success is True
    text_content = obs.payload["text_content"]
    assert "Muse Portal" in text_content
    assert "Welcome to Muse browser" in text_content  # live page text preview
    assert obs.payload["session_id"] == sid

    find_tool = BrowserFindTool(driver=driver)
    find_obs = await find_tool.execute({"query": "Muse", "session_id": sid})
    assert find_obs.success is True
    assert find_obs.payload["details"]["matches_count"] >= 1


# ---------------------------------------------------------------------------
# Scenario B: operate the live page (type, click, screenshot) via the subagent.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_operate_browser_type_click_screenshot() -> None:
    driver = PlaywrightCDPDriver()
    page = _FakeDomPage(title="Form", body_text="Greeting: Hello", url="about:blank")
    page.add_element("#name", _FakeElement("input", value=""))
    page.add_element("#go", _FakeElement("button", text="Go"))

    def _on_go() -> None:
        name_el = page._resolve("#name")
        page._elements["body"].text = f"Greeting: Hi {name_el.value if name_el else ''}"

    page._resolve("#go").onclick = _on_go  # type: ignore[assignment]
    sid = "scn_operate"
    install_fake_page(driver, sid, page)

    open_tool = BrowserOpenTool(driver=driver)
    await open_tool.execute({"url": "https://example.com", "session_id": sid})

    subagent = BrowserSubagent(agent_id="scn_worker", driver=driver)

    typed = await subagent.execute_action(
        sid,
        BrowserAction(action_type=BrowserActionType.TYPE, selector="#name", text="Muse"),
    )
    assert typed.success is True
    assert typed.details == {"live": True}
    assert await page.input_value("#name") == "Muse"

    clicked = await subagent.execute_action(
        sid,
        BrowserAction(action_type=BrowserActionType.CLICK, selector="#go"),
    )
    assert clicked.success is True
    # RA-154: driver 直驱收敛到共享执行 seam，CLICK 结果塑形与工具路径统一
    # （details 含 selector）；旧精确 {"live": True} 钉的是已消除的分歧。
    assert clicked.details["live"] is True
    assert page._elements["body"].text == "Greeting: Hi Muse"

    # RA-154: EXTRACT_TEXT 经共享执行 seam 走新的 browser_extract_text 工具。
    extracted = await subagent.execute_action(
        sid,
        BrowserAction(action_type=BrowserActionType.EXTRACT_TEXT),
    )
    assert extracted.success is True
    assert extracted.details == {"live": True}
    assert "Greeting: Hi Muse" in (extracted.text_content or "")

    shot_tool = BrowserScreenshotTool(driver=driver)
    shot_obs = await shot_tool.execute({"session_id": sid})
    assert shot_obs.success is True
    assert shot_obs.payload["details"]["live"] is True
    assert "screenshot_base64" in shot_obs.payload["details"]

    # The click tool (agent-facing) also drives the same live page.
    click_tool = BrowserClickTool(driver=driver)
    click_obs = await click_tool.execute({"session_id": sid, "selector": "#go"})
    assert click_obs.success is True
    assert click_obs.payload["details"]["live"] is True

    close_tool = BrowserCloseTool(driver=driver)
    close_obs = await close_tool.execute({"session_id": sid})
    assert close_obs.success is True


# ---------------------------------------------------------------------------
# Scenario C: asynchronous browser task lifecycle.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_browser_task_lifecycle() -> None:
    # RA-149: browser_spawn_task 已 fail-closed（无异步派发后端），场景直接向
    # 共享任务存储登记任务记录，覆盖 list / peek / steer / close 工具链。
    from lca.contracts.atoms.ids.ids import new_id
    from lca.infrastructure.tools.browser.task_store import (
        BrowserTaskRecord,
        get_shared_task_store,
    )

    sid = "scn_task"
    task_id = new_id("btask")
    task_desc = "访问站点并确认登录按钮存在"
    store = get_shared_task_store()
    store.register_task(
        BrowserTaskRecord(
            task_id=task_id,
            task_description=task_desc,
            session_id=sid,
            status="running",
            initial_url="https://example.com",
            current_url="https://example.com",
            title="Browser Task",
        )
    )
    store.add_timeline_step(task_id, "spawn", f"Task spawned: {task_desc[:80]}")

    list_tool = BrowserListTasksTool()
    list_obs = await list_tool.execute({})
    task_ids = [t["browser_task_id"] for t in list_obs.payload["details"]["tasks"]]
    assert task_id in task_ids

    peek_tool = BrowserPeekTaskTool()
    peek_obs = await peek_tool.execute({"browser_task_id": task_id})
    assert peek_obs.payload["details"]["status"] == "running"
    assert len(peek_obs.payload["details"]["timeline"]) >= 1

    steer_tool = BrowserSteerTaskTool()
    steer_obs = await steer_tool.execute({"browser_task_id": task_id, "task": "点击右上角登录按钮"})
    assert steer_obs.success is True
    assert steer_obs.payload["details"]["status"] == "running"

    close_tool = BrowserCloseTaskTool()
    close_obs = await close_tool.execute({"browser_task_id": task_id, "reason": "完成"})
    assert close_obs.success is True
    assert close_obs.payload["details"]["closed"] is True

    peek_after = await peek_tool.execute({"browser_task_id": task_id})
    assert peek_after.payload["details"]["status"] == "closed"


# ---------------------------------------------------------------------------
# Scenario D: human takeover roundtrip over REST + WebSocket.
# ---------------------------------------------------------------------------


def test_scenario_human_takeover_roundtrip() -> None:
    arbitration = BrowserArbitrationEngine()
    driver = PlaywrightCDPDriver(arbitration_engine=arbitration)
    page = _FakeDomPage(
        title="Takeover",
        body_text="Sensitive page content",
        url="https://example.com",
    )
    sid = "scn_takeover"
    install_fake_page(driver, sid, page)
    # RA-150: fake page 只写 _pages；补一个 mock CDP 会话，让"接管后放行派发"的断言走真实 CDP 路径。
    driver._cdp_sessions[sid] = AsyncMock()
    app = make_app(driver)
    app.state.browser_driver = driver
    client = TestClient(app)

    resp = client.post(
        "/lca-api/browser/sessions",
        json={"session_id": sid, "initial_url": "https://example.com"},
    )
    assert resp.status_code == 201
    assert resp.json()["session_id"] == sid

    with client.websocket_connect(f"/lca-api/browser/sessions/{sid}/stream") as ws:
        relay = driver.get_relay(sid)
        assert relay is not None
        assert relay.client_count == 1

        # The connect path pushes an initial snapshot; drain and ack it.
        snapshot = ws.receive_bytes()
        assert snapshot[0] == 0x01
        ws.send_json({"type": "ack"})

        input_event = BrowserInputEvent(
            type=BrowserInputEventType.MOUSE_DOWN,
            x=0.5,
            y=0.5,
            button="left",
        )

        # Agent owns the session -> frontend input is physically dropped.
        arbitration.start_agent_task(sid)
        assert arbitration.get_status(sid) == BrowserSessionStatus.AGENT_RUNNING
        assert asyncio.run(driver.dispatch_input(sid, input_event)) is False

        # Human takes over -> input is allowed and dispatched.
        arbitration.request_human_takeover(sid, reason="user_click_takeover")
        assert arbitration.get_status(sid) == BrowserSessionStatus.HUMAN_TAKEOVER
        assert asyncio.run(driver.dispatch_input(sid, input_event)) is True

        # Screencast frames still reach the viewer with the 0x01 binary header.
        raw_jpeg = b"\xff\xd8\xff\xe0fake_jpeg_payload"
        assert asyncio.run(relay.emit_frame(raw_jpeg)) is True
        frame = ws.receive_bytes()
        assert frame[0] == 0x01
        assert frame[1:] == raw_jpeg
        ws.send_json({"type": "ack"})

        # Human hands control back -> input is dropped again.
        arbitration.release_to_agent(sid)
        assert arbitration.get_status(sid) == BrowserSessionStatus.IDLE
        assert asyncio.run(driver.dispatch_input(sid, input_event)) is False

    resp = client.delete(f"/lca-api/browser/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["closed"] is True


# ---------------------------------------------------------------------------
# Scenario E: CAPTCHA preference persistence.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_captcha_preference_flow() -> None:
    set_tool = BrowserSetCaptchaPreferenceTool()
    set_obs = await set_tool.execute(
        {
            "choice": "ask",
            "scope": {"kind": "site", "value": "shop.example.com"},
            "user_statement": "遇到验证码请询问我",
        }
    )
    assert set_obs.success is True

    get_tool = BrowserGetCaptchaPreferenceTool()
    get_obs = await get_tool.execute({"site": "shop.example.com"})
    assert get_obs.success is True
    assert get_obs.payload["details"]["choice"] == "ask"

    default_obs = await get_tool.execute({"site": "other.example.com"})
    assert default_obs.payload["details"]["choice"] == "solve"


# ---------------------------------------------------------------------------
# Scenario F: full agent -> human takeover -> agent roundtrip.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scenario_agent_to_human_to_agent_roundtrip() -> None:
    # RA-149: browser_spawn_task 已 fail-closed（无异步派发后端），场景直接向
    # 共享任务存储登记任务记录，覆盖 transfer / steer 与仲裁状态机。
    from lca.contracts.atoms.ids.ids import new_id
    from lca.infrastructure.tools.browser.task_store import (
        BrowserTaskRecord,
        get_shared_task_store,
    )

    arbitration = BrowserArbitrationEngine()
    sid = "scn_full"
    task_id = new_id("btask")
    task_desc = "完成注册流程，遇到验证码转交人工"
    store = get_shared_task_store()
    store.register_task(
        BrowserTaskRecord(
            task_id=task_id,
            task_description=task_desc,
            session_id=sid,
            status="running",
            initial_url="https://example.com",
            current_url="https://example.com",
            title="Browser Task",
        )
    )
    store.add_timeline_step(task_id, "spawn", f"Task spawned: {task_desc[:80]}")

    # Agent starts running -> transfer to human takeover.
    arbitration.start_agent_task(sid)
    transfer_tool = BrowserTransferTaskTool(arbitration_engine=arbitration)
    transfer_obs = await transfer_tool.execute(
        {
            "browser_task_id": task_id,
            "target": "human_takeover",
            "reason": "需要人工处理验证码",
        }
    )
    assert transfer_obs.success is True
    assert "status=human_takeover" in transfer_obs.payload["widget_tag"]
    assert arbitration.get_status(sid) == BrowserSessionStatus.HUMAN_TAKEOVER

    # Human completes the verification, then hands control back to agent.
    agent_transfer = BrowserTransferTaskTool(arbitration_engine=arbitration)
    agent_obs = await agent_transfer.execute(
        {
            "browser_task_id": task_id,
            "target": "agent",
            "reason": "用户已完成验证码，交还控制权",
        }
    )
    assert agent_obs.success is True
    assert arbitration.get_status(sid) == BrowserSessionStatus.IDLE

    steer_tool = BrowserSteerTaskTool()
    steer_obs = await steer_tool.execute(
        {"browser_task_id": task_id, "task": "验证码已由用户完成，继续注册"}
    )
    assert steer_obs.success is True

    close_tool = BrowserCloseTaskTool()
    close_obs = await close_tool.execute({"browser_task_id": task_id, "reason": "完成"})
    assert close_obs.success is True
    assert close_obs.payload["details"]["closed"] is True
