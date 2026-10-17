"""Tests for browser gateway REST routes and WebSocket streaming (INV-BROWSER-05)."""

from unittest.mock import AsyncMock

import pytest
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient

from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver
from lca.plugins.transport.webserver.routes_browser import (
    close_browser_session_endpoint,
    create_browser_session_endpoint,
    get_browser_session_endpoint,
    list_browser_sessions_endpoint,
    navigate_browser_session_endpoint,
    stream_browser_session_ws,
)


@pytest.fixture
def test_app() -> Starlette:
    driver = PlaywrightCDPDriver()
    driver._init_cdp_for_session = AsyncMock()
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
    return app


def test_browser_sessions_crud_endpoints(test_app: Starlette) -> None:
    client = TestClient(test_app)

    # 1. 初始列出会话（为空）
    resp = client.get("/lca-api/browser/sessions")
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []

    # 2. 创建新会话
    resp = client.post(
        "/lca-api/browser/sessions",
        json={
            "session_id": "test_sess_crud",
            "run_id": "run_01",
            "initial_url": "https://example.com",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["session_id"] == "test_sess_crud"
    assert data["url"] == "https://example.com"

    # 3. 单个会话查询
    resp = client.get("/lca-api/browser/sessions/test_sess_crud")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "test_sess_crud"

    # 4. 导航
    resp = client.post(
        "/lca-api/browser/sessions/test_sess_crud/navigate",
        json={"url": "https://python.org"},
    )
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://python.org"

    # 5. 关闭会话
    resp = client.delete("/lca-api/browser/sessions/test_sess_crud")
    assert resp.status_code == 200
    assert resp.json()["closed"] is True

    # 6. 关闭后再次查询为 404
    resp = client.get("/lca-api/browser/sessions/test_sess_crud")
    assert resp.status_code == 404


def test_browser_websocket_screencast_stream(test_app: Starlette) -> None:
    client = TestClient(test_app)
    driver: PlaywrightCDPDriver = test_app.state.browser_driver

    with client.websocket_connect("/lca-api/browser/sessions/test_ws_session/stream") as websocket:
        relay = driver.get_relay("test_ws_session")
        assert relay is not None
        assert relay.client_count == 1

        # 模拟后端推送图像二进制帧
        import asyncio

        asyncio.run(relay.emit_frame(b"\xff\xd8\xffsampleframe"))

        # 前端客户端接收二进制数据
        raw_bytes = websocket.receive_bytes()
        assert raw_bytes[0] == 0x01
        assert raw_bytes[1:] == b"\xff\xd8\xffsampleframe"

        # 前端发送 ACK 确认帧
        websocket.send_json({"type": "ack"})

        # 前端发送输入事件
        websocket.send_json(
            {
                "type": "input",
                "event": {
                    "type": "mouse_down",
                    "x": 640.0,
                    "y": 360.0,
                    "button": "left",
                },
            }
        )

    # 连接断开后验证客户端注销
    assert relay.client_count == 0
