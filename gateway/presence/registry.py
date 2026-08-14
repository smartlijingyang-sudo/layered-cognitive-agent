"""In-process device table. Presence only — does not interpret PTY frames."""

from __future__ import annotations

import time
from typing import Any

from gateway.presence.channel import PresenceChannel
from gateway.presence.models import Device, DeviceStatus


class PresenceRegistry:
    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._channels: dict[str, PresenceChannel] = {}
        self.last_success_id: str = ""

    def online(self, device: Device, channel: PresenceChannel) -> None:
        now = time.time()
        device.status = DeviceStatus.ONLINE
        device.connected_at = now
        device.last_seen = now
        self._devices[device.device_id] = device
        self._channels[device.device_id] = channel

    def offline(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if device is not None:
            device.status = DeviceStatus.OFFLINE
            device.last_seen = time.time()
        self._channels.pop(device_id, None)

    def touch(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        if device is not None:
            device.last_seen = time.time()

    def get(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def channel(self, device_id: str) -> PresenceChannel | None:
        return self._channels.get(device_id)

    def first_online(self, capability: str) -> Device | None:
        online = self.online_with(capability)
        return online[0] if len(online) == 1 else None

    def online_with(self, capability: str) -> list[Device]:
        return [
            device
            for device in self._devices.values()
            if device.status is DeviceStatus.ONLINE and capability in device.capabilities
        ]

    def remember_success(self, device_id: str) -> None:
        self.last_success_id = device_id

    def list_devices(self) -> list[Device]:
        return list(self._devices.values())

    def summary(self) -> dict[str, Any]:
        online = sum(1 for d in self._devices.values() if d.status is DeviceStatus.ONLINE)
        return {"online": online, "devices": len(self._devices)}
