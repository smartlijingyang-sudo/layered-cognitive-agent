"""Device gateway — LobeHub-aligned device registry + WS protocol."""

from __future__ import annotations

from lca.plugins.transport.device_gateway.auth import AuthenticatedUser, AuthError, verify_token
from lca.plugins.transport.device_gateway.hub import DeviceHub
from lca.plugins.transport.device_gateway.models import Device, DeviceConnection
from lca.plugins.transport.device_gateway.registry import DeviceRegistry
from lca.plugins.transport.device_gateway.settings import DeviceGatewaySettings

__all__ = [
    "AuthError",
    "AuthenticatedUser",
    "Device",
    "DeviceConnection",
    "DeviceGatewaySettings",
    "DeviceHub",
    "DeviceRegistry",
    "verify_token",
]
