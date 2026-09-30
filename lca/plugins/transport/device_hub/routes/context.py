"""Request-context seam for device routes — app-state accessors + auth."""

from __future__ import annotations

from typing import Any, cast

import structlog
from starlette.requests import Request

from lca.plugins.transport.device_hub.auth.auth import AuthenticatedUser, verify_token
from lca.plugins.transport.device_hub.hub.hub import DeviceHub
from lca.plugins.transport.device_hub.pairing.pairing import DevicePairingService
from lca.plugins.transport.device_hub.registry.registry import DeviceRegistry
from lca.plugins.transport.device_hub.settings.settings import DeviceHubSettings

# Keep the original logger name so the split does not change log output.
_log = structlog.get_logger("lca.plugins.transport.device_hub.routes.routes")


def _registry(request: Request) -> DeviceRegistry:
    return cast("DeviceRegistry", request.app.state.devices)


def _hub(request: Request) -> DeviceHub:
    return cast("DeviceHub", request.app.state.device_hub)


def _settings(request: Request) -> DeviceHubSettings:
    return cast("DeviceHubSettings", request.app.state.device_settings)


def _pairing(request: Request) -> DevicePairingService:
    service = getattr(request.app.state, "device_pairing", None)
    if service is None:
        service = DevicePairingService()
        request.app.state.device_pairing = service
    return cast("DevicePairingService", service)


def _auth_from_body(request: Request, body: dict[str, Any]) -> AuthenticatedUser:
    token = str(body.get("token") or request.headers.get("authorization") or "")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    token_type = str(body.get("tokenType") or body.get("token_type") or "serviceToken")
    if not token:
        token = _settings(request).service_token
        token_type = "serviceToken"  # noqa: S105
    pairing_service = getattr(request.app.state, "device_pairing", None)
    return verify_token(token, token_type, _settings(request), pairing_service=pairing_service)


async def _read_json(request: Request) -> dict[str, Any]:
    if request.method == "OPTIONS":
        return {}
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}
