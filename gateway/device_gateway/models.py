"""Device + connection records. Pure data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DeviceConnection:
    """One live WebSocket belonging to a device."""

    connection_id: str
    channel: str
    connected_at: datetime
    websocket: Any = field(repr=False, compare=False)


@dataclass
class Device:
    """One physical machine.  May hold several live channels."""

    device_id: str
    hostname: str
    platform: str
    home: str
    workspace: str
    user_id: str
    workspace_id: str | None = None
    registered_at: datetime | None = None
    channels: list[DeviceConnection] = field(default_factory=list)

    @property
    def online(self) -> bool:
        return bool(self.channels)

    def as_dict(self) -> dict[str, Any]:
        return {
            "deviceId": self.device_id,
            "hostname": self.hostname,
            "platform": self.platform,
            "home": self.home,
            "workspace": self.workspace,
            "userId": self.user_id,
            "workspaceId": self.workspace_id,
            "online": self.online,
            "channels": [
                {
                    "connectionId": c.connection_id,
                    "channel": c.channel,
                    "connectedAt": c.connected_at.isoformat(),
                }
                for c in self.channels
            ],
        }
