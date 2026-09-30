"""WebSocket /api/device/ws — device channel lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime

from starlette.websockets import WebSocket, WebSocketDisconnect

from lca.plugins.transport.device_hub.auth.auth import AuthError, verify_token
from lca.plugins.transport.device_hub.hub.hub import DeviceHub
from lca.plugins.transport.device_hub.models.models import DeviceConnection
from lca.plugins.transport.device_hub.registry.registry import DeviceRegistry
from lca.plugins.transport.device_hub.routes.context import _log
from lca.plugins.transport.device_hub.settings.settings import DeviceHubSettings


async def connect_device(websocket: WebSocket) -> None:
    await websocket.accept()
    registry: DeviceRegistry = websocket.app.state.devices
    hub: DeviceHub = websocket.app.state.device_hub
    settings: DeviceHubSettings = websocket.app.state.device_settings
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
        pairing_service = getattr(websocket.app.state, "device_pairing", None)
        user = verify_token(
            str(hello.get("token") or ""),
            str(hello.get("tokenType") or "serviceToken"),
            settings,
            pairing_service=pairing_service,
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
    except WebSocketDisconnect:
        # INTENTIONAL: 客户端断开 → 走 finally 清理 hub/registry;
        # WebSocket 关闭是预期结束,不是错误。
        pass
    finally:
        live = registry.channel(device_id)
        if live is not None and live.connection_id == connection_id:
            hub.fail_device(device_id, f"device {device_id} offline")
        registry.detach_channel(device_id, connection_id)
        _log.info("device_offline", device_id=device_id, connection_id=connection_id)
