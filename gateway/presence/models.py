"""Presence records. Pure data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

CAP_CONSOLE = "console"
CAP_SANDBOX = "sandbox"


class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"


@dataclass(slots=True)
class Device:
    device_id: str
    subject: str
    name: str
    capabilities: tuple[str, ...] = (CAP_CONSOLE,)
    status: DeviceStatus = DeviceStatus.OFFLINE
    connected_at: float = 0.0
    last_seen: float = 0.0
    platform: str = ""
    home: str = ""
    root: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "device_id": self.device_id,
            "subject": self.subject,
            "name": self.name,
            "capabilities": list(self.capabilities),
            "status": self.status.value,
            "connected_at": self.connected_at,
            "last_seen": self.last_seen,
            "platform": self.platform,
            "home": self.home,
            "root": self.root,
        }
