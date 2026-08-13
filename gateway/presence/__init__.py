"""Presence: which host machines are online. No PTY, no Run."""

from gateway.presence.models import CAP_CONSOLE, CAP_SANDBOX, Device, DeviceStatus
from gateway.presence.registry import PresenceRegistry

__all__ = [
    "CAP_CONSOLE",
    "CAP_SANDBOX",
    "Device",
    "DeviceStatus",
    "PresenceRegistry",
]
