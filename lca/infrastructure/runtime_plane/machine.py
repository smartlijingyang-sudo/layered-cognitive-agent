"""Machine candidate + transport injection. Gateway owns Presence."""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.models.core.plane import PlaneRef
from lca.infrastructure.computer.machine import MachineTransport

_machine_resolver: Callable[[str | None], PlaneRef | None] | None = None
_transport_resolver: Callable[[str], MachineTransport | None] | None = None


def set_machine_resolver(
    resolver: Callable[[str | None], PlaneRef | None] | None,
) -> None:
    global _machine_resolver
    _machine_resolver = resolver


def set_machine_transport_resolver(
    resolver: Callable[[str], MachineTransport | None] | None,
) -> None:
    global _transport_resolver
    _transport_resolver = resolver


def resolve_machine(device_id: str | None = None) -> PlaneRef | None:
    if _machine_resolver is None:
        return None
    return _machine_resolver(device_id)


def resolve_machine_transport(device_id: str) -> MachineTransport | None:
    if _transport_resolver is None:
        return None
    return _transport_resolver(device_id)
