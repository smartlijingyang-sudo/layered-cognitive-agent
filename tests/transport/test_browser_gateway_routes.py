"""Tests for browser gateway REST routes and WebSocket streaming (INV-BROWSER-05)."""

from unittest.mock import AsyncMock

import pytest
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient

from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver
from lca.plugins.transport.webserver.routes_browser import (
    _WS_LCA_STREAM_PATH,
    _WS_STREAM_PATH,
    ROUTE_SPECS,
    setup,
    stream_browser_session_ws,
)


@pytest.fixture
def test_app() -> Starlette:
    driver = PlaywrightCDPDriver()
    driver._init_cdp_for_session = AsyncMock()
    routes = [Route(spec.path, spec.handler, methods=list(spec.methods)) for spec in ROUTE_SPECS]
    routes.append(WebSocketRoute(_WS_STREAM_PATH, stream_browser_session_ws))
    routes.append(WebSocketRoute(_WS_LCA_STREAM_PATH, stream_browser_session_ws))
    app = Starlette(routes=routes)
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


def test_browser_sessions_direct_routes_and_options(test_app: Starlette) -> None:
    """验证 /browser/* 原生短路径与 OPTIONS preflight。"""
    client = TestClient(test_app)

    # 1. OPTIONS 预检请求验证 CORS
    opt_resp = client.options("/browser/sessions")
    assert opt_resp.status_code == 204
    assert opt_resp.headers.get("access-control-allow-methods") is not None

    # 2. POST 创建会话
    resp = client.post(
        "/browser/sessions",
        json={"session_id": "direct_sess_01", "initial_url": "https://news.ycombinator.com"},
    )
    assert resp.status_code == 201
    assert resp.json()["session_id"] == "direct_sess_01"

    # 3. GET 查询会话列表
    list_resp = client.get("/browser/sessions")
    assert list_resp.status_code == 200
    sessions = list_resp.json()["sessions"]
    assert any(s["session_id"] == "direct_sess_01" for s in sessions)

    # 4. DELETE 关闭会话
    del_resp = client.delete("/browser/sessions/direct_sess_01")
    assert del_resp.status_code == 200
    assert del_resp.json()["closed"] is True


@pytest.mark.asyncio
async def test_browser_routes_plugin_setup_contract() -> None:
    """验证 lca-gateway-routes-browser 插件 setup 装配契约。"""
    from unittest.mock import MagicMock

    meta = getattr(setup, "meta", None)
    assert meta is not None
    assert meta["id"] == "lca-gateway-routes-browser"
    assert meta["provides"] == []  # 确保为空，不破坏 plan binding
    assert "route_registry" in meta["requires"]

    mock_registry = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.require.return_value = mock_registry
    mock_runtime = MagicMock()
    mock_ctx._runtime.return_value = mock_runtime

    await setup.setup(mock_ctx, {})
    assert mock_registry.register_http.call_count >= 1
    assert mock_registry.register_websocket.call_count == 2
