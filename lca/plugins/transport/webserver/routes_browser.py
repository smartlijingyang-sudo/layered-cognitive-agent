"""HTTP /lca-api/browser/* and WebSocket /stream — Browser session & streaming routes."""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.browser.stream import (
    BrowserInputEvent,
)
from lca.contracts.protocols.browser import BrowserDriverPort
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.routing import RouteSpec
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver
from lca.plugins.transport.webserver.handlers.cors.cors import cors_headers
from lca.plugins.transport.webserver.route.register import register_routes

logger = logging.getLogger(__name__)

_GLOBAL_BROWSER_DRIVER: PlaywrightCDPDriver | None = None


def get_browser_driver(target: Any) -> BrowserDriverPort:
    """从 Starlette app.state 或全局单例中解析浏览器驱动。"""
    global _GLOBAL_BROWSER_DRIVER
    app = getattr(target, "app", target)
    state = getattr(app, "state", None)
    if state and hasattr(state, "browser_driver"):
        return state.browser_driver  # type: ignore[no-any-return]

    if _GLOBAL_BROWSER_DRIVER is None:
        _GLOBAL_BROWSER_DRIVER = PlaywrightCDPDriver()
    return _GLOBAL_BROWSER_DRIVER


async def list_browser_sessions_endpoint(request: Request) -> Response:
    """列出所有活跃的浏览器会话。"""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    driver = get_browser_driver(request)
    sessions = await driver.list_sessions()
    payload = {"sessions": [s.model_dump() for s in sessions]}
    return JSONResponse(payload, headers=cors_headers())


async def create_browser_session_endpoint(request: Request) -> Response:
    """创建或初始化一个浏览器会话。"""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    body = {}
    with contextlib.suppress(Exception):
        body = await request.json()

    session_id = str(body.get("session_id") or f"sess_{id(request)}")
    run_id = body.get("run_id")
    initial_url = str(body.get("initial_url") or "about:blank")

    driver = get_browser_driver(request)
    summary = await driver.create_session(
        session_id=session_id,
        run_id=run_id,
        initial_url=initial_url,
    )
    return JSONResponse(summary.model_dump(), status_code=201, headers=cors_headers())


async def get_browser_session_endpoint(request: Request) -> Response:
    """获取单个浏览器会话信息。"""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    session_id = request.path_params.get("session_id", "")
    driver = get_browser_driver(request)
    summary = await driver.get_session(session_id)
    if summary is None:
        return JSONResponse({"error": "Session not found"}, status_code=404, headers=cors_headers())

    return JSONResponse(summary.model_dump(), headers=cors_headers())


async def navigate_browser_session_endpoint(request: Request) -> Response:
    """控制浏览器会话导航至新 URL。"""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    session_id = request.path_params.get("session_id", "")
    body = {}
    with contextlib.suppress(Exception):
        body = await request.json()

    url = str(body.get("url") or "about:blank")
    driver = get_browser_driver(request)
    summary = await driver.navigate(session_id, url)
    return JSONResponse(summary.model_dump(), headers=cors_headers())


async def close_browser_session_endpoint(request: Request) -> Response:
    """关闭指定浏览器会话并释放资源。"""
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=cors_headers())

    session_id = request.path_params.get("session_id", "")
    driver = get_browser_driver(request)
    closed = await driver.close_session(session_id)
    return JSONResponse({"closed": closed}, headers=cors_headers())


async def stream_browser_session_ws(websocket: WebSocket) -> None:
    """双向流式通道：下行推送二进制帧，上行接收键鼠控制输入。"""
    await websocket.accept()
    session_id = websocket.path_params.get("session_id", "")
    driver = get_browser_driver(websocket)

    relay = driver.get_relay(session_id)
    if relay is None:
        await driver.create_session(session_id=session_id)
        relay = driver.get_relay(session_id)

    if relay is None:
        await websocket.close(code=1011)
        return

    relay.register_client(websocket)

    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            text_data = msg.get("text")
            if not text_data:
                continue

            try:
                data = json.loads(text_data)
            except Exception as parse_err:
                logger.debug("[routes_browser] Non-json message dropped: %s", parse_err)
                continue

            cmd_type = data.get("type")
            if cmd_type == "ack":
                relay.handle_ack()
            elif cmd_type == "input" and "event" in data:
                try:
                    event = BrowserInputEvent.model_validate(data["event"])
                    await driver.dispatch_input(session_id, event)
                except Exception as err:
                    logger.warning("[routes_browser] Failed to handle input event: %s", err)
            elif cmd_type == "control":
                action = data.get("action")
                if action == "navigate" and "url" in data:
                    await driver.navigate(session_id, str(data["url"]))
    except (WebSocketDisconnect, Exception) as exc:
        logger.debug("[routes_browser] WebSocket stream ended for %s: %s", session_id, exc)
    finally:
        relay.unregister_client(websocket)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()


ROUTE_SPECS = (
    RouteSpec("/lca-api/browser/sessions", list_browser_sessions_endpoint, ("GET", "OPTIONS")),
    RouteSpec("/lca-api/browser/sessions", create_browser_session_endpoint, ("POST", "OPTIONS")),
    RouteSpec("/lca-api/browser/sessions/{session_id}", get_browser_session_endpoint, ("GET", "OPTIONS")),
    RouteSpec("/lca-api/browser/sessions/{session_id}/navigate", navigate_browser_session_endpoint, ("POST", "OPTIONS")),
    RouteSpec("/lca-api/browser/sessions/{session_id}", close_browser_session_endpoint, ("DELETE", "OPTIONS")),
)

_WS_STREAM_PATH = "/lca-api/browser/sessions/{session_id}/stream"


@plugin(
    id="lca-gateway-routes-browser",
    provides=("capability:browser.stream",),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /lca-api/browser/* REST & WebSocket screencast routes.",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-routes-browser.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("gateway_browser_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """标准插件注册装配入口。"""
    registry = ctx.require("route_registry")
    register_routes(registry, ctx, ROUTE_SPECS, plugin_id="lca-gateway-routes-browser")

    from starlette.routing import WebSocketRoute

    ws_dispose = registry.register_websocket(WebSocketRoute(_WS_STREAM_PATH, stream_browser_session_ws))
    inner: Any = ctx._runtime()  # type: ignore[attr-defined]
    inner.effect(ws_dispose, label=f"ws:{_WS_STREAM_PATH}")


__all__ = [
    "ROUTE_SPECS",
    "close_browser_session_endpoint",
    "create_browser_session_endpoint",
    "get_browser_session_endpoint",
    "list_browser_sessions_endpoint",
    "navigate_browser_session_endpoint",
    "setup",
    "stream_browser_session_ws",
]
