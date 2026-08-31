"""Device gateway — LobeHub-aligned device registry + WS protocol."""

from __future__ import annotations

from lca.plugins.transport.device_hub.auth import AuthenticatedUser, AuthError, verify_token
from lca.plugins.transport.device_hub.hub import DeviceHub
from lca.plugins.transport.device_hub.models import Device, DeviceConnection
from lca.plugins.transport.device_hub.registry import DeviceRegistry
from lca.plugins.transport.device_hub.settings import DeviceHubSettings

__all__ = [
    "AuthError",
    "AuthenticatedUser",
    "Device",
    "DeviceConnection",
    "DeviceHub",
    "DeviceHubSettings",
    "DeviceRegistry",
    "verify_token",
]
