"""HTTP /api/device/* + WS /api/device/ws — LobeHub GatewayClient protocol."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from lca.infrastructure.tools.lca_computer.manifest import LOCAL_SYSTEM_ID as _COMPUTER_IDENTIFIER
from lca.plugins.transport.device_gateway.auth import AuthenticatedUser, AuthError, verify_token
from lca.plugins.transport.device_gateway.hub import DeviceHub, encode_arguments
from lca.plugins.transport.device_gateway.models import DeviceConnection
from lca.plugins.transport.device_gateway.registry import DeviceRegistry
from lca.plugins.transport.device_gateway.settings import DeviceGatewaySettings
from lca.plugins.transport.webserver.handlers.cors import cors_headers

_log = structlog.get_logger(__name__)


def _registry(request: Request) -> DeviceRegistry:
    return cast("DeviceRegistry", request.app.state.devices)


def _hub(request: Request) -> DeviceHub:
    return cast("DeviceHub", request.app.state.device_hub)


def _settings(request: Request) -> DeviceGatewaySettings:
    return cast("DeviceGatewaySettings", request.app.state.device_settings)


def _auth_from_body(request: Request, body: dict[str, Any]) -> AuthenticatedUser:
    token = str(body.get("token") or request.headers.get("authorization") or "")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    token_type = str(body.get("tokenType") or body.get("token_type") or "serviceToken")
    if not token:
        token = _settings(request).service_token
        token_type = "serviceToken"  # noqa: S105
    return verify_token(token, token_type, _settings(request))


async def _read_json(request: Request) -> dict[str, Any]:
    if request.method == "OPTIONS":
        return {}
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


async def device_status(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        user = _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    online = _registry(request).list_online(user.user_id, user.workspace_id)
    return JSONResponse(
        {"online": bool(online), "count": len(online)},
        headers=cors_headers(),
    )


async def list_devices(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        user = _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    devices = _registry(request).list_online(user.user_id, user.workspace_id)
    return JSONResponse(
        {"devices": [d.as_dict() for d in devices]},
        headers=cors_headers(),
    )


async def tool_call(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    device_id = str(body.get("deviceId") or body.get("device_id") or "")
    if not device_id:
        return JSONResponse({"error": "deviceId required"}, status_code=400, headers=cors_headers())
    api_name = str(body.get("apiName") or body.get("api_name") or "")
    identifier = str(body.get("identifier") or _COMPUTER_IDENTIFIER)
    arguments = body.get("arguments") or body.get("params") or {}
    timeout_s = float(body.get("timeout_s") or 60)
    try:
        result = await _hub(request).call_tool(
            device_id,
            {
                "identifier": identifier,
                "apiName": api_name,
                "arguments": encode_arguments(arguments),
                "type": "tool",
            },
            timeout_s=timeout_s,
        )
    except (TimeoutError, ConnectionError) as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)},
            status_code=504,
            headers=cors_headers(),
        )
    return JSONResponse(result, headers=cors_headers())


async def system_info(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    device_id = str(body.get("deviceId") or body.get("device_id") or "")
    try:
        result = await _hub(request).call_rpc(device_id, "systemInfo", {}, timeout_s=15)
    except (TimeoutError, ConnectionError) as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)}, status_code=504, headers=cors_headers()
        )
    return JSONResponse(result, headers=cors_headers())


async def rpc(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    device_id = str(body.get("deviceId") or body.get("device_id") or "")
    method = str(body.get("method") or "")
    params = body.get("params")
    try:
        result = await _hub(request).call_rpc(device_id, method, params, timeout_s=30)
    except (TimeoutError, ConnectionError) as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)}, status_code=504, headers=cors_headers()
        )
    return JSONResponse(result, headers=cors_headers())


async def agent_run(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    _log.info("agent_run_requested", body_keys=list(body.keys()))
    return JSONResponse(
        {"success": True, "operationId": "", "status": "accepted"},
        headers=cors_headers(),
    )


async def upload_files(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    device_id = str(body.get("deviceId") or body.get("device_id") or "")
    files = body.get("files") or {}
    base_dir = str(body.get("baseDir") or body.get("base_dir") or "/home/sandbox-user")
    try:
        result = await _hub(request).call_tool(
            device_id,
            {
                "identifier": _COMPUTER_IDENTIFIER,
                "apiName": "writeFiles",
                "arguments": json.dumps({"files": files, "base_dir": base_dir}),
                "type": "tool",
            },
            timeout_s=60,
        )
    except (TimeoutError, ConnectionError) as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)}, status_code=504, headers=cors_headers()
        )
    return JSONResponse(result, headers=cors_headers())


async def connect_device(websocket: WebSocket) -> None:
    await websocket.accept()
    registry: DeviceRegistry = websocket.app.state.devices
    hub: DeviceHub = websocket.app.state.device_hub
    settings: DeviceGatewaySettings = websocket.app.state.device_settings
    params = websocket.query_params
    device_id = str(params.get("deviceId") or "").strip()
    connection_id = str(params.get("connectionId") or "").strip()
    hostname = str(params.get("hostname") or "")
    platform = str(params.get("platform") or "")
    channel_name = str(params.get("channel") or "cli")
    if not device_id or not connection_id:
        await websocket.send_json(
            {"type": "auth_failed", "reason": "deviceId and connectionId required"}
        )
        await websocket.close(code=4400)
        return
    try:
        hello = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    if not isinstance(hello, dict) or hello.get("type") != "auth":
        await websocket.send_json({"type": "auth_failed", "reason": "expected auth"})
        await websocket.close(code=4400)
        return
    try:
        user = verify_token(
            str(hello.get("token") or ""),
            str(hello.get("tokenType") or "serviceToken"),
            settings,
        )
    except AuthError as exc:
        await websocket.send_json({"type": "auth_failed", "reason": str(exc)})
        await websocket.close(code=4403)
        return
    home = str(hello.get("home") or params.get("home") or "")
    workspace = str(hello.get("workspace") or params.get("workspace") or "/home/sandbox-user")
    registry.register_device(
        device_id=device_id,
        hostname=hostname,
        platform=platform,
        home=home,
        workspace=workspace,
        user_id=user.user_id,
        workspace_id=user.workspace_id,
    )
    conn = DeviceConnection(
        connection_id=connection_id,
        channel=channel_name,
        connected_at=datetime.now(UTC),
        websocket=websocket,
    )
    registry.attach_channel(device_id, conn)
    await websocket.send_json({"type": "auth_success"})
    _log.info("device_online", device_id=device_id, channel=channel_name)
    try:
        while True:
            msg = await websocket.receive_json()
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            if kind == "heartbeat":
                await websocket.send_json({"type": "heartbeat_ack"})
            elif kind in {
                "tool_call_response",
                "rpc_response",
                "system_info_response",
            }:
                request_id = str(msg.get("requestId") or "")
                result = msg.get("result")
                hub.complete(request_id, result if isinstance(result, dict) else {})
            elif kind == "agent_run_ack":
                hub.complete(str(msg.get("operationId") or ""), msg)
            elif kind in {"dsh_notification", "dsh_turn_finished"}:
                hub.handle_dsh_inbound(msg)
    except WebSocketDisconnect:
        pass
    finally:
        live = registry.channel(device_id)
        if live is not None and live.connection_id == connection_id:
            hub.fail_device(device_id, f"device {device_id} offline")
        registry.detach_channel(device_id, connection_id)
        _log.info("device_offline", device_id=device_id, connection_id=connection_id)
