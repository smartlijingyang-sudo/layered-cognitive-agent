"""Presence registry: online table only."""

from __future__ import annotations

from typing import Any

from gateway.presence.models import CAP_CONSOLE, CAP_SANDBOX, Device, DeviceStatus
from gateway.presence.registry import PresenceRegistry


class _Sink:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)


def test_online_then_list() -> None:
    registry = PresenceRegistry()
    sink = _Sink()
    registry.online(
        Device(device_id="local-host", subject="local-dev-user", name="box"),
        sink,
    )
    listed = registry.list_devices()
    assert len(listed) == 1
    assert listed[0].status is DeviceStatus.ONLINE
    assert listed[0].capabilities == (CAP_CONSOLE,)
    assert registry.channel("local-host") is sink
    assert registry.summary() == {"online": 1, "devices": 1}


def test_offline_drops_channel_keeps_record() -> None:
    registry = PresenceRegistry()
    registry.online(
        Device(device_id="local-host", subject="u", name="box"),
        _Sink(),
    )
    registry.offline("local-host")
    device = registry.get("local-host")
    assert device is not None
    assert device.status is DeviceStatus.OFFLINE
    assert registry.channel("local-host") is None
    assert registry.summary()["online"] == 0


def test_first_online_by_capability() -> None:
    registry = PresenceRegistry()
    registry.online(
        Device(device_id="a", subject="u", name="a", capabilities=(CAP_CONSOLE,)),
        _Sink(),
    )
    registry.online(
        Device(device_id="b", subject="u", name="b", capabilities=(CAP_CONSOLE, CAP_SANDBOX)),
        _Sink(),
    )
    found = registry.first_online(CAP_SANDBOX)
    assert found is not None
    assert found.device_id == "b"
