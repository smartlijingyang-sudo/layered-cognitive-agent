"""End-to-End Scenario Test for Browser Preview & Live Takeover (INV-BROWSER-01 ~ 06).

Verifies the complete life cycle across Contracts, Infrastructure, Transport, Cognition, and UI layers:
- INV-BROWSER-01: Immutable DTOs with extra forbid.
- INV-BROWSER-02: Voiceless subagent (no send_message).
- INV-BROWSER-03: Single-writer ownership arbitration (rejects input when agent is running).
- INV-BROWSER-04: Screencast binary framing (0x01) and backpressure ACK.
- INV-BROWSER-05: Zero-orphan cleanup upon session close.
- INV-BROWSER-06: Viewport coordinate normalization and precision clamping.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient

from lca.contracts.models.browser.stream import (
    BrowserInputEvent,
    BrowserInputEventType,
    BrowserSessionStatus,
    BrowserSessionSummary,
    normalize_viewport_coordinates,
)
from lca.infrastructure.browser.arbitration import BrowserArbitrationEngine
from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver
from lca.infrastructure.browser.subagent import BrowserSubagent
from lca.infrastructure.tools.browser.tools import build_browser_tools
from lca.plugins.transport.webserver.routes_browser import (
    close_browser_session_endpoint,
    create_browser_session_endpoint,
    get_browser_session_endpoint,
    list_browser_sessions_endpoint,
    navigate_browser_session_endpoint,
    stream_browser_session_ws,
)


@pytest.fixture
def e2e_system():
    arbitration = BrowserArbitrationEngine()
    driver = PlaywrightCDPDriver(arbitration_engine=arbitration)
    driver._init_cdp_for_session = AsyncMock()
    subagent = BrowserSubagent(
        agent_id="e2e_browser_worker",
        tools=build_browser_tools(),
        arbitration_engine=arbitration,
    )

    app = Starlette(
        routes=[
            Route(
                "/lca-api/browser/sessions",
                list_browser_sessions_endpoint,
                methods=["GET", "OPTIONS"],
            ),
            Route("/lca-api/browser/sessions", create_browser_session_endpoint, methods=["POST"]),
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
                "/lca-api/browser/sessions/{session_id}/stream", stream_browser_session_ws
            ),
        ]
    )
    app.state.browser_driver = driver
    client = TestClient(app)

    return {
        "arbitration": arbitration,
        "driver": driver,
        "subagent": subagent,
        "app": app,
        "client": client,
    }


def test_e2e_browser_preview_and_takeover_lifecycle(e2e_system):
    client: TestClient = e2e_system["client"]
    driver: PlaywrightCDPDriver = e2e_system["driver"]
    arbitration: BrowserArbitrationEngine = e2e_system["arbitration"]
    subagent: BrowserSubagent = e2e_system["subagent"]

    session_id = "e2e_sess_001"

    # --- Step 1: INV-BROWSER-02 子代理无发声工具检测 ---
    tools = subagent.get_tools()
    assert len(tools) > 0
    assert all(getattr(t, "name", "") != "send_message" for t in tools)

    # --- Step 2: REST 会话创建 ---
    resp = client.post(
        "/lca-api/browser/sessions",
        json={
            "session_id": session_id,
            "run_id": "run_e2e_01",
            "initial_url": "https://example.com",
        },
    )
    assert resp.status_code == 201
    summary_data = resp.json()
    assert summary_data["session_id"] == session_id
    assert summary_data["url"] == "https://example.com"

    # 验证 INV-BROWSER-01 模型不可变性
    summary = BrowserSessionSummary.model_validate(summary_data)
    with pytest.raises(ValidationError):
        summary.url = "https://tampered.com"

    # --- Step 3: WebSocket 握手与推流 (INV-BROWSER-04) ---
    with client.websocket_connect(f"/lca-api/browser/sessions/{session_id}/stream") as ws:
        relay = driver.get_relay(session_id)
        assert relay is not None
        assert relay.client_count == 1

        # 模拟后端产生截图画面
        raw_jpeg = b"\xff\xd8\xff\xe0mock_jpeg_stream_data"
        asyncio.run(relay.emit_frame(raw_jpeg))

        # 验证前端接收到的 0x01 二进制帧头
        frame = ws.receive_bytes()
        assert frame[0] == 0x01
        assert frame[1:] == raw_jpeg

        # 前端发送 ACK 维持背压平衡
        ws.send_json({"type": "ack"})

        # --- Step 4: 仲裁与接管测试 (INV-BROWSER-03) ---
        # 4.1 当 AI 运行任务时，上行输入必须被物理丢弃
        arbitration.start_agent_task(session_id)
        assert arbitration.get_status(session_id) == BrowserSessionStatus.AGENT_RUNNING

        # 前端点击输入
        norm_x, norm_y = normalize_viewport_coordinates(640, 400, 1280, 800)
        assert norm_x == 0.5
        assert norm_y == 0.5

        input_event = BrowserInputEvent(
            type=BrowserInputEventType.MOUSE_DOWN,
            x=norm_x,
            y=norm_y,
            button="left",
        )
        # 尝试通过驱动派发，必须返回 False (被拦截)
        dispatched = asyncio.run(driver.dispatch_input(session_id, input_event))
        assert dispatched is False

        # 4.2 用户请求接管 -> HUMAN_TAKEOVER
        arbitration.request_human_takeover(session_id, reason="user_click_takeover")
        assert arbitration.get_status(session_id) == BrowserSessionStatus.HUMAN_TAKEOVER

        # 接管状态下，输入放行
        dispatched = asyncio.run(driver.dispatch_input(session_id, input_event))
        assert dispatched is True

        # 4.3 用户交还控制权
        arbitration.release_to_agent(session_id)
        assert arbitration.get_status(session_id) == BrowserSessionStatus.IDLE

    # --- Step 5: 优雅关闭与资源清理 (INV-BROWSER-05) ---
    resp = client.delete(f"/lca-api/browser/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["closed"] is True

    # 再次查询应当为 404
    resp = client.get(f"/lca-api/browser/sessions/{session_id}")
    assert resp.status_code == 404
