"""Device gateway — LobeHub-aligned device registry + WS protocol."""

from __future__ import annotations

from gateway.device_gateway.auth import AuthenticatedUser, AuthError, verify_token
from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.models import Device, DeviceConnection
from gateway.device_gateway.registry import DeviceRegistry
from gateway.device_gateway.settings import DeviceGatewaySettings

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
