"""Barrel re-export + argument encoding through the device routes entry point."""

from __future__ import annotations

import json

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.plugins.transport.device_hub.routes import routes as barrel
from lca.plugins.transport.device_hub.routes import routes_http, routes_ws
from lca.plugins.transport.device_hub.settings.settings import DeviceHubSettings

_HTTP_HANDLERS = (
    "agent_run",
    "device_status",
    "download_companion",
    "download_runner_bat",
    "download_runner_command",
    "install_ps1",
    "install_sh",
    "list_devices",
    "pair_code",
    "pair_poll",
    "pair_preauth",
    "pair_verify",
    "rpc",
    "system_info",
    "tool_call",
    "upload_files",
)


def test_barrel_reexports_http_handlers() -> None:
    for name in _HTTP_HANDLERS:
        assert getattr(barrel, name) is getattr(routes_http, name)


def test_barrel_reexports_websocket_handler() -> None:
    assert barrel.connect_device is routes_ws.connect_device


class _FakeHub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], float]] = []

    async def call_tool(
        self,
        device_id: str,
        tool_call: dict[str, object],
        *,
        timeout_s: float,
    ) -> dict[str, object]:
        self.calls.append((device_id, tool_call, timeout_s))
        return {"success": True}


def test_tool_call_encodes_arguments_via_barrel() -> None:
    hub = _FakeHub()
    app = Starlette(
        routes=[Route("/api/device/tool-call", barrel.tool_call, methods=["POST", "OPTIONS"])]
    )
    app.state.devices = object()
    app.state.device_hub = hub
    app.state.device_settings = DeviceHubSettings(service_token="test-service-token")  # noqa: S106

    client = TestClient(app)
    resp = client.post(
        "/api/device/tool-call",
        json={
            "token": "test-service-token",
            "deviceId": "dev-1",
            "apiName": "run_command",
            "arguments": {"command": "echo hi"},
        },
    )
    assert resp.status_code == 200
    assert len(hub.calls) == 1
    device_id, tool_call, timeout_s = hub.calls[0]
    assert device_id == "dev-1"
    assert tool_call["apiName"] == "run_command"
    assert tool_call["arguments"] == json.dumps({"command": "echo hi"}, ensure_ascii=False)
    assert tool_call["type"] == "tool"
    assert timeout_s == 60
